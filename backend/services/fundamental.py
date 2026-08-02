"""财务数据服务 — 公告日(point-in-time)基本面，防前视

从 QMT 拉取财务数据（Income/Balance/Pershareindex 等），以【公告日 m_anntime】
为可用时点构建截面面板，保证研究日 T 只能用 T 之前【已披露】的财报，杜绝前视。

存储: data/cache/fundamental/{code}.parquet, 每表一行含:
    timetag(报告截止日) / anntime(公告日) / 及各指标列

本文件所有内存逻辑不依赖 QMT，可用合成数据测试。
"""

from __future__ import annotations

import pandas as pd
from loguru import logger

from backend.config import settings

FUND_DIR = settings.cache_dir / "fundamental"

# 统一收入/占位数比较常用的指标；持久化时只用以下字段（前端也按此展示）
FUND_FIELDS = [
    "eps",            # 每股收益(基本)
    "roe",            # 净资产收益率
    "pb",             # 市净率(每股净资产可换算)
    "net_profit",
    "revenue",
    "total_assets",
    "total_liab",
]


def snapshot_status() -> dict:
    """本地基本面快照状态（供两端标注 fund_* 可用性）。不读大文件，只扫目录。"""
    d = FUND_DIR
    codes = []
    if d.is_dir():
        codes = [p.stem.replace("_", ".") for p in d.glob("*.parquet")]
    return {"rows": len(codes), "codes": codes, "ready": bool(codes)}


def _ensure_dir():
    FUND_DIR.mkdir(parents=True, exist_ok=True)


def snapshot_fundamental(qmt, codes: list[str]) -> int:
    """批量拉取并落盘；QMT 需连接。返回记录数。"""
    from backend.data.qmt_client import QMTClient
    if not (isinstance(qmt, QMTClient) and qmt.connected):
        logger.warning("财务数据快照：QMT 未连接，跳过")
        return 0
    _ensure_dir()
    records = 0
    tables = ["Pershareindex", "Income", "Balance", "CostCapital"]
    for code in codes:
        try:
            data = qmt.get_financial(
                [code], tables=tables, report_type="announce_time"
            )
            frames = _code_frames(data.get(code))
            if not frames:
                continue
            merged = _merge_frames(frames)
            if merged.empty:
                continue
            safe = code.replace(".", "_")
            merged.to_parquet(FUND_DIR / f"{safe}.parquet", index=False)
            records += len(merged)
        except Exception as e:
            logger.warning(f"财务数据快照失败 {code}: {e}")
    return records


def _code_frames(code_tables) -> dict[str, pd.DataFrame]:
    out = {}
    for table, df in (code_tables or {}).items():
        if isinstance(df, pd.DataFrame) and not df.empty:
            out[table] = df
    return out


def _merge_frames(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """把多张财务表按公告日合并成一张宽表：columns=字段, row 为公告日, 升序

    以 anntime 为连接键、按表优先级（Pershareindex > Income > Balance > CostCapital）
    合并各表呈现的指标，避免 `pd.concat(axis=1)` 造成的重复列（各表都带 anntime，
    eps 又同时出现在 Pershareindex/Income）导致无法落盘。
    """
    _PRIORITY = ["Pershareindex", "Income", "Balance", "CostCapital", "Cashflow"]
    order = {p: i for i, p in enumerate(_PRIORITY)}
    parts: list[pd.DataFrame] = []
    for table, df in frames.items():
        ann = _find_col(df, ["m_anntime", "announce_time", "mAnnounce", "anntime"])
        if ann is None:
            continue
        keep = set()
        for c in df.columns:
            if str(c).lower() in {f.lower() for f in FUND_FIELDS}:
                keep.add(c)
        if not keep:
            continue
        ren = {}
        if ann != "anntime":
            ren[ann] = "anntime"
        sub = df[list(keep | {ann})].copy().rename(columns=ren)
        sub["_table"] = order.get(table, 99)
        parts.append(sub)
    if not parts:
        return pd.DataFrame()

    rows = sorted(parts, key=lambda s: int(s.iloc[0]["_table"]) if len(s) else 0)
    if not rows:
        return pd.DataFrame()
    merged = rows[0].drop(columns="_table")
    for r in rows[1:]:
        r = r.drop(columns="_table")
        merged = pd.merge(
            merged, r, on="anntime", how="outer", suffixes=("", "_dup")
        )
        merged = merged[[c for c in merged.columns if not c.endswith("_dup")]]
    if "anntime" not in merged.columns:
        return pd.DataFrame()
    merged = merged.sort_values("anntime")
    return merged


def _find_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    lower = {str(c).lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in lower:
            return lower[cand.lower()]
    return None


def load_code_fundamental(code: str) -> pd.DataFrame | None:
    """读取单只股票基本面（含 anntime），无则 None"""
    safe = code.replace(".", "_")
    path = FUND_DIR / f"{safe}.parquet"
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception as e:
        logger.warning(f"读取基本面 {path} 失败: {e}")
        return None


def build_fundamental_panels(
    codes: list[str], trade_dates: pd.DatetimeIndex, fund_dir=None
) -> dict[str, pd.DataFrame]:
    """按公告日 ffill 构建各指标的点位面板 {field: DataFrame(index=date, columns=code)}

    任一 trading_day 上，某只股票取「公告日 <= 该日」的最近一期值；无则 NA。

    Args:
        codes: 股票代码
        trade_dates: 研究交易日期序列
        fund_dir: 覆盖数据目录（测试用）
    """
    panels: dict[str, dict] = {f: {} for f in FUND_FIELDS}
    d = FUND_DIR if fund_dir is None else fund_dir

    for code in codes:
        safe = code.replace(".", "_")
        path = d / f"{safe}.parquet"
        if not path.exists():
            continue
        try:
            df = pd.read_parquet(path)
        except Exception:
            continue
        ann = None
        for c in df.columns:
            if str(c).lower() in ("anntime", "m_anntime", "ann", "annt", "nt"):
                ann = c
                break
        if ann is None:
            continue
        col = df[ann]
        if pd.api.types.is_numeric_dtype(col):
            # 数值：假设毫秒 epoch（QMT 时间戳）；< 10^12 视为秒
            unit = "ms" if (col.dropna().abs() > 1e12).any() else "s"
            ts = pd.to_datetime(col, unit=unit, errors="coerce")
        else:
            ts = pd.to_datetime(col, errors="coerce")
        for f in FUND_FIELDS:
            if f in df.columns and ts.notna().any():
                s = pd.Series(df[f].values, index=ts.values)
                s = s[ts.notna().values]
                # 按公告日升序、取每个公告日最近值 → 落到 trade_dates 上 ffill
                s = s[~s.index.duplicated(keep="last")]
                s = s.sort_index()
                s = s.reindex(trade_dates, method="ffill").astype(float, errors="ignore")
                panels[f][code] = s.reindex(trade_dates)

    out = {}
    for f, d1 in panels.items():
        if d1:
            frame = pd.DataFrame(d1).sort_index()
            out[f] = frame
    return out


def inject_fundamental_namespace(panels: dict) -> dict:
    """给 limit obj express via fundamental 面板注入到命名空间（如 fund.pe ...）

    Args:
        s: 现有求值命名空间
    Returns:
        新增的 {fund_xxx: panel} 或 {fund: {}}。
    """
    return {f"fund_{f}": p for f, p in panels.items()}