import { useMemo } from 'react';
import { Card } from '@/components/ui/Card';

export interface TearSheetData {
  annual_return: number;
  max_drawdown: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  calmar_ratio: number;
  win_rate: number;
  profit_loss_ratio: number;
  var_95: number;
  total_return?: number;
  volatility?: number;
  cvar_95?: number;
  trading_days?: number;
  monthly_returns?: Record<string, Record<string, number>>;
}

interface TearSheetProps {
  data: TearSheetData;
}

interface MetricCardProps {
  label: string;
  value: number;
  format: 'pct' | 'ratio' | 'pct_signed';
}

function MetricCard({ label, value, format }: MetricCardProps) {
  let displayValue: string;
  let colorClass: string;

  if (format === 'pct') {
    displayValue = `${(value * 100).toFixed(2)}%`;
    colorClass = value > 0 ? 'text-[#30d158]' : value < 0 ? 'text-[#ff3b30]' : 'text-[#fdfcfc]';
  } else if (format === 'pct_signed') {
    displayValue = `${(value * 100).toFixed(2)}%`;
    colorClass = value > 0 ? 'text-[#30d158]' : value < 0 ? 'text-[#ff3b30]' : 'text-[#fdfcfc]';
  } else {
    displayValue = value.toFixed(3);
    colorClass = value > 0 ? 'text-[#30d158]' : value < 0 ? 'text-[#ff3b30]' : 'text-[#fdfcfc]';
  }

  return (
    <div className="rounded border border-[#403b3b] bg-[#302c2c] px-3 py-2.5">
      <div className="text-xs text-[#9a9898] mb-1">{label}</div>
      <div className={`text-lg font-mono font-semibold ${colorClass}`}>
        {displayValue}
      </div>
    </div>
  );
}

const MONTHS = ['01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12'];
const MONTH_LABELS = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'];

function getHeatmapColor(value: number, maxAbs: number): string {
  if (maxAbs === 0) return '#302c2c';
  const intensity = Math.min(Math.abs(value) / maxAbs, 1);
  if (value > 0) {
    // green shades
    const alpha = 0.15 + intensity * 0.7;
    return `rgba(127, 216, 143, ${alpha})`;
  } else if (value < 0) {
    // red shades
    const alpha = 0.15 + intensity * 0.7;
    return `rgba(224, 108, 117, ${alpha})`;
  }
  return '#302c2c';
}

function MonthlyHeatmap({ monthlyReturns }: { monthlyReturns: Record<string, Record<string, number>> }) {
  const years = Object.keys(monthlyReturns).sort();

  const maxAbs = useMemo(() => {
    let max = 0;
    for (const year of years) {
      for (const month of MONTHS) {
        const val = monthlyReturns[year]?.[month] ?? 0;
        max = Math.max(max, Math.abs(val));
      }
    }
    return max;
  }, [monthlyReturns, years]);

  if (years.length === 0) return null;

  return (
    <Card title="月度收益热力图">
      <div className="overflow-x-auto">
        <table className="w-full text-xs font-mono">
          <thead>
            <tr>
              <th className="text-left text-[#9a9898] font-normal pr-2 py-1 sticky left-0 bg-[#262222]">年份</th>
              {MONTH_LABELS.map((m) => (
                <th key={m} className="text-center text-[#9a9898] font-normal px-1 py-1">{m}</th>
              ))}
              <th className="text-center text-[#9a9898] font-normal px-1 py-1">全年</th>
            </tr>
          </thead>
          <tbody>
            {years.map((year) => {
              const months = monthlyReturns[year] ?? {};
              // 计算年度收益
              let annualRet = 0;
              for (const m of MONTHS) {
                const v = months[m];
                if (v !== undefined) annualRet = (1 + annualRet) * (1 + v) - 1;
              }
              return (
                <tr key={year}>
                  <td className="text-[#9a9898] pr-2 py-0.5 sticky left-0 bg-[#262222]">{year}</td>
                  {MONTHS.map((m) => {
                    const val = months[m];
                    const hasData = val !== undefined;
                    return (
                      <td key={m} className="text-center px-0.5 py-0.5">
                        <div
                          className="rounded px-1 py-1 text-center"
                          style={{
                            backgroundColor: hasData ? getHeatmapColor(val, maxAbs) : '#302c2c',
                            color: hasData ? (val > 0 ? '#30d158' : val < 0 ? '#ff3b30' : '#9a9898') : '#6e6e73',
                          }}
                        >
                          {hasData ? `${(val * 100).toFixed(1)}%` : '—'}
                        </div>
                      </td>
                    );
                  })}
                  <td className="text-center px-1 py-0.5">
                    <span className={annualRet > 0 ? 'text-[#30d158]' : annualRet < 0 ? 'text-[#ff3b30]' : 'text-[#9a9898]'}>
                      {(annualRet * 100).toFixed(1)}%
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export function TearSheet({ data }: TearSheetProps) {
  const metrics: MetricCardProps[] = [
    { label: '年化收益', value: data.annual_return, format: 'pct_signed' },
    { label: '最大回撤', value: data.max_drawdown, format: 'pct' },
    { label: 'Sharpe', value: data.sharpe_ratio, format: 'ratio' },
    { label: 'Sortino', value: data.sortino_ratio, format: 'ratio' },
    { label: 'Calmar', value: data.calmar_ratio, format: 'ratio' },
    { label: '胜率', value: data.win_rate, format: 'pct' },
    { label: '盈亏比', value: data.profit_loss_ratio, format: 'ratio' },
    { label: 'VaR (95%)', value: data.var_95, format: 'pct' },
  ];

  return (
    <div className="flex flex-col gap-4">
      {/* 指标卡片网格 */}
      <div className="grid grid-cols-4 gap-2">
        {metrics.map((m) => (
          <MetricCard key={m.label} {...m} />
        ))}
      </div>

      {/* 月度收益热力图 */}
      {data.monthly_returns && Object.keys(data.monthly_returns).length > 0 && (
        <MonthlyHeatmap monthlyReturns={data.monthly_returns} />
      )}
    </div>
  );
}
