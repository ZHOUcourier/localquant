"""数据探索路由 — SQL 查询 / 全市场扫描 / 横截面分析 / 异常检测

数据来源均为本地 Parquet 行情缓存（data/cache/{period}/{code}.parquet），
无缓存数据时返回明确的空结果与提示，不伪造数据。
"""

import math
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import APIRouter
from pydantic import BaseModel

from backend.config import settings
from backend.database import get_db
from backend.services import market_data
from backend.services.duckdb_service import DuckDBService

router = APIRouter()

duckdb_service = DuckDBService()

_SQL_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|create|alter|attach|detach|"
    r"export|copy|import|install|load|pragma|call)\b",
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


class SaveSQLRequest(BaseModel):
    name: str
    sql: str


async def _record_sql(sql: str, name: str = "") -> None:
    """记录 SQL 历史（最近 200 条以内按 last_used_at 去重覆盖）"""
    cleaned = sql.strip().rstrip(";").strip()
    if not cleaned:
        return
    now = int(time.time())
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, last_used_at FROM research_sql_queries WHERE sql = ?",
            (cleaned,),
        )
        row = await cursor.fetchone()
        if row:
            await db.execute(
                "UPDATE research_sql_queries SET last_used_at = ? WHERE id = ?",
                (now, row["id"]),
            )
        else:
            await db.execute(
                "INSERT INTO research_sql_queries (name, sql, created_at, last_used_at) "
                "VALUES (?, ?, ?, ?)",
                (name or "未命名查询", cleaned, now, now),
            )
        await db.commit()
    finally:
        await db.close()


@router.post("/query")
async def sql_query(body: SQLQueryRequest):
    """DuckDB SQL 查询本地 Parquet 数据（仅允许 SELECT）"""
    sql = body.sql.strip().rstrip(";")
    if not sql:
        return {
            "columns": [],
            "data": [],
            "row_count": 0,
            "error": "SQL 为空",
            "code": "invalid_query",
        }
    if not sql.lower().lstrip("(").startswith(("select", "with", "describe", "show")):
        return {
            "columns": [],
            "data": [],
            "row_count": 0,
            "error": "仅支持 SELECT / WITH / DESCRIBE 查询",
            "code": "invalid_query",
        }
    if _SQL_FORBIDDEN.search(sql):
        return {
            "columns": [],
            "data": [],
            "row_count": 0,
            "error": "SQL 中包含不允许的写操作关键字",
            "code": "invalid_query",
        }
    result = duckdb_service.query_local(sql)
    if isinstance(result, dict) and result.get("error"):
        result.setdefault("code", "query_error")
        return result
    await _record_sql(sql)
    return result


class SQLHistoryEntry(BaseModel):
    id: int
    name: str
    sql: str
    created_at: int
    last_used_at: int | None


