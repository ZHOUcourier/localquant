import React, { useEffect, useRef, useState } from 'react';
import { Badge } from '@/components/ui/Badge';
import type { BadgeVariant } from '@/components/ui/Badge';
import { ScrollArea } from '@/components/ui/ScrollArea';

export type LogStatus = 'running' | 'success' | 'failed' | 'info';

export interface LogEntry {
  status: LogStatus;
  message: string;
  timestamp: string;
  node_id?: string;
  node_name?: string;
}

interface ExecutionLogProps {
  workflowId: string | null;
}

const statusVariant: Record<LogStatus, BadgeVariant> = {
  running: 'warning',
  success: 'success',
  failed: 'error',
  info: 'info',
};

const statusLabel: Record<LogStatus, string> = {
  running: '运行中',
  success: '成功',
  failed: '失败',
  info: '信息',
};

export const ExecutionLog: React.FC<ExecutionLogProps> = ({ workflowId }) => {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!workflowId) return;

    setLogs([]);

    const url = `/api/workflow/run/${workflowId}/stream`;
    const eventSource = new EventSource(url);

    eventSource.onmessage = (event) => {
      try {
        const entry: LogEntry = JSON.parse(event.data);
        setLogs((prev) => [...prev, entry]);
      } catch {
        // ignore malformed messages
      }
    };

    eventSource.onerror = () => {
      eventSource.close();
    };

    return () => {
      eventSource.close();
    };
  }, [workflowId]);

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      const el =
        scrollRef.current.querySelector('[data-radix-scroll-area-viewport]') ??
        scrollRef.current;
      el.scrollTop = el.scrollHeight;
    }
  }, [logs]);

  if (!workflowId) {
    return (
      <div style={{ color: '#646262', fontSize: 12, padding: 16, fontFamily: 'monospace' }}>
        请先保存工作流后再执行
      </div>
    );
  }

  if (logs.length === 0) {
    return (
      <div style={{ color: '#646262', fontSize: 12, padding: 16, fontFamily: 'monospace' }}>
        等待执行日志...
      </div>
    );
  }

  return (
    <ScrollArea maxHeight={200} ref={scrollRef}>
      <div style={{ fontFamily: 'monospace', fontSize: 12, lineHeight: '20px' }}>
        {logs.map((entry, idx) => (
          <div
            key={idx}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '2px 12px',
              borderBottom: '1px solid rgba(15,0,0,0.12)',
            }}
          >
            <span style={{ color: '#646262', flexShrink: 0, fontSize: 11 }}>
              {entry.timestamp
                ? new Date(entry.timestamp).toLocaleTimeString('zh-CN', { hour12: false })
                : '--:--:--'}
            </span>
            {entry.node_name && (
              <span style={{ color: '#424245', minWidth: 80 }}>{entry.node_name}</span>
            )}
            <Badge variant={statusVariant[entry.status]}>
              {statusLabel[entry.status]}
            </Badge>
            <span style={{ color: '#646262', fontSize: 11 }}>{entry.message}</span>
          </div>
        ))}
      </div>
    </ScrollArea>
  );
};
