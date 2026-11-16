# 0012 P4+P5 のレビューと修正

日付: 2026-11-14 / 実施: code-reviewer・test-reviewer(各2回)、code-implementer(修正2回)/ 記録・再検証: メインエージェント
レビュー対象: P4・P5 で追加・変更した `sources/`・`jobs/`(直下・records・locks)・`common/` と対応テスト(`apps/crawler/` は未コミット。比較基準 HEAD `061dc7b196f67a689e0d834eb676ce356d6cdb34`)

## 1. 1回目のレビュー結果(ともに「軽微な修正で可」、Critical なし)

code-reviewer の総評: 並行性・ロック・リースの設計は全経路を追って重大な欠陥なし。喪失時・停止待ち超過時・最終状態未記録時にロック文書を削除しない条件と、版条件による保護は実装どおり。0007 §4 の申し送りも遵守。

### Important(3件)と対応

| 指摘 | 対応 |
| --- | --- |
| [test-reviewer・本体の欠陥] 最後の手段の `failed` が、すでに終端のジョブを上書きする。実行対象が `finish(SUCCEEDED)` の後に例外を出すと Runner が `failed(internal_error)` に上書き。`JobContext.finish` の終端後の2回目も True で上書き(再現スクリプトで確認) | `JobContext.finish` は終端と分かっていれば何も書かず False(喪失も記録しない)。他者が状態を変えていたときは従来どおり喪失(`job_record_superseded`)を記録して False(区別している)。Runner の `_execute` は `context.is_terminal` が真なら最後の手段を呼ばない。succeeded・partially_succeeded・cancelled・failed の各最終状態の後に例外を出すテスト |
| [code-reviewer] 壊れたロックの `job_id`(空)で `JobRecordStore.fetch("")` が、実 opensearch-py では `ValueError`(`OpenSearchException` ではなく分類を素通り)、fake は None で挙動が分かれる。回復・解放・受付が落ち、起動できない | `JobRecordStore.fetch` と `client_calls.fetch_record` の先頭で空 ID なら None。契約テストを fake と opensearch 実装(transport 経由)の両方に追加。回復・解放・受付の各経路に `job_id` が欠落・非文字列・空のロックのテスト |
| [code-reviewer] `parse_instant` が `OverflowError`(`9999-12-31T23:59:59-05:00` 等)を `ValueError` にしない。1件の壊れた日時のロックで `list_locks` 全体が失敗し起動時の回復が落ちる | `parse_instant` で `OverflowError` を `ValueError`(`from None`、入力値なし)に変換。範囲外日時のロックを混ぜても回復全体が成功するテスト。設定の `updated_at` が範囲外の記録は、その記録だけ `MalformedSourceRecord` |

### Suggestion・Nitpick の対応

- Runner のホットループ(`_run_job` がジョブを `queued` のまま終えても即再走査): `_run_job` は終端なら True、そうでなければ False。`run_next` は例外を `job_id`(`loggable_id`)と例外の種類つきでログに出し False。`run_until_stopped` は False のとき `scan_interval` 待つ
- 管理者のロック解放で、ロックが指すジョブの `status` が形式不正なら 500 ではなく `LockInUse`(409。解放しない)
- 取り消し後のロック削除失敗(ジョブは `cancelled`、ロックは残る、再試行は `JobAlreadyFinished`): architecture 5.5 が許容する限界として docstring に明記しテストで固定
- `_fail_job` が `StoreUnavailableError` で失敗する場合に `job_id` つき警告、`NotReleased` を Runner が警告(理由は固定名)
- `purge.py` の docstring に、`document_id` を持たない記録が2件以上あるとソース削除の走査が `non_unique_sort` になりうる限界を注記
- `MAX_CONFLICT_ATTEMPTS` の4か所重複を `common/conflict.py` に統一(`jobs/records`・`jobs/locks`・`jobs` 直下は互いに依存できない(R6)ため、全層から参照できる葉の `common` に置いた。`sources` は設定可能な別の値5)
- テスト: `seed_queued` をロック先に(競合解消)、`SystemExit`・`KeyboardInterrupt` で heartbeat が止まる・`heartbeat.start` 失敗でジョブは `queued` のままロック保持、形式不正な先頭 `queued` で Runner が継続、`JobCancellation.cancel` に形式不正記録、起動時の回復→Runner の結合、#33 の一気通貫、受付の巻き戻し失敗、確認点つき retrier、`NotFound` 注入
- R7 検出器がレシーバ名(`repository` を含む名前)に依存する限界を docstring に明記(別名代入の検出は未対応)。`test_job_ids.py` の一意性テストは乱数元を固定して決定的に
- ハートビート(S-8): 期限超過後に `tick()` が成功すると `is_owned()` が True に戻る(`lost_reason` は None のまま)現行挙動を、**挙動は変えず**テストで固定(設計判断の余地として報告)