@router.get("/sql/queries")
async def list_sql_queries():
    """已保存/最近使用的 SQL 查询"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, name, sql, created_at, last_used_at "
            "FROM research_sql_queries ORDER BY last_used_at DESC LIMIT 200"
        )
        rows = await cursor.fetchall()
        return {"queries": [dict(r) for r in rows]}
    finally:
        await db.close()


@router.post("/sql/queries")
async def save_sql_query(req: SaveSQLRequest):
    """保存常用 SQL（同名覆盖 sql，否则新增）"""
    name = req.name.strip()
    sql = req.sql.strip().rstrip(";").strip()
    if not name or not sql:
        return {"error": "name 与 sql 不能为空", "code": "invalid_request"}
    now = int(time.time())
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id FROM research_sql_queries WHERE name = ?", (name,)
        )
        row = await cursor.fetchone()
        if row:
            await db.execute(
                "UPDATE research_sql_queries SET sql = ?, last_used_at = ? WHERE id = ?",
                (sql, now, row["id"]),
            )
            query_id = row["id"]
        else:
            cursor = await db.execute(
                "INSERT INTO research_sql_queries (name, sql, created_at, last_used_at) "
                "VALUES (?, ?, ?, ?)",
                (name, sql, now, now),
            )
            query_id = cursor.lastrowid
        await db.commit()
        return {"id": query_id, "name": name, "sql": sql}
    finally:
        await db.close()


@router.delete("/sql/queries/{query_id}")
async def delete_sql_query(query_id: int):
    db = await get_db()
    try:
        await db.execute("DELETE FROM research_sql_queries WHERE id = ?", (query_id,))
        await db.commit()
        return {"deleted": query_id}
    finally:
        await db.close()


FIELD_DICTIONARY = {
    "open": "开盘价（原始价）",
    "high": "最高价（原始价）",
    "low": "最低价（原始价）",
    "close": "收盘价（原始价）",
    "volume": "成交量（股/手，以 QMT 返回单位为准）",
    "amount": "成交额（元）",
    "adjust_factor": "复权因子（后复权价/原始价；前复权=close×factor/最新factor）",
    "turnover": "换手率（需股本快照）",
}

SQL_TEMPLATES = [
    {
        "id": "recent_daily",
        "name": "单只股票最近 30 个交易日日线",
        "sql": "SELECT * FROM read_parquet('data/cache/1d/000001_SZ.parquet') ORDER BY index DESC LIMIT 30;",
        "note": "把文件名中的 000001_SZ 替换为你的股票代码（. 换成 _）",
    },
    {
        "id": "limit_move_scan",
        "name": "某日全市场涨幅榜",
        "sql": "SELECT filename AS code, close FROM read_parquet('data/cache/1d/*.parquet', filename=true) WHERE CAST(index AS VARCHAR) LIKE '2026-08-07%' ORDER BY close DESC LIMIT 50;",
        "note": "示例按收盘价排序；真正的涨幅榜需用 LAG 或 pct_change 计算",
    },
    {
        "id": "volume_spike",
        "name": "某日成交量前 50",
        "sql": "SELECT filename AS code, volume, amount FROM read_parquet('data/cache/1d/*.parquet', filename=true) WHERE CAST(index AS VARCHAR) LIKE '2026-08-07%' ORDER BY volume DESC LIMIT 50;",
    },
    {
        "id": "index_ohlc",
        "name": "指数最近 60 日",
        "sql": "SELECT * FROM read_parquet('data/cache/1d/000300_SH.parquet') ORDER BY index DESC LIMIT 60;",
    },
]


@router.get("/schema")
async def explorer_schema():
    """数据字典与查询模板：帮助快速知道每个周期有哪些字段、如何写 SQL"""
    tables = (await list_tables()).get("tables", [])
    for t in tables:
        t["fields"] = [
            {"name": c, "description": FIELD_DICTIONARY.get(c, "")}
            for c in t.get("columns", [])
        ]
    return {"tables": tables, "field_dictionary": FIELD_DICTIONARY, "templates": SQL_TEMPLATES}


@router.get("/tables")
async def list_tables():
    """列出本地可查询的数据表（各周期的 Parquet 缓存）

    sample_range 取该周期全部文件的并集范围，而不是第一个文件的范围；
    避免 QUBE get_data_status 拿到单文件样本区间后误判可回测区间。
    """
    tables = []
    cache_dir = settings.cache_dir
    if cache_dir.exists():
        for period_dir in sorted(cache_dir.iterdir()):
            if not period_dir.is_dir():
                continue
            files = sorted(period_dir.glob("*.parquet"))
            if not files:
                continue

            if period_dir.name == "reference":
                # 参考快照是 [date, code, ...] 长表，不是行情面板；
                # 日期范围来自 date 列，而不是把默认 RangeIndex 误解析成 1970。
                columns: list[str] = []
                ref_dates: list = []
                for f in files:
                    try:
                        df = pd.read_parquet(f)
                        columns = list(df.columns)
                        if "date" in df.columns:
                            ref_dates.extend(pd.to_datetime(df["date"], errors="coerce").dropna().tolist())
                    except Exception:
                        continue
                date_range = (
                    f"{min(ref_dates).date()} ~ {max(ref_dates).date()}"
                    if ref_dates
                    else ""
                )
                tables.append(
                    {
                        "period": "reference",
                        "path": "data/cache/reference/*.parquet",
                        "kind": "reference",
                        "file_count": len(files),
                        "columns": columns,
                        "sample_range": date_range,
                        "codes": [],
                        "note": "参考元数据快照（行业/成分/合约/两融池），非行情价格表",
                    }
                )
                continue

            # 行情周期：用覆盖度缓存的并集范围；列结构只读第一个文件即可（下载层保证同构）
            sample = _load_stock(files[0])
            columns = list(sample.columns) if sample is not None else []
            date_range = ""
            try:
                coverage = market_data.cache_coverage(period_dir.name)
                starts = [e.get("start") for e in coverage if e.get("start")]
                ends = [e.get("end") for e in coverage if e.get("end")]
                if starts and ends:
                    date_range = f"{min(starts)} ~ {max(ends)}"
            except Exception:
                if sample is not None and len(sample) > 0:
                    date_range = f"{sample.index.min().date()} ~ {sample.index.max().date()}"
            all_codes = [_file_code(f) for f in files]
            tables.append(
                {
                    "period": period_dir.name,
                    "path": f"data/cache/{period_dir.name}/*.parquet",
                    "kind": "quotes",
                    "stock_count": len(files),
                    "columns": columns,
                    "sample_range": date_range,
                    "codes": all_codes[:200],
                    "codes_truncated": len(all_codes) > 200,
                    "note": (
                        "缓存为不复权价 + adjust_factor 列；前复权价 = close × adjust_factor / 最新 adjust_factor"
                        if "adjust_factor" in columns
                        else "旧版前复权缓存（无 adjust_factor 列）"
                    ),
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
        err = market_data.no_cache_error_detail(body.period)
        return {
            "columns": [],
            "data": [],
            "row_count": 0,
            "error": err["message"] + " — " + err["hint"],
            "code": err["code"],
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
                "code": "invalid_request",
            }
        col, op, val = m.group(1), m.group(2), float(m.group(3))
        parsed.append((col, "==" if op == "=" else op, val))

    try:
        target = pd.to_datetime(body.date)
    except Exception:
        return {
            "columns": [],
            "data": [],
            "row_count": 0,
            "error": "日期格式不合法",
            "code": "invalid_request",
        }

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
            if (
                (op == ">" and v <= val)
                or (op == "<" and v >= val)
                or (op == ">=" and v < val)
                or (op == "<=" and v > val)
                or (op == "==" and v != val)
                or (op == "!=" and v == val)
            ):
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
        err = market_data.no_cache_error_detail(body.period)
        return {
            "error": err["message"] + " — " + err["hint"],
            "code": err["code"],
        }

    try:
        target = pd.to_datetime(body.date)
    except Exception:
        return {"error": "日期格式不合法", "code": "invalid_request"}

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
            "error": f"该日期无 {body.field} 数据（检查日期是否为交易日、数据是否已缓存）",
            "code": "no_data",
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
        return {
            "error": f"未找到 {body.code} 的本地缓存数据，请先到「数据中心」下载",
            "code": "no_cached_data",
        }

    df = _load_stock(path)
    if df is None or df.empty or body.field not in df.columns:
        return {"error": f"数据为空或缺少字段 {body.field}", "code": "invalid_field"}

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


# ── 公共：按代码加载收盘价序列 ─────────────────────────────


def _load_close(code: str, period: str = "1d") -> pd.Series | None:
    """加载单只股票的收盘价序列（本地缓存），不存在返回 None"""
    safe_code = code.strip().replace(".", "_")
    path = settings.cache_dir / period / f"{safe_code}.parquet"
    if not path.exists():
        return None
    df = _load_stock(path)
    if df is None or df.empty or "close" not in df.columns:
        return None
    s = df["close"].astype(float).dropna()
    s.index = pd.to_datetime(s.index).normalize()
    return s[~s.index.duplicated(keep="last")].sort_index()


def _clip_range(s: pd.Series, start_date: str, end_date: str) -> pd.Series:
    if start_date:
        s = s[s.index >= pd.to_datetime(start_date)]
    if end_date:
        s = s[s.index <= pd.to_datetime(end_date)]
    return s


def _histogram(values: pd.Series, bins: int = 20) -> list[dict]:
    counts, edges = np.histogram(values.dropna(), bins=bins)
    return [
        {"bin": f"{edges[i]:.4g}", "count": int(counts[i])} for i in range(len(counts))
    ]


# ── 回归分析 ─────────────────────────────────────────────────


class RegressionRequest(BaseModel):
    code_y: str  # 因变量 Y
    code_x: str  # 自变量 X
    start_date: str = ""
    end_date: str = ""
    use_returns: bool = False  # False=收盘价回归，True=日收益率回归
    period: str = "1d"


@router.post("/regression")
async def regression_analysis(body: RegressionRequest):
    """两标的线性回归：Y = beta*X + alpha，返回散点/拟合线/统计量/边缘分布"""
    sy = _load_close(body.code_y, body.period)
    sx = _load_close(body.code_x, body.period)
    if sy is None:
        return {"error": f"未找到 {body.code_y} 的本地缓存数据，请先到「数据中心」下载"}
    if sx is None:
        return {"error": f"未找到 {body.code_x} 的本地缓存数据，请先到「数据中心」下载"}

    sy = _clip_range(sy, body.start_date, body.end_date)
    sx = _clip_range(sx, body.start_date, body.end_date)
    df = pd.DataFrame({"y": sy, "x": sx}).dropna()
    if body.use_returns:
        df = df.pct_change().dropna()
    if len(df) < 10:
        return {
            "error": "重叠区间样本不足 10 个交易日，无法回归（检查日期区间与数据覆盖）"
        }

    x, y = df["x"].to_numpy(), df["y"].to_numpy()
    beta, alpha = np.polyfit(x, y, 1)
    r = float(np.corrcoef(x, y)[0, 1])
    y_hat = beta * x + alpha
    ss_res = float(((y - y_hat) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

    return {
        "code_y": body.code_y,
        "code_x": body.code_x,
        "use_returns": body.use_returns,
        "points": [
            [round(float(a), 6), round(float(b), 6), str(d.date())]
            for d, a, b in zip(df.index, x, y)
        ],
        "line": {
            "x0": float(x.min()),
            "y0": float(beta * x.min() + alpha),
            "x1": float(x.max()),
            "y1": float(beta * x.max() + alpha),
        },
        "stats": {
            "样本数量": len(df),
            "Beta": round(float(beta), 4),
            "Alpha": round(float(alpha), 4),
            "R": round(r, 4),
            "R^2": round(float(r2), 4),
        },
        "hist_x": _histogram(df["x"]),
        "hist_y": _histogram(df["y"]),
    }


# ── 季节性分析 ────────────────────────────────────────────────


class SeasonalityRequest(BaseModel):
    code: str
    years: int = 5
    period: str = "1d"


@router.post("/seasonality")
async def seasonality_analysis(body: SeasonalityRequest):
    """季节性分析：分年度叠加走势（归一化）+ 月度涨跌幅矩阵 + 逐月统计"""
    s = _load_close(body.code, body.period)
    if s is None:
        return {"error": f"未找到 {body.code} 的本地缓存数据，请先到「数据中心」下载"}

    years = sorted(s.index.year.unique())[-max(int(body.years), 2) :]
    s = s[s.index.year >= years[0]]
    if len(years) < 2:
        return {"error": "本地数据不足两个年度，无法做季节性对比"}

    # 年度叠加曲线：每年首日归一化为 100，x 轴用 MM-DD
    yearly_series = []
    for yr in years:
        ys = s[s.index.year == yr]
        if len(ys) < 20:
            continue
        norm = ys / float(ys.iloc[0]) * 100.0
        yearly_series.append(
            {
                "year": int(yr),
                "x": [d.strftime("%m-%d") for d in norm.index],
                "y": [round(float(v), 3) for v in norm.to_numpy()],
            }
        )

    # 月度收益矩阵（月末/月初收盘价环比）
    monthly = s.resample("ME").last().pct_change() * 100.0
    matrix_rows = []
    for yr in years:
        row: dict = {"year": int(yr)}
        for m in range(1, 13):
            sel = monthly[(monthly.index.year == yr) & (monthly.index.month == m)]
            row[f"m{m}"] = (
                round(float(sel.iloc[0]), 2)
                if len(sel) and not pd.isna(sel.iloc[0])
                else None
            )
        matrix_rows.append(row)

    # 逐月统计：均值/上涨次数/下跌次数
    month_stats = []
    for m in range(1, 13):
        vals = [r[f"m{m}"] for r in matrix_rows if r[f"m{m}"] is not None]
        month_stats.append(
            {
                "month": m,
                "avg": round(float(np.mean(vals)), 2) if vals else None,
                "up": sum(1 for v in vals if v > 0),
                "down": sum(1 for v in vals if v <= 0),
                "count": len(vals),
            }
        )

    return {
        "code": body.code,
        "years": [int(y) for y in years],
        "yearly_series": yearly_series,
        "monthly_matrix": matrix_rows,
        "month_stats": month_stats,
    }


# ── 历史波动率分析 ─────────────────────────────────────────────


class VolatilityRequest(BaseModel):
    code: str
    windows: list[int] = [5, 15, 30, 50]
    annualize: int = 250
    start_date: str = ""
    end_date: str = ""
    period: str = "1d"


@router.post("/volatility")
async def volatility_analysis(body: VolatilityRequest):
    """历史波动率 HV：对数收益滚动标准差年化，多窗口时序 + 统计概览 + 频率分布"""
    s = _load_close(body.code, body.period)
    if s is None:
        return {"error": f"未找到 {body.code} 的本地缓存数据，请先到「数据中心」下载"}

    log_ret = np.log(s / s.shift(1))
    windows = [max(int(w), 2) for w in (body.windows or [5, 15, 30, 50])][:6]
    ann = np.sqrt(max(int(body.annualize), 1))

    series_out = []
    stats_out = {}
    hist_out = {}
    for w in windows:
        hv = (log_ret.rolling(w).std() * ann).dropna()
        hv_clip = _clip_range(hv, body.start_date, body.end_date)
        if hv_clip.empty:
            continue
        name = f"HV{w}"
        series_out.append(
            {
                "name": name,
                "x": [str(d.date()) for d in hv_clip.index],
                "y": [round(float(v), 4) for v in hv_clip.to_numpy()],
            }
        )
        latest = float(hv_clip.iloc[-1])
        stats_out[name] = {
            "最新": round(latest, 4),
            "均值": round(float(hv_clip.mean()), 4),
            "中值": round(float(hv_clip.median()), 4),
            "标准差": round(float(hv_clip.std()), 4),
            "百分位": round(float((hv_clip < latest).mean() * 100), 2),
            "最高": round(float(hv_clip.max()), 4),
            "最低": round(float(hv_clip.min()), 4),
        }
        hist_out[name] = _histogram(hv_clip, bins=12)

    if not series_out:
        return {"error": "所选区间内数据不足，无法计算波动率（调整区间或窗口）"}

    return {
        "code": body.code,
        "annualize": int(body.annualize),
        "series": series_out,
        "stats": stats_out,
        "histograms": hist_out,
    }


# ── 相关性分析 ────────────────────────────────────────────────


class CorrelationMatrixRequest(BaseModel):
    codes: list[str]
    start_date: str = ""
    end_date: str = ""
    period: str = "1d"


@router.post("/correlation")
async def correlation_matrix(body: CorrelationMatrixRequest):
    """多标的日收益率 Pearson 相关系数矩阵"""
    codes = [c.strip() for c in body.codes if c.strip()]
    if len(codes) < 2:
        return {"error": "至少需要 2 个标的代码"}

    frames: dict[str, pd.Series] = {}
    missing: list[str] = []
    for code in codes[:30]:
        s = _load_close(code, body.period)
        if s is None:
            missing.append(code)
            continue
        frames[code] = _clip_range(s, body.start_date, body.end_date)

    if len(frames) < 2:
        return {
            "error": "可用标的不足 2 个（缺失: "
            + ", ".join(missing[:10])
            + "），请先到「数据中心」下载"
        }

    rets = pd.DataFrame(frames).pct_change().dropna(how="all")
    corr = rets.corr(min_periods=10)
    ordered = list(corr.columns)
    matrix = [
        [
            None if pd.isna(corr.iloc[i, j]) else round(float(corr.iloc[i, j]), 3)
            for j in range(len(ordered))
        ]
        for i in range(len(ordered))
    ]

    return {
        "codes": ordered,
        "matrix": matrix,
        "missing": missing,
        "n_obs": len(rets),
    }


# ── 风险画像 ────────────────────────────────────────────────────


class RiskProfileRequest(BaseModel):
    code: str
    start_date: str = ""
    end_date: str = ""
    period: str = "1d"


@router.post("/risk-profile")
async def risk_profile(body: RiskProfileRequest):
    """单标的风险画像：收益/波动/回撤/尾部风险指标 + 净值与回撤曲线 + 收益分布"""
    s = _load_close(body.code, body.period)
    if s is None:
        return {"error": f"未找到 {body.code} 的本地缓存数据，请先到「数据中心」下载"}
    s = _clip_range(s, body.start_date, body.end_date)
    if len(s) < 30:
        return {"error": "区间内样本不足 30 个交易日，无法给出有意义的风险指标"}

    ret = s.pct_change().dropna()
    equity = (1 + ret).cumprod()
    roll_max = equity.cummax()
    drawdown = equity / roll_max - 1

    n = len(ret)
    ann_ret = float((1 + ret.mean()) ** 250 - 1)
    ann_vol = float(ret.std() * np.sqrt(250))
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0.0
    max_dd = float(drawdown.min())
    var95 = float(ret.quantile(0.05))
    cvar95 = float(ret[ret <= var95].mean()) if (ret <= var95).any() else var95

    metrics = {
        "区间涨跌幅": round(float(equity.iloc[-1] - 1) * 100, 2),
        "年化收益(%)": round(ann_ret * 100, 2),
        "年化波动(%)": round(ann_vol * 100, 2),
        "夏普比率": round(sharpe, 3),
        "最大回撤(%)": round(max_dd * 100, 2),
        "卡玛比率": round(ann_ret / abs(max_dd), 3) if max_dd < 0 else None,
        "日胜率(%)": round(float((ret > 0).mean()) * 100, 2),
        "偏度": round(float(ret.skew()), 3),
        "峰度": round(float(ret.kurt()), 3),
        "VaR95(日,%)": round(var95 * 100, 2),
        "CVaR95(日,%)": round(cvar95 * 100, 2),
        "样本数": n,
    }

    dates = [str(d.date()) for d in equity.index]
    return {
        "code": body.code,
        "metrics": metrics,
        "equity": {"x": dates, "y": [round(float(v), 4) for v in equity]},
        "drawdown": {
            "x": dates,
            "y": [round(float(v) * 100, 2) for v in drawdown],
        },
        "return_hist": _histogram(ret * 100, bins=30),
    }


# ── 配对价差分析 ──────────────────────────────────────────────


class PairSpreadRequest(BaseModel):
    code_a: str
    code_b: str
    window: int = 60
    start_date: str = ""
    end_date: str = ""
    period: str = "1d"


@router.post("/pair-spread")
async def pair_spread(body: PairSpreadRequest):
    """配对价差：价格比价序列 + 对数价差滚动 Z-Score（±2 带），支持配对交易研究"""
    sa = _load_close(body.code_a, body.period)
    sb = _load_close(body.code_b, body.period)
    if sa is None:
        return {"error": f"未找到 {body.code_a} 的本地缓存数据，请先到「数据中心」下载"}
    if sb is None:
        return {"error": f"未找到 {body.code_b} 的本地缓存数据，请先到「数据中心」下载"}

    df = pd.DataFrame({"a": sa, "b": sb}).dropna()
    df = df[(df["a"] > 0) & (df["b"] > 0)]
    window = max(int(body.window), 5)
    df = _clip_df_range(df, body.start_date, body.end_date, extra_head=window)
    if len(df) < window + 10:
        return {
            "error": f"重叠样本不足（需至少 {window + 10} 个交易日），调整区间或窗口"
        }

    ratio = df["a"] / df["b"]
    log_spread = np.log(df["a"]) - np.log(df["b"])
    roll_mean = log_spread.rolling(window).mean()
    roll_std = log_spread.rolling(window).std()
    zscore = ((log_spread - roll_mean) / roll_std).dropna()

    # 裁到用户请求区间（前面多取了 window 个热身样本）
    if body.start_date:
        zscore = zscore[zscore.index >= pd.to_datetime(body.start_date)]
        ratio = ratio[ratio.index >= pd.to_datetime(body.start_date)]
    if zscore.empty:
        return {"error": "所选区间内无有效 Z-Score 样本，请扩大区间"}

    ret_corr = float(df["a"].pct_change().corr(df["b"].pct_change()))
    cur_z = float(zscore.iloc[-1])
    return {
        "code_a": body.code_a,
        "code_b": body.code_b,
        "window": window,
        "stats": {
            "当前 Z-Score": round(cur_z, 3),
            "收益相关系数": round(ret_corr, 3),
            "当前比价": round(float(ratio.iloc[-1]), 4),
            "比价均值": round(float(ratio.mean()), 4),
            "|Z|>2 占比(%)": round(float((zscore.abs() > 2).mean()) * 100, 2),
            "样本数": len(zscore),
        },
        "ratio": {
            "x": [str(d.date()) for d in ratio.index],
            "y": [round(float(v), 4) for v in ratio],
        },
        "zscore": {
            "x": [str(d.date()) for d in zscore.index],
            "y": [round(float(v), 3) for v in zscore],
        },
    }


def _clip_df_range(
    df: pd.DataFrame, start_date: str, end_date: str, extra_head: int = 0
) -> pd.DataFrame:
    """按区间裁剪 DataFrame，可在起点前多保留 extra_head 行供滚动窗口热身"""
    if end_date:
        df = df[df.index <= pd.to_datetime(end_date)]
    if start_date:
        start = pd.to_datetime(start_date)
        pos = df.index.searchsorted(start)
        df = df.iloc[max(0, int(pos) - extra_head) :]
    return df


# ── 滚动相关 / 滚动 Beta ───────────────────────────────────────


class RollingCorrRequest(BaseModel):
    code_a: str  # 标的
    code_b: str  # 基准（如指数）
    window: int = 60
    start_date: str = ""
    end_date: str = ""
    period: str = "1d"


@router.post("/rolling-corr")
async def rolling_corr(body: RollingCorrRequest):
    """两标的日收益的滚动相关系数与滚动 Beta（a 对 b 回归）时序"""
    sa = _load_close(body.code_a, body.period)
    sb = _load_close(body.code_b, body.period)
    if sa is None:
        return {"error": f"未找到 {body.code_a} 的本地缓存数据，请先到「数据中心」下载"}
    if sb is None:
        return {"error": f"未找到 {body.code_b} 的本地缓存数据，请先到「数据中心」下载"}

    rets = pd.DataFrame({"a": sa, "b": sb}).dropna().pct_change().dropna()
    window = max(int(body.window), 10)
    rets = _clip_df_range(rets, body.start_date, body.end_date, extra_head=window)
    if len(rets) < window + 5:
        return {
            "error": f"重叠样本不足（需至少 {window + 5} 个交易日），调整区间或窗口"
        }

    roll_corr = rets["a"].rolling(window).corr(rets["b"])
    roll_beta = (
        rets["a"].rolling(window).cov(rets["b"]) / rets["b"].rolling(window).var()
    )
    out = pd.DataFrame({"corr": roll_corr, "beta": roll_beta}).dropna()
    if body.start_date:
        out = out[out.index >= pd.to_datetime(body.start_date)]
    if out.empty:
        return {"error": "所选区间内无有效滚动样本，请扩大区间"}

    return {
        "code_a": body.code_a,
        "code_b": body.code_b,
        "window": window,
        "stats": {
            "当前相关": round(float(out["corr"].iloc[-1]), 3),
            "相关均值": round(float(out["corr"].mean()), 3),
            "当前 Beta": round(float(out["beta"].iloc[-1]), 3),
            "Beta 均值": round(float(out["beta"].mean()), 3),
            "样本数": len(out),
        },
        "x": [str(d.date()) for d in out.index],
        "corr": [round(float(v), 3) for v in out["corr"]],
        "beta": [round(float(v), 3) for v in out["beta"]],
    }


# ── 事件研究（CAR/BHAR） ───────────────────────────────────────────────


class EventStudyRequest(BaseModel):
    event_type: str = "limit_up"  # limit_up / limit_down / volume_spike / dividend / custom
    codes: str = ""
    start_date: str = ""
    end_date: str = ""
    window_before: int = 10
    window_after: int = 10
    min_events: int = 5
    volume_k: float = 3.0
    events: list[dict] = []  # 手工事件 [{date, code}]（event_type=custom 时使用）
    benchmark_code: str = ""  # 基准标的（如 000300.SH）；空=全市场截面均值
    period: str = "1d"


@router.post("/event-study")
async def event_study(body: EventStudyRequest):
    """事件研究：事件窗口 CAR/BHAR + t 值 + 正值占比

    内置事件源（全部来自本地 QMT 缓存）：
      limit_up / limit_down  一字涨停/跌停（high==low 且收盘触及涨跌停近似价）
      volume_spike           放量（量 > k× 前 20 日均量）
      dividend               除权除息（adjust_factor 跳变）
      custom                 手工事件列表
    基准默认当日全市场截面均值；事件日=0。
    """
    from backend.services.event_study import build_event_frame, event_study_analysis

    pool = [c.strip() for c in body.codes.split(",") if c.strip()]
    if not pool:
        pool = market_data.list_cached_codes("1d", exclude_indices=True)
    try:
        panels = market_data.load_price_panels(
            codes=pool, start_date=body.start_date, end_date=body.end_date
        )
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    close = panels["close"]
    volume = panels.get("volume")
    high = panels.get("high")
    low = panels.get("low")
    # 前向填充口径：停牌日收益 0、复牌日跳空入账（与回测/因子研究一致）
    rets = market_data.build_return_panel(close)

    up = down = None
    if body.event_type in ("limit_up", "limit_down"):
        reference = market_data.load_reference_panels(close, volume)
        up, down = reference["up_limit"], reference["down_limit"]

    dividend = None
    if body.event_type == "dividend":
        dividend = market_data.dividend_events(
            period=body.period, codes=list(close.columns), days=3650, limit=100000
        )

    events = build_event_frame(
        event_type=body.event_type,
        close=close,
        volume=volume,
        high=high,
        low=low,
        up_limit=up,
        down_limit=down,
        dividend_events=dividend,
        manual_events=body.events or None,
        volume_k=body.volume_k,
    )
    market_returns = None
    benchmark_code = body.benchmark_code.strip()
    if benchmark_code:
        try:
            bench = market_data.load_price_panels(
                codes=[benchmark_code],
                start_date=body.start_date,
                end_date=body.end_date,
            )
            market_returns = market_data.build_return_panel(bench["close"]).iloc[:, 0]
        except Exception as e:
            return {"ok": False, "error": f"基准行情加载失败 {benchmark_code}: {e}"}

    result = event_study_analysis(
        rets,
        events,
        window_before=body.window_before,
        window_after=body.window_after,
        market_returns=market_returns,
        min_events=body.min_events,
    )
    result["event_type"] = body.event_type
    result["n_detected"] = len(events)
    result["n_stocks"] = int(close.shape[1])
    result["data_start"] = str(close.index[0])[:10]
    result["data_end"] = str(close.index[-1])[:10]
    return result


@router.post("/event-study/calendar-time")
async def event_study_calendar_time(body: EventStudyRequest):
    """Calendar-time portfolio 事件研究：事件组合按月聚合后的时间序列检验。

    适用于事件在时间上高度聚集、窗口重叠的研究场景；与单事件 CAR 互补。
    """
    from backend.services.event_study import build_event_frame, calendar_time_portfolio

    pool = [c.strip() for c in body.codes.split(",") if c.strip()]
    if not pool:
        pool = market_data.list_cached_codes("1d", exclude_indices=True)
    try:
        panels = market_data.load_price_panels(
            codes=pool, start_date=body.start_date, end_date=body.end_date
        )
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    close = panels["close"]
    volume = panels.get("volume")
    high = panels.get("high")
    low = panels.get("low")
    rets = market_data.build_return_panel(close)

    up = down = None
    if body.event_type in ("limit_up", "limit_down"):
        reference = market_data.load_reference_panels(close, volume)
        up, down = reference["up_limit"], reference["down_limit"]

    dividend = None
    if body.event_type == "dividend":
        dividend = market_data.dividend_events(
            period=body.period, codes=list(close.columns), days=3650, limit=100000
        )

    events = build_event_frame(
        event_type=body.event_type,
        close=close,
        volume=volume,
        high=high,
        low=low,
        up_limit=up,
        down_limit=down,
        dividend_events=dividend,
        manual_events=body.events or None,
        volume_k=body.volume_k,
    )
    market_returns = None
    benchmark_code = body.benchmark_code.strip()
    if benchmark_code:
        try:
            bench = market_data.load_price_panels(
                codes=[benchmark_code],
                start_date=body.start_date,
                end_date=body.end_date,
            )
            market_returns = market_data.build_return_panel(bench["close"]).iloc[:, 0]
        except Exception as e:
            return {"ok": False, "error": f"基准行情加载失败 {benchmark_code}: {e}"}

    result = calendar_time_portfolio(
        rets,
        events,
        window_after=body.window_after,
        market_returns=market_returns,
        min_events=body.min_events,
    )
    result["event_type"] = body.event_type
    result["n_detected"] = len(events)
    result["n_stocks"] = int(close.shape[1])
    result["data_start"] = str(close.index[0])[:10]
    result["data_end"] = str(close.index[-1])[:10]
    return result
