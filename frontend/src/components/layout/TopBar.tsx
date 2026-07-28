import { useLocation, Link } from 'react-router-dom';

const routeTitles: Record<string, string> = {
  '/': '工作台',
  '/explore': '数据探索',
  '/factor': '因子研究',
  '/backtest': '策略回测',
  '/workflow': '工作流',
  '/experiments': '实验管理',
  '/data': '数据管理',
  '/settings': '设置',
};

function getTitle(pathname: string): string {
  if (routeTitles[pathname]) return routeTitles[pathname];
  if (pathname.startsWith('/workflow/')) return '工作流编辑器';
  return '';
}

export default function TopBar() {
  const location = useLocation();
  const title = getTitle(location.pathname);

  return (
    <div
      className="flex items-center justify-between px-4 shrink-0"
      style={{
        height: 40,
        background: '#262222',
        borderBottom: '1px solid #403b3b',
      }}
    >
      {/* Left: breadcrumb / title */}
      <div className="flex items-center gap-2">
        {location.pathname !== '/' && (
          <span className="text-[#9a9898] text-[13px]">
            <Link to="/" className="text-[#9a9898] no-underline hover:text-[#fdfcfc]">
              工作台
            </Link>
            <span className="mx-1">/</span>
          </span>
        )}
        <span className="text-[13px] text-[#fdfcfc]">{title}</span>
      </div>

      {/* Right: QMT connection status */}
      <div className="flex items-center gap-1.5">
        <span
          className="inline-block rounded-full"
          style={{
            width: 8,
            height: 8,
            background: '#6e6e73',
          }}
        />
        <span className="text-[12px] text-[#9a9898]">QMT 未连接</span>
      </div>
    </div>
  );
}
