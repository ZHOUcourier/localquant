import { useState } from 'react';
import { Tabs } from '@/components/ui';
import { DataOverview } from '@/components/explore/DataOverview';
import { SQLPanel } from '@/components/explore/SQLPanel';
import { MarketScanner } from '@/components/explore/MarketScanner';
import { CrossSection } from '@/components/explore/CrossSection';
import { AnomalyDetector } from '@/components/explore/AnomalyDetector';

const tabItems = [
  { key: 'overview', label: '数据概览' },
  { key: 'sql', label: 'SQL 查询 · AI' },
  { key: 'scan', label: '全市场扫描' },
  { key: 'cross', label: '横截面分析' },
  { key: 'anomaly', label: '异常检测' },
];

export default function DataExplore() {
  const [activeTab, setActiveTab] = useState('overview');

  return (
    <div className="flex flex-col h-full">
      <Tabs items={tabItems} activeKey={activeTab} onChange={setActiveTab} />

      <div className="flex-1 mt-4 overflow-auto">
        {activeTab === 'overview' && <DataOverview />}
        {activeTab === 'sql' && <SQLPanel />}
        {activeTab === 'scan' && <MarketScanner />}
        {activeTab === 'cross' && <CrossSection />}
        {activeTab === 'anomaly' && <AnomalyDetector />}
      </div>
    </div>
  );
}
