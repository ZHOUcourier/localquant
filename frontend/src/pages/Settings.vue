<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { Save, Check, RefreshCw, Info } from 'lucide-vue-next'
import { Card, Input, Button, Badge, Select } from '@/components/ui'
import type { SelectOption } from '@/components/ui'

interface ConfigData {
  qmt_path: string
  qmt_data_dir: string
  openai_api_key_masked: string
  openai_api_key_set: boolean
  openai_base_url: string
  ai_provider: string
  ai_model: string
  ai_effort: string
  ai_engine: string
  ai_cli: string
  ai_cli_model: string
  ai_cli_effort: string
  factor_service_url: string
  backend_port: number
  frontend_port: number
  data_dir: string
  cache_dir: string
  database_url: string
  version: string
}

interface DataStatus {
  qmt_connected?: boolean
  cache_count?: number
  cache_size?: string
  total_records?: number
  [key: string]: unknown
}

interface ProviderInfo {
  id: string
  label: string
  base_url: string
  model: string
  models: string[]
  byok: boolean
}
interface CliInfo {
  id: string
  label: string
  bin: string
  available: boolean
  models: string[]
  supports_model: boolean
  supports_effort: boolean
}

const queryClient = useQueryClient()

// 推理强度选项（对齐 reasoning_effort）
const EFFORT_LEVELS = [
  { k: 'minimal', label: '极简', desc: '最快、最省，适合简单任务' },
  { k: 'low', label: '低', desc: '较快，轻量推理' },
  { k: 'medium', label: '中（默认）', desc: '平衡速度与质量' },
  { k: 'high', label: '高', desc: '最强推理，较慢、消耗更多' },
]

const form = reactive({
  qmt_path: '',
  qmt_data_dir: '',
  openai_api_key: '', // 留空表示不修改
  openai_base_url: '',
  ai_provider: 'opencode-zen',
  ai_model: '',
  ai_effort: 'medium',
  ai_engine: 'api',
  ai_cli: 'claude',
  ai_cli_model: '',
  ai_cli_effort: 'default',
  factor_service_url: '',
  backend_port: 8000,
  frontend_port: 5173,
})

const { data: config, isLoading } = useQuery<ConfigData>({
  queryKey: ['config'],
  queryFn: () => fetch('/api/config/').then((r) => r.json()),
})

const { data: dataStatus } = useQuery<DataStatus>({
  queryKey: ['data-status'],
  queryFn: () => fetch('/api/data/status').then((r) => r.json()),
})

// 供应商/本机 CLI 清单由后端统一下发（对齐 models.dev，与 QUBE 共用同一注册表）
const { data: providerData } = useQuery<{ providers: ProviderInfo[] }>({
  queryKey: ['ai-providers'],
  queryFn: () => fetch('/api/ai/providers').then((r) => r.json()),
})
const { data: cliData } = useQuery<{ tools: CliInfo[] }>({
  queryKey: ['ai-cli-tools'],
  queryFn: () => fetch('/api/ai/cli-tools').then((r) => r.json()),
})
const providers = computed(() => providerData.value?.providers ?? [])
const cliTools = computed(() => cliData.value?.tools ?? [])
const selectedProvider = computed(() => providers.value.find((p) => p.id === form.ai_provider))
const selectedCli = computed(() => cliTools.value.find((t) => t.id === form.ai_cli))
// CLI 强度（多一个“CLI 默认”）
const CLI_EFFORT_LEVELS = [
  { k: 'default', label: 'CLI 默认' },
  { k: 'minimal', label: '极简' },
  { k: 'low', label: '低' },
  { k: 'medium', label: '中' },
  { k: 'high', label: '高' },
]
// 预置供应商的模型下拉选项（BYOK 无清单，降级手输）
const modelOptions = computed<SelectOption[]>(() =>
  (selectedProvider.value?.models ?? []).map((m) => ({ value: m, label: m })),
)

