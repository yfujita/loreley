# 0011 P5: `jobs` 直下(受付・取り消し・ロック解放・起動時回復・Job Runner・`JobContext`)

日付: 2026-11-14 / 実施: code-implementer / 記録・再検証: メインエージェント
フェーズ開始時点の HEAD: `061dc7b196f67a689e0d834eb676ce356d6cdb34`(`apps/crawler/` は未コミット)。P4+P5 のレビュー(code + test)を次に実施。

## 1. 検証結果(メインが再実行、`apps/crawler`)

```
$ uv run pytest -q           -> 2161 passed, 3 skipped in 19.22s(P4 後 1891 → +270。skip は macOS 固有の3件)
$ uv run ruff check          -> All checks passed!
$ uv run ruff format --check -> 183 files already formatted
$ uv lock --check            -> Resolved 39 packages
```

実装担当の報告: `tests/jobs tests/architecture` の 748 件を5回連続成功(スレッドのテストの不安定さなし)。変異確認(scratchpad のコピー、89件)は、初回85件で生存5件(同値1・検出力不足4)→ テスト追加で全件検出。`git status` は `apps/crawler/` のみ。

## 2. 実装内容(`apps/crawler/src/loreley_crawler/jobs/`)

- 新規: `settings.py`(`JobsSettings`)、`cancel_requests.py`(`CancelRequestRegistry`)、`wakeup.py`(`RunnerWakeup`)、`interruptions.py`(中断の例外)、`job_updates.py`(版条件つき更新と読み直し)、`lock_cleanup.py`、`existing_job.py`、`log_text.py`、`admission.py`(受付)、`cancellation.py`(取り消し)、`lock_release.py`(管理者のロック解放)、`recovery.py`(起動時の回復)、`context.py`(`JobContext`・`Check`)、`runner.py`(`JobRunner`・`JobExecutor`)
- 変更: `jobs/__init__.py`(入口の公開)、`records/job_record.py`(`JobStatus.is_terminal`、`FailureReason`=architecture 4.8 の16コード)、`records/job_store.py`(`find_oldest_queued(owner)`・`list_running(owner)`)、`records/__init__.py`、`locks/lock_store.py`(`list_locks()`。上限到達で `lock_list_truncated`)
- tests: `tests/jobs/` に `support.py`、`test_admission.py`・`test_cancellation.py`・`test_lock_release.py`・`test_recovery.py`・`test_context.py`・`test_runner.py`・`test_job_updates.py`・`test_lock_cleanup.py`・`test_settings.py`・`test_cancel_requests.py`。変更: `tests/jobs/records/test_job_store.py`、`tests/jobs/locks/test_lock_store.py`、`tests/architecture/test_dependency_rules.py`(`jobs` 直下の実ファイルが `crawl`・`source_delete` を import しない検査を追加。既存の自己テストの違反例を1行変更: `common`→`jobs` の例は `jobs/__init__` が `common` を import するようになり循環と判定されるため `import loreley_crawler.config` に替えた)

## 3. テスト観点との対応(architecture 12章)

#13(受付の同時実行を fake の割り込みフックと8スレッドで検証。1つだけ成功)、#14・#25・#26・#27(取り消しの各時点と競合、取り消し要求の伝達・終端後の消去・重ねた要求・再起動で消えること)、#15(起動時の回復)、#18(メンテナンスフラグ。形式不正は「立っている」)、#28・#29(ロック解放と Job Runner の競合の両先後、解放しないロック)、#32(喪失記録時・停止待ち超過時にロック文書を削除しない)、#33(Store 層の書き込みがリトライを尽くすと `failed(store_unavailable)`)、`StoreUnexpectedResponseError`→`failed(internal_error)`、R3・R6(Job Runner が `crawl`・`source_delete` を import しない)。

## 4. 決めてよい事項で決めた内容

