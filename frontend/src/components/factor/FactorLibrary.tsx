import type React from 'react';
import { useState, useEffect, useCallback } from 'react';
import { Card, Button, Input, Badge, Dialog, ScrollArea } from '@/components/ui';

export interface FactorItem {
  id: string;
  name: string;
  description: string;
  category: string;
  formula: string;
  code: string;
  version: number;
  created_at: number;
  updated_at: number;
}

interface FactorLibraryProps {
  onRefresh?: () => void;
}

const CATEGORY_OPTIONS = ['全部', 'momentum', 'value', 'quality', 'volatility', 'technical'];

const categoryVariant: Record<string, 'default' | 'success' | 'warning' | 'error' | 'info'> = {
  momentum: 'info',
  value: 'success',
  quality: 'warning',
  volatility: 'error',
  technical: 'default',
};

export default function FactorLibrary({ onRefresh }: FactorLibraryProps) {
  const [factors, setFactors] = useState<FactorItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('全部');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [form, setForm] = useState({ name: '', description: '', category: 'momentum', formula: '', code: '' });
  const [submitting, setSubmitting] = useState(false);

  const fetchFactors = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/factor/library');
      if (res.ok) {
        const data = await res.json() as FactorItem[];
        setFactors(data);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchFactors();
  }, [fetchFactors]);

  const filtered = factors.filter((f) => {
    const matchSearch = !search || f.name.toLowerCase().includes(search.toLowerCase()) || f.description.toLowerCase().includes(search.toLowerCase());
    const matchCategory = category === '全部' || f.category === category;
    return matchSearch && matchCategory;
  });

  const handleRegister = async () => {
    if (!form.name.trim()) return;
    setSubmitting(true);
    try {
      const res = await fetch('/api/factor/library', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      if (res.ok) {
        setDialogOpen(false);
        setForm({ name: '', description: '', category: 'momentum', formula: '', code: '' });
        await fetchFactors();
        onRefresh?.();
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      const res = await fetch(`/api/factor/library/${id}`, { method: 'DELETE' });
      if (res.ok) {
        await fetchFactors();
      }
    } catch {
      // ignore
    }
  };

  interface FactorColumn {
    key: string;
    title: string;
    dataIndex: string;
    width?: number;
    render?: (record: FactorItem) => React.ReactNode;
  }

  const columns: FactorColumn[] = [
    {
      key: 'name',
      title: '名称',
      dataIndex: 'name',
      width: 160,
      render: (record) => (
        <span className="font-medium text-[#007aff]">{record.name}</span>
      ),
    },
    {
      key: 'category',
      title: '分类',
      dataIndex: 'category',
      width: 100,
      render: (record) => (
        <Badge variant={categoryVariant[record.category] ?? 'default'}>
          {record.category || '未分类'}
        </Badge>
      ),
    },
    {
      key: 'description',
      title: '描述',
      dataIndex: 'description',
    },
    {
      key: 'created_at',
      title: '创建时间',
      dataIndex: 'created_at',
      width: 160,
      render: (record) => {
        const d = new Date(record.created_at);
        return <span className="text-xs text-[#9a9898]">{d.toLocaleDateString()}</span>;
      },
    },
    {
      key: 'actions',
      title: '操作',
      dataIndex: 'id',
      width: 80,
      render: (record) => (
        <Button variant="danger" size="sm" onClick={() => handleDelete(record.id)}>
          删除
        </Button>
      ),
    },
  ];

  return (
    <Card
      title="因子库"
      extra={
        <Button variant="primary" size="sm" onClick={() => setDialogOpen(true)}>
          注册因子
        </Button>
      }
      className={loading ? 'opacity-60' : ''}
    >
      <div className="flex flex-col gap-3">
        {/* 搜索和过滤 */}
        <div className="flex gap-2">
          <Input
            placeholder="搜索因子名称/描述..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="flex-1"
          />
          <div className="flex gap-1">
            {CATEGORY_OPTIONS.map((c) => (
              <button
                key={c}
                type="button"
                className={`rounded-[4px] border px-2 py-1 text-xs cursor-pointer transition-colors ${
                  category === c
                    ? 'border-[#007aff] bg-[#007aff]/10 text-[#007aff]'
                    : 'border-[#403b3b] bg-[#302c2c] text-[#9a9898] hover:text-[#fdfcfc]'
                }`}
                onClick={() => setCategory(c)}
              >
                {c}
              </button>
            ))}
          </div>
        </div>

        {/* 因子列表 */}
        <ScrollArea maxHeight={400}>
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="bg-[#302c2c]">
                {columns.map((col) => (
                  <th
                    key={col.key}
                    className="border-b border-[#403b3b] px-3 py-2 text-left text-xs font-medium text-[#9a9898]"
                    style={{ width: col.width }}
                  >
                    {col.title}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={columns.length} className="px-3 py-8 text-center text-[#6e6e73]">
                    暂无因子数据
                  </td>
                </tr>
              ) : (
                filtered.map((record, idx) => (
                  <tr key={record.id ?? idx} className="border-b border-[#403b3b] transition-colors hover:bg-[#363131]">
                    {columns.map((col) => (
                      <td key={col.key} className="px-3 py-2 text-[#fdfcfc]">
                        {col.render
                          ? col.render(record)
                          : String((record as unknown as Record<string, unknown>)[col.dataIndex] ?? '')}
                      </td>
                    ))}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </ScrollArea>
      </div>

      {/* 注册因子 Dialog */}
      <Dialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        title="注册因子"
        footer={
          <>
            <Button variant="secondary" onClick={() => setDialogOpen(false)}>
              取消
            </Button>
            <Button variant="primary" loading={submitting} onClick={handleRegister}>
              提交
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-[#9a9898]">因子名称 *</label>
            <Input
              placeholder="例: 5日动量因子"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-[#9a9898]">分类</label>
            <div className="flex gap-1 flex-wrap">
              {CATEGORY_OPTIONS.filter((c) => c !== '全部').map((c) => (
                <button
                  key={c}
                  type="button"
                  className={`rounded-[4px] border px-2 py-1 text-xs cursor-pointer transition-colors ${
                    form.category === c
                      ? 'border-[#007aff] bg-[#007aff]/10 text-[#007aff]'
                      : 'border-[#403b3b] bg-[#302c2c] text-[#9a9898] hover:text-[#fdfcfc]'
                  }`}
                  onClick={() => setForm({ ...form, category: c })}
                >
                  {c}
                </button>
              ))}
            </div>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-[#9a9898]">描述</label>
            <Input
              placeholder="因子描述..."
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-[#9a9898]">公式</label>
            <Input
              placeholder="因子公式..."
              value={form.formula}
              onChange={(e) => setForm({ ...form, formula: e.target.value })}
            />
          </div>
        </div>
      </Dialog>
    </Card>
  );
}
