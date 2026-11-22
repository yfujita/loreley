# 0013 P6a: `crawl`(実行開始〜チャンク処理)と `jobs` 入口のファサード

日付: 2026-11-14 / 実施: code-implementer / 記録・再検証: メインエージェント
フェーズ開始時点の HEAD: `061dc7b196f67a689e0d834eb676ce356d6cdb34`(`apps/crawler/` は未コミット)。P6 は 6a・6b に分け、**レビューは 6b 完了後に P6 全体をまとめて**実施(0002 §6)。

## 1. 検証結果(メインが再実行、`apps/crawler`)

```
$ uv run pytest -q           -> 2414 passed, 3 skipped in 34.93s(P5 後 2217 → +197。skip は macOS 固有の3件)
$ uv run ruff check          -> All checks passed!
$ uv run ruff format --check -> 213 files already formatted
$ uv lock --check            -> Resolved 39 packages
```

`git status` は `apps/crawler/` のみ。実装担当の変異確認(scratchpad のコピー、約60件)は初回の生存4件のうち3件にテストを追加して検出、残る1件(文書ごとの確認点)は取得の retrier の確認点と重複する冗長コードだったので削除。最終は全件検出(意図した no-op 変異を除く)。スレッドは使わず(ハートビートは `ManualWaiter` で待ちに入ったまま)、スリープなし。

## 2. 実装内容

- `jobs/records_facade.py`(新規): `DocumentRecords(repository, clock)`(`record_skip`・`record_oversize`・`purge`・`delete_all_of_source`)、`JobHistory(repository)`(`find_previous_completed_crawl`)。`Repository` を公開属性に持たない(テストあり)。どのメソッドも `Retrier` で `StoreUnavailableError` をリトライしてから送出し、`StoreUnexpectedResponseError` は伝播。`jobs/__init__.py` が `SkipStage`・`OversizeDetector`・`DocumentRecordType`・`PreviousCrawl`・`StoreWriteFailedError`・`loggable_id`・`LOSS_LOCK_NOT_OWNED` も公開
- `crawl/`: `settings.py`(`CrawlSettings`)、`dependencies.py`(`CrawlDependencies`)、`failure.py`(`CrawlFailure`)、`snapshot.py`(`SettingsSnapshot`)、`tally.py`(`RegistrationTally`)、`skip_counter.py`(`ConsecutiveSkipCounter`)、`constants.py`、`outcomes.py`(スキップ・サイズ超過の記録と計数)、`indexer_calls.py`(`IndexerCaller`)、`start.py`(`prepare_crawl`・`PreparedCrawl`)、`fetch_stage.py`、`batch_registration.py`、`run.py`(`CrawlRun`)、`executor.py`(`CrawlExecutor`)
- **`CrawlExecutor.__call__`(`JobExecutor`)は 6b まで未完成**: 列挙の完了・登録結果の確定・整理までを終えたら `NotImplementedError("...P6b")` を送出し、Job Runner の最後の手段が `failed(internal_error)` にする(終了通知は送っていないので Indexer は削除しない。安全側)。docstring に明記。**`main`(P8)へ接続する前に 6b を完成させる**。テスト用に 6a の範囲だけを実行する入口 `CrawlExecutor.run_until_finish_notice(record, context) -> ReadyToFinish | FailureRecorded` を公開
- `tests/architecture` の許可表は変更不要(P1 の許可表の辺だけで足りた。R7 も新ファイルで通る)
- tests: `tests/jobs/test_records_facade.py`、`tests/crawl/`(`support.py`・`conftest.py`・`test_start.py`・`test_start_notice.py`・`test_chunks.py`・`test_retries.py`・`test_consecutive_skips.py`・`test_enumeration_failures.py`・`test_purge.py`・`test_tally.py`・`test_entry.py`・`test_logging.py`)

## 3. テスト観点との対応(architecture 12章のうち 6a の範囲)

