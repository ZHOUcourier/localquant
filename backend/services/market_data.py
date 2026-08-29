"""行情面板数据服务

从本地 Parquet 缓存（优先）或 QMT 加载多标的行情，
组装为面板 DataFrame (index=交易日, columns=股票代码)。
供因子计算、回测等场景使用；无数据时抛出带明确提示的 ValueError。
"""

from __future__ import annotations

import json
from datetime import datetime

import numpy as np
import pandas as pd
from loguru import logger

from backend.config import settings
from backend.data.cache import DataCache
from backend.data.converter import normalize_kline_fields, normalize_timestamp
from backend.data.qmt_client import QMTClient

_cache = DataCache()
_qmt = QMTClient()


def data_freshness(period: str = "1d", max_codes: int = 300) -> dict:
    """数据时效检查：统计各缓存标的的最新交易日及其陈旧程度（相对最新交易日历）

    陈旧口径：自然日 vs 工作日（交易日历不可得时用工作日近似）。
    长假（春节/国庆）按交易日历判定不会误报「数据断档」。
    """
    codes = list_cached_codes(period)
    today = datetime.now().astimezone().date()
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
    latest_ts = pd.Timestamp(latest_date) if latest_date else None

    # 交易日历（QMT 有则用，未连接用工作日近似）：陈旧判定 = 最近数据日距「最新应交易日」的交易日数
    trade_dates = _trading_calendar()
    if latest_ts is not None:
        if trade_dates is not None:
            past = [d for d in trade_dates if d <= latest_ts.date()]
            latest_trade_idx = len(past) - 1
            expected_idx = len(trade_dates) - 1
            stale_trade_days = expected_idx - latest_trade_idx
        else:
            stale_trade_days = len(pd.bdate_range(latest_ts.date(), today)) - 1
    else:
        stale_trade_days = None

    # 停牌/新股可能久缺数，以「交易日」为经验阈值（约 5 个交易日明显滞后）
    stale_threshold = 5
    per_code_stale = {}
    for r in rows:
        if latest_ts is None:
            per_code_stale[r["code"]] = 0
            continue
        d = pd.Timestamp(r["latest_date"]).date()
        if trade_dates is not None:
            past = [x for x in trade_dates if x <= d]
            idx = len(past) - 1
            per_code_stale[r["code"]] = expected_idx - idx
        else:
            per_code_stale[r["code"]] = len(pd.bdate_range(d, today)) - 1
    stale = [
        {**r, "stale_trade_days": per_code_stale.get(r["code"], 0)}
        for r in rows
        if per_code_stale.get(r["code"], 0) > stale_threshold
    ]
    return {
        "period": period,
        "total": len(rows),
        "latest_date": latest_date,
        "staleness_days": (today - latest_ts.date()).days if latest_ts is not None else None,
        "stale_trade_days": stale_trade_days,
        "stale_threshold_trade_days": stale_threshold,
        "calendar": "qmt" if trade_dates is not None else "weekday_approx",
        "stale_count": len(stale),
        "stale": stale[:50],
        "status": "ok" if not stale else "stale",
    }


# 交易日历缓存（QMT 拉取失败/未连接时为 None → 用工作日近似）
_trade_cal: dict = {"ts": 0.0, "dates": None}
_TRADE_CAL_TTL = 6 * 3600


def _trading_calendar() -> list | None:
    """QMT 交易日历（SH 市场，覆盖 A 股主要交易日）；未连接/失败返回 None"""
    import time

    now = time.time()
    if now - _trade_cal["ts"] < _TRADE_CAL_TTL:
        return _trade_cal["dates"]
    _trade_cal["ts"] = now
    _trade_cal["dates"] = None
    if not _qmt.connected:
        return None
    try:
        dates = _qmt.get_trading_dates(market="SH")
        parsed = sorted(
            {pd.Timestamp(d).date() for d in dates}
        )
        if parsed:
            _trade_cal["dates"] = parsed
    except Exception as e:
        logger.warning(f"获取交易日历失败: {e}")
    return _trade_cal["dates"]


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


