<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
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
const SIDEBAR_KEY = 'lq-main-sidebar'
const SIDEBAR_MIN = 160
const SIDEBAR_MAX = 360

function loadSidebar() {
  try {
    const raw = localStorage.getItem(SIDEBAR_KEY)
    if (raw) {
      const p = JSON.parse(raw)
      return { width: Number(p.width) || 220, collapsed: !!p.collapsed }
    }
  } catch {
    /* 回默认 */
  }
  return { width: 220, collapsed: false }
}

const sidebar = reactive(loadSidebar())
watch(sidebar, () => {
  try {
    localStorage.setItem(SIDEBAR_KEY, JSON.stringify(sidebar))
  } catch {
    /* 忽略 */
  }
})

const sidebarDragging = ref(false)

function clampSidebar(w: number) {
  return Math.max(SIDEBAR_MIN, Math.min(SIDEBAR_MAX, w))
}

function onSidebarDrag(e: MouseEvent) {
  sidebarDragging.value = true
  const startX = e.clientX
  const startWidth = sidebar.width
  document.body.style.cursor = 'ew-resize'
  document.body.style.userSelect = 'none'
  const move = (ev: MouseEvent) => {
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
          @dblclick="sidebar.width = 220"
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
          <RouterView />
        </main>
      </div>
    </div>

    <!-- 底部状态栏：资讯 + 指数行情（横跨全屏宽） -->
    <StatusBar />
  </div>
</template>
