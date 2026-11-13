# 0014 R2 の表現修正と infrastructure クライアントの注入方法の追加

- 日付: 2026-11-13
- 種別: 途中の追加指示への対応(軽微。プランは作り直さない)

## 指示(ユーザー)

軽微な指摘 2 点の修正(0013 の `connectors` 独立化に対する指摘)。

1. R2 の「データソースへのアクセスは `connectors` だけが行う」は、将来 `infrastructure` 側にクライアント(例: Confluence API)を置くと、実際の通信は `infrastructure` が行うため矛盾しうる。「探索・取得を制御する責務は `connectors` が持ち、外部 API との通信や認証などの低レベルな I/O は、必要に応じて `infrastructure` に委ねる」に直す
2. `infrastructure` のクライアントの注入方法を決めておく。Connector が自分で生成せず外から渡す。`FsOps` の注入と同じ考え方で、Composition Root(`main.py`)が Client Factory を作って `ConnectorType` に渡す。`create(config)` のインターフェースは変えない

## 実施した作業

`crawler-module-structure-v0.3.md`(未承認の版のため、新版は作らず v0.3 を修正)と `crawler-design-decisions-v0.2.md` を更新した。

- R2: 責務の分担の表現に直した(探索・取得の制御は `connectors`、低レベルな I/O は必要に応じて `infrastructure`。Confluence の例と、MVP の FS は `FsOps` に委ねて `infrastructure` を使わないことを併記)
- 4.10: 依存先に、クライアントは外から渡されること(CM-P-26)を追記。「やること」に、クライアント・Client Factory の受け取りの項目を追加
- 7.3: CM-P-26(案)を追加。Client Factory は `connector_config` からクライアントを作る関数で、`main.py` が `ConnectorType` の生成時に渡す。`create(config)` は変えない。`infrastructure` が `connectors` に依存しない向きは変わらない
- 7.4: CM-U-8 に CM-P-26 への参照を追記(具体化は Web Connector の追加時)
- v0.3 冒頭の改訂欄に追記。decisions-v0.2 の方針 #15 に 1 文追記

## 判断・設計上の理由

- **区分は案**: ユーザーの指摘は方針の提案で、確定とは言われていないため CM-P-26 は案にした。MVP の FS には適用対象がない(`FsOps` のみ)ので、実装の追加はない
- **Client と Client Factory の両方を書いた**: 接続先・認証が `connector_config`(ソースごと)で変わる場合は、生成時に 1 つのクライアントを渡すより、設定からクライアントを作る Factory を渡す方が合うため。どちらを使うかは Web Connector の設計時に決める(CM-U-8)
- 版は新設しない: v0.3 は本会話中に作った未承認の版で、同じ版に反映するほうが履歴が簡潔になるため

## 検証

- 修正は文言・追記のみで、依存関係(R1〜R5、R3 の 9 本)は変えていない。独立レビューは省略した(理由: 構成・依存の変更がなく、前回レビューの観点に影響しないため)

## 未対応事項・次にやること

- 設計書はユーザー未承認の案を含む
- Web Connector の設計時に、注入するクライアントの種類(Client か Factory)と `infrastructure` への置き方を決める(CM-U-8)
