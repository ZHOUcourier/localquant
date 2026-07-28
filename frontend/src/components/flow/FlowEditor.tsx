import { useCallback } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  BackgroundVariant,
  ConnectionMode,
  useReactFlow,
  type Node,
  type NodeTypes,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { WorkNode } from './WorkNode';
import { useFlowStore } from '../../store/flowStore';
import type { PluginNodeSchema } from '../../hooks/usePlugins';

const nodeTypes: NodeTypes = {
  workNode: WorkNode,
};

const defaultEdgeOptions = {
  style: { stroke: '#9a9898', strokeWidth: 1.5 },
  selectedStyle: { stroke: '#007aff', strokeWidth: 2 },
  animated: false,
};

let nodeCounter = 1000;

/** 从 schema 构建 widgets / ports（与 NodePalette 相同逻辑） */
function buildWidgets(schema: PluginNodeSchema) {
  if (!schema.input_schema?.properties) return [];
  return Object.entries(schema.input_schema.properties).map(([key, prop]) => ({
    name: key,
    type: prop.ui?.input_type || 'text_field',
    value: prop.default ?? '',
    options: prop.ui?.options ?? prop.enum,
  }));
}

function buildPorts(schema: PluginNodeSchema, direction: 'input' | 'output') {
  const s = direction === 'input' ? schema.input_schema : schema.output_schema;
  if (!s?.properties) return [];
  return Object.entries(s.properties).map(([name, prop]) => ({
    name,
    label: prop.title || name,
    type: prop.type || 'string',
  }));
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

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      selectNode(node.id);
    },
    [selectNode]
  );

  const handlePaneClick = useCallback(() => {
    selectNode(null);
  }, [selectNode]);

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
    <div className={className} style={{ width: '100%', height: '100%' }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeClick={handleNodeClick}
        onPaneClick={handlePaneClick}
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
    </div>
  );
}
