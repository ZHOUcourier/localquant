/**
 * Monaco 初始化（Vite worker 接线）+ 轻量语言服务
 * - editor/json worker；python 等基础语言由主包 tokenizer 提供高亮
 * - Python：注册量化研究常用 API 补全（pandas/numpy/节点约定），配合
 *   后端 /api/plugins/lint（ruff）实现内联诊断（见 registerRuffLint）
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

// —— Python 补全：关键字 + 量化研究常用库/方法 ——————————————————
const PY_KEYWORDS = [
  'def', 'class', 'return', 'import', 'from', 'as', 'if', 'elif', 'else', 'for',
  'while', 'try', 'except', 'finally', 'with', 'lambda', 'yield', 'raise', 'pass',
  'break', 'continue', 'global', 'nonlocal', 'assert', 'del', 'not', 'and', 'or',
  'in', 'is', 'None', 'True', 'False', 'async', 'await',
]
const PY_SNIPPETS: { label: string; insert: string; detail: string }[] = [
  { label: 'pd.DataFrame', insert: 'pd.DataFrame(${1:data})', detail: 'pandas DataFrame' },
  { label: 'pd.Series', insert: 'pd.Series(${1:data})', detail: 'pandas Series' },
  { label: 'pd.concat', insert: 'pd.concat([${1:dfs}], axis=${2:0})', detail: '拼接' },
  { label: 'rolling', insert: 'rolling(${1:window}).${2:mean}()', detail: '滚动窗口' },
  { label: 'shift', insert: 'shift(${1:1})', detail: '平移' },
  { label: 'pct_change', insert: 'pct_change(${1:1})', detail: '收益率' },
  { label: 'rank', insert: 'rank(axis=1, pct=True)', detail: '截面排名' },
  { label: 'groupby', insert: 'groupby(${1:key})', detail: '分组' },
  { label: 'fillna', insert: 'fillna(${1:0})', detail: '缺失填充' },
  { label: 'np.log', insert: 'np.log(${1:x})', detail: 'numpy 对数' },
  { label: 'np.where', insert: 'np.where(${1:cond}, ${2:a}, ${3:b})', detail: '条件选择' },
  { label: 'np.nan', insert: 'np.nan', detail: 'NaN' },
  {
    label: 'work_node 节点骨架',
    insert: [
      '@work_node(name="${1:节点名}", group="${2:99-自定义节点}")',
      'class ${3:MyNode}(BaseWorkNode):',
      '    @classmethod',
      '    def input_model(cls):',
      '        return ${4:MyInput}',
      '',
      '    @classmethod',
      '    def output_model(cls):',
      '        return ${5:MyOutput}',
      '',
      '    def run(self, input):',
      '        ${0:pass}',
    ].join('\n'),
    detail: 'LocalQuant 工作流节点模板',
  },
]

let pythonCompletionRegistered = false
function registerPythonCompletion() {
  if (pythonCompletionRegistered) return
  pythonCompletionRegistered = true
  monaco.languages.registerCompletionItemProvider('python', {
    provideCompletionItems(model, position) {
      const word = model.getWordUntilPosition(position)
      const range = new monaco.Range(
        position.lineNumber, word.startColumn, position.lineNumber, word.endColumn,
      )
      const suggestions: monaco.languages.CompletionItem[] = [
        ...PY_KEYWORDS.map((k) => ({
          label: k,
          kind: monaco.languages.CompletionItemKind.Keyword,
          insertText: k,
          range,
        })),
        ...PY_SNIPPETS.map((s) => ({
          label: s.label,
          kind: monaco.languages.CompletionItemKind.Snippet,
          insertText: s.insert,
          insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
          detail: s.detail,
          range,
        })),
      ]
      return { suggestions }
    },
  })
}
registerPythonCompletion()

// —— ruff 内联诊断：内容变化去抖调用后端，把诊断映射为 markers ————————
export interface RuffDiagnostic {
  line: number
  column: number
  end_line: number
  end_column: number
  code: string
  message: string
  severity: 'error' | 'warning'
}

export async function lintPython(source: string): Promise<{ diagnostics: RuffDiagnostic[]; note?: string }> {
  const res = await fetch('/api/plugins/lint', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source }),
  })
  if (!res.ok) throw new Error(`lint HTTP ${res.status}`)
  return res.json()
}

/** 把 ruff 诊断写入编辑器 markers（内联红/黄波浪线 + hover 详情） */
export function applyRuffMarkers(model: monaco.editor.ITextModel, diags: RuffDiagnostic[]) {
  monaco.editor.setModelMarkers(
    model,
    'ruff',
    diags.map((d) => ({
      startLineNumber: d.line || 1,
      startColumn: d.column || 1,
      endLineNumber: d.end_line || d.line || 1,
      endColumn: d.end_column || (d.column || 1) + 1,
      message: `${d.code} ${d.message}`,
      severity: d.severity === 'error' ? monaco.MarkerSeverity.Error : monaco.MarkerSeverity.Warning,
    })),
  )
}

export { monaco }
