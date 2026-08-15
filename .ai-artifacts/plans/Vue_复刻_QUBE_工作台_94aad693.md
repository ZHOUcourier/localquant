# QUBE 复刻方案（Vue 技术栈，基于参考站源码级分析修订）

参考：281=因子分析、272=股票（策略+回测）、1355=主页（新会话空态）。截图 `.qoder/ref_*.png`。
参考站技术事实（已从 DOM/bundle/网络请求确认）：React+Vite+Zustand+TanStack Query、Base UI、ECharts、Monaco 0.55、react-markdown、SSE 流式；**右侧画板为自定义拖拽分栏（非固定宽）**。我们用 Vue3 等价复刻，最左全局侧栏沿用现有 `Layout.vue`。

## 〇、视觉风格：opencode 风格（不采用参考站视觉）

**只复刻参考站的布局/交互/功能，视觉全部按 `frontend/DESIGN-opencode.ai.md` 执行**（与现有 `theme/opencode.ts` 一致）：
- 全站等宽字体（Berkeley Mono 回退栈：IBM Plex Mono → ui-monospace → Menlo…），无 sans-serif
- 配色：canvas `#fdfcfc`、ink `#201d1d`、surface-soft `#f8f7f7`、surface-card `#f1eeee`、hairline `rgba(15,0,0,0.12)`；语义色用 Apple ramp：accent `#007aff`、success `#30d158`、warning `#ff9f0a`、danger `#ff3b30`
- 形状：交互元素一律 4px 圆角（`rounded.sm`），容器 0px；**无阴影、无渐变、无毛玻璃**（参考站的 glass-blur/rounded-2xl 一概不用），卡片=1px hairline 描边块
- 按钮：primary 黑底 ink 白字 4px；secondary 白底 hairline-strong 描边；Tab 用透明底+下划线式（button-tab）
- 图标位可用 ASCII 括号记号（`[+]`/`[-]`/`▶`/`✓`）替代 SVG 装饰
- 语义映射：阶段 pill 完成=success、进行中=accent、错误=danger、未开始=mute；深度思考块用 accent 蓝（非参考站 rgb(57,100,254)）；空态分组色点用 accent/success/warning；交易方向买=danger 红、卖=success 绿

## 一、布局与分栏（重写 frontend/src/pages/Qube.vue）

结构：**QUBE 次级侧边栏（240px，可折叠）｜对话区（flex-1，最小 420px）｜右侧画板（可拖拽调宽）**

### 画板分栏机制（严格按参考站源码实现）
- 画板宽度由状态 `canvasWidthPx` 控制，内联 style width；**clamp 到 [360, min(1600, 容器宽-420)]**
- 拖拽手柄：画板左缘 `absolute -left-1 w-2 h-full cursor-ew-resize hover:bg-primary/25`，`mousedown` 自定义拖拽（拖动中 `body.cursor=ew-resize`、`userSelect=none`，公式 `newWidth = startWidth + (startX - clientX)`，实时 clamp）
- **双击手柄 = 展开到 900px**（受容器 clamp），非"复位默认"
- 折叠按钮：手柄上 `absolute -left-3.5 top-1/2` 的 size-7 圆形箭头；**折叠 = width:0 完全隐藏**；非拖拽时宽度变化带 `transition-[width] duration-300 ease-out`
- **工作区状态持久化**：新增 `composables/useQubeWorkspace.ts`（reactive + localStorage `lq-qube-workspace`，仿参考站 zustand persist），字段对齐参考站结构：`{ canvasWidthPx, canvasCollapsed, perSession: { [sessionId]: { active:{kind:'factor'|'strategy',id}, canvasTab, selectedBacktestRunId, selectedAnalysisId, backtestParams, analysisParams } } }`

### 1. 次级侧边栏（参考站顶栏功能移到这里，按用户要求）
- 「+ 新建对话」；会话列表（标题+时间，hover 重命名/删除）；底部「清空全部对话」（确认弹窗）
- 「系统提示词」入口：弹窗展示/编辑 AI 系统提示词（替代参考站"长期记忆"），可恢复默认
- 「技能库」入口：弹窗式技能面板，完整复刻参考站技能库结构——「我的技能 / 系统内置」两个过滤 Tab + 搜索框 + 分类胶囊（全部/记忆/策略/回测/调优/仿真交易/对话/因子，各带计数）+ 技能卡 2 列网格（display_name + description 全文 + params chip，内置卡带锁标只读）+ 提示条「系统内置技能由系统维护，不可修改」；「+ 新建技能」建自定义技能（名称/描述/分类/prompt 模板，点击插入输入框）
- 底部「引擎设置」：保留现有配置抽屉（api/cli、API Key、CLI 工具）

