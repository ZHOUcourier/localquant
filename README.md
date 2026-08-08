# LocalQuant — 本地投研工作站

基于 QMT 数据接口的本地量化投研平台，以 ComfyUI 风格的节点化工作流为核心，集成数据探索、因子研究、策略回测、QUBE 策略 Agent、策略库与实验管理等功能。

## 功能模块

| 模块 | 说明 |
|------|------|
| **工作流编辑器** | iframe 内嵌官方 ComfyUI 前端，搭建研究管线；节点右键查看/编辑代码（Monaco + AI 改写 + ruff 诊断）、因子分析节点「显示分析结果」直接弹出综合报告、内置节点代码 fork 保护、底部本机性能监控 |
| **数据探索** | 数据概览、SQL 查询（含 AI 生成 SQL 与结果解读）、全市场扫描、横截面分析、异常检测，全部基于本地 Parquet 缓存；**市场环境仪表盘**（宽基牛/震荡/熊判定 + 小盘/成长/中盘 vs 大盘风格轮动，数据中心顶部）；**事件研究**（一字涨/跌停、放量、除权除息、手工事件 → 窗口 CAR/BHAR + t 值 + 正值占比，近邻事件自动合并防重复计数） |
| **因子研究** | 因子库卡片/列表双视图、IC 排序与筛选、点击查看公式（LaTeX + Python 代码）与全部指标、逐因子 AI 分析；IC 汇总/分层平均收益/单调性输出；内置量化算子库，公式可直接在公式节点运行；**因子批量扫描**（勾选类别/因子 → 全市场一次算完 → 按 IC/RankIC/ICIR 排序 → 入池，SSE 逐因子进度，结果覆盖更新+历史快照）；**因子体检**（基于 IC 历史快照的生命周期阶段：萌芽/稳定/观察/衰减/失效 + IC 趋势徽标）；**因子池拥挤度**（池内因子两两截面相关）；**样本外验证**（walk-forward 滚动锚定分割，每折 in-sample/OOS IC + 分层多空，防过拟合）；**因子池→组合回测闭环**（选因子 → 等权/滚动 IC 加权合成[样本外权重，无前视] → 每日 Top-N 做多 → 回测 → 绩效 → 风格+行业归因一键打通）；**组合 walk-forward 回测**（训练窗口定权重 → 测试窗口出信号 → 滚动拼接样本外净值，附全样本参考对比过拟合差距）；另备 **AlphaLens 分析**（行业分组 IC/分层收益/因子加权多空/换手率）与自研综合报告互补；**因子面板导出 CSV**（`/api/factor/export-panel`，研究交付与离线复核） |
| **分钟因子 · 日内高频** | 分钟缓存（1m/5m/15m/30m/60m）→ 自动清洗（竞价 bar 剔除、半日市/一字板标记）→ 分钟公式求值（`m_*` 字段 + `ID_*` 聚合 / `M_*` 序列算子 + 现成高频因子 TAIL_RET/OPEN_RET/RV/JUMP_DAY/AMIHUD5/VWAP_DEV/VOLUME_CLOCK/AUC_VOL_RATIO/LIMIT_UP_TIME/OVERNIGHT_RET/INTRADAY_RET）→ 自动折叠日频面板，下游全链路复用；**时刻 IC 曲线**（09:45~14:55 各时点采截面算 RankIC，回答「因子信息何时最强」）；回测 **execute_at 执行时点**（收盘/尾盘/次日开盘，开盘执行按开→收计收益）；因子库「日内高频」类别预置 14 个因子，批量扫描自动分流；工作流「因子构建（分钟）」节点 |
| **策略回测** | 向量化回测、绩效指标、净值/回撤曲线（工作流回测节点 + QUBE 策略工作台）；**交易成本拆分**（佣金/滑点/印花税分列金额、占比与 bps/换手）；**容量分析**（信号在参与率约束下可容纳的资金规模，逐档资金规模给出受限天数比例与理论容量上限）；**回测风格归因**（回测记录页一键运行：组合收益 ~ Σ β×风格因子收益 + alpha，回答「策略赚的钱来自哪种风格、剩的是不是纯 alpha」）；**参数敏感性**（网格扫描：佣金/滑点/印花税/止盈止损逐组合回测对比，验证策略稳健性）；**退市强制清算**（数据提前截止的持仓按末日价 ×(1-`delisting_loss`) 变现，`delisting_events` 明细 + assumptions 明示，杜绝「死股冻结不实现损失」）；**复牌跳空收益**（收益率前向填充口径，停牌损失如实入账） |
| **QUBE 策略 Agent** | 多轮对话设计策略的 AI Agent（pi-agent-core 风格工具调用循环），能读文档/样本数据、写代码、跑回测、存策略；右侧策略工作台分屏（代码/回测/日志/版本 + AI 优化/自动优化）；配置与设置页 AI 完全独立 |
| **策略库** | 工作中 / 已保存两态；QUBE 对话与工作流产出默认「工作中」，仅用户可手动设为「已保存」；策略代码版本历史可回滚 |
| **实验管理** | 实验记录、多实验对比、研究日志 |
| **风险与组合分析** | 风格暴露（Barra 精简）/ 组合优化（SLSQP 带约束）/ 绩效补充指标（alpha·beta/上下行捕获/Active Share）/ 压力测试（含**历史情景回放**：2015 股灾/2018 熊市/2024 小微盘危机等真实窗口 × 当前权重）/ **组合事前风险预测**（风格+行业因子协方差 → 预测波动 + 因子风险贡献分解）；**回测归因含行业因子**（均值偏离编码，回答「超额来自行业还是选股」）；**空头可融券过滤**（QMT 两融标的池快照，dollar_neutral 只允许池内做空）；**块自助蒙特卡洛**（保留自相关与波动聚集）；支持**从本地行情缓存加载面板**（股票池+区间，前复权）与**回测记录风格归因**（回归法，`/api/risk/attribution-run`） |
| **数据管理** | QMT 数据下载、缓存管理、数据质量检查（含价格跳变/量能尖峰/疑似停牌退市披露）、**最近除权事件清单**（adjust_factor 跳变检测：股票/日期/比例）、财务快照拉取（含 **Cashflow 现金流表**，供现金流/质量因子；字段按别名表归一）、标的池快照（**两融/沪深股通**，供空头过滤与北向池研究）、数据时效检查（**交易日历口径**：QMT 日历优先、工作日近似兜底，长假不误报）；**退市/历史代码清单**（维护退市代码，全市场批量下载自动并入，消除幸存者偏差）；**历史参考快照导入**（指数成分/行业/合约名称/两融池 as-of 导入，覆盖历史区间的 ST/成分/两融状态） |
| **工作台** | 首页 **每日研究简报**：市场状态 + 因子池体检摘要 + 近 7 日除权事件 + 数据时效 + 最近批处理（/api/ops/briefing 实时聚合，15 分钟自动刷新） |
| **AI 辅助** | 节点代码改写、自然语言生成工作流、因子分析建议、数据探索 SQL 生成与结果解读；供应商预置（免填 URL，对齐 models.dev）/ 自定义 BYOK / 本机 CLI 工具三种接入，模型下拉选择与推理强度可调 |

