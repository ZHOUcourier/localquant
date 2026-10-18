import asyncio
import json

import httpx
import numpy as np
import pandas as pd
import pytest
from fastapi import FastAPI

from backend import database
from backend.models.research import ResearchProtocol, StudyCreate, TrialCreate
from backend.routes.research import router
from backend.services import research_registry as registry
from backend.services import research_service as service


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "research.db")
    asyncio.run(database.init_db())


def protocol():
    dates = pd.bdate_range("2023-01-02", periods=140)
    return ResearchProtocol(
        start_date=str(dates[0].date()), train_end=str(dates[49].date()),
        validation_end=str(dates[94].date()), end_date=str(dates[139].date()),
        min_dates=20, min_stocks=10, top_n=4, horizon=3,
    )


async def registered():
    study = await registry.create_study(StudyCreate(
        title="隔离检验", hypothesis="手算与时序实现验证，不是金融有效性声明",
        sources=["pytest 隔离用例"], protocol=protocol(),
    ))
    trial = await registry.register_trial(study["id"], TrialCreate(
        formula="RANK(CLOSE / DELAY(CLOSE, 5) - 1)", rationale="检查前缀计算与接口",
    ))
    return study, trial


def inputs(n_dates=140):
    dates = pd.bdate_range("2023-01-02", periods=n_dates)
    codes = [f"600{i:03d}.SH" for i in range(12)]
    rng = np.random.default_rng(194)
    close = pd.DataFrame(100 * np.cumprod(1 + rng.normal(0.0002, 0.01, (n_dates, 12)), axis=0), index=dates, columns=codes)
    volume = pd.DataFrame(1e6, index=dates, columns=codes)
    mask = pd.DataFrame(True, index=dates, columns=codes)
    return {
        "panels": {"close": close, "open": close, "high": close * 1.01, "low": close * 0.99, "volume": volume, "amount": close * volume},
        "raw_close": close.copy(), "mask": mask, "industry": None, "fundamental": {},
        "states": pd.Series("range_normal", index=dates), "codes": codes,
        "reference": {"tradable_mask": mask, "up_limit": None, "down_limit": None, "assumptions": ["isolated fixture"]},
    }


def test_no_data_records_waiting_without_fabricated_metrics(isolated_db, monkeypatch):
    from backend.services import market_data

    monkeypatch.setattr(market_data, "list_cached_codes", lambda *args, **kwargs: [])

    async def check():
        study, trial = await registered()
        run = await service.run_trial(trial["id"])
        assert run["status"] == "awaiting_data"
        assert run["result"]["summary"] == {}
        assert run["result"]["decision"] == "insufficient_data"
        saved = await registry.get_study(study["id"])
        assert saved["runs"][0]["id"] == run["id"]
        assert saved["state"] == "research"
        assert saved["selected_trial_id"] is None
        json.dumps(run, allow_nan=False)

    asyncio.run(check())


def test_api_validates_protocol_and_roundtrips_no_data(isolated_db, monkeypatch):
    from backend.services import market_data

    monkeypatch.setattr(market_data, "list_cached_codes", lambda *args, **kwargs: [])
    app = FastAPI()
    app.include_router(router, prefix="/api/research")

    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/api/research/studies")).json() == []
            payload = {"title": "研究", "hypothesis": "可证伪假设", "sources": ["研究员假设"], "protocol": protocol().model_dump()}
            invalid = {**payload, "protocol": {**payload["protocol"], "end_date": "2000-01-01"}}
            assert (await client.post("/api/research/studies", json=invalid)).status_code == 422
            response = await client.post("/api/research/studies", json=payload)
            assert response.status_code == 200
            sid = response.json()["id"]
            trial = (await client.post(f"/api/research/studies/{sid}/trials", json={"formula": "RANK(CLOSE)", "rationale": "检查"})).json()
            waiting = await client.post(f"/api/research/trials/{trial['id']}/run", json={"phase": "validation"})
            assert waiting.json()["status"] == "awaiting_data"
            assert (await client.post(f"/api/research/trials/{trial['id']}/run", json={"phase": "holdout"})).status_code == 409
            assert (await client.post(f"/api/research/studies/{sid}/review", json={"target_state": "active", "note": "尚无证据"})).status_code == 409
            assert (await client.get("/api/research/studies/missing")).status_code == 404
            assert len((await client.get("/api/research/guidance")).json()["roadmap"]) == 5

    asyncio.run(check())


