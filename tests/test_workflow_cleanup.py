"""工作流运行产物生命周期测试。"""

import os
import time
from pathlib import Path

from backend.services import workflow_service


def _touch(path: Path, age_days: int):
    path.write_bytes(b"x")
    old = time.time() - age_days * 86400
    os.utime(path, (old, old))


def test_cleanup_workflow_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(workflow_service.settings, "output_dir", tmp_path)
    old_run = tmp_path / "old-run"
    new_run = tmp_path / "new-run"
    keep = tmp_path / "_node_cache"
    old_run.mkdir()
    new_run.mkdir()
    keep.mkdir()
    _touch(old_run / "n1.pkl", 40)
    _touch(new_run / "n1.pkl", 2)
    _touch(keep / "cache.pkl", 40)

    result = workflow_service.cleanup_workflow_artifacts(keep_days=30, dry_run=True)
    assert result["dry_run"] is True
    assert old_run.exists()

    result = workflow_service.cleanup_workflow_artifacts(keep_days=30)
    assert result["removed_dirs"] == 1
    assert result["removed_files"] == 1
    assert not old_run.exists()
    assert new_run.exists()
    assert keep.exists()


def test_compact_node_outputs_does_not_store_dataframe_strings():
    import pandas as pd

    outputs = {
        "n1": {
            "factor_data": pd.DataFrame(
                {"A": [1.0, 2.0], "B": [3.0, 4.0]},
                index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
            )
        }
    }
    compact = workflow_service.compact_node_outputs(outputs)
    node = compact["n1"]
    assert node["_full_pkl"] is True
    assert "_preview_fields" in node
    assert "factor_data" in node["_preview_fields"]