- **仮値**: `runner_scan_interval_seconds` 5秒(architecture 11章の空欄)、`admitting_lock_grace_seconds` 60秒(11章)、`owner` は256バイト以内・制御文字(Cc)なし・空でない(CA-P-3。`JobsSettings` で検査)、競合を読み直して判定し直す回数3(`job_updates`・`lock_cleanup`・`lock_release`)
- **構成**: 設定は `JobsSettings`(`owner`・`HeartbeatSettings`・走査間隔・受付途中の猶予)。Job Runner は `owner` が自分の `queued` だけを `queued_at`、`job_id` の順で取り出す。ハートビートは `heartbeat_factory`(`main` が専用クライアントの `LockStore` で作る)で注入。`Retrier` は確認点なしの基本形を渡し、`JobContext` が `dataclasses.replace` で確認点つきを作る。`JobContext.check(Check.OWNERSHIP | CANCELLATION | MAINTENANCE)` は `enum.Flag`(順序: 所有、取り消し、メンテナンス)。`JobContext` の記録の書き込み(最終状態を含む)は確認点を通さない(取り消し・喪失の後にも最終状態を残すため)。`JobContext.wait` は既定で所有と取り消しだけ確認(メンテナンスは Store を読むため既定では確認しない)。実行対象が `queued`→`running` で取り消しに負けると `context.start_running()` が `JobNotStartable` を送出し、Job Runner が捕捉して実行せず止めロックを解放
- 案どおりに局所化した箇所: `FailureReason`(`records/job_record.py`)、`SETTINGS_SNAPSHOT_KEYS`(`context.py`、6項目)

### 設計書に明記がなく、安全側で決めたこと(改版依頼に載せる)

1. **ロック解放(管理者)の順序**: ロック文書の版条件つき削除が先、ジョブの `failed(lock_released)` が後。リースが再開していれば版が進んで削除に失敗し、判定し直して `lock_in_use`(生きているジョブを `failed` にしない)。ロック削除後にジョブ更新が競合したら、`running` のまま読み直した版で `failed` にする
2. **`queued`→`failed` を2か所で許した**(architecture 4.2 の遷移表にない): (a) リース設定時にロックがない・他のジョブのものなら、実行せず `failed(lock_lost)`、(b) 実行対象が `running` にする前に例外で終わった場合の最後の手段の `failed` を `queued` から書く
3. **最終状態を記録できていないときは、ロック文書を削除しない**(「実行対象の終わり方を問わず1回」の例外)。`running` のジョブのロックを消して新しい受付を通さないため。ハートビートは必ず止める。リース切れ後に管理者の解放が `failed(lock_released)` にする
4. **最後の手段の理由**: `StoreUnavailableError`→`store_unavailable`、それ以外(`StoreUnexpectedResponseError` を含む)→`internal_error`。実行対象が最終状態を記録せずに返った場合も同じ。ログには例外の種類だけ(R11)
5. **`job_id` の衝突**: 受付は巻き戻したうえで `StoreUnavailableError("job_id_collision")` を送出(api が503・再試行可能に)。ロックの `job_id` が衝突した ID のため、その場で作り直さない
6. **`running` への取り消し**: 要求を記録した後にジョブを読み直す。終端になっていれば要求を消し `JobAlreadyFinished` を返す(終端後に誰も消さない要求を残さないため)。結果として、202のつもりが409 `job_already_finished` になりうる
7. **受付の設定の判断**: クロールでは、設定が `status` を読めない形式不正でも受け付け、`crawl` の実行開始が `config_invalid` で `failed`(開始通知の前なので安全)。ソース削除は、存在すれば形式不正でも受け付ける
8. **`JobContext.finish`**: `failed` なら `failure_reason` 必須。`failure_detail` は保存前に表示用整形(512文字)。他者が状態を変えていたら上書きせず `False`、喪失(`job_record_superseded`)を記録してロックを削除させない。`update()` は `status`・`connector_config` を書けない。`record_settings` は6項目を厳密に検査し1度だけ書ける
9. **起動時の回復**: `running` のジョブを持つロックで、ジョブの `owner` が自分以外のものは触らず警告。判断できないものは削除しない
10. `RunnerWakeup.wait` は通知で戻ると `True`(テストで通知を検出するため)

## 5. 設計書との食い違い・不明点

重大な食い違いはない(上記 §4 の 2・3・5・6 は設計書に明記がなく実装で決めたため改版依頼に載せる)。

