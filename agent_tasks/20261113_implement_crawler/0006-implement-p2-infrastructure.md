# 0006 P2: `infrastructure`(Repository・`indexer_client`)と fakes

日付: 2026-11-13 / 実施: code-implementer / 記録・再検証: メインエージェント
フェーズ開始時点の HEAD: `061dc7b196f67a689e0d834eb676ce356d6cdb34`(`apps/crawler/` は未コミット)

## 1. 検証結果(メインが再実行、`apps/crawler`)

```
$ uv run pytest -q          -> 794 passed in 8.01s(P1 の 335 件 + 459 件)
$ uv run ruff check         -> All checks passed!
$ uv run ruff format --check -> 82 files already formatted
$ uv lock --check           -> Resolved 39 packages
```

スキップしたテストなし。実装担当は全体を3回続けて実行し成功。`apps/indexer`・docs・infra への変更なし(git status で新規は `apps/crawler/` のみ)。実機確認用の Docker コンテナ・プロセスの残りなし。

## 2. Indexer 契約表(api v0.10 と `apps/indexer` の実スキーマ・エラー・テストの突き合わせ)

結論: **仕様と実装のスキーマ・エラー・ステータスに食い違いはない。Indexer の変更は不要。**

### エンドポイント

| 操作 | メソッド・パス | リクエスト | 成功 | 備考 |
| --- | --- | --- | --- | --- |
| 開始通知 | `POST /crawls/start` | `crawl_id`・`source_id`・`crawl_started_at`・`ttl`(整数)・`ratio_threshold`(有限の数)・`min_delete_count`(整数)・`force_delete`・`rewrite_mode`(真偽値) | 200 `{"crawl_id","status":"running"}` | 同一値の再送は成功、内容が違えば409 |
| `last-seen` | `POST /sources/{source_id}/last-seen` | `crawl_id`・`crawl_started_at`・`lock{owner,job_id}`・`document_ids[]`(小文字64桁16進。件数上限は Indexer の `max_last_seen_ids`) | 200 `{"results":[{"document_id","result"}]}` | `result`: updated / unchanged / not_found / update_conflict / lock_not_owned |
| バッチ登録 | `POST /sources/{source_id}/documents:batch` | `crawl_id`・`crawl_started_at`・`lock`・`documents[]`(`external_id`・`title`・`mime_type`・`raw_content`(標準base64)・`content_hash`・`source_updated_at`・`size`、任意で `url`・`path`) | 200 `{"results":[...]}` | `status: ok`(`change`: created / updated / unchanged、`extract_failed`)または `status: failed`(`failure_type`: document_rejected / oversize / lock_not_owned / write_conflict / update_conflict) |
| 終了通知 | `POST /crawls/{crawl_id}/finish` | `source_id`・`outcome`・`finished_at`。`enumeration_completed` のときは `enumerated_count`・`skipped_document_ids`・`oversize_document_ids` も必須。`skipped_count` は任意(値は使われない) | 202(ボディなし) | 202 は受理の確認ではない。未知の `crawl_id` にも202 |
| Status | `GET /crawls/{crawl_id}` | なし | 200(値のない項目はキーごと省略) | `running` 以外が終端 |
| ソース削除1 | `POST /sources/{source_id}/deletions:discard` | `lock`(必須。所有は確認されない)、任意 `reason`(`source_deleted` のみ) | 200 `{"discarded_crawl_ids":[...]}` | 試行上限超過は503 |
| ソース削除2 | `DELETE /sources/{source_id}/documents` | JSON ボディ `{"lock":{...}}`(必須) | 200 `{"deleted_count":n}` | 所有確認あり。再実行上限超過は503 |
| ソース削除3 | `DELETE /sources/{source_id}/deletion-records` | JSON ボディ `{"lock":{...}}`(必須) | 200 `{"deleted": bool}` | 所有確認あり。記録がなければ false(成功) |

### エラー(共通の形 `{"error":{"code","message","retryable"}}`)

