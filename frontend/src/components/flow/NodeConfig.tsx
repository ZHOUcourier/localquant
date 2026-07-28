import { useCallback, useMemo } from 'react';
import { usePlugins, type PluginNodeSchema, type SchemaProperty } from '../../hooks/usePlugins';
import { useFlowStore } from '../../store/flowStore';

const COLOR_MAP: Record<string, string> = {
  orange: '#007aff',
  green: '#30d158',
  yellow: '#ff9f0a',
  '#ffd60a': '#ffd60a',
  cyan: '#64d2ff',
  red: '#ff3b30',
  black: '#9a9898',
};

function resolveColor(c: string) {
  return COLOR_MAP[c] || c || '#007aff';
}

const labelStyle: React.CSSProperties = {
  color: '#9a9898',
  fontSize: 11,
  marginBottom: 3,
  display: 'block',
};

const fieldInputStyle: React.CSSProperties = {
  width: '100%',
  background: '#f8f7f7',
  border: '1px solid rgba(15,0,0,0.12)',
  borderRadius: 4,
  color: '#201d1d',
  fontSize: 12,
  padding: '5px 8px',
  outline: 'none',
  fontFamily: "var(--font-mono, monospace)",
  boxSizing: 'border-box',
};

/** 单个参数表单控件 */
function ParamField({
  fieldKey,
  prop,
  value,
  onChange,
}: {
  fieldKey: string;
  prop: SchemaProperty;
  value: unknown;
  onChange: (key: string, val: unknown) => void;
}) {
  const uiType = prop.ui?.input_type || 'text_field';
  const label = prop.title || fieldKey;
  const val = String(value ?? prop.default ?? '');

  // None → 不渲染控件，提示通过连线输入
  if (uiType === 'None') {
    return (
      <div style={{ marginBottom: 10 }}>
        <label style={labelStyle}>{label}</label>
        <div
          style={{
            color: '#646262',
            fontSize: 11,
            fontStyle: 'italic',
            padding: '4px 0',
          }}
        >
          通过连线输入
        </div>
      </div>
    );
  }

  // date_picker
  if (uiType === 'date_picker') {
    return (
      <div style={{ marginBottom: 10 }}>
        <label style={labelStyle}>{label}</label>
        <input
          type="date"
          value={val}
          onChange={(e) => onChange(fieldKey, e.target.value)}
          style={fieldInputStyle}
        />
      </div>
    );
  }

  // text_field (支持多行)
  if (uiType === 'text_field') {
    const isMultiLine = (prop.ui?.max_lines ?? 0) > 1 || val.length > 60;
    if (isMultiLine) {
      return (
        <div style={{ marginBottom: 10 }}>
          <label style={labelStyle}>{label}</label>
          <textarea
            value={val}
            onChange={(e) => onChange(fieldKey, e.target.value)}
            placeholder={prop.ui?.placeholder}
            rows={3}
            style={{
              ...fieldInputStyle,
              resize: 'vertical',
              minHeight: 60,
            }}
          />
        </div>
      );
    }
    return (
      <div style={{ marginBottom: 10 }}>
        <label style={labelStyle}>{label}</label>
        <input
          type="text"
          value={val}
          onChange={(e) => onChange(fieldKey, e.target.value)}
          placeholder={prop.ui?.placeholder}
          style={fieldInputStyle}
        />
      </div>
    );
  }

  // code_editor → textarea（mini Monaco 替代）
  if (uiType === 'code_editor') {
    return (
      <div style={{ marginBottom: 10 }}>
        <label style={labelStyle}>{label}</label>
        <textarea
          value={val}
          onChange={(e) => onChange(fieldKey, e.target.value)}
          placeholder={`输入 ${prop.ui?.language || 'code'} 代码...`}
          spellCheck={false}
          style={{
            ...fieldInputStyle,
            height: 200,
            resize: 'vertical',
            lineHeight: 1.5,
            tabSize: 4,
          }}
        />
      </div>
    );
  }

  // combobox
  if (uiType === 'combobox') {
    const options = prop.ui?.options || prop.enum || [];
    return (
      <div style={{ marginBottom: 10 }}>
        <label style={labelStyle}>{label}</label>
        <select
          value={val}
          onChange={(e) => onChange(fieldKey, e.target.value)}
          style={{
            ...fieldInputStyle,
            cursor: 'pointer',
            appearance: 'none',
            paddingRight: 24,
            backgroundImage:
              "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%23808080'/%3E%3C/svg%3E\")",
            backgroundRepeat: 'no-repeat',
            backgroundPosition: 'right 8px center',
          }}
        >
          {options.map((o) => (
            <option key={String(o)} value={String(o)}>
              {String(o)}
            </option>
          ))}
        </select>
      </div>
    );
  }

  // number_field
  if (uiType === 'number_field') {
    return (
      <div style={{ marginBottom: 10 }}>
        <label style={labelStyle}>{label}</label>
        <input
          type="number"
          value={val}
          onChange={(e) => onChange(fieldKey, e.target.value)}
          style={fieldInputStyle}
        />
      </div>
    );
  }

  // stock_picker → text input
  if (uiType === 'stock_picker') {
    return (
      <div style={{ marginBottom: 10 }}>
        <label style={labelStyle}>{label}</label>
        <input
          type="text"
          value={val}
          onChange={(e) => onChange(fieldKey, e.target.value)}
          placeholder="000001.SZ,600000.SH"
          style={fieldInputStyle}
        />
      </div>
    );
  }

  // fallback → text
  return (
    <div style={{ marginBottom: 10 }}>
      <label style={labelStyle}>{label}</label>
      <input
        type="text"
        value={val}
        onChange={(e) => onChange(fieldKey, e.target.value)}
        style={fieldInputStyle}
      />
    </div>
  );
}

