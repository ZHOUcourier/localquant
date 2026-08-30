"""因子批量扫描 / 样本外验证 / 生命周期监控测试（合成面板，不依赖 QMT）"""

import asyncio
import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend.services.factor_research import FactorResearchService, factor_research

svc = FactorResearchService()


def _make_panels(n_dates: int = 400, n_stocks: int = 60, seed: int = 1):
    """合成面板：带一个已知动量信号的真实收益结构"""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-02", periods=n_dates)
    codes = [f"{600000 + i:06d}.SH" for i in range(n_stocks)]

    # 因子：滚动 20 日动量 + 噪声；收益 = 0.03 * 昨日因子 + 噪声（T+1 生效）
    raw = pd.DataFrame(
        rng.normal(0, 1, size=(n_dates, n_stocks)), index=dates, columns=codes
    )
    factor = raw.rolling(20, min_periods=20).mean()
    noise = rng.normal(0, 0.02, size=(n_dates, n_stocks))
    ret = pd.DataFrame(noise, index=dates, columns=codes) + 0.03 * factor.shift(1)
    close = (1 + ret.fillna(0)).cumprod()
    volume = pd.DataFrame(
        rng.uniform(1e6, 1e7, size=(n_dates, n_stocks)), index=dates, columns=codes
    )
    return factor, close, volume


def _insert_preset_factor(db_path, name: str, formula: str, category: str) -> int:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO preset_factors (factor_code, factor_name, category_code, "
        "category_name, description, is_preset) VALUES (?, ?, ?, ?, ?, 1)",
        (name.upper(), name, category, category, f"测试因子，公式是：{formula}"),
    )
    conn.commit()
    fid = cur.lastrowid
    conn.close()
    return fid


def _synthetic_formula(field: str = "close") -> str:
    return "RANK(CLOSE / DELAY(CLOSE, 20) - 1)"


class TestWalkForward:
    def test_validation_on_synthetic_signal(self):
        factor, close, _volume = _make_panels()
        return_data = close.pct_change()
        res = svc.walk_forward_validation(
            factor, return_data, train_days=200, test_days=60, n_splits=2, period=1
        )
        assert res["ok"] is True
        assert len(res["folds"]) == 2
        agg = res["aggregate"]
        # 合成信号有正 IC：OOS IC 应为正且非零
        assert agg["oos_ic_mean"] > 0.01
        assert agg["oos_sign_consistency"] >= 0.5
        assert len(agg["ic_decay_oos"]) == 4

    def test_validation_insufficient_samples(self):
        factor, close, _ = _make_panels(n_dates=50)
        res = svc.walk_forward_validation(
            factor, close.pct_change(), train_days=200, test_days=60
        )
        assert res["ok"] is False

    def test_validation_random_noise_has_low_oos_ic(self):
        """纯噪声因子 OOS IC 应接近 0"""
        factor, close, _ = _make_panels(seed=42)
        noise = pd.DataFrame(
            np.random.default_rng(9).normal(0, 1, size=factor.shape),
            index=factor.index,
            columns=factor.columns,
        )
        res = svc.walk_forward_validation(
            noise, close.pct_change(), train_days=200, test_days=60, n_splits=2
        )
        assert res["ok"] is True
        assert abs(res["aggregate"]["oos_ic_mean"]) < 0.05

    def test_window_long_short(self):
        factor, close, _ = _make_panels()
        cum, mean = svc._window_long_short(
            factor, close.pct_change(), 0, 120, n_groups=5
        )
        assert isinstance(cum, float)
        assert isinstance(mean, float)


