"""P2 ML→回测衔接测试：因子面板输出、walk-forward 无前视"""

import numpy as np
import pandas as pd

from backend.plugins.builtin.ml_models import (
    RFInput,
    RFNode,
    _build_factor_panel,
    _oos_predict,
)


def _tabular(n_dates=40, n_stocks=5, seed=5):
    """构造长表：date, code, close, f1, f2, target（target=次日收益）"""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-02", periods=n_dates)
    codes = [f"S{i}" for i in range(n_stocks)]
    rows = []
    for d in dates:
        for c in codes:
            f1 = rng.normal()
            f2 = rng.normal()
            rows.append(
                {
                    "date": d,
                    "code": c,
                    "close": 100 + rng.normal(),
                    "f1": f1,
                    "f2": f2,
                    "target": 0.5 * f1 + rng.normal(0, 0.1),
                }
            )
    return pd.DataFrame(rows)


def test_walk_forward_no_lookahead_positions():
    """walk-forward 的 OOS 位置严格在训练窗之后（无前视）"""
    X = np.arange(100).reshape(-1, 1).astype(float)
    y = np.arange(100).astype(float)

    class _Dummy:
        def fit(self, X, y):
            self._m = float(np.mean(y))

        def predict(self, X):
            return np.full(len(X), self._m)

    pos, pred, ytrue, _ = _oos_predict(
        lambda: _Dummy(), X, y, walk_forward=True, train_window=30, test_window=10
    )
    # 首个 OOS 位置应 >= train_window（不使用未来数据训练）
    assert pos.min() >= 30
    assert len(pos) == len(pred) == len(ytrue)


def test_rf_outputs_factor_panel():
    """RF 节点填 date_col/code_col 后输出 (date×code) 因子面板与 return_data"""
    df = _tabular()
    node = RFNode()
    out = node.run(
        RFInput(
            data=df,
            target_col="target",
            feature_cols="f1,f2",
            test_ratio=0.3,
            date_col="date",
            code_col="code",
        )
    )
    assert out.factor_panel is not None
    assert out.return_data is not None
    # 因子面板列应为股票代码
    assert set(out.factor_panel.columns) <= {"S0", "S1", "S2", "S3", "S4"}
    # 面板可直接喂给因子分析（index 为日期）
    assert isinstance(out.factor_panel.index, pd.DatetimeIndex)


def test_build_factor_panel_reshape():
    """OOS 预测重塑：预测值按 (date, code) 落位正确"""
    df = pd.DataFrame(
        {
            "date": ["2024-01-02", "2024-01-02", "2024-01-03", "2024-01-03"],
            "code": ["A", "B", "A", "B"],
            "close": [10.0, 20.0, 11.0, 19.0],
        }
    )
    positions = np.array([0, 1, 2, 3])
    preds = np.array([0.1, 0.2, 0.3, 0.4])
    panel, ret = _build_factor_panel(df, positions, preds, "date", "code")
    assert panel.loc[pd.Timestamp("2024-01-02"), "A"] == 0.1
    assert panel.loc[pd.Timestamp("2024-01-03"), "B"] == 0.4
    assert ret is not None  # 有 close 列 → 产出收益面板
