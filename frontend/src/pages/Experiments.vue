<script setup lang="ts">
import { computed, ref } from 'vue'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { GitBranch, FlaskConical, BarChart3, Search, Pencil, Check, X } from 'lucide-vue-next'
import { Card, Badge, Button, Input, Dialog } from '@/components/ui'

interface Experiment {
  id: string
  source: string
  source_id: string
  name: string
  note: string
  tags: string[]
  params: Record<string, unknown>
  metrics: Record<string, unknown>
  status: string
  created_at: number
}

interface CompareResult {
  experiments: Experiment[]
  param_diffs: Record<string, unknown>
  metric_comparison: Record<string, unknown>
}

const sourceIcons: Record<string, typeof GitBranch> = {
  workflow: GitBranch,
  factor: FlaskConical,
  backtest: BarChart3,
  explore: Search,
}

const sourceColors: Record<string, string> = {
  workflow: '#007aff',
  factor: '#30d158',
  backtest: '#ff9f0a',
  explore: '#64d2ff',
}

const statusVariant: Record<string, 'success' | 'warning' | 'error' | 'info' | 'default'> = {
  success: 'success',
  completed: 'success',
  running: 'warning',
  failed: 'error',
  pending: 'default',
}

function formatTime(ts: number) {
  if (!ts) return '-'
  return new Date(ts * 1000).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const queryClient = useQueryClient()
const selected = ref<Set<string>>(new Set())
const compareOpen = ref(false)
const noteEditId = ref<string | null>(null)
const noteText = ref('')

const { data: experimentsData } = useQuery<Experiment[]>({
  queryKey: ['experiments'],
  queryFn: () => fetch('/api/experiment/').then((r) => r.json()),
})
const experiments = computed(() => experimentsData.value ?? [])

const {
  data: compareResult,
  mutate: compareMutate,
  isPending: compareLoading,
} = useMutation<CompareResult, Error, string[]>({
  mutationFn: (ids) =>
    fetch('/api/experiment/compare', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ experiment_ids: ids }),
    }).then((r) => r.json()),
  onSuccess: () => (compareOpen.value = true),
})

const noteMutation = useMutation({
  mutationFn: ({ id, note }: { id: string; note: string }) =>
    fetch(`/api/experiment/${id}/note`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ note }),
    }).then((r) => r.json()),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['experiments'] })
    noteEditId.value = null
  },
})

