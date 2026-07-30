import { useCallback, useEffect, useState } from 'react';
import { Loader2, RotateCcw, ChevronDown, ChevronRight } from 'lucide-react';
import { Dialog } from '../ui/Dialog';
import { Badge } from '../ui/Badge';
import type { BadgeVariant } from '../ui/Badge';
import { useFlowStore } from '../../store/flowStore';

/** 后端 GET /api/workflow/{id}/runs 返回的单条运行记录 */
interface NodeRunInfo {
  title?: string;
  name?: string;
  status?: string;
  duration_ms?: number;
  error?: string;
}

interface RunRecord {
  id: string;
  workflow_id: string;
  status: string; // running/completed/failed/cancelled
  started_at: number | null;
  finished_at: number | null;
  node_outputs: Record<string, NodeRunInfo>;
  logs: { message?: string; level?: string }[];
}

interface RunHistoryDialogProps {
  open: boolean;
  onClose: () => void;
  workflowId: string | null;
}

const STATUS_BADGE: Record<string, { variant: BadgeVariant; label: string }> = {
  completed: { variant: 'success', label: '成功' },
  failed: { variant: 'error', label: '失败' },
  cancelled: { variant: 'warning', label: '已取消' },
  running: { variant: 'info', label: '运行中' },
};

function fmtTs(ts: number | null): string {
  if (!ts) return '-';
  return new Date(ts * 1000).toLocaleString('zh-CN', { hour12: false });
}

function fmtDuration(run: RunRecord): string {
  if (!run.started_at || !run.finished_at) return '-';
  const sec = run.finished_at - run.started_at;
  if (sec < 60) return `${sec}s`;
  return `${Math.floor(sec / 60)}m${sec % 60}s`;
}

function fmtMs(ms?: number): string {
  if (ms == null) return '';
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(2)}s`;
}

/**
 * 运行历史弹窗（对标 ComfyUI 的运行队列/历史）：
 * 列出每次运行的状态、起止时间、耗时与每节点耗时明细，
 * 支持「载入结果」把历史运行恢复到画布（节点状态 + 输出预览 + 分析报告）。
 */
export function RunHistoryDialog({ open, onClose, workflowId }: RunHistoryDialogProps) {
  const [runs, setRuns] = useState<RunRecord[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const { setCurrentRunId, setNodeStatus, setNodeDuration, setNodeError, resetStatuses } = useFlowStore();
  const currentRunId = useFlowStore((s) => s.currentRunId);

  useEffect(() => {
    if (!open || !workflowId) return;
    let alive = true;
    setLoading(true);
    setError(null);
    fetch(`/api/workflow/${workflowId}/runs`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => alive && setRuns(data))
      .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [open, workflowId]);

  // 载入历史运行：恢复节点状态/耗时/错误与 currentRunId，画布上即可查看输出/报告
  const handleLoad = useCallback(
    (run: RunRecord) => {
      resetStatuses();
      setCurrentRunId(run.id);
      for (const [uuid, info] of Object.entries(run.node_outputs || {})) {
        setNodeStatus(uuid, info.status === 'success' ? 'success' : 'failed');
        if (typeof info.duration_ms === 'number') setNodeDuration(uuid, info.duration_ms);
        if (info.error) setNodeError(uuid, info.error);
      }
      onClose();
    },
    [resetStatuses, setCurrentRunId, setNodeStatus, setNodeDuration, setNodeError, onClose],
  );

  return (
    <Dialog open={open} onClose={onClose} title="运行历史" className="w-[640px]">
      <div style={{ maxHeight: 420, overflowY: 'auto' }}>
        {loading && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#646262', fontSize: 12, padding: 16 }}>
            <Loader2 size={13} style={{ animation: 'spin 1s linear infinite' }} />
            加载运行历史...
          </div>
        )}
        {error && (
          <div style={{ color: '#ff3b30', fontSize: 12, padding: 16 }}>加载失败: {error}</div>
        )}
        {!loading && !error && (!runs || runs.length === 0) && (
          <div style={{ color: '#9a9898', fontSize: 12, padding: 16, textAlign: 'center' }}>
            暂无运行记录 — 点击工具栏「运行」开始第一次执行
          </div>
        )}
        {runs?.map((run) => {
          const badge = STATUS_BADGE[run.status] || { variant: 'default' as BadgeVariant, label: run.status };
          const nodeEntries = Object.entries(run.node_outputs || {});
          const expanded = expandedId === run.id;
          const isCurrent = run.id === currentRunId;
          return (
            <div
              key={run.id}
              style={{
                border: `1px solid ${isCurrent ? '#007aff' : 'rgba(15,0,0,0.12)'}`,
                borderRadius: 4,
                marginBottom: 8,
                background: '#fdfcfc',
              }}
            >
              <div
                style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 10px', cursor: 'pointer' }}
                onClick={() => setExpandedId(expanded ? null : run.id)}
              >
                {expanded ? <ChevronDown size={13} color="#9a9898" /> : <ChevronRight size={13} color="#9a9898" />}
                <Badge variant={badge.variant}>{badge.label}</Badge>
                <span style={{ fontSize: 12, color: '#201d1d', fontFamily: 'var(--font-mono, monospace)' }}>
                  {fmtTs(run.started_at)}
                </span>
                <span style={{ fontSize: 11, color: '#646262' }}>耗时 {fmtDuration(run)}</span>
                {nodeEntries.length > 0 && (
                  <span style={{ fontSize: 11, color: '#9a9898' }}>{nodeEntries.length} 个节点</span>
                )}
                {isCurrent && <span style={{ fontSize: 10, color: '#007aff' }}>当前载入</span>}
                <div style={{ flex: 1 }} />
                <button
                  className="tb-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleLoad(run);
                  }}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 4,
                    padding: '3px 8px',
                    background: 'transparent',
                    border: '1px solid rgba(15,0,0,0.12)',
                    borderRadius: 4,
                    color: '#007aff',
                    fontSize: 11,
                    cursor: 'pointer',
                  }}
                  title="将该次运行的节点状态与输出载入画布"
                >
                  <RotateCcw size={11} />
                  载入结果
                </button>
              </div>
              {expanded && (
                <div style={{ borderTop: '1px solid rgba(15,0,0,0.08)', padding: '6px 10px 8px 30px' }}>
                  {nodeEntries.length === 0 && (
                    <div style={{ fontSize: 11, color: '#9a9898' }}>
                      该记录无节点明细（旧版本运行或未执行任何节点）
                    </div>
                  )}
                  {nodeEntries.map(([uuid, info]) => (
                    <div
                      key={uuid}
                      style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11, lineHeight: '20px' }}
                    >
                      <span style={{ color: info.status === 'success' ? '#30d158' : '#ff3b30', width: 12 }}>
                        {info.status === 'success' ? '✓' : '✗'}
                      </span>
                      <span style={{ color: '#424245', minWidth: 140 }}>{info.title || info.name || uuid}</span>
                      <span style={{ color: '#9a9898', fontFamily: 'var(--font-mono, monospace)' }}>
                        {fmtMs(info.duration_ms)}
                      </span>
                      {info.error && (
                        <span style={{ color: '#ff3b30', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {info.error}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </Dialog>
  );
}
