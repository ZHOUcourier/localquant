<script setup lang="ts">
import { computed, ref } from 'vue'
import { Sparkles } from 'lucide-vue-next'
import { VChart } from '@/components/ui'
import type { FactorReport } from './types'

const props = defineProps<{
  report: FactorReport | null
  factorName: string | null
  loading?: boolean
}>()

const LINE_COLORS = ['#ff3b30', '#ff9f0a', '#ffd60a', '#30d158', '#007aff', '#64d2ff', '#bf5af2', '#a2845e']
const AXIS_LABEL = { fontSize: 10, color: '#646262' }
const SPLIT_LINE = { lineStyle: { color: 'rgba(15,0,0,0.06)' } }

// —— 数据卡：指标标签、顺序、格式 ——————————————————————————
const PCT_KEYS = new Set(['factor_return', 'annual_return', 'max_drawdown', 'p_ic_lt_neg', 'p_ic_gt_pos'])
const METRIC_META: [string, string][] = [
  ['factor_return', '因子收益'],
  ['annual_return', '年化收益'],
  ['sharpe_ratio', '夏普比率'],
  ['max_drawdown', '最大回撤'],
  ['ic_mean', 'IC 均值'],
  ['rank_ic', 'Rank_IC'],
  ['ic_std', 'IC 标准差'],
  ['ic_ir', 'IC_IR'],
  ['ir', 'IR'],
  ['p_ic_lt_neg', 'P(IC<-0.02)'],
  ['p_ic_gt_pos', 'P(IC>0.02)'],
  ['t_stat', 't  统计量'],
  ['p_value', 'p-value'],
  ['monotonicity', '单调性'],
]
function fmtVal(key: string, v: number): string {
  if (typeof v !== 'number' || Number.isNaN(v)) return '-'
  if (PCT_KEYS.has(key)) return `${(v * 100).toFixed(2)}%`
  return v.toFixed(4)
}
function metricColor(key: string, v: number): string {
  if (key === 'max_drawdown') return '#ff3b30'
  if (['factor_return', 'annual_return', 'sharpe_ratio', 'ic_mean', 'rank_ic', 'ic_ir', 'ir'].includes(key)) {
    return v > 0 ? '#ff453a' : v < 0 ? '#30d158' : '#201d1d' // 红涨绿跌
  }
  return '#201d1d'
}

const PERF_COLS: [string, string, boolean][] = [
  ['group', '分组', false],
  ['annualizedReturn', '年化收益率', true],
  ['excessAnnualized', '超额年化', true],
  ['maxDrawdown', '最大回撤', true],
  ['excessMaxDrawdown', '超额最大回撤', true],
  ['annualizedVolatility', '年化波动', true],
  ['excessAnnualizedVolatility', '超额年化波动', true],
  ['turnoverRate', '换手率', true],
  ['monthlyWinRate', '月度胜率', true],
  ['excessMonthlyWinRate', '超额月度胜率', true],
  ['trackingError', '跟踪误差', false],
  ['sharpeRatio', '夏普比率', false],
  ['informationRatio', '信息比率', false],
]

/** {列: {date: v}} → 按日期升序排列 [date, ...] */
function sortedDates(maps: Record<string, Record<string, number>>): string[] {
  const dates = new Set<string>()
  Object.values(maps).forEach((m) => Object.keys(m).forEach((d) => dates.add(d)))
  return [...dates].sort()
}

const CARD = 'rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] p-3'

const aiText = ref<string | null>(null)
const aiLoading = ref(false)
const aiError = ref<string | null>(null)

