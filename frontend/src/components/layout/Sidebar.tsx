import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Search,
  FlaskConical,
  BarChart3,
  GitBranch,
  History,
  Database,
  Settings,
} from 'lucide-react';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: '工作台', end: true },
  { to: '/explore', icon: Search, label: '数据探索', end: false },
  { to: '/factor', icon: FlaskConical, label: '因子研究', end: false },
  { to: '/backtest', icon: BarChart3, label: '策略回测', end: false },
  { to: '/workflow', icon: GitBranch, label: '工作流', end: false },
  { to: '/experiments', icon: History, label: '实验管理', end: false },
  { to: '/data', icon: Database, label: '数据管理', end: false },
  { to: '/settings', icon: Settings, label: '设置', end: false },
];

export default function Sidebar() {
  return (
    <div
      className="flex flex-col h-full shrink-0"
      style={{
        width: 200,
        background: '#262222',
        borderRight: '1px solid #403b3b',
      }}
    >
      {/* Logo */}
      <div
        className="flex items-center h-10 px-4 shrink-0"
        style={{ borderBottom: '1px solid #403b3b' }}
      >
        <span
          className="text-base font-bold tracking-wide"
          style={{ color: '#007aff', fontFamily: 'var(--font-mono)' }}
        >
          LocalQuant
        </span>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-2 overflow-y-auto">
        {navItems.map(({ to, icon: Icon, label, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `relative flex items-center gap-2 px-4 no-underline transition-colors duration-100 ${
                isActive
                  ? 'text-[#fdfcfc] bg-[#302c2c]'
                  : 'text-[#9a9898] hover:text-[#fdfcfc] hover:bg-[#302c2c]'
              }`
            }
            style={{ height: 36 }}
          >
            {({ isActive }) => (
              <>
                {isActive && (
                  <span
                    className="absolute left-0 top-0 bottom-0"
                    style={{
                      width: 2,
                      background: '#007aff',
                    }}
                  />
                )}
                <Icon size={16} />
                <span className="text-[13px]">{label}</span>
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Version */}
      <div
        className="shrink-0 px-4 py-2 text-[11px]"
        style={{ color: '#6e6e73', borderTop: '1px solid #403b3b' }}
      >
        v0.1.0
      </div>
    </div>
  );
}
