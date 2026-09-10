# factor-formula-audit审查预置因子公式可执行性

你是量化平台的代码审查员。项目位于 /Users/victor/Desktop/coding/localquant（Python 3.12 + uv，FastAPI 后端在 backend/）。这是一个只读审查任务：**绝对不要修改项目内任何文件**，临时脚本只能写到 /tmp。不要调用任何付费 AI 接口。 背景：该项目有一个预置因子库（约 622 个因子，存于 data/localquant.db 的 SQLite 中，表结构见 backend/database.py），因子公式通过 backend/services/factor_operators.py 的算子命名空间 + backend/services/formula_normalizer.py 的方言规范化求值。2026-08 曾有审查发现「33 个预置因子公式语法错误/不可执行」（已知问题，后在 commit 0a4d4fd 声称修复：方言自动规范化、结构化错误分类与状态门控）。 你的任务：验证当前预置因子库中公式的可执行性现状，给出证据清单。 具体步骤建议： 1. 读 backend/database.py 找到因子表名与字段；用 sqlite3 读取全部预置因子（可能有 category/公式字段），统计数量与类别分布。 2. 读 backend/services/factor_operators.py、formula_normalizer.py 以及因子求值入口（可能在 backend/services/factor_research.py 或 routes/factor.py，找到「公式求值/批量扫描」所用的同一函数），理解正确的调用方式（注意：需要真实行情面板作为输入；本地缓存为 data/cache/1d/*.parquet，125 只股票）。 3. 写一个 /tmp 下的脚本，用与生产相同的求值入口，对每个预置因子的公式在真实缓存面板上求值（若公式需要财务/股本/行业等参考数据，data/cache/reference/ 下有 instrument/industry/universe/index_constituents parquet；缺数据的公式请单独归类为「缺数据」而不是「公式错误」）。为避免超时，对每个因子求值加超时保护并限制输出。 4. 汇总：总数、成功数、失败数；每个失败因子给出：因子名、公式、错误类型与错误信息原文（截取关键行）。区分：a) 语法/方言错误；b) 引用不存在的算子或字段；c) 数据缺失导致；d) 其他。 5. 另外抽查：公式里用到的字段（如 m_/ID_/fund_/market_cap/turnover/industry）在求值命名空间中是否真的被注入（对照 factor_operators/求值入口代码）。 报告格式（控制在 600 字以内的结论 + 失败明细表）： - 统计摘要（成功/失败/缺数据） - 失败明细：因子名 | 公式片段 | 错误信息 | 归类 - 你使用的求值入口函数全名（文件:行号），证明你走的是生产同一路径 - 任何你发现的可疑设计问题（如错误被静默吞掉、结果缓存掩盖失败等）

2026-08-30 23:12

I'll start by reading the key source files to understand the database schema, factor evaluation entry points, and operator namespace.

3执行工具 3 次

Now let me find the factor evaluation entry point used in production (routes/factor.py or factor_research.py):

2执行工具 2 次

Let me look at the main production evaluation path in factor_research.py around line 1573:

2执行工具 2 次

Now let me understand the data loading functions and check what parquet files look like:

2执行工具 2 次

I notice there's no `formula` column in `preset_factors`. Let me check how formulas are stored - perhaps in the `factors` table or in the description:

1执行工具 1 次

The formulas are embedded in the `description` field. Let me check how they're extracted:

5执行工具 5 次

Now I have a thorough understanding. Let me also check the `eval_formula_on_local` static method signature:

1执行工具 1 次

It's an instance method, not static. Let me check if there's a standalone function version or how routes call it:

4执行工具 4 次

Good. Now I have the full picture. Let me also check how fundamental panels are loaded:

1执行工具 1 次

Now I have enough understanding. Let me write the audit script:

3执行工具 3 次

The output is very long with warnings. Let me redirect stderr and just get the results:

1执行工具 1 次

Excellent! Now I have the full results. Let me do a deeper analysis of the failure patterns to properly reclassify them:

2执行工具 2 次

Now I see the key pattern. The `ADV(n)` calls in Alpha101 formulas use a single-argument form (`ADV(20)`) meaning "20-day average volume", but the operator definition requires two arguments: `ADV(volume, n)`. This is an API mismatch -- the namespace provides `adv20` as a pre-computed panel but doesn't provide a single-arg `ADV()` wrapper.

Let me also check what happens with `RETURNS` used as a bare name (not `RETURNS(x,n)`):

1执行工具 1 次

Now I understand the root causes clearly:

1. **`ADV(n)` single-arg form**: Alpha101 formulas use `ADV(20)` meaning "20-day average volume", but the operator is defined as `ADV(volume, n)` requiring two args. The namespace provides pre-computed `adv20`/`ADV20` panels but no single-arg ADV wrapper. This is a **semantic API mismatch** -- 33 factors affected.
2. **`RETURNS` as bare name**: Some formulas use `RETURNS` (the function) where they mean the returns *panel*. In the namespace, `RETURNS` maps to the function `RETURNS(x, n)`, while the panel is at `RETURNS_` / `ret`. When formulas do `SUM(RETURNS, 240)`, it passes the function object instead of the panel. This is another **naming collision** -- ~12 factors.
3. **Other issues**: A few individual formula bugs.

Let me now precisely count each pattern and verify the static classifier's accuracy:

2执行工具 2 次

This is a critical finding. The static classifier marks 275 factors as "executable" but actual evaluation shows **50 of them fail at runtime**. The static classifier only checks syntax (AST parse) and name existence in the namespace, but misses:

1. `ADV(n)` -- passes AST parse (valid function call), name `ADV` exists in namespace, but fails because it needs 2 args not 1
2. `RETURNS` used as panel -- name exists (as function), but formula expects it to be a DataFrame
3. Other argument-count / type mismatches

Let me get precise counts for each root cause pattern:

2执行工具 2 次

Now let me verify the field injection check (task 5):

1执行工具 1 次

Important finding: `returns` (lowercase) maps to the **function** not the panel. The panel is at `RETURNS_`, `ret`, and `RET`. This confirms the collision. Let me also verify that `market_cap` and `turnover` are None because no such panels were passed (they'd need to come from external data):

1执行工具 1 次

Now let me verify the exact line numbers for the production entry point:

1执行工具 1 次

I now have all the data needed for the report. Let me compile it.

------

## 审查报告：预置因子公式可执行性现状

### 统计摘要

| 指标                          | 数量    |
| :---------------------------- | :------ |
| 预置因子总数                  | 622     |
| 有公式                        | 276     |
| 无公式（参数化/字段型）       | 346     |
| **求值成功**                  | **211** |
| **求值失败**                  | **65**  |
| -- 语法/方言错误              | 1       |
| -- 算子API不匹配(ADV/RETURNS) | 41      |
| -- 其他运行时错误             | 9       |
| -- 数据缺失(分钟缓存)         | 14      |

**成功率：211/276 = 76.4%**（有公式的因子中）；整体 211/622 = 33.9%。

### 使用的求值入口

- `FactorResearchService.eval_formula_on_local()` — `backend/services/factor_research.py:1546`
- 内部调用 `build_operator_namespace()` (`factor_operators.py:1019`) + `eval_factor_formula()` (`factor_operators.py:32`)
- 与 Web API (`routes/factor.py:811,902`) 走完全相同路径

### 失败明细（50 个日频公式错误 + 14 个分钟数据缺失 + 1 个语法错误）

**A. ADV(n) 单参数形式不兼容（29 个）** — Alpha101 公式用 `ADV(20)` 表示"20日均量"，但算子定义为 `ADV(volume, n)` 双参数。命名空间提供了预计算面板 `adv20`/`ADV20`，但没有单参数包装器。

| 因子     | 公式片段                            | 错误                             |
| :------- | :---------------------------------- | :------------------------------- |
| alpha007 | `IF((ADV(20) < VOLUME),...)`        | ADV() missing 1 required arg 'n' |
| alpha017 | `VOLUME / ADV(20)`                  | 同上                             |
| alpha025 | `RETURNS * ADV(20)`                 | 同上 (+ RETURNS碰撞)             |
| alpha028 | `CORRELATION(ADV(20), LOW, 5)`      | 同上                             |
| alpha031 | `SCALE(CLOSE, ADV20)` ... `ADV(20)` | 同上                             |
| alpha036 | `ADV(20)` + bare `RETURNS`          | 同上                             |
| alpha039 | `VOLUME / ADV(20)`                  | 同上                             |
| alpha043 | `VOLUME / ADV(20)`                  | 同上                             |
| alpha047 | `/ ADV(20)`                         | 同上                             |
| alpha063 | `ADV(180)`                          | 同上                             |
| alpha067 | `INDUSTRY_NEUTRALIZE(ADV(20))`      | 同上                             |
| alpha069 | `ADV(20)`                           | 同上                             |
| alpha070 | `ADV(50)`                           | 同上                             |
| alpha071 | `ADV(180)`                          | 同上                             |
| alpha072 | `ADV(40)`                           | 同上                             |
| alpha076 | `ADV(81)`                           | 同上                             |
| alpha077 | `ADV(40)`                           | 同上                             |
| alpha078 | `ADV(40)`                           | 同上                             |
| alpha080 | `ADV(10)`                           | 同上                             |
| alpha085 | `ADV(30)`                           | 同上                             |
| alpha087 | `ADV(81)`                           | 同上                             |
| alpha088 | `ADV(60)`                           | 同上                             |
| alpha089 | `ADV(10)`                           | 同上                             |
| alpha090 | `ADV(40)`                           | 同上                             |
| alpha091 | `ADV(30)`                           | 同上                             |
| alpha092 | `ADV(30)`                           | 同上                             |
| alpha093 | `ADV(81)`                           | 同上                             |
| alpha094 | `ADV(60)`                           | 同上                             |
| alpha096 | `ADV(60)`                           | 同上                             |
| alpha097 | `ADV(60)`                           | 同上                             |
| alpha098 | `ADV(5)`                            | 同上                             |
| alpha100 | `ADV(20)`                           | 同上                             |

**B. RETURNS 函数/面板命名碰撞（9+3=12 个）** — `returns`/`RETURNS` 在命名空间中映射到函数 `RETURNS(x,n)` 而非收益面板。公式中裸用 `RETURNS` 时传入的是函数对象。面板实际注册在 `ret`/`RET`/`RETURNS_`。

| 因子     | 公式片段                                        | 错误                               |
| :------- | :---------------------------------------------- | :--------------------------------- |
| alpha001 | `IF((RETURNS < 0), STDDEV(RETURNS, 20), CLOSE)` | '<' not supported: function vs int |
| alpha008 | `SUM(RETURNS, 5)`                               | 'function' has no attr 'rolling'   |
| alpha014 | `DELTA(RETURNS, 3)`                             | 'function' has no attr 'shift'     |
| alpha019 | `SUM(RETURNS, 250)`                             | 同上                               |
| alpha029 | `DELAY((-1 * RETURNS), 6)`                      | unsupported *: int * function      |
| alpha034 | `STDDEV(RETURNS, 2)`                            | 'function' has no attr 'rolling'   |
| alpha035 | `TS_RANK(RETURNS, 32)`                          | 同上                               |
| alpha052 | `SUM(RETURNS, 240)`                             | 同上                               |
| alpha056 | `SUM(RETURNS, 10)` / `RETURNS * CAP`            | 同上                               |

**C. 其他公式级错误（9 个）**

| 因子             | 公式片段                                        | 错误                       | 归类                   |
| :--------------- | :---------------------------------------------- | :------------------------- | :--------------------- |
| alpha191_023     | `sma((close>delay(close,1)?std(close:20),0)...` | unmatched ')'              | a) 语法                |
| alpha191_190     | `close/delay(close)-1` (DELAY缺参)              | DELAY() missing arg 'n'    | b) 算子误用            |
| alpha191_183     | `sumac(close-mean(close,24))` (SUMAC缺参)       | SUMAC() missing arg 'n'    | b) 算子误用            |
| alpha191_165     | `sumac(close-mean(close,48))`                   | 同上                       | b) 算子误用            |
| alpha191_036     | `corr(rank(volume), rank(vwap)), 6), 2)`        | CORR() missing arg 'n'     | b) 算子误用            |
| alpha191_010     | `max(IF(...)**2, 5)`                            | MAX() missing arg 'b'      | b) 算子误用(MAX需双参) |
| alpha191_144     | `sumif(abs(...)/amount,20,close<...)`           | 'int' has no attr 'where'  | b) SUMIF参数序错       |
| alpha191_166     | `(20-2)(sum(...)` → tuple**int                  | tuple pow error            | a) 隐式乘法翻译缺陷    |
| alpha191_137/055 | `IF(...)&...` float & float                     | unsupported &: float&float | a) 规范化后&运算类型错 |

**D. 数据缺失（14 个 INTRADAY 因子）** — 本地无 5m 分钟缓存，全部 INTRADAY 类因子无法求值。这不是公式错误。

### 可疑设计问题

1. **静态分类器过于乐观**：`classify_formula_status()` (`factor_research.py:143`) 只做 AST 解析 + 名字存在性检查，将 275 个因子标记为 `executable`，但实际有 50 个在运行时失败。它不验证参数数量/类型兼容性。DB 中存储的 `formula_status` 与此一致（0 mismatch），说明状态从未被实际求值校正过。
2. **`RETURNS` 命名冲突未解决**：`build_operator_namespace()` 第 1195 行把 `RETURNS` 注册为函数（`RETURNS = RETURNS`），同时第 1099-1103 行把面板注册为 `returns`（小写也被第 1305 行的别名循环覆盖为函数）。Alpha101 原始公式中 `RETURNS` 是面板变量名，不是函数调用。修复方案：增加一个 `RETURNS` 面板别名或让规范化层把裸 `RETURNS` 替换为 `ret`。
3. **`ADV(n)` 单参形式未适配**：Alpha101 规范中 `ADV(n)` = n日均量，但算子只有 `ADV(volume, n)`。修复方案：增加单参数重载或在规范化层把 `ADV(n)` 翻译为 `adv{n}`。
4. **错误被正确结构化但未反馈到 DB**：`FormulaError` 有 code/message 结构，eval 路径也正确捕获并返回，但结果从不回写 `formula_status` 列——该列只在 seed/import 时由静态分类器设置，运行时发现的错误不会更新状态。