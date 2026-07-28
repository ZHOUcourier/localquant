import { useState, useMemo, useCallback, useRef } from 'react';
import { useReactFlow } from '@xyflow/react';
import Editor from '@monaco-editor/react';
import { useQueryClient } from '@tanstack/react-query';
import { usePlugins, type PluginNodeSchema } from '../../hooks/usePlugins';
import { useFlowStore } from '../../store/flowStore';
import { buildWidgets, buildPorts } from '../../lib/nodeSchema';
import { Dialog } from '../ui/Dialog';
import { Button } from '../ui/Button';

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

const CUSTOM_NODE_TEMPLATE = `"""自定义节点模板

编写要求：
1. 用 @work_node 装饰一个继承 BaseWorkNode 的类（源码中只能有一个节点类）
2. input_model / output_model 返回 Pydantic Model，定义输入参数与输出字段
3. run() 实现节点逻辑
"""
from typing import Optional, Type

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from backend.plugins.base import BaseWorkNode
from backend.plugins.registry import work_node
from backend.plugins.ui_control import ui


@ui(
    data={"input_type": "None"},  # 仅通过连线输入
    factor={"input_type": "text_field"},
)
class MyNodeInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    factor: str = Field(default="", title="参数")


class MyNodeOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None


@work_node(
    name="我的节点",
    group="99-自定义节点",
    box_color="cyan",
    description="自定义处理节点",
)
class MyCustomNode(BaseWorkNode):
    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return MyNodeInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return MyNodeOutput

    def run(self, input: MyNodeInput) -> Optional[BaseModel]:
        df = input.data if input.data is not None else pd.DataFrame()
        # TODO: 在这里实现节点逻辑
        return MyNodeOutput(data=df)
`;

export function NodePalette() {
  const { data: groups, isLoading } = usePlugins();
  const queryClient = useQueryClient();
  const addNode = useFlowStore((s) => s.addNode);
  const { screenToFlowPosition } = useReactFlow();
  const [search, setSearch] = useState('');
  // 默认全部收起：只有显式设为 false 的分组才展开
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const paletteRef = useRef<HTMLDivElement>(null);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  // 自定义节点创建弹窗
  const [showCreator, setShowCreator] = useState(false);
  const [creatorSource, setCreatorSource] = useState(CUSTOM_NODE_TEMPLATE);
  const [creatorSaving, setCreatorSaving] = useState(false);
  const [creatorError, setCreatorError] = useState<string | null>(null);
  // 自定义节点删除确认
  const [deleteTarget, setDeleteTarget] = useState<PluginNodeSchema | null>(null);
  const [deleting, setDeleting] = useState(false);

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

  // 创建自定义节点
  const handleCreateCustom = useCallback(async () => {
    setCreatorSaving(true);
    setCreatorError(null);
    try {
      const res = await fetch('/api/plugins/custom', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: creatorSource }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(err?.detail || `HTTP ${res.status}`);
      }
      await queryClient.invalidateQueries({ queryKey: ['plugins'] });
      setShowCreator(false);
      setCreatorSource(CUSTOM_NODE_TEMPLATE);
      setExpanded((prev) => ({ ...prev, '99-自定义节点': true }));
    } catch (e) {
      setCreatorError(e instanceof Error ? e.message : String(e));
    } finally {
      setCreatorSaving(false);
    }
  }, [creatorSource, queryClient]);

  // 删除自定义节点
  const handleDeleteCustom = useCallback(async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await fetch(`/api/plugins/custom/${deleteTarget.name}`, { method: 'DELETE' });
      await queryClient.invalidateQueries({ queryKey: ['plugins'] });
    } finally {
      setDeleting(false);
      setDeleteTarget(null);
    }
  }, [deleteTarget, queryClient]);

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

      {/* 新建自定义节点 */}
      <div style={{ padding: '0 8px 4px' }}>
        <button
          onClick={() => setShowCreator(true)}
          style={{
            width: '100%',
            background: 'transparent',
            border: '1px dashed rgba(15,0,0,0.25)',
            borderRadius: 4,
            color: '#646262',
            fontSize: 11,
            padding: '5px 8px',
            cursor: 'pointer',
            fontFamily: 'inherit',
            transition: 'all 0.15s',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.color = '#201d1d';
            e.currentTarget.style.borderColor = '#201d1d';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.color = '#646262';
            e.currentTarget.style.borderColor = 'rgba(15,0,0,0.25)';
          }}
        >
          ＋ 新建自定义节点
        </button>
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
                      {/* 自定义节点可删除 */}
                      {node.is_custom && isHovered && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setDeleteTarget(node);
                          }}
                          style={{
                            background: 'none',
                            border: 'none',
                            color: '#ff3b30',
                            cursor: 'pointer',
                            fontSize: 12,
                            padding: '0 2px',
                            lineHeight: 1,
                            flexShrink: 0,
                          }}
                          title="删除自定义节点"
                        >
                          ×
                        </button>
                      )}
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

      {/* 新建自定义节点弹窗 */}
      <Dialog
        open={showCreator}
        onClose={() => !creatorSaving && setShowCreator(false)}
        title="新建自定义节点"
        className="!max-w-[760px] w-[760px]"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowCreator(false)} disabled={creatorSaving}>
              取消
            </Button>
            <Button onClick={handleCreateCustom} loading={creatorSaving}>
              创建节点
            </Button>
          </>
        }
      >
        <div style={{ fontSize: 11, color: '#646262', marginBottom: 8, lineHeight: 1.5 }}>
          编写节点代码后点击“创建节点”，节点将出现在“99-自定义节点”分组中，并持久化到 data/custom_nodes/。
        </div>
        {creatorError && (
          <div
            style={{
              color: '#ff3b30',
              fontSize: 11,
              marginBottom: 8,
              fontFamily: 'var(--font-mono, monospace)',
              whiteSpace: 'pre-wrap',
              maxHeight: 60,
              overflowY: 'auto',
            }}
          >
            {creatorError}
          </div>
        )}
        <div style={{ border: '1px solid rgba(15,0,0,0.12)', borderRadius: 4, overflow: 'hidden' }}>
          <Editor
            height="420px"
            language="python"
            theme="light"
            value={creatorSource}
            onChange={(v) => setCreatorSource(v ?? '')}
            options={{
              minimap: { enabled: false },
              fontSize: 12,
              lineNumbers: 'on',
              scrollBeyondLastLine: false,
              automaticLayout: true,
              tabSize: 4,
              wordWrap: 'on',
            }}
          />
        </div>
      </Dialog>

      {/* 删除自定义节点确认 */}
      <Dialog
        open={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        title="删除自定义节点"
        footer={
          <>
            <Button variant="secondary" onClick={() => setDeleteTarget(null)} disabled={deleting}>
              取消
            </Button>
            <Button variant="danger" onClick={handleDeleteCustom} loading={deleting}>
              确定删除
            </Button>
          </>
        }
      >
        确定删除自定义节点“{deleteTarget?.display_name}”？引用该节点的工作流将无法运行。
      </Dialog>
    </div>
  );
}
