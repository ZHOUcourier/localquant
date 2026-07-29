import { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import ReactECharts from 'echarts-for-react';
import { Sparkles } from 'lucide-react';
import { Dialog } from '@/components/ui/Dialog';

/** 与 ResultViewer 一致：/runs/{run_id}/nodes/{uuid}/output 的单字段预览 */
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

const LINE_COLORS = ['#ff3b30', '#ff9f0a', '#ffd60a', '#30d158', '#007aff', '#64d2ff', '#bf5af2', '#a2845e'];
const AXIS_LABEL = { fontSize: 10, color: '#646262' };
const SPLIT_LINE = { lineStyle: { color: 'rgba(15,0,0,0.06)' } };

/** 分组绩效表列（对齐因子研究页综合报告） */
const PERF_LABELS: Record<string, string> = {
  group: '分组',
  annualizedReturn: '年化收益率',
  excessAnnualized: '超额年化',
  maxDrawdown: '最大回撤',
  excessMaxDrawdown: '超额最大回撤',
  annualizedVolatility: '年化波动',
  excessAnnualizedVolatility: '超额年化波动',
  turnoverRate: '换手率',
  monthlyWinRate: '月度胜率',
  excessMonthlyWinRate: '超额月度胜率',
  trackingError: '跟踪误差',
  sharpeRatio: '夏普比率',
  informationRatio: '信息比率',
};
const PERF_PCT = new Set([
  'annualizedReturn', 'excessAnnualized', 'maxDrawdown', 'excessMaxDrawdown',
  'annualizedVolatility', 'excessAnnualizedVolatility', 'turnoverRate',
  'monthlyWinRate', 'excessMonthlyWinRate',
]);

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <div style={{ fontSize: 12, fontWeight: 600, color: '#201d1d', marginBottom: 8 }}>{children}</div>;
}

const CARD_STYLE: React.CSSProperties = {
  border: '1px solid rgba(15,0,0,0.12)',
  borderRadius: 4,
  background: '#fdfcfc',
  padding: 12,
};

