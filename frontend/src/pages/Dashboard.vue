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

/* ── 每日研究简报（/api/ops/briefing 实时聚合） ── */
interface Briefing {
  generated_at: number
  market: {
    ok: boolean
    message?: string
    data_date?: string
    indices?: { name: string; state: string; mom20: number; mom60: number }[]
    style_rotation?: { label: string; strength: number; trend: string }[]
    market_state?: { label: string; n_bull: number; n_bear: number; hv20_avg: number }
  } | null
  factors: {
    pool_n?: number
    stages?: Record<string, number>
    n_with_snapshot?: number
    decaying?: { factor_name: string; stage: string; latest_ic_mean: number; trend_label: string }[]
    error?: string
  } | null
  dividend_events: { code: string; date: string; factor_ratio: number }[]
  data_freshness: { total: number; latest_date: string | null; stale_count: number; calendar: string } | null
  research_readiness: {
    ready: boolean
    n_stocks: number
    n_days: number
    data_start: string | null
    data_end: string | null
    reference_latest: string | null
    fundamental_ready: boolean
    minute_ready: boolean
    qmt_connected: boolean
    blockers: string[]
    warnings: string[]
    error?: string
  } | null
  recent_jobs: { job_name: string; status: string; trigger: string; detail: string }[]
}
const { data: briefing } = useQuery<Briefing>({
  queryKey: ['research-briefing'],
  queryFn: () => fetch('/api/ops/briefing').then((r) => r.json()),
  refetchInterval: 15 * 60 * 1000,
})

const stageColors: Record<string, string> = {
  稳定: 'bg-[#30d158]/15 text-[#248a3d]',
  萌芽: 'bg-[#007aff]/10 text-[#0056b3]',
  观察: 'bg-[#ff9f0a]/15 text-[#cc7f08]',
  衰减: 'bg-[#ff9f0a]/25 text-[#a05a00]',
  失效: 'bg-[#ff3b30]/10 text-[#c62d23]',
  样本不足: 'bg-[#f1eeee] text-[#9a9898]',
}

