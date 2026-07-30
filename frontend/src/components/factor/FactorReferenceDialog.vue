<script setup lang="ts">
/**
 * FactorReferenceDialog — 因子编写「变量与算子参考」
 *
 * 展示可用基础字段、算子函数分组与示例，与后端公式求值环境一致。
 * 让使用者知道公式/代码模式下可以用哪些变量与函数。
 */
import { computed, toRef } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { Dialog, Button } from '@/components/ui'

interface FactorField {
  name: string
  desc: string
  available: boolean
}
interface OperatorGroup {
  group: string
  ops: string[]
}
interface FactorReference {
  fields: FactorField[]
  operator_groups: OperatorGroup[]
  examples: { title: string; formula: string }[]
}

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: [] }>()

async function fetchReference(): Promise<FactorReference> {
  const res = await fetch('/api/factor/reference')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

const { data } = useQuery({
  queryKey: ['factor-reference'],
  queryFn: fetchReference,
  enabled: toRef(props, 'open'),
  staleTime: 10 * 60 * 1000,
})

const fields = computed(() => data.value?.fields ?? [])
const operatorGroups = computed(() => data.value?.operator_groups ?? [])
const examples = computed(() => data.value?.examples ?? [])
</script>

<template>
  <Dialog :open="open" title="因子编写 · 变量与算子参考" @close="emit('close')">
    <div class="flex max-h-[70vh] flex-col gap-4 overflow-auto text-xs" style="width: min(600px, 86vw)">
      <div class="rounded-[4px] bg-[#f8f7f7] px-3 py-2 leading-relaxed text-[#646262]">
        因子构建支持<b>公式</b>与<b>代码</b>两种方式，二者共用同一套字段与算子（大小写均可）。
        公式可直接在「因子构建（公式）」节点运行；代码方式把结果写入
        <code class="rounded bg-[#201d1d] px-1 text-[#fdfcfc]">factor_data</code>。
      </div>

      <!-- 基础字段 -->
      <section>
        <div class="mb-2 text-[13px] font-semibold text-[#201d1d]">基础字段</div>
        <div class="grid grid-cols-2 gap-1.5">
          <div
            v-for="f in fields"
            :key="f.name"
            class="flex items-center justify-between rounded-[4px] border border-[rgba(15,0,0,0.10)] bg-[#fdfcfc] px-2 py-1.5"
          >
            <span class="font-mono text-[#201d1d]">{{ f.name }}</span>
            <span class="flex items-center gap-1.5 text-[#646262]">
              {{ f.desc }}
              <span :class="f.available ? 'text-[#30d158]' : 'text-[#ff9f0a]'">
                {{ f.available ? '●' : '○' }}
              </span>
            </span>
          </div>
        </div>
        <div class="mt-1 text-[10px] text-[#9a9898]">● 本地可用　○ 需先下载对应数据</div>
      </section>

      <!-- 算子分组 -->
      <section>
        <div class="mb-2 text-[13px] font-semibold text-[#201d1d]">算子函数</div>
        <div class="flex flex-col gap-2">
          <div v-for="g in operatorGroups" :key="g.group">
            <div class="mb-1 text-[11px] font-medium text-[#646262]">{{ g.group }}</div>
            <div class="flex flex-wrap gap-1">
              <span
                v-for="op in g.ops"
                :key="op"
                class="rounded-[3px] border border-[rgba(15,0,0,0.10)] bg-[#f1eeee] px-1.5 py-0.5 font-mono text-[11px] text-[#201d1d]"
              >
                {{ op }}
              </span>
            </div>
          </div>
        </div>
      </section>

      <!-- 示例 -->
      <section>
        <div class="mb-2 text-[13px] font-semibold text-[#201d1d]">公式示例</div>
        <div class="flex flex-col gap-1.5">
          <div
            v-for="ex in examples"
            :key="ex.title"
            class="rounded-[4px] border border-[rgba(15,0,0,0.10)] overflow-hidden"
          >
            <div class="bg-[#f8f7f7] px-2 py-1 text-[11px] text-[#646262]">{{ ex.title }}</div>
            <pre class="overflow-auto bg-[#201d1d] px-2 py-1.5 font-mono text-[11px] text-[#fdfcfc]">{{ ex.formula }}</pre>
          </div>
        </div>
      </section>
    </div>

    <template #footer>
      <Button variant="secondary" @click="emit('close')">关闭</Button>
    </template>
  </Dialog>
</template>
