# 方案：全量采用 ComfyUI 前端 + 前端 Vue 化 + 许可证变更

| 项 | 内容 |
| --- | --- |
| 文档状态 | 已实施（P0–P5 已落地并验证；前端 build+typecheck 通过，后端协议闭环与 iframe 内嵌已验证） |
| 决策日期 | 2026-07-30 |
| 决策方案 | 方案 A：全量采用 ComfyUI，后端实现其协议 |
| 前端策略 | 整体 React → Vue 重写（保留 opencode 浅色外壳外观），工作流页 iframe 内嵌 ComfyUI 前端 |
| 前端锁定 | comfyui-frontend-package==1.47.10（最新稳定核心版 requirements 所 pin，已启用 Nodes 2.0） |
| 许可证 | MIT → GPL-3.0-or-later（已完成：LICENSE/pyproject/README/NOTICE/SPDX） |
| 约束 | 零模拟数据原则不变；system_stats 等用真实 psutil 数据 |

---

## 1. 背景与目标

现工作流编辑器为自研 React + `@xyflow/react`，与 ComfyUI 在节点交互深度上有差距（子图/群组、撤销重做、成熟队列与节点系统等）。经评估，决定**不再自研编辑器内核**，直接采用官方 `Comfy-Org/ComfyUI_frontend`（Vue SPA），并让 localquant 的 Python 后端实现 ComfyUI 服务器协议。

同时，为统一前端技术栈、消除「React 外壳 + Vue 编辑器」的割裂，决定**把 localquant 现有 React 前端整体重写为 Vue 3**，外观维持现有 opencode 浅色风格基本不变；工作流页面以 **iframe** 方式内嵌独立构建的 ComfyUI 前端。

### 目标形态

- 工作流编辑器 = 官方 ComfyUI 前端（原样使用，独立 bundle）。
- localquant 后端 = 保留 Python/FastAPI 与现有节点计算逻辑，**新增 ComfyUI 协议适配层**。
- localquant 外壳（侧边栏 / 顶栏 / 底部状态栏 / 因子研究 / 数据探索 / Dashboard / 设置等）= **Vue 3 重写**，保持现有浅色外观。
- 许可证转为 GPL-3.0。

### ComfyUI 仓库结构（背景事实，来自官方核实）

- `Comfy-Org/ComfyUI`（原 `comfyanonymous/ComfyUI`）：**纯后端引擎**（Python 执行引擎 + API 服务器），前端已移出。
- `Comfy-Org/ComfyUI_frontend`：**纯前端**（Vue 3 + TS + PrimeVue SPA），2025-08 起并入 litegraph.js 画布库；需连一个 ComfyUI 后端，走 HTTP + WebSocket。
- `comfyui-frontend-package`（PyPI）：把编译后的前端静态资源打成 pip 包供后端托管。
- 现状注意：ComfyUI 正推进 **Nodes 2.0**（渲染从 LiteGraph Canvas 迁往 Vue），前端内部处于变动期。

---

## 2. 目标架构

```
┌─────────────────────────────────────────────────────────┐
│  localquant 前端外壳（Vue 3，opencode 浅色主题）            │
│  ┌───────────┐  ┌──────────────────────────────────────┐ │
│  │ Sidebar   │  │ TopBar                                │ │
│  │ (Vue)     │  ├──────────────────────────────────────┤ │
│  │           │  │ 路由内容区：                            │ │
│  │           │  │  /            Dashboard (Vue)          │ │
│  │           │  │  /factor      因子研究   (Vue)          │ │
│  │           │  │  /data        数据探索   (Vue)          │ │
│  │           │  │  /settings    设置       (Vue)          │ │
│  │           │  │  /workflow/:id ┌────────────────────┐  │ │
│  │           │  │               │ <iframe src="/comfy">│  │ │
│  │           │  │               │  ComfyUI 前端(深色)  │  │ │
│  │           │  │               └────────────────────┘  │ │
│  │           │  ├──────────────────────────────────────┤ │
│  │           │  │ StatusBar (Vue) 资讯 + 行情            │ │
│  └───────────┘  └──────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
                         │ HTTP + WebSocket
                         ▼
┌─────────────────────────────────────────────────────────┐
│  localquant 后端（FastAPI）                                │
│  ┌─────────────────────────────────────────────────────┐ │
│  │ ComfyUI 协议适配层（新增）                             │ │
│  │  /object_info /prompt /ws /history /queue /interrupt  │ │
│  │  /view /system_stats /features ...                    │ │
│  └───────────────┬─────────────────────────────────────┘ │
│                  ▼                                         │
│  现有引擎：ALL_WORK_NODES 注册表 / runner / workflow_runs   │
│  现有业务：因子计算 / 回测 / 数据探索 / market_data / QMT    │
└─────────────────────────────────────────────────────────┘
```

