<script setup lang="ts">
import { computed, onActivated, onMounted, reactive, ref } from 'vue'
import { Button, Card, Dialog, Input, Select, Tabs } from '@/components/ui'
import type { SelectOption, TabItem } from '@/components/ui'

type Phase = 'validation' | 'holdout' | 'monitor'
type ReviewState = 'active' | 'watch' | 'dormant' | 'retired'
type JsonRecord = Record<string, unknown>
interface Stats {
  status?: string
  n_obs?: number
  mean?: number
  se?: number
  ci_low?: number
  ci_high?: number
  p_value?: number
  lags?: number
}
interface Track {
  status?: string
  ic?: Stats
  net?: Stats
  returns?: Record<string, number>
}
interface ResearchResult {
  status?: string
  decision?: string
  source?: string
  summary?: unknown
  tracks?: Record<string, Track>
  primary?: Stats
  bootstrap?: JsonRecord
  regime?: {
    status?: string
    conditional?: { state?: string; n_obs?: number; mean?: number; shrunk_mean?: number; eligible?: boolean }[]
    comparison?: JsonRecord
  }
  monitor?: JsonRecord
  manifest?: JsonRecord
  limitations?: string[]
}
interface Trial {
  id: string
  study_id: string
  formula: string
  direction: 1 | -1
  rationale: string
  created_at: number
}
interface Run {
  id: string
  study_id: string
  trial_id: string
  phase: Phase
  status: 'running' | 'completed' | 'awaiting_data' | 'failed'
  result?: ResearchResult | null
  error?: string | null
  created_at: number
}
interface Study {
  id: string
  title: string
  hypothesis: string
  sources: string[]
  protocol: JsonRecord
  protocol_hash: string
  state: string
  selected_trial_id: string | null
  universe: string[]
  created_at: number
  trials?: Trial[]
  runs?: Run[]
  reviews?: JsonRecord[]
}
interface Guidance {
  principles?: string[]
  roadmap?: { period: string; objective: string; acceptance: string; do_not: string }[]
  audit_checklist?: string[]
}
interface NumberField {
  key: string
  label: string
  initial: string
  min?: number
  max?: number
  exclusiveMin?: boolean
  exclusiveMax?: boolean
  integer?: boolean
}

const commonFields: NumberField[] = [
  { key: 'horizon', label: '预测周期（交易日）', initial: '5', min: 1, max: 60, integer: true },
  { key: 'top_n', label: '持仓数量 Top N', initial: '20', min: 1, max: 1000, integer: true },
  { key: 'rebalance_days', label: '调仓间隔（交易日）', initial: '5', min: 1, max: 252, integer: true },
  { key: 'alpha', label: '显著性水平 α', initial: '0.05', min: 0, max: 0.2, exclusiveMin: true },
  { key: 'trial_budget', label: '候选试验预算', initial: '20', min: 1, max: 1000, integer: true },
  { key: 'min_dates', label: '最少有效日期数', initial: '60', min: 20, max: 1000, integer: true },
  { key: 'min_stocks', label: '最少有效股票数', initial: '30', min: 10, max: 10000, integer: true },
]
const advancedFields: NumberField[] = [
  { key: 'commission_rate', label: '佣金率（小数）', initial: '0.001', min: 0, max: 0.1 },
  { key: 'slippage', label: '滑点率（小数）', initial: '0.001', min: 0, max: 0.1 },
  { key: 'stamp_tax', label: '印花税率（小数）', initial: '0.0005', min: 0, max: 0.1 },
  { key: 'initial_capital', label: '初始资金（元）', initial: '1000000', min: 0, exclusiveMin: true },
  { key: 'candidate_weight', label: '候选组合权重', initial: '0.25', min: 0, max: 1, exclusiveMin: true },
  { key: 'monitor_window', label: '监控窗口（交易日）', initial: '60', min: 20, integer: true },
  { key: 'review_every', label: '复核间隔（交易日）', initial: '20', min: 1, integer: true },
  { key: 'minimum_effect', label: '最小每日成本后增量（小数）', initial: '0' },
  { key: 'regime_shrinkage', label: '状态估计收缩强度', initial: '60', min: 1, integer: true },
]
const numberFields = [...commonFields, ...advancedFields]
const dateFields = [
  { key: 'start_date', label: '开始日期 · start_date' },
  { key: 'train_end', label: '训练截止 · train_end' },
  { key: 'validation_end', label: '验证截止 · validation_end' },
  { key: 'end_date', label: '留出截止 · end_date' },
]
const phases: { key: Phase; label: string }[] = [
  { key: 'validation', label: '运行验证' },
  { key: 'holdout', label: '选定并运行留出' },
  { key: 'monitor', label: '运行监控' },
]
const directionOptions: SelectOption[] = [
  { value: '1', label: '正向（1）· 因子越大越优先' },
  { value: '-1', label: '反向（-1）· 因子越小越优先' },
]
const reviewOptions: SelectOption[] = [
  { value: 'active', label: 'active · 启用' },
  { value: 'watch', label: 'watch · 观察' },
  { value: 'dormant', label: 'dormant · 休眠' },
  { value: 'retired', label: 'retired · 退役' },
]
const evidenceTabs: TabItem[] = [
  { key: 'primary', label: '主检验' },
  { key: 'tracks', label: '三轨对照' },
  { key: 'regime', label: '状态 / 监控' },
  { key: 'audit', label: '审计证据' },
]
const labels: Record<string, string> = {
  research: '研究中', active: '启用', watch: '观察', dormant: '休眠', retired: '退役',
  running: '计算中', completed: '计算完成', awaiting_data: '等待 QMT 数据 · 未验证', failed: '运行失败 · 未验证',
  supported: '证据支持', inconclusive: '证据不足以定论', insufficient_data: '数据不足 · 未验证',
  review_needed: '需要人工复核', validation: '验证集', holdout: '留出集', monitor: '监控',
}
const studies = ref<Study[]>([])
const selectedStudyId = ref('')
const study = ref<Study | null>(null)
const listLoading = ref(false)
const detailLoading = ref(false)
const listError = ref('')
const detailError = ref('')
const mutationError = ref('')
const notice = ref('')
const pending = ref<{ kind: string; trialId?: string; phase?: Phase } | null>(null)
const showCreate = ref(false)
const createError = ref('')
const selectedRunId = ref('')
const evidenceTab = ref('primary')
const holdoutTrial = ref<Trial | null>(null)
const guidance = ref<Guidance | null>(null)
const guidanceLoading = ref(false)
const guidanceError = ref('')
let detailRequest = 0
let loadedOnce = false

