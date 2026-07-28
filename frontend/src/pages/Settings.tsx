import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Save, Check, RefreshCw, Info } from 'lucide-react';
import { Card, Input, Button, Badge } from '@/components/ui';

interface ConfigData {
  qmt_path: string;
  qmt_data_dir: string;
  openai_api_key_masked: string;
  openai_api_key_set: boolean;
  openai_base_url: string;
  ai_provider: string;
  ai_model: string;
  factor_service_url: string;
  backend_port: number;
  frontend_port: number;
  data_dir: string;
  cache_dir: string;
  database_url: string;
  version: string;
}

interface DataStatus {
  qmt_connected?: boolean;
  cache_count?: number;
  cache_size?: string;
  total_records?: number;
  [key: string]: unknown;
}

// 主流厂商预置（均为 OpenAI 兼容接口）；选择后自动填入 Base URL 与默认模型
const AI_PROVIDERS: { key: string; label: string; baseUrl: string; model: string }[] = [
  { key: 'openai', label: 'OpenAI', baseUrl: 'https://api.openai.com/v1', model: 'gpt-4o-mini' },
  { key: 'deepseek', label: 'DeepSeek', baseUrl: 'https://api.deepseek.com/v1', model: 'deepseek-chat' },
  { key: 'moonshot', label: '月之暗面 Kimi', baseUrl: 'https://api.moonshot.cn/v1', model: 'moonshot-v1-8k' },
  { key: 'qwen', label: '通义千问', baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-plus' },
  { key: 'zhipu', label: '智谱 GLM', baseUrl: 'https://open.bigmodel.cn/api/paas/v4', model: 'glm-4-flash' },
  { key: 'custom', label: '自定义', baseUrl: '', model: '' },
];

export default function Settings() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    qmt_path: '',
    qmt_data_dir: '',
    openai_api_key: '', // 留空表示不修改
    openai_base_url: '',
    ai_provider: 'openai',
    ai_model: '',
    factor_service_url: '',
    backend_port: 8000,
    frontend_port: 5173,
  });

  const { data: config, isLoading } = useQuery<ConfigData>({
    queryKey: ['config'],
    queryFn: () => fetch('/api/config/').then(r => r.json()),
  });

  const { data: dataStatus } = useQuery<DataStatus>({
    queryKey: ['data-status'],
    queryFn: () => fetch('/api/data/status').then(r => r.json()),
  });

  useEffect(() => {
    if (config) {
      setForm(prev => ({
        ...prev,
        qmt_path: config.qmt_path ?? '',
        qmt_data_dir: config.qmt_data_dir ?? '',
        openai_base_url: config.openai_base_url ?? '',
        ai_provider: config.ai_provider ?? 'openai',
        ai_model: config.ai_model ?? '',
        factor_service_url: config.factor_service_url ?? '',
        backend_port: config.backend_port ?? 8000,
        frontend_port: config.frontend_port ?? 5173,
      }));
    }
  }, [config]);

  const saveMutation = useMutation({
    mutationFn: async () => {
      // API Key 输入框留空时不覆盖已有配置
      const body: Record<string, unknown> = {
        qmt_path: form.qmt_path,
        qmt_data_dir: form.qmt_data_dir,
        openai_base_url: form.openai_base_url,
        ai_provider: form.ai_provider,
        ai_model: form.ai_model,
        factor_service_url: form.factor_service_url,
        backend_port: form.backend_port,
        frontend_port: form.frontend_port,
      };
      if (form.openai_api_key) {
        body.openai_api_key = form.openai_api_key;
      }
      const res = await fetch('/api/config/', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        throw new Error(data?.detail ?? `保存失败 (HTTP ${res.status})`);
      }
      return res.json();
    },
    onSuccess: () => {
      setForm(prev => ({ ...prev, openai_api_key: '' }));
      queryClient.invalidateQueries({ queryKey: ['config'] });
    },
  });

  const updateField = (key: string, value: string | number) => {
    setForm(prev => ({ ...prev, [key]: value }));
    saveMutation.reset();
  };

  // 切换厂商预置：自动填入对应 Base URL 与默认模型
  const selectProvider = (key: string) => {
    const preset = AI_PROVIDERS.find(p => p.key === key);
    setForm(prev => ({
      ...prev,
      ai_provider: key,
      openai_base_url: preset?.baseUrl ?? prev.openai_base_url,
      ai_model: preset?.model ?? prev.ai_model,
    }));
    saveMutation.reset();
  };

  return (
    <div>
      <div className="mb-4">
        <h1 className="text-xl font-semibold text-[#201d1d] mb-1">设置</h1>
        <p className="text-[13px] text-[#646262]">
          配置持久化到项目根目录 .env 文件，端口类修改需重启后端生效
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* QMT 配置 */}
        <Card title="QMT 配置">
          <div className="space-y-3">
            <div>
              <label className="block text-xs text-[#646262] mb-1">MiniQMT 路径</label>
              <Input
                value={form.qmt_path}
                onChange={e => updateField('qmt_path', e.target.value)}
                placeholder="如: D:/国金QMT/userdata_mini"
              />
            </div>
            <div>
              <label className="block text-xs text-[#646262] mb-1">数据目录</label>
              <Input
                value={form.qmt_data_dir}
                onChange={e => updateField('qmt_data_dir', e.target.value)}
                placeholder="如: D:/国金QMT/userdata_mini"
              />
            </div>
            <div className="flex items-center gap-2 pt-1">
              <span
                className={`inline-block h-2 w-2 rounded-full ${dataStatus?.qmt_connected ? 'bg-[#30d158]' : 'bg-[#ff3b30]'}`}
              />
              <span className="text-xs text-[#646262]">
                QMT {dataStatus?.qmt_connected ? '已连接' : '未连接'}
              </span>
            </div>
          </div>
        </Card>

        {/* AI 配置 */}
        <Card title="AI 配置">
          <div className="space-y-3">
            <div>
              <label className="block text-xs text-[#646262] mb-1">服务商</label>
              <div className="flex flex-wrap gap-1.5">
                {AI_PROVIDERS.map(p => (
                  <button
                    key={p.key}
                    type="button"
                    onClick={() => selectProvider(p.key)}
                    className={`rounded-[4px] px-2.5 py-1 text-xs transition-colors cursor-pointer ${
                      form.ai_provider === p.key
                        ? 'bg-[#201d1d] text-[#fdfcfc]'
                        : 'bg-[#f1eeee] text-[#646262] hover:text-[#201d1d]'
                    }`}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="block text-xs text-[#646262] mb-1">
                API Key
                {config?.openai_api_key_set && (
                  <span className="ml-2 font-mono text-[#30d158]">
                    已配置 ({config.openai_api_key_masked})
                  </span>
                )}
              </label>
              <Input
                type="password"
                value={form.openai_api_key}
                onChange={e => updateField('openai_api_key', e.target.value)}
                placeholder={config?.openai_api_key_set ? '留空则保持不变' : 'sk-...'}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-[#646262] mb-1">Base URL</label>
                <Input
                  value={form.openai_base_url}
                  onChange={e => updateField('openai_base_url', e.target.value)}
                  placeholder="如: https://api.openai.com/v1"
                />
              </div>
              <div>
                <label className="block text-xs text-[#646262] mb-1">模型</label>
                <Input
                  value={form.ai_model}
                  onChange={e => updateField('ai_model', e.target.value)}
                  placeholder="如: gpt-4o-mini"
                />
              </div>
            </div>
            <div className="flex items-start gap-1.5 pt-1">
              <Info size={13} className="mt-0.5 shrink-0 text-[#9a9898]" />
              <span className="text-xs text-[#9a9898]">
                用于工作流编辑器的“AI 生成工作流”与节点代码 AI 修改；均走 OpenAI 兼容接口，自建服务选“自定义”并填入地址
              </span>
            </div>
          </div>
        </Card>

        {/* 服务配置 */}
        <Card title="服务配置">
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-[#646262] mb-1">后端端口</label>
                <Input
                  type="number"
                  value={form.backend_port}
                  onChange={e => updateField('backend_port', Number(e.target.value))}
                />
              </div>
              <div>
                <label className="block text-xs text-[#646262] mb-1">前端端口</label>
                <Input
                  type="number"
                  value={form.frontend_port}
                  onChange={e => updateField('frontend_port', Number(e.target.value))}
                />
              </div>
            </div>
            <div>
              <label className="block text-xs text-[#646262] mb-1">因子研究服务地址</label>
              <Input
                value={form.factor_service_url}
                onChange={e => updateField('factor_service_url', e.target.value)}
                placeholder="如: http://localhost:8001"
              />
            </div>
            <div className="flex items-start gap-1.5 pt-1">
              <Info size={13} className="mt-0.5 shrink-0 text-[#9a9898]" />
              <span className="text-xs text-[#9a9898]">端口修改后需重启 make dev 生效</span>
            </div>
          </div>
        </Card>

        {/* 数据与存储 */}
        <Card title="数据与存储">
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="text-[#646262]">数据目录</span>
              <span className="font-mono text-[#201d1d]">{config?.data_dir ?? '-'}</span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-[#646262]">缓存目录</span>
              <span className="font-mono text-[#201d1d]">{config?.cache_dir ?? '-'}</span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-[#646262]">数据库</span>
              <span className="font-mono text-[#201d1d] truncate max-w-[220px]">{config?.database_url ?? '-'}</span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-[#646262]">已缓存品种</span>
              <span className="font-mono text-[#007aff]">{dataStatus?.cache_count ?? 0}</span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-[#646262]">磁盘占用</span>
              <span className="font-mono text-[#007aff]">{dataStatus?.cache_size ?? '0 MB'}</span>
            </div>
          </div>
        </Card>

        {/* 关于 */}
        <Card title="关于">
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="text-[#646262]">应用</span>
              <span className="font-mono text-[#201d1d]">LocalQuant 本地投研工作站</span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-[#646262]">版本</span>
              <span className="font-mono text-[#201d1d]">v{config?.version ?? '-'}</span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-[#646262]">后端地址</span>
              <span className="font-mono text-[#201d1d]">http://localhost:{config?.backend_port ?? 8000}</span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-[#646262]">API 文档</span>
              <a
                href={`http://localhost:${config?.backend_port ?? 8000}/docs`}
                target="_blank"
                rel="noreferrer"
                className="font-mono text-[#007aff] hover:underline"
              >
                /docs
              </a>
            </div>
          </div>
        </Card>
      </div>

      {/* 保存按钮 */}
      <div className="mt-4 flex items-center gap-3">
        <Button
          variant="primary"
          onClick={() => saveMutation.mutate()}
          loading={saveMutation.isPending}
          disabled={isLoading}
        >
          {saveMutation.isSuccess ? <Check size={14} className="mr-1" /> : <Save size={14} className="mr-1" />}
          {saveMutation.isSuccess ? '已保存' : '保存'}
        </Button>
        <Button
          variant="secondary"
          onClick={() => queryClient.invalidateQueries({ queryKey: ['config'] })}
        >
          <RefreshCw size={14} className="mr-1" />
          重新加载
        </Button>
        {saveMutation.isSuccess && <Badge variant="success">已写入 .env</Badge>}
        {saveMutation.isError && (
          <span className="font-mono text-xs text-[#ff3b30]">
            {saveMutation.error instanceof Error ? saveMutation.error.message : '保存失败'}
          </span>
        )}
      </div>
    </div>
  );
}
