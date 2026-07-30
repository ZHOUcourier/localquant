<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { Input } from '@/components/ui'
import { Sparkles, BookOpen } from 'lucide-vue-next'
import {
  usePresetFactors,
  usePresetFactorCategories,
  useAddToFactorPool,
} from '@/composables/usePresetFactors'
import type { PresetFactor, PresetFactorParams } from '@/composables/usePresetFactors'
import FactorDetailDialog from './FactorDetailDialog.vue'
import FactorReferenceDialog from './FactorReferenceDialog.vue'

/* ── 工具函数 ── */
function fmt(v: number | null, digits = 4): string {
  if (v == null) return '—'
  return v.toFixed(digits)
}
function fmtPct(v: number | null, digits = 2): string {
  if (v == null) return '—'
  return `${(v * 100).toFixed(digits)}%`
}

type ViewMode = 'card' | 'list'
type SortField = 'rank_ic' | 'ic_mean' | 'ic_ir' | 'annualized_return'

const SORT_OPTIONS: { field: SortField; label: string }[] = [
  { field: 'rank_ic', label: 'RANK_IC' },
  { field: 'ic_mean', label: 'IC_MEAN' },
  { field: 'ic_ir', label: 'IC_IR' },
  { field: 'annualized_return', label: '年化收益' },
]

const viewMode = ref<ViewMode>('card')
const search = ref('')
const categoryCode = ref('')
const sortField = ref<SortField | undefined>(undefined)
const sortOrder = ref<'asc' | 'desc'>('desc')
const page = ref(1)
const pageSize = 30

// 搜索防抖
const debouncedSearch = ref('')
let timer: ReturnType<typeof setTimeout> | undefined
watch(search, (value) => {
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => {
    debouncedSearch.value = value
    page.value = 1
  }, 300)
})
onUnmounted(() => {
  if (timer) clearTimeout(timer)
})

// 构建查询参数（响应式）
const queryParams = computed<PresetFactorParams>(() => {
  const params: PresetFactorParams = { page: page.value, page_size: pageSize }
  if (categoryCode.value) params.category_code = categoryCode.value
  if (sortField.value) {
    params.sort_field = sortField.value
    params.sort_order = sortOrder.value
  }
  if (debouncedSearch.value) params.search = debouncedSearch.value
  return params
})

const { data, isLoading, isFetching } = usePresetFactors(queryParams)
const { data: categories } = usePresetFactorCategories()
const addToPoolMutation = useAddToFactorPool()
const addingId = ref<number | null>(null)
// 因子详情弹窗（点击因子打开；可直接定位到 AI 分析）
const detail = ref<{ id: number; tab: 'formula' | 'ai' } | null>(null)
const showReference = ref(false)

function openDetail(id: number) {
  detail.value = { id, tab: 'formula' }
}
function openAI(id: number) {
  detail.value = { id, tab: 'ai' }
}

function handleCategoryClick(code: string) {
  categoryCode.value = categoryCode.value === code ? '' : code
  page.value = 1
}

function handleSort(field: SortField) {
  if (sortField.value === field) {
    sortOrder.value = sortOrder.value === 'desc' ? 'asc' : 'desc'
  } else {
    sortField.value = field
    sortOrder.value = 'desc'
  }
  page.value = 1
}

async function handleAddToPool(id: number) {
  addingId.value = id
  try {
    await addToPoolMutation.mutateAsync(id)
  } catch {
    // 静默处理
  } finally {
    addingId.value = null
  }
}

const factors = computed(() => data.value?.items ?? [])
const total = computed(() => data.value?.total ?? 0)
const totalPages = computed(() => Math.ceil(total.value / pageSize))
const totalCount = computed(() => categories.value?.reduce((sum, c) => sum + c.factor_count, 0) ?? 0)

// 分页页码（含省略号）
const pageNumbers = computed<(number | '...')[]>(() => {
  const tp = totalPages.value
  const p = page.value
  const pages: (number | '...')[] = []
  for (let i = 1; i <= tp; i++) {
    if (i === 1 || i === tp || (i >= p - 2 && i <= p + 2)) pages.push(i)
    else if (pages[pages.length - 1] !== '...') pages.push('...')
  }
  return pages
})

