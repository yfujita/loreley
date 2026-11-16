# 0010 P4: `sources` と `jobs/records`・`jobs/locks`(ハートビート)

日付: 2026-11-14 / 実施: code-implementer / 記録・再検証: メインエージェント
フェーズ開始時点の HEAD: `061dc7b196f67a689e0d834eb676ce356d6cdb34`(`apps/crawler/` は未コミット)。レビューは P5 完了後に P4+P5 をまとめて実施(0002 §6)。

## 1. 検証結果(メインが再実行、`apps/crawler`)

```
$ uv run pytest -q           -> 1891 passed, 3 skipped in 9.87s(P3 後 1488 → +403。3件は macOS 固有で P3 と同じ)
$ uv run ruff check          -> All checks passed!
$ uv run ruff format --check -> 158 files already formatted
$ uv lock --check            -> Resolved 39 packages
```

`git status` は `apps/crawler/` と P0 の docs のみ。`apps/indexer`・infra への変更なし。実装担当は3回連続成功を確認。変異確認(scratchpad のコピー、58件)は最終的に全件検出か同値・無効のみ。

## 2. 実装内容(`apps/crawler/src/loreley_crawler/`)

- `common/`(変更): `timestamps.parse_instant`(`format_instant` の書式を読み戻す。TZ なし・読めない値は `ValueError`)、`errors.is_store_unavailable`(リトライ判定用。`StoreUnavailableError` のみ真)、`retry.Retrier`(`RetryPolicy`・確認点・sleep・乱数元を束ねた呼び出し口)
- `sources/`: `validation.py`(値の規則の検証。`source_id` の文字種は `SOURCE_ID_PATTERN`・`SOURCE_ID_MAX_LENGTH` の1か所に局所化)、`records.py`、`results.py`、`source_store.py`(`SourceReader`=読み取り・一覧、`SourceStore`=登録・更新・`mark_deleting`・`delete`)
- `jobs/records/`: `job_ids.py`、`job_record.py`、`job_store.py`、`document_records.py`(スキップ記録・原本サイズ超過記録)、`maintenance_flag.py`(fail-closed)、`purge.py`(記録の整理・一括削除)、`previous_crawl.py`
- `jobs/locks/`: `lock_document.py`、`lock_store.py`(`LockStore`: `acquire`・`read`・`set_lease`・`delete_unchanged`・`release_own`)、`heartbeat.py`(`Heartbeat`・`HeartbeatSettings`・`TickWaiter`・`EventTickWaiter`)
- tests: `tests/sources/`、`tests/jobs/records/`、`tests/jobs/locks/`、`tests/common/` の追加分、`tests/fakes/lost_response_repository.py`(書き込みは成功するが応答が失われる fake。`behavior.inject` は操作を実行しないためこの再現に使えない)、`tests/architecture/test_write_rules.py`(R7 の残りを追加)
- `tests/architecture/dependency_rules.py` の許可表・期待集合テストは変更なし(必要な辺は P1 で用意済み)

## 3. 0007 §4 の申し送りへの対応

