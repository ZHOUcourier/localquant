<script setup lang="ts">
/**
 * QUBE — 策略研究 AI Agent
 *
 * - 左侧会话列表（持久化于后端 qube_sessions）
 * - 中间对话区：pi 风格 agent 事件流（delta / tool_call / tool_result / done），
 *   工具调用在流中实时呈现；```strategy 块渲染为策略卡片一键入库
 * - 右侧策略工作台分屏（StrategyWorkbench）：对话产出的策略在此
 *   回测 / AI 优化 / 版本管理；可折叠
 * - 右上「配置」：QUBE 专属 AI 配置（与设置页 AI 完全独立）——
 *   API 供应商（预置免 Base URL，模型下拉选择，仅 BYOK 自填）或本机 CLI 工具
 */
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  BookMarked,
  Loader2,
  MessageSquarePlus,
  PanelRightClose,
  PanelRightOpen,
  Send,
  Settings2,
  Sparkles,
  Trash2,
  X,
} from 'lucide-vue-next'
import { Select } from '@/components/ui'
import type { SelectOption } from '@/components/ui'
import StrategyWorkbench from '@/components/qube/StrategyWorkbench.vue'

interface Session {
  id: string
  title: string
  updated_at: number
}
interface Msg {
  role: 'user' | 'assistant'
  content: string
}
interface ProviderInfo {
  id: string
  label: string
  base_url: string
  model: string
  models: string[]
  byok: boolean
}
interface CliInfo {
  id: string
  label: string
  bin: string
  available: boolean
  models: string[]
  supports_model: boolean
  supports_effort: boolean
}

const route = useRoute()

const sessions = ref<Session[]>([])
const activeId = ref('')
const messages = ref<Msg[]>([])
const input = ref('')
const streaming = ref(false)
const chatError = ref<string | null>(null)
const listEl = ref<HTMLDivElement | null>(null)

async function jsonFetch(url: string, options?: RequestInit) {
  const res = await fetch(url, options)
  const body = await res.json().catch(() => null)
  if (!res.ok) throw new Error(body?.detail || `HTTP ${res.status}`)
  return body
}

function scrollToBottom() {
  nextTick(() => {
    if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight
  })
}

// —— 会话 ————————————————————————————————————————————————————————
async function loadSessions() {
  const d = await jsonFetch('/api/qube/sessions')
  sessions.value = d.sessions
}

async function openSession(id: string) {
  activeId.value = id
  chatError.value = null
  const d = await jsonFetch(`/api/qube/sessions/${id}/messages`)
  messages.value = d.messages
  scrollToBottom()
}

async function newSession() {
  const s = await jsonFetch('/api/qube/sessions', { method: 'POST' })
  sessions.value.unshift(s)
  activeId.value = s.id
  messages.value = []
}

async function removeSession(id: string) {
  await jsonFetch(`/api/qube/sessions/${id}`, { method: 'DELETE' })
  sessions.value = sessions.value.filter((s) => s.id !== id)
  if (activeId.value === id) {
    activeId.value = ''
    messages.value = []
  }
}

// —— 对话（SSE 流式） ————————————————————————————————————————————
async function send() {
  const text = input.value.trim()
  if (!text || streaming.value) return
  if (!activeId.value) await newSession()
  input.value = ''
  chatError.value = null
  messages.value.push({ role: 'user', content: text })
  messages.value.push({ role: 'assistant', content: '' })
  streaming.value = true
  scrollToBottom()
  const append = (s: string) => {
    messages.value[messages.value.length - 1].content += s
    scrollToBottom()
  }
  try {
    const res = await fetch('/api/qube/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: activeId.value, message: text }),
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
        let evt: {
          type?: string
          text?: string
          delta?: string
          name?: string
          result?: string
          error?: string
          message?: string
          done?: boolean
        }
        try {
          evt = JSON.parse(line.slice(5))
        } catch {
          continue
        }
        // 兼容 pi 风格事件（type 字段）与旧格式（裸 delta/error/done）
        const kind = evt.type || (evt.error ? 'error' : evt.done ? 'done' : 'delta')
        if (kind === 'error') throw new Error(evt.message || evt.error || 'AI 服务错误')
        if (kind === 'delta') append(evt.text ?? evt.delta ?? '')
        else if (kind === 'tool_call') append(`\n🔧 调用工具 ${evt.name}\n`)
        else if (kind === 'tool_result') {
          append(`✓ ${evt.name} 完成\n`)
          // agent 自己存了策略 → 刷新右侧工作台并展开
          if (evt.name === 'save_strategy') {
            workbenchOpen.value = true
            let preferId: string | undefined
            try {
              preferId = JSON.parse(evt.result || '{}').strategy_id
            } catch {
              preferId = undefined
            }
            workbenchRef.value?.refresh(preferId)
          }
        }
      }
    }
    // 刷新会话标题（首条消息生成标题）
    loadSessions()
  } catch (e) {
    chatError.value = e instanceof Error ? e.message : String(e)
    if (!messages.value[messages.value.length - 1]?.content) messages.value.pop()
  } finally {
    streaming.value = false
    scrollToBottom()
  }
}

