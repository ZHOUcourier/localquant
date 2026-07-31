<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Loader2, Maximize2, Minimize2, X } from 'lucide-vue-next'
import { useWorkflow } from '@/composables/useWorkflow'
import ComprehensiveReport from '@/components/factor/ComprehensiveReport.vue'
import AlphaLensReport from '@/components/factor/AlphaLensReport.vue'
import NodeCodeDialog from '@/components/workflow/NodeCodeDialog.vue'
import type { FactorReport, AlphaLensReport as AlphaLensReportT } from '@/components/factor/types'

/**
 * 工作流编辑器 = iframe 内嵌官方 ComfyUI 前端（方案 C.4）
 *
 * ComfyUI 前端是独立 Vue 应用（自带 Pinia/PrimeVue/litegraph），
 * 与外壳同 bundle 挂载会产生单例/版本冲突，因此用 iframe 隔离；
 * 二者共用同一个 localquant 后端（/comfy/api/* 协议适配层）。
 *
 * iframe 内扩展经 postMessage 委托弹窗类交互给外壳：
 * - localquant:show-node-report → 因子分析综合报告弹窗（与因子研究页同构）
 * - localquant:edit-node-code   → Monaco 节点代码编辑弹窗（高亮/补全/ruff）
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
  // 把工作流上下文告知编辑器（扩展侧按需消费）
  iframeRef.value?.contentWindow?.postMessage(
    {
      type: 'localquant:workflow-context',
      workflowId: workflowId.value,
      workflowName: workflow.value?.name || '',
    },
    window.location.origin,
  )
}

// 工作流名称异步到达后补发一次上下文（扩展需要 workflowId 注入运行记录）
watch(workflow, () => {
  if (loaded.value) onIframeLoad()
})

function toggleFullscreen() {
  fullscreen.value = !fullscreen.value
}

// —— 因子分析综合报告弹窗 ——————————————————————————————
const reportOpen = ref(false)
const reportLoading = ref(false)
const reportError = ref<string | null>(null)
const report = ref<FactorReport | null>(null)
const alReport = ref<AlphaLensReportT | null>(null)
const reportKind = ref<'factor' | 'alphalens'>('factor')
const reportTitle = ref('')

async function openNodeReport(nodeId: string, runId: string, nodeTitle: string, kind: 'factor' | 'alphalens') {
  reportOpen.value = true
  reportLoading.value = true
  reportError.value = null
  report.value = null
  alReport.value = null
  reportKind.value = kind
  reportTitle.value = nodeTitle
  try {
    const qs = runId ? `?run_id=${encodeURIComponent(runId)}` : ''
    const res = await fetch(
      `/api/workflow/node-report/${encodeURIComponent(workflowId.value)}/${encodeURIComponent(nodeId)}${qs}`,
    )
    const data = await res.json().catch(() => null)
    if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`)
    if (kind === 'alphalens') alReport.value = data.report
    else report.value = data.report
  } catch (e) {
    reportError.value = e instanceof Error ? e.message : String(e)
  } finally {
    reportLoading.value = false
  }
}

// —— 节点代码 Monaco 弹窗 ——————————————————————————————————
const codeOpen = ref(false)
const codeClassType = ref('')
const codeDisplayName = ref('')

function onNodeCodeSaved() {
  // 通知 iframe 内 ComfyUI 刷新节点定义（fork 出的新节点立即可用）
  iframeRef.value?.contentWindow?.postMessage(
    { type: 'localquant:refresh-node-defs' },
    window.location.origin,
  )
}

// —— iframe 消息入口 ——————————————————————————————————————
function onMessage(e: MessageEvent) {
  if (e.origin !== window.location.origin) return
  const d = e.data
  if (!d || typeof d !== 'object') return
  if (d.type === 'localquant:show-node-report') {
    openNodeReport(
      String(d.nodeId || ''),
      String(d.runId || ''),
      String(d.nodeTitle || '因子分析'),
      d.reportKind === 'alphalens' ? 'alphalens' : 'factor',
    )
  } else if (d.type === 'localquant:edit-node-code') {
    codeClassType.value = String(d.classType || '')
    codeDisplayName.value = String(d.displayName || d.classType || '')
    codeOpen.value = true
  }
}
onMounted(() => window.addEventListener('message', onMessage))
onBeforeUnmount(() => window.removeEventListener('message', onMessage))

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

    <!-- 因子分析综合报告弹窗（与因子研究页同构同源） -->
    <div
      v-if="reportOpen"
      class="fixed inset-0 z-[80] flex items-center justify-center bg-black/45"
      @click.self="reportOpen = false"
    >
      <div
        class="flex flex-col overflow-hidden rounded-[6px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc]"
        style="width: min(1200px, 96vw); height: min(88vh, 900px)"
      >
        <div
          class="flex shrink-0 items-center justify-between border-b border-[rgba(15,0,0,0.12)] bg-[#f1eeee] px-4 py-2.5"
        >
          <span class="text-[13px] font-semibold text-[#201d1d]">分析结果 · {{ reportTitle }}</span>
          <button
            class="cursor-pointer border-0 bg-transparent text-[#646262] hover:text-[#201d1d]"
            @click="reportOpen = false"
          >
            <X :size="16" />
          </button>
        </div>
        <div class="min-h-0 flex-1 overflow-auto p-4">
          <div
            v-if="reportError"
            class="rounded-[4px] border border-[#ff9f0a]/50 bg-[#ff9f0a]/10 px-3 py-2.5 text-xs text-[#8a5a00]"
          >
            {{ reportError }}
          </div>
          <ComprehensiveReport
            v-else-if="reportKind === 'factor'"
            :report="report"
            :factor-name="reportTitle"
            :loading="reportLoading"
          />
          <AlphaLensReport
            v-else
            :report="alReport"
            :factor-name="reportTitle"
            :loading="reportLoading"
          />
        </div>
      </div>
    </div>

    <!-- 节点代码 Monaco 编辑弹窗 -->
    <NodeCodeDialog
      :open="codeOpen"
      :class-type="codeClassType"
      :display-name="codeDisplayName"
      @close="codeOpen = false"
      @saved="onNodeCodeSaved"
    />
  </div>
</template>
