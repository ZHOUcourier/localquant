"""纯本地临时 SQLite 测试；覆盖本模块的 conftest 真库 autouse 初始化。"""

import asyncio
import hashlib
import json
import sqlite3
import time
from contextlib import closing

import pytest
from pydantic import ValidationError

from backend import database
from backend.models.research import (
    ResearchProtocol,
    ReviewRequest,
    RunRequest,
    StudyCreate,
    TrialCreate,
)
from backend.services import research_registry as registry


@pytest.fixture(scope="module", autouse=True)
def _init_db_session(tmp_path_factory):
    """覆盖 tests/conftest.py 的同名 fixture，绝不调用全库 init_db。"""
    original = database.DB_PATH
    database.DB_PATH = tmp_path_factory.mktemp("research-session") / "session.sqlite"
    try:
        yield
    finally:
        database.DB_PATH = original


@pytest.fixture(autouse=True)
def registry_db(tmp_path, monkeypatch, _init_db_session):
    path = tmp_path / "research.sqlite"
    monkeypatch.setattr(database, "DB_PATH", path)
    return path


def protocol(**overrides):
    values = {
        "start_date": "2020-01-01",
        "train_end": "2021-01-01",
        "validation_end": "2022-01-01",
        "end_date": "2023-01-01",
    }
    values.update(overrides)
    return ResearchProtocol(**values)


def study_request(**overrides):
    return StudyCreate(
        title="本地 QMT 研究",
        hypothesis="成本后收益有实用增量",
        sources=["研究员假设（尚无行情数据）"],
        protocol=protocol(**overrides),
    )


def trial_request(formula="close / delay(close, 5)", direction=1):
    return TrialCreate(formula=formula, direction=direction, rationale="预注册动量假设")


async def new_trial(**protocol_overrides):
    study = await registry.create_study(study_request(**protocol_overrides))
    trial = await registry.register_trial(study["id"], trial_request())
    return study, trial


async def complete(trial_id, phase="validation", result=None):
    _, _, run = await registry.begin_run(trial_id, phase)
    return await registry.finish_run(
        run["id"], "completed", {} if result is None else result
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"start_date": "20200101"},
        {"start_date": "2020-1-01"},
        {"start_date": "2020-02-30"},
        {"start_date": "2020-01-01T00:00:00"},
        {"start_date": "2021-01-01"},
        {"train_end": "2022-01-01"},
        {"validation_end": "2023-01-01"},
        {"end_date": "2019-01-01"},
    ],
)
def test_protocol_dates(overrides):
    with pytest.raises(ValidationError):
        protocol(**overrides)


@pytest.mark.parametrize(
    "field,value",
    [
        ("initial_capital", 0),
        ("initial_capital", -1),
        ("initial_capital", float("inf")),
        ("initial_capital", float("nan")),
        ("commission_rate", -0.001),
        ("commission_rate", 0.1001),
        ("slippage", -1),
        ("slippage", float("nan")),
        ("stamp_tax", 0.11),
        ("stamp_tax", float("inf")),
        ("minimum_effect", float("inf")),
        ("minimum_effect", float("nan")),
        ("horizon", 0),
        ("horizon", 61),
        ("top_n", 0),
        ("top_n", 1001),
        ("rebalance_days", 0),
        ("rebalance_days", 253),
        ("alpha", 0),
        ("alpha", 0.21),
        ("trial_budget", 0),
        ("trial_budget", 1001),
        ("min_dates", 19),
        ("min_dates", 1001),
        ("min_stocks", 9),
        ("min_stocks", 10001),
        ("candidate_weight", 0),
        ("candidate_weight", 1.01),
        ("monitor_window", 19),
        ("review_every", 0),
        ("regime_shrinkage", 0),
        ("baseline_formulas", [" "]),
        ("baseline_formulas", ["close"] * 11),
    ],
)
def test_protocol_numeric_and_baseline_constraints(field, value):
    with pytest.raises(ValidationError):
        protocol(**{field: value})


