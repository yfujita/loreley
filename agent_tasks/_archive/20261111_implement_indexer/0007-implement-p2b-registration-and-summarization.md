# 0007 P2b 実装: 登録・last-seen・summarization

日付: 2026-11-11 / 実施: code-implementer(メインが検証を再実行) / プラン: 0002 §6 P2 の後半
比較基準(P2 全体のレビュー用): HEAD c065b9e(`apps/indexer` は未コミットの新規ファイル全体)

## 実施内容の概要

登録(`documents:batch` のドメイン処理)、`last_seen_at` 部分更新、summarization(キュー・ワーカー・書き戻し・再走査)を実装した。あわせて P2a の判断修正(`document_id` の先頭 `/` を除去しない)を反映した。crawl_runs の開始/終了通知・deletion・api・main は未着手(P3 以降)。コミットはしていない。

## 検証結果(メインが再実行して一致を確認)

- `uv run pytest` → **782 passed**(P2a の 605 から +177。3回連続で同数、約3.2秒)
- `uv run ruff check` → All checks passed
- `uv run ruff format --check` → 114 files already formatted
- `git status`: `apps/indexer` と `agent_tasks` 以外の変更なし(`.obsidian/workspace.json` は無関係の既存変更)
- 実装担当のミューテーション確認: スクラッチパッドのコピーで21通りの改変(max比較、ロック喪失の継続、読み直し回数、再書き込みモード、サイズ超過、text_hash照合、メンテナンスフラグ確認、pending条件、ソース単位ロック、受理条件、件数上限、キュー重複排除、再走査の間隔下限、extract_failed で本文を残す、409読み直し 等)をすべてテストが検出。最初に未検出だった「ロックが途中で戻ってもバッチを再開しない」はテストを追加して検出できるようにした

## 変更・作成したファイル(`apps/indexer/` 配下)

- `src/loreley_indexer/config.py`: `registration_config()`、`summarization_config()`、設定 `summary_input_max_chars`(既定 30,000、上限 1,000,000)を追加
- `src/loreley_indexer/documents/`: `__init__.py`(公開入口)、`config.py`(`RegistrationConfig`)、`requests.py`(`LockInfo`、`CrawlContext`、`DocumentInput`)、`results.py`(`Change`、`FailureType`、`DocumentRegistered`/`DocumentFailed`、`LastSeenResult`、`LastSeenEntry`)、`registration.py`(`DocumentRegistrar`)、`last_seen.py`(`LastSeenUpdater`)、`search_document.py`(文書組み立て・変更判定)、`ownership.py`(`LockOwnershipChecker`)、`source_locks.py`(`SourceLocks`)、`document_id.py`(修正)
- `src/loreley_indexer/documents/summarization/`: `config.py`、`status.py`、`prompt.py`、`request_queue.py`、`processor.py`、`rescanner.py`、`worker.py`、`service.py`(`Summarization`、`create_summarization`)、`__init__.py`
- `tests/`: `documents/{factories,conftest}.py`、`test_registration.py`、`test_registration_conflicts.py`、`test_last_seen.py`、`test_source_locks.py`、`summarization/{conftest,test_prompt,test_request_queue,test_processor,test_rescanner,test_worker,test_summary_flow}.py`、`test_document_id.py`・`test_config.py`・`architecture/{dependency_rules,test_dependency_rules}.py` の更新

## P2a の修正

