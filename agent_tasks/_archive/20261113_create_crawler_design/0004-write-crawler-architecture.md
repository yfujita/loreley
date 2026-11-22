# 0004 crawler-architecture 作成(P2)とR2レビュー

- 日付: 2026-11-13
- 実施: P2(document-writer)、R2(document-reviewer。初回+再レビュー)
- 結果: R2 通過(Critical 0。Important は初回4件+再レビュー1件をすべて反映。再々レビューはレビュアーが不要と判定)

## 実施内容

- P2: `docs/v0.x/system-design/crawler/crawler-architecture-v0.1.md`(約970行)を新規作成。0002 の P2 章立て案(1〜13章)どおり。13章は小節構成(13.1 確認した事実、13.2 確定、13.3 案、13.4 未決、13.5 I-1〜I-7の定義、13.6 interface申し送りへの対応、13.7 他文書への依頼、13.8 課題の横断一覧)。
- R2 初回: Critical 0 / Important 4 / Suggestion 12 / Nitpick 5。Indexer突き合わせ(チェックリスト1〜6)は一致。件数照合 `enumerated_count == N_seen + E_missing` を全ケースで検算し成立を確認。`fetch_not_found` をスキップ扱いにする判断も妥当と判定。
- R2 再レビュー: 前回 Important は解消(I-C のみ `partial` の確定時点で新規 Important N-1 が出た)。N-1・Suggestion 3件・Nitpick 2件を反映。

## 変更ファイル

- `docs/v0.x/system-design/crawler/crawler-architecture-v0.1.md`(新規)

## Indexer設計・実装で確認した事実(13.1)

- ロック文書: `loreley-jobs` の `lock-{source_id}`。`owner`・`job_id`・`lease_expires_at`(すべて文字列、オフセット付きISO 8601)。所有は「要請の owner・job_id が一致し現在時刻 < lease_expires_at」。文書なし・null・形式不正は不所有。Indexerの仮定義と食い違いなし(I-5)。
- メンテナンスフラグ: ID `maintenance`、項目 `enabled`。`False` と明示されているときだけ「立っていない」(fail-closed)。
- `infra/opensearch/schema/jobs.json` は4項目・`dynamic: false` の仮定義で、`loreley-sources` の索引は作成物にない(I-6)。
- Indexer の Repository には `create` と条件付き削除がなく、ロック取得に必要なのでCrawler側で用意する。
- Indexer README が v0.9 を参照したままで、v0.10 で確定した事項(DELETE の `lock` ボディ等)を未決と書いている(I-7)。
- 未確認: OpenSearch実機での `create`・`if_seq_no` の挙動、Crawlerが書いたロック文書をIndexer実機が読む動作。

## 主な設計判断(いずれも「案」。確定はIndexer設計・PD承認済みとQ1〜Q3回答のみ)

- チャンク処理: 列挙はストリーミング、last-seen は取得より前に要請が必要なため、列挙をチャンクに区切り、チャンクごとに last-seen → 取得 → バッチ登録。取得と登録はバッチ単位で交互に進め、保持する原本はバッチ1つ分まで。
- 件数照合の不変条件: 列挙済みで登録されなかった新規文書はすべて `skipped_document_ids`(または `oversize_document_ids`)に載せる。このため `fetch_not_found` はスキップ扱い。`N_seen` は `last_seen_at >= crawl_started_at` の件数(api 4.4と一致)。
- リトライは interface 6章の `retry` 属性に従う。列挙の `Failed` はストリーミングで途中再開できないためリトライしない。
- 連続スキップ(連続20件で `failed`): 取得段階(取得成功でリセット)と登録段階(`status: ok` でリセット)で別カウンタ。api 3.5・SD 3.1 にない本書の独自拡張で、CA-U-16 として未決登録。`connector_internal_error` もこの計数に含める。
- リースの値はロック文書だけが持ち、ジョブ記録には持たせない。`queued` 中のロックは `lease_expires_at` を null(Indexerの所有判定で「不所有」となり矛盾しない)。ハートビートは独立し、同期HTTP待ち中もリースを更新。ロック解放前にハートビートを止める。
- 「削除中」は `loreley-sources.status=deleting` に置く案(CA-U-2)。ロックを失っても残り、新規クロールは起動されない。
- 終了通知: 内容は `loreley-jobs` に固定保存。`failed`・`cancelled` の項目省略は案(API-U-12。Indexer実装で採用中)。送信開始を `finish_notice.send_started_at` として記録し、記録前の取り消しは有効(`enumeration_completed` は送らず `cancelled` を新たに固定して送る。CA-P-42)。記録後の取り消しは送信リトライを止める。
- `partial`: 集計確定前は `true`、確定後(終了通知の内容の固定後を含む)は `false`。
- `document_id` の二重実装対策: バッチ応答の `document_id` を Crawler の算出値と実行時に照合し、不一致なら `failed`。共有テストベクタ・共有ライブラリの採否は CA-U-9。
- 事前確認(interface CI-U-6)は専用操作を置かず、`create` を開始通知の前に呼ぶ。
- `external_id` 衝突(interface CI-U-2): 案はジョブ `failed`(CA-U-6)。識別子エラー文書は登録せず件数と例をジョブ記録に残し `partially_succeeded`(CA-U-7)。
- サイズ超過(CI-U-3): Crawler の `max_raw_bytes`・`size_hint` による事前判定・別記録 `oversize`・ジョブstatusには影響しない・`oversize_document_ids` にCrawler側とIndexer側の両方を載せる(CA-U-4)。
- 終了通知のID一覧が Indexer の `SKIP_OVERSIZE_ID_LIMIT`(既定10,000)を超えると、Indexerは202で受理したうえで削除判定を `validation_failed` にする。警告閾値8,000件(仮値、CA-P-41)。

