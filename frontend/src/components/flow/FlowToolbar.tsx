import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Play, Square, Save, Circle, Loader2, Check, ArrowLeft, Download, Upload, Maximize2, Minimize2, Sparkles, History, Cpu } from 'lucide-react';
import type { Node, Edge } from '@xyflow/react';
import { useFlowStore } from '../../store/flowStore';
import { useExecution } from '../../hooks/useExecution';
import { useSaveWorkflow } from '../../hooks/useWorkflow';
import { usePlugins } from '../../hooks/usePlugins';
import { extractStaticInputData, buildSchemaMap, buildNodeData } from '../../lib/nodeSchema';
import { Dialog } from '../ui/Dialog';
import { Button } from '../ui/Button';
import { RunHistoryDialog } from './RunHistoryDialog';

interface FlowToolbarProps {
  onSave?: () => void;
  fullscreen?: boolean;
  onToggleFullscreen?: () => void;
}

/** 用量百分比 → 颜色（与因子研究页资源监控一致） */
function usageColor(pct: number): string {
  if (pct >= 85) return '#ff3b30';
  if (pct >= 60) return '#ff9f0a';
  return '#30d158';
}

/**
 * 工具栏资源占用指示（对标 ComfyUI 顶栏的 CPU/RAM 监控）：
 * 每 3s 轮询 /api/system/resources，展示 CPU / 内存占用百分比。
 */
function ResourceChip() {
  const [cpu, setCpu] = useState<number | null>(null);
  const [mem, setMem] = useState<number | null>(null);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const r = await fetch('/api/system/resources');
        if (!r.ok) return;
        const data = await r.json();
        if (!alive) return;
        setCpu(typeof data?.cpu?.avg === 'number' ? data.cpu.avg : null);
        setMem(typeof data?.memory?.physical?.percent === 'number' ? data.memory.physical.percent : null);
      } catch {
        if (alive) { setCpu(null); setMem(null); }
      }
    };
    tick();
    const id = setInterval(tick, 3000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        padding: '3px 8px',
        border: '1px solid rgba(15,0,0,0.12)',
        borderRadius: 4,
        fontSize: 11,
        color: '#646262',
        fontVariantNumeric: 'tabular-nums',
      }}
      title="本机资源占用（CPU 均值 / 物理内存，3s 刷新）"
    >
      <Cpu size={12} style={{ flexShrink: 0 }} />
      <span>
        CPU <span style={{ color: cpu == null ? '#9a9898' : usageColor(cpu), fontWeight: 600 }}>{cpu == null ? '--' : `${cpu.toFixed(0)}%`}</span>
      </span>
      <span>
        内存 <span style={{ color: mem == null ? '#9a9898' : usageColor(mem), fontWeight: 600 }}>{mem == null ? '--' : `${mem.toFixed(0)}%`}</span>
      </span>
    </div>
  );
}

const AI_FLOW_PLACEHOLDER = `描述你想要的工作流，例如：
・拉取沪深300成分股日线数据，计算 20 日动量因子，做 IC 分析和分组收益
・在当前工作流基础上，因子标准化之后加一步行业中性化
・用 MACD 金叉作为信号跑一个回测，结果推送到钉钉`;

