import { useState, useCallback } from 'react';
import { BacktestConfig, type BacktestConfigData } from '@/components/backtest/BacktestConfig';
import { EquityCurve } from '@/components/backtest/EquityCurve';
import { TearSheet, type TearSheetData } from '@/components/backtest/TearSheet';
import { ScrollArea } from '@/components/ui/ScrollArea';

interface BacktestResult {
  equityCurve: Record<string, number>;
  strategyReturns: Record<string, number>;
  drawdownSeries: Record<string, number>;
  tearSheet: TearSheetData;
  initialCapital: number;
}

// 生成模拟回测数据（用于演示）
function generateMockResult(config: BacktestConfigData): BacktestResult {
  const start = new Date(config.startDate);
  const end = new Date(config.endDate);
  const days: string[] = [];
  const d = new Date(start);
  while (d <= end) {
    if (d.getDay() !== 0 && d.getDay() !== 6) {
      days.push(d.toISOString().slice(0, 10));
    }
    d.setDate(d.getDate() + 1);
  }

  const n = days.length;
  const dailyReturn = config.initialCapital * (0.15 / 252);
  const dailyVol = config.initialCapital * (0.2 / Math.sqrt(252));

  let equity = config.initialCapital;
  const equityCurve: Record<string, number> = {};
  const strategyReturns: Record<string, number> = {};
  const drawdownSeries: Record<string, number> = {};
  let peak = config.initialCapital;

  // 月度收益
  const monthlyReturns: Record<string, Record<string, number>> = {};

  for (const day of days) {
    const ret = (dailyReturn + (Math.random() - 0.5) * dailyVol * 2) / config.initialCapital;
    equity = equity * (1 + ret);
    equityCurve[day] = equity;
    strategyReturns[day] = ret;
    peak = Math.max(peak, equity);
    drawdownSeries[day] = equity / peak - 1;

    const [y, m] = [day.slice(0, 4), day.slice(5, 7)];
    if (!monthlyReturns[y]) monthlyReturns[y] = {};
    if (!monthlyReturns[y][m]) monthlyReturns[y][m] = 0;
    monthlyReturns[y][m] = (1 + monthlyReturns[y][m]) * (1 + ret) - 1;
  }

  const totalReturn = equity / config.initialCapital - 1;
  const annFactor = 252 / n;
  const annualReturn = (1 + totalReturn) ** annFactor - 1;
  const vol = Math.sqrt(Object.values(strategyReturns).reduce((s, r) => s + r * r, 0) / n) * Math.sqrt(252);
  const dailyRf = 1.03 ** (1 / 252) - 1;
  const excessReturns = Object.values(strategyReturns).map((r) => r - dailyRf);
  const meanExcess = excessReturns.reduce((a, b) => a + b, 0) / n;
  const stdExcess = Math.sqrt(excessReturns.reduce((s, e) => s + (e - meanExcess) ** 2, 0) / n);
  const sharpe = stdExcess > 0 ? (meanExcess / stdExcess) * Math.sqrt(252) : 0;

  const downsideReturns = excessReturns.filter((r) => r < 0);
  const downsideStd = downsideReturns.length > 0
    ? Math.sqrt(downsideReturns.reduce((s, r) => s + r * r, 0) / downsideReturns.length) * Math.sqrt(252)
    : 1e-9;
  const sortino = downsideStd > 0 ? (annualReturn - 0.03) / downsideStd : 0;

  const maxDd = Math.min(...Object.values(drawdownSeries));
  const calmar = maxDd !== 0 ? annualReturn / Math.abs(maxDd) : 0;

  const wins = Object.values(strategyReturns).filter((r) => r > 0);
  const losses = Object.values(strategyReturns).filter((r) => r < 0);
  const winRate = wins.length / n;
  const avgWin = wins.length > 0 ? wins.reduce((a, b) => a + b, 0) / wins.length : 0;
  const avgLoss = losses.length > 0 ? Math.abs(losses.reduce((a, b) => a + b, 0) / losses.length) : 1e-9;

  const sortedReturns = Object.values(strategyReturns).sort((a, b) => a - b);
  const varIdx = Math.floor(n * 0.05);
  const var95 = sortedReturns[varIdx] ?? 0;

  return {
    equityCurve,
    strategyReturns,
    drawdownSeries,
    initialCapital: config.initialCapital,
    tearSheet: {
      annual_return: annualReturn,
      max_drawdown: maxDd,
      sharpe_ratio: sharpe,
      sortino_ratio: sortino,
      calmar_ratio: calmar,
      win_rate: winRate,
      profit_loss_ratio: avgLoss > 0 ? avgWin / avgLoss : 0,
      var_95: var95,
      total_return: totalReturn,
      volatility: vol,
      trading_days: n,
      monthly_returns: monthlyReturns,
    },
  };
}

