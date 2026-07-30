<script setup lang="ts">
import { computed, ref } from 'vue'
import { Button, Input, VChart } from '@/components/ui'

/** 后端 /api/explorer/pair-spread 返回结构 */
interface PairSpreadResult {
  code_a?: string
  code_b?: string
  window?: number
  stats?: Record<string, number>
  ratio?: { x: string[]; y: number[] }
  zscore?: { x: string[]; y: number[] }
  error?: string
}

const AXIS_LABEL = { fontSize: 10, color: '#646262' }
const SPLIT_LINE = { lineStyle: { color: 'rgba(15,0,0,0.06)' } }

/**
 * 配对价差分析：两标的比价 + 对数价差滚动 Z-Score（±2 开平仓参考带），
 * 用于配对交易/相对强弱研究。
 */
const codeA = ref('')
const codeB = ref('')
const windowSize = ref('60')
const startDate = ref('')
const endDate = ref('')
const result = ref<PairSpreadResult | null>(null)
const loading = ref(false)

async function analyze() {
  if (!codeA.value.trim() || !codeB.value.trim()) return
  loading.value = true
  try {
    const res = await fetch('/api/explorer/pair-spread', {
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

const zOption = computed(() => {
  const r = result.value
  if (!r?.zscore) return null
  return {
    grid: { left: 48, right: 16, top: 12, bottom: 30 },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: r.zscore.x,
      axisLabel: { ...AXIS_LABEL, interval: Math.max(1, Math.floor(r.zscore.x.length / 8)) },
    },
    yAxis: { type: 'value', scale: true, axisLabel: AXIS_LABEL, splitLine: SPLIT_LINE },
    series: [
      {
        name: 'Z-Score',
        type: 'line',
        showSymbol: false,
        data: r.zscore.y,
        lineStyle: { color: '#007aff', width: 1.5 },
        itemStyle: { color: '#007aff' },
        markLine: {
          symbol: 'none',
          silent: true,
          lineStyle: { type: 'dashed' },
          data: [
            { yAxis: 2, lineStyle: { color: '#ff3b30' }, label: { formatter: '+2σ', fontSize: 10 } },
            { yAxis: 0, lineStyle: { color: '#9a9898' }, label: { formatter: '0', fontSize: 10 } },
            { yAxis: -2, lineStyle: { color: '#30d158' }, label: { formatter: '-2σ', fontSize: 10 } },
          ],
        },
      },
    ],
  }
})

const ratioOption = computed(() => {
  const r = result.value
  if (!r?.ratio) return null
  return {
    grid: { left: 56, right: 16, top: 12, bottom: 30 },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: r.ratio.x,
      axisLabel: { ...AXIS_LABEL, interval: Math.max(1, Math.floor(r.ratio.x.length / 8)) },
    },
    yAxis: { type: 'value', scale: true, axisLabel: AXIS_LABEL, splitLine: SPLIT_LINE },
    series: [
      {
        type: 'line',
        showSymbol: false,
        data: r.ratio.y,
        lineStyle: { color: '#ff9f0a', width: 1.5 },
        itemStyle: { color: '#ff9f0a' },
      },
    ],
  }
})

function zScoreColor(k: string, v: number): string {
  return k === '当前 Z-Score' && Math.abs(v) > 2 ? '#ff3b30' : '#201d1d'
}
</script>

<template>
  <div class="flex flex-col gap-4">
    <div class="flex flex-wrap items-end gap-3">
      <div class="flex flex-col gap-1">
        <label class="text-xs text-[#646262]">标的 A</label>
        <div class="w-36"><Input v-model="codeA" placeholder="600519.SH" /></div>
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-xs text-[#646262]">标的 B</label>
        <div class="w-36"><Input v-model="codeB" placeholder="000858.SZ" /></div>
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-xs text-[#646262]">Z-Score 窗口</label>
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
      <Button variant="primary" :loading="loading" @click="analyze">价差分析</Button>
    </div>

    <div
      v-if="result?.error"
      class="rounded-[4px] border border-[#ff3b30]/30 bg-[#ff3b30]/10 px-3 py-2 text-sm text-[#ff3b30]"
    >
      {{ result.error }}
    </div>

    <div v-if="result?.stats" class="grid grid-cols-6 gap-3">
      <div
        v-for="[k, v] in Object.entries(result.stats)"
        :key="k"
        class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-3 py-2.5"
      >
        <div class="mb-1 text-[11px] text-[#646262]">{{ k }}</div>
        <div class="font-mono text-base" :style="{ color: zScoreColor(k, v) }">{{ v }}</div>
      </div>
    </div>

    <div v-if="zOption" class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] p-3">
      <div class="mb-2 text-xs text-[#646262]">
        对数价差滚动 Z-Score（窗口 {{ result?.window }}）— 突破 ±2σ 为常用配对开仓参考
      </div>
      <VChart :option="zOption" :height="280" />
    </div>

    <div v-if="ratioOption" class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] p-3">
      <div class="mb-2 text-xs text-[#646262]">比价序列 {{ result?.code_a }} / {{ result?.code_b }}</div>
      <VChart :option="ratioOption" :height="220" />
    </div>
  </div>
</template>
