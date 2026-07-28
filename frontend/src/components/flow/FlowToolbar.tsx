import { useCallback, useState } from 'react';
import { Play, Square, Save, Circle, Loader2, Check } from 'lucide-react';
import { useFlowStore } from '../../store/flowStore';
import { useExecution } from '../../hooks/useExecution';
import { useSaveWorkflow } from '../../hooks/useWorkflow';

interface FlowToolbarProps {
  onSave?: () => void;
}

export function FlowToolbar({ onSave }: FlowToolbarProps) {
  const { workflowId, workflowName, nodes, edges, setWorkflowName, setWorkflow, isRunning, nodeStatuses } = useFlowStore();
  const { runWorkflow, stopExecution } = useExecution();
  const saveMutation = useSaveWorkflow();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(workflowName);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');

  const handleNameSubmit = useCallback(() => {
    setWorkflowName(draft.trim() || '未命名工作流');
    setEditing(false);
  }, [draft, setWorkflowName]);

  const handleNameKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter') handleNameSubmit();
      if (e.key === 'Escape') {
        setDraft(workflowName);
        setEditing(false);
      }
    },
    [handleNameSubmit, workflowName]
  );

  const handleSave = useCallback(async () => {
    if (onSave) {
      onSave();
      return;
    }
    setSaveStatus('saving');
    try {
      // 将 ReactFlow nodes/edges 转换为后端格式
      const backendNodes = nodes.map(n => ({
        uuid: n.id,
        name: (n.data as Record<string, unknown>)?.pluginName as string || '',
        title: (n.data as Record<string, unknown>)?.title as string || n.id,
        positionX: n.position?.x ?? 0,
        positionY: n.position?.y ?? 0,
        width: n.measured?.width ?? (n.data as Record<string, unknown>)?.width as number ?? 240,
        height: n.measured?.height ?? (n.data as Record<string, unknown>)?.height as number ?? 180,
        static_input_data: ((n.data as Record<string, unknown>)?.static_input_data as Record<string, unknown>) || {},
      }));
      const backendLinks = edges.map((e, i) => ({
        uuid: e.id || `l${i}`,
        previous_node_uuid: e.source,
        output_field_name: (e.sourceHandle as string) || 'output',
        next_node_uuid: e.target,
        input_field_name: (e.targetHandle as string) || 'input',
      }));

      const result = await saveMutation.mutateAsync({
        id: workflowId,
        name: workflowName,
        nodes: backendNodes,
        links: backendLinks,
      });

      // 如果是新建，更新 store 中的 workflowId
      if (!workflowId && result?.id) {
        setWorkflow(result.id, workflowName, nodes, edges);
      }

      setSaveStatus('saved');
      setTimeout(() => setSaveStatus('idle'), 2000);
    } catch {
      setSaveStatus('error');
      setTimeout(() => setSaveStatus('idle'), 2000);
    }
  }, [onSave, nodes, edges, workflowId, workflowName, saveMutation, setWorkflow]);

  const handleRunClick = useCallback(() => {
    if (!workflowId) return;
    if (isRunning) {
      stopExecution();
    } else {
      runWorkflow(workflowId);
    }
  }, [workflowId, isRunning, runWorkflow, stopExecution]);

  // 统计运行状态
  const totalNodes = Object.keys(nodeStatuses).length;
  const statusCounts = Object.values(nodeStatuses).reduce(
    (acc, s) => { acc[s] = (acc[s] || 0) + 1; return acc; },
    {} as Record<string, number>
  );

  const statusText = isRunning
    ? `运行中 (${statusCounts['running'] || 0}/${totalNodes})`
    : statusCounts['failed']
    ? '运行失败'
    : statusCounts['success']
    ? '运行完成'
    : '就绪';

  const statusColor = isRunning
    ? '#007aff'
    : statusCounts['failed']
    ? '#ff3b30'
    : statusCounts['success']
    ? '#30d158'
    : '#646262';

  const saveBtnColor = saveStatus === 'saved' ? '#30d158' : saveStatus === 'error' ? '#ff3b30' : '#646262';
  const saveBtnText = saveStatus === 'saving' ? '保存中...' : saveStatus === 'saved' ? '已保存' : saveStatus === 'error' ? '保存失败' : '保存';

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '8px 16px',
        background: '#f1eeee',
        borderBottom: '1px solid rgba(15,0,0,0.12)',
        height: 44,
        flexShrink: 0,
      }}
    >
      {/* 工作流名称 */}
      {editing ? (
        <input
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={handleNameSubmit}
          onKeyDown={handleNameKeyDown}
          style={{
            background: '#f8f7f7',
            border: '1px solid #007aff',
            borderRadius: 4,
            color: '#201d1d',
            padding: '2px 8px',
            fontSize: 13,
            fontFamily: 'inherit',
            outline: 'none',
            minWidth: 120,
          }}
        />
      ) : (
        <span
          onDoubleClick={() => { setDraft(workflowName); setEditing(true); }}
          style={{
            color: '#201d1d',
            fontSize: 13,
            fontWeight: 600,
            cursor: 'pointer',
            userSelect: 'none',
          }}
          title="双击编辑名称"
        >
          {workflowName}
        </span>
      )}

      {/* 分隔 */}
      <div style={{ flex: 1 }} />

      {/* 运行状态 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        {isRunning && (
          <Loader2
            size={12}
            style={{ color: statusColor, animation: 'spin 1s linear infinite', flexShrink: 0 }}
          />
        )}
        {!isRunning && (
          <Circle
            size={10}
            fill={statusColor}
            stroke={statusColor}
            style={{ flexShrink: 0 }}
          />
        )}
        <span style={{ color: statusColor, fontSize: 12 }}>{statusText}</span>
      </div>

      {/* 保存按钮 */}
      <button
        onClick={handleSave}
        disabled={saveStatus === 'saving'}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 5,
          padding: '4px 12px',
          background: '#f8f7f7',
          border: '1px solid rgba(15,0,0,0.12)',
          borderRadius: 4,
          color: saveBtnColor,
          fontSize: 12,
          cursor: saveStatus === 'saving' ? 'not-allowed' : 'pointer',
          transition: 'color 0.2s ease',
        }}
        title="保存工作流"
      >
        {saveStatus === 'saved' ? <Check size={13} /> : <Save size={13} />}
        {saveBtnText}
      </button>

      {/* 运行/停止按钮 */}
      <button
        onClick={handleRunClick}
        disabled={!workflowId}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 5,
          padding: '4px 14px',
          background: isRunning ? '#ff3b30' : '#007aff',
          border: 'none',
          borderRadius: 4,
          color: isRunning ? '#fff' : '#201d1d',
          fontSize: 12,
          fontWeight: 600,
          cursor: !workflowId ? 'not-allowed' : 'pointer',
          opacity: !workflowId ? 0.5 : 1,
          transition: 'background 0.15s ease',
        }}
        title={isRunning ? '停止运行' : '运行工作流'}
      >
        {isRunning ? <Square size={13} fill="currentColor" /> : <Play size={13} />}
        {isRunning ? '停止' : '运行'}
      </button>
    </div>
  );
}