export default function BacktestPage() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleRun = useCallback(async (config: BacktestConfigData) => {
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      // 调用后端 API（若后端不可用则使用模拟数据）
      const response = await fetch('/api/backtest/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          signals: {},
          prices: {},
          initial_capital: config.initialCapital,
          commission_rate: config.commissionRate,
          slippage: config.slippage,
        }),
      });

      if (response.ok) {
        const data = await response.json();
        // 获取 tear sheet
        const tsResponse = await fetch('/api/backtest/tear-sheet', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            returns: data.strategy_returns,
            risk_free_rate: 0.03,
          }),
        });

        if (tsResponse.ok) {
          const tsData = await tsResponse.json();
          setResult({
            equityCurve: data.equity_curve,
            strategyReturns: data.strategy_returns,
            drawdownSeries: tsData.drawdown_series ?? {},
            initialCapital: data.initial_capital,
            tearSheet: {
              annual_return: tsData.annual_return,
              max_drawdown: tsData.max_drawdown,
              sharpe_ratio: tsData.sharpe_ratio,
              sortino_ratio: tsData.sortino_ratio,
              calmar_ratio: tsData.calmar_ratio,
              win_rate: tsData.win_rate,
              profit_loss_ratio: tsData.profit_loss_ratio,
              var_95: tsData.var_95,
              total_return: tsData.total_return,
              volatility: tsData.volatility,
              trading_days: tsData.trading_days,
              monthly_returns: tsData.monthly_returns,
            },
          });
        } else {
          throw new Error('Tear sheet API failed');
        }
      } else {
        throw new Error('Backtest API failed');
      }
    } catch {
      // 后端不可用，使用模拟数据
      const mockResult = generateMockResult(config);
      setResult(mockResult);
    } finally {
      setLoading(false);
    }
  }, []);

  return (
    <div className="flex h-full gap-4 p-4">
      {/* 左侧：回测配置 */}
      <div className="w-[420px] flex-shrink-0 flex flex-col">
        <ScrollArea className="h-full">
          <BacktestConfig onRun={handleRun} loading={loading} />
        </ScrollArea>
      </div>

      {/* 右侧：回测结果 */}
      <div className="flex-1 min-w-0">
        <ScrollArea className="h-full">
          {error && (
            <div className="rounded border border-[#e06c75] bg-[#e06c75]/10 px-4 py-3 text-sm text-[#e06c75]">
              {error}
            </div>
          )}

          {!result && !loading && !error && (
            <div className="flex h-full items-center justify-center">
              <div className="text-center">
                <div className="mb-2 text-4xl text-[#30363d]">📊</div>
                <div className="text-sm text-[#808080]">配置左侧参数，运行回测查看结果</div>
              </div>
            </div>
          )}

          {loading && (
            <div className="flex h-full items-center justify-center">
              <div className="text-center">
                <div className="mb-2 h-8 w-8 mx-auto animate-spin rounded-full border-2 border-[#fab283] border-t-transparent" />
                <div className="text-sm text-[#808080]">回测运行中...</div>
              </div>
            </div>
          )}

          {result && (
            <div className="flex flex-col gap-4">
              {/* 绩效指标 + 热力图 */}
              <TearSheet data={result.tearSheet} />

              {/* 收益曲线 + 回撤 */}
              <EquityCurve
                equityCurve={result.equityCurve}
                drawdownSeries={result.drawdownSeries}
                initialCapital={result.initialCapital}
              />
            </div>
          )}
        </ScrollArea>
      </div>
    </div>
  );
}
