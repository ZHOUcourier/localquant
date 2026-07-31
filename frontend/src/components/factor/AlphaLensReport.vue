<script setup lang="ts">
/**
 * AlphaLensReport — AlphaLens 因子分析报告（ECharts 渲染）
 *
 * 数据来自后端 /api/factor/alphalens（调用 alphalens-reloaded 计算），
 * 与自研 ComprehensiveReport 互补：突出「行业分组 IC / 分层收益」「因子加权多空组合」
 * 「分位数换手率 / 因子秩自相关」等 AlphaLens 特有口径。
 */
import { computed } from 'vue'
import { VChart } from '@/components/ui'
import type { AlphaLensReport } from './types'

const props = defineProps<{
  report: AlphaLensReport | null
  factorName: string | null
  loading?: boolean
}>()

const LINE_COLORS = ['#ff3b30', '#ff9f0a', '#ffd60a', '#30d158', '#007aff', '#64d2ff', '#bf5af2', '#a2845e']
const AXIS_LABEL = { fontSize: 10, color: '#646262' }
const SPLIT_LINE = { lineStyle: { color: 'rgba(15,0,0,0.06)' } }
const CARD = 'rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] p-3'

const periods = computed(() => props.report?.periods ?? [])

/** 多序列时间线（{系列名: {date: v}}） */
function multiLine(maps: Record<string, Record<string, number>>, asPct: boolean, zeroLine = false) {
  const keys = Object.keys(maps)
  const dates = new Set<string>()
  keys.forEach((k) => Object.keys(maps[k] || {}).forEach((d) => dates.add(d)))
  const xs = [...dates].sort()
  return {
    grid: { left: 48, right: 12, top: 24, bottom: 24 },
    legend: { top: 0, textStyle: { fontSize: 10, color: '#646262' } },
    tooltip: {
      trigger: 'axis',
      valueFormatter: (v: number) => (asPct ? `${(Number(v) * 100).toFixed(2)}%` : Number(v).toFixed(4)),
    },
    xAxis: { type: 'category', data: xs, axisLabel: AXIS_LABEL, axisLine: { lineStyle: { color: '#d8d4d4' } } },
    yAxis: {
      type: 'value',
      scale: true,
      axisLabel: { ...AXIS_LABEL, formatter: asPct ? (v: number) => `${(v * 100).toFixed(0)}%` : (v: number) => v.toFixed(2) },
      splitLine: SPLIT_LINE,
    },
    series: keys.map((k, i) => ({
      name: k,
      type: 'line',
      showSymbol: false,
      connectNulls: true,
      data: xs.map((d) => maps[k]?.[d] ?? null),
      lineStyle: { width: 1.4, color: LINE_COLORS[i % LINE_COLORS.length] },
      itemStyle: { color: LINE_COLORS[i % LINE_COLORS.length] },
      ...(zeroLine && i === 0
        ? { markLine: { symbol: 'none', silent: true, data: [{ yAxis: 0, lineStyle: { color: '#c8c4c4' } }] } }
        : {}),
    })),
  }
}

/** 分组柱状：x=类目，series=各周期 */
function groupedBar(rows: { cat: string; period: string; v: number }[], asPct: boolean) {
  const cats = [...new Set(rows.map((r) => r.cat))]
  const pers = periods.value
  return {
    grid: { left: 48, right: 12, top: 24, bottom: 28 },
    legend: { top: 0, textStyle: { fontSize: 10, color: '#646262' } },
    tooltip: { trigger: 'axis', valueFormatter: (v: number) => (asPct ? `${(Number(v) * 100).toFixed(2)}%` : Number(v).toFixed(4)) },
    xAxis: { type: 'category', data: cats, axisLabel: AXIS_LABEL },
    yAxis: { type: 'value', axisLabel: { ...AXIS_LABEL, formatter: asPct ? (v: number) => `${(v * 100).toFixed(1)}%` : (v: number) => v.toFixed(2) }, splitLine: SPLIT_LINE },
    series: pers.map((p, i) => ({
      name: p,
      type: 'bar',
      data: cats.map((c) => rows.find((r) => r.cat === c && r.period === p)?.v ?? null),
      itemStyle: { color: LINE_COLORS[i % LINE_COLORS.length], borderRadius: [2, 2, 0, 0] },
    })),
  }
}

// 分层平均收益（x=分位数，series=周期）
const quantileReturnOption = computed(() => {
  const r = props.report
  if (!r) return null
  return groupedBar(
    r.mean_return_by_quantile.map((d) => ({ cat: `Q${d.factor_quantile}`, period: d.period, v: d.mean_return })),
    true,
  )
})

// 行业分组 IC（x=行业，series=周期）
const groupIcOption = computed(() => {
  const r = props.report
  if (!r || !r.has_group) return null
  return groupedBar(r.ic_by_group.map((d) => ({ cat: d.group, period: d.period, v: d.ic_mean })), false)
})

// 因子加权多空组合累计收益（各周期一条线）
const factorWeightedOption = computed(() => {
  const r = props.report
  if (!r) return null
  return multiLine(r.factor_weighted_cumulative, true, true)
})

// IC 时序（各周期）
const icSeriesOption = computed(() => {
  const r = props.report
  if (!r) return null
  return multiLine(r.ic_series, false, true)
})

