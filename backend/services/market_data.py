"""行情面板数据服务

从本地 Parquet 缓存（优先）或 QMT 加载多标的行情，
组装为面板 DataFrame (index=交易日, columns=股票代码)。
供因子计算、回测等场景使用；无数据时抛出带明确提示的 ValueError。
"""

from __future__ import annotations

import pandas as pd
from loguru import logger

from backend.data.cache import DataCache
from backend.data.converter import normalize_kline_fields, normalize_timestamp
from backend.data.qmt_client import QMTClient

_cache = DataCache()
_qmt = QMTClient()

PRICE_FIELDS = ["open", "high", "low", "close", "volume", "amount"]


def list_cached_codes(period: str = "1d") -> list[str]:
    """列出本地缓存中指定周期的全部股票代码"""
    period_dir = _cache._cache_dir / period
    if not period_dir.exists():
        return []
    codes = []
    for f in sorted(period_dir.glob("*.parquet")):
        # 文件名中 '.' 被替换为 '_'，还原为标准代码
        stem = f.stem
        if "_" in stem:
            code, market = stem.rsplit("_", 1)
            codes.append(f"{code}.{market}")
        else:
            codes.append(stem)
    return codes


def _load_single(code: str, period: str) -> pd.DataFrame | None:
    """加载单只股票 K 线：本地缓存优先，其次 QMT（并回写缓存）"""
    df = _cache.get(code, period)
    if df is not None and not df.empty:
        return df

    if _qmt.connected:
        try:
            data = _qmt.get_kline([code], period=period)
            df = data.get(code)
            if df is not None and not df.empty:
                _cache.save(code, period, df)
                return df
        except Exception as e:
            logger.warning(f"QMT 获取 {code} 行情失败: {e}")
    return None


def load_price_panels(
    codes: list[str],
    start_date: str = "",
    end_date: str = "",
    period: str = "1d",
) -> dict[str, pd.DataFrame]:
    """加载多只股票的行情面板

    Returns:
        {field: DataFrame(index=date, columns=code)}，field 含 open/high/low/close/volume/amount

    Raises:
        ValueError: 无任何可用数据时，给出明确的解决提示
    """
    if not codes:
        codes = list_cached_codes(period)
    if not codes:
        raise ValueError(
            "本地无缓存行情数据且未指定股票池 — "
            "请先在「数据管理」页下载行情数据，或在股票池中填入代码"
        )

    frames: dict[str, dict[str, pd.Series]] = {f: {} for f in PRICE_FIELDS}
    missing: list[str] = []

    for code in codes:
        df = _load_single(code, period)
        if df is None or df.empty:
            missing.append(code)
            continue
        df = normalize_kline_fields(df)
        df = df.copy()
        df.index = normalize_timestamp(df.index)
        df = df.sort_index()
        for field in PRICE_FIELDS:
            if field in df.columns:
                frames[field][code] = df[field].astype(float)

    if not frames["close"]:
        qmt_hint = "" if _qmt.connected else "（QMT 未连接，无法在线获取）"
        raise ValueError(
            f"未找到任何行情数据{qmt_hint} — 缺失: {', '.join(missing[:10])}。"
            "请先在「数据管理」页下载对应股票的日线数据"
        )

    panels: dict[str, pd.DataFrame] = {}
    for field, series_map in frames.items():
        if not series_map:
            continue
        panel = pd.DataFrame(series_map).sort_index()
        # 统一为无时区的日期索引，便于按区间过滤与序列化
        idx = pd.to_datetime(panel.index)
        if idx.tz is not None:
            idx = idx.tz_localize(None)
        panel.index = idx.normalize()
        if start_date:
            panel = panel[panel.index >= pd.to_datetime(start_date)]
        if end_date:
            panel = panel[panel.index <= pd.to_datetime(end_date)]
        panels[field] = panel

    if "close" not in panels or panels["close"].empty:
        raise ValueError(
            "所选日期区间内无行情数据 — 请调整起止日期或先下载对应区间的数据"
        )
    return panels


def panel_to_dict(panel: pd.DataFrame) -> dict:
    """DataFrame(index=date, columns=code) -> {date_str: {code: value}}（NaN 剔除）"""
    result: dict[str, dict[str, float]] = {}
    for ts, row in panel.iterrows():
        clean = {k: float(v) for k, v in row.items() if pd.notna(v)}
        if clean:
            result[str(ts.date())] = clean
    return result


# ── 缓存覆盖度 ─────────────────────────────────────────────

# {path: (mtime, entry)} — 文件未变时免重复读 parquet
_coverage_cache: dict[str, tuple[float, dict]] = {}


def cache_coverage(period: str = "1d") -> list[dict]:
    """扫描本地缓存，返回每只股票的起止日期与条数

    Returns:
        [{code, start, end, rows}]，按 code 排序
    """
    period_dir = _cache._cache_dir / period
    if not period_dir.exists():
        return []

    entries: list[dict] = []
    for f in sorted(period_dir.glob("*.parquet")):
        stem = f.stem
        if "_" in stem:
            head, market = stem.rsplit("_", 1)
            code = f"{head}.{market}"
        else:
            code = stem

        mtime = f.stat().st_mtime
        cached = _coverage_cache.get(str(f))
        if cached and cached[0] == mtime:
            entries.append(cached[1])
            continue

        try:
            df = pd.read_parquet(f)
            idx = normalize_timestamp(df.index)
            entry = {
                "code": code,
                "start": str(pd.Timestamp(idx.min()).date()) if len(idx) else None,
                "end": str(pd.Timestamp(idx.max()).date()) if len(idx) else None,
                "rows": len(df),
            }
        except Exception as e:
            logger.warning(f"读取缓存 {f} 失败: {e}")
            entry = {"code": code, "start": None, "end": None, "rows": 0}
        _coverage_cache[str(f)] = (mtime, entry)
        entries.append(entry)
    return entries


# ── 参考数据面板装配 ─────────────────────────────────────


def load_reference_panels(
    close: pd.DataFrame,
    volume: pd.DataFrame | None = None,
) -> dict:
    """装配回测/中性化所需的参考面板，缺失项为 None 并记入 assumptions

    Returns:
        {
          tradable_mask: DataFrame|None,   可交易掩码（停牌推断）
          up_limit / down_limit: DataFrame|None,  涨跌停近似价
          market_cap: DataFrame|None,      流通市值面板
          industry_map: dict[code, industry],
          assumptions: [str],              未能处理的假设清单（报告页展示）
        }
    """
    from backend.services import reference_data

    assumptions: list[str] = []

    tradable = None
    if volume is not None and not volume.empty:
        tradable = reference_data.build_tradable_mask(
            volume.reindex(index=close.index, columns=close.columns)
        )
    else:
        assumptions.append("无成交量数据，未处理停牌（停牌日仍可交易）")

    up_limit, down_limit = reference_data.build_limit_prices(close)

    market_cap = reference_data.build_market_cap_panel(close)
    if market_cap is None:
        assumptions.append("无股本快照，市值面板不可用（市值中性化/换手率不可用）")

    industry_map = reference_data.load_industry_map()
    if not industry_map:
        assumptions.append("无行业分类快照，行业中性化不可用")

    return {
        "tradable_mask": tradable,
        "up_limit": up_limit,
        "down_limit": down_limit,
        "market_cap": market_cap,
        "industry_map": industry_map,
        "assumptions": assumptions,
    }