1. `sort` は `document_id` で終える: `purge.py` の `SCAN_SORT = (SortKey("document_id"),)`、`record_type` ごと・1ソースごとに1回。`SpyRepository` で「`record_type` ごとに1回」「`sort` の最後が `document_id`」をテスト。
2. `pit_expired` は走査全体をやり直す: `with scan` ブロック全体を `Retrier` で包み、ID を集め切ってから削除(PIT の保持時間と削除のリトライの待ちを無関係にする)。`SCAN_PAGE` への `pit_expired` 注入で、走査が1回やり直され全件削除され `open_scan_count==0` をテスト。
3. リトライ後の `AlreadyExists`・`Conflict` は読み直す: `acquire`(読み直して自分の `owner`・`job_id` なら `Acquired`)、`set_lease`(自分のロックなら読んだ版でやり直す)、`release_own`(ロックがなければ完了)、ジョブ記録の `create`・`update`(読み直した内容が自分の書いた内容と完全一致なら成功。後から誰かが書けば `JobSuperseded`)、スキップ記録・サイズ超過記録(`last_job_id` が同じジョブなら記録済みとして `consecutive_skips` を二重に増やさない)、設定の登録・更新(内容比較で自然に成功扱い)。`LostResponseRepository` で検証。
4. 記録なしの版条件つき書き込みは `Conflict`: すべて「読み直して判定し直す」。
5. `StoreUnexpectedResponseError` はリトライしない。理由・種別名は固定文字列で本文を含まない。形式不正の記録は `MalformedSourceRecord` に項目名だけを載せる。`connector_config` は `repr=False`。
6. R7 の残り: Repository の書き込み呼び出しは `sources/`・`jobs/records/`・`jobs/locks/` だけ/版条件つきの `seq_no`・`primary_term` を定数にしない(欠落も不可)/`SourceStore` を import してよいのは `sources/`・`api/`・`source_delete/`・`main.py` だけ(`jobs`・`scheduler`・`crawl` は `SourceReader`)/`Repository.__abstractmethods__` が期待集合と一致(版条件なしの書き込み操作を足せない)/実ツリーに違反ファイルを足すと失敗する検査と検出器の自己テスト。「`sources` が `loreley-jobs` を書く」ことは、Repository がインスタンスごとの注入であることと import の許可表の組み合わせで防ぐ。**`main.py` が作る Repository が3つだけであることの検査は P8**。

## 4. 決めてよい事項で決めた内容

- **仮値**(引数で差し替え可能。値は P8 の `config.py` が詰める): `HeartbeatSettings` リース300秒・更新間隔100秒・失敗時の再試行間隔10秒・停止の待ち上限30秒。関係式 `0 < 再試行 < 更新間隔 < リース` を `__post_init__` で検証。停止の待ちは「更新1回+読み直し1回」ぶん。ハートビート専用クライアントのタイムアウト(10秒)との関係の検査は P8 の `config.py` に残る(停止の待ち上限 ≥ そのタイムアウトの約2倍)。競合を読み直してやり直す回数: 設定の `SourceStore` は5(`max_conflict_attempts`)、ロックとスキップ記録は3。0件列挙警告のために読む件数: `find_previous_completed_crawl` の `max_jobs` 引数(呼び出し側 `crawl` が architecture 11章の10を渡す)
- **リトライの置き場**(module 4.4 と整合): `SourceStore.register`・`update` は HTTP ハンドラから直接呼ばれるため内部で操作全体をリトライ。`SourceReader`・`mark_deleting`・`delete`・`jobs/records` の読み書き・`LockStore` は1回の試行で `StoreUnavailableError` をそのまま送出し、リトライは呼び出し側(`JobContext`・受付)が `Retrier` で行う。例外は `purge.py`(仕様どおり内部でリトライ)
- **`purge`**: 部分失敗は失敗 ID だけを再送し、尽きたら `StoreWriteFailedError`(`StoreUnavailableError` の子、reason `bulk_delete_incomplete`)。条件指定削除は置かず全件走査+バルク削除(順3も同じ)。整理は `should_delete(document_id)` を呼び出し側(`crawl`)が渡す。`document_id` が読めない記録は整理では消さず、ソース削除では消す
- **形式不正の扱い(fail-closed)**: ロック文書の読めない `lease_expires_at` は期限切れ、読めない `acquired_at` は十分に古いとみなす(壊れたロックも管理者の解放・回復で消せる。Indexer の「形式不正は所有していない」と同じ側)。`owner`・`job_id` が文字列でなければ `""`。設定: `mark_deleting` は形式不正の記録でも `deleting` にできる。`update` は `status` が読めない記録、または保つべき `connector_type` が読めない記録に `StoreUnexpectedResponseError("malformed_source_record")` を送出し書かない
- **設定まわり**: `mark_deleting` は `status` だけ変える(`updated_at` は変えない。定期起動の起点に使うため)。`delete` は `status=deleting` のときだけ削除(それ以外は `SourceNotDeleting`)。内容比較(crawler-api 4.4.2)で `connector_config` は JSON の型の違い(`1` と `1.0`、`1` と `true`)を同じとみなさず、迷うときは書き込む側に倒す。`ratio_threshold` は数値比較。`schedule_interval_seconds` の省略・項目欠落は null(手動のみ)
- **ジョブ ID**: `job-{%Y%m%dT%H%M%SZ}-{16進8桁}`(crawler-api 4.1 の例に合わせた)。乱数元は差し替え可能
- **スキップ記録の更新**: 設計書(3.3.3/6.4)の `attempts`・`last_skipped_at`・`last_job_id` と `consecutive_skips`+1 に加え、`stage`・`reason` も最新に更新
- **ロック作成時の `heartbeat_at`** は null
- **`Heartbeat`**: 1ジョブ1インスタンス・1スレッド(daemon)。待ちは `TickWaiter` で差し替え。`tick()` を公開し更新の規則をスレッドなしで検証。`stop(timeout_seconds=None)`(引数はテスト用)。`lock` プロパティが解放の削除に使う最新の版

