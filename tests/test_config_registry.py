"""配置注册表与环境文件安全写入测试。"""

import asyncio
import os
import stat

import pytest
from pydantic import ValidationError

from backend.config import settings
from backend.config_registry import SECRET_FIELDS, SETTING_SPECS, UNIVERSE_SPECS
from backend.env_file import delete_env_keys, update_env_file
from backend.routes import settings as settings_routes


def test_registry_attrs_exist_on_settings():
    for spec in SETTING_SPECS:
        assert hasattr(settings, spec.attr), spec.attr
    for spec in UNIVERSE_SPECS:
        assert getattr(settings, spec.attr) == spec.default


def test_secret_fields_derived_from_registry():
    assert "OPENAI_API_KEY" in SECRET_FIELDS
    assert "QUBE_API_KEY" in SECRET_FIELDS
    assert "UNIVERSE_MIN_LIST_DAYS" not in SECRET_FIELDS


def test_update_env_file_is_atomic_and_importable(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# keep\nAI_PROVIDER=old\n", encoding="utf-8")
    update_env_file(
        {
            "AI_PROVIDER": "new",
            "UNIVERSE_MIN_LIST_DAYS": "730",
            "QZ_BASE_URL": "https://example.com/a#b",
        },
        env,
    )
    text = env.read_text(encoding="utf-8")
    assert "# keep" in text
    assert "AI_PROVIDER=new" in text
    assert "UNIVERSE_MIN_LIST_DAYS=730" in text
    assert 'QZ_BASE_URL="https://example.com/a#b"' in text
    if os.name == "posix":
        assert stat.S_IMODE(env.stat().st_mode) == 0o600


def test_delete_env_keys_preserves_comments(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# c\nA=1\nB=2\n", encoding="utf-8")
    assert delete_env_keys(["A"], env) is True
    text = env.read_text(encoding="utf-8")
    assert "A=1" not in text and "B=2" in text and "# c" in text


def test_update_config_universe_fields(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("", encoding="utf-8")
    monkeypatch.setattr(settings_routes, "ENV_FILE", env)
    monkeypatch.setattr(settings, "universe_exclude_st", True, raising=False)
    monkeypatch.setattr(settings, "universe_min_list_days", 730, raising=False)

    body = settings_routes.ConfigUpdate(
        universe_exclude_st=False, universe_min_list_days=500
    )
    asyncio.run(settings_routes.update_config(body))

    text = env.read_text(encoding="utf-8")
    assert "UNIVERSE_EXCLUDE_ST=false" in text
    assert "UNIVERSE_MIN_LIST_DAYS=500" in text
    assert settings.universe_exclude_st is False
    assert settings.universe_min_list_days == 500


def test_update_config_rejects_invalid_universe_days(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("", encoding="utf-8")
    monkeypatch.setattr(settings_routes, "ENV_FILE", env)
    with pytest.raises(ValidationError):
        settings_routes.ConfigUpdate(universe_min_list_days=9999)
