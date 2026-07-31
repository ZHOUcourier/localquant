"""AI 供应商预置与本机 CLI 工具注册表（设置页 AI 与 QUBE Agent 共用）

供应商清单对齐 models.dev（opencode 供应商注册表）：预置供应商自带 Base URL，
用户只需填 API Key；仅「自定义（BYOK）」需要自填 Base URL。
CLI 工具按用户偏好顺序排列，通过 shutil.which 探测本机可用性。
"""

import asyncio
import shutil
from typing import Optional

# 预置供应商（有序）：id → {label, base_url, model, models}
# base_url 均为 OpenAI 兼容 chat/completions 端点前缀；models 为下拉可选清单
# （来自 models.dev 快照，按发布时间降序，已剔除图像/视频类模型）
PROVIDER_PRESETS: dict[str, dict] = {
    "opencode-zen": {
        "label": "OpenCode Zen",
        "base_url": "https://opencode.ai/zen/v1",
        "model": "claude-sonnet-5",
        "models": [
            "claude-opus-5",
            "claude-sonnet-5",
            "gpt-5.6-sol",
            "gpt-5.6-luna",
            "gpt-5.6-terra",
            "grok-4.5",
            "gemini-3.6-flash",
            "gemini-3.5-flash-lite",
            "kimi-k3",
            "glm-5.2",
            "kimi-k2.7-code",
            "ling-3.0-flash-free",
            "laguna-s-2.1-free",
            "hy3-free",
        ],
    },
    "opencode-go": {
        "label": "OpenCode Go",
        "base_url": "https://opencode.ai/zen/go/v1",
        "model": "kimi-k3",
        "models": [
            "kimi-k3",
            "grok-4.5",
            "hy3",
            "glm-5.2",
            "kimi-k2.7-code",
            "qwen3.7-plus",
            "minimax-m3",
            "qwen3.7-max",
            "deepseek-v4-flash",
            "deepseek-v4-pro",
            "mimo-v2.5",
            "mimo-v2.5-pro",
            "kimi-k2.6",
            "glm-5.1",
        ],
    },
    "deepseek": {
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "models": [
            "deepseek-v4-flash",
            "deepseek-v4-pro",
            "deepseek-chat",
            "deepseek-reasoner",
        ],
    },
    "zhipuai": {
        "label": "Zhipu AI",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-5",
        "models": [
            "glm-5.2",
            "glm-5.1",
            "glm-5",
            "glm-5v-turbo",
            "glm-4.7",
            "glm-4.7-flashx",
            "glm-4.7-flash",
            "glm-4.6",
            "glm-4.6v",
            "glm-4.5",
            "glm-4.5-air",
            "glm-4.5-flash",
        ],
    },
    "zhipuai-coding-plan": {
        "label": "Zhipu AI Coding Plan",
        "base_url": "https://open.bigmodel.cn/api/coding/paas/v4",
        "model": "glm-5.1",
        "models": [
            "glm-5.2",
            "glm-5.1",
            "glm-5-turbo",
            "glm-5v-turbo",
            "glm-4.7",
            "glm-4.6v",
            "glm-4.5-air",
        ],
    },
    "zai": {
        "label": "Z.AI",
        "base_url": "https://api.z.ai/api/paas/v4",
        "model": "glm-5",
        "models": [
            "glm-5.2",
            "glm-5.1",
            "glm-5",
            "glm-5-turbo",
            "glm-5v-turbo",
            "glm-4.7",
            "glm-4.7-flash",
            "glm-4.7-flashx",
            "glm-4.6",
            "glm-4.6v",
            "glm-4.5",
            "glm-4.5-air",
            "glm-4.5-flash",
        ],
    },
    "zai-coding-plan": {
        "label": "Z.AI Coding Plan",
        "base_url": "https://api.z.ai/api/coding/paas/v4",
        "model": "glm-5.1",
        "models": [
            "glm-5.2",
            "glm-5.1",
            "glm-5-turbo",
            "glm-5v-turbo",
            "glm-4.7",
            "glm-4.5-air",
        ],
    },
    "kimi-for-coding": {
        "label": "Kimi For Coding",
        "base_url": "https://api.kimi.com/coding/v1",
        "model": "kimi-for-coding",
        "models": ["k3", "k3-256k", "kimi-for-coding", "kimi-for-coding-highspeed"],
    },
    "alibaba-cn": {
        "label": "Alibaba (China)",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen3.7-plus",
        "models": [
            "qwen3.7-plus",
            "qwen3.7-max",
            "qwen3.6-flash",
            "qwen3.6-plus",
            "qwen3.5-plus",
            "qwen3.5-flash",
            "glm-5.2",
            "glm-5.1",
            "deepseek-v4-flash",
            "deepseek-v4-pro",
            "kimi-k2.6",
            "qwen-max",
        ],
    },
    "alibaba-token-plan-cn": {
        "label": "Alibaba Token Plan (China)",
        "base_url": "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
        "model": "qwen3.7-plus",
        "models": [
            "qwen3.8-max-preview",
            "qwen3.7-plus",
            "qwen3.7-max",
            "qwen3.6-flash",
            "glm-5.2",
            "kimi-k2.7-code",
            "kimi-k2.6",
            "deepseek-v4-flash",
            "deepseek-v4-pro",
        ],
    },
    "alibaba-coding-plan-cn": {
        "label": "Alibaba Coding Plan (China)",
        "base_url": "https://coding.dashscope.aliyuncs.com/v1",
        "model": "qwen3-coder-plus",
        "models": [
            "qwen3.7-plus",
            "qwen3.7-max",
            "qwen3.6-flash",
            "qwen3.6-plus",
            "qwen3.5-plus",
            "qwen3-coder-next",
            "qwen3-coder-plus",
            "MiniMax-M2.5",
            "glm-5",
            "glm-4.7",
            "kimi-k2.5",
        ],
    },
    "moonshotai-cn": {
        "label": "Moonshot AI (China)",
        "base_url": "https://api.moonshot.cn/v1",
        "model": "kimi-k2.5",
        "models": [
            "kimi-k3",
            "kimi-k2.7-code",
            "kimi-k2.7-code-highspeed",
            "kimi-k2.6",
            "kimi-k2.5",
            "kimi-k2-thinking",
            "kimi-k2-thinking-turbo",
            "kimi-k2-turbo-preview",
            "kimi-k2-0905-preview",
            "kimi-k2-0711-preview",
        ],
    },
    "minimax-cn": {
        "label": "MiniMax (minimaxi.com)",
        "base_url": "https://api.minimaxi.com/v1",
        "model": "MiniMax-M2.5",
        "models": [
            "MiniMax-M3",
            "MiniMax-M2.7",
            "MiniMax-M2.7-highspeed",
            "MiniMax-M2.5",
            "MiniMax-M2.5-highspeed",
            "MiniMax-M2.1",
            "MiniMax-M2",
        ],
    },
    "minimax-cn-token-plan": {
        "label": "MiniMax Token Plan (minimaxi.com)",
        "base_url": "https://api.minimaxi.com/v1",
        "model": "MiniMax-M2.5",
        "models": [
            "MiniMax-M3",
            "MiniMax-M2.7",
            "MiniMax-M2.7-highspeed",
            "MiniMax-M2.5",
            "MiniMax-M2.5-highspeed",
            "MiniMax-M2.1",
            "MiniMax-M2",
        ],
    },
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "models": [
            "gpt-5.6-sol",
            "gpt-5.6-luna",
            "gpt-5.6",
            "gpt-5.6-terra",
            "gpt-5.5-pro",
            "gpt-5.5",
            "gpt-5.4",
            "gpt-5.4-pro",
            "gpt-5.4-mini",
            "gpt-5.4-nano",
            "gpt-4o",
            "gpt-4o-mini",
        ],
    },
    # 自定义 BYOK：唯一需要用户自填 Base URL 的选项（模型也手输）
    "custom": {"label": "自定义（BYOK）", "base_url": "", "model": "", "models": []},
}

