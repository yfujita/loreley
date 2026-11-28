// 外部リンクの定義表(E 4.2・F 3.5)。route を持たない外部リンク項目(MVP は OpenSearch Dashboards 1 件。AF-20)。
// 表示するかは `/meta`(EP-14)の値で決まる: URL が `null`(未設定・EP-14 の失敗を含む)なら、領域ごと出さない。
import { mdiOpenInNew } from '@/shared/theme/icons'

/** URL の取得元。`ExternalLinks` が EP-14 の値から作る。 */
export type ExternalLinkSource = 'dashboards'

export type ExternalLinkDefinition = {
  id: string
  label: string
  icon: string
  source: ExternalLinkSource
}

export const externalLinks: readonly ExternalLinkDefinition[] = [
  {
    id: 'opensearch-dashboards',
    label: 'OpenSearch Dashboards',
    icon: mdiOpenInNew,
    source: 'dashboards',
  },
]

/** 設定の URL を、リンクにしてよいか(http・https だけ)。`javascript:` などを href に入れない。 */
export function toSafeExternalUrl(value: string | null): string | null {
  if (value === null) return null
  try {
    const url = new URL(value)
    return url.protocol === 'http:' || url.protocol === 'https:' ? value : null
  } catch {
    return null
  }
}