## 5. P5 以降への申し送り

- `JobRecordStore.update(record, changes)` → `JobUpdated(record)` / `JobSuperseded(current | None)`。`JobSuperseded` なら `current.status` が `failed`(`lock_released`)などに変わっていないか確認(喪失判断は `JobContext`)、そうでなければ `current` の版でやり直す。読み直した内容が自分の書いた内容と一致するときは `JobUpdated`。リトライは `Retrier`(`is_store_unavailable`)
- `JobRecordStore.fetch` は `record_type=job` 以外を None に。受付用の `create` は `JobIdCollision` を返しうる(ID を作り直す)。一覧(`queued_at` 順・`owner`・状態別・直近のクロールジョブ)は P5・P7 で `list_records` を使って追加する
- `LockStore`: ハートビート用には専用 Repository の `LockStore`。実行開始のリース設定は `set_lease(lock, lease_seconds=…, require_active_lease=False)`。`LockNotOwned` の理由 `lock_missing`・`lock_taken_over`・`lease_expired`。`delete_unchanged(lock)`(版条件つき1回の削除)は受付の巻き戻し・`queued` の取り消し・管理者の解放・回復が使う(`LockChanged` なら読み直して判断し直す)。`release_own(lock)` は通常の解放。`list_locks`(回復の手順2・4用)は P5 で追加
- `Heartbeat`: `start(lock, lease_expires_at)` → `is_owned()`・`record_loss(reason)`(`JobContext` が `lock_not_owned` を受けたとき)→ `stop()`。`stop()` が False(停止の待ち超過)または `lost_reason` が非 None のとき **Job Runner はロック文書を削除しない**(2.2・5.7)。解放は `release_own(heartbeat.lock)`。喪失の理由 `lock_missing`・`lock_taken_over`・`lease_expired`・`unexpected_error`・`stop_timeout`・`lock_not_owned`(外から記録)
- メンテナンスフラグ: `is_maintenance_enabled(repository)`(jobs 用 Repository)
- 整理・一括削除: `purge_document_records(repository, retrier, source_id=, record_type=, should_delete=)`(`crawl` の整理、architecture 6.4)、`delete_document_records_of_source(...)`(`source_delete` の順3)。`StoreWriteFailedError`・`StoreUnavailableError` は `failed(store_unavailable)`、`StoreUnexpectedResponseError` は `failed(internal_error)`。`Retrier` に `JobContext` の確認点を渡す
- 設定: `jobs`・`scheduler`・`crawl` は `SourceReader`、`api`・`source_delete` は `SourceStore`。`crawl` の1回読み取りの結果は `SourceRecord | MalformedSourceRecord | None`(`MalformedSourceRecord` は `invalid_fields`(項目名のみ)と `status`。`crawl` は `config_invalid` の固定文を `deleting`・未登録・不正で出し分ける)。`scheduler` は `list_scheduled_active_sources()`。`api` は `validate_source_values` の `ValueProblem(field, reason)` の `reason` をそのまま `details.errors` に使い、`validate_connector_config` の `ConnectorError` を 400 `config_invalid` / 500 に対応づける。`RegistrationConflict.existing_status` が None の場合がある(形式不正な既存記録)
- config.py(P8): 停止の待ち上限 ≥ ハートビート専用クライアントのタイムアウトの約2倍の検査を整合性検査に足す