# 旧版供应商 id 兼容映射（.env 中可能残留）
LEGACY_PROVIDER_ALIASES = {
    "moonshot": "moonshotai-cn",
    "qwen": "alibaba-cn",
    "zhipu": "zhipuai",
}

# 本机 CLI 工具（有序）：id → {label, bin, args}；args 中 {prompt} 会被替换
CLI_TOOLS: dict[str, dict] = {
    "claude": {
        "label": "Claude Code",
        "bin": "claude",
        "args": ["-p", "--output-format", "text", "{prompt}"],
    },
    "codex": {"label": "Codex CLI", "bin": "codex", "args": ["exec", "{prompt}"]},
    "coder": {"label": "Coder", "bin": "coder", "args": ["{prompt}"]},
    "qoder": {"label": "Qoder CLI", "bin": "qoder", "args": ["-p", "{prompt}"]},
    "opencode": {"label": "OpenCode", "bin": "opencode", "args": ["run", "{prompt}"]},
    "cursor-agent": {
        "label": "Cursor Agent",
        "bin": "cursor-agent",
        "args": ["-p", "{prompt}"],
    },
    "hermes": {"label": "Hermes", "bin": "hermes", "args": ["{prompt}"]},
    "trae": {"label": "Trae CLI", "bin": "trae", "args": ["{prompt}"]},
    "kimi": {"label": "Kimi CLI", "bin": "kimi", "args": ["-p", "{prompt}"]},
    "codebuddy": {
        "label": "CodeBuddy Code",
        "bin": "codebuddy",
        "args": ["-p", "{prompt}"],
    },
    "pi": {"label": "Pi Agent", "bin": "pi", "args": ["{prompt}"]},
}