| HTTP | code | retryable | `indexer_client` の結果 |
| --- | --- | --- | --- |
| 400 | `invalid_request` | false | `IndexerRejected` |
| 404 | `crawl_not_found`(Status)/`not_found` | false | `IndexerRejected` |
| 405 | `method_not_allowed` | false | `IndexerRejected` |
| その他 | `http_error` | false | `IndexerRejected` |
| 409 | `crawl_already_finished`・`stale_crawl_started_at`・`crawl_start_conflict`(開始通知)/`crawl_not_started`・`crawl_source_mismatch`・`crawl_started_at_mismatch`・`crawl_already_closed`・`crawl_finished`(`last-seen`・バッチ登録)/`finish_content_mismatch`・`finish_source_mismatch`(終了通知)/`lock_not_owned`(ソース削除2・3、リクエスト全体) | false | `IndexerRejected` |
| 500 | `internal_error` | false | `IndexerUnavailable("http_500")` |
| 503 | `unavailable`(OpenSearch 全体異常、書き込み競合の上限超過、discard・削除2の上限超過、起動前) | true | `IndexerUnavailable("http_503")` |
| 接続エラー・タイムアウト | なし | なし | `IndexerUnavailable("connection_error"/"timeout")` |

- 文書単位の `lock_not_owned`(`last-seen`・バッチ登録)は HTTP 200 の本文で返る(リクエスト全体の409とは別)。
- 契約外の応答(2xx なのに JSON でない、必須項目なし、未知の列挙値)は `IndexerRejected(status, "malformed_response")`(設計書にない区分。安全側=リトライしない)。

### 突き合わせで気づいた点(食い違いではなく前提)

1. `source_id`・`crawl_id` に `/` を含めると実 Indexer は404を返す(`%2F` を Starlette がルーティング前にデコード)。`..` もクライアント側の URL 正規化で404。space・`日本`・`%`・`?`・`#`・`+`・`:`・`;` はパーセントエンコードで実機を通った。api 3.3 は ID の `/` を禁止していないが、Crawler の案 CAPI-P-15(英数字始まり、英数字と `.`・`_`・`-` のみ)なら起きない。**文字種規則が変わると破綻するため、規則の設計書改版時に留意が要る。**
2. HTTP 502・504 は設計書の定義どおり `IndexerRejected`(その他)。プロキシのない MVP 構成では来ない。
3. 既知: `apps/indexer/README.md` が api v0.9 を参照している(Indexer 側の課題。変更していない)。

## 3. 変更・作成したファイル(すべて `apps/crawler/`)

- 変更(P1 の成果物の最小限の調整): `pyproject.toml`・`uv.lock`(`urllib3>=2.2,<3` を直接依存に明記)、`common/errors.py`(`IndexerUnavailableError` を削除、`StoreUnexpectedResponseError(error_type)` を追加)、`tests/common/test_errors.py`・`test_log_setup.py`(urllib3 のロガーが `urllib3.*` 配下であることの確認を追加。`RESTRICTED_LOGGER_NAMES` は変更不要)、`tests/architecture/dependency_rules.py`・`test_dependency_rules.py`(R2 の外部ライブラリ表: `urllib3` は `indexer_client` のみ、`httpx`・`httpx2`・`requests`・`aiohttp` はどのモジュールも不可)、`tests/architecture/test_write_rules.py`(R7 の Repository 内部の検査を追加)
- 新規 `src/loreley_crawler/infrastructure/opensearch/`: `repository.py`(`Repository` ABC 7操作)、`results.py`、`queries.py`、`settings.py`、`classification.py`、`client_calls.py`、`scan.py`(PIT+`search_after`)、`bulk_delete.py`、`query_builder.py`、`opensearch_repository.py`、`connection.py`
- 新規 `src/loreley_crawler/infrastructure/indexer_client/`: `client.py`(`IndexerClient` ABC 8操作)、`http_client.py`(urllib3)、`config.py`、`models.py`、`payloads.py`、`parsing.py`、`results.py`
- 新規 `tests/fakes/`: `behavior.py`、`in_memory_repository.py`、`fake_opensearch.py`(transport 差し替えエミュレータ)、`fake_indexer_client.py`、`local_http_server.py`
- 新規 `tests/infrastructure/{opensearch,indexer_client}/`

