import { type MaybeRefOrGetter, computed, toValue } from 'vue'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'

/* ── 类型定义 ── */
export interface PresetFactor {
  id: number
  factor_code: string
  factor_name: string
  category_id: number | null
  category_code: string | null
  category_name: string | null
  category_color_hex: string | null
  description: string | null
  ic_mean: number | null
  rank_ic: number | null
  ic_ir: number | null
  ic_std: number | null
  annualized_return: number | null
  maximum_drawdown: number | null
  sharpe_ratio: number | null
  turnover_rate: number | null
  start_date: string | null
  data_date: string | null
  stock_pool: string | null
  is_preset: boolean
}

export interface PresetFactorCategory {
  id: number
  category_code: string
  category_name: string
  color_hex: string | null
  factor_count: number
}

/** 因子详情（额外包含公式的三种形式） */
export interface PresetFactorDetail extends PresetFactor {
  formula: string
  formula_latex: string
  formula_code: string
  /** 因子类型：formula（公式型）/ data_field（数据字段型）/ indicator（参数化指标） */
  factor_type?: 'formula' | 'data_field' | 'indicator'
  recalc_mode?: string
  recalc_message?: string
}

/** IC 指标历史快照（重算覆盖前自动留存） */
export interface FactorICSnapshot {
  id: number
  factor_id: number
  ic_mean: number | null
  rank_ic: number | null
  ic_ir: number | null
  ic_std: number | null
  annualized_return: number | null
  maximum_drawdown: number | null
  sharpe_ratio: number | null
  turnover_rate: number | null
  data_date: string | null
  snapshot_at: number
}

export interface PresetFactorResponse {
  items: PresetFactor[]
  total: number
  page: number
  page_size: number
}

export interface PresetFactorParams {
  page?: number
  page_size?: number
  category_code?: string
  sort_field?: string
  sort_order?: 'asc' | 'desc'
  search?: string
}

/* ── API 请求函数 ── */
async function fetchPresetFactors(params: PresetFactorParams): Promise<PresetFactorResponse> {
  const searchParams = new URLSearchParams()
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) searchParams.set('page_size', String(params.page_size))
  if (params.category_code) searchParams.set('category_code', params.category_code)
  if (params.sort_field) searchParams.set('sort_field', params.sort_field)
  if (params.sort_order) searchParams.set('sort_order', params.sort_order)
  if (params.search) searchParams.set('search', params.search)

  const res = await fetch(`/api/factor/preset?${searchParams.toString()}`)
  if (!res.ok) throw new Error(`Failed to fetch preset factors: ${res.status}`)
  return res.json()
}

async function fetchPresetFactorCategories(): Promise<PresetFactorCategory[]> {
  const res = await fetch('/api/factor/preset/categories')
  if (!res.ok) throw new Error(`Failed to fetch categories: ${res.status}`)
  return res.json()
}

async function addToFactorPool(factorId: number): Promise<void> {
  const res = await fetch(`/api/factor/preset/${factorId}/add-to-pool`, { method: 'POST' })
  if (!res.ok) throw new Error(`Failed to add to pool: ${res.status}`)
}

async function fetchFactorPool(): Promise<PresetFactor[]> {
  const res = await fetch('/api/factor/preset/pool')
  if (!res.ok) throw new Error(`Failed to fetch factor pool: ${res.status}`)
  return res.json()
}

async function removeFromPool(factorId: number): Promise<void> {
  const res = await fetch(`/api/factor/preset/pool/${factorId}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`Failed to remove from pool: ${res.status}`)
}

async function recalculateFactor(factorId: number): Promise<PresetFactorDetail> {
  const res = await fetch(`/api/factor/preset/${factorId}/recalculate`, { method: 'POST' })
  if (!res.ok) throw new Error(`Failed to recalculate: ${res.status}`)
  return res.json()
}

async function fetchFactorDetail(factorId: number): Promise<PresetFactorDetail> {
  const res = await fetch(`/api/factor/preset/${factorId}`)
  if (!res.ok) throw new Error(`Failed to fetch factor detail: ${res.status}`)
  return res.json()
}

async function fetchFactorHistory(factorId: number): Promise<FactorICSnapshot[]> {
  const res = await fetch(`/api/factor/preset/${factorId}/history`)
  if (!res.ok) throw new Error(`Failed to fetch factor history: ${res.status}`)
  return res.json()
}

/* ── Composables ── */
export function usePresetFactors(params: MaybeRefOrGetter<PresetFactorParams>) {
  return useQuery({
    queryKey: ['preset-factors', computed(() => toValue(params))],
    queryFn: () => fetchPresetFactors(toValue(params)),
    placeholderData: keepPreviousData,
    staleTime: 60 * 1000,
  })
}

export function usePresetFactorCategories() {
  return useQuery({
    queryKey: ['preset-factor-categories'],
    queryFn: fetchPresetFactorCategories,
    staleTime: 5 * 60 * 1000,
  })
}

export function useAddToFactorPool() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: addToFactorPool,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['preset-factors'] })
      queryClient.invalidateQueries({ queryKey: ['factor-pool'] })
    },
  })
}

export function useFactorPool() {
  return useQuery({
    queryKey: ['factor-pool'],
    queryFn: fetchFactorPool,
    staleTime: 60 * 1000,
  })
}

export function useRemoveFromPool() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: removeFromPool,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['factor-pool'] })
    },
  })
}

export function useRecalculateFactor() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: recalculateFactor,
    onSuccess: (_data, factorId) => {
      queryClient.invalidateQueries({ queryKey: ['factor-pool'] })
      queryClient.invalidateQueries({ queryKey: ['preset-factors'] })
      queryClient.invalidateQueries({ queryKey: ['preset-factor-detail', factorId] })
      queryClient.invalidateQueries({ queryKey: ['preset-factor-history', factorId] })
    },
  })
}

export function usePresetFactorDetail(factorId: MaybeRefOrGetter<number | null>) {
  return useQuery({
    queryKey: ['preset-factor-detail', computed(() => toValue(factorId))],
    queryFn: () => fetchFactorDetail(toValue(factorId) as number),
    enabled: computed(() => toValue(factorId) != null),
    staleTime: 60 * 1000,
  })
}

export function useFactorHistory(factorId: MaybeRefOrGetter<number | null>) {
  return useQuery({
    queryKey: ['preset-factor-history', computed(() => toValue(factorId))],
    queryFn: () => fetchFactorHistory(toValue(factorId) as number),
    enabled: computed(() => toValue(factorId) != null),
    staleTime: 30 * 1000,
  })
}
