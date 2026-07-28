import { useState, useMemo, useCallback, useRef } from 'react';
import { useReactFlow } from '@xyflow/react';
import { usePlugins, type PluginNodeSchema } from '../../hooks/usePlugins';
import { useFlowStore } from '../../store/flowStore';

// box_color 名称 → 实际色值
const COLOR_MAP: Record<string, string> = {
  orange: '#007aff',
  green: '#30d158',
  yellow: '#ff9f0a',
  '#ffd60a': '#ffd60a',
  cyan: '#64d2ff',
  red: '#ff3b30',
  black: '#9a9898',
};

function resolveColor(c: string) {
  return COLOR_MAP[c] || c || '#007aff';
}

/** 从 input_schema 提取默认 widgets */
function buildWidgets(schema: PluginNodeSchema) {
  if (!schema.input_schema?.properties) return [];
  return Object.entries(schema.input_schema.properties).map(([key, prop]) => ({
    name: key,
    type: prop.ui?.input_type || 'text_field',
    value: prop.default ?? '',
    options: prop.ui?.options ?? prop.enum,
  }));
}

/** 从 schema 提取 inputs / outputs */
function buildPorts(schema: PluginNodeSchema, direction: 'input' | 'output') {
  const s = direction === 'input' ? schema.input_schema : schema.output_schema;
  if (!s?.properties) return [];
  return Object.entries(s.properties).map(([name, prop]) => ({
    name,
    label: prop.title || name,
    type: prop.type || 'string',
  }));
}

let nodeCounter = 0;

export function NodePalette() {
  const { data: groups, isLoading } = usePlugins();
  const addNode = useFlowStore((s) => s.addNode);
  const { screenToFlowPosition } = useReactFlow();
  const [search, setSearch] = useState('');
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const paletteRef = useRef<HTMLDivElement>(null);

  // 过滤节点
  const filteredGroups = useMemo(() => {
    if (!groups) return {};
    const q = search.toLowerCase().trim();
    const result: Record<string, PluginNodeSchema[]> = {};
    for (const [group, nodes] of Object.entries(groups)) {
      const matched = q
        ? nodes.filter(
            (n) =>
              n.display_name.toLowerCase().includes(q) ||
              n.name.toLowerCase().includes(q)
          )
        : nodes;
      if (matched.length > 0) result[group] = matched;
    }
    return result;
  }, [groups, search]);

  const handleAddNode = useCallback(
    (schema: PluginNodeSchema) => {
      // 获取画布容器
      const flowEl = document.querySelector('.react-flow') as HTMLElement | null;
      if (!flowEl) return;
      const rect = flowEl.getBoundingClientRect();

      const position = screenToFlowPosition({
        x: rect.left + rect.width / 2,
        y: rect.top + rect.height / 2,
      });

      const id = `node_${Date.now()}_${nodeCounter++}`;
      addNode({
        id,
        type: 'workNode',
        position,
        data: {
          label: schema.display_name,
          box_color: schema.box_color,
          nodeType: schema.name,
          inputs: buildPorts(schema, 'input'),
          outputs: buildPorts(schema, 'output'),
          widgets: buildWidgets(schema),
        },
      });
    },
    [addNode, screenToFlowPosition]
  );

  // 拖拽开始
  const handleDragStart = useCallback(
    (e: React.DragEvent, schema: PluginNodeSchema) => {
      e.dataTransfer.setData('application/localquant-node', JSON.stringify(schema));
      e.dataTransfer.effectAllowed = 'copy';
    },
    []
  );

  const toggleGroup = useCallback((group: string) => {
    setCollapsed((prev) => ({ ...prev, [group]: !prev[group] }));
  }, []);

  return (
    <div
      ref={paletteRef}
      style={{
        width: 200,
        flexShrink: 0,
        background: '#262222',
        borderRight: '1px solid #403b3b',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      {/* 搜索框 */}
      <div style={{ padding: '8px 8px 4px' }}>
        <input
          type="text"
          placeholder="搜索节点..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{
            width: '100%',
            background: '#201d1d',
            border: '1px solid #403b3b',
            borderRadius: 4,
            color: '#fdfcfc',
            fontSize: 12,
            padding: '5px 8px',
            outline: 'none',
            fontFamily: 'inherit',
            boxSizing: 'border-box',
          }}
        />
      </div>

      {/* 节点列表 */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '4px 0' }}>
        {isLoading && (
          <div style={{ color: '#555', fontSize: 11, textAlign: 'center', padding: 16 }}>
            加载中...
          </div>
        )}
        {Object.entries(filteredGroups).map(([group, nodes]) => (
          <div key={group}>
            {/* 分组标题 */}
            <div
              onClick={() => toggleGroup(group)}
              style={{
                display: 'flex',
                alignItems: 'center',
                padding: '6px 10px',
                cursor: 'pointer',
                color: '#9a9898',
                fontSize: 11,
                fontWeight: 600,
                userSelect: 'none',
                letterSpacing: 0.5,
              }}
            >
              <span
                style={{
                  display: 'inline-block',
                  marginRight: 4,
                  fontSize: 8,
                  transition: 'transform 0.15s',
                  transform: collapsed[group] ? 'rotate(-90deg)' : 'rotate(0deg)',
                }}
              >
                ▼
              </span>
              {group}
              <span style={{ marginLeft: 'auto', color: '#646262', fontSize: 10 }}>
                {nodes.length}
              </span>
            </div>

            {/* 节点项 */}
            {!collapsed[group] &&
              nodes.map((node) => {
                const color = resolveColor(node.box_color);
                return (
                  <div
                    key={node.name}
                    draggable
                    onDragStart={(e) => handleDragStart(e, node)}
                    onClick={() => handleAddNode(node)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      padding: '5px 10px 5px 14px',
                      cursor: 'pointer',
                      gap: 6,
                      transition: 'background 0.1s',
                    }}
                    onMouseEnter={(e) => {
                      (e.currentTarget as HTMLDivElement).style.background = '#302c2c';
                    }}
                    onMouseLeave={(e) => {
                      (e.currentTarget as HTMLDivElement).style.background = 'transparent';
                    }}
                  >
                    {/* 色条 */}
                    <div
                      style={{
                        width: 3,
                        height: 18,
                        borderRadius: 2,
                        background: color,
                        flexShrink: 0,
                      }}
                    />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div
                        style={{
                          color: '#fdfcfc',
                          fontSize: 12,
                          fontWeight: 500,
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        }}
                      >
                        {node.display_name}
                      </div>
                      {node.input_schema?.properties && (
                        <div
                          style={{
                            color: '#646262',
                            fontSize: 10,
                            whiteSpace: 'nowrap',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                          }}
                        >
                          {Object.keys(node.input_schema.properties).length} 个参数
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
          </div>
        ))}
      </div>
    </div>
  );
}
