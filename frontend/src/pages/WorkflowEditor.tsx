import { useEffect, useState, useCallback, useRef } from 'react';
import { useParams, useSearchParams, useBlocker } from 'react-router-dom';
import { ReactFlowProvider } from '@xyflow/react';
import type { Node, Edge } from '@xyflow/react';
import { FlowEditor } from '../components/flow/FlowEditor';
import { FlowToolbar } from '../components/flow/FlowToolbar';
import { NodePalette } from '../components/flow/NodePalette';
import { NodeConfig } from '../components/flow/NodeConfig';
import { BottomPanel } from '../components/flow/BottomPanel';
import { Dialog } from '../components/ui/Dialog';
import { Button } from '../components/ui/Button';
import { useWorkflow, useWorkflowTemplates } from '../hooks/useWorkflow';
import { usePlugins } from '../hooks/usePlugins';
import { useFlowStore } from '../store/flowStore';
import { buildSchemaMap, buildNodeData } from '../lib/nodeSchema';
import type { WorkflowDetail } from '../hooks/useWorkflow';

function WorkflowEditorInner() {
  const { id } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  // /workflow/new：新建模式（可选 ?template=xxx），不创建 DB 记录，保存时才入库
  const isNew = id === 'new';
  const templateId = searchParams.get('template');

  const { data: workflow, isLoading, error } = useWorkflow(isNew ? null : id || null);
  const { data: templates } = useWorkflowTemplates();
  const { data: pluginGroups } = usePlugins();
  const { setWorkflow, setCurrentRunId, isDirty, resetState } = useFlowStore();

  // 网页全屏：隐藏应用其他 UI，编辑器铺满视口（非浏览器全屏）
  const [fullscreen, setFullscreen] = useState(false);
  const toggleFullscreen = useCallback(() => setFullscreen((v) => !v), []);
  useEffect(() => {
    if (!fullscreen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setFullscreen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [fullscreen]);

  // 拦截导航：当有未保存更改时
  const blocker = useBlocker(isDirty);

  // 画布初始化守卫：同一个工作流/模板只初始化一次，
  // 避免 plugins/templates 查询焦点重取时 effect 重跑、重置掉未保存的编辑
  const initializedRef = useRef<string | null>(null);

  // 组件卸载时重置状态
  useEffect(() => {
    return () => {
      resetState();
    };
  }, [resetState]);

  useEffect(() => {
    // 已有工作流：等工作流与插件 schema 都就绪后再转换，保证节点端口/控件完整
    if (isNew || !workflow || !pluginGroups) return;
    if (initializedRef.current === `wf:${workflow.id}`) return;

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
    // 恢复最近一次运行：节点输出预览与因子分析报告刷新后仍可查看
    setCurrentRunId(workflow.last_run_id || null);
    initializedRef.current = `wf:${workflow.id}`;
  }, [isNew, workflow, pluginGroups, setWorkflow, setCurrentRunId]);

  // 新建模式：从模板预填画布（workflowId 置空，保存时才创建）或空白画布
  useEffect(() => {
    if (!isNew || !pluginGroups) return;
    const initKey = `new:${templateId || ''}`;
    if (initializedRef.current === initKey) return;

    if (!templateId) {
      setWorkflow('', '未命名工作流', [], []);
      initializedRef.current = initKey;
      return;
    }
    if (!templates) return;
    const tpl = templates.find((t) => t.id === templateId);
    if (!tpl) {
      setWorkflow('', '未命名工作流', [], []);
      initializedRef.current = initKey;
      return;
    }

    const schemaMap = buildSchemaMap(pluginGroups);
    const rfNodes: Node[] = (tpl.nodes as WorkflowDetail['nodes']).map(n => ({
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
    const rfEdges: Edge[] = (tpl.links as WorkflowDetail['links']).map(l => ({
      id: l.uuid,
      source: l.previous_node_uuid,
      sourceHandle: l.output_field_name,
      target: l.next_node_uuid,
      targetHandle: l.input_field_name,
      animated: false,
    }));

    // 名字加后缀，与模板本身区分；未保存前不会出现在工作流列表
    setWorkflow('', `${tpl.name}（副本）`, rfNodes, rfEdges);
    initializedRef.current = initKey;
  }, [isNew, templateId, templates, pluginGroups, setWorkflow]);

  if (!isNew && isLoading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#646262', fontSize: 13 }}>
        加载中...
      </div>
    );
  }

  if (!isNew && error) {
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
        background: '#fdfcfc',
        overflow: 'hidden',
        // 全屏：覆盖整个视口（侧边栏/顶栏被盖住）；弹窗 z-50 仍在上层
        ...(fullscreen
          ? { position: 'fixed' as const, inset: 0, zIndex: 40, height: '100vh' }
          : { height: '100%' }),
      }}
    >
      {/* 顶部工具栏 */}
      <FlowToolbar fullscreen={fullscreen} onToggleFullscreen={toggleFullscreen} />

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
