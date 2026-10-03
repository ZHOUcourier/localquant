<script setup lang="ts">
/**
 * SkillParamsDialog — 带参数技能的填参弹窗
 *
 * 用户技能声明了参数（{{name}} 占位符）时，「在 QUBE 中使用」先弹此表单：
 * 填参 → 实时预览渲染结果 → 确认后把最终 prompt 交给父组件预填 QUBE 输入框。
 */
import { computed, reactive, ref, watch } from 'vue'
import { Dialog, Input, Select } from '@/components/ui'
import type { SelectOption } from '@/components/ui'
import { renderSkillPrompt } from '@/components/qube/types'
import type { Skill, SkillParam } from '@/components/qube/types'

const props = defineProps<{ skill: Skill }>()
const emit = defineEmits<{ close: []; confirm: [prompt: string] }>()

const values = reactive<Record<string, string>>({})
const error = ref('')

watch(
  () => props.skill,
  (s) => {
    for (const key of Object.keys(values)) delete values[key]
    for (const p of s.params) values[p.name] = p.default || ''
  },
  { immediate: true },
)

const rendered = computed(() => renderSkillPrompt(props.skill.prompt, values))

function optionList(p: SkillParam): SelectOption[] {
  return p.options.map((o) => ({ value: o, label: o }))
}

// 字面 {{name}} 占位符展示（放函数里避免与模板插值语法冲突）
function ph(p: SkillParam): string {
  return '{{' + p.name + '}}'
}

function submit() {
  const missing = props.skill.params.find((p) => p.required && !(values[p.name] || '').trim())
  if (missing) {
    error.value = `请填写「${missing.label}」`
    return
  }
  error.value = ''
  emit('confirm', rendered.value)
}
</script>

<template>
  <Dialog :open="true" :title="`使用技能 · ${skill.display_name}`" @close="emit('close')">
    <div class="space-y-3">
      <p v-if="skill.description" class="text-xs leading-relaxed text-[#646262]">
        {{ skill.description }}
      </p>
      <div v-for="p in skill.params" :key="p.name">
        <label class="mb-1.5 block text-[13px] font-medium text-[#201d1d]">
          {{ p.label }}
          <span class="ml-1 font-mono text-[10px] font-normal text-[#9a9898]">{{ ph(p) }}</span>
          <span v-if="p.required" class="ml-1 text-[#ff3b30]">*</span>
        </label>
        <Select
          v-if="p.type === 'select'"
          v-model="values[p.name]"
          :options="optionList(p)"
          :placeholder="p.placeholder || '请选择'"
        />
        <Input
          v-else
          v-model="values[p.name]"
          :type="p.type === 'number' ? 'number' : 'text'"
          :placeholder="p.placeholder || (p.default ? `默认：${p.default}` : '')"
        />
      </div>
      <div>
        <label class="mb-1 block text-[11px] text-[#9a9898]">发送内容预览</label>
        <div
          class="max-h-32 overflow-y-auto whitespace-pre-wrap rounded-[4px] border border-[rgba(15,0,0,0.1)] bg-[#f8f7f7] px-2.5 py-1.5 text-[11px] leading-relaxed text-[#646262]"
        >
          {{ rendered }}
        </div>
      </div>
      <div v-if="error" class="text-[11px] text-[#ff3b30]">{{ error }}</div>
    </div>
    <template #footer>
      <button
        class="rounded-[4px] border border-[rgba(15,0,0,0.15)] px-3 py-1.5 text-xs text-[#646262]"
        @click="emit('close')"
      >
        取消
      </button>
      <button
        class="rounded-[4px] bg-[#201d1d] px-3 py-1.5 text-xs text-[#fdfcfc] hover:opacity-85"
        @click="submit"
      >
        填参并在 QUBE 中使用
      </button>
    </template>
  </Dialog>
</template>
