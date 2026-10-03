<script setup lang="ts">
/**
 * 日内高频（分钟级）因子研究 — 公式求值 + 时刻 IC 曲线
 *
 * 链路：分钟缓存（5m 等）→ 清洗（竞价剔除/半日/一字标记）→ 公式求值
 * （ID_* / M_* 算子 + 现成高频因子）→ 折叠日频 → 综合报告；另提供
 * 「时刻 IC 曲线」回答「因子信息在一天里哪个时点最强」。
 */
import { computed, ref } from 'vue'
import { Button, Card, VChart } from '@/components/ui'

interface TimeIcPoint {
  time: string
  ic?: number | null
  rank_ic?: number | null
  icir?: number
  positive_ratio?: number
  n_days?: number
  note?: string
}
interface ComputeResult {
  ok?: boolean
  error?: string
  period?: string
  n_stocks?: number
  start?: string
  end?: string
  n_days?: number
  collapsed_to_daily?: boolean
  one_line_pct?: number | null
  half_day_pct?: number | null
  missing?: string[]
  note?: string
  factor_data?: Record<string, Record<string, number>>
  return_data?: Record<string, Record<string, number>>
}
interface IcByTimeResult {
  ok?: boolean
  error?: string
  times?: TimeIcPoint[]
  n_stocks?: number
  data_start?: string
  data_end?: string
  note?: string
}

const PERIODS = [
  { value: '5m', label: '5分钟（推荐）' },
  { value: '1m', label: '1分钟' },
  { value: '15m', label: '15分钟' },
  { value: '30m', label: '30分钟' },
  { value: '60m', label: '60分钟' },
]

const EXAMPLES = [
  { label: '尾盘动量', formula: 'RANK(TAIL_RET(12))' },
  { label: '开盘反转', formula: 'RANK(-OPEN_RET(6))' },
  { label: '已实现波动率反转', formula: 'RANK(-RV(48))' },
  { label: '跳跃占比', formula: 'RANK(JUMP_DAY())' },
  { label: '日内非流动性', formula: 'RANK(-AMIHUD5())' },
  { label: '收盘VWAP偏离', formula: 'RANK(VWAP_DEV())' },
  { label: '尾盘量能占比', formula: "RANK(ID_SUM(ID_SLICE(m_volume, '14:30', '15:00')) / ID_SUM(m_volume))" },
  { label: '价量熵(30m)', formula: 'RANK(-ID_PV_ENTROPY(m_close, m_volume, 30))' },
  { label: '价量熵(30m·20日均)', formula: 'RANK(-MA(ID_PV_ENTROPY(m_close, m_volume, 30), 20))' },
]

const period = ref('5m')
const formula = ref('')
const codes = ref('')
const startDate = ref('')
const endDate = ref('')
const loading = ref(false)
const errorMsg = ref('')
const result = ref<ComputeResult | null>(null)
const icTimes = ref<IcByTimeResult | null>(null)
const icLoading = ref(false)

// ── vectorbt 快速参数扫描（Beta） ──
interface ScanRow {
  groups: number
  rebalance_days: number
  total_return: number
  annual_return: number
  sharpe: number
  max_drawdown: number
  trades: number
}
interface ScanResult {
  ok?: boolean
  message?: string
  rows?: ScanRow[]
  best?: ScanRow | null
  n_stocks?: number
  n_dates?: number
  assumptions?: string[]
}
const scanGroups = ref('5,10,20')
const scanRebalance = ref('1,5,10,20')
const scanFee = ref(0.0015)
const scanDirection = ref(1)
const scanLoading = ref(false)
const scanError = ref('')
const scanResult = ref<ScanResult | null>(null)

function parseIntList(s: string): number[] {
  return s.split(',').map((x) => parseInt(x.trim(), 10)).filter((n) => Number.isFinite(n) && n > 0)
}

async function runScan() {
  if (!formula.value.trim()) return
  scanLoading.value = true
  scanError.value = ''
  scanResult.value = null
  try {
    scanResult.value = await postJson<ScanResult>('/api/vectorbt/quantile-scan', {
      formula: formula.value,
      period: period.value,
      stock_pool: codes.value.split(',').map((s) => s.trim()).filter(Boolean),
      start_date: startDate.value,
      end_date: endDate.value,
      groups: parseIntList(scanGroups.value),
      rebalance_days: parseIntList(scanRebalance.value),
      fee_rate: scanFee.value,
      direction: scanDirection.value,
    })
    if (scanResult.value?.ok === false) scanError.value = scanResult.value.message ?? '扫描失败'
  } catch (e) {
    scanError.value = e instanceof Error ? e.message : String(e)
  } finally {
    scanLoading.value = false
  }
}

