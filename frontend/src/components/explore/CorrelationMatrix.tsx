import { useState, useCallback } from 'react';
import { Button, Input } from '@/components/ui';

/** 后端 /api/explorer/correlation 返回结构 */
interface CorrelationResult {
  codes?: string[];
  matrix?: (number | null)[][];
  missing?: string[];
  n_obs?: number;
  error?: string;
}

/** 相关系数 → 单元格背景（对标券商终端相关性分析的分档配色） */
function corrBg(v: number | null): string {
  if (v == null) return 'transparent';
  const a = Math.abs(v);
  if (a >= 0.8) return 'rgba(0,64,133,0.85)';
  if (a >= 0.6) return 'rgba(0,90,180,0.65)';
  if (a >= 0.3) return 'rgba(0,122,255,0.4)';
  return 'rgba(0,122,255,0.15)';
}

function corrColor(v: number | null): string {
  if (v == null) return '#9a9898';
  return Math.abs(v) >= 0.6 ? '#fdfcfc' : '#201d1d';
}

/**
 * 相关性分析（对标券商终端「相关性分析」）：
 * 多标的日收益率 Pearson 相关系数矩阵，按 |ρ| 分档着色。
 */
export function CorrelationMatrix() {
  const [codesText, setCodesText] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [result, setResult] = useState<CorrelationResult | null>(null);
  const [loading, setLoading] = useState(false);

  const analyze = useCallback(async () => {
    const codes = codesText.split(/[,，\s]+/).map((s) => s.trim()).filter(Boolean);
    if (codes.length < 2) return;
    setLoading(true);
    try {
      const res = await fetch('/api/explorer/correlation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ codes, start_date: startDate, end_date: endDate }),
      });
      setResult(await res.json());
    } catch (err) {
      setResult({ error: String(err) });
    } finally {
      setLoading(false);
    }
  }, [codesText, startDate, endDate]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex min-w-[320px] flex-1 flex-col gap-1">
          <label className="text-xs text-[#646262]">标的代码（逗号/空格分隔，至少 2 个，最多 30 个）</label>
          <Input
            placeholder="600519.SH, 000001.SZ, 300750.SZ"
            value={codesText}
            onChange={(e) => setCodesText(e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-[#646262]">起始日期</label>
          <Input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="w-36" />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-[#646262]">结束日期</label>
          <Input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="w-36" />
        </div>
        <Button variant="primary" onClick={analyze} loading={loading}>
          相关性分析
        </Button>
      </div>

      {/* 分档图例 */}
      <div className="flex items-center gap-2 text-[11px] text-[#646262]">
        <span>|ρ| 分档:</span>
        {[
          { label: '0.00 - 0.29', bg: 'rgba(0,122,255,0.15)' },
          { label: '0.30 - 0.59', bg: 'rgba(0,122,255,0.4)' },
          { label: '0.60 - 0.79', bg: 'rgba(0,90,180,0.65)' },
          { label: '0.80 - 1.00', bg: 'rgba(0,64,133,0.85)' },
        ].map((item) => (
          <span key={item.label} className="rounded-[3px] px-2 py-0.5 font-mono" style={{ background: item.bg, color: item.bg.includes('0.15') || item.bg.includes('0.4') ? '#201d1d' : '#fdfcfc' }}>
            {item.label}
          </span>
        ))}
      </div>

      {result?.error && (
        <div className="rounded-[4px] border border-[#ff3b30]/30 bg-[#ff3b30]/10 px-3 py-2 text-sm text-[#ff3b30]">
          {result.error}
        </div>
      )}

      {result?.missing && result.missing.length > 0 && !result.error && (
        <div className="rounded-[4px] border border-[#ff9f0a]/30 bg-[#ff9f0a]/10 px-3 py-2 text-xs text-[#cc7f08]">
          以下代码无本地缓存已跳过: {result.missing.join(', ')}
        </div>
      )}

      {result?.codes && result.matrix && (
        <div className="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] p-3">
          <div className="mb-2 text-xs text-[#646262]">
            日收益率 Pearson 相关系数矩阵（样本 {result.n_obs} 个交易日）
          </div>
          <div className="overflow-x-auto">
            <table className="border-collapse font-mono text-xs">
              <thead>
                <tr>
                  <th className="px-2 py-1.5 text-left text-[#646262]"> </th>
                  {result.codes.map((c) => (
                    <th key={c} className="px-2 py-1.5 text-center text-[#646262]">{c}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.codes.map((rowCode, i) => (
                  <tr key={rowCode}>
                    <td className="px-2 py-1 text-[#201d1d]">{rowCode}</td>
                    {result.codes!.map((colCode, j) => {
                      const v = i === j ? 1 : result.matrix![i][j];
                      return (
                        <td
                          key={colCode}
                          className="min-w-[72px] border border-[#fdfcfc] px-2 py-1.5 text-center"
                          style={{ background: corrBg(v), color: corrColor(v) }}
                          title={`${rowCode} × ${colCode}: ${v ?? '-'}`}
                        >
                          {v == null ? '-' : v.toFixed(3)}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
