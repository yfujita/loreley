# 0011 P4 実装: crawl_runs / deletion

日付: 2026-11-12 / 実施: code-implementer(メインが検証を再実行) / プラン: 0002 §6 P4
比較基準(P3+P4 のレビュー用): HEAD c065b9e(`apps/indexer` は未コミットの新規ファイル全体)
次: P3+P4 をまとめて code-reviewer / test-reviewer でレビュー(プラン §8)

## 実施内容の概要

削除ワーカー、判定、バッチ実行、ソース削除 1〜3、ファサード、設定、`delete_by_query` 専用タイムアウト(0005 の持ち越し)を実装した。api・main・README・Dockerfile は未着手(P5/P6)。コミットはしていない。

## 検証結果(メインが再実行して一致を確認)

- `uv run pytest` → **1274 passed**(P3 の 1105 から +169。うち `tests/crawl_runs/deletion` は152。3回連続で同数)
- `uv run ruff check` → All checks passed
- `uv run ruff format --check` → 160 files already formatted
- `apps/indexer` と `agent_tasks` 以外の変更なし(`.obsidian/workspace.json` は無関係の既存変更)
- 実装担当の確認: deletion を8回連続実行して不安定さなし。実スレッドを使うテストは2件のみ(起床で処理される、停止で終了する)
- ミューテーション確認(スクラッチのコピー上で62件、**62件すべて検出・生存0**): T>D ガードの削除と `>=` 化、強制削除での割合ルール迂回、件数照合の省略、`N_seen` の `crawl_started_at` 条件、`E_missing`、スキップ・サイズ超過 ID の除外、判定前の refresh、ID 上限判定、最小件数・割合の境界、`cutoff` の向き、TTL 再確認の削除、`source_id` 照合の削除、バッチ前のメンテナンス確認の削除、409 を削除扱いにする変更、自分の結果の読み直しの削除、バッチ排他の削除、`deleted_count` の記録、バックオフ・リトライ回数の境界、ロック確認の削除(全削除・記録の削除)、全削除の再実行ごとの再確認、事前・事後 refresh の削除、`_count` 確認の削除、再実行上限 +1、`source_id` 条件の誤り、discard が終端状態を上書きする変更、discard の排他・上限、記録の削除が別ソースまで消す変更、アダプタの `request_timeout` 欠落、専用クライアントが `retry_on_timeout=True` になる変更 など

## 変更・作成したファイル(`apps/indexer/` 配下)

新規 `src/loreley_indexer/crawl_runs/deletion/`: `__init__`、`config`(`DeletionConfig`)、`exclusion`(`SourceBatchExclusion`)、`judgment`(純粋関数 `ttl_cutoff`・`is_expired`・`passes_ratio_rule`、`Measurements`、`progress_update`)、`targets`(`TargetCollector`)、`judge`(`DeletionJudge`)、`result_writer`(`ResultWriter`)、`executor`(`BatchExecutor`)、`outcome`、`processor`(`DeletionProcessor`)、`worker`(`DeletionWorker`)、`source_deletion`(`SourceDeletion`)、`service`(`DeletionManager`、`create_deletion_manager`)
変更: `common/errors.py`(`LockNotOwnedError`)、`common/locks.py`(`LockInfo` を `documents.requests` から移動。documents は再公開で互換)、`config.py`(`os_delete_by_query_timeout_seconds`、`Settings.deletion_config()`)、`crawl_runs/__init__.py`(再公開)、`crawl_runs/lifecycle/results.py`(`DeletionResults.list_non_terminal`・`delete_source_records` を追加。P3 のレビュー対象に含む)、`infrastructure/opensearch/{connection,search_index_adapter,__init__}.py`(専用クライアント)
テスト: 新規 `tests/crawl_runs/deletion/`(`conftest`、`scenario`、`test_judgment`、`test_targets`、`test_exclusion`、`test_decision`、`test_execution`、`test_serial`、`test_worker`、`test_source_deletion`、`test_concurrent_crawls`)、変更 `tests/common/test_errors.py`、`tests/infrastructure/opensearch/{test_connection,test_request_shape,test_search_index_adapter,test_unavailable_wiring}.py`、`tests/test_config.py`、`tests/crawl_runs/lifecycle/test_results.py`
依存ルール許可表(`ALLOWED`)の変更なし(deletion は `crawl_runs.lifecycle`・`infrastructure.opensearch`・common だけを import)

## 判断・設計上の理由

### ユーザー未承認の追加・変更
1. **新設定 `os_delete_by_query_timeout_seconds`**(既定 600秒、gt=0・le=3600)。`OpenSearchConnectionConfig.delete_by_query_timeout_seconds` に対応
2. **アダプタのコンストラクタに必須引数を2つ追加**: `delete_by_query_client`、`delete_by_query_timeout_seconds`。`delete_by_query` だけ専用クライアント(`create_delete_by_query_client(config)` = `retry_on_timeout=False`)で `request_timeout` を付けて送る。opensearch-py では timeout 再送が transport(クライアント)単位でリクエストごとに切り替えられないため別クライアントにした(0005 の持ち越しへの対応)。接続エラーの再試行は通常と同じ。P5 の main が2つのクライアントを作って渡す
3. `LockInfo` を `common/locks.py` へ移動(R3。documents は再公開で互換)
4. `DeletionResults` に2メソッド追加

