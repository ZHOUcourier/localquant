<script setup lang="ts">
/**
 * 风险与组合分析 — 风格暴露、组合优化、绩效指标、压力测试。
 * 输入为 close 面板（{日期: {代码: 收盘价}}），可手工粘贴 JSON，
 * 也可一键生成合成示例（无 QMT 也可验证后端计算逻辑）。
 */
import { computed, ref } from 'vue'
import { Card, Button } from '@/components/ui'
import VChart from '@/components/ui/VChart.vue'
import { Activity, SlidersHorizontal, Target, Scale, ShieldAlert, Loader2 } from 'lucide-vue-next'

type Panel = Record<string, Record<string, number>>

const CODES = ['000001.SZ', '600000.SH', '000002.SZ', '600036.SH', '601318.SH']

const OBS = [
  '2023-03-01', '2023-03-02', '2023-03-03', '2023-03-06', '2023-03-07',
  '2023-03-08', '2023-03-09', '2023-03-10', '2023-03-13', '2023-03-14',
  '2023-03-15', '2023-03-16', '2023-03-17', '2023-03-20', '2023-03-21',
  '2023-03-22', '2023-03-23', '2023-03-24', '2023-03-27', '2023-03-28',
  '2023-03-29', '2023-03-30', '2023-03-31', '2023-04-03', '2023-04-04',
  '2023-04-06', '2023-04-07', '2023-04-10', '2023-04-11', '2023-04-12',
]

const panelText = ref('')
const busy = ref<'' | 'exposure' | 'optimize' | 'metrics' | 'stress'>('')
const errorMsg = ref('')

const state = ref<{
  exposure: Record<string, Panel> | null
  weights: Record<string, number> | null
  metrics: Record<string, unknown> | null
  stress: Record<string, unknown> | null
}>({ exposure: null, weights: null, metrics: null, stress: null })