关键点：**ComfyUI 前端是独立 bundle，由后端托管在 `/comfy/` 路径**；Vue 外壳通过 iframe 引用它。二者共用同一个 localquant 后端。

---

## Part A — 许可证变更（MIT → GPL-3.0）

因合并 GPL-3.0 的 ComfyUI 代码，整个 localquant 必须转为 GPL-3.0（copyleft 传染至整个可分发作品）。改动清单：

1. 根 `LICENSE`：MIT 全文 → GPL-3.0 全文。
2. `pyproject.toml`：`license = "GPL-3.0-or-later"`；补 OSI 分类器。
3. `frontend/package.json`：`"license": "GPL-3.0-or-later"`。
4. `README.md`：新增 License 段，声明基于 ComfyUI（GPL-3.0）构建，附上游版权与链接。
5. 新增 `THIRD_PARTY_NOTICES` / `NOTICE`：列出 ComfyUI、ComfyUI_frontend、litegraph.js 的版权、来源与所用 commit/tag。
6. 从 ComfyUI 改写的源文件：保留原版权头 + `SPDX-License-Identifier: GPL-3.0-or-later`。
7. 贡献指南写明分发义务：对外分发（含 SaaS/二进制）须提供完整对应源码。
8. 用单独 commit `chore: relicense MIT → GPL-3.0` 作为许可证分界点（不重写 git 历史）。

> 影响提醒：转 GPL-3.0 后，后续闭源商用受限。此为已确认的取舍。

---

## Part B — 后端 ComfyUI 协议适配层（核心工作量①）

让官方前端以为自己连的是标准 ComfyUI 后端。

### B.1 路由清单（按优先级）

**必须（前端加载 + 跑图最小闭环）**

| 接口 | 作用 | 复用现有 | 工作量 |
| --- | --- | --- | --- |
| `GET /object_info` | 返回所有节点定义，前端据此画节点 | 反射 `ALL_WORK_NODES`（见 B.4） | 大 |
| `GET /object_info/{class}` | 单节点定义 | 同上 | 小 |
| `POST /prompt` | 提交图入队，返回 `prompt_id`+`number` | API 图 → runner nodes/links，复用 `run_stream` | 大 |
| `GET /prompt` | 当前队列状态 | workflow_runs | 小 |
| `WS /ws` | 推执行进度 | runner 事件 → WS 消息（见 B.3） | 大 |
| `POST /interrupt` | 停止执行 | 已有 `request_cancel()` | 小 |
| `GET /history` `/history/{id}` | 运行历史 | 已有 workflow_runs 表 | 中 |
| `GET/POST /queue` | 队列查看/清空 | 需补真队列（见风险 F.4） | 中 |
| `GET /system_stats` `/features` | 前端启动握手 | 真实/占位响应 | 小 |

**次要（结果查看/上传/杂项，多为占位或按需）**

`GET /view`（B.5 重点摩擦）、`POST /upload/image`、`/upload/mask`、`/embeddings`、`/extensions`、`/models` `/models/{folder}`、`/workflow_templates`、`/userdata*`、`/users`、`/view_metadata`、`/free`。

### B.2 图格式转换（易踩坑）

- ComfyUI **API(prompt) 格式**：`{ "<node_id>": { "class_type": "...", "inputs": {字段: 值 或 [上游node_id, 输出索引]} } }`。
- 连线用**输出索引**（不是名字）→ 需把 localquant `output_field_name` 映射为该节点 `RETURN_TYPES` 中的**位置索引**。这是最易错点。
- 另有 **workflow(UI) 格式**（litegraph 序列化画布），由前端自行维护、提交时降解为 API 格式，**后端只需处理 API 格式**。
- `POST /prompt` 请求体：`{prompt, client_id, extra_data}`；响应：`{prompt_id, number, node_errors}`。

