/**
 * 节点分类颜色 — 全局唯一来源
 *
 * 画布节点（WorkNode）、侧边栏（NodePalette）、配置面板（NodeConfig）、
 * 小地图（MiniMap）必须统一从这里取色，禁止各自维护颜色映射。
 *
 * 后端 box_color 可能是命名色（orange/green...）或原始 hex（#FF9800...），
 * 这里统一归一到 OpenCode 主题色板。
 */
export const NODE_COLOR_MAP: Record<string, string> = {
  // 命名色
  orange: '#007aff',   // 01-数据获取
  blue: '#64d2ff',     // 02-数据处理
  green: '#30d158',
  yellow: '#ff9f0a',
  cyan: '#64d2ff',
  red: '#ff3b30',      // 08-回测
  purple: '#af52de',   // 09-输出
  black: '#9a9898',
  // 后端原始 hex → 主题色
  '#4CAF50': '#30d158', // 05-因子构建
  '#FF9800': '#ff9f0a', // 06-因子分析
  '#9C27B0': '#af52de', // 03-特征工程
  '#2196F3': '#0a84ff', // 04-技术指标
  '#E91E63': '#ff375f', // 07-机器学习
  '#607D8B': '#8e8e93', // 10-基础工具
  '#795548': '#a2845e', // 11-信息推送
  '#ffd60a': '#ffd60a',
};

/** box_color → 主题色值（未知命名色回退蓝色，未知 hex 原样透传） */
export function resolveNodeColor(c?: string): string {
  if (!c) return '#007aff';
  if (NODE_COLOR_MAP[c]) return NODE_COLOR_MAP[c];
  return c.startsWith('#') ? c : '#007aff';
}
