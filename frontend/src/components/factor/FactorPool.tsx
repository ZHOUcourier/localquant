import { useState, useCallback } from 'react';
import {
  useFactorPool,
  useRemoveFromPool,
  useRecalculateFactor,
} from '@/hooks/usePresetFactors';
import type { PresetFactor } from '@/hooks/usePresetFactors';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';

/* ── 工具函数 ── */
function fmt(v: number | null, digits = 4): string {
  if (v == null) return '—';
  return v.toFixed(digits);
}

function fmtPct(v: number | null, digits = 2): string {
  if (v == null) return '—';
  return `${(v * 100).toFixed(digits)}%`;
}

/* ── 对比分析表格 ── */
function ComparisonTable({ factors }: { factors: PresetFactor[] }) {
  const metrics = [
    { label: 'IC_MEAN', key: 'ic_mean', format: fmt },
    { label: 'RANK_IC', key: 'rank_ic', format: fmt },
    { label: 'IC_IR', key: 'ic_ir', format: fmt },
    { label: '年化收益', key: 'annualized_return', format: fmtPct },
    { label: '最大回撤', key: 'maximum_drawdown', format: fmtPct },
    { label: '夏普比率', key: 'sharpe_ratio', format: (v: number | null) => fmt(v, 2) },
  ] as const;

  return (
    <div className="mt-3 rounded-[4px] border border-[rgba(15,0,0,0.12)]">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="bg-[#f8f7f7]">
            <th className="border-b border-[rgba(15,0,0,0.12)] px-3 py-2 text-left text-xs font-medium text-[#646262]">
              指标
            </th>
            {factors.map((f) => (
              <th
                key={f.id}
                className="border-b border-[rgba(15,0,0,0.12)] px-3 py-2 text-left text-xs font-medium text-[#201d1d]"
              >
                {f.factor_name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {metrics.map((m) => (
            <tr key={m.key} className="border-b border-[rgba(15,0,0,0.12)]">
              <td className="px-3 py-2 text-xs text-[#646262]">{m.label}</td>
              {factors.map((f) => (
                <td key={f.id} className="px-3 py-2 text-xs text-[#201d1d]">
                  {m.format(f[m.key as keyof PresetFactor] as number | null)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ── 因子池项 ── */
function PoolItem({
  factor,
  onRequestRemove,
  onRecalculate,
  removing,
  recalculating,
}: {
  factor: PresetFactor;
  onRequestRemove: (id: number) => void;
  onRecalculate: (id: number) => void;
  removing: boolean;
  recalculating: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-[rgba(15,0,0,0.12)] py-3 last:border-b-0">
      {/* 左侧：名称 + 分类 + IC 指标 */}
      <div className="flex min-w-0 flex-1 items-center gap-4">
        <span className="shrink-0 text-sm font-medium text-[#201d1d]">
          {factor.factor_name}
        </span>
        <span className="flex shrink-0 items-center gap-1 text-xs text-[#646262]">
          <span
            className="inline-block h-[6px] w-[6px] rounded-full"
            style={{ backgroundColor: factor.category_color_hex || '#646262' }}
          />
          {factor.category_name || '未分类'}
        </span>
        <div className="hidden items-center gap-3 sm:flex">
          {[
            { label: 'IC_MEAN', value: fmt(factor.ic_mean) },
            { label: 'RANK_IC', value: fmt(factor.rank_ic) },
            { label: 'IC_IR', value: fmt(factor.ic_ir) },
            { label: 'IC_STD', value: fmt(factor.ic_std) },
          ].map((m) => (
            <span key={m.label} className="flex items-center gap-1 text-xs">
              <span className="text-[#9a9898]">{m.label}</span>
              <span className="text-[#201d1d]">{m.value}</span>
            </span>
          ))}
        </div>
      </div>

      {/* 右侧：操作按钮 */}
      <div className="flex shrink-0 items-center gap-2">
        <button
          type="button"
          disabled={recalculating}
          className="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2 py-1 text-xs text-[#646262] transition-colors hover:text-[#201d1d] disabled:text-[#9a9898] cursor-pointer"
          title="重算为覆盖更新：新指标直接写回当前因子记录（不另存新因子），旧值自动存入历史快照，可在因子详情中查看"
          onClick={() => onRecalculate(factor.id)}
        >
          {recalculating ? '计算中...' : '↻ 重算 IC（覆盖）'}
        </button>
        <button
          type="button"
          disabled={removing}
          className="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2 py-1 text-xs text-[#646262] transition-colors hover:text-[#ff3b30] disabled:text-[#9a9898] cursor-pointer"
          onClick={() => onRequestRemove(factor.id)}
        >
          {removing ? '移除中...' : '[−] 移除'}
        </button>
      </div>
    </div>
  );
}

/* ── 主组件 ── */
export default function FactorPool() {
  const { data, isLoading } = useFactorPool();
  const removeMutation = useRemoveFromPool();
  const recalcMutation = useRecalculateFactor();

  const [removingId, setRemovingId] = useState<number | null>(null);
  const [recalculatingId, setRecalculatingId] = useState<number | null>(null);
  const [showComparison, setShowComparison] = useState(false);
  const [removeConfirmId, setRemoveConfirmId] = useState<number | null>(null);

  const factors = data ?? [];

  const handleRemove = useCallback(
    async (id: number) => {
      setRemovingId(id);
      try {
        await removeMutation.mutateAsync(id);
      } catch {
        // 静默处理
      } finally {
        setRemovingId(null);
        setRemoveConfirmId(null);
      }
    },
    [removeMutation]
  );

  const handleRecalculate = useCallback(
    async (id: number) => {
      setRecalculatingId(id);
      try {
        await recalcMutation.mutateAsync(id);
      } catch {
        // 静默处理
      } finally {
        setRecalculatingId(null);
      }
    },
    [recalcMutation]
  );

  /* ── 空状态 ── */
  if (!isLoading && factors.length === 0) {
    return (
      <div className="flex h-[200px] items-center justify-center rounded-[4px] border border-[rgba(15,0,0,0.12)]">
        <span className="font-mono text-xs text-[#646262]">
          因子池为空，请从因子库中添加因子
        </span>
      </div>
    );
  }

  /* ── 加载中 ── */
  if (isLoading) {
    return (
      <div className="flex h-[200px] items-center justify-center">
        <span className="text-xs text-[#646262]">加载中...</span>
      </div>
    );
  }

  return (
    <div className="flex flex-col">
      {/* 顶部栏：计数 + 对比按钮 */}
      <div className="mb-3 flex items-center justify-between">
        <span className="text-xs text-[#646262]">
          共 {factors.length} 个因子
        </span>
        {factors.length >= 2 && (
          <button
            type="button"
            className="rounded-[4px] bg-[#201d1d] px-3 py-1 text-xs font-medium text-[#fdfcfc] transition-colors hover:bg-[#0f0000] cursor-pointer"
            onClick={() => setShowComparison((v) => !v)}
          >
            {showComparison ? '[−] 收起对比' : '[+] 对比分析'}
          </button>
        )}
      </div>

      {/* 因子列表 */}
      <div className="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-3">
        {factors.map((f) => (
          <PoolItem
            key={f.id}
            factor={f}
            onRequestRemove={(id) => setRemoveConfirmId(id)}
            onRecalculate={handleRecalculate}
            removing={removingId === f.id}
            recalculating={recalculatingId === f.id}
          />
        ))}
      </div>

      {/* 对比分析表格 */}
      {showComparison && factors.length >= 2 && (
        <ComparisonTable factors={factors} />
      )}

      {/* 移除确认对话框 */}
      <ConfirmDialog
        open={removeConfirmId !== null}
        title="[−] 移除因子"
        message="确定要从因子池中移除该因子吗？"
        confirmText="移除"
        cancelText="取消"
        variant="danger"
        onConfirm={() => removeConfirmId !== null && handleRemove(removeConfirmId)}
        onCancel={() => setRemoveConfirmId(null)}
      />
    </div>
  );
}