### 2. 对话区
- **空态起始页**（按 1355 源码复刻，删期货组）：
  - 标题"想从哪儿开始？"逐字动画：每字 `span.split-char` + `--i` 变量，CSS `@keyframes reveal-char`（opacity 0→1 + translateY(0.42em)→0，delay `calc(var(--i)*32ms)`）；副文案
  - 3 组模板：股票策略（accent 色点，茅台 5/20 双均线、海龟突破+ATR、多均线趋势过滤）、因子研究（warning 色点，20日动量、20日波动率、成交量变化、量价相关性、低PB+高ROE、看看我的因子库）、常用工具（danger 色点，看看我所有策略、在历史上跑一遍回测）
  - 分组头：色点 + 组名 + 灰描述 + 右侧计数徽标；卡片 `grid repeat(auto-fill,18rem)`，高 h-24，hairline 描边 4px 圆角，含标题+市场徽标、两行截断描述，入场动画 `.anim-reveal-up`（delay `--i*45ms+60ms`）；点卡片=发送对应 prompt
- **消息模型与渲染**（对齐参考站 `display_timeline` 结构）：
  - 一条 assistant 消息 = `thinking` + 交替的 text/tool 段落时间线，前端按段渲染（不再是整块文本）
  - 用户消息右对齐圆角描边气泡；AI 消息左侧 size-6 圆形 icon + 内容列（文本段宽度约 2/3 容器）
  - 文本段 markdown 渲染（`marked` + `dompurify`；等宽字体，h3 semibold、表格 overflow-x-auto、代码块 surface-card 底 hairline 描边、ul list-disc）
  - **深度思考块**：accent 蓝主题 hairline 描边卡，折叠条「深度思考过程 · N 字」，点开展开可滚动；流式时显示轮播等待文案
  - **工具卡片**（canvas 底 hairline 描边 4px 圆角 p-3 text-xs + ASCII 记号，按工具映射）：已创建因子（"打开画板"黑钮）、因子分析完成（"查看分析"白钮）、已写入策略代码（"代码/回测"双钮）、已更新回测参数（内嵌 surface-soft 底 key-value 表）、回测完成（副标"回测 #id · N 笔交易" + 指标 chip 总收益/最大回撤/夏普 + "查看/AI 优化"钮）
- **输入区**：textarea（Enter 发送/Shift+Enter 换行）+ 圆形发送钮（空禁用）；**输入框下方一排下拉**：供应商 → 模型 → 推理强度（models.dev 预置表，同设置页；改动写 `PUT /api/qube/config`）。策略转写按钮不放这里（移策略库）

### 3. 右侧画板（新组件 components/qube/CanvasPanel.vue 容器）
- 顶部 Artifact 条（h-11 浮动卡）：当前工件 chip（"因子 #N"/策略名）+「关闭临时项」；会话切换时从 `perSession` 恢复
- **因子画板 FactorBoard.vue**（复刻 281）：
  - 头部浮动卡：因子名（可编辑）+ Tab「代码｜分析结果」+ 黑底「▶ 跑分析」+「存入因子库」
  - 代码 Tab：「公式/Python」切换 + 现有 Monaco 封装
  - 分析参数条：起止日期、调仓周期(1/5/10/20)、分组数(5/10)、因子方向(1/-1)、股票池
  - 分析结果 Tab（ScrollArea + space-y-4）：
    - 进度卡：总进度条（h-1.5 圆角）+ **9 阶段 pill**（task_start 任务开始/factor_build 构建因子/market_data 加载并对齐行情/clean 清洗并标准化因子/returns 计算收益和滞后项/grouping 因子分组/analysis 计算分组收益和 IC/summary 汇总指标和完整图表/complete 分析完成），状态色按〇节语义映射：完成=success、进行中=accent、错误=danger、未开始=mute
    - 本次生效参数 dl 卡、关键指标网格（IC_mean/Rank_IC/IC_std/IC_IR/年化/夏普/最大回撤/t统计量等）、分组收益宽表（分组1..N + 多空组合 × 年化/超额/回撤/波动/夏普）
    - 图表网格 `grid lg:grid-cols-2`（ECharts/VChart，对齐参考站 ic_charts 八图 + 收益图）：IC 序列+累计、Rank_IC 序列、IC 分布、Rank_IC 分布、IC 衰减、Rank_IC 衰减、IC 自相关、分组累计收益/超额收益
    - 「历史分析」下拉切换往次结果
