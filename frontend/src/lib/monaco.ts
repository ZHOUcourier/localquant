/**
 * Monaco 初始化（Vite worker 接线）
 * 仅注册 editor/json worker；python 等基础语言由主包 tokenizer 提供。
 */
import * as monaco from 'monaco-editor'
import EditorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker'
import JsonWorker from 'monaco-editor/esm/vs/language/json/json.worker?worker'

self.MonacoEnvironment = {
  getWorker(_workerId: string, label: string) {
    if (label === 'json') return new JsonWorker()
    return new EditorWorker()
  },
}

export { monaco }
