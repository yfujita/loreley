<script setup lang="ts">
// S2 のスタブ(フェーズ 3)。route・テンプレート・見出し・フォーカスを確認するための最小のページで、
// 画面のフェーズで本実装に差し替える。
import { useRouteTitle } from '@/admin/composables/useRouteTitle'
import { READY_VIEW_STATE } from '@/admin/lib/viewState'
import DetailPage from '@/admin/templates/DetailPage.vue'

const title = useRouteTitle()
const viewState = READY_VIEW_STATE
</script>

<template>
  <DetailPage :title="title" mono-title :view-state="viewState" testid-prefix="s2">
    <p class="pa-4 ma-0">S2(画面は後続のフェーズで実装します)</p>
  </DetailPage>
</template>
