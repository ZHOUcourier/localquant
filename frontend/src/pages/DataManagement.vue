<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useMutation, useQuery } from '@tanstack/vue-query'
import { Wifi, WifiOff, Database, Download, ShieldCheck, Loader2, Layers, RefreshCw, CalendarClock } from 'lucide-vue-next'
import { Card, Button, Input, Select, Badge, Dialog, Table, ScrollArea } from '@/components/ui'
import type { Column, BadgeVariant } from '@/components/ui'

interface DataStatus {
  qmt_connected?: boolean
  qmt_path?: string
  qmt_data_dir?: string
  cache_count?: number
  cache_size?: string
  total_records?: number
  [key: string]: unknown
}

interface QualityResult {
  passed?: boolean
  issues?: string[]
  summary?: string
  [key: string]: unknown
}

interface CoverageEntry {
  code: string
  start: string | null
  end: string | null
  rows: number
}

interface ReferenceStatus {
  reference?: Record<string, { rows: number; latest: string | null }>
  snapshot_indices?: string[]
}

const periodOptions = [
  { value: '1d', label: '日线' },
  { value: '1m', label: '1分钟' },
  { value: '5m', label: '5分钟' },
  { value: '15m', label: '15分钟' },
  { value: '30m', label: '30分钟' },
  { value: '60m', label: '60分钟' },
  { value: 'tick', label: 'Tick' },
]

const symbol = ref('')
const period = ref('1d')
const startDate = ref('')
const endDate = ref('')
const qualityOpen = ref(false)

const { data: status, refetch: refetchStatus } = useQuery<DataStatus>({
  queryKey: ['data-status'],
  queryFn: () => fetch('/api/data/status').then((r) => r.json()),
})

const downloadMutation = useMutation({
  mutationFn: async () => {
    const res = await fetch('/api/data/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        symbol: symbol.value,
        period: period.value,
        start_date: startDate.value,
        end_date: endDate.value,
      }),
    })
    const body = await res.json().catch(() => null)
    if (!res.ok) {
      throw new Error(body?.detail ?? `下载接口错误 (HTTP ${res.status})`)
    }
    return body as { status: string; symbol: string; rows: number }
  },
  onSuccess: () => {
    refetchStatus()
  },
})

const qualityMutation = useMutation<QualityResult, Error, void>({
  mutationFn: () =>
    fetch('/api/data/quality-check', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    }).then((r) => r.json()),
  onSuccess: () => (qualityOpen.value = true),
})

// ── 批量下载（SSE 逐只进度） ────────────────────────────

const batchSector = ref('')
const batchSymbols = ref('')
const batchPeriod = ref('1d')
const batchStart = ref('')
const batchEnd = ref('')

const batch = reactive({
  running: false,
  total: 0,
  done: 0,
  ok: 0,
  failedCodes: [] as string[],
  currentCode: '',
  message: '',
  error: '',
  referenceLogs: [] as string[],
})

const batchProgress = computed(() =>
  batch.total > 0 ? Math.round((batch.done / batch.total) * 100) : 0,
)

/** 消费 POST SSE 流（fetch + ReadableStream，EventSource 不支持 POST） */
async function consumeSse(
  url: string,
  body: unknown,
  onEvent: (type: string, data: Record<string, unknown>) => void,
) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok || !res.body) {
    const err = await res.json().catch(() => null)
    throw new Error(err?.detail ?? `接口错误 (HTTP ${res.status})`)
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() ?? ''
    for (const block of blocks) {
      let eventType = 'message'
      let data = ''
      for (const line of block.split('\n')) {
        if (line.startsWith('event: ')) eventType = line.slice(7).trim()
        else if (line.startsWith('data: ')) data += line.slice(6)
      }
      if (!data) continue
      try {
        onEvent(eventType, JSON.parse(data))
      } catch {
        // 忽略非 JSON 块
      }
    }
  }
}

