# 0003 フェーズ1: v0.1(抽出版)の作成 作業記録

## 概要
承認済みプラン(0001)のフェーズ1。0002 の抽出マップに基づき、document-writer 3体を並行で動かして SD v0.8 から v0.1 を5文書作成した。仕様・数値は変えず、案/推測/未決の注記は残した。食い違い X1〜X14 は解消せず、各文書に未決/要確認として明記(解消は v0.2)。

## 変更(作成)したファイル
- docs/v0.x/system-design/indexer/indexer-architecture-v0.1.md(1〜20章。責務と境界、登録処理、競合制御、整合性、要約、Deletion Manager、突合、再インデックス、障害、バックアップ、非機能、テスト観点、確認状況、未決 U-1〜U-24、食い違い X1〜X14)
- docs/v0.x/system-design/indexer/indexer-api-v0.1.md(0〜11章。開始/終了通知、バッチ登録、部分更新、Status API、ソース削除・突合での呼び出し、未決・要確認)
- docs/v0.x/system-design/opensearch/schema/search-index-v0.1.md
- docs/v0.x/system-design/opensearch/schema/loreley-texts-v0.1.md
- docs/v0.x/system-design/opensearch/schema/loreley-deletions-v0.1.md
- (各文書末尾に確認状況表。Schema は型の定義が SD にないため JSON マッピングは未記載)

## 判断・設計上の理由
- SD で未定義の API(バッチ登録、`last_seen_at` 部分更新、ロック所有情報、ソース削除・突合の呼び出し、各リクエスト/レスポンス本文とエラーコード)は創作せず「SD v0.8 では未定義(N-4)」と明記。例の追加は v0.2 で「提案(案)」として行う。
- 判定番号の二重(X5)は「割合ルールの判定1〜3」「順1〜6」と呼び分けて併記(統一は v0.2)。
- X1 は本文側(Status API の利用者は Crawler、Admin View は Admin API 経由)で記述し、用語集との差を注記。X2 は `loreley-texts` 廃止が未決である旨を注記。
- §11 のテスト観点は E-11〜E-39、C-*、D-* の原文を全文確認のうえ ARCH 分を転記。Crawler 領域が主のケースは「Crawler 領域が主」と明記、転記しなかった ID は architecture 16.8 に行き先一覧。D-18 は欠番(X12)。
- 重複統合は2つの責務表と要約の整合(旧3か所)のみ。内容は変更なし。

## 未対応事項・次にやること
- 相互参照の解決確認(5文書が揃ったので v0.2 / レビューで確認)。
- api 側の `extract_failed`(第5章)・`N_seen`(第8章)と architecture の重複統合、deletions の判定順序・`failed` 理由コードと api 第9章の重複・矛盾確認。
- architecture の「根拠」列で旧 § を新章番号に置換した箇所の妥当性確認。17.1 の Crawler 領域「参考」行の要否。
- 食い違い X1〜X14 の解消(フェーズ2)。X7(`fetched_at`/`metadata` の所在)、X8(`url`/`path`)、X9(`summary_embedding`)等はユーザー判断を要する可能性があり、独断で確定しない。
- SD 自身が全文整合確認未完了(X13)。§3.7 冒頭は推測、§9・§11 は導出。