export function NodeConfig() {
  const { data: groups } = usePlugins();
  const selectedNodeId = useFlowStore((s) => s.selectedNodeId);
  const nodes = useFlowStore((s) => s.nodes);
  const updateNodeData = useFlowStore((s) => s.updateNodeData);
  const selectNode = useFlowStore((s) => s.selectNode);

  // 构建节点类型 → schema 映射
  const schemaMap = useMemo(() => {
    const map: Record<string, PluginNodeSchema> = {};
    if (groups) {
      for (const nodes of Object.values(groups)) {
        for (const n of nodes) {
          map[n.name] = n;
        }
      }
    }
    return map;
  }, [groups]);

  const selectedNode = nodes.find((n) => n.id === selectedNodeId);
  const nodeType = selectedNode?.data?.nodeType as string | undefined;
  const schema = nodeType ? schemaMap[nodeType] : null;
  const boxColor = resolveColor((selectedNode?.data?.box_color as string) || 'orange');

  // 从 widgets 中取当前值
  const widgets = (selectedNode?.data?.widgets as Array<{ name: string; value?: unknown }>) || [];
  const widgetMap = useMemo(() => {
    const m: Record<string, unknown> = {};
    for (const w of widgets) m[w.name] = w.value;
    return m;
  }, [widgets]);

  const handleChange = useCallback(
    (key: string, val: unknown) => {
      if (!selectedNodeId) return;
      const updated = widgets.map((w) =>
        w.name === key ? { ...w, value: val } : w
      );
      updateNodeData(selectedNodeId, { widgets: updated });
    },
    [selectedNodeId, widgets, updateNodeData]
  );

  const handleClose = useCallback(() => {
    selectNode(null);
  }, [selectNode]);

  // 未选中节点
  if (!selectedNode || !schema) {
    return (
      <div
        style={{
          width: 280,
          flexShrink: 0,
          background: '#f1eeee',
          borderLeft: '1px solid rgba(15,0,0,0.12)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <span style={{ color: '#646262', fontSize: 12 }}>
          {selectedNode ? '加载中...' : '选择节点查看配置'}
        </span>
      </div>
    );
  }

  const properties = schema.input_schema?.properties || {};

  return (
    <div
      style={{
        width: 280,
        flexShrink: 0,
        background: '#f1eeee',
        borderLeft: '1px solid rgba(15,0,0,0.12)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      {/* 顶部：节点名称 + 色条 + 关闭 */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          padding: '10px 12px',
          borderBottom: '1px solid rgba(15,0,0,0.12)',
          gap: 8,
        }}
      >
        <div
          style={{
            width: 4,
            height: 20,
            borderRadius: 2,
            background: boxColor,
            flexShrink: 0,
          }}
        />
        <span
          style={{
            color: '#201d1d',
            fontSize: 13,
            fontWeight: 600,
            flex: 1,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {schema.display_name}
        </span>
        <button
          onClick={handleClose}
          style={{
            background: 'none',
            border: 'none',
            color: '#9a9898',
            cursor: 'pointer',
            fontSize: 16,
            padding: '0 4px',
            lineHeight: 1,
          }}
          title="关闭"
        >
          ×
        </button>
      </div>

      {/* 中间：参数表单 */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 14px' }}>
        {Object.keys(properties).length === 0 ? (
          <div style={{ color: '#646262', fontSize: 12 }}>该节点无可配置参数</div>
        ) : (
          Object.entries(properties).map(([key, prop]) => (
            <ParamField
              key={key}
              fieldKey={key}
              prop={prop}
              value={widgetMap[key]}
              onChange={handleChange}
            />
          ))
        )}
      </div>

      {/* 底部：节点描述 */}
      <div
        style={{
          padding: '10px 14px',
          borderTop: '1px solid rgba(15,0,0,0.12)',
          flexShrink: 0,
        }}
      >
        <div style={{ color: '#646262', fontSize: 10, lineHeight: 1.5 }}>
          <span style={{ color: '#9a9898' }}>类型：</span>
          {schema.name}
          {schema.input_schema?.properties && (
            <>
              {' · '}
              <span style={{ color: '#9a9898' }}>参数：</span>
              {Object.keys(schema.input_schema.properties).length}
            </>
          )}
          {schema.output_schema?.properties && (
            <>
              {' · '}
              <span style={{ color: '#9a9898' }}>输出：</span>
              {Object.keys(schema.output_schema.properties).length}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
