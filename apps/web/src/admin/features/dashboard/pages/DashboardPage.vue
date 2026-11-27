<script setup lang="ts">
// D1 のスタブ(フェーズ 3)。route・テンプレート・見出し・フォーカスを確認するための最小のページで、
// 画面のフェーズで本実装に差し替える。
import { useRouteTitle } from '@/admin/composables/useRouteTitle'
import { READY_VIEW_STATE } from '@/admin/lib/viewState'
import DashboardPageTemplate from '@/admin/templates/DashboardPage.vue'

const title = useRouteTitle()
const viewState = READY_VIEW_STATE
</script>

<template>
  <DashboardPageTemplate :title="title" :view-state="viewState" testid-prefix="d1">
    <p class="pa-4 ma-0">D1(画面は後続のフェーズで実装します)</p>
  </DashboardPageTemplate>
</template>
