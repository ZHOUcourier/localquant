"""Token 估算与模型上下文窗口（QUBE 上下文/用量显示，无第三方依赖）

- estimate_tokens：本地启发式估算（中韩日按字符、其余按词近似）。
  用于：供应商不返回 usage 时的兜底、CLI 引擎用量、以及上下文的近似拆分；
  真实数值以 API 返回的 usage 为准（include_usage）。
- model_context_window：常见模型名 → 上下文窗口（token），未知回退默认值，
  供前端展示「已用 / 窗口」进度条与自动压缩判断。
"""

import re

# CJK / 假名这类高信息密度字符：单字近似计 ~1 token 的换算系数
_CJK_RE = re.compile(
    r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3040-\u30ff]"
)
_WS_RE = re.compile(r"\s")

_CJK_PER_TOKEN = 0.85
_ASCII_PER_TOKEN = 0.28
_BASE_OVERHEAD = 4

DEFAULT_CONTEXT_WINDOW = 128_000

# 模型名（子串，长关键字优先）→ 上下文窗口（token，近似）
_MODEL_WINDOWS: dict[str, int] = {
    # 长关键字优先被匹配，避免 "gpt-4" 误中 "gpt-4o"
    "gpt-4.1": 1_000_000,
    "gpt-5": 400_000,
    "gemini": 1_000_000,
    "claude-sonnet-4": 200_000,
    "claude": 200_000,
    "gpt-4o": 128_000,
    "gpt-4": 128_000,
    "gpt-4o-mini": 128_000,
    "deepseek-chat": 128_000,
    "deepseek-reasoner": 128_000,
    "deepseek": 128_000,
    "qwen2.5": 131_072,
    "qwen-max": 131_072,
    "qwen": 131_072,
    "kimi": 128_000,
    "glm-4.5": 128_000,
    "glm": 128_000,
    "doubao": 128_000,
    "llama-3.1": 128_000,
    "o4": 200_000,
    "o3": 200_000,
    "o1": 200_000,
}


def estimate_tokens(text: str) -> int:
    """本地启发式估算 token 数（近似）。"""
    if not text:
        return 0
    cjk = len(_CJK_RE.findall(text))
    non_cjk = len(_WS_RE.sub("", text)) - cjk
    return max(
        1, int(cjk * _CJK_PER_TOKEN + non_cjk * _ASCII_PER_TOKEN) + _BASE_OVERHEAD
    )


def model_context_window(model: str) -> int:
    """模型 → 上下文窗口上限（token）。未知模型回退默认值。"""
    low = model.lower()
    for key in sorted(_MODEL_WINDOWS, key=len, reverse=True):
        if key in low:
            return _MODEL_WINDOWS[key]
    return DEFAULT_CONTEXT_WINDOW