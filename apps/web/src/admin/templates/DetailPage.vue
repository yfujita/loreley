<script setup lang="ts">
// 詳細テンプレート(DS 6.2): ページ見出し領域(識別子・状態タグ・操作)+カードの縦並び。
// 読み込み中・見つかりません・エラーはカードで出し、本文(カード群)は `viewState` が ready・stale のときだけ描く。
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
  >
    <template #tag><slot name="tag" /></template>
    <template #description><slot name="description" /></template>
  </PageHeader>
  <div class="detail-page__body">
    <TopProgress :active="viewState.isRefreshing" />
    <ViewStateBody
      card
      :view-state="viewState"
      :texts="texts"
      :testid-prefix="testidPrefix"
      @retry="emit('retry')"
    >
      <div class="detail-page__stack">
        <slot />
      </div>
      <template v-if="$slots['notfound-actions']" #notfound-actions>
        <slot name="notfound-actions" />
      </template>
    </ViewStateBody>
  </div>
</template>

<style scoped>
.detail-page__body {
  position: relative;
}
.detail-page__stack {
  display: grid;
  gap: 16px;
}
</style>