## 6. 設計書との食い違い・不明点

食い違いはない。注意点: `connectors/__init__.py` は docstring のみで `ConnectorRegistry` は `loreley_crawler.connectors.registry` から import する(`sources` が使う)。設計書は `jobs` 直下(受付など)が `records`/`locks` を呼ぶとする。P4 のプリミティブは単発の試行で、競合時の判断は呼び出し側という作りにした(module 4.4・CM-P-12 と整合)。

## 7. 設計書の改版依頼リスト(提案。P4 分)

1. **module 4.3・4.4**: `sources` を `SourceReader`(読み取り)と `SourceStore`(書き込み)に分け、`jobs`・`scheduler`・`crawl` は `SourceReader` だけ。R7 に「Repository の書き込み呼び出しは `sources/`・`jobs/records/`・`jobs/locks/` だけ」「版条件つき書き込みの版は読んだ値」「`SourceStore` の import 元は `api`・`source_delete`・`main` だけ」の機械検査を追記
2. **architecture 5.3・3.3**: 応答喪失後のリトライの扱い(`AlreadyExists`・`Conflict` は読み直して自分の書き込みなら成功)を、ロック取得・ジョブ記録の作成/更新・スキップ記録(`last_job_id` による二重計上の防止)について明記。ジョブ記録の更新は「読み直した内容が自分の書いた内容と一致するとき成功」
3. **architecture 9章**: Store 層の理由名を追記(`bulk_delete_incomplete`、`source_register_contention`、`source_update_contention`、`source_delete_contention`、`lock_acquire_contention`、`lease_contention`、`lock_release_contention`、`document_record_write_contention`、`source_list_truncated`)。種別名(`StoreUnexpectedResponseError`)は `malformed_source_record`、`malformed_job_record`
4. **architecture 3.3.3**: スキップ記録の更新項目に `stage`・`reason` を足す
5. **architecture 5.1・3.2**: ロック文書の読めない `lease_expires_at` は期限切れ、読めない `acquired_at` は古いとみなす/作成時の `heartbeat_at` は null/ソース削除の順0は `updated_at` を変えない/順5は `status=deleting` の設定だけ削除
6. **crawler-api 4.4**: 既存の設定が形式不正のとき、登録は409(`details.status` が null になりうる)、更新は500 `internal_error`(`status` が読めない場合)。`connector_config` の内容比較は JSON の型を区別する
7. **architecture 11章**: ハートビートの停止の待ち30秒、再試行10秒の仮値(CM-U-6)を採用値として追記

## 8. 持ち越し

- 実 OpenSearch でしか確認できないもの: `create` と `if_seq_no` の並行時の原子性(fake の同時 `create` までを検証)、opensearch-py のスレッド安全性とハートビート専用クライアントの要否(CM-U-1)、10,001件以上の走査・バルク削除の部分失敗・PIT(#37)、`allow_partial_*` のサーバー側の受理(0007 §5)
- `main.py` が作る Repository が3つだけであることの検査は P8

## 9. 次のアクション

P5(`jobs` 直下: 受付・取り消し・解放・回復・Job Runner・`JobContext`)を `code-implementer` に依頼する。完了後に P4+P5 を code-reviewer・test-reviewer で並列レビュー(並行性・ロック・削除を重点。比較基準 HEAD `061dc7b196f67a689e0d834eb676ce356d6cdb34`、対象は P4・P5 で追加・変更したファイル)。
