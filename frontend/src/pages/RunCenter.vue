<script setup lang="ts">
import { computed, ref } from 'vue'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { Play, Square, GitBranch, ChevronRight, Loader2, Pencil } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import { Card, Badge, Button } from '@/components/ui'
import { useWorkflows } from '@/composables/useWorkflow'

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
</script>

<template>
  <div class="flex flex-col h-full">
    <div class="mb-4">
      <h1 class="text-xl font-semibold text-[#201d1d] mb-1">运行中心</h1>
      <p class="text-[13px] text-[#646262]">
        在此实际运行已编排好的工作流，实时查看执行进度与历史运行记录
      </p>
    </div>

    <div class="grid flex-1 min-h-0 grid-cols-1 gap-4 lg:grid-cols-3">
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
  </div>
</template>