#1(`document_id` 不一致で `failed(document_id_mismatch)`、再送なし)、#2・#9(呼び出し順 開始通知→チャンクごとに `last-seen`(取得より前)→取得→登録、取得と登録の交互進行、バッチの閉じ条件、`last-seen` の分割)、#3・#4(`crawl_id`=`job_id`、`crawl_started_at` は開始・`last-seen`・バッチで同一文字列、開始通知の再送は同一値、型 strict(`rewrite_mode` を省略しない)、`LockInfo` は Runner のロックと一致)、#7・#8・#22(`enumerated_count` は重複と識別子エラーを除きスキップ・サイズ超過を含む。登録されなかった文書は `skipped_document_ids`/`oversize_document_ids` に載り `enumerated_count` = 登録+スキップ+サイズ超過)、#10(連続スキップは取得段階と登録段階で別カウンタ、散在は打ち切らない、連続20件で `failed(skip_limit_exceeded)`、`oversize` と識別子エラーは計数もリセットもしない)、#11(最大3回・バックオフ1秒・2秒、400・409 は再送なし、500・503・接続エラー・タイムアウトは再送し直らなければ `failed(indexer_unavailable)`、`document_rejected` は失敗した文書だけ再送、`write_conflict`・`update_conflict` は `failed(conflict_unresolved)` でスキップしない)、#20(件数集計、最初の `ok` の保持、`partial` の遷移)、#21(`external_id_collision`→`failed`、`EnumerationTooLargeError`→`failed(enumeration_too_large)`、列挙失敗→`failed(enumeration_failed)`)、#24(整理は完了したクロールだけ。失敗したクロール・列挙失敗では整理しない)、#35(設定の1回読み取り、`settings_snapshot` は6項目のみ・`settings_source_updated_at` は別項目、`config_invalid` は4通り+未登録 `connector_type`)、#33 の一部(整理のバルク削除の部分失敗が尽きると `StoreWriteFailedError` が伝播)、完了条件8(センチネル(本文・`connector_config` の参照名・秘密)で全ログとジョブ記録全件を8経路で検査)。

## 4. 決めてよい事項で決めた内容

1. **仮値(`CrawlSettings`、すべて architecture 11章の値。設定可能。`config.py`(P8)が詰める)**: `chunk_size=500`、`last_seen_max_ids=500`、`batch_max_documents=20`、`batch_max_raw_bytes=32MiB`、`consecutive_skip_limit=20`、`invalid_id_example_limit=20`(名前は `config.py` の `CrawlerSizeLimits` に合わせた)
2. **6a で `failed` にするのは `CrawlFailure`(crawl が理由を決める失敗)だけ**: `config_invalid`・`enumeration_failed`・`indexer_*`・`external_id_collision`・`enumeration_too_large`・`skip_limit_exceeded`・`conflict_unresolved`・`document_id_mismatch`・契約違反の `internal_error`。`CancellationRequested`・`OwnershipLost`・`MaintenanceDetected`・Store 層例外・想定外の例外は 6b の担当でそのまま伝播(列挙・Connector は finally で閉じる)。失敗時の `registration` は常に付ける(集計が1件もなければ0件・`partial=true`。CA-K-15)
3. **確認点**: 設定の読み取りは `OWNERSHIP | CANCELLATION`(メンテナンスは手順7で明示的に確認=手順6→7の順を守る)、手順7の確認と**すべての Indexer 要請(各試行の前)は `Check.ALL`**(R8)、取得・Store 層の書き込み・列挙は `OWNERSHIP | CANCELLATION`。**メンテナンスフラグは文書の区切りごとには読まない**(Store の読み取りが文書数ぶん発生するため。Indexer への要請の前にだけ読む。architecture 4.6 の「文書の区切り」からの意図的な絞り込み。目的は Indexer 書き込みの停止)
4. **`connector_config`** は `prepare_crawl` の局所変数だけ。`CrawlRun` の状態・ジョブ記録・ログ・例外に出さない
5. **リトライの数え方**: リクエスト単位(3回)と文書単位(3回)を別々に数える。文書単位の再送の待ちも同じバックオフ(`JobContext.wait`)。`create` のリトライは `transient` のみ(6.2)。取得は `transient`・`unknown` をリトライし `permanent` はしない
6. **連続スキップの計数順(設計書にない決定)**: 再送を終えてから、バッチの文書の順に反映する。理由: 再送の回の順で数えると `[拒否, ok, 拒否, ok, …]` のような散在が、拒否の確定が遅れるせいで「連続」になってしまう(テストあり)
7. **スキップ記録の `reason`** は「分類名+短い固定文」の固定表(`outcomes.py`)。Connector・Indexer の説明文は載せない。`failure_detail` には段階と分類名だけ
8. **整理の判定は設計書の字義どおり**: 今回列挙され、スキップにもサイズ超過にもならなかった記録、または今回列挙されなかった記録を消す。**観察**: 前回スキップで今回サイズ超過になった文書の古いスキップ記録は残る(テストで固定。設計の見直し候補)
9. **取得が契約外の分類を返した場合**(例: `source_unreachable`)は `failed(internal_error)`(スキップにしない。削除に関わるため安全側)
10. `document_id` 不一致の `failure_detail` には両方の ID(SHA-256 hex)を載せた
11. `CrawlRun` に `start_notice_sent` を足し、`FailureRecorded.run`(実行開始に失敗したときは None)を持たせた(6b の「終了通知 `failed` は開始通知の後に限る」の判定用)

