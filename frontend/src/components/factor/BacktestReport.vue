<script setup lang="ts">
import { computed } from 'vue'
import { VChart } from '@/components/ui'
import type { BacktestReport } from './types'

/**
 * 回测综合报告 — 与因子分析综合报告同构同源
 * 净值vs基准曲线 · 回撤曲线 · 月度收益热力图 · 指标卡 · 前5大回撤区间 · 假设提示
 */
const props = defineProps<{
  report: BacktestReport | null
  factorName: string | null
  loading?: boolean
}>()

const AXIS_LABEL = { fontSize: 10, color: '#646262' }
const SPLIT_LINE = { lineStyle: { color: 'rgba(15,0,0,0.06)' } }
const CARD = 'rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] p-3'

// —— 指标卡（红涨绿跌，回撤恒红，百分比/数值格式） ————————————————
const PCT_KEYS = new Set([
  'total_return', 'annual_return', 'volatility', 'max_drawdown',
  'var_95', 'cvar_95', 'win_rate',
])
const METRIC_META: [string, string][] = [
  ['total_return', '累计收益'],
  ['annual_return', '年化收益'],
  ['volatility', '年化波动'],
  ['sharpe_ratio', '夏普比率'],
  ['sortino_ratio', '索提诺'],
  ['calmar_ratio', '卡玛比率'],
  ['max_drawdown', '最大回撤'],
  ['var_95', 'VaR(95%)'],
  ['cvar_95', 'CVaR(95%)'],
  ['win_rate', '胜率'],
  ['profit_loss_ratio', '盈亏比'],
  ['trading_days', '交易日数'],
]
function fmtVal(key: string, v: number): string {
  if (typeof v !== 'number' || Number.isNaN(v)) return '-'
  if (key === 'trading_days') return String(Math.round(v))
  if (PCT_KEYS.has(key)) return `${(v * 100).toFixed(2)}%`
  return v.toFixed(3)
}
function metricColor(key: string, v: number): string {
  if (key === 'max_drawdown' || key === 'var_95' || key === 'cvar_95') return '#ff3b30'
  if (['total_return', 'annual_return', 'sharpe_ratio', 'sortino_ratio', 'calmar_ratio'].includes(key)) {
    return v > 0 ? '#ff453a' : v < 0 ? '#30d158' : '#201d1d' // 红涨绿跌
  }
  return '#201d1d'
}
const metricCards = computed(() => {
  const s = props.report?.summary || {}
  return METRIC_META.filter(([k]) => k in s).map(([k, label]) => ({
    key: k,
    label,
    value: fmtVal(k, s[k] as number),
    color: metricColor(k, s[k] as number),
  }))
})

function sortedDates(maps: Record<string, Record<string, number>>): string[] {
  const dates = new Set<string>()
  Object.values(maps).forEach((m) => Object.keys(m).forEach((d) => dates.add(d)))
  return [...dates].sort()
}

// —— 净值 vs 基准曲线 ——————————————————————————————————————
const navOption = computed(() => {
  const r = props.report
  if (!r) return null
  const series: Record<string, Record<string, number>> = { 策略净值: r.nav_curve }
  const keys = ['策略净值']
  if (r.benchmark_curve && Object.keys(r.benchmark_curve).length) {
    series['基准'] = r.benchmark_curve
    keys.push('基准')
  }
  const dates = sortedDates(series)
  const colors: Record<string, string> = { 策略净值: '#ff3b30', 基准: '#8e8e93' }
  return {
    grid: { left: 48, right: 12, top: 24, bottom: 24 },
    legend: { top: 0, textStyle: { fontSize: 10, color: '#646262' } },
    tooltip: { trigger: 'axis', valueFormatter: (v: number) => Number(v).toFixed(3) },
    xAxis: { type: 'category', data: dates, axisLabel: AXIS_LABEL, axisLine: { lineStyle: { color: '#d8d4d4' } } },
    yAxis: { type: 'value', scale: true, axisLabel: { ...AXIS_LABEL, formatter: (v: number) => v.toFixed(2) }, splitLine: SPLIT_LINE },
    series: keys.map((k) => ({
      name: k, type: 'line', showSymbol: false, connectNulls: true,
      data: dates.map((d) => series[k]?.[d] ?? null),
      lineStyle: { width: 1.4, color: colors[k] }, itemStyle: { color: colors[k] },
    })),
  }
})

// —— 回撤曲线（面积） ——————————————————————————————————————
const drawdownOption = computed(() => {
  const r = props.report
  if (!r) return null
  const dates = Object.keys(r.drawdown_curve).sort()
  return {
    grid: { left: 48, right: 12, top: 16, bottom: 24 },
    tooltip: { trigger: 'axis', valueFormatter: (v: number) => `${(Number(v) * 100).toFixed(2)}%` },
    xAxis: { type: 'category', data: dates, axisLabel: AXIS_LABEL, axisLine: { lineStyle: { color: '#d8d4d4' } } },
    yAxis: { type: 'value', axisLabel: { ...AXIS_LABEL, formatter: (v: number) => `${(v * 100).toFixed(0)}%` }, splitLine: SPLIT_LINE },
    series: [{
      name: '回撤', type: 'line', showSymbol: false,
      data: dates.map((d) => r.drawdown_curve[d]),
      lineStyle: { width: 1, color: '#ff3b30' },
      areaStyle: { color: 'rgba(255,59,48,0.14)' },
    }],
  }
})

