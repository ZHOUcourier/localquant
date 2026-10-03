# Selection side chat

**Session:** 2026-10-03 14:56 ~ 2026-10-03 14:56

**Work Directory:** `/Users/victor/Desktop/coding/localquant`

**Session ID:** `sess_1bcb3d59-7d09-4131-bbb4-1633efc8b19d`（zcode://sess_1bcb3d59-7d09-4131-bbb4-1633efc8b19d）

**Exported:** 2026-10-03 23:41 · agent-dump 1.1.1

---

### **You**
分钟级高频如何建设。localquant/docs/ref/一个30分钟价量熵 这个因子不错，可以把它加进来（分钟级高频）。这个是来自 quantzone ，这个平台似乎对高频因子颇有研究。解释的时候，请完善解释一下整个分钟级高频流程如何构建。比如，解释我要进行常见的量化，就是需要采用因子投资的方法，即找因子，然后根据这些理论一些模型，验证，回测等等。只说不做

### **Assistant**
The user is asking about how to build minute-level high-frequency (高频) factor infrastructure in their localquant project. They reference a doc at `localquant/docs/ref/一个30分钟价量熵` — a factor doc about "30-minute price-volume entropy" that comes from QuantZone platform. They want me to:

1. Explain how to build the minute-level high-frequency pipeline (only explain, not implement — "只说不做" = "talk only, don't do")
2. Explain the overall quantitative factor investing methodology: find factors, validate with models, backtest, etc.
3. Discuss adding this 30-min price-volume entropy factor as a candidate

So the deliverable is an explanation/assessment, not code. Let me first read the referenced doc and understand the existing project structure to ground my explanation in their actual codebase.

Let me explore:
- The doc file: localquant/docs/ref/一个30分钟价量熵 (need to find exact filename)
- The existing factor framework in localquant to understand how factors are currently computed (daily-level presumably)
- Data infrastructure — do they have minute-level data?

Let me start by looking at the docs/ref directory and the repo structure.

我先读一下你提到的那份价量熵文档，再看看现有因子框架的结构，然后给你讲清楚分钟级高频的建设思路。

### **Assistant**
The file is actually a directory `一个30分钟价量熵` (or a file without extension). Let me look at it.

### **Assistant**
这份文档是 11 张小红书截图（quantzone攻城小队 发的），我先读图理解因子定义，同时派一个探索 agent 摸清项目里现有的分钟线/日内数据能力和因子流水线结构。

The doc is a set of 11 JPG screenshots from 小红书 (Xiaohongshu/RED) posted by quantzone攻城小队. I need to read these images to understand the factor. Let me read them all — that's 11 images. Let me read them in batches.

Also I should look at the existing intraday infrastructure: `intraday_operators.py`, `intraday_cleaner.py`, `market_data.py`, `factor_research.py` — to understand what minute-level data capabilities already exist.

