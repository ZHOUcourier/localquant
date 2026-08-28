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

const sql = ref("SELECT trade_date, code, open, high, low, close, volume FROM quotes_1d ORDER BY trade_date DESC LIMIT 20;")
const result = ref<QueryResult | null>(null)
const loading = ref(false)
// AI：自然语言生成 SQL / 结果解读
const aiQuestion = ref('')
const aiGenLoading = ref(false)
const aiInsight = ref<string | null>(null)
const aiInsightLoading = ref(false)
const aiError = ref<string | null>(null)

interface SavedQuery {
  id: number
  name: string
  sql: string
  last_used_at?: number | null
}
const savedQueries = ref<SavedQuery[]>([])
const saveName = ref('')
const saveMsg = ref('')

interface QueryTemplate {
  id: string
  name: string
  sql: string
  note?: string
}
interface FieldInfo {
  name: string
  description: string
}
const templates = ref<QueryTemplate[]>([])
const fieldDictionary = ref<FieldInfo[]>([])

async function loadSchema() {
  try {
    const res = await fetch('/api/explorer/schema')
    if (!res.ok) return
    const data = await res.json()
    templates.value = data.templates ?? []
    const quoteTable = (data.tables ?? []).find((t: { kind?: string }) => t.kind === 'quotes')
    fieldDictionary.value = quoteTable?.fields ?? []
  } catch {
    /* 数据字典加载失败不阻断编辑 */
  }
}
loadSchema()

function applyTemplate(t: QueryTemplate) {
  sql.value = t.sql
}

async function loadSaved() {
  try {
    const res = await fetch('/api/explorer/sql/queries')
    if (res.ok) savedQueries.value = (await res.json()).queries ?? []
  } catch {
    /* 历史列表加载失败不阻断 SQL 编辑 */
  }
}
loadSaved()

async function saveQuery() {
  if (!saveName.value.trim() || !sql.value.trim()) return
  try {
    const res = await fetch('/api/explorer/sql/queries', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: saveName.value.trim(), sql: sql.value }),
    })
    if (!res.ok) throw new Error(await res.text())
    saveMsg.value = `已保存「${saveName.value.trim()}」`
    saveName.value = ''
    await loadSaved()
  } catch (e) {
    saveMsg.value = e instanceof Error ? e.message : String(e)
  }
}

async function removeQuery(id: number) {
  try {
    await fetch(`/api/explorer/sql/queries/${id}`, { method: 'DELETE' })
    savedQueries.value = savedQueries.value.filter((q) => q.id !== id)
  } catch {
    /* ignore */
  }
}

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

    <div v-if="templates.length" class="flex flex-wrap items-center gap-1.5">
      <span class="text-[11px] text-[#9a9898]">模板:</span>
      <button
        v-for="t in templates"
        :key="t.id"
        type="button"
        class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2 py-1 text-[11px] text-[#646262] hover:text-[#201d1d] cursor-pointer"
        :title="t.note || t.name"
        @click="applyTemplate(t)"
      >
        {{ t.name }}
      </button>
    </div>

    <div v-if="fieldDictionary.length" class="flex flex-wrap gap-x-3 gap-y-1 rounded-[4px] border border-[rgba(15,0,0,0.08)] bg-[#f8f7f7] px-2 py-1.5">
      <span
        v-for="f in fieldDictionary"
        :key="f.name"
        class="text-[10px] text-[#9a9898]"
        :title="f.description"
      >
        {{ f.name }}<span v-if="f.description">: {{ f.description }}</span>
      </span>
    </div>

    <div v-if="savedQueries.length" class="flex flex-wrap items-center gap-1.5">
      <span class="text-[11px] text-[#9a9898]">历史/收藏:</span>
      <button
        v-for="q in savedQueries.slice(0, 12)"
        :key="q.id"
        type="button"
        class="group inline-flex items-center gap-1 rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2 py-1 text-[11px] text-[#646262] hover:text-[#201d1d] cursor-pointer"
        title="点击填入编辑器"
        @click="sql = q.sql"
      >
        {{ q.name }}
        <span class="text-[#9a9898] opacity-0 group-hover:opacity-100" title="删除" @click.stop="removeQuery(q.id)">×</span>
      </button>
    </div>

    <div class="flex items-center gap-2">
      <input
        v-model="saveName"
        type="text"
        placeholder="给这条 SQL 起个名字后保存"
        class="min-w-[180px] flex-1 rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2 py-1 text-xs outline-none placeholder:text-[#9a9898]"
      />
      <Button variant="secondary" size="sm" :disabled="!saveName.trim() || !sql.trim()" @click="saveQuery">保存 SQL</Button>
      <span v-if="saveMsg" class="text-[11px] text-[#248a3d]">{{ saveMsg }}</span>
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
