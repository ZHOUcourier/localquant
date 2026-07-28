import { useMemo } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import { Card } from '@/components/ui';

export interface QuantileDataPoint {
  date: string;
  groups: Record<string, number>; // group label -> return
}

export interface QuantileStats {
  groupReturns: Record<string, number>; // cumulative return per group
  longShortReturn: number;
}

interface QuantileChartProps {
  data: QuantileDataPoint[];
  stats: QuantileStats;
  loading?: boolean;
}

const GROUP_COLORS = [
  '#ff3b30', // group 1 (worst)
  '#ff9f0a',
  '#ffd60a',
  '#32d74b',
  '#30d158', // group 5 (best)
  '#64d2ff',
  '#0a84ff',
  '#bf5af2',
];

function CumulativeCard({ label, value }: { label: string; value: string }) {
  const isPositive = parseFloat(value) > 0;
  return (
    <div className="flex flex-col items-center rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-3 py-2">
      <span className="text-xs text-[#646262]">{label}</span>
      <span className={`text-lg font-semibold font-mono ${isPositive ? 'text-[#30d158]' : 'text-[#ff3b30]'}`}>
        {value}
      </span>
    </div>
  );
}

export default function QuantileChart({ data, stats, loading }: QuantileChartProps) {
  const groupLabels = useMemo(() => {
    if (data.length === 0) return [];
    return Object.keys(data[0].groups).sort();
  }, [data]);

  const chartData = useMemo(
    () =>
      data.map((d) => ({
        date: d.date,
        ...d.groups,
      })),
    [data]
  );

  return (
    <div className="flex flex-col gap-3">
      {/* 累计收益卡片 */}
      <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-6">
        {groupLabels.map((g) => (
          <CumulativeCard
            key={g}
            label={`第${g}组`}
            value={`${((stats.groupReturns[g] ?? 0) * 100).toFixed(2)}%`}
          />
        ))}
        <CumulativeCard
          label="多空收益"
          value={`${(stats.longShortReturn * 100).toFixed(2)}%`}
        />
      </div>

      {/* 各组收益折线图 */}
      <Card title="分层累计收益" className={loading ? 'opacity-50' : ''}>
        <ResponsiveContainer width="100%" height={300}>
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
              tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#fdfcfc',
                border: '1px solid rgba(15,0,0,0.12)',
                borderRadius: 4,
                fontSize: 12,
              }}
              labelStyle={{ color: '#646262' }}
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              formatter={(value: any) => [`${(Number(value) * 100).toFixed(2)}%`]}
            />
            <Legend
              wrapperStyle={{ fontSize: 12, color: '#646262' }}
            />
            {groupLabels.map((g, i) => (
              <Line
                key={g}
                type="monotone"
                dataKey={g}
                name={`第${g}组`}
                stroke={GROUP_COLORS[i % GROUP_COLORS.length]}
                dot={false}
                strokeWidth={1.5}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </Card>
    </div>
  );
}
