# 0015 P5 実装: api・main・起動順

日付: 2026-11-12 / 実施: code-implementer(メインが検証を再実行) / プラン: 0002 §6 P5・0014
比較基準(P5 のレビュー用): HEAD c065b9e(`apps/indexer` は未コミットの新規ファイル全体)

## 実施内容の概要

(0) 0014 のユーザー判断(メンテナンスフラグの fail-closed 化)と、0013 の残り Suggestion(テスト・ログ・docstring)を先に反映し、(1) api 層(8 API + `/healthz`)、(2) main(依存の組み立て・lifespan・起動順・ログ設定)を実装した。Dockerfile・README・最終検証は P6。コミットはしていない。

## 検証結果(メインが再実行して一致を確認)

- `uv run pytest` → **1774 passed**(P4 後の 1328 から +446。3回連続で同数、約19秒)
- `uv run ruff check` → All checks passed
- `uv run ruff format --check` → 184 files already formatted
- `uv lock --check` → OK
- `apps/indexer` と `agent_tasks` 以外の変更なし(`.obsidian/workspace.json` は無関係の既存変更)
- 実装担当の確認: 一時スクリプトで実際の uvicorn + fake を起動し、healthz 200、DELETE のボディ付き要求、チャンク転送の上限超過が 400、停止後にスレッドが残らないことを確認済み(スクリプトはスクラッチパッドのみ)
- ミューテーション確認(スクラッチのコピー上で66件、**64件検出・2件生存**): 生存の1件(`_Body` の `strict=True` を外す)は `model_validate(..., strict=True)` との二重化による等価変異(両方外すと検出)。もう1件(`allow_inf_nan=False` を外す)は最初生存したが、ドメインの `StartNotification` が二重に拒否して 400 のままだったためで、`1e999` で message が `ratio_threshold (finite_number)` であることを確認するよう直して検出された

## 依存追加

- 本体: `fastapi>=0.115,<1`、`uvicorn>=0.32,<1`
- テスト用(dev グループ): **`httpx2>=2.16,<3`**。starlette の `TestClient` が `httpx` だと「`httpx2` を入れよ」という非推奨警告を出すため `httpx2` を選び、`httpx` 自体は入れていない。**メインの確認**: uv.lock の source は PyPI(`registry = "https://pypi.org/simple"`)、パッケージのメタデータの Homepage/Source は `https://github.com/pydantic/httpx2`(Pydantic 組織のリポジトリ)、Requires-Dist は anyio・httpcore2(==2.16.0)・idna・truststore。**本番イメージには含まれない**(dev グループ。`uv sync --no-dev`)。ただし通常の `httpx` ではなく見慣れないパッケージ名なので、**ユーザー確認事項として記録する**

## 変更・作成したファイル(`apps/indexer/` 配下)

先に直した分:
- `src/loreley_indexer/infrastructure/opensearch/jobs.py`: メンテナンスフラグの fail-closed 化(文書があり `enabled` が `False` と明示されたときだけ「立っていない」。それ以外は「立っている」とみなし、WARNING に record_id と項目名のみ)
- `crawl_runs/lifecycle/results.py`: 不正記録の WARNING をプロセスごと・記録 ID ごとに1回だけにした(以降 DEBUG)
- `crawl_runs/deletion/worker.py`: 復旧時の INFO ログ(連続失敗 n 回から復旧。値は出さない)
- `infrastructure/opensearch/connection.py`: 専用クライアントの docstring 修正
- テスト: `test_jobs_reader.py`(fail-closed の7形式+値非出力+正常時は無ログ)、削除は判定前・バッチ前、要約は生成前・書き込み前の各確認経路でフラグの不正値のテスト、S1(判定・再確認の基準時刻)・S3(本番配線)・S4(409後の進捗書き込み)・N1・N2・N3、警告1回・復旧ログのテスト。**TTL の追加条件は入れていない(ユーザー判断)。そのテストも足していない**