Let me read the images first (they're the key reference), and in parallel explore the codebase structure. Reading 11 images might be a lot of context, but they're necessary to understand the factor. Let me read them in a few batches. Actually, since I need to understand the factor definition deeply, let me read them all but be mindful. Each image is ~300KB jpg.

Let me batch: first 4 images, then continue. Actually I can read multiple in parallel in one block. Let me do 6 first, then 5.

In parallel, I'll dispatch an Explore agent to survey the existing intraday/minute-data capabilities and factor pipeline so I don't burn context reading big files.

### **Assistant**
I've got the first 3 pages of the doc. Key facts so far:

- Factor name: `feat_single_amt_ratio_entropy_30m`
- It's a daily-frequency factor computed FROM minute-level data (intraday aggregation collapsed to daily). So it's actually a "minute-data-derived daily factor" — this matters a lot: you don't need minute-level backtesting infrastructure, just minute data → aggregate → daily factor values → existing daily IC/layered backtest pipeline works.
- Calculation:
  1. Get 1-minute close & volume, clean suspended/no-trade/missing price/abnormal volume minutes
  2. Aggregate 1m → 30m bars (close_30m,b, volume_30m,b where b = intraday 30-min slot index)
  3. price_ratio_b = close_30m,b / Σ close_30m,b; volume_ratio_b = volume_30m,b / Σ volume_30m,b
  4. p_b = price_ratio_b × volume_ratio_b, re-normalize to probability distribution
  5. Entropy = -Σ p_b ln(p_b), 0 when p_b=0
- Backtest: rolling 5/10/20-day mean smoothing, 20-day rolling mean performed best

Let me read the remaining images to get the backtest results (IC, long-short, small-cap vs large-cap behavior — "小票里是猛兽，大票里变绵羊" = beast in small caps, lamb in large caps). Pages 5-12. Let me read them in batches. Pages 5, 6, 7, 8 first, then 9, 10, 11, 12.

前 3 页已经把因子定义讲清楚了：`feat_single_amt_ratio_entropy_30m` 是把 1 分钟数据聚合成 30 分钟 bar、用“价占比×量占比”构造分布再算全天信息熵的**日频因子**（输入是分钟数据，输出落回日频面板）。继续把回测结果部分读完。

### **Assistant**
Good. Pages 5-8 give me:

- Page 5 (group backtest chart): 20-quantile layered backtest on 中证1000 (benchmark 000852), 2020-02-06 to 2025-07-15, VWAP group backtest. G0 = best group. Excess Ann 16.90%, Sharpe 1.36, Max DD -21.25%, IC mean 0.80?? Actually the numbers: G0 16.90% (excess ann), 1.36 sharpe, -21.25% max DD, 0.80 (calmar?), 54.32% win rate, 3.73% IC mean, 5.52 ICIR. Monotonic layering. Cum IC ~50 over 5 years. G0 annualized 22.9%.
- Page 6: G0-only equal-weight strategy: annualized 22.86%, excess 17.18% annualized, strategy max DD 44.29%, excess max DD 21.25%. Yearly: all positive excess except 2024 (-0.85%), 2023 highest 27.09%.
- Page 7: style correlation: high corr with residual_volatility (0.46) and liquidity (-0.50... wait, liquidity -0.50, residual_volatility -0.46 in the chart; text says 与波动率和流动性因子的相关性较高，分别达到0.46和0.5). So they neutralize size, industry, volatility, liquidity. Actually the bar chart shows liquidity -0.50, residual_volatility -0.46 (negative bars), but text says 0.46 and 0.5 (magnitude).
- Page 8: after neutralization (_neutralised_1): liquidity -0.47, residual_volatility -0.40 still. Then a neutralized group backtest: excess ann 11.42%, sharpe 1.00, max DD -21.01%, IC mean 0.48%, ICIR 1.37, long-short ann 18.42%, long-short sharpe 2.3, IC neutral 32.25%.

Wait — page 8's numbers: G0 11.42% excess ann after neutralization, still decent. Long-short 18.42% ann, sharpe 2.3.

Let me read the last pages 9-12 to see the small-cap vs large-cap comparison (the title says "小票里是猛兽，大票里变绵羊" — beast in small caps, lamb in large caps), and any conclusion + limitations.

回测数据很清晰了：中证1000 股票池上 20 分组、年化超额 16.9%，中性化后仍有 11.4%，但与流动性/波动率因子相关性高。继续读最后 4 页（大小票对比和结论部分）。

### **Assistant**
I've read pages 9-12. Let me check if there's a page 1 (the first image). The directory listing showed images numbered 2-12 (11 images). Page 1 might be missing or the numbering starts at 2. Looking at the listing: images _2 through _12 — that's 11 files. So page 1 (probably the cover/title) is missing. Not critical.

Full picture of the doc:

**Factor**: `feat_single_amt_ratio_entropy_30m` — 日内成交结构熵因子
1. Get 1-min close & volume; clean suspensions, no-trade minutes, missing prices, abnormal volumes
2. Aggregate 1m → 30m bars: close_30m,b, volume_30m,b (b = intraday slot index)
3. price_ratio_b = close_30m,b / Σclose_30m,b; volume_ratio_b = volume_30m,b / Σvolume_30m,b
4. p_b = price_ratio_b × volume_ratio_b, renormalize to probability distribution
5. Entropy = -Σ p_b ln(p_b), 0·ln0 = 0

Higher = more dispersed/uniform intraday price-volume structure; lower = concentrated (sudden shocks, short-term crowding).

**Backtest (from QuantZone)**:
- Raw factor, 20-day rolling mean smoothing best ("rolling_mean_20")
- Universe: 中证1000 (benchmark 000852), 2020-02-06 ~ 2025-07-15, VWAP group backtest, 20 groups
- Raw: monotonic layering, excess ann 16.9%, max DD -21.25%, cum IC ~50 over 5 years, IC mean 3.73%, ICIR 5.52 (hmm, that ICIR seems high; whatever, report as-is). G0 ann 22.9%. G0-only strategy: ann 22.86%, excess 17.18%, strategy max DD 44.29%, excess max DD 21.25%. Yearly positive except 2024 (-0.85%); 2023 best 27.09%.
- Style correlations: liquidity -0.50, residual_volatility -0.46 (highest), mid_cap -0.19, momentum -0.10, leverage -0.11, growth 0.13, book_to_price 0.08
- After neutralizing size/industry/vol/liquidity ("neutralised_1"): excess ann 11.42%, max DD -21.01%, cum IC 6, IC mean 0.48%, ICIR 1.37, long-short ann 18.42% sharpe 2.3. Some decay in predictive power.
- After full style neutralization (n21): G0 ann 10.2%, excess ann only 4.3%, max DD -18.89%, cum IC ~1.9? IC curve no longer monotonic upward since 2023 → time-series decay. Strategy: ann 9.87%, excess 4.3%, max DD 18.83%. Unstable excess. Conclusion: retains some cross-sectional selection ability but stability insufficient, practical excess contribution limited.
- Universe test: neutralized factor on 沪深300+中证500 (800 stocks, benchmark 000300): loses layering ability, best group G9 (not G0), IC flips negative, no monotonic decay. "小票里是猛兽，大票里变绵羊" — works in small caps, dies in large caps.

So the doc's honest conclusion: strong in small-cap universe (中证1000), decays with neutralization, basically dead in large caps. Typical microstructure/liquidity-adjacent factor.

Now the user's ask:
1. 分钟级高频如何建设 — how to build minute-level high-frequency (factor research) capability in localquant
2. This factor is good, add it as a candidate (分钟级高频) — but "只说不做" — talk only, don't do. So the deliverable is an explanation/design doc-style answer, not code.
3. Explain the whole minute-level workflow construction
4. Explain the general quant factor investing methodology: find factors → models → validation → backtest etc.

The user says "解释的时候，请完善解释一下整个分钟级高频流程如何构建。比如，解释我要进行常见的量化，就是需要采用因子投资的方法，即找因子，然后根据这些理论一些模型，验证，回测等等。只说不做"

So they want a thorough explanation of:
- The full factor-investing methodology (找因子 → 构造 → 清洗/预处理 → 单因子检验 → 因子合成/组合 → 组合构建 → 回测 → 风险控制 → 实盘)
- How to build minute-level high-frequency capability specifically in localquant (grounded in the actual codebase state)
- Where this entropy factor fits, and how to validate it locally

Key codebase facts (from Explore agent):
- Data: per-code parquet at data/cache/{period}/{code}.parquet; source QMT/xtquant (Windows-only); 1d has 125 stocks; 5m cache EMPTY; cleaner supports 1m/5m/15m/30m/60m with A-share specifics
- Intraday engine exists: intraday_operators.py with ID_* aggregators (minute→daily), M_* ops, 11-14 ready intraday factors; but hardcoded to 5m
- Downstream: IC analysis, quantile layering, alphalens, backtest — all daily-frequency
- No resampling capability
- Factor definition: formula DSL + presets; preset_factors table 622 rows including 14 INTRADAY ones
- Experiments: experiment_service CRUD; backtest daily only

So the good news: this entropy factor is a "minute→daily" factor (intraday aggregation collapsed to daily panel), which fits EXACTLY the existing intraday_operators architecture (ID_* aggregators + daily downstream). The user doesn't need minute-frequency backtesting to use this factor. The gap is: (a) minute data itself (5m cache empty, need 1m or 5m data; QMT required; doc's factor uses 1m close/volume aggregated to 30m), (b) resampling 1m→30m, (c) new operators for the entropy computation (price_ratio × volume_ratio → normalize → entropy), (d) registering as preset factor with formula, (e) universe support (中证1000-style small caps; localquant has 125 stocks downloaded — universe definition needed), (f) neutralization support (factor /neutralize endpoint exists).

Actually, for the entropy factor: 30-min bars need 1m data ideally (A-share 4 hours = 240 1-min bars/day → 8 slots of 30min). But 5m data also aggregates cleanly to 30m (6 bars per slot). QMT supports downloading 1m/5m. The doc says "将1分钟收盘价和成交量聚合为30分钟bar" — but with 5m data you'd get nearly identical results (30m close = last 5m close; volume sum). Minor differences at boundaries/suspensions.

