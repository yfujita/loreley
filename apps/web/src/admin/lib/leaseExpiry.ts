// リース期限の整形(E 5.9・F 3.5。FMOD-P-15)。`lease_expires_at` を表示する箇所は、すべてここを通す。
//
// 409 の `details.existing_job.lease_expires_at` は、Crawler が値を日時として読めないときだけ
// `0001-01-01T00:00:00.000Z`(番兵)を返す(B 2.11・I-73)。日時として整形せず「期限切れ」として扱う。
// `null` は「期限なし(実行待ち)」で、番兵とは別。
// S2 の `lock.job.lease_expires_at` は `api` が読むため、読めなければ `null` で番兵は出ない(期限切れは `lock.state` で分かる)。
import { formatDate, parseIsoDateTime } from '@/shared/lib/datetime'

export const LEASE_EXPIRY_SENTINEL = '0001-01-01T00:00:00.000Z'
const SENTINEL_TIME = Date.parse(LEASE_EXPIRY_SENTINEL)

export type LeaseExpiry =
  // 日時(ブラウザのローカル時刻。`iso` は `<time datetime>` 用)
  | { kind: 'datetime'; iso: string; text: string }
  // 番兵: 期限切れ(日時として整形しない)
  | { kind: 'expired'; text: string }
  // 期限が null・読めないのにリース切れ(`stalled=true`・`lock.state=lease_expired`): 期限を確認できない
  | { kind: 'unknown-expired'; text: string }
  // 期限なし(実行待ち)
  | { kind: 'none'; text: string }

export const LEASE_EXPIRY_TEXT = {
  expired: '期限切れ',
  unknownExpired: '期限を確認できません(期限切れ)',
  none: '期限なし(実行待ち)',
} as const

/**
 * `expired`: リース切れかどうか。J2 では `stalled=true`、S2 のロック状態カードでは `lock.state=lease_expired`
 * から呼び出し側が渡す(画面で再計算しない)。
 */
export function formatLeaseExpiry(
  value: string | null | undefined,
  options: { expired: boolean },
): LeaseExpiry {
  const date = value === null || value === undefined ? null : parseIsoDateTime(value)

  if (date !== null && date.getTime() === SENTINEL_TIME) {
    return { kind: 'expired', text: LEASE_EXPIRY_TEXT.expired }
  }
  if (date !== null && value !== null && value !== undefined) {
    return { kind: 'datetime', iso: value, text: formatDate(date) }
  }
  return options.expired
    ? { kind: 'unknown-expired', text: LEASE_EXPIRY_TEXT.unknownExpired }
    : { kind: 'none', text: LEASE_EXPIRY_TEXT.none }
}
