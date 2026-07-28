import { memo } from 'react';
import { Handle, Position, type NodeProps, type Node } from '@xyflow/react';
import { useFlowStore, type NodeStatus } from '../../store/flowStore';
import { NodeWidget } from './NodeWidget';

// 节点类别色映射
const BOX_COLORS: Record<string, string> = {
  orange: '#fab283',
  green: '#7fd88f',
  yellow: '#f5a742',
  '#e5c07b': '#e5c07b',
  cyan: '#56b6c2',
  red: '#e06c75',
  black: '#808080',
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
  pending: '#808080',
  running: '#fab283',
  success: '#7fd88f',
  failed: '#e06c75',
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

  const boxColor = BOX_COLORS[data.box_color || 'orange'] || '#fab283';
  const inputs = data.inputs || [];
  const outputs = data.outputs || [];
  const widgets = data.widgets || [];

  const statusIcon = STATUS_ICONS[status];
  const statusColor = STATUS_COLORS[status];

  // 根据运行状态决定边框和样式
  const borderColor = status === 'running'
    ? '#fab283'
    : status === 'success'
    ? '#7fd88f'
    : status === 'failed'
    ? '#e06c75'
    : selected ? '#fab283' : '#30363d';

  // 左侧色条：success 显示绿色，其他状态显示原始 boxColor
  const leftBarColor = status === 'success' ? '#7fd88f' : status === 'failed' ? '#e06c75' : boxColor;

  // running 状态使用脉冲动画 className
  const nodeClassName = status === 'running' ? 'work-node work-node--running' : 'work-node';

  return (
    <div
      className={nodeClassName}
      style={{
        background: '#161b22',
        border: `1px solid ${borderColor}`,
        borderRadius: 6,
        minWidth: 200,
        fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
        fontSize: 12,
        boxShadow: selected && status === 'pending'
          ? '0 0 0 1px #fab283'
          : status === 'running'
          ? '0 0 8px rgba(250,178,131,0.3)'
          : '0 2px 8px rgba(0,0,0,0.4)',
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
          borderBottom: '1px solid #30363d',
          background: '#21262d',
          borderRadius: '5px 5px 0 0',
        }}
      >
        <span style={{ color: '#eeeeee', fontWeight: 600, fontSize: 12 }}>
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
                background: '#fab283',
                border: '1px solid #0a0a0a',
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
                  color: '#808080',
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
                  color: '#808080',
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
                background: '#fab283',
                border: '1px solid #0a0a0a',
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
