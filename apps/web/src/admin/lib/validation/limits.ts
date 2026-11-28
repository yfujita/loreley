// 画面の検証の定数(E 7.1・F 3.5)。1 か所に定義する。
// API は上限値を返さない(AAPI-P-20)ので、パターンの上限は仮値。最終の判定は Crawler(サーバー)。

/** パターンの最大件数(`max_patterns`。仮値)。 */
export const MAX_PATTERNS = 100
/** 1 パターンの最大バイト数(UTF-8。`max_pattern_bytes`。仮値)。 */
export const MAX_PATTERN_BYTES = 1024
/** この値を超えた行の下に「n / 1,024 バイト」を出す。 */
export const PATTERN_BYTES_NOTICE_THRESHOLD = 800

/** `source_id` の最大文字数。 */
export const MAX_SOURCE_ID_LENGTH = 256
/** `ttl`・`min_delete_count` の最大桁数(9 桁。JavaScript の安全整数に収まる。承認済み(ゲート C。#3))。 */
export const MAX_INTEGER_DIGITS = 9
