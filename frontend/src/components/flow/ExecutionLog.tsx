import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ScrollArea } from '@/components/ui/ScrollArea';
import { Badge } from '@/components/ui/Badge';
import type { BadgeVariant } from '@/components/ui/Badge';
import { useFlowStore } from '@/store/flowStore';

export type LogStatus = 'running' | 'success' | 'failed' | 'info';

export interface LogEntry {
  status: LogStatus;
  level?: string; // info | error（后端 SSE 附带）
  message: string;
  timestamp: string;
  node_uuid?: string;
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

/** 级别筛选选项 */
const LEVEL_OPTIONS = [
  { value: 'all', label: '全部级别' },
  { value: 'info', label: '信息' },
  { value: 'running', label: '运行中' },
  { value: 'success', label: '成功' },
  { value: 'failed', label: '失败' },
];

const filterSelectStyle: React.CSSProperties = {
  background: '#f8f7f7',
  border: '1px solid rgba(15,0,0,0.12)',
  borderRadius: 4,
  color: '#646262',
  fontSize: 11,
  padding: '2px 6px',
  outline: 'none',
  fontFamily: 'inherit',
  cursor: 'pointer',
};

export const ExecutionLog: React.FC<ExecutionLogProps> = ({ workflowId }) => {
  // 日志直接从 flowStore 读取（由 useExecution 解析运行 SSE 事件写入），
  // 不再自行建 EventSource —— 后端运行接口是 POST 流，EventSource(GET) 永远连不上
  const logs = useFlowStore((s) => s.executionLogs);
  const scrollRef = useRef<HTMLDivElement>(null);
  // 筛选与排序
  const [levelFilter, setLevelFilter] = useState('all');
  const [nodeFilter, setNodeFilter] = useState('all'); // all | global | 节点uuid
  const [sortDesc, setSortDesc] = useState(false); // false=时间正序（默认），true=倒序

  // 出现过的节点清单（用于按节点筛选）
  const nodeOptions = useMemo(() => {
    const map = new Map<string, string>();
    for (const l of logs) {
      if (l.node_uuid && l.node_name) map.set(l.node_uuid, l.node_name);
    }
    return Array.from(map.entries()).map(([uuid, name]) => ({ uuid, name }));
  }, [logs]);

  // 应用筛选 + 排序
  const visibleLogs = useMemo(() => {
    let result = logs;
    if (levelFilter !== 'all') {
      result = result.filter((l) => (l.status || 'info') === levelFilter);
    }
    if (nodeFilter === 'global') {
      result = result.filter((l) => !l.node_uuid);
    } else if (nodeFilter !== 'all') {
      result = result.filter((l) => l.node_uuid === nodeFilter);
    }
    if (sortDesc) {
      result = [...result].reverse();
    }
    return result;
  }, [logs, levelFilter, nodeFilter, sortDesc]);

  // Auto-scroll to bottom（仅正序时跟随）
  useEffect(() => {
    if (sortDesc) return;
    if (scrollRef.current) {
      const el =
        scrollRef.current.querySelector('[data-radix-scroll-area-viewport]') ??
        scrollRef.current;
      el.scrollTop = el.scrollHeight;
    }
  }, [visibleLogs, sortDesc]);

  if (!workflowId) {
    return (
      <div style={{ color: '#646262', fontSize: 12, padding: 16, fontFamily: 'monospace' }}>
        请先保存工作流后再执行
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* 筛选栏 */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '4px 12px',
          borderBottom: '1px solid rgba(15,0,0,0.12)',
          fontFamily: 'var(--font-mono, monospace)',
          flexShrink: 0,
        }}
      >
        <select
          value={levelFilter}
          onChange={(e) => setLevelFilter(e.target.value)}
          style={filterSelectStyle}
          title="按日志级别筛选"
        >
          {LEVEL_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        <select
          value={nodeFilter}
          onChange={(e) => setNodeFilter(e.target.value)}
          style={filterSelectStyle}
          title="按节点/全局筛选"
        >
          <option value="all">全部来源</option>
          <option value="global">全局（工作流级）</option>
          {nodeOptions.map((n) => (
            <option key={n.uuid} value={n.uuid}>{n.name}</option>
          ))}
        </select>
        <button
          onClick={() => setSortDesc((v) => !v)}
          style={{ ...filterSelectStyle, cursor: 'pointer' }}
          title="切换时间排序"
        >
          时间 {sortDesc ? '↓ 最新在前' : '↑ 最早在前'}
        </button>
        <span style={{ marginLeft: 'auto', color: '#9a9898', fontSize: 10 }}>
          {visibleLogs.length}/{logs.length} 条
        </span>
      </div>

      {logs.length === 0 ? (
        <div style={{ color: '#646262', fontSize: 12, padding: 16, fontFamily: 'monospace' }}>
          等待执行日志...
        </div>
      ) : (
        <ScrollArea maxHeight={200} ref={scrollRef}>
          <div style={{ fontFamily: 'monospace', fontSize: 12, lineHeight: '20px' }}>
            {visibleLogs.map((entry, idx) => (
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
                <span style={{ color: '#424245', minWidth: 80 }}>
                  {entry.node_name || '全局'}
                </span>
                <Badge variant={statusVariant[entry.status] || 'info'}>
                  {statusLabel[entry.status] || '信息'}
                </Badge>
                <span style={{ color: '#646262', fontSize: 11 }}>{entry.message}</span>
              </div>
            ))}
            {visibleLogs.length === 0 && (
              <div style={{ color: '#9a9898', fontSize: 11, padding: 12 }}>
                无匹配日志（调整上方筛选条件）
              </div>
            )}
          </div>
        </ScrollArea>
      )}
    </div>
  );
};
