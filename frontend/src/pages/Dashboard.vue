<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useQuery } from '@tanstack/vue-query'
import { ArrowRight } from 'lucide-vue-next'
import { useBackendHealth } from '@/composables/useBackendHealth'

// ── Types ──────────────────────────────────────────────────────────

interface WorkflowItem {
  id: string
  name: string
  description: string
  updated_at: number
}

interface Experiment {
  id: string
  source: string
  name: string
  status: string
  metrics: Record<string, unknown>
  created_at: number
}

interface DataStatus {
  qmt_connected?: boolean
  cache_count?: number
  cache_size?: string
  total_records?: number
  [key: string]: unknown
}

interface PresetFactorResult {
  total: number
  items: unknown[]
  [key: string]: unknown
}

// ── Helpers ────────────────────────────────────────────────────────

function formatTime(ts: number) {
  if (!ts) return '-'
  return new Date(ts * 1000).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function statusBg(status: string) {
  if (status === 'completed') return '#30d15820'
  if (status === 'running') return '#ff9f0a20'
  if (status === 'failed') return '#ff3b3020'
  return '#f8f7f7'
}
function statusColor(status: string) {
  if (status === 'completed') return '#30d158'
  if (status === 'running') return '#cc7f08'
  if (status === 'failed') return '#d70015'
  return '#646262'
}

const router = useRouter()
const { online, checking, version } = useBackendHealth()

// Data fetching
const { data: workflows } = useQuery<WorkflowItem[]>({
  queryKey: ['workflows', 'my', ''],
  queryFn: () => fetch('/api/workflow/?tab=my&search=').then((r) => r.json()),
})
const { data: presetWorkflows } = useQuery<WorkflowItem[]>({
  queryKey: ['workflows', 'preset', ''],
  queryFn: () => fetch('/api/workflow/?tab=preset&search=').then((r) => r.json()),
})
const { data: experiments } = useQuery<Experiment[]>({
  queryKey: ['experiments', 'dashboard'],
  queryFn: () => fetch('/api/experiment/?limit=50').then((r) => r.json()),
})
const { data: dataStatus } = useQuery<DataStatus>({
  queryKey: ['data-status'],
  queryFn: () => fetch('/api/data/status').then((r) => r.json()),
})
const { data: presetFactorData } = useQuery<PresetFactorResult>({
  queryKey: ['preset-factors-count'],
  queryFn: () => fetch('/api/factor/preset?page=1&page_size=1').then((r) => r.json()),
})
const { data: libraryFactors } = useQuery<unknown[]>({
  queryKey: ['factor-library'],
  queryFn: () => fetch('/api/factor/library').then((r) => r.json()),
})

// Derived data
const myWorkflows = computed(() => workflows.value ?? [])
const totalWorkflows = computed(() => myWorkflows.value.length + (presetWorkflows.value?.length ?? 0))
const myWorkflowCount = computed(() => myWorkflows.value.length)
const presetFactorCount = computed(() => presetFactorData.value?.total ?? 0)
const customFactorCount = computed(() => libraryFactors.value?.length ?? 0)
const experimentCount = computed(() => experiments.value?.length ?? 0)
const recentExperiments = computed(() => (experiments.value ?? []).slice(0, 5))
const recentWorkflows = computed(() =>
  [...myWorkflows.value].sort((a, b) => (b.updated_at || 0) - (a.updated_at || 0)).slice(0, 5),
)

// 状态卡数据
const statusCards = computed(() => [
  {
    label: '后端',
    value: checking.value ? '检查中...' : online.value ? `在线 v${version.value ?? ''}` : '离线',
    indicator: checking.value ? undefined : online.value ? 'ok' : 'error',
  },
  {
    label: 'QMT',
    value: dataStatus.value?.qmt_connected ? '已连接' : '未连接',
    indicator: dataStatus.value?.qmt_connected ? 'ok' : 'error',
  },
  {
    label: '缓存',
    value: `${dataStatus.value?.cache_count ?? 0} 品种 / ${dataStatus.value?.cache_size ?? '0 B'}`,
    indicator: dataStatus.value?.cache_count ? 'ok' : undefined,
  },
  {
    label: '记录数',
    value: `${dataStatus.value?.total_records ?? 0} 条`,
    indicator: dataStatus.value?.total_records ? 'ok' : undefined,
  },
])

function indicatorChar(ind?: string) {
  return ind === 'ok' ? '+' : ind === 'error' ? 'x' : '-'
}
function indicatorColor(ind?: string) {
  return ind === 'ok' ? '#30d158' : ind === 'error' ? '#ff3b30' : '#646262'
}

// 内容统计行（含展开态）
const expanded = ref<Record<string, boolean>>({})
function toggleExpand(key: string) {
  expanded.value[key] = !expanded.value[key]
}

const mono =
  'Berkeley Mono, IBM Plex Mono, ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace'
</script>

<template>
  <div class="max-w-[960px] mx-auto">
    <!-- Page title -->
    <div class="mb-8">
      <h1 class="text-base font-bold text-[#201d1d] mb-1" :style="{ fontFamily: mono }">
        [+] 工作台
      </h1>
      <p class="text-sm text-[#646262]" :style="{ fontFamily: mono }">LocalQuant 本地投研平台</p>
    </div>

    <!-- ── 系统状态概览 ─────────────────────────────────────────── -->
    <div class="mb-12">
      <div class="mb-3">
        <h2 class="text-base font-bold text-[#201d1d]" :style="{ fontFamily: mono }">系统状态</h2>
        <div class="mt-1" style="border-bottom: 1px solid rgba(15, 0, 0, 0.12)" />
      </div>
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <div
          v-for="card in statusCards"
          :key="card.label"
          class="rounded-[4px] px-4 py-3 card-hover"
          style="background-color: #f1eeee; border: 1px solid rgba(15, 0, 0, 0.12)"
        >
          <div class="flex items-center justify-between">
            <span class="text-sm text-[#646262]" :style="{ fontFamily: mono }">
              [{{ indicatorChar(card.indicator) }}] {{ card.label }}
            </span>
          </div>
          <div class="mt-1 text-base font-medium text-[#201d1d]" :style="{ fontFamily: mono }">
            <span :style="{ color: indicatorColor(card.indicator) }">{{ card.value }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- ── 模块统计 ─────────────────────────────────────────────── -->
    <div class="mb-12">
      <div class="mb-3">
        <h2 class="text-base font-bold text-[#201d1d]" :style="{ fontFamily: mono }">内容统计</h2>
        <div class="mt-1" style="border-bottom: 1px solid rgba(15, 0, 0, 0.12)" />
      </div>
      <div class="rounded-[4px]" style="border: 1px solid rgba(15, 0, 0, 0.12); background-color: #fdfcfc">
        <!-- 工作流 -->
        <div>
          <div class="flex items-center justify-between py-2 px-2 rounded-[4px] transition-colors hover:bg-[#f1eeee]">
            <button
              type="button"
              class="flex items-center gap-2 bg-transparent border-none cursor-pointer p-0"
              :style="{ fontFamily: mono }"
              :title="expanded['wf'] ? '收起' : '展开详情'"
              @click="toggleExpand('wf')"
            >
              <span class="text-sm text-[#646262]">{{ expanded['wf'] ? '[-]' : '[+]' }}</span>
              <span class="text-sm text-[#201d1d]">工作流</span>
            </button>
            <div class="flex items-center gap-2">
              <span class="text-sm text-[#646262]" :style="{ fontFamily: mono }">
                预置 {{ totalWorkflows - myWorkflowCount }} 个，我的 {{ myWorkflowCount }} 个
              </span>
              <button
                type="button"
                class="flex h-5 w-5 items-center justify-center rounded-[4px] text-[#646262] transition-colors hover:bg-[#e8e5e5] hover:text-[#201d1d] bg-transparent border-none cursor-pointer"
                title="进入"
                @click="router.push('/workflow')"
              >
                <ArrowRight :size="13" />
              </button>
            </div>
          </div>
          <div v-if="expanded['wf']" class="px-2 pb-2 pl-8 text-xs text-[#646262] leading-relaxed" :style="{ fontFamily: mono }">
            预置模板 {{ totalWorkflows - myWorkflowCount }} 个·可直接复制为自己的工作流<br />
            我的工作流 {{ myWorkflowCount }} 个·点右侧箭头进入工作流列表
          </div>
        </div>
        <div style="border-bottom: 1px solid rgba(15, 0, 0, 0.12)" />
        <!-- 因子库 -->
        <div>
          <div class="flex items-center justify-between py-2 px-2 rounded-[4px] transition-colors hover:bg-[#f1eeee]">
            <button
              type="button"
              class="flex items-center gap-2 bg-transparent border-none cursor-pointer p-0"
              :style="{ fontFamily: mono }"
              :title="expanded['factor'] ? '收起' : '展开详情'"
              @click="toggleExpand('factor')"
            >
              <span class="text-sm text-[#646262]">{{ expanded['factor'] ? '[-]' : '[+]' }}</span>
              <span class="text-sm text-[#201d1d]">因子库</span>
            </button>
            <div class="flex items-center gap-2">
              <span class="text-sm text-[#646262]" :style="{ fontFamily: mono }">
                预置 {{ presetFactorCount }} 个，自建 {{ customFactorCount }} 个
              </span>
              <button
                type="button"
                class="flex h-5 w-5 items-center justify-center rounded-[4px] text-[#646262] transition-colors hover:bg-[#e8e5e5] hover:text-[#201d1d] bg-transparent border-none cursor-pointer"
                title="进入"
                @click="router.push('/factor')"
              >
                <ArrowRight :size="13" />
              </button>
            </div>
          </div>
          <div v-if="expanded['factor']" class="px-2 pb-2 pl-8 text-xs text-[#646262] leading-relaxed" :style="{ fontFamily: mono }">
            预置因子 {{ presetFactorCount }} 个·支持公式/LaTeX 查看、IC 排序与 AI 分析<br />
            自建因子 {{ customFactorCount }} 个·点右侧箭头进入因子研究
          </div>
        </div>
        <div style="border-bottom: 1px solid rgba(15, 0, 0, 0.12)" />
        <!-- 实验 -->
        <div>
          <div class="flex items-center justify-between py-2 px-2 rounded-[4px] transition-colors hover:bg-[#f1eeee]">
            <button
              type="button"
              class="flex items-center gap-2 bg-transparent border-none cursor-pointer p-0"
              :style="{ fontFamily: mono }"
              :title="expanded['exp'] ? '收起' : '展开详情'"
              @click="toggleExpand('exp')"
            >
              <span class="text-sm text-[#646262]">{{ expanded['exp'] ? '[-]' : '[+]' }}</span>
              <span class="text-sm text-[#201d1d]">实验</span>
            </button>
            <div class="flex items-center gap-2">
              <span class="text-sm text-[#646262]" :style="{ fontFamily: mono }">{{ experimentCount }} 个</span>
              <button
                type="button"
                class="flex h-5 w-5 items-center justify-center rounded-[4px] text-[#646262] transition-colors hover:bg-[#e8e5e5] hover:text-[#201d1d] bg-transparent border-none cursor-pointer"
                title="进入"
                @click="router.push('/experiments')"
              >
                <ArrowRight :size="13" />
              </button>
            </div>
          </div>
          <div v-if="expanded['exp']" class="px-2 pb-2 pl-8 text-xs text-[#646262]" :style="{ fontFamily: mono }">
            共 {{ experimentCount }} 个实验记录·点右侧箭头查看实验列表
          </div>
        </div>
      </div>
    </div>

    <!-- ── 最近活动 ─────────────────────────────────────────────── -->
    <div class="mb-12">
      <div class="mb-3">
        <h2 class="text-base font-bold text-[#201d1d]" :style="{ fontFamily: mono }">最近活动</h2>
        <div class="mt-1" style="border-bottom: 1px solid rgba(15, 0, 0, 0.12)" />
      </div>
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <!-- 最近工作流 -->
        <div>
          <div class="flex items-center justify-between mb-2">
            <span class="text-sm font-medium text-[#201d1d]" :style="{ fontFamily: mono }">工作流</span>
            <button
              class="text-xs text-[#646262] hover:text-[#201d1d] cursor-pointer transition-colors"
              :style="{ fontFamily: mono }"
              @click="router.push('/workflow')"
            >
              查看全部 →
            </button>
          </div>
          <div class="rounded-[4px]" style="border: 1px solid rgba(15, 0, 0, 0.12); background-color: #fdfcfc">
            <div
              v-if="recentWorkflows.length === 0"
              class="py-4 text-center text-sm text-[#646262]"
              :style="{ fontFamily: mono }"
            >
              [-] 暂无工作流
            </div>
            <template v-else>
              <div v-for="(wf, i) in recentWorkflows" :key="wf.id">
                <div
                  class="flex items-center justify-between py-2 px-2 rounded-[4px] cursor-pointer hover:bg-[#f1eeee] transition-colors"
                  @click="router.push(`/workflow/${wf.id}`)"
                >
                  <span class="text-sm text-[#201d1d] truncate mr-3" :style="{ fontFamily: mono }">
                    {{ wf.name || '未命名工作流' }}
                  </span>
                  <span class="text-xs text-[#646262] flex-shrink-0" :style="{ fontFamily: mono }">
                    {{ formatTime(wf.updated_at) }}
                  </span>
                </div>
                <div v-if="i < recentWorkflows.length - 1" style="border-bottom: 1px solid rgba(15, 0, 0, 0.12)" />
              </div>
            </template>
          </div>
        </div>

        <!-- 最近实验 -->
        <div>
          <div class="flex items-center justify-between mb-2">
            <span class="text-sm font-medium text-[#201d1d]" :style="{ fontFamily: mono }">实验</span>
            <button
              class="text-xs text-[#646262] hover:text-[#201d1d] cursor-pointer transition-colors"
              :style="{ fontFamily: mono }"
              @click="router.push('/experiments')"
            >
              查看全部 →
            </button>
          </div>
          <div class="rounded-[4px]" style="border: 1px solid rgba(15, 0, 0, 0.12); background-color: #fdfcfc">
            <div
              v-if="recentExperiments.length === 0"
              class="py-4 text-center text-sm text-[#646262]"
              :style="{ fontFamily: mono }"
            >
              [-] 暂无实验
            </div>
            <template v-else>
              <div v-for="(exp, i) in recentExperiments" :key="exp.id">
                <div
                  class="flex items-center justify-between py-2 px-2 rounded-[4px] cursor-pointer hover:bg-[#f1eeee] transition-colors"
                  @click="router.push('/experiments')"
                >
                  <span class="text-sm text-[#201d1d] truncate mr-3" :style="{ fontFamily: mono }">
                    {{ exp.name || exp.id.slice(0, 8) }}
                  </span>
                  <span class="text-xs text-[#646262] flex-shrink-0 flex items-center gap-2" :style="{ fontFamily: mono }">
                    <span
                      class="text-xs px-1.5 py-0.5 rounded-[4px]"
                      :style="{ backgroundColor: statusBg(exp.status), color: statusColor(exp.status) }"
                    >
                      {{ exp.status }}
                    </span>
                    <span>{{ formatTime(exp.created_at) }}</span>
                  </span>
                </div>
                <div v-if="i < recentExperiments.length - 1" style="border-bottom: 1px solid rgba(15, 0, 0, 0.12)" />
              </div>
            </template>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
