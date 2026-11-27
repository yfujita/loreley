<script setup lang="ts">
// アプリのシェル(DS 5.1): `VApp` + 左サイドバー(`VNavigationDrawer`)+ `VMain`(`RouterView`)。
// 幅 840px 以上はサイドバーを常時表示、840px 未満は上部バー(`VAppBar`)のボタンで開く一時表示。
// サイドバーに静的な `permanent` は付けない(840px 未満でもドロワーにならなくなる)。常時表示・一時表示の切替は
// Vuetify の既定の挙動に任せる: `display.mobileBreakpoint: 'md'`(`shared/theme/display.ts`)の `mobile` で決まる(FARC-U-14)。
// パンくずは `useBreadcrumbs` で作って provide する(`PageHeader`(層 3)が `shell`(層 4)を import せずに受け取るため)。
import { onBeforeUnmount, onMounted, provide, ref, useTemplateRef } from 'vue'
import { useDisplay } from 'vuetify'

import { useBreadcrumbs } from '@/admin/composables/useBreadcrumbs'
import { breadcrumbsKey } from '@/admin/lib/injectionKeys'
import AppSnackbar from '@/shared/ui/AppSnackbar.vue'

import MobileAppBar from './MobileAppBar.vue'
import type { NavGroupDefinition } from './navItems'
import SideNav from './SideNav.vue'
import SkipLink from './SkipLink.vue'

defineProps<{ navGroups: readonly NavGroupDefinition[] }>()

const { mobile } = useDisplay()
// `null`: 既定(常時表示なら開、一時表示なら閉)。Vuetify が幅の切替に合わせて決める。
const drawerOpen = ref<boolean | null>(null)
const appBar = useTemplateRef<{ focusMenuButton: () => void }>('appBar')

provide(breadcrumbsKey, useBreadcrumbs())

function toggleDrawer(): void {
  drawerOpen.value = drawerOpen.value !== true
}

// 一時表示のドロワーが閉じたら、フォーカスをメニューのボタンへ戻す(DS 8)。スクリム・項目の選択(画面遷移)でも閉じる。
// 項目の選択では、続けて遷移後の処理(`afterEach`)が `h1` へフォーカスを移す。
function onDrawerModelUpdate(open: boolean): void {
  const wasOpen = drawerOpen.value === true
  drawerOpen.value = open
  if (wasOpen && !open && mobile.value) appBar.value?.focusMenuButton()
}

// Esc で閉じる(DS 8)。`VNavigationDrawer` は Esc を扱わない(Vuetify 4.3.4 で確認)ので、ここで受ける。
// フォーカスはメニューのボタンにあることが多く、ドロワーの外なので、ドキュメントで受ける。
function closeDrawerOnEscape(event: KeyboardEvent): void {
  if (event.key !== 'Escape' || !mobile.value || drawerOpen.value !== true) return
  onDrawerModelUpdate(false)
}
onMounted(() => document.addEventListener('keydown', closeDrawerOnEscape))
onBeforeUnmount(() => document.removeEventListener('keydown', closeDrawerOnEscape))
</script>

<template>
  <v-app>
    <SkipLink />
    <MobileAppBar
      v-if="mobile"
      ref="appBar"
      :drawer-open="drawerOpen === true"
      @toggle="toggleDrawer"
    />
    <v-navigation-drawer
      :model-value="drawerOpen"
      class="app-shell__drawer"
      aria-label="メインメニュー"
      color="surface-variant"
      :width="mobile ? 272 : 232"
      @update:model-value="onDrawerModelUpdate"
    >
      <SideNav :nav-groups="navGroups" />
    </v-navigation-drawer>
    <v-main id="main" tabindex="-1" class="app-shell__main">
      <div class="app-shell__content">
        <router-view />
      </div>
    </v-main>
    <AppSnackbar />
  </v-app>
</template>

<style scoped>
.app-shell__drawer {
  border-right: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.app-shell__main:focus-visible {
  outline: none;
}
.app-shell__content {
  max-width: 1400px;
  padding: 24px 32px 40px;
}
@media (max-width: 1144px) {
  .app-shell__content {
    padding: 20px 24px 32px;
  }
}
@media (max-width: 839px) {
  .app-shell__content {
    padding: 16px;
  }
}
</style>
