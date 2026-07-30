<script setup lang="ts">
import { ref } from 'vue'
import { Button, Input } from '@/components/ui'

interface ScanResult {
  columns: string[]
  data: unknown[][]
  row_count: number
  error?: string
}

const date = ref('')
const conditions = ref('close > 10')
const result = ref<ScanResult | null>(null)
const loading = ref(false)

async function scan() {
  if (!date.value.trim()) return
  loading.value = true
  try {
    const conditionList = conditions.value
      .split(';')
      .map((s) => s.trim())
      .filter(Boolean)
    const res = await fetch('/api/explorer/scan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date: date.value, conditions: conditionList }),
    })
    result.value = (await res.json()) as ScanResult
  } catch (err) {
    result.value = { columns: [], data: [], row_count: 0, error: String(err) }
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="flex flex-col gap-3">
    <div class="flex items-end gap-3">
      <div class="flex flex-col gap-1">
        <label class="text-xs text-[#646262]">日期</label>
        <div class="w-40"><Input v-model="date" placeholder="2024-01-02" /></div>
      </div>
      <div class="flex flex-col gap-1 flex-1">
        <label class="text-xs text-[#646262]">筛选条件（多条用分号分隔）</label>
        <Input v-model="conditions" placeholder="close > 10" />
      </div>
      <Button variant="primary" :loading="loading" @click="scan">扫描</Button>
    </div>

    <div
      v-if="result?.error"
      class="rounded-[4px] border border-[#ff3b30]/30 bg-[#ff3b30]/10 px-3 py-2 text-sm text-[#ff3b30]"
    >
      {{ result.error }}
    </div>

    <template v-if="result && result.columns.length > 0">
      <div class="text-xs text-[#646262]">共 {{ result.row_count }} 条结果</div>
      <div class="rounded-[4px] border border-[rgba(15,0,0,0.12)] overflow-auto max-h-[500px]">
        <table class="w-full border-collapse text-sm">
          <thead class="sticky top-0 z-10">
            <tr class="bg-[#f8f7f7]">
              <th class="border-b border-[rgba(15,0,0,0.12)] px-3 py-2 text-left text-xs font-medium text-[#646262] w-10">
                #
              </th>
              <th
                v-for="col in result.columns"
                :key="col"
                class="border-b border-[rgba(15,0,0,0.12)] px-3 py-2 text-left text-xs font-medium text-[#646262] whitespace-nowrap"
              >
                {{ col }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(row, ri) in result.data"
              :key="ri"
              class="border-b border-[rgba(15,0,0,0.12)] hover:bg-[#f1eeee] transition-colors"
            >
              <td class="px-3 py-1.5 text-xs text-[#646262]">{{ ri + 1 }}</td>
              <td
                v-for="(val, ci) in row"
                :key="ci"
                class="px-3 py-1.5 text-[#201d1d] whitespace-nowrap font-mono text-xs"
              >
                <span v-if="val === null" class="text-[#9a9898]">NULL</span>
                <template v-else>{{ String(val) }}</template>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <div v-if="result && result.row_count === 0 && !result.error" class="text-sm text-[#646262] py-8 text-center">
      无匹配数据
    </div>
  </div>
</template>
