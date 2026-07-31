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

/** AlphaLens 报告（后端 /api/factor/alphalens 返回，调用 alphalens-reloaded 计算） */
export interface AlphaLensReport {
  periods: string[]
  quantiles: number
  has_group: boolean
  ic_summary: {
    period: string
    ic_mean: number
    ic_std: number
    ic_ir: number
    risk_adjusted: number
    t_stat: number
    p_value: number
    positive_ratio: number
  }[]
  ic_series: Record<string, Record<string, number>>
  ic_by_group: { group: string; period: string; ic_mean: number }[]
  mean_return_by_quantile: { factor_quantile: number; period: string; mean_return: number }[]
  mean_return_by_quantile_group: {
    group: string
    factor_quantile: number
    period: string
    mean_return: number
  }[]
  cumulative_return_by_quantile: Record<string, Record<string, Record<string, number>>>
  factor_weighted_cumulative: Record<string, Record<string, number>>
  quantile_turnover: Record<string, Record<string, number>>
  rank_autocorrelation: Record<string, Record<string, number>>
}
