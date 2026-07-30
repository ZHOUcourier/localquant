<script setup lang="ts">
import { computed, ref } from 'vue'
import { Button, Input, VChart } from '@/components/ui'

/** 后端 /api/explorer/volatility 返回结构 */
interface VolatilityResult {
  code?: string
  annualize?: number
  series?: { name: string; x: string[]; y: number[] }[]
  stats?: Record<string, Record<string, number>>
  histograms?: Record<string, { bin: string; count: number }[]>
  error?: string
}

const HV_COLORS: Record<string, string> = {
  HV5: '#ff3b30',
  HV15: '#bf5af2',
  HV30: '#007aff',
  HV50: '#30d158',
}

const AXIS_LABEL = { fontSize: 10, color: '#646262' }
const SPLIT_LINE = { lineStyle: { color: 'rgba(15,0,0,0.06)' } }
const STAT_ROWS = ['最新', '均值', '中值', '标准差', '百分位', '最高', '最低']

/**
 * 历史波动率（对标券商终端「历史波动率」）：
 * HV5/15/30/50 多窗口时序 + 统计概览表 + 频率分布。
 */
const code = ref('')
const startDate = ref('')
const endDate = ref('')
const annualize = ref('250')
const histKey = ref('HV5')
const result = ref<VolatilityResult | null>(null)
const loading = ref(false)

async function analyze() {
  if (!code.value.trim()) return
  loading.value = true
  try {
    const res = await fetch('/api/explorer/volatility', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        code: code.value.trim(),
        start_date: startDate.value,
        end_date: endDate.value,
        annualize: Number(annualize.value) || 250,
      }),
    })
    result.value = await res.json()
  } catch (err) {
    result.value = { error: String(err) }
  } finally {
    loading.value = false
  }
}

const lineOption = computed(() => {
  const series = result.value?.series
  if (!series?.length) return null
  // 用最长序列的 x 轴作为类目轴
  const base = series.reduce((a, b) => (a.x.length >= b.x.length ? a : b))
  return {
    grid: { left: 52, right: 16, top: 30, bottom: 30 },
    legend: { top: 0, textStyle: { fontSize: 11, color: '#646262' } },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: base.x,
      axisLabel: { ...AXIS_LABEL, interval: Math.max(1, Math.floor(base.x.length / 10)) },
    },
    yAxis: { type: 'value', scale: true, axisLabel: AXIS_LABEL, splitLine: SPLIT_LINE },
    series: series.map((s) => {
      const map = new Map(s.x.map((x, i) => [x, s.y[i]]))
      return {
        name: s.name,
        type: 'line',
        showSymbol: false,
        connectNulls: true,
        data: base.x.map((x) => map.get(x) ?? null),
        lineStyle: { width: 1.5, color: HV_COLORS[s.name] },
        itemStyle: { color: HV_COLORS[s.name] },
      }
    }),
  }
})

const statCols = computed(() => (result.value?.stats ? Object.keys(result.value.stats) : []))
const histData = computed(() => result.value?.histograms?.[histKey.value] ?? [])

const histOption = computed(() => ({
  grid: { left: 60, right: 16, top: 10, bottom: 24 },
  tooltip: { trigger: 'axis' },
  xAxis: { type: 'value', axisLabel: AXIS_LABEL, splitLine: SPLIT_LINE, minInterval: 1 },
  yAxis: { type: 'category', data: histData.value.map((d) => d.bin), axisLabel: AXIS_LABEL },
  series: [{ type: 'bar', data: histData.value.map((d) => d.count), itemStyle: { color: '#ff9f0a' } }],
}))

function statCell(c: string, row: string): string {
  const v = result.value?.stats?.[c]?.[row]
  if (v == null) return '-'
  return row === '百分位' ? `${v}%` : String(v)
}
</script>

<template>
  <div class="flex flex-col gap-4">
    <div class="flex flex-wrap items-end gap-3">
      <div class="flex flex-col gap-1">
        <label class="text-xs text-[#646262]">标的代码</label>
        <div class="w-40"><Input v-model="code" placeholder="600519.SH" /></div>
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-xs text-[#646262]">起始日期</label>
        <div class="w-36"><Input v-model="startDate" type="date" /></div>
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-xs text-[#646262]">结束日期</label>
        <div class="w-36"><Input v-model="endDate" type="date" /></div>
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-xs text-[#646262]">年化系数</label>
        <div class="w-24"><Input v-model="annualize" type="number" /></div>
      </div>
      <Button variant="primary" :loading="loading" @click="analyze">波动率分析</Button>
    </div>

    <div
      v-if="result?.error"
      class="rounded-[4px] border border-[#ff3b30]/30 bg-[#ff3b30]/10 px-3 py-2 text-sm text-[#ff3b30]"
    >
      {{ result.error }}
    </div>

    <div v-if="lineOption" class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] p-3">
      <div class="mb-2 text-xs text-[#646262]">
        历史波动率时序（对数收益滚动标准差 × √{{ result?.annualize }}）
      </div>
      <VChart :option="lineOption" :height="340" />
    </div>

    <div v-if="statCols.length > 0" class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] p-3">
      <div class="mb-2 text-xs text-[#646262]">统计概览</div>
      <table class="w-full border-collapse font-mono text-xs">
        <thead>
          <tr>
            <th class="border-b border-[rgba(15,0,0,0.12)] px-2 py-1.5 text-left text-[#646262]">指标</th>
            <th
              v-for="c in statCols"
              :key="c"
              class="border-b border-[rgba(15,0,0,0.12)] px-2 py-1.5 text-right"
              :style="{ color: HV_COLORS[c] || '#646262' }"
            >
              {{ c }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in STAT_ROWS" :key="row" class="hover:bg-[#f1eeee]">
            <td class="border-b border-[rgba(15,0,0,0.08)] px-2 py-1 text-[#646262]">{{ row }}</td>
            <td
              v-for="c in statCols"
              :key="c"
              class="border-b border-[rgba(15,0,0,0.08)] px-2 py-1 text-right text-[#201d1d]"
            >
              {{ statCell(c, row) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="result?.histograms" class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] p-3">
      <div class="mb-2 flex items-center gap-3">
        <span class="text-xs text-[#646262]">频率分布</span>
        <button
          v-for="k in Object.keys(result.histograms)"
          :key="k"
          class="tb-btn"
          :style="{
            padding: '2px 8px',
            fontSize: '11px',
            borderRadius: '4px',
            cursor: 'pointer',
            border: `1px solid ${histKey === k ? HV_COLORS[k] || '#007aff' : 'rgba(15,0,0,0.12)'}`,
            background: histKey === k ? 'rgba(0,122,255,0.06)' : 'transparent',
            color: histKey === k ? HV_COLORS[k] || '#007aff' : '#646262',
          }"
          @click="histKey = k"
        >
          {{ k }}
        </button>
      </div>
      <VChart :option="histOption" :height="240" />
    </div>
  </div>
</template>
