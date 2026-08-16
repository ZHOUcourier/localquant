"""面板 artifact 传输测试 — 全市场研究不能靠嵌套 JSON 传整表。"""

import pandas as pd
import pytest

from backend.services import panel_artifact


def _panels(n_stocks: int, n_dates: int) -> dict[str, pd.DataFrame]:
    dates = pd.bdate_range("2024-01-02", periods=n_dates)
    codes = [f"{600000 + i:06d}.SH" for i in range(n_stocks)]
    factor = pd.DataFrame(1.0, index=dates, columns=codes)
    returns = factor * 0.01
    return {"factor_data": factor, "return_data": returns}


def test_small_panels_stay_inline(tmp_path, monkeypatch):
    monkeypatch.setattr(panel_artifact, "_ARTIFACT_DIR", tmp_path)
    resp = panel_artifact.build_panel_response(
        _panels(5, 20), inline_names=["factor_data", "return_data"]
    )
    assert resp["panel_mode"] == "inline"
    assert resp["factor_data"]
    assert resp["return_data"]
    assert resp["panel_token"]
    loaded = panel_artifact.load_panels(resp["panel_token"])
    assert loaded["factor_data"].shape == (20, 5)


def test_large_panels_switch_to_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(panel_artifact, "_ARTIFACT_DIR", tmp_path)
    monkeypatch.setattr(panel_artifact, "INLINE_CELL_LIMIT", 100)
    resp = panel_artifact.build_panel_response(
        _panels(50, 50), inline_names=["factor_data", "return_data"]
    )
    assert resp["panel_mode"] == "artifact"
    assert resp["factor_data"] == {}
    assert resp["return_data"] == {}
    assert resp["preview"]["factor_data"]
    assert len(resp["preview_stocks"]) <= panel_artifact.PREVIEW_STOCKS
    loaded = panel_artifact.load_panels(resp["panel_token"])
    assert loaded["factor_data"].shape == (50, 50)


def test_invalid_token_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(panel_artifact, "_ARTIFACT_DIR", tmp_path)
    with pytest.raises(ValueError):
        panel_artifact.load_panels("../../etc/passwd")
