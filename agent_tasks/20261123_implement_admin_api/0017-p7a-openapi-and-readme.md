# 0017 P7a・README: OpenAPI の宣言と公開配線・`openapi_export.py`・結合テスト・`tzdata`・README

日付: 2026-11-24

## 実施内容

並行して 2 つを実施した(触るファイルは分離)。
- `code-implementer`(P7a): OpenAPI の宣言と公開配線・`openapi_export.py`・`server/` の結合テスト・`tzdata` の直接依存化・`ClientDisconnect` の扱い
- `document-writer`: `apps/api/README.md` の全面更新

メインエージェントが検証を再実行し、README の第 6 章を実装と突き合わせた。手動スモークは次の作業記録で扱う。

## 検証(メインエージェントが再実行、`apps/api`)

- `uv run pytest`: 3389 passed(0016 時点 3246)/ `uv run ruff check`: All checks passed / `uv run ruff format --check`: 249 files already formatted / `uv lock --check`: OK
- `apps/api` 以外に差分なし。起動プロセスの残りなし。実 Crawler・実 OpenSearch・実ネットワークには接続していない
- `env -i`(環境変数なし)で `python -m loreley_api.admin.openapi_export <path>` を 2 回実行 → 成功し、2 回の出力が `cmp` で一致
- 書き出した OpenAPI(約 100 KB): 14 操作、`servers=[{"url":"/api/admin/v1"}]`、**422 はどの操作にもない**、タグは 6 種(dashboard・documents・jobs・meta・opensearch・sources)、`requestBody` があるのは EP-03(`register_source`)・EP-04(`update_source`)・EP-06(`start_crawl`)のみ、ステータス宣言は P7a の報告どおり
- README の第 6 章(OpenAPI)を実装と突き合わせ: `OPENAPI_ENABLED` 既定 false・無効時 `GET /api/admin/v1/openapi.json` は JSON の 404・書き出しコマンド `python -m loreley_api.admin.openapi_export <出力パス>` は実装と一致

## 変更ファイル(`apps/api/` 配下)

- src 新規: `admin/openapi_export.py`、`admin/schemas/errors.py`(`ErrorResponse`・`error_responses(*codes)`)、`admin/schemas/request_bodies.py`(`json_request_body`・`REQUEST_BODY_MODELS`)
- src 変更: `admin/app.py`(`create_admin_app(deps, *, openapi_enabled=False)`、OpenAPI 整形、`servers`、`operationId`)、`admin/__init__.py`、`admin/base/codes.py`(`ApiTag`)、`admin/routers/{sources,crawl_operations,documents,jobs,opensearch,dashboard,meta}.py`(tags・responses・openapi_extra)、`main.py`、`common/http/body.py`(`ClientDisconnect`)、`pyproject.toml`・`uv.lock`(`tzdata>=2026.6,<2027`)
- tests 新規: `openapi_structure.py`、`admin/test_openapi.py`、`admin/test_openapi_export.py`、`server/test_admin_openapi.py`、`server/test_blocking_isolation.py`。変更: `conftest.py`(`forbid_network_connections`・`anyio_backend` を共有化)、`admin/conftest.py`、`test_main.py`、`common/http/test_body.py`、`test_config.py`(tzdata 2 件)
- `README.md`: 全面更新(1 概要、2 公開範囲と安全性(新設。HO-40・HO-41)、3 提供する API(EP-01〜14 の表、`GET /healthz`)、4 起動方法(必須 3 変数を足した `uv run`・`docker run` の例)、5 環境変数(必須・待ち受けとログ・OpenSearch・Crawler と死活確認・Admin 固有)、6 OpenAPI、7 開発・テスト)

## 判断・設計上の理由(P7a)

