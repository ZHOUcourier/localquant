<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  Search,
  Star,
  Trash2,
  Eye,
  Copy,
  Plus,
  FolderOpen,
  Download,
  CheckSquare,
  Square,
  X,
} from 'lucide-vue-next'
import {
  useWorkflows,
  useDeleteWorkflow,
  useWorkflowTemplates,
  useToggleFavorite,
} from '@/composables/useWorkflow'
import { useQueryClient } from '@tanstack/vue-query'
import { Input, Button, Badge, Dialog, ConfirmDialog } from '@/components/ui'

type TabKey = 'preset' | 'my' | 'favorite'

const TABS: { key: TabKey; label: string }[] = [
  { key: 'preset', label: '[+] 预置模板' },
  { key: 'my', label: '[+] 我创建的' },
  { key: 'favorite', label: '[+] 收藏' },
]

const router = useRouter()
const queryClient = useQueryClient()
const activeTab = ref<TabKey>('my')
const search = ref('')
const showCreateDialog = ref(false)
const deleteConfirm = ref<string | null>(null)
// 批量管理
const batchMode = ref(false)
const selected = ref<Set<string>>(new Set())
const batchDeleteConfirm = ref(false)
const batchBusy = ref(false)

const { data: workflows, isLoading } = useWorkflows(activeTab, search)
const { data: templates } = useWorkflowTemplates()
const deleteMutation = useDeleteWorkflow()
const toggleFavorite = useToggleFavorite()

// 新建/用模板：只打开编辑器（ComfyUI iframe），用户在编辑器内保存
function handleCreateNew() {
  showCreateDialog.value = false
  router.push('/workflow/new')
}

function handleCreateFromTemplate(templateId: string) {
  showCreateDialog.value = false
  router.push(`/workflow/new?template=${encodeURIComponent(templateId)}`)
}

