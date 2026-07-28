import { useState, useRef, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Play, Square, GitBranch, ChevronRight, Loader2, Pencil } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Card, Badge, Button } from '@/components/ui';
import { useWorkflows } from '../hooks/useWorkflow';

interface RunRecord {
  id: string;
  workflow_id: string;
  status: string;
  started_at: number;
  finished_at: number | null;
  logs: Array<{ time?: string; level?: string; message?: string } | string>;
}

interface LogLine {
  time: string;
  type: string;
  text: string;
}

const statusVariant: Record<string, 'success' | 'warning' | 'error' | 'default'> = {
  success: 'success',
  completed: 'success',
  running: 'warning',
  failed: 'error',
};

function formatTs(ts: number | null) {
  if (!ts) return '-';
  return new Date(ts * 1000).toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
}

const eventLabels: Record<string, string> = {
  execution_order: '执行顺序',
  node_start: '节点开始',
  node_complete: '节点完成',
  node_failed: '节点失败',
  workflow_complete: '运行完成',
  workflow_failed: '运行失败',
};

const eventColors: Record<string, string> = {
  node_start: '#007aff',
  node_complete: '#30d158',
  node_failed: '#ff3b30',
  workflow_complete: '#30d158',
  workflow_failed: '#ff3b30',
};