def list_cached_codes(period: str = "1d", exclude_indices: bool = False) -> list[str]:
    """列出本地缓存中指定周期的全部股票代码

    exclude_indices=True 时，尽量只保留股票/退市历史代码（剔除宽基指数等
    非个股缓存）。优先以 reference/instrument.parquet 的标的清单判定；
    快照不存在时保持原样返回（宁多勿少，避免误删可研究标的）。
    """
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
    if not exclude_indices or not codes:
        return codes

    def _is_index_like(code: str) -> bool:
        """按代码形态识别常见宽基指数缓存（不依赖快照，宁少勿多）。

        上证指数均为 000xxx.SH；深证指数为 399xxx.SZ；北证指数为 899xxx.BJ。
        股票代码不会落在这些段位（沪市 6xx/688，深市 000/001/002/003/300/301）。
        """
        if code.endswith(".SH"):
            return code.startswith("000")
        if code.endswith(".SZ"):
            return code.startswith("399")
        if code.endswith(".BJ"):
            return code.startswith("899")
        return False

    try:
        from backend.services import reference_data

        inst = reference_data.load_instrument_frame()
        if inst is not None and not inst.empty:
            # load_instrument_frame 返回 index=code 的 DataFrame；
            # 历史导入文件列结构可能不同，两种形态都兼容。
            code_values = (
                inst.index.astype(str)
                if "code" not in inst.columns
                else inst["code"].astype(str)
            )
            known = {str(c).strip() for c in code_values.dropna()}
            known.update(load_delisted_codes())
            # 快照内标的肯定保留；快照外标的只剔除「代码形态可判定」的指数，
            # 未知代码保留（可能是未维护进 instrument 快照的退市/历史标的），
            # 避免默认股票池重新引入幸存者偏差。
            filtered = [c for c in codes if c in known or not _is_index_like(c)]
            if filtered:
                return filtered
    except Exception as e:
        logger.debug(f"按 instrument 快照过滤股票池失败，保留全部缓存代码: {e}")

    # instrument 快照缺失：仅按代码形态剔除明确指数，其余全部保留
    return [c for c in codes if not _is_index_like(c)]


# ── 退市 / 历史代码清单 ─────────────────────────────────────
#
# QMT 的「沪深A股」板块只含当前在册成分，退市股从不会进入批量下载，
# 全市场研究链路（因子 IC / 回测）因此存在系统性幸存者偏差。
# 本清单让研究员手工维护「退市/历史代码」，批量下载时自动并入，
# 使退市股历史行情进入缓存与后续研究。QMT 对多数退市代码仍保留历史 K 线。

DELISTED_FILE = settings.cache_dir / "delisted_codes.json"


def load_delisted_codes() -> list[str]:
    """读取本地维护的「退市/历史代码清单」（JSON: {"codes": [...], "updated_at": ...}）"""
    if not DELISTED_FILE.exists():
        return []
    try:
        data = json.loads(DELISTED_FILE.read_text("utf-8"))
        return sorted({str(c).strip() for c in data.get("codes", []) if str(c).strip()})
    except Exception as e:
        logger.warning(f"读取退市代码清单失败 {DELISTED_FILE}: {e}")
        return []


def save_delisted_codes(codes: list[str]) -> list[str]:
    """保存「退市/历史代码清单」，返回归一化后的代码列表"""
    cleaned = sorted({str(c).strip() for c in codes if str(c).strip()})
    import time as _time

    DELISTED_FILE.parent.mkdir(parents=True, exist_ok=True)
    DELISTED_FILE.write_text(
        json.dumps(
            {"codes": cleaned, "updated_at": _time.strftime("%Y-%m-%d %H:%M:%S")},
            ensure_ascii=False,
            indent=2,
        ),
        "utf-8",
    )
    logger.info(f"退市/历史代码清单已保存：{len(cleaned)} 只")
    return cleaned


def merge_delisted_codes(codes: list[str]) -> list[str]:
    """把「退市/历史代码清单」并入待下载列表（去重保序）"""
    seen = set(codes)
    merged = list(codes)
    for c in load_delisted_codes():
        if c not in seen:
            merged.append(c)
            seen.add(c)
    return merged


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


def build_return_panel(close: pd.DataFrame) -> pd.DataFrame:
    """基于最近可用收盘价前向填充的日收益面板（index=日期, columns=股票）

    原始 `close.pct_change()` 在停牌/数据缺口处产生 NaN，若直接 fillna(0)，
    复牌/恢复交易日的跳空涨跌（停牌期间积累的信息）会被整段丢弃，
    回测与 IC 会系统性低估波动与损失。先用最近可用收盘价前向填充再算收益：
    停牌期间收益为 0（持仓冻结，正确），复牌日计入跳空（真实 P&L）。
    """
    return close.ffill().pct_change().fillna(0.0)


