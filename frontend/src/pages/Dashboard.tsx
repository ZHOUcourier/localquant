import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowRight } from 'lucide-react';
import { useBackendHealth } from '@/hooks/useBackendHealth';

// ── Types ──────────────────────────────────────────────────────────

interface WorkflowItem {
  id: string;
  name: string;
  description: string;
  updated_at: number;
}

interface Experiment {
  id: string;
  source: string;
  name: string;
  status: string;
  metrics: Record<string, unknown>;
  created_at: number;
}

interface DataStatus {
  qmt_connected?: boolean;
  cache_count?: number;
  cache_size?: string;
  total_records?: number;
  [key: string]: unknown;
}

interface PresetFactorResult {
  total: number;
  items: unknown[];
  [key: string]: unknown;
}

// ── Helpers ────────────────────────────────────────────────────────

function formatTime(ts: number) {
  if (!ts) return '-';
  return new Date(ts * 1000).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

// ── Reusable section components ────────────────────────────────────

function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-3">
      <h2
        className="text-base font-bold text-[#201d1d]"
        style={{ fontFamily: 'Berkeley Mono, IBM Plex Mono, ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace' }}
      >
        {children}
      </h2>
      <div className="mt-1" style={{ borderBottom: '1px solid rgba(15,0,0,0.12)' }} />
    </div>
  );
}

function StatusCard({
  label,
  value,
  indicator,
}: {
  label: string;
  value: string;
  indicator?: 'ok' | 'warn' | 'error';
}) {
  const indicatorChar = indicator === 'ok' ? '+' : indicator === 'error' ? 'x' : '-';
  const indicatorColor =
    indicator === 'ok' ? '#30d158' : indicator === 'error' ? '#ff3b30' : '#646262';

  return (
    <div
      className="rounded-[4px] px-4 py-3"
      style={{
        backgroundColor: '#f1eeee',
        border: '1px solid rgba(15,0,0,0.12)',
      }}
    >
      <div className="flex items-center justify-between">
        <span
          className="text-sm text-[#646262]"
          style={{ fontFamily: 'Berkeley Mono, IBM Plex Mono, ui-monospace, monospace' }}
        >
          [{indicatorChar}] {label}
        </span>
      </div>
      <div
        className="mt-1 text-base font-medium text-[#201d1d]"
        style={{ fontFamily: 'Berkeley Mono, IBM Plex Mono, ui-monospace, monospace' }}
      >
        <span style={{ color: indicatorColor }}>{value}</span>
      </div>
    </div>
  );
}

