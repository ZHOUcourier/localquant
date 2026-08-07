<script setup lang="ts">
import { ref } from 'vue'
import { Tabs } from '@/components/ui'
import DataManagement from './DataManagement.vue'
import DataExplore from './DataExplore.vue'
import RegimeCard from '@/components/explore/RegimeCard.vue'

const tabItems = [
  { key: 'manage', label: '数据管理' },
  { key: 'explore', label: '数据探索' },
]

/** 数据中心：数据管理（QMT 连接/下载/缓存）与数据探索（SQL/扫描/分析）合并入口 */
const activeTab = ref('manage')
</script>

<template>
  <!-- 整页滚动：内容自然高度，滚动由外层 Layout main 承接（避免双层滚动条） -->
  <div class="flex flex-col">
    <div class="mb-4">
      <h1 class="text-xl font-semibold text-[#201d1d] mb-1">数据中心</h1>
      <p class="text-[13px] text-[#646262]">
        管理 QMT 数据源与本地缓存，并对数据进行 SQL 查询、扫描与分析
      </p>
    </div>

    <!-- 市场环境仪表盘（研究员第一步：市场状态 + 风格轮动；基于指数日线缓存） -->
    <div class="mb-4">
      <RegimeCard />
    </div>

    <Tabs :items="tabItems" :active-key="activeTab" @change="(k) => (activeTab = k)" />

    <div class="mt-4">
      <DataManagement v-if="activeTab === 'manage'" />
      <DataExplore v-if="activeTab === 'explore'" />
    </div>
  </div>
</template>
