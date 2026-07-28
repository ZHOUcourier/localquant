"""Parquet 本地缓存管理

存储结构: data/cache/{period}/{code}.parquet
支持增量追加、去重合并、缓存统计。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd
from loguru import logger

from backend.config import settings


class DataCache:
    """基于 Parquet 的本地数据缓存"""

    def __init__(self, cache_dir: Optional[Path] = None):
        self._cache_dir = cache_dir or settings.cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    # ── 路径 ─────────────────────────────────────────────────

    def _get_path(self, code: str, period: str) -> Path:
        """获取缓存文件路径（code 中 '.' 替换为 '_'）"""
        safe_code = code.replace(".", "_")
        period_dir = self._cache_dir / period
        period_dir.mkdir(parents=True, exist_ok=True)
        return period_dir / f"{safe_code}.parquet"

    # ── 读取 ─────────────────────────────────────────────────

    def get(self, code: str, period: str) -> Optional[pd.DataFrame]:
        """读取缓存数据，不存在则返回 None"""
        path = self._get_path(code, period)
        if not path.exists():
            return None
        try:
            df = pd.read_parquet(path)
            return df
        except Exception as e:
            logger.warning(f"Failed to read cache {path}: {e}")
            return None

    # ── 写入 ─────────────────────────────────────────────────

    def save(self, code: str, period: str, df: pd.DataFrame):
        """保存 DataFrame 到 Parquet 缓存"""
        if df.empty:
            return
        path = self._get_path(code, period)
        try:
            df.to_parquet(path, engine="pyarrow", index=True)
            logger.debug(f"Cache saved: {path} ({len(df)} rows)")
        except Exception as e:
            logger.warning(f"Failed to save cache {path}: {e}")

    # ── 增量更新 ─────────────────────────────────────────────

    def get_or_append(self, code: str, period: str, new_df: pd.DataFrame) -> pd.DataFrame:
        """增量更新：合并新数据并去重

        如果已有缓存，合并后按索引去重（保留最新）；
        如果无缓存，直接保存新数据。
        """
        if new_df.empty:
            existing = self.get(code, period)
            return existing if existing is not None else pd.DataFrame()

        existing = self.get(code, period)
        if existing is None:
            self.save(code, period, new_df)
            return new_df.copy()

        # 合并并按索引去重（保留后面的新数据）
        combined = pd.concat([existing, new_df])
        combined = combined[~combined.index.duplicated(keep="last")]
        combined = combined.sort_index()
        self.save(code, period, combined)
        return combined.copy()

    # ── 查询 ─────────────────────────────────────────────────

    def get_latest_timestamp(self, code: str, period: str) -> Optional[str]:
        """获取缓存中最新一条数据的时间戳（字符串形式）"""
        df = self.get(code, period)
        if df is None or df.empty:
            return None
        try:
            latest = df.index[-1]
            return str(latest)
        except Exception:
            return None

    # ── 失效 ─────────────────────────────────────────────────

    def invalidate(self, code: str, period: str):
        """删除指定缓存文件"""
        path = self._get_path(code, period)
        if path.exists():
            try:
                path.unlink()
                logger.info(f"Cache invalidated: {path}")
            except Exception as e:
                logger.warning(f"Failed to invalidate cache {path}: {e}")

    # ── 统计 ─────────────────────────────────────────────────

    def cache_status(self) -> dict:
        """统计缓存状态：文件数、总大小、按周期分组"""
        total_files = 0
        total_size = 0
        by_period: dict[str, dict] = {}

        if not self._cache_dir.exists():
            return {"total_files": 0, "total_size_bytes": 0, "by_period": {}}

        for period_dir in sorted(self._cache_dir.iterdir()):
            if not period_dir.is_dir():
                continue
            period_name = period_dir.name
            files = list(period_dir.glob("*.parquet"))
            if not files:
                continue
            dir_size = sum(f.stat().st_size for f in files if f.exists())
            by_period[period_name] = {
                "files": len(files),
                "size_bytes": dir_size,
            }
            total_files += len(files)
            total_size += dir_size

        return {
            "total_files": total_files,
            "total_size_bytes": total_size,
            "by_period": by_period,
        }
