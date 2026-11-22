# 0020 C からの A・B 修正依頼の反映

日付: 2026-11-22
担当: document-writer(B 担当。メインが記録)

## 変更ファイル

A(`api-base-design-v0.1.md`)・B(`admin-api-v0.1.md`)のみ。C・E・F・agent_tasks は無変更。EP 番号・パス・承認済みの code 名・項目名は不変(例外: `rerun_blocked_reason` の値追加)。C の案(AAA-P-8・18・19・24・25・30・33)は A・B から「C の案」として参照するだけで、A・B の区分は案(ゲート3)のまま。

## 修正内容

**B**
- 2.2・2.11・EP-10: Crawler・Indexer が書いた値(ジョブ記録・削除記録・ロック文書)が読めないときは項目を `null` にし、`unavailable` には載せない。`malformed` は EP-02 の設定項目だけ。`null` を許す型: `JobBrief` の `status`・`job_type`・`trigger`・`queued_at`(`status=null` なら `stalled=false`・`cancellable=false`)、EP-10 の `registration` の件数、`registration.phase`(`partial` が真偽値でないとき `null`)。`job_id`・`source_id` は `null` 不可
- 2.9: 「ロック文書→ジョブ記録の順」に、EP-02・409 の `lock_state` はその順で読み、一覧(EP-01・09)と EP-10 は確認読み(ロックの不一致を見たとき)で満たす旨を補足。`stalled` はロックが別のジョブのものである `running` も確認読みの後 `true`
- 2.9・EP-10: データソース設定がないときの `rerun_blocked_reason` に**専用値 `source_missing`** を追加(`source_deleting` に寄せると削除済みのソースを「削除中」と誤表示するため。jobs-v0.1.md 2.3 に削除中・削除済みの理由文言は載っていない)。`rerunnable=null` の条件に「データソース設定の読み取りの失敗」を追加。新規 **AAPI-P-41(案。ゲート3)**
- 2.2・EP-02: 理由コードは `timeout` 優先。`ttl_days` は `ttl_seconds` が読めないとき `null`、`unavailable` のキーは `ttl_seconds` のみ

**A**
- 4章: 「秘密情報はない」を、OpenSearch の接続情報(`OPENSEARCH_USERNAME`・`PASSWORD`・`VERIFY_CERTS`・`CA_CERTS_PATH`。Crawler・Indexer と同じ)のみ任意で持つに。パスワードはログ・エラー本文に出さない。共通設定に認証・TLS、索引名 4 つ(`SEARCH_INDEX_NAME` を含む)、`ADMITTING_LOCK_GRACE_SECONDS` を追加(個別の一覧・既定・検証は C 7.2 が正本)
- 5.6: OpenSearch の再試行は、接続エラー(接続タイムアウト含む)・429・5xx は再試行、読み取りタイムアウトは再試行しない
- 2.1・BAPI-U-6: 「同期関数は anyio のスレッドプール」を `async def` + 区分別の上限に更新(C 8.1。上限値 16・4・8 は仮値で実測が未決)
- 8章: compose で `ADMITTING_LOCK_GRACE_SECONDS` を Crawler の `LORELEY_CRAWLER_ADMITTING_LOCK_GRACE_SECONDS` と同じ変数から渡す、索引名 4 つ、OpenSearch の認証・TLS を Crawler・Indexer と同じ変数から渡す

## ID

新規 AAPI-P-41(案。ゲート3)。変更(区分は案のまま): AAPI-P-25、AAPI-P-27、BAPI-P-6、BAPI-P-12(区分に「再試行条件の明確化は案(ゲート3)」を併記)、BAPI-U-6。B 11.9 に AAPI-P-41、P-25・P-27 の追記を追加

## 他文書への影響(追従が必要)

- **C**: 5.3 の評価順 8 を `source_missing`(設定がない)と `source_deleting`(`status=deleting`)に分ける。順 7 は B の `rerunnable=null` の条件として載ったので「B にない補足」の注記は不要。12章の「A・B に追記が要る点」は解消扱い
- **E・F**: `JobBrief` の `status`・`job_type`・`trigger`・`queued_at`、`registration` の件数・`partial`・`phase` が `null` になりうる(画面は「—」、`status=null` のジョブにタグ・操作を出さない)。`rerun_blocked_reason` の新値 `source_missing`(専用文言は画面仕様・E・F に足すかゲート3の確認後。未知の値は一般文言)。`rerunnable=null` の条件が増えた(画面は不可として扱う)

## 自己検算(writer)

2.3 の code 表と EP のエラー表の不一致 0(`crawler_*` 4 種は共通行)、EP 14 本、ID 参照の未定義・未参照 0、JSON 例 16 ブロックがパース可、表の列数に崩れなし、不採用項目は記録のみ残存、旧記述(「anyio のスレッドプールで動く」「秘密情報はない(認証」)の残存なし

## 次

- C の追従修正(担当 writer。D 執筆の後)、E・F の追従(担当 writer。R3 修正の後)、A・B の差分確認