- `normalize_external_id` から先頭 `/` の除去を削除(NFC と `\`→`/` のみ)。docstring に理由(設計書の「先頭に `/` を付けない」は入力の前提で除去規則ではない。last-seen の ID が Crawler とずれる)を記載。api 4.3 のテストベクタは不変

## 公開インターフェース(P3 以降への申し送り)

- `DocumentRegistrar(config, admission_checker, search_index, jobs, extractor, summary_requests, source_locks, clock).register(CrawlContext, [DocumentInput]) -> list[DocumentOutcome]`
- `LastSeenUpdater(...).update(context, document_ids) -> list[LastSeenEntry]`
- `create_summarization(SummarizationConfig, search_index=, jobs=, llm=, clock=)`、`summarization.start()`(無効なら何もしない)/`stop()`
- **`SourceLocks` は登録と last-seen で同じインスタンスを渡す**(直列化の前提)。P3 の開始・終了通知用ロックは別インスタンス(案19)
- 例外: 受理条件5種は `AdmissionRejectedError`(409)、入力不正は `ValueError`(api が 400)、OpenSearch 全体異常は `UnavailableError`(503)、固定スクリプト Update 拒否は `OpenSearchUnexpectedResponseError`(500)
- P5(api層)の責務: **base64 デコード前に長さから推定してサイズ上限を判定する**(巨大な base64 のデコード自体を api 層で防ぐ)、`documents` 空・件数・合計サイズの 400、`fetched_at`・`metadata`・未知項目の無視(案7)、日時文字列のパース、結果型から api 4.2/4.3 の JSON への写像(`DocumentFailed.message` は固定文)
- P3: `deletion_result` を `rewrite_mode` 付きで保存する(`AdmissionChecker` が返す)

## 判断・設計上の理由(倒した未決・仮定・仮名)

登録:
1. 文書ごとの順序: ロック所有確認 → サイズ確認 → 抽出 → 取得 → 判定 → 書き込み。最初のロック失敗以降は、ロックが戻っても未処理文書をすべて `lock_not_owned`(書かない。案5)
2. 先頭で全文書の `document_id` を算出(NUL は ValueError)→ ソース単位ロック取得 → 受理条件確認 → 処理(前の要請が状態を変えた後の値を見るため、ロック取得後に確認)
3. 読み直し回数: 最初の読み出し + `write_conflict_max_rereads` 回(PUT は最大 上限+1 回)。超過は `write_conflict`。`create` の 409、条件付き PUT の 409/文書なし、補完 Update の文書なしはいずれも読み直し(文書がなければ新規 `create`)。fake の「存在しない文書への if_seq_no 付き操作」が NotFound でも Conflict でも同じ結果になることをテスト済み(U-31(2) の備え)
4. 補完 Update が 409(`retry_on_conflict` 超過)なら読み直しせず即 `update_conflict`
5. 変更判定: 完成した候補文書と既存を `content_hash`・`text_hash`・`index_status`・`title`・`source_updated_at`・`mime_type`・`size`・`url`・`path` で比較(値なしは None 同士で一致)。`summary_status` は比較しない。`source_updated_at` は UTC ミリ秒に正規化して比較
6. 要約項目: `extract_failed` は `summary_status=disabled`(`content`/`text_hash`/`summary`/`summary_model` は書かない、`truncated=false`)。再書き込みモードは要約を引き継がない。本文同一(両ハッシュ同じ)は既存の要約を引き継ぐ(既存に `summary_status` が無ければリセット)。それ以外は `pending`(要約無効なら `disabled`)
7. `external_id` は NFC・`/` 統一後の値を保存(応答は送られた値をそのまま返す)。`indexed_at` は書き込み時刻、`acl`・`extractor_version` 等は書かない
8. **「文書固有の拒否(`Rejected`)が連続20件で打ち切り」は Crawler 側の規則(api 3.5/arch 4.4: リトライ後スキップ+ジョブ failed)と読み、Indexer には実装しない**。`Rejected` は文書単位 `document_rejected`(message は OpenSearch の error_type 名のみ)
9. api 3.5 の `failure_type: store_error`(全体異常)は例外伝播にしたため使わない
10. PUT 成功後、`summary_status=pending` なら `summary_requests.submit(document_id)`(結果は待たない。キュー満杯でも登録は成功のまま `pending` が残り、再走査に委ねる)

last-seen:
11. 件数上限超過と ID が64桁小文字 hex でない場合は ValueError(入力値は含めない)。空リストは `[]`(受理条件は確認する)。固定スクリプト Update が `Rejected` の場合は文書単位の区分がないため `OpenSearchUnexpectedResponseError`

summarization:
12. **生成依頼は文書 ID のみ運ぶ(module 4.3 の「ID・content_hash・text_hash・本文」から逸脱)**。ワーカーが生成開始時に文書を読み直し、そのときの `content_hash`/`text_hash`/本文を生成元として保持(arch 7.4「生成を始めた時点の文書」と同じ)。理由: キューに本文を溜めるとメモリが `queue_size × 最大本文` になる(K39)。登録経由と再走査経由を同一処理にできる。キュー内は待機中の同一 ID を重複排除(処理中の ID は再依頼可能)
13. 試行: LLM 呼び出しと書き戻しをそれぞれ `summary_max_attempts` 回まで(間は `retry_backoff_*`、ジッタなし、停止要請で待ちを打ち切る)。書き戻し1試行内で409を `write_conflict_max_rereads` まで読み直す。上限超過は `pending` のまま(`failed` に遷移させない。案12)。`Rejected` は再試行せず `pending` のまま。LLM が空文字の要約を返したら失敗扱い
14. メンテナンスフラグは各書き込み試行の直前に確認(案11)。立っていれば `PAUSED_BY_MAINTENANCE` で書かず `pending` のまま。LLM 呼び出し前には確認しない(設計書は書き込み前のみ)
15. 再走査: 要請フラグ(起動時 / `pending` が残った / キュー満杯で断った)があり、前回走査から `summary_rescan_min_interval_seconds` 経過していれば `pending` の ID を `summary_rescan_page_size` ごとに列挙して依頼。キュー満杯で打ち切り、残りは次回
16. ワーカーの `run_once(wait_seconds=0)`: 依頼を1件処理(True)。処理中の例外は握りつぶさずログ(ID と例外クラス名のみ)に残してスレッドを落とさず、`pending` のまま再走査を要請
17. **未承認の設定項目 `summary_input_max_chars` を追加**(既定 30,000、上限 1,000,000)。LLM への入力を無制限にしないため(K39)。プロンプトは日本語固定文+タイトル+本文(本文は `input_max_chars` 文字で切る。`content` 自体は変えない)。不要ならこの1項目とプロンプトの切り詰めを外せる
18. 本文・プロンプト・要約をログや例外に出さない(R9)。センチネル文字列でのログ検査テストあり

仮名(設計書にない名前): `failure_type=oversize`(案1)、`SummaryOutcome` の値(`written`/`discarded`/`left_pending`/`paused_by_maintenance`/`disabled`)

依存ルール許可表の変更(根拠): `ALLOWED["config"]` に `documents` と `documents.summarization` を追加(config.py が各モジュールの Config dataclass に値を詰める方針。どのモジュールも config に依存しないため循環なし)。P2a の「config は documents(extraction 以外)を import できない」テストを「Config を持つ documents 系は可、crawl_runs は不可」に置き換え。R1〜R9 の他の検査は変更なし

## arch テストID対応表(`tests/documents/` 配下。要旨)

C-1 / C-2 / C-3 / C-4 / C-6 / C-7 / C-10a・b / C-12 / C-15 / C-17(a)〜(d) / C-18a・b・c / C-19a・b・c / C-20(a)(b) / C-21(a)〜(d) / C-22(b-1)(b-2) / C-24(a)(b) / C-25 / C-26 / C-27(a)(b) / E-3 / E-5・E-44・E-45 / E-6 / E-20(a)(b)(c) / E-21 / E-30 / E-45b(a1)(a2)(b) / L-5 / L-9 / D-77・78・81・82 の登録側 を `test_registration.py`、`test_registration_conflicts.py`、`test_last_seen.py`、`summarization/*` で再現。0005 の持ち越し(タイムアウト再送で409→読み直しで成立)は `test_registration_conflicts.py::test_resend_after_a_lost_response_succeeds_when_create_returns_409`・`..._conditional_put_returns_409`。案19 は `test_source_locks.py`
再現対象外: C-27(c)(開始通知の再送=P3)、E-41(件数照合=P3/P4)、L-6(分散フェンシングなしの既知の制限)、L-3系

## 未対応事項・持ち越し

- `search_index.refresh()` を挟まないと再走査(検索)は直前の書き込みを見ない(実機では約1秒の遅れで `pending` を拾うだけ)。P5 の起動順テストで留意
- `llm_timeout_seconds` は LLM クライアント構築側(実プロバイダ未実装)で使う設定で、P2b では未使用
- 実スレッドを使うテストは起動停止1件、同時実行の待ち確認(`test_source_locks.py`、0.2秒)、キューの待ち(`test_request_queue.py`)のみ。いずれも成功条件に時間を使わない
- U-31(実機)、`document_id`(先頭 `/` を除かない)の Crawler 側突き合わせは持ち越し
- **ユーザー確認が必要な点(未承認)**: 判断12(生成依頼を ID のみにした = module 4.3 からの逸脱)、判断17(`summary_input_max_chars` の追加)、判断8(文書固有拒否の連続20件打ち切りを Indexer に実装しない)。プラン §3 の「案に近い側に倒す」方針の範囲で進めたが、承認は未取得

## 次のアクション

1. P2 全体(P2a+P2b)を code-reviewer / test-reviewer で並列レビュー(比較基準 HEAD c065b9e)
2. 指摘対応後、P3(crawl_runs / lifecycle)へ