function handleBatchEvent(type: string, data: Record<string, unknown>) {
  if (type === 'batch_start') {
    batch.total = data.total as number
  } else if (type === 'symbol_complete') {
    batch.done++
    batch.ok++
    batch.currentCode = data.code as string
  } else if (type === 'symbol_failed') {
    batch.done++
    batch.failedCodes.push(data.code as string)
    batch.currentCode = data.code as string
  } else if (type === 'reference_saved') {
    const err = data.error ? `（失败: ${data.error}）` : ''
    batch.referenceLogs.push(`${data.kind}: ${data.rows} 条${err}`)
  } else if (type === 'batch_complete') {
    batch.message = `完成：成功 ${data.ok} 只，失败 ${data.failed} 只`
  } else if (type === 'batch_failed') {
    batch.error = (data.message as string) ?? '批量下载失败'
  }
}

async function runBatch(payload: { sector?: string; symbols?: string[] }) {
  batch.running = true
  batch.total = 0
  batch.done = 0
  batch.ok = 0
  batch.failedCodes = []
  batch.currentCode = ''
  batch.message = ''
  batch.error = ''
  batch.referenceLogs = []
  try {
    await consumeSse(
      '/api/data/download-batch',
      {
        sector: payload.sector ?? '',
        symbols: payload.symbols ?? [],
        period: batchPeriod.value,
        start_date: batchStart.value,
        end_date: batchEnd.value,
      },
      handleBatchEvent,
    )
  } catch (e) {
    batch.error = e instanceof Error ? e.message : '批量下载失败'
  } finally {
    batch.running = false
    refetchStatus()
    refetchCoverage()
    refetchReference()
  }
}

function startBatch() {
  if (batchSector.value.trim()) {
    runBatch({ sector: batchSector.value.trim() })
  } else {
    const symbols = batchSymbols.value
      .split(/[\s,，;；]+/)
      .map((s) => s.trim())
      .filter(Boolean)
    runBatch({ symbols })
  }
}

function retryFailed() {
  runBatch({ symbols: [...batch.failedCodes] })
}

// ── 一键补齐 ──────────────────────────────────────────

async function runUpdateCached() {
  batch.running = true
  batch.total = 0
  batch.done = 0
  batch.ok = 0
  batch.failedCodes = []
  batch.currentCode = ''
  batch.message = ''
  batch.error = ''
  batch.referenceLogs = []
  try {
    await consumeSse('/api/data/update-cached?period=1d', {}, handleBatchEvent)
  } catch (e) {
    batch.error = e instanceof Error ? e.message : '补齐失败'
  } finally {
    batch.running = false
    refetchStatus()
    refetchCoverage()
    refetchReference()
  }
}

// ── 覆盖度与参考数据 ──────────────────────────────────

const { data: coverageData, refetch: refetchCoverage } = useQuery<{
  count: number
  entries: CoverageEntry[]
}>({
  queryKey: ['data-coverage'],
  queryFn: () => fetch('/api/data/coverage?period=1d').then((r) => r.json()),
})

const { data: referenceData, refetch: refetchReference } = useQuery<ReferenceStatus>({
  queryKey: ['reference-status'],
  queryFn: () => fetch('/api/data/reference-status').then((r) => r.json()),
})

const coverageColumns = [
  { key: 'code', title: '代码', dataIndex: 'code' },
  { key: 'start', title: '起始', dataIndex: 'start' },
  { key: 'end', title: '截止', dataIndex: 'end' },
  { key: 'rows', title: '条数', dataIndex: 'rows' },
]

const referenceLabels: Record<string, string> = {
  index_constituents: '指数成分快照',
  industry: '行业分类',
  capital: '股本记录',
  instrument: '合约详情',
}

// ── 每日批处理调度 ─────────────────────────────────────

interface DailyJob {
  job_name: string
  status: 'running' | 'ok' | 'failed' | 'skipped'
  trigger: string
  detail: string
  started_at: number | null
  finished_at: number | null
}

interface SchedulerStatus {
  enabled?: boolean
  update_time?: string
  recalc_time?: string
  recent?: DailyJob[]
}

const jobLabels: Record<string, string> = {
  market_update: '行情增量·参考快照',
  factor_recalc: '因子池重算',
}

