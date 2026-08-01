<script setup lang="ts">
/**
 * ChatMessage — 单条消息渲染（对齐参考站 display_timeline 结构）
 * 用户：右对齐描边气泡；AI：思考块 + text/tool 交替时间线（markdown + 工具卡）。
 */
import { computed } from 'vue'
import { renderMarkdown } from '@/lib/markdown'
import ThinkingBlock from './ThinkingBlock.vue'
import ToolCard from './ToolCard.vue'
import type { ChatMsg, TimelineItem } from './types'

const props = defineProps<{
  msg: ChatMsg
  streaming?: boolean
}>()

const emit = defineEmits<{
  openFactor: [factorId: string, tab: string]
  openStrategy: [strategyId: string, tab: string]
  viewAnalysis: [factorId: string, analysisId: string]
  viewBacktest: [strategyId: string, runId: string]
  optimize: [strategyId: string, runId: string]
}>()

// 时间线：有 tool_calls 用其 display_timeline；否则整块 content 当一个文本段
const timeline = computed<TimelineItem[]>(() => {
  const tc = props.msg.tool_calls
  if (tc?.display_timeline?.length) return tc.display_timeline
  return props.msg.content ? [{ type: 'text', content: props.msg.content }] : []
})

const thinking = computed(() => props.msg.tool_calls?.thinking || '')
const calls = computed(() => props.msg.tool_calls?.calls || [])
</script>

<template>
  <!-- 用户消息 -->
  <div v-if="msg.role === 'user'" class="flex justify-end">
    <div
      class="max-w-[78%] whitespace-pre-wrap rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-3 py-2 text-xs leading-relaxed text-[#201d1d]"
    >
      {{ msg.content }}
    </div>
  </div>

  <!-- AI 消息 -->
  <div v-else class="flex gap-2.5">
    <div
      class="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#201d1d] font-mono text-[10px] font-bold text-[#fdfcfc]"
    >
      Q
    </div>
    <div class="min-w-0 flex-1 space-y-2.5">
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
      </template>

      <slot name="tail" />
    </div>
  </div>
</template>