def test_formula_evaluation_cannot_access_future_prices():
    data = inputs(20)
    future = service._causal_factors(["DELAY(CLOSE, -1)"], data)[0]
    assert future.isna().all().all()
    full = service._causal_factors(["RANK(CLOSE)"], data)[0]
    cut = 12
    shortened = {
        **data,
        "panels": {k: v.iloc[:cut] for k, v in data["panels"].items()},
    }
    prefix = service._causal_factors(["RANK(CLOSE)"], shortened)[0]
    pd.testing.assert_frame_equal(prefix, full.iloc[:cut])


def test_complete_evidence_is_finite_and_preserves_execution_contract():
    p = protocol().model_dump()
    study = {"protocol": p, "protocol_hash": "frozen", "runs": []}
    trial = {"id": "trial", "formula": "RANK(CLOSE / DELAY(CLOSE, 5) - 1)", "direction": 1}
    result = service.compute_evidence(study, trial, "validation", inputs(95))

    assert result["status"] == "completed"
    assert set(result["tracks"]) == {"raw", "neutralized", "incremental"}
    assert result["manifest"]["test_alpha"] == pytest.approx(p["alpha"] / p["trial_budget"])
    assert result["manifest"]["execution"] == "signal_T_close_fill_T_plus_1_close"
    assert result["manifest"]["label_end_offset"] == 4
    assert result["manifest"]["signal_evaluation"] == "causal_prefix"
    assert result["primary"]["n_obs"] == 45
    assert result["manifest"]["evaluation_end"] == p["validation_end"]
    assert np.isfinite(result["primary"]["mean"])
    json.dumps(result, allow_nan=False)


def test_lookahead_formula_never_gets_supported():
    study = {"protocol": protocol().model_dump(), "protocol_hash": "frozen", "runs": []}
    trial = {"id": "future", "formula": "DELAY(CLOSE, -1)", "direction": 1}
    result = service.compute_evidence(study, trial, "validation", inputs(95))
    assert result["decision"] == "insufficient_data"
    assert result["tracks"]["raw"]["ic"]["n_obs"] == 0


def test_run_preserves_prior_evidence_for_monitor(isolated_db, monkeypatch):
    data = inputs()
    monkeypatch.setattr(service, "_load_inputs", lambda study, phase: data)
    seen = []

    def compute(study, trial, phase, loaded):
        seen.append((phase, [r["phase"] for r in study["runs"] if r["status"] == "completed"]))
        return {"decision": "inconclusive", "summary": {}, "manifest": {"validation_data_hash": "same"}}

    monkeypatch.setattr(service, "compute_evidence", compute)

    async def check():
        _, trial = await registered()
        assert (await service.run_trial(trial["id"], "validation"))["status"] == "completed"
        assert (await service.run_trial(trial["id"], "holdout"))["status"] == "completed"
        assert (await service.run_trial(trial["id"], "monitor"))["status"] == "completed"
        assert seen[-1] == ("monitor", ["validation", "holdout"])

    asyncio.run(check())


def test_monitor_same_grid_is_not_another_completed_review(isolated_db, monkeypatch):
    monkeypatch.setattr(service, "_load_inputs", lambda study, phase: inputs())

    def compute(study, trial, phase, loaded):
        result = {"decision": "inconclusive", "summary": {}, "manifest": {"validation_data_hash": "same"}, "limitations": []}
        if phase == "monitor":
            result["monitor"] = {"status": "monitoring", "review_date": "2024-01-31", "review_number": 1}
        return result

    monkeypatch.setattr(service, "compute_evidence", compute)

    async def check():
        study, trial = await registered()
        await service.run_trial(trial["id"], "validation")
        await service.run_trial(trial["id"], "holdout")
        first = await service.run_trial(trial["id"], "monitor")
        duplicate = await service.run_trial(trial["id"], "monitor")
        assert first["status"] == "completed"
        assert duplicate["status"] == "awaiting_data"
        assert duplicate["result"]["monitor"]["duplicate_of"] == first["id"]
        saved = await registry.get_study(study["id"])
        assert sum(r["phase"] == "monitor" and r["status"] == "completed" for r in saved["runs"]) == 1

    asyncio.run(check())


def test_regime_code_rejects_paths():
    with pytest.raises(ValueError, match="QMT index code"):
        ResearchProtocol.model_validate({**protocol().model_dump(), "regime_index": "../../private"})


def test_cache_reader_never_downloads_missing_data(monkeypatch):
    from backend.services import market_data

    monkeypatch.setattr(market_data._cache, "get", lambda *args: None)

    def forbid(*args, **kwargs):
        pytest.fail("research must not fetch remote QMT data")

    monkeypatch.setattr(market_data, "_fetch_and_cache", forbid)
    with pytest.raises(service.ResearchDataUnavailable, match="缺少本地 QMT"):
        service._cached_panels(["600000.SH"], "2024-01-02", "2024-03-29")