function mulberry32(a: number) {
  return function () {
    a |= 0
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function buildSample() {
  const rnd = mulberry32(20240802)
  const close: Panel = {}
  OBS.forEach((d, di) => {
    close[d] = {}
    for (const c of CODES) {
      const drift = (CODES.indexOf(c) % 3) * 0.002 // 制造风格差异
      close[d][c] =
        di === 0 ? 10 + rnd() * 20
        : close[OBS[di - 1]][c] * (1 + drift + (rnd() - 0.5) * 0.03)
    }
  })
  panelText.value = JSON.stringify({ close }, null, 2)
  state.value = { exposure: null, weights: null, metrics: null, stress: null }
  errorMsg.value = ''
}

function readClose(): Panel {
  if (!panelText.value.trim()) buildSample()
  const obj = JSON.parse(panelText.value) as { close?: Panel }
  if (!obj.close) throw new Error('面板需包含 "close" 字段')
  return obj.close
}

const parseClose = readClose

/** 从 close 推导 returns / 动量评分（仅作输入准备；实际计算在后端） */
function buildInputs(close: Panel) {
  const dates = Object.keys(close).sort()
  const codes = CODES.filter((c) => close[dates[0]]?.[c] != null)
  const returns: Panel = {}
  for (let i = 1; i < dates.length; i++) {
    const d = dates[i]
    const prev = dates[i - 1]
    returns[d] = {}
    for (const c of codes) {
      const p = close[prev][c]
      const cur = close[d][c]
      returns[d][c] = p ? (cur - p) / p : 0
    }
  }
  // 组合日收益 = 等权均值；基准 = 滞后 5 日的移动平均（产生 beta != 1 便于展示）
  const strategy: Record<string, number> = {}
  const benchmark: Record<string, number> = {}
  const perDay = dates.slice(1).map((d) => ({
    d,
    v: Object.values(returns[d]).reduce((a, b) => a + b, 0) / codes.length,
  }))
  perDay.forEach((row, i) => {
    strategy[row.d] = row.v
    const win = perDay.slice(Math.max(0, i - 4), i + 1).map((x) => x.v)
    benchmark[row.d] = win.reduce((a, b) => a + b, 0) / win.length
  })
  const dl = dates.length
  const scores: Record<string, number> = {}
  for (const c of codes) {
    const p0 = close[dates[Math.max(0, dl - 11)]][c]
    const p1 = close[dates[dl - 1]][c]
    scores[c] = p0 && p1 ? (p1 - p0) / p0 : 0
  }
  return { returns, strategy, benchmark, scores }
}

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = await res.json().catch(() => null)
  if (!res.ok) throw new Error(data?.detail ?? `接口错误 (HTTP ${res.status})`)
  return data as T
}

async function guard(run: () => Promise<void>) {
  busy.value = 'optimize'
  errorMsg.value = ''
  try {
    await run()
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : '计算失败'
  } finally {
    busy.value = ''
  }
}

function runExposure() {
  return guard(async () => {
    const close = parseClose()
    state.value.exposure = await postJson<Record<string, Panel>>('/api/risk/style-exposure', { close })
  })
}

function runOptimize() {
  return guard(async () => {
    const { scores } = buildInputs(parseClose())
    const out = await postJson<{ weights: Record<string, number> }>('/api/risk/optimize', { scores })
    state.value.weights = out.weights
  })
}

function runMetrics() {
  return guard(async () => {
    const { strategy, benchmark } = buildInputs(parseClose())
    state.value.metrics = await postJson<Record<string, unknown>>('/api/risk/metrics', {
      returns: strategy,
      benchmark,
    })
  })
}

function runStress() {
  return guard(async () => {
    let weights = state.value.weights
    if (!weights) {
      const { scores } = buildInputs(parseClose())
      weights = (await postJson<{ weights: Record<string, number> }>('/api/risk/optimize', { scores })).weights
      state.value.weights = weights
    }
    state.value.stress = await postJson<Record<string, unknown>>('/api/risk/stress', { weights })
  })
}

// ── 图表选项（纯展示） ────────────────────────────────

const exposureChartOption = computed(() => {
  const exp = state.value.exposure
  if (!exp) return {}
  const styleKeys = Object.keys(exp)
  const series = styleKeys.map((s) => ({
    name: s,
    type: 'line',
    smooth: true,
    showSymbol: false,
    data: OBS.map((d) => {
      const p = exp[s][d]
      const vals = p ? Object.values(p) : []
      return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : 0
    }),
  }))
  return {
    tooltip: { trigger: 'axis' },
    legend: { type: 'scroll', bottom: 0 },
    grid: { left: 40, right: 16, top: 20, bottom: 40 },
    xAxis: { type: 'category', data: OBS, boundaryGap: false },
    yAxis: { type: 'value' },
    series,
  }
})

const weightChartOption = computed(() => {
  const w = state.value.weights
  if (!w) return {}
  return {
    tooltip: { trigger: 'axis', valueFormatter: (v: number) => (v * 100).toFixed(2) + '%' },
    grid: { left: 44, right: 16, top: 20, bottom: 40 },
    xAxis: { type: 'category', data: Object.keys(w), axisLabel: { rotate: 30 } },
    yAxis: { type: 'value', axisLabel: { formatter: (v: number) => v * 100 + '%' } },
    series: [{ type: 'bar', data: Object.values(w).map((v) => Number(v.toFixed(4))), itemStyle: { color: '#007aff' } }],
  }
})
</script>

<template>
  <div class="flex flex-col max-w-[1400px] overflow-auto">
    <div>
      <h1 class="text-xl font-semibold text-[#201d1d] mb-1">风险与组合分析</h1>
      <p class="text-[13px] text-[#646262]">
        风格暴露 / 组合优化（带约束）/ 绩效补充指标 / 压力测试 — 计算均由后端 /api/risk/* 完成
      </p>
    </div>

    <div class="mt-4 grid grid-cols-1 lg:grid-cols-3 gap-4">
      <!-- 输入 -->
      <Card title="输入面板（close: {日期: {代码: 收盘价}}）" class="row-span-2">
        <textarea
          v-model="panelText"
          rows="18"
          spellcheck="false"
          class="w-full font-mono text-xs p-2 rounded-[4px] border border-[#e3e0e0] bg-[#f8f7f7] text-[#201d1d] focus:outline-none focus:border-[#007aff] resize-y"
          placeholder='{"close": {"2023-03-01": {"000001.SZ": 12.3}}}'
        />
        <div class="mt-3 flex flex-wrap gap-2">
          <Button variant="secondary" size="sm" @click="buildSample">
            <Activity :size="14" class="mr-1" /> 生成合成示例
          </Button>
          <Button variant="primary" size="sm" :disabled="!!busy" @click="runExposure">
            <SlidersHorizontal :size="14" class="mr-1" /> 风格暴露
          </Button>
          <Button variant="primary" size="sm" :disabled="!!busy" @click="runOptimize">
            <Target :size="14" class="mr-1" /> 组合优化
          </Button>
          <Button variant="primary" size="sm" :disabled="!!busy" @click="runMetrics">
            <Scale :size="14" class="mr-1" /> 绩效指标
          </Button>
          <Button variant="danger" size="sm" :disabled="!!busy" @click="runStress">
            <ShieldAlert :size="14" class="mr-1" /> 压力测试
          </Button>
        </div>
        <div v-if="busy" class="mt-3 flex items-center gap-2 text-xs text-[#646262]">
          <Loader2 :size="13" class="animate-spin" /> 计算中...
        </div>
        <div v-if="errorMsg" class="mt-3 rounded-[4px] border border-[#ff3b30] bg-[#ff3b30]/10 px-3 py-2 font-mono text-xs text-[#ff3b30]">
          {{ errorMsg }}
        </div>
      </Card>

      <!-- 风格暴露 -->
      <Card title="风格暴露（截面均值走势）" class="lg:col-span-2">
        <div v-if="!state.exposure" class="py-10 text-center text-xs text-[#646262]">点击「风格暴露」查看 Barra-like 风格因子暴露</div>
        <VChart v-else :option="exposureChartOption" :height="280" />
      </Card>

      <!-- 组合权重 -->
      <Card title="组合权重" class="lg:col-span-1">
        <div v-if="!state.weights" class="py-10 text-center text-xs text-[#646262]">点击「组合优化」生成带约束的权重</div>
        <template v-else>
          <VChart :option="weightChartOption" height="200" />
          <div v-for="(w, c) in state.weights" :key="String(c)" class="flex items-center justify-between py-0.5 border-b border-[#f1eeee] last:border-0">
            <span class="text-xs font-mono text-[#201d1d]">{{ c }}</span>
            <span class="text-xs font-mono text-[#007aff]">{{ (w * 100).toFixed(2) }}%</span>
          </div>
        </template>
      </Card>

      <!-- 绩效指标 + 压力测试 -->
      <Card title="绩效指标" class="lg:col-span-1">
        <div v-if="!state.metrics" class="py-10 text-center text-xs text-[#646262]">点击「绩效指标」补充 alpha/beta、捕获率等</div>
        <div v-else>
          <div v-for="(v, k) in state.metrics" :key="String(k)" class="flex items-center justify-between py-0.5 border-b border-[#f1eeee] last:border-0">
            <span class="text-xs text-[#646262]">{{ String(k) }}</span>
            <span class="text-xs font-mono text-[#201d1d]">{{ typeof v === 'number' ? Number(v).toFixed(4) : String(v ?? '') }}</span>
          </div>
        </div>
      </Card>

      <Card title="压力测试" class="lg:col-span-1">
        <div v-if="!state.stress" class="py-10 text-center text-xs text-[#646262]">点击「压力测试」查看场景冲击</div>
        <pre v-else class="text-[11px] font-mono text-[#201d1d] whitespace-pre-wrap">{{ JSON.stringify(state.stress, null, 2) }}</pre>
      </Card>
    </div>

    <p class="mt-3 text-[11px] text-[#646262]">
      说明：前端仅为输入准备与图表展示；风格暴露、SLSQP 权重优化、绩效指标、压力冲击全部由后端完成。粘贴式面板便于无真实行情时验证。
    </p>
  </div>
</template>