function StatRow({
  label,
  detail,
  extra,
  onClick,
}: {
  label: string;
  detail: string;
  /** 展开后显示的明细内容 */
  extra?: React.ReactNode;
  onClick?: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const mono = 'Berkeley Mono, IBM Plex Mono, ui-monospace, monospace';
  return (
    <div>
      <div className="flex items-center justify-between py-2 px-2 rounded-[4px] transition-colors hover:bg-[#f1eeee]">
        {/* [+] / [-] 切换展开 */}
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="flex items-center gap-2 bg-transparent border-none cursor-pointer p-0"
          style={{ fontFamily: mono }}
          title={expanded ? '收起' : '展开详情'}
        >
          <span className="text-sm text-[#646262]">{expanded ? '[-]' : '[+]'}</span>
          <span className="text-sm text-[#201d1d]">{label}</span>
        </button>
        <div className="flex items-center gap-2">
          <span className="text-sm text-[#646262]" style={{ fontFamily: mono }}>
            {detail}
          </span>
          {/* 小箭头：跳转到对应页面 */}
          <button
            type="button"
            onClick={onClick}
            className="flex h-5 w-5 items-center justify-center rounded-[4px] text-[#646262] transition-colors hover:bg-[#e8e5e5] hover:text-[#201d1d] bg-transparent border-none cursor-pointer"
            style={{ fontFamily: mono }}
            title="进入"
          >
            <ArrowRight size={13} />
          </button>
        </div>
      </div>
      {expanded && extra && (
        <div className="px-2 pb-2 pl-8 text-xs text-[#646262]" style={{ fontFamily: mono }}>
          {extra}
        </div>
      )}
    </div>
  );
}

function ActivityRow({
  name,
  right,
  onClick,
}: {
  name: string;
  right: React.ReactNode;
  onClick?: () => void;
}) {
  return (
    <div
      className="flex items-center justify-between py-2 px-2 rounded-[4px] cursor-pointer hover:bg-[#f1eeee] transition-colors"
      onClick={onClick}
    >
      <span
        className="text-sm text-[#201d1d] truncate mr-3"
        style={{ fontFamily: 'Berkeley Mono, IBM Plex Mono, ui-monospace, monospace' }}
      >
        {name}
      </span>
      <span
        className="text-xs text-[#646262] flex-shrink-0"
        style={{ fontFamily: 'Berkeley Mono, IBM Plex Mono, ui-monospace, monospace' }}
      >
        {right}
      </span>
    </div>
  );
}

// ── Main Component ─────────────────────────────────────────────────

export default function Dashboard() {
  const navigate = useNavigate();
  const { online, checking, version } = useBackendHealth();

  // Data fetching
  const { data: workflows = [] } = useQuery<WorkflowItem[]>({
    queryKey: ['workflows', 'my', ''],
    queryFn: () =>
      fetch('/api/workflow/?tab=my&search=').then((r) => r.json()),
  });

  const { data: presetWorkflows = [] } = useQuery<WorkflowItem[]>({
    queryKey: ['workflows', 'preset', ''],
    queryFn: () => fetch('/api/workflow/?tab=preset&search=').then((r) => r.json()),
  });

  const { data: experiments = [] } = useQuery<Experiment[]>({
    queryKey: ['experiments', 'dashboard'],
    queryFn: () => fetch('/api/experiment/?limit=50').then((r) => r.json()),
  });

  const { data: dataStatus } = useQuery<DataStatus>({
    queryKey: ['data-status'],
    queryFn: () => fetch('/api/data/status').then((r) => r.json()),
  });

  const { data: presetFactorData } = useQuery<PresetFactorResult>({
    queryKey: ['preset-factors-count'],
    queryFn: () =>
      fetch('/api/factor/preset?page=1&page_size=1').then((r) => r.json()),
  });

  const { data: libraryFactors = [] } = useQuery<unknown[]>({
    queryKey: ['factor-library'],
    queryFn: () => fetch('/api/factor/library').then((r) => r.json()),
  });

  // Derived data
  const myWorkflows = workflows;
  const totalWorkflows = myWorkflows.length + presetWorkflows.length;
  const myWorkflowCount = myWorkflows.length;
  const presetFactorCount = presetFactorData?.total ?? 0;
  const customFactorCount = libraryFactors.length;
  const experimentCount = experiments.length;
  const recentExperiments = experiments.slice(0, 5);

  const recentWorkflows = [...myWorkflows]
    .sort((a, b) => (b.updated_at || 0) - (a.updated_at || 0))
    .slice(0, 5);

  const mono = 'Berkeley Mono, IBM Plex Mono, ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace';

  return (
    <div className="max-w-[960px] mx-auto">
      {/* Page title */}
      <div className="mb-8">
        <h1
          className="text-base font-bold text-[#201d1d] mb-1"
          style={{ fontFamily: mono }}
        >
          [+] 工作台
        </h1>
        <p className="text-sm text-[#646262]" style={{ fontFamily: mono }}>
          LocalQuant 本地投研平台
        </p>
      </div>

      {/* ── 系统状态概览 ─────────────────────────────────────────── */}
      <div className="mb-12">
        <SectionHeader>系统状态</SectionHeader>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <StatusCard
            label="后端"
            value={
              checking
                ? '检查中...'
                : online
                  ? `在线 v${version ?? ''}`
                  : '离线'
            }
            indicator={checking ? undefined : online ? 'ok' : 'error'}
          />
          <StatusCard
            label="QMT"
            value={
              dataStatus?.qmt_connected ? '已连接' : '未连接'
            }
            indicator={dataStatus?.qmt_connected ? 'ok' : 'error'}
          />
          <StatusCard
            label="缓存"
            value={`${dataStatus?.cache_count ?? 0} 品种 / ${dataStatus?.cache_size ?? '0 B'}`}
            indicator={dataStatus?.cache_count ? 'ok' : undefined}
          />
          <StatusCard
            label="记录数"
            value={`${dataStatus?.total_records ?? 0} 条`}
            indicator={dataStatus?.total_records ? 'ok' : undefined}
          />
        </div>
      </div>

      {/* ── 模块统计 ─────────────────────────────────────────────── */}
      <div className="mb-12">
        <SectionHeader>内容统计</SectionHeader>
        <div
          className="rounded-[4px]"
          style={{
            border: '1px solid rgba(15,0,0,0.12)',
            backgroundColor: '#fdfcfc',
          }}
        >
          <StatRow
            label="工作流"
            detail={`预置 ${totalWorkflows - myWorkflowCount} 个，我的 ${myWorkflowCount} 个`}
            extra={
              <div className="leading-relaxed">
                预置模板 {totalWorkflows - myWorkflowCount} 个·可直接复制为自己的工作流<br />
                我的工作流 {myWorkflowCount} 个·点右侧箭头进入工作流列表
              </div>
            }
            onClick={() => navigate('/workflow')}
          />
          <div style={{ borderBottom: '1px solid rgba(15,0,0,0.12)' }} />
          <StatRow
            label="因子库"
            detail={`预置 ${presetFactorCount} 个，自建 ${customFactorCount} 个`}
            extra={
              <div className="leading-relaxed">
                预置因子 {presetFactorCount} 个·支持公式/LaTeX 查看、IC 排序与 AI 分析<br />
                自建因子 {customFactorCount} 个·点右侧箭头进入因子研究
              </div>
            }
            onClick={() => navigate('/factor')}
          />
          <div style={{ borderBottom: '1px solid rgba(15,0,0,0.12)' }} />
          <StatRow
            label="实验"
            detail={`${experimentCount} 个`}
            extra={<div>共 {experimentCount} 个实验记录·点右侧箭头查看实验列表</div>}
            onClick={() => navigate('/experiments')}
          />
        </div>
      </div>

      {/* ── 最近活动 ─────────────────────────────────────────────── */}
      <div className="mb-12">
        <SectionHeader>最近活动</SectionHeader>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* 最近工作流 */}
          <div>
            <div
              className="flex items-center justify-between mb-2"
            >
              <span
                className="text-sm font-medium text-[#201d1d]"
                style={{ fontFamily: mono }}
              >
                工作流
              </span>
              <button
                className="text-xs text-[#646262] hover:text-[#201d1d] cursor-pointer transition-colors"
                style={{ fontFamily: mono }}
                onClick={() => navigate('/workflow')}
              >
                查看全部 →
              </button>
            </div>
            <div
              className="rounded-[4px]"
              style={{
                border: '1px solid rgba(15,0,0,0.12)',
                backgroundColor: '#fdfcfc',
              }}
            >
              {recentWorkflows.length === 0 ? (
                <div
                  className="py-4 text-center text-sm text-[#646262]"
                  style={{ fontFamily: mono }}
                >
                  [-] 暂无工作流
                </div>
              ) : (
                recentWorkflows.map((wf, i) => (
                  <div key={wf.id}>
                    <ActivityRow
                      name={wf.name || '未命名工作流'}
                      right={formatTime(wf.updated_at)}
                      onClick={() => navigate(`/workflow/${wf.id}`)}
                    />
                    {i < recentWorkflows.length - 1 && (
                      <div style={{ borderBottom: '1px solid rgba(15,0,0,0.12)' }} />
                    )}
                  </div>
                ))
              )}
            </div>
          </div>

          {/* 最近实验 */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <span
                className="text-sm font-medium text-[#201d1d]"
                style={{ fontFamily: mono }}
              >
                实验
              </span>
              <button
                className="text-xs text-[#646262] hover:text-[#201d1d] cursor-pointer transition-colors"
                style={{ fontFamily: mono }}
                onClick={() => navigate('/experiments')}
              >
                查看全部 →
              </button>
            </div>
            <div
              className="rounded-[4px]"
              style={{
                border: '1px solid rgba(15,0,0,0.12)',
                backgroundColor: '#fdfcfc',
              }}
            >
              {recentExperiments.length === 0 ? (
                <div
                  className="py-4 text-center text-sm text-[#646262]"
                  style={{ fontFamily: mono }}
                >
                  [-] 暂无实验
                </div>
              ) : (
                recentExperiments.map((exp, i) => (
                  <div key={exp.id}>
                    <ActivityRow
                      name={exp.name || exp.id.slice(0, 8)}
                      right={
                        <span className="flex items-center gap-2">
                          <span
                            className="text-xs px-1.5 py-0.5 rounded-[4px]"
                            style={{
                              backgroundColor:
                                exp.status === 'completed'
                                  ? '#30d15820'
                                  : exp.status === 'running'
                                    ? '#ff9f0a20'
                                    : exp.status === 'failed'
                                      ? '#ff3b3020'
                                      : '#f8f7f7',
                              color:
                                exp.status === 'completed'
                                  ? '#30d158'
                                  : exp.status === 'running'
                                    ? '#cc7f08'
                                    : exp.status === 'failed'
                                      ? '#d70015'
                                      : '#646262',
                            }}
                          >
                            {exp.status}
                          </span>
                          <span>{formatTime(exp.created_at)}</span>
                        </span>
                      }
                      onClick={() => navigate('/experiments')}
                    />
                    {i < recentExperiments.length - 1 && (
                      <div style={{ borderBottom: '1px solid rgba(15,0,0,0.12)' }} />
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
