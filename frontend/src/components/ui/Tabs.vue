<script setup lang="ts">
import { ref, watch } from 'vue'
import type { TabItem } from './types'

const props = defineProps<{
  items: TabItem[]
  activeKey?: string
  defaultActiveKey?: string
}>()

const emit = defineEmits<{ change: [key: string] }>()

const internalKey = ref(props.defaultActiveKey ?? props.activeKey ?? props.items[0]?.key ?? '')
watch(
  () => props.activeKey,
  (v) => {
    if (v != null) internalKey.value = v
  },
)

function handleClick(key: string, disabled?: boolean) {
  if (disabled) return
  internalKey.value = key
  emit('change', key)
}
</script>

<template>
  <div class="flex flex-col">
    <div class="flex" style="border-bottom: 1px solid rgba(15, 0, 0, 0.12)">
      <button
        v-for="item in items"
        :key="item.key"
        type="button"
        class="relative px-3 py-2 text-sm transition-colors cursor-pointer"
        :class="
          item.disabled
            ? 'text-[#9a9898] cursor-not-allowed'
            : internalKey === item.key
              ? 'text-[#201d1d]'
              : 'text-[#646262] hover:text-[#201d1d]'
        "
        @click="handleClick(item.key, item.disabled)"
      >
        {{ item.label }}
        <span
          v-if="item.badge"
          class="ml-1 inline-block rounded-[3px] bg-[rgba(255,159,10,0.15)] px-1 align-middle text-[10px] font-medium leading-4 text-[#cc7f08]"
          >{{ item.badge }}</span
        >
        <span
          v-if="internalKey === item.key"
          class="absolute bottom-0 left-0 right-0 h-[2px] bg-[#9a9898]"
        />
      </button>
    </div>
  </div>
</template>
