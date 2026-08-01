<script setup lang="ts">
/**
 * Skills — 技能库独立页（左侧导航入口 /skills）
 *
 * 「我的技能 / 系统内置」两 Tab + 搜索 + 分类胶囊 + 技能卡网格。
 * 卡片标注来源（QuantSkills / LLMQuant）并带外链；可用技能可「在 QUBE 中使用」
 * （跳转到 /qube 并把 prompt 模板预填进输入框）。系统内置只读，本地无能力的置灰「未接入」。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { BookMarked, ExternalLink } from 'lucide-vue-next'
import { Select } from '@/components/ui'
import type { SelectOption } from '@/components/ui'
import type { Skill } from '@/components/qube/types'
import { jsonFetch } from '@/components/qube/types'
import SkillDetailDialog from '@/components/skills/SkillDetailDialog.vue'

const router = useRouter()
const builtin = ref<Skill[]>([])
const mine = ref<Skill[]>([])
const activeTab = ref<'builtin' | 'mine'>('builtin')
const activeCat = ref('all')
const search = ref('')
const loading = ref(false)

const creating = ref(false)
const form = ref({ display_name: '', description: '', category: '对话', prompt: '' })
const CATEGORIES = ['记忆', '策略', '回测', '调优', '仿真交易', '对话', '因子']
const categoryOptions: SelectOption[] = CATEGORIES.map((c) => ({ value: c, label: c }))

// 技能详情弹窗：记录卡片位置，App Store 展开动画从卡片出发
const cardEls = new Map<number, HTMLElement>()
function setCardRef(id: number, el: unknown) {
  if (el instanceof HTMLElement) cardEls.set(id, el)
  else cardEls.delete(id)
}
function cardOrigin(id: number): { x: number; y: number; width: number; height: number } | undefined {
  const el = cardEls.get(id)
  if (!el) return undefined
  const r = el.getBoundingClientRect()
  return { x: r.left, y: r.top, width: r.width, height: r.height }
}
const detail = ref<{ id: number; origin?: { x: number; y: number; width: number; height: number } } | null>(null)
function openDetail(id: number) {
  detail.value = { id, origin: cardOrigin(id) }
}

// 参考来源（用户要求展示 quant-wiki / quantpaper / quantskills 等社区）
const REFERENCES = [
  { name: 'QuantSkills', url: 'https://www.quantskills.ai' },
  { name: 'LLMQuant Skills', url: 'https://github.com/LLMQuant/skills' },
]

async function load() {
  loading.value = true
  try {
    const [b, m] = await Promise.all([
      jsonFetch('/api/qube/skills/builtin'),
      jsonFetch('/api/qube/skills/user'),
    ])
    builtin.value = b.skills
    mine.value = m.skills
  } finally {
    loading.value = false
  }
}
onMounted(load)

const currentList = computed(() => (activeTab.value === 'builtin' ? builtin.value : mine.value))

const categories = computed(() => {
  const cats: { id: string; label: string; count: number }[] = [
    { id: 'all', label: '全部', count: currentList.value.length },
  ]
  const order = ['记忆', '策略', '回测', '调优', '仿真交易', '对话', '因子', '综合', '分析']
  for (const c of order) {
    const n = currentList.value.filter((s) => s.category === c).length
    if (n) cats.push({ id: c, label: c, count: n })
  }
  return cats
})

const filtered = computed(() =>
  currentList.value.filter((s) => {
    if (activeCat.value !== 'all' && s.category !== activeCat.value) return false
    const q = search.value.trim().toLowerCase()
    if (q && !`${s.display_name}${s.description}`.toLowerCase().includes(q)) return false
    return true
  }),
)

function useSkill(s: Skill) {
  if (s.builtin && !s.enabled) return
  const text = s.builtin ? `请帮我${s.display_name}。` : s.prompt
  router.push({ path: '/qube', query: { prompt: text } })
}

async function submitCreate() {
  if (!form.value.display_name.trim() || !form.value.prompt.trim()) return
  await jsonFetch('/api/qube/skills', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(form.value),
  })
  form.value = { display_name: '', description: '', category: '对话', prompt: '' }
  creating.value = false
  activeTab.value = 'mine'
  load()
}

async function removeSkill(s: Skill) {
  await jsonFetch(`/api/qube/skills/${s.id}`, { method: 'DELETE' })
  load()
}

function switchTab(t: 'builtin' | 'mine') {
  activeTab.value = t
  activeCat.value = 'all'
  creating.value = false
}

// 来源显示名映射
function sourceLabel(src: string): string {
  if (!src) return ''
  if (src === 'QuantSkills') return 'QuantSkills'
  if (src === 'LLMQuant') return 'LLMQuant'
  return src
}
</script>

<template>
  <div class="flex h-full flex-col p-4">
    <!-- 标题 + 参考来源 -->
    <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
      <div class="flex items-center gap-2">
        <BookMarked :size="16" class="text-[#007aff]" />
        <span class="text-sm font-semibold text-[#201d1d]">技能库</span>
        <span class="text-[11px] text-[#9a9898]">
          内置技能来自开源量化社区，点击「在 QUBE 中使用」把 prompt 模板带过去
        </span>
      </div>
      <div class="flex items-center gap-3 text-[11px] text-[#646262]">
        <span class="text-[#9a9898]">参考来源：</span>
        <a
          v-for="r in REFERENCES"
          :key="r.url"
          :href="r.url"
          target="_blank"
          rel="noopener noreferrer"
          class="flex items-center gap-1 text-[#007aff] hover:underline"
        >
          {{ r.name }} <ExternalLink :size="10" />
        </a>
      </div>
    </div>

    <!-- 过滤 Tab -->
    <div class="mb-3 flex flex-wrap items-center gap-2">
      <div class="flex gap-1">
        <button
          v-for="t in [
            { k: 'builtin', l: `系统内置 · ${builtin.length}` },
            { k: 'mine', l: `我的技能 · ${mine.length}` },
          ]"
          :key="t.k"
          class="rounded-[4px] px-3 py-1 text-xs"
          :class="activeTab === t.k ? 'bg-[#201d1d] text-[#fdfcfc]' : 'bg-[#f1eeee] text-[#646262] hover:text-[#201d1d]'"
          @click="switchTab(t.k as 'builtin' | 'mine')"
        >
          {{ t.l }}
        </button>
      </div>
      <input
        v-model="search"
        placeholder="搜索技能…"
        class="ml-auto w-[220px] rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-2.5 py-1 text-xs outline-none focus:border-[#201d1d]"
      />
      <button
        v-if="activeTab === 'mine'"
        class="rounded-[4px] bg-[#201d1d] px-2.5 py-1 text-xs text-[#fdfcfc] hover:opacity-85"
        @click="creating = !creating"
      >
        ＋ 新建技能
      </button>
    </div>

    <!-- 新建技能表单 -->
    <div v-if="creating" class="mb-3 space-y-2 rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] p-3">
      <div class="flex gap-2">
        <input
          v-model="form.display_name"
          placeholder="技能名称"
          class="flex-1 rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2.5 py-1 text-xs outline-none focus:border-[#201d1d]"
        />
        <div class="w-[120px] shrink-0">
          <Select v-model="form.category" :options="categoryOptions" />
        </div>
      </div>
      <input
        v-model="form.description"
        placeholder="一句话描述（可选）"
        class="w-full rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2.5 py-1 text-xs outline-none focus:border-[#201d1d]"
      />
      <textarea
        v-model="form.prompt"
        rows="3"
        placeholder="prompt 模板，例：请对当前策略做一次压力测试并给出改进建议。"
        class="w-full resize-none rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2.5 py-1.5 text-xs outline-none focus:border-[#201d1d]"
      />
      <div class="flex justify-end gap-2">
        <button class="rounded-[4px] border border-[rgba(15,0,0,0.15)] px-3 py-1 text-xs text-[#646262]" @click="creating = false">
          取消
        </button>
        <button
          :disabled="!form.display_name.trim() || !form.prompt.trim()"
          class="rounded-[4px] bg-[#201d1d] px-3 py-1 text-xs text-[#fdfcfc] disabled:opacity-50"
          @click="submitCreate"
        >
          创建
        </button>
      </div>
    </div>

    <!-- 分类胶囊 -->
    <div v-if="activeTab === 'builtin'" class="mb-2 flex flex-wrap gap-1.5">
      <button
        v-for="c in categories"
        :key="c.id"
        class="rounded-full px-2.5 py-0.5 text-[11px]"
        :class="activeCat === c.id ? 'bg-[#201d1d] text-[#fdfcfc]' : 'bg-[#f1eeee] text-[#646262] hover:text-[#201d1d]'"
        @click="activeCat = c.id"
      >
        {{ c.label }} · {{ c.count }}
      </button>
    </div>

    <!-- 技能卡网格 -->
    <div class="min-h-0 flex-1 overflow-y-auto">
      <div v-if="loading" class="flex h-32 items-center justify-center text-xs text-[#646262]">加载中…</div>
      <div v-else-if="!filtered.length" class="flex h-32 items-center justify-center text-xs text-[#9a9898]">
        {{ activeTab === 'mine' ? '还没有自定义技能 — 点【＋ 新建技能】写一个 prompt 模板' : '无匹配技能' }}
      </div>
      <div v-else class="grid grid-cols-1 gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
        <div
          v-for="s in filtered"
          :key="s.id"
          :ref="(el) => setCardRef(s.id, el)"
          v-motion
          :initial="{ opacity: 0, y: 14 }"
          :enter="{ opacity: 1, y: 0, transition: { delay: Math.min(Number(s.id) % 8, 8) * 25 } }"
          :hovered="{ y: -2, transition: { duration: 120 } }"
          :tapped="{ scale: 0.98, transition: { duration: 90 } }"
          class="group flex cursor-pointer flex-col rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] p-3"
          :class="s.builtin && !s.enabled ? 'opacity-60' : 'card-hover'"
          title="点击查看技能手册与 GitHub 仓库信息"
          @click="openDetail(s.id)"
        >
          <div class="flex items-start gap-1.5">
            <span class="min-w-0 flex-1 truncate text-[13px] font-medium text-[#201d1d]">
              {{ s.display_name }}
            </span>
            <button
              v-if="!s.builtin"
              class="shrink-0 text-[10px] text-[#9a9898] opacity-0 hover:text-[#ff3b30] group-hover:opacity-100"
              title="删除"
              @click.stop="removeSkill(s)"
            >
              ✕
            </button>
          </div>
          <div class="mt-1 line-clamp-2 text-[11px] leading-relaxed text-[#646262]">
            {{ s.description }}
          </div>
          <div class="mt-1.5 flex flex-wrap items-center gap-1">
            <span
              v-if="s.builtin && !s.enabled"
              class="rounded-[3px] bg-[#f1eeee] px-1 py-0.5 text-[9px] text-[#9a9898]"
            >
              未接入
            </span>
            <span
              v-for="p in s.params.slice(0, 4)"
              :key="p"
              class="rounded-[3px] bg-[#f8f7f7] px-1 py-0.5 font-mono text-[9px] text-[#646262]"
            >
              {{ p }}
            </span>
          </div>
          <!-- 来源 + 操作 -->
          <div class="mt-2 flex items-center justify-between">
            <a
              v-if="s.url"
              :href="s.url"
              target="_blank"
              rel="noopener noreferrer"
              class="flex items-center gap-1 text-[10px] text-[#007aff] hover:underline"
              @click.stop
            >
              {{ sourceLabel(s.source) }} <ExternalLink :size="9" />
            </a>
            <span v-else-if="s.source" class="text-[10px] text-[#9a9898]">{{ sourceLabel(s.source) }}</span>
            <span v-else class="text-[10px] text-[#9a9898]">自定义</span>
            <button
              class="rounded-[4px] bg-[#201d1d] px-2 py-1 text-[11px] text-[#fdfcfc] hover:opacity-85 disabled:opacity-50"
              :disabled="s.builtin && !s.enabled"
              @click.stop="useSkill(s)"
            >
              在 QUBE 中使用
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 技能详情弹窗（v-if 控制挂载：每次打开全新实例，App Store 动画从本次点击的卡片出发） -->
    <SkillDetailDialog v-if="detail" :skill-id="detail.id" :origin="detail.origin" @close="detail = null" />
  </div>
</template>