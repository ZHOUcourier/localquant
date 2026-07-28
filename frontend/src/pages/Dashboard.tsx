import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { GitBranch, Search, FlaskConical, BarChart3, Wifi, WifiOff, Database } from 'lucide-react';
import { Card, Badge } from '@/components/ui';

const quickActions = [
  { title: '新建工作流', description: '创建自动化数据处理与分析流程', icon: GitBranch, path: '/workflow', color: '#007aff' },
  { title: '数据探索', description: '浏览和搜索市场数据', icon: Search, path: '/explore', color: '#64d2ff' },
  { title: '因子研究', description: '构建和分析 Alpha 因子', icon: FlaskConical, path: '/factor', color: '#30d158' },
  { title: '运行回测', description: '执行策略回测并查看结果', icon: BarChart3, path: '/backtest', color: '#ff9f0a' },
];

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
  [key: string]: unknown;
}

function formatTime(ts: number) {
  if (!ts) return '-';
  return new Date(ts * 1000).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}

const statusVariant: Record<string, 'success' | 'warning' | 'error' | 'info' | 'default'> = {
  success: 'success', completed: 'success', running: 'warning', failed: 'error', pending: 'default',
};

export default function Dashboard() {
  const navigate = useNavigate();

  const { data: workflows = [] } = useQuery<WorkflowItem[]>({
    queryKey: ['workflows'],
    queryFn: () => fetch('/api/workflow/').then(r => r.json()),
  });

  const { data: experiments = [] } = useQuery<Experiment[]>({
    queryKey: ['experiments'],
    queryFn: () => fetch('/api/experiment/?limit=5').then(r => r.json()),
  });

  const { data: dataStatus } = useQuery<DataStatus>({
    queryKey: ['data-status'],
    queryFn: () => fetch('/api/data/status').then(r => r.json()),
  });

  const recentWorkflows = [...workflows].sort((a, b) => (b.updated_at || 0) - (a.updated_at || 0)).slice(0, 5);
  const recentExperiments = experiments.slice(0, 5);

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-[#fdfcfc] mb-1">工作台</h1>
        <p className="text-[13px] text-[#9a9898]">欢迎使用 LocalQuant 本地投研平台</p>
      </div>

      {/* 快速操作 */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {quickActions.map(({ title, description, icon: Icon, path, color }) => (
          <Card
            key={title}
            className="cursor-pointer hover:border-[#007aff] transition-colors duration-150"
            onClick={() => navigate(path)}
          >
            <div className="flex flex-col gap-3 py-2">
              <div className="flex items-center justify-center w-9 h-9 rounded" style={{ background: `${color}20` }}>
                <Icon size={20} style={{ color }} />
              </div>
              <div>
                <div className="text-sm font-medium text-[#fdfcfc] mb-1">{title}</div>
                <div className="text-[12px] text-[#9a9898] leading-relaxed">{description}</div>
              </div>
            </div>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* 最近工作流 */}
        <Card title="最近工作流" extra={<button className="text-xs text-[#007aff] hover:underline cursor-pointer" onClick={() => navigate('/workflow')}>查看全部</button>}>
          {recentWorkflows.length === 0 ? (
            <p className="text-xs text-[#6e6e73] py-4 text-center">暂无工作流</p>
          ) : (
            <div className="space-y-2">
              {recentWorkflows.map(wf => (
                <div
                  key={wf.id}
                  className="flex items-center justify-between p-2 rounded hover:bg-[#363131] cursor-pointer transition-colors"
                  onClick={() => navigate(`/workflow/${wf.id}`)}
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <GitBranch size={14} className="text-[#007aff] flex-shrink-0" />
                    <span className="text-sm text-[#fdfcfc] truncate">{wf.name || '未命名工作流'}</span>
                  </div>
                  <span className="text-xs text-[#6e6e73] flex-shrink-0 ml-2">{formatTime(wf.updated_at)}</span>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* 最近实验 */}
        <Card title="最近实验" extra={<button className="text-xs text-[#007aff] hover:underline cursor-pointer" onClick={() => navigate('/experiments')}>查看全部</button>}>
          {recentExperiments.length === 0 ? (
            <p className="text-xs text-[#6e6e73] py-4 text-center">暂无实验</p>
          ) : (
            <div className="space-y-2">
              {recentExperiments.map(exp => (
                <div key={exp.id} className="flex items-center justify-between p-2 rounded hover:bg-[#363131] cursor-pointer transition-colors" onClick={() => navigate('/experiments')}>
                  <div className="flex items-center gap-2 min-w-0">
                    <FlaskConical size={14} className="text-[#30d158] flex-shrink-0" />
                    <span className="text-sm text-[#fdfcfc] truncate">{exp.name || exp.id.slice(0, 8)}</span>
                    <Badge variant={statusVariant[exp.status] || 'default'} className="flex-shrink-0">{exp.status}</Badge>
                  </div>
                  <div className="flex gap-1 flex-shrink-0 ml-2">
                    {Object.entries(exp.metrics || {}).slice(0, 1).map(([k, v]) => (
                      <span key={k} className="text-xs text-[#9a9898]">
                        {k}: {typeof v === 'number' ? v.toFixed(4) : String(v)}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* 数据状态 */}
        <Card title="数据状态">
          <div className="space-y-3 py-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                {dataStatus?.qmt_connected ? (
                  <Wifi size={16} className="text-[#30d158]" />
                ) : (
                  <WifiOff size={16} className="text-[#ff3b30]" />
                )}
                <span className="text-sm text-[#fdfcfc]">QMT 连接</span>
              </div>
              <Badge variant={dataStatus?.qmt_connected ? 'success' : 'error'}>
                {dataStatus?.qmt_connected ? '已连接' : '未连接'}
              </Badge>
            </div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Database size={16} className="text-[#64d2ff]" />
                <span className="text-sm text-[#fdfcfc]">缓存数据</span>
              </div>
              <span className="text-sm text-[#9a9898]">
                {dataStatus?.cache_count ?? 0} 品种 / {dataStatus?.cache_size ?? '0 B'}
              </span>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
