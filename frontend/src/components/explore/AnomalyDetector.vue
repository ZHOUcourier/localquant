<script setup lang="ts">
import { computed, ref } from 'vue'
import { Button, Input, Select } from '@/components/ui'

interface AnomalyResult {
  anomalies?: {
    columns: string[]
    data: unknown[][]
    row_count: number
  }
  error?: string
  code?: string
  field?: string
}

const fieldOptions = [
  { value: 'close', label: 'close' },
  { value: 'volume', label: 'volume' },
  { value: 'amount', label: 'amount' },
]

const code = ref('')
const field = ref('close')
const windowSize = ref('20')
const threshold = ref('2.0')
const result = ref<AnomalyResult | null>(null)
const loading = ref(false)

async function detect() {
  if (!code.value.trim()) return
  loading.value = true
  try {
    const res = await fetch('/api/explorer/anomaly', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        code: code.value,
        field: field.value,
        window: Number(windowSize.value) || 20,
        threshold: Number(threshold.value) || 2.0,
      }),
    })
    result.value = (await res.json()) as AnomalyResult
  } catch (err) {
    result.value = { error: String(err) }
  } finally {
    loading.value = false
  }
}

const anomalyData = computed(() => result.value?.anomalies)
</script>

<template>
  <div class="flex flex-col gap-3">
    <div class="flex items-end gap-3 flex-wrap">
      <div class="flex flex-col gap-1">
        <label class="text-xs text-[#646262]">股票代码</label>
        <div class="w-40"><Input v-model="code" placeholder="000001.SH" /></div>
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-xs text-[#646262]">字段</label>
        <div class="w-28"><Select v-model="field" :options="fieldOptions" /></div>
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-xs text-[#646262]">窗口大小</label>
        <div class="w-24"><Input v-model="windowSize" type="number" /></div>
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-xs text-[#646262]">阈值</label>
        <div class="w-24"><Input v-model="threshold" type="number" /></div>
      </div>
      <Button variant="primary" :loading="loading" @click="detect">检测</Button>
    </div>

    <div
      v-if="result?.error"
      class="rounded-[4px] border border-[#ff3b30]/30 bg-[#ff3b30]/10 px-3 py-2 text-sm text-[#ff3b30]"
    >
      {{ result.error }}
    </div>

    <template v-if="anomalyData && anomalyData.columns.length > 0">
      <div class="text-xs text-[#646262]">
        检测到 {{ anomalyData.row_count }} 个异常值（{{ result?.code }} / {{ result?.field }}）
      </div>
      <div class="rounded-[4px] border border-[rgba(15,0,0,0.12)] overflow-auto max-h-[500px]">
        <table class="w-full border-collapse text-sm">
          <thead class="sticky top-0 z-10">
            <tr class="bg-[#f8f7f7]">
              <th class="border-b border-[rgba(15,0,0,0.12)] px-3 py-2 text-left text-xs font-medium text-[#646262] w-10">
                #
              </th>
              <th
                v-for="col in anomalyData.columns"
                :key="col"
                class="border-b border-[rgba(15,0,0,0.12)] px-3 py-2 text-left text-xs font-medium text-[#646262] whitespace-nowrap"
              >
                {{ col }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(row, ri) in anomalyData.data"
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

    <div
      v-if="anomalyData && anomalyData.row_count === 0 && !result?.error"
      class="text-sm text-[#646262] py-8 text-center"
    >
      未检测到异常值
    </div>
  </div>
</template>
