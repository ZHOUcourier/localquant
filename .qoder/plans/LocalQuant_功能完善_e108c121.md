# LocalQuant 功能完善计划

## 背景

基于对参考网站 (pandaaiquant.com) 工作流和因子库页面的详细分析，以及本地代码库的全面审查，识别出以下核心差距并制定实施方案。所有前端实现必须严格遵循 `/frontend/DESIGN-opencode.ai.md` 设计规范。

---

## Phase 1: 工作流系统完善（最高优先级）

### 1.1 工作流列表页重构
**目标文件**: `frontend/src/pages/WorkflowList.tsx`, `backend/routes/workflow.py`, `backend/services/workflow_service.py`

**当前状态**: 简单卡片网格，仅支持新建/删除/从模板创建，无分类、无搜索。

**改动**:
- **左侧分类导航栏**: 增加 Tab 切换 — "预置模板" | "我创建的" | "收藏"
- **表格视图替代卡片**: 参考网站的表格布局，列包含：名称、分类、标签、更新时间、操作（查看/收藏/删除/复制）
- **搜索和筛选**: 顶部搜索框 + 分类筛选下拉
- **创建工作流模态框**: 点击"创建工作流"弹出模态框，展示模板卡片列表（含名称、描述、节点数、类型标签），支持选择模板创建或创建空白工作流
- **收藏功能**: 后端 workflow 模型增加 `is_favorite` 字段

**后端改动**:
- `models/workflow.py`: WorkflowResponse 增加 `is_favorite` 字段
- `routes/workflow.py`: 增加 `PUT /{id}/favorite` 接口、列表接口增加 `tab` 和 `search` 查询参数
- `services/workflow_service.py`: 实现收藏逻辑和筛选逻辑

### 1.2 工作流编辑器导航改进
**目标文件**: `frontend/src/pages/WorkflowEditor.tsx`, `frontend/src/components/flow/FlowToolbar.tsx`

**当前问题**: 进入编辑器后无法返回，无取消按钮，无离开确认。

**改动**:
- **顶部工具栏左侧**: 增加返回按钮（`← 返回`），点击跳转 `/workflow`
- **离开确认**: 使用 `useBlocker`（react-router）拦截导航，当有未保存更改时弹出确认对话框（"工作流有未保存的更改，确定要离开吗？"）
- **取消按钮**: 工具栏增加"取消"按钮，等同于返回（带确认）
- **脏状态追踪**: flowStore 增加 `isDirty` 标志，任何节点/边/配置变更时设为 true，保存后重置

### 1.3 节点面板树形层级展示
**目标文件**: `frontend/src/components/flow/NodePalette.tsx`

**当前状态**: 扁平分组列表，节点堆在一起不易区分。

**改动**:
- **树形折叠结构**: 每个分组可折叠，默认收起，显示节点计数（如 `01-数据获取 (5)`）
- **搜索**: 保留现有搜索，搜索时自动展开匹配的分组
- **视觉层级**: 分组标题使用 OpenCode 规范的 ASCII 括号标记 `[+]`/`[-]` 表示展开/收起状态
- **节点项**: 显示节点名称 + 简短描述，hover 显示 tooltip

### 1.4 节点代码编辑增强
**目标文件**: `frontend/src/components/flow/NodeConfig.tsx`, `frontend/src/components/flow/WorkNode.tsx`, `frontend/src/components/flow/NodeWidget.tsx`

**当前状态**: 部分节点支持代码编辑（Monaco Editor），但节点整体代码不可查看编辑。

**改动**:
- **节点级代码查看**: 在 NodeConfig 面板增加"节点代码"Tab，展示该节点后端的完整 Python 源代码（只读或可编辑）
- **后端接口**: `routes/plugins.py` 增加 `GET /{name}/source` 返回节点源文件内容
- **代码编辑语法检测**: Monaco Editor 配置 Python 语言支持，启用基本语法错误提示（利用 Monaco 内置的 Python tokenizer 进行实时语法检查，红色波浪线标记错误）
- **行内错误显示**: 利用 Monaco 的 `markers` API，在代码行左侧显示错误图标和错误信息

### 1.5 工作流导入/导出
**目标文件**: `frontend/src/components/flow/FlowToolbar.tsx`, `backend/routes/workflow.py`

**改动**:
- **导出**: 工具栏增加"导出"按钮，将当前工作流序列化为 JSON 并下载
- **导入**: 工具栏增加"导入"按钮，上传 JSON 文件创建新工作流
- **后端**: 增加 `POST /workflow/import` 接口

### 1.6 完整搬运参考网站 48 个节点
**目标**: 将参考网站的全部 48 个节点完整迁移到本地，不删减任何节点。

**完整节点清单（6 大类）**:

