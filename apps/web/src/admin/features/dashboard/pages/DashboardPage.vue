<script setup lang="ts">
// D1 のスタブ(フェーズ 3)。route・テンプレート・見出し・フォーカスを確認するための最小のページで、
// 画面のフェーズで本実装に差し替える。
import { useRouteTitle } from '@/admin/composables/useRouteTitle'
import { resolveViewState } from '@/admin/lib/viewState'
import DashboardPageTemplate from '@/admin/templates/DashboardPage.vue'

const title = useRouteTitle()
const viewState = resolveViewState({
  isLoading: false,
  isFetching: false,
  hasData: true,
  isEmpty: false,
  isLoadingError: false,
  isRefetchError: false,
  dataUpdatedAt: 0,
  error: null,
})
</script>

<template>
  <DashboardPageTemplate :title="title" :view-state="viewState" testid-prefix="d1">
    <p class="pa-4 ma-0">D1(画面は後続のフェーズで実装します)</p>
  </DashboardPageTemplate>
</template>
