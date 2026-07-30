<script setup lang="ts">
import { ref } from 'vue'
import { Tabs } from '@/components/ui'
import DataOverview from '@/components/explore/DataOverview.vue'
import SQLPanel from '@/components/explore/SQLPanel.vue'
import MarketScanner from '@/components/explore/MarketScanner.vue'
import CrossSection from '@/components/explore/CrossSection.vue'
import AnomalyDetector from '@/components/explore/AnomalyDetector.vue'
import RegressionAnalysis from '@/components/explore/RegressionAnalysis.vue'
import Seasonality from '@/components/explore/Seasonality.vue'
import VolatilityAnalysis from '@/components/explore/VolatilityAnalysis.vue'
import CorrelationMatrix from '@/components/explore/CorrelationMatrix.vue'
import RiskProfile from '@/components/explore/RiskProfile.vue'
import PairSpread from '@/components/explore/PairSpread.vue'
import RollingCorrelation from '@/components/explore/RollingCorrelation.vue'

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
]

const activeTab = ref('overview')
</script>

<template>
  <div class="flex flex-col h-full">
    <Tabs :items="tabItems" :active-key="activeTab" @change="(k) => (activeTab = k)" />

    <div class="flex-1 mt-4 overflow-auto">
      <DataOverview v-if="activeTab === 'overview'" />
      <SQLPanel v-if="activeTab === 'sql'" />
      <MarketScanner v-if="activeTab === 'scan'" />
      <CrossSection v-if="activeTab === 'cross'" />
      <AnomalyDetector v-if="activeTab === 'anomaly'" />
      <RiskProfile v-if="activeTab === 'risk'" />
      <RegressionAnalysis v-if="activeTab === 'regression'" />
      <RollingCorrelation v-if="activeTab === 'rolling'" />
      <PairSpread v-if="activeTab === 'pair'" />
      <Seasonality v-if="activeTab === 'seasonality'" />
      <VolatilityAnalysis v-if="activeTab === 'volatility'" />
      <CorrelationMatrix v-if="activeTab === 'correlation'" />
    </div>
  </div>
</template>
