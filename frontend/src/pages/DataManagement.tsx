import { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { Wifi, WifiOff, Database, Download, ShieldCheck, Loader2 } from 'lucide-react';
import { Card, Button, Input, Select, Badge, Dialog } from '@/components/ui';

interface DataStatus {
  qmt_connected?: boolean;
  qmt_path?: string;
  qmt_data_dir?: string;
  cache_count?: number;
  cache_size?: string;
  total_records?: number;
  [key: string]: unknown;
}

interface QualityResult {
  passed?: boolean;
  issues?: string[];
  summary?: string;
  [key: string]: unknown;
}

const periodOptions = [
  { value: '1d', label: '日线' },
  { value: '1m', label: '1分钟' },
  { value: '5m', label: '5分钟' },
  { value: '15m', label: '15分钟' },
  { value: '30m', label: '30分钟' },
  { value: '60m', label: '60分钟' },
  { value: 'tick', label: 'Tick' },
];

export default function DataManagement() {
  const [symbol, setSymbol] = useState('');
  const [period, setPeriod] = useState('1d');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [qualityOpen, setQualityOpen] = useState(false);

  const { data: status, refetch: refetchStatus } = useQuery<DataStatus>({
    queryKey: ['data-status'],
    queryFn: () => fetch('/api/data/status').then(r => r.json()),
  });

  const downloadMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch('/api/data/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol, period, start_date: startDate, end_date: endDate }),
      });
      const body = await res.json().catch(() => null);
      if (!res.ok) {
        throw new Error(body?.detail ?? `下载接口错误 (HTTP ${res.status})`);
      }
      return body as { status: string; symbol: string; rows: number };
    },
    onSuccess: () => {
      refetchStatus();
    },
  });

  const qualityMutation = useMutation<QualityResult>({
    mutationFn: () =>
      fetch('/api/data/quality-check', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }).then(r => r.json()),
    onSuccess: () => setQualityOpen(true),
  });

  return (
    <div>
      <div className="mb-4">
        <h1 className="text-xl font-semibold text-[#201d1d] mb-1">数据管理</h1>
        <p className="text-[13px] text-[#646262]">管理 QMT 数据源连接与本地缓存</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* QMT 连接状态 */}
        <Card title="QMT 连接状态">
          <div className="flex flex-col items-center py-4 gap-3">
            <div className="relative">
              <div
                className={`w-12 h-12 rounded-full flex items-center justify-center ${
                  status?.qmt_connected ? 'bg-[#30d158]/15' : 'bg-[#ff3b30]/15'
                }`}
              >
                {status?.qmt_connected ? (
                  <Wifi size={24} className="text-[#30d158]" />
                ) : (
                  <WifiOff size={24} className="text-[#ff3b30]" />
                )}
              </div>
              <span
                className={`absolute -top-0.5 -right-0.5 w-3.5 h-3.5 rounded-full border-2 border-[#f1eeee] ${
                  status?.qmt_connected ? 'bg-[#30d158]' : 'bg-[#ff3b30]'
                }`}
              />
            </div>
            <div className="text-center">
              <div className={`text-sm font-medium mb-1 ${status?.qmt_connected ? 'text-[#30d158]' : 'text-[#ff3b30]'}`}>
                {status?.qmt_connected ? '已连接' : '未连接'}
              </div>
              {status?.qmt_path && (
                <div className="text-xs text-[#646262] font-mono truncate max-w-[200px]">{status.qmt_path}</div>
              )}
              {status?.qmt_data_dir && (
                <div className="text-xs text-[#646262] font-mono truncate max-w-[200px]">{status.qmt_data_dir}</div>
              )}
            </div>
          </div>
        </Card>

        {/* 缓存统计 */}
        <Card title="缓存统计">
          <div className="space-y-3 py-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Database size={15} className="text-[#64d2ff]" />
                <span className="text-sm text-[#201d1d]">已缓存品种</span>
              </div>
              <span className="text-sm font-mono text-[#007aff]">{status?.cache_count ?? 0}</span>
            </div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Database size={15} className="text-[#64d2ff]" />
                <span className="text-sm text-[#201d1d]">数据总量</span>
              </div>
              <span className="text-sm font-mono text-[#007aff]">{status?.total_records?.toLocaleString() ?? '0'} 条</span>
            </div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Database size={15} className="text-[#64d2ff]" />
                <span className="text-sm text-[#201d1d]">磁盘占用</span>
              </div>
              <span className="text-sm font-mono text-[#007aff]">{status?.cache_size ?? '0 MB'}</span>
            </div>
          </div>
        </Card>

        {/* 数据质量 */}
        <Card title="数据质量">
          <div className="flex flex-col items-center justify-center py-6 gap-3">
            <ShieldCheck size={32} className="text-[#64d2ff]" />
            <p className="text-xs text-[#646262] text-center">运行数据质量检查，验证缓存数据完整性</p>
            <Button
              variant="secondary"
              size="sm"
              loading={qualityMutation.isPending}
              onClick={() => qualityMutation.mutate()}
            >
              运行检查
            </Button>
          </div>
        </Card>
      </div>

      {/* 数据下载 */}
      <Card title="数据下载" className="mt-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 items-end">
          <div>
            <label className="block text-xs text-[#646262] mb-1">品种代码</label>
            <Input
              value={symbol}
              onChange={e => setSymbol(e.target.value)}
              placeholder="如: 000001.SZ"
            />
          </div>
          <div>
            <label className="block text-xs text-[#646262] mb-1">周期</label>
            <Select options={periodOptions} value={period} onChange={setPeriod} />
          </div>
          <div>
            <label className="block text-xs text-[#646262] mb-1">开始日期</label>
            <Input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} />
          </div>
          <div>
            <label className="block text-xs text-[#646262] mb-1">结束日期</label>
            <Input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} />
          </div>
          <Button
            variant="primary"
            disabled={!symbol}
            loading={downloadMutation.isPending}
            onClick={() => downloadMutation.mutate()}
          >
            <Download size={14} className="mr-1" />
            下载
          </Button>
        </div>

        {/* 下载状态（真实结果，非模拟进度） */}
        {downloadMutation.isPending && (
          <div className="mt-3 flex items-center gap-2 text-xs text-[#646262]">
            <Loader2 size={13} className="animate-spin" />
            正在从 QMT 下载 {symbol} ({period}) 数据...
          </div>
        )}
        {downloadMutation.isError && (
          <div className="mt-3 rounded-[4px] border border-[#ff3b30] bg-[#ff3b30]/10 px-3 py-2 font-mono text-xs text-[#ff3b30]">
            {downloadMutation.error instanceof Error ? downloadMutation.error.message : '下载失败'}
          </div>
        )}
        {downloadMutation.isSuccess && (
          <div className="mt-3 rounded-[4px] border border-[#30d158] bg-[#30d158]/10 px-3 py-2 font-mono text-xs text-[#30d158]">
            下载完成: {downloadMutation.data?.symbol} 共 {downloadMutation.data?.rows} 条数据已写入本地缓存
          </div>
        )}
      </Card>

      {/* 质量检查结果对话框 */}
      <Dialog
        open={qualityOpen}
        onClose={() => setQualityOpen(false)}
        title="数据质量检查结果"
      >
        {qualityMutation.data ? (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <Badge variant={qualityMutation.data.passed ? 'success' : 'warning'}>
                {qualityMutation.data.passed ? '通过' : '存在问题'}
              </Badge>
              {qualityMutation.data.summary && (
                <span className="text-xs text-[#646262]">{qualityMutation.data.summary}</span>
              )}
            </div>
            {qualityMutation.data.issues && qualityMutation.data.issues.length > 0 && (
              <ul className="space-y-1">
                {qualityMutation.data.issues.map((issue, i) => (
                  <li key={i} className="text-xs text-[#ff3b30] flex items-start gap-1">
                    <span className="mt-0.5">•</span>
                    <span>{issue}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ) : (
          <div className="flex items-center justify-center py-4 gap-2 text-[#646262]">
            <Loader2 size={14} className="animate-spin" />
            检查中...
          </div>
        )}
      </Dialog>
    </div>
  );
}