function newDraft() {
  return { title: '', hypothesis: '', sources: '', codes: '', baselineFormulas: '', regimeIndex: '000300.SH',
    dates: Object.fromEntries(dateFields.map((field) => [field.key, ''])) as Record<string, string>,
    numbers: Object.fromEntries(numberFields.map((field) => [field.key, field.initial])) as Record<string, string> }
}
const draft = reactive(newDraft())
// Keep separate drafts when switching studies; failed saves never discard user input.
const trialDrafts = reactive<Record<string, { formula: string; direction: string; rationale: string }>>({})
const reviewDrafts = reactive<Record<string, { state: string; note: string }>>({})
function ensureDrafts(id: string) {
  trialDrafts[id] ??= { formula: '', direction: '1', rationale: '' }
  reviewDrafts[id] ??= { state: 'watch', note: '' }
}
const trialDraft = computed(() => trialDrafts[selectedStudyId.value])
const reviewDraft = computed(() => reviewDrafts[selectedStudyId.value])
const trials = computed(() => study.value?.trials ?? [])
const runs = computed(() => [...(study.value?.runs ?? [])].sort((a, b) => b.created_at - a.created_at))
const serverRunning = computed(() => runs.value.some((run) => run.status === 'running'))
const ready = computed(() => !!study.value && study.value.id === selectedStudyId.value && !detailLoading.value && !detailError.value)
const frozen = computed(() => !!study.value?.selected_trial_id || runs.value.some((run) => run.phase === 'holdout'))
const selectedRun = computed(() => runs.value.find((run) => run.id === selectedRunId.value))
const result = computed(() => selectedRun.value?.result)
const runOptions = computed<SelectOption[]>(() => runs.value.map((run) => ({
  value: run.id,
  label: `${dateTime(run.created_at)} · ${label(run.phase)} · ${trialName(run.trial_id)} · ${label(run.status)}`,
})))
const trackRows = computed(() => [
  { key: 'raw', name: '原始因子', data: result.value?.tracks?.raw },
  { key: 'neutralized', name: '中性化因子', data: result.value?.tracks?.neutralized },
  { key: 'incremental', name: '增量组合', data: result.value?.tracks?.incremental },
])
const primaryMetrics = computed(() => {
  const stats = result.value?.primary
  return [
    { label: '主检验状态', value: label(stats?.status) },
    { label: '有效观测 n', value: fmt(stats?.n_obs) },
    { label: '均值 mean', value: fmt(stats?.mean) },
    { label: '标准误 SE', value: fmt(stats?.se) },
    { label: '置信区间 CI', value: interval(stats) },
    { label: 'p 值', value: fmt(stats?.p_value) },
    { label: '滞后阶数 lags', value: fmt(stats?.lags) },
    { label: '冻结显著性水平 α', value: fmt(study.value?.protocol?.alpha) },
  ]
})
const createReason = computed(() => {
  if (pending.value) return '正在保存或计算，请勿重复提交。'
  if (!draft.title.trim() || !draft.hypothesis.trim()) return '请填写研究标题与可检验的假设。'
  if (!lines(draft.sources).length) return '请至少填写一条假设来源。'
  const dates = dateFields.map((field) => draft.dates[field.key])
  if (dates.some((date) => !validDate(date))) return '四个日期必须手动填写完整；不会推测 QMT 的历史数据可得性。'
  if (!dates.every((date, index) => index === 0 || dates[index - 1] < date)) return '日期必须满足 start_date < train_end < validation_end < end_date。'
  for (const field of numberFields) {
    // Vue's native number input may emit a number through the shared Input model.
    const text = String(draft.numbers[field.key] ?? '')
    const value = Number(text)
    if (!text.trim() || !Number.isFinite(value) || (field.integer && !Number.isInteger(value))) return `请填写有效的${field.label}${field.integer ? '（整数）' : ''}。`
    if (field.min !== undefined && (field.exclusiveMin ? value <= field.min : value < field.min)) return `${field.label}须${field.exclusiveMin ? '大于' : '不小于'} ${field.min}。`
    if (field.max !== undefined && (field.exclusiveMax ? value >= field.max : value > field.max)) return `${field.label}须${field.exclusiveMax ? '小于' : '不大于'} ${field.max}。`
  }
  if (!draft.regimeIndex.trim()) return '请填写 QMT 状态基准指数代码。'
  return ''
})
const actionReason = computed(() => {
  if (pending.value) return '请求正在处理，请勿重复提交；长计算不会被客户端计时中断。'
  if (detailLoading.value) return '正在同步研究状态。'
  if (!ready.value) return '服务器状态尚未确认，请先刷新研究。'
  if (serverRunning.value) return '服务器仍有计算中的任务，请刷新查看完成状态。'
  return ''
})
const registerReason = computed(() => {
  if (actionReason.value) return actionReason.value
  if (frozen.value) return '已不可逆选定留出候选，禁止再登记候选或修改协议。'
  const budget = study.value?.protocol?.trial_budget
  if (typeof budget === 'number' && trials.value.length >= budget) return '已达到冻结协议的候选试验预算。'
  if (!trialDraft.value?.formula.trim() || !trialDraft.value?.rationale.trim()) return '请填写候选公式与研究理由。'
  return ''
})
const reviewReason = computed(() => {
  if (actionReason.value) return actionReason.value
  if (!reviewDraft.value?.note.trim()) return '人工复核必须填写理由，不会自动启用或退役。'
  if (!reviewOptions.some((option) => option.value === reviewDraft.value?.state)) return '请选择目标状态。'
  if (study.value?.state === 'retired' && reviewDraft.value.state !== 'retired') return '退役研究不能直接恢复；请重新登记研究。'
  if (!runs.value.some((run) => run.status === 'completed')) return '尚无完成的研究证据，不能改变生命周期状态。'
  if (reviewDraft.value.state === 'active' && !runs.value.some((run) => run.trial_id === study.value?.selected_trial_id && run.phase === 'holdout' && run.status === 'completed' && run.result?.decision === 'supported')) return '启用需要选定候选的最终留出证据支持。'
  return ''
})
const holdoutReason = computed(() => holdoutTrial.value ? phaseReason(holdoutTrial.value, 'holdout') : '请先选择候选。')

