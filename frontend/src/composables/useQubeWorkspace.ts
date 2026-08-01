/**
 * useQubeWorkspace — QUBE 工作区状态（对齐参考站 zustand persist 结构）
 *
 * localStorage `lq-qube-workspace` 持久化：
 * - canvasWidthPx / canvasCollapsed：右侧画板宽度（360–1600，折叠=完全隐藏）
 * - perSession：每会话的画板焦点（工件/Tab/选中的历史分析与回测/参数草稿）
 */
import { reactive, watch } from 'vue'

export interface ArtifactRef {
  kind: 'factor' | 'strategy'
  id: string
}

export interface SessionWorkspace {
  active: ArtifactRef | null
  canvasTab: string // 策略: code|backtest|logs|versions；因子: code|analysis
  selectedBacktestRunId: string
  selectedAnalysisId: string
  backtestParams: {
    period_start: string
    period_end: string
    init_balance: number
    commission_rate: number
    slippage: number
  }
  analysisParams: {
    period_start: string
    period_end: string
    adjustment_cycle: number
    group_number: number
    factor_direction: number
  }
}

interface QubeWorkspace {
  canvasWidthPx: number
  canvasCollapsed: boolean
  sidebarWidthPx: number
  sidebarCollapsed: boolean
  perSession: Record<string, SessionWorkspace>
}

const STORAGE_KEY = 'lq-qube-workspace'
export const CANVAS_MIN = 360
export const CANVAS_MAX = 1600
export const CHAT_MIN = 420
export const CANVAS_EXPAND = 900 // 双击拖拽条展开目标宽
export const SIDEBAR_MIN = 180
export const SIDEBAR_MAX = 400

function defaultSession(): SessionWorkspace {
  return {
    active: null,
    canvasTab: 'code',
    selectedBacktestRunId: '',
    selectedAnalysisId: '',
    backtestParams: {
      period_start: '',
      period_end: '',
      init_balance: 1000000,
      commission_rate: 0.001,
      slippage: 0.001,
    },
    analysisParams: {
      period_start: '',
      period_end: '',
      adjustment_cycle: 5,
      group_number: 5,
      factor_direction: 1,
    },
  }
}

function load(): QubeWorkspace {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      return {
        canvasWidthPx: Number(parsed.canvasWidthPx) || 492,
        canvasCollapsed: !!parsed.canvasCollapsed,
        sidebarWidthPx: Number(parsed.sidebarWidthPx) || 240,
        sidebarCollapsed: !!parsed.sidebarCollapsed,
        perSession: parsed.perSession || {},
      }
    }
  } catch {
    /* 损坏则回默认 */
  }
  return {
    canvasWidthPx: 492,
    canvasCollapsed: false,
    sidebarWidthPx: 240,
    sidebarCollapsed: false,
    perSession: {},
  }
}

const state = reactive<QubeWorkspace>(load())

watch(
  state,
  () => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
    } catch {
      /* 忽略配额错误 */
    }
  },
  { deep: true },
)

/** 画板宽度 clamp：[360, min(1600, 容器宽-聊天区最小 420)] */
export function clampCanvasWidth(width: number, containerWidth: number): number {
  const max = Math.max(CANVAS_MIN, Math.min(CANVAS_MAX, containerWidth - CHAT_MIN))
  return Math.max(CANVAS_MIN, Math.min(max, width))
}

export function useQubeWorkspace() {
  function session(id: string): SessionWorkspace {
    if (!state.perSession[id]) state.perSession[id] = defaultSession()
    return state.perSession[id]
  }
  return { state, session }
}
