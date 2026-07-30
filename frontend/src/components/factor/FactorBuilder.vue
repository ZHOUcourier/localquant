<script setup lang="ts">
import { computed, ref } from 'vue'
import { Card, Tabs, Input, Button, ScrollArea, CodeEditor, Dialog } from '@/components/ui'
import type { TabItem } from '@/components/ui'
import type { FactorResult } from './types'

const emit = defineEmits<{ factorComputed: [result: FactorResult] }>()

const builderTabs: TabItem[] = [
  { key: 'formula', label: '公式模式' },
  { key: 'code', label: '代码模式' },
]

const defaultCode = `import pandas as pd
import numpy as np

def compute_factor(close: pd.DataFrame, volume: pd.DataFrame) -> pd.DataFrame:
    """
    自定义因子计算函数
    :param close: 收盘价 DataFrame (index=date, columns=stocks)
    :param volume: 成交量 DataFrame
    :return: 因子值 DataFrame
    """
    # 示例: 5日动量
    ret = close.pct_change(5)
    return ret
`

const mode = ref('formula')
const formula = ref('')
const code = ref(defaultCode)
const pool = ref('')
const startDate = ref('')
const endDate = ref('')
const computing = ref(false)
const error = ref<string | null>(null)
const preview = ref<FactorResult | null>(null)
// AI 生成/修改因子（公式与代码模式共用，与工作流节点 ✦ AI 交互一致）
const showAI = ref(false)
const aiInstruction = ref('')
const aiLoading = ref(false)
const aiError = ref<string | null>(null)

async function handleAI() {
  if (!aiInstruction.value.trim()) return
  aiLoading.value = true
  aiError.value = null
  try {
    const res = await fetch('/api/ai/factor-code', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        mode: mode.value,
        current: mode.value === 'formula' ? formula.value : code.value,
        instruction: aiInstruction.value,
      }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => null)
      throw new Error(err?.detail || `HTTP ${res.status}`)
    }
    const data = await res.json()
    // 结果填入编辑器，由用户确认后自行点「计算因子」
    if (mode.value === 'formula') formula.value = data.content || ''
    else code.value = data.content || ''
    showAI.value = false
    aiInstruction.value = ''
  } catch (e) {
    aiError.value = e instanceof Error ? e.message : String(e)
  } finally {
    aiLoading.value = false
  }
}

async function handleCompute() {
  computing.value = true
  error.value = null
  try {
    // 调用后端基于本地真实行情数据计算因子
    const res = await fetch('/api/factor/compute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        mode: mode.value,
        formula: formula.value,
        code: code.value,
        stock_pool: pool.value
          .split(/[,，\s]+/)
          .map((s) => s.trim())
          .filter(Boolean),
        start_date: startDate.value,
        end_date: endDate.value,
      }),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => null)
      throw new Error(body?.detail ?? `因子计算接口错误 (HTTP ${res.status})`)
    }
    const data = await res.json()
    const result: FactorResult = {
      dates: data.dates,
      stocks: data.stocks,
      values: data.factor_data,
      returnData: data.return_data,
      name: mode.value === 'formula' ? formula.value || 'factor' : 'custom_factor',
    }
    preview.value = result
    emit('factorComputed', result)
  } catch (e) {
    error.value =
      e instanceof TypeError
        ? '无法连接后端服务 (http://localhost:8000)，请先运行 make dev 或 make dev-backend'
        : e instanceof Error
          ? e.message
          : String(e)
    preview.value = null
  } finally {
    computing.value = false
  }
}

// 预览仅展示最近 20 个交易日，避免渲染过大表格
const previewDates = computed(() => (preview.value ? preview.value.dates.slice(-20) : []))

function cellValue(d: string, s: string): number | undefined {
  return preview.value?.values[d]?.[s]
}
function cellClass(v: number | undefined): string {
  if (v != null && v > 0) return 'text-[#30d158]'
  if (v != null && v < 0) return 'text-[#ff3b30]'
  return 'text-[#201d1d]'
}
</script>

