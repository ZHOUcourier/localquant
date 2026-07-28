import type { ReactNode } from 'react';
import Sidebar from './Sidebar';
import TopBar from './TopBar';
import { useBackendHealth } from '@/hooks/useBackendHealth';

interface LayoutProps {
  children: ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  const { online, checking } = useBackendHealth();

  return (
    <div className="flex flex-col h-screen" style={{ background: '#fdfcfc' }}>
      <TopBar />

      {!online && !checking && (
        <div
          className="flex items-center gap-2 border-b bg-[#f8f7f7] px-4 py-2 font-mono text-[13px] text-[#cc7f08]"
          style={{ borderColor: 'rgba(15, 0, 0, 0.12)' }}
        >
          <span className="inline-block h-2 w-2 rounded-full bg-[#ff9f0a]" />
          后端服务未连接 (http://localhost:8000) — 请运行
          <code className="rounded-[4px] bg-[#201d1d] px-1.5 py-0.5 text-[#fdfcfc]">make dev</code>
          或
          <code className="rounded-[4px] bg-[#201d1d] px-1.5 py-0.5 text-[#fdfcfc]">make dev-backend</code>
          ，页面数据将无法加载
        </div>
      )}

      <div className="flex flex-1 min-h-0">
        <Sidebar />
        <main className="flex-1 overflow-auto p-4">
          {children}
        </main>
      </div>
    </div>
  );
}