**構造上の注意(P6 が決める)**: R3 により `crawl`・`source_delete` は `infrastructure.opensearch` を import できない。一方 P4 の `purge_document_records`・`DocumentRecordStore`・`find_previous_completed_crawl`・`is_maintenance_enabled` は `Repository` を引数に取る。そのため `jobs` 入口に `Repository` を見せないファサードが要る(P5 では作っていない)。`scheduler` の「直近のクロールジョブの受付時刻」も、`jobs` 入口経由の関数が P7 で要る。

## 6. P6 以降への申し送り

**`crawl`・`source_delete`(実行対象)**
- 型は `JobExecutor = Callable[[JobRecord, JobContext], None]`。`main` が `{JobType.CRAWL: ..., JobType.SOURCE_DELETE: ...}` の両方を `JobRunner` に渡す(片方でも欠けると `ValueError`)
- `jobs` 入口(`from loreley_crawler.jobs import ...`)の公開物: 型・設定 `JobContext`、`Check`、`JobRecord`、`JobStatus`、`JobType`、`JobTrigger`、`FailureReason`、`SETTINGS_SNAPSHOT_KEYS`/例外 `JobInterrupted`、`CancellationRequested`、`OwnershipLost(reason)`、`MaintenanceDetected`、`JobNotStartable`
- `JobContext` の API: `start_running() -> str`(`started_at` の文字列を返す。`crawl_started_at` に使う。`JobNotStartable` は捕捉せず伝播)、`record_settings(snapshot 6項目, 設定の updated_at: datetime)`、`update(changes)`(他者が状態を変えていたら `OwnershipLost`)、`finish(status, failure_reason=, failure_detail=, changes=) -> bool`(`False` は上書きしなかった)、`check(Check...)`、`retrier(Check...)`(R8: 試行ごとに確認)、`wait(seconds, Check...)`、`record_lock_not_owned()`(Indexer の `lock_not_owned` を受けたとき)、`is_terminal`、`record`、`job_id`
- 理由コードの対応: `OwnershipLost`→`lock_lost`、`MaintenanceDetected`→`maintenance`、`StoreUnavailableError`・`StoreWriteFailedError`→`store_unavailable`、`StoreUnexpectedResponseError`→`internal_error`
- `source_delete` の順1・2・4の前は `Check.OWNERSHIP | Check.MAINTENANCE`(取り消しは対象外)。`crawl` の開始通知より前の確認は `Check.ALL`。ポーリングの待ちは既定(所有と取り消し)

**`api`**(`jobs` と `sources` だけを import する)
- 受付: `JobAdmission.accept_manual_crawl(source_id, force_delete=, rewrite_mode=)`、`accept_scheduled_crawl`、`accept_source_delete`。結果: `Accepted(job: AcceptedJob)`、拒否 `SourceConfigNotFound`(404)・`SourceDeleting`・`MaintenanceEnabled`・`LockAlreadyHeld(existing_job: ExistingJob)`(409の3種)
- 取り消し: `JobCancellation.cancel(job_id)`。結果: `Cancelled`(200)、`CancelRequested`(202)、`JobNotFound`(404)、`JobNotCancellable`(409)、`JobAlreadyFinished(status)`(409)
- ロック解放: `LockRelease.release(source_id)`。結果: `LockReleased(failed_job_id)`(200 `released=true`)、`NoLockToRelease`(200 `released=false`)、`LockInUse(existing_job)`(409)
- 例外: `StoreUnavailableError` は503、`StoreUnexpectedResponseError` は500。`job_id` の形式検査は `api` 側

**`scheduler`**: `accept_scheduled_crawl` を使う。拒否は見送るだけ。「直近のクロールジョブの受付時刻」は未実装で、`jobs` 入口の関数を P7 が追加

**`main`(P8)**: 共有物を1つずつ作る(`CancelRequestRegistry`、`RunnerWakeup`、`JobsSettings`)。`JobAdmission`・`JobCancellation`・`LockRelease`・`StartupRecovery`・`JobRunner` を組み立てる(受付・取り消し・解放・回復には確認点なしの `Retrier(policy)`、`read_maintenance_flag=partial(is_maintenance_enabled, jobs_repository)`、`heartbeat_factory=lambda: Heartbeat(heartbeat_lock_store, clock, settings.heartbeat)`)。起動順は整合性検査→OpenSearch 接続→`StartupRecovery.run()`→`JobRunner.start()`→HTTP。停止は `JobRunner.request_stop()`(ジョブの完了は待たない。CM-U-4)。P8 の `config.py` の整合性検査に「ハートビートの停止の待ち上限 ≥ 専用クライアントのタイムアウトの約2倍」(0010 §5)を足す。R7 の残り「`main` が作る Repository は3つだけ」の検査も P8

