# 0010 P3 実装: crawl_runs / lifecycle

日付: 2026-11-12 / 実施: code-implementer(メインが検証を再実行) / プラン: 0002 §6 P3
比較基準(P3+P4 のレビュー用): HEAD c065b9e(`apps/indexer` は未コミットの新規ファイル全体)
レビューは P3 と P4 の完了後にまとめて実施する(プラン §8)

## 実施内容の概要

開始通知・終了通知・世代管理・再送判定・Status・起動時整理・終端遷移ヘルパー(保持件数の整理を含む)を `crawl_runs/lifecycle` に実装した。deletion(判定・実行・ソース削除・ワーカー本体)・api・main は未着手(P4/P5)。コミットはしていない。

## 先に追加したテスト(P2 test-reviewer の Suggestion S1〜S3)

- S1: PDF 打ち切り境界(`pdf_with_pages(["x"*1024, "y"])` は `truncated=True`・`text=="x"*1024`、`["x"*1024]` は `truncated=False`)
- S2: `retry_backoff_initial_seconds=max=30` でも停止要請後の `run_once()` が5秒未満(本番配線 `sleep=stop_event.wait`)。processor 単体の `sleeps == [1.0]` は `sleeps in ([], [1.0])` に緩和し、`len(llm.prompts)==1` を主とした
- S3: `submit` の `notify()` の確認(`_SignalingCondition` を `tests/documents/summarization/conftest.py` に移して共有化、`signal_when_a_taker_waits(queue)`)

## 検証結果(メインが再実行して一致を確認)

- `uv run pytest` → **1105 passed**(P2 完了時の 863 から +242。3回連続で同数)
- `uv run ruff check` → All checks passed
- `uv run ruff format --check` → 135 files already formatted
- `apps/indexer` と `agent_tasks` 以外の変更なし(`.obsidian/workspace.json` は無関係の既存変更)
- 実装担当のミューテーション確認: スクラッチのコピー上で70件、69件を検出・1件生存(`list_running_without_finish` から `missing=("finish_received_at",)` を外す変更。`_supersede` が読み直しで再確認するため結果が同じになる等価変異)。途中で未検出だった「同時刻の複数結果の `waiting_for` が crawl_id 順になる」はテストを追加して検出させた

## 変更・作成したファイル(`apps/indexer/` 配下)

新規(`src/loreley_indexer/`): `common/source_locks.py`(`SourceLocks`。documents から移動)、`crawl_runs/lifecycle/{config,notifications,results,start,finish,status,restart}.py`、`crawl_runs/service.py`(ファサード `CrawlRuns`)
変更: `common/errors.py`(契約エラー追加)、`config.py`(`Settings.lifecycle_config()`)、`crawl_runs/__init__.py`・`crawl_runs/lifecycle/__init__.py`(再公開)、`documents/{registration,last_seen,__init__}.py`(`SourceLocks` の import 元を common に変更)。`documents/source_locks.py` は削除
テスト: `tests/crawl_runs/factories.py`(拡張)、`tests/crawl_runs/lifecycle/{conftest,test_lifecycle_config,test_notifications,test_start,test_finish,test_status,test_restart,test_results,test_serialization}.py`、`tests/common/{test_errors,test_source_locks}.py`、`tests/architecture/{dependency_rules,test_dependency_rules}.py`、`tests/test_config.py` ほか

## 判断・設計上の理由(倒した未決・仮名・追加項目。いずれもユーザー未承認)