// ── QuantZone 对拍（Beta） ──
interface ReconcileResult {
  ok?: boolean
  message?: string
  verdict?: string
  qz_factor?: string
  local_formula?: string
  n_points?: number
  metrics?: Record<string, number>
  sample?: { date: string; code: string; local: number; qz: number }[]
  qz_preview?: { date: string; code: string; value: number }[]
  local_missing?: string
  notes?: string[]
}
const qzFactor = ref('feat_single_amt_ratio_entropy_30m')
const qzLocalFormula = ref('ID_PV_ENTROPY(m_close, m_volume, 30)')
const qzMaxCodes = ref(20)
const qzLoading = ref(false)
const qzError = ref('')
const qzResult = ref<ReconcileResult | null>(null)

const VERDICT_LABELS: Record<string, string> = {
  match: '口径一致',
  direction_match: '排序一致（量级有差）',
  mismatch: '口径不一致',
  local_missing: '本地数据缺失',
  insufficient_overlap: '重叠样本不足',
}

async function runReconcile() {
  qzLoading.value = true
  qzError.value = ''
  qzResult.value = null
  try {
    qzResult.value = await postJson<ReconcileResult>('/api/quantzone/reconcile', {
      qz_factor: qzFactor.value,
      local_formula: qzLocalFormula.value,
      start_date: startDate.value,
      end_date: endDate.value,
      max_codes: qzMaxCodes.value,
    })
  } catch (e) {
    qzError.value = e instanceof Error ? e.message : String(e)
  } finally {
    qzLoading.value = false
  }
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

async function compute() {
  if (!formula.value.trim()) return
  loading.value = true
  errorMsg.value = ''
  icTimes.value = null
  try {
    result.value = await postJson<ComputeResult>('/api/factor/intraday/compute', {
      formula: formula.value,
      period: period.value,
      stock_pool: codes.value.split(',').map((s) => s.trim()).filter(Boolean),
      start_date: startDate.value,
      end_date: endDate.value,
    })
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

async function runIcByTime() {
  if (!formula.value.trim()) return
  icLoading.value = true
  errorMsg.value = ''
  try {
    icTimes.value = await postJson<IcByTimeResult>('/api/factor/intraday/ic-by-time', {
      formula: formula.value,
      period: period.value,
      stock_pool: codes.value.split(',').map((s) => s.trim()).filter(Boolean),
      start_date: startDate.value,
      end_date: endDate.value,
    })
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e)
  } finally {
    icLoading.value = false
  }
}

/** 时刻 IC 曲线图 */
const icChartOption = computed(() => {
  const times = icTimes.value?.times ?? []
  const valid = times.filter((t) => t.ic != null && t.n_days && (t.n_days ?? 0) > 0)
  if (!valid.length) return {}
  return {
    grid: { left: 48, right: 40, top: 30, bottom: 30 },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: valid.map((t) => t.time), name: '日内时刻', nameTextStyle: { fontSize: 10, color: '#646262' } },
    yAxis: [
      { type: 'value', axisLabel: { formatter: (v: number) => v.toFixed(3) } },
      { type: 'value', name: 'ICIR', nameTextStyle: { fontSize: 10, color: '#646262' }, splitLine: { show: false } },
    ],
    series: [
      { name: 'RankIC', type: 'line', smooth: true, data: valid.map((t) => t.rank_ic), itemStyle: { color: '#007aff' } },
      { name: 'ICIR', type: 'bar', yAxisIndex: 1, data: valid.map((t) => t.icir ?? 0), itemStyle: { color: 'rgba(191,90,242,0.45)' }, barWidth: '40%' },
    ],
  }
})

const metaRows = computed(() => {
  const r = result.value
  if (!r) return []
  const rows: [string, string][] = []
  rows.push(['周期', `${r.period ?? ''}（清洗 ${r.n_stocks ?? 0} 只标的）`])
  rows.push(['区间', `${r.start ?? ''} ~ ${r.end ?? ''}（${r.n_days ?? 0} 个交易日）`])
  rows.push(['折叠为日频', r.collapsed_to_daily ? '是（分钟结果 → ID_LAST 折叠）' : '否（公式直接返回日频）'])
  if (r.one_line_pct != null) rows.push(['一字板占比', (r.one_line_pct * 100).toFixed(2) + '%'])
  if (r.half_day_pct != null) rows.push(['半日市占比', (r.half_day_pct * 100).toFixed(2) + '%'])
  if (r.missing?.length) rows.push(['缺失代码', r.missing.slice(0, 5).join(', ')])
  return rows
})
</script>

<template>
  <div class="flex flex-col gap-3">
    <Card title="日内高频因子 · 分钟级研究">
      <template #extra>
        <span class="rounded-[3px] bg-[rgba(255,159,10,0.15)] px-1.5 py-0.5 text-[10px] font-medium text-[#cc7f08]">Beta</span>
      </template>
      <div class="flex flex-wrap items-center gap-2">
        <select v-model="period" class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2 py-1 text-xs">
          <option v-for="p in PERIODS" :key="p.value" :value="p.value">{{ p.label }}</option>
        </select>
        <input
          v-model="codes"
          type="text"
          placeholder="股票池（逗号分隔，留空=全部 5m 缓存）"
          class="min-w-[200px] flex-1 rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2 py-1 text-xs font-mono outline-none placeholder:text-[#9a9898]"
        />
        <input v-model="startDate" type="date" class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-1.5 py-1 text-xs" />
        <input v-model="endDate" type="date" class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-1.5 py-1 text-xs" />
      </div>

      <div class="mt-2 flex flex-wrap gap-1.5">
        <span class="text-[11px] leading-6 text-[#646262]">示例：</span>
        <button
          v-for="ex in EXAMPLES"
          :key="ex.label"
          class="rounded-[3px] border border-[rgba(0,122,255,0.35)] bg-[rgba(0,122,255,0.06)] px-1.5 py-0.5 text-[11px] text-[#007aff] hover:bg-[rgba(0,122,255,0.12)]"
          @click="formula = ex.formula"
        >
          {{ ex.label }}
        </button>
      </div>

      <textarea
        v-model="formula"
        rows="4"
        spellcheck="false"
        placeholder="分钟公式：RANK(TAIL_RET(12)) ｜ 字段 m_close/m_volume... ｜ 聚合 ID_LAST/ID_MEAN/ID_SLICE ｜ 序列 M_MA/M_DELAY"
        class="mt-2 w-full font-mono text-xs p-2 rounded-[4px] border border-[#e3e0e0] bg-[#f8f7f7] text-[#201d1d] focus:outline-none focus:border-[#007aff] resize-y"
      />
      <div class="mt-2 flex gap-2">
        <Button variant="primary" size="sm" :loading="loading" @click="compute">计算因子（折叠日频）</Button>
        <Button variant="secondary" size="sm" :loading="icLoading" @click="runIcByTime">时刻 IC 曲线</Button>
      </div>
      <div v-if="errorMsg" class="mt-3 rounded-[4px] border border-[#ff3b30] bg-[#ff3b30]/10 px-3 py-2 font-mono text-xs text-[#ff3b30]">{{ errorMsg }}</div>
      <div v-if="result?.error" class="mt-3 rounded-[4px] border border-[#ff3b30] bg-[#ff3b30]/10 px-3 py-2 font-mono text-xs text-[#ff3b30]">{{ result.error }}</div>
      <div v-if="result?.note" class="mt-3 text-[11px] text-[#9a9898]">{{ result.note }}</div>
      <div v-if="result" class="mt-3 grid grid-cols-1 lg:grid-cols-3 gap-2">
        <div
          v-for="[k, v] in metaRows"
          :key="k"
          class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2.5 py-1.5"
        >
          <div class="text-[11px] text-[#646262]">{{ k }}</div>
          <div class="text-xs font-mono text-[#201d1d]">{{ v }}</div>
        </div>
      </div>
    </Card>

    <Card title="时刻 IC 曲线 — 因子信息随时点分布（指导执行时点）">
      <div v-if="!icChartOption.series" class="py-10 text-center text-xs text-[#646262]">
        先写公式点「时刻 IC 曲线」：同一公式在 09:45/10:30/11:15/14:00/14:45/14:55 各取截面，对同一次日收益算 RankIC
      </div>
      <template v-else>
        <VChart :option="icChartOption" :height="260" />
        <div class="mt-2 flex flex-wrap gap-1.5">
          <span
            v-for="t in (icTimes?.times ?? []).filter((x) => x.ic != null)"
            :key="t.time"
            class="rounded-[3px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-2 py-1 text-[11px] font-mono"
          >
            {{ t.time }} ｜ RankIC {{ (t.rank_ic ?? 0).toFixed(4) }} ｜ ICIR {{ (t.icir ?? 0).toFixed(2) }} ｜ 正值占比 {{ ((t.positive_ratio ?? 0) * 100).toFixed(0) }}%
          </span>
        </div>
        <div v-if="icTimes?.note" class="mt-2 text-[11px] text-[#9a9898]">{{ icTimes.note }}</div>
      </template>
    </Card>
    <Card title="快速参数扫描 · vectorbt">
      <template #extra>
        <span class="rounded-[3px] bg-[rgba(255,159,10,0.15)] px-1.5 py-0.5 text-[10px] font-medium text-[#cc7f08]">Beta</span>
      </template>
      <div class="text-[11px] leading-5 text-[#646262]">
        对上方公式跑 分组数 × 调仓周期 参数网格（等权目标仓位 + 固定费率的简化假设，用于快速筛参数区域；与生产回测口径不同，数字不直接互比）。
      </div>
      <div class="mt-2 flex flex-wrap items-center gap-2">
        <label class="text-[11px] text-[#646262]">分组数</label>
        <input v-model="scanGroups" type="text" class="w-24 rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2 py-1 font-mono text-xs" />
        <label class="text-[11px] text-[#646262]">调仓(日)</label>
        <input v-model="scanRebalance" type="text" class="w-28 rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2 py-1 font-mono text-xs" />
        <label class="text-[11px] text-[#646262]">单边费率</label>
        <input v-model.number="scanFee" type="number" step="0.0005" min="0" class="w-20 rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2 py-1 font-mono text-xs" />
        <select v-model.number="scanDirection" class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2 py-1 text-xs">
          <option :value="1">高值做多</option>
          <option :value="-1">低值做多</option>
        </select>
        <Button variant="secondary" size="sm" :loading="scanLoading" :disabled="!formula.trim()" @click="runScan">运行扫描</Button>
      </div>
      <div v-if="scanError" class="mt-2 rounded-[4px] border border-[#ff3b30] bg-[#ff3b30]/10 px-3 py-2 font-mono text-xs text-[#ff3b30]">{{ scanError }}</div>
      <div v-if="scanResult?.rows?.length" class="mt-2">
        <div v-if="scanResult.best" class="mb-1.5 text-[11px] text-[#646262]">
          最优（按 Sharpe）：{{ scanResult.best.groups }} 组 / {{ scanResult.best.rebalance_days }} 日调仓 ｜ 年化 {{ (scanResult.best.annual_return * 100).toFixed(2) }}% ｜ 回撤 {{ (scanResult.best.max_drawdown * 100).toFixed(2) }}%
        </div>
        <table class="w-full text-left font-mono text-[11px]">
          <thead>
            <tr class="border-b border-[rgba(15,0,0,0.12)] text-[#646262]">
              <th class="py-1 pr-2">分组</th>
              <th class="py-1 pr-2">调仓(日)</th>
              <th class="py-1 pr-2">累计收益</th>
              <th class="py-1 pr-2">年化</th>
              <th class="py-1 pr-2">Sharpe</th>
              <th class="py-1 pr-2">最大回撤</th>
              <th class="py-1">交易次数</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in scanResult.rows" :key="`${r.groups}-${r.rebalance_days}`" class="border-b border-[rgba(15,0,0,0.06)]">
              <td class="py-1 pr-2">{{ r.groups }}</td>
              <td class="py-1 pr-2">{{ r.rebalance_days }}</td>
              <td class="py-1 pr-2">{{ (r.total_return * 100).toFixed(1) }}%</td>
              <td class="py-1 pr-2">{{ (r.annual_return * 100).toFixed(1) }}%</td>
              <td class="py-1 pr-2">{{ r.sharpe.toFixed(2) }}</td>
              <td class="py-1 pr-2">{{ (r.max_drawdown * 100).toFixed(1) }}%</td>
              <td class="py-1">{{ r.trades }}</td>
            </tr>
          </tbody>
        </table>
        <div v-if="scanResult.assumptions?.length" class="mt-1.5 text-[10px] leading-4 text-[#9a9898]">
          假设：{{ scanResult.assumptions.join('；') }}
        </div>
      </div>
    </Card>

    <Card title="QuantZone 对拍 — 本地实现 vs 官方因子值">
      <template #extra>
        <span class="rounded-[3px] bg-[rgba(255,159,10,0.15)] px-1.5 py-0.5 text-[10px] font-medium text-[#cc7f08]">Beta</span>
      </template>
      <div class="text-[11px] leading-5 text-[#646262]">
        同股票同日期逐点对比本地公式与 QuantZone 官方因子值，快速区分「实现口径差」与「数据差」。对拍公式须为原始值（不带 RANK）。密钥在 .env（QZ_ACCESS_KEY / QZ_SIGN_SECRET）。
      </div>
      <div class="mt-2 grid grid-cols-1 gap-2 lg:grid-cols-2">
        <div>
          <div class="mb-1 text-[11px] text-[#646262]">QZ 因子名</div>
          <input v-model="qzFactor" type="text" class="w-full rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2 py-1 font-mono text-xs" />
        </div>
        <div>
          <div class="mb-1 text-[11px] text-[#646262]">本地原始值公式</div>
          <input v-model="qzLocalFormula" type="text" class="w-full rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2 py-1 font-mono text-xs" />
        </div>
      </div>
      <div class="mt-2 flex items-center gap-2">
        <label class="text-[11px] text-[#646262]">股票数上限</label>
        <input v-model.number="qzMaxCodes" type="number" min="2" max="100" class="w-20 rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2 py-1 font-mono text-xs" />
        <Button variant="secondary" size="sm" :loading="qzLoading" @click="runReconcile">运行对拍</Button>
      </div>
      <div v-if="qzError" class="mt-2 rounded-[4px] border border-[#ff3b30] bg-[#ff3b30]/10 px-3 py-2 font-mono text-xs text-[#ff3b30]">{{ qzError }}</div>
      <div v-if="qzResult" class="mt-2">
        <div v-if="qzResult.message" class="rounded-[4px] border border-[#ff3b30] bg-[#ff3b30]/10 px-3 py-2 font-mono text-xs text-[#ff3b30]">{{ qzResult.message }}</div>
        <template v-else>
          <div class="flex flex-wrap items-center gap-2">
            <span class="rounded-[3px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2 py-1 text-[11px] font-medium">
              判定：{{ VERDICT_LABELS[qzResult.verdict ?? ''] ?? qzResult.verdict }}
            </span>
            <span v-if="qzResult.n_points" class="rounded-[3px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2 py-1 font-mono text-[11px]">
              重叠 {{ qzResult.n_points }} 点 ｜ 相关 {{ (qzResult.metrics?.corr ?? 0).toFixed(6) }} ｜ 平均绝对差 {{ (qzResult.metrics?.mean_abs_diff ?? 0).toExponential(2) }} ｜ 相对差≤1% 占比 {{ ((qzResult.metrics?.match_ratio_rel1pct ?? 0) * 100).toFixed(1) }}%
            </span>
          </div>
          <div v-if="qzResult.local_missing" class="mt-1.5 text-[11px] text-[#cc7f08]">{{ qzResult.local_missing }}</div>
          <div v-if="qzResult.notes?.length" class="mt-1.5 text-[11px] leading-4 text-[#9a9898]">{{ qzResult.notes.join('；') }}</div>
          <table v-if="qzResult.sample?.length" class="mt-2 w-full text-left font-mono text-[11px]">
            <thead>
              <tr class="border-b border-[rgba(15,0,0,0.12)] text-[#646262]">
                <th class="py-1 pr-2">日期</th>
                <th class="py-1 pr-2">代码</th>
                <th class="py-1 pr-2">本地值</th>
                <th class="py-1">QZ 值</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="s in qzResult.sample" :key="`${s.date}-${s.code}`" class="border-b border-[rgba(15,0,0,0.06)]">
                <td class="py-1 pr-2">{{ s.date }}</td>
                <td class="py-1 pr-2">{{ s.code }}</td>
                <td class="py-1 pr-2">{{ s.local.toFixed(6) }}</td>
                <td class="py-1">{{ s.qz.toFixed(6) }}</td>
              </tr>
            </tbody>
          </table>
          <div v-if="!qzResult.sample?.length && qzResult.qz_preview?.length" class="mt-2 text-[11px] text-[#9a9898]">
            QZ 因子值预览（本地无可对比数据）：{{ qzResult.qz_preview.slice(0, 5).map((p) => `${p.date} ${p.code} ${p.value.toFixed(4)}`).join('，') }}
          </div>
        </template>
      </div>
    </Card>
  </div>
</template>