/** 运行中心：选择工作流实际运行，实时查看进度日志与历史运行记录 */
export default function RunCenter() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: workflows, isLoading } = useWorkflows('my', '');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [logs, setLogs] = useState<LogLine[]>([]);
  const abortRef = useRef<AbortController | null>(null);

  const { data: runs } = useQuery<RunRecord[]>({
    queryKey: ['workflow-runs', selectedId],
    queryFn: () => fetch(`/api/workflow/${selectedId}/runs`).then(r => r.json()),
    enabled: !!selectedId,
  });

  const appendLog = useCallback((type: string, text: string) => {
    const time = new Date().toLocaleTimeString('zh-CN', { hour12: false });
    setLogs(prev => [...prev, { time, type, text }]);
  }, []);

  const handleRun = useCallback(async () => {
    if (!selectedId || running) return;
    setLogs([]);
    setRunning(true);
    const controller = new AbortController();
    abortRef.current = controller;
    appendLog('info', '开始运行工作流...');

    try {
      const response = await fetch(`/api/workflow/${selectedId}/run/stream`, {
        method: 'POST',
        signal: controller.signal,
        headers: { Accept: 'text/event-stream' },
      });
      if (!response.ok || !response.body) {
        throw new Error(`运行失败 (HTTP ${response.status})`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const blocks = buffer.split('\n\n');
        buffer = blocks.pop() || '';

        for (const block of blocks) {
          if (!block.trim()) continue;
          let eventType = '';
          let dataStr = '';
          for (const line of block.split('\n')) {
            if (line.startsWith('event: ')) eventType = line.slice(7).trim();
            else if (line.startsWith('data: ')) dataStr += (dataStr ? '\n' : '') + line.slice(6);
          }
          if (!eventType) continue;

          try {
            const data = dataStr ? JSON.parse(dataStr) : {};
            const label = eventLabels[eventType] || eventType;
            const detail = data.node_title || data.node_name || data.node_uuid
              ? ` — ${data.node_title || data.node_name || data.node_uuid}`
              : '';
            const error = data.error ? ` (${data.error})` : '';
            appendLog(eventType, `${label}${detail}${error}`);
          } catch {
            appendLog(eventType, eventLabels[eventType] || eventType);
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        appendLog('info', '已手动停止');
      } else {
        appendLog('workflow_failed', err instanceof Error ? err.message : '运行出错');
      }
    } finally {
      setRunning(false);
      abortRef.current = null;
      queryClient.invalidateQueries({ queryKey: ['workflow-runs', selectedId] });
    }
  }, [selectedId, running, appendLog, queryClient]);

  const handleStop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return (
    <div className="flex flex-col h-full">
      <div className="mb-4">
        <h1 className="text-xl font-semibold text-[#201d1d] mb-1">运行中心</h1>
        <p className="text-[13px] text-[#646262]">
          在此实际运行已编排好的工作流，实时查看执行进度与历史运行记录
        </p>
      </div>

      <div className="grid flex-1 min-h-0 grid-cols-1 gap-4 lg:grid-cols-3">
        {/* 左侧：工作流列表 */}
        <Card title="选择工作流" className="flex flex-col min-h-0 overflow-hidden">
          <div className="flex-1 overflow-y-auto -mx-1 px-1">
            {isLoading && <p className="py-4 text-center text-xs text-[#646262]">加载中...</p>}
            {!isLoading && (!workflows || workflows.length === 0) && (
              <div className="py-8 text-center">
                <p className="mb-2 text-xs text-[#646262]">还没有工作流</p>
                <Button variant="secondary" size="sm" onClick={() => navigate('/workflow')}>
                  去创建
                </Button>
              </div>
            )}
            {workflows?.map(wf => (
              <div
                key={wf.id}
                onClick={() => { setSelectedId(wf.id); setLogs([]); }}
                className={`mb-1 flex cursor-pointer items-center gap-2 rounded-[4px] px-2 py-2 transition-colors ${
                  selectedId === wf.id
                    ? 'bg-[#007aff]/10 text-[#007aff]'
                    : 'text-[#201d1d] hover:bg-[#f1eeee]'
                }`}
              >
                <GitBranch size={14} className="shrink-0" />
                <span className="flex-1 truncate text-[13px]">{wf.name}</span>
                <button
                  onClick={(e) => { e.stopPropagation(); navigate(`/workflow/${wf.id}`); }}
                  className="cursor-pointer text-[#9a9898] hover:text-[#007aff]"
                  title="编辑工作流"
                >
                  <Pencil size={12} />
                </button>
                <ChevronRight size={14} className="shrink-0 text-[#9a9898]" />
              </div>
            ))}
          </div>
        </Card>

        {/* 中间：运行控制 + 实时日志 */}
        <Card title="运行" className="flex flex-col min-h-0 overflow-hidden">
          <div className="mb-3 flex items-center gap-2">
            <Button
              variant="primary"
              size="sm"
              disabled={!selectedId || running}
              onClick={handleRun}
              className="flex items-center gap-1"
            >
              {running ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />}
              {running ? '运行中...' : '运行'}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              disabled={!running}
              onClick={handleStop}
              className="flex items-center gap-1"
            >
              <Square size={12} />
              停止
            </Button>
            {!selectedId && <span className="text-xs text-[#9a9898]">请先在左侧选择一个工作流</span>}
          </div>

          <div
            className="flex-1 overflow-y-auto rounded-[4px] p-2 font-mono text-xs"
            style={{ background: '#201d1d', minHeight: 200 }}
          >
            {logs.length === 0 ? (
              <span className="text-[#9a9898]">运行日志将在这里实时显示</span>
            ) : (
              logs.map((log, i) => (
                <div key={i} className="mb-0.5 flex gap-2">
                  <span className="shrink-0 text-[#9a9898]">{log.time}</span>
                  <span style={{ color: eventColors[log.type] || '#fdfcfc' }}>{log.text}</span>
                </div>
              ))
            )}
          </div>
        </Card>

        {/* 右侧：历史运行记录 */}
        <Card title="运行历史" className="flex flex-col min-h-0 overflow-hidden">
          <div className="flex-1 overflow-y-auto">
            {!selectedId && (
              <p className="py-4 text-center text-xs text-[#9a9898]">选择工作流后显示历史记录</p>
            )}
            {selectedId && (!runs || runs.length === 0) && (
              <p className="py-4 text-center text-xs text-[#9a9898]">暂无运行记录</p>
            )}
            {runs?.map(run => (
              <div
                key={run.id}
                className="mb-2 rounded-[4px] border border-[rgba(15,0,0,0.12)] p-2"
              >
                <div className="flex items-center justify-between">
                  <Badge variant={statusVariant[run.status] || 'default'}>{run.status}</Badge>
                  <span className="font-mono text-[11px] text-[#646262]">{formatTs(run.started_at)}</span>
                </div>
                <div className="mt-1 text-[11px] text-[#9a9898]">
                  结束: {formatTs(run.finished_at)}
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
