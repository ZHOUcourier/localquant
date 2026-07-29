import React, { useEffect, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import { Sparkles } from 'lucide-react';
import { useFlowStore } from '@/store/flowStore';
import { ScrollArea } from '@/components/ui/ScrollArea';

/** 后端 /runs/{run_id}/nodes/{uuid}/output 返回的单字段预览 */
interface FieldPreview {
  name: string;
  kind: 'table' | 'series' | 'multiseries' | 'metrics' | 'image' | 'images' | 'scalar' | 'json';
  columns?: string[];
  rows?: Record<string, unknown>[];
  shape?: [number, number];
  x?: string[];
  y?: number[];
  series?: { name: string; y: (number | null)[] }[];
  data?: unknown;
}

const METRIC_LABELS: Record<string, string> = {
  total_return: '总收益',
  annual_return: '年化收益',
  annual_volatility: '年化波动',
  sharpe_ratio: '夏普比率',
  max_drawdown: '最大回撤',
  calmar_ratio: '卡玛比率',
  win_rate: '胜率',
  trading_days: '交易天数',
  initial_capital: '初始资金',
};

const PCT_KEYS = new Set([
  'total_return', 'annual_return', 'annual_volatility', 'max_drawdown', 'win_rate',
]);

const FIELD_LABELS: Record<string, string> = {
  equity_curve: '净值曲线',
  strategy_returns: '策略收益率',
  drawdown_curve: '回撤曲线',
  positions: '持仓',
  metrics: '绩效指标',
  monthly_returns: '月度收益',
  benchmark_curve: '基准净值',
  summary: '关键指标',
  group_perf: '分组绩效',
  ic_summary: '各周期 IC 汇总',
  group_cumulative: '分组累计收益',
  group_excess_cumulative: '分组超额累计收益',
  ic_series: 'IC / Rank_IC 时序',
  ic_cumulative: 'IC / Rank_IC 累计',
  ic_decay: 'IC / Rank_IC 衰减',
  ic_distribution: 'IC 分布',
  ic_autocorr: 'IC / Rank_IC 自相关',
  latest_ranking: '最新一期因子值排名',
};

function fmtMetric(key: string, v: unknown): string {
  if (typeof v !== 'number') return String(v);
  if (PCT_KEYS.has(key)) return `${(v * 100).toFixed(2)}%`;
  if (Number.isInteger(v)) return String(v);
  return v.toFixed(4);
}

/** 指标卡 */
function MetricsCards({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data);
  if (entries.length === 0) return null;
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
      {entries.map(([k, v]) => (
        <div
          key={k}
          style={{
            background: '#fdfcfc',
            border: '1px solid rgba(15,0,0,0.12)',
            borderRadius: 4,
            padding: '6px 12px',
            minWidth: 90,
          }}
        >
          <div style={{ color: '#646262', fontSize: 10, marginBottom: 2 }}>
            {METRIC_LABELS[k] || k}
          </div>
          <div
            style={{
              color:
                typeof v === 'number' && (k === 'max_drawdown' ? v < 0 : false)
                  ? '#ff3b30'
                  : '#201d1d',
              fontSize: 14,
              fontWeight: 600,
              fontFamily: 'var(--font-mono, monospace)',
            }}
          >
            {fmtMetric(k, v)}
          </div>
        </div>
      ))}
    </div>
  );
}

/** 时间序列曲线 */
function SeriesChart({ field }: { field: FieldPreview }) {
  const isDrawdown = field.name.toLowerCase().includes('drawdown');
  const color = isDrawdown ? '#ff3b30' : '#007aff';
  const option = {
    grid: { left: 56, right: 16, top: 10, bottom: 22 },
    tooltip: {
      trigger: 'axis',
      textStyle: { fontSize: 11 },
      valueFormatter: (v: number) => (typeof v === 'number' ? v.toFixed(4) : String(v)),
    },
    xAxis: {
      type: 'category',
      data: (field.x || []).map((s) => s.slice(0, 10)),
      axisLabel: { fontSize: 10, color: '#646262' },
      axisLine: { lineStyle: { color: 'rgba(15,0,0,0.2)' } },
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLabel: { fontSize: 10, color: '#646262' },
      splitLine: { lineStyle: { color: 'rgba(15,0,0,0.06)' } },
    },
    series: [
      {
        type: 'line',
        data: field.y || [],
        showSymbol: false,
        lineStyle: { width: 1.4, color },
        areaStyle: { color, opacity: 0.08 },
      },
    ],
  };
  return <ReactECharts option={option} style={{ height: 220, width: '100%' }} notMerge />;
}

const MULTI_COLORS = ['#ff3b30', '#ff9f0a', '#ffd60a', '#30d158', '#007aff', '#64d2ff', '#bf5af2', '#a2845e'];

