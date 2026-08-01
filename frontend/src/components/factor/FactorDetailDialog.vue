<script setup lang="ts">
/**
 * FactorDetailDialog — 因子详情弹窗
 *
 * 点击因子后展示：
 * - 公式：代码形式（Python 片段） + LaTeX 数学渲染（KaTeX）两种呈现
 * - 具体数据：全部 IC/绩效指标、股票池、数据区间
 * - 重算：明确标注「覆盖更新」语义 + 历史快照列表
 * - AI 分析：调用 /api/ai/factor-advice 给出因子解读与使用建议
 */
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, toRef, watch } from 'vue'
import katex from 'katex'
import 'katex/dist/katex.min.css'
import { Sparkles, RefreshCw } from 'lucide-vue-next'
import { useSpring, useReducedMotion } from '@vueuse/motion'
import { CodeEditor } from '@/components/ui'
import { usePresetFactorDetail, useFactorHistory, useRecalculateFactor } from '@/composables/usePresetFactors'

function fmt(v: number | null | undefined, digits = 4): string {
  if (v == null) return '—'
  return v.toFixed(digits)
}
function fmtPct(v: number | null | undefined, digits = 2): string {
  if (v == null) return '—'
  return `${(v * 100).toFixed(digits)}%`
}

type TabKey = 'formula' | 'data' | 'history' | 'ai'

export interface FactorDialogOrigin {
  x: number
  y: number
  width: number
  height: number
}

const props = withDefaults(
  defineProps<{
    factorId: number | null
    initialTab?: TabKey
    origin?: FactorDialogOrigin | null
  }>(),
  { initialTab: 'formula', origin: null },
)
const emit = defineEmits<{ close: [] }>()

// ── App Store 卡片展开动效 ──────────────────────────────────────
// 面板外壳从点击的卡片矩形（collapsed）用弹簧动画放大到居中的卡片式弹窗（expanded，非全屏）。
// 文本不单独淡入淡出，而是跟随外壳缩放位移一起移动（连贯），
// 仅在首尾贴近卡片尺寸时渐隐渐现，避免关闭时闪现大片空白。
const reduced = useReducedMotion()

const panelAnim = reactive({ x: 0, y: 0, sx: 1, sy: 1, bg: 1 })
const fxAnim = reactive({ backdrop: 0 })
const panelSpring = useSpring(panelAnim, { stiffness: 260, damping: 27, mass: 1 })
const fxSpring = useSpring(fxAnim, { stiffness: 150, damping: 22, mass: 1 })

// 展开目标：居中的卡片式弹窗尺寸（非全屏）
const modalSize = ref({ w: 0, h: 0 })
const collapsedVals = ref<{ x: number; y: number; sx: number; sy: number; bg: number } | null>(null)
const expandedVals = ref<{ x: number; y: number; sx: number; sy: number; bg: number } | null>(null)

function measureLayout() {
  const vw = Math.max(document.documentElement.clientWidth, 1)
  const vh = Math.max(document.documentElement.clientHeight, 1)
  const w = Math.min(760, Math.max(320, vw - 48))
  const h = Math.min(Math.max(vh * 0.85, 240), 720)
  modalSize.value = { w, h }
  const cx = (vw - w) / 2
  const cy = (vh - h) / 2
  const o = props.origin
  collapsedVals.value = o
    ? {
        x: o.x,
        y: o.y,
        sx: Math.min(o.width / w, 1),
        sy: Math.min(o.height / h, 1),
        bg: 0,
      }
    : { x: cx, y: cy, sx: 0.92, sy: 0.92, bg: 1 }
  expandedVals.value = { x: cx, y: cy, sx: 1, sy: 1, bg: 1 }
}

const BACKDROP_ON = { backdrop: 0.4 } as const
const BACKDROP_OFF = { backdrop: 0 } as const

async function playOpen() {
  measureLayout()
  Object.assign(panelAnim, collapsedVals.value!)
  Object.assign(fxAnim, BACKDROP_OFF)
  if (reduced.value) {
    Object.assign(panelAnim, expandedVals.value!)
    Object.assign(fxAnim, BACKDROP_ON)
    return
  }
  await nextTick()
  await Promise.all([panelSpring.set(expandedVals.value!), fxSpring.set(BACKDROP_ON)])
}

async function playClose() {
  if (reduced.value) return
  const c = collapsedVals.value
  if (!c) return
  panelSpring.set(c)
  fxSpring.set(BACKDROP_OFF)
  await waitForNearCollapse()
}