1. **`SourceLocks` を common へ移動**。documents と crawl_runs が互いに依存できない(R3)ため。インスタンスは別(`CrawlRuns` が内部で専用の1つを作る。案19)。許可表の変更は不要(common は全モジュールから参照可)
2. **許可表の変更は1行**: `ALLOWED["config"]` に `crawl_runs` を追加(`config.py` が `LifecycleConfig` を import するため。P2 の documents と同じ方針。`crawl_runs.lifecycle`・`crawl_runs.deletion` を config が直接 import するのは禁止のまま)
3. **受理の書き込みで 409 が `write_conflict_max_rereads` を超えたとき**: 設計書に規定なし。何も書かずに `UnavailableError("write_conflict")`(api で 503 の再試行可能なエラー)。受理は冪等で Crawler の再送で収束する
4. **開始通知の書き込み順**: 世代の更新 → 旧結果の `superseded` 化 → 新しい結果の作成(設計書の記述順は世代・結果作成・supersede)。結果作成を最後のコミット点にして、途中失敗後の再送が「結果あり=成功」で世代更新や整理を飛ばさないため(`test_a_start_that_failed_before_the_result_was_created_succeeds_when_resent`)
5. **再送比較**: 7項目(`source_id`、`crawl_started_at`、`ttl`、`ratio_threshold`、`min_delete_count`、`force_delete`、`rewrite_mode`)を正規化後の値で完全一致。`crawl_started_at` はミリ秒UTCに揃えて比較(D-79(c) は未決のため寛容側)。`ratio_threshold` は数値比較(整数1と保存済みの1.0は一致)。世代判定は strict(`<`。同時刻は受理)
6. 判定順 終端結果 → 再送比較 → 世代判定は設計どおり。終端状態の結果は内容や世代にかかわらず `crawl_already_finished`
7. **ID 一覧の合算件数**: 各一覧を重複除去・ソートした件数の合計を `skip_and_oversize_id_count` に常に記録し、`> skip_oversize_id_limit` のとき `skip_and_oversize_id_limit_exceeded=True` かつ一覧を保存しない。上限以内でも件数とフラグ(False)を記録する(設計書は超過時の記録だけを規定)
8. **`failed`/`cancelled` の受理**: `outcome` と digest を保存し、`enumerated_count` と ID 一覧は保存しない(K36 の「ダイジェストだけ」の読み)。`finish_received_at` なし。`ended_at` は設定。待ち行列に入れず wake もしない
9. **`FinishNotification` の追加検証**: ID 一覧の各要素は64桁小文字 hex(不正は ValueError)。`enumeration_completed` では `enumerated_count` と2つの一覧が必須、`failed`/`cancelled` では省略可。`skipped_count` は入力に持たない。`finished_at` は形式検証のみで保存も比較もしない。`crawl_id`・`source_id` は空文字を拒否(設計書にない形式検証)
10. **ダイジェストの正規形**: `{"outcome","enumerated_count","skipped_document_ids"(重複除去・ソート。省略は null),"oversize_document_ids"}` を `sort_keys`+区切り `,` `:` の JSON にして SHA-256(hex)。`source_id`・`finished_at` は含めない。省略(null)と空リストは別の値
11. **未知の `crawl_id`**: 案16どおり 202・結果を作らず、ログに `crawl_id` のみ。他の項目は出さない(テストで固定)
12. **`waiting_for`**: `running` かつ `finish_received_at` ありの結果に、直前の先行結果の `crawl_id` を返す(A→B→C で C は B)。順序は `(finish_received_at, crawl_id)`。`finish_received_at` なしの `running` は先行にならず `waiting_for` も None
13. **Status の項目**: api 4.5 の項目に `finished_at`(=結果の `ended_at`)。`reason_detail`・`rewrite_mode`・ID 一覧・skip_and_oversize の項目は返さない(api 4.5 にないため)
14. **保持件数の整理**: 終端遷移が書けたあとにそのソースの終端状態の結果を新しい順(`ended_at`、`started_at`、`crawl_id` の降順)に N 件残し、残りを削除。`running`(待機中含む)は数えず消さない。世代の記録(`deletion-{source}`)は対象外
15. **起動時整理**: 一覧が上限(`LIST_MAX_SIZE`)いっぱいなら繰り返す。受け付け前に呼ぶ前提でソース単位ロックは使わない。`failed` にした件数を返す。ID 一覧は終端遷移の同じ書き込みで消え、ダイジェスト・`finish_received_at`・記録済みの `deleted_count` は残る

### 形式検証の責務分担(NaN/Inf など)
- ドメイン側(`StartNotification.__post_init__`): 型(`ttl`・`min_delete_count` は int で bool 不可、`ratio_threshold` は有限の数値で bool 不可、`force_delete`・`rewrite_mode` は bool)と NaN/Inf を ValueError(メッセージに入力値なし)で拒否する多層防御。**範囲は一切検証しない**(確定事項。ttl=0・負値、しきい値1.5・負値も通る。テストで固定)
- API 層(P5)の責務: pydantic の `allow_inf_nan=False` と strict 型(`ttl: 1.5`・`1.0` を int に黙って変換しない、`rewrite_mode` に文字列や数値を拒否)で 400。日時のパースとタイムゾーン必須、`outcome` の列挙変換、必須項目の欠落、ValueError→400。D-94(f)(`rewrite_mode` が真偽値以外)は設計書でも未決のため、案14どおり形式不正の 400 とする想定

## arch テストID対応表(P3 で再現したもの。要旨)

D-11、D-12(開始側)、D-13(保存側)、D-15/D-75(a)、D-16、D-17、D-20/D-34、D-21(保存側)、D-29、D-31/D-32、D-36(開始側)、D-39(a)〜(c)、D-40、D-41/D-42(ID 一覧削除・digest 残存の保存側)、D-43、D-45、D-46(a)(b)、D-77/D-78/D-81/D-82(P2a 済み+開始通知の結果から受理条件が通ること)、D-79(a)〜(c)、D-80(6項目)、D-91(a)〜(j)(m)〜(q)・(k)・(l)、D-92(a)(c) の保存側、D-93(再起動側)、D-94(a)〜(e)((f) は ValueError)、C-27(c) の開始通知側、K43、案19(`test_serialization.py`)
直列キュー制御(arch 16.1): 実装が `threading.Lock` のため、処理中の書き込みの直前でゲートを使って1つ目を止め、2つ目が待たされるのを確認してから再開する形にした
P4 に回すもの: D-9・D-12 の実行側、D-19・D-31〜D-33 の判定・実行側、D-44、D-74、D-76、D-85〜D-90、D-92(b)、D-93 の B の ID 一覧による判定、E-41(件数照合)、E-43、ソース削除(D-35・D-41・D-42 の discard 割り込み側)

