"""机器学习模型节点 — MLP/RF/LGBM/XGB/GRU/SVM/LSTM/CNN/Transformer/GNN/Optuna"""

from typing import Optional, Type

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from backend.plugins.base import BaseWorkNode
from backend.plugins.registry import work_node
from backend.plugins.ui_control import ui

# ────────────────────────── 通用 I/O 模型 ──────────────────────────


class MLTrainInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    target_col: str = Field(default="target", title="目标列")
    feature_cols: str = Field(default="", title="特征列(逗号分隔，留空=全部数值列)")
    test_ratio: float = Field(default=0.2, title="测试集比例")


class MLPredictionOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    predictions: list = Field(default_factory=list, title="预测结果")
    metrics: dict = Field(default_factory=dict, title="评估指标")


def _prepare_xy(df: pd.DataFrame, feature_cols: str, target_col: str):
    """从 DataFrame 准备 X, y"""
    if df is None or df.empty:
        return None, None, []
    if feature_cols.strip():
        fcols = [c.strip() for c in feature_cols.split(",") if c.strip()]
        fcols = [c for c in fcols if c in df.columns]
    else:
        fcols = df.select_dtypes(include=[np.number]).columns.tolist()
    fcols = [c for c in fcols if c != target_col]
    if target_col not in df.columns or not fcols:
        return None, None, fcols
    X = df[fcols].astype(float).values
    y = df[target_col].astype(float).values
    return X, y, fcols


def _split_data(X, y, test_ratio: float):
    """简单切分训练/测试集"""
    n = len(X)
    split = int(n * (1 - test_ratio))
    return X[:split], X[split:], y[:split], y[split:]


def _regression_metrics(y_true, y_pred):
    """回归评估指标"""
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

    return {
        "mse": float(mean_squared_error(y_true, y_pred)),
        "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "r2": float(r2_score(y_true, y_pred)),
    }


def _classification_metrics(y_true, y_pred):
    """分类评估指标"""
    from sklearn.metrics import accuracy_score, f1_score

    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "f1": float(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
    }


# ============================================================
# 9. MLP模型节点
# ============================================================


@ui(
    target_col={"input_type": "text_field"},
    hidden_layers={"input_type": "text_field", "placeholder": "隐藏层结构，如 64,32"},
    max_iter={"input_type": "number_field"},
    task_type={"input_type": "combobox", "options": ["regression", "classification"]},
    data={"input_type": "None"},
)
class MLPInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    target_col: str = "target"
    feature_cols: str = ""
    test_ratio: float = 0.2
    hidden_layers: str = "64,32"
    max_iter: int = 500
    task_type: str = "regression"


@work_node(
    name="MLP模型",
    group="07-机器学习",
    box_color="#E91E63",
    description="多层感知机神经网络，适用于非线性回归与分类任务",
)
class MLPNode(BaseWorkNode):
    """多层感知机模型"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return MLPInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return MLPredictionOutput

    def run(self, input: MLPInput) -> Optional[BaseModel]:
        try:
            from sklearn.neural_network import MLPClassifier, MLPRegressor
        except ImportError:
            return MLPredictionOutput(
                data=pd.DataFrame(),
                predictions=[],
                metrics={"error": "请安装 scikit-learn: pip install scikit-learn"},
            )

        X, y, fcols = _prepare_xy(input.data, input.feature_cols, input.target_col)
        if X is None:
            return MLPredictionOutput(
                data=pd.DataFrame(), predictions=[], metrics={"error": "数据准备失败"}
            )

        X_train, X_test, y_train, y_test = _split_data(X, y, input.test_ratio)
        layers = tuple(
            int(l.strip()) for l in input.hidden_layers.split(",") if l.strip()
        )

        if input.task_type == "classification":
            model = MLPClassifier(
                hidden_layer_sizes=layers, max_iter=input.max_iter, random_state=42
            )
        else:
            model = MLPRegressor(
                hidden_layer_sizes=layers, max_iter=input.max_iter, random_state=42
            )
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)

        metrics = (
            _classification_metrics(y_test, y_pred)
            if input.task_type == "classification"
            else _regression_metrics(y_test, y_pred)
        )
        return MLPredictionOutput(
            data=input.data, predictions=y_pred.tolist(), metrics=metrics
        )


# ============================================================
# 10. 随机森林模型节点
# ============================================================


@ui(
    target_col={"input_type": "text_field"},
    n_estimators={"input_type": "number_field"},
    max_depth={"input_type": "number_field"},
    task_type={"input_type": "combobox", "options": ["regression", "classification"]},
    data={"input_type": "None"},
)
class RFInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    target_col: str = "target"
    feature_cols: str = ""
    test_ratio: float = 0.2
    n_estimators: int = 100
    max_depth: int = 0  # 0 = None
    task_type: str = "regression"


@work_node(
    name="随机森林模型",
    group="07-机器学习",
    box_color="#E91E63",
    description="基于集成学习的随机森林，抗过拟合能力强",
)
class RFNode(BaseWorkNode):
    """随机森林模型"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return RFInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return MLPredictionOutput

    def run(self, input: RFInput) -> Optional[BaseModel]:
        try:
            from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
        except ImportError:
            return MLPredictionOutput(
                data=pd.DataFrame(),
                predictions=[],
                metrics={"error": "请安装 scikit-learn"},
            )

        X, y, fcols = _prepare_xy(input.data, input.feature_cols, input.target_col)
        if X is None:
            return MLPredictionOutput(
                data=pd.DataFrame(), predictions=[], metrics={"error": "数据准备失败"}
            )

        X_train, X_test, y_train, y_test = _split_data(X, y, input.test_ratio)
        depth = input.max_depth if input.max_depth > 0 else None

        if input.task_type == "classification":
            model = RandomForestClassifier(
                n_estimators=input.n_estimators, max_depth=depth, random_state=42
            )
        else:
            model = RandomForestRegressor(
                n_estimators=input.n_estimators, max_depth=depth, random_state=42
            )
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)

        metrics = (
            _classification_metrics(y_test, y_pred)
            if input.task_type == "classification"
            else _regression_metrics(y_test, y_pred)
        )
        # 特征重要度
        importances = dict(zip(fcols, [float(x) for x in model.feature_importances_]))
        metrics["feature_importances"] = importances
        return MLPredictionOutput(
            data=input.data, predictions=y_pred.tolist(), metrics=metrics
        )


