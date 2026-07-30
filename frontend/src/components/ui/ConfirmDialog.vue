<script setup lang="ts">
import Dialog from './Dialog.vue'
import Button from './Button.vue'

withDefaults(
  defineProps<{
    open: boolean
    title: string
    message: string
    confirmText?: string
    cancelText?: string
    variant?: 'danger' | 'default'
  }>(),
  { confirmText: '确认', cancelText: '取消', variant: 'default' },
)

const emit = defineEmits<{ confirm: []; cancel: [] }>()
</script>

<template>
  <Dialog :open="open" :title="title" @close="emit('cancel')">
    <span style="color: #424245">{{ message }}</span>
    <template #footer>
      <Button variant="secondary" @click="emit('cancel')">{{ cancelText }}</Button>
      <Button :variant="variant === 'danger' ? 'danger' : 'primary'" @click="emit('confirm')">
        {{ confirmText }}
      </Button>
    </template>
  </Dialog>
</template>