class TestScanFactors:
    def _seed_db(self, tmp_path, monkeypatch):
        """指向临时库，并向预设因子表插入公式型因子"""
        from backend import database

        db_path = str(tmp_path / "test.db")
        monkeypatch.setattr(database, "DB_PATH", Path(db_path))
        asyncio.run(database.init_db())
        fid1 = _insert_preset_factor(db_path, "mom20", _synthetic_formula(), "TECHNICAL")
        fid2 = _insert_preset_factor(db_path, "rev5", "RANK(DELAY(CLOSE, 5) / CLOSE - 1)", "TECHNICAL")
        return db_path, fid1, fid2

    def test_scan_stream_events(self, tmp_path, monkeypatch):
        from backend.services import market_data

        _factor, close, volume = _make_panels(n_dates=120, n_stocks=60)
        panels = {"close": close, "volume": volume}

        monkeypatch.setattr(market_data, "list_cached_codes", lambda *a, **k: list(close.columns))
        monkeypatch.setattr(
            market_data,
            "load_price_panels",
            lambda *a, **k: panels,
        )
        monkeypatch.setattr(
            market_data,
            "build_cross_section_mask",
            lambda panels: None,
        )

        db_path, fid1, fid2 = self._seed_db(tmp_path, monkeypatch)

        events = []
        async def _run():
            async for chunk in factor_research.scan_factors_stream(
                factor_ids=[fid1, fid2], limit=10, max_workers=2
            ):
                events.append(chunk)

        asyncio.run(_run())
        types = [e.split("\n")[0].replace("event: ", "") for e in events]
        assert "scan_start" in types
        assert types[0] == "scan_start"
        assert types[-1] == "scan_done"
        assert types.count("factor_done") == 2

        done = json.loads(events[-1].split("\n")[1].replace("data: ", ""))
        assert done["ok_count"] == 2
        assert done["failed"] == 0
        # 小样本扫描必须显式给出置信度警示，而不是让用户把玩具样本当全市场结论
        assert done.get("warnings")
        assert any("股票" in w for w in done["warnings"])

        # 库内指标已覆盖更新，且必须标记为本地 QMT 样本（不允许外部参考值直接入池）
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT ic_mean, data_date, annualized_return, maximum_drawdown, "
            "sharpe_ratio, metric_source, metric_sample_json "
            "FROM preset_factors WHERE id=?",
            (fid1,),
        ).fetchone()
        conn.close()
        assert row[0] is not None and row[0] > 0.01
        assert row[1] is not None
        assert row[2] is not None
        assert row[3] is not None
        assert row[4] is not None
        assert row[5] == "local_recalc"
        sample = json.loads(row[6])
        assert sample["n_stocks"] == 60

    def test_add_to_pool_rejects_external_reference(self, tmp_path, monkeypatch):
        """外部参考指标不得入池；必须先基于本地 QMT 样本重算"""
        from backend import database

        db_path = str(tmp_path / "gate.db")
        monkeypatch.setattr(database, "DB_PATH", Path(db_path))
        asyncio.run(database.init_db())
        fid = _insert_preset_factor(db_path, "mom20", _synthetic_formula(), "TECHNICAL")
        conn = sqlite3.connect(db_path)
        conn.execute(
            "UPDATE preset_factors SET ic_mean=0.03, metric_source='external_ref' WHERE id=?",
            (fid,),
        )
        conn.commit()
        conn.close()

        with pytest.raises(ValueError):
            asyncio.run(factor_research.add_to_pool(fid))

    def test_scan_stream_no_data(self, tmp_path, monkeypatch):
        """无行情缓存时应产出明确的 scan_done 错误事件而非崩溃"""
        from backend import database
        from backend.services import market_data

        db_path = str(tmp_path / "test2.db")
        monkeypatch.setattr(database, "DB_PATH", Path(db_path))
        asyncio.run(database.init_db())
        fid1 = _insert_preset_factor(db_path, "mom20", _synthetic_formula(), "TECHNICAL")

        def _boom(*a, **k):
            raise ValueError("本地无缓存行情数据且未指定股票池")

        monkeypatch.setattr(market_data, "list_cached_codes", lambda *a, **k: [])
        monkeypatch.setattr(market_data, "load_price_panels", _boom)

        events = []

        async def _run():
            async for chunk in factor_research.scan_factors_stream(
                factor_ids=[fid1], limit=10
            ):
                events.append(chunk)

        asyncio.run(_run())
        done = json.loads(events[-1].split("\n")[1].replace("data: ", ""))
        assert done["ok_count"] == 0
        assert "无缓存行情数据" in done["message"]


