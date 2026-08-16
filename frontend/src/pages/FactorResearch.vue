<script setup lang="ts">
import { computed, ref } from 'vue'
import { Tabs, Card, Button, VChart } from '@/components/ui'
import type { TabItem } from '@/components/ui'
import { Layers, Trash2 } from 'lucide-vue-next'
import FactorBuilder from '@/components/factor/FactorBuilder.vue'
import FactorLibrary from '@/components/factor/FactorLibrary.vue'
import FactorPool from '@/components/factor/FactorPool.vue'
import FactorScan from '@/components/factor/FactorScan.vue'
import SystemResourceMonitor from '@/components/factor/SystemResourceMonitor.vue'
import ComprehensiveReport from '@/components/factor/ComprehensiveReport.vue'
import AlphaLensReport from '@/components/factor/AlphaLensReport.vue'
import IntradayFactor from '@/components/factor/IntradayFactor.vue'
import type { FactorResult, FactorReport, AlphaLensReport as AlphaLensReportT } from '@/components/factor/types'

// 页级主 tab：因子研究 | 因子库
const pageTabs: TabItem[] = [
  { key: 'research', label: '因子研究' },
  { key: 'intraday', label: '分钟因子 · 日内高频' },
  { key: 'library', label: '因子库' },
]

// 因子库子 tab
const libraryTabs: TabItem[] = [
  { key: 'preset', label: '预置因子' },
  { key: 'scan', label: '批量扫描' },
  { key: 'pool', label: '因子池' },
  { key: 'custom', label: '自建因子' },
]

type FactorMatrix = Record<string, Record<string, number>>

interface CorrData {
  names: string[]
  matrix: number[][]
}

interface CombinedPanelResponse {
  dates?: string[]
  stocks?: string[]
  preview_stocks?: string[]
  panel_token?: string
  panel_mode?: 'inline' | 'artifact'
  factor_data?: FactorMatrix
  return_data?: FactorMatrix
  preview?: { factor_data?: FactorMatrix; return_data?: FactorMatrix }
}

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => null)
    throw new Error(data?.detail ?? `接口错误 (HTTP ${res.status})`)
  }
  return res.json()
}

const pageTab = ref('research')
const libraryTab = ref('preset')
const evaluating = ref(false)
const evalError = ref<string | null>(null)
const nGroups = ref(5)

// 全部来自后端真实计算，初始为空
const report = ref<FactorReport | null>(null)
const corrData = ref<CorrData | null>(null)
const computedFactors = ref<Record<string, FactorResult>>({})
const currentFactor = ref<string | null>(null)

// AlphaLens（按需运行，比综合报告重）：记住当前因子数据供单独调用
const alReport = ref<AlphaLensReportT | null>(null)
const alLoading = ref(false)
const alError = ref<string | null>(null)
const lastEntry = ref<FactorResult | null>(null)

const factorNames = computed(() => Object.keys(computedFactors.value))

/** 对指定因子执行完整评估。全市场 artifact 模式只传 token；小样本兼容矩阵传输。 */
async function evaluate(
  name: string,
  entry: FactorResult,
  allFactors: Record<string, FactorResult>,
  groups: number,
) {
  evaluating.value = true
  evalError.value = null
  try {
    const rep = await postJson<FactorReport>('/api/factor/analysis', {
      factor_data: entry.panelMode === 'artifact' ? {} : entry.values,
      return_data: entry.panelMode === 'artifact' ? {} : entry.returnData,
      factor_token: entry.panelMode === 'artifact' ? entry.factorToken : '',
      return_token: entry.panelMode === 'artifact' ? entry.returnToken : '',
      n_groups: groups,
    })
    report.value = rep
    lastEntry.value = entry
    alReport.value = null
    alError.value = null

    const names = Object.keys(allFactors)
    if (names.length >= 2) {
      const allArtifact = names.every((n) => allFactors[n].factorToken)
      const cRes = await postJson<{
        matrix: Record<string, Record<string, number>>
        factor_names: string[]
      }>('/api/factor/correlation', allArtifact
        ? { factors: {}, factor_tokens: Object.fromEntries(names.map((n) => [n, allFactors[n].factorToken])) }
        : { factors: Object.fromEntries(names.map((n) => [n, allFactors[n].values])) })
      const cNames = cRes.factor_names
      corrData.value = { names: cNames, matrix: cNames.map((a) => cNames.map((b) => cRes.matrix[a]?.[b] ?? 0)) }
    } else {
      corrData.value = null
    }
    currentFactor.value = name
  } catch (e) {
    evalError.value =
      e instanceof TypeError
        ? '无法连接后端服务 (http://localhost:8000)，请先运行 make dev 或 make dev-backend'
        : e instanceof Error
          ? e.message
          : String(e)
  } finally {
    evaluating.value = false
  }
}

