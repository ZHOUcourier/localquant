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
  '#e06c75', // group 1 (worst)
  '#f5a742',
  '#e5c07b',
  '#98c379',
  '#7fd88f', // group 5 (best)
  '#56b6c2',
  '#61afef',
  '#c678dd',
];

function CumulativeCard({ label, value }: { label: string; value: string }) {
  const isPositive = parseFloat(value) > 0;
  return (
    <div className="flex flex-col items-center rounded-[4px] border border-[#30363d] bg-[#21262d] px-3 py-2">
      <span className="text-xs text-[#808080]">{label}</span>
      <span className={`text-lg font-semibold font-mono ${isPositive ? 'text-[#7fd88f]' : 'text-[#e06c75]'}`}>
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
              tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#161b22',
                border: '1px solid #30363d',
                borderRadius: 4,
                fontSize: 12,
              }}
              labelStyle={{ color: '#808080' }}
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              formatter={(value: any) => [`${(Number(value) * 100).toFixed(2)}%`]}
            />
            <Legend
              wrapperStyle={{ fontSize: 12, color: '#808080' }}
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
