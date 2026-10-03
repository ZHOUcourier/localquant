# 新开一个 develop 分支吧。

**Session:** 2026-09-10 21:40 ~ 2026-09-10 22:29

**Work Directory:** `/Users/victor/Desktop/coding/localquant`

**Session ID:** `sess_a862f0fb-633d-4a91-9318-85a4198a6c3c`（zcode://sess_a862f0fb-633d-4a91-9318-85a4198a6c3c）

**Exported:** 2026-10-03 23:41 · agent-dump 1.1.1

---

### **You**
新开一个 develop 分支吧。
Readme 文档中存在大量功能描述，优化其放置位置和展现方式。并且，readme文档中的功能似乎存在重复描述的情况需要修正。

### **You**
新开一个 develop 分支吧。
Readme 文档中存在大量功能描述，优化其放置位置和展现方式。并且，readme文档中的功能似乎存在重复描述的情况需要修正。

### **Assistant**
The user wants me to:
1. Create a new `develop` branch
2. The README has a lot of feature descriptions - optimize their placement and presentation
3. There seem to be duplicate feature descriptions in the README that need fixing

Let me start by creating the develop branch and reading the README.

This is a task that involves restructuring a README document. Let me first look at the README to understand its structure. The user gave a fairly clear task: create develop branch, reorganize README feature descriptions, fix duplicates.

Let me start with creating the branch and reading the README.

我先创建 develop 分支，然后通读 README 找出重复的功能描述。

### **Assistant**
Let me analyze the README structure:

1. **Title + intro** (line 1-3)
2. **投资边界 system-level constraint** (line 5)
3. **功能模块** (line 7-22) — a giant table with 13 modules, each cell crammed with tons of feature details
4. **工作流编辑器中的节点设计细节** (line 24-36) — details about nodes
5. **QUBE 策略 Agent 与代码沙箱** (line 38-42)
6. **自定义节点** (line 44-67)
7. **技术栈** (line 69-79)
8. **快速开始** (line 81-139)
9. **项目结构** (line 141-170)
10. **注意事项** (line 174-200) — huge "notes" section with lots of feature descriptions mixed with caveats
11. **License** (line 202-212)

Problems identified:

1. **功能模块 table is overloaded**: Each table cell contains massive amounts of detail (some cells are 300+ words). This is hard to read — should be converted to sections with bullets, or keep table high-level and move details.

2. **Duplication**: Let me identify duplicate descriptions:

   - **市场环境/风格轮动**: Line 12 (数据探索 - "市场环境仪表盘（宽基牛/震荡/熊判定 + 小盘/成长/中盘 vs 大盘风格轮动，数据中心顶部）") AND Line 35 ("市场环境节点能力：/api/regime/overview 基于本地指数日线缓存输出宽基趋势状态（MA20/MA60/动量/HV20 联合判定牛/震荡/熊）、风格轮动（小盘/成长/中盘 vs 大盘 20 日相对强弱），数据中心顶部仪表盘展示") — duplicated.
   
   - **市场环境 also in 工作台**: Line 21 "首页每日研究简报：市场状态 + ..." — that's a different feature (briefing), fine.
   
   - **投资边界/普通多头 constraints**: Line 5 (top callout), Line 15 (策略回测 - "**仅普通股票多头**（`normalize` 固定为 `long_only`...）"), Line 33 (回测节点 - "**投资边界固定为普通多头**..."), Line 40 (QUBE Agent - "Agent 系统提示词固定为**普通股票多头**约束"), Line 178 (注意事项 - "**交易边界**：系统只做普通股票多头..."). This is repeated 4-5 times. The top callout is the authoritative one; others can reference it.
   
   - **T+1 成交**: Line 15 ("**执行口径统一为 T 日信号 → T+1 收盘成交**（信号当日与建仓当日均不计收益，无前视）") AND Line 33 ("T 日信号 T+1 收盘成交（信号当日与建仓当日均不计收益）") — duplicated between 策略回测 module row and 回测节点 detail.
   
   - **交易成本拆分**: Line 15 ("**交易成本拆分**（佣金/滑点/印花税分列金额、占比与 bps/换手）") AND Line 33 ("成本明细拆分输出（佣金/滑点/印花税分列）") — duplicated.
   
   - **停牌/一字板预算缩减**: Line 5 ("停牌/一字板冻结旧仓时买入按预算缩减"), Line 15 ("停牌/一字板冻结旧仓时买入按预算缩减，缩减天数见 leverage_summary"), Line 33 ("停牌/一字板导致调仓无法成交时不推演挂单...冻结旧仓挤占预算时买入按预算缩减...（缩减天数见 leverage_summary）") — triplicated.
   
   - **事件研究**: Line 12 数据探索 has "事件研究（一字涨/跌停、放量、除权除息、手工事件 → 窗口 CAR/BHAR + t 值 + 正值占比...）" — and 注意事项 Line 183 has "**事件研究窗口语义**：window_before/window_after..." — the 注意事项 one is a semantics note, could stay but overlaps.
   
   - **前向填充收益率**: Line 15? No — 注意事项 Line 181 ("**收益率面板统一为前向填充口径**...复牌日的跳空涨跌如实入账") AND Line 15 (策略回测 - "**复牌跳空收益**（收益率前向填充口径，停牌损失如实入账）") — duplicated.
   
   - **退市强制清算**: Line 15 ("**退市强制清算**（数据提前截止的持仓按末日价 ×(1-delisting_loss) 变现，delisting_events 明细 + assumptions 明示）") AND Line 184 (注意事项 - "**数据提前截止（退市/缓存截断）强制清算**：...") AND Line 20 (数据管理 - "**退市/历史代码清单**（维护退市代码...消除幸存者偏差）") — the 退市清单 itself is a different feature, but the delisting liquidation is duplicated between 策略回测 and 注意事项.
   
   - **历史参考快照导入**: Line 20 (数据管理 - "**历史参考快照导入**（指数成分/行业/合约名称/两融池 as-of 导入，仅作研究元数据...）") AND Line 190 (注意事项 - "**历史参考快照导入**（POST /api/data/import-reference）：QMT 只能提供当前成分/名称/行业/两融池...") — duplicated almost verbatim.
   
   - **退市/历史代码清单**: Line 20 AND Line 184 (mentioned in the delisting bullet) — partially duplicated.
   
   - **AI 配置 / 供应商预置**: Line 22 (AI 辅助 - "供应商预置（免填 URL，对齐 models.dev）/ 自定义 BYOK / 本机 CLI 工具三种接入") AND Line 41 (QUBE section - "**独立 AI 配置**：QUBE 的供应商/模型/推理强度/API Key/CLI 与「设置 → AI」完全分开，各存各的 .env 键。供应商预置对齐 models.dev，含 OpenCode Zen/Go、DeepSeek...") — the models.dev 供应商预置 is duplicated. Line 41 is about QUBE-specific independence, but re-lists all providers.
   
   - **沙箱**: Line 42 (代码沙箱 bullet), Line 77 (技术栈 - "**沙箱**: OpenSandbox..."), Line 89 (环境要求 - "Docker Desktop（可选...）"), Line 114-124 (快速开始 - 代码执行沙箱 section), Line 196 (注意事项 - 执行加固 mentions sandbox indirectly? No, 执行加固 is about other things). The 沙箱 appears in QUBE section (42), 技术栈 (77), 快速开始 (89, 114-124). Line 42's description overlaps heavily with 快速开始's sandbox section: "回测/QUBE 的信号代码经 backend/services/sandbox.py 执行——优先用 OpenSandbox 容器隔离...Docker/服务未就绪时降级为进程内执行并标注...GET /api/system/sandbox 会实际探测" vs 快速开始 "未启 Docker/沙箱服务时，回测会自动降级为进程内执行（无容器隔离，日志/回测结果会标注）；状态可查 GET /api/system/sandbox（实际探测 server，active=false 即当前为进程内降级）". Clear duplication.
   
   - **walk-forward 样本外验证**: Line 13 (因子研究 - "**样本外验证**（walk-forward 滚动锚定分割，每折 in-sample/OOS IC + 分层多空统计量，防过拟合...）") AND Line 34 ("**因子样本外验证节点**：walk-forward 滚动锚定分割（训练 [0,t) → 测试 [t, t+test) 逐折后移），输出每折 in-sample IC 与 OOS IC/分层多空统计量...）") — one is the 因子研究页 feature, the other is the workflow node. They're similar but distinct surfaces (page vs node). Still heavily overlapping — could merge description.
   
   - **组合 walk-forward 回测** (Line 13) — separate feature.
   
   - **数据时效检查**: Line 20 (数据管理 - "数据时效检查（交易日历口径：QMT 日历优先、工作日近似兜底，长假不误报）") AND Line 194 ("数据时效可在 GET /api/data/freshness 查看（最新交易日 + 显著滞后标的清单）") — partially duplicated.
   
   - **导出**: Line 13 ("**因子面板导出 CSV**（/api/factor/export-panel，研究交付与离线复核）") AND Line 191 ("**研究交付导出**：因子面板与前瞻收益可导出 CSV...回测记录可导出...") — duplicated.
   
   - **面板 artifact**: Line 193 ("全市场面板本地 artifact...") — this is an implementation note in 注意事项; fine to keep there or move.
   
   - **节点缓存随数据失效**: Line 192 — 注意事项 only.
   
   - **节点端口/颜色/说明/代码编辑**: Lines 26-29 are workflow editor details — fine in the node details section.
   
   - **因子重算覆盖更新**: Line 30 ("**因子重算**：预置因子重算 IC 采用覆盖更新语义...可在因子详情「重算历史」中回溯") AND Line 13 (因子研究 - "结果覆盖更新+历史快照" in 批量扫描) — partially overlapping: Line 13's 批量扫描 mentions "结果覆盖更新+历史快照", Line 30 says the same thing for 因子重算. These are the same semantics (批量扫描 and 重算 both do 覆盖更新+历史快照). Partial duplication.

   - **IC 排序/因子库**: Line 13 mentions 因子库卡片/列表双视图、IC 排序与筛选 — unique.

   - **参数敏感性**: Line 15 — unique.

   - **AlphaLens**: Line 13 ("另备 AlphaLens 分析（行业分组 IC/分层收益/因子加权多空统计量/换手率）与自研综合报告互补") AND Line 32 ("「因子分析（AlphaLens）」调用 alphalens-reloaded 产出行业分组 IC/分层收益等") AND Line 74 (技术栈 - "alphalens-reloaded（行业分组/因子加权多空等标准口径）") — triple mention, though tech stack mention is fine.

   - **风格归因**: Line 15 ("**回测风格归因**（回测记录页一键运行：组合收益 ~ Σ β×风格因子收益 + alpha...）") AND Line 19 (风险与组合分析 - "**回测归因含行业因子**（均值偏离编码，回答「超额来自行业还是选股」）...**回测记录风格归因**（回归法，/api/risk/attribution-run）") — duplicated between 策略回测 and 风险与组合分析 rows. Both describe 回测记录页的风格归因.

   - **组合优化仅允许纯多头**: Line 19 — part of investment boundary repetition but small.

   - **SQL/AI SQL**: Line 12 (数据探索 - "SQL 查询（含 AI 生成 SQL、结果解读、SQL 历史/收藏与字段字典/查询模板）") AND Line 22 (AI 辅助 - "数据探索 SQL 生成与结果解读") — duplicated.
   
   - **节点代码改写**: Line 11 (工作流编辑器 - "节点右键查看/编辑代码（Monaco + AI 改写 + ruff 诊断）") AND Line 22 (AI 辅助 - "节点代码改写、自然语言生成工作流、因子分析建议...") — the AI 辅助 row is essentially an index of AI features described elsewhere. It's a summary row, could be OK but contributes to duplication feel.

   - **因子分析建议**: Line 13 ("逐因子 AI 分析") AND Line 22 ("因子分析建议") — duplicated.

   - **基准对比**: Line 15 ("支持可选基准对比（如 000300.SH）") AND Line 33 ("支持可选基准对比（跟踪误差/信息比率）") — duplicated.

3. **注意事项 section is a catch-all**: It mixes true caveats (xtquant Windows-only, security) with feature documentation (历史快照导入, 研究交付导出, 数据时效, 强制清算). Many of these belong in the feature modules.

The user asks:
1. 新开 develop 分支 ✓ (done)
2. 优化 README 中大量功能描述的放置位置和展现方式 — the 功能模块 table is unwieldy (huge cells); the 注意事项 mixes features and caveats.
3. 修正重复描述.