# ============================================================
# 11. LightGBM模型节点
# ============================================================


@ui(
    target_col={"input_type": "text_field"},
    n_estimators={"input_type": "number_field"},
    learning_rate={"input_type": "number_field"},
    task_type={"input_type": "combobox", "options": ["regression", "classification"]},
    data={"input_type": "None"},
)
class LGBMInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    target_col: str = "target"
    feature_cols: str = ""
    test_ratio: float = 0.2
    n_estimators: int = 100
    learning_rate: float = 0.1
    num_leaves: int = 31
    task_type: str = "regression"


@work_node(
    name="LightGBM模型",
    group="07-机器学习",
    box_color="#E91E63",
    description="基于梯度提升树的高效模型，训练速度快",
)
class LGBMNode(BaseWorkNode):
    """LightGBM 梯度提升树模型"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return LGBMInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return MLPredictionOutput

    def run(self, input: LGBMInput) -> Optional[BaseModel]:
        try:
            import lightgbm as lgb
        except ImportError:
            return MLPredictionOutput(
                data=pd.DataFrame(),
                predictions=[],
                metrics={"error": "请安装 lightgbm: pip install lightgbm"},
            )

        X, y, fcols = _prepare_xy(input.data, input.feature_cols, input.target_col)
        if X is None:
            return MLPredictionOutput(
                data=pd.DataFrame(), predictions=[], metrics={"error": "数据准备失败"}
            )

        X_train, X_test, y_train, y_test = _split_data(X, y, input.test_ratio)
        params = {
            "n_estimators": input.n_estimators,
            "learning_rate": input.learning_rate,
            "num_leaves": input.num_leaves,
            "random_state": 42,
            "verbose": -1,
        }

        if input.task_type == "classification":
            model = lgb.LGBMClassifier(**params)
        else:
            model = lgb.LGBMRegressor(**params)
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)

        metrics = (
            _classification_metrics(y_test, y_pred)
            if input.task_type == "classification"
            else _regression_metrics(y_test, y_pred)
        )
        return MLPredictionOutput(
            data=input.data, predictions=y_pred.tolist(), metrics=metrics
        )


# ============================================================
# 12. XGBoost模型节点
# ============================================================


@ui(
    target_col={"input_type": "text_field"},
    n_estimators={"input_type": "number_field"},
    learning_rate={"input_type": "number_field"},
    max_depth={"input_type": "number_field"},
    task_type={"input_type": "combobox", "options": ["regression", "classification"]},
    data={"input_type": "None"},
)
class XGBInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    target_col: str = "target"
    feature_cols: str = ""
    test_ratio: float = 0.2
    n_estimators: int = 100
    learning_rate: float = 0.1
    max_depth: int = 6
    task_type: str = "regression"


@work_node(
    name="XGBoost模型",
    group="07-机器学习",
    box_color="#E91E63",
    description="极端梯度提升树，量化投资常用模型",
)
class XGBNode(BaseWorkNode):
    """XGBoost 模型"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return XGBInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return MLPredictionOutput

    def run(self, input: XGBInput) -> Optional[BaseModel]:
        try:
            import xgboost as xgb
        except ImportError:
            return MLPredictionOutput(
                data=pd.DataFrame(),
                predictions=[],
                metrics={"error": "请安装 xgboost: pip install xgboost"},
            )

        X, y, fcols = _prepare_xy(input.data, input.feature_cols, input.target_col)
        if X is None:
            return MLPredictionOutput(
                data=pd.DataFrame(), predictions=[], metrics={"error": "数据准备失败"}
            )

        X_train, X_test, y_train, y_test = _split_data(X, y, input.test_ratio)

        if input.task_type == "classification":
            model = xgb.XGBClassifier(
                n_estimators=input.n_estimators,
                learning_rate=input.learning_rate,
                max_depth=input.max_depth,
                random_state=42,
                verbosity=0,
            )
        else:
            model = xgb.XGBRegressor(
                n_estimators=input.n_estimators,
                learning_rate=input.learning_rate,
                max_depth=input.max_depth,
                random_state=42,
                verbosity=0,
            )
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)

        metrics = (
            _classification_metrics(y_test, y_pred)
            if input.task_type == "classification"
            else _regression_metrics(y_test, y_pred)
        )
        return MLPredictionOutput(
            data=input.data, predictions=y_pred.tolist(), metrics=metrics
        )


