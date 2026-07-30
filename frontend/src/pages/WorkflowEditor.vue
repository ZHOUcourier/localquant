<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Loader2, Maximize2, Minimize2 } from 'lucide-vue-next'
import { useWorkflow } from '@/composables/useWorkflow'

/**
 * 工作流编辑器 = iframe 内嵌官方 ComfyUI 前端（方案 C.4）
 *
 * ComfyUI 前端是独立 Vue 应用（自带 Pinia/PrimeVue/litegraph），
 * 与外壳同 bundle 挂载会产生单例/版本冲突，因此用 iframe 隔离；
 * 二者共用同一个 localquant 后端（/comfy/api/* 协议适配层）。
 *
 * 网页全屏：把外壳侧栏/顶栏/状态栏都盖住，让编辑器占满整个浏览器视口
 * （fixed inset-0，非视频全屏）；Esc 或按钮退出。
 */
const route = useRoute()
const workflowId = computed(() => String(route.params.id || ''))
const { data: workflow } = useWorkflow(workflowId)

const loaded = ref(false)
const fullscreen = ref(false)

// dev 下 vite 已代理 /comfy → 8000；生产由后端同源托管
const comfySrc = computed(() => `/comfy/?workflow_id=${encodeURIComponent(workflowId.value)}`)

const iframeRef = ref<HTMLIFrameElement | null>(null)

function onIframeLoad() {
  loaded.value = true
  // 把工作流上下文告知编辑器（扩展侧可按需消费）
  iframeRef.value?.contentWindow?.postMessage(
    {
      type: 'localquant:workflow-context',
      workflowId: workflowId.value,
      workflowName: workflow.value?.name || '',
    },
    window.location.origin,
  )
}

function toggleFullscreen() {
  fullscreen.value = !fullscreen.value
}

// Esc 退出全屏
function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape' && fullscreen.value) fullscreen.value = false
}
watch(fullscreen, (fs) => {
  if (fs) window.addEventListener('keydown', onKey)
  else window.removeEventListener('keydown', onKey)
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div
    class="h-full w-full"
    :class="fullscreen ? 'fixed inset-0 z-[60]' : 'relative'"
    style="background: #202020"
  >
    <!-- 加载占位：iframe 内 ComfyUI 自带 splash，此处只兜底首帧空白 -->
    <div
      v-if="!loaded"
      class="absolute inset-0 z-10 flex items-center justify-center gap-2 text-[13px] text-[#9a9898]"
    >
      <Loader2 class="animate-spin" :size="16" />
      正在加载 ComfyUI 编辑器...
    </div>

    <!-- 网页全屏切换按钮（悬浮右上角） -->
    <button
      class="absolute right-3 top-3 z-20 flex items-center gap-1 rounded-[4px] border px-2.5 py-1 text-[12px] transition-colors"
      style="border-color: rgba(255, 255, 255, 0.18); background: rgba(32, 29, 29, 0.72); color: #e8e5e5; backdrop-filter: blur(4px)"
      :title="fullscreen ? '退出网页全屏 (Esc)' : '网页全屏（隐藏侧栏/顶栏/状态栏）'"
      @click="toggleFullscreen"
    >
      <component :is="fullscreen ? Minimize2 : Maximize2" :size="13" />
      {{ fullscreen ? '退出全屏' : '全屏' }}
    </button>

    <iframe
      ref="iframeRef"
      :src="comfySrc"
      title="ComfyUI 工作流编辑器"
      class="h-full w-full border-0"
      allow="clipboard-read; clipboard-write"
      @load="onIframeLoad"
    />
  </div>
</template>
