import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { GitBranch, FlaskConical, BarChart3, Search, Pencil, Check, X } from 'lucide-react';
import { Card, Table, Badge, Button, Input, Dialog } from '@/components/ui';
import type { Column } from '@/components/ui';

interface Experiment {
  id: string;
  source: string;
  source_id: string;
  name: string;
  note: string;
  tags: string[];
  params: Record<string, unknown>;
  metrics: Record<string, unknown>;
  status: string;
  created_at: number;
}

interface CompareResult {
  experiments: Experiment[];
  param_diffs: Record<string, unknown>;
  metric_comparison: Record<string, unknown>;
}

const sourceIcons: Record<string, typeof GitBranch> = {
  workflow: GitBranch,
  factor: FlaskConical,
  backtest: BarChart3,
  explore: Search,
};

const sourceColors: Record<string, string> = {
  workflow: '#fab283',
  factor: '#7fd88f',
  backtest: '#f5a742',
  explore: '#56b6c2',
};

const statusVariant: Record<string, 'success' | 'warning' | 'error' | 'info' | 'default'> = {
  success: 'success',
  completed: 'success',
  running: 'warning',
  failed: 'error',
  pending: 'default',
};

function formatTime(ts: number) {
  if (!ts) return '-';
  return new Date(ts * 1000).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}

