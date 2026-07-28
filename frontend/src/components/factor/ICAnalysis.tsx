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
}

interface ICAnalysisProps {
  icSeries: ICDataPoint[];
  stats: ICStats;
  loading?: boolean;
}

function StatCard({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="flex flex-col items-center rounded-[4px] border border-[#30363d] bg-[#21262d] px-3 py-2">
      <span className="text-xs text-[#808080]">{label}</span>
      <span className={`text-lg font-semibold font-mono ${color}`}>{value}</span>
    </div>
  );
}

export default function ICAnalysis({ icSeries, stats, loading }: ICAnalysisProps) {
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
          color={stats.mean > 0 ? 'text-[#7fd88f]' : 'text-[#e06c75]'}
        />
        <StatCard
          label="IR"
          value={stats.ir.toFixed(4)}
          color={stats.ir > 0.5 ? 'text-[#7fd88f]' : 'text-[#f5a742]'}
        />
        <StatCard
          label="Rank IC"
          value={stats.rank_ic.toFixed(4)}
          color={stats.rank_ic > 0 ? 'text-[#7fd88f]' : 'text-[#e06c75]'}
        />
        <StatCard
          label="IC 正比例"
          value={`${(stats.positive_ratio * 100).toFixed(1)}%`}
          color={stats.positive_ratio > 0.5 ? 'text-[#7fd88f]' : 'text-[#f5a742]'}
        />
      </div>

      {/* IC 时序折线图 */}
      <Card title="IC 时序" className={loading ? 'opacity-50' : ''}>
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={chartData} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 11, fill: '#808080' }}
              tickLine={{ stroke: '#30363d' }}
              axisLine={{ stroke: '#30363d' }}
            />
            <YAxis
              tick={{ fontSize: 11, fill: '#808080' }}
              tickLine={{ stroke: '#30363d' }}
              axisLine={{ stroke: '#30363d' }}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#161b22',
                border: '1px solid #30363d',
                borderRadius: 4,
                fontSize: 12,
              }}
              labelStyle={{ color: '#808080' }}
            />
            <ReferenceLine y={0} stroke="#555555" strokeDasharray="3 3" />
            <Line
              type="monotone"
              dataKey="IC"
              stroke="#fab283"
              dot={false}
              strokeWidth={1.5}
            />
            <Line
              type="monotone"
              dataKey="RankIC"
              stroke="#56b6c2"
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