**01-基础工具（7个）**: Python代码输入、自定义股票池、公式输入、模型上传、循环控制、模型下载、数据下载

**02-特征工程（1个）**: 特征工程构建

**03-机器学习（11个）**: MLP模型、随机森林模型、LightGBM模型、XGBoost模型、GRU模型、SVM模型、LSTM模型、CNN模型、Transformer模型、GNN模型、超参数搜索(Optuna)

**04-因子相关（12个）**: 因子大赛参赛节点、因子分析(期货)、线性因子构建、因子构建(机器学习)、自定义因子构建、因子权重调整（归一化）、多因子合并、多因子组合、因子相关性分析、因子相关性分析结果、因子分析、因子分析结果

**05-回测相关（3个）**: 股票回测、期货回测、策略回测结果

**07-智能体（14个）**: 研报 RAG、RAG、技能集合、智能体、极速智能体、MCP、提示词输入、技能、钉钉助手、极速智能体应用、智能体聚合、智能体集合、智能体消息、智能体交易

**实现方式**:
- 每个节点创建对应的 `BaseWorkNode` 子类，注册到插件系统
- 节点需要定义 input_model、output_model、run() 方法
- 对于需要外部依赖的节点（如 ML 框架），先实现骨架 + 明确依赖声明，后续按需安装
- 同时修复现有 6 个数据处理节点的 TODO（连通上游数据）

### 1.7 输出节点实现
**目标文件**: `backend/plugins/builtin/output.py`

**当前问题**: 文件几乎为空，但模板 `stock_selection.json` 引用了 `OutputNode`。

**改动**: 实现基本的输出节点（数据表格展示、CSV 导出），修复模板引用问题。

---

## Phase 2: 因子库预置集成

### 2.1 从参考网站完整抓取 608 个因子数据
**目标**: 将参考网站 (pandaaiquant.com) 上已有的全部 608 个因子数据完整抓取下来，存入本地数据库。

**数据来源**: 参考网站的 API 接口（已由 Browser 研究阶段记录了完整的数据结构）

**抓取内容（每个因子）**: factorCode, factorName, categoryName, categoryCode, categoryColorHex, description(含公式), icMean, rankIc, icIr, icStd, annualizedReturn, maximumDrawdown, sharpeRatio, turnoverRate, startDate, dataDate, stockPool

