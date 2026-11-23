# Admin API 仕様書 v0.1

- 版: v0.1(本文。ゲート3(2026-11-23)の承認を反映済み。実装はスコープ外で、実装時確認事項(AAPI-U)が残る)
- 更新日: 2026-11-23
- 前版: なし(初版)
- 位置づけ: Admin View(管理者向けの画面)が使う **Admin API の仕様**。エンドポイント(パス・メソッド・主な応答項目・エラー code)、Admin 固有のエラー code、Crawler の 6 API との対応を定める。共通の規約(エラー応答の形式・共通 code・時刻・OpenAPI の方針・環境変数の命名)は `../api-base-design-v0.1.md`(以下 A)が正本。導出ロジック(リース切れ・ロック状態・死活判定)とデータアクセスの詳細は C(`admin-api-architecture-v0.1.md`。作成済み)が正本で、本書は**結果と参照**だけを書く。
- **この版は本文**: 骨子(フェーズ1)に、各エンドポイントのリクエスト・応答の全項目、全エラーパターン、読み取り元との対応、JSON の例(3〜8章)、Crawler の 6 API の写像表(9章)、失敗時の振る舞い(10章)を足した。ゲート2で確認した具体値・名前と回答は 11.7、本文で新たに決めた承認済みの案(ゲート3。2026-11-23)は 11.9、C に渡す事項は 11.10 にまとめた。
- 改訂履歴: v0.1 は初版。ゲート1(2026-11-22。ユーザー承認)で承認された方針と、ゲート2(2026-11-22。ユーザー承認)で承認された具体値・名前を「承認済みの案」として反映した(確定にしていない)。ゲート2の回答で、再実行の専用エンドポイント(`POST /jobs/{job_id}/rerun`)と書き込み系の `Origin` 検査は採用が選ばれなかったため、**不採用として扱った(当初は解釈。ゲート3(2026-11-23)で「不採用のままでよい」と明示回答を得た)**。前者は本書から外し(再実行は画面が EP-06 を呼ぶ。4.1)、後者は A 2.3 の未対応のリスクにした。これに伴い、EP 番号を振り直した(EP-01〜14。欠番なし。11.7 の注)。フェーズ2-1 で骨子を本文にした(新規の案は AAPI-P-24〜34・AAPI-U-9〜11)。R1(document-reviewer)の指摘を反映した(`job_id` のエンコード、`config_invalid` の分解の例外、更新の処理順の訂正、`-K-` の出典と区分の見直し、本文の規約、新規の案 AAPI-P-35〜38・AAPI-U-12 ほか)。フェーズ5の統合(2026-11-23)で、申し送りへの参照を A 9章の実番号(HO-1〜HO-50)に置き換え、更新日を統一した。R4 指摘の反映(2026-11-23): 11.9 に A 9.3 への参照を足した(B の内容は変更なし)。ゲート3の承認(2026-11-23)の反映: 案の区分を承認済みの案(ゲート3。2026-11-23)に、不採用の解釈とリスクの扱いをゲート3の明示回答に更新した(設計の内容は変更なし)。 PR #10 のレビュー指摘(2026-11-23)に対応して、**一覧の EP(EP-01・09・11)の `unavailable` を行単位にした**(2.2・2.11・3.1・5.1・6.1。AAPI-P-42。AAPI-P-16・25・27・30 の修正。承認済みの案(ゲート3)の修正で、確定にしていない)。 API 基盤の実装に合わせた追従改訂(`20261123_update_api_design_after_base_impl`。2026-11-23): 他文書の HO 範囲の表記を「HO-1〜HO-51」に統一した(設計の内容は変更していない)。
- 本書の対象は Admin API だけで、Search API・MCP の設計は含まない(A 1章)。SD・PD・crawler / indexer 設計・機能設計・画面仕様は変更しない。変更が要る点は A 9章(申し送り一覧。HO-1〜HO-51)に集約し、本書は該当する HO 番号で参照する。本タスクの 6 文書(A〜F)は、いずれも v0.1 で作成済み(A 0章の関連文書の表)。

## 0. この文書について

- 対象: `/api/admin/v1/` 配下の Admin API(14 本)。呼び出し元は Admin View(Web UI)だけ。
- 範囲外(参照のみ): Crawler の 6 API の契約(crawler-api)、Connector の `connector_config` の項目と検証(connector-file-system など)、エラー応答の形式・共通 code(A 5.2)、導出ロジック・環境変数の個別一覧(C)、フロントエンド(E・F)。
- 読み方: 1章で API の全体と対応表、2章で共通事項、3〜8章で領域別のエンドポイント(リクエスト・応答・エラー・出所・例)、9章で Crawler の 6 API の写像、10章で失敗時の振る舞い、11章に確認状況(ID・ゲート2確認事項・ゲート3で承認した案・C への引き継ぎ・検算結果)を置く。

