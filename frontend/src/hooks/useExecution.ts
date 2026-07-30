import { useCallback, useRef } from 'react';
import { useFlowStore, type ExecutionLogEntry } from '@/store/flowStore';

export function useExecution() {
  const {
    setNodeStatus, setNodeDuration, setNodeError, resetStatuses, setRunning,
    setCurrentRunId, setRunStartedAt, setRunFinishedAt, appendLog, clearLogs,
  } = useFlowStore();
  const abortRef = useRef<AbortController | null>(null);
  // 本次运行 id：停止时用于通知后端取消（AbortController 只断前端连接）
  const runIdRef = useRef<string | null>(null);

  const runWorkflow = useCallback(
    async (workflowId: string) => {
      // 1. 重置所有节点状态为 pending，清空上一次日志，记录运行开始时间
      resetStatuses();
      clearLogs();
      setRunning(true);
      setRunStartedAt(Date.now());
      runIdRef.current = null;

      // 2. 创建 AbortController
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        // 3. 连接 SSE
        const response = await fetch(`/api/workflow/${workflowId}/run/stream`, {
          method: 'POST',
          signal: controller.signal,
          headers: { Accept: 'text/event-stream' },
        });

        if (!response.ok || !response.body) {
          throw new Error(`SSE 连接失败: ${response.status}`);
        }

        // 4. 读取 SSE 流
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });

          // 按双换行分割完整的 SSE 事件块
          const blocks = buffer.split('\n\n');
          // 最后一个可能不完整，保留在 buffer
          buffer = blocks.pop() || '';

          for (const block of blocks) {
            if (!block.trim()) continue;

            // 解析 event: 和 data: 行
            let eventType = '';
            let dataStr = '';
            for (const line of block.split('\n')) {
              if (line.startsWith('event: ')) {
                eventType = line.slice(7).trim();
              } else if (line.startsWith('data: ')) {
                dataStr += (dataStr ? '\n' : '') + line.slice(6);
              }
            }

            if (!eventType || !dataStr) continue;

            try {
              const data = JSON.parse(dataStr);

              // 根据 event 类型更新节点状态
              switch (eventType) {
                case 'execution_order':
                  // 记录本次运行 id，供节点输出预览/后端取消使用
                  if (data.run_id) {
                    setCurrentRunId(data.run_id);
                    runIdRef.current = data.run_id;
                  }
                  break;
                case 'node_start':
                  if (data.node_uuid) setNodeStatus(data.node_uuid, 'running');
                  break;
                case 'node_complete':
                  if (data.node_uuid) {
                    setNodeStatus(data.node_uuid, 'success');
                    if (typeof data.duration_ms === 'number') {
                      setNodeDuration(data.node_uuid, data.duration_ms);
                    }
                  }
                  break;
                case 'node_failed':
                  if (data.node_uuid) {
                    setNodeStatus(data.node_uuid, 'failed');
                    if (typeof data.duration_ms === 'number') {
                      setNodeDuration(data.node_uuid, data.duration_ms);
                    }
                    if (data.message) setNodeError(data.node_uuid, String(data.message));
                  }
                  break;
                // workflow_complete / workflow_failed / workflow_cancelled 不更新节点状态
              }

              // 全部事件写入执行日志（底部「执行日志」面板消费）
              const statusMap: Record<string, ExecutionLogEntry['status']> = {
                node_start: 'running',
                node_complete: 'success',
                node_failed: 'failed',
                workflow_complete: 'success',
                workflow_failed: 'failed',
              };
              appendLog({
                status: statusMap[eventType] || 'info',
                level: data.level,
                message: data.message || eventType,
                timestamp: data.timestamp || new Date().toISOString(),
                node_uuid: data.node_uuid,
                node_name: data.node_name,
                duration_ms: data.duration_ms,
              });
            } catch {
              // 忽略 JSON 解析错误
            }
          }
        }
      } catch (err: unknown) {
        if (err instanceof DOMException && err.name === 'AbortError') {
          // 用户主动取消，不视为错误
        } else {
          console.error('工作流执行出错:', err);
          appendLog({
            status: 'failed',
            message: err instanceof Error ? err.message : '运行连接中断',
            timestamp: new Date().toISOString(),
          });
        }
      } finally {
        setRunning(false);
        setRunFinishedAt(Date.now());
        abortRef.current = null;
      }
    },
    [
      setNodeStatus, setNodeDuration, setNodeError, resetStatuses, setRunning,
      setCurrentRunId, setRunStartedAt, setRunFinishedAt, appendLog, clearLogs,
    ],
  );

  const stopExecution = useCallback(() => {
    // 先通知后端取消（下一个节点边界生效），再断开 SSE 连接
    const runId = runIdRef.current;
    if (runId) {
      fetch(`/api/workflow/runs/${runId}/cancel`, { method: 'POST' }).catch(() => {});
      useFlowStore.getState().appendLog({
        status: 'info',
        message: '已请求停止（当前节点执行完后终止）',
        timestamp: new Date().toISOString(),
      });
    }
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  return { runWorkflow, stopExecution };
}
