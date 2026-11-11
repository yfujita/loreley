# 0005 レビュー指摘(1回目)の修正 作業記録

## 概要
0004 の v0.2 5文書を document-reviewer でレビューした。Critical 0件、Important 8件、Suggestion 6件、Nitpick 5件。document-writer 2体(architecture/api と schema 3文書)が v0.2 をその場で修正した(v0.2 は未公開ドラフトのため新版は作らない)。

## レビュー結果(要約)
- 良好: 数値・状態値・API名・判定順・失敗理由コード・§11 の期待結果は SD v0.8 と一致。architecture 18.1 の行番号も一致。
- Important:
  1. K8 が状態名の一覧を確定扱い(SD §14.7 では案)
  2. 未決 ID 体系が文書ごとにバラバラ
  3. api 0章・1章の章番号誤参照
  4. architecture 11章末の参照誤り(16.6→16.9)
  5. ロック所有確認の粒度が architecture と api で矛盾
  6. api 5.4 のソース削除ジョブのロックが SD L265 と食い違い
  7. マッピング案が `dynamic: strict` 下で `url/path` 等を欠く
  8. マッピング案に推測/仮置き/プレースホルダの区分がない
  9. 「未知の crawl_id の破棄」が確定と案の両方に載る(上記の別項。計8件の Important のうち 7・8 と合わせて対応)

## 変更したファイル
- docs/v0.x/system-design/indexer/indexer-architecture-v0.2.md
- docs/v0.x/system-design/indexer/indexer-api-v0.2.md
- docs/v0.x/system-design/opensearch/schema/search-index-v0.2.md
- docs/v0.x/system-design/opensearch/schema/loreley-texts-v0.2.md
- docs/v0.x/system-design/opensearch/schema/loreley-deletions-v0.2.md

## 対応内容と判断理由
- K8 を SD §14.7 の確定範囲(受理済みの旧い削除を止めない、`interrupted`/`stale` 廃止、`discarded` の理由、`failed` の範囲)に絞り、状態名の一覧は案 P25 に移した(1.3、9.10、api 4.3 にも注記)。
- ID 体系: architecture の K/P/U/G を正本として renumber せず、api は `API-U-1`〜`API-U-14`、schema は文書ローカル U-* とし、文書をまたぐ参照は「architecture U-n」のように文書名付きにした。architecture との対応表を schema に併記。旧版 ID(旧 Xn/Gn/Nn)と「元の設計書」を除去。
- ロック所有確認: 「文書ごと(案)。バッチ途中でロックを失った場合の部分結果の返し方は未決」と明記し、文書単位の `failure_type: lock_not_owned` を提案(案)として併記(`API-U-13`)。api 5.1 の 409 から `lock_not_owned` を外した。
- ソース削除ジョブのロック: SD L265「自分のロック文書を先に削除してからジョブ終了(案)」に合わせ、順3 の時点でロック文書は削除済みである点と、ロック所有情報の添付可否が未決である点を記載(`API-U-14`、architecture U-4)。
- K7/P16: 「未知の crawl_id の終了通知を削除に使わず破棄」は確定、「記録するか(件数上限付き選択肢あり)」は案として区別。
- マッピング JSON: `strict` 下で `url/path` を含む文書が拒否される旨を明記。要素を SD の方針/推測/仮置き/プレースホルダに区分し、確認状況表に反映。
- Suggestion/Nitpick は全件対応(api 4.2/5.2 の例の矛盾解消、停止確認の重複を 9.8 に統合、SD 節参照を出典注記へ、区分「方針(区分の明記なし)」を「案(確定の明記なし)」へ、など)。見送りはなし。

## 未対応事項・次にやること
- 修正後の全文再読は未実施(architecture/api の担当)。再レビューで整合を確認する。
- `loreley-deletions-v0.2` が状態名の一覧を確定扱いにしていないか(P25 との整合)を確認する。
- 設計判断の未決はユーザー判断待ち(X2 `loreley-texts` 廃止、`fetched_at`/`metadata`、`url`/`path`、`summary_embedding`、原本サイズ超過の拒否主体、スナップショット項目名、API-U-13/14 ほか)。
- architecture 1.3 の注記位置は一部のみ統一。
- 次: document-reviewer による再レビュー → task-reviewer。