/** 多线时间序列图（分组累计收益 / IC 时序等） */
function MultiSeriesChart({ field }: { field: FieldPreview }) {
  const series = field.series || [];
  const option = {
    grid: { left: 56, right: 16, top: 28, bottom: 22 },
    legend: { top: 0, textStyle: { fontSize: 10, color: '#646262' }, type: 'scroll' as const },
    tooltip: {
      trigger: 'axis' as const,
      textStyle: { fontSize: 11 },
      valueFormatter: (v: number) => (typeof v === 'number' ? v.toFixed(4) : String(v)),
    },
    xAxis: {
      type: 'category' as const,
      data: field.x || [],
      axisLabel: { fontSize: 10, color: '#646262' },
      axisLine: { lineStyle: { color: 'rgba(15,0,0,0.2)' } },
    },
    yAxis: {
      type: 'value' as const,
      scale: true,
      axisLabel: { fontSize: 10, color: '#646262' },
      splitLine: { lineStyle: { color: 'rgba(15,0,0,0.06)' } },
    },
    series: series.map((s, i) => ({
      name: s.name,
      type: 'line' as const,
      data: s.y,
      showSymbol: false,
      lineStyle: { width: 1.4, color: MULTI_COLORS[i % MULTI_COLORS.length] },
      itemStyle: { color: MULTI_COLORS[i % MULTI_COLORS.length] },
    })),
  };
  return <ReactECharts option={option} style={{ height: 260, width: '100%' }} notMerge />;
}

/** 表格 */
function TableView({ field }: { field: FieldPreview }) {
  const columns = field.columns || [];
  const rows = field.rows || [];
  if (rows.length === 0) {
    return <div style={{ color: '#646262', fontSize: 11 }}>（空表格）</div>;
  }
  return (
    <div style={{ maxHeight: 240, overflow: 'auto', border: '1px solid rgba(15,0,0,0.12)', borderRadius: 4 }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: 'monospace', fontSize: 11 }}>
        <thead>
          <tr>
            {columns.map((col) => (
              <th
                key={col}
                style={{
                  padding: '4px 10px',
                  textAlign: 'left',
                  borderBottom: '1px solid rgba(15,0,0,0.12)',
                  color: '#646262',
                  fontWeight: 500,
                  whiteSpace: 'nowrap',
                  background: '#f1eeee',
                  position: 'sticky',
                  top: 0,
                }}
              >
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIdx) => (
            <tr key={rowIdx}>
              {columns.map((col) => {
                const v = row[col];
                return (
                  <td
                    key={col}
                    style={{
                      padding: '3px 10px',
                      borderBottom: '1px solid rgba(15,0,0,0.06)',
                      color: '#201d1d',
                      whiteSpace: 'nowrap',
                      maxWidth: 260,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}
                  >
                    {v == null
                      ? '-'
                      : typeof v === 'number' && !Number.isInteger(v)
                      ? v.toFixed(4)
                      : String(v)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {field.shape && field.shape[0] > rows.length && (
        <div style={{ color: '#9a9898', fontSize: 10, padding: '4px 10px' }}>
          共 {field.shape[0]} 行，仅展示前 {rows.length} 行
        </div>
      )}
    </div>
  );
}

/** 单个输出字段渲染 */
function FieldBlock({ field }: { field: FieldPreview }) {
  const label = FIELD_LABELS[field.name] || field.name;
  let body: React.ReactNode;
  switch (field.kind) {
    case 'series':
      body = <SeriesChart field={field} />;
      break;
    case 'multiseries':
      body = <MultiSeriesChart field={field} />;
      break;
    case 'metrics':
      body = <MetricsCards data={(field.data as Record<string, unknown>) || {}} />;
      break;
    case 'table':
      body = <TableView field={field} />;
      break;
    case 'image':
      body = (
        <img
          src={String(field.data)}
          alt={field.name}
          style={{ maxWidth: '100%', border: '1px solid rgba(15,0,0,0.12)', borderRadius: 4 }}
        />
      );
      break;
    case 'images':
      body = (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {((field.data as string[]) || []).map((src, i) => (
            <img
              key={i}
              src={src}
              alt={`${field.name}-${i}`}
              style={{ maxWidth: '48%', border: '1px solid rgba(15,0,0,0.12)', borderRadius: 4 }}
            />
          ))}
        </div>
      );
      break;
    case 'scalar':
      body = (
        <span style={{ color: '#201d1d', fontSize: 13, fontWeight: 600, fontFamily: 'var(--font-mono, monospace)' }}>
          {typeof field.data === 'number' && !Number.isInteger(field.data)
            ? (field.data as number).toFixed(4)
            : String(field.data)}
        </span>
      );
      break;
    default:
      body = (
        <pre
          style={{
            margin: 0,
            padding: 8,
            background: '#fdfcfc',
            border: '1px solid rgba(15,0,0,0.12)',
            borderRadius: 4,
            fontSize: 11,
            maxHeight: 180,
            overflow: 'auto',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-all',
          }}
        >
          {JSON.stringify(field.data, null, 2)}
        </pre>
      );
  }
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ color: '#646262', fontSize: 11, fontWeight: 600, marginBottom: 6 }}>
        {label}
        {field.shape && (
          <span style={{ fontWeight: 400, color: '#9a9898' }}>
            {' '}({field.shape[0]} × {field.shape[1]})
          </span>
        )}
      </div>
      {body}
    </div>
  );
}

const hintStyle: React.CSSProperties = {
  color: '#646262',
  fontSize: 12,
  padding: 16,
  fontFamily: 'monospace',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  height: '100%',
};

/** 因子分析节点结果的 AI 综合分析（复用 /api/ai/factor-report） */
function AIAnalysisPanel({ fields }: { fields: FieldPreview[] }) {
  const [text, setText] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const summaryField = fields.find((f) => f.name === 'summary' && f.kind === 'metrics');
  if (!summaryField) return null;
  const summary = (summaryField.data as Record<string, unknown>) || {};
  const perfField = fields.find((f) => f.name === 'group_perf' && f.kind === 'table');
  const groupPerf = (perfField?.rows as Record<string, unknown>[]) || [];

  const handleAI = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/ai/factor-report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ summary, group_perf: groupPerf }),
      });
      if (!res.ok) {
        const e = await res.json().catch(() => null);
        throw new Error(e?.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      setText(data.analysis || '');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ marginBottom: 14 }}>
      <button
        onClick={handleAI}
        disabled={loading}
        style={{
          display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer',
          border: '1px solid #007aff', background: 'rgba(0,122,255,0.1)', color: '#007aff',
          borderRadius: 4, padding: '4px 12px', fontSize: 12, fontWeight: 500, opacity: loading ? 0.5 : 1,
        }}
      >
        <Sparkles size={13} />
        {loading ? 'AI 分析中...' : 'AI 综合分析'}
      </button>
      {error && (
        <div style={{ marginTop: 8, border: '1px solid #ff3b30', background: 'rgba(255,59,48,0.1)', color: '#ff3b30', borderRadius: 4, padding: '6px 10px', fontSize: 11 }}>{error}</div>
      )}
      {text && (
        <div style={{ marginTop: 8, maxHeight: 320, overflow: 'auto', whiteSpace: 'pre-wrap', border: '1px solid rgba(0,122,255,0.3)', background: 'rgba(0,122,255,0.05)', borderRadius: 4, padding: '10px 12px', fontSize: 11, lineHeight: 1.6, color: '#424245' }}>
          {text}
        </div>
      )}
    </div>
  );
}

