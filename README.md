# LocalQuant — 本地投研工作站

基于 QMT 数据接口的本地量化投研平台，以 ComfyUI 风格的节点化工作流为核心，集成数据探索、因子研究、策略回测、实验管理等功能。

## 功能模块

| 模块 | 说明 |
|------|------|
| **工作流编辑器** | ComfyUI 风格节点编辑器，搭建研究管线；节点端口按需生成（只有数据字段有连线口），支持画布锁定、连线加粗、节点右键「另存为新节点预设」、类目批量删除到回收站并还原 |
| **数据探索** | 数据概览、SQL 查询（含 AI 生成 SQL 与结果解读）、全市场扫描、横截面分析、异常检测，全部基于本地 Parquet 缓存 |
| **因子研究** | 因子库卡片/列表双视图、IC 排序与筛选、点击查看公式（LaTeX 数学渲染 + Python 代码）与全部指标、逐因子 AI 分析；AlphaLens 式 IC 汇总/分层平均收益/单调性输出；内置量化算子库（RANK/DELAY/CORR/TS_RANK/DECAYLINEAR 等），因子库 Alpha 公式可直接在公式节点运行 |
| **策略回测** | 向量化回测、绩效指标、净值/回撤曲线（由工作流回测节点提供） |
| **实验管理** | 实验记录、多实验对比、研究日志 |
| **数据管理** | QMT 数据下载、缓存管理、数据质量检查 |
| **AI 辅助** | 节点代码改写、自然语言生成工作流、因子分析建议、数据探索 SQL 生成与结果解读（OpenAI 兼容接口） |

### 工作流编辑器中的节点设计细节

- **节点端口**：仅数据型输入（DataFrame/dict 等，或标注「仅连线输入」的字段）生成连线端口；普通参数只在节点上渲染控件，不再为每个变量都开端口。
- **节点颜色**：画布节点、左侧节点面板、右侧配置面板三处统一取自 `frontend/src/lib/nodeColors.ts`，全局唯一。
- **节点说明**：左侧面板悬停节点弹出说明卡（描述/工作流示例/输入输出端口/注意事项）；拖入画布后点击节点，配置面板「节点说明」页展示同款文档。
- **代码编辑**：所有代码编辑界面（节点代码、SQL、因子代码、新建节点）统一使用带「网页全屏」按钮的编辑器（`components/ui/CodeEditor`，Esc 退出）。
- **因子重算**：预置因子重算 IC 采用**覆盖更新**语义（新指标写回原记录，不另存新因子），覆盖前旧值自动存入历史快照，可在因子详情「重算历史」中回溯。
- **因子编写**：公式/代码两种方式共用一套字段（open/high/low/close/volume/amount/vwap）与量化算子（RANK/DELAY/DELTA/CORR/STD/TS_RANK/DECAYLINEAR、以及 MACD/BOLL/KDJ/ATR/RSI/CCI/WR 等技术指标，大小写均可）；因子库区分**公式型/数据字段型/参数化指标**三类展示。因子库 Alpha 公式可直接粘到「因子构建（公式）」工作流节点运行（节点按股票池+区间自取 QMT 行情，并输出 return_data 供 IC/分组收益节点直连）。详见 [docs/因子编写指南.md](docs/因子编写指南.md)，因子库内可点「变量参考」查看。
- **工作流因子链路**：因子构建（公式/代码）→ 因子标准化/中性化 → 因子分析（一站式）/ IC 计算 / 分组收益 / 因子衰减 均基于 QMT 行情面板做**截面**计算，与因子研究页**同源**（同一套 factor_research 服务，full_factor_analysis 统一入口），结果一致。「因子分析」节点一个即输出 IC 统计/时序、IC 衰减、分层平均/累计收益、多空曲线、换手率与关键指标（对齐 AlphaLens）；因子研究页含 IC/分层/衰减/换手率/相关性页。
- **回测节点**：向量化回测，输出净值/回撤曲线与完整绩效（年化收益/波动/夏普/索提诺/卡玛/最大回撤/VaR/CVaR/胜率/盈亏比/月度收益），支持可选基准对比（跟踪误差/信息比率）。
- **工作流日志**：支持按级别、按节点 / 全局筛选与时间正序 / 倒序排序。

### 自定义节点

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

## 技术栈

- **后端**: Python / FastAPI / pandas / DuckDB / xtquant
- **前端**: React / TypeScript / React Flow / Tailwind CSS / KaTeX (公式渲染) / Monaco (代码编辑) / Recharts + ECharts (图表)
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
# 一键启动前后端（并行运行，Ctrl+C 同时退出）
make dev
# 前端页面 → http://localhost:5173
# 后端 API → http://localhost:8000（根路径自动跳转到 /docs 接口文档）

# 或分别启动
make dev-backend   # 后端 → http://localhost:8000
make dev-frontend  # 前端 → http://localhost:5173（需后端已启动，否则页面顶部会提示后端未连接）
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
│       ├── components/flow/    # 工作流编辑器（画布/面板/日志/节点说明/预设另存）
│       ├── components/explore/ # 数据探索（概览/SQL·AI/扫描/截面/异常）
│       ├── components/factor/  # 因子研究（因子库/详情弹窗/IC/分层）
│       ├── components/ui/      # 通用组件（含 CodeEditor 全屏编辑器）
│       ├── lib/nodeColors.ts   # 节点分类颜色全局唯一来源
│       └── pages/              # 页面
├── data/             # 本地数据（gitignore；custom_nodes/trash 为节点回收站）
├── templates/        # 工作流模板
└── Makefile
```



## 注意事项

- xtquant 仅支持 Windows，macOS 开发时 QMT 数据功能不可用
- 数据全部来自 QMT，不使用模拟数据
- 前端采用 OpenCode 浅色主题风格，frontend/DESIGN-opencode.ai.md
