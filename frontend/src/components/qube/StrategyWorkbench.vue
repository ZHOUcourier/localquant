<script setup lang="ts">
/**
 * StrategyWorkbench — QUBE 右侧策略工作台分屏
 *
 * 对话产出的策略在此独立呈现与迭代（参考官网策略工作台交互）：
 * - 顶部：策略选择下拉 + 状态徽章（工作中/已保存）
 * - 功能条：代码 / 回测 / 日志 / 版本 四个 tab + 运行回测 / AI 优化 / 自动优化
 * - 参数条：回测时间区间、初始资金、手续费倍率、滑点、频率（本地日线 1d）
 * - 代码：Monaco（高亮/补全/ruff），保存即记录版本；回测：指标卡 + 净值/回撤曲线；
 *   版本：历史列表可回滚；AI 优化用 QUBE 引擎，结果填入编辑器由用户确认保存
 */
import { computed, ref, watch } from 'vue'
import { Loader2, Play, RefreshCw, Repeat, Save, Sparkles } from 'lucide-vue-next'
import { Select, Tabs, VChart } from '@/components/ui'
import type { SelectOption, TabItem } from '@/components/ui'
import CodeEditor from '@/components/ui/CodeEditor.vue'

interface StrategyItem {
  id: string
  name: string
  status: 'working' | 'saved'
  source: string
  content: string
  code: string
  session_id: string
}
interface VersionItem {
  id: number
  note: string
  code: string
  created_at: number
}
interface BtResult {
  equity_curve: Record<string, number>
  drawdown_series: Record<string, number>
  tear_sheet: Record<string, number>
}

const props = defineProps<{ sessionId: string }>()

const strategies = ref<StrategyItem[]>([])
const selectedId = ref('')
const detail = ref<StrategyItem | null>(null)
const code = ref('')
const activeTab = ref('code')
const logs = ref<{ time: string; text: string; error?: boolean }[]>([])
const versions = ref<VersionItem[]>([])
const btResult = ref<BtResult | null>(null)
const btRunning = ref(false)
const aiRunning = ref(false)
const autoRunning = ref(false)
const saving = ref(false)
const aiNote = ref('')

// 回测参数（频率固定本地日线 1d）
const params = ref({
  start: '',
  end: '',
  capital: 1000000,
  feeMult: 1, // 手续费倍率 ×0.001
  slippage: 0.001,
})

const tabs: TabItem[] = [
  { key: 'code', label: '代码' },
  { key: 'backtest', label: '回测' },
  { key: 'logs', label: '日志' },
  { key: 'versions', label: '版本' },
]

const options = computed<SelectOption[]>(() =>
  strategies.value.map((s) => ({ value: s.id, label: s.name })),
)

function log(text: string, error = false) {
  logs.value.unshift({ time: new Date().toLocaleTimeString(), text, error })
}

async function jsonFetch(url: string, options?: RequestInit) {
  const res = await fetch(url, options)
  const body = await res.json().catch(() => null)
  if (!res.ok) throw new Error(body?.detail || `HTTP ${res.status}`)
  return body
}

// —— 策略列表 / 详情 ————————————————————————————————————————
async function loadList(preferId?: string) {
  const [w, s] = await Promise.all([
    jsonFetch('/api/strategy/?status=working'),
    jsonFetch('/api/strategy/?status=saved'),
  ])
  // 工作台只管理有代码语义的策略行（排除工作流虚拟条目）
  strategies.value = [...w.strategies, ...s.strategies].filter(
    (x: StrategyItem) => !x.id.startsWith('wf:'),
  )
  const prefer =
    preferId ||
    selectedId.value ||
    // 优先当前会话产出的策略
    strategies.value.find((x) => x.session_id === props.sessionId)?.id ||
    strategies.value[0]?.id ||
    ''
  if (prefer && strategies.value.some((x) => x.id === prefer)) selectedId.value = prefer
}

async function loadDetail() {
  if (!selectedId.value) {
    detail.value = null
    code.value = ''
    versions.value = []
    return
  }
  detail.value = await jsonFetch(`/api/strategy/${encodeURIComponent(selectedId.value)}`)
  code.value = detail.value?.code || ''
  btResult.value = null
  loadVersions()
}

