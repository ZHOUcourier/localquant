import { memo, useCallback } from 'react';
import { useFlowStore } from '../../store/flowStore';

interface WidgetDef {
  name: string;
  type: string;
  value?: unknown;
  options?: unknown[];
}

interface NodeWidgetProps {
  nodeId: string;
  widget: WidgetDef;
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  height: 24,
  background: '#201d1d',
  border: '1px solid #403b3b',
  borderRadius: 3,
  color: '#fdfcfc',
  fontSize: 11,
  padding: '2px 6px',
  outline: 'none',
  fontFamily: "var(--font-mono, monospace)",
  boxSizing: 'border-box' as const,
};

function NodeWidgetComponent({ nodeId, widget }: NodeWidgetProps) {
  const updateNodeData = useFlowStore((s) => s.updateNodeData);
  const nodes = useFlowStore((s) => s.nodes);
  const node = nodes.find((n) => n.id === nodeId);
  const widgets: WidgetDef[] = (node?.data?.widgets as WidgetDef[]) || [];
  const idx = widgets.findIndex((w) => w.name === widget.name);

  const handleChange = useCallback(
    (val: string) => {
      if (idx < 0) return;
      const updated = [...widgets];
      updated[idx] = { ...updated[idx], value: val };
      updateNodeData(nodeId, { widgets: updated });
    },
    [nodeId, idx, widgets, updateNodeData]
  );

  const val = String(widget.value ?? '');

  // None 类型不渲染
  if (widget.type === 'None') return null;

  // code_editor → "点击编辑" 按钮
  if (widget.type === 'code_editor') {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 4,
          padding: '1px 0',
        }}
      >
        <span style={{ color: '#9a9898', fontSize: 10, flexShrink: 0 }}>{widget.name}</span>
        <button
          style={{
            background: '#302c2c',
            border: '1px solid #403b3b',
            borderRadius: 3,
            color: '#9a9898',
            fontSize: 10,
            padding: '2px 6px',
            cursor: 'pointer',
            whiteSpace: 'nowrap',
          }}
          title="在右侧面板编辑代码"
        >
          点击编辑
        </button>
      </div>
    );
  }

  // combobox
  if (widget.type === 'combobox') {
    const opts = (widget.options || []) as string[];
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 4,
          padding: '1px 0',
        }}
      >
        <span style={{ color: '#9a9898', fontSize: 10, flexShrink: 0, minWidth: 36 }}>
          {widget.name}
        </span>
        <select
          value={val}
          onChange={(e) => handleChange(e.target.value)}
          style={{
            ...inputStyle,
            flex: 1,
            cursor: 'pointer',
            appearance: 'none',
            paddingRight: 16,
            backgroundImage:
              "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%23808080'/%3E%3C/svg%3E\")",
            backgroundRepeat: 'no-repeat',
            backgroundPosition: 'right 4px center',
          }}
        >
          {opts.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      </div>
    );
  }

  // date_picker
  if (widget.type === 'date_picker') {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 4,
          padding: '1px 0',
        }}
      >
        <span style={{ color: '#9a9898', fontSize: 10, flexShrink: 0, minWidth: 36 }}>
          {widget.name}
        </span>
        <input
          type="date"
          value={val}
          onChange={(e) => handleChange(e.target.value)}
          style={{
            ...inputStyle,
            flex: 1,
            colorScheme: 'dark',
          }}
        />
      </div>
    );
  }

  // number_field
  if (widget.type === 'number_field') {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 4,
          padding: '1px 0',
        }}
      >
        <span style={{ color: '#9a9898', fontSize: 10, flexShrink: 0, minWidth: 36 }}>
          {widget.name}
        </span>
        <input
          type="number"
          value={val}
          onChange={(e) => handleChange(e.target.value)}
          style={{ ...inputStyle, flex: 1 }}
        />
      </div>
    );
  }

  // default: text_field / stock_picker / unknown → text input
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 4,
        padding: '1px 0',
      }}
    >
      <span style={{ color: '#9a9898', fontSize: 10, flexShrink: 0, minWidth: 36 }}>
        {widget.name}
      </span>
      <input
        type="text"
        value={val}
        onChange={(e) => handleChange(e.target.value)}
        placeholder={widget.type === 'stock_picker' ? '股票代码' : undefined}
        style={{ ...inputStyle, flex: 1 }}
      />
    </div>
  );
}

export const NodeWidget = memo(NodeWidgetComponent);
