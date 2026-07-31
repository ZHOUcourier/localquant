<script setup lang="ts">
/**
 * NodeCodeDialog — 工作流节点代码编辑弹窗（外壳侧 Monaco 版）
 *
 * 由 iframe 内 ComfyUI 扩展经 postMessage 委托打开：
 * 完整 Monaco 能力（语法高亮 / Python 补全 / ruff 内联诊断）+ AI 改写 +
 * 保存（内置节点 fork 保护，与 node_tools.js 行为一致）。
 * 保存成功后 emit('saved')，由父组件通知 iframe 刷新节点定义。
 */
import { ref, watch } from 'vue'
import { Sparkles, X } from 'lucide-vue-next'
import CodeEditor from '@/components/ui/CodeEditor.vue'

const props = defineProps<{
  open: boolean
  classType: string
  displayName: string
}>()
const emit = defineEmits<{ close: []; saved: [] }>()

const source = ref('')
const isCustom = ref(false)
const loading = ref(false)
const msg = ref('')
const aiInstruction = ref('')
const aiLoading = ref(false)
const saving = ref(false)

async function jsonFetch(url: string, options?: RequestInit) {
  const res = await fetch(url, options)
  const body = await res.json().catch(() => null)
  if (!res.ok) throw new Error(body?.detail || `HTTP ${res.status}`)
  return body
}

async function load() {
  if (!props.classType) return
  loading.value = true
  msg.value = ''
  aiInstruction.value = ''
  try {
    const d = await jsonFetch(`/api/plugins/${encodeURIComponent(props.classType)}/source`)
    source.value = d.source || ''
    isCustom.value = !!d.is_custom
  } catch (e) {
    source.value = ''
    msg.value = `无法读取源码：${e instanceof Error ? e.message : e}`
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.open, props.classType],
  ([open]) => {
    if (open) load()
  },
  { immediate: true },
)

async function handleAI() {
  if (!aiInstruction.value.trim()) {
    msg.value = '请先在下方输入修改要求'
    return
  }
  aiLoading.value = true
  msg.value = 'AI 改写中…'
  try {
    const d = await jsonFetch('/api/ai/node-code', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source: source.value,
        instruction: aiInstruction.value,
        node_name: props.classType,
      }),
    })
    source.value = d.source || source.value
    msg.value = 'AI 已生成，请检查后点「保存」'
  } catch (e) {
    msg.value = `AI 失败：${e instanceof Error ? e.message : e}`
  } finally {
    aiLoading.value = false
  }
}

async function handleSave() {
  saving.value = true
  msg.value = '保存中…'
  try {
    let saved
    if (isCustom.value) {
      saved = await jsonFetch(`/api/plugins/custom/${encodeURIComponent(props.classType)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: source.value }),
      })
    } else {
      saved = await jsonFetch('/api/plugins/custom', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: source.value, base_name: props.classType }),
      })
    }
    msg.value = `已保存：${saved?.display_name || saved?.name || '完成'}`
    emit('saved')
  } catch (e) {
    msg.value = `保存失败：${e instanceof Error ? e.message : e}`
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div
    v-if="open"
    class="fixed inset-0 z-[80] flex items-center justify-center bg-black/45"
    @click.self="emit('close')"
  >
    <div
      class="flex flex-col overflow-hidden rounded-[6px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc]"
      style="width: min(920px, 94vw); height: min(82vh, 760px)"
    >
      <!-- 头部 -->
      <div
        class="flex shrink-0 items-center justify-between border-b border-[rgba(15,0,0,0.12)] bg-[#f1eeee] px-4 py-2.5"
      >
        <span class="text-[13px] font-semibold text-[#201d1d]">
          节点代码 · {{ displayName || classType }}
        </span>
        <button class="cursor-pointer border-0 bg-transparent text-[#646262] hover:text-[#201d1d]" @click="emit('close')">
          <X :size="16" />
        </button>
      </div>

      <!-- fork 保护提示 -->
      <div class="shrink-0 bg-[#f8f7f7] px-4 py-2 text-[11px] leading-relaxed text-[#646262]">
        <template v-if="isCustom">该节点为<b>自定义节点</b>，保存将<b>原地更新</b>其源码。</template>
        <template v-else>该节点为<b>内置节点</b>，保存将创建一个<b>「（改）」副本</b>（不改原节点）。</template>
        编辑器内置语法高亮、Python 补全与 ruff 内联诊断（波浪线处悬停可见详情）。
      </div>

      <!-- 编辑器 -->
      <div class="min-h-0 flex-1 px-4 py-3">
        <div v-if="loading" class="flex h-full items-center justify-center text-xs text-[#646262]">
          源码加载中...
        </div>
        <CodeEditor
          v-else
          v-model="source"
          language="python"
          height="100%"
          :title="`节点代码 · ${displayName || classType}`"
          :font-size="12"
        />
      </div>

      <!-- 底部：AI 改写 + 保存 -->
      <div class="flex shrink-0 flex-wrap items-center gap-2 border-t border-[rgba(15,0,0,0.12)] px-4 py-2.5">
        <input
          v-model="aiInstruction"
          placeholder="用自然语言描述要如何修改该节点，例如：把窗口参数默认值改成 20"
          class="min-w-[200px] flex-1 rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-2.5 py-1.5 text-xs text-[#201d1d] outline-none focus:border-[#007aff]"
          @keydown.enter="handleAI"
        />
        <button
          :disabled="aiLoading"
          class="flex items-center gap-1 rounded-[4px] border border-[#7c3aed]/40 bg-transparent px-3 py-1.5 text-xs text-[#7c3aed] transition-colors hover:bg-[#7c3aed]/10 disabled:opacity-50"
          @click="handleAI"
        >
          <Sparkles :size="12" />
          {{ aiLoading ? 'AI 改写中...' : '✦ AI 改写' }}
        </button>
        <button
          :disabled="saving || loading"
          class="rounded-[4px] border-0 bg-[#201d1d] px-4 py-1.5 text-xs text-[#fdfcfc] transition-opacity hover:opacity-85 disabled:opacity-50"
          @click="handleSave"
        >
          {{ saving ? '保存中...' : '保存' }}
        </button>
      </div>
      <div v-if="msg" class="shrink-0 px-4 pb-2 text-[11px] text-[#646262]">{{ msg }}</div>
    </div>
  </div>
</template>
