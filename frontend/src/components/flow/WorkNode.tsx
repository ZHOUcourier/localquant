import { memo } from 'react';
import { Handle, Position, type NodeProps, type Node } from '@xyflow/react';
import { useFlowStore, type NodeStatus } from '../../store/flowStore';
import { NodeWidget } from './NodeWidget';

// 节点类别色映射
const BOX_COLORS: Record<string, string> = {
  orange: '#007aff',
  green: '#30d158',
  yellow: '#ff9f0a',
  '#ffd60a': '#ffd60a',
  cyan: '#64d2ff',
  red: '#ff3b30',
  black: '#9a9898',
};

// 节点状态图标
const STATUS_ICONS: Record<NodeStatus, string> = {
  pending: '○',
  running: '◉',
  success: '✓',
  failed: '✗',
};

// 状态颜色
const STATUS_COLORS: Record<NodeStatus, string> = {
  pending: '#9a9898',
  running: '#007aff',
  success: '#30d158',
  failed: '#ff3b30',
};

export interface WorkNodeData {
  label: string;
  nodeType?: string;
  box_color?: string;
  inputs?: Array<{ name: string; label: string; type?: string }>;
  outputs?: Array<{ name: string; label: string; type?: string }>;
  widgets?: Array<{ name: string; type: string; value?: unknown; options?: unknown[] }>;
  [key: string]: unknown;
}

type WorkNodeType = Node<WorkNodeData>;

function WorkNodeComponent({ id, data, selected }: NodeProps<WorkNodeType>) {
  const nodeStatuses = useFlowStore((s) => s.nodeStatuses);
  const status = nodeStatuses[id] || 'pending';

  const boxColor = BOX_COLORS[data.box_color || 'orange'] || '#007aff';
  const inputs = data.inputs || [];
  const outputs = data.outputs || [];
  const widgets = data.widgets || [];

  const statusIcon = STATUS_ICONS[status];
  const statusColor = STATUS_COLORS[status];

  // 根据运行状态决定边框和样式
  const borderColor = status === 'running'
    ? '#007aff'
    : status === 'success'
    ? '#30d158'
    : status === 'failed'
    ? '#ff3b30'
    : selected ? '#007aff' : '#403b3b';

  // 左侧色条：success 显示绿色，其他状态显示原始 boxColor
  const leftBarColor = status === 'success' ? '#30d158' : status === 'failed' ? '#ff3b30' : boxColor;

  // running 状态使用脉冲动画 className
  const nodeClassName = status === 'running' ? 'work-node work-node--running' : 'work-node';

  return (
    <div
      className={nodeClassName}
      style={{
        background: '#201d1d',
        border: `1px solid ${borderColor}`,
        borderRadius: 4,
        minWidth: 200,
        fontFamily: "var(--font-mono, monospace)",
        fontSize: 12,
        boxShadow: selected && status === 'pending'
          ? '0 0 0 1px #007aff'
          : status === 'running'
          ? '0 0 8px rgba(0,122,255,0.3)'
          : 'none',
        overflow: 'visible',
        position: 'relative',
      }}
    >
      {/* 左侧色条 */}
      <div
        style={{
          position: 'absolute',
          left: 0,
          top: 0,
          bottom: 0,
          width: 3,
          background: leftBarColor,
          borderRadius: '6px 0 0 6px',
        }}
      />

      {/* 标题栏 */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '6px 10px 6px 12px',
          borderBottom: '1px solid #403b3b',
          background: '#302c2c',
          borderRadius: '5px 5px 0 0',
        }}
      >
        <span style={{ color: '#fdfcfc', fontWeight: 600, fontSize: 12 }}>
          {data.label}
        </span>
        <span
          style={{
            color: statusColor,
            fontSize: 13,
            marginLeft: 8,
            lineHeight: 1,
          }}
          title={status}
        >
          {statusIcon}
        </span>
      </div>

      {/* 主体区域 */}
      <div
        style={{
          display: 'flex',
          minHeight: 32,
          position: 'relative',
        }}
      >
        {/* 左侧输入 Handles */}
        <div style={{ width: 10, flexShrink: 0, position: 'relative' }}>
          {inputs.map((input, i) => (
            <Handle
              key={`in-${input.name}`}
              id={input.name}
              type="target"
              position={Position.Left}
              style={{
                top: inputs.length === 1 ? '50%' : `${((i + 1) / (inputs.length + 1)) * 100}%`,
                width: 8,
                height: 8,
                background: '#007aff',
                border: '1px solid #fdfcfc',
                borderRadius: '50%',
              }}
            />
          ))}
        </div>

        {/* 输入标签 */}
        {inputs.length > 0 && (
          <div style={{ padding: '4px 4px 4px 2', minWidth: 60 }}>
            {inputs.map((input) => (
              <div
                key={`in-label-${input.name}`}
                style={{
                  color: '#9a9898',
                  fontSize: 11,
                  lineHeight: inputs.length === 1 ? undefined : '20px',
                  textAlign: 'left',
                  whiteSpace: 'nowrap',
                  ...(inputs.length === 1 ? { paddingTop: 4 } : {}),
                }}
              >
                {input.label}
              </div>
            ))}
          </div>
        )}

        {/* 中间 Widget 区域 */}
        {widgets.length > 0 && (
          <div style={{ flex: 1, padding: '4px 6px', minWidth: 100 }}>
            {widgets
              .filter((w) => w.type !== 'None')
              .map((w) => (
                <NodeWidget key={w.name} nodeId={id} widget={w} />
              ))}
          </div>
        )}

        {/* 输出标签 */}
        {outputs.length > 0 && (
          <div style={{ padding: '4px 2px 4px 4', minWidth: 50, textAlign: 'right' }}>
            {outputs.map((output) => (
              <div
                key={`out-label-${output.name}`}
                style={{
                  color: '#9a9898',
                  fontSize: 11,
                  lineHeight: outputs.length === 1 ? undefined : '20px',
                  textAlign: 'right',
                  whiteSpace: 'nowrap',
                  ...(outputs.length === 1 ? { paddingTop: 4 } : {}),
                }}
              >
                {output.label}
              </div>
            ))}
          </div>
        )}

        {/* 右侧输出 Handles */}
        <div style={{ width: 10, flexShrink: 0, position: 'relative' }}>
          {outputs.map((output, i) => (
            <Handle
              key={`out-${output.name}`}
              id={output.name}
              type="source"
              position={Position.Right}
              style={{
                top: outputs.length === 1 ? '50%' : `${((i + 1) / (outputs.length + 1)) * 100}%`,
                width: 8,
                height: 8,
                background: '#007aff',
                border: '1px solid #fdfcfc',
                borderRadius: '50%',
              }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

export const WorkNode = memo(WorkNodeComponent);