/** 多线时间序列图 option（百分比 / 数值 两种 y 轴格式） */
function multiLineOption(
  maps: Record<string, Record<string, number>>,
  keys: string[],
  asPct: boolean,
  zeroLine = false,
) {
  const dates = sortedDates(maps)
  return {
    grid: { left: 44, right: 12, top: 24, bottom: 24 },
    legend: { top: 0, textStyle: { fontSize: 10, color: '#646262' } },
    tooltip: {
      trigger: 'axis',
      valueFormatter: (v: number) => (asPct ? `${(Number(v) * 100).toFixed(2)}%` : Number(v).toFixed(4)),
    },
    xAxis: { type: 'category', data: dates, axisLabel: { ...AXIS_LABEL }, axisLine: { lineStyle: { color: '#d8d4d4' } } },
    yAxis: {
      type: 'value',
      scale: true,
      axisLabel: { ...AXIS_LABEL, formatter: asPct ? (v: number) => `${(v * 100).toFixed(0)}%` : (v: number) => v.toFixed(1) },
      splitLine: SPLIT_LINE,
    },
    series: keys.map((k, i) => ({
      name: k,
      type: 'line',
      showSymbol: false,
      connectNulls: true,
      data: dates.map((d) => maps[k]?.[d] ?? null),
      lineStyle: { width: 1.4, color: LINE_COLORS[i % LINE_COLORS.length] },
      itemStyle: { color: LINE_COLORS[i % LINE_COLORS.length] },
      ...(zeroLine && i === 0
        ? { markLine: { symbol: 'none', silent: true, data: [{ yAxis: 0, lineStyle: { color: '#c8c4c4' } }] } }
        : {}),
    })),
  }
}

const groupKeys = computed(() => (props.report ? Object.keys(props.report.group_cumulative) : []))
const groupCumOption = computed(() =>
  props.report ? multiLineOption(props.report.group_cumulative, groupKeys.value, true) : null,
)
const groupExcessOption = computed(() =>
  props.report ? multiLineOption(props.report.group_excess_cumulative, groupKeys.value, true) : null,
)
const icTsOption = computed(() =>
  props.report
    ? multiLineOption({ IC: props.report.ic.series, Rank_IC: props.report.rank_ic.series }, ['IC', 'Rank_IC'], false, true)
    : null,
)
const icCumOption = computed(() =>
  props.report
    ? multiLineOption({ IC: props.report.ic.cumulative, Rank_IC: props.report.rank_ic.cumulative }, ['IC', 'Rank_IC'], false, true)
    : null,
)

/** IC/Rank_IC 分组柱（衰减/自相关） */
function groupedBarOption(
  icArr: { x: number; v: number }[],
  rankArr: { x: number; v: number }[],
  xLabel: string,
) {
  const xs = Array.from(new Set([...icArr.map((d) => d.x), ...rankArr.map((d) => d.x)])).sort((a, b) => a - b)
  const icMap = new Map(icArr.map((d) => [d.x, d.v]))
  const rankMap = new Map(rankArr.map((d) => [d.x, d.v]))
  return {
    grid: { left: 44, right: 12, top: 24, bottom: 28 },
    legend: { top: 0, textStyle: { fontSize: 10, color: '#646262' } },
    tooltip: { trigger: 'axis', valueFormatter: (v: number) => Number(v).toFixed(4) },
    xAxis: { type: 'category', data: xs, name: xLabel, axisLabel: AXIS_LABEL },
    yAxis: { type: 'value', axisLabel: { ...AXIS_LABEL, formatter: (v: number) => v.toFixed(2) }, splitLine: SPLIT_LINE },
    series: [
      { name: 'IC', type: 'bar', data: xs.map((x) => icMap.get(x) ?? null), itemStyle: { color: '#007aff', borderRadius: [2, 2, 0, 0] } },
      { name: 'Rank_IC', type: 'bar', data: xs.map((x) => rankMap.get(x) ?? null), itemStyle: { color: '#ff9f0a', borderRadius: [2, 2, 0, 0] } },
    ],
  }
}

const decayOption = computed(() => {
  const r = props.report
  if (!r) return null
  return groupedBarOption(
    r.ic.decay.map((d) => ({ x: d.period, v: d.ic })),
    r.rank_ic.decay.map((d) => ({ x: d.period, v: d.ic })),
    '持有期',
  )
})
const acOption = computed(() => {
  const r = props.report
  if (!r) return null
  return groupedBarOption(
    r.ic.autocorr.map((d) => ({ x: d.lag, v: d.acf })),
    r.rank_ic.autocorr.map((d) => ({ x: d.lag, v: d.acf })),
    '滞后阶数',
  )
})

