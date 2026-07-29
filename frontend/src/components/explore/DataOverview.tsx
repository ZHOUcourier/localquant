/**
 * DataOverview — 本地数据概览
 *
 * 展示各周期 Parquet 缓存的表结构、股票数量、数据区间与可用代码，
 * 为 SQL 查询 / 扫描 / 截面分析提供数据地图。
 */
import { useQuery } from '@tanstack/react-query';

interface TableInfo {
  period: string;
  path: string;
  stock_count: number;
  columns: string[];
  sample_range: string;
  codes: string[];
}

async function fetchTables(): Promise<{ tables: TableInfo[] }> {
  const res = await fetch('/api/explorer/tables');
  if (!res.ok) throw new Error(`Failed to fetch tables: ${res.status}`);
  return res.json();
}

export function DataOverview() {
  const { data, isLoading } = useQuery({
    queryKey: ['explorer-tables'],
    queryFn: fetchTables,
    staleTime: 60 * 1000,
  });

  if (isLoading) {
    return <div className="py-8 text-center text-xs text-[#646262]">加载中...</div>;
  }

  const tables = data?.tables ?? [];

  if (tables.length === 0) {
    return (
      <div className="rounded-[4px] border border-[rgba(15,0,0,0.12)] px-4 py-10 text-center text-sm text-[#646262]">
        本地暂无行情缓存数据
        <div className="mt-2 text-xs text-[#9a9898]">
          请先在「数据下载」标签页下载行情，数据将缓存到 data/cache/ 供 SQL 查询与探索分析使用
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {tables.map((t) => (
        <div
          key={t.period}
          className="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f1eeee] p-4"
        >
          <div className="mb-2 flex items-center justify-between">
            <span className="text-sm font-medium text-[#201d1d]">
              [{t.period}] 行情数据
            </span>
            <span className="text-xs text-[#646262]">
              {t.stock_count} 只股票 · {t.sample_range || '区间未知'}
            </span>
          </div>
          <div className="mb-2 text-xs text-[#646262]">
            SQL 路径：
            <code className="rounded-[3px] bg-[#201d1d] px-1.5 py-0.5 text-[11px] text-[#fdfcfc]">
              read_parquet('{t.path}')
            </code>
          </div>
          <div className="mb-2 flex flex-wrap gap-1">
            <span className="text-xs text-[#9a9898]">字段：</span>
            {t.columns.map((c) => (
              <span
                key={c}
                className="rounded-[3px] border border-[rgba(15,0,0,0.10)] bg-[#fdfcfc] px-1.5 py-0.5 text-[11px] text-[#201d1d]"
              >
                {c}
              </span>
            ))}
          </div>
          <details className="text-xs text-[#646262]">
            <summary className="cursor-pointer select-none hover:text-[#201d1d]">
              查看已缓存股票代码（前 {t.codes.length} 个）
            </summary>
            <div className="mt-2 flex max-h-[120px] flex-wrap gap-1 overflow-auto">
              {t.codes.map((c) => (
                <span key={c} className="rounded-[3px] bg-[#fdfcfc] px-1.5 py-0.5 font-mono text-[11px]">
                  {c}
                </span>
              ))}
            </div>
          </details>
        </div>
      ))}
    </div>
  );
}