const briefingTime = computed(() => {
  const ts = briefing.value?.generated_at
  if (!ts) return ''
  return new Date(ts * 1000).toLocaleTimeString('zh-CN', { hour12: false })
})

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
          v-for="(card, i) in statusCards"
          :key="card.label"
          v-motion
          :initial="{ opacity: 0, y: 10 }"
          :enter="{ opacity: 1, y: 0, transition: { delay: i * 45 } }"
          :hovered="{ y: -2, transition: { duration: 120 } }"
          :tapped="{ scale: 0.98, transition: { duration: 90 } }"
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

    <!-- ── 每日研究简报 ─────────────────────────────────────────── -->
    <div class="mb-12">
      <div class="mb-3 flex items-center justify-between">
        <div>
          <h2 class="text-base font-bold text-[#201d1d]" :style="{ fontFamily: mono }">每日研究简报</h2>
          <div class="mt-1" style="border-bottom: 1px solid rgba(15, 0, 0, 0.12)" />
        </div>
        <span v-if="briefingTime" class="text-[10px] text-[#9a9898]" :style="{ fontFamily: mono }">
          更新于 {{ briefingTime }} · 15 分钟自动刷新
        </span>
      </div>

      <div class="grid grid-cols-1 gap-3 lg:grid-cols-2">

        <!-- 研究数据就绪度 -->
        <div
          v-if="briefing?.research_readiness"
          class="rounded-[4px] px-3 py-2.5"
          :style="{
            border: `1px solid ${briefing.research_readiness.ready ? 'rgba(48,209,88,0.35)' : 'rgba(255,159,10,0.45)'}`,
            backgroundColor: briefing.research_readiness.ready ? 'rgba(48,209,88,0.04)' : 'rgba(255,159,10,0.05)',
          }"
        >
          <div class="mb-1.5 flex items-center justify-between">
            <span class="text-[11px] font-medium text-[#646262]" :style="{ fontFamily: mono }">
              研究数据就绪度
            </span>
            <span
              class="rounded-[3px] px-1.5 py-0.5 text-[10px] font-semibold"
              :class="briefing.research_readiness.ready ? 'bg-[#30d158]/15 text-[#248a3d]' : 'bg-[#ff9f0a]/15 text-[#a05a00]'"
            >
              {{ briefing.research_readiness.ready ? '可用于正式研究' : '仅建议方法验证' }}
            </span>
          </div>
          <div v-if="!briefing.research_readiness.error" class="space-y-1">
            <div class="flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] text-[#646262]">
              <span>股票 {{ briefing.research_readiness.n_stocks }} 只</span>
              <span>历史 {{ briefing.research_readiness.n_days }} 交易日</span>
              <span>{{ briefing.research_readiness.data_start ?? '—' }} ~ {{ briefing.research_readiness.data_end ?? '—' }}</span>
            </div>
            <div class="flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] text-[#646262]">
              <span>参考快照 {{ briefing.research_readiness.reference_latest ?? '无' }}</span>
              <span>财务 {{ briefing.research_readiness.fundamental_ready ? '已缓存' : '缺失' }}</span>
              <span>分钟 {{ briefing.research_readiness.minute_ready ? '已缓存' : '缺失' }}</span>
              <span>QMT {{ briefing.research_readiness.qmt_connected ? '已连接' : '未连接' }}</span>
            </div>
            <div v-if="briefing.research_readiness.blockers?.length" class="text-[10px] leading-relaxed text-[#a05a00]">
              <div v-for="(b, i) in briefing.research_readiness.blockers" :key="`b${i}`">✕ {{ b }}</div>
            </div>
            <div v-if="briefing.research_readiness.warnings?.length" class="text-[10px] leading-relaxed text-[#8a5a00]">
              <div v-for="(w, i) in briefing.research_readiness.warnings" :key="`w${i}`">⚠ {{ w }}</div>
            </div>
          </div>
          <div v-else class="py-1 text-[11px] text-[#9a9898]">{{ briefing.research_readiness.error }}</div>
        </div>
        <!-- 市场状态 -->
        <div class="rounded-[4px] px-3 py-2.5" style="border: 1px solid rgba(15, 0, 0, 0.12); background-color: #fdfcfc">
          <div class="mb-1.5 text-[11px] font-medium text-[#646262]" :style="{ fontFamily: mono }">市场环境</div>
          <template v-if="briefing?.market?.ok">
            <div class="flex flex-wrap items-center gap-2">
              <span
                class="rounded-[3px] px-2 py-0.5 text-[11px] font-semibold"
                :class="stageColors[briefing.market.market_state?.label ?? ''] ?? 'bg-[#f1eeee] text-[#646262]'"
              >
                {{ briefing.market.market_state?.label }}
              </span>
              <span class="text-[10px] text-[#646262]">
                {{ briefing.market.market_state?.n_bull }} 偏多 / {{ briefing.market.market_state?.n_bear }} 偏空 ·
                HV20 均值 {{ ((briefing.market.market_state?.hv20_avg ?? 0) * 100).toFixed(0) }}% ·
                数据截至 {{ briefing.market.data_date }}
              </span>
            </div>
            <div class="mt-1.5 flex flex-wrap gap-1">
              <span
                v-for="i in briefing.market.indices"
                :key="i.name"
                class="rounded-[3px] border border-[rgba(15,0,0,0.08)] bg-[#f8f7f7] px-1.5 py-0.5 text-[10px] text-[#646262]"
              >
                {{ i.name }} {{ i.state }} {{ (i.mom20 * 100).toFixed(1)}}
              </span>
              <span
                v-for="s in briefing.market.style_rotation"
                :key="s.label"
                class="rounded-[3px] border border-[rgba(15,0,0,0.08)] bg-[#f8f7f7] px-1.5 py-0.5 text-[10px]"
                :style="{ color: s.strength >= 0 ? '#c62d23' : '#1d8a3e' }"
              >
                {{ s.label }} {{ s.trend }} {{ (Math.abs(s.strength) * 100).toFixed(1) }}%
              </span>
            </div>
          </template>
          <div v-else class="py-2 text-[11px] leading-relaxed text-[#cc7f08]">
            {{ briefing?.market?.message || '加载中...' }}
          </div>
        </div>

        <!-- 因子池体检 -->
        <div class="rounded-[4px] px-3 py-2.5" style="border: 1px solid rgba(15, 0, 0, 0.12); background-color: #fdfcfc">
          <div class="mb-1.5 text-[11px] font-medium text-[#646262]" :style="{ fontFamily: mono }">
            因子池体检（{{ briefing?.factors?.pool_n ?? 0 }} 个因子 · {{ briefing?.factors?.n_with_snapshot ?? 0 }} 个有历史快照）
          </div>
          <template v-if="briefing?.factors && !briefing.factors.error">
            <div class="flex flex-wrap items-center gap-1">
              <span
                v-for="(n, stage) in briefing.factors.stages ?? {}"
                :key="String(stage)"
                class="rounded-[3px] px-1.5 py-0.5 text-[10px] font-medium"
                :class="stageColors[String(stage)] ?? 'bg-[#f1eeee] text-[#9a9898]'"
              >
                {{ String(stage) }} {{ n }}
              </span>
            </div>
            <div v-if="briefing.factors.decaying?.length" class="mt-1.5">
              <div class="text-[10px] text-[#a05a00]">近期衰减/失效：</div>
              <div class="mt-0.5 flex flex-wrap gap-1">
                <span
                  v-for="d in briefing.factors.decaying"
                  :key="d.factor_name"
                  class="rounded-[3px] border border-[rgba(255,159,10,0.3)] bg-[#ff9f0a]/6 px-1.5 py-0.5 text-[10px] text-[#8a5a00]"
                >
                  {{ d.factor_name }} {{ d.trend_label }} IC={{ d.latest_ic_mean.toFixed(4) }}
                </span>
              </div>
            </div>
          </template>
          <div v-else class="py-2 text-[11px] text-[#9a9898]">{{ briefing?.factors?.error || '加载中...' }}</div>
        </div>

        <!-- 除权事件 + 数据时效 -->
        <div class="rounded-[4px] px-3 py-2.5" style="border: 1px solid rgba(15, 0, 0, 0.12); background-color: #fdfcfc">
          <div class="mb-1.5 text-[11px] font-medium text-[#646262]" :style="{ fontFamily: mono }">
            近 7 日除权事件（{{ briefing?.dividend_events?.length ?? 0 }} 起）
          </div>
          <div v-if="briefing?.dividend_events?.length" class="flex flex-wrap gap-1">
            <span
              v-for="e in briefing.dividend_events"
              :key="`${e.code}-${e.date}`"
              class="rounded-[3px] border border-[rgba(15,0,0,0.08)] bg-[#f8f7f7] px-1.5 py-0.5 font-mono text-[10px] text-[#646262]"
            >
              {{ e.code }} {{ e.date }} ×{{ e.factor_ratio.toFixed(3) }}
            </span>
          </div>
          <div v-else class="py-1.5 text-[11px] text-[#9a9898]">
            近 7 日无除权事件（或本地无缓存数据）
          </div>
          <div class="mt-2 border-t border-[rgba(15,0,0,0.06)] pt-1.5 text-[10px] text-[#646262]">
            数据时效：
            <template v-if="briefing?.data_freshness">
              最新交易日 {{ briefing.data_freshness.latest_date ?? '无' }} ·
              {{ briefing.data_freshness.total }} 只缓存 ·
              滞后标的 {{ briefing.data_freshness.stale_count }} 只
              <span class="text-[#9a9898]">
                （{{ briefing.data_freshness.calendar === 'qmt' ? 'QMT 交易日历' : '工作日近似' }}口径）
              </span>
            </template>
            <template v-else>暂无缓存</template>
          </div>
        </div>

        <!-- 最近批处理 -->
        <div class="rounded-[4px] px-3 py-2.5" style="border: 1px solid rgba(15, 0, 0, 0.12); background-color: #fdfcfc">
          <div class="mb-1.5 text-[11px] font-medium text-[#646262]" :style="{ fontFamily: mono }">最近批处理</div>
          <div v-if="briefing?.recent_jobs?.length" class="space-y-0.5">
            <div
              v-for="(j, i) in briefing.recent_jobs.slice(0, 4)"
              :key="i"
              class="flex items-center justify-between gap-2 text-[10px]"
            >
              <span class="truncate text-[#201d1d]">{{ j.job_name }}</span>
              <span class="flex shrink-0 items-center gap-1">
                <span
                  class="rounded-[2px] px-1 py-px text-[9px] font-medium"
                  :class="j.status === 'ok' ? 'bg-[#30d158]/15 text-[#248a3d]' : j.status === 'failed' ? 'bg-[#ff3b30]/10 text-[#c62d23]' : 'bg-[#f1eeee] text-[#9a9898]'"
                >
                  {{ j.status }}
                </span>
              </span>
              <span class="max-w-[45%] truncate text-[#9a9898]" :title="j.detail">{{ j.detail }}</span>
            </div>
          </div>
          <div v-else class="py-1.5 text-[11px] text-[#9a9898]">暂无批处理记录</div>
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
                  v-motion
                  :initial="{ opacity: 0, x: -8 }"
                  :enter="{ opacity: 1, x: 0, transition: { delay: i * 30 } }"
                  :hovered="{ x: 2, transition: { duration: 120 } }"
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
                  v-motion
                  :initial="{ opacity: 0, x: -8 }"
                  :enter="{ opacity: 1, x: 0, transition: { delay: i * 30 } }"
                  :hovered="{ x: 2, transition: { duration: 120 } }"
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
