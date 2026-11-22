# 0003 P1 実装: 基盤・infrastructure

日付: 2026-11-11 / 実施: code-implementer(メインが検証を再実行) / プラン: 0002 §6 P1
比較基準(レビュー用): HEAD c065b9e。`apps/indexer` は新規作成のためファイル全体が対象

## 実施内容の概要

プロジェクト雛形、設定、`common/`、`infrastructure/opensearch`(Repositoryインターフェース・結果区分・実アダプタ・例外分類)、`infrastructure/llm`(インターフェースと無効な既定実装)、テスト用fake、依存ルールテストを作成した。コミットはしていない。

## 検証結果(メインが再実行して一致を確認)

- `uv run pytest` → 253 passed
- `uv run ruff check` → All checks passed!
- `uv run ruff format --check` → 53 files already formatted
- 依存ルールテストの検査器: 違反ファイルを一時的に置くと失敗し、削除後に通ることを実装担当が確認済み
- 実行環境: UV_PYTHON=/Users/yfujita/.pyenv/versions/3.12.11/bin/python、uv はスクラッチパッドのvenvに導入した0.13.7

## 変更・作成したファイル(`apps/indexer/` 配下、すべて新規)

- 設定: `pyproject.toml`(Python >=3.12,<3.13、hatchling、ruff、pytest。依存は opensearch-py 3.2 / pydantic 2.14 / pydantic-settings 2.16)、`.python-version`、`uv.lock`、`.gitignore`
- `src/loreley_indexer/config.py`: 環境変数 `LORELEY_INDEXER_*`、プラン§4の仮値を ge/le で検証。`opensearch_url` は必須
- `src/loreley_indexer/common/`: `errors.py`、`clock.py`、`timestamps.py`、`locks.py`、`log_masking.py`
- `src/loreley_indexer/infrastructure/opensearch/`: `results.py`、`errors.py`、`classification.py`、`queries.py`、`search_index.py`、`store.py`、`jobs.py`、`connection.py`、`search_index_adapter.py`、`store_adapter.py`、`client_calls.py`、`__init__.py`
- `src/loreley_indexer/infrastructure/llm/`: `client.py`、`__init__.py`
- `tests/`: `fakes/`(clock, gate, behavior, in_memory_search_index, in_memory_store, llm)、`conftest.py`、`common/`、`test_config.py`、`infrastructure/{opensearch,llm,test_fake_utilities.py}`、`architecture/{dependency_rules.py,test_dependency_rules.py}`

## 判断・設計上の理由

- 全体異常は戻り値でなく例外 `OpenSearchUnavailableError`(api層で503 `unavailable`)。接続エラー・タイムアウト・429・5xx・`cluster_block_exception`・`circuit_breaking_exception`・`index_not_found_exception`。409は`Conflict`、404(`document_missing_exception`等)は`NotFound`、その他4xxは`Rejected`
- `Rejected` は OpenSearch の reason を保持しない(文書内容が入りうるため)。例外連鎖は `from None`
- 読み取り・検索系での想定外応答は `OpenSearchUnexpectedResponseError`(api層で500想定)
- モジュール用の設定dataclassは各モジュール側に置き、`config.py`が変換(module 3章「モジュールは config.py に依存しない」)。P1では `OpenSearchConnectionConfig` と `IndexNames` のみ。他は各フェーズで追加
- 仮定義の隔離: インデックス名の既定値は `connection.py` の1か所、ロック・メンテナンスフラグ形式は `jobs.py` と `common/locks.py`
- `loreley-jobs` は `StoreReader` のみを受け取る `StoreJobsReader`(読み取り専用、R6)。不正なロック文書は「所有していない」に倒す
- `last_seen_at` は固定のpainlessスクリプト+paramsでmax比較(現在値より新しいときのみ書く、それ以外は `ctx.op='none'`)。upsertしない。`retry_on_conflict` はコンストラクタで受ける
- `delete_by_query` は `source_id` 必須、`conflicts="proceed"`
- `search_document_ids` は `document_id` 昇順の `search_after`(ID のみ)。`count_existing_ids` は ids クエリを1000件ずつ分割して合算。Store の `list_records` は毎回 refresh、`limit` は 1〜10,000 必須
- スキップ文書除外はアダプタに入れず呼び出し側(P4)がメモリ上で除外
- 無効なLLMは呼ぶと `LlmDisabledError`、失敗種別は戻り値 `LlmFailure`
- fake: `InMemorySearchIndex`(`_seq_no`模擬、`fetch`はリアルタイム、search/count/delete_by_queryはrefresh後のスナップショット、`refresh_stalled`、`delete_by_query`の`version_conflicts`模擬、存在しない文書への条件付き操作の応答は引数で切替)、`InMemoryStore`、`FakeLlmClient`、`behavior.before`(割り込みフック)・`behavior.inject`(応答差し替え)、`Gate`

## プランからの逸脱・補足

- 依存はP1で使う3つのみ。fastapi/uvicorn/bs4/lxml/pypdf/httpx は各フェーズで `uv add`(lock再生成)
- `apps/indexer/.gitignore` を新設(.venv等。ルートの.gitignoreにはなかった)
- 依存ルールテストは import で検査できる範囲のみ(R1〜R5、R9のllm限定、R2のライブラリ限定、common は葉、config は main のみ)。**R6・R7・R8 は機械的には担保していない**(レビューおよび各フェーズのテストで確認する)
- 許可表: `documents`→`crawl_runs` は `crawl_runs` と `crawl_runs.lifecycle` のみ(deletion不可)。`documents`直下はllm不可。`api`はinfrastructure不可

## 未決・仮定に倒した内容(プラン§3/§3.1に沿う追加分)

- 仮定義(実機未確認): インデックス名 `loreley-documents`/`loreley-deletions`/`loreley-jobs`、ロック文書 `lock-{source_id}`(owner/job_id/lease_expires_at)、メンテナンスフラグ(ID `maintenance`、`enabled`)、ソートキー `document_id`、`record_type`・`status` は keyword 前提

## 未対応事項・持ち越し

- U-31の実機確認(painlessのmax比較、`delete_by_query`競合、`search_after`、存在しない文書への`if_seq_no`付き操作の応答、`retry_on_conflict`)。アダプタはリクエスト形のみテスト
- R6・R7・R8 の機械的検査なし(上記)
- `common/errors.py` に契約エラー(409 `crawl_not_started` など)は未定義。P2/P3で必要分を追加
- コミット未実施

## 次のアクション(P2への申し送り)

- fake は `tests.fakes.*`、fixtureは `conftest.py`(`search_index` / `deletions_store` / `jobs_store` / `clock` / `llm`)。`seed()`はフック・呼び出し記録を通らない。「1件も書かない」確認は `write_calls()`
- 競合再現: `search_index.behavior.before(ops.REPLACE, cb)`(GETとPUTの間に差し込み)、`behavior.inject(ops.REPLACE, Conflict(), times=3)`(409連続)
- 検索系(`search_document_ids`/`count`/`count_existing_ids`)は `refresh()` まで反映されない。`delete_by_query` の前に `refresh()` を呼ぶ(arch 9.14)
- 要約の完了待ちは `FakeLlmClient(on_generate=callback)` / `Gate().pass_through`
- 依存を追加したら `uv add`。依存ルールの許可表(`tests/architecture/dependency_rules.py` の `ALLOWED`)を変更する場合は根拠を作業記録に残す
- 次: P1のレビュー(code-reviewer / test-reviewer)
