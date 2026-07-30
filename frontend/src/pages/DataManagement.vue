<script setup lang="ts">
import { ref } from 'vue'
import { useMutation, useQuery } from '@tanstack/vue-query'
import { Wifi, WifiOff, Database, Download, ShieldCheck, Loader2 } from 'lucide-vue-next'
import { Card, Button, Input, Select, Badge, Dialog } from '@/components/ui'

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
