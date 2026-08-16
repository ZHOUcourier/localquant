<script setup lang="ts">
/**
 * 风险与组合分析 — 风格暴露、组合优化、绩效指标、压力测试。
 * 输入为 close 面板（{日期: {代码: 收盘价}}）；研究数据只从本地 QMT 缓存加载，
 * 不提供合成行情示例。
 */
import { computed, ref } from 'vue'
import { Card, Button } from '@/components/ui'
import VChart from '@/components/ui/VChart.vue'
import { Activity, SlidersHorizontal, Target, Scale, ShieldAlert, Loader2, Database } from 'lucide-vue-next'

type Panel = Record<string, Record<string, number>>

const panelText = ref('')
const busy = ref<'' | 'exposure' | 'optimize' | 'metrics' | 'stress'>('')
const errorMsg = ref('')

const state = ref<{
  exposure: Record<string, Panel> | null
  weights: Record<string, number> | null
  metrics: Record<string, unknown> | null
  stress: Record<string, unknown> | null
}>({ exposure: null, weights: null, metrics: null, stress: null })

/* ── 从本地行情缓存加载真实面板（而非手工粘贴/合成示例） ── */
const cacheCodes = ref('')
const cacheStart = ref('')
const cacheEnd = ref('')
const cacheLoading = ref(false)
const cacheInfo = ref('')
const loadedPanels = ref<{ close: Panel; volume: Panel; amount: Panel } | null>(null)
const riskPanelToken = ref('')

async function loadFromCache() {
  cacheLoading.value = true
  cacheInfo.value = ''
  errorMsg.value = ''
  try {
    const q = new URLSearchParams()
    if (cacheCodes.value.trim()) q.set('codes', cacheCodes.value.trim())
    if (cacheStart.value) q.set('start_date', cacheStart.value)
    if (cacheEnd.value) q.set('end_date', cacheEnd.value)
    const res = await fetch(`/api/risk/panel?${q.toString()}`)
    const data = await res.json().catch(() => null)
    if (!res.ok) throw new Error(data?.detail ?? `接口错误 (HTTP ${res.status})`)
    riskPanelToken.value = data.panel_token ?? ''
    if (data.panel_mode === 'inline') {
      loadedPanels.value = { close: data.close, volume: data.volume, amount: data.amount }
      panelText.value = JSON.stringify(
        { close: data.close, volume: data.volume, amount: data.amount },
        null,
        2,
      )
    } else {
      // 全市场大面板只在服务端暂存，不展开到浏览器 textarea
      loadedPanels.value = null
      panelText.value = ''
    }
    cacheInfo.value = `已加载 ${data.codes?.length ?? 0} 只标的 · ${data.start} ~ ${data.end}（前复权口径）` +
      (data.panel_mode === 'artifact' ? '；大面板已在服务端暂存' : '')
    state.value = { exposure: null, weights: null, metrics: null, stress: null }
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e)
  } finally {
    cacheLoading.value = false
  }
}

function readClose(): Panel {
  if (!panelText.value.trim()) {
    throw new Error('请先点击「加载」从本地 QMT 行情缓存加载面板')
  }
  const obj = JSON.parse(panelText.value) as { close?: Panel }
  if (!obj.close) throw new Error('面板需包含 "close" 字段')
  return obj.close
}

const parseClose = readClose

/** 从 close 推导 returns / 动量评分（仅作输入准备；实际计算在后端） */
function buildInputs(close: Panel) {
  const dates = Object.keys(close).sort()
  const codes = Object.keys(close[dates[0]] || {})
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

function requireInlinePanel(): Panel {
  if (riskPanelToken.value && !panelText.value.trim()) {
    throw new Error('当前为全市场大面板（服务端暂存），请指定较小型股票池后再做组合优化/绩效/压力测试')
  }
  return parseClose()
}

function runExposure() {
  return guard(async () => {
    const panels = loadedPanels.value
    state.value.exposure = await postJson<Record<string, Panel>>('/api/risk/style-exposure', {
      close: panels ? panels.close : {},
      volume: panels?.volume ?? {},
      amount: panels?.amount ?? {},
      panel_token: riskPanelToken.value,
    })
  })
}

function runOptimize() {
  return guard(async () => {
    const { scores } = buildInputs(requireInlinePanel())
    const out = await postJson<{ weights: Record<string, number> }>('/api/risk/optimize', { scores })
    state.value.weights = out.weights
  })
}

function runMetrics() {
  return guard(async () => {
    const { strategy, benchmark } = buildInputs(requireInlinePanel())
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
      const { scores } = buildInputs(requireInlinePanel())
      weights = (await postJson<{ weights: Record<string, number> }>('/api/risk/optimize', { scores })).weights
      state.value.weights = weights
    }
    state.value.stress = await postJson<Record<string, unknown>>('/api/risk/stress', { weights })
  })
}

