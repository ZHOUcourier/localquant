"""QMT 数据客户端 — xtquant.xtdata 封装

xtquant 仅 Windows 可用，macOS/Linux 开发环境下自动降级为未连接状态。
所有方法在未连接时调用会抛出 ConnectionError，不会导致进程崩溃。
"""
from __future__ import annotations

from typing import Any, Callable, Optional

import pandas as pd
from loguru import logger


class QMTClient:
    """QMT 数据客户端，封装 xtquant.xtdata 接口"""

    def __init__(self):
        self._xtdata: Any = None
        self._connected: bool = False
        self._try_connect()

    # ── 连接管理 ─────────────────────────────────────────────

    def _try_connect(self):
        """尝试导入 xtquant 并连接 QMT 客户端"""
        try:
            from xtquant import xtdata  # type: ignore[import-untyped]

            # 尝试建立连接（QMT 客户端未启动时会抛异常）
            xtdata.connect()
            self._xtdata = xtdata
            self._connected = True
            logger.info("QMT xtdata connected successfully")
        except ImportError:
            logger.warning(
                "xtquant not installed — QMT data source unavailable "
                "(only available on Windows with QMT client)"
            )
            self._connected = False
        except Exception as e:
            logger.warning(f"QMT xtdata connection failed: {e}")
            self._connected = False

    @property
    def connected(self) -> bool:
        """当前是否已连接到 QMT"""
        return self._connected

    def check_connection(self) -> dict:
        """返回连接状态信息"""
        if self._connected:
            return {"connected": True, "message": "QMT xtdata 已连接"}
        return {
            "connected": False,
            "message": "QMT 未连接（xtquant 未安装或 QMT 客户端未启动）",
        }

    def _ensure_connected(self):
        """确保已连接，否则抛出异常"""
        if not self._connected:
            raise ConnectionError(
                "QMT 未连接 — xtquant 仅 Windows 可用，"
                "请确保已安装 xtquant 并启动 QMT 客户端"
            )

    # ── K 线数据 ─────────────────────────────────────────────

    def get_kline(
        self,
        codes: list[str],
        period: str = "1d",
        start_time: str = "",
        end_time: str = "",
        count: int = -1,
        dividend_type: str = "front",
    ) -> dict[str, pd.DataFrame]:
        """获取 K 线数据

        Args:
            codes: 合约代码列表，如 ["000001.SZ", "600000.SH"]
            period: 周期（1m/5m/15m/30m/1h/1d/1w/1mon）
            start_time: 开始时间，如 "20240101" 或 "20240101093000"
            end_time: 结束时间
            count: 数据条数，-1 返回全部
            dividend_type: 复权类型（none/front/back/forward/backward）

        Returns:
            {stock_code: DataFrame} 字典
        """
        self._ensure_connected()
        result: dict[str, pd.DataFrame] = {}
        try:
            data = self._xtdata.get_market_data_ex(
                stock_list=codes,
                period=period,
                start_time=start_time,
                end_time=end_time,
                count=count,
                dividend_type=dividend_type,
            )
            if isinstance(data, dict):
                for code, df in data.items():
                    if isinstance(df, pd.DataFrame) and not df.empty:
                        result[code] = df
        except Exception as e:
            logger.warning(f"Failed to get kline data: {e}")
        return result

    # ── 财务数据 ─────────────────────────────────────────────

    def get_financial(
        self,
        codes: list[str],
        tables: list[str] | None = None,
        start_time: str = "",
        end_time: str = "",
    ) -> dict:
        """获取财务数据

        Args:
            codes: 合约代码列表
            tables: 财务表名列表
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            {stock_code: DataFrame} 字典
        """
        self._ensure_connected()
        result: dict = {}
        try:
            data = self._xtdata.get_financial_data(
                stock_list=codes,
                table_list=tables or [],
                start_time=start_time,
                end_time=end_time,
            )
            if isinstance(data, dict):
                result = data
        except Exception as e:
            logger.warning(f"Failed to get financial data: {e}")
        return result

    # ── 板块 ─────────────────────────────────────────────────

    def get_sector_list(self) -> list[str]:
        """获取板块列表"""
        self._ensure_connected()
        try:
            sectors = self._xtdata.get_sector_list()
            return sectors if isinstance(sectors, list) else []
        except Exception as e:
            logger.warning(f"Failed to get sector list: {e}")
            return []

    def get_sector_stocks(self, sector: str) -> list[str]:
        """获取板块成分股"""
        self._ensure_connected()
        try:
            stocks = self._xtdata.get_stock_list_in_sector(sector)
            return stocks if isinstance(stocks, list) else []
        except Exception as e:
            logger.warning(f"Failed to get sector stocks for '{sector}': {e}")
            return []

    # ── 合约详情 ─────────────────────────────────────────────

    def get_instrument_detail(self, codes: list[str]) -> dict[str, dict]:
        """获取合约详细信息"""
        self._ensure_connected()
        result: dict[str, dict] = {}
        try:
            for code in codes:
                detail = self._xtdata.get_instrument_detail(code)
                if isinstance(detail, dict):
                    result[code] = detail
        except Exception as e:
            logger.warning(f"Failed to get instrument detail: {e}")
        return result

    # ── 交易日 ───────────────────────────────────────────────

    def get_trading_dates(
        self,
        market: str = "SH",
        start_time: str = "",
        end_time: str = "",
    ) -> list[str]:
        """获取交易日列表"""
        self._ensure_connected()
        try:
            dates = self._xtdata.get_trading_dates(
                market=market,
                start_time=start_time,
                end_time=end_time,
            )
            return dates if isinstance(dates, list) else []
        except Exception as e:
            logger.warning(f"Failed to get trading dates: {e}")
            return []

    # ── 下载历史 ─────────────────────────────────────────────

    def download_history(
        self,
        codes: list[str],
        period: str = "1d",
        start_time: str = "",
        end_time: str = "",
        callback: Optional[Callable] = None,
    ):
        """下载历史数据到本地"""
        self._ensure_connected()
        try:
            self._xtdata.download_history_data(
                stock_list=codes,
                period=period,
                start_time=start_time,
                end_time=end_time,
                callback=callback,
            )
        except Exception as e:
            logger.warning(f"Failed to download history: {e}")

    # ── 实时行情 ─────────────────────────────────────────────

    def subscribe_realtime(self, codes: list[str], callback: Optional[Callable] = None) -> int:
        """订阅实时行情

        Returns:
            订阅 ID，0 表示失败
        """
        self._ensure_connected()
        try:
            seq = self._xtdata.subscribe_quote(
                stock_list=codes,
                period="tick",
                callback=callback,
            )
            return seq if isinstance(seq, int) else 0
        except Exception as e:
            logger.warning(f"Failed to subscribe realtime: {e}")
            return 0

    def get_full_tick(self, codes: list[str]) -> dict:
        """获取最新 Tick 快照"""
        self._ensure_connected()
        result: dict = {}
        try:
            data = self._xtdata.get_full_tick(stock_list=codes)
            if isinstance(data, dict):
                result = data
        except Exception as e:
            logger.warning(f"Failed to get full tick: {e}")
        return result
