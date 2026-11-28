<script setup lang="ts">
// 幅 840px 未満だけに置く上部バー(DS 5.1): ナビのドロワーを開閉するボタンとブランド。
// MVP は認証・ユーザーメニューがなく載せる要素がないので、デスクトップではグローバルヘッダーを置かない。
// 将来(認証 AF-23 など)に載せる要素のために、`actions` スロットを確保する。
import { useTemplateRef } from 'vue'

import { mdiMenu } from '@/shared/theme/icons'

defineProps<{ drawerOpen: boolean }>()

defineEmits<{ toggle: [] }>()

const menuButton = useTemplateRef<{ $el: HTMLElement }>('menuButton')

/** ドロワーを閉じたとき、フォーカスをメニューのボタンへ戻す(DS 8)。 */
defineExpose({ focusMenuButton: () => menuButton.value?.$el.focus() })
</script>

<template>
  <v-app-bar flat height="48" class="mobile-app-bar">
    <v-btn
      ref="menuButton"
      variant="text"
      icon
      color="on-surface"
      aria-label="メニューを開く"
      :aria-expanded="drawerOpen"
      @click="$emit('toggle')"
    >
      <v-icon :icon="mdiMenu" />
    </v-btn>
    <span class="mobile-app-bar__brand text-body-strong">Loreley 管理</span>
    <v-spacer />
    <slot name="actions" />
  </v-app-bar>
</template>

<style scoped>
.mobile-app-bar {
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.mobile-app-bar__brand {
  margin-left: 4px;
}
</style>
