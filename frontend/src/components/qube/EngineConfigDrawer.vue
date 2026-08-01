<script setup lang="ts">
/**
 * EngineConfigDrawer — QUBE 引擎密钥配置（精简版）
 *
 * 引擎/供应商/模型/推理强度的「选择」全部交给对话框下方的 ModelBar，此处不再重复；
 * 本抽屉只负责对话框里不便放的东西：API Key、Base URL（BYOK）。
 * 展示当前引擎与供应商仅作只读上下文提示。
 */
import { computed, onMounted, ref } from 'vue'
import { jsonFetch } from './types'

interface ProviderInfo {
  id: string
  label: string
  byok: boolean
}

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: [] }>()

const loaded = ref(false)
const providers = ref<ProviderInfo[]>([])
const engine = ref('api')
const providerId = ref('')
const cliId = ref('')
const baseUrl = ref('')
const apiKey = ref('')
const keyMasked = ref('')
const saving = ref(false)
const msg = ref('')

const selectedProvider = computed(() => providers.value.find((p) => p.id === providerId.value))

async function load() {
  const d = await jsonFetch('/api/qube/config')
  providers.value = d.providers
  engine.value = d.qube_engine
  providerId.value = d.qube_provider
  cliId.value = d.qube_cli
  baseUrl.value = d.qube_base_url || ''
  keyMasked.value = d.qube_api_key_masked
  loaded.value = true
}
onMounted(load)
defineExpose({ reload: load })

async function save() {
  saving.value = true
  msg.value = ''
  try {
    const body: Record<string, string> = { qube_base_url: baseUrl.value }
    if (apiKey.value) body.qube_api_key = apiKey.value
    await jsonFetch('/api/qube/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    apiKey.value = ''
    msg.value = '已保存'
    load()
  } catch (e) {
    msg.value = e instanceof Error ? e.message : String(e)
  } finally {
    saving.value = false
  }
}

void props
</script>

<template>
  <div v-if="props.open" class="fixed inset-0 z-[80] flex justify-end bg-black/30" @click.self="emit('close')">
    <div class="flex h-full w-[380px] flex-col overflow-y-auto border-l border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] p-4">
      <div class="mb-1 flex items-center justify-between">
        <span class="text-[13px] font-semibold text-[#201d1d]">引擎密钥</span>
        <button class="text-[#646262] hover:text-[#201d1d]" @click="emit('close')">✕</button>
      </div>
      <div class="mb-4 text-[11px] leading-relaxed text-[#9a9898]">
        引擎、供应商、模型、推理强度请在对话框下方直接切换；这里只填 API 供应商需要的密钥。
      </div>

      <template v-if="loaded">
        <!-- 当前状态（只读提示） -->
        <div class="mb-4 rounded-[4px] bg-[#f8f7f7] px-3 py-2 text-[11px] text-[#646262]">
          当前引擎：<span class="font-medium text-[#201d1d]">{{ engine === 'cli' ? '本机 CLI 工具' : 'API 供应商' }}</span>
          <span v-if="engine === 'cli'"> · {{ cliId }}</span>
          <span v-else> · {{ selectedProvider?.label || providerId }}</span>
        </div>

        <template v-if="engine === 'cli'">
          <div class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-3 py-2.5 text-[11px] leading-relaxed text-[#646262]">
            本机 CLI 工具使用你已登录的账号，<b class="text-[#201d1d]">无需在此配置 API Key</b>。
            如需更换 CLI 工具或模型，请用对话框下方的下拉。
          </div>
        </template>

        <template v-else>
          <div v-if="selectedProvider?.byok" class="mb-3">
            <label class="mb-1 block text-xs text-[#646262]">Base URL（BYOK）</label>
            <input
              v-model="baseUrl"
              placeholder="https://your-endpoint/v1"
              class="w-full rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-2.5 py-1.5 text-xs outline-none focus:border-[#201d1d]"
            />
          </div>
          <div class="mb-3">
            <label class="mb-1 block text-xs text-[#646262]">
              API Key {{ keyMasked ? `（已设置 ${keyMasked}，留空不修改）` : '' }}
            </label>
            <input
              v-model="apiKey"
              type="password"
              placeholder="sk-..."
              class="w-full rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-2.5 py-1.5 text-xs outline-none focus:border-[#201d1d]"
            />
          </div>
          <div class="flex items-center gap-2">
            <button
              :disabled="saving"
              class="rounded-[4px] bg-[#201d1d] px-4 py-1.5 text-xs text-[#fdfcfc] hover:opacity-85 disabled:opacity-50"
              @click="save"
            >
              {{ saving ? '保存中...' : '保存密钥' }}
            </button>
            <span class="text-[11px] text-[#646262]">{{ msg }}</span>
          </div>
        </template>
      </template>
    </div>
  </div>
</template>
