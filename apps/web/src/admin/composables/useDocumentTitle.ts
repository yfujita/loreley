// `document.title`(DS 5.3: 「title - Loreley 管理」。F 3.1)。FMOD-U-10。
// ページ遷移後の更新は router の `afterEach`(guards.ts)が行う。動的な見出し(識別子など)の反映にこの composable を使う。
import { toValue, watchEffect, type MaybeRefOrGetter } from 'vue'

export const APP_TITLE = 'Loreley 管理'

export function formatDocumentTitle(title: string): string {
  return `${title} - ${APP_TITLE}`
}

/** `title` が変わるたびに `document.title` を更新する。 */
export function useDocumentTitle(title: MaybeRefOrGetter<string>): void {
  watchEffect(() => {
    document.title = formatDocumentTitle(toValue(title))
  })
}
