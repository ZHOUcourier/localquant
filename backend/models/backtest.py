"""回测 Pydantic 模型"""
from pydantic import BaseModel, Field
from typing import Optional


class BacktestRequest(BaseModel):
    """回测请求"""
    signals: dict  # {date: {code: signal}}
    prices: dict  # {date: {code: price}}
    initial_capital: float = 1000000
    commission_rate: float = 0.001
    slippage: float = 0.001
    benchmark: str = "000300.SH"
    start_date: str = ""
    end_date: str = ""


class BacktestResult(BaseModel):
    """回测结果"""
    total_return: float
    annual_return: float
    max_drawdown: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    volatility: float
    win_rate: float
    profit_loss_ratio: float
    total_trades: int
    # 详细数据路径（存文件）
    equity_curve_path: Optional[str] = None
    trades_path: Optional[str] = None
    monthly_returns_path: Optional[str] = None