// 右侧策略工作台分屏
const workbenchOpen = ref(true)
const workbenchRef = ref<InstanceType<typeof StrategyWorkbench> | null>(null)

// —— 策略块识别：```strategy ... ``` → 卡片 + 保存 ————————————————————
interface Segment {
  type: 'text' | 'strategy'
  content: string
}
function splitSegments(content: string): Segment[] {
  const segs: Segment[] = []
  const re = /```strategy\n([\s\S]*?)(?:```|$)/g
  let last = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(content))) {
    if (m.index > last) segs.push({ type: 'text', content: content.slice(last, m.index) })
    segs.push({ type: 'strategy', content: m[1].trim() })
    last = m.index + m[0].length
  }
  if (last < content.length) segs.push({ type: 'text', content: content.slice(last) })
  return segs
}

const savedKeys = ref(new Set<string>())
async function saveStrategy(content: string) {
  const nameMatch = content.match(/名称[:：]\s*(.+)/)
  const name = (nameMatch?.[1] || `QUBE 策略 ${new Date().toLocaleString()}`).trim()
  await jsonFetch('/api/strategy/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name,
      description: 'QUBE 对话产出',
      content,
      source: 'chat',
      session_id: activeId.value,
    }),
  })
  savedKeys.value = new Set([...savedKeys.value, content])
  // 刷新右侧工作台并展开，新策略直接可回测/优化
  workbenchOpen.value = true
  workbenchRef.value?.refresh()
}

// —— QUBE 配置（独立于设置页 AI） ————————————————————————————————
const configOpen = ref(false)
const providers = ref<ProviderInfo[]>([])
const cliTools = ref<CliInfo[]>([])
const cfg = ref({
  qube_engine: 'api',
  qube_provider: 'opencode-zen',
  qube_model: '',
  qube_effort: 'medium',
  qube_api_key: '',
  qube_base_url: '',
  qube_cli: 'claude',
  qube_cli_model: '',
  qube_cli_effort: 'default',
})
const cfgKeyMasked = ref('')
const cfgSaving = ref(false)
const cfgMsg = ref('')

const EFFORT_LEVELS = [
  { k: 'minimal', label: '极简' },
  { k: 'low', label: '低' },
  { k: 'medium', label: '中' },
  { k: 'high', label: '高' },
]

// CLI 强度：多一个“CLI 默认”（不传 flag，用工具自身默认）
const CLI_EFFORT_LEVELS = [
  { k: 'default', label: 'CLI 默认' },
  { k: 'minimal', label: '极简' },
  { k: 'low', label: '低' },
  { k: 'medium', label: '中' },
  { k: 'high', label: '高' },
]

const selectedProvider = computed(() => providers.value.find((p) => p.id === cfg.value.qube_provider))
const selectedCli = computed(() => cliTools.value.find((t) => t.id === cfg.value.qube_cli))

async function loadConfig() {
  const d = await jsonFetch('/api/qube/config')
  providers.value = d.providers
  cliTools.value = d.cli_tools
  cfg.value.qube_engine = d.qube_engine
  cfg.value.qube_provider = d.qube_provider
  cfg.value.qube_model = d.qube_model
  cfg.value.qube_effort = d.qube_effort || 'medium'
  cfg.value.qube_base_url = d.qube_base_url
  cfg.value.qube_cli = d.qube_cli
  cfg.value.qube_cli_model = d.qube_cli_model || ''
  cfg.value.qube_cli_effort = d.qube_cli_effort || 'default'
  cfgKeyMasked.value = d.qube_api_key_masked
}

