<script setup lang="ts">
import { computed, ref } from 'vue'
import { Button, Input, VChart } from '@/components/ui'

/** 后端 /api/explorer/regression 返回结构 */
interface RegressionResult {
  code_y?: string
  code_x?: string
  use_returns?: boolean
  points?: [number, number, string][]
  line?: { x0: number; y0: number; x1: number; y1: number }
  stats?: Record<string, number>
  hist_x?: { bin: string; count: number }[]
  hist_y?: { bin: string; count: number }[]
  error?: string
}

const AXIS_LABEL = { fontSize: 10, color: '#646262' }
const SPLIT_LINE = { lineStyle: { color: 'rgba(15,0,0,0.06)' } }

function histOption(data: { bin: string; count: number }[], color: string) {
  return {
    grid: { left: 40, right: 12, top: 8, bottom: 24 },
    xAxis: { type: 'category', data: data.map((d) => d.bin), axisLabel: AXIS_LABEL },
    yAxis: { type: 'value', axisLabel: AXIS_LABEL, splitLine: SPLIT_LINE },
    tooltip: { trigger: 'axis' },
    series: [{ type: 'bar', data: data.map((d) => d.count), itemStyle: { color } }],
  }
}

/**
 * 回归分析（对标券商终端「回归分析」）：
 * 两标的收盘价/收益率 OLS 回归 — 散点 + 拟合线 + Beta/Alpha/R/R² + 双边缘分布。
 */
const codeY = ref('')
const codeX = ref('')
const startDate = ref('')
const endDate = ref('')
const useReturns = ref(false)
const result = ref<RegressionResult | null>(null)
const loading = ref(false)

async function analyze() {
  if (!codeY.value.trim() || !codeX.value.trim()) return
  loading.value = true
  try {
    const res = await fetch('/api/explorer/regression', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        code_y: codeY.value.trim(),
        code_x: codeX.value.trim(),
        start_date: startDate.value,
        end_date: endDate.value,
        use_returns: useReturns.value,
      }),
    })
    result.value = await res.json()
  } catch (err) {
    result.value = { error: String(err) }
  } finally {
    loading.value = false
  }
}

const scatterOption = computed(() => {
  const r = result.value
  if (!r?.points || !r?.line) return null
  return {
    grid: { left: 60, right: 20, top: 20, bottom: 40 },
    tooltip: {
      trigger: 'item',
      formatter: (p: { value: [number, number, string] }) =>
        `${p.value[2]}<br/>X: ${p.value[0]}<br/>Y: ${p.value[1]}`,
    },
    xAxis: { type: 'value', name: `X: ${r.code_x}`, scale: true, axisLabel: AXIS_LABEL, splitLine: SPLIT_LINE },
    yAxis: { type: 'value', name: `Y: ${r.code_y}`, scale: true, axisLabel: AXIS_LABEL, splitLine: SPLIT_LINE },
    series: [
      { type: 'scatter', symbolSize: 5, data: r.points, itemStyle: { color: 'rgba(0,122,255,0.55)' } },
      {
        type: 'line',
        showSymbol: false,
        data: [
          [r.line.x0, r.line.y0],
          [r.line.x1, r.line.y1],
        ],
        lineStyle: { color: '#ff3b30', width: 2 },
      },
    ],
  }
})

const histXOption = computed(() => (result.value?.hist_x ? histOption(result.value.hist_x, '#007aff') : null))
const histYOption = computed(() => (result.value?.hist_y ? histOption(result.value.hist_y, '#ff3b30') : null))
</script>

<template>
  <div class="flex flex-col gap-4">
    <div class="flex flex-wrap items-end gap-3">
      <div class="flex flex-col gap-1">
        <label class="text-xs text-[#646262]">因变量 Y（代码）</label>
        <div class="w-36"><Input v-model="codeY" placeholder="600519.SH" /></div>
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-xs text-[#646262]">自变量 X（代码）</label>
        <div class="w-36"><Input v-model="codeX" placeholder="000300.SH" /></div>
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-xs text-[#646262]">起始日期</label>
        <div class="w-36"><Input v-model="startDate" type="date" /></div>
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-xs text-[#646262]">结束日期</label>
        <div class="w-36"><Input v-model="endDate" type="date" /></div>
      </div>
      <label class="mb-1.5 flex cursor-pointer items-center gap-1.5 text-xs text-[#646262]">
        <input v-model="useReturns" type="checkbox" />
        按日收益率回归
      </label>
      <Button variant="primary" :loading="loading" @click="analyze">回归分析</Button>
    </div>

    <div
      v-if="result?.error"
      class="rounded-[4px] border border-[#ff3b30]/30 bg-[#ff3b30]/10 px-3 py-2 text-sm text-[#ff3b30]"
    >
      {{ result.error }}
    </div>

    <div v-if="result?.stats" class="grid grid-cols-5 gap-3">
      <div
        v-for="[k, v] in Object.entries(result.stats)"
        :key="k"
        class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-3 py-3"
      >
        <div class="mb-1 text-xs text-[#646262]">{{ k }}</div>
        <div class="font-mono text-lg text-[#201d1d]">{{ v }}</div>
      </div>
    </div>

    <div v-if="scatterOption" class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] p-3">
      <div class="mb-2 text-xs text-[#646262]">
        散点与拟合线 — Y = {{ result?.stats?.Beta }}·X + {{ result?.stats?.Alpha }}
      </div>
      <VChart :option="scatterOption" :height="360" />
    </div>

    <div v-if="histXOption && histYOption" class="grid grid-cols-2 gap-3">
      <div class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] p-3">
        <div class="mb-2 text-xs text-[#646262]">X 分布 — {{ result?.code_x }}</div>
        <VChart :option="histXOption" :height="180" />
      </div>
      <div class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] p-3">
        <div class="mb-2 text-xs text-[#646262]">Y 分布 — {{ result?.code_y }}</div>
        <VChart :option="histYOption" :height="180" />
      </div>
    </div>
  </div>
</template>
