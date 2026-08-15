<script setup lang="ts">
/**
 * FactorScan — 因子批量扫描（研究第一步：扫一遍存量因子看谁还活着）
 *
 * 选择类别/因子 → 全市场一次算完（SSE 逐因子进度）→ 按 IC/RankIC/ICIR 排序
 * → 勾选加入因子池。结果覆盖更新预置因子指标并留存历史快照（与单因子重算同语义）。
 */
import { computed, onUnmounted, ref } from 'vue'
import { Button, Select } from '@/components/ui'
import type { SelectOption } from '@/components/ui'
import { Play, RefreshCw, Database } from 'lucide-vue-next'
import { usePresetFactorCategories } from '@/composables/usePresetFactors'

interface ScanRow {
  factor_id: number
  factor_name: string
  category_name: string
  ok: boolean
  error?: string
  metrics?: {
    ic_mean: number
    rank_ic: number
    ic_ir: number
    t_stat: number
    positive_ratio: number
    long_short_cum: number
    monotonicity: number
    n_cross_sections: number
  }
  elapsed_ms?: number
}

const { data: categories } = usePresetFactorCategories()

const categoryCode = ref('')
const scanAll = ref(false)
const maxWorkers = ref(4)
const stockPool = ref('')
const running = ref(false)
const rows = ref<ScanRow[]>([])
const summary = ref<{ ok_count: number; failed: number; failed_names: string[]; data_date: string; n_stocks: number; n_dates: number; duration_ms: number; message?: string; warnings?: string[] } | null>(null)
const errorMsg = ref<string | null>(null)
const progress = ref({ done: 0, total: 0 })
const selected = ref<Set<number>>(new Set())

const categoryOptions = computed<SelectOption[]>(() => [
  { value: '', label: '全部类别' },
  ...(categories.value ?? []).map((c) => ({ value: c.category_code, label: `${c.category_name} (${c.factor_count})` })),
])

const presetTotal = computed(() =>
  (categories.value ?? []).reduce((sum, c) => sum + (c.factor_count || 0), 0),
)

const sortField = ref<keyof NonNullable<ScanRow['metrics']> | 'factor_name'>('rank_ic')
const sortedRows = computed(() => {
  const arr = [...rows.value]
  const f = sortField.value
  if (f === 'factor_name') {
    return arr.sort((a, b) => a.factor_name.localeCompare(b.factor_name))
  }
  return arr.sort((a, b) => (b.metrics?.[f] ?? -Infinity) - (a.metrics?.[f] ?? -Infinity))
})

function fmt(v: number | null | undefined, d = 4): string {
  if (v == null || Number.isNaN(v)) return '—'
  return v.toFixed(d)
}

function parseSSEEvent(raw: string): { type: string; data: any } | null {
  let type = ''
  const dataLines: string[] = []
  for (const line of raw.split('\n')) {
    if (line.startsWith('event: ')) type = line.slice(7).trim()
    else if (line.startsWith('data: ')) dataLines.push(line.slice(6))
  }
  if (!dataLines.length) return null
  try {
    return { type, data: JSON.parse(dataLines.join('\n')) }
  } catch {
    return null
  }
}

async function runScan() {
  running.value = true
  errorMsg.value = null
  rows.value = []
  summary.value = null
  progress.value = { done: 0, total: 0 }
  try {
    const body: Record<string, unknown> = {
      category_codes: scanAll.value || !categoryCode.value ? undefined : [categoryCode.value],
      limit: 300,
      periods: [1, 5, 10, 20],
      max_workers: maxWorkers.value,
      stock_pool: stockPool.value
        .split(/[,，]/)
        .map((c) => c.trim())
        .filter(Boolean),
    }
    if (body.category_codes === undefined) delete body.category_codes
    const res = await fetch('/api/factor/scan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok || !res.body) {
      const err = await res.json().catch(() => null)
      throw new Error(err?.detail ?? `HTTP ${res.status}`)
    }
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const parts = buffer.split('\n\n')
      buffer = parts.pop() ?? ''
      for (const part of parts) {
        const evt = parseSSEEvent(part)
        if (!evt) continue
        if (evt.type === 'scan_start') {
          progress.value.total = evt.data.total
        } else if (evt.type === 'factor_done') {
          rows.value.push(evt.data as ScanRow)
          progress.value.done += 1
        } else if (evt.type === 'scan_done') {
          summary.value = evt.data
          if (!evt.data.ok_count && evt.data.failed && evt.data.message) {
            errorMsg.value = evt.data.message
          }
        }
      }
    }
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e)
  } finally {
    running.value = false
  }
}