async function loadVersions() {
  if (!selectedId.value) return
  const d = await jsonFetch(`/api/strategy/${encodeURIComponent(selectedId.value)}/versions`)
  versions.value = d.versions
}

watch(selectedId, loadDetail)
loadList()

// 供父组件在对话保存策略后刷新
defineExpose({ refresh: (preferId?: string) => loadList(preferId) })

// —— 保存版本 ————————————————————————————————————————————————
async function saveCode(note = '手动保存') {
  if (!detail.value) return
  saving.value = true
  try {
    await jsonFetch(`/api/strategy/${encodeURIComponent(detail.value.id)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: code.value, version_note: note }),
    })
    log(`已保存版本：${note}`)
    loadVersions()
  } catch (e) {
    log(`保存失败：${e instanceof Error ? e.message : e}`, true)
  } finally {
    saving.value = false
  }
}

// —— 运行回测 ————————————————————————————————————————————————
async function runBacktest(): Promise<boolean> {
  if (!code.value.trim()) {
    log('代码为空，无法回测', true)
    return false
  }
  btRunning.value = true
  try {
    const d = await jsonFetch('/api/backtest/run-strategy', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        signal_code: code.value,
        start_date: params.value.start,
        end_date: params.value.end,
        initial_capital: Number(params.value.capital) || 1000000,
        commission_rate: 0.001 * (Number(params.value.feeMult) || 1),
        slippage: Number(params.value.slippage) || 0,
      }),
    })
    btResult.value = d
    activeTab.value = 'backtest'
    const t = d.tear_sheet || {}
    const iso = d.sandboxed ? '🔒 沙箱隔离' : '⚠ 进程内（无容器隔离）'
    log(
      `回测完成[${iso}]：年化 ${fmtPct(t.annual_return)} · 夏普 ${fmtNum(t.sharpe_ratio)} · 最大回撤 ${fmtPct(t.max_drawdown)}`,
    )
    return true
  } catch (e) {
    log(`回测失败：${e instanceof Error ? e.message : e}`, true)
    activeTab.value = 'logs'
    return false
  } finally {
    btRunning.value = false
  }
}

// —— AI 优化 / 自动优化 ————————————————————————————————————————
async function aiOptimize(save = false): Promise<boolean> {
  if (!detail.value) return false
  aiRunning.value = true
  aiNote.value = ''
  try {
    const d = await jsonFetch(`/api/strategy/${encodeURIComponent(detail.value.id)}/optimize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        code: code.value,
        content: detail.value.content || '',
        metrics: btResult.value?.tear_sheet || {},
      }),
    })
    code.value = d.code
    aiNote.value = d.note
    activeTab.value = 'code'
    log(`AI 优化完成：${d.note.slice(0, 80)}`)
    if (save) await saveCode(`自动优化：${d.note.slice(0, 60)}`)
    else log('新代码已填入编辑器，确认后点「保存版本」')
    return true
  } catch (e) {
    log(`AI 优化失败：${e instanceof Error ? e.message : e}`, true)
    return false
  } finally {
    aiRunning.value = false
  }
}

/** 自动优化：优化 → 保存版本 → 回测，最多 3 轮，任一步失败即停 */
async function autoOptimize() {
  autoRunning.value = true
  log('自动优化开始（最多 3 轮：AI 优化 → 保存版本 → 回测）')
  try {
    for (let i = 1; i <= 3; i++) {
      log(`—— 第 ${i} 轮 ——`)
      if (!(await aiOptimize(true))) break
      if (!(await runBacktest())) break
    }
    log('自动优化结束')
  } finally {
    autoRunning.value = false
  }
}

async function rollback(v: VersionItem) {
  if (!detail.value) return
  try {
    const d = await jsonFetch(
      `/api/strategy/${encodeURIComponent(detail.value.id)}/versions/${v.id}/rollback`,
      { method: 'POST' },
    )
    code.value = d.code
    activeTab.value = 'code'
    log(`已回滚到版本 #${v.id}`)
    loadVersions()
  } catch (e) {
    log(`回滚失败：${e instanceof Error ? e.message : e}`, true)
  }
}

