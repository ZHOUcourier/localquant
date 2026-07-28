# LocalQuant — 本地投研工作站

基于 QMT 数据接口的本地量化投研平台，以 ComfyUI 风格的节点化工作流为核心，集成数据探索、因子研究、策略回测、实验管理等功能。

## 功能模块

| 模块 | 说明 |
|------|------|
| **工作流编辑器** | ComfyUI 风格节点编辑器，搭建研究管线 |
| **数据探索** | SQL 查询、全市场扫描、横截面分析、异常检测 |
| **因子研究** | IC 分析、分层收益、因子中性化、因子库管理 |
| **策略回测** | 向量化回测、绩效 Tear Sheet、蒙特卡洛模拟 |
| **实验管理** | 实验记录、多实验对比、研究日志 |
| **数据管理** | QMT 数据下载、缓存管理、数据质量检查 |

## 技术栈

- **后端**: Python / FastAPI / pandas / DuckDB / xtquant
- **前端**: React / TypeScript / React Flow / Tailwind CSS
- **分析**: Alphalens (因子分析) / QuantStats (绩效分析) / pandas-ta (技术指标)
- **存储**: Parquet (数据缓存) / SQLite (元数据)

## 快速开始

### 环境要求

- Python >= 3.12
- Node.js >= 18
- uv (Python 包管理)
- QMT 客户端（Windows，用于数据获取）

### 安装

```bash
# 克隆项目
cd localquant

# 安装所有依赖
make install
```

### 启动

```bash
# 一键启动前后端
make dev

# 或分别启动
make dev-backend   # 后端 → http://localhost:8000
make dev-frontend  # 前端 → http://localhost:5173
```

### 配置

复制 `.env.example` 为 `.env` 并配置：

```bash
cp .env.example .env
```

关键配置项：
- `QMT_PATH` — MiniQMT 客户端路径
- `QMT_DATA_DIR` — MiniQMT 数据目录
- `OPENAI_API_KEY` — AI 辅助功能（可选）

## 项目结构

```
localquant/
├── backend/          # Python 后端
│   ├── main.py       # FastAPI 入口
│   ├── config.py     # 配置
│   ├── plugins/      # 节点插件系统（@work_node）
│   ├── engine/       # 工作流执行引擎
│   ├── services/     # 业务逻辑（因子/回测/探索/实验）
│   ├── data/         # QMT 数据层
│   ├── models/       # Pydantic 数据模型
│   └── routes/       # API 路由
├── frontend/         # React 前端
│   └── src/
│       ├── components/flow/   # 工作流编辑器
│       ├── components/explore/ # 数据探索
│       ├── components/factor/  # 因子研究
│       ├── components/backtest/ # 回测
│       └── pages/              # 页面
├── data/             # 本地数据（gitignore）
├── templates/        # 工作流模板
└── Makefile
```

## 自定义节点

在 `data/custom_nodes/` 目录放置 Python 文件：

```python
from backend.plugins import BaseWorkNode, work_node, ui
from pydantic import BaseModel, Field

@ui(param={"input_type": "text_field"})
class MyInput(BaseModel):
    param: str = "default"

class MyOutput(BaseModel):
    result: str = ""

@work_node(name="我的节点", group="08-自定义", box_color="green")
class MyNode(BaseWorkNode):
    @classmethod
    def input_model(cls): return MyInput
    @classmethod
    def output_model(cls): return MyOutput
    def run(self, input):
        return MyOutput(result=f"Hello {input.param}")
```

## 注意事项

- xtquant 仅支持 Windows，macOS 开发时 QMT 数据功能不可用
- 数据全部来自 QMT，不使用模拟数据
- 前端采用 OpenCode 暗色主题风格