### 工作流编辑器中的节点设计细节

- **节点端口**：仅数据型输入（DataFrame/dict 等，或标注「仅连线输入」的字段）生成连线端口；普通参数只在节点上渲染控件，不再为每个变量都开端口。
- **节点颜色**：画布节点、左侧节点面板、右侧配置面板三处统一取自 `frontend/src/lib/nodeColors.ts`，全局唯一。
- **节点说明**：左侧面板悬停节点弹出说明卡（描述/工作流示例/输入输出端口/注意事项）；拖入画布后点击节点，配置面板「节点说明」页展示同款文档。
- **代码编辑**：所有代码编辑界面（节点代码、SQL、因子代码、新建节点）统一使用带「网页全屏」按钮的编辑器（`components/ui/CodeEditor`，Esc 退出）。
- **因子重算**：预置因子重算 IC 采用**覆盖更新**语义（新指标写回原记录，不另存新因子），覆盖前旧值自动存入历史快照，可在因子详情「重算历史」中回溯。
- **因子编写**：公式/代码两种方式共用一套字段与量化算子；除量价外，研究/公式路径还注入 **基本面 fund_*（按公告日点位）、market_cap / turnover（需股本快照）、行业映射（供 INDUSTRY_NEUTRALIZE）**，并据快照现状动态标注可用性（无数据可取时求值会明确报错而非静默给错值）。因子库 Alpha 公式可直接粘到「因子构建（公式）」工作流节点运行（节点按股票池+区间自取 QMT 行情，并输出 return_data 供 IC/分组收益节点直连）。详见 [docs/因子编写指南.md](docs/因子编写指南.md)，因子库内可点「变量参考」查看。
- **工作流因子链路**：因子构建（公式/代码）→ 因子标准化/中性化 → 因子分析（一站式）/ 因子分析（AlphaLens）/ IC 计算 / 分组收益 / 因子衰减 均基于 QMT 行情面板做**截面**计算。自研「因子分析」与因子研究页**同源**（同一套 factor_research 服务）；「因子分析（AlphaLens）」调用 alphalens-reloaded 产出行业分组 IC/分层收益等。两个分析节点均可在节点上点「显示分析结果」直接弹出报告。
- **回测节点**：向量化回测，默认成本佣金率 0.001 / 滑点 0.001 / 卖出印花税 0.0005（与回测接口、QUBE 一致），T 日信号 T+1 执行，输出净值/回撤曲线与完整绩效（年化收益/波动/夏普/索提诺/卡玛/最大回撤/VaR/CVaR/胜率/盈亏比/月度收益），支持可选基准对比（跟踪误差/信息比率）。逐仓风控（止盈/止损/移动止损）对**多头与空头**同时生效；一字板导致调仓无法成交时不推演挂单（持仓保持，次数在 assumptions 明示）。成本明细拆分输出（佣金/滑点/印花税分列）。
- **因子样本外验证节点**：walk-forward 滚动锚定分割（训练 [0,t) → 测试 [t, t+test) 逐折后移），输出每折 in-sample IC 与 OOS IC/分层多空、聚合 OOS IC 均值/t 值/同向一致性/衰减，防过拟合。
- **市场环境节点能力**：`/api/regime/overview` 基于本地指数日线缓存输出宽基趋势状态（MA20/MA60/动量/HV20 联合判定牛/震荡/熊）、风格轮动（小盘/成长/中盘 vs 大盘 20 日相对强弱），数据中心顶部仪表盘展示。
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
- 数据全部来自 QMT，不使用模拟数据（行情来源唯一；历史成分/名称/两融池等**参考元数据**可通过「历史快照导入」补充，见下）
- **严谨性约定**（自研研究/回测路径默认启用）：
  - 因子 IC/分层的「可交易掩码」（停牌/ST/次新股过滤）在能取到量价面板的研究路径默认**开启**，避免无法成交的票污染截面；ST 状态与次新过滤均按**逐日 as-of** 判定（ST 从 instrument 快照日起生效，不把「现在的 ST」倒灌历史截面；次新股按「T 距上市日 < 20 天」逐日排除，而非按面板末日一刀切）；
  - **收益率面板统一为前向填充口径**（`close.ffill().pct_change()`）：停牌/数据缺口期间收益为 0，**复牌日的跳空涨跌如实入账**——原始 `pct_change().fillna(0)` 会把停牌期间积累的跳空整段丢失，系统性低估波动与损失；
  - **滚动 IC 加权无前视**：IC 合成权重用 IC 序列 **shift(1) 后**的滚动均值——`IC[T]` 需要 T+1 日收益才能算出，T 日不可得，直接滚动会把「即将赚到的收益」算进当日权重（1 日前视，组合虚高）；
  - **事件研究窗口语义**：`window_before/window_after` 为事件前/后天数（正数），相对日 = [-before, +after]（事件日=0）；事件在面板边界导致窗口截断时按实际存在的相对日对齐累计（不做越界/错位拼接），收益面板同样为前向填充口径；
  - **数据提前截止（退市/缓存截断）强制清算**：回测引擎对末日早于面板末日的持仓，在截止后首日按「末日价 ×(1-`delisting_loss`)」强制变现并释放权重（默认 0=全额变现的保守上界），不计交易费用，事件明细入 `delisting_events`、assumptions 明示；请用「退市/历史代码清单」（数据管理页 / `GET·POST /api/data/delisted`）维护退市代码并在批量下载时自动并入，使退市整理期价格如实入账；
  - 所有回测/因子研究的**参数、样本与指标均写溯源记录**（`provenance` 表，/api/data 下可查），保证任意结果可复现；回测的口径（成本/风险字段/归一方式）也一并记录；
  - IC 标准差统一为**样本标准差（ddof=1）**；单调性只奖励单调递增方向；多因子合成先横截面去均值再 z-score；IC 衰减与 IC 汇总表**同口径**（T→T+p 复利收益）；
  - 基本面/股本/行业等参考数据均按**公告日(point-in-time)**生效；`as_of` 早于任何行业快照时返回空而非未来行业，杜绝前视；市值/换手率按公告日口径；
  - **历史参考快照导入**（`POST /api/data/import-reference`）：QMT 只能提供当前成分/名称/行业/两融池，2015 年沪深300 成分、历史上曾 ST 的名称等无法回溯。研究员可从已核验来源整理历史快照（constituents/industry/instrument/margin，as-of 日期标注）导入，使指数成分重建、ST 逐日过滤、两融池逐日掩码覆盖历史区间——这是**参考元数据**，不改变「行情唯一来自 QMT」的约束；
  - **研究交付导出**：因子面板与前瞻收益可导出 CSV（`POST /api/factor/export-panel` → `GET /api/factor/export-file/{token}`），回测记录可导出净值/日收益/交易明细/日志（`GET /api/backtest/runs/{id}/export?part=equity|returns|trades|log`）；
  - **工作流节点缓存随数据失效**：节点级输出缓存键包含本地数据缓存版本（行情/参考数据最新 mtime + 文件数），重新下载/更新数据后自动失效，不会把旧数据的结果当成新结果；
  - 数据时效可在 `GET /api/data/freshness` 查看（最新交易日 + 显著滞后标的清单）。
