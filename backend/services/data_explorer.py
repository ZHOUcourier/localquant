"""数据探索服务 — 使用 DuckDB 查询本地 Parquet 数据"""
import duckdb
import pandas as pd
import math
from pathlib import Path
from typing import Optional
from loguru import logger

from backend.config import settings


class DataExplorerService:
    """数据探索服务"""
    
    def __init__(self):
        self.cache_dir = settings.cache_dir
    
    def query(self, sql: str, params: Optional[list] = None) -> dict:
        """执行 SQL 查询本地 Parquet 数据"""
        try:
            conn = duckdb.connect()
            if params:
                result = conn.execute(sql, params).fetchdf()
            else:
                result = conn.execute(sql).fetchdf()
            conn.close()
            
            columns = result.columns.tolist()
            data = []
            for row in result.values.tolist():
                clean_row = []
                for val in row:
                    if isinstance(val, float) and math.isnan(val):
                        clean_row.append(None)
                    elif isinstance(val, pd.Timestamp):
                        clean_row.append(str(val))
                    else:
                        clean_row.append(val)
                data.append(clean_row)
            
            return {"columns": columns, "data": data, "row_count": len(data)}
        except Exception as e:
            logger.error(f"Query failed: {e}")
            return {"columns": [], "data": [], "row_count": 0, "error": str(e)}
    
    def market_scan(self, date: str, conditions: list[str] = None) -> dict:
        """全市场扫描"""
        cache_pattern = str(self.cache_dir / "1d" / "*.parquet")
        where_parts = [f"CAST(index AS VARCHAR) LIKE '{date}%'"]
        if conditions:
            where_parts.extend(conditions)
        where_clause = " AND ".join(where_parts)
        sql = f"SELECT * FROM read_parquet('{cache_pattern}') WHERE {where_clause}"
        return self.query(sql)
    
    def cross_section_analysis(self, date: str, field: str, codes: Optional[list[str]] = None) -> dict:
        """横截面分析"""
        cache_pattern = str(self.cache_dir / "1d" / "*.parquet")
        where_parts = [f"CAST(index AS VARCHAR) LIKE '{date}%'"]
        if codes:
            code_list = "', '".join(c.replace(".", "_") for c in codes)
            where_parts.append(f"filename IN ('{code_list}')")
        where_clause = " AND ".join(where_parts)
        
        stats_sql = f"""
            SELECT COUNT(*) as count, AVG({field}) as mean, MIN({field}) as min,
                   MAX({field}) as max, STDDEV({field}) as stddev,
                   APPROX_QUANTILE({field}, 0.25) as q25,
                   APPROX_QUANTILE({field}, 0.5) as median,
                   APPROX_QUANTILE({field}, 0.75) as q75
            FROM read_parquet('{cache_pattern}') WHERE {where_clause}
        """
        stats = self.query(stats_sql)
        return {"statistics": stats}
    
    def anomaly_detection(self, code: str, field: str, window: int = 20, threshold: float = 2.0) -> dict:
        """异常值检测（滚动 Z-Score）"""
        safe_code = code.replace(".", "_")
        file_path = self.cache_dir / "1d" / f"{safe_code}.parquet"
        if not file_path.exists():
            return {"anomalies": [], "error": f"数据文件不存在: {file_path}"}
        
        sql = f"""
            WITH data AS (
                SELECT *, ROW_NUMBER() OVER () as rn FROM read_parquet('{file_path}')
            ),
            stats AS (
                SELECT *, 
                    AVG({field}) OVER (ORDER BY rn ROWS BETWEEN {window} PRECEDING AND CURRENT ROW) as rolling_mean,
                    STDDEV({field}) OVER (ORDER BY rn ROWS BETWEEN {window} PRECEDING AND CURRENT ROW) as rolling_std
                FROM data
            )
            SELECT *, ABS({field} - rolling_mean) / NULLIF(rolling_std, 0) as z_score
            FROM stats
            WHERE ABS({field} - rolling_mean) / NULLIF(rolling_std, 0) > {threshold}
        """
        result = self.query(sql)
        return {"anomalies": result, "code": code, "field": field}
    
    def data_quality_check(self, codes: list[str], period: str = "1d") -> dict:
        """数据质量检查"""
        report = {"total_codes": len(codes), "checked_codes": 0, "issues": []}
        for code in codes:
            safe_code = code.replace(".", "_")
            file_path = self.cache_dir / period / f"{safe_code}.parquet"
            if not file_path.exists():
                report["issues"].append({"code": code, "issue": "missing_file", "message": f"缓存文件不存在"})
                continue
            report["checked_codes"] += 1
            sql = f"SELECT COUNT(*) as total, COUNT(*) - COUNT(close) as null_close FROM read_parquet('{file_path}')"
            result = self.query(sql)
            if result["data"]:
                total, null_close = result["data"][0]
                if null_close and null_close > 0:
                    report["issues"].append({"code": code, "issue": "null_values", "message": f"close 有 {null_close} 个空值"})
                if total == 0:
                    report["issues"].append({"code": code, "issue": "empty_data", "message": "数据为空"})
        report["summary"] = {"total_issues": len(report["issues"])}
        return report


# 全局单例
data_explorer = DataExplorerService()