/** 分布直方图 option */
function distOption(centers: number[], counts: number[], color: string) {
  return {
    grid: { left: 40, right: 12, top: 12, bottom: 24 },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: centers.map((c) => c.toFixed(3)), axisLabel: AXIS_LABEL },
    yAxis: { type: 'value', axisLabel: AXIS_LABEL, splitLine: SPLIT_LINE, minInterval: 1 },
    series: [
      {
        type: 'bar',
        data: centers.map((c, i) => ({
          value: counts[i],
          itemStyle: { color: c >= 0 ? color : '#c8c4c4', borderRadius: [2, 2, 0, 0] },
        })),
      },
    ],
  }
}

const dd = computed(() => props.report?.ic.distribution)
const rdd = computed(() => props.report?.rank_ic.distribution)
const icDistOption = computed(() => (dd.value ? distOption(dd.value.centers, dd.value.counts, '#007aff') : null))
const rankDistOption = computed(() => (rdd.value ? distOption(rdd.value.centers, rdd.value.counts, '#ff9f0a') : null))

function perfCell(row: Record<string, number | string>, key: string, pct: boolean): string {
  const v = row[key]
  if (v == null) return '-'
  if (typeof v === 'number') return pct ? `${(v * 100).toFixed(2)}%` : v.toFixed(4)
  return String(v)
}

async function handleAI() {
  const r = props.report
  if (!r) return
  aiLoading.value = true
  aiError.value = null
  try {
    const labeled: Record<string, string> = {}
    for (const [k, label] of METRIC_META) labeled[label] = fmtVal(k, r.summary[k])
    const res = await fetch('/api/ai/factor-report', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ factor_name: props.factorName, summary: labeled, group_perf: r.group_perf }),
    })
    if (!res.ok) {
      const e = await res.json().catch(() => null)
      throw new Error(e?.detail || `HTTP ${res.status}`)
    }
    const data = await res.json()
    aiText.value = data.analysis || ''
  } catch (e) {
    aiError.value = e instanceof Error ? e.message : String(e)
  } finally {
    aiLoading.value = false
  }
}
</script>