My plan:
- Restructure the README:
  - Keep the top: title, intro, investment boundary callout.
  - Replace the 功能模块 giant table with a **功能总览 table (short, one-line per module)** + **分模块小节 (### per module) with bullets** — or group modules into thematic sections (研究流程: 数据探索 → 因子研究 → 分钟因子 → 策略回测 → 风险分析; 平台: 工作流编辑器, QUBE Agent, 策略库, 实验管理, 数据管理, 工作台, AI 辅助).
  
  Actually, let me think about what's best for a README. A common pattern:
  - 功能总览 (short table: module + one-sentence description) for scanning
  - Then "功能详解" or per-module subsections with concise bullets for details.
  
  But that might make the README very long. Alternative: keep a structured module section with subsections and bullets (not a table), merging duplicates. The current README is ~213 lines. A restructure will probably keep similar length but better organized.

  Let me decide the target structure:

  ```
  # LocalQuant — 本地投研工作站
  intro
  > 投资边界 callout (authoritative, single source for 多头约束)

  ## 功能总览
  (one-line-per-module table — 13 rows, short)

  ## 核心功能详解
  ### 工作流编辑器
  ### 数据探索
  ### 因子研究
  ### 分钟因子 · 日内高频
  ### 策略回测
  ### QUBE 策略 Agent
  ### 策略库 / 实验管理
  ### 风险与组合分析
  ### 数据管理
  ### 工作台 / AI 辅助

  ## 工作流节点设计细节
  (existing bullets, deduplicated: remove 市场环境节点 (merge into 数据探索 or keep — it's a node capability), remove 回测节点 details that duplicate 策略回测 module... but the node section is specifically about the workflow nodes, so keep node-specific bits, remove general bits already covered in 策略回测)

  ## 代码沙箱
  (merge QUBE section's sandbox bullet + 快速开始's sandbox section? The 快速开始 has operational setup steps — keep setup there, keep the "what it is" briefly in QUBE/platform section, reference 快速开始)

  ## 自定义节点 (keep)

  ## 技术栈 (keep)

  ## 快速开始 (keep, remove duplicate sandbox explanation, keep steps)

  ## 项目结构 (keep)

  ## 注意事项 → rename to 「严谨性与设计约定」 keep only true conventions/caveats:
  - remove features that moved to modules (历史快照导入 → 数据管理; 导出 → 因子研究/回测; 强制清算 → 策略回测; 市场环境 → 数据探索)
  - keep: 可交易掩码, 前向填充口径, 滚动 IC 无前视, 事件研究窗口语义 (maybe move to 数据探索? it's a semantics convention — keep in 严谨性), IC 口径细节, point-in-time, 默认股票池剔除指数, 面板 artifact, 复权存储, 空数据错误统一, 访问安全, 执行加固, 工程检查
  - Actually many of these are great "严谨性约定" content — keep them as a dedicated section since they're a selling point. But trim the feature-y parts.
  ```

Wait — I should be careful about scope. The user said: "Readme 文档中存在大量功能描述，优化其放置位置和展现方式。并且，readme文档中的功能似乎存在重复描述的情况需要修正。"

So: reorganize placement/presentation of feature descriptions + fix duplicates. This is a documentation refactor. I have full latitude on structure. Let me design a clean structure and write it.

Let me carefully enumerate all content and decide where each piece goes, ensuring no loss of information (important — this README is dense with real information; I must not drop facts, only reorganize and dedupe).

Let me list every fact and its target:

**Line 3 intro** — keep.

**Line 5 投资边界 callout** — keep as the single authoritative statement. Other places will reference "见顶部投资边界" instead of restating. But some restatements carry extra info:
- Line 15: "总仓位 ≤ 100% 为循环内硬约束——停牌/一字板冻结旧仓时买入按预算缩减，缩减天数见 leverage_summary/assumptions" — the callout already says 停牌/一字板冻结旧仓时买入按预算缩减. The leverage_summary detail is unique → keep in 回测 section only.
- Line 33: "逐仓风控（止盈/止损/移动止损）仅作用于多头持仓；停牌/一字板导致调仓无法成交时不推演挂单（持仓保持，次数在 assumptions 明示）" — "不推演挂单、次数在 assumptions 明示" is unique → move to 回测.
- Line 40: QUBE 系统提示词固定多头约束 — keep briefly in QUBE section ("系统提示词同样锁定普通多头边界").
- Line 178: 注意事项交易边界 — remove, replaced by callout reference. Actually 注意事项 could drop the bullet entirely since the callout covers it. Or keep one-line pointer. I'll drop it and let the callout be the single place. Hmm, but 注意事项 as a list — dropping is fine since top callout is prominent.

**功能模块 table → restructure**. New plan:

`## 功能总览` — a compact table with **模块 | 一句话说明**. Then `## 功能详解` (or just individual `###` under a `## 功能模块`) with short bullets per module.

Actually, wait. Let me think about the reading experience. 13 modules each with 3-8 bullets = long but scannable. The current table is unreadable because cells have 300+ chars. Converting to `### Module` + bullets is the classic fix.

But 13 subsections might bloat the README's TOC. Alternative: group into 4-5 thematic groups:

1. **研究主线** (数据探索 / 因子研究 / 分钟因子 / 策略回测 / 风险与组合分析)
2. **Agent 与工作流** (工作流编辑器 / QUBE 策略 Agent / 自定义节点)
3. **资产与沉淀** (策略库 / 实验管理 / 数据管理 / 工作台)
4. **AI 辅助** (横切能力)

Hmm, but the user may want module structure preserved. Let me keep the 13 modules as `###` headings under `## 功能模块`, each with tight bullets. And keep an overview table? That risks duplicating again (one-liner + bullets is fine — the one-liner is a summary, bullets are details; that's presentation, not duplication).

Actually to avoid re-introducing duplication, I'll do: `## 功能模块` with `### <模块名>` subsections + bullets. No separate overview table. The headings themselves give the scan list. That's cleaner. Hmm, but a compact overview table is nice for a README landing scan... The intro paragraph (line 3) already enumerates: 数据探索、因子研究、策略回测、QUBE 策略 Agent、策略库与实验管理. Good enough.

Let me go with per-module `###` + bullets. Now the dedup decisions:

### 工作流编辑器 (from line 11 + node details 26-32 + 部分 33)
Bullets:
- iframe 内嵌官方 ComfyUI 前端，搭建研究管线
- 节点右键查看/编辑代码（Monaco + AI 改写 + ruff 诊断）；所有代码编辑界面统一带「网页全屏」编辑器 (merge line 29 here)
- 因子分析节点「显示分析结果」直接弹出综合报告
- 内置节点代码 fork 保护
- 底部本机性能监控
- 节点完整输出落本地 pkl、运行记录只存预览，明细按需取（API）；运行产物长期保留；显式清理接口 (POST /api/workflow/runs/cleanup, dry_run 默认)
- 工作流日志：按级别、按节点/全局筛选、时间排序 (from line 36)
- 节点端口设计：仅数据型输入生成端口 (line 26)
- 节点颜色统一 nodeColors.ts (line 27)
- 节点说明卡：左侧面板悬停 + 配置面板同款文档 (line 28)
- 工作流因子链路 (line 32): 因子构建（公式/代码）→ 标准化/中性化 → 分析节点们，截面计算；自研因子分析与因子研究页同源；AlphaLens 节点；「显示分析结果」
- 因子构建（公式）节点可直接跑因子库 Alpha 公式，按股票池+区间自取行情 (from line 31 — partially; line 31 is mostly about 因子编写 which belongs in 因子研究 module. Let me split: the 公式节点 capability → 工作流编辑器 (factor chain bullet); the 因子编写 field/算子/数据注入 → 因子研究 module.)

### 数据探索 (from line 12)
- 数据概览、SQL 查询（AI 生成 SQL、结果解读、历史/收藏、字段字典/查询模板）
- 全市场扫描、横截面分析、异常检测；本地 Parquet 缓存
- 市场环境仪表盘 (merge line 35 here): 宽基牛/震荡/熊（MA20/MA60/动量/HV20）+ 风格轮动（小盘/成长/中盘 vs 大盘 20 日相对强弱），数据中心顶部；工作流亦提供市场环境节点 (/api/regime/overview)
- 事件研究: 一字涨/跌停、放量、除权除息、手工事件 → 窗口 CAR/BHAR + t 值 + 正值占比；基准指数与市场模型 alpha/beta；事件日聚类稳健 t；calendar-time portfolio 月度检验；近邻事件合并 (line 12) + 窗口语义 (line 183 的 window_before/after 语义 — 这是语义约定，可放严谨性 or here。它是「严谨性约定」bullet 的一部分。I think moving it to 事件研究 bullet as a sub-point makes it more discoverable: "窗口语义：window_before/after 为事件前/后天数，相对日 [-before, +after]，边界截断按实际相对日对齐". Yes, move here.)
- 全市场扫描的 memory 保护? That's in 因子研究's 批量扫描. OK.

### 因子研究 (from line 13 + 30 + 31 + parts of 186/191/13)
- 因子库：卡片/列表双视图、IC 排序筛选、公式（LaTeX+Python）与指标查看、逐因子 AI 分析
- IC 汇总/分层平均收益/单调性；量化算子库
- 因子编写：公式/代码共用字段与算子；基本面 fund_*（公告日点位）、market_cap/turnover（股本快照）、行业映射；可用性动态标注；详见 docs 指南 + 「变量参考」(line 31)
- 因子批量扫描：勾选类别/因子 → SSE 进度 → IC/RankIC/ICIR 排序 → 入池；覆盖更新+历史快照；指标来源标注（external_ref/local_recalc，line 186 的门槛规则也放这）；股票池分批、内存保护、置信度警示、多重检验提示
- 因子重算/覆盖更新语义 (line 30): merge into 批量扫描 bullet or separate small bullet: 预置因子重算采用覆盖更新（新指标写回原记录），旧值自动入历史快照，详情页「重算历史」回溯 — actually line 30 says "预置因子重算 IC" while line 13 批量扫描 says "结果覆盖更新+历史快照". They're the same mechanism. Merge into one bullet: "重算/批量扫描结果**覆盖更新**语义：新指标写回原记录，旧值自动存历史快照，因子详情「重算历史」可回溯".
- 因子体检：生命周期阶段 + IC 趋势徽标
- 因子池拥挤度
- 样本外验证 (merge line 34): walk-forward 滚动锚定分割，每折 in-sample/OOS IC + 分层多空统计量、聚合 OOS 均值/t 值/同向一致性/衰减；因子研究页与工作流节点均提供；防过拟合
- 因子池→组合回测闭环：等权/滚动 IC 加权（样本外权重无前视）→ 每日 Top-N 做多 → 回测 → 绩效 → 风格+行业归因
- 组合 walk-forward 回测：训练窗定权重 → 测试窗出信号 → 滚动拼接 OOS 净值 + 全样本参考对比
- AlphaLens 分析（行业分组 IC/分层收益/因子加权多空/换手率）与自研综合报告互补
- 因子面板导出 CSV (merge line 191 部分): POST /api/factor/export-panel — 研究交付
- IC 口径细节 (line 187): IC 标准差 ddof=1；单调性只奖励递增；合成先去均值再 z-score；IC 衰减与汇总同口径 — these are 严谨性约定; could stay in 严谨性 section. They're methodology guarantees. I'll keep them in 严谨性约定 (they apply broadly). Hmm — but user wants feature descriptions placed well. IC 口径 is methodology, belongs in 严谨性. Keep in 严谨性.
- 多重检验提示 — in 批量扫描 bullet already.

### 分钟因子 · 日内高频 (line 14) — mostly unique, keep as-is, light reformat to bullets:
- 分钟缓存 1m~60m → 自动清洗（竞价 bar 剔除、半日市/一字板标记）→ 分钟公式求值（m_* 字段、ID_*/M_* 算子、预置高频因子列表）→ 折叠日频面板复用
- 时刻 IC 曲线（09:45~14:55 截面 RankIC）
- 回测 execute_at 执行时点（next_close/尾盘/next_open 计收益口径）
- 因子库「日内高频」类别 14 个预置因子，批量扫描自动分流
- 工作流「因子构建（分钟）」节点

### 策略回测 (line 15 + 33 node part + 184 delisting + 181 复牌跳空)
- 向量化回测 + 绩效指标 + 净值/回撤曲线；工作流回测节点与 QUBE 工作台共用
- 执行口径：T 日信号 → T+1 收盘成交（信号日与建仓日不计收益，无前视）
- 仅普通多头 → 引用顶部投资边界；总仓位 ≤100% 硬约束；停牌/一字板冻结旧仓时买入按预算缩减（leverage_summary）；调仓不成交不推演挂单（assumptions 明示次数）(merge 33's unique bits)
- 逐仓风控（止盈/止损/移动止损）仅作用于多头持仓 (from 33)
- 交易成本拆分（佣金/滑点/印花税分列，占比与 bps/换手）；参数敏感性网格扫描
- 容量分析（参与率约束、逐档资金规模、受限天数比例、理论容量上限、ADV 窗口可调、未模拟项明示）
- 退市强制清算 (merge 184): 数据提前截止的持仓按末日价 ×(1-delisting_loss) 强制变现，delisting_events 明细 + assumptions 明示；配合数据管理页「退市/历史代码清单」维护
- 复牌跳空收益（前向填充口径）(merge 181 的引用 — the full 前向填充 rationale stays in 严谨性; here one line)
- 回测风格归因（记录页一键：组合收益 ~ Σβ×风格 + alpha）(merge with 19 — see below)
- 可选基准对比（如 000300.SH；跟踪误差/信息比率）
- 回测记录导出（equity/returns/trades/log）(from 191)

Where does 回测风格归因 live — 策略回测 or 风险与组合分析? Line 15 puts it in 策略回测; line 19 (风险) has "**回测归因含行业因子**（均值偏离编码...）" and "**回测记录风格归因**（回归法，/api/risk/attribution-run）". These describe the same feature from two angles: 回测记录页一键运行风格归因 (回测) and the 风险 service providing 行业因子归因 + API. Best: put the full description in 风险与组合分析 (since it's the risk module's capability) OR in 策略回测 with cross-ref. I'll put it once in 策略回测 (it's triggered from 回测记录页): "回测风格+行业归因（回归法，风格因子 + 行业因子均值偏离编码，回答超额来自风格/行业/选股；/api/risk/attribution-run）" and in 风险与组合分析 keep 风格暴露/优化/压力测试 etc. without re-describing 回测归因. Actually line 19's 风险 module has its own "组合事前风险预测"、"风格暴露（Barra 精简）" — those are unique. The duplicated bit is the 回测归因. Single placement: 策略回测 module. In 风险 module, I'll mention "风格/行业归因引擎同时服务回测记录页" — hmm, that's still a mention. Better: keep it only in 风险与组合分析 (since Barra 风格因子库、行业编码 live there) and in 策略回测 write "一键风格/行业归因（见风险与组合分析）"? Cross-references in a README are okay but weak. Decision: describe fully under 风险与组合分析 as "回测归因" item; in 策略回测 keep just "回测记录页一键运行风格/行业归因（回归法）" — no. That's still duplication.

OK final: put the feature in 策略回测 (user action location) with the full description including 行业因子均值偏离编码, and remove from 风险与组合分析 entirely. 风险 module keeps: 风格暴露、组合优化、绩效补充指标、压力测试+历史情景回放、组合事前风险预测、块自助蒙特卡洛、本地行情缓存加载面板。Wait, "支持从本地行情缓存加载面板（股票池+区间，前复权）" (line 19) — that's a 风险 module input feature; keep there. And "/api/risk/attribution-run" API mention — include in the 回测归因 bullet under 策略回测.

### QUBE 策略 Agent (line 16 + 40 + 41)
- 多轮对话设计策略（pi-agent-core 架构工具调用循环 + 事件流）；内置工具 read_doc/preview_data/run_backtest/save_strategy
- 右侧策略工作台分屏（代码/回测/日志/版本 + AI 优化/自动优化）
- 系统提示词锁定普通多头边界（引用顶部）
- 独立 AI 配置：与设置→AI 完全分开，各存 .env 键；供应商预置对齐 models.dev（OpenCode Zen/Go、DeepSeek、Zhipu/Z.AI、Kimi、Alibaba、Moonshot、MiniMax 等，免填 Base URL），BYOK 或本机 CLI 引擎
- 策略默认「工作中」，用户手动「已保存」→ that's 策略库 module (line 17). Keep there.

### 策略库 (line 17) — short, keep:
- 工作中/已保存两态；QUBE 与工作流产出默认工作中，手动保存；版本历史回滚

### 实验管理 (line 18) — keep:
- 实验记录、多实验对比、研究日志；回测/工作流完成自动创建并关联 source_id

### 风险与组合分析 (line 19 minus 回测归因)
- 风格暴露（Barra 精简）
- 组合优化（SLSQP 带约束，仅纯多头）
- 绩效补充指标（alpha·beta/上下行捕获/Active Share）
- 压力测试 + 历史情景回放（2015/2018/2024 × 当前权重）
- 组合事前风险预测（因子协方差 → 预测波动 + 风险贡献分解）
- 块自助蒙特卡洛（保留自相关与波动聚集）
- 从本地行情缓存加载面板 / 回测记录分析入口

### 数据管理 (line 20 + 190 + 184 的退市清单部分)
- QMT 数据下载、缓存管理、数据质量检查（价格跳变/量能尖峰/疑似停牌退市披露；单列参考快照）
- 最近除权事件清单（adjust_factor 跳变）
- 财务快照拉取（Cashflow；别名归一）
- 标的池快照（两融/沪深股通，市场结构参考）
- 宽基指数成分自动快照（逐日 as-of 积累）
- 数据时效检查（交易日历口径，长假不误报；GET /api/data/freshness 合并 line 194）
- 退市/历史代码清单（消除幸存者偏差；批量下载自动并入）(merge 184's pointer)
- 历史参考快照导入（merge line 190: POST /api/data/import-reference；constituents/industry/instrument/margin as-of；解决 QMT 只有当前快照的历史回溯问题；仅参考元数据）

### 工作台 (line 21) — keep, unique:
- 每日研究简报：市场状态 + 研究数据就绪度 + 因子池体检摘要 + 近 7 日除权 + 数据时效 + 最近批处理；15 分钟自动刷新

### AI 辅助 (line 22) — this row duplicates AI features described in modules. Rewrite as cross-cutting summary without re-listing where they already exist? The row lists: 节点代码改写、自然语言生成工作流、因子分析建议、数据探索 SQL 生成与结果解读；三种接入方式；模型下拉与推理强度。
- 节点代码改写 → already in 工作流编辑器 (Monaco + AI 改写)
- SQL 生成解读 → already in 数据探索
- 因子分析建议 → already in 因子研究 (逐因子 AI 分析)
- 自然语言生成工作流 → unique! Not mentioned elsewhere.
- 接入方式（供应商预置/BYOK/CLI、模型下拉、推理强度）→ partially duplicated in QUBE 独立 AI 配置 (line 41 lists providers).

Resolution: AI 辅助 becomes "跨模块 AI 能力" short section: "AI 能力贯穿各模块：节点代码改写与诊断（工作流）、自然语言生成工作流、SQL 生成与结果解读（数据探索）、逐因子 AI 分析（因子研究）。接入方式：供应商预置（免填 URL，对齐 models.dev）/ 自定义 BYOK / 本机 CLI 工具，模型下拉选择与推理强度可调。" — Hmm, that still re-lists. But a cross-cutting section that indexes where AI appears is legitimately useful and is presentation, not duplication, IF the modules themselves don't re-describe the AI bits. To truly dedupe: modules keep feature bullets but strip AI-specific wording, and AI section lists the AI touchpoints. E.g.:
- 工作流编辑器: "节点右键查看/编辑代码（Monaco + ruff 诊断 + AI 改写）" → keep AI mention minimal or drop "AI 改写" and let AI section carry it.
Simplest robust approach: keep short AI mentions inline (users scanning a module want to know AI is there), and make the AI 辅助 section only about **接入与配置** (providers/BYOK/CLI/model selection/effort) + one line "AI 能力散布于：节点代码改写、NL 生成工作流、SQL 生成解读、因子分析建议（见各模块）". One-line index is fine.

But then QUBE 独立 AI 配置 (line 41) re-lists providers incl. the long provider list. Dedupe: provider list lives once. Where? QUBE section's "独立 AI 配置" is specifically about QUBE's independence; the general AI 接入 is in AI 辅助. The provider enumeration (OpenCode Zen/Go、DeepSeek、Zhipu/Z.AI（含 Coding Plan）、Kimi、Alibaba、Moonshot、MiniMax) appears only in line 41. AI 辅助 says "供应商预置（免填 URL，对齐 models.dev）". So: keep full provider list in AI 辅助 (the general AI config place), and QUBE section says "供应商/模型/推理强度/API Key/CLI 与设置→AI 完全独立，各存各的 .env 键；同样支持供应商预置/BYOK/本机 CLI" without re-listing providers. 

### 工作流节点设计细节 section (24-36): after moving 市场环境节点 (→数据探索), 回测节点 unique bits (→策略回测), 样本外验证节点 (→因子研究 合并), 因子重算 (→因子研究), 因子编写 (→因子研究), 工作流因子链路 (→工作流编辑器), 日志 (→工作流编辑器), 端口/颜色/说明/代码编辑 (→工作流编辑器)... the section empties out. So I can dissolve it entirely into the modules! That's the "优化放置位置" ask. The section title "工作流编辑器中的节点设计细节" suggests these are editor-specific, but most items are actually feature descriptions that belong to their modules.

Hmm wait — should 节点端口/颜色/说明 stay as "编辑器 UX" bullets? They're editor UX details → 工作流编辑器 module. Yes.

So new structure:

```
# LocalQuant
intro
> 投资边界

## 功能模块
### 工作流编辑器
### 数据探索
### 因子研究
### 分钟因子 · 日内高频
### 策略回测
### QUBE 策略 Agent
### 策略库
### 实验管理
### 风险与组合分析
### 数据管理
### 工作台
### AI 辅助

## 代码沙箱  (merged: line 42 "what it is" + keep 快速开始 setup steps there)
   Actually sandbox straddles: description (42) + setup (114-124) + tech stack (77). 
   Option: keep a short "代码沙箱" subsection under 快速开始 (operational) and remove line 42's duplication, leaving in QUBE section one line "信号代码经沙箱隔离执行（见快速开始）". The system probe detail (GET /api/system/sandbox 实际探测) — keep in 快速开始 sandbox subsection.

## 自定义节点 (keep as-is)

## 技术栈 (keep; sandbox line stays — it's a one-liner inventory, fine)

## 快速开始 (keep; sandbox subsection keeps setup + probe + degrade behavior)

## 项目结构 (keep)

## 严谨性约定 (renamed from 注意事项's 严谨性约定 block; keep methodology bullets)
   - 可交易掩码（as-of ST/次新）
   - 前向填充收益率口径
   - 滚动 IC 加权无前视
   - IC 口径（ddof=1/单调性/合成/衰减同口径）
   - point-in-time 参考数据
   - 默认股票池剔除指数
   - 参数/样本/指标溯源 provenance
   - 预置因子指标分来源 → moved to 因子研究? It's a rule (入池门槛) — I said put in 因子研究批量扫描 bullet. Also fine to keep the rule here. Choose one: put in 因子研究 (where 入池 happens). Remove from 严谨性.
   - 工作流节点缓存随数据失效
   - 全市场面板 artifact (193)
   - 复权存储 (197)
   - 空数据错误统一 (198)
   - 事件研究窗口语义 → moved to 数据探索事件研究 bullet. OK.

## 注意事项 (true caveats)
   - xtquant Windows-only
   - 行情唯一来源 QMT + 参考元数据导入 (dedupe with 数据管理历史快照导入 — keep one-liner here pointing to 数据管理? The 注意事项 line 177 says "数据全部来自 QMT，不使用模拟数据...参考元数据可通过历史快照导入补充，见下" and line 190 details import. Since import detail moved to 数据管理, 注意事项 keeps "行情唯一来源 QMT；历史参考快照可作研究元数据补充（见数据管理）" — small overlap acceptable? To minimize duplication: 注意事项 keeps "数据全部来自 QMT，不使用模拟数据" and drops the 参考元数据 clause (it's in 数据管理). Hmm the clause "仅作为研究元数据、不改变多头约束" is a boundary clarification — the 数据管理 bullet already says 仅参考元数据. Fine.
   - 交易边界 bullet (178) → delete (top callout is authoritative). Or keep one-liner "交易边界见顶部投资边界"。 I'll delete to avoid duplication; the callout is at top and prominent. Actually hmm, someone jumping to 注意事项 might miss it. One pointer line costs little: I'll fold it: since 严谨性约定 has 多头-related items anyway... Let me just delete it; the callout is bold and at the very top.
   - 访问安全 (195) keep
   - 执行加固 (196) keep
   - 前端主题 (199) keep
   - 工程检查 (200) keep
   - 研究交付导出 (191) → moved to 因子研究 (面板 CSV) + 策略回测 (回测记录导出). Remove here.
   - 数据时效 (194) → merged into 数据管理. Remove here.
   - 历史快照导入 (190) → merged into 数据管理. Remove here.
   - 强制清算 (184) → merged into 策略回测. Remove here.

## License (keep)
```

Wait, also need to double check: 快速开始 sandbox section (114-124) vs QUBE section sandbox (42):
- 42: "回测/QUBE 的信号代码经 backend/services/sandbox.py 执行——优先用 OpenSandbox 容器隔离（数据经文件 API 以 CSV 传入，不挂载卷，兼容 Windows），Docker/服务未就绪时降级为进程内执行并标注。仅覆盖 /api/backtest/run-strategy 与 QUBE run_backtest；因子研究页与工作流因子节点保持原生执行。GET /api/system/sandbox 会实际探测 opensandbox-server（HTTP 健康探测 + TCP 兜底），不再把「包已安装/配置已开启」显示为「隔离已就绪」。"
- 114-124: "QUBE/回测的信号代码默认尝试在 OpenSandbox 容器中隔离执行（客户端已随 make install 安装）。要真正启用隔离，先启动 Docker Desktop，再单开一个终端跑沙箱服务：make sandbox-server。未启 Docker/沙箱服务时，回测会自动降级为进程内执行（无容器隔离，日志/回测结果会标注）；状态可查 GET /api/system/sandbox（实际探测 server，active=false 即当前为进程内降级）。"

Unique to 42: backend/services/sandbox.py 路径、数据经文件 API CSV 传入不挂载卷兼容 Windows、覆盖范围（仅 run-strategy 与 QUBE run_backtest；因子页/工作流因子节点原生执行）、探测方式细节（HTTP+TCP 兜底）。
Unique to 114-124: make install 已装客户端、make sandbox-server 启动步骤、降级行为、active=false 含义。
Duplicated: 降级为进程内执行并标注、GET /api/system/sandbox 探测。

Merge: create a dedicated `## 代码执行沙箱` section (or keep in 快速开始 as subsection) that has: 是什么（隔离机制、数据传递、覆盖范围）+ 怎么启用（Docker + make sandbox-server）+ 状态查询与降级。Then remove the QUBE section's sandbox bullet (leave QUBE section purely about the agent + AI config), and remove the duplicated explanation lines from 快速开始 (keep the setup commands). Also 环境要求 Docker line (89) mentions sandbox — fine, one line.

Where to place a `## 代码执行沙箱` section? It's an optional runtime component — good as a subsection of 快速开始 (since it's about running). The mechanism details (覆盖范围) are feature-y... I'll put the full merged sandbox content as a `### 代码执行沙箱（可选，推荐）` subsection in 快速开始. And in QUBE section, drop the sandbox bullet entirely (QUBE's sandbox usage is covered there: "QUBE/回测的信号代码"). Good.

Also 技术栈 line 77 sandbox one-liner — keep (inventory).

Now check other cross-dups I may have missed:

- Line 12 数据探索 "全市场扫描" vs 因子研究 "因子批量扫描" — different (全市场扫描 = market scan; 批量扫描 = factor batch scan). Keep both.
- Line 13 "因子池→组合回测闭环...风格+行业归因一键打通" vs 策略回测风格归因 — the 闭环 mentions 归因打通 as part of the loop; the 归因 feature itself described once in 策略回测. Acceptable minor overlap; I'll word the 闭环 bullet as "…→ 绩效 → 风格/行业归因一键打通" without re-describing 归因. OK.
- Line 15 "**回测风格归因**（回测记录页一键运行...）" and Line 19 "支持...与**回测记录风格归因**（回归法，/api/risk/attribution-run）" — consolidate into 策略回测 as decided. Wait, actually, reconsider: the 风险与组合分析 module is where Barra 风格暴露 lives; the attribution-run is /api/risk/*. From a module ownership view it's a 风险 service feature surfaced on 回测记录页. Either choice dedupes. I'll put it in 风险与组合分析 (where the analytic engine and Barra factors are described) and in 策略回测 keep a short "回测记录页支持一键风格/行业归因（由风险模块回归法实现）"?? That's duplication again (two mentions). 

  Decision: full description in **策略回测** (the entry point users click), and in 风险与组合分析 remove the 回测归因 mentions entirely. The 风险 module still has plenty. Also then 策略回测 bullet includes 行业因子均值偏离编码 + /api/risk/attribution-run + "超额来自行业还是选股" phrasing. Done — single place.

- Line 19 "组合优化仅允许纯多头" — investment boundary; keep one short clause in 组合优化 bullet (it's a constraint specific to that feature; the top callout says 系统不允许做空 but the 优化器 constraint is a feature-level guarantee. Keep short: "组合优化（SLSQP 带约束，仅纯多头）" — fine, minimal.)

- Line 13 "**组合 walk-forward 回测**（训练窗口定权重 → 测试窗口出信号 → 滚动拼接样本外净值，附全样本参考对比过拟合差距）" — unique. Keep.

- Line 13 批量扫描 "支持股票池分批扫描、内存保护、样本置信度警示与多重检验提示" — keep.

- Line 186 "**预置因子指标分来源**：外部抓取的参考指标标为 external_ref，本地 QMT 行情重算后标为 local_recalc；只有 local_recalc 且样本达到门槛（≥300 只、≥252 个交易日）的因子允许入因子池或进入组合回测" — merge into 因子研究 (批量扫描/指标来源). I'll put as its own bullet under 因子研究: "指标来源标注：external_ref（外部参考值）/ local_recalc（本地重算）；仅 local_recalc 且样本达门槛（≥300 只、≥252 交易日）可入池/进组合回测". Then remove from 严谨性.

- Line 189 "**默认股票池剔除指数缓存**" — 严谨性. Keep there.

- Line 192 "**工作流节点缓存随数据失效**" — 严谨性 or 工作流编辑器? It's a correctness guarantee about workflow caching — I'd put it under 工作流编辑器 as a bullet ("节点输出缓存键包含数据缓存版本，更新数据自动失效") — it's a feature of the editor. Hmm, it's listed under 严谨性约定 currently. Either works. I'll move to 工作流编辑器 (placement optimization!). 

- Line 193 全市场面板 artifact — keep in 严谨性/注意事项 as infra note. Or 数据探索? It concerns /api/factor/compute 与 /api/risk/panel. Keep in 严谨性 (engineering behavior).

- Line 197 复权存储 — keep in 注意事项/严谨性 (storage convention). Keep.

- Line 198 空数据错误统一 — keep.

- Line 195 访问安全 — keep.

- Line 196 执行加固 — keep.

- Line 180 可交易掩码 — 严谨性 keep.

- Line 181 前向填充 — 严谨性 keep (with 策略回测 bullet referencing briefly via 复牌跳空收益. Actually the 策略回测 bullet "复牌跳空收益（收益率前向填充口径，停牌损失如实入账）" IS a restatement of the 严谨性 item... but from feature view it's a backtest behavior. Keep the short feature bullet + full rationale in 严谨性. The short bullet is 1 line; acceptable? The user asked to fix duplications — a one-line feature mention + a methodology rationale section is not really "重复描述" as long as wording differs and roles differ. But to be safe I could drop the 策略回测 复牌跳空 bullet and keep 前向填充 in 严谨性... but then 回测 module misses a feature. Hmm. The 前向填充 is a research-path-wide convention (因子研究 also uses it). I'll keep 严谨性 as the single full explanation and in 策略回测 not restate it (remove "**复牌跳空收益**" bullet). Wait but it was listed as a backtest feature in line 15... The information survives in 严谨性 bullet ("复牌日的跳空涨跌如实入账"). OK remove from 策略回测 to dedupe. Hmm, actually let me reconsider — users reading 策略回测 want to know how 停牌 handled. The 严谨性约定 section will be linked/referenced... in a README people scroll. I'll keep a very short mention in 策略回测: "停牌/缺口期间收益为 0、复牌跳空如实入账（前向填充口径，见严谨性约定）" — that's a pointer, not duplication. Fine.

Actually, let me now also reconsider: is converting the big table into 12 `###` subsections with bullets the right "展现方式"? I believe yes: tables with paragraph-length cells are unreadable; headings + bullets are scannable. Also the README gains a clearer hierarchy. Length will grow slightly but readability improves. Also add a small TOC? GitHub auto-generates TOC for READMEs. Not needed.

Also note: the module bullets should preserve API paths and technical specifics — this README doubles as the project's feature registry (commits suggest it's carefully maintained). I must be careful not to lose any fact. Let me do a final fact-by-fact pass as I write.

Also the intro line 3 lists modules — keep.

One more dup check: line 21 工作台 "近 7 日除权事件" vs 数据管理 "最近除权事件清单" — different surfaces (briefing vs management), keep both.

Line 20 "数据时效检查（交易日历口径：QMT 日历优先、工作日近似兜底，长假不误报）" + line 194 "数据时效可在 GET /api/data/freshness 查看（最新交易日 + 显著滞后标的清单）" → merge into 数据管理: "数据时效检查（交易日历口径，长假不误报；GET /api/data/freshness 输出最新交易日 + 显著滞后标的清单）". Remove line 194 from 注意事项.

Line 12 "SQL 历史/收藏与字段字典/查询模板" — unique. Keep.

Line 11 cleanup API — keep in 工作流编辑器.

Line 34 样本外验证节点 details "训练 [0,t) → 测试 [t, t+test) 逐折后移...聚合 OOS IC 均值/t 值/同向一致性/衰减" — merge into 因子研究样本外验证 bullet: "walk-forward 滚动锚定分割（训练 [0,t) → 测试 [t,t+test) 逐折后移），每折 in-sample/OOS IC + 分层多空统计量，聚合 OOS 均值/t 值/同向一致性/衰减；因子研究页与工作流节点均提供，防过拟合".

Line 35 市场环境节点 → 数据探索 bullet + note "工作流提供市场环境节点（/api/regime/overview）". Wait, is /api/regime/overview used by both the dashboard and the node? Line 35 says "市场环境节点能力：/api/regime/overview 基于本地指数日线缓存输出..." and line 12 says "市场环境仪表盘（...数据中心顶部）". So API serves both. Merge: "市场环境仪表盘（数据中心顶部）：宽基牛/震荡/熊（MA20/MA60/动量/HV20 联合判定）+ 风格轮动（小盘/成长/中盘 vs 大盘 20 日相对强弱）；基于本地指数日线缓存（/api/regime/overview），工作流亦有市场环境节点".

Line 30 因子重算 → 因子研究 bullet (merge with 批量扫描 覆盖更新).

Line 31 因子编写 → 因子研究 bullet: "因子编写：公式/代码两种方式共用字段与量化算子；除量价外注入基本面 fund_*（按公告日点位）、market_cap/turnover（需股本快照）、行业映射（供 INDUSTRY_NEUTRALIZE），并据快照现状动态标注可用性（无数据时求值明确报错）；因子库 Alpha 公式可直接粘贴到「因子构建（公式）」节点运行（节点按股票池+区间自取 QMT 行情，输出 return_data 供 IC/分组收益节点直连）；详见 docs/因子编写指南.md，因子库内可点「变量参考」"。

Line 32 工作流因子链路 → 工作流编辑器 bullet: "因子链路：因子构建（公式/代码/分钟）→ 标准化/中性化 → 因子分析（一站式）/（AlphaLens）/ IC 计算 / 分组收益 / 因子衰减，均基于 QMT 行情面板截面计算；自研「因子分析」与因子研究页同源（同一 factor_research 服务）；「因子分析（AlphaLens）」调用 alphalens-reloaded；两个分析节点均可「显示分析结果」弹出报告"。

Line 33 回测节点 → 策略回测 module: unique bits: 默认成本参数（佣金 0.001/滑点 0.001/卖出印花税 0.0005，与回测接口、QUBE 一致）、输出指标列表（年化/波动/夏普/索提诺/卡玛/最大回撤/VaR/CVaR/胜率/盈亏比/月度收益 + 基准跟踪误差/信息比率）、逐仓风控仅多头、不推演挂单 assumptions。Line 15 already has 绩效指标 generally; the explicit metric list is detail worth keeping once. Put in 策略回测: "完整绩效输出（年化收益/波动/夏普/索提诺/卡玛/最大回撤/VaR/CVaR/胜率/盈亏比/月度收益；选基准时附跟踪误差/信息比率）" and "工作流回测节点与回测接口/QUBE 使用同一套默认成本（佣金 0.001 / 滑点 0.001 / 卖出印花税 0.0005）".

Line 40 QUBE details → QUBE module: backend/services/qube_agent.py、pi 链接、工具列表、事件流。Keep.

Line 41 → QUBE 独立 AI 配置 bullet (providers list → move to AI 辅助 module; QUBE keeps independence statement). Wait — where should the provider list live? AI 辅助 module says "供应商预置（免填 URL，对齐 models.dev）". The detailed list "OpenCode Zen/Go、DeepSeek、Zhipu/Z.AI（含 Coding Plan）、Kimi、Alibaba、Moonshot、MiniMax 等" — put in AI 辅助. QUBE bullet: "QUBE 的供应商/模型/推理强度/API Key/CLI 与「设置 → AI」完全独立，各存各的 .env 键；接入方式与 AI 辅助一致（预置/BYOK/本机 CLI）".

Also line 22 "推理强度可调" appears in AI 辅助 and line 41 — consolidated as above.

Also .env config section (134-139) mentions AI config and QUBE_* independence — that's config doc, fine, keep.

Now 注意事项 remaining items to keep as-is or lightly edited:
- xtquant Windows-only (176)
- 数据全部来自 QMT (177) — trim the 参考元数据 cross-ref? Keep short: "数据全部来自 QMT，不使用模拟数据；历史参考快照等研究元数据可经「数据管理 → 历史参考快照导入」补充". That's a pointer. OK keep short version.
- (178 deleted)
- 严谨性约定 block: keep items 180,181,182,185,187,188,189,192?,193; remove 183 (→数据探索), 184 (→策略回测), 186 (→因子研究), 190 (→数据管理), 191 (→因子研究/策略回测), 194 (→数据管理).
  Wait 192 (节点缓存随数据失效) — I said move to 工作流编辑器. Then 严谨性 keeps: 可交易掩码, 前向填充, 滚动IC无前视, 溯源 provenance, IC 口径, point-in-time, 默认股票池剔除指数, 面板 artifact.
- 195 访问安全 keep
- 196 执行加固 keep
- 197 复权存储 keep
- 198 空数据错误统一 keep
- 199 前端主题 keep
- 200 工程检查 keep

Renaming: I'll restructure 注意事项 into two sections: `## 严谨性约定` (methodology) and keep the rest under `## 注意事项`. Since 严谨性约定 was a sub-bullet of 注意事项 before, promoting it to its own section improves placement (it's a selling point). 

Also: the top intro (line 3) — fine.

Section order: 功能模块 → 自定义节点 → 技术栈 → 快速开始 → 项目结构 → 严谨性约定 → 注意事项 → License. Keep roughly current order (自定义节点 currently after QUBE section; since QUBE section dissolves into modules, 自定义节点 stays after 功能模块). 快速开始 before or after 技术栈? Current: 技术栈 then 快速开始. Keep. 严谨性约定/注意事项 after 项目结构, before License. Keep.

Hmm, one consideration: 功能模块 with 12 subsections each having 3-8 bullets will be ~120 lines. Total README maybe ~230 lines. Acceptable.

Wait, also I should double-check the 工作台 module: "每日研究简报：市场状态 + 研究数据就绪度（股票数/历史长度/参考快照/财务/分钟/QMT 连接，未达门槛明确提示「仅方法验证」）+ 因子池体检摘要 + 近 7 日除权事件 + 数据时效 + 最近批处理（/api/ops/briefing 实时聚合，15 分钟自动刷新）" — unique, keep.

And 数据管理 module: also "**主要宽基指数成分自动快照**（沪深300/中证500/中证1000/科创50/创业板指逐日积累 as-of 成分）" — unique. "**标的池快照（两融/沪深股通，仅作为市场结构参考，系统不用于做空/融资）**" — keep.

分钟因子 module details: "分钟缓存（1m/5m/15m/30m/60m）→ 自动清洗（竞价 bar 剔除、半日市/一字板标记）→ 分钟公式求值（m_* 字段 + ID_* 聚合 / M_* 序列算子 + 现成高频因子 TAIL_RET/OPEN_RET/RV/JUMP_DAY/AMIHUD5/VWAP_DEV/VOLUME_CLOCK/AUC_VOL_RATIO/LIMIT_UP_TIME/OVERNIGHT_RET/INTRADAY_RET）→ 自动折叠日频面板，下游全链路复用；时刻 IC 曲线（09:45~14:55 各时点采截面算 RankIC，回答「因子信息何时最强」）；回测 execute_at 执行时点（next_close=次日收盘成交 / 尾盘=信号日收盘成交 / next_open=次日开盘成交：新仓按开→收、存量持仓按收→收、卖出按隔夜收→开计收益）；因子库「日内高频」类别预置 14 个因子，批量扫描自动分流；工作流「因子构建（分钟）」节点" — all unique. Split into bullets; the execute_at detail could also live in 策略回测 (execute_at is a backtest param)... but it's introduced by 分钟因子. Keep in 分钟因子 with mention "回测支持 execute_at 执行时点". Fine.

策略回测 module also has "**参数敏感性**（网格扫描：佣金/滑点/印花税/止盈止损逐组合回测对比，验证策略稳健性）" — unique. "**容量分析**（...）" — unique.

OK. Also there's line 15 "**执行口径统一为 T 日信号 → T+1 收盘成交**（信号当日与建仓当日均不计收益，无前视）" — keep once in 策略回测; the 回测节点 details in line 33 restate it — removed via merge.

Also note line 15 "**仅普通股票多头**（normalize 固定为 long_only，负信号视为不买入，不融资/不融券/不做空；总仓位 ≤ 100% 为循环内硬约束——停牌/一字板冻结旧仓时买入按预算缩减，缩减天数见 leverage_summary/assumptions）" — the normalize/max_gross_exposure technical bits also appear in line 178 (deleted). Keep the technical detail in 策略回测 bullet: "`normalize` 固定 `long_only`、`max_gross_exposure` 上限 1.0（循环内硬约束）；负信号清零；停牌/一字板冻结旧仓时买入按预算缩减（缩减天数见 `leverage_summary`/assumptions）；调仓不成交不推演挂单（次数 assumptions 明示）".

Now let me also think: should I ask the user about the restructure approach? The task is clear enough ("优化放置位置和展现方式 + 修重复"), and I'm operating autonomously. Proceed.

Also, per instructions: for non-trivial implementation, EnterPlanMode is suggested... but this is a documentation refactor, fairly mechanical, and the user's ask is direct. The autonomous-operation note says proceed. I'll proceed without plan mode (docs-only change, reversible, on a fresh develop branch as user requested).

Let me now write the new README. I'll draft carefully.

Draft:

```markdown
# LocalQuant — 本地投研工作站

基于 QMT 数据接口的本地量化投研平台，以 ComfyUI 风格的节点化工作流为核心，集成数据探索、因子研究、策略回测、QUBE 策略 Agent、策略库与实验管理等功能。

> **投资边界（系统级约束）**：本平台只做**普通股票多头投资**——正信号按日归一为满仓组合，总仓位始终 ≤ 100%（回测循环内逐日强制执行的硬约束，停牌/一字板冻结旧仓时买入按预算缩减，任何情况下不越界）；负信号视为「不买入」。系统**不提供、也不允许**融资、融券、做空、多空对冲或任何形式的杠杆交易。`dollar_neutral` / 原始权重（`none`）模式已在回测引擎与 QUBE 工具层移除；因子研究中的「多空组合」仅是 Top 组减 Bottom 组的统计诊断，不代表可交易的空头持仓。

## 功能模块

### 工作流编辑器

iframe 内嵌官方 ComfyUI 前端，以节点画布搭建研究管线。

- **节点代码**：节点右键查看/编辑代码（Monaco + AI 改写 + ruff 内联诊断）；内置节点代码 fork 保护；所有代码编辑界面（节点代码/SQL/因子代码/新建节点）统一使用带「网页全屏」按钮的编辑器（Esc 退出）。
- **节点 UX**：仅数据型输入生成连线端口，普通参数只渲染控件；画布节点/节点面板/配置面板三处颜色统一取自 `frontend/src/lib/nodeColors.ts`；左侧面板悬停弹出节点说明卡（描述/示例/输入输出端口/注意事项），配置面板「节点说明」页展示同款文档；工作流日志支持按级别、按节点/全局筛选与时间排序。
- **运行产物**：节点完整输出落本地 pkl、运行记录只存预览，明细经 `/api/workflow/runs/{run_id}/nodes/{node_uuid}/output` 按需取用；运行产物长期保留，如需清理显式调用 `POST /api/workflow/runs/cleanup`（默认 `dry_run=true` 只统计，传 `dry_run=false` 才实际删除）。
- **节点缓存随数据失效**：节点级输出缓存键包含本地数据缓存版本（行情/参考数据最新 mtime + 文件数），重新下载/更新数据后自动失效，不会把旧数据的结果当成新结果。
- **因子链路**：因子构建（公式/代码/分钟）→ 因子标准化/中性化 → 因子分析（一站式）/ 因子分析（AlphaLens）/ IC 计算 / 分组收益 / 因子衰减，均基于 QMT 行情面板做**截面**计算。自研「因子分析」与因子研究页**同源**（同一套 factor_research 服务）；「因子分析（AlphaLens）」调用 alphalens-reloaded 产出行业分组 IC/分层收益等。两个分析节点均可在节点上点「显示分析结果」直接弹出报告。
- **市场环境节点**：`/api/regime/overview` 输出宽基趋势状态与风格轮动（见「数据探索」），供工作流内直接引用。

Hmm wait — I merged 市场环境 into 数据探索; do I need the extra pointer bullet in 工作流编辑器? Line 35's original context was "工作流编辑器中的节点设计细节 → 市场环境节点能力". The API serves the dashboard. If I put the full description in 数据探索 (dashboard + node), no pointer needed here. Drop this bullet. 

### 数据探索

全部基于本地 Parquet 缓存。

- **概览与查询**：数据概览、SQL 查询（AI 生成 SQL、结果解读、SQL 历史/收藏、字段字典/查询模板）、全市场扫描、横截面分析、异常检测。
- **市场环境仪表盘**（数据中心顶部）：宽基牛/震荡/熊判定（MA20/MA60/动量/HV20 联合）+ 小盘/成长/中盘 vs 大盘风格轮动（20 日相对强弱），基于本地指数日线缓存（`/api/regime/overview`）；工作流亦提供市场环境节点。
- **事件研究**：一字涨/跌停、放量、除权除息、手工事件 → 窗口 CAR/BHAR + t 值 + 正值占比；支持指定基准指数与市场模型 alpha/beta，附加按事件日聚类的稳健 t 值，并提供 calendar-time portfolio 月度时间序列检验；近邻事件自动合并防重复计数。窗口语义：`window_before/window_after` 为事件前/后天数（正数），相对日 = [-before, +after]（事件日=0）；窗口在面板边界截断时按实际存在的相对日对齐累计（不做越界/错位拼接），收益面板为前向填充口径。

### 因子研究

- **因子库**：卡片/列表双视图、IC 排序与筛选、点击查看公式（LaTeX + Python 代码）与全部指标、逐因子 AI 分析；IC 汇总/分层平均收益/单调性输出；内置量化算子库，公式可直接在公式节点运行。
- **因子编写**：公式/代码两种方式共用一套字段与量化算子；除量价外，研究/公式路径还注入基本面 fund_*（按公告日点位）、market_cap / turnover（需股本快照）、行业映射（供 INDUSTRY_NEUTRALIZE），并据快照现状动态标注可用性（无数据可取时求值明确报错而非静默给错值）。详见 [docs/因子编写指南.md](docs/因子编写指南.md)，因子库内可点「变量参考」查看。
- **批量扫描**：勾选类别/因子 → SSE 逐因子进度 → 按 IC/RankIC/ICIR 排序 → 入池；支持股票池分批扫描、内存保护、样本置信度警示与多重检验提示。
- **重算与快照**：预置因子重算/批量扫描结果采用**覆盖更新**语义（新指标写回原记录，不另存新因子），覆盖前旧值自动存入历史快照，可在因子详情「重算历史」中回溯。
- **指标来源**：外部抓取的参考指标标为 `external_ref`，本地 QMT 行情重算后标为 `local_recalc`；只有 `local_recalc` 且样本达到门槛（≥300 只、≥252 个交易日）的因子允许入因子池或进入组合回测。
- **因子体检**：基于 IC 历史快照的生命周期阶段（萌芽/稳定/观察/衰减/失效）+ IC 趋势徽标；**因子池拥挤度**：池内因子两两截面相关。
- **样本外验证**：walk-forward 滚动锚定分割（训练 [0,t) → 测试 [t, t+test) 逐折后移），每折 in-sample/OOS IC + 分层多空统计量，聚合 OOS IC 均值/t 值/同向一致性/衰减，防过拟合；因子研究页与工作流节点均提供（多空统计量仅为研究诊断，不代表可交易做空）。
- **因子池 → 组合回测闭环**：选因子 → 等权/滚动 IC 加权合成（样本外权重，无前视）→ 每日 Top-N 做多 → 回测 → 绩效 → 风格+行业归因一键打通；**组合 walk-forward 回测**：训练窗口定权重 → 测试窗口出信号 → 滚动拼接样本外净值，附全样本参考对比过拟合差距。
- **AlphaLens 分析**：行业分组 IC/分层收益/因子加权多空统计量/换手率，与自研综合报告互补。
- **因子面板导出**：`POST /api/factor/export-panel` 导出因子面板与前瞻收益 CSV，用于研究交付与离线复核。

### 分钟因子 · 日内高频

- **链路**：分钟缓存（1m/5m/15m/30m/60m）→ 自动清洗（竞价 bar 剔除、半日市/一字板标记）→ 分钟公式求值（`m_*` 字段 + `ID_*` 聚合 / `M_*` 序列算子）→ 自动折叠日频面板，下游全链路复用。
- **现成高频因子**：TAIL_RET / OPEN_RET / RV / JUMP_DAY / AMIHUD5 / VWAP_DEV / VOLUME_CLOCK / AUC_VOL_RATIO / LIMIT_UP_TIME / OVERNIGHT_RET / INTRADAY_RET；因子库「日内高频」类别预置 14 个因子，批量扫描自动分流。
- **时刻 IC 曲线**：09:45~14:55 各时点采截面算 RankIC，回答「因子信息何时最强」。
- **执行时点**：回测支持 `execute_at`（next_close=次日收盘成交 / 尾盘=信号日收盘成交 / next_open=次日开盘成交；新仓按开→收、存量持仓按收→收、卖出按隔夜收→开计收益）。
- **工作流**：提供「因子构建（分钟）」节点。

### 策略回测

工作流回测节点、回测接口与 QUBE 共用同一回测引擎；默认成本佣金 0.001 / 滑点 0.001 / 卖出印花税 0.0005 三处一致。

- **执行口径**：统一为 T 日信号 → T+1 收盘成交（信号当日与建仓当日均不计收益，无前视）；支持可选基准对比（如 `000300.SH`，附跟踪误差/信息比率）。
- **仅普通股票多头**（见顶部投资边界）：`normalize` 固定 `long_only`、`max_gross_exposure` 固定上限 1.0（循环内硬约束），负信号在引擎内清零；停牌/一字板冻结旧仓时买入按预算缩减（缩减天数见 `leverage_summary`/assumptions），调仓无法成交时不推演挂单（持仓保持，次数在 assumptions 明示）；逐仓风控（止盈/止损/移动止损）仅作用于多头持仓。
- **完整绩效**：净值/回撤曲线 + 年化收益/波动/夏普/索提诺/卡玛/最大回撤/VaR/CVaR/胜率/盈亏比/月度收益。
- **交易成本拆分**：佣金/滑点/印花税分列金额、占比与 bps/换手；**参数敏感性**：网格扫描（佣金/滑点/印花税/止盈止损逐组合回测对比）验证稳健性。
- **容量分析**：信号在参与率约束下可容纳的资金规模，逐档资金规模给出受限天数比例与理论容量上限；ADV 窗口可调，assumptions 明示 A 股整手/涨跌停/冲击成本等未模拟项。
- **退市强制清算**：数据提前截止的持仓按「末日价 ×(1-`delisting_loss`)」强制变现并释放权重（默认 0=全额变现的保守上界，不计交易费用），事件明细入 `delisting_events`、assumptions 明示；请配合「数据管理 → 退市/历史代码清单」维护退市代码，使退市整理期价格如实入账。
- **风格/行业归因**：回测记录页一键运行（回归法 `/api/risk/attribution-run`）——组合收益 ~ Σβ×风格因子收益 + alpha，行业因子按均值偏离编码，回答「超额来自风格、行业还是选股」。
- **记录导出**：回测记录可导出净值/日收益/交易明细/日志（`GET /api/backtest/runs/{id}/export?part=equity|returns|trades|log`）。

### QUBE 策略 Agent

- 多轮对话设计策略的 AI Agent：`backend/services/qube_agent.py` 是 [pi](https://github.com/earendil-works/pi) 的 pi-agent-core 架构 Python 移植——工具调用循环 + 事件流（delta / tool_call / tool_result / done）；内置工具 `read_doc`（读《因子编写指南》）、`preview_data`（看真实行情样本）、`run_backtest`（真实回测）、`save_strategy`（存策略库）。
- 系统提示词固定为普通股票多头约束（见顶部投资边界）：负信号视为不买入、总仓位 ≤ 100%，不得生成融资/融券/做空逻辑。
- 右侧策略工作台分屏：代码/回测/日志/版本 + AI 优化/自动优化。
- **独立 AI 配置**：QUBE 的供应商/模型/推理强度/API Key/CLI 与「设置 → AI」完全分开，各存各的 `.env` 键；接入方式与 AI 辅助一致（预置/BYOK/本机 CLI）。

### 策略库

- 工作中 / 已保存两态；QUBE 对话与工作流产出默认「工作中」，仅用户可手动设为「已保存」；策略代码版本历史可回滚。

### 实验管理

- 实验记录、多实验对比、研究日志；回测与工作流运行完成后自动创建实验记录并关联 source_id。

### 风险与组合分析

- **风格暴露**（Barra 精简）；**绩效补充指标**（alpha·beta / 上下行捕获 / Active Share）。
- **组合优化**：SLSQP 带约束（仅允许纯多头）。
- **压力测试**：含历史情景回放（2015 股灾 / 2018 熊市 / 2024 小微盘危机等真实窗口 × 当前权重）；**块自助蒙特卡洛**（保留自相关与波动聚集）。
- **组合事前风险预测**：风格+行业因子协方差 → 预测波动 + 因子风险贡献分解。
- 支持**从本地行情缓存加载面板**（股票池+区间，前复权）作为分析输入。

### 数据管理

- **下载与缓存**：QMT 数据下载、缓存管理、数据质量检查（仅检查行情文件并单列参考快照；含价格跳变/量能尖峰/疑似停牌退市披露）。
- **除权与复权**：最近除权事件清单（adjust_factor 跳变检测：股票/日期/比例）；复权存储口径见「注意事项」。
- **财务快照**：财务快照拉取（含 Cashflow 现金流表，供现金流/质量因子；字段按别名表归一）。
- **标的池与成分**：标的池快照（两融/沪深股通，仅作市场结构参考，系统不用于做空/融资）；主要宽基指数成分自动快照（沪深300/中证500/中证1000/科创50/创业板指逐日积累 as-of 成分）。
- **退市/历史代码清单**：维护退市代码（数据管理页 / `GET·POST /api/data/delisted`），全市场批量下载自动并入，消除幸存者偏差。
- **数据时效检查**：交易日历口径（QMT 日历优先、工作日近似兜底，长假不误报）；`GET /api/data/freshness` 输出最新交易日 + 显著滞后标的清单。
- **历史参考快照导入**：`POST /api/data/import-reference`——QMT 只能提供当前成分/名称/行业/两融池，2015 年沪深300 成分、历史上曾 ST 的名称等无法回溯；可从已核验来源整理历史快照（constituents/industry/instrument/margin，as-of 日期标注）导入，使指数成分重建、ST 逐日过滤、两融池逐日掩码覆盖历史区间。仅作研究元数据，不改变「行情唯一来自 QMT」与「只做普通多头」约束。

### 工作台

- 首页**每日研究简报**：市场状态 + 研究数据就绪度（股票数/历史长度/参考快照/财务/分钟/QMT 连接，未达门槛明确提示「仅方法验证」）+ 因子池体检摘要 + 近 7 日除权事件 + 数据时效 + 最近批处理（`/api/ops/briefing` 实时聚合，15 分钟自动刷新）。

### AI 辅助

- AI 能力贯穿各模块：节点代码改写（工作流）、自然语言生成工作流、数据探索 SQL 生成与结果解读、逐因子 AI 分析与因子分析建议（因子研究）。
- **接入方式**：供应商预置（免填 URL，对齐 [models.dev](https://models.dev)，含 OpenCode Zen/Go、DeepSeek、Zhipu/Z.AI（含 Coding Plan）、Kimi、Alibaba、Moonshot、MiniMax 等）/ 自定义 BYOK / 本机 CLI 工具（Claude Code/Codex/OpenCode/Pi 等）；模型下拉选择与推理强度可调。
```

Wait — "本机 CLI 工具（Claude Code/Codex/OpenCode/Pi 等）" — the CLI list was in line 41 (QUBE section). Moving the CLI list to AI 辅助 makes sense since 接入方式 is general. Good.

自定义节点 — keep as is.

技术栈 — keep as is.

快速开始 — keep, but the sandbox subsection: merge line 42's unique mechanism details here:

```markdown
### 代码执行沙箱（可选，推荐）

QUBE/回测的信号代码经 `backend/services/sandbox.py` 执行：优先在 OpenSandbox 容器中隔离（数据经文件 API 以 CSV 传入，不挂载卷，兼容 Windows），Docker/服务未就绪时自动降级为进程内执行并在日志/结果中标注；仅覆盖 `/api/backtest/run-strategy` 与 QUBE `run_backtest`，因子研究页与工作流因子节点保持原生执行。

启用隔离：客户端已随 `make install` 安装，先启动 Docker Desktop，再单开一个终端跑沙箱服务：

```bash
make sandbox-server   # 实质执行 uvx opensandbox-server
```

状态可查 `GET /api/system/sandbox`（实际探测 opensandbox-server，HTTP 健康探测 + TCP 兜底；`active=false` 即当前为进程内降级）。
```

And remove the QUBE 沙箱 bullet (42) — QUBE section no longer mentions sandbox; the sandbox section says "QUBE/回测的信号代码" which covers it.

环境要求 Docker line — keep.

项目结构 — keep.

严谨性约定 (new section from 注意事项 subset):

```markdown
## 严谨性约定

自研研究/回测路径默认启用：

- **可交易掩码**：因子 IC/分层的停牌/ST/次新股过滤在能取到量价面板的研究路径默认开启，避免无法成交的票污染截面；ST 状态与次新过滤均按**逐日 as-of** 判定（ST 从 instrument 快照日起生效，不把「现在的 ST」倒灌历史截面；次新股按「T 距上市日 < 20 天」逐日排除，而非按面板末日一刀切）。
- **收益率面板统一为前向填充口径**（`close.ffill().pct_change()`）：停牌/数据缺口期间收益为 0，复牌日的跳空涨跌如实入账——原始 `pct_change().fillna(0)` 会把停牌期间积累的跳空整段丢失，系统性低估波动与损失。
- **滚动 IC 加权无前视**：IC 合成权重用 IC 序列 shift(1) 后的滚动均值——`IC[T]` 需要 T+1 日收益才能算出，T 日不可得，直接滚动会把「即将赚到的收益」算进当日权重（1 日前视，组合虚高）。
- **IC 口径**：IC 标准差统一为样本标准差（ddof=1）；单调性只奖励单调递增方向；多因子合成先横截面去均值再 z-score；IC 衰减与 IC 汇总表同口径（T→T+p 复利收益）。
- **Point-in-time**：基本面/股本/行业等参考数据均按公告日生效；`as_of` 早于任何行业快照时返回空而非未来行业，杜绝前视；市值/换手率按公告日口径。
- **默认股票池剔除指数缓存**：宽基指数（000xxx.SH / 399xxx.SZ / 899xxx.BJ）只用于市场环境与指数行情，不会混入因子 IC/分层、批量扫描、组合回测、事件研究或 QUBE 回测的默认股票池；显式传入的股票池仍原样生效。
- **全量溯源**：所有回测/因子研究的参数、样本与指标均写溯源记录（`provenance` 表，/api/data 下可查），回测的口径（成本/风险字段/归一方式）一并记录，保证任意结果可复现。
- **全市场面板本地 artifact**：全 A 面板（5000~6000 只股票）不作为大 JSON 往返浏览器；`/api/factor/compute` 与 `/api/risk/panel` 将完整面板保存在 `data/outputs/panel_artifacts`（48 小时自动清理），前端只接收 token + 受限预览，分析接口按 token 读取完整数据。
- **复权存储**：...
- **空数据错误统一**：...
```

注意事项 (remaining):
```markdown
## 注意事项

- xtquant 仅支持 Windows，macOS 开发时 QMT 数据功能不可用
- 数据全部来自 QMT，不使用模拟数据；历史成分/名称/两融池等参考元数据可经「数据管理 → 历史参考快照导入」补充
- **访问安全**：...
- **执行加固**：...
- 前端采用 OpenCode 浅色主题风格，frontend/DESIGN-opencode.ai.md
- 工程检查：...
```

Hmm wait, 复权存储 (197) and 空数据错误统一 (198) — are they 严谨性约定 or 注意事项? 复权存储 is a storage convention = 严谨性-ish. 空数据错误统一 is API behavior design. Both fine in 严谨性约定 honestly, but the original had them as top-level 注意事项 bullets. I'll keep them top-level in 注意事项 to avoid over-promoting. Actually "严谨性约定" = rigor conventions about research correctness. 复权存储 affects factor correctness across除权 — it IS a rigor item. But fine either way. Decision: put 复权存储 in 严谨性约定 (it prevents a subtle correctness issue), 空数据错误统一 in 注意事项. Hmm, the original also had 交易边界 which I delete. And 数据来源 line 177.

Actually, let me keep it simpler and truer to original grouping: 注意事项 keeps everything not moved into modules, in original bullet order:
- xtquant Windows
- 数据来源 QMT (trimmed)
- 严谨性约定 (promoted sub-list with the research-correctness items)
- 访问安全
- 执行加固
- 复权存储
- 空数据错误统一
- 前端主题
- 工程检查

If I promote 严谨性约定 to its own `##` section, then order: `## 严谨性约定` then `## 注意事项` (rest). That's clean. Let me do that.

Wait, also double check line 184's "请用「退市/历史代码清单」...并在批量下载时自动并入" — merged into 策略回测 退市强制清算 bullet + 数据管理 退市清单 bullet. Good.

Line 191 导出 — split: 因子面板导出 → 因子研究; 回测记录导出 → 策略回测. Good.

Line 183 事件研究窗口语义 → 数据探索 事件研究 bullet. Good.

Line 186 指标来源 → 因子研究. Good.

Line 190 历史参考快照导入 → 数据管理. Good.

Line 194 数据时效 → 数据管理. Good.

Line 192 节点缓存随数据失效 → 工作流编辑器. Good.

Line 35 市场环境 → 数据探索. Good.

Now, also confirm nothing else in 注意事项 line 177: "数据全部来自 QMT，不使用模拟数据（行情来源唯一；历史成分/名称/两融池等**参考元数据**可通过「历史快照导入」补充，见下）" — I'll trim "见下" → "（见功能模块 → 数据管理）" or just "可经「数据管理 → 历史参考快照导入」补充". Good.

One more: line 5 callout mentions "因子研究中的「多空组合」仅是 Top 组减 Bottom 组的统计诊断" — and 因子研究样本外验证 bullet says "多空统计量仅为研究诊断，不代表可交易做空" — mild reinforcement, fine (callout is authoritative statement; bullet is contextual). Keep.

Also line 15 "支持可选基准对比（如 000300.SH）" and line 33 "支持可选基准对比（跟踪误差/信息比率）" → merged: "支持可选基准对比（如 `000300.SH`，附跟踪误差/信息比率）" once in 策略回测. Good.

Let me also double check 功能模块 intro line 3 — fine as is.

Also the "工作流编辑器" module's first line: original line 11 mentions "节点右键查看/编辑代码（Monaco + AI 改写 + ruff 诊断）、因子分析节点「显示分析结果」直接弹出综合报告、内置节点代码 fork 保护、底部本机性能监控" — I need to keep "因子分析节点「显示分析结果」直接弹出综合报告" (it's in my 因子链路 bullet: "两个分析节点均可在节点上点「显示分析结果」直接弹出报告" ✓) and "底部本机性能监控" — I need to add that. Put in 节点 UX bullet or its own: add to first bullet group: "底部本机性能监控". I'll add a bullet: "- **性能监控**：底部实时展示本机性能。" Actually just append to 节点 UX bullet.

Also line 11: "iframe 内嵌官方 ComfyUI 前端，搭建研究管线" — my intro line covers.

OK. Also check: did I keep "（与回测接口、QUBE 一致）" for default costs — yes ("三处一致").

Now line count estimate — fine.

Also, should the module order change? Current order: 工作流编辑器, 数据探索, 因子研究, 分钟因子, 策略回测, QUBE, 策略库, 实验管理, 风险与组合分析, 数据管理, 工作台, AI 辅助. That follows the research pipeline roughly. Keep.

One question: use `###` under `## 功能模块` — the original had a table under `## 功能模块`. New: intro sentence + subsections. Good.

Also: I should preserve the exact phrase "多空仅为研究诊断，不代表可交易做空" nuances. ✓.

Also the 技术栈 section mentions "自研 factor_research（IC/分层/衰减等，与工作流因子节点同源）" — that's a restatement of the 同源 point but in tech-stack inventory context; acceptable (one is feature, one is stack inventory). Keep.

Also line 42's "GET /api/system/sandbox 会实际探测 opensandbox-server（HTTP 健康探测 + TCP 兜底），不再把「包已安装/配置已开启」显示为「隔离已就绪」" — the "不再把..." part is a changelog-ish note; merge as "（实际探测 opensandbox-server：HTTP 健康探测 + TCP 兜底，而非仅看包安装/配置开关）". Good.

Now also, per the delivery protocol, after editing I should consider a visual gate? This is a markdown file, not pptx/pdf/docx — judge is for rendered deliverables of those types. A README.md edit doesn't need the judge. I can do a quick self-check: verify markdown renders (lint via rg for broken tables etc.). I'll do a quick sanity pass: check for leftover duplicated phrases with grep.

Plan of action:
1. ✅ develop branch created
2. Rewrite README.md
3. Grep for residual duplication (e.g., "T+1", "models.dev", "前向填充", "delisting", "import-reference", "freshness", "regime", "覆盖更新") to confirm single placement (or justified multi-context).
4. Commit on develop.

Wait — should I commit? The user asked to create the branch and fix the README. Committing on develop seems natural ("新开一个 develop 分支吧" implies work goes there). The git guidance says "Commit or push only when the user asks." The user asked for a new branch + README changes. Creating a branch without committing leaves changes floating between branches (uncommitted changes follow the working tree). Hmm — if I don't commit, the branch creation is meaningless. I think committing on develop is implied and appropriate here. I'll commit the README change on develop. Note: data/localquant.db is modified in the working tree — I must NOT include it in the commit (only README.md). 

Also: should I commit the branch creation itself (no changes)? Not needed; just commit README change on develop.

Let me now write the full new README.

One more consideration on 展现方式: within modules, use bold lead-ins + short bullets, keep `code` formatting for APIs. Also add a one-line description under each `###` heading where the original had one (e.g., 数据探索 "全部基于本地 Parquet 缓存").

Also: keep the docs link and NOTICE/License sections untouched.

Let me also double-check the 分钟因子 module: original says "分钟公式求值（m_* 字段 + ID_* 聚合 / M_* 序列算子 + 现成高频因子 ...）" — I split 现成高频因子 into its own bullet. And "因子库「日内高频」类别预置 14 个因子，批量扫描自动分流" — note the 现成高频因子 list has 11 items but 预置 14 个因子 — keep both facts as-is (the 14 includes more than the listed 现成 ones presumably). Keep verbatim facts.

Also "回测 execute_at 执行时点" — original: "回测 **execute_at 执行时点**（next_close=次日收盘成交 / 尾盘=信号日收盘成交 / next_open=次日开盘成交：新仓按开→收、存量持仓按收→收、卖出按隔夜收→开计收益）". Keep in 分钟因子 bullet (it's part of 分钟因子's capability). ✓

Writing now. I'll write the whole file with Write tool (full replacement). It's a big file; I have the original content in context, so Write is fine (I've read it).

Let me carefully compose the final document.

Also — keep header hierarchy: `##` for main sections, `###` for modules and 快速开始 subsections.

Also I want to add a tiny intro line under `## 功能模块` like "按研究流程组织；细节以小节列出。" Simple.

Final check on 注意事项 执行加固 bullet (196) — it mentions "「数据下载」节点仅允许 http(s)..." — keep verbatim.

访问安全 (195) keep verbatim.

复权存储 (197) keep verbatim.

空数据错误统一 (198) keep verbatim.

前端主题 (199), 工程检查 (200) keep verbatim.

Let me write it.

Actually one more dedup scan on my draft:
- "QMT 行情面板截面计算" appears in 因子链路 bullet only. ✓
- "alphalens-reloaded" appears in 工作流因子链路 bullet + 技术栈 + AlphaLens 分析 bullet in 因子研究. Three mentions: 因子研究 bullet describes the 页面 AlphaLens 分析 (行业分组 IC/分层收益/因子加权多空统计量/换手率); 工作流链路 bullet describes the AlphaLens 节点. Hmm — the 因子研究页's "另备 AlphaLens 分析" (line 13) vs workflow's "因子分析（AlphaLens）" node (line 32). Are they the same feature? Line 13: "另备 **AlphaLens 分析**（行业分组 IC/分层收益/因子加权多空统计量/换手率）与自研综合报告互补" — this is in 因子研究 module (the page). Line 32: "「因子分析（AlphaLens）」调用 alphalens-reloaded 产出行业分组 IC/分层收益等。两个分析节点均可在节点上点「显示分析结果」" — workflow nodes. So the page has AlphaLens analysis and the workflow has an AlphaLens node — likely same underlying capability, two surfaces. To dedupe: in 工作流因子链路 bullet, just say "「因子分析（AlphaLens）」节点调用 alphalens-reloaded（口径见因子研究）" — or put the AlphaLens description once in 因子链路 bullet since it's workflow... Original line 13 put "AlphaLens 分析" in 因子研究 module. Keep description in 因子研究 bullet ("AlphaLens 分析：基于 alphalens-reloaded 的行业分组 IC/分层收益/因子加权多空统计量/换手率，与自研综合报告互补；因子研究页与工作流「因子分析（AlphaLens）」节点同 capability"). Hmm, actually simpler: keep 因子研究 bullet for the page feature; in the 工作流因子链路 bullet write "「因子分析（AlphaLens）」调用 alphalens-reloaded" without re-listing outputs ("产出行业分组 IC/分层收益等" → drop since listed in 因子研究). Good enough — minor.

- "factor_research 同源" appears in 工作流链路 bullet + 技术栈. Acceptable.

OK, also one thing: the original line 13 says "点击查看公式（LaTeX + Python 代码）与全部指标" — keep. "IC 排序与筛选" ✓.

Line 13 also: "**因子池拥挤度**（池内因子两两截面相关）" ✓ merged with 体检.

Ready to write. After writing, run a few greps to verify no accidental loss: check that key tokens exist in new file: leverage_summary, delisting_loss, delisted, import-reference, export-panel, export-file, freshness, regime/overview, attribution-run, execute_at, sandbox-server, provenance, ddof, adjust_factor, no_cached_data, panel_artifacts, comfyui-frontend-package==1.47.10, etc. Also check no leftover "见下" dangling refs.

Then commit: `git add README.md && git commit -m "docs: 重构 README 功能模块——表格改小节+去重"` with a Chinese message matching repo style (commits are in Chinese, e.g. "fix: ...", "chore: ..."). Use "docs: ..." prefix. Message: "docs: README 功能模块改为分节展现并消除重复描述".

Let me write the file now.

Also, keep the trailing blank lines/structure tidy. The original had some stray blank lines (171-173). I'll clean.

Compose final README:

---

# LocalQuant — 本地投研工作站

基于 QMT 数据接口的本地量化投研平台，以 ComfyUI 风格的节点化工作流为核心，集成数据探索、因子研究、策略回测、QUBE 策略 Agent、策略库与实验管理等功能。

> **投资边界（系统级约束）**：... (verbatim line 5)

## 功能模块

### 工作流编辑器

iframe 内嵌官方 ComfyUI 前端，以节点画布搭建研究管线。

- **节点代码**：节点右键查看/编辑代码（Monaco + AI 改写 + ruff 内联诊断），内置节点代码 fork 保护；所有代码编辑界面（节点代码 / SQL / 因子代码 / 新建节点）统一使用带「网页全屏」按钮的编辑器（`components/ui/CodeEditor`，Esc 退出）。
- **节点 UX**：仅数据型输入（DataFrame/dict 等，或标注「仅连线输入」的字段）生成连线端口，普通参数只在节点上渲染控件；画布节点 / 左侧节点面板 / 右侧配置面板三处颜色统一取自 `frontend/src/lib/nodeColors.ts`；左侧面板悬停节点弹出说明卡（描述 / 工作流示例 / 输入输出端口 / 注意事项），配置面板「节点说明」页展示同款文档；底部本机性能监控；工作流日志支持按级别、按节点 / 全局筛选与时间正序 / 倒序排序。
- **运行产物**：节点完整输出落本地 pkl、运行记录只存预览（明细经 `/api/workflow/runs/{run_id}/nodes/{node_uuid}/output` 按需取用）；运行产物长期保留，如需清理显式调用 `POST /api/workflow/runs/cleanup`（默认 `dry_run=true` 只统计，传 `dry_run=false` 才实际删除）。
- **节点缓存随数据失效**：节点级输出缓存键包含本地数据缓存版本（行情 / 参考数据最新 mtime + 文件数），重新下载 / 更新数据后自动失效，不会把旧数据的结果当成新结果。
- **因子链路**：因子构建（公式 / 代码 / 分钟）→ 因子标准化 / 中性化 → 因子分析（一站式）/ 因子分析（AlphaLens）/ IC 计算 / 分组收益 / 因子衰减，均基于 QMT 行情面板做**截面**计算；自研「因子分析」与因子研究页**同源**（同一套 factor_research 服务），「因子分析（AlphaLens）」调用 alphalens-reloaded；两个分析节点均可在节点上点「显示分析结果」直接弹出报告。因子库 Alpha 公式可直接粘贴到「因子构建（公式）」节点运行（节点按股票池 + 区间自取 QMT 行情，并输出 return_data 供 IC / 分组收益节点直连）。

### 数据探索

全部基于本地 Parquet 缓存。

- **概览与查询**：数据概览、SQL 查询（AI 生成 SQL、结果解读、SQL 历史 / 收藏、字段字典 / 查询模板）、全市场扫描、横截面分析、异常检测。
- **市场环境仪表盘**（数据中心顶部）：宽基牛 / 震荡 / 熊判定（MA20 / MA60 / 动量 / HV20 联合）+ 小盘 / 成长 / 中盘 vs 大盘风格轮动（20 日相对强弱），基于本地指数日线缓存（`/api/regime/overview`）；工作流亦提供市场环境节点。
- **事件研究**：一字涨 / 跌停、放量、除权除息、手工事件 → 窗口 CAR / BHAR + t 值 + 正值占比；支持指定基准指数与市场模型 alpha/beta，附加按事件日聚类的稳健 t 值，并提供 **calendar-time portfolio** 月度时间序列检验；近邻事件自动合并防重复计数。窗口语义：`window_before / window_after` 为事件前 / 后天数（正数），相对日 = [-before, +after]（事件日 = 0）；事件在面板边界导致窗口截断时按实际存在的相对日对齐累计（不做越界 / 错位拼接），收益面板为前向填充口径（见「严谨性约定」）。

### 因子研究

- **因子库**：卡片 / 列表双视图、IC 排序与筛选、点击查看公式（LaTeX + Python 代码）与全部指标、逐因子 AI 分析；IC 汇总 / 分层平均收益 / 单调性输出；内置量化算子库，公式可直接在公式节点运行。
- **因子编写**：公式 / 代码两种方式共用一套字段与量化算子；除量价外，研究 / 公式路径还注入 **基本面 fund_*（按公告日点位）、market_cap / turnover（需股本快照）、行业映射（供 INDUSTRY_NEUTRALIZE）**，并据快照现状动态标注可用性（无数据可取时求值会明确报错而非静默给错值）。详见 [docs/因子编写指南.md](docs/因子编写指南.md)，因子库内可点「变量参考」查看。
- **因子批量扫描**：勾选类别 / 因子 → SSE 逐因子进度 → 按 IC / RankIC / ICIR 排序 → 入池；支持股票池分批扫描、内存保护、样本置信度警示与**多重检验提示**。
- **重算与历史快照**：预置因子重算 / 批量扫描结果采用**覆盖更新**语义（新指标写回原记录，不另存新因子），覆盖前旧值自动存入历史快照，可在因子详情「重算历史」中回溯。
- **指标来源标注**：外部抓取的参考指标标为 `external_ref`，本地 QMT 行情重算后标为 `local_recalc`；只有 `local_recalc` 且样本达到门槛（≥300 只、≥252 个交易日）的因子允许入因子池或进入组合回测。
- **因子体检**：基于 IC 历史快照的生命周期阶段（萌芽 / 稳定 / 观察 / 衰减 / 失效）+ IC 趋势徽标；**因子池拥挤度**：池内因子两两截面相关。
- **样本外验证**：walk-forward 滚动锚定分割（训练 [0,t) → 测试 [t, t+test) 逐折后移），输出每折 in-sample IC 与 OOS IC / 分层多空统计量，聚合 OOS IC 均值 / t 值 / 同向一致性 / 衰减，防过拟合；因子研究页与工作流节点均提供（多空仅为研究诊断，不代表可交易做空）。
- **因子池 → 组合回测闭环**：选因子 → 等权 / 滚动 IC 加权合成（样本外权重，无前视）→ 每日 Top-N 做多 → 回测 → 绩效 → 风格 + 行业归因一键打通；**组合 walk-forward 回测**：训练窗口定权重 → 测试窗口出信号 → 滚动拼接样本外净值，附全样本参考对比过拟合差距。
- **AlphaLens 分析**：基于 alphalens-reloaded 的行业分组 IC / 分层收益 / 因子加权多空统计量 / 换手率，与自研综合报告互补。
- **因子面板导出 CSV**：`POST /api/factor/export-panel`（前瞻收益一并导出），用于研究交付与离线复核。

### 分钟因子 · 日内高频

- **链路**：分钟缓存（1m/5m/15m/30m/60m）→ 自动清洗（竞价 bar 剔除、半日市 / 一字板标记）→ 分钟公式求值（`m_*` 字段 + `ID_*` 聚合 / `M_*` 序列算子）→ 自动折叠日频面板，下游全链路复用。
- **现成高频因子**：TAIL_RET / OPEN_RET / RV / JUMP_DAY / AMIHUD5 / VWAP_DEV / VOLUME_CLOCK / AUC_VOL_RATIO / LIMIT_UP_TIME / OVERNIGHT_RET / INTRADAY_RET；因子库「日内高频」类别预置 14 个因子，批量扫描自动分流；工作流提供「因子构建（分钟）」节点。
- **时刻 IC 曲线**：09:45~14:55 各时点采截面算 RankIC，回答「因子信息何时最强」。
- **执行时点**：回测 `execute_at`（next_close=次日收盘成交 / 尾盘=信号日收盘成交 / next_open=次日开盘成交；新仓按开→收、存量持仓按收→收、卖出按隔夜收→开计收益）。

### 策略回测

工作流回测节点、回测接口与 QUBE 共用同一套回测引擎与默认成本（佣金率 0.001 / 滑点 0.001 / 卖出印花税 0.0005）。

- **执行口径**：统一为 T 日信号 → T+1 收盘成交（信号当日与建仓当日均不计收益，无前视）；支持可选基准对比（如 `000300.SH`，附跟踪误差 / 信息比率）。
- **仅普通股票多头**（见顶部投资边界）：`normalize` 固定 `long_only`、`max_gross_exposure` 固定上限 1.0，负信号在回测引擎内清零；总仓位 ≤ 100% 为循环内硬约束——停牌 / 一字板冻结旧仓时买入按预算缩减（缩减天数见 `leverage_summary` / assumptions），调仓无法成交时不推演挂单（持仓保持，次数在 assumptions 明示）；逐仓风控（止盈 / 止损 / 移动止损）仅作用于多头持仓。
- **完整绩效**：净值 / 回撤曲线，年化收益 / 波动 / 夏普 / 索提诺 / 卡玛 / 最大回撤 / VaR / CVaR / 胜率 / 盈亏比 / 月度收益。
- **交易成本拆分**：佣金 / 滑点 / 印花税分列金额、占比与 bps / 换手；**参数敏感性**：网格扫描（佣金 / 滑点 / 印花税 / 止盈止损逐组合回测对比）验证策略稳健性。
- **容量分析**：信号在参与率约束下可容纳的资金规模，逐档资金规模给出受限天数比例与理论容量上限；ADV 窗口可调，assumptions 明示 A 股整手 / 涨跌停 / 冲击成本等未模拟项。
- **退市强制清算**：数据提前截止的持仓按「末日价 ×(1-`delisting_loss`)」强制变现并释放权重（默认 0=全额变现的保守上界，不计交易费用），事件明细入 `delisting_events`、assumptions 明示；请配合「数据管理 → 退市 / 历史代码清单」维护退市代码并在批量下载时自动并入，使退市整理期价格如实入账。
- **停牌收益口径**：收益率面板为前向填充口径——停牌 / 缺口期间收益为 0，复牌跳空涨跌如实入账（详见「严谨性约定」）。
- **风格 / 行业归因**：回测记录页一键运行（回归法，`/api/risk/attribution-run`）——组合收益 ~ Σ β×风格因子收益 + alpha，行业因子按均值偏离编码，回答「策略赚的钱来自哪种风格、超额来自行业还是选股、剩的是不是纯 alpha」。
- **记录导出**：回测记录可导出净值 / 日收益 / 交易明细 / 日志（`GET /api/backtest/runs/{id}/export?part=equity|returns|trades|log`）。

### QUBE 策略 Agent

- 多轮对话设计策略的 AI Agent：`backend/services/qube_agent.py` 是 [pi](https://github.com/earendil-works/pi) 的 pi-agent-core 架构 Python 移植——工具调用循环 + 事件流（delta / tool_call / tool_result / done）；内置工具 `read_doc`（读《因子编写指南》）、`preview_data`（看真实行情样本）、`run_backtest`（真实回测）、`save_strategy`（存策略库）。
- 系统提示词固定为普通股票多头约束（见顶部投资边界）：负信号视为不买入、总仓位 ≤ 100%，不得生成融资 / 融券 / 做空逻辑。
- 右侧策略工作台分屏：代码 / 回测 / 日志 / 版本 + AI 优化 / 自动优化。
- **独立 AI 配置**：QUBE 的供应商 / 模型 / 推理强度 / API Key / CLI 与「设置 → AI」完全分开，各存各的 `.env` 键；接入方式与「AI 辅助」一致。

### 策略库

- 工作中 / 已保存两态；QUBE 对话与工作流产出默认「工作中」，仅用户可手动设为「已保存」；策略代码版本历史可回滚。

### 实验管理

- 实验记录、多实验对比、研究日志；回测与工作流运行完成后自动创建实验记录并关联 source_id。

### 风险与组合分析

- **风格暴露**（Barra 精简）；**绩效补充指标**（alpha·beta / 上下行捕获 / Active Share）。
- **组合优化**：SLSQP 带约束，仅允许纯多头。
- **压力测试**：含**历史情景回放**（2015 股灾 / 2018 熊市 / 2024 小微盘危机等真实窗口 × 当前权重）；**块自助蒙特卡洛**（保留自相关与波动聚集）。
- **组合事前风险预测**：风格 + 行业因子协方差 → 预测波动 + 因子风险贡献分解。
- 支持**从本地行情缓存加载面板**（股票池 + 区间，前复权）作为分析输入。

### 数据管理

- **下载与缓存**：QMT 数据下载、缓存管理、数据质量检查（仅检查行情文件并单列参考快照；含价格跳变 / 量能尖峰 / 疑似停牌退市披露）。
- **除权事件**：最近除权事件清单（`adjust_factor` 跳变检测：股票 / 日期 / 比例）。
- **财务快照**：财务快照拉取（含 **Cashflow 现金流表**，供现金流 / 质量因子；字段按别名表归一）。
- **标的池与指数成分**：标的池快照（两融 / 沪深股通，仅作为市场结构参考，系统不用于做空 / 融资）；主要宽基指数成分自动快照（沪深300 / 中证500 / 中证1000 / 科创50 / 创业板指逐日积累 as-of 成分）。
- **退市 / 历史代码清单**：维护退市代码（数据管理页 / `GET·POST /api/data/delisted`），全市场批量下载自动并入，消除幸存者偏差。
- **数据时效检查**：交易日历口径（QMT 日历优先、工作日近似兜底，长假不误报）；`GET /api/data/freshness` 输出最新交易日 + 显著滞后标的清单。
- **历史参考快照导入**（`POST /api/data/import-reference`）：QMT 只能提供当前成分 / 名称 / 行业 / 两融池，2015 年沪深300 成分、历史上曾 ST 的名称等无法回溯；可从已核验来源整理历史快照（constituents / industry / instrument / margin，as-of 日期标注）导入，使指数成分重建、ST 逐日过滤、两融池逐日掩码覆盖历史区间——仅作研究元数据，不改变「行情唯一来自 QMT」与「只做普通多头」约束。

### 工作台

- 首页**每日研究简报**：市场状态 + **研究数据就绪度**（股票数 / 历史长度 / 参考快照 / 财务 / 分钟 / QMT 连接，未达门槛明确提示「仅方法验证」）+ 因子池体检摘要 + 近 7 日除权事件 + 数据时效 + 最近批处理（`/api/ops/briefing` 实时聚合，15 分钟自动刷新）。

### AI 辅助

- AI 能力贯穿各模块：节点代码改写（工作流）、自然语言生成工作流、数据探索 SQL 生成与结果解读、因子分析建议（因子研究）。
- **接入方式**：供应商预置（免填 URL，对齐 [models.dev](https://models.dev)，含 OpenCode Zen/Go、DeepSeek、Zhipu/Z.AI（含 Coding Plan）、Kimi、Alibaba、Moonshot、MiniMax 等）/ 自定义 BYOK / 本机 CLI 工具（Claude Code / Codex / OpenCode / Pi 等）；模型下拉选择与推理强度可调。

## 自定义节点

(verbatim 44-67)

## 技术栈

(verbatim 69-79)

## 快速开始

### 环境要求 (verbatim 83-89)

### 安装 (verbatim 91-99)

### 启动 (verbatim 101-112)

### 代码执行沙箱（可选，推荐）

QUBE / 回测的信号代码经 `backend/services/sandbox.py` 执行：优先在 OpenSandbox 容器中隔离（数据经文件 API 以 CSV 传入，不挂载卷，兼容 Windows），Docker / 沙箱服务未就绪时自动降级为进程内执行（无容器隔离，日志 / 回测结果会标注）；仅覆盖 `/api/backtest/run-strategy` 与 QUBE `run_backtest`，因子研究页与工作流因子节点保持原生执行。

客户端已随 `make install` 安装。要真正启用隔离，先启动 Docker Desktop，再单开一个终端跑沙箱服务：

```bash
make sandbox-server   # 实质执行 uvx opensandbox-server
```

状态可查 `GET /api/system/sandbox`：实际探测 opensandbox-server（HTTP 健康探测 + TCP 兜底，而非仅看包安装 / 配置开关），`active=false` 即当前为进程内降级。

### 配置 (verbatim 126-139)

## 项目结构 (verbatim 141-170)

## 严谨性约定

自研研究 / 回测路径默认启用：

- **可交易掩码**：因子 IC / 分层的「可交易掩码」（停牌 / ST / 次新股过滤）在能取到量价面板的研究路径默认**开启**，避免无法成交的票污染截面；ST 状态与次新过滤均按**逐日 as-of** 判定（ST 从 instrument 快照日起生效，不把「现在的 ST」倒灌历史截面；次新股按「T 距上市日 < 20 天」逐日排除，而非按面板末日一刀切）。
- **收益率面板统一为前向填充口径**（`close.ffill().pct_change()`）：停牌 / 数据缺口期间收益为 0，**复牌日的跳空涨跌如实入账**——原始 `pct_change().fillna(0)` 会把停牌期间积累的跳空整段丢失，系统性低估波动与损失。
- **滚动 IC 加权无前视**：IC 合成权重用 IC 序列 **shift(1) 后**的滚动均值——`IC[T]` 需要 T+1 日收益才能算出，T 日不可得，直接滚动会把「即将赚到的收益」算进当日权重（1 日前视，组合虚高）。
- **IC 口径**：IC 标准差统一为**样本标准差（ddof=1）**；单调性只奖励单调递增方向；多因子合成先横截面去均值再 z-score；IC 衰减与 IC 汇总表**同口径**（T→T+p 复利收益）。
- **Point-in-time**：基本面 / 股本 / 行业等参考数据均按**公告日(point-in-time)**生效；`as_of` 早于任何行业快照时返回空而非未来行业，杜绝前视；市值 / 换手率按公告日口径。
- **默认股票池剔除指数缓存**：宽基指数（000xxx.SH / 399xxx.SZ / 899xxx.BJ）只用于市场环境与指数行情，不会混入因子 IC / 分层、批量扫描、组合回测、事件研究或 QUBE 回测的默认股票池；显式传入的股票池仍原样生效。
- **全量溯源**：所有回测 / 因子研究的**参数、样本与指标均写溯源记录**（`provenance` 表，/api/data 下可查），回测的口径（成本 / 风险字段 / 归一方式）也一并记录，保证任意结果可复现。
- **全市场面板本地 artifact**：全 A 面板（5000~6000 只股票）不再作为大 JSON 往返浏览器；`/api/factor/compute` 与 `/api/risk/panel` 将完整面板保存在 `data/outputs/panel_artifacts`（48 小时自动清理），前端只接收 token + 受限预览，分析接口按 token 读取完整数据。
- **复权存储**：缓存为**不复权价 + `adjust_factor` 列**（由后复权价反推，锚定上市日——新增除权事件不改变历史因子值，增量缓存自洽）；因子 / 回测 / 研究读取默认按**前复权**换算（`raw × factor / 最新 factor`），跨除权追更后历史价格全局一致，不再需要重下历史区间。旧版前复权缓存（无 `adjust_factor` 列）qfq 读取透明兼容，下载时自动重建；SQL 探索看到的为原始价 + adjust_factor 列（前复权 = close × adjust_factor / 最新 adjust_factor）。

Hmm wait — I put 复权存储 both in 严谨性约定... earlier I debated. Fine, 严谨性约定 it is.

## 注意事项

- xtquant 仅支持 Windows，macOS 开发时 QMT 数据功能不可用
- 数据全部来自 QMT，不使用模拟数据（行情来源唯一；历史成分 / 名称 / 两融池等**参考元数据**可经「数据管理 → 历史参考快照导入」补充）
- **访问安全**：默认仅绑定 `127.0.0.1`...（verbatim）
- **执行加固**：（verbatim 196）
- **空数据错误统一**：（verbatim 198）
- 前端采用 OpenCode 浅色主题风格，frontend/DESIGN-opencode.ai.md
- 工程检查：（verbatim 200）

## License (verbatim)

---

Wait, I dropped "**停牌收益口径**" duplicate in 策略回测 — I earlier decided to keep a pointer. I included it as a bullet "停牌收益口径：收益率面板为前向填充口径——停牌 / 缺口期间收益为 0，复牌跳空涨跌如实入账（详见「严谨性约定」）". Hmm, that IS nearly verbatim duplication of the 严谨性 bullet. The user explicitly wants duplication fixed. The 严谨性 bullet is one section away. I'll drop this bullet from 策略回测 entirely — the 严谨性约定 covers it globally (it even says 收益率面板统一, which applies to 回测). OK drop.

But wait, original line 15 had "**复牌跳空收益**（收益率前向填充口径，停牌损失如实入账）" as a backtest feature. Removing it from 回测 loses discoverability but removes duplication. The 严谨性约定 item explicitly covers "复牌日的跳空涨跌如实入账". I'll drop the 回测 bullet. Good.

Also check 策略回测 intro: "工作流回测节点、回测接口与 QUBE 共用同一套回测引擎与默认成本（佣金率 0.001 / 滑点 0.001 / 卖出印花税 0.0005）" — original line 33 said 回测节点默认成本 "与回测接口、QUBE 一致". ✓.

Also double check I kept "向量化回测" from line 15 — original line 15 starts "向量化回测、绩效指标、净值/回撤曲线（工作流回测节点 + QUBE 策略工作台）". My draft: intro says 共用引擎; 完整绩效 bullet has 净值/回撤曲线 + metrics. Add "向量化回测" to intro: "向量化回测引擎，工作流回测节点、回测接口与 QUBE 共用同一套实现与默认成本（...）". ✓

Also "支持可选基准对比" ✓.

Now the 数据探索 module lost "全部基于本地 Parquet 缓存" placement — original line 12 says all exploration features are based on local Parquet cache. ✓ kept as intro line.

AI 辅助 bullet: "因子分析建议（因子研究）" — original had both "逐因子 AI 分析" (line 13) and "因子分析建议" (line 22). These might be the same feature (per-factor AI analysis = AI 因子分析建议). I merged as "逐因子 AI 分析与建议（因子研究）". Fine.

Also: "自然语言生成工作流" — unique ✓.

One more scan of original for anything I haven't placed:

Line 11: "iframe 内嵌官方 ComfyUI 前端" ✓; "搭建研究管线" ✓; "节点右键查看/编辑代码（Monaco + AI 改写 + ruff 诊断）" ✓; "因子分析节点「显示分析结果」直接弹出综合报告" ✓ (因子链路 bullet); "内置节点代码 fork 保护" ✓; "底部本机性能监控" ✓; "节点完整输出落本地 pkl、运行记录只存预览（/api/... 按需取明细）" ✓; "运行产物长期保留；如需清理，显式调用 POST /api/workflow/runs/cleanup（默认 dry_run=true 只统计，传 dry_run=false 才实际删除）" ✓.

Line 12: "数据概览" ✓; "SQL 查询（含 AI 生成 SQL、结果解读、SQL 历史/收藏与字段字典/查询模板）" ✓; "全市场扫描" ✓; "横截面分析" ✓; "异常检测" ✓; "全部基于本地 Parquet 缓存" ✓; "市场环境仪表盘（宽基牛/震荡/熊判定 + 小盘/成长/中盘 vs 大盘风格轮动，数据中心顶部）" ✓; "事件研究（...）" ✓.

Line 13: all ✓ (因子库双视图/IC 排序筛选/公式查看/逐因子 AI 分析/IC 汇总分层单调性/算子库/批量扫描/体检/拥挤度/样本外验证/闭环/组合 walk-forward/AlphaLens/面板导出).

Line 14: all ✓.

Line 15: "向量化回测、绩效指标、净值/回撤曲线" ✓; "执行口径 T+1" ✓; "仅普通股票多头 + normalize + leverage_summary" ✓; "可选基准对比" ✓; "交易成本拆分" ✓; "容量分析" ✓; "回测风格归因" ✓; "参数敏感性" ✓; "退市强制清算" ✓; "复牌跳空收益" → covered in 严谨性约定 ✓ (dropped as dup).

Line 16: QUBE ✓ (多轮对话/工具循环/工作台分屏/配置独立).

Line 17: 策略库 ✓.

Line 18: 实验管理 ✓.

Line 19: 风格暴露 ✓; 组合优化 ✓; 绩效补充 ✓; 压力测试+历史情景 ✓; 事前风险预测 ✓; 回测归因含行业因子 → moved to 策略回测 ✓; 组合优化仅纯多头 ✓; 块自助蒙特卡洛 ✓; 本地行情缓存加载面板 ✓; 回测记录风格归因 attribution-run → 策略回测 ✓.

Line 20: all ✓ (下载/缓存管理/质量检查/除权清单/财务快照 Cashflow/标的池两融/宽基成分/数据时效/退市清单/历史快照导入).

Line 21: 工作台 ✓.

Line 22: AI 辅助 ✓ (节点代码改写/NL 生成工作流/SQL/因子建议/供应商预置/BYOK/CLI/模型下拉/推理强度).

Lines 26-36 node details: 端口 ✓, 颜色 ✓, 说明卡 ✓, 代码编辑器 ✓, 因子重算 ✓ (因子研究), 因子编写 ✓ (因子研究), 因子链路 ✓, 回测节点 ✓ (策略回测), 样本外验证节点 ✓ (因子研究), 市场环境节点 ✓ (数据探索), 日志 ✓.

Lines 40-42: QUBE ✓, 独立 AI 配置 ✓, 沙箱 ✓ (快速开始).

Everything placed. 

Now write the file. Also final formatting: the original uses "、" and "/" spacing inconsistently; I'll use "/" with spaces like my draft — hmm, original style is dense "两融/沪深股通" without spaces. To minimize diff noise and match repo style, maybe keep original punctuation style (no spaces around /). The original README uses e.g. "佣金/滑点/印花税" without spaces. I'll keep original strings as much as possible verbatim rather than reformatting every slash. That also reduces risk of unintended meaning drift. Let me use original phrasing verbatim wherever possible, only restructuring into bullets.

Revised approach: reuse original text blocks verbatim inside bullets. E.g.:

- **交易成本拆分**（佣金/滑点/印花税分列金额、占比与 bps/换手）；**参数敏感性**（网格扫描：佣金/滑点/印花税/止盈止损逐组合回测对比，验证策略稳健性）

Keep the （） style. Good — verbatim preservation makes the diff cleaner and respects the author's voice.

Let me now produce the final file with original wording preserved as much as possible.

Structure of 功能模块 sections with original text:

### 工作流编辑器

iframe 内嵌官方 ComfyUI 前端，以节点画布搭建研究管线。

- **节点代码**：节点右键查看/编辑代码（Monaco + AI 改写 + ruff 诊断）；内置节点代码 fork 保护；所有代码编辑界面（节点代码、SQL、因子代码、新建节点）统一使用带「网页全屏」按钮的编辑器（`components/ui/CodeEditor`，Esc 退出）。
- **节点交互**：仅数据型输入（DataFrame/dict 等，或标注「仅连线输入」的字段）生成连线端口，普通参数只在节点上渲染控件；画布节点、左侧节点面板、右侧配置面板三处颜色统一取自 `frontend/src/lib/nodeColors.ts`，全局唯一；左侧面板悬停节点弹出说明卡（描述/工作流示例/输入输出端口/注意事项），拖入画布后点击节点，配置面板「节点说明」页展示同款文档；底部本机性能监控。
- **运行产物**：节点完整输出落本地 pkl、运行记录只存预览（`/api/workflow/runs/{run_id}/nodes/{node_uuid}/output` 按需取明细）；运行产物长期保留；如需清理，显式调用 `POST /api/workflow/runs/cleanup`（默认 dry_run=true 只统计，传 dry_run=false 才实际删除）。
- **节点缓存随数据失效**：节点级输出缓存键包含本地数据缓存版本（行情/参考数据最新 mtime + 文件数），重新下载/更新数据后自动失效，不会把旧数据的结果当成新结果。
- **工作流日志**：按级别、按节点 / 全局筛选，时间正序 / 倒序排序。
- **因子链路**：因子构建（公式/代码）→ 因子标准化/中性化 → 因子分析（一站式）/ 因子分析（AlphaLens）/ IC 计算 / 分组收益 / 因子衰减 均基于 QMT 行情面板做**截面**计算；自研「因子分析」与因子研究页**同源**（同一套 factor_research 服务），「因子分析（AlphaLens）」调用 alphalens-reloaded；两个分析节点均可在节点上点「显示分析结果」直接弹出报告。因子库 Alpha 公式可直接粘到「因子构建（公式）」节点运行（节点按股票池+区间自取 QMT 行情，并输出 return_data 供 IC/分组收益节点直连）。

Wait — 因子构建（分钟）should be in the chain too; the 分钟因子 module mentions the node. Chain bullet: "因子构建（公式/代码/分钟）". OK.

### 数据探索

全部功能基于本地 Parquet 缓存。

- **概览与查询**：数据概览、SQL 查询（含 AI 生成 SQL、结果解读、SQL 历史/收藏与字段字典/查询模板）、全市场扫描、横截面分析、异常检测。
- **市场环境仪表盘**（数据中心顶部）：宽基牛/震荡/熊判定（MA20/MA60/动量/HV20 联合）+ 小盘/成长/中盘 vs 大盘风格轮动（20 日相对强弱），基于本地指数日线缓存（`/api/regime/overview`）；工作流亦提供市场环境节点。
- **事件研究**：一字涨/跌停、放量、除权除息、手工事件 → 窗口 CAR/BHAR + t 值 + 正值占比；支持指定基准指数与市场模型 alpha/beta，附加按事件日聚类的稳健 t 值，并提供 **calendar-time portfolio** 月度时间序列检验；近邻事件自动合并防重复计数。窗口语义：`window_before/window_after` 为事件前/后天数（正数），相对日 = [-before, +after]（事件日=0）；事件在面板边界导致窗口截断时按实际存在的相对日对齐累计（不做越界/错位拼接），收益面板同样为前向填充口径。

### 因子研究

(as drafted, with original wording)

### 分钟因子 · 日内高频

(as drafted)

### 策略回测

向量化回测引擎，工作流回测节点、回测接口与 QUBE 策略工作台共用（默认成本一致：佣金率 0.001 / 滑点 0.001 / 卖出印花税 0.0005）。

- **执行口径**：统一为 T 日信号 → T+1 收盘成交（信号当日与建仓当日均不计收益，无前视）；支持可选基准对比（如 `000300.SH`，附跟踪误差/信息比率）。
- **仅普通股票多头**（见顶部投资边界）：`normalize` 固定为 `long_only`、`max_gross_exposure` 固定上限 1.0，负信号在回测引擎内清零；总仓位 ≤ 100% 为循环内硬约束——停牌/一字板冻结旧仓时买入按预算缩减，缩减天数见 `leverage_summary`/assumptions；停牌/一字板导致调仓无法成交时不推演挂单（持仓保持，次数在 assumptions 明示）；逐仓风控（止盈/止损/移动止损）仅作用于多头持仓。
- **完整绩效**：净值/回撤曲线与完整指标（年化收益/波动/夏普/索提诺/卡玛/最大回撤/VaR/CVaR/胜率/盈亏比/月度收益）。
- **交易成本拆分**（佣金/滑点/印花税分列金额、占比与 bps/换手）；**参数敏感性**：网格扫描（佣金/滑点/印花税/止盈止损逐组合回测对比，验证策略稳健性）。
- **容量分析**：信号在参与率约束下可容纳的资金规模，逐档资金规模给出受限天数比例与理论容量上限；ADV 窗口可调，assumptions 明示 A 股整手/涨跌停/冲击成本未模拟项。
- **退市强制清算**：数据提前截止的持仓按末日价 ×(1-`delisting_loss`) 强制变现并释放权重（默认 0=全额变现的保守上界，不计交易费用），事件明细入 `delisting_events`、assumptions 明示；请用「数据管理 → 退市/历史代码清单」维护退市代码并在批量下载时自动并入，使退市整理期价格如实入账。
- **风格/行业归因**：回测记录页一键运行（回归法，`/api/risk/attribution-run`）：组合收益 ~ Σ β×风格因子收益 + alpha，行业因子按均值偏离编码——回答「策略赚的钱来自哪种风格、超额来自行业还是选股、剩的是不是纯 alpha」。
- **记录导出**：回测记录可导出净值/日收益/交易明细/日志（`GET /api/backtest/runs/{id}/export?part=equity|returns|trades|log`）。

### QUBE 策略 Agent
### 策略库
### 实验管理
### 风险与组合分析
### 数据管理
### 工作台
### AI 辅助

(as drafted)

Then 自定义节点, 技术栈, 快速开始 (with merged sandbox subsection), 项目结构, 严谨性约定, 注意事项, License.

I think this is solid. Write it.

For the commit: repo commit style is "fix:", "chore:", "test:" in Chinese. Use: "docs: 重构 README——功能模块改为分节列表，合并重复描述". 

Let me write the file now. After that, verify with grep a few tokens and count lines, then commit only README.md.

Actually — one more check on 快速开始环境要求 line 89: "Docker Desktop（可选；Windows 用 WSL2 后端）——开启回测信号代码的容器隔离（OpenSandbox）；不装则自动降级为进程内执行" — slight overlap with sandbox subsection's degrade sentence. It's a one-line env requirement; keep as is (env list must mention Docker). Acceptable.

And 配置 section line 139 "SANDBOX_ENABLED / SANDBOX_IMAGE / SANDBOX_SERVER_DOMAIN — 代码执行沙箱" keep.

Writing now.

develop 分支已建好。我通读了 README，问题很明确：**功能模块是一张 13 行的大表格，单元格动辄三四百字，完全没法扫读**；「工作流编辑器节点设计细节」「QUBE 与沙箱」「注意事项」三节里又散落着大量与表格重复的功能描述（投资边界/多头约束重复了 5 处、T+1 成交口径 2 处、退市清算 2 处、历史快照导入 2 处、沙箱 2 处、市场环境 2 处等）。

我的重构方案：把大表格拆成按模块的小节 + 短列表（功能描述归位到所属模块），把散落在「节点细节/注意事项」里的重复描述合并进对应模块，每个事实只保留一处。现在重写 README：

### **Assistant**
Now verify: check that key facts survive (grep tokens), and check for residual duplication. Let me grep for key API paths and terms to confirm single placement, then commit only README.md.

重写完成。现在做一遍完整性校验：确认关键事实（API 路径、参数名）没有丢失，且重复描述已收敛到唯一位置。

### **Assistant**
Almost all single. A few notes:

1. `export-file` = 0 — original line 191 mentioned `GET /api/factor/export-file/{token}`. I dropped it! Let me check: original said "（`POST /api/factor/export-panel` → `GET /api/factor/export-file/{token}`）". My 因子研究 bullet only has POST /api/factor/export-panel. I should restore the export-file GET mention. Let me add it back.

2. `sandbox-server` = 2 — one in 快速开始 code block, one in... let me check. "make sandbox-server   # 实质执行 uvx opensandbox-server" — the comment contains "opensandbox-server" which matches "sandbox-server" grep. So actually it's one feature mention + the opensandbox-server probe. Fine.

3. `adjust_factor` = 2 — one in 数据管理 除权事件, one in 复权存储 (严谨性约定). Both legitimate (different facts). Original had more. Fine.

4. `models.dev` = 2 — AI 辅助 bullet + 技术栈. Acceptable (tech stack inventory).

5. `comfyui-frontend-package` = 2 — 技术栈 + License. Same as original. Fine.

6. `INDUSTRY_NEUTRALIZE` = 2 — 因子编写 bullet + 执行加固 (注意事项). Same as original (both legitimate, different contexts).

Let me fix the export-file omission. Also double-check: original line 191 "因子面板与前瞻收益可导出 CSV（POST /api/factor/export-panel → GET /api/factor/export-file/{token}）". Update the 因子研究 bullet to include the GET endpoint.

Also let me double check a couple more terms that were in the original: "外部参考值 / 本地 QMT 重算值" (line 13 指标来源 wording) — my bullet says external_ref/local_recalc with description; original also had "**指标来源**：外部参考值 / 本地 QMT 重算值" in 批量扫描. Covered semantically. OK.

Also "opencode 浅色主题" line 156 + line 199 both mention theme — same as original, fine.

Also check: original line 5 callout — kept verbatim ✓.

Fix export-file then commit.

校验结果良好，大部分关键事实都只出现一次。发现一处遗漏：原文的 `GET /api/factor/export-file/{token}`（导出文件下载端点）被我漏掉了，补回：

### **Assistant**
Committed only README.md (the data/localquant.db modification was pre-existing and untouched, left uncommitted as expected).

Done. Summarize for the user:
- develop branch created
- README restructured: what changed and why
- dedup list
- verification done
- commit info

完成。`develop` 分支已创建，README 重构已提交（`c6bdb7b`，只包含 README.md；工作区里原本就有的 `data/localquant.db` 改动未动）。

## 做了什么

**1. 展现方式：大表格 → 分节列表**

原来的「功能模块」是一张 13 行的表格，单个单元格长达三四百字，基本无法扫读。现在改为每个模块一个 `###` 小节 + 短列表（12 个模块：工作流编辑器、数据探索、因子研究、分钟因子、策略回测、QUBE Agent、策略库、实验管理、风险与组合分析、数据管理、工作台、AI 辅助），模块内的功能点用加粗引导词逐条列出，API 路径和参数名全部保留。

**2. 放置位置：散落的功能描述归位到所属模块**

原「工作流编辑器节点设计细节」「QUBE 与代码沙箱」「注意事项」三节里混着大量本属于具体模块的功能介绍，已全部合并归位。原「注意事项」中的研究口径条目独立成了「严谨性约定」一节（可交易掩码、前向填充、滚动 IC 无前视、IC 口径、point-in-time、复权存储等），注意事项只留真正的环境限制与安全告警。

**3. 消除的重复描述**（每项收敛到唯一位置，并核对了关键 API/参数无遗漏）：

- **多头约束/投资边界**：原文重复 5 处（顶部声明、回测模块、回测节点、QUBE、注意事项），现在只在顶部声明一次，其余位置改为引用
- **T+1 成交口径、成本拆分、基准对比、停牌预算缩减**：回测模块与回测节点描述合并为一处
- **沙箱**：QUBE 节与快速开始各写一遍，合并为「快速开始 → 代码执行沙箱」，保留了机制细节（文件 API 传 CSV、覆盖范围、实际探测）
- **市场环境仪表盘**：数据探索与节点细节两处合一
- **事件研究窗口语义、历史参考快照导入、数据时效、退市清算、因子面板/回测记录导出、指标来源门槛**：原「注意事项」里的功能描述分别移入数据探索/数据管理/策略回测/因子研究
- **AI 供应商清单**：原来在 QUBE 节完整罗列，归到「AI 辅助」，QUBE 节只保留「配置完全独立」这一真正差异点

校验：逐项 grep 了 26 个关键事实（`leverage_summary`、`delisting_loss`、`import-reference`、`attribution-run`、`execute_at`、`provenance` 等），除「技术栈/License 清单」这类合理的复述外均已单点化；过程中发现并补回了一处险些丢失的 `GET /api/factor/export-file/{token}` 端点。文档信息量没有损失，只做了重组。

### **You**
为什么这部分“

> **投资边界（系统级约束）**：本平台只做**普通股票多头投资**——正信号按日归一为满仓组合，总仓位始终 ≤ 100%（回测循环内逐日强制执行的硬约束，停牌/一字板冻结旧仓时买入按预算缩减，任何情况下不越界）；负信号视为「不买入」。系统**不提供、也不允许**融资、融券、做空、多空对冲或任何形式的杠杆交易。`dollar_neutral` / 原始权重（`none`）模式已在回测引擎与 QUBE 工具层移除；因子研究中的「多空组合」仅是 Top 组减 Bottom 组的统计诊断，不代表可交易的空头持仓。”不放到后面“严谨性约定”或者“注意事项”这里去

### **Assistant**
The user is asking a question: why is the 投资边界 (investment boundary) callout placed at the top of the README rather than in the 严谨性约定 (rigor conventions) or 注意事项 (notes) section?

This is a "describe reasoning" question — they're asking for my rationale. But there's also an implicit possibility they want it moved. Let me think about whether to just explain, or explain and offer/ask.

The user says "为什么不放到后面...去" — they're questioning the placement decision. The best response: explain the reasoning clearly, and give a recommendation. Since I'm in an interactive conversation now (not autonomous execution), and this is a genuine design question, I should explain my reasoning. If they want it moved, they'd say so — but actually, the question might be a soft way of suggesting "I think it should be moved."

Let me think about the actual merits:

Arguments for keeping it at the top:
1. It's not a "convention" or "note" — it's a product-level scope statement. It defines what the system IS and IS NOT. The 严谨性约定 section is about methodology correctness (IC calculations, point-in-time data, forward-fill); 注意事项 is about environment limitations and security caveats. The investment boundary is neither — it's a fundamental capability boundary.
2. It's the single most important thing a reader must know before evaluating anything else: someone reading "多空组合", "做空诊断" features might misunderstand. It changes the interpretation of many features downstream (回测、QUBE、组合优化、因子研究的多空统计).
3. Placement at top = prominence. It was written as a blockquote callout (>) specifically to be visually distinct. The README's first screen should tell the reader the most critical constraint.
4. Deduplication rationale: I made the top callout the single source of truth and turned the other 4 mentions into references ("见顶部投资边界"). If we move the callout to the back, then the forward references break — the backtests section says "见顶部投资边界" which would dangle.
5. Semantics: 注意事项 = "things to be aware of" (operational caveats), 严谨性约定 = "methodology guarantees". The boundary is a system-level constraint — neither. Moving it there would bury a scoping statement among technical notes, and readers skimming would miss it.

Arguments for moving to the back:
1. The top of a README is prime real estate; some would argue a README should start with what the project does, features, quick start — and constraints belong later.
2. It's a long paragraph; it pushes actual content down.

My recommendation: keep it at top. This is a deliberate information architecture decision:
- The boundary statement is a "scope/contract" statement, not a caveat. In docs hierarchy: what is this → what it is NOT → how it works → details.
- It prevents misreading the whole document: e.g., 因子研究 mentions "多空组合"、"分层多空统计量"、"因子加权多空" — without the top boundary, a reader could think the platform supports shorting. The boundary reframes all subsequent feature descriptions.
- It's load-bearing for safety/compliance framing: this is a quant research platform; stating the trading boundary up front is the project author's deliberate choice (it was at top in the original README too — I kept it there; the original author placed it there).
- Practical: my dedup made it the single source; 回测/QUBE sections point to it ("见顶部投资边界"). Moving it would require re-anchoring references.

Also important: the original README (before my refactor) already had it at the top (line 5). I deliberately preserved that placement — it wasn't my invention. That's worth mentioning: this was pre-existing, and I preserved it because it functions as a scope declaration.

However, if the user prefers it moved, it's a one-minute change — but I'd advise against, or offer a middle ground: keep a one-line summary at top ("只做普通股票多头，不融资/融券/做空——详见严谨性约定") and put the full text later. Actually that middle ground creates duplication again (which we just removed) — though a one-liner pointer is not really duplication.

Hmm, what's the right interaction here? The user asked "why". The instruction says: when the user is describing a problem or asking a question rather than requesting a change, the deliverable is the assessment. Report findings and stop. So I should explain the rationale, give my recommendation, and let them decide. I shouldn't move it unilaterally.

Let me structure the answer:

1. Direct answer: because it's a scope declaration (系统是什么/不是什么), not a convention or caveat; and it was already at top in the original, I kept it.
2. The functional reasons:
   - 定性不同: 严谨性约定 = 方法论正确性保证 (research correctness); 注意事项 = 环境限制/安全告警 (operational caveats). 投资边界 = 产品能力边界/合规声明 — 它定义后面所有功能描述的解读框架.
   - 阅读顺序: it changes how you read everything below (多空组合、分层多空、因子加权多空、组合优化 — without the boundary these could be misread as shorting capability). Top placement prevents misreading rather than correcting it after the fact.
   - 承重结构: my dedup made it the single source of truth; 回测和 QUBE 小节写着「见顶部投资边界」, moving it would break those anchors and re-introduce the "约束写在哪里" problem.
   - 视觉设计: blockquote callout is meant to be prominent — it's a contract statement, deserves first-screen visibility.
3. Acknowledge the trade-off: it does occupy prime first-screen space with a dense paragraph. If that's the concern, options: (a) keep as-is (recommended), (b) compress to one line at top + full text in 严谨性约定 (slight duplication, acceptable pointer style), (c) move entirely (I'd advise against).
4. Ask/offer: if you want it moved, say the word. Actually per guidance — offering follow-ups after answering is fine.

Keep it concise, prose-first, no giant headers needed. Maybe a short list for the reasons. Not too long.

One more consideration: is my reasoning actually right? Could the user be right that it belongs in 注意事项? The original author put it at top deliberately (it was line 5 of the original README, right after the intro, before 功能模块). Given the README describes lots of "多空" statistics, the boundary at top is genuinely the correct doc pattern ("scope statement up front"). I'll stand by recommending it stays, while acknowledging the alternative.

Also note: the boundary is not just about the research platform's own behavior — it's a "system-level constraint" that the engine enforces (硬约束 in the backtest loop). It's part of the product's definition, like "this tool only does X".

Length: moderate. Answer in Chinese. No need for tools — this is a pure explanation turn. Actually wait — should I verify the original placement claim? I have the original README content in context from the first Read: line 5 was the 投资边界 callout, right after intro. Yes, confirmed from conversation context. No tool calls needed.

End with: my recommendation + if you'd like it moved/compressed, I can do it. That's a legitimate "offering follow-up", allowed.

这是个有意为之的定位决策，主要有三层原因（也说明一下：这个位置不是我新加的——重构前的 README 里它就在第 5 行、紧跟简介，我保留并强化了它）：

**1. 它的定性和其他两节不同。** 「严谨性约定」是方法论承诺（IC 怎么算、有没有前视、复权口径对不对），「注意事项」是运维告警（xtquant 仅 Windows、CORS 安全）。而投资边界是**产品能力边界的声明**——“这个系统是什么、不是什么”。它不描述某个功能怎么做对，而是划定整个文档里所有功能描述的解读框架，性质上更接近简介的一部分，而不是某条“约定”或“注意”。

**2. 放在顶部是防止误读，放后面是事后纠偏。** 下文大量出现「多空组合」「分层多空统计量」「因子加权多空」「组合优化」这些词——如果读者先看到这些功能、最后才在注意事项里看到“不能做空”，中间一整段都会带着错误预期去读。边界声明放在第一屏，读者从第一段就知道“多空”只是统计诊断，后面所有相关描述都不需要二次解释。

**3. 它是这次去重的“锚点”。** 上一轮我把 5 处多头约束收敛成了这一处唯一声明，回测和 QUBE 小节里写的是「见顶部投资边界」这样的回指。如果把它挪到文档尾部，这些回指就断了，等于又要重新决定“约束写在哪里、别处怎么引用”——而尾部埋一条被别处引用的关键声明，恰好是文档组织里最差的位置。

它确实有代价：占用了第一屏最贵的位置，且段落很密。如果你觉得这个代价不值得，有两个折中方案：

- **压缩成一行放顶部**，如“> **投资边界**：只做普通股票多头（仓位 ≤ 100%，不做空/融资/融券），详见下方「严谨性约定」”，完整段落移到后面——但这会重新引入轻微重复；
- **整体后移**——我不推荐，理由如上。

我的建议是保持现状。如果你还是想挪，告诉我选哪种折中，我来改。

### **You**
作为 README 是否目前对项目介绍太详细了，可以放到 docs 或者哪里去？

### **Assistant**
The user is asking: is the README currently too detailed as a project introduction? Could the detailed content be moved to docs/ or elsewhere?

This is a question / design discussion. They're asking for my assessment and a proposal. Per the guidance: when the user is describing a problem or asking a question rather than requesting a change, the deliverable is my assessment. But this one leans toward "they probably want me to do it" — actually, re-read: "作为 README 是否目前对项目介绍太详细了，可以放到 docs 或者哪里去？" — "As a README, is it currently too detailed for a project introduction? Could it be moved to docs or somewhere?"

This is a question seeking my assessment + a proposal. It's a genuine scope decision about how to restructure. I should give an assessment and a concrete recommendation. Should I just do it? The user is asking "是否...可以..." — it's phrased as a question, seeking opinion. But in the previous turn, I answered "why" and offered options, and the user came back with another question. I think the right move here is to give a clear assessment with a concrete restructure plan, and since the user seems to be iterating on README structure with me, I could propose the split and ask which parts to move — or just recommend and do it?

The autonomous-operation guidance says: for reversible actions that follow from the original request, proceed. But this is a conversation where the user is asking my opinion ("是否太详细了？"). The exception clause: "when the user is describing a problem, asking a question, or thinking out loud rather than requesting a change, the deliverable is your assessment. Report your findings and stop. Don't apply a fix until they ask for one."

This is clearly a question. So I should give my assessment and a concrete proposal, not execute yet. But I can make the proposal very concrete (what stays, what moves where) so they can just say "好，就这么做".

Let me think about the actual substance: Is the README too detailed?

Current README after my refactor (~230 lines):
1. Title + intro
2. 投资边界 callout
3. 功能模块 (12 subsections, ~120 lines) — the bulk
4. 自定义节点 (code example)
5. 技术栈
6. 快速开始 (env, install, dev, sandbox, config)
7. 项目结构
8. 严谨性约定 (~9 bullets, dense methodology)
9. 注意事项
10. License

Is it too detailed? My honest assessment: Yes, for a typical README audience. A README's job: what is this, is it for me, how do I run it, where to learn more. The current README serves more as a comprehensive feature registry / single source of truth. The 功能模块 section with per-module bullets is documentation-level detail. The 严谨性约定 is methodology documentation. These are valuable — they read like a well-maintained feature spec — but they make the README long.

What's the right split? Common pattern:
- README.md: intro, boundary (short), feature overview (compact table or short list), quick start, project structure (brief), links to docs, License.
- docs/: move detailed module documentation, 严谨性约定, sandbox details, custom node guide, etc.

But wait — there's a consideration: this README functions as the project's feature registry. Recent commits show the README is carefully maintained with precise API paths. The owner may use it as the canonical reference. Moving to docs/ should preserve that value: split into topic docs, not just dump one giant file.

Also there's already a docs/ directory: docs/因子编写指南.md exists. Let me check what's in docs/ before proposing — I should look at the actual repo state to ground my proposal. Let me list docs/ and check whether there's a docs structure/conventions, and check README references to docs.

Also consider: who reads this? It's a personal/local research platform (本地投研工作站), single author (Alpherg Zhou). For a solo local tool, the README doubles as the author's own memory/feature registry. Moving detail out of README has real cost for the author (discoverability in one place). But the user themselves is asking whether it's too detailed — they feel it is.

A good middle structure:

README.md (keep ~100-120 lines):
- Title + one-paragraph intro
- 投资边界 (keep as-is, we just discussed it)
- 功能总览: compact table (module | one-liner) — back to a table but with one-line cells this time
- 快速开始 (env/install/dev/config essentials)
- 自定义节点 (it's a code example; could stay — it's short and is a "getting started" style item; or move to docs/自定义节点.md. I'd move to docs and link, keeping README tighter. Actually it's only ~25 lines including code; keeping is fine. Hmm. It's a "how to extend" doc — belongs in docs/ honestly. But it's also a nice README showcase. I'd move it to docs to keep README lean, with a link.)
- 文档索引 (links to docs/*)
- 项目结构 (keep, it's short and useful)
- 技术栈 (keep — it's scannable and useful for evaluation)
- License

docs/:
- docs/功能详解.md or split per module? Splitting per module into 12 files is overkill for a solo project. One docs/功能模块.md (or features.md) holding the detailed per-module bullets is fine.
- docs/严谨性约定.md (methodology)
- docs/自定义节点.md (the guide with code example)
- docs/代码执行沙箱.md? The sandbox setup is operational — keep the make commands in README quick start (short), move mechanism detail to docs or keep a condensed version. Sandbox section is ~15 lines; could stay in README as part of 快速开始 but trimmed; or move. I'd keep a 3-line version in README quick start + link.

Wait, also 注意事项 — mostly caveats; keep short in README or move to docs. The 访问安全/执行加固 bullets are long; move to docs (e.g., docs/安全与加固.md or into 严谨性约定 doc renamed 设计约定.md).

Actually, let me reconsider the split to keep it simple and maintainable:

README keeps:
1. 简介 (1 para)
2. 投资边界 (callout, as discussed)
3. 功能总览 (compact table: 12 rows, one-line each) — this preserves scannability
4. 快速开始 (环境要求/安装/启动/沙箱三行版/配置要点)
5. 项目结构 (maybe keep)
6. 技术栈 (maybe keep; it's 10 lines)
7. 文档导航 (links)
8. License

docs/ gains:
- docs/功能模块.md (the detailed per-module bullets — move verbatim)
- docs/严谨性约定.md (methodology bullets)
- docs/自定义节点.md (guide)
- docs/安全与工程约定.md? or fold 注意事项 items: 访问安全/执行加固/空数据错误统一 into 严谨性约定.md → rename to docs/设计约定.md covering both? Simpler: docs/严谨性与工程约定.md.

Hmm, but one file vs several: the author's commit history shows they like consolidated docs. Let me check docs/ first.

Also important: there are cross-references. QUBE's read_doc tool reads docs/因子编写指南.md. The backend may reference README? Let me grep for "README" references in code/docs to make sure moving content doesn't break references (e.g., tests or UI pointing at README sections). Also the in-README link "详见 docs/因子编写指南.md".

Plan for this turn:
1. Look at docs/ contents and any references to README in the repo (quick greps).
2. Give assessment: yes, it's drifted from "README" to "feature spec"; propose concrete split with file names and what stays/moves; note trade-offs (single-file registry vs README brevity); then ask if they want me to execute (or just say "确认的话我就动手").

Given the user's phrasing is a question, I'll deliver assessment + concrete plan and offer to execute. That respects the "report and stop" rule for questions while making it trivially easy to proceed.

Let me do the quick repo inspection first (docs/ listing, grep README references, maybe line count of README now).

你的感觉是对的——我先看一下 docs/ 现状和仓库里对 README 的引用，再给结论和拆分方案。

### **Assistant**
Interesting — backend code references README (backend/database.py, backend/routes/qube.py, backend/services/qube_agent.py, qube_skills, qube_skill_repo). Let me check what those references actually are — if code parses README sections or just mentions it in prompts, moving content could break things. Let me grep the actual matches.

有几个后端文件引用了 README，拆分前必须确认它们引用的是什么——如果是解析特定章节就会受影响。查一下：

### **You**
The TodoWrite tool hasn't been used recently. If you're working on tasks that would benefit from tracking progress, consider using the TodoWrite tool to track progress. Also consider cleaning up the todo list if has become stale and no longer matches what you are working on. Only use it if it's relevant to the current work. This is just a gentle reminder - ignore if not applicable.

### **Assistant**
Good — all those README references are about fetching GitHub READMEs of external skill repos (QUBE 技能库), nothing parses our local README.md. So splitting the README is safe code-wise.

Current state:
- README.md: 265 lines
- docs/: 因子编写指南.md (22KB), 审查与修复流程.md, QMTapi.pdf, ref/

The README's own references: the 功能模块 → 因子编写 links to docs/因子编写指南.md; 注意事项 references frontend/DESIGN-opencode.ai.md. No code depends on README content.

Now my assessment. The user asks: is the README too detailed as a project intro, and can detail move to docs?

My answer: 是的，偏长了。265 行里约 120 行是功能模块逐条细节，30 行是严谨性约定——这些是"参考文档/设计文档"性质，不是"项目门面"性质。README 应该回答：这是什么、给谁用、怎么跑起来、去哪看更多。

But also honest counterpoint: this README doubles as the author's feature registry (careful API paths etc.), and for a solo local project, one-file discoverability has value. The fix isn't deletion — it's relocation with an index, preserving all facts.

Proposed structure:

**README.md（保留 ~100 行）**
1. 简介（1 段）
2. 投资边界 callout（按上一轮讨论保留在顶部，可精简）
3. 功能总览：紧凑表格（12 行，每行一句话）——这次是真正的"一句话"
4. 快速开始（环境要求/安装/启动/配置要点；沙箱压缩为 3-4 行 + 链接）
5. 技术栈（10 行，保留，评估有用）
6. 文档导航（新增小节，列 docs/ 链接）
7. License

**docs/ 新增**
- docs/功能模块.md — 12 个模块的详细列表（现有功能模块小节原文迁移）
- docs/严谨性与工程约定.md — 严谨性约定 + 注意事项中的执行加固/访问安全/空数据错误统一/复权存储等
- docs/自定义节点.md — 自定义节点指南（代码示例）
- docs/代码执行沙箱.md — 机制细节（覆盖范围、探测逻辑、降级行为）

Wait — 项目结构 section: keep in README (it's standard README content, short). Or move? It's ~28 lines. Keep — standard and useful for orientation. Actually could trim, but fine to keep.

自定义节点: move to docs, README 功能总览 or 文档导航 links to it.

Sandbox: README keeps short setup (make sandbox-server + 状态查询一行), mechanism detail moves to docs.

注意事项 remaining in README? xtquant Windows-only and QMT-data-only are quick-start relevant — fold into 环境要求/快速开始 or a short 注意 bullet list (2-3 lines). Frontend theme + 工程检查 → docs 工程约定 doc.

Also: should 功能总览 be a table or bullets? A 12-row two-column table with genuinely one-line descriptions is good README practice.

Trade-off to mention: after split, the README is no longer the single-file registry; contributors/agents (like future AI sessions) must follow one more hop. Mitigation: 文档导航 section + keep links from each 功能总览 row? Keep it simple: one 导航 section.

Also mention what I verified: backend README references are about external GitHub skill repos, not our README — so no code breakage. frontend/DESIGN-opencode.ai.md is a design doc reference that will move with 注意事项 content but the README mention should stay pointing to it.

Now: execute or propose? The user's message is a question ("是否太详细了，可以放到 docs 或者哪里去？"). Per the rule: deliverable is assessment; don't apply fix until asked. But the question includes "可以放到 docs 或者哪里去？" which is close to a request with an implied "please". Hmm. "可以放到 docs 或者哪里去?" = "could it be moved to docs or somewhere?" — I read this as soliciting a recommendation + likely wanting it done. But given last turn I explicitly ended with "如果你还是想挪，告诉我选哪种折中，我来改" and the user responded with another question instead of a directive, the conversation mode is consultative. The safest and most useful move: give a crisp assessment + concrete split plan (file names, what moves), and ask one focused question only if needed.

Actually, the guidance about AskUserQuestion: use only when genuinely blocked on a user decision. Here there IS a real decision: how aggressive the split is (my recommended structure vs just moving 严谨性约定 vs minimal). But I have a clear recommendation; the user can just say "做吧" or adjust. I'll present the plan in text and let them confirm. That matches "report and stop" for questions.

Actually wait — let me reconsider. Over-asking is also bad. The user has now twice pushed toward "README too heavy" (first asked to reorganize, now asks if it's too detailed and should move to docs). The trajectory of intent is pretty clear: they want the README slimmed. The remaining question "或者哪里去" is asking me where. I could just do it — but it's a scope change from the previous task with structural choices (how many files, what stays). Given the autonomous-operation note says "For reversible actions that follow from the original request, proceed without asking" — but the exception says for questions, deliver the assessment.

The message is literally a question ("是否...？可以...？"). I'll answer it with a firm recommendation and a concrete plan, then say "确认后我就动手" — one line. That's not blocking on trivia; it's respecting that this is a consultative exchange. Hmm, but it does end the turn with "waiting for confirmation" which the guidance warns against for actual requests... The guidance: "Exception: when the user is describing a problem, asking a question, or thinking out loud rather than requesting a change, the deliverable is your assessment. Report your findings and stop."

Yes — this is a question. Deliver assessment + plan, stop. Make the plan concrete enough that "好" is a sufficient trigger.

Let me draft the response concisely:

1. 结论: 是，README 现在承担了两个角色——项目门面 + 功能规格书。265 行中 ~150 行是规格书内容（功能模块细节 120 行 + 严谨性约定/工程注意事项 ~40 行）。README 该回答"是什么/怎么跑/去哪看更多"，规格细节应该住 docs/。
2. 已核实: 后端代码里的 "README" 引用都是抓取外部 GitHub 技能仓库的 README，与本仓库 README 无关 → 拆分无代码风险。docs/ 已有 因子编写指南.md 等，先例成立。
3. 方案（保留全部事实，只搬家 + 留索引）:
   - README 保留: 简介、投资边界、功能总览（12 行一句话表格）、快速开始（含沙箱 3 行精简版 + 链接）、技术栈、项目结构、文档导航、License → 约 100-110 行
   - docs/功能模块.md: 现有 12 个模块的详细列表整体迁入
   - docs/严谨性与工程约定.md: 严谨性约定 9 条 + 注意事项里的执行加固/访问安全/空数据错误统一/工程检查等
   - docs/自定义节点.md: 自定义节点指南（含代码示例）
   - docs/代码执行沙箱.md: 机制细节（数据传递/覆盖范围/探测/降级）
   - xtquant 仅 Windows、数据只来自 QMT 这类一句话提醒并入快速开始
4. 代价说明: 以后查细节要多一跳（或用文档导航直达）；对 AI 会话/协作者影响通过导航区缓解。
5. 确认后我就动手（在 develop 上）。

One question I could fold in: 功能总览用表格还是列表 — minor, I'll just decide (table).

Should I mention 投资边界 in the slim README? Yes keep per last discussion — it stays at top, it's part of the "门面" (scope statement). Maybe slightly compressed but keep verbatim is fine.

Length: keep it tight. Use a short structure. No need for headers maybe; use bold labels + lists.

是的，现在确实太详细了——问题不在写得不好，而在 README 承担了两个角色：**项目门面**（是什么、怎么跑起来）和**功能规格书**（每个模块的功能清单、方法论约定）。现在 265 行里约 150 行是规格书内容，这些内容对“来评估这个项目的人”是噪音，对“每天用它的人”（也就是你自己）才是干货。

拆分前我核实了两件事：

- **没有代码风险**：backend 里那些 `README` 引用都是 QUBE 技能库抓取**外部 GitHub 仓库**的 README，与本仓库的 README.md 无关，拆分不影响任何代码；
- **docs/ 已有先例**：`docs/因子编写指南.md`、`docs/审查与修复流程.md` 已经存在，README 里也有指向它们的链接，规格文档住 docs/ 是这个仓库既有的惯例。

## 建议的拆分方案（事实不删，只搬家 + 留索引）

**README.md 收敛到约 100 行**，只保留门面内容：

1. 简介 + 投资边界（维持上一轮讨论的顶部位置）
2. **功能总览**：12 行紧凑表格，每格真正一句话（如“因子研究——因子库/批量扫描/体检/样本外验证，详见 docs/功能模块.md"）
3. 快速开始（环境要求、安装、启动、配置；沙箱压缩为三四行 + 链接）
4. 技术栈、项目结构（各十来行，保留）
5. **文档导航**（新增小节，列下方 docs 文件）
6. License

**docs/ 新增四个文件**，承接现在的详细内容：

| 新文件 | 承接内容 |
|---|---|
| `docs/功能模块.md` | 现有 12 个模块的详细功能列表，整体迁入 |
| `docs/严谨性与工程约定.md` | 严谨性约定 9 条 + 注意事项里的执行加固/访问安全/空数据错误统一/工程检查 |
| `docs/自定义节点.md` | 自定义节点指南（含代码示例） |
| `docs/代码执行沙箱.md` | 沙箱机制细节（数据传递、覆盖范围、探测与降级行为） |

xtquant 仅 Windows、数据唯一来源 QMT 这类一句话级别的提醒，并入快速开始的环境要求里，不单独成文。

**代价**说清楚：以后查某个功能的细节要多一跳（README → docs），但文档导航区可以直达；对 AI 会话（比如 QUBE 的 `read_doc`、以后的我）也不受影响，反而 docs/ 是它们约定俗成的检索位置。

方案就是这些。你确认（或调整拆法）后我就在 develop 上动手：四个 docs 文件 + README 瘦身 + 导航链接，一个 commit 完成。

### **You**
可以，请动手吧

### **Assistant**
The user confirmed. Now I execute the plan:

1. Create `docs/功能模块.md` — the detailed 12-module feature list (from current README's 功能模块 section, verbatim mostly)
2. Create `docs/严谨性与工程约定.md` — 严谨性约定 9 bullets + 注意事项 items (执行加固/访问安全/空数据错误统一/工程检查/复权存储 etc.)
3. Create `docs/自定义节点.md` — custom node guide with code example
4. Create `docs/代码执行沙箱.md` — sandbox mechanism details
5. Slim README.md to ~100 lines: 简介 + 投资边界, 功能总览 table (12 rows, one-line each), 快速开始 (with short sandbox), 技术栈, 项目结构, 文档导航, License; fold xtquant Windows-only and QMT-only into 环境要求
6. Commit on develop

Let me use TodoWrite to track since this is a multi-step task. Actually it's a fairly linear 5-file task; a todo list is reasonable but might be overkill. The reminder nudged me to consider it. I'll use a small todo list.

Let me plan the content of each file carefully.

Current README content (from my rewrite, which is in my context). Let me map content:

**docs/功能模块.md** — takes the entire current "## 功能模块" section (12 subsections with bullets). I should add a title and a small intro, plus maybe back-link to README. Structure:

```markdown
# 功能模块详解

各模块的完整功能清单。模块概览与快速开始见 [README](../README.md)；研究口径与工程约定见 [严谨性与工程约定](./严谨性与工程约定.md)。

## 工作流编辑器
...(current content verbatim)

## 数据探索
...
(etc, 12 sections)
```

Note: in the new docs file, the section levels: current README uses `###` under `## 功能模块`. In the new doc, modules become `##`. I need to adjust heading levels (### → ##). Content otherwise verbatim.

Cross-references inside content: 
- 因子编写 bullet links to `docs/因子编写指南.md` — from docs/, the relative link must change to `./因子编写指南.md` (same dir). Original text: "详见 [docs/因子编写指南.md](docs/因子编写指南.md)" → in docs/功能模块.md it should be "[因子编写指南](./因子编写指南.md)".
- "（见顶部投资边界）" references in 策略回测 and QUBE sections — the 投资边界 lives in README now. Change to "（见 [README 投资边界](../README.md)）" or keep "（见 README 顶部投资边界）". I'll use a link: `（见 [README · 投资边界](../README.md#投资边界系统级约束)）` — anchor links for Chinese headings in GitHub work with the heading text; the heading is "> **投资边界（系统级约束）**" which is a blockquote, not a heading — no anchor exists. So just plain text "（见 README 顶部「投资边界」）" with a link to ../README.md. Simpler: keep text, add link to ../README.md.
- "（见「严谨性约定」）" in 数据探索 事件研究 bullet → link to ./严谨性与工程约定.md.
- 复权存储 mention in 数据管理: "复权存储口径见「注意事项」" — wait, in my rewrite I wrote "**除权事件**：最近除权事件清单（`adjust_factor` 跳变检测：股票/日期/比例）。" — did I include a reference? Let me check my written README... In 数据管理 I wrote: "- **除权事件**：最近除权事件清单（`adjust_factor` 跳变检测：股票/日期/比例）。" No cross-ref. OK.
- AI 辅助 mentions "接入方式与「AI 辅助」一致" in QUBE — within same doc, fine.

**docs/严谨性与工程约定.md** — takes:
- The entire "## 严谨性约定" section (9 bullets: 可交易掩码, 前向填充, 滚动 IC 无前视, IC 口径, Point-in-time, 默认股票池剔除指数, 全量溯源, 全市场面板 artifact, 复权存储)
- From 注意事项: 访问安全, 执行加固, 空数据错误统一, 工程检查, and 数据全部来自 QMT? Hmm — "数据全部来自 QMT，不使用模拟数据" — that's a data-source principle. I planned to fold the one-liner into README 快速开始环境要求 ("xtquant 仅 Windows，macOS 开发时 QMT 数据功能不可用；数据唯一来源 QMT"). But the fuller statement with 参考元数据补充 → that's now in 数据管理 (历史参考快照导入 bullet in 功能模块.md). So the 严谨性与工程约定 doc can include a "数据来源" line too. Let me put under 工程约定: 数据全部来自 QMT、不使用模拟数据（历史参考元数据经「数据管理 → 历史参考快照导入」补充，见功能模块文档）。Hmm, that duplicates 功能模块.md's import bullet slightly — it's a one-line principle statement, acceptable. Actually to keep dedup discipline: 注意事项 original line: "数据全部来自 QMT，不使用模拟数据（行情来源唯一；历史成分/名称/两融池等参考元数据可经「数据管理 → 历史参考快照导入」补充）" — I'll keep this one-liner in the 约定 doc (principle) and NOT repeat in README beyond the quick-start line "数据唯一来源 QMT（不用模拟数据）". Hmm, that IS a small duplication. Alternative: quick start env says "QMT 客户端（Windows，用于数据获取）——数据唯一来源，见环境要求" — the 环境要求 already says QMT 客户端（Windows，用于数据获取）. I'll add to that bullet: "；数据唯一来自 QMT，不使用模拟数据". And in the 约定 doc, drop the data-source bullet to avoid dup? But it's a principle worth stating in the 约定 doc... 

Decision: put the full principle line in 严谨性与工程约定.md (as part of 严谨性 spirit: 行情来源唯一), and in README 快速开始 just add a parenthetical to the QMT env bullet: "QMT 客户端（Windows，用于数据获取；xtquant 仅支持 Windows，macOS 开发时数据功能不可用）". The "不使用模拟数据" principle lives in the 约定 doc. That way each fact appears once: Windows-only caveat in README quick start (operational), data-source principle in 约定 doc. Wait, original README line 176-177 were: "xtquant 仅支持 Windows..." and "数据全部来自 QMT，不使用模拟数据...". My plan: 
- README 环境要求 bullet: "QMT 客户端（Windows，用于数据获取）——xtquant 仅支持 Windows，macOS 开发时 QMT 数据功能不可用"
- 约定 doc: "行情来源唯一：数据全部来自 QMT，不使用模拟数据；历史成分/名称/两融池等参考元数据可经「数据管理 → 历史参考快照导入」补充（见[功能模块](./功能模块.md)）"

Good, no dup.

- Also 前端主题 (OpenCode 浅色主题, frontend/DESIGN-opencode.ai.md) → 约定 doc 工程部分.

Structure of 严谨性与工程约定.md:

```markdown
# 严谨性与工程约定

自研研究/回测路径默认启用的研究口径约定，以及工程与安全约定。模块功能清单见 [功能模块](./功能模块.md)。

## 投资边界

Hmm — should the 投资边界 full text also live here? Last turn I argued it stays in README top as the single declaration. If I duplicate it here that violates dedup. The 策略回测/QUBE sections in 功能模块.md reference "见 README 顶部投资边界". Keep single source in README. Don't copy it into the 约定 doc. OK.

## 严谨性约定（研究口径）
(9 bullets verbatim, with internal cross-refs adjusted if any)
- The 严谨性约定 bullets reference "见「数据管理 → 退市/历史代码清单」"? No — that was in 策略回测 bullet (功能模块). Let me check my README text for 严谨性约定 bullets... The 复权存储 bullet mentions SQL 探索. No cross-doc refs. Fine verbatim.
- Wait, 数据探索 事件研究 bullet in 功能模块.md says "（见「严谨性约定」）" → becomes link to this doc.

## 工程与安全约定
- **执行加固**：... (verbatim)
- **访问安全**：... (verbatim)
- **空数据错误统一**：... (verbatim)
- 行情来源唯一：... (as above)
- 前端主题：前端采用 OpenCode 浅色主题风格，见 frontend/DESIGN-opencode.ai.md
- 工程检查：... (verbatim)
```

Hmm, ordering: maybe 数据来源 first? Order: 行情来源唯一, 执行加固, 访问安全, 空数据错误统一, 前端主题, 工程检查. Fine.

**docs/自定义节点.md** — takes the 自定义节点 section:

```markdown
# 自定义节点指南

通过插件系统在 `data/custom_nodes/` 目录扩展工作流节点。节点会在左侧面板「08-自定义」分组出现。

Wait — "节点会在左侧面板「08-自定义」分组出现" — don't invent facts. The example code has group="08-自定义". Stick to original text only. Original: "在 `data/custom_nodes/` 目录放置 Python 文件：" + code. I can add a minimal intro sentence that's derivable: the decorator registers a work node. Careful not to fabricate. I'll keep it nearly verbatim with a one-line intro: "在 `data/custom_nodes/` 目录放置 Python 文件即可注册自定义工作流节点（插件系统 `backend/plugins/` 的 `@work_node` 装饰器）：" — backend/plugins is in 项目结构 ("plugins/ # 节点插件系统（@work_node）"), so that's grounded.

Also worth adding (grounded from README content): 自定义节点为用户自编 Python 的完整执行环境（可运行任意代码），仅限本机可信使用 — that's in 执行加固. Adding a safety note here with link is helpful and grounded: "> 注意：自定义节点是**用户自编 Python 的完整执行环境**（可运行任意代码），仅限本机可信使用（见[严谨性与工程约定](./严谨性与工程约定.md)）。" — this duplicates the 执行加固 bullet partially. It's a safety-critical note; a one-line pointer in the custom-node doc is justified (pointer + partial restatement). Hmm, dedup discipline... The user cared about duplication. A cross-cutting safety warning on the page about running arbitrary code is standard practice; I'll phrase as pointer: "自定义节点为用户自编 Python 的完整执行环境（可运行任意代码），仅限本机可信使用——详见[严谨性与工程约定 · 执行加固](./严谨性与工程约定.md)。" That's mostly a pointer. Acceptable.

**docs/代码执行沙箱.md** — takes the 快速开始 sandbox subsection content:

```markdown
# 代码执行沙箱

## 机制
QUBE/回测的信号代码经 `backend/services/sandbox.py` 执行：优先在 OpenSandbox 容器中隔离（数据经文件 API 以 CSV 传入，不挂载卷，兼容 Windows），Docker/沙箱服务未就绪时自动降级为进程内执行（无容器隔离，日志/回测结果会标注）；仅覆盖 `/api/backtest/run-strategy` 与 QUBE `run_backtest`，因子研究页与工作流因子节点保持原生执行。

## 启用
客户端已随 `make install` 安装。要真正启用隔离，先启动 Docker Desktop，再单开一个终端跑沙箱服务：

```bash
make sandbox-server   # 实质执行 uvx opensandbox-server
```

## 状态查询
状态可查 `GET /api/system/sandbox`：实际探测 opensandbox-server（HTTP 健康探测 + TCP 兜底，而非仅看包安装/配置开关），`active=false` 即当前为进程内降级。
```

**README.md new version**:

```markdown
# LocalQuant — 本地投研工作站

基于 QMT 数据接口的本地量化投研平台，以 ComfyUI 风格的节点化工作流为核心，集成数据探索、因子研究、策略回测、QUBE 策略 Agent、策略库与实验管理等功能。

> **投资边界（系统级约束）**：(verbatim)

## 功能总览

| 模块 | 简介 |
|------|------|
| **工作流编辑器** | iframe 内嵌官方 ComfyUI 前端搭建研究管线；节点代码编辑/说明/缓存/因子链路，详见 [docs/功能模块.md](docs/功能模块.md) |
...
```

Hmm wait — putting "详见 docs/功能模块.md" in every row is repetitive. Better: one line above/below the table: "各模块完整功能清单见 [docs/功能模块.md](docs/功能模块.md)。" and keep table cells as pure one-liners. Yes.

One-liners per module (must be genuinely one line, derived from the detail):

- 工作流编辑器: iframe 内嵌官方 ComfyUI 前端搭建研究管线，节点代码编辑、因子分析链路与完整运行产物管理
- 数据探索: 概览/SQL/AI 生成 SQL/全市场扫描/横截面/异常检测 + 市场环境仪表盘 + 事件研究，基于本地 Parquet 缓存
- 因子研究: 因子库、批量扫描、因子体检、样本外验证、因子池→组合回测闭环与面板导出
- 分钟因子 · 日内高频: 分钟缓存→清洗→分钟公式→折叠日频面板，时刻 IC 曲线与回测执行时点
- 策略回测: 向量化回测，T+1 收盘成交、成本拆分、容量分析、退市清算、风格/行业归因，仅普通多头
- QUBE 策略 Agent: 多轮对话设计策略的 AI Agent（工具调用循环 + 策略工作台），AI 配置独立
- 策略库: 工作中/已保存两态与版本回滚
- 实验管理: 实验记录、多实验对比、研究日志，回测/工作流自动关联
- 风险与组合分析: 风格暴露、组合优化、压力测试（历史情景回放）、事前风险预测
- 数据管理: QMT 下载与缓存、质量检查、除权/退市清单、指数成分快照、历史参考快照导入
- 工作台: 首页每日研究简报（市场状态、数据就绪度、体检摘要、除权、时效）
- AI 辅助: 节点代码改写、NL 生成工作流、SQL 生成与解读、因子分析建议；供应商预置/BYOK/本机 CLI

Then: "> 各模块完整功能清单见 [docs/功能模块.md](docs/功能模块.md)。"

## 快速开始

### 环境要求
- Python >= 3.12
- Node.js >= 18
- uv (Python 包管理)
- QMT 客户端（Windows，用于数据获取）——xtquant 仅支持 Windows，macOS 开发时 QMT 数据功能不可用
- Docker Desktop（可选；Windows 用 WSL2 后端）——开启回测信号代码的容器隔离（OpenSandbox），不装则自动降级为进程内执行

### 安装 (verbatim)
### 启动 (verbatim)

### 代码执行沙箱（可选，推荐）
QUBE/回测的信号代码优先在 OpenSandbox 容器中隔离执行，未就绪时自动降级为进程内执行并在结果中标注。启用方式与机制细节见 [docs/代码执行沙箱.md](docs/代码执行沙箱.md)。

```bash
make sandbox-server   # 先启动 Docker Desktop，实质执行 uvx opensandbox-server
```

### 配置 (verbatim)

## 项目结构 (verbatim — it mentions data/custom_nodes which relates to custom nodes; fine)

Should 项目结构 stay? Yes, planned. It's ~28 lines. Hmm, "收敛到约 100 行" — let me count: title+intro+callout ~8, 功能总览 ~18, 快速开始 ~45 (env 7, install 8, dev 12, sandbox 7, config 12), 项目结构 ~30, 技术栈 ~12, 文档导航 ~8, License ~12 → ~135 lines. A bit over 100 but fine. Could trim 项目结构 to keep? I said I'd keep it. OK, ~135 lines is a big improvement over 265 and acceptable. Actually, let me reconsider — maybe move 项目结构 out too? No — 项目结构 is standard README content and helps orientation; keep. 

## 技术栈 (verbatim 10 lines)

## 文档

- [docs/功能模块.md](docs/功能模块.md) — 12 个功能模块的完整清单
- [docs/严谨性与工程约定.md](docs/严谨性与工程约定.md) — 研究口径（IC/前视/point-in-time/复权等）与工程安全约定
- [docs/自定义节点.md](docs/自定义节点.md) — 编写自定义工作流节点
- [docs/代码执行沙箱.md](docs/代码执行沙箱.md) — 信号代码容器隔离的机制与启用
- [docs/因子编写指南.md](docs/因子编写指南.md) — 因子公式/代码编写（因子库「变量参考」同源；QUBE read_doc 可读）
- [docs/审查与修复流程.md](docs/审查与修复流程.md) — 现有的流程文档 (I should include since it exists; let me check what it is — it's a process doc 3.5KB. Title suggests dev process. Include in nav.)
- frontend/DESIGN-opencode.ai.md — 前端设计主题 (this moved out of 注意事项; include in nav)

Section title: "## 文档" or "## 文档导航". I'll use "## 文档".

## License (verbatim)

Now — one more check on the 约定 doc title: "严谨性与工程约定.md". In 功能总览/导航 link text consistent.

Also: the 因子研究 module bullet in 功能模块.md references "[docs/因子编写指南.md](docs/因子编写指南.md)" → change to "[因子编写指南](./因子编写指南.md)".

事件研究 bullet references "（见「严谨性约定」）" → "（见[严谨性与工程约定](./严谨性与工程约定.md)）".

策略回测 "（见顶部投资边界）" → "（见 [README · 投资边界](../README.md)）" — hmm, cleaner: "（见 README 顶部「投资边界」）" with the whole phrase linked? Markdown: `（见 [README 顶部「投资边界」](../README.md)）`. OK.

QUBE bullet: "（见顶部投资边界）" → same treatment.

因子池→组合回测闭环: no refs. 退市强制清算 references "「数据管理 → 退市/历史代码清单」" — both now in same doc (功能模块.md), fine as is.

风险与组合分析: no external refs.

数据管理: 复权事件 bullet — in my rewrite did I reference 复权存储? I wrote just "最近除权事件清单（`adjust_factor` 跳变检测：股票/日期/比例）。" Fine. But maybe add pointer to 复权存储 convention in 约定 doc? Optional; skip to avoid clutter. Actually the 复权存储 bullet is in 约定 doc now; a link from 数据管理 除权事件 could help: "（复权口径见[严谨性与工程约定](./严谨性与工程约定.md)）" — I'll add, small and useful.

自定义节点 doc: title "# 自定义节点", content as planned.

README 功能总览 table header: | 模块 | 简介 |. 

Also the README 功能模块 section had intro lines under some sections ("全部功能基于本地 Parquet 缓存", "向量化回测引擎...") — those move verbatim into docs/功能模块.md.

One subtlety: docs/功能模块.md heading levels — currently `## 功能模块` → doc title `# 功能模块`, modules `##`. The subsections' bullets unchanged.

Also 功能模块.md intro: "各模块的完整功能清单。模块速览见 [README](../README.md#功能总览) — anchor: the heading is "## 功能总览" → GitHub anchor for Chinese: #功能总览. GitHub generates anchors from heading text, Chinese characters preserved: `../README.md#功能总览` should work. I'll include; harmless if it fails.

Now also make sure: README previously had "## 功能模块" heading — replaced by "## 功能总览".

Also the 约定 doc: include 投资边界 pointer? The doc's intro can say "交易边界（只做普通多头）见 README 顶部声明" — one line pointer, fine. Actually the 严谨性约定 bullets don't discuss the boundary. I'll add a one-line note in intro: "系统的交易边界（仅普通股票多头）统一见 [README 顶部「投资边界」](../README.md)。" Good for discoverability without duplication.

Todo list: 5 items (4 docs files, README rewrite, commit). Let me create todos, then write files, then verify (grep check + maybe markdown lint quick), then commit.

Let me now write all files. I'll do Write calls — 4 new docs + 1 README rewrite. I can parallelize the 4 new file writes? They're independent. Write README last (depends on nothing, but fine). Then commit.

Let me draft final content for each file.

---

docs/功能模块.md:

# 功能模块

各功能模块的完整清单。模块速览与快速开始见 [README](../README.md)；研究口径与工程/安全约定见 [严谨性与工程约定](./严谨性与工程约定.md)。

## 工作流编辑器

iframe 内嵌官方 ComfyUI 前端，以节点画布搭建研究管线。

- **节点代码**：... (verbatim from current README)
- **节点交互**：...
- **运行产物**：...
- **节点缓存随数据失效**：...
- **工作流日志**：...
- **因子链路**：...

## 数据探索

全部功能基于本地 Parquet 缓存。

- **概览与查询**：...
- **市场环境仪表盘**（数据中心顶部）：... 基于...（`/api/regime/overview`）；工作流亦提供市场环境节点。
- **事件研究**：...（见[严谨性与工程约定](./严谨性与工程约定.md)）。窗口语义：...

Wait, current text: "收益面板同样为前向填充口径（见「严谨性约定」）。" → change to "（见[严谨性与工程约定](./严谨性与工程约定.md)）"。

## 因子研究
... (verbatim, fix 因子编写指南 link to ./因子编写指南.md)

## 分钟因子 · 日内高频
(verbatim)

## 策略回测

向量化回测引擎，工作流回测节点、回测接口与 QUBE 策略工作台共用（默认成本三处一致：佣金率 0.001 / 滑点 0.001 / 卖出印花税 0.0005）。

- **执行口径**：...
- **仅普通股票多头**（见 [README 顶部「投资边界」](../README.md)）：...
...

## QUBE 策略 Agent
...系统提示词固定为普通股票多头约束（见 [README 顶部「投资边界」](../README.md)）...

## 策略库
## 实验管理
## 风险与组合分析
## 数据管理
(除权事件 bullet + 复权口径 pointer: "- **除权事件**：最近除权事件清单（`adjust_factor` 跳变检测：股票/日期/比例）；复权存储口径见[严谨性与工程约定](./严谨性与工程约定.md)。")
## 工作台
## AI 辅助

---

docs/严谨性与工程约定.md:

# 严谨性与工程约定

自研研究/回测路径默认启用的研究口径，以及工程与安全约定。系统的交易边界（仅普通股票多头）统一见 [README 顶部「投资边界」](../README.md)；模块功能清单见 [功能模块](./功能模块.md)。

## 研究口径（严谨性约定）

- **可交易掩码**：...
- **收益率面板统一为前向填充口径**：...
- **滚动 IC 加权无前视**：...
- **IC 口径**：...
- **Point-in-time**：...
- **默认股票池剔除指数缓存**：...
- **全量溯源**：...
- **全市场面板本地 artifact**：...
- **复权存储**：...

## 行情来源

- 数据全部来自 QMT，不使用模拟数据（行情来源唯一）；历史成分/名称/两融池等**参考元数据**可经「数据管理 → 历史参考快照导入」补充（见[功能模块 · 数据管理](./功能模块.md)）。

Hmm, as a section with one bullet — maybe fold into 工程与安全约定 as first bullet? Or make "## 数据来源" tiny section. Simpler: put as first bullet under 工程与安全约定? It's not really 工程/安全. I'll make it a short bullet list under "## 数据来源" — fine, small.

Actually simpler: two sections: "## 研究口径" and "## 工程与安全约定" with the 数据来源 line as the first bullet of 工程与安全约定 renamed... no. Keep three small sections; it's fine. Or: "## 其他约定" ... Let me just do:

## 研究口径
(9 bullets)

## 工程与安全约定

- **行情来源唯一**：数据全部来自 QMT，不使用模拟数据；历史成分/名称/两融池等**参考元数据**可经「数据管理 → 历史参考快照导入」补充（见[功能模块](./功能模块.md)）。
- **执行加固**：...
- **访问安全**：...
- **空数据错误统一**：...
- **前端主题**：采用 OpenCode 浅色主题风格，见 frontend/DESIGN-opencode.ai.md。
- **工程检查**：...

Good, two sections.

---

docs/自定义节点.md:

# 自定义节点

在 `data/custom_nodes/` 目录放置 Python 文件，即可通过插件系统（`backend/plugins/`，`@work_node` 装饰器）注册自定义工作流节点：

(code block verbatim)

> 自定义节点为**用户自编 Python 的完整执行环境**（可运行任意代码），仅限本机可信使用——详见[严谨性与工程约定](./严谨性与工程约定.md)。

---

docs/代码执行沙箱.md:

# 代码执行沙箱

QUBE/回测的信号代码经 `backend/services/sandbox.py` 执行：优先在 OpenSandbox 容器中隔离（数据经文件 API 以 CSV 传入，不挂载卷，兼容 Windows），Docker/沙箱服务未就绪时自动降级为进程内执行（无容器隔离，日志/回测结果会标注）；仅覆盖 `/api/backtest/run-strategy` 与 QUBE `run_backtest`，因子研究页与工作流因子节点保持原生执行。

## 启用

客户端已随 `make install` 安装。要真正启用隔离，先启动 Docker Desktop，再单开一个终端跑沙箱服务：

```bash
make sandbox-server   # 实质执行 uvx opensandbox-server
```

## 状态查询

`GET /api/system/sandbox`：实际探测 opensandbox-server（HTTP 健康探测 + TCP 兜底，而非仅看包安装/配置开关），`active=false` 即当前为进程内降级。

---

README.md new:

# LocalQuant — 本地投研工作站

(intro verbatim)

> **投资边界（系统级约束）**：... (verbatim)

## 功能总览

| 模块 | 简介 |
|------|------|
| **工作流编辑器** | iframe 内嵌官方 ComfyUI 前端搭建研究管线：节点代码编辑（Monaco + ruff）、因子分析链路、运行产物与缓存管理 |
| **数据探索** | 概览 / SQL（AI 生成与解读）/ 全市场扫描 / 横截面 / 异常检测 + 市场环境仪表盘 + 事件研究，基于本地 Parquet 缓存 |
| **因子研究** | 因子库、批量扫描、因子体检与拥挤度、样本外验证、因子池 → 组合回测闭环、AlphaLens、面板导出 |
| **分钟因子 · 日内高频** | 分钟缓存 → 清洗 → 分钟公式 → 折叠日频面板；时刻 IC 曲线；回测 `execute_at` 执行时点 |
| **策略回测** | 向量化回测：T 日信号 T+1 收盘成交、成本拆分、容量分析、参数敏感性、退市清算、风格/行业归因 |
| **QUBE 策略 Agent** | 多轮对话设计策略的 AI Agent（工具调用循环 + 策略工作台），AI 配置独立 |
| **策略库** | 工作中 / 已保存两态，版本历史回滚 |
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

(verbatim)

## 项目结构

(verbatim)

## 技术栈

(verbatim)

## 文档

| 文档 | 内容 |
|------|------|
| [docs/功能模块.md](docs/功能模块.md) | 12 个功能模块的完整清单 |
| [docs/严谨性与工程约定.md](docs/严谨性与工程约定.md) | 研究口径（可交易掩码/前向填充/无前视/IC 口径/point-in-time/复权等）与工程、安全约定 |
| [docs/自定义节点.md](docs/自定义节点.md) | 编写自定义工作流节点 |
| [docs/代码执行沙箱.md](docs/代码执行沙箱.md) | 信号代码容器隔离：机制、启用、状态查询 |
| [docs/因子编写指南.md](docs/因子编写指南.md) | 因子公式/代码编写（因子库「变量参考」同源文档） |
| [docs/审查与修复流程.md](docs/审查与修复流程.md) | 审查与修复流程 |

Hmm — do I know what 审查与修复流程.md contains? Name suggests dev review/fix process. Description "审查与修复流程" is safe (tautological). Fine.

Should the nav be a table or list? A list is fine too. I'll use a list (less rigid):

## 文档

- [功能模块](docs/功能模块.md) — 12 个功能模块的完整功能清单
- [严谨性与工程约定](docs/严谨性与工程约定.md) — 研究口径与工程/安全约定
- [自定义节点](docs/自定义节点.md) — 编写自定义工作流节点
- [代码执行沙箱](docs/代码执行沙箱.md) — 信号代码容器隔离的机制与启用
- [因子编写指南](docs/因子编写指南.md) — 因子公式/代码编写（因子库「变量参考」同源）
- [审查与修复流程](docs/审查与修复流程.md)
- 前端主题：[frontend/DESIGN-opencode.ai.md](frontend/DESIGN-opencode.ai.md)

## License

(verbatim)

Count lines: roughly 130. Good.

Also: I need to double check the 功能总览 table one-liners against facts (no invention):
- 工作流编辑器 one-liner: grounded ✓ (Monaco + AI 改写 + ruff — I dropped "AI 改写" in one-liner, fine; said "节点代码编辑（Monaco + ruff）")
- 数据探索 ✓
- 因子研究 ✓
- 分钟因子 ✓ (execute_at is code-formatted inside table cell — fine)
- 策略回测 ✓
- QUBE ✓
- 策略库 ✓ ("策略代码版本历史可回滚" → "版本历史回滚" ✓)
- 实验管理 ✓ ("自动创建并关联 source_id" → "自动创建" fine)
- 风险与组合分析 ✓ (add 绩效补充指标/蒙特卡洛? one-liner can't have everything; fine)
- 数据管理 ✓
- 工作台 ✓
- AI 辅助 ✓

Now write todos and execute. After writes: verify links exist (all linked files exist), then commit. Also update: should I git mv? No — README.md is modified in place; new files added.

Also, one consideration: the 功能模块.md uses `##` headings for modules — fine.

Also double-check: in README 配置 section verbatim includes "大部分可在设置页 / QUBE 配置里改" ✓.

Let me also make sure I keep the trailing "对外分发（含二进制/SaaS）须一并提供完整对应源码。" etc.

Also check the intro of docs/功能模块.md mentions "12 个模块"? The doc has 12 `##` sections — wait, count: 工作流编辑器, 数据探索, 因子研究, 分钟因子, 策略回测, QUBE, 策略库, 实验管理, 风险与组合分析, 数据管理, 工作台, AI 辅助 = 12 ✓.

Commit message: "docs: README 收敛为项目门面，功能详情拆分至 docs/"

Body: describe the 4 new files + README slimming.

Now execute. TodoWrite first, then 4 Write calls (can be parallel), then README Write, then verification + commit.

Actually all 5 writes are independent (I have all content planned). But README is a full rewrite via Write (I've read it, state current). Fine to do all in sequence. Let me batch: TodoWrite, then 4 docs writes in one block, then README write, then bash verify + commit.

For verification: grep the new README for remaining heavy detail (should be gone), check all relative links resolve (simple script), wc -l. Then commit all 5 files.

好，开始动手。先建个任务清单，然后写四个 docs 文件，最后瘦身 README。

### **Assistant**
Four docs files created. Now rewrite the README slim version.

四个 docs 文件已建好。现在写瘦身版 README：

### **Assistant**
Now verify:
1. All relative links in the 5 files resolve to existing files.
2. Key facts still present across the doc set (the grep token check).
3. README line count.

Then commit.

README 已收敛。现在校验所有文档内的相对链接是否有效、关键事实是否在文档集内无遗漏，然后提交：

### **Assistant**
All key facts present, no missing tokens, links all valid. README went from 265 → 145 lines (with the detail now in docs/). Total doc set is 307 lines but README itself is the front door at 145.

Wait, my target was ~100-110 lines for README, it's 145 — the 项目结构 tree (30 lines) and quick start contribute. That's fine; the plan said "收敛到约 100 行" — 145 is close enough given I kept 项目结构 and 技术栈 as agreed. Good.

Now commit. Only the 5 files (README.md + 4 docs). data/localquant.db is modified but must not be committed.

校验全部通过：链接无断链，30+ 个关键事实（API 路径、参数名、约定条目）在文档集内无缺失。提交：

### **Assistant**
Done. Final summary for the user:
- What was done: 4 new docs files + slim README
- README now 145 lines (from 265)
- Structure of new README
- Verification done
- Commit 72ec390 on develop

完成，已提交 `72ec390` 到 develop。README 从 265 行收敛到 145 行，详细内容全部搬入 docs/，事实零删减。

**现在的 README** 只回答门面问题：简介 + 投资边界 → **功能总览**（12 行一句话表格，表格下方一行链接指向详单）→ 快速开始（沙箱压缩为 5 行）→ 技术栈 → 项目结构 → **文档导航**（新增小节）→ License。xtquant 仅 Windows 这类一句话提醒并入了环境要求。

**新增的四个文档**：

| 文件 | 行数 | 承接内容 |
|---|---|---|
| [docs/功能模块.md](/Users/victor/Desktop/coding/localquant/docs/功能模块.md) | 97 | 12 个模块的完整功能清单（原功能模块小节整体迁入） |
| [docs/严谨性与工程约定.md](/Users/victor/Desktop/coding/localquant/docs/严谨性与工程约定.md) | 24 | 研究口径 9 条 + 行情来源/执行加固/访问安全/空数据错误/工程检查 |
| [docs/自定义节点.md](/Users/victor/Desktop/coding/localquant/docs/自定义节点.md) | 26 | 自定义节点指南（含代码示例与安全提示） |
| [docs/代码执行沙箱.md](/Users/victor/Desktop/coding/localquant/docs/代码执行沙箱.md) | 15 | 沙箱机制、启用步骤、状态查询 |

搬家时同步修正了跨文档引用：docs 内的“因子编写指南”链接改为同目录相对路径，策略回测/QUBE 里的“见顶部投资边界”指向 README，事件研究/除权事件的口径引用指向严谨性与工程约定文档。

提交前做了两项校验：全文档 34 个相对链接无断链；30+ 个关键事实（`leverage_summary`、`import-reference`、`attribution-run`、`provenance`、`@work_node` 等）在文档集内逐项 grep 确认无缺失。原来上次修改遗留的 `data/localquant.db` 工作区改动仍未纳入提交。
