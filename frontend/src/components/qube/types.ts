/**
 * QUBE 对话/画板共享类型（对齐后端 SSE 协议与 tool_calls_json 结构）
 */

export interface ToolCall {
  name: string
  display_name: string
  args: Record<string, unknown>
  result: Record<string, unknown>
  strategy_id?: string
  factor_id?: string
  backtest_run_id?: string
  factor_analysis_id?: string
}

export interface TimelineItem {
  type: 'text' | 'tool'
  content?: string
  call_index?: number
}

export interface ToolCalls {
  calls: ToolCall[]
  display_timeline: TimelineItem[]
  thinking: string
}

export interface TokenUsage {
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  reasoning_tokens?: number
  estimated?: boolean
}

export interface ChatAttachment {
  id: string
  name: string
  kind: 'text' | 'table'
  size: number
}

export interface ChatMsg {
  id?: number
  role: 'user' | 'assistant'
  content: string
  created_at?: number
  tool_calls?: ToolCalls | null
  usage?: TokenUsage | null
  attachments?: ChatAttachment[] | null
}

export interface ContextStats {
  context_window: number
  context_used: number
  context_pct: number
  completion_tokens: number
  reasoning_tokens: number
  total_tokens: number
  compacted: boolean
  compacted_at: number
  breakdown: {
    system: number
    summary: number
    conversation: number
    completion: number
    reasoning: number
  }
}

export interface StageItem {
  code: string
  label: string
  status: 'done' | 'running' | 'error' | 'pending'
}

export interface Progress {
  stage: string
  label: string
  percent: number
  current: number
  total: number
  stages: StageItem[]
}

export interface AnalysisRecord {
  id: string
  factor_id: string
  status: string
  progress: Progress
  params: Record<string, unknown>
  metrics: Record<string, number>
  error: string
  created_at: number
  finished_at: number | null
}

export interface AnalysisDetail extends AnalysisRecord {
  metrics: Record<string, never> & { summary?: Record<string, number>; ic_summary?: unknown[] }
  group_return: {
    group_perf?: Record<string, number | string>[]
    mean_return_by_group?: Record<string, number>
  }
  charts: {
    ic?: IcReport
    rank_ic?: IcReport
    group_cumulative?: Record<string, Record<string, number>>
    group_excess_cumulative?: Record<string, Record<string, number>>
    long_short_cumulative?: Record<string, number>
  }
}

export interface IcReport {
  series: Record<string, number>
  cumulative: Record<string, number>
  distribution: { centers: number[]; counts: number[]; skew: number; kurt: number }
  autocorr: { lag: number; acf: number }[]
  decay: { period: number; ic: number }[]
  mean: number
  ir: number
}

export interface BacktestRun {
  id: string
  strategy_id: string
  strategy_name: string
  status: string
  progress: Progress
  params: Record<string, unknown>
  metrics: Record<string, number>
  error: string
  created_at: number
  finished_at: number | null
}

export interface BacktestRunDetail extends BacktestRun {
  equity: { ts: string; equity: number }[]
  trades: {
    ts: string
    symbol: string
    side: string
    price: number
    qty: number
    fee: number
    reason: string
  }[]
  log: string
}

export interface QubeFactor {
  id: string
  name: string
  description: string
  code_type: 'formula' | 'python'
  code: string
}

export interface SkillParam {
  name: string
  label: string
  type: 'text' | 'number' | 'select'
  required: boolean
  default: string
  options: string[]
  placeholder: string
}

export interface Skill {
  id: number
  name: string
  display_name: string
  description: string
  category: string
  category_id: string
  params: SkillParam[]
  prompt: string
  builtin: boolean
  enabled: boolean
  source: string
  url: string
  repo_url: string
  stars: number
}

export interface SkillRepo {
  ok: boolean
  error?: string
  repo_url: string
  owner?: string
  repo?: string
  branch?: string
  subpath?: string
  readme?: string | null
  skill_md?: string | null
  meta?: {
    stars?: number | null
    forks?: number | null
    license?: string
    description?: string
    language?: string
    updated_at?: string
    html_url?: string
    default_branch?: string
  }
  fetched_at?: number
}

export interface SkillDetail {
  skill: Skill
  repo: SkillRepo
}

export async function jsonFetch(url: string, options?: RequestInit) {
  const res = await fetch(url, options)
  const body = await res.json().catch(() => null)
  if (!res.ok) throw new Error(body?.detail || `HTTP ${res.status}`)
  return body
}

/** multipart 上传（FormData 时不要手动设 Content-Type，交给浏览器带 boundary） */
export async function uploadFetch<T = Record<string, unknown>>(
  url: string,
  form: FormData,
): Promise<T> {
  const res = await fetch(url, { method: 'POST', body: form })
  const body = await res.json().catch(() => null)
  if (!res.ok) throw new Error(body?.detail || `HTTP ${res.status}`)
  return body as T
}

/** 技能 prompt 模板 {{参数}} 替换 */
export function renderSkillPrompt(tpl: string, values: Record<string, string>): string {
  return tpl.replace(/\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}/g, (m, key: string) =>
    key in values && values[key] !== '' ? values[key] : m,
  )
}

export function fmtBytes(size?: number | null): string {
  if (typeof size !== 'number' || !Number.isFinite(size) || size < 0) return '-'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(0)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

export function fmtPct(v?: number | null): string {
  return typeof v === 'number' && Number.isFinite(v) ? `${(v * 100).toFixed(2)}%` : '-'
}

export function fmtNum(v?: number | null, digits = 4): string {
  return typeof v === 'number' && Number.isFinite(v) ? v.toFixed(digits) : '-'
}

export function fmtTime(ts?: number | null): string {
  return ts ? new Date(ts * 1000).toLocaleString() : '-'
}
