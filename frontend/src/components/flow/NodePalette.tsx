import { useState, useMemo, useCallback, useRef } from 'react';
import { useReactFlow } from '@xyflow/react';
import { usePlugins, type PluginNodeSchema } from '../../hooks/usePlugins';
import { useFlowStore } from '../../store/flowStore';
import { buildWidgets, buildPorts } from '../../lib/nodeSchema';

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

let nodeCounter = 0;

export function NodePalette() {
  const { data: groups, isLoading } = usePlugins();
  const addNode = useFlowStore((s) => s.addNode);
  const { screenToFlowPosition } = useReactFlow();
  const [search, setSearch] = useState('');
  // 默认全部收起：只有显式设为 false 的分组才展开
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const paletteRef = useRef<HTMLDivElement>(null);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  // 过滤节点 + 搜索时自动展开匹配分组
  const { filteredGroups, visibleExpanded } = useMemo(() => {
    if (!groups) return { filteredGroups: {}, visibleExpanded: {} };
    const q = search.toLowerCase().trim();
    const result: Record<string, PluginNodeSchema[]> = {};
    const newExpanded: Record<string, boolean> = {};

    for (const [group, nodes] of Object.entries(groups)) {
      const matched = q
        ? nodes.filter(
            (n) =>
              n.display_name.toLowerCase().includes(q) ||
              n.name.toLowerCase().includes(q) ||
              (n.description && n.description.toLowerCase().includes(q))
          )
        : nodes;
      if (matched.length > 0) {
        result[group] = matched;
        // 搜索时自动展开有匹配结果的分组
        if (q) {
          newExpanded[group] = true;
        }
      }
    }

    // 非搜索时，使用用户手动展开的状态
    const visible = q ? newExpanded : Object.fromEntries(
      Object.entries(expanded).filter(([k]) => k in result)
    );

    return { filteredGroups: result, visibleExpanded: visible };
  }, [groups, search, expanded]);

  const handleAddNode = useCallback(
    (schema: PluginNodeSchema) => {
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
    setExpanded((prev) => ({ ...prev, [group]: !prev[group] }));
  }, []);

  const hasResults = Object.keys(filteredGroups).length > 0;

  return (
    <div
      ref={paletteRef}
      style={{
        width: 200,
        flexShrink: 0,
        background: '#fdfcfc',
        borderRight: '1px solid rgba(15,0,0,0.12)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        fontFamily: "'Berkeley Mono', 'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
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
            background: '#f8f7f7',
            border: '1px solid rgba(15,0,0,0.12)',
            borderRadius: 4,
            color: '#201d1d',
            fontSize: 12,
            padding: '5px 8px',
            outline: 'none',
            fontFamily: 'inherit',
            boxSizing: 'border-box',
          }}
          onFocus={(e) => {
            e.currentTarget.style.background = '#fdfcfc';
            e.currentTarget.style.borderColor = '#201d1d';
          }}
          onBlur={(e) => {
            e.currentTarget.style.background = '#f8f7f7';
            e.currentTarget.style.borderColor = 'rgba(15,0,0,0.12)';
          }}
        />
      </div>

      {/* 节点列表 */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '4px 0' }}>
        {isLoading && (
          <div style={{ color: '#646262', fontSize: 11, textAlign: 'center', padding: 16, fontFamily: 'inherit' }}>
            加载中...
          </div>
        )}

        {!isLoading && !hasResults && (
          <div style={{ color: '#9a9898', fontSize: 11, textAlign: 'center', padding: 16, fontFamily: 'inherit' }}>
            无匹配节点
          </div>
        )}

        {Object.entries(filteredGroups).map(([group, nodes]) => {
          const isExpanded = !!visibleExpanded[group];
          return (
            <div key={group}>
              {/* 分组标题 */}
              <div
                onClick={() => toggleGroup(group)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  padding: '6px 10px',
                  cursor: 'pointer',
                  color: '#201d1d',
                  fontSize: 11,
                  fontWeight: 600,
                  fontFamily: 'inherit',
                  userSelect: 'none',
                  letterSpacing: 0,
                  transition: 'background 0.1s',
                }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLDivElement).style.background = '#f1eeee';
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLDivElement).style.background = 'transparent';
                }}
              >
                <span style={{ marginRight: 6, fontSize: 11, fontWeight: 400, color: '#646262' }}>
                  {isExpanded ? '[-]' : '[+]'}
                </span>
                <span style={{ flex: 1 }}>{group}</span>
                <span style={{ color: '#9a9898', fontSize: 10, fontWeight: 400 }}>
                  ({nodes.length})
                </span>
              </div>

              {/* 节点项 */}
              {isExpanded &&
                nodes.map((node) => {
                  const color = resolveColor(node.box_color);
                  const isHovered = hoveredNode === node.name;
                  return (
                    <div
                      key={node.name}
                      draggable
                      onDragStart={(e) => handleDragStart(e, node)}
                      onClick={() => handleAddNode(node)}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        padding: '5px 10px 5px 22px',
                        cursor: 'pointer',
                        gap: 6,
                        transition: 'background 0.1s',
                        position: 'relative',
                        background: isHovered ? '#f1eeee' : 'transparent',
                      }}
                      onMouseEnter={(e) => {
                        setHoveredNode(node.name);
                        const rect = e.currentTarget.getBoundingClientRect();
                        setTooltipPos({ x: rect.right + 4, y: rect.top + rect.height / 2 });
                      }}
                      onMouseLeave={() => {
                        setHoveredNode(null);
                      }}
                    >
                      {/* hairline 竖线连接 */}
                      <div
                        style={{
                          position: 'absolute',
                          left: 14,
                          top: 0,
                          bottom: 0,
                          width: 1,
                          background: 'rgba(15,0,0,0.12)',
                        }}
                      />
                      <div
                        style={{
                          position: 'absolute',
                          left: 14,
                          top: '50%',
                          width: 6,
                          height: 1,
                          background: 'rgba(15,0,0,0.12)',
                        }}
                      />
                      {/* 色条 */}
                      <div
                        style={{
                          width: 3,
                          height: 18,
                          borderRadius: 0,
                          background: color,
                          flexShrink: 0,
                        }}
                      />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div
                          style={{
                            color: '#201d1d',
                            fontSize: 11,
                            fontWeight: 500,
                            whiteSpace: 'nowrap',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            fontFamily: 'inherit',
                          }}
                        >
                          {node.display_name}
                        </div>
                      </div>
                    </div>
                  );
                })}
            </div>
          );
        })}
      </div>

      {/* Tooltip */}
      {hoveredNode && (() => {
        const node = Object.values(filteredGroups)
          .flat()
          .find((n) => n.name === hoveredNode);
        if (!node?.description) return null;
        return (
          <div
            style={{
              position: 'fixed',
              left: tooltipPos.x,
              top: tooltipPos.y,
              transform: 'translateY(-50%)',
              background: '#201d1d',
              color: '#fdfcfc',
              fontSize: 11,
              fontFamily: 'inherit',
              padding: '4px 8px',
              borderRadius: 4,
              maxWidth: 200,
              whiteSpace: 'normal',
              lineHeight: 1.4,
              pointerEvents: 'none',
              zIndex: 9999,
            }}
          >
            {node.description}
          </div>
        );
      })()}
    </div>
  );
}