# 每个 CLI 工具的模型/强度参数元数据（与 CLI_TOOLS 分开维护，便于扩展）：
#   model_flag  : 模型参数 flag（如 ["-m"] / ["--model"]）；None 表示该工具不注入模型（用其自身默认）
#   effort      : 强度写法模式 — variant(--variant L)/flag(--effort L)/config(-c model_reasoning_effort=L)/suffix(model:L)/None
#   models      : 建议模型下拉（前端仍可自由输入；空列表=仅自由输入）
# 已核实本机已装工具的 --help；opencode/claude/pi 准确，codex/gemini/cursor-agent 依公开文档。
CLI_TOOL_META: dict[str, dict] = {
    "claude": {
        "model_flag": ["--model"],
        "effort": "flag",
        "models": ["sonnet", "opus", "haiku"],
    },
    "codex": {
        "model_flag": ["-m"],
        "effort": "config",
        "models": ["gpt-5-codex", "gpt-5", "o4-mini"],
    },
    "opencode": {
        "model_flag": ["-m"],
        "effort": "variant",
        "models": [
            "anthropic/claude-sonnet-4-5",
            "openai/gpt-5",
            "google/gemini-2.5-pro",
        ],
    },
    "pi": {
        "model_flag": ["--model"],
        "effort": "suffix",
        "models": ["sonnet", "opus"],
    },
    "cursor-agent": {"model_flag": ["--model"], "effort": None, "models": []},
    "gemini": {"model_flag": ["-m"], "effort": None, "models": []},
}


def _cli_meta(cli_id: str) -> dict:
    return CLI_TOOL_META.get(cli_id, {})


def _apply_cli_model_effort(
    cli_id: str, model: str, effort: str
) -> tuple[str, list[str]]:
    """根据工具元数据，把 model/effort 转为（可能改写的 model, 额外 flag 列表）

    effort 为空/"default" 时不注入（用 CLI 自身默认）；suffix 模式把强度拼入模型串。
    """
    meta = _cli_meta(cli_id)
    model = (model or "").strip()
    effort = (effort or "").strip()
    use_effort = effort and effort != "default"
    extra: list[str] = []
    mode = meta.get("effort")
    if use_effort and mode == "suffix" and model:
        model = f"{model}:{effort}"
    elif use_effort and mode == "variant":
        extra += ["--variant", effort]
    elif use_effort and mode == "flag":
        extra += ["--effort", effort]
    elif use_effort and mode == "config":
        extra += ["-c", f"model_reasoning_effort={effort}"]
    model_flag = meta.get("model_flag")
    model_args = [*model_flag, model] if (model and model_flag) else []
    return model, [*model_args, *extra]


def resolve_provider(provider: str) -> str:
    """旧版供应商 id → 新 id；未知 id 归为 custom"""
    provider = LEGACY_PROVIDER_ALIASES.get(provider, provider)
    return provider if provider in PROVIDER_PRESETS else "custom"


