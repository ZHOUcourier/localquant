<script setup lang="ts">
/**
 * ToolCard — AI 消息中的工具调用卡片（复刻参考站工具卡语义，opencode 视觉）
 * 按工具名映射不同卡片：因子创建/因子分析/策略代码/回测参数/回测结果/通用。
 */
import { computed } from 'vue'
import type { ToolCall } from './types'
import { fmtNum, fmtPct } from './types'

const props = defineProps<{ call: ToolCall }>()

const emit = defineEmits<{
  openFactor: [factorId: string, tab: string]
  openStrategy: [strategyId: string, tab: string]
  viewAnalysis: [factorId: string, analysisId: string]
  viewBacktest: [strategyId: string, runId: string]
  optimize: [strategyId: string, runId: string]
}>()

const r = computed(() => props.call.result || {})
const failed = computed(() => typeof r.value.error === 'string' && !!r.value.error)

const kind = computed(() => {
  const n = props.call.name
  if (n === 'generate_stock_factor_code') return 'factor'
  if (n === 'run_factor_analysis') return 'analysis'
  if (n === 'generate_stock_strategy_code') return 'strategy'
  if (n === 'set_backtest_params') return 'params'
  if (n === 'run_backtest') return 'backtest'
  return 'generic'
})

const paramsKv = computed(() => {
  const p = (r.value.params || props.call.args || {}) as Record<string, unknown>
  return Object.entries(p).filter(([, v]) => v !== '' && v != null)
})

const btMetrics = computed(() => (r.value.metrics || {}) as Record<string, number>)
const faSummary = computed(() => (r.value.summary || {}) as Record<string, number>)

function short(id?: unknown): string {
  return String(id || '').slice(0, 8)
}
</script>

