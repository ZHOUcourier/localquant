/** factor 组件共享类型（SFC 的 script setup 不便对外导出类型，集中在此） */

export interface FactorResult {
  dates: string[]
  stocks: string[]
  /** {date: {stock: factor_value}} */
  values: Record<string, Record<string, number>>
  /** {date: {stock: daily_return}} 用于 IC / 分层分析 */
  returnData: Record<string, Record<string, number>>
  /** 用于标识该因子（相关性分析） */
  name: string
}

/** 因子综合报告（后端 /api/factor/analysis 返回，与因子分析节点同源） */
export interface ICBlock {
  series: Record<string, number>
  cumulative: Record<string, number>
  distribution: { centers: number[]; counts: number[]; skew: number; kurt: number }
  autocorr: { lag: number; acf: number }[]
  decay: { period: number; ic: number }[]
  mean: number
  ir: number
}

export interface FactorReport {
  summary: Record<string, number>
  ic_summary: {
    period: number
    ic_mean: number
    ic_std: number
    ic_ir: number
    ic_tstat: number
    positive_ratio: number
  }[]
  group_perf: Record<string, number | string>[]
  group_cumulative: Record<string, Record<string, number>>
  group_excess_cumulative: Record<string, Record<string, number>>
  long_short_cumulative: Record<string, number>
  ic: ICBlock
  rank_ic: ICBlock
  latest: { date: string; symbol: string; factor_value: number }[]
}
