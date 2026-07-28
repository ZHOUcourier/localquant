"""DuckDB 服务 — 使用 SQL 查询本地 Parquet 数据"""
from __future__ import annotations

import math
from typing import Optional

import duckdb
import pandas as pd
from loguru import logger

from backend.config import settings


class DuckDBService:
    """DuckDB 查询服务，提供对本地 Parquet 缓存的 SQL 访问"""

    def __init__(self):
        self.cache_dir = settings.cache_dir

    # ── 核心查询 ─────────────────────────────────────────────

    def query_local(self, sql: str, params: Optional[list] = None) -> dict:
        """执行 SQL 查询本地 Parquet 数据

        支持语法：
            SELECT * FROM read_parquet('data/cache/1d/*.parquet') WHERE ...
            SELECT * FROM 'data/cache/1d/000001_SZ.parquet' WHERE ...

        Args:
            sql: SQL 查询语句
            params: 查询参数

        Returns:
            {"columns": [...], "data": [...], "row_count": N}
        """
        try:
            conn = duckdb.connect()
            if params:
                result = conn.execute(sql, params).fetchdf()
            else:
                result = conn.execute(sql).fetchdf()
            conn.close()

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
            }
        except Exception as e:
            logger.error(f"DuckDB query failed: {e}")
            return {"columns": [], "data": [], "row_count": 0, "error": str(e)}

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