watch(config, (c) => {
  if (!c) return
  form.qmt_path = c.qmt_path ?? ''
  form.qmt_data_dir = c.qmt_data_dir ?? ''
  form.openai_base_url = c.openai_base_url ?? ''
  form.ai_provider = c.ai_provider ?? 'opencode-zen'
  form.ai_model = c.ai_model ?? ''
  form.ai_effort = c.ai_effort ?? 'medium'
  form.ai_engine = c.ai_engine ?? 'api'
  form.ai_cli = c.ai_cli ?? 'claude'
  form.ai_cli_model = c.ai_cli_model ?? ''
  form.ai_cli_effort = c.ai_cli_effort ?? 'default'
  form.factor_service_url = c.factor_service_url ?? ''
  form.backend_port = c.backend_port ?? 8000
  form.frontend_port = c.frontend_port ?? 5173
})

const saveMutation = useMutation({
  mutationFn: async () => {
    // API Key 输入框留空时不覆盖已有配置
    const body: Record<string, unknown> = {
      qmt_path: form.qmt_path,
      qmt_data_dir: form.qmt_data_dir,
      openai_base_url: form.openai_base_url,
      ai_provider: form.ai_provider,
      ai_model: form.ai_model,
      ai_effort: form.ai_effort,
      ai_engine: form.ai_engine,
      ai_cli: form.ai_cli,
      ai_cli_model: form.ai_cli_model,
      ai_cli_effort: form.ai_cli_effort,
      factor_service_url: form.factor_service_url,
      backend_port: Number(form.backend_port),
      frontend_port: Number(form.frontend_port),
    }
    if (form.openai_api_key) {
      body.openai_api_key = form.openai_api_key
    }
    const res = await fetch('/api/config/', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) {
      const data = await res.json().catch(() => null)
      throw new Error(data?.detail ?? `保存失败 (HTTP ${res.status})`)
    }
    return res.json()
  },
  onSuccess: () => {
    form.openai_api_key = ''
    queryClient.invalidateQueries({ queryKey: ['config'] })
  },
})

// 表单编辑时重置保存状态
watch(form, () => saveMutation.reset())

// 切换供应商：预置免填 Base URL（后端自带），仅 BYOK 需要自填
function selectProvider(p: ProviderInfo) {
  form.ai_provider = p.id
  form.ai_model = p.model || form.ai_model
  if (!p.byok) form.openai_base_url = ''
  saveMutation.reset()
}
</script>

