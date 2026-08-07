<script setup lang="ts">
/**
 * RegimeCard — 市场环境仪表盘（研究员的第一步：市场状态 + 风格轮动）
 * 数据：/api/regime/overview（本地指数日线缓存，无缓存时明确提示）
 */
import { onMounted, ref } from 'vue'
import { TrendingUp, TrendingDown, Activity } from 'lucide-vue-next'

interface RegimeData {
  ok: boolean
  message?: string
  data_date?: string
  indices?: {
    code: string
    name: string
    style: string
    state: string
    mom20: number
    mom60: number
    hv20: number
    price: number
    ma20: number
    ma60: number
  }[]
  style_rotation?: {
    label: string
    strength: number
    trend: string
    series?: { x: string[]; y: number[] }
  }[]
  market_state?: {
    label: string
    votes: Record<string, number>
    hv20_avg: number
    n_bull: number
    n_bear: number
  }
  missing?: (string | { code: string; name?: string; style?: string })[]
}

const data = ref<RegimeData | null>(null)
const loading = ref(true)

const STATE_COLORS: Record<string, string> = {
  牛: 'bg-[#ff3b30]/15 text-[#c62d23]',
  震荡偏多: 'bg-[#ff9f0a]/20 text-[#a05a00]',
  震荡: 'bg-[#646262]/10 text-[#646262]',
  震荡偏空: 'bg-[#30d158]/20 text-[#248a3d]',
  熊: 'bg-[#30d158]/15 text-[#248a3d]',
}

async function load() {
  loading.value = true
  try {
    const res = await fetch('/api/regime/overview')
    data.value = await res.json()
  } catch {
    data.value = { ok: false, message: '无法连接后端服务' }
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] p-4">
    <div class="mb-3 flex items-center justify-between">
      <div class="flex items-center gap-2">
        <Activity :size="14" class="text-[#646262]" />
        <h2 class="text-sm font-semibold text-[#201d1d]">市场环境</h2>
        <span v-if="data?.data_date" class="text-[11px] text-[#9a9898]">数据截至 {{ data.data_date }}</span>
      </div>
      <button
        type="button"
        class="cursor-pointer rounded-[4px] border border-[rgba(15,0,0,0.12)] px-2 py-1 text-[11px] text-[#646262] transition-colors hover:text-[#201d1d]"
        :disabled="loading"
        @click="load"
      >
        ↻ 刷新
      </button>
    </div>

    <div v-if="loading" class="py-6 text-center text-xs text-[#9a9898]">加载中...</div>

    <div v-else-if="!data?.ok" class="rounded-[4px] border border-[#ff9f0a]/40 bg-[#ff9f0a]/8 px-3 py-2 text-[11px] leading-relaxed text-[#8a5a00]">
      {{ data?.message || '暂无指数数据' }}
      <div v-if="data?.missing?.length" class="mt-1 font-mono text-[10px] opacity-80">
        {{ data.missing.map((m) => (typeof m === 'string' ? m : m.code)).join(' / ') }}
      </div>
    </div>

    <template v-else>
      <!-- 市场综合状态 -->
      <div class="mb-3 flex flex-wrap items-center gap-2">
        <span class="rounded-[4px] px-2.5 py-1 text-xs font-semibold" :class="STATE_COLORS[data.market_state?.label ?? '震荡'] ?? STATE_COLORS['震荡']">
          {{ data.market_state?.label }}
        </span>
        <span class="text-[11px] text-[#646262]">
          {{ data.market_state?.n_bull }} 偏多 / {{ data.market_state?.n_bear }} 偏空 ·
          波动率均值 {{ ((data.market_state?.hv20_avg ?? 0) * 100).toFixed(0) }}%
        </span>
      </div>

      <!-- 宽基状态表 -->
      <div class="mb-3 grid grid-cols-2 gap-1.5 sm:grid-cols-3 lg:grid-cols-5">
        <div
          v-for="i in data.indices"
          :key="i.code"
          class="rounded-[4px] border border-[rgba(15,0,0,0.1)] bg-[#f8f7f7] px-2 py-1.5"
        >
          <div class="flex items-center justify-between">
            <span class="text-[11px] font-medium text-[#201d1d]">{{ i.name }}</span>
            <span class="rounded-[2px] px-1 py-px text-[9px] font-medium" :class="STATE_COLORS[i.state] ?? ''">{{ i.state }}</span>
          </div>
          <div class="mt-0.5 flex items-center gap-1 font-mono text-[10px] text-[#646262]">
            <span :class="i.mom20 >= 0 ? 'text-[#c62d23]' : 'text-[#248a3d]'">{{ (i.mom20 * 100).toFixed(1) }}%</span>
            <span class="text-[#9a9898]">20日</span>
            <span :class="i.mom60 >= 0 ? 'text-[#c62d23]' : 'text-[#248a3d]'">{{ (i.mom60 * 100).toFixed(1) }}%</span>
            <span class="text-[#9a9898]">60日</span>
          </div>
        </div>
      </div>

      <!-- 风格轮动 -->
      <div v-if="data.style_rotation?.length" class="flex flex-wrap gap-2">
        <div
          v-for="s in data.style_rotation"
          :key="s.label"
          class="flex items-center gap-1.5 rounded-[4px] border border-[rgba(15,0,0,0.1)] bg-[#f8f7f7] px-2 py-1.5"
        >
          <span class="text-[11px] text-[#646262]">{{ s.label }}</span>
          <span
            class="flex items-center gap-0.5 font-mono text-[11px] font-semibold"
            :class="s.strength > 0 ? 'text-[#c62d23]' : 'text-[#248a3d]'"
          >
            <TrendingUp v-if="s.strength > 0" :size="11" />
            <TrendingDown v-else :size="11" />
            {{ (s.strength * 100).toFixed(1) }}%
          </span>
        </div>
      </div>
    </template>
  </div>
</template>
