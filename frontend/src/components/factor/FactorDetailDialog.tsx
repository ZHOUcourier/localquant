/**
 * FactorDetailDialog — 因子详情弹窗
 *
 * 点击因子后展示：
 * - 公式：代码形式（Python 片段） + LaTeX 数学渲染（KaTeX）两种呈现
 * - 具体数据：全部 IC/绩效指标、股票池、数据区间
 * - 重算：明确标注「覆盖更新」语义 + 历史快照列表
 * - AI 分析：调用 /api/ai/factor-advice 给出因子解读与使用建议
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import katex from 'katex';
import 'katex/dist/katex.min.css';
import { Sparkles, RefreshCw } from 'lucide-react';
import { Dialog } from '@/components/ui/Dialog';
import { Button } from '@/components/ui/Button';
import {
  usePresetFactorDetail,
  useFactorHistory,
  useRecalculateFactor,
} from '@/hooks/usePresetFactors';

function fmt(v: number | null | undefined, digits = 4): string {
  if (v == null) return '—';
  return v.toFixed(digits);
}

function fmtPct(v: number | null | undefined, digits = 2): string {
  if (v == null) return '—';
  return `${(v * 100).toFixed(digits)}%`;
}

/** KaTeX 渲染块（渲染失败时回退为原始公式文本） */
function LatexBlock({ latex, fallback }: { latex: string; fallback: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!ref.current || !latex) return;
    try {
      katex.render(latex, ref.current, {
        throwOnError: true,
        displayMode: true,
      });
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, [latex]);

  if (!latex || failed) {
    return (
      <div className="rounded-[4px] bg-[#f8f7f7] px-3 py-3 text-center text-sm text-[#201d1d] font-mono">
        {fallback || '暂无公式'}
      </div>
    );
  }
  return (
    <div
      ref={ref}
      className="overflow-x-auto rounded-[4px] bg-[#f8f7f7] px-3 py-2 text-[#201d1d]"
      style={{ fontSize: 14 }}
    />
  );
}

type TabKey = 'formula' | 'data' | 'history' | 'ai';
export type FactorDetailTab = TabKey;

