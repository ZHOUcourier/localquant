# Selection side chat

**Session:** 2026-10-03 14:52 ~ 2026-10-03 14:54

**Work Directory:** `/Users/victor/Desktop/coding/localquant`

**Session ID:** `sess_bd13688f-d1e8-4e96-9da8-867c87f39d09`（zcode://sess_bd13688f-d1e8-4e96-9da8-867c87f39d09）

**Exported:** 2026-10-03 23:41 · agent-dump 1.1.1

---

### **You**
分钟级高频如何建设。localquant/docs/ref/一个30分钟价量熵 这个因子不错，可以把它加进来（分钟级高频）。这个是来自 quantzone ，这个平台似乎对高频因子颇有研究。解释的时候，请完善解释一下整个分钟级高频流程如何构建。比如，解释我要进行常见的量化，就是需要采用因子投资的方法，即找因子，然后根据这些理论一些模型，验证，回测等等。只说不做

### **You**
The preceding conversation was inherited from the parent task for reference only. Do not continue the parent's active work automatically; answer only new questions sent in this side chat. Modify the workspace only when the user explicitly asks you to do so in this side chat.

### **You**
这个 qmt 是只能在他提供的框框里面写入策略代码，还是说我也可以只管自己运行，只要向他发送交易请求就可以？

### **Assistant**
Let me parse the user's questions. There are two parts:

1. The first message (from the parent task context): "分钟级高频如何建设。localquant/docs/ref/一个30分钟价量熵 这个因子不错，可以把它加进来（分钟级高频）。这个是来自 quantzone...解释的时候，请完善解释一下整个分钟级高频流程如何构建...只说不做" — this is marked as inherited context, "Do not continue the parent's active work automatically; answer only new questions sent in this side chat."

2. The NEW question in this side chat: "这个 qmt 是只能在他提供的框框里面写入策略代码，还是说我也可以只管自己运行，只要向他发送交易请求就可以？"

So the actual question I need to answer is about QMT (迅投QMT, a Chinese quantitative trading platform used with brokers like 国金, 国盛, etc.): Is QMT only able to run strategies written inside its own built-in strategy editor ("框框里面写入策略代码"), or can the user run their own code externally and just send trading requests to QMT?

This is a knowledge question about QMT's architecture. Let me think about what I know:

QMT (迅投 miniQMT / QMT) has two main modes:

1. **内置策略模式 (built-in strategy mode)**: You write Python strategy code inside the QMT client's strategy editor ("策略开发" panel). The strategies run inside QMT's embedded Python environment. You use the built-in `ContextInfo` API, event-driven framework (handlebar, init, etc.).

2. **miniQMT 模式 (external mode)**: QMT provides a "极简模式" (miniQMT) where the QMT client acts as a gateway/server. External Python processes can connect to it:
   - **xtquant library**: The official Python library (xtdata for market data, xttrader for trading). Your own code runs anywhere (your own Python environment), and connects to the running miniQMT client via a session path (user data path). Orders are sent through `xttrader` API.
   - This is exactly "自己运行，只要向他发送交易请求" — yes, this is possible via miniQMT + xtquant.

