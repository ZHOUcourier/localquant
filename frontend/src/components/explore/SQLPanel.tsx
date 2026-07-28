import { useState, useCallback } from 'react';
import Editor from '@monaco-editor/react';
import { Button } from '@/components/ui';

interface QueryResult {
  columns: string[];
  data: unknown[][];
  row_count: number;
  error?: string;
}

export function SQLPanel() {
  const [sql, setSql] = useState('SELECT * FROM read_parquet(\'data/cache/1d/*.parquet\') LIMIT 20;');
  const [result, setResult] = useState<QueryResult | null>(null);
  const [loading, setLoading] = useState(false);

  const execute = useCallback(async () => {
    if (!sql.trim()) return;
    setLoading(true);
    try {
      const res = await fetch('/api/explorer/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sql }),
      });
      const data: QueryResult = await res.json();
      setResult(data);
    } catch (err) {
      setResult({ columns: [], data: [], row_count: 0, error: String(err) });
    } finally {
      setLoading(false);
    }
  }, [sql]);

  return (
    <div className="flex flex-col gap-3">
      <div className="rounded-[4px] border border-[#30363d] overflow-hidden">
        <Editor
          height="200px"
          defaultLanguage="sql"
          theme="vs-dark"
          value={sql}
          onChange={(v) => setSql(v ?? '')}
          options={{
            minimap: { enabled: false },
            fontSize: 13,
            lineNumbers: 'on',
            scrollBeyondLastLine: false,
            automaticLayout: true,
            tabSize: 2,
            wordWrap: 'on',
          }}
        />
      </div>

      <div className="flex items-center gap-2">
        <Button variant="primary" onClick={execute} loading={loading}>
          执行
        </Button>
        {result && !result.error && (
          <span className="text-xs text-[#808080]">
            返回 {result.row_count} 行
          </span>
        )}
      </div>

      {result?.error && (
        <div className="rounded-[4px] border border-[#e06c75]/30 bg-[#e06c75]/10 px-3 py-2 text-sm text-[#e06c75]">
          {result.error}
        </div>
      )}

      {result && result.columns.length > 0 && (
        <div className="rounded-[4px] border border-[#30363d] overflow-auto max-h-[400px]">
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
      )}
    </div>
  );
}
