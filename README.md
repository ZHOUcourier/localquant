# LocalQuant — 本地投研工作站

基于 QMT 数据接口的本地量化投研平台，以 ComfyUI 风格的节点化工作流为核心，集成数据探索、因子研究、策略回测、QUBE 策略 Agent、策略库与实验管理等功能。

## 功能模块

| 模块 | 说明 |
|------|------|
| **工作流编辑器** | iframe 内嵌官方 ComfyUI 前端，搭建研究管线；节点右键查看/编辑代码（Monaco + AI 改写 + ruff 诊断）、因子分析节点「显示分析结果」直接弹出综合报告、内置节点代码 fork 保护、底部本机性能监控 |
| **数据探索** | 数据概览、SQL 查询（含 AI 生成 SQL 与结果解读）、全市场扫描、横截面分析、异常检测，全部基于本地 Parquet 缓存 |
| **因子研究** | 因子库卡片/列表双视图、IC 排序与筛选、点击查看公式（LaTeX + Python 代码）与全部指标、逐因子 AI 分析；IC 汇总/分层平均收益/单调性输出；内置量化算子库，公式可直接在公式节点运行；另备 **AlphaLens 分析**（行业分组 IC/分层收益/因子加权多空/换手率）与自研综合报告互补 |
| **策略回测** | 向量化回测、绩效指标、净值/回撤曲线（工作流回测节点 + QUBE 策略工作台） |
| **QUBE 策略 Agent** | 多轮对话设计策略的 AI Agent（pi-agent-core 风格工具调用循环），能读文档/样本数据、写代码、跑回测、存策略；右侧策略工作台分屏（代码/回测/日志/版本 + AI 优化/自动优化）；配置与设置页 AI 完全独立 |
| **策略库** | 工作中 / 已保存两态；QUBE 对话与工作流产出默认「工作中」，仅用户可手动设为「已保存」；策略代码版本历史可回滚 |
| **实验管理** | 实验记录、多实验对比、研究日志 |
| **数据管理** | QMT 数据下载、缓存管理、数据质量检查 |
| **AI 辅助** | 节点代码改写、自然语言生成工作流、因子分析建议、数据探索 SQL 生成与结果解读；供应商预置（免填 URL，对齐 models.dev）/ 自定义 BYOK / 本机 CLI 工具三种接入，模型下拉选择与推理强度可调 |

### 工作流编辑器中的节点设计细节

- **节点端口**：仅数据型输入（DataFrame/dict 等，或标注「仅连线输入」的字段）生成连线端口；普通参数只在节点上渲染控件，不再为每个变量都开端口。
- **节点颜色**：画布节点、左侧节点面板、右侧配置面板三处统一取自 `frontend/src/lib/nodeColors.ts`，全局唯一。
- **节点说明**：左侧面板悬停节点弹出说明卡（描述/工作流示例/输入输出端口/注意事项）；拖入画布后点击节点，配置面板「节点说明」页展示同款文档。
- **代码编辑**：所有代码编辑界面（节点代码、SQL、因子代码、新建节点）统一使用带「网页全屏」按钮的编辑器（`components/ui/CodeEditor`，Esc 退出）。
- **因子重算**：预置因子重算 IC 采用**覆盖更新**语义（新指标写回原记录，不另存新因子），覆盖前旧值自动存入历史快照，可在因子详情「重算历史」中回溯。
- **因子编写**：公式/代码两种方式共用一套字段（open/high/low/close/volume/amount/vwap）与量化算子（RANK/DELAY/DELTA/CORR/STD/TS_RANK/DECAYLINEAR、以及 MACD/BOLL/KDJ/ATR/RSI/CCI/WR 等技术指标，大小写均可）；因子库区分**公式型/数据字段型/参数化指标**三类展示。因子库 Alpha 公式可直接粘到「因子构建（公式）」工作流节点运行（节点按股票池+区间自取 QMT 行情，并输出 return_data 供 IC/分组收益节点直连）。详见 [docs/因子编写指南.md](docs/因子编写指南.md)，因子库内可点「变量参考」查看。
- **工作流因子链路**：因子构建（公式/代码）→ 因子标准化/中性化 → 因子分析（一站式）/ 因子分析（AlphaLens）/ IC 计算 / 分组收益 / 因子衰减 均基于 QMT 行情面板做**截面**计算。自研「因子分析」与因子研究页**同源**（同一套 factor_research 服务）；「因子分析（AlphaLens）」调用 alphalens-reloaded 产出行业分组 IC/分层收益等。两个分析节点均可在节点上点「显示分析结果」直接弹出报告。
- **回测节点**：向量化回测，输出净值/回撤曲线与完整绩效（年化收益/波动/夏普/索提诺/卡玛/最大回撤/VaR/CVaR/胜率/盈亏比/月度收益），支持可选基准对比（跟踪误差/信息比率）。
- **工作流日志**：支持按级别、按节点 / 全局筛选与时间正序 / 倒序排序。

