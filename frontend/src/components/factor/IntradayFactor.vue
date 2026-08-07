<script setup lang="ts">
/**
 * 日内高频（分钟级）因子研究 — 公式求值 + 时刻 IC 曲线
 *
 * 链路：分钟缓存（5m 等）→ 清洗（竞价剔除/半日/一字标记）→ 公式求值
 * （ID_* / M_* 算子 + 现成高频因子）→ 折叠日频 → 综合报告；另提供
 * 「时刻 IC 曲线」回答「因子信息在一天里哪个时点最强」。
 */
import { computed, ref } from 'vue'
import { Button, Card, VChart } from '@/components/ui'

interface TimeIcPoint {
  time: string
  ic?: number | null
  rank_ic?: number | null
  icir?: number
  positive_ratio?: number
  n_days?: number
  note?: string
}
interface ComputeResult {
  ok?: boolean
  error?: string
  period?: string
  n_stocks?: number
  start?: string
  end?: string
  n_days?: number
  collapsed_to_daily?: boolean
  one_line_pct?: number | null
  half_day_pct?: number | null
  missing?: string[]
  note?: string
  factor_data?: Record<string, Record<string, number>>
  return_data?: Record<string, Record<string, number>>
}
interface IcByTimeResult {
  ok?: boolean
  error?: string
  times?: TimeIcPoint[]
  n_stocks?: number
  data_start?: string
  data_end?: string
  note?: string
}

const PERIODS = [
  { value: '5m', label: '5分钟（推荐）' },
  { value: '1m', label: '1分钟' },
  { value: '15m', label: '15分钟' },
  { value: '30m', label: '30分钟' },
  { value: '60m', label: '60分钟' },
]

const EXAMPLES = [
  { label: '尾盘动量', formula: 'RANK(TAIL_RET(12))' },
  { label: '开盘反转', formula: 'RANK(-OPEN_RET(6))' },
  { label: '已实现波动率反转', formula: 'RANK(-RV(48))' },
  { label: '跳跃占比', formula: 'RANK(JUMP_DAY())' },
  { label: '日内非流动性', formula: 'RANK(-AMIHUD5())' },
  { label: '收盘VWAP偏离', formula: 'RANK(VWAP_DEV())' },
  { label: '尾盘量能占比', formula: "RANK(ID_SUM(ID_SLICE(m_volume, '14:30', '15:00')) / ID_SUM(m_volume))" },
]

const period = ref('5m')
const formula = ref('')
const codes = ref('')
const startDate = ref('')
const endDate = ref('')
const loading = ref(false)
const errorMsg = ref('')
const result = ref<ComputeResult | null>(null)
const icTimes = ref<IcByTimeResult | null>(null)
const icLoading = ref(false)

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = await res.json().catch(() => null)
  if (!res.ok) throw new Error(data?.detail ?? `接口错误 (HTTP ${res.status})`)
  return data as T
}

async function compute() {
  if (!formula.value.trim()) return
  loading.value = true
  errorMsg.value = ''
  icTimes.value = null
  try {
    result.value = await postJson<ComputeResult>('/api/factor/intraday/compute', {
      formula: formula.value,
      period: period.value,
      stock_pool: codes.value.split(',').map((s) => s.trim()).filter(Boolean),
      start_date: startDate.value,
      end_date: endDate.value,
    })
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

async function runIcByTime() {
  if (!formula.value.trim()) return
  icLoading.value = true
  errorMsg.value = ''
  try {
    icTimes.value = await postJson<IcByTimeResult>('/api/factor/intraday/ic-by-time', {
      formula: formula.value,
      period: period.value,
      stock_pool: codes.value.split(',').map((s) => s.trim()).filter(Boolean),
      start_date: startDate.value,
      end_date: endDate.value,
    })
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e)
  } finally {
    icLoading.value = false
  }
}

/** 时刻 IC 曲线图 */
const icChartOption = computed(() => {
  const times = icTimes.value?.times ?? []
  const valid = times.filter((t) => t.ic != null && t.n_days && (t.n_days ?? 0) > 0)
  if (!valid.length) return {}
  return {
    grid: { left: 48, right: 40, top: 30, bottom: 30 },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: valid.map((t) => t.time), name: '日内时刻', nameTextStyle: { fontSize: 10, color: '#646262' } },
    yAxis: [
      { type: 'value', axisLabel: { formatter: (v: number) => v.toFixed(3) } },
      { type: 'value', name: 'ICIR', nameTextStyle: { fontSize: 10, color: '#646262' }, splitLine: { show: false } },
    ],
    series: [
      { name: 'RankIC', type: 'line', smooth: true, data: valid.map((t) => t.rank_ic), itemStyle: { color: '#007aff' } },
      { name: 'ICIR', type: 'bar', yAxisIndex: 1, data: valid.map((t) => t.icir ?? 0), itemStyle: { color: 'rgba(191,90,242,0.45)' }, barWidth: '40%' },
    ],
  }
})

