import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  FlaskConical,
  GitBranch,
  Play,
  History,
  Database,
  Settings,
} from 'lucide-react';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: '工作台', end: true },
  { to: '/data', icon: Database, label: '数据中心', end: false },
  { to: '/factor', icon: FlaskConical, label: '因子研究', end: false },
  { to: '/workflow', icon: GitBranch, label: '工作流', end: false },
  { to: '/runs', icon: Play, label: '运行中心', end: false },
  { to: '/experiments', icon: History, label: '实验管理', end: false },
  { to: '/settings', icon: Settings, label: '设置', end: false },
];

export default function Sidebar() {
  return (
    <div
      className="flex flex-col h-full shrink-0"
      style={{
        width: 200,
        background: '#f1eeee',
        borderRight: '1px solid rgba(15, 0, 0, 0.12)',
      }}
    >
      <div
        className="flex items-center h-10 px-4 shrink-0"
        style={{ borderBottom: '1px solid rgba(15, 0, 0, 0.12)' }}
      >
        <span
          className="text-base font-bold tracking-wide"
          style={{ color: '#007aff', fontFamily: 'var(--font-mono)' }}
        >
          LocalQuant
        </span>
      </div>

      <nav className="flex-1 py-2 overflow-y-auto">
        {navItems.map(({ to, icon: Icon, label, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `relative flex items-center gap-2 px-4 no-underline transition-colors duration-100 ${
                isActive
                  ? 'text-[#201d1d] bg-[#f8f7f7]'
                  : 'text-[#646262] hover:text-[#201d1d] hover:bg-[#f8f7f7]'
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

      <div
        className="shrink-0 px-4 py-2 text-[11px]"
        style={{ color: '#646262', borderTop: '1px solid rgba(15, 0, 0, 0.12)' }}
      >
        v0.1.0
      </div>
    </div>
  );
}