- **OpenAPI の公開**: `True` のときだけサブアプリに `/openapi.json` が出る。既定は JSON の 404。`/docs`・`/redoc`(外側・サブアプリ)と外側の `/openapi.json` は常に 404。公開と書き出しは同じ文書(`app.openapi()` を 1 回だけ整形する関数に差し替え)。`info` は title=`Loreley Admin API`、version=`v1`
- **422 の除去と `requestBody` の宣言**は、FastAPI が依存関係の中の本文を OpenAPI に出さず 422 を既定で足すため、`create_admin_app` の `app.openapi` を差し替える後処理にした。`HTTPValidationError`・`ValidationError` スキーマも除去。要求本文のスキーマ(`RegisterSourceBody`・`UpdateSourceBody`・`StartCrawlBody`)は `components` に足す(`models_json_schema`。同名で内容が違うと `ValueError`)。EP-06 は `required: false`、EP-03・04 は `required: true`、EP-05・07・08 は `requestBody` なし
- **エラー応答の宣言**: 400 `invalid_request` は全操作に自動で入る。ほかは B の各 EP のエラー表どおりにステータスごとに宣言し、説明文に返しうる `error.code` を列挙(`ErrorCode` はステータスと 1 対 1。B 2.3)。EP-13 は B 8.1 では「エラーなし」だが、未知のクエリを 400 にするので 400 を宣言。`ErrorResponse.error.code` は `str`(列挙にしない。共通 code や将来の code で型生成が壊れないように)
- **`operationId`** は `generate_unique_id_function` でルート関数名(14 個とも一意)。タグは `ApiTag`(6 種)を全ルートに付ける(EP-06・08 は `sources`、EP-07 は `jobs`)
- **`openapi_export`**: 接続しない代役(属性にアクセスすると `RuntimeError`)を `build_admin_dependencies` に渡して `.openapi()` を書き出す。`OPENAPI_ENABLED` に関係なく書き出せる。出力は `indent=2, sort_keys=True, ensure_ascii=False` + 末尾改行
- **`servers`**: FastAPI の既定では、書き出し(`app.openapi()`)には `servers` が出ず、公開時は `root_path` から `servers: [{"url":"/api/admin/v1"}]` が足される(実測)。型生成の入力(書き出し)と実 API の説明が食い違い `baseUrl` の出所が不安定になるため、`servers=[{"url": ADMIN_API_PREFIX}]` を固定し `root_path_in_servers=False` にした。公開と書き出しが同一の文書になることをテストで固定。`paths` はマウント位置を含まない相対パス(`/sources` など)。入れ子のマウントと `FastAPI(root_path=…)` は未検証のまま(BAPI-U-2 の残り)
- **`ClientDisconnect`**: 本文読み取り中の切断は、従来 ERROR ログ + 500 のアクセスログになっていた(本物の異常と見分けがつかない)。`read_limited_body` で捕捉し、WARNING 1 行(固定文。値・例外内容なし)+ `ApiError(400, invalid_request)` にした。切断した相手には届かないのでアクセスログのステータスが 400 になるだけ。変更は `common/http/body.py` のみ(約 10 行)。B/C に規定なし(D 4.12(c) は「ログ水準を下げるなどを検討」)
- **`tzdata`**: `pyproject.toml` に `tzdata>=2026.6,<2027`(CalVer。ロック済みの 2026.6)を直接依存に。2027 年に上限の見直しが要る。`zoneinfo.reset_tzpath(to=[])` で OS の zoneinfo を空にした状態で `CRON_TIMEZONE=Asia/Tokyo` が通ることをテスト
- **server の結合確認(C 11章 14)**: 実物の `BlockingRunner`・実物の `HttpCrawlerClient`・ローカル HTTP スタブ(遅延 1.5 秒)で、`crawler` 枠(4)を使い切り、さらに 2 本を枠待ちにした間に `/healthz`・EP-01・EP-14 が 200 で即応答(読み取り完了の時点で Crawler 呼び出しは 1 つも終わっていない。のちにすべて 202)。別テストで遅延の間もタイマーが進む(イベントループが塞がれていない)

## README に関する判断(document-writer)

- 冒頭の「基盤だけ」「実装は D と一部異なる」を消し、Admin API(`/api/admin/v1`)を提供と書き直した。設計書との細部の差は作業記録で申し送り、追従改訂までは実装を正とする。冒頭の「HO-51 に差分がある」という参照は、追従改訂済み(A 9.2)のため削除
- **HO-40・HO-41**: 認証なし・localhost のみ・破壊的操作の一覧・`connector_config.root` の注意。本文なしの POST(EP-05・06・07)は `Origin` を問わず処理される(0013 のテストで確認した現状)。EP-03 は JSON の `Content-Type` が必要。EP-04・08 は CORS 未許可で届かない。DNS rebinding なら全 EP が対象。軽い緩和は足していない。設計書(A 2.3・B 2.10・BAPI-U-8)の文言と合わせた
- Docker 起動例は単体の `docker build`/`docker run`(必須 3 変数 `OPENSEARCH_URL`・`CRAWLER_URL`・`INDEXER_URL`、ポートはホストのループバックにだけ publish)と `uv run` にとどめた。compose の `api` サービス・Dockerfile の Node ステージは範囲外(HO-34〜37)と明記。現イメージに `/app/web` がなく EP-13 の `web` が異常になることを注記
- 環境変数は `config.py` の `Settings` と検証を正本にし、設計書 C 7.2 とも一致を確認。`ConfigError` の例は実際に `LORELEY_API_PORT=abc` で起動して得た実出力(`port: int_parsing; opensearch_url: missing; crawler_url: missing; indexer_url: missing`)に近い形で書いた(設計書の例は `int_parsing` だが必須の欠落は `missing`)
- README に書いていない: `tzdata`(P7a で直接依存化)、結合テスト・手動スモーク(作業記録の事項)

