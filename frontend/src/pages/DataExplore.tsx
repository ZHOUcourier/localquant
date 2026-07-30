import { useState } from 'react';
import { Tabs } from '@/components/ui';
import { DataOverview } from '@/components/explore/DataOverview';
import { SQLPanel } from '@/components/explore/SQLPanel';
import { MarketScanner } from '@/components/explore/MarketScanner';
import { CrossSection } from '@/components/explore/CrossSection';
import { AnomalyDetector } from '@/components/explore/AnomalyDetector';
import { RegressionAnalysis } from '@/components/explore/RegressionAnalysis';
import { Seasonality } from '@/components/explore/Seasonality';
import { VolatilityAnalysis } from '@/components/explore/VolatilityAnalysis';
import { CorrelationMatrix } from '@/components/explore/CorrelationMatrix';
import { RiskProfile } from '@/components/explore/RiskProfile';
import { PairSpread } from '@/components/explore/PairSpread';
import { RollingCorrelation } from '@/components/explore/RollingCorrelation';

const tabItems = [
  { key: 'overview', label: '数据概览' },
  { key: 'sql', label: 'SQL 查询 · AI' },
  { key: 'scan', label: '全市场扫描' },
  { key: 'cross', label: '横截面分析' },
  { key: 'anomaly', label: '异常检测' },
  { key: 'risk', label: '风险画像' },
  { key: 'regression', label: '回归分析' },
  { key: 'rolling', label: '滚动相关/Beta' },
  { key: 'pair', label: '配对价差' },
  { key: 'seasonality', label: '季节图表' },
  { key: 'volatility', label: '历史波动率' },
  { key: 'correlation', label: '相关性分析' },
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
        {activeTab === 'risk' && <RiskProfile />}
        {activeTab === 'regression' && <RegressionAnalysis />}
        {activeTab === 'rolling' && <RollingCorrelation />}
        {activeTab === 'pair' && <PairSpread />}
        {activeTab === 'seasonality' && <Seasonality />}
        {activeTab === 'volatility' && <VolatilityAnalysis />}
        {activeTab === 'correlation' && <CorrelationMatrix />}
      </div>
    </div>
  );
}
