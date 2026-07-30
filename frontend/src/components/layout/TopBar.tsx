import { useEffect, useState } from 'react';
import { useLocation, Link } from 'react-router-dom';

const routeTitles: Record<string, string> = {
  '/': '工作台',
  '/data': '数据中心',
  '/factor': '因子研究',
  '/workflow': '工作流',
  '/runs': '运行中心',
  '/experiments': '实验管理',
  '/settings': '设置',
};

/** 子路由面包屑：pathname → { text, link? }[] */
function getBreadcrumbs(pathname: string): { text: string; link?: string }[] {
  if (routeTitles[pathname]) return [{ text: routeTitles[pathname] }];
  if (pathname.startsWith('/workflow/')) return [
    { text: '工作流', link: '/workflow' },
    { text: '编辑器' },
  ];
  return [{ text: '' }];
}

/** 右上角实时时钟 */
function Clock() {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const date = now.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit', weekday: 'short' });
  const time = now.toLocaleTimeString('zh-CN', { hour12: false });

  return (
    <span className="font-mono text-[12px] text-[#646262]" style={{ fontVariantNumeric: 'tabular-nums' }}>
      {date} {time}
    </span>
  );
}

/** QMT 真实连接状态（轮询 /api/data/status，不再硬编码） */
function QmtStatus() {
  const [connected, setConnected] = useState<boolean | null>(null);

  useEffect(() => {
    let alive = true;
    const check = async () => {
      try {
        const r = await fetch('/api/data/status');
        if (!r.ok) throw new Error();
        const data = await r.json();
        if (alive) setConnected(!!data.qmt_connected);
      } catch {
        if (alive) setConnected(null);
      }
    };
    check();
    const id = setInterval(check, 30000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  return (
    <div className="flex items-center gap-1.5">
      <span
        className="inline-block rounded-full"
        style={{
          width: 8,
          height: 8,
          background: connected ? '#30d158' : '#6e6e73',
        }}
      />
      <span className="text-[12px] text-[#646262]">
        {connected == null ? 'QMT 状态未知' : connected ? 'QMT 已连接' : 'QMT 未连接'}
      </span>
    </div>
  );
}

export default function TopBar() {
  const location = useLocation();
  const crumbs = getBreadcrumbs(location.pathname);

  return (
    <div
      className="flex items-center justify-between px-8 shrink-0"
      style={{
        height: 56,
        background: '#fdfcfc',
        borderBottom: '1px solid rgba(15, 0, 0, 0.08)',
      }}
    >
      <div className="flex items-center gap-1">
        {crumbs.map((crumb, i) => {
          const isLast = i === crumbs.length - 1;
          if (isLast || !crumb.link) {
            return (
              <span key={i} className="text-[15px] font-medium text-[#201d1d]">
                {crumb.text}
              </span>
            );
          }
          return (
            <span key={i} className="flex items-center gap-1">
              <Link
                to={crumb.link}
                className="text-[13px] text-[#646262] no-underline hover:text-[#201d1d]"
              >
                {crumb.text}
              </Link>
              <span className="text-[13px] text-[#9a9898]">/</span>
            </span>
          );
        })}
      </div>

      <div className="flex items-center gap-4">
        <QmtStatus />
        <Clock />
      </div>
    </div>
  );
}
