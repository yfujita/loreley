<script setup lang="ts">
// SPA 内の 404(admin-view 4.2)。新しい画面は作らず、一覧型のページ見出しとエラーブロック(DS 4.5)で出す。
// Nginx は `/admin/` 配下の未知のパス(`assets/` 以外)に `index.html` を返すので、未知の URL はここに来る。
import { ROUTE_NAMES } from '@/admin/lib/routeNames'
import ListPage from '@/admin/templates/ListPage.vue'
import StateBlock from '@/shared/ui/StateBlock.vue'
import { READY_VIEW_STATE } from '@/admin/lib/viewState'

// 一覧の「データなし」ではなく、固定のエラーブロックを出す。ready にして、本文のスロットに StateBlock を置く。
const viewState = READY_VIEW_STATE
</script>

<template>
  <ListPage title="ページが見つかりません" :view-state="viewState">
    <StateBlock
      kind="notfound"
      title="ページが見つかりません"
      message="URL が間違っているか、ページが移動した可能性があります。ダッシュボードから目的の画面を開いてください。"
    >
      <router-link :to="{ name: ROUTE_NAMES.dashboard }">ダッシュボードへ戻る</router-link>
    </StateBlock>
  </ListPage>
</template>