api 層(新規 `src/loreley_indexer/api/`): `app.py`(`create_api_app`)、`routes.py`(8 API + `/healthz`。同期 `def`)、`schemas.py`(strict な pydantic モデル)、`request_body.py`(Content-Length・ストリーム上限、JSON パース。NaN/Infinity 拒否)、`batch.py`・`raw_content.py`(件数・サイズ防御と base64 の長さからのサイズ推定)、`errors.py`(共通エラー形式・例外写像)、`responses.py`(結果型→JSON)、`middleware.py`(ready ゲート・アクセスログ・想定外例外の吸収)、`config.py`(`ApiConfig`)、`dependencies.py`(`ApiDependencies`)、`__init__.py`。api は `infrastructure` を直接 import していない
main・設定・ログ: `main.py`(依存の組み立て・lifespan・起動順・エントリポイント)、`common/log_setup.py`(`configure_logging`)、`config.py`(`Settings.api_config()`、`http_host`、`http_port`、`log_level`)、`pyproject.toml`・`uv.lock`
テスト(新規): `tests/api/{test_endpoints,test_validation,test_errors,test_logging,factories,stubs,conftest}.py`、`tests/test_main.py`、`tests/common/test_log_setup.py`。更新: `tests/test_config.py`、`tests/architecture/test_dependency_rules.py`
依存ルール許可表(`tests/architecture/dependency_rules.py`)の変更は2点: `config` から `api` への許可を追加(`ApiConfig` を `Settings.api_config()` で詰めるため。api は config に依存しないので循環なし)、外部ライブラリの所有表に `httpx2` を `httpx` と同じ扱いで追加

## 判断・設計上の理由(すべてユーザー未承認。プラン§3「案に近い側に倒す」の範囲)

