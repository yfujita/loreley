# 0014 P6b: `crawl` の終了通知・ポーリング・最終状態・異常系・警告

日付: 2026-11-14 / 実施: code-implementer / 記録・再検証: メインエージェント
フェーズ開始時点の HEAD: `061dc7b196f67a689e0d834eb676ce356d6cdb34`(`apps/crawler/` は未コミット)。P6 全体(6a+6b)の code + test レビューを次に実施。

## 1. 検証結果(メインが再実行、`apps/crawler`)

```
$ uv run pytest -q           -> 2516 passed, 3 skipped in 16.08s(6a 後 2414 → +102。skip は macOS 固有の3件)
$ uv run ruff check          -> All checks passed!
$ uv run ruff format --check -> 221 files already formatted
$ uv lock --check            -> Resolved 39 packages
```

`git status` は `apps/crawler/` のみ。`NotImplementedError`(6a の暫定)は `src/loreley_crawler/crawl` から除去済み。実装担当の変異確認: 6b 向け46件+6aの約60件を回帰で再確認。初回の生存5件のうち3件にテストを追加して検出(ID 一覧の警告が通知を送る時点でジョブ記録に載っていること、終了通知の再送が所有確認の対象外であること、識別子エラーだけで `partially_succeeded` になること)。他者が終端にした場合のガードは冗長でログ記録の検証テストに、終端状態に `waiting_for` が付く変異は有効データで起きない同値。最終は同値1件を除き全件検出。新規テストはスレッドを使わず(ハートビートは `ManualWaiter`、時間は固定時計、待ちは `env.sleeps` に記録するだけ)、スリープなし。

## 2. 実装内容(`apps/crawler/src/loreley_crawler/crawl/`)

- 新規: `finish_notice.py`(`FinishNotice`: 内容の固定と `finish_notice` の記録形式)、`status_polling.py`(`StatusPoller`・`DeletionConfirmation`・`PollingResult`・`deletion_summary_record`)、`warning_log.py`(`WarningLog` と警告コード)
- 変更: `settings.py`(`CrawlSettings` に6項目)、`dependencies.py`(`CrawlDependencies` に `job_history`・`clock`)、`indexer_calls.py`(`finish_crawl`・`get_status`、終了通知用の失敗の対応づけ)、`run.py`(終了通知・ポーリング・警告・通知 `failed`/`cancelled`・最終変更の組み立て)、`executor.py`(正常終了と全異常の最終対応)、`constants.py`(`NO_CHECKS`)、`__init__.py`(公開型)
- tests: 新規 `tests/crawl/test_finish.py`・`test_polling.py`・`test_endings.py`・`test_warnings.py`・`test_finish_notice.py`。更新 `test_entry.py`(`NotImplementedError` の検証をやめ Runner との分担の検証に)、`test_logging.py`(6b の6経路を追加。全経路を `__call__` 経由に)、`support.py`(`finish`/`status` のイベント記録、実 Indexer 同様の `finish_received_at` の付与、`advance_clock_on_sleep`)。`tests/architecture`・`config.py`・共有 fake・docs は変更なし

## 3. 実装内容と判断理由

**終了通知**
- 送る順序: (1) ID 一覧の警告閾値を確認 → (2) 内容を `finish_notice` に保存して固定 → (3) `Check.ALL`(所有・取り消し・メンテナンス)で確認 → (4) `send_started_at` を記録 → (5) 送る
- `finish_notice` は `{"content": 送る本文, "send_started_at": 時刻|null}`(設計書は「別に記録」とだけ。4.7 の「`finish_notice` に `send_started_at` を記録」に合わせた)。`finished_at` はミリ秒に切って固定するので、記録の文字列と送る値が一致し再送しても同一
- **(3) の `Check.ALL` は設計書に明記なし**。終了通知は Indexer の削除判断のトリガなので、喪失・メンテナンス中は `enumeration_completed` を送らない安全側
- `enumeration_completed` の再送の確認点は取り消しだけ(終了通知は所有確認の対象外。5.7)
- 失敗の対応づけ: リトライを尽くした場合と409は `finish_notice_failed`、400・404 などは `indexer_rejected`
- `failed`/`cancelled` の通知は `outcome`・`source_id`・`finished_at` だけを固定して送る(確認点なし、`send_started_at` も記録しない)。条件は「`start_notice_sent` かつ `enumeration_completed` の送信開始前」。送れなくても握りつぶす。固定済みで未送信の `enumeration_completed` は `cancelled`/`failed` で置き換える

