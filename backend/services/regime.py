"""市场环境 / 风格轮动服务 — 研究员判断市场状态的第一步

数据来源：本地缓存指数日线（QMT 下载，如 000300.SH / 000905.SH / 000852.SH /
399006.SZ / 000688.SH）。无缓存时返回明确的结构化提示，不伪造数据。

指标口径（全部基于已实现收益，无前视）：
- 趋势：MA20 / MA60 多空排列 + 20 日动量
- 波动：HV20（对数收益滚动年化）
- 量能：5 日均额 / 60 日均额
- 状态判定：趋势 + 动量 + 波动联合（牛/震荡偏多/震荡/震荡偏空/熊）
- 风格轮动：小盘(中证1000)/大盘(沪深300)、成长(创业板)/价值代理(沪深300)
  的 20 日滚动比价（相对强弱）
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd

from backend.services import market_data

# 宽基配置：代码 → 展示名 → 风格标签
_BROAD_INDICES: list[dict] = [
    {"code": "000300.SH", "name": "沪深300", "style": "大盘"},
    {"code": "000905.SH", "name": "中证500", "style": "中盘"},
    {"code": "000852.SH", "name": "中证1000", "style": "小盘"},
    {"code": "399006.SZ", "name": "创业板指", "style": "成长"},
    {"code": "000688.SH", "name": "科创50", "style": "成长"},
]

# 结果缓存（TTL 15 分钟，数据未变时避免重复计算）
_cache: dict = {"ts": 0.0, "data_date": "", "payload": {}}
_TTL = 15 * 60


def _trend_state(close: pd.Series) -> dict:
    """单指数趋势状态：MA 排列 + 动量 + 波动"""
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()
    mom20 = float(close.iloc[-1] / close.iloc[-21] - 1) if len(close) > 21 else 0.0
    log_ret = np.log(close / close.shift(1))
    hv20 = float(log_ret.rolling(20).std().iloc[-1] * np.sqrt(250))
    price, m20, m60 = float(close.iloc[-1]), float(ma20.iloc[-1]), float(ma60.iloc[-1])
    up_align = price > m20 > m60
    down_align = price < m20 < m60

    if up_align and mom20 > 0.02:
        state = "牛"
    elif down_align and mom20 < -0.02:
        state = "熊"
    elif (price > m20) ^ (m20 > m60) or up_align:
        state = "震荡偏多"
    elif down_align:
        state = "震荡偏空"
    else:
        state = "震荡"

    return {
        "ma20": round(m20, 2),
        "ma60": round(m60, 2),
        "mom20": round(mom20, 4),
        "hv20": round(hv20, 4) if not pd.isna(hv20) else 0.0,
        "price": round(price, 2),
        "state": state,
    }


def _rolling_relative_strength(a: pd.Series, b: pd.Series, window: int = 20) -> pd.Series:
    """A 相对 B 的 20 日滚动相对强弱（A 收益 - B 收益）"""
    ra, rb = a.pct_change(), b.pct_change()
    common = ra.index.intersection(rb.index)
    spread = (ra.reindex(common) - rb.reindex(common)).dropna()
    return spread.rolling(window, min_periods=10).sum()


def market_regime() -> dict:
    """市场环境总览（内存缓存 15 分钟）"""
    now = time.time()
    if _cache["payload"] and now - _cache["ts"] < _TTL:
        return _cache["payload"]

    panels: dict[str, pd.DataFrame] = {}
    missing: list[str] = []
    for item in _BROAD_INDICES:
        df = market_data._cache.get(item["code"], "1d")
        if df is None or df.empty or "close" not in df.columns or len(df) < 60:
            missing.append(item["code"])
            continue
        try:
            df = market_data._apply_adjust(df, item["code"], "qfq")
        except ValueError:
            df = df.copy()
        close = df["close"].astype(float).dropna()
        close.index = pd.to_datetime(close.index).normalize()
        panels[item["code"]] = close

    if not panels:
        payload = {
            "ok": False,
            "message": "本地无指数日线缓存 — 请先在「数据中心」按指数代码下载行情"
            "（如 000300.SH / 000905.SH / 000852.SH / 399006.SZ / 000688.SH）",
            "missing": _BROAD_INDICES,
            "indices": [],
            "style_rotation": [],
            "market_state": {},
        }
        _cache.update({"ts": now, "data_date": "", "payload": payload})
        return payload

    # 各宽基趋势状态
    indices = []
    for item in _BROAD_INDICES:
        if item["code"] not in panels:
            continue
        state = _trend_state(panels[item["code"]])
        state.update({"code": item["code"], "name": item["name"], "style": item["style"]})
        state["mom60"] = round(
            float(panels[item["code"]].iloc[-1] / panels[item["code"]].iloc[-61] - 1), 4
        ) if len(panels[item["code"]]) > 61 else 0.0
        indices.append(state)

    # 风格轮动（需沪深300 + 中证1000 / 创业板）
    style_rotation = []
    pairs = [
        ("小盘 vs 大盘", "000852.SH", "000300.SH"),
        ("成长 vs 大盘", "399006.SZ", "000300.SH"),
        ("中盘 vs 大盘", "000905.SH", "000300.SH"),
    ]
    for label, a_code, b_code in pairs:
        if a_code in panels and b_code in panels:
            rs = _rolling_relative_strength(panels[a_code], panels[b_code])
            if not rs.empty:
                style_rotation.append(
                    {
                        "label": label,
                        "strength": round(float(rs.iloc[-1]), 4),
                        "trend": "↑" if float(rs.iloc[-1]) > 0 else "↓",
                        "series": {
                            "x": [str(d.date()) for d in rs.index[-120:]],
                            "y": [round(float(v), 4) for v in rs.values[-120:]],
                        },
                    }
                )

    # 市场综合状态（多数指数状态投票）
    from collections import Counter

    votes = Counter(i["state"] for i in indices)
    market_state = {
        "label": votes.most_common(1)[0][0] if votes else "震荡",
        "votes": dict(votes),
        "hv20_avg": round(
            float(np.mean([i["hv20"] for i in indices])) if indices else 0.0, 4
        ),
        "n_bull": sum(1 for i in indices if i["state"] in ("牛", "震荡偏多")),
        "n_bear": sum(1 for i in indices if i["state"] in ("熊", "震荡偏空")),
    }

    data_date = str(
        min(p.index[-1] for p in panels.values())
    )[:10]
    payload = {
        "ok": True,
        "data_date": data_date,
        "indices": indices,
        "style_rotation": style_rotation,
        "market_state": market_state,
        "missing": [m for m in missing],
    }
    _cache.update({"ts": now, "data_date": data_date, "payload": payload})
    return payload


def regime_freshness() -> dict:
    """指数缓存时效（供仪表盘显示数据日期与陈旧状态）"""
    latest = {}
    for item in _BROAD_INDICES:
        df = market_data._cache.get(item["code"], "1d")
        if df is None or df.empty:
            continue
        latest[item["code"]] = str(df.index[-1])[:10]
    return {"latest": latest, "ok": bool(latest)}
