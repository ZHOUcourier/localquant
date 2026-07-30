<script setup lang="ts">
import { computed, ref } from 'vue'
import { useFactorPool, useRemoveFromPool, useRecalculateFactor } from '@/composables/usePresetFactors'
import type { PresetFactor } from '@/composables/usePresetFactors'
import { ConfirmDialog } from '@/components/ui'

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
    <!-- 顶部栏：计数 + 对比按钮 -->
    <div class="mb-3 flex items-center justify-between">
      <span class="text-xs text-[#646262]">共 {{ factors.length }} 个因子</span>
      <button
        v-if="factors.length >= 2"
        type="button"
        class="rounded-[4px] bg-[#201d1d] px-3 py-1 text-xs font-medium text-[#fdfcfc] transition-colors hover:bg-[#0f0000] cursor-pointer"
        @click="showComparison = !showComparison"
      >
        {{ showComparison ? '[−] 收起对比' : '[+] 对比分析' }}
      </button>
    </div>

    <!-- 因子列表 -->
    <div class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-3">
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
