# LocalQuant — 本地投研工作站

基于 QMT 数据接口的本地量化投研平台，以 ComfyUI 风格的节点化工作流为核心，集成数据探索、因子研究、策略回测、QUBE 策略 Agent、策略库与实验管理等功能。

> **投资边界（系统级约束）**：本平台只做**普通股票多头投资**——正信号按日归一为满仓组合，总仓位始终 ≤ 100%（回测循环内逐日强制执行的硬约束，停牌/一字板冻结旧仓时买入按预算缩减，任何情况下不越界）；负信号视为「不买入」。系统**不提供、也不允许**融资、融券、做空、多空对冲或任何形式的杠杆交易。`dollar_neutral` / 原始权重（`none`）模式已在回测引擎与 QUBE 工具层移除；因子研究中的「多空组合」仅是 Top 组减 Bottom 组的统计诊断，不代表可交易的空头持仓。

## 功能总览

| 模块 | 简介 |
|------|------|
| **工作流编辑器** | iframe 内嵌官方 ComfyUI 前端搭建研究管线：节点代码编辑（Monaco + ruff）、因子分析链路、运行产物与缓存管理 |
| **数据探索** | 概览 / SQL（含 AI 生成与解读）/ 全市场扫描 / 横截面 / 异常检测 + 市场环境仪表盘 + 事件研究，基于本地 Parquet 缓存 |
| **因子研究** | 因子库、批量扫描、因子体检与拥挤度、样本外验证、因子池 → 组合回测闭环、AlphaLens、面板导出 |
| **分钟因子 · 日内高频** | 分钟缓存 → 清洗 → 分钟公式 → 折叠日频面板；时刻 IC 曲线；回测 `execute_at` 执行时点 |
| **策略回测** | 向量化回测：T 日信号 T+1 收盘成交、成本拆分、容量分析、参数敏感性、退市清算、风格/行业归因 |
| **QUBE 策略 Agent** | 多轮对话设计策略的 AI Agent（21 个平台工具的工具调用循环 + 策略/因子画板 + 内置技能库，技能原文本地缓存离线可用），AI 配置独立 |
| **策略库** | 工作中 / 已保存两态，策略代码版本历史可回滚 |
| **实验管理** | 实验记录、多实验对比、研究日志，回测/工作流完成后自动创建 |
| **风险与组合分析** | 风格暴露（Barra）、组合优化（SLSQP 纯多头）、压力测试（历史情景回放）、事前风险预测 |
| **数据管理** | QMT 下载与缓存、质量检查、除权/退市清单、财务快照、指数成分快照、历史参考快照导入 |
| **工作台** | 首页每日研究简报：市场状态、数据就绪度、体检摘要、除权事件、数据时效 |
| **AI 辅助** | 节点代码改写、自然语言生成工作流、SQL 生成与解读、因子分析建议；供应商预置 / BYOK / 本机 CLI |

> 各模块的完整功能清单见 **[docs/功能模块.md](docs/功能模块.md)**。

## 快速开始

### 环境要求

- Python >= 3.12
- Node.js >= 18
- uv (Python 包管理)
- QMT 客户端（Windows，用于数据获取）——xtquant 仅支持 Windows，macOS 开发时 QMT 数据功能不可用
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

QUBE/回测的信号代码优先在 OpenSandbox 容器中隔离执行，Docker/沙箱服务未就绪时自动降级为进程内执行并在结果中标注。机制与状态查询见 [docs/代码执行沙箱.md](docs/代码执行沙箱.md)。

```bash
make sandbox-server   # 先启动 Docker Desktop；实质执行 uvx opensandbox-server
```

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

## 技术栈

