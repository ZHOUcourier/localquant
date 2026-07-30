<script setup lang="ts">
import { ref } from 'vue'
import { Sparkles } from 'lucide-vue-next'
import { Button, CodeEditor, Input } from '@/components/ui'

interface QueryResult {
  columns: string[]
  data: unknown[][]
  row_count: number
  error?: string
}

const sql = ref("SELECT * FROM read_parquet('data/cache/1d/*.parquet') LIMIT 20;")
const result = ref<QueryResult | null>(null)
const loading = ref(false)
// AI：自然语言生成 SQL / 结果解读
const aiQuestion = ref('')
const aiGenLoading = ref(false)
const aiInsight = ref<string | null>(null)
const aiInsightLoading = ref(false)
const aiError = ref<string | null>(null)

async function execute() {
  if (!sql.value.trim()) return
  loading.value = true
  aiInsight.value = null
  try {
    const res = await fetch('/api/explorer/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sql: sql.value }),
    })
    result.value = (await res.json()) as QueryResult
  } catch (err) {
    result.value = { columns: [], data: [], row_count: 0, error: String(err) }
  } finally {
    loading.value = false
  }
}

// AI：自然语言 → SQL（填入编辑器，由用户确认执行）
async function handleAIGenerate() {
  if (!aiQuestion.value.trim()) return
  aiGenLoading.value = true
  aiError.value = null
  try {
    const res = await fetch('/api/ai/explore-sql', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: aiQuestion.value }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => null)
      throw new Error(err?.detail || `HTTP ${res.status}`)
    }
    const data = await res.json()
    if (data.sql) sql.value = data.sql
  } catch (e) {
    aiError.value = e instanceof Error ? e.message : String(e)
  } finally {
    aiGenLoading.value = false
  }
}

// AI：解读查询结果
async function handleAIInsight() {
  if (!result.value || result.value.columns.length === 0) return
  aiInsightLoading.value = true
  aiError.value = null
  try {
    const res = await fetch('/api/ai/explore-insight', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        columns: result.value.columns,
        rows: result.value.data.slice(0, 50),
        context: `SQL: ${sql.value}`,
      }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => null)
      throw new Error(err?.detail || `HTTP ${res.status}`)
    }
    const data = await res.json()
    aiInsight.value = data.insight || ''
  } catch (e) {
    aiError.value = e instanceof Error ? e.message : String(e)
  } finally {
    aiInsightLoading.value = false
  }
}
</script>

<template>
  <div class="flex flex-col gap-3">
    <!-- AI 生成 SQL -->
    <div class="flex items-center gap-2">
      <div class="flex-1">
        <Input
          v-model="aiQuestion"
          placeholder="✦ 用自然语言描述查询，AI 生成 SQL（如：查平安银行最近 30 天收盘价）"
          @keydown.enter="handleAIGenerate"
        />
      </div>
      <button
        type="button"
        :disabled="aiGenLoading || !aiQuestion.trim()"
        class="flex shrink-0 items-center gap-1.5 rounded-[4px] border border-[rgba(124,58,237,0.4)] bg-[#fdfcfc] px-3 py-1.5 text-xs font-medium text-[#7c3aed] transition-colors hover:bg-[#f8f7f7] disabled:opacity-50 cursor-pointer"
        @click="handleAIGenerate"
      >
        <Sparkles :size="12" />
        {{ aiGenLoading ? '生成中...' : 'AI 生成 SQL' }}
      </button>
    </div>

    <div
      v-if="aiError"
      class="rounded-[4px] border border-[#ff3b30]/30 bg-[#ff3b30]/10 px-3 py-2 text-xs text-[#ff3b30]"
    >
      {{ aiError }}
    </div>

    <CodeEditor v-model="sql" language="sql" :height="200" title="SQL 查询编辑" :font-size="13" />

    <div class="flex items-center gap-2">
      <Button variant="primary" :loading="loading" @click="execute">执行</Button>
      <span v-if="result && !result.error" class="text-xs text-[#646262]">
        返回 {{ result.row_count }} 行
      </span>
      <button
        v-if="result && !result.error && result.columns.length > 0"
        type="button"
        :disabled="aiInsightLoading"
        class="flex items-center gap-1 rounded-[4px] border border-[rgba(124,58,237,0.4)] bg-[#fdfcfc] px-2.5 py-1 text-xs text-[#7c3aed] transition-colors hover:bg-[#f8f7f7] disabled:opacity-50 cursor-pointer"
        @click="handleAIInsight"
      >
        <Sparkles :size="11" />
        {{ aiInsightLoading ? '解读中...' : 'AI 解读结果' }}
      </button>
    </div>

    <div
      v-if="aiInsight"
      class="whitespace-pre-wrap rounded-[4px] border border-[rgba(124,58,237,0.3)] bg-[#f8f7f7] px-3 py-2.5 text-xs leading-relaxed text-[#424245]"
    >
      {{ aiInsight }}
    </div>

    <div
      v-if="result?.error"
      class="rounded-[4px] border border-[#ff3b30]/30 bg-[#ff3b30]/10 px-3 py-2 text-sm text-[#ff3b30]"
    >
      {{ result.error }}
    </div>

    <div
      v-if="result && result.columns.length > 0"
      class="rounded-[4px] border border-[rgba(15,0,0,0.12)] overflow-auto max-h-[400px]"
    >
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
  </div>
</template>
