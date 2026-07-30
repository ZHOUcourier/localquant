import { useState, useCallback } from 'react';
import ReactECharts from 'echarts-for-react';
import { Button, Input } from '@/components/ui';

/** 后端 /api/explorer/rolling-corr 返回结构 */
interface RollingCorrResult {
  code_a?: string;
  code_b?: string;
  window?: number;
  stats?: Record<string, number>;
  x?: string[];
  corr?: number[];
  beta?: number[];
  error?: string;
}

const AXIS_LABEL = { fontSize: 10, color: '#646262' };
const SPLIT_LINE = { lineStyle: { color: 'rgba(15,0,0,0.06)' } };

/**
 * 滚动相关 / 滚动 Beta：观察个股与基准（或两标的间）关系的时变性，
 * 补充静态回归/相关矩阵无法体现的结构变化。
 */
export function RollingCorrelation() {
  const [codeA, setCodeA] = useState('');
  const [codeB, setCodeB] = useState('');
  const [window, setWindow] = useState('60');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [result, setResult] = useState<RollingCorrResult | null>(null);
  const [loading, setLoading] = useState(false);

  const analyze = useCallback(async () => {
    if (!codeA.trim() || !codeB.trim()) return;
    setLoading(true);
    try {
      const res = await fetch('/api/explorer/rolling-corr', {
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

  const chartOption = result?.x && result.corr && result.beta ? {
    grid: { left: 48, right: 48, top: 30, bottom: 30 },
    legend: { top: 0, textStyle: { fontSize: 11, color: '#646262' } },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: result.x,
      axisLabel: { ...AXIS_LABEL, interval: Math.max(1, Math.floor(result.x.length / 8)) },
    },
    yAxis: [
      { type: 'value', name: '相关', min: -1, max: 1, axisLabel: AXIS_LABEL, splitLine: SPLIT_LINE },
      { type: 'value', name: 'Beta', scale: true, axisLabel: AXIS_LABEL, splitLine: { show: false } },
    ],
    series: [
      {
        name: '滚动相关',
        type: 'line',
        showSymbol: false,
        yAxisIndex: 0,
        data: result.corr,
        lineStyle: { color: '#007aff', width: 1.5 },
        itemStyle: { color: '#007aff' },
      },
      {
        name: '滚动 Beta',
        type: 'line',
        showSymbol: false,
        yAxisIndex: 1,
        data: result.beta,
        lineStyle: { color: '#ff9f0a', width: 1.5 },
        itemStyle: { color: '#ff9f0a' },
      },
    ],
  } : null;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-[#646262]">标的</label>
          <Input placeholder="600519.SH" value={codeA} onChange={(e) => setCodeA(e.target.value)} className="w-36" />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-[#646262]">基准（指数/标的）</label>
          <Input placeholder="000300.SH" value={codeB} onChange={(e) => setCodeB(e.target.value)} className="w-36" />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-[#646262]">滚动窗口</label>
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
          滚动分析
        </Button>
      </div>

      {result?.error && (
        <div className="rounded-[4px] border border-[#ff3b30]/30 bg-[#ff3b30]/10 px-3 py-2 text-sm text-[#ff3b30]">
          {result.error}
        </div>
      )}

      {result?.stats && (
        <div className="grid grid-cols-5 gap-3">
          {Object.entries(result.stats).map(([k, v]) => (
            <div key={k} className="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-3 py-2.5">
              <div className="mb-1 text-[11px] text-[#646262]">{k}</div>
              <div className="font-mono text-base text-[#201d1d]">{v}</div>
            </div>
          ))}
        </div>
      )}

      {chartOption && (
        <div className="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] p-3">
          <div className="mb-2 text-xs text-[#646262]">
            {result?.code_a} 对 {result?.code_b} 的滚动相关（左轴）与滚动 Beta（右轴），窗口 {result?.window} 日
          </div>
          <ReactECharts style={{ height: 320 }} option={chartOption} />
        </div>
      )}
    </div>
  );
}
