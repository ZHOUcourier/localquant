import { useState, useCallback } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { Button, Input, Select } from '@/components/ui';

interface StatsData {
  count: number;
  mean: number;
  median: number;
  stddev: number;
  min: number;
  max: number;
  q25: number;
  q75: number;
}

interface CrossSectionResult {
  statistics?: {
    columns: string[];
    data: unknown[][];
    row_count: number;
  };
  histogram?: { bin: string; count: number }[];
  error?: string;
}

const fieldOptions = [
  { value: 'close', label: 'close' },
  { value: 'volume', label: 'volume' },
  { value: 'amount', label: 'amount' },
];

export function CrossSection() {
  const [date, setDate] = useState('');
  const [field, setField] = useState('close');
  const [result, setResult] = useState<CrossSectionResult | null>(null);
  const [loading, setLoading] = useState(false);

  const analyze = useCallback(async () => {
    if (!date.trim()) return;
    setLoading(true);
    try {
      const res = await fetch('/api/explorer/cross-section', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ date, field }),
      });
      const data: CrossSectionResult = await res.json();
      setResult(data);
    } catch (err) {
      setResult({ error: String(err) });
    } finally {
      setLoading(false);
    }
  }, [date, field]);

  // Parse statistics from result
  let stats: StatsData | null = null;
  if (result?.statistics?.data?.[0]) {
    const cols = result.statistics.columns;
    const row = result.statistics.data[0];
    const get = (key: string) => {
      const idx = cols.indexOf(key);
      return idx >= 0 ? Number(row[idx]) : 0;
    };
    stats = {
      count: get('count'),
      mean: get('mean'),
      median: get('median'),
      stddev: get('stddev'),
      min: get('min'),
      max: get('max'),
      q25: get('q25'),
      q75: get('q75'),
    };
  }

  const histogramData = result?.histogram ?? [];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-end gap-3">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-[#9a9898]">日期</label>
          <Input
            placeholder="2024-01-02"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="w-40"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-[#9a9898]">字段</label>
          <Select
            options={fieldOptions}
            value={field}
            onChange={setField}
            className="w-32"
          />
        </div>
        <Button variant="primary" onClick={analyze} loading={loading}>
          分析
        </Button>
      </div>

      {result?.error && (
        <div className="rounded-[4px] border border-[#ff3b30]/30 bg-[#ff3b30]/10 px-3 py-2 text-sm text-[#ff3b30]">
          {result.error}
        </div>
      )}

      {stats && (
        <div className="grid grid-cols-5 gap-3">
          {[
            { label: '均值', value: stats.mean },
            { label: '中位数', value: stats.median },
            { label: '标准差', value: stats.stddev },
            { label: '最大值', value: stats.max },
            { label: '最小值', value: stats.min },
          ].map((item) => (
            <div
              key={item.label}
              className="rounded-[4px] border border-[#403b3b] bg-[#262222] px-3 py-3"
            >
              <div className="text-xs text-[#9a9898] mb-1">{item.label}</div>
              <div className="text-lg font-mono text-[#fdfcfc]">
                {Number.isFinite(item.value) ? item.value.toFixed(4) : '-'}
              </div>
            </div>
          ))}
        </div>
      )}

      {stats && (
        <div className="grid grid-cols-3 gap-3">
          {[
            { label: '样本数', value: stats.count },
            { label: 'Q25', value: stats.q25 },
            { label: 'Q75', value: stats.q75 },
          ].map((item) => (
            <div
              key={item.label}
              className="rounded-[4px] border border-[#403b3b] bg-[#262222] px-3 py-3"
            >
              <div className="text-xs text-[#9a9898] mb-1">{item.label}</div>
              <div className="text-lg font-mono text-[#fdfcfc]">
                {Number.isFinite(item.value) ? item.value.toFixed(4) : '-'}
              </div>
            </div>
          ))}
        </div>
      )}

      {histogramData.length > 0 && (
        <div className="rounded-[4px] border border-[#403b3b] bg-[#262222] p-4">
          <div className="text-sm text-[#9a9898] mb-3">分布直方图</div>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={histogramData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#403b3b" />
              <XAxis
                dataKey="bin"
                tick={{ fill: '#9a9898', fontSize: 11 }}
                axisLine={{ stroke: '#403b3b' }}
              />
              <YAxis
                tick={{ fill: '#9a9898', fontSize: 11 }}
                axisLine={{ stroke: '#403b3b' }}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#262222',
                  border: '1px solid #403b3b',
                  borderRadius: '4px',
                  color: '#fdfcfc',
                }}
              />
              <Bar dataKey="count" fill="#007aff" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
