<script setup lang="ts">
defineProps<{ title?: string }>()
</script>

<template>
  <div class="rounded-[4px] border bg-[#f1eeee]" style="border-color: rgba(15, 0, 0, 0.12)">
    <div
      v-if="title || $slots.title || $slots.extra"
      class="flex items-center justify-between px-3 py-2"
      style="border-bottom: 1px solid rgba(15, 0, 0, 0.12)"
    >
      <div v-if="title || $slots.title" class="text-sm font-medium text-[#201d1d]">
        <slot name="title">{{ title }}</slot>
      </div>
      <div v-if="$slots.extra" class="flex items-center gap-2"><slot name="extra" /></div>
    </div>
    <div class="p-3"><slot /></div>
  </div>
</template>
