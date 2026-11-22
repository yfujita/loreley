# 0004 フェーズ2: v0.2(改善版)の作成 作業記録

## 概要
承認済みプラン(0001)のフェーズ2。v0.1 を P3 の方針(構造化と曖昧さの解消、仕様・数値は変えない)で改善し、document-writer 3体の並行作業で v0.2 を5文書作成した。v0.1 は変更していない。

## 変更(作成)したファイル
- docs/v0.x/system-design/indexer/indexer-architecture-v0.2.md(1〜15章は v0.1 と同じ章番号。16 テスト観点(論点別に再編)、17 確認状況(確定 K1〜K17、案 P1〜P24、未決 U-1〜U-25、推測・導出 G-1〜G-9)、18 変更点)
- docs/v0.x/system-design/indexer/indexer-api-v0.2.md(4章 SDが定めるAPIの例、5章 SD未定義APIの「提案(案)」、7 確認状況、8 変更点)
- docs/v0.x/system-design/opensearch/schema/search-index-v0.2.md
- docs/v0.x/system-design/opensearch/schema/loreley-texts-v0.2.md
- docs/v0.x/system-design/opensearch/schema/loreley-deletions-v0.2.md

## 判断・設計上の理由
- 共通解消ルールを3体に配布: 文言上の食い違いは SD 本文・§14 を正として解消、設計判断を伴うものは決めず「未決(ユーザー判断)」に集約。
- 解消した食い違い: X1(Status API の利用者は Crawler、Admin View は Admin API 経由)、X3(終了通知は「202。内容が異なる再送は 409(案)」)、X5(「割合ルールの判定1〜3」「削除判定の順1〜6」の呼び分け)、X6(Indexer が読むインデックスを architecture 2.3 の表に集約)、X11(404 条件は案、確定は未決)、X14(推測の注記)。
- 未決として残した(ユーザー判断): X2 `loreley-texts` 廃止、X4 設定スナップショット項目名、X7 `fetched_at`/`metadata` の所在、X8 `url`/`path` の項目数、X9 `summary_embedding`、X10 原本サイズ超過の拒否主体。選択肢は併記。
- API の例: SD で形が決まっている API(開始/終了通知・Status API)は SD の項目に沿って例示。SD 未定義(エラー応答、バッチ登録 `POST /sources/{source_id}/documents:batch`、`last_seen_at` 更新、ソース削除、突合、`raw_content` base64 等)は「提案(案)」と明示し、確定扱いにしていない。
- マッピング JSON: search-index 4.1 と loreley-texts 3.2 に「提案(案)」として掲載(`dynamic: strict`、shard 1、replica 0、`index_options: offsets` 等、SD 方針の範囲内。型は用途からの案)。loreley-deletions はマッピング未決のため JSON なし。
- 経緯・履歴表現を除去し、重複(クロール手順、開始/終了通知の失敗、D=0 の説明、二重の責務表、再インデックス表)を統合。テスト観点は期待結果を変えず再編(v0.1 のテストケース ID が v0.2 で過不足なく一致することをスクリプトで確認済み)。

## 未対応事項・次にやること
- 文書ごとに未決 ID の採番が異なる(例: search-index の U-1 は `url/path`、deletions の U-1 はスナップショット項目名)。統一するかレビューで判断。architecture は X9 を U-25 として新規追加。
- 相互参照の整合(architecture ↔ api ↔ schema 3 文書)、deletions の判定順序・`failed` 理由コードと api の重複・矛盾は未確認。
- architecture の K8・K10 は v0.1 に無い表現を追加している(状態値の列挙、「受容事項(9)に書くのみ」)。K11 は独立の確定項目化。SD 該当行との照合が必要。
- architecture 18.1 の行番号は 0002 付録の転記で、SD 原文との再確認は未実施。
- api 5.2〜5.5 のキー名・パス・`failure_type` の値はエージェントの提案。SD の規約(§14 同期 HTTP・冪等、ID 設計、`if_seq_no`、ロック所有確認)との矛盾確認が必要。api 4.1 の応答 `{crawl_id,status}` は案。
- loreley-texts の確認状況表の「3.1 のマッピング方針」は区分が「方針(区分の明記なし)」。区分表現を他文書と揃えるか判断。
- 次: document-reviewer によるレビュー(フェーズ3)。