**ポーリング**
- 待ちは `JobContext.wait`、確認点は所有と取り消し(最初の要請の前にも確認)。区分は設計書どおり: 404だけが連続→`unknown`、404以外が混在または上限時間超過→`unconfirmed`、終端状態→`confirmed`。成功の応答で連続を数え直す
- 202 は受理の確認として扱わない。最初の成功の応答で受理の根拠(`finish_received_at`、または `failed`+`outcome_*`)を確かめ、なければ警告 `finish_not_acknowledged` を残してポーリングを続ける
- `deletion_summary` は12項目から None を省き、文字列は表示用に整形。打ち切ったときだけ `observed_at` を足す。上限時間は時計との差で測る(テストは待った秒数だけ時計を進めるので決定的)

**最終状態と異常系(`executor.py`)**
- 正常: `succeeded`。スキップ(`skipped_document_ids`)または識別子エラーがあれば `partially_succeeded`。原本サイズ超過・抽出失敗・削除結果(`skipped_by_ratio` など)は status を変えない。記録内容は `registration`・`confirmation`・`deletion_summary`・`warnings`

| 例外 | 最終状態 |
| --- | --- |
| `CrawlFailure` | その理由コードの `failed` |
| `CancellationRequested` | `cancelled` |
| `OwnershipLost` | `failed(lock_lost)` |
| `MaintenanceDetected` | `failed(maintenance)` |
| `StoreUnavailableError`(`StoreWriteFailedError` を含む) | `failed(store_unavailable)` |
| `StoreUnexpectedResponseError` | `failed(internal_error)` |
| 想定外の例外 | `failed(internal_error)`(詳細は型名のみ) |

- 取り消し: 送信開始前→通知 `cancelled` を送る。送信リトライ中→リトライをやめ確認結果の区分は書かない。ポーリング中→`unconfirmed`
- 他者がすでに終端にしていた場合は何も書かず通知も送らない(`finish` の False は再判定しない)。`JobNotStartable` は Runner のために伝播。最終状態を記録できなければ例外は伝播(Runner が最後の手段を試み、だめならロックを残して回復に委ねる)。記録できたジョブは Runner が上書きせずロックを解放(e2e テストあり)

**警告(`warnings`)**: 形式 `[{"code": ..., ...}]`、同じコードは1つだけ、上限 `warnings_max_entries=20`。コード(名称は案): `invalid_external_id`(件数と例。例は表示用に整形した `external_id` と固定の違反種別)、`enumerated_zero_after_nonzero`(前回の `job_id` と件数)、`finish_id_list_over_threshold`、`finish_not_acknowledged`、`polling_aborted`。0件列挙の警告は `finalize_registration` の中、`partial=false` 確定の前(`JobHistory.find_previous_completed_crawl`)。status・終了通知は変わらない(CA-P-52)

**仮値(`CrawlSettings`。architecture 11章の値。空欄なし)**: `finish_id_list_warning_threshold=8000`、`polling_interval_seconds=5`、`polling_timeout_seconds=1800`、`polling_max_consecutive_failures=3`、`warnings_max_entries=20`、`previous_crawl_lookup_jobs=10`。`config.py` の `CrawlerSizeLimits` と `CrawlSettings`/`DocumentsSettings` の項目名の一致をテストで固定

## 4. 設計書との食い違い・不明点(レビューで確認する)

1. **依頼文との差(重要)**: メインの依頼は「`OwnershipLost` ではロックを失っているので終了通知は送らない」と書いたが、設計書(5.7・4.8)は `failed` 通知を可能なら送る(`send_started_at` 前に限る。所有確認の対象外)としている。実装は設計書どおり、`lock_lost` でも送信前なら `failed` 通知を送る(`failed` 通知は削除を起こさないので安全側)。→ **レビューで安全性を確認する**(ロックを他の Crawler が引き継いでいる状況で `failed` 通知を送って Indexer 側に害がないか)
2. 終了通知(`enumeration_completed`)の送信前に、メンテナンス・所有の確認を入れた(7.9 は `last-seen`・バッチ登録の前しか挙げていないが、削除判断のトリガなので止める側に倒した)
3. 400・404・405 など409以外の終了通知の拒否は、7.8 の全 API 共通の行に従い `indexer_rejected`(4.8 の `finish_notice_failed` の行は「リトライ尽き、409」のみ)
4. 受理の根拠が得られないときの警告名・`polling_aborted`・上記コード名は設計書にない名前で、すべて案
5. `deletion_summary` の「読めた日時」を `observed_at` として、打ち切ったときだけ記録
6. `confirmation` は区分の文字列そのものとし、ポーリングに入っていない・終えられなかったジョブには書かない。取り消しだけ `unconfirmed` を書く