def build_cross_section_mask(
    panels: dict,
    min_list_days: int = 20,
    exclude_st: bool = True,
) -> pd.DataFrame | None:
    """构建每日「可交易」掩码（True=可交易），供因子 IC/分层截面过滤。

    规则组合（任一为 False 即排除）:
      - 停牌: 成交量=0 / 缺数据（逐日判定）
      - ST: 逐日 as-of 状态（instrument 快照从快照日起生效并前向填充；
            早于首次快照的日期无 ST 信息 → 不排除，避免把「现在的 ST」套到历史截面）
      - 次新股: 逐日判定（T 距上市日 < min_list_days 的截面剔除，
            而非按面板末日一刀切；早于上市日的日期天然缺数据，无需处理）

    Returns:
        DataFrame(index=date, columns=code)，无可判定信息时返回 None
    """
    close = panels.get("close")
    if close is None or close.empty:
        return None
    mask = pd.DataFrame(True, index=close.index, columns=close.columns, dtype=bool)

    # 停牌（成交量>0 才可交易）
    volume = panels.get("volume")
    if volume is not None and not volume.empty:
        vol = volume.reindex(index=close.index, columns=close.columns).fillna(0.0)
        mask = mask & (vol > 0)

    if exclude_st:
        try:
            from backend.services import reference_data

            st_status = reference_data.build_st_status(close.index, close.columns)
            if st_status is not None:
                mask = mask & ~st_status
        except Exception:
            pass

    if min_list_days > 0:
        try:
            from backend.services import reference_data

            inst = reference_data.load_instrument_frame()
            if inst is not None and "list_date" in inst.columns:
                lds = {
                    c: pd.to_datetime(str(v)).date()
                    for c, v in inst["list_date"].dropna().items()
                    if c in mask.columns
                }
                if lds:
                    cols = list(lds.keys())
                    day_arr = close.index.values.astype("datetime64[D]")[:, None]
                    ld_arr = np.array(
                        [np.datetime64(lds[c]) for c in cols], dtype="datetime64[D]"
                    )[None, :]
                    since_days = (day_arr - ld_arr).astype("int64")
                    newborn = pd.DataFrame(
                        since_days < min_list_days, index=close.index, columns=cols
                    )
                    # 补齐全列（无上市日信息的股票不参与次新判定，保持可交易）
                    newborn = newborn.reindex(
                        index=close.index, columns=mask.columns, fill_value=False
                    )
                    mask = mask & ~newborn
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


def dividend_events(
    period: str = "1d",
    codes: list[str] | None = None,
    days: int = 90,
    limit: int = 50,
) -> list[dict]:
    """从缓存 adjust_factor 检测除权除息事件

    除权事件 = adjust_factor 相邻交易日跳变（后复权因子锚定上市日，
    事件当日 factor 发生变化）。返回 [{code, date, factor_ratio, }] 按日期倒序。

    factor_ratio = 当日 factor / 前一日 factor（>1 表示后复权放大，
    如 1.5 对应 10 送 5 / 拆股等事件）。
    """
    all_codes = codes or list_cached_codes(period)
    events: list[dict] = []
    for code in all_codes:
        df = _cache.get(code, period)
        if df is None or df.empty or "adjust_factor" not in df.columns:
            continue
        try:
            f = df["adjust_factor"].astype(float)
            ratio = f / f.shift(1)
            idx = ratio[(ratio.abs() - 1.0).abs() > 1e-9].dropna()
        except Exception:
            continue
        for ts, r in idx.items():
            events.append(
                {
                    "code": code,
                    "date": str(pd.Timestamp(ts).date()),
                    "factor_ratio": round(float(r), 6),
                }
            )
    events.sort(key=lambda e: e["date"], reverse=True)
    if days:
        cutoff = pd.Timestamp(datetime.now().astimezone().date()) - pd.Timedelta(days=days)
        events = [e for e in events if pd.Timestamp(e["date"]) >= cutoff]
    return events[:limit]


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

    industry_map = reference_data.load_industry_map(
        as_of=str(close.index[0])[:10] if len(close.index) else ""
    )
    if not industry_map:
        assumptions.append("无行业分类快照，行业中性化不可用")
    else:
        snap_dates = reference_data.industry_snapshot_dates()
        if len(snap_dates) <= 1:
            assumptions.append(
                "行业分类仅有单一快照"
                + (f"（{snap_dates[0]}）" if snap_dates else "")
                + "，整段区间按静态分类处理，历史行业变动未反映（PIT 需积累多期快照）"
            )

    return {
        "tradable_mask": tradable,
        "up_limit": up_limit,
        "down_limit": down_limit,
        "market_cap": market_cap,
        "industry_map": industry_map,
        "assumptions": assumptions,
    }
