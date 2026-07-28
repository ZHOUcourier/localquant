import { useEffect } from 'react';
import { useParams, useBlocker } from 'react-router-dom';
import { ReactFlowProvider } from '@xyflow/react';
import type { Node, Edge } from '@xyflow/react';
import { FlowEditor } from '../components/flow/FlowEditor';
import { FlowToolbar } from '../components/flow/FlowToolbar';
import { NodePalette } from '../components/flow/NodePalette';
import { NodeConfig } from '../components/flow/NodeConfig';
import { BottomPanel } from '../components/flow/BottomPanel';
import { Dialog } from '../components/ui/Dialog';
import { Button } from '../components/ui/Button';
import { useWorkflow } from '../hooks/useWorkflow';
import { usePlugins } from '../hooks/usePlugins';
import { useFlowStore } from '../store/flowStore';
import { buildSchemaMap, buildNodeData } from '../lib/nodeSchema';

function WorkflowEditorInner() {
  const { id } = useParams<{ id: string }>();
  const { data: workflow, isLoading, error } = useWorkflow(id || null);
  const { data: pluginGroups } = usePlugins();
  const { setWorkflow, isDirty, resetState } = useFlowStore();

  // 拦截导航：当有未保存更改时
  const blocker = useBlocker(isDirty);

  // 组件卸载时重置状态
  useEffect(() => {
    return () => {
      resetState();
    };
  }, [resetState]);

  useEffect(() => {
    // 等工作流与插件 schema 都就绪后再转换，保证节点端口/控件完整
    if (!workflow || !pluginGroups) return;

    const schemaMap = buildSchemaMap(pluginGroups);

    // 将后端节点格式转换为 ReactFlow 格式（data 结构与拖放创建的节点一致）
    const rfNodes: Node[] = workflow.nodes.map(n => ({
      id: n.uuid,
      position: { x: n.positionX, y: n.positionY },
      type: 'workNode',
      data: buildNodeData(
        n.name,
        n.title || n.name,
        n.static_input_data || {},
        schemaMap[n.name],
      ),
    }));

    const rfEdges: Edge[] = workflow.links.map(l => ({
      id: l.uuid,
      source: l.previous_node_uuid,
      sourceHandle: l.output_field_name,
      target: l.next_node_uuid,
      targetHandle: l.input_field_name,
      animated: false,
    }));

    // 直接写入 store（FlowEditor 从 store 渲染），并重置脏状态
    setWorkflow(workflow.id, workflow.name, rfNodes, rfEdges);
  }, [workflow, pluginGroups, setWorkflow]);

  if (isLoading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#646262', fontSize: 13 }}>
        加载中...
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#ff3b30', fontSize: 13 }}>
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
        background: '#fdfcfc',
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

      {/* useBlocker 离开确认对话框 */}
      <Dialog
        open={blocker.state === 'blocked'}
        onClose={() => blocker.reset?.()}
        title="未保存的更改"
        footer={
          <>
            <Button variant="secondary" onClick={() => blocker.reset?.()}>
              继续编辑
            </Button>
            <Button variant="danger" onClick={() => blocker.proceed?.()}>
              确定离开
            </Button>
          </>
        }
      >
        工作流有未保存的更改，确定要离开吗？
      </Dialog>
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
