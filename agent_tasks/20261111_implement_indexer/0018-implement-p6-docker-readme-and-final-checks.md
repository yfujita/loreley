# 0018 P6 実装: Dockerfile・README・最終検証

日付: 2026-11-12 / 実施: code-implementer(メインが検証を再実行し、`docker build` と実イメージの確認をメインが実施) / プラン: 0002 §6 P6
比較基準(レビュー用): HEAD c065b9e(`apps/indexer` は未コミットの新規ファイル全体)

## 実施内容の概要

`apps/indexer/Dockerfile`(空ファイルから作成)、`.dockerignore`、`README.md`(約275行)を作成し、最終検証を行った。`src`・`tests` の機能変更はしていない。コミットはしていない。

## 検証結果(メインが再実行して一致を確認)

- `uv run pytest` → **2083 passed**(実装担当は3回: 29.54s・29.84s・27.89s、メインは27.11s)
- `uv run ruff check` → All checks passed
- `uv run ruff format --check` → 190 files already formatted(0017 の189との差は、`pyproject.toml` を含む数え方の差。`.py` の追加はなし)
- `uv lock --check` → Resolved 43 packages(一致)
- 変更範囲は `apps/indexer` の Dockerfile・.dockerignore・README のみ(`agent_tasks` と無関係の `.obsidian/workspace.json` 以外に変更なし)

## docker build と実イメージの確認(完了条件12。メインが実施)

実装担当は Docker デーモン停止中(`docker info` 失敗)のため未実施と報告したが、メインの確認時点ではデーモンが起動していた(Docker 20.10.13、linux/amd64)。ローカルビルドのみを実施した(イメージ名 `loreley-indexer:p6-check`。ベースイメージの取得とローカルのイメージ作成以外の外部操作なし)。

- `docker build -t loreley-indexer:p6-check apps/indexer` → **成功**(約24秒、イメージサイズ 190MB)
- 非 root: `uid=10001(indexer) gid=10001(indexer)`。`/app` への書き込みは `Permission denied`(読み取り専用)
- イメージの中身: `uv` なし。`pytest`・`httpx2`・`ruff` なし(`--no-dev` が効いている)。`fastapi`・`uvicorn`・`loreley_indexer` あり
- HEALTHCHECK: `interval=15s`・`timeout=5s`・`start-period=120s`・`retries=3`、urllib の1行コマンド(ポートは `LORELEY_INDEXER_HTTP_PORT` に追従、プロキシ無効)
- ENV に秘密値なし(`LORELEY_INDEXER_HTTP_HOST=0.0.0.0`、`PYTHONPATH=/app/src` など)
- OpenSearch URL 未設定での起動 → 設定エラーで停止(想定どおり)
- **発見した問題(R9 違反)**: URL 未設定のとき、pydantic の `ValidationError` の `input_value` に環境変数の入力辞書が出る。`LORELEY_INDEXER_OPENSEARCH_PASSWORD=SENTINEL-SECRET-PW` を設定して URL を省くと、標準エラー出力に `input_value={'http_host': '0.0.0.0', ...': 'SENTINEL-SECRET-PW'}` としてパスワードが出た(コンテナ起動で再現)。`Settings` の `SecretStr` は、検証エラーが入力の生の辞書を出すため効かない。範囲外の値(`HTTP_PORT=0`)では `input_value='0'` のみで URL のパスワードは出なかった。→ 修正を依頼(下記)
- 実際のコンテナ起動(OpenSearch への接続を伴う `/healthz` 200、SIGTERM の停止)は、OpenSearch が無いため未確認。実装担当がローカル(Docker なし)で、空ヒットを返す stdlib の偽 OpenSearch に対して `env -i` の最小環境で起動し、起動時の整理→ready→`/healthz` 200、HEALTHCHECK と同じ python ワンライナーの成否、SIGTERM での停止処理(終了コード143)を確認済み

## 変更・作成したファイル(`apps/indexer/` 配下)

