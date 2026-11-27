<script setup lang="ts">
// ダッシュボードテンプレート(DS 6.4): ページ見出し領域+その下の操作行(最終取得・自動更新・更新ボタン。
// すべての状態・幅で見出しの下に置く)+カード・タイルの縦並び。読み取り専用で、操作を持たない。
import PageHeader from './PageHeader.vue'
import TopProgress from '@/shared/ui/TopProgress.vue'
import ViewStateBody from './ViewStateBody.vue'
import type { PageHeaderProps, ViewStateProps } from './types'

defineProps<PageHeaderProps & ViewStateProps>()

const emit = defineEmits<{ action: [id: string]; retry: [] }>()
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
  <div v-if="$slots.toolbar" class="dashboard-page__toolbar">
    <slot name="toolbar" />
  </div>
  <div class="dashboard-page__body">
    <TopProgress :active="viewState.isRefreshing" />
    <ViewStateBody
      card
      :view-state="viewState"
      :texts="texts"
      :testid-prefix="testidPrefix"
      @retry="emit('retry')"
    >
      <div class="dashboard-page__stack">
        <slot />
      </div>
      <template v-if="$slots.loading" #loading><slot name="loading" /></template>
      <template #empty-actions><slot name="empty-actions" /></template>
    </ViewStateBody>
  </div>
</template>

<style scoped>
.dashboard-page__toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 16px;
  margin-bottom: 16px;
}
.dashboard-page__body {
  position: relative;
}
.dashboard-page__stack {
  display: grid;
  gap: 16px;
}
</style>