# 推理强度选项（对齐 OpenAI reasoning_effort 语义）
EFFORT_LEVELS = ["minimal", "low", "medium", "high"]


def apply_effort(payload: dict, effort: str) -> dict:
    """把推理强度写入 OpenAI 兼容请求体（reasoning_effort）

    medium 为默认不下发（兼容不支持该字段的供应商）；其余等级显式下发。
    不支持的服务端会忽略未知字段，不影响其他调用。
    """
    if effort and effort in EFFORT_LEVELS and effort != "medium":
        payload["reasoning_effort"] = effort
    return payload


def list_providers() -> list[dict]:
    """有序供应商清单（供前端渲染；custom 需自填 Base URL，models 供下拉选择）"""
    return [
        {
            "id": pid,
            "label": p["label"],
            "base_url": p["base_url"],
            "model": p["model"],
            "models": p.get("models", []),
            "byok": pid == "custom",
        }
        for pid, p in PROVIDER_PRESETS.items()
    ]


def list_cli_tools() -> list[dict]:
    """有序 CLI 工具清单 + 本机可用性探测 + 模型/强度元数据"""
    tools = []
    for cid, t in CLI_TOOLS.items():
        meta = _cli_meta(cid)
        tools.append(
            {
                "id": cid,
                "label": t["label"],
                "bin": t["bin"],
                "available": shutil.which(t["bin"]) is not None,
                "models": meta.get("models", []),
                "supports_model": meta.get("model_flag") is not None,
                "supports_effort": meta.get("effort") is not None,
            }
        )
    return tools


def build_cli_command(
    cli_id: str, prompt: str, model: str = "", effort: str = ""
) -> Optional[list[str]]:
    """CLI id + 提示词(+模型/强度) → 完整命令行；未知/不可用返回 None

    model/effort 按工具元数据注入到位置参数 prompt 之前（flag 先于正文）；
    为空/“default”时不注入，用 CLI 自身默认。
    """
    tool = CLI_TOOLS.get(cli_id)
    if not tool:
        return None
    binary = shutil.which(tool["bin"])
    if not binary:
        return None
    _model, extra = _apply_cli_model_effort(cli_id, model, effort)
    out = [binary]
    for a in tool["args"]:
        if a == "{prompt}":
            out.extend(extra)  # 模型/强度 flag 注入在位置参数之前
            out.append(prompt)
        else:
            out.append(a.replace("{prompt}", prompt))
    return out


async def run_cli(
    cli_id: str, prompt: str, timeout: float = 300.0, model: str = "", effort: str = ""
) -> str:
    """一次性运行 CLI（print 模式），返回 stdout 文本"""
    cmd = build_cli_command(cli_id, prompt, model, effort)
    if not cmd:
        raise RuntimeError(f"CLI 工具不可用: {cli_id}（请确认已安装并在 PATH 中）")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.DEVNULL,  # 非 TTY 下部分 CLI 会等待 stdin，必须显式关闭
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError(f"CLI 执行超时（{int(timeout)}s）: {cli_id}")
    if proc.returncode != 0 and not stdout:
        raise RuntimeError(
            f"CLI 执行失败 (exit {proc.returncode}): "
            f"{(stderr or b'').decode(errors='replace')[:300]}"
        )
    return (stdout or b"").decode(errors="replace").strip()


async def stream_cli(cli_id: str, prompt: str, model: str = "", effort: str = ""):
    """流式运行 CLI：逐段 yield stdout 文本（QUBE 对话使用）"""
    cmd = build_cli_command(cli_id, prompt, model, effort)
    if not cmd:
        raise RuntimeError(f"CLI 工具不可用: {cli_id}（请确认已安装并在 PATH 中）")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.DEVNULL,  # 非 TTY 下部分 CLI 会等待 stdin，必须显式关闭
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert proc.stdout is not None
    try:
        while True:
            chunk = await proc.stdout.read(256)
            if not chunk:
                break
            yield chunk.decode(errors="replace")
        await proc.wait()
        if proc.returncode != 0:
            err = (
                (await proc.stderr.read()).decode(errors="replace")[:300]
                if proc.stderr
                else ""
            )
            if err:
                yield f"\n[CLI exit {proc.returncode}] {err}"
    finally:
        if proc.returncode is None:
            proc.kill()
