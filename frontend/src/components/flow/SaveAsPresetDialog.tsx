/**
 * SaveAsPresetDialog — 右键节点「另存为新节点预设」
 *
 * 把画布上某个节点的源码另存为一个新的自定义节点预设，出现在左侧节点面板中。
 * 类目可从现有分组中选择，也可以新建类目。
 */
import { useCallback, useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { usePlugins } from '../../hooks/usePlugins';
import { Dialog } from '../ui/Dialog';
import { Button } from '../ui/Button';

interface SaveAsPresetDialogProps {
  open: boolean;
  onClose: () => void;
  /** 节点类型（注册名） */
  nodeType: string | null;
  /** 节点当前显示名 */
  nodeLabel: string;
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  background: '#f8f7f7',
  border: '1px solid rgba(15,0,0,0.12)',
  borderRadius: 4,
  color: '#201d1d',
  fontSize: 12,
  padding: '6px 10px',
  outline: 'none',
  fontFamily: 'inherit',
  boxSizing: 'border-box',
};

const labelStyle: React.CSSProperties = {
  color: '#646262',
  fontSize: 11,
  marginBottom: 4,
  display: 'block',
};

export function SaveAsPresetDialog({ open, onClose, nodeType, nodeLabel }: SaveAsPresetDialogProps) {
  const { data: groups } = usePlugins();
  const queryClient = useQueryClient();
  const [displayName, setDisplayName] = useState('');
  const [group, setGroup] = useState('');
  const [newGroup, setNewGroup] = useState('');
  const [useNewGroup, setUseNewGroup] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const groupNames = groups ? Object.keys(groups) : [];

  useEffect(() => {
    if (open) {
      setDisplayName(`${nodeLabel}（预设）`);
      setGroup(groupNames.includes('99-自定义节点') ? '99-自定义节点' : groupNames[0] || '');
      setNewGroup('');
      setUseNewGroup(false);
      setError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, nodeLabel]);

  const handleSave = useCallback(async () => {
    if (!nodeType) return;
    const targetGroup = useNewGroup ? newGroup.trim() : group;
    if (!targetGroup) {
      setError('请选择或输入类目');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      // 1. 取节点当前源码
      const srcRes = await fetch(`/api/plugins/${nodeType}/source`);
      if (!srcRes.ok) throw new Error('获取节点源码失败');
      const srcData = await srcRes.json();

      // 2. 另存为新的自定义节点预设（不影响原节点）
      const res = await fetch('/api/plugins/custom', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source: srcData.source,
          base_name: srcData.class_name,
          display_name: displayName.trim() || `${nodeLabel}（预设）`,
          group: targetGroup,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(err?.detail || `HTTP ${res.status}`);
      }
      await queryClient.invalidateQueries({ queryKey: ['plugins'] });
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }, [nodeType, nodeLabel, displayName, group, newGroup, useNewGroup, queryClient, onClose]);

  return (
    <Dialog
      open={open}
      onClose={() => !saving && onClose()}
      title="另存为新节点预设"
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={saving}>
            取消
          </Button>
          <Button onClick={handleSave} loading={saving}>
            保存到侧边栏
          </Button>
        </>
      }
    >
      <div style={{ fontSize: 11, color: '#646262', marginBottom: 12, lineHeight: 1.6 }}>
        将该节点的当前实现另存为一个新预设，保存后会出现在左侧节点面板的所选类目中，
        原节点不受影响。
      </div>
      {error && (
        <div style={{ color: '#ff3b30', fontSize: 11, marginBottom: 8, whiteSpace: 'pre-wrap' }}>
          {error}
        </div>
      )}
      <div style={{ marginBottom: 12 }}>
        <label style={labelStyle}>预设名称</label>
        <input
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          style={inputStyle}
          autoFocus
        />
      </div>
      <div style={{ marginBottom: 8 }}>
        <label style={labelStyle}>保存类目</label>
        {!useNewGroup ? (
          <select
            value={group}
            onChange={(e) => setGroup(e.target.value)}
            style={{ ...inputStyle, cursor: 'pointer' }}
          >
            {groupNames.map((g) => (
              <option key={g} value={g}>{g}</option>
            ))}
          </select>
        ) : (
          <input
            value={newGroup}
            onChange={(e) => setNewGroup(e.target.value)}
            placeholder="输入新类目名，如 12-我的策略"
            style={inputStyle}
          />
        )}
      </div>
      <button
        onClick={() => setUseNewGroup((v) => !v)}
        style={{
          background: 'none',
          border: 'none',
          color: '#007aff',
          fontSize: 11,
          cursor: 'pointer',
          padding: 0,
          fontFamily: 'inherit',
        }}
      >
        {useNewGroup ? '← 从现有类目中选择' : '＋ 新建类目'}
      </button>
    </Dialog>
  );
}