/** 按需运行 AlphaLens 分析（复用当前因子值与收益；因子研究页无行业数据，不传 sector_map） */
async function runAlphaLens() {
  const entry = lastEntry.value
  if (!entry) return
  alLoading.value = true
  alError.value = null
  try {
    alReport.value = await postJson<AlphaLensReportT>('/api/factor/alphalens', {
      factor_data: entry.panelMode === 'artifact' ? {} : entry.values,
      return_data: entry.panelMode === 'artifact' ? {} : entry.returnData,
      factor_token: entry.panelMode === 'artifact' ? entry.factorToken : '',
      return_token: entry.panelMode === 'artifact' ? entry.returnToken : '',
      periods: [1, 5, 10],
      quantiles: nGroups.value,
    })
  } catch (e) {
    alError.value = e instanceof Error ? e.message : String(e)
  } finally {
    alLoading.value = false
  }
}

async function handleFactorComputed(result: FactorResult) {
  const factors = { ...computedFactors.value, [result.name]: result }
  computedFactors.value = factors
  await evaluate(result.name, result, factors, nGroups.value)
}

/** 切换分层组数后重新评估当前因子 */
async function handleGroupsChange(groups: number) {
  nGroups.value = groups
  const cf = currentFactor.value
  const entry = cf ? computedFactors.value[cf] : null
  if (cf && entry) await evaluate(cf, entry, computedFactors.value, groups)
}

/** 点击已计算因子 → 重新评估该因子 */
async function handleSelectFactor(name: string) {
  const entry = computedFactors.value[name]
  if (!entry) return
  await evaluate(name, entry, computedFactors.value, nGroups.value)
}

function handleRemoveFactor(name: string) {
  const next = { ...computedFactors.value }
  delete next[name]
  computedFactors.value = next
  if (currentFactor.value === name) {
    currentFactor.value = null
    report.value = null
  }
}

/** 多因子等权合成（后端 /api/factor/combine），并将合成结果作为新因子评估 */
async function handleCombine() {
  const names = Object.keys(computedFactors.value)
  if (names.length < 2) return
  const first = computedFactors.value[names[0]]
  const allArtifact = names.every((n) => computedFactors.value[n].factorToken)
  evaluating.value = true
  evalError.value = null
  try {
    const data = await postJson<CombinedPanelResponse>('/api/factor/combine', allArtifact
      ? { factors: {}, factor_tokens: Object.fromEntries(names.map((n) => [n, computedFactors.value[n].factorToken])) }
      : { factors: Object.fromEntries(names.map((n) => [n, computedFactors.value[n].values])) })
    const name = `合成因子(${names.length})`
    const combined: FactorResult = {
      name,
      dates: data.dates ?? first.dates,
      stocks: data.stocks ?? first.stocks,
      previewStocks: data.preview_stocks ?? data.stocks ?? first.previewStocks,
      values: data.panel_mode === 'artifact' ? {} : (data.factor_data ?? {}),
      returnData: first.returnData,
      factorToken: data.panel_token,
      returnToken: first.returnToken ?? data.panel_token,
      panelToken: data.panel_token,
      panelMode: data.panel_mode,
    }
    const factors = { ...computedFactors.value, [name]: combined }
    computedFactors.value = factors
    await evaluate(name, combined, factors, nGroups.value)
  } catch (e) {
    evalError.value = e instanceof Error ? e.message : String(e)
  } finally {
    evaluating.value = false
  }
}

