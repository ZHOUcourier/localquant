<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'

const routeTitles: Record<string, string> = {
  '/': '工作台',
  '/data': '数据中心',
  '/factor': '因子研究',
  '/workflow': '工作流',
  '/runs': '运行中心',
  '/experiments': '实验管理',
  '/settings': '设置',
}

/** 子路由面包屑：pathname → { text, link? }[] */
function getBreadcrumbs(pathname: string): { text: string; link?: string }[] {
  if (routeTitles[pathname]) return [{ text: routeTitles[pathname] }]
  if (pathname.startsWith('/workflow/'))
    return [{ text: '工作流', link: '/workflow' }, { text: '编辑器' }]
  return [{ text: '' }]
}

const route = useRoute()
const crumbs = computed(() => getBreadcrumbs(route.path))

// 右上角实时时钟
const now = ref(new Date())
let clockTimer: ReturnType<typeof setInterval> | undefined
const dateText = computed(() =>
  now.value.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit', weekday: 'short' }),
)
const timeText = computed(() => now.value.toLocaleTimeString('zh-CN', { hour12: false }))

// QMT 真实连接状态（轮询 /api/data/status，不再硬编码）
const connected = ref<boolean | null>(null)
let qmtTimer: ReturnType<typeof setInterval> | undefined
async function checkQmt() {
  try {
    const r = await fetch('/api/data/status')
    if (!r.ok) throw new Error()
    const data = await r.json()
    connected.value = !!data.qmt_connected
  } catch {
    connected.value = null
  }
}

onMounted(() => {
  clockTimer = setInterval(() => (now.value = new Date()), 1000)
  checkQmt()
  qmtTimer = setInterval(checkQmt, 30000)
})
onUnmounted(() => {
  clearInterval(clockTimer)
  clearInterval(qmtTimer)
})
</script>

<template>
  <div
    class="flex items-center justify-between px-8 shrink-0"
    style="height: 56px; background: #fdfcfc; border-bottom: 1px solid rgba(15, 0, 0, 0.08)"
  >
    <div class="flex items-center gap-1">
      <template v-for="(crumb, i) in crumbs" :key="i">
        <span v-if="i === crumbs.length - 1 || !crumb.link" class="text-[15px] font-medium text-[#201d1d]">
          {{ crumb.text }}
        </span>
        <span v-else class="flex items-center gap-1">
          <RouterLink
            :to="crumb.link"
            class="text-[13px] text-[#646262] no-underline hover:text-[#201d1d]"
          >
            {{ crumb.text }}
          </RouterLink>
          <span class="text-[13px] text-[#9a9898]">/</span>
        </span>
      </template>
    </div>

    <div class="flex items-center gap-4">
      <div class="flex items-center gap-1.5">
        <span
          class="inline-block rounded-full"
          :style="{ width: '8px', height: '8px', background: connected ? '#30d158' : '#6e6e73' }"
        />
        <span class="text-[12px] text-[#646262]">
          {{ connected == null ? 'QMT 状态未知' : connected ? 'QMT 已连接' : 'QMT 未连接' }}
        </span>
      </div>
      <span class="font-mono text-[12px] text-[#646262]" style="font-variant-numeric: tabular-nums">
        {{ dateText }} {{ timeText }}
      </span>
    </div>
  </div>
</template>
