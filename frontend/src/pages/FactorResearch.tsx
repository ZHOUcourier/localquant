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
import FactorLibrary from '@/components/factor/FactorLibrary';
import FactorPool from '@/components/factor/FactorPool';
import SystemResourceMonitor from '@/components/factor/SystemResourceMonitor';
import ComprehensiveReport from '@/components/factor/ComprehensiveReport';
import type { FactorReport } from '@/components/factor/ComprehensiveReport';

echarts.use([HeatmapChart, GridComponent, TooltipComponent, VisualMapComponent, CanvasRenderer]);

// 页级主 tab：因子研究 | 因子库
const pageTabs: TabItem[] = [
  { key: 'research', label: '因子研究' },
  { key: 'library', label: '因子库' },
];

// 因子库子 tab
const libraryTabs: TabItem[] = [
  { key: 'preset', label: '预置因子' },
  { key: 'pool', label: '因子池' },
  { key: 'custom', label: '自建因子' },
];

type FactorMatrix = Record<string, Record<string, number>>;

interface CorrData {
  names: string[];
  matrix: number[][];
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
  const [pageTab, setPageTab] = useState('research');
  const [libraryTab, setLibraryTab] = useState('preset');
  const [evaluating, setEvaluating] = useState(false);
  const [evalError, setEvalError] = useState<string | null>(null);
  const [nGroups, setNGroups] = useState(5);

  // 全部来自后端真实计算，初始为空
  const [report, setReport] = useState<FactorReport | null>(null);
  const [corrData, setCorrData] = useState<CorrData | null>(null);
  const [computedFactors, setComputedFactors] = useState<Record<string, FactorMatrix>>({});
  const [currentFactor, setCurrentFactor] = useState<string | null>(null);
  const [returnData, setReturnData] = useState<FactorMatrix | null>(null);

  /** 对指定因子矩阵执行完整评估：一次 /api/factor/analysis 得到综合报告（与因子分析节点同源） */
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
      const rep = await postJson<FactorReport>('/api/factor/analysis', {
        factor_data: values,
        return_data: returns,
        n_groups: groups,
      });
      setReport(rep);

      // 相关性（需要至少 2 个因子）
      if (Object.keys(allFactors).length >= 2) {
        const cRes = await postJson<{
          matrix: Record<string, Record<string, number>>;
          factor_names: string[];
        }>('/api/factor/correlation', { factors: allFactors });
        const names = cRes.factor_names;
        setCorrData({ names, matrix: names.map((a) => names.map((b) => cRes.matrix[a]?.[b] ?? 0)) });
      } else {
        setCorrData(null);
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
    if (currentFactor === name) { setCurrentFactor(null); setReport(null); }
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
      axisLine: { lineStyle: { color: '#d8d4d4' } },
    },
    yAxis: {
      type: 'category' as const,
      data: corrData.names,
      splitArea: { show: true },
      axisLabel: { color: '#646262', fontSize: 11 },
      axisLine: { lineStyle: { color: '#d8d4d4' } },
    },
    visualMap: {
      min: -1,
      max: 1,
      calculable: true,
      orient: 'vertical' as const,
      right: 0,
      top: 'center' as const,
      inRange: { color: ['#ff3b30', '#f1eeee', '#30d158'] },
      textStyle: { color: '#646262' },
    },
    series: [
      {
        name: '相关性',
        type: 'heatmap' as const,
        data: corrData.matrix.flatMap((row, i) => row.map((val, j) => [i, j, val])),
        label: {
          show: true,
          color: '#201d1d',
          fontSize: 11,
          formatter: (params: { value: number[] }) => params.value[2].toFixed(2),
        },
        emphasis: { itemStyle: { borderColor: '#646262', borderWidth: 1 } },
      },
    ],
  };

  const factorNames = Object.keys(computedFactors);

  return (
    <div className="flex h-full flex-col gap-4 overflow-auto">
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
          {/* 已计算因子 + 分层组数 + 合成 */}
          <div className="flex flex-wrap items-center gap-2 rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-3 py-2">
            <span className="text-xs text-[#646262]">已计算因子:</span>
            {factorNames.length === 0 && <span className="font-mono text-xs text-[#9a9898]">（暂无 — 在左下构建并计算）</span>}
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
                  className="cursor-pointer text-[#9a9898] opacity-0 transition-opacity hover:text-[#ff3b30] group-hover:opacity-100"
                  title="移除"
                >
                  <Trash2 size={11} />
                </button>
              </span>
            ))}
            <div className="ml-auto flex items-center gap-2">
              <span className="text-xs text-[#646262]">分层组数:</span>
              {[3, 5, 10].map(g => (
                <button
                  key={g}
                  onClick={() => handleGroupsChange(g)}
                  disabled={evaluating}
                  className={`cursor-pointer rounded-[4px] border px-2 py-0.5 font-mono text-xs transition-colors disabled:opacity-50 ${
                    nGroups === g
                      ? 'border-[#007aff] bg-[#007aff]/10 text-[#007aff]'
                      : 'border-[rgba(15,0,0,0.12)] text-[#646262] hover:text-[#201d1d]'
                  }`}
                >
                  {g}组
                </button>
              ))}
              <Button
                variant="secondary"
                size="sm"
                disabled={factorNames.length < 2 || evaluating}
                onClick={handleCombine}
                className="flex items-center gap-1 text-xs"
              >
                <Layers size={12} />
                等权合成
              </Button>
            </div>
          </div>

          {evalError && (
            <div className="rounded-[4px] border border-[#ff3b30] bg-[#ff3b30]/10 px-3 py-2 font-mono text-xs text-[#ff3b30]">
              {evalError}
            </div>
          )}

          {/* 上排：左=因子基本数据与操作 / 右=系统资源 */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <FactorBuilder onFactorComputed={handleFactorComputed} />
            </div>
            <Card className="lg:col-span-1">
              <SystemResourceMonitor />
            </Card>
          </div>

          {/* 下方：全宽综合报告 */}
          <Card>
            <ComprehensiveReport report={report} factorName={currentFactor} loading={evaluating} />
            {corrData && corrOption && (
              <div className="mt-4 border-t border-[rgba(15,0,0,0.08)] pt-4">
                <div className="mb-2 text-xs font-semibold text-[#201d1d]">因子相关性（{corrData.names.length} 个因子）</div>
                <div className="rounded-[4px] border border-[rgba(15,0,0,0.12)] p-2">
                  <ReactEChartsCore echarts={echarts} option={corrOption} style={{ height: 360, width: '100%' }} notMerge />
                </div>
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