# ============================================================
# 13. GRU模型节点
# ============================================================


@ui(
    target_col={"input_type": "text_field"},
    hidden_size={"input_type": "number_field"},
    num_layers={"input_type": "number_field"},
    seq_len={"input_type": "number_field"},
    epochs={"input_type": "number_field"},
    data={"input_type": "None"},
)
class GRUInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    target_col: str = "target"
    feature_cols: str = ""
    test_ratio: float = 0.2
    hidden_size: int = 64
    num_layers: int = 2
    seq_len: int = 10
    epochs: int = 50
    learning_rate: float = 0.001


@work_node(
    name="GRU模型",
    group="07-机器学习",
    box_color="#E91E63",
    description="门控循环单元，适合时序数据建模",
)
class GRUNode(BaseWorkNode):
    """GRU 循环神经网络模型"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return GRUInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return MLPredictionOutput

    def run(self, input: GRUInput) -> Optional[BaseModel]:
        try:
            import torch
            import torch.nn as nn
        except ImportError:
            return MLPredictionOutput(
                data=pd.DataFrame(),
                predictions=[],
                metrics={"error": "请安装 PyTorch: pip install torch"},
            )

        df = input.data
        if df is None or df.empty:
            return MLPredictionOutput(
                data=pd.DataFrame(), predictions=[], metrics={"error": "输入数据为空"}
            )

        # 准备特征
        if input.feature_cols.strip():
            fcols = [c.strip() for c in input.feature_cols.split(",") if c.strip()]
            fcols = [c for c in fcols if c in df.columns]
        else:
            fcols = df.select_dtypes(include=[np.number]).columns.tolist()
        fcols = [c for c in fcols if c != input.target_col]

        if input.target_col not in df.columns or not fcols:
            return MLPredictionOutput(
                data=pd.DataFrame(),
                predictions=[],
                metrics={"error": "目标列或特征列无效"},
            )

        values = df[fcols].astype(float).values
        target = df[input.target_col].astype(float).values

        # 构造序列样本
        seq_len = input.seq_len
        n_features = len(fcols)
        X_seq, y_seq = [], []
        for i in range(len(values) - seq_len):
            X_seq.append(values[i : i + seq_len])
            y_seq.append(target[i + seq_len])
        if not X_seq:
            return MLPredictionOutput(
                data=pd.DataFrame(), predictions=[], metrics={"error": "序列长度不足"}
            )

        X_arr = np.array(X_seq, dtype=np.float32)
        y_arr = np.array(y_seq, dtype=np.float32)
        split = int(len(X_arr) * (1 - input.test_ratio))
        X_train, X_test = X_arr[:split], X_arr[split:]
        y_train, y_test = y_arr[:split], y_arr[split:]

        class GRUModel(nn.Module):
            def __init__(self, n_feat, hidden, n_layers):
                super().__init__()
                self.gru = nn.GRU(n_feat, hidden, n_layers, batch_first=True)
                self.fc = nn.Linear(hidden, 1)

            def forward(self, x):
                out, _ = self.gru(x)
                return self.fc(out[:, -1, :]).squeeze(-1)

        model = GRUModel(n_features, input.hidden_size, input.num_layers)
        optimizer = torch.optim.Adam(model.parameters(), lr=input.learning_rate)
        criterion = nn.MSELoss()

        X_t = torch.tensor(X_train)
        y_t = torch.tensor(y_train)
        model.train()
        for _ in range(input.epochs):
            optimizer.zero_grad()
            loss = criterion(model(X_t), y_t)
            loss.backward()
            optimizer.step()

        model.eval()
        with torch.no_grad():
            y_pred = model(torch.tensor(X_test)).numpy()

        metrics = _regression_metrics(y_test, y_pred)
        return MLPredictionOutput(data=df, predictions=y_pred.tolist(), metrics=metrics)


# ============================================================
# 14. SVM模型节点
# ============================================================


@ui(
    target_col={"input_type": "text_field"},
    kernel={"input_type": "combobox", "options": ["rbf", "linear", "poly", "sigmoid"]},
    C={"input_type": "number_field"},
    task_type={"input_type": "combobox", "options": ["regression", "classification"]},
    data={"input_type": "None"},
)
class SVMInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    target_col: str = "target"
    feature_cols: str = ""
    test_ratio: float = 0.2
    kernel: str = "rbf"
    C: float = 1.0
    task_type: str = "regression"


@work_node(
    name="SVM模型",
    group="07-机器学习",
    box_color="#E91E63",
    description="支持向量机，适合小样本分类与回归",
)
class SVMNode(BaseWorkNode):
    """支持向量机模型"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return SVMInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return MLPredictionOutput

    def run(self, input: SVMInput) -> Optional[BaseModel]:
        try:
            from sklearn.svm import SVC, SVR
        except ImportError:
            return MLPredictionOutput(
                data=pd.DataFrame(),
                predictions=[],
                metrics={"error": "请安装 scikit-learn"},
            )

        X, y, fcols = _prepare_xy(input.data, input.feature_cols, input.target_col)
        if X is None:
            return MLPredictionOutput(
                data=pd.DataFrame(), predictions=[], metrics={"error": "数据准备失败"}
            )

        X_train, X_test, y_train, y_test = _split_data(X, y, input.test_ratio)

        if input.task_type == "classification":
            model = SVC(kernel=input.kernel, C=input.C, random_state=42)
        else:
            model = SVR(kernel=input.kernel, C=input.C)
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)

        metrics = (
            _classification_metrics(y_test, y_pred)
            if input.task_type == "classification"
            else _regression_metrics(y_test, y_pred)
        )
        return MLPredictionOutput(
            data=input.data, predictions=y_pred.tolist(), metrics=metrics
        )


