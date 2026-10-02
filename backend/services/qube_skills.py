"""QUBE 技能库 — 内置技能 seed 数据（精选自公开量化技能社区，标注来源）

来源：
- QuantSkills (https://www.quantskills.ai)：因子研究全流程 + 分析师两类热门技能，
  内容取自各技能详情页 README 与社区实测文章（GPL-3.0），url 指向详情页。
  因子线覆盖：方向/风险形态因子库 → 挖掘工作流 → 生产工厂 → 体检评估 →
  正交化 → 衰减 → 合并 → 诊断优化 → 回测过拟合检查。
- LLMQuant (https://github.com/LLMQuant/skills)：18 个金融大类 Agent Skills（MIT）。

seed 策略：每次启动清空 builtin=1 的旧内置行再写入（用户自建技能不受影响）。
手册（prompt）需自包含：GitHub 原文抓取失败时（离线/网络受限），agent 仅凭手册也能执行。
"""

import json
import time

from backend.database import get_db

# (name, display_name, category, category_id, description, prompt(详细内容 markdown), source, url, stars, repo_url)
QUANTSKILLS_SKILLS: list[tuple] = [
    (
        "qs-factor-decay",
        "因子衰减分析",
        "因子",
        "factor",
        "多期限 Rank IC 衰减曲线 → 指数/幂律/双指数拟合 → Bootstrap 半衰期置信区间 → 换手衰减 + Q5-Q1 分组收益衰减 → 推荐最优再平衡频率。",
        """## 这个技能解决什么问题

回答量化研究中的核心问题：**这个因子能用多久、多久该换一次**。

IC = 0.05 的因子，在 1 天、5 天、20 天持有期上预测力如何变化？
- IC(1d)=0.05, IC(20d)≈0 → 信号衰减快，需要每日调仓
- IC(1d)=0.05, IC(20d)=0.04 → 信号持久，可以月频调仓
- IC(1d)=-0.02, IC(20d)=+0.05 → **方向反转**：短期反转 + 长期动量

不做衰减分析，你不知道最优持有期——要么过度交易、要么错过 Alpha。

## 7 步分析流程

1. 校验输入：signal [date×symbol] + forward returns [date×symbol×horizon]
2. 计算各期限 Rank IC 序列（Spearman）
3. 拟合 IC 衰减曲线（指数 / 幂律 / 双指数）
4. Block Bootstrap (1000次) 估计半衰期 τ₀.₅ 的 95% 置信区间
5. 换手率衰减（日换手率随再平衡间隔的变化）
6. 分组收益衰减（Q5−Q1 spread 随持有期的变化）
7. 输出 DecayReport（JSON + 文本报告）

## 方向反转（A 股常见）

短期 IC 为负（均值回复）、中长期 IC 为正（动量延续）不是 bug，而是真实的因子结构。
单边衰减 → 标准拟合；方向反转 → 降级为非参数并分别标注各 horizon 的 IC 符号；纯噪声 → 标记为不可用。

## 管线定位

因子挖掘 → 因子评估 → 正交化 → **衰减分析(本技能)** → 因子合并 → 回测。
正交化之后、多因子合并之前的质量把控节点；衰减过快的因子不适合低频合并。

作者 lionjiadong · GPL-3.0 · `git clone https://github.com/quantskills/skill-factor-decay.git`""",
        "QuantSkills",
        "https://www.quantskills.ai/skills/skill-factor-decay",
        1,
        "https://github.com/quantskills/skill-factor-decay",
    ),
    (
        "qs-directional-alpha",
        "方向类因子库（296 个 OHLCV 因子）",
        "因子",
        "factor",
        "296 个独立 OHLCV 因子 Skill：趋势/动量/突破/反转/通道五大类，A 股 98 只 + 美股 50 只真实行情验证 296/296 全部通过。",
        """## 仓库内容

QuantSkills 组织的方向类因子库，收录刻画价格方向、趋势延续、突破、反转和通道位置的 OHLCV 因子：

| 类别 | 数量 | 说明 |
|---|---|---|
| Trend 趋势 | 148 (50%) | 均线偏离、EMA 差、趋势强度、趋势效率 |
| Momentum 动量 | 50 (17%) | 收益动量、跳期动量等方向延续信号 |
| Breakout 突破 | 48 (16%) | 上轨突破、下轨跌破等突破状态 |
| Reversal 反转 | 25 (8%) | 收益反转类信号 |
| Channel 通道 | 25 (8%) | 区间位置、通道内相对位置 |

## 单因子结构

每个因子是独立 Skill 文件夹（如 `R001-5d-z-scored-return-momentum/`），含 SKILL.md、`scripts/factor.py`（`compute_factor(df)`）、`scripts/validate.py` 自检、`validation_real/` 真实行情验证结果、`references/formula.md` 公式说明。

## 数据要求与验证口径

只依赖标准 OHLCV 字段 `date, symbol, open, high, low, close, volume`。
验证：A 股 98 只 + 美股 50 只，样本 2021-01-04 → 2026-06-10，**296/296 全部通过**；指标含覆盖率、5 日 Rank IC、ICIR、五分组 Q5-Q1 收益差、Top 组换手率、无未来函数检查。

## 姊妹仓库（QuantSkills 因子库全家桶）

- 🧭 directional-alpha — 方向类（本仓库）
- 🛡️ risk-pattern-alpha — 波动率 · K线形态 · 震荡 · 回撤
- 📊 volume-stat-alpha — 成交量 · 量价 · 流动性 · 时序排名 · 收益分布

作者 abgyjaguo · GPL-3.0 · `git clone https://github.com/quantskills/skill-quant-factor-directional-alpha.git`""",
        "QuantSkills",
        "https://www.quantskills.ai/skills/skill-quant-factor-directional-alpha",
        1,
        "https://github.com/quantskills/skill-quant-factor-directional-alpha",
    ),
    (
        "qs-factor-mining",
        "因子挖掘（研报/论文 → 可回测因子）",
        "因子",
        "factor",
        "从研报、论文、PDF、DOCX 等文档中提取量化因子假设，转换为可执行公式，支持创建、回测与分析。",
        """## 这个技能做什么

从公开研报、论文、PDF、DOCX 或文本中**提取量化因子假设**，将其转换为可执行的因子公式，并可选择创建、回测和分析。

示例请求：

```
从这篇论文中提取三个可复现的 A 股因子，
先列出公式、方向、参数和假设，不要立即运行回测。
```

技能会先提取因子逻辑和来源，再核对公式约束；只有用户明确要求执行时，才会真正创建或回测因子。

## 研究边界（重要）

- 数据来源：A 股日频数据；实际字段与覆盖范围以平台为准
- 默认参数：约 60 天回测区间、10 个分组、1 日调仓——正式研究应显式设置日期与调仓周期
- 已知限制：公式语法差异、短样本、数据窥探、交易成本和可交易性处理均可能影响结果
- **回测结果是历史诊断，不代表未来收益，不构成投资建议**

## 安全提示

使用交互式登录，不要把手机号、密码、Token 或配置文件内容写入提示词、命令历史、示例或仓库。

原作者 TerribleCookie，QuantSkills 迁移维护 · GPL-3.0（上游 MIT）· `git clone https://github.com/quantskills/skill-factor-mining-pandaai.git`""",
        "QuantSkills",
        "https://www.quantskills.ai/skills/skill-factor-mining-pandaai",
        0,
        "https://github.com/quantskills/skill-factor-mining-pandaai",
    ),
    (
        "qs-serenity-model",
        "Serenity 投研模型（公开帖子逆向研究）",
        "分析",
        "analyst",
        "从公开 X 帖子里逆向研究逻辑：extract → clean → auto-review → evaluate → report 五段流水线，把帖子拆成最小信号单元，并用价格数据回看公开 call 的后续表现。",
        """## 这是什么

把交易员 Serenity（@aleabitoreddit）的**公开 X 帖子**重构成可复用的研究模型。目标不是验证私人收益或跟单，而是**逆向公开帖子里可观察的推理模式**，并检验这些公开信号事后的价格表现。

## 五段流水线

```
extract   帖子导出(csv/json/jsonl/txt/md) → 归一化信号表
clean     cashtag 白名单过滤 → 生成复核队列（引用/免责/反讽/无 ticker 贴）
auto-review  套用语义标签：引用贴 · 历史战绩 · 众包 watchlist · 活跃 thesis
evaluate  1/5/20/60/120 交易日前向收益 + 最大回撤
report    画像 · 逻辑树 · 证据图 · 风险图 → serenity_model_report.md
```

每条信号在最小单元上分解：ticker、主题/子主题、瓶颈论断、供应链角色、证据类型、催化、时间窗、风险标记、信心信号、跟进/修正关系。

## 核心约束

- 🌐 只用公开材料，记录来源与抓取日期
- 🧾 收益声明不背书：截图、粉丝量、病毒式回报数字一律标「未验证」
- ✂️ 引用与本人观点分离；⚖️ 失败/被修正的观点与成功观点同等入库（防赢家偏差）
- 📉 研究贴 ≠ 拉盘贴：病毒式传播本身可能成为催化，单独标记
- 🚫 只述不荐：输出研究结构与事实归纳，不构成任何投资建议

其通用化版本是姊妹仓库 skill-x-trader-builder（把任意公开交易员账号逆向成研究模型）。

作者 songshuquant 等 4 人 · GPL-3.0 · `git clone https://github.com/quantskills/skill-serenity-research-model.git`""",
        "QuantSkills",
        "https://www.quantskills.ai/skills/skill-serenity-research-model",
        4,
        "https://github.com/quantskills/skill-serenity-research-model",
    ),
    (
        "qs-stock-dossier",
        "A股个股档案（一键尽调报告）",
        "分析",
        "analyst",
        "输入一个 A 股代码，输出一份可溯源的中文个股尽调报告：基本面、分红资本运作、股东行为、质押解禁减持风险、资金面，一次查清。",
        """## 这是什么

对单只 A 股（如 `000001.SZ`）做**一键尽调**：把分散的 25+ 个数据接口按 5 个数据阶段串成流水线，叠加 10 条分级风险规则，产出 9 章结构化报告——**每个结论都标注来源接口、报告期和查询窗口**。

## 五个数据阶段

| 阶段 | 回答什么 |
|---|---|
| 🏢 公司画像 | 这是家什么公司？股本结构？有无 ST 历史？ |
| 📊 财务报表 | 营收/利润/现金流趋势？预告变脸？审计非标？ |
| 💸 分红与资本运作 | 回报股东还是频繁抽血？ |
| 👥 股东与事件风险 | 筹码集中度？减持计划？质押率？未来解禁压力？ |
| 💹 资金面 | 量价异动？席位资金？北向进出？ |

## 风险规则引擎（组合信号是核心）

单看质押率或解禁日历都不可怕，**叠加才是雷区**：
- 🔴 高风险：ST/*ST；审计非标；质押率 ≥50%；90天内解禁 >流通盘10%；`减持计划 + 业绩预告下修`
- 🟡 中风险：质押率 30%–50%；解禁占流通盘 5%–10%；股东户数 +20% 且股价滞涨；连续3年不分红 + 频繁再融资
- 🟢 低风险：孤立小额事件 → 附录备查

## 报告结构（固定 9 章）

摘要与结论 → 公司概况 → 财务分析 → 分红与资本运作 → 股东结构与变动 → 风险事件 → 资金面 → 风险信号清单 → 数据附录

核心约束：公式透明（衍生指标写出公式与字段名）、同期对比、空数据如实报、措辞克制（不下涨跌结论）。

示例提问：`给 000001.SZ 做一份个股体检报告` / `帮我尽调隆基绿能，重点看质押和解禁`

作者 abgyjaguo · GPL-3.0 · `git clone https://github.com/quantskills/skill-a-share-stock-dossier.git`""",
        "QuantSkills",
        "https://www.quantskills.ai/skills/skill-a-share-stock-dossier",
        3,
        "https://github.com/quantskills/skill-a-share-stock-dossier",
    ),
    (
        "qs-smart-money",
        "主力资金画像（席位/北向行为追踪）",
        "分析",
        "analyst",
        "龙虎榜席位身份识别与画像档案、北向资金跨期行为、北向×机构×融资×大宗的多源资金合力与分歧，输出可溯源的资金主体行为画像报告。",
        """## 这是什么

不预测涨跌，只回答两件事：**谁在买卖**，以及**他们一贯怎么做**。把龙虎榜席位、北向资金、融资盘、大宗买方串成"资金主体身份识别 + 跨期行为画像"。

## 三大支柱

1. **席位身份与画像**：龙虎榜上的"机构专用"、"深股通专用"、知名游资营业部归类成身份标签；每个席位累积画像档案——上榜频次、累计净买卖、上榜后 5/10/20 日胜率、平均持有/退出周期、偏好板块
2. **北向跨期行为**：加/减仓 streak、持股集中度变化、板块轮动迁移、与指数背离、持续建仓 vs 短期博弈
3. **资金合力/分歧**：北向 × 机构席位 × 融资盘 × 大宗买方四路方向叠加
   - ≥3 路同向买入 → 🟢 资金合力榜
   - 一路买一路卖量级相当 → 🟠 资金分歧榜（对打）
   - ≥2 路无数据 → ⚪ 证据不足（不强下结论）

## 核心约束

- 🏷️ 身份是推断：席位标签来自规则匹配，明确标注"非官方认定"
- 🧮 公式透明：净买卖、上榜后 N 日收益、胜率、持有周期、streak 长度写出口径
- 🤝 列全四路：合力/分歧结论列出全部四路方向，含"无数据"的路
- 🗣️ 措辞克制：用"可能提示""同向/对打"，不下涨跌结论

示例提问：`给 000001.SZ 做一份资金主体画像` / `画像一下"机构专用"席位的上榜后10日胜率` / `列一下最近活跃的知名游资席位和偏好板块`

作者 abgyjaguo · GPL-3.0 · `git clone https://github.com/quantskills/skill-smart-money-profiler.git`""",
        "QuantSkills",
        "https://www.quantskills.ai/skills/skill-smart-money-profiler",
        1,
        "https://github.com/quantskills/skill-smart-money-profiler",
    ),
    (
        "qs-factor-evaluate",
        "因子体检（七项指标+六维主分）",
        "因子",
        "factor",
        "给定 [date×symbol] 截面信号：契约校验 → Rank IC 与 Pearson IC 双对照 → 多头回测 → 分组单调性 → 换手率 → 六维主分，输出标准化体检报告。因子体检仪，不是回测引擎。",
        """## 这个技能解决什么问题

新手最常见的反模式是「只跑一个回测收益率就下结论」。本技能把因子评价固化成标准流程：
从**有效性、风险收益、稳健性、换手成本**四个维度给单个因子做「完整体检」，
输出七项指标 + 一个可比的六维主分——像面试官一样判断这个因子值不值得继续深入。

## 输入 / 输出

- 输入：`[date × symbol]` 截面信号面板（不自带行情，需自备 OHLCV）
- 输出：标准化七项体检报告 + 六维主分（主分可比、可排序、可追踪）

## 六步体检流程

1. **校验信号契约**：截面规模、缺失率、均值分布是否合格
2. **双 IC 对照**：Rank IC 与 Pearson IC 一起算，一眼看出线性相关还是极端值主导
3. **多头回测**：T+1 开盘买 Top 10% 等权，双边手续费 15bp，T+1+H 卖出
4. **分组单调性**：5 或 10 分位，Spearman 检验「高分组 vs 低分组」是否一致趋势
5. **年化换手率**：评估策略容量与成本，换手过高在主分中施加惩罚
6. **主分公式 v2**：原始指标先压缩到 [-2, +2] 再归一加权，不同因子可同台比较

## 使用边界

- 换市场要重设假设：A 股记得处理涨跌停、停牌；美股按实际交易机制调整费率
- 主分只在同口径（市场/窗口/成本假设）下可比，不是跨市场绝对排名
- 实测示例：20 日动量在 3 只美股样本上被评出 score=-1.295——负分恰恰说明评分体系在正常工作

## 管线定位

因子挖掘 → **评估(本技能)** → 正交化 → 衰减分析 → 合并 → 回测。评价结果可直接喂给 factor-blend。

QuantSkills 社区 · GPL-3.0 · `git clone https://github.com/quantskills/skill-factor-evaluate.git`""",
        "QuantSkills",
        "https://www.quantskills.ai/skills/skill-factor-evaluate",
        1,
        "https://github.com/quantskills/skill-factor-evaluate",
    ),
    (
        "qs-factor-mine",
        "因子挖掘工作流 SOP（单点假设实验法）",
        "因子",
        "factor",
        "把「加一个新因子」拆成可重复、可归因、可回滚的标准动作：单点假设原则 + 5 步闭环 + 信号契约 + 相关性门控 + ITER_NOTE 四字段。工作流 SOP，不是因子库。",
        """## 这个技能是什么

**不是因子库，是工作流 SOP。** 解决「想法太多、改得太杂，最后不知道哪一步起作用」的问题。
核心规则是**单点假设原则**：每轮只改一件事——同时改因子、改组合方法、改标签，
涨了跌了都不知道是谁干的。

## 5 步闭环（每轮实验）

1. **读宪法**：evaluation.md（评分公式）与 program.md（研究方向）是唯一依据，不读不许提假设
2. **写 ITER_NOTE**：四字段必填 `op_type / hypothesis / change / expected`，缺一不能跑
3. **改代码**：一次只改一个 op_type，范围锁死
4. **跑验证**：runner.once 看 score 升降
5. **归档/回滚**：ACCEPTED 归档；REJECTED / CRASH 回滚，不怕搞砸

ITER_NOTE 会被强制校验：`hypothesis="试试看"`、`expected="提升"` 这类含糊表述会被判不合格——
本质是逼你把「我想试试」翻译成「基于什么假设、改了什么、预期效果在什么区间」。

## 信号契约（必须项）

因子信号必须做**截面 MAD winsorize + z-score**：处理后截面均值严格为 0、标准差严格为 1。
标准化让不同因子可比，避免量纲和极端值带来的伪相关。

## 相关性门控

新因子与已有因子 Spearman |ρ| ≥ 0.85 **直接拒绝**（0.60 软警告）——自动拦截「换皮因子」。

## 因子族起点

factor-families.md 按 Phase 1~3 列出 11 个典型因子表达式：动量/反转、波动率/低波、
流动性、量价相关、形态/lottery，全部经过信号契约验证、拿来就能算，适合做变体和组合的起点。

QuantSkills 社区 · GPL-3.0 · `git clone https://github.com/quantskills/skill-factor-mine.git`""",
        "QuantSkills",
        "https://www.quantskills.ai/skills/skill-factor-mine",
        1,
        "https://github.com/quantskills/skill-factor-mine",
    ),
    (
        "qs-factor-blend",
        "多因子合并（去冗余→加权→合成信号）",
        "因子",
        "factor",
        "输入多个同口径已评价截面因子：相关矩阵去冗余（默认阈值 0.7）→ 等权/ICIR/Score 三种加权 → 逐日截面 z-score 合成 composite_signal。信号层合并，不做资金分配。",
        """## 这个技能解决什么问题

手头攒了一堆因子（动量、反转、波动率、换手率……）每个都「有点道理」：全用怕信息重复，
只挑一个又浪费预测力。本技能把「去冗余 → 加权 → 合成」整条链路封装成标准 8 步工作流，
从多个因子生成一个干净、可解释的复合 Alpha 信号。

**核心理念**：这是**信号层合并**（产出 composite_signal[date×symbol]），不是组合层资金分配。

## 8 步工作流

校验输入 → 读取评价 → 过滤因子 → 计算相关矩阵 → 去冗余 → 选择权重 → 生成复合信号 → 重新评价

- **去冗余**：因子间 rank 相关超过阈值（默认 0.7，`--corr-threshold` 可调）自动剔除重复信号
- **合成**：逐日截面 z-score 标准化，输出可直接接入选股/组合构建的复合信号

## 三种加权方案

| 方案 | 逻辑 | 适合 |
|---|---|---|
| equal | 去冗余后平分权重，默认基准 | 因子少、质量接近 |
| ICIR | 按 ICIR 分配，预测力强的话语权大 | 追求 IC 稳定性 |
| score | 综合 ICIR+覆盖率+换手率 | 日常研究推荐 |

## 用法与产物

```
python scripts/blend.py --factor-dir data/factors --weight score
```

输入要求：同一口径、**已完成评价**的截面因子（parquet）。交互模式先展示方案与质量速览再执行。
产物：composite_signal + combine_state.pkl（中间状态）+ combine_report.json（诊断报告），可复现可回溯。

## 管线定位

factor-evaluate（体检）→ factor-decay（衰减）→ **blend(本技能)** → 组合构建。
实测中 ICIR/Score 加权显著优于等权，且换手率保持在合理区间。

QuantSkills 社区 · GPL-3.0 · `git clone https://github.com/quantskills/skill-factor-blend.git`""",
        "QuantSkills",
        "https://www.quantskills.ai/skills/skill-factor-blend",
        1,
        "https://github.com/quantskills/skill-factor-blend",
    ),
    (
        "qs-factor-optimize",
        "因子诊断（KEEP/REFINE/REJECT）",
        "因子",
        "factor",
        "给已有因子做标准化体检：Period Sweep 扫参数 → Ablation 拆组件 → Refinement 增强 → 输出 KEEP/REFINE/REJECT 结论。因子诊断器，不是因子生成器。",
        """## 这个技能解决什么问题

从研报抄的公式回测挺美、实盘就亏？本技能不发明新因子，只做**已有因子的诊断、优化和
baseline 选择**：扫参数、拆组件、测稳健性，最后必须告诉你：保留、优化、还是放弃。

## 四个最常见的坑

- **美股公式，A 股噪声**：市场结构不同，套利空间已被压缩
- **240 日窗口饿晕**：3 年数据上 warm-up 太长，利用率过低
- **样本量不够**：行业 zscore 在 3-4 只/行业时噪声爆炸
- **方向反了**：以为是均值回归，数据跑的是动量

## 六步诊断链路

1. **Period Sweep**：扫核心 period 参数，优先稳健区间而非单点最高值
2. **Best Period 选择**：综合主指标、相邻稳定性、换手与风险权衡
3. **Ablation**：拆出可解释组件，分类 core / helpful / risk_control / cosmetic / harmful
4. **Refinement**：从 best period + core 出发增强，不造新因子
5. **最终报告**：optimize_report.md 把原始版、最佳参数版、核心版、优化版放一起对比
6. **结论**：KEEP / REFINE / REJECT（每份报告必须给）

## 三条红线

- 不编造数据：缺失指标直接报 BLOCKED
- 不覆盖源码：Refinement 只生成建议，推广需用户确认
- 必须给结论：keep / refine / reject 三选一

## 用法

```
python scripts/init_optimize_folder.py ./momentum_factor --factor-name momentum \\
  --engine "skills.backtest + skills.report" --data "A-share daily, 2018-2024, HS300"
```

产物集中在 optimize_tests/ 目录（00_manifest.json + period_sweep/ + ablation/ + refinement/ + 报告），不污染原始因子代码。核心指标三个：IC、Sharpe、Turnover。

QuantSkills 社区 · GPL-3.0 · `git clone https://github.com/quantskills/skill-factor-optimize.git`""",
        "QuantSkills",
        "https://www.quantskills.ai/skills/skill-factor-optimize",
        1,
        "https://github.com/quantskills/skill-factor-optimize",
    ),
    (
        "qs-risk-pattern-alpha",
        "风险与形态因子库（288 个 OHLCV 因子）",
        "因子",
        "factor",
        "288 个独立 OHLCV 因子 Skill：波动率、K 线形态、振荡指标、回撤压力四大方向，每个因子带独立实现与验证入口。directional-alpha 的姊妹仓库。",
        """## 仓库内容

QuantSkills 组织的风险与形态因子库，收录 288 个独立的 OHLCV 因子，
覆盖四个方向：**波动率、K 线形态、振荡指标、回撤压力**。
每个因子都有独立实现和验证入口，可直接计算因子值，也可挑选候选接入自己的评价或组合流程。

## 验证口径

2026-07 历史测试：5 只美股近两年数据，抽取 15 个代表性因子——15/15 全部运行，
样本覆盖率 > 98.5%。该结果只说明当次样本的运行与覆盖情况，**不代表 288 个因子在其他
市场、时间窗口或策略中都有效**。

## 数据要求

只依赖标准 OHLCV 字段 `date, symbol, open, high, low, close, volume`。

## 姊妹仓库（QuantSkills 因子库全家桶）

- 🧭 directional-alpha — 方向类（趋势/动量/突破/反转/通道，296 个）
- 🛡️ risk-pattern-alpha — 风险与形态（本仓库）
- 📊 volume-stat-alpha — 成交量 · 量价 · 流动性 · 时序排名 · 收益分布

使用边界：因子被收录、脚本通过验证或历史 IC 有表现，都不能直接推出未来收益。

QuantSkills 社区 · GPL-3.0 · `git clone https://github.com/quantskills/skill-quant-factor-risk-pattern-alpha.git`""",
        "QuantSkills",
        "https://www.quantskills.ai/skills/skill-quant-factor-risk-pattern-alpha",
        1,
        "https://github.com/quantskills/skill-quant-factor-risk-pattern-alpha",
    ),
    (
        "qs-factor-factory",
        "因子生产工厂（批量生成+验证+打包）",
        "因子",
        "factor",
        "输入标准 OHLCV 数据和一批因子设定：批量完成特征生成、截面标准化、基础验证，并把每个因子打包成独立 Skill（文档+代码+验证脚本+结果）。批次层面生成索引与汇总报告。",
        """## 这个技能是什么

**因子生产工厂**：不是现成因子库。输入一份标准 OHLCV 数据和一批因子设定后，
批量完成特征生成、截面标准化和基础验证，再把每个因子分别打包成可运行的独立 Skill。

## 交付物

每个因子目录保留：说明文档、调用说明、可运行的计算代码、验证脚本、验证结果；
批次层面还有索引与汇总报告。因子公式、代码、文档和验证**一起交接**，
而不是散落在临时脚本里——这是它比「一张结果表」更持久的价值。

## 实测参考

20 只 A 股 2023—2024 年约 9600 行数据，10 个因子及其验证结果约 10 分钟生成
（具体取决于设备、数据和参数）。重复的代码编写、文档整理和初步验证被统一成可复跑的交付格式。

## 使用边界

它负责**生产和验证因子 Skill**，不负责证明这些因子能形成策略；
不替代组合、交易成本和收益判断。验证通过 ≠ 未来有效。

## 与平台工作流衔接

批量产物接入平台：公式类因子可直接用 generate_stock_factor_code 逐个写入画板 →
run_factor_analysis 验证 → 达标的 save_factor_to_library 入库。

QuantSkills 社区 · GPL-3.0 · `git clone https://github.com/quantskills/skill-quant-factor-skill-factory.git`""",
        "QuantSkills",
        "https://www.quantskills.ai/skills/skill-quant-factor-skill-factory",
        1,
        "https://github.com/quantskills/skill-quant-factor-skill-factory",
    ),
    (
        "qs-factor-orthogonalize",
        "因子正交化（逐日 OLS 剥离已知暴露）",
        "因子",
        "factor",
        "对截面因子逐日做 OLS 回归，剥离行业、市值、Beta、波动率、旧因子等已知暴露，用残差生成新因子，并输出暴露、IC 保留率、换手、覆盖率诊断。",
        """## 这个技能解决什么问题

因子跑出 IC 之后先问一句：**这里面有多少是行业/市值/风格暴露贡献的？**
本技能逐日进行截面 OLS 回归，把原始因子对行业、市值、Beta、波动率和旧因子等
变量的暴露剥离，使用**残差**生成新的因子值。

## 输出

- 残差因子（新因子值）
- 暴露诊断：暴露、IC 保留率、换手、覆盖率——方便检查清理前后发生了什么

## 实测参考

200 只模拟股票 × 100 交易日：正交化后因子与三类风格变量的相关性降到 0.001 以下。
这说明当时设置下的暴露剥离确实完成；**但不能证明残差一定是「纯 Alpha」，
也不能保证 IC 或实际收益随之提高**。

## 使用边界

- 适合场景：已有因子疑似依赖行业、规模或风格时，先把暴露和残差信号分开检查
- 正交化改变的是**信号解释**，不是自动增强收益

## 管线定位

因子挖掘 → 评估 → **正交化(本技能)** → 衰减分析 → 合并。
与 factor-blend 的分工：正交化清洗单个因子内部的已知暴露；合并处理多个信号之间的信息重复。

QuantSkills 社区 · GPL-3.0 · `git clone https://github.com/quantskills/skill-factor-orthogonalize.git`""",
        "QuantSkills",
        "https://www.quantskills.ai/skills/skill-factor-orthogonalize",
        1,
        "https://github.com/quantskills/skill-factor-orthogonalize",
    ),
    (
        "qs-backtest-overfit",
        "回测过拟合检查（DSR/PBO/折减）",
        "回测",
        "backtest",
        "评估回测过拟合与多重检验风险：输入被选中策略的收益序列并如实提供试验次数，用 DSR、PBO、Haircut Sharpe（Harvey-Liu 折减）和 MinTRL 检查「好看的结果是不是试出来的」。",
        """## 这个技能解决什么问题

多次挖因子、调参数之后留下的「最佳结果」，很可能只是**试出来的**。
本技能针对这种选择偏差：输入被选中策略的收益序列，并**如实提供**试验次数或试验矩阵，
用四个工具分别检查不同维度的过拟合风险。

## 四件套

| 工具 | 检查什么 |
|---|---|
| DSR (Deflated Sharpe) | 选择偏差：扣掉「从 N 次试验里挑最好」的水分后的 Sharpe |
| PBO | 样本内外排名一致性：回测最优的参数在样本外还靠谱吗 |
| Haircut Sharpe | Harvey-Liu 多重检验折减：多重比较后的夏普该打几折 |
| MinTRL | 最低样本长度：当前 Sharpe 需要多少年数据才可信 |

## 实测参考（对照实验）

- 纯噪声案例：从 200 个策略里挑出的年化 Sharpe 高达 **1.65**，但 DSR 只有 **0.63**——原形毕露
- 注入日漂移的对照案例：DSR 升到 **0.98**——真实的持续性信号能通过检查

共 23 项检查。这个对照展示了工具怎样区分「看起来很好」和「在当前假设下通过统计检查」。

## 使用边界

- 当前在 QuantSkills 官方资产目录中标记为 L1 Listed / **draft**
- 能检查多重试验和选择偏差，**不能**发现幸存者偏差、数据前瞻、交易成本拟合——
  这些仍需回到数据、样本构造和研究过程人工复核
- 结论是统计检查通过与否，不构成对未来收益的任何承诺

## 管线定位

放在研究流程最后一步：因子挖掘 → 评估 → 合并 → 回测 → **过拟合检查(本技能)**。
凡是「试了很多组参数后选出的最好结果」，入库/上线前都应过一遍。

QuantSkills 社区 · GPL-3.0 · `git clone https://github.com/quantskills/skill-backtest-overfit.git`""",
        "QuantSkills",
        "https://www.quantskills.ai/skills/skill-backtest-overfit",
        1,
        "https://github.com/quantskills/skill-backtest-overfit",
    ),
]

