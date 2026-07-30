<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'

const props = defineProps<{
  open: boolean
  title?: string
}>()

const emit = defineEmits<{ close: [] }>()

function handleEsc(e: KeyboardEvent) {
  if (e.key === 'Escape' && props.open) emit('close')
}
onMounted(() => document.addEventListener('keydown', handleEsc))
onUnmounted(() => document.removeEventListener('keydown', handleEsc))
</script>

<template>
  <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center">
    <div class="absolute inset-0 bg-black/40" @click="emit('close')" />
    <div
      class="relative z-10 flex max-h-[90vh] min-w-[320px] max-w-[90vw] flex-col rounded-[4px] border bg-[#fdfcfc]"
      style="border-color: rgba(15, 0, 0, 0.12)"
    >
      <div
        v-if="title || $slots.title"
        class="flex shrink-0 items-center justify-between px-4 py-3"
        style="border-bottom: 1px solid rgba(15, 0, 0, 0.12)"
      >
        <div class="text-sm font-medium text-[#201d1d]"><slot name="title">{{ title }}</slot></div>
        <button
          type="button"
          class="text-[#646262] hover:text-[#201d1d] transition-colors cursor-pointer"
          @click="emit('close')"
        >
          ✕
        </button>
      </div>
      <div class="min-h-0 flex-1 overflow-auto px-4 py-3 text-sm text-[#201d1d]"><slot /></div>
      <div
        v-if="$slots.footer"
        class="flex shrink-0 items-center justify-end gap-2 px-4 py-3"
        style="border-top: 1px solid rgba(15, 0, 0, 0.12)"
      >
        <slot name="footer" />
      </div>
    </div>
  </div>
</template>
