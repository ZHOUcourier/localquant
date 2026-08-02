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
const dropUp = ref(false) // 下方空间不足时向上弹
const containerRef = ref<HTMLDivElement | null>(null)

const MENU_MAX = 264 // 菜单最大高度(px)，与模板 max-h-[264px] 一致

const selectedOption = computed(() => props.options.find((o) => o.value === model.value))

function toggle() {
  if (props.disabled) return
  if (!open.value) {
    // 打开前测量：下方放不下且上方更宽裕 → 向上弹（避免撑高页面被滚上去）
    const el = containerRef.value
    if (el) {
      const rect = el.getBoundingClientRect()
      const below = window.innerHeight - rect.bottom
      const above = rect.top
      dropUp.value = below < Math.min(MENU_MAX, 220) && above > below
    }
  }
  open.value = !open.value
}

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
      @click="toggle"
    >
      <span class="min-w-0 flex-1 truncate text-left" :class="!selectedOption && 'text-[#9a9898]'">
        {{ selectedOption ? selectedOption.label : placeholder }}
      </span>
      <span class="ml-1 shrink-0 text-[#646262]">▾</span>
    </button>
    <div
      v-if="open"
      class="absolute z-50 max-h-[264px] overflow-y-auto rounded-[4px] border bg-[#fdfcfc] py-1"
      :class="dropUp ? 'bottom-full mb-1' : 'top-full mt-1'"
      style="
        min-width: 100%;
        width: max-content;
        max-width: min(92vw, 480px);
        border-color: rgba(15, 0, 0, 0.12);
      "
    >
      <div
        v-for="option in options"
        :key="option.value"
        class="flex cursor-pointer items-center gap-2 truncate whitespace-nowrap px-3 py-1.5 text-sm transition-colors"
        :class="
          option.disabled
            ? 'text-[#9a9898] cursor-not-allowed'
            : option.value === model
              ? 'bg-[#f1eeee] text-[#201d1d] font-medium'
              : 'text-[#201d1d] hover:bg-[#f1eeee]'
        "
        :title="option.label"
        @click="handleSelect(option.value, option.disabled)"
      >
        <span class="min-w-0 flex-1 truncate">{{ option.label }}</span>
      </div>
    </div>
  </div>
</template>
