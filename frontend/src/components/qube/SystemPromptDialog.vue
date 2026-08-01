<script setup lang="ts">
/**
 * SystemPromptDialog — 系统提示词展示/编辑（替代参考站「长期记忆」）
 * 管理跨会话生效的 AI 系统预知提示词；可保存/恢复默认。
 */
import { onMounted, ref } from 'vue'
import Dialog from '@/components/ui/Dialog.vue'
import { jsonFetch } from './types'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: [] }>()

const prompt = ref('')
const defaultPrompt = ref('')
const customized = ref(false)
const saving = ref(false)
const savedTip = ref('')

async function load() {
  const d = await jsonFetch('/api/qube/system-prompt')
  prompt.value = d.prompt
  defaultPrompt.value = d.default_prompt
  customized.value = d.customized
}
onMounted(load)

async function save() {
  saving.value = true
  savedTip.value = ''
  try {
    const d = await jsonFetch('/api/qube/system-prompt', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: prompt.value }),
    })
    customized.value = d.customized
    savedTip.value = '已保存'
    setTimeout(() => (savedTip.value = ''), 2000)
  } finally {
    saving.value = false
  }
}

function restoreDefault() {
  prompt.value = defaultPrompt.value
}

void props
</script>

<template>
  <Dialog :open="props.open" title="AI 系统提示词" @close="emit('close')">
    <div class="w-[640px] max-w-[86vw]">
      <p class="mb-3 flex items-start gap-1.5 rounded-[4px] bg-[#007aff]/6 px-2.5 py-1.5 text-[11px] leading-relaxed text-[#0056b3]">
        <span class="font-mono">[i]</span>
        <span>
          这段提示词跨会话生效，作为 AI 的长期背景与行为准则（相当于参考站的「长期记忆/偏好与事实」）。
          修改后对之后的所有对话生效；临时的回测参数不要写在这里。
        </span>
      </p>
      <textarea
        v-model="prompt"
        rows="16"
        spellcheck="false"
        class="w-full resize-none rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-3 py-2 font-mono text-[12px] leading-relaxed text-[#201d1d] outline-none focus:border-[#201d1d]"
      />
      <div class="mt-1 text-[10px] text-[#9a9898]">
        {{ customized ? '当前使用自定义提示词' : '当前使用内置默认提示词' }} · {{ prompt.length }} 字
      </div>
    </div>
    <template #footer>
      <span v-if="savedTip" class="mr-auto text-[11px] text-[#1d8a3e]">{{ savedTip }}</span>
      <button
        class="rounded-[4px] border border-[rgba(15,0,0,0.15)] px-3 py-1 text-xs text-[#646262] hover:text-[#201d1d]"
        @click="restoreDefault"
      >
        恢复默认
      </button>
      <button
        :disabled="saving"
        class="rounded-[4px] bg-[#201d1d] px-4 py-1 text-xs text-[#fdfcfc] hover:opacity-85 disabled:opacity-50"
        @click="save"
      >
        {{ saving ? '保存中…' : '保存' }}
      </button>
    </template>
  </Dialog>
</template>
