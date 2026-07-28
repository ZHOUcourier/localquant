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
          color: '#646262',
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

  // 节点执行完成后后端回传的真实输出数据
  const outputData: Record<string, unknown>[] =
    (selectedNode?.data?.output as Record<string, unknown>[]) || [];

  if (outputData.length === 0) {
    return (
      <div
        style={{
          color: '#646262',
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
                  borderBottom: '1px solid rgba(15,0,0,0.12)',
                  color: '#646262',
                  fontWeight: 500,
                  whiteSpace: 'nowrap',
                  background: '#f1eeee',
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
                    borderBottom: '1px solid rgba(15,0,0,0.12)',
                    color: '#201d1d',
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
