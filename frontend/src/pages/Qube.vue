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
  MessageSquarePlus,
  PanelLeftOpen,
  PanelLeftClose,
  PanelRightClose,
  PanelRightOpen,
  RefreshCw,
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
import type { ChatMsg, ToolCall } from '@/components/qube/types'
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

const promptOpen = ref(false)
const configOpen = ref(false)
const clearConfirm = ref(false)

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
  const d = await jsonFetch(`/api/qube/sessions/${id}/messages`)
  messages.value = d.messages
  // 画板焦点恢复：优先 workspace 持久化，其次后端 resume
  const cur = sessionWs(id)
  if (!cur.active && d.workspace_resume) {
    cur.active = { kind: d.workspace_resume.kind, id: d.workspace_resume.id }
  }
  scrollToBottom()
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

// —— 对话（SSE 流式，支持中止 / 断网判定 / 重试） ———————————————————————
async function sendText(text: string) {
  if (!text.trim() || streaming.value) return
  if (!activeId.value) await newSession()
  input.value = ''
  chatError.value = null
  chatOffline.value = false
  lastText.value = text
  messages.value.push({ role: 'user', content: text })
  messages.value.push({
    role: 'assistant',
    content: '',
    tool_calls: { calls: [], display_timeline: [], thinking: '' },
  })
  // 关键：取数组内的 reactive 代理引用（写原始对象不会触发视图更新）
  const am = messages.value[messages.value.length - 1]
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

  try {
    const res = await fetch('/api/qube/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: activeId.value, message: text }),
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
      if (!am.content && !tc.calls.length && !tc.thinking) messages.value.pop()
      // 把用户那条也回退，便于重试时重新整体发送
      messages.value.pop()
      messages.value.pop()
    } else {
      chatError.value = e instanceof Error ? e.message : String(e)
      if (!am.content && !tc.calls.length && !tc.thinking) messages.value.pop()
    }
  } finally {
    streaming.value = false
    abortRef.value = null
    scrollToBottom()
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
  sendText(input.value)
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

const canvasVisible = computed(() => !wsState.canvasCollapsed && !!ws.value.active)

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
    <!-- QUBE 次级侧边栏（可收起 + 可拖宽，VSCode 风格拖杆） -->
    <div
      v-show="!wsState.sidebarCollapsed"
      class="relative flex shrink-0 flex-col border-r border-[rgba(15,0,0,0.08)] bg-[#f8f7f7]"
      :class="sidebarDragging ? '' : 'transition-[width] duration-200 ease-out'"
      :style="{ width: `${wsState.sidebarWidthPx}px` }"
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

      <!-- 会话列表 -->
      <div class="mt-2 min-h-0 flex-1 overflow-y-auto px-2">
        <div class="mb-1 px-1 text-[10px] font-medium uppercase text-[#9a9898]">对话</div>
        <div
          v-for="s in sessions"
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
          <span v-else class="min-w-0 flex-1 truncate">{{ s.title }}</span>
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
        </div>
        <div v-if="!sessions.length" class="px-2 py-6 text-center text-[11px] text-[#9a9898]">
          暂无对话 — 点「新建对话」开始
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
        <button
          v-if="ws.active"
          class="flex shrink-0 items-center gap-1 rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2 py-1 text-[11px] text-[#424245] hover:text-[#201d1d]"
          @click="toggleCanvas"
        >
          <component :is="wsState.canvasCollapsed ? PanelRightOpen : PanelRightClose" :size="12" />
          画板
        </button>
      </div>

      <div ref="listEl" class="min-h-0 flex-1 overflow-y-auto">
        <EmptyState v-if="!messages.length" @pick="onPick" />
        <div v-else class="space-y-4 px-4 py-4">
          <ChatMessage
            v-for="(m, i) in messages"
            :key="i"
            :msg="m"
            :streaming="streaming && i === messages.length - 1"
            @open-factor="openFactor"
            @open-strategy="openStrategy"
            @view-analysis="viewAnalysis"
            @view-backtest="viewBacktest"
            @optimize="optimize"
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

    <!-- 右侧画板（可拖拽调宽；折叠 = width 0 隐藏） -->
    <div
      v-show="canvasVisible"
      class="relative shrink-0 border-l border-[rgba(15,0,0,0.08)] bg-[#fdfcfc]"
      :class="dragging ? '' : 'transition-[width] duration-300 ease-out'"
      :style="{ width: `${wsState.canvasWidthPx}px` }"
    >
      <!-- 拖拽手柄（VSCode 风格：贴左缘） -->
      <ResizeHandle
        side="left"
        :dragging="dragging"
        @drag-start="onDragStart"
        @dblclick="onDragDouble"
      />
      <button
        class="absolute -left-3.5 top-1/2 z-20 flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-full border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] text-[#646262] hover:text-[#201d1d]"
        title="收起画板"
        @click="toggleCanvas"
      >
        <PanelRightClose :size="13" />
      </button>

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