### 対応しなかったもの(理由つき)

- `sources/validation.py` が64bit範囲外の整数(`ttl`・`min_delete_count`・`schedule_interval_seconds`)を許す件: OpenSearch の `long` の範囲を超える値は書き込みで失敗し 500。**P8(`api`)への申し送り**(型として表現可能な範囲だけ `ProblemReason.FORMAT` で弾く案。「範囲は見ない」方針 CA-K-16 とは別)
- R7 検出器の別名代入の検出(限界を docstring に明記)

## 2. 2回目のレビュー(再レビュー)結果

- code-reviewer: 「軽微な修正で可」。前回の Important 2件と test-reviewer の Important は、コードを直接読んで解消を確認。修正による新たな競合・設計書にない追加なし。
  - `finish` の契約: 「終端と分かっている」判定は `apply_job_update` が競合時に読み直した最新の記録に基づき、古い読み取りで立つ経路はない(`_is_terminal` を立てる3箇所: 自分の `finish` 成功、`_record_superseded`、`start_running` で取り消しに負けて現在の状態が終端)。ロックを削除しない3条件は `_release` の入口で効いたまま
  - `finish` が False を返す意味: 「すでに終端」(自分で記録済み、または他者が記録)で、どちらかは区別できない(区別が要るなら `heartbeat.lost_reason`)。**P6 の呼び出し側は、False を受けたときに実行結果を再判定しない**こと
  - Runner: ホットループ解消、停止要求の取りこぼしなし(`request_stop` は停止フラグ→`notify`、`RunnerWakeup.wait` は通知が先でも即戻る)
  - **S-8 のハートビートは安全側**: Indexer が最終的な判定者(メモリ上の期限は書き込み前の `now` から計算するのでロック文書の期限以下。要請の到着前に期限が切れたら Indexer が `lock_not_owned` で拒否し、`record_lock_not_owned` で喪失が記録される)。期限超過中に管理者の解放や他ジョブの取得でロックが変わった場合は tick が版条件で `Conflict`→読み直し→喪失として記録。確認点に余裕を持たせる(残り時間が要請のタイムアウト未満なら所有していないとする)かは設計判断の余地だが Indexer が強制するので必須ではない
  - `common/conflict.py` は import を持たない葉で R10 に適合
- test-reviewer: 「軽微な修正で可」。前回の Important は解消。変異15件で生存2件(同値)。`finish` 側のガード単独除去は `test_context.py` が検出、Runner 側のガード単独除去は `finish` 側のガードに包含される同値(実害なしの二重防御)。スレッド系を CPU バーナー8本の負荷下で各500回繰り返して失敗0、10回連続成功、スレッドのリークなし。空の `job_id` は2層で守られ、実機側の意味は `test_repository_contract.py`(実 `OpenSearch` クライアント+fake transport)が持つ
- 両者が指摘した残り: 起動時の回復(`StartupRecovery._is_stale`)で、自分のロックが指すジョブ記録の `status` が形式不正だと `malformed_job_record` で回復全体が異常終了する。管理者の解放は `LockInUse` にしたので、解放も再起動もできず手編集でしか直せなくなる

## 3. 3回目の小修正(再レビューは省略)

- 回復の `_is_stale` で `malformed_job_record` だけ捕捉。そのロックは「判断できない」として削除せず、ジョブ記録も変更せず、`source_id` と `job_id`(`loggable_id`)つきの警告を出して続行(値は出さない)。他の `StoreUnexpectedResponseError` は伝播。回復の他の手順(`running`→`failed(crawler_restart)`)は記録の `status` と `owner` だけで対象を選び `job_type`・`source_id` は読まないため、他の項目が壊れていても落ちない(docstring に明記、テストで固定)。テスト: `status` が `"garbage"`・None・5 のロックと記録を変更しないこと、他のソースの `running` の失敗・孤児ロックの削除・`queued` の保持は進むこと、警告に `job_id` が出て値は出ないこと、`owner` が壊れたロックは触らず警告
- Nitpick: `lock_document.py` の docstring に「`owner` が壊れたロックは回復では触らず管理者の解放で消す」、`LostResponseRepository` の docstring に再現できない場合(未適用の応答喪失は `behavior.inject`、遅延適用は `behavior.before` か `seed`、`delete_ids` の応答喪失は対象外で `fail_bulk_delete_of` で部分失敗)、`test_runner.py` の "logged" 名のテストにログ検証、`test_previous_crawl.py` に同一 `queued_at` のとき `job_id` の降順になるケース
- **再レビューを省略した理由**: 修正が小さく(回復の1か所の例外捕捉と docstring・テスト)、両レビュアーが方針(判断できないものは削除せず警告して続行)に異論なく、管理者の解放の既存の同種の扱いに揃える変更であるため。メインが検証を再実行して確認した。変異確認は6件中5件検出、生存1件は到達できない防御(`status` プロパティが送出しうる `StoreUnexpectedResponseError` は `malformed_job_record` だけ)で同値