| 論点 | 決めたこと | 理由 |
| --- | --- | --- |
| DELETE の `lock` | **JSON ボディ** `{"lock": {"owner","job_id"}}`(ソース削除2・3)。1 は `{"lock","reason"?}` | api 3.2 は運び方を決めておらず、4.6 の例がボディ形式。ヘッダ案は不採用。Crawler 側の HTTP クライアントは DELETE にボディを載せられる必要がある |
| 開始通知 | 200 `{"crawl_id","status":"running"}` | 4.1 の案 |
| 終了通知 | 202 ボディなし | 4.4 の案 |
| ソース削除1〜3 | `{"discarded_crawl_ids":[]}` / `{"deleted_count":n}` / `{"deleted":bool}`。`reason`(1)は任意で、あれば `source_deleted` のみ | 4.6〜4.8 |
| `skipped_count`(API-U-12) | **型だけ検証(非負整数)し、値は使わない。ID 一覧の件数との一致も検証しない** | ダイジェストは `skipped_count` を含まない(K25)。重複を除く数え方が設計書になく、不一致で job を落とすのは過剰 |
| 孤立サロゲート | `external_id`・`source_id`・`crawl_id`・`lock.*`・`content_hash`・日時・`raw_content` は API 層で 400。`title`・`mime_type`・`path`・`url` は API 層では通し、ドメインが文書単位 `document_rejected`(0008 A3) | pydantic の `str` は孤立サロゲートを拒否するため、この4項目だけ型確認のみの `LooseText` にした。1文書のファイル名のためにバッチ全体を 400 にすると、再送しても直らずジョブが止まる |
| ID の長さ上限(定数。設定化せず) | `source_id`・`crawl_id`・`lock.owner`・`lock.job_id`: **256バイト**(UTF-8)、`external_id`: **4096バイト**。`title`・`path`・`url`・`mime_type` は上限なし | `_id` 512バイト内(`deletion_result-` 接頭辞16+256=272)。`external_id` は仮値で、超過文書があると要求全体が 400 になる |
| 整数の型 | `ttl`・`min_delete_count` は int64 範囲の整数、`size`・`enumerated_count`・`skipped_count` は 0 以上 int64 | OpenSearch の long に収まる型の検証(意味の範囲は検証しない。確定事項どおり0や負値も通る) |
| `content_hash` | 64桁**小文字** hex の形式のみ検証(照合・再計算なし) | 案4。設計書は SHA-256 としか書いていないため、大文字を送る Crawler があると 400 になる |
| 上限超過の扱い | 件数・合計サイズ・ボディサイズは 400 `invalid_request`。1件が `max_raw_bytes` 超過の文書は 400 にせず、**デコードせず** `raw_content=b""`・`size=max(申告,推定)` でドメインへ渡し、ドメインが `failure_type=oversize` にする | 案1・案22 |
| `/healthz` と起動前 | `ready`(Event)が立つまで、**`/healthz` を含むすべてのパスが 503 `unavailable`(retryable)**。立つのは起動時の整理・ワーカー起動の後。本文は `{"status":"ok"}` のみ | 整理の完了前にリクエストが処理されないことの二重の防御 |
| 404/405 | 共通形式で `not_found`/`method_not_allowed` | 設計書に規定なし。形式を揃えるため |
| ドメインの `ValueError` | 400 `invalid_request`・固定文 "the request is invalid"(例外メッセージは使わない)。pydantic・パス検証は位置と型のみ(例 `ttl (int_type)`) | R9 |
| 想定外の例外 | `common.IndexerError` の写像で 500 `internal_error`(固定文)。middleware が吸収し**再送出しない**(スタックトレースに入力値が出るのを避ける)。ログにはクラス名のみ | R9 |
| `OpenSearchUnavailableError` | `UnavailableError` の子であることをテストで固定(503) | 指示どおり確認済み |
| 要約の起動失敗 | `summary_enabled` かつ LLM が `DisabledLlmClient` なら `StartupError`(固定文)。具体プロバイダが未実装のため、実運用の構成で要約を有効にすると常に起動失敗 | 指示どおり |
| 停止順 | 起動の逆順(要約→削除)。要約の起動失敗時は削除も止める | |
| ログ | uvicorn の `access_log=False`・`log_config=None`、自前のアクセスログ(メソッド・ルートのテンプレート・ステータス・msのみ。ルート外は `-`) | R9。ID を含む実パスは出さない |
| ログレベル | 追加設定 `log_level`(既定 INFO)。DEBUG でも `opensearch`・`opensearch.trace`・`urllib3` は WARNING 固定 | urllib3 が DEBUG でリクエストパス(ID)を出すため |
| pypdf のログ抑止 | **現状のまま**(`documents/extraction/pdf.py` の import 時の副作用)。`configure_logging` との整理はしていない | 任意項目。ルートのハンドラ置換では pypdf のレベルは変わらず矛盾しない |
| 追加設定 | `LORELEY_INDEXER_HTTP_HOST`(既定 `127.0.0.1`。コンテナでは `0.0.0.0` を指定)、`HTTP_PORT`(既定8000、1〜65535)、`LOG_LEVEL`(既定 INFO) | エントリポイントに必要 |

### 注意すべき点・設計書との差異
- **ログと `crawl_id`**: 依頼のログ検査は「`crawl_id` も全ログに出ない」だったが、P3/P4 の `crawl_runs` は案16(未知 `crawl_id` の終了通知)、削除の完了・失敗、不正記録の ID として `crawl_id` を意図して出している(ジョブ ID で本文でも秘密でもない)。api 層のログには一切出ない。テストは「api 層のログにはどのセンチネルも出ない」「通し経路では `crawl_id` だけが `crawl_runs` のロガーから出てよい」。`crawl_id` も完全に消すなら P3/P4 のログ文言の変更が別途必要
- 受理条件・通知の 409 はドメインのエラーをそのまま写像しており、設計書との矛盾は見つからなかった

## 設計書 ID・節とテストの対応(要旨)

