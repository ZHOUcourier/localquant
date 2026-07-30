<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

/** 后端 /api/data/ticker 返回结构 */
interface Quote {
  name: string
  code: string
  price?: number
  change?: number
  pct?: number
  amount?: number
  date?: string
  source: 'qmt' | 'cache' | 'none'
}

interface TickerResponse {
  qmt_connected: boolean
  quotes: Quote[]
}

/** 成交额（元）→ 「xxxx亿」 */
function fmtAmount(amount?: number): string {
  if (!amount || amount <= 0) return ''
  return `${(amount / 1e8).toFixed(0)}亿`
}

/** A 股配色：红涨绿跌 */
function pctColor(pct?: number): string {
  if (pct == null) return '#9a9898'
  if (pct > 0) return '#ff3b30'
  if (pct < 0) return '#30d158'
  return '#646262'
}

/** 资讯源标识 → 展示名 */
const NEWS_SOURCE_LABELS: Record<string, string> = {
  eastmoney: '东财快讯',
  sina: '新浪7×24',
}

/**
 * 底部状态栏（对标券商终端底栏）：
 * 上行滚动资讯（真实快讯源：东财/新浪 7×24，不可用时明确提示）、
 * 下行指数行情（QMT 实时优先，未连接回退本地缓存收盘价）+ QMT 连接状态。
 *
 * 资讯优先级：后端已将关联个股/重大事项的快讯置顶并标 important，前端红色 ● 高亮。
 * 滚动速度按内容总长度归一（恒定像素速度），避免条目多时“滚得太快”。
 */
interface NewsEntry {
  time: string
  text: string
  important: boolean
  url?: string
}

const ticker = ref<TickerResponse | null>(null)
const news = ref<NewsEntry[]>([])
const newsSource = ref('')
const newsError = ref<string | null>(null)
const paused = ref(false) // 停止滚动
const newsClosed = ref(false) // 关闭资讯行

let tickerTimer: ReturnType<typeof setInterval> | undefined
let newsTimer: ReturnType<typeof setInterval> | undefined

// 行情：15s 轮询
async function loadTicker() {
  try {
    const r = await fetch('/api/data/ticker')
    if (!r.ok) return
    ticker.value = await r.json()
  } catch {
    /* 后端离线时静默，Layout 已有离线提示条 */
  }
}

// 资讯：60s 轮询（后端同样有 60s 缓存）
async function loadNews() {
  try {
    const r = await fetch('/api/data/news')
    if (!r.ok) return
    const data = await r.json()
    // 优先用结构化 entries；旧版后端只有 items 时降级解析
    if (Array.isArray(data.entries) && data.entries.length) {
      news.value = data.entries
    } else if (Array.isArray(data.items)) {
      news.value = data.items.map((s: string) => {
        const m = /^(\d{2}:\d{2})\s+(.*)$/.exec(s)
        return m ? { time: m[1], text: m[2], important: false } : { time: '', text: s, important: false }
      })
    }
    newsSource.value = data.source || ''
    newsError.value = data.error || null
  } catch {
    /* ignore */
  }
}

onMounted(() => {
  loadTicker()
  tickerTimer = setInterval(loadTicker, 15000)
  loadNews()
  newsTimer = setInterval(loadNews, 60000)
})
onUnmounted(() => {
  clearInterval(tickerTimer)
  clearInterval(newsTimer)
})

const quotes = computed(() => ticker.value?.quotes?.filter((q) => q.source !== 'none') ?? [])
const cacheMode = computed(
  () => quotes.value.length > 0 && quotes.value.every((q) => q.source === 'cache'),
)
const newsLabel = computed(() =>
  NEWS_SOURCE_LABELS[newsSource.value] ? ` · ${NEWS_SOURCE_LABELS[newsSource.value]}` : '',
)
// 滚动时长 ∝ 内容总字符数（约 6px/字·每秒），下限 60s；保证无论条目多少都是恒定可读速度
const marqueeDuration = computed(() => {
  const chars = news.value.reduce((n, e) => n + e.text.length + 8, 0)
  return Math.max(60, Math.round(chars * 0.9))
})

// 点击资讯打开详情（新标签页）
function openDetail(e: NewsEntry) {
  if (e.url) window.open(e.url, '_blank', 'noopener')
}
</script>