<template>
  <Card title="因子构建器" class="h-full flex flex-col">
    <div class="flex flex-col gap-3">
      <!-- 模式切换 -->
      <Tabs :items="builderTabs" :active-key="mode" @change="(k) => (mode = k)" />

      <!-- 公式模式 -->
      <div v-if="mode === 'formula'" class="flex flex-col gap-2">
        <div class="flex items-center justify-between">
          <label class="text-xs text-[#646262]">
            因子公式表达式（可用变量: open/high/low/close/volume/amount, np, pd）
          </label>
          <button
            class="tb-btn"
            title="用 AI 生成/修改因子公式（需先在设置中配置 AI）"
            style="border: 1px solid rgba(124, 58, 237, 0.4); background: transparent; color: #7c3aed; border-radius: 4px; font-size: 11px; font-weight: 600; padding: 2px 8px; cursor: pointer"
            @click="showAI = true"
          >
            ✦ AI
          </button>
        </div>
        <Input v-model="formula" placeholder="例: close / close.shift(5) - 1" />
      </div>

      <!-- 代码模式 -->
      <div v-if="mode === 'code'" class="flex flex-col gap-2">
        <div class="flex items-center justify-between">
          <label class="text-xs text-[#646262]">Python 代码</label>
          <button
            class="tb-btn"
            title="用 AI 生成/修改因子代码（需先在设置中配置 AI）"
            style="border: 1px solid rgba(124, 58, 237, 0.4); background: transparent; color: #7c3aed; border-radius: 4px; font-size: 11px; font-weight: 600; padding: 2px 8px; cursor: pointer"
            @click="showAI = true"
          >
            ✦ AI
          </button>
        </div>
        <CodeEditor v-model="code" language="python" :height="220" title="因子代码编辑" :font-size="13" />
      </div>

      <!-- 参数区域 -->
      <div class="grid grid-cols-3 gap-2">
        <div class="flex flex-col gap-1">
          <label class="text-xs text-[#646262]">股票池</label>
          <Input v-model="pool" placeholder="留空=全部已缓存股票" />
        </div>
        <div class="flex flex-col gap-1">
          <label class="text-xs text-[#646262]">起始日期</label>
          <Input v-model="startDate" type="date" />
        </div>
        <div class="flex flex-col gap-1">
          <label class="text-xs text-[#646262]">结束日期</label>
          <Input v-model="endDate" type="date" />
        </div>
      </div>

      <Button variant="primary" :loading="computing" @click="handleCompute">计算因子</Button>

      <!-- 错误提示（真实后端错误，无模拟数据兜底） -->
      <div
        v-if="error"
        class="rounded-[4px] border border-[#ff3b30] bg-[#ff3b30]/10 px-3 py-2 font-mono text-xs text-[#ff3b30]"
      >
        {{ error }}
      </div>

      <!-- 因子值预览 -->
      <div v-if="preview" class="flex flex-col gap-2">
        <label class="text-xs text-[#646262]">因子值预览（最近 {{ previewDates.length }} 个交易日）</label>
        <ScrollArea :max-height="200">
          <table class="w-full border-collapse text-xs">
            <thead>
              <tr class="bg-[#f8f7f7]">
                <th class="border-b border-[rgba(15,0,0,0.12)] px-2 py-1.5 text-left text-[#646262] sticky top-0 bg-[#f8f7f7]">
                  日期
                </th>
                <th
                  v-for="s in preview.stocks"
                  :key="s"
                  class="border-b border-[rgba(15,0,0,0.12)] px-2 py-1.5 text-right text-[#646262] sticky top-0 bg-[#f8f7f7]"
                >
                  {{ s }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="d in previewDates" :key="d" class="hover:bg-[#f1eeee]">
                <td class="border-b border-[rgba(15,0,0,0.12)] px-2 py-1 text-[#646262]">{{ d }}</td>
                <td
                  v-for="s in preview.stocks"
                  :key="s"
                  class="border-b border-[rgba(15,0,0,0.12)] px-2 py-1 text-right font-mono"
                  :class="cellClass(cellValue(d, s))"
                >
                  {{ cellValue(d, s) != null ? cellValue(d, s)!.toFixed(3) : '-' }}
                </td>
              </tr>
            </tbody>
          </table>
        </ScrollArea>
      </div>
    </div>

    <!-- AI 生成/修改因子弹窗 -->
    <Dialog
      :open="showAI"
      :title="mode === 'formula' ? 'AI 生成 / 修改因子公式' : 'AI 生成 / 修改因子代码'"
      @close="!aiLoading && (showAI = false)"
    >
      <div class="mb-2 text-[11px] leading-relaxed text-[#646262]" style="width: 480px">
        用自然语言描述想要的因子或修改要求，结果会填入编辑器，确认后再点「计算因子」。
      </div>
      <div v-if="aiError" class="mb-2 whitespace-pre-wrap font-mono text-[11px] text-[#ff3b30]">
        {{ aiError }}
      </div>
      <textarea
        v-model="aiInstruction"
        :placeholder="
          mode === 'formula'
            ? '例：20 日动量截面排名因子；把当前公式改成对数收益版本'
            : '例：写一个 20 日反转因子；给当前代码加上去极值和标准化'
        "
        :rows="5"
        class="w-full resize-y rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-2.5 py-2 text-xs leading-relaxed text-[#201d1d] outline-none"
        style="font-family: inherit; box-sizing: border-box"
      />
      <template #footer>
        <Button variant="secondary" :disabled="aiLoading" @click="showAI = false">取消</Button>
        <Button :loading="aiLoading" :disabled="!aiInstruction.trim()" @click="handleAI">
          {{ aiLoading ? '生成中...' : '生成并填入编辑器' }}
        </Button>
      </template>
    </Dialog>
  </Card>
</template>
