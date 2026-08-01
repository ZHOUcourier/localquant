<script setup lang="ts">
/**
 * StrategyWorkbench — 右侧策略画板（复刻参考站 272）
 *
 * - 头部：策略名（可编辑）+ 状态徽章 + Tab「代码｜回测｜日志｜版本」
 *   + 操作行「▶ 运行回测（黑）/ ✦ AI 优化（白）/ 设为落地成果」
 * - 回测参数卡：起止日期/初始资金/手续费/滑点（会话级持久化）
 * - 回测 Tab：8 阶段进度 → 生效参数 → 指标卡 → 净值曲线 → 交易明细
 * - 日志 Tab：回测运行日志；版本 Tab：载入编辑器/回滚
 * - 回测走 /api/backtest/runs 落库 + 轮询，历史下拉可切换往次
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Select } from '@/components/ui'
import type { SelectOption } from '@/components/ui'
import CodeEditor from '@/components/ui/CodeEditor.vue'
import VChart from '@/components/ui/VChart.vue'
import StageProgress from './StageProgress.vue'
import type { BacktestRun, BacktestRunDetail } from './types'
import { fmtNum, fmtPct, fmtTime, jsonFetch } from './types'
import type { SessionWorkspace } from '@/composables/useQubeWorkspace'

interface StrategyDetail {
  id: string
  name: string
  status: 'working' | 'saved'
  description: string
  content: string
  code: string
}
interface VersionItem {
  id: number
  note: string
  code: string
  created_at: number
}

const props = defineProps<{
  strategyId: string
  sessionId: string
  ws: SessionWorkspace
}>()

const detail = ref<StrategyDetail | null>(null)
const code = ref('')
const versions = ref<VersionItem[]>([])
const runs = ref<BacktestRun[]>([])
const runDetail = ref<BacktestRunDetail | null>(null)
const btRunning = ref(false)
const aiRunning = ref(false)
const aiNote = ref('')
const errorMsg = ref('')
const editingName = ref(false)
const nameDraft = ref('')
let pollTimer: ReturnType<typeof setInterval> | null = null

const tab = computed({
  get: () => props.ws.canvasTab || 'code',
  set: (v: string) => (props.ws.canvasTab = v),
})

const TABS = [
  { k: 'code', l: '代码' },
  { k: 'backtest', l: '回测' },
  { k: 'logs', l: '日志' },
  { k: 'versions', l: '版本' },
]

// —— 加载 ————————————————————————————————————————————————
async function loadDetail() {
  if (!props.strategyId) return
  try {
    detail.value = await jsonFetch(`/api/strategy/${encodeURIComponent(props.strategyId)}`)
    code.value = detail.value?.code || ''
    errorMsg.value = ''
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e)
    detail.value = null
  }
}

async function loadVersions() {
  if (!props.strategyId) return
  const d = await jsonFetch(`/api/strategy/${encodeURIComponent(props.strategyId)}/versions`)
  versions.value = d.versions
}

async function loadRuns(selectId?: string) {
  if (!props.strategyId) return
  const d = await jsonFetch(`/api/backtest/runs?strategy_id=${encodeURIComponent(props.strategyId)}`)
  runs.value = d.runs
  const prefer = selectId || props.ws.selectedBacktestRunId || runs.value[0]?.id || ''
  if (prefer && runs.value.some((r) => r.id === prefer)) await openRun(prefer)
  else runDetail.value = null
}

async function openRun(id: string) {
  props.ws.selectedBacktestRunId = id
  runDetail.value = await jsonFetch(`/api/backtest/runs/${id}`)
  if (runDetail.value?.status === 'running') startPolling(id)
}

function startPolling(id: string) {
  stopPolling()
  btRunning.value = true
  pollTimer = setInterval(async () => {
    try {
      const d: BacktestRunDetail = await jsonFetch(`/api/backtest/runs/${id}`)
      runDetail.value = d
      if (d.status !== 'running') {
        stopPolling()
        loadRuns(id)
      }
    } catch {
      stopPolling()
    }
  }, 1500)
}

function stopPolling() {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = null
  btRunning.value = false
}

onBeforeUnmount(stopPolling)

watch(
  () => props.strategyId,
  () => {
    stopPolling()
    runDetail.value = null
    aiNote.value = ''
    loadDetail()
    loadVersions()
    loadRuns()
  },
  { immediate: true },
)

defineExpose({
  refresh: () => {
    loadDetail()
    loadVersions()
    loadRuns()
  },
  openRun: (id: string) => {
    tab.value = 'backtest'
    openRun(id)
  },
})

// —— 编辑 / 保存 ————————————————————————————————————————
async function commitName() {
  if (!detail.value) return
  const name = nameDraft.value.trim()
  editingName.value = false
  if (name && name !== detail.value.name) {
    detail.value.name = name
    await jsonFetch(`/api/strategy/${encodeURIComponent(detail.value.id)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    })
  }
}

async function saveCode(note = '手动保存') {
  if (!detail.value) return
  await jsonFetch(`/api/strategy/${encodeURIComponent(detail.value.id)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code: code.value, version_note: note }),
  })
  loadVersions()
}

async function markSaved() {
  if (!detail.value) return
  await jsonFetch(`/api/strategy/${encodeURIComponent(detail.value.id)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status: 'saved' }),
  })
  detail.value.status = 'saved'
}

// —— 回测 ————————————————————————————————————————————————
async function runBacktest() {
  if (!detail.value || btRunning.value) return
  errorMsg.value = ''
  try {
    // 编辑器内容与库里不同则先落一版
    if (code.value !== detail.value.code) {
      await saveCode('回测前自动保存')
      detail.value.code = code.value
    }
    const p = props.ws.backtestParams
    const d = await jsonFetch('/api/backtest/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        strategy_id: detail.value.id,
        strategy_name: detail.value.name,
        session_id: props.sessionId,
        signal_code: code.value,
        period_start: p.period_start,
        period_end: p.period_end,
        init_balance: Number(p.init_balance) || 1000000,
        commission_rate: Number(p.commission_rate) || 0,
        slippage: Number(p.slippage) || 0,
      }),
    })
    tab.value = 'backtest'
    props.ws.selectedBacktestRunId = d.id
    runDetail.value = null
    startPolling(d.id)
    openRun(d.id)
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e)
  }
}

// —— AI 优化 ————————————————————————————————————————————
async function aiOptimize() {
  if (!detail.value || aiRunning.value) return
  aiRunning.value = true
  aiNote.value = ''
  errorMsg.value = ''
  try {
    const d = await jsonFetch(`/api/strategy/${encodeURIComponent(detail.value.id)}/optimize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        code: code.value,
        content: detail.value.content || detail.value.description || '',
        metrics: runDetail.value?.metrics || {},
      }),
    })
    code.value = d.code
    aiNote.value = d.note
    tab.value = 'code'
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e)
  } finally {
    aiRunning.value = false
  }
}

// —— 版本 ————————————————————————————————————————————————
async function rollback(v: VersionItem) {
  if (!detail.value) return
  const d = await jsonFetch(
    `/api/strategy/${encodeURIComponent(detail.value.id)}/versions/${v.id}/rollback`,
    { method: 'POST' },
  )
  code.value = d.code
  tab.value = 'code'
  loadVersions()
}

function loadToEditor(v: VersionItem) {
  code.value = v.code
  tab.value = 'code'
}

// —— 展示 ————————————————————————————————————————————————
const historyOptions = computed<SelectOption[]>(() =>
  runs.value.map((r) => ({
    value: r.id,
    label: `${fmtTime(r.created_at)} · ${r.status === 'done' ? '完成' : r.status === 'error' ? '失败' : '运行中'}`,
  })),
)

const METRICS: [string, string, 'pct' | 'num' | 'int' | 'cash'][] = [
  ['total_return', '总收益', 'pct'],
  ['annual_return', '年化收益', 'pct'],
  ['max_drawdown', '最大回撤', 'pct'],
  ['sharpe_ratio', '夏普', 'num'],
  ['trade_count', '交易笔数', 'int'],
  ['final_equity', '最终权益', 'cash'],
]

function metricVal(key: string, fmt: string): string {
  const v = runDetail.value?.metrics?.[key]
  if (typeof v !== 'number') return '-'
  if (fmt === 'pct') return fmtPct(v)
  if (fmt === 'int') return String(Math.round(v))
  if (fmt === 'cash') return v.toLocaleString('zh-CN', { maximumFractionDigits: 0 })
  return fmtNum(v, 2)
}

const equityOption = computed(() => {
  const eq = runDetail.value?.equity
  if (!eq?.length) return null
  return {
    grid: { left: 60, right: 12, top: 12, bottom: 22 },
    tooltip: { trigger: 'axis', valueFormatter: (v: number) => Number(v).toFixed(0) },
    xAxis: {
      type: 'category',
      data: eq.map((p) => p.ts),
      axisLabel: { fontSize: 9, color: '#646262' },
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLabel: { fontSize: 9, color: '#646262' },
      splitLine: { lineStyle: { color: 'rgba(15,0,0,0.06)' } },
    },
    series: [
      {
        type: 'line',
        showSymbol: false,
        data: eq.map((p) => p.equity),
        lineStyle: { width: 1.4, color: '#201d1d' },
        itemStyle: { color: '#201d1d' },
      },
    ],
  }
})

const effectiveParams = computed(() => {
  const p = runDetail.value?.params || {}
  return [
    ['period_start', String(p.period_start || '自动')],
    ['period_end', String(p.period_end || '自动')],
    ['init_balance', String(p.init_balance ?? 1000000)],
    ['commission_rate', String(p.commission_rate ?? 0.001)],
    ['slippage', String(p.slippage ?? 0.001)],
    ['frequency', '1d'],
  ]
})

const logLines = computed(() => (runDetail.value?.log || '').split('\n').filter(Boolean))

const busy = computed(() => btRunning.value || aiRunning.value)
</script>

<template>
  <div class="flex h-full flex-col overflow-hidden">
    <div v-if="!detail" class="flex flex-1 items-center justify-center text-xs text-[#9a9898]">
      {{ errorMsg || '策略加载中…' }}
    </div>
    <template v-else>
      <!-- 头部：名称 + 状态 + 操作 -->
      <div class="shrink-0 border-b border-[rgba(15,0,0,0.08)] bg-[#fdfcfc] px-3 py-2">
        <div class="flex items-center gap-2">
          <template v-if="editingName">
            <input
              v-model="nameDraft"
              class="w-[180px] rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-2 py-0.5 text-[13px] outline-none focus:border-[#201d1d]"
              @keydown.enter="commitName"
              @blur="commitName"
            />
          </template>
          <template v-else>
            <span class="max-w-[200px] truncate text-[13px] font-semibold text-[#201d1d]" :title="detail.name">
              {{ detail.name }}
            </span>
            <button
              class="text-[10px] text-[#9a9898] hover:text-[#201d1d]"
              title="重命名"
              @click="((nameDraft = detail.name), (editingName = true))"
            >
              ✎
            </button>
          </template>
          <span
            class="rounded-full px-2 py-0.5 text-[10px]"
            :class="detail.status === 'saved' ? 'bg-[#30d158]/12 text-[#1d8a3e]' : 'bg-[#ff9f0a]/12 text-[#9a6200]'"
          >
            {{ detail.status === 'saved' ? '✓ 落地成果' : '● 工作产出' }}
          </span>
          <div class="ml-auto flex items-center gap-1.5">
            <button
              v-if="detail.status !== 'saved'"
              class="rounded-[4px] border border-[rgba(15,0,0,0.15)] bg-transparent px-2.5 py-1 text-[11px] text-[#424245] hover:text-[#201d1d]"
              title="提升为策略库「落地成果」"
              @click="markSaved"
            >
              设为落地成果
            </button>
            <button
              :disabled="busy"
              class="rounded-[4px] border border-[rgba(15,0,0,0.15)] bg-transparent px-2.5 py-1 text-[11px] text-[#424245] hover:text-[#201d1d] disabled:opacity-50"
              @click="aiOptimize"
            >
              {{ aiRunning ? '优化中…' : '✦ AI 优化' }}
            </button>
            <button
              :disabled="busy"
              class="rounded-[4px] bg-[#201d1d] px-3 py-1 text-[11px] font-medium text-[#fdfcfc] hover:opacity-85 disabled:opacity-50"
              @click="runBacktest"
            >
              {{ btRunning ? '回测中…' : '▶ 运行回测' }}
            </button>
          </div>
        </div>
        <div class="mt-1.5 flex gap-1">
          <button
            v-for="t in TABS"
            :key="t.k"
            class="border-b-2 px-2.5 py-1 text-xs"
            :class="
              tab === t.k
                ? 'border-[#201d1d] font-medium text-[#201d1d]'
                : 'border-transparent text-[#646262] hover:text-[#201d1d]'
            "
            @click="tab = t.k"
          >
            {{ t.l }}
          </button>
        </div>
      </div>

      <!-- 回测参数条 -->
      <div
        class="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-[rgba(15,0,0,0.08)] bg-[#fdfcfc] px-3 py-2 text-[11px] text-[#646262]"
      >
        <span class="font-medium text-[#201d1d]">回测参数</span>
        <span class="rounded-[3px] bg-[#f1eeee] px-1.5 py-0.5 text-[10px]">股票 · 本地日线</span>
        <label class="flex items-center gap-1">
          时间
          <input
            v-model="ws.backtestParams.period_start"
            type="date"
            class="rounded-[3px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-1.5 py-0.5 text-[11px] outline-none"
          />
          →
          <input
            v-model="ws.backtestParams.period_end"
            type="date"
            class="rounded-[3px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-1.5 py-0.5 text-[11px] outline-none"
          />
        </label>
        <label class="flex items-center gap-1">
          初始资金
          <input
            v-model.number="ws.backtestParams.init_balance"
            type="number"
            class="w-[92px] rounded-[3px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-1.5 py-0.5 text-[11px] outline-none"
          />
        </label>
        <label class="flex items-center gap-1">
          手续费
          <input
            v-model.number="ws.backtestParams.commission_rate"
            type="number"
            step="0.0005"
            min="0"
            class="w-[64px] rounded-[3px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-1.5 py-0.5 text-[11px] outline-none"
          />
        </label>
        <label class="flex items-center gap-1">
          滑点
          <input
            v-model.number="ws.backtestParams.slippage"
            type="number"
            step="0.001"
            min="0"
            class="w-[60px] rounded-[3px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-1.5 py-0.5 text-[11px] outline-none"
          />
        </label>
        <span>频率 1d</span>
      </div>

      <div v-if="errorMsg" class="mx-3 mt-2 rounded-[4px] border border-[#ff3b30]/40 bg-[#ff3b30]/8 px-2.5 py-1.5 text-[11px] text-[#c62d23]">
        {{ errorMsg }}
      </div>

      <!-- 代码 Tab -->
      <div v-show="tab === 'code'" class="flex min-h-0 flex-1 flex-col gap-2 p-3">
        <div
          v-if="aiNote"
          class="shrink-0 rounded-[4px] border border-[#007aff]/30 bg-[#007aff]/6 px-2.5 py-1.5 text-[11px] leading-relaxed text-[#0056b3]"
        >
          ✦ {{ aiNote }}
        </div>
        <div class="min-h-[220px] flex-1">
          <CodeEditor v-model="code" language="python" height="100%" :title="`策略代码 · ${detail.name}`" :font-size="12" />
        </div>
        <div class="flex shrink-0 items-center gap-2">
          <button
            :disabled="busy"
            class="rounded-[4px] border border-[rgba(15,0,0,0.15)] bg-transparent px-3 py-1 text-[11px] text-[#424245] hover:text-[#201d1d] disabled:opacity-50"
            @click="saveCode()"
          >
            保存版本
          </button>
          <span class="text-[10px] text-[#9a9898]">
            需定义 generate_signals(prices, **kwargs)；保存即记录一条版本
          </span>
        </div>
      </div>

      <!-- 回测 Tab -->
      <div v-show="tab === 'backtest'" class="min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
        <div class="flex items-center gap-2 text-[11px] text-[#646262]">
          <span class="font-medium text-[#201d1d]">回测结果</span>
          <div class="ml-auto w-[240px]">
            <Select
              :model-value="ws.selectedBacktestRunId"
              :options="historyOptions"
              placeholder="历史回测"
              @update:model-value="(v: string) => v && openRun(v)"
            />
          </div>
        </div>

        <div v-if="!runDetail" class="flex h-40 items-center justify-center text-xs text-[#9a9898]">
          尚未回测 — 点击右上「▶ 运行回测」
        </div>
        <template v-else>
          <StageProgress
            :progress="runDetail.progress"
            :title="`${detail.name} · ${runDetail.status === 'done' ? '回测完成' : runDetail.status === 'error' ? '回测失败' : '回测中'}`"
            :subtitle="`回测 #${runDetail.id.slice(0, 8)}${runDetail.finished_at ? ` · 用时 ${Math.max(1, (runDetail.finished_at || 0) - runDetail.created_at)} 秒` : ''}`"
          />
          <div
            v-if="runDetail.status === 'error'"
            class="rounded-[4px] border border-[#ff3b30]/40 bg-[#ff3b30]/8 px-2.5 py-1.5 text-[11px] text-[#c62d23]"
          >
            {{ runDetail.error }}
          </div>

          <template v-if="runDetail.status === 'done'">
            <div class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] p-3">
              <div class="mb-1.5 text-xs font-semibold text-[#201d1d]">本次生效参数</div>
              <div class="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px]">
                <div v-for="[k, v] in effectiveParams" :key="k" class="flex justify-between">
                  <span class="text-[#9a9898]">{{ k }}</span>
                  <span class="font-mono text-[#201d1d]">{{ v }}</span>
                </div>
              </div>
            </div>

            <div class="grid grid-cols-3 gap-1.5">
              <div
                v-for="[key, label, fmt] in METRICS"
                :key="key"
                class="rounded-[4px] border border-[rgba(15,0,0,0.1)] bg-[#fdfcfc] px-2.5 py-2"
              >
                <div class="text-[10px] text-[#9a9898]">{{ label }}</div>
                <div class="mt-0.5 font-mono text-[13px] font-semibold text-[#201d1d]">
                  {{ metricVal(key, fmt) }}
                </div>
              </div>
            </div>

            <div class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] p-3">
              <div class="mb-2 text-xs font-semibold text-[#201d1d]">净值曲线</div>
              <VChart v-if="equityOption" :option="equityOption" :height="200" />
            </div>

            <div class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] p-3">
              <div class="mb-2 text-xs font-semibold text-[#201d1d]">
                交易明细（共 {{ runDetail.trades.length }} 条）
              </div>
              <div class="max-h-[300px] overflow-auto">
                <table class="w-full min-w-[600px] text-[11px]">
                  <thead>
                    <tr class="sticky top-0 border-b border-[rgba(15,0,0,0.22)] bg-[#fdfcfc] text-left text-[#646262]">
                      <th class="py-1 pr-3 font-medium">时间</th>
                      <th class="py-1 pr-3 font-medium">标的</th>
                      <th class="py-1 pr-3 font-medium">方向</th>
                      <th class="py-1 pr-3 font-medium">价格</th>
                      <th class="py-1 pr-3 font-medium">数量</th>
                      <th class="py-1 pr-3 font-medium">手续费</th>
                      <th class="py-1 font-medium">备注</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(t, i) in runDetail.trades" :key="i" class="border-b border-[rgba(15,0,0,0.06)]">
                      <td class="py-1 pr-3 font-mono">{{ t.ts }}</td>
                      <td class="py-1 pr-3 font-mono">{{ t.symbol }}</td>
                      <td class="py-1 pr-3 font-medium" :style="{ color: t.side === '买入' ? '#ff3b30' : '#30d158' }">
                        {{ t.side }}
                      </td>
                      <td class="py-1 pr-3 font-mono">{{ t.price }}</td>
                      <td class="py-1 pr-3 font-mono">{{ t.qty }}</td>
                      <td class="py-1 pr-3 font-mono">{{ t.fee }}</td>
                      <td class="py-1 text-[#9a9898]">{{ t.reason }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </template>
        </template>
      </div>

      <!-- 日志 Tab -->
      <div v-show="tab === 'logs'" class="min-h-0 flex-1 space-y-1 overflow-y-auto p-3">
        <div v-if="!logLines.length" class="flex h-40 items-center justify-center text-xs text-[#9a9898]">
          暂无日志 — 运行回测后查看
        </div>
        <template v-else>
          <div class="mb-1 text-[11px] text-[#646262]">
            策略日志 · 回测 #{{ (runDetail?.id || '').slice(0, 8) }} · 共 {{ logLines.length }} 条
          </div>
          <div
            v-for="(l, i) in logLines"
            :key="i"
            class="rounded-[3px] px-2 py-0.5 font-mono text-[11px]"
            :class="l.includes('[ERROR]') ? 'bg-[#ff3b30]/8 text-[#c62d23]' : l.includes('[WARN]') ? 'text-[#9a6200]' : 'text-[#424245]'"
          >
            {{ l }}
          </div>
        </template>
      </div>

      <!-- 版本 Tab -->
      <div v-show="tab === 'versions'" class="min-h-0 flex-1 space-y-1.5 overflow-y-auto p-3">
        <div class="text-[11px] text-[#646262]">
          共 {{ versions.length }} 个版本 —— 最新版即当前编辑器内容
        </div>
        <div v-if="!versions.length" class="flex h-40 items-center justify-center text-xs text-[#9a9898]">
          暂无版本记录
        </div>
        <div
          v-for="(v, i) in versions"
          :key="v.id"
          class="rounded-[4px] border border-[rgba(15,0,0,0.1)] bg-[#fdfcfc] px-2.5 py-2"
        >
          <div class="flex items-center gap-2">
            <span class="rounded-[3px] bg-[#201d1d] px-1.5 py-0.5 font-mono text-[10px] text-[#fdfcfc]">
              v{{ versions.length - i }}
            </span>
            <span
              v-if="i === 0"
              class="rounded-full bg-[#30d158]/12 px-1.5 py-0.5 text-[9px] text-[#1d8a3e]"
            >
              最新
            </span>
            <span
              v-else-if="v.note.startsWith('AI')"
              class="rounded-full bg-[#007aff]/10 px-1.5 py-0.5 text-[9px] text-[#0056b3]"
            >
              AI 改
            </span>
            <span
              v-else-if="v.note.includes('回滚')"
              class="rounded-full bg-[#ff9f0a]/12 px-1.5 py-0.5 text-[9px] text-[#9a6200]"
            >
              回滚
            </span>
            <span class="ml-auto shrink-0 text-[10px] text-[#9a9898]">{{ fmtTime(v.created_at) }}</span>
          </div>
          <div class="mt-1 truncate text-[11px] text-[#424245]" :title="v.note">{{ v.note }}</div>
          <div class="mt-1.5 flex gap-1.5">
            <button
              class="rounded-[3px] border border-[rgba(15,0,0,0.12)] bg-transparent px-2 py-0.5 text-[10px] text-[#424245] hover:text-[#201d1d]"
              @click="loadToEditor(v)"
            >
              载入编辑器
            </button>
            <button
              class="rounded-[3px] border border-[rgba(15,0,0,0.12)] bg-transparent px-2 py-0.5 text-[10px] text-[#424245] hover:text-[#201d1d]"
              @click="rollback(v)"
            >
              回滚到此版
            </button>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