# ============================================================
# 15. LSTM模型节点
# ============================================================


@ui(
    target_col={"input_type": "text_field"},
    hidden_size={"input_type": "number_field"},
    num_layers={"input_type": "number_field"},
    seq_len={"input_type": "number_field"},
    epochs={"input_type": "number_field"},
    data={"input_type": "None"},
)
class LSTMInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    target_col: str = "target"
    feature_cols: str = ""
    test_ratio: float = 0.2
    hidden_size: int = 64
    num_layers: int = 2
    seq_len: int = 10
    epochs: int = 50
    learning_rate: float = 0.001


@work_node(
    name="LSTM模型",
    group="07-机器学习",
    box_color="#E91E63",
    description="长短期记忆网络，捕捉时序长期依赖",
)
class LSTMNode(BaseWorkNode):
    """LSTM 长短期记忆网络模型"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return LSTMInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return MLPredictionOutput

    def run(self, input: LSTMInput) -> Optional[BaseModel]:
        try:
            import torch
            import torch.nn as nn
        except ImportError:
            return MLPredictionOutput(
                data=pd.DataFrame(),
                predictions=[],
                metrics={"error": "请安装 PyTorch: pip install torch"},
            )

        df = input.data
        if df is None or df.empty:
            return MLPredictionOutput(
                data=pd.DataFrame(), predictions=[], metrics={"error": "输入数据为空"}
            )

        if input.feature_cols.strip():
            fcols = [c.strip() for c in input.feature_cols.split(",") if c.strip()]
            fcols = [c for c in fcols if c in df.columns]
        else:
            fcols = df.select_dtypes(include=[np.number]).columns.tolist()
        fcols = [c for c in fcols if c != input.target_col]

        if input.target_col not in df.columns or not fcols:
            return MLPredictionOutput(
                data=pd.DataFrame(),
                predictions=[],
                metrics={"error": "目标列或特征列无效"},
            )

        values = df[fcols].astype(float).values
        target = df[input.target_col].astype(float).values
        seq_len = input.seq_len

        X_seq, y_seq = [], []
        for i in range(len(values) - seq_len):
            X_seq.append(values[i : i + seq_len])
            y_seq.append(target[i + seq_len])
        if not X_seq:
            return MLPredictionOutput(
                data=pd.DataFrame(), predictions=[], metrics={"error": "序列长度不足"}
            )

        X_arr = np.array(X_seq, dtype=np.float32)
        y_arr = np.array(y_seq, dtype=np.float32)
        split = int(len(X_arr) * (1 - input.test_ratio))

        class LSTMModel(nn.Module):
            def __init__(self, n_feat, hidden, n_layers):
                super().__init__()
                self.lstm = nn.LSTM(n_feat, hidden, n_layers, batch_first=True)
                self.fc = nn.Linear(hidden, 1)

            def forward(self, x):
                out, _ = self.lstm(x)
                return self.fc(out[:, -1, :]).squeeze(-1)

        n_features = len(fcols)
        model = LSTMModel(n_features, input.hidden_size, input.num_layers)
        optimizer = torch.optim.Adam(model.parameters(), lr=input.learning_rate)
        criterion = nn.MSELoss()

        X_t = torch.tensor(X_arr[:split])
        y_t = torch.tensor(y_arr[:split])
        model.train()
        for _ in range(input.epochs):
            optimizer.zero_grad()
            loss = criterion(model(X_t), y_t)
            loss.backward()
            optimizer.step()

        model.eval()
        with torch.no_grad():
            y_pred = model(torch.tensor(X_arr[split:])).numpy()
        y_test = y_arr[split:]

        metrics = _regression_metrics(y_test, y_pred)
        return MLPredictionOutput(data=df, predictions=y_pred.tolist(), metrics=metrics)


# ============================================================
# 16. CNN模型节点
# ============================================================


@ui(
    target_col={"input_type": "text_field"},
    seq_len={"input_type": "number_field"},
    epochs={"input_type": "number_field"},
    data={"input_type": "None"},
)
class CNNInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    target_col: str = "target"
    feature_cols: str = ""
    test_ratio: float = 0.2
    seq_len: int = 10
    epochs: int = 50
    learning_rate: float = 0.001
    num_filters: int = 64
    kernel_size: int = 3


@work_node(
    name="CNN模型",
    group="07-机器学习",
    box_color="#E91E63",
    description="卷积神经网络，可提取局部时序模式特征",
)
class CNNNode(BaseWorkNode):
    """CNN 卷积神经网络模型（用于时序特征）"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return CNNInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return MLPredictionOutput

    def run(self, input: CNNInput) -> Optional[BaseModel]:
        try:
            import torch
            import torch.nn as nn
        except ImportError:
            return MLPredictionOutput(
                data=pd.DataFrame(),
                predictions=[],
                metrics={"error": "请安装 PyTorch: pip install torch"},
            )

        df = input.data
        if df is None or df.empty:
            return MLPredictionOutput(
                data=pd.DataFrame(), predictions=[], metrics={"error": "输入数据为空"}
            )

        if input.feature_cols.strip():
            fcols = [c.strip() for c in input.feature_cols.split(",") if c.strip()]
            fcols = [c for c in fcols if c in df.columns]
        else:
            fcols = df.select_dtypes(include=[np.number]).columns.tolist()
        fcols = [c for c in fcols if c != input.target_col]

        if input.target_col not in df.columns or not fcols:
            return MLPredictionOutput(
                data=pd.DataFrame(),
                predictions=[],
                metrics={"error": "目标列或特征列无效"},
            )

        values = df[fcols].astype(float).values
        target = df[input.target_col].astype(float).values
        seq_len = input.seq_len

        X_seq, y_seq = [], []
        for i in range(len(values) - seq_len):
            X_seq.append(values[i : i + seq_len])
            y_seq.append(target[i + seq_len])
        if not X_seq:
            return MLPredictionOutput(
                data=pd.DataFrame(), predictions=[], metrics={"error": "序列长度不足"}
            )

        X_arr = np.array(X_seq, dtype=np.float32).transpose(0, 2, 1)  # (N, C, L)
        y_arr = np.array(y_seq, dtype=np.float32)
        split = int(len(X_arr) * (1 - input.test_ratio))

        class CNNModel(nn.Module):
            def __init__(self, n_channels, n_filters, k_size, seq_length):
                super().__init__()
                padding = (k_size - 1) // 2
                self.conv1 = nn.Conv1d(n_channels, n_filters, k_size, padding=padding)
                self.relu = nn.ReLU()
                self.pool = nn.AdaptiveAvgPool1d(1)
                self.fc = nn.Linear(n_filters, 1)

            def forward(self, x):
                x = self.relu(self.conv1(x))
                x = self.pool(x).squeeze(-1)
                return self.fc(x).squeeze(-1)

        n_features = len(fcols)
        model = CNNModel(n_features, input.num_filters, input.kernel_size, seq_len)
        optimizer = torch.optim.Adam(model.parameters(), lr=input.learning_rate)
        criterion = nn.MSELoss()

        X_t = torch.tensor(X_arr[:split])
        y_t = torch.tensor(y_arr[:split])
        model.train()
        for _ in range(input.epochs):
            optimizer.zero_grad()
            loss = criterion(model(X_t), y_t)
            loss.backward()
            optimizer.step()

        model.eval()
        with torch.no_grad():
            y_pred = model(torch.tensor(X_arr[split:])).numpy()
        y_test = y_arr[split:]

        metrics = _regression_metrics(y_test, y_pred)
        return MLPredictionOutput(data=df, predictions=y_pred.tolist(), metrics=metrics)


