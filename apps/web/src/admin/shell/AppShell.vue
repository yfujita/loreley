<script setup lang="ts">
// アプリのシェル(DS 5.1): `VApp` + 左サイドバー(`VNavigationDrawer`)+ `VMain`(`RouterView`)。
// 幅 840px 以上はサイドバーを常時表示、840px 未満は上部バー(`VAppBar`)のボタンで開く一時表示。
// サイドバーに静的な `permanent` は付けない(840px 未満でもドロワーにならなくなる)。常時表示・一時表示の切替は
// Vuetify の既定の挙動に任せる: `display.mobileBreakpoint: 'md'`(`shared/theme/display.ts`)の `mobile` で決まる(FARC-U-14)。
// パンくずは `useBreadcrumbs` で作って provide する(`PageHeader`(層 3)が `shell`(層 4)を import せずに受け取るため)。
import { nextTick, onBeforeUnmount, onMounted, provide, ref, useTemplateRef, watch } from 'vue'
import { useDisplay } from 'vuetify'

import { useBreadcrumbs } from '@/admin/composables/useBreadcrumbs'
import { breadcrumbsKey } from '@/admin/lib/injectionKeys'
import AppSnackbar from '@/shared/ui/AppSnackbar.vue'

import MobileAppBar from './MobileAppBar.vue'
import type { NavGroupDefinition } from './navItems'
import SideNav from './SideNav.vue'
import SkipLink from './SkipLink.vue'

defineProps<{ navGroups: readonly NavGroupDefinition[] }>()

/** ドロワーの `inert` が外れるのを待つ最大のフレーム数 */
const FOCUS_WAIT_FRAMES = 20

// アンマウント後は、フォーカス待ちのフレーム送りを打ち切る(`focusFirstNavItem`)
let isUnmounted = false

const { mobile } = useDisplay()
// `null`: 既定(常時表示なら開、一時表示なら閉)。Vuetify が幅の切替に合わせて決める。
const drawerOpen = ref<boolean | null>(null)
const appBar = useTemplateRef<{ focusMenuButton: () => void }>('appBar')

provide(breadcrumbsKey, useBreadcrumbs())

async function toggleDrawer(): Promise<void> {
  const opening = drawerOpen.value !== true
  drawerOpen.value = opening
  if (opening) await focusFirstNavItem()
}

// 開いたら、フォーカスをドロワーの中(最初のナビ項目)へ入れる(DS 8)。閉じ込めは `retain-focus`(下)が行う。
// 閉じている間のドロワーは `inert` で、開いた直後はまだ外れていない(フォーカスできない)ので、外れるまでの数フレームを待つ。
async function focusFirstNavItem(): Promise<void> {
  await nextTick()
  for (let frame = 0; frame < FOCUS_WAIT_FRAMES && !isUnmounted; frame++) {
    const element = drawerElement()
    if (element !== null && !element.hasAttribute('inert')) {
      element.querySelector<HTMLElement>('a[href]')?.focus()
      return
    }
    await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()))
  }
}

// `VNavigationDrawer` の `$el` は部品の根ではないことがあるので、class で探す。
function drawerElement(): HTMLElement | null {
  return document.querySelector<HTMLElement>('.app-shell__drawer')
}

function isFocusInsideDrawer(): boolean {
  return drawerElement()?.contains(document.activeElement) === true
}

function isFocusNowhere(): boolean {
  const active = document.activeElement
  return active === null || active === document.body
}

// 幅の変化(`mobile` の切替)で閉じる通知かを見分ける。`mobile` が変わった同じ tick(同期の watcher で印を付け、次の tick で外す)に
// 来た「閉じる」はリサイズ由来。スクリムのクリックは `mobile` が変わらないので、リサイズとは区別できる(どちらもフォーカスは body になりうる)。
let isViewportChanging = false
watch(
  mobile,
  () => {
    isViewportChanging = true
    window.setTimeout(() => {
      isViewportChanging = false
    }, 0)
  },
  { flush: 'sync' },
)

// 一時表示のドロワーが閉じたら、フォーカスをメニューのボタンへ戻す(DS 8)。スクリム・項目の選択(画面遷移)でも閉じる。
// 項目の選択では、続けて遷移後の処理(`afterEach`)が `h1` へフォーカスを移す。
// 戻す条件:
// - Esc などの利用者の操作(`userInitiated`): 常に戻す
// - スクリムのクリックなど `mobile` が変わっていない閉じ方: フォーカスがドロワーの中、またはどこにもない(body)とき
// - 幅の変化(840px 未満へのリサイズ・回転)で自動的に閉じたとき: フォーカスがドロワーの中にあったときだけ。
//   何も操作していない(body)・入力欄などにあるときは、フォーカスを動かさない(操作していないのにリングが出ないように)
function onDrawerModelUpdate(open: boolean, options: { userInitiated?: boolean } = {}): void {
  const wasOpen = drawerOpen.value === true
  drawerOpen.value = open
  if (!wasOpen || open || !mobile.value) return
  const shouldRestoreFocus =
    options.userInitiated === true ||
    (isViewportChanging ? isFocusInsideDrawer() : isFocusInsideDrawer() || isFocusNowhere())
  if (shouldRestoreFocus) appBar.value?.focusMenuButton()
}

// Esc で閉じる(DS 8)。`VNavigationDrawer` は Esc を扱わない(Vuetify 4.3.4 で確認)ので、ここで受ける。
// フォーカスはメニューのボタンにあることが多く、ドロワーの外なので、ドキュメントで受ける。
function closeDrawerOnEscape(event: KeyboardEvent): void {
  if (event.key !== 'Escape' || !mobile.value || drawerOpen.value !== true) return
  onDrawerModelUpdate(false, { userInitiated: true })
}
onMounted(() => document.addEventListener('keydown', closeDrawerOnEscape))
onBeforeUnmount(() => {
  isUnmounted = true
  document.removeEventListener('keydown', closeDrawerOnEscape)
})
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
    <!-- retain-focus・capture-focus: 一時表示(mobile)のときだけ、フォーカスをドロワーの中に閉じ込める(DS 8)。
         常時表示のときに付けると、デスクトップの Tab が奪われる -->
    <v-navigation-drawer
      :model-value="drawerOpen"
      :retain-focus="mobile"
      :capture-focus="mobile"
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
