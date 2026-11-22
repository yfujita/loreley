# 0005 P1: 基盤・`common`・依存ルール検査

日付: 2026-11-13 / 実施: code-implementer / 記録・再検証: メインエージェント
フェーズ開始時点の HEAD: `061dc7b196f67a689e0d834eb676ce356d6cdb34`(`apps/crawler/` は未コミット)

## 1. 実施内容

`apps/crawler/` を新規作成した(既存ファイルの変更なし)。

- 設定: `pyproject.toml`(`loreley-crawler`。本番依存 fastapi・uvicorn・pydantic・pydantic-settings・opensearch-py、dev 依存 httpx2・pytest・ruff。Indexer と同じ ruff・pytest 設定)、`uv.lock`、`.python-version`(3.12)、`.gitignore`、`.dockerignore`
- `src/loreley_crawler/`: module-structure v0.4 3章のディレクトリをすべて docstring のみの `__init__.py` で作成(api、scheduler、sources、jobs(records・locks)、crawl、source_delete、documents、connectors(interface・filesystem)、infrastructure(opensearch・indexer_client))
- `common/`: `clock.py`(`Clock`・`SystemClock`)、`timestamps.py`(`format_instant`: UTC・ミリ秒・切り捨て、naive は `ValueError`)、`retry.py`(`RetryPolicy`・`wait_with_checkpoint`・`run_with_retry`)、`display_text.py`、`log_masking.py`・`log_setup.py`(Indexer から移植。R9 を R11 に直した)、`errors.py`(`CrawlerError`・`StoreUnavailableError(reason)`・`IndexerUnavailableError(reason)`)
- `config.py`: 起動時整合性検査の純粋関数 `check_size_limits(CrawlerSizeLimits, IndexerLimits) -> LimitCheckResult`(違反の一覧+未設定のため省略した項目名)。環境変数は読まない
- `tests/`: `conftest.py`、`fakes/clock.py`(`FixedClock`)、`common/` の単体テスト、`test_config.py`(architecture 12章 #39 の単体部分)、`architecture/`(`dependency_rules.py`、`test_dependency_rules.py`(R1〜R6・R10)、`test_write_rules.py`(R7 の部分検査))

## 2. 決めてよい事項で決めた内容(0002 §4.1)

- **CM-U-9 仮置き(a)**: Indexer の上限が未設定なら `unchecked_limits` に項目名を入れて返し、その項目の検査だけ省略。警告の出力は呼び出し側(P8)。環境変数名は P8 で決める。
- **検査の項目名**: `max_raw_bytes`、`batch_max_documents`、`batch_max_raw_bytes`、`last_seen_max_ids`、`finish_id_list_warning_threshold`、`batch_max_raw_bytes_in_base64`。自分の値どうしの検査(`max_raw_bytes` ≤ `batch_max_raw_bytes`)は Indexer の値に依存せず常に行う。「4/3倍」は `ceil(4n/3)`(Indexer `config.py` の `4n > 3L` と同値。境界値テスト済み)。
- **リトライ**: 回数・間隔の既定値は `common` に持たせず config から渡す。ジッタは待ち時間を最大 `jitter_ratio` の割合だけ短くする方式(0で無し)。`max_backoff_seconds` は超えない。乱数元を差し替え可能。確認点は各試行の前と、待ちの `slice_seconds`(既定1秒)ごと。例外・結果の両方をリトライ判定でき(`is_retryable_error` / `is_retryable_result`)、結果が尽きたら最後の結果を返し、例外が尽きたら最後の例外を送出。`BaseException` はリトライしない。時計は retry では使わない(待ちを分割して数える)。
- **表示用整形**: 順序は「孤立サロゲート→U+FFFD」「制御文字(Cc)のエスケープ」「切り詰め」。切り詰めはエスケープ後に数え `max_chars` 以内、エスケープ列の途中では切らない。エスケープは `\n`・`\r`・`\t`、他は `\xNN`。`external_id` 用の ID エスケープは `documents`(P3)の担当。
- **共有エラー型**: 設計書に具体名がないため最小限。P2 で Repository・`indexer_client` の結果の作りに合わせて調整してよい。
- **依存ルール表(`ALLOWED`)**: R3 の9本の辺を集合として固定。`documents` は `connectors.interface` のみ、`sources`・`crawl` は `connectors` と `connectors.interface` を許可。`connectors` 内部は 直下→filesystem→interface。MVP では `connectors` から `infrastructure` を許可しない。`config` は各モジュールの入口のみ、`main` は全モジュール(Composition Root)。R2 の外部ライブラリ: `opensearchpy` は `opensearch` のみ。`urllib3`・`httpx`・`httpx2`・`requests`・`aiohttp` は `opensearch` と `indexer_client`(HTTP クライアントの選定自体は P2)。
- **R7 の部分検査**: クライアントの書き込み呼び出しは `infrastructure/opensearch/` 内のみ。`loreley-documents`・`loreley-deletions` を docstring 以外の文字列定数として使わない。Repository の書き込み範囲(sources だけが loreley-sources、jobs だけが loreley-jobs)、版条件つき更新、main が作る Repository の数は未検査(P2・P4 で足す。`test_write_rules.py` の docstring に明記)。

設計書との食い違いはない。設計書に明記がなく補った点: 日時は書式 `format_instant` のみ(`parse_instant` は設計書の common の責務にないため足していない。P4 で必要なら足す)。`main.py` は P8。

## 3. 検証結果(メインが再実行して確認、`apps/crawler`)

```
$ uv run pytest -q
335 passed in 0.93s
$ uv run ruff check
All checks passed!
$ uv run ruff format --check
42 files already formatted
```

実装担当の報告: 依存ルール検査は、テスト内で実ツリーに違反の偽ファイルを足すと失敗する(api→crawl、common→jobs、connectors/filesystem→opensearchpy、jobs/records のクライアント書き込み、sources が loreley-deletions を指す)。手動でも違反ファイルを置いて4件失敗するのを確認し、削除した。スキップしたテストはない。

## 4. レビュー

P1 単独のレビューは行わない(0002 §6 のとおり P2 完了後に P1+P2 をまとめて code + test レビュー)。

## 5. 未対応事項・次のアクション

- 未対応(後続フェーズ): `/healthz`(P8)、環境変数の読み込みと設定エラー送出(P8)、R7 の Repository 範囲の検査(P2・P4)、Dockerfile・README(P9)。
- ログ用 `RESTRICTED_LOGGER_NAMES` は opensearch-py と urllib3 のみ。`indexer_client` が選ぶライブラリのロガーも P2 で確認する。
- 次: P2(infrastructure・fakes。最初に Indexer 契約表。HTTP クライアント選定)。
