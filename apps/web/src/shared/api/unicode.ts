// API に渡す値(パス・本文)の Unicode の検査(純粋)。
// `admin/api` が import できる shared は `shared/api` だけ(R17)なので、パス値の検証(admin/api)と
// パターンの検証(admin/lib)が共有するこの関数は、ここに置く。

/** 対になっていないサロゲート(孤児サロゲート)を含むか。`encodeURIComponent` は含む文字列で `URIError` を投げる。 */
export function hasLoneSurrogate(value: string): boolean {
  for (let index = 0; index < value.length; index += 1) {
    const code = value.charCodeAt(index)
    const isHigh = code >= 0xd800 && code <= 0xdbff
    const isLow = code >= 0xdc00 && code <= 0xdfff
    if (isHigh) {
      const next = value.charCodeAt(index + 1)
      if (next >= 0xdc00 && next <= 0xdfff) {
        index += 1
        continue
      }
      return true
    }
    if (isLow) return true
  }
  return false
}