### B.3 WebSocket 消息映射

| ComfyUI WS 消息 | 载荷 | runner 对应事件 |
| --- | --- | --- |
| `status` | `{status:{exec_info:{queue_remaining}}, sid}` | 连接/队列变化 |
| `execution_start` | `{prompt_id}` | 工作流开始 |
| `executing` | `{node, prompt_id}`（`node=null`=整体结束） | node_start / 结束 |
| `progress` | `{value, max, node, prompt_id}` | 节点进度（无节点内进度则用 i/n 近似） |
| `executed` | `{node, output, prompt_id}` | node_complete + 输出预览 |
| `execution_error` | `{node_id, exception_message, ...}` | node_failed |
| `execution_success` | `{prompt_id}` | workflow_complete |

### B.4 节点反射适配器（核心工作量②，推荐"自动适配"而非重写）

不改现有 `work_node` 本体，写一个反射器把 pydantic 字段 + `@ui` 转成 `object_info`，`run()` 包一层适配。

`@ui` 控件 → ComfyUI `INPUT_TYPES` 映射：

| localquant `@ui` | ComfyUI 定义 |
| --- | --- |
| `date_picker` | `("STRING", {})` + 自定义日期 widget 扩展 |
| `text_field` | `("STRING", {"multiline": false})` |
| `code_editor` | `("STRING", {"multiline": true})` + 代码高亮扩展 |
| `combobox(options)` | `(["选项1","选项2"], {})`（下拉=选项列表当类型） |
| `number_field` | `("INT"/"FLOAT", {"default":_, "min":_, "max":_})` |
| `input_type: None`（仅连线） | 自定义类型输入槽，无 widget |
| DataFrame 端口 | 自定义类型串如 `"DATAFRAME"` / `"PANEL"`，仅用于连线 |

ComfyUI 节点契约映射目标：`INPUT_TYPES`(required/optional/hidden)、`RETURN_TYPES`、`RETURN_NAMES`、`FUNCTION`、`CATEGORY`、`OUTPUT_NODE`。自定义类型（DATAFRAME 等）ComfyUI 原生支持——类型即字符串，同名可连。

---

## Part C — 前端 React → Vue 全量重写 + 内嵌 ComfyUI（核心工作量③）

### C.1 决策

- localquant 自有前端**整体重写为 Vue 3**，统一技术栈，**外观维持 opencode 浅色风格基本不变**。
- 工作流页面以 **iframe 内嵌**独立构建的 ComfyUI 前端。
- 「统一技术栈」= 框架层面都是 Vue；ComfyUI 前端仍是上游独立应用（隔离在 iframe），便于独立升级与跟上游同步。

### C.2 技术栈映射

| React 现状 | Vue 目标 |
| --- | --- |
| React 19 | Vue 3.5（`<script setup>` + Composition API） |
| Vite | Vite（保留） |
| react-router-dom | vue-router |
| zustand | Pinia |
| @tanstack/react-query | @tanstack/vue-query |
| echarts-for-react | vue-echarts（echarts 保留） |
| ag-grid-react | ag-grid-vue3 |
| @monaco-editor/react | monaco-editor 直接封装 / vue-monaco 封装 |
| lucide-react | lucide-vue-next |
| recharts | 统一改用 vue-echarts（recharts 无 Vue 版） |
| tailwindcss / katex / clsx | 保留（框架无关） |
| index.css opencode 主题 token | 保留（框架无关，直接复用） |

### C.3 页面 / 组件去留清单

**外壳（保留外观，重写为 Vue）**
- `layout/`：Layout、Sidebar、TopBar、StatusBar → Vue 组件，浅色外观不变。
- `ui/`：Button、Input、Card、Table、Tabs、Badge、Select、Dialog、CodeEditor、ScrollArea 等 → Vue 版组件库。

**业务页（重写为 Vue，逻辑不变）**
- `pages/`：Dashboard、DataCenter、DataExplore、FactorResearch、RunCenter、Experiments、Settings、WorkflowList。
- `components/explore/`：DataOverview、SQLPanel、MarketScanner、CrossSection、AnomalyDetector、RegressionAnalysis、Seasonality、VolatilityAnalysis、CorrelationMatrix、RiskProfile、PairSpread、RollingCorrelation。
- `components/factor/`：FactorBuilder、FactorLibrary、ICAnalysis、QuantileChart、ComprehensiveReport、FactorReferenceDialog 等。
- hooks → composables：useBackendHealth、usePlugins、usePresetFactors、useWorkflow（改 vue-query）。

