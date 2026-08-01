<script setup lang="ts">
/**
 * FactorBoard — 右侧因子画板（复刻参考站 281）
 *
 * - 头部：因子名（可编辑）+ Tab「代码｜分析结果」+「▶ 跑分析」+「存入因子库」
 * - 代码 Tab：公式/Python 切换 + Monaco
 * - 分析参数条：起止日期/调仓周期/分组数/因子方向
 * - 分析结果 Tab：9 阶段进度 → 生效参数 → 关键指标 → 分组收益表 → 图表网格
 * - 「历史分析」下拉切换往次结果；运行中轮询详情直至 done/error
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Select } from '@/components/ui'
import type { SelectOption } from '@/components/ui'
import CodeEditor from '@/components/ui/CodeEditor.vue'
import VChart from '@/components/ui/VChart.vue'
import StageProgress from './StageProgress.vue'
import type { AnalysisDetail, AnalysisRecord, IcReport, QubeFactor } from './types'
import { fmtNum, fmtPct, fmtTime, jsonFetch } from './types'
import type { SessionWorkspace } from '@/composables/useQubeWorkspace'

const props = defineProps<{
  factorId: string
  sessionId: string
  ws: SessionWorkspace
}>()

const factor = ref<QubeFactor | null>(null)
const analyses = ref<AnalysisRecord[]>([])
const detail = ref<AnalysisDetail | null>(null)
const running = ref(false)
const saving = ref(false)
const savedToLibrary = ref(false)
const errorMsg = ref('')
const editingName = ref(false)
const nameDraft = ref('')
let pollTimer: ReturnType<typeof setInterval> | null = null

const tab = computed({
  get: () => (props.ws.canvasTab === 'analysis' ? 'analysis' : 'code'),
  set: (v: string) => (props.ws.canvasTab = v),
})

// —— 加载 ————————————————————————————————————————————————
async function loadFactor() {
  if (!props.factorId) return
  try {
    factor.value = await jsonFetch(`/api/qube/factors/${props.factorId}`)
    errorMsg.value = ''
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e)
    factor.value = null
  }
}

async function loadAnalyses(selectId?: string) {
  if (!props.factorId) return
  const d = await jsonFetch(`/api/qube/factor-analysis?factor_id=${props.factorId}`)
  analyses.value = d.analyses
  const prefer =
    selectId || props.ws.selectedAnalysisId || analyses.value[0]?.id || ''
  if (prefer && analyses.value.some((a) => a.id === prefer)) {
    await openAnalysis(prefer)
  } else {
    detail.value = null
  }
}

async function openAnalysis(id: string) {
  props.ws.selectedAnalysisId = id
  detail.value = await jsonFetch(`/api/qube/factor-analysis/${id}`)
  if (detail.value?.status === 'running') startPolling(id)
}

function startPolling(id: string) {
  stopPolling()
  running.value = true
  pollTimer = setInterval(async () => {
    try {
      const d: AnalysisDetail = await jsonFetch(`/api/qube/factor-analysis/${id}`)
      detail.value = d
      if (d.status !== 'running') {
        stopPolling()
        loadAnalyses(id)
      }
    } catch {
      stopPolling()
    }
  }, 1500)
}

function stopPolling() {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = null
  running.value = false
}

onBeforeUnmount(stopPolling)

watch(
  () => props.factorId,
  () => {
    stopPolling()
    detail.value = null
    loadFactor()
    loadAnalyses()
  },
  { immediate: true },
)

defineExpose({
  refresh: () => {
    loadFactor()
    loadAnalyses()
  },
  openAnalysis: (id: string) => {
    tab.value = 'analysis'
    openAnalysis(id)
  },
})

// —— 编辑 ————————————————————————————————————————————————
async function saveFactorField(fields: Record<string, string>) {
  if (!factor.value) return
  await jsonFetch(`/api/qube/factors/${factor.value.id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(fields),
  })
}

async function commitName() {
  if (!factor.value) return
  const name = nameDraft.value.trim()
  editingName.value = false
  if (name && name !== factor.value.name) {
    factor.value.name = name
    await saveFactorField({ name })
  }
}

async function switchCodeType(t: 'formula' | 'python') {
  if (!factor.value || factor.value.code_type === t) return
  factor.value.code_type = t
  await saveFactorField({ code_type: t })
}

let codeSaveTimer: ReturnType<typeof setTimeout> | null = null
function onCodeChange(v: string) {
  if (!factor.value) return
  factor.value.code = v
  if (codeSaveTimer) clearTimeout(codeSaveTimer)
  codeSaveTimer = setTimeout(() => saveFactorField({ code: v }), 800)
}

// —— 跑分析 / 存入因子库 ————————————————————————————————————
async function runAnalysis() {
  if (!factor.value || running.value) return
  errorMsg.value = ''
  try {
    const d = await jsonFetch('/api/qube/factor-analysis', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        factor_id: factor.value.id,
        session_id: props.sessionId,
        ...props.ws.analysisParams,
      }),
    })
    tab.value = 'analysis'
    props.ws.selectedAnalysisId = d.id
    detail.value = {
      id: d.id,
      factor_id: factor.value.id,
      status: 'running',
      progress: null as never,
      params: { ...props.ws.analysisParams },
      metrics: {},
      group_return: {},
      charts: {},
      error: '',
      created_at: Math.floor(Date.now() / 1000),
      finished_at: null,
    } as AnalysisDetail
    startPolling(d.id)
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e)
  }
}

async function saveToLibrary() {
  if (!factor.value || saving.value) return
  saving.value = true
  try {
    await jsonFetch(`/api/qube/factors/${factor.value.id}/save-to-library`, { method: 'POST' })
    savedToLibrary.value = true
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e)
  } finally {
    saving.value = false
  }
}

// —— 参数选项 ————————————————————————————————————————————
const CYCLE_OPTS: SelectOption[] = [1, 5, 10, 20].map((v) => ({ value: String(v), label: `${v} 日` }))
const GROUP_OPTS: SelectOption[] = [3, 5, 10].map((v) => ({ value: String(v), label: `${v} 组` }))
const DIR_OPTS: SelectOption[] = [
  { value: '1', label: '正向 (1)' },
  { value: '-1', label: '反向 (-1)' },
]

const historyOptions = computed<SelectOption[]>(() =>
  analyses.value.map((a) => ({
    value: a.id,
    label: `${fmtTime(a.created_at)} · ${a.status === 'done' ? '完成' : a.status === 'error' ? '失败' : '运行中'}`,
  })),
)

// —— 指标 / 表格 ————————————————————————————————————————
const summary = computed(() => detail.value?.metrics?.summary || null)

const METRIC_ITEMS: [string, string, 'pct' | 'num'][] = [
  ['factor_return', '因子收益', 'pct'],
  ['sharpe_ratio', '夏普', 'num'],
  ['annual_return', '年化', 'pct'],
  ['max_drawdown', '最大回撤', 'pct'],
  ['ic_mean', 'IC_mean', 'num'],
  ['rank_ic', 'Rank_IC', 'num'],
  ['ic_std', 'IC_std', 'num'],
  ['ic_ir', 'IC_IR', 'num'],
  ['ir', 'IR', 'num'],
  ['p_ic_lt_neg', 'P(IC<-0.02)', 'pct'],
  ['p_ic_gt_pos', 'P(IC>0.02)', 'pct'],
  ['t_stat', 't 统计量', 'num'],
]

const GROUP_COLS: [string, string, 'pct' | 'num'][] = [
  ['annualizedReturn', '年化', 'pct'],
  ['excessAnnualized', '超额年化', 'pct'],
  ['maxDrawdown', '回撤', 'pct'],
  ['volatility', '波动', 'pct'],
  ['turnoverRate', '换手', 'num'],
  ['sharpeRatio', '夏普', 'num'],
  ['informationRatio', '信息比率', 'num'],
]

const groupPerf = computed(() => detail.value?.group_return?.group_perf || [])

// —— 图表 ————————————————————————————————————————————————
const AXIS = { fontSize: 9, color: '#646262' }
const SPLIT = { lineStyle: { color: 'rgba(15,0,0,0.06)' } }

function seqOption(rep?: IcReport) {
  if (!rep?.series) return null
  const dates = Object.keys(rep.series)
  return {
    grid: { left: 40, right: 36, top: 20, bottom: 20 },
    tooltip: { trigger: 'axis' },
    legend: { show: false },
    xAxis: { type: 'category', data: dates, axisLabel: AXIS },
    yAxis: [
      { type: 'value', axisLabel: AXIS, splitLine: SPLIT },
      { type: 'value', axisLabel: AXIS, splitLine: { show: false } },
    ],
    series: [
      {
        name: 'IC',
        type: 'bar',
        data: dates.map((d) => rep.series[d]),
        itemStyle: {
          color: (p: { value: number }) => (p.value >= 0 ? '#30d158' : '#ff3b30'),
        },
      },
      {
        name: '累计',
        type: 'line',
        yAxisIndex: 1,
        showSymbol: false,
        data: dates.map((d) => rep.cumulative[d]),
        lineStyle: { width: 1.4, color: '#007aff' },
        itemStyle: { color: '#007aff' },
      },
    ],
  }
}

function distOption(rep?: IcReport) {
  if (!rep?.distribution?.centers?.length) return null
  return {
    grid: { left: 40, right: 12, top: 20, bottom: 20 },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: rep.distribution.centers, axisLabel: AXIS },
    yAxis: { type: 'value', axisLabel: AXIS, splitLine: SPLIT },
    series: [
      { type: 'bar', data: rep.distribution.counts, itemStyle: { color: '#007aff' } },
    ],
  }
}

function decayOption(rep?: IcReport) {
  if (!rep?.decay?.length) return null
  return {
    grid: { left: 40, right: 12, top: 20, bottom: 20 },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: rep.decay.map((d) => d.period), axisLabel: AXIS },
    yAxis: { type: 'value', axisLabel: AXIS, splitLine: SPLIT },
    series: [
      {
        type: 'bar',
        data: rep.decay.map((d) => d.ic),
        itemStyle: { color: (p: { value: number }) => (p.value >= 0 ? '#007aff' : '#ff3b30') },
      },
    ],
  }
}

function acfOption(rep?: IcReport) {
  if (!rep?.autocorr?.length) return null
  return {
    grid: { left: 40, right: 12, top: 20, bottom: 20 },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: rep.autocorr.map((d) => d.lag), axisLabel: AXIS },
    yAxis: { type: 'value', axisLabel: AXIS, splitLine: SPLIT },
    series: [
      {
        type: 'line',
        data: rep.autocorr.map((d) => d.acf),
        lineStyle: { width: 1.4, color: '#007aff' },
        itemStyle: { color: '#007aff' },
      },
    ],
  }
}

const GROUP_COLORS = ['#007aff', '#30d158', '#ff9f0a', '#ff3b30', '#64d2ff', '#9a9898', '#201d1d']

function cumOption(curves?: Record<string, Record<string, number>>, extra?: Record<string, number>) {
  if (!curves || !Object.keys(curves).length) return null
  const names = Object.keys(curves)
  const dates = Object.keys(curves[names[0]] || {})
  const series = names.map((n, i) => ({
    name: n,
    type: 'line',
    showSymbol: false,
    data: dates.map((d) => curves[n][d]),
    lineStyle: { width: 1.2, color: GROUP_COLORS[i % GROUP_COLORS.length] },
    itemStyle: { color: GROUP_COLORS[i % GROUP_COLORS.length] },
  }))
  if (extra && Object.keys(extra).length) {
    series.push({
      name: '多空组合',
      type: 'line',
      showSymbol: false,
      data: dates.map((d) => extra[d]),
      lineStyle: { width: 1.6, color: '#201d1d' },
      itemStyle: { color: '#201d1d' },
    } as (typeof series)[0])
  }
  return {
    grid: { left: 44, right: 12, top: 30, bottom: 20 },
    tooltip: { trigger: 'axis' },
    legend: { top: 0, textStyle: { fontSize: 9, color: '#646262' }, itemWidth: 10, itemHeight: 6 },
    xAxis: { type: 'category', data: dates, axisLabel: AXIS },
    yAxis: {
      type: 'value',
      axisLabel: { ...AXIS, formatter: (v: number) => `${(v * 100).toFixed(0)}%` },
      splitLine: SPLIT,
    },
    series,
  }
}

const charts = computed(() => {
  const c = detail.value?.charts
  if (!c || detail.value?.status !== 'done') return []
  return [
    { title: 'IC 序列（含累计）', option: seqOption(c.ic) },
    { title: 'Rank_IC 序列（含累计）', option: seqOption(c.rank_ic) },
    { title: 'IC 分布', option: distOption(c.ic) },
    { title: 'Rank_IC 分布', option: distOption(c.rank_ic) },
    { title: 'IC 衰减', option: decayOption(c.ic) },
    { title: 'Rank_IC 衰减', option: decayOption(c.rank_ic) },
    { title: 'IC 自相关', option: acfOption(c.ic) },
    { title: 'Rank_IC 自相关', option: acfOption(c.rank_ic) },
    { title: '分组累计收益', option: cumOption(c.group_cumulative, c.long_short_cumulative) },
    { title: '分组超额收益', option: cumOption(c.group_excess_cumulative) },
  ].filter((x) => x.option)
})

const effectiveParams = computed(() => {
  const p = detail.value?.params || {}
  return [
    ['市场', '股票'],
    ['分析区间', `${p.period_start || '自动'} → ${p.period_end || '自动'}`],
    ['调仓周期', `${p.adjustment_cycle ?? 5} 日`],
    ['分组数', `${p.group_number ?? 5}`],
    ['因子方向', `${p.factor_direction ?? 1}`],
    ['股票池', '全部本地缓存'],
  ]
})
</script>

<template>
  <div class="flex h-full flex-col overflow-hidden">
    <div v-if="!factor" class="flex flex-1 items-center justify-center text-xs text-[#9a9898]">
      {{ errorMsg || '因子加载中…' }}
    </div>
    <template v-else>
      <!-- 头部：名称 + Tab + 操作 -->
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
            <span class="max-w-[200px] truncate text-[13px] font-semibold text-[#201d1d]" :title="factor.name">
              {{ factor.name }}
            </span>
            <button
              class="text-[10px] text-[#9a9898] hover:text-[#201d1d]"
              title="重命名"
              @click="((nameDraft = factor.name), (editingName = true))"
            >
              ✎
            </button>
          </template>
          <span class="rounded-full bg-[#30d158]/12 px-2 py-0.5 text-[10px] text-[#1d8a3e]">因子</span>
          <div class="ml-auto flex items-center gap-1.5">
            <button
              :disabled="saving || savedToLibrary"
              class="rounded-[4px] border border-[rgba(15,0,0,0.15)] bg-transparent px-2.5 py-1 text-[11px] text-[#424245] hover:text-[#201d1d] disabled:opacity-50"
              @click="saveToLibrary"
            >
              {{ savedToLibrary ? '✓ 已存入因子库' : '存入因子库' }}
            </button>
            <button
              :disabled="running"
              class="rounded-[4px] bg-[#201d1d] px-3 py-1 text-[11px] font-medium text-[#fdfcfc] hover:opacity-85 disabled:opacity-50"
              @click="runAnalysis"
            >
              {{ running ? '分析中…' : '▶ 跑分析' }}
            </button>
          </div>
        </div>
        <!-- Tab 行 -->
        <div class="mt-1.5 flex gap-1">
          <button
            v-for="t in [
              { k: 'code', l: '代码' },
              { k: 'analysis', l: '分析结果' },
            ]"
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

      <!-- 分析参数条 -->
      <div
        class="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-[rgba(15,0,0,0.08)] bg-[#fdfcfc] px-3 py-2 text-[11px] text-[#646262]"
      >
        <span class="font-medium text-[#201d1d]">分析参数</span>
        <span class="rounded-[3px] bg-[#f1eeee] px-1.5 py-0.5 text-[10px]">股票</span>
        <label class="flex items-center gap-1">
          时间
          <input
            v-model="ws.analysisParams.period_start"
            type="date"
            class="rounded-[3px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-1.5 py-0.5 text-[11px] outline-none"
          />
          →
          <input
            v-model="ws.analysisParams.period_end"
            type="date"
            class="rounded-[3px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-1.5 py-0.5 text-[11px] outline-none"
          />
        </label>
        <label class="flex items-center gap-1">
          调仓
          <Select
            :model-value="String(ws.analysisParams.adjustment_cycle)"
            :options="CYCLE_OPTS"
            @update:model-value="(v: string) => (ws.analysisParams.adjustment_cycle = Number(v))"
          />
        </label>
        <label class="flex items-center gap-1">
          分组
          <Select
            :model-value="String(ws.analysisParams.group_number)"
            :options="GROUP_OPTS"
            @update:model-value="(v: string) => (ws.analysisParams.group_number = Number(v))"
          />
        </label>
        <label class="flex items-center gap-1">
          方向
          <Select
            :model-value="String(ws.analysisParams.factor_direction)"
            :options="DIR_OPTS"
            @update:model-value="(v: string) => (ws.analysisParams.factor_direction = Number(v))"
          />
        </label>
      </div>

      <div v-if="errorMsg" class="mx-3 mt-2 rounded-[4px] border border-[#ff3b30]/40 bg-[#ff3b30]/8 px-2.5 py-1.5 text-[11px] text-[#c62d23]">
        {{ errorMsg }}
      </div>

      <!-- 代码 Tab -->
      <div v-show="tab === 'code'" class="flex min-h-0 flex-1 flex-col gap-2 p-3">
        <div class="flex shrink-0 items-center gap-2 text-[11px] text-[#646262]">
          编写方式
          <button
            v-for="t in [
              { k: 'formula', l: '公式' },
              { k: 'python', l: 'Python' },
            ]"
            :key="t.k"
            class="rounded-[4px] px-2.5 py-0.5 text-[11px]"
            :class="
              factor.code_type === t.k
                ? 'bg-[#201d1d] text-[#fdfcfc]'
                : 'bg-[#f1eeee] text-[#646262] hover:text-[#201d1d]'
            "
            @click="switchCodeType(t.k as 'formula' | 'python')"
          >
            {{ t.l }}
          </button>
          <span class="text-[10px] text-[#9a9898]">
            {{ factor.code_type === 'formula' ? '公式表达式，如 close/DELAY(close,20)-1' : '需定义 compute_factor(close, volume) 或 factor_data' }}
          </span>
        </div>
        <div class="min-h-[200px] flex-1">
          <CodeEditor
            :model-value="factor.code"
            :language="factor.code_type === 'python' ? 'python' : 'plaintext'"
            height="100%"
            :title="`因子代码 · ${factor.name}`"
            :font-size="12"
            @update:model-value="onCodeChange"
          />
        </div>
      </div>

      <!-- 分析结果 Tab -->
      <div v-show="tab === 'analysis'" class="min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
        <!-- 历史分析下拉 -->
        <div class="flex items-center gap-2 text-[11px] text-[#646262]">
          <span class="font-medium text-[#201d1d]">分析结果</span>
          <div class="ml-auto w-[240px]">
            <Select
              :model-value="ws.selectedAnalysisId"
              :options="historyOptions"
              placeholder="历史分析"
              @update:model-value="(v: string) => v && openAnalysis(v)"
            />
          </div>
        </div>

        <div v-if="!detail" class="flex h-40 items-center justify-center text-xs text-[#9a9898]">
          尚未分析 — 点击右上「▶ 跑分析」
        </div>
        <template v-else>
          <StageProgress
            :progress="detail.progress"
            :title="`${factor.name} · ${detail.status === 'done' ? '因子分析完成' : detail.status === 'error' ? '因子分析失败' : '因子分析中'}`"
            :subtitle="`分析 #${detail.id.slice(0, 8)}${detail.finished_at ? ` · 用时 ${Math.max(1, (detail.finished_at || 0) - detail.created_at)} 秒` : ''}`"
          />
          <div
            v-if="detail.status === 'error'"
            class="rounded-[4px] border border-[#ff3b30]/40 bg-[#ff3b30]/8 px-2.5 py-1.5 text-[11px] text-[#c62d23]"
          >
            {{ detail.error }}
          </div>

          <template v-if="detail.status === 'done'">
            <!-- 本次生效参数 -->
            <div class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] p-3">
              <div class="mb-1.5 text-xs font-semibold text-[#201d1d]">本次生效参数</div>
              <div class="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px]">
                <div v-for="[k, v] in effectiveParams" :key="k" class="flex justify-between">
                  <span class="text-[#9a9898]">{{ k }}</span>
                  <span class="font-mono text-[#201d1d]">{{ v }}</span>
                </div>
              </div>
            </div>

            <!-- 关键指标 -->
            <div v-if="summary" class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] p-3">
              <div class="mb-1.5 text-xs font-semibold text-[#201d1d]">关键指标</div>
              <div class="grid grid-cols-2 gap-1.5 sm:grid-cols-3">
                <div
                  v-for="[key, label, fmt] in METRIC_ITEMS"
                  :key="key"
                  class="rounded-[4px] bg-[#f8f7f7] px-2 py-1.5"
                >
                  <div class="text-[10px] text-[#9a9898]">{{ label }}</div>
                  <div class="font-mono text-xs font-semibold text-[#201d1d]">
                    {{ fmt === 'pct' ? fmtPct(summary[key]) : fmtNum(summary[key]) }}
                  </div>
                </div>
              </div>
            </div>

            <!-- 分组收益表 -->
            <div v-if="groupPerf.length" class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] p-3">
              <div class="mb-1.5 text-xs font-semibold text-[#201d1d]">分组收益</div>
              <div class="overflow-x-auto">
                <table class="w-full min-w-[520px] text-[11px]">
                  <thead>
                    <tr class="border-b border-[rgba(15,0,0,0.22)] text-left text-[#646262]">
                      <th class="py-1 pr-3 font-medium">分组</th>
                      <th v-for="[k, label] in GROUP_COLS" :key="k" class="py-1 pr-3 font-medium">
                        {{ label }}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="g in groupPerf"
                      :key="String(g.group)"
                      class="border-b border-[rgba(15,0,0,0.06)]"
                    >
                      <td class="py-1 pr-3 font-medium text-[#201d1d]">{{ g.group }}</td>
                      <td v-for="[k, , fmt] in GROUP_COLS" :key="k" class="py-1 pr-3 font-mono">
                        {{ fmt === 'pct' ? fmtPct(g[k] as number) : fmtNum(g[k] as number, 2) }}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <!-- 图表网格 -->
            <div class="grid grid-cols-1 gap-3 lg:grid-cols-2">
              <div
                v-for="c in charts"
                :key="c.title"
                class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] p-2.5"
              >
                <div class="mb-1 text-[11px] font-semibold text-[#201d1d]">{{ c.title }}</div>
                <VChart :option="c.option!" :height="170" />
              </div>
            </div>
          </template>
        </template>
      </div>
    </template>
  </div>
</template>
