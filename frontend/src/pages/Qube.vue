<script setup lang="ts">
/**
 * QUBE — 策略研究 AI Agent（复刻 pandaaiquant，opencode 视觉）
 *
 * 三栏：QUBE 次级侧边栏（会话/系统提示词/技能库/引擎设置）｜对话区
 * （空态模板卡 + timeline 消息 + 输入区+模型下拉）｜右侧画板（可拖拽调宽，
 * 按会话绑定 factor/strategy 自动切换 FactorBoard / StrategyWorkbench）。
 */
import { computed, nextTick, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  BookMarked,
  BrainCircuit,
  Minimize2,
  Download,
  MessageSquarePlus,
  PanelLeftOpen,
  PanelLeftClose,
  PanelRightClose,
  PanelRightOpen,
  Pencil,
  Pin,
  RefreshCw,
  Search,
  Send,
  Settings2,
  Sparkles,
  Square,
  Trash2,
  WifiOff,
} from 'lucide-vue-next'
import ChatMessage from '@/components/qube/ChatMessage.vue'
import EmptyState from '@/components/qube/EmptyState.vue'
import ModelBar from '@/components/qube/ModelBar.vue'
import FactorBoard from '@/components/qube/FactorBoard.vue'
import StrategyWorkbench from '@/components/qube/StrategyWorkbench.vue'
import SystemPromptDialog from '@/components/qube/SystemPromptDialog.vue'
import EngineConfigDrawer from '@/components/qube/EngineConfigDrawer.vue'
import { ResizeHandle } from '@/components/ui'
import type { ChatMsg, ContextStats, ToolCall, ToolCalls } from '@/components/qube/types'
import { jsonFetch } from '@/components/qube/types'
import {
  CANVAS_EXPAND,
  SIDEBAR_MAX,
  SIDEBAR_MIN,
  clampCanvasWidth,
  useQubeWorkspace,
} from '@/composables/useQubeWorkspace'

interface Session {
  id: string
  title: string
  updated_at: number
  bound_type?: string
  bound_id?: string
  pinned?: boolean
  message_count?: number
}

const route = useRoute()
const { state: wsState, session: sessionWs } = useQubeWorkspace()

const sessions = ref<Session[]>([])
const activeId = ref('')
const messages = ref<ChatMsg[]>([])
const input = ref('')
const streaming = ref(false)
const chatError = ref<string | null>(null)
const chatOffline = ref(false)
const lastText = ref('')
const abortRef = ref<AbortController | null>(null)
const listEl = ref<HTMLDivElement | null>(null)
const rootEl = ref<HTMLDivElement | null>(null)
const inputEl = ref<HTMLTextAreaElement | null>(null)
const renamingId = ref('')
const renameDraft = ref('')
const search = ref('')
const editing = ref<{ id: number; content: string } | null>(null)
const deletingMsg = ref<ChatMsg | null>(null)
const copyOk = ref(false)

const promptOpen = ref(false)
const configOpen = ref(false)
const clearConfirm = ref(false)

// —— 上下文 / token 用量 ————————————————
const stats = ref<ContextStats | null>(null)
const statsKey = ref('')
const compressBusy = ref(false)
const compressedAuto = ref(false)
const showBreakdown = ref(false)

