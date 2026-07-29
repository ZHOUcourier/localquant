/**
 * FactorReferenceDialog — 因子编写「变量与算子参考」
 *
 * 展示可用基础字段、算子函数分组与示例，与后端公式求值环境一致。
 * 让使用者知道公式/代码模式下可以用哪些变量与函数。
 */
import { useQuery } from '@tanstack/react-query';
import { Dialog } from '@/components/ui/Dialog';
import { Button } from '@/components/ui/Button';

interface FactorField {
  name: string;
  desc: string;
  available: boolean;
}
interface OperatorGroup {
  group: string;
  ops: string[];
}
interface FactorReference {
  fields: FactorField[];
  operator_groups: OperatorGroup[];
  examples: { title: string; formula: string }[];
}

async function fetchReference(): Promise<FactorReference> {
  const res = await fetch('/api/factor/reference');
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export function FactorReferenceDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { data } = useQuery({
    queryKey: ['factor-reference'],
    queryFn: fetchReference,
    enabled: open,
    staleTime: 10 * 60 * 1000,
  });

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="因子编写 · 变量与算子参考"
      className="!max-w-[640px] w-[640px]"
      footer={<Button variant="secondary" onClick={onClose}>关闭</Button>}
    >
      <div className="flex max-h-[70vh] flex-col gap-4 overflow-auto text-xs">
        <div className="rounded-[4px] bg-[#f8f7f7] px-3 py-2 leading-relaxed text-[#646262]">
          因子构建支持<b>公式</b>与<b>代码</b>两种方式，二者共用同一套字段与算子（大小写均可）。
          公式可直接在「因子构建（公式）」节点运行；代码方式把结果写入 <code className="rounded bg-[#201d1d] px-1 text-[#fdfcfc]">factor_data</code>。
        </div>

        {/* 基础字段 */}
        <section>
          <div className="mb-2 text-[13px] font-semibold text-[#201d1d]">基础字段</div>
          <div className="grid grid-cols-2 gap-1.5">
            {data?.fields.map((f) => (
              <div
                key={f.name}
                className="flex items-center justify-between rounded-[4px] border border-[rgba(15,0,0,0.10)] bg-[#fdfcfc] px-2 py-1.5"
              >
                <span className="font-mono text-[#201d1d]">{f.name}</span>
                <span className="flex items-center gap-1.5 text-[#646262]">
                  {f.desc}
                  <span className={f.available ? 'text-[#30d158]' : 'text-[#ff9f0a]'}>
                    {f.available ? '●' : '○'}
                  </span>
                </span>
              </div>
            ))}
          </div>
          <div className="mt-1 text-[10px] text-[#9a9898]">● 本地可用　○ 需先下载对应数据</div>
        </section>

        {/* 算子分组 */}
        <section>
          <div className="mb-2 text-[13px] font-semibold text-[#201d1d]">算子函数</div>
          <div className="flex flex-col gap-2">
            {data?.operator_groups.map((g) => (
              <div key={g.group}>
                <div className="mb-1 text-[11px] font-medium text-[#646262]">{g.group}</div>
                <div className="flex flex-wrap gap-1">
                  {g.ops.map((op) => (
                    <span
                      key={op}
                      className="rounded-[3px] border border-[rgba(15,0,0,0.10)] bg-[#f1eeee] px-1.5 py-0.5 font-mono text-[11px] text-[#201d1d]"
                    >
                      {op}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* 示例 */}
        <section>
          <div className="mb-2 text-[13px] font-semibold text-[#201d1d]">公式示例</div>
          <div className="flex flex-col gap-1.5">
            {data?.examples.map((ex) => (
              <div key={ex.title} className="rounded-[4px] border border-[rgba(15,0,0,0.10)] overflow-hidden">
                <div className="bg-[#f8f7f7] px-2 py-1 text-[11px] text-[#646262]">{ex.title}</div>
                <pre className="overflow-auto bg-[#201d1d] px-2 py-1.5 font-mono text-[11px] text-[#fdfcfc]">
                  {ex.formula}
                </pre>
              </div>
            ))}
          </div>
        </section>
      </div>
    </Dialog>
  );
}
