<script setup lang="ts">
import {
  LayoutDashboard,
  FlaskConical,
  GitBranch,
  Play,
  History,
  Database,
  Radar,
  PanelLeftClose,
  Settings,
  Sparkles,
  BookMarked,
  Wrench,
} from 'lucide-vue-next'

const navItems = [
  { to: '/', icon: LayoutDashboard, label: '工作台', end: true },
  { to: '/data', icon: Database, label: '数据中心', end: false },
  { to: '/factor', icon: FlaskConical, label: '因子研究', end: false },
  { to: '/workflow', icon: GitBranch, label: '工作流', end: false },
  { to: '/qube', icon: Sparkles, label: 'QUBE', end: false },
  { to: '/strategies', icon: BookMarked, label: '策略库', end: false },
  { to: '/skills', icon: Wrench, label: '技能库', end: false },
  { to: '/runs', icon: Play, label: '回测记录', end: false },
  { to: '/experiments', icon: History, label: '实验管理', end: false },
  { to: '/risk', icon: Radar, label: '风险分析', end: false },
  { to: '/settings', icon: Settings, label: '设置', end: false },
]

const emit = defineEmits<{ collapse: [] }>()
</script>

<template>
  <div class="flex h-full w-full flex-col overflow-hidden" style="background: #f8f7f7">
    <div class="flex items-center h-14 px-5 shrink-0">
      <span
        class="text-base font-bold tracking-wide"
        style="color: #007aff; font-family: var(--font-mono)"
      >
        LocalQuant
      </span>
    </div>

    <nav class="flex-1 px-2 py-2 overflow-y-auto">
      <RouterLink
        v-for="item in navItems"
        :key="item.to"
        v-slot="{ isActive, isExactActive }"
        :to="item.to"
        custom
      >
        <a
          :href="item.to"
          class="relative flex items-center gap-2.5 px-3 no-underline transition-colors duration-100"
          :class="
            (item.end ? isExactActive : isActive)
              ? 'text-[#201d1d] font-medium'
              : 'text-[#646262] hover:text-[#201d1d] hover:bg-[#f1eeee] rounded-[4px]'
          "
          style="height: 40px; margin-bottom: 2px"
          @click.prevent="$router.push(item.to)"
        >
          <!-- 选中态左侧竖黑线（OpenCode 风格） -->
          <span
            v-if="item.end ? isExactActive : isActive"
            class="absolute left-0 top-1/2 h-[20px] w-[2px] -translate-y-1/2 bg-[#201d1d]"
          />
          <component :is="item.icon" :size="16" />
          <span class="text-[13px]">{{ item.label }}</span>
        </a>
      </RouterLink>
    </nav>

    <div class="flex shrink-0 items-center justify-between px-5 py-3">
      <span class="text-[11px]" style="color: #9a9898">v0.1.0</span>
      <button
        class="flex items-center gap-1 text-[11px] text-[#9a9898] hover:text-[#201d1d]"
        title="收起侧边栏"
        @click="emit('collapse')"
      >
        <PanelLeftClose :size="13" /> 收起
      </button>
    </div>
  </div>
</template>
