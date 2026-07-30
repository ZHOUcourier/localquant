import { useCallback, useMemo, useRef, useState } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  BackgroundVariant,
  ConnectionMode,
  useReactFlow,
  type Node,
  type Edge,
  type NodeTypes,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Trash2, Save, Lock } from 'lucide-react';
import { WorkNode } from './WorkNode';
import { SaveAsPresetDialog } from './SaveAsPresetDialog';
import { useFlowStore } from '../../store/flowStore';
import { buildWidgets, buildPorts } from '../../lib/nodeSchema';
import { resolveNodeColor } from '../../lib/nodeColors';
import type { PluginNodeSchema } from '../../hooks/usePlugins';

const nodeTypes: NodeTypes = {
  workNode: WorkNode,
};

// 连线加粗，提升可读性（与 index.css 中的 .react-flow__edge-path 保持一致）
const defaultEdgeOptions = {
  style: { stroke: '#9a9898', strokeWidth: 2.5 },
  animated: false,
};

let nodeCounter = 1000;

interface EdgeMenuState {
  edgeId: string;
  x: number;
  y: number;
  sourceLabel: string;
  targetLabel: string;
  fieldInfo: string;
}

interface NodeMenuState {
  nodeId: string;
  nodeType: string;
  label: string;
  x: number;
  y: number;
}

interface FlowEditorProps {
  className?: string;
}

