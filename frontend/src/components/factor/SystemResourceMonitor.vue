<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { Cpu, MemoryStick, HardDrive, Zap } from 'lucide-vue-next'

/** 后端 /api/system/resources 返回结构 */
interface Resources {
  cpu: { per_core: number[]; count: number; avg: number; freq_mhz: number | null }
  memory: {
    physical: { used: number; total: number; percent: number }
    virtual: { used: number; total: number; percent: number }
  }
  disk: {
    cache: number
    outputs: number
    experiments: number
    factor_total: number
    device: { total: number; used: number; free: number; percent: number }
  }
  gpu: {
    available: boolean
    reason?: string
    gpus?: { name: string; util: number; mem_used_mb: number; mem_total_mb: number; temperature: number | null }[]
  }
}

function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let v = n / 1024
  let i = 0
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i++
  }
  return `${v.toFixed(v >= 100 ? 0 : 1)} ${units[i]}`
}

/** 用量 → 颜色（低=绿, 中=琥珀, 高=红） */
function levelColor(pct: number): string {
  if (pct >= 85) return '#ff3b30'
  if (pct >= 60) return '#ff9f0a'
  return '#30d158'
}

function clampPercent(percent: number): number {
  return Math.max(0, Math.min(100, percent))
}

const LABEL = 'text-[10px] uppercase tracking-wide text-[#9a9898]'
const SECTION = 'rounded-[4px] border border-[rgba(15,0,0,0.1)] bg-[#fdfcfc] p-3'

/**
 * 系统资源监控（CPU 分核心 / 内存物理+虚拟 / 磁盘因子占用 / GPU）
 * — opencode 浅色风格，图形化直观展示，每 2s 轮询一次。
 */
const res = ref<Resources | null>(null)
const error = ref<string | null>(null)
let timer: ReturnType<typeof setInterval> | undefined

