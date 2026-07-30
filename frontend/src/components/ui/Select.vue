<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

export interface SelectOption {
  value: string
  label: string
  disabled?: boolean
}

const props = withDefaults(
  defineProps<{
    options: SelectOption[]
    placeholder?: string
    disabled?: boolean
  }>(),
  { placeholder: '请选择', disabled: false },
)

const model = defineModel<string>({ default: '' })
const emit = defineEmits<{ change: [value: string] }>()

const open = ref(false)
const containerRef = ref<HTMLDivElement | null>(null)

const selectedOption = computed(() => props.options.find((o) => o.value === model.value))

function handleClickOutside(e: MouseEvent) {
  if (containerRef.value && !containerRef.value.contains(e.target as Node)) {
    open.value = false
  }
}
onMounted(() => document.addEventListener('mousedown', handleClickOutside))
onUnmounted(() => document.removeEventListener('mousedown', handleClickOutside))

function handleSelect(val: string, optionDisabled?: boolean) {
  if (optionDisabled) return
  model.value = val
  emit('change', val)
  open.value = false
}
</script>

<template>
  <div ref="containerRef" class="relative">
    <button
      type="button"
      class="flex w-full items-center justify-between rounded-[4px] border bg-[#f8f7f7] px-3 py-1.5 text-sm text-[#201d1d] transition-colors cursor-pointer"
      :class="[open && 'border-[#201d1d] bg-[#fdfcfc]', disabled && 'opacity-50 cursor-not-allowed']"
      :style="{ borderColor: open ? '#201d1d' : 'rgba(15, 0, 0, 0.12)' }"
      :disabled="disabled"
      @click="open = !open"
    >
      <span :class="!selectedOption && 'text-[#9a9898]'">
        {{ selectedOption ? selectedOption.label : placeholder }}
      </span>
      <span class="ml-2 text-[#646262]">▾</span>
    </button>
    <div
      v-if="open"
      class="absolute z-50 mt-1 w-full rounded-[4px] border bg-[#fdfcfc] py-1"
      style="border-color: rgba(15, 0, 0, 0.12)"
    >
      <div
        v-for="option in options"
        :key="option.value"
        class="cursor-pointer px-3 py-1.5 text-sm transition-colors"
        :class="
          option.disabled
            ? 'text-[#9a9898] cursor-not-allowed'
            : option.value === model
              ? 'bg-[#f1eeee] text-[#201d1d] font-medium'
              : 'text-[#201d1d] hover:bg-[#f1eeee]'
        "
        @click="handleSelect(option.value, option.disabled)"
      >
        {{ option.label }}
      </div>
    </div>
  </div>
</template>
