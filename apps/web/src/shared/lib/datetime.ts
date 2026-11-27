// 日時の表記(DS 4.9。FARC-P-24・33): `YYYY-MM-DD HH:mm`(24 時間。秒が要る箇所だけ `:ss`)。
// ブラウザのローカル時刻で表示し、タイムゾーンの略称は付けない。日時ライブラリは足さない。
// API の時刻は ISO 8601(UTC・ミリ秒精度。A 5.1)なので、`Date` に変換してから扱う。

// 書式はロケールに任せず、部品(formatToParts)から組み立てる(ロケールごとの区切り・桁の違いを避ける)。
const PARTS_FORMAT = new Intl.DateTimeFormat('en-US', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hourCycle: 'h23',
})

type FormatOptions = {
  /** 秒まで出す(秒が必要な箇所だけ) */
  withSeconds?: boolean
}

/** ISO 8601 の文字列を `Date` にする。日時として読めなければ null。 */
export function parseIsoDateTime(value: string): Date | null {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

/** `Date`(Query の `dataUpdatedAt` など)を、ブラウザのローカル時刻の表記にする。 */
export function formatDate(date: Date, options: FormatOptions = {}): string {
  const parts = new Map(PARTS_FORMAT.formatToParts(date).map((part) => [part.type, part.value]))
  const day = `${parts.get('year')}-${parts.get('month')}-${parts.get('day')}`
  const time = `${parts.get('hour')}:${parts.get('minute')}`
  return options.withSeconds === true ? `${day} ${time}:${parts.get('second')}` : `${day} ${time}`
}

/**
 * ISO 8601 の文字列を、ブラウザのローカル時刻の `YYYY-MM-DD HH:mm`(`withSeconds` なら `:ss` つき)にする。
 * 日時として読めない文字列は null(呼び出し側が「—」などにする)。
 */
export function formatDateTime(value: string, options: FormatOptions = {}): string | null {
  const date = parseIsoDateTime(value)
  return date === null ? null : formatDate(date, options)
}