- **访问安全**：默认仅绑定 `127.0.0.1` 并只放行本机前端来源（CORS 不含通配符）。如需跨机器访问，请自行在 `.env` 设 `ALLOWED_ORIGINS` 并**自行承担无鉴权**的执行类接口（因子/回测/策略）与 `config` 接口的可达风险。
- **执行加固**：工作流节点计算运行在线程池，慢节点不会阻塞服务器（含取消响应）；「数据下载」节点仅允许 http(s) 且保存路径收敛到 `output/downloads`；「公式计算/代码执行」节点内置函数为受限白名单（无 `import/open/os`）；本地 SQL 接口拒绝写关键字并限制单次最多返回 2000 行；自定义节点为**用户自编 Python 的完整执行环境**（可运行任意代码），仅限本机可信使用；AI/QUBE 的 Base URL 仅接受 http(s)，配置写入会剥离换行控制字符；**因子求值命名空间线程隔离**（`INDUSTRY_NEUTRALIZE` 捕获各自命名空间的行业映射，并发批量扫描/工作流互不污染，不依赖模块级全局）。
- **复权存储**：缓存为**不复权价 + `adjust_factor` 列**（由后复权价反推，锚定上市日——新增除权事件不改变历史因子值，增量缓存自洽）；因子/回测/研究读取默认按**前复权**换算（`raw × factor / 最新 factor`），跨除权追更后历史价格全局一致，不再需要重下历史区间。旧版前复权缓存（无 `adjust_factor` 列）qfq 读取透明兼容，下载时自动重建；SQL 探索看到的为原始价 + adjust_factor 列（前复权 = close × adjust_factor / 最新 adjust_factor）。
- **空数据错误统一**：缓存为空/未连接时，数据类接口统一返回结构化错误（`code: no_cached_data` / `qmt_not_connected` + message + hint），不再静默返回空列表，研究员可区分「没数据」与「出 bug」。
- 前端采用 OpenCode 浅色主题风格，frontend/DESIGN-opencode.ai.md

## License

本项目以 **GPL-3.0-or-later** 分发。

工作流编辑器基于 [ComfyUI](https://github.com/comfyanonymous/ComfyUI) 与
[ComfyUI_frontend](https://github.com/Comfy-Org/ComfyUI_frontend)（均为 GPL-3.0）构建：
后端实现其服务器协议（`backend/comfy/`），前端经 `comfyui-frontend-package==1.47.10`
托管于 `/comfy/` 并以 iframe 内嵌。因合并 GPL-3.0 代码，整个作品转为 GPL-3.0。

上游版权、来源与所用版本见 [NOTICE](./NOTICE)，完整许可证见 [LICENSE](./LICENSE)。
对外分发（含二进制/SaaS）须一并提供完整对应源码。
