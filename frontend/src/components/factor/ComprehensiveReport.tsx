import { useMemo, useState } from 'react';
import {
  LineChart, Line, BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid,
  Tooltip as RTooltip, ResponsiveContainer, ReferenceLine, Legend,
} from 'recharts';
import { Sparkles } from 'lucide-react';

/** /api/factor/analysis 返回结构 */
export interface FactorReport {
  summary: Record<string, number>;
  ic_summary: { period: number; ic_mean: number; ic_std: number; ic_ir: number; ic_tstat: number; positive_ratio: number }[];
  group_perf: Record<string, number | string>[];
  group_cumulative: Record<string, Record<string, number>>;
  group_excess_cumulative: Record<string, Record<string, number>>;
  long_short_cumulative: Record<string, number>;
  ic: ICBlock;
  rank_ic: ICBlock;
  latest: { date: string; symbol: string; factor_value: number }[];
}
interface ICBlock {
  series: Record<string, number>;
  cumulative: Record<string, number>;
  distribution: { centers: number[]; counts: number[]; skew: number; kurt: number };
  autocorr: { lag: number; acf: number }[];
  decay: { period: number; ic: number }[];
  mean: number;
  ir: number;
}

const LINE_COLORS = ['#ff3b30', '#ff9f0a', '#ffd60a', '#30d158', '#007aff', '#64d2ff', '#bf5af2', '#a2845e'];
const AXIS = { fontSize: 10, fill: '#646262' };
const TOOLTIP_STYLE = { backgroundColor: '#fdfcfc', border: '1px solid rgba(15,0,0,0.12)', borderRadius: 4, fontSize: 11 };

// —— 数据卡：指标标签、顺序、格式 ——————————————————————————
const PCT_KEYS = new Set(['factor_return', 'annual_return', 'max_drawdown', 'p_ic_lt_neg', 'p_ic_gt_pos']);
const METRIC_META: [string, string][] = [
  ['factor_return', '因子收益'], ['annual_return', '年化收益'], ['sharpe_ratio', '夏普比率'], ['max_drawdown', '最大回撤'],
  ['ic_mean', 'IC 均值'], ['rank_ic', 'Rank_IC'], ['ic_std', 'IC 标准差'], ['ic_ir', 'IC_IR'], ['ir', 'IR'],
  ['p_ic_lt_neg', 'P(IC<-0.02)'], ['p_ic_gt_pos', 'P(IC>0.02)'], ['t_stat', 't 统计量'], ['p_value', 'p-value'], ['monotonicity', '单调性'],
];
function fmtVal(key: string, v: number): string {
  if (typeof v !== 'number' || Number.isNaN(v)) return '-';
  if (PCT_KEYS.has(key)) return `${(v * 100).toFixed(2)}%`;
  return v.toFixed(4);
}
function metricColor(key: string, v: number): string {
  if (key === 'max_drawdown') return '#ff3b30';
  if (['factor_return', 'annual_return', 'sharpe_ratio', 'ic_mean', 'rank_ic', 'ic_ir', 'ir'].includes(key)) {
    return v > 0 ? '#ff453a' : v < 0 ? '#30d158' : '#201d1d'; // 红涨绿跌
  }
  return '#201d1d';
}

// —— 分组绩效表列 ————————————————————————————————
const PERF_COLS: [string, string, boolean][] = [
  ['group', '分组', false], ['annualizedReturn', '年化收益率', true], ['excessAnnualized', '超额年化', true],
  ['maxDrawdown', '最大回撤', true], ['excessMaxDrawdown', '超额最大回撤', true], ['annualizedVolatility', '年化波动', true],
  ['excessAnnualizedVolatility', '超额年化波动', true], ['turnoverRate', '换手率', true], ['monthlyWinRate', '月度胜率', true],
  ['excessMonthlyWinRate', '超额月度胜率', true], ['trackingError', '跟踪误差', false], ['sharpeRatio', '夏普比率', false],
  ['informationRatio', '信息比率', false],
];

/** {列: {date: v}} → [{date, 列1, 列2...}] 合并 */
function mergeByDate(maps: Record<string, Record<string, number>>): Record<string, number | string>[] {
  const dates = new Set<string>();
  Object.values(maps).forEach((m) => Object.keys(m).forEach((d) => dates.add(d)));
  return [...dates].sort().map((date) => {
    const row: Record<string, number | string> = { date };
    for (const [k, m] of Object.entries(maps)) row[k] = m[date];
    return row;
  });
}
function SectionTitle({ children }: { children: React.ReactNode }) {
  return <div className="mb-2 text-xs font-semibold text-[#201d1d]">{children}</div>;
}
const CARD = 'rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] p-3';