# LLMQuant/skills 18 个大类（MIT；npx skills add LLMQuant/skills 可一键安装）
# (name_suffix, display_name, description, workflows)
LLMQUANT_CATEGORIES: list[tuple[str, str, str, str]] = [
    (
        "data",
        "LLMQuant Data 基础数据",
        "LLMQuant Data 基础数据和有来源的研究。",
        "10-K 风险审查、13F 持有人、美国宏观快照、宏观简报",
    ),
    (
        "equities",
        "股票研究",
        "股票研究、横向比较、估值、催化剂和卖出纪律。",
        "Five-lens analysis、equity compare、research memo、merger arb、take-profit lab",
    ),
    ("etfs", "ETF 分析", "ETF 持仓、重叠、集中度和敞口分析。", "ETF overlap report"),
    (
        "options",
        "期权与波动率",
        "期权、波动率、Greeks、异常交易和期权回测。",
        "IV rank、strategy builder、Greeks dashboard、P&L simulator、volatility surface",
    ),
    (
        "equity-derivatives",
        "个股衍生品",
        "单只股票的衍生品和混合证券研究。",
        "Single-stock derivative playbook、convertible and warrant lens",
    ),
    (
        "commodities",
        "商品期货",
        "商品现货、期货曲线、库存和宏观联动。",
        "Commodity market lens、futures curve monitor",
    ),
    (
        "crypto",
        "加密市场",
        "加密市场行情、代币研究、永续资金费率、基差和杠杆监控。",
        "Crypto market regime、token research、perp funding monitor",
    ),
    (
        "prediction-markets",
        "预测市场",
        "事件赔率、预测市场合约、概率差和跨平台套利检查。",
        "Event probability brief、arb watch、probability vs options pricing",
    ),
    (
        "macro",
        "宏观研究",
        "宏观面板、央行会议前瞻、流动性、增长、通胀和组合影响。",
        "Global macro dashboard、Fed policy preview、macro-to-portfolio impact",
    ),
    (
        "credit",
        "信用研究",
        "发行人信用、利差行情、高收益压力、再融资和违约风险。",
        "Issuer credit risk review、credit spread regime、high-yield stress monitor",
    ),
    (
        "rates-fx",
        "利率与外汇",
        "利率、收益率曲线、央行分化、外汇 carry 和汇率风险。",
        "Yield curve trade lens、central-bank divergence、FX carry dashboard",
    ),
    (
        "events",
        "事件跟踪",
        "财报、并购、监管、法律、政策和催化剂事件跟踪。",
        "Earnings event brief、M&A event tracker、regulatory risk monitor",
    ),
    (
        "portfolio",
        "组合管理",
        "公司档案、观点跟踪、关注列表、提醒和主题研究。",
        "Company profile、thesis tracker、theme research、watchlist monitor、alert manager",
    ),
    (
        "portfolio-lab",
        "组合实验室",
        "组合敞口图、假设推演和虚拟组合状态。",
        "Portfolio exposure map、portfolio what-if simulator",
    ),
    (
        "risk",
        "风险监控",
        "风险行情、对冲、恐慌打分和研究质量检查。",
        "Fear score、VIX status、hedge advisor、research health check",
    ),
    (
        "strategies",
        "策略手册",
        "对冲基金和基金经理的策略手册。",
        "Equity long/short、long-biased、event-driven、macro、quant、multi-strategy",
    ),
    (
        "market-intelligence",
        "市场情报",
        "可复用的市场工具和信号视图。",
        "Macro view、market sentiment、event probability signals",
    ),
    (
        "investor-lenses",
        "投资大师视角",
        "用数据当证据的投资大师视角分析。",
        "Buffett、Graham、Munger、Lynch、Fisher、Burry、Ackman、Damodaran 等",
    ),
]


