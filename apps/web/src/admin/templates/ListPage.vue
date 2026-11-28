<script setup lang="ts">
// 一覧テンプレート(DS 6.1): ページ見出し領域+カード(ツールバー・stale アラート・表・ページング)。
// 状態(読み込み中・空・エラー・stale)は `viewState` で出し分ける。表・ツールバー・ページングは画面がスロットで渡す。
import { computed } from 'vue'

import PageHeader from './PageHeader.vue'
import TopProgress from '@/shared/ui/TopProgress.vue'
import ViewStateBody from './ViewStateBody.vue'
import type { PageHeaderProps, ViewStateProps } from './types'

const props = defineProps<PageHeaderProps & ViewStateProps & { cardLabel?: string }>()

const emit = defineEmits<{ action: [id: string]; retry: [] }>()

// ページング(footer)は、表を出している間だけ。
const showFooter = computed(() => ['ready', 'stale'].includes(props.viewState.kind))
</script>

<template>
  <PageHeader
    :title="title"
    :mono-title="monoTitle"
    :description="description"
    :actions="actions"
    :primary-action-id="primaryActionId"
    @action="emit('action', $event)"
  />
  <v-card
    class="list-page__card"
    :role="cardLabel !== undefined ? 'region' : undefined"
    :aria-label="cardLabel"
  >
    <TopProgress :active="viewState.isRefreshing" />
    <div v-if="$slots.toolbar" class="list-page__toolbar">
      <slot name="toolbar" />
    </div>
    <ViewStateBody
      :view-state="viewState"
      :texts="texts"
      :testid-prefix="testidPrefix"
      @retry="emit('retry')"
    >
      <slot />
      <template v-if="$slots.loading" #loading><slot name="loading" /></template>
      <template v-if="$slots['empty-actions']" #empty-actions>
        <slot name="empty-actions" />
      </template>
    </ViewStateBody>
    <slot v-if="showFooter" name="footer" />
  </v-card>
</template>

<style scoped>
.list-page__card {
  position: relative;
  overflow: hidden;
}
.list-page__toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px 16px;
  padding: 12px 16px;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
</style>
