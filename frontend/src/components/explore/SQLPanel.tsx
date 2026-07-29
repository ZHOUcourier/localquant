import { useState, useCallback } from 'react';
import { Sparkles } from 'lucide-react';
import { Button, CodeEditor, Input } from '@/components/ui';

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
  // AI：自然语言生成 SQL / 结果解读
  const [aiQuestion, setAiQuestion] = useState('');
  const [aiGenLoading, setAiGenLoading] = useState(false);
  const [aiInsight, setAiInsight] = useState<string | null>(null);
  const [aiInsightLoading, setAiInsightLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);

  const execute = useCallback(async () => {
    if (!sql.trim()) return;
    setLoading(true);
    setAiInsight(null);
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

  // AI：自然语言 → SQL（填入编辑器，由用户确认执行）
  const handleAIGenerate = useCallback(async () => {
    if (!aiQuestion.trim()) return;
    setAiGenLoading(true);
    setAiError(null);
    try {
      const res = await fetch('/api/ai/explore-sql', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: aiQuestion }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(err?.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      if (data.sql) setSql(data.sql);
    } catch (e) {
      setAiError(e instanceof Error ? e.message : String(e));
    } finally {
      setAiGenLoading(false);
    }
  }, [aiQuestion]);

  // AI：解读查询结果
  const handleAIInsight = useCallback(async () => {
    if (!result || result.columns.length === 0) return;
    setAiInsightLoading(true);
    setAiError(null);
    try {
      const res = await fetch('/api/ai/explore-insight', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          columns: result.columns,
          rows: result.data.slice(0, 50),
          context: `SQL: ${sql}`,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(err?.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      setAiInsight(data.insight || '');
    } catch (e) {
      setAiError(e instanceof Error ? e.message : String(e));
    } finally {
      setAiInsightLoading(false);
    }
  }, [result, sql]);

  return (
    <div className="flex flex-col gap-3">
      {/* AI 生成 SQL */}
      <div className="flex items-center gap-2">
        <Input
          placeholder="✦ 用自然语言描述查询，AI 生成 SQL（如：查平安银行最近 30 天收盘价）"
          value={aiQuestion}
          onChange={(e) => setAiQuestion(e.target.value)}
          className="flex-1"
          onKeyDown={(e) => {
            if (e.key === 'Enter') handleAIGenerate();
          }}
        />
        <button
          type="button"
          disabled={aiGenLoading || !aiQuestion.trim()}
          onClick={handleAIGenerate}
          className="flex shrink-0 items-center gap-1.5 rounded-[4px] border border-[rgba(124,58,237,0.4)] bg-[#fdfcfc] px-3 py-1.5 text-xs font-medium text-[#7c3aed] transition-colors hover:bg-[#f8f7f7] disabled:opacity-50 cursor-pointer"
        >
          <Sparkles size={12} />
          {aiGenLoading ? '生成中...' : 'AI 生成 SQL'}
        </button>
      </div>

      {aiError && (
        <div className="rounded-[4px] border border-[#ff3b30]/30 bg-[#ff3b30]/10 px-3 py-2 text-xs text-[#ff3b30]">
          {aiError}
        </div>
      )}

      <CodeEditor
        value={sql}
        onChange={setSql}
        language="sql"
        height={200}
        title="SQL 查询编辑"
        fontSize={13}
      />

      <div className="flex items-center gap-2">
        <Button variant="primary" onClick={execute} loading={loading}>
          执行
        </Button>
        {result && !result.error && (
          <span className="text-xs text-[#646262]">
            返回 {result.row_count} 行
          </span>
        )}
        {result && !result.error && result.columns.length > 0 && (
          <button
            type="button"
            disabled={aiInsightLoading}
            onClick={handleAIInsight}
            className="flex items-center gap-1 rounded-[4px] border border-[rgba(124,58,237,0.4)] bg-[#fdfcfc] px-2.5 py-1 text-xs text-[#7c3aed] transition-colors hover:bg-[#f8f7f7] disabled:opacity-50 cursor-pointer"
          >
            <Sparkles size={11} />
            {aiInsightLoading ? '解读中...' : 'AI 解读结果'}
          </button>
        )}
      </div>

      {aiInsight && (
        <div className="whitespace-pre-wrap rounded-[4px] border border-[rgba(124,58,237,0.3)] bg-[#f8f7f7] px-3 py-2.5 text-xs leading-relaxed text-[#424245]">
          {aiInsight}
        </div>
      )}

      {result?.error && (
        <div className="rounded-[4px] border border-[#ff3b30]/30 bg-[#ff3b30]/10 px-3 py-2 text-sm text-[#ff3b30]">
          {result.error}
        </div>
      )}

      {result && result.columns.length > 0 && (
        <div className="rounded-[4px] border border-[rgba(15,0,0,0.12)] overflow-auto max-h-[400px]">
          <table className="w-full border-collapse text-sm">
            <thead className="sticky top-0 z-10">
              <tr className="bg-[#f8f7f7]">
                <th className="border-b border-[rgba(15,0,0,0.12)] px-3 py-2 text-left text-xs font-medium text-[#646262] w-10">
                  #
                </th>
                {result.columns.map((col) => (
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
              {result.data.map((row, ri) => (
                <tr key={ri} className="border-b border-[rgba(15,0,0,0.12)] hover:bg-[#f1eeee] transition-colors">
                  <td className="px-3 py-1.5 text-xs text-[#646262]">{ri + 1}</td>
                  {row.map((val, ci) => (
                    <td key={ci} className="px-3 py-1.5 text-[#201d1d] whitespace-nowrap font-mono text-xs">
                      {val === null ? <span className="text-[#9a9898]">NULL</span> : String(val)}
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