// —— 展示 ————————————————————————————————————————————————————
const METRICS: [string, string, boolean][] = [
  ['total_return', '总收益', true],
  ['annual_return', '年化收益', true],
  ['sharpe_ratio', '夏普比率', false],
  ['max_drawdown', '最大回撤', true],
  ['volatility', '年化波动', true],
  ['sortino_ratio', 'Sortino', false],
  ['calmar_ratio', 'Calmar', false],
  ['win_rate', '胜率', true],
  ['profit_loss_ratio', '盈亏比', false],
  ['trading_days', '交易日数', false],
]
function fmtPct(v?: number) {
  return typeof v === 'number' ? `${(v * 100).toFixed(2)}%` : '-'
}
function fmtNum(v?: number) {
  return typeof v === 'number' ? v.toFixed(3) : '-'
}
function metricVal(key: string, pct: boolean): string {
  const v = btResult.value?.tear_sheet?.[key]
  if (typeof v !== 'number') return '-'
  if (key === 'trading_days') return String(v)
  return pct ? fmtPct(v) : fmtNum(v)
}

function lineOption(series: Record<string, number>, color: string, asPct: boolean) {
  const dates = Object.keys(series).sort()
  return {
    grid: { left: 56, right: 12, top: 12, bottom: 24 },
    tooltip: {
      trigger: 'axis',
      valueFormatter: (v: number) => (asPct ? `${(Number(v) * 100).toFixed(2)}%` : Number(v).toFixed(0)),
    },
    xAxis: { type: 'category', data: dates, axisLabel: { fontSize: 10, color: '#646262' } },
    yAxis: {
      type: 'value',
      scale: true,
      axisLabel: {
        fontSize: 10,
        color: '#646262',
        formatter: asPct ? (v: number) => `${(v * 100).toFixed(0)}%` : undefined,
      },
      splitLine: { lineStyle: { color: 'rgba(15,0,0,0.06)' } },
    },
    series: [
      {
        type: 'line',
        showSymbol: false,
        data: dates.map((d) => series[d]),
        lineStyle: { width: 1.4, color },
        itemStyle: { color },
        areaStyle: asPct ? { color: `${color}22` } : undefined,
      },
    ],
  }
}
const equityOption = computed(() =>
  btResult.value ? lineOption(btResult.value.equity_curve, '#007aff', false) : null,
)
const ddOption = computed(() =>
  btResult.value ? lineOption(btResult.value.drawdown_series, '#ff3b30', true) : null,
)

function fmtTime(ts: number) {
  return new Date(ts * 1000).toLocaleString()
}

const busy = computed(() => btRunning.value || aiRunning.value || autoRunning.value || saving.value)
</script>