function fmtTokens(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(n >= 100000 ? 0 : 1)}k` : `${n}`
}

async function loadStats() {
  if (!activeId.value) {
    stats.value = null
    return
  }
  const id = activeId.value
  try {
    const d = await jsonFetch(`/api/qube/sessions/${id}/stats`)
    if (id === activeId.value) {
      stats.value = d
      statsKey.value = id
    }
  } catch {
    /* 统计失败不阻断聊天 */
  }
}

const contextPct = computed(() =>
  stats.value && stats.value.context_window ? (stats.value.context_used / stats.value.context_window) * 100 : 0,
)
const contextColor = computed(() => {
  if (contextPct.value >= 85) return '#ff3b30'
  if (contextPct.value >= 60) return '#ff9f0a'
  return '#10a37f'
})

/** Claude Code 式自动压缩：上下文接近窗口上限时，先把早前对话压成摘要再发送 */
async function maybeAutoCompact() {
  if (compressedAuto.value || !activeId.value || !stats.value) return
  if (contextPct.value < 85 || messages.value.length < 16) return
  compressedAuto.value = true
  await compressSession(true)
}

async function compressSession(silent = false) {
  if (!activeId.value || compressBusy.value) return
  compressBusy.value = true
  try {
    await jsonFetch(`/api/qube/sessions/${activeId.value}/compress`, { method: 'POST' })
    await Promise.all([loadStats(), reloadMessages()])
    loadSessions()
    showBreakdown.value = false
  } catch (e) {
    if (!silent) chatError.value = e instanceof Error ? e.message : String(e)
  } finally {
    compressBusy.value = false
  }
}

// 当前会话工作区状态（画板宽度/绑定/参数持久化）
const ws = computed(() => sessionWs(activeId.value || '__none__'))

const factorBoardRef = ref<InstanceType<typeof FactorBoard> | null>(null)
const strategyRef = ref<InstanceType<typeof StrategyWorkbench> | null>(null)

function scrollToBottom() {
  nextTick(() => {
    if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight
  })
}

// —— 会话 ————————————————————————————————————————————————
async function loadSessions() {
  const d = await jsonFetch('/api/qube/sessions')
  sessions.value = d.sessions
}

async function openSession(id: string) {
  activeId.value = id
  chatError.value = null
  editing.value = null
  const d = await jsonFetch(`/api/qube/sessions/${id}/messages`)
  messages.value = d.messages
// 画板焦点恢复：优先 workspace 持久化，其次后端 resume
  const cur = sessionWs(id)
  if (!cur.active && d.workspace_resume) {
    cur.active = { kind: d.workspace_resume.kind, id: d.workspace_resume.id }
  }
  compressedAuto.value = false
  showBreakdown.value = false
  loadStats()
  scrollToBottom()
}

async function reloadMessages() {
  if (!activeId.value) return
  const d = await jsonFetch(`/api/qube/sessions/${activeId.value}/messages`)
  messages.value = d.messages
  loadStats()
}

async function newSession() {
  chatError.value = null
  chatOffline.value = false
  const s = await jsonFetch('/api/qube/sessions', { method: 'POST' })
  sessions.value.unshift(s)
  activeId.value = s.id
  messages.value = []
  nextTick(() => inputEl.value?.focus())
}

async function removeSession(id: string) {
  await jsonFetch(`/api/qube/sessions/${id}`, { method: 'DELETE' })
  sessions.value = sessions.value.filter((s) => s.id !== id)
  delete wsState.perSession[id]
  if (activeId.value === id) {
    activeId.value = ''
    messages.value = []
  }
}

async function clearAll() {
  await jsonFetch('/api/qube/sessions', { method: 'DELETE' })
  sessions.value = []
  wsState.perSession = {}
  activeId.value = ''
  messages.value = []
  clearConfirm.value = false
}

function startRename(s: Session) {
  renamingId.value = s.id
  renameDraft.value = s.title
}

async function commitRename() {
  const id = renamingId.value
  const title = renameDraft.value.trim()
  renamingId.value = ''
  if (!id || !title) return
  const s = sessions.value.find((x) => x.id === id)
  if (s && title !== s.title) {
    s.title = title
    await jsonFetch(`/api/qube/sessions/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    })
  }
}

