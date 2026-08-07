"""行情面板数据服务

从本地 Parquet 缓存（优先）或 QMT 加载多标的行情，
组装为面板 DataFrame (index=交易日, columns=股票代码)。
供因子计算、回测等场景使用；无数据时抛出带明确提示的 ValueError。
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
from loguru import logger

from backend.data.cache import DataCache
from backend.data.converter import normalize_kline_fields, normalize_timestamp
from backend.data.qmt_client import QMTClient

_cache = DataCache()
_qmt = QMTClient()


def data_freshness(period: str = "1d", max_codes: int = 300) -> dict:
    """数据时效检查：统计各缓存标的的最新交易日及其陈旧天数（相对今日）

    Returns:
        {"latest": str, "stale_count": int, "total": int,
         "stale": [{"code", "latest_date", "staleness_days"}], "fresh": [...]}
    """
    codes = list_cached_codes(period)
    today = date.today()
    rows: list[dict] = []
    for code in codes[:max_codes]:
        ts = _cache.get_latest_timestamp(code, period)
        if not ts:
            continue
        try:
            dt = pd.Timestamp(ts)
            latest_d = dt.date()
        except Exception:
            continue
        rows.append(
            {
                "code": code,
                "latest_date": str(latest_d),
                "staleness_days": (today - latest_d).days,
            }
        )
    latest_date = max((r["latest_date"] for r in rows), default=None)
    stale_threshold = 7  # 停牌/新股可能久缺数，7 天作为"明显滞后"的经验阈值
    stale = [r for r in rows if r["staleness_days"] > stale_threshold]
    return {
        "period": period,
        "total": len(rows),
        "latest_date": latest_date,
        "staleness_days": (today - pd.Timestamp(latest_date).date()).days
        if latest_date
        else None,
        "stale_count": len(stale),
        "stale": stale[:50],
        "status": "ok" if not stale else "stale",
    }

PRICE_FIELDS = ["open", "high", "low", "close", "volume", "amount"]

# 统一话术：空缓存 / 未连接时的指引文案，各处保持一致，研究员可据此判断「没数据」而非「出 bug」
_CACHE_GUIDE = "请先在「数据中心」下载行情数据（数据管理 → 按板块/代码批量下载），或核对缓存目录"


def no_cache_error_detail(scope: str = "") -> dict:
    """统一的「本地无缓存数据」结构化错误体

    code 供程序分支（如 QUBE/CLI 判断 no_cached_data），message/hint 供人阅读。
    """
    msg = "本地无缓存行情数据"
    if scope:
        msg += f"（{scope}）"
    return {"code": "no_cached_data", "message": msg, "hint": _CACHE_GUIDE}


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


def _load_single(code: str, period: str, adjust: str = "qfq") -> pd.DataFrame | None:
    """加载单只股票 K 线：本地缓存优先，其次 QMT（并回写缓存）

    adjust: qfq（前复权，默认，与历史行为一致）/ hfq（后复权）/ none（不复权）。
    缓存帧含不复权价 + adjust_factor 列；旧版前复权缓存（无 factor 列）
    在 qfq 模式下透明兼容，hfq/none 模式明确报错提示重下。
    """
    df = _cache.get(code, period)
    if df is not None and not df.empty:
        return _apply_adjust(df, code, adjust)

    if _qmt.connected:
        try:
            df = _fetch_and_cache(code, period)
            if df is not None:
                return _apply_adjust(df, code, adjust)
        except Exception as e:
            logger.warning(f"QMT 获取 {code} 行情失败: {e}")
    return None


# 旧版缓存（前复权价、无 adjust_factor 列）已按 qfq 读取的标记
_legacy_adjust: set[str] = set()


def _apply_adjust(df: pd.DataFrame, code: str, adjust: str = "qfq") -> pd.DataFrame:
    """把含 adjust_factor 列的缓存帧换算为目标复权口径

    存储语义：不复权 OHLCV + adjust_factor（= 后复权价 / 不复权价，锚定上市日，
    新增除权事件不改变历史 factor，增量缓存天然一致；前复权 = raw × factor/latest_factor）。
    """
    if adjust not in ("qfq", "hfq", "none"):
        raise ValueError(f"未知复权口径: {adjust}（可选 qfq/hfq/none）")
    if "adjust_factor" not in df.columns:
        if adjust != "qfq":
            raise ValueError(
                f"{code} 为旧版前复权缓存，仅支持 qfq 读取 — "
                "请重新下载该标的以启用复权因子存储（raw + adjust_factor）"
            )
        _legacy_adjust.add(code)
        df = df.copy()
        df["adjust_factor"] = 1.0
        return df
    if adjust == "qfq":
        df = df.copy()
        scale = df["adjust_factor"] / float(df["adjust_factor"].iloc[-1])
        for col in ("open", "high", "low", "close"):
            if col in df.columns:
                df[col] = df[col].astype(float) * scale
    elif adjust == "hfq":
        df = df.copy()
        for col in ("open", "high", "low", "close"):
            if col in df.columns:
                df[col] = df[col].astype(float) * df["adjust_factor"].astype(float)
    return df


def _fetch_and_cache(code: str, period: str) -> pd.DataFrame | None:
    """从 QMT 拉不复权 + 后复权两套数据，合成 adjust_factor 并落缓存

    后复权锚定上市日，增量缓存自洽（新增除权只影响事件之后的价格），
    前复权由 raw × factor/latest_factor 在读取时合成，根治跨除权重算问题。
    """
    raw = _qmt.get_kline([code], period=period, dividend_type="none").get(code)
    if raw is None or raw.empty:
        return None
    raw = normalize_kline_fields(raw)
    back = _qmt.get_kline([code], period=period, dividend_type="back").get(code)
    if back is None or back.empty:
        logger.warning(f"{code} 后复权数据缺失，adjust_factor 置 1（按不复权存储）")
        raw = raw.copy()
        raw["adjust_factor"] = 1.0
    else:
        back = normalize_kline_fields(back)
        raw = _merge_with_factor(raw, back)
    _cache.save(code, period, raw)
    return raw


def _merge_with_factor(raw: pd.DataFrame, back: pd.DataFrame) -> pd.DataFrame:
    """不复权帧 + 后复权帧 → 不复权 OHLCV + adjust_factor 列（按日期对齐）"""
    raw = raw.copy()
    raw.index = normalize_timestamp(raw.index).normalize()
    back_close = back["close"].astype(float)
    back_close.index = normalize_timestamp(back_close.index).normalize()
    back_close = back_close[~back_close.index.duplicated(keep="last")]
    factor = back_close.reindex(raw.index)
    raw_close = raw["close"].astype(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        raw["adjust_factor"] = (factor / raw_close).replace([np.inf, -np.inf], np.nan)
    # 无除权区间 factor≈1，缺失回填 1（避免 NaN 污染收益序列）
    raw["adjust_factor"] = raw["adjust_factor"].fillna(1.0)
    return raw


def load_price_panels(
    codes: list[str],
    start_date: str = "",
    end_date: str = "",
    period: str = "1d",
    adjust: str = "qfq",
) -> dict[str, pd.DataFrame]:
    """加载多只股票的行情面板

    Args:
        codes: 股票代码列表；空则取全部本地缓存
        adjust: 复权口径（qfq 默认 / hfq / none）

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
            + _CACHE_GUIDE
            + "，或在股票池中填入代码"
        )

    frames: dict[str, dict[str, pd.Series]] = {f: {} for f in PRICE_FIELDS}
    missing: list[str] = []

    for code in codes:
        df = _load_single(code, period, adjust=adjust)
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
            + _CACHE_GUIDE
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


