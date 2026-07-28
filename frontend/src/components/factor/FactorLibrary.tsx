import { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import { Input } from '@/components/ui';
import {
  usePresetFactors,
  usePresetFactorCategories,
  useAddToFactorPool,
} from '@/hooks/usePresetFactors';
import type { PresetFactor, PresetFactorParams } from '@/hooks/usePresetFactors';

/* ── 工具函数 ── */
function fmt(v: number | null, digits = 4): string {
  if (v == null) return '—';
  return v.toFixed(digits);
}

function fmtPct(v: number | null, digits = 2): string {
  if (v == null) return '—';
  return `${(v * 100).toFixed(digits)}%`;
}

type ViewMode = 'card' | 'list';
type SortField = 'rank_ic' | 'ic_mean' | 'ic_ir' | 'annualized_return';

/* ── 排序字段配置 ── */
const SORT_OPTIONS: { field: SortField; label: string }[] = [
  { field: 'rank_ic', label: 'RANK_IC' },
  { field: 'ic_mean', label: 'IC_MEAN' },
  { field: 'ic_ir', label: 'IC_IR' },
  { field: 'annualized_return', label: '年化收益' },
];

/* ── 卡片视图 ── */
function FactorCard({
  factor,
  onAddToPool,
  adding,
}: {
  factor: PresetFactor;
  onAddToPool: (id: number) => void;
  adding: boolean;
}) {
  return (
    <div
      className="flex flex-col rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f1eeee] p-3"
    >
      {/* 头部：名称 + 分类 */}
      <div className="mb-2 flex items-start justify-between gap-2">
        <span className="text-sm font-medium leading-tight text-[#201d1d]">
          {factor.factor_name}
        </span>
        <span className="flex shrink-0 items-center gap-1 text-[11px] text-[#646262]">
          <span
            className="inline-block h-[6px] w-[6px] rounded-full"
            style={{ backgroundColor: factor.category_color_hex || '#646262' }}
          />
          {factor.category_name || '未分类'}
        </span>
      </div>

      {/* 描述 */}
      <p className="mb-3 line-clamp-2 text-xs leading-relaxed text-[#646262]">
        {factor.description || '暂无描述'}
      </p>

      {/* IC 指标 */}
      <div className="mb-2 grid grid-cols-4 gap-1">
        {[
          { label: 'IC_MEAN', value: fmt(factor.ic_mean) },
          { label: 'RANK_IC', value: fmt(factor.rank_ic) },
          { label: 'IC_IR', value: fmt(factor.ic_ir) },
          { label: 'IC_STD', value: fmt(factor.ic_std) },
        ].map((m) => (
          <div key={m.label} className="flex flex-col items-center">
            <span className="text-[10px] text-[#9a9898]">{m.label}</span>
            <span className="text-xs font-medium text-[#201d1d]">{m.value}</span>
          </div>
        ))}
      </div>

      {/* 绩效指标 */}
      <div className="mb-3 grid grid-cols-4 gap-1">
        {[
          { label: '年化收益', value: fmtPct(factor.annualized_return) },
          { label: '最大回撤', value: fmtPct(factor.maximum_drawdown) },
          { label: '夏普比率', value: fmt(factor.sharpe_ratio, 2) },
          { label: '换手率', value: fmtPct(factor.turnover_rate) },
        ].map((m) => (
          <div key={m.label} className="flex flex-col items-center">
            <span className="text-[10px] text-[#9a9898]">{m.label}</span>
            <span className="text-xs font-medium text-[#201d1d]">{m.value}</span>
          </div>
        ))}
      </div>

      {/* 操作 */}
      <button
        type="button"
        disabled={adding}
        className="mt-auto w-full rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2 py-1.5 text-xs font-medium text-[#201d1d] transition-colors hover:bg-[#f8f7f7] disabled:text-[#9a9898] cursor-pointer"
        onClick={() => onAddToPool(factor.id)}
      >
        {adding ? '加入中...' : '[+] 加入因子池'}
      </button>
    </div>
  );
}

/* ── 列表视图 ── */
function FactorListView({
  factors,
  sortField,
  sortOrder,
  onSort,
  onAddToPool,
  addingId,
}: {
  factors: PresetFactor[];
  sortField: string | undefined;
  sortOrder: 'asc' | 'desc';
  onSort: (field: SortField) => void;
  onAddToPool: (id: number) => void;
  addingId: number | null;
}) {
  const SortHeader = ({ field, label }: { field: SortField; label: string }) => (
    <th
      className="border-b border-[rgba(15,0,0,0.12)] px-3 py-2 text-left text-xs font-medium text-[#646262] cursor-pointer select-none hover:text-[#201d1d]"
      onClick={() => onSort(field)}
    >
      <span className="inline-flex items-center gap-1">
        {label}
        {sortField === field && (
          <span className="text-[#007aff]">{sortOrder === 'asc' ? '↑' : '↓'}</span>
        )}
      </span>
    </th>
  );

  return (
    <table className="w-full border-collapse text-sm">
      <thead>
        <tr className="bg-[#f8f7f7]">
          <th className="border-b border-[rgba(15,0,0,0.12)] px-3 py-2 text-left text-xs font-medium text-[#646262]">
            因子名称
          </th>
          <th className="border-b border-[rgba(15,0,0,0.12)] px-3 py-2 text-left text-xs font-medium text-[#646262]">
            分类
          </th>
          {SORT_OPTIONS.map((o) => (
            <SortHeader key={o.field} field={o.field} label={o.label} />
          ))}
          <th className="border-b border-[rgba(15,0,0,0.12)] px-3 py-2 text-left text-xs font-medium text-[#646262]">
            年化收益
          </th>
          <th className="border-b border-[rgba(15,0,0,0.12)] px-3 py-2 text-left text-xs font-medium text-[#646262]">
            最大回撤
          </th>
          <th className="border-b border-[rgba(15,0,0,0.12)] px-3 py-2 text-left text-xs font-medium text-[#646262]">
            夏普比率
          </th>
          <th className="border-b border-[rgba(15,0,0,0.12)] px-3 py-2 text-left text-xs font-medium text-[#646262]">
            操作
          </th>
        </tr>
      </thead>
      <tbody>
        {factors.length === 0 ? (
          <tr>
            <td colSpan={10} className="px-3 py-8 text-center text-[#646262]">
              暂无因子数据
            </td>
          </tr>
        ) : (
          factors.map((f) => (
            <tr
              key={f.id}
              className="border-b border-[rgba(15,0,0,0.12)] transition-colors hover:bg-[#f1eeee]"
            >
              <td className="px-3 py-2 text-sm font-medium text-[#201d1d]">
                {f.factor_name}
              </td>
              <td className="px-3 py-2">
                <span className="inline-flex items-center gap-1 text-xs text-[#646262]">
                  <span
                    className="inline-block h-[6px] w-[6px] rounded-full"
                    style={{ backgroundColor: f.category_color_hex || '#646262' }}
                  />
                  {f.category_name || '未分类'}
                </span>
              </td>
              <td className="px-3 py-2 text-xs text-[#201d1d]">{fmt(f.ic_mean)}</td>
              <td className="px-3 py-2 text-xs text-[#201d1d]">{fmt(f.rank_ic)}</td>
              <td className="px-3 py-2 text-xs text-[#201d1d]">{fmt(f.ic_ir)}</td>
              <td className="px-3 py-2 text-xs text-[#201d1d]">{fmtPct(f.annualized_return)}</td>
              <td className="px-3 py-2 text-xs text-[#201d1d]">{fmtPct(f.maximum_drawdown)}</td>
              <td className="px-3 py-2 text-xs text-[#201d1d]">{fmt(f.sharpe_ratio, 2)}</td>
              <td className="px-3 py-2">
                <button
                  type="button"
                  disabled={addingId === f.id}
                  className="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2 py-1 text-xs text-[#201d1d] transition-colors hover:bg-[#f8f7f7] disabled:text-[#9a9898] cursor-pointer"
                  onClick={() => onAddToPool(f.id)}
                >
                  {addingId === f.id ? '...' : '[+]'}
                </button>
              </td>
            </tr>
          ))
        )}
      </tbody>
    </table>
  );
}

/* ── 分页组件 ── */
function Pagination({
  page,
  totalPages,
  onPageChange,
}: {
  page: number;
  totalPages: number;
  onPageChange: (p: number) => void;
}) {
  if (totalPages <= 1) return null;

  const pages: (number | '...')[] = [];
  for (let i = 1; i <= totalPages; i++) {
    if (i === 1 || i === totalPages || (i >= page - 2 && i <= page + 2)) {
      pages.push(i);
    } else if (pages[pages.length - 1] !== '...') {
      pages.push('...');
    }
  }

  return (
    <div className="flex items-center justify-center gap-1 py-3">
      <button
        type="button"
        disabled={page <= 1}
        className="rounded-[4px] border border-[rgba(15,0,0,0.12)] px-2 py-1 text-xs text-[#646262] transition-colors hover:text-[#201d1d] disabled:text-[#9a9898] disabled:cursor-not-allowed cursor-pointer"
        onClick={() => onPageChange(page - 1)}
      >
        上一页
      </button>
      {pages.map((p, i) =>
        p === '...' ? (
          <span key={`e${i}`} className="px-1 text-xs text-[#9a9898]">
            ...
          </span>
        ) : (
          <button
            key={p}
            type="button"
            className={`rounded-[4px] px-2 py-1 text-xs transition-colors cursor-pointer ${
              p === page
                ? 'bg-[#201d1d] text-[#fdfcfc]'
                : 'border border-[rgba(15,0,0,0.12)] text-[#646262] hover:text-[#201d1d]'
            }`}
            onClick={() => onPageChange(p)}
          >
            {p}
          </button>
        )
      )}
      <button
        type="button"
        disabled={page >= totalPages}
        className="rounded-[4px] border border-[rgba(15,0,0,0.12)] px-2 py-1 text-xs text-[#646262] transition-colors hover:text-[#201d1d] disabled:text-[#9a9898] disabled:cursor-not-allowed cursor-pointer"
        onClick={() => onPageChange(page + 1)}
      >
        下一页
      </button>
    </div>
  );
}

/* ── 主组件 ── */
export default function FactorLibrary() {
  const [viewMode, setViewMode] = useState<ViewMode>('card');
  const [search, setSearch] = useState('');
  const [categoryCode, setCategoryCode] = useState('');
  const [sortField, setSortField] = useState<SortField | undefined>(undefined);
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const [page, setPage] = useState(1);
  const pageSize = 30;

  // 搜索防抖
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const handleSearchChange = useCallback((value: string) => {
    setSearch(value);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      setDebouncedSearch(value);
      setPage(1);
    }, 300);
  }, []);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  // 构建查询参数
  const queryParams = useMemo<PresetFactorParams>(() => {
    const params: PresetFactorParams = { page, page_size: pageSize };
    if (categoryCode) params.category_code = categoryCode;
    if (sortField) {
      params.sort_field = sortField;
      params.sort_order = sortOrder;
    }
    if (debouncedSearch) params.search = debouncedSearch;
    return params;
  }, [page, categoryCode, sortField, sortOrder, debouncedSearch]);

  // 数据查询
  const { data, isLoading, isFetching } = usePresetFactors(queryParams);
  const { data: categories } = usePresetFactorCategories();
  const addToPoolMutation = useAddToFactorPool();
  const [addingId, setAddingId] = useState<number | null>(null);

  // 分类切换
  const handleCategoryClick = useCallback((code: string) => {
    setCategoryCode((prev) => (prev === code ? '' : code));
    setPage(1);
  }, []);

  // 排序切换
  const handleSort = useCallback(
    (field: SortField) => {
      if (sortField === field) {
        setSortOrder((prev) => (prev === 'desc' ? 'asc' : 'desc'));
      } else {
        setSortField(field);
        setSortOrder('desc');
      }
      setPage(1);
    },
    [sortField]
  );

  // 加入因子池
  const handleAddToPool = useCallback(
    async (id: number) => {
      setAddingId(id);
      try {
        await addToPoolMutation.mutateAsync(id);
      } catch {
        // 静默处理
      } finally {
        setAddingId(null);
      }
    },
    [addToPoolMutation]
  );

  const factors = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / pageSize);
  const totalCount = categories?.reduce((sum, c) => sum + c.factor_count, 0) ?? 0;

  return (
    <div className="flex flex-col">
      {/* 顶部工具栏：搜索 + 视图切换 */}
      <div className="mb-3 flex items-center gap-3">
        <div className="relative flex-1">
          <Input
            placeholder="搜索因子名称 / 描述 / 公式..."
            value={search}
            onChange={(e) => handleSearchChange(e.target.value)}
            className="w-full"
          />
        </div>
        <div className="flex items-center gap-1">
          {/* 排序选择 */}
          <select
            className="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2 py-1.5 text-xs text-[#646262] cursor-pointer"
            value={sortField ?? ''}
            onChange={(e) => {
              const v = e.target.value as SortField | '';
              setSortField(v || undefined);
              setPage(1);
            }}
          >
            <option value="">排序</option>
            {SORT_OPTIONS.map((o) => (
              <option key={o.field} value={o.field}>
                {o.label}
              </option>
            ))}
          </select>
          {sortField && (
            <button
              type="button"
              className="rounded-[4px] border border-[rgba(15,0,0,0.12)] px-2 py-1.5 text-xs text-[#646262] cursor-pointer hover:text-[#201d1d]"
              onClick={() => setSortOrder((p) => (p === 'desc' ? 'asc' : 'desc'))}
            >
              {sortOrder === 'desc' ? '↓ 降序' : '↑ 升序'}
            </button>
          )}
          {/* 视图切换 */}
          <div className="flex rounded-[4px] border border-[rgba(15,0,0,0.12)]">
            <button
              type="button"
              className={`px-2 py-1.5 text-xs cursor-pointer transition-colors ${
                viewMode === 'card'
                  ? 'bg-[#201d1d] text-[#fdfcfc]'
                  : 'text-[#646262] hover:text-[#201d1d]'
              }`}
              onClick={() => setViewMode('card')}
            >
              卡片
            </button>
            <button
              type="button"
              className={`px-2 py-1.5 text-xs cursor-pointer transition-colors ${
                viewMode === 'list'
                  ? 'bg-[#201d1d] text-[#fdfcfc]'
                  : 'text-[#646262] hover:text-[#201d1d]'
              }`}
              onClick={() => setViewMode('list')}
            >
              列表
            </button>
          </div>
        </div>
      </div>

      {/* 分类标签栏 */}
      <div className="mb-3 flex gap-2 overflow-x-auto pb-1" style={{ scrollbarWidth: 'thin' }}>
        <button
          type="button"
          className={`shrink-0 rounded-[4px] border px-2 py-1 text-xs transition-colors cursor-pointer ${
            !categoryCode
              ? 'border-[#007aff] bg-[#007aff]/10 text-[#007aff]'
              : 'border-[rgba(15,0,0,0.12)] text-[#646262] hover:text-[#201d1d]'
          }`}
          onClick={() => {
            setCategoryCode('');
            setPage(1);
          }}
        >
          全部·{totalCount}
        </button>
        {categories?.map((cat) => (
          <button
            key={cat.category_code}
            type="button"
            className={`flex shrink-0 items-center gap-1 rounded-[4px] border px-2 py-1 text-xs transition-colors cursor-pointer ${
              categoryCode === cat.category_code
                ? 'border-[#007aff] bg-[#007aff]/10 text-[#007aff]'
                : 'border-[rgba(15,0,0,0.12)] text-[#646262] hover:text-[#201d1d]'
            }`}
            onClick={() => handleCategoryClick(cat.category_code)}
          >
            <span
              className="inline-block h-[6px] w-[6px] rounded-full"
              style={{ backgroundColor: cat.color_hex || '#646262' }}
            />
            {cat.category_name}·{cat.factor_count}
          </button>
        ))}
      </div>

      {/* 内容区域 */}
      <div className={`relative ${isFetching ? 'opacity-60' : ''}`}>
        {isLoading ? (
          <div className="flex h-[200px] items-center justify-center">
            <span className="text-xs text-[#646262]">加载中...</span>
          </div>
        ) : viewMode === 'card' ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {factors.map((f) => (
              <FactorCard
                key={f.id}
                factor={f}
                onAddToPool={handleAddToPool}
                adding={addingId === f.id}
              />
            ))}
            {factors.length === 0 && (
              <div className="col-span-full flex h-[120px] items-center justify-center">
                <span className="text-xs text-[#646262]">暂无因子数据</span>
              </div>
            )}
          </div>
        ) : (
          <FactorListView
            factors={factors}
            sortField={sortField}
            sortOrder={sortOrder}
            onSort={handleSort}
            onAddToPool={handleAddToPool}
            addingId={addingId}
          />
        )}
      </div>

      {/* 分页 */}
      <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />
    </div>
  );
}
