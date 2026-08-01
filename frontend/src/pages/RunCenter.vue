<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { Play, Square, GitBranch, ChevronRight, Loader2, Pencil } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import { Card, Badge, Button, VChart } from '@/components/ui'
import { useWorkflows } from '@/composables/useWorkflow'
import type { BacktestRun, BacktestRunDetail } from '@/components/qube/types'
import { fmtNum, fmtPct, jsonFetch } from '@/components/qube/types'

interface RunRecord {
  id: string
  workflow_id: string
  status: string
  started_at: number
  finished_at: number | null
  logs: Array<{ time?: string; level?: string; message?: string } | string>
}

interface LogLine {
  time: string
  type: string
  text: string
}

const statusVariant: Record<string, 'success' | 'warning' | 'error' | 'default'> = {
  success: 'success',
  completed: 'success',
  running: 'warning',
  failed: 'error',
}

function formatTs(ts: number | null) {
  if (!ts) return '-'
  return new Date(ts * 1000).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

const eventLabels: Record<string, string> = {
  execution_order: '执行顺序',
  node_start: '节点开始',
  node_complete: '节点完成',
  node_failed: '节点失败',
  workflow_complete: '运行完成',
  workflow_failed: '运行失败',
}

const eventColors: Record<string, string> = {
  node_start: '#007aff',
  node_complete: '#30d158',
  node_failed: '#ff3b30',
  workflow_complete: '#30d158',
  workflow_failed: '#ff3b30',
}

/** 运行中心：选择工作流实际运行，实时查看进度日志与历史运行记录 */
const router = useRouter()
const queryClient = useQueryClient()
const { data: workflows, isLoading } = useWorkflows('my', '')
const selectedId = ref<string | null>(null)
const running = ref(false)
const logs = ref<LogLine[]>([])
let abortController: AbortController | null = null

const { data: runs } = useQuery<RunRecord[]>({
  queryKey: ['workflow-runs', selectedId],
  queryFn: () => fetch(`/api/workflow/${selectedId.value}/runs`).then((r) => r.json()),
  enabled: computed(() => !!selectedId.value),
})

function appendLog(type: string, text: string) {
  const time = new Date().toLocaleTimeString('zh-CN', { hour12: false })
  logs.value = [...logs.value, { time, type, text }]
}

function selectWorkflow(id: string) {
  selectedId.value = id
  logs.value = []
}

async function handleRun() {
  if (!selectedId.value || running.value) return
  logs.value = []
  running.value = true
  const controller = new AbortController()
  abortController = controller
  appendLog('info', '开始运行工作流...')

  try {
    const response = await fetch(`/api/workflow/${selectedId.value}/run/stream`, {
      method: 'POST',
      signal: controller.signal,
      headers: { Accept: 'text/event-stream' },
    })
    if (!response.ok || !response.body) {
      throw new Error(`运行失败 (HTTP ${response.status})`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const blocks = buffer.split('\n\n')
      buffer = blocks.pop() || ''

      for (const block of blocks) {
        if (!block.trim()) continue
        let eventType = ''
        let dataStr = ''
        for (const line of block.split('\n')) {
          if (line.startsWith('event: ')) eventType = line.slice(7).trim()
          else if (line.startsWith('data: ')) dataStr += (dataStr ? '\n' : '') + line.slice(6)
        }
        if (!eventType) continue

        try {
          const data = dataStr ? JSON.parse(dataStr) : {}
          const label = eventLabels[eventType] || eventType
          const detail =
            data.node_title || data.node_name || data.node_uuid
              ? ` — ${data.node_title || data.node_name || data.node_uuid}`
              : ''
          const error = data.error ? ` (${data.error})` : ''
          appendLog(eventType, `${label}${detail}${error}`)
        } catch {
          appendLog(eventType, eventLabels[eventType] || eventType)
        }
      }
    }
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      appendLog('info', '已手动停止')
    } else {
      appendLog('workflow_failed', err instanceof Error ? err.message : '运行出错')
    }
  } finally {
    running.value = false
    abortController = null
    queryClient.invalidateQueries({ queryKey: ['workflow-runs', selectedId] })
  }
}

function handleStop() {
  abortController?.abort()
}

// —— 顶层 Tab：工作流运行 / 策略回测记录 ————————————————————
const topTab = ref<'workflow' | 'backtest'>('workflow')

// 策略回测记录（backtest_runs，QUBE 画板与此处共用同一批落库数据）
const btRuns = ref<BacktestRun[]>([])
const btDetail = ref<BacktestRunDetail | null>(null)
const btLoading = ref(false)

async function loadBtRuns() {
  btLoading.value = true
  try {
    const d = await jsonFetch('/api/backtest/runs?limit=100')
    btRuns.value = d.runs
    if (btRuns.value.length && !btDetail.value) await openBtRun(btRuns.value[0].id)
  } finally {
    btLoading.value = false
  }
}

async function openBtRun(id: string) {
  btDetail.value = await jsonFetch(`/api/backtest/runs/${id}`)
}

function switchTop(t: 'workflow' | 'backtest') {
  topTab.value = t
  if (t === 'backtest' && !btRuns.value.length) loadBtRuns()
}

const btEquityOption = computed(() => {
  const eq = btDetail.value?.equity
  if (!eq?.length) return null
  return {
    grid: { left: 60, right: 12, top: 12, bottom: 22 },
    tooltip: { trigger: 'axis', valueFormatter: (v: number) => Number(v).toFixed(0) },
    xAxis: { type: 'category', data: eq.map((p) => p.ts), axisLabel: { fontSize: 9, color: '#646262' } },
    yAxis: {
      type: 'value',
      scale: true,
      axisLabel: { fontSize: 9, color: '#646262' },
      splitLine: { lineStyle: { color: 'rgba(15,0,0,0.06)' } },
    },
    series: [
      {
        type: 'line',
        showSymbol: false,
        data: eq.map((p) => p.equity),
        lineStyle: { width: 1.4, color: '#201d1d' },
        itemStyle: { color: '#201d1d' },
      },
    ],
  }
})

const BT_METRICS: [string, string, 'pct' | 'num' | 'int'][] = [
  ['total_return', '总收益', 'pct'],
  ['annual_return', '年化', 'pct'],
  ['max_drawdown', '最大回撤', 'pct'],
  ['sharpe_ratio', '夏普', 'num'],
  ['trade_count', '交易笔数', 'int'],
]

function btMetric(key: string, fmt: string): string {
  const v = btDetail.value?.metrics?.[key]
  if (typeof v !== 'number') return '-'
  if (fmt === 'pct') return fmtPct(v)
  if (fmt === 'int') return String(Math.round(v))
  return fmtNum(v, 2)
}

onMounted(loadBtRuns)
</script>

<template>
  <div class="flex flex-col h-full">
    <div class="mb-4">
      <h1 class="text-xl font-semibold text-[#201d1d] mb-1">回测记录与运行中心</h1>
      <p class="text-[13px] text-[#646262]">
        运行已编排的工作流，或查看 QUBE / 策略库产生的策略回测记录
      </p>
    </div>

    <!-- 顶层 Tab -->
    <div class="mb-3 flex gap-1 border-b border-[rgba(15,0,0,0.12)]">
      <button
        v-for="t in [
          { k: 'workflow', l: '工作流运行' },
          { k: 'backtest', l: '策略回测记录' },
        ]"
        :key="t.k"
        class="border-b-2 px-3 py-1.5 text-[13px]"
        :class="
          topTab === t.k
            ? 'border-[#201d1d] font-medium text-[#201d1d]'
            : 'border-transparent text-[#646262] hover:text-[#201d1d]'
        "
        @click="switchTop(t.k as 'workflow' | 'backtest')"
      >
        {{ t.l }}
      </button>
    </div>

    <div v-show="topTab === 'workflow'" class="grid flex-1 min-h-0 grid-cols-1 gap-4 lg:grid-cols-3">
      <!-- 左侧：工作流列表 -->
      <Card title="选择工作流" class="flex flex-col min-h-0 overflow-hidden">
        <div class="flex-1 overflow-y-auto -mx-1 px-1">
          <p v-if="isLoading" class="py-4 text-center text-xs text-[#646262]">加载中...</p>
          <div v-if="!isLoading && (!workflows || workflows.length === 0)" class="py-8 text-center">
            <p class="mb-2 text-xs text-[#646262]">还没有工作流</p>
            <Button variant="secondary" size="sm" @click="router.push('/workflow')">去创建</Button>
          </div>
          <div
            v-for="wf in workflows"
            :key="wf.id"
            class="mb-1 flex cursor-pointer items-center gap-2 rounded-[4px] px-2 py-2 transition-colors"
            :class="
              selectedId === wf.id
                ? 'bg-[#007aff]/10 text-[#007aff]'
                : 'text-[#201d1d] hover:bg-[#f1eeee]'
            "
            @click="selectWorkflow(wf.id)"
          >
            <GitBranch :size="14" class="shrink-0" />
            <span class="flex-1 truncate text-[13px]">{{ wf.name }}</span>
            <button
              class="cursor-pointer text-[#9a9898] hover:text-[#007aff]"
              title="编辑工作流"
              @click.stop="router.push(`/workflow/${wf.id}`)"
            >
              <Pencil :size="12" />
            </button>
            <ChevronRight :size="14" class="shrink-0 text-[#9a9898]" />
          </div>
        </div>
      </Card>

      <!-- 中间：运行控制 + 实时日志 -->
      <Card title="运行" class="flex flex-col min-h-0 overflow-hidden">
        <div class="mb-3 flex items-center gap-2">
          <Button
            variant="primary"
            size="sm"
            :disabled="!selectedId || running"
            class="flex items-center gap-1"
            @click="handleRun"
          >
            <Loader2 v-if="running" :size="13" class="animate-spin" />
            <Play v-else :size="13" />
            {{ running ? '运行中...' : '运行' }}
          </Button>
          <Button
            variant="secondary"
            size="sm"
            :disabled="!running"
            class="flex items-center gap-1"
            @click="handleStop"
          >
            <Square :size="12" />
            停止
          </Button>
          <span v-if="!selectedId" class="text-xs text-[#9a9898]">请先在左侧选择一个工作流</span>
        </div>

        <div
          class="flex-1 overflow-y-auto rounded-[4px] p-2 font-mono text-xs"
          style="background: #201d1d; min-height: 200px"
        >
          <span v-if="logs.length === 0" class="text-[#9a9898]">运行日志将在这里实时显示</span>
          <div v-for="(log, i) in logs" v-else :key="i" class="mb-0.5 flex gap-2">
            <span class="shrink-0 text-[#9a9898]">{{ log.time }}</span>
            <span :style="{ color: eventColors[log.type] || '#fdfcfc' }">{{ log.text }}</span>
          </div>
        </div>
      </Card>

      <!-- 右侧：历史运行记录 -->
      <Card title="运行历史" class="flex flex-col min-h-0 overflow-hidden">
        <div class="flex-1 overflow-y-auto">
          <p v-if="!selectedId" class="py-4 text-center text-xs text-[#9a9898]">
            选择工作流后显示历史记录
          </p>
          <p v-if="selectedId && (!runs || runs.length === 0)" class="py-4 text-center text-xs text-[#9a9898]">
            暂无运行记录
          </p>
          <div
            v-for="run in runs"
            :key="run.id"
            class="mb-2 rounded-[4px] border border-[rgba(15,0,0,0.12)] p-2"
          >
            <div class="flex items-center justify-between">
              <Badge :variant="statusVariant[run.status] || 'default'">{{ run.status }}</Badge>
              <span class="font-mono text-[11px] text-[#646262]">{{ formatTs(run.started_at) }}</span>
            </div>
            <div class="mt-1 text-[11px] text-[#9a9898]">结束: {{ formatTs(run.finished_at) }}</div>
          </div>
        </div>
      </Card>
    </div>

    <!-- 策略回测记录 -->
    <div v-show="topTab === 'backtest'" class="grid flex-1 min-h-0 grid-cols-1 gap-4 lg:grid-cols-3">
      <!-- 左：回测记录列表 -->
      <Card title="回测记录" class="flex flex-col min-h-0 overflow-hidden">
        <div class="flex-1 overflow-y-auto -mx-1 px-1">
          <p v-if="btLoading" class="py-4 text-center text-xs text-[#646262]">加载中...</p>
          <p v-else-if="!btRuns.length" class="py-8 text-center text-xs text-[#9a9898]">
            暂无回测记录 — 去 QUBE 让 AI 跑回测，或在策略画板运行回测
          </p>
          <div
            v-for="r in btRuns"
            :key="r.id"
            class="mb-1 cursor-pointer rounded-[4px] border p-2 transition-colors"
            :class="
              btDetail?.id === r.id
                ? 'border-[#007aff]/40 bg-[#007aff]/8'
                : 'border-[rgba(15,0,0,0.12)] hover:bg-[#f1eeee]'
            "
            @click="openBtRun(r.id)"
          >
            <div class="flex items-center justify-between gap-2">
              <span class="truncate text-[12px] font-medium text-[#201d1d]">{{ r.strategy_name || '未命名策略' }}</span>
              <Badge :variant="statusVariant[r.status] || 'default'">{{ r.status }}</Badge>
            </div>
            <div class="mt-1 flex items-center gap-2 font-mono text-[10px]">
              <span :style="{ color: (r.metrics?.total_return || 0) >= 0 ? '#c62d23' : '#1d8a3e' }">
                {{ fmtPct(r.metrics?.total_return) }}
              </span>
              <span class="text-[#9a9898]">回撤 {{ fmtPct(r.metrics?.max_drawdown) }}</span>
              <span class="text-[#9a9898]">夏普 {{ fmtNum(r.metrics?.sharpe_ratio, 2) }}</span>
            </div>
            <div class="mt-0.5 text-[10px] text-[#9a9898]">{{ formatTs(r.created_at) }}</div>
          </div>
        </div>
      </Card>

      <!-- 右：回测详情（跨 2 列） -->
      <Card title="回测详情" class="flex flex-col min-h-0 overflow-hidden lg:col-span-2">
        <div v-if="!btDetail" class="flex flex-1 items-center justify-center text-xs text-[#9a9898]">
          选择左侧一条回测记录查看详情
        </div>
        <div v-else class="flex-1 space-y-3 overflow-y-auto">
          <div class="flex items-center gap-2">
            <span class="text-[13px] font-semibold text-[#201d1d]">{{ btDetail.strategy_name || '未命名策略' }}</span>
            <Badge :variant="statusVariant[btDetail.status] || 'default'">{{ btDetail.status }}</Badge>
            <span class="ml-auto font-mono text-[11px] text-[#646262]">#{{ btDetail.id.slice(0, 8) }}</span>
          </div>

          <div v-if="btDetail.status === 'error'" class="rounded-[4px] border border-[#ff3b30]/40 bg-[#ff3b30]/8 px-3 py-2 text-xs text-[#c62d23]">
            {{ btDetail.error }}
          </div>

          <template v-if="btDetail.status === 'done'">
            <div class="grid grid-cols-2 gap-1.5 sm:grid-cols-5">
              <div
                v-for="[key, label, fmt] in BT_METRICS"
                :key="key"
                class="rounded-[4px] border border-[rgba(15,0,0,0.1)] bg-[#fdfcfc] px-2.5 py-2"
              >
                <div class="text-[10px] text-[#9a9898]">{{ label }}</div>
                <div class="mt-0.5 font-mono text-[13px] font-semibold text-[#201d1d]">{{ btMetric(key, fmt) }}</div>
              </div>
            </div>

            <div class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] p-3">
              <div class="mb-2 text-xs font-semibold text-[#201d1d]">净值曲线</div>
              <VChart v-if="btEquityOption" :option="btEquityOption" :height="200" />
            </div>

            <div class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] p-3">
              <div class="mb-2 text-xs font-semibold text-[#201d1d]">交易明细（共 {{ btDetail.trades.length }} 条）</div>
              <div class="max-h-[240px] overflow-auto">
                <table class="w-full min-w-[560px] text-[11px]">
                  <thead>
                    <tr class="sticky top-0 border-b border-[rgba(15,0,0,0.22)] bg-[#fdfcfc] text-left text-[#646262]">
                      <th class="py-1 pr-3 font-medium">时间</th>
                      <th class="py-1 pr-3 font-medium">标的</th>
                      <th class="py-1 pr-3 font-medium">方向</th>
                      <th class="py-1 pr-3 font-medium">价格</th>
                      <th class="py-1 pr-3 font-medium">数量</th>
                      <th class="py-1 font-medium">手续费</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(t, i) in btDetail.trades" :key="i" class="border-b border-[rgba(15,0,0,0.06)]">
                      <td class="py-1 pr-3 font-mono">{{ t.ts }}</td>
                      <td class="py-1 pr-3 font-mono">{{ t.symbol }}</td>
                      <td class="py-1 pr-3 font-medium" :style="{ color: t.side === '买入' ? '#ff3b30' : '#30d158' }">{{ t.side }}</td>
                      <td class="py-1 pr-3 font-mono">{{ t.price }}</td>
                      <td class="py-1 pr-3 font-mono">{{ t.qty }}</td>
                      <td class="py-1 font-mono">{{ t.fee }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </template>
          <div v-else class="flex h-40 items-center justify-center text-xs text-[#646262]">回测进行中…</div>
        </div>
      </Card>
    </div>
  </div>
</template>