**9 大分类（原样搬运）**:
- 技术类因子 (79个, #5FA5FA)
- 估值因子 (10个, #2E8E6C)
- 量能指标因子 (36个, #DFAA20)
- 超买超卖因子 (42个, #F87171)
- 均线类因子 (81个, #23C8E2)
- 基础因子 (8个, #94A3B8)
- 财务指标衍生因子 (90个, #F472B6)
- Alpha101 (87个, #3D66E0)
- Alpha191 (175个, #86DDD3)

**实现**:
- 创建抓取脚本 `backend/scripts/scrape_factors.py`，调用参考网站的 API 分页获取全部 608 个因子
- 因子存储到 SQLite 数据库（复用现有 `database.py`），新建 `preset_factors` 表
- IC 指标等绩效数据直接使用网站已计算好的值，不做本地重新计算
- 因子记录标记为 `is_preset=True`，与用户自建因子区分
- 用户如需重新计算某个因子的 IC，手动点进去触发计算

### 2.2 因子库前端重构
**目标文件**: `frontend/src/pages/FactorResearch.tsx`, `frontend/src/components/factor/FactorLibrary.tsx`

**改动**:
- **视图切换**: 增加卡片视图/列表视图切换按钮
- **卡片设计**: 遵循 OpenCode 规范（`#f1eeee` 表面色、`4px` 圆角、hairline 边框），展示因子名称、分类标签（带颜色圆点）、描述摘要、IC 指标（IC_MEAN/RANK_IC/IC_IR/IC_STD）+ 绩效指标（年化收益、最大回撤、夏普比率、换手率）
- **分类标签栏**: 横向可滚动标签，显示各分类及计数（如"技术类因子·79"），点击筛选
- **排序功能**: 支持按 RANK_IC、IC_MEAN、IC_IR 等指标升降序排列
- **分页**: 每页 30 条，底部分页控件
- **搜索**: 保留现有搜索，增强为支持因子名/描述/公式模糊搜索
- **操作按钮**: 每个因子卡片增加"查看工作流"、"加入因子池"按钮

### 2.3 因子后端 API 适配
**目标文件**: `backend/routes/factor.py`, `backend/services/factor_research.py`

**改动**:
- **预置因子列表接口**: `GET /factor/preset` 支持分页、分类筛选、排序、搜索
- **因子详情接口**: `GET /factor/preset/{id}` 返回因子完整信息（含网站预计算的 IC 和绩效指标）
- **手动重算接口**: `POST /factor/preset/{id}/recalculate` 用户手动触发重新计算某个因子的 IC
- 所有预计算数据直接存储和返回，不做实时计算

### 2.4 因子池功能
**目标文件**: 新建 `frontend/src/components/factor/FactorPool.tsx`

**改动**:
- 支持将因子加入"因子池"进行管理和对比
- 因子池页面展示已收藏的因子，支持批量 IC 分析对比
- 后端增加因子池 CRUD API

---

## Phase 3: Dashboard 重构

### 3.1 主界面改造
**目标文件**: `frontend/src/pages/Dashboard.tsx`

**当前问题**: 有 4 个快捷操作卡片（新建工作流/数据探索/因子研究/运行回测），用户不需要这些。

**改动**:
- **移除快捷操作卡片**: 删除"创建策略"、"因子"、"回测"等 4 个快捷入口
- **系统状态概览**: 展示系统整体状况 — 后端连接状态、数据缓存状态、磁盘使用量
- **各模块内容统计**: 以简洁列表展示每个栏目的内容数量：
  - 工作流: X 个（预置 Y 个，我创建的 Z 个）
  - 因子库: X 个（预置 Y 个，自建 Z 个）
  - 回测记录: X 条
  - 实验: X 个
- **最近活动**: 保留最近工作流和实验列表，但精简展示
- **设计风格**: 严格遵循 OpenCode 规范 — 奶油色背景 `#fdfcfc`、卡片表面 `#f1eeee`、hairline 边框、无阴影无渐变、ASCII 标记

---

## Phase 4: UI/UX 细节改进

### 4.1 全局导航改进
**目标文件**: `frontend/src/components/layout/Sidebar.tsx`, `frontend/src/components/layout/TopBar.tsx`

**改动**:
- 面包屑导航增强：显示完整路径（如 "工作流 / 编辑器"）
- 确保所有页面都有一致的返回机制

### 4.2 二次确认对话框
**目标文件**: 新建 `frontend/src/components/ui/ConfirmDialog.tsx`（或复用现有 Dialog）

**改动**:
- 工作流编辑器离开确认
- 删除操作确认（已有部分，需统一风格）
- 遵循 OpenCode 设计规范样式

---

## 执行顺序和依赖关系

```
Phase 1.1 (列表页) ──┐
Phase 1.2 (编辑器导航) ─┤── 可并行
Phase 1.3 (节点面板树形) ─┤
Phase 1.6 (数据处理连通) ─┘
         │
         ▼
Phase 1.4 (代码编辑增强) ── 依赖 1.2, 1.3
Phase 1.5 (导入导出) ── 依赖 1.1
Phase 1.7 (输出节点) ── 独立
         │
         ▼
Phase 2.1 (抓取因子数据) ── 依赖 Phase 1 完成
         │
         ▼
Phase 2.2 (因子库前端) ── 依赖 2.1
Phase 2.3 (因子API适配) ── 与 2.2 并行
Phase 2.4 (因子池) ── 依赖 2.2, 2.3
         │
         ▼
Phase 3.1 (Dashboard) ── 依赖 Phase 1, 2 完成（需知道最终模块结构）
Phase 4 (UI细节) ── 最后统一处理
```

## 关键约束

1. **零模拟数据原则**: 所有数据必须来自真实后端计算或真实数据存储，禁止 mock
2. **OpenCode 设计规范**: 所有前端实现必须严格遵循 `/frontend/DESIGN-opencode.ai.md` — 颜色 `#fdfcfc`/`#201d1d`/`#f1eeee`/`#007aff`、4px 圆角、hairline 边框、无阴影无渐变、ASCII 标记 `[+]`/`[-]`
3. **现有架构保持一致**: React + Tailwind + ReactFlow + Zustand + React Query + Monaco Editor 技术栈不变
4. **后端兼容**: 所有新 API 保持 RESTful 风格，与现有路由结构一致

## 被拒绝的替代方案

- **LiteGraph 替代 ReactFlow**: 参考网站使用 LiteGraph(Canvas)，但本地项目已使用 ReactFlow(SVG)，迁移成本过高且 React 生态集成更好，不替换
- **只搬运部分节点**: 用户要求完整搬运全部 48 个节点，不做删减。所有节点（含智能体/ML）都有用，全部实现
- **本地重新计算因子 IC**: 用户明确要求直接使用参考网站已计算好的 IC 数据，不做本地重新计算。仅在用户手动触发时才重算
- **自行生成预置因子**: 用户要求完整搬运网站上的 608 个因子，不自行编造或生成因子数据
- **搬运参考网站视觉风格**: 用户明确要求按 OpenCode 设计规范执行，不参考参考网站的视觉风格
