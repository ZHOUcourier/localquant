/**
 * OpenCode 设计系统主题
 * 暖黑背景 (#201d1d) + 暖白文字 (#fdfcfc) + Apple HIG 语义色，
 * Berkeley Mono 单一字体，扁平无阴影，4px 圆角。
 */
export const colors = {
  bg: {
    primary: '#201d1d',
    panel: '#262222',
    element: '#302c2c',
    hover: '#363131',
  },
  text: {
    primary: '#fdfcfc',
    muted: '#9a9898',
    disabled: '#6e6e73',
  },
  accent: '#007aff',
  accentHover: '#0056b3',
  accentActive: '#004085',
  success: '#30d158',
  warning: '#ff9f0a',
  error: '#ff3b30',
  info: '#64d2ff',
  border: '#403b3b',
  borderOutline: '#646262',
  borderFocus: '#007aff',
  // 节点类别色（Apple HIG 派生）
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
  sm: '2px',
  md: '4px',
  lg: '6px',
} as const;
