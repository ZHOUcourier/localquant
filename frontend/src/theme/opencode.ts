/**
 * OpenCode 设计系统主题 (Light)
 * 暖白背景 (#fdfcfc) + 暖黑文字 (#201d1d) + Apple HIG 语义色，
 * Berkeley Mono 单一字体，扁平无阴影，4px 圆角。
 */
export const colors = {
  bg: {
    primary: '#fdfcfc',
    panel: '#f1eeee',
    element: '#f8f7f7',
    hover: '#f1eeee',
  },
  text: {
    primary: '#201d1d',
    body: '#424245',
    muted: '#646262',
    disabled: '#9a9898',
  },
  accent: '#007aff',
  accentHover: '#0056b3',
  accentActive: '#004085',
  success: '#30d158',
  warning: '#ff9f0a',
  error: '#ff3b30',
  info: '#64d2ff',
  border: 'rgba(15, 0, 0, 0.12)',
  borderOutline: '#646262',
  borderFocus: '#201d1d',
  nodeData: '#007aff',
  nodeProcess: '#30d158',
  nodeIndicator: '#ff9f0a',
  nodeFactor: '#ffd60a',
  nodeAnalysis: '#64d2ff',
  nodeBacktest: '#ff3b30',
  nodeOutput: '#9a9898',
} as const;

export const fonts = {
  mono: "'Berkeley Mono', 'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
  sans: "'Berkeley Mono', 'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
} as const;

export const spacing = {
  xs: '4px',
  sm: '8px',
  md: '12px',
  lg: '16px',
  xl: '24px',
  '2xl': '32px',
} as const;

export const radii = {
  none: '0px',
  sm: '4px',
  full: '9999px',
} as const;
