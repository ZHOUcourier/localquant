import { useState, useCallback } from 'react';
import ReactECharts from 'echarts-for-react';
import { Button, Input } from '@/components/ui';

/** 后端 /api/explorer/risk-profile 返回结构 */
interface RiskProfileResult {
  code?: string;
  metrics?: Record<string, number | null>;
  equity?: { x: string[]; y: number[] };
  drawdown?: { x: string[]; y: number[] };
  return_hist?: { bin: string; count: number }[];
  error?: string;
}

const AXIS_LABEL = { fontSize: 10, color: '#646262' };
const SPLIT_LINE = { lineStyle: { color: 'rgba(15,0,0,0.06)' } };

/** 指标值着色：收益/夏普类正绿负红，回撤/VaR 类恒红 */
function metricColor(key: string, v: number | null): string {
  if (v == null) return '#9a9898';
  if (/回撤|VaR|CVaR/.test(key)) return '#ff3b30';
  if (/涨跌|收益|夏普|卡玛|胜率/.test(key)) return v >= 0 ? '#30d158' : '#ff3b30';
  return '#201d1d';
}

/**
 * 风险画像：单标的收益/波动/回撤/尾部风险一站式体检 —
 * 指标卡 + 净值曲线 + 回撤水下图 + 日收益分布。
 */
export function RiskProfile() {
  const [code, setCode] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [result, setResult] = useState<RiskProfileResult | null>(null);
  const [loading, setLoading] = useState(false);

  const analyze = useCallback(async () => {
    if (!code.trim()) return;
    setLoading(true);
    try {
      const res = await fetch('/api/explorer/risk-profile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: code.trim(), start_date: startDate, end_date: endDate }),
      });
      setResult(await res.json());
    } catch (err) {
      setResult({ error: String(err) });
    } finally {
      setLoading(false);
    }
  }, [code, startDate, endDate]);

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
        <Button variant="primary" onClick={analyze} loading={loading}>
          风险画像
        </Button>
      </div>

      {result?.error && (
        <div className="rounded-[4px] border border-[#ff3b30]/30 bg-[#ff3b30]/10 px-3 py-2 text-sm text-[#ff3b30]">
          {result.error}
        </div>
      )}

      {result?.metrics && (
        <div className="grid grid-cols-6 gap-3">
          {Object.entries(result.metrics).map(([k, v]) => (
            <div key={k} className="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-3 py-2.5">
              <div className="mb-1 text-[11px] text-[#646262]">{k}</div>
              <div className="font-mono text-base" style={{ color: metricColor(k, v) }}>
                {v == null ? '-' : v}
              </div>
            </div>
          ))}
        </div>
      )}

      {result?.equity && result?.drawdown && (
        <div className="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] p-3">
          <div className="mb-2 text-xs text-[#646262]">净值曲线（区间首日=1）与回撤水下图</div>
          <ReactECharts
            style={{ height: 380 }}
            option={{
              grid: [
                { left: 56, right: 16, top: 12, height: '52%' },
                { left: 56, right: 16, top: '70%', height: '22%' },
              ],
              axisPointer: { link: [{ xAxisIndex: 'all' }] },
              tooltip: { trigger: 'axis' },
              xAxis: [
                { type: 'category', gridIndex: 0, data: result.equity.x, axisLabel: { show: false } },
                {
                  type: 'category', gridIndex: 1, data: result.drawdown.x,
                  axisLabel: { ...AXIS_LABEL, interval: Math.max(1, Math.floor(result.drawdown.x.length / 8)) },
                },
              ],
              yAxis: [
                { type: 'value', gridIndex: 0, scale: true, axisLabel: AXIS_LABEL, splitLine: SPLIT_LINE },
                { type: 'value', gridIndex: 1, axisLabel: { ...AXIS_LABEL, formatter: '{value}%' }, splitLine: SPLIT_LINE },
              ],
              series: [
                {
                  name: '净值', type: 'line', xAxisIndex: 0, yAxisIndex: 0, showSymbol: false,
                  data: result.equity.y, lineStyle: { color: '#007aff', width: 1.5 }, itemStyle: { color: '#007aff' },
                },
                {
                  name: '回撤(%)', type: 'line', xAxisIndex: 1, yAxisIndex: 1, showSymbol: false,
                  data: result.drawdown.y,
                  lineStyle: { color: '#ff3b30', width: 1 },
                  itemStyle: { color: '#ff3b30' },
                  areaStyle: { color: 'rgba(255,59,48,0.15)' },
                },
              ],
            }}
          />
        </div>
      )}

      {result?.return_hist && (
        <div className="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] p-3">
          <div className="mb-2 text-xs text-[#646262]">日收益分布（%）</div>
          <ReactECharts
            style={{ height: 220 }}
            option={{
              grid: { left: 48, right: 16, top: 10, bottom: 24 },
              tooltip: { trigger: 'axis' },
              xAxis: { type: 'category', data: result.return_hist.map(d => d.bin), axisLabel: AXIS_LABEL },
              yAxis: { type: 'value', axisLabel: AXIS_LABEL, splitLine: SPLIT_LINE },
              series: [{
                type: 'bar',
                data: result.return_hist.map(d => ({
                  value: d.count,
                  itemStyle: { color: parseFloat(d.bin) >= 0 ? '#ff3b30' : '#30d158' },
                })),
              }],
            }}
          />
        </div>
      )}
    </div>
  );
}