def _llmquant_prompt(display: str, desc: str, workflows: str) -> str:
    return f"""## {display}

{desc}

**主要 workflows**：{workflows}

## 关于 LLMQuant Skills

面向金融的可复用 Agent Skills（共 18 个大类，覆盖股票、期权、宏观、加密、信用、组合、风险等）。
每个大类以 SKILL.md 为入口，列出该类全部流程（workflows/*.md），并要求所有外部事实都有数据来源作为依据。

**安装**（适用于 Claude Code / Codex / Cursor 等多种 Agent）：

```
npx skills add LLMQuant/skills            # 交互挑选
npx skills add LLMQuant/skills -g --all   # 全局安装全部大类
```

数据层为 LLMQuant Data（MCP server，提供价格、财报、13F、宏观、ETF 持仓、加密等数据）；
未连接数据层时技能也可当普通流程用，Agent 会要求你提供数据并标清缺口。

LLMQuant 开源社区 · MIT License · https://github.com/LLMQuant/skills"""


async def seed_builtin_skills() -> None:
    """重建内置技能：清空旧 builtin 行，写入 QuantSkills + LLMQuant 精选（用户自建不受影响）"""
    now = int(time.time())
    db = await get_db()
    try:
        await db.execute("DELETE FROM qube_skills WHERE builtin = 1")
        for (
            name,
            display,
            cat,
            cat_id,
            desc,
            prompt,
            source,
            url,
            stars,
            repo_url,
        ) in QUANTSKILLS_SKILLS:
            await db.execute(
                "INSERT INTO qube_skills (name, display_name, description, category, "
                "category_id, params_json, prompt, builtin, enabled, created_at, source, url, stars, repo_url) "
                "VALUES (?, ?, ?, ?, ?, '[]', ?, 1, 1, ?, ?, ?, ?, ?)",
                (
                    name,
                    display,
                    desc,
                    cat,
                    cat_id,
                    prompt,
                    now,
                    source,
                    url,
                    stars,
                    repo_url,
                ),
            )
        for suffix, display, desc, workflows in LLMQUANT_CATEGORIES:
            await db.execute(
                "INSERT INTO qube_skills (name, display_name, description, category, "
                "category_id, params_json, prompt, builtin, enabled, created_at, source, url, stars, repo_url) "
                "VALUES (?, ?, ?, '综合', 'llmquant', ?, ?, 1, 1, ?, 'LLMQuant', ?, 0, ?)",
                (
                    f"llmquant-{suffix}",
                    f"llmquant-{suffix} · {display}",
                    desc,
                    json.dumps([], ensure_ascii=False),
                    _llmquant_prompt(display, desc, workflows),
                    now,
                    f"https://github.com/LLMQuant/skills/tree/master/skills/llmquant-{suffix}",
                    f"https://github.com/LLMQuant/skills/tree/master/skills/llmquant-{suffix}",
                ),
            )
        await db.commit()
    finally:
        await db.close()
