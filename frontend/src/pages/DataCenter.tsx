import { useState } from 'react';
import { Tabs } from '@/components/ui';
import DataManagement from './DataManagement';
import DataExplore from './DataExplore';

const tabItems = [
  { key: 'manage', label: '数据管理' },
  { key: 'explore', label: '数据探索' },
];

/** 数据中心：数据管理（QMT 连接/下载/缓存）与数据探索（SQL/扫描/分析）合并入口 */
export default function DataCenter() {
  const [activeTab, setActiveTab] = useState('manage');

  return (
    <div className="flex flex-col h-full">
      <div className="mb-4">
        <h1 className="text-xl font-semibold text-[#201d1d] mb-1">数据中心</h1>
        <p className="text-[13px] text-[#646262]">
          管理 QMT 数据源与本地缓存，并对数据进行 SQL 查询、扫描与分析
        </p>
      </div>

      <Tabs items={tabItems} activeKey={activeTab} onChange={setActiveTab} />

      <div className="flex-1 mt-4 min-h-0 overflow-auto">
        {activeTab === 'manage' && <DataManagement />}
        {activeTab === 'explore' && <DataExplore />}
      </div>
    </div>
  );
}
