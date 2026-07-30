<script setup lang="ts">
import { ref } from 'vue'
import { Button, Input } from '@/components/ui'

/** 后端 /api/explorer/correlation 返回结构 */
interface CorrelationResult {
  codes?: string[]
  matrix?: (number | null)[][]
  missing?: string[]
  n_obs?: number
  error?: string
}

/** 相关系数 → 单元格背景（对标券商终端相关性分析的分档配色） */
function corrBg(v: number | null): string {
  if (v == null) return 'transparent'
  const a = Math.abs(v)
  if (a >= 0.8) return 'rgba(0,64,133,0.85)'
  if (a >= 0.6) return 'rgba(0,90,180,0.65)'
  if (a >= 0.3) return 'rgba(0,122,255,0.4)'
  return 'rgba(0,122,255,0.15)'
}

function corrColor(v: number | null): string {
  if (v == null) return '#9a9898'
  return Math.abs(v) >= 0.6 ? '#fdfcfc' : '#201d1d'
}

/**
 * 相关性分析（对标券商终端「相关性分析」）：
 * 多标的日收益率 Pearson 相关系数矩阵，按 |ρ| 分档着色。
 */
const codesText = ref('')
const startDate = ref('')
const endDate = ref('')
const result = ref<CorrelationResult | null>(null)
const loading = ref(false)

const legend = [
  { label: '0.00 - 0.29', bg: 'rgba(0,122,255,0.15)' },
  { label: '0.30 - 0.59', bg: 'rgba(0,122,255,0.4)' },
  { label: '0.60 - 0.79', bg: 'rgba(0,90,180,0.65)' },
  { label: '0.80 - 1.00', bg: 'rgba(0,64,133,0.85)' },
]

async function analyze() {
  const codes = codesText.value
    .split(/[,，\s]+/)
    .map((s) => s.trim())
    .filter(Boolean)
  if (codes.length < 2) return
  loading.value = true
  try {
    const res = await fetch('/api/explorer/correlation', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ codes, start_date: startDate.value, end_date: endDate.value }),
    })
    result.value = await res.json()
  } catch (err) {
    result.value = { error: String(err) }
  } finally {
    loading.value = false
  }
}

function cellValue(i: number, j: number): number | null {
  return i === j ? 1 : (result.value?.matrix?.[i]?.[j] ?? null)
}
</script>

<template>
  <div class="flex flex-col gap-4">
    <div class="flex flex-wrap items-end gap-3">
      <div class="flex min-w-[320px] flex-1 flex-col gap-1">
        <label class="text-xs text-[#646262]">标的代码（逗号/空格分隔，至 少 2 个，最多 30 个）</label>
        <Input v-model="codesText" placeholder="600519.SH, 000001.SZ, 300750.SZ" />
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-xs text-[#646262]">起始日期</label>
        <div class="w-36"><Input v-model="startDate" type="date" /></div>
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-xs text-[#646262]">结束日期</label>
        <div class="w-36"><Input v-model="endDate" type="date" /></div>
      </div>
      <Button variant="primary" :loading="loading" @click="analyze">相关性分析</Button>
    </div>

    <!-- 分档图例 -->
    <div class="flex items-center gap-2 text-[11px] text-[#646262]">
      <span>|ρ| 分档:</span>
      <span
        v-for="item in legend"
        :key="item.label"
        class="rounded-[3px] px-2 py-0.5 font-mono"
        :style="{
          background: item.bg,
          color: item.bg.includes('0.15') || item.bg.includes('0.4') ? '#201d1d' : '#fdfcfc',
        }"
      >
        {{ item.label }}
      </span>
    </div>

    <div
      v-if="result?.error"
      class="rounded-[4px] border border-[#ff3b30]/30 bg-[#ff3b30]/10 px-3 py-2 text-sm text-[#ff3b30]"
    >
      {{ result.error }}
    </div>

    <div
      v-if="result?.missing && result.missing.length > 0 && !result.error"
      class="rounded-[4px] border border-[#ff9f0a]/30 bg-[#ff9f0a]/10 px-3 py-2 text-xs text-[#cc7f08]"
    >
      以下代码无本地缓存已跳过: {{ result.missing.join(', ') }}
    </div>

    <div v-if="result?.codes && result.matrix" class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] p-3">
      <div class="mb-2 text-xs text-[#646262]">
        日收益率 Pearson 相关系数矩阵（样本 {{ result.n_obs }} 个交易日）
      </div>
      <div class="overflow-x-auto">
        <table class="border-collapse font-mono text-xs">
          <thead>
            <tr>
              <th class="px-2 py-1.5 text-left text-[#646262]"> </th>
              <th v-for="c in result.codes" :key="c" class="px-2 py-1.5 text-center text-[#646262]">
                {{ c }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(rowCode, i) in result.codes" :key="rowCode">
              <td class="px-2 py-1 text-[#201d1d]">{{ rowCode }}</td>
              <td
                v-for="(colCode, j) in result.codes"
                :key="colCode"
                class="min-w-[72px] border border-[#fdfcfc] px-2 py-1.5 text-center"
                :style="{ background: corrBg(cellValue(i, j)), color: corrColor(cellValue(i, j)) }"
                :title="`${rowCode} × ${colCode}: ${cellValue(i, j) ?? '-'}`"
              >
                {{ cellValue(i, j) == null ? '-' : cellValue(i, j)!.toFixed(3) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
