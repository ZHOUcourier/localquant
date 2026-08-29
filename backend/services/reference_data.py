"""参考数据快照服务 — 指数成分/行业分类/股本/合约详情

存储结构（data/cache/reference/ 下的 Parquet 快照，随批量下载自动更新）：
  index_constituents.parquet: [date, index_name, code]      指数/板块成分 as-of 快照
  industry.parquet:           [date, code, industry]        申万一级行业快照
  capital.parquet:            [code, date, float_shares, total_shares]  股本变动记录
  instrument.parquet:         [date, code, name, list_date, up_stop, down_stop]

快照只能在 QMT 连接时采集（Windows）；加载函数不依赖 QMT，任何环境可用。
历史指数成分靠快照逐日积累，早于首次快照的区间仍是当前成分（幸存者偏差），
调用方需通过 assumptions 明示该局限。
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
from loguru import logger

from backend.config import settings

REFERENCE_DIR = settings.cache_dir / "reference"

_CONSTITUENTS_FILE = "index_constituents.parquet"
_INDUSTRY_FILE = "industry.parquet"
_CAPITAL_FILE = "capital.parquet"
_INSTRUMENT_FILE = "instrument.parquet"
_UNIVERSE_FILE = "universe.parquet"

# 可融资融券标的池候选板块名（QMT 各版本命名可能不同，取并集）
_MARGIN_SECTORS = ["融资融券标的", "两融标的", "融资融券"]
# 沪深股通（北向可投资）标的池候选板块名
_HSGT_SECTORS = ["沪股通", "深股通", "沪深股通"]


def _path(name: str):
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    return REFERENCE_DIR / name


def _read(name: str) -> pd.DataFrame | None:
    p = REFERENCE_DIR / name
    if not p.exists():
        return None
    try:
        return pd.read_parquet(p)
    except Exception as e:
        logger.warning(f"读取参考数据 {name} 失败: {e}")
        return None


def _append_dedup(name: str, new_rows: pd.DataFrame, keys: list[str]):
    """追加行并按 keys 去重（保留最新），落盘"""
    if new_rows.empty:
        return
    existing = _read(name)
    combined = (
        pd.concat([existing, new_rows], ignore_index=True)
        if existing is not None
        else new_rows
    )
    combined = combined.drop_duplicates(subset=keys, keep="last")
    combined.to_parquet(_path(name), index=False)


def import_reference_snapshot(kind: str, snapshot_date: str, df: pd.DataFrame) -> int:
    """导入历史参考数据快照（as-of 指定日期），追加去重落盘

    用途：QMT 只能给「当前」成分/行业/名称/两融池，历史 as-of 状态（如
    2015 年沪深300 成分、历史上曾 ST 的名称）无法从行情源回溯。研究员可从
    其他已核验来源整理历史快照并在此导入，使 as-of 研究链路（指数成分重建、
    ST 逐日过滤、两融池逐日掩码）能覆盖历史区间。

    Args:
        kind: constituents（列 index_name, code）| industry（code, industry）|
              instrument（code, name[, list_date]）| margin（code[, pool]）
        snapshot_date: 该快照对应的 as-of 日期（YYYY-MM-DD）
        df: 快照内容（含列头）

    Returns:
        落盘行数
    """
    ds = str(pd.Timestamp(snapshot_date).date())
    if kind == "constituents":
        rows = df[["index_name", "code"]].copy()
        rows["date"] = ds
        _append_dedup(_CONSTITUENTS_FILE, rows, ["date", "index_name", "code"])
    elif kind == "industry":
        rows = df[["code", "industry"]].copy()
        rows["date"] = ds
        _append_dedup(_INDUSTRY_FILE, rows, ["date", "code"])
    elif kind == "instrument":
        rows = df[["code", "name"]].copy()
        for col in ("list_date", "up_stop", "down_stop"):
            if col in df.columns:
                rows[col] = df[col]
        rows["date"] = ds
        _append_dedup(_INSTRUMENT_FILE, rows, ["date", "code"])
    elif kind == "margin":
        rows = df[["code"]].copy()
        rows["pool"] = df["pool"] if "pool" in df.columns else "margin"
        rows["date"] = ds
        _append_dedup(_UNIVERSE_FILE, rows, ["date", "pool", "code"])
    else:
        raise ValueError(
            f"未知快照类型 {kind}（可选 constituents/industry/instrument/margin）"
        )
    return len(rows)


# ── 快照采集（需要 QMT 连接，仅 Windows） ─────────────────────────


def snapshot_index_constituents(qmt, sector: str) -> int:
    """记录板块/指数成分的 as-of 快照，返回成分股数"""
    stocks = qmt.get_sector_stocks(sector)
    if not stocks:
        return 0
    today = datetime.now().astimezone().date().isoformat()
    rows = pd.DataFrame({"date": today, "index_name": sector, "code": stocks})
    _append_dedup(_CONSTITUENTS_FILE, rows, ["date", "index_name", "code"])
    return len(stocks)


# 每日调度固定积累的主要宽基/风格指数（QMT 不同版本板块名可能不同，取候选并集去重）
MAJOR_INDEX_SECTORS = [
    "000300.SH",
    "000905.SH",
    "000852.SH",
    "000688.SH",
    "399006.SZ",
    "沪深300",
    "中证500",
    "中证1000",
    "科创50",
    "创业板指",
]


def snapshot_major_indices(qmt) -> int:
    """快照主要宽基/风格指数成分（候选名逐项尝试，成功项去重统计）。

    QMT 板块列表在不同券商版本中命名不一致；这里对常见代码与中文名做
    候选尝试，以便从「今天」开始自动积累指数成分 as-of 历史，避免以后
    重建历史指数成分时只能依赖手工导入。
    """
    total = 0
    seen: set[str] = set()
    for sector in MAJOR_INDEX_SECTORS:
        try:
            stocks = qmt.get_sector_stocks(sector)
        except Exception:
            continue
        if not stocks:
            continue
        # 防止同一指数同时命中代码与中文名时重复计数
        key = tuple(sorted(stocks))
        if key in seen:
            continue
        seen.add(key)
        total += snapshot_index_constituents(qmt, sector)
    return total


def snapshot_industry(qmt) -> int:
    """记录申万一级行业分类快照（SW1 开头板块），返回覆盖股票数"""
    sectors = qmt.get_sector_list()
    sw1 = [s for s in sectors if s.startswith("SW1")]
    if not sw1:
        return 0
    today = datetime.now().astimezone().date().isoformat()
    records: list[dict] = []
    for sector in sw1:
        industry = sector[3:] or sector  # "SW1食品饮料" → "食品饮料"
        for code in qmt.get_sector_stocks(sector):
            records.append({"date": today, "code": code, "industry": industry})
    if not records:
        return 0
    rows = pd.DataFrame(records)
    _append_dedup(_INDUSTRY_FILE, rows, ["date", "code"])
    return len(records)


# Capital 表中股本字段的候选名（xtquant 各版本命名不一致）
_FLOAT_SHARE_FIELDS = ["circulating_capital", "float_capital", "floatCapital"]
_TOTAL_SHARE_FIELDS = ["total_capital", "totalCapital"]


def _pick_field(df: pd.DataFrame, candidates: list[str]) -> str | None:
    lower = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in lower:
            return lower[cand.lower()]
    return None


def snapshot_capital(qmt, codes: list[str]) -> int:
    """从财务 Capital 表记录股本变动，返回记录数"""
    if not codes:
        return 0
    data = qmt.get_financial(codes, tables=["Capital"])
    records: list[dict] = []
    for code, tables in data.items():
        df = tables.get("Capital") if isinstance(tables, dict) else tables
        if not isinstance(df, pd.DataFrame) or df.empty:
            continue
        float_col = _pick_field(df, _FLOAT_SHARE_FIELDS)
        total_col = _pick_field(df, _TOTAL_SHARE_FIELDS)
        # 点-in-time：用公告日 m_anntime 作为股本变动生效点（而非报告期 m_timetag），
        # 避免研究日 T 提前用到尚未披露的新股本数量
        time_col = _pick_field(df, ["m_anntime", "m_timetag", "timetag"])
        for _, row in df.iterrows():
            ts = row[time_col] if time_col else None
            dt = _parse_date(ts)
            if dt is None:
                continue
            records.append(
                {
                    "code": code,
                    "date": dt,
                    "float_shares": float(row[float_col])
                    if float_col
                    else float("nan"),
                    "total_shares": float(row[total_col])
                    if total_col
                    else float("nan"),
                }
            )
    if not records:
        return 0
    rows = pd.DataFrame(records)
    _append_dedup(_CAPITAL_FILE, rows, ["code", "date"])
    return len(records)


def snapshot_instrument(qmt, codes: list[str]) -> int:
    """记录合约详情快照（名称/上市日/涨跌停价），返回记录数"""
    if not codes:
        return 0
    details = qmt.get_instrument_detail(codes)
    today = datetime.now().astimezone().date().isoformat()
    records: list[dict] = []
    for code, d in details.items():
        if not isinstance(d, dict):
            continue
        records.append(
            {
                "date": today,
                "code": code,
                "name": str(d.get("InstrumentName", "")),
                "list_date": _parse_date(d.get("OpenDate")) or "",
                "up_stop": float(d.get("UpStopPrice") or 0.0),
                "down_stop": float(d.get("DownStopPrice") or 0.0),
            }
        )
    if not records:
        return 0
    rows = pd.DataFrame(records)
    _append_dedup(_INSTRUMENT_FILE, rows, ["date", "code"])
    return len(records)


# ── 标的池快照（可融券 / 北向）────────────────────────────────


def snapshot_universe_pools(qmt) -> dict[str, int]:
    """记录标的池 as-of 快照（两融标的=可融券池，沪深股通=北向池），返回各池成分数

    用途：两融/北向标的池仅作为市场结构参考；本系统只做普通股票多头，
    北向池内因子研究。快照为 as-of 形式，早于首次快照的区间用最新池（幸存者偏差，
    调用方通过 assumptions 明示）。
    """
    out: dict[str, int] = {}
    sectors = qmt.get_sector_list()
    names = set(sectors)
    pools: dict[str, list[str]] = {"margin": [], "hsgt": []}
    for sector in _MARGIN_SECTORS:
        if sector in names:
            pools["margin"].extend(qmt.get_sector_stocks(sector))
    for sector in _HSGT_SECTORS:
        if sector in names:
            pools["hsgt"].extend(qmt.get_sector_stocks(sector))
    today = datetime.now().astimezone().date().isoformat()
    for pool, codes in pools.items():
        uniq = sorted(set(codes))
        if not uniq:
            continue
        rows = pd.DataFrame({"date": today, "pool": pool, "code": uniq})
        _append_dedup(_UNIVERSE_FILE, rows, ["date", "pool", "code"])
        out[pool] = len(uniq)
    return out


def load_universe_pool(pool: str, as_of: str = "") -> set[str]:
    """标的池最新（或不晚于 as_of）成分代码集合；无快照返回空集"""
    df = _read(_UNIVERSE_FILE)
    if df is None or df.empty:
        return set()
    df = df[df["pool"] == pool]
    if df.empty:
        return set()
    if as_of:
        df = df[df["date"] <= as_of]
        if df.empty:
            return set()
    latest = df.sort_values("date").drop_duplicates("code", keep="last")
    return set(latest["code"])


def load_universe_pool_mask(
    pool: str, dates
) -> pd.DataFrame | None:
    """标的池逐日 as-of 成分掩码：True=池内（index=日期, columns=代码）

    基于 universe 快照（date, pool, code）：从快照日起生效并前向填充；
    早于首次快照的日期 → NaN（调用方决定回退策略，不得向后借用未来快照）。
    """
    df = _read(_UNIVERSE_FILE)
    if df is None or df.empty:
        return None
    df = df[df["pool"] == pool]
    if df.empty:
        return None
    snap_dates = pd.to_datetime(df["date"]).dt.normalize()
    pivot = df.pivot_table(
        index=snap_dates, columns="code", values="pool", aggfunc="count"
    )
    pivot = pivot > 0
    target = pd.DatetimeIndex(pd.to_datetime(dates)).normalize()
    all_dates = pd.DatetimeIndex(sorted(set(pivot.index) | set(target)))
    aligned = pivot.reindex(all_dates).ffill().reindex(target)
    return aligned

def _parse_date(value) -> str | None:
    """把 '20240101' / '2024-01-01' / datetime / epoch(ms|s) 解析为 'YYYY-MM-DD'，失败返回 None"""
    if value is None or value == "" or value == 0:
        return None
    try:
        # 数值：优先按 YYYYMMDD 紧凑日期，其次按 epoch 秒/毫秒
        if isinstance(value, (int, float, np.integer, np.floating)):
            if pd.isna(value) or value == 0:
                return None
            v = float(value)
            if 19000101 <= v <= 21001231 and abs(v - round(v)) < 1e-9:
                s = str(int(v))
                return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
            unit = "ms" if v >= 1e11 else "s"
            return pd.to_datetime(v, unit=unit).date().isoformat()
        s = str(value)
        if len(s) == 8 and s.isdigit():
            return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
        # 字符串型 epoch（如 '1600000000000.0'）
        if s.replace(".", "", 1).isdigit() and len(s) >= 10:
            v = float(s)
            unit = "ms" if v >= 1e11 else "s"
            return pd.to_datetime(v, unit=unit).date().isoformat()
        return pd.to_datetime(s).date().isoformat()
    except Exception:
        return None


# ── 加载（不依赖 QMT，任何环境可用） ─────────────────────────────


def reference_status() -> dict:
    """参考数据现状概览，供数据管理页展示"""
    status: dict[str, dict] = {}
    for key, name, date_col in [
        ("index_constituents", _CONSTITUENTS_FILE, "date"),
        ("industry", _INDUSTRY_FILE, "date"),
        ("capital", _CAPITAL_FILE, "date"),
        ("instrument", _INSTRUMENT_FILE, "date"),
        ("universe_pools", _UNIVERSE_FILE, "date"),
    ]:
        df = _read(name)
        if df is None or df.empty:
            status[key] = {"rows": 0, "latest": None}
        else:
            status[key] = {"rows": len(df), "latest": str(df[date_col].max())}
    return status


def load_industry_map(as_of: str = "") -> dict[str, str]:
    """返回 {code: industry}，取不晚于 as_of 的最新快照（as_of 为空取最新）"""
    df = _read(_INDUSTRY_FILE)
    if df is None or df.empty:
        return {}
    if as_of:
        as_of_norm = _parse_date(as_of) or str(as_of)
        df = df[df["date"] <= as_of_norm]
        if df.empty:
            # as_of 早于任何行业快照：宁可返回空（调用方退化为不按行业中性化），
            # 也不回退到 as_of 之后的「未来」行业造成前视
            return {}
    latest = df.sort_values("date").drop_duplicates("code", keep="last")
    return dict(zip(latest["code"], latest["industry"]))


def load_index_membership(index_name: str) -> pd.DataFrame | None:
    """指数成分 as-of 掩码：DataFrame(index=快照日, columns=code, bool)

    使用时按交易日 ffill 即得逐日成员；早于首次快照的日期无记录。
    """
    df = _read(_CONSTITUENTS_FILE)
    if df is None or df.empty:
        return None
    df = df[df["index_name"] == index_name]
    if df.empty:
        return None
    df = df.assign(member=True)
    mask = df.pivot_table(
        index="date", columns="code", values="member", aggfunc="any"
    ).fillna(False)
    mask.index = pd.to_datetime(mask.index)
    return mask.sort_index()


def load_membership_mask(index_name: str, dates) -> pd.DataFrame | None:
    """指数成分逐日 as-of 掩码：True=当日为该指数成分（index=日期, columns=代码）

    从成分快照日起生效并前向填充；早于首次快照的日期为 NaN（不得向后借用未来
    快照，调用方用 assumptions 明示）。无快照返回 None。
    """
    df = _read(_CONSTITUENTS_FILE)
    if df is None or df.empty:
        return None
    df = df[df["index_name"] == index_name]
    if df.empty:
        return None
    snap_dates = pd.to_datetime(df["date"]).dt.normalize()
    pivot = df.pivot_table(
        index=snap_dates, columns="code", values="index_name", aggfunc="count"
    )
    pivot = pivot > 0
    target = pd.DatetimeIndex(pd.to_datetime(dates)).normalize()
    all_dates = pd.DatetimeIndex(sorted(set(pivot.index) | set(target)))
    aligned = pivot.reindex(all_dates).ffill().reindex(target)
    return aligned


def load_industry_panel(dates, codes=None) -> pd.DataFrame | None:
    """逐日 as-of 行业面板：DataFrame(index=日期, columns=代码, values=行业名)

    对每个日期取不晚于当日的最新行业快照并前向填充；早于首次快照的日期为 NaN
    （不得向后借用未来快照，调用方用 assumptions 明示静态区间）。无快照返回 None。
    """
    df = _read(_INDUSTRY_FILE)
    if df is None or df.empty:
        return None
    snap_dates = pd.to_datetime(df["date"]).dt.normalize()
    pivot = df.pivot_table(
        index=snap_dates, columns="code", values="industry", aggfunc="last"
    ).sort_index()
    if codes is not None:
        pivot = pivot.reindex(columns=codes)
    target = pd.DatetimeIndex(pd.to_datetime(dates)).normalize()
    all_dates = pd.DatetimeIndex(sorted(set(pivot.index) | set(target)))
    aligned = pivot.reindex(all_dates).ffill().reindex(target)
    return aligned


def industry_snapshot_dates() -> list[str]:
    """已有行业快照的日期（升序），供调用方判断 as-of 覆盖范围"""
    df = _read(_INDUSTRY_FILE)
    if df is None or df.empty:
        return []
    return sorted(pd.to_datetime(df["date"]).dt.date.astype(str).unique().tolist())


def list_snapshot_indices() -> list[str]:
    """已有成分快照的板块/指数名列表"""
    df = _read(_CONSTITUENTS_FILE)
    if df is None or df.empty:
        return []
    return sorted(df["index_name"].unique().tolist())


def build_market_cap_panel(close_panel: pd.DataFrame) -> pd.DataFrame | None:
    """流通市值面板 = 流通股本（按变动日 ffill）× 收盘价；无股本数据返回 None"""
    cap = _read(_CAPITAL_FILE)
    if cap is None or cap.empty:
        return None
    cap = cap.dropna(subset=["float_shares"])
    cap = cap[cap["float_shares"] > 0]
    if cap.empty:
        return None
    shares = cap.pivot_table(
        index="date", columns="code", values="float_shares", aggfunc="last"
    )
    shares.index = pd.to_datetime(shares.index)
    shares = shares.sort_index()
    common = close_panel.columns.intersection(shares.columns)
    if common.empty:
        return None
    # 对齐到行情日期并前向填充（股本在变动日之间保持不变）
    aligned = (
        shares[common]
        .reindex(shares.index.union(close_panel.index))
        .ffill()
        .reindex(close_panel.index)
    )
    return aligned * close_panel[common]


def build_turnover_panel(volume_panel, close_panel) -> pd.DataFrame | None:
    """换手率面板 = 成交股数 / 流通股本（按变动日 ffill）；无股本/成交数据返回 None"""
    cap = _read(_CAPITAL_FILE)
    if cap is None or cap.empty:
        return None
    if volume_panel is None or close_panel is None:
        return None
    free_shares = cap.dropna(subset=["float_shares"])
    free_shares = free_shares[free_shares["float_shares"] > 0]
    if free_shares.empty:
        return None
    shares = free_shares.pivot_table(
        index="date", columns="code", values="float_shares", aggfunc="last"
    )
    shares.index = pd.to_datetime(shares.index)
    shares = shares.sort_index()
    common = volume_panel.columns.intersection(shares.columns)
    if common.empty:
        return None
    aligned = (
        shares[common]
        .reindex(shares.index.union(volume_panel.index))
        .ffill()
        .reindex(volume_panel.index)
    )
    # 成交额/价格 → 股数不可得；直接用成交量(股) / 流通股本
    return volume_panel[common].div(aligned.replace(0, np.inf)) * 100.0


def load_instrument_frame() -> pd.DataFrame | None:
    """最新合约详情：DataFrame(index=code, columns=[name, list_date, up_stop, down_stop])

    仅取实际存在的列（导入的历史快照可能缺 up_stop/down_stop）。
    """
    df = _read(_INSTRUMENT_FILE)
    if df is None or df.empty:
        return None
    latest = df.sort_values("date").drop_duplicates("code", keep="last")
    keep = [c for c in ("name", "list_date", "up_stop", "down_stop") if c in latest.columns]
    return latest.set_index("code")[keep]


def build_st_status(dates, codes) -> pd.DataFrame | None:
    """逐日 as-of ST 状态：True=ST（index=日期, columns=代码）

    基于 instrument 快照（date, code, name）：ST 状态从「含 ST 名称的快照日」起
    生效并前向填充——今天才快照到的 *ST 名称不会倒灌到 2015 年截面（避免用未来
    信息）；早于首次快照的日期无 ST 信息 → False（不排除，调用方用 assumptions
    明示该局限）。代码从未出现于快照 → False。
    """
    df = _read(_INSTRUMENT_FILE)
    if df is None or df.empty or "name" not in df.columns:
        return None
    snap = df[["date", "code", "name"]].copy()
    snap["is_st"] = snap["name"].fillna("").str.upper().str.contains("ST")
    snap_dates = pd.to_datetime(snap["date"]).dt.normalize()
    pivot = snap.pivot_table(
        index=snap_dates, columns="code", values="is_st", aggfunc="any"
    )
    if pivot.empty:
        return None
    pivot = pivot.reindex(columns=codes)
    target = pd.DatetimeIndex(pd.to_datetime(dates)).normalize()
    all_dates = pd.DatetimeIndex(sorted(set(pivot.index) | set(target)))
    aligned = pivot.reindex(all_dates).ffill().reindex(target)
    # nullable boolean 填充：避免 object dtype 隐式 downcast 警告
    return aligned.astype("boolean").fillna(False).astype(bool)


# ── 派生面板（可交易掩码 / 涨跌停近似价） ─────────────────────────


def build_tradable_mask(volume_panel: pd.DataFrame) -> pd.DataFrame:
    """可交易掩码：成交量>0 视为可交易（volume==0 或缺数据推断为停牌）"""
    return volume_panel.fillna(0.0) > 0


def limit_pct_for_code(code: str, name: str = "") -> float:
    """按板归类的涨跌停幅度近似：ST±5%、创业/科创±20%、北交所±30%、主板±10%"""
    if "ST" in name.upper():
        return 0.05
    if code.endswith(".BJ"):
        return 0.30
    prefix = code.split(".")[0][:3]
    if prefix in ("300", "301", "302", "688", "689"):
        return 0.20
    return 0.10


def build_limit_prices(
    close_panel: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """涨跌停近似价：昨收 ×(1±板块幅度)，四舍五入至分

    幅度：ST 5%（逐日 as-of 状态，instrument 快照生效日起）、创业/科创 20%、
    北交所 30%、主板 10%。历史涨跌停价 QMT 不提供，按板归类近似；
    早于首次快照的区间无 ST 状态 → 按非 ST 幅度（调用方以 assumptions 明示）。
    """
    base_pcts = pd.Series(
        {c: limit_pct_for_code(c, "") for c in close_panel.columns}
    )
    pcts = pd.DataFrame(
        np.tile(base_pcts.to_numpy(), (len(close_panel), 1)),
        index=close_panel.index,
        columns=close_panel.columns,
        dtype=float,
    )
    st_status = build_st_status(close_panel.index, close_panel.columns)
    if st_status is not None:
        pcts[st_status] = 0.05
    prev_close = close_panel.shift(1)
    up = (prev_close * (1 + pcts)).round(2)
    down = (prev_close * (1 - pcts)).round(2)
    return up, down