区分の凡例は A 0章と同じ(確定 / 案 / 承認済みの案 / 未決 / 推測 / 導出)。承認済みの案は、**方針**がゲート1、**パス・項目名・code 名・数値**がゲート2(いずれも 2026-11-22)で承認されたもの。本タスクで新たに決めた案・導出・解釈の扱いは、ゲート3(2026-11-23)で承認されたもの。区分欄に承認したゲートを書く。ゲート3の承認により、本文中で「案」と書いた判断は、ID の区分欄が正で、承認済みの案(ゲート3)に読み替える。確定(`-K-`)にはしていない。ゲート2の回答で採用が選ばれなかった案は「不採用として扱った(解釈)」とし、ID は欠番として残す(ゲート3(2026-11-23)で「不採用のままでよい」と明示回答があった)。承認済みの案(ゲート3)を後から修正したものは、区分欄に「承認済みの案(ゲート3)の修正(PR #10 のレビュー指摘への対応。2026-11-23)」と書く。

ID 体系: `AAPI-K-n` / `AAPI-P-n` / `AAPI-U-n`。既存設計との不整合は `I-n`(本書の予約範囲は I-70〜79)。A の ID は `BAPI-*`。エンドポイントは本書の通し番号 `EP-nn`。

関連文書: A の 0章の表のとおり。主な入力は、機能設計(AF-1〜20)、画面仕様(`admin-view-v0.1.md` 10.4、`admin/*.md` の各「データ項目」)、crawler-api v0.4(1・3・4章)、crawler-architecture v0.4(3.2・3.3・4.8・5章・7.6・7.7)、`opensearch/schema/search-index-v0.10.md`・`loreley-deletions-v0.10.md`。

---

## 1. API 一覧

ベースは `/api/admin/v1`(承認済みの案。BAPI-P-1)。パス・メソッド・名前は承認済みの案(ゲート2。AAPI-P-3)。

### 1.1 エンドポイント一覧

| EP | メソッド + パス | 領域 | 用途 | 読み取り元 / 呼び出す Crawler API | 章 |
| --- | --- | --- | --- | --- | --- |
| EP-01 | `GET /sources` | sources | データソース一覧(S1。全件) | OpenSearch(`loreley-sources`・`loreley-jobs`・検索インデックス) | 3.1 |
| EP-02 | `GET /sources/{source_id}` | sources | データソース詳細(S2・S4) | 同上+ロック文書 | 3.2 |
| EP-03 | `POST /sources` | sources | データソース登録(S3) | Crawler `POST /sources` | 3.3 |
| EP-04 | `PUT /sources/{source_id}` | sources | データソース更新(S4。全置換) | Crawler `PUT /sources/{source_id}` | 3.4 |
| EP-05 | `POST /sources/{source_id}/delete-jobs` | sources | データソース削除ジョブの起動・再実行 | Crawler `POST /sources/{source_id}/delete-jobs` | 3.5 |
| EP-06 | `POST /sources/{source_id}/crawl-jobs` | クロール操作 | クロールの手動起動(`force_delete`・`rewrite_mode`) | Crawler `POST /sources/{source_id}/crawl-jobs` | 4.1 |
| EP-07 | `POST /jobs/{job_id}/cancel` | クロール操作 | ジョブの取消 | Crawler `POST /jobs/{job_id}/cancel` | 4.2 |
| EP-08 | `DELETE /sources/{source_id}/lock` | クロール操作 | ロック解放 | Crawler `DELETE /sources/{source_id}/lock` | 4.3 |
| EP-09 | `GET /jobs` | jobs | ジョブ一覧(J1。サーバー側ページング) | `loreley-jobs`(ジョブ記録・ロック文書) | 5.1 |
| EP-10 | `GET /jobs/{job_id}` | jobs | ジョブ詳細(J2) | `loreley-jobs`・`loreley-deletions` | 5.2 |
| EP-11 | `GET /sources/{source_id}/documents` | documents | 文書の確認(X1。タブごと。サーバー側ページング) | `loreley-jobs`(スキップ・サイズ超過記録)・検索インデックス | 6 |
| EP-12 | `GET /opensearch/cluster` | opensearch | OpenSearch のクラスタ状態(O1。1 応答) | OpenSearch(`cluster.health`・`cat.*`) | 7 |
| EP-13 | `GET /dashboard` | dashboard | コンポーネントの死活(D1) | 各コンポーネントの `/healthz`・OpenSearch の応答 | 8.1 |
| EP-14 | `GET /meta` | meta | cron のタイムゾーン・Dashboards の URL | 設定(環境変数)だけ | 8.2 |

- 「領域」列の「クロール操作」は章立て(4章)の区分である。**OpenAPI のタグは 6 種**(sources・jobs・documents・opensearch・dashboard・meta)で、操作の対象のリソースで決める(EP-06・EP-08 は `sources`、EP-07 は `jobs`。A 5.4。BAPI-P-23)。
- **Crawler の 6 API との対応**(crawler-api 1章): クロール起動 → EP-06(失敗ジョブの再実行も、画面が EP-06 を呼ぶ)、取り消し → EP-07、ロック解放 → EP-08、設定の登録 → EP-03、設定の更新 → EP-04、ソース削除ジョブ起動 → EP-05。6 API すべてに対応する Admin API があり、Admin API が Crawler に中継する操作はこの 6 つだけ(固定の経路。任意のパスは転送しない。SD §14.4)。
- **Admin API が書くものは何もない**: 書き込みはすべて Crawler の HTTP 経由で、`loreley-jobs`・`loreley-sources`・`loreley-deletions`・検索インデックス・メンテナンスフラグには書かない(AAPI-K-1。A BAPI-K-8)。EP-01・02・09〜12 は OpenSearch の読み取りだけで動くため、Crawler・Indexer が停止していても応答する(10章)。
- 設定の取得・一覧は Crawler に読み取り API を置かず、Admin API が `loreley-sources` を直接読む(CAPI-U-2。ユーザー回答 2026-11-16)。ジョブ状態・登録結果・削除結果は `loreley-jobs`・`loreley-deletions` を直接読む(CAPI-K-5)。
- メンテナンスフラグは書かず、読む専用の API も置かない(AF-19 は、拒否 code `maintenance_enabled` とジョブ・削除結果の失敗理由 `maintenance` の表示だけ。AAPI-P-36)。

### 1.2 AF → エンドポイントのトレーサビリティ

| AF | 機能 | EP | 備考 |
| --- | --- | --- | --- |
| AF-1 | データソース設定の登録・更新 | EP-03、EP-04、EP-14(タイムゾーン) | 項目別の検証エラー(2.4)、`config_invalid` の分解(2.5) |
| AF-2 | データソース設定の参照 | EP-01、EP-02 | |
| AF-3 | クロールの手動起動(強制削除・再書き込み) | EP-06 | |
| AF-4 | 実行待ち・実行中ジョブの取消 | EP-07 | 取消できるかの判定は EP-09・EP-10 の `cancellable` |
| AF-5 | 失敗ジョブの再実行(指定の引き継ぎ) | EP-10、EP-06 | 専用の EP はない。画面が EP-10 の応答(`source_id`・`force_delete`・`rewrite_mode`・`rerunnable`)をもとに EP-06 を呼ぶ(4.1) |
| AF-6 | 起動拒否の理由の表示 | EP-06 の 409 | `lock_held`・`maintenance_enabled`・`source_deleting`(2.3) |
| AF-7 | 止まったジョブの復旧 | EP-08、EP-02(`lock`)、EP-01・09・10(`stalled`) | ロック状態 7 値(2.9) |
| AF-8 | ジョブ状態・エラー・警告・起動時の指定・最終クロール完了日時 | EP-09、EP-10、EP-01・02(`last_crawl`・`last_completed_at`) | |
| AF-9 | 登録結果の参照 | EP-10(`registration`) | 途中 / 確定を `phase` で示す |
| AF-10 | 削除結果の参照(結果未確認・結果不明) | EP-10(`deletion`) | 確認結果の区分と `loreley-deletions` の現在値を併記 |
| AF-11 | スキップされた文書 | EP-11(`tab=skipped`) | 既存 / 新規 / 確認できません(`existence`) |
| AF-12 | 抽出失敗の文書 | EP-11(`tab=extract_failed`) | |
| AF-13 | 原本サイズ超過 | EP-11(`tab=oversize`) | |
| AF-14 | 要約未生成の文書 | EP-11(`tab=summary_pending`) | 要約の有効 / 無効は返さない(AAPI-P-9) |
| AF-15 | インデックス件数(データソースごと) | EP-01、EP-02(`document_count`)、EP-11(`document_count`・`tab_counts`) | |
| AF-16 | データソースの削除(確認操作つき) | EP-05 | 再実行も同じ呼び出し。確認操作は画面 |
| AF-17 | OpenSearch 最小ビュー | EP-12 | 読み取り専用 |
| AF-18 | Loreley ダッシュボード(死活) | EP-13 | |
| AF-19 | メンテナンス中の表示 | EP-06・EP-05 の 409 `maintenance_enabled`、EP-10 の `failure_reason`・`deletion` の理由 | 専用のエンドポイントはない |
| AF-20 | OpenSearch Dashboards への導線 | EP-14(`dashboards_url`) | 未設定ならリンクを出さない |

AF-1〜20 のすべてが、少なくとも 1 つのエンドポイントに対応する(11.8 の検算)。

### 1.3 画面 × エンドポイント対応表

| 画面・部品 | 使う EP | 備考 |
| --- | --- | --- |
| シェル(サイドバー) | EP-14 | Dashboards の外部リンク(AF-20) |
| D1 ダッシュボード | EP-13 | 30 秒ごとの自動更新(`refetchInterval`)。D1 は EP-14(`/meta`)を使わない(画面仕様 `dashboard-v0.1.md` に cron のタイムゾーン・Dashboards の URL を使う箇所がない。任意コンポーネントの `opensearch-dashboards` タイルは EP-13 の `state`、外部リンクはシェルが EP-14 から取る) |
| S1 データソース一覧 | EP-01、EP-14 | クライアント側ページング。DLG-1 は EP-06、DLG-2 は EP-05、削除の再実行は EP-05 |
| S2 データソース詳細 | EP-02、EP-14 | DLG-1(EP-06)、DLG-2・削除の再実行(EP-05)、DLG-5(EP-08) |
| S3 データソース登録 | EP-03、EP-14 | |
| S4 データソース編集 | EP-02、EP-04、EP-14 | 現在値の取得に失敗したらフォームを出さない(画面仕様) |
| J1 ジョブ一覧 | EP-09、EP-01(データソースの選択肢)、EP-07(DLG-3) | |
| J2 ジョブ詳細 | EP-10、EP-07(DLG-3)、EP-06(DLG-4。再実行)、EP-08(DLG-5)、EP-05(削除の再実行) | 実行待ち・実行中は 10 秒ごとの自動更新 |
| X1 文書の確認 | EP-11、EP-01(データソースの選択) | 手動更新のみ |
| O1 OpenSearch | EP-12 | 絞り込みは画面側(AAPI-P-6) |

### 1.4 画面データ項目の検算(画面のデータ項目 → 応答項目)

各画面仕様の「データ項目(想定)」の項目が、応答項目名として定義されていることを示す(項目の型・意味は 3〜8章。検算結果は 11.8)。

| 画面 | 画面仕様のデータ項目 | 応答項目(EP) |
| --- | --- | --- |
| D1 | コンポーネントごとの状態(正常 / 異常 / 未設定 / 判定不能) | `components[].state`(EP-13) |
| D1 | 確認時刻 | `components[].checked_at`、`checked_at`(EP-13) |
| D1 | 判定不能の理由 | `components[].reason`(EP-13) |
| D1 | 最終取得成功日時 | API は持たない(クライアントが取得成功時に保持。AAPI-P-8)。取得時刻は `checked_at` |
| D1 | 任意コンポーネントが設定されているか | `state=not_configured`(EP-13) |
| S1 | `source_id`、`schedule_cron`、`status`(`deleting` か否か) | `items[].source_id`・`schedule_cron`・`status`(EP-01) |
| S1 | 直近のクロールジョブの状態・日時・起動の種別・起動時の指定 | `items[].last_crawl`(`status`・`queued_at`・`started_at`・`finished_at`・`trigger`・`force_delete`・`rewrite_mode`)(EP-01) |
| S1 | リース切れの判定・ロックの有無 | `items[].last_crawl.stalled`、`failure_reason`(`lock_released`)(EP-01) |
| S1 | 削除中の補足(削除ジョブの状態) | `items[].delete_job`(EP-01) |
| S1 | 登録文書数 | `items[].document_count`(EP-01) |
| S1・J1・X1 | 行ごとの「取得できません」(「—」+「取得できません」) | `items[].unavailable`(行の取得失敗。キーは行の相対パス。EP-01・09・11。`null` +キーあり=取得できなかった、`null` +キーなし=値がない。2.2) |
| S1 | cron のタイムゾーン | `cron_timezone`(EP-14) |
| S1 | 最終クロール完了日時(AF-U-9) | `items[].last_completed_at`(EP-01) |
| S2 | 識別子・種別・取得設定 5 項目(`root`・`include_patterns`・`exclude_patterns`・`follow_symlinks`・`include_hidden`) | `source_id`・`connector_type`・`connector_config`(EP-02。不透明に返す。AAPI-P-20) |
| S2 | 実行周期・TTL・しきい値・最小件数 | `schedule_cron`・`ttl_seconds`・`ttl_days`・`ratio_threshold_percent`・`min_delete_count`(EP-02) |
| S2 | ロック状態 6 種(+取得失敗) | `lock.state`・`lock.job`・`lock.acquired_at`(EP-02) |
| S2 | 直近のジョブ(ID・状態・起動・起動時の指定・開始 / 終了・失敗の理由) | `last_crawl`(`job_id`・`status`・`trigger`・`force_delete`・`rewrite_mode`・`started_at`・`finished_at`・`failure_reason`)(EP-02) |
| S2 | インデックス(登録文書数) | `index.document_count`(EP-02) |
| S2 | cron のタイムゾーン | `cron_timezone`(EP-14) |
| S3・S4 | 入力: `source_id`・`connector_type`・`connector_config`(5 項目)・`schedule_cron`・TTL(日)・しきい値(%)・最小件数 | EP-03・EP-04 のリクエスト(`ttl_days`・`ratio_threshold_percent` ほか。AAPI-P-14) |
| S3・S4 | 項目別のエラー(`field`・`reason`、`config_invalid` の項目と固定文) | `details.errors[]`(2.4・2.5) |
| S3・S4 | 409 `source_already_exists`(削除中の識別子かの区別)、409 `source_deleting` | `details.status`(EP-03)、`source_deleting`(EP-04) |
| S3・S4 | 取得設定の上限値(100・1,024) | 返さない(画面が既定値で表示し、最終判定はサーバー。AAPI-P-20) |
| J1 | ジョブ ID・データソース・種別・起動・起動時の指定・状態・開始・終了・取消の可否 | `items[]`(`job_id`・`source_id`・`job_type`・`trigger`・`force_delete`・`rewrite_mode`・`status`・`stalled`・`failure_reason`・`queued_at`・`started_at`・`finished_at`・`cancellable`)(EP-09) |
| J2 | 種別・起動・起動時の指定・受付 / 開始 / 終了・リース期限 | EP-10 の同名の項目、`lease_expires_at` |
| J2 | 失敗の理由と説明 | `failure_reason`・`failure_detail`(EP-10) |
| J2 | 警告 | `warnings[]`(EP-10) |
| J2 | 登録結果(列挙・登録(新規・更新)・スキップ・サイズ超過・エラー、途中 / 確定) | `registration`(`enumerated_count`・`created_count`・`updated_count`・`unchanged_count`・`skipped_count`・`oversize_count`・`error_count`・`invalid_id_count`・`partial`・`phase`)(EP-10) |
| J2 | 削除結果(状態・理由・件数・しきい値・確認結果の区分・現在値) | `deletion`(`summary`・`confirmation`・`current`・`current_state`・`settings`)(EP-10) |
| J2 | 削除結果の現在値の取得時刻 | `deletion.fetched_at`(EP-10) |
| J2 | 取消できるか・最新のジョブか・終了通知後の取消か・再実行できるか | `cancellable`・`latest_for_source`・`cancel_after_finish_notice`・`rerunnable`・`rerun_blocked_reason`(EP-10) |
| X1 | スキップ記録(`source_id`・`document_id`・`external_id`・`stage`・`reason`・`attempts`・`consecutive_skips`・`first_skipped_at`・`last_skipped_at`・`last_job_id`)+「既存・新規」 | `items[]`(EP-11。`source_id` はパスで既知)+`existence` |
| X1 | 原本サイズ超過記録(`external_id`・`detected_by`・`size`・`first_detected_at`・`last_detected_at`・`last_job_id`) | `items[]`(EP-11。`document_id` を加える) |
| X1 | 抽出失敗(`title`・`external_id`・`mime_type`・`size`・`source_updated_at`・`last_seen_at`) | `items[]`(EP-11。`document_id` を加える) |
| X1 | 要約未生成(`title`・`external_id`・`mime_type`・`source_updated_at`・`indexed_at`) | `items[]`(EP-11。`document_id` を加える) |
| X1 | 登録文書数、各タブの総件数、深いページング | `document_count`、`tab_counts`、`total`・`window_limit`(EP-11) |
| O1 | クラスタ名・状態・ノード数・アクティブ / 未割り当て / 初期化中 / 移動中のシャード数 | `cluster`(`name`・`status`・`node_count`・`active_shards`・`unassigned_shards`・`initializing_shards`・`relocating_shards`)(EP-12) |
| O1 | インデックス名・状態・ドキュメント件数(取得不能は null) | `indices[]`(`name`・`status`・`document_count`)(EP-12) |
| O1 | シャード(インデックス名・番号・役割・状態・ノード名(未割り当ては null)) | `shards[]`(`index`・`shard`・`role`・`state`・`node`)(EP-12) |
| O1 | クラスタの全ノードの名前(シャードのないノードの行) | `nodes[].name`(EP-12) |

---

## 2. 共通事項

### 2.1 ページング・並べ替え・絞り込み(承認済みの案。AAPI-P-1。具体値は承認済みの案(ゲート2))

- **S1(EP-01)・O1(EP-12)は全件を返す**(クライアント側でページ分け・並べ替え・絞り込み。S1 は想定数十件。O1 の件数の上限は 7.1)。**J1(EP-09)・X1(EP-11)はサーバー側ページング**。
- クエリパラメータ: `page`(1 起点。既定 1)、`items_per_page`(`25`・`50`・`100` のいずれか。既定 25)、`sort`(並べ替えの項目。先頭に `-` を付けると降順。単一の項目だけ)。絞り込みは EP ごと(`source_id`・`status`・`tab`)。画面の URL のクエリ(`size` など)との対応は E・F。
- ページ付きの応答の形: `items`(配列)、`total`(条件に合う総件数)、`page`、`items_per_page`、`window_limit`。
- **深いページの上限(承認済みの案(ゲート2)): `page × items_per_page` が 10,000 を超える要求は 400 `invalid_request`(`details.errors=[{field:"page", reason:"range"}]`)**。OpenSearch の既定の取得上限(`max_result_window`。10,000。crawler-architecture 3.1 の検討と同じ)に合わせた。`total` は上限を超えても正確な件数を返し(`track_total_hits`)、画面が「表示できるのは先頭 10,000 件までです」と案内できる(`window_limit` を返す)。
- **既定の並び順(承認済みの案(ゲート2))**: J1 は `-queued_at`(新しい順。直列実行のため受付の順と開始の順は一致する。導出)。X1 は、スキップ `-last_skipped_at`、抽出失敗 `-last_seen_at`、原本サイズ超過 `-last_detected_at`、要約未生成 `-indexed_at`。**並べ替えられる項目は各 EP の 1 項目だけ**(昇順・降順。画面仕様の「並べ替え」列に一致)。同順位は ID(`job_id`・`document_id`)の昇順で決める(取りこぼし・重複を避ける。導出)。

### 2.2 部分失敗・`null`・`unavailable`(承認済みの案(ゲート3)。AAPI-P-16)

- 応答に複数の読み取り(例: ジョブ一覧+登録文書数)が含まれ、**一部だけ失敗した**ときは、**本体を 200 で返し、取得できなかった項目を `null` にして、`unavailable` に「項目のパス → 理由コード」を載せる**。画面は「—」+「取得できません」を出す(S1・S2・X1)。
- **`unavailable` の位置とキー(AAPI-P-42。PR #10 のレビュー指摘への対応で、AAPI-P-16・P-25 を修正)**: 失敗した読み取りの対象が**どの行か**を区別できるよう、一覧の EP は行ごとに持つ。
  - **単一のオブジェクトの応答(EP-02・EP-10・EP-12・EP-13・EP-14)**: 最上位の `unavailable`。キーは**応答の項目の正式なパス**(例 `index.document_count`、`deletion.current`、`lock`、`stalled`、`latest_for_source`)。
  - **一覧の EP(EP-01・EP-09・EP-11)**: **各 `items[i]` に `unavailable` オブジェクトを持つ(常に存在し、失敗がなければ `{}`)**。キーは**その行の中の項目の相対パス**(EP-01: `last_crawl`・`last_crawl.stalled`・`last_completed_at`・`delete_job`・`delete_job.stalled`・`document_count`。EP-09: `stalled`。EP-11: `existence`)。`JobBrief` が行の中に入れ子で入る EP-01 では、`stalled` は `last_crawl.stalled`・`delete_job.stalled` になる。一覧の EP の**最上位 `unavailable` は、行に属さない最上位の項目だけ**を載せる(EP-11 の `tab_counts.<タブ>`・`document_count`。常に存在し、EP-01・EP-09 では常に `{}`)。**`items[].…` 形式のキーは使わない**。
  - **規則**: 「`null` で、その行(または最上位)の `unavailable` にキーがある」=**取得できなかった**。「`null` でキーがない」=**値がない**(未実行・該当なしなど)、または保存値が読めない(下の保存値の規則)。
  - **行ごとに成否が分かれる読み取り**(`msearch` のサブ要求、ロック文書の `mget` の文書単位など)は、失敗した行だけにキーを付ける。**一括検索の全体(`msearch` 全体の例外、`existence` の一括検索、検索インデックスの件数の集計全体)や、主たる読み取りの一部が失敗したとき**は、**全行の `unavailable` に同じキーを付ける**(最上位ではなく行に)。
  - 例(EP-01。`source-a` は未実行で値がない、`source-b` は読み取りに失敗した。2 行の `last_crawl` はどちらも `null` だが、行の `unavailable` で区別できる):

```json
{ "items": [
    { "source_id": "source-a", "connector_type": "file_system", "schedule_cron": null, "status": "active",
      "last_crawl": null, "last_completed_at": null, "delete_job": null, "document_count": 0, "unavailable": {} },
    { "source_id": "source-b", "connector_type": "file_system", "schedule_cron": null, "status": "active",
      "last_crawl": null, "last_completed_at": null, "delete_job": null, "document_count": 12,
      "unavailable": { "last_crawl": "store_unavailable", "last_completed_at": "store_unavailable" } } ],
  "unavailable": {} }
```

- **理由コード**: `store_unavailable`(`loreley-jobs`・`loreley-sources`・`loreley-deletions` の読み取りの失敗)・`search_index_unavailable`(検索インデックスの読み取りの失敗)・`timeout`・`malformed`(保存済みの値が読めない。EP-02 の設定項目)。**理由コードは `timeout` を優先する**(失敗した読み取りが接続・読み取りのタイムアウトだったとき `timeout`、それ以外は対象別に `store_unavailable` / `search_index_unavailable`。遅いのか止まっているのかを区別する。C 5.8 の承認済みの案(ゲート3)。AAA-P-25)。`unavailable` は常に存在し、失敗がなければ空のオブジェクト(AAPI-P-25)。**OpenSearch が HTTP 200 のまま返す部分的な失敗(`mget` の文書単位の `error`・`found` が真偽値でないもの、検索の `_shards.failed>0`・形の異常)は成功と読まず、その読み取りの失敗として扱う**(「記録なし」・部分的な結果として使わない。検索の `timed_out=true` は `timeout`、それ以外は対象別。C 3.2・5.8 の承認済みの案(ゲート3)。AAA-P-39。実機での形は AAA-U-2)。
- **ジョブ記録・削除記録・ロック文書など、Crawler・Indexer が書いた値が読めない(欠落・型違い)ときは、その項目を `null` にする**(`unavailable` には載せない。`malformed` は EP-02 の設定項目だけ)。このため、`JobBrief` の `status`・`job_type`・`trigger`・`queued_at`、`registration` の件数・`partial`・`phase` などの型は `null` を許す(`phase` は `partial` が `null` のとき `null`)(2.11・EP-10。C 5.0 の承認済みの案(ゲート3)。AAA-P-25)。画面は `null` を「—」として扱う。
- **その EP の主たる読み取り**(EP-01 の `loreley-sources`、EP-02 の設定、EP-09 のジョブ一覧、EP-10 のジョブ記録、EP-11 の設定の存在確認と一覧、EP-12 全体)が失敗したときは、部分的な応答にせず、503 `unavailable`(A 5.2)。EP-12 は 1 カード分を 1 つの取得結果として扱い、概況だけ・マトリクスだけが取れた応答は返さない(画面仕様。AAPI-P-6)。
- 値がない(未実行・未到達・該当なし)ときも `null`。**その行(または最上位)の `unavailable` にキーがある `null` は「取得できなかった」、キーがない `null` は「値がない」**(上の規則)。

### 2.3 Admin 固有のエラー code(正本。承認済みの案(ゲート2。2026-11-22)。AAPI-P-2・P-19)

共通 code(`invalid_request`・`not_found`・`method_not_allowed`・`http_error`・`internal_error`・`unavailable`)と形式は A 5.2。Crawler の code は**同じ名前のまま返す**(写像の一般則。2.6)。下の表の「EP」列は、その code を返しうる EP で、3〜8章の各 EP の「エラー」表と一致する(共通 code は含まない)。

| HTTP | `code` | `retryable` | 条件 | `details` | EP |
| --- | --- | --- | --- | --- | --- |
| 400 | `config_invalid` | false | Crawler が `connector_config` の違反を返した(2.5) | `errors[]`(項目別。分解できたとき)、`crawler_message` | 03・04 |
| 404 | `source_config_not_found` | false | データソースの設定がない | — | 02・04・05・06・11 |
| 404 | `job_not_found` | false | そのジョブ ID の `crawl`・`source_delete` ジョブがない | — | 07・10 |
| 409 | `lock_held` | false | 起動しようとしたソースにロックがある(2.7) | `existing_job`、`lock_state`、`options_applied`、`requested` | 05・06 |
| 409 | `lock_in_use` | false | 解放できないロック(リース期限内の実行中・実行待ち、取得直後) | `existing_job`、`lock_state` | 08 |
| 409 | `source_deleting` | false | ソース削除中のため、起動・更新できない | — | 04・06 |
| 409 | `maintenance_enabled` | false | メンテナンスフラグが立っている | — | 05・06 |
| 409 | `source_already_exists` | false | 同じ識別子があり内容が異なる(削除中を含む) | `status`(`active`・`deleting`・null) | 03 |
| 409 | `job_not_cancellable` | false | `source_delete` ジョブは取り消せない | — | 07 |
| 409 | `job_already_finished` | false | 取り消そうとしたジョブがすでに終端 | `status` | 07 |
| 502 | `crawler_error` | false | Crawler の想定外の応答(500・契約外・Admin API の送った形の拒否) | — | 03〜08 |
| 503 | `crawler_unavailable` | true | Crawler が 503 `unavailable`(Store 層の障害)を返した | — | 03〜08 |
| 503 | `crawler_unreachable` | true | Crawler に届かなかった(接続拒否・名前解決失敗・接続のタイムアウト・TLS の確立の失敗(MVP は http 限定のため通常は起きない。9.1)。**起動時の回復中を含む**) | — | 03〜08 |
| 504 | `crawler_response_lost` | false | 要求を送った後に応答が来なかった(応答のタイムアウト・切断)。**操作の結果は不明** | `outcome_unknown=true` | 03〜08 |

- `lock_held`・`lock_in_use` 以外の 409 は、Crawler の同名の code(crawler-api 4.1〜4.4)を写す。
- **取消の `job_already_finished`(409)は成功に変換せず、そのまま返す**(承認済みの案(ゲート2)。AAPI-P-21)。画面が、すでに終端であることを「成功扱い」で表示する(AF-P-2。DLG-3 の仕様)。理由: Admin API の写像を恒等に保つため。
- `crawler_response_lost` のとき、起動系(EP-05・06)は、画面が状態を確認してから再操作する(再送すると、受付済みなら 409 `lock_held` で既存ジョブが分かる。crawler-api 3.4)。

### 2.4 `details.errors[]`(項目別のエラー)

- 形: `{ "field": "...", "reason": "...", "detail": "..." }`。`reason` の値は A 5.2(`required`・`type`・`format`・`range`・`exclusive`・`unknown_field`・`unsupported`。Admin API が使わない `read_only` は含めない)に、`config_invalid` 用の `config_invalid` を加える。`detail` は `config_invalid` のときだけ(違反の種類の固定文)。
- `field` は Admin API の**リクエストの項目名**(`ttl_days`・`ratio_threshold_percent`・`schedule_cron`・`connector_config.root`・`connector_config.include_patterns[2]` など)。Crawler が返した項目名は、2.5 の表で Admin API の名前に写す。値は載せない(A 5.2)。
- Admin API 自身が検証するもの(承認済みの案。AAPI-P-7): `ttl_days` / `ttl_seconds`(どちらか一方が必須・整数・**1 以上**(ゲート1の「非負」からの変更。AAPI-P-37)・int64 に収まる。両方・どちらもなしは `exclusive`・`required`)、`ratio_threshold_percent`(数値・0 以上 100 未満・小数第 2 位まで(`range`・`format`))、`min_delete_count`(整数・0 以上・int64 に収まる)、パスの ID の形式(A 5.3)、ページング(2.1)、`force_delete`・`rewrite_mode`(真偽値)。**`connector_config` の中身・`schedule_cron` の書式・`connector_type` の値は検証せず、Crawler に任せる**(複製しない。AAPI-K-5)。**しきい値の範囲を Crawler に渡す前に検証する**ことは確定(AAPI-K-2)。

### 2.5 `config_invalid` の分解(分解方式。方式は確定。細部は承認済みの案(ゲート2)。AAPI-K-5・P-12)

Crawler の `config_invalid`(400)は `message` だけを返し、項目別の構造を持たない(crawler-api 4.4。512 文字で切り詰め・エスケープ済み)。**Admin API が `message`(「項目名(配列は添字): 違反の種類」の固定文。最初の違反 1 件)を項目と違反の種類に分解して返す**(ユーザー回答 2026-11-22。0004)。**Connector の検証規則は複製しない**(案(b)は採らない)。

- 分解の規則(承認済みの案(ゲート2)): `message` を最初の `: `(コロン+空白)で 2 つに分け、前半が `^[A-Za-z_][A-Za-z0-9_]*(\[[0-9]+\])?$` に一致し、後半が空でなければ分解成功とする。
- 分解成功: 400 `config_invalid`。`details.errors=[{ "field": "<field>", "reason": "config_invalid", "detail": "<違反の種類の固定文>" }]`。`details.crawler_message` に元の `message` も載せる。`<field>` は、前半が `connector_config` **以外**なら `connector_config.<前半>`(例 `connector_config.include_patterns[2]`、`connector_config.root`)。**前半が `connector_config` 自身のとき(例外)は、プレフィックスを付けず `field="connector_config"`** とする(`connector_config.connector_config` にしない)。
  - 上の例外は、`file_system` Connector が項目名を `connector_config` 自身として返す 2 つの違反による: 「オブジェクトでない」「未知の項目がある」(`apps/crawler/src/loreley_crawler/connectors/filesystem/config.py`、connector-file-system v0.3 2.2。R1 I-2)。これらは**特定の入力欄・行に結びつかない**ので、画面は上部のアラートに出す(画面仕様 `sources-v0.1.md` 2.4「項目を特定できない場合は上部のアラート」。画面は常に 5 項目を送るため通常は起きない)。
  - 画面は、項目から該当の入力欄・行を決め、固定文を画面の文言に対応づける(画面仕様 `sources-v0.1.md` 2.3.2・2.4)。`detail` は **Connector が定める日本語の固定文**(例 「`/` で始まる絶対パスでない」「未知の項目がある」)で、画面は完全一致の対応表で照合する(AAPI-U-2)。照合できない固定文は上部のアラートに出す(画面仕様どおり)。
- **分解不能・切り詰め**(`message` が 512 文字に達している、前半が上の形に一致しない、`: ` がない): `details.errors` は**空**、`details.crawler_message` に元の `message` を載せる。画面は上部のアラートにフォールバックする(画面仕様どおり)。
- `crawler_message` は Crawler が入力値・errno・パスを含めない固定文(crawler-api 3.3。CFS-P-28)なので、そのまま載せてよい(導出)。Connector が増えて説明文に切り詰めた相対パスなどが入りうる場合は、A 5.2 の「値を載せない」規則との整合を見直す(AAPI-U-2)。
- この方式は **`message` の形式と日本語の固定文に依存する**(Crawler・Connector 側の変更で壊れうる)。Crawler が構造化した項目別の情報を返すようになれば不要になる(HO-11。AAPI-U-2)。
- 照合の結果、画面仕様の期待(`sources-v0.1.md` 2.3.2 の対応表の Crawler の固定文、2.4)との食い違いは、`connector_config` 自身の違反を除いてなかった(上記。画面仕様の側は変更不要。I-n にしない)。

```json
{ "error": { "code": "config_invalid", "message": "connector_config is invalid", "retryable": false,
  "details": { "errors": [ { "field": "connector_config.include_patterns[2]", "reason": "config_invalid", "detail": "`\\` を含む(エスケープはない)" } ],
               "crawler_message": "include_patterns[2]: `\\` を含む(エスケープはない)" } } }
```

### 2.6 Crawler 写像の一般則(承認済みの案。AAPI-P-2。API ごとの詳細は 9章)

| Crawler の応答 | Admin API の応答 |
| --- | --- |
| 2xx(200・201・202) | 同じステータス。本文は Admin API の DTO に変換 |
| 400 `invalid_request`(`details.errors` の項目が `connector_type`・`connector_config`・`ttl`・`ratio_threshold`・`min_delete_count`・`schedule_cron`) | 400 `invalid_request`。項目名を Admin API の名前に写す(`ttl` → `ttl_days` / `ttl_seconds`(送ったほう)、`ratio_threshold` → `ratio_threshold_percent`)。理由はそのまま |
| 400 `invalid_request`(`body`・`unknown_field`・`read_only`、または Admin API が検証済みの `source_id` の形式。`source_id` はパスにも登録の本文にもあり、Admin API が先に同じ規則で検証する) | 502 `crawler_error`(Admin API が送らない・検証済みの違反。Admin API の不具合) |
| 400 `invalid_request`(項目が `job_id`)・404 `not_found`(EP-07 の `job_id` に `%`・`?` などを含むとき。2.12) | **404 `job_not_found`**(Crawler が生成する ID の形ではなく、存在しない ID と同義。AAPI-P-39) |
| 400 `config_invalid` | 400 `config_invalid`(2.5) |
| 404 `source_config_not_found`・`job_not_found` | 404 同名 |
| 404 `not_found`・405・`http_error`(契約外の呼び出し) | 502 `crawler_error` |
| 409(`lock_held`・`lock_in_use`・`source_deleting`・`maintenance_enabled`・`source_already_exists`・`job_not_cancellable`・`job_already_finished`) | 409 同名。`details` は 2.3・2.7 |
| 500 `internal_error`、契約外の 2xx・JSON でない本文 | 502 `crawler_error` |
| 503 `unavailable` | 503 `crawler_unavailable` |
| 接続前の失敗(接続拒否・名前解決失敗・接続のタイムアウト・TLS の確立の失敗) | 503 `crawler_unreachable`(起動時の回復中もここ) |
| 要求を送った後の応答喪失(応答のタイムアウト・切断) | 504 `crawler_response_lost` |

- Crawler の `message` は、`config_invalid` 以外では Admin API の応答に含めない(固定文を使う。A 5.2)。
- **読み取りは継続し、書き込み系(EP-03〜08)だけが失敗する**: Crawler が落ちている・回復中でも、EP-01・02・09〜12 は OpenSearch の読み取りだけ、EP-14 は設定だけで応答する(EP-13 は各コンポーネントの確認結果を返す)(AAPI-P-2。10章)。

### 2.7 `lock_held` の 409(承認済みの案(ゲート1)。応答の形は承認済みの案(ゲート2)。AAPI-P-35・P-13)

SD §14.4 の「重複起動を冪等な成功として扱う」案は採らない(I-70。HO-4)。**成功扱いにせず 409 で、既存ジョブと「指定は反映されていない」を返す**(ゲート1の承認 2026-11-22。0003。承認済みの案。AAPI-P-35)。

```json
{
  "error": {
    "code": "lock_held",
    "message": "the source is locked by another job",
    "retryable": false,
    "details": {
      "options_applied": false,
      "requested": { "force_delete": true, "rewrite_mode": false },
      "existing_job": {
        "job_id": "job-20261122T010203Z-3fa9c2d1", "job_type": "crawl", "status": "running",
        "trigger": "schedule", "lease_expires_at": "2026-11-22T01:07:03.456Z"
      },
      "lock_state": "held_crawl"
    }
  }
}
```

- `options_applied`: 常に `false`(指定した `force_delete`・`rewrite_mode` は、起動していないため既存ジョブにも反映されない)。`requested`: 受け取った指定(`force_delete`・`rewrite_mode`)。EP-05 では `options_applied` と `requested` は省く(指定がないため)。
- `existing_job`: Crawler の `details.existing_job`(crawler-api 4.1)を写す(`job_id`・`job_type`・`status`・`trigger`・`lease_expires_at`。ジョブ記録がない・読めない値は `null`)。
- `lock_state`: 2.9 の 7 値。Admin API が `loreley-jobs` のロック文書・ジョブ記録を読んで導出する(読めなければ `unknown`)。`lease_expired`・`orphan` のとき、画面は成功扱いにせず警告して AF-7(ロック解放)へ導く(画面仕様 7.7)。
- EP-08 の `lock_in_use` も同じ `existing_job`・`lock_state` を持つ。

### 2.8 単位の変換(承認済みの案(ゲート2)。AAPI-P-14)

画面の入力単位は TTL=日、しきい値=%(画面仕様 `sources-v0.1.md` 2.3.0。ゲート C 承認済み)。**Admin API が Crawler の値(TTL=秒、しきい値=0〜1 の割合)に変換する**(`CAPI-U-3` への回答)。

- リクエスト: `ttl_days`(整数)**または** `ttl_seconds`(整数)のどちらか一方。日で割り切れない既存値(Crawler API を直接使って登録されたものなど)を S4 で編集できるようにするため、秒の指定も受ける(画面が「N 秒」表示に切り替える)。`ratio_threshold_percent`(小数第 2 位までの数値。0 以上 100 未満)。変換は十進数で行う(浮動小数の誤差を避ける。導出)。`ttl` の秒 = `ttl_days` × 86,400。割合 = `ratio_threshold_percent` ÷ 100。
- 応答: `ttl_seconds`(保存値)と `ttl_days`(日で割り切れるときだけ整数。それ以外は `null`)、`ratio_threshold_percent`。**応答の `ratio_threshold_percent` は、保存値(0〜1 の数値)の十進数の文字列表現を介して厳密に 100 倍する**(`0.29` → `29`。浮動小数の誤差を出さない。AAPI-P-38)。
- **注意(AAPI-P-38。承認済みの案(ゲート3))**: Crawler の API を直接使って登録された値のように、保存値が**小数第 3 位以下**を持つ(例 `0.12345` → 12.345 %)と、応答の `ratio_threshold_percent` は小数第 2 位を超える。画面がそのまま再保存すると、リクエストの検証(小数第 2 位まで)で `format` のエラーになる。`ttl_seconds` のような逃げ道(別の項目での指定)は、項目の追加になるため足さない。代わりに、**画面が小数第 3 位以下を持つ値を表示するときに注意を出し、丸めた値を確認してから保存する**(画面の責務。E・F)。ゲート3(G3-5。2026-11-23)で現案どおり承認された(別の逃げ道は足さない)。
- **既定値は補わない**(`ttl`・しきい値・最小件数は必須。画面仕様の #2。CAPI-P-7)。

### 2.9 ロック状態 7 値と導出されるフラグ(結果は本書、導出は C。承認済みの案(ゲート3)。AAPI-P-17・AAPI-P-18。`lock_state` の値の名前もゲート2の対象外の案)

| `lock_state` | 意味 |
| --- | --- |
| `none` | ロック文書がない |
| `held_crawl` | `crawl` ジョブが保持している(実行待ち、または実行中でリース期限内) |
| `held_delete` | `source_delete` ジョブが保持している(同上) |
| `lease_expired` | 実行中のジョブのリース期限が過ぎている(期限が null・形式不正も過ぎたとみなす。crawler-api 4.3) |
| `orphan` | **ジョブ記録がなく、ロックの取得から 60 秒を超えている**(`acquired_at` が読めない値も含む。crawler-api 4.3 の「取得直後でない」)、またはジョブが終端状態(孤児ロック) |
| `just_acquired` | ジョブ記録がなく、**ロックの取得から 60 秒以内**(受付の途中の可能性。仮値 60 秒。crawler-architecture 11章。Crawler の値との同期は AAPI-U-6)。`orphan` と排他 |
| `unknown` | 読めない・取得できない。**ジョブ記録はあるが `status`(または `job_type`)が読めない**場合も `unknown`(crawler-api 4.3 の `status` が読めない場合の 409 `lock_in_use` に対応。AAPI-P-17) |

- 判定の順序(結果の定義。導出は C): ロック文書がなければ `none`。ロック文書があれば、`job_id` でジョブ記録を引く(**読む順序は、ロック文書 → ジョブ記録**。逆にすると、ロックの解放・ジョブの終了の途中の状態を誤って `stalled` と判定する偽陽性が出うる。C へ)。ジョブ記録がなければ、`acquired_at` で `just_acquired` / `orphan`。ジョブ記録が終端なら `orphan`。実行待ち・実行中でリース期限内なら `held_*`、リース切れなら `lease_expired`。
- **「ロック文書 → ジョブ記録の順」の満たし方**(C 5.2 の承認済みの案(ゲート3)。AAA-P-18): EP-02・EP-08 の 409 の `lock_state` は、上の順で読む。一覧(EP-01・09)・EP-10 は、どのジョブが実行中かをジョブ記録を読むまで知らないためロックを先に読めない。代わりに、ロックの不一致を見たときに**ロック文書 → ジョブ記録の順で読み直す**(確認読み)ことで偽陽性を避ける。
- `stalled`(ジョブの項目): **実行中(保存上)かつリース期限超過**(リース切れ。ゲート1の方針。AAPI-P-4)。期限が `null`・形式不正のものも超過とみなす(crawler-api 4.3)。**実行中なのにロック文書がない、またはロック文書が別のジョブのものであるジョブも、確認読みの後に `true` とする**(推測。ロックを持たないジョブは Indexer が書き込みを拒否するため止まる。AAPI-P-27・AAPI-U-9)。ロック文書を読めず判定できないときは `null`(その行(または最上位)の `unavailable` の `stalled` のキー(EP-01 の入れ子では `last_crawl.stalled`・`delete_job.stalled`)。2.2)。実行中以外は `false`。画面は「失敗(リース切れ。ロック未解放)」と表示する。解放後は保存上も `failed`(`failure_reason=lock_released`)になる。
- `cancellable`: `crawl` ジョブで、実行待ち、または実行中でリース期限内(リース切れ・`source_delete`・終端は不可)。`stalled=null` のときは `false`(安全側。AAPI-P-27)。
- `latest_for_source`: そのデータソースで最新の `crawl` ジョブ(受付日時の降順の先頭)か。
- `rerunnable`・`rerun_blocked_reason`(**画面が再実行の操作を出し分けるための導出フラグ**。サーバー側では強制しない。ゲート2で専用の再実行 EP は採用されなかった): `crawl` ジョブで、保存上 `failed`、`latest_for_source`、データソースが削除中でないとき `rerunnable=true`。そうでないときの `rerun_blocked_reason` は `not_crawl`・`not_failed`・`stalled`(ロック未解放)・`superseded`(より新しいジョブがある)・`source_deleting`(設定が `status=deleting`)・`source_missing`(データソースの設定がない=削除済み。**案(AAPI-P-41)。画面仕様 `jobs-v0.1.md` 2.3 に理由の文言はなく、「削除中」と表示すると削除済みのソースを誤って示すため、専用の値にした**)(`rerunnable=true` のときは `null`)。`rerunnable=null` になるのは、`stalled` または `latest_for_source` が決まらないとき、または**データソースの設定の読み取りに失敗したとき**(C 5.3 の評価順。AAA-P-19)。
- `cancel_after_finish_notice`: ジョブが `cancelled` で、終了通知の送信を始めた後に取消が受け付けられた(`finish_notice.send_started_at` がある。CAPI-U-6。画面は「取消は削除を止めていません」を出す)。

### 2.10 安全性(認証なしの `api`。A 2.3 の補足)

- **認証がない**ため、到達できる人は次を実行できる: ソース削除ジョブの起動(EP-05。そのソースの全文書・記録・設定が消え、取り消せない)、`force_delete=true` のクロール起動(EP-06。割合ルール・最小件数ルールを無視して削除する。再実行(AF-5)で引き継がれる場合を含む)、取消(EP-07)、ロック解放(EP-08)、データソース設定の登録・更新(EP-03・EP-04)。API に確認や二重送信の防止はなく、誤操作の防止は画面の確認ダイアログに委ねる。
- **`connector_config.root` は、Crawler のコンテナから見える任意のパスを指定できる**。Admin API は `connector_config` を検証・加工せず Crawler に中継する(AAPI-P-20)。読めるのは Crawler に `:ro` でマウントしたディレクトリだけ(A 2.3)。
- **エラー本文に入力値・認証情報・パスを出さない**: `details.errors` は項目名と理由だけ(A 5.2)。`crawler_message` は Crawler が入力値・errno・パスを含めない固定文(2.5)。EP-02 が返す `connector_config` は、Connector の規則で認証情報を参照名だけにする(PD §4.8。`file_system` には認証情報がない)。
- **ブラウザ経由の書き込み要求への保護はない**(悪意あるウェブページが、ユーザーのブラウザから localhost の `api` に書き込み要求を送る攻撃)。`Origin` 検査は、ゲート2の回答で採用が選ばれなかったため不採用として扱った(解釈。ゲート3(2026-11-23)で不採用のままでよいと確認済み)。単純なリクエスト(GET・HEAD・POST)で届くのは本文なしの POST の EP-05・06・07(EP-03 は `Content-Type: application/json` を要する。2.12)。EP-04(PUT)・EP-08(DELETE)は preflight が要り CORS 未許可のため届かず、EP-08 は DNS rebinding でのみ到達しうる。DNS rebinding なら全 EP が対象。リスクは**ゲート3(2026-11-23)で受け入れると回答があった**(README に注意書きを置き、軽い緩和は足さない。リスクがなくなったわけではない)。受け入れた未対応のリスクとして A 2.3・BAPI-U-8 に登録した。

### 2.11 共通の DTO(応答の部品。承認済みの案(ゲート3)。AAPI-P-25)

3章以降の応答で共通に使う部品。**項目は省略せず、値がないときは `null`**(A 5.1)。時刻は UTC の ISO 8601・ミリ秒(A 5.1)。

**`SourceSettings`**(EP-02〜04)

| 項目 | 型 | 内容 |
| --- | --- | --- |
| `source_id` | string | 識別子 |
| `connector_type` | string | 種別(MVP は `file_system`) |
| `connector_config` | object | 取得設定。保存済みの値をそのまま返し、補完・加工しない(AAPI-P-20) |
| `ttl_seconds` | integer | TTL(秒。保存値) |
| `ttl_days` | integer / null | TTL(日)。秒が 86,400 で割り切れるときだけ。それ以外は `null` |
| `ratio_threshold_percent` | number | 削除の割合しきい値(%)。保存値(0〜1)× 100 |
| `min_delete_count` | integer | 最小件数 |
| `schedule_cron` | string / null | cron 式。`null` は手動のみ |
| `status` | string | `active` / `deleting` |
| `updated_at` | datetime | 設定の更新日時 |

**`SourceListItem`**(EP-01 の `items[]` の 1 行)

| 項目 | 型 | 内容 |
| --- | --- | --- |
| `source_id`・`connector_type`・`schedule_cron`・`status` | string / string / string(null) / string | 3.1 |
| `last_crawl`・`delete_job` | `JobBrief` / null | 3.1。**`JobBrief` はこの行の中に入れ子で入るため、`stalled` の失敗は行の `unavailable` の `last_crawl.stalled`・`delete_job.stalled`(相対パス)になる** |
| `last_completed_at`・`document_count` | datetime / null、integer / null | 3.1 |
| `unavailable` | object | **この行の失敗**(常に存在。なければ `{}`)。キーは行の中の項目の相対パス(2.2) |

**`JobListItem`**(EP-09 の `items[]` の 1 行)= `JobBrief` の全項目 + `unavailable`(object。この行の失敗。常に存在。キーは `stalled`。2.2)。

**`JobBrief`**(EP-01・02・09。J1 の行・S1 の最終クロール・S2 の直近のジョブ。**`JobBrief` 自体は `unavailable` を持たない**。EP-01・02 では入れ子の外側の行(または最上位)の `unavailable` が、EP-09 では `JobListItem` の `unavailable` が失敗を示す)

| 項目 | 型 | 内容 |
| --- | --- | --- |
| `job_id`・`source_id` | string | |
| `job_type` | string / null | `crawl` / `source_delete`。**保存値が読めないときは `null`**(2.2) |
| `trigger` | string / null | `manual` / `schedule`。読めないときは `null` |
| `status` | string / null | 保存上の状態: `queued` / `running` / `succeeded` / `partially_succeeded` / `failed` / `cancelled`。読めないときは `null`(このとき `stalled=false`・`cancellable=false`) |
| `force_delete`・`rewrite_mode` | boolean / null | 受付時の指定。`source_delete` と、記録にない場合は `null` |
| `queued_at` | datetime / null | 受付。読めないときは `null` |
| `started_at`・`finished_at` | datetime / null | 開始・終了。未到達は `null` |
| `failure_reason` | string / null | `failed` のときの理由コード(`config_invalid`・`lock_released` など。Crawler のコードをそのまま返す。AAPI-U-3)。それ以外は `null` |
| `stalled` | boolean / null | リース切れか(2.9)。`status=running` 以外は `false`。ロック文書を読めず判定できないときだけ `null`(その行または最上位の `unavailable` の `stalled` のキー(EP-01 の入れ子では `last_crawl.stalled`・`delete_job.stalled`)を伴う。2.2) |
| `cancellable` | boolean | 取消できるか(2.9)。`stalled` が `null` のときは `false`(安全側) |

**`JobAccepted`**(EP-05・06 の 202)

| 項目 | 型 | 内容 |
| --- | --- | --- |
| `job_id` | string | 受け付けたジョブ(Indexer の `crawl_id` と同値。CA-P-1) |
| `job_type` | string | `crawl`(EP-06) / `source_delete`(EP-05) |
| `source_id` | string | |
| `status` | string | `queued` |
| `trigger` | string | `manual` |
| `force_delete`・`rewrite_mode` | boolean / null | 記録した指定(EP-05 は `null`。Crawler の応答に含まれない) |
| `queued_at` | datetime | 受付 |

**`ExistingJob`**(`lock_held`・`lock_in_use` の `details.existing_job`、`lock.job`)

| 項目 | 型 | 内容 |
| --- | --- | --- |
| `job_id` | string | ロック文書が指すジョブ |
| `job_type`・`status`・`trigger` | string / null | ジョブ記録がない(孤児ロック)・値が読めないときは `null` |
| `lease_expires_at` | datetime / null | ロック文書のリース期限。実行待ちは `null`。**Crawler は、値があるのに日時として読めないときだけ `0001-01-01T00:00:00.000Z` を返す(crawler-api 4.1)。Admin API はそのまま通し、画面は期限切れとして扱う**(I-73) |

### 2.12 入力の規約(承認済みの案(ゲート3)。AAPI-P-24。形式は A 5.1〜5.3)

- **パスの ID**: `source_id` は `^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$`(半角英数字で始まり、半角英数字・`.`・`_`・`-` だけ、256 文字以内。CAPI-K-6・P-15)、`job_id` は空でなく、UTF-8 で 256 バイト以内、制御文字なし(CAPI-P-18)。違反は 400 `invalid_request`・`details.errors=[{field:"source_id"|"job_id", reason:"format"}]`。**`/` を含む値は Admin API のルーティングで 404 `not_found`**(Crawler の `%2F` の扱いと同じ。crawler-api 3.3)。Crawler には検証済みの ID だけを送り、**URL に埋めるときは `source_id`・`job_id` とも `quote(value, safe="")` で符号化し、その後 `.` を `%2E` に置換する**。`source_id` の文字種は符号化で変わらない(`.` を含む `source_id` は `%2E` になる)。`job_id` は検証が緩く(`%`・`?`・`#`・`.` などを含みうる)、符号化しないとパスが崩れ、固定の経路にならないため(R1 I-1。`job_id` の検証規則は変えない)。**`quote` は `.` を符号化しないが、urllib3 は URL の正規化でドットセグメントを除去する(`job_id=".."` は `/jobs/../cancel` → `/cancel` に崩れる。`%2E` は保持される。urllib3 2.8.0。R2 I-1 が確認)ため、`.` を `%2E` に置換する**(承認済みの案(ゲート3。2026-11-23)。AAPI-P-24。代案の「`.`・`..` だけの `job_id` を検証で拒否する」は採らない。11.9)。エンコード後の ID を Crawler が `%2F`(404 `not_found`)・`%3F`・`%25`・`%2e%2e`(400 `invalid_request`)として扱う挙動は、crawler-api 3.3「パスの扱い」(契約外・TestClient での実測)に由来し、実機では未確認(AAPI-U-12)。Crawler が 404 `job_not_found` を返せば Admin API の 404 `job_not_found` になる。**`job_id` を理由とする 400 `invalid_request`・404 `not_found` も、EP-07(取消)では 404 `job_not_found` に写す**(Crawler が生成する ID の形ではなく、存在しない ID と同義。AAPI-P-39)。`source_id` は Admin API が文字種を検証済みなので、Crawler のこれらの応答は 502 `crawler_error`(2.6)。EP-10 は Admin API が `loreley-jobs` から直接読むので、存在しない ID は 404 `job_not_found` で揃う。
- **クエリ**: 各 EP が定義したものだけ。未知のクエリは 400 `invalid_request`・`unknown_field`。値の型・範囲の違反は `type`・`range`、列挙値の違反は `unsupported`。
- **本文(EP-03・04・06)**: **本文が空(`Content-Length: 0` または本文なし)なら `Content-Type` を問わず許し、`{}` として扱う**(EP-06 は本文なしと `{}` を同じとして扱う。EP-03・04 では必須の項目の欠落になる)。**本文があるとき**は JSON のオブジェクトで、`Content-Type: application/json` でないもの・JSON として読めないもの・1 MiB 超は 400 `invalid_request`(`details` なし。A 5.1)。オブジェクトでなければ `[{field:"body", reason:"type"}]`。未知の項目は `unknown_field`(項目名は A 5.2 の整形をして載せる)、必須の欠落は `required`、型の違反は `type`(型は厳密。数値・真偽値を文字列から変換しない。`30.0` は整数ではない)。違反は**すべて**返す。
- **本文を読まない EP**(GET、EP-05・07・08): 本文があっても無視する(crawler-api 3.2 と同じ)。EP-06 は本文なし・`{}` を同じとして扱う(上)。
- **検証の順序**: パス → クエリ → 本文の形式・型 → 範囲(Admin API の検証)→ Crawler・OpenSearch の呼び出し(A 5.3)。Admin API の検証に通らない要求は Crawler に送らない。

---

## 3. データソース(S1〜S4)

各 EP の「エラー」表は、その EP 固有のものだけを書く。**全 EP 共通**: 404 `not_found`(未定義のパス)・405 `method_not_allowed`・500 `internal_error`(A 5.2)。ID を取る EP は 400 `invalid_request`(`source_id`・`job_id` の `format`。2.12)、本文を取る EP は本文の形式違反の 400(2.12)を持つ。各 EP の応答の「出所」は、読み取り専用で読むインデックスとフィールド(導出の定義は C)。

### 3.1 EP-01 `GET /sources`

データソースの一覧(S1)。X1・J1 のデータソースの選択肢にも使う。**全件返却**(ページングなし。AAPI-P-1)。並べ替え・絞り込み・ページ分けは画面側(S1 は想定数十件)。

**リクエスト**: パス・クエリ・本文なし。

**応答(200)**: `items[]`(`SourceListItem`。2.11)、`unavailable`(最上位。**常に `{}`**。2.2)。`items[]` は `source_id` の昇順。**取得できなかった項目は、その行の `unavailable`(相対パスのキー)に載る**(2.2)。

| 項目 | 型 | `null` / 備考 | 出所 |
| --- | --- | --- | --- |
| `items[].source_id` | string | | `loreley-sources` の `source_id` |
| `items[].connector_type` | string | | 同 `connector_type` |
| `items[].schedule_cron` | string / null | `null` は手動のみ | 同 `schedule_cron` |
| `items[].status` | string | `active` / `deleting` | 同 `status` |
| `items[].last_crawl` | `JobBrief` / null | 未実行は `null`(行の `unavailable` にキーなし)。取得失敗も `null`(**行の `unavailable` の `last_crawl`** にキーがある) | `loreley-jobs`: `record_type=job`・`job_type=crawl`・その `source_id` の `queued_at` が最新の 1 件(AAPI-P-4) |
| `items[].last_completed_at` | datetime / null | 成功・一部成功のジョブがなければ `null`。取得失敗も `null`(**行の `unavailable` の `last_completed_at`** にキーがある) | 同: `status` が `succeeded`・`partially_succeeded` の `finished_at` の最大値(**最終クロール完了日時**。AAPI-P-4) |
| `items[].delete_job` | `JobBrief` / null | `status=deleting` のときだけ値(その `source_id` の最新の `source_delete` ジョブ)。それ以外は `null`。取得失敗は**行の `unavailable` の `delete_job`**(`status=deleting` の行だけ) | 同: `job_type=source_delete` |
| `items[].document_count` | integer / null | 取得失敗は `null`(**行の `unavailable` の `document_count`**)。0 件は `0`(キーなし) | 検索インデックス(エイリアス)の `source_id` ごとの文書数。**数え方(AAPI-P-23)**: `index_status` を問わない全文書(抽出失敗・要約未生成を含む)。削除ジョブで消える文書数(DLG-2)と一致させるため(導出) |
| `items[].unavailable` | object | **この行の失敗**(常に存在。なければ `{}`)。キーは `last_crawl`・`last_crawl.stalled`・`last_completed_at`・`delete_job`・`delete_job.stalled`・`document_count`(行の中の項目の相対パス)。理由は `store_unavailable`・`search_index_unavailable`・`timeout`。**行ごとに成否が分かれうる読み取り(ソースごとのサブ要求)は、失敗した行だけに付け、集計全体が失敗したときは全行に同じキーを付ける**(2.2) | |
| `unavailable`(最上位) | object | EP-01 では行に属さない項目がないため**常に `{}`** | |

- `stalled`(`last_crawl`・`delete_job` の中)は、実行中のジョブだけ、ロック文書 `lock-{source_id}` を**先に**読んで導出する(導出は C。2.9)。ロック文書を読めなかった行は `last_crawl.stalled`(または `delete_job.stalled`)が `null` で、**その行の `unavailable` の `last_crawl.stalled`(または `delete_job.stalled`)** にキーがある(他の行は影響を受けない)。

**エラー**

| HTTP | `code` | 発生条件 |
| --- | --- | --- |
| 400 | `invalid_request` | 未知のクエリ(`unknown_field`) |
| 503 | `unavailable` | `loreley-sources` の読み取りが再試行しても失敗した(A 5.2。**主たる読み取り**。部分的な応答にしない)。件数が OpenSearch の取得上限(10,000 件)を超えて切り詰められる場合も同じ(想定外。Crawler の `source_list_truncated` に倣う。導出) |

`loreley-jobs`・検索インデックスの失敗は 503 にせず、200 で `null`+**その行の `unavailable`**(2.2)。

```json
{
  "items": [
    {
      "source_id": "docs-share", "connector_type": "file_system", "schedule_cron": "0 3 * * *", "status": "active",
      "last_crawl": {
        "job_id": "job-20261122T180000Z-3fa9c2d1", "source_id": "docs-share", "job_type": "crawl", "trigger": "schedule",
        "status": "failed", "force_delete": false, "rewrite_mode": false,
        "queued_at": "2026-11-22T18:00:00.123Z", "started_at": "2026-11-22T18:00:01.020Z", "finished_at": "2026-11-22T18:10:04.500Z",
        "failure_reason": "enumeration_failed", "stalled": false, "cancellable": false
      },
      "last_completed_at": "2026-11-21T18:07:12.300Z",
      "delete_job": null,
      "document_count": 1284,
      "unavailable": {}
    }
  ],
  "unavailable": {}
}
```

### 3.2 EP-02 `GET /sources/{source_id}`

データソースの詳細(S2)と編集の現在値(S4)。

**リクエスト**: パスの `source_id`(2.12)。クエリ・本文なし。

**応答(200)**: `SourceSettings`(2.11)の項目に、次を加える。

| 項目 | 型 | `null` / 備考 | 出所 |
| --- | --- | --- | --- |
| (`SourceSettings` の各項目) | | 保存済みの値が読めない(欠落・型違い)項目は `null` とし、`unavailable.<項目名>=malformed`(AAPI-P-34・AAPI-U-10)。**`ttl_days` は `ttl_seconds` から導出するため、`ttl_seconds` が読めないとき `null` になり、キーは `ttl_seconds` だけ**(C 5.8) | `loreley-sources` の `_source`(`ttl`・`ratio_threshold` は 2.8 の変換) |
| `lock` | object | 取得失敗は `null`(`unavailable.lock`) | `loreley-jobs`: ロック文書 `lock-{source_id}` と、それが指すジョブ記録 |
| `lock.state` | string | 2.9 の 7 値。ロックなしは `none` | 導出(C) |
| `lock.job` | `ExistingJob` / null | ロックなし・`none` は `null`。**`lease_expires_at` は Admin API がロック文書から読むため、読めない値は `null`**(`0001-01-01T00:00:00.000Z` の番兵値は、Crawler の 409 の `existing_job` だけ。期限切れかどうかは `lock.state` で表す) | ロック文書の `job_id` で引いたジョブ記録(`job_type`・`status`・`trigger`)とロック文書の `lease_expires_at` |
| `lock.acquired_at` | datetime / null | ロックなしは `null` | ロック文書の `acquired_at` |
| `last_crawl` | `JobBrief` / null | EP-01 と同じ | 同 |
| `last_completed_at` | datetime / null | 同 | 同 |
| `delete_job` | `JobBrief` / null | 同 | 同 |
| `index.document_count` | integer / null | 取得失敗は `null`(`unavailable.index.document_count`)。数え方は EP-01 | 検索インデックス |
| `unavailable` | object | キーは `lock`・`last_crawl`・`last_completed_at`・`delete_job`・`last_crawl.stalled`・`delete_job.stalled`・`index.document_count`・(`SourceSettings` の項目名) | |

**エラー**

| HTTP | `code` | `details` | 発生条件 |
| --- | --- | --- | --- |
| 404 | `source_config_not_found` | — | `loreley-sources` に `source_id` の設定がない |
| 400 | `invalid_request` | `errors` | `source_id` の形式違反、未知のクエリ |
| 503 | `unavailable` | — | `loreley-sources` の読み取りの失敗。**S4 が現在値のないまま全置換しないよう、設定が取れなければ部分的な応答にしない** |

`lock`・`last_crawl`・`delete_job`・`index` の失敗は 200 で `null`+`unavailable`(2.2)。

```json
{
  "source_id": "docs-share", "connector_type": "file_system",
  "connector_config": { "root": "/data/documents/share", "include_patterns": [], "exclude_patterns": ["**/draft/**"], "follow_symlinks": false, "include_hidden": false },
  "ttl_seconds": 2592000, "ttl_days": 30, "ratio_threshold_percent": 20, "min_delete_count": 10,
  "schedule_cron": "0 3 * * *", "status": "active", "updated_at": "2026-11-20T02:00:00.000Z",
  "lock": { "state": "none", "job": null, "acquired_at": null },
  "last_crawl": {
    "job_id": "job-20261122T180000Z-3fa9c2d1", "source_id": "docs-share", "job_type": "crawl", "trigger": "schedule",
    "status": "failed", "force_delete": false, "rewrite_mode": false,
    "queued_at": "2026-11-22T18:00:00.123Z", "started_at": "2026-11-22T18:00:01.020Z", "finished_at": "2026-11-22T18:10:04.500Z",
    "failure_reason": "enumeration_failed", "stalled": false, "cancellable": false
  },
  "last_completed_at": "2026-11-21T18:07:12.300Z",
  "delete_job": null,
  "index": { "document_count": null },
  "unavailable": { "index.document_count": "search_index_unavailable" }
}
```

(例は、検索インデックスの読み取りだけが失敗した部分失敗の形。`index.document_count` が `null` で、`unavailable` に理由がある。`lock`・`last_crawl` は `loreley-jobs` から取れている。)

### 3.3 EP-03 `POST /sources`

データソースの登録(S3。AF-1)。Crawler `POST /sources`(crawler-api 4.4.2)に中継する。

**リクエスト(本文)**

| 項目 | 型 | 必須 | 検証(Admin API) | 備考 |
| --- | --- | --- | --- | --- |
| `source_id` | string | ○ | `^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$`(違反は `format`) | 登録後は変更できない |
| `connector_type` | string | ○ | 文字列であること(`type`)。**値は検証しない**(Crawler が `unsupported`) | MVP は `file_system` |
| `connector_config` | object | ○ | JSON のオブジェクトであること(`type`)。**中身は検証・加工せず中継する**(AAPI-K-5・P-20) | 画面は `file_system` の 5 項目(`root`・`include_patterns`・`exclude_patterns`・`follow_symlinks`・`include_hidden`)を常に送る。`root` は Crawler のコンテナから見える任意のパス(2.10) |
| `ttl_days` | integer | ※ | 1 以上(ゲート1の「非負」からの変更。AAPI-P-37)。`× 86,400` が int64 に収まる(`range`) | `ttl_days` と `ttl_seconds` の**どちらか一方が必須**。両方は `exclusive`、どちらもなしは `required` |
| `ttl_seconds` | integer | ※ | 1 以上・int64 に収まる(`range`) | |
| `ratio_threshold_percent` | number | ○ | 0 以上 100 未満(`range`)。小数第 3 位以下があれば `format`。整数・小数の JSON の数値(文字列・真偽値は `type`) | しきい値の範囲は Admin API だけが検証する(AAPI-K-2) |
| `min_delete_count` | integer | ○ | 0 以上・int64 に収まる(`range`) | |
| `schedule_cron` | string / null | 任意 | 文字列または `null`(`type`)。**書式は検証しない**(Crawler が検証。CAPI-P-30) | 省略・`null` は手動のみ |

**Crawler への送信**(crawler-api 4.4.1): `source_id`・`connector_type`・`connector_config` はそのまま。`ttl` = `ttl_seconds`(`ttl_days` なら × 86,400)、`ratio_threshold` = `ratio_threshold_percent` ÷ 100(十進数で計算し JSON の数値にする。2.8)、`min_delete_count` はそのまま、`schedule_cron` は指定がなければ `null`。`status`・`updated_at` は送らない。

**応答**: 201(新規に保存した)または 200(同じ内容がすでに登録されていた。冪等。CAPI-P-10)。本文は `SourceSettings`(Crawler が返した保存内容を 2.8 で変換)。

**エラー**

| HTTP | `code` | `details` | 発生条件 |
| --- | --- | --- | --- |
| 400 | `invalid_request` | `errors[]` | 上の検証の違反(`required`・`type`・`format`・`range`・`exclusive`・`unknown_field`)。Crawler の 400 `invalid_request` のうち項目が `connector_type`(`unsupported`)・`connector_config`(`type`・`format`)・`ttl`・`ratio_threshold`・`min_delete_count`・`schedule_cron`(`format`・`type`)のもの(2.6。項目名は Admin の名前に写す) |
| 400 | `config_invalid` | `errors[]`(分解できたとき)、`crawler_message` | Crawler の `validate_config` が `connector_config` の違反を返した(2.5) |
| 409 | `source_already_exists` | `status` | 同じ `source_id` があり、内容が異なる、または `status=deleting`(同じ内容でも)。`status` は既存の `active` / `deleting`。既存が形式不正で読めなければ `null`(CAPI-P-26) |
| 502 | `crawler_error` | — | Crawler の想定外の応答(500。`validate_config` の想定外の例外を含む)・契約外・Admin が検証済みの項目の拒否 |
| 503 | `crawler_unavailable` / `crawler_unreachable` | — | 2.3 |
| 504 | `crawler_response_lost` | `outcome_unknown` | 2.3(再送は 200 の冪等応答か 409 になる) |

**注意**: 登録・更新では接続確認をしない(crawler-api 4.4)。`connector_config` の違反は、Crawler の最初の違反 1 件だけが返る(画面は送信前に全項目を検証する。画面仕様 2.3.2)。入力値はエラー本文に載せない。

```json
{ "source_id": "docs-share", "connector_type": "file_system",
  "connector_config": { "root": "/data/documents/share", "include_patterns": [], "exclude_patterns": [], "follow_symlinks": false, "include_hidden": false },
  "ttl_days": 30, "ratio_threshold_percent": 20, "min_delete_count": 10, "schedule_cron": "0 3 * * *" }
```

(応答 201 は `SourceSettings`(2.11)。400 の例)

```json
{ "error": { "code": "invalid_request", "message": "the request is invalid", "retryable": false,
  "details": { "errors": [ { "field": "ratio_threshold_percent", "reason": "range" }, { "field": "ttl_days", "reason": "exclusive" } ] } } }
```

### 3.4 EP-04 `PUT /sources/{source_id}`

データソース設定の更新(S4)。Crawler `PUT /sources/{source_id}`(crawler-api 4.4.3)に中継する。**変更できる項目の全置換**(必須項目を省略できない)。

**リクエスト**: パスの `source_id`。本文は EP-03 の本文から **`source_id`・`connector_type` を除いた項目**(`connector_config`・`ttl_days` / `ttl_seconds`・`ratio_threshold_percent`・`min_delete_count`・`schedule_cron`)。検証・変換は EP-03 と同じ。`source_id`・`connector_type` を本文に含めると 400 `invalid_request`・`unknown_field`(Admin API が先に拒否する)。`schedule_cron` を省略すると `null`(手動のみ)に置き換わる。

**応答**: 200。本文は `SourceSettings`。内容が現在と同じときは Crawler が書き込まず `updated_at` も変えない(CAPI-P-10)。

**エラー**: EP-03 の 400・502・503・504 に加えて次のとおり(`source_already_exists` は返らない)。

| HTTP | `code` | 発生条件 |
| --- | --- | --- |
| 404 | `source_config_not_found` | 設定がない |
| 409 | `source_deleting` | 設定が `status=deleting`(削除中は更新しない) |
| 400 | `config_invalid` | EP-03 と同じ。**Crawler は、設定があり保存済みの `connector_type` が読めるときだけ、その種別で先に `connector_config` を検証する**。したがって `config_invalid` が **409 `source_deleting` より先に返りうる**(削除中のソースでも、種別が読めれば先に検証される)。**設定がない、または種別が読めないときは検証せず、404 `source_config_not_found`(種別が読めないときは 500 → 502)になる**(crawler-api 4.4.3 の処理順の手順 3・4。同 4.4.3 の「順序の帰結」の文言は、404 についても先に検証されるように読めて曖昧で、手順 3 が正。R1 I-3。HO-10) |
| 502 | `crawler_error` | EP-03 に加え、既存の設定が形式不正で `status`・`connector_type` が読めない(Crawler の 500。CAPI-P-26) |

**反映**: 保存した設定は次に開始するジョブから使われる。実行中のジョブには反映されず、実行待ちのジョブには開始時に反映される(画面が注意書きを出す。crawler-api 4.4.1)。

### 3.5 EP-05 `POST /sources/{source_id}/delete-jobs`

データソースの削除(AF-16)。**ソース削除ジョブの起動**で、設定だけを消す API はない(AAPI-K-4)。失敗したジョブの再実行も同じ呼び出しを繰り返す(crawler-api 4.6)。Crawler `POST /sources/{source_id}/delete-jobs` に中継する。

**リクエスト**: パスの `source_id` だけ。本文は読まない。確認は画面(DLG-2。要入力確認)。

**応答**: 202。`JobAccepted`(`job_type=source_delete`、`force_delete`・`rewrite_mode` は `null`)。

**エラー**

| HTTP | `code` | `details` | 発生条件 |
| --- | --- | --- | --- |
| 404 | `source_config_not_found` | — | 設定がない(設定の削除の後にロックだけが残った場合は、再実行ではなく EP-08 で消す) |
| 409 | `maintenance_enabled` | — | メンテナンスフラグが立っている |
| 409 | `lock_held` | `existing_job`、`lock_state` | そのソースにロックがある(実行待ち・実行中の削除ジョブを含む)。**`options_applied`・`requested` は含めない**(指定がないため。2.7) |
| 502・503・504 | `crawler_error` ほか | — | 2.3 |

`source_deleting` は返さない(削除中も受け付ける。CAPI-P-12)。**注意**: そのソースの全文書・スキップ記録・削除の記録・設定が消え、取り消せない。API に確認の仕組みはなく、誤操作の防止は画面(A 2.3)。

```json
{ "job_id": "job-20261122T020000Z-9b1c44aa", "job_type": "source_delete", "source_id": "docs-share", "status": "queued",
  "trigger": "manual", "force_delete": null, "rewrite_mode": null, "queued_at": "2026-11-22T02:00:00.100Z" }
```

---

## 4. クロール操作

### 4.1 EP-06 `POST /sources/{source_id}/crawl-jobs`

クロールの手動起動(AF-3)と、失敗ジョブの再実行(AF-5)。Crawler `POST /sources/{source_id}/crawl-jobs`(crawler-api 4.1)に中継する。

**リクエスト**

| 項目 | 型 | 必須 | 既定 | 検証 |
| --- | --- | --- | --- | --- |
| `source_id`(パス) | string | ○ | | 2.12 |
| `force_delete` | boolean | 任意 | `false` | 真偽値(`type`)。**手動起動だけで指定できる**(AAPI-K-3) |
| `rewrite_mode` | boolean | 任意 | `false` | 同上。定期起動では常に `false` |

本文なし・`{}` は、どちらも `false`。Crawler には 2 項目を常に明示して送る。

**応答**: 202。`JobAccepted`(`job_type=crawl`、`trigger=manual`)。

**エラー**(起動の拒否。AF-6。複数に当たるときは Crawler が先に判定したものを返す。crawler-api 4.1 の順は、設定 → メンテナンス → ロック → 再確認)

| HTTP | `code` | `details` | 発生条件 |
| --- | --- | --- | --- |
| 404 | `source_config_not_found` | — | 設定がない |
| 409 | `source_deleting` | — | ソース削除中(`status=deleting`)。削除ジョブが再確認で入っていた場合を含む |
| 409 | `maintenance_enabled` | — | メンテナンスフラグが立っている |
| 409 | `lock_held` | `options_applied=false`、`requested`、`existing_job`、`lock_state` | そのソースのロックがある(実行中・実行待ち、リース切れ・孤児ロック)。**成功扱いにしない**(AAPI-P-35。2.7) |
| 400 | `invalid_request` | `errors[]` | `force_delete`・`rewrite_mode` の型違い、未知の項目 |
| 502・503・504 | `crawler_error` ほか | — | 2.3。**504 のときは受付済みかもしれない**(再送は 409 `lock_held`・`existing_job` で確認できる) |

**失敗ジョブの再実行(AF-5)**: 専用の EP は採用されなかった(ゲート2)。画面は J2(EP-10)の応答で `rerunnable=true` のときだけ操作を出し、`source_id`・`force_delete`・`rewrite_mode`(元ジョブの起動時の指定)を**そのままこの EP のリクエストに渡す**(UC-11・UC-17。DLG-4 が読み取り専用で提示する)。対象のデータソースはパスで、引き継ぎは既存の 2 項目で表現できるため、**リクエストの項目は追加しない**。判定(最新の失敗ジョブか、ロック解放済みか)は画面の表示に基づき、サーバー側では強制しない。表示が古くても、ロックで二重には起動せず(409 `lock_held`)、起動されるのは通常の手動起動と同じ新しいクロールで、実害は増えない(導出)。`source_delete` ジョブの再実行は EP-05 の再呼び出し。

**注意**: `force_delete=true` は、割合ルール・最小件数ルールを無視して削除する(TTL を過ぎた文書だけが対象。削除は取り返しがつかない)。再実行で引き継がれる場合も同じ(画面が警告つきの確認を出す)。`rewrite_mode=true` の前の準備(要約生成の停止)は Indexer の運用手順で、要約の有効 / 無効は返さない(AAPI-P-9)。

```json
{ "force_delete": false, "rewrite_mode": false }
```

```json
{ "job_id": "job-20261122T030000Z-77aa01bc", "job_type": "crawl", "source_id": "docs-share", "status": "queued",
  "trigger": "manual", "force_delete": false, "rewrite_mode": false, "queued_at": "2026-11-22T03:00:00.050Z" }
```

### 4.2 EP-07 `POST /jobs/{job_id}/cancel`

`crawl` ジョブの取消(AF-4)。Crawler `POST /jobs/{job_id}/cancel`(crawler-api 4.2)に中継する。

**リクエスト**: パスの `job_id` だけ。本文は読まない。

**応答**: **200** `{ "job_id": "...", "status": "cancelled" }`(実行待ちを取り消した)、**202** `{ "job_id": "...", "status": "running" }`(実行中への取消要求の**受付だけ**。完了は J2 の `status` で確認する)。

**エラー**(Crawler の判定順: ジョブなし → 種別 → 終端)

| HTTP | `code` | `details` | 発生条件 |
| --- | --- | --- | --- |
| 404 | `job_not_found` | — | そのジョブがない(ロック・スキップ記録など、ジョブ以外の記録の ID を含む。CAPI-P-18)。**Crawler が `job_id` を理由に 400 `invalid_request`・404 `not_found` を返した場合も、この 404 に写す**(`%`・`?` などを含む `job_id` は Admin API の検証を通るが、Crawler が生成する ID の形ではなく、存在しない ID と同義。AAPI-P-39・AAPI-U-12) |
| 409 | `job_not_cancellable` | — | `source_delete` ジョブ(状態を問わない) |
| 409 | `job_already_finished` | `status` | `crawl` ジョブがすでに終端(`succeeded`・`partially_succeeded`・`failed`・`cancelled`)。`running` への要求の直後に終端になった場合も 409 になりうる(CAPI-P-24)。**成功に変換せず返し、画面が成功扱いにする**(AAPI-P-21) |
| 502・503・504 | `crawler_error` ほか | — | 2.3。実行待ちの取消の後のロック削除が失敗した 503 は、再送すると 409 `job_already_finished` になる(crawler-api 4.2 の既知の限界) |

**注意**: 終了通知の送信を始めた後の取消は Indexer の削除を止めない(CA-K-9)。画面は J2 の `cancel_after_finish_notice`(EP-10)で伝える。リース切れの実行中ジョブは取消が完了しないことがあり、EP-08 を使う。メンテナンスフラグは確認されない(CAPI-P-17)。

### 4.3 EP-08 `DELETE /sources/{source_id}/lock`

実行中でないロックの解放(AF-7)。Crawler `DELETE /sources/{source_id}/lock`(crawler-api 4.3)に中継する。

**リクエスト**: パスの `source_id` だけ。本文は読まない。**設定がなくても解放できる**(ソース削除の後に残ったロック)。

**応答**: 200。

| 項目 | 型 | 内容 |
| --- | --- | --- |
| `source_id` | string | |
| `released` | boolean | ロック文書を削除したら `true`。ロック文書がなければ `false`(何もしていない。冪等) |
| `failed_job_id` | string / null | `failed`(`lock_released`)にした実行中ジョブの ID。なければ `null` |

**エラー**

| HTTP | `code` | `details` | 発生条件 |
| --- | --- | --- | --- |
| 409 | `lock_in_use` | `existing_job`、`lock_state` | 解放しないロック: リース期限内の実行中・実行待ちのジョブ、取得直後(受付の途中の可能性。直近 60 秒)、ジョブの `status` が読めない(形式不正)。`lock_state` は Admin API が Crawler の 409 の後にロック文書・ジョブ記録を読んで導出する(読めなければ `unknown`) |
| 502・503・504 | `crawler_error` ほか | — | 2.3。503 は競合が解けない場合を含む |

**注意**: 解放してもジョブは再起動されない(再実行は EP-06・EP-05)。ロックが残るのは異常時で、画面は警告つきの確認(DLG-5)を出す。解放後も動いている Crawler は、次のハートビートで所有権の喪失を知ってジョブを止める(crawler-api 4.3)。

```json
{ "source_id": "docs-share", "released": true, "failed_job_id": "job-20261122T120000Z-aa41c3d9" }
```

---

## 5. ジョブ(J1・J2)

### 5.1 EP-09 `GET /jobs`

ジョブ(クロール・ソース削除)の実行履歴(J1)。サーバー側ページング(2.1)。

**リクエスト(クエリ)**

| 名前 | 型 | 必須 | 既定 | 検証 |
| --- | --- | --- | --- | --- |
| `source_id` | string | 任意 | すべて | 2.12 の形式。**登録されていない ID は 404 にせず、空の結果を返す**(導出。AAPI-P-26) |
| `status` | string | 任意 | すべて | `queued`・`running`・`succeeded`・`partially_succeeded`・`failed`・`cancelled`、または複合の `active`(= `queued` + `running`)。それ以外は `unsupported` |
| `page` | integer | 任意 | 1 | 1 以上。`page × items_per_page` が 10,000 を超えると `range` |
| `items_per_page` | integer | 任意 | 25 | `25`・`50`・`100`(それ以外は `unsupported`) |
| `sort` | string | 任意 | `-queued_at` | `queued_at`・`-queued_at`。**画面の「開始」列の並べ替えは `queued_at` に対応づける**(実行待ちは「受付 日時」を表示する列で、直列実行のため受付の順と開始の順は一致する。導出。2.1)。それ以外は `unsupported` |

**応答(200)**: `items[]`(`JobListItem` = `JobBrief` + 行の `unavailable`。2.11)、`total`、`page`、`items_per_page`、`window_limit`(10,000)、`unavailable`(最上位。**常に `{}`**。2.2)。

- 出所: `loreley-jobs` の `record_type=job`(`source_id`・`status` の `term` で絞り込み、`queued_at` で並べ、同順位は `job_id` の昇順)。`stalled`・`cancellable` は、そのページの `status=running` の行だけ、ロック文書 `lock-{source_id}` を読んで導出する(C)。ロック文書の読み取りが失敗した行は `stalled=null`・`cancellable=false` で、**その行の `unavailable` の `stalled` が `store_unavailable`(または `timeout`)**。ロック文書を `mget` で読む単位は文書ごとなので、失敗した文書に対応する行だけにキーが付く。`mget` 全体が失敗したときは、`status=running` の全行に同じキーを付ける(2.2)。
- `status` の絞り込みは**保存上の状態**による。リース切れの実行中ジョブは `running`・`active` に含まれ、`failed` には含まれない(画面は `stalled`・`failure_reason` でタグを切り替える)。

**エラー**

| HTTP | `code` | `details` | 発生条件 |
| --- | --- | --- | --- |
| 400 | `invalid_request` | `errors[]` | 上の検証の違反(`page` の `range`・`type`、`status`・`sort`・`items_per_page` の `unsupported`、`source_id` の `format`、未知のクエリの `unknown_field`) |
| 503 | `unavailable` | — | `loreley-jobs` の読み取りの失敗(主たる読み取り) |

```json
{ "items": [ { "job_id": "job-20261122T030000Z-77aa01bc", "source_id": "docs-share", "job_type": "crawl", "trigger": "manual",
    "status": "running", "force_delete": false, "rewrite_mode": true, "queued_at": "2026-11-22T03:00:00.050Z",
    "started_at": "2026-11-22T03:00:01.000Z", "finished_at": null, "failure_reason": null, "stalled": false, "cancellable": true,
    "unavailable": {} } ],
  "total": 9, "page": 1, "items_per_page": 25, "window_limit": 10000, "unavailable": {} }
```

### 5.2 EP-10 `GET /jobs/{job_id}`

ジョブの詳細(J2)。ジョブ記録・ロック文書・`loreley-deletions` を読み取りのみで読む。

**リクエスト**: パスの `job_id`(2.12)。クエリ・本文なし。

**応答(200)**

| 項目 | 型 | `null` / 備考 | 出所 |
| --- | --- | --- | --- |
| `JobBrief` の項目すべて | | 2.11 | `loreley-jobs` のジョブ記録(`record_type=job`) |
| `failure_detail` | string / null | `failed` 以外は `null` | 同 `failure_detail`。Crawler が切り詰め・エスケープ済みで、文書の本文・認証情報を含まない(CA-P-45・48。切り詰めた相対パス・`external_id` を含みうる。ジョブ記録の値であり、本 API のエラー本文ではない) |
| `lease_expires_at` | datetime / null | 実行中のジョブで、ロック文書の値が日時として読めるときだけ。それ以外は `null`(`stalled=true` のときの期限切れの表示は画面) | ロック文書 `lock-{source_id}` の `lease_expires_at` |
| `latest_for_source` | boolean / null | `crawl` ジョブだけ意味を持つ(`source_delete` は `false`)。取得失敗は `null` | 同じ `source_id` の最新の `crawl` ジョブとの比較(導出は C) |
| `rerunnable` | boolean / null | `stalled`・`latest_for_source` が決まらないとき、または設定の読み取りに失敗したときは `null`(画面は不可として扱う。`unavailable` の `rerunnable`) | 導出(2.9)。データソースの設定(`loreley-sources`)の読み取りを含む |
| `rerun_blocked_reason` | string / null | `not_crawl`・`not_failed`・`stalled`・`superseded`・`source_deleting`・`source_missing`。`rerunnable` が `true` または `null` のときは `null` | 導出(2.9) |
| `cancel_after_finish_notice` | boolean | | ジョブ記録の `status=cancelled` かつ `finish_notice.send_started_at` がある |
| `warnings` | array | 警告がなければ `[]`。各要素は `code`(string)と Crawler が定めた固定の項目(例: `invalid_external_id` の件数・例、`enumerated_zero_after_nonzero` の `previous_job_id`・`previous_enumerated_count`、`polling_aborted` の `confirmation`)。**コード名・項目は Crawler 設計の案(CA-P-73)で、そのまま通す**(AAPI-U-3) | ジョブ記録の `warnings` |
| `registration` | object / null | `source_delete`・記録がないとき(実行待ち)は `null` | ジョブ記録の `registration` |
| `registration.enumerated_count`・`created_count`・`updated_count`・`unchanged_count`・`skipped_count`・`oversize_count`・`error_count`・`invalid_id_count` | integer / null(保存値が読めないとき `null`。2.2) | `error_count` は抽出に失敗した文書の数(CA 7.7)。`skipped_count`・`oversize_count`・`error_count` は X1 の各タブの件数と別の値(そのジョブの集計) | 同(`partial` の値を含め保存値のまま) |
| `registration.partial` | boolean / null | 保存値。**読めないとき(真偽値でない・欠落)は `null`**(2.2。C 5.0・5.4 と同じ) | 同 |
| `registration.phase` | string / null | **`partial` が `null`(読めない)のとき、または `partial=true` で `status` が `null`(読めない)のときは `null`**。それ以外は `final`(`partial=false`)/ `in_progress`(`partial=true` で `status` が `queued`・`running`)/ `incomplete`(`partial=true` で終端。確定前に終わった) | 導出(AAPI-P-4) |
| `deletion` | object / null | `source_delete` は `null`。`crawl` は常にオブジェクト | |
| `deletion.summary` | object / null | ジョブ記録に要約がなければ `null` | ジョブ記録の `deletion_summary`。キーは `status`・`reason`・`forced`・`target_count`・`denominator`・`deleted_count`・`enumerated_count`・`n_seen`・`e_missing`・`finish_received_at`・`deletion_started_at`・`finished_at`・`observed_at`(記録にない項目は `null`。`observed_at` は確認を打ち切ったときだけ) |
| `deletion.confirmation` | string / null | `confirmed` / `unconfirmed`(結果未確認)/ `unknown`(結果不明)。確認に入っていないジョブは `null`(AF-10) | ジョブ記録の `confirmation` |
| `deletion.current` | object / null | 記録がない・実行待ち・取得失敗は `null` | `loreley-deletions` の `deletion_result-{job_id}`(ID で取得)。キーは `status`・`reason`・`reason_detail`・`forced`・`target_count`・`denominator`・`deleted_count`・`ended_at` |
| `deletion.current_state` | string | `available` / `not_found`(記録がない。結果不明の説明は画面)/ `unavailable`(読み取り失敗。`unavailable.deletion.current`)。**実行待ちのジョブは読まず `not_found`**(AAPI-P-29) | |
| `deletion.fetched_at` | datetime / null | 現在値を読んだ時刻(画面の「取得時刻」)。読んでいなければ `null` | Admin API の時計 |
| `deletion.settings` | object / null | `ttl_seconds`・`ratio_threshold_percent`・`min_delete_count`。設定スナップショットがない(開始前に失敗した)ときは `null` | ジョブ記録の `settings_snapshot`(`ttl`・`ratio_threshold`・`min_delete_count` を 2.8 で変換) |
| `unavailable` | object | キーは `stalled`・`lease_expires_at`・`latest_for_source`・`rerunnable`・`deletion.current` | |

- 失敗理由(`failure_reason`)・警告・削除結果の状態名・理由コードは、上流(CA-P-10・73、loreley-deletions §3)の案で、確定時に再確認する(AAPI-U-3)。未知のコードはそのまま返し、画面が一般的な文言にする。メンテナンス(AF-19)は `failure_reason=maintenance`・削除結果の `reason=maintenance` として現れる。

**エラー**

| HTTP | `code` | `details` | 発生条件 |
| --- | --- | --- | --- |
| 404 | `job_not_found` | — | `loreley-jobs` に `job_id` の記録がない、または `record_type` が `job` でない(ロック・スキップ記録・メンテナンスフラグの ID。CAPI-P-18) |
| 400 | `invalid_request` | `errors[]` | `job_id` の形式違反、未知のクエリ |
| 503 | `unavailable` | — | ジョブ記録の読み取りの失敗(主たる読み取り) |

ロック文書・`loreley-deletions`・最新ジョブの取得の失敗は 200 で `null`+`unavailable`(2.2)。

```json
{
  "job_id": "job-20261122T150000Z-5d2e8a10", "source_id": "wiki-export", "job_type": "crawl", "trigger": "schedule",
  "status": "failed", "force_delete": false, "rewrite_mode": false,
  "queued_at": "2026-11-22T15:00:00.123Z", "started_at": "2026-11-22T15:00:01.020Z", "finished_at": "2026-11-22T15:10:04.500Z",
  "failure_reason": "skip_limit_exceeded", "failure_detail": "skip_limit_exceeded: 20 consecutive skips", "stalled": false, "cancellable": false,
  "lease_expires_at": null, "latest_for_source": true, "rerunnable": true, "rerun_blocked_reason": null, "cancel_after_finish_notice": false,
  "warnings": [],
  "registration": { "enumerated_count": 1300, "created_count": 12, "updated_count": 40, "unchanged_count": 1100, "skipped_count": 20, "oversize_count": 1,
    "error_count": 3, "invalid_id_count": 0, "partial": true, "phase": "incomplete" },
  "deletion": { "summary": null, "confirmation": null, "current": null, "current_state": "not_found", "fetched_at": "2026-11-22T15:20:00.000Z",
    "settings": { "ttl_seconds": 2592000, "ratio_threshold_percent": 20, "min_delete_count": 10 } },
  "unavailable": {}
}
```

(`failure_detail` の文言は説明用。)

---

## 6. 文書の確認(X1)

### 6.1 EP-11 `GET /sources/{source_id}/documents`

データソースごとの、確認が必要な文書(スキップ・抽出失敗・原本サイズ超過・要約未生成)をタブごとに返す(AF-11〜14)。サーバー側ページング(2.1)。**各タブの総件数と登録文書数を各取得で併せて返す**(AAPI-P-5)。

**リクエスト**

| 名前 | 型 | 必須 | 既定 | 検証 |
| --- | --- | --- | --- | --- |
| `source_id`(パス) | string | ○ | | 2.12 |
| `tab`(クエリ) | string | ○ | | `skipped`・`extract_failed`・`oversize`・`summary_pending`(欠落は `required`、それ以外は `unsupported`) |
| `page`・`items_per_page` | integer | 任意 | 1・25 | EP-09 と同じ |
| `sort` | string | 任意 | 下表の既定 | 下表の項目の昇順・降順だけ(それ以外は `unsupported`) |

| `tab` | 出所 | 既定の並び(`sort`) | 同順位 |
| --- | --- | --- | --- |
| `skipped` | `loreley-jobs`: `record_type=skip`・`source_id`(CA 3.3.3) | `-last_skipped_at` | `document_id` 昇順 |
| `extract_failed` | 検索インデックス: `source_id`・`index_status=extract_failed`(IA K53) | `-last_seen_at` | 同 |
| `oversize` | `loreley-jobs`: `record_type=oversize`・`source_id`(CA 3.3.4) | `-last_detected_at` | 同 |
| `summary_pending` | 検索インデックス: `source_id`・`summary_status=pending` | `-indexed_at` | 同 |

**応答(200)**: `tab`、`items[]`(各行に `unavailable`。下記)、`total`、`page`、`items_per_page`、`window_limit`(10,000)、`tab_counts`、`document_count`、`unavailable`(最上位。行に属さない項目 `tab_counts.<タブ>`・`document_count` の失敗だけ。2.2)。

- `tab_counts`: `skipped`・`extract_failed`・`oversize`・`summary_pending`(integer / null。各タブの総件数。取得失敗は `null`+最上位の `unavailable` の `tab_counts.<タブ>`)。**抽出失敗の件数はスキップ件数と別**(PD §4.2)。
- `document_count`: 登録文書数(integer / null。数え方は 3.1。取得失敗は `null`+最上位の `unavailable` の `document_count`)。
- `items[]` の項目(タブごと。**どのタブの行も `unavailable`(object。この行の失敗。常に存在。なければ `{}`)を持つ**。キーは `skipped` タブの `existence` だけで、他のタブの行は常に `{}`。`null` で行の `unavailable` にキーがないものは「値がない」):

| `tab` | 項目 |
| --- | --- |
| `skipped` | `document_id`、`external_id`、`stage`(`fetch`・`index`)、`reason`(記録のまま「分類名: 固定文」。分解は画面)、`attempts`、`consecutive_skips`、`first_skipped_at`、`last_skipped_at`、`last_job_id`、`existence`(`existing`・`new`・`unknown`) |
| `extract_failed` | `document_id`、`title`(なければ `null`)、`external_id`、`mime_type`、`size`、`source_updated_at`、`last_seen_at` |
| `oversize` | `document_id`、`external_id`、`detected_by`(`crawler`・`indexer`)、`size`(分かる場合だけ。なければ `null`)、`first_detected_at`、`last_detected_at`、`last_job_id` |
| `summary_pending` | `document_id`、`title`、`external_id`、`mime_type`、`source_updated_at`、`indexed_at` |

- **`existence`(承認済みの案。AAPI-P-5・P-24)**: ページ内の `document_id`(スキップ記録の値は検索インデックスの `_id` と同じ算出値。AAPI-U-7)を **1 回の一括検索**(ID の一括取得。**上限 100 件**。`items_per_page` の上限と同じ)で検索インデックスに問い合わせ、見つかれば `existing`、なければ `new`。一括検索の全体が失敗したら、そのページの全件を `unknown` にしてページ全体は返し、**全行の `unavailable` に `existence`(`search_index_unavailable`・`timeout`)を付ける**(2.2)。一括検索は 1 回の `ids` クエリなので、行ごとに成否が分かれることはない(C 3.3 R-11)。`document_id` が読めない行は `unknown` にする。スキップ以外のタブの項目に `existence` はない。
- 要約未生成タブの実データでの検証は、要約機能(LLM プロバイダ)の実装後(AF-14。AAPI-U-8)。画面は 0 件の空状態として先に実装できる。
- 設定の存在確認(`loreley-sources` の ID 取得)、一覧、件数は同じリクエストの中で読み、**同順位は `document_id` の昇順**で決める(AAPI-P-30)。
- 要約が無効のときも `summary_pending` は 0 件になるだけで、有効 / 無効は返さない(AAPI-P-9)。

**エラー**

| HTTP | `code` | `details` | 発生条件 |
| --- | --- | --- | --- |
| 404 | `source_config_not_found` | — | `loreley-sources` に設定がない(削除中のソースは存在すれば 200) |
| 400 | `invalid_request` | `errors[]` | `tab` の `required`・`unsupported`、`page` の `range`、`items_per_page`・`sort` の `unsupported`、`source_id` の `format`、未知のクエリ |
| 503 | `unavailable` | — | 設定の存在確認、またはそのタブの一覧の読み取りの失敗(主たる読み取り) |

`tab_counts`・`document_count` の失敗は 200 で `null`+最上位の `unavailable`、`existence` の失敗は `unknown`+**その行の `unavailable`**(2.2)。

```json
{ "tab": "skipped",
  "items": [ { "document_id": "9f2c…e1", "external_id": "manuals/2026/guide.pdf", "stage": "fetch",
      "reason": "fetch_permission_denied: 取得の権限がなかった", "attempts": 3, "consecutive_skips": 5,
      "first_skipped_at": "2026-11-18T03:00:10.000Z", "last_skipped_at": "2026-11-22T03:00:12.000Z",
      "last_job_id": "job-20261122T030000Z-77aa01bc", "existence": "existing", "unavailable": {} } ],
  "total": 6, "page": 1, "items_per_page": 25, "window_limit": 10000,
  "tab_counts": { "skipped": 6, "extract_failed": 3, "oversize": 2, "summary_pending": null },
  "document_count": 1284, "unavailable": { "tab_counts.summary_pending": "search_index_unavailable" } }
```

---

## 7. OpenSearch(O1)

### 7.1 EP-12 `GET /opensearch/cluster`

OpenSearch の汎用の情報(クラスタ状態・インデックス・シャード・ノード名)を **1 つの応答で全件返す**(AAPI-P-6)。Loreley 固有の概念(データソース・ジョブなど)は含めない(UC-8)。概況とマトリクスは 1 カード・1 画面なので、1 つの取得結果として扱い、**どれかが失敗したら全体を 503** にする(概況だけ・マトリクスだけが取れた応答は返さない)。絞り込み・並べ替え・ページ分けは画面側で、**パラメータはない**。

**リクエスト**: パス・クエリ・本文なし(未知のクエリは 400 `unknown_field`)。

**応答(200)**

| 項目 | 型 | 備考 | 出所(opensearch-py。読み取りのみ) |
| --- | --- | --- | --- |
| `fetched_at` | datetime | | Admin API の時計 |
| `cluster.name` | string | | `cluster.health` の `cluster_name` |
| `cluster.status` | string | `green` / `yellow` / `red` | 同 `status` |
| `cluster.node_count` | integer | | 同 `number_of_nodes` |
| `cluster.active_shards` | integer | 移動中を含む | 同 `active_shards` |
| `cluster.relocating_shards` | integer | アクティブの**内数** | 同 `relocating_shards` |
| `cluster.initializing_shards`・`cluster.unassigned_shards` | integer | 外数 | 同 `initializing_shards`・`unassigned_shards` |
| `nodes[].name` | string | クラスタの全ノード(シャードを持たないノードも) | `cat.nodes` の `name` |
| `indices[].name` | string | | `cat.indices` の `index` |
| `indices[].status` | string / null | `green` / `yellow` / `red`。取得できなければ `null` | 同 `health` |
| `indices[].document_count` | integer / null | 取得できない(クローズ済みなど)は `null`。0 件と区別 | 同 `docs.count`(文字列を整数に変換) |
| `shards[].index` | string | | `cat.shards` の `index` |
| `shards[].shard` | integer | 番号 | 同 `shard` |
| `shards[].role` | string | `primary` / `replica` | 同 `prirep`(`p`・`r`) |
| `shards[].state` | string | `started` / `initializing` / `relocating` / `unassigned`(未知の値は小文字にしてそのまま) | 同 `state` |
| `shards[].node` | string / null | 未割り当ては `null`。**`relocating` は移動元のノード名**(推測。AAPI-U-4) | 同 `node` |
| `truncated` | boolean | 切り詰めたか | |
| `total_indices` | integer | 切り詰め前のインデックス数 | |

- プライマリ数・レプリカ数は返さない(画面が出さない。画面仕様 3.2)。`cat.*` は `format=json`・`h=`・`bytes=b` を明示して取得し、値を文字列で受けて整数・`null` に変換する(0004。C)。
- **取得のそろえ方**(承認済みの案(ゲート3)。AAPI-P-31): 「シャード一覧にあるが、インデックス一覧にない」インデックスは、`indices[]` に `status=null`・`document_count=null` で補う(画面仕様 9章)。「インデックス一覧にあるが、シャード一覧にない」インデックスはそのまま(シャードなしの列)。
- **件数の上限(AAPI-P-6)**: インデックスは 1,000 件まで。超えたら、画面と同じ並び(状態の悪い順 → 名前の昇順)で先頭 1,000 件に切り詰め、`truncated=true`・`total_indices` を返す(シャードは切り詰めたインデックスのものだけ)。想定規模(単一ノード・数十〜数百のインデックス)では起きない安全網。

**エラー**

| HTTP | `code` | 発生条件 |
| --- | --- | --- |
| 400 | `invalid_request` | 未知のクエリ |
| 503 | `unavailable` | `cluster.health`・`cat.indices`・`cat.shards`・`cat.nodes` のいずれかが再試行しても失敗した |

```json
{ "fetched_at": "2026-11-22T10:48:03.000Z",
  "cluster": { "name": "loreley", "status": "yellow", "node_count": 1, "active_shards": 1, "relocating_shards": 0, "initializing_shards": 0, "unassigned_shards": 1 },
  "nodes": [ { "name": "node-1" } ],
  "indices": [ { "name": "loreley-documents-000001", "status": "yellow", "document_count": 12846 } ],
  "shards": [ { "index": "loreley-documents-000001", "shard": 0, "role": "primary", "state": "started", "node": "node-1" },
              { "index": "loreley-documents-000001", "shard": 0, "role": "replica", "state": "unassigned", "node": null } ],
  "truncated": false, "total_indices": 1 }
```

---

## 8. ダッシュボード(D1)とメタ情報

### 8.1 EP-13 `GET /dashboard`

コンポーネントの死活(AF-18。Indexer・Crawler は `/healthz` を直接読む。AAPI-K-7)。**死活のみ**で、履歴・推移・アラートはない。リクエストごとに各コンポーネントを並行に確認する(Admin API は状態を保持しない)。

**リクエスト**: パス・クエリ・本文なし。

**応答(200)**: `checked_at`(**全コンポーネントの確認が終わり、応答を組み立てた時刻**。各 `components[].checked_at` 以上)、`components[]`(固定の順: `crawler`・`indexer`・`opensearch`・`api`・`web`・`opensearch-dashboards`・`embedding`・`llm`。常に 8 件)。各要素:

| 項目 | 型 | 内容 |
| --- | --- | --- |
| `id` | string | 上の 8 つ。画面の表示名と同じ(`crawler`・`indexer`・`opensearch`・`api`・`opensearch-dashboards`・`embedding`・`llm` は compose のサービス名。**`web` は compose のサービスではなく、`api` が配信する Web UI** で、画面仕様 `dashboard-v0.1.md` 3.2 の表示名) |
| `state` | string | `normal` / `abnormal` / `undetermined`(判定不能)/ `not_configured`(未設定。任意コンポーネントだけ) |
| `reason` | string / null | `abnormal`・`undetermined` のときの診断用の理由(値は `connection_refused`・`name_not_resolved`・`unexpected_status`・`missing`・`timeout`・`connection_error`。AAPI-P-33)。`normal`・`not_configured` は `null`。画面は未知の値を一般的な文言にする |
| `checked_at` | datetime | そのコンポーネントの確認が終わった時刻 |

**最終取得成功日時**は応答に含めない(クライアントが取得成功時に保持する。AAPI-P-8)。

判定(AAPI-P-8。導出ロジックは C)

| コンポーネント | 確認の方法 | `normal` | `abnormal`(`reason`) | `undetermined`(`reason`) |
| --- | --- | --- | --- | --- |
| `crawler`・`indexer` | `GET {LORELEY_API_CRAWLER_URL / INDEXER_URL}/healthz`。**2xx かどうかだけ**で、本文は解釈しない(BAPI-P-13) | 2xx | 接続拒否(`connection_refused`)、名前解決失敗(`name_not_resolved`)、2xx 以外(`unexpected_status`) | 3 秒以内に応答なし(`timeout`)、その他の通信エラー(`connection_error`) |
| `opensearch` | `cluster.health` の応答の有無(`red` でも応答できれば正常。詳細は O1) | 応答あり | 接続拒否・名前解決失敗・HTTP エラーの応答(EP-12 の `unavailable` と同様。例外との対応は AAPI-U-11) | タイムアウト、その他 |
| `api` | 応答できていること自体 | 常に `normal` | — | — |
| `web` | `LORELEY_API_WEB_DIST_DIR` 直下の `index.html` が読めること | 読める | 読めない(`missing`) | — |
| `opensearch-dashboards`・`embedding`・`llm`(任意) | 確認用 URL(`LORELEY_API_DASHBOARDS_HEALTH_URL`・`…EMBEDDING_HEALTH_URL`・`…LLM_HEALTH_URL`)が設定されていれば `GET`(2xx のみ)。**未設定なら確認せず `not_configured`** | 2xx | `crawler` と同じ | 同上 |

- **確認先の URL は環境変数だけで決め、リクエストからは受け取らない。確認のプローブはリダイレクトに従わず、3xx は 2xx 以外として `abnormal`(`unexpected_status`)にする**(内部の別のサービスへ誘導されない。A 6。導出。R1 S-12)。
- **異常と判定不能の境界(AAPI-P-8)**: 確認先から「応答がない」と確かめられた(接続拒否・名前解決失敗・2xx 以外)ものは**異常**。「時間内に応答がない」「その他の通信エラー」は、確認自体が失敗して分からないので**判定不能**(画面仕様 `dashboard-v0.1.md` 3.1)。1 つの確認につき 3 秒(`LORELEY_API_HEALTH_PROBE_TIMEOUT_SECONDS`。30 秒の自動更新より十分短い)。
- **起動直後の見え方**: Indexer は起動時の整理、Crawler は起動時の回復が終わるまで接続を受け付けないため(indexer-api §1、crawler-api §3.1)、起動直後(Crawler は最大約 3 分)は `abnormal`(接続拒否)に見える(導出)。回復の完了後に自動で `normal` に戻る。
- 環境変数名(AAPI-P-8): 上記のほか `LORELEY_API_HEALTH_PROBE_TIMEOUT_SECONDS`。個別の一覧と既定は C が正本。

**エラー**: なし(各コンポーネントの失敗は `components[].state` で表し、`api` が応答できる限り 200)。

```json
{ "checked_at": "2026-11-22T10:48:05.450Z",
  "components": [
    { "id": "crawler", "state": "normal", "reason": null, "checked_at": "2026-11-22T10:48:02.100Z" },
    { "id": "indexer", "state": "abnormal", "reason": "connection_refused", "checked_at": "2026-11-22T10:48:02.050Z" },
    { "id": "opensearch", "state": "normal", "reason": null, "checked_at": "2026-11-22T10:48:02.300Z" },
    { "id": "api", "state": "normal", "reason": null, "checked_at": "2026-11-22T10:48:02.500Z" },
    { "id": "web", "state": "normal", "reason": null, "checked_at": "2026-11-22T10:48:02.500Z" },
    { "id": "opensearch-dashboards", "state": "not_configured", "reason": null, "checked_at": "2026-11-22T10:48:02.500Z" },
    { "id": "embedding", "state": "not_configured", "reason": null, "checked_at": "2026-11-22T10:48:02.500Z" },
    { "id": "llm", "state": "undetermined", "reason": "timeout", "checked_at": "2026-11-22T10:48:05.400Z" } ] }
```

### 8.2 EP-14 `GET /meta`

画面が必要とする、`api` の設定(環境変数)に由来する情報。**設定だけで応答し、他のコンポーネントを呼ばない**。

**使う画面**: シェル(サイドバーの OpenSearch Dashboards の外部リンク。`dashboards_url`)と、cron のタイムゾーンを表示・入力の説明に出す S1・S2・S3・S4(`cron_timezone`)。**D1 は使わない**(画面仕様 `dashboard-v0.1.md`・`admin-view-v0.1.md` 3章・10.4 の D1 に該当する箇所がない)。

**リクエスト**: パス・クエリ・本文なし。

**応答(200)**

| 項目 | 型 | 内容 |
| --- | --- | --- |
| `cron_timezone` | string / null | cron 式を解釈するタイムゾーンの IANA 名(例 `Asia/Tokyo`)。環境変数 `LORELEY_API_CRON_TIMEZONE`。**未設定は `null`**(UTC とはみなさない。画面は「適用されるタイムゾーンを取得できません」を出す。画面仕様 2.4) |
| `dashboards_url` | string / null | OpenSearch Dashboards の、**ブラウザから到達できる URL**。環境変数 `LORELEY_API_DASHBOARDS_URL`。未設定は `null`(画面は外部リンクを出さない。AF-20。AAPI-P-10) |

- cron のタイムゾーンは **Admin API の環境変数で持つ**(確定。AAPI-K-8)。Crawler の `LORELEY_CRAWLER_TIMEZONE` と値がずれると、画面の表示と実際の実行時刻がずれるため、**運用前提として同じ値を渡す**(A 8章。HO-43)。IANA 名として不正な値は起動時に失敗する(A 4章)。
- 要約の有効 / 無効、取得設定の上限値(`max_patterns`・`max_pattern_bytes`)、原本サイズの上限値は**返さない**(AAPI-P-9・P-20)。

**エラー**: なし(共通のもののみ)。

```json
{ "cron_timezone": "Asia/Tokyo", "dashboards_url": "http://localhost:5601" }
```

---

## 9. Crawler の 6 API の写像表

Admin API が Crawler に中継する操作は、crawler-api v0.4 の 6 API だけ(固定の経路。任意のパスは転送しない)。本章は、API ごとに、**送信前の検証・変換、成功、エラー(400・404・409・500・503・接続エラー・起動時の回復中)の写像**を具体化する。一般則は 2.6、code と `details` は 2.3、2.5、2.7。

### 9.1 共通の扱い(承認済みの案(ゲート3)。AAPI-P-28)

| 項目 | 内容 |
| --- | --- |
| 呼び出し先 | `LORELEY_API_CRAWLER_URL`(例 `http://crawler:8001`。内部ネットワークだけ。crawler-api 3.1)+固定のパス(下表)。Crawler は認証なし(CAPI-K-7) |
| 送るもの | UTF-8 の JSON(`Content-Type: application/json`)。ID は検証済みで、**URL に埋めるときは `quote(value, safe="")` の後に `.` を `%2E` に置換する**(`job_id` は `%`・`?`・`#`・`.` などを含みうるため。`.`・`..` は urllib3 のドットセグメント除去で崩れるため `%2E`。2.12。AAPI-U-12)。本文を読まない API(取消・ロック解放・削除ジョブ起動)には本文を付けない |
| 受け取るもの | JSON。エラーは `{"error": {"code", "message", "retryable", "details"}}`(crawler-api 3.3)。**`code` を使って分岐し、`message` は `config_invalid` のときだけ通す**(2.5)。JSON でない本文・`error.code` がない本文・未知の `code` は 502 `crawler_error` |
| リダイレクト | **追従しない**。3xx(末尾スラッシュの 307 など。crawler-api 3.3)は契約外として 502 `crawler_error` |
| タイムアウト・再送 | 接続 3 秒・応答 60 秒(仮値。A 5.6。CAPI-U-10)。**自動再送しない**(冪等でない API を含むため。P-5)。接続前に失敗(接続拒否・名前解決失敗・接続のタイムアウト、**TLS の確立の失敗(`SSLError`。接続の確立中の失敗として送る前に分類する。MVP は `CRAWLER_URL` が http 限定(BAPI-P-24)のため通常は起きず、https を許す将来は分類を見直す。C 4.3 の承認済みの案(ゲート3)。AAA-P-41)**)したら 503 `crawler_unreachable`(未到達が確かなので再試行してよい)。送信後に応答が来ない(応答のタイムアウト・切断)場合は 504 `crawler_response_lost`(`outcome_unknown=true`) |
| 起動時の回復中 | Crawler は起動時の回復(CA 5.8)が終わるまで受付を始めず、接続できない(crawler-api 3.1。CAPI-U-1)。Admin API からは**接続前の失敗**に見えるので 503 `crawler_unreachable`(`retryable=true`)になる。回復は最大約 3 分(Dockerfile の `--start-period` 180 秒。仮値)で、終われば自動で応じる。**読み取り(EP-01・02・09〜12・14)は影響を受けない**(10章) |
| 受付の途中の失敗 | 起動系で受付の途中(ロック取得の後・ジョブ保存の前)に Crawler が 503 を返すと、ジョブのないロック(孤児ロック)が残りうる(crawler-api 3.3)。その後の起動は `lock_held`(`lock_state=orphan` または `just_acquired`)になり、EP-08 で解放する |
| ジョブ記録・状態の確認 | 結果が不明(504)のとき、画面は EP-01・02・09・10 で状態を確認する。Admin API が Crawler に問い合わせて確かめることはしない(Crawler に読み取り API はない。CAPI-P-16) |

### 9.2 API ごとの写像

**9.2.1 クロール起動** — Crawler `POST /sources/{source_id}/crawl-jobs`(crawler-api 4.1)← EP-06

| 項目 | 内容 |
| --- | --- |
| 送信前の検証 | `source_id` の形式、`force_delete`・`rewrite_mode` の型(2.12) |
| 送る本文 | `{"force_delete": <bool>, "rewrite_mode": <bool>}`(既定 `false` を明示) |
| 成功 | 202(`job_id`・`job_type`・`source_id`・`status`・`trigger`・`force_delete`・`rewrite_mode`・`queued_at`)→ 202 `JobAccepted` |

| Crawler の応答 | Admin API の応答 |
| --- | --- |
| 404 `source_config_not_found` | 404 同名 |
| 409 `source_deleting` | 409 同名 |
| 409 `maintenance_enabled` | 409 同名 |
| 409 `lock_held`(`details.existing_job`) | 409 `lock_held`。`existing_job` は写し、`lock_state` は Admin API が読み取りで導出(読めなければ `unknown`)、`options_applied=false`、`requested` は送った指定 |
| 400 `invalid_request` | 502 `crawler_error`(Admin API が検証済みの項目のため) |
| 503 `unavailable`(Store 層の障害。ジョブ ID の衝突を含む) | 503 `crawler_unavailable`(再送すれば新しい ID で受け付けられうる) |
| 500 `internal_error`・契約外 | 502 `crawler_error` |
| 接続前の失敗 / 応答喪失 | 503 `crawler_unreachable` / 504 `crawler_response_lost`(受付済みかもしれない。再送は 409 `lock_held` で確認できる) |

**9.2.2 取り消し** — Crawler `POST /jobs/{job_id}/cancel`(crawler-api 4.2)← EP-07

| 項目 | 内容 |
| --- | --- |
| 送信前の検証 | `job_id` の形式 |
| 成功 | 200 `{job_id, status:"cancelled"}`、202 `{job_id, status:"running"}` → 同じステータス・同じ本文 |

| Crawler の応答 | Admin API の応答 |
| --- | --- |
| 404 `job_not_found` | 404 同名 |
| 400 `invalid_request`(項目が `job_id`)・404 `not_found`(`job_id` に `%`・`?` などを含み、パスとして扱えなかった場合。crawler-api 3.3「パスの扱い」) | **404 `job_not_found`**(Crawler が生成する ID の形ではなく、存在しない ID と同義。AAPI-P-39。実機では未確認。AAPI-U-12) |
| 409 `job_not_cancellable` | 409 同名 |
| 409 `job_already_finished`(`details.status`) | 409 同名(`details.status` を写す。成功への変換はしない。AAPI-P-21) |
| 400 `invalid_request`(`job_id` 以外) | 502 `crawler_error` |
| 503 `unavailable` | 503 `crawler_unavailable`(実行待ちの取消の後のロック削除の失敗を含む。再送は 409 `job_already_finished`。crawler-api 4.2) |
| 500・契約外 / 接続前 / 応答喪失 | 502 `crawler_error` / 503 `crawler_unreachable` / 504 `crawler_response_lost` |

**9.2.3 ロック解放** — Crawler `DELETE /sources/{source_id}/lock`(crawler-api 4.3)← EP-08

| 項目 | 内容 |
| --- | --- |
| 送信前の検証 | `source_id` の形式 |
| 成功 | 200 `{source_id, released, failed_job_id}` → 同じ本文 |

| Crawler の応答 | Admin API の応答 |
| --- | --- |
| 409 `lock_in_use`(`details.existing_job`) | 409 `lock_in_use`。`existing_job` は写し、`lock_state` は Admin API が導出 |
| 400 `invalid_request` | 502 `crawler_error` |
| 503 `unavailable`(競合が解けない・ジョブ更新の失敗を含む) | 503 `crawler_unavailable`(ロック削除の後にジョブの更新が失敗したときは、ロックのない `running` のジョブが回復まで残る。crawler-api 4.3) |
| 500・契約外 / 接続前 / 応答喪失 | 502 / 503 `crawler_unreachable` / 504 `crawler_response_lost`(`released` が曖昧になる。再送は `released=false` になりうる。crawler-api 4.3 の既知の限界) |

404 は返らない(設定がなくても解放できる)。Crawler の 404 `not_found` は契約外として 502。

**9.2.4 設定の登録** — Crawler `POST /sources`(crawler-api 4.4.2)← EP-03

| 項目 | 内容 |
| --- | --- |
| 送信前の検証 | `source_id` の形式、型、`ttl_days` / `ttl_seconds` の排他・範囲、`ratio_threshold_percent` の範囲・桁(AAPI-K-2。範囲外は**送らない**)、`min_delete_count` の範囲。`connector_config` の中身・`schedule_cron` の書式・`connector_type` の値は検証しない |
| 送る本文 | `{source_id, connector_type, connector_config, ttl, ratio_threshold, min_delete_count, schedule_cron}`(3.3) |
| 成功 | 201 / 200(保存した設定。`status`・`updated_at` を含む)→ 同じステータス・`SourceSettings` |

| Crawler の応答 | Admin API の応答 |
| --- | --- |
| 400 `invalid_request`(項目が `connector_type`・`connector_config`・`ttl`・`ratio_threshold`・`min_delete_count`・`schedule_cron`) | 400 `invalid_request`(項目名を Admin の名前に写し、`reason` はそのまま。2.6) |
| 400 `invalid_request`(`body`・`unknown_field`・`read_only`、および検証済みの `source_id`) | 502 `crawler_error` |
| 400 `config_invalid` | 400 `config_invalid`(分解。2.5) |
| 409 `source_already_exists`(`details.status`) | 409 同名(`details.status` を写す) |
| 500 `internal_error`(`validate_config` の想定外の例外を含む) | 502 `crawler_error` |
| 503 `unavailable` | 503 `crawler_unavailable` |
| 接続前 / 応答喪失 | 503 `crawler_unreachable` / 504 `crawler_response_lost`(再送は 200 の冪等応答か 409 になる。同じ内容なら安全) |

**9.2.5 設定の更新** — Crawler `PUT /sources/{source_id}`(crawler-api 4.4.3)← EP-04

| 項目 | 内容 |
| --- | --- |
| 送信前の検証 | 9.2.4 に同じ(`source_id`・`connector_type` は本文にない) |
| 送る本文 | `{connector_config, ttl, ratio_threshold, min_delete_count, schedule_cron}`(全置換) |
| 成功 | 200(保存した設定。同じ内容なら書き込まず `updated_at` も不変)→ 200 `SourceSettings` |

| Crawler の応答 | Admin API の応答 |
| --- | --- |
| 404 `source_config_not_found` | 404 同名 |
| 409 `source_deleting` | 409 同名 |
| 400 `invalid_request` / 400 `config_invalid` | 9.2.4 に同じ。**`config_invalid` が先に返りうるのは 409 `source_deleting` に対してだけ**(設定があり種別が読めるとき、削除中でも先に検証される)。**設定がない・種別が読めないときは検証せず、404 / 500(→ 502)になる**(crawler-api 4.4.3 の手順 3・4。同「順序の帰結」の文言の曖昧さは HO-10。R1 I-3) |
| 500 `internal_error`(既存の設定が形式不正で `status`・`connector_type` が読めない。`validate_config` の想定外の例外) | 502 `crawler_error` |
| 503 `unavailable`(競合が解けない場合を含む) | 503 `crawler_unavailable` |
| 接続前 / 応答喪失 | 503 `crawler_unreachable` / 504 `crawler_response_lost`(再送しても同じ内容なら 200 で書き込まれない) |

**9.2.6 ソース削除ジョブ起動** — Crawler `POST /sources/{source_id}/delete-jobs`(crawler-api 4.6)← EP-05

| 項目 | 内容 |
| --- | --- |
| 送信前の検証 | `source_id` の形式。画面の確認(DLG-2)は画面の責務で、API にはない |
| 成功 | 202(`job_id`・`job_type`・`source_id`・`status`・`trigger`・`queued_at`)→ 202 `JobAccepted`(`force_delete`・`rewrite_mode` は `null`) |

| Crawler の応答 | Admin API の応答 |
| --- | --- |
| 404 `source_config_not_found` | 404 同名 |
| 409 `maintenance_enabled` | 409 同名 |
| 409 `lock_held`(`details.existing_job`。削除ジョブが実行待ち・実行中のときを含む) | 409 `lock_held`(`lock_state` を導出。`options_applied`・`requested` なし) |
| 400 `invalid_request` | 502 `crawler_error` |
| 503 `unavailable` | 503 `crawler_unavailable` |
| 500・契約外 / 接続前 / 応答喪失 | 502 / 503 `crawler_unreachable` / 504 `crawler_response_lost`(再送は 409 `lock_held` で確認できる) |

`source_deleting` は返らない(削除中も受け付ける。CAPI-P-12)。

---

## 10. 失敗時の振る舞い

### 10.1 原則(承認済みの案。AAPI-P-2)

- **読み取りは継続し、書き込み系(EP-03〜08)だけが失敗する**。読み取り系の EP-01・02・09〜12 は OpenSearch だけ、EP-14 は設定だけに依存するので、Crawler・Indexer が停止中・回復中でも応答する。EP-13 は各コンポーネントの確認結果を返し、コンポーネントの停止は応答の失敗ではなく `state` として表す(200)。
- **部分失敗**は、本体を 200 で返し、取得できなかった項目を `null`+`unavailable`(2.2)にする。その EP の主たる読み取りの失敗は 503 `unavailable`。
- **Crawler への書き込みは自動再送しない**(A 5.6)。結果が不明(504)のときは、画面が状態を確認してから再操作する。
- Admin API が Indexer を呼ぶのは `/healthz`(EP-13)だけ。Indexer の停止は、EP-13 の `indexer` の `state` と、Crawler のジョブの失敗(`indexer_unavailable`。J1・J2 に現れる)として見える。

### 10.2 障害別の挙動(承認済みの案(ゲート3)。AAPI-P-32)

| 障害 | Admin API の挙動 | 画面への影響 |
| --- | --- | --- |
| **Crawler 停止中**(接続拒否・名前解決失敗) | EP-03〜08: 503 `crawler_unreachable`(`retryable=true`)。EP-13: `crawler` が `abnormal`。他の EP は通常どおり | 登録・更新・起動・取消・解放・削除は失敗として表示し、入力は残す(画面仕様 2.4・7.7 の通信失敗)。表示は継続。実行中だったジョブはリース期限を過ぎると `stalled=true`(止まったジョブ)になる |
| **Crawler の起動直後(回復中。最大約 3 分)** | 上と同じ(接続前の失敗)。回復後は自動で応じる。回復で実行中だったジョブは `failed`(`crawler_restart`)になる(CA 5.8) | 上と同じ。D1 は `crawler` が一時的に `abnormal` |
| **Crawler の応答が遅い・切断** | EP-03〜08: 504 `crawler_response_lost`(`outcome_unknown=true`) | 「結果を確認できません」。画面は状態を再取得して確認する(起動系は再送すると 409 `lock_held` で受付済みのジョブが分かる) |
| **Crawler が Store 層の障害を返す**(503) | 503 `crawler_unavailable`(`retryable=true`) | 時間をおいて再試行。読み取り系も同じ OpenSearch に依存するので同時に失敗しうる |
| **Crawler の想定外・契約外の応答** | 502 `crawler_error` | 想定外のエラー(管理者に連絡)。Admin API か Crawler の不具合 |
| **Indexer 停止中** | Admin API の読み取り・操作に影響なし。EP-13: `indexer` が `abnormal`(`connection_refused` など) | D1 に異常。起動したクロールは Crawler が Indexer に届かず `failed`(`indexer_unavailable`)になり、J1・J2 に現れる(受付は Indexer を呼ばないため起動は受け付けられる) |
| **OpenSearch 停止中** | EP-01・02・09・10・11・12: 503 `unavailable`。EP-03〜08: Crawler も OpenSearch に依存するため 503 `crawler_unavailable`(または Crawler が停止して `crawler_unreachable`)。EP-08 の 409 の `lock_state` は `unknown`。EP-13: `opensearch` が `abnormal`(接続拒否・名前解決失敗)または `undetermined`(タイムアウト)で、他は通常。EP-14: 通常 | 読み取り画面は「取得できません」(前回データがあれば古いデータの警告。画面仕様の stale)。D1 は表示を続け、`opensearch` に異常 |
| **索引単位の障害**(`loreley-jobs` だけ・検索インデックスだけが読めない) | EP-01: 200 で該当項目を `null`+**その行の `unavailable`**(`last_crawl`・`last_crawl.stalled`・`document_count` など。失敗した行だけ。一括の失敗は全行)。EP-02: 200 で該当項目を `null`+最上位の `unavailable`。EP-09・10: `loreley-jobs` の失敗は 503。EP-11: 一覧の読み取りの失敗は 503、件数の失敗は `null`+最上位の `unavailable`、`existence` の失敗は `unknown`+その行の `unavailable`。EP-10: ロック文書・`loreley-deletions` の失敗は `null`+`unavailable` | 該当項目だけ「—」+「取得できません」(S1・S2・X1)。J2 の削除結果の現在値は「結果不明」の説明 |
| **`web` のファイルがない**(ビルド成果物の欠落) | EP-13: `web` が `abnormal`(`missing`)。API は動く | 画面が開けない場合は API だけが動く(D1 を見られない)。ブラウザ側の扱いは E |
| **`api` 自身に届かない** | (応答なし) | Admin View の表示・操作がすべて失敗する。前回データの警告(E・F)。D1 の「判定不能」への降格はクライアント側(画面仕様 `dashboard-v0.1.md` 4.3) |
| **cron のタイムゾーンが未設定** | EP-14: `cron_timezone=null` | 「適用されるタイムゾーンを取得できません」の警告(S3・S4)。保存は止めない |

### 10.3 画面別の影響(要約)

| 画面 | Crawler 停止 | OpenSearch 停止 | Indexer 停止 |
| --- | --- | --- | --- |
| D1 | `crawler` 異常。他は表示 | `opensearch` 異常。他は表示 | `indexer` 異常 |
| S1 | 一覧は表示。起動・削除は失敗 | 取得失敗(前回データ) | 影響なし |
| S2 | 表示は継続。起動・編集・解放・削除は失敗 | 取得失敗 | 影響なし |
| S3・S4 | 保存は上部のアラート(入力は残る) | S4 は現在値が取れずフォームを出さない。S3 は Crawler 経由で失敗 | 影響なし |
| J1・J2 | 表示は継続(リース切れの検知あり)。取消・再実行・解放は失敗 | 取得失敗 | ジョブが `indexer_unavailable` で失敗して現れる |
| X1 | 影響なし | 取得失敗(件数は「—」) | 影響なし |
| O1 | 影響なし | 取得失敗 | 影響なし |

---

## 11. 確認状況

### 11.1 確認した事実(2026-11-22)

- 機能設計(AF-1〜20、AF-U-1・3・5・6・7・9・10・13、6.1)、画面仕様(`admin-view-v0.1.md` の 4・5・7・10 章(10.3・10.4)、`admin/dashboard`・`sources`・`jobs`・`documents`・`opensearch` の各「データ項目」と関連章)、DS 10章を読み、1.4 の検算に使った。
- crawler-api v0.4(1〜4章・5.2〜5.4)、crawler-architecture v0.4(2・3.2・3.3・4.2・4.3・4.8・5.1・5.4・7.6・7.7・10・11章)、indexer-api v0.10 の 1章、`search-index-v0.10.md`(項目・`summary_status`・`index_status`)、`loreley-deletions-v0.10.md`(2.2)、`infra/opensearch/` の索引名、`deploy/compose/compose.yaml`(ポート・索引名)を読んだ。
- 本文化にあたり(フェーズ2-1)、次を読んで項目名・code・ステータスを引用した: crawler-api v0.4 の 3〜4.6 章(各 API のリクエスト・応答・エラー・順序)、crawler-architecture v0.4 の 3.2・3.3(`loreley-sources`・`loreley-jobs` の項目)・4.8(失敗理由)・5.1(ロック文書)・7.6・7.7(確認結果の区分・登録結果)、`infra/opensearch/schema/jobs.json`・`sources.json`・`deletions.json`(項目と型。`confirmation`・`failure_reason`・`registration` などは `dynamic: false` の索引で `_source` から読む)、`apps/crawler` の `crawl/status_polling.py`(`deletion_summary` の項目、`confirmation` の値 `confirmed`・`unconfirmed`・`unknown`、`observed_at`)、画面仕様の各「データ項目」と文言・状態。
- 技術事実(`cat.*` の JSON 取得、FastAPI の `app.frontend()` ほか)はフェーズ0の tech-advisor の報告(0004)による。本書の作成者は再確認していない。

確認していないこと: `cluster.health`・`cat.*` の項目名の実機での確認(AAPI-U-4・U-11)、Crawler・Indexer の実機での `/healthz` の挙動と起動直後の見え方(AAPI-U-1)、`config_invalid` の `message` の実際の形式(Connector の実装での確認。AAPI-U-2)、`cat.*` の値の型(AAPI-U-4)、集計の負荷(AAPI-U-5)。

### 11.2 確定(AAPI-K)

確定にしたのは、ユーザーの明示的な回答と、確定として書かれている既承認文書の引用だけ。承認済みの案を引用したもの、ゲート1で承認された方針は確定にしない(11.3)。

| ID | 内容 | 出典 |
| --- | --- | --- |
| AAPI-K-1 | Admin API は Crawler への 6 つの操作の中継と、`loreley-sources`・`loreley-jobs`・`loreley-deletions`・検索インデックス・クラスタ情報の**読み取りのみ**を行い、何にも書かない(メンテナンスフラグも書かない)。設定の取得・一覧は直接読む | CAPI-K-5(確定。`loreley-jobs` に書くのは Crawler だけ)、CAPI-U-2(解消。ユーザー回答 2026-11-16)、SD §14.2・§14.4、BAPI-K-8 |
| AAPI-K-2 | しきい値の範囲(0 以上 1 未満)の検証は Admin API だけが行い、範囲外は Crawler に渡さない | CAPI-K-3(確定。CA-K-16)、SD §3.5、PD §8.2 |
| AAPI-K-3 | `force_delete` は手動起動だけで指定できる | CAPI-K-2(確定) |
| AAPI-K-4 | データソースの削除はソース削除ジョブの起動で行い、設定だけを消す API は置かない | CAPI-K-8(確定。ユーザー回答 2026-11-13) |
| AAPI-K-5 | `config_invalid` は**分解方式**: Admin API が Crawler の `message` を項目と違反の種類に分解して返す。分解不能・切り詰めは画面が上部のアラートにフォールバック。**connector の検証規則は複製しない**(案(b)は採らない)。**ユーザーの回答は明示されている(0004)。確定は方式のみ**で、分解の規則・`field` の表記・例外(`connector_config` 自身)・形は承認済みの案(ゲート2。AAPI-P-12) | ユーザー回答(2026-11-22。0004) |
| AAPI-K-6 | (欠番。確定ではなく承認済みの案(ゲート1)のため AAPI-P-35 に移した。R1 I-5) | — |
| AAPI-K-7 | Indexer・Crawler の死活は `/healthz` を直接読む(BAPI-K-5) | ユーザー回答(2026-11-22。0001 Q1') |
| AAPI-K-8 | cron のタイムゾーンは Admin API の環境変数で持つ。環境変数名は承認済みの案(ゲート2。AAPI-P-11) | ユーザー回答(2026-11-22。0001 Q1) |
| AAPI-K-9 | (欠番。確定ではなく承認済みの案(画面仕様のゲート B・C の承認事項の引用)のため AAPI-P-40 に移した。R1 再確認 N-3) | — |

ダッシュボードの更新間隔 30 秒・Dashboards の外部リンク(旧 AAPI-K-9)は、画面仕様のゲート B・C の承認事項の引用で、確定にせず AAPI-P-40 にした。時刻を ISO 8601(UTC)で返すことも確定にしていない(BAPI-P-20。承認済みの案(既承認文書の引用)。ゲート3でユーザー確認済み。2026-11-23)。「メンテナンスフラグは書かない」は AAPI-K-1(CAPI-K-5)、「AF-19 は表示のみ」は承認済みの案(AAPI-P-36)。

### 11.3 案・承認済みの案(AAPI-P)

「0002 4章」は作業プランの事項番号。区分欄に承認したゲート(ゲート1=方針、ゲート2=具体値・名前。いずれも 2026-11-22)を書いた。確定(`-K-`)にはしていない。

| ID | 内容 | 区分 | 0002 4章 | 章 |
| --- | --- | --- | --- | --- |
| AAPI-P-1 | ページング: S1・O1 は全件返却、J1・X1 はサーバー側(`page`・`items_per_page`・`sort`)。深いページの上限と既定の並び順は 2.1 | 承認済みの案(方針はゲート1、具体値・名前はゲート2。2026-11-22) | 1 | 2.1 |
| AAPI-P-2 | エラー写像の一般則: Crawler の 400・404 は写像、409 は拒否理由 code と既存ジョブ情報、503・接続エラーは読み取り継続・書き込み系のみ失敗。回復中は接続エラー(503 系)。Crawler の code は同名で返す | 承認済みの案(方針はゲート1、具体値・名前はゲート2。2026-11-22) | 2 | 2.3・2.6 |
| AAPI-P-3 | エンドポイントの一覧・パス・メソッド(EP-01〜14) | 承認済みの案(ゲート2。2026-11-22。再実行の専用 EP を除く。ゲート2の一覧に行がなく、「採用は `/meta` のみ・他の具体値・名前は案どおり」の回答から承認として扱った(解釈)。ゲート3でユーザー確認済み。2026-11-23) | — | 1.1 |
| AAPI-P-4 | リース切れ=実行中かつリース期限超過(`stalled`)。最終クロール完了日時=成功・一部成功の `finished_at` の最大値(`last_completed_at`)。登録結果=`loreley-jobs` の保存値(`partial`+`phase`) | 承認済みの案(ゲート1。2026-11-22) | 5 | 2.9・3.1・5.2 |
| AAPI-P-5 | X1: タブ件数は各取得で併せて返す(`tab_counts`)。「既存 / 新規 / 確認できません」は検索インデックスの `document_id` の有無で導出(ページ単位の一括検索。上限 100 件) | 承認済みの案(方針はゲート1、具体値・名前はゲート2。2026-11-22) | 6 | 6.1 |
| AAPI-P-6 | O1: クラスタヘルス・インデックス・シャード・ノード名を 1 応答で全件返却。絞り込みは画面側。件数の上限は 1,000 インデックス(超過は切り詰め+`truncated`) | 承認済みの案(方針はゲート1、具体値・名前はゲート2。2026-11-22) | 7 | 7.1 |
| AAPI-P-7 | `ttl`・`min_delete_count` は型・範囲・int64 だけを Admin API が検証(`ttl` の下限を除く。`ttl` の下限 1 は AAPI-P-37、`min_delete_count` は 0 以上)。しきい値は 0 以上 100 未満(%) | 承認済みの案(ゲート1。2026-11-22) | 8 | 2.4 |
| AAPI-P-8 | D1: 各 `/healthz` を直接取得し、タイムアウト 3 秒、失敗は「判定不能」。`api` は応答できれば正常、`web` は静的ファイルの存在、任意コンポーネントは確認用 URL の環境変数の有無。最終取得成功日時はクライアントが保持。異常と判定不能の境界は 8.1 | 承認済みの案(方針はゲート1、具体値・名前はゲート2。2026-11-22) | 9 | 8.1 |
| AAPI-P-9 | 要約の有効 / 無効は返さない(画面は条件付き文言のまま) | 承認済みの案(ゲート1。2026-11-22) | 10 | 4.1・6.1・8.2 |
| AAPI-P-10 | Dashboards 導線: `api` の環境変数でブラウザから到達できる URL を設定、未設定ならリンクを出さない。メタ情報の API で返す | 承認済みの案(方針はゲート1、具体値・名前はゲート2。2026-11-22) | 11 | 8.2 |
| AAPI-P-11 | cron のタイムゾーンの環境変数名 `LORELEY_API_CRON_TIMEZONE`(IANA 名。未設定は `null` で返す)。Crawler の `LORELEY_CRAWLER_TIMEZONE` と同じ値を渡すことは運用前提 | 承認済みの案(ゲート2。2026-11-22。環境変数で持つことは確定。AAPI-K-8) | 13 | 8.2 |
| AAPI-P-12 | `config_invalid` の分解の規則(最初の `: ` で分ける・項目の形・`field` の表記・フォールバックの条件・`crawler_message`) | 承認済みの案(ゲート2。2026-11-22) | 3 | 2.5 |
| AAPI-P-13 | `lock_held` の 409 の形(`options_applied`・`requested`・`existing_job`・`lock_state`) | 承認済みの案(ゲート2。2026-11-22) | 4 | 2.7 |
| AAPI-P-14 | 単位の変換: Admin API が日 → 秒、% → 割合に変換。リクエストは `ttl_days` または `ttl_seconds`、`ratio_threshold_percent` | 承認済みの案(ゲート2。2026-11-22) | — | 2.8 |
| AAPI-P-15 | (不採用)失敗ジョブの再実行の専用エンドポイント(`POST /jobs/{job_id}/rerun`。最新の失敗ジョブだけ・指定を引き継ぐ・409 `job_not_rerunnable`)。再実行は、画面が J2 の応答をもとに EP-06 を呼ぶ(4.1) | 不採用として扱った(ゲート2の回答で採用が選ばれなかったため。解釈。ゲート3(2026-11-23)で不採用のままでよいと明示回答)。ID は欠番として残す | — | 4.1 |
| AAPI-P-16 | 部分失敗: 本体は 200 で `null`+`unavailable`。**一覧の EP(EP-01・09・11)は各行に `unavailable` を持ち(キーは行の相対パス)、最上位 `unavailable` は行に属さない項目だけ**。主たる読み取りの失敗は 503(AAPI-P-42) | 承認済みの案(ゲート3)の修正(PR #10 のレビュー指摘への対応。2026-11-23) | 1・6 | 2.2 |
| AAPI-P-17 | ロック状態 7 値(`lock_state`) | 承認済みの案(ゲート3。2026-11-23) | — | 2.9 |
| AAPI-P-18 | ジョブの導出フラグ(`stalled`・`cancellable`・`latest_for_source`・`rerunnable`・`rerun_blocked_reason`・`cancel_after_finish_notice`。画面が操作を出し分けるためのもので、サーバー側では強制しない) | 承認済みの案(ゲート3。2026-11-23) | 5 | 2.9 |
| AAPI-P-19 | Crawler 起因のエラー code 4 種(`crawler_error`・`crawler_unavailable`・`crawler_unreachable`・`crawler_response_lost`)と、書き込みの自動再送なし | 承認済みの案(ゲート2。2026-11-22) | 2 | 2.3 |
| AAPI-P-20 | `connector_config` は不透明に中継・返却(5 項目の補完・加工をしない。上限値は返さない。既定値の補完は画面) | 承認済みの案(ゲート2。2026-11-22) | — | 3.2・8.2 |
| AAPI-P-21 | 取消の `job_already_finished`(409)は成功に変換せず、画面が成功扱いにする | 承認済みの案(ゲート2。2026-11-22) | — | 2.3・4.2 |
| AAPI-P-22 | メタ情報の EP-14(`cron_timezone`・`dashboards_url`)。要件外の追加案のうち、ゲート2で採用されたのはこれだけ | 承認済みの案(ゲート2。2026-11-22) | 11・13 | 8.2 |
| AAPI-P-23 | 登録文書数の数え方: 検索インデックスの `source_id` の全文書(抽出失敗・要約未生成を含む) | 承認済みの案(方針はゲート1、具体値・名前はゲート2。2026-11-22) | 5 | 3.1 |
| AAPI-P-24 | 入力の規約: パス ID の形式と符号化(`quote(safe="")` の後に `.` を `%2E` に置換)、未知のクエリ・本文の項目は 400、本文が空なら `Content-Type` を問わず許し(`{}` 扱い)、あれば `application/json` の JSON オブジェクト、型は厳密(`30.0` は整数でない)、違反は全部返す、本文を読まない EP、検証の順序 | 承認済みの案(ゲート3。2026-11-23) | 2 | 2.12 |
| AAPI-P-25 | (OpenSearch の HTTP 200 の部分的な失敗は失敗として扱い、`timed_out=true` は `timeout`。C の案 AAA-P-39)応答の共通 DTO(`SourceSettings`・`JobBrief`・`JobAccepted`・`ExistingJob`)の項目名・型・`null` 条件。`unavailable` は、単一の応答では最上位のオブジェクトで、キーは項目の正式なパス、一覧の EP では各 `items[i]` の `unavailable`(キーは行の相対パス。AAPI-P-42)で、理由コードは `store_unavailable`・`search_index_unavailable`・`timeout`(優先)・`malformed`。**ジョブ記録・削除記録由来の項目は、保存値が読めないとき `null`(`unavailable` に載せない)で、`JobBrief` の `status`・`job_type`・`trigger`・`queued_at`、`registration` の件数・`partial` などの型は `null` を許し、`phase` は `partial` が `null` のとき `null`**(C 5.0・5.8 の承認済みの案(ゲート3)。AAA-P-25) | 承認済みの案(ゲート3)の修正(PR #10 のレビュー指摘への対応。2026-11-23) | — | 2.2・2.11 |
| AAPI-P-26 | EP-09 の入力: `source_id` が未登録なら 404 にせず空の結果、`status` の列挙値(`active` を含む)、`sort` は `queued_at` だけ | 承認済みの案(ゲート3。2026-11-23) | 1 | 5.1 |
| AAPI-P-27 | `stalled` の補足: 実行中でロック文書がない、または別のジョブのロックなら(確認読みの後)`true`(推測)、ロックを読めなければ `null`(その行・応答の `unavailable` の `stalled`。一覧は行単位。AAPI-P-42)、`null` のとき `cancellable=false` | 承認済みの案(ゲート3)の修正(PR #10 のレビュー指摘への対応。2026-11-23) | 5 | 2.9 |
| AAPI-P-28 | Crawler クライアントの規約: 固定のパス、リダイレクトに従わない、`error.code` で分岐し `message` は `config_invalid` のときだけ通す、JSON でない・未知の code は 502、起動時の回復中は `crawler_unreachable` | 承認済みの案(ゲート3。2026-11-23) | 2 | 9.1 |
| AAPI-P-29 | EP-10 の削除結果の読み取り: `crawl` ジョブだけ `deletion` を返す、実行待ちは読まず `not_found`、`current_state`・`fetched_at`、`settings` は設定スナップショットから | 承認済みの案(ゲート3。2026-11-23) | 5 | 5.2 |
| AAPI-P-30 | EP-11 の補足: 設定の存在確認(404)、同順位は `document_id` の昇順、`existence` の失敗は**その行の `unavailable` の `existence`**(一括検索の全体の失敗は全行。AAPI-P-42) | 承認済みの案(ゲート3)の修正(PR #10 のレビュー指摘への対応。2026-11-23) | 6 | 6.1 |
| AAPI-P-31 | EP-12 の値の正規化: `cat.*` の文字列を整数・`null` に変換、`prirep` → `role`、`state` は小文字、`relocating` の `node` は移動元(推測)、インデックス一覧にないインデックスは `null` で補う | 承認済みの案(ゲート3。2026-11-23) | 7 | 7.1 |
| AAPI-P-32 | 障害別の挙動(10.2・10.3)。各障害での EP の応答と画面への影響 | 承認済みの案(ゲート3。2026-11-23) | 2 | 10 |
| AAPI-P-33 | EP-13 の `reason` の値(`connection_refused`・`name_not_resolved`・`unexpected_status`・`missing`・`timeout`・`connection_error`)と、`opensearch` の判定(HTTP エラーの応答は `abnormal`) | 承認済みの案(ゲート3。2026-11-23) | 9 | 8.1 |
| AAPI-P-34 | EP-02 で保存済みの設定項目が読めないとき、その項目を `null` にして `unavailable.<項目名>=malformed` を付ける(S4 の修復の入口を残す) | 承認済みの案(ゲート3。2026-11-23) | — | 3.2 |
| AAPI-P-35 | `lock_held` は成功扱いにせず 409 で既存ジョブと「指定は反映されていない」を返す(SD §14.4 の冪等成功案は採らない) | 承認済みの案(ゲート1。2026-11-22。0003)。旧 AAPI-K-6 から区分を訂正 | 4 | 2.7 |
| AAPI-P-36 | AF-19(メンテナンス中の表示)は表示のみで、専用の EP を置かない(拒否 code `maintenance_enabled` と失敗理由 `maintenance` の表示) | 承認済みの案(ゲート1。作業プラン 2章)。機能設計の AF-P-3(ユーザー未確認の前提)に基づく | — | 1.1 |
| AAPI-P-37 | `ttl` の範囲は**1 以上**(ゲート1の「型・非負・int64 範囲」(作業プラン 4章 #8)からの変更。画面仕様 `sources-v0.1.md` 2.3 の TTL「1 以上の整数」に合わせた。`min_delete_count` は 0 以上) | 承認済みの案(ゲート3。2026-11-23) | 8 | 2.4・3.3 |
| AAPI-P-38 | 応答の `ratio_threshold_percent` は、保存値の十進数の文字列表現を介して厳密に 100 倍する。保存値が小数第 3 位以下を持つと再保存で `format` になるため、画面が注意を出して丸めさせる(秒指定のような逃げ道は足さない) | 承認済みの案(ゲート3。2026-11-23) | — | 2.8 |
| AAPI-P-39 | EP-07(取消)で、Crawler が `job_id` を理由に返す 400 `invalid_request`・404 `not_found`(`%`・`?` などを含む `job_id` は Admin API の検証を通る)を、502 でなく 404 `job_not_found` に写す(Crawler が生成する ID の形ではなく、存在しない ID と同義) | 承認済みの案(ゲート3。2026-11-23) | 2 | 2.12・2.6・4.2・9.2.2 |
| AAPI-P-40 | ダッシュボードの更新間隔は 30 秒、OpenSearch Dashboards への導線は外部リンク(設定時のみ)。画面仕様 `dashboard-v0.1.md` 4.1(`admin-view-v0.1.md` 10.1 #26。承認済み(ゲート C 2026-11-22))、`admin-view-v0.1.md` 3章(ナビ。承認済み(ゲート B))の引用。機能設計 AF-18(更新間隔)・AF-20(導線の経路)は後続設計に委ねていた(AF-U-3(c)・AF-U-11)。旧 AAPI-K-9 から区分を訂正 | 承認済みの案(画面仕様のゲート B・C の承認事項の引用。ユーザー確認済み(ゲート3。2026-11-23)) | — | 8.1・8.2 |
| AAPI-P-41 | `rerun_blocked_reason` に `source_missing`(データソースの設定がない=削除済み)を足す。`rerunnable=null` の条件に「データソースの設定の読み取りの失敗」を加える(C 5.3 の評価順)。画面仕様に理由の文言がないため、E・F・画面仕様の追従が要る | 承認済みの案(ゲート3。2026-11-23) | — | 2.9・5.2 |
| AAPI-P-42 | **一覧の EP(EP-01・09・11)の `unavailable` を行単位にする**。各 `items[i]` に `unavailable` を持たせ(常に存在。なければ `{}`)、キーは行の中の項目の相対パス(`last_crawl`・`last_crawl.stalled`・`last_completed_at`・`delete_job`・`delete_job.stalled`・`document_count`・`stalled`・`existence`)。最上位 `unavailable` は行に属さない項目(EP-11 の `tab_counts.<タブ>`・`document_count`)だけで、`items[].…` 形式のキーは廃止。「`null` +キーあり」=取得できなかった、「`null` +キーなし」=値がない。一括の失敗は全行に同じキー。単一の応答(EP-02・10・12・13・14)は変えない。AAPI-P-16・25・27・30 の修正 | 承認済みの案(ゲート3)の修正(PR #10 のレビュー指摘への対応。2026-11-23) | — | 2.2・2.11・3.1・5.1・6.1 |

### 11.4 未決(AAPI-U)

| ID | 内容 | 決める場所 |
| --- | --- | --- |
| AAPI-U-1 | 起動時の回復中・起動直後に、Crawler・Indexer への接続が実機でどう見えるか(接続拒否・名前解決失敗のどちらか。CAPI-U-1 の Admin API 側) | 実機・Integration Test |
| AAPI-U-2 | `config_invalid` の `message` の形式依存(Crawler 側の変更で壊れる)。Crawler が項目別の構造を返せば不要。Connector が増えたときの `crawler_message` の安全性。**`detail` は Connector が定める日本語の固定文で、画面は完全一致の対応表で照合する**(固定文の変更で照合できなくなる。`connector_config` 自身の違反は `field=connector_config`。2.5) | HO-11(A 9章)、Crawler 設計 |
| AAPI-U-3 | 失敗理由・警告・削除結果の状態名と理由コードは上流の案(CA-P-10・73、loreley-deletions §3)。確定時に再確認 | Crawler・Indexer 設計の確定時 |
| AAPI-U-4 | `cat.*` の値の型(文字列になる想定)、クローズ済みインデックスの `null`、未割り当てシャードの `node`(`null` になる想定)、`cat.indices` の追加列(0004)。`cluster.health`・`cat.*` の項目名は OpenSearch の標準の API による(実機では未確認) | 実装時 |
| AAPI-U-5 | EP-01 の件数の集計・EP-09 の `stalled` 導出の負荷(実測) | C、実装後 |
| AAPI-U-6 | `just_acquired` の猶予(60 秒)は Crawler の仮値(crawler-architecture 11章)と合わせる必要がある(同期の方法) | C |
| AAPI-U-7 | スキップ記録の `document_id` が検索インデックスの `_id` と一致すること(interface 5.2 の算出値)の確認 | 実装時 |
| AAPI-U-8 | 要約未生成タブの実データでの検証は、要約機能(LLM プロバイダ)の実装後(AF-14) | 実装後 |
| AAPI-U-9 | 実行中なのにロック文書がないジョブの扱い(本書は `stalled=true`。推測。Crawler の回復・解放の動作との整合を確認) | C、実機 |
| AAPI-U-10 | 保存済みの設定項目が読めないときの扱い(`null`+`malformed`。S4 の画面の扱いは E・F) | E・F、C |
| AAPI-U-11 | opensearch-py の例外・HTTP エラーと、EP-13 の `opensearch` の `abnormal` / `undetermined` の対応、`cat.shards` の `relocating` の `node` の形(0004 の未確認事項) | 実機・C |
| AAPI-U-12 | `job_id` を符号化(`quote(safe="")` + `.` → `%2E`)して Crawler に送ったときの、`%`・`?`・`.`・`%2F` を含む ID の Crawler の挙動(crawler-api 3.3「パスの扱い」は TestClient の実測で、実 uvicorn は未確認)。400 `invalid_request`・404 `not_found` が返れば、EP-07 では 404 `job_not_found` に写す(AAPI-P-39) | 実機・Integration Test |

### 11.5 既存設計との不整合(I-n)

| ID | 内容 | 本書での扱い |
| --- | --- | --- |
| I-70 | SD §14.4 は、重複起動の 409 を Admin API が通常は成功として扱う案とするが、本書は成功扱いにせず 409 で返す(AAPI-P-35) | ゲート1の承認(2026-11-22)。逸脱として HO-4 に書いた。画面仕様 7.7 の「SD §14.4 の案になる場合も…」は、成功扱いにしない設計で足りる |
| I-71 | admin-view 10.4 は `config_invalid` の項目別表示を案(b)(Admin API が先に検証)推奨とするが、本書は案(a)(分解方式)を採る(AAPI-K-5) | ユーザー回答(2026-11-22)。画面仕様側の「推奨 (b)」の記述の更新を HO-21 に書いた |
| I-72 | admin-view 10.4(D1)は「`web` と `api` が同居する場合の扱い」を問うが、本書は `web` を静的ファイルの存在で判定する(`api` と同じコンテナのため、`api` が応答できる限り通常は存在する) | 承認済みの案(ゲート2)。画面側の記述の更新は不要(画面は返された `state` を表示するだけ) |
| I-73 | crawler-api 4.1 は、`existing_job.lease_expires_at` が日時として読めないときだけ番兵値 `0001-01-01T00:00:00.000Z` を返す(`null` の規則と異なる) | そのまま通し、画面は期限切れとして扱う(2.11) |
| I-74 | 画面仕様 `dashboard-v0.1.md` 3.3 は判定不能の理由に「結果が古い」を挙げるが、Admin API はリクエストごとに確認するため、この理由を返さない(古さはクライアントが前回データを降格して表す。同 4.3) | 画面側で足りる。画面仕様の更新は不要(理由コードの一覧は本書 8.1) |
| I-75 | 機能設計 AF-5 は、元ジョブの両指定を「Admin API が読んで起動の指定に渡す」(導出)とするが、専用の再実行 EP が採用されなかったため、本設計では **画面が EP-10 の応答(`force_delete`・`rewrite_mode`・`rerunnable`)をもとに EP-06 を呼ぶ**(4.1) | 機能設計の記述を「Admin View が API の応答から渡す」と読み替える。HO-19(機能設計 AF-5 の追記) |

### 11.6 作業プラン 4章の事項 1〜14 の記録先

| 事項 | 内容 | 記録 ID |
| --- | --- | --- |
| 1 | ページング | AAPI-P-1 |
| 2 | エラー応答 | BAPI-P-5(形式)、AAPI-P-2・P-19(Admin 固有) |
| 3 | `config_invalid` | AAPI-K-5(方式のみ確定。0004)、AAPI-P-12(細部) |
| 4 | `lock_held` | AAPI-P-35(ゲート1の承認)、AAPI-P-13(形) |
| 5 | AF-U-6/9/10 | AAPI-P-4、AAPI-P-23 |
| 6 | X1 | AAPI-P-5 |
| 7 | O1 | AAPI-P-6 |
| 8 | `ttl`・`min_delete_count` | AAPI-P-7 |
| 9 | D1 | AAPI-P-8、BAPI-P-13 |
| 10 | 要約の有効 / 無効 | AAPI-P-9 |
| 11 | Dashboards 導線 | AAPI-P-10、AAPI-P-22 |
| 12 | URL・OpenAPI | BAPI-P-1・P-3・P-4 |
| 13 | cron タイムゾーン | AAPI-K-8、AAPI-P-11 |
| 14 | Web UI の配置・SPA フォールバック | BAPI-P-2 |

**持ち越し論点(機能設計 AF-U)の状態**(決めた / 案 / 後続)

| AF-U | 論点 | 状態 | 本書での扱い |
| --- | --- | --- | --- |
| AF-U-1 | ダッシュボードの死活の取得経路 | 決めた | `/healthz` の直接取得(AAPI-K-7)。EP-13 |
| AF-U-3 | (a) 指定が反映されなかったときの通知 | 決めた(承認済みの案) | 409 `lock_held` の `options_applied=false`・`requested`(AAPI-P-35・P-13。2.7) |
| | (b) 「停止中」表示 | 後続 | 将来拡張(AF-31)。本書の対象外 |
| | (c) ダッシュボードの更新間隔 | 決めた | 30 秒(画面仕様。AAPI-P-40)。API は更新間隔を持たない |
| AF-U-5 | (a) 原本サイズ超過の表示 | 決めた | 専用タブ(画面仕様)。EP-11 `tab=oversize` |
| | (b) 「既存/新規」の導出 | 決めた(承認済みの案) | 検索インデックスの `document_id` の有無(AAPI-P-5。EP-11 `existence`) |
| | (c) 本文の切り詰めの表示先 | 後続 | X1 に置かない(画面仕様 7.3)。Search View で扱う |
| AF-U-6 | 検索インデックス参照の形・件数の数え方・リース切れの判定・409 の扱い・取消完了の確認 | 決めた | EP-11・登録文書数(AAPI-P-23)・`stalled`(AAPI-P-4。導出は C)・2.7・9章・`cancel_after_finish_notice`(EP-10)。取消の完了は J2 の `status` で確認(画面の自動更新) |
| AF-U-7 | しきい値・TTL の入力検証と単位 | 決めた(承認済みの案) | Admin API が検証・変換(AAPI-P-7・P-14)。TTL の下限 1 は承認済みの案(ゲート3。AAPI-P-37) |
| | 強制削除・再書き込み・再実行の確認の出し方 | 後続(画面) | 画面仕様(DLG-1・DLG-4)。API は指定を受けるだけ |
| AF-U-9 | 最終クロール完了日時の定義 | 決めた(承認済みの案) | 成功・一部成功の `finished_at` の最大値(`last_completed_at`。AAPI-P-4) |
| AF-U-10 | 登録結果の数え方・形・保持期間 | 形は決めた。数え方・保持は後続 | 形は EP-10 の `registration`(`phase`)。数え方は Crawler の保存値のまま(CA 7.7)。保持はジョブ記録を自動で消さない(CA 3.5。運用で手動整理) |
| AF-U-13 | cron のタイムゾーン取得 | 決めた | Admin API の環境変数(AAPI-K-8・P-11)を EP-14 で返す。次回実行予定日時は MVP に含めない |

### 11.7 ゲート2確認事項一覧

具体値・名前は**案として置いた値**で、ユーザーの回答(ゲート2。2026-11-22)を右端の列に書いた。承認された項目は ID の区分を「承認済みの案(ゲート2。2026-11-22)」にした(確定にはしていない)。採用が選ばれなかったのは #19(再実行の専用エンドポイント)と #23(`Origin` 検査)で、**不採用として扱い**(ゲート2の回答からの解釈。ゲート3(2026-11-23)で「不採用のままでよい」と明示回答)、本書・A から外した。「正本」は値を定義する文書。

**EP 番号の扱い**: 再実行の専用エンドポイント(旧 EP-08)を外したため、EP-09〜15 を EP-08〜14 に振り直し、欠番はない(EP 番号は本ドラフトの中だけの通し番号で、他文書・外部からの参照がまだないため)。旧 EP-15 `/meta` は EP-14 になった。

| # | 項目 | 案の値 | 理由 | ID | 正本 | 回答(ゲート2。2026-11-22) |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 深いページの上限値 | `page × items_per_page ≤ 10,000`(超過は 400 `invalid_request`・`page` の `range`)。`total` は正確な件数 | OpenSearch の既定の取得上限に合わせる。想定規模(1 万〜10 万文書)で足りる | AAPI-P-1 | B 2.1 | 承認 |
| 2 | 既定の並び順・`items_per_page` | J1 `-queued_at`、X1 は スキップ `-last_skipped_at`・抽出失敗 `-last_seen_at`・サイズ超過 `-last_detected_at`・要約未生成 `-indexed_at`。`items_per_page` は 25・50・100(既定 25) | 画面仕様どおり(新しい順)。並べ替えは各 EP 1 項目 | AAPI-P-1 | B 2.1 | 承認 |
| 3 | エラー code 名一覧 | B 2.3 の表(Admin 固有 14 種: `config_invalid`・`source_config_not_found`・`job_not_found`・`lock_held`・`lock_in_use`・`source_deleting`・`maintenance_enabled`・`source_already_exists`・`job_not_cancellable`・`job_already_finished`・`crawler_error`・`crawler_unavailable`・`crawler_unreachable`・`crawler_response_lost`)と、A 5.2 の共通 code(`invalid_request`・`not_found`・`method_not_allowed`・`http_error`・`internal_error`・`unavailable`) | Crawler の code は同名で返し写像を恒等にする。Admin 固有のうち Crawler 起因は 4 種 | AAPI-P-2・P-19、BAPI-P-5 | B 2.3、A 5.2 | 承認 |
| 4 | `config_invalid` の分解仕様 | 最初の `: ` で分け、前半が `^[A-Za-z_][A-Za-z0-9_]*(\[[0-9]+\])?$` なら成功。`field=connector_config.<項目>`(前半が `connector_config` 自身のときは `field=connector_config`)・`reason=config_invalid`・`detail=<日本語の固定文>`・`details.crawler_message`。`message` が 512 文字、または分解不能なら `errors` を空にして上部アラートへ | 検証規則を複製せず(案(a))、Crawler の固定文の形だけに依存する | AAPI-K-5、AAPI-P-12 | B 2.5 | 承認 |
| 5 | `lock_held` の 409 の形 | 2.7 の JSON(`options_applied=false`・`requested`・`existing_job`・`lock_state`)。`lock_state` は 7 値 | 成功扱いにせず、既存ジョブと「指定は反映されていない」を画面が判別できる | AAPI-P-35、AAPI-P-13 | B 2.7 | 承認 |
| 6 | 登録文書数の数え方 | 検索インデックスの `source_id` の全文書(`index_status`・`summary_status` を問わない。抽出失敗・要約未生成を含む) | 削除ジョブで消える文書の数と一致する(DLG-2) | AAPI-P-23 | B 3.1 | 承認 |
| 7 | X1 の一括検索の上限 | 100 件(1 ページの最大件数と同じ。1 ページ 1 回の一括検索) | 追加の問い合わせを 1 回に抑える。失敗は `unknown` | AAPI-P-5 | B 6.1 | 承認 |
| 8 | O1 の件数上限・超過時 | インデックス 1,000 件。超過は(状態の悪い順 → 名前)で先頭 1,000 件に切り詰め、`truncated=true`・`total_indices` | 応答の大きさの安全網。想定規模では起きない | AAPI-P-6 | B 7.1 | 承認 |
| 9 | D1: タイムアウト・判定境界 | 1 確認 3 秒(`LORELEY_API_HEALTH_PROBE_TIMEOUT_SECONDS`)。異常=接続拒否・名前解決失敗・2xx 以外。判定不能=タイムアウト・その他の通信エラー | 30 秒更新より十分短い。「確認できたうえで応答がない」を異常とする(画面仕様) | AAPI-P-8 | B 8.1 | 承認 |
| 10 | D1: `web` の判定対象 | `LORELEY_API_WEB_DIST_DIR` 直下の `index.html` が読めること | `web` は `api` が静的配信するため、ファイルの存在が実体 | AAPI-P-8 | B 8.1 | 承認 |
| 11 | D1: 環境変数名 | `LORELEY_API_CRAWLER_URL`・`LORELEY_API_INDEXER_URL`、任意は `LORELEY_API_DASHBOARDS_HEALTH_URL`・`LORELEY_API_EMBEDDING_HEALTH_URL`・`LORELEY_API_LLM_HEALTH_URL`(設定があれば確認、なければ `not_configured`) | 設定の有無で「未設定」を判定する(承認済みの方針) | AAPI-P-8 | B 8.1、C | 承認 |
| 12 | Dashboards の URL の環境変数名 | `LORELEY_API_DASHBOARDS_URL`(ブラウザから到達できる URL。未設定ならリンクを出さない) | 確認用の URL(上)と用途が違うため別の変数 | AAPI-P-10 | B 8.2 | 承認 |
| 13 | cron のタイムゾーンの環境変数名 | `LORELEY_API_CRON_TIMEZONE`(IANA 名。未設定は `null`。不正な名前は起動失敗)。compose で `LORELEY_CRAWLER_TIMEZONE` と同じ値を渡す | 環境変数で持つことは確定。名前は Crawler の `LORELEY_CRAWLER_TIMEZONE` に倣う | AAPI-P-11、BAPI-K-7 | B 8.2、A 8 | 承認 |
| 14 | OpenAPI のパス・既定・環境変数 | パス `/api/admin/v1/openapi.json`。**既定は無効**(`LORELEY_API_OPENAPI_ENABLED=true` で有効)。Swagger UI・ReDoc は常に無効。型生成は `app.openapi()` の書き出しで、公開に依存しない | 認証なしの `api` に公開範囲を広げない(tech-advisor の推奨)。標準 UI は外部の CDN に依存する | BAPI-P-3・P-4 | A 5.4 | 承認 |
| 15 | 型生成ツール | Hey API(`@hey-api/openapi-ts`。exact pin)。0.x の更新は都度確認 | TanStack Vue Query の生成プラグインがあり、TypeScript 6 に対応(0004) | BAPI-P-10 | A 5.4、E | 承認 |
| 16 | Admin API の構成 | サブアプリのマウント(`/api/admin/v1` に独立した FastAPI アプリ)。代替は `APIRouter` | Admin 専用の OpenAPI を独立に出せ、Search API・MCP の追加で混ざらない | BAPI-P-9 | A 5.4 | 承認 |
| 17 | Web UI の配置・フォールバックの範囲 | `/admin/` 配下・history モード。**`/admin/` 配下の未知パスだけ `index.html` へ**(`/api/` と、`/admin/` 配下の欠落アセットは返さない)。実装は `app.frontend()` を第一候補 | ゲート1の「`/api/` 以外の未知パスは `index.html`」を Admin View の配置に合わせて解釈した | BAPI-P-2 | A 2.2 | 承認 |
| 18 | TTL・しきい値の単位 | Admin API が変換。リクエストは `ttl_days` または `ttl_seconds`、`ratio_threshold_percent`(小数第 2 位まで)。応答は `ttl_seconds`・`ttl_days`(割り切れなければ `null`)・`ratio_threshold_percent` | 画面仕様(承認済み #2)に従う。日で割り切れない既存値を編集できるよう秒も受ける | AAPI-P-14 | B 2.8 | 承認 |
| 19 | 再実行の専用エンドポイント | (不採用として扱った)`POST /jobs/{job_id}/rerun`(最新の失敗した `crawl` ジョブだけ。`force_delete`・`rewrite_mode` を引き継ぐ。不可は 409 `job_not_rerunnable`) | 対象範囲と引き継ぎをサーバー側で保証する | AAPI-P-15 | B 4.1(代替) | **不採用として扱った**(ゲート2の回答で採用が選ばれなかったため。解釈。ゲート3(2026-11-23)で不採用のままでよいと明示回答)。AF-5 は、画面が J2 の応答(`source_id`・`force_delete`・`rewrite_mode`・`rerunnable`)をもとに EP-06 を呼ぶ(B 4.1。リクエストの項目の追加なし) |
| 20 | 取消の `job_already_finished` | 409 のまま返し、画面が成功扱いにする | 写像を恒等に保つ。`lock_held` を成功にしない方針と整合 | AAPI-P-21 | B 2.3 | 承認 |
| 21 | Crawler への呼び出しのタイムアウト・再送 | 接続 3 秒・応答 60 秒。書き込みは自動再送しない。接続前の失敗=503 `crawler_unreachable`、送信後の応答喪失=504 `crawler_response_lost`(`outcome_unknown=true`) | 冪等でない起動を再送しない(P-5)。再送は 409 `lock_held` で受付済みのジョブを確認できる(crawler-api 3.4) | AAPI-P-19、BAPI-P-12 | A 5.6、B 2.3 | 承認 |
| 22 | `connector_config` の扱い・上限値 | 不透明に中継・返却。`max_patterns`・`max_pattern_bytes` は返さず(画面は既定値 100・1,024 で表示し、最終判定はサーバー)、5 項目の既定値の補完は画面 | Connector の規則を複製しない(AAPI-K-5) | AAPI-P-20 | B 3.2 | 承認 |
| 23 | 書き込み系の `Origin` 検査(追加の提案) | (不採用として扱った)許可リストにない `Origin` の POST・PUT・DELETE を 403 `origin_not_allowed`。許可リスト `LORELEY_API_ALLOWED_ORIGINS`(既定は localhost 系) | 認証なしの localhost API は、悪意あるページからの書き込み要求を受けうる(SD §6.1 の MCP 向けの流儀に倣う)。**要件にない追加**で承認が要る | BAPI-P-15 | なし(A 2.3) | **不採用として扱った**(ゲート2の回答で採用が選ばれなかったため。解釈。ゲート2の時点ではユーザーがリスクを受け入れたことにはしなかった)。A 2.3 に未対応のリスクとして明記し、BAPI-U-8 に登録。**ゲート3(2026-11-23)で、不採用のままでよい・リスクは受け入れ(README に注意書き)・軽い緩和は足さない、と明示回答があった。リスクがなくなったわけではない** |
| 24 | 実装ディレクトリ・ポート | `apps/api/`(パッケージ `loreley_api`)・`apps/web/`。コンテナ内のポート 8080、ホストは `127.0.0.1:${API_HOST_PORT:-8080}` | 既存の `apps/crawler`・`apps/indexer` に揃える。8000・8001 と重ならない | BAPI-P-11・P-14 | A 3、8 | 承認 |

### 11.8 検算の結果(自己検算。R1 の指摘の反映後)

スクリプトで機械的に確認し、画面データ項目は目視で突き合わせた。

- **AF-1〜20**: 1.2 の表に 20 件すべてがあり、それぞれ 3〜8章の EP の本文に対応する(AF-5 は EP-10 の応答と EP-06 のリクエストで足りる。4.1)。対応漏れなし。
- **EP**: 1.1 の表の EP-01〜14 と、3〜8章の見出しが 1 対 1。欠番・旧番号なし。
- **エラー code**: 2.3 の表の各 code の「EP」列と、3〜8章の各 EP の「エラー」表の code が、`crawler_*`(EP-03〜08 の「502・503・504」の行)を除いて一致する(不一致 0)。9章の写像表の code は 2.3 の表の code だけを使う。`job_not_rerunnable`・`origin_not_allowed`・`rerun` は不採用の記録以外に残らない。
- **画面データ項目**: 1.4 の表の応答項目が、3〜8章の応答の表に、同じ名前で定義されている。画面仕様の「データ項目(想定)」で応答に載せないのは、D1 の最終取得成功日時(クライアント保持)と、S3・S4 の取得設定の上限値(返さない)の 2 点だけ。
- **ID**: `BAPI-*`・`AAPI-*` の参照に、未定義はない。定義だけで本文から参照されない ID は、不採用の BAPI-P-15・AAPI-P-15 と、欠番の BAPI-K-6・AAPI-K-6 に限る。
- **JSON の例**: すべての JSON ブロックが JSON として解釈でき、項目名・型・`null` の規則が 2.11 と該当 EP の表に一致する。**同じ `job_id` は、例をまたいで同じ状態にした**(`job-20261122T180000Z-3fa9c2d1`: 失敗(EP-01・02)、`…T030000Z-77aa01bc`: 実行待ち → 実行中(EP-06・09・11)、`…T150000Z-5d2e8a10`: 別ソースの失敗(EP-10)、`…T120000Z-aa41c3d9`: ロック解放で失敗にしたジョブ(EP-08))。EP-12 の例は、概況の件数とシャードの一覧が一致する。EP-13 の例は、トップの `checked_at` が各確認以上。
- **`-K-` の出典**: AAPI-K-1〜5・7・8 は、ユーザーの明示的な回答、または確定として書かれた既承認文書(CAPI-K-n、SD、PD)。承認済みの案の引用と、ユーザーの確認が不明なものは `-K-` から外した(BAPI-K-6、AAPI-K-6、AAPI-K-9。11.2)。残る AAPI-K は 1〜5・7・8。
- **安全性**: 破壊的操作(EP-05・EP-06 の `force_delete`・EP-07・EP-08)、`root` の任意パス(EP-03・04・2.10)、エラー本文に入力値・認証情報・パスを出さないこと、ブラウザ経由の書き込みへの保護がないこと(受け入れた未対応のリスク。ゲート3で確認済み。2026-11-23)を、該当 EP と 2.10 で矛盾なく書いた。
- 次フェーズで確認すること: C・D・F の対応(トレーサビリティ)、導出ロジックの定義(11.10)。

### 11.9 ゲート3(2026-11-23)で承認した新規の案

(ユーザーの判断が分かれうるものの要点は A 9.3(G3-1〜G3-23)。AAPI-P-35・36 はゲート1承認済みの区分訂正のみで、判断は要らない。)

本文化で新たに決めた判断のうち、ゲート2の対象外のもの(ID は 11.3)。区分は「承認済みの案(ゲート3。2026-11-23)」。主な判断の要点を挙げる(ゲート2で承認済みの方針・値の細部で、承認の要否が軽いものを含む)。

| ID | 判断の要点 |
| --- | --- |
| AAPI-P-24 | 未知のクエリ・本文の項目は 400。型は厳密(`30.0` は整数でない)。本文を読まない EP は本文を無視する |
| AAPI-P-25 | 応答の部品(`SourceSettings`・`JobBrief`・`JobAccepted`・`ExistingJob`)の項目名・型。`unavailable` は、単一の応答では最上位でキーは正式なパス、**一覧の EP では各行の `unavailable`(行の相対パス。AAPI-P-42)** |
| AAPI-P-26 | `GET /jobs` で未登録の `source_id` は 404 でなく空の結果 |
| AAPI-P-27 | 実行中でロック文書がないジョブは `stalled=true`(推測)。ロックを読めなければ `stalled=null`・`cancellable=false`(その行の `unavailable` の `stalled`。一覧は行単位) |
| AAPI-P-28 | Crawler クライアント: リダイレクトに従わない、`code` で分岐、未知の `code`・JSON でない本文は 502 |
| AAPI-P-29 | J2 の削除結果: 実行待ちは読まない、`current_state`・`fetched_at`・`settings`(設定スナップショット)を足す |
| AAPI-P-30 | X1 の補足: 設定の存在確認(404)、同順位は `document_id` の昇順、`existence` の失敗はその行の `unavailable` の `existence`(一括の失敗は全行。AAPI-P-42) |
| AAPI-P-31 | O1 の値の正規化(`relocating` の `node` は移動元=推測、インデックス一覧にないインデックスは補う) |
| AAPI-P-32 | 障害別の挙動と画面への影響(10.2・10.3) |
| AAPI-P-33 | D1 の `reason` の値と `opensearch` の判定 |
| AAPI-P-34 | S2・S4 で保存済みの設定項目が読めないとき `null`+`malformed`(S4 の修復の入口を残す) |
| AAPI-P-16・17・18 | (フェーズ1から)部分失敗の表現、ロック状態 7 値、導出フラグ。ゲート2の確認事項一覧に行がなかったため、ここで承認を取る |
| AAPI-P-37 | `ttl` の下限を 1 にすること(ゲート1の「非負」からの変更。画面仕様に合わせた) |
| AAPI-P-38 | 応答の `ratio_threshold_percent` の厳密変換と、小数第 3 位以下を持つ保存値を再保存するときの注意(秒指定のような逃げ道は足さない。代替の選択はユーザー判断) |
| AAPI-P-3 | EP の一覧・パス・メソッドは、ゲート2の一覧に行がなく、回答の文言(採用は `/meta` のみ・他は案どおり)から承認として扱った(解釈) |
| AAPI-P-15 / BAPI-P-15 | 再実行の専用 EP と `Origin` 検査は、ゲート2の回答で採用が選ばれなかったため不採用として扱った(解釈)。**未対応のリスク(BAPI-U-8)を受け入れるか、軽い緩和を足すか** |
| BAPI-P-20 | 時刻を ISO 8601(UTC)で返すこと(0001 の「既存設計でそのまま使うもの」をユーザーが確認したか。承認済みの案(既承認文書の引用)に区分を下げた。旧 BAPI-K-6) |
| AAPI-P-41 | `rerun_blocked_reason` に `source_missing` を足す(`source_deleting` に寄せず専用の値にする案。画面仕様に理由の文言がない)。`rerunnable=null` に設定の読み取りの失敗を加える |
| AAPI-P-42 | **一覧の EP(EP-01・09・11)の `unavailable` を行単位にする**(PR #10 のレビュー指摘。行の `null` が「取得失敗」と「値がない」を区別できないため。各行に `unavailable`、最上位は行に属さない項目だけ。ゲート3で承認済みの AAPI-P-16・25・27・30 の修正) |
| AAPI-P-25・P-27 | 読めない保存値は `null`(DTO の型が `null` を許す)。実行中でロックなし・別ジョブのロックは確認読みの後 `stalled=true`(C の案 AAA-P-25・P-18) |
| AAPI-P-39 | 取消(EP-07)で、`job_id` を理由とする Crawler の 400・404 `not_found` を 404 `job_not_found` に写すこと |
| AAPI-P-40 | 更新間隔 30 秒・外部リンクを、確定から「承認済みの案(画面仕様のゲート B・C の引用)」に直したこと(旧 AAPI-K-9) |
| AAPI-P-35 | `lock_held` の 409(ゲート1の承認。旧 AAPI-K-6 から区分を「承認済みの案」に訂正) |
| AAPI-P-36 | AF-19 は表示のみ(ゲート1。作業プラン 2章。機能設計 AF-P-3 はユーザー未確認の前提) |
| AAPI-U-9〜12 | 未決(実行中でロックなしの扱い、読めない設定項目の画面の扱い、opensearch-py の例外の対応と `relocating` の `node` の形、`job_id` のエンコードの実機の挙動) |
| AAPI-P-24(関連 AAPI-U-12) | `job_id` の符号化は `.` を `%2E` に置換する案。**代案: `.`・`..` だけの `job_id` を B 2.12 の検証で拒否する**(AAPI-P-24 の変更になる。ユーザーが選ぶ。採るのは符号化の案) |

### 11.10 C への引き継ぎ

B は結果と参照だけを書いた。C(`admin-api-architecture-v0.1.md`)で定義が要る事項:

1. **導出ロジックの定義**: `lock_state` の 7 値の判定順序、`stalled`・`cancellable`・`latest_for_source`・`rerunnable`・`rerun_blocked_reason`・`cancel_after_finish_notice`、`registration.phase`、`last_crawl`・`last_completed_at`・`delete_job`(`loreley-jobs` の集計の形)、`existence`、`ttl_days`・`ratio_threshold_percent` の変換(十進数)。`just_acquired` の猶予(60 秒。Crawler の仮値と同期。AAPI-U-6)。
2. **データアクセス**: 各 EP が読むインデックス・項目(3〜8章の「出所」)の OpenSearch クエリ(`loreley-sources` の全件取得、`loreley-jobs` の最新ジョブの集計と `mget`(ロック文書)、検索インデックスの `source_id` ごとの件数、X1 の件数(`msearch`)と ID の一括取得、`deletion_result-{job_id}` の取得、`cluster.health`・`cat.*` の `h=`・`bytes=b`)、`track_total_hits`、取得の窓(10,000)、索引名の環境変数(エイリアス `loreley-documents`)。読み取り専用の保証(書き込みメソッドを持たない)。
3. **環境変数の個別一覧と既定**: 本書で名前が決まったもの(`LORELEY_API_CRAWLER_URL`・`INDEXER_URL`・`CRON_TIMEZONE`・`DASHBOARDS_URL`・`DASHBOARDS_HEALTH_URL`・`EMBEDDING_HEALTH_URL`・`LLM_HEALTH_URL`・`WEB_DIST_DIR`・`HEALTH_PROBE_TIMEOUT_SECONDS`・`OPENAPI_ENABLED`。いずれも `LORELEY_API_` 付き)と、タイムアウト・上限の名前。
4. **仮値**: Crawler 接続 3 秒・応答 60 秒、OpenSearch 10 秒・再試行 2 回(A 5.6)、確認 3 秒、ページの窓 10,000、O1 のインデックス上限 1,000、X1 の一括検索 100、`just_acquired` の猶予 60 秒、`ttl`・本文の上限 1 MiB。
5. **Crawler クライアント**: urllib3 の設定(再試行なし・リダイレクトに従わない・タイムアウト)、例外から 503 `crawler_unreachable`・504 `crawler_response_lost` への分類、`message`・`details` の取り込みと、`config_invalid` の分解の実装(2.5)、スレッドプールの枯渇対策(BAPI-U-6)。
6. **死活の確認**: `/healthz` と opensearch-py の例外の分類(`abnormal` / `undetermined`。AAPI-P-33・U-11)、並行確認の実装、`web` の確認、任意コンポーネントの `not_configured` の判定。
7. **部分失敗**: 失敗の理由コードの付け方(例外の種類との対応)、`malformed` の判定規則(AAPI-P-34)、`warnings` の通し方。
8. **R1 で追加された事項**: (a) **`job_id`・`source_id` の符号化**(`quote(safe="")` の後に `.` を `%2E`。スタブが `%2E%2E` を受けることを確認)と、特殊文字を含む `job_id` の Crawler の挙動(AAPI-U-12)。(b) **`lock_state` の排他的な定義**(`orphan` と `just_acquired` は取得から 60 秒で分かれ、ジョブの `status` が読めなければ `unknown`。2.9)と、**ロック文書 → ジョブ記録の順に読む**ことで `stalled` の偽陽性を避ける。(c) **死活のプローブはリダイレクトに従わず、確認先の URL は環境変数だけで決める**(リクエストから受け取らない。3xx は `unexpected_status`。SSRF の予防)。(d) 応答の `ratio_threshold_percent` の十進数の厳密な変換(AAPI-P-38)。(e) `unavailable` は、単一の応答では最上位でキーは項目の正式なパス、一覧の EP(EP-01・09・11)では各行の `unavailable` でキーは行の相対パス(最上位は行に属さない項目だけ。2.2。AAPI-P-42)。
9. **テスト観点**: Crawler・OpenSearch の偽物(`tests/fakes/`)での写像表(9章)・障害別の挙動(10.2)・部分失敗・ページングの窓の確認。