Requirements:
- The broker must provide QMT/miniQMT access (e.g., 国金证券 QMT, 国盛, 华鑫 with奇点, etc.). Usually requires applying for quantitative trading permission (开通量化权限), often with minimum capital requirements (varies, e.g., 国金 ~50万? Actually different brokers have different thresholds; some have low or no threshold now).
- miniQMT (极简模式) needs to be running/logged in for xtquant to connect. The user data path (userdata_mini) is used to establish the session.
- xtquant provides xtdata (market data, including tick, minute bars) and xttrader (trading: order, cancel, query positions/deals/assets).
- Connection: `XtQuantTrader(path, session_id)` where path is the userdata_mini path; MiniQmtClient... Also `xttrader` supports both mini mode and 投研版.
- Note: miniQMT mode — the strategy logic runs in YOUR process; QMT just executes orders. Market data can come from xtdata (via the QMT client's data connection) or your own data source.
- There's also the built-in strategy mode where code runs inside QMT — subject to QMT's Python version (embedded), and the code editor.
- Additionally, some people use Ptrade (another platform, 恒生) which is strictly in-platform. QMT specifically supports the external model via miniQMT + xtquant.

Also worth noting:
- In the built-in mode, you can also use `passorder` etc. But external control is officially supported through xtquant (迅投官方库) — it's not hacking; it's the sanctioned way.
- Versions: QMT client with 极简模式 (miniQMT) — login window has "极简模式" checkbox. The installed client must support it (most broker-distributed QMT do now).
- Also there's "投研版" vs "正式版" distinctions for xtquant trading. And session_id must be unique; only certain number of concurrent sessions (I recall miniQMT supports limited concurrent connections, like 3? Not sure — better not to state uncertain specifics).
- Alternative: Some brokers offerOpenD-like gateways? For QMT, xtquant is the way.

Since the user is in the localquant project (a local quant system on macOS? Actually darwin platform — but QMT is Windows-only! That's an important caveat: QMT/miniQMT client runs on Windows. On Mac you'd need a Windows VM/remote Windows machine. xtquant itself is a Python lib that can run on... I believe xtquant is Windows-focused; the client definitely is Windows-only. xtquant lib may work on non-Windows for xtdata? Actually xtquant historically ships Windows wheels only (py3.6-3.12?), though recent versions may support Linux/mac for data? I recall xtquant on PyPI supports Linux and macOS for xtdata? Hmm — xtquant on pypi: "迅投xtquant" — I believe there are Linux builds, and macOS support is limited/absent for xttrader. Safer: QMT client is Windows-only; typical setups run it on a Windows machine/VPS and connect remotely... but xttrader connects via local userdata path, so remote requires the strategy process on the same Windows machine (or wine workarounds). Actually you can run strategy code on the same Windows box; remote order sending is not natively supported over network (the xttrader connects to the local miniQMT via shared memory/local IPC through the userdata path). So the architecture: your strategy process must run on the same Windows machine as miniQMT. Many people then bridge it with their own HTTP/WebSocket gateway to a remote research environment.

Given the localquant repo is on macOS (darwin), this caveat is relevant: they'd need a Windows environment.

Should I check the repo for QMT-related docs? The question is conversational ("只说不做" was the parent's instruction — explain, don't implement). The side chat question: "这个 qmt 是只能在他提供的框框里面写入策略代码，还是说我也可以只管自己运行，只要向他发送交易请求就可以？"

I could answer from knowledge. But maybe the repo has docs about QMT (localquant/docs). Let me quickly check the repo for QMT-related references to ground the answer in their setup. The parent context mentions localquant/docs/ref/. A quick grep for "qmt" in docs would be cheap and could ground the answer. That seems worthwhile.

Let me do a quick search: grep -ri "qmt" in the repo docs. Use Bash or the Explore agent? It's a single quick lookup — do it directly with a fast grep command.

Then answer:

**Answer structure:**
- Lead: 两种模式都支持。QMT 不是只能在内置编辑器里写策略——官方提供了 miniQMT（极简模式）+ xtquant 库，你的策略代码可以在自己的 Python 环境里运行，通过 xttrader 向 QMT 发交易请求；QMT 只充当行情+下单通道。
- 内置模式: 策略编辑器里写代码，跑在 QMT 内嵌 Python，事件驱动框架（init/handlebar），适合简单场景；Python 版本受限、库受限、调试不便。
- 外部模式 (miniQMT): 客户端勾选极简模式登录；本地 Python 装 xtquant；xtdata 拉行情（tick/分钟线），XtQuantTrader + StockAccount 下单撤单查持仓；策略进程与 miniQMT 客户端在同一台 Windows 机器上（通过 userdata_mini 路径建立会话，本质是本地 IPC，不是网络接口）。所以“自己运行、只发交易请求”是官方支持的正路，不是 hack。
- 条件/注意事项: 
  - 券商开通 QMT 权限（资金门槛各券商不同）；
  - QMT 客户端 Windows only，需保持登录运行；你的策略进程必须在同一台机器上（想跨机器就自己包一层 HTTP/WebSocket 网关，把下单接口暴露给自己的研究环境——很多团队这么干）;
  - xtquant 版本要和客户端匹配；session_id 唯一；实盘前用模拟盘/小额测试。
  - 也可以混合：行情用你自己的数据源（比如你 localquant 已经有的分钟数据），只有下单走 xttrader。
- Relate to their localquant/分钟级高频 plan briefly? The side-chat question is only about QMT mode. Keep the answer focused but can add one line connecting: 对你的分钟级高频系统，推荐的就是外部模式——研究/回测/信号在 localquant 里做，实盘执行层通过 xtquant 发单。

Actually the user's earlier message said "只说不做" (only explain, don't do) for the 分钟级高频 topic. The current question is just about QMT's architecture. So answer in Chinese, prose, moderately detailed but not bloated.

Let me quickly check the repo for QMT mentions to ground it. I'll run a grep.

Actually, let me think about whether the search is needed. The question is purely about QMT's capability. A quick grep might reveal they already have QMT integration docs in the repo (e.g., a broker adapter). It's cheap. I'll do one grep command.

Let me run: `grep -ril "qmt" /Users/victor/Desktop/coding/localquant --include="*.md" -l | head -20` and maybe also search code. One command with both.

Then write the final answer.

Regarding accuracy of xtquant details:
- `xtquant` package: `xtdata` for data, `xttrader` for trading. Connect: `from xtquant.xttrader import XtQuantTrader; session = XtQuantTrader(r"path\userdata_mini", session_id); session.start(); connect_result = session.connect()`. Account: `from xtquant.xttype import StockAccount; acc = StockAccount('资金账号')`. Order: `session.order_stock(acc, '600000', xtconstant.STOCK_BUY, 100, xtconstant.FIX_PRICE, 10.5)`. Subscribe callbacks via `XtQuantTraderCallback` (on_stock_order, on_stock_trade, etc.). This is correct.
- Data: `xtdata.get_market_data`, subscribe_quote, download_history_data. Correct.
- miniQMT login: QMT 客户端登录界面勾选“极简模式”。The userdata path is typically `安装目录\userdata_mini`. Correct.
- Constraints: miniQMT 需要保持客户端在线；断线后 session 失效。xtquant 需要与其匹配的 Python 版本（支持 3.6–3.12 视版本）。Client is Windows-only. Correct.
- 并发 session 限制：官方说 miniQMT 最多支持 3 个 session? I recall "一个 miniQMT 最多允许 3 个 XtQuantTrader session 同时连接" — I'm not 100% sure. I'll phrase cautiously or omit.
- 投研版/正式版：xttrader 在正式版 miniQMT 下可实盘下单。Fine to omit.

Also mention: QMT 内置模式里也能干不少事，但框架事件驱动（handlebar 是 K 线驱动），对分钟级高频的 tick 级控制不灵活；外部模式自由度高，适合接你自己的研究栈。

One more consideration: the user might be conflating with Ptrade. Not needed.

Mac caveat: their environment is macOS (the localquant repo). QMT 客户端只有 Windows 版，所以实盘执行机得是 Windows（实体机、VPS 或虚拟机），localquant 的研究端在 Mac 上做，通过网关把信号传到 Windows 执行机。That's a load-bearing practical point for them.

Now, the search. Let me run it.

After the search, final answer in Chinese. Structure:
1. 直接回答：两种都可以，外部“只发交易请求”是官方支持的模式。
2. 内置模式简述。
3. 外部模式（miniQMT + xtquant）细节：怎么连、能做什么、限制（同机、Windows、客户端在线）。
4. 对你这套系统的落地建议一句（研究在 localquant，执行网关在 Windows 上跑 miniQMT，中间自己桥接）。

Keep it readable prose, maybe a short list. Not too long.

我先在仓库里快速看一下有没有已有的 QMT 相关资料，再回答。

### **Assistant**
The repo has QMT references. Let me check the README and the 分钟级别的量化 session doc briefly to see what their QMT context is.

### **Assistant**
The repo already uses xtquant for data (QMT data interface). The user's localquant system already integrates QMT as a data source (`QMT_PATH` / `QMT_DATA_DIR` — MiniQMT 客户端路径与数据目录, xtquant 仅 Windows).

Now the question: "这个 qmt 是只能在他提供的框框里面写入策略代码，还是说我也可以只管自己运行，只要向他发送交易请求就可以？"

Answer: Both modes exist. QMT has:
1. 内置策略模式 — write strategy code in the QMT client's strategy editor, runs inside QMT's embedded Python.
2. miniQMT（极简模式）+ xtquant — external mode. The client runs as a gateway; your own Python code runs in your own environment and connects via xtquant (xtdata for market data, XtQuantTrader for trading via the userdata_mini path). This is exactly "自己运行，只发交易请求" — officially supported, not a hack. Their localquant already uses xtdata for data this way.

Constraints:
- miniQMT client must be logged in and running on a Windows machine (QMT client is Windows-only; their README already notes xtquant 仅 Windows).
- XtQuantTrader connects via local IPC through the userdata_mini path — so the strategy process must be on the same machine as the miniQMT client. It's not a network API. To drive it from the Mac research side, they'd wrap a small gateway (HTTP/WebSocket) on the Windows box.
- Broker must grant QMT/量化权限.
- Trading: order_stock, cancel, query positions/assets; callbacks via XtQuantTraderCallback.
- session_id unique.

Also relevant: their README says the platform boundary is 普通股票多头, T+1, no leverage — xttrader supports normal stock orders fine.

Also mention: 内置模式的局限（嵌入式 Python、事件驱动 handlebar、调试不便、库受限），对分钟级高频不合适；推荐外部模式。And the parent conversation's plan already said "实盘时接 miniQMT" (from the 分钟级别的量化 doc) — consistent.

Keep answer concise, prose-first, in Chinese. Lead with the direct answer.

直接回答：**两种都可以，而且第二种（自己运行代码、只向 QMT 发交易请求）是官方支持的正路，不是绕过手段。** 你这套 localquant 现在其实已经在用第二种模式了——README 里写的 xtquant/MiniQMT 数据接口，走的就是这条路。

QMT 有两套使用方式：

**1. 内置策略模式（你说的“框框”）**
在 QMT 客户端的策略编辑器里写 Python，代码跑在 QMT 内嵌的 Python 环境里，用的是它的事件驱动框架（`init` / `handlebar` 等）。这个模式自由度低：Python 版本和第三方库受限、调试体验差、`handlebar` 本质是 K 线驱动，对分钟级/盘中实时控制很不灵活。一般只拿它做简单的东西。

**2. miniQMT（极简模式）+ xtquant——外部运行，只发指令**
QMT 客户端登录时勾选“极简模式”，它就退化成一个常驻网关，只负责连行情源和柜台。你的策略代码跑在你自己的 Python 环境里（3.6–3.12 视 xtquant 版本），通过官方库 `xtquant` 与它通信：

- `xtdata`：拉行情（tick、分钟线）和订阅推送——你 localquant 的数据层已经在用这个；
- `xttrader`：交易。`XtQuantTrader(userdata_mini路径, session_id)` 建立会话后，就能 `order_stock` 下单、撤单、查资金持仓，成交回报通过 `XtQuantTraderCallback` 推给你的进程。

信号计算、因子、调仓逻辑全在你的进程里，QMT 只当行情 + 下单通道。你之前那篇《分钟级别的量化》里写的“实盘时接 miniQMT”，指的就是这个。

几个关键限制要注意：

- **必须同机**：`XtQuantTrader` 是通过本地的 `userdata_mini` 路径做进程间通信建立的会话，**不是网络接口**。所以策略进程必须和 miniQMT 客户端跑在同一台 Windows 机器上。QMT 客户端只有 Windows 版（你的 README 也标注了 xtquant 仅 Windows）——你 Mac 上的研究端想实盘下单，常见做法是在 Windows 机上跑一个自己的薄网关（HTTP/WebSocket 服务，包一层 xttrader），Mac 侧把目标持仓差集推过去执行。
- **客户端必须保持登录在线**，断线会话就失效，所以实盘机要稳定常驻（很多人用一台 Windows VPS 或小主机专门干这个）。
- **券商侧**：需要开通 QMT/量化权限，各券商资金门槛不同，开通后一般会给你 miniQMT 登录入口。
- xtquant 版本要和客户端版本大致匹配；`session_id` 每个进程要唯一。

所以对你的架构来说结论很清晰：**研究、回测、因子计算留在 localquant（Mac 端），执行层是 Windows 机上一个独立的小进程（miniQMT + xtquant），输入“目标持仓 − 当前持仓”的差集，输出订单流**——正好就是你在执行层设计里已经定下的那个接口，QMT 在里面只扮演“下单 + 行情网关”的角色。
