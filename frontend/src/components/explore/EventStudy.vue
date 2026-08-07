<script setup lang="ts">
import { computed, ref } from 'vue'
import { Button, VChart } from '@/components/ui'

/** 后端 /api/explorer/event-study 返回结构 */
interface CarPoint {
  mean: number
  t: number
  positive_ratio: number
  n: number
}
interface EventStudyResult {
  ok?: boolean
  error?: string
  event_type?: string
  n_events?: number
  n_detected?: number
  window?: number[]
  car?: Record<string, CarPoint>
  bhar_mean?: number
  bhar_t?: number
  bhar_positive_ratio?: number
  car_end_t?: number
  positive_ratio_end?: number
  note?: string
  n_stocks?: number
  data_start?: string
  data_end?: string
}

const EVENT_TYPES = [
  { value: 'limit_up', label: '一字涨停' },
  { value: 'limit_down', label: '一字跌停' },
  { value: 'volume_spike', label: '放量事件（量>3×20日均量）' },
  { value: 'dividend', label: '除权除息' },
  { value: 'custom', label: '手工事件' },
]

const eventType = ref('limit_up')
const codes = ref('')
const startDate = ref('')
const endDate = ref('')
const before = ref(10)
const after = ref(10)
const minEvents = ref(5)
const manualEvents = ref('')
const loading = ref(false)
const errorMsg = ref('')
const result = ref<EventStudyResult | null>(null)

async function run() {
  loading.value = true
  errorMsg.value = ''
  result.value = null
  try {
    let events: { date: string; code: string }[] = []
    if (eventType.value === 'custom' && manualEvents.value.trim()) {
      events = manualEvents.value
        .split('\n')
        .map((l) => l.trim())
        .filter(Boolean)
        .map((l) => {
          const [date, code] = l.split(/[\s,]+/)
          return { date, code }
        })
    }
    const res = await fetch('/api/explorer/event-study', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        event_type: eventType.value,
        codes: codes.value.trim(),
        start_date: startDate.value,
        end_date: endDate.value,
        window_before: Number(before.value),
        window_after: Number(after.value),
        min_events: Number(minEvents.value),
        events,
      }),
    })
    result.value = await res.json()
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

/** CAR 曲线（事件窗口异常收益累计均值 + 期末 t 值标注） */
const carOption = computed(() => {
  const car = result.value?.car
  if (!car) return {}
  const days = Object.keys(car).sort((a, b) => Number(a) - Number(b))
  return {
    grid: { left: 48, right: 16, top: 30, bottom: 30 },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: days, name: '相对事件日（0=事件日）', nameTextStyle: { fontSize: 10, color: '#646262' } },
    yAxis: { type: 'value', axisLabel: { formatter: (v: number) => (v * 100).toFixed(1) + '%' } },
    series: [
      {
        name: '平均CAR',
        type: 'line',
        smooth: true,
        data: days.map((d) => Number((car[d].mean * 100).toFixed(3))),
        itemStyle: { color: '#007aff' },
        areaStyle: { opacity: 0.08 },
      },
    ],
  }
})

const summaryRows = computed(() => {
  const r = result.value
  if (!r) return []
  const rows: [string, string][] = []
  rows.push(['事件类型', r.event_type ?? ''])
  rows.push(['事件数（去重合并后）', String(r.n_events ?? 0)])
  rows.push(['检测到事件总数', String(r.n_detected ?? 0)])
  rows.push(['BHAR 均值', r.bhar_mean != null ? (r.bhar_mean * 100).toFixed(2) + '%' : '—'])
  rows.push(['BHAR t 值', r.bhar_t != null ? String(r.bhar_t) : '—'])
  rows.push(['BHAR 正值占比', r.bhar_positive_ratio != null ? (r.bhar_positive_ratio * 100).toFixed(1) + '%' : '—'])
  rows.push(['窗口期末 CAR t 值', r.car_end_t != null ? String(r.car_end_t) : '—'])
  rows.push(['窗口期末正值占比', r.positive_ratio_end != null ? (r.positive_ratio_end * 100).toFixed(1) + '%' : '—'])
  return rows
})
</script>

<template>
  <div class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] p-3">
    <div class="flex flex-wrap items-center gap-2">
      <select v-model="eventType" class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2 py-1 text-xs">
        <option v-for="t in EVENT_TYPES" :key="t.value" :value="t.value">{{ t.label }}</option>
      </select>
      <input
        v-model="codes"
        type="text"
        placeholder="股票池（逗号分隔，留空=全部缓存）"
        class="min-w-[220px] flex-1 rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2 py-1 text-xs font-mono outline-none placeholder:text-[#9a9898]"
      />
      <input v-model="startDate" type="date" class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-1.5 py-1 text-xs" />
      <input v-model="endDate" type="date" class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-1.5 py-1 text-xs" />
      <input v-model.number="before" type="number" min="0" title="事件前窗口" class="w-16 rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-1.5 py-1 text-xs" />
      <span class="text-[11px] text-[#646262]">±</span>
      <input v-model.number="after" type="number" min="0" title="事件后窗口" class="w-16 rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-1.5 py-1 text-xs" />
      <Button variant="primary" size="sm" :loading="loading" @click="run">事件研究</Button>
    </div>

    <div v-if="eventType === 'custom'" class="mt-2">
      <textarea
        v-model="manualEvents"
        rows="3"
        spellcheck="false"
        placeholder="每行一个事件：日期 代码（如 2024-01-15 600000.SH）"
        class="w-full font-mono text-xs p-2 rounded-[4px] border border-[#e3e0e0] bg-[#fdfcfc] focus:outline-none"
      />
    </div>

    <div v-if="errorMsg" class="mt-3 rounded-[4px] border border-[#ff3b30] bg-[#ff3b30]/10 px-3 py-2 font-mono text-xs text-[#ff3b30]">{{ errorMsg }}</div>

    <template v-if="result">
      <div v-if="result.error" class="mt-3 rounded-[4px] border border-[#ff3b30] bg-[#ff3b30]/10 px-3 py-2 font-mono text-xs text-[#ff3b30]">{{ result.error }}</div>
      <div v-else-if="result.ok === false" class="mt-3 rounded-[4px] border border-[#ff9f0a] bg-[#ff9f0a]/10 px-3 py-2 font-mono text-xs text-[#9a5b00]">{{ result.note }}</div>
      <template v-else>
        <div class="mt-3 grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] p-2.5">
            <div class="mb-1.5 text-[11px] font-medium text-[#646262]">CAR 累计异常收益（事件窗口）</div>
            <VChart v-if="carOption.series" :option="carOption" :height="240" />
            <div v-else class="py-8 text-center text-xs text-[#646262]">窗口样本不足</div>
          </div>
          <div class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] p-2.5">
            <div class="mb-1.5 text-[11px] font-medium text-[#646262]">统计摘要（t 值 = 均值/标准误，横截面口径）</div>
            <div v-for="[k, v] in summaryRows" :key="k" class="flex items-center justify-between py-1 border-b border-[#f1eeee] last:border-0">
              <span class="text-xs text-[#646262]">{{ k }}</span>
              <span class="text-xs font-mono text-[#201d1d]">{{ v }}</span>
            </div>
            <div v-if="result.note" class="mt-2 text-[11px] text-[#9a9898]">{{ result.note }}</div>
          </div>
        </div>
      </template>
    </template>
  </div>
</template>
