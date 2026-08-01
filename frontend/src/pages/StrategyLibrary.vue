<script setup lang="ts">
/**
 * StrategyLibrary — 策略库（工作产出 / 落地成果）
 *
 * 分类规则：QUBE 对话产出的策略与工作流都归「工作产出」；
 * 只有用户点「设为落地成果」才进入「落地成果」（系统/AI 不会自动提升）。
 * 工作流以虚拟条目出现（id=wf:xxx），提升时后端落快照行。
 */
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { BookMarked, ExternalLink, GitBranch, MessageSquare, Radio, Trash2, X } from 'lucide-vue-next'
import { Tabs } from '@/components/ui'
import type { TabItem } from '@/components/ui'
import CodeEditor from '@/components/ui/CodeEditor.vue'

interface Strategy {
  id: string
  name: string
  description: string
  status: 'working' | 'saved'
  source: 'chat' | 'workflow'
  content: string
  workflow_id: string
  session_id: string
  updated_at: number
}

const router = useRouter()
const tabs: TabItem[] = [
  { key: 'working', label: '工作产出' },
  { key: 'saved', label: '落地成果' },
]
const active = ref('working')
const items = ref<Strategy[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

async function jsonFetch(url: string, options?: RequestInit) {
  const res = await fetch(url, options)
  const body = await res.json().catch(() => null)
  if (!res.ok) throw new Error(body?.detail || `HTTP ${res.status}`)
  return body
}

async function load() {
  loading.value = true
  error.value = null
  try {
    const d = await jsonFetch(`/api/strategy/?status=${active.value}`)
    items.value = d.strategies
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

function switchTab(k: string) {
  active.value = k
  load()
}

async function promote(s: Strategy) {
  await jsonFetch(`/api/strategy/${encodeURIComponent(s.id)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status: 'saved' }),
  })
  load()
}

async function backToWorking(s: Strategy) {
  await jsonFetch(`/api/strategy/${encodeURIComponent(s.id)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status: 'working' }),
  })
  load()
}

async function remove(s: Strategy) {
  await jsonFetch(`/api/strategy/${encodeURIComponent(s.id)}`, { method: 'DELETE' })
  load()
}

function openSource(s: Strategy) {
  if (s.source === 'workflow' && s.workflow_id) router.push(`/workflow/${s.workflow_id}`)
  else if (s.session_id) router.push({ path: '/qube', query: { session: s.session_id } })
  else router.push('/qube')
}

function fmtTime(ts: number): string {
  if (!ts) return '—'
  return new Date(ts * 1000).toLocaleString()
}

// 策略详情弹窗
const detail = ref<Strategy | null>(null)

// QMT 转写弹窗（导出方向：本平台 generate_signals → 迅投 QMT 实盘代码）
const qmt = ref<{
  strategy: Strategy
  loading: boolean
  code: string
  note: string
  filename: string
  error: string
} | null>(null)

function openQmt(s: Strategy) {
  qmt.value = { strategy: s, loading: false, code: '', note: '', filename: '', error: '' }
}

async function runQmt() {
  if (!qmt.value) return
  qmt.value.loading = true
  qmt.value.error = ''
  try {
    const d = await jsonFetch(`/api/strategy/${encodeURIComponent(qmt.value.strategy.id)}/export-qmt`, {
      method: 'POST',
    })
    qmt.value.code = d.code
    qmt.value.note = d.note
    qmt.value.filename = d.filename
  } catch (e) {
    qmt.value.error = e instanceof Error ? e.message : String(e)
  } finally {
    qmt.value.loading = false
  }
}

async function copyQmt() {
  if (qmt.value?.code) await navigator.clipboard.writeText(qmt.value.code)
}

function downloadQmt() {
  if (!qmt.value?.code) return
  const blob = new Blob([qmt.value.code], { type: 'text/x-python' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = qmt.value.filename || 'strategy_qmt.py'
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(load)
</script>

<template>
  <div class="flex h-full flex-col p-4">
    <div class="mb-3 flex items-center justify-between">
      <div class="flex items-center gap-2">
        <BookMarked :size="16" class="text-[#007aff]" />
        <span class="text-sm font-semibold text-[#201d1d]">策略库</span>
        <span class="text-[11px] text-[#9a9898]">
          工作流与 QUBE 对话产出默认「工作产出」；只有你能设为「落地成果」
        </span>
      </div>
      <Tabs :items="tabs" :active-key="active" @change="switchTab" />
    </div>

    <div v-if="error" class="mb-2 rounded-[4px] border border-[#ff3b30]/40 bg-[#ff3b30]/8 px-3 py-2 text-xs text-[#ff3b30]">
      {{ error }}
    </div>

    <div class="min-h-0 flex-1 overflow-y-auto">
      <div v-if="loading" class="flex h-32 items-center justify-center text-xs text-[#646262]">加载中...</div>
      <div v-else-if="!items.length" class="flex h-32 items-center justify-center text-xs text-[#9a9898]">
        {{ active === 'working' ? '暂无工作产出的策略 — 去 QUBE 对话创建，或新建工作流' : '暂无落地成果 — 在「工作产出」里手动设为落地成果' }}
      </div>

      <div v-else class="grid grid-cols-1 gap-2.5 md:grid-cols-2 xl:grid-cols-3">
        <div
          v-for="s in items"
          :key="s.id"
          class="flex flex-col rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] p-3 transition-colors hover:border-[rgba(15,0,0,0.25)]"
        >
          <div class="mb-1 flex items-center justify-between gap-2">
            <span class="truncate text-[13px] font-medium text-[#201d1d]">{{ s.name }}</span>
            <span
              class="flex shrink-0 items-center gap-1 rounded-[3px] px-1.5 py-0.5 text-[10px]"
              :class="s.source === 'workflow' ? 'bg-[#007aff]/10 text-[#007aff]' : 'bg-[#7c3aed]/10 text-[#7c3aed]'"
            >
              <component :is="s.source === 'workflow' ? GitBranch : MessageSquare" :size="10" />
              {{ s.source === 'workflow' ? '工作流' : 'QUBE 对话' }}
            </span>
          </div>
          <div class="mb-2 line-clamp-2 min-h-[16px] text-[11px] text-[#646262]">
            {{ s.description || (s.content ? s.content.slice(0, 80) : '暂无描述') }}
          </div>
          <div class="mt-auto flex items-center justify-between">
            <span class="text-[10px] text-[#9a9898]">{{ fmtTime(s.updated_at) }}</span>
            <div class="flex items-center gap-1.5">
              <button
                v-if="s.content"
                class="rounded-[3px] border border-[rgba(15,0,0,0.12)] bg-transparent px-2 py-0.5 text-[11px] text-[#424245] hover:text-[#201d1d]"
                @click="detail = s"
              >
                查看
              </button>
              <button
                class="flex items-center gap-0.5 rounded-[3px] border border-[rgba(15,0,0,0.12)] bg-transparent px-2 py-0.5 text-[11px] text-[#424245] hover:text-[#201d1d]"
                @click="openSource(s)"
              >
                <ExternalLink :size="10" /> 打开
              </button>
              <button
                v-if="s.source === 'chat' && !s.id.startsWith('wf:')"
                class="flex items-center gap-0.5 rounded-[3px] border border-[rgba(15,0,0,0.12)] bg-transparent px-2 py-0.5 text-[11px] text-[#424245] hover:text-[#201d1d]"
                title="转写为迅投 QMT 实盘代码"
                @click="openQmt(s)"
              >
                <Radio :size="10" /> 转写 QMT
              </button>
              <button
                v-if="s.status === 'working'"
                class="rounded-[3px] border-0 bg-[#201d1d] px-2 py-0.5 text-[11px] text-[#fdfcfc] hover:opacity-85"
                @click="promote(s)"
              >
                设为落地成果
              </button>
              <button
                v-else
                class="rounded-[3px] border border-[rgba(15,0,0,0.12)] bg-transparent px-2 py-0.5 text-[11px] text-[#424245] hover:text-[#201d1d]"
                @click="backToWorking(s)"
              >
                移回工作产出
              </button>
              <button
                v-if="!s.id.startsWith('wf:')"
                class="border-0 bg-transparent text-[#9a9898] hover:text-[#ff3b30]"
                title="删除策略"
                @click="remove(s)"
              >
                <Trash2 :size="12" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 策略详情弹窗 -->
    <div v-if="detail" class="fixed inset-0 z-[80] flex items-center justify-center bg-black/45" @click.self="detail = null">
      <div
        class="flex flex-col overflow-hidden rounded-[6px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc]"
        style="width: min(820px, 92vw); height: min(76vh, 680px)"
      >
        <div class="flex shrink-0 items-center justify-between border-b border-[rgba(15,0,0,0.12)] bg-[#f1eeee] px-4 py-2.5">
          <span class="text-[13px] font-semibold text-[#201d1d]">{{ detail.name }}</span>
          <button class="border-0 bg-transparent text-[#646262] hover:text-[#201d1d]" @click="detail = null">
            <X :size="15" />
          </button>
        </div>
        <div class="min-h-0 flex-1 p-4">
          <CodeEditor
            :model-value="detail.content"
            :language="detail.source === 'workflow' ? 'json' : 'markdown'"
            height="100%"
            read-only
            :lint="false"
            :title="detail.name"
            :font-size="12"
          />
        </div>
      </div>
    </div>

    <!-- QMT 转写弹窗 -->
    <div v-if="qmt" class="fixed inset-0 z-[80] flex items-center justify-center bg-black/45" @click.self="qmt = null">
      <div
        class="flex flex-col overflow-hidden rounded-[6px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc]"
        style="width: min(840px, 92vw); height: min(80vh, 720px)"
      >
        <div class="flex shrink-0 items-center justify-between border-b border-[rgba(15,0,0,0.12)] bg-[#f1eeee] px-4 py-2.5">
          <span class="flex items-center gap-1.5 text-[13px] font-semibold text-[#201d1d]">
            <Radio :size="14" /> 策略转写 · {{ qmt.strategy.name }}
          </span>
          <button class="border-0 bg-transparent text-[#646262] hover:text-[#201d1d]" @click="qmt = null">
            <X :size="15" />
          </button>
        </div>
        <div class="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
          <p class="text-[11px] leading-relaxed text-[#646262]">
            把本平台策略（generate_signals）转写成迅投 QMT（miniQMT / xtquant）可直接运行的实盘代码。
            若两边数据能力差异导致无法等价实现，AI 会明确告诉你哪里不行、为什么、怎么降级。
            目前仅提供 QMT 转写。
          </p>
          <div v-if="qmt.error" class="rounded-[4px] border border-[#ff3b30]/40 bg-[#ff3b30]/8 px-3 py-2 text-xs text-[#ff3b30]">
            {{ qmt.error }}
          </div>
          <div
            v-if="qmt.note"
            class="whitespace-pre-wrap rounded-[4px] border border-[#007aff]/25 bg-[#007aff]/6 px-3 py-2 text-[11px] leading-relaxed text-[#0056b3]"
          >
            {{ qmt.note }}
          </div>
          <div v-if="qmt.code" class="h-[360px]">
            <CodeEditor
              :model-value="qmt.code"
              language="python"
              height="100%"
              read-only
              :lint="false"
              :title="qmt.filename"
              :font-size="12"
            />
          </div>
          <div v-else-if="!qmt.loading" class="flex h-40 items-center justify-center text-xs text-[#9a9898]">
            点击下方「开始转写」生成 QMT 代码
          </div>
          <div v-else class="flex h-40 items-center justify-center text-xs text-[#646262]">AI 转写中…</div>
        </div>
        <div class="flex shrink-0 items-center justify-end gap-2 border-t border-[rgba(15,0,0,0.12)] px-4 py-2.5">
          <button
            v-if="qmt.code"
            class="rounded-[4px] border border-[rgba(15,0,0,0.15)] px-3 py-1 text-xs text-[#424245] hover:text-[#201d1d]"
            @click="copyQmt"
          >
            复制
          </button>
          <button
            v-if="qmt.code"
            class="rounded-[4px] border border-[rgba(15,0,0,0.15)] px-3 py-1 text-xs text-[#424245] hover:text-[#201d1d]"
            @click="downloadQmt"
          >
            下载 .py
          </button>
          <button
            :disabled="qmt.loading"
            class="rounded-[4px] bg-[#201d1d] px-4 py-1 text-xs text-[#fdfcfc] hover:opacity-85 disabled:opacity-50"
            @click="runQmt"
          >
            {{ qmt.loading ? '转写中…' : qmt.code ? '重新转写' : '开始转写' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
