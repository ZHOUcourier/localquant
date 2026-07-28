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

    # AI
    openai_api_key: str = ""
    openai_base_url: str = ""

    # 因子研究服务
    factor_service_url: str = "http://localhost:8001"

    # 数据库
    database_url: str = "sqlite+aiosqlite:///./data/localquant.db"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

# 确保数据目录存在
for d in [settings.cache_dir, settings.output_dir, settings.workflow_dir,
          settings.experiment_dir, settings.custom_nodes_dir]:
    d.mkdir(parents=True, exist_ok=True)