const metaRows = computed(() => {
  const r = result.value
  if (!r) return []
  const rows: [string, string][] = []
  rows.push(['周期', `${r.period ?? ''}（清洗 ${r.n_stocks ?? 0} 只标的）`])
  rows.push(['区间', `${r.start ?? ''} ~ ${r.end ?? ''}（${r.n_days ?? 0} 个交易日）`])
  rows.push(['折叠为日频', r.collapsed_to_daily ? '是（分钟结果 → ID_LAST 折叠）' : '否（公式直接返回日频）'])
  if (r.one_line_pct != null) rows.push(['一字板占比', (r.one_line_pct * 100).toFixed(2) + '%'])
  if (r.half_day_pct != null) rows.push(['半日市占比', (r.half_day_pct * 100).toFixed(2) + '%'])
  if (r.missing?.length) rows.push(['缺失代码', r.missing.slice(0, 5).join(', ')])
  return rows
})
</script>

<template>
  <div class="flex flex-col gap-3">
    <Card title="日内高频因子 · 分钟级研究">
      <div class="flex flex-wrap items-center gap-2">
        <select v-model="period" class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2 py-1 text-xs">
          <option v-for="p in PERIODS" :key="p.value" :value="p.value">{{ p.label }}</option>
        </select>
        <input
          v-model="codes"
          type="text"
          placeholder="股票池（逗号分隔，留空=全部 5m 缓存）"
          class="min-w-[200px] flex-1 rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2 py-1 text-xs font-mono outline-none placeholder:text-[#9a9898]"
        />
        <input v-model="startDate" type="date" class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-1.5 py-1 text-xs" />
        <input v-model="endDate" type="date" class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-1.5 py-1 text-xs" />
      </div>

      <div class="mt-2 flex flex-wrap gap-1.5">
        <span class="text-[11px] leading-6 text-[#646262]">示例：</span>
        <button
          v-for="ex in EXAMPLES"
          :key="ex.label"
          class="rounded-[3px] border border-[rgba(0,122,255,0.35)] bg-[rgba(0,122,255,0.06)] px-1.5 py-0.5 text-[11px] text-[#007aff] hover:bg-[rgba(0,122,255,0.12)]"
          @click="formula = ex.formula"
        >
          {{ ex.label }}
        </button>
      </div>

      <textarea
        v-model="formula"
        rows="4"
        spellcheck="false"
        placeholder="分钟公式：RANK(TAIL_RET(12)) ｜ 字段 m_close/m_volume... ｜ 聚合 ID_LAST/ID_MEAN/ID_SLICE ｜ 序列 M_MA/M_DELAY"
        class="mt-2 w-full font-mono text-xs p-2 rounded-[4px] border border-[#e3e0e0] bg-[#f8f7f7] text-[#201d1d] focus:outline-none focus:border-[#007aff] resize-y"
      />
      <div class="mt-2 flex gap-2">
        <Button variant="primary" size="sm" :loading="loading" @click="compute">计算因子（折叠日频）</Button>
        <Button variant="secondary" size="sm" :loading="icLoading" @click="runIcByTime">时刻 IC 曲线</Button>
      </div>
      <div v-if="errorMsg" class="mt-3 rounded-[4px] border border-[#ff3b30] bg-[#ff3b30]/10 px-3 py-2 font-mono text-xs text-[#ff3b30]">{{ errorMsg }}</div>
      <div v-if="result?.error" class="mt-3 rounded-[4px] border border-[#ff3b30] bg-[#ff3b30]/10 px-3 py-2 font-mono text-xs text-[#ff3b30]">{{ result.error }}</div>
      <div v-if="result?.note" class="mt-3 text-[11px] text-[#9a9898]">{{ result.note }}</div>
      <div v-if="result" class="mt-3 grid grid-cols-1 lg:grid-cols-3 gap-2">
        <div
          v-for="[k, v] in metaRows"
          :key="k"
          class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2.5 py-1.5"
        >
          <div class="text-[11px] text-[#646262]">{{ k }}</div>
          <div class="text-xs font-mono text-[#201d1d]">{{ v }}</div>
        </div>
      </div>
    </Card>

    <Card title="时刻 IC 曲线 — 因子信息随时点分布（指导执行时点）">
      <div v-if="!icChartOption.series" class="py-10 text-center text-xs text-[#646262]">
        先写公式点「时刻 IC 曲线」：同一公式在 09:45/10:30/11:15/14:00/14:45/14:55 各取截面，对同一次日收益算 RankIC
      </div>
      <template v-else>
        <VChart :option="icChartOption" :height="260" />
        <div class="mt-2 flex flex-wrap gap-1.5">
          <span
            v-for="t in (icTimes?.times ?? []).filter((x) => x.ic != null)"
            :key="t.time"
            class="rounded-[3px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-2 py-1 text-[11px] font-mono"
          >
            {{ t.time }} ｜ RankIC {{ (t.rank_ic ?? 0).toFixed(4) }} ｜ ICIR {{ (t.icir ?? 0).toFixed(2) }} ｜ 正值占比 {{ ((t.positive_ratio ?? 0) * 100).toFixed(0) }}%
          </span>
        </div>
        <div v-if="icTimes?.note" class="mt-2 text-[11px] text-[#9a9898]">{{ icTimes.note }}</div>
      </template>
    </Card>
  </div>
</template>
