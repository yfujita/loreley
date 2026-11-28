// EP-14 `GET /meta` のフィクスチャ(F 7.3)。生成した型(スキーマ名の型)で `satisfies` する。
import type { MetaResponse } from '@/admin/api'

export const meta = {
  /** Dashboards の URL あり・cron のタイムゾーンあり */
  normal: () =>
    ({
      cron_timezone: 'Asia/Tokyo',
      dashboards_url: 'http://localhost:5601',
    }) satisfies MetaResponse,
  /** Dashboards 未設定(外部リンク領域を出さない。AF-20) */
  noDashboards: () =>
    ({ cron_timezone: 'Asia/Tokyo', dashboards_url: null }) satisfies MetaResponse,
  /** タイムゾーンを取得できない(警告。sources 2.4) */
  noTimezone: () =>
    ({ cron_timezone: null, dashboards_url: 'http://localhost:5601' }) satisfies MetaResponse,
}
