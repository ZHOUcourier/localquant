/**
 * CodeEditor — 带「网页全屏」按钮的 Monaco 编辑器封装
 *
 * 全屏为覆盖整个视口的网页全屏（fixed inset-0，隐藏其他 UI），
 * 非浏览器 Fullscreen API；Esc 或按钮退出。
 * 所有涉及代码编辑的界面统一使用本组件。
 */
import { useEffect, useState, useCallback } from 'react';
import Editor from '@monaco-editor/react';
import { Maximize2, Minimize2 } from 'lucide-react';

interface CodeEditorProps {
  value: string;
  onChange?: (value: string) => void;
  language?: string;
  height?: number | string;
  readOnly?: boolean;
  /** 全屏时顶栏显示的标题 */
  title?: string;
  fontSize?: number;
}

export function CodeEditor({
  value,
  onChange,
  language = 'python',
  height = 300,
  readOnly = false,
  title = '代码编辑',
  fontSize = 12,
}: CodeEditorProps) {
  const [fullscreen, setFullscreen] = useState(false);

  const exitFullscreen = useCallback(() => setFullscreen(false), []);

  useEffect(() => {
    if (!fullscreen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') exitFullscreen();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [fullscreen, exitFullscreen]);

  const editorOptions = {
    readOnly,
    minimap: { enabled: fullscreen },
    fontSize: fullscreen ? 14 : fontSize,
    lineNumbers: 'on' as const,
    scrollBeyondLastLine: false,
    automaticLayout: true,
    tabSize: 4,
    wordWrap: 'on' as const,
    padding: { top: 8 },
  };

  const editor = (
    <Editor
      height={fullscreen ? 'calc(100vh - 48px)' : '100%'}
      language={language}
      theme="light"
      value={value}
      onChange={(v) => onChange?.(v ?? '')}
      options={editorOptions}
    />
  );

  if (fullscreen) {
    return (
      <div
        style={{
          position: 'fixed',
          inset: 0,
          zIndex: 100,
          background: '#fdfcfc',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <div
          style={{
            height: 48,
            flexShrink: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0 16px',
            borderBottom: '1px solid rgba(15,0,0,0.12)',
            background: '#f1eeee',
            fontFamily: 'var(--font-mono, monospace)',
          }}
        >
          <span style={{ fontSize: 13, fontWeight: 600, color: '#201d1d' }}>
            {title}
          </span>
          <button
            onClick={exitFullscreen}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 5,
              padding: '4px 10px',
              background: 'transparent',
              border: '1px solid rgba(15,0,0,0.12)',
              borderRadius: 4,
              color: '#646262',
              fontSize: 12,
              cursor: 'pointer',
              fontFamily: 'inherit',
            }}
            title="退出全屏 (Esc)"
          >
            <Minimize2 size={13} />
            退出全屏
          </button>
        </div>
        <div style={{ flex: 1 }}>{editor}</div>
      </div>
    );
  }

  return (
    <div
      style={{
        position: 'relative',
        height,
        minHeight: typeof height === 'number' ? height : 120,
        border: '1px solid rgba(15,0,0,0.12)',
        borderRadius: 4,
        overflow: 'hidden',
      }}
    >
      <button
        onClick={() => setFullscreen(true)}
        style={{
          position: 'absolute',
          top: 6,
          right: 16,
          zIndex: 10,
          display: 'flex',
          alignItems: 'center',
          gap: 4,
          padding: '3px 8px',
          background: 'rgba(253,252,252,0.9)',
          border: '1px solid rgba(15,0,0,0.12)',
          borderRadius: 4,
          color: '#646262',
          fontSize: 11,
          cursor: 'pointer',
          fontFamily: 'var(--font-mono, monospace)',
        }}
        title="网页全屏编辑（隐藏其他界面）"
      >
        <Maximize2 size={11} />
        全屏
      </button>
      {editor}
    </div>
  );
}
