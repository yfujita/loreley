// O1 のシャード配置マトリクスが受け取る表示用のモデル(DS 4.15・opensearch 3.3)。
// API の応答 → このモデルの組み立て(行・列・凡例の対象。絞り込み後のインデックスだけを数える)は
// `features/opensearch/models/matrixModel.ts` が行い、ここの部品は受け取った値を描くだけにする(R7)。
// `role`・`state`・`status` は OpenAPI で素の string(列挙なし)なので、API の値のまま持ち、描画側が `lib/clusterValues` のガードを通す。

/** セルに並べる 1 つのシャード。 */
export type ShardChipModel = {
  /** シャード番号(`P0` の `0`) */
  number: number
  role: string
  state: string
}

/** 列(インデックス)。 */
export type MatrixColumn = {
  name: string
  /** `green` / `yellow` / `red`(未知の値もありうる)。取得できなければ null */
  status: string | null
  /** ドキュメント件数。取得できなければ null(0 件と区別する) */
  documentCount: number | null
  /** ノード名 → そのノードに載っているシャード(プライマリ → レプリカ、番号の昇順) */
  shardsByNode: ReadonlyMap<string, readonly ShardChipModel[]>
  /** 未割り当て(ノードなし)のシャード */
  unassigned: readonly ShardChipModel[]
}

/** 行(ノード)。`shardCount` は表示対象のインデックス(全ページ)に載っているシャード数。 */
export type MatrixNode = {
  name: string
  shardCount: number
}

/** 凡例に出す項目。プライマリ・レプリカは常に出し、それ以外は表示対象のどこかにあるときだけ。 */
export type MatrixLegend = {
  unassignedReplica: boolean
  unassignedPrimary: boolean
  inTransit: boolean
}

export type MatrixModel = {
  nodes: readonly MatrixNode[]
  /** 「未割り当て」の行の `shardCount`。0 のときは行を出さない */
  unassignedShardCount: number
  columns: readonly MatrixColumn[]
  legend: MatrixLegend
}