export function FlowEditor({ className }: FlowEditorProps) {
  const {
    nodes,
    edges,
    onNodesChange,
    onEdgesChange,
    onConnect,
    selectNode,
    addNode,
    locked,
    setLocked,
  } = useFlowStore();
  const nodeStatuses = useFlowStore((s) => s.nodeStatuses);

  // 执行中节点的入边高亮流动（对标 ComfyUI 执行时的连线动态）；
  // 已成功节点的入边着绿色，直观展示数据已流过的路径
  const displayEdges = useMemo(() => {
    const hasRun = Object.keys(nodeStatuses).length > 0;
    if (!hasRun) return edges;
    return edges.map((e) => {
      const targetStatus = nodeStatuses[e.target];
      if (targetStatus === 'running') {
        return {
          ...e,
          animated: true,
          style: { stroke: '#007aff', strokeWidth: 2.5 },
        };
      }
      if (targetStatus === 'success') {
        return { ...e, style: { stroke: '#30d158', strokeWidth: 2.5 } };
      }
      if (targetStatus === 'failed') {
        return { ...e, style: { stroke: '#ff3b30', strokeWidth: 2.5 } };
      }
      return e;
    });
  }, [edges, nodeStatuses]);

  const { screenToFlowPosition } = useReactFlow();
  const wrapperRef = useRef<HTMLDivElement>(null);

  // 连线点击弹窗
  const [edgeMenu, setEdgeMenu] = useState<EdgeMenuState | null>(null);
  // 节点右键菜单
  const [nodeMenu, setNodeMenu] = useState<NodeMenuState | null>(null);
  // 另存为预设弹窗
  const [presetTarget, setPresetTarget] = useState<{ nodeType: string; label: string } | null>(null);

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      selectNode(node.id);
      setEdgeMenu(null);
      setNodeMenu(null);
    },
    [selectNode]
  );

  const handlePaneClick = useCallback(() => {
    selectNode(null);
    setEdgeMenu(null);
    setNodeMenu(null);
  }, [selectNode]);

  // 右键节点 → 上下文菜单（另存为预设 / 删除节点）
  const handleNodeContextMenu = useCallback(
    (e: React.MouseEvent, node: Node) => {
      e.preventDefault();
      const rect = wrapperRef.current?.getBoundingClientRect();
      setNodeMenu({
        nodeId: node.id,
        nodeType: (node.data?.nodeType as string) || '',
        label: (node.data?.label as string) || node.id,
        x: e.clientX - (rect?.left ?? 0),
        y: e.clientY - (rect?.top ?? 0),
      });
      setEdgeMenu(null);
    },
    []
  );

  const handleDeleteNode = useCallback(() => {
    if (!nodeMenu || locked) return;
    onNodesChange([{ type: 'remove', id: nodeMenu.nodeId }]);
    setNodeMenu(null);
  }, [nodeMenu, locked, onNodesChange]);

  // 单击连线 → 选中高亮 + 弹出操作窗
  const handleEdgeClick = useCallback(
    (e: React.MouseEvent, edge: Edge) => {
      e.stopPropagation();
      const rect = wrapperRef.current?.getBoundingClientRect();
      const sourceNode = nodes.find((n) => n.id === edge.source);
      const targetNode = nodes.find((n) => n.id === edge.target);
      setEdgeMenu({
        edgeId: edge.id,
        x: e.clientX - (rect?.left ?? 0),
        y: e.clientY - (rect?.top ?? 0),
        sourceLabel: (sourceNode?.data?.label as string) || edge.source,
        targetLabel: (targetNode?.data?.label as string) || edge.target,
        fieldInfo: `${edge.sourceHandle ?? 'output'} → ${edge.targetHandle ?? 'input'}`,
      });
    },
    [nodes]
  );

  const handleDeleteEdge = useCallback(() => {
    if (!edgeMenu || locked) return;
    onEdgesChange([{ type: 'remove', id: edgeMenu.edgeId }]);
    setEdgeMenu(null);
  }, [edgeMenu, locked, onEdgesChange]);

  // 拖拽悬停
  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
  }, []);

  // 放置节点（锁定时禁止）
  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      if (locked) return;
      const raw = e.dataTransfer.getData('application/localquant-node');
      if (!raw) return;

      try {
        const schema: PluginNodeSchema = JSON.parse(raw);
        const position = screenToFlowPosition({
          x: e.clientX,
          y: e.clientY,
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
      } catch {
        // ignore invalid data
      }
    },
    [addNode, screenToFlowPosition, locked]
  );

  return (
    <div ref={wrapperRef} className={className} style={{ width: '100%', height: '100%', position: 'relative' }}>
      <ReactFlow
        nodes={nodes}
        edges={displayEdges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeClick={handleNodeClick}
        onNodeContextMenu={handleNodeContextMenu}
        onPaneClick={handlePaneClick}
        onEdgeClick={handleEdgeClick}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        nodeTypes={nodeTypes}
        defaultEdgeOptions={defaultEdgeOptions}
        colorMode="light"
        snapToGrid
        snapGrid={[16, 16]}
        connectionMode={ConnectionMode.Loose}
        fitView
        proOptions={{ hideAttribution: true }}
        style={{ background: '#fdfcfc' }}
        nodesDraggable={!locked}
        nodesConnectable={!locked}
        elementsSelectable={!locked}
        edgesFocusable={!locked}
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={20}
          size={1}
          color="rgba(15,0,0,0.12)"
        />
        <Controls
          position="bottom-left"
          onInteractiveChange={(interactive: boolean) => setLocked(!interactive)}
          style={{
            background: '#f1eeee',
            border: '1px solid rgba(15,0,0,0.12)',
            borderRadius: 4,
          }}
        />
        <MiniMap
          position="bottom-right"
          nodeColor={(n) => resolveNodeColor((n.data as { box_color?: string })?.box_color)}
          maskColor="rgba(15,0,0,0.06)"
          style={{
            background: '#f1eeee',
            border: '1px solid rgba(15,0,0,0.12)',
            borderRadius: 4,
          }}
          pannable
          zoomable
        />
      </ReactFlow>

      {/* 锁定状态提示 */}
      {locked && (
        <div
          style={{
            position: 'absolute',
            top: 12,
            left: '50%',
            transform: 'translateX(-50%)',
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            padding: '4px 12px',
            background: '#201d1d',
            color: '#fdfcfc',
            borderRadius: 4,
            fontSize: 12,
            zIndex: 10,
            fontFamily: 'var(--font-mono, monospace)',
          }}
        >
          <Lock size={12} />
          画布已锁定：禁止拖拽、连线与增删节点（点左下角锁图标解锁）
        </div>
      )}

      {/* 节点右键菜单 */}
      {nodeMenu && (
        <div
          style={{
            position: 'absolute',
            left: Math.min(nodeMenu.x + 4, (wrapperRef.current?.clientWidth ?? 400) - 200),
            top: Math.min(nodeMenu.y + 4, (wrapperRef.current?.clientHeight ?? 300) - 120),
            width: 192,
            background: '#fdfcfc',
            border: '1px solid rgba(15,0,0,0.16)',
            borderRadius: 4,
            boxShadow: '0 4px 16px rgba(15,0,0,0.12)',
            zIndex: 20,
            fontFamily: 'var(--font-mono, monospace)',
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              padding: '8px 10px',
              borderBottom: '1px solid rgba(15,0,0,0.10)',
              fontSize: 11,
              fontWeight: 600,
              color: '#201d1d',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {nodeMenu.label}
          </div>
          <button
            onClick={() => {
              setPresetTarget({ nodeType: nodeMenu.nodeType, label: nodeMenu.label });
              setNodeMenu(null);
            }}
            disabled={!nodeMenu.nodeType}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              width: '100%',
              padding: '7px 10px',
              background: 'transparent',
              border: 'none',
              color: '#201d1d',
              fontSize: 12,
              cursor: 'pointer',
              fontFamily: 'inherit',
              textAlign: 'left',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = '#f1eeee'; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
          >
            <Save size={12} />
            另存为新节点预设
          </button>
          <button
            onClick={handleDeleteNode}
            disabled={locked}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              width: '100%',
              padding: '7px 10px',
              background: 'transparent',
              border: 'none',
              borderTop: '1px solid rgba(15,0,0,0.08)',
              color: locked ? '#9a9898' : '#ff3b30',
              fontSize: 12,
              cursor: locked ? 'not-allowed' : 'pointer',
              fontFamily: 'inherit',
              textAlign: 'left',
            }}
            onMouseEnter={(e) => { if (!locked) e.currentTarget.style.background = '#f1eeee'; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
          >
            <Trash2 size={12} />
            删除节点
          </button>
        </div>
      )}

      {/* 另存为预设弹窗 */}
      <SaveAsPresetDialog
        open={!!presetTarget}
        onClose={() => setPresetTarget(null)}
        nodeType={presetTarget?.nodeType ?? null}
        nodeLabel={presetTarget?.label ?? ''}
      />

      {/* 连线操作弹窗 */}
      {edgeMenu && (
        <div
          style={{
            position: 'absolute',
            left: Math.min(edgeMenu.x + 8, (wrapperRef.current?.clientWidth ?? 400) - 240),
            top: Math.min(edgeMenu.y + 8, (wrapperRef.current?.clientHeight ?? 300) - 110),
            width: 232,
            background: '#fdfcfc',
            border: '1px solid rgba(15,0,0,0.16)',
            borderRadius: 4,
            boxShadow: '0 4px 16px rgba(15,0,0,0.12)',
            zIndex: 10,
            fontFamily: 'var(--font-mono, monospace)',
          }}
        >
          <div
            style={{
              padding: '8px 10px',
              borderBottom: '1px solid rgba(15,0,0,0.10)',
              fontSize: 11,
              color: '#201d1d',
            }}
          >
            <div style={{ fontWeight: 600, marginBottom: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {edgeMenu.sourceLabel} → {edgeMenu.targetLabel}
            </div>
            <div style={{ color: '#646262', fontSize: 10 }}>{edgeMenu.fieldInfo}</div>
          </div>
          <div style={{ display: 'flex', padding: 6, gap: 6 }}>
            <button
              onClick={handleDeleteEdge}
              style={{
                flex: 1,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 4,
                padding: '4px 8px',
                background: 'transparent',
                border: '1px solid rgba(255,59,48,0.4)',
                borderRadius: 4,
                color: '#ff3b30',
                fontSize: 11,
                cursor: 'pointer',
              }}
            >
              <Trash2 size={12} />
              删除连线
            </button>
            <button
              onClick={() => setEdgeMenu(null)}
              style={{
                padding: '4px 10px',
                background: 'transparent',
                border: '1px solid rgba(15,0,0,0.12)',
                borderRadius: 4,
                color: '#646262',
                fontSize: 11,
                cursor: 'pointer',
              }}
            >
              取消
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
