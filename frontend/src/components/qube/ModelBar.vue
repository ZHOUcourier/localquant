<script setup lang="ts">
/**
 * ModelBar — 输入框下方的模型选择行（引擎 → 供应商/CLI 工具 → 模型 → 推理强度）
 *
 * 全部用现有 UI Select 组件（不自造下拉，无卡顿/闪烁）；改动即写 /api/qube/config。
 * 加载完成（loaded）前不渲染，如实跟随后端实际配置显示（不写死默认 API）。
 */
import { computed, onMounted, ref } from 'vue'
import { Select } from '@/components/ui'
import type { SelectOption } from '@/components/ui'
import { jsonFetch } from './types'

interface ProviderInfo {
  id: string
  label: string
  model: string
  models: string[]
  byok: boolean
}
interface CliInfo {
  id: string
  label: string
  available: boolean
  models: string[]
  supports_model: boolean
  supports_effort: boolean
}

const loaded = ref(false)
const providers = ref<ProviderInfo[]>([])
const cliTools = ref<CliInfo[]>([])
const cfg = ref({
  qube_engine: 'api',
  qube_provider: '',
  qube_model: '',
  qube_effort: 'medium',
  qube_cli: '',
  qube_cli_model: '',
  qube_cli_effort: 'default',
})

const isCli = computed(() => cfg.value.qube_engine === 'cli')
const selectedProvider = computed(() => providers.value.find((p) => p.id === cfg.value.qube_provider))
const selectedCli = computed(() => cliTools.value.find((t) => t.id === cfg.value.qube_cli))

// —— 下拉选项 ————————————————————————————————————————————
const engineOptions: SelectOption[] = [
  { value: 'api', label: 'API 供应商' },
  { value: 'cli', label: '本机 CLI' },
]

const sourceOptions = computed<SelectOption[]>(() =>
  isCli.value
    ? cliTools.value.map((t) => ({
        value: t.id,
        label: t.available ? t.label : `${t.label}（未安装）`,
        disabled: !t.available,
      }))
    : providers.value.map((p) => ({ value: p.id, label: p.label })),
)

const modelOptions = computed<SelectOption[]>(() => {
  if (isCli.value) {
    const list = selectedCli.value?.models ?? []
    // CLI 允许「用 CLI 自身默认」（空值）
    return [{ value: '', label: 'CLI 默认' }, ...list.map((m) => ({ value: m, label: m }))]
  }
  return (selectedProvider.value?.models ?? []).map((m) => ({ value: m, label: m }))
})

const effortOptions = computed<SelectOption[]>(() =>
  isCli.value
    ? [
        { value: 'default', label: 'CLI 默认' },
        { value: 'minimal', label: '极简' },
        { value: 'low', label: '低' },
        { value: 'medium', label: '中' },
        { value: 'high', label: '高' },
      ]
    : [
        { value: 'minimal', label: '极简' },
        { value: 'low', label: '低' },
        { value: 'medium', label: '中' },
        { value: 'high', label: '高' },
      ],
)

// —— v-model 桥接（读当前配置，写即 patch 后端）————————————
const engineModel = computed({
  get: () => cfg.value.qube_engine,
  set: (v: string) => {
    cfg.value.qube_engine = v
    patch({ qube_engine: v })
  },
})
const sourceModel = computed({
  get: () => (isCli.value ? cfg.value.qube_cli : cfg.value.qube_provider),
  set: (v: string) => {
    if (isCli.value) {
      cfg.value.qube_cli = v
      patch({ qube_cli: v })
    } else {
      cfg.value.qube_provider = v
      // 切供应商时把模型重置为该供应商默认，避免残留不匹配的模型名
      const p = providers.value.find((x) => x.id === v)
      cfg.value.qube_model = p?.model || ''
      patch({ qube_provider: v, qube_model: cfg.value.qube_model })
    }
  },
})
const modelModel = computed({
  get: () => (isCli.value ? cfg.value.qube_cli_model : cfg.value.qube_model),
  set: (v: string) => {
    if (isCli.value) {
      cfg.value.qube_cli_model = v
      patch({ qube_cli_model: v })
    } else {
      cfg.value.qube_model = v
      patch({ qube_model: v })
    }
  },
})
const effortModel = computed({
  get: () => (isCli.value ? cfg.value.qube_cli_effort : cfg.value.qube_effort),
  set: (v: string) => {
    if (isCli.value) {
      cfg.value.qube_cli_effort = v
      patch({ qube_cli_effort: v })
    } else {
      cfg.value.qube_effort = v
      patch({ qube_effort: v })
    }
  },
})

// CLI 模型/强度是否可选（部分工具不支持）
const showModel = computed(() => (isCli.value ? !!selectedCli.value?.supports_model : true))
const showEffort = computed(() => (isCli.value ? !!selectedCli.value?.supports_effort : true))

async function load() {
  const d = await jsonFetch('/api/qube/config')
  providers.value = d.providers
  cliTools.value = d.cli_tools
  cfg.value.qube_engine = d.qube_engine
  cfg.value.qube_provider = d.qube_provider
  cfg.value.qube_model = d.qube_model
  cfg.value.qube_effort = d.qube_effort || 'medium'
  cfg.value.qube_cli = d.qube_cli
  cfg.value.qube_cli_model = d.qube_cli_model || ''
  cfg.value.qube_cli_effort = d.qube_cli_effort || 'default'
  loaded.value = true
}
onMounted(load)
defineExpose({ reload: load })

async function patch(body: Record<string, string>) {
  await jsonFetch('/api/qube/config', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}
</script>

<template>
  <!-- 加载完成前不渲染，避免先显示默认 API 再跳到实际配置的闪烁 -->
  <!-- 全部一行显示：引擎/源固定窄宽，模型/强度弹性收缩，模型名过长靠 Select 内 truncate 截断不换行 -->
  <div v-if="loaded" class="flex min-w-0 flex-nowrap items-center gap-1.5">
    <div class="min-w-0 shrink-[3] basis-[104px]"><Select v-model="engineModel" :options="engineOptions" /></div>
    <div class="min-w-0 flex-1"><Select v-model="sourceModel" :options="sourceOptions" :placeholder="isCli ? 'CLI 工具' : '供应商'" /></div>
    <div v-if="showModel" class="min-w-0 flex-[1.4]"><Select v-model="modelModel" :options="modelOptions" placeholder="选择模型" /></div>
    <div v-if="showEffort" class="min-w-0 shrink-0 basis-[100px]"><Select v-model="effortModel" :options="effortOptions" /></div>
  </div>
</template>
