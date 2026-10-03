"""密钥入系统凭据库（keyring）+ 永不回显 回归测试

覆盖：
- .env 明文密钥 → OS 凭据库一次性迁移（成功后才删行、保留注释、幂等）
- 凭据库不可用时跳过迁移（保持 .env 行为）
- store_secret 写凭据库并清除 .env 明文；delete_env_key 删行保留注释
- 配置 GET 永不回显（无掩码字段）、PUT 密钥走凭据库、QZ 密钥可配置
- 凭据库不可用回退 .env

使用 fake keyring backend（keyring.set_keyring），不触碰真实系统凭据库。
"""

import asyncio
from typing import ClassVar

import keyring
import keyring.backend
import pytest
from keyring.backends import fail as fail_backend

from backend.routes import settings as settings_routes
from backend.secrets import (
    SERVICE,
    delete_env_key,
    get_secret,
    is_available,
    migrate_env_secrets,
    store_secret,
)


class FakeKeyring(keyring.backend.KeyringBackend):
    """内存 keyring 后端（priority 高于 fail 后端即可用）"""

    priority = 1
    store: ClassVar[dict[tuple[str, str], str]] = {}

    def set_password(self, service, username, password):
        FakeKeyring.store[(service, username)] = password

    def get_password(self, service, username):
        return FakeKeyring.store.get((service, username))

    def delete_password(self, service, username):
        FakeKeyring.store.pop((service, username), None)


@pytest.fixture()
def fake_keyring(monkeypatch):
    FakeKeyring.store = {}
    keyring.set_keyring(FakeKeyring())
    yield FakeKeyring
    keyring.set_keyring(fail_backend.Keyring())


ENV_BODY = (
    "# 注释行保留\n"
    "AI_PROVIDER=opencode-zen\n"
    "OPENAI_API_KEY=sk-test-1234567890\n"
    "QZ_ACCESS_KEY=qz-ak-1\n"
    "\n"
    "# 尾部注释\n"
)


def test_is_available_with_fake_backend(fake_keyring):
    assert is_available() is True


def test_migrate_env_secrets_moves_and_removes(fake_keyring, tmp_path):
    env = tmp_path / ".env"
    env.write_text(ENV_BODY, encoding="utf-8")

    migrated = migrate_env_secrets(env)

    assert sorted(migrated) == ["OPENAI_API_KEY", "QZ_ACCESS_KEY"]
    assert fake_keyring.store[(SERVICE, "OPENAI_API_KEY")] == "sk-test-1234567890"
    text = env.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY" not in text
    assert "QZ_ACCESS_KEY" not in text
    assert "AI_PROVIDER=opencode-zen" in text  # 非密钥保留
    assert "# 注释行保留" in text and "# 尾部注释" in text
    # 幂等：再跑一次无事发生
    assert migrate_env_secrets(env) == []


def test_migrate_env_secrets_skips_when_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr("backend.secrets.is_available", lambda: False)
    env = tmp_path / ".env"
    env.write_text(ENV_BODY, encoding="utf-8")

    assert migrate_env_secrets(env) == []
    assert "OPENAI_API_KEY=sk-test-1234567890" in env.read_text(encoding="utf-8")


def test_store_secret_writes_keyring_and_clears_env(fake_keyring, tmp_path):
    env = tmp_path / ".env"
    env.write_text("OPENAI_API_KEY=old\nX=1\n", encoding="utf-8")

    assert store_secret("OPENAI_API_KEY", "new-secret", env) is True
    assert get_secret("OPENAI_API_KEY") == "new-secret"
    text = env.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY" not in text and "X=1" in text


def test_store_secret_returns_false_when_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr("backend.secrets.is_available", lambda: False)
    env = tmp_path / ".env"
    env.write_text("X=1\n", encoding="utf-8")

    assert store_secret("OPENAI_API_KEY", "v", env) is False
    assert "X=1" in env.read_text(encoding="utf-8")  # .env 未被动过