- `Dockerfile`: マルチステージ。builder で `pip install uv==0.13.7` → `uv sync --frozen --no-dev --no-install-project` → `compileall`。runtime は `python:3.12.11-slim-bookworm` に `/app/.venv` と `/app/src` だけをコピー。非 root(uid/gid 10001、ホームなし、nologin)。`PYTHONPATH=/app/src`。`EXPOSE 8000`。`HEALTHCHECK`。`CMD ["python","-m","loreley_indexer.main"]`(単一プロセス)
- `.dockerignore`: `.venv`・`**/__pycache__`・`**/*.py[cod]`・各種キャッシュ・`tests/`・`README.md`・`.git`・`Dockerfile`・`.dockerignore`・`.env*`・`*.pem`・`*.key`
- `README.md`: 概要 / 起動方法(ローカル・Docker・開発)/ 設定(44項目、`config.py` から機械的に抽出して既定値・上限を照合)/ API / 起動・停止の挙動 / Crawler 向け契約 / 要約 / メンテナンス(指示にない追加。arch 11・4.3 に基づく) / 既知の制限 / テスト方針

## 判断・設計上の理由(いずれもユーザー未承認)

- uv は `pip install uv==0.13.7`(builder のみ): 実際に動かした版をそのまま固定でき、ベースイメージと同じ取得元(PyPI)だけで済む。公式イメージ(`ghcr.io/astral-sh/uv`)はタグの存在をオフラインで確認できなかった
- ベースイメージ `python:3.12.11-slim-bookworm`: pyenv の 3.12.11(テスト実行と同じ版)に合わせた。digest 固定はしていない(セキュリティ更新の取り込みと引き換え)。alpine(musl)は wheel の種類が変わるため避けた
- アプリ本体は非 editable のパッケージとして入れず `PYTHONPATH=/app/src` で参照: `pyproject.toml` の `[build-system] requires=["hatchling"]` が無固定で `uv.lock` に載らず、project install するとビルド時に PyPI から未固定のバックエンドを取得してしまうため。この方式なら入るものはすべて `uv.lock` のハッシュ付き
- HEALTHCHECK の `start-period=120s`: `/healthz` は起動時の整理が終わるまで 503 で、uvicorn は lifespan 完了まで接続自体を受け付けない。整理は OpenSearch への読み書きで、1リクエスト最大30秒×再試行2回(既定)を待ちうるので、それを上回る値にした。curl は slim にないので標準ライブラリ urllib
- `--frozen` は lock の鮮度を検証しない: ビルド前に `uv lock --check` を行う運用をコメントと README に記載
- 停止猶予は README に「30秒以上」と記載: 削除ワーカー・要約ワーカーの `stop()` がそれぞれ最大10秒 join する(コード確認済み)ため、Docker の既定10秒では足りないことがある

## 完了条件1〜13(0001)との対応

| # | 根拠 |
| --- | --- |
| 1 依存ルール R1〜R9 | `tests/architecture/test_dependency_rules.py`(import を AST で検査)、`test_write_rules.py`(R7)。R6・R7・R8 は部分検査 |
| 2 8 API・400・共通エラー | `tests/api/test_endpoints.py`・`test_errors.py`・`test_validation.py` |
| 3 登録 | `tests/documents/test_registration.py`・`test_registration_conflicts.py`・`test_registration_config.py` |
| 4 `last-seen` | `tests/documents/test_last_seen.py` |
| 5 抽出 | `tests/documents/extraction/test_extractor.py`・`test_normalization.py`・`test_decoding.py` |
| 6 `crawl_runs` | `tests/crawl_runs/lifecycle/*` |
| 7 削除 | `tests/crawl_runs/deletion/*` |
| 8 要約 | `tests/documents/summarization/*` |
| 9 起動順序 | `tests/test_main.py`(整理→削除→要約の順、整理完了前は 503、再起動前の削除は再開されない) |
| 10 ログ | `tests/api/test_logging.py`・`tests/common/test_log_masking.py`・`test_log_setup.py`・`tests/infrastructure/opensearch/test_log_leak.py`(実クライアント+ローカル HTTP スタブ)。**ただし起動時の設定読み込みエラー(上記の発見)はカバーされていなかった → 修正中** |
| 11 pytest/ruff | 上記の結果のとおり全て成功 |
| 12 docker build | **実施済み(成功)**。イメージの非 root・依存・HEALTHCHECK を確認。OpenSearch に接続しての実コンテナ起動は未確認(OpenSearch が無い) |
| 13 一覧の記録 | 本記録の仮値一覧・採用判断の一覧・持ち越し一覧 |

## 仮値一覧(`config.py` から機械的に抽出。既定 / 上限、根拠 ID)

