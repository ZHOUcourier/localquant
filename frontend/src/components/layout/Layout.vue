<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import Sidebar from './Sidebar.vue'
import TopBar from './TopBar.vue'
import StatusBar from './StatusBar.vue'
import { useBackendHealth } from '@/composables/useBackendHealth'

const { online, checking } = useBackendHealth()
const route = useRoute()
// 工作流编辑器需要满幅画布（iframe 内嵌 ComfyUI），不加内边距
const isCanvasPage = computed(() => /^\/workflow\/[^/]+$/.test(route.path))
</script>

<template>
  <div class="flex h-screen flex-col" style="background: #fdfcfc">
    <div class="flex min-h-0 flex-1">
      <!-- 侧边栏全高，Logo 位于整个界面最左上角 -->
      <Sidebar />

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

        <!-- 内容区留白对齐 opencode 官网（content-panel padding: 2rem 3rem）；画布页不加内边距 -->
        <main class="flex-1 min-h-0 overflow-auto" :class="isCanvasPage ? '' : 'px-12 py-8'">
          <RouterView />
        </main>
      </div>
    </div>

    <!-- 底部状态栏：资讯 + 指数行情（横跨全屏宽） -->
    <StatusBar />
  </div>
</template>
