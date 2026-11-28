// 単位変換・丸め(E 7.3・7.7・F 3.5)。変換は Admin API が行うので、画面は入力単位のまま送る(日 → 秒の変換は持たない)。
// ここは、S4 の表示のための秒 → 日と、しきい値の桁判定・丸め。

export const SECONDS_PER_DAY = 86_400

/** 秒 → 日。日で割り切れるときだけ整数、それ以外は null(S4 が「N 秒」表示に切り替える)。 */
export function secondsToDays(seconds: number): number | null {
  return seconds % SECONDS_PER_DAY === 0 ? seconds / SECONDS_PER_DAY : null
}

/**
 * しきい値が小数第 3 位以下を持つか(Crawler の API を直接使って登録された値など。E 7.7)。
 * `String(n)`(文字列表現の桁を数える方法)は使わない: 極小の値は指数表記になり(`String(1e-7)` は `'1e-7'`)、桁を数え誤る。
 * 小数第 2 位までの十進数は `toFixed(2)` で往復しても同じ値になる、という導出による。
 */
export function hasMoreThanTwoDecimals(value: number): boolean {
  return Number(value.toFixed(2)) !== value
}

/** `String(n)` が指数表記のとき、指数なしの十進の文字列に直す(`1e-7` → `0.0000001`)。 */
function toPlainDecimalString(value: number): string {
  const text = String(value)
  const match = /^(-?)(\d+)(?:\.(\d+))?e([+-]\d+)$/.exec(text)
  if (match === null) return text

  const [, sign = '', integerPart = '', fractionPart = '', exponentText = '0'] = match
  const exponent = Number(exponentText)
  const digits = integerPart + fractionPart
  // 小数点の位置(digits の先頭からの桁数)。
  const pointIndex = integerPart.length + exponent
  if (pointIndex <= 0) return `${sign}0.${'0'.repeat(-pointIndex)}${digits}`
  if (pointIndex >= digits.length)
    return `${sign}${digits}${'0'.repeat(pointIndex - digits.length)}`
  return `${sign}${digits.slice(0, pointIndex)}.${digits.slice(pointIndex)}`
}

/**
 * 小数第 2 位に四捨五入する(0 から遠ざかる向きの half-up)。丸めは十進で行う。
 * `toFixed(2)` をそのまま使わない: 2 進の誤差で `(2.675).toFixed(2)` は `'2.67'`、`(1.005).toFixed(2)` は `'1.00'` になり、
 * 四捨五入の期待(`2.68`・`1.01`)とずれる。
 */
export function roundToTwoDecimals(value: number): number {
  const plain = toPlainDecimalString(Math.abs(value))
  const [integerPart = '0', fractionPart = ''] = plain.split('.')
  if (fractionPart.length <= 2) return value

  const scaled = BigInt(integerPart + fractionPart.slice(0, 2).padEnd(2, '0'))
  const rounded = fractionPart.charCodeAt(2) >= '5'.charCodeAt(0) ? scaled + 1n : scaled
  const digits = rounded.toString().padStart(3, '0')
  const result = Number(`${digits.slice(0, -2)}.${digits.slice(-2)}`)
  return value < 0 ? -result : result
}