function lines(value: string) { return value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean) }
function validDate(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const parsed = new Date(`${value}T00:00:00Z`)
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value
}
function label(value: unknown): string {
  return typeof value === 'string' && value ? labels[value] ?? value : '未验证'
}
function fmt(value: unknown): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—'
  if (Number.isInteger(value)) return String(value)
  if (Math.abs(value) < 0.0001) return value.toExponential(3)
  return value.toFixed(4)
}
function interval(stats?: Stats): string {
  if (stats?.ci_low == null && stats?.ci_high == null) return '未验证'
  return `[${fmt(stats?.ci_low)}, ${fmt(stats?.ci_high)}]`
}
function pretty(value: unknown): string {
  if (value == null || value === '') return '未验证'
  return typeof value === 'string' ? value : JSON.stringify(value, null, 2)
}
function dateTime(seconds: unknown): string {
  if (typeof seconds !== 'number' || !Number.isFinite(seconds)) return '—'
  const date = new Date(seconds * 1000)
  return Number.isFinite(date.getTime()) ? date.toLocaleString('zh-CN', { hour12: false }) : '—'
}
function trialName(id: string): string {
  const index = trials.value.findIndex((trial) => trial.id === id)
  return index < 0 ? id : `候选 ${index + 1}`
}
function latestRun(trialId: string, phase: Phase) {
  return runs.value.find((run) => run.trial_id === trialId && run.phase === phase)
}
function phaseReason(trial: Trial, phase: Phase): string {
  if (actionReason.value) return actionReason.value
  if (phase === 'validation') {
    if (frozen.value) return '留出候选已选定，验证阶段已冻结。'
    return latestRun(trial.id, 'validation')?.status === 'completed' ? '该候选验证已完成，不能覆盖旧证据；参数变化请登记新候选。' : ''
  }
  const lockedTrialId = study.value?.selected_trial_id || runs.value.find((run) => run.phase === 'holdout')?.trial_id
  if (lockedTrialId && lockedTrialId !== trial.id) return '已选定其他候选，不可更换。'
  if (phase === 'holdout') {
    if (latestRun(trial.id, 'validation')?.status !== 'completed') return '须先完成该候选的 validation 验证。'
    if (latestRun(trial.id, 'holdout')?.status === 'completed') return '留出已完成，不可重复开启；请进入监控。'
    return ''
  }
  if (study.value?.selected_trial_id !== trial.id || latestRun(trial.id, 'holdout')?.status !== 'completed') return '须先选定该候选并完成 holdout 留出验证。'
  return ''
}
function errorText(error: unknown): string {
  return error instanceof TypeError ? '无法确认后端响应，请检查连接并刷新服务器状态后再操作。' : error instanceof Error ? error.message : String(error)
}
async function request<T>(path: string, body?: unknown): Promise<T> {
  // No timeout/AbortSignal: QMT calculations may take a long time.
  const response = await fetch(`/api/research${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  })
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = Array.isArray(data?.detail)
      ? data.detail.map((item: { loc?: (string | number)[]; msg?: string }) => `${item.loc?.join('.') ?? '参数'}: ${item.msg ?? '无效'}`).join('；')
      : typeof data?.detail === 'string' ? data.detail : `接口错误 (HTTP ${response.status})`
    throw new Error(detail)
  }
  if (data === null) throw new Error('接口未返回 JSON，操作结果未确认；请刷新服务器状态。')
  return data as T
}
function applyStudy(data: Study) {
  study.value = data
  const index = studies.value.findIndex((item) => item.id === data.id)
  if (index < 0) studies.value.unshift(data)
  else studies.value[index] = data
  if (!runs.value.some((run) => run.id === selectedRunId.value)) selectedRunId.value = runs.value[0]?.id ?? ''
}
async function loadStudies() {
  listLoading.value = true
  listError.value = ''
  try {
    const data = await request<Study[]>('/studies')
    if (!Array.isArray(data)) throw new Error('研究列表响应格式不正确。')
    studies.value = data
  } catch (error) { listError.value = errorText(error) }
  finally { listLoading.value = false }
}
async function loadStudy(id: string) {
  const token = ++detailRequest
  detailLoading.value = true
  detailError.value = ''
  try {
    const data = await request<Study>(`/studies/${encodeURIComponent(id)}`)
    if (data.id !== id) throw new Error('研究详情与所选研究不一致，请重新刷新。')
    if (token === detailRequest && selectedStudyId.value === id) applyStudy(data)
  } catch (error) {
    if (token === detailRequest && selectedStudyId.value === id) detailError.value = errorText(error)
  } finally { if (token === detailRequest) detailLoading.value = false }
}
async function selectStudy(id: string) {
  if (pending.value || detailLoading.value) return
  ensureDrafts(id)
  selectedStudyId.value = id
  selectedRunId.value = ''
  study.value = null
  mutationError.value = ''
  notice.value = ''
  holdoutTrial.value = null
  await loadStudy(id)
}
async function refresh() {
  if (pending.value || listLoading.value || detailLoading.value) return
  await loadStudies()
  if (selectedStudyId.value) await loadStudy(selectedStudyId.value)
  else if (studies.value.length) await selectStudy(studies.value[0].id)
  loadedOnce = true
}
async function syncStudy(id: string) {
  // Reconcile even after a failed POST: a lost response may still have committed on the server.
  await Promise.all([loadStudy(id), loadStudies()])
}
async function createStudy() {
  if (createReason.value) return
  pending.value = { kind: 'create' }
  createError.value = ''
  notice.value = ''
  try {
    const data = await request<Study>('/studies', {
      title: draft.title.trim(), hypothesis: draft.hypothesis.trim(), sources: lines(draft.sources),
      protocol: {
        ...draft.dates,
        ...Object.fromEntries(numberFields.map((field) => [field.key, Number(draft.numbers[field.key])])),
        codes: [...new Set(draft.codes.split(/[\s,，;；]+/).filter(Boolean).map((code) => code.toUpperCase()))],
        baseline_formulas: lines(draft.baselineFormulas), regime_index: draft.regimeIndex.trim().toUpperCase(),
      },
    })
    selectedStudyId.value = data.id
    ensureDrafts(data.id)
    selectedRunId.value = ''
    mutationError.value = ''
    applyStudy(data)
    Object.assign(draft, newDraft())
    showCreate.value = false
    notice.value = '假设已登记，协议已冻结。尚无实证结果，未验证。'
    await syncStudy(data.id)
  } catch (error) { createError.value = `${errorText(error)} 表单已保留；如响应中断，请先刷新列表确认是否已创建。` }
  finally { pending.value = null }
}
async function registerTrial() {
  if (registerReason.value || !study.value || !trialDraft.value) return
  const id = study.value.id
  const form = trialDraft.value
  pending.value = { kind: 'trial' }
  mutationError.value = ''
  notice.value = ''
  try {
    await request<Trial>(`/studies/${encodeURIComponent(id)}/trials`, {
      formula: form.formula.trim(), direction: Number(form.direction) as 1 | -1, rationale: form.rationale.trim(),
    })
    trialDrafts[id] = { formula: '', direction: '1', rationale: '' }
    notice.value = '候选已登记，尚未验证。'
  } catch (error) { mutationError.value = errorText(error) }
  finally { await syncStudy(id); pending.value = null }
}
function startPhase(trial: Trial, phase: Phase) {
  if (phaseReason(trial, phase)) return
  if (phase === 'holdout') holdoutTrial.value = trial
  else void runTrial(trial, phase)
}
function confirmHoldout() {
  const trial = holdoutTrial.value
  if (!trial || holdoutReason.value) return
  holdoutTrial.value = null
  void runTrial(trial, 'holdout')
}
async function runTrial(trial: Trial, phase: Phase) {
  if (phaseReason(trial, phase) || !study.value) return
  const id = study.value.id
  pending.value = { kind: 'run', trialId: trial.id, phase }
  mutationError.value = ''
  notice.value = ''
  try {
    const run = await request<Run>(`/trials/${encodeURIComponent(trial.id)}/run`, { phase })
    if (study.value?.id === id) {
      study.value.runs = [run, ...(study.value.runs ?? []).filter((item) => item.id !== run.id)]
      selectedRunId.value = run.id
      evidenceTab.value = 'primary'
      if (phase === 'holdout') study.value.selected_trial_id = trial.id
    }
    notice.value = `${label(phase)}：${label(run.status)}。计算完成不等于证据支持，请查看结论与限制。`
  } catch (error) { mutationError.value = errorText(error) }
  finally { await syncStudy(id); pending.value = null }
}
async function submitReview() {
  if (reviewReason.value || !study.value || !reviewDraft.value) return
  const id = study.value.id
  const form = reviewDraft.value
  pending.value = { kind: 'review' }
  mutationError.value = ''
  notice.value = ''
  try {
    await request<unknown>(`/studies/${encodeURIComponent(id)}/review`, { target_state: form.state as ReviewState, note: form.note.trim() })
    form.note = ''
    notice.value = '人工复核已保存。生命周期状态不替代实证结论。'
  } catch (error) { mutationError.value = errorText(error) }
  finally { await syncStudy(id); pending.value = null }
}
async function loadGuidance() {
  if (guidanceLoading.value) return
  guidanceLoading.value = true
  guidanceError.value = ''
  try { guidance.value = await request<Guidance>('/guidance') }
  catch (error) { guidanceError.value = errorText(error) }
  finally { guidanceLoading.value = false }
}
function openGuidance(event: Event) {
  if ((event.target as HTMLDetailsElement).open && !guidance.value && !guidanceLoading.value) void loadGuidance()
}
function downloadEvidence() {
  if (!study.value || !ready.value) return
  const blob = new Blob([JSON.stringify(study.value, null, 2)], { type: 'application/json;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `research-${String(study.value.id).replace(/[^a-zA-Z0-9_-]/g, '_')}.json`
  anchor.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}
onMounted(() => { void refresh() })
onActivated(() => { if (loadedOnce) void refresh() })
</script>

<template>
  <section class="research-workbench space-y-4 font-mono text-sm text-[#201d1d]" aria-label="研究证据工作台">
    <Card title="研究证据 / 先冻结协议，再检验假设">
      <template #extra>
        <Button :disabled="!!pending" @click="showCreate = !showCreate">{{ showCreate ? '收起新建' : '新建研究' }}</Button>
      </template>
      <p class="text-xs leading-6 text-[#646262]">QMT 是唯一行情来源。不生成演示 IC、夏普或收益；没有实际数据就显示未验证。假设来源仅作研究依据，不会自动抓取材料或调用模型。</p>
      <p class="mt-1 text-xs leading-6">[1] 假设与冻结协议 → [2] 登记候选 / 验证 → [3] 不可逆选定 / 留出 → [4] 监控 / 人工复核</p>
    </Card>

    <Card v-if="showCreate" title="[1] 登记带来源的假设 · 创建即冻结全部协议">
      <form class="space-y-4" novalidate @submit.prevent="createStudy">
        <div class="form-grid">
          <label class="field">研究标题<Input v-model="draft.title" :disabled="!!pending" placeholder="填写研究问题，不预填示例研究" /></label>
          <label class="field">假设来源（每行一条，必填）<textarea v-model="draft.sources" :disabled="!!pending" rows="3" placeholder="文献、内部研究记录或材料出处；链接不会被自动访问" /></label>
          <label class="field full-width">可检验的假设<textarea v-model="draft.hypothesis" :disabled="!!pending" rows="3" placeholder="描述机制、预期方向、成立条件与可能的反证" /></label>
        </div>
        <div class="notice-box">四个日期必须手填，并满足 start_date &lt; train_end &lt; validation_end &lt; end_date。填写区间不代表 QMT 已有对应历史数据；实际可得性由后端检验。协议创建后没有编辑入口。</div>
        <div class="form-grid four-columns">
          <label v-for="field in dateFields" :key="field.key" class="field">{{ field.label }}<Input v-model="draft.dates[field.key]" type="date" :disabled="!!pending" /></label>
        </div>
        <label class="field">股票代码（可留空；空列表交由后端确定实际 QMT 股票池）<textarea v-model="draft.codes" :disabled="!!pending" rows="2" placeholder="以逗号、空格或换行分隔，使用 QMT 市场后缀代码" /></label>
        <div class="form-grid four-columns">
          <label v-for="field in commonFields" :key="field.key" class="field">{{ field.label }}<Input v-model="draft.numbers[field.key]" type="number" :min="field.min" :max="field.max" :step="field.integer ? 1 : 'any'" :disabled="!!pending" /></label>
        </div>
        <details class="fold">
          <summary>[+] 高级协议参数 · 成本、基线、状态与监控（同样冻结）</summary>
          <div class="form-grid four-columns mt-3">
            <label v-for="field in advancedFields" :key="field.key" class="field">{{ field.label }}<Input v-model="draft.numbers[field.key]" type="number" :min="field.min" :max="field.max" :step="field.integer ? 1 : 'any'" :disabled="!!pending" /></label>
            <label class="field">状态基准指数 · QMT<Input v-model="draft.regimeIndex" :disabled="!!pending" /></label>
            <label class="field full-width">基线公式（每行一条，可留空）<textarea v-model="draft.baselineFormulas" :disabled="!!pending" rows="3" placeholder="填写要比较的真实基线公式；不预置收益或评估结果" /></label>
          </div>
          <p class="hint mt-2">费率与权重使用小数而非百分数。默认数值仅为协议参数，不是已验证的数据或绩效。</p>
        </details>
        <p v-if="createError" role="alert" class="error-box">{{ createError }}</p>
        <div class="flex flex-wrap items-center gap-3">
          <Button type="submit" variant="primary" :loading="pending?.kind === 'create'" :disabled="!!createReason" :title="createReason || '创建后所有协议参数不可编辑'">创建并冻结协议</Button>
          <p class="hint">{{ createReason || '已填写必要信息；提交即永久冻结协议。' }}</p>
        </div>
      </form>
    </Card>

    <div class="workbench-grid">
      <aside class="min-w-0">
        <Card title="研究列表">
          <template #extra><Button size="sm" :loading="listLoading || detailLoading" :disabled="!!pending" @click="refresh">刷新</Button></template>
          <p v-if="listLoading" class="hint" role="status">正在读取服务器研究列表…</p>
          <p v-if="listError" role="alert" class="error-box">{{ listError }}</p>
          <p v-if="!listLoading && !listError && !studies.length" class="hint py-4">暂无研究，也没有演示卡片。请先新建带来源的假设。</p>
          <div v-if="studies.length" class="space-y-2">
            <Button v-for="item in studies" :key="item.id" class="study-button" :class="{ 'study-selected': selectedStudyId === item.id }" :disabled="!!pending || detailLoading || listLoading" :aria-pressed="selectedStudyId === item.id" @click="selectStudy(item.id)">
              <span class="block break-words">{{ item.title }}</span>
              <span class="mt-1 block text-xs font-normal text-[#646262]">{{ label(item.state) }} · {{ dateTime(item.created_at) }}</span>
            </Button>
          </div>
          <p class="hint mt-3">刷新从服务器恢复协议、候选、运行与复核记录，不在本地推断成功状态。</p>
        </Card>
      </aside>

      <div class="min-w-0 space-y-4" aria-live="polite">
        <p v-if="detailLoading" class="notice-box" role="status">正在同步研究详情…</p>
        <p v-if="detailError" role="alert" class="error-box">{{ detailError }} 当前信息可能过期；操作已禁用，请刷新。</p>
        <p v-if="mutationError" role="alert" class="error-box">{{ mutationError }} 未成功保存的表单已保留。</p>
        <p v-if="notice" class="notice-box" role="status">{{ notice }}</p>
        <p v-if="pending?.kind === 'run'" class="notice-box" role="status">{{ label(pending.phase) }}请求处理中。计算可能较长，不会因客户端超时中断；按钮已禁用，请勿重复提交。页面重载后请刷新服务器状态确认结果。</p>
        <p v-else-if="serverRunning" class="notice-box" role="status">服务器仍在计算，尚无最终结论。请使用「刷新」恢复最新运行状态，不要重复发起。</p>

        <template v-if="study">
          <Card :title="study.title">
            <template #extra><Button size="sm" :disabled="!ready || !!pending" @click="downloadEvidence">下载研究 JSON</Button></template>
            <div class="flex flex-wrap gap-x-4 gap-y-2 text-xs">
              <span>生命周期：{{ label(study.state) }}</span>
              <span>留出候选：{{ study.selected_trial_id ? trialName(study.selected_trial_id) : '尚未选定' }}</span>
              <span>数据源：仅 QMT</span>
            </div>
            <p class="mt-3 whitespace-pre-wrap break-words leading-6">{{ study.hypothesis }}</p>
            <div class="mt-3 text-xs"><strong>假设来源</strong><ul v-if="study.sources?.length" class="source-list"><li v-for="(source, index) in study.sources" :key="index">[{{ index + 1 }}] {{ source }}</li></ul><p v-else class="hint">未返回来源，需审计。</p></div>
            <details class="fold mt-3">
              <summary>[+] 查看冻结协议 / 实际股票池 / 协议哈希</summary>
              <p class="hint mt-3 break-all">研究 ID：{{ study.id }}<br />协议哈希：{{ study.protocol_hash || '未验证' }}</p>
              <pre class="json-block">{{ pretty(study.protocol) }}</pre>
              <p class="hint">服务器股票池：{{ study.universe?.length ? `${study.universe.length} 只（不等于有效样本数量）` : '尚未返回股票，数据可用性未验证' }}</p>
              <pre v-if="study.universe?.length" class="json-block">{{ study.universe.join(', ') }}</pre>
            </details>
            <p class="hint mt-3">下载仅由当前服务器详情在本地生成 Blob，不上传证据，不补齐缺失结果。人工状态不等于统计支持。</p>
          </Card>

          <Card title="[2] 候选登记与分阶段运行">
            <p class="hint mb-3">已登记 {{ trials.length }} 个 / 预算 {{ fmt(study.protocol?.trial_budget) }}。训练用于开发假设，验证用于比较候选；留出集只用于不可逆选定后的检验。</p>
            <form v-if="trialDraft" class="space-y-3" novalidate @submit.prevent="registerTrial">
              <label class="field">候选公式<textarea v-model="trialDraft.formula" :disabled="!!pending || frozen" rows="2" placeholder="输入待检验公式，不自动生成候选" /></label>
              <div class="form-grid">
                <div class="field"><span id="research-direction-label">方向</span><Select v-model="trialDraft.direction" :options="directionOptions" :disabled="!!pending || frozen" aria-labelledby="research-direction-label" /></div>
                <label class="field">登记理由<textarea v-model="trialDraft.rationale" :disabled="!!pending || frozen" rows="2" placeholder="解释公式与假设的关系，保留试验动机" /></label>
              </div>
              <div class="flex flex-wrap items-center gap-3"><Button type="submit" :loading="pending?.kind === 'trial'" :disabled="!!registerReason" :title="registerReason">登记候选</Button><p class="hint">{{ registerReason || '候选登记后保留记录，不覆盖既往试验。' }}</p></div>
            </form>
            <p v-if="!trials.length" class="hint mt-4">暂无候选，未验证。不会插入示例公式或指标。</p>
            <article v-for="(trial, index) in trials" :key="trial.id" class="trial-row">
              <div class="flex flex-wrap justify-between gap-2 text-xs"><strong>候选 {{ index + 1 }} · {{ trial.direction === -1 ? '反向 -1' : '正向 1' }}{{ study.selected_trial_id === trial.id ? ' · 已选定（不可逆）' : '' }}</strong><span class="text-[#646262]">{{ dateTime(trial.created_at) }}</span></div>
              <pre class="formula-block">{{ trial.formula }}</pre>
              <p class="hint whitespace-pre-wrap break-words">理由：{{ trial.rationale || '—' }}</p>
              <div class="phase-grid mt-3">
                <div v-for="phase in phases" :key="phase.key" class="space-y-2">
                  <Button size="sm" class="w-full" :loading="pending?.kind === 'run' && pending.trialId === trial.id && pending.phase === phase.key" :disabled="!!phaseReason(trial, phase.key)" :title="phaseReason(trial, phase.key) || (phase.key === 'holdout' ? '不可逆操作，点击后需确认' : '仅使用 QMT 实际数据运行')" @click="startPhase(trial, phase.key)">{{ phase.label }}</Button>
                  <p class="hint">{{ label(latestRun(trial.id, phase.key)?.status) }}</p>
                  <p v-if="phaseReason(trial, phase.key)" class="hint">{{ phaseReason(trial, phase.key) }}</p>
                  <p v-if="latestRun(trial.id, phase.key)?.error" class="text-xs text-[#d70015] break-words">{{ latestRun(trial.id, phase.key)?.error }}</p>
                </div>
              </div>
            </article>
          </Card>

          <Card title="[3] 运行证据 · 不以缺失值代替零">
            <p v-if="!runs.length" class="hint py-4">尚无运行记录。主检验、IC、净收益及状态条件效果均未验证。</p>
            <template v-else>
              <div class="field"><span id="research-run-label">选择运行记录（可查看历史失败 / 待数据记录）</span><Select v-model="selectedRunId" :options="runOptions" aria-labelledby="research-run-label" /></div>
              <template v-if="selectedRun">
                <div class="notice-box mt-3">
                  <p>{{ label(selectedRun.phase) }} / {{ label(selectedRun.status) }} · {{ dateTime(selectedRun.created_at) }}</p>
                  <p class="mt-1">结论：{{ label(result?.decision) }} · 结果状态：{{ label(result?.status) }} · 数据来源：{{ result?.source || '未验证（仅允许 QMT）' }}</p>
                  <p v-if="selectedRun.status !== 'completed' || !result" class="mt-1">未验证：{{ selectedRun.status === 'awaiting_data' ? '等待 QMT 提供符合冻结协议的数据，不使用其他来源兜底。' : selectedRun.status === 'running' ? '计算尚未完成，请刷新状态。' : '尚无完整证据，不能据此启用。' }}</p>
                </div>
                <p v-if="selectedRun.error" class="error-box mt-3" role="alert">{{ selectedRun.error }}</p>
                <p class="mt-3 whitespace-pre-wrap break-words text-xs leading-6">{{ pretty(result?.summary) }}</p>
                <div class="mt-3 overflow-x-auto"><Tabs :items="evidenceTabs" :active-key="evidenceTab" @change="(key) => evidenceTab = key" /></div>
                <div v-if="evidenceTab === 'primary'" class="mt-3 space-y-3">
                  <div class="metric-grid"><div v-for="metric in primaryMetrics" :key="metric.label" class="metric"><span class="hint">{{ metric.label }}</span><strong class="mt-1 block font-medium">{{ metric.value }}</strong></div></div>
                  <p class="hint">数值按后端原始单位显示，不推算、不年化、不补零。CI / p / n 必须结合冻结协议、试验预算与限制解释；计算完成不等于支持假设。</p>
                  <details class="fold"><summary>[+] Bootstrap / 主检验原始证据</summary><pre class="json-block">{{ pretty(result?.bootstrap) }}</pre><pre class="json-block">{{ pretty(result?.primary) }}</pre></details>
                </div>
                <div v-else-if="evidenceTab === 'tracks'" class="mt-3">
                  <p class="hint mb-2">原始 / 中性化 / 增量三轨按服务器结果并列。未返回的轨道保持未验证；收益日期数不代替有效观测 n。</p>
                  <div class="table-scroll"><table><thead><tr><th>轨道 / 状态</th><th>指标 / 状态</th><th>n</th><th>均值</th><th>SE</th><th>CI</th><th>p</th></tr></thead><tbody>
                    <template v-for="track in trackRows" :key="track.key">
                      <tr><th rowspan="2">{{ track.name }}<span class="block font-normal text-[#646262]">{{ label(track.data?.status) }}</span></th><td>IC · {{ label(track.data?.ic?.status) }}</td><td>{{ fmt(track.data?.ic?.n_obs) }}</td><td>{{ fmt(track.data?.ic?.mean) }}</td><td>{{ fmt(track.data?.ic?.se) }}</td><td>{{ interval(track.data?.ic) }}</td><td>{{ fmt(track.data?.ic?.p_value) }}</td></tr>
                      <tr><td>净收益 · {{ label(track.data?.net?.status) }}</td><td>{{ fmt(track.data?.net?.n_obs) }}</td><td>{{ fmt(track.data?.net?.mean) }}</td><td>{{ fmt(track.data?.net?.se) }}</td><td>{{ interval(track.data?.net) }}</td><td>{{ fmt(track.data?.net?.p_value) }}</td></tr>
                    </template>
                  </tbody></table></div>
                  <details v-for="track in trackRows" :key="track.key" class="fold mt-3"><summary>[+] {{ track.name }} · 原始证据 / 收益序列</summary><pre class="json-block">{{ pretty(track.data) }}</pre></details>
                </div>
                <div v-else-if="evidenceTab === 'regime'" class="mt-3 space-y-3">
                  <h3 class="text-xs font-bold">状态条件矩阵 · {{ label(result?.regime?.status) }}</h3>
                  <div v-if="result?.regime?.conditional?.length" class="table-scroll"><table><thead><tr><th>市场状态</th><th>有效观测 n</th><th>均值</th><th>收缩后均值</th><th>检验资格</th></tr></thead><tbody><tr v-for="(condition, index) in result.regime.conditional" :key="index"><td>{{ condition.state || '未验证' }}</td><td>{{ fmt(condition.n_obs) }}</td><td>{{ fmt(condition.mean) }}</td><td>{{ fmt(condition.shrunk_mean) }}</td><td>{{ condition.eligible === true ? '具备资格（不等于支持）' : condition.eligible === false ? '不具备资格' : '未验证' }}</td></tr></tbody></table></div>
                  <p v-else class="hint">状态条件结果未验证，未返回可展示的矩阵。</p>
                  <details class="fold"><summary>[+] 状态模型比较</summary><pre class="json-block">{{ pretty(result?.regime?.comparison) }}</pre></details>
                  <h3 class="text-xs font-bold">监控证据</h3><pre class="json-block">{{ pretty(result?.monitor) }}</pre>
                  <p class="hint">状态条件分析与监控不自动变更生命周期；异常须人工复核。</p>
                </div>
                <div v-else class="mt-3 space-y-3"><h3 class="text-xs font-bold">数据 / 计算清单 Manifest</h3><pre class="json-block">{{ pretty(result?.manifest) }}</pre><details class="fold"><summary>[+] 完整运行 JSON（包含未识别的服务端字段）</summary><pre class="json-block">{{ pretty(selectedRun) }}</pre></details></div>
                <div class="limitations mt-4"><h3 class="text-xs font-bold">限制与未验证项</h3><ul v-if="result?.limitations?.length" class="source-list"><li v-for="(limitation, index) in result.limitations" :key="index">[!] {{ limitation }}</li></ul><p v-else class="hint mt-2">未返回限制说明，不代表不存在限制；缺失证据仍为未验证。</p></div>
              </template>
            </template>
          </Card>

          <Card title="[4] 人工生命周期复核">
            <p class="hint mb-3">当前状态：{{ label(study.state) }}。状态变更必须说明理由，由后端检查证据与转移规则；不因单次显著结果自动启用。</p>
            <form v-if="reviewDraft" class="space-y-3" novalidate @submit.prevent="submitReview">
              <div class="form-grid"><div class="field"><span id="research-review-label">目标状态</span><Select v-model="reviewDraft.state" :options="reviewOptions" :disabled="!!pending" aria-labelledby="research-review-label" /></div><label class="field">复核理由（必填）<textarea v-model="reviewDraft.note" :disabled="!!pending" rows="3" placeholder="引用运行证据，说明启用、观察、休眠或退役的依据及限制" /></label></div>
              <div class="flex flex-wrap items-center gap-3"><Button type="submit" :loading="pending?.kind === 'review'" :disabled="!!reviewReason" :title="reviewReason">保存人工复核</Button><p class="hint">{{ reviewReason || '将记录目标状态与复核理由，不修改冻结协议。' }}</p></div>
            </form>
            <details class="fold mt-3"><summary>[+] 历史复核记录（{{ study.reviews?.length ?? 0 }}）</summary><p v-if="!study.reviews?.length" class="hint mt-3">尚无人工复核记录。</p><pre v-for="(review, index) in study.reviews ?? []" :key="index" class="json-block">{{ pretty(review) }}</pre></details>
          </Card>
        </template>
        <Card v-else-if="!detailLoading && !detailError" title="等待选择研究"><p class="hint">从左侧选择已有研究，或新建假设与冻结协议。实际 QMT 数据与实证结果尚未验证。</p></Card>
      </div>
    </div>

    <details class="fold guidance" @toggle="openGuidance">
      <summary>[+] 研究原则 / 路线图 / 审计清单</summary>
      <p v-if="guidanceLoading" role="status" class="hint mt-3">正在读取研究指引…</p>
      <div v-if="guidanceError" class="mt-3"><p class="error-box" role="alert">{{ guidanceError }}</p><Button class="mt-2" size="sm" :disabled="guidanceLoading" @click="loadGuidance">重试指引</Button></div>
      <template v-if="guidance">
        <h3 class="mt-4 text-xs font-bold">研究原则</h3><ul class="source-list"><li v-for="(principle, index) in guidance.principles ?? []" :key="index">[+] {{ principle }}</li></ul>
        <h3 class="mt-4 text-xs font-bold">路线图（规划不是验收结果）</h3><div v-if="guidance.roadmap?.length" class="table-scroll mt-2"><table><thead><tr><th>阶段</th><th>目标</th><th>验收条件</th><th>不做什么</th></tr></thead><tbody><tr v-for="(step, index) in guidance.roadmap" :key="index"><td>{{ step.period }}</td><td>{{ pretty(step.objective) }}</td><td>{{ pretty(step.acceptance) }}</td><td>{{ pretty(step.do_not) }}</td></tr></tbody></table></div><p v-else class="hint">未返回路线图。</p>
        <h3 class="mt-4 text-xs font-bold">审计清单（未自动勾选）</h3><ul class="source-list"><li v-for="(item, index) in guidance.audit_checklist ?? []" :key="index">[ ] {{ item }}</li></ul>
      </template>
    </details>

    <Dialog :open="!!holdoutTrial" title="不可逆选定候选并开启留出检验" @close="holdoutTrial = null">
      <div class="max-w-xl space-y-3">
        <p>确认后将永久选定此候选，禁止新增候选或更换留出候选。即使 QMT 数据不足或运行失败，也不能将留出集重新用于选优。</p>
        <pre class="formula-block">{{ holdoutTrial?.formula }}</pre>
        <p class="hint">协议与方向不变。留出检验不保证统计支持；只有留出完成后才可运行监控。</p>
        <p class="hint">{{ holdoutReason || '该候选已完成验证，满足开启条件。请确认已完成所有候选比较。' }}</p>
      </div>
      <template #footer><Button @click="holdoutTrial = null">取消</Button><Button variant="primary" :disabled="!!holdoutReason" :title="holdoutReason" @click="confirmHoldout">确认不可逆选定并运行</Button></template>
    </Dialog>
  </section>
</template>

<style scoped>
.research-workbench :deep(input), .research-workbench textarea { min-width: 0; }
.workbench-grid { display: grid; grid-template-columns: minmax(210px, 260px) minmax(0, 1fr); gap: 16px; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.four-columns { grid-template-columns: repeat(4, minmax(0, 1fr)); }
.full-width { grid-column: 1 / -1; }
.field { display: flex; flex-direction: column; min-width: 0; gap: 6px; font-size: 12px; color: #646262; }
.field textarea { width: 100%; resize: vertical; border: 1px solid rgba(15, 0, 0, 0.12); border-radius: 4px; background: #f8f7f7; color: #201d1d; padding: 8px 12px; font: inherit; font-size: 13px; line-height: 1.6; }
.field textarea:focus { outline: none; border-color: #201d1d; background: #fdfcfc; }
.field textarea:disabled { opacity: .5; cursor: not-allowed; }
.hint { font-size: 12px; line-height: 1.7; color: #646262; overflow-wrap: anywhere; }
.notice-box, .error-box { padding: 10px 12px; border: 1px solid rgba(15, 0, 0, 0.12); border-radius: 4px; font-size: 12px; line-height: 1.7; overflow-wrap: anywhere; }
.error-box { color: #d70015; border-color: #d70015; }
.study-button { display: block; width: 100%; text-align: left; white-space: normal; border-color: rgba(15, 0, 0, 0.12); }
.study-selected { border-color: #646262; background: #f1eeee; }
.fold { border-top: 1px solid rgba(15, 0, 0, 0.12); padding-top: 12px; }
.fold summary { cursor: pointer; color: #646262; font-size: 12px; line-height: 1.7; list-style: none; }
.fold summary::-webkit-details-marker { display: none; }
.fold summary:focus-visible { outline: 1px solid #646262; outline-offset: 4px; }
.source-list { margin-top: 8px; display: grid; gap: 6px; font-size: 12px; line-height: 1.7; white-space: pre-wrap; overflow-wrap: anywhere; }
.json-block, .formula-block { white-space: pre-wrap; overflow-wrap: anywhere; font-family: inherit; font-size: 12px; line-height: 1.7; padding: 12px; border: 1px solid rgba(15, 0, 0, 0.12); margin: 12px 0; }
.json-block { max-height: 360px; overflow: auto; }
.trial-row { margin-top: 16px; padding-top: 16px; border-top: 1px solid rgba(15, 0, 0, 0.12); }
.phase-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.metric-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); }
.metric { border-bottom: 1px solid rgba(15, 0, 0, 0.12); padding: 12px 8px; overflow-wrap: anywhere; }
.table-scroll { max-width: 100%; overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 12px; line-height: 1.7; }
th, td { text-align: left; vertical-align: top; padding: 8px; border-bottom: 1px solid rgba(15, 0, 0, 0.12); }
th { font-weight: 500; }
.limitations { border-top: 1px solid rgba(15, 0, 0, 0.12); padding-top: 12px; }
.guidance { padding: 12px; border: 1px solid rgba(15, 0, 0, 0.12); }
@media (max-width: 1100px) { .four-columns, .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 850px) { .workbench-grid { grid-template-columns: minmax(0, 1fr); } }
@media (max-width: 640px) { .form-grid, .phase-grid, .metric-grid { grid-template-columns: minmax(0, 1fr); } }
</style>
