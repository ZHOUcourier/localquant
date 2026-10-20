from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

from backend.config_registry import SPEC_BY_ATTR

# .env 为配置的唯一事实来源：设置页写入 .env，读取时也应优先于 shell 环境变量，
# 否则残留的 AI_*/QUBE_* 环境变量会静默覆盖 .env，导致设置页显示与持久化不一致。
load_dotenv(override=True)


def _default(attr: str):
    """配置默认值统一取自 config_registry，避免 Settings 与设置页各写一份。"""
    return SPEC_BY_ATTR[attr].default


class Settings(BaseSettings):
    # 项目基础
    project_name: str = "LocalQuant"
    version: str = "0.1.0"
    debug: bool = True

    # 服务
    backend_port: int = _default("backend_port")
    frontend_port: int = _default("frontend_port")

    # 数据目录
    data_dir: Path = Path("./data")
    cache_dir: Path = Path("./data/cache")
    output_dir: Path = Path("./data/outputs")
    workflow_dir: Path = Path("./data/workflows")
    experiment_dir: Path = Path("./data/experiments")
    custom_nodes_dir: Path = Path("./data/custom_nodes")
    templates_dir: Path = Path("./templates")

    # QMT
    qmt_path: str = _default("qmt_path")
    qmt_data_dir: str = _default("qmt_data_dir")

    # QuantZone（宽舟科技）因子数据平台 — 对拍/因子值拉取，密钥存系统凭据库（回退 .env）
    qz_access_key: str = _default("qz_access_key")
    qz_sign_secret: str = _default("qz_sign_secret")
    qz_base_url: str = _default("qz_base_url")

    # PandaAI 公开数据 token（仅离线脚本 scrape_factors 使用）
    panda_token: str = _default("panda_token")

    # AI（设置页 → 各场景化 AI 接口）
    openai_api_key: str = _default("openai_api_key")
    openai_base_url: str = _default("openai_base_url")  # 仅 custom（BYOK）需要
    ai_provider: str = _default("ai_provider")  # 见 services/ai_providers.PROVIDER_PRESETS
    ai_model: str = _default("ai_model")
    ai_effort: str = _default("ai_effort")  # minimal/low/medium/high
    ai_engine: str = _default("ai_engine")  # api=供应商接口 / cli=本机 CLI 工具
    ai_cli: str = _default("ai_cli")  # 见 services/ai_providers.CLI_TOOLS
    ai_cli_model: str = _default("ai_cli_model")  # 空=用 CLI 自身默认
    ai_cli_effort: str = _default("ai_cli_effort")  # default/minimal/low/medium/high

    # QUBE AI Agent（与设置页 AI 配置完全独立）
    qube_provider: str = _default("qube_provider")
    qube_model: str = _default("qube_model")
    qube_effort: str = _default("qube_effort")
    qube_api_key: str = _default("qube_api_key")
    qube_base_url: str = _default("qube_base_url")  # 仅 custom（BYOK）需要
    qube_engine: str = _default("qube_engine")  # api / cli
    qube_cli: str = _default("qube_cli")
    qube_cli_model: str = _default("qube_cli_model")
    qube_cli_effort: str = _default("qube_cli_effort")

    # 股票池约束（非密钥；各入口默认继承，可在单次运行中覆盖）
    universe_exclude_st: bool = _default("universe_exclude_st")
    universe_exclude_new: bool = _default("universe_exclude_new")
    universe_min_list_days: int = _default("universe_min_list_days")
    universe_include_bj: bool = _default("universe_include_bj")
    universe_exclude_delisting: bool = _default("universe_exclude_delisting")

    # 代码执行沙箱（OpenSandbox 容器隔离；仅 QUBE/回测信号代码）
    # Docker/opensandbox-server 不可用时自动降级为进程内执行
    sandbox_enabled: bool = True
    sandbox_image: str = "opensandbox/code-interpreter:v1.1.0"
    sandbox_server_domain: str = "localhost:8080"

    # 数据库
    database_url: str = "sqlite+aiosqlite:///./data/localquant.db"

    # 每日批处理（自动更新）
    scheduler_enabled: bool = True
    scheduler_update_time: str = "15:45"  # 收盘后增量行情 + 快照
    scheduler_recalc_time: str = "18:30"  # 次日开盘前重算因子池（较晚确保公告数据回补）
    scheduler_recalc_periods: list[int] = [1, 5, 10, 20]
    scheduler_max_recalc: int = 500  # 单次批处理最多重算因子数（保护）

    # 跨机器访问时显式放行的来源（逗号分隔）；默认仅本机前端来源
    allowed_origins: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

# 密钥 overlay：.env / 环境变量之外，再从 OS 凭据库回填空缺的密钥字段。
# 启动迁移（main.py lifespan 中 migrate_env_secrets）完成后会再次调用 overlay。
from backend.secrets import overlay_settings as _overlay_secrets

_overlay_secrets(settings)

# 确保数据目录存在
for d in [
    settings.cache_dir,
    settings.output_dir,
    settings.workflow_dir,
    settings.experiment_dir,
    settings.custom_nodes_dir,
]:
    d.mkdir(parents=True, exist_ok=True)