## 設計書との食い違い・申し送り(設計書は未変更)

1. D 4.3・D 3章: `create_admin_app(deps)` に `openapi_enabled` キーワード引数が増えた。`ADMIN_API_PREFIX` の定義は `main` から `admin/app.py` に移った。`schemas/errors.py` は D 3章どおり実装。`schemas/request_bodies.py` は D になく追加(AAM-P-25 の範囲)
2. D 4.12(c): 422 除去と `requestBody` 宣言の実装形(`app.openapi` の差し替え)と、`servers` を固定する理由(公開と書き出しの食い違い)を追記したい。BAPI-U-2 の「`servers`・`paths`」は上記で確認済み(入れ子のマウントと `FastAPI(root_path=…)` は未検証)
3. D 4.12(c)・A: `ClientDisconnect` は WARNING 1 行 + 400(`common/http/body.py`)で確定。D の「未確認」を直したい
4. B 8.1(EP-13): 「エラーなし」とあるが、実装は未知のクエリを 400 にする(EP-14 の「共通のもののみ」と同じ扱い)
5. **型生成への影響(実害は小さい)**: `UpdateSourceBody`・`RegisterSourceBody` の `ttl_days`・`ttl_seconds` は OpenAPI 上 `integer | null`(既定 null)だが、実行時は明示的な `null` を `type` で拒否する(B 2.4 の「省略のみ」)。pydantic のスキーマからの生成物。必要なら後続で `json_schema_extra` などで絞る
6. `ErrorResponse.error.code` は `str`(列挙にしない)。E で列挙型が要るなら要相談
7. 設計書の更新は README では不要(`document-writer` の判断)

## 検出力確認(P7a。14 件を一時変更し全件検出、復元済み)

422 除去の無効化、EP-03 の requestBody 削除、EP-06 を `required=True` に、EP-07・08 のタグ変更、OPENAPI を常に無効/常に有効、`docs_url` の有効化、`servers` 削除、書き出しで接続を試みる、`ClientDisconnect` の捕捉を無効化、Crawler 呼び出しをイベントループ上で直接実行、400 の自動宣言の除去、`sort_keys` 無効

## 未対応事項・次にやること

- **手動スモーク(メインエージェント)**: 実 OpenSearch・実 Crawler・実 Indexer(専用 compose プロジェクト `loreley-admin-smoke`)に対し、EP-01〜14・障害系・OpenAPI の公開(`OPENAPI_ENABLED` の有無)・ログ(アクセスログがテンプレート表記・ID/本文/`connector_config` なし)を確認する。事前に 9200・8000・8001・8080 の占有を確認し、9200 を別プロジェクトが使っていれば止めずにユーザーに判断を仰ぐ
- 手動スモークで確認するもの: 実機で `OPENAPI_ENABLED=true` の `/api/admin/v1/openapi.json` を取り、書き出した JSON と一致するか/実 Crawler の応答が宣言した 200・202 と一致するか/AAPI-U-11(接続拒否時の `ConnectionError.info` の型)/AAA-U-10(期限後に残るスレッド)/クエリの意味(AAA-U-1〜3、AAPI-U-7)/`cat.*` の実際の列・`relocating` の `node` 表記
- 書き出した OpenAPI JSON のコミット先と Hey API 側の読み込み(`servers` の扱い)は、フロントエンドのタスク(FARC-P-6)
- R-C(後半)の重点: OpenAPI の宣言(各 EP のステータス一覧と B の突き合わせ)、`ClientDisconnect` の WARNING + 400 の判断、README の正確さ(HO-40・41)
- 据え置き: `test_secret_output.py` の DNS 依存
