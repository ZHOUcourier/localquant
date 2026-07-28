import { useMemo } from 'react';
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { Card } from '@/components/ui/Card';

export interface EquityCurveProps {
  /** {date: equity_value} */
  equityCurve: Record<string, number>;
  /** {date: strategy_return} */
  strategyReturns?: Record<string, number>;
  /** {date: benchmark_equity} */
  benchmarkCurve?: Record<string, number>;
  /** {date: drawdown_value} */
  drawdownSeries?: Record<string, number>;
  initialCapital?: number;
}

interface ChartPoint {
  date: string;
  strategy: number;
  benchmark: number;
  drawdown: number;
}

function formatDate(dateStr: string) {
  // "2023-01-15" → "01-15"
  return dateStr.slice(5);
}

function formatPct(v: number) {
  return `${(v * 100).toFixed(2)}%`;
}

function formatMoney(v: number) {
  if (Math.abs(v) >= 1e8) return `${(v / 1e8).toFixed(2)}亿`;
  if (Math.abs(v) >= 1e4) return `${(v / 1e4).toFixed(1)}万`;
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 0 });
}

const CustomTooltip = ({ active, payload, label }: { active?: boolean; payload?: Array<{ value: number; name: string; color: string }>; label?: string }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded border border-[#30363d] bg-[#161b22] px-3 py-2 text-xs shadow-lg">
      <div className="mb-1 text-[#808080]">{label}</div>
      {payload.map((p, i) => (
        <div key={i} className="flex items-center gap-2">
          <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: p.color }} />
          <span className="text-[#808080]">{p.name}:</span>
          <span className="font-mono text-[#eeeeee]">
            {p.name.includes('净值') ? formatMoney(p.value) : formatPct(p.value)}
          </span>
        </div>
      ))}
    </div>
  );
};

export function EquityCurve({
  equityCurve,
  benchmarkCurve,
  drawdownSeries,
  initialCapital = 1000000,
}: EquityCurveProps) {
  const data = useMemo<ChartPoint[]>(() => {
    const dates = Object.keys(equityCurve).sort();
    return dates.map((date) => {
      const eqVal = equityCurve[date] ?? 0;
      const bmVal = benchmarkCurve?.[date] ?? initialCapital;
      const ddVal = drawdownSeries?.[date] ?? 0;
      // 归一化为收益率
      const strategyReturn = eqVal / initialCapital - 1;
      const benchmarkReturn = bmVal / initialCapital - 1;
      return {
        date: formatDate(date),
        strategy: strategyReturn,
        benchmark: benchmarkReturn,
        drawdown: ddVal,
      };
    });
  }, [equityCurve, benchmarkCurve, drawdownSeries, initialCapital]);

  // 稀疏 x-axis ticks
  const tickInterval = useMemo(() => {
    const len = data.length;
    if (len <= 30) return 5;
    if (len <= 100) return 15;
    return Math.floor(len / 10);
  }, [data.length]);

  if (data.length === 0) return null;

  return (
    <div className="flex flex-col gap-4">
      {/* 累计收益曲线 */}
      <Card title="累计收益曲线">
        <div className="h-[260px]">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#30363d" vertical={false} />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 11, fill: '#808080' }}
                tickLine={false}
                axisLine={{ stroke: '#30363d' }}
                interval={tickInterval}
              />
              <YAxis
                tick={{ fontSize: 11, fill: '#808080' }}
                tickLine={false}
                axisLine={false}
                tickFormatter={formatPct}
                width={60}
              />
              <Tooltip content={<CustomTooltip />} />
              <Legend
                wrapperStyle={{ fontSize: 12, color: '#808080' }}
                iconType="line"
              />
              <ReferenceLine y={0} stroke="#555555" strokeDasharray="2 2" />
              <Line
                type="monotone"
                dataKey="strategy"
                name="策略"
                stroke="#fab283"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, fill: '#fab283' }}
              />
              {benchmarkCurve && (
                <Line
                  type="monotone"
                  dataKey="benchmark"
                  name="基准"
                  stroke="#56b6c2"
                  strokeWidth={1.5}
                  dot={false}
                  strokeDasharray="4 2"
                  activeDot={{ r: 3, fill: '#56b6c2' }}
                />
              )}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* 回撤曲线 */}
      <Card title="回撤曲线">
        <div className="h-[160px]">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#30363d" vertical={false} />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 11, fill: '#808080' }}
                tickLine={false}
                axisLine={{ stroke: '#30363d' }}
                interval={tickInterval}
              />
              <YAxis
                tick={{ fontSize: 11, fill: '#808080' }}
                tickLine={false}
                axisLine={false}
                tickFormatter={formatPct}
                width={60}
              />
              <Tooltip content={<CustomTooltip />} />
              <Area
                type="monotone"
                dataKey="drawdown"
                name="回撤"
                stroke="#e06c75"
                strokeWidth={1.5}
                fill="#e06c75"
                fillOpacity={0.2}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </Card>
    </div>
  );
}