# ============================================================
# 17. Transformer模型节点
# ============================================================


@ui(
    target_col={"input_type": "text_field"},
    seq_len={"input_type": "number_field"},
    d_model={"input_type": "number_field"},
    nhead={"input_type": "number_field"},
    epochs={"input_type": "number_field"},
    data={"input_type": "None"},
)
class TransformerInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    target_col: str = "target"
    feature_cols: str = ""
    test_ratio: float = 0.2
    seq_len: int = 10
    d_model: int = 64
    nhead: int = 4
    num_layers: int = 2
    epochs: int = 50
    learning_rate: float = 0.001


@work_node(
    name="Transformer模型",
    group="07-机器学习",
    box_color="#E91E63",
    description="基于自注意力机制的深度学习模型",
)
class TransformerNode(BaseWorkNode):
    """Transformer 注意力机制模型"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return TransformerInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return MLPredictionOutput

    def run(self, input: TransformerInput) -> Optional[BaseModel]:
        try:
            import torch
            import torch.nn as nn
        except ImportError:
            return MLPredictionOutput(
                data=pd.DataFrame(),
                predictions=[],
                metrics={"error": "请安装 PyTorch: pip install torch"},
            )

        df = input.data
        if df is None or df.empty:
            return MLPredictionOutput(
                data=pd.DataFrame(), predictions=[], metrics={"error": "输入数据为空"}
            )

        if input.feature_cols.strip():
            fcols = [c.strip() for c in input.feature_cols.split(",") if c.strip()]
            fcols = [c for c in fcols if c in df.columns]
        else:
            fcols = df.select_dtypes(include=[np.number]).columns.tolist()
        fcols = [c for c in fcols if c != input.target_col]

        if input.target_col not in df.columns or not fcols:
            return MLPredictionOutput(
                data=pd.DataFrame(),
                predictions=[],
                metrics={"error": "目标列或特征列无效"},
            )

        values = df[fcols].astype(float).values
        target = df[input.target_col].astype(float).values
        seq_len = input.seq_len

        X_seq, y_seq = [], []
        for i in range(len(values) - seq_len):
            X_seq.append(values[i : i + seq_len])
            y_seq.append(target[i + seq_len])
        if not X_seq:
            return MLPredictionOutput(
                data=pd.DataFrame(), predictions=[], metrics={"error": "序列长度不足"}
            )

        X_arr = np.array(X_seq, dtype=np.float32)
        y_arr = np.array(y_seq, dtype=np.float32)
        split = int(len(X_arr) * (1 - input.test_ratio))

        class TransformerModel(nn.Module):
            def __init__(self, n_feat, d_model, nhead, n_layers, seq_length):
                super().__init__()
                self.input_proj = nn.Linear(n_feat, d_model)
                self.pos_encoding = nn.Parameter(
                    torch.randn(1, seq_length, d_model) * 0.02
                )
                encoder_layer = nn.TransformerEncoderLayer(
                    d_model=d_model, nhead=nhead, batch_first=True
                )
                self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=n_layers)
                self.fc = nn.Linear(d_model, 1)

            def forward(self, x):
                x = self.input_proj(x) + self.pos_encoding
                x = self.encoder(x)
                return self.fc(x[:, -1, :]).squeeze(-1)

        n_features = len(fcols)
        model = TransformerModel(
            n_features, input.d_model, input.nhead, input.num_layers, seq_len
        )
        optimizer = torch.optim.Adam(model.parameters(), lr=input.learning_rate)
        criterion = nn.MSELoss()

        X_t = torch.tensor(X_arr[:split])
        y_t = torch.tensor(y_arr[:split])
        model.train()
        for _ in range(input.epochs):
            optimizer.zero_grad()
            loss = criterion(model(X_t), y_t)
            loss.backward()
            optimizer.step()

        model.eval()
        with torch.no_grad():
            y_pred = model(torch.tensor(X_arr[split:])).numpy()
        y_test = y_arr[split:]

        metrics = _regression_metrics(y_test, y_pred)
        return MLPredictionOutput(data=df, predictions=y_pred.tolist(), metrics=metrics)


# ============================================================
# 18. GNN模型节点
# ============================================================


@ui(
    target_col={"input_type": "text_field"},
    hidden_channels={"input_type": "number_field"},
    epochs={"input_type": "number_field"},
    data={"input_type": "None"},
)
class GNNInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    target_col: str = "target"
    feature_cols: str = ""
    test_ratio: float = 0.2
    hidden_channels: int = 64
    epochs: int = 50
    learning_rate: float = 0.01


@work_node(
    name="GNN模型",
    group="07-机器学习",
    box_color="#E91E63",
    description="图神经网络，用于股票关联关系建模",
)
class GNNNode(BaseWorkNode):
    """图神经网络模型（基于 PyG）"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return GNNInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return MLPredictionOutput

    def run(self, input: GNNInput) -> Optional[BaseModel]:
        try:
            import torch
            import torch.nn.functional as F
            from torch_geometric.nn import GCNConv
        except ImportError:
            return MLPredictionOutput(
                data=pd.DataFrame(),
                predictions=[],
                metrics={
                    "error": "请安装 PyTorch 和 PyG: pip install torch torch-geometric"
                },
            )

        df = input.data
        if df is None or df.empty:
            return MLPredictionOutput(
                data=pd.DataFrame(), predictions=[], metrics={"error": "输入数据为空"}
            )

        if input.feature_cols.strip():
            fcols = [c.strip() for c in input.feature_cols.split(",") if c.strip()]
            fcols = [c for c in fcols if c in df.columns]
        else:
            fcols = df.select_dtypes(include=[np.number]).columns.tolist()
        fcols = [c for c in fcols if c != input.target_col]

        if input.target_col not in df.columns or not fcols:
            return MLPredictionOutput(
                data=pd.DataFrame(),
                predictions=[],
                metrics={"error": "目标列或特征列无效"},
            )

        import torch
        import torch.nn.functional as F
        from torch_geometric.data import Data
        from torch_geometric.nn import GCNConv

        x = torch.tensor(df[fcols].astype(float).values, dtype=torch.float)
        y = torch.tensor(df[input.target_col].astype(float).values, dtype=torch.float)

        # 构建全连接图（简化处理，实际应基于股票关系构建邻接矩阵）
        n = x.size(0)
        edge_index = torch.combinations(torch.arange(n), r=2).t()
        # 对于大数据集，限制边数
        if edge_index.size(1) > 10000:
            indices = torch.randperm(edge_index.size(1))[:10000]
            edge_index = edge_index[:, indices]

        data = Data(x=x, y=y, edge_index=edge_index)
        split = int(n * (1 - input.test_ratio))
        train_mask = torch.zeros(n, dtype=torch.bool)
        train_mask[:split] = True
        test_mask = ~train_mask

        class GCNModel(torch.nn.Module):
            def __init__(self, in_ch, hidden_ch):
                super().__init__()
                self.conv1 = GCNConv(in_ch, hidden_ch)
                self.conv2 = GCNConv(hidden_ch, 1)

            def forward(self, data):
                x, edge_index = data.x, data.edge_index
                x = F.relu(self.conv1(x, edge_index))
                x = F.dropout(x, training=self.training)
                x = self.conv2(x, edge_index)
                return x.squeeze(-1)

        model = GCNModel(len(fcols), input.hidden_channels)
        optimizer = torch.optim.Adam(model.parameters(), lr=input.learning_rate)
        criterion = torch.nn.MSELoss()

        model.train()
        for _ in range(input.epochs):
            optimizer.zero_grad()
            out = model(data)
            loss = criterion(out[train_mask], data.y[train_mask])
            loss.backward()
            optimizer.step()

        model.eval()
        with torch.no_grad():
            pred = model(data)
            y_pred = pred[test_mask].numpy()
            y_test = data.y[test_mask].numpy()

        metrics = _regression_metrics(y_test, y_pred)
        return MLPredictionOutput(data=df, predictions=y_pred.tolist(), metrics=metrics)