class TestSampleGate:
    """P1-E：最小样本门槛必须同时守住入池与组合回测两条入口"""

    def _seed_local_recalc(self, tmp_path, monkeypatch, n_stocks: int, n_dates: int) -> int:
        from backend import database

        db_path = str(tmp_path / "gate.db")
        monkeypatch.setattr(database, "DB_PATH", Path(db_path))
        asyncio.run(database.init_db())
        fid = _insert_preset_factor(db_path, "mom20", _synthetic_formula(), "TECHNICAL")
        conn = sqlite3.connect(db_path)
        conn.execute(
            "UPDATE preset_factors SET metric_source='local_recalc', metric_sample_json=? "
            "WHERE id=?",
            (json.dumps({"n_stocks": n_stocks, "n_dates": n_dates}), fid),
        )
        conn.commit()
        conn.close()
        return fid

    def test_add_to_pool_rejects_small_sample(self, tmp_path, monkeypatch):
        fid = self._seed_local_recalc(tmp_path, monkeypatch, n_stocks=20, n_dates=100)
        with pytest.raises(ValueError, match="样本门槛"):
            asyncio.run(factor_research.add_to_pool(fid))

    def test_portfolio_rejects_small_sample_bypass(self, tmp_path, monkeypatch):
        """小样本因子经 factor_ids 直送 /portfolio（绕过入池）同样必须被拒"""
        from fastapi import HTTPException

        from backend.routes.backtest import PortfolioRequest, portfolio_backtest

        fid = self._seed_local_recalc(tmp_path, monkeypatch, n_stocks=20, n_dates=100)
        with pytest.raises(HTTPException) as ei:
            asyncio.run(portfolio_backtest(PortfolioRequest(factor_ids=[fid])))
        assert ei.value.status_code == 400
        assert "样本门槛" in ei.value.detail

    def test_validate_local_sample_boundaries(self):
        from backend.services.factor_research import validate_local_sample

        assert validate_local_sample("f", json.dumps({"n_stocks": 300, "n_dates": 252})) is None
        assert validate_local_sample("f", json.dumps({"n_stocks": 299, "n_dates": 252}))
        assert validate_local_sample("f", json.dumps({"n_stocks": 300, "n_dates": 251}))
        assert validate_local_sample("f", None)  # 无样本记录视同未达标


class TestFactorHealth:
    def test_health_with_history(self, tmp_path, monkeypatch):
        from pathlib import Path

        from backend import database

        db_path = str(tmp_path / "health.db")
        monkeypatch.setattr(database, "DB_PATH", Path(db_path))
        asyncio.run(database.init_db())

        import aiosqlite

        async def _seed():
            async with aiosqlite.connect(db_path) as db:
                await db.execute(
                    "CREATE TABLE IF NOT EXISTS preset_factor_ic_history ("
                    "id INTEGER PRIMARY KEY AUTOINCREMENT, factor_id INTEGER NOT NULL, "
                    "ic_mean REAL, rank_ic REAL, ic_ir REAL, ic_std REAL, "
                    "annualized_return REAL, maximum_drawdown REAL, sharpe_ratio REAL, "
                    "turnover_rate REAL, data_date TEXT, snapshot_at INTEGER)"
                )
                # 因子 A：IC 稳定在 0.05；因子 B：从 0.06 掉到 0.005（失效）
                await db.execute(
                    "INSERT INTO preset_factors (factor_code, factor_name, category_name, category_code, ic_mean, rank_ic, data_date) "
                    "VALUES ('F_STABLE', 'f_stable', 'TECHNICAL', 'TECHNICAL', 0.05, 0.04, '2024-01-01')"
                )
                await db.execute(
                    "INSERT INTO preset_factors (factor_code, factor_name, category_name, category_code, ic_mean, rank_ic, data_date) "
                    "VALUES ('F_DEAD', 'f_dead', 'TECHNICAL', 'TECHNICAL', 0.005, 0.004, '2024-06-01')"
                )
                fid1, fid2 = 1, 2
                for ic, ts in [(0.05, 100), (0.05, 200), (0.06, 300), (0.05, 400)]:
                    await db.execute(
                        "INSERT INTO preset_factor_ic_history "
                        "(factor_id, ic_mean, ic_std, ic_ir, data_date, snapshot_at) "
                        "VALUES (?, ?, 0.02, ?, ?, ?)",
                        (fid1, ic, ic / 0.02, "2024-01-01", ts),
                    )
                for ic, ts in [
                    (0.06, 100), (0.06, 200), (0.06, 300),
                    (0.05, 400), (0.04, 500), (0.03, 600),
                    (0.02, 700), (0.01, 800), (0.005, 900),
                ]:
                    await db.execute(
                        "INSERT INTO preset_factor_ic_history "
                        "(factor_id, ic_mean, ic_std, ic_ir, data_date, snapshot_at) "
                        "VALUES (?, ?, 0.02, ?, ?, ?)",
                        (fid2, ic, ic / 0.02, "2024-01-01", ts),
                    )
                await db.commit()

        asyncio.run(_seed())

        health = asyncio.run(factor_research.factor_health())
        by_name = {h["factor_name"]: h for h in health}
        assert by_name["f_stable"]["stage"] == "稳定"
        assert by_name["f_dead"]["stage"] == "失效"
        assert by_name["f_stable"]["n_snapshots"] == 4
        assert by_name["f_dead"]["trend_label"] == "↓"
