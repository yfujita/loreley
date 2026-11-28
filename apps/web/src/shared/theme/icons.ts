// アイコン(DS 3.1・R12): `@mdi/js` を import してよいのはこのファイルだけ。使うアイコンをここで名前付き import して
// 再 export し、他のファイルはここから import する(tree-shaking とポリシー確認(FARC-U-3)を 1 か所にする)。
// CDN の `<link>`・`@mdi/font` は使わない。
import { aliases, mdi } from 'vuetify/iconsets/mdi-svg'

export {
  mdiAlertCircleOutline,
  mdiAlertOutline,
  mdiCancel,
  mdiCheckCircleOutline,
  mdiChevronLeft,
  mdiChevronRight,
  mdiClockOutline,
  mdiClose,
  mdiCloseOctagonOutline,
  mdiDatabaseOutline,
  mdiDotsVertical,
  mdiFileSearchOutline,
  mdiHelpCircleOutline,
  mdiInformationOutline,
  mdiLockOpenOutline,
  mdiLockOutline,
  mdiMenu,
  mdiOpenInNew,
  mdiPlayCircleOutline,
  mdiPlaylistCheck,
  mdiRefresh,
  mdiServer,
  mdiSwapHorizontal,
  mdiTimerSand,
  mdiViewDashboardOutline,
} from '@mdi/js'

/** `createVuetify({ icons })` に渡す設定(`mdi-svg`。部品の内部アイコンも SVG パスで描く)。 */
export const iconOptions = { defaultSet: 'mdi', aliases, sets: { mdi } } as const
