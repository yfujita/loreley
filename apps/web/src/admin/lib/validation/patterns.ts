// `connector_config`(`file_system`)の `root`・パターンの画面の検証(sources 2.3.2・F 3.5)。
// 画面側の規則は Connector の規則の**複製**で、ずれたときの安全網がサーバーの `config_invalid`(E 7.1)。
// 文言は画面仕様 2.3.2 の「画面のメッセージと Crawler の固定文の対応」の表。
import { formatCount } from '@/shared/lib/number'
import { hasLoneSurrogate } from '@/shared/api/unicode'

import {
  MAX_PATTERNS,
  MAX_PATTERN_BYTES,
  PATTERN_BYTES_NOTICE_THRESHOLD,
} from '@/admin/lib/validation/limits'

export const PATTERN_MESSAGES = {
  rootEmpty: '取得元のパスを入力してください',
  rootNotAbsolute: '「/」で始まる絶対パスで入力してください',
  rootDoubleSlash: '連続する「/」は使えません',
  dotSegment: '「.」「..」のセグメントは使えません',
  nul: '使えない文字(NUL)が含まれています',
  loneSurrogate: '使えない文字が含まれています',
  patternEmpty: 'パターンを入力するか、この行を削除してください',
  patternBackslash: '「\\」は使えません(エスケープはありません)',
  patternEmptySegment: '先頭・末尾・連続する「/」は使えません',
  patternDoubleStarNotAlone: '「**」は単独のセグメントで使います(例: **/*.md)',
  patternDoubleStarAdjacent: '「**」を隣り合わせにできません(例: **/**)',
  tooManyPatterns: `パターンは ${MAX_PATTERNS} 件までです`,
  patternSurroundingWhitespace: '前後の空白も、パターンの一部として扱われます。',
} as const

export function patternBytesMessage(byteCount: number): string {
  return `1 つのパターンは 1〜${formatCount(MAX_PATTERN_BYTES)} バイト(UTF-8)です(現在 ${formatCount(byteCount)} バイト)`
}

const textEncoder = new TextEncoder()

/** UTF-8 のバイト数。 */
export function utf8ByteLength(value: string): number {
  return textEncoder.encode(value).length
}

/** 取得元のパス(`root`)の検証。エラー文を返す(問題がなければ null)。 */
export function validateRoot(value: string): string | null {
  if (value === '') return PATTERN_MESSAGES.rootEmpty
  if (value.includes('\u0000')) return PATTERN_MESSAGES.nul
  if (hasLoneSurrogate(value)) return PATTERN_MESSAGES.loneSurrogate
  if (!value.startsWith('/')) return PATTERN_MESSAGES.rootNotAbsolute
  if (value.includes('//')) return PATTERN_MESSAGES.rootDoubleSlash
  if (value.split('/').some((segment) => segment === '.' || segment === '..')) {
    return PATTERN_MESSAGES.dotSegment
  }
  return null
}

/** 1 行のパターン(`include_patterns[i]`・`exclude_patterns[i]`)の検証。エラー文を返す(問題がなければ null)。 */
export function validatePattern(value: string): string | null {
  if (value === '') return PATTERN_MESSAGES.patternEmpty
  const byteCount = utf8ByteLength(value)
  if (byteCount > MAX_PATTERN_BYTES) return patternBytesMessage(byteCount)
  if (value.includes('\u0000')) return PATTERN_MESSAGES.nul
  if (hasLoneSurrogate(value)) return PATTERN_MESSAGES.loneSurrogate
  if (value.includes('\\')) return PATTERN_MESSAGES.patternBackslash

  const segments = value.split('/')
  if (segments.some((segment) => segment === '')) return PATTERN_MESSAGES.patternEmptySegment
  if (segments.some((segment) => segment === '.' || segment === '..')) {
    return PATTERN_MESSAGES.dotSegment
  }
  if (segments.some((segment) => segment !== '**' && segment.includes('**'))) {
    return PATTERN_MESSAGES.patternDoubleStarNotAlone
  }
  for (let index = 1; index < segments.length; index += 1) {
    if (segments[index] === '**' && segments[index - 1] === '**') {
      return PATTERN_MESSAGES.patternDoubleStarAdjacent
    }
  }
  return null
}

export type PatternListValidation = {
  /** 一覧の下に出すエラー(添字のない配列のエラー。件数の超過) */
  listMessage: string | null
  /** 行ごとのエラー(行と添字を 1 対 1 にするため、空の行も除かない) */
  rowMessages: readonly (string | null)[]
}

/** パターン一覧の検証。件数の超過と、全行の検証(すべて出す)。 */
export function validatePatternList(patterns: readonly string[]): PatternListValidation {
  return {
    listMessage: patterns.length > MAX_PATTERNS ? PATTERN_MESSAGES.tooManyPatterns : null,
    rowMessages: patterns.map(validatePattern),
  }
}

/** 前後に空白があるか(エラーにはせず、その行の下に注意を出す。保存する値は入力のまま)。 */
export function hasSurroundingWhitespace(value: string): boolean {
  return value !== value.trim()
}

/** この行の下に「n / 1,024 バイト」を出すか(800 バイトを超えたとき)。 */
export function shouldShowPatternByteCount(value: string): boolean {
  return utf8ByteLength(value) > PATTERN_BYTES_NOTICE_THRESHOLD
}
