import { useCallback, useRef, useState } from 'react';
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
import { Trash2 } from 'lucide-react';
import { WorkNode } from './WorkNode';
import { useFlowStore } from '../../store/flowStore';
import { buildWidgets, buildPorts } from '../../lib/nodeSchema';
import type { PluginNodeSchema } from '../../hooks/usePlugins';

const nodeTypes: NodeTypes = {
  workNode: WorkNode,
};

const defaultEdgeOptions = {
  style: { stroke: '#9a9898', strokeWidth: 1.5 },
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
  } = useFlowStore();

  const { screenToFlowPosition } = useReactFlow();
  const wrapperRef = useRef<HTMLDivElement>(null);

  // 连线点击弹窗
  const [edgeMenu, setEdgeMenu] = useState<EdgeMenuState | null>(null);

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      selectNode(node.id);
      setEdgeMenu(null);
    },
    [selectNode]
  );

  const handlePaneClick = useCallback(() => {
    selectNode(null);
    setEdgeMenu(null);
  }, [selectNode]);

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
    if (!edgeMenu) return;
    onEdgesChange([{ type: 'remove', id: edgeMenu.edgeId }]);
    setEdgeMenu(null);
  }, [edgeMenu, onEdgesChange]);

  // 拖拽悬停
  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
  }, []);

  // 放置节点
  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
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
    [addNode, screenToFlowPosition]
  );

  return (
    <div ref={wrapperRef} className={className} style={{ width: '100%', height: '100%', position: 'relative' }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeClick={handleNodeClick}
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
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={20}
          size={1}
          color="rgba(15,0,0,0.12)"
        />
        <Controls
          position="bottom-left"
          style={{
            background: '#f1eeee',
            border: '1px solid rgba(15,0,0,0.12)',
            borderRadius: 4,
          }}
        />
        <MiniMap
          position="bottom-right"
          nodeColor={() => '#007aff'}
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
