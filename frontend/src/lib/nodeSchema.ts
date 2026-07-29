import type { PluginNodeSchema, PluginGroups, SchemaProperty } from '../hooks/usePlugins';

/** 节点 widget 定义（与 WorkNode/NodeConfig 消费的结构一致） */
export interface WidgetDef {
  name: string;
  type: string;
  value?: unknown;
  options?: unknown[];
}

export interface PortDef {
  name: string;
  label: string;
  type: string;
}

/**
 * 判断输入字段是否为「真实可连线」的数据入口。
 *
 * 只有需要从上游接收数据的字段才生成输入端口：
 * - ui.input_type === 'None'：后端显式声明仅通过连线输入；
 * - 数据型字段（object / 无明确基础类型，如 DataFrame/dict）且未配置控件。
 * 普通参数（字符串/数字/下拉等）只在节点上渲染控件，不再生成无意义的端口。
 */
export function isConnectableInput(prop: SchemaProperty): boolean {
  const uiType = prop.ui?.input_type;
  if (uiType === 'None') return true;
  if (uiType && uiType !== 'None') return false; // 显式配置了控件 → 参数输入
  // 无 ui 配置：object（dict/DataFrame 回退 schema）或无类型声明视为数据口
  const t = prop.type;
  if (t === 'object') return true;
  if (t === undefined && !prop.enum) return true;
  return false;
}

/** 从 schema 构建 widgets（携带默认值；跳过仅连线输入的数据字段） */
export function buildWidgets(schema: PluginNodeSchema): WidgetDef[] {
  if (!schema.input_schema?.properties) return [];
  return Object.entries(schema.input_schema.properties)
    .filter(([, prop]) => !isConnectableInput(prop))
    .map(([key, prop]) => ({
      name: key,
      type: prop.ui?.input_type || 'text_field',
      value: prop.default ?? '',
      options: prop.ui?.options ?? prop.enum,
    }));
}

/** 从 schema 构建输入/输出端口：输入侧仅保留真实可连线的数据口，输出侧全部保留 */
export function buildPorts(schema: PluginNodeSchema, direction: 'input' | 'output'): PortDef[] {
  const s = direction === 'input' ? schema.input_schema : schema.output_schema;
  if (!s?.properties) return [];
  return Object.entries(s.properties)
    .filter(([, prop]) => direction === 'output' || isConnectableInput(prop))
    .map(([name, prop]) => ({
      name,
      label: prop.title || name,
      type: prop.type || 'string',
    }));
}

/** groups → {节点类名: schema} 映射 */
export function buildSchemaMap(groups: PluginGroups | undefined): Record<string, PluginNodeSchema> {
  const map: Record<string, PluginNodeSchema> = {};
  if (groups) {
    for (const nodes of Object.values(groups)) {
      for (const n of nodes) map[n.name] = n;
    }
  }
  return map;
}

/**
 * 由 schema + 已保存的 static_input_data 构建完整的 WorkNode data。
 * schema 缺失（如节点已被移除）时返回降级数据，保证画布仍可渲染。
 */
export function buildNodeData(
  pluginName: string,
  title: string,
  staticInputData: Record<string, unknown>,
  schema: PluginNodeSchema | undefined,
): Record<string, unknown> {
  if (!schema) {
    return {
      label: title || pluginName,
      nodeType: pluginName,
      box_color: 'black',
      inputs: [],
      outputs: [],
      widgets: Object.entries(staticInputData || {}).map(([name, value]) => ({
        name,
        type: 'text_field',
        value,
      })),
      missingSchema: true,
    };
  }
  // 默认值被已保存的 static_input_data 覆盖
  const widgets = buildWidgets(schema).map((w) =>
    staticInputData && w.name in staticInputData ? { ...w, value: staticInputData[w.name] } : w
  );
  return {
    label: title || schema.display_name,
    nodeType: schema.name,
    box_color: schema.box_color,
    inputs: buildPorts(schema, 'input'),
    outputs: buildPorts(schema, 'output'),
    widgets,
  };
}

/** 从 WorkNode data 提取 static_input_data（排除连线输入的 None 类型） */
export function extractStaticInputData(data: Record<string, unknown>): Record<string, unknown> {
  const widgets = (data.widgets as WidgetDef[]) || [];
  const result: Record<string, unknown> = {};
  for (const w of widgets) {
    if (w.type === 'None') continue;
    if (w.value !== undefined && w.value !== '') result[w.name] = w.value;
  }
  return result;
}