api 1章 8 API の契約(4.1・K24・K37・D-94、バッチ 4.3・C-1・C-6・K30・案7・K45・案1・4.9・API-U-13、last-seen 4.2・K51、終了 4.4・K25・K32・K38・K7・P16、Status 4.5・K43・P25、ソース削除 4.6〜4.8・案8・K29)= `tests/api/test_endpoints.py` / 3.4 エラー表・共通形式 = `test_errors.py` / 受理条件5種の409(3.2・K23・D-77〜D-82)/ D-94(f)・案14(strict、範囲は検証しない)・案22・API-U-6/17(サイズ防御。巨大 base64 でデコード関数が呼ばれないこと)= `test_validation.py` / 起動順(完了条件9、module 5.6、arch 12章、D-93)= `tests/test_main.py`(整理→削除→要約の順、整理完了前は 503、再起動前の削除は再開されず `failed(indexer_restart)`、停止の逆順、起動失敗時の後始末、整理失敗でワーカーが始まらない、要約有効かつ未設定で `StartupError`)/ 案2(wake)・案19(同一 SourceLocks)・クライアント2つ = `test_main.py`・`test_endpoints.py` / ログ(完了条件10、R9)= `test_logging.py`(センチネル10種、正常・400・ドメイン `ValueError`・503・500、通し経路、DEBUG まで)・`test_log_setup.py` / 依存ルール R1〜R9 = `tests/architecture/`(api は infrastructure・config を import しない)/ fail-closed(0014)= `test_jobs_reader.py`・`test_decision.py`・`test_execution.py`・`test_processor.py`

## P6 への申し送り

- **起動方法**: `python -m loreley_indexer.main`(単一プロセス。`uvicorn.run(app, ...)` にアプリのオブジェクトを渡すため workers は増やさない。`--workers`・`--reload` は使わない)。Dockerfile の `CMD` もこれにそろえる
- **環境変数(`LORELEY_INDEXER_` 接頭辞)**: 環境変数のみ(`.env` なし)。必須は `OPENSEARCH_URL`。接続は `OPENSEARCH_USERNAME`・`OPENSEARCH_PASSWORD`(SecretStr)・`OPENSEARCH_VERIFY_CERTS`・`OPENSEARCH_CA_CERTS_PATH`、タイムアウト・再試行は `OS_REQUEST_TIMEOUT_SECONDS`・`OS_TRANSPORT_MAX_RETRIES`・`OS_DELETE_BY_QUERY_TIMEOUT_SECONDS`。P5 で追加: `HTTP_HOST`・`HTTP_PORT`・`LOG_LEVEL`。ほかのサイズ上限・削除・要約・再試行の仮値は `tests/test_config.py` の `PLANNED_DEFAULTS` と上限表を参照
- **README に書くこと**: 起動方法と環境変数、`HEALTHCHECK` は `/healthz`(整理完了前は 503、完了後 200)/ 起動手順(整理→削除→要約→受け付け)と、再起動前に受理した削除は再開されず `failed(indexer_restart)` になること / DELETE にボディ(`lock`)を載せる必要があること(Crawler 設計の確認事項)/ 要約を有効にすると LLM プロバイダ未実装のため起動に失敗すること / 追加した定数(ID の長さ上限256バイト、`external_id` の4096バイト、`content_hash` の小文字64桁。Crawler 側と突き合わせる)/ メンテナンスフラグは fail-closed(形式は Crawler 設計の確定時に再確認)/ 0013・0014 から決まっている事項: TTL の誤設定リスク、要約の再開遅延と先頭30,000文字の制限、判定時の `MalformedRecordError` が先頭を詰まらせる既知の制限(WARNING 監視)、巨大 HTML の処理時間(約40秒)
- Dockerfile は非 root、`uv sync --frozen --no-dev`(`httpx2` は dev グループ)。`docker build` は Docker が停止中のため持ち越しの見込み

## 未対応事項・持ち越し

- ユーザー未承認の点は上の判断一覧のとおり(DELETE の `lock` をボディにしたこと、孤立サロゲートの4項目だけをドメインに任せたこと、ID 長の仮値、`skipped_count` を検証しないこと、追加設定3つ、`/healthz` を含む起動前 503、`httpx2` の追加)
- 実 OpenSearch・実 LLM の接続テスト、U-31、Docker は未実施(範囲外)
- ログに `crawl_id` が出る件(上記)
- コミット未実施

## 次のアクション

P5 を code-reviewer / test-reviewer で並列レビュー(比較基準 HEAD c065b9e。対象は `api/`・`main.py`・`common/log_setup.py`・`config.py` の変更、`infrastructure/opensearch/jobs.py` の fail-closed 化と、起動順・ログ・API のテスト、パッケージ全体の依存ルール)。
