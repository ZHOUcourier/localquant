from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 项目基础
    project_name: str = "LocalQuant"
    version: str = "0.1.0"
    debug: bool = True

    # 服务
    backend_port: int = 8000
    frontend_port: int = 5173

    # 数据目录
    data_dir: Path = Path("./data")
    cache_dir: Path = Path("./data/cache")
    output_dir: Path = Path("./data/outputs")
    workflow_dir: Path = Path("./data/workflows")
    experiment_dir: Path = Path("./data/experiments")
    custom_nodes_dir: Path = Path("./data/custom_nodes")
    templates_dir: Path = Path("./templates")

    # QMT
    qmt_path: str = ""
    qmt_data_dir: str = ""

    # AI（设置页 → 各场景化 AI 接口）
    openai_api_key: str = ""
    openai_base_url: str = ""  # 仅 custom（BYOK）需要；预置供应商自带 Base URL
    ai_provider: str = "opencode-zen"  # 见 services/ai_providers.PROVIDER_PRESETS
    ai_model: str = ""
    ai_effort: str = "medium"  # 推理强度 minimal/low/medium/high（支持的模型生效）
    ai_engine: str = "api"  # api=供应商接口 / cli=本机 CLI 工具
    ai_cli: str = "claude"  # 见 services/ai_providers.CLI_TOOLS

    # QUBE AI Agent（与设置页 AI 配置完全独立）
    qube_provider: str = "opencode-zen"
    qube_model: str = ""
    qube_effort: str = "medium"  # 推理强度 minimal/low/medium/high
    qube_api_key: str = ""
    qube_base_url: str = ""  # 仅 custom（BYOK）需要
    qube_engine: str = "api"  # api / cli
    qube_cli: str = "claude"

    # 代码执行沙箱（OpenSandbox 容器隔离；仅 QUBE/回测信号代码）
    # Docker/opensandbox-server 不可用时自动降级为进程内执行
    sandbox_enabled: bool = True
    sandbox_image: str = "opensandbox/code-interpreter:v1.1.0"
    sandbox_server_domain: str = "localhost:8080"

    # 因子研究服务
    factor_service_url: str = "http://localhost:8001"

    # 数据库
    database_url: str = "sqlite+aiosqlite:///./data/localquant.db"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

# 确保数据目录存在
for d in [
    settings.cache_dir,
    settings.output_dir,
    settings.workflow_dir,
    settings.experiment_dir,
    settings.custom_nodes_dir,
]:
    d.mkdir(parents=True, exist_ok=True)