- **策略画板**（升级现有 StrategyWorkbench.vue，复刻 272）：
  - 头部：策略名（可编辑）+ 已保存徽章 + Tab「代码｜回测｜日志｜版本」+ 操作行「▶ 运行回测（黑）/ AI 优化（白）/ 保存到策略库」
  - 回测参数卡：起止日期、初始资金、手续费、滑点、股票池/基准
  - 回测 Tab：**8 阶段进度**（task_start/queued 等待计算资源/validation 校验策略与参数/engine_start 启动回测引擎/market_init 加载行情并初始化账户/simulation 按交易日执行回测/summary 汇总指标与交易记录/complete）→ 本次生效参数 → 指标卡（总收益/年化/最大回撤/夏普/交易笔数/最终权益）→ 净值曲线（ECharts 单线）→ 交易明细表（时间/标的/方向-买 danger 红 卖 success 绿/价格/数量/手续费/备注，min-w-[720px] 横向滚动）；「历史回测」下拉（选中项持久化到 perSession）
  - 日志 Tab：运行概要卡 + 等宽日志行（含条数统计）
  - 版本 Tab：v 徽章 + 最新/AI 改/回滚标签 + 备注 + 「载入编辑器/回滚到此版」（复用现有 /api/strategy 版本接口）

## 二、后端改动

### 消息与流式协议（routes/qube.py + services/qube_agent.py）
- `qube_messages` 加 `tool_calls_json` 列（存 `{calls:[{name,args,result,display_name,factor_id?,strategy_id?,backtest_run_id?}], display_timeline:[{type:'text'|'tool',content?,call_index?}], thinking}`），替代现在把 🔧 行拼进 content 的做法；`GET /sessions/{id}/messages` 返回结构化 tool_calls + `workspace_resume`（末次绑定的 factor_analysis/backtest 焦点）
- SSE 事件集对齐参考站：`delta` / `thinking`（捕获 delta.reasoning_content）/ `tool_start {name}` / `tool`（完整 call 结果，含结构化 id）/ `factor_analysis_started {factor_id, analysis_id}` / `backtest_started {strategy_id, backtest_run_id}` / `done` / `error`；前端沿用 ReadableStream 解析
- 新端点：`PATCH /sessions/{id}`（重命名）、`DELETE /sessions`（清空）、`GET/PUT /system-prompt`（存 `data/qube_system_prompt.md`，空回退内置 QUBE_SYSTEM）
- 会话表加 `bound_type/bound_id`（factor/strategy），供画板恢复

### Agent 工具扩充（build_qube_tools，复用现有服务）
- `create_factor(name, code_type: formula|python, code)`：登记因子（新表 qube_factors：id/session_id/name/code_type/code/created_at/updated_at），tool 事件带 factor_id
- `run_factor_analysis(factor_id, params)`：触发因子分析编排（下节），先发 `factor_analysis_started`，完成后把关键指标摘要回给模型
- `set_backtest_params(params)`：结构化参数推给画板（tool 卡内嵌 kv 表）
- `run_backtest` 改造：落库 backtest_runs（下节），带进度阶段回写，返回 backtest_id + 指标摘要
- `save_strategy` 保留（策略库 working 态）

### 因子分析编排（POST /api/qube/factor-analysis + GET 列表/详情）
- 流程按 9 阶段推进并回写 progress：公式→代码（`factor_research.formula_to_code`）→ 计算因子值（复用 /api/factor/compute 服务逻辑）→ 对齐行情（market_data）→ 标准化清洗 → IC/RankIC 序列/分布/衰减/自相关 + 分组收益（复用 factor_operators / factor_analysis 节点同款服务）
- 新表 `factor_analyses`：id/factor_id/session_id/status/progress_json/params_json（period_start/end、adjustment_cycle、group_number、factor_direction、stock_pool）/metrics_json/group_return_json/charts_json/created_at/finished_at —— 字段语义对齐参考站响应结构，画板「历史分析」下拉读列表
- 画板轮询 `GET /api/qube/factor-analysis/{id}`（含 progress）直至 done/error

