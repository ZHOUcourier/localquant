import { useState, useCallback } from 'react';
import { Tabs, Card } from '@/components/ui';
import type { TabItem } from '@/components/ui';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { HeatmapChart } from 'echarts/charts';
import {
  GridComponent,
  TooltipComponent,
  VisualMapComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import FactorBuilder from '@/components/factor/FactorBuilder';
import type { FactorResult } from '@/components/factor/FactorBuilder';
import ICAnalysis from '@/components/factor/ICAnalysis';
import type { ICDataPoint, ICStats } from '@/components/factor/ICAnalysis';
import QuantileChart from '@/components/factor/QuantileChart';
import type { QuantileDataPoint, QuantileStats } from '@/components/factor/QuantileChart';
import FactorLibrary from '@/components/factor/FactorLibrary';

echarts.use([HeatmapChart, GridComponent, TooltipComponent, VisualMapComponent, CanvasRenderer]);

// 因子评估 tab
const evalTabs: TabItem[] = [
  { key: 'ic', label: 'IC 分析' },
  { key: 'quantile', label: '分层收益' },
  { key: 'correlation', label: '相关性' },
];

interface ICData {
  series: ICDataPoint[];
  stats: ICStats;
}

interface QuantileData {
  data: QuantileDataPoint[];
  stats: QuantileStats;
}

interface CorrData {
  names: string[];
  matrix: number[][];
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="flex h-[280px] items-center justify-center rounded-[4px] border border-[rgba(15,0,0,0.12)]">
      <span className="font-mono text-xs text-[#9a9898]">{text}</span>
    </div>
  );
}

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error(data?.detail ?? `接口错误 (HTTP ${res.status})`);
  }
  return res.json();
}

