<script setup lang="ts">
// フォーム上部のエラー要約(DS 4.6): 件数つきで、各項目へのリンクを並べる。`role="alert"`。
// 送信時にフォーカスを移す(`focus()` を公開)。リンクを押すと、項目にフォーカスを移す。
// 項目が折りたたみの中にあるときは、`select` で通知するので、呼び出し側が先に開く(開いた後にフォーカスする)。
import { nextTick, useTemplateRef } from 'vue'

import { mdiAlertCircleOutline } from '@/shared/theme/icons'

export type ErrorSummaryItem = {
  /** リンク先の入力欄の id */
  fieldId: string
  message: string
}

defineProps<{
  items: readonly ErrorSummaryItem[]
}>()

const emit = defineEmits<{
  select: [item: ErrorSummaryItem]
}>()

const root = useTemplateRef<HTMLElement>('root')

function focus(): void {
  root.value?.focus()
}
defineExpose({ focus })

async function focusField(item: ErrorSummaryItem): Promise<void> {
  emit('select', item)
  await nextTick()
  document.getElementById(item.fieldId)?.focus()
}
</script>

<template>
  <div v-if="items.length > 0" ref="root" class="error-summary" role="alert" tabindex="-1">
    <p class="text-body-strong error-summary__title">
      <v-icon :icon="mdiAlertCircleOutline" size="20" />
      入力内容を確認してください({{ items.length }} 件)
    </p>
    <ul>
      <li v-for="item in items" :key="item.fieldId">
        <a :href="`#${item.fieldId}`" @click.prevent="focusField(item)">{{ item.message }}</a>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.error-summary {
  padding: 12px 16px;
  border-radius: 4px;
  background: rgb(var(--v-theme-error-container));
  color: rgb(var(--v-theme-on-error-container));
  border: 1px solid rgba(var(--v-theme-error), 0.35);
  border-left: 4px solid rgb(var(--v-theme-error));
}
.error-summary__title {
  display: flex;
  gap: 8px;
  align-items: center;
  margin: 0 0 4px;
  color: rgb(var(--v-theme-error));
}
.error-summary ul {
  margin: 0;
  padding-left: 28px;
}
.error-summary a {
  color: inherit;
  font-weight: 600;
}
</style>