export function FactorDetailDialog({
  factorId,
  initialTab = 'formula',
  onClose,
}: {
  factorId: number | null;
  initialTab?: TabKey;
  onClose: () => void;
}) {
  const { data: factor, isLoading } = usePresetFactorDetail(factorId);
  const { data: history } = useFactorHistory(factorId);
  const recalcMutation = useRecalculateFactor();
  const [tab, setTab] = useState<TabKey>('formula');
  const [recalcMsg, setRecalcMsg] = useState<string | null>(null);
  // AI 分析
  const [aiLoading, setAiLoading] = useState(false);
  const [aiAdvice, setAiAdvice] = useState<string | null>(null);
  const [aiError, setAiError] = useState<string | null>(null);

  useEffect(() => {
    // 切换因子时重置状态
    setTab(initialTab);
    setRecalcMsg(null);
    setAiAdvice(null);
    setAiError(null);
  }, [factorId, initialTab]);

  const metrics = useMemo(
    () =>
      factor
        ? [
            { label: 'IC_MEAN', value: fmt(factor.ic_mean) },
            { label: 'RANK_IC', value: fmt(factor.rank_ic) },
            { label: 'IC_IR', value: fmt(factor.ic_ir) },
            { label: 'IC_STD', value: fmt(factor.ic_std) },
            { label: '年化收益', value: fmtPct(factor.annualized_return) },
            { label: '最大回撤', value: fmtPct(factor.maximum_drawdown) },
            { label: '夏普比率', value: fmt(factor.sharpe_ratio, 2) },
            { label: '换手率', value: fmtPct(factor.turnover_rate) },
          ]
        : [],
    [factor]
  );

  const handleRecalc = useCallback(async () => {
    if (!factorId) return;
    setRecalcMsg(null);
    try {
      const result = await recalcMutation.mutateAsync(factorId);
      setRecalcMsg(result.recalc_message || '重算完成（覆盖更新）');
    } catch (e) {
      setRecalcMsg(`重算失败: ${e instanceof Error ? e.message : String(e)}`);
    }
  }, [factorId, recalcMutation]);

  const handleAI = useCallback(async () => {
    if (!factor) return;
    setAiLoading(true);
    setAiError(null);
    try {
      const res = await fetch('/api/ai/factor-advice', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          factor_name: factor.factor_name,
          factor_code: factor.factor_code,
          formula: factor.formula,
          description: factor.description,
          metrics: {
            IC_MEAN: factor.ic_mean,
            RANK_IC: factor.rank_ic,
            IC_IR: factor.ic_ir,
            IC_STD: factor.ic_std,
            年化收益: factor.annualized_return,
            最大回撤: factor.maximum_drawdown,
            夏普比率: factor.sharpe_ratio,
            换手率: factor.turnover_rate,
          },
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(err?.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      setAiAdvice(data.advice || '');
    } catch (e) {
      setAiError(e instanceof Error ? e.message : String(e));
    } finally {
      setAiLoading(false);
    }
  }, [factor]);

  const tabs: { key: TabKey; label: string }[] = [
    { key: 'formula', label: '公式' },
    { key: 'data', label: '具体数据' },
    { key: 'history', label: `重算历史${history?.length ? `(${history.length})` : ''}` },
    { key: 'ai', label: '✦ AI 分析' },
  ];

  return (
    <Dialog
      open={factorId != null}
      onClose={onClose}
      title={factor ? `${factor.factor_name} · ${factor.factor_code}` : '因子详情'}
      className="!max-w-[680px] w-[680px]"
      footer={
        <Button variant="secondary" onClick={onClose}>
          关闭
        </Button>
      }
    >
      {isLoading || !factor ? (
        <div className="py-10 text-center text-xs text-[#646262]">加载中...</div>
      ) : (
        <div>
          {/* 头部：分类 + 描述 */}
          <div className="mb-3 flex items-center gap-2 text-xs text-[#646262]">
            <span
              className="inline-block h-[7px] w-[7px] rounded-full"
              style={{ backgroundColor: factor.category_color_hex || '#646262' }}
            />
            {factor.category_name || '未分类'}
            <span className="text-[#9a9898]">
              {factor.stock_pool ? `· 股票池 ${factor.stock_pool}` : ''}
              {factor.start_date ? ` · ${factor.start_date} 起` : ''}
              {factor.data_date ? ` · 数据截至 ${factor.data_date}` : ''}
            </span>
          </div>

          {/* Tab 切换 */}
          <div className="mb-3 flex border-b border-[rgba(15,0,0,0.12)]">
            {tabs.map((t) => (
              <button
                key={t.key}
                type="button"
                onClick={() => setTab(t.key)}
                className={`px-3 py-1.5 text-xs cursor-pointer transition-colors ${
                  tab === t.key
                    ? 'border-b-2 border-[#201d1d] font-medium text-[#201d1d]'
                    : 'text-[#646262] hover:text-[#201d1d]'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>

          {/* 公式 Tab（按因子类型分别展示） */}
          {tab === 'formula' && (
            <div className="flex flex-col gap-3">
              {/* 类型标识 */}
              <div className="flex items-center gap-2">
                <span
                  className={`rounded-[3px] px-2 py-0.5 text-[11px] font-medium ${
                    factor.factor_type === 'formula'
                      ? 'bg-[#007aff]/10 text-[#007aff]'
                      : factor.factor_type === 'indicator'
                      ? 'bg-[#ff9f0a]/15 text-[#cc7f08]'
                      : 'bg-[#30d158]/15 text-[#248a3d]'
                  }`}
                >
                  {factor.factor_type === 'formula'
                    ? '公式型因子'
                    : factor.factor_type === 'indicator'
                    ? '参数化指标'
                    : '数据字段型因子'}
                </span>
                <span className="text-[11px] text-[#9a9898]">
                  {factor.factor_type === 'formula'
                    ? '可直接在「因子构建（公式）」节点运行'
                    : factor.factor_type === 'indicator'
                    ? '参数化技术指标，可用「技术指标」节点或公式复现'
                    : '直接调用底层数据字段，无需公式'}
                </span>
              </div>

              {factor.factor_type === 'formula' && factor.formula ? (
                <>
                  <div>
                    <div className="mb-1 text-[11px] font-medium text-[#646262]">
                      数学公式（LaTeX 渲染）
                    </div>
                    <LatexBlock latex={factor.formula_latex} fallback={factor.formula} />
                  </div>
                  <div>
                    <div className="mb-1 flex items-center justify-between text-[11px] font-medium text-[#646262]">
                      <span>代码形式（可粘贴到公式/代码节点运行）</span>
                      <button
                        type="button"
                        onClick={() => navigator.clipboard?.writeText(factor.formula)}
                        className="text-[#007aff] cursor-pointer bg-transparent border-none"
                        title="复制公式"
                      >
                        复制公式
                      </button>
                    </div>
                    <pre className="max-h-[220px] overflow-auto rounded-[4px] bg-[#201d1d] px-3 py-2.5 text-xs leading-relaxed text-[#fdfcfc]">
                      {factor.formula_code || factor.formula}
                    </pre>
                  </div>
                </>
              ) : (
                <div className="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-3 py-3 text-xs leading-relaxed text-[#424245]">
                  {factor.factor_type === 'data_field'
                    ? '该因子为底层数据字段（如财务/估值指标），在数据节点中直接选用对应字段即可，无需编写公式。'
                    : '该因子为参数化技术指标，可在「技术指标」节点配置参数使用，或用公式算子复现（参见下方变量参考）。'}
                  <div className="mt-2 font-mono text-[11px] text-[#646262]">
                    字段代码：{factor.factor_code}
                  </div>
                </div>
              )}

              {factor.description && (
                <div>
                  <div className="mb-1 text-[11px] font-medium text-[#646262]">因子简介</div>
                  <div className="text-xs leading-relaxed text-[#424245]">
                    {factor.description}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* 具体数据 Tab */}
          {tab === 'data' && (
            <div>
              <div className="grid grid-cols-4 gap-2">
                {metrics.map((m) => (
                  <div
                    key={m.label}
                    className="flex flex-col items-center rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-2 py-2.5"
                  >
                    <span className="text-[10px] text-[#9a9898]">{m.label}</span>
                    <span className="mt-0.5 text-sm font-medium text-[#201d1d]">{m.value}</span>
                  </div>
                ))}
              </div>

              {/* 重算：明确覆盖语义 */}
              <div className="mt-4 rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] p-3">
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-xs font-medium text-[#201d1d]">重新计算 IC 指标</span>
                  <button
                    type="button"
                    disabled={recalcMutation.isPending}
                    onClick={handleRecalc}
                    className="flex items-center gap-1 rounded-[4px] bg-[#201d1d] px-3 py-1 text-xs text-[#fdfcfc] transition-colors hover:bg-[#0f0000] disabled:opacity-50 cursor-pointer"
                  >
                    <RefreshCw size={11} className={recalcMutation.isPending ? 'animate-spin' : ''} />
                    {recalcMutation.isPending ? '重算中...' : '重算（覆盖更新）'}
                  </button>
                </div>
                <div className="text-[11px] leading-relaxed text-[#646262]">
                  <span className="font-medium text-[#cc7f08]">覆盖，不另存：</span>
                  重算得到的新指标会直接写回当前因子记录（不会生成新因子条目）；
                  覆盖前的旧值会自动存入「重算历史」快照，可随时回溯对比。
                </div>
                {recalcMsg && (
                  <div className="mt-2 rounded-[4px] bg-[#fdfcfc] px-2 py-1.5 text-[11px] text-[#424245]">
                    {recalcMsg}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* 重算历史 Tab */}
          {tab === 'history' && (
            <div className="max-h-[320px] overflow-auto">
              {!history || history.length === 0 ? (
                <div className="py-8 text-center text-xs text-[#9a9898]">
                  暂无历史快照（每次重算覆盖前会自动留存旧值）
                </div>
              ) : (
                <table className="w-full border-collapse text-xs">
                  <thead>
                    <tr className="bg-[#f8f7f7]">
                      {['快照时间', 'IC_MEAN', 'RANK_IC', 'IC_IR', '年化收益', '最大回撤'].map((h) => (
                        <th
                          key={h}
                          className="border-b border-[rgba(15,0,0,0.12)] px-2 py-1.5 text-left font-medium text-[#646262]"
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {history.map((s) => (
                      <tr key={s.id} className="border-b border-[rgba(15,0,0,0.08)]">
                        <td className="px-2 py-1.5 text-[#646262]">
                          {new Date(s.snapshot_at * 1000).toLocaleString('zh-CN', { hour12: false })}
                        </td>
                        <td className="px-2 py-1.5 text-[#201d1d]">{fmt(s.ic_mean)}</td>
                        <td className="px-2 py-1.5 text-[#201d1d]">{fmt(s.rank_ic)}</td>
                        <td className="px-2 py-1.5 text-[#201d1d]">{fmt(s.ic_ir)}</td>
                        <td className="px-2 py-1.5 text-[#201d1d]">{fmtPct(s.annualized_return)}</td>
                        <td className="px-2 py-1.5 text-[#201d1d]">{fmtPct(s.maximum_drawdown)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}

          {/* AI 分析 Tab */}
          {tab === 'ai' && (
            <div>
              {!aiAdvice && !aiLoading && (
                <div className="flex flex-col items-center gap-3 py-6">
                  <div className="text-center text-xs leading-relaxed text-[#646262]">
                    AI 将解读该因子的公式逻辑、点评各项指标强弱，
                    <br />
                    并给出使用场景与调仓周期建议（需先在设置中配置 AI）。
                  </div>
                  <button
                    type="button"
                    onClick={handleAI}
                    className="flex items-center gap-1.5 rounded-[4px] bg-[#7c3aed] px-4 py-1.5 text-xs font-medium text-white transition-opacity hover:opacity-90 cursor-pointer"
                  >
                    <Sparkles size={12} />
                    开始 AI 分析
                  </button>
                  {aiError && (
                    <div className="max-w-full whitespace-pre-wrap text-[11px] text-[#ff3b30]">
                      {aiError}
                    </div>
                  )}
                </div>
              )}
              {aiLoading && (
                <div className="py-10 text-center text-xs text-[#646262]">
                  AI 分析中（可能需要几十秒）...
                </div>
              )}
              {aiAdvice && !aiLoading && (
                <div>
                  <div className="max-h-[320px] overflow-auto whitespace-pre-wrap rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-3 py-2.5 text-xs leading-relaxed text-[#424245]">
                    {aiAdvice}
                  </div>
                  <button
                    type="button"
                    onClick={handleAI}
                    className="mt-2 text-[11px] text-[#7c3aed] cursor-pointer bg-transparent border-none"
                  >
                    ↻ 重新分析
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </Dialog>
  );
}
