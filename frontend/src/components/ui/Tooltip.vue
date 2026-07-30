<script setup lang="ts">
import { onUnmounted, ref } from 'vue'

export type TooltipPlacement = 'top' | 'bottom' | 'left' | 'right'

const props = withDefaults(
  defineProps<{
    content: string
    placement?: TooltipPlacement
    delay?: number
  }>(),
  { placement: 'top', delay: 200 },
)

const placementStyles: Record<TooltipPlacement, string> = {
  top: 'bottom-full left-1/2 -translate-x-1/2 mb-1.5',
  bottom: 'top-full left-1/2 -translate-x-1/2 mt-1.5',
  left: 'right-full top-1/2 -translate-y-1/2 mr-1.5',
  right: 'left-full top-1/2 -translate-y-1/2 ml-1.5',
}

const visible = ref(false)
let timeout: ReturnType<typeof setTimeout> | null = null

function handleMouseEnter() {
  timeout = setTimeout(() => (visible.value = true), props.delay)
}
function handleMouseLeave() {
  if (timeout) {
    clearTimeout(timeout)
    timeout = null
  }
  visible.value = false
}
onUnmounted(() => {
  if (timeout) clearTimeout(timeout)
})
</script>

<template>
  <div class="relative inline-flex" @mouseenter="handleMouseEnter" @mouseleave="handleMouseLeave">
    <slot />
    <div
      v-if="visible"
      class="pointer-events-none absolute z-50 whitespace-nowrap rounded-[4px] border bg-[#201d1d] px-2 py-1 text-xs text-[#fdfcfc]"
      :class="placementStyles[placement]"
      style="border-color: rgba(15, 0, 0, 0.12)"
    >
      <slot name="content">{{ content }}</slot>
    </div>
  </div>
</template>