## 7. 未対応事項・既知の限界

- **先頭の形式不正ジョブ**: `queued` の先頭ジョブの記録が形式不正(`job_type`・`source_id` が読めない)だと、Job Runner がその例外をログに出して走査し続け、後続のジョブが実行されない(先頭ブロック)。記録は Crawler だけが書くため起きないはずの異常に対する安全側の挙動
- **解放の応答喪失**: ロック解放で、削除の応答が失われた場合に `released` の真偽が曖昧になりうる(孤児ロックのとき。`running` のジョブがあれば `failed` にする)
- **ロックのないままのジョブ**: ロックを削除した後でジョブ更新が Store の異常で失敗すると、ロックのない `running` のジョブが残り、次の再起動の回復(`crawler_restart`)まで残る
- **ロック一覧の上限**: `list_running`・`list_locks` は上限(10,000)に達したら例外(想定規模では起きない)
- **fake だけでは未検証**: 実 OpenSearch での `create`・`if_seq_no` の並行時の原子性、ハートビート専用クライアントの要否(CM-U-1)、実環境の `queued_at`(date 型)・`owner`・`status` のソート・絞り込み(infra のマッピング前提作業の範囲)、実機のスレッドと GIL の挙動

## 8. 設計書の改版依頼リスト(提案。P5 分)

1. architecture 4.2 の遷移表: `queued`→`failed` を追加(ロックを失った `queued`=`lock_lost`、`running` にする前に例外で終わった場合の最後の手段)
2. architecture 5.5・module 4.4/2.2: 最終状態を記録できなかった場合はロック文書を削除しない(「終わり方を問わず1回」の例外)
3. architecture 4.3: `job_id` の衝突は受付を巻き戻して再試行可能な異常(503)
4. architecture 5.4: ロック解放の順序はロック削除(版条件)が先、ジョブの `failed(lock_released)` が後。ロック削除後にジョブ更新が競合したら `running` のまま読み直した版で `failed`
5. architecture 4.7・crawler-api 4.2: `running` への取り消し要求は記録後にジョブを読み直し、終端なら要求を消して409 `job_already_finished` を返しうる
6. architecture 4.3: クロールの受付は設定の `status` が形式不正でも受け付け、`crawl` の実行開始が `config_invalid` にする
7. architecture 9章: Store 層の理由名 `job_update_contention`・`lock_cleanup_contention`・`lock_release_contention`・`job_id_collision`、種別名 `job_list_truncated`・`lock_list_truncated`、喪失の理由 `lock_not_owned`・`job_record_superseded`
8. module 4.4: `JobContext` の公開 API(`Check`、`JobNotStartable`、`finish` の戻り値、`start_running` が `started_at` を返す)と `FailureReason` が `jobs/records` にあること
9. module R3 と 4.4 の整合: `crawl`・`source_delete` が `infrastructure.opensearch` を import できない一方、`jobs/records` の操作は `Repository` を取る。`jobs` 入口にファサードを置く旨を明記(P6 が具体化)
10. architecture 11章: Job Runner の走査間隔5秒、受付途中の猶予60秒の採用を追記

## 9. 次のアクション

1. P4+P5 を code-reviewer・test-reviewer で並列レビュー(比較基準 HEAD `061dc7b196f67a689e0d834eb676ce356d6cdb34`。重点は並行性(ロック解放の順序・受付の巻き戻し・`JobContext` の喪失検知)、ロックを削除しない条件(§4-3)、`queued`→`failed` の2か所(§4-2)、削除に関わる安全側の判断)→ 0012 に記録
2. P6(`crawl`)。P6 の依頼に §6 と §5 の「`jobs` 入口のファサードが要る」を必ず含める