export function FlowToolbar({ onSave, fullscreen, onToggleFullscreen }: FlowToolbarProps) {
  const navigate = useNavigate();
  const { workflowId, workflowName, nodes, edges, setWorkflowName, setWorkflow, isRunning, nodeStatuses, isDirty, markClean, markDirty, runStartedAt, runFinishedAt } = useFlowStore();
  const { runWorkflow, stopExecution } = useExecution();
  const { data: pluginGroups } = usePlugins();
  const saveMutation = useSaveWorkflow();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(workflowName);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [showBackConfirm, setShowBackConfirm] = useState(false);
  const [importing, setImporting] = useState(false);
  // 运行历史弹窗
  const [showHistory, setShowHistory] = useState(false);
  // AI 生成工作流
  const [showAI, setShowAI] = useState(false);
  const [aiInstruction, setAiInstruction] = useState('');
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);
  const fileInputRef = useCallback(() => document.getElementById('workflow-import-input') as HTMLInputElement | null, []);

  const handleBack = useCallback(() => {
    if (isDirty) {
      setShowBackConfirm(true);
    } else {
      navigate('/workflow');
    }
  }, [isDirty, navigate]);

  const handleConfirmBack = useCallback(() => {
    setShowBackConfirm(false);
    navigate('/workflow');
  }, [navigate]);

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
      const backendNodes = nodes.map(n => {
        const data = (n.data || {}) as Record<string, unknown>;
        return {
          uuid: n.id,
          name: (data.nodeType as string) || '',
          title: (data.label as string) || n.id,
          positionX: n.position?.x ?? 0,
          positionY: n.position?.y ?? 0,
          width: n.measured?.width ?? 240,
          height: n.measured?.height ?? 180,
          static_input_data: extractStaticInputData(data),
        };
      });
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

      // 如果是新建，更新 store 中的 workflowId 并跳到正式地址
      // （setTimeout 等 isDirty=false 刷新完成，避免 useBlocker 用旧状态拦截）
      if (!workflowId && result?.id) {
        setWorkflow(result.id, workflowName, nodes, edges);
        setTimeout(() => navigate(`/workflow/${result.id}`, { replace: true }), 0);
      }

      setSaveStatus('saved');
      markClean();
      setTimeout(() => setSaveStatus('idle'), 2000);
    } catch {
      setSaveStatus('error');
      setTimeout(() => setSaveStatus('idle'), 2000);
    }
  }, [onSave, nodes, edges, workflowId, workflowName, saveMutation, setWorkflow, markClean, navigate]);

  // AI 生成/修改工作流 → 应用到画布（需手动保存）
  const handleAIGenerate = useCallback(async () => {
    if (!aiInstruction.trim() || !pluginGroups) return;
    setAiLoading(true);
    setAiError(null);
    try {
      const currentWorkflow = nodes.length > 0 ? {
        nodes: nodes.map(n => {
          const data = (n.data || {}) as Record<string, unknown>;
          return {
            uuid: n.id,
            name: (data.nodeType as string) || '',
            title: (data.label as string) || n.id,
            positionX: n.position?.x ?? 0,
            positionY: n.position?.y ?? 0,
            static_input_data: extractStaticInputData(data),
          };
        }),
        links: edges.map((e, i) => ({
          uuid: e.id || `l${i}`,
          previous_node_uuid: e.source,
          output_field_name: (e.sourceHandle as string) || 'output',
          next_node_uuid: e.target,
          input_field_name: (e.targetHandle as string) || 'input',
        })),
      } : null;

      const res = await fetch('/api/ai/workflow', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ instruction: aiInstruction, current_workflow: currentWorkflow }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(err?.detail || `HTTP ${res.status}`);
      }
      const wf = await res.json();

      // 后端格式 → ReactFlow 画布
      const schemaMap = buildSchemaMap(pluginGroups);
      const rfNodes: Node[] = (wf.nodes || []).map((n: Record<string, unknown>) => ({
        id: String(n.uuid),
        position: { x: Number(n.positionX) || 0, y: Number(n.positionY) || 0 },
        type: 'workNode',
        data: buildNodeData(
          String(n.name),
          String(n.title || n.name),
          (n.static_input_data as Record<string, unknown>) || {},
          schemaMap[String(n.name)],
        ),
      }));
      const rfEdges: Edge[] = (wf.links || []).map((l: Record<string, unknown>, i: number) => ({
        id: String(l.uuid || `l${i}`),
        source: String(l.previous_node_uuid),
        sourceHandle: String(l.output_field_name || 'output'),
        target: String(l.next_node_uuid),
        targetHandle: String(l.input_field_name || 'input'),
        animated: false,
      }));

      // 保留当前 workflowId 与名称（新建时采用 AI 给的名字），应用后标脏，由用户确认保存
      setWorkflow(workflowId || '', workflowId ? workflowName : (wf.name || workflowName), rfNodes, rfEdges);
      markDirty();
      setShowAI(false);
      setAiInstruction('');
    } catch (e) {
      setAiError(e instanceof Error ? e.message : String(e));
    } finally {
      setAiLoading(false);
    }
  }, [aiInstruction, pluginGroups, nodes, edges, workflowId, workflowName, setWorkflow, markDirty]);

  const handleRunClick = useCallback(() => {
    if (!workflowId) return;
    if (isRunning) {
      stopExecution();
    } else {
      runWorkflow(workflowId);
    }
  }, [workflowId, isRunning, runWorkflow, stopExecution]);

  // 快捷键（对标 ComfyUI）：Cmd/Ctrl+Enter 运行/停止，Cmd/Ctrl+S 保存
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey)) return;
      if (e.key === 'Enter') {
        e.preventDefault();
        handleRunClick();
      } else if (e.key === 's' || e.key === 'S') {
        e.preventDefault();
        handleSave();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [handleRunClick, handleSave]);

  // 运行计时器：运行中每秒刷新，结束后定格展示总耗时
  const [, setTimerTick] = useState(0);
  useEffect(() => {
    if (!isRunning) return;
    const id = setInterval(() => setTimerTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, [isRunning]);
  const elapsedMs = runStartedAt
    ? (isRunning ? Date.now() : runFinishedAt ?? Date.now()) - runStartedAt
    : null;
  const elapsedText = elapsedMs != null
    ? `${String(Math.floor(elapsedMs / 60000)).padStart(2, '0')}:${String(Math.floor(elapsedMs / 1000) % 60).padStart(2, '0')}`
    : null;

  // 导出工作流
  const handleExport = useCallback(() => {
    const backendNodes = nodes.map(n => {
      const data = (n.data || {}) as Record<string, unknown>;
      return {
        uuid: n.id,
        name: (data.nodeType as string) || '',
        title: (data.label as string) || n.id,
        positionX: n.position?.x ?? 0,
        positionY: n.position?.y ?? 0,
        width: n.measured?.width ?? 240,
        height: n.measured?.height ?? 180,
        static_input_data: extractStaticInputData(data),
      };
    });
    const backendLinks = edges.map((e, i) => ({
      uuid: e.id || `l${i}`,
      previous_node_uuid: e.source,
      output_field_name: (e.sourceHandle as string) || 'output',
      next_node_uuid: e.target,
      input_field_name: (e.targetHandle as string) || 'input',
    }));
    const exportData = {
      name: workflowName,
      description: '',
      nodes: backendNodes,
      links: backendLinks,
    };
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${workflowName || 'workflow'}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [nodes, edges, workflowName]);

  // 导入工作流
  const handleImportClick = useCallback(() => {
    const input = fileInputRef();
    if (input) input.click();
  }, [fileInputRef]);

  const handleImportFile = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = '';
    setImporting(true);
    try {
      const text = await file.text();
      const data = JSON.parse(text);
      const res = await fetch('/api/workflow/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      if (!res.ok) throw new Error('导入失败');
      const wf = await res.json();
      navigate(`/workflow/${wf.id}`);
    } catch {
      // 静默失败，可以后续加 toast
    } finally {
      setImporting(false);
    }
  }, [navigate, fileInputRef]);

  // 统计运行状态
  const totalNodes = Object.keys(nodeStatuses).length;
  const statusCounts = Object.values(nodeStatuses).reduce(
    (acc, s) => { acc[s] = (acc[s] || 0) + 1; return acc; },
    {} as Record<string, number>
  );
  const doneCount = (statusCounts['success'] || 0) + (statusCounts['failed'] || 0);
  const progressPct = totalNodes > 0 ? (doneCount / totalNodes) * 100 : 0;

  const statusText = isRunning
    ? `运行中 ${doneCount}/${totalNodes}`
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
        position: 'relative',
      }}
    >
      {/* 返回按钮 */}
      <button
        className="tb-btn"
        onClick={handleBack}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 4,
          padding: '4px 10px',
          background: 'transparent',
          border: '1px solid rgba(15,0,0,0.12)',
          borderRadius: 4,
          color: '#201d1d',
          fontSize: 12,
          fontWeight: 500,
          cursor: 'pointer',
          transition: 'background 0.15s ease',
        }}
        title="返回工作流列表"
      >
        <ArrowLeft size={13} />
        返回
      </button>

      {/* 取消按钮 */}
      <button
        className="tb-btn"
        onClick={handleBack}
        style={{
          padding: '4px 10px',
          background: 'transparent',
          border: '1px solid rgba(15,0,0,0.12)',
          borderRadius: 4,
          color: '#646262',
          fontSize: 12,
          fontWeight: 500,
          cursor: 'pointer',
          transition: 'background 0.15s ease',
        }}
        title="取消编辑"
      >
        取消
      </button>

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
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            color: '#201d1d',
            fontSize: 13,
            fontWeight: 600,
            cursor: 'pointer',
            userSelect: 'none',
          }}
          title="双击编辑名称"
        >
          {workflowName}
          {/* 未保存标记（对标 ComfyUI 的 *Unsaved 圆点） */}
          {isDirty && (
            <span
              style={{ width: 7, height: 7, borderRadius: '50%', background: '#ff9f0a', flexShrink: 0 }}
              title="有未保存的更改 (⌘S 保存)"
            />
          )}
        </span>
      )}

      {/* 分隔 */}
      <div style={{ flex: 1 }} />

      {/* 运行状态 + 计时器 */}
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
        {elapsedText && (
          <span
            style={{ color: '#9a9898', fontSize: 11, fontVariantNumeric: 'tabular-nums' }}
            title={isRunning ? '已运行时长' : '上次运行总耗时'}
          >
            {elapsedText}
          </span>
        )}
      </div>

      {/* 资源占用（CPU/内存） */}
      <ResourceChip />

      {/* 运行历史 */}
      <button
        className="tb-btn"
        onClick={() => setShowHistory(true)}
        disabled={!workflowId}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 5,
          padding: '4px 10px',
          background: 'transparent',
          border: '1px solid rgba(15,0,0,0.12)',
          borderRadius: 4,
          color: !workflowId ? '#9a9898' : '#646262',
          fontSize: 12,
          fontWeight: 500,
          cursor: !workflowId ? 'not-allowed' : 'pointer',
          transition: 'background 0.15s ease',
        }}
        title={workflowId ? '查看运行历史（可载入历史结果）' : '保存工作流后可查看运行历史'}
      >
        <History size={13} />
        历史
      </button>

      {/* AI 生成工作流 */}
      <button
        className="tb-btn"
        onClick={() => setShowAI(true)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 5,
          padding: '4px 10px',
          background: 'transparent',
          border: '1px solid rgba(15,0,0,0.12)',
          borderRadius: 4,
          color: '#7c3aed',
          fontSize: 12,
          fontWeight: 500,
          cursor: 'pointer',
          transition: 'background 0.15s ease',
        }}
        title="AI 生成/修改工作流（需先在设置中配置 AI）"
      >
        <Sparkles size={13} />
        AI 生成
      </button>

      {/* 全屏切换 */}
      {onToggleFullscreen && (
        <button
          className="tb-btn"
          onClick={onToggleFullscreen}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 5,
            padding: '4px 10px',
            background: 'transparent',
            border: '1px solid rgba(15,0,0,0.12)',
            borderRadius: 4,
            color: '#646262',
            fontSize: 12,
            fontWeight: 500,
            cursor: 'pointer',
            transition: 'background 0.15s ease',
          }}
          title={fullscreen ? '退出全屏 (Esc)' : '全屏编辑（隐藏其他界面）'}
        >
          {fullscreen ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
          {fullscreen ? '退出全屏' : '全屏'}
        </button>
      )}

      {/* 导出按钮 */}
      <button
        className="tb-btn"
        onClick={handleExport}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 5,
          padding: '4px 10px',
          background: 'transparent',
          border: '1px solid rgba(15,0,0,0.12)',
          borderRadius: 4,
          color: '#646262',
          fontSize: 12,
          fontWeight: 500,
          cursor: 'pointer',
          transition: 'background 0.15s ease',
        }}
        title="导出工作流为 JSON"
      >
        <Download size={13} />
        导出
      </button>

      {/* 导入按钮 */}
      <button
        className="tb-btn"
        onClick={handleImportClick}
        disabled={importing}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 5,
          padding: '4px 10px',
          background: 'transparent',
          border: '1px solid rgba(15,0,0,0.12)',
          borderRadius: 4,
          color: importing ? '#9a9898' : '#646262',
          fontSize: 12,
          fontWeight: 500,
          cursor: importing ? 'not-allowed' : 'pointer',
          transition: 'background 0.15s ease',
        }}
        title="从 JSON 文件导入工作流"
      >
        {importing ? <Loader2 size={13} style={{ animation: 'spin 1s linear infinite' }} /> : <Upload size={13} />}
        {importing ? '导入中...' : '导入'}
      </button>
      <input
        id="workflow-import-input"
        type="file"
        accept=".json"
        onChange={handleImportFile}
        style={{ display: 'none' }}
      />

      {/* 保存按钮 */}
      <button
        className="tb-btn"
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
        title="保存工作流 (⌘S)"
      >
        {saveStatus === 'saved' ? <Check size={13} /> : <Save size={13} />}
        {saveBtnText}
      </button>

      {/* 运行/停止按钮 */}
      <button
        className="tb-btn-solid"
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
        title={isRunning ? '停止运行 (⌘↩)' : '运行工作流 (⌘↩)'}
      >
        {isRunning ? <Square size={13} fill="currentColor" /> : <Play size={13} />}
        {isRunning ? '停止' : '运行'}
      </button>

      {/* 整体运行进度条（工具栏底部 2px，对标 ComfyUI 顶栏进度） */}
      {totalNodes > 0 && (isRunning || doneCount > 0) && (
        <div
          style={{
            position: 'absolute',
            left: 0,
            right: 0,
            bottom: -1,
            height: 2,
            background: 'transparent',
            pointerEvents: 'none',
          }}
        >
          <div
            style={{
              width: `${progressPct}%`,
              height: '100%',
              background: statusCounts['failed'] ? '#ff3b30' : isRunning ? '#007aff' : '#30d158',
              transition: 'width 0.3s ease, background 0.3s ease',
            }}
          />
        </div>
      )}

      {/* 离开确认对话框 */}
      <Dialog
        open={showBackConfirm}
        onClose={() => setShowBackConfirm(false)}
        title="未保存的更改"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowBackConfirm(false)}>
              继续编辑
            </Button>
            <Button variant="danger" onClick={handleConfirmBack}>
              确定离开
            </Button>
          </>
        }
      >
        工作流有未保存的更改，确定要离开吗？
      </Dialog>

      {/* 运行历史弹窗 */}
      <RunHistoryDialog
        open={showHistory}
        onClose={() => setShowHistory(false)}
        workflowId={workflowId}
      />

      {/* AI 生成工作流弹窗 */}
      <Dialog
        open={showAI}
        onClose={() => !aiLoading && setShowAI(false)}
        title="AI 生成 / 修改工作流"
        className="w-[560px]"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowAI(false)} disabled={aiLoading}>
              取消
            </Button>
            <Button onClick={handleAIGenerate} loading={aiLoading} disabled={!aiInstruction.trim()}>
              {aiLoading ? '生成中（可能需要几十秒）...' : '生成并应用到画布'}
            </Button>
          </>
        }
      >
        <div style={{ fontSize: 11, color: '#646262', marginBottom: 8, lineHeight: 1.6 }}>
          用自然语言描述需求，AI 会基于平台全部可用节点生成工作流。
          画布上已有节点时，会在现有基础上修改。
          <span style={{ color: '#ff9f0a' }}>生成结果会替换当前画布，确认无误后请点“保存”。</span>
        </div>
        {aiError && (
          <div
            style={{
              color: '#ff3b30',
              fontSize: 11,
              marginBottom: 8,
              fontFamily: 'var(--font-mono, monospace)',
              whiteSpace: 'pre-wrap',
              maxHeight: 80,
              overflowY: 'auto',
            }}
          >
            {aiError}
          </div>
        )}
        <textarea
          value={aiInstruction}
          onChange={(e) => setAiInstruction(e.target.value)}
          placeholder={AI_FLOW_PLACEHOLDER}
          rows={7}
          autoFocus
          style={{
            width: '100%',
            background: '#f8f7f7',
            border: '1px solid rgba(15,0,0,0.12)',
            borderRadius: 4,
            color: '#201d1d',
            fontSize: 12,
            padding: '8px 10px',
            outline: 'none',
            resize: 'vertical',
            lineHeight: 1.6,
            boxSizing: 'border-box',
            fontFamily: 'inherit',
          }}
        />
      </Dialog>
    </div>
  );
}