### 倒した未決・仮名
5. ファサード: `CrawlRuns`(P3)は変更せず、別オブジェクト `DeletionManager` を新設。`wake=event.set` の配線は 0010 の申し送りどおり
6. **削除専用ロック設計**: `SourceBatchExclusion`(`threading.Condition` のソース単位排他。`CrawlRuns` の `SourceLocks` とも documents のロックとも別)。バッチ側(`hold_batch`)とソース削除側(`hold_priority`)があり、ソース削除が待っている間は削除側が同じソースの次のバッチを取らない(arch P29)。排他の範囲は、バッチ1回分(自分の結果の読み直し→メンテナンス確認→進捗書き込み→文書の削除)と、discard・文書の全削除。判定(件数・ID 取り込み)と状態遷移は排他の外で行い `if_seq_no` の条件付き書き込みで守る(長い判定で discard を待たせない)。記録の削除(順3)は排他を取らない(冪等でワーカーは404で止まる)
7. 先行待ち: 先行する結果が非終端なら `WAITING`(何も書かず検索インデックスも読まない)。ワーカーは待ち行列の先頭だけを処理するので、直接 `process()` を呼んだときの防御
8. **判定の順序**: 先行待ち → メンテナンス(`deletion_started_at` を書く前に判定。立っていれば `failed`)→ `deletion_started_at` の条件付き更新 → ID 一覧の上限超過(保存されていない一覧では `E_missing` を数えられないため、件数照合より前。検索インデックスは読まない)→ refresh を1回 → 件数照合 → 判定時刻を1回固定して対象取り込み → 対象0件なら `deleted(0)` → T>D(強制でも適用)→ 割合・最小件数(強制なら無視)。T と D は同じ refresh 後に取る
9. `cutoff` の丸め: TTL は範囲検証なしのため、日時計算が溢れないよう約±100年に丸める(`judgment.MAX_TTL_SECONDS`)。設計書にない防御的な追加で判定は変わらない
10. 割合ルール: しきい値が NaN のとき `T/D <= NaN` が偽で `skipped_by_ratio`(削除しない側)。D≤0 で T>0 は削除しない
11. 例外の扱い(設計書に規定なし): 判定フェーズの OpenSearch 全体異常は結果を変えず伝播(ワーカーが ID と例外クラス名のみログ。次の走査で処理し直す。結果は `running` のまま)。実行フェーズの削除エラー(全体異常・文書固有の拒否)だけを有界リトライしてから `failed(delete_error)`。`OpenSearchUnexpectedResponseError`・`MalformedRecordError` は伝播。書き込みの409が `write_conflict_max_rereads` を超えたら `UnavailableError("write_conflict")` で結果は変えない
12. `delete_error_retry_attempts` は最初の1回を含む総試行回数(arch 4.4 の「最大3回」の読み)。`reason_detail` は `unavailable:<reason>`、`rejected:<error_type>`、`target_limit_exceeded`(内容は含めない)。バックオフは `min(initial×factor^n, max)` にジッタ(既定0.5〜1倍)。ジッタ・sleep は注入可能(本番の sleep は `stop_event.wait`)
13. **TTL 再確認**: 現在時刻(`last_seen_at + TTL < 現在時刻`)に加え、**文書の `source_id` が結果のものと同じか**も確認(設計書にない安全側の追加。他ソースの文書を消さない)。読めない・無い `last_seen_at` は期限切れとみなさない。409は `write_conflict_max_rereads` まで読み直し、超えたら削除せず `deleted_count` に数えない
14. 進捗: バッチの前に `deleted_count` と判定の数値(`n_seen`・`e_missing`・T・D)を条件付きで書く。終端遷移の同じ書き込みにも同じ数値を載せる
15. 停止: `stop()` は実行中のバッチを終え、次のバッチの前と再試行の待ちで止まる。結果は `running` のまま残り、次回起動の整理で `failed(indexer_restart)` になる
16. **ソース削除1(discard)**: `lock` は受け取るが確認しない(案8)。`discard_max_attempts` は「試行ラウンド数」と解釈(1ラウンド=全非終端結果を一覧し読み直してから `discarded` を条件付きで書く)。最終ラウンドの後も1回確認し、残っていれば `UnavailableError("discard_conflict")`。戻り値は実際に `discarded` にした `crawl_id`
17. **ソース削除2(文書の全削除)**: 実行回数は「最初の1回+`delete_by_query_max_reruns`」。各回で refresh → `delete_by_query`(`source_id` 条件)→ refresh → `_count`。上限まで0にならなければ `UnavailableError("documents_remaining")`。戻り値は各回の `deleted` の合計。**ロック所有は1回目だけでなく再実行の前ごとに確認**(別ジョブがロックを取った後の再実行で新しい登録を消さないため。「何も書かずに409」は1回目に失敗した場合に成り立つ)
18. **ソース削除3**: `deletion-{source_id}` と該当ソースの全結果(終端・非終端とも)を削除。1件でも消したら `true`、なければ `false`(成功)