/** 组合事前风险预测（因子协方差 + 市场模型残差）+ 历史情景回放 */
const forecastLoading = ref(false)
const forecast = ref<Record<string, unknown> | null>(null)
async function runForecast() {
  forecastLoading.value = true
  errorMsg.value = ''
  try {
    let weights = state.value.weights
    if (!weights) {
      const { scores } = buildInputs(requireInlinePanel())
      weights = (await postJson<{ weights: Record<string, number> }>('/api/risk/optimize', { scores })).weights
      state.value.weights = weights
    }
    const q = new URLSearchParams()
    if (cacheCodes.value.trim()) q.set('codes', cacheCodes.value.trim())
    if (cacheStart.value) q.set('start_date', cacheStart.value)
    if (cacheEnd.value) q.set('end_date', cacheEnd.value)
    const res = await fetch(`/api/risk/forecast-panel?${q.toString()}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ weights }),
    })
    const data = await res.json().catch(() => null)
    if (!res.ok) throw new Error(data?.detail ?? `接口错误 (HTTP ${res.status})`)
    forecast.value = data
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e)
  } finally {
    forecastLoading.value = false
  }
}

const historicalScenarios = computed(() => {
  const v = forecast.value?.historical_scenarios
  if (!v || typeof v !== 'object') return []
  return Object.entries(v as Record<string, { cum_return_pct: number | null; max_drawdown_pct: number | null; worst_day_pct: number | null; note?: string }>).map(([name, s]) => ({ name, ...s }))
})

// ── 图表选项（纯展示） ────────────────────────────────

const exposureChartOption = computed(() => {
  const exp = state.value.exposure
  if (!exp) return {}
  const styleKeys = Object.keys(exp)
  const firstPanel = exp[styleKeys[0]]
  const dates = firstPanel ? Object.keys(firstPanel).sort() : []
  const series = styleKeys.map((s) => ({
    name: s,
    type: 'line',
    smooth: true,
    showSymbol: false,
    data: dates.map((d) => {
      const p = exp[s][d]
      const vals = p ? Object.values(p) : []
      return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : 0
    }),
  }))
  return {
    tooltip: { trigger: 'axis' },
    legend: { type: 'scroll', bottom: 0 },
    grid: { left: 40, right: 16, top: 20, bottom: 40 },
    xAxis: { type: 'category', data: dates, boundaryGap: false },
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
  <!-- 整页滚动：内容自然高度，滚动由外层 Layout main 承接（避免双层滚动条） -->
  <div class="flex flex-col max-w-[1400px]">
    <div>
      <h1 class="text-xl font-semibold text-[#201d1d] mb-1">风险与组合分析</h1>
      <p class="text-[13px] text-[#646262]">
        风格暴露 / 组合优化（带约束）/ 绩效补充指标 / 压力测试 — 计算均由后端 /api/risk/* 完成
      </p>
    </div>

    <div class="mt-4 grid grid-cols-1 lg:grid-cols-3 gap-4">
      <!-- 输入 -->
      <Card title="输入面板（close: {日期: {代码: 收盘价}}）" class="row-span-2">
        <!-- 从本地缓存加载（推荐：有缓存行情时直接取真实数据） -->
        <div class="mb-3 rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] p-2.5">
          <div class="mb-1.5 text-[11px] font-medium text-[#646262]">从本地行情缓存加载（前复权）</div>
          <div class="flex flex-wrap items-center gap-1.5">
            <input
              v-model="cacheCodes"
              type="text"
              placeholder="股票池，逗号分隔（留空=全部）"
              class="min-w-[180px] flex-1 rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2 py-1 text-xs font-mono outline-none placeholder:text-[#9a9898]"
            />
            <input v-model="cacheStart" type="date" class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-1.5 py-1 text-xs" />
            <input v-model="cacheEnd" type="date" class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-1.5 py-1 text-xs" />
            <Button variant="secondary" size="sm" :loading="cacheLoading" @click="loadFromCache">
              <Database :size="13" class="mr-1" /> 加载
            </Button>
          </div>
          <div v-if="cacheInfo" class="mt-1.5 text-[11px] text-[#248a3d]">{{ cacheInfo }}</div>
        </div>
        <textarea
          v-model="panelText"
          rows="13"
          spellcheck="false"
          class="w-full font-mono text-xs p-2 rounded-[4px] border border-[#e3e0e0] bg-[#f8f7f7] text-[#201d1d] focus:outline-none focus:border-[#007aff] resize-y"
          placeholder='{"close": {"2023-03-01": {"000001.SZ": 12.3}}}'
        />
        <div class="mt-3 flex flex-wrap gap-2">
          <Button variant="primary" size="sm" :disabled="!!busy" @click="runExposure">
            <SlidersHorizontal :size="14" class="mr-1" /> 风格暴露
          </Button>
          <Button variant="primary" size="sm" :disabled="!!busy" @click="runOptimize">
            <Target :size="14" class="mr-1" /> 组合优化
          </Button>
          <Button variant="primary" size="sm" :disabled="!!busy" @click="runMetrics">
            <Scale :size="14" class="mr-1" /> 绩效指标
          </Button>
          <Button variant="primary" size="sm" :disabled="!!busy" @click="runForecast">
            <Activity :size="14" class="mr-1" /> 事前风险预测
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

      <!-- 事前风险预测 + 历史情景回放 -->
      <Card title="组合事前风险预测（因子协方差法）+ 历史情景回放" class="lg:col-span-3">
        <div v-if="!forecast" class="py-8 text-center text-xs text-[#646262]">
          先生成组合权重，再点「事前风险预测」：预测组合年化波动、各风格/行业因子风险贡献占比、
          以及 2015 股灾 / 2018 熊市 / 2024 小微盘流动性危机等真实窗口回放（需缓存覆盖对应历史区间）
        </div>
        <template v-else>
          <div class="mb-3 grid grid-cols-2 lg:grid-cols-4 gap-2">
            <div class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-3 py-2">
              <div class="text-[11px] text-[#646262]">预测年化波动</div>
              <div class="text-base font-bold text-[#201d1d]">{{ ((forecast.forecast_vol_annual as number) * 100).toFixed(1) }}%</div>
            </div>
            <div class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-3 py-2">
              <div class="text-[11px] text-[#646262]">个券特异风险占比</div>
              <div class="text-base font-bold text-[#201d1d]">{{ ((forecast.idiosyncratic_pct as number ?? 0) * 100).toFixed(1) }}%</div>
            </div>
            <div class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-3 py-2">
              <div class="text-[11px] text-[#646262]">覆盖股票数</div>
              <div class="text-base font-bold text-[#201d1d]">{{ forecast.n_stocks }}</div>
            </div>
            <div class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-3 py-2">
              <div class="text-[11px] text-[#646262]">样本区间</div>
              <div class="text-sm font-mono text-[#201d1d]">{{ forecast.data_start }} ~ {{ forecast.data_end }}</div>
            </div>
          </div>
          <div v-if="forecast.note" class="mb-2 text-[11px] text-[#9a9898]">{{ forecast.note }}</div>
          <div v-if="forecast.factor_risk_contrib && Object.keys(forecast.factor_risk_contrib as object).length" class="mb-4">
            <div class="mb-1.5 text-[11px] font-medium text-[#646262]">因子风险贡献占比（事前）</div>
            <div class="flex h-3 w-full overflow-hidden rounded-[3px]">
              <div
                v-for="(v, k) in (forecast.factor_risk_contrib as Record<string, number>)"
                :key="String(k)"
                :style="{ width: Math.max((v * 100), 0.5) + '%', backgroundColor: ['#007aff', '#ff9f0a', '#30d158', '#bf5af2', '#ff3b30', '#64d2ff'][String(k).length % 6] }"
              />
            </div>
            <div class="mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
              <span v-for="(v, k) in (forecast.factor_risk_contrib as Record<string, number>)" :key="String(k)" class="text-[11px] font-mono text-[#646262]">
                {{ k }}: {{ (v * 100).toFixed(1) }}%
              </span>
            </div>
          </div>
          <div>
            <div class="mb-1.5 text-[11px] font-medium text-[#646262]">历史情景回放（真实行情窗口 × 当前权重）</div>
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
              <div v-for="s in historicalScenarios" :key="s.name" class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-3 py-2">
                <div class="text-xs font-medium text-[#201d1d]">{{ s.name }}</div>
                <div v-if="s.cum_return_pct == null" class="mt-1 text-[11px] text-[#9a9898]">区间内无行情缓存（{{ s.note ?? '' }}）</div>
                <div v-else class="mt-1 grid grid-cols-3 gap-1 text-center">
                  <div><div class="text-[10px] text-[#9a9898]">累计</div><div class="text-xs font-mono font-bold" :class="s.cum_return_pct >= 0 ? 'text-[#ff3b30]' : 'text-[#248a3d]'">{{ s.cum_return_pct }}%</div></div>
                  <div><div class="text-[10px] text-[#9a9898]">最大回撤</div><div class="text-xs font-mono font-bold text-[#248a3d]">{{ s.max_drawdown_pct }}%</div></div>
                  <div><div class="text-[10px] text-[#9a9898]">最差单日</div><div class="text-xs font-mono font-bold text-[#248a3d]">{{ s.worst_day_pct }}%</div></div>
                </div>
              </div>
            </div>
          </div>
        </template>
      </Card>
    </div>

    <p class="mt-3 text-[11px] text-[#646262]">
      说明：前端仅为输入准备与图表展示；风格暴露、SLSQP 权重优化、绩效指标、压力冲击全部由后端完成。粘贴式面板便于无真实行情时验证。
    </p>
  </div>
</template>