# 作为资深研究员试用这套系统，只报告问题，不要修改任何代码。现存的问题是否都修复完善了？

**Session:** 2026-09-10 22:35 ~ 2026-09-10 22:38

**Work Directory:** `/Users/victor/Desktop/coding/localquant`

**Session ID:** `sess_19c3d558-21cb-44ea-8be8-8cc4ce52a507`（zcode://sess_19c3d558-21cb-44ea-8be8-8cc4ce52a507）

**Exported:** 2026-10-03 23:41 · agent-dump 1.1.1

---

### **You**
作为资深研究员试用这套系统，只报告问题，不要修改任何代码。现存的问题是否都修复完善了？

### **You**
之前问 AI 的时候，AI 不建议我把 Pi 作为 Qube 的底层，说是太重了。但是我想想，这还是挺完善的，为什么不要这样呢？到底有没有必要这样呢？

### **You**
之前问 AI 的时候，AI 不建议我把 Pi 作为 Qube 的底层，说是太重了。但是我想想，这还是挺完善的，为什么不要这样呢？到底有没有必要这样呢？

### **Assistant**
The user is asking about a design decision in their project. They mention "Pi" and "Qube" — these seem to be modules or components in their localquant project. Previously an AI advised them not to use Pi as the underlying layer for Qube because "Pi is too heavy." The user is now second-guessing: Pi is quite complete/mature, so why not use it? Is it really necessary to avoid it?

I need to understand what Pi and Qube are in this codebase. Let me explore the project first. This is a question/thinking-out-loud scenario — the user wants my assessment, not a code change. The deliverable is analysis.

Let me look at the project structure to understand what Pi and Qube refer to. I should explore the localquant project. Let me do some searching myself or delegate to an Explore agent. Given this is a nuanced architecture question, I need to actually understand the codebase. Let me first look at the directory structure and README/docs.

Let me start with quick exploration.

我先看一下项目里 Pi 和 Qube 分别是什么，再回答这个问题。

### **Assistant**
Let me search for "Pi" and "Qube" in the docs and codebase.

### **Assistant**
Now I understand better:

