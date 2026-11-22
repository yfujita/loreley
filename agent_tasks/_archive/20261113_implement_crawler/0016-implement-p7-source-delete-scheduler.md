# 0016 P7: `source_delete` と `scheduler`

日付: 2026-11-14 / 実施: code-implementer / 記録・再検証: メインエージェント
フェーズ開始時点の HEAD: `061dc7b196f67a689e0d834eb676ce356d6cdb34`(`apps/crawler/` は未コミット)。P7 のレビューは P8 完了後に P7+P8 をまとめて実施(0002 §6。**データ削除を含むため code-reviewer 省略不可**)。

## 1. 検証結果(メインが再実行、`apps/crawler`)

```
$ uv run pytest -q           -> 2769 passed, 3 skipped in 15.55s(P6 後 2583 → +186。skip は macOS 固有の3件)
$ uv run ruff check          -> All checks passed!
$ uv run ruff format --check -> 243 files already formatted
$ uv lock --check            -> Resolved 39 packages
```

`git status` は `apps/crawler/` のみ。実装担当は3回連続成功を確認。変異確認(scratchpad のコピー、35件)は33件検出、1件は同値(`finish` は終端後は no-op)、1件はパターンが消滅(冗長な status 確認を除去したため)。初回の生存2件(ID が同じで変異が見えない停止要求テスト、待ちが自分で停止を報告するテストの欠落)はテストを修正・追加して検出。スレッドのテストは `Event`・手動の待ち・固定時計で書き、すべての join・待ちにタイムアウト。スリープなし。

## 2. 実装内容(`apps/crawler/src/loreley_crawler/`)

**source_delete**(新規 `source_delete/{__init__,executor,indexer_calls,failure,dependencies}.py`)
- `SourceDeleteExecutor`(`JobExecutor`)。順0〜6: 0=`start_running`→`SourceStore.mark_deleting`、1・2・4=Indexer の discard・delete_documents・delete_deletion_records(各 `LockInfo(owner, job_id)`)、3=`DocumentRecords.delete_all_of_source`、5=`SourceStore.delete`、6=`finish(SUCCEEDED)`(ロック文書の削除は Job Runner)
- 確認点(リトライの各試行の前も含む): Indexer 呼び出し(順1・2・4)は `Check.OWNERSHIP | Check.MAINTENANCE`(**取り消しは意図的に除外**)、Store の手順(0・3・5)は `Check.OWNERSHIP` のみ(architecture 8.1・module 4.6)
- Indexer エラー: `IndexerUnavailable` はリトライ(3回、1秒・2秒のバックオフ)→尽きたら `failed(indexer_unavailable)`。409 `lock_not_owned` は `record_lock_not_owned` して `failed(lock_lost)`(discard を含む3呼び出しで一律)。その他の `IndexerRejected`(400・他の409・404・405・`malformed_response`)はリトライせず `failed(indexer_rejected)`
- 理由コード: `OwnershipLost`→`lock_lost`、`MaintenanceDetected`→`maintenance`、`StoreUnavailableError`・`StoreWriteFailedError`→`store_unavailable`、`StoreUnexpectedResponseError`→`internal_error`、その他の例外→`internal_error`(型名のみ)。`failure_detail` は常に固定文(Indexer のメッセージや要求値は載せない)
- `finish` の False(すでに終端)は再判定せず、何も書かず warning。順5は `status=deleting` のときだけ削除(`SourceNotDeleting` なら `failed(internal_error)` で設定は残す)。冪等: 順0で設定がない(`SourceNotFound`)場合も順1〜5を実行して成功、すでに `deleting` の設定は書き換えない。`JobNotStartable` は Runner のために伝播

