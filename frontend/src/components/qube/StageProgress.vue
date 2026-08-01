<script setup lang="ts">
/**
 * StageProgress — 阶段进度（因子分析 9 阶段 / 回测 8 阶段共用）
 * 复刻参考站：总进度条 + 阶段 pill 网格；语义色按 opencode 映射
 * （done=success / running=accent / error=danger / pending=mute）。
 */
import type { Progress } from './types'

const props = defineProps<{
  progress: Progress | null
  title: string
  subtitle?: string
}>()

function pillClass(status: string): string {
  switch (status) {
    case 'done':
      return 'border-[#30d158]/30 bg-[#30d158]/8 text-[#1d8a3e]'
    case 'running':
      return 'border-[#007aff]/30 bg-[#007aff]/8 text-[#0056b3] animate-pulse'
    case 'error':
      return 'border-[#ff3b30]/40 bg-[#ff3b30]/8 text-[#c62d23]'
    default:
      return 'border-[rgba(15,0,0,0.1)] text-[#9a9898]'
  }
}

function pillMark(status: string): string {
  if (status === 'done') return '✓ '
  if (status === 'error') return '✗ '
  return ''
}

const percentColor = () =>
  props.progress?.stages.some((s) => s.status === 'error') ? '#ff3b30' : '#30d158'
</script>

<template>
  <div
    v-if="progress"
    class="rounded-[4px] border bg-[#fdfcfc] p-3"
    :style="{
      borderColor: progress.stages.some((s) => s.status === 'error')
        ? 'rgba(255,59,48,0.35)'
        : progress.percent >= 100
          ? 'rgba(48,209,88,0.35)'
          : 'rgba(15,0,0,0.12)',
    }"
  >
    <div class="mb-2 flex items-center justify-between gap-2">
      <div class="min-w-0">
        <div class="truncate text-xs font-semibold text-[#201d1d]">{{ title }}</div>
        <div v-if="subtitle" class="mt-0.5 truncate text-[10px] text-[#9a9898]">{{ subtitle }}</div>
      </div>
      <span class="shrink-0 font-mono text-xs font-semibold" :style="{ color: percentColor() }">
        {{ progress.percent }}%
      </span>
    </div>
    <div class="mb-2 h-1.5 overflow-hidden rounded-full bg-[#f1eeee]">
      <div
        class="h-full rounded-full transition-[width] duration-300"
        :style="{ width: `${progress.percent}%`, background: percentColor() }"
      />
    </div>
    <div class="grid grid-cols-3 gap-1">
      <div
        v-for="s in progress.stages"
        :key="s.code"
        class="truncate rounded-[4px] border px-1.5 py-1 text-center text-[10px]"
        :class="pillClass(s.status)"
        :title="s.label"
      >
        {{ pillMark(s.status) }}{{ s.label }}
      </div>
    </div>
  </div>
</template>
