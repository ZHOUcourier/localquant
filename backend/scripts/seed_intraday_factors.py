"""种子脚本：预置「日内高频」因子类别与分钟级因子（幂等，可重复执行）

用法: uv run python -m backend.scripts.seed_intraday_factors

因子公式为分钟语法（m_ 字段 / ID_* / M_* / 现成高频函数），求值环境与
「因子构建（分钟）」节点一致；下载 5m 分钟行情后可在因子库点「重算」
基于本地数据真实计算 IC（recalculate 自动路由分钟语法）。

描述中带「公式：」前缀，与既有预置因子（Alpha101/191）的公式提取约定一致。
"""

import asyncio
import sqlite3
from pathlib import Path

CATEGORY = {
    "category_code": "INTRADAY",
    "category_name": "日内高频",
    "color_hex": "#26A69A",
    "factor_count": 0,
}

# (factor_code, factor_name, 公式, 说明)
INTRADAY_FACTORS = [
    (
        "intraday_tail_mom_12",
        "尾盘动量(12bar)",
        "RANK(TAIL_RET(12))",
        "5m 最后 12 根 bar（1 小时）收益，尾盘动量对次日收益的预测力，A 股经典执行时点因子",
    ),
    (
        "intraday_tail_mom_30",
        "尾盘动量(30bar)",
        "RANK(TAIL_RET(30))",
        "5m 最后 30 根 bar（2.5 小时）收益，更长尾盘窗口",
    ),
    (
        "intraday_open_rev_6",
        "开盘反转(6bar)",
        "RANK(-OPEN_RET(6))",
        "开盘 30 分钟收益反转：高开冲高后回落的日内均值回归",
    ),
    (
        "intraday_rv5_rev",
        "已实现波动率反转(5m)",
        "RANK(-RV(48))",
        "5m 已实现波动率（全日 48 根 bar 收益平方和）反转：高波动日次日均值回归",
    ),
    (
        "intraday_jump_day",
        "日内跳跃占比",
        "RANK(JUMP_DAY())",
        "RV/BV 双幂变差比：>1 表示当日存在跳跃性波动（消息/流动性冲击）",
    ),
    (
        "intraday_amihud5",
        "日内非流动性(Amihud)",
        "RANK(-AMIHUD5())",
        "分钟口径 Amihud：每根 bar |收益|/成交额 的日均值，比日线口径更精细",
    ),
    (
        "intraday_vwap_dev",
        "收盘VWAP偏离",
        "RANK(VWAP_DEV())",
        "收盘价相对全日 VWAP 的偏离：尾盘拉抬（正）/砸盘（负）信号",
    ),
    (
        "intraday_vol_clock",
        "成交量时钟",
        "RANK(VOLUME_CLOCK())",
        "日内量能集中度（Herfindahl）：越接近 1 量越集中，情绪/交易型资金行为",
    ),
    (
        "intraday_auc_vol_ratio",
        "竞价量比",
        "RANK(AUC_VOL_RATIO())",
        "当日集合竞价量 / 前 5 日竞价量均值：开盘情绪强度，需分钟 meta 竞价信息",
    ),
    (
        "intraday_limit_up_time",
        "封板时间(一字)",
        "RANK(-LIMIT_UP_TIME())",
        "一字涨停封板时刻（越早越强）：A 股情绪面经典因子，仅能识别一字板（近似）",
    ),
    (
        "intraday_overnight_ret",
        "隔夜收益",
        "RANK(OVERNIGHT_RET())",
        "今开/昨收-1：A 股隔夜效应（机构调仓/情绪），与日内收益互补",
    ),
    (
        "intraday_intraday_ret",
        "日内收益",
        "RANK(INTRADAY_RET())",
        "今收/今开-1：日内收益部分（去除隔夜噪声）",
    ),
    (
        "intraday_tail_volume_share",
        "尾盘量能占比",
        "RANK(ID_SUM(ID_SLICE(m_volume, '14:30', '15:00')) / ID_SUM(m_volume))",
        "尾盘 30 分钟成交量占全日比例：尾盘资金行为强度",
    ),
    (
        "intraday_vol_am_pm_ratio",
        "上下午波动比",
        "RANK(ID_STD(ID_SLICE(m_close, '13:00', '15:00')) / ID_STD(ID_SLICE(m_close, '09:30', '11:30')))",
        "下午 vs 上午价格波动比：日内波动结构，信息时点分布",
    ),
]


def _db_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "localquant.db"


def seed() -> None:
    db_path = _db_path()
    if not db_path.exists():
        raise SystemExit(f"数据库不存在: {db_path} — 请先启动一次后端（make dev-backend）")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO preset_factor_categories "
        "(category_code, category_name, color_hex, factor_count) VALUES (?, ?, ?, ?)",
        (CATEGORY["category_code"], CATEGORY["category_name"], CATEGORY["color_hex"], CATEGORY["factor_count"]),
    )
    cur.execute(
        "SELECT id FROM preset_factor_categories WHERE category_code = ?",
        (CATEGORY["category_code"],),
    )
    cat_id = cur.fetchone()[0]

    now = asyncio.get_event_loop().time()
    del now  # created_at 走数据库默认值
    inserted = 0
    for code, name, formula, desc in INTRADAY_FACTORS:
        description = f"{desc}。公式：{formula}"
        cur.execute(
            """INSERT OR REPLACE INTO preset_factors
               (factor_code, factor_name, category_id, category_code, category_name,
                category_color_hex, description, stock_pool, is_preset)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'A', 1)""",
            (code, name, cat_id, CATEGORY["category_code"], CATEGORY["category_name"],
             CATEGORY["color_hex"], description),
        )
        inserted += 1
    cur.execute(
        "UPDATE preset_factor_categories SET factor_count = ? WHERE id = ?",
        (inserted, cat_id),
    )
    conn.commit()
    conn.close()
    print(f"✅ 日内高频类别: {inserted} 个预置因子（分钟语法，下载 5m 行情后可点「重算」）")


if __name__ == "__main__":
    seed()
