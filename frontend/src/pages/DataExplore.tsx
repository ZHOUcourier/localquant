import { useState } from 'react';
import { Tabs } from '@/components/ui';
import { SQLPanel } from '@/components/explore/SQLPanel';
import { MarketScanner } from '@/components/explore/MarketScanner';
import { CrossSection } from '@/components/explore/CrossSection';
import { AnomalyDetector } from '@/components/explore/AnomalyDetector';

const tabItems = [
  { key: 'sql', label: 'SQL 查询' },
  { key: 'scan', label: '全市场扫描' },
  { key: 'cross', label: '横截面分析' },
  { key: 'anomaly', label: '异常检测' },
];

export default function DataExplore() {
  const [activeTab, setActiveTab] = useState('sql');

  return (
    <div className="flex flex-col h-full">
      <div className="mb-4">
        <h1 className="text-xl font-semibold text-[#eeeeee] mb-1">数据探索</h1>
        <p className="text-[13px] text-[#808080]">
          SQL 查询、市场扫描、横截面分析与异常检测
        </p>
      </div>

      <Tabs items={tabItems} activeKey={activeTab} onChange={setActiveTab} />

      <div className="flex-1 mt-4 overflow-auto">
        {activeTab === 'sql' && <SQLPanel />}
        {activeTab === 'scan' && <MarketScanner />}
        {activeTab === 'cross' && <CrossSection />}
        {activeTab === 'anomaly' && <AnomalyDetector />}
      </div>
    </div>
  );
}
