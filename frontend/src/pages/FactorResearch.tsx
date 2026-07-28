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

// 生成模拟 IC 数据
function generateMockIC(): { series: ICDataPoint[]; stats: ICStats } {
  const dates: string[] = [];
  const series: ICDataPoint[] = [];
  const base = new Date('2024-01-02');
  for (let i = 0; i < 60; i++) {
    const d = new Date(base);
    d.setDate(d.getDate() + i);
    if (d.getDay() === 0 || d.getDay() === 6) continue;
    const dateStr = d.toISOString().slice(0, 10);
    dates.push(dateStr);
    const ic = (Math.random() - 0.45) * 0.1;
    series.push({ date: dateStr, ic, rank_ic: ic + (Math.random() - 0.5) * 0.02 });
  }
  const ics = series.map((s) => s.ic);
  const mean = ics.reduce((a, b) => a + b, 0) / ics.length;
  const std = Math.sqrt(ics.map((x) => (x - mean) ** 2).reduce((a, b) => a + b, 0) / ics.length);
  return {
    series,
    stats: {
      mean,
      ir: std > 0 ? mean / std : 0,
      rank_ic: series.reduce((a, s) => a + (s.rank_ic ?? 0), 0) / series.length,
      positive_ratio: ics.filter((x) => x > 0).length / ics.length,
    },
  };
}

// 生成模拟分层数据
function generateMockQuantile(): { data: QuantileDataPoint[]; stats: QuantileStats } {
  const data: QuantileDataPoint[] = [];
  const base = new Date('2024-01-02');
  const groupCum: Record<string, number> = { '1': 0, '2': 0, '3': 0, '4': 0, '5': 0 };
  for (let i = 0; i < 60; i++) {
    const d = new Date(base);
    d.setDate(d.getDate() + i);
    if (d.getDay() === 0 || d.getDay() === 6) continue;
    const dateStr = d.toISOString().slice(0, 10);
    const groups: Record<string, number> = {};
    for (const g of Object.keys(groupCum)) {
      const r = (Math.random() - 0.5) * 0.02 + (parseInt(g) - 3) * 0.001;
      groupCum[g] += r;
      groups[g] = groupCum[g];
    }
    data.push({ date: dateStr, groups });
  }
  return {
    data,
    stats: {
      groupReturns: { ...groupCum },
      longShortReturn: groupCum['5'] - groupCum['1'],
    },
  };
}

// 生成模拟相关性矩阵
function generateMockCorrelation(): { names: string[]; matrix: number[][] } {
  const names = ['动量', '价值', '质量', '波动率', '技术'];
  const matrix: number[][] = [];
  for (let i = 0; i < names.length; i++) {
    matrix[i] = [];
    for (let j = 0; j < names.length; j++) {
      if (i === j) {
        matrix[i][j] = 1;
      } else if (j < i) {
        matrix[i][j] = matrix[j][i];
      } else {
        matrix[i][j] = Math.round((Math.random() - 0.5) * 2 * 100) / 100;
      }
    }
  }
  return { names, matrix };
}

export default function FactorResearch() {
  const [evalTab, setEvalTab] = useState('ic');
  const [_factorResult, setFactorResult] = useState<FactorResult | null>(null);

  // 模拟数据（实际应从后端获取）
  const [icData] = useState(generateMockIC);
  const [quantileData] = useState(generateMockQuantile);
  const [corrData] = useState(generateMockCorrelation);

  const handleFactorComputed = useCallback((result: FactorResult) => {
    setFactorResult(result);
  }, []);

  const corrOption = {
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
      axisLabel: { color: '#808080', fontSize: 11 },
      axisLine: { lineStyle: { color: '#30363d' } },
    },
    yAxis: {
      type: 'category' as const,
      data: corrData.names,
      splitArea: { show: true },
      axisLabel: { color: '#808080', fontSize: 11 },
      axisLine: { lineStyle: { color: '#30363d' } },
    },
    visualMap: {
      min: -1,
      max: 1,
      calculable: true,
      orient: 'vertical' as const,
      right: 0,
      top: 'center' as const,
      inRange: {
        color: ['#e06c75', '#21262d', '#7fd88f'],
      },
      textStyle: { color: '#808080' },
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
          color: '#eeeeee',
          fontSize: 11,
          formatter: (params: { value: number[] }) => params.value[2].toFixed(2),
        },
        emphasis: {
          itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.5)' },
        },
      },
    ],
  };

  return (
    <div className="flex flex-col gap-4 p-4 h-full overflow-auto">
      <h1 className="text-xl font-semibold text-[#eeeeee]">因子研究</h1>

      {/* 上半部分: 因子构建器 + 因子评估 */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* 区域 1: 因子构建器 */}
        <FactorBuilder onFactorComputed={handleFactorComputed} />

        {/* 区域 2: 因子评估 */}
        <Card title="因子评估" className="h-full flex flex-col">
          <Tabs items={evalTabs} activeKey={evalTab} onChange={setEvalTab} />
          <div className="mt-3 flex-1 overflow-auto">
            {evalTab === 'ic' && (
              <ICAnalysis icSeries={icData.series} stats={icData.stats} />
            )}
            {evalTab === 'quantile' && (
              <QuantileChart data={quantileData.data} stats={quantileData.stats} />
            )}
            {evalTab === 'correlation' && (
              <div className="rounded-[4px] border border-[#30363d] p-2">
                <ReactEChartsCore
                  echarts={echarts}
                  option={corrOption}
                  style={{ height: 360, width: '100%' }}
                  notMerge
                />
              </div>
            )}
          </div>
        </Card>
      </div>

      {/* 下半部分: 因子库 */}
      <FactorLibrary />
    </div>
  );
}
