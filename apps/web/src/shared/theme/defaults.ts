// Vuetify の `defaults`(DS 3.2)。Vuetify 既定の Material らしさ(大きい角丸・強い色)を落とし、落ち着いた管理画面にする。
// 入力欄の高さ 40px(DS 2.3)は、実測で `density: 'compact'` が 40px、`comfortable` が 48px(Vuetify 4.3.4)。
// ボタンの種類ごとの色・枠(outlined の枠は `line-strong`)は、`defaults` だけでは表せないので global.css が補う。
import type { VuetifyOptions } from 'vuetify'

/** `VSnackbar` の表示時間(DS 4.7)。 */
export const SNACKBAR_TIMEOUT_MS = 6000

export const vuetifyDefaults: NonNullable<VuetifyOptions['defaults']> = {
  VBtn: { variant: 'flat', rounded: 'md', color: 'primary' },
  VTextField: {
    variant: 'outlined',
    density: 'compact',
    color: 'primary',
    hideDetails: 'auto',
  },
  VSelect: {
    variant: 'outlined',
    density: 'compact',
    color: 'primary',
    hideDetails: 'auto',
  },
  VTextarea: {
    variant: 'outlined',
    density: 'compact',
    color: 'primary',
    hideDetails: 'auto',
  },
  VCombobox: {
    variant: 'outlined',
    density: 'compact',
    color: 'primary',
    hideDetails: 'auto',
  },
  VCard: { variant: 'flat', border: 'thin', rounded: 'lg', elevation: 0 },
  VChip: { variant: 'flat', label: true, size: 'small', rounded: 'md' },
  VAlert: { variant: 'flat', border: 'start', rounded: 'md' },
  VDataTable: { density: 'comfortable', hover: true },
  VDataTableServer: { density: 'comfortable', hover: true },
  VDialog: { maxWidth: 560 },
  VSnackbar: { timeout: SNACKBAR_TIMEOUT_MS, location: 'bottom', color: 'ink' },
  // 幅 232px・常時表示/一時表示の切替は AppShell が `mdAndUp` で決める(静的な `permanent` は付けない)。
  VNavigationDrawer: { width: 232 },
  VList: { nav: true, density: 'comfortable', color: 'primary' },
  VTabs: { color: 'primary' },
  VBreadcrumbs: { density: 'compact' },
}
