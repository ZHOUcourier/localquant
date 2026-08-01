<script setup lang="ts">
/**
 * SkillDetailDialog — 技能详情弹窗
 *
 * 点击技能卡后从卡片位置 App Store 展开：展示技能操作手册（prompt markdown）、
 * 关联 GitHub 仓库 README / SKILL.md（源码仓库信息）与仓库元数据（stars/license/描述）。
 * 底部提供「在 QUBE 中使用」跳转（预填 prompt 模板）。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ExternalLink, BookOpen, GitFork, Star } from 'lucide-vue-next'
import { useSpring, useReducedMotion } from '@vueuse/motion'
import { renderMarkdown } from '@/lib/markdown'
import { jsonFetch } from '@/components/qube/types'
import type { SkillDetail, SkillRepo } from '@/components/qube/types'

export interface SkillDialogOrigin {
  x: number
  y: number
  width: number
  height: number
}

const props = withDefaults(
  defineProps<{
    skillId: number
    origin?: SkillDialogOrigin | null
  }>(),
  { origin: null },
)
const emit = defineEmits<{ close: [] }>()
const router = useRouter()

// ── App Store 卡片展开动效（同因子详情弹窗）──────────────────────
const reduced = useReducedMotion()
const panelAnim = reactive({ x: 0, y: 0, sx: 1, sy: 1, bg: 1 })
const fxAnim = reactive({ backdrop: 0 })
const panelSpring = useSpring(panelAnim, { stiffness: 260, damping: 27, mass: 1 })
const fxSpring = useSpring(fxAnim, { stiffness: 150, damping: 22, mass: 1 })

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
    const stop = watch(
      () => panelAnim.sx,
      (s) => {
        if (s <= target) finish()
      },
    )
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

onMounted(() => {
  document.body.style.overflow = 'hidden'
  window.addEventListener('keydown', onKey)
  playOpen()
  load()
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
  document.body.style.overflow = ''
})

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') handleClose()
}

// ── 数据加载：技能详情 + GitHub 仓库信息 ────────────────────────
const data = ref<SkillDetail | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)
const repoLoading = ref(false)

async function load(refresh = false) {
  loading.value = true
  error.value = null
  try {
    const res = await jsonFetch(`/api/qube/skills/${props.skillId}/detail${refresh ? '?refresh=true' : ''}`)
    data.value = res
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

// 仓库加载状态：首次请求已带仓库信息；手动刷新时单独提示
async function refreshRepo() {
  repoLoading.value = true
  try {
    await load(true)
  } finally {
    repoLoading.value = false
  }
}

const skill = computed(() => data.value?.skill ?? null)
const repo = computed<SkillRepo | null>(() => data.value?.repo ?? null)
const repoOk = computed(() => repo.value?.ok === true)

// 默认展示 prompt 手册；有 README 时加一个「README」分栏
const tab = ref('manual')
const tabs = computed<{ key: string; label: string }[]>(() => {
  const list: { key: string; label: string }[] = [{ key: 'manual', label: '操作手册' }]
  if (repoOk.value && repo.value?.readme) list.push({ key: 'readme', label: 'GitHub README' })
  if (repoOk.value && repo.value?.skill_md) list.push({ key: 'skill', label: 'SKILL.md' })
  return list
})
watch(tabs, (t) => {
  if (t.length && !t.some((x) => x.key === tab.value)) tab.value = t[0].key
})

function useInQube() {
  const s = skill.value
  if (!s) return
  if (s.builtin && !s.enabled) return
  const text = s.builtin ? `请帮我${s.display_name}。` : s.prompt
  router.push({ path: '/qube', query: { prompt: text } })
}

function fmtStars(v?: number | null): string {
  if (!v) return '—'
  return v >= 1000 ? `${(v / 1000).toFixed(1)}k` : String(v)
}
function fmtDate(v?: string): string {
  if (!v) return '—'
  const d = new Date(v)
  return Number.isNaN(d.getTime()) ? v : d.toLocaleDateString('zh-CN')
}
function sourceLabel(src: string): string {
  if (!src) return ''
  if (src === 'QuantSkills') return 'QuantSkills'
  if (src === 'LLMQuant') return 'LLMQuant'
  return src
}
</script>

<template>
  <Teleport to="body">
    <div class="fixed inset-0 z-50">
      <div class="absolute inset-0" :style="backdropStyle" @click="handleClose" />

      <div class="fixed left-0 top-0 overflow-hidden" :style="shellStyle">
        <div class="h-full overflow-auto" :style="contentStyle">
          <div class="w-full px-6 py-6">
            <!-- 头部 -->
            <div class="mb-4 flex items-center justify-between gap-3">
              <div class="min-w-0">
                <div class="truncate text-base font-bold text-[#201d1d]">
                  {{ skill ? skill.display_name : '技能详情' }}
                </div>
                <div class="mt-0.5 text-[11px] text-[#646262]">
                  {{ skill ? `技能库${skill.builtin ? ' · 系统内置' : ' · 自定义'} · 点击背景或按 Esc 关闭` : '' }}
                </div>
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

            <div v-if="loading" class="py-10 text-center text-xs text-[#646262]">加载中...</div>
            <div v-else-if="error" class="py-10 text-center text-xs text-[#ff3b30]">{{ error }}</div>
            <div v-else-if="!skill">
              <div class="py-10 text-center text-xs text-[#646262]">技能不存在</div>
            </div>
            <div v-else>
              <!-- 元信息行：分类 · 来源 · stars · 仓库 -->
              <div class="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-[#646262]">
                <span
                  class="rounded-[3px] bg-[#f1eeee] px-1.5 py-0.5 text-[10px] text-[#424245]"
                >
                  {{ skill.category || '未分类' }}
                </span>
                <span>{{ sourceLabel(skill.source) || '自定义' }}</span>
                <a
                  v-if="skill.url"
                  :href="skill.url"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="flex items-center gap-1 text-[#007aff] hover:underline"
                >
                  来源链接 <ExternalLink :size="10" />
                </a>
              </div>

              <!-- 仓库元数据卡片（有仓库时） -->
              <div
                v-if="repoOk && repo"
                class="mb-3 flex flex-wrap items-center gap-3 rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-3 py-2"
              >
                <span class="flex items-center gap-1 text-[11px] font-medium text-[#201d1d]">
                  <GitFork :size="12" class="text-[#646262]" />
                  {{ repo.owner }}/{{ repo.repo }}
                </span>
                <span class="flex items-center gap-1 text-[11px] text-[#646262]">
                  <Star :size="11" class="text-[#ff9f0a]" /> {{ fmtStars(repo.meta?.stars) }}
                </span>
                <span v-if="repo.meta?.license" class="text-[11px] text-[#646262]">{{ repo.meta.license }}</span>
                <span v-if="repo.meta?.language" class="text-[11px] text-[#646262]">{{ repo.meta.language }}</span>
                <span v-if="repo.meta?.updated_at" class="text-[11px] text-[#9a9898]">更新 {{ fmtDate(repo.meta.updated_at) }}</span>
                <a
                  v-if="repo.meta?.html_url"
                  :href="repo.meta.html_url"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="ml-auto flex items-center gap-1 text-[#007aff] hover:underline"
                >
                  GitHub <ExternalLink :size="10" />
                </a>
                <button
                  type="button"
                  class="flex items-center gap-1 text-[10px] text-[#9a9898] hover:text-[#201d1d]"
                  :disabled="repoLoading"
                  @click="refreshRepo"
                >
                  {{ repoLoading ? '刷新中...' : '↻ 刷新' }}
                </button>
              </div>

              <!-- 分栏 -->
              <div class="mb-3 flex flex-wrap items-center gap-1 border-b border-[rgba(15,0,0,0.12)]">
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

              <!-- 操作手册（prompt 模板 markdown） -->
              <div v-if="tab === 'manual'" class="md-body max-w-[52rem]">
                <div v-if="!skill.prompt" class="text-xs text-[#9a9898]">该技能暂无手册内容。</div>
                <div v-else v-html="renderMarkdown(skill.prompt)" />
              </div>

              <!-- GitHub README -->
              <div v-else-if="tab === 'readme'" class="md-body max-w-[52rem]">
                <div class="mb-2 flex items-center gap-2 text-[11px] text-[#646262]">
                  <BookOpen :size="12" />
                  README.md <span class="text-[#9a9898]">({{ repo?.branch }}@{{ repo?.owner }}/{{ repo?.repo }})</span>
                </div>
                <div v-if="!repo?.readme" class="text-xs text-[#9a9898]">仓库未提供 README。</div>
                <div v-else v-html="renderMarkdown(repo.readme)" />
              </div>

              <!-- SKILL.md -->
              <div v-else-if="tab === 'skill'" class="md-body max-w-[52rem]">
                <div class="mb-2 flex items-center gap-2 text-[11px] text-[#646262]">
                  <BookOpen :size="12" />
                  SKILL.md 技能本体
                </div>
                <div v-if="!repo?.skill_md" class="text-xs text-[#9a9898]">仓库未提供 SKILL.md。</div>
                <div v-else v-html="renderMarkdown(repo.skill_md)" />
              </div>

              <!-- 底部操作 -->
              <div class="mt-5 flex items-center justify-end gap-2 border-t border-[rgba(15,0,0,0.08)] pt-3">
                <span v-if="skill.builtin && !skill.enabled" class="text-[11px] text-[#9a9898]">该技能暂未接入平台工具</span>
                <button
                  type="button"
                  :disabled="skill.builtin && !skill.enabled"
                  class="rounded-[4px] bg-[#201d1d] px-4 py-1.5 text-xs text-[#fdfcfc] hover:opacity-85 disabled:opacity-50"
                  @click="useInQube"
                >
                  在 QUBE 中使用
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>
