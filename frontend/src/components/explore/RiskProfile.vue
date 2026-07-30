<script setup lang="ts">
import { computed, ref } from 'vue'
import { Button, Input, VChart } from '@/components/ui'

interface RiskProfileResult {
  metrics?: Record<string, number | null>
  equity?: { x: string[]; y: number[] }
  drawdown?: { x: string[]; y: number[] }
  return_hist?: { bin: string; count: number }[]
  error?: string
}

const AXIS_LABEL = { fontSize: 10, color: '#646262' }
const SPLIT_LINE = { lineStyle: { color: 'rgba(15,0,0,0.06)' } }

/** 指标值着色：收益/夏普类正绿负红，回撤/VaR 类恒红 */
function metricColor(key: string, v: number | null): string {
  if (v == null) return '#9a9898'
  if (/回撤|VaR|CVaR/.test(key)) return '#ff3b30'
  if (/涨跌|收益|夏普|卡玛|胜率/.test(key)) return v >= 0 ? '#30d158' : '#ff3b30'
  return '#201d1d'
}

/**
 * 风险画像：单标的收益/波动/回撤/尾部风险一站式体检 —
 * 指标卡 + 净值曲线 + 回撤水下图 + 日收益分布。
 */
const code = ref('')
const startDate = ref('')
const endDate = ref('')
const result = ref<RiskProfileResult | null>(null)
const loading = ref(false)

async function analyze() {
  if (!code.value.trim()) return
  loading.value = true
  try {
    const res = await fetch('/api/explorer/risk-profile', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        code: code.value.trim(),
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

const equityDrawdownOption = computed(() => {
  const r = result.value
  if (!r?.equity || !r?.drawdown) return null
  return {
    grid: [
      { left: 56, right: 16, top: 12, height: '52%' },
      { left: 56, right: 16, top: '70%', height: '22%' },
    ],
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    tooltip: { trigger: 'axis' },
    xAxis: [
      { type: 'category', gridIndex: 0, data: r.equity.x, axisLabel: { show: false } },
      {
        type: 'category',
        gridIndex: 1,
        data: r.drawdown.x,
        axisLabel: { ...AXIS_LABEL, interval: Math.max(1, Math.floor(r.drawdown.x.length / 8)) },
      },
    ],
    yAxis: [
      { type: 'value', gridIndex: 0, scale: true, axisLabel: AXIS_LABEL, splitLine: SPLIT_LINE },
      { type: 'value', gridIndex: 1, axisLabel: { ...AXIS_LABEL, formatter: '{value}%' }, splitLine: SPLIT_LINE },
    ],
    series: [
      {
        name: '净值',
        type: 'line',
        xAxisIndex: 0,
        yAxisIndex: 0,
        showSymbol: false,
        data: r.equity.y,
        lineStyle: { color: '#007aff', width: 1.5 },
        itemStyle: { color: '#007aff' },
      },
      {
        name: '回撤(%)',
        type: 'line',
        xAxisIndex: 1,
        yAxisIndex: 1,
        showSymbol: false,
        data: r.drawdown.y,
        lineStyle: { color: '#ff3b30', width: 1 },
        itemStyle: { color: '#ff3b30' },
        areaStyle: { color: 'rgba(255,59,48,0.15)' },
      },
    ],
  }
})

const returnHistOption = computed(() => {
  const rh = result.value?.return_hist
  if (!rh) return null
  return {
    grid: { left: 48, right: 16, top: 10, bottom: 24 },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: rh.map((d) => d.bin), axisLabel: AXIS_LABEL },
    yAxis: { type: 'value', axisLabel: AXIS_LABEL, splitLine: SPLIT_LINE },
    series: [
      {
        type: 'bar',
        data: rh.map((d) => ({
          value: d.count,
          itemStyle: { color: parseFloat(d.bin) >= 0 ? '#ff3b30' : '#30d158' },
        })),
      },
    ],
  }
})
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
      <Button variant="primary" :loading="loading" @click="analyze">风险画像</Button>
    </div>

    <div
      v-if="result?.error"
      class="rounded-[4px] border border-[#ff3b30]/30 bg-[#ff3b30]/10 px-3 py-2 text-sm text-[#ff3b30]"
    >
      {{ result.error }}
    </div>

    <div v-if="result?.metrics" class="grid grid-cols-6 gap-3">
      <div
        v-for="[k, v] in Object.entries(result.metrics)"
        :key="k"
        class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-3 py-2.5"
      >
        <div class="mb-1 text-[11px] text-[#646262]">{{ k }}</div>
        <div class="font-mono text-base" :style="{ color: metricColor(k, v) }">
          {{ v == null ? '-' : v }}
        </div>
      </div>
    </div>

    <div
      v-if="equityDrawdownOption"
      class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] p-3"
    >
      <div class="mb-2 text-xs text-[#646262]">净值曲线（区间首日=1）与 回撤水下图</div>
      <VChart :option="equityDrawdownOption" :height="380" />
    </div>

    <div
      v-if="returnHistOption"
      class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] p-3"
    >
      <div class="mb-2 text-xs text-[#646262]">日收益分布（%）</div>
      <VChart :option="returnHistOption" :height="220" />
    </div>
  </div>
</template>