## 5. 設計書との食い違い・不明点

大きな食い違いはない。設計書に明記がなく実装で決めたもの(改版依頼に載せる): 連続スキップの計数順(§4-6)、文書の区切りでのメンテナンス確認の絞り込み(§4-3)、失敗時の `registration`(0件・`partial=true`)を設定エラーの `failed` にも付けたこと、`config_invalid`(型違い・欠落)の `failure_detail` に項目名だけ(固定の語彙。値は載せない)を載せたこと(architecture 4.8 は「固定文で区別」)、整理の字義どおりの判定で残る古いスキップ記録(§4-8)、文書単位の再送回数をリクエスト単位とは別枠で数えること、契約外の取得エラー分類は `failed(internal_error)`。

## 6. 6b への申し送り

**公開した型(`loreley_crawler.crawl`)**: `CrawlRun`(状態: `tally`・`enumeration`(`enumerated_count`・`has_enumerated`)・`invalid_id_examples`・`snapshot`・`source_id`・`start_notice_sent`・`registration_record()`。段階: `send_start_notice`・`process_chunks`・`finalize_registration`・`purge_document_records`・`close`)、`RegistrationTally`(`skipped_document_ids`/`oversize_document_ids` は重複なし・記録順のタプル、`invalid_id_count`・`partial`・`finalize()`・`to_record(enumerated_count=)`)、`CrawlFailure(reason, detail)`、`StageResult = ReadyToFinish(run) | FailureRecorded(failure, recorded, run)`、`CrawlExecutor`・`CrawlDependencies`・`CrawlSettings`、`PreparedCrawl`・`SettingsSnapshot`・`ConsecutiveSkipCounter`

**未実装の入口(6b)**:
- `CrawlExecutor.__call__` の後半: `run_until_finish_notice` の戻りが `ReadyToFinish` のときの処理(終了通知の組み立て・固定(`finish_notice` への保存、`send_started_at`)・送信、ポーリングと確認結果の区分、最終状態 `succeeded`/`partially_succeeded`(識別子エラー・スキップがあれば partially))
- `FailureRecorded` の経路への `failed` 通知(`start_notice_sent` と `send_started_at` 前の条件)
- `CancellationRequested`・`OwnershipLost`・`MaintenanceDetected`・`StoreUnavailableError`・`StoreWriteFailedError`・`StoreUnexpectedResponseError`・想定外の例外の最終対応(理由コード: `lock_lost`・`maintenance`・`store_unavailable`・`internal_error`。現在 `run_until_finish_notice` が伝播する例外はすべて 6b で捕捉)。`OwnershipLost("lock_not_owned")` は `record_lock_not_owned` 済みで伝播
- 0件列挙警告: `CrawlRun.finalize_registration` の docstring に挿入位置を明記(`partial=false` の確定の前)。`JobHistory` は `CrawlDependencies` に未接続で 6b で足す。`find_previous_completed_crawl(source_id=, excluding_job_id=, max_jobs=10, retrier=)`
- `warnings`: 識別子エラーの例(`run.invalid_id_examples`、件数 `tally.invalid_id_count`)を保持済み。ID 一覧の警告閾値・ポーリング関連の設定値は `CrawlSettings` に 6b が追加
- `JobContext.finish` が False を返したときは実行結果を再判定しない。`finish` の `changes` は JSON 型(`RegistrationTally.to_record` は int・bool のみ)
- 取り消し時: `run.close()`(列挙・Connector)は `run_until_finish_notice` の finally で済むので、6b の `cancelled` 通知で別途列挙を閉じる必要はない