## P4/P5 への申し送り

### P4(deletion。すべて `crawl_runs.lifecycle` から import)
- `DeletionResults`(`CrawlRuns.results` が持つインスタンスを deletion が共有する): `fetch_result(crawl_id) -> StoredResult | None`、`replace_result(current, record) -> Written | Conflict | NotFound`(非終端の更新。`deletion_started_at`、`deleted_count` の進捗)、`transition_to_terminal(current, status, *, reason=None, reason_detail=None, progress=None)`(ID 一覧を同じ書き込みで削除しダイジェストは残す。`ended_at` を設定し書けたら保持件数 N の整理)、`list_unfinished_received(source_id=None)`(待ち行列、受理順)、`preceding_results(record)`、`list_running_without_finish`、`prune_terminal_results`
- 409/文書なしは戻り値。読み直しと再判定は呼び出し側(R8)。`retry_after_conflict(attempt, max_rereads=...)` が使える(超過は `UnavailableError("write_conflict")`)。自分の結果が終端・404 なら止まる
- 待機中の判定順1: `preceding_results(record)` が空になったら判定へ進む
- deletion 用の設定は `crawl_runs` 側に別の frozen dataclass を足し、`crawl_runs/__init__.py` で再公開、`config.py` が変換(config は `crawl_runs` の入口だけを import できる)
- `deletion`→`lifecycle` の import は `crawl_runs.lifecycle` から(R5)。lifecycle→deletion は禁止のまま
- ソース削除の discard: `transition_to_terminal(..., DISCARDED, reason=SOURCE_DELETED)` を `Conflict` なら読み直して再試行。直列化はバッチ排他と別(開始・終了のロックは `CrawlRuns` 内部の専用 `SourceLocks`。deletion 用のロックは P4 で別途設計)
- wake: `CrawlRuns(config=, deletions_store=, clock=, wake=callable)`。`wake` は `enumeration_completed` の受理を永続化したあとに1回呼ばれる(failed/cancelled、再送、遅れた通知、未知 crawl_id、拒否では呼ばれない)。例外を送出しないこと。想定配線: main が `threading.Event` を作り、`wake=event.set` を `CrawlRuns` に、同じイベントを削除ワーカーに渡す(ワーカーは `event.wait(deletion_poll_interval_seconds)`。案2)

### P5(api・main)
- ファサード: `CrawlRuns.start_crawl(StartNotification)`、`finish_crawl(FinishNotification)`、`crawl_status(crawl_id) -> CrawlStatus`、`fail_unfinished_crawls_after_restart() -> int`(起動時整理。**HTTP 受付の前に1回**。`/healthz` はこの完了後に応答)
- 開始通知の成功応答は `{crawl_id, status: "running"}` を api が組み立てる。終了通知は 202
- 例外と HTTP: `ContractError` のサブクラスをそのまま共通エラー形式に。ValueError(通知オブジェクト生成時)は 400、`UnavailableError` は 503、`MalformedRecordError`・`OpenSearchUnexpectedResponseError` は 500。終了通知の「形式 400 → source_id 409」は、通知オブジェクトの生成(400)が受理(409)より先になることで満たす
- `skipped_count`(api 4.4)は domain に入力を持たない。api が受けて件数と一致するか検証するか無視するかは P5 で決める(API-U-12 で未決)

## 未対応・持ち越し

- 同じ `crawl_id` を別の `source_id` で同時に開始通知すると、ソース単位ロックでは直列化されず、結果の作成(無条件 `save`)が競合しうる。Store 層に create 専用がないことと、`crawl_id` はジョブ ID で一意という前提による。単一 Crawler の MVP では起きないので対応しなかった
- `list_unfinished_received` は取得件数が `LIST_MAX_SIZE`(10,000)までで全件を並べ替える。通常は数件
- docs への反映、README、仮値一覧への追加は未実施(P3 では設定値の追加なし。既存の `skip_oversize_id_limit`・`write_conflict_max_rereads`・`deletion_retention_count` を使用)
- U-31(実機)。`loreley-deletions` の `finish_received_at`・`status`・`ended_at` を `exists`・`term`・ソートで使う keyword 前提は仮定義のまま
- 設計書の食い違い・矛盾は見つからなかった
- コミット未実施

## 次のアクション

P4(crawl_runs / deletion)を `code-implementer` に依頼する(0002 §6 P4。申し送りは本記録、0003(fake・delete_by_query 関連)、0005(delete_by_query 専用タイムアウト)。完了後に P3+P4 をまとめて code-reviewer / test-reviewer でレビュー)。