<template>
  <div class="flex h-full flex-col bg-[#f8f7f7]">
    <!-- 顶部：策略选择 + 状态 -->
    <div class="flex shrink-0 items-center gap-2 border-b border-[rgba(15,0,0,0.08)] bg-[#fdfcfc] px-3 py-2">
      <div class="w-[220px]">
        <Select v-model="selectedId" :options="options" placeholder="选择策略" />
      </div>
      <span
        v-if="detail"
        class="rounded-full px-2 py-0.5 text-[10px]"
        :class="detail.status === 'saved' ? 'bg-[#30d158]/12 text-[#1d8a3e]' : 'bg-[#ff9f0a]/12 text-[#9a6200]'"
      >
        {{ detail.status === 'saved' ? '✓ 已保存' : '● 工作中' }}
      </span>
      <button
        class="ml-auto flex items-center gap-1 rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-transparent px-2 py-1 text-[11px] text-[#646262] hover:text-[#201d1d]"
        title="刷新策略列表"
        @click="loadList()"
      >
        <RefreshCw :size="11" />
      </button>
    </div>

    <div v-if="!detail" class="flex flex-1 flex-col items-center justify-center gap-2 text-[#9a9898]">
      <div class="text-xs">暂无策略 — 在左侧与 QUBE 对话产出策略后自动出现在这里</div>
    </div>

    <template v-else>
      <!-- 功能条：名称 + tabs + 操作按钮 -->
      <div class="flex shrink-0 flex-wrap items-center gap-2 border-b border-[rgba(15,0,0,0.08)] bg-[#fdfcfc] px-3 py-2">
        <span class="max-w-[180px] truncate text-[13px] font-semibold text-[#201d1d]" :title="detail.name">
          {{ detail.name }}
        </span>
        <Tabs :items="tabs" :active-key="activeTab" @change="(k) => (activeTab = k)" />
        <div class="ml-auto flex items-center gap-1.5">
          <button
            :disabled="busy"
            class="flex items-center gap-1 rounded-[4px] border-0 bg-[#201d1d] px-3 py-1.5 text-[11px] font-medium text-[#fdfcfc] hover:opacity-85 disabled:opacity-40"
            @click="runBacktest"
          >
            <Loader2 v-if="btRunning" :size="11" class="animate-spin" />
            <Play v-else :size="11" />
            运行回测
          </button>
          <button
            :disabled="busy"
            class="flex items-center gap-1 rounded-[4px] border border-[#7c3aed]/40 bg-transparent px-3 py-1.5 text-[11px] text-[#7c3aed] hover:bg-[#7c3aed]/10 disabled:opacity-40"
            @click="aiOptimize(false)"
          >
            <Loader2 v-if="aiRunning && !autoRunning" :size="11" class="animate-spin" />
            <Sparkles v-else :size="11" />
            AI 优化
          </button>
          <button
            :disabled="busy"
            class="flex items-center gap-1 rounded-[4px] border border-[rgba(15,0,0,0.15)] bg-transparent px-3 py-1.5 text-[11px] text-[#424245] hover:text-[#201d1d] disabled:opacity-40"
            title="最多 3 轮：AI 优化 → 保存版本 → 回测"
            @click="autoOptimize"
          >
            <Loader2 v-if="autoRunning" :size="11" class="animate-spin" />
            <Repeat v-else :size="11" />
            自动优化
          </button>
        </div>
      </div>

      <!-- 回测参数条 -->
      <div class="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-[rgba(15,0,0,0.08)] bg-[#fdfcfc] px-3 py-2 text-[11px] text-[#646262]">
        <span class="font-medium text-[#201d1d]">回测参数</span>
        <span class="rounded-[3px] bg-[#f1eeee] px-1.5 py-0.5 text-[10px]">股票 · 本地日线</span>
        <label class="flex items-center gap-1">
          时间
          <input v-model="params.start" type="date" class="rounded-[3px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-1.5 py-0.5 text-[11px] outline-none" />
          →
          <input v-model="params.end" type="date" class="rounded-[3px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-1.5 py-0.5 text-[11px] outline-none" />
        </label>
        <label class="flex items-center gap-1">
          初始资金
          <input v-model="params.capital" type="number" class="w-[92px] rounded-[3px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-1.5 py-0.5 text-[11px] outline-none" />
        </label>
        <label class="flex items-center gap-1">
          手续费倍率
          <input v-model="params.feeMult" type="number" step="0.5" min="0" class="w-[52px] rounded-[3px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-1.5 py-0.5 text-[11px] outline-none" />
          x
        </label>
        <label class="flex items-center gap-1">
          滑点
          <input v-model="params.slippage" type="number" step="0.001" min="0" class="w-[60px] rounded-[3px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-1.5 py-0.5 text-[11px] outline-none" />
        </label>
        <span>频率 1d</span>
      </div>

      <!-- 内容区 -->
      <div class="min-h-0 flex-1 overflow-y-auto p-3">
        <!-- 代码 -->
        <div v-show="activeTab === 'code'" class="flex h-full flex-col gap-2">
          <div
            v-if="aiNote"
            class="shrink-0 rounded-[4px] border border-[#7c3aed]/30 bg-[#7c3aed]/8 px-2.5 py-1.5 text-[11px] leading-relaxed text-[#5b21b6]"
          >
            ✦ {{ aiNote }}
          </div>
          <div class="min-h-[260px] flex-1">
            <CodeEditor v-model="code" language="python" height="100%" :title="`策略代码 · ${detail.name}`" :font-size="12" />
          </div>
          <div class="flex shrink-0 items-center gap-2">
            <button
              :disabled="busy"
              class="flex items-center gap-1 rounded-[4px] border border-[rgba(15,0,0,0.15)] bg-transparent px-3 py-1.5 text-[11px] text-[#424245] hover:text-[#201d1d] disabled:opacity-40"
              @click="saveCode()"
            >
              <Save :size="11" /> 保存版本
            </button>
            <span class="text-[10px] text-[#9a9898]">
              需定义 generate_signals(prices, **kwargs)；保存即记录一条版本
            </span>
          </div>
        </div>

        <!-- 回测 -->
        <div v-show="activeTab === 'backtest'" class="space-y-3">
          <div v-if="!btResult" class="flex h-40 items-center justify-center text-xs text-[#9a9898]">
            尚未回测 — 点击右上「运行回测」
          </div>
          <template v-else>
            <div class="grid grid-cols-2 gap-2 sm:grid-cols-5">
              <div v-for="[key, label, pct] in METRICS" :key="key" class="rounded-[4px] border border-[rgba(15,0,0,0.1)] bg-[#fdfcfc] px-2.5 py-2">
                <div class="text-[10px] text-[#9a9898]">{{ label }}</div>
                <div class="mt-0.5 font-mono text-[13px] font-semibold text-[#201d1d]">
                  {{ metricVal(key, pct) }}
                </div>
              </div>
            </div>
            <div class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] p-3">
              <div class="mb-2 text-xs font-semibold text-[#201d1d]">净值曲线</div>
              <VChart v-if="equityOption" :option="equityOption" :height="220" />
            </div>
            <div class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] p-3">
              <div class="mb-2 text-xs font-semibold text-[#201d1d]">回撤曲线</div>
              <VChart v-if="ddOption" :option="ddOption" :height="180" />
            </div>
          </template>
        </div>

        <!-- 日志 -->
        <div v-show="activeTab === 'logs'" class="space-y-1">
          <div v-if="!logs.length" class="flex h-40 items-center justify-center text-xs text-[#9a9898]">
            暂无日志 — 回测 / AI 优化 / 版本操作会记录在这里
          </div>
          <div
            v-for="(l, i) in logs"
            :key="i"
            class="flex gap-2 rounded-[3px] px-2 py-1 font-mono text-[11px]"
            :class="l.error ? 'bg-[#ff3b30]/8 text-[#c62d23]' : 'text-[#424245]'"
          >
            <span class="shrink-0 text-[#9a9898]">{{ l.time }}</span>
            <span class="whitespace-pre-wrap break-all">{{ l.text }}</span>
          </div>
        </div>

        <!-- 版本 -->
        <div v-show="activeTab === 'versions'" class="space-y-1.5">
          <div v-if="!versions.length" class="flex h-40 items-center justify-center text-xs text-[#9a9898]">
            暂无版本记录
          </div>
          <div
            v-for="v in versions"
            :key="v.id"
            class="flex items-center gap-2 rounded-[4px] border border-[rgba(15,0,0,0.1)] bg-[#fdfcfc] px-2.5 py-2"
          >
            <span class="shrink-0 font-mono text-[11px] text-[#9a9898]">#{{ v.id }}</span>
            <span class="min-w-0 flex-1 truncate text-[11px] text-[#201d1d]" :title="v.note">{{ v.note }}</span>
            <span class="shrink-0 text-[10px] text-[#9a9898]">{{ fmtTime(v.created_at) }}</span>
            <button
              class="shrink-0 rounded-[3px] border border-[rgba(15,0,0,0.12)] bg-transparent px-2 py-0.5 text-[10px] text-[#424245] hover:text-[#201d1d]"
              @click="rollback(v)"
            >
              回滚
            </button>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
