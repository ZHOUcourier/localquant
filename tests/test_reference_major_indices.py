"""主要宽基指数成分自动快照测试。"""

from backend.services import reference_data


class FakeQMT:
    def __init__(self):
        self.calls = []

    def get_sector_stocks(self, sector):
        self.calls.append(sector)
        if sector == "000300.SH":
            return ["600000.SH", "000001.SZ"]
        if sector == "沪深300":
            return ["600000.SH", "000001.SZ"]  # 与代码候选重复，应去重
        if sector == "000905.SH":
            return ["600000.SH", "000002.SZ"]
        return []


def test_snapshot_major_indices(tmp_path, monkeypatch):
    monkeypatch.setattr(reference_data, "REFERENCE_DIR", tmp_path)
    qmt = FakeQMT()
    rows = reference_data.snapshot_major_indices(qmt)
    # 000300.SH + 000905.SH 两个不同成分集合；沪深300 重复集合不计
    assert rows == 4
    frame = reference_data._read(reference_data._CONSTITUENTS_FILE)
    assert frame is not None
    assert set(frame["index_name"]) == {"000300.SH", "000905.SH"}