**工作流编辑相关（废弃，由 ComfyUI 取代）**
- `pages/WorkflowEditor.tsx` → 改为「iframe 容器页」。
- `components/flow/*`（FlowEditor、FlowToolbar、WorkNode、NodeConfig、NodePalette、NodeWidget、BottomPanel、ExecutionLog、ResultViewer、RunHistoryDialog、SaveAsPresetDialog）→ **不迁移，废弃**。
- `store/flowStore`、`hooks/useExecution`、`lib/nodeSchema`、`lib/nodeColors` → 废弃。
- ⚠️ 例外：`FactorReportDialog` 的因子报告可视化不能丢，见 Part D。

### C.4 内嵌方式（iframe，非同 bundle 挂载）

- ComfyUI 前端独立 build，由 FastAPI 托管于 `/comfy/`；Vue 工作流页用 `<iframe src="/comfy/">` 全屏嵌入。
- **为何 iframe 而非同页挂载**：ComfyUI 前端是完整 Vue 应用（自带 Vue 运行时、Pinia、PrimeVue、vue-router、litegraph）。与外壳 Vue 应用同 bundle 挂载会产生单例/版本冲突（两个 Vue 实例、两套 PrimeVue）。iframe 保证隔离、可独立升级、跟上游同步简单。
- **通信**：父子必要时用 `postMessage`（如外壳向编辑器传股票池/触发运行）；多数场景无需跨 iframe——工作流状态都在后端。
- **外观接缝**：外壳浅色、iframe 内 ComfyUI 深色，存在视觉分界，已接受。

### C.5 前端交付与版本锁定（含 Nodes 2.0 版本决策）

**决策：锚定 `Comfy-Org/ComfyUI_frontend@v1.48.5`（2026-07-23，1.48 线最终补丁），并启用 Nodes 2.0。**

背景数据（2026-07-30 核实）：
- Nodes 2.0（Vue 渲染，即 V3 schema 体系）在 ComfyUI 核心 **v0.3.76（2025-12-02）** 以 public beta 进入，至今约 8 个月，现已是稳定版**默认**渲染方式。
- 前端最新：v1.49.1（07-29）/ v1.49.0（07-27）/ v1.48.5（07-23）。v1.47–1.49 大量提交在打磨 `vue-nodes`（即 Nodes 2.0），说明它是当前主线并在持续稳定化。

为何选 v1.48.5 而非最新 v1.49.x：
- v1.49.x 仅发布 1–3 天，太新，回归风险高；nightly 更不可取。
- v1.48.5 是 1.48 线的第 6 个补丁（.0→.5），经过多轮修复，Nodes 2.0 成熟度足够，是「稳定但不过时」的甜点位。

**更稳的替代（优先核实）**：锚定「**最新稳定核心版本所 pin 的 `comfyui-frontend-package` 版本**」——即最新 stable `Comfy-Org/ComfyUI` 的依赖里写死的前端版本。这是 ComfyUI 团队自己一起 QA 过的前后端组合，能最大程度保证协议兼容。立项前先查该版本号，若与 v1.48.5 接近则直接采用它。

对协议适配层的关键影响：
- Nodes 2.0 是**渲染层**变更，它能渲染 V1（legacy）与 V3 两种 schema 的节点。因此我们的 `/object_info` 适配器**可先输出 V1 兼容 schema 即可获得 Nodes 2.0 渲染**，无需一上来就实现 V3 schema——先降风险，后续再按需升级到 V3 以支持更丰富的动态 widget（MatchType/DynamicCombo/Autogrow 等）。
- 部分特性（如动态增长节点）需 V3 才完整，列为 P2 之后的增强项。

交付与维护：
- 经 `--front-end-version Comfy-Org/ComfyUI_frontend@v1.48.5` 或直接 vendored build 固定，绝不跟 nightly。
- 重新锚定节奏：每约 2 个 minor 版本、且新线稳定后再升，不逐版跟。
- 保留 ComfyUI 内的 LiteGraph 回退开关作为逃生舱。

