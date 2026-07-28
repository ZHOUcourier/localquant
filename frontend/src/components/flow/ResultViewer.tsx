import React from 'react';
import { useFlowStore } from '@/store/flowStore';
import { ScrollArea } from '@/components/ui/ScrollArea';

export const ResultViewer: React.FC = () => {
  const selectedNodeId = useFlowStore((s) => s.selectedNodeId);
  const nodeStatuses = useFlowStore((s) => s.nodeStatuses);
  const nodes = useFlowStore((s) => s.nodes);

  // 检查选中节点是否已完成
  const selectedStatus = selectedNodeId ? nodeStatuses[selectedNodeId] : null;
  const selectedNode = nodes.find((n) => n.id === selectedNodeId);

  if (!selectedNodeId || selectedStatus !== 'success') {
    return (
      <div
        style={{
          color: '#555',
          fontSize: 12,
          padding: 16,
          fontFamily: 'monospace',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
        }}
      >
        点击已完成的节点查看输出
      </div>
    );
  }

  // 模拟输出数据（后续从后端/API获取）
  const outputData: Record<string, unknown>[] =
    (selectedNode?.data?.output as Record<string, unknown>[]) || [];

  if (outputData.length === 0) {
    return (
      <div
        style={{
          color: '#555',
          fontSize: 12,
          padding: 16,
          fontFamily: 'monospace',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
        }}
      >
        该节点暂无输出数据
      </div>
    );
  }

  const columns = Object.keys(outputData[0] || {});

  return (
    <ScrollArea maxHeight={200}>
      <table
        style={{
          width: '100%',
          borderCollapse: 'collapse',
          fontFamily: 'monospace',
          fontSize: 12,
        }}
      >
        <thead>
          <tr>
            {columns.map((col) => (
              <th
                key={col}
                style={{
                  padding: '4px 12px',
                  textAlign: 'left',
                  borderBottom: '1px solid #30363d',
                  color: '#808080',
                  fontWeight: 500,
                  whiteSpace: 'nowrap',
                  background: '#161b22',
                  position: 'sticky',
                  top: 0,
                }}
              >
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {outputData.map((row, rowIdx) => (
            <tr key={rowIdx}>
              {columns.map((col) => (
                <td
                  key={col}
                  style={{
                    padding: '3px 12px',
                    borderBottom: '1px solid #21262d',
                    color: '#c9d1d9',
                    whiteSpace: 'nowrap',
                    maxWidth: 300,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}
                >
                  {row[col] != null ? String(row[col]) : '-'}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </ScrollArea>
  );
};