**scheduler**(新規 `scheduler/{__init__,scheduler,settings,waiter}.py`)
- `Scheduler`: daemon スレッド(`start`・`request_stop`・`join`・`run_until_stopped`)、`run_once` は1周をスレッドなしで実行(判定テストが決定的)。待ちは差し替え可能(`TickWaiter`・`EventTickWaiter`。`scheduler/waiter.py`。`scheduler` は `jobs.locks` を import できないので形を再宣言)。停止は `threading.Event` と待ちの両方で効き、1周の途中の停止は次のソースの前で止まる
- 1周: `SourceReader.list_scheduled_active_sources()`(retrier 経由)→形式不正のソース(`MalformedSourceRecord`)は項目名だけの警告でスキップ→間隔が None ならスキップ→起点は直近のクロールジョブの `queued_at`(なければ設定の `updated_at`)→`(now - base).total_seconds() >= interval` なら期限(経過秒の比較なので巨大な間隔でも datetime がオーバーフローせず、時計が戻れば期限前)→`JobAdmission.accept_scheduled_crawl(source_id)`(`force_delete`・`rewrite_mode` の引数なし)
- 拒否(`LockAlreadyHeld`・`MaintenanceEnabled`・`SourceDeleting`・`SourceConfigNotFound`)は固定の理由でログに出すだけ。待ち行列を作らず、停止中の起動も取り返さない(ロックが空いた後は1回だけ起動)
- 一覧の失敗・想定外の例外は例外の型名だけをログに出して次の周期を待つ。ソース単位の失敗は他のソースを止めない。直近ジョブの `queued_at` が読めない場合は `StoreUnexpectedResponseError("malformed_job_record")` でそのソースはスキップ(クロールを起動しない)

**jobs の追加**: `jobs/records/latest_crawl.py`(`find_latest_crawl_queued_at(repository, source_id=)`: `record_type=job`・`job_type=crawl`・`source_id` で絞り、`queued_at`→`job_id` の降順で limit 1、状態・trigger は問わない)、`JobHistory.find_latest_crawl_queued_at(source_id=, retrier=) -> datetime | None`(`jobs/records_facade.py`)、`jobs/records/__init__.py` の公開。`tests/architecture` は変更不要(許可表に `source_delete`→`jobs`・`sources`・`indexer_client`、`scheduler`→`jobs`・`sources` がある)

**tests**: `tests/source_delete/`(117件: 順0〜6の単一タイムライン、各段階でのロック・ハートビート保持、順3が他ソースの記録・ロック・ジョブ・メンテナンスフラグを消さない(接頭辞が似た source_id を含む)、各停止点での喪失・メンテナンスと「破壊的イベント」の厳密な一覧(後続の削除が呼ばれない)、期限切れリース・ハートビート tick で気づく奪取・形式不正フラグ=立っている・フラグ読み取り失敗・リトライ待ち中にフラグが立つ、3呼び出し×全 Indexer エラー、順0・3・5の Store エラー(`StoreUnexpectedResponseError` はリトライしない・バルク削除の部分失敗)、順5が `deleting` 以外を拒否、`finish` の False、取り消しは確認点でない、取り消しに負けて開始できないジョブ、Runner 結合の e2e(実際の受付・Runner・ハートビート・ロック: ロックは最後に削除、途中停止後の再実行で完了、`deleting` のソースにクロールを起動できない、喪失時はロックを残す)、センチネル)、`tests/scheduler/`(50件: 期限の境界、起点のルール、拒否を見送り待ち行列を作らない、停止中の起動を取り返さない、エラーの隔離、形式不正のソース・`queued_at`、`force_delete`・`rewrite_mode` は常に false、手動の待ちでのスレッドのテスト、停止、センチネル)、`tests/jobs/records/test_latest_crawl.py`(9件)、`tests/jobs/test_records_facade.py`(+4件)

## 3. 決めてよい事項で決めた内容・仮値

