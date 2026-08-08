"""事件研究服务 — CAR/BHAR 事件窗口统计（event study）

通用口径（与 factor_research / backtest_analysis 一致，无前视）：
- 收益面板 r[T] = T-1 → T 日收益；
- 事件日为 T0，事件窗口 [T0+w1, T0+w2] 的异常收益 = 个股收益 - 基准收益
  （基准默认当日全市场截面均值，或调用方传入指数/基准序列）；
- CAR = 窗口内异常收益逐日累加；BHAR = Π(1+r_i) - Π(1+r_m)；
- 统计量：平均 CAR/BHAR 序列、窗口期末 t 值（横截面标准误）、正值占比、
  事件日历重叠（同一股票 3 日内多个事件自动合并，避免重复计数）。

内置事件源（全部来自本地 QMT 缓存，不新增数据源）：
  limit_up   一字涨停（high==low 且收盘触及涨停近似价）
  limit_down 一字跌停
  dividend   除权除息（adjust_factor 跳变）
  volume_spike 放量（成交量 > k× 前 20 日均量）
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from loguru import logger

# 同一股票事件间隔小于该天数视为同一事件（避免连板事件重复计数）
DEFAULT_MERGE_GAP = 3


def _detect_limit_events(
    close: pd.DataFrame,
    high: pd.DataFrame,
    low: pd.DataFrame,
    up_limit: pd.DataFrame,
    down_limit: pd.DataFrame,
    event: str = "limit_up",
) -> pd.DataFrame:
    """一字板事件：high==low 且收盘触及涨跌停近似价"""
    events: list[dict] = []
    one_line = (high - low).abs() < 1e-9
    for date in close.index:
        row = close.loc[date]
        up = up_limit.loc[date] if date in up_limit.index else pd.Series(dtype=float)
        dn = down_limit.loc[date] if date in down_limit.index else pd.Series(dtype=float)
        hit_up = one_line.loc[date] & (row >= up - 0.005) & up.notna()
        hit_dn = one_line.loc[date] & (row <= dn + 0.005) & dn.notna()
        target = hit_up if event == "limit_up" else hit_dn
        for code in target[target].index:
            events.append({"date": date, "code": code})
    if not events:
        return pd.DataFrame(columns=["date", "code"])
    df = pd.DataFrame(events)
    df["date"] = pd.to_datetime(df["date"])
    return df


def _detect_volume_spike(
    close: pd.DataFrame,
    volume: pd.DataFrame | None,
    k: float = 3.0,
) -> pd.DataFrame:
    """放量事件：当日量 > k× 前 20 日均量（不含当日）"""
    if volume is None:
        return pd.DataFrame(columns=["date", "code"])
    adv = volume.rolling(20, min_periods=5).mean().shift(1)
    hit = (volume > k * adv) & adv.notna()
    events = []
    for date in hit.index:
        for code in hit.columns[hit.loc[date].fillna(False).values]:
            events.append({"date": date, "code": code})
    if not events:
        return pd.DataFrame(columns=["date", "code"])
    df = pd.DataFrame(events)
    df["date"] = pd.to_datetime(df["date"])
    return df


def _merge_duplicate_events(events: pd.DataFrame, gap: int = DEFAULT_MERGE_GAP) -> pd.DataFrame:
    """同一股票窗口内相邻事件合并（取首个事件日），防止连板/连续事件重复计数"""
    if events.empty:
        return events
    out: list[dict] = []
    for code, g in events.sort_values("date").groupby("code"):
        keep: list = []
        last = None
        for _, row in g.iterrows():
            if last is None or (row["date"] - last).days > gap:
                keep.append(row)
                last = row["date"]
        out.extend(keep)
    return pd.DataFrame(out).reset_index(drop=True) if out else events.iloc[0:0]


def event_study_analysis(
    returns: pd.DataFrame,
    events: pd.DataFrame,
    window_before: int = 10,
    window_after: int = 10,
    market_returns: pd.Series | None = None,
    min_events: int = 5,
    merge_gap: int = DEFAULT_MERGE_GAP,
) -> dict:
    """事件研究主函数

    Args:
        returns: 日收益面板 DataFrame(index=date, columns=code)
        events: DataFrame [date, code]（date 为 pd.Timestamp 或可解析字符串）
        window_before / window_after: 事件前/后窗口天数（正数，如 10/10 =
            相对日 [-10, +10]，事件日=0，含事件日）
        market_returns: 基准日收益 Series；None 时用当日全市场截面均值
        min_events: 有效事件数下限，不足时给出提示（统计不可靠）

    Returns:
        {ok, n_events, window, car: {rel_day: {mean, t, positive_ratio}},
         bhar_mean, car_end_t, positive_ratio_end, per_event: [...],
         note}
    """
    if returns.empty:
        return {"ok": False, "note": "无收益面板，无法做事件研究", "n_events": 0}
    ev = events.copy()
    ev["date"] = pd.to_datetime(ev["date"])
    ev = ev[ev["code"].isin(returns.columns)]
    if ev.empty:
        return {"ok": False, "note": "事件与收益面板无交集（检查股票池/区间）", "n_events": 0}
    if merge_gap > 0:
        ev = _merge_duplicate_events(ev, merge_gap)
    n_events = len(ev)
    if n_events < min_events:
        return {
            "ok": False,
            "n_events": n_events,
            "note": f"有效事件仅 {n_events} 个（< {min_events}），统计不可靠",
        }

    idx = returns.index
    pos = {d: i for i, d in enumerate(idx)}
    if market_returns is None:
        market = returns.mean(axis=1)
    else:
        market = market_returns.reindex(idx).fillna(returns.mean(axis=1))

    # 窗口语义：window_before/window_after 为正的天数（事件前/后），
    # rel_days = 相对事件日的偏移（事件日=0）。
    rel_days = list(range(-window_before, window_after + 1))
    car_curves: dict[int, list[float]] = {d: [] for d in rel_days}
    per_event: list[dict] = []

    for _, row in ev.iterrows():
        code, date = row["code"], row["date"]
        if code not in returns.columns or date not in pos:
            continue
        i0 = pos[date]
        r = returns[code]
        series: dict[int, float] = {}
        for d in rel_days:
            j = i0 + d
            if 0 <= j < len(idx):
                series[d] = r.iloc[j]
        if len(series) < 2:
            continue
        # 异常收益 = 个股 - 基准；BHAR = Π(1+r_i)/Π(1+r_m) - 1
        # 注意：窗口在面板边界被截断时（事件靠近区间头部/尾部），
        # series 只含窗口内实际存在的相对日——cum 下标必须与「实际存在的
        # 相对日序列」对齐，而非枚举全部 rel_days（旧实现会对不齐且越界）
        present = [d for d in rel_days if d in series]
        r_arr = np.array([series[d] for d in present])
        m_arr = np.array([market.loc[idx[i0 + d]] for d in present])
        ab = np.nan_to_num(r_arr) - np.nan_to_num(m_arr)
        cum = np.cumsum(ab)
        for k, d in enumerate(present):
            car_curves[d].append(float(cum[k]))
        bhar = float(np.prod(1 + np.nan_to_num(r_arr)) / np.prod(1 + np.nan_to_num(m_arr)) - 1)
        per_event.append({"code": code, "date": str(date.date()), "bhar": bhar})

    car_out: dict[str, dict] = {}
    for d in rel_days:
        vals = car_curves[d]
        if not vals:
            continue
        v = np.array(vals)
        mean = float(v.mean())
        sd = float(v.std(ddof=1)) if len(v) > 1 else 0.0
        t = mean / (sd / np.sqrt(len(v))) if sd > 0 else 0.0
        car_out[str(d)] = {
            "mean": round(mean, 6),
            "t": round(t, 3),
            "positive_ratio": round(float((v > 0).mean()), 4),
            "n": int(len(v)),
        }

    if not per_event:
        return {"ok": False, "n_events": 0, "note": "窗口内无可用的完整收益序列"}

    bhar_vals = np.array([e["bhar"] for e in per_event])
    end_key = str(window_after)
    end = car_out.get(end_key)
    return {
        "ok": True,
        "n_events": int(len(per_event)),
        "window": [window_before, window_after],
        "car": car_out,
        "bhar_mean": round(float(bhar_vals.mean()), 6),
        "bhar_t": round(
            float(bhar_vals.mean() / (bhar_vals.std(ddof=1) / np.sqrt(len(bhar_vals))))
            if bhar_vals.std(ddof=1) > 0 and len(bhar_vals) > 1
            else 0.0,
            3,
        ),
        "bhar_positive_ratio": round(float((bhar_vals > 0).mean()), 4),
        "car_end_t": end["t"] if end else 0.0,
        "positive_ratio_end": end["positive_ratio"] if end else 0.0,
        "note": (
            f"基准={'全市场截面均值' if market_returns is None else '调用方基准'}；"
            "CAR 为事件窗口异常收益累计（事件日=0，含当日）；同股票事件间隔 "
            f"{merge_gap} 日内自动合并；事件日价格行为已含在收益序列中，无前视"
        ),
    }


def build_event_frame(
    event_type: str,
    close: pd.DataFrame,
    volume: pd.DataFrame | None = None,
    high: pd.DataFrame | None = None,
    low: pd.DataFrame | None = None,
    up_limit: pd.DataFrame | None = None,
    down_limit: pd.DataFrame | None = None,
    dividend_events: list[dict] | None = None,
    manual_events: list[dict] | None = None,
    volume_k: float = 3.0,
) -> pd.DataFrame:
    """按事件类型构造 [date, code] 事件表（内置事件源 + 手工事件合并）"""
    frames: list[pd.DataFrame] = []
    if event_type == "limit_up" and up_limit is not None and high is not None and low is not None:
        frames.append(_detect_limit_events(close, high, low, up_limit, down_limit, "limit_up"))
    elif event_type == "limit_down" and down_limit is not None and high is not None and low is not None:
        frames.append(_detect_limit_events(close, high, low, up_limit, down_limit, "limit_down"))
    elif event_type == "volume_spike":
        frames.append(_detect_volume_spike(close, volume, volume_k))
    elif event_type == "dividend":
        if dividend_events:
            frames.append(
                pd.DataFrame(
                    [{"date": pd.to_datetime(e["date"]), "code": e["code"]} for e in dividend_events]
                )
            )
    if manual_events:
        frames.append(
            pd.DataFrame(
                [{"date": pd.to_datetime(e["date"]), "code": e["code"]} for e in manual_events]
            )
        )
    if not frames:
        return pd.DataFrame(columns=["date", "code"])
    out = pd.concat(frames, ignore_index=True)
    return out.drop_duplicates(["date", "code"]).reset_index(drop=True)