### 回测记录持久化
- 新表 `backtest_runs`：id/strategy_id/session_id/status/progress_json/params_json/metrics_json/equity_json([{ts,equity}])/trades_json([{ts,symbol,side,price,qty,fee,reason}])/log_text/created_at/finished_at
- 策略画板回测与 Agent run_backtest 均落库并按 8 阶段回写 progress；`GET /api/backtest/runs?strategy_id=`、`GET /api/backtest/runs/{id}`
- **RunCenter.vue 加「策略回测记录」Tab**：时间/策略名/收益/回撤/夏普列表，点击看净值曲线+明细

### 技能库（数据一模一样复刻参考站，已扒全 30 个）
- 参考站技能本质 = **Agent 工具清单**（字段：name/display_name/description/category/category_id/params）。已抓到全部 30 个内置技能原文（记忆1/策略8/回测3/调优4/仿真交易6/对话2/因子6），seed 时**逐字保留** display_name/description/category/params
- 新表 `qube_skills`（id/name/display_name/description/category/category_id/params_json/prompt/builtin/enabled/created_at）；本地暂无对应后端能力的技能（期货/港美股策略与因子、仿真盘 6 个、调优 4 个）seed 时 `enabled=0`，UI 置灰标注「未接入」，其余（记忆、股票策略、版本、回测、行情查询、股票因子、因子分析、绑定目标等）与 Agent 工具一一对应
- 端点：`GET /api/qube/skills/builtin`、`GET /api/qube/skills/user`、`POST/PUT/DELETE /api/qube/skills`（builtin 403），响应字段对齐参考站
- 内置技能中与本地能力对应的部分，作为 Agent 工具命名/描述的蓝本（如 run_factor_analysis 的参数名 period_start/adjustment_cycle/group_number/factor_direction/stock_pool 直接沿用）

### QMT 转写（策略库，导出方向：本平台 → QMT）
- `POST /api/strategy/{id}/export-qmt`：专用系统提示词 + `qube_complete`，把 generate_signals 策略转写为迅投 QMT（xtquant，init/handlebar 结构）实盘代码，明确标注无法等价实现处及降级方案
- `StrategyLibrary.vue` 策略卡加「转写为 QMT」→ 弹窗（说明文案 + 开始转写 + Monaco 只读结果 + 复制/下载 .py）

## 三、对接与联调
- 前端沿用现有 fetch/vue-query 模式；新增依赖仅 `marked` + `dompurify`；图表用现有 ECharts6/VChart；编辑器用现有 Monaco 封装（本地，无需 CDN）
- 新表在 `backend/database.py` 建表 + 旧库 ALTER 兼容（qube_messages 加列、qube_sessions 加列）
- 不做参考站的消息虚拟列表（本地单机消息量小，直接渲染）

## 四、测试计划
- 后端：pytest 全量不回归；新增技能 CRUD、factor-analysis 编排（小样本数据）、backtest_runs 落库与进度回写的单测
- 前端：`npm run build` 通过；浏览器走查：空态动画/模板卡→发消息→timeline 工具卡→画板拖拽（360/1600 边界、双击 900、折叠 width 0、刷新后宽度恢复）→因子跑分析（9 阶段+图表）→策略回测（8 阶段+净值+明细）→历史下拉→版本/日志→技能插入→系统提示词编辑→QMT 转写→回测记录 Tab→会话切换画板状态恢复
- AI 链路验证：只用免费 opencode CLI 引擎最小化提示词跑通，不消耗付费额度；回测/因子分析不加激进超时

## 假设与范围
- 会话管理放次级侧边栏（用户要求），不复刻参考站顶部 Tab 栏与"长期记忆"（改为系统提示词编辑）
- 模型选择按用户要求放输入框下方（参考站在输入框内右侧）
- 参考站的算力/通知/仿真盘/调优任务/期货/港美股不在范围
- 内置技能=Agent 工具清单展示（与参考站语义一致）；自定义技能=prompt 模板插入输入框；深度思考开关不单独做（跟随推理强度配置）
- 30 个内置技能全部展示（含期货/港美股/仿真盘/调优），但本地无后端能力的置灰「未接入」不可被 AI 调用；如你希望干脆不显示这些，可在实现时改一行过滤条件