// 各分位数累计收益（选首个周期展示，多分位一图）
const firstPeriod = computed(() => periods.value[0] ?? '')
const quantileCumOption = computed(() => {
  const r = props.report
  if (!r) return null
  const byQ = r.cumulative_return_by_quantile[firstPeriod.value] || {}
  return multiLine(byQ, true)
})

// 换手率（各周期）
const turnoverOption = computed(() => {
  const r = props.report
  if (!r || !Object.keys(r.quantile_turnover).length) return null
  return multiLine(r.quantile_turnover, false)
})

function fmt(v: number, digits = 4): string {
  return typeof v === 'number' && !Number.isNaN(v) ? v.toFixed(digits) : '-'
}
function icColor(v: number): string {
  return v > 0.02 ? '#ff453a' : v < -0.02 ? '#30d158' : '#201d1d'
}
</script>

<template>
  <div v-if="loading" class="flex h-40 items-center justify-center text-xs text-[#646262]">
    AlphaLens 分析计算中...
  </div>
  <div v-else-if="!report" class="flex h-40 items-center justify-center text-xs text-[#646262]">
    暂无 AlphaLens 报告 — 点击「运行 AlphaLens 分析」
  </div>
  <div v-else class="space-y-4">
    <div class="flex items-center justify-between">
      <span class="text-sm font-semibold text-[#201d1d]">
        AlphaLens 报告{{ factorName ? ` — ${factorName}` : '' }}
      </span>
      <span class="text-[11px] text-[#9a9898]">
        alphalens-reloaded · {{ report.quantiles }} 分位 · {{ report.has_group ? '含行业分组' : '无行业数据' }}
      </span>
    </div>

    <!-- IC 汇总表 -->
    <div :class="CARD">
      <div class="mb-2 text-xs font-semibold text-[#201d1d]">IC 汇总（各持有期）</div>
      <div class="overflow-auto">
        <table class="w-full border-collapse font-mono text-[11px]">
          <thead>
            <tr>
              <th v-for="h in ['周期', 'IC 均值', 'IC 标准差', 'IC_IR', 't 值', 'p 值', '正比例']" :key="h"
                class="whitespace-nowrap border-b border-[rgba(15,0,0,0.12)] bg-[#f1eeee] px-2 py-1 text-left font-medium text-[#646262]">
                {{ h }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in report.ic_summary" :key="row.period">
              <td class="border-b border-[rgba(15,0,0,0.06)] px-2 py-1 text-[#201d1d]">{{ row.period }}</td>
              <td class="border-b border-[rgba(15,0,0,0.06)] px-2 py-1" :style="{ color: icColor(row.ic_mean) }">{{ fmt(row.ic_mean) }}</td>
              <td class="border-b border-[rgba(15,0,0,0.06)] px-2 py-1 text-[#201d1d]">{{ fmt(row.ic_std) }}</td>
              <td class="border-b border-[rgba(15,0,0,0.06)] px-2 py-1 text-[#201d1d]">{{ fmt(row.ic_ir) }}</td>
              <td class="border-b border-[rgba(15,0,0,0.06)] px-2 py-1 text-[#201d1d]">{{ fmt(row.t_stat, 2) }}</td>
              <td class="border-b border-[rgba(15,0,0,0.06)] px-2 py-1 text-[#201d1d]">{{ fmt(row.p_value) }}</td>
              <td class="border-b border-[rgba(15,0,0,0.06)] px-2 py-1 text-[#201d1d]">{{ (row.positive_ratio * 100).toFixed(1) }}%</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 分层平均收益 + 因子加权多空 -->
    <div class="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <div :class="CARD">
        <div class="mb-2 text-xs font-semibold text-[#201d1d]">分层平均收益（按分位数）</div>
        <VChart v-if="quantileReturnOption" :option="quantileReturnOption" :height="240" />
      </div>
      <div :class="CARD">
        <div class="mb-2 text-xs font-semibold text-[#201d1d]">因子加权多空组合累计收益</div>
        <VChart v-if="factorWeightedOption" :option="factorWeightedOption" :height="240" />
      </div>
    </div>

    <!-- 行业分组 IC（有行业数据时）-->
    <div v-if="report.has_group" :class="CARD">
      <div class="mb-2 text-xs font-semibold text-[#201d1d]">行业分组 IC（AlphaLens 核心增量）</div>
      <VChart v-if="groupIcOption" :option="groupIcOption" :height="260" />
    </div>

    <!-- IC 时序 + 各分位数累计 -->
    <div class="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <div :class="CARD">
        <div class="mb-2 text-xs font-semibold text-[#201d1d]">IC 时序</div>
        <VChart v-if="icSeriesOption" :option="icSeriesOption" :height="240" />
      </div>
      <div :class="CARD">
        <div class="mb-2 text-xs font-semibold text-[#201d1d]">各分位数累计收益（{{ firstPeriod }}）</div>
        <VChart v-if="quantileCumOption" :option="quantileCumOption" :height="240" />
      </div>
    </div>

    <!-- 换手率 -->
    <div v-if="turnoverOption" :class="CARD">
      <div class="mb-2 text-xs font-semibold text-[#201d1d]">顶层分位数换手率</div>
      <VChart :option="turnoverOption" :height="220" />
    </div>
  </div>
</template>