function toggleSelect(id: string) {
  const next = new Set(selected.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selected.value = next
}

function toggleAll() {
  if (selected.value.size === experiments.value.length) selected.value = new Set()
  else selected.value = new Set(experiments.value.map((e) => e.id))
}

function handleCompare() {
  if (selected.value.size < 2) return
  compareMutate(Array.from(selected.value))
}

function startEditNote(exp: Experiment) {
  noteEditId.value = exp.id
  noteText.value = exp.note || ''
}

function saveNote() {
  if (noteEditId.value) noteMutation.mutate({ id: noteEditId.value, note: noteText.value })
}

function isParamDiff(vals: unknown): boolean {
  const values = Object.values(vals as Record<string, unknown>)
  return values.length > 1 && new Set(values.map((x) => JSON.stringify(x))).size > 1
}

function fmtMetric(v: unknown): string {
  if (v === undefined) return '-'
  return typeof v === 'number' ? v.toFixed(6) : JSON.stringify(v)
}
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-4">
      <div>
        <h1 class="text-xl font-semibold text-[#201d1d] mb-1">实验管理</h1>
        <p class="text-[13px] text-[#646262]">
          自动归档因子评估、策略回测、工作流运行的参数与指标，勾选 2 条以上可横向对比 — 共
          {{ experiments.length }} 条记录
        </p>
      </div>
      <Button variant="primary" size="sm" :disabled="selected.size < 2" @click="handleCompare">
        对比 ({{ selected.size }})
      </Button>
    </div>

    <Card>
      <table class="w-full border-collapse text-sm">
        <thead>
          <tr class="bg-[#f8f7f7]">
            <th class="px-3 py-2 text-left text-xs font-medium text-[#646262]" style="border-bottom: 1px solid rgba(15, 0, 0, 0.12); width: 40px">
              <input
                type="checkbox"
                :checked="selected.size === experiments.length && experiments.length > 0"
                class="accent-[#007aff]"
                @change="toggleAll"
              />
            </th>
            <th class="px-3 py-2 text-left text-xs font-medium text-[#646262]" style="border-bottom: 1px solid rgba(15, 0, 0, 0.12); width: 90px">来源</th>
            <th class="px-3 py-2 text-left text-xs font-medium text-[#646262]" style="border-bottom: 1px solid rgba(15, 0, 0, 0.12)">名称</th>
            <th class="px-3 py-2 text-left text-xs font-medium text-[#646262]" style="border-bottom: 1px solid rgba(15, 0, 0, 0.12); width: 90px">状态</th>
            <th class="px-3 py-2 text-left text-xs font-medium text-[#646262]" style="border-bottom: 1px solid rgba(15, 0, 0, 0.12); width: 120px">时间</th>
            <th class="px-3 py-2 text-left text-xs font-medium text-[#646262]" style="border-bottom: 1px solid rgba(15, 0, 0, 0.12)">关键指标</th>
            <th class="px-3 py-2 text-left text-xs font-medium text-[#646262]" style="border-bottom: 1px solid rgba(15, 0, 0, 0.12)">备注</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="record in experiments"
            :key="record.id"
            class="transition-colors hover:bg-[#f1eeee]"
            style="border-bottom: 1px solid rgba(15, 0, 0, 0.12)"
          >
            <td class="px-3 py-2">
              <input
                type="checkbox"
                :checked="selected.has(record.id)"
                class="accent-[#007aff]"
                @change="toggleSelect(record.id)"
              />
            </td>
            <td class="px-3 py-2">
              <span class="inline-flex items-center gap-1">
                <component
                  :is="sourceIcons[record.source] || Search"
                  :size="13"
                  :style="{ color: sourceColors[record.source] || '#646262' }"
                />
                <span class="text-xs">{{ record.source }}</span>
              </span>
            </td>
            <td class="px-3 py-2">
              <span class="font-medium">{{ record.name || '-' }}</span>
            </td>
            <td class="px-3 py-2">
              <Badge :variant="statusVariant[record.status] || 'default'">{{ record.status }}</Badge>
            </td>
            <td class="px-3 py-2">
              <span class="text-xs text-[#646262]">{{ formatTime(record.created_at) }}</span>
            </td>
            <td class="px-3 py-2">
              <span v-if="!record.metrics || Object.keys(record.metrics).length === 0" class="text-[#9a9898]">-</span>
              <div v-else class="flex gap-2 flex-wrap">
                <span
                  v-for="[k, v] in Object.entries(record.metrics).slice(0, 3)"
                  :key="k"
                  class="text-xs text-[#646262]"
                >
                  {{ k }}:
                  <span class="text-[#201d1d]">{{ typeof v === 'number' ? v.toFixed(4) : String(v) }}</span>
                </span>
              </div>
            </td>
            <td class="px-3 py-2">
              <div v-if="noteEditId === record.id" class="flex items-center gap-1">
                <Input v-model="noteText" placeholder="输入备注..." />
                <button class="text-[#30d158] hover:text-[#28b04a] cursor-pointer" @click="saveNote">
                  <Check :size="14" />
                </button>
                <button class="text-[#646262] hover:text-[#201d1d] cursor-pointer" @click="noteEditId = null">
                  <X :size="14" />
                </button>
              </div>
              <div v-else class="flex items-center gap-1 group">
                <span class="text-xs text-[#646262] truncate max-w-[120px]">{{ record.note || '-' }}</span>
                <button
                  class="opacity-0 group-hover:opacity-100 text-[#646262] hover:text-[#007aff] transition-opacity cursor-pointer"
                  @click="startEditNote(record)"
                >
                  <Pencil :size="12" />
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </Card>

    <!-- 对比对话框 -->
    <Dialog :open="compareOpen" title="实验对比" @close="compareOpen = false">
      <div v-if="compareLoading" class="text-center py-8 text-[#646262]">加载中...</div>
      <div v-else-if="compareResult" class="space-y-4 max-h-[60vh] overflow-auto" style="min-width: 560px">
        <!-- 参数差异 -->
        <div>
          <h3 class="text-sm font-medium text-[#201d1d] mb-2">参数差异</h3>
          <p v-if="Object.keys(compareResult.param_diffs).length === 0" class="text-xs text-[#9a9898]">
            无参数差异
          </p>
          <div v-else class="rounded border border-[rgba(15,0,0,0.12)] overflow-hidden">
            <table class="w-full text-xs">
              <thead>
                <tr class="bg-[#f8f7f7]">
                  <th class="px-2 py-1.5 text-left text-[#646262] font-medium">参数</th>
                  <th
                    v-for="e in compareResult.experiments"
                    :key="e.id"
                    class="px-2 py-1.5 text-left text-[#646262] font-medium truncate max-w-[120px]"
                  >
                    {{ e.name || e.id.slice(0, 8) }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="[key, vals] in Object.entries(compareResult.param_diffs)"
                  :key="key"
                  class="border-t border-[rgba(15,0,0,0.12)]"
                >
                  <td class="px-2 py-1 text-[#007aff] font-mono">{{ key }}</td>
                  <td
                    v-for="e in compareResult.experiments"
                    :key="e.id"
                    class="px-2 py-1 font-mono"
                    :class="isParamDiff(vals) ? 'bg-[#007aff]/10 text-[#007aff]' : 'text-[#201d1d]'"
                  >
                    {{
                      (vals as Record<string, unknown>)[e.id] !== undefined
                        ? JSON.stringify((vals as Record<string, unknown>)[e.id])
                        : '-'
                    }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- 指标对比 -->
        <div>
          <h3 class="text-sm font-medium text-[#201d1d] mb-2">指标对比</h3>
          <p v-if="Object.keys(compareResult.metric_comparison).length === 0" class="text-xs text-[#9a9898]">
            无指标数据
          </p>
          <div v-else class="rounded border border-[rgba(15,0,0,0.12)] overflow-hidden">
            <table class="w-full text-xs">
              <thead>
                <tr class="bg-[#f8f7f7]">
                  <th class="px-2 py-1.5 text-left text-[#646262] font-medium">指标</th>
                  <th
                    v-for="e in compareResult.experiments"
                    :key="e.id"
                    class="px-2 py-1.5 text-left text-[#646262] font-medium truncate max-w-[120px]"
                  >
                    {{ e.name || e.id.slice(0, 8) }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="[key, vals] in Object.entries(compareResult.metric_comparison)"
                  :key="key"
                  class="border-t border-[rgba(15,0,0,0.12)]"
                >
                  <td class="px-2 py-1 text-[#64d2ff] font-medium">{{ key }}</td>
                  <td
                    v-for="e in compareResult.experiments"
                    :key="e.id"
                    class="px-2 py-1 font-mono text-[#201d1d]"
                  >
                    {{ fmtMetric((vals as Record<string, unknown>)[e.id]) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </Dialog>
  </div>
</template>