function cardIcMetrics(f: PresetFactor) {
  return [
    { label: 'IC_MEAN', value: fmt(f.ic_mean) },
    { label: 'RANK_IC', value: fmt(f.rank_ic) },
    { label: 'IC_IR', value: fmt(f.ic_ir) },
    { label: 'IC_STD', value: fmt(f.ic_std) },
  ]
}
function cardPerfMetrics(f: PresetFactor) {
  return [
    { label: '年化收益', value: fmtPct(f.annualized_return) },
    { label: '最大回撤', value: fmtPct(f.maximum_drawdown) },
    { label: '夏普比率', value: fmt(f.sharpe_ratio, 2) },
    { label: '换手率', value: fmtPct(f.turnover_rate) },
  ]
}
</script>

<template>
  <div class="flex flex-col">
    <!-- 顶部工具栏：搜索 + 视图切换 -->
    <div class="mb-3 flex items-center gap-3">
      <div class="relative flex-1">
        <Input v-model="search" placeholder="搜索因子名称 / 描述 / 公式..." />
      </div>
      <div class="flex items-center gap-1">
        <!-- 变量与算子参考 -->
        <button
          type="button"
          class="flex items-center gap-1 rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2 py-1.5 text-xs text-[#646262] transition-colors hover:text-[#201d1d] cursor-pointer"
          title="查看公式/代码可用的变量与算子"
          @click="showReference = true"
        >
          <BookOpen :size="12" />
          变量参考
        </button>
        <!-- 排序选择 -->
        <select
          class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2 py-1.5 text-xs text-[#646262] cursor-pointer"
          :value="sortField ?? ''"
          @change="
            (e) => {
              const v = (e.target as HTMLSelectElement).value as SortField | ''
              sortField = v || undefined
              page = 1
            }
          "
        >
          <option value="">排序</option>
          <option v-for="o in SORT_OPTIONS" :key="o.field" :value="o.field">{{ o.label }}</option>
        </select>
        <button
          v-if="sortField"
          type="button"
          class="rounded-[4px] border border-[rgba(15,0,0,0.12)] px-2 py-1.5 text-xs text-[#646262] cursor-pointer hover:text-[#201d1d]"
          @click="sortOrder = sortOrder === 'desc' ? 'asc' : 'desc'"
        >
          {{ sortOrder === 'desc' ? '↓ 降序' : '↑ 升序' }}
        </button>
        <!-- 视图切换 -->
        <div class="flex rounded-[4px] border border-[rgba(15,0,0,0.12)]">
          <button
            type="button"
            class="px-2 py-1.5 text-xs cursor-pointer transition-colors"
            :class="viewMode === 'card' ? 'bg-[#201d1d] text-[#fdfcfc]' : 'text-[#646262] hover:text-[#201d1d]'"
            @click="viewMode = 'card'"
          >
            卡片
          </button>
          <button
            type="button"
            class="px-2 py-1.5 text-xs cursor-pointer transition-colors"
            :class="viewMode === 'list' ? 'bg-[#201d1d] text-[#fdfcfc]' : 'text-[#646262] hover:text-[#201d1d]'"
            @click="viewMode = 'list'"
          >
            列表
          </button>
        </div>
      </div>
    </div>

    <!-- 分类标签栏 -->
    <div class="mb-3 flex gap-2 overflow-x-auto pb-1" style="scrollbar-width: thin">
      <button
        type="button"
        class="shrink-0 rounded-[4px] border px-2 py-1 text-xs transition-colors cursor-pointer"
        :class="
          !categoryCode
            ? 'border-[#007aff] bg-[#007aff]/10 text-[#007aff]'
            : 'border-[rgba(15,0,0,0.12)] text-[#646262] hover:text-[#201d1d]'
        "
        @click="
          () => {
            categoryCode = ''
            page = 1
          }
        "
      >
        全部·{{ totalCount }}
      </button>
      <button
        v-for="cat in categories"
        :key="cat.category_code"
        type="button"
        class="flex shrink-0 items-center gap-1 rounded-[4px] border px-2 py-1 text-xs transition-colors cursor-pointer"
        :class="
          categoryCode === cat.category_code
            ? 'border-[#007aff] bg-[#007aff]/10 text-[#007aff]'
            : 'border-[rgba(15,0,0,0.12)] text-[#646262] hover:text-[#201d1d]'
        "
        @click="handleCategoryClick(cat.category_code)"
      >
        <span class="inline-block h-[6px] w-[6px] rounded-full" :style="{ backgroundColor: cat.color_hex || '#646262' }" />
        {{ cat.category_name }}·{{ cat.factor_count }}
      </button>
    </div>

    <!-- 内容区域 -->
    <div class="relative" :class="isFetching ? 'opacity-60' : ''">
      <div v-if="isLoading" class="flex h-[200px] items-center justify-center">
        <span class="text-xs text-[#646262]">加载中...</span>
      </div>

      <!-- 卡片视图 -->
      <div v-else-if="viewMode === 'card'" class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        <div
          v-for="f in factors"
          :key="f.id"
          class="flex flex-col rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f1eeee] p-4 cursor-pointer transition-colors hover:border-[#9a9898]"
          title="点击查看公式与具体数据"
          @click="openDetail(f.id)"
        >
          <div class="mb-2 flex items-start justify-between gap-2">
            <span class="text-sm font-medium leading-tight text-[#201d1d]">{{ f.factor_name }}</span>
            <span class="flex shrink-0 items-center gap-1 text-[11px] text-[#646262]">
              <span class="inline-block h-[6px] w-[6px] rounded-full" :style="{ backgroundColor: f.category_color_hex || '#646262' }" />
              {{ f.category_name || '未分类' }}
            </span>
          </div>
          <p class="mb-3 line-clamp-2 text-xs leading-relaxed text-[#646262]">{{ f.description || '暂无描述' }}</p>
          <div class="mb-2 grid grid-cols-4 gap-1">
            <div v-for="m in cardIcMetrics(f)" :key="m.label" class="flex flex-col items-center">
              <span class="text-[10px] text-[#9a9898]">{{ m.label }}</span>
              <span class="text-xs font-medium text-[#201d1d]">{{ m.value }}</span>
            </div>
          </div>
          <div class="mb-3 grid grid-cols-4 gap-1">
            <div v-for="m in cardPerfMetrics(f)" :key="m.label" class="flex flex-col items-center">
              <span class="text-[10px] text-[#9a9898]">{{ m.label }}</span>
              <span class="text-xs font-medium text-[#201d1d]">{{ m.value }}</span>
            </div>
          </div>
          <div class="mt-auto flex gap-2">
            <button
              type="button"
              :disabled="addingId === f.id"
              class="flex-1 rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2 py-1.5 text-xs font-medium text-[#201d1d] transition-colors hover:bg-[#f8f7f7] disabled:text-[#9a9898] cursor-pointer"
              @click.stop="handleAddToPool(f.id)"
            >
              {{ addingId === f.id ? '加入中...' : '[+] 加入因子池' }}
            </button>
            <button
              type="button"
              class="flex items-center gap-1 rounded-[4px] border border-[rgba(124,58,237,0.4)] bg-[#fdfcfc] px-2 py-1.5 text-xs font-medium text-[#7c3aed] transition-colors hover:bg-[#f8f7f7] cursor-pointer"
              title="AI 分析该因子"
              @click.stop="openAI(f.id)"
            >
              <Sparkles :size="11" />
              AI
            </button>
          </div>
        </div>
        <div v-if="factors.length === 0" class="col-span-full flex h-[120px] items-center justify-center">
          <span class="text-xs text-[#646262]">暂无因子数据</span>
        </div>
      </div>

      <!-- 列表视图 -->
      <table v-else class="w-full border-collapse text-sm">
        <thead>
          <tr class="bg-[#f8f7f7]">
            <th class="border-b border-[rgba(15,0,0,0.12)] px-3 py-2 text-left text-xs font-medium text-[#646262]">因子名称</th>
            <th class="border-b border-[rgba(15,0,0,0.12)] px-3 py-2 text-left text-xs font-medium text-[#646262]">分类</th>
            <th
              v-for="o in SORT_OPTIONS"
              :key="o.field"
              class="border-b border-[rgba(15,0,0,0.12)] px-3 py-2 text-left text-xs font-medium text-[#646262] cursor-pointer select-none hover:text-[#201d1d]"
              @click="handleSort(o.field)"
            >
              <span class="inline-flex items-center gap-1">
                {{ o.label }}
                <span v-if="sortField === o.field" class="text-[#007aff]">{{ sortOrder === 'asc' ? '↑' : '↓' }}</span>
              </span>
            </th>
            <th class="border-b border-[rgba(15,0,0,0.12)] px-3 py-2 text-left text-xs font-medium text-[#646262]">年化收益</th>
            <th class="border-b border-[rgba(15,0,0,0.12)] px-3 py-2 text-left text-xs font-medium text-[#646262]">最大回撤</th>
            <th class="border-b border-[rgba(15,0,0,0.12)] px-3 py-2 text-left text-xs font-medium text-[#646262]">夏普比率</th>
            <th class="border-b border-[rgba(15,0,0,0.12)] px-3 py-2 text-left text-xs font-medium text-[#646262]">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="factors.length === 0">
            <td colspan="10" class="px-3 py-8 text-center text-[#646262]">暂无因子数据</td>
          </tr>
          <tr
            v-for="f in factors"
            :key="f.id"
            class="border-b border-[rgba(15,0,0,0.12)] transition-colors hover:bg-[#f1eeee] cursor-pointer"
            title="点击查看公式与具体数据"
            @click="openDetail(f.id)"
          >
            <td class="px-3 py-2 text-sm font-medium text-[#201d1d]">{{ f.factor_name }}</td>
            <td class="px-3 py-2">
              <span class="inline-flex items-center gap-1 text-xs text-[#646262]">
                <span class="inline-block h-[6px] w-[6px] rounded-full" :style="{ backgroundColor: f.category_color_hex || '#646262' }" />
                {{ f.category_name || '未分类' }}
              </span>
            </td>
            <td class="px-3 py-2 text-xs text-[#201d1d]">{{ fmt(f.ic_mean) }}</td>
            <td class="px-3 py-2 text-xs text-[#201d1d]">{{ fmt(f.rank_ic) }}</td>
            <td class="px-3 py-2 text-xs text-[#201d1d]">{{ fmt(f.ic_ir) }}</td>
            <td class="px-3 py-2 text-xs text-[#201d1d]">{{ fmtPct(f.annualized_return) }}</td>
            <td class="px-3 py-2 text-xs text-[#201d1d]">{{ fmtPct(f.maximum_drawdown) }}</td>
            <td class="px-3 py-2 text-xs text-[#201d1d]">{{ fmt(f.sharpe_ratio, 2) }}</td>
            <td class="px-3 py-2">
              <div class="flex items-center gap-1">
                <button
                  type="button"
                  :disabled="addingId === f.id"
                  class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2 py-1 text-xs text-[#201d1d] transition-colors hover:bg-[#f8f7f7] disabled:text-[#9a9898] cursor-pointer"
                  title="加入因子池"
                  @click.stop="handleAddToPool(f.id)"
                >
                  {{ addingId === f.id ? '...' : '[+]' }}
                </button>
                <button
                  type="button"
                  class="rounded-[4px] border border-[rgba(124,58,237,0.4)] bg-[#fdfcfc] px-2 py-1 text-xs text-[#7c3aed] transition-colors hover:bg-[#f8f7f7] cursor-pointer"
                  title="AI 分析该因子"
                  @click.stop="openAI(f.id)"
                >
                  ✦
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 分页 -->
    <div v-if="totalPages > 1" class="flex items-center justify-center gap-1 py-3">
      <button
        type="button"
        :disabled="page <= 1"
        class="rounded-[4px] border border-[rgba(15,0,0,0.12)] px-2 py-1 text-xs text-[#646262] transition-colors hover:text-[#201d1d] disabled:text-[#9a9898] disabled:cursor-not-allowed cursor-pointer"
        @click="page -= 1"
      >
        上一页
      </button>
      <template v-for="(p, i) in pageNumbers" :key="typeof p === 'number' ? p : `e${i}`">
        <span v-if="p === '...'" class="px-1 text-xs text-[#9a9898]">...</span>
        <button
          v-else
          type="button"
          class="rounded-[4px] px-2 py-1 text-xs transition-colors cursor-pointer"
          :class="p === page ? 'bg-[#201d1d] text-[#fdfcfc]' : 'border border-[rgba(15,0,0,0.12)] text-[#646262] hover:text-[#201d1d]'"
          @click="page = p"
        >
          {{ p }}
        </button>
      </template>
      <button
        type="button"
        :disabled="page >= totalPages"
        class="rounded-[4px] border border-[rgba(15,0,0,0.12)] px-2 py-1 text-xs text-[#646262] transition-colors hover:text-[#201d1d] disabled:text-[#9a9898] disabled:cursor-not-allowed cursor-pointer"
        @click="page += 1"
      >
        下一页
      </button>
    </div>

    <!-- 因子详情弹窗（公式 LaTeX/代码 + 具体数据 + 重算历史 + AI 分析） -->
    <FactorDetailDialog
      :factor-id="detail?.id ?? null"
      :initial-tab="detail?.tab ?? 'formula'"
      @close="detail = null"
    />

    <!-- 变量与算子参考 -->
    <FactorReferenceDialog :open="showReference" @close="showReference = false" />
  </div>
</template>