| 設定名 | 既定 | 上限 | 根拠 |
| --- | --- | --- | --- |
| `max_raw_bytes` | 20 MiB | 100 MiB | U-3・U-5・15.4 |
| `max_batch_documents` | 50 | 500 | U-3・API-U-6 |
| `max_batch_bytes` | 64 MiB | 256 MiB | U-3 |
| `max_request_body_bytes` | 100 MiB | 512 MiB | U-3・API-U-17 |
| `max_content_bytes` | 5 MiB | 50 MiB | U-8・15.2 |
| `max_last_seen_ids` | 1,000 | 10,000 | API-U-7 |
| `write_conflict_max_rereads` | 3 | 10 | U-31(4)・R8 |
| `update_retry_on_conflict` | 3 | 10 | U-31(3) |
| `delete_by_query_max_reruns` | 5 | 20 | K48・U-31(5) |
| `retry_backoff_initial_seconds` | 1.0 | 60 | 4.4 |
| `retry_backoff_factor` | 2.0 | 10 | 4.4 |
| `retry_backoff_max_seconds` | 30.0 | 300 | 4.4 |
| `skip_oversize_id_limit` | 10,000 | 100,000 | K34・U-2・API-U-5 |
| `deletion_batch_size` | 100 | 1,000 | U-2 |
| `deletion_retention_count` | 20 | 1,000 | U-2 |
| `max_deletion_targets` | 200,000 | 2,000,000 | K47・15.4 |
| `search_after_page_size` | 1,000 | 10,000 | 9.8 |
| `deletion_poll_interval_seconds` | 2.0 | 60 | U-14 |
| `delete_error_retry_attempts` | 3 | 10 | 4.4 |
| `discard_max_attempts` | 20 | 100 | P7・P29 |
| `summary_enabled` | false | - | 7.1 |
| `summary_concurrency` | 1 | 8 | K49 |
| `summary_max_attempts` | 3 | 10 | 7.4 |
| `summary_queue_size` | 100 | 10,000 | K39 |
| `summary_rescan_page_size` | 100 | 1,000 | 7.4 |
| `summary_rescan_min_interval_seconds` | 60.0 | 3,600 | P15 |
| `llm_timeout_seconds` | 60.0 | 600 | 7.1 |
| `os_request_timeout_seconds` | 30.0 | 300 | U-3 |
| `os_transport_max_retries` | 2 | 5 | 4.4 |

0014 で表に追加した4件:

| 設定名 | 既定 | 上限 | 根拠 | 承認 |
| --- | --- | --- | --- | --- |
| `summary_rescan_max_interval_seconds` | 3,600 | 86,400 | 案12 更新・K54(3) | 0014 でユーザー承認 |
| `deletion_poll_backoff_max_seconds` | 300 | 3,600 | arch 9.9・0012 | **未承認** |
| `os_delete_by_query_timeout_seconds` | 600 | 3,600 | arch 4.4・U-3 | **未承認** |
| `summary_input_max_chars` | 30,000 | 1,000,000 | K39・0007 | **未承認** |

- 0002 §4 の全行と 0014 の追加4件は `config.py` に存在し、既定値・上限が一致(§4 の `retry_backoff_*` の「固定上限あり」は 60/10/300)
- §4・0014 にない config の項目: P5 の `http_host`(127.0.0.1)・`http_port`(8000、1〜65,535)・`log_level`(INFO)(設計書に規定なし。0015 に記録済み)、接続設定(`opensearch_*`)、索引名3つ(§3.1 の仮名)
- 整合検証4件: `rescan max ≥ min` と `poll_backoff_max ≥ interval`(0014 に記載)、`max_raw ≤ max_batch` と `max_batch×4 ≤ max_request_body×3`(0016 で追加。**未承認**)
- 設定外の定数: ID の長さ上限(`source_id`・`crawl_id`・`lock.*` 256バイト、`external_id` 4096バイト)、`LIST_MAX_SIZE` 10,000、TTL の丸め ±約100年(`MAX_TTL_SECONDS`)、ワーカー停止の join 10秒、Content-Length の桁数上限 20、検証エラー報告の上限 10件

## 設計書の「案」を採用した判断の一覧

