<script setup lang="ts">
/**
 * ChatMessage — 单条消息渲染（对齐参考站 display_timeline 结构）
 * 用户：右对齐描边气泡；AI：思考块 + text/tool 交替时间线（markdown + 工具卡）。
 * 消息操作（参考站动作条，hover 显示，圆形浅灰反馈）：
 *   用户：复制 / 编辑 / 删除；AI：复制 / 重新生成（仅最末）/ 删除。
 */
import { computed } from 'vue'
import { Copy, Pencil, RefreshCw, Trash2 } from 'lucide-vue-next'
import { renderMarkdown } from '@/lib/markdown'
import ThinkingBlock from './ThinkingBlock.vue'
import ToolCard from './ToolCard.vue'
import type { ChatMsg, TimelineItem } from './types'

const props = defineProps<{
  msg: ChatMsg
  streaming?: boolean
  isLast?: boolean
}>()

const emit = defineEmits<{
  openFactor: [factorId: string, tab: string]
  openStrategy: [strategyId: string, tab: string]
  viewAnalysis: [factorId: string, analysisId: string]
  viewBacktest: [strategyId: string, runId: string]
  optimize: [strategyId: string, runId: string]
  copy: [text: string]
  edit: [msg: ChatMsg]
  regenerate: [msg: ChatMsg]
  remove: [msg: ChatMsg]
}>()

// 时间线：有 tool_calls 用其 display_timeline；否则整块 content 当一个文本段
const timeline = computed<TimelineItem[]>(() => {
  const tc = props.msg.tool_calls
  if (tc?.display_timeline?.length) return tc.display_timeline
  return props.msg.content ? [{ type: 'text', content: props.msg.content }] : []
})

const thinking = computed(() => props.msg.tool_calls?.thinking || '')
const calls = computed(() => props.msg.tool_calls?.calls || [])
const hasId = computed(() => typeof props.msg.id === 'number')
const hasContent = computed(() => !!props.msg.content)
const timeLabel = computed(() =>
  props.msg.created_at ? new Date(props.msg.created_at * 1000).toLocaleString('zh-CN', { hour12: false }) : '',
)

// 每句 AI 回复的 token 用量（来自后端 usage；无则隐藏）
const tokenLabel = computed(() => {
  const u = props.msg.usage
  if (!u) return ''
  const parts: string[] = []
  if (u.reasoning_tokens) parts.push(`思考 ${u.reasoning_tokens.toLocaleString()}`)
  if (u.completion_tokens) parts.push(`输出 ${u.completion_tokens.toLocaleString()}`)
  if (!parts.length) return ''
  return `${parts.join(' · ')} ${u.estimated ? '(估)' : ''}`
})

// 操作按钮统一样式（圆形 hover 浅灰底，对齐参考站）
const A = 'flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[#9a9898] hover:bg-[#f1eeee] hover:text-[#201d1d]'
</script>

<template>
  <!-- 用户消息 -->
  <div v-if="msg.role === 'user'" class="group flex flex-col items-end">
    <div
      class="max-w-[78%] whitespace-pre-wrap rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-3 py-2 text-xs leading-relaxed text-[#201d1d]"
    >
      {{ msg.content }}
    </div>
    <!-- 动作条：hover 显示 -->
    <div class="mt-1 flex items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
      <button :class="A" title="复制" @click="emit('copy', msg.content)"><Copy :size="13" /></button>
      <button v-if="hasContent && hasId" :class="A" title="编辑" @click="emit('edit', msg)">
        <Pencil :size="13" />
      </button>
      <button v-if="hasContent && hasId" :class="A" title="删除" @click="emit('remove', msg)">
        <Trash2 :size="13" />
      </button>
    </div>
  </div>

  <!-- AI 消息 -->
  <div v-else class="group flex gap-2.5">
    <div
      class="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#201d1d] font-mono text-[10px] font-bold text-[#fdfcfc]"
    >
      Q
    </div>
    <div class="min-w-0 flex-1 space-y-1">
      <span class="block text-[11px] font-semibold text-[#201d1d]">QUBE</span>

      <div class="space-y-2.5">
        <ThinkingBlock v-if="thinking" :text="thinking" :streaming="streaming && !timeline.length" />

        <template v-for="(seg, i) in timeline" :key="i">
          <div
            v-if="seg.type === 'text' && seg.content?.trim()"
            class="md-body max-w-[52rem]"
            v-html="renderMarkdown(seg.content)"
          />
          <ToolCard
            v-else-if="seg.type === 'tool' && seg.call_index != null && calls[seg.call_index]"
            class="max-w-[52rem]"
            :call="calls[seg.call_index]"
            @open-factor="(id, tab) => emit('openFactor', id, tab)"
            @open-strategy="(id, tab) => emit('openStrategy', id, tab)"
            @view-analysis="(fid, aid) => emit('viewAnalysis', fid, aid)"
            @view-backtest="(sid, rid) => emit('viewBacktest', sid, rid)"
            @optimize="(sid, rid) => emit('optimize', sid, rid)"
          />
          <div
            v-else-if="seg.type === 'text' && !seg.content?.trim()"
            v-show="streaming && seg === timeline[timeline.length - 1]"
            class="flex items-center gap-1.5 text-xs text-[#9a9898]"
          >
            <span class="inline-block h-2 w-2 animate-pulse rounded-full bg-[#007aff]" />
          </div>
        </template>
      </div>

      <!-- 左下角：时间 + 复制/重新生成/删除 -->
      <div class="flex items-center gap-0.5 pl-0.5 opacity-0 transition-opacity group-hover:opacity-100">
        <span v-if="timeLabel" class="mr-1 text-[10px] text-[#9a9898]">{{ timeLabel }}</span>
        <button v-if="!streaming" :class="A" title="复制" @click="emit('copy', msg.content)">
          <Copy :size="13" />
        </button>
        <button
          v-if="hasContent && isLast && !streaming"
          :class="A"
          title="重新生成"
          @click="emit('regenerate', msg)"
        >
          <RefreshCw :size="13" />
        </button>
        <button v-if="hasContent && hasId && !streaming" :class="A" title="删除" @click="emit('remove', msg)">
          <Trash2 :size="13" />
        </button>
      </div>

      <div v-if="tokenLabel" class="mt-1 flex items-center gap-0.5 pl-0.5 font-mono text-[10px] text-[#b0aeae]">
        {{ tokenLabel }}
      </div>

      <slot name="tail" />
    </div>
  </div>
</template>