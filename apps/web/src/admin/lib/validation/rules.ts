// フォームの項目の画面の検証(sources 2.3・E 7.1・7.2。F 3.5)。項目 → 規則の表と純関数。検証ライブラリは足さない。
//
// 数値は**文字列のまま形式を検証してから**数値にする(浮動小数の誤差を持ち込まない。E 7.2)。
// 戻り値の `ok: true` の `value` は、そのまま JSON の数値としてリクエストに載せられる値。
import { MAX_INTEGER_DIGITS, MAX_SOURCE_ID_LENGTH } from '@/admin/lib/validation/limits'

export type FieldParseResult<T> = { ok: true; value: T } | { ok: false; message: string }

export const RULE_MESSAGES = {
  sourceIdRequired: '識別子を入力してください',
  sourceIdFormat: '半角英数字で始まり、半角英数字と . _ - だけで入力してください',
  ttlRequired: 'TTL を入力してください',
  ttl: '1 以上の整数で入力してください',
  ratioRequired: '削除の割合しきい値を入力してください',
  ratio: '0 以上 100 未満で入力してください',
  minDeleteCountRequired: '最小件数を入力してください',
  minDeleteCount: '0 以上の整数で入力してください',
} as const

const SOURCE_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]*$/
const INTEGER_PATTERN = new RegExp(`^[0-9]{1,${MAX_INTEGER_DIGITS}}$`)
// しきい値: 整数部 1〜3 桁、小数第 2 位まで(E 7.2)。
const RATIO_PATTERN = /^[0-9]{1,3}(\.[0-9]{1,2})?$/

const fail = (message: string): FieldParseResult<never> => ({ ok: false, message })

/** 識別子(S3)。前後の空白は除かない(形式違反として扱う)。 */
export function parseSourceId(text: string): FieldParseResult<string> {
  if (text === '') return fail(RULE_MESSAGES.sourceIdRequired)
  if (text.length > MAX_SOURCE_ID_LENGTH || !SOURCE_ID_PATTERN.test(text)) {
    return fail(RULE_MESSAGES.sourceIdFormat)
  }
  return { ok: true, value: text }
}

/** TTL(日・秒のどちらのモードでも): 1 以上の整数、9 桁まで。前後の空白は無視する。 */
export function parseTtl(text: string): FieldParseResult<number> {
  const trimmed = text.trim()
  if (trimmed === '') return fail(RULE_MESSAGES.ttlRequired)
  if (!INTEGER_PATTERN.test(trimmed)) return fail(RULE_MESSAGES.ttl)
  const value = Number(trimmed)
  return value >= 1 ? { ok: true, value } : fail(RULE_MESSAGES.ttl)
}

/** 削除の割合しきい値(%): 0 以上 100 未満、小数第 2 位まで。前後の空白は無視する。 */
export function parseRatioThreshold(text: string): FieldParseResult<number> {
  const trimmed = text.trim()
  if (trimmed === '') return fail(RULE_MESSAGES.ratioRequired)
  if (!RATIO_PATTERN.test(trimmed)) return fail(RULE_MESSAGES.ratio)
  const value = Number(trimmed)
  return value >= 0 && value < 100 ? { ok: true, value } : fail(RULE_MESSAGES.ratio)
}

/** 最小件数: 0 以上の整数、9 桁まで。前後の空白は無視する。 */
export function parseMinDeleteCount(text: string): FieldParseResult<number> {
  const trimmed = text.trim()
  if (trimmed === '') return fail(RULE_MESSAGES.minDeleteCountRequired)
  if (!INTEGER_PATTERN.test(trimmed)) return fail(RULE_MESSAGES.minDeleteCount)
  return { ok: true, value: Number(trimmed) }
}

/**
 * 要入力確認(DLG-2)で、入力が対象の識別子と一致するか。前後の空白を無視した完全一致(大文字小文字を区別。DS 4.8)。
 */
export function matchesTypedConfirmation(input: string, expected: string): boolean {
  return input.trim() === expected
}