def test_delete_env_key_keeps_other_lines(fake_keyring, tmp_path):
    env = tmp_path / ".env"
    env.write_text(ENV_BODY, encoding="utf-8")

    assert delete_env_key("QZ_ACCESS_KEY", env) is True
    text = env.read_text(encoding="utf-8")
    assert "QZ_ACCESS_KEY" not in text
    assert "OPENAI_API_KEY=sk-test-1234567890" in text
    assert "# 注释行保留" in text
    assert delete_env_key("NOT_EXIST", env) is False


# ── 配置路由：永不回显 + 密钥写入路由 ──────────────────────────


@pytest.fixture()
def env_file(tmp_path, monkeypatch):
    p = tmp_path / ".env"
    p.write_text("", encoding="utf-8")
    monkeypatch.setattr(settings_routes, "ENV_FILE", p)
    return p


def test_get_config_never_echoes_key(fake_keyring, env_file, monkeypatch):
    from backend.config import settings as app_settings

    monkeypatch.setattr(app_settings, "openai_api_key", "sk-abcdef123456", raising=False)
    monkeypatch.setattr(app_settings, "qz_access_key", "", raising=False)
    monkeypatch.setattr(app_settings, "qz_sign_secret", "", raising=False)

    data = asyncio.run(settings_routes.get_config())
    assert "openai_api_key_masked" not in data
    assert "sk-abcdef123456" not in str(data)
    assert data["openai_api_key_set"] is True
    assert data["qz_access_key_set"] is False and data["qz_sign_secret_set"] is False
    assert data["secrets_backend"] == "os_keychain"


def test_update_config_routes_secret_to_keyring(fake_keyring, env_file):
    body = settings_routes.ConfigUpdate(
        openai_api_key="sk-new-key-1", qz_access_key="qz-ak-2"
    )
    result = asyncio.run(settings_routes.update_config(body))

    assert get_secret("OPENAI_API_KEY") == "sk-new-key-1"
    assert get_secret("QZ_ACCESS_KEY") == "qz-ak-2"
    assert env_file.read_text(encoding="utf-8") == ""  # 明文不落 .env
    assert "OPENAI_API_KEY" in result["updated"] and "QZ_ACCESS_KEY" in result["updated"]


def test_update_config_falls_back_to_env_without_keyring(monkeypatch, fake_keyring, env_file):
    monkeypatch.setattr("backend.secrets.is_available", lambda: False)
    body = settings_routes.ConfigUpdate(openai_api_key="sk-fallback-1")
    result = asyncio.run(settings_routes.update_config(body))

    assert "OPENAI_API_KEY=sk-fallback-1" in env_file.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY" in result["updated"]


def test_update_config_empty_secret_is_noop(fake_keyring, env_file, monkeypatch):
    from backend.config import settings as app_settings

    monkeypatch.setattr(app_settings, "qube_api_key", "keep-me", raising=False)
    body = settings_routes.ConfigUpdate(openai_api_key="")
    asyncio.run(settings_routes.update_config(body))

    assert get_secret("OPENAI_API_KEY") == ""  # 空串不写入凭据库
    assert env_file.read_text(encoding="utf-8") == ""


# ── QUBE 配置路由 ──────────────────────────────────────────────


def test_qube_get_config_never_echoes_key(fake_keyring, monkeypatch):
    from backend.config import settings as app_settings
    from backend.routes import qube as qube_routes

    monkeypatch.setattr(app_settings, "qube_api_key", "qube-secret-123", raising=False)
    data = asyncio.run(qube_routes.get_qube_config())

    assert "qube_api_key_masked" not in data
    assert "qube-secret-123" not in str(data)
    assert data["qube_api_key_set"] is True


def test_qube_update_config_routes_key_to_keyring(fake_keyring, env_file):
    from backend.routes import qube as qube_routes

    body = qube_routes.QubeConfigUpdate(qube_api_key="qube-new-key", qube_model="m1")
    result = asyncio.run(qube_routes.update_qube_config(body))

    assert get_secret("QUBE_API_KEY") == "qube-new-key"
    assert "QUBE_API_KEY" not in env_file.read_text(encoding="utf-8")
    assert "QUBE_API_KEY" in result["updated"] and "QUBE_MODEL" in result["updated"]
