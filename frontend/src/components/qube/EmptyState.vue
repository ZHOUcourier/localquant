<script setup lang="ts">
/**
 * EmptyState — 新会话空态起始页（复刻 1355：逐字标题动画 + 模板卡片组）
 * 删除期货组；分组色点用 opencode 语义色 accent/warning/danger。
 */
const emit = defineEmits<{ pick: [prompt: string] }>()

const TITLE = '想从哪儿开始？'

interface TplCard {
  title: string
  desc: string
  market?: string
  prompt: string
}
interface TplGroup {
  name: string
  desc: string
  color: string
  cards: TplCard[]
}

const GROUPS: TplGroup[] = [
  {
    name: '股票策略',
    desc: '写代码 → 回测 → 迭代',
    color: '#007aff',
    cards: [
      {
        title: '茅台 5/20 双均线',
        desc: '600519 单票双均线金叉死叉，入门验证回测链路',
        market: '股票',
        prompt:
          '帮我写一个贵州茅台(600519.SH)的 5/20 双均线策略：5 日均线上穿 20 日均线买入、下穿卖出，写入画板并运行回测。',
      },
      {
        title: '海龟突破 + ATR 止损',
        desc: '20 日新高突破入场，2×ATR 止损，10 日新低离场',
        market: '股票',
        prompt:
          '帮我实现海龟交易法则的股票版：20 日新高突破入场、2×ATR 止损、10 日新低离场，先写入画板再回测看效果。',
      },
      {
        title: '多均线趋势过滤',
        desc: '5/10/20/60 多头排列持有，破位清仓',
        market: '股票',
        prompt:
          '设计一个多均线趋势策略：5/10/20/60 日均线多头排列时持有，跌破 20 日均线清仓，写入画板并回测。',
      },
    ],
  },
  {
    name: '因子研究',
    desc: '建因子 → IC/分组分析',
    color: '#ff9f0a',
    cards: [
      {
        title: '20 日动量因子',
        desc: 'close/DELAY(close,20)-1，动量效应基准因子',
        market: '股票',
        prompt: '帮我创建一个 20 日动量因子（close/DELAY(close,20)-1），并运行因子分析看 IC 和分组收益。',
      },
      {
        title: '20 日波动率因子',
        desc: '低波动异象：STD(returns,20) 反向',
        market: '股票',
        prompt: '创建 20 日波动率因子（收益率 20 日标准差，方向取反做低波动），跑因子分析验证低波动异象。',
      },
      {
        title: '成交量变化因子',
        desc: '量能突增/萎缩的截面排名',
        market: '股票',
        prompt: '帮我建一个成交量变化因子：RANK(volume/MA(volume,20))，跑因子分析看看量能因子的有效性。',
      },
      {
        title: '量价相关性因子',
        desc: 'CORR(close, volume, 10) 量价背离',
        market: '股票',
        prompt: '创建量价相关性因子 -1*CORR(close,volume,10)，运行因子分析并解读结果。',
      },
      {
        title: '看看我的因子库',
        desc: '列出已有因子和最近分析指标',
        prompt: '列出我的所有因子，附上最近一次分析的 IC 和单调性，帮我点评哪些值得继续迭代。',
      },
    ],
  },
  {
    name: '常用工具',
    desc: '盘点资产与回测',
    color: '#ff3b30',
    cards: [
      {
        title: '看看我所有策略',
        desc: '策略清单 + 最近回测表现',
        prompt: '列出我的所有策略和最近一次回测的收益/夏普/回撤，帮我总结哪个最值得继续优化。',
      },
      {
        title: '在历史上跑一遍回测',
        desc: '对当前绑定策略执行全区间回测',
        prompt: '对当前画板绑定的策略，用本地数据的完整可用区间跑一遍回测，并解读关键指标。',
      },
      {
        title: '查查本地数据范围',
        desc: '可用股票数与日期区间',
        prompt: '查一下本地缓存行情的股票数量和日期区间，告诉我能支撑哪些类型的研究。',
      },
    ],
  },
]
</script>

<template>
  <div class="mx-auto w-full max-w-[56rem] space-y-4 px-4 py-8">
    <div>
      <p class="text-lg font-semibold text-[#201d1d]">
        <span
          v-for="(ch, i) in TITLE.split('')"
          :key="i"
          class="split-char"
          :style="{ '--i': i }"
          >{{ ch }}</span
        >
      </p>
      <p class="mt-1 text-xs text-[#9a9898]">
        点一张卡片我就接着办，或者直接在下面打字告诉我你的想法。
      </p>
    </div>

    <div class="space-y-5">
      <section v-for="g in GROUPS" :key="g.name" class="space-y-2.5">
        <div class="flex items-center gap-2">
          <span class="h-1.5 w-1.5 rounded-full" :style="{ background: g.color }" />
          <h3 class="text-xs font-semibold text-[#201d1d]">{{ g.name }}</h3>
          <span class="text-[10px] text-[#9a9898]">{{ g.desc }}</span>
          <span
            class="ml-auto rounded-full bg-[#f1eeee] px-1.5 py-0.5 font-mono text-[9px] text-[#646262]"
          >
            {{ g.cards.length }}
          </span>
        </div>
        <div class="grid gap-2.5" style="grid-template-columns: repeat(auto-fill, minmax(16rem, 1fr))">
          <div
            v-for="(c, ci) in g.cards"
            :key="c.title"
            class="anim-reveal-up h-24"
            :style="{ '--i': ci }"
          >
            <button
              class="card-hover group h-full w-full rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#fdfcfc] px-3 py-2.5 text-left"
              @click="emit('pick', c.prompt)"
            >
              <span class="flex items-center gap-1.5">
                <span class="line-clamp-1 text-[13px] font-medium text-[#201d1d]">{{ c.title }}</span>
                <span
                  v-if="c.market"
                  class="shrink-0 rounded-full px-1.5 text-[9px]"
                  :style="{ background: `${g.color}1a`, color: g.color }"
                >
                  {{ c.market }}
                </span>
              </span>
              <span class="mt-1 line-clamp-2 block text-[11px] leading-relaxed text-[#9a9898]">
                {{ c.desc }}
              </span>
            </button>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>
