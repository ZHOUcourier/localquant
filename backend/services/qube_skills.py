"""QUBE 技能库 — 内置技能 seed 数据（精选自公开量化技能社区，标注来源）

来源：
- QuantSkills (https://www.quantskills.ai)：因子/分析师两类热门技能，
  内容取自各技能详情页 README（GPL-3.0），url 指向详情页。
- LLMQuant (https://github.com/LLMQuant/skills)：18 个金融大类 Agent Skills（MIT）。

seed 策略：每次启动清空 builtin=1 的旧内置行再写入（用户自建技能不受影响）。
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
