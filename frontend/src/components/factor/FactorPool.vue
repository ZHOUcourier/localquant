<script setup lang="ts">
import { computed, ref } from 'vue'
import { useFactorPool, useRemoveFromPool, useRecalculateFactor } from '@/composables/usePresetFactors'
import type { PresetFactor } from '@/composables/usePresetFactors'
import { ConfirmDialog, Button, VChart } from '@/components/ui'
import { Play, Activity } from 'lucide-vue-next'

/* ── 工具函数 ── */
function fmt(v: number | null, digits = 4): string {
  if (v == null) return '—'
  return v.toFixed(digits)
}
function fmtPct(v: number | null, digits = 2): string {
  if (v == null) return '—'
  return `${(v * 100).toFixed(digits)}%`
}

// 对比分析指标定义
const comparisonMetrics = [
  { label: 'IC_MEAN', key: 'ic_mean', fmt: (v: number | null) => fmt(v) },
  { label: 'RANK_IC', key: 'rank_ic', fmt: (v: number | null) => fmt(v) },
  { label: 'IC_IR', key: 'ic_ir', fmt: (v: number | null) => fmt(v) },
  { label: '年化收益', key: 'annualized_return', fmt: (v: number | null) => fmtPct(v) },
  { label: '最大回撤', key: 'maximum_drawdown', fmt: (v: number | null) => fmtPct(v) },
  { label: '夏普比率', key: 'sharpe_ratio', fmt: (v: number | null) => fmt(v, 2) },
] as const

// 因子池项 IC 指标列
function poolItemMetrics(f: PresetFactor) {
  return [
    { label: 'IC_MEAN', value: fmt(f.ic_mean) },
    { label: 'RANK_IC', value: fmt(f.rank_ic) },
    { label: 'IC_IR', value: fmt(f.ic_ir) },
    { label: 'IC_STD', value: fmt(f.ic_std) },
  ]
}

const { data, isLoading } = useFactorPool()
const removeMutation = useRemoveFromPool()
const recalcMutation = useRecalculateFactor()

const removingId = ref<number | null>(null)
const recalculatingId = ref<number | null>(null)
const showComparison = ref(false)
const removeConfirmId = ref<number | null>(null)

const factors = computed(() => data.value ?? [])

async function handleRemove(id: number) {
  removingId.value = id
  try {
    await removeMutation.mutateAsync(id)
  } catch {
    // 静默处理
  } finally {
    removingId.value = null
    removeConfirmId.value = null
  }
}

async function handleRecalculate(id: number) {
  recalculatingId.value = id
  try {
    await recalcMutation.mutateAsync(id)
  } catch {
    // 静默处理
  } finally {
    recalculatingId.value = null
  }
}

/* ── 构建组合并回测（因子池 → 合成 → Top-N → 回测 → 归因） ── */
const showPortfolio = ref(false)
const pfCombine = ref<'equal' | 'ic_weighted'>('equal')
const pfTopN = ref(20)
const pfStart = ref('')
const pfEnd = ref('')
const pfRunning = ref(false)
const pfError = ref<string | null>(null)
const pfResult = ref<any | null>(null)

interface PortfolioResult {
  ok: boolean
  combine_method: string
  top_n: number
  n_factors: number
  factor_names: string[]
  factor_weights: Record<string, number>
  failed: { factor_name: string; error: string }[]
  equity_curve: Record<string, number>
  tear_sheet: Record<string, number>
  cost_summary: { total_cost: number; breakdown: Record<string, number> }
  attribution: { alpha_cum: number; alpha_annual: number; alpha_ir: number; r2: number; beta: Record<string, number>; contribution: Record<string, number> } | null
  assumptions: string[]
  n_stocks: number
  data_date: string
}

async function runPortfolio() {
  pfRunning.value = true
  pfError.value = null
  pfResult.value = null
  try {
    const res = await fetch('/api/backtest/portfolio', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        factor_ids: [],
        combine_method: pfCombine.value,
        top_n: pfTopN.value,
        start_date: pfStart.value,
        end_date: pfEnd.value,
      }),
    })
    const data = await res.json().catch(() => null)
    if (!res.ok) throw new Error(data?.detail ?? `接口错误 (HTTP ${res.status})`)
    pfResult.value = data as PortfolioResult
  } catch (e) {
    pfError.value = e instanceof Error ? e.message : String(e)
  } finally {
    pfRunning.value = false
  }
}