---

## Part D — 结果展示摩擦

ComfyUI 前端为图像/latent/文本生成设计（节点预览、Gallery、`/view` 皆图片语义）；localquant 产物是 DataFrame / IC 曲线 / 分层绩效 / 因子综合报告 / ECharts 图。**官方前端不会原生渲染这些**。

方案（择一或组合）：
1. 用 ComfyUI **扩展 API**（`registerExtension`：自定义 widget / 底部面板 tab / 自定义 DOM）在节点里渲染 ECharts 报告——保交互，工作量大。
2. 后端把结果渲染成图片走 `/view`——省事但丢交互。
3. 「HTML/Any 预览节点」输出富内容。
4. **保留在 Vue 外壳侧**：因子分析报告仍走独立的 Vue 因子研究页展示（工作流只负责算，报告在因子页看）——最省力，推荐作为初期方案。

> 结论：因子可视化是产品核心价值，此块是方案 A 里最费工的部分，须计入排期。初期建议走方案 4（报告留在 Vue 因子页），后续再评估是否做 ComfyUI 扩展。

---

## Part E — 分阶段计划与 Go/No-Go

| 阶段 | 目标 | 交付物 | 卡点 |
| --- | --- | --- | --- |
| **P0 PoC** | 官方前端连上你后端**把画布画出来** | `/object_info`+`/system_stats`+`/features` 最小实现；iframe 加载官方前端 | ✅ 画布出现你的节点 = 继续；❌ = 重评 |
| **P1 执行闭环** | 跑通一个真实工作流并看状态 | `POST /prompt` + `/ws` + `/interrupt` + `/history` | ✅ 端到端跑通 |
| **P2 节点适配器** | 全部 builtin 节点自动暴露 | B.4 反射适配器 + 类型映射 | 参数/连线正确 |
| **P3 前端 Vue 外壳** | 外壳与业务页 Vue 化 | layout/ui/业务页重写，opencode 外观保持；工作流页 iframe 容器 | 外观一致、页面功能对齐 |
| **P4 结果展示** | 因子报告/曲线可见 | Part D 方案（初期方案 4） | 核心可视化不丢 |
| **P5 License + 收尾** | 合规 + 打磨 | Part A 全部；真队列、IS_CHANGED、回退开关 | 合规审查通过 |

先做 **P0 + P1 PoC**（独立 spike 分支，不碰 License、不重写前端），验证「官方前端 ↔ 你后端」能否跑通最小工作流，通过后再做 P2–P5。

---

## Part F — 风险


1. **队列语义**：现为"即时跑"，ComfyUI 为"入队列"，须补真队列，否则 `/queue` 行为对不上。
2. **前端重写工作量**：React→Vue 全量重写是独立大工程

---

## Part G — 相关开源项目对比结论（panda_quantflow / litegraph / panda_factor）

> 背景：本项目后端节点契约（`BaseWorkNode`/`@work_node`）复刻自 panda_quantflow，因子算子库复刻自 panda_factor 官网手册。2026-07-30 对两仓库做了实证核查（含反编译其前端产物），结论存档如下，作为方案 A 的补充依据。


我们的项目已否决 litegraph。

### G.1 panda_factor 的取舍：抄正确性，不抄基础设施

- **不整体替换**本项目因子模块：其数据工程层（`panda_data`/自动更新/因子持久化）焊死在 MongoDB + 网盘分发的私有库表上，因子格式为 `['symbol','date']` 长表；整体引入将推翻 QMT + DuckDB/parquet 本地栈与面板 DataFrame 体系，适配成本≈重写其数据访问层。
- 算子层（136 函数）与分析层（IC/分层/换手/中性化等）本项目已与其官网手册全集对齐，覆盖面打平，无替换必要。
- **应做的两件事**（转 GPL-3.0 后与其许可证兼容）参考或者直接应用其合理的代码https://github.com/PandaAI-Tech/panda_factor：
  1. 逐个核对算子边界处理（停牌、涨跌停、排名并列、中性化行业处理等），发现差距单点移植其实现；
  2. 参考其「因子持久化 + 每日自动增量更新」思路，在本项目 DuckDB 层实现等价能力（列入 P5 之后的增强项）。