### 設計書との食い違い・限界(推測で埋めていない)
- refresh が反映されない場合、`_count` が古いまま0と判定して「完了」と誤る可能性は残る(fake の `refresh_stalled` で検出できるのは古い `_count` が0でない場合だけ)。実機確認は U-31 に持ち越し
- 先頭の結果が壊れた記録などで処理できないと、全ソースの待ち行列が止まる(ログに出るのみ。ハング検知は設けない方針(9.9)の範囲)
- 判定フェーズの全体異常は `running` のまま走査ごとにやり直す。上限付きにするか(例: 連続失敗で `failed`)は設計書に規定なし(レビューで判断を仰ぐ)
- D-86(PIT なし取得)は fake での確認のみ
- 設計書との矛盾は見つからなかった

## arch テストID対応表(`tests/crawl_runs/deletion/` 配下。要旨)

D-1・D-2・D-3(割合ルールと境界)/ D-5・D-6・E-9・E-10(強制削除モード。件数照合・メンテナンス・スキップ文書は迂回しない)/ E-1・D-25・E-27・E-8 / D-10・D-21・E-41・二重防御 / D-13(K35 含む)/ D-38 / D-72 / D-85(強制でも適用)/ D-76(a)(b) / D-86 / D-9 / D-87(a)(b)(c)・D-88・D-89 / D-19・D-33 / D-44 / D-31・D-32・D-46(a)(b) / D-36 / D-12・D-39(実行側)/ D-92(a)(b)(c) / D-93 / D-35 / D-41・D-42 / D-74(a)(b)(c) / D-84 / D-90(a)(b)(c)(refresh 停止は `refresh_stalled`)/ E-43 / E-41(件数照合)/ ロック確認(案8、4種の不所有)/ `request_timeout`・専用クライアント / 設定
未再現: D-26・D-47〜D-51・D-56〜D-69・D-71 は設計書上 16.10(対象外)

## P5 への申し送り

### 配線(`main.py`)
```python
wake_event = threading.Event()
runs = CrawlRuns(config=settings.lifecycle_config(), deletions_store=..., clock=..., wake=wake_event.set)
os_client = create_opensearch_client(conn); dbq_client = create_delete_by_query_client(conn)
search_index = OpenSearchSearchIndexRepository(
    os_client, names.search_index, update_retry_on_conflict=...,
    delete_by_query_client=dbq_client,
    delete_by_query_timeout_seconds=conn.delete_by_query_timeout_seconds)
deletion = create_deletion_manager(settings.deletion_config(), results=runs.results,
    search_index=search_index, jobs=StoreJobsReader(jobs_store), clock=clock, wake_event=wake_event)
```
- **起動順**: `runs.fail_unfinished_crawls_after_restart()` → `deletion.start()` → HTTP 受付。先にワーカーを始めると、再起動前に受理した削除を再開してしまう
- 停止は `deletion.stop()`(`start()` は1回だけ。再起動不可)

### 公開インターフェース(`DeletionManager`)
- `start()` / `stop()` / `wake()`、`worker.run_once()`、`processor.process(crawl_id)`
- `discard_source_crawls(source_id, lock: LockInfo) -> list[str]`、`delete_source_documents(source_id, lock) -> int`、`delete_source_records(source_id, lock) -> bool`
- `LockInfo` は `loreley_indexer.common.locks`(または `documents.LockInfo`)

### エラー→HTTP の写像
- `LockNotOwnedError`: 409 `lock_not_owned`、`retryable=false`
- `UnavailableError` は 503 `unavailable`(retryable)。`reason`: `write_conflict`、`discard_conflict`、`documents_remaining`(api 4.7 の5xx に当たる)、OpenSearch 由来(`http_503` など)
- `OpenSearchUnexpectedResponseError`・`MalformedRecordError` は 500
- ソース削除2・3の `lock` はリクエストに必須。DELETE への `lock` の載せ方(ボディかヘッダか)は api 3.2 で未確定のため P5 で決める。順1は受け取るだけで確認しない
- api 4.6 のレスポンスは `{"discarded_crawl_ids": [...]}`、4.7 は `{"deleted_count": n}`、4.8 は `{"deleted": bool}`。discard は実行中のバッチ1回分だけ待たされうるので Crawler 側のタイムアウトはそれを見込む

## 未対応事項・持ち越し

- docs・README への新設定(`os_delete_by_query_timeout_seconds` など)の反映は未実施(P6)
- U-31(実機): `delete_by_query` の `version_conflicts`・タイムアウト・再送抑止、削除時の `not_found` の応答、`search_after` と `document_id` ソート、refresh の挙動
- 判定フェーズの全体異常を上限付きにするか(連続失敗で `failed` など)は未決
- コミット未実施

## 次のアクション

P3+P4 を code-reviewer / test-reviewer で並列レビュー(比較基準 HEAD c065b9e。対象は `crawl_runs/` 全体と対応するテスト、`infrastructure/opensearch` の専用クライアント変更)。
