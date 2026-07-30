<script setup lang="ts">
/**
 * CodeEditor — 带「网页全屏」按钮的 Monaco 编辑器封装（Vue 版）
 *
 * 全屏为覆盖整个视口的网页全屏（fixed inset-0，隐藏其他 UI），
 * 非浏览器 Fullscreen API；Esc 或按钮退出。
 * 所有涉及代码编辑的界面统一使用本组件。
 */
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Maximize2, Minimize2 } from 'lucide-vue-next'
import { monaco } from '@/lib/monaco'

const props = withDefaults(
  defineProps<{
    language?: string
    height?: number | string
    readOnly?: boolean
    /** 全屏时顶栏显示的标题 */
    title?: string
    fontSize?: number
  }>(),
  { language: 'python', height: 300, readOnly: false, title: '代码编辑', fontSize: 12 },
)

const model = defineModel<string>({ default: '' })

const fullscreen = ref(false)
const editorEl = ref<HTMLDivElement | null>(null)
let editor: ReturnType<typeof monaco.editor.create> | null = null

function createEditor() {
  if (!editorEl.value) return
  editor = monaco.editor.create(editorEl.value, {
    value: model.value,
    language: props.language,
    theme: 'vs',
    readOnly: props.readOnly,
    minimap: { enabled: fullscreen.value },
    fontSize: fullscreen.value ? 14 : props.fontSize,
    lineNumbers: 'on',
    scrollBeyondLastLine: false,
    automaticLayout: true,
    tabSize: 4,
    wordWrap: 'on',
    padding: { top: 8 },
  })
  editor.onDidChangeModelContent(() => {
    const v = editor?.getValue() ?? ''
    if (v !== model.value) model.value = v
  })
}

onMounted(createEditor)
onBeforeUnmount(() => editor?.dispose())

// 外部值变化 → 同步进编辑器（避免光标跳动只在值不同时设置）
watch(model, (v) => {
  if (editor && editor.getValue() !== v) editor.setValue(v ?? '')
})
watch(
  () => props.language,
  (lang) => {
    const m = editor?.getModel()
    if (m) monaco.editor.setModelLanguage(m, lang)
  },
)
watch(fullscreen, (fs) => {
  editor?.updateOptions({ minimap: { enabled: fs }, fontSize: fs ? 14 : props.fontSize })
})

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') fullscreen.value = false
}
watch(fullscreen, (fs) => {
  if (fs) window.addEventListener('keydown', onKey)
  else window.removeEventListener('keydown', onKey)
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div
    :style="
      fullscreen
        ? { position: 'fixed', inset: '0', zIndex: 100, background: '#fdfcfc', display: 'flex', flexDirection: 'column' }
        : {
            position: 'relative',
            height: typeof height === 'number' ? `${height}px` : height,
            minHeight: typeof height === 'number' ? `${height}px` : '120px',
            border: '1px solid rgba(15,0,0,0.12)',
            borderRadius: '4px',
            overflow: 'hidden',
          }
    "
  >
    <div
      v-if="fullscreen"
      style="
        height: 48px;
        flex-shrink: 0;
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0 16px;
        border-bottom: 1px solid rgba(15, 0, 0, 0.12);
        background: #f1eeee;
        font-family: var(--font-mono, monospace);
      "
    >
      <span style="font-size: 13px; font-weight: 600; color: #201d1d">{{ title }}</span>
      <button
        title="退出全屏 (Esc)"
        style="
          display: flex;
          align-items: center;
          gap: 5px;
          padding: 4px 10px;
          background: transparent;
          border: 1px solid rgba(15, 0, 0, 0.12);
          border-radius: 4px;
          color: #646262;
          font-size: 12px;
          cursor: pointer;
          font-family: inherit;
        "
        @click="fullscreen = false"
      >
        <Minimize2 :size="13" />
        退出全屏
      </button>
    </div>

    <button
      v-if="!fullscreen"
      title="网页全屏编辑（隐藏其他界面）"
      style="
        position: absolute;
        top: 6px;
        right: 16px;
        z-index: 10;
        display: flex;
        align-items: center;
        gap: 4px;
        padding: 3px 8px;
        background: rgba(253, 252, 252, 0.9);
        border: 1px solid rgba(15, 0, 0, 0.12);
        border-radius: 4px;
        color: #646262;
        font-size: 11px;
        cursor: pointer;
        font-family: var(--font-mono, monospace);
      "
      @click="fullscreen = true"
    >
      <Maximize2 :size="11" />
      全屏
    </button>

    <div ref="editorEl" :style="{ height: fullscreen ? 'calc(100vh - 48px)' : '100%', width: '100%' }" />
  </div>
</template>