- **Scheduler の判定周期**: `SchedulerSettings.check_interval_seconds = 30.0`(architecture 11章が空欄。正の値を検証。開始は最大でこの値だけ遅れうる)
- **メンテナンスフラグの範囲**: 順1・2・4の前だけ確認(architecture 8.1・module 4.6)。順3・5の前には確認しない。**順2の最中にフラグが立つと順3(Crawler 側の記録削除)は実行され、順4が止まる**。より厳しくしていない(設計書の記述どおり)。この場合を固定するテストは置いていない → **レビューで要否を判断する(§5)**
- discard(順1)の409 `lock_not_owned` も `lock_lost` として一律に扱う(discard は所有確認されない仕様だが、応答が来た場合の安全側の扱い)
- リトライは `context.retrier(checks)`(P5 の `Retrier` のポリシー3回)
- 小さな重複: `scheduler/waiter.py` が `TickWaiter` の形を再宣言(R の依存ルールで `jobs.locks` を import できない)、`source_delete/executor.py` の `_job_owner` は `crawl` のコピー(`crawl/start.py` にも独自の実装)

## 4. 設計書との食い違い・不明点

1. architecture 8.1 は、順2の最中にメンテナンスフラグが立った場合に順3を止めるかを言っていない(§3)
2. 既に設定が存在しない状態でソース削除を開始した場合に、Indexer の順1〜4を実行するかを明示する行が見つからなかった。8.3 の「削除済みなら成功扱い」に従い実行して成功する
3. P4 からの既知の限界: 同じソース・同じ種別で `document_id` を持たない記録が2件以上あると順3の並べ替えが一意にならず `non_unique_sort`→`failed(internal_error)`(`purge.py` に記載)

## 5. P8 への申し送り

- `source_delete`: `SourceDeleteExecutor(SourceDeleteDependencies(source_store=SourceStore(sources_repo, clock, retrier), indexer_client=HttpIndexerClient, document_records=DocumentRecords(jobs_repo, clock)))` を `executors[JobType.SOURCE_DELETE]` に渡す(`crawl` は `CrawlExecutor`)。設定は不要
- `scheduler`: `Scheduler(settings=SchedulerSettings(check_interval_seconds=...), source_reader, job_history=JobHistory(jobs_repo), admission=<API と同じ JobAdmission>, clock, retrier=<確認点なしの Retrier(policy)>, waiter=None)`。`scheduler.start()` は起動時の回復・Job Runner の開始の後、HTTP の前。停止は `request_stop()`→`join(timeout)`。環境変数1つ(`check_interval_seconds`、既定30.0)。Scheduler の retrier は `time.sleep` で待ち、停止では中断されない(最悪約3秒のバックオフ)ので join にタイムアウトを付ける

## 6. 設計書の改版依頼リスト(提案。P7 分)

1. architecture 11章: Scheduler の判定周期30秒(仮値)
2. architecture 8.1: メンテナンスフラグは順1・2・4の各試行の前に読み、所有は順0・3・5の前に確認する(順3・5はフラグの対象外であることを明確に)
3. architecture 8.1・8.3: 開始時に設定がなくても冪等な順1〜4は実行されジョブは成功する。順5は `status=deleting` でない設定を拒否し `failed(internal_error)`
4. architecture 7.8: 順1(discard)の409 `lock_not_owned` も順2・4と同様に扱う
5. architecture 4.3: Scheduler の起点は直近の `crawl` ジョブの `queued_at`(状態・trigger を問わない)。読めない値ならそのソースはスキップ。経過時間で比較する(起点に加算しない)
6. module 4.2・4.4: `JobHistory.find_latest_crawl_queued_at` をファサードに追加、`scheduler` は独自の待ち(`TickWaiter`)を持つ

## 7. 未対応事項

- P7 として残した作業はなし
- 持ち越し(実機): 0014 §7 のとおり

## 8. 次のアクション

P8(`api`・`config.py` 完成・`main.py`)を `code-implementer` に依頼する(8a: `api`+`/healthz`+`config.py`、8b: `main.py`・組み立て・起動停止順)。完了後に P7+P8 を code-reviewer・test-reviewer で並列レビュー(**重点: メンテナンスフラグの範囲(§3)、起動順・停止順、ログ流出、データ削除の安全側**)。
