<script setup lang="ts">
defineProps<{
  maxHeight?: string | number
  horizontal?: boolean
}>()
</script>

<template>
  <div
    class="overflow-auto"
    :class="horizontal && 'overflow-x-auto'"
    :style="{ maxHeight: typeof maxHeight === 'number' ? `${maxHeight}px` : maxHeight }"
  >
    <slot />
  </div>
</template>