// —— 会话置顶 / 导出 ——————————————————————————————————
async function togglePin(s: Session) {
  s.pinned = !s.pinned
  // 不要改动会话时间：取消置顶后用原 updated_at 归回原处
  sessions.value.sort((a, b) => Number(b.pinned || 0) - Number(a.pinned || 0) || b.updated_at - a.updated_at)
  await jsonFetch(`/api/qube/sessions/${s.id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pinned: s.pinned }),
  })
}

async function exportSession(id: string) {
  try {
    const res = await fetch(`/api/qube/sessions/${id}/export`)
    if (!res.ok) throw new Error('导出失败')
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `qube-${id.slice(0, 8)}.md`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  } catch (e) {
    chatError.value = e instanceof Error ? e.message : String(e)
  }
}

// —— 对话（SSE 流式，支持中止 / 断网判定 / 重试 / 编辑 / 重新生成） ———————
function emptyTools() {
  return { calls: [], display_timeline: [], thinking: '' } as ToolCalls
}

function newAssistantMsg(): ChatMsg {
  return { role: 'assistant', content: '', tool_calls: emptyTools() }
}

/**
 * 通用流式应答：对已就位的 assistant 消息 am 执行一轮 SSE 消费。
 * onError 由调用方决定失败时如何回退（普通发送回退用户+助手；编辑/重生成仅回退助手占位）。
 */
async function streamReply(
  am: ChatMsg,
  url: string,
  payload: Record<string, unknown>,
  opts: { popOnError?: boolean } = {},
) {
  const tc = am.tool_calls!
  streaming.value = true
  const controller = new AbortController()
  abortRef.value = controller
  scrollToBottom()

  let curText = ''
  const flushText = () => {
    if (curText.trim()) tc.display_timeline.push({ type: 'text', content: curText })
    curText = ''
  }
  const rollbackHelper = () => {
    if (opts.popOnError && messages.value[messages.value.length - 1] === am) {
      messages.value.pop()
    }
  }

  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: controller.signal,
    })
    if (!res.ok || !res.body) {
      const e = await res.json().catch(() => null)
      throw new Error(e?.detail || `HTTP ${res.status}`)
    }
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n\n')
      buf = lines.pop() || ''
      for (const line of lines) {
        if (!line.startsWith('data:')) continue
        let evt: Record<string, unknown>
        try {
          evt = JSON.parse(line.slice(5))
        } catch {
          continue
        }
        const kind = (evt.type as string) || (evt.error ? 'error' : evt.done ? 'done' : 'delta')
        if (kind === 'error') throw new Error((evt.message as string) || (evt.error as string) || 'AI 服务错误')
        else if (kind === 'delta') {
          curText += (evt.text as string) ?? (evt.delta as string) ?? ''
          am.content = curText
          scrollToBottom()
        } else if (kind === 'thinking') {
          tc.thinking += (evt.text as string) || ''
        } else if (kind === 'tool_start') {
          flushText()
          am.content = ''
        } else if (kind === 'tool') {
          const call = evt.call as ToolCall
          tc.calls.push(call)
          tc.display_timeline.push({ type: 'tool', call_index: tc.calls.length - 1 })
          applyToolSideEffect(call)
          scrollToBottom()
        } else if (kind === 'done') {
          flushText()
          am.content = ''
        }
      }
    }
    // 结束后重新拉取，让每条消息带上稳定的 id / created_at（供编辑/删除/重生成）
    if (activeId.value) await reloadMessages()
    loadSessions()
  } catch (e) {
    // 用户主动中止：不算错误，保留已生成内容
    if (e instanceof DOMException && e.name === 'AbortError') {
      flushText()
      am.content = ''
    } else if (e instanceof TypeError) {
      // fetch 抛 TypeError = 网络层失败（断网 / 后端没起 / DNS）
      chatOffline.value = true
      chatError.value = '网络连接中断，未能完成本轮对话。请检查后端是否在运行，或点「重试」重新发送。'
      if (!am.content && !tc.calls.length && !tc.thinking) rollbackHelper()
      if (opts.popOnError) messages.value.pop() // 连用户那条也回退，便于重试整体重发
    } else {
      chatError.value = e instanceof Error ? e.message : String(e)
      if (!am.content && !tc.calls.length && !tc.thinking) rollbackHelper()
    }
  } finally {
    streaming.value = false
    abortRef.value = null
    scrollToBottom()
  }
}

/** 普通发送：追加用户消息 + 空助手占位，POST /chat */
async function sendText(text: string) {
  if (!text.trim() || streaming.value) return
  if (!activeId.value) await newSession()
  input.value = ''
  chatError.value = null
  chatOffline.value = false
  lastText.value = text
  // Claude Code 式：上下文将满时先压缩早前对话释放空间，再发本轮
  await maybeAutoCompact()
  messages.value.push({ role: 'user', content: text })
  const am = newAssistantMsg()
  messages.value.push(am)
  await streamReply(am, '/api/qube/chat', { session_id: activeId.value, message: text }, { popOnError: true })
}

/** 进入编辑模式：把该用户消息内容放进输入框（带取消/保存条） */
function startEdit(m: ChatMsg) {
  if (streaming.value) return
  if (typeof m.id !== 'number' || m.role !== 'user') return
  editing.value = { id: m.id, content: m.content }
  input.value = m.content
  nextTick(() => inputEl.value?.focus())
}

function cancelEdit() {
  editing.value = null
  input.value = ''
}

/** 保存编辑并重跑：更新内容 → 截断后续 → POST /chat/edit 流式重答 */
async function editSend() {
  if (!editing.value || streaming.value) return
  const { id, content } = editing.value
  const text = content.trim()
  if (!text || !activeId.value) return
  editing.value = null
  input.value = ''
  chatError.value = null
  chatOffline.value = false
  lastText.value = text
  const idx = messages.value.findIndex((m) => m.id === id)
  if (idx < 0) return
  const current = messages.value[idx]
  if (current.role === 'user') {
    ;(current as { content: string }).content = text
    messages.value.splice(idx + 1)
    messages.value.push(newAssistantMsg())
    const am = messages.value[messages.value.length - 1]
    await streamReply(am, '/api/qube/chat/edit', {
      session_id: activeId.value,
      message_id: id,
      content: text,
    })
  }
}

/** 重新生成：移除上一条助手回复，POST /chat/regenerate 重跑同一用户消息 */
async function regenerate(m: ChatMsg) {
  if (streaming.value) return
  const last = messages.value[messages.value.length - 1]
  if (last !== m || last.role !== 'assistant') return
  if (typeof m.id !== 'number') return
  messages.value.pop()
  const am = newAssistantMsg()
  messages.value.push(am)
  chatError.value = null
  chatOffline.value = false
  const userMsg = [...messages.value].reverse().find((x) => x.role === 'user')
  if (userMsg?.content) lastText.value = userMsg.content
  await streamReply(
    am,
    `/api/qube/messages/${m.id}/regenerate?session_id=${encodeURIComponent(activeId.value)}`,
    {},
  )
}

/** 删除消息（及之后）→ 重载 */
async function removeMessage(m: ChatMsg) {
  deletingMsg.value = null
  if (streaming.value || typeof m.id !== 'number' || !activeId.value) return
  try {
    await jsonFetch(`/api/qube/messages/${m.id}?session_id=${encodeURIComponent(activeId.value)}`, {
      method: 'DELETE',
    })
    await reloadMessages()
    loadSessions()
  } catch (e) {
    chatError.value = e instanceof Error ? e.message : String(e)
  }
}

async function copyText(text: string) {
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    copyOk.value = true
    setTimeout(() => (copyOk.value = false), 1200)
  } catch {
    /* 忽略剪贴板权限 */
  }
}

// 中止当前流式响应
function stopStreaming() {
  abortRef.value?.abort()
}

// 断网/出错后重发上一条
function retry() {
  if (lastText.value) sendText(lastText.value)
}

// 工具产出 → 画板联动（打开对应工件并展开画板）
function applyToolSideEffect(call: ToolCall) {
  if (call.factor_id && (call.name === 'generate_stock_factor_code' || call.name === 'run_factor_analysis')) {
    openFactor(call.factor_id, call.name === 'run_factor_analysis' ? 'analysis' : 'code')
    if (call.factor_analysis_id) ws.value.selectedAnalysisId = call.factor_analysis_id
  }
  if (call.strategy_id && (call.name === 'generate_stock_strategy_code' || call.name === 'run_backtest')) {
    openStrategy(call.strategy_id, call.name === 'run_backtest' ? 'backtest' : 'code')
    if (call.backtest_run_id) ws.value.selectedBacktestRunId = call.backtest_run_id
  }
}

function send() {
  if (editing.value) editSend()
  else sendText(input.value)
}

function onPick(prompt: string) {
  sendText(prompt)
}

// —— 画板联动（工具卡按钮 / 工具副作用） ————————————————————
function openFactor(id: string, tab: string) {
  ws.value.active = { kind: 'factor', id }
  ws.value.canvasTab = tab === 'analysis' ? 'analysis' : 'code'
  wsState.canvasCollapsed = false
  nextTick(() => factorBoardRef.value?.refresh())
}

function openStrategy(id: string, tab: string) {
  ws.value.active = { kind: 'strategy', id }
  ws.value.canvasTab = ['code', 'backtest', 'logs', 'versions'].includes(tab) ? tab : 'code'
  wsState.canvasCollapsed = false
  nextTick(() => strategyRef.value?.refresh())
}

function viewAnalysis(factorId: string, analysisId: string) {
  openFactor(factorId, 'analysis')
  ws.value.selectedAnalysisId = analysisId
  nextTick(() => factorBoardRef.value?.openAnalysis(analysisId))
}

function viewBacktest(strategyId: string, runId: string) {
  openStrategy(strategyId, 'backtest')
  ws.value.selectedBacktestRunId = runId
  nextTick(() => strategyRef.value?.openRun(runId))
}

function optimize(strategyId: string, runId: string) {
  openStrategy(strategyId, 'code')
  void runId
}

// —— 画板拖拽调宽（严格按参考站：clamp / 双击 900 / 折叠 width 0） ————
const dragging = ref(false)
const sidebarDragging = ref(false)

function clampSidebarWidth(w: number) {
  return Math.max(SIDEBAR_MIN, Math.min(SIDEBAR_MAX, w))
}

function onSidebarDragStart(e: MouseEvent) {
  e.preventDefault()
  sidebarDragging.value = true
  const startX = e.clientX
  const startWidth = wsState.sidebarWidthPx
  document.body.style.cursor = 'ew-resize'
  document.body.style.userSelect = 'none'
  const move = (ev: MouseEvent) => {
    wsState.sidebarWidthPx = clampSidebarWidth(startWidth + (ev.clientX - startX))
  }
  const up = () => {
    sidebarDragging.value = false
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
    window.removeEventListener('mousemove', move)
    window.removeEventListener('mouseup', up)
  }
  window.addEventListener('mousemove', move)
  window.addEventListener('mouseup', up)
}

function toggleSidebar() {
  wsState.sidebarCollapsed = !wsState.sidebarCollapsed
}

function onDragStart(e: MouseEvent) {
  e.preventDefault()
  dragging.value = true
  const startX = e.clientX
  const startWidth = wsState.canvasWidthPx
  document.body.style.cursor = 'ew-resize'
  document.body.style.userSelect = 'none'
  const move = (ev: MouseEvent) => {
    const containerWidth = rootEl.value?.clientWidth ?? window.innerWidth
    wsState.canvasWidthPx = clampCanvasWidth(startWidth + (startX - ev.clientX), containerWidth)
  }
  const up = () => {
    dragging.value = false
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
    window.removeEventListener('mousemove', move)
    window.removeEventListener('mouseup', up)
  }
  window.addEventListener('mousemove', move)
  window.addEventListener('mouseup', up)
}

function onDragDouble() {
  const containerWidth = rootEl.value?.clientWidth ?? window.innerWidth
  wsState.canvasWidthPx = clampCanvasWidth(CANVAS_EXPAND, containerWidth)
}

function toggleCanvas() {
  wsState.canvasCollapsed = !wsState.canvasCollapsed
}

// 面板宽度（驱动展开/收起动画：折叠 → 0px，CSS transition-[width] 平滑过渡）
const sidebarPanelWidth = computed(() => (wsState.sidebarCollapsed ? 0 : wsState.sidebarWidthPx))
const canvasPanelWidth = computed(() =>
  wsState.canvasCollapsed || !ws.value.active ? 0 : wsState.canvasWidthPx,
)

// —— 会话搜索 / 时间分组 / 相对时间（对齐参考站） ————————————————
const filteredSessions = computed(() => {
  const q = search.value.trim().toLowerCase()
  const list = sessions.value.filter((s) => !q || s.title.toLowerCase().includes(q))
  return [...list].sort(
    (a, b) => Number(b.pinned || 0) - Number(a.pinned || 0) || b.updated_at - a.updated_at,
  )
})

function dayBucket(ts: number): string {
  const now = Date.now() / 1000
  const diff = now - ts
  if (diff < 3600) return '今天'
  if (diff < 86400 * 2) return '昨天'
  if (diff < 86400 * 7) return '过去 7 天'
  if (diff < 86400 * 30) return '过去 30 天'
  return new Date(ts * 1000).toLocaleDateString('zh-CN', { month: 'long' })
}

function relativeTime(ts: number): string {
  const now = Date.now() / 1000
  const diff = now - ts
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)} 天前`
  return new Date(ts * 1000).toLocaleDateString('zh-CN')
}

interface SessionGroup {
  label: string
  items: Session[]
}
const sessionGroups = computed<SessionGroup[]>(() => {
  const pins = filteredSessions.value.filter((s) => s.pinned)
  const rest = filteredSessions.value.filter((s) => !s.pinned)
  const groups: SessionGroup[] = []
  if (pins.length) groups.push({ label: '置顶', items: pins })
  const buckets = new Map<string, Session[]>()
  for (const s of rest) {
    const b = dayBucket(s.updated_at)
    if (!buckets.has(b)) buckets.set(b, [])
    buckets.get(b)!.push(s)
  }
  const bucketsLs = ['今天', '昨天', '过去 7 天', '过去 30 天']
  for (const name of bucketsLs) if (buckets.has(name)) groups.push({ label: name, items: buckets.get(name)! })
  const remaining = Array.from(buckets.entries()).filter(([k]) => !bucketsLs.includes(k))
  for (const [, items] of remaining) groups.push({ label: '更早', items })
  return groups
})

function groupingLabel(s: Session): string {
  return s.pinned ? '置顶' : dayBucket(s.updated_at)
}

onMounted(async () => {
  await Promise.all([loadSessions()])
  const sid = String(route.query.session || '')
  const prompt = String(route.query.prompt || '')
  if (sid) {
    await openSession(sid)
  } else if (sessions.value.length) {
    await openSession(sessions.value[0].id)
  }
  // 从技能库「在 QUBE 中使用」带过来的 prompt 模板，预填进输入框并聚焦
  if (prompt) {
    input.value = prompt
    nextTick(() => inputEl.value?.focus())
  }
})

// 页面卸载时清理可能残留的拖拽样式
onBeforeUnmount(() => {
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
})

watch(activeId, () => {
  chatError.value = null
})
</script>

<template>
  <div ref="rootEl" class="flex h-full">
    <!-- QUBE 次级侧边栏（可收起 + 可拖宽，VSCode 风格拖杆；收起=宽度动画到 0） -->
    <div
      class="relative flex shrink-0 flex-col overflow-hidden border-r border-[rgba(15,0,0,0.08)] bg-[#f8f7f7]"
      :class="[
        wsState.sidebarCollapsed ? 'border-transparent' : '',
        sidebarDragging ? '' : 'transition-[width] duration-200 ease-out',
      ]"
      :style="{ width: `${sidebarPanelWidth}px` }"
    >
      <div class="flex items-center gap-1.5 px-3 py-3">
        <Sparkles :size="14" class="text-[#201d1d]" />
        <span class="text-[13px] font-semibold text-[#201d1d]">QUBE</span>
        <span class="text-[10px] text-[#9a9898]">对话投研工作台</span>
        <button
          class="ml-auto flex items-center gap-1 text-[10px] text-[#9a9898] hover:text-[#201d1d]"
          title="收起侧边栏"
          @click="toggleSidebar"
        >
          <PanelLeftClose :size="13" />
        </button>
      </div>

      <div class="px-2">
        <button
          class="flex w-full items-center justify-center gap-1.5 rounded-[4px] bg-[#201d1d] px-2 py-1.5 text-[12px] text-[#fdfcfc] hover:opacity-85"
          @click="newSession"
        >
          <MessageSquarePlus :size="13" /> 新建对话
        </button>
      </div>

      <!-- 会话搜索 -->
      <div class="px-2 pt-2">
        <div class="flex items-center gap-1.5 rounded-[4px] border border-[rgba(15,0,0,0.10)] bg-[#fdfcfc] px-2 py-1">
          <Search :size="12" class="shrink-0 text-[#9a9898]" />
          <input
            v-model="search"
            placeholder="搜索对话…"
            class="w-full min-w-0 bg-transparent text-xs text-[#201d1d] outline-none placeholder:text-[#9a9898]"
          />
        </div>
      </div>

      <!-- 会话列表（置顶 + 时间分组） -->
      <div class="mt-2 min-h-0 flex-1 overflow-y-auto px-2">
        <template v-for="grp in sessionGroups" :key="grp.label">
          <div class="mb-1 mt-2 flex items-center gap-1 px-1 text-[10px] font-medium uppercase text-[#9a9898]">
            <Pin v-if="grp.label === '置顶'" :size="10" />
            <span class="truncate">{{ grp.label }}</span>
            <span class="ml-auto font-mono text-[9px]">{{ grp.items.length }}</span>
          </div>
          <div
            v-for="s in grp.items"
            :key="s.id"
            class="group relative mb-0.5 flex cursor-pointer items-center gap-1 px-2 py-1.5 text-xs"
            :class="s.id === activeId ? 'font-medium text-[#201d1d]' : 'rounded-[4px] text-[#646262] hover:bg-[#f1eeee] hover:text-[#201d1d]'"
            @click="openSession(s.id)"
          >
            <!-- 选中态左侧竖黑线（OpenCode 风格） -->
            <span
              v-if="s.id === activeId"
              class="absolute left-0 top-1/2 h-[14px] w-[2px] -translate-y-1/2 bg-[#201d1d]"
            />
            <input
              v-if="renamingId === s.id"
              v-model="renameDraft"
              class="min-w-0 flex-1 rounded-[3px] border border-[rgba(15,0,0,0.2)] bg-[#fdfcfc] px-1 py-0.5 text-xs outline-none"
              @click.stop
              @keydown.enter="commitRename"
              @blur="commitRename"
            />
            <template v-else>
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-1">
                  <span class="min-w-0 flex-1 truncate">{{ s.title }}</span>
                  <span class="shrink-0 text-[9px] text-[#b0aeae]">{{ s.message_count }}</span>
                </div>
                <div class="mt-0.5 truncate text-[9px] text-[#b0aeae]">
                  {{ groupingLabel(s) }} · {{ relativeTime(s.updated_at) }}
                </div>
              </div>
              <button
                v-if="renamingId !== s.id"
                :class="s.pinned ? 'text-[#9a6200]' : 'text-[#9a9898] hover:text-[#9a6200]'"
                class="hidden shrink-0 group-hover:block"
                :title="s.pinned ? '取消置顶' : '置顶'"
                @click.stop="togglePin(s)"
              >
                <Pin :size="12" />
              </button>
              <button
                v-if="renamingId !== s.id"
                class="hidden shrink-0 text-[#9a9898] hover:text-[#201d1d] group-hover:block"
                title="重命名"
                @click.stop="startRename(s)"
              >
                ✎
              </button>
              <button
                v-if="renamingId !== s.id"
                class="hidden shrink-0 text-[#9a9898] hover:text-[#ff3b30] group-hover:block"
                title="删除"
                @click.stop="removeSession(s.id)"
              >
                <Trash2 :size="12" />
              </button>
            </template>
          </div>
        </template>
        <div v-if="!filteredSessions.length" class="px-2 py-6 text-center text-[11px] text-[#9a9898]">
          {{ search ? '无匹配的对话' : '暂无对话 — 点「新建对话」开始' }}
        </div>
      </div>

      <!-- 底部：功能入口 -->
      <div class="shrink-0 space-y-0.5 border-t border-[rgba(15,0,0,0.08)] p-2">
        <button
          class="flex w-full items-center gap-2 rounded-[4px] px-2 py-1.5 text-xs text-[#646262] hover:bg-[#f1eeee] hover:text-[#201d1d]"
          @click="promptOpen = true"
        >
          <BrainCircuit :size="13" /> 系统提示词
        </button>
        <RouterLink
          to="/skills"
          class="flex w-full items-center gap-2 rounded-[4px] px-2 py-1.5 text-xs text-[#646262] hover:bg-[#f1eeee] hover:text-[#201d1d]"
        >
          <BookMarked :size="13" /> 技能库
        </RouterLink>
        <button
          class="flex w-full items-center gap-2 rounded-[4px] px-2 py-1.5 text-xs text-[#646262] hover:bg-[#f1eeee] hover:text-[#201d1d]"
          @click="configOpen = true"
        >
          <Settings2 :size="13" /> 引擎设置
        </button>
        <button
          v-if="sessions.length"
          class="flex w-full items-center gap-2 rounded-[4px] px-2 py-1.5 text-xs text-[#9a9898] hover:bg-[#ff3b30]/8 hover:text-[#ff3b30]"
          @click="clearConfirm = true"
        >
          <Trash2 :size="13" /> 清空全部对话
        </button>
      </div>

      <!-- 拖宽手柄（VSCode 风格：贴右缘） -->
      <ResizeHandle
        side="right"
        :dragging="sidebarDragging"
        @drag-start="onSidebarDragStart"
        @dblclick="wsState.sidebarWidthPx = 240"
      />
    </div>

    <!-- 次侧栏收起态：窄条展开按钮 -->
    <button
      v-if="wsState.sidebarCollapsed"
      class="flex w-[26px] shrink-0 items-start justify-center border-r border-[rgba(15,0,0,0.08)] bg-[#f8f7f7] pt-4 text-[#646262] hover:bg-[#f1eeee] hover:text-[#201d1d]"
      title="展开侧边栏"
      @click="toggleSidebar"
    >
      <PanelLeftOpen :size="15" />
    </button>

    <!-- 对话区 -->
    <div class="flex min-w-0 flex-1 flex-col bg-[#fdfcfc]" style="min-width: 420px">
      <div class="flex shrink-0 items-center justify-between gap-2 border-b border-[rgba(15,0,0,0.08)] px-4 py-2">
        <div class="flex min-w-0 items-center gap-2">
          <button
            v-if="wsState.sidebarCollapsed"
            class="flex shrink-0 items-center gap-1 rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2 py-1 text-[11px] text-[#424245] hover:text-[#201d1d]"
            title="展开侧边栏"
            @click="toggleSidebar"
          >
            <PanelLeftOpen :size="12" /> 会话
          </button>
          <span class="truncate text-xs font-medium text-[#201d1d]">
            {{ activeId ? sessions.find((s) => s.id === activeId)?.title || '当前对话' : 'QUBE 对话投研' }}
          </span>
        </div>
        <div class="flex shrink-0 items-center gap-1.5">
          <button
            v-if="activeId"
            class="flex shrink-0 items-center gap-1 rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2 py-1 text-[11px] text-[#424245] hover:text-[#201d1d]"
            title="导出对话为 Markdown"
            @click="exportSession(activeId)"
          >
            <Download :size="12" /> 导出
          </button>
          <button
            v-if="ws.active"
            class="flex shrink-0 items-center gap-1 rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2 py-1 text-[11px] text-[#424245] hover:text-[#201d1d]"
            @click="toggleCanvas"
          >
            <component :is="wsState.canvasCollapsed ? PanelRightOpen : PanelRightClose" :size="12" />
            画板
          </button>
        </div>
      </div>

      <div ref="listEl" class="min-h-0 flex-1 overflow-y-auto">
        <EmptyState v-if="!messages.length" @pick="onPick" />
        <div v-else class="space-y-4 px-4 py-4">
          <ChatMessage
            v-for="(m, i) in messages"
            :key="m.id ?? i"
            :msg="m"
            :streaming="streaming && i === messages.length - 1"
            :is-last="i === messages.length - 1"
            @open-factor="openFactor"
            @open-strategy="openStrategy"
            @view-analysis="viewAnalysis"
            @view-backtest="viewBacktest"
            @optimize="optimize"
            @copy="copyText"
            @edit="startEdit"
            @regenerate="regenerate"
            @remove="deletingMsg = $event"
          >
            <template v-if="streaming && i === messages.length - 1 && !m.content && !m.tool_calls?.calls.length" #tail>
              <div class="flex items-center gap-1.5 px-1 text-xs text-[#9a9898]">
                <span class="inline-block h-2 w-2 animate-pulse rounded-full bg-[#007aff]" />
                QUBE 思考中…
              </div>
            </template>
          </ChatMessage>

          <div
            v-if="chatError"
            class="flex items-start gap-2 rounded-[4px] border px-3 py-2 text-xs"
            :class="chatOffline ? 'border-[#ff9f0a]/40 bg-[#ff9f0a]/8 text-[#9a6200]' : 'border-[#ff3b30]/40 bg-[#ff3b30]/8 text-[#ff3b30]'"
          >
            <WifiOff v-if="chatOffline" :size="14" class="mt-0.5 shrink-0" />
            <span class="min-w-0 flex-1">{{ chatError }}</span>
            <button
              class="flex shrink-0 items-center gap-1 rounded-[3px] border border-current/30 px-2 py-0.5 text-[11px] hover:opacity-80"
              @click="retry"
            >
              <RefreshCw :size="11" /> 重试
            </button>
          </div>
        </div>
      </div>

      <!-- 输入区 -->
      <div class="shrink-0 border-t border-[rgba(15,0,0,0.08)] p-3">
        <!-- 上下文用量 + 压缩 -->
        <div v-if="stats" class="mb-1.5">
          <div class="flex items-center gap-2 text-[10px]">
            <span class="shrink-0 text-[#9a9898]">上下文</span>
            <div class="h-1 min-w-0 flex-1 overflow-hidden rounded-full bg-[#ece9e9]">
              <div
                class="h-full rounded-full transition-all"
                :style="{ width: Math.min(100, contextPct) + '%', background: contextColor }"
              />
            </div>
            <span class="shrink-0 font-mono text-[#646262]">
              <span :style="{ color: contextColor }">{{ contextPct.toFixed(0) }}%</span>
              · <span>{{ fmtTokens(stats.context_used) }}/{{ fmtTokens(stats.context_window) }}</span>
            </span>
            <button
              class="shrink-0 rounded px-1.5 py-0.5 text-[#9a9898] hover:bg-[#f1eeee] hover:text-[#201d1d]"
              title="查看 token 用量构成"
              @click="showBreakdown = !showBreakdown"
            >
              构成
            </button>
            <button
              class="flex shrink-0 items-center gap-1 rounded border border-[rgba(15,0,0,0.12)] px-1.5 py-0.5 text-[#646262] hover:text-[#201d1d] disabled:cursor-not-allowed disabled:opacity-40"
              :disabled="compressBusy || messages.length < 16"
              :title="stats.compacted ? '已压缩过；再次压缩把更多早前对话并入摘要' : '把较早的对话压缩成摘要，释放上下文；不影响后续新消息'"
              @click="compressSession()"
            >
              <Minimize2 :size="11" />
              {{ compressBusy ? '压缩中…' : stats.compacted ? '重新压缩' : '压缩上下文' }}
            </button>
          </div>
          <div v-if="showBreakdown && stats" class="mt-1.5 space-y-0.5 rounded-[4px] border border-[rgba(15,0,0,0.1)] bg-[#f8f7f7] px-2.5 py-1.5 font-mono text-[10px] text-[#646262]">
            <div v-if="stats.compacted" class="text-[#9a6200]">（已压缩早期对话 — 摘要并入系统提示词，节省上下文）</div>
            <div class="flex justify-between"><span>系统提示</span><span>{{ fmtTokens(stats.breakdown.system) }}</span></div>
            <div v-if="stats.breakdown.summary" class="flex justify-between"><span>会话摘要</span><span>{{ fmtTokens(stats.breakdown.summary) }}</span></div>
            <div class="flex justify-between"><span>最近对话</span><span>{{ fmtTokens(stats.breakdown.conversation) }}</span></div>
            <div class="flex justify-between"><span>累计输出</span><span>{{ fmtTokens(stats.breakdown.completion) }}</span></div>
            <div class="flex justify-between"><span>深度思考</span><span>{{ fmtTokens(stats.breakdown.reasoning) }}</span></div>
            <div class="mt-0.5 flex justify-between border-t border-[rgba(15,0,0,0.1)] pt-0.5 text-[#201d1d]">
              <span>合计</span><span>{{ fmtTokens(stats.total_tokens) }}</span>
            </div>
          </div>
        </div>

        <!-- 编辑消息条 -->
        <div
          v-if="editing"
          class="mb-1.5 flex items-center gap-2 rounded-[4px] border border-[#007aff]/30 bg-[#007aff]/6 px-2.5 py-1.5 text-[11px] text-[#0056b3]"
        >
          <Pencil :size="12" class="shrink-0" />
          <span class="min-w-0 flex-1 truncate">正在编辑已发送的消息（发送后从此处继续对话）</span>
          <button
            class="shrink-0 rounded-[3px] border border-[#007aff]/30 px-2 py-0.5 text-[10px] text-[#0056b3] hover:bg-[#007aff]/10"
            @click="cancelEdit"
          >
            取消
          </button>
        </div>
        <div class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] p-2 focus-within:border-[#201d1d]">
          <textarea
            ref="inputEl"
            v-model="input"
            rows="2"
            placeholder="请在这里输入提问… (Enter 发送, Shift+Enter 换行)"
            class="w-full resize-none bg-transparent px-1 text-xs leading-relaxed text-[#201d1d] outline-none"
            @keydown.enter.exact.prevent="send"
          />
          <div class="mt-1 flex items-end justify-between gap-2">
            <ModelBar />
            <!-- 流式中显示「停止」按钮，否则显示「发送」 -->
            <button
              v-if="streaming"
              class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-[rgba(15,0,0,0.2)] bg-[#fdfcfc] text-[#201d1d] hover:bg-[#f1eeee]"
              title="停止生成"
              @click="stopStreaming"
            >
              <Square :size="12" />
            </button>
            <button
              v-else
              :disabled="!input.trim()"
              class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[#201d1d] text-[#fdfcfc] hover:opacity-85 disabled:opacity-40"
              @click="send"
            >
              <Send :size="13" />
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 右侧画板（可拖拽调宽；折叠/无工件 = 宽度动画到 0 收起） -->
    <div
      class="relative shrink-0 overflow-hidden border-l border-[rgba(15,0,0,0.08)] bg-[#fdfcfc]"
      :class="[
        wsState.canvasCollapsed || !ws.active ? 'border-transparent' : '',
        dragging ? '' : 'transition-[width] duration-300 ease-out',
      ]"
      :style="{ width: `${canvasPanelWidth}px` }"
    >
      <!-- 拖拽手柄（VSCode 风格：贴左缘） -->
      <ResizeHandle
        side="left"
        :dragging="dragging"
        @drag-start="onDragStart"
        @dblclick="onDragDouble"
      />

      <FactorBoard
        v-if="ws.active?.kind === 'factor'"
        ref="factorBoardRef"
        :factor-id="ws.active.id"
        :session-id="activeId"
        :ws="ws"
      />
      <StrategyWorkbench
        v-else-if="ws.active?.kind === 'strategy'"
        ref="strategyRef"
        :strategy-id="ws.active.id"
        :session-id="activeId"
        :ws="ws"
      />
    </div>

    <!-- 弹窗 / 抽屉 -->
    <SystemPromptDialog v-if="promptOpen" :open="promptOpen" @close="promptOpen = false" />
    <EngineConfigDrawer :open="configOpen" @close="configOpen = false" />

    <!-- 删除消息确认 -->
    <div
      v-if="deletingMsg"
      class="fixed inset-0 z-[90] flex items-center justify-center bg-black/40"
      @click.self="deletingMsg = null"
    >
      <div class="w-[340px] rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] p-4">
        <div class="text-sm font-medium text-[#201d1d]">删除这条消息？</div>
        <div class="mt-2 text-xs text-[#646262]">
          将删除这条消息及其之后的所有消息（会截断当前对话，不可恢复）。
        </div>
        <div class="mt-4 flex justify-end gap-2">
          <button
            class="rounded-[4px] border border-[rgba(15,0,0,0.15)] px-3 py-1 text-xs text-[#646262]"
            @click="deletingMsg = null"
          >
            取消
          </button>
          <button class="rounded-[4px] bg-[#ff3b30] px-3 py-1 text-xs text-white hover:opacity-85" @click="removeMessage(deletingMsg)">
            删除
          </button>
        </div>
      </div>
    </div>

    <div v-if="clearConfirm" class="fixed inset-0 z-[90] flex items-center justify-center bg-black/40" @click.self="clearConfirm = false">
      <div class="w-[320px] rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] p-4">
        <div class="text-sm font-medium text-[#201d1d]">清空全部对话</div>
        <div class="mt-2 text-xs text-[#646262]">将删除所有会话与消息，且不可恢复。确定继续？</div>
        <div class="mt-4 flex justify-end gap-2">
          <button class="rounded-[4px] border border-[rgba(15,0,0,0.15)] px-3 py-1 text-xs text-[#646262]" @click="clearConfirm = false">
            取消
          </button>
          <button class="rounded-[4px] bg-[#ff3b30] px-3 py-1 text-xs text-white hover:opacity-85" @click="clearAll">
            清空
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
