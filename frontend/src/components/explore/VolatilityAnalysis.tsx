import { useState, useCallback } from 'react';
import ReactECharts from 'echarts-for-react';
import { Button, Input } from '@/components/ui';

/** 后端 /api/explorer/volatility 返回结构 */
interface VolatilityResult {
  code?: string;
  annualize?: number;
  series?: { name: string; x: string[]; y: number[] }[];
  stats?: Record<string, Record<string, number>>;
  histograms?: Record<string, { bin: string; count: number }[]>;
  error?: string;
}

const HV_COLORS: Record<string, string> = {
  HV5: '#ff3b30',
  HV15: '#bf5af2',
  HV30: '#007aff',
  HV50: '#30d158',
};

const AXIS_LABEL = { fontSize: 10, color: '#646262' };
const SPLIT_LINE = { lineStyle: { color: 'rgba(15,0,0,0.06)' } };
const STAT_ROWS = ['最新', '均值', '中值', '标准差', '百分位', '最高', '最低'];

/**
 * 历史波动率（对标券商终端「历史波动率」）：
 * HV5/15/30/50 多窗口时序 + 统计概览表 + 频率分布。
 */
export function VolatilityAnalysis() {
  const [code, setCode] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [annualize, setAnnualize] = useState('250');
  const [histKey, setHistKey] = useState('HV5');
  const [result, setResult] = useState<VolatilityResult | null>(null);
  const [loading, setLoading] = useState(false);

  const analyze = useCallback(async () => {
    if (!code.trim()) return;
    setLoading(true);
    try {
      const res = await fetch('/api/explorer/volatility', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: code.trim(),
          start_date: startDate,
          end_date: endDate,
          annualize: Number(annualize) || 250,
        }),
      });
      setResult(await res.json());
    } catch (err) {
      setResult({ error: String(err) });
    } finally {
      setLoading(false);
    }
  }, [code, startDate, endDate, annualize]);

  const lineOption = result?.series?.length ? (() => {
    // 用最长序列的 x 轴作为类目轴
    const base = result.series!.reduce((a, b) => (a.x.length >= b.x.length ? a : b));
    return {
      grid: { left: 52, right: 16, top: 30, bottom: 30 },
      legend: { top: 0, textStyle: { fontSize: 11, color: '#646262' } },
      tooltip: { trigger: 'axis' },
      xAxis: {
        type: 'category',
        data: base.x,
        axisLabel: { ...AXIS_LABEL, interval: Math.max(1, Math.floor(base.x.length / 10)) },
      },
      yAxis: { type: 'value', scale: true, axisLabel: AXIS_LABEL, splitLine: SPLIT_LINE },
      series: result.series!.map((s) => {
        const map = new Map(s.x.map((x, i) => [x, s.y[i]]));
        return {
          name: s.name,
          type: 'line',
          showSymbol: false,
          connectNulls: true,
          data: base.x.map((x) => map.get(x) ?? null),
          lineStyle: { width: 1.5, color: HV_COLORS[s.name] },
          itemStyle: { color: HV_COLORS[s.name] },
        };
      }),
    };
  })() : null;

  const statCols = result?.stats ? Object.keys(result.stats) : [];
  const histData = result?.histograms?.[histKey] ?? [];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-[#646262]">标的代码</label>
          <Input placeholder="600519.SH" value={code} onChange={(e) => setCode(e.target.value)} className="w-40" />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-[#646262]">起始日期</label>
          <Input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="w-36" />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-[#646262]">结束日期</label>
          <Input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="w-36" />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-[#646262]">年化系数</label>
          <Input type="number" value={annualize} onChange={(e) => setAnnualize(e.target.value)} className="w-24" />
        </div>
        <Button variant="primary" onClick={analyze} loading={loading}>
          波动率分析
        </Button>
      </div>

      {result?.error && (
        <div className="rounded-[4px] border border-[#ff3b30]/30 bg-[#ff3b30]/10 px-3 py-2 text-sm text-[#ff3b30]">
          {result.error}
        </div>
      )}

      {lineOption && (
        <div className="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] p-3">
          <div className="mb-2 text-xs text-[#646262]">
            历史波动率时序（对数收益滚动标准差 × √{result?.annualize}）
          </div>
          <ReactECharts style={{ height: 340 }} option={lineOption} />
        </div>
      )}

      {statCols.length > 0 && (
        <div className="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] p-3">
          <div className="mb-2 text-xs text-[#646262]">统计概览</div>
          <table className="w-full border-collapse font-mono text-xs">
            <thead>
              <tr>
                <th className="border-b border-[rgba(15,0,0,0.12)] px-2 py-1.5 text-left text-[#646262]">指标</th>
                {statCols.map((c) => (
                  <th key={c} className="border-b border-[rgba(15,0,0,0.12)] px-2 py-1.5 text-right" style={{ color: HV_COLORS[c] || '#646262' }}>
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {STAT_ROWS.map((row) => (
                <tr key={row} className="hover:bg-[#f1eeee]">
                  <td className="border-b border-[rgba(15,0,0,0.08)] px-2 py-1 text-[#646262]">{row}</td>
                  {statCols.map((c) => {
                    const v = result?.stats?.[c]?.[row];
                    return (
                      <td key={c} className="border-b border-[rgba(15,0,0,0.08)] px-2 py-1 text-right text-[#201d1d]">
                        {v == null ? '-' : row === '百分位' ? `${v}%` : v}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {result?.histograms && (
        <div className="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] p-3">
          <div className="mb-2 flex items-center gap-3">
            <span className="text-xs text-[#646262]">频率分布</span>
            {Object.keys(result.histograms).map((k) => (
              <button
                key={k}
                onClick={() => setHistKey(k)}
                className="tb-btn"
                style={{
                  padding: '2px 8px',
                  fontSize: 11,
                  borderRadius: 4,
                  cursor: 'pointer',
                  border: `1px solid ${histKey === k ? HV_COLORS[k] || '#007aff' : 'rgba(15,0,0,0.12)'}`,
                  background: histKey === k ? 'rgba(0,122,255,0.06)' : 'transparent',
                  color: histKey === k ? HV_COLORS[k] || '#007aff' : '#646262',
                }}
              >
                {k}
              </button>
            ))}
          </div>
          <ReactECharts
            style={{ height: 240 }}
            option={{
              grid: { left: 60, right: 16, top: 10, bottom: 24 },
              tooltip: { trigger: 'axis' },
              xAxis: { type: 'value', axisLabel: AXIS_LABEL, splitLine: SPLIT_LINE, minInterval: 1 },
              yAxis: { type: 'category', data: histData.map((d) => d.bin), axisLabel: AXIS_LABEL },
              series: [{ type: 'bar', data: histData.map((d) => d.count), itemStyle: { color: '#ff9f0a' } }],
            }}
          />
        </div>
      )}
    </div>
  );
}
