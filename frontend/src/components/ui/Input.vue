<script setup lang="ts">
withDefaults(
  defineProps<{
    placeholder?: string
    disabled?: boolean
    type?: string
  }>(),
  { placeholder: '', disabled: false, type: 'text' },
)

const model = defineModel<string>({ default: '' })
</script>

<template>
  <div
    class="flex items-center rounded-[4px] border bg-[#f8f7f7] transition-colors focus-within:border-[#201d1d] focus-within:bg-[#fdfcfc]"
    :class="disabled && 'opacity-50 cursor-not-allowed'"
    style="border-color: rgba(15, 0, 0, 0.12)"
  >
    <span v-if="$slots.prefix" class="pl-2 text-[#646262] flex-shrink-0"><slot name="prefix" /></span>
    <input
      v-model="model"
      :type="type"
      :disabled="disabled"
      :placeholder="placeholder"
      class="w-full bg-transparent px-3 py-1.5 text-sm text-[#201d1d] outline-none font-mono placeholder:text-[#9a9898]"
    />
    <span v-if="$slots.suffix" class="pr-2 text-[#646262] flex-shrink-0"><slot name="suffix" /></span>
  </div>
</template>