## 7. P7・P8 への申し送り

**ファサード(`from loreley_crawler.jobs import ...`)**:
- `DocumentRecords(repository, clock)`: `record_skip(job_id=, source_id=, document_id=, external_id=, stage: SkipStage, reason=, attempts=, retrier=)`、`record_oversize(job_id=, source_id=, document_id=, external_id=, detected_by: OversizeDetector, size=, retrier=)`、`purge(source_id=, record_type: DocumentRecordType, should_delete=, retrier=) -> int`、**`delete_all_of_source(source_id=, retrier=) -> int`**(P7 `source_delete` の順3。部分失敗が尽きると `StoreWriteFailedError`)
- `JobHistory(repository)`: `find_previous_completed_crawl(source_id=, excluding_job_id=, max_jobs=, retrier=)`。`scheduler` 向けの「直近のクロールジョブの `queued_at`」は未実装(P7)

**P8(組み立て)**: `DocumentRecords(jobs_repository, clock)` → `CrawlDependencies(source_reader, connector_registry, indexer_client, document_records, settings=CrawlSettings, documents_settings=DocumentsSettings)` → `CrawlExecutor(deps)` を `JobRunner` の `executors[JobType.CRAWL]` に渡す(6b 完成後)。整合性検査(`config.py`)との対応: `CrawlerSizeLimits.max_raw_bytes` ← `DocumentsSettings.max_raw_bytes`、`batch_max_documents`・`batch_max_raw_bytes`・`last_seen_max_ids` ← `CrawlSettings`、`finish_id_list_warning_threshold` は 6b の `CrawlSettings` に追加される

## 8. 未対応事項・既知の限界

- 6b 全般(§6)
- `CrawlRun` のコンストラクタが例外を送出すると Connector が閉じられない(現状はコンストラクタに例外要因がなく不要と判断)
- 実機でしか確認できないもの: `document_id` 照合(CM-U-3)、`create` と `if_seq_no` の並行時の原子性、10,001件以上の整理(#37)、スレッド・GIL 下のハートビート

## 9. 設計書の改版依頼リスト(提案。P6a 分)

1. architecture 6.3: 連続スキップの計数は、再送を終えてからバッチの文書の順に反映する(散在を連続にしないため)
2. architecture 4.6・7.9: メンテナンスフラグは Indexer への要請の前に確認し、文書の区切りごとには Store を読まない。区切りで確認するのは所有・取り消しのメモリ上の確認だけ
3. architecture 3.3.3: スキップ記録の `reason` の固定文の表(分類名+固定文)
4. architecture 4.8: 取得が契約外の分類を返したときは `failed(internal_error)`。設定エラーの `failure_detail` に項目名を載せる
5. architecture 3.3.1・7.7: 失敗した(設定エラーを含む)ジョブの `registration` は0件・`partial=true` で付く
6. architecture 6.4: 整理の判定で、前回スキップ・今回サイズ超過の文書のスキップ記録が残る点(現行の字義どおり)。残す・消すを決める(設計の見直し候補)
7. module 4.4・4.5: `jobs` 入口のファサード(`DocumentRecords`・`JobHistory`)と `crawl` の公開型(`CrawlExecutor`・`CrawlRun` など)
8. architecture 6.1: 最大試行回数は、リクエスト単位と文書単位を別々に数える。文書単位の再送の待ちも同じバックオフ

## 10. 次のアクション

6b(終了通知・ポーリング・異常系の最終対応・0件警告・`warnings`)を `code-implementer` に依頼する(§6 と 0012 §6 の `JobContext` 申し送りを含める)。6b 完了後に P6 全体の code + test レビュー。