# ============================================================
# 19. 超参数搜索(Optuna)节点
# ============================================================


@ui(
    target_col={"input_type": "text_field"},
    model_type={
        "input_type": "combobox",
        "options": ["lightgbm", "xgboost", "random_forest", "mlp"],
    },
    n_trials={"input_type": "number_field"},
    task_type={"input_type": "combobox", "options": ["regression", "classification"]},
    data={"input_type": "None"},
)
class OptunaSearchInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    target_col: str = "target"
    feature_cols: str = ""
    test_ratio: float = 0.2
    model_type: str = "lightgbm"
    n_trials: int = 50
    task_type: str = "regression"


class OptunaSearchOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    best_params: dict = Field(default_factory=dict, title="最优参数")
    best_score: float = Field(default=0.0, title="最优得分")
    trials: list = Field(default_factory=list, title="搜索历史")


@work_node(
    name="超参数搜索(Optuna)",
    group="07-机器学习",
    box_color="#E91E63",
    description="使用Optuna进行模型超参数自动搜索优化",
)
class OptunaSearchNode(BaseWorkNode):
    """基于 Optuna 的超参数搜索"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return OptunaSearchInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return OptunaSearchOutput

    def run(self, input: OptunaSearchInput) -> Optional[BaseModel]:
        try:
            import optuna

            optuna.logging.set_verbosity(optuna.logging.WARNING)
        except ImportError:
            return OptunaSearchOutput(
                data=pd.DataFrame(),
                best_params={},
                best_score=0.0,
                trials=[],
            )

        X, y, fcols = _prepare_xy(input.data, input.feature_cols, input.target_col)
        if X is None:
            return OptunaSearchOutput(
                data=pd.DataFrame(), best_params={}, best_score=0.0
            )

        X_train, X_test, y_train, y_test = _split_data(X, y, input.test_ratio)

        def objective(trial):
            model_type = input.model_type
            if model_type == "lightgbm":
                try:
                    import lightgbm as lgb

                    params = {
                        "n_estimators": trial.suggest_int("n_estimators", 50, 500),
                        "learning_rate": trial.suggest_float(
                            "learning_rate", 0.01, 0.3
                        ),
                        "num_leaves": trial.suggest_int("num_leaves", 15, 127),
                        "max_depth": trial.suggest_int("max_depth", 3, 12),
                        "random_state": 42,
                        "verbose": -1,
                    }
                    m = (
                        lgb.LGBMRegressor(**params)
                        if input.task_type == "regression"
                        else lgb.LGBMClassifier(**params)
                    )
                except ImportError:
                    return float("inf")
            elif model_type == "xgboost":
                try:
                    import xgboost as xgb

                    params = {
                        "n_estimators": trial.suggest_int("n_estimators", 50, 500),
                        "learning_rate": trial.suggest_float(
                            "learning_rate", 0.01, 0.3
                        ),
                        "max_depth": trial.suggest_int("max_depth", 3, 12),
                        "random_state": 42,
                        "verbosity": 0,
                    }
                    m = (
                        xgb.XGBRegressor(**params)
                        if input.task_type == "regression"
                        else xgb.XGBClassifier(**params)
                    )
                except ImportError:
                    return float("inf")
            elif model_type == "random_forest":
                from sklearn.ensemble import (
                    RandomForestClassifier,
                    RandomForestRegressor,
                )

                params = {
                    "n_estimators": trial.suggest_int("n_estimators", 50, 500),
                    "max_depth": trial.suggest_int("max_depth", 3, 20),
                    "random_state": 42,
                }
                m = (
                    RandomForestRegressor(**params)
                    if input.task_type == "regression"
                    else RandomForestClassifier(**params)
                )
            else:  # mlp
                from sklearn.neural_network import MLPClassifier, MLPRegressor

                params = {
                    "hidden_layer_sizes": (
                        trial.suggest_int("h1", 16, 128),
                        trial.suggest_int("h2", 16, 64),
                    ),
                    "max_iter": 500,
                    "random_state": 42,
                }
                m = (
                    MLPRegressor(**params)
                    if input.task_type == "regression"
                    else MLPClassifier(**params)
                )

            m.fit(X_train, y_train)
            y_pred = m.predict(X_test)
            if input.task_type == "regression":
                return float(np.sqrt(np.mean((y_test - y_pred) ** 2)))
            else:
                return -float(np.mean(y_test == y_pred))

        direction = "minimize" if input.task_type == "regression" else "maximize"
        study = optuna.create_study(direction=direction)
        study.optimize(objective, n_trials=input.n_trials)

        trials_info = [
            {"number": t.number, "value": t.value, "params": t.params}
            for t in study.trials
        ]
        return OptunaSearchOutput(
            data=input.data,
            best_params=study.best_params,
            best_score=float(study.best_value),
            trials=trials_info,
        )