def test_protocol_defaults_frozen_extra_and_direction():
    req = protocol()
    assert req.codes == req.baseline_formulas == []
    assert (req.horizon, req.top_n, req.rebalance_days, req.trial_budget) == (
        5,
        20,
        5,
        20,
    )
    assert (req.alpha, req.min_dates, req.min_stocks) == (0.05, 60, 30)
    assert (req.commission_rate, req.slippage, req.stamp_tax) == (0.001, 0.001, 0.0005)
    assert (req.initial_capital, req.candidate_weight) == (1_000_000, 0.25)
    assert (req.monitor_window, req.review_every, req.minimum_effect) == (60, 20, 0)
    assert (req.regime_index, req.regime_shrinkage) == ("000300.SH", 60)
    assert protocol(minimum_effect=-0.001).minimum_effect == -0.001
    with pytest.raises(ValidationError):
        req.alpha = 0.1
    with pytest.raises(ValidationError):
        protocol(unregistered_setting=True)
    assert trial_request(direction=-1).direction == -1
    assert trial_request(formula="-close", direction=1).direction == 1
    assert RunRequest().phase == "validation"


def test_codes_normalization_all_allowed_prefixes():
    sh = [f"{prefix}001.SH" for prefix in ("600", "601", "603", "605", "688", "689")]
    sz = [
        f"{prefix}001.SZ"
        for prefix in ("000", "001", "002", "003", "300", "301", "302")
    ]
    bj = ["430001.BJ", "830001.BJ", "920001.BJ"]
    codes = [" 600001.sh ", "000001", "600001.SH"] + sh + sz + bj
    result = protocol(codes=codes).codes
    assert result[:2] == ["600001.SH", "000001.SZ"]
    assert len(result) == len(set(sh + sz + bj))
    assert set(result) == set(sh + sz + bj)


@pytest.mark.parametrize(
    "code",
    [
        "000300.SH",
        "510300.SH",
        "900901.SH",
        "200001.SZ",
        "399001.SZ",
        "600000.SZ",
        "000001.BJ",
        "920001.SH",
        "930001.BJ",
        "00700.HK",
        "AAPL",
        "60000",
        "6000000.SH",
        "",
        "600000.SH'; DROP TABLE experiments;--",
    ],
)
def test_non_a_share_codes_rejected(code):
    with pytest.raises(ValidationError):
        protocol(codes=[code])


@pytest.mark.parametrize(
    "field,value",
    [
        ("title", " "),
        ("title", "x" * 161),
        ("hypothesis", ""),
        ("hypothesis", "x" * 4001),
        ("sources", []),
        ("sources", [" "]),
        ("sources", ["citation"] * 21),
    ],
)
def test_study_request_constraints(field, value):
    data = study_request().model_dump()
    data[field] = value
    with pytest.raises(ValidationError):
        StudyCreate(**data)


@pytest.mark.parametrize(
    "data",
    [
        {"formula": " ", "rationale": "ok"},
        {"formula": "x" * 4001, "rationale": "ok"},
        {"formula": "close", "rationale": " "},
        {"formula": "close", "rationale": "x" * 4001},
        {"formula": "close", "rationale": "ok", "direction": 0},
    ],
)
def test_trial_request_constraints(data):
    with pytest.raises(ValidationError):
        TrialCreate(**data)


def test_run_and_review_request_constraints():
    with pytest.raises(ValidationError):
        RunRequest(phase="train")
    with pytest.raises(ValidationError):
        ReviewRequest(target_state="research", note="reason")
    with pytest.raises(ValidationError):
        ReviewRequest(target_state="active", note=" ")


