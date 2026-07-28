import { useState, useCallback } from 'react';
import { Tabs, Card, Button } from '@/components/ui';
import type { TabItem } from '@/components/ui';
import { Layers, Trash2 } from 'lucide-react';
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
import FactorPool from '@/components/factor/FactorPool';

echarts.use([HeatmapChart, GridComponent, TooltipComponent, VisualMapComponent, CanvasRenderer]);

// 页级主 tab：因子研究 | 因子库
const pageTabs: TabItem[] = [
  { key: 'research', label: '因子研究' },
  { key: 'library', label: '因子库' },
];

// 因子评估 tab
const evalTabs: TabItem[] = [
  { key: 'ic', label: 'IC 分析' },
  { key: 'quantile', label: '分层收益' },
  { key: 'correlation', label: '相关性' },
];

// 因子库子 tab
const libraryTabs: TabItem[] = [
  { key: 'preset', label: '预置因子' },
  { key: 'pool', label: '因子池' },
  { key: 'custom', label: '自建因子' },
];

// IC 分析周期
const IC_PERIODS = [1, 5, 10, 20];

type FactorMatrix = Record<string, Record<string, number>>;

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

interface ICApiPeriod {
  ic_series: { date: string; ic: number | null }[];
  rank_ic_series: { date: string; rank_ic: number | null }[];
  ic_mean: number;
  ic_ir: number;
  rank_ic_mean: number;
  ic_positive_ratio: number;
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="flex h-[280px] items-center justify-center rounded-[4px] border border-[rgba(15,0,0,0.12)]">
      <span className="font-mono text-xs text-[#646262]">{text}</span>
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

function toICData(p: ICApiPeriod): ICData {
  const rankByDate = new Map(p.rank_ic_series.map((r) => [r.date, r.rank_ic]));
  return {
    series: p.ic_series
      .filter((d) => d.ic != null)
      .map((d) => ({
        date: d.date.slice(0, 10),
        ic: d.ic as number,
        rank_ic: rankByDate.get(d.date) ?? undefined,
      })),
    stats: {
      mean: p.ic_mean,
      ir: p.ic_ir,
      rank_ic: p.rank_ic_mean,
      positive_ratio: p.ic_positive_ratio,
    },
  };
}

export default function FactorResearch() {
  const [pageTab, setPageTab] = useState('research');
  const [libraryTab, setLibraryTab] = useState('preset');
  const [evalTab, setEvalTab] = useState('ic');
  const [evaluating, setEvaluating] = useState(false);
  const [evalError, setEvalError] = useState<string | null>(null);

  // 评估参数
  const [icPeriod, setIcPeriod] = useState(1);
  const [nGroups, setNGroups] = useState(5);

  // 全部来自后端真实计算，初始为空
  const [icByPeriod, setIcByPeriod] = useState<Record<number, ICData>>({});
  const [quantileData, setQuantileData] = useState<QuantileData | null>(null);
  const [corrData, setCorrData] = useState<CorrData | null>(null);
  const [computedFactors, setComputedFactors] = useState<Record<string, FactorMatrix>>({});
  const [currentFactor, setCurrentFactor] = useState<string | null>(null);
  // 记录最近一次收益数据，供参数变更 / 因子合成后重新评估
  const [returnData, setReturnData] = useState<FactorMatrix | null>(null);

  /** 对指定因子矩阵执行完整评估（多周期 IC + 分层 + 相关性） */
  const evaluate = useCallback(async (
    name: string,
    values: FactorMatrix,
    returns: FactorMatrix,
    allFactors: Record<string, FactorMatrix>,
    groups: number,
  ) => {
    setEvaluating(true);
    setEvalError(null);
    try {
      // 多周期 IC 分析：一次请求同时计算 1/5/10/20 日
      const icRes = await postJson<Record<string, ICApiPeriod>>('/api/factor/ic-analysis', {
        factor_data: values,
        return_data: returns,
        periods: IC_PERIODS,
      });
      const byPeriod: Record<number, ICData> = {};
      for (const p of IC_PERIODS) {
        const item = icRes[`period_${p}`];
        if (item) byPeriod[p] = toICData(item);
      }
      setIcByPeriod(byPeriod);

      // 分层收益
      const qRes = await postJson<{
        group_returns: Record<string, { date: string; return: number }[]>;
        cumulative_returns: Record<string, number>;
      }>('/api/factor/quantile', {
        factor_data: values,
        return_data: returns,
        n_groups: groups,
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
        .map(([date, g]) => ({ date, groups: g }));
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
      if (Object.keys(allFactors).length >= 2) {
        const cRes = await postJson<{
          matrix: Record<string, Record<string, number>>;
          factor_names: string[];
        }>('/api/factor/correlation', { factors: allFactors });
        const names = cRes.factor_names;
        setCorrData({
          names,
          matrix: names.map((a) => names.map((b) => cRes.matrix[a]?.[b] ?? 0)),
        });
      }
      setCurrentFactor(name);
    } catch (e) {
      const msg = e instanceof TypeError
        ? '无法连接后端服务 (http://localhost:8000)，请先运行 make dev 或 make dev-backend'
        : e instanceof Error ? e.message : String(e);
      setEvalError(msg);
    } finally {
      setEvaluating(false);
    }
  }, []);

  const handleFactorComputed = useCallback(async (result: FactorResult) => {
    const factors = { ...computedFactors, [result.name]: result.values };
    setComputedFactors(factors);
    setReturnData(result.returnData);
    await evaluate(result.name, result.values, result.returnData, factors, nGroups);
  }, [computedFactors, evaluate, nGroups]);

  /** 切换分层组数后重新评估当前因子 */
  const handleGroupsChange = useCallback(async (groups: number) => {
    setNGroups(groups);
    if (currentFactor && returnData && computedFactors[currentFactor]) {
      await evaluate(currentFactor, computedFactors[currentFactor], returnData, computedFactors, groups);
    }
  }, [currentFactor, returnData, computedFactors, evaluate]);

  /** 点击已计算因子 → 重新评估该因子 */
  const handleSelectFactor = useCallback(async (name: string) => {
    if (!returnData || !computedFactors[name]) return;
    await evaluate(name, computedFactors[name], returnData, computedFactors, nGroups);
  }, [returnData, computedFactors, evaluate, nGroups]);

  const handleRemoveFactor = useCallback((name: string) => {
    setComputedFactors(prev => {
      const next = { ...prev };
      delete next[name];
      return next;
    });
    if (currentFactor === name) setCurrentFactor(null);
  }, [currentFactor]);

  /** 多因子等权合成（后端 /api/factor/combine），并将合成结果作为新因子评估 */
  const handleCombine = useCallback(async () => {
    if (Object.keys(computedFactors).length < 2 || !returnData) return;
    setEvaluating(true);
    setEvalError(null);
    try {
      const combined = await postJson<FactorMatrix>('/api/factor/combine', { factors: computedFactors });
      const name = `合成因子(${Object.keys(computedFactors).length})`;
      const factors = { ...computedFactors, [name]: combined };
      setComputedFactors(factors);
      await evaluate(name, combined, returnData, factors, nGroups);
    } catch (e) {
      setEvalError(e instanceof Error ? e.message : String(e));
      setEvaluating(false);
    }
  }, [computedFactors, returnData, evaluate, nGroups]);

  const icData = icByPeriod[icPeriod] ?? null;

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
      axisLabel: { color: '#646262', fontSize: 11 },
      axisLine: { lineStyle: { color: '#403b3b' } },
    },
    yAxis: {
      type: 'category' as const,
      data: corrData.names,
      splitArea: { show: true },
      axisLabel: { color: '#646262', fontSize: 11 },
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
      textStyle: { color: '#646262' },
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
          itemStyle: { borderColor: '#646262', borderWidth: 1 },
        },
      },
    ],
  };

  const factorNames = Object.keys(computedFactors);

  return (
    <div className="flex flex-col gap-4 h-full overflow-auto">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-[#201d1d]">因子研究</h1>
        <Tabs items={pageTabs} activeKey={pageTab} onChange={setPageTab} />
      </div>

      {pageTab === 'library' ? (
        /* ============ 因子库 ============ */
        <div className="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] p-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-base font-bold text-[#201d1d]">因子库</h2>
            <Tabs items={libraryTabs} activeKey={libraryTab} onChange={setLibraryTab} />
          </div>

          {libraryTab === 'preset' ? (
            <FactorLibrary />
          ) : libraryTab === 'pool' ? (
            <FactorPool />
          ) : (
            <div className="flex h-[200px] items-center justify-center rounded-[4px] border border-[rgba(15,0,0,0.12)]">
              <span className="text-xs text-[#646262]">自建因子功能开发中...</span>
            </div>
          )}
        </div>
      ) : (
        /* ============ 因子研究 ============ */
        <>
          {/* 已计算因子列表 + 合成 */}
          {factorNames.length > 0 && (
            <div className="flex flex-wrap items-center gap-2 rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-3 py-2">
              <span className="text-xs text-[#646262]">已计算因子:</span>
              {factorNames.map(name => (
                <span
                  key={name}
                  className={`group inline-flex cursor-pointer items-center gap-1 rounded-[4px] border px-2 py-0.5 font-mono text-xs transition-colors ${
                    currentFactor === name
                      ? 'border-[#007aff] bg-[#007aff]/10 text-[#007aff]'
                      : 'border-[rgba(15,0,0,0.12)] text-[#646262] hover:text-[#201d1d]'
                  }`}
                  onClick={() => handleSelectFactor(name)}
                  title="点击评估该因子"
                >
                  {name}
                  <button
                    onClick={(e) => { e.stopPropagation(); handleRemoveFactor(name); }}
                    className="opacity-0 group-hover:opacity-100 text-[#9a9898] hover:text-[#ff3b30] transition-opacity cursor-pointer"
                    title="移除"
                  >
                    <Trash2 size={11} />
                  </button>
                </span>
              ))}
              <Button
                variant="secondary"
                size="sm"
                disabled={factorNames.length < 2 || evaluating}
                onClick={handleCombine}
                className="ml-auto flex items-center gap-1 text-xs"
              >
                <Layers size={12} />
                等权合成
              </Button>
            </div>
          )}

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {/* 因子构建器 */}
            <FactorBuilder onFactorComputed={handleFactorComputed} />

            {/* 因子评估 */}
            <Card title={currentFactor ? `因子评估 — ${currentFactor}` : '因子评估'} className="h-full flex flex-col">
              <Tabs items={evalTabs} activeKey={evalTab} onChange={setEvalTab} />
              <div className="mt-3 flex-1 overflow-auto">
                {evalError && (
                  <div className="mb-3 rounded-[4px] border border-[#ff3b30] bg-[#ff3b30]/10 px-3 py-2 font-mono text-xs text-[#ff3b30]">
                    {evalError}
                  </div>
                )}
                {evalTab === 'ic' && (
                  <>
                    <div className="mb-3 flex items-center gap-1">
                      <span className="mr-1 text-xs text-[#646262]">预测周期:</span>
                      {IC_PERIODS.map(p => (
                        <button
                          key={p}
                          onClick={() => setIcPeriod(p)}
                          className={`cursor-pointer rounded-[4px] border px-2 py-0.5 font-mono text-xs transition-colors ${
                            icPeriod === p
                              ? 'border-[#007aff] bg-[#007aff]/10 text-[#007aff]'
                              : 'border-[rgba(15,0,0,0.12)] text-[#646262] hover:text-[#201d1d]'
                          }`}
                        >
                          {p}日
                        </button>
                      ))}
                    </div>
                    {icData ? (
                      <ICAnalysis icSeries={icData.series} stats={icData.stats} loading={evaluating} />
                    ) : (
                      <EmptyState text={evaluating ? '评估计算中...' : '暂无评估数据 — 请先在左侧构建并计算因子'} />
                    )}
                  </>
                )}
                {evalTab === 'quantile' && (
                  <>
                    <div className="mb-3 flex items-center gap-1">
                      <span className="mr-1 text-xs text-[#646262]">分层组数:</span>
                      {[3, 5, 10].map(g => (
                        <button
                          key={g}
                          onClick={() => handleGroupsChange(g)}
                          className={`cursor-pointer rounded-[4px] border px-2 py-0.5 font-mono text-xs transition-colors ${
                            nGroups === g
                              ? 'border-[#007aff] bg-[#007aff]/10 text-[#007aff]'
                              : 'border-[rgba(15,0,0,0.12)] text-[#646262] hover:text-[#201d1d]'
                          }`}
                        >
                          {g}组
                        </button>
                      ))}
                    </div>
                    {quantileData ? (
                      <QuantileChart data={quantileData.data} stats={quantileData.stats} loading={evaluating} />
                    ) : (
                      <EmptyState text={evaluating ? '评估计算中...' : '暂无评估数据 — 请先在左侧构建并计算因子'} />
                    )}
                  </>
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
                    <EmptyState text={`相关性分析需要至少 2 个因子（当前已计算 ${factorNames.length} 个）`} />
                  )
                )}
              </div>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