/** 多线时间序列图 */
function MultiLine({ data, keys }: { data: Record<string, number | string>[]; keys: string[] }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(15,0,0,0.06)" />
        <XAxis dataKey="date" tick={AXIS} tickLine={{ stroke: '#d8d4d4' }} axisLine={{ stroke: '#d8d4d4' }} minTickGap={40} />
        <YAxis tick={AXIS} tickLine={{ stroke: '#d8d4d4' }} axisLine={{ stroke: '#d8d4d4' }} tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`} />
        <RTooltip contentStyle={TOOLTIP_STYLE} labelStyle={{ color: '#646262' }} formatter={(v: unknown) => `${(Number(v) * 100).toFixed(2)}%`} />
        <Legend wrapperStyle={{ fontSize: 10 }} />
        {keys.map((k, i) => (
          <Line key={k} type="monotone" dataKey={k} stroke={LINE_COLORS[i % LINE_COLORS.length]} dot={false} strokeWidth={1.4} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

interface Props {
  report: FactorReport | null;
  factorName: string | null;
  loading?: boolean;
}

/**
 * 因子综合分析报告 —— 与工作流「因子分析」节点同源（/api/factor/analysis）。
 * 数据卡 + 分组绩效表 + 分组/超额累计 + IC/Rank_IC 时序/累计/衰减/分布/自相关 + 最新排名 + AI 分析。
 */
export default function ComprehensiveReport({ report, factorName, loading }: Props) {
  const [aiText, setAiText] = useState<string | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);

  const groupCum = useMemo(() => (report ? mergeByDate(report.group_cumulative) : []), [report]);
  const groupExcess = useMemo(() => (report ? mergeByDate(report.group_excess_cumulative) : []), [report]);
  const groupKeys = useMemo(() => (report ? Object.keys(report.group_cumulative) : []), [report]);
  const icTs = useMemo(() => (report ? mergeByDate({ IC: report.ic.series, Rank_IC: report.rank_ic.series }) : []), [report]);
  const icCum = useMemo(() => (report ? mergeByDate({ IC: report.ic.cumulative, Rank_IC: report.rank_ic.cumulative }) : []), [report]);

  const decayData = useMemo(() => {
    if (!report) return [];
    const m: Record<number, { period: number; IC?: number; Rank_IC?: number }> = {};
    report.ic.decay.forEach((d) => { m[d.period] = { ...(m[d.period] || { period: d.period }), IC: d.ic }; });
    report.rank_ic.decay.forEach((d) => { m[d.period] = { ...(m[d.period] || { period: d.period }), Rank_IC: d.ic }; });
    return Object.values(m).sort((a, b) => a.period - b.period);
  }, [report]);

  const acData = useMemo(() => {
    if (!report) return [];
    const m: Record<number, { lag: number; IC?: number; Rank_IC?: number }> = {};
    report.ic.autocorr.forEach((d) => { m[d.lag] = { ...(m[d.lag] || { lag: d.lag }), IC: d.acf }; });
    report.rank_ic.autocorr.forEach((d) => { m[d.lag] = { ...(m[d.lag] || { lag: d.lag }), Rank_IC: d.acf }; });
    return Object.values(m).sort((a, b) => a.lag - b.lag);
  }, [report]);

  const handleAI = async () => {
    if (!report) return;
    setAiLoading(true); setAiError(null);
    try {
      const labeled: Record<string, string> = {};
      for (const [k, label] of METRIC_META) labeled[label] = fmtVal(k, report.summary[k]);
      const res = await fetch('/api/ai/factor-report', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ factor_name: factorName, summary: labeled, group_perf: report.group_perf }),
      });
      if (!res.ok) { const e = await res.json().catch(() => null); throw new Error(e?.detail || `HTTP ${res.status}`); }
      const data = await res.json();
      setAiText(data.analysis || '');
    } catch (e) {
      setAiError(e instanceof Error ? e.message : String(e));
    } finally {
      setAiLoading(false);
    }
  };

  if (loading) return <div className="flex h-40 items-center justify-center text-xs text-[#646262]">综合报告计算中...</div>;
  if (!report) {
    return <div className="flex h-40 items-center justify-center text-xs text-[#646262]">暂无综合报告 — 请先在左上构建并计算因子</div>;
  }

  const dd = report.ic.distribution;
  const rdd = report.rank_ic.distribution;

  return (
    <div className="space-y-4">
      {/* 顶部：标题 + AI 分析按钮 */}
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-[#201d1d]">综合报告{factorName ? ` — ${factorName}` : ''}</span>
        <button
          onClick={handleAI}
          disabled={aiLoading}
          className="flex items-center gap-1.5 rounded-[4px] border border-[#007aff] bg-[#007aff]/10 px-3 py-1 text-xs font-medium text-[#007aff] transition-colors hover:bg-[#007aff]/20 disabled:opacity-50"
        >
          <Sparkles size={13} />
          {aiLoading ? 'AI 分析中...' : 'AI 综合分析'}
        </button>
      </div>

      {/* AI 分析结果 */}
      {aiError && <div className="rounded-[4px] border border-[#ff3b30] bg-[#ff3b30]/10 px-3 py-2 text-xs text-[#ff3b30]">{aiError}</div>}
      {aiText && (
        <div className="max-h-[360px] overflow-auto whitespace-pre-wrap rounded-[4px] border border-[#007aff]/30 bg-[#007aff]/5 px-3 py-2.5 text-xs leading-relaxed text-[#424245]">
          {aiText}
        </div>
      )}

      {/* 数据卡 */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
        {METRIC_META.map(([key, label]) => (
          <div key={key} className="rounded-[4px] border border-[rgba(15,0,0,0.1)] bg-[#fdfcfc] px-2.5 py-2">
            <div className="text-[10px] text-[#9a9898]">{label}</div>
            <div className="mt-0.5 font-mono text-sm font-semibold" style={{ color: metricColor(key, report.summary[key]) }}>
              {fmtVal(key, report.summary[key])}
            </div>
          </div>
        ))}
      </div>

      {/* 分组绩效表 */}
      <div className={CARD}>
        <SectionTitle>分组收益</SectionTitle>
        <div className="overflow-auto">
          <table className="w-full border-collapse font-mono text-[11px]">
            <thead>
              <tr>
                {PERF_COLS.map(([, label]) => (
                  <th key={label} className="whitespace-nowrap border-b border-[rgba(15,0,0,0.12)] bg-[#f1eeee] px-2 py-1 text-left font-medium text-[#646262]">{label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {report.group_perf.map((row, ri) => (
                <tr key={ri}>
                  {PERF_COLS.map(([key, , pct]) => {
                    const v = row[key];
                    const isNum = typeof v === 'number';
                    return (
                      <td key={key} className="whitespace-nowrap border-b border-[rgba(15,0,0,0.06)] px-2 py-1 text-[#201d1d]">
                        {v == null ? '-' : isNum ? (pct ? `${((v as number) * 100).toFixed(2)}%` : (v as number).toFixed(4)) : String(v)}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* 分组累计 + 超额累计 */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div className={CARD}><SectionTitle>各分组累计收益</SectionTitle><MultiLine data={groupCum} keys={groupKeys} /></div>
        <div className={CARD}><SectionTitle>各分组超额累计收益</SectionTitle><MultiLine data={groupExcess} keys={groupKeys} /></div>
      </div>

      {/* IC / Rank_IC 时序 + 累计 */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div className={CARD}>
          <SectionTitle>IC / Rank_IC 时序</SectionTitle>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={icTs} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(15,0,0,0.06)" />
              <XAxis dataKey="date" tick={AXIS} tickLine={{ stroke: '#d8d4d4' }} axisLine={{ stroke: '#d8d4d4' }} minTickGap={40} />
              <YAxis tick={AXIS} tickLine={{ stroke: '#d8d4d4' }} axisLine={{ stroke: '#d8d4d4' }} tickFormatter={(v: number) => v.toFixed(2)} />
              <RTooltip contentStyle={TOOLTIP_STYLE} labelStyle={{ color: '#646262' }} formatter={(v: unknown) => Number(v).toFixed(4)} />
              <Legend wrapperStyle={{ fontSize: 10 }} />
              <ReferenceLine y={0} stroke="#c8c4c4" />
              <Line type="monotone" dataKey="IC" stroke="#007aff" dot={false} strokeWidth={1.2} />
              <Line type="monotone" dataKey="Rank_IC" stroke="#ff9f0a" dot={false} strokeWidth={1.2} />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div className={CARD}>
          <SectionTitle>IC / Rank_IC 累计</SectionTitle>
          <MultiLineRaw data={icCum} />
        </div>
      </div>

      {/* 衰减 + 自相关 */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div className={CARD}>
          <SectionTitle>IC / Rank_IC 衰减</SectionTitle>
          <GroupedBar data={decayData} xKey="period" xLabel="持有期" />
        </div>
        <div className={CARD}>
          <SectionTitle>IC / Rank_IC 自相关</SectionTitle>
          <GroupedBar data={acData} xKey="lag" xLabel="滞后阶数" />
        </div>
      </div>

      {/* 分布 */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div className={CARD}>
          <SectionTitle>IC 分布 (skew={dd.skew.toFixed(3)} kurt={dd.kurt.toFixed(3)})</SectionTitle>
          <DistChart centers={dd.centers} counts={dd.counts} color="#007aff" />
        </div>
        <div className={CARD}>
          <SectionTitle>Rank_IC 分布 (skew={rdd.skew.toFixed(3)} kurt={rdd.kurt.toFixed(3)})</SectionTitle>
          <DistChart centers={rdd.centers} counts={rdd.counts} color="#ff9f0a" />
        </div>
      </div>

      {/* 最新一期因子值排名 */}
      <div className={CARD}>
        <SectionTitle>最新数据 — 因子值排名{report.latest[0] ? `（${report.latest[0].date}）` : ''}</SectionTitle>
        <div className="max-h-[280px] overflow-auto">
          <table className="w-full border-collapse font-mono text-[11px]">
            <thead>
              <tr>
                {['#', '股票代码', '因子值'].map((h) => (
                  <th key={h} className="sticky top-0 border-b border-[rgba(15,0,0,0.12)] bg-[#f1eeee] px-2 py-1 text-left font-medium text-[#646262]">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {report.latest.slice(0, 30).map((r, i) => (
                <tr key={r.symbol}>
                  <td className="border-b border-[rgba(15,0,0,0.06)] px-2 py-1 text-[#9a9898]">{i + 1}</td>
                  <td className="border-b border-[rgba(15,0,0,0.06)] px-2 py-1 text-[#201d1d]">{r.symbol}</td>
                  <td className="border-b border-[rgba(15,0,0,0.06)] px-2 py-1 text-[#201d1d]">{r.factor_value.toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

/** IC 累计多线（数值格式，非百分比） */
function MultiLineRaw({ data }: { data: Record<string, number | string>[] }) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(15,0,0,0.06)" />
        <XAxis dataKey="date" tick={AXIS} tickLine={{ stroke: '#d8d4d4' }} axisLine={{ stroke: '#d8d4d4' }} minTickGap={40} />
        <YAxis tick={AXIS} tickLine={{ stroke: '#d8d4d4' }} axisLine={{ stroke: '#d8d4d4' }} tickFormatter={(v: number) => v.toFixed(1)} />
        <RTooltip contentStyle={TOOLTIP_STYLE} labelStyle={{ color: '#646262' }} formatter={(v: unknown) => Number(v).toFixed(4)} />
        <Legend wrapperStyle={{ fontSize: 10 }} />
        <ReferenceLine y={0} stroke="#c8c4c4" />
        <Line type="monotone" dataKey="IC" stroke="#007aff" dot={false} strokeWidth={1.4} />
        <Line type="monotone" dataKey="Rank_IC" stroke="#ff9f0a" dot={false} strokeWidth={1.4} />
      </LineChart>
    </ResponsiveContainer>
  );
}

/** IC/Rank_IC 分组柱（衰减/自相关） */
function GroupedBar({ data, xKey, xLabel }: { data: Record<string, number>[]; xKey: string; xLabel: string }) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(15,0,0,0.06)" />
        <XAxis dataKey={xKey} tick={AXIS} tickLine={{ stroke: '#d8d4d4' }} axisLine={{ stroke: '#d8d4d4' }} />
        <YAxis tick={AXIS} tickLine={{ stroke: '#d8d4d4' }} axisLine={{ stroke: '#d8d4d4' }} tickFormatter={(v: number) => v.toFixed(2)} />
        <RTooltip contentStyle={TOOLTIP_STYLE} labelStyle={{ color: '#646262' }} formatter={(v: unknown) => Number(v).toFixed(4)} labelFormatter={(l) => `${xLabel} ${l}`} />
        <Legend wrapperStyle={{ fontSize: 10 }} />
        <ReferenceLine y={0} stroke="#c8c4c4" />
        <Bar dataKey="IC" fill="#007aff" radius={[2, 2, 0, 0]} />
        <Bar dataKey="Rank_IC" fill="#ff9f0a" radius={[2, 2, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** 分布直方图 */
function DistChart({ centers, counts, color }: { centers: number[]; counts: number[]; color: string }) {
  const data = centers.map((c, i) => ({ bin: c.toFixed(3), count: counts[i] }));
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(15,0,0,0.06)" />
        <XAxis dataKey="bin" tick={AXIS} tickLine={{ stroke: '#d8d4d4' }} axisLine={{ stroke: '#d8d4d4' }} minTickGap={20} />
        <YAxis tick={AXIS} tickLine={{ stroke: '#d8d4d4' }} axisLine={{ stroke: '#d8d4d4' }} allowDecimals={false} />
        <RTooltip contentStyle={TOOLTIP_STYLE} labelStyle={{ color: '#646262' }} formatter={(v: unknown) => [String(v), '频数']} labelFormatter={(l) => `IC≈${l}`} />
        <Bar dataKey="count" radius={[2, 2, 0, 0]}>
          {data.map((d, i) => (<Cell key={i} fill={Number(d.bin) >= 0 ? color : '#c8c4c4'} />))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