function pickProvider(p: ProviderInfo) {
  cfg.value.qube_provider = p.id
  if (!p.byok) cfg.value.qube_base_url = ''
  cfg.value.qube_model = p.model
}

// 当前供应商的模型下拉选项（BYOK 无清单，降级为手输）
const modelOptions = computed<SelectOption[]>(() =>
  (selectedProvider.value?.models ?? []).map((m) => ({ value: m, label: m })),
)

async function saveConfig() {
  cfgSaving.value = true
  cfgMsg.value = ''
  try {
    const body: Record<string, string> = {
      qube_engine: cfg.value.qube_engine,
      qube_provider: cfg.value.qube_provider,
      qube_model: cfg.value.qube_model,
      qube_effort: cfg.value.qube_effort,
      qube_base_url: cfg.value.qube_base_url,
      qube_cli: cfg.value.qube_cli,
      qube_cli_model: cfg.value.qube_cli_model,
      qube_cli_effort: cfg.value.qube_cli_effort,
    }
    if (cfg.value.qube_api_key) body.qube_api_key = cfg.value.qube_api_key
    await jsonFetch('/api/qube/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    cfg.value.qube_api_key = ''
    cfgMsg.value = '已保存'
    loadConfig()
  } catch (e) {
    cfgMsg.value = e instanceof Error ? e.message : String(e)
  } finally {
    cfgSaving.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadSessions(), loadConfig()])
  const sid = String(route.query.session || '')
  if (sid) openSession(sid)
  else if (sessions.value.length) openSession(sessions.value[0].id)
})
</script>