async function tick() {
  try {
    const r = await fetch('/api/system/resources')
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    res.value = await r.json()
    error.value = null
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}

onMounted(() => {
  tick()
  timer = setInterval(tick, 2000)
})
onUnmounted(() => clearInterval(timer))

function diskSeg(v: number): string {
  const total = res.value?.disk.factor_total || 1
  return `${(v / total) * 100}%`
}
</script>

<template>
  <div class="flex h-full flex-col gap-3 overflow-auto">
    <div class="flex items-center justify-between">
      <h2 class="text-sm font-semibold text-[#201d1d]">系统资源</h2>
      <span class="flex items-center gap-1 text-[10px] text-[#9a9898]">
        <span class="h-1.5 w-1.5 rounded-full" :style="{ background: error ? '#ff3b30' : '#30d158' }" />
        {{ error ? '连接中断' : '实时 · 2s' }}
      </span>
    </div>

    <div v-if="!res" class="flex flex-1 items-center justify-center text-xs text-[#646262]">
      {{ error ? `资源读取失败: ${error}` : '读取系统资源中...' }}
    </div>

    <template v-else>
      <!-- CPU：每核心竖条 -->
      <div :class="SECTION">
        <div class="mb-2 flex items-center justify-between">
          <span class="flex items-center gap-1.5 text-xs font-medium text-[#201d1d]"><Cpu :size="13" /> CPU</span>
          <span class="font-mono text-xs text-[#646262]">
            {{ res.cpu.count }} 核 · 均
            <span :style="{ color: levelColor(res.cpu.avg) }">{{ res.cpu.avg }}%</span>
            {{ res.cpu.freq_mhz ? ` · ${(res.cpu.freq_mhz / 1000).toFixed(1)}GHz` : '' }}
          </span>
        </div>
        <div class="flex items-end gap-1" style="height: 56px">
          <div
            v-for="(c, i) in res.cpu.per_core"
            :key="i"
            class="flex flex-1 flex-col items-center justify-end"
            :title="`核心 ${i}: ${c}%`"
          >
            <div class="flex w-full items-end justify-center overflow-hidden rounded-[2px] bg-[#f1eeee]" style="height: 44px">
              <div class="w-full transition-[height] duration-500" :style="{ height: `${Math.max(3, c)}%`, background: levelColor(c) }" />
            </div>
            <span class="mt-0.5 text-[9px] text-[#9a9898]">{{ i }}</span>
          </div>
        </div>
      </div>

      <!-- 内存：物理 + 虚拟 -->
      <div :class="SECTION">
        <div class="mb-2 flex items-center gap-1.5 text-xs font-medium text-[#201d1d]"><MemoryStick :size="13" /> 内存</div>
        <div class="space-y-2.5">
          <div>
            <div class="mb-1 flex items-center justify-between">
              <span :class="LABEL">物理内存</span>
              <span class="font-mono text-[10px] text-[#646262]">
                {{ fmtBytes(res.memory.physical.used) }} / {{ fmtBytes(res.memory.physical.total) }} · {{ res.memory.physical.percent }}%
              </span>
            </div>
            <div class="h-2 w-full overflow-hidden rounded-full bg-[#f1eeee]">
              <div
                class="h-full rounded-full transition-[width] duration-500"
                :style="{ width: `${clampPercent(res.memory.physical.percent)}%`, background: levelColor(res.memory.physical.percent) }"
              />
            </div>
          </div>
          <div>
            <div class="mb-1 flex items-center justify-between">
              <span :class="LABEL">虚拟内存 (交换)</span>
              <span class="font-mono text-[10px] text-[#646262]">
                {{ fmtBytes(res.memory.virtual.used) }} / {{ fmtBytes(res.memory.virtual.total) }} · {{ res.memory.virtual.percent }}%
              </span>
            </div>
            <div class="h-2 w-full overflow-hidden rounded-full bg-[#f1eeee]">
              <div
                class="h-full rounded-full transition-[width] duration-500"
                :style="{ width: `${clampPercent(res.memory.virtual.percent)}%`, background: levelColor(res.memory.virtual.percent) }"
              />
            </div>
          </div>
        </div>
      </div>

      <!-- 磁盘：因子运算占用 -->
      <div :class="SECTION">
        <div class="mb-2 flex items-center justify-between">
          <span class="flex items-center gap-1.5 text-xs font-medium text-[#201d1d]"><HardDrive :size="13" /> 磁盘 · 因子运算占用</span>
          <span class="font-mono text-sm font-semibold text-[#201d1d]">{{ fmtBytes(res.disk.factor_total) }}</span>
        </div>
        <div v-if="res.disk.factor_total > 0" class="mb-2 flex h-2 w-full overflow-hidden rounded-full bg-[#f1eeee]">
          <div :style="{ width: diskSeg(res.disk.cache), background: '#007aff' }" />
          <div :style="{ width: diskSeg(res.disk.outputs), background: '#bf5af2' }" />
          <div :style="{ width: diskSeg(res.disk.experiments), background: '#30d158' }" />
        </div>
        <div class="flex flex-wrap gap-x-4 gap-y-1 font-mono text-[10px] text-[#646262]">
          <span><span class="mr-1 inline-block h-2 w-2 rounded-[2px] align-middle" style="background: #007aff" />缓存 {{ fmtBytes(res.disk.cache) }}</span>
          <span><span class="mr-1 inline-block h-2 w-2 rounded-[2px] align-middle" style="background: #bf5af2" />产物 {{ fmtBytes(res.disk.outputs) }}</span>
          <span><span class="mr-1 inline-block h-2 w-2 rounded-[2px] align-middle" style="background: #30d158" />实验 {{ fmtBytes(res.disk.experiments) }}</span>
        </div>
        <div class="mt-1.5 text-[10px] text-[#9a9898]">
          本盘剩余 {{ fmtBytes(res.disk.device.free) }} / {{ fmtBytes(res.disk.device.total) }}
        </div>
      </div>

      <!-- GPU -->
      <div :class="SECTION">
        <div class="mb-2 flex items-center gap-1.5 text-xs font-medium text-[#201d1d]"><Zap :size="13" /> GPU</div>
        <div v-if="res.gpu.available && res.gpu.gpus" class="space-y-2.5">
          <div v-for="(g, i) in res.gpu.gpus" :key="i">
            <div class="mb-1 flex items-center justify-between">
              <span class="text-[11px] text-[#424245]">{{ g.name }}{{ g.temperature != null ? ` · ${g.temperature}°C` : '' }}</span>
              <span class="font-mono text-[10px] text-[#646262]">
                {{ fmtBytes(g.mem_used_mb * 1024 * 1024) }} / {{ fmtBytes(g.mem_total_mb * 1024 * 1024) }} · {{ g.util }}%
              </span>
            </div>
            <div class="h-2 w-full overflow-hidden rounded-full bg-[#f1eeee]">
              <div
                class="h-full rounded-full transition-[width] duration-500"
                :style="{ width: `${clampPercent(g.util)}%`, background: levelColor(g.util) }"
              />
            </div>
          </div>
        </div>
        <div v-else class="text-[11px] leading-relaxed text-[#9a9898]">{{ res.gpu.reason || '未检测到 GPU' }}</div>
      </div>
    </template>
  </div>
</template>