## 採番ID

- CA-K: 1〜20(確定。出典はIndexer設計のK番号・PD・Q1〜Q3回答のみ)
- CA-P: 1〜42(案)
- CA-U: 1〜16(未決): 1 数値の正式値 / 2 「削除中」の置き場所 / 3 メンテナンスフラグの書き込み手段 / 4 サイズ超過の記録先・影響・`error_count` の定義 / 5 ジョブ記録の保持期間 / 6 `external_id` 衝突の扱い / 7 `invalid_external_id` の記録方法 / 8 周期形式 / 9 二重実装対策の残り / 10 並行モデル / 11 索引・マッピングの作成担当 / 12 Admin API設計の不在 / 13 停止後の回復時に確認区分を書くか / 14 Crawler仮値とIndexer設定上限の整合手段(`SKIP_OVERSIZE_ID_LIMIT`・`JOBS_INDEX_NAME`を含む) / 15 `source_id` の文字種 / 16 連続スキップの取得段階への拡張
- 既存設計との不整合: I-7(新規。Indexer READMEが古い)。I-1〜I-6 は13.5に自己完結する形で定義。I-8・I-9 は欠番。13.8の横断一覧に CA-U 全件・CI-U-1〜10・I-1〜I-7・I-10・I-11 を掲載済み。

## 他文書への依頼(13.7)・申し送り

- **interface**: 11.5 の「I-1〜I-6 は横断一覧に掲載予定。現時点の定義は agent_tasks の 0001」を、architecture 13.5 への参照に差し替える必要がある(P4で実施)。
- **FS**: `create` でルートの存在確認を行うか、`size_hint`(ファイルサイズ)を返すか、マウント外れの分類。
- **crawler-api**: 受付の拒否条件(ロック保持中・削除中・メンテナンス中)、`force_delete`・`rewrite_mode` は手動のみ、ロック解放の対象、`source_delete` の受付で `status=deleting` を許す、設定レコードの `status` は登録・更新で変更不可、「設定の削除」はソース削除ジョブの手順5だけ、`source_id` の文字種。
- **module-structure**: ハートビートの並行モデル、共通処理・Indexerクライアント・Repository(`create`・条件付き削除)の配置。
- 横断一覧(13.8)には crawler-api(CAPI-U)・FS(CFS-U)・Web(CW-U)・module-structure(CM-)の分が未追記(P4で追記)。

## 未対応事項

- ユーザー判断候補(設計書内で案・未決として記録済み。レビュアー意見: 今すぐの判断は不要で、承認時にまとめて確認で足りる): ①`external_id` 衝突をジョブ `failed` にする案(CA-U-6) ②識別子エラー文書の `partially_succeeded` 扱いとサイズ超過のstatus影響(CA-U-4・7) ③「削除中」の置き場所(CA-U-2) ④連続スキップの取得段階への拡張(CA-U-16) ⑤周期形式=秒間隔(CA-U-8) ⑥メンテナンスフラグの書き込み手段(CA-U-3) ⑦Crawler仮値とIndexer設定上限の整合手段(CA-U-14)
- 他文書への修正要望: interface 11.5 の参照差し替え(P4)。
- 次: P3(api / FS / Web を並列作成。R3 ゲートつき)。