const corrOption = computed(() => {
  const cd = corrData.value
  if (!cd) return null
  return {
    tooltip: {
      position: 'top' as const,
      formatter: (params: { value: number[] }) => {
        const [x, y, val] = params.value
        return `${cd.names[y]} vs ${cd.names[x]}: ${val}`
      },
    },
    grid: { top: 10, right: 80, bottom: 60, left: 80 },
    xAxis: {
      type: 'category' as const,
      data: cd.names,
      splitArea: { show: true },
      axisLabel: { color: '#646262', fontSize: 11 },
      axisLine: { lineStyle: { color: '#d8d4d4' } },
    },
    yAxis: {
      type: 'category' as const,
      data: cd.names,
      splitArea: { show: true },
      axisLabel: { color: '#646262', fontSize: 11 },
      axisLine: { lineStyle: { color: '#d8d4d4' } },
    },
    visualMap: {
      min: -1,
      max: 1,
      calculable: true,
      orient: 'vertical' as const,
      right: 0,
      top: 'center' as const,
      inRange: { color: ['#ff3b30', '#f1eeee', '#30d158'] },
      textStyle: { color: '#646262' },
    },
    series: [
      {
        name: '相关性',
        type: 'heatmap' as const,
        data: cd.matrix.flatMap((row, i) => row.map((val, j) => [i, j, val])),
        label: {
          show: true,
          color: '#201d1d',
          fontSize: 11,
          formatter: (params: { value: number[] }) => params.value[2].toFixed(2),
        },
        emphasis: { itemStyle: { borderColor: '#646262', borderWidth: 1 } },
      },
    ],
  }
})
</script>