<template>
  <div v-if="loading" class="flex h-40 items-center justify-center text-xs text-[#646262]">
    综合报告计算中...
  </div>
  <div v-else-if="!report" class="flex h-40 items-center justify-center text-xs text-[#646262]">
    暂无综合报告 — 请先在左上构建并计算因子
  </div>
  <div v-else class="space-y-4">
    <!-- 顶部：标题 + AI 分析按钮 -->
    <div class="flex items-center justify-between">
      <span class="text-sm font-semibold text-[#201d1d]">综合报告{{ factorName ? ` — ${factorName}` : '' }}</span>
      <button
        :disabled="aiLoading"
        class="flex items-center gap-1.5 rounded-[4px] border border-[#007aff] bg-[#007aff]/10 px-3 py-1 text-xs font-medium text-[#007aff] transition-colors hover:bg-[#007aff]/20 disabled:opacity-50"
        @click="handleAI"
      >
        <Sparkles :size="13" />
        {{ aiLoading ? 'AI 分析中...' : 'AI 综合分析' }}
      </button>
    </div>

    <!-- AI 分析结果 -->
    <div v-if="aiError" class="rounded-[4px] border border-[#ff3b30] bg-[#ff3b30]/10 px-3 py-2 text-xs text-[#ff3b30]">
      {{ aiError }}
    </div>
    <div
      v-if="aiText"
      class="max-h-[360px] overflow-auto whitespace-pre-wrap rounded-[4px] border border-[#007aff]/30 bg-[#007aff]/5 px-3 py-2.5 text-xs leading-relaxed text-[#424245]"
    >
      {{ aiText }}
    </div>

    <!-- 数据卡 -->
    <div class="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
      <div
        v-for="[key, label] in METRIC_META"
        :key="key"
        class="rounded-[4px] border border-[rgba(15,0,0,0.1)] bg-[#fdfcfc] px-2.5 py-2"
      >
        <div class="text-[10px] text-[#9a9898]">{{ label }}</div>
        <div class="mt-0.5 font-mono text-sm font-semibold" :style="{ color: metricColor(key, report.summary[key]) }">
          {{ fmtVal(key, report.summary[key]) }}
        </div>
      </div>
    </div>

    <!-- 分组绩效表 -->
    <div :class="CARD">
      <div class="mb-2 text-xs font-semibold text-[#201d1d]">分组收益</div>
      <div class="overflow-auto">
        <table class="w-full border-collapse font-mono text-[11px]">
          <thead>
            <tr>
              <th
                v-for="[, label] in PERF_COLS"
                :key="label"
                class="whitespace-nowrap border-b border-[rgba(15,0,0,0.12)] bg-[#f1eeee] px-2 py-1 text-left font-medium text-[#646262]"
              >
                {{ label }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, ri) in report.group_perf" :key="ri">
              <td
                v-for="[key, , pct] in PERF_COLS"
                :key="key"
                class="whitespace-nowrap border-b border-[rgba(15,0,0,0.06)] px-2 py-1 text-[#201d1d]"
              >
                {{ perfCell(row, key, pct) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 分组累计 + 超额累计 -->
    <div class="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <div :class="CARD">
        <div class="mb-2 text-xs font-semibold text-[#201d1d]">各分组累计收益</div>
        <VChart v-if="groupCumOption" :option="groupCumOption" :height="260" />
      </div>
      <div :class="CARD">
        <div class="mb-2 text-xs font-semibold text-[#201d1d]">各分组超额累计收益</div>
        <VChart v-if="groupExcessOption" :option="groupExcessOption" :height="260" />
      </div>
    </div>

    <!-- IC / Rank_IC 时序 + 累计 -->
    <div class="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <div :class="CARD">
        <div class="mb-2 text-xs font-semibold text-[#201d1d]">IC / Rank_IC 时序</div>
        <VChart v-if="icTsOption" :option="icTsOption" :height="240" />
      </div>
      <div :class="CARD">
        <div class="mb-2 text-xs font-semibold text-[#201d1d]">IC / Rank_IC 累计</div>
        <VChart v-if="icCumOption" :option="icCumOption" :height="240" />
      </div>
    </div>

    <!-- 衰减 + 自相关 -->
    <div class="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <div :class="CARD">
        <div class="mb-2 text-xs font-semibold text-[#201d1d]">IC / Rank_IC 衰减</div>
        <VChart v-if="decayOption" :option="decayOption" :height="240" />
      </div>
      <div :class="CARD">
        <div class="mb-2 text-xs font-semibold text-[#201d1d]">IC / Rank_IC 自相关</div>
        <VChart v-if="acOption" :option="acOption" :height="240" />
      </div>
    </div>

    <!-- 分布 -->
    <div class="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <div :class="CARD">
        <div class="mb-2 text-xs font-semibold text-[#201d1d]">
          IC 分布 (skew={{ dd?.skew.toFixed(3) }} kurt={{ dd?.kurt.toFixed(3) }})
        </div>
        <VChart v-if="icDistOption" :option="icDistOption" :height="240" />
      </div>
      <div :class="CARD">
        <div class="mb-2 text-xs font-semibold text-[#201d1d]">
          Rank_IC 分布 (skew={{ rdd?.skew.toFixed(3) }} kurt={{ rdd?.kurt.toFixed(3) }})
        </div>
        <VChart v-if="rankDistOption" :option="rankDistOption" :height="240" />
      </div>
    </div>

    <!-- 最新一期因子值排名 -->
    <div :class="CARD">
      <div class="mb-2 text-xs font-semibold text-[#201d1d]">
        最新数据 — 因子值排名{{ report.latest[0] ? `（${report.latest[0].date}）` : '' }}
      </div>
      <div class="max-h-[280px] overflow-auto">
        <table class="w-full border-collapse font-mono text-[11px]">
          <thead>
            <tr>
              <th
                v-for="h in ['#', '股票代码', '因子值']"
                :key="h"
                class="sticky top-0 border-b border-[rgba(15,0,0,0.12)] bg-[#f1eeee] px-2 py-1 text-left font-medium text-[#646262]"
              >
                {{ h }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(r, i) in report.latest.slice(0, 30)" :key="r.symbol">
              <td class="border-b border-[rgba(15,0,0,0.06)] px-2 py-1 text-[#9a9898]">{{ i + 1 }}</td>
              <td class="border-b border-[rgba(15,0,0,0.06)] px-2 py-1 text-[#201d1d]">{{ r.symbol }}</td>
              <td class="border-b border-[rgba(15,0,0,0.06)] px-2 py-1 text-[#201d1d]">{{ r.factor_value.toFixed(4) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