const pfEquityOption = computed(() => {
  const r = pfResult.value
  if (!r) return null
  const xs = Object.keys(r.equity_curve).sort()
  return {
    grid: { left: 60, right: 12, top: 12, bottom: 22 },
    tooltip: { trigger: 'axis', valueFormatter: (v: number) => Number(v).toFixed(0) },
    xAxis: { type: 'category', data: xs, axisLabel: { color: '#646262', fontSize: 10 } },
    yAxis: { type: 'value', scale: true, axisLabel: { color: '#646262', fontSize: 10 } },
    series: [
      {
        name: '组合净值',
        type: 'line',
        showSymbol: false,
        data: xs.map((d) => r.equity_curve[d]),
        lineStyle: { color: '#007aff', width: 1.5 },
        areaStyle: { color: 'rgba(0,122,255,0.08)' },
      },
    ],
  }
})

function pfPct(v: number | undefined): string {
  return v == null ? '—' : `${(v * 100).toFixed(2)}%`
}
</script>

<template>
  <!-- 空状态 -->
  <div
    v-if="!isLoading && factors.length === 0"
    class="flex h-[200px] items-center justify-center rounded-[4px] border border-[rgba(15,0,0,0.12)]"
  >
    <span class="font-mono text-xs text-[#646262]">因子池为空，请从因子库中添加因子</span>
  </div>

  <!-- 加载中 -->
  <div v-else-if="isLoading" class="flex h-[200px] items-center justify-center">
    <span class="text-xs text-[#646262]">加载中...</span>
  </div>

  <div v-else class="flex flex-col">
    <!-- 顶部栏：计数 + 对比/组合按钮 -->
    <div class="mb-3 flex items-center justify-between">
      <span class="text-xs text-[#646262]">共 {{ factors.length }} 个因子</span>
      <div class="flex items-center gap-2">
        <button
          v-if="factors.length >= 2"
          type="button"
          class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-3 py-1 text-xs font-medium text-[#646262] transition-colors hover:text-[#201d1d] cursor-pointer"
          @click="showComparison = !showComparison"
        >
          {{ showComparison ? '[−] 收起对比' : '[+] 对比分析' }}
        </button>
        <button
          v-if="factors.length >= 2"
          type="button"
          class="flex items-center gap-1 rounded-[4px] bg-[#201d1d] px-3 py-1 text-xs font-medium text-[#fdfcfc] transition-colors hover:bg-[#0f0000] cursor-pointer"
          title="因子池 → 合成 → Top-N 做多 → 回测 → 风格归因（研究主链路一键打通）"
          @click="showPortfolio = !showPortfolio"
        >
          <Play :size="11" />
          {{ showPortfolio ? '收起组合回测' : '构建组合并回测' }}
        </button>
      </div>
    </div>

    <!-- 组合回测面板 -->
    <div
      v-if="showPortfolio && factors.length >= 2"
      class="mb-3 rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] p-3"
    >
      <div class="flex flex-wrap items-center gap-3">
        <span class="text-xs font-medium text-[#201d1d]">构建组合</span>
        <select
          v-model="pfCombine"
          class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-2 py-1 text-xs"
        >
          <option value="equal">等权合成</option>
          <option value="ic_weighted">IC 加权合成（研究参考口径）</option>
        </select>
        <label class="flex items-center gap-1 text-xs text-[#646262]">
          每日做多 Top
          <input v-model.number="pfTopN" type="number" min="1" class="w-14 rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-1.5 py-1 font-mono text-xs" />
          只
        </label>
        <label class="flex items-center gap-1 text-xs text-[#646262]">
          起
          <input v-model="pfStart" type="date" class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-1.5 py-1 text-xs" />
        </label>
        <label class="flex items-center gap-1 text-xs text-[#646262]">
          止
          <input v-model="pfEnd" type="date" class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-1.5 py-1 text-xs" />
        </label>
        <Button variant="primary" size="sm" :loading="pfRunning" @click="runPortfolio">
          <Activity :size="12" class="mr-1" />
          {{ pfRunning ? '回测中...' : '运行回测' }}
        </Button>
        <span class="text-[10px] text-[#9a9898]">
          面板一次加载、全池因子求值；IC 加权权重来自全区间尾部滚动 IC（含未来信息，仅供研究参考）
        </span>
      </div>

      <div v-if="pfError" class="mt-2 rounded-[4px] border border-[#ff9f0a]/40 bg-[#ff9f0a]/8 px-2.5 py-1.5 text-[11px] text-[#8a5a00]">
        {{ pfError }}
      </div>

      <template v-if="pfResult?.ok">
        <!-- 指标 -->
        <div class="mt-3 grid grid-cols-2 gap-1.5 sm:grid-cols-6">
          <div
            v-for="[k, l] in [
              ['total_return', '总收益'],
              ['annual_return', '年化收益'],
              ['sharpe_ratio', '夏普'],
              ['max_drawdown', '最大回撤'],
              ['volatility', '年化波动'],
              ['win_rate', '日胜率'],
            ]"
            :key="k"
            class="rounded-[4px] border border-[rgba(15,0,0,0.08)] bg-[#f8f7f7] px-2 py-1.5"
          >
            <div class="text-[10px] text-[#9a9898]">{{ l }}</div>
            <div class="mt-0.5 font-mono text-[12px] font-semibold text-[#201d1d]">
              {{ ['total_return', 'annual_return', 'max_drawdown', 'volatility', 'win_rate'].includes(k) ? pfPct(pfResult.tear_sheet[k]) : (pfResult.tear_sheet[k] ?? 0).toFixed(2) }}
            </div>
          </div>
        </div>

        <!-- 净值曲线 -->
        <div class="mt-3">
          <VChart v-if="pfEquityOption" :option="pfEquityOption" :height="180" />
        </div>

        <!-- 归因 + 权重 -->
        <div class="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
          <div class="rounded-[4px] border border-[rgba(15,0,0,0.08)] bg-[#f8f7f7] p-2">
            <div class="mb-1 text-[10px] font-medium text-[#9a9898]">风格归因（alpha 是否真实存在）</div>
            <template v-if="pfResult.attribution">
              <div class="flex flex-wrap gap-1.5 text-[11px]">
                <span class="font-mono" :style="{ color: pfResult.attribution.alpha_cum >= 0 ? '#c62d23' : '#1d8a3e' }">
                  Alpha 累计 {{ pfPct(pfResult.attribution.alpha_cum) }}
                </span>
                <span class="font-mono text-[#646262]">年化 {{ pfPct(pfResult.attribution.alpha_annual) }}</span>
                <span class="font-mono text-[#646262]">IR {{ pfResult.attribution.alpha_ir.toFixed(2) }}</span>
                <span class="font-mono text-[#646262]">R² {{ pfResult.attribution.r2.toFixed(2) }}</span>
              </div>
              <div class="mt-1 flex flex-wrap gap-1">
                <span
                  v-for="(v, s) in pfResult.attribution.contribution"
                  :key="String(s)"
                  class="rounded-[3px] border border-[rgba(15,0,0,0.1)] bg-[#fdfcfc] px-1.5 py-0.5 font-mono text-[10px] text-[#646262]"
                >
                  {{ String(s) }} β={{ pfResult.attribution.beta[String(s)].toFixed(2) }} · {{ (v * 100).toFixed(1) }}%
                </span>
              </div>
            </template>
            <div v-else class="text-[10px] text-[#9a9898]">归因不可用（面板/样本不足）</div>
          </div>
          <div class="rounded-[4px] border border-[rgba(15,0,0,0.08)] bg-[#f8f7f7] p-2">
            <div class="mb-1 text-[10px] font-medium text-[#9a9898]">因子权重（{{ pfResult.n_factors }} 个因子）</div>
            <div class="flex flex-wrap gap-1">
              <span
                v-for="(w, name) in pfResult.factor_weights"
                :key="String(name)"
                class="rounded-[3px] border border-[rgba(15,0,0,0.1)] bg-[#fdfcfc] px-1.5 py-0.5 font-mono text-[10px] text-[#646262]"
              >
                {{ String(name) }} · {{ (Math.abs(w) * 100).toFixed(0) }}%
              </span>
            </div>
            <div class="mt-1 text-[10px] text-[#9a9898]">
              {{ pfResult.n_stocks }} 只标的 · 数据截至 {{ pfResult.data_date }} ·
              成本合计 {{ pfResult.cost_summary?.total_cost.toFixed(2) ?? '—' }}
            </div>
          </div>
        </div>

        <div v-if="pfResult.failed?.length" class="mt-2 text-[10px] text-[#cc7f08]">
          求值失败：{{ pfResult.failed.map((f: any) => `${f.factor_name}（${f.error}）`).join('；') }}
        </div>
      </template>
    </div>

    <!-- 因子列表 -->
    <div class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-3">
      <TransitionGroup name="list-fade" tag="div">
        <div
          v-for="f in factors"
          :key="f.id"
          class="flex items-center justify-between gap-3 border-b border-[rgba(15,0,0,0.12)] py-3 last:border-b-0"
        >
        <!-- 左侧：名称 + 分类 + IC 指标 -->
        <div class="flex min-w-0 flex-1 items-center gap-4">
          <span class="shrink-0 text-sm font-medium text-[#201d1d]">{{ f.factor_name }}</span>
          <span class="flex shrink-0 items-center gap-1 text-xs text-[#646262]">
            <span
              class="inline-block h-[6px] w-[6px] rounded-full"
              :style="{ backgroundColor: f.category_color_hex || '#646262' }"
            />
            {{ f.category_name || '未分类' }}
          </span>
          <div class="hidden items-center gap-3 sm:flex">
            <span v-for="m in poolItemMetrics(f)" :key="m.label" class="flex items-center gap-1 text-xs">
              <span class="text-[#9a9898]">{{ m.label }}</span>
              <span class="text-[#201d1d]">{{ m.value }}</span>
            </span>
          </div>
        </div>

        <!-- 右侧：操作按钮 -->
        <div class="flex shrink-0 items-center gap-2">
          <button
            type="button"
            :disabled="recalculatingId === f.id"
            class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2 py-1 text-xs text-[#646262] transition-colors hover:text-[#201d1d] disabled:text-[#9a9898] cursor-pointer"
            title="重算为覆盖更新：新指标直接写回当前因子记录（不另存新因子），旧值自动存入历史快照，可在因子详情中查看"
            @click="handleRecalculate(f.id)"
          >
            {{ recalculatingId === f.id ? '计算中...' : '↻ 重算 IC（覆盖）' }}
          </button>
          <button
            type="button"
            :disabled="removingId === f.id"
            class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2 py-1 text-xs text-[#646262] transition-colors hover:text-[#ff3b30] disabled:text-[#9a9898] cursor-pointer"
            @click="removeConfirmId = f.id"
          >
            {{ removingId === f.id ? '移除中...' : '[−] 移除' }}
          </button>
        </div>
      </div>
      </TransitionGroup>
    </div>

    <!-- 对比分析表格 -->
    <div v-if="showComparison && factors.length >= 2" class="mt-3 rounded-[4px] border border-[rgba(15,0,0,0.12)]">
      <table class="w-full border-collapse text-sm">
        <thead>
          <tr class="bg-[#f8f7f7]">
            <th class="border-b border-[rgba(15,0,0,0.12)] px-3 py-2 text-left text-xs font-medium text-[#646262]">
              指标
            </th>
            <th
              v-for="f in factors"
              :key="f.id"
              class="border-b border-[rgba(15,0,0,0.12)] px-3 py-2 text-left text-xs font-medium text-[#201d1d]"
            >
              {{ f.factor_name }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="m in comparisonMetrics" :key="m.key" class="border-b border-[rgba(15,0,0,0.12)]">
            <td class="px-3 py-2 text-xs text-[#646262]">{{ m.label }}</td>
            <td v-for="f in factors" :key="f.id" class="px-3 py-2 text-xs text-[#201d1d]">
              {{ m.fmt(f[m.key as keyof PresetFactor] as number | null) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 移除确认对话框 -->
    <ConfirmDialog
      :open="removeConfirmId !== null"
      title="[−] 移除因子"
      message="确定要从因子池中移除该因子吗？"
      confirm-text="移除"
      cancel-text="取消"
      variant="danger"
      @confirm="removeConfirmId !== null && handleRemove(removeConfirmId)"
      @cancel="removeConfirmId = null"
    />
  </div>
</template>