export default function Experiments() {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [compareOpen, setCompareOpen] = useState(false);
  const [noteEditId, setNoteEditId] = useState<string | null>(null);
  const [noteText, setNoteText] = useState('');

  const { data: experiments = [] } = useQuery<Experiment[]>({
    queryKey: ['experiments'],
    queryFn: () => fetch('/api/experiment/').then(r => r.json()),
  });

  const { data: compareResult, mutate: compareMutate, isPending: compareLoading } = useMutation<CompareResult, Error, string[]>({
    mutationFn: (ids) =>
      fetch('/api/experiment/compare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ experiment_ids: ids }),
      }).then(r => r.json()),
    onSuccess: () => setCompareOpen(true),
  });

  const noteMutation = useMutation({
    mutationFn: ({ id, note }: { id: string; note: string }) =>
      fetch(`/api/experiment/${id}/note`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ note }),
      }).then(r => r.json()),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['experiments'] });
      setNoteEditId(null);
    },
  });

  const toggleSelect = (id: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    if (selected.size === experiments.length) setSelected(new Set());
    else setSelected(new Set(experiments.map(e => e.id)));
  };

  const handleCompare = () => {
    if (selected.size < 2) return;
    compareMutate(Array.from(selected));
  };

  const startEditNote = (exp: Experiment) => {
    setNoteEditId(exp.id);
    setNoteText(exp.note || '');
  };

  const saveNote = () => {
    if (noteEditId) noteMutation.mutate({ id: noteEditId, note: noteText });
  };

  const columns: Column<Experiment & { _selected?: boolean }>[] = [
    {
      key: 'check',
      title: (
        <input
          type="checkbox"
          checked={selected.size === experiments.length && experiments.length > 0}
          onChange={toggleAll}
          className="accent-[#fab283]"
        />
      ),
      dataIndex: 'id' as keyof Experiment,
      width: 40,
      render: (_v, record) => (
        <input
          type="checkbox"
          checked={selected.has(record.id)}
          onChange={() => toggleSelect(record.id)}
          className="accent-[#fab283]"
        />
      ),
    },
    {
      key: 'source',
      title: '来源',
      dataIndex: 'source' as keyof Experiment,
      width: 90,
      render: (val) => {
        const Icon = sourceIcons[val as string] || Search;
        const color = sourceColors[val as string] || '#808080';
        return (
          <span className="inline-flex items-center gap-1">
            <Icon size={13} style={{ color }} />
            <span className="text-xs">{val as string}</span>
          </span>
        );
      },
    },
    {
      key: 'name',
      title: '名称',
      dataIndex: 'name' as keyof Experiment,
      render: (val) => <span className="font-medium">{(val as string) || '-'}</span>,
    },
    {
      key: 'status',
      title: '状态',
      dataIndex: 'status' as keyof Experiment,
      width: 90,
      render: (val) => (
        <Badge variant={statusVariant[val as string] || 'default'}>{val as string}</Badge>
      ),
    },
    {
      key: 'created_at',
      title: '时间',
      dataIndex: 'created_at' as keyof Experiment,
      width: 120,
      render: (val) => <span className="text-xs text-[#808080]">{formatTime(val as number)}</span>,
    },
    {
      key: 'metrics',
      title: '关键指标',
      dataIndex: 'metrics' as keyof Experiment,
      render: (val) => {
        const m = val as Record<string, unknown>;
        if (!m || Object.keys(m).length === 0) return <span className="text-[#555555]">-</span>;
        return (
          <div className="flex gap-2 flex-wrap">
            {Object.entries(m).slice(0, 3).map(([k, v]) => (
              <span key={k} className="text-xs text-[#808080]">
                {k}: <span className="text-[#eeeeee]">{typeof v === 'number' ? v.toFixed(4) : String(v)}</span>
              </span>
            ))}
          </div>
        );
      },
    },
    {
      key: 'note',
      title: '备注',
      dataIndex: 'note' as keyof Experiment,
      render: (_val, record) => {
        if (noteEditId === record.id) {
          return (
            <div className="flex items-center gap-1">
              <Input
                value={noteText}
                onChange={e => setNoteText(e.target.value)}
                className="h-7 text-xs py-0.5"
                placeholder="输入备注..."
                autoFocus
              />
              <button onClick={saveNote} className="text-[#7fd88f] hover:text-[#5ec46e] cursor-pointer"><Check size={14} /></button>
              <button onClick={() => setNoteEditId(null)} className="text-[#808080] hover:text-[#eeeeee] cursor-pointer"><X size={14} /></button>
            </div>
          );
        }
        return (
          <div className="flex items-center gap-1 group">
            <span className="text-xs text-[#808080] truncate max-w-[120px]">{(record.note as string) || '-'}</span>
            <button
              onClick={() => startEditNote(record)}
              className="opacity-0 group-hover:opacity-100 text-[#808080] hover:text-[#fab283] transition-opacity cursor-pointer"
            >
              <Pencil size={12} />
            </button>
          </div>
        );
      },
    },
  ];

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-xl font-semibold text-[#eeeeee] mb-1">实验管理</h1>
          <p className="text-[13px] text-[#808080]">共 {experiments.length} 条实验记录</p>
        </div>
        <Button
          variant="primary"
          size="sm"
          disabled={selected.size < 2}
          onClick={handleCompare}
        >
          对比 ({selected.size})
        </Button>
      </div>

      <Card>
        <Table
          columns={columns}
          dataSource={experiments as (Experiment & { _selected?: boolean })[]}
          rowKey="id"
        />
      </Card>

      {/* 对比对话框 */}
      <Dialog
        open={compareOpen}
        onClose={() => setCompareOpen(false)}
        title="实验对比"
        className="max-w-[720px]"
      >
        {compareLoading ? (
          <div className="text-center py-8 text-[#808080]">加载中...</div>
        ) : compareResult ? (
          <div className="space-y-4 max-h-[60vh] overflow-auto">
            {/* 参数差异 */}
            <div>
              <h3 className="text-sm font-medium text-[#eeeeee] mb-2">参数差异</h3>
              {Object.keys(compareResult.param_diffs).length === 0 ? (
                <p className="text-xs text-[#555555]">无参数差异</p>
              ) : (
                <div className="rounded border border-[#30363d] overflow-hidden">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="bg-[#21262d]">
                        <th className="px-2 py-1.5 text-left text-[#808080] font-medium">参数</th>
                        {compareResult.experiments.map(e => (
                          <th key={e.id} className="px-2 py-1.5 text-left text-[#808080] font-medium truncate max-w-[120px]">
                            {e.name || e.id.slice(0, 8)}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(compareResult.param_diffs).map(([key, vals]) => (
                        <tr key={key} className="border-t border-[#30363d]">
                          <td className="px-2 py-1 text-[#fab283] font-mono">{key}</td>
                          {compareResult.experiments.map(e => {
                            const v = (vals as Record<string, unknown>)[e.id];
                            const isDiff = Object.values(vals as Record<string, unknown>).length > 1 &&
                              new Set(Object.values(vals as Record<string, unknown>).map(x => JSON.stringify(x))).size > 1;
                            return (
                              <td
                                key={e.id}
                                className={`px-2 py-1 font-mono ${isDiff ? 'bg-[#fab283]/10 text-[#fab283]' : 'text-[#eeeeee]'}`}
                              >
                                {v !== undefined ? JSON.stringify(v) : '-'}
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            {/* 指标对比 */}
            <div>
              <h3 className="text-sm font-medium text-[#eeeeee] mb-2">指标对比</h3>
              {Object.keys(compareResult.metric_comparison).length === 0 ? (
                <p className="text-xs text-[#555555]">无指标数据</p>
              ) : (
                <div className="rounded border border-[#30363d] overflow-hidden">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="bg-[#21262d]">
                        <th className="px-2 py-1.5 text-left text-[#808080] font-medium">指标</th>
                        {compareResult.experiments.map(e => (
                          <th key={e.id} className="px-2 py-1.5 text-left text-[#808080] font-medium truncate max-w-[120px]">
                            {e.name || e.id.slice(0, 8)}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(compareResult.metric_comparison).map(([key, vals]) => (
                        <tr key={key} className="border-t border-[#30363d]">
                          <td className="px-2 py-1 text-[#56b6c2] font-medium">{key}</td>
                          {compareResult.experiments.map(e => {
                            const v = (vals as Record<string, unknown>)[e.id];
                            return (
                              <td key={e.id} className="px-2 py-1 font-mono text-[#eeeeee]">
                                {v !== undefined ? (typeof v === 'number' ? v.toFixed(6) : JSON.stringify(v)) : '-'}
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        ) : null}
      </Dialog>
    </div>
  );
}
