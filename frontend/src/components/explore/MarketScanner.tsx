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
          <label className="text-xs text-[#9a9898]">日期</label>
          <Input
            placeholder="2024-01-02"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="w-40"
          />
        </div>
        <div className="flex flex-col gap-1 flex-1">
          <label className="text-xs text-[#9a9898]">筛选条件（多条用分号分隔）</label>
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
        <div className="rounded-[4px] border border-[#ff3b30]/30 bg-[#ff3b30]/10 px-3 py-2 text-sm text-[#ff3b30]">
          {result.error}
        </div>
      )}

      {result && result.columns.length > 0 && (
        <>
          <div className="text-xs text-[#9a9898]">共 {result.row_count} 条结果</div>
          <div className="rounded-[4px] border border-[#403b3b] overflow-auto max-h-[500px]">
            <table className="w-full border-collapse text-sm">
              <thead className="sticky top-0 z-10">
                <tr className="bg-[#302c2c]">
                  <th className="border-b border-[#403b3b] px-3 py-2 text-left text-xs font-medium text-[#9a9898] w-10">
                    #
                  </th>
                  {result.columns.map((col) => (
                    <th
                      key={col}
                      className="border-b border-[#403b3b] px-3 py-2 text-left text-xs font-medium text-[#9a9898] whitespace-nowrap"
                    >
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.data.map((row, ri) => (
                  <tr key={ri} className="border-b border-[#403b3b] hover:bg-[#363131] transition-colors">
                    <td className="px-3 py-1.5 text-xs text-[#6e6e73]">{ri + 1}</td>
                    {row.map((val, ci) => (
                      <td key={ci} className="px-3 py-1.5 text-[#fdfcfc] whitespace-nowrap font-mono text-xs">
                        {val === null ? <span className="text-[#6e6e73]">NULL</span> : String(val)}
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
        <div className="text-sm text-[#9a9898] py-8 text-center">无匹配数据</div>
      )}
    </div>
  );
}
