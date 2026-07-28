import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Trash2, FolderOpen, Layout } from 'lucide-react';
import { useWorkflows, useDeleteWorkflow, useWorkflowTemplates, useCreateFromTemplate, useSaveWorkflow } from '../hooks/useWorkflow';

export default function WorkflowList() {
  const navigate = useNavigate();
  const { data: workflows, isLoading } = useWorkflows();
  const deleteMutation = useDeleteWorkflow();
  const { data: templates } = useWorkflowTemplates();
  const createFromTemplate = useCreateFromTemplate();
  const saveWorkflow = useSaveWorkflow();
  const [showTemplateMenu, setShowTemplateMenu] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);

  const handleCreateNew = async () => {
    const result = await saveWorkflow.mutateAsync({
      name: '未命名工作流',
      nodes: [],
      links: [],
    });
    if (result?.id) {
      navigate(`/workflow/${result.id}`);
    }
  };

  const handleCreateFromTemplate = async (templateId: string) => {
    const result = await createFromTemplate.mutateAsync(templateId);
    setShowTemplateMenu(false);
    if (result?.id) {
      navigate(`/workflow/${result.id}`);
    }
  };

  const handleDelete = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (deleteConfirm === id) {
      deleteMutation.mutate(id);
      setDeleteConfirm(null);
    } else {
      setDeleteConfirm(id);
      setTimeout(() => setDeleteConfirm(null), 3000);
    }
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
    <div style={{ padding: '24px 32px', maxWidth: 1200, margin: '0 auto' }}>
      {/* 顶部标题栏 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 28 }}>
        <h1 style={{ color: '#fdfcfc', fontSize: 20, fontWeight: 700, margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
          <Layout size={20} style={{ color: '#007aff' }} />
          工作流
        </h1>
        <div style={{ flex: 1 }} />

        {/* 从模板创建 */}
        <div style={{ position: 'relative' }}>
          <button
            onClick={() => setShowTemplateMenu(!showTemplateMenu)}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '6px 14px', background: '#302c2c', border: '1px solid #403b3b',
              borderRadius: 4, color: '#d4d2d2', fontSize: 13, cursor: 'pointer',
            }}
          >
            <FolderOpen size={14} />
            从模板创建
          </button>
          {showTemplateMenu && templates && templates.length > 0 && (
            <div
              style={{
                position: 'absolute', top: '100%', right: 0, marginTop: 4,
                background: '#262222', border: '1px solid #403b3b', borderRadius: 4,
                minWidth: 220, zIndex: 100, boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
                overflow: 'hidden',
              }}
            >
              {templates.map(t => (
                <button
                  key={t.id}
                  onClick={() => handleCreateFromTemplate(t.id)}
                  style={{
                    display: 'block', width: '100%', padding: '10px 14px',
                    background: 'transparent', border: 'none', borderBottom: '1px solid #302c2c',
                    color: '#d4d2d2', fontSize: 13, textAlign: 'left', cursor: 'pointer',
                  }}
                  onMouseEnter={e => (e.currentTarget.style.background = '#302c2c')}
                  onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                >
                  <div style={{ fontWeight: 500 }}>{t.name}</div>
                  <div style={{ color: '#9a9898', fontSize: 11, marginTop: 2 }}>{t.description}</div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* 新建工作流 */}
        <button
          onClick={handleCreateNew}
          style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '6px 16px', background: '#007aff', border: 'none',
            borderRadius: 4, color: '#201d1d', fontSize: 13, fontWeight: 600, cursor: 'pointer',
          }}
        >
          <Plus size={14} />
          新建工作流
        </button>
      </div>

      {/* 加载中 */}
      {isLoading && (
        <div style={{ color: '#9a9898', fontSize: 13, textAlign: 'center', padding: 60 }}>
          加载中...
        </div>
      )}

      {/* 空状态 */}
      {!isLoading && (!workflows || workflows.length === 0) && (
        <div style={{
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
          padding: '80px 20px', color: '#9a9898',
        }}>
          <Layout size={48} style={{ color: '#403b3b', marginBottom: 16 }} />
          <p style={{ fontSize: 15, marginBottom: 16, color: '#d4d2d2' }}>还没有工作流</p>
          <button
            onClick={handleCreateNew}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '8px 20px', background: '#007aff', border: 'none',
              borderRadius: 4, color: '#201d1d', fontSize: 13, fontWeight: 600, cursor: 'pointer',
            }}
          >
            <Plus size={14} />
            创建第一个工作流
          </button>
        </div>
      )}

      {/* 工作流卡片网格 */}
      {!isLoading && workflows && workflows.length > 0 && (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
          gap: 16,
        }}>
          {workflows.map(wf => (
            <div
              key={wf.id}
              onClick={() => navigate(`/workflow/${wf.id}`)}
              style={{
                background: '#262222',
                border: '1px solid #403b3b',
                borderRadius: 4,
                padding: '18px 20px',
                cursor: 'pointer',
                transition: 'border-color 0.15s ease, transform 0.1s ease',
                position: 'relative',
              }}
              onMouseEnter={e => {
                e.currentTarget.style.borderColor = '#007aff';
                e.currentTarget.style.transform = 'translateY(-1px)';
              }}
              onMouseLeave={e => {
                e.currentTarget.style.borderColor = '#403b3b';
                e.currentTarget.style.transform = 'translateY(0)';
              }}
            >
              {/* 删除按钮 */}
              <button
                onClick={(e) => handleDelete(wf.id, e)}
                title={deleteConfirm === wf.id ? '再次点击确认删除' : '删除'}
                style={{
                  position: 'absolute', top: 12, right: 12,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  width: 28, height: 28,
                  background: deleteConfirm === wf.id ? '#ff3b30' : 'transparent',
                  border: 'none', borderRadius: 4,
                  color: deleteConfirm === wf.id ? '#fff' : '#9a9898',
                  cursor: 'pointer', opacity: 0.7,
                  transition: 'all 0.15s ease',
                }}
                onMouseEnter={e => { e.currentTarget.style.opacity = '1'; e.currentTarget.style.background = deleteConfirm === wf.id ? '#ff3b30' : '#302c2c'; }}
                onMouseLeave={e => { e.currentTarget.style.opacity = '0.7'; e.currentTarget.style.background = deleteConfirm === wf.id ? '#ff3b30' : 'transparent'; }}
              >
                <Trash2 size={14} />
              </button>

              {/* 名称 */}
              <div style={{ color: '#fdfcfc', fontSize: 14, fontWeight: 600, marginBottom: 6, paddingRight: 32 }}>
                {wf.name}
              </div>

              {/* 描述 */}
              <div style={{
                color: '#9a9898', fontSize: 12, marginBottom: 14,
                overflow: 'hidden', textOverflow: 'ellipsis',
                display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
                minHeight: 32, lineHeight: '16px',
              }}>
                {wf.description || '暂无描述'}
              </div>

              {/* 底部信息 */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ color: '#555', fontSize: 11 }}>
                  {formatTime(wf.updated_at)}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
