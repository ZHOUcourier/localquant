import { useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { ReactFlowProvider, useReactFlow } from '@xyflow/react';
import type { Node, Edge } from '@xyflow/react';
import { FlowEditor } from '../components/flow/FlowEditor';
import { FlowToolbar } from '../components/flow/FlowToolbar';
import { NodePalette } from '../components/flow/NodePalette';
import { NodeConfig } from '../components/flow/NodeConfig';
import { BottomPanel } from '../components/flow/BottomPanel';
import { useWorkflow } from '../hooks/useWorkflow';
import { useFlowStore } from '../store/flowStore';

function WorkflowEditorInner() {
  const { id } = useParams<{ id: string }>();
  const { data: workflow, isLoading, error } = useWorkflow(id || null);
  const { setWorkflow } = useFlowStore();
  const { setNodes, setEdges } = useReactFlow();

  useEffect(() => {
    if (!workflow) return;

    // 更新 store
    setWorkflow(workflow.id, workflow.name, [], []);

    // 将后端节点格式转换为 ReactFlow 格式
    const rfNodes: Node[] = workflow.nodes.map(n => ({
      id: n.uuid,
      position: { x: n.positionX, y: n.positionY },
      data: {
        pluginName: n.name,
        title: n.title || n.name,
        static_input_data: n.static_input_data || {},
        width: n.width || 240,
        height: n.height || 180,
      },
      type: 'workNode',
      measured: { width: n.width || 240, height: n.height || 180 },
    }));

    const rfEdges: Edge[] = workflow.links.map(l => ({
      id: l.uuid,
      source: l.previous_node_uuid,
      sourceHandle: l.output_field_name,
      target: l.next_node_uuid,
      targetHandle: l.input_field_name,
      animated: false,
    }));

    setNodes(rfNodes);
    setEdges(rfEdges);
  }, [workflow, setWorkflow, setNodes, setEdges]);

  if (isLoading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#808080', fontSize: 13 }}>
        加载中...
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#e06c75', fontSize: 13 }}>
        加载工作流失败
      </div>
    );
  }

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        background: '#0a0a0a',
        overflow: 'hidden',
      }}
    >
      {/* 顶部工具栏 */}
      <FlowToolbar />

      {/* 主体区域 */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* 左侧 Node Palette */}
        <NodePalette />

        {/* 中央画布 */}
        <div style={{ flex: 1, position: 'relative' }}>
          <FlowEditor />
        </div>

        {/* 右侧 Node Config */}
        <NodeConfig />
      </div>

      {/* 底部面板 */}
      <BottomPanel />
    </div>
  );
}

export default function WorkflowEditor() {
  return (
    <ReactFlowProvider>
      <WorkflowEditorInner />
    </ReactFlowProvider>
  );
}
