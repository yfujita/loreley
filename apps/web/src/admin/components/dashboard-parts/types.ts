// D1 の概況バー・コンポーネントタイルが受け取る表示用のモデル(DS 4.16)。
// 値の組み立て(API の応答 → このモデル。取得失敗時の降格を含む)は `features/dashboard` が行い、
// ここの部品は受け取った値を描くだけにする(R7: データ取得・API の値の意味を知らない)。

/** タイルに出すタグの種類。`StatusTag` の `kind="health"` の値と同じ。 */
export type TileStatus = 'normal' | 'abnormal' | 'undetermined' | 'not_configured'

export type ComponentTileModel = {
  /** compose のサービス名(等幅の見出し)。`data-testid` の `d1-tile-{id}` にも使う */
  id: string
  /** 役割(12px) */
  role: string
  status: TileStatus
  /** 3 行目(確認の補足・判定不能の理由・前回の状態) */
  detail: string
  /** 3 行目を本文色にする(いま起きている異常・判定不能の説明)。false は補助色 */
  emphasized: boolean
  /** 末尾の導線。画面は route 名だけを渡し、URL の組み立ては router に任せる */
  link: { label: string; routeName: string } | null
}

export type SummaryTone = 'success' | 'error' | 'warning'

/** 概況バーの件数行の 1 項目。`names` があれば「ラベル: 名前(等幅)」、なければ「ラベル 値」。 */
export type SummaryItem = {
  key: string
  label: string
  value?: string
  names?: readonly string[]
}

export type SummaryModel = {
  tone: SummaryTone
  title: string
  items: readonly SummaryItem[]
}