// 弹簧动画末尾 settle 很慢（约 0.5~0.8s），且此时内容已淡出、外壳接近卡片大小，
// 继续等待只会让空白外壳长时间盖在卡片上。因此缩到接近卡片尺寸（1.08x）就视为完成，立即卸载还原卡片。
function waitForNearCollapse(maxMs = 650): Promise<void> {
  return new Promise((resolve) => {
    const c = collapsedVals.value
    if (!c) return resolve()
    const target = c.sx * 1.08
    if (panelAnim.sx <= target) return resolve()
    let done = false
    const finish = () => {
      if (done) return
      done = true
      stop()
      clearTimeout(timer)
      resolve()
    }
    const stop = watch(() => panelAnim.sx, (s) => {
      if (s <= target) finish()
    })
    const timer = setTimeout(finish, maxMs)
  })
}

let closing = false
function handleClose() {
  if (closing) return
  closing = true
  playClose().then(() => emit('close'))
}

function lerpColor(t: number): string {
  const c0 = [241, 238, 238]
  const c1 = [253, 252, 252]
  const p = Math.max(0, Math.min(1, t))
  const r = Math.round(c0[0] + (c1[0] - c0[0]) * p)
  const g = Math.round(c0[1] + (c1[1] - c0[1]) * p)
  const b = Math.round(c0[2] + (c1[2] - c0[2]) * p)
  return `rgb(${r}, ${g}, ${b})`
}

// 文本跟随外壳缩放：缩放比例 > 0.75 时完全可见（开合主体阶段），
// 接近卡片尺寸时淡出，保证闭合全程无大片空白。
const contentOpacity = computed(() => {
  const c = collapsedVals.value
  if (!c) return 1
  const s = panelAnim.sx
  if (s >= 0.75) return 1
  if (s <= c.sx) return 0
  return (s - c.sx) / (0.75 - c.sx)
})

const shellStyle = computed(() => {
  const { w, h } = modalSize.value
  const v = panelAnim
  return {
    width: `${w}px`,
    height: `${h}px`,
    transform: `translate(${v.x}px, ${v.y}px) scale(${v.sx}, ${v.sy})`,
    transformOrigin: 'top left',
    willChange: 'transform, opacity',
    borderRadius: '4px',
    border: '1px solid rgba(15, 0, 0, 0.12)',
    backgroundColor: lerpColor(v.bg),
  }
})
const contentStyle = computed(() => ({ opacity: contentOpacity.value }))
const backdropStyle = computed(() => ({ backgroundColor: `rgba(0, 0, 0, ${fxAnim.backdrop})` }))

// 父组件用 v-if 控制本组件挂载：每次打开都是全新实例，
// 弹簧动画值随之重新初始化，保证开启动画总是从「本次点击的卡片」位置开始。
onMounted(() => {
  document.body.style.overflow = 'hidden'
  window.addEventListener('keydown', onKey)
  playOpen()
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
  document.body.style.overflow = ''
})

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') handleClose()
}

const { data: factor, isLoading } = usePresetFactorDetail(toRef(props, 'factorId'))
const { data: history } = useFactorHistory(toRef(props, 'factorId'))
const recalcMutation = useRecalculateFactor()
const tab = ref<TabKey>(props.initialTab)
const recalcMsg = ref<string | null>(null)
// AI 分析
const aiLoading = ref(false)
const aiAdvice = ref<string | null>(null)
const aiError = ref<string | null>(null)

// 切换因子时重置状态
watch(
  () => [props.factorId, props.initialTab],
  () => {
    tab.value = props.initialTab
    recalcMsg.value = null
    aiAdvice.value = null
    aiError.value = null
  },
)

// KaTeX 渲染（渲染失败回退原始公式文本）
const latexEl = ref<HTMLDivElement | null>(null)
const latexFailed = ref(false)
watch([latexEl, () => factor.value?.formula_latex, tab], () => {
  const el = latexEl.value
  const latex = factor.value?.formula_latex
  if (!el || !latex) return
  try {
    katex.render(latex, el, { throwOnError: true, displayMode: true })
    latexFailed.value = false
  } catch {
    latexFailed.value = true
  }
})

