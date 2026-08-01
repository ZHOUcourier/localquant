<script setup lang="ts">
import { computed } from 'vue'
import { cn } from '@/lib/utils'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
export type ButtonSize = 'sm' | 'md' | 'lg'

const props = withDefaults(
  defineProps<{
    variant?: ButtonVariant
    size?: ButtonSize
    loading?: boolean
    disabled?: boolean
    type?: 'button' | 'submit'
  }>(),
  { variant: 'secondary', size: 'md', loading: false, disabled: false, type: 'button' },
)

const variantStyles: Record<ButtonVariant, string> = {
  primary:
    'bg-[#201d1d] text-[#fdfcfc] border-none hover:bg-[#302c2c] active:bg-[#0f0000] disabled:bg-[#f1eeee] disabled:text-[#9a9898]',
  secondary:
    'bg-[#fdfcfc] text-[#201d1d] border border-[#646262] hover:bg-[#f1eeee] active:bg-[#f1eeee] disabled:border-[rgba(15,0,0,0.12)] disabled:bg-[#f1eeee] disabled:text-[#9a9898]',
  ghost: 'bg-transparent text-[#201d1d] border border-transparent hover:bg-[#f1eeee] disabled:text-[#9a9898]',
  danger:
    'bg-[#ff3b30] text-[#fdfcfc] border-none hover:bg-[#d70015] active:bg-[#a50011] disabled:bg-[#f1eeee] disabled:text-[#9a9898]',
}

const sizeStyles: Record<ButtonSize, string> = {
  sm: 'px-2 py-1 text-xs',
  md: 'px-3 py-1.5 text-sm',
  lg: 'px-4 py-2 text-base',
}

const classes = computed(() =>
  cn(
    'press inline-flex items-center justify-center rounded-[4px] font-medium transition-colors duration-150 cursor-pointer',
    variantStyles[props.variant],
    sizeStyles[props.size],
    (props.disabled || props.loading) && 'cursor-not-allowed opacity-70',
  ),
)
</script>

<template>
  <button :type="type" :class="classes" :disabled="disabled || loading">
    <span
      v-if="loading"
      class="mr-1.5 inline-block h-3 w-3 animate-spin rounded-full border border-current border-t-transparent"
    />
    <slot />
  </button>
</template>
