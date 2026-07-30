import { useState, useCallback } from 'react';
import ReactECharts from 'echarts-for-react';
import { Button, Input } from '@/components/ui';

/** 后端 /api/explorer/seasonality 返回结构 */
interface SeasonalityResult {
  code?: string;
  years?: number[];
  yearly_series?: { year: number; x: string[]; y: number[] }[];
  monthly_matrix?: ({ year: number } & Record<string, number | null>)[];
  month_stats?: { month: number; avg: number | null; up: number; down: number; count: number }[];
  error?: string;
}

const YEAR_COLORS = ['#ff3b30', '#007aff', '#30d158', '#bf5af2', '#ff9f0a', '#64d2ff', '#a2845e', '#ffd60a'];
const AXIS_LABEL = { fontSize: 10, color: '#646262' };
const SPLIT_LINE = { lineStyle: { color: 'rgba(15,0,0,0.06)' } };

/** 月度收益值 → 单元格背景色（红涨绿跌，A 股配色） */
function cellBg(v: number | null): string {
  if (v == null) return 'transparent';
  const alpha = Math.min(Math.abs(v) / 15, 0.85);
  return v > 0 ? `rgba(255,59,48,${alpha})` : `rgba(48,209,88,${alpha})`;
}

/**
 * 季节图表（对标券商终端「季节图表」）：
 * 分年度归一化走势叠加 + 月度涨跌幅热力矩阵 + 逐月涨跌统计。
 */
export function Seasonality() {
  const [code, setCode] = useState('');
  const [years, setYears] = useState('5');
  const [result, setResult] = useState<SeasonalityResult | null>(null);
  const [loading, setLoading] = useState(false);

  const analyze = useCallback(async () => {
    if (!code.trim()) return;
    setLoading(true);
    try {
      const res = await fetch('/api/explorer/seasonality', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: code.trim(), years: Number(years) || 5 }),
      });
      setResult(await res.json());
    } catch (err) {
      setResult({ error: String(err) });
    } finally {
      setLoading(false);
    }
  }, [code, years]);

  // 分年叠加曲线：x 轴用 MM-DD 类目全集
  const overlayOption = result?.yearly_series?.length ? (() => {
    const allX = Array.from(new Set(result.yearly_series!.flatMap(s => s.x))).sort();
    return {
      grid: { left: 48, right: 16, top: 30, bottom: 30 },
      legend: { top: 0, textStyle: { fontSize: 11, color: '#646262' } },
      tooltip: { trigger: 'axis' },
      xAxis: {
        type: 'category',
        data: allX,
        axisLabel: { ...AXIS_LABEL, interval: Math.max(1, Math.floor(allX.length / 12)) },
      },
      yAxis: { type: 'value', scale: true, axisLabel: AXIS_LABEL, splitLine: SPLIT_LINE, name: '首日=100' },
      series: result.yearly_series!.map((s, i) => {
        const map = new Map(s.x.map((x, idx) => [x, s.y[idx]]));
        return {
          name: String(s.year),
          type: 'line',
          showSymbol: false,
          connectNulls: true,
          data: allX.map(x => map.get(x) ?? null),
          lineStyle: { width: 1.5, color: YEAR_COLORS[i % YEAR_COLORS.length] },
          itemStyle: { color: YEAR_COLORS[i % YEAR_COLORS.length] },
        };
      }),
    };
  })() : null;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-end gap-3">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-[#646262]">标的代码</label>
          <Input placeholder="600519.SH" value={code} onChange={(e) => setCode(e.target.value)} className="w-40" />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-[#646262]">回看年数</label>
          <Input type="number" value={years} onChange={(e) => setYears(e.target.value)} className="w-24" />
        </div>
        <Button variant="primary" onClick={analyze} loading={loading}>
          季节性分析
        </Button>
      </div>

      {result?.error && (
        <div className="rounded-[4px] border border-[#ff3b30]/30 bg-[#ff3b30]/10 px-3 py-2 text-sm text-[#ff3b30]">
          {result.error}
        </div>
      )}

      {overlayOption && (
        <div className="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] p-3">
          <div className="mb-2 text-xs text-[#646262]">分年度走势叠加（每年首个交易日归一化为 100）</div>
          <ReactECharts style={{ height: 340 }} option={overlayOption} />
        </div>
      )}

      {result?.monthly_matrix && result.monthly_matrix.length > 0 && (
        <div className="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] p-3">
          <div className="mb-2 text-xs text-[#646262]">月度涨跌幅矩阵（%）— 红涨绿跌</div>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse font-mono text-xs">
              <thead>
                <tr>
                  <th className="border-b border-[rgba(15,0,0,0.12)] px-2 py-1.5 text-left text-[#646262]">年份</th>
                  {Array.from({ length: 12 }, (_, i) => (
                    <th key={i} className="border-b border-[rgba(15,0,0,0.12)] px-2 py-1.5 text-right text-[#646262]">
                      {i + 1}月
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.monthly_matrix.map((row) => (
                  <tr key={row.year}>
                    <td className="border-b border-[rgba(15,0,0,0.08)] px-2 py-1 text-[#201d1d]">{row.year}</td>
                    {Array.from({ length: 12 }, (_, i) => {
                      const v = row[`m${i + 1}`] as number | null;
                      return (
                        <td
                          key={i}
                          className="border-b border-[rgba(15,0,0,0.08)] px-2 py-1 text-right"
                          style={{ background: cellBg(v), color: v == null ? '#9a9898' : '#201d1d' }}
                        >
                          {v == null ? '-' : v.toFixed(2)}
                        </td>
                      );
                    })}
                  </tr>
                ))}
                {result.month_stats && (
                  <tr>
                    <td className="px-2 py-1 font-semibold text-[#201d1d]">均值</td>
                    {result.month_stats.map((s) => (
                      <td
                        key={s.month}
                        className="px-2 py-1 text-right font-semibold"
                        style={{ color: s.avg == null ? '#9a9898' : s.avg > 0 ? '#ff3b30' : '#30d158' }}
                      >
                        {s.avg == null ? '-' : s.avg.toFixed(2)}
                      </td>
                    ))}
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {result?.month_stats && (
        <div className="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] p-3">
          <div className="mb-2 text-xs text-[#646262]">逐月上涨/下跌次数（近 {result.years?.length} 年）</div>
          <ReactECharts
            style={{ height: 220 }}
            option={{
              grid: { left: 40, right: 16, top: 30, bottom: 24 },
              legend: { top: 0, textStyle: { fontSize: 11, color: '#646262' } },
              tooltip: { trigger: 'axis' },
              xAxis: { type: 'category', data: result.month_stats.map(s => `${s.month}月`), axisLabel: AXIS_LABEL },
              yAxis: { type: 'value', axisLabel: AXIS_LABEL, splitLine: SPLIT_LINE, minInterval: 1 },
              series: [
                { name: '上涨次数', type: 'bar', data: result.month_stats.map(s => s.up), itemStyle: { color: '#ff3b30' } },
                { name: '下跌次数', type: 'bar', data: result.month_stats.map(s => s.down), itemStyle: { color: '#30d158' } },
              ],
            }}
          />
        </div>
      )}
    </div>
  );
}
