export const colors = {
  bg: {
    primary: '#0a0a0a',
    panel: '#161b22',
    element: '#21262d',
    hover: '#2d333b',
  },
  text: {
    primary: '#eeeeee',
    muted: '#808080',
    disabled: '#555555',
  },
  accent: '#fab283',
  success: '#7fd88f',
  warning: '#f5a742',
  error: '#e06c75',
  info: '#56b6c2',
  border: '#30363d',
  borderFocus: '#fab283',
  // 节点类别色
  nodeData: '#fab283',
  nodeProcess: '#7fd88f',
  nodeIndicator: '#f5a742',
  nodeFactor: '#e5c07b',
  nodeAnalysis: '#56b6c2',
  nodeBacktest: '#e06c75',
  nodeOutput: '#808080',
} as const;

export const fonts = {
  mono: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
  sans: "system-ui, -apple-system, 'Segoe UI', sans-serif",
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
  lg: '8px',
} as const;
