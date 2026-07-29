import { useMemo } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { Card } from '@/components/ui';

export interface ICDataPoint {
  date: string;
  ic: number;
  rank_ic?: number;
}

export interface ICStats {
  mean: number;
  ir: number;
  rank_ic: number;
  positive_ratio: number;
  std?: number;
  tstat?: number;
  skew?: number;
  kurtosis?: number;
}

/** 跨周期 IC 汇总（AlphaLens 风格 IC 表） */
export interface ICSummaryRow {
  period: number;
  mean: number;
  std: number;
  ir: number;
  tstat: number;
  rank_ic: number;
  positive_ratio: number;
}

interface ICAnalysisProps {
  icSeries: ICDataPoint[];
  stats: ICStats;
  summary?: ICSummaryRow[];
  loading?: boolean;
}

function StatCard({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="flex flex-col items-center rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-3 py-2">
      <span className="text-xs text-[#646262]">{label}</span>
      <span className={`text-lg font-semibold font-mono ${color}`}>{value}</span>
    </div>
  );
}

export default function ICAnalysis({ icSeries, stats, summary, loading }: ICAnalysisProps) {
  const chartData = useMemo(
    () =>
      icSeries.map((d) => ({
        date: d.date,
        IC: d.ic,
        RankIC: d.rank_ic ?? null,
      })),
    [icSeries]
  );

  return (
    <div className="flex flex-col gap-3">
      {/* IC 统计卡片 */}
      <div className="grid grid-cols-4 gap-2">
        <StatCard
          label="IC 均值"
          value={stats.mean.toFixed(4)}
          color={stats.mean > 0 ? 'text-[#30d158]' : 'text-[#ff3b30]'}
        />
        <StatCard
          label="IR"
          value={stats.ir.toFixed(4)}
          color={stats.ir > 0.5 ? 'text-[#30d158]' : 'text-[#ff9f0a]'}
        />
        <StatCard
          label="Rank IC"
          value={stats.rank_ic.toFixed(4)}
          color={stats.rank_ic > 0 ? 'text-[#30d158]' : 'text-[#ff3b30]'}
        />
        <StatCard
          label="IC 正比例"
          value={`${(stats.positive_ratio * 100).toFixed(1)}%`}
          color={stats.positive_ratio > 0.5 ? 'text-[#30d158]' : 'text-[#ff9f0a]'}
        />
      </div>

      {/* 扩展统计（t 值 / 偏度 / 峰度，AlphaLens 同口径） */}
      {(stats.tstat != null || stats.std != null) && (
        <div className="grid grid-cols-4 gap-2">
          <StatCard label="IC 标准差" value={(stats.std ?? 0).toFixed(4)} color="text-[#201d1d]" />
          <StatCard
            label="t 值"
            value={(stats.tstat ?? 0).toFixed(2)}
            color={Math.abs(stats.tstat ?? 0) > 2 ? 'text-[#30d158]' : 'text-[#ff9f0a]'}
          />
          <StatCard label="偏度" value={(stats.skew ?? 0).toFixed(3)} color="text-[#201d1d]" />
          <StatCard label="峰度" value={(stats.kurtosis ?? 0).toFixed(3)} color="text-[#201d1d]" />
        </div>
      )}

      {/* 跨周期 IC 汇总表 */}
      {summary && summary.length > 0 && (
        <Card title="IC 汇总（各预测周期）">
          <table className="w-full border-collapse text-xs">
            <thead>
              <tr className="bg-[#f8f7f7]">
                {['周期', 'IC 均值', 'IC 标准差', 'IR', 't 值', 'Rank IC', 'IC>0 比例'].map((h) => (
                  <th key={h} className="border-b border-[rgba(15,0,0,0.12)] px-2 py-1.5 text-left font-medium text-[#646262]">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {summary.map((r) => (
                <tr key={r.period} className="border-b border-[rgba(15,0,0,0.08)]">
                  <td className="px-2 py-1.5 text-[#201d1d]">{r.period} 日</td>
                  <td className={`px-2 py-1.5 ${r.mean > 0 ? 'text-[#30d158]' : 'text-[#ff3b30]'}`}>{r.mean.toFixed(4)}</td>
                  <td className="px-2 py-1.5 text-[#201d1d]">{r.std.toFixed(4)}</td>
                  <td className="px-2 py-1.5 text-[#201d1d]">{r.ir.toFixed(3)}</td>
                  <td className={`px-2 py-1.5 ${Math.abs(r.tstat) > 2 ? 'text-[#30d158]' : 'text-[#646262]'}`}>{r.tstat.toFixed(2)}</td>
                  <td className="px-2 py-1.5 text-[#201d1d]">{r.rank_ic.toFixed(4)}</td>
                  <td className="px-2 py-1.5 text-[#201d1d]">{(r.positive_ratio * 100).toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {/* IC 时序折线图 */}
      <Card title="IC 时序" className={loading ? 'opacity-50' : ''}>
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={chartData} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#403b3b" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 11, fill: '#646262' }}
              tickLine={{ stroke: '#403b3b' }}
              axisLine={{ stroke: '#403b3b' }}
            />
            <YAxis
              tick={{ fontSize: 11, fill: '#646262' }}
              tickLine={{ stroke: '#403b3b' }}
              axisLine={{ stroke: '#403b3b' }}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#fdfcfc',
                border: '1px solid rgba(15,0,0,0.12)',
                borderRadius: 4,
                fontSize: 12,
              }}
              labelStyle={{ color: '#646262' }}
            />
            <ReferenceLine y={0} stroke="#6e6e73" strokeDasharray="3 3" />
            <Line
              type="monotone"
              dataKey="IC"
              stroke="#007aff"
              dot={false}
              strokeWidth={1.5}
            />
            <Line
              type="monotone"
              dataKey="RankIC"
              stroke="#64d2ff"
              dot={false}
              strokeWidth={1.5}
              strokeDasharray="4 2"
            />
          </LineChart>
        </ResponsiveContainer>
      </Card>
    </div>
  );
}
