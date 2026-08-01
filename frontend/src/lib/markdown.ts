/**
 * markdown 渲染（marked + dompurify）— QUBE 对话 AI 消息文本段专用
 * 样式由 index.css 的 .md-body 控制（opencode 风格：等宽字体、hairline 表格）。
 */
import DOMPurify from 'dompurify'
import { marked } from 'marked'

marked.setOptions({ gfm: true, breaks: true })

export function renderMarkdown(text: string): string {
  const html = marked.parse(text || '', { async: false }) as string
  return DOMPurify.sanitize(html)
}
