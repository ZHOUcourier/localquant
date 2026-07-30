<script setup lang="ts">
import { computed, ref } from 'vue'
import { Button, Input, Select, VChart } from '@/components/ui'

interface StatsData {
  count: number
  mean: number
  median: number
  stddev: number
  min: number
  max: number
  q25: number
  q75: number
}

interface CrossSectionResult {
  statistics?: {
    columns: string[]
    data: unknown[][]
    row_count: number
  }
  histogram?: { bin: string; count: number }[]
  error?: string
}

const fieldOptions = [
  { value: 'close', label: 'close' },
  { value: 'volume', label: 'volume' },
  { value: 'amount', label: 'amount' },
]

const date = ref('')
const field = ref('close')
const result = ref<CrossSectionResult | null>(null)
const loading = ref(false)

async function analyze() {
  if (!date.value.trim()) return
  loading.value = true
  try {
    const res = await fetch('/api/explorer/cross-section', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date: date.value, field: field.value }),
    })
    result.value = (await res.json()) as CrossSectionResult
  } catch (err) {
    result.value = { error: String(err) }
  } finally {
    loading.value = false
  }
}

// 从查询结果解析统计量
const stats = computed<StatsData | null>(() => {
  const st = result.value?.statistics
  if (!st?.data?.[0]) return null
  const cols = st.columns
  const row = st.data[0]
  const get = (key: string) => {
    const idx = cols.indexOf(key)
    return idx >= 0 ? Number(row[idx]) : 0
  }
  return {
    count: get('count'),
    mean: get('mean'),
    median: get('median'),
    stddev: get('stddev'),
    min: get('min'),
    max: get('max'),
    q25: get('q25'),
    q75: get('q75'),
  }
})

const mainStats = computed(() =>
  stats.value
    ? [
        { label: '均值', value: stats.value.mean },
        { label: '中位数', value: stats.value.median },
        { label: '标准差', value: stats.value.stddev },
        { label: '最大值', value: stats.value.max },
        { label: '最小值', value: stats.value.min },
      ]
    : [],
)
const subStats = computed(() =>
  stats.value
    ? [
        { label: '样本数', value: stats.value.count },
        { label: 'Q25', value: stats.value.q25 },
        { label: 'Q75', value: stats.value.q75 },
      ]
    : [],
)

const histogramData = computed(() => result.value?.histogram ?? [])

// 分布直方图（原 recharts BarChart → ECharts）
const histOption = computed(() => ({
  grid: { left: 48, right: 16, top: 16, bottom: 40 },
  tooltip: {
    trigger: 'axis',
    backgroundColor: '#fdfcfc',
    borderColor: 'rgba(15,0,0,0.12)',
    textStyle: { color: '#201d1d', fontSize: 12 },
  },
  xAxis: {
    type: 'category',
    data: histogramData.value.map((d) => d.bin),
    axisLabel: { color: '#646262', fontSize: 11 },
    axisLine: { lineStyle: { color: '#403b3b' } },
    splitLine: { show: false },
  },
  yAxis: {
    type: 'value',
    axisLabel: { color: '#646262', fontSize: 11 },
    axisLine: { lineStyle: { color: '#403b3b' } },
    splitLine: { lineStyle: { color: 'rgba(64,59,59,0.2)', type: 'dashed' } },
  },
  series: [
    {
      type: 'bar',
      data: histogramData.value.map((d) => d.count),
      itemStyle: { color: '#007aff', borderRadius: [2, 2, 0, 0] },
    },
  ],
}))
</script>

<template>
  <div class="flex flex-col gap-4">
    <div class="flex items-end gap-3">
      <div class="flex flex-col gap-1">
        <label class="text-xs text-[#646262]">日期</label>
        <div class="w-40"><Input v-model="date" placeholder="2024-01-02" /></div>
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-xs text-[#646262]">字段</label>
        <div class="w-32"><Select v-model="field" :options="fieldOptions" /></div>
      </div>
      <Button variant="primary" :loading="loading" @click="analyze">分析</Button>
    </div>

    <div
      v-if="result?.error"
      class="rounded-[4px] border border-[#ff3b30]/30 bg-[#ff3b30]/10 px-3 py-2 text-sm text-[#ff3b30]"
    >
      {{ result.error }}
    </div>

    <div v-if="stats" class="grid grid-cols-5 gap-3">
      <div
        v-for="item in mainStats"
        :key="item.label"
        class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-3 py-3"
      >
        <div class="text-xs text-[#646262] mb-1">{{ item.label }}</div>
        <div class="text-lg font-mono text-[#201d1d]">
          {{ Number.isFinite(item.value) ? item.value.toFixed(4) : '-' }}
        </div>
      </div>
    </div>

    <div v-if="stats" class="grid grid-cols-3 gap-3">
      <div
        v-for="item in subStats"
        :key="item.label"
        class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-3 py-3"
      >
        <div class="text-xs text-[#646262] mb-1">{{ item.label }}</div>
        <div class="text-lg font-mono text-[#201d1d]">
          {{ Number.isFinite(item.value) ? item.value.toFixed(4) : '-' }}
        </div>
      </div>
    </div>

    <div
      v-if="histogramData.length > 0"
      class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] p-4"
    >
      <div class="text-sm text-[#646262] mb-3">分布直方图</div>
      <VChart :option="histOption" :height="300" />
    </div>
  </div>
</template>
