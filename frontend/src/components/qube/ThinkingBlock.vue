<script setup lang="ts">
/**
 * ThinkingBlock — 深度思考折叠块（accent 蓝，opencode 风 hairline 描边）
 * 折叠态「深度思考过程 · N 字」，点击展开可滚动全文；流式中显示等待动画。
 */
import { ref } from 'vue'

const props = defineProps<{
  text: string
  streaming?: boolean
}>()
void props

const expanded = ref(false)
</script>

<template>
  <div class="overflow-hidden rounded-[4px] border border-[#007aff]/25 bg-[#007aff]/4">
    <button
      class="flex w-full items-center gap-1.5 px-2.5 py-1.5 text-left text-[11px] text-[#0056b3] hover:bg-[#007aff]/8"
      @click="expanded = !expanded"
    >
      <!-- 思考状态：流式中呼吸圆点 / 完成后 ✓ -->
      <span v-if="streaming" class="inline-block h-2 w-2 animate-pulse rounded-full bg-[#007aff]" />
      <span v-else class="font-mono text-[#30d158]">✓</span>
      <span>{{ streaming ? '正在思考…' : `思考过程 · ${text.length} 字` }}</span>
      <span class="ml-auto font-mono">{{ expanded ? '−' : '+' }}</span>
    </button>
    <div
      v-if="expanded"
      class="max-h-[260px] overflow-y-auto whitespace-pre-wrap border-t border-[#007aff]/15 px-2.5 py-2 text-[11px] leading-relaxed text-[#3a5da8]"
    >
      {{ text }}
    </div>
  </div>
</template>