<template>
  <div class="flex h-full">
    <!-- 会话列表 -->
    <div class="flex w-[220px] shrink-0 flex-col border-r border-[rgba(15,0,0,0.08)] bg-[#f8f7f7]">
      <div class="flex items-center justify-between px-3 py-3">
        <span class="flex items-center gap-1.5 text-[13px] font-semibold text-[#201d1d]">
          <Sparkles :size="14" class="text-[#7c3aed]" /> QUBE
        </span>
        <button
          class="flex items-center gap-1 rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2 py-1 text-[11px] text-[#424245] hover:text-[#201d1d]"
          @click="newSession"
        >
          <MessageSquarePlus :size="12" /> 新对话
        </button>
      </div>
      <div class="flex-1 overflow-y-auto px-2 pb-2">
        <div
          v-for="s in sessions"
          :key="s.id"
          class="group mb-0.5 flex cursor-pointer items-center justify-between rounded-[4px] px-2.5 py-2 text-xs"
          :class="s.id === activeId ? 'bg-[#e8e5e5] text-[#201d1d] font-medium' : 'text-[#646262] hover:bg-[#f1eeee] hover:text-[#201d1d]'"
          @click="openSession(s.id)"
        >
          <span class="truncate">{{ s.title }}</span>
          <button
            class="hidden shrink-0 border-0 bg-transparent text-[#9a9898] hover:text-[#ff3b30] group-hover:block"
            @click.stop="removeSession(s.id)"
          >
            <Trash2 :size="12" />
          </button>
        </div>
        <div v-if="!sessions.length" class="px-2 py-6 text-center text-[11px] text-[#9a9898]">
          暂无对话 — 点击「新对话」开始
        </div>
      </div>
    </div>

    <!-- 对话区 -->
    <div class="flex min-w-0 flex-1 flex-col bg-[#fdfcfc]">
      <div class="flex shrink-0 items-center justify-between border-b border-[rgba(15,0,0,0.08)] px-4 py-2.5">
        <span class="text-xs text-[#646262]">
          通过对话设计量化策略；产出的策略默认进入策略库「工作中」，只有你能手动设为「已保存」。
        </span>
        <div class="flex items-center gap-1.5">
          <button
            class="flex items-center gap-1 rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2.5 py-1 text-[11px] text-[#424245] hover:text-[#201d1d]"
            :title="workbenchOpen ? '收起策略工作台' : '展开策略工作台'"
            @click="workbenchOpen = !workbenchOpen"
          >
            <component :is="workbenchOpen ? PanelRightClose : PanelRightOpen" :size="12" />
            工作台
          </button>
          <button
            class="flex items-center gap-1 rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2.5 py-1 text-[11px] text-[#424245] hover:text-[#201d1d]"
            @click="configOpen = true"
          >
            <Settings2 :size="12" /> 配置
          </button>
        </div>
      </div>

      <div ref="listEl" class="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        <div v-if="!messages.length" class="flex h-full flex-col items-center justify-center gap-2 text-[#9a9898]">
          <Sparkles :size="28" class="text-[#7c3aed]/50" />
          <div class="text-sm font-medium text-[#646262]">QUBE 策略研究 Agent</div>
          <div class="text-xs">例：“帮我设计一个 20 日动量 + 低波动的双因子选股策略”</div>
        </div>

        <div v-for="(m, i) in messages" :key="i" class="mb-4">
          <!-- 用户消息 -->
          <div v-if="m.role === 'user'" class="flex justify-end">
            <div class="max-w-[78%] whitespace-pre-wrap rounded-[6px] bg-[#201d1d] px-3 py-2 text-xs leading-relaxed text-[#fdfcfc]">
              {{ m.content }}
            </div>
          </div>
          <!-- 助手消息：文本 + 策略卡片 -->
          <div v-else class="flex justify-start">
            <div class="max-w-[88%] space-y-2">
              <template v-for="(seg, si) in splitSegments(m.content)" :key="si">
                <div
                  v-if="seg.type === 'text' && seg.content.trim()"
                  class="whitespace-pre-wrap rounded-[6px] border border-[rgba(15,0,0,0.08)] bg-[#f8f7f7] px-3 py-2 text-xs leading-relaxed text-[#201d1d]"
                >
                  {{ seg.content.trim() }}
                </div>
                <div
                  v-else-if="seg.type === 'strategy'"
                  class="overflow-hidden rounded-[6px] border border-[#7c3aed]/30"
                >
                  <div class="flex items-center justify-between bg-[#7c3aed]/10 px-3 py-1.5">
                    <span class="flex items-center gap-1 text-[11px] font-semibold text-[#7c3aed]">
                      <BookMarked :size="12" /> 策略
                    </span>
                    <button
                      class="rounded-[4px] border border-[#7c3aed]/40 bg-transparent px-2 py-0.5 text-[11px] text-[#7c3aed] hover:bg-[#7c3aed]/10 disabled:opacity-50"
                      :disabled="savedKeys.has(seg.content)"
                      @click="saveStrategy(seg.content)"
                    >
                      {{ savedKeys.has(seg.content) ? '已存入策略库（工作中）' : '保存到策略库' }}
                    </button>
                  </div>
                  <pre class="max-h-[320px] overflow-auto whitespace-pre-wrap bg-[#fdfcfc] px-3 py-2 font-mono text-[11px] leading-relaxed text-[#201d1d]">{{ seg.content }}</pre>
                </div>
              </template>
              <div v-if="streaming && i === messages.length - 1 && !m.content" class="flex items-center gap-1.5 px-1 text-xs text-[#9a9898]">
                <Loader2 :size="12" class="animate-spin" /> QUBE 思考中...
              </div>
            </div>
          </div>
        </div>

        <div v-if="chatError" class="rounded-[4px] border border-[#ff3b30]/40 bg-[#ff3b30]/8 px-3 py-2 text-xs text-[#ff3b30]">
          {{ chatError }}
        </div>
      </div>

      <!-- 输入区 -->
      <div class="shrink-0 border-t border-[rgba(15,0,0,0.08)] p-3">
        <div class="flex items-end gap-2">
          <textarea
            v-model="input"
            rows="2"
            placeholder="描述你想要的策略，Enter 发送，Shift+Enter 换行"
            class="flex-1 resize-none rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-3 py-2 text-xs leading-relaxed text-[#201d1d] outline-none focus:border-[#7c3aed]"
            @keydown.enter.exact.prevent="send"
          />
          <button
            :disabled="streaming || !input.trim()"
            class="flex h-[34px] items-center gap-1 rounded-[4px] border-0 bg-[#7c3aed] px-4 text-xs text-white hover:opacity-90 disabled:opacity-40"
            @click="send"
          >
            <Send :size="13" /> 发送
          </button>
        </div>
      </div>
    </div>

    <!-- 右侧：策略工作台分屏（对话产出的策略在此回测/优化/管理版本） -->
    <div
      v-show="workbenchOpen"
      class="min-w-0 shrink-0 border-l border-[rgba(15,0,0,0.08)]"
      style="width: 44%"
    >
      <StrategyWorkbench ref="workbenchRef" :session-id="activeId" />
    </div>

    <!-- 配置抽屉 -->
    <div v-if="configOpen" class="fixed inset-0 z-[80] flex justify-end bg-black/30" @click.self="configOpen = false">
      <div class="flex h-full w-[400px] flex-col overflow-y-auto border-l border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] p-4">
        <div class="mb-3 flex items-center justify-between">
          <span class="text-[13px] font-semibold text-[#201d1d]">QUBE Agent 配置</span>
          <button class="border-0 bg-transparent text-[#646262] hover:text-[#201d1d]" @click="configOpen = false">
            <X :size="15" />
          </button>
        </div>
        <div class="mb-3 text-[11px] leading-relaxed text-[#9a9898]">
          与「设置 → AI 配置」完全独立；引擎可选 API 供应商或本机 CLI 工具。
        </div>

        <!-- 引擎 -->
        <div class="mb-3">
          <label class="mb-1 block text-xs text-[#646262]">引擎</label>
          <div class="flex gap-1.5">
            <button
              v-for="e in [{ k: 'api', l: 'API 供应商' }, { k: 'cli', l: '本机 CLI 工具' }]"
              :key="e.k"
              class="rounded-[4px] px-3 py-1 text-xs"
              :class="cfg.qube_engine === e.k ? 'bg-[#201d1d] text-[#fdfcfc]' : 'bg-[#f1eeee] text-[#646262] hover:text-[#201d1d]'"
              @click="cfg.qube_engine = e.k"
            >
              {{ e.l }}
            </button>
          </div>
        </div>

        <!-- API 供应商 -->
        <template v-if="cfg.qube_engine === 'api'">
          <div class="mb-3">
            <label class="mb-1 block text-xs text-[#646262]">供应商（预置免 Base URL，仅自定义 BYOK 需自填）</label>
            <div class="flex flex-wrap gap-1.5">
              <button
                v-for="p in providers"
                :key="p.id"
                class="rounded-[4px] px-2.5 py-1 text-[11px]"
                :class="cfg.qube_provider === p.id ? 'bg-[#201d1d] text-[#fdfcfc]' : 'bg-[#f1eeee] text-[#646262] hover:text-[#201d1d]'"
                @click="pickProvider(p)"
              >
                {{ p.label }}
              </button>
            </div>
          </div>
          <div v-if="selectedProvider?.byok" class="mb-3">
            <label class="mb-1 block text-xs text-[#646262]">Base URL（BYOK）</label>
            <input
              v-model="cfg.qube_base_url"
              placeholder="https://your-endpoint/v1"
              class="w-full rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-2.5 py-1.5 text-xs outline-none focus:border-[#007aff]"
            />
          </div>
          <div class="mb-3">
            <label class="mb-1 block text-xs text-[#646262]">模型</label>
            <!-- 预置供应商：从清单下拉选择；BYOK 无清单手输 -->
            <Select
              v-if="modelOptions.length"
              v-model="cfg.qube_model"
              :options="modelOptions"
              placeholder="选择模型"
            />
            <input
              v-else
              v-model="cfg.qube_model"
              placeholder="模型名称"
              class="w-full rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-2.5 py-1.5 text-xs outline-none focus:border-[#007aff]"
            />
          </div>
          <div class="mb-3">
            <label class="mb-1 block text-xs text-[#646262]">推理强度</label>
            <div class="flex gap-1.5">
              <button
                v-for="lv in EFFORT_LEVELS"
                :key="lv.k"
                class="rounded-[4px] px-3 py-1 text-xs"
                :class="cfg.qube_effort === lv.k ? 'bg-[#201d1d] text-[#fdfcfc]' : 'bg-[#f1eeee] text-[#646262] hover:text-[#201d1d]'"
                @click="cfg.qube_effort = lv.k"
              >
                {{ lv.label }}
              </button>
            </div>
            <div class="mt-1 text-[10px] text-[#9a9898]">仅支持 reasoning_effort 的推理模型生效；越高越强但越慢。</div>
          </div>
          <div class="mb-3">
            <label class="mb-1 block text-xs text-[#646262]">
              API Key {{ cfgKeyMasked ? `（已设置 ${cfgKeyMasked}，留空不修改）` : '' }}
            </label>
            <input
              v-model="cfg.qube_api_key"
              type="password"
              placeholder="sk-..."
              class="w-full rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-2.5 py-1.5 text-xs outline-none focus:border-[#007aff]"
            />
          </div>
        </template>

        <!-- CLI 工具 -->
        <template v-else>
          <div class="mb-3">
            <label class="mb-1 block text-xs text-[#646262]">CLI 工具（灰色表示本机未检测到）</label>
            <div class="flex flex-col gap-1">
              <button
                v-for="t in cliTools"
                :key="t.id"
                class="flex items-center justify-between rounded-[4px] px-2.5 py-1.5 text-left text-xs"
                :class="cfg.qube_cli === t.id ? 'bg-[#201d1d] text-[#fdfcfc]' : 'bg-[#f1eeee] text-[#646262] hover:text-[#201d1d]'"
                @click="cfg.qube_cli = t.id"
              >
                <span :class="!t.available && cfg.qube_cli !== t.id ? 'opacity-45' : ''">{{ t.label }}</span>
                <span class="font-mono text-[10px]" :class="t.available ? 'text-[#30d158]' : 'text-[#9a9898]'">
                  {{ t.available ? '可用' : '未安装' }}
                </span>
              </button>
            </div>
          </div>
          <div class="mb-3 text-[11px] leading-relaxed text-[#9a9898]">
            使用你本机已登录的 CLI 工具作为 Agent 引擎（无需 API Key）。
          </div>

          <!-- CLI 模型（建议芯片 + 自由输入；留空=CLI 默认） -->
          <div v-if="selectedCli?.supports_model" class="mb-3">
            <label class="mb-1 block text-xs text-[#646262]">模型（留空 = 用 CLI 自身默认）</label>
            <div v-if="selectedCli?.models?.length" class="mb-1.5 flex flex-wrap gap-1.5">
              <button
                v-for="m in selectedCli.models"
                :key="m"
                class="rounded-[4px] px-2 py-0.5 text-[11px]"
                :class="cfg.qube_cli_model === m ? 'bg-[#201d1d] text-[#fdfcfc]' : 'bg-[#f1eeee] text-[#646262] hover:text-[#201d1d]'"
                @click="cfg.qube_cli_model = m"
              >
                {{ m }}
              </button>
            </div>
            <input
              v-model="cfg.qube_cli_model"
              placeholder="模型名（可自由输入，留空用默认）"
              class="w-full rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-2.5 py-1.5 text-xs outline-none focus:border-[#007aff]"
            />
          </div>

          <!-- CLI 推理强度（仅支持的工具显示） -->
          <div v-if="selectedCli?.supports_effort" class="mb-3">
            <label class="mb-1 block text-xs text-[#646262]">推理强度</label>
            <div class="flex flex-wrap gap-1.5">
              <button
                v-for="lv in CLI_EFFORT_LEVELS"
                :key="lv.k"
                class="rounded-[4px] px-3 py-1 text-xs"
                :class="cfg.qube_cli_effort === lv.k ? 'bg-[#201d1d] text-[#fdfcfc]' : 'bg-[#f1eeee] text-[#646262] hover:text-[#201d1d]'"
                @click="cfg.qube_cli_effort = lv.k"
              >
                {{ lv.label }}
              </button>
            </div>
            <div class="mt-1 text-[10px] text-[#9a9898]">选“CLI 默认”则不传强度参数；具体档位是否生效取决于所选模型/供应商。</div>
          </div>
        </template>

        <div class="mt-1 flex items-center gap-2">
          <button
            :disabled="cfgSaving"
            class="rounded-[4px] border-0 bg-[#201d1d] px-4 py-1.5 text-xs text-[#fdfcfc] hover:opacity-85 disabled:opacity-50"
            @click="saveConfig"
          >
            {{ cfgSaving ? '保存中...' : '保存配置' }}
          </button>
          <span class="text-[11px] text-[#646262]">{{ cfgMsg }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