<template>
  <!-- 整页滚动：内容自然高度，滚动由外层 Layout main 承接（避免双层滚动条） -->
  <div class="flex flex-col gap-4">
    <div class="flex items-center justify-between">
      <h1 class="text-xl font-semibold text-[#201d1d]">因子研究</h1>
      <Tabs :items="pageTabs" :active-key="pageTab" @change="(k) => (pageTab = k)" />
    </div>

    <!-- ============ 分钟因子 · 日内高频 ============ -->
    <div v-if="pageTab === 'intraday'">
      <IntradayFactor />
    </div>

    <!-- ============ 因子库 ============ -->
    <div
      v-else-if="pageTab === 'library'"
      class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] p-4"
    >
      <div class="mb-3 flex items-center justify-between">
        <h2 class="text-base font-bold text-[#201d1d]">因子库</h2>
        <Tabs :items="libraryTabs" :active-key="libraryTab" @change="(k) => (libraryTab = k)" />
      </div>
      <FactorLibrary v-if="libraryTab === 'preset'" />
      <FactorScan v-else-if="libraryTab === 'scan'" />
      <FactorPool v-else-if="libraryTab === 'pool'" />
      <div
        v-else
        class="flex h-[200px] items-center justify-center rounded-[4px] border border-[rgba(15,0,0,0.12)]"
      >
        <span class="text-xs text-[#646262]">自建因子功能开发中...</span>
      </div>
    </div>

    <!-- ============ 因子研究 ============ -->
    <template v-else>
      <!-- 已计算因子 + 分层组数 + 合成 -->
      <div class="flex flex-wrap items-center gap-2 rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-3 py-2">
        <span class="text-xs text-[#646262]">已计算因子:</span>
        <span v-if="factorNames.length === 0" class="font-mono text-xs text-[#9a9898]">
          （暂无 — 在左下构建并计算）
        </span>
        <span
          v-for="name in factorNames"
          :key="name"
          class="group inline-flex cursor-pointer items-center gap-1 rounded-[4px] border px-2 py-0.5 font-mono text-xs transition-colors"
          :class="
            currentFactor === name
              ? 'border-[#007aff] bg-[#007aff]/10 text-[#007aff]'
              : 'border-[rgba(15,0,0,0.12)] text-[#646262] hover:text-[#201d1d]'
          "
          title="点击评估该因子"
          @click="handleSelectFactor(name)"
        >
          {{ name }}
          <button
            class="cursor-pointer text-[#9a9898] opacity-0 transition-opacity hover:text-[#ff3b30] group-hover:opacity-100"
            title="移除"
            @click.stop="handleRemoveFactor(name)"
          >
            <Trash2 :size="11" />
          </button>
        </span>
        <div class="ml-auto flex items-center gap-2">
          <span class="text-xs text-[#646262]">分层组数:</span>
          <button
            v-for="g in [3, 5, 10]"
            :key="g"
            :disabled="evaluating"
            class="cursor-pointer rounded-[4px] border px-2 py-0.5 font-mono text-xs transition-colors disabled:opacity-50"
            :class="
              nGroups === g
                ? 'border-[#007aff] bg-[#007aff]/10 text-[#007aff]'
                : 'border-[rgba(15,0,0,0.12)] text-[#646262] hover:text-[#201d1d]'
            "
            @click="handleGroupsChange(g)"
          >
            {{ g }}组
          </button>
          <Button
            variant="secondary"
            size="sm"
            :disabled="factorNames.length < 2 || evaluating"
            class="flex items-center gap-1 text-xs"
            @click="handleCombine"
          >
            <Layers :size="12" />
            等权合成
          </Button>
        </div>
      </div>

      <div
        v-if="evalError"
        class="rounded-[4px] border border-[#ff3b30] bg-[#ff3b30]/10 px-3 py-2 font-mono text-xs text-[#ff3b30]"
      >
        {{ evalError }}
      </div>

      <!-- 上排：左=因子基本数据与操作 / 右=系统资源 -->
      <div class="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div class="lg:col-span-2">
          <FactorBuilder @factor-computed="handleFactorComputed" />
        </div>
        <Card class="lg:col-span-1">
          <SystemResourceMonitor />
        </Card>
      </div>

      <!-- 下方：全宽综合报告 -->
      <Card>
        <ComprehensiveReport :report="report" :factor-name="currentFactor" :loading="evaluating" />
        <div v-if="corrData && corrOption" class="mt-4 border-t border-[rgba(15,0,0,0.08)] pt-4">
          <div class="mb-2 text-xs font-semibold text-[#201d1d]">
            因子 相关性（{{ corrData.names.length }} 个因子）
          </div>
          <div class="rounded-[4px] border border-[rgba(15,0,0,0.12)] p-2">
            <VChart :option="corrOption" :height="360" />
          </div>
        </div>
      </Card>

      <!-- AlphaLens 分析（按需，与自研综合报告互补） -->
      <Card>
        <div class="mb-3 flex items-center justify-between">
          <div>
            <span class="text-sm font-semibold text-[#201d1d]">AlphaLens 分析</span>
            <span class="ml-2 text-[11px] text-[#9a9898]">业界标准 alphalens-reloaded：分层/因子加权多空/换手率等</span>
          </div>
          <Button
            variant="secondary"
            :loading="alLoading"
            :disabled="!report || alLoading"
            @click="runAlphaLens"
          >
            {{ alReport ? '重新运行 AlphaLens' : '运行 AlphaLens 分析' }}
          </Button>
        </div>
        <div v-if="alError" class="mb-2 rounded-[4px] border border-[#ff9f0a]/50 bg-[#ff9f0a]/10 px-3 py-2 text-xs text-[#8a5a00]">
          {{ alError }}
        </div>
        <AlphaLensReport
          v-if="alReport || alLoading"
          :report="alReport"
          :factor-name="currentFactor"
          :loading="alLoading"
        />
        <div v-else class="py-6 text-center text-xs text-[#9a9898]">
          {{ report ? '点击右上「运行 AlphaLens 分析」获取行业分组 IC / 分层收益 / 因子加权多空等报告' : '请先在左上构建并计算因子' }}
        </div>
      </Card>
    </template>
  </div>
</template>