### プラン §3 の22項目(2026-11-11 にユーザーが「全て案どおり承認」)
原本サイズ超過の拒否(`oversize`)、削除ワーカーの走査型+起床通知、起動時整理の対象、`content_hash` を照合しない、ロック失敗時の部分結果、`last-seen` の要請単位、`fetched_at`/`metadata` の無視、ソース削除2・3のロック確認(1は確認しない)、同期クライアント、T>D ガード、メンテナンスフラグの確認箇所、要約の失敗・再試行、抽出・正規化の規則、開始通知の型(範囲は検証しない)、エラー名と HTTP、未知 `crawl_id` の終了通知は 202、`waiting_for` と 404、`deleted_count` の進捗更新、ソース単位の直列化、`common/` の新設、`/healthz`、上限超過は 400
0014(2026-11-12)でユーザーが承認した3件: TTL の追加条件は入れない、メンテナンスフラグは fail-closed、要約の再走査の方針変更(案12→指数バックオフの永続再走査)

### ユーザー未承認の判断(P1〜P6 の記録を集約。完了報告時にユーザーへ確認する)
- **P1(0003〜0005)**: 全体異常は戻り値でなく例外 `OpenSearchUnavailableError`、401/403 は全体異常、`Rejected` は reason を保持しない、`last_seen_at` は固定 painless スクリプト+params で upsert しない、依存ルール R6〜R8 は部分検査のみ
- **P2(0006〜0008)**: `document_id` は先頭 `/` を除去しない(0006 判断1をメインが修正)、失敗種別の仮名と `DeletionReason` の値、レコードに `crawl_id`・`reason_detail`・`started_at`/`ended_at` を追加、正規化でサロゲートを除去、受理条件の `crawl_started_at` はミリ秒に正規化して比較、**0007 判断8**(文書固有拒否の連続20件打ち切りを Indexer に実装しない)、**0007 判断12**(要約の生成依頼を文書 ID のみにした=module 4.3 からの逸脱)、**0007 判断17**(`summary_input_max_chars` を追加)、0008 の6項目(メタデータ検査に `mime_type` を含める、`DOCUMENT_REJECTED` の基本メッセージ変更、検査順 oversize→メタデータ→抽出、PDF 打ち切りは正規化後の長さで判定、`should_stop` の追加、`summary_rescan_max_interval_seconds`(0014 で承認済み))
- **P3(0010)判断1〜15**: 開始通知の書き込み順を「世代→superseded化→結果作成」にした(設計書の記述順と異なる)、受理の409が上限超過なら `UnavailableError("write_conflict")`、`SourceLocks` を common へ移動、ID 一覧の件数とフラグを上限以内でも記録、`failed`/`cancelled` はダイジェストのみ保存、`crawl_id`/`source_id` の空文字拒否、`finished_at` は保存・比較しない
- **P4(0011)判断1〜18**: `os_delete_by_query_timeout_seconds`、専用クライアント `delete_by_query_client`(`retry_on_timeout=False`)、`LockInfo` を common へ移動、削除専用排他 `SourceBatchExclusion`、TTL 再確認に `source_id` 一致を追加、ソース削除2は再実行ごとにロック所有を再確認、`discard_max_attempts` は試行ラウンド数、`delete_error_retry_attempts` は初回を含む総試行回数、判定フェーズの全体異常は `running` のまま再実行(上限なし)
- **P3+P4 レビュー対応(0012)**: `deletion_poll_backoff_max_seconds` とバックオフの挙動、`SearchIndexRepository.fetch_for_deletion` の追加、`progress_update` は `deleted_count` を減らさない、再起動整理で未記録の `deleted_count` に0を付ける、不正記録は list から除外しログのみ(先行扱いされなくなる)。見送り: 連続失敗で `failed` にする案、先頭失敗時に次のソースへ進む案
- **P5(0015)**: DELETE の `lock` を JSON ボディで受ける、`skipped_count` は型のみ検証し値を使わない、孤立サロゲートの分担(`title`/`mime_type`/`path`/`url` は文書単位 `document_rejected`、他は全体400)、ID 長の上限(256/4096バイト)、`content_hash` は小文字64桁 hex のみ、起動前は `/healthz` を含め全パス 503、追加設定 `HTTP_HOST`・`HTTP_PORT`・`LOG_LEVEL`、404/405 を共通形式で返す、ドメインの `ValueError` は400の固定文、想定外の例外は500で再送出しない、`fastapi`・`uvicorn` の追加、**dev 依存 `httpx2`**(PyPI の Pydantic 組織のリポジトリ。通常の `httpx` ではなく見慣れない名前なので要確認。code-reviewer が PyPI で確認済み。本番イメージには含まれない)
- **P5 レビュー対応(0016・0017)**: opensearch/opensearchpy/urllib3 のロガーを ERROR 固定、ログ文言の変更(診断情報 `origin` の追加)、`Settings` のサイズ整合検証、`source_id`・`crawl_id`・`lock.*`・パス ID の制御文字拒否、`UnexpectedResponseError` 基底クラスと `close_clients` の新設、`ClientDisconnect` は 400、Content-Length の20桁超は 400。**撤回済み**: `ignore=404`(0017)、`external_id` の制御文字拒否(0017)。見送り: 専用例外 `InvalidInputError`
- **P6(本作業)**: uv は pip で固定、アプリ本体は `PYTHONPATH` 参照、HEALTHCHECK の値、uid 10001、停止猶予30秒の推奨、README にメンテナンスの章を入れたこと

