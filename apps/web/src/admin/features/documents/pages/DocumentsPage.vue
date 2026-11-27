<script setup lang="ts">
// X1 のスタブ(フェーズ 3)。route・テンプレート・見出し・フォーカスを確認するための最小のページで、
// 画面のフェーズで本実装に差し替える。
import { useRouteTitle } from '@/admin/composables/useRouteTitle'
import { resolveViewState } from '@/admin/lib/viewState'
import ListPage from '@/admin/templates/ListPage.vue'

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
  <ListPage :title="title" :view-state="viewState" testid-prefix="x1">
    <p class="pa-4 ma-0">X1(画面は後続のフェーズで実装します)</p>
  </ListPage>
</template>
