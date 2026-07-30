<script setup lang="ts" generic="T extends Record<string, any>">
export interface Column {
  key: string
  title: string
  dataIndex: string
  width?: string | number
}

const props = withDefaults(
  defineProps<{
    columns: Column[]
    dataSource: T[]
    rowKey?: string | ((record: T) => string)
  }>(),
  { rowKey: 'id' },
)

const emit = defineEmits<{ rowClick: [record: T, index: number] }>()

function getRowKey(record: T, index: number): string {
  if (typeof props.rowKey === 'function') return props.rowKey(record)
  return String(record[props.rowKey] ?? index)
}
</script>

<template>
  <table class="w-full border-collapse text-sm">
    <thead>
      <tr class="bg-[#f8f7f7]">
        <th
          v-for="col in columns"
          :key="col.key"
          class="px-3 py-2 text-left text-xs font-medium text-[#646262]"
          :style="{ borderBottom: '1px solid rgba(15, 0, 0, 0.12)', width: typeof col.width === 'number' ? `${col.width}px` : col.width }"
        >
          {{ col.title }}
        </th>
      </tr>
    </thead>
    <tbody>
      <tr
        v-for="(record, rowIndex) in dataSource"
        :key="getRowKey(record, rowIndex)"
        class="transition-colors hover:bg-[#f1eeee]"
        style="border-bottom: 1px solid rgba(15, 0, 0, 0.12)"
        @click="emit('rowClick', record, rowIndex)"
      >
        <td v-for="col in columns" :key="col.key" class="px-3 py-2 text-[#201d1d]">
          <!-- 自定义单元格渲染：<template #cell-{key}="{ value, record, index }"> -->
          <slot
            :name="`cell-${col.key}`"
            :value="record[col.dataIndex]"
            :record="record"
            :index="rowIndex"
          >
            {{ String(record[col.dataIndex] ?? '') }}
          </slot>
        </td>
      </tr>
    </tbody>
  </table>
</template>