export const ResultViewer: React.FC = () => {
  const selectedNodeId = useFlowStore((s) => s.selectedNodeId);
  const nodeStatuses = useFlowStore((s) => s.nodeStatuses);
  const currentRunId = useFlowStore((s) => s.currentRunId);

  const [fields, setFields] = useState<FieldPreview[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedStatus = selectedNodeId ? nodeStatuses[selectedNodeId] : null;

  // 拉取选中节点的运行产物预览
  useEffect(() => {
    setFields(null);
    setError(null);
    if (!selectedNodeId || !currentRunId || selectedStatus !== 'success') return;
    let cancelled = false;
    setLoading(true);
    fetch(`/api/workflow/runs/${currentRunId}/nodes/${selectedNodeId}/output`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data) => {
        if (!cancelled) {
          setFields(data.fields || []);
          setLoading(false);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e));
          setLoading(false);
        }
      });
    return () => { cancelled = true; };
  }, [selectedNodeId, currentRunId, selectedStatus]);

  if (!selectedNodeId || selectedStatus !== 'success') {
    return <div style={hintStyle}>运行工作流后，点击已完成的节点查看输出</div>;
  }
  if (loading) {
    return <div style={hintStyle}>加载输出中...</div>;
  }
  if (error) {
    return <div style={{ ...hintStyle, color: '#ff3b30' }}>输出加载失败: {error}</div>;
  }
  if (!fields || fields.length === 0) {
    return <div style={hintStyle}>该节点暂无输出数据</div>;
  }

  // 排序：指标卡优先，其次曲线/图片，再表格，最后其他
  const kindOrder: Record<string, number> = { metrics: 0, series: 1, multiseries: 1, image: 2, images: 2, table: 3, scalar: 4, json: 5 };
  const sorted = [...fields].sort((a, b) => (kindOrder[a.kind] ?? 9) - (kindOrder[b.kind] ?? 9));

  return (
    <ScrollArea maxHeight={360}>
      <div style={{ padding: '12px 16px' }}>
        <AIAnalysisPanel fields={fields} />
        {sorted.map((f) => (
          <FieldBlock key={f.name} field={f} />
        ))}
      </div>
    </ScrollArea>
  );
};
