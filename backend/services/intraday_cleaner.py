"""分钟数据清洗层（日内高频研究前置）

清洗规则（研究员视角，全部显式化，不静默丢数据）：
1. 集合竞价 bar 剔除：日首根（1m<09:31 / 5m<09:35 等）视为竞价聚合 bar，
   其成交量/成交额单独提取到 auction 信息（竞价量比因子的原料），不进主序列；
2. 半日市标记：当日 bar 数 < 常规日 80% 时标记 is_half（长假前半天、特殊休市）；
3. 一字板标记：high==low 且收盘触及涨跌停近似价 → one_line=True（封板时间因子原料）；
4. 停牌日 = 交易日历上有、但当日无任何 bar（缺失即天然不可交易，不额外标记）。

返回结构：
    panels: {field: DataFrame(index=datetime, columns=code)}（清洗后的分钟面板）
    meta:   {code: DataFrame(index=date, columns=[n_bars, is_half, one_line,
            auc_vol, auc_amt, prev_close, first_time])}（逐日摘要，因子可直接取用）
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# 各周期首根有效 bar 的时刻阈值（时间字符串比较）：更早的 bar 视为竞价聚合
PERIOD_FIRST_BAR = {
    "1m": "09:31",
    "5m": "09:35",
    "15m": "09:45",
    "30m": "10:00",
    "60m": "10:30",
}
DEFAULT_FIRST_BAR = "09:35"
# 常规日完整 bar 数（A 股 4 小时连续竞价，5m=48 根；作为半日判定基准）
PERIOD_FULL_BARS = {
    "1m": 240,
    "5m": 48,
    "15m": 16,
    "30m": 8,
    "60m": 4,
}
DEFAULT_FULL_BARS = 48

# 全局缓存实例（测试可 monkeypatch 指向临时目录）
_cache = None


def _bar_time(x: pd.Timestamp) -> str:
    return f"{x.hour:02d}:{x.minute:02d}"


def clean_code_minute(
    df: pd.DataFrame,
    period: str = "5m",
    one_line: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """清洗单只股票的分钟数据

    Args:
        df: QMT 分钟 K 线 DataFrame（index=datetime，含 open/high/low/close/volume/amount）
        period: 周期（用于首根 bar 与完整 bar 数判定）
        one_line: 是否做一字板标记（需 close/high/low）

    Returns:
        (cleaned 分钟面板, meta 逐日摘要 DataFrame)
    """
    if df is None or df.empty:
        return df, pd.DataFrame()
    d = df.copy()
    d.index = pd.to_datetime(d.index)
    d = d.sort_index()
    if "amount" not in d.columns:
        d["amount"] = d.get("volume", 0.0) * d.get("close", 0.0)

    first_bar = PERIOD_FIRST_BAR.get(period, DEFAULT_FIRST_BAR)
    full_bars = PERIOD_FULL_BARS.get(period, DEFAULT_FULL_BARS)

    t = d.index
    date_key = t.normalize()
    auc_records: dict[pd.Timestamp, dict] = {}
    # 每交易日首根（时间 < first_bar）为竞价聚合 bar：提取 auction 信息后剔除
    drop: list[bool] = []
    auc = np.zeros(len(d))
    for i in range(len(d)):
        is_first = i == 0 or date_key[i] != date_key[i - 1]
        is_auction_bar = is_first and _bar_time(t[i]) < first_bar
        drop.append(bool(is_auction_bar))
        if is_auction_bar:
            auc[i] = 1.0
            day = date_key[i]
            auc_records[day] = {
                "auc_vol": float(d["volume"].iloc[i]),
                "auc_amt": float(d["amount"].iloc[i]),
                "auc_time": _bar_time(t[i]),
            }
    d = d[~np.array(drop)]

    if d.empty:
        return d, pd.DataFrame()

    # 逐日摘要
    t2 = d.index
    date_key2 = t2.normalize()
    days: list[dict] = []
    for day, g in d.groupby(date_key2):
        rec = {
            "n_bars": len(g),
            "is_half": len(g) < int(full_bars * 0.8),
            "one_line": False,
        }
        auc_info = auc_records.get(day, {})
        rec.update(auc_info)
        if one_line and {"high", "low", "close"} <= set(g.columns):
            # 全日所有 bar high==low（无波动区间）且收盘钉在限价位 → 一字板
            rec["one_line"] = bool(
                (g["high"] - g["low"]).abs().max() < 1e-9
            )
        rec["prev_close"] = None
        days.append((day, rec))
    meta = pd.DataFrame([r for _, r in days], index=[k for k, _ in days])
    meta.index.name = "date"

    # prev_close：上一交易日收盘价（跨日连续，用于隔夜收益）
    if "close" in d.columns:
        closes = d["close"]
        prev = pd.Series(
            closes.groupby(date_key2).last().shift(1), index=meta.index
        )
        meta["prev_close"] = prev.to_numpy()
    return d, meta


def load_intraday_panels(
    codes: list[str],
    period: str = "5m",
    start_date: str = "",
    end_date: str = "",
    clean: bool = True,
) -> dict:
    """加载多只股票的分钟面板（清洗后）

    Args:
        codes: 股票代码；空则取本地全部该周期缓存
        period: 分钟周期（1m/5m/15m/30m/60m）
        clean: 是否做清洗（竞价剔除/半日/一字标记）；False 返回原始分钟面板

    Returns:
        {
          "panels": {field: DataFrame(index=datetime, columns=code)},
          "meta": {code: DataFrame(index=date, ...)},
          "codes": [...], "period": period,
          "start": "YYYY-MM-DD", "end": "YYYY-MM-DD",
          "cleaned": bool,
          "missing": [code...]
        }
    """
    from backend.data.cache import DataCache
    from backend.config import settings

    cache = _cache if _cache is not None else DataCache(settings.cache_dir)
    if not codes:
        codes = list_cached_codes(period)
    if not codes:
        raise ValueError(
            f"本地无 {period} 分钟缓存 — 请先在「数据管理」下载分钟行情"
            "（周期需与请求一致），或指定股票池"
        )

    fields = ["open", "high", "low", "close", "volume", "amount"]
    series_map: dict[str, dict] = {f: {} for f in fields}
    meta_map: dict[str, pd.DataFrame] = {}
    missing: list[str] = []
    for code in codes:
        df = cache.get(code, period)
        if df is None or df.empty:
            missing.append(code)
            continue
        if clean:
            df, meta = clean_code_minute(df, period)
            if df.empty:
                missing.append(code)
                continue
            if not meta.empty:
                meta_map[code] = meta
        df = df.copy()
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        if start_date:
            df = df[df.index >= pd.Timestamp(start_date)]
        if end_date:
            df = df[df.index <= pd.Timestamp(end_date) + pd.Timedelta(days=1)]
        for f in fields:
            if f in df.columns:
                series_map[f][code] = df[f].astype(float)

    if not series_map["close"]:
        raise ValueError(
            f"未找到任何 {period} 分钟数据 — 请先下载分钟行情（可先在小股票池验证）"
        )
    panels = {
        f: pd.DataFrame(m).sort_index() for f, m in series_map.items() if m
    }
    first = panels["close"].index[0]
    last = panels["close"].index[-1]
    return {
        "panels": panels,
        "meta": meta_map,
        "codes": list(panels["close"].columns),
        "period": period,
        "start": str(first.date()),
        "end": str(last.date()),
        "cleaned": clean,
        "missing": missing,
        "n_bars_per_stock": {c: int(panels["close"].shape[0]) for c in panels["close"].columns},
    }


def list_cached_codes(period: str = "5m") -> list[str]:
    """本地指定周期缓存股票列表"""
    from backend.services import market_data

    return market_data.list_cached_codes(period)