## 4. 検証結果(メインが再実行、`apps/crawler`)

```
$ uv run pytest -q           -> 2217 passed, 3 skipped in 13.24s(P5 実装直後 2161 → 2208 → 2217)
$ uv run ruff check          -> All checks passed!
$ uv run ruff format --check -> 184 files already formatted
$ uv lock --check            -> Resolved 39 packages
```

skip 3件は macOS 固有(0009 §4)。`git status` は `apps/crawler/` のみ。残骸ファイル・プロセスなし。

## 5. 設計書の改版依頼リスト(提案。P4・P5 のレビュー修正分。0010 §7・0011 §8 に追加)

1. architecture 4.8: 最終状態は1度だけ記録する(終端の後の `finish` は何もしない。最後の手段も上書きしない)
2. architecture 5.3・5.7: ハートビートは、期限超過を観測しただけでは喪失を永続化しない。更新に成功すれば所有が戻る(S-8。永続化を求めるなら要改版。Indexer が最終判定者のため現行は安全側)
3. crawler-api 4.3: ロックが指すジョブの `status` が読めないときは `lock_in_use`(409。`existing_job.status` は null)
4. architecture 3.3.2・5.1: `job_id` が欠落・非文字列のロックは、ジョブ記録なしの孤児ロックとして扱う(空の `job_id` は Store に問い合わせない)
5. architecture 2.5: UTC にすると範囲を超える日時(`9999-12-31T23:59:59-05:00` など)は、読めない日時として扱う
6. module 4.4: `run_next` はジョブを終端にできなかったとき False(走査間隔だけ待つ)。先頭の形式不正な `queued` で Runner が止まらず警告して待つ
7. architecture 5.8: 回復は、ロックが指すジョブ記録の `status` が形式不正なら、そのロックを削除せずジョブ記録も変更せず警告して続行する(回復全体を止めない)。管理者の解放も同じ状況を `lock_in_use` にする。解消手段は手編集かソース削除ジョブの再実行で、運用手順に書く(CA-U-3 と同様)
8. P8(`api`)への申し送り: `sources/validation.py` は64bit範囲外の整数を弾かない。OpenSearch の `long` の範囲を超える値は書き込みで失敗するため、`api` 側の検証か `reason` の扱いを P8 で決める

## 6. P6 への申し送り(0010 §5・0011 §6 に加えて)

- **`jobs` 入口のファサードが必要**(code-reviewer の提案): `crawl`・`source_delete` は R3 により `infrastructure.opensearch` を import できないが、P4 の関数(`purge_document_records`・`delete_document_records_of_source`・`find_previous_completed_crawl`・`is_maintenance_enabled`・`DocumentRecordStore`)は `Repository` を引数に取る。`jobs` 入口から `Repository` を内部に束ねたクラスを公開し、`main` が jobs 用 Repository で組み立てて注入する。例: `DocumentRecords`(`record_skip`・`record_oversize`・`purge(source_id, record_type, should_delete, retrier)`・`delete_all_of_source(source_id, retrier)`)、`JobHistory`(`find_previous_completed_crawl(source_id, excluding_job_id, max_jobs)` と、`scheduler` 向けの直近のクロールジョブの `queued_at`)。`SkipStage`・`OversizeDetector`・`DocumentRecordType`・`StoreWriteFailedError`・`PreviousCrawl` を `jobs/__init__.py` から公開する。`crawl` は `Retrier` を `JobContext.retrier(...)` から取り各操作の引数で渡す
- `JobRecordStore.update`/`create` の応答喪失判定は `dict ==` 比較。**`changes` は JSON 型(list・dict・str・数値)で渡す**(tuple や非 JSON 値だと JSON 往復で不一致になり、`create` で偽の `JobIdCollision` になりうる)
- **`JobContext.finish` の False は「すでに終端」(自分で記録済み、または他者が記録)**。区別が要るなら `heartbeat.lost_reason`。呼び出し側は False を受けたとき実行結果を再判定しない
- 0011 §6 の `JobContext`・理由コードの対応、`Check` の使い分け(`crawl` の開始通知より前は `Check.ALL`)

## 7. 持ち越し

0010 §8・0011 §7 のとおり(実 OpenSearch での `create`・`if_seq_no` の並行時の原子性、ハートビート専用クライアントの要否 CM-U-1、実環境のソート・絞り込み・date 型、スレッドと GIL、10,001件以上の走査・バルク削除の部分失敗・PIT、`allow_partial_*` のサーバー側の受理)。

## 8. 次のアクション

P6(`crawl`)を `code-implementer` に依頼する(0007 §4・0010 §5・0011 §6・本記録 §6 を含める。規模が大きいため 6a・6b に分けてよい。0002 §5 P6)。完了後に P6 の code + test レビュー。