export default function FactorResearch() {
  const [evalTab, setEvalTab] = useState('ic');
  const [evaluating, setEvaluating] = useState(false);
  const [evalError, setEvalError] = useState<string | null>(null);

  // 全部来自后端真实计算，初始为空
  const [icData, setIcData] = useState<ICData | null>(null);
  const [quantileData, setQuantileData] = useState<QuantileData | null>(null);
  const [corrData, setCorrData] = useState<CorrData | null>(null);
  // 已计算的因子集合（用于相关性分析，需要 >= 2 个因子）
  const [computedFactors, setComputedFactors] = useState<Record<string, Record<string, Record<string, number>>>>({});

  const handleFactorComputed = useCallback(async (result: FactorResult) => {
    setEvaluating(true);
    setEvalError(null);

    const factors = { ...computedFactors, [result.name]: result.values };
    setComputedFactors(factors);

    try {
      // IC 分析
      const icRes = await postJson<Record<string, {
        ic_series: { date: string; ic: number | null }[];
        rank_ic_series: { date: string; rank_ic: number | null }[];
        ic_mean: number;
        ic_ir: number;
        rank_ic_mean: number;
        ic_positive_ratio: number;
      }>>('/api/factor/ic-analysis', {
        factor_data: result.values,
        return_data: result.returnData,
        periods: [1],
      });
      const p1 = icRes['period_1'];
      if (p1) {
        const rankByDate = new Map(p1.rank_ic_series.map((r) => [r.date, r.rank_ic]));
        setIcData({
          series: p1.ic_series
            .filter((d) => d.ic != null)
            .map((d) => ({
              date: d.date.slice(0, 10),
              ic: d.ic as number,
              rank_ic: rankByDate.get(d.date) ?? undefined,
            })),
          stats: {
            mean: p1.ic_mean,
            ir: p1.ic_ir,
            rank_ic: p1.rank_ic_mean,
            positive_ratio: p1.ic_positive_ratio,
          },
        });
      }

      // 分层收益
      const qRes = await postJson<{
        group_returns: Record<string, { date: string; return: number }[]>;
        cumulative_returns: Record<string, number>;
      }>('/api/factor/quantile', {
        factor_data: result.values,
        return_data: result.returnData,
        n_groups: 5,
      });
      const groupKeys = Object.keys(qRes.group_returns).sort();
      const cumByDate = new Map<string, Record<string, number>>();
      for (const key of groupKeys) {
        const label = key.replace('group_', '');
        let cum = 0;
        for (const point of qRes.group_returns[key]) {
          const date = point.date.slice(0, 10);
          cum = (1 + cum) * (1 + point.return) - 1;
          if (!cumByDate.has(date)) cumByDate.set(date, {});
          cumByDate.get(date)![label] = cum;
        }
      }
      const qPoints: QuantileDataPoint[] = [...cumByDate.entries()]
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([date, groups]) => ({ date, groups }));
      const groupReturns: Record<string, number> = {};
      for (const [key, v] of Object.entries(qRes.cumulative_returns)) {
        groupReturns[key.replace('group_', '')] = v;
      }
      const labels = Object.keys(groupReturns).sort();
      const longShort = labels.length >= 2
        ? (groupReturns[labels[labels.length - 1]] ?? 0) - (groupReturns[labels[0]] ?? 0)
        : 0;
      setQuantileData({ data: qPoints, stats: { groupReturns, longShortReturn: longShort } });

      // 相关性（需要至少 2 个因子）
      if (Object.keys(factors).length >= 2) {
        const cRes = await postJson<{
          matrix: Record<string, Record<string, number>>;
          factor_names: string[];
        }>('/api/factor/correlation', { factors });
        const names = cRes.factor_names;
        setCorrData({
          names,
          matrix: names.map((a) => names.map((b) => cRes.matrix[a]?.[b] ?? 0)),
        });
      }
    } catch (e) {
      const msg = e instanceof TypeError
        ? '无法连接后端服务 (http://localhost:8000)，请先运行 make dev 或 make dev-backend'
        : e instanceof Error ? e.message : String(e);
      setEvalError(msg);
    } finally {
      setEvaluating(false);
    }
  }, [computedFactors]);

  const corrOption = corrData && {
    tooltip: {
      position: 'top' as const,
      formatter: (params: { value: number[] }) => {
        const [x, y, val] = params.value;
        return `${corrData.names[y as number]} vs ${corrData.names[x as number]}: ${val}`;
      },
    },
    grid: { top: 10, right: 80, bottom: 60, left: 80 },
    xAxis: {
      type: 'category' as const,
      data: corrData.names,
      splitArea: { show: true },
      axisLabel: { color: '#9a9898', fontSize: 11 },
      axisLine: { lineStyle: { color: '#403b3b' } },
    },
    yAxis: {
      type: 'category' as const,
      data: corrData.names,
      splitArea: { show: true },
      axisLabel: { color: '#9a9898', fontSize: 11 },
      axisLine: { lineStyle: { color: '#403b3b' } },
    },
    visualMap: {
      min: -1,
      max: 1,
      calculable: true,
      orient: 'vertical' as const,
      right: 0,
      top: 'center' as const,
      inRange: {
        color: ['#ff3b30', '#302c2c', '#30d158'],
      },
      textStyle: { color: '#9a9898' },
    },
    series: [
      {
        name: '相关性',
        type: 'heatmap' as const,
        data: corrData.matrix.flatMap((row, i) =>
          row.map((val, j) => [i, j, val])
        ),
        label: {
          show: true,
          color: '#fdfcfc',
          fontSize: 11,
          formatter: (params: { value: number[] }) => params.value[2].toFixed(2),
        },
        emphasis: {
          itemStyle: { borderColor: '#9a9898', borderWidth: 1 },
        },
      },
    ],
  };

  return (
    <div className="flex flex-col gap-4 p-4 h-full overflow-auto">
      <h1 className="text-xl font-semibold text-[#201d1d]">因子研究</h1>

      {/* 上半部分: 因子构建器 + 因子评估 */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* 区域 1: 因子构建器 */}
        <FactorBuilder onFactorComputed={handleFactorComputed} />

        {/* 区域 2: 因子评估 */}
        <Card title="因子评估" className="h-full flex flex-col">
          <Tabs items={evalTabs} activeKey={evalTab} onChange={setEvalTab} />
          <div className="mt-3 flex-1 overflow-auto">
            {evalError && (
              <div className="mb-3 rounded-[4px] border border-[#ff3b30] bg-[#ff3b30]/10 px-3 py-2 font-mono text-xs text-[#ff3b30]">
                {evalError}
              </div>
            )}
            {evalTab === 'ic' && (
              icData ? (
                <ICAnalysis icSeries={icData.series} stats={icData.stats} loading={evaluating} />
              ) : (
                <EmptyState text={evaluating ? '评估计算中...' : '暂无评估数据 — 请先在左侧构建并计算因子'} />
              )
            )}
            {evalTab === 'quantile' && (
              quantileData ? (
                <QuantileChart data={quantileData.data} stats={quantileData.stats} loading={evaluating} />
              ) : (
                <EmptyState text={evaluating ? '评估计算中...' : '暂无评估数据 — 请先在左侧构建并计算因子'} />
              )
            )}
            {evalTab === 'correlation' && (
              corrData && corrOption ? (
                <div className="rounded-[4px] border border-[rgba(15,0,0,0.12)] p-2">
                  <ReactEChartsCore
                    echarts={echarts}
                    option={corrOption}
                    style={{ height: 360, width: '100%' }}
                    notMerge
                  />
                </div>
              ) : (
                <EmptyState text={`相关性分析需要至少 2 个因子（当前已计算 ${Object.keys(computedFactors).length} 个）`} />
              )
            )}
          </div>
        </Card>
      </div>

      {/* 下半部分: 因子库 */}
      <FactorLibrary />
    </div>
  );
}
