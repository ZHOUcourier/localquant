import { useState, useCallback } from 'react';
import ReactECharts from 'echarts-for-react';
import { Button, Input } from '@/components/ui';

/** 后端 /api/explorer/regression 返回结构 */
interface RegressionResult {
  code_y?: string;
  code_x?: string;
  use_returns?: boolean;
  points?: [number, number, string][];
  line?: { x0: number; y0: number; x1: number; y1: number };
  stats?: Record<string, number>;
  hist_x?: { bin: string; count: number }[];
  hist_y?: { bin: string; count: number }[];
  error?: string;
}

const AXIS_LABEL = { fontSize: 10, color: '#646262' };
const SPLIT_LINE = { lineStyle: { color: 'rgba(15,0,0,0.06)' } };

function HistChart({ title, data, color }: { title: string; data: { bin: string; count: number }[]; color: string }) {
  return (
    <div className="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] p-3">
      <div className="mb-2 text-xs text-[#646262]">{title}</div>
      <ReactECharts
        style={{ height: 180 }}
        option={{
          grid: { left: 40, right: 12, top: 8, bottom: 24 },
          xAxis: { type: 'category', data: data.map(d => d.bin), axisLabel: AXIS_LABEL },
          yAxis: { type: 'value', axisLabel: AXIS_LABEL, splitLine: SPLIT_LINE },
          tooltip: { trigger: 'axis' },
          series: [{ type: 'bar', data: data.map(d => d.count), itemStyle: { color } }],
        }}
      />
    </div>
  );
}

/**
 * 回归分析（对标券商终端「回归分析」）：
 * 两标的收盘价/收益率 OLS 回归 — 散点 + 拟合线 + Beta/Alpha/R/R² + 双边缘分布。
 */
export function RegressionAnalysis() {
  const [codeY, setCodeY] = useState('');
  const [codeX, setCodeX] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [useReturns, setUseReturns] = useState(false);
  const [result, setResult] = useState<RegressionResult | null>(null);
  const [loading, setLoading] = useState(false);

  const analyze = useCallback(async () => {
    if (!codeY.trim() || !codeX.trim()) return;
    setLoading(true);
    try {
      const res = await fetch('/api/explorer/regression', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code_y: codeY.trim(),
          code_x: codeX.trim(),
          start_date: startDate,
          end_date: endDate,
          use_returns: useReturns,
        }),
      });
      setResult(await res.json());
    } catch (err) {
      setResult({ error: String(err) });
    } finally {
      setLoading(false);
    }
  }, [codeY, codeX, startDate, endDate, useReturns]);

  const scatterOption = result?.points && result.line ? {
    grid: { left: 60, right: 20, top: 20, bottom: 40 },
    tooltip: {
      trigger: 'item',
      formatter: (p: { value: [number, number, string] }) =>
        `${p.value[2]}<br/>X: ${p.value[0]}<br/>Y: ${p.value[1]}`,
    },
    xAxis: { type: 'value', name: `X: ${result.code_x}`, scale: true, axisLabel: AXIS_LABEL, splitLine: SPLIT_LINE },
    yAxis: { type: 'value', name: `Y: ${result.code_y}`, scale: true, axisLabel: AXIS_LABEL, splitLine: SPLIT_LINE },
    series: [
      {
        type: 'scatter',
        symbolSize: 5,
        data: result.points,
        itemStyle: { color: 'rgba(0,122,255,0.55)' },
      },
      {
        type: 'line',
        showSymbol: false,
        data: [
          [result.line.x0, result.line.y0],
          [result.line.x1, result.line.y1],
        ],
        lineStyle: { color: '#ff3b30', width: 2 },
      },
    ],
  } : null;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-[#646262]">因变量 Y（代码）</label>
          <Input placeholder="600519.SH" value={codeY} onChange={(e) => setCodeY(e.target.value)} className="w-36" />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-[#646262]">自变量 X（代码）</label>
          <Input placeholder="000300.SH" value={codeX} onChange={(e) => setCodeX(e.target.value)} className="w-36" />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-[#646262]">起始日期</label>
          <Input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="w-36" />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-[#646262]">结束日期</label>
          <Input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="w-36" />
        </div>
        <label className="mb-1.5 flex cursor-pointer items-center gap-1.5 text-xs text-[#646262]">
          <input type="checkbox" checked={useReturns} onChange={(e) => setUseReturns(e.target.checked)} />
          按日收益率回归
        </label>
        <Button variant="primary" onClick={analyze} loading={loading}>
          回归分析
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
            <div key={k} className="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-3 py-3">
              <div className="mb-1 text-xs text-[#646262]">{k}</div>
              <div className="font-mono text-lg text-[#201d1d]">{v}</div>
            </div>
          ))}
        </div>
      )}

      {scatterOption && (
        <div className="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] p-3">
          <div className="mb-2 text-xs text-[#646262]">
            散点与拟合线 — Y = {result?.stats?.Beta}·X + {result?.stats?.Alpha}
          </div>
          <ReactECharts style={{ height: 360 }} option={scatterOption} />
        </div>
      )}

      {result?.hist_x && result?.hist_y && (
        <div className="grid grid-cols-2 gap-3">
          <HistChart title={`X 分布 — ${result.code_x}`} data={result.hist_x} color="#007aff" />
          <HistChart title={`Y 分布 — ${result.code_y}`} data={result.hist_y} color="#ff3b30" />
        </div>
      )}
    </div>
  );
}
