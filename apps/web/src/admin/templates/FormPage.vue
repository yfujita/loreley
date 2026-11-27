<script setup lang="ts">
// フォーム / 編集テンプレート(DS 6.3): ページ見出し領域+最大幅 640px の 1 列のカード。
// 編集の現在値の取得中・見つかりません・エラーは `viewState` で出し分け、フォーム本体は ready のときだけ描く
// (取得できなければフォームを出さない)。エラー要約・保存ボタンはフォーム(スロット)が持つ。
import PageHeader from './PageHeader.vue'
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
  <div class="form-page__body">
    <ViewStateBody
      card
      :view-state="viewState"
      :texts="texts"
      :testid-prefix="testidPrefix"
      @retry="emit('retry')"
    >
      <v-card class="form-page__card">
        <slot />
      </v-card>
      <template v-if="$slots['notfound-actions']" #notfound-actions>
        <slot name="notfound-actions" />
      </template>
    </ViewStateBody>
  </div>
</template>

<style scoped>
.form-page__body {
  max-width: 640px;
}
.form-page__card {
  padding: 24px;
}
</style>
