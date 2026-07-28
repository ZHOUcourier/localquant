import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, Star, Trash2, Eye, Copy, Plus, FolderOpen, Download, CheckSquare, Square, X } from 'lucide-react';
import { useWorkflows, useDeleteWorkflow, useWorkflowTemplates, useToggleFavorite } from '../hooks/useWorkflow';
import { useQueryClient } from '@tanstack/react-query';
import { Input } from '../components/ui/Input';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Dialog } from '../components/ui/Dialog';
import { ConfirmDialog } from '../components/ui/ConfirmDialog';

type TabKey = 'preset' | 'my' | 'favorite';

const TABS: { key: TabKey; label: string }[] = [
  { key: 'preset', label: '[+] 预置模板' },
  { key: 'my', label: '[+] 我创建的' },
  { key: 'favorite', label: '[+] 收藏' },
];

export default function WorkflowList() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<TabKey>('my');
  const [search, setSearch] = useState('');
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
  // 批量管理
  const [batchMode, setBatchMode] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [batchDeleteConfirm, setBatchDeleteConfirm] = useState(false);
  const [batchBusy, setBatchBusy] = useState(false);

  const { data: workflows, isLoading } = useWorkflows(activeTab, search);
  const { data: templates } = useWorkflowTemplates();
  const deleteMutation = useDeleteWorkflow();
  const toggleFavorite = useToggleFavorite();

  // 新建/用模板：只打开编辑器，不创建 DB 记录，用户点保存才入库
  const handleCreateNew = () => {
    setShowCreateDialog(false);
    navigate('/workflow/new');
  };

  const handleCreateFromTemplate = (templateId: string) => {
    setShowCreateDialog(false);
    navigate(`/workflow/new?template=${encodeURIComponent(templateId)}`);
  };

  // 批量选择
  const toggleSelect = (id: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const allSelected = !!workflows && workflows.length > 0 && workflows.every(w => selected.has(w.id));
  const toggleSelectAll = () => {
    if (!workflows) return;
    setSelected(allSelected ? new Set() : new Set(workflows.map(w => w.id)));
  };

  const exitBatchMode = () => {
    setBatchMode(false);
    setSelected(new Set());
  };

  // 批量导出：拉取详情后合并为一个 JSON 文件（可直接导入）
  const handleBatchExport = async () => {
    if (selected.size === 0) return;
    setBatchBusy(true);
    try {
      const details = await Promise.all(
        [...selected].map(id => fetch(`/api/workflow/${id}`).then(r => r.json()))
      );
      const payload = {
        workflows: details.map(d => ({
          name: d.name,
          description: d.description || '',
          nodes: d.nodes || [],
          links: d.links || [],
        })),
      };
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `workflows-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setBatchBusy(false);
    }
  };

  // 批量删除
  const handleBatchDelete = async () => {
    setBatchBusy(true);
    try {
      await Promise.all(
        [...selected].map(id => fetch(`/api/workflow/${id}`, { method: 'DELETE' }))
      );
      queryClient.invalidateQueries({ queryKey: ['workflows'] });
      exitBatchMode();
    } finally {
      setBatchBusy(false);
      setBatchDeleteConfirm(false);
    }
  };

  const handleDelete = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setDeleteConfirm(id);
  };

  const handleDeleteConfirm = () => {
    if (deleteConfirm) {
      deleteMutation.mutate(deleteConfirm);
      setDeleteConfirm(null);
    }
  };

  const handleToggleFavorite = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    toggleFavorite.mutate(id);
  };

  const formatTime = (ts: number) => {
    const d = new Date(ts * 1000);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return '刚刚';
    if (diffMin < 60) return `${diffMin} 分钟前`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr} 小时前`;
    const diffDay = Math.floor(diffHr / 24);
    if (diffDay < 7) return `${diffDay} 天前`;
    return d.toLocaleDateString('zh-CN');
  };

  return (
    <div className="min-h-screen bg-[#fdfcfc] font-mono">
      <div className="mx-auto max-w-[960px] px-6 py-8">
        {/* 顶部标题栏 */}
        <div className="mb-6 flex items-center justify-between">
          <h1 className="text-[20px] font-bold text-[#201d1d]">
            [+] 工作流
          </h1>
          <div className="flex items-center gap-2">
            {activeTab !== 'preset' && !batchMode && (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setBatchMode(true)}
                className="flex items-center gap-1.5"
              >
                <CheckSquare size={14} />
                批量管理
              </Button>
            )}
            <Button
              variant="primary"
              size="sm"
              onClick={() => setShowCreateDialog(true)}
              className="flex items-center gap-1.5"
            >
              <Plus size={14} />
              创建工作流
            </Button>
          </div>
        </div>

        {/* Tab 导航 */}
        <div
          className="mb-4 flex gap-0"
          style={{ borderBottom: '1px solid rgba(15, 0, 0, 0.12)' }}
        >
          {TABS.map(tab => (
            <button
              key={tab.key}
              type="button"
              onClick={() => setActiveTab(tab.key)}
              className={`
                relative cursor-pointer px-4 py-2 text-sm font-medium transition-colors
                ${activeTab === tab.key
                  ? 'text-[#201d1d]'
                  : 'text-[#646262] hover:text-[#201d1d]'
                }
              `}
            >
              {tab.label}
              {activeTab === tab.key && (
                <span className="absolute bottom-0 left-0 right-0 h-[2px] bg-[#9a9898]" />
              )}
            </button>
          ))}
        </div>

        {/* 搜索框 */}
        {activeTab !== 'preset' && (
          <div className="mb-4">
            <Input
              placeholder="搜索工作流名称..."
              prefix={<Search size={14} />}
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="h-9 w-full max-w-[320px]"
            />
          </div>
        )}

        {/* 批量操作栏 */}
        {batchMode && activeTab !== 'preset' && (
          <div
            className="mb-4 flex items-center gap-2 rounded-[4px] bg-[#f8f7f7] px-3 py-2"
            style={{ border: '1px solid rgba(15, 0, 0, 0.12)' }}
          >
            <button
              type="button"
              onClick={toggleSelectAll}
              className="flex cursor-pointer items-center gap-1.5 text-xs text-[#201d1d]"
            >
              {allSelected ? <CheckSquare size={14} /> : <Square size={14} />}
              全选
            </button>
            <span className="text-xs text-[#646262]">已选 {selected.size} 项</span>
            <div className="flex-1" />
            <Button
              variant="secondary"
              size="sm"
              onClick={handleBatchExport}
              disabled={selected.size === 0 || batchBusy}
              className="flex items-center gap-1 text-xs"
            >
              <Download size={12} />
              导出选中 ({selected.size})
            </Button>
            <Button
              variant="danger"
              size="sm"
              onClick={() => setBatchDeleteConfirm(true)}
              disabled={selected.size === 0 || batchBusy}
              className="flex items-center gap-1 text-xs"
            >
              <Trash2 size={12} />
              删除选中 ({selected.size})
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={exitBatchMode}
              className="flex items-center gap-1 text-xs"
            >
              <X size={12} />
              退出
            </Button>
          </div>
        )}

        {/* 加载中 */}
        {isLoading && (
          <div className="py-16 text-center text-sm text-[#646262]">
            加载中...
          </div>
        )}

        {/* 空状态 */}
        {!isLoading && (!workflows || workflows.length === 0) && (
          <div className="flex flex-col items-center justify-center py-20">
            <div className="mb-4 text-[#9a9898]">
              <FolderOpen size={40} />
            </div>
            <p className="mb-2 text-sm text-[#424245]">
              {activeTab === 'preset' && '暂无预置模板'}
              {activeTab === 'my' && '还没有工作流'}
              {activeTab === 'favorite' && '还没有收藏的工作流'}
            </p>
            {activeTab === 'my' && (
              <Button variant="primary" size="sm" onClick={() => setShowCreateDialog(true)}>
                创建第一个工作流
              </Button>
            )}
          </div>
        )}

        {/* 表格视图 */}
        {!isLoading && workflows && workflows.length > 0 && (
          <div
            className="overflow-hidden rounded-[4px]"
            style={{ border: '1px solid rgba(15, 0, 0, 0.12)' }}
          >
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="bg-[#f8f7f7]">
                  {batchMode && activeTab !== 'preset' && (
                    <th className="px-4 py-2.5" style={{ borderBottom: '1px solid rgba(15, 0, 0, 0.12)', width: 40 }} />
                  )}
                  <th className="px-4 py-2.5 text-left text-xs font-medium text-[#646262]" style={{ borderBottom: '1px solid rgba(15, 0, 0, 0.12)' }}>
                    名称
                  </th>
                  <th className="px-4 py-2.5 text-left text-xs font-medium text-[#646262]" style={{ borderBottom: '1px solid rgba(15, 0, 0, 0.12)' }}>
                    描述
                  </th>
                  {activeTab === 'preset' && (
                    <th className="px-4 py-2.5 text-left text-xs font-medium text-[#646262]" style={{ borderBottom: '1px solid rgba(15, 0, 0, 0.12)', width: 80 }}>
                      节点数
                    </th>
                  )}
                  <th className="px-4 py-2.5 text-left text-xs font-medium text-[#646262]" style={{ borderBottom: '1px solid rgba(15, 0, 0, 0.12)', width: 120 }}>
                    更新时间
                  </th>
                  <th className="px-4 py-2.5 text-right text-xs font-medium text-[#646262]" style={{ borderBottom: '1px solid rgba(15, 0, 0, 0.12)', width: 140 }}>
                    操作
                  </th>
                </tr>
              </thead>
              <tbody>
                {workflows.map(wf => (
                  <tr
                    key={wf.id}
                    className="cursor-pointer transition-colors hover:bg-[#f1eeee]"
                    onClick={() => {
                      if (batchMode && activeTab !== 'preset') {
                        toggleSelect(wf.id);
                      } else if (activeTab === 'preset') {
                        handleCreateFromTemplate(wf.id);
                      } else {
                        navigate(`/workflow/${wf.id}`);
                      }
                    }}
                  >
                    {/* 批量选择 */}
                    {batchMode && activeTab !== 'preset' && (
                      <td className="px-4 py-3" style={{ borderBottom: '1px solid rgba(15, 0, 0, 0.08)' }}>
                        {selected.has(wf.id)
                          ? <CheckSquare size={15} className="text-[#201d1d]" />
                          : <Square size={15} className="text-[#9a9898]" />}
                      </td>
                    )}
                    {/* 名称 */}
                    <td className="px-4 py-3 text-[#201d1d] font-medium" style={{ borderBottom: '1px solid rgba(15, 0, 0, 0.08)' }}>
                      <div className="flex items-center gap-2">
                        {wf.is_favorite && (
                          <Star size={12} className="fill-[#ff9f0a] text-[#ff9f0a] flex-shrink-0" />
                        )}
                        <span className="truncate">{wf.name}</span>
                      </div>
                    </td>
                    {/* 描述 */}
                    <td className="px-4 py-3 text-[#646262] text-xs" style={{ borderBottom: '1px solid rgba(15, 0, 0, 0.08)' }}>
                      <div className="truncate max-w-[280px]">
                        {wf.description || '—'}
                      </div>
                    </td>
                    {/* 节点数 (preset only) */}
                    {activeTab === 'preset' && (
                      <td className="px-4 py-3 text-[#646262] text-xs" style={{ borderBottom: '1px solid rgba(15, 0, 0, 0.08)' }}>
                        <Badge variant="default">
                          {'node_count' in wf ? (wf as any).node_count ?? 0 : (wf as any).nodes?.length ?? 0}
                        </Badge>
                      </td>
                    )}
                    {/* 更新时间 */}
                    <td className="px-4 py-3 text-[#646262] text-xs" style={{ borderBottom: '1px solid rgba(15, 0, 0, 0.08)' }}>
                      {wf.updated_at ? formatTime(wf.updated_at) : '—'}
                    </td>
                    {/* 操作 */}
                    <td className="px-4 py-3 text-right" style={{ borderBottom: '1px solid rgba(15, 0, 0, 0.08)' }}>
                      <div className="flex items-center justify-end gap-1">
                        {activeTab !== 'preset' && (
                          <>
                            {/* 查看 */}
                            <button
                              onClick={(e) => { e.stopPropagation(); navigate(`/workflow/${wf.id}`); }}
                              className="rounded-[4px] p-1.5 text-[#646262] transition-colors hover:bg-[#f1eeee] hover:text-[#201d1d]"
                              title="查看"
                            >
                              <Eye size={14} />
                            </button>
                            {/* 收藏 */}
                            <button
                              onClick={(e) => handleToggleFavorite(wf.id, e)}
                              className={`rounded-[4px] p-1.5 transition-colors ${
                                wf.is_favorite
                                  ? 'text-[#ff9f0a] hover:bg-[#ff9f0a]/10'
                                  : 'text-[#646262] hover:bg-[#f1eeee] hover:text-[#ff9f0a]'
                              }`}
                              title={wf.is_favorite ? '取消收藏' : '收藏'}
                            >
                              <Star size={14} className={wf.is_favorite ? 'fill-current' : ''} />
                            </button>
                            {/* 删除 */}
                            <button
                              onClick={(e) => handleDelete(wf.id, e)}
                              className="rounded-[4px] p-1.5 text-[#646262] transition-colors hover:bg-[#f1eeee] hover:text-[#ff3b30]"
                              title="删除"
                            >
                              <Trash2 size={14} />
                            </button>
                          </>
                        )}
                        {activeTab === 'preset' && (
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={(e) => { e.stopPropagation(); handleCreateFromTemplate(wf.id); }}
                            className="flex items-center gap-1 text-xs"
                          >
                            <Copy size={12} />
                            使用
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* 删除确认对话框 */}
      <ConfirmDialog
        open={!!deleteConfirm}
        title="[-] 删除工作流"
        message="确定要删除这个工作流吗？此操作不可撤销。"
        confirmText="删除"
        cancelText="取消"
        variant="danger"
        onConfirm={handleDeleteConfirm}
        onCancel={() => setDeleteConfirm(null)}
      />

      {/* 批量删除确认 */}
      <ConfirmDialog
        open={batchDeleteConfirm}
        title="[-] 批量删除工作流"
        message={`确定要删除选中的 ${selected.size} 个工作流吗？此操作不可撤销。`}
        confirmText="删除"
        cancelText="取消"
        variant="danger"
        onConfirm={handleBatchDelete}
        onCancel={() => setBatchDeleteConfirm(false)}
      />

      {/* 创建工作流模态框 */}
      <Dialog
        open={showCreateDialog}
        onClose={() => setShowCreateDialog(false)}
        title="[+] 创建工作流"
        className="w-[520px]"
      >
        <div className="space-y-4">
          {/* 创建空白工作流 */}
          <div
            className="cursor-pointer rounded-[4px] p-4 transition-colors hover:bg-[#f8f7f7]"
            style={{ border: '1px solid rgba(15, 0, 0, 0.12)' }}
            onClick={handleCreateNew}
          >
            <div className="flex items-center gap-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-[4px] bg-[#f1eeee]">
                <Plus size={16} className="text-[#201d1d]" />
              </div>
              <div>
                <div className="text-sm font-medium text-[#201d1d]">空白工作流</div>
                <div className="text-xs text-[#646262]">从零开始创建一个新工作流</div>
              </div>
            </div>
          </div>

          {/* 分隔线 */}
          <div className="text-xs font-medium text-[#646262]">从模板创建</div>

          {/* 模板列表 */}
          <div className="space-y-2 max-h-[320px] overflow-y-auto">
            {templates && templates.length > 0 ? (
              templates.map(t => (
                <div
                  key={t.id}
                  className="cursor-pointer rounded-[4px] p-3 transition-colors hover:bg-[#f8f7f7]"
                  style={{ border: '1px solid rgba(15, 0, 0, 0.12)' }}
                  onClick={() => handleCreateFromTemplate(t.id)}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-[#201d1d]">{t.name}</div>
                      <div className="mt-1 text-xs text-[#646262] line-clamp-2">
                        {t.description || '暂无描述'}
                      </div>
                    </div>
                    <Badge variant="default" className="ml-2 flex-shrink-0">
                      {t.nodes?.length ?? 0} 节点
                    </Badge>
                  </div>
                </div>
              ))
            ) : (
              <div className="py-4 text-center text-xs text-[#9a9898]">
                暂无可用模板
              </div>
            )}
          </div>
        </div>
      </Dialog>
    </div>
  );
}
