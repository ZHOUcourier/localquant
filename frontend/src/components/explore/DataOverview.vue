<script setup lang="ts">
/**
 * DataOverview — 本地数据概览
 *
 * 展示各周期 Parquet 缓存的表结构、股票数量、数据区间与可用代码，
 * 为 SQL 查询 / 扫描 / 截面分析提供数据地图。
 */
import { computed } from 'vue'
import { useQuery } from '@tanstack/vue-query'

interface TableInfo {
  period: string
  path: string
  stock_count: number
  columns: string[]
  sample_range: string
  codes: string[]
}

async function fetchTables(): Promise<{ tables: TableInfo[] }> {
  const res = await fetch('/api/explorer/tables')
  if (!res.ok) throw new Error(`Failed to fetch tables: ${res.status}`)
  return res.json()
}

const { data, isLoading } = useQuery({
  queryKey: ['explorer-tables'],
  queryFn: fetchTables,
  staleTime: 60 * 1000,
})

const tables = computed(() => data.value?.tables ?? [])
</script>

<template>
  <div v-if="isLoading" class="py-8 text-center text-xs text-[#646262]">加载中...</div>

  <div
    v-else-if="tables.length === 0"
    class="rounded-[4px] border border-[rgba(15,0,0,0.12)] px-4 py-10 text-center text-sm text-[#646262]"
  >
    本地暂无行情缓存数据
    <div class="mt-2 text-xs text-[#9a9898]">
      请先在「数据下载」标签页下载行情，数据将缓存到 data/cache/ 供 SQL 查询与探索分析使用
    </div>
  </div>

  <div v-else class="flex flex-col gap-4">
    <div
      v-for="t in tables"
      :key="t.period"
      class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f1eeee] p-4"
    >
      <div class="mb-2 flex items-center justify-between">
        <span class="text-sm font-medium text-[#201d1d]">[{{ t.period }}] 行情数据</span>
        <span class="text-xs text-[#646262]">
          {{ t.stock_count }} 只股票 · {{ t.sample_range || '区间未知' }}
        </span>
      </div>
      <div class="mb-2 text-xs text-[#646262]">
        SQL 路径：
        <code class="rounded-[3px] bg-[#201d1d] px-1.5 py-0.5 text-[11px] text-[#fdfcfc]">
          read_parquet('{{ t.path }}')
        </code>
      </div>
      <div class="mb-2 flex flex-wrap gap-1">
        <span class="text-xs text-[#9a9898]">字段：</span>
        <span
          v-for="c in t.columns"
          :key="c"
          class="rounded-[3px] border border-[rgba(15,0,0,0.10)] bg-[#fdfcfc] px-1.5 py-0.5 text-[11px] text-[#201d1d]"
        >
          {{ c }}
        </span>
      </div>
      <details class="text-xs text-[#646262]">
        <summary class="cursor-pointer select-none hover:text-[#201d1d]">
          查看已缓存股票代码（前 {{ t.codes.length }} 个）
        </summary>
        <div class="mt-2 flex max-h-[120px] flex-wrap gap-1 overflow-auto">
          <span
            v-for="c in t.codes"
            :key="c"
            class="rounded-[3px] bg-[#fdfcfc] px-1.5 py-0.5 font-mono text-[11px]"
          >
            {{ c }}
          </span>
        </div>
      </details>
    </div>
  </div>
</template>