Note: 30-min slots in A-share: 9:30-10:00 (well, 9:30-10:00 includes open auction effect; 240 minutes → 8 slots: 10:00,10:30,11:00,11:30 (morning 120min = 4 slots), 13:30,14:00,14:30,15:00 (afternoon 120min = 4 slots). With auction bar conventions (intraday_cleaner strips auction bars) — the cleaner already handles A-share specifics like auction-bar removal. Also note 9:30 bar vs 9:31 conventions.

Also: p_b = price_ratio × volume_ratio. Interesting: Σb price_ratio_b × volume_ratio_b — since price ratios sum to 1 and volume ratios sum to 1, p_b sums to 1 already (Σ p_b = Σ p_r × v_r = 1 if independent... actually Σ_b (price_ratio_b × volume_ratio_b) is NOT necessarily 1 — e.g. two slots each with (0.5, 0.5) → p = 0.25+0.25 = 0.5. So renormalization is needed — the doc says "实际计算时可对p_b再归一化"). Max entropy = ln(8) ≈ 2.079 for 8 slots. Min → 0 when all trading in one slot.

Economic interpretation: entropy high = trading spread evenly across day = stable participation; entropy low = concentrated = shocks/crowding. Doc found: LOW entropy (G0 = 最低熵组? "收益最高组为G0组") — G0 is the first group; need to check direction. From page 5: "收益最高组为G0组达到年化22.9%" and annualized return by group shows G0 highest ~22.9% descending to G19 lowest. If groups are sorted ascending by factor value, G0 = lowest entropy = most concentrated trading → highest returns in 中证1000. So low intraday entropy (concentrated trading) predicts HIGHER future returns in small caps. Interesting — likely related to attention/shock underreaction or lottery-like continuation in small caps. Or it could be that groups are sorted descending. I shouldn't over-claim direction; I can state it as "G0（因子值最低组，即日内成交最集中）表现最好" with a caveat to verify direction locally. Actually let me be careful: group labels G0..G19, "二十分组分层效果明显，单调性较好" and annualized returns descending from G0. Standard convention: G0 = lowest factor decile/quantile. So lowest entropy → highest return. But I'll note direction needs local verification.

Hmm wait — actually I should double check whether G0 = lowest. In QuantZone convention unknown. The style correlation: entropy vs liquidity -0.50 (high liquidity stocks → low entropy?), residual_volatility -0.46. Small caps have concentrated trading. Low entropy correlated with high liquidity (since liquid stocks trade all day evenly)... Actually let me not over-interpret. I'll present the direction question as something to verify (IC sign will tell).

Now the user's main ask: **分钟级高频如何建设** — build out the explanation. Let me structure the answer:

## Part 1: 因子投资方法论全景 (the general pipeline)
1. 数据层 (data): sources, storage, cleaning, point-in-time, survivorship
2. 因子挖掘 (factor discovery): 三大来源 — 经济逻辑/文献 (Alpha101, Alpha191, 学术因子), 数据驱动 (遗传规划/ML), 平台因子库 (QuantZone 2276 factors); classify: 价量/基本面/另类; frequency: 日频/日内
3. 单因子检验 (factor validation): 预处理 (去极值 winsorize, 标准化, 中性化), IC/RankIC, 分组回测 (quantile layering, monotonicity), 多空组合, 换手率/衰减, 相关性 vs 已有因子, 因子稳定性 (分年度/分行业/分市值域)
4. 因子组合 (synthesis): 等权/IC加权/回归法/机器学习
5. 组合构建与回测 (portfolio & backtest): 调仓频率, 交易成本, 冲击成本, 组合优化 (maximize alpha s.t. risk constraints)
6. 风险与绩效归因 (attribution): 风格归因, 行业归因, Brinson
7. 模拟盘/实盘 (paper/live)

## Part 2: 分钟级高频（日内）因子体系如何建设 — grounded in localquant
Key concept: 大多数"分钟级因子"其实是 **分钟数据 → 日频因子值** (daily-frequency factors derived from intraday microstructure)。真正"分钟级调仓"的高频交易是另一回事 (T+0, 盘内信号)。对于因子投资框架, 用户需要的是前者。The entropy factor is exactly this.

Architecture layers to build in localquant:
1. **数据层**: 1m/5m bar storage (QMT download; 5m cache exists but empty; ~5000 A-share stocks × 240 bars/day → 1m full market ≈ 120万行/天 → parquet per code is right; estimate storage: 1 stock-year of 1m ≈ 57600 rows ≈ few MB; full market 5 years ≈ ~100-300GB? Let me estimate: 5700 stocks × 240 bars × 250 days = 342M rows/year. Parquet row ~30-50 bytes compressed → ~15GB/year. So full-market 1m 5 years ≈ 50-80GB. Start with a subset (中证1000 constituents) → much smaller. Or just use 5m (1/6 of that).
2. **清洗层**: already exists (intraday_cleaner.py handles A-share specifics) — 停牌/无成交/涨跌停/集合竞价bar
3. **重采样层** (missing): 1m→30m resample, align to A-share slot boundaries (9:31-10:00 style or 9:30-10:00), handle lunch break & suspensions
4. **因子计算层**: extend intraday_operators — the ID_* namespace already collapses minute→daily; add entropy operator or a generic ID_ENTROPY; the formula DSL could express it if operators exist
5. **检验层**: reuse existing daily IC/quantile/alphalens/neutralize — no new work needed since output is daily panel
6. **回测层**: daily portfolio backtest with 中证1000-style universe; support cost models for small caps (higher impact)
7. **维护层**: daily incremental update via scheduler (QMT runs pre-market/post-market), data quality checks

Practical build order (roadmap):
- Phase 0: acquire minute data for a pilot universe
- Phase 1: resample + implement entropy factor as a preset (formula + operator)
- Phase 2: run the standard validation chain locally, compare with doc's numbers (benchmark: 中证1000, 20 groups, VWAP, 2020-2025)
- Phase 3: neutralization & universes (small vs large cap replication of "beast vs lamb")
- Phase 4: factor pool integration

## Part 3: 这个价量熵因子具体怎么做进 localquant (design, no code)
- Formula representation in the DSL: needs new operators e.g. ID_ENTROPY(price, volume, window=30min)... Actually as a formula: 30m bucket → price_ratio = close_30m / ts_sum(close_30m, day) etc. In existing DSL terms, needs ID_* operators extended: ID_SLICE already exists... The cleanest: one new composite operator `ID_PV_ENTROPY(period_minutes=30)` returning daily panel.
- Where it plugs in: preset_factors table + seed script (backend/scripts/seed_intraday_factors.py pattern), category INTRADAY
- Validation targets to reproduce: IC mean ~3.7% (raw, 中证1000), excess ~16.9%; after neutralization 11.4% → 4.3% (fully neutralized); universe sensitivity (300+500: dead). Expectations: with only 125 stocks locally, results will differ from a 1000-stock universe — important caveat!
- Warnings: doc is from a platform selling factor library (survivorship/overfitting risk in promoted factors), 2024 anomaly (Feb 2024 small-cap crash + Sep 24 2024 rally), T+1 constraints, small-cap liquidity/capacity, the factor's decay under neutralization means much of raw alpha is liquidity/vol beta.

## Part 4: 高频因子家族 — what else minute data enables (a menu)
- 已有: tail momentum, overnight ret, RV, Amihud, VWAP dev, volume clock, auction volume ratio, limit-up time...
- 经典高频因子库: 聪明钱 (smart money), 高频波动率分解 (已实现波动率、上行/下行半方差、跳跃), 订单流不平衡代理 (tick不成,分钟可做: 主动买卖占比近似), 尾盘/开盘效应, 大单净流入 (需要逐笔或快照), 高频量价相关性 (日内corr(p,v)), 振幅分解, 日内偏度/峰度, APM (上午动量), MPB (mom pop breakout)...
- The entropy factor is a member of "日内分布/结构" family — siblings: 日内成交量分布熵、价格路径复杂度、时段收益占比等.

Also mention: QuantZone's approach (SDK, 因子库 2276 factors, pre-market updates) — could be an additional data source for factor VALUES (not raw data): you can pull their computed factor values and cross-check your own computation — a good validation shortcut ("对拍").

Keep it 只说不做 — no implementation. The answer should be in Chinese, well-structured, thorough but readable. The user asked for a fairly complete explanation — this warrants a long-form answer. Let me also anchor specific localquant file references so it's actionable later.

Length: this deserves a substantial answer, but must stay readable. Use sections with headers, prose-heavy, a few tables where enumerable. Chinese language (user writes in Chinese).

One more check — do I know the direction of the factor (G0 = high or low entropy)? From page 5: "收益最高组为G0组". The title of the backtest: "amt_ratio_entropy_30m_rolling_mean_20_000852_group". Standard quantile group backtests label G0..G19 ascending by factor value → G0 = lowest entropy = most concentrated intraday trading = highest future return in CSI1000. And the style correlations: entropy negatively correlated with liquidity (-0.50) and residual vol (-0.46). So LOW entropy ↔ high liquidity... hmm, that seems backwards: entropy measures dispersion of trading across slots. Liquid large stocks trade evenly all day → HIGH entropy. Small caps trade in bursts → LOW entropy. But correlation with liquidity is -0.50: high liquidity ↔ LOW entropy?? That contradicts. Unless... entropy high = dispersed; liquidity factor value high = illiquid? Factor conventions for "liquidity" style factor: often constructed so higher = more liquid, or higher = lower liquidity... Barra CN style "LIQUIDITY" is typically STOM/STOQ measures where higher = more liquid. If entropy correlates -0.50 with liquidity(higher=more liquid), then more liquid → lower entropy → more concentrated?? That doesn't match intuition. Alternatively the liquidity factor might be signed as "illiquidity". I can't resolve this; better to not over-claim. I'll say the doc reports G0 (需确认方向，通常G0为因子值最低组) best, and note the economic reading both ways with the local replication resolving it. Actually — the doc says "该因子值越高，表示日内价量成交结构越分散、越均衡" and best group G0. If G0 = lowest values = most concentrated → concentrated trading predicts higher returns in small caps. I'll state this with the caveat "若G0为因子值最低组（常见约定）".

Also worth noting for replication: the localquant universe is 125 stocks (daily data), which is NOT 中证1000 — user should download minute data for a proper small-cap universe, or the replication will deviate. Also 中证1000 constituent history is point-in-time — survivorship matters.

Storage estimate for minute data — let me be more careful:
- 1 stock-day of 1m bars: 240 bars (A-share 4h trading). Each bar: datetime, OHLCV, amount ≈ maybe 60 bytes raw, ~20-30 bytes parquet with compression.
- 1 stock-year: 240×250 = 60,000 bars → ~1.5-2MB parquet.
- 5000 stocks × 5 years: ~30-50GB. For 中证1000 × 5 years 1m: ~8-10GB. 5m data: ~1/6 → 1.5-2GB. That's manageable locally. I'll give rough numbers like "全市场1分钟五年几十GB，中证1000成分1分钟五年约10GB量级，5分钟再除以6".

Actually QMT's 1m history depth is limited (usually ~1-2 years for 1m via download, depends on broker; 5m deeper). That's an important practical caveat for QMT as source. Alternatives: 迅投研, 通联, RiceQuant/JoinQuant 米筐/聚宽 ( minute data via paid), akshare minute (limited history), baostock (5m data free! baostock provides 5/15/30/60m bars with decent history, and 1m not available... actually baostock has 5min+ history back to 2011 or so — good free source for 5m). Tushare pro has 1min/5min (积分门槛). Since localquant currently only has QMT — mention adding a fallback source (baostock for 5m is the cheapest path; the user's factor needs only 30m aggregation which 5m data suffices for).

Wait — the factor doc says aggregate 1m close/volume to 30m. With 5m bars: each 30m slot = 6 5m bars; close_30m = last 5m close (same as last 1m close of the slot); volume_30m = sum. Identical result except when a slot has missing minutes. So 5m data is sufficient for THIS factor. Good point to make: "这个因子对数据粒度的真实需求是30分钟bar，5分钟数据聚合即可，数据量小一个数量级，baostock/QMT都能拿到".

QMT minute history: xtquant download_history_data supports 1m/5m with history depth depending on broker (often several years for 5m). Fine.

Now also: the user said "可以把它加进来（分钟级高频）" — they want it added, but "只说不做" — so I explain HOW it would be added (design), not implement. I should give a concrete integration design: where it lands in the codebase (intraday_operators.py new operator + seed_intraday_factors.py preset entry + formula), what the validation plan is, expected metrics to compare against the doc.

Also the "常见量化 = 因子投资方法" walkthrough: 找因子 → 模型 → 验证 → 回测. The user wants the full methodology explained clearly. I'll write a compact but complete pipeline description with the localquant mapping at each step (which existing feature covers it — that makes it concrete and shows what's missing for minute-level).

Structure of final answer (Chinese):

1. TL;DR — 这个因子是什么、结论如何、在 localquant 落地需要补哪几块
2. 因子拆解 (公式+含义+方向) — 30min entropy, 8 slots, max ln8
3. 文档回测结论摘要 (numbers + 递进: raw → 部分中性化 → 全中性化 → 大票池失效)
4. 因子投资的完整方法论 (the general pipeline user asked for) — with localquant 对应
5. 分钟级高频体系怎么建 (architecture: 数据→清洗→重采样→因子→检验→回测→维护; 现状与缺口 grounded in code)
6. 这个因子如何落地 (concrete design: operator + preset + universe + validation checklist vs doc numbers; 5m enough; pilot universe)
7. 风险与注意事项 (推广平台因子的小心点, 2024, 小票容量, 中性化后衰减说明大部分alpha是流动性/波动率暴露, 与现有INTRADAY因子的相关性检查)
8. 高频因子家族延伸 (what else this infrastructure unlocks) — short menu

Keep prose readable, tables only for enumerable facts (backtest numbers, build gaps). Reference files as clickable paths.

Length check: this is a "explain comprehensively" request — a long answer is appropriate, but I should keep it tight; aim for something like 1500-2200 Chinese words equivalent. Use headers.

Let me also double-check a couple of codebase claims I'll reference:
- intraday_operators.py: ID_* namespace, build_intraday_namespace — from Explore agent, trust it.
- factor_research.py hardwired to 5m (lines 1687, 1731) — trust.
- seed_intraday_factors.py — trust.
- data/cache/{period}/{code}.parquet — trust.

One consideration: the user said "来自 quantzone，这个平台似乎对高频因子颇有研究" — acknowledge: QuantZone 因子库 2276 factors, daily pre-market updates, SDK. Also their series title "攻城小队". I can note that QuantZone factor values themselves can be pulled via their SDK for 对拍 (cross-validation), which is a smart way to verify local implementation. Don't over-claim knowledge of QuantZone beyond the doc.

Backtest numbers table (from doc):
| 口径 | 年化超额 | 最大回撤(超额) | 备注 |
| 原始因子·中证1000·20分组 | 16.9% | -21.25% | G0 年化 22.9%, 五年累计IC≈50, 单调性好 |
| G0等权策略 | 超额17.18% (绝对22.86%) | 策略-44.29% / 超额-21.25% | 仅2024年超额-0.85% |
| 市值+行业+波动率+流动性中性化 | 11.42% | -21.01% | 多空年化18.42%, 多空夏普2.3 |
| 全风格中性化 | 4.3% | -18.89% | IC 2023年起不再上行, 稳定性不足 |
| 沪深300+中证500池 | ~0 (失效) | - | 分层失效, IC转负 |

Also IC mean raw 3.73% daily rank IC (roughly), ICIR 5.52 (per doc header). Hmm, those header numbers: G0 16.90% | 1.36 | -21.25% | 0.80 | 54.32% | 3.73% | 5.52 — likely Sharpe 1.36, MaxDD -21.25%, Calmar 0.80, WinRate 54.32%, IC Mean 3.73%, ICIR 5.52. And page 8 (neutralised_1): 11.42% | 1.00 | -21.01% | 0.54 | 54.05% | 0.48% | 1.37. Page 10 (n21): 4.30% | 0.42 | -18.89% | 0.23 | 52.37% | 0.20% | 0.81. Wait page 10 header says G0 4.30% excess... and IC Mean 0.20%, ICIR 0.81. Hmm but the text on page 11 says strategy ann 9.87% excess 4.3% max DD 18.83%. OK consistent.

Note in page 8 header: "0.48%" IC mean — that's daily rank IC mean 0.48%?? That seems low vs raw 3.73%. Cum IC 6 over 5 years (1130 days × 0.48% ≈ 5.4 ✓). Raw: 1130 × 3.73% ≈ 42 ≈ "累计IC达到50" ✓ roughly. OK so daily rank IC: raw ~3.7%, neutralized_1 ~0.48%, fully neutralized ~0.20%. These are consistent internally. Good.

Now the entropy direction: G0 best. In QuantZone convention G0 is likely the lowest quantile of factor values. Low entropy = trading concentrated in few slots. So in 中证1000, stocks whose trading is concentrated (爆量脉冲式) outperform. Plausible microstructure story: attention-driven underreaction continuation, or associated with 妖股/涨停 dynamics in small caps. But careful: I'll present with hedge.

Also 2024 max DD: Feb 2024 micro-cap crash and/or Sep 2024 — the doc notes 2024 negative excess (-0.85% raw; strategy). Fine.

One more local-replication caveat: the doc uses VWAP group backtest and point-in-time 中证1000 membership. localquant currently has 125 stocks of daily data and empty 5m cache — user must first download minute data for their universe. Also QMT is Windows-only — the user seems to have that (data_download.py exists and they've used it for 1d). Fine, mention briefly.

Also mention: 公式表达 — in localquant's DSL the factor would need new operators; simplest as a composite ID operator. Two implementation routes: (a) extend intraday_operators with ID_PV_ENTROPY(bucket=30) that returns daily panel; (b) generalize resample(30m) then reuse M_*/ID_* ops. Recommend (a) for now (fits existing engine), (b) later as part of 重采样层.

Also worth flagging: factor_research intraday path is hardcoded to 5m — the entropy factor wants 30m buckets which works from 5m data (6 bars/slot), so no engine change needed for THIS factor — just new operators. Nice synergy to point out.

And validation checklist to run locally (using existing endpoints): /compute → /ic-analysis (periods 1,5,10,20) → /quantile (20 groups) → /neutralize (size/industry if available — does localquant have industry data? fundamental.py exists; neutralize endpoint exists) → /correlation vs existing INTRADAY presets (esp. intraday_vol_clock, intraday_tail_volume_share — volume-distribution family) → /alphalens → backtest G0 portfolio with costs.

Also data quality: A-share 30m slot conventions — 8 slots: 09:31–10:00, 10:01–10:30, ..., 13:01–13:30, ..., 14:31–15:00. With 1m bars labeled 9:31...15:00 (240 bars). Cleaner strips auction bar (9:30 open auction bar labeled 9:30 in QMT 1m? QMT 1m bars: first bar 9:31 usually contains 9:30-9:31; there's also a 9:30 auction bar in some feeds — intraday_cleaner already handles). Mention slot alignment must handle 午休 (11:30/13:00 boundary: 11:01-11:30 is slot 4, 13:01-13:30 is slot 5) and 停牌半天.

Turnover note: raw factor turnover 10.28% per... page 5 metrics "Best Turnover 9.62%"? Page 10: "Best Turnover 30.23%"? Hmm — page 5 metric table: Best Turnover 9.62%, Best Holding 9, Total Trades 2736... These are per-group. Whatever — the 20-day rolling smoothing exists because daily entropy is noisy; single-day entropy turnover high. Mention smoothing as part of the design (rolling_mean_20 wrapper in formula).

Now, let me think about what "分钟级高频" 建设 means at the architecture level for localquant, written as recommendations:

**层次1 数据**
- 现状: data/cache/{period}/{code}.parquet, QMT 下载, 5m 空, 1d 有125只
- 建: (a) 试点股票池 (先中证1000成分或自选池100-300只), 5m 起步 (够做30分钟桶, 量小), 1m 视需要; (b) 增量更新任务挂 scheduler (QMT 盘后下载); (c) 数据质量检查 (缺失分钟数/停牌标记/异常量); (d) 备选源 baostock (免费5m, 历史长) 以摆脱 QMT 单点
- 存储: parquet-per-code 已合适, 无需换 DuckDB 表; 全市场才需要考虑

**层次2 重采样 (新增能力)**
- 1m/5m → 30m/60m, 按 A 股时段对齐 (8×30min), 午休/停牌处理; 这是通用能力, 服务所有"分钟→日内结构"因子

**层次3 因子引擎**
- 现状: intraday_operators ID_*/M_* 已有, 输出日频面板; factor_research 固定读 5m
- 建: 新增熵算子 (或分布族算子: ID_DIST_ENTROPY(field, bucket)); 预设注册 seed_intraday_factors 模式; 公式化 rolling_mean_20 平滑

**层次4 检验 (现成)**
- IC/分层/中性化/相关度/alphalens 全部日频现成 — 这就是"分钟数据→日频因子"路线的最大好处: 下游零改动

**层次5 回测 (现成+小补)**
- 组合回测日频现成; 需要: 股票池参数化 (中证1000 vs 自选), 小票成本假设 (冲击成本更高), 基准 (000852) 数据

**层次6 流程 (实验管理)**
- experiments 表已有; 建议把"文档复现"作为一个实验记录: 目标指标对照表

方法论部分 (找因子→验证→回测) — 我要写清楚每一步干什么、为什么、用什么指标、常见坑:

1. **因子从哪来**: 逻辑驱动 (经济直觉/行为金融: 动量、反转、流动性溢价、注意力), 文献/因子库 (Alpha101/191, 学术 400+), 数据驱动挖掘 (GP/ML, 过拟合风险高), 平台因子 (QuantZone 等)。高频/日内因子的特有逻辑来源: 市场微观结构 (订单流、流动性提供、知情交易), 日内行为模式 (尾盘效应、隔夜vs日内、涨停板)。
2. **因子计算与预处理**: 点时数据 (point-in-time, 财报用公告日), 去极值 (MAD/分位), 标准化 (zscore/rank), 中性化 (市值/行业/风格回归取残差) — 顺序和选择影响结论。
3. **单因子检验**: IC/RankIC (预测力, >0.03 日频可用, 0.05 优秀), ICIR (稳定性, >0.5), 分组单调性 (20分组, 看是否单调还是仅头部), 多空组合 (但 A 股做空受限, 头部组合才是可实现的), 换手与衰减 (调仓成本 vs IC half-life), 分域测试 (大/小票、行业内、分年度), 相关性 (与已有因子池的相关, 增量信息)。
4. **从因子到策略**: 因子组合 (等权/IC加权/最优化), 组合构建 (top-N / 分组头部 / 优化器: 目标 alpha 最大化+风险约束+换手约束), 成本模型 (佣金+印花+冲击), 回测纪律 (样本内外, walk-forward, 避免未来函数: 因子在第 T 日收盘后算, T+1 开盘或 VWAP 成交)。
5. **归因与风控**: 风格/行业归因, 确认超额来自因子本身而非 beta; 压力时段检验 (2015, 2016熔断, 2019Q1, 2021核心资产, 2024.2 小票流动性危机, 2024.9.24)。
6. **跟踪与迭代**: 因子会衰减 (拥挤度), 持续监控 IC, 定期重新检验。

这份回答里用户重点要的是"只说不做"的完整讲解。我会把 localquant 现状映射进去,让讲解落地。

关于"把因子加进来"的落地设计 (只说不做):
- 算子: intraday_operators.py 增加 `ID_PV_ENTROPY(bucket_minutes=30)` (输入分钟 close/volume, 输出日面板) — 或者更通用的两步: `ID_BUCKET_SUM/ID_BUCKET_LAST(bucket)` + 公式层组装熵。推荐先用单一复合算子, 快且对齐文档口径。
- 预设: seed 到 INTRADAY 分类, formula 形如 `ts_mean(ID_PV_ENTROPY(close, volume, 30), 20)` (rolling_mean_20 对齐文档最优口径)。
- 数据: 5m 起步 (30分钟桶=6根5m), 试点池, scheduler 增量。
- 验证对照表: 对齐文档指标 (中证1000 口径) — 本地池不同会有偏差, 方向/单调性/量级三看。
- 相关性检查: 与 intraday_vol_clock, intraday_tail_volume_share, 换手率, 波动率 — 文档已提示 liquidity/vol 相关 0.5, 预期会有重叠。

坑:
- 平台推广因子 = 事后筛选幸存者风险; 文档自己的中性化递进已经展示: 裸因子 16.9% → 全中性化 4.3% → 大票池失效。这说明大头 alpha 是流动性+波动率暴露。作为"纯alpha"它弱, 作为"小票池内增强"它可用。
- 2024.2 微盘危机是该因子家族的共同压力测试。
- 容量: 小票、VWAP 成交、G0 组 ~50 只 (1000/20), 策略容量有限。
- T+1 与涨跌停可成交性 (G0 集中在活跃小票, 涨停买不进)。
- 复现风险: QuantZone 口径 (VWAP group backtest, 调仓频率=5天? "Acting Window 5") — 对齐口径才能对比。

注意到 page 5 metric table: Acting Window 5 (每5天调仓), Benchmark 000852. And page 10: Acting Window 5. OK mention 调仓窗口5天。

Also "五年累计IC达到50" — that's cum sum of daily rank IC over 1130 days ≈ mean 4.4%? close to 3.73% stated... whatever, quote doc as-is.

I think I have everything. Now write the final answer in Chinese. Structure:

# 先说结论 (TL;DR)
# 一、这个因子在讲什么 (拆解)
# 二、文档回测结果与它的"衰减曲线" (table + 解读: beast vs lamb)
# 三、因子投资的完整流程 (方法论, 每步映射 localquant)
# 四、分钟级高频体系怎么建 (六层, 现状/缺口/建议)
# 五、价量熵落地设计 (只说不做)
# 六、注意事项与风险

Keep it readable. The user is clearly sophisticated (they built localquant), so I can be technical but should stay in clear prose. Avoid excessive bullet fragmentation; mix prose + tables. Cite localquant files as clickable refs.

Length target: comprehensive but not bloated. Maybe ~2000-2500 words Chinese. This is a "explain the whole thing" request, so length is justified. Let me write it well.

文档 11 页全部读完，代码结构也摸清了。下面把因子本身、文档回测结论、分钟级高频体系建设方案、以及它在 localquant 里的落地设计完整讲一遍（只说不做）。

---

# TL;DR

`feat_single_amt_ratio_entropy_30m` 是一个**用分钟数据算、但输出落回日频面板**的日内结构因子：把 1 分钟数据聚合成 30 分钟 bar，用“价占比 × 量占比”构造全天 8 个时段的概率分布，算信息熵。文档在中证1000 池上裸因子年化超额 16.9%，但经过逐层中性化后衰减到 4.3%，在沪深300+中证500 池上直接失效——“小票猛兽、大票绵羊”名副其实。

对你来说有个好消息：**这个因子不需要你建“分钟级回测引擎”**。localquant 现有的 `intraday_operators.py` 架构（分钟→日频面板→日频 IC/分层回测）正好是它需要的形态，下游检验链路全部现成。真正的缺口只有三块：**分钟数据本身**（5m 缓存是空的）、**1m/5m→30m 重采样对齐**、**熵算子**。

---

# 一、因子在讲什么

**计算步骤**（对齐文档口径）：

1. 取 1 分钟 `close`、`volume`，清洗停牌、无成交、价格缺失、量异常的分钟；
2. 聚合成 30 分钟 bar：`close_30m,b`、`volume_30m,b`，b 为当日第 b 个时段（A 股 4 小时 = 8 个时段）；
3. 算占比：`price_ratio_b = close_30m,b / Σ close_30m,b`，`volume_ratio_b = volume_30m,b / Σ volume_30m,b`；
4. 联合权重 `p_b = price_ratio_b × volume_ratio_b`，再归一化成概率分布（两个占比各自和为 1，乘积之和一般不为 1，必须再归一）；
5. 全天信息熵 `H = -Σ p_b·ln(p_b)`，`p_b=0` 项记 0。

**含义**：熵越高，成交越均匀铺满全天，资金参与持续、结构稳定；熵越低，成交集中在少数时段，对应突发冲击或短线资金拥挤。理论上限 `ln(8) ≈ 2.08`（完全均匀）。单日熵噪声大，文档回测对原始因子做 5/10/20 日滚动均值平滑，**20 日最优**——这本身就说明它是个低信噪比因子，靠平滑换取可用性。

**方向**（按常见分组约定 G0=因子值最低组推断，落地时用 IC 符号验证）：中证1000 池内 G0 表现最好，即**日内成交越集中、熵越低，未来收益越高**。

---

# 二、文档回测结果：一条清晰的“衰减曲线”

这篇文档最有价值的地方不是那个 16.9%，而是它诚实地做了四层递进测试：

| 测试口径 | 年化超额 | 超额最大回撤 | 日 Rank IC 均值 | 结论 |
|---|---|---|---|---|
| 裸因子，中证1000，20分组，5日调仓 | 16.9% | -21.25% | ~3.7% | 单调性好，五年累计 IC≈50 |
| G0 组等权策略 | 17.18%（绝对 22.86%） | -21.25% | — | 仅 2024 年超额为负（-0.85%） |
| 市值+行业+波动率+流动性中性化 | 11.42% | -21.01% | ~0.48% | 多空年化 18.4%、夏普 2.3，预测力开始衰减 |
| 全风格中性化 | **4.3%** | -18.89% | ~0.20% | 2023 年起 IC 不再单边上行，稳定性不足 |
| 换到沪深300+中证500 池 | 失效 | — | 转负 | 分层不再单调，最高组漂移到 G9 |

配合风格相关性（与流动性 -0.50、残差波动率 -0.46）可以下判断：**裸因子超额的大头是流动性+波动率暴露，纯 alpha 部分存在但偏弱、且集中在小票域**。它适合的用法是“小票池内的增强因子”，而不是全天域独立选股因子。另外 2024 年是它的压力时点（2 月微盘流动性危机 + 9 月行情切换），文档里两个口径在 2024 年都录得负超额。

---

# 三、因子投资的完整流程（方法论总览）

你问的“常见量化怎么做”，完整链路是这七步。我把每一步和 localquant 现状对应上：

**1. 数据层**。行情（日频/分钟/tick）、基本面（财报要用公告日 point-in-time，不能用披露截止日，否则引入未来函数）、成分股历史（做池子要时点成分，用今天的成分股回测五年就是幸存者偏差）。→ localquant：`data/cache/{period}/{code}.parquet` + QMT 下载，日频 125 只已有。

**2. 因子挖掘**。三个来源：逻辑驱动（动量、反转、流动性溢价、注意力效应这些经济/行为解释）；文献与因子库（Alpha101、Alpha191、学术因子几百个，QuantZone 这类平台库属于此类——好处是省挖掘成本，坏处是推广因子天然经过事后筛选）；数据驱动挖掘（遗传规划/ML，过拟合风险最高，必须配严格的样本外纪律）。日内因子的特有逻辑来源是**市场微观结构**（订单流、流动性提供、知情交易）和**日内行为模式**（尾盘、隔夜 vs 日内、涨停板）——价量熵就属于“日内成交分布”这一族。

**3. 因子预处理**。去极值（MAD 或分位截断）→ 标准化（zscore 或 rank）→ 中性化（对市值、行业、风格因子截面回归取残差）。顺序和选择会实质改变结论，文档那四层递进就是在做这件事。

**4. 单因子检验**。核心指标四件套：IC/RankIC（预测力，日频因子 0.03 以上可用、0.05 算优秀）、ICIR（稳定性，0.5 以上）、分组单调性（20 分组看是否全层单调，还是只有头部有效——A 股做空受限，只有 G0 可实现时多空指标是虚的）、换手与衰减（IC 半衰期要撑得起调仓成本）。再加三个压力测试：分年度稳定性、分市值域（大小票）、与已有因子池的相关性（增量信息才是价值）。→ localquant：`/ic-analysis`、`/quantile`、`/neutralize`、`/correlation`、alphalens 全链路现成。

**5. 因子组合与回测**。多因子合成（等权/IC 加权/回归法/ML），组合构建（top-N 或分组头部，含优化器约束），成本模型（佣金+印花+冲击成本，小票冲击要放大），回测纪律（因子 T 日收盘后可得、T+1 成交，walk-forward 样本外验证）。→ localquant：`backtest_analysis.py` 的组合/walk-forward 回测现成。

**6. 归因与风控**。风格/行业归因确认超额来自因子本身而非 beta；在已知危机时点做压力检验（2015 股灾、2024.2 微盘危机、2024.9.24 等）。

**7. 跟踪迭代**。因子会衰减、会被拥挤交易稀释，上线后持续监控滚动 IC，定期重检。

**这份文档本身就是第 3、4、6 步的标准示范**——这也是它比一般“晒曲线”帖子可信的原因。

---

# 四、分钟级高频体系怎么建（六层架构）

先厘清一个关键概念：**因子投资语境下的“分钟级高频”，99% 指的是“分钟数据 → 日频因子值”**，就像价量熵这样——日内微观结构信息浓缩成一个日频截面值，进日频调仓组合。真正“分钟级调仓”的日内交易（T+0 盘内信号）是另一套技术栈（tick 数据、盘口、低延迟执行），和你的因子框架是两条线。你要建的是前者。

对照现状（探索结果：5m 缓存为空、无重采样能力、日内引擎固定 5m、下游全日频），建议按六层建：

| 层 | 现状 | 缺口与建议 |
|---|---|---|
| ① 数据 | QMT 下载，parquet per code，`data/cache/5m/` 空 | 试点池起步：先 100~300 只（如中证1000 子集），**5m 起步就够**（这个因子只吃 30 分钟桶，30m 桶 = 6 根 5m，结果与 1m 聚合几乎一致，数据量小一个数量级）；scheduler 挂盘后增量更新；考虑加 baostock 做免费 5m 备源，摆脱 QMT 单点 |
| ② 清洗 | `intraday_cleaner.py` 已处理 A 股特性（竞价 bar、半天、一字板） | 基本现成，补数据质量巡检（每日缺失分钟数、异常量报警） |
| ③ 重采样 | **完全没有** | 新增通用能力：1m/5m → 30m/60m，按 A 股 8 时段对齐（09:31–10:00、…、11:01–11:30、13:01–13:30、…、14:31–15:00），处理午休边界和停牌日 |
| ④ 因子引擎 | `intraday_operators.py` 的 ID_*/M_* 命名空间 + 14 个 INTRADAY 预设 | 加分布族算子即可（见下节设计），引擎架构不用动 |
| ⑤ 检验链 | IC/分层/中性化/相关性/alphalens 全日频现成 | **零改动**——这是“分钟→日频”路线最大的好处 |
| ⑥ 回测 | 日频组合回测、walk-forward 现成 | 补两件小事：股票池参数化（时点成分的中证1000 口径）、小票成本假设上调；基准 000852 行情 |

存储量级给你个底：中证1000 成分 5 年 5m 数据约 1.5~2GB，全市场 1m 五年也就几十 GB——parquet per code 的现有架构完全撑得住，不需要引入新存储。

---

# 五、价量熵在 localquant 的落地设计（只说不做）

**算子层**：在 `backend/services/intraday_operators.py` 加一个复合算子 `ID_PV_ENTROPY(price, volume, bucket_minutes=30)`——内部做时段分桶、双占比、归一、熵，输出日频面板（和现有 ID_* 聚合器同构）。比起拆成一堆原子算子再在公式层组装，单算子快且严格对齐文档口径；以后想泛化“日内分布”家族（量分布熵、收益分布熵、时段占比等）再抽公共的桶聚合原语。

**预设注册**：按 `backend/scripts/seed_intraday_factors.py` 的模式进 INTRADAY 分类，公式带平滑包装对齐文档最优口径，形如 `ts_mean(ID_PV_ENTROPY(close, volume, 30), 20)`。

**验证计划**（复现文档，做成一个 experiment 记录）：
1. 下载试点池 5m 数据，跑 `/compute` → `/ic-analysis`（periods 1/5/10/20）→ `/quantile`（20 分组）；
2. 对照文档指标三看：**方向**（IC 符号，验证“低熵=高收益”的推断）、**单调性**（是否全层单调）、**量级**（日 IC 是否在 0.3%~0.5% 量级）；本地池和文档的中证1000 时点成分不同，量级有偏差是正常的；
3. `/neutralize` 对市值/波动率/流动性中性化，复现“16.9% → 11.4% → 4.3%”的衰减轨迹，确认本地结论同构；
4. `/correlation` 对现有 INTRADAY 预设查重——尤其 `intraday_vol_clock`、`intraday_tail_volume_share` 这两个同属“成交量分布”家族的，以及换手率、波动率类日频因子。文档提示它与流动性/波动率相关 0.5，预期重叠不低，这决定它进因子池的边际价值。

**一个额外的取巧验证路径**：QuantZone 有 SDK 和因子库（2276 个因子，盘前更新到前一交易日），可以直接拉他们算好的该因子值和本地实现**对拍**——数值对不上时能快速区分是“实现口径差”还是“数据差”，比自己闷头排查省很多时间。

---

# 六、注意事项

- **平台推广因子的事后筛选风险**：能被拿出来写帖子推广的因子，天然是库里表现好的那一批。这篇文档因为做了完整的中性化递进和换域测试而可信度较高——但它的结论本身就是“纯化后弱”，别只记住 16.9% 那个数。
- **口径对齐才能对比**：文档是 VWAP 成交、5 日调仓窗口、时点中证1000 成分。本地复现若不齐这三项，数字差很多不代表因子坏了。
- **可实现性**：G0 组约 50 只小票，涨停买不进、跌停卖不出，小票冲击成本高，T+1 限制下策略容量有限——回测必须带涨跌停可成交性判断和放大后的成本。
- **拥挤度**：日内分布类因子在量化小票产品里的使用密度不低，2024.2 那次微盘流动性危机就是这类暴露的集体压力测试，建议把它列入你的常规压力时点清单。

总体判断：这个因子值得进池子——逻辑干净（微观结构里的“成交集中度”）、数据需求低（5m 就够）、你的架构接住它的成本很小；但要按“小票池增强因子”定位，而不是独立 alpha 来源。等你要动手时，第五节的设计可以直接当开工清单用。

### **You**
The preceding conversation was inherited from the parent task for reference only. Do not continue the parent's active work automatically; answer only new questions sent in this side chat. Modify the workspace only when the user explicitly asks you to do so in this side chat.