async function addToPool(id: number) {
  await fetch(`/api/factor/preset/${id}/add-to-pool`, { method: 'POST' })
  selected.value.delete(id)
}

function toggleRow(id: number) {
  const next = new Set(selected.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selected.value = next
}

async function addSelected() {
  await Promise.all([...selected.value].map((id) => addToPool(id)))
}

onUnmounted(() => {
  // 组件卸载不中断后端扫描（结果仍落库），仅丢弃本地状态
})
</script>

<template>
  <div class="flex flex-col gap-3">
    <!-- 配置行 -->
    <div class="flex flex-wrap items-center gap-2 rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-3 py-2">
      <Database :size="13" class="text-[#646262]" />
      <span class="text-xs text-[#646262]">批量扫描</span>
      <div class="w-[160px]">
        <Select v-model="categoryCode" :options="categoryOptions" placeholder="全部类别" :disabled="running" />
      </div>
      <label class="flex cursor-pointer items-center gap-1 text-xs text-[#646262]">
        <input v-model="scanAll" type="checkbox" class="accent-[#007aff]" :disabled="running" />
        全部 {{ presetTotal }} 个因子
      </label>
      <input
        v-model="stockPool"
        type="text"
        :disabled="running"
        placeholder="股票池（逗号分隔，留空=全部本地股票）"
        class="w-[300px] rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2 py-1 text-xs text-[#201d1d] outline-none focus:border-[#007aff] disabled:opacity-50"
      />
      <Button
        variant="secondary"
        size="sm"
        :loading="running"
        class="flex items-center gap-1 text-xs"
        @click="runScan"
      >
        <Play :size="12" />
        {{ running ? `扫描中 ${progress.done}/${progress.total}` : '开始扫描' }}
      </Button>
      <span class="text-[11px] text-[#9a9898]">
        面板只加载一次、全因子共享；结果覆盖更新 + 历史快照；按「数据中心」下载的行情计算
      </span>
    </div>

    <!-- 扫描样本警示 -->
    <div
      v-if="summary?.warnings?.length"
      class="rounded-[4px] border border-[#ff9f0a]/35 bg-[#ff9f0a]/7 px-3 py-2 text-[11px] leading-relaxed text-[#a05a00]"
    >
      <div v-for="(w, i) in summary.warnings" :key="i">⚠ {{ w }}</div>
    </div>

    <div v-if="errorMsg" class="rounded-[4px] border border-[#ff3b30]/40 bg-[#ff3b30]/8 px-3 py-2 text-xs text-[#c62d23]">
      {{ errorMsg }}
    </div>

    <div
      v-if="summary"
      class="rounded-[4px] border border-[#30d158]/30 bg-[#30d158]/6 px-3 py-2 text-xs text-[#248a3d]"
    >
      扫描完成：成功 {{ summary.ok_count }} · 失败 {{ summary.failed }}
      <template v-if="summary.failed_names.length">（{{ summary.failed_names.join('、') }}）</template>
      · 数据截至 {{ summary.data_date }} · {{ summary.n_stocks }} 只 · {{ summary.n_dates }} 个交易日 · 耗时
      {{ (summary.duration_ms / 1000).toFixed(1) }}s
    </div>

    <!-- 结果表 -->
    <div v-if="rows.length" class="overflow-auto rounded-[4px] border border-[rgba(15,0,0,0.12)]">
      <table class="w-full min-w-[900px] text-xs">
        <thead>
          <tr class="bg-[#f8f7f7] text-left text-[#646262]">
            <th class="px-2 py-1.5 font-medium">勾选</th>
            <th class="px-2 py-1.5 font-medium cursor-pointer select-none hover:text-[#201d1d]" @click="sortField = 'factor_name'">
              因子 {{ sortField === 'factor_name' ? '⇅' : '' }}
            </th>
            <th class="px-2 py-1.5 font-medium">类别</th>
            <th
              v-for="(label, key) in { rank_ic: 'RANK_IC', ic_mean: 'IC_MEAN', ic_ir: 'IC_IR', t_stat: 'T值', positive_ratio: '正占比', long_short_cum: '多空累计', monotonicity: '单调性' }"
              :key="key"
              class="cursor-pointer select-none px-2 py-1.5 font-medium hover:text-[#201d1d]"
              @click="sortField = key as any"
            >
              {{ label }} {{ sortField === key ? '⇅' : '' }}
            </th>
            <th class="px-2 py-1.5 font-medium">截面数</th>
            <th class="px-2 py-1.5 font-medium">耗时</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="r in sortedRows"
            :key="r.factor_id"
            class="border-t border-[rgba(15,0,0,0.06)] transition-colors hover:bg-[#f1eeee]"
            :class="!r.ok ? 'opacity-50' : ''"
          >
            <td class="px-2 py-1.5">
              <input
                v-if="r.ok"
                type="checkbox"
                :checked="selected.has(r.factor_id)"
                class="accent-[#007aff]"
                @change="toggleRow(r.factor_id)"
              />
            </td>
            <td class="px-2 py-1.5 font-medium text-[#201d1d]">{{ r.factor_name }}</td>
            <td class="px-2 py-1.5 text-[#646262]">{{ r.category_name }}</td>
            <template v-if="r.ok">
              <td class="px-2 py-1.5 font-mono" :class="r.metrics!.rank_ic > 0 ? 'text-[#248a3d]' : 'text-[#c62d23]'">{{ fmt(r.metrics!.rank_ic) }}</td>
              <td class="px-2 py-1.5 font-mono" :class="r.metrics!.ic_mean > 0 ? 'text-[#248a3d]' : 'text-[#c62d23]'">{{ fmt(r.metrics!.ic_mean) }}</td>
              <td class="px-2 py-1.5 font-mono">{{ fmt(r.metrics!.ic_ir) }}</td>
              <td class="px-2 py-1.5 font-mono">{{ fmt(r.metrics!.t_stat) }}</td>
              <td class="px-2 py-1.5 font-mono">{{ fmt(r.metrics!.positive_ratio, 2) }}</td>
              <td class="px-2 py-1.5 font-mono">{{ fmt(r.metrics!.long_short_cum, 2) }}</td>
              <td class="px-2 py-1.5 font-mono">{{ fmt(r.metrics!.monotonicity, 2) }}</td>
              <td class="px-2 py-1.5 font-mono text-[#9a9898]">{{ r.metrics!.n_cross_sections }}</td>
            </template>
            <template v-else>
              <td colspan="7" class="px-2 py-1.5 text-[#c62d23]">{{ r.error }}</td>
            </template>
            <td class="px-2 py-1.5 font-mono text-[#9a9898]">{{ r.elapsed_ms }}ms</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-else-if="!running && !errorMsg" class="py-6 text-center text-xs text-[#9a9898]">
      选择类别或勾选「全部因子」后点击「开始扫描」— 按 IC 排序找出当前仍有效的因子
    </div>

    <div v-if="selected.size" class="flex items-center gap-2">
      <Button variant="secondary" size="sm" class="text-xs" @click="addSelected">
        <RefreshCw :size="12" class="mr-1" />
        将勾选的 {{ selected.size }} 个因子加入因子池
      </Button>
    </div>
  </div>
</template>