def build_cross_section_mask(
    panels: dict,
    min_list_days: int = 20,
    exclude_st: bool = True,
) -> pd.DataFrame | None:
    """构建每日「可交易」掩码（True=可交易），供因子 IC/分层截面过滤。

    规则组合（任一为 False 即排除）:
      - 停牌: 成交量=0 / 缺数据
      - ST: 最新合约名称含 ST（referrence instrument 快照）
      - 次新股: 上市日距今 < min_list_days（缺 instrument 时不排除）

    Returns:
        DataFrame(index=date, columns=code)，无可判定信息时返回 None
    """
    close = panels.get("close")
    if close is None or close.empty:
        return None
    mask = pd.DataFrame(True, index=close.index, columns=close.columns, dtype=float)

    # 停牌（成交量>0 才可交易）
    volume = panels.get("volume")
    if volume is not None and not volume.empty:
        vol = volume.reindex(index=close.index, columns=close.columns).fillna(0.0)
        mask = mask & (vol > 0)

    if exclude_st:
        try:
            from backend.services import reference_data

            inst = reference_data.load_instrument_frame()
            if inst is not None and not inst.empty:
                names = inst["name"].fillna("").str.upper()
                st_codes = set(names[names.str.contains("ST")].index)
                for c in st_codes:
                    if c in mask.columns:
                        mask[c] = False
        except Exception:
            pass

    if min_list_days > 0:
        try:
            from backend.services import reference_data

            inst = reference_data.load_instrument_frame()
            if inst is not None and "list_date" in inst.columns:
                now = close.index[-1]
                for code, row in inst.iterrows():
                    ld = row.get("list_date")
                    if not ld or code not in mask.columns:
                        continue
                    try:
                        ld = pd.to_datetime(str(ld))
                        if (now - ld).days < min_list_days:
                            mask[code] = False
                    except Exception:
                        continue
        except Exception:
            pass

    if mask.all().all():
        # 没有任何可判定信息，视为无过滤
        return mask
    return mask


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
