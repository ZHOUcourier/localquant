"""DuckDB 服务 — 使用 SQL 查询本地 Parquet 数据"""
from __future__ import annotations

import math
import re

import duckdb
import pandas as pd
from loguru import logger

from backend.config import settings

# 单次查询返回的最大结果行数（防止整市场扫描 OOM）
MAX_RESULT_ROWS = 2000

# 写/危险操作关键字，禁止在本地查询接口中出现（读接口只允许查询）
_SQL_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|create|alter|attach|detach|"
    r"export|copy|import|install|load|pragma|call)\b",
    re.IGNORECASE,
)

# 统一行情视图前缀：每个行情周期注册一个只读视图 quotes_<周期>
# （如 quotes_1d / quotes_5m），把 pandas Parquet 的无名日期索引列
# （DuckDB 里叫 __index_level_0__）规范成 trade_date，并从文件名解析 code，
# 让用户 / AI 面向干净的 trade_date / code / OHLCV 列，而不是 __index_level_0__。
QUOTE_VIEW_PREFIX = "quotes_"
# 行情视图暴露的值列（只保留实际存在的）
KLINE_WANTED = ["open", "high", "low", "close", "volume", "amount", "adjust_factor"]


def quote_view(period: str) -> str:
    """返回某周期对应的统一行情视图名（如 quotes_1d）"""
    return f"{QUOTE_VIEW_PREFIX}{period}"


class DuckDBService:
    """DuckDB 查询服务，提供对本地 Parquet 缓存的 SQL 访问"""

    def __init__(self):
        self.cache_dir = settings.cache_dir

    # ── 核心查询 ─────────────────────────────────────────────

    def query_local(self, sql: str, params: list | None = None) -> dict:
        """执行 SQL 查询本地 Parquet 数据

        支持语法：
            SELECT * FROM read_parquet('data/cache/1d/*.parquet') WHERE ...
            SELECT * FROM 'data/cache/1d/000001_SZ.parquet' WHERE ...

        Args:
            sql: SQL 查询语句
            params: 查询参数

        Returns:
            {"columns": [...], "data": [...], "row_count": N}
            出错时 {"columns": [], "data": [], "row_count": 0, "error", "code"}，
            code ∈ invalid_query（语句非法）/ query_error（执行失败），供程序分支
        """
        try:
            statement = sql.lstrip().lstrip("(").lower()
            if not statement.startswith(("select", "with", "describe", "show")):
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

            conn = duckdb.connect()
            # 注册用户可见的统一行情视图（quotes_<周期>），再执行用户 SQL
            self._register_quote_views(conn)
            if params:
                result = conn.execute(sql, params).fetchdf()
            else:
                result = conn.execute(sql).fetchdf()
            conn.close()

            truncated = len(result) > MAX_RESULT_ROWS
            if truncated:
                result = result.iloc[:MAX_RESULT_ROWS]

            # 时间戳列统一转可读字符串：单列时间戳经 fetchdf().values 会变成
            # epoch 纳秒整数（混合列时才是 pd.Timestamp），这里对齐成可读格式
            for col in result.columns:
                if pd.api.types.is_datetime64_any_dtype(result[col]):
                    result[col] = result[col].astype(str)

            columns = result.columns.tolist()
            data = result.values.tolist()

            # 清理 NaN / Timestamp 等不可序列化类型
            clean_data = []
            for row in data:
                clean_row = []
                for val in row:
                    if isinstance(val, float) and math.isnan(val):
                        clean_row.append(None)
                    elif isinstance(val, pd.Timestamp):
                        clean_row.append(str(val))
                    else:
                        clean_row.append(val)
                clean_data.append(clean_row)

            return {
                "columns": columns,
                "data": clean_data,
                "row_count": len(clean_data),
                "truncated": truncated if truncated else False,
            }
        except Exception as e:
            logger.error(f"DuckDB query failed: {e}")
            return {
                "columns": [],
                "data": [],
                "row_count": 0,
                "error": str(e),
                "code": "query_error",
            }

    # ── 统一行情视图 ─────────────────────────────────────────

    def _register_quote_views(self, conn) -> None:
        """在每个行情周期上注册只读视图 quotes_<周期>。

        视图把 pandas Parquet 的无名日期索引列（DuckDB 里是 __index_level_0__）
        别名为 trade_date，并从文件名解析出 code（000001_SZ → 000001.SZ），
        再暴露实际存在的 open/high/low/close/volume/amount/adjust_factor 列。

        只为「行情」目录建视图：用首文件 schema 是否含 open/close 判定，
        自动跳过 reference/ 这类参考快照（长表，非行情面板）。
        视图是惰性求值，注册本身不读数据；建在临时连接上，连接关闭即失效。
        """
        cache_dir = self.cache_dir
        try:
            if not cache_dir.exists():
                return
            for period_dir in sorted(cache_dir.iterdir()):
                if not period_dir.is_dir():
                    continue
                files = sorted(period_dir.glob("*.parquet"))
                if not files:
                    continue
                # 用首文件 schema 判定是否为行情（含 open/close 列）
                try:
                    schema = conn.execute(
                        f"DESCRIBE SELECT * FROM read_parquet('{files[0]}')"
                    ).fetchall()
                except Exception:
                    continue
                cols = {row[0] for row in schema}
                if "open" not in cols or "close" not in cols:
                    continue
                present = [c for c in KLINE_WANTED if c in cols]
                glob_path = str((period_dir.resolve() / "*.parquet").as_posix())
                view = quote_view(period_dir.name)
                conn.execute(
                    f"""
                    CREATE OR REPLACE TEMP VIEW "{view}" AS
                    SELECT
                        __index_level_0__ AS trade_date,
                        replace(
                            regexp_extract(filename, '([A-Za-z0-9_]+)\\.parquet$', 1),
                            '_', '.'
                        ) AS code,
                        {", ".join(present)}
                    FROM read_parquet('{glob_path}', filename=true)
                    """
                )
        except Exception as e:
            # 视图注册失败不应阻断普通 read_parquet 查询，仅记录
            logger.warning(f"注册行情视图失败（不影响原始查询）: {e}")

    # ── 路径工具 ─────────────────────────────────────────────

    def get_parquet_path(self, code: str, period: str = "1d") -> str:
        """获取 Parquet 文件路径字符串（可直接用于 SQL）

        Args:
            code: 股票代码（如 "000001.SZ"，内部将 '.' 替换为 '_'）
            period: 数据周期

        Returns:
            绝对路径字符串
        """
        safe_code = code.replace(".", "_")
        return str(self.cache_dir / period / f"{safe_code}.parquet")
