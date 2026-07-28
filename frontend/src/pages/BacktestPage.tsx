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

export default function BacktestPage() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleRun = useCallback(async (config: BacktestConfigData) => {
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await fetch('/api/backtest/run-strategy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          signal_code: config.signalCode,
          stock_pool: config.stockPool,
          start_date: config.startDate,
          end_date: config.endDate,
          initial_capital: config.initialCapital,
          commission_rate: config.commissionRate,
          slippage: config.slippage,
        }),
      });

      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail ?? `回测接口错误 (HTTP ${response.status})`);
      }

      const data = await response.json();
      setResult({
        equityCurve: data.equity_curve,
        strategyReturns: data.strategy_returns,
        drawdownSeries: data.drawdown_series ?? {},
        initialCapital: data.initial_capital,
        tearSheet: data.tear_sheet,
      });
    } catch (e) {
      // 不使用任何模拟数据兜底，直接展示真实错误
      const msg = e instanceof TypeError
        ? '无法连接后端服务 (http://localhost:8000)，请先运行 make dev 或 make dev-backend'
        : e instanceof Error ? e.message : String(e);
      setError(msg);
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
            <div className="rounded-[4px] border border-[#ff3b30] bg-[#ff3b30]/10 px-4 py-3 font-mono text-sm text-[#ff3b30]">
              {error}
            </div>
          )}

          {!result && !loading && !error && (
            <div className="flex h-full items-center justify-center">
              <div className="text-center">
                <div className="mb-2 font-mono text-sm text-[#9a9898]">配置左侧参数，运行回测查看结果</div>
                <div className="font-mono text-xs text-[#6e6e73]">回测基于本地缓存行情数据，请先在「数据管理」页下载数据</div>
              </div>
            </div>
          )}

          {loading && (
            <div className="flex h-full items-center justify-center">
              <div className="text-center">
                <div className="mb-2 h-8 w-8 mx-auto animate-spin rounded-full border-2 border-[#007aff] border-t-transparent" />
                <div className="font-mono text-sm text-[#9a9898]">回测运行中...</div>
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
