"""集中配置声明 — 环境变量键、类型、默认值、分组与密钥标记的唯一来源。

设置路由、`.env` 写入、密钥迁移都从这份声明派生，避免新增配置时
在 Settings / 设置路由 / secrets 之间反复手写映射。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any

from pydantic import Field, TypeAdapter


def _bounded_int(min_value: int, max_value: int):
    return Annotated[int, Field(ge=min_value, le=max_value)]


@dataclass(frozen=True)
class SettingSpec:
    env_key: str
    attr: str
    type: Any
    default: Any
    group: str
    title: str
    description: str = ""
    secret: bool = False
    editable: bool = True
    reload: str = "live"  # live=即时生效 / restart=需重启
    choices: tuple[str, ...] = ()

    def coerce(self, value: Any) -> Any:
        if self.choices and str(value) not in self.choices:
            raise ValueError(
                f"{self.env_key} 需为 {'/'.join(self.choices)}，收到 {value!r}"
            )
        return TypeAdapter(self.type).validate_python(value)

    def env_value(self, value: Any) -> str:
        """把配置值写成适合 .env 的文本。"""
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)


_PORT = _bounded_int(1, 65535)
_LIST_DAYS = _bounded_int(0, 3650)

SETTING_SPECS: tuple[SettingSpec, ...] = (
    # ── QMT ────────────────────────────────────────────────
    SettingSpec("QMT_PATH", "qmt_path", str, "", "qmt", "MiniQMT 路径",
                reload="restart"),
    SettingSpec("QMT_DATA_DIR", "qmt_data_dir", str, "", "qmt", "QMT 数据目录",
                reload="restart"),
    # ── AI 辅助 ────────────────────────────────────────────
    SettingSpec("OPENAI_API_KEY", "openai_api_key", str, "", "ai", "API Key",
                secret=True),
    SettingSpec("OPENAI_BASE_URL", "openai_base_url", str, "", "ai", "Base URL"),
    SettingSpec("AI_PROVIDER", "ai_provider", str, "opencode-zen", "ai", "供应商"),
    SettingSpec("AI_MODEL", "ai_model", str, "", "ai", "模型"),
    SettingSpec("AI_EFFORT", "ai_effort", str, "medium", "ai", "推理强度",
                choices=("minimal", "low", "medium", "high")),
    SettingSpec("AI_ENGINE", "ai_engine", str, "api", "ai", "接入方式",
                choices=("api", "cli")),
    SettingSpec("AI_CLI", "ai_cli", str, "claude", "ai", "CLI 工具"),
    SettingSpec("AI_CLI_MODEL", "ai_cli_model", str, "", "ai", "CLI 模型"),
    SettingSpec("AI_CLI_EFFORT", "ai_cli_effort", str, "default", "ai", "CLI 强度",
                choices=("default", "minimal", "low", "medium", "high")),
    # ── QuantZone ──────────────────────────────────────────
    SettingSpec("QZ_ACCESS_KEY", "qz_access_key", str, "", "quantzone", "Access Key",
                secret=True),
    SettingSpec("QZ_SIGN_SECRET", "qz_sign_secret", str, "", "quantzone", "Sign Secret",
                secret=True),
    SettingSpec("QZ_BASE_URL", "qz_base_url", str, "https://api.quantzone.tech",
                "quantzone", "Base URL"),
    # ── QUBE（QUBE 页单独展示，但仍走同一套存储） ──────────
    SettingSpec("QUBE_PROVIDER", "qube_provider", str, "opencode-zen", "qube", "供应商"),
    SettingSpec("QUBE_MODEL", "qube_model", str, "", "qube", "模型"),
    SettingSpec("QUBE_EFFORT", "qube_effort", str, "medium", "qube", "推理强度",
                choices=("minimal", "low", "medium", "high")),
    SettingSpec("QUBE_API_KEY", "qube_api_key", str, "", "qube", "API Key",
                secret=True),
    SettingSpec("QUBE_BASE_URL", "qube_base_url", str, "", "qube", "Base URL"),
    SettingSpec("QUBE_ENGINE", "qube_engine", str, "api", "qube", "接入方式",
                choices=("api", "cli")),
    SettingSpec("QUBE_CLI", "qube_cli", str, "claude", "qube", "CLI 工具"),
    SettingSpec("QUBE_CLI_MODEL", "qube_cli_model", str, "", "qube", "CLI 模型"),
    SettingSpec("QUBE_CLI_EFFORT", "qube_cli_effort", str, "default", "qube", "CLI 强度",
                choices=("default", "minimal", "low", "medium", "high")),
    # ── 服务 ───────────────────────────────────────────────
    SettingSpec("BACKEND_PORT", "backend_port", _PORT, 8000, "service", "后端端口",
                reload="restart"),
    SettingSpec("FRONTEND_PORT", "frontend_port", _PORT, 5173, "service", "前端端口",
                reload="restart"),
    # ── 股票池约束（非密钥；全局默认值） ───────────────────
    SettingSpec("UNIVERSE_EXCLUDE_ST", "universe_exclude_st", bool, True, "universe",
                "剔除 ST/*ST",
                "按逐日 as-of 名称状态排除风险警示股票；无历史快照的区间无法回溯"),
    SettingSpec("UNIVERSE_EXCLUDE_NEW", "universe_exclude_new", bool, True, "universe",
                "剔除次新股"),
    SettingSpec("UNIVERSE_MIN_LIST_DAYS", "universe_min_list_days", _LIST_DAYS, 730,
                "universe", "上市至少天数",
                "按自然日计算；730 约等于两年，0 表示不按上市时间过滤"),
    SettingSpec("UNIVERSE_INCLUDE_BJ", "universe_include_bj", bool, True, "universe",
                "包含北交所"),
    SettingSpec("UNIVERSE_EXCLUDE_DELISTING", "universe_exclude_delisting", bool, True,
                "universe", "剔除退市整理期",
                "仅按当日名称状态排除，不用今天的退市清单回溯历史"),
    # ── 离线脚本 token ─────────────────────────────────────
    SettingSpec("PANDA_TOKEN", "panda_token", str, "", "script", "PandaAI Token",
                secret=True, editable=False),
)

SPEC_BY_ATTR: dict[str, SettingSpec] = {s.attr: s for s in SETTING_SPECS}
SPEC_BY_ENV: dict[str, SettingSpec] = {s.env_key: s for s in SETTING_SPECS}
SECRET_FIELDS: dict[str, str] = {
    s.env_key: s.attr for s in SETTING_SPECS if s.secret
}
EDITABLE_SPECS: tuple[SettingSpec, ...] = tuple(
    s for s in SETTING_SPECS if s.editable and s.group != "qube"
)
QUBE_SPECS: tuple[SettingSpec, ...] = tuple(
    s for s in SETTING_SPECS if s.group == "qube"
)
UNIVERSE_SPECS: tuple[SettingSpec, ...] = tuple(
    s for s in SETTING_SPECS if s.group == "universe"
)
