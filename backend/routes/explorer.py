"""数据探索路由 — SQL 查询 / 全市场扫描 / 横截面分析 / 异常检测

数据来源均为本地 Parquet 行情缓存（data/cache/{period}/{code}.parquet），
无缓存数据时返回明确的空结果与提示，不伪造数据。
"""

import math
import re
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import APIRouter
from pydantic import BaseModel

from backend.config import settings
from backend.services.duckdb_service import DuckDBService

router = APIRouter()

duckdb_service = DuckDBService()

_SQL_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|copy|pragma|install|load)\b",
    re.IGNORECASE,
)


def _cache_files(period: str = "1d") -> list[Path]:
    d = settings.cache_dir / period
    if not d.exists():
        return []
    return sorted(d.glob("*.parquet"))


def _file_code(path: Path) -> str:
    """000001_SZ.parquet → 000001.SZ"""
    return path.stem.replace("_", ".")


def _load_stock(path: Path) -> pd.DataFrame | None:
    try:
        df = pd.read_parquet(path)
        df.index = pd.to_datetime(df.index)
        return df
    except Exception:
        return None


def _clean_value(val):
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return None
    if isinstance(val, (pd.Timestamp,)):
        return str(val)
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        return float(val)
    return val


# ── SQL 查询 ─────────────────────────────────────────────────


class SQLQueryRequest(BaseModel):
    sql: str


@router.post("/query")
async def sql_query(body: SQLQueryRequest):
    """DuckDB SQL 查询本地 Parquet 数据（仅允许 SELECT）"""
    sql = body.sql.strip().rstrip(";")
    if not sql:
        return {"columns": [], "data": [], "row_count": 0, "error": "SQL 为空"}
    if not sql.lower().lstrip("(").startswith(("select", "with", "describe", "show")):
        return {
            "columns": [],
            "data": [],
            "row_count": 0,
            "error": "仅支持 SELECT / WITH / DESCRIBE 查询",
        }
    if _SQL_FORBIDDEN.search(sql):
        return {
            "columns": [],
            "data": [],
            "row_count": 0,
            "error": "SQL 中包含不允许的写操作关键字",
        }
    return duckdb_service.query_local(sql)


@router.get("/tables")
async def list_tables():
    """列出本地可查询的数据表（各周期的 Parquet 缓存）"""
    tables = []
    cache_dir = settings.cache_dir
    if cache_dir.exists():
        for period_dir in sorted(cache_dir.iterdir()):
            if not period_dir.is_dir():
                continue
            files = sorted(period_dir.glob("*.parquet"))
            if not files:
                continue
            # 读第一个文件获取列结构
            sample = _load_stock(files[0])
            columns = list(sample.columns) if sample is not None else []
            date_range = ""
            if sample is not None and len(sample) > 0:
                date_range = (
                    f"{sample.index.min().date()} ~ {sample.index.max().date()}"
                )
            tables.append(
                {
                    "period": period_dir.name,
                    "path": f"data/cache/{period_dir.name}/*.parquet",
                    "stock_count": len(files),
                    "columns": columns,
                    "sample_range": date_range,
                    "codes": [_file_code(f) for f in files[:200]],
                }
            )
    return {"tables": tables}


# ── 全市场扫描 ────────────────────────────────────────────────

_COND_RE = re.compile(
    r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(>=|<=|>|<|==|!=|=)\s*(-?\d+\.?\d*)\s*$"
)


class ScanRequest(BaseModel):
    date: str
    conditions: list[str] = []
    period: str = "1d"


@router.post("/scan")
async def market_scan(body: ScanRequest):
    """按日期对全部缓存股票做条件扫描（如 close > 10; volume > 1000000）"""
    files = _cache_files(body.period)
    if not files:
        return {
            "columns": [],
            "data": [],
            "row_count": 0,
            "error": "本地无行情缓存数据，请先到「数据中心」下载行情",
        }

    parsed = []
    for cond in body.conditions:
        m = _COND_RE.match(cond)
        if not m:
            return {
                "columns": [],
                "data": [],
                "row_count": 0,
                "error": f"条件格式不支持: {cond}（示例: close > 10）",
            }
        col, op, val = m.group(1), m.group(2), float(m.group(3))
        parsed.append((col, "==" if op == "=" else op, val))

    try:
        target = pd.to_datetime(body.date)
    except Exception:
        return {"columns": [], "data": [], "row_count": 0, "error": "日期格式不合法"}

    rows = []
    columns: list[str] = []
    for path in files:
        df = _load_stock(path)
        if df is None or df.empty:
            continue
        day = df[df.index.normalize() == target.normalize()]
        if day.empty:
            continue
        rec = day.iloc[-1]
        ok = True
        for col, op, val in parsed:
            if col not in rec.index:
                ok = False
                break
            v = rec[col]
            if pd.isna(v):
                ok = False
                break
            if op == ">" and not v > val:
                ok = False
            elif op == "<" and not v < val:
                ok = False
            elif op == ">=" and not v >= val:
                ok = False
            elif op == "<=" and not v <= val:
                ok = False
            elif op == "==" and not v == val:
                ok = False
            elif op == "!=" and not v != val:
                ok = False
            if not ok:
                break
        if ok:
            if not columns:
                columns = ["code"] + list(rec.index)
            rows.append([_file_code(path)] + [_clean_value(v) for v in rec.tolist()])

    return {"columns": columns, "data": rows, "row_count": len(rows)}


# ── 横截面分析 ────────────────────────────────────────────────


class CrossSectionRequest(BaseModel):
    date: str
    field: str = "close"
    period: str = "1d"


@router.post("/cross-section")
async def cross_section(body: CrossSectionRequest):
    """某日全市场指定字段的截面统计与分布直方图"""
    files = _cache_files(body.period)
    if not files:
        return {"error": "本地无行情缓存数据，请先到「数据中心」下载行情"}

    try:
        target = pd.to_datetime(body.date)
    except Exception:
        return {"error": "日期格式不合法"}

    values = []
    for path in files:
        df = _load_stock(path)
        if df is None or df.empty or body.field not in df.columns:
            continue
        day = df[df.index.normalize() == target.normalize()]
        if day.empty:
            continue
        v = day.iloc[-1][body.field]
        if not pd.isna(v):
            values.append(float(v))

    if not values:
        return {
            "error": f"该日期无 {body.field} 数据（检查日期是否为交易日、数据是否已缓存）"
        }

    s = pd.Series(values)
    stats_cols = ["count", "mean", "median", "stddev", "min", "max", "q25", "q75"]
    stats_row = [
        int(s.count()),
        float(s.mean()),
        float(s.median()),
        float(s.std()) if len(s) > 1 else 0.0,
        float(s.min()),
        float(s.max()),
        float(s.quantile(0.25)),
        float(s.quantile(0.75)),
    ]

    # 直方图（20 个分箱）
    counts, edges = np.histogram(s, bins=20)
    histogram = [
        {"bin": f"{edges[i]:.2f}", "count": int(counts[i])} for i in range(len(counts))
    ]

    return {
        "statistics": {"columns": stats_cols, "data": [stats_row], "row_count": 1},
        "histogram": histogram,
    }


# ── 异常检测 ─────────────────────────────────────────────────


class AnomalyRequest(BaseModel):
    code: str
    field: str = "close"
    window: int = 20
    threshold: float = 2.0
    period: str = "1d"


@router.post("/anomaly")
async def anomaly_detection(body: AnomalyRequest):
    """滚动 Z-Score 异常检测：|值 - 滚动均值| > threshold × 滚动标准差"""
    safe_code = body.code.strip().replace(".", "_")
    path = settings.cache_dir / body.period / f"{safe_code}.parquet"
    if not path.exists():
        return {"error": f"未找到 {body.code} 的本地缓存数据，请先到「数据中心」下载"}

    df = _load_stock(path)
    if df is None or df.empty or body.field not in df.columns:
        return {"error": f"数据为空或缺少字段 {body.field}"}

    s = df[body.field].astype(float)
    window = max(int(body.window), 2)
    rolling_mean = s.rolling(window).mean()
    rolling_std = s.rolling(window).std()
    zscore = (s - rolling_mean) / rolling_std
    mask = zscore.abs() > body.threshold

    columns = ["date", body.field, "rolling_mean", "zscore", "direction"]
    rows = []
    for idx in s.index[mask.fillna(False)]:
        z = float(zscore.loc[idx])
        rows.append(
            [
                str(idx.date()),
                _clean_value(s.loc[idx]),
                _clean_value(rolling_mean.loc[idx]),
                round(z, 3),
                "偏高" if z > 0 else "偏低",
            ]
        )

    return {
        "anomalies": {"columns": columns, "data": rows, "row_count": len(rows)},
        "code": body.code,
        "field": body.field,
    }
