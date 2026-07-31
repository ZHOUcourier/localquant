"""CLI 工具模型/强度注入回归测试（build_cli_command）

验证各 CLI 的 model/effort 按其元数据正确注入到位置参数之前，
"默认/空"时不注入，未知工具/未安装返回 None。不发任何真实模型调用。
"""

from unittest import mock

from backend.services import ai_providers as ap


def _cmd(cli_id, prompt="hi", model="", effort=""):
    """伪造 shutil.which 让工具"可用"，只验证命令拼装（不真正执行）"""
    with mock.patch.object(ap.shutil, "which", return_value=f"/usr/bin/{cli_id}"):
        return ap.build_cli_command(cli_id, prompt, model, effort)


def test_claude_model_and_effort_flags():
    cmd = _cmd("claude", model="sonnet", effort="high")
    # claude: --model <m> --effort <level>，注入在位置参数 prompt 之前
    assert "--model" in cmd and cmd[cmd.index("--model") + 1] == "sonnet"
    assert "--effort" in cmd and cmd[cmd.index("--effort") + 1] == "high"
    assert cmd[-1] == "hi"


def test_opencode_uses_variant_for_effort():
    cmd = _cmd("opencode", model="openai/gpt-5", effort="high")
    assert "-m" in cmd and cmd[cmd.index("-m") + 1] == "openai/gpt-5"
    assert "--variant" in cmd and cmd[cmd.index("--variant") + 1] == "high"


def test_pi_embeds_effort_in_model_suffix():
    cmd = _cmd("pi", model="sonnet", effort="high")
    # pi: 强度以 model:level 后缀表达，不单独加 flag
    assert "--model" in cmd and cmd[cmd.index("--model") + 1] == "sonnet:high"
    assert "--variant" not in cmd and "--effort" not in cmd


def test_codex_uses_config_override_for_effort():
    cmd = _cmd("codex", model="gpt-5", effort="low")
    assert "-m" in cmd and cmd[cmd.index("-m") + 1] == "gpt-5"
    assert "-c" in cmd and cmd[cmd.index("-c") + 1] == "model_reasoning_effort=low"


def test_default_effort_and_empty_model_inject_nothing():
    cmd = _cmd("claude", model="", effort="default")
    assert "--model" not in cmd and "--effort" not in cmd
    assert cmd[-1] == "hi"


def test_model_only_no_effort():
    cmd = _cmd("opencode", model="openai/gpt-5", effort="default")
    assert "-m" in cmd and "--variant" not in cmd


def test_unknown_tool_returns_none():
    assert _cmd("nope", model="x") is None


def test_uninstalled_tool_returns_none():
    with mock.patch.object(ap.shutil, "which", return_value=None):
        assert ap.build_cli_command("claude", "hi", "sonnet", "high") is None


def test_list_cli_tools_exposes_metadata():
    tools = {t["id"]: t for t in ap.list_cli_tools()}
    assert tools["claude"]["supports_effort"] is True
    assert tools["claude"]["supports_model"] is True
    assert "sonnet" in tools["claude"]["models"]
    # 未配元数据的工具：不支持模型/强度注入
    assert tools["trae"]["supports_effort"] is False
    assert tools["trae"]["supports_model"] is False
