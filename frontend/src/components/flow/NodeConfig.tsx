import { useCallback, useEffect, useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { usePlugins, type PluginNodeSchema, type SchemaProperty } from '../../hooks/usePlugins';
import { useFlowStore } from '../../store/flowStore';
import { buildWidgets, buildPorts, isConnectableInput } from '../../lib/nodeSchema';
import { resolveNodeColor } from '../../lib/nodeColors';
import { Dialog } from '../ui/Dialog';
import { Button } from '../ui/Button';
import { CodeEditor } from '../ui/CodeEditor';

const labelStyle: React.CSSProperties = {
  color: '#646262',
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

  // code_editor → 内嵌 Monaco（支持网页全屏）
  if (uiType === 'code_editor') {
    return (
      <div style={{ marginBottom: 10 }}>
        <label style={labelStyle}>{label}</label>
        <CodeEditor
          value={val}
          onChange={(v) => onChange(fieldKey, v)}
          language={prop.ui?.language || 'python'}
          height={200}
          title={label}
          fontSize={12}
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

interface SourceMeta {
  is_custom: boolean;
  class_name: string;
}

export function NodeConfig() {
  const { data: groups } = usePlugins();
  const queryClient = useQueryClient();
  const selectedNodeId = useFlowStore((s) => s.selectedNodeId);
  const nodes = useFlowStore((s) => s.nodes);
  const updateNodeData = useFlowStore((s) => s.updateNodeData);
  const selectNode = useFlowStore((s) => s.selectNode);

  // 面板当前展示的节点（与画布选中态解耦，便于处理未保存拦截）
  const [displayedNodeId, setDisplayedNodeId] = useState<string | null>(null);
  // 参数草稿：仅在点保存后才写回节点数据
  const [draftValues, setDraftValues] = useState<Record<string, unknown>>({});
  // Tab / 源码状态
  const [activeTab, setActiveTab] = useState<'params' | 'source' | 'doc'>('params');
  const [sourceCode, setSourceCode] = useState('');
  const [originalSource, setOriginalSource] = useState('');
  const [sourceMeta, setSourceMeta] = useState<SourceMeta | null>(null);
  const [sourceLoaded, setSourceLoaded] = useState(false);
  const [sourceLoading, setSourceLoading] = useState(false);
  const [sourceError, setSourceError] = useState<string | null>(null);
  // 保存状态
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  // AI 修改节点代码
  const [showNodeAI, setShowNodeAI] = useState(false);
  const [nodeAiInstruction, setNodeAiInstruction] = useState('');
  const [nodeAiLoading, setNodeAiLoading] = useState(false);
  const [nodeAiError, setNodeAiError] = useState<string | null>(null);
  // fork 后 plugins 列表刷新前的临时 schema
  const [schemaOverride, setSchemaOverride] = useState<PluginNodeSchema | null>(null);
  // 未保存拦截：待切换的目标节点（null 表示关闭面板）
  const [pendingSwitch, setPendingSwitch] = useState<{ target: string | null } | null>(null);

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

  const displayedNode = nodes.find((n) => n.id === displayedNodeId);
  const nodeType = displayedNode?.data?.nodeType as string | undefined;
  const schema: PluginNodeSchema | null =
    (nodeType ? schemaMap[nodeType] : null) ||
    (schemaOverride && schemaOverride.name === nodeType ? schemaOverride : null);
  const boxColor = resolveNodeColor((displayedNode?.data?.box_color as string) || 'orange');
  const nodeLabel = (displayedNode?.data?.label as string) || schema?.display_name || '';

  // 从 widgets 中取当前已保存值
  const widgets = (displayedNode?.data?.widgets as Array<{ name: string; value?: unknown }>) || [];
  const widgetMap = useMemo(() => {
    const m: Record<string, unknown> = {};
    for (const w of widgets) m[w.name] = w.value;
    return m;
  }, [widgets]);

  // 脏状态：参数草稿与已保存值不一致 / 源码被修改
  const paramsDirty = useMemo(
    () =>
      Object.entries(draftValues).some(
        ([k, v]) => String(v ?? '') !== String(widgetMap[k] ?? '')
      ),
    [draftValues, widgetMap]
  );
  const codeDirty = sourceLoaded && sourceCode !== originalSource;
  const isDirtyLocal = paramsDirty || codeDirty;

  // 切换展示节点并重置所有草稿
  const resetTo = useCallback((id: string | null) => {
    setDisplayedNodeId(id);
    setDraftValues({});
    setSourceCode('');
    setOriginalSource('');
    setSourceMeta(null);
    setSourceLoaded(false);
    setSourceError(null);
    setSaveError(null);
    setActiveTab('params');
  }, []);

  // 画布选中变化：有未保存修改时弹窗拦截
  useEffect(() => {
    if (selectedNodeId === displayedNodeId) return;
    if (isDirtyLocal) {
      setPendingSwitch({ target: selectedNodeId });
    } else {
      resetTo(selectedNodeId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedNodeId]);

  // 获取节点源码（打开代码 Tab 时懒加载）
  // 注意：sourceLoading 不能进依赖数组，否则 setSourceLoading(true) 会触发
  // 上一次 effect 的 cleanup（cancelled=true），导致请求结果被丢弃、永远停在加载中
  useEffect(() => {
    if (activeTab !== 'source' || !nodeType || sourceLoaded) return;
    let cancelled = false;
    setSourceLoading(true);
    setSourceError(null);
    fetch(`/api/plugins/${nodeType}/source`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data) => {
        if (!cancelled) {
          setSourceCode(data.source || '');
          setOriginalSource(data.source || '');
          setSourceMeta({
            is_custom: !!data.is_custom,
            class_name: data.class_name || nodeType,
          });
          setSourceLoaded(true);
          setSourceLoading(false);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setSourceError(e instanceof Error ? e.message : String(e));
          setSourceLoading(false);
        }
      });
    return () => { cancelled = true; };
  }, [activeTab, nodeType, sourceLoaded]);

  const handleChange = useCallback((key: string, val: unknown) => {
    setDraftValues((prev) => ({ ...prev, [key]: val }));
  }, []);

  // AI 修改节点代码：结果写入源码草稿（codeDirty），由用户审阅后点保存生效
  const handleNodeAI = useCallback(async () => {
    if (!nodeAiInstruction.trim() || !sourceLoaded) return;
    setNodeAiLoading(true);
    setNodeAiError(null);
    try {
      const res = await fetch('/api/ai/node-code', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source: sourceCode,
          instruction: nodeAiInstruction,
          node_name: nodeLabel,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(err?.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      setSourceCode(data.source || sourceCode);
      setShowNodeAI(false);
      setNodeAiInstruction('');
    } catch (e) {
      setNodeAiError(e instanceof Error ? e.message : String(e));
    } finally {
      setNodeAiLoading(false);
    }
  }, [nodeAiInstruction, sourceLoaded, sourceCode, nodeLabel]);

  // 保存：参数写回节点；代码修改则 fork 为新的自定义节点（不改内置源码）
  const doSave = useCallback(async () => {
    if (!displayedNodeId || !displayedNode) return;
    setSaving(true);
    setSaveError(null);
    try {
      if (codeDirty) {
        const isCustom = !!sourceMeta?.is_custom;
        const url = isCustom ? `/api/plugins/custom/${nodeType}` : '/api/plugins/custom';
        const body = isCustom
          ? { source: sourceCode }
          : { source: sourceCode, base_name: sourceMeta?.class_name || nodeType };
        const res = await fetch(url, {
          method: isCustom ? 'PUT' : 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => null);
          throw new Error(err?.detail || `HTTP ${res.status}`);
        }
        const newSchema: PluginNodeSchema = await res.json();
        // 用新 schema 重建 widgets/端口，保留草稿参数值
        const rebuilt = buildWidgets(newSchema).map((w) => {
          const v = draftValues[w.name] ?? widgetMap[w.name];
          return v !== undefined ? { ...w, value: v } : w;
        });
        updateNodeData(displayedNodeId, {
          nodeType: newSchema.name,
          label: newSchema.display_name,
          box_color: newSchema.box_color,
          inputs: buildPorts(newSchema, 'input'),
          outputs: buildPorts(newSchema, 'output'),
          widgets: rebuilt,
        });
        setSchemaOverride(newSchema);
        setSourceMeta({ is_custom: true, class_name: sourceMeta?.class_name || nodeType || '' });
        setOriginalSource(sourceCode);
        setDraftValues({});
        queryClient.invalidateQueries({ queryKey: ['plugins'] });
      } else if (paramsDirty) {
        const updated = widgets.map((w) =>
          w.name in draftValues ? { ...w, value: draftValues[w.name] } : w
        );
        updateNodeData(displayedNodeId, { widgets: updated });
        setDraftValues({});
      }
    } finally {
      setSaving(false);
    }
  }, [
    displayedNodeId, displayedNode, codeDirty, paramsDirty, sourceMeta, nodeType,
    sourceCode, draftValues, widgetMap, widgets, updateNodeData, queryClient,
  ]);

  const handleSaveClick = useCallback(async () => {
    try {
      await doSave();
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : String(e));
    }
  }, [doSave]);

  const handleClose = useCallback(() => {
    selectNode(null);
  }, [selectNode]);

  // 未保存弹窗操作
  const handleDiscardAndSwitch = useCallback(() => {
    if (!pendingSwitch) return;
    resetTo(pendingSwitch.target);
    setPendingSwitch(null);
  }, [pendingSwitch, resetTo]);

  const handleSaveAndSwitch = useCallback(async () => {
    if (!pendingSwitch) return;
    try {
      await doSave();
      resetTo(pendingSwitch.target);
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : String(e));
      // 保存失败：留在当前节点
      selectNode(displayedNodeId);
    }
    setPendingSwitch(null);
  }, [pendingSwitch, doSave, resetTo, selectNode, displayedNodeId]);

  const handleCancelSwitch = useCallback(() => {
    // 继续编辑：恢复画布选中态
    selectNode(displayedNodeId);
    setPendingSwitch(null);
  }, [selectNode, displayedNodeId]);

  const panelWidth = activeTab === 'source' ? 460 : activeTab === 'doc' ? 320 : 280;

  // 未选中节点
  if (!displayedNode || !schema) {
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
          {displayedNode ? '加载中...' : '选择节点查看配置'}
        </span>
        {/* 弹窗在无节点时也需渲染（如关闭面板触发） */}
        <UnsavedDialog
          open={!!pendingSwitch}
          saving={saving}
          onDiscard={handleDiscardAndSwitch}
          onSave={handleSaveAndSwitch}
          onCancel={handleCancelSwitch}
        />
      </div>
    );
  }

  const properties = schema.input_schema?.properties || {};

  return (
    <div
      style={{
        width: panelWidth,
        flexShrink: 0,
        background: '#f1eeee',
        borderLeft: '1px solid rgba(15,0,0,0.12)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        transition: 'width 0.15s ease',
      }}
    >
      {/* 顶部：节点名称 + 色条 + 保存 + 关闭 */}
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
            borderRadius: 0,
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
          title={nodeLabel}
        >
          {nodeLabel}
        </span>
        {schema.is_custom && (
          <span
            style={{
              fontSize: 10,
              color: '#007aff',
              border: '1px solid #007aff',
              borderRadius: 3,
              padding: '0 4px',
              flexShrink: 0,
            }}
          >
            自定义
          </span>
        )}
        {isDirtyLocal && (
          <button
            onClick={handleSaveClick}
            disabled={saving}
            style={{
              background: '#007aff',
              border: 'none',
              borderRadius: 4,
              color: '#fff',
              fontSize: 11,
              fontWeight: 600,
              padding: '3px 10px',
              cursor: saving ? 'not-allowed' : 'pointer',
              flexShrink: 0,
            }}
            title={codeDirty ? '保存（代码已修改，将生成新的自定义节点）' : '保存参数修改'}
          >
            {saving ? '保存中...' : '保存'}
          </button>
        )}
        <button
          onClick={handleClose}
          style={{
            background: 'none',
            border: 'none',
            color: '#646262',
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

      {/* Tab 切换栏 */}
      <div
        style={{
          display: 'flex',
          borderBottom: '1px solid rgba(15,0,0,0.12)',
          flexShrink: 0,
        }}
      >
        {([
          { key: 'params' as const, label: `参数配置${paramsDirty ? ' ●' : ''}` },
          { key: 'source' as const, label: `节点代码${codeDirty ? ' ●' : ''}` },
          { key: 'doc' as const, label: '节点说明' },
        ]).map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            style={{
              background: 'transparent',
              border: 'none',
              borderBottom: activeTab === tab.key ? '2px solid #9a9898' : '2px solid transparent',
              color: activeTab === tab.key ? '#201d1d' : '#646262',
              fontWeight: 500,
              fontSize: 12,
              fontFamily: "var(--font-mono, monospace)",
              padding: '8px 14px',
              cursor: 'pointer',
              lineHeight: 1.5,
              transition: 'color 0.15s',
            }}
          >
            {tab.label}
          </button>
        ))}
        <div style={{ flex: 1 }} />
        {/* AI 改代码小按钮 */}
        <button
          onClick={() => {
            setActiveTab('source'); // 触发源码懒加载
            setShowNodeAI(true);
          }}
          style={{
            background: 'transparent',
            border: 'none',
            color: '#7c3aed',
            fontSize: 11,
            fontWeight: 600,
            padding: '8px 10px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: 3,
          }}
          title="用 AI 修改该节点代码（需先在设置中配置 AI）"
        >
          ✦ AI
        </button>
      </div>

      {/* 保存错误提示 */}
      {saveError && (
        <div
          style={{
            color: '#ff3b30',
            fontSize: 11,
            padding: '6px 12px',
            borderBottom: '1px solid rgba(15,0,0,0.12)',
            fontFamily: "var(--font-mono, monospace)",
            whiteSpace: 'pre-wrap',
            maxHeight: 80,
            overflowY: 'auto',
          }}
        >
          保存失败: {saveError}
        </div>
      )}

      {/* 中间：参数表单 / 源码 / 节点说明 */}
      {activeTab === 'params' ? (
        <div style={{ flex: 1, overflowY: 'auto', padding: '12px 14px' }}>
          {Object.keys(properties).length === 0 ? (
            <div style={{ color: '#646262', fontSize: 12 }}>该节点无可配置参数</div>
          ) : (
            Object.entries(properties).map(([key, prop]) => (
              <ParamField
                key={key}
                fieldKey={key}
                prop={prop}
                value={key in draftValues ? draftValues[key] : widgetMap[key]}
                onChange={handleChange}
              />
            ))
          )}
        </div>
      ) : activeTab === 'doc' ? (
        <NodeDocPanel schema={schema} boxColor={boxColor} />
      ) : (
        <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          {sourceLoading && (
            <div style={{ color: '#646262', fontSize: 12, padding: '12px 14px' }}>加载中...</div>
          )}
          {sourceError && (
            <div style={{
              color: '#ff3b30',
              fontSize: 12,
              padding: '12px 14px',
              fontFamily: "var(--font-mono, monospace)",
            }}>
              加载失败: {sourceError}
            </div>
          )}
          {!sourceLoading && !sourceError && sourceLoaded && (
            <>
              <div
                style={{
                  color: '#646262',
                  fontSize: 10,
                  padding: '6px 12px',
                  borderBottom: '1px solid rgba(15,0,0,0.12)',
                  lineHeight: 1.5,
                }}
              >
                {sourceMeta?.is_custom
                  ? '自定义节点：保存后直接更新该节点代码'
                  : '内置节点：修改代码保存后会生成一个新的自定义节点（原节点不受影响）'}
              </div>
              <div style={{ flex: 1, padding: '8px 10px', minHeight: 0 }}>
                <CodeEditor
                  value={sourceCode}
                  onChange={setSourceCode}
                  language="python"
                  height="100%"
                  title={`节点代码 — ${nodeLabel}`}
                  fontSize={12}
                />
              </div>
            </>
          )}
        </div>
      )}

      {/* 底部：节点描述 */}
      <div
        style={{
          padding: '10px 14px',
          borderTop: '1px solid rgba(15,0,0,0.12)',
          flexShrink: 0,
        }}
      >
        <div style={{ color: '#646262', fontSize: 10, lineHeight: 1.5 }}>
          <span style={{ color: '#646262' }}>类型：</span>
          {schema.name}
          {schema.input_schema?.properties && (
            <>
              {' · '}
              <span style={{ color: '#646262' }}>参数：</span>
              {Object.keys(schema.input_schema.properties).length}
            </>
          )}
          {schema.output_schema?.properties && (
            <>
              {' · '}
              <span style={{ color: '#646262' }}>输出：</span>
              {Object.keys(schema.output_schema.properties).length}
            </>
          )}
        </div>
      </div>

      {/* 未保存修改确认弹窗 */}
      <UnsavedDialog
        open={!!pendingSwitch}
        saving={saving}
        onDiscard={handleDiscardAndSwitch}
        onSave={handleSaveAndSwitch}
        onCancel={handleCancelSwitch}
      />

      {/* AI 修改节点代码弹窗 */}
      <Dialog
        open={showNodeAI}
        onClose={() => !nodeAiLoading && setShowNodeAI(false)}
        title={`AI 修改节点代码 — ${nodeLabel}`}
        className="w-[520px]"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowNodeAI(false)} disabled={nodeAiLoading}>
              取消
            </Button>
            <Button
              onClick={handleNodeAI}
              loading={nodeAiLoading}
              disabled={!nodeAiInstruction.trim() || !sourceLoaded}
            >
              {nodeAiLoading ? '生成中...' : '生成修改'}
            </Button>
          </>
        }
      >
        <div style={{ fontSize: 11, color: '#646262', marginBottom: 8, lineHeight: 1.6 }}>
          描述要如何修改该节点（如“给回测加一个印花税参数，卖出时扣除”）。
          AI 修改后的代码会填入“节点代码”编辑器，
          <span style={{ color: '#ff9f0a' }}>你审阅确认后点“保存”才会生效（内置节点会 fork 为新的自定义节点，不动原节点）</span>。
        </div>
        {!sourceLoaded && (
          <div style={{ fontSize: 11, color: '#9a9898', marginBottom: 8 }}>正在加载节点源码...</div>
        )}
        {nodeAiError && (
          <div
            style={{
              color: '#ff3b30',
              fontSize: 11,
              marginBottom: 8,
              fontFamily: 'var(--font-mono, monospace)',
              whiteSpace: 'pre-wrap',
              maxHeight: 80,
              overflowY: 'auto',
            }}
          >
            {nodeAiError}
          </div>
        )}
        <textarea
          value={nodeAiInstruction}
          onChange={(e) => setNodeAiInstruction(e.target.value)}
          placeholder={'例如：\n・增加一个“最大持仓比例”参数，限制单只股票仓位\n・输出里加一个月度收益统计\n・把手续费改成双边收取'}
          rows={5}
          autoFocus
          style={{
            width: '100%',
            background: '#f8f7f7',
            border: '1px solid rgba(15,0,0,0.12)',
            borderRadius: 4,
            color: '#201d1d',
            fontSize: 12,
            padding: '8px 10px',
            outline: 'none',
            resize: 'vertical',
            lineHeight: 1.6,
            boxSizing: 'border-box',
            fontFamily: 'inherit',
          }}
        />
      </Dialog>
    </div>
  );
}

/** 节点说明面板 — 描述 / 工作流示例 / 输入输出端口 / 注意事项 */
function NodeDocPanel({ schema, boxColor }: { schema: PluginNodeSchema; boxColor: string }) {
  const inputPorts = schema.input_schema?.properties
    ? Object.entries(schema.input_schema.properties)
        .filter(([, p]) => isConnectableInput(p))
        .map(([name, p]) => ({ name, label: p.title || name }))
    : [];
  const paramFields = schema.input_schema?.properties
    ? Object.entries(schema.input_schema.properties)
        .filter(([, p]) => !isConnectableInput(p))
        .map(([name, p]) => ({ name, label: p.title || name }))
    : [];
  const outputPorts = schema.output_schema?.properties
    ? Object.entries(schema.output_schema.properties).map(([name, p]) => ({
        name,
        label: p.title || name,
      }))
    : [];

  const sectionTitle: React.CSSProperties = {
    fontSize: 11,
    fontWeight: 700,
    color: '#201d1d',
    margin: '14px 0 6px',
    paddingBottom: 4,
    borderBottom: '1px dashed rgba(15,0,0,0.16)',
  };
  const chip: React.CSSProperties = {
    display: 'inline-block',
    background: '#f1eeee',
    border: '1px solid rgba(15,0,0,0.10)',
    borderRadius: 3,
    padding: '1px 7px',
    margin: '2px 5px 2px 0',
    fontSize: 11,
    color: '#201d1d',
  };

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '12px 14px', fontSize: 12, lineHeight: 1.6 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
        <span style={{ width: 8, height: 8, background: boxColor, borderRadius: 2, flexShrink: 0 }} />
        <span style={{ color: '#646262', fontSize: 11 }}>{schema.group}</span>
        {schema.is_custom && (
          <span style={{ fontSize: 10, color: '#007aff', border: '1px solid #007aff', borderRadius: 3, padding: '0 4px' }}>
            自定义
          </span>
        )}
      </div>
      <div style={{ color: '#424245' }}>{schema.description || '暂无描述'}</div>

      {schema.example && (
        <>
          <div style={sectionTitle}>工作流示例</div>
          <div style={{ color: '#424245', fontSize: 11 }}>{schema.example}</div>
        </>
      )}

      <div style={sectionTitle}>输入端口（需连线提供）</div>
      <div>
        {inputPorts.length > 0
          ? inputPorts.map((p) => <span key={p.name} style={chip}>{p.label}</span>)
          : <span style={{ color: '#9a9898', fontSize: 11 }}>无（源节点）</span>}
      </div>

      <div style={sectionTitle}>节点参数（面板配置）</div>
      <div>
        {paramFields.length > 0
          ? paramFields.map((p) => <span key={p.name} style={chip}>{p.label}</span>)
          : <span style={{ color: '#9a9898', fontSize: 11 }}>无可配置参数</span>}
      </div>

      <div style={sectionTitle}>输出端口（可连接属性）</div>
      <div>
        {outputPorts.length > 0
          ? outputPorts.map((p) => <span key={p.name} style={chip}>{p.label}</span>)
          : <span style={{ color: '#9a9898', fontSize: 11 }}>无输出</span>}
      </div>

      {schema.notes && schema.notes.length > 0 && (
        <>
          <div style={{ ...sectionTitle, color: '#cc7f08', borderBottomColor: 'rgba(255,159,10,0.35)' }}>
            注意事项
          </div>
          <ul style={{ margin: 0, paddingLeft: 16, color: '#424245', fontSize: 11 }}>
            {schema.notes.map((n, i) => (
              <li key={i} style={{ marginBottom: 3 }}>{n}</li>
            ))}
          </ul>
        </>
      )}

      <div style={{ ...sectionTitle, color: '#646262' }}>类型标识</div>
      <div style={{ color: '#9a9898', fontSize: 11, fontFamily: 'var(--font-mono, monospace)' }}>
        {schema.name}
      </div>
    </div>
  );
}

/** 未保存修改确认弹窗 */
function UnsavedDialog({
  open,
  saving,
  onDiscard,
  onSave,
  onCancel,
}: {
  open: boolean;
  saving: boolean;
  onDiscard: () => void;
  onSave: () => void;
  onCancel: () => void;
}) {
  return (
    <Dialog
      open={open}
      onClose={onCancel}
      title="未保存的节点修改"
      footer={
        <>
          <Button variant="secondary" onClick={onCancel}>
            继续编辑
          </Button>
          <Button variant="danger" onClick={onDiscard}>
            放弃修改
          </Button>
          <Button onClick={onSave} disabled={saving}>
            {saving ? '保存中...' : '保存修改'}
          </Button>
        </>
      }
    >
      当前节点的参数或代码有未保存的修改，是否保存？
    </Dialog>
  );
}
