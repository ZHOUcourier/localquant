import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Save, Check } from 'lucide-react';
import { Card, Input, Button, Badge } from '@/components/ui';

interface ConfigData {
  qmt_path?: string;
  qmt_data_dir?: string;
  openai_api_key?: string;
  openai_base_url?: string;
  backend_port?: number;
  frontend_port?: number;
  [key: string]: unknown;
}

export default function Settings() {
  const [form, setForm] = useState({
    qmt_path: '',
    qmt_data_dir: '',
    openai_api_key: '',
    openai_base_url: '',
    backend_port: 8000,
    frontend_port: 5173,
  });
  const [saved, setSaved] = useState(false);

  const { data: currentConfig } = useQuery<ConfigData>({
    queryKey: ['config'],
    queryFn: () => fetch('/api/data/status').then(r => r.json()),
  });

  useEffect(() => {
    if (currentConfig) {
      setForm(prev => ({
        qmt_path: currentConfig.qmt_path ?? prev.qmt_path,
        qmt_data_dir: currentConfig.qmt_data_dir ?? prev.qmt_data_dir,
        openai_api_key: currentConfig.openai_api_key ?? prev.openai_api_key,
        openai_base_url: currentConfig.openai_base_url ?? prev.openai_base_url,
        backend_port: currentConfig.backend_port ?? prev.backend_port,
        frontend_port: currentConfig.frontend_port ?? prev.frontend_port,
      }));
    }
  }, [currentConfig]);

  const handleSave = () => {
    // 保存到 localStorage 作为配置持久化（后端暂无配置写入接口，前端暂存）
    localStorage.setItem('localquant_config', JSON.stringify(form));
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const updateField = (key: string, value: string | number) => {
    setForm(prev => ({ ...prev, [key]: value }));
    setSaved(false);
  };

  return (
    <div>
      <div className="mb-4">
        <h1 className="text-xl font-semibold text-[#fdfcfc] mb-1">设置</h1>
        <p className="text-[13px] text-[#9a9898]">配置 QMT、AI 及服务参数</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* QMT 配置 */}
        <Card title="QMT 配置">
          <div className="space-y-3">
            <div>
              <label className="block text-xs text-[#9a9898] mb-1">MiniQMT 路径</label>
              <Input
                value={form.qmt_path}
                onChange={e => updateField('qmt_path', e.target.value)}
                placeholder="如: D:/国金QMT/userdata_mini"
              />
            </div>
            <div>
              <label className="block text-xs text-[#9a9898] mb-1">数据目录</label>
              <Input
                value={form.qmt_data_dir}
                onChange={e => updateField('qmt_data_dir', e.target.value)}
                placeholder="如: D:/国金QMT/userdata_mini"
              />
            </div>
          </div>
        </Card>

        {/* AI 配置 */}
        <Card title="AI 配置">
          <div className="space-y-3">
            <div>
              <label className="block text-xs text-[#9a9898] mb-1">API Key</label>
              <Input
                type="password"
                value={form.openai_api_key}
                onChange={e => updateField('openai_api_key', e.target.value)}
                placeholder="sk-..."
              />
            </div>
            <div>
              <label className="block text-xs text-[#9a9898] mb-1">Base URL</label>
              <Input
                value={form.openai_base_url}
                onChange={e => updateField('openai_base_url', e.target.value)}
                placeholder="如: https://api.openai.com/v1"
              />
            </div>
          </div>
        </Card>

        {/* 服务配置 */}
        <Card title="服务配置">
          <div className="space-y-3">
            <div>
              <label className="block text-xs text-[#9a9898] mb-1">后端端口</label>
              <Input
                type="number"
                value={form.backend_port}
                onChange={e => updateField('backend_port', Number(e.target.value))}
              />
            </div>
            <div>
              <label className="block text-xs text-[#9a9898] mb-1">前端端口</label>
              <Input
                type="number"
                value={form.frontend_port}
                onChange={e => updateField('frontend_port', Number(e.target.value))}
              />
            </div>
          </div>
        </Card>

        {/* 当前生效配置 */}
        <Card title="当前生效配置">
          <div className="space-y-2">
            {currentConfig ? (
              Object.entries(currentConfig).slice(0, 8).map(([key, value]) => (
                <div key={key} className="flex items-center justify-between text-xs">
                  <span className="text-[#9a9898] font-mono">{key}</span>
                  <span className="text-[#fdfcfc] font-mono truncate max-w-[200px] ml-2">
                    {typeof value === 'string' && value.length > 30
                      ? value.slice(0, 30) + '...'
                      : value !== null && value !== undefined
                      ? String(value)
                      : '-'}
                  </span>
                </div>
              ))
            ) : (
              <p className="text-xs text-[#6e6e73] py-2">加载中...</p>
            )}
          </div>
        </Card>
      </div>

      {/* 保存按钮 */}
      <div className="mt-4 flex items-center gap-3">
        <Button variant="primary" onClick={handleSave}>
          {saved ? <Check size={14} className="mr-1" /> : <Save size={14} className="mr-1" />}
          {saved ? '已保存' : '保存'}
        </Button>
        {saved && <Badge variant="success">配置已保存到本地</Badge>}
      </div>
    </div>
  );
}