## 4. 判断・設計上の理由(決めてよい事項で決めた内容)

1. **HTTP クライアントは urllib3(CM-U-2)**: `PoolManager.request` が `DELETE` でも `body` をそのまま送る/リクエストごとに `urllib3.Timeout(connect, read)` を渡せる(API ごとのタイムアウト)/プールがスレッドセーフ/opensearch-py の既存依存で新しい依存が増えない。`retries=False`・`redirect=False`(リトライは確認点つきで呼び出し側)。`NewConnectionError` は `ConnectTimeoutError` の子なのでタイムアウトより先に判定。**#17 の結果**: ローカル `http.server`(ポート0)に対し、ソース削除2・3の `DELETE` がボディ `{"lock":{...}}`・`Content-Type`・`Content-Length` を落とさず届くことを確認。実 Indexer でも正しい lock は成功、誤った lock は409 `lock_not_owned`。
2. **結果の返し方**: Indexer 側は成功型・`IndexerUnavailable(reason)`・`IndexerRejected(status_code, error_code)`(例外にしない)。Store 側の「全体異常」は `StoreUnavailableError`(例外)で伝播(設計書の「結果区分として返す」と表現が違うが5区分の意味は同じ)。想定外の4xx は `StoreUnexpectedResponseError(error_type)`(設計書にない区分。Crawler の不具合として最後の手段 `failed(internal_error)` に落とす想定。**P4・P5 に要周知**)。Indexer のエラー本文の `message` は結果に載せない(R11)。
3. **版条件つき書き込みで記録がない場合**: 実 OpenSearch 3.9.0 では409(`Conflict`)を実機確認。fake は `NotFound`。契約テストは両方許容。呼び出し側はどちらも「条件が外れた」として読み直す。
4. トランスポートの自動再送は無効(`max_retries=0`、`retry_on_timeout=False`)。リトライは呼び出し側の1か所に集約。ハートビート専用クライアントは別の短いタイムアウト。
5. `list_records` は検索の前に refresh する(Indexer の前例。設計書は走査・条件指定削除の契約にだけ refresh を明記していたので補った)。
6. **全件走査**: `scan(record_filter, *, sort)` を `with` で使う。`__enter__` で refresh と PIT 作成、`__exit__` で PIT を閉じる(最後まで読んだ・失敗・途中でやめた・呼び出し側が例外のいずれでも。閉じる処理は重複しても1回。閉じるのに失敗しても結果は変えずクラス名だけ WARNING)。タイブレークは呼び出し側が `sort` に一意な組を渡す方式(第一候補 `document_id`。`_shard_doc` は不使用)。**条件指定削除は置かない**(ソース削除の順3は全件走査+バルク削除)。
7. **R7 の追加検査**: Repository 内の `index` は `op_type` か版(`if_seq_no`+`if_primary_term`)必須、`delete` は版必須。`bulk` は `bulk_delete.py` のみ。`update` 系・`delete_by_query`・`reindex`・索引/マッピング変更は禁止。`loreley-` 始まりの文字列を持たない。**未検査のまま残る**: `loreley-sources` を書くのは `sources` だけ・`loreley-jobs` を書くのは `jobs` だけという割り当て、読んだ版を条件にすること、`main.py` が作る Repository が3つだけであること(P4・P5・P8 で追加)。
8. **仮値(設計書の空欄。設定可能)**: 通常の読み書きタイムアウト30秒、ハートビート専用10秒、全件走査の検索1回60秒、Indexer 接続10秒。設計書に既定値がある数値(走査ページ1,000、PIT 60秒、バルク1,000、API ごと 30/60/300/600/4,200/60秒)はそのまま。
9. 終了通知では `skipped_count`(任意)を送らない(Indexer は値を使わない)。`failed`・`cancelled` の通知は渡された項目だけ送る。
10. **厳密な JSON**: `ttl`・`min_delete_count`・`size`・`enumerated_count` は `type(v) is int`(`bool`・小数は `TypeError`)、`ratio_threshold` は有限数のみ(`NaN`・`inf` は `ValueError`)、`force_delete`・`rewrite_mode` は `bool` のみで `rewrite_mode` は常に送る。日時は `format_instant`。孤立サロゲートを含む `title` は `\udc80` のエスケープで送る(実 Indexer で文書単位 `document_rejected` を確認)。ID・`content_hash` の検証はしない。
11. **fake**: `InMemoryRepository`(走査は開始時点のスナップショット。バルク削除の部分失敗を `fail_bulk_delete_of` で注入。割り込みフック・応答差し替えは `behavior`)、`FakeIndexerClient`(全呼び出しを順に記録、`registration_failures` と `behavior.inject` で差し替え)。契約テストは2実装に同じテストを流す(opensearch 側は実クライアントの transport をメモリ上のエミュレータに差し替え。refresh するまで検索に見えない・PIT・`search_after`・`_bulk`・版条件・失敗注入を再現)。変異確認: refresh を外す・PIT を閉じない・`search_after` を外す、のいずれもテストが失敗した。

