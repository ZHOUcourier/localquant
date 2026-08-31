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


def _wide_df(n_rows: int) -> "pd.DataFrame":
    """非日期索引的宽表，确保走表格分支而非多线图分支"""
    import pandas as pd

    return pd.DataFrame(
        {f"c{j}": range(n_rows) for j in range(14)},
        index=[f"r{i}" for i in range(n_rows)],
    )


def test_df_preview_keeps_tail_when_truncated():
    df = _wide_df(300)
    preview = workflow_service._df_preview(df)
    assert preview["kind"] == "table"
    assert preview["truncated"] is True
    assert preview["shape"] == [300, 14]
    assert len(preview["rows"]) == 150
    assert len(preview["tail_rows"]) == 50
    assert preview["rows"][0]["index"] == "r0"
    # 尾部必须是真实的最后 50 行，最后一行与源数据末尾一致
    assert preview["tail_rows"][-1]["index"] == "r299"
    assert preview["tail_rows"][-1]["c0"] == 299
    assert preview["tail_rows"][0]["index"] == "r250"


def test_df_preview_small_frame_not_truncated():
    df = _wide_df(200)
    preview = workflow_service._df_preview(df)
    assert preview["kind"] == "table"
    assert "truncated" not in preview
    assert "tail_rows" not in preview
    assert len(preview["rows"]) == 200