<template>
  <div
    class="shrink-0 select-none font-mono"
    style="
      border-top: 1px solid rgba(15, 0, 0, 0.12);
      background: #f8f7f7;
      font-variant-numeric: tabular-nums;
    "
  >
    <!-- 第一行：资讯滚动（可暂停/关闭/点击详情） -->
    <div
      v-if="!newsClosed"
      class="flex items-center gap-2 overflow-hidden px-3"
      style="height: 24px; border-bottom: 1px solid rgba(15,0,0,0.08)"
    >
      <span
        class="shrink-0 rounded-[3px] px-1.5 text-[10px] font-semibold"
        style="background: rgba(0,122,255,0.1); color: #0056b3; line-height: 16px"
      >
        资讯{{ newsLabel }}
      </span>
      <!-- 暂停/继续 -->
      <button
        class="shrink-0 text-[11px] text-[#646262] hover:text-[#201d1d]"
        :title="paused ? '继续滚动' : '暂停滚动'"
        @click="paused = !paused"
      >
        {{ paused ? '▶' : '‖' }}
      </button>
      <div class="relative flex-1 overflow-hidden" style="height: 24px">
        <div
          v-if="news.length > 0"
          class="statusbar-marquee absolute flex items-center whitespace-nowrap"
          :style="{ lineHeight: '24px', animationDuration: `${marqueeDuration}s`, animationPlayState: paused ? 'paused' : 'running' }"
        >
          <!-- 内容双拷贝实现无缝循环；重要项红色 ● 高亮，时间灰色弱化；可点击看详情 -->
          <template v-for="pass in 2" :key="pass">
            <span
              v-for="(e, i) in news"
              :key="`${pass}-${i}`"
              class="mr-6 inline-flex items-center gap-1.5 text-[11px]"
              :class="e.url ? 'cursor-pointer hover:underline' : ''"
              :title="e.url ? '点击查看详情' : ''"
              @click="openDetail(e)"
            >
              <span v-if="e.important" class="text-[#ff3b30]">●</span>
              <span v-if="e.time" class="text-[#9a9898]">{{ e.time }}</span>
              <span :class="e.important ? 'font-medium text-[#d70015]' : 'text-[#424245]'">{{ e.text }}</span>
            </span>
          </template>
        </div>
        <span v-else class="text-[11px] text-[#9a9898]" style="line-height: 24px">
          {{ newsError || '资讯加载中...' }}
        </span>
      </div>
      <!-- 关闭资讯行 -->
      <button
        class="shrink-0 text-[12px] text-[#9a9898] hover:text-[#ff3b30]"
        title="关闭资讯"
        @click="newsClosed = true"
      >
        ✕
      </button>
    </div>
    <!-- 关闭后的细条：一键重新打开 -->
    <div
      v-else
      class="flex items-center px-3"
      style="height: 18px; border-bottom: 1px solid rgba(15,0,0,0.08)"
    >
      <button
        class="text-[10px] text-[#9a9898] hover:text-[#0056b3]"
        title="重新打开资讯"
        @click="newsClosed = false"
      >
        ▸ 资讯
      </button>
    </div>

    <!-- 第二行：指数行情 + QMT 状态 -->
    <div class="flex items-center gap-4 overflow-x-auto px-3" style="height: 26px">
      <span v-if="quotes.length === 0" class="text-[11px] text-[#9a9898]">
        暂无行情数据 — QMT 未连接且本地无指数缓存，请到「数据中心」下载指数 日线（如 000001.SH）
      </span>
      <span
        v-for="q in quotes"
        :key="q.code"
        class="flex shrink-0 items-baseline gap-1.5 text-[11px]"
        :title="`${q.code}${q.source === 'cache' ? `（本地缓存 ${q.date || ''} 收盘）` : '（QMT 实时）'}`"
      >
        <span class="text-[#424245]">{{ q.name }}</span>
        <span :style="{ color: pctColor(q.pct), fontWeight: 600 }">{{ q.price?.toFixed(2) }}</span>
        <span :style="{ color: pctColor(q.pct) }">
          {{ q.change != null && q.change > 0 ? '+' : '' }}{{ q.change?.toFixed(2) }}
        </span>
        <span :style="{ color: pctColor(q.pct) }">
          {{ q.pct != null && q.pct > 0 ? '+' : '' }}{{ q.pct?.toFixed(2) }}%
        </span>
        <span v-if="fmtAmount(q.amount)" class="text-[#9a9898]">{{ fmtAmount(q.amount) }}</span>
      </span>
      <div class="flex-1" />
      <span v-if="cacheMode" class="shrink-0 text-[10px] text-[#cc7f08]">
        本地缓存收盘价（非实时）
      </span>
      <span class="flex shrink-0 items-center gap-1.5 text-[11px] text-[#646262]">
        <span
          class="inline-block h-1.5 w-1.5 rounded-full"
          :style="{ background: ticker?.qmt_connected ? '#30d158' : '#9a9898' }"
        />
        {{ ticker?.qmt_connected ? 'QMT 已连接' : 'QMT 未连接' }}
      </span>
    </div>
  </div>
</template>
