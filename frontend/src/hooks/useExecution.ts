import { useCallback, useRef } from 'react';
import { useFlowStore } from '@/store/flowStore';

export function useExecution() {
  const { setNodeStatus, resetStatuses, setRunning } = useFlowStore();
  const abortRef = useRef<AbortController | null>(null);

  const runWorkflow = useCallback(
    async (workflowId: string) => {
      // 1. 重置所有节点状态为 pending
      resetStatuses();
      setRunning(true);

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
                case 'node_start':
                  if (data.node_uuid) setNodeStatus(data.node_uuid, 'running');
                  break;
                case 'node_complete':
                  if (data.node_uuid) setNodeStatus(data.node_uuid, 'success');
                  break;
                case 'node_failed':
                  if (data.node_uuid) setNodeStatus(data.node_uuid, 'failed');
                  break;
                // execution_order / workflow_complete / workflow_failed 不需要更新节点状态
              }
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
        }
      } finally {
        setRunning(false);
        abortRef.current = null;
      }
    },
    [setNodeStatus, resetStatuses, setRunning],
  );

  const stopExecution = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  return { runWorkflow, stopExecution };
}
