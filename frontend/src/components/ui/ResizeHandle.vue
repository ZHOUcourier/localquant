<script setup lang="ts">
/**
 * ResizeHandle — VSCode 风格面板拖宽手柄
 *
 * - 常态透明；hover/拖动中显示完全不透明 accent 蓝（#007aff），由细渐粗
 * - 中央浮标带「左右调节」图标（ChevronsLeftRight），hover 时出现
 * - side：手柄贴在宿主面板的哪条边（宿主需 position:relative）
 */
import { ref } from 'vue'
import { ChevronsLeftRight } from 'lucide-vue-next'

const props = defineProps<{
  side: 'left' | 'right'
  dragging?: boolean
}>()

const emit = defineEmits<{ dragStart: [e: MouseEvent]; dblclick: [] }>()

const hovered = ref(false)
void props
</script>

<template>
  <div
    class="group/handle absolute top-0 z-30 flex h-full w-[7px] cursor-ew-resize items-center justify-center"
    :class="side === 'left' ? '-left-[3px]' : '-right-[3px]'"
    @mouseenter="hovered = true"
    @mouseleave="hovered = false"
    @mousedown.prevent="(e) => emit('dragStart', e)"
    @dblclick="emit('dblclick')"
  >
    <!-- 蓝条：常态 0 宽，hover 2px，拖动中 4px，全程完全不透明 #007aff -->
    <div
      class="h-full transition-all duration-100"
      :style="{
        width: dragging ? '4px' : hovered ? '2px' : '0px',
        background: '#007aff',
      }"
    />
    <!-- 左右调节浮标（hover/拖动时出现） -->
    <div
      v-if="hovered || dragging"
      class="absolute top-1/2 flex h-6 w-4 -translate-y-1/2 items-center justify-center rounded-[3px] bg-[#007aff] text-white"
    >
      <ChevronsLeftRight :size="11" />
    </div>
  </div>
</template>
