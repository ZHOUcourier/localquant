import { useState, useCallback } from 'react';
import { Button, Input } from '@/components/ui';

interface ScanResult {
  columns: string[];
  data: unknown[][];
  row_count: number;
  error?: string;
}

export function MarketScanner() {
  const [date, setDate] = useState('');
  const [conditions, setConditions] = useState('close > 10');
  const [result, setResult] = useState<ScanResult | null>(null);
  const [loading, setLoading] = useState(false);

  const scan = useCallback(async () => {
    if (!date.trim()) return;
    setLoading(true);
    try {
      const conditionList = conditions
        .split(';')
        .map((s) => s.trim())
        .filter(Boolean);
      const res = await fetch('/api/explorer/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ date, conditions: conditionList }),
      });
      const data: ScanResult = await res.json();
      setResult(data);
    } catch (err) {
      setResult({ columns: [], data: [], row_count: 0, error: String(err) });
    } finally {
      setLoading(false);
    }
  }, [date, conditions]);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-end gap-3">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-[#808080]">日期</label>
          <Input
            placeholder="2024-01-02"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="w-40"
          />
        </div>
        <div className="flex flex-col gap-1 flex-1">
          <label className="text-xs text-[#808080]">筛选条件（多条用分号分隔）</label>
          <Input
            placeholder="close > 10"
            value={conditions}
            onChange={(e) => setConditions(e.target.value)}
          />
        </div>
        <Button variant="primary" onClick={scan} loading={loading}>
          扫描
        </Button>
      </div>

      {result?.error && (
        <div className="rounded-[4px] border border-[#e06c75]/30 bg-[#e06c75]/10 px-3 py-2 text-sm text-[#e06c75]">
          {result.error}
        </div>
      )}

      {result && result.columns.length > 0 && (
        <>
          <div className="text-xs text-[#808080]">共 {result.row_count} 条结果</div>
          <div className="rounded-[4px] border border-[#30363d] overflow-auto max-h-[500px]">
            <table className="w-full border-collapse text-sm">
              <thead className="sticky top-0 z-10">
                <tr className="bg-[#21262d]">
                  <th className="border-b border-[#30363d] px-3 py-2 text-left text-xs font-medium text-[#808080] w-10">
                    #
                  </th>
                  {result.columns.map((col) => (
                    <th
                      key={col}
                      className="border-b border-[#30363d] px-3 py-2 text-left text-xs font-medium text-[#808080] whitespace-nowrap"
                    >
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.data.map((row, ri) => (
                  <tr key={ri} className="border-b border-[#30363d] hover:bg-[#2d333b] transition-colors">
                    <td className="px-3 py-1.5 text-xs text-[#555555]">{ri + 1}</td>
                    {row.map((val, ci) => (
                      <td key={ci} className="px-3 py-1.5 text-[#eeeeee] whitespace-nowrap font-mono text-xs">
                        {val === null ? <span className="text-[#555555]">NULL</span> : String(val)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {result && result.row_count === 0 && !result.error && (
        <div className="text-sm text-[#808080] py-8 text-center">无匹配数据</div>
      )}
    </div>
  );
}
