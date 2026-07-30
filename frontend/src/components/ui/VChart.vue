<script setup lang="ts">
/**
 * VChart — ECharts 轻封装（替代 echarts-for-react；recharts 用法统一迁到此组件）
 * 自动 init/setOption/resize/dispose；option 变化时增量更新。
 */
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'

const props = withDefaults(
  defineProps<{
    option: Record<string, unknown>
    height?: number | string
    /** notMerge 更新（结构变化大的图表建议 true） */
    notMerge?: boolean
  }>(),
  { height: 300, notMerge: true },
)

const emit = defineEmits<{ chartClick: [params: unknown] }>()

const el = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null
let resizeObserver: ResizeObserver | null = null

onMounted(() => {
  if (!el.value) return
  chart = echarts.init(el.value)
  chart.setOption(props.option, { notMerge: props.notMerge })
  chart.on('click', (params) => emit('chartClick', params))
  resizeObserver = new ResizeObserver(() => chart?.resize())
  resizeObserver.observe(el.value)
})

watch(
  () => props.option,
  (opt) => {
    chart?.setOption(opt, { notMerge: props.notMerge })
  },
  { deep: true },
)

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div ref="el" :style="{ height: typeof height === 'number' ? `${height}px` : height, width: '100%' }" />
</template>