<template>
  <div
    class="rounded-[4px] border bg-[#fdfcfc] p-3 text-xs"
    :style="{ borderColor: failed ? 'rgba(255,59,48,0.35)' : 'rgba(15,0,0,0.12)' }"
  >
    <!-- 失败态：统一展示错误 -->
    <template v-if="failed">
      <div class="flex items-start gap-2">
        <span class="shrink-0 font-mono text-[#ff3b30]">[x]</span>
        <div class="min-w-0 flex-1">
          <div class="font-medium text-[#201d1d]">{{ call.display_name }} · 失败</div>
          <div class="mt-1 break-all text-[11px] text-[#c62d23]">{{ r.error }}</div>
        </div>
      </div>
    </template>

    <!-- 已创建因子 -->
    <template v-else-if="kind === 'factor'">
      <div class="flex items-center gap-2">
        <span class="shrink-0 font-mono text-[#30d158]">[+]</span>
        <div class="min-w-0 flex-1">
          <div class="truncate font-medium text-[#201d1d]">
            已创建股票因子 · {{ r.name || call.args.name }}
          </div>
          <div class="mt-0.5 text-[10px] text-[#9a9898]">
            因子 #{{ short(call.factor_id) }} · {{ r.code_type || 'formula' }}
          </div>
        </div>
        <button
          class="shrink-0 rounded-[4px] bg-[#201d1d] px-2.5 py-1 text-[11px] text-[#fdfcfc] hover:opacity-85"
          @click="emit('openFactor', call.factor_id || '', 'code')"
        >
          打开画板
        </button>
      </div>
    </template>

    <!-- 因子分析完成 -->
    <template v-else-if="kind === 'analysis'">
      <div class="flex items-center gap-2">
        <span class="shrink-0 font-mono text-[#30d158]">[✓]</span>
        <div class="min-w-0 flex-1">
          <div class="truncate font-medium text-[#201d1d]">
            因子 #{{ short(call.factor_id) }} · 分析完成
          </div>
          <div class="mt-0.5 text-[10px] text-[#9a9898]">
            分析 #{{ short(call.factor_analysis_id) }} · 股票 · done
          </div>
        </div>
        <button
          class="shrink-0 rounded-[4px] border border-[rgba(15,0,0,0.15)] bg-transparent px-2.5 py-1 text-[11px] text-[#424245] hover:text-[#201d1d]"
          @click="emit('viewAnalysis', call.factor_id || '', call.factor_analysis_id || '')"
        >
          查看分析
        </button>
      </div>
      <div v-if="Object.keys(faSummary).length" class="mt-2 flex flex-wrap gap-1.5">
        <span class="rounded-[3px] bg-[#f1eeee] px-1.5 py-0.5 font-mono text-[10px] text-[#424245]">
          IC {{ fmtNum(faSummary.ic_mean) }}
        </span>
        <span class="rounded-[3px] bg-[#f1eeee] px-1.5 py-0.5 font-mono text-[10px] text-[#424245]">
          IC_IR {{ fmtNum(faSummary.ic_ir) }}
        </span>
        <span class="rounded-[3px] bg-[#f1eeee] px-1.5 py-0.5 font-mono text-[10px] text-[#424245]">
          年化 {{ fmtPct(faSummary.annual_return) }}
        </span>
        <span class="rounded-[3px] bg-[#f1eeee] px-1.5 py-0.5 font-mono text-[10px] text-[#424245]">
          夏普 {{ fmtNum(faSummary.sharpe_ratio, 2) }}
        </span>
      </div>
    </template>

    <!-- 已写入策略代码 -->
    <template v-else-if="kind === 'strategy'">
      <div class="flex items-center gap-2">
        <span class="shrink-0 font-mono text-[#007aff]">&lt;/&gt;</span>
        <div class="min-w-0 flex-1">
          <div class="truncate font-medium text-[#201d1d]">
            已写入策略代码 · {{ r.name || call.args.name }}
          </div>
          <div class="mt-0.5 truncate text-[10px] text-[#9a9898]">
            股票 · {{ call.args.summary || '策略代码已写入画板' }}
          </div>
        </div>
        <button
          class="shrink-0 rounded-[4px] border border-[rgba(15,0,0,0.15)] bg-transparent px-2.5 py-1 text-[11px] text-[#424245] hover:text-[#201d1d]"
          @click="emit('openStrategy', call.strategy_id || '', 'code')"
        >
          代码
        </button>
        <button
          class="shrink-0 rounded-[4px] bg-[#201d1d] px-2.5 py-1 text-[11px] text-[#fdfcfc] hover:opacity-85"
          @click="emit('openStrategy', call.strategy_id || '', 'backtest')"
        >
          回测
        </button>
      </div>
    </template>

    <!-- 已更新回测参数（内嵌 kv 表） -->
    <template v-else-if="kind === 'params'">
      <div class="flex items-start gap-2">
        <span class="shrink-0 font-mono text-[#646262]">[=]</span>
        <div class="min-w-0 flex-1">
          <div class="font-medium text-[#201d1d]">已更新股票回测参数</div>
          <div class="mt-0.5 text-[10px] text-[#9a9898]">已把回测参数推给右侧画板，可直接运行回测。</div>
          <div class="mt-2 rounded-[4px] bg-[#f8f7f7] px-2.5 py-1.5">
            <div
              v-for="[k, v] in paramsKv"
              :key="k"
              class="flex justify-between gap-3 py-0.5 font-mono text-[10px]"
            >
              <span class="text-[#9a9898]">{{ k }}</span>
              <span class="text-[#201d1d]">{{ v }}</span>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- 回测完成 -->
    <template v-else-if="kind === 'backtest'">
      <div class="flex items-center gap-2">
        <span class="shrink-0 font-mono text-[#30d158]">[✓]</span>
        <div class="min-w-0 flex-1">
          <div class="truncate font-medium text-[#201d1d]">策略 · 回测完成</div>
          <div class="mt-0.5 text-[10px] text-[#9a9898]">
            回测 #{{ short(call.backtest_run_id) }} · 股票 · {{ btMetrics.trade_count ?? '-' }} 笔交易
          </div>
        </div>
        <button
          class="shrink-0 rounded-[4px] border border-[rgba(15,0,0,0.15)] bg-transparent px-2.5 py-1 text-[11px] text-[#424245] hover:text-[#201d1d]"
          @click="emit('viewBacktest', call.strategy_id || '', call.backtest_run_id || '')"
        >
          查看
        </button>
        <button
          class="shrink-0 rounded-[4px] bg-[#201d1d] px-2.5 py-1 text-[11px] text-[#fdfcfc] hover:opacity-85"
          @click="emit('optimize', call.strategy_id || '', call.backtest_run_id || '')"
        >
          ✦ AI 优化
        </button>
      </div>
      <div class="mt-2 flex flex-wrap gap-1.5 font-mono text-[10px]">
        <span class="rounded-[3px] bg-[#f1eeee] px-1.5 py-0.5">
          总收益
          <b :style="{ color: (btMetrics.total_return || 0) >= 0 ? '#c62d23' : '#1d8a3e' }">
            {{ fmtPct(btMetrics.total_return) }}
          </b>
        </span>
        <span class="rounded-[3px] bg-[#f1eeee] px-1.5 py-0.5">
          最大回撤 <b class="text-[#1d8a3e]">{{ fmtPct(btMetrics.max_drawdown) }}</b>
        </span>
        <span class="rounded-[3px] bg-[#f1eeee] px-1.5 py-0.5">
          夏普 <b class="text-[#201d1d]">{{ fmtNum(btMetrics.sharpe_ratio, 2) }}</b>
        </span>
      </div>
    </template>

    <!-- 通用工具卡 -->
    <template v-else>
      <div class="flex items-center gap-2">
        <span class="shrink-0 font-mono text-[#30d158]">[✓]</span>
        <span class="min-w-0 flex-1 truncate font-medium text-[#201d1d]">{{ call.display_name }}</span>
        <span class="shrink-0 font-mono text-[10px] text-[#9a9898]">{{ call.name }}</span>
      </div>
    </template>
  </div>
</template>