<template>
  <div>
    <div class="mb-4">
      <h1 class="text-xl font-semibold text-[#201d1d] mb-1">设置</h1>
      <p class="text-[13px] text-[#646262]">
        配置持久化到项目根目录 .env 文件，端口类修改需重启后端生效
      </p>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <!-- QMT 配置 -->
      <Card title="QMT 配置">
        <div class="space-y-3">
          <div>
            <label class="block text-xs text-[#646262] mb-1">MiniQMT 路径</label>
            <Input v-model="form.qmt_path" placeholder="如: D:/国金QMT/userdata_mini" />
          </div>
          <div>
            <label class="block text-xs text-[#646262] mb-1">数据目录</label>
            <Input v-model="form.qmt_data_dir" placeholder="如: D:/国金QMT/userdata_mini" />
          </div>
          <div class="flex items-center gap-2 pt-1">
            <span
              class="inline-block h-2 w-2 rounded-full"
              :class="dataStatus?.qmt_connected ? 'bg-[#30d158]' : 'bg-[#ff3b30]'"
            />
            <span class="text-xs text-[#646262]">
              QMT {{ dataStatus?.qmt_connected ? '已连接' : '未连接' }}
            </span>
          </div>
        </div>
      </Card>

      <!-- AI 配置 -->
      <Card title="AI 配置">
        <div class="space-y-3">
          <div>
            <label class="block text-xs text-[#646262] mb-1">接入方式</label>
            <div class="flex gap-1.5">
              <button
                v-for="e in [{ k: 'api', l: 'API 供应商' }, { k: 'cli', l: '本机 CLI 工具' }]"
                :key="e.k"
                type="button"
                class="rounded-[4px] px-3 py-1 text-xs transition-colors cursor-pointer"
                :class="
                  form.ai_engine === e.k
                    ? 'bg-[#201d1d] text-[#fdfcfc]'
                    : 'bg-[#f1eeee] text-[#646262] hover:text-[#201d1d]'
                "
                @click="form.ai_engine = e.k"
              >
                {{ e.l }}
              </button>
            </div>
          </div>

          <!-- API 供应商模式 -->
          <template v-if="form.ai_engine === 'api'">
            <div>
              <label class="block text-xs text-[#646262] mb-1">
                供应商（预置免填 Base URL，仅自定义 BYOK 需自填）
              </label>
              <div class="flex flex-wrap gap-1.5">
                <button
                  v-for="p in providers"
                  :key="p.id"
                  type="button"
                  class="rounded-[4px] px-2.5 py-1 text-xs transition-colors cursor-pointer"
                  :class="
                    form.ai_provider === p.id
                      ? 'bg-[#201d1d] text-[#fdfcfc]'
                      : 'bg-[#f1eeee] text-[#646262] hover:text-[#201d1d]'
                  "
                  @click="selectProvider(p)"
                >
                  {{ p.label }}
                </button>
              </div>
            </div>
            <div>
              <label class="block text-xs text-[#646262] mb-1">
                API Key
                <span v-if="config?.openai_api_key_set" class="ml-2 font-mono text-[#30d158]">
                  已配置 ({{ config.openai_api_key_masked }})
                </span>
              </label>
              <Input
                v-model="form.openai_api_key"
                type="password"
                :placeholder="config?.openai_api_key_set ? '留空则保持不变' : 'sk-...'"
              />
            </div>
            <div class="grid gap-3" :class="selectedProvider?.byok ? 'grid-cols-2' : 'grid-cols-1'">
              <div v-if="selectedProvider?.byok">
                <label class="block text-xs text-[#646262] mb-1">Base URL（BYOK）</label>
                <Input v-model="form.openai_base_url" placeholder="如: https://your-endpoint/v1" />
              </div>
              <div>
                <label class="block text-xs text-[#646262] mb-1">模型</label>
                <!-- 预置供应商：清单下拉选择；BYOK 手输 -->
                <Select
                  v-if="modelOptions.length"
                  v-model="form.ai_model"
                  :options="modelOptions"
                  placeholder="选择模型"
                />
                <Input v-else v-model="form.ai_model" :placeholder="selectedProvider?.model || '模型名称'" />
              </div>
            </div>
            <div>
              <label class="block text-xs text-[#646262] mb-1">推理强度</label>
              <div class="flex gap-1.5">
                <button
                  v-for="lv in EFFORT_LEVELS"
                  :key="lv.k"
                  type="button"
                  class="rounded-[4px] px-2.5 py-1 text-xs transition-colors cursor-pointer"
                  :class="form.ai_effort === lv.k ? 'bg-[#201d1d] text-[#fdfcfc]' : 'bg-[#f1eeee] text-[#646262] hover:text-[#201d1d]'"
                  :title="lv.desc"
                  @click="form.ai_effort = lv.k"
                >
                  {{ lv.label }}
                </button>
              </div>
              <div class="mt-1 text-[10px] text-[#9a9898]">仅支持 reasoning_effort 的推理模型生效（如 GPT-5 / GLM 系）；其余模型自动忽略。</div>
            </div>
          </template>

          <!-- 本机 CLI 模式 -->
          <template v-else>
            <div>
              <label class="block text-xs text-[#646262] mb-1">CLI 工具（使用你本机已登录的 CLI，无需 API Key）</label>
              <div class="flex flex-wrap gap-1.5">
                <button
                  v-for="t in cliTools"
                  :key="t.id"
                  type="button"
                  class="flex items-center gap-1.5 rounded-[4px] px-2.5 py-1 text-xs transition-colors cursor-pointer"
                  :class="
                    form.ai_cli === t.id
                      ? 'bg-[#201d1d] text-[#fdfcfc]'
                      : 'bg-[#f1eeee] text-[#646262] hover:text-[#201d1d]'
                  "
                  :title="t.available ? `本机可用 (${t.bin})` : `未检测到 ${t.bin}，请先安装`"
                  @click="form.ai_cli = t.id"
                >
                  <span :class="!t.available && form.ai_cli !== t.id ? 'opacity-45' : ''">{{ t.label }}</span>
                  <span
                    class="inline-block h-1.5 w-1.5 rounded-full"
                    :class="t.available ? 'bg-[#30d158]' : 'bg-[#c8c4c4]'"
                  />
                </button>
              </div>
            </div>

            <!-- CLI 模型（建议芯片 + 自由输入；留空=CLI 默认） -->
            <div v-if="selectedCli?.supports_model">
              <label class="block text-xs text-[#646262] mb-1">CLI 模型（留空 = 用 CLI 自身默认）</label>
              <div v-if="selectedCli?.models?.length" class="mb-1.5 flex flex-wrap gap-1.5">
                <button
                  v-for="m in selectedCli.models"
                  :key="m"
                  type="button"
                  class="rounded-[4px] px-2 py-0.5 text-[11px] cursor-pointer"
                  :class="form.ai_cli_model === m ? 'bg-[#201d1d] text-[#fdfcfc]' : 'bg-[#f1eeee] text-[#646262] hover:text-[#201d1d]'"
                  @click="form.ai_cli_model = m"
                >
                  {{ m }}
                </button>
              </div>
              <Input v-model="form.ai_cli_model" placeholder="模型名（可自由输入，留空用默认）" />
            </div>

            <!-- CLI 推理强度（仅支持的工具显示） -->
            <div v-if="selectedCli?.supports_effort">
              <label class="block text-xs text-[#646262] mb-1">推理强度</label>
              <div class="flex flex-wrap gap-1.5">
                <button
                  v-for="lv in CLI_EFFORT_LEVELS"
                  :key="lv.k"
                  type="button"
                  class="rounded-[4px] px-3 py-1 text-xs cursor-pointer"
                  :class="form.ai_cli_effort === lv.k ? 'bg-[#201d1d] text-[#fdfcfc]' : 'bg-[#f1eeee] text-[#646262] hover:text-[#201d1d]'"
                  @click="form.ai_cli_effort = lv.k"
                >
                  {{ lv.label }}
                </button>
              </div>
              <div class="mt-1 text-[10px] text-[#9a9898]">选“CLI 默认”则不传强度参数；具体档位是否生效取决于所选模型/供应商。</div>
            </div>
          </template>

          <div class="flex items-start gap-1.5 pt-1">
            <Info :size="13" class="mt-0.5 shrink-0 text-[#9a9898]" />
            <span class="text-xs text-[#9a9898]">
              用于工作流 AI 生成、节点代码 AI 改写、因子/数据探索等场景；QUBE Agent 的 AI 配置在 QUBE 页面内单独设置，互不影响
            </span>
          </div>
        </div>
      </Card>

      <!-- 服务配置 -->
      <Card title="服务配置">
        <div class="space-y-3">
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-xs text-[#646262] mb-1">后端端口</label>
              <Input :model-value="String(form.backend_port)" type="number" @update:model-value="(v: string) => (form.backend_port = Number(v))" />
            </div>
            <div>
              <label class="block text-xs text-[#646262] mb-1">前端端口</label>
              <Input :model-value="String(form.frontend_port)" type="number" @update:model-value="(v: string) => (form.frontend_port = Number(v))" />
            </div>
          </div>
          <div>
            <label class="block text-xs text-[#646262] mb-1">因子研究服务地址</label>
            <Input v-model="form.factor_service_url" placeholder="如: http://localhost:8001" />
          </div>
          <div class="flex items-start gap-1.5 pt-1">
            <Info :size="13" class="mt-0.5 shrink-0 text-[#9a9898]" />
            <span class="text-xs text-[#9a9898]">端口修改后需重启 make dev 生效</span>
          </div>
        </div>
      </Card>

      <!-- 数据与存储 -->
      <Card title="数据与存储">
        <div class="space-y-2">
          <div class="flex items-center justify-between text-xs">
            <span class="text-[#646262]">数据目录</span>
            <span class="font-mono text-[#201d1d]">{{ config?.data_dir ?? '-' }}</span>
          </div>
          <div class="flex items-center justify-between text-xs">
            <span class="text-[#646262]">缓存目录</span>
            <span class="font-mono text-[#201d1d]">{{ config?.cache_dir ?? '-' }}</span>
          </div>
          <div class="flex items-center justify-between text-xs">
            <span class="text-[#646262]">数据库</span>
            <span class="font-mono text-[#201d1d] truncate max-w-[220px]">{{ config?.database_url ?? '-' }}</span>
          </div>
          <div class="flex items-center justify-between text-xs">
            <span class="text-[#646262]">已缓存品种</span>
            <span class="font-mono text-[#007aff]">{{ dataStatus?.cache_count ?? 0 }}</span>
          </div>
          <div class="flex items-center justify-between text-xs">
            <span class="text-[#646262]">磁盘占用</span>
            <span class="font-mono text-[#007aff]">{{ dataStatus?.cache_size ?? '0 MB' }}</span>
          </div>
        </div>
      </Card>

      <!-- 关于 -->
      <Card title="关于">
        <div class="space-y-2">
          <div class="flex items-center justify-between text-xs">
            <span class="text-[#646262]">应用</span>
            <span class="font-mono text-[#201d1d]">LocalQuant 本地投研工作站</span>
          </div>
          <div class="flex items-center justify-between text-xs">
            <span class="text-[#646262]">版本</span>
            <span class="font-mono text-[#201d1d]">v{{ config?.version ?? '-' }}</span>
          </div>
          <div class="flex items-center justify-between text-xs">
            <span class="text-[#646262]">后端地址</span>
            <span class="font-mono text-[#201d1d]">http://localhost:{{ config?.backend_port ?? 8000 }}</span>
          </div>
          <div class="flex items-center justify-between text-xs">
            <span class="text-[#646262]">API 文档</span>
            <a
              :href="`http://localhost:${config?.backend_port ?? 8000}/docs`"
              target="_blank"
              rel="noreferrer"
              class="font-mono text-[#007aff] hover:underline"
            >
              /docs
            </a>
          </div>
        </div>
      </Card>
    </div>

    <!-- 保存按钮 -->
    <div class="mt-4 flex items-center gap-3">
      <Button
        variant="primary"
        :loading="saveMutation.isPending.value"
        :disabled="isLoading"
        @click="saveMutation.mutate()"
      >
        <Check v-if="saveMutation.isSuccess.value" :size="14" class="mr-1" />
        <Save v-else :size="14" class="mr-1" />
        {{ saveMutation.isSuccess.value ? '已保存' : '保存' }}
      </Button>
      <Button variant="secondary" @click="queryClient.invalidateQueries({ queryKey: ['config'] })">
        <RefreshCw :size="14" class="mr-1" />
        重新加载
      </Button>
      <Badge v-if="saveMutation.isSuccess.value" variant="success">已写入 .env</Badge>
      <span v-if="saveMutation.isError.value" class="font-mono text-xs text-[#ff3b30]">
        {{ saveMutation.error.value instanceof Error ? saveMutation.error.value.message : '保存失败' }}
      </span>
    </div>
  </div>
</template>
