# 0006 横断整合と課題の集約(P4)

- 日付: 2026-11-13
- 実施: P4(document-writer: architecture・interface・api・FS の修正。整合レビューは document-reviewer。FS 7.3・11.6 の古い記述はメインが直接修正)
- 結果: P4 の整合レビューを通過(Critical 0。Important 1件[N-1]と Suggestion・Nitpick をすべて反映。再レビューはレビュアーが不要と判定)

## 実施内容

R3 で出た他文書への修正要望(0005 の統合版)を、architecture と interface に反映した。

**crawler-architecture-v0.1.md(約1050行。R2通過後の変更)**
- 5.3 ジョブ記録の書き手を表に整理(CA-P-43)。受付が保存する `queued` 記録・`queued` の取り消し・管理者のロック解放による `running`→`failed` は API 側(受付と Scheduler。受付処理の共通化は module-structure で決める)、`running` 以降は Job Runner、すべての更新を読んだ版 `_seq_no`/`_primary_term` の条件付き更新にする。Runner は `failed`(`lock_released`)を見たら所有権喪失として止まる。ハートビートはロック文書だけを書く。
- 4.7 取り消し要求の伝達(CA-P-44): API 側が `job_id` キーのメモリ上フラグに記録して 202。Job Runner が確認点で参照する。単一プロセス前提(API と Job Runner が同一の Crawler プロセス)。再起動でフラグは消えるが `running` は回復で `failed`(`crawler_restart`)になるので整合する。確認点に達しない場合の脱出は、リース切れ `running` ならロック解放、リース期限内で止まった場合は Crawler の再起動による回復(5.8)だけ(MVP)。
- 7.7 I-43 を解消(CA-P-25 更新): `warnings` の表示用文字列は `locator` ではなく規則適用前の `external_id` の切り詰め。interface 3.2 は変更なし。
- `failure_detail`(CA-P-45・CA-P-48): 列挙失敗・`create` 失敗は分類名に加えて Connector の説明文(固定文+errno名+切り詰めた相対パス)を載せてよい。`external_id_collision` は「後に検出された1件の切り詰めた `external_id` と共有する `document_id`」(ID集合は文字列を持たず SHA-256 だけ保持するため、先に列挙された1件の文字列は手元に残らない。列挙の再実行で回収する案は採らない)。保存前に共通処理が文字数の切り詰め・制御文字のエスケープ・孤立サロゲートの置換を適用する(二重の防御)。
- 3.3 `record_type=job` のみジョブとみなす。2.1〜2.3 Admin API が `loreley-sources` を読み取り専用で直接読む経路(CA-P-46。決定は Admin API 設計時=CA-U-12/CAPI-U-2)。5.1 `acquired_at`(create 時に設定、ハートビートでは更新しない)、5.4 `queued` のロックと受付途中のロック(`acquired_at` が直近=仮値60秒)は解放しない(CA-P-47、最終決定は CAPI-U-7)。3.2・4.5 `connector_config` の確定時点(手順8)。9章 FS 3.3 参照。CA-U-15 に CAPI-P-15 を反映。
- 12章テスト観点 #25〜#30(取り消しと実行開始の競合、取り消し要求の伝達、再起動と取り消し要求、ロック解放と Runner の競合、解放しないロック、`send_started_at` の前後の取り消し)。
- 13.8 横断一覧を完成: CA-U-1〜16、CI-U-1〜11、CAPI-U-1〜10、CFS-U-1〜6、CW-U-1〜20、I-1〜I-7、I-10、I-11、I-20、I-30、I-40〜I-44(I-43 は解消済み)。ID・一行要約・参照先のみ。CM-(module-structure)分は P5 後に追記。
- 採番: CA-K 1〜20(変更なし)、CA-P 1〜48、CA-U 1〜16。

**connector-interface-v0.1.md(R1通過後の変更)**
- 11.5: I-1〜I-6 の所在を architecture 13.5 の参照に差し替え。6.1: ConnectorError の `message` を、固定文に加え errno 名・切り詰めた相対パスや識別子を含めてよいものに緩和(CI-P-17。案)。9章: 結論を Web 4.1 の差し替え文案に沿って改訂(構造は Web でも成立/I-40 は契約の設計判断=CI-U-11/I-41・I-42 は補足/I-43 は architecture 7.7 で解消済み/I-44 は Indexer の既存制約)。3.3 の 2(I-41)、3.3 の 6・10章 #8(I-42)の補足。CI-P-17 を番号順に整理。確定(CI-K)は 1〜10 のまま。新規: CI-P-17、CI-U-11。

**crawler-api-v0.1.md**: 「architecture で補う予定」の前方参照を実在の章参照に置換。5.7 の修正要望表は「反映済み」とし、残る未決を CAPI-U-2・CAPI-U-7・CAPI-U-4 に紐づけ。`message` の記述を interface 6.1 緩和に整合。関連文書表を更新。

**connector-file-system-v0.1.md**: 衝突時の記述(8.4・11.6)を「後に検出された1件+`document_id`」に整合。7.3・11.6 の architecture 旧状態の記述を現状(反映済み)に更新(メイン)。関連文書表を更新。

## 整合レビューの結果(要旨)

- R3 の修正要望はほぼ漏れなく反映され、Indexer 突き合わせ(ロック・リース・終了通知・ソース削除・件数照合)は崩れていない。ロック文書に `acquired_at` を足しても Indexer は3項目(owner・job_id・lease_expires_at)だけを読むため影響しない。
- 13.8 の横断一覧は、他文書の実在する ID と照合して網羅されていることを確認(重複・欠落・参照切れなし)。
- Important N-1(衝突の `failure_detail` が ID集合の保持量と両立しない)を、2件目のみ+`document_id` の案に統一して解消。

## 変更ファイル

- `docs/v0.x/system-design/crawler/crawler-architecture-v0.1.md`
- `docs/v0.x/system-design/crawler/connector/connector-interface-v0.1.md`
- `docs/v0.x/system-design/crawler/crawler-api-v0.1.md`
- `docs/v0.x/system-design/crawler/connector/connector-file-system-v0.1.md`

## module-structure(P5)への申し送り

- architecture 13.7: ハートビートの並行モデル(CA-U-10)、共通処理・Indexer クライアント・Repository(`create`・条件付き削除)の配置、受付処理の共通化(API と Scheduler)、API と Job Runner が同一プロセスであること(取り消しフラグ)。
- interface 11.6: CI-U-1(`document_id` の二重実装対策)、CI-U-9(Connector 呼び出しとリース更新の並行モデル)、`ConnectorType` と共通処理の配置。
- FS: `os.read`/`os.scandir` の差し替え(注入点)を実装に設ける(テストの決定性)。

## 未対応事項・ユーザー判断候補(設計書内では案・未決・I-n として記録済み。承認時にまとめて確認)

- 0005 の「未対応事項・ユーザー判断候補」と同じ(I-40、Q1「設定の削除」の解釈、glob確定・include_patterns の意味、`title` の取得、衝突時のジョブ failed、周期形式、メンテナンスフラグの書き込み手段 など)。
- 次: P5(crawler-module-structure。R5 レビュー)→ 13.8 への CM- 追記 → 最終レビュー(全6本の横断)→ task-reviewer。