### QUBE 策略 Agent 与代码沙箱

- **QUBE Agent**：`backend/services/qube_agent.py` 是 [pi](https://github.com/earendil-works/pi) 的 pi-agent-core 架构的 Python 移植——工具调用循环 + 事件流（delta / tool_call / tool_result / done）。内置工具：`read_doc`（读《因子编写指南》）、`preview_data`（看真实行情样本）、`run_backtest`（真实回测）、`save_strategy`（存策略库）。对话产出的策略在右侧「策略工作台」分屏里回测、AI 优化、管理版本。
- **独立 AI 配置**：QUBE 的供应商/模型/推理强度/API Key/CLI 与「设置 → AI」完全分开，各存各的 `.env` 键。供应商预置对齐 [models.dev](https://models.dev)，含 OpenCode Zen/Go、DeepSeek、Zhipu/Z.AI（含 Coding Plan）、Kimi、Alibaba、Moonshot、MiniMax 等，预置免填 Base URL，仅自定义 BYOK 需自填；也可切换本机 CLI 工具（Claude Code/Codex/OpenCode/Pi 等）作为引擎。
- **代码沙箱**：回测/QUBE 的信号代码经 `backend/services/sandbox.py` 执行——优先用 OpenSandbox 容器隔离（数据经文件 API 以 CSV 传入，不挂载卷，兼容 Windows），Docker/服务未就绪时降级为进程内执行并标注。仅覆盖 `/api/backtest/run-strategy` 与 QUBE `run_backtest`；因子研究页与工作流因子节点保持原生执行。

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

- **后端**: Python ≥ 3.12 / FastAPI / pandas / DuckDB / xtquant（QMT，仅 Windows）
- **前端**: Vue 3 / TypeScript / Vite / Tailwind CSS v4 / TanStack Vue Query / KaTeX（公式渲染）/ Monaco（代码编辑）/ ECharts（图表）
- **工作流**: 官方 ComfyUI 前端（comfyui-frontend-package）iframe 内嵌 + 后端协议适配层
- **分析**: 自研 factor_research（IC/分层/衰减等，与工作流因子节点同源）+ alphalens-reloaded（行业分组/因子加权多空等标准口径）/ QuantStats（绩效）/ pandas-ta（技术指标）/ statsmodels·scipy
- **ML 节点**: scikit-learn / LightGBM / XGBoost / PyTorch
- **AI**: OpenAI 兼容接口（多供应商预置，对齐 models.dev）/ 本机 CLI 工具；QUBE Agent 为 pi-agent-core 的 Python 移植
- **沙箱**: OpenSandbox（回测信号代码容器隔离，Docker 不可用时降级进程内）
- **存储**: Parquet（数据缓存）/ SQLite（元数据、策略库、QUBE 会话）

## 快速开始

### 环境要求

- Python >= 3.12
- Node.js >= 18
- uv (Python 包管理)
- QMT 客户端（Windows，用于数据获取）
- Docker Desktop（可选；Windows 用 WSL2 后端）——开启回测信号代码的容器隔离（OpenSandbox）；不装则自动降级为进程内执行

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

### 代码执行沙箱（可选，推荐）

QUBE/回测的信号代码默认尝试在 OpenSandbox 容器中隔离执行（客户端已随 `make install` 安装）。
要真正启用隔离，先启动 Docker Desktop，再单开一个终端跑沙箱服务：

```bash
make sandbox-server   # 实质执行 uvx opensandbox-server
```

未启 Docker/沙箱服务时，回测会自动降级为进程内执行（无容器隔离，日志/回测结果会标注）；
状态可查 `GET /api/system/sandbox`。

### 配置

复制 `.env.example` 为 `.env` 并配置：

```bash
cp .env.example .env
```

关键配置项（完整清单见 `.env.example`，大部分可在设置页 / QUBE 配置里改）：
- `QMT_PATH` / `QMT_DATA_DIR` — MiniQMT 客户端路径与数据目录
- `AI_PROVIDER` / `AI_MODEL` / `AI_EFFORT` / `AI_ENGINE` / `AI_CLI` — AI 辅助（供应商预置免填 URL；engine=cli 时用本机 CLI）
- `OPENAI_API_KEY` / `OPENAI_BASE_URL` — API Key；URL 仅自定义 BYOK 供应商需填
- `QUBE_*` — QUBE Agent 专属 AI 配置（与上面完全独立）
- `SANDBOX_ENABLED` / `SANDBOX_IMAGE` / `SANDBOX_SERVER_DOMAIN` — 代码执行沙箱

## 项目结构

```
localquant/
├── backend/          # Python 后端
│   ├── main.py       # FastAPI 入口
│   ├── config.py     # 配置（.env 持久化）
│   ├── plugins/      # 节点插件系统（@work_node）
│   ├── engine/       # 工作流执行引擎
│   ├── comfy/        # ComfyUI 协议适配层 + 官方前端托管（/comfy/）+ 节点工具扩展
│   ├── services/     # 业务逻辑（factor_research/回测/探索/实验/
│   │                #   ai_providers 供应商注册表 / qube_agent 策略Agent / sandbox 沙箱）
│   ├── data/         # QMT 数据层
│   ├── models/       # Pydantic 数据模型
│   └── routes/       # API 路由（workflow/factor/backtest/ai/qube/strategy/system 等）
├── frontend/         # Vue 3 前端外壳（opencode 浅色主题）
│   └── src/
│       ├── components/explore/  # 数据探索（概览/SQL·AI/扫描/截面/异常）
│       ├── components/factor/   # 因子研究（因子库/详情弹窗/综合报告）
│       ├── components/qube/     # QUBE 策略工作台（StrategyWorkbench）
│       ├── components/workflow/ # 节点代码 Monaco 弹窗等
│       ├── components/ui/       # 通用组件（CodeEditor 全屏编辑器·ruff、VChart、Select）
│       ├── lib/monaco.ts        # Monaco 接线（Python 补全 + ruff 内联诊断）
│       ├── composables/         # useWorkflow/usePlugins/usePresetFactors 等
│       └── pages/               # 页面（工作流/因子/QUBE/策略库/设置 等）
├── docs/             # 因子编写指南等（QUBE read_doc 工具可读）
├── data/             # 本地数据（gitignore；custom_nodes/trash 为节点回收站）
├── templates/        # 工作流模板
└── Makefile
```



## 注意事项

- xtquant 仅支持 Windows，macOS 开发时 QMT 数据功能不可用
- 数据全部来自 QMT，不使用模拟数据
- 前端采用 OpenCode 浅色主题风格，frontend/DESIGN-opencode.ai.md

## License

本项目以 **GPL-3.0-or-later** 分发。

工作流编辑器基于 [ComfyUI](https://github.com/comfyanonymous/ComfyUI) 与
[ComfyUI_frontend](https://github.com/Comfy-Org/ComfyUI_frontend)（均为 GPL-3.0）构建：
后端实现其服务器协议（`backend/comfy/`），前端经 `comfyui-frontend-package==1.47.10`
托管于 `/comfy/` 并以 iframe 内嵌。因合并 GPL-3.0 代码，整个作品转为 GPL-3.0。

上游版权、来源与所用版本见 [NOTICE](./NOTICE)，完整许可证见 [LICENSE](./LICENSE)。
对外分发（含二进制/SaaS）须一并提供完整对应源码。
