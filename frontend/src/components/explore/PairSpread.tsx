import { useState, useCallback } from 'react';
import ReactECharts from 'echarts-for-react';
import { Button, Input } from '@/components/ui';

/** 后端 /api/explorer/pair-spread 返回结构 */
interface PairSpreadResult {
  code_a?: string;
  code_b?: string;
  window?: number;
  stats?: Record<string, number>;
  ratio?: { x: string[]; y: number[] };
  zscore?: { x: string[]; y: number[] };
  error?: string;
}

const AXIS_LABEL = { fontSize: 10, color: '#646262' };
const SPLIT_LINE = { lineStyle: { color: 'rgba(15,0,0,0.06)' } };

/**
 * 配对价差分析：两标的比价 + 对数价差滚动 Z-Score（±2 开平仓参考带），
 * 用于配对交易/相对强弱研究。
 */
export function PairSpread() {
  const [codeA, setCodeA] = useState('');
  const [codeB, setCodeB] = useState('');
  const [window, setWindow] = useState('60');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [result, setResult] = useState<PairSpreadResult | null>(null);
  const [loading, setLoading] = useState(false);

  const analyze = useCallback(async () => {
    if (!codeA.trim() || !codeB.trim()) return;
    setLoading(true);
    try {
      const res = await fetch('/api/explorer/pair-spread', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code_a: codeA.trim(),
          code_b: codeB.trim(),
          window: Number(window) || 60,
          start_date: startDate,
          end_date: endDate,
        }),
      });
      setResult(await res.json());
    } catch (err) {
      setResult({ error: String(err) });
    } finally {
      setLoading(false);
    }
  }, [codeA, codeB, window, startDate, endDate]);

  const zOption = result?.zscore ? {
    grid: { left: 48, right: 16, top: 12, bottom: 30 },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: result.zscore.x,
      axisLabel: { ...AXIS_LABEL, interval: Math.max(1, Math.floor(result.zscore.x.length / 8)) },
    },
    yAxis: { type: 'value', scale: true, axisLabel: AXIS_LABEL, splitLine: SPLIT_LINE },
    series: [
      {
        name: 'Z-Score',
        type: 'line',
        showSymbol: false,
        data: result.zscore.y,
        lineStyle: { color: '#007aff', width: 1.5 },
        itemStyle: { color: '#007aff' },
        markLine: {
          symbol: 'none',
          silent: true,
          lineStyle: { type: 'dashed' },
          data: [
            { yAxis: 2, lineStyle: { color: '#ff3b30' }, label: { formatter: '+2σ', fontSize: 10 } },
            { yAxis: 0, lineStyle: { color: '#9a9898' }, label: { formatter: '0', fontSize: 10 } },
            { yAxis: -2, lineStyle: { color: '#30d158' }, label: { formatter: '-2σ', fontSize: 10 } },
          ],
        },
      },
    ],
  } : null;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-[#646262]">标的 A</label>
          <Input placeholder="600519.SH" value={codeA} onChange={(e) => setCodeA(e.target.value)} className="w-36" />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-[#646262]">标的 B</label>
          <Input placeholder="000858.SZ" value={codeB} onChange={(e) => setCodeB(e.target.value)} className="w-36" />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-[#646262]">Z-Score 窗口</label>
          <Input type="number" value={window} onChange={(e) => setWindow(e.target.value)} className="w-24" />
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
          价差分析
        </Button>
      </div>

      {result?.error && (
        <div className="rounded-[4px] border border-[#ff3b30]/30 bg-[#ff3b30]/10 px-3 py-2 text-sm text-[#ff3b30]">
          {result.error}
        </div>
      )}

      {result?.stats && (
        <div className="grid grid-cols-6 gap-3">
          {Object.entries(result.stats).map(([k, v]) => (
            <div key={k} className="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-3 py-2.5">
              <div className="mb-1 text-[11px] text-[#646262]">{k}</div>
              <div
                className="font-mono text-base"
                style={{ color: k === '当前 Z-Score' && Math.abs(v) > 2 ? '#ff3b30' : '#201d1d' }}
              >
                {v}
              </div>
            </div>
          ))}
        </div>
      )}

      {zOption && (
        <div className="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] p-3">
          <div className="mb-2 text-xs text-[#646262]">
            对数价差滚动 Z-Score（窗口 {result?.window}）— 突破 ±2σ 为常用配对开仓参考
          </div>
          <ReactECharts style={{ height: 280 }} option={zOption} />
        </div>
      )}

      {result?.ratio && (
        <div className="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] p-3">
          <div className="mb-2 text-xs text-[#646262]">
            比价序列 {result.code_a} / {result.code_b}
          </div>
          <ReactECharts
            style={{ height: 220 }}
            option={{
              grid: { left: 56, right: 16, top: 12, bottom: 30 },
              tooltip: { trigger: 'axis' },
              xAxis: {
                type: 'category',
                data: result.ratio.x,
                axisLabel: { ...AXIS_LABEL, interval: Math.max(1, Math.floor(result.ratio.x.length / 8)) },
              },
              yAxis: { type: 'value', scale: true, axisLabel: AXIS_LABEL, splitLine: SPLIT_LINE },
              series: [{
                type: 'line',
                showSymbol: false,
                data: result.ratio.y,
                lineStyle: { color: '#ff9f0a', width: 1.5 },
                itemStyle: { color: '#ff9f0a' },
              }],
            }}
          />
        </div>
      )}
    </div>
  );
}