const metrics = computed(() =>
  factor.value
    ? [
        { label: 'IC_MEAN', value: fmt(factor.value.ic_mean) },
        { label: 'RANK_IC', value: fmt(factor.value.rank_ic) },
        { label: 'IC_IR', value: fmt(factor.value.ic_ir) },
        { label: 'IC_STD', value: fmt(factor.value.ic_std) },
        { label: '年化收益', value: fmtPct(factor.value.annualized_return) },
        { label: '最大回撤', value: fmtPct(factor.value.maximum_drawdown) },
        { label: '夏普比率', value: fmt(factor.value.sharpe_ratio, 2) },
        { label: '换手率', value: fmtPct(factor.value.turnover_rate) },
      ]
    : [],
)

const tabs = computed<{ key: TabKey; label: string }[]>(() => [
  { key: 'formula', label: '公式' },
  { key: 'data', label: '具体数据' },
  { key: 'history', label: `重算历史${history.value?.length ? `(${history.value.length})` : ''}` },
  { key: 'ai', label: '✦ AI 分析' },
])

async function handleRecalc() {
  if (!props.factorId) return
  recalcMsg.value = null
  try {
    const result = await recalcMutation.mutateAsync(props.factorId)
    recalcMsg.value = result.recalc_message || '重算完成（覆盖更新）'
  } catch (e) {
    recalcMsg.value = `重算失败: ${e instanceof Error ? e.message : String(e)}`
  }
}

async function handleAI() {
  const f = factor.value
  if (!f) return
  aiLoading.value = true
  aiError.value = null
  try {
    const res = await fetch('/api/ai/factor-advice', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        factor_name: f.factor_name,
        factor_code: f.factor_code,
        formula: f.formula,
        description: f.description,
        metrics: {
          IC_MEAN: f.ic_mean,
          RANK_IC: f.rank_ic,
          IC_IR: f.ic_ir,
          IC_STD: f.ic_std,
          年化收益: f.annualized_return,
          最大回撤: f.maximum_drawdown,
          夏普比率: f.sharpe_ratio,
          换手率: f.turnover_rate,
        },
      }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => null)
      throw new Error(err?.detail || `HTTP ${res.status}`)
    }
    const data = await res.json()
    aiAdvice.value = data.advice || ''
  } catch (e) {
    aiError.value = e instanceof Error ? e.message : String(e)
  } finally {
    aiLoading.value = false
  }
}

function copyFormula() {
  if (factor.value) navigator.clipboard?.writeText(factor.value.formula)
}

function typeBadgeClass(t?: string): string {
  if (t === 'formula') return 'bg-[#007aff]/10 text-[#007aff]'
  if (t === 'indicator') return 'bg-[#ff9f0a]/15 text-[#cc7f08]'
  return 'bg-[#30d158]/15 text-[#248a3d]'
}
</script>