## 5. 設計書の改版依頼リスト(提案。P6b 分。0013 §9 に追加)

1. architecture 3.3.1・7.5: `finish_notice` の形式(`content` と `send_started_at`)。`failed`/`cancelled` の通知は `send_started_at` を記録せず、未送信の固定内容は置き換える
2. architecture 7.5・5.7: `enumeration_completed` の送信前に所有・取り消し・メンテナンスを確認する(喪失・メンテナンス中は `failed` 通知を送る)。送信リトライの確認点は取り消しだけ
3. architecture 4.8・7.8: 終了通知の失敗の対応づけ(リトライ尽き・409→`finish_notice_failed`、そのほか→`indexer_rejected`)
4. architecture 3.3.1・7.6: `warnings` の形式と警告コード。`deletion_summary` の `observed_at`、`confirmation` の記録条件
5. architecture 7.6: ポーリングの上限時間は最初の要請からの経過で測り、最初の要請の前にも所有・取り消しを確認する
6. architecture 4.7: 取り消しの境界は `send_started_at` 記録の前後。ちょうど記録の直後は「送信開始後」として扱う(`cancelled` 通知は送らない)
7. architecture 4.8: 他者が終端にしたジョブ(`lock_released` など)には通知も記録も行わない
8. module 4.5: `CrawlExecutor`・`CrawlRun`・`FinishNotice`・`StatusPoller` の公開型。`CrawlDependencies` に `job_history`・`clock` を追加
9. architecture 11章: 6b の仮値(ID 一覧閾値8000、ポーリング間隔5秒・上限30分・失敗連続3回、警告上限20、過去ジョブ10)を採用値として明記

## 6. P8 への申し送り

- 組み立て: `DocumentRecords(jobs_repository, clock)` と `JobHistory(jobs_repository)` を作る → `CrawlDependencies(source_reader, connector_registry, indexer_client, document_records, job_history, clock, settings=CrawlSettings, documents_settings=DocumentsSettings)` → `CrawlExecutor(deps)` を `executors[JobType.CRAWL]` に渡す
- `CrawlSettings` の環境変数から詰める項目: 6a 分 `chunk_size`・`last_seen_max_ids`・`batch_max_documents`・`batch_max_raw_bytes`・`consecutive_skip_limit`・`invalid_id_example_limit`、6b 分 `finish_id_list_warning_threshold`・`polling_interval_seconds`・`polling_timeout_seconds`・`polling_max_consecutive_failures`・`warnings_max_entries`・`previous_crawl_lookup_jobs`
- 整合性検査の対応: `CrawlerSizeLimits.max_raw_bytes` ← `DocumentsSettings.max_raw_bytes`、`batch_max_documents`・`batch_max_raw_bytes`・`last_seen_max_ids`・`finish_id_list_warning_threshold` ← `CrawlSettings` の同名項目(名前一致はテストで固定済み)
- ポーリングの上限時間(既定30分)はハートビートのリース更新と独立(別スレッドで続く)。Job Runner の `heartbeat_factory` と `clock` を `CrawlDependencies.clock` と同じ時計にする(上限時間と `finished_at` が同じ時刻源になる)
- センチネル検査(完了条件8)は `crawl` 全体に広げ済み。P8 では API のエラー応答に同種の検査を足す

## 7. 未対応事項・既知の限界

- 実機(実 Indexer・実 OpenSearch)でしか確認できないもの: 実 Indexer の Status 応答の項目(`finish_received_at` の有無、`waiting_for` の出方)、終了通知の409の出方、実ポーリング間隔と30分の妥当性、スレッド・GIL 下のハートビート
- 終了通知 `failed` は Store 層が使えないと固定内容を保存できずに送れない(設計書の「できれば」)
- 最終状態を記録できなかったジョブは、再起動時の回復(`crawler_restart`)まで `running` のまま残る(設計どおり)

## 8. 次のアクション

P6 全体(6a+6b)の code-reviewer・test-reviewer を並列で実施(重点: 異常系の最終対応、`send_started_at` の境界(#25・#30)、削除に関わる安全側の判断(終了通知の送信可否。特に §4-1)、件数照合、状態遷移の網羅、`jobs` ファサードと R3)→ 0015 に記録。その後 P7(`source_delete`・`scheduler`)と P8。
