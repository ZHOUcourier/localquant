"""技术指标节点 — 基于 pandas_ta 计算各类技术指标"""
import pandas as pd
import pandas_ta as ta
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Type

from backend.plugins.base import BaseWorkNode
from backend.plugins.registry import work_node
from backend.plugins.ui_control import ui


# ────────────────────────── 通用 I/O 模型 ──────────────────────────

class DataFrameIO(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None


# ────────────────────────── 1. MA / EMA ──────────────────────────

@ui(
    period={"input_type": "number_field"},
    ma_type={"input_type": "combobox", "options": ["SMA", "EMA"]},
)
class MAInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    period: int = 20
    ma_type: str = "SMA"


class MAOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None


@work_node(name="MA/EMA 均线", group="03-技术指标", box_color="#2196F3")
class MANode(BaseWorkNode):
    """简单/指数移动平均线"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return MAInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return MAOutput

    def run(self, ctx) -> dict:
        params = self._get_params(ctx)
        df: pd.DataFrame = params.get("data")
        if df is None or df.empty:
            return {"data": pd.DataFrame()}
        period = int(params.get("period", 20))
        ma_type = params.get("ma_type", "SMA").upper()

        result = df.copy()
        if ma_type == "EMA":
            result.ta.ema(length=period, append=True)
        else:
            result.ta.sma(length=period, append=True)
        return {"data": result}

    def _get_params(self, ctx) -> dict:
        """合并连入输入与节点自身参数"""
        if hasattr(ctx, "_pending_inputs") and hasattr(ctx, "_node_id"):
            inputs = ctx._pending_inputs.get(ctx._node_id, {})
            return {**self.__dict__, **{k: v for k, v in inputs.items() if v is not None}}
        return self.__dict__


# ────────────────────────── 2. MACD ──────────────────────────

@ui(
    fast_period={"input_type": "number_field"},
    slow_period={"input_type": "number_field"},
    signal_period={"input_type": "number_field"},
)
class MACDInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    fast_period: int = 12
    slow_period: int = 26
    signal_period: int = 9


class MACDOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None


@work_node(name="MACD", group="03-技术指标", box_color="#2196F3")
class MACDNode(BaseWorkNode):
    """MACD 指标（DIF / DEA / MACD 柱）"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return MACDInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return MACDOutput

    def run(self, ctx) -> dict:
        params = self._get_params(ctx)
        df: pd.DataFrame = params.get("data")
        if df is None or df.empty:
            return {"data": pd.DataFrame()}

        result = df.copy()
        result.ta.macd(
            fast=int(params.get("fast_period", 12)),
            slow=int(params.get("slow_period", 26)),
            signal=int(params.get("signal_period", 9)),
            append=True,
        )
        return {"data": result}

    def _get_params(self, ctx) -> dict:
        if hasattr(ctx, "_pending_inputs") and hasattr(ctx, "_node_id"):
            inputs = ctx._pending_inputs.get(ctx._node_id, {})
            return {**self.__dict__, **{k: v for k, v in inputs.items() if v is not None}}
        return self.__dict__


# ────────────────────────── 3. RSI ──────────────────────────

@ui(period={"input_type": "number_field"})
class RSIInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    period: int = 14


class RSIOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None


@work_node(name="RSI", group="03-技术指标", box_color="#2196F3")
class RSINode(BaseWorkNode):
    """相对强弱指标"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return RSIInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return RSIOutput

    def run(self, ctx) -> dict:
        params = self._get_params(ctx)
        df: pd.DataFrame = params.get("data")
        if df is None or df.empty:
            return {"data": pd.DataFrame()}

        result = df.copy()
        result.ta.rsi(length=int(params.get("period", 14)), append=True)
        return {"data": result}

    def _get_params(self, ctx) -> dict:
        if hasattr(ctx, "_pending_inputs") and hasattr(ctx, "_node_id"):
            inputs = ctx._pending_inputs.get(ctx._node_id, {})
            return {**self.__dict__, **{k: v for k, v in inputs.items() if v is not None}}
        return self.__dict__


# ────────────────────────── 4. KDJ（Stochastic） ──────────────────────────

@ui(period={"input_type": "number_field"})
class KDJInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    period: int = 9


class KDJOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None


@work_node(name="KDJ", group="03-技术指标", box_color="#2196F3")
class KDJNode(BaseWorkNode):
    """KDJ 随机指标（基于 Stochastic）"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return KDJInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return KDJOutput

    def run(self, ctx) -> dict:
        params = self._get_params(ctx)
        df: pd.DataFrame = params.get("data")
        if df is None or df.empty:
            return {"data": pd.DataFrame()}

        period = int(params.get("period", 9))
        result = df.copy()

        # pandas_ta 的 stoch 计算 %K 和 %D
        result.ta.stoch(k=period, d=3, smooth_k=3, append=True)

        # 计算 J 列: J = 3*K - 2*D
        k_cols = [c for c in result.columns if c.upper().startswith("STOCHk") or c.upper().startswith("STOCH_k")]
        d_cols = [c for c in result.columns if c.upper().startswith("STOCHd") or c.upper().startswith("STOCH_d")]
        if k_cols and d_cols:
            result["J"] = 3 * result[k_cols[0]] - 2 * result[d_cols[0]]

        return {"data": result}

    def _get_params(self, ctx) -> dict:
        if hasattr(ctx, "_pending_inputs") and hasattr(ctx, "_node_id"):
            inputs = ctx._pending_inputs.get(ctx._node_id, {})
            return {**self.__dict__, **{k: v for k, v in inputs.items() if v is not None}}
        return self.__dict__


# ────────────────────────── 5. BOLL（布林带） ──────────────────────────

@ui(
    period={"input_type": "number_field"},
    std_dev={"input_type": "number_field"},
)
class BOLLInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    period: int = 20
    std_dev: float = 2.0


class BOLLOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None


@work_node(name="BOLL 布林带", group="03-技术指标", box_color="#2196F3")
class BOLLNode(BaseWorkNode):
    """布林带指标"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return BOLLInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return BOLLOutput

    def run(self, ctx) -> dict:
        params = self._get_params(ctx)
        df: pd.DataFrame = params.get("data")
        if df is None or df.empty:
            return {"data": pd.DataFrame()}

        result = df.copy()
        result.ta.bbands(
            length=int(params.get("period", 20)),
            std=float(params.get("std_dev", 2.0)),
            append=True,
        )
        return {"data": result}

    def _get_params(self, ctx) -> dict:
        if hasattr(ctx, "_pending_inputs") and hasattr(ctx, "_node_id"):
            inputs = ctx._pending_inputs.get(ctx._node_id, {})
            return {**self.__dict__, **{k: v for k, v in inputs.items() if v is not None}}
        return self.__dict__


# ────────────────────────── 6. ATR ──────────────────────────

@ui(period={"input_type": "number_field"})
class ATRInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    period: int = 14


class ATROutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None


@work_node(name="ATR", group="03-技术指标", box_color="#2196F3")
class ATRNode(BaseWorkNode):
    """平均真实波幅"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return ATRInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return ATROutput

    def run(self, ctx) -> dict:
        params = self._get_params(ctx)
        df: pd.DataFrame = params.get("data")
        if df is None or df.empty:
            return {"data": pd.DataFrame()}

        result = df.copy()
        result.ta.atr(length=int(params.get("period", 14)), append=True)
        return {"data": result}

    def _get_params(self, ctx) -> dict:
        if hasattr(ctx, "_pending_inputs") and hasattr(ctx, "_node_id"):
            inputs = ctx._pending_inputs.get(ctx._node_id, {})
            return {**self.__dict__, **{k: v for k, v in inputs.items() if v is not None}}
        return self.__dict__


# ────────────────────────── 7. 自定义公式 ──────────────────────────

@ui(formula={"input_type": "code_editor", "language": "python"})
class CustomFormulaInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    formula: str = "df['close'] * 2"
    output_col: str = "custom"


class CustomFormulaOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None


@work_node(name="自定义公式指标", group="03-技术指标", box_color="#2196F3")
class CustomFormulaNode(BaseWorkNode):
    """基于自定义公式计算指标"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return CustomFormulaInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return CustomFormulaOutput

    def run(self, ctx) -> dict:
        params = self._get_params(ctx)
        df: pd.DataFrame = params.get("data")
        if df is None or df.empty:
            return {"data": pd.DataFrame()}

        formula = params.get("formula", "")
        output_col = params.get("output_col", "custom")
        if not formula:
            return {"data": df.copy()}

        result = df.copy()
        # 提供 df 和常用列作为上下文
        eval_ctx = {"df": result, "ta": ta}
        # 把常用列直接暴露
        for col in result.columns:
            eval_ctx[col.lower()] = result[col]

        try:
            expr_result = eval(formula, {"__builtins__": {}}, eval_ctx)  # noqa: S307
            if isinstance(expr_result, pd.Series):
                result[output_col] = expr_result
            else:
                result[output_col] = expr_result
        except Exception as e:
            result[output_col] = float("nan")

        return {"data": result}

    def _get_params(self, ctx) -> dict:
        if hasattr(ctx, "_pending_inputs") and hasattr(ctx, "_node_id"):
            inputs = ctx._pending_inputs.get(ctx._node_id, {})
            return {**self.__dict__, **{k: v for k, v in inputs.items() if v is not None}}
        return self.__dict__
