import { useState, useCallback } from 'react';
import { Button, Input, Select } from '@/components/ui';

interface AnomalyResult {
  anomalies?: {
    columns: string[];
    data: unknown[][];
    row_count: number;
  };
  error?: string;
  code?: string;
  field?: string;
}

const fieldOptions = [
  { value: 'close', label: 'close' },
  { value: 'volume', label: 'volume' },
  { value: 'amount', label: 'amount' },
];

export function AnomalyDetector() {
  const [code, setCode] = useState('');
  const [field, setField] = useState('close');
  const [window, setWindow] = useState('20');
  const [threshold, setThreshold] = useState('2.0');
  const [result, setResult] = useState<AnomalyResult | null>(null);
  const [loading, setLoading] = useState(false);

  const detect = useCallback(async () => {
    if (!code.trim()) return;
    setLoading(true);
    try {
      const res = await fetch('/api/explorer/anomaly', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code,
          field,
          window: Number(window) || 20,
          threshold: Number(threshold) || 2.0,
        }),
      });
      const data: AnomalyResult = await res.json();
      setResult(data);
    } catch (err) {
      setResult({ error: String(err) });
    } finally {
      setLoading(false);
    }
  }, [code, field, window, threshold]);

  const anomalyData = result?.anomalies;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-end gap-3 flex-wrap">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-[#646262]">股票代码</label>
          <Input
            placeholder="000001.SH"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            className="w-40"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-[#646262]">字段</label>
          <Select
            options={fieldOptions}
            value={field}
            onChange={setField}
            className="w-28"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-[#646262]">窗口大小</label>
          <Input
            type="number"
            value={window}
            onChange={(e) => setWindow(e.target.value)}
            className="w-24"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-[#646262]">阈值</label>
          <Input
            type="number"
            step="0.1"
            value={threshold}
            onChange={(e) => setThreshold(e.target.value)}
            className="w-24"
          />
        </div>
        <Button variant="primary" onClick={detect} loading={loading}>
          检测
        </Button>
      </div>

      {result?.error && (
        <div className="rounded-[4px] border border-[#ff3b30]/30 bg-[#ff3b30]/10 px-3 py-2 text-sm text-[#ff3b30]">
          {result.error}
        </div>
      )}

      {anomalyData && anomalyData.columns.length > 0 && (
        <>
          <div className="text-xs text-[#646262]">
            检测到 {anomalyData.row_count} 个异常值（{result.code} / {result.field}）
          </div>
          <div className="rounded-[4px] border border-[rgba(15,0,0,0.12)] overflow-auto max-h-[500px]">
            <table className="w-full border-collapse text-sm">
              <thead className="sticky top-0 z-10">
                <tr className="bg-[#f8f7f7]">
                  <th className="border-b border-[rgba(15,0,0,0.12)] px-3 py-2 text-left text-xs font-medium text-[#646262] w-10">
                    #
                  </th>
                  {anomalyData.columns.map((col) => (
                    <th
                      key={col}
                      className="border-b border-[rgba(15,0,0,0.12)] px-3 py-2 text-left text-xs font-medium text-[#646262] whitespace-nowrap"
                    >
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {anomalyData.data.map((row, ri) => (
                  <tr key={ri} className="border-b border-[rgba(15,0,0,0.12)] hover:bg-[#f1eeee] transition-colors">
                    <td className="px-3 py-1.5 text-xs text-[#646262]">{ri + 1}</td>
                    {row.map((val, ci) => {
                      const colName = anomalyData.columns[ci];
                      const isZScore = colName === 'z_score';
                      return (
                        <td
                          key={ci}
                          className={`px-3 py-1.5 whitespace-nowrap font-mono text-xs ${
                            isZScore ? 'text-[#ff3b30]' : 'text-[#201d1d]'
                          }`}
                        >
                          {val === null ? (
                            <span className="text-[#9a9898]">NULL</span>
                          ) : typeof val === 'number' ? (
                            val.toFixed(4)
                          ) : (
                            String(val)
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {result && anomalyData && anomalyData.row_count === 0 && !result.error && (
        <div className="text-sm text-[#646262] py-8 text-center">未检测到异常值</div>
      )}
    </div>
  );
}