## 持ち越し一覧

- **U-31(実 OpenSearch での確認)**: `_seq_no` による楽観ロックと存在しない文書への `if_seq_no` 付き操作の応答、`delete_by_query` の競合・`version_conflicts`・タイムアウトの再送抑止、`search_after` と `document_id` のソート、painless の max 比較と `Instant` のパース(fake は実機より寛容な可能性)、`retry_on_conflict`、`_reindex`、refresh の挙動(シャード部分失敗の応答形、`_count` が古いまま0になる可能性)、404 の本文の形(特に `update`)、D-86(PIT なし取得)、fake と実アダプタの契約一致テスト
- 実コンテナでの OpenSearch 接続を伴う起動・`/healthz`、実 uvicorn 経由の `ClientDisconnect`、実 LLM、実 Crawler との接続
- **Crawler との突き合わせ**: `document_id` の先頭 `/` を除去しない点、`content_hash` が小文字 hex か、DELETE にボディを載せられるか、ファイル名由来の孤立サロゲートの扱い、ID 長の上限、ロック文書・メンテナンスフラグの形式(fail-closed)、索引名、マッピング前提(`document_id` のソート、`record_type`・`status` の keyword 前提)
- docs への新設定(`summary_input_max_chars`、`summary_rescan_max_interval_seconds`、`deletion_poll_backoff_max_seconds`、`os_delete_by_query_timeout_seconds`、`HTTP_*`、`LOG_LEVEL`)の反映(`apps/indexer` 以外は変更しない方針のため未実施)
- その他: 日本語 PDF の抽出品質は未検証、判定時の `MalformedRecordError` が先頭を詰まらせる件、同一 `crawl_id` を別 `source_id` で同時に開始通知した場合の競合、メンテナンスフラグ不正 WARNING の再武装、`SEARCH_INDEX_CALLS`/`STORE_CALLS` の共有化、要約の `failed` 遷移と有効化後の既存文書の一括生成(未実装)
- コミット未実施

## 実装担当が報告した src の気づき(変更していない)

1. `api/schemas.py` の docstring(12行目)に、通常の(非 raw)文字列として `\ud800` が書かれている。孤立サロゲートが docstring の定数に入る。Python 3.13 で `compileall` が `UnicodeEncodeError` で失敗した。プロジェクトは `==3.12.*` に固定で 3.12.11 では成功するので現状は問題ない。raw docstring か `\\ud800` にすると堅くなる
2. `pyproject.toml` の `[build-system] requires=["hatchling"]` が無固定。Dockerfile は project install をしないため影響しない
3. `uv sync --frozen` の代わりに `--locked` にすると、lock が古い場合にビルドが失敗する(再現性は高まる)。指示は `--frozen` なのでそれに従った
4. README には `docker build` が未実施である旨を「テスト方針」の最後に一文だけ記載している。**メインが `docker build` を実施して成功したため、記載を「実施済み」に直す必要がある**(次の修正で対応)

## 次のアクション

1. 修正(code-implementer): 起動時の設定読み込みエラーで秘密値が標準エラー出力に出る問題(R9)の修正と、テスト・README の更新(`docker build` 実施済みへの修正、`api/schemas.py` の docstring)
2. レビュー(並列): code-reviewer(`Dockerfile`・`.dockerignore`)、document-reviewer(`README.md`・作業記録)
3. タスクレビュー(task-reviewer)。完了報告前にユーザーへ未承認事項を確認する
4. 確認用に作成した Docker イメージ `loreley-indexer:p6-check` は、レビュー完了後に削除する