const jobStatusBadge: Record<string, BadgeVariant> = {
  running: 'warning',
  ok: 'success',
  failed: 'error',
  skipped: 'default',
}

const runSteps = ref<string[]>([])

const { data: schedulerStatus, refetch: refetchScheduler } = useQuery<SchedulerStatus>({
  queryKey: ['scheduler-status'],
  queryFn: () => fetch('/api/ops/scheduler').then((r) => r.json()),
})

const schedulerRunMutation = useMutation({
  mutationFn: async () => {
    const body = runSteps.value.length
      ? JSON.stringify({ steps: runSteps.value })
      : '{}'
    const res = await fetch('/api/ops/scheduler/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
    })
    const resp = await res.json().catch(() => null)
    if (!res.ok) throw new Error(resp?.detail ?? `调度失败 (HTTP ${res.status})`)
    return resp as Record<string, string>
  },
  onSuccess: () => {
    refetchScheduler()
    refetchProvenance()
  },
})

function fmtJobTime(ms: number | null | undefined) {
  if (!ms) return '—'
  const d = new Date(ms)
  return d.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function toggleStep(s: string) {
  if (runSteps.value.includes(s)) {
    runSteps.value = runSteps.value.filter((x) => x !== s)
  } else {
    runSteps.value = [...runSteps.value, s]
  }
}

// ── 分析溯源 ─────────────────────────────────────────

interface ProvenanceRow {
  id: number
  kind: string
  entity_id: string
  entity_name: string
  params_json?: Record<string, unknown>
  metrics_json?: Record<string, unknown>
  notes: string
  source: string
  created_at: number | null
}

const provKind = ref('')

const { data: provenanceData, refetch: refetchProvenance } = useQuery<ProvenanceRow[]>({
  queryKey: ['provenance', provKind],
  queryFn: () =>
    fetch(`/api/ops/provenance?limit=50&kind=${provKind}`).then((r) => r.json()),
})

const provenanceColumns: Column[] = [
  { key: 'id', title: 'ID', dataIndex: 'id' },
  { key: 'kind', title: '类型', dataIndex: 'kind' },
  { key: 'entity_name', title: '实体', dataIndex: 'entity_name' },
  { key: 'source', title: '来源', dataIndex: 'source' },
  { key: 'created_at', title: '时间', dataIndex: 'created_at' },
]
</script>

<template>
  <div>
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <!-- QMT 连接状态 -->
      <Card title="QMT 连接状态">
        <div class="flex flex-col items-center py-4 gap-3">
          <div class="relative">
            <div
              class="w-12 h-12 rounded-full flex items-center justify-center"
              :class="status?.qmt_connected ? 'bg-[#30d158]/15' : 'bg-[#ff3b30]/15'"
            >
              <Wifi v-if="status?.qmt_connected" :size="24" class="text-[#30d158]" />
              <WifiOff v-else :size="24" class="text-[#ff3b30]" />
            </div>
            <span
              class="absolute -top-0.5 -right-0.5 w-3.5 h-3.5 rounded-full border-2 border-[#f1eeee]"
              :class="status?.qmt_connected ? 'bg-[#30d158]' : 'bg-[#ff3b30]'"
            />
          </div>
          <div class="text-center">
            <div
              class="text-sm font-medium mb-1"
              :class="status?.qmt_connected ? 'text-[#30d158]' : 'text-[#ff3b30]'"
            >
              {{ status?.qmt_connected ? '已连接' : '未连接' }}
            </div>
            <div v-if="status?.qmt_path" class="text-xs text-[#646262] font-mono truncate max-w-[200px]">
              {{ status.qmt_path }}
            </div>
            <div v-if="status?.qmt_data_dir" class="text-xs text-[#646262] font-mono truncate max-w-[200px]">
              {{ status.qmt_data_dir }}
            </div>
          </div>
        </div>
      </Card>

      <!-- 缓存统计 -->
      <Card title="缓存统计">
        <div class="space-y-3 py-2">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <Database :size="15" class="text-[#64d2ff]" />
              <span class="text-sm text-[#201d1d]">已缓存品种</span>
            </div>
            <span class="text-sm font-mono text-[#007aff]">{{ status?.cache_count ?? 0 }}</span>
          </div>
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <Database :size="15" class="text-[#64d2ff]" />
              <span class="text-sm text-[#201d1d]">数据总量</span>
            </div>
            <span class="text-sm font-mono text-[#007aff]">
              {{ status?.total_records?.toLocaleString() ?? '0' }} 条
            </span>
          </div>
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <Database :size="15" class="text-[#64d2ff]" />
              <span class="text-sm text-[#201d1d]">磁盘占用</span>
            </div>
            <span class="text-sm font-mono text-[#007aff]">{{ status?.cache_size ?? '0 MB' }}</span>
          </div>
        </div>
      </Card>

      <!-- 数据质量 -->
      <Card title="数据质量">
        <div class="flex flex-col items-center justify-center py-6 gap-3">
          <ShieldCheck :size="32" class="text-[#64d2ff]" />
          <p class="text-xs text-[#646262] text-center">运行数据质量检查，验证缓存数据完整性</p>
          <Button
            variant="secondary"
            size="sm"
            :loading="qualityMutation.isPending.value"
            @click="qualityMutation.mutate()"
          >
            运行检查
          </Button>
        </div>
      </Card>
    </div>

    <!-- 数据下载 -->
    <div class="mt-4">
      <Card title="数据下载">
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 items-end">
          <div>
            <label class="block text-xs text-[#646262] mb-1">品种代码</label>
            <Input v-model="symbol" placeholder="如: 000001.SZ" />
          </div>
          <div>
            <label class="block text-xs text-[#646262] mb-1">周期</label>
            <Select v-model="period" :options="periodOptions" />
          </div>
          <div>
            <label class="block text-xs text-[#646262] mb-1">开始日期</label>
            <Input v-model="startDate" type="date" />
          </div>
          <div>
            <label class="block text-xs text-[#646262] mb-1">结束日期</label>
            <Input v-model="endDate" type="date" />
          </div>
          <Button
            variant="primary"
            :disabled="!symbol"
            :loading="downloadMutation.isPending.value"
            @click="downloadMutation.mutate()"
          >
            <Download :size="14" class="mr-1" />
            下载
          </Button>
        </div>

        <!-- 下载状态（真实结果，非模拟进度） -->
        <div
          v-if="downloadMutation.isPending.value"
          class="mt-3 flex items-center gap-2 text-xs text-[#646262]"
        >
          <Loader2 :size="13" class="animate-spin" />
          正在从 QMT 下载 {{ symbol }} ({{ period }}) 数据...
        </div>
        <div
          v-if="downloadMutation.isError.value"
          class="mt-3 rounded-[4px] border border-[#ff3b30] bg-[#ff3b30]/10 px-3 py-2 font-mono text-xs text-[#ff3b30]"
        >
          {{ downloadMutation.error.value instanceof Error ? downloadMutation.error.value.message : '下载失败' }}
        </div>
        <div
          v-if="downloadMutation.isSuccess.value"
          class="mt-3 rounded-[4px] border border-[#30d158] bg-[#30d158]/10 px-3 py-2 font-mono text-xs text-[#30d158]"
        >
          下载完成: {{ downloadMutation.data.value?.symbol }} 共 {{ downloadMutation.data.value?.rows }} 条数据已写入本地缓存
        </div>
      </Card>
    </div>

    <!-- 批量下载（板块/指数/代码列表） -->
    <div class="mt-4">
      <Card title="批量下载">
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 items-end">
          <div>
            <label class="block text-xs text-[#646262] mb-1">板块/指数名（如：沪深300）</label>
            <Input v-model="batchSector" placeholder="优先于代码列表" />
          </div>
          <div class="lg:col-span-2">
            <label class="block text-xs text-[#646262] mb-1">代码列表（逗号/空格/换行分隔）</label>
            <Input v-model="batchSymbols" placeholder="000001.SZ, 600000.SH ..." />
          </div>
          <div>
            <label class="block text-xs text-[#646262] mb-1">周期</label>
            <Select v-model="batchPeriod" :options="periodOptions" />
          </div>
          <div class="flex gap-2">
            <Button
              variant="primary"
              :disabled="batch.running || (!batchSector.trim() && !batchSymbols.trim())"
              @click="startBatch"
            >
              <Layers :size="14" class="mr-1" />
              批量下载
            </Button>
            <Button
              variant="secondary"
              :disabled="batch.running"
              @click="runUpdateCached"
            >
              <RefreshCw :size="14" class="mr-1" />
              一键补齐
            </Button>
          </div>
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
          <div>
            <label class="block text-xs text-[#646262] mb-1">开始日期</label>
            <Input v-model="batchStart" type="date" />
          </div>
          <div>
            <label class="block text-xs text-[#646262] mb-1">结束日期</label>
            <Input v-model="batchEnd" type="date" />
          </div>
        </div>

        <!-- 进度（真实 SSE 事件驱动） -->
        <div v-if="batch.running || batch.total > 0" class="mt-4 space-y-2">
          <div class="flex items-center justify-between text-xs text-[#646262]">
            <span class="flex items-center gap-1.5">
              <Loader2 v-if="batch.running" :size="13" class="animate-spin" />
              {{ batch.done }} / {{ batch.total }}
              <span v-if="batch.currentCode" class="font-mono">{{ batch.currentCode }}</span>
            </span>
            <span class="font-mono">{{ batchProgress }}%</span>
          </div>
          <div class="h-1.5 rounded-full bg-[#e3e0e0] overflow-hidden">
            <div
              class="h-full rounded-full bg-[#007aff] transition-all duration-200"
              :style="{ width: `${batchProgress}%` }"
            />
          </div>
          <div v-if="batch.message" class="text-xs text-[#30d158] font-mono">{{ batch.message }}</div>
          <div v-if="batch.referenceLogs.length" class="text-xs text-[#646262] font-mono">
            参考数据快照 — {{ batch.referenceLogs.join('；') }}
          </div>
          <div
            v-if="batch.failedCodes.length"
            class="rounded-[4px] border border-[#ff9f0a] bg-[#ff9f0a]/10 px-3 py-2 text-xs"
          >
            <div class="flex items-center justify-between">
              <span class="text-[#ff9f0a]">失败 {{ batch.failedCodes.length }} 只：
                <span class="font-mono">{{ batch.failedCodes.slice(0, 10).join(', ') }}{{ batch.failedCodes.length > 10 ? ' …' : '' }}</span>
              </span>
              <Button variant="secondary" size="sm" :disabled="batch.running" @click="retryFailed">
                重试失败项
              </Button>
            </div>
          </div>
          <div
            v-if="batch.error"
            class="rounded-[4px] border border-[#ff3b30] bg-[#ff3b30]/10 px-3 py-2 font-mono text-xs text-[#ff3b30]"
          >
            {{ batch.error }}
          </div>
        </div>
      </Card>
    </div>

    <!-- 缓存覆盖度 & 参考数据 -->
    <div class="mt-4 grid grid-cols-1 lg:grid-cols-3 gap-4">
      <div class="lg:col-span-2">
        <Card :title="`缓存覆盖度（日线，${coverageData?.count ?? 0} 只）`">
          <div v-if="!coverageData?.entries?.length" class="py-6 text-center text-xs text-[#646262]">
            本地无缓存数据 — 请先使用上方批量下载
          </div>
          <ScrollArea v-else class="max-h-[320px]">
            <Table :columns="coverageColumns" :data-source="coverageData.entries" row-key="code" />
          </ScrollArea>
        </Card>
      </div>
      <Card title="参考数据快照">
        <div class="space-y-3 py-2">
          <div
            v-for="(label, key) in referenceLabels"
            :key="key"
            class="flex items-center justify-between"
          >
            <span class="text-sm text-[#201d1d]">{{ label }}</span>
            <span class="text-xs font-mono" :class="referenceData?.reference?.[key]?.rows ? 'text-[#007aff]' : 'text-[#646262]'">
              {{ referenceData?.reference?.[key]?.rows ?? 0 }} 条
              <template v-if="referenceData?.reference?.[key]?.latest">
                · {{ referenceData.reference[key].latest }}
              </template>
            </span>
          </div>
          <div v-if="referenceData?.snapshot_indices?.length" class="pt-2 border-t border-[#e3e0e0]">
            <div class="text-xs text-[#646262] mb-1.5">已有成分快照的指数/板块</div>
            <div class="flex flex-wrap gap-1.5">
              <Badge v-for="name in referenceData.snapshot_indices" :key="name" variant="info">
                {{ name }}
              </Badge>
            </div>
          </div>
          <p class="text-xs text-[#646262] leading-relaxed pt-1">
            参考数据随批量下载自动快照；指数历史成分从首次快照日起逐日积累，更早区间仍为当前成分（存在幸存者偏差）。
          </p>
        </div>
      </Card>
    </div>

    <!-- 每日批处理调度 -->
    <div class="mt-4 grid grid-cols-1 lg:grid-cols-3 gap-4">
      <div class="lg:col-span-1">
        <Card title="每日批处理调度">
          <div class="space-y-3 py-1">
            <div class="flex items-center justify-between">
              <span class="text-xs text-[#646262]">调度开关</span>
              <Badge :variant="schedulerStatus?.enabled ? 'success' : 'default'">
                {{ schedulerStatus?.enabled ? '已启用' : '已停用' }}
              </Badge>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-xs text-[#646262]">行情增量·快照</span>
              <span class="text-sm font-mono text-[#007aff]">{{ schedulerStatus?.update_time ?? '—' }}</span>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-xs text-[#646262]">因子池重算</span>
              <span class="text-sm font-mono text-[#007aff]">{{ schedulerStatus?.recalc_time ?? '—' }}</span>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-xs text-[#646262]">运行范围</span>
              <div class="flex flex-wrap gap-1.5 justify-end">
                <button
                  v-for="s in ['market', 'recalc'] as const"
                  :key="s"
                  class="text-[11px] px-2 py-0.5 rounded-full border"
                  :class="runSteps.includes(s) ? 'bg-[#007aff] text-white border-[#007aff]' : 'border-[#d5d2d2] text-[#646262]'"
                  @click="toggleStep(s)"
                >
                  {{ s === 'market' ? '行情' : '重算' }}
                </button>
              </div>
            </div>
            <div class="pt-1 flex gap-2">
              <Button variant="primary" size="sm" class="flex-1" :loading="schedulerRunMutation.isPending.value" @click="schedulerRunMutation.mutate()">
                <CalendarClock :size="14" class="mr-1" />
                手动运行
              </Button>
              <Button variant="secondary" size="sm" @click="refetchScheduler()">
                <RefreshCw :size="14" />
              </Button>
            </div>
            <div v-if="schedulerRunMutation.data.value" class="text-[11px] font-mono text-[#30d158]">
              {{ Object.entries(schedulerRunMutation.data.value).map(([k, v]) => `${k}=${v}`).join(' · ') }}
            </div>
            <div v-if="schedulerRunMutation.isError.value" class="text-[11px] font-mono text-[#ff3b30]">
              {{ schedulerRunMutation.error.value instanceof Error ? schedulerRunMutation.error.value.message : '运行失败' }}
            </div>
            <p class="text-[11px] text-[#646262] leading-relaxed pt-1 border-t border-[#e3e0e0]">
              QMT 未连接或本地无行情缓存时，对应步骤自动跳过（不伪造），仅在有真实数据时执行。
            </p>
          </div>
        </Card>
      </div>

      <div class="lg:col-span-2">
        <Card title="最近任务">
          <div v-if="!schedulerStatus?.recent?.length" class="py-6 text-center text-xs text-[#646262]">
            暂无运行记录 — 点击「手动运行」或等待定时调度
          </div>
          <ScrollArea v-else class="max-h-[300px]">
            <table class="w-full text-sm">
              <thead>
                <tr class="text-left text-xs text-[#646262]">
                  <th class="py-1.5 pr-2 font-normal">任务</th>
                  <th class="py-1.5 pr-2 font-normal">状态</th>
                  <th class="py-1.5 pr-2 font-normal">触发</th>
                  <th class="py-1.5 pr-2 font-normal">时间</th>
                  <th class="py-1.5 font-normal">详情</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(job, i) in schedulerStatus?.recent" :key="i" class="border-t border-[#f1eeee] align-top">
                  <td class="py-2 pr-2 text-[13px] text-[#201d1d]">{{ jobLabels[job.job_name] ?? job.job_name }}</td>
                  <td class="py-2 pr-2"><Badge :variant="jobStatusBadge[job.status] ?? 'default'">{{ job.status }}</Badge></td>
                  <td class="py-2 pr-2 text-xs text-[#646262]">{{ job.trigger === 'schedule' ? '定时' : '手动' }}</td>
                  <td class="py-2 pr-2 text-xs font-mono text-[#646262]">{{ fmtJobTime(job.started_at) }}</td>
                  <td class="py-2 text-xs font-mono text-[#646262] max-w-[340px] truncate" :title="job.detail">{{ job.detail || '—' }}</td>
                </tr>
              </tbody>
            </table>
          </ScrollArea>
        </Card>
      </div>
    </div>

    <!-- 分析溯源 -->
    <div class="mt-4">
      <Card title="分析溯源 (Provenance)">
        <div class="flex items-center justify-between mb-2 gap-2 flex-wrap">
          <p class="text-xs text-[#646262]">
            每次因子/回测/组合计算记录 universe、复权、参数等，保证任何数字可复现
          </p>
          <div class="flex items-center gap-2">
            <Select
              v-model="provKind"
              :options="[
                { value: '', label: '全部类型' },
                { value: 'factor', label: '因子' },
                { value: 'backtest', label: '回测' },
              ]"
              class="w-[130px]"
            />
          </div>
        </div>
        <div v-if="!provenanceData?.length" class="py-5 text-center text-xs text-[#646262]">
          暂无溯源记录 — 因子重算/回测后自动写入
        </div>
        <ScrollArea v-else class="max-h-[320px]">
          <Table :columns="provenanceColumns" :data-source="provenanceData" row-key="id">
            <template #cell-entity_name="{ value, record }">
              <div class="flex flex-col gap-0.5">
                <span class="text-[13px] text-[#201d1d]">{{ value || record?.entity_id || '—' }}</span>
                <span v-if="record?.params_json && Object.keys(record.params_json).length" class="text-[11px] font-mono text-[#646262] truncate max-w-[240px]" :title="JSON.stringify(record.params_json)">
                  {{ JSON.stringify(record.params_json) }}
                </span>
              </div>
            </template>
            <template #cell-created_at="{ value }">
              <span class="text-xs font-mono text-[#646262]">{{ fmtJobTime(value as number | null) }}</span>
            </template>
          </Table>
        </ScrollArea>
      </Card>
    </div>

    <!-- 质量检查结果对话框 -->
    <Dialog :open="qualityOpen" title="数据质量检查结果" @close="qualityOpen = false">
      <div v-if="qualityMutation.data.value" class="space-y-3">
        <div class="flex items-center gap-2">
          <Badge :variant="qualityMutation.data.value.passed ? 'success' : 'warning'">
            {{ qualityMutation.data.value.passed ? '通过' : '存在问题' }}
          </Badge>
          <span v-if="qualityMutation.data.value.summary" class="text-xs text-[#646262]">
            {{ qualityMutation.data.value.summary }}
          </span>
        </div>
        <ul
          v-if="qualityMutation.data.value.issues && qualityMutation.data.value.issues.length > 0"
          class="space-y-1"
        >
          <li
            v-for="(issue, i) in qualityMutation.data.value.issues"
            :key="i"
            class="text-xs text-[#ff3b30] flex items-start gap-1"
          >
            <span class="mt-0.5">•</span>
            <span>{{ issue }}</span>
          </li>
        </ul>
      </div>
      <div v-else class="flex items-center justify-center py-4 gap-2 text-[#646262]">
        <Loader2 :size="14" class="animate-spin" />
        检查中...
      </div>
    </Dialog>
  </div>
</template>