// —— 月度收益热力图 ——————————————————————————————————————
const monthlyOption = computed(() => {
  const r = props.report
  if (!r || !Object.keys(r.monthly_returns).length) return null
  const years = Object.keys(r.monthly_returns).sort()
  const months = ['01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12']
  const data: [number, number, number][] = []
  let maxAbs = 0.0001
  years.forEach((y, yi) => {
    months.forEach((m, mi) => {
      const v = r.monthly_returns[y]?.[m]
      if (typeof v === 'number') {
        data.push([mi, yi, v])
        maxAbs = Math.max(maxAbs, Math.abs(v))
      }
    })
  })
  return {
    grid: { left: 48, right: 12, top: 16, bottom: 40 },
    tooltip: {
      position: 'top',
      formatter: (p: { data: [number, number, number] }) =>
        `${years[p.data[1]]}-${months[p.data[0]]}: ${(p.data[2] * 100).toFixed(2)}%`,
    },
    xAxis: { type: 'category', data: months.map((m) => `${parseInt(m, 10)}月`), splitArea: { show: true }, axisLabel: AXIS_LABEL },
    yAxis: { type: 'category', data: years, splitArea: { show: true }, axisLabel: AXIS_LABEL },
    visualMap: {
      min: -maxAbs, max: maxAbs, calculable: false, show: false,
      inRange: { color: ['#30d158', '#f5f5f5', '#ff3b30'] }, // 绿跌→白→红涨
    },
    series: [{
      type: 'heatmap', data,
      label: { show: true, fontSize: 9, formatter: (p: { data: [number, number, number] }) => `${(p.data[2] * 100).toFixed(1)}` },
      itemStyle: { borderColor: '#fff', borderWidth: 1 },
    }],
  }
})

function fmtPct(v: number | undefined): string {
  return typeof v === 'number' ? `${(v * 100).toFixed(2)}%` : '-'
}
</script>

<template>
  <div v-if="loading" class="flex items-center justify-center py-16 text-sm text-[#9a9898]">
    正在加载回测报告...
  </div>
  <div v-else-if="!report" class="flex items-center justify-center py-16 text-sm text-[#9a9898]">
    暂无回测报告 — 请先运行含「回测」节点的工作流
  </div>
  <div v-else class="space-y-4">
    <!-- 假设提示条（数据缺失时明示，绝不静默） -->
    <div
      v-if="report.assumptions && report.assumptions.length"
      class="rounded-[4px] border border-[#ff9f0a]/50 bg-[#ff9f0a]/10 px-3 py-2 text-xs text-[#8a5a00]"
    >
      <div class="mb-1 font-medium">回测假设（未处理项，结果解读需注意）</div>
      <ul class="space-y-0.5">
        <li v-for="(a, i) in report.assumptions" :key="i" class="flex items-start gap-1">
          <span class="mt-0.5">•</span><span>{{ a }}</span>
        </li>
      </ul>
    </div>

    <!-- 指标卡 -->
    <div class="grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-6">
      <div v-for="m in metricCards" :key="m.key" :class="CARD">
        <div class="text-[11px] text-[#646262]">{{ m.label }}</div>
        <div class="mt-1 font-mono text-sm font-semibold" :style="{ color: m.color }">{{ m.value }}</div>
      </div>
    </div>

    <!-- 净值 vs 基准 -->
    <div :class="CARD">
      <div class="mb-1 text-xs font-medium text-[#201d1d]">净值曲线（策略 vs 基准）</div>
      <VChart v-if="navOption" :option="navOption" style="height: 260px" autoresize />
    </div>

    <!-- 回撤曲线 -->
    <div :class="CARD">
      <div class="mb-1 text-xs font-medium text-[#201d1d]">回撤曲线</div>
      <VChart v-if="drawdownOption" :option="drawdownOption" style="height: 180px" autoresize />
    </div>

    <!-- 月度收益热力图 -->
    <div v-if="monthlyOption" :class="CARD">
      <div class="mb-1 text-xs font-medium text-[#201d1d]">月度收益热力图</div>
      <VChart :option="monthlyOption" style="height: 240px" autoresize />
    </div>

    <!-- 相对基准指标 -->
    <div v-if="report.benchmark" :class="CARD">
      <div class="mb-2 text-xs font-medium text-[#201d1d]">相对基准</div>
      <div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <div><span class="text-[11px] text-[#646262]">基准累计收益</span><div class="font-mono text-sm">{{ fmtPct(report.benchmark.total_return) }}</div></div>
        <div><span class="text-[11px] text-[#646262]">基准年化</span><div class="font-mono text-sm">{{ fmtPct(report.benchmark.annual_return) }}</div></div>
        <div><span class="text-[11px] text-[#646262]">跟踪误差</span><div class="font-mono text-sm">{{ fmtPct(report.benchmark.tracking_error) }}</div></div>
        <div><span class="text-[11px] text-[#646262]">信息比率</span><div class="font-mono text-sm">{{ report.benchmark.information_ratio?.toFixed(3) ?? '-' }}</div></div>
      </div>
    </div>

    <!-- 前 5 大回撤区间 -->
    <div v-if="report.top_drawdowns && report.top_drawdowns.length" :class="CARD">
      <div class="mb-2 text-xs font-medium text-[#201d1d]">前 5 大回撤区间</div>
      <table class="w-full text-xs">
        <thead>
          <tr class="text-left text-[#646262]">
            <th class="py-1 font-normal">回撤幅度</th>
            <th class="py-1 font-normal">前高日</th>
            <th class="py-1 font-normal">谷底日</th>
            <th class="py-1 font-normal">恢复日</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(d, i) in report.top_drawdowns" :key="i" class="border-t border-[rgba(15,0,0,0.06)]">
            <td class="py-1 font-mono text-[#ff3b30]">{{ fmtPct(d.drawdown) }}</td>
            <td class="py-1 font-mono">{{ d.peak_date || '-' }}</td>
            <td class="py-1 font-mono">{{ d.trough_date || '-' }}</td>
            <td class="py-1 font-mono">{{ d.recovery_date || '未恢复' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
