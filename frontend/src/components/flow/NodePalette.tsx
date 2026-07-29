import { useState, useMemo, useCallback, useRef } from 'react';
import { useReactFlow } from '@xyflow/react';
import { useQueryClient } from '@tanstack/react-query';
import { Settings2, Trash2, Undo2 } from 'lucide-react';
import { usePlugins, type PluginNodeSchema } from '../../hooks/usePlugins';
import { useFlowStore } from '../../store/flowStore';
import { buildWidgets, buildPorts, isConnectableInput } from '../../lib/nodeSchema';
import { resolveNodeColor } from '../../lib/nodeColors';
import { Dialog } from '../ui/Dialog';
import { Button } from '../ui/Button';
import { CodeEditor } from '../ui/CodeEditor';

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

/** 回收站条目 */
interface TrashEntry {
  type: 'group' | 'node' | 'custom_node';
  key: string;
  label: string;
  group?: string;
  deleted_at: number;
}

/** 管理模式下的选择项 */
interface SelectedItem {
  type: 'group' | 'node' | 'custom_node';
  key: string;
  label: string;
}

/** 富悬停说明面板（对齐官网：介绍 / 工作流示例 / 输入输出 / 注意事项） */
function NodeTooltip({ node, pos }: { node: PluginNodeSchema; pos: { x: number; y: number } }) {
  const inputPorts = node.input_schema?.properties
    ? Object.entries(node.input_schema.properties)
        .filter(([, p]) => isConnectableInput(p))
        .map(([name, p]) => p.title || name)
    : [];
  const outputPorts = node.output_schema?.properties
    ? Object.entries(node.output_schema.properties).map(([name, p]) => p.title || name)
    : [];
  const top = Math.min(pos.y, Math.max(window.innerHeight - 380, 8));

  const sectionTitle: React.CSSProperties = {
    fontSize: 11,
    fontWeight: 700,
    color: '#64d2ff',
    margin: '10px 0 4px',
    borderBottom: '1px dashed rgba(253,252,252,0.25)',
    paddingBottom: 3,
  };
  const chip: React.CSSProperties = {
    display: 'inline-block',
    background: 'rgba(253,252,252,0.12)',
    borderRadius: 3,
    padding: '1px 6px',
    margin: '2px 4px 2px 0',
    fontSize: 10.5,
  };

  return (
    <div
      style={{
        position: 'fixed',
        left: pos.x,
        top,
        width: 264,
        maxHeight: 400,
        overflowY: 'auto',
        background: '#201d1d',
        color: '#fdfcfc',
        fontSize: 11,
        fontFamily: 'inherit',
        padding: '10px 12px',
        borderRadius: 4,
        lineHeight: 1.55,
        pointerEvents: 'none',
        zIndex: 9999,
        boxShadow: '0 6px 24px rgba(15,0,0,0.25)',
      }}
    >
      <div style={{ fontWeight: 700, fontSize: 12, marginBottom: 2 }}>
        {node.display_name}
        <span style={{ fontWeight: 400, color: '#9a9898', marginLeft: 6, fontSize: 10 }}>
          {node.group}
        </span>
      </div>
      <div style={{ color: 'rgba(253,252,252,0.85)' }}>
        {node.description || '暂无描述'}
      </div>

      {node.example && (
        <>
          <div style={sectionTitle}>工作流示例</div>
          <div style={{ color: 'rgba(253,252,252,0.85)' }}>{node.example}</div>
        </>
      )}

      <div style={sectionTitle}>输入端口（连线）</div>
      <div>
        {inputPorts.length > 0
          ? inputPorts.map((p) => <span key={p} style={chip}>{p}</span>)
          : <span style={{ color: '#9a9898' }}>无（源节点，参数在节点上配置）</span>}
      </div>

      <div style={sectionTitle}>输出端口（可连接属性）</div>
      <div>
        {outputPorts.length > 0
          ? outputPorts.map((p) => <span key={p} style={chip}>{p}</span>)
          : <span style={{ color: '#9a9898' }}>无输出</span>}
      </div>

      {node.notes && node.notes.length > 0 && (
        <>
          <div style={{ ...sectionTitle, color: '#ff9f0a' }}>注意事项</div>
          <ul style={{ margin: 0, paddingLeft: 14, color: 'rgba(253,252,252,0.85)' }}>
            {node.notes.map((n, i) => (
              <li key={i} style={{ marginBottom: 2 }}>{n}</li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

export function NodePalette() {
  const { data: groups, isLoading } = usePlugins();
  const queryClient = useQueryClient();
  const addNode = useFlowStore((s) => s.addNode);
  const locked = useFlowStore((s) => s.locked);
  const { screenToFlowPosition } = useReactFlow();
  const [search, setSearch] = useState('');
  // 默认全部收起：只有显式设为 true 的分组才展开
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const paletteRef = useRef<HTMLDivElement>(null);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  // 自定义节点创建弹窗
  const [showCreator, setShowCreator] = useState(false);
  const [creatorSource, setCreatorSource] = useState(CUSTOM_NODE_TEMPLATE);
  const [creatorSaving, setCreatorSaving] = useState(false);
  const [creatorError, setCreatorError] = useState<string | null>(null);
  // 管理模式（批量删除节点/类目 → 回收站）
  const [manageMode, setManageMode] = useState(false);
  const [selected, setSelected] = useState<Record<string, SelectedItem>>({});
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  // 回收站
  const [showTrash, setShowTrash] = useState(false);
  const [trashItems, setTrashItems] = useState<TrashEntry[]>([]);
  const [trashLoading, setTrashLoading] = useState(false);
  const [restoringKey, setRestoringKey] = useState<string | null>(null);

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
        if (q) newExpanded[group] = true;
      }
    }

    const visible = q ? newExpanded : Object.fromEntries(
      Object.entries(expanded).filter(([k]) => k in result)
    );

    return { filteredGroups: result, visibleExpanded: visible };
  }, [groups, search, expanded]);

  const handleAddNode = useCallback(
    (schema: PluginNodeSchema) => {
      if (locked) return;
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
    [addNode, screenToFlowPosition, locked]
  );

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

  // ── 管理模式：批量选择与删除 ──
  const toggleSelect = useCallback((item: SelectedItem) => {
    setSelected((prev) => {
      const next = { ...prev };
      const k = `${item.type}:${item.key}`;
      if (next[k]) delete next[k];
      else next[k] = item;
      return next;
    });
  }, []);

  const selectedCount = Object.keys(selected).length;

  const handleBatchDelete = useCallback(async () => {
    setDeleting(true);
    try {
      await fetch('/api/plugins/palette/hide', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items: Object.values(selected) }),
      });
      await queryClient.invalidateQueries({ queryKey: ['plugins'] });
      setSelected({});
      setManageMode(false);
    } finally {
      setDeleting(false);
      setConfirmDelete(false);
    }
  }, [selected, queryClient]);

  // ── 回收站 ──
  const loadTrash = useCallback(async () => {
    setTrashLoading(true);
    try {
      const res = await fetch('/api/plugins/palette/trash');
      const data = await res.json();
      setTrashItems(data.items || []);
    } finally {
      setTrashLoading(false);
    }
  }, []);

  const openTrash = useCallback(() => {
    setShowTrash(true);
    loadTrash();
  }, [loadTrash]);

  const handleRestore = useCallback(async (entry: TrashEntry) => {
    setRestoringKey(`${entry.type}:${entry.key}`);
    try {
      await fetch('/api/plugins/palette/restore', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items: [{ type: entry.type, key: entry.key }] }),
      });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['plugins'] }),
        loadTrash(),
      ]);
    } finally {
      setRestoringKey(null);
    }
  }, [queryClient, loadTrash]);

  const hasResults = Object.keys(filteredGroups).length > 0;

  const checkboxStyle: React.CSSProperties = {
    width: 12,
    height: 12,
    accentColor: '#007aff',
    cursor: 'pointer',
    flexShrink: 0,
  };

  return (
    <div
      ref={paletteRef}
      style={{
        width: 216,
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

      {/* 新建自定义节点 + 管理/回收站 */}
      <div style={{ padding: '0 8px 4px', display: 'flex', gap: 4 }}>
        <button
          onClick={() => setShowCreator(true)}
          style={{
            flex: 1,
            background: 'transparent',
            border: '1px dashed rgba(15,0,0,0.25)',
            borderRadius: 4,
            color: '#646262',
            fontSize: 11,
            padding: '5px 6px',
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
          ＋ 新建节点
        </button>
        <button
          onClick={() => { setManageMode((v) => !v); setSelected({}); }}
          title="管理节点/类目（批量删除到回收站）"
          style={{
            background: manageMode ? '#201d1d' : 'transparent',
            border: '1px solid rgba(15,0,0,0.25)',
            borderRadius: 4,
            color: manageMode ? '#fdfcfc' : '#646262',
            padding: '5px 7px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
          }}
        >
          <Settings2 size={12} />
        </button>
        <button
          onClick={openTrash}
          title="回收站（还原已删除的节点/类目）"
          style={{
            background: 'transparent',
            border: '1px solid rgba(15,0,0,0.25)',
            borderRadius: 4,
            color: '#646262',
            padding: '5px 7px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
          }}
        >
          <Undo2 size={12} />
        </button>
      </div>

      {/* 管理模式提示 + 批量删除栏 */}
      {manageMode && (
        <div
          style={{
            margin: '0 8px 4px',
            padding: '5px 8px',
            background: '#f8f7f7',
            border: '1px solid rgba(15,0,0,0.12)',
            borderRadius: 4,
            fontSize: 10.5,
            color: '#646262',
            lineHeight: 1.5,
          }}
        >
          勾选节点或整个类目后批量删除，删除项进入回收站可还原。
          <button
            disabled={selectedCount === 0}
            onClick={() => setConfirmDelete(true)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              width: '100%',
              justifyContent: 'center',
              marginTop: 5,
              padding: '4px 0',
              background: selectedCount > 0 ? '#ff3b30' : '#f1eeee',
              border: 'none',
              borderRadius: 4,
              color: selectedCount > 0 ? '#fff' : '#9a9898',
              fontSize: 11,
              cursor: selectedCount > 0 ? 'pointer' : 'not-allowed',
              fontFamily: 'inherit',
            }}
          >
            <Trash2 size={11} />
            删除所选（{selectedCount}）
          </button>
        </div>
      )}

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
          const groupSelected = !!selected[`group:${group}`];
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
                  gap: 6,
                }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLDivElement).style.background = '#f1eeee';
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLDivElement).style.background = 'transparent';
                }}
              >
                {manageMode && (
                  <input
                    type="checkbox"
                    checked={groupSelected}
                    onClick={(e) => e.stopPropagation()}
                    onChange={() => toggleSelect({ type: 'group', key: group, label: group })}
                    style={checkboxStyle}
                  />
                )}
                <span style={{ fontSize: 11, fontWeight: 400, color: '#646262' }}>
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
                  const color = resolveNodeColor(node.box_color);
                  const isHovered = hoveredNode === node.name;
                  const itemType = node.is_custom ? 'custom_node' : 'node';
                  const isChecked = !!selected[`${itemType}:${node.name}`];
                  return (
                    <div
                      key={node.name}
                      draggable={!manageMode}
                      onDragStart={(e) => handleDragStart(e, node)}
                      onClick={() =>
                        manageMode
                          ? toggleSelect({ type: itemType, key: node.name, label: node.display_name })
                          : handleAddNode(node)
                      }
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        padding: '5px 10px 5px 22px',
                        cursor: 'pointer',
                        gap: 6,
                        transition: 'background 0.1s',
                        position: 'relative',
                        background: isHovered || isChecked ? '#f1eeee' : 'transparent',
                      }}
                      onMouseEnter={(e) => {
                        setHoveredNode(node.name);
                        const rect = e.currentTarget.getBoundingClientRect();
                        setTooltipPos({ x: rect.right + 6, y: rect.top - 8 });
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
                      {manageMode && (
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onClick={(e) => e.stopPropagation()}
                          onChange={() => toggleSelect({ type: itemType, key: node.name, label: node.display_name })}
                          style={checkboxStyle}
                        />
                      )}
                      {/* 色条（与画布节点/详情面板同源取色） */}
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

      {/* 富悬停说明 */}
      {!manageMode && hoveredNode && (() => {
        const node = Object.values(filteredGroups)
          .flat()
          .find((n) => n.name === hoveredNode);
        if (!node) return null;
        return <NodeTooltip node={node} pos={tooltipPos} />;
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
        <CodeEditor
          value={creatorSource}
          onChange={setCreatorSource}
          language="python"
          height={420}
          title="新建自定义节点"
        />
      </Dialog>

      {/* 批量删除二次确认 */}
      <Dialog
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        title="删除到回收站"
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmDelete(false)} disabled={deleting}>
              取消
            </Button>
            <Button variant="danger" onClick={handleBatchDelete} loading={deleting}>
              确定删除（{selectedCount}）
            </Button>
          </>
        }
      >
        <div style={{ fontSize: 12, lineHeight: 1.7 }}>
          将删除以下 {selectedCount} 项到回收站（可随时还原）：
          <ul style={{ margin: '8px 0 0', paddingLeft: 18, color: '#646262', fontSize: 11 }}>
            {Object.values(selected).map((item) => (
              <li key={`${item.type}:${item.key}`}>
                {item.type === 'group' ? '【类目】' : item.type === 'custom_node' ? '【自定义节点】' : '【节点】'}
                {item.label}
              </li>
            ))}
          </ul>
          <div style={{ marginTop: 8, color: '#ff9f0a', fontSize: 11 }}>
            注意：引用被删节点的已保存工作流在还原之前无法运行。
          </div>
        </div>
      </Dialog>

      {/* 回收站弹窗 */}
      <Dialog
        open={showTrash}
        onClose={() => setShowTrash(false)}
        title="回收站"
        className="w-[480px]"
        footer={
          <Button variant="secondary" onClick={() => setShowTrash(false)}>
            关闭
          </Button>
        }
      >
        {trashLoading ? (
          <div style={{ color: '#646262', fontSize: 12, padding: 12 }}>加载中...</div>
        ) : trashItems.length === 0 ? (
          <div style={{ color: '#9a9898', fontSize: 12, padding: 12, textAlign: 'center' }}>
            回收站为空
          </div>
        ) : (
          <div style={{ maxHeight: 320, overflowY: 'auto' }}>
            {trashItems.map((entry) => (
              <div
                key={`${entry.type}:${entry.key}`}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '7px 4px',
                  borderBottom: '1px solid rgba(15,0,0,0.08)',
                  fontSize: 12,
                }}
              >
                <span
                  style={{
                    fontSize: 10,
                    color: '#646262',
                    border: '1px solid rgba(15,0,0,0.16)',
                    borderRadius: 3,
                    padding: '0 4px',
                    flexShrink: 0,
                  }}
                >
                  {entry.type === 'group' ? '类目' : entry.type === 'custom_node' ? '自定义' : '节点'}
                </span>
                <span style={{ flex: 1, color: '#201d1d', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {entry.label}
                </span>
                <span style={{ color: '#9a9898', fontSize: 10, flexShrink: 0 }}>
                  {entry.deleted_at ? new Date(entry.deleted_at * 1000).toLocaleString('zh-CN', { hour12: false }) : ''}
                </span>
                <button
                  onClick={() => handleRestore(entry)}
                  disabled={restoringKey === `${entry.type}:${entry.key}`}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 3,
                    padding: '3px 8px',
                    background: 'transparent',
                    border: '1px solid rgba(0,122,255,0.4)',
                    borderRadius: 4,
                    color: '#007aff',
                    fontSize: 11,
                    cursor: 'pointer',
                    fontFamily: 'inherit',
                    flexShrink: 0,
                  }}
                >
                  <Undo2 size={11} />
                  {restoringKey === `${entry.type}:${entry.key}` ? '还原中' : '还原'}
                </button>
              </div>
            ))}
          </div>
        )}
      </Dialog>
    </div>
  );
}