/** 数据卡（summary 的键由后端返回，已是中文标签） */
function SummaryCards({ data }: { data: Record<string, unknown> }) {
  const pctKeys = new Set(['因子收益', '年化收益', '最大回撤', 'P(IC<-0.02)', 'P(IC>0.02)']);
  const posKeys = new Set(['因子收益', '年化收益', '夏普比率', 'IC_mean', 'Rank_IC', 'IC_IR', 'IR']);
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 8 }}>
      {Object.entries(data).map(([k, v]) => {
        const num = typeof v === 'number' ? v : NaN;
        const color = k === '最大回撤'
          ? '#ff3b30'
          : posKeys.has(k)
          ? (num > 0 ? '#ff453a' : num < 0 ? '#30d158' : '#201d1d')
          : '#201d1d';
        return (
          <div key={k} style={{ ...CARD_STYLE, padding: '8px 10px' }}>
            <div style={{ color: '#646262', fontSize: 10, marginBottom: 2, whiteSpace: 'nowrap' }}>{k}</div>
            <div style={{ color, fontSize: 14, fontWeight: 600, fontFamily: 'var(--font-mono, monospace)' }}>
              {Number.isNaN(num) ? String(v) : pctKeys.has(k) ? `${(num * 100).toFixed(2)}%` : num.toFixed(4)}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** 多线时间序列图 */
function MultiLine({ field, height = 240 }: { field: FieldPreview; height?: number }) {
  const option = {
    grid: { left: 52, right: 12, top: 26, bottom: 20 },
    legend: { top: 0, textStyle: { fontSize: 10, color: '#646262' }, type: 'scroll' as const },
    tooltip: {
      trigger: 'axis' as const,
      textStyle: { fontSize: 11 },
      valueFormatter: (v: number) => (typeof v === 'number' ? v.toFixed(4) : String(v)),
    },
    xAxis: {
      type: 'category' as const,
      data: field.x || [],
      axisLabel: AXIS_LABEL,
      axisLine: { lineStyle: { color: 'rgba(15,0,0,0.2)' } },
    },
    yAxis: { type: 'value' as const, scale: true, axisLabel: AXIS_LABEL, splitLine: SPLIT_LINE },
    series: (field.series || []).map((s, i) => ({
      name: s.name,
      type: 'line' as const,
      data: s.y,
      showSymbol: false,
      lineStyle: { width: 1.4, color: LINE_COLORS[i % LINE_COLORS.length] },
      itemStyle: { color: LINE_COLORS[i % LINE_COLORS.length] },
    })),
  };
  return <ReactECharts option={option} style={{ height, width: '100%' }} notMerge />;
}

/** 柱状图（衰减/自相关/分布 —— 从表格行构造） */
function BarsFromRows({
  rows, xKey, valueKeys, height = 220,
}: { rows: Record<string, unknown>[]; xKey: string; valueKeys: string[]; height?: number }) {
  const option = {
    grid: { left: 52, right: 12, top: 26, bottom: 20 },
    legend: valueKeys.length > 1
      ? { top: 0, textStyle: { fontSize: 10, color: '#646262' } }
      : undefined,
    tooltip: {
      trigger: 'axis' as const,
      textStyle: { fontSize: 11 },
      valueFormatter: (v: number) => (typeof v === 'number' ? v.toFixed(4) : String(v)),
    },
    xAxis: {
      type: 'category' as const,
      data: rows.map((r) => {
        const v = r[xKey];
        return typeof v === 'number' && !Number.isInteger(v) ? v.toFixed(3) : String(v);
      }),
      axisLabel: AXIS_LABEL,
      axisLine: { lineStyle: { color: 'rgba(15,0,0,0.2)' } },
    },
    yAxis: { type: 'value' as const, scale: true, axisLabel: AXIS_LABEL, splitLine: SPLIT_LINE },
    series: valueKeys.map((k, i) => ({
      name: k,
      type: 'bar' as const,
      data: rows.map((r) => (typeof r[k] === 'number' ? (r[k] as number) : null)),
      itemStyle: { color: LINE_COLORS[(i + 4) % LINE_COLORS.length], opacity: 0.85 },
      barMaxWidth: 18,
    })),
  };
  return <ReactECharts option={option} style={{ height, width: '100%' }} notMerge />;
}

/** 通用表格 */
function DataTable({ field, labels, pctKeys, maxHeight = 260 }: {
  field: FieldPreview;
  labels?: Record<string, string>;
  pctKeys?: Set<string>;
  maxHeight?: number;
}) {
  const columns = field.columns || [];
  const rows = field.rows || [];
  if (rows.length === 0) return <div style={{ color: '#646262', fontSize: 11 }}>（空表格）</div>;
  return (
    <div style={{ maxHeight, overflow: 'auto', border: '1px solid rgba(15,0,0,0.12)', borderRadius: 4 }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: 'monospace', fontSize: 11 }}>
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col} style={{
                padding: '4px 10px', textAlign: 'left', borderBottom: '1px solid rgba(15,0,0,0.12)',
                color: '#646262', fontWeight: 500, whiteSpace: 'nowrap', background: '#f1eeee',
                position: 'sticky', top: 0,
              }}>
                {labels?.[col] || col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {columns.map((col) => {
                const v = row[col];
                const text = v == null
                  ? '-'
                  : typeof v === 'number' && pctKeys?.has(col)
                  ? `${(v * 100).toFixed(2)}%`
                  : typeof v === 'number' && !Number.isInteger(v)
                  ? v.toFixed(4)
                  : String(v);
                return (
                  <td key={col} style={{
                    padding: '3px 10px', borderBottom: '1px solid rgba(15,0,0,0.06)',
                    color: '#201d1d', whiteSpace: 'nowrap',
                  }}>
                    {text}
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

interface FactorReportDialogProps {
  open: boolean;
  onClose: () => void;
  runId: string;
  nodeUuid: string;
  nodeLabel?: string;
}

/**
 * 因子分析综合报告弹窗 —— 在工作流「因子分析」节点上点击「查看分析报告」打开。
 * 数据来源与底部结果面板一致（/runs/{id}/nodes/{uuid}/output），
 * 布局对齐因子研究页综合报告：数据卡 + AI 分析 + 分组绩效 + 全套 IC 图表 + 最新排名。
 */
export function FactorReportDialog({ open, onClose, runId, nodeUuid, nodeLabel }: FactorReportDialogProps) {
  const [fields, setFields] = useState<FieldPreview[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [aiText, setAiText] = useState<string | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setFields(null);
    setAiText(null);
    setAiError(null);
    fetch(`/api/workflow/runs/${runId}/nodes/${nodeUuid}/output`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data) => {
        if (!cancelled) { setFields(data.fields || []); setLoading(false); }
      })
      .catch((e) => {
        if (!cancelled) { setError(e instanceof Error ? e.message : String(e)); setLoading(false); }
      });
    return () => { cancelled = true; };
  }, [open, runId, nodeUuid]);

  const f = useMemo(() => {
    const map: Record<string, FieldPreview> = {};
    (fields || []).forEach((x) => { map[x.name] = x; });
    return map;
  }, [fields]);

  const handleAI = async () => {
    const summary = (f.summary?.data as Record<string, unknown>) || {};
    const groupPerf = (f.group_perf?.rows as Record<string, unknown>[]) || [];
    setAiLoading(true);
    setAiError(null);
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
      setAiText(data.analysis || '');
    } catch (e) {
      setAiError(e instanceof Error ? e.message : String(e));
    } finally {
      setAiLoading(false);
    }
  };

  const grid2: React.CSSProperties = { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 };

  // 节点处于 React Flow 缩放画布内（CSS transform），fixed 定位会失效，portal 到 body
  return createPortal(
    <Dialog
      open={open}
      onClose={onClose}
      title={`因子分析报告${nodeLabel ? ` — ${nodeLabel}` : ''}`}
      className="w-[94vw] max-w-[1180px]"
    >
      <div style={{ maxHeight: '78vh', overflow: 'auto', paddingRight: 4 }}>
        {loading && <div style={{ color: '#646262', fontSize: 12, padding: 24, textAlign: 'center' }}>加载分析报告中...</div>}
        {error && <div style={{ color: '#ff3b30', fontSize: 12, padding: 24, textAlign: 'center' }}>报告加载失败: {error}</div>}

        {!loading && !error && fields && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {/* 数据卡 */}
            {f.summary?.kind === 'metrics' && (
              <div>
                <SectionTitle>关键指标</SectionTitle>
                <SummaryCards data={(f.summary.data as Record<string, unknown>) || {}} />
              </div>
            )}

            {/* AI 综合分析 */}
            <div>
              <button
                onClick={handleAI}
                disabled={aiLoading}
                style={{
                  display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer',
                  border: '1px solid #007aff', background: 'rgba(0,122,255,0.1)', color: '#007aff',
                  borderRadius: 4, padding: '4px 12px', fontSize: 12, fontWeight: 500,
                  opacity: aiLoading ? 0.5 : 1,
                }}
              >
                <Sparkles size={13} />
                {aiLoading ? 'AI 分析中...' : 'AI 综合分析'}
              </button>
              {aiError && (
                <div style={{ marginTop: 8, border: '1px solid #ff3b30', background: 'rgba(255,59,48,0.1)', color: '#ff3b30', borderRadius: 4, padding: '6px 10px', fontSize: 11 }}>
                  {aiError}
                </div>
              )}
              {aiText && (
                <div style={{ marginTop: 8, whiteSpace: 'pre-wrap', border: '1px solid rgba(0,122,255,0.3)', background: 'rgba(0,122,255,0.05)', borderRadius: 4, padding: '10px 12px', fontSize: 11, lineHeight: 1.6, color: '#424245' }}>
                  {aiText}
                </div>
              )}
            </div>

            {/* 分组绩效表 */}
            {f.group_perf?.kind === 'table' && (
              <div>
                <SectionTitle>分组绩效（含多空组合）</SectionTitle>
                <DataTable field={f.group_perf} labels={PERF_LABELS} pctKeys={PERF_PCT} />
              </div>
            )}

            {/* 分组累计 / 超额累计 */}
            <div style={grid2}>
              {f.group_cumulative?.kind === 'multiseries' && (
                <div style={CARD_STYLE}>
                  <SectionTitle>分组累计收益</SectionTitle>
                  <MultiLine field={f.group_cumulative} />
                </div>
              )}
              {f.group_excess_cumulative?.kind === 'multiseries' && (
                <div style={CARD_STYLE}>
                  <SectionTitle>分组超额累计收益</SectionTitle>
                  <MultiLine field={f.group_excess_cumulative} />
                </div>
              )}
            </div>

            {/* IC 时序 / 累计 */}
            <div style={grid2}>
              {f.ic_series?.kind === 'multiseries' && (
                <div style={CARD_STYLE}>
                  <SectionTitle>IC / Rank_IC 时序</SectionTitle>
                  <MultiLine field={f.ic_series} />
                </div>
              )}
              {f.ic_cumulative?.kind === 'multiseries' && (
                <div style={CARD_STYLE}>
                  <SectionTitle>IC / Rank_IC 累计</SectionTitle>
                  <MultiLine field={f.ic_cumulative} />
                </div>
              )}
            </div>

            {/* 衰减 / 自相关 */}
            <div style={grid2}>
              {f.ic_decay?.kind === 'table' && (f.ic_decay.rows?.length || 0) > 0 && (
                <div style={CARD_STYLE}>
                  <SectionTitle>IC / Rank_IC 衰减</SectionTitle>
                  <BarsFromRows rows={f.ic_decay.rows!} xKey="period" valueKeys={['IC', 'Rank_IC']} />
                </div>
              )}
              {f.ic_autocorr?.kind === 'table' && (f.ic_autocorr.rows?.length || 0) > 0 && (
                <div style={CARD_STYLE}>
                  <SectionTitle>IC / Rank_IC 自相关</SectionTitle>
                  <BarsFromRows rows={f.ic_autocorr.rows!} xKey="lag" valueKeys={['IC', 'Rank_IC']} />
                </div>
              )}
            </div>

            {/* IC 分布 / 各周期 IC 汇总 */}
            <div style={grid2}>
              {f.ic_distribution?.kind === 'table' && (f.ic_distribution.rows?.length || 0) > 0 && (
                <div style={CARD_STYLE}>
                  <SectionTitle>IC 分布</SectionTitle>
                  <BarsFromRows rows={f.ic_distribution.rows!} xKey="ic_bin" valueKeys={['ic_count']} />
                </div>
              )}
              {f.ic_summary?.kind === 'table' && (
                <div style={CARD_STYLE}>
                  <SectionTitle>各周期 IC 汇总</SectionTitle>
                  <DataTable field={f.ic_summary} maxHeight={220} />
                </div>
              )}
            </div>

            {/* 最新一期因子值排名 */}
            {f.latest_ranking?.kind === 'table' && (
              <div>
                <SectionTitle>最新一期因子值排名</SectionTitle>
                <DataTable field={f.latest_ranking} maxHeight={300} />
              </div>
            )}
          </div>
        )}
      </div>
    </Dialog>,
    document.body
  );
}