## 5. 実機での使い捨て確認(リポジトリに残していない。Integration Test の代替ではない)

実装担当が、手元の OpenSearch 3.9.0(Docker。確認後に停止・削除)と実 Indexer(確認後に停止)に対し、使い捨てスクリプトで確認した。

- Store 層: `create` の2回目は `AlreadyExists`。版条件の置き換え・削除は古い版が `Conflict`、正しい版は成功。skip 10,500件+oversize 10,500件(同じ `document_id` が種類をまたいで共存)+別ソース50件で `record_type` ごとの走査が11ページ・重複なしで全件。走査しながらバルク削除(存在しない ID を混ぜた)が全件成功し、他ソースの50件と oversize は残った。終了後・途中放棄・消費側の例外のいずれでも開いている PIT は0件。存在しない索引への読み・削除は `index_not_found_exception`→`StoreUnavailableError`。
- Indexer クライアント: 開始通知(再送成功、内容違い409)、`last-seen`、バッチ登録(文書単位の結果、誤 lock は文書単位 `lock_not_owned`)、終了通知、Status、ソース削除1〜3(DELETE ボディ、誤 lock は409)が契約どおりに解釈された。

注意: これらの実機確認は P2 の範囲を超えた使い捨ての確認で、完了条件上の検証ではない(Integration Test はスコープ外)。結果は参考情報。

## 6. 設計書との食い違い・不明点

- 設計書の食い違いはない(上記の補った点・追加した区分を除く)。
- **infra 側の運用上の注意(別タスク向け)**: OpenSearch は存在しない索引への書き込み(`create`・版条件つき `index`)で既定では索引を自動作成する(マッピングなしの動的マッピング)。読み・削除は404。`opensearch-init` を必ず先に実行する前提(compose の依存で担保)で、`action.auto_create_index` を無効にするかは infra 側の判断事項。
- `StoreUnexpectedResponseError` と `IndexerRejected("malformed_response")` は設計書にない区分。レビューで方針を確認する。

## 7. 未対応事項・持ち越し

- 実 OpenSearch・実 Indexer の統合テスト(スコープ外)。実機での `create` と版条件の原子性・並行下の挙動、opensearch-py のスレッド安全性(CM-U-1)は未検証。CM-U-3(実 Indexer での `document_id` 照合)は `SHA-256(source_id\0external_id)` の一致をバッチ応答で見ただけ。
- R7 の残り(§4-7)。
- `scan` は `sort` の一意性を呼び出し側に委ねる(P4 の `jobs/records` は `document_id` で並べ、`record_type` ごとに走査する)。

## 8. 次のアクション

1. P1+P2 を code-reviewer(バルク削除・PIT 管理を重点)と test-reviewer で並列レビュー(比較基準 HEAD `061dc7b196f67a689e0d834eb676ce356d6cdb34`)
2. 指摘を対応・再レビューし、作業記録を残す
3. P3(`connectors`・`documents`)
