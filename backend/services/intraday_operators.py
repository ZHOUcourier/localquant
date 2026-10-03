"""日内高频聚合算子库 — 分钟面板 → 日频因子面板

设计语义（与 docs 分钟级设计一致）：
- 分钟级字段 m_open/m_high/m_low/m_close/m_volume/m_amount：
  DataFrame(index=datetime, columns=code)；
- ID_* 聚合算子把分钟维度按自然日折叠成 DataFrame(index=date, columns=code)，
  输出与现有日频因子面板同构，下游 IC/分层/回测全链路直接复用；
- M_* 序列算子作用于分钟维度（按日分组滚动，不跨日混算）；
- 现成高频因子函数（TAIL_RET/RV/JUMP_DAY/...）无参调用，闭包内取面板。

清洗约定：调用方先过 intraday_cleaner（竞价 bar 已剔除，meta 含一字/半日标记）。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ── 工具 ─────────────────────────────────────────────────────────


def _date_key(idx: pd.DatetimeIndex) -> pd.Index:
    """datetime index → 自然日 index（同长度，用于 groupby）"""
    return pd.DatetimeIndex(idx.normalize().unique())


def _intraday_pct_change(panel: pd.DataFrame) -> pd.DataFrame:
    """日内收益：逐日 pct_change，**日首根置 NaN**（隔夜跳空不属于日内波动）"""
    rets = panel.pct_change()
    norm = np.asarray(pd.DatetimeIndex(panel.index).normalize())
    is_new_day = np.concatenate([[True], norm[1:] != norm[:-1]])
    rets.loc[is_new_day] = np.nan
    return rets


def _collapse(series: pd.DataFrame, agg) -> pd.DataFrame:
    """分钟面板 (dt × code) → 日频面板 (date × code)：按列分组到自然日聚合"""
    out: dict[str, pd.Series] = {}
    for code in series.columns:
        s = series[code].dropna()
        if s.empty:
            continue
        out[code] = s.groupby(s.index.normalize()).agg(agg)
    if not out:
        return pd.DataFrame()
    return pd.DataFrame(out).sort_index()


def _within_time(series: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    """时段切片：保留时刻在 [start, end) 内的分钟 bar（start/end 如 '09:30'）"""
    times = series.index.strftime("%H:%M")
    mask = (times >= start) & (times < end)
    return series.loc[mask]


# ── ID_* 聚合算子（分钟 → 日） ─────────────────────────────────────


def ID_LAST(series: pd.DataFrame, n_bars: int = 0) -> pd.DataFrame:
    """每日最后一根 bar 的值；n_bars>0 时为最后 n 根均值（更稳健的收盘估计）"""
    if n_bars and n_bars > 0:
        out = {}
        for code in series.columns:
            s = series[code].dropna()
            if s.empty:
                continue
            t = s.groupby(s.index.normalize()).tail(n_bars)
            out[code] = t.groupby(t.index.normalize()).mean()
        return pd.DataFrame(out).sort_index()
    return _collapse(series, "last")


def ID_FIRST(series: pd.DataFrame, n_bars: int = 0) -> pd.DataFrame:
    """每日第一根 bar 的值；n_bars>0 时为前 n 根均值"""
    if n_bars and n_bars > 0:
        out = {}
        for code in series.columns:
            s = series[code].dropna()
            if s.empty:
                continue
            t = s.groupby(s.index.normalize()).head(n_bars)
            out[code] = t.groupby(t.index.normalize()).mean()
        return pd.DataFrame(out).sort_index()
    return _collapse(series, "first")


def ID_SUM(series: pd.DataFrame) -> pd.DataFrame:
    return _collapse(series, "sum")


def ID_MEAN(series: pd.DataFrame) -> pd.DataFrame:
    return _collapse(series, "mean")


def ID_MAX(series: pd.DataFrame) -> pd.DataFrame:
    return _collapse(series, "max")


def ID_MIN(series: pd.DataFrame) -> pd.DataFrame:
    return _collapse(series, "min")


def ID_STD(series: pd.DataFrame) -> pd.DataFrame:
    return _collapse(series, "std")


def ID_MEDIAN(series: pd.DataFrame) -> pd.DataFrame:
    return _collapse(series, "median")


def ID_QUANTILE(series: pd.DataFrame, q: float = 0.5) -> pd.DataFrame:
    out = {}
    for code in series.columns:
        s = series[code].dropna()
        if s.empty:
            continue
        out[code] = s.groupby(s.index.normalize()).quantile(q)
    return pd.DataFrame(out).sort_index()


def ID_COUNT(series: pd.DataFrame) -> pd.DataFrame:
    return _collapse(series, "count")


def ID_SLICE(series: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    """时段切片（返回分钟级）：ID_SLICE(m_close, '14:00', '15:00') 后再套 ID_*"""
    return _within_time(series, start, end)


# ── 30 分钟时段分桶（价量熵因子的地基） ─────────────────────────────

# A 股连续竞价：上午 09:30-11:30、下午 13:00-15:00，各 120 交易分钟；
# 30 分钟时段共 8 个（09:30-10:00, ..., 14:30-15:00）。
_MORNING_END_MIN = 11 * 60 + 30
_AFTERNOON_START_MIN = 13 * 60
_DAY_TRADING_MIN = 240


def _trading_minute_elapsed(index: pd.DatetimeIndex) -> np.ndarray:
    """bar 时刻 → 当日已交易分钟数（以 bar 末端计）。

    09:31 → 1，10:00 → 30，11:30 → 120，13:01 → 121，15:00 → 240。
    竞价 bar（09:30 及更早）与盘中异常时刻返回 0（调用方据此剔除）。
    """
    minutes = index.hour * 60 + index.minute
    elapsed = np.where(
        minutes <= _MORNING_END_MIN,
        minutes - 9 * 60 - 30,
        _DAY_TRADING_MIN // 2 + (minutes - _AFTERNOON_START_MIN),
    )
    return np.where((minutes > 9 * 60 + 30) & (minutes <= 15 * 60), elapsed, 0)


def _slot_index(index: pd.DatetimeIndex, bucket_minutes: int = 30) -> np.ndarray:
    """bar 时刻 → 日内时段序号（0 起，30 分钟桶对应 0..7）；竞价/异常时刻为 -1"""
    elapsed = _trading_minute_elapsed(index)
    return np.where(elapsed > 0, (elapsed - 1) // bucket_minutes, -1)


def ID_PV_ENTROPY(price: pd.DataFrame, volume: pd.DataFrame, bucket_minutes: int = 30) -> pd.DataFrame:
    """日内价量结构熵（分钟面板 → 日频面板）

    按文档口径（QuantZone feat_single_amt_ratio_entropy_30m）：
    1. 将分钟数据按日内 30 分钟时段分桶（钟表时段语义，停牌/无成交时段自然留空）；
    2. 每时段取代表价（时段末收盘）与成交量合计；
    3. price_ratio_b = close_b / Σclose，volume_ratio_b = vol_b / Σvol；
    4. p_b = price_ratio_b × volume_ratio_b，日内再归一化为概率分布；
    5. 熵 = -Σ p_b·ln(p_b)，p_b=0 项记 0；均匀分布达上界 ln(8)≈2.079。

    清洗约定：price 缺失、volume<=0、竞价 bar（时段序号 -1）不参与计算；
    全日无有效成交 → NaN。熵越低 = 成交越集中于少数时段。

    bucket_minutes：时段宽度（分钟），默认 30；60m 等粗于 30m 的周期下每根
    bar 自成一个更宽的时段（熵上界相应变低，跨周期不可比）。
    """
    if bucket_minutes <= 0:
        raise ValueError("bucket_minutes 必须为正")
    if price is None or volume is None or price.empty:
        return pd.DataFrame()
    out: dict[str, pd.Series] = {}
    for code in price.columns:
        s_price = price[code].dropna()
        if s_price.empty:
            continue
        s_vol = volume[code].reindex(s_price.index).fillna(0.0).astype(float)
        day = pd.DatetimeIndex(s_price.index).normalize()
        slot = _slot_index(pd.DatetimeIndex(s_price.index), bucket_minutes)
        all_days = pd.Index(day.unique())  # 价格面板出现过的交易日（保留 NaN 行）
        valid = (slot >= 0) & (s_vol.to_numpy() > 0)
        if not valid.any():
            out[code] = pd.Series(np.nan, index=all_days)
            continue
        sp = s_price[valid]
        sv = s_vol[valid]
        key_day = day[valid]
        key_slot = slot[valid]
        g = pd.Series(sp.to_numpy()).groupby([key_day, key_slot])
        slot_close = g.last()
        slot_vol = pd.Series(sv.to_numpy()).groupby([key_day, key_slot]).sum()
        day_close_sum = slot_close.groupby(level=0).transform("sum")
        day_vol_sum = slot_vol.groupby(level=0).transform("sum")
        p = (slot_close / day_close_sum.replace(0, np.nan)) * (
            slot_vol / day_vol_sum.replace(0, np.nan)
        )
        p = p / p.groupby(level=0).transform("sum")
        pos = p[p > 0]
        entropy = -(pos * np.log(pos)).groupby(level=0).sum()
        out[code] = entropy.reindex(all_days)
    if not out:
        return pd.DataFrame()
    return pd.DataFrame(out).sort_index()


# ── M_* 序列算子（分钟维度，按日分组不跨日） ────────────────────────


def _apply_daily_rolling(series: pd.DataFrame, window: int, func) -> pd.DataFrame:
    out: dict[str, pd.Series] = {}
    for code in series.columns:
        s = series[code].dropna()
        if s.empty:
            continue
        g = s.groupby(s.index.normalize()).rolling(window, min_periods=1).apply(
            func, raw=False
        )
        g = g.droplevel(0)
        out[code] = g
    return pd.DataFrame(out).sort_index()


def M_DELAY(series: pd.DataFrame, n: int = 1) -> pd.DataFrame:
    """分钟维度前 n 根（按日分组，日首根为 NaN）"""
    out = {}
    for code in series.columns:
        s = series[code]
        g = s.groupby(s.index.normalize()).shift(n)
        out[code] = g
    return pd.DataFrame(out).sort_index()


def M_MA(series: pd.DataFrame, n: int = 12) -> pd.DataFrame:
    return _apply_daily_rolling(series, n, lambda x: x.mean())


def M_SUM(series: pd.DataFrame, n: int = 12) -> pd.DataFrame:
    return _apply_daily_rolling(series, n, lambda x: x.sum())


def M_STD(series: pd.DataFrame, n: int = 12) -> pd.DataFrame:
    return _apply_daily_rolling(series, n, lambda x: x.std())


def M_CUMSUM(series: pd.DataFrame) -> pd.DataFrame:
    out = {}
    for code in series.columns:
        s = series[code]
        out[code] = s.groupby(s.index.normalize()).cumsum()
    return pd.DataFrame(out).sort_index()


# ── 现成高频因子（无参，闭包取面板；返回日频面板） ──────────────────


def TAIL_RET(panels: dict, n_bars: int = 12) -> pd.DataFrame:
    """尾盘动量：当日最后 n 根 bar 的累计收益 close[-1] / close[-1-n] - 1"""
    close = panels["close"]
    close_last = ID_LAST(close, 0)
    close_minus_n = ID_LAST(M_DELAY(close, n_bars), 0)  # 第 (-1-n) 根 bar 收盘
    return close_last / close_minus_n - 1.0


def OPEN_RET(panels: dict, n_bars: int = 6) -> pd.DataFrame:
    """开盘反转：当日前 n 根 bar 的累计收益 close[n-1] / 昨收 - 1"""
    close = panels["close"]
    prev_close = ID_LAST(close, 0).shift(1)
    close_n = ID_FIRST(M_DELAY(close, -(n_bars - 1)), 0)  # 第 n 根 bar 收盘
    return close_n / prev_close - 1.0


def RV(panels: dict, n_bars: int = 48) -> pd.DataFrame:
    """已实现波动率：日内分钟收益平方和（日频）；n_bars=48 对应全日 5m

    日内收益逐日计算并屏蔽日首根（隔夜跳空不计入日内波动）。
    """
    close = panels["close"]
    rets = _intraday_pct_change(close)
    return ID_SUM(rets**2)


def JUMP_DAY(panels: dict) -> pd.DataFrame:
    """跳跃占比：RV / BV（双幂变差）；>1 表示当日存在跳跃性波动"""
    close = panels["close"]
    rets = _intraday_pct_change(close)
    rv = ID_SUM(rets**2)
    r1 = M_DELAY(rets, 1)
    bv = ID_SUM(rets.abs() * r1.abs()) * (np.pi / 2)
    return rv.div(bv.replace(0, np.nan))


def AMIHUD5(panels: dict) -> pd.DataFrame:
    """日内非流动性：每根 bar |收益|/成交额 的日均值 × 1e9（Amihud 分钟口径）"""
    close = panels["close"]
    amount = panels.get("amount")
    if amount is None:
        return pd.DataFrame()
    rets = _intraday_pct_change(close).abs()
    illiq = rets.div(amount.replace(0, np.nan))
    return ID_MEAN(illiq) * 1e9


def VWAP_DEV(panels: dict) -> pd.DataFrame:
    """价格偏离日内 VWAP：收盘 / 全日 VWAP - 1（尾盘拉抬/砸盘信号）"""
    close = panels["close"]
    amount = panels.get("amount")
    volume = panels.get("volume")
    if amount is None or volume is None:
        return pd.DataFrame()
    day_vwap = ID_SUM(amount) / ID_SUM(volume).replace(0, np.nan)
    return ID_LAST(close, 0).div(day_vwap.replace(0, np.nan)) - 1.0


def VOLUME_CLOCK(panels: dict) -> pd.DataFrame:
    """成交量时钟（日内量能集中度）：Σ(份额²)，1/n 为均匀分布，越接近 1 越集中"""
    volume = panels.get("volume")
    if volume is None:
        return pd.DataFrame()
    shares = volume.div(volume.groupby(volume.index.normalize()).transform("sum").replace(0, np.nan))
    return ID_SUM(shares**2)


def AUC_VOL_RATIO(panels: dict, meta: dict, lookback: int = 5) -> pd.DataFrame:
    """竞价量比：当日竞价量 / 前 lookback 日竞价量均值（开盘情绪强度）"""
    codes = list(panels["close"].columns)
    out: dict[str, pd.Series] = {}
    for code in codes:
        m = meta.get(code)
        if m is None or "auc_vol" not in m.columns:
            continue
        auc = m["auc_vol"].astype(float)
        base = auc.rolling(lookback, min_periods=lookback).mean().shift(1)
        out[code] = auc / base.replace(0, np.nan)
    return pd.DataFrame(out).sort_index()


def LIMIT_UP_TIME(panels: dict, meta: dict) -> pd.DataFrame:
    """封板时间：一字涨停日的首次封板时刻（10.5 = 10:30），非一字日 NaN

    注意：仅能识别「一字板」封板时刻（high==low）；盘中打开过的一字板无法
    从分钟 OHLC 还原，此为近似（作为 assumption 明示）。
    """
    close = panels["close"]
    codes = list(close.columns)
    out: dict[str, pd.Series] = {}
    for code in codes:
        m = meta.get(code)
        if m is None or "one_line" not in m.columns:
            continue
        one = m["one_line"].fillna(False)
        if not one.any():
            continue
        s = close[code]
        times = s.index.strftime("%H:%M")
        rec: dict = {}
        for day, is_one in one.items():
            if not bool(is_one):
                continue
            day_bars = s[s.index.normalize() == day]
            if day_bars.empty:
                continue
            first_t = times[np.where((s.index.normalize() == day).to_numpy())[0][0]]
            hh, mm = int(first_t[:2]), int(first_t[3:5])
            rec[day] = hh + mm / 60.0
        out[code] = pd.Series(rec)
    return pd.DataFrame(out).sort_index()


def OVERNIGHT_RET(panels: dict) -> pd.DataFrame:
    """隔夜收益：今开 / 昨收 - 1"""
    close = panels["close"]
    open_ = panels["open"]
    prev_close = ID_LAST(close, 0).shift(1)
    day_open = ID_FIRST(open_, 0)
    return day_open / prev_close - 1.0


def INTRADAY_RET(panels: dict) -> pd.DataFrame:
    """日内收益：今收 / 今开 - 1"""
    close = panels["close"]
    open_ = panels["open"]
    return ID_LAST(close, 0) / ID_FIRST(open_, 0) - 1.0


def PV_ENTROPY_30M(panels: dict, bucket_minutes: int = 30) -> pd.DataFrame:
    """日内价量结构熵（现成因子包装）：ID_PV_ENTROPY(m_close, m_volume, 30)

    熵越低 = 成交越集中于少数 30 分钟时段（突发冲击/短线资金拥挤）。
    对照 QuantZone feat_single_amt_ratio_entropy_30m。
    """
    return ID_PV_ENTROPY(panels.get("close"), panels.get("volume"), bucket_minutes)


def build_intraday_namespace(panels: dict, meta: dict | None = None) -> dict:
    """分钟公式求值命名空间：m_* 字段 + ID_*/M_* 算子 + 现成高频因子

    meta 可为空（现成因子中依赖 meta 的 AUC_VOL_RATIO/LIMIT_UP_TIME 会返回空面板）。
    """
    meta = meta or {}
    ns: dict = {
        "np": np,
        "pd": pd,
        # 分钟字段（大小写均可）
        "m_open": panels.get("open"),
        "M_OPEN": panels.get("open"),
        "m_high": panels.get("high"),
        "M_HIGH": panels.get("high"),
        "m_low": panels.get("low"),
        "M_LOW": panels.get("low"),
        "m_close": panels.get("close"),
        "M_CLOSE": panels.get("close"),
        "m_volume": panels.get("volume"),
        "M_VOLUME": panels.get("volume"),
        "m_amount": panels.get("amount"),
        "M_AMOUNT": panels.get("amount"),
        "m_returns": (
            _intraday_pct_change(panels["close"])
            if panels.get("close") is not None
            else None
        ),
    }
    ops = {
        "ID_LAST": ID_LAST,
        "ID_FIRST": ID_FIRST,
        "ID_SUM": ID_SUM,
        "ID_MEAN": ID_MEAN,
        "ID_MAX": ID_MAX,
        "ID_MIN": ID_MIN,
        "ID_STD": ID_STD,
        "ID_MEDIAN": ID_MEDIAN,
        "ID_QUANTILE": ID_QUANTILE,
        "ID_COUNT": ID_COUNT,
        "ID_SLICE": ID_SLICE,
        "ID_PV_ENTROPY": ID_PV_ENTROPY,
        "M_DELAY": M_DELAY,
        "M_MA": M_MA,
        "M_SUM": M_SUM,
        "M_STD": M_STD,
        "M_CUMSUM": M_CUMSUM,
    }
    ns.update(ops)
    ns.update({k.lower(): v for k, v in ops.items()})
    # 合并日频算子（RANK/ZSCORE/MA/DELAY...），供折叠后的日频面板直接套用
    try:
        from backend.services.factor_operators import get_daily_operators

        daily = get_daily_operators()
        ns.update(daily)
        ns.update({k.lower(): v for k, v in daily.items()})
    except Exception:
        pass
    # 现成高频因子（闭包取面板/meta）
    factors = {
        "TAIL_RET": lambda n_bars=12: TAIL_RET(panels, int(n_bars)),
        "OPEN_RET": lambda n_bars=6: OPEN_RET(panels, int(n_bars)),
        "RV": lambda n_bars=48: RV(panels, int(n_bars)),
        "JUMP_DAY": lambda: JUMP_DAY(panels),
        "AMIHUD5": lambda: AMIHUD5(panels),
        "VWAP_DEV": lambda: VWAP_DEV(panels),
        "VOLUME_CLOCK": lambda: VOLUME_CLOCK(panels),
        "AUC_VOL_RATIO": lambda lookback=5: AUC_VOL_RATIO(panels, meta, int(lookback)),
        "LIMIT_UP_TIME": lambda: LIMIT_UP_TIME(panels, meta),
        "OVERNIGHT_RET": lambda: OVERNIGHT_RET(panels),
        "INTRADAY_RET": lambda: INTRADAY_RET(panels),
        "PV_ENTROPY_30M": lambda bucket_minutes=30: PV_ENTROPY_30M(panels, int(bucket_minutes)),
    }
    ns.update(factors)
    ns.update({k.lower(): v for k, v in factors.items()})
    return ns