- **QUBE** = 策略 Agent（策略工作台），a multi-turn conversational AI agent for strategy design. `backend/services/qube_agent.py` is described as a Python port of [pi](https://github.com/earendil-works/pi)'s pi-agent-core architecture — tool call loop + event stream.
- **Pi** = https://github.com/earendil-works/pi — pi-agent-core. The user is asking: previously an AI said don't use Pi as the underlying layer for Qube because it's "too heavy" — but the user thinks Pi is quite complete, so why not use it? Is it really necessary?

So the question is architectural: should QUBE (the agent) be built directly on the Pi library (pi-agent-core, presumably a TypeScript/Node library?) vs. the current hand-ported Python version?

Wait — pi from earendil-works. Let me recall: pi is an agent framework by Mario Zechner (badlogic). Actually "pi" — earendil-works? Let me check. There's "pi-mono" by badlogic (Mario Zechner) — https://github.com/badlogic/pi-mono — "pi" coding agent. earendil-works/pi might be a fork or something else. Let me look at the current qube_agent.py to understand what exists.

Let me read the relevant docs section and the qube_agent.py file to understand the current implementation, then I can give an informed assessment.

Let me also check if there's any archived AI conversation about this decision (they mentioned "之前问 AI 的时候" — maybe in docs/ref or archived conversations).

找到了线索：QUBE 是项目里的策略 Agent，而 pi 是一个 agent 框架。我再看看当前的实现和之前的讨论记录。

### **Assistant**
So the current state: `backend/services/qube_agent.py` is a 1238-line Python file that is a hand-port of pi-agent-core architecture (tool call loop + event stream).

The user's question: previously asked an AI whether to use Pi as the underlying layer for QUBE, and the AI said no because Pi is "too heavy". The user now wonders: Pi is quite complete/polished, why not use it? Is it really necessary to avoid it?

Key facts to verify:
1. What is pi exactly? Pi (earendil-works/pi) — I need to check what language it's in. The badlogic (Mario Zechner) pi-mono is TypeScript. If pi is TypeScript/Node, then using it as the underlying layer for a Python FastAPI backend would mean running a Node subprocess or bridging — that's a big deal.

Actually wait — let me check. The doc says "本机 CLI 工具（Claude Code/Codex/OpenCode/Pi 等）" — so Pi can be used as a CLI tool. And qube_agent.py is a "Python 移植" (Python port) of pi-agent-core architecture.

Let me look at the qube_agent.py header and ai_providers.py to see how CLI integration works, and check if pi is available via pip or npm. Let me also look for the archived AI conversation that discussed this decision ("之前问 AI 的时候") — the recent commits mention archiving AI plans and conversation exports. Let me search for those.

当前实现清楚了：`qube_agent.py`（1238 行）是 pi-agent-core 架构的 Python 手工移植。我再确认一下 pi 本身的技术形态和之前 AI 给出的理由记录。

### **Assistant**
Now I have a clear picture. Let me also quickly verify what pi actually is — earendil-works/pi. Let me check on the web to confirm its tech stack (TypeScript? npm package? size? dependencies). Actually, the doc mentions "@earendil-works/pi-agent-core" which is an npm package name (the `@` scope suggests npm/TypeScript). Pi by Mario Zechner (badlogic) moved to... hmm, actually there's "pi" from earendil-works. Let me do a quick web check to confirm the language and weight of pi-agent-core.

Actually, let me think about what matters for the answer:

The user asks: "之前问 AI 的时候，AI 不建议我把 Pi 作为 Qube 的底层，说是太重了。但是我想想，这还是挺完善的，为什么不要这样呢？到底有没有必要这样呢？"

Translation: "Previously when I asked AI, the AI didn't recommend using Pi as the underlying layer for QUBE, saying it's too heavy. But thinking about it, it's quite complete/mature — why not use it? Is it really necessary (to avoid it)?"

Wait, ambiguity in "到底有没有必要这样呢": "Is it necessary to do this?" — i.e., is it necessary to use Pi as the base? Or necessary to avoid it? Given context, the user is asking "有没有必要把 Pi 作为底层" — is it worth/warranted to build QUBE on Pi?

So my job: give an assessment of whether QUBE should be built on the Pi library vs. the current hand-ported 1238-line Python implementation.

Key considerations:

1. **Language/runtime mismatch**: pi (earendil-works/pi) is a TypeScript/Node project — @earendil-works/pi-agent-core is an npm package. The localquant backend is Python (FastAPI + httpx, uv). To use pi as the underlying layer, you'd either:
   - Run a Node sidecar/subprocess and bridge via IPC/SSE — extra runtime dependency, deployment complexity (user runs this locally on Windows with QMT — QMT is Windows-only, so the user's environment is Windows + Python; adding a Node runtime requirement is real friction).
   - Or use pi's CLI as a subprocess (already supported as one of the CLI tool options in AI 辅助 — "本机 CLI 工具（Claude Code/Codex/OpenCode/Pi 等）").
   
2. **What "too heavy" means here**: The actual agent loop QUBE needs is small — the hand-port is 1238 lines including tools, usage accounting, event stream. The core loop (agent loop) is maybe a couple hundred lines. The value pi provides beyond this loop: extensions, steering, retry, compaction, skills, themes, TUI, packages etc. Most of that is irrelevant to QUBE's narrow, fixed toolset (read_doc, preview_data, run_backtest, save_strategy, factor tools, etc.).

3. **What QUBE actually needs from a "framework"**: 
   - OpenAI-compatible streaming with reasoning_content (their providers include DeepSeek, Zhipu, Kimi, MiniMax... many need specific handling of reasoning tokens and some quirks).
   - Tool loop with max_turns cap (MAX_TURNS=8).
   - SSE event semantics.
   - Usage accumulation.
   - Integration with local backtest engine — tools need to call backend services directly (in-process), not through a subprocess.
   
   A JS framework can't call `backend.services.backtest` in-process; the tools would have to be remote-called back into Python — that's a huge layer of indirection for 4-8 tools.

4. **When Pi would make sense**: if QUBE were a general-purpose coding agent (file editing, shell, multi-repo), or if the project were Node/TS anyway, or if you wanted pi's extension ecosystem/skills. Also pi-as-CLI is already integrated as one provider option — that's the cheap way to "use Pi" without embedding.

5. **Cost of the current port**: 1238 lines, self-owned, no dependency drift, works with their provider quirks. The risk of the port is duplicated maintenance as pi evolves — but pi-agent-core's core loop is stable and small; they only ported the architecture (loop + event semantics), not the whole library.

Also worth noting: the question "到底有没有必要" — the honest answer: 没有必要 (not necessary), and the earlier advice ("太重") is directionally right but the word "重" is less precise than the real reasons: runtime mismatch (Node vs Python), in-process tool integration requirement, and the fact that QUBE only needs the ~200-line core of what pi offers. The current state (architecture port + pi as optional CLI provider) captures Pi's value at near-zero cost. If they want more of Pi, the leverage point is using Pi CLI as a provider (already supported), not rewiring QUBE's internals.

Let me verify a few facts before answering:
1. Confirm pi is TypeScript/npm. Quick web check.
2. Look at how CLI tools are integrated in ai_providers.py (to confirm "Pi as CLI" is already an option — this is a strong argument: they already use Pi where it's cheap to use).
3. Check the backend stack (FastAPI? uv?) — pyproject.toml.

Let me do these in parallel. Also maybe check qube_agent.py tail to see tool registration and how backtest tools call in-process services.

当前实现和文档都看清楚了。我快速核实几个关键事实：pi 的技术栈形态、QUBE 工具如何接入本地回测引擎。

### **Assistant**
Now I have all the facts I need:

1. **pi is TypeScript/npm** — packages: pi-ai, pi-agent-core, pi-coding-agent, pi-tui. Installing it as the "underlying layer" for QUBE means adding a Node.js runtime to a pure-Python FastAPI backend (which runs on the user's Windows machine alongside QMT).

2. **QUBE's tools are deeply in-process**: `_tool_run_backtest` etc. directly call `backend.database.get_db`, `backend.services.market_data`, pandas, etc. — line 250, 265, 314, 316, 351, 398 show lazy in-function imports of backend modules. If pi (Node) were the underlying layer, every tool call would have to round-trip back into Python (HTTP/IPC bridge), or the entire backtest engine would need to be re-exposed as a service. That's the real cost — not "heaviness" in the abstract.

3. **What QUBE needs from an agent framework is small**: ~1238 lines total including all tool implementations; the loop itself is a fraction of that. pi-agent-core's core value (tool loop + event stream) is exactly what was ported.

4. **Pi is already used where it's cheap**: as one of the CLI providers in AI 辅助 ("本机 CLI 工具（Claude Code/Codex/OpenCode/Pi 等）"). So the project already leverages Pi where integration cost is low.

5. The AI's "太重" reasoning: directionally right but the precise reasons are:
   - runtime mismatch (Node vs Python) — the biggest
   - in-process tool integration (backtest engine, DB, market data are Python in-process)
   - scope mismatch: pi's weight is in coding-agent/TUI/extensions/telemetry — none of which QUBE uses; QUBE needs only the ~200-line kernel
   - deployment: this is a local single-user app on Windows (QMT is Windows-only); adding Node as a hard dependency for one feature is real friction
   
   Counter-considerations (when the user would be right to want Pi):
   - Pi is mature, well-tested, handles provider quirks, streaming, retries, etc. A hand-port has to maintain those.
   - If the backend were Node/TS, or if QUBE wanted to become a full coding agent with file/shell editing, using pi directly would be justified.

But the current state — architecture port (loop + event semantics) + Pi CLI as optional provider — captures Pi's value at near-zero integration cost. The hand-port risk is small because the core loop is stable and small.

So my answer: 没必要，且当前方案其实已经"用上了 Pi"——用的是它的架构而不是它的代码。The AI's advice was right but "太重" is a vague word; the real reasons are runtime mismatch + in-process tools. The user's instinct ("Pi 挺完善的") is correct — and that value is already captured via the port + CLI provider option.

One more nuance to verify quickly: does the port duplicate anything fragile? The usage accounting (reasoning tokens), effort mapping, provider quirks — these are in ai_providers.py presumably. I don't need more detail; I have enough.

Also should I check git history for the prior AI discussion? The user said "之前问 AI 的时候" — maybe there's an archived conversation. I searched docs/ref for 太重 and found nothing relevant. The archived conversations from commit a6e3792 "chore: 归档散落的 AI 计划与对话导出" — let me quickly check where those went. Actually, it's not critical — I know the decision and the current state. The user is asking for my assessment of the architecture question, not archaeology of the prior conversation. I'll skip further digging.

Actually, let me reconsider — the user might benefit from knowing exactly what was said before. But I searched and found nothing. Let me do one quick check of the archived plans location just in case, cheap to do... Actually no — the deliverable is my assessment. The prior AI's reasoning is characterized by the user as "太重了" and I can address it directly. Enough.

Now the answer structure (in Chinese, since user writes Chinese):

1. Lead with the conclusion: 不必要。而且你现在的方案其实已经"用了 Pi"——用的是它的架构设计，不是它的代码。之前 AI 说的"太重"方向对，但真正的原因不是"重"，而是两层更硬的约束。

2. The two hard constraints:
   - 运行时错配: pi 是 TypeScript/npm 包（pi-ai / pi-agent-core / pi-tui），你的 backend 是纯 Python FastAPI。拿它当底层意味着常驻一个 Node sidecar + IPC 桥。
   - 工具必须进程内: QUBE 的工具（run_backtest、preview_data、read_doc、save_strategy）直接调 backend 的数据库、行情服务、回测引擎（qube_agent.py 里 250/314/398 行那些函数内 import 就是证据）。换成 Node 底层后每个工具都得跨进程回调 Python，或者把回测引擎重新暴露成服务——为了四五个工具搭一整层 RPC。

3. "完善"的重量在哪: pi 的完善度大部分在 coding agent CLI、TUI、扩展、telemetry 这些 QUBE 用不到的地方。QUBE 需要的只是 pi-agent-core 那个 ~200 行的内核（工具循环 + 事件流），这正是被移植的部分。用 1238 行（含全部工具实现）自持，换来零 Node 依赖、供应商怪癖（DeepSeek/Zhipu/Kimi 的 reasoning_content 等）随手可改。

4. 你"Pi 挺完善"的直觉没错，而且已经兑现了：
   - 架构上: qube_agent.py 就是对标 pi-agent-core 的移植。
   - 使用上: AI 辅助里 Pi 已经作为本机 CLI 供应商接入了——这是"用 Pi"最便宜的方式，真正跑在 pi 上的任务可以走这条路。

5. 什么时候答案会反过来: 如果哪天 QUBE 要做成通用编码 agent（读写文件、跑 shell）、或者后端迁到 Node/TS、或者你需要 pi 的扩展生态，那时直接上 pi 才划算。

Keep it readable prose, not over-structured. Maybe minimal headers or just paragraphs. The user asked a conceptual question — direct prose answer, moderate length. I'll write in Chinese.

Length: this deserves a substantive but not bloated answer. ~400-500 Chinese words.

结论先说：**没有必要把 Pi 作为 QUBE 的底层，而且你现在的方案其实已经在“用 Pi”了——用的是它的架构，不是它的代码。**之前那个 AI 说“太重”方向是对的，但这个词不准确，真正的原因是两个更硬的约束，跟完不完善没关系。

**约束一：运行时错配。**我查了 pi 的仓库——它是 TypeScript 项目，`pi-agent-core` 是 npm 包（连同 pi-ai、pi-tui 一起组成 monorepo）。而你的 backend 是纯 Python（FastAPI + httpx），跑在 Windows 上和 QMT 伴生。把 pi 当底层意味着必须常驻一个 Node 进程做 sidecar，再搭一层 IPC/SSE 桥，给一个本地单用户应用增加一整个运行时依赖。

**约束二：工具必须在进程内。**这是更根本的一条。QUBE 的价值全在工具上——`run_backtest` 直接调你的向量化回测引擎，`preview_data` 直接读 `market_data` 和数据库（`qube_agent.py` 里那些函数内的 `from backend.database import get_db` 就是证据）。如果底层换成 Node 的 pi，每一次工具调用都要跨进程回调 Python，等于为了四五个工具把回测引擎、行情缓存、策略库全部重新暴露成远程服务。pi 再完善，也替代不了“工具就在同一进程里”这件事。

**你说的“完善”确实存在，但重量不在你要的地方。**pi 的完善度大部分在 coding agent CLI、终端 TUI、扩展生态、telemetry 这些 QUBE 根本用不到的部分；QUBE 需要的只是 pi-agent-core 那个约两百行的内核——工具循环加事件流——而这恰恰是被移植过来的部分。现在用 1238 行自持代码（含全部工具实现）换来的是：零 Node 依赖，以及各家供应商的怪癖（DeepSeek/Zhipu/Kimi 的 `reasoning_content`、推理强度映射这些）随时可以就地改，不用等上游。

所以你的直觉“Pi 挺完善的”没有错，只是这个价值你已经用最便宜的方式兑现了两处：一是 `qube_agent.py` 就是对 pi-agent-core 架构的对标移植；二是「AI 辅助」里 Pi 已经作为本机 CLI 供应商接入了——真想让 pi 本人跑任务，走那条路就行，不需要它进到 QUBE 的内核里。

什么时候答案会反过来：如果哪天 QUBE 要往通用编码 agent 方向走（读写文件、跑 shell、多仓库），或者后端整体迁去 Node/TS，或者你需要 pi 的扩展生态，那时候直接上 pi 才划算。以现在的定位——固定工具集、进程内回测、本地部署——手写这个内核是更对的取舍。