<template>
  <Teleport to="body">
    <div v-if="factorId != null" class="fixed inset-0 z-50">
      <!-- 遮罩：随内容一同淡入淡出 -->
      <div class="absolute inset-0" :style="backdropStyle" @click="handleClose" />

      <!-- 形态外壳：从卡片矩形弹簧放大到居中的卡片式弹窗（非全屏） -->
      <div class="fixed left-0 top-0 overflow-hidden" :style="shellStyle">
        <div class="h-full overflow-auto" :style="contentStyle">
          <div class="w-full px-6 py-6">
            <!-- 头部：标题 + 关闭 -->
            <div class="mb-4 flex items-center justify-between gap-3">
              <div class="min-w-0">
                <div class="truncate text-base font-bold text-[#201d1d]">
                  {{ factor ? `${factor.factor_name} · ${factor.factor_code}` : '因子详情' }}
                </div>
                <div class="mt-0.5 text-[11px] text-[#646262]">LocalQuant 因子库 · 点击背景或按 Esc 关闭</div>
              </div>
              <button
                type="button"
                class="press flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-[rgba(15,0,0,0.15)] bg-[#f8f7f7] text-sm text-[#646262] transition-colors hover:text-[#201d1d]"
                title="关闭"
                @click="handleClose"
              >
                ✕
              </button>
            </div>
      <div v-if="isLoading || !factor" class="py-10 text-center text-xs text-[#646262]">加载中...</div>
      <div v-else>
        <!-- 头部：分类 + 描述 -->
        <div class="mb-3 flex items-center gap-2 text-xs text-[#646262]">
          <span class="inline-block h-[7px] w-[7px] rounded-full" :style="{ backgroundColor: factor.category_color_hex || '#646262' }" />
          {{ factor.category_name || '未分类' }}
          <span class="text-[#9a9898]">
            {{ factor.stock_pool ? `· 股票池 ${factor.stock_pool}` : '' }}
            {{ factor.start_date ? ` · ${factor.start_date} 起` : '' }}
            {{ factor.data_date ? ` · 数据截至 ${factor.data_date}` : '' }}
          </span>
        </div>

        <!-- Tab 切换 -->
        <div class="mb-3 flex border-b border-[rgba(15,0,0,0.12)]">
          <button
            v-for="t in tabs"
            :key="t.key"
            type="button"
            class="px-3 py-1.5 text-xs cursor-pointer transition-colors"
            :class="tab === t.key ? 'border-b-2 border-[#201d1d] font-medium text-[#201d1d]' : 'text-[#646262] hover:text-[#201d1d]'"
            @click="tab = t.key"
          >
            {{ t.label }}
          </button>
        </div>

        <!-- 公式 Tab -->
        <div v-if="tab === 'formula'" class="flex flex-col gap-3">
          <div class="flex items-center gap-2">
            <span class="rounded-[3px] px-2 py-0.5 text-[11px] font-medium" :class="typeBadgeClass(factor.factor_type)">
              {{ factor.factor_type === 'formula' ? '公式型因子' : factor.factor_type === 'indicator' ? '参数化指标' : '数据字段型因子' }}
            </span>
            <span class="text-[11px] text-[#9a9898]">
              {{
                factor.factor_type === 'formula'
                  ? '可直接在「因子构建（公式）」节点运行'
                  : factor.factor_type === 'indicator'
                    ? '参数化技术指标，可用「技术指标」节点或公式复现'
                    : '直接调用底层数据字段，无需公式'
              }}
            </span>
          </div>

          <template v-if="factor.factor_type === 'formula' && factor.formula">
            <div>
              <div class="mb-1 text-[11px] font-medium text-[#646262]">数学公式（LaTeX 渲染）</div>
              <div
                v-if="!factor.formula_latex || latexFailed"
                class="rounded-[4px] bg-[#f8f7f7] px-3 py-3 text-center text-sm text-[#201d1d] font-mono"
              >
                {{ factor.formula || '暂无公式' }}
              </div>
              <div v-else ref="latexEl" class="overflow-x-auto rounded-[4px] bg-[#f8f7f7] px-3 py-2 text-[#201d1d]" style="font-size: 14px" />
            </div>
            <div>
              <div class="mb-1 flex items-center justify-between text-[11px] font-medium text-[#646262]">
                <span>代码形式（可粘贴到公式/代码节点运行）</span>
                <button type="button" class="text-[#007aff] cursor-pointer bg-transparent border-none" title="复制公式" @click="copyFormula">
                  复制公式
                </button>
              </div>
              <CodeEditor
                :model-value="factor.formula_code || factor.formula"
                language="python"
                :height="180"
                read-only
                :lint="false"
                title="因子代码"
                :font-size="12"
              />
            </div>
          </template>
          <div v-else class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-3 py-3 text-xs leading-relaxed text-[#424245]">
            {{
              factor.factor_type === 'data_field'
                ? '该因子为底层数据字段（如财务/估值指标），在数据节点中直接选用对应字段即可，无需编写公式。'
                : '该因子为参数化技术指标，可在「技术指标」节点配置参数使用，或用公式算子复现（参见下方变量参考）。'
            }}
            <div class="mt-2 font-mono text-[11px] text-[#646262]">字段代码：{{ factor.factor_code }}</div>
          </div>

          <div v-if="factor.description">
            <div class="mb-1 text-[11px] font-medium text-[#646262]">因子简介</div>
            <div class="text-xs leading-relaxed text-[#424245]">{{ factor.description }}</div>
          </div>
        </div>

        <!-- 具体数据 Tab -->
        <div v-if="tab === 'data'">
          <div class="grid grid-cols-4 gap-2">
            <div
              v-for="m in metrics"
              :key="m.label"
              class="flex flex-col items-center rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-2 py-2.5"
            >
              <span class="text-[10px] text-[#9a9898]">{{ m.label }}</span>
              <span class="mt-0.5 text-sm font-medium text-[#201d1d]">{{ m.value }}</span>
            </div>
          </div>

          <!-- 重算：明确覆盖语义 -->
          <div class="mt-4 rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] p-3">
            <div class="mb-2 flex items-center justify-between">
              <span class="text-xs font-medium text-[#201d1d]">重新计算 IC 指标</span>
              <button
                type="button"
                :disabled="recalcMutation.isPending.value"
                class="flex items-center gap-1 rounded-[4px] bg-[#201d1d] px-3 py-1 text-xs text-[#fdfcfc] transition-colors hover:bg-[#0f0000] disabled:opacity-50 cursor-pointer"
                @click="handleRecalc"
              >
                <RefreshCw :size="11" :class="recalcMutation.isPending.value ? 'animate-spin' : ''" />
                {{ recalcMutation.isPending.value ? '重算中...' : '重算（覆盖更新）' }}
              </button>
            </div>
            <div class="text-[11px] leading-relaxed text-[#646262]">
              <span class="font-medium text-[#cc7f08]">覆盖，不另存：</span>
              重算得到的新指标会直接写回当前因子记录（不会生成新因子条目）；
              覆盖前的旧值会自动存入「重算历史」快照，可随时回溯对比。
            </div>
            <div v-if="recalcMsg" class="mt-2 rounded-[4px] bg-[#fdfcfc] px-2 py-1.5 text-[11px] text-[#424245]">
              {{ recalcMsg }}
            </div>
          </div>
        </div>

        <!-- 重算历史 Tab -->
        <div v-if="tab === 'history'" class="max-h-[320px] overflow-auto">
          <div v-if="!history || history.length === 0" class="py-8 text-center text-xs text-[#9a9898]">
            暂无历史快照（每次重算覆盖前会自动留存旧值）
          </div>
          <table v-else class="w-full border-collapse text-xs">
            <thead>
              <tr class="bg-[#f8f7f7]">
                <th
                  v-for="h in ['快照时间', 'IC_MEAN', 'RANK_IC', 'IC_IR', '年化收益', '最大回撤']"
                  :key="h"
                  class="border-b border-[rgba(15,0,0,0.12)] px-2 py-1.5 text-left font-medium text-[#646262]"
                >
                  {{ h }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="s in history" :key="s.id" class="border-b border-[rgba(15,0,0,0.08)]">
                <td class="px-2 py-1.5 text-[#646262]">
                  {{ new Date(s.snapshot_at * 1000).toLocaleString('zh-CN', { hour12: false }) }}
                </td>
                <td class="px-2 py-1.5 text-[#201d1d]">{{ fmt(s.ic_mean) }}</td>
                <td class="px-2 py-1.5 text-[#201d1d]">{{ fmt(s.rank_ic) }}</td>
                <td class="px-2 py-1.5 text-[#201d1d]">{{ fmt(s.ic_ir) }}</td>
                <td class="px-2 py-1.5 text-[#201d1d]">{{ fmtPct(s.annualized_return) }}</td>
                <td class="px-2 py-1.5 text-[#201d1d]">{{ fmtPct(s.maximum_drawdown) }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- AI 分析 Tab -->
        <div v-if="tab === 'ai'">
          <div v-if="!aiAdvice && !aiLoading" class="flex flex-col items-center gap-3 py-6">
            <div class="text-center text-xs leading-relaxed text-[#646262]">
              AI 将解读该因子的公式逻辑、点评各项指标强弱，<br />
              并给出使用场景与调仓周期建议（需先在设置中配置 AI）。
            </div>
            <button
              type="button"
              class="flex items-center gap-1.5 rounded-[4px] bg-[#7c3aed] px-4 py-1.5 text-xs font-medium text-white transition-opacity hover:opacity-90 cursor-pointer"
              @click="handleAI"
            >
              <Sparkles :size="12" />
              开始 AI 分析
            </button>
            <div v-if="aiError" class="max-w-full whitespace-pre-wrap text-[11px] text-[#ff3b30]">{{ aiError }}</div>
          </div>
          <div v-if="aiLoading" class="py-10 text-center text-xs text-[#646262]">AI 分析中（可能需要几十秒）...</div>
          <div v-if="aiAdvice && !aiLoading">
            <div class="max-h-[320px] overflow-auto whitespace-pre-wrap rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-3 py-2.5 text-xs leading-relaxed text-[#424245]">
              {{ aiAdvice }}
            </div>
            <button type="button" class="mt-2 text-[11px] text-[#7c3aed] cursor-pointer bg-transparent border-none" @click="handleAI">
              ↻ 重新分析
            </button>
          </div>
        </div>
      </div>
        </div>
      </div>
    </div>
  </div>
  </Teleport>
</template>
