<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { PanelLeftOpen } from 'lucide-vue-next'
import Sidebar from './Sidebar.vue'
import TopBar from './TopBar.vue'
import StatusBar from './StatusBar.vue'
import { ResizeHandle } from '@/components/ui'
import { useBackendHealth } from '@/composables/useBackendHealth'

const { online, checking } = useBackendHealth()
const route = useRoute()
// 满幅页（无内边距）：工作流编辑器（iframe 内嵌 ComfyUI）与 QUBE（左中右分屏，自带 h-full 布局）
const isFullBleedPage = computed(
  () => /^\/workflow\/[^/]+$/.test(route.path) || route.path === '/qube',
)

// —— 主侧边栏：可收起 + 可拖宽（VSCode 风格拖杆），localStorage 持久化 ——
// 宽度默认贴合导航文字：刚好显示最长一行不换行（图标 + 文本 + 内边距/间距按当前字体计算）。
const SIDEBAR_KEY = 'lq-main-sidebar'
const SIDEBAR_MAX = 360
const FALLBACK_FIT_WIDTH = 120
const NAV_LABELS = [
  '工作台', '数据中心', '因子研究', '工作流', 'QUBE',
  '策略库', '技能库', '回测记录', '实验管理', '风险分析', '设置',
]

const fitWidth = ref(FALLBACK_FIT_WIDTH)

function measureFitWidth(): number {
  try {
    const rem = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16
    const canvas = document.createElement('canvas')
    const ctx = canvas.getContext('2d')
    let maxLabel = 0
    if (ctx) {
      ctx.font = `13px ${getComputedStyle(document.body).fontFamily || 'sans-serif'}`
      maxLabel = Math.max(...NAV_LABELS.map((label) => ctx.measureText(label).width))
    }
    if (!maxLabel) maxLabel = 52
    // 图标 16 + 文本 + nav px-2×2 + item px-3×2 + gap-2.5（rem 系数 3.125）+ 2px 余量
    return Math.ceil(maxLabel + 16 + rem * 3.125 + 2)
  } catch {
    return FALLBACK_FIT_WIDTH
  }
}

function loadSidebar() {
  try {
    const raw = localStorage.getItem(SIDEBAR_KEY)
    if (raw) {
      const p = JSON.parse(raw)
      if (p.v === 2) {
        return {
          width: Number(p.width) || FALLBACK_FIT_WIDTH,
          collapsed: !!p.collapsed,
          auto: p.auto !== false,
          v: 2,
        }
      }
      // v1 旧记录：宽度默认按贴合处理，一次迁移到 auto
      return { width: FALLBACK_FIT_WIDTH, collapsed: !!p.collapsed, auto: true, v: 2 }
    }
  } catch {
    /* 回默认 */
  }
  return { width: FALLBACK_FIT_WIDTH, collapsed: false, auto: true, v: 2 }
}

const sidebar = reactive(loadSidebar())
watch(sidebar, () => {
  try {
    localStorage.setItem(SIDEBAR_KEY, JSON.stringify(sidebar))
  } catch {
    /* 忽略 */
  }
})

// 首次挂载后按真实字体测量贴合宽度；auto 模式跟随贴合宽度，手动拖宽后保留用户选择
onMounted(async () => {
  await nextTick()
  try {
    await document.fonts?.ready
  } catch {
    /* 字体 API 不可用时忽略 */
  }
  fitWidth.value = measureFitWidth()
  if (sidebar.auto || sidebar.width < fitWidth.value) {
    sidebar.width = fitWidth.value
  }
})

const sidebarDragging = ref(false)

function clampSidebar(w: number) {
  return Math.max(fitWidth.value, Math.min(SIDEBAR_MAX, w))
}

function resetSidebarWidth() {
  sidebar.auto = true
  sidebar.width = fitWidth.value
}

function onSidebarDrag(e: MouseEvent) {
  sidebarDragging.value = true
  const startX = e.clientX
  const startWidth = sidebar.width
  document.body.style.cursor = 'ew-resize'
  document.body.style.userSelect = 'none'
  const move = (ev: MouseEvent) => {
    sidebar.auto = false
    sidebar.width = clampSidebar(startWidth + (ev.clientX - startX))
  }
  const up = () => {
    sidebarDragging.value = false
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
    window.removeEventListener('mousemove', move)
    window.removeEventListener('mouseup', up)
  }
  window.addEventListener('mousemove', move)
  window.addEventListener('mouseup', up)
}
</script>

<template>
  <div class="flex h-screen flex-col" style="background: #fdfcfc">
    <div class="flex min-h-0 flex-1">
      <!-- 侧边栏全高，Logo 位于整个界面最左上角；可拖宽/收起 -->
      <div
        v-show="!sidebar.collapsed"
        class="relative shrink-0 border-r border-[rgba(15,0,0,0.08)]"
        :class="sidebarDragging ? '' : 'transition-[width] duration-200 ease-out'"
        :style="{ width: `${sidebar.width}px` }"
      >
        <Sidebar @collapse="sidebar.collapsed = true" />
        <ResizeHandle
          side="right"
          :dragging="sidebarDragging"
          @drag-start="onSidebarDrag"
          @dblclick="resetSidebarWidth"
        />
      </div>

      <!-- 收起态：窄条展开按钮 -->
      <button
        v-if="sidebar.collapsed"
        class="flex w-[26px] shrink-0 items-start justify-center border-r border-[rgba(15,0,0,0.08)] bg-[#f8f7f7] pt-4 text-[#646262] hover:bg-[#f1eeee] hover:text-[#201d1d]"
        title="展开侧边栏"
        @click="sidebar.collapsed = false"
      >
        <PanelLeftOpen :size="15" />
      </button>

      <div class="flex flex-col flex-1 min-w-0">
        <TopBar />

        <div
          v-if="!online && !checking"
          class="flex items-center gap-2 border-b bg-[#f8f7f7] px-4 py-2 font-mono text-[13px] text-[#cc7f08]"
          style="border-color: rgba(15, 0, 0, 0.12)"
        >
          <span class="inline-block h-2 w-2 rounded-full bg-[#ff9f0a]" />
          后端服务未连接 (http://localhost:8000) — 请运行
          <code class="rounded-[4px] bg-[#201d1d] px-1.5 py-0.5 text-[#fdfcfc]">make dev</code>
          或
          <code class="rounded-[4px] bg-[#201d1d] px-1.5 py-0.5 text-[#fdfcfc]">make dev-backend</code>
          ，页面数据将无法加载
        </div>

        <!-- 内容区留白对齐 opencode 官网（content-panel padding: 2rem 3rem）；满幅页（画布/QUBE）不加内边距 -->
        <main class="flex-1 min-h-0 overflow-auto" :class="isFullBleedPage ? '' : 'px-12 py-8'">
          <!-- 不使用 <Transition out-in> 包裹路由组件：路由组件均为懒加载异步组件，
               out-in 切换存在挂载时机竞态（新组件渲染为空 → 白屏），稳定性优先 -->
          <RouterView v-slot="{ Component }">
            <component :is="Component" :key="route.path" />
          </RouterView>
        </main>
      </div>
    </div>

    <!-- 底部状态栏：资讯 + 指数行情（横跨全屏宽） -->
    <StatusBar />
  </div>
</template>