// 批量选择
function toggleSelect(id: string) {
  const next = new Set(selected.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selected.value = next
}

const allSelected = computed(
  () =>
    !!workflows.value &&
    workflows.value.length > 0 &&
    workflows.value.every((w) => selected.value.has(w.id)),
)
function toggleSelectAll() {
  if (!workflows.value) return
  selected.value = allSelected.value ? new Set() : new Set(workflows.value.map((w) => w.id))
}

function exitBatchMode() {
  batchMode.value = false
  selected.value = new Set()
}

// 批量导出：拉取详情后合并为一个 JSON 文件（可直接导入）
async function handleBatchExport() {
  if (selected.value.size === 0) return
  batchBusy.value = true
  try {
    const details = await Promise.all(
      [...selected.value].map((id) => fetch(`/api/workflow/${id}`).then((r) => r.json())),
    )
    const payload = {
      workflows: details.map((d) => ({
        name: d.name,
        description: d.description || '',
        nodes: d.nodes || [],
        links: d.links || [],
      })),
    }
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `workflows-${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
  } finally {
    batchBusy.value = false
  }
}

// 批量删除
async function handleBatchDelete() {
  batchBusy.value = true
  try {
    await Promise.all(
      [...selected.value].map((id) => fetch(`/api/workflow/${id}`, { method: 'DELETE' })),
    )
    queryClient.invalidateQueries({ queryKey: ['workflows'] })
    exitBatchMode()
  } finally {
    batchBusy.value = false
    batchDeleteConfirm.value = false
  }
}

function handleDeleteConfirm() {
  if (deleteConfirm.value) {
    deleteMutation.mutate(deleteConfirm.value)
    deleteConfirm.value = null
  }
}

function handleRowClick(wf: { id: string }) {
  if (batchMode.value && activeTab.value !== 'preset') {
    toggleSelect(wf.id)
  } else if (activeTab.value === 'preset') {
    handleCreateFromTemplate(wf.id)
  } else {
    router.push(`/workflow/${wf.id}`)
  }
}

function formatTime(ts: number) {
  const d = new Date(ts * 1000)
  const now = new Date()
  const diffMs = now.getTime() - d.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return '刚刚'
  if (diffMin < 60) return `${diffMin} 分钟前`
  const diffHr = Math.floor(diffMin / 60)
  if (diffHr < 24) return `${diffHr} 小时前`
  const diffDay = Math.floor(diffHr / 24)
  if (diffDay < 7) return `${diffDay} 天前`
  return d.toLocaleDateString('zh-CN')
}

function nodeCount(wf: Record<string, unknown>): number {
  if ('node_count' in wf && wf.node_count != null) return Number(wf.node_count)
  const nodes = wf.nodes as unknown[] | undefined
  return nodes?.length ?? 0
}
</script>

<template>
  <div class="min-h-full bg-[#fdfcfc] font-mono">
    <div class="mx-auto max-w-[960px] px-6 py-8">
      <!-- 顶部标题栏 -->
      <div class="mb-6 flex items-center justify-between">
        <h1 class="text-[20px] font-bold text-[#201d1d]">[+] 工作流</h1>
        <div class="flex items-center gap-2">
          <Button
            v-if="activeTab !== 'preset' && !batchMode"
            variant="secondary"
            size="sm"
            class="flex items-center gap-1.5"
            @click="batchMode = true"
          >
            <CheckSquare :size="14" />
            批量管理
          </Button>
          <Button
            variant="primary"
            size="sm"
            class="flex items-center gap-1.5"
            @click="showCreateDialog = true"
          >
            <Plus :size="14" />
            创建工作流
          </Button>
        </div>
      </div>

      <!-- Tab 导航 -->
      <div class="mb-4 flex gap-0" style="border-bottom: 1px solid rgba(15, 0, 0, 0.12)">
        <button
          v-for="tab in TABS"
          :key="tab.key"
          type="button"
          class="relative cursor-pointer px-4 py-2 text-sm font-medium transition-colors"
          :class="activeTab === tab.key ? 'text-[#201d1d]' : 'text-[#646262] hover:text-[#201d1d]'"
          @click="activeTab = tab.key"
        >
          {{ tab.label }}
          <span
            v-if="activeTab === tab.key"
            class="absolute bottom-0 left-0 right-0 h-[2px] bg-[#9a9898]"
          />
        </button>
      </div>

      <!-- 搜索框 -->
      <div v-if="activeTab !== 'preset'" class="mb-4">
        <div class="w-full max-w-[320px]">
          <Input v-model="search" placeholder="搜索工作流名称...">
            <template #prefix><Search :size="14" /></template>
          </Input>
        </div>
      </div>

      <!-- 批量操作栏 -->
      <div
        v-if="batchMode && activeTab !== 'preset'"
        class="mb-4 flex items-center gap-2 rounded-[4px] bg-[#f8f7f7] px-3 py-2"
        style="border: 1px solid rgba(15, 0, 0, 0.12)"
      >
        <button
          type="button"
          class="flex cursor-pointer items-center gap-1.5 text-xs text-[#201d1d]"
          @click="toggleSelectAll"
        >
          <CheckSquare v-if="allSelected" :size="14" />
          <Square v-else :size="14" />
          全选
        </button>
        <span class="text-xs text-[#646262]">已选 {{ selected.size }} 项</span>
        <div class="flex-1" />
        <Button
          variant="secondary"
          size="sm"
          :disabled="selected.size === 0 || batchBusy"
          class="flex items-center gap-1 text-xs"
          @click="handleBatchExport"
        >
          <Download :size="12" />
          导出选中 ({{ selected.size }})
        </Button>
        <Button
          variant="danger"
          size="sm"
          :disabled="selected.size === 0 || batchBusy"
          class="flex items-center gap-1 text-xs"
          @click="batchDeleteConfirm = true"
        >
          <Trash2 :size="12" />
          删除选中 ({{ selected.size }})
        </Button>
        <Button variant="ghost" size="sm" class="flex items-center gap-1 text-xs" @click="exitBatchMode">
          <X :size="12" />
          退出
        </Button>
      </div>

      <!-- 加载中 -->
      <div v-if="isLoading" class="py-16 text-center text-sm text-[#646262]">加载中...</div>

      <!-- 空状态 -->
      <div
        v-if="!isLoading && (!workflows || workflows.length === 0)"
        class="flex flex-col items-center justify-center py-20"
      >
        <div class="mb-4 text-[#9a9898]">
          <FolderOpen :size="40" />
        </div>
        <p class="mb-2 text-sm text-[#424245]">
          <template v-if="activeTab === 'preset'">暂无预置模板</template>
          <template v-if="activeTab === 'my'">还没有工作流</template>
          <template v-if="activeTab === 'favorite'">还没有收藏的工作流</template>
        </p>
        <Button v-if="activeTab === 'my'" variant="primary" size="sm" @click="showCreateDialog = true">
          创建第一个工作流
        </Button>
      </div>

      <!-- 表格视图 -->
      <div
        v-if="!isLoading && workflows && workflows.length > 0"
        class="overflow-hidden rounded-[4px]"
        style="border: 1px solid rgba(15, 0, 0, 0.12)"
      >
        <table class="w-full border-collapse text-sm">
          <thead>
            <tr class="bg-[#f8f7f7]">
              <th
                v-if="batchMode && activeTab !== 'preset'"
                class="px-4 py-2.5"
                style="border-bottom: 1px solid rgba(15, 0, 0, 0.12); width: 40px"
              />
              <th class="px-4 py-2.5 text-left text-xs font-medium text-[#646262]" style="border-bottom: 1px solid rgba(15, 0, 0, 0.12)">
                名称
              </th>
              <th class="px-4 py-2.5 text-left text-xs font-medium text-[#646262]" style="border-bottom: 1px solid rgba(15, 0, 0, 0.12)">
                描述
              </th>
              <th
                v-if="activeTab === 'preset'"
                class="px-4 py-2.5 text-left text-xs font-medium text-[#646262]"
                style="border-bottom: 1px solid rgba(15, 0, 0, 0.12); width: 80px"
              >
                节点数
              </th>
              <th class="px-4 py-2.5 text-left text-xs font-medium text-[#646262]" style="border-bottom: 1px solid rgba(15, 0, 0, 0.12); width: 120px">
                更新时间
              </th>
              <th class="px-4 py-2.5 text-right text-xs font-medium text-[#646262]" style="border-bottom: 1px solid rgba(15, 0, 0, 0.12); width: 140px">
                操作
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="wf in workflows"
              :key="wf.id"
              class="cursor-pointer transition-colors hover:bg-[#f1eeee]"
              @click="handleRowClick(wf)"
            >
              <!-- 批量选择 -->
              <td
                v-if="batchMode && activeTab !== 'preset'"
                class="px-4 py-3"
                style="border-bottom: 1px solid rgba(15, 0, 0, 0.08)"
              >
                <CheckSquare v-if="selected.has(wf.id)" :size="15" class="text-[#201d1d]" />
                <Square v-else :size="15" class="text-[#9a9898]" />
              </td>
              <!-- 名称 -->
              <td class="px-4 py-3 text-[#201d1d] font-medium" style="border-bottom: 1px solid rgba(15, 0, 0, 0.08)">
                <div class="flex items-center gap-2">
                  <Star v-if="wf.is_favorite" :size="12" class="fill-[#ff9f0a] text-[#ff9f0a] flex-shrink-0" />
                  <span class="truncate">{{ wf.name }}</span>
                </div>
              </td>
              <!-- 描述 -->
              <td class="px-4 py-3 text-[#646262] text-xs" style="border-bottom: 1px solid rgba(15, 0, 0, 0.08)">
                <div class="truncate max-w-[280px]">{{ wf.description || '—' }}</div>
              </td>
              <!-- 节点数 (preset only) -->
              <td
                v-if="activeTab === 'preset'"
                class="px-4 py-3 text-[#646262] text-xs"
                style="border-bottom: 1px solid rgba(15, 0, 0, 0.08)"
              >
                <Badge variant="default">{{ nodeCount(wf as unknown as Record<string, unknown>) }}</Badge>
              </td>
              <!-- 更新时间 -->
              <td class="px-4 py-3 text-[#646262] text-xs" style="border-bottom: 1px solid rgba(15, 0, 0, 0.08)">
                {{ wf.updated_at ? formatTime(wf.updated_at) : '—' }}
              </td>
              <!-- 操作 -->
              <td class="px-4 py-3 text-right" style="border-bottom: 1px solid rgba(15, 0, 0, 0.08)">
                <div class="flex items-center justify-end gap-1">
                  <template v-if="activeTab !== 'preset'">
                    <!-- 查看 -->
                    <button
                      class="rounded-[4px] p-1.5 text-[#646262] transition-colors hover:bg-[#f1eeee] hover:text-[#201d1d]"
                      title="查看"
                      @click.stop="router.push(`/workflow/${wf.id}`)"
                    >
                      <Eye :size="14" />
                    </button>
                    <!-- 收藏 -->
                    <button
                      class="rounded-[4px] p-1.5 transition-colors"
                      :class="
                        wf.is_favorite
                          ? 'text-[#ff9f0a] hover:bg-[#ff9f0a]/10'
                          : 'text-[#646262] hover:bg-[#f1eeee] hover:text-[#ff9f0a]'
                      "
                      :title="wf.is_favorite ? '取消收藏' : '收藏'"
                      @click.stop="toggleFavorite.mutate(wf.id)"
                    >
                      <Star :size="14" :class="wf.is_favorite ? 'fill-current' : ''" />
                    </button>
                    <!-- 删除 -->
                    <button
                      class="rounded-[4px] p-1.5 text-[#646262] transition-colors hover:bg-[#f1eeee] hover:text-[#ff3b30]"
                      title="删除"
                      @click.stop="deleteConfirm = wf.id"
                    >
                      <Trash2 :size="14" />
                    </button>
                  </template>
                  <Button
                    v-if="activeTab === 'preset'"
                    variant="secondary"
                    size="sm"
                    class="flex items-center gap-1 text-xs"
                    @click.stop="handleCreateFromTemplate(wf.id)"
                  >
                    <Copy :size="12" />
                    使用
                  </Button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 删除确认对话框 -->
    <ConfirmDialog
      :open="!!deleteConfirm"
      title="[-] 删除工作流"
      message="确定要删除这个工作流吗？此操作不可撤销。"
      confirm-text="删除"
      cancel-text="取消"
      variant="danger"
      @confirm="handleDeleteConfirm"
      @cancel="deleteConfirm = null"
    />

    <!-- 批量删除确认 -->
    <ConfirmDialog
      :open="batchDeleteConfirm"
      title="[-] 批量删除工作流"
      :message="`确定要删除选中的 ${selected.size} 个工作流吗？此操作不可撤销。`"
      confirm-text="删除"
      cancel-text="取消"
      variant="danger"
      @confirm="handleBatchDelete"
      @cancel="batchDeleteConfirm = false"
    />

    <!-- 创建工作流模态框 -->
    <Dialog :open="showCreateDialog" title="[+] 创建工作流" @close="showCreateDialog = false">
      <div class="space-y-4" style="width: 480px">
        <!-- 创建空白工作流 -->
        <div
          class="cursor-pointer rounded-[4px] p-4 transition-colors hover:bg-[#f8f7f7]"
          style="border: 1px solid rgba(15, 0, 0, 0.12)"
          @click="handleCreateNew"
        >
          <div class="flex items-center gap-3">
            <div class="flex h-8 w-8 items-center justify-center rounded-[4px] bg-[#f1eeee]">
              <Plus :size="16" class="text-[#201d1d]" />
            </div>
            <div>
              <div class="text-sm font-medium text-[#201d1d]">空白工作流</div>
              <div class="text-xs text-[#646262]">从零开始创建一个新工作流</div>
            </div>
          </div>
        </div>

        <!-- 分隔线 -->
        <div class="text-xs font-medium text-[#646262]">从模板创建</div>

        <!-- 模板列表 -->
        <div class="space-y-2 max-h-[320px] overflow-y-auto">
          <template v-if="templates && templates.length > 0">
            <div
              v-for="t in templates"
              :key="t.id"
              class="cursor-pointer rounded-[4px] p-3 transition-colors hover:bg-[#f8f7f7]"
              style="border: 1px solid rgba(15, 0, 0, 0.12)"
              @click="handleCreateFromTemplate(t.id)"
            >
              <div class="flex items-start justify-between">
                <div class="flex-1 min-w-0">
                  <div class="text-sm font-medium text-[#201d1d]">{{ t.name }}</div>
                  <div class="mt-1 text-xs text-[#646262] line-clamp-2">
                    {{ t.description || '暂无描述' }}
                  </div>
                </div>
                <Badge variant="default" class="ml-2 flex-shrink-0">{{ t.nodes?.length ?? 0 }} 节点</Badge>
              </div>
            </div>
          </template>
          <div v-else class="py-4 text-center text-xs text-[#9a9898]">暂无可用模板</div>
        </div>
      </div>
    </Dialog>
  </div>
</template>
