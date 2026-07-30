/** ui 组件库共享类型（SFC 的 script setup 不便对外导出类型，集中在此） */

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
export type ButtonSize = 'sm' | 'md' | 'lg'

export interface Column {
  key: string
  title: string
  dataIndex: string
  width?: string | number
}

export interface TabItem {
  key: string
  label: string
  disabled?: boolean
}

export type BadgeVariant = 'default' | 'success' | 'warning' | 'error' | 'info'

export interface SelectOption {
  value: string
  label: string
  disabled?: boolean
}

export type TooltipPlacement = 'top' | 'bottom' | 'left' | 'right'
