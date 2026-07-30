<script setup lang="ts">
import { computed, ref } from 'vue'
import { Button, Input, VChart } from '@/components/ui'

/** 后端 /api/explorer/rolling-corr 返回结构 */
interface RollingCorrResult {
  code_a?: string
  code_b?: string
  window?: number
  stats?: Record<string, number>
  x?: string[]
  corr?: number[]
  beta?: number[]
  error?: string
}

const AXIS_LABEL = { fontSize: 10, color: '#646262' }
const SPLIT_LINE = { lineStyle: { color: 'rgba(15,0,0,0.06)' } }

/**
 * 滚动相关 / 滚动 Beta：观察个股与基准（或两标的间）关系的时变性，
 * 补充静态回归/相关矩阵无法体现的结构变化。
 */
const codeA = ref('')
const codeB = ref('')
const windowSize = ref('60')
const startDate = ref('')
const endDate = ref('')
const result = ref<RollingCorrResult | null>(null)
const loading = ref(false)

async function analyze() {
  if (!codeA.value.trim() || !codeB.value.trim()) return
  loading.value = true
  try {
    const res = await fetch('/api/explorer/rolling-corr', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        code_a: codeA.value.trim(),
        code_b: codeB.value.trim(),
        window: Number(windowSize.value) || 60,
        start_date: startDate.value,
        end_date: endDate.value,
      }),
    })
    result.value = await res.json()
  } catch (err) {
    result.value = { error: String(err) }
  } finally {
    loading.value = false
  }
}

const chartOption = computed(() => {
  const r = result.value
  if (!r?.x || !r.corr || !r.beta) return null
  return {
    grid: { left: 48, right: 48, top: 30, bottom: 30 },
    legend: { top: 0, textStyle: { fontSize: 11, color: '#646262' } },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: r.x,
      axisLabel: { ...AXIS_LABEL, interval: Math.max(1, Math.floor(r.x.length / 8)) },
    },
    yAxis: [
      { type: 'value', name: '相关', min: -1, max: 1, axisLabel: AXIS_LABEL, splitLine: SPLIT_LINE },
      { type: 'value', name: 'Beta', scale: true, axisLabel: AXIS_LABEL, splitLine: { show: false } },
    ],
    series: [
      {
        name: '滚动相关',
        type: 'line',
        showSymbol: false,
        yAxisIndex: 0,
        data: r.corr,
        lineStyle: { color: '#007aff', width: 1.5 },
        itemStyle: { color: '#007aff' },
      },
      {
        name: '滚动 Beta',
        type: 'line',
        showSymbol: false,
        yAxisIndex: 1,
        data: r.beta,
        lineStyle: { color: '#ff9f0a', width: 1.5 },
        itemStyle: { color: '#ff9f0a' },
      },
    ],
  }
})
</script>

<template>
  <div class="flex flex-col gap-4">
    <div class="flex flex-wrap items-end gap-3">
      <div class="flex flex-col gap-1">
        <label class="text-xs text-[#646262]">标的</label>
        <div class="w-36"><Input v-model="codeA" placeholder="600519.SH" /></div>
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-xs text-[#646262]">基准（指数/标的）</label>
        <div class="w-36"><Input v-model="codeB" placeholder="000300.SH" /></div>
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-xs text-[#646262]">滚动窗口</label>
        <div class="w-24"><Input v-model="windowSize" type="number" /></div>
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-xs text-[#646262]">起始日期</label>
        <div class="w-36"><Input v-model="startDate" type="date" /></div>
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-xs text-[#646262]">结束日期</label>
        <div class="w-36"><Input v-model="endDate" type="date" /></div>
      </div>
      <Button variant="primary" :loading="loading" @click="analyze">滚动分析</Button>
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
        class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-3 py-2.5"
      >
        <div class="mb-1 text-[11px] text-[#646262]">{{ k }}</div>
        <div class="font-mono text-base text-[#201d1d]">{{ v }}</div>
      </div>
    </div>

    <div v-if="chartOption" class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] p-3">
      <div class="mb-2 text-xs text-[#646262]">
        {{ result?.code_a }} 对 {{ result?.code_b }} 的滚动相关（左轴）与滚动 Beta（右轴），窗口
        {{ result?.window }} 日
      </div>
      <VChart :option="chartOption" :height="320" />
    </div>
  </div>
</template>