- **后端**: Python ≥ 3.12 / FastAPI / pandas / DuckDB / xtquant（QMT，仅 Windows）
- **前端**: Vue 3 / TypeScript / Vite / Tailwind CSS v4 / TanStack Vue Query / KaTeX（公式渲染）/ Monaco（代码编辑）/ ECharts（图表）；Monaco/ECharts/vendor 已手动分包，主入口不再承载全部第三方代码
- **工作流**: 官方 ComfyUI 前端（comfyui-frontend-package）iframe 内嵌 + 后端协议适配层
- **分析**: 自研 factor_research（IC/分层/衰减等，与工作流因子节点同源）+ alphalens-reloaded（行业分组/因子加权多空等标准口径）/ QuantStats（绩效）/ pandas-ta（技术指标）/ statsmodels·scipy
- **ML 节点**: scikit-learn / LightGBM / XGBoost / PyTorch
- **AI**: OpenAI 兼容接口（多供应商预置，对齐 models.dev）/ 本机 CLI 工具；QUBE Agent 为 pi-agent-core 的 Python 移植
- **沙箱**: OpenSandbox（回测信号代码容器隔离，Docker 不可用时降级进程内）
- **存储**: Parquet（数据缓存）/ SQLite（元数据、策略库、QUBE 会话）
- **CI**: GitHub Actions（后端 pytest + ruff，前端 build）

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
├── docs/             # 因子编写指南等功能文档（见下方「文档」）
├── data/             # 本地数据（gitignore；custom_nodes 为自定义节点，trash 为节点回收站）
├── templates/        # 工作流模板
└── Makefile
```

## 文档

- [功能模块](docs/功能模块.md) — 12 个功能模块的完整功能清单
- [严谨性与工程约定](docs/严谨性与工程约定.md) — 研究口径（可交易掩码/前向填充/无前视/IC 口径/point-in-time/复权等）与工程、安全约定
- [自定义节点](docs/自定义节点.md) — 编写自定义工作流节点
- [代码执行沙箱](docs/代码执行沙箱.md) — 信号代码容器隔离的机制、启用与状态查询
- [因子编写指南](docs/因子编写指南.md) — 因子公式/代码编写（因子库「变量参考」同源文档）
- [审查与修复流程](docs/审查与修复流程.md)
- 前端主题：[frontend/DESIGN-opencode.ai.md](frontend/DESIGN-opencode.ai.md)

## 致谢与来源

QUBE 策略 Agent 与因子研究在多处参考了 **PandaAI** 生态的公开成果：

- **PandaAI / panda_factor** — 因子公式算子库（`backend/services/factor_operators.py`）复刻 PandaAI 公式版口径；工作流节点契约（`BaseWorkNode`/`@work_node`）与因子算子库设计参考 [PandaAI-Tech/panda_factor](https://github.com/PandaAI-Tech/panda_factor)。
- **QuantSkills**（PandaAI 旗下开源量化能力平台）— QUBE 内置技能库的量化技能内容来自 [quantskills.ai](https://www.quantskills.ai)（GPL-3.0）：因子研究全流程技能（方向/风险形态因子库、挖掘工作流 SOP、生产工厂、体检评估、正交化、衰减、合并、诊断优化、回测过拟合检查）与分析师技能。技能手册为面向本平台的适配改写，各仓库 README/SKILL.md 原文缓存于本地库随项目分发。
- **LLMQuant** — 18 个金融大类 Agent Skills（MIT，[LLMQuant/skills](https://github.com/LLMQuant/skills)）。
- **pi（earendil-works）** — QUBE Agent 内核（Tool 声明、agent loop、事件流协议）为 pi-agent-core 架构的 Python 移植（MIT）。
- **ComfyUI / ComfyUI_frontend / OpenSandbox** — 工作流编辑器与代码执行沙箱（见上方技术栈）。

上述第三方组件的版权、许可证与分发形态的完整声明见 **[NOTICE](./NOTICE)**。

## License

本项目以 **GPL-3.0-or-later** 分发。

工作流编辑器基于 [ComfyUI](https://github.com/comfyanonymous/ComfyUI) 与
[ComfyUI_frontend](https://github.com/Comfy-Org/ComfyUI_frontend)（均为 GPL-3.0）构建：
后端实现其服务器协议（`backend/comfy/`），前端经 `comfyui-frontend-package==1.47.10`
托管于 `/comfy/` 并以 iframe 内嵌。QUBE 内置技能库含 QuantSkills 技能内容（GPL-3.0，
原文随本地库分发）。因合并 GPL-3.0 代码，整个作品转为 GPL-3.0。

上游版权、来源与所用版本见 [NOTICE](./NOTICE)，完整许可证见 [LICENSE](./LICENSE)。
对外分发（含二进制/SaaS）须一并提供完整对应源码。
