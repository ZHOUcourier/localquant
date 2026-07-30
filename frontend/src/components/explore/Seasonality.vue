<script setup lang="ts">
import { computed, ref } from 'vue'
import { Button, Input, VChart } from '@/components/ui'

/** 后端 /api/explorer/seasonality 返回结构 */
interface SeasonalityResult {
  code?: string
  years?: number[]
  yearly_series?: { year: number; x: string[]; y: number[] }[]
  monthly_matrix?: ({ year: number } & Record<string, number | null>)[]
  month_stats?: { month: number; avg: number | null; up: number; down: number; count: number }[]
  error?: string
}

const YEAR_COLORS = ['#ff3b30', '#007aff', '#30d158', '#bf5af2', '#ff9f0a', '#64d2ff', '#a2845e', '#ffd60a']
const AXIS_LABEL = { fontSize: 10, color: '#646262' }
const SPLIT_LINE = { lineStyle: { color: 'rgba(15,0,0,0.06)' } }

/** 月度收益值 → 单元格背景色（红涨绿跌，A 股配色） */
function cellBg(v: number | null): string {
  if (v == null) return 'transparent'
  const alpha = Math.min(Math.abs(v) / 15, 0.85)
  return v > 0 ? `rgba(255,59,48,${alpha})` : `rgba(48,209,88,${alpha})`
}

/**
 * 季节图表（对标券商终端「季节图表」）：
 * 分年度归一化走势叠加 + 月度涨跌幅热力矩阵 + 逐月涨跌统计。
 */
const code = ref('')
const years = ref('5')
const result = ref<SeasonalityResult | null>(null)
const loading = ref(false)

async function analyze() {
  if (!code.value.trim()) return
  loading.value = true
  try {
    const res = await fetch('/api/explorer/seasonality', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: code.value.trim(), years: Number(years.value) || 5 }),
    })
    result.value = await res.json()
  } catch (err) {
    result.value = { error: String(err) }
  } finally {
    loading.value = false
  }
}

// 分年叠加曲线：x 轴用 MM-DD 类目全集
const overlayOption = computed(() => {
  const series = result.value?.yearly_series
  if (!series?.length) return null
  const allX = Array.from(new Set(series.flatMap((s) => s.x))).sort()
  return {
    grid: { left: 48, right: 16, top: 30, bottom: 30 },
    legend: { top: 0, textStyle: { fontSize: 11, color: '#646262' } },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: allX,
      axisLabel: { ...AXIS_LABEL, interval: Math.max(1, Math.floor(allX.length / 12)) },
    },
    yAxis: { type: 'value', scale: true, axisLabel: AXIS_LABEL, splitLine: SPLIT_LINE, name: '首日=100' },
    series: series.map((s, i) => {
      const map = new Map(s.x.map((x, idx) => [x, s.y[idx]]))
      return {
        name: String(s.year),
        type: 'line',
        showSymbol: false,
        connectNulls: true,
        data: allX.map((x) => map.get(x) ?? null),
        lineStyle: { width: 1.5, color: YEAR_COLORS[i % YEAR_COLORS.length] },
        itemStyle: { color: YEAR_COLORS[i % YEAR_COLORS.length] },
      }
    }),
  }
})

const monthStatsOption = computed(() => {
  const ms = result.value?.month_stats
  if (!ms) return null
  return {
    grid: { left: 40, right: 16, top: 30, bottom: 24 },
    legend: { top: 0, textStyle: { fontSize: 11, color: '#646262' } },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: ms.map((s) => `${s.month}月`), axisLabel: AXIS_LABEL },
    yAxis: { type: 'value', axisLabel: AXIS_LABEL, splitLine: SPLIT_LINE, minInterval: 1 },
    series: [
      { name: '上涨次数', type: 'bar', data: ms.map((s) => s.up), itemStyle: { color: '#ff3b30' } },
      { name: '下跌次数', type: 'bar', data: ms.map((s) => s.down), itemStyle: { color: '#30d158' } },
    ],
  }
})

const months = Array.from({ length: 12 }, (_, i) => i + 1)
function cellValue(row: Record<string, number | null>, m: number): number | null {
  return (row[`m${m}`] as number | null) ?? null
}
</script>

<template>
  <div class="flex flex-col gap-4">
    <div class="flex items-end gap-3">
      <div class="flex flex-col gap-1">
        <label class="text-xs text-[#646262]">标的代码</label>
        <div class="w-40"><Input v-model="code" placeholder="600519.SH" /></div>
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-xs text-[#646262]">回看年数</label>
        <div class="w-24"><Input v-model="years" type="number" /></div>
      </div>
      <Button variant="primary" :loading="loading" @click="analyze">季节性分析</Button>
    </div>

    <div
      v-if="result?.error"
      class="rounded-[4px] border border-[#ff3b30]/30 bg-[#ff3b30]/10 px-3 py-2 text-sm text-[#ff3b30]"
    >
      {{ result.error }}
    </div>

    <div v-if="overlayOption" class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] p-3">
      <div class="mb-2 text-xs text-[#646262]">分年度走势叠加（每年首个 交易日归一化为 100）</div>
      <VChart :option="overlayOption" :height="340" />
    </div>

    <div
      v-if="result?.monthly_matrix && result.monthly_matrix.length > 0"
      class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] p-3"
    >
      <div class="mb-2 text-xs text-[#646262]">月度涨跌幅矩阵（%）— 红涨绿跌</div>
      <div class="overflow-x-auto">
        <table class="w-full border-collapse font-mono text-xs">
          <thead>
            <tr>
              <th class="border-b border-[rgba(15,0,0,0.12)] px-2 py-1.5 text-left text-[#646262]">年份</th>
              <th
                v-for="m in months"
                :key="m"
                class="border-b border-[rgba(15,0,0,0.12)] px-2 py-1.5 text-right text-[#646262]"
              >
                {{ m }}月
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in result.monthly_matrix" :key="row.year">
              <td class="border-b border-[rgba(15,0,0,0.08)] px-2 py-1 text-[#201d1d]">{{ row.year }}</td>
              <td
                v-for="m in months"
                :key="m"
                class="border-b border-[rgba(15,0,0,0.08)] px-2 py-1 text-right"
                :style="{ background: cellBg(cellValue(row, m)), color: cellValue(row, m) == null ? '#9a9898' : '#201d1d' }"
              >
                {{ cellValue(row, m) == null ? '-' : cellValue(row, m)!.toFixed(2) }}
              </td>
            </tr>
            <tr v-if="result.month_stats">
              <td class="px-2 py-1 font-semibold text-[#201d1d]">均值</td>
              <td
                v-for="s in result.month_stats"
                :key="s.month"
                class="px-2 py-1 text-right font-semibold"
                :style="{ color: s.avg == null ? '#9a9898' : s.avg > 0 ? '#ff3b30' : '#30d158' }"
              >
                {{ s.avg == null ? '-' : s.avg.toFixed(2) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-if="monthStatsOption" class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] p-3">
      <div class="mb-2 text-xs text-[#646262]">逐月上涨/下跌次数（近 {{ result?.years?.length }} 年）</div>
      <VChart :option="monthStatsOption" :height="220" />
    </div>
  </div>
</template>
