import { useQuery } from '@tanstack/react-query';

/** 单个字段的 UI 元数据 */
export interface UIConfig {
  input_type: 'date_picker' | 'text_field' | 'code_editor' | 'combobox' | 'number_field' | 'stock_picker' | 'None' | string;
  placeholder?: string;
  options?: string[];
  language?: string;
  min_lines?: number;
  max_lines?: number;
}

/** input_schema 中每个字段的 JSON Schema + ui 扩展 */
export interface SchemaProperty {
  title?: string;
  type?: string;
  default?: unknown;
  ui?: UIConfig;
  enum?: string[];
}

/** 节点 schema（后端 get_schema() 返回） */
export interface PluginNodeSchema {
  name: string;
  display_name: string;
  group: string;
  type: string;
  box_color: string;
  input_schema: {
    properties: Record<string, SchemaProperty>;
    required?: string[];
  } | null;
  output_schema: {
    properties: Record<string, SchemaProperty>;
  } | null;
}

/** API 返回：按 group 分组的节点列表 */
export type PluginGroups = Record<string, PluginNodeSchema[]>;

async function fetchPlugins(): Promise<PluginGroups> {
  const res = await fetch('/api/plugins/');
  if (!res.ok) throw new Error(`Failed to fetch plugins: ${res.status}`);
  return res.json();
}

export function usePlugins() {
  return useQuery({
    queryKey: ['plugins'],
    queryFn: fetchPlugins,
    staleTime: 5 * 60 * 1000,
  });
}