def test_no_data_registration_hash_and_protocol_snapshot(registry_db):
    async def scenario():
        assert await registry.list_studies() == []
        assert await registry.get_study("missing") is None
        request = study_request(codes=["600000.SH"], baseline_formulas=["close"])
        before = int(time.time())
        study = await registry.create_study(request)
        assert before <= study["created_at"] <= int(time.time())
        assert set(study) == {
            "id",
            "title",
            "hypothesis",
            "sources",
            "protocol",
            "protocol_hash",
            "state",
            "selected_trial_id",
            "universe",
            "created_at",
        }
        assert study["state"] == "research"
        assert study["selected_trial_id"] is None and study["universe"] == []
        canonical = json.dumps(
            study["protocol"],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        assert study["protocol_hash"] == hashlib.sha256(canonical.encode()).hexdigest()
        reordered = dict(reversed(list(request.protocol.model_dump().items())))
        same = await registry.create_study(
            StudyCreate(
                title="独立重复协议",
                hypothesis=request.hypothesis,
                sources=request.sources,
                protocol=ResearchProtocol(**reordered),
            )
        )
        assert same["protocol_hash"] == study["protocol_hash"]
        request.protocol.codes.append("000001.SZ")
        study["protocol"]["baseline_formulas"].append("volume")
        fetched = await registry.get_study(study["id"])
        assert fetched["protocol"]["codes"] == ["600000.SH"]
        assert fetched["protocol"]["baseline_formulas"] == ["close"]
        assert fetched["trials"] == fetched["runs"] == fetched["reviews"] == []
        assert len(await registry.list_studies()) == 2

    asyncio.run(scenario())
    with closing(sqlite3.connect(registry_db)) as db:
        tables = {
            r[0]
            for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert tables == {
            "research_studies",
            "research_trials",
            "research_runs",
            "research_reviews",
            "experiments",
        }


def test_duplicate_trial_budget_and_sql_text():
    async def scenario():
        study, trial = await new_trial(trial_budget=2)
        duplicate = await registry.register_trial(
            study["id"],
            TrialCreate(
                formula=trial["formula"],
                direction=trial["direction"],
                rationale="不覆盖原始依据",
            ),
        )
        assert duplicate == trial
        inverse = await registry.register_trial(
            study["id"], trial_request(direction=-1)
        )
        assert inverse["direction"] == -1 and inverse["id"] != trial["id"]
        with pytest.raises(ValueError, match="budget"):
            await registry.register_trial(study["id"], trial_request(formula="volume"))
        assert await registry.register_trial(study["id"], trial_request()) == trial
        assert len((await registry.get_study(study["id"]))["trials"]) == 2
        other = await registry.create_study(study_request())
        formula = "close'; DROP TABLE research_trials;--"
        stored = await registry.register_trial(
            other["id"], trial_request(formula=formula)
        )
        assert stored["formula"] == formula
        assert len(await registry.list_studies()) == 2

    asyncio.run(scenario())


def test_holdout_lock_survives_missing_data_failure_and_rejects_reselection():
    async def scenario():
        study, trial = await new_trial()
        alternate = await registry.register_trial(
            study["id"], trial_request(formula="volume")
        )
        with pytest.raises(ValueError, match="validation"):
            await registry.begin_run(trial["id"], "holdout")
        assert (await registry.get_study(study["id"]))["selected_trial_id"] is None
        await complete(trial["id"])
        await complete(alternate["id"])
        with pytest.raises(ValueError, match="Validation"):
            await registry.begin_run(trial["id"], "validation")
        selected, returned_trial, run = await registry.begin_run(trial["id"], "holdout")
        assert returned_trial == trial and selected["selected_trial_id"] == trial["id"]
        # begin_run 返回前选择已提交，尚未取得任何计算数据。
        assert (await registry.get_study(study["id"]))["selected_trial_id"] == trial[
            "id"
        ]
        for status in ("awaiting_data", "failed"):
            await registry.finish_run(
                run["id"], status, {"reason": "no local QMT cache"}
            )
            with pytest.raises(ValueError, match="locked"):
                await registry.begin_run(alternate["id"], "holdout")
            with pytest.raises(ValueError, match="locked"):
                await registry.register_trial(
                    study["id"], trial_request(formula="open")
                )
            assert await registry.register_trial(study["id"], trial_request()) == trial
            with pytest.raises(ValueError, match="Monitor"):
                await registry.begin_run(trial["id"], "monitor")
            _, _, run = await registry.begin_run(trial["id"], "holdout")
        await registry.finish_run(run["id"], "completed", {"decision": "unsupported"})
        with pytest.raises(ValueError, match="already completed"):
            await registry.begin_run(trial["id"], "holdout")
        with pytest.raises(ValueError, match="Monitor"):
            await registry.begin_run(alternate["id"], "monitor")
        await complete(trial["id"], "monitor")
        await complete(trial["id"], "monitor")  # 证据截止日幂等由上游负责。

    asyncio.run(scenario())


def test_running_is_per_study_and_validation_retry():
    async def scenario():
        study, trial = await new_trial()
        second = await registry.register_trial(
            study["id"], trial_request(formula="volume")
        )
        _, _, run = await registry.begin_run(trial["id"], "validation")
        for phase in ("validation", "holdout", "monitor"):
            with pytest.raises(ValueError, match="running"):
                await registry.begin_run(second["id"], phase)
        _, unrelated = await new_trial()
        await complete(unrelated["id"])
        for status in ("awaiting_data", "failed"):
            await registry.finish_run(run["id"], status, {})
            _, _, run = await registry.begin_run(trial["id"], "validation")
        await registry.finish_run(run["id"], "completed", {})
        with pytest.raises(ValueError, match="already completed"):
            await registry.begin_run(trial["id"], "validation")

    asyncio.run(scenario())


def test_concurrent_budget_and_duplicate_registration():
    async def scenario():
        study = await registry.create_study(study_request(trial_budget=1))
        results = await asyncio.gather(
            *[registry.register_trial(study["id"], trial_request()) for _ in range(6)]
        )
        assert len({result["id"] for result in results}) == 1
        other = await registry.create_study(study_request(trial_budget=1))
        results = await asyncio.gather(
            *[
                registry.register_trial(
                    other["id"], trial_request(formula=f"close + {i}")
                )
                for i in range(6)
            ],
            return_exceptions=True,
        )
        assert sum(isinstance(result, dict) for result in results) == 1
        assert sum(isinstance(result, ValueError) for result in results) == 5
        assert len((await registry.get_study(other["id"]))["trials"]) == 1

    asyncio.run(scenario())


def test_concurrent_runs_and_holdout_selection():
    async def scenario():
        study, trial = await new_trial()
        other = await registry.register_trial(
            study["id"], trial_request(formula="volume")
        )
        results = await asyncio.gather(
            registry.begin_run(trial["id"], "validation"),
            registry.begin_run(other["id"], "validation"),
            return_exceptions=True,
        )
        successes = [result for result in results if isinstance(result, tuple)]
        assert len(successes) == 1
        assert sum(isinstance(result, ValueError) for result in results) == 1
        _, winner, run = successes[0]
        await registry.finish_run(run["id"], "completed", {})
        loser = trial if winner["id"] == other["id"] else other
        await complete(loser["id"])
        results = await asyncio.gather(
            registry.begin_run(trial["id"], "holdout"),
            registry.begin_run(other["id"], "holdout"),
            return_exceptions=True,
        )
        successes = [result for result in results if isinstance(result, tuple)]
        assert len(successes) == 1
        assert sum(isinstance(result, ValueError) for result in results) == 1
        _, winner, run = successes[0]
        await registry.finish_run(run["id"], "awaiting_data", {})
        assert (await registry.get_study(study["id"]))["selected_trial_id"] == winner[
            "id"
        ]

    asyncio.run(scenario())


@pytest.mark.parametrize("status", ["completed", "awaiting_data", "failed"])
def test_finish_preserves_evidence_and_experiment_metadata(registry_db, status):
    async def scenario():
        study, trial = await new_trial()
        _, _, run = await registry.begin_run(trial["id"], "validation")
        evidence = {
            "summary": {"net_increment": 0.001},
            "decision": "inconclusive",
            "daily": [{"date": "2022-01-01", "value": None}],
            "audit": {"source": "WindowsQMT", "warnings": ["样本不足"]},
        }
        result = await registry.finish_run(run["id"], status, evidence, "诊断文本")
        assert result["result"] == evidence and result["error"] == "诊断文本"
        assert result["status"] == status
        assert (await registry.get_study(study["id"]))["runs"][0] == result
        assert (
            await registry.finish_run(run["id"], status, evidence, "诊断文本") == result
        )
        with pytest.raises(ValueError, match="overwritten"):
            await registry.finish_run(run["id"], status, {"summary": {}})
        with closing(sqlite3.connect(registry_db)) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("SELECT * FROM experiments").fetchall()
            assert len(rows) == 1
            experiment = dict(rows[0])
            assert (
                experiment["source"],
                experiment["source_id"],
                experiment["status"],
            ) == ("research", run["id"], status)
            assert json.loads(experiment["metrics_json"]) == evidence["summary"]
            assert json.loads(experiment["params_json"]) == {
                "phase": "validation",
                "protocol_hash": study["protocol_hash"],
                "trial": trial,
            }

    asyncio.run(scenario())


def test_finish_rolls_back_both_tables_on_experiment_failure(registry_db):
    async def scenario():
        study, trial = await new_trial()
        _, _, run = await registry.begin_run(trial["id"], "validation")
        with closing(sqlite3.connect(registry_db)) as db:
            db.execute("""CREATE TRIGGER reject_experiment BEFORE INSERT ON experiments
                          BEGIN SELECT RAISE(ABORT, 'audit write rejected'); END""")
            db.commit()
        with pytest.raises(sqlite3.IntegrityError, match="audit write rejected"):
            await registry.finish_run(
                run["id"], "completed", {"essential_evidence": [1, 2]}
            )
        saved = (await registry.get_study(study["id"]))["runs"][0]
        assert saved == run
        with closing(sqlite3.connect(registry_db)) as db:
            assert db.execute("SELECT COUNT(*) FROM experiments").fetchone()[0] == 0
            db.execute("DROP TRIGGER reject_experiment")
            db.commit()
        await registry.finish_run(
            run["id"], "completed", {"essential_evidence": [1, 2]}
        )
        with closing(sqlite3.connect(registry_db)) as db:
            assert (
                db.execute("SELECT metrics_json FROM experiments").fetchone()[0] == "{}"
            )

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "evidence",
    [
        {"summary": {"x": float("nan")}},
        {"daily": [float("inf")]},
        {"audit": {"unserializable": object()}},
    ],
)
def test_non_json_evidence_rejected_without_partial_finish(registry_db, evidence):
    async def scenario():
        study, trial = await new_trial()
        _, _, run = await registry.begin_run(trial["id"], "validation")
        with pytest.raises(ValueError, match="JSON"):
            await registry.finish_run(run["id"], "completed", evidence)
        assert (await registry.get_study(study["id"]))["runs"][0] == run
        with closing(sqlite3.connect(registry_db)) as db:
            assert db.execute("SELECT COUNT(*) FROM experiments").fetchone()[0] == 0

    asyncio.run(scenario())


def test_concurrent_finish_records_once(registry_db):
    async def scenario():
        _, trial = await new_trial()
        _, _, run = await registry.begin_run(trial["id"], "validation")
        results = await asyncio.gather(
            *[
                registry.finish_run(run["id"], "completed", {"proof": "same"})
                for _ in range(4)
            ]
        )
        assert all(result == results[0] for result in results)
        with closing(sqlite3.connect(registry_db)) as db:
            assert db.execute("SELECT COUNT(*) FROM experiments").fetchone()[0] == 1

    asyncio.run(scenario())


def test_no_evidence_cannot_change_state_and_unsupported_cannot_activate():
    async def scenario():
        study, trial = await new_trial()
        for status in (None, "awaiting_data", "failed"):
            if status:
                _, _, run = await registry.begin_run(trial["id"], "validation")
                await registry.finish_run(run["id"], status, {"decision": "supported"})
            for state in ("active", "watch", "dormant", "retired"):
                with pytest.raises(ValueError):
                    await registry.review_study(
                        study["id"], ReviewRequest(target_state=state, note="人工复核")
                    )
        await complete(trial["id"], result={"decision": "supported"})
        with pytest.raises(ValueError, match="holdout"):
            await registry.review_study(
                study["id"], ReviewRequest(target_state="active", note="仅验证集")
            )
        await complete(trial["id"], "holdout", {"decision": "unsupported"})
        with pytest.raises(ValueError, match="supported"):
            await registry.review_study(
                study["id"], ReviewRequest(target_state="active", note="未支持")
            )
        fetched = await registry.get_study(study["id"])
        assert fetched["state"] == "research" and fetched["reviews"] == []

    asyncio.run(scenario())


@pytest.mark.parametrize("state", ["watch", "dormant", "retired"])
def test_completed_validation_allows_non_active_review(state):
    async def scenario():
        study, trial = await new_trial()
        await complete(trial["id"])
        review = await registry.review_study(
            study["id"], ReviewRequest(target_state=state, note="已有证据")
        )
        assert review["from_state"] == "research" and review["target_state"] == state
        fetched = await registry.get_study(study["id"])
        assert fetched["state"] == state and fetched["reviews"] == [review]

    asyncio.run(scenario())


def test_manual_active_same_state_notes_and_retired_terminal():
    async def scenario():
        study, trial = await new_trial()
        await complete(trial["id"])
        await complete(trial["id"], "holdout", {"decision": "supported"})
        assert (await registry.get_study(study["id"]))["state"] == "research"
        for state in (
            "active",
            "active",
            "watch",
            "dormant",
            "active",
            "retired",
            "retired",
        ):
            review = await registry.review_study(
                study["id"], ReviewRequest(target_state=state, note="人工复核，仅建议")
            )
            assert review["target_state"] == state
        # 即使有新的监控证据，也不能自动或间接复活已退役研究。
        await complete(trial["id"], "monitor", {"decision": "supported"})
        for state in ("active", "watch", "dormant"):
            with pytest.raises(ValueError, match="terminal"):
                await registry.review_study(
                    study["id"], ReviewRequest(target_state=state, note="不应复活")
                )
        fetched = await registry.get_study(study["id"])
        assert fetched["state"] == "retired" and len(fetched["reviews"]) == 7
        assert fetched["reviews"][1]["from_state"] == "active"
        assert fetched["protocol_hash"] == study["protocol_hash"]

    asyncio.run(scenario())


def test_universe_freeze_sorted_unique_immutable_and_empty():
    async def scenario():
        study = await registry.create_study(study_request())
        expected = ["000001.SZ", "600000.SH"]
        assert (
            await registry.freeze_universe(
                study["id"], ["600000.sh", "000001", "600000.SH"]
            )
            == expected
        )
        assert (
            await registry.freeze_universe(study["id"], list(reversed(expected)))
            == expected
        )
        for replacement in (["600000.SH"], [], ["000001.SZ", "600000.SH", "920001.BJ"]):
            with pytest.raises(ValueError, match="frozen"):
                await registry.freeze_universe(study["id"], replacement)
        fetched = await registry.get_study(study["id"])
        assert (
            fetched["universe"] == expected
            and fetched["protocol_hash"] == study["protocol_hash"]
        )
        empty = await registry.create_study(study_request())
        assert await registry.freeze_universe(empty["id"], []) == []
        assert await registry.freeze_universe(empty["id"], []) == []
        with pytest.raises(ValueError, match="frozen"):
            await registry.freeze_universe(empty["id"], expected)
        with pytest.raises(ValueError):
            await registry.freeze_universe(empty["id"], ["510300.SH"])

    asyncio.run(scenario())


def test_concurrent_universe_first_writer_wins():
    async def scenario():
        study = await registry.create_study(study_request())
        results = await asyncio.gather(
            registry.freeze_universe(study["id"], ["600000.SH"]),
            registry.freeze_universe(study["id"], ["000001.SZ"]),
            return_exceptions=True,
        )
        successes = [result for result in results if isinstance(result, list)]
        assert len(successes) == 1
        assert sum(isinstance(result, ValueError) for result in results) == 1
        assert (await registry.get_study(study["id"]))["universe"] == successes[0]

    asyncio.run(scenario())


def test_missing_ids_and_invalid_runtime_requests():
    async def scenario():
        with pytest.raises(KeyError):
            await registry.register_trial("missing", trial_request())
        with pytest.raises(KeyError):
            await registry.begin_run("missing", "validation")
        with pytest.raises(KeyError):
            await registry.finish_run("missing", "completed", {})
        with pytest.raises(KeyError):
            await registry.freeze_universe("missing", [])
        with pytest.raises(KeyError):
            await registry.review_study(
                "missing", ReviewRequest(target_state="watch", note="人工复核")
            )
        with pytest.raises(ValueError):
            await registry.begin_run("missing", "train")
        with pytest.raises(ValueError):
            await registry.finish_run("missing", "running", {})
        with pytest.raises(ValueError):
            await registry.finish_run("missing", "completed", [])

    asyncio.run(scenario())
