# Loreley Indexer

社内ドキュメントの登録・削除判定・削除実行・要約生成を担うコンポーネント。Crawler から HTTP で呼ばれる。設計は `docs/v0.x/system-design/indexer/`(`indexer-architecture-v0.9.md`(以下 arch)、`indexer-api-v0.9.md`(以下 api)、`indexer-module-structure-v0.3.md`)を正とし、本書は起動・設定・運用の要点をまとめる。

## 1. 概要

- **責務**: 抽出・正規化(txt / Markdown / HTML / PDF)と検索インデックスへの登録、`last_seen_at` の部分更新、クロール結果(`loreley-deletions`)の管理、削除の判断・実行(Deletion Manager)、要約生成の枠組み。検索インデックスと削除記録を書き換える唯一のコンポーネント
- **MVP の前提**: 単一ホスト・単一 Indexer・直列実行・認証なし。ソース単位のロック・削除ワーカー・起床通知はプロセス内にあり、**複数プロセス・複数 Indexer は対象外**(arch 13.2)
- **認証・認可がない**: Crawler と同じ内部ネットワークにだけ置き、ホストや外部に公開しない(api 3.1)。`DELETE` でソースの文書の全削除まで呼べる
- **他モジュールとの関係**: Crawler とメッセージブローカーなしで HTTP で直接通信する(本書 4 章)。OpenSearch の検索インデックス(`loreley-documents`)と Store 層(`loreley-deletions`、`loreley-jobs`)に読み書きする。`loreley-jobs`(ロック・メンテナンスフラグ)は**読み取りのみ**。Indexer はインデックスの作成・マッピング定義をしない
- **スコープ外**: LLM の具体プロバイダ(インターフェースのみ。要約は無効が既定で、有効にすると起動に失敗する。7 章)

## 2. 起動方法

### ローカル

Python 3.12 と [uv](https://docs.astral.sh/uv/) を使う。

```sh
cd apps/indexer
uv sync
LORELEY_INDEXER_OPENSEARCH_URL=http://localhost:9200 uv run python -m loreley_indexer.main
```

`python -m loreley_indexer.main` は単一プロセスで uvicorn を起動する(`--workers`・`--reload` は使わない)。既定の待ち受けは `127.0.0.1:8000`。

### Docker

ビルドコンテキストは `apps/indexer`。

```sh
docker build -t loreley-indexer apps/indexer
docker run --restart unless-stopped \
  --network <OpenSearch と共通のネットワーク> \
  -p 127.0.0.1:8000:8000 \
  -e LORELEY_INDEXER_OPENSEARCH_URL=http://opensearch:9200 \
  loreley-indexer
```

- **認証がないので、外部に公開しない**(1 章)。上の例は、ポートをホストのループバック(`127.0.0.1`)にだけ publish している。Crawler とは同じ Docker ネットワークで通信するなら、ポートは publish しなくてよい。`0.0.0.0` への publish(`-p 8000:8000`)はしない
- `--rm` は、再起動ポリシーと併用できない(Docker がエラーにする)ので付けていない。`--network` は、`http://opensearch:9200` のような名前を解決するために、OpenSearch と同じネットワークを指定する
- OpenSearch に到達できないと、起動時の処理(5 章)が失敗してプロセスが終了する。再起動ポリシー(`--restart unless-stopped` など)を付ける。Compose なら、OpenSearch の `depends_on`(`condition: service_healthy`)で起動を待たせる
- イメージは Python 3.12(slim。ベースイメージはタグとダイジェストで固定。運用は `Dockerfile` の冒頭のコメント)で、依存は `uv.lock` から入れる(dev 依存は含まない)。**非 root(uid 10001)** で動く。ビルドツールは最終イメージに含まれない
- コンテナでは `LORELEY_INDEXER_HTTP_HOST=0.0.0.0` が設定済み(既定の `127.0.0.1` では外から届かない)。`LORELEY_INDEXER_HTTP_PORT` を変えたら、公開するポートも合わせる
- 接続先・認証情報などの設定は、イメージに焼き込まず実行時に環境変数で渡す(Docker の secrets や `_FILE` 形式は読めない)。環境変数は `docker inspect` で見えるので、その権限を絞る
- `HEALTHCHECK` は `GET /healthz`(間隔 15 秒、タイムアウト 5 秒、再試行 3 回)。起動時の整理が終わるまで 503 で、uvicorn も接続を受け付けないため、`--start-period` を **120 秒**にしている。OpenSearch の 1 リクエストは最大 `OS_REQUEST_TIMEOUT_SECONDS` ×(1 + `OS_TRANSPORT_MAX_RETRIES`)= 既定 30 × 3 = 90 秒かかり、起動時の整理は複数のリクエストなので、OpenSearch の遅延が続くと 120 秒を超えうる。起動が遅い環境や、タイムアウト設定を伸ばしたときは、`--start-period` も伸ばす
- `HEALTHCHECK` のホストは `127.0.0.1` 固定。`HTTP_HOST` を特定の IP や IPv6 に変えるなら、`HEALTHCHECK` も合わせる
- 停止は SIGTERM(`docker stop`)。停止の挙動は 5 章。猶予は **30 秒以上**にする(Docker の既定 10 秒では、実行中の削除バッチの完了待ちが足りないことがある)

### 開発

```sh
cd apps/indexer
uv sync                      # dev 依存(pytest、ruff、httpx2)を含めて入れる
uv run pytest
uv run ruff check
uv run ruff format --check
uv lock --check              # uv.lock が pyproject.toml と一致していること
```

`httpx2` は starlette の `TestClient` が要求するテスト用の依存で、本番イメージには含まれない。

## 3. 設定(環境変数)

設定は環境変数のみ(`.env` は読まない)。接頭辞は `LORELEY_INDEXER_`。値の形式が不正、または上限を超えると起動に失敗する。

起動時の設定エラーは、`invalid settings: opensearch_url: missing; http_port: less_than_equal` のように、**フィールド名と検証の種別だけ**を標準エラー出力に出して終了する(終了コード 1。最大 10 件)。値は、秘密値(`OPENSEARCH_PASSWORD` など)の漏洩を防ぐため出さない。設定どうしの整合条件の違反は、フィールド名の代わりに `settings: raw_bytes_above_batch_bytes` のように検証名が出る。

**数値の既定値は設計書で未決のため仮値**(arch 15.7、K39)。実測して決める前提で、無制限のリトライ・メモリ使用にならないよう、すべて上限を設けている。上限を超える値は設定できない。整数の項目の下限は、特記がなければ 1(秒などの小数は 0 より大きい値)。

### 必須・接続

| 環境変数 | 既定 | 説明 |
| --- | --- | --- |
| `OPENSEARCH_URL` | (必須) | OpenSearch の URL。認証情報を URL に埋め込む、または URL を解釈できない(ポートが数値でないなど)と、固定文 `invalid OpenSearch connection settings (...)` で起動に失敗する(URL の値は出さない。認証情報は下の項目で渡す) |
| `OPENSEARCH_USERNAME` | なし | Basic 認証のユーザー名。`..._PASSWORD` と**両方**を指定したときだけ認証する |
| `OPENSEARCH_PASSWORD` | なし | パスワード(秘密値。ログでは伏せる) |
| `OPENSEARCH_VERIFY_CERTS` | `true` | TLS 証明書の検証 |
| `OPENSEARCH_CA_CERTS_PATH` | なし | CA 証明書のパス |
| `OS_REQUEST_TIMEOUT_SECONDS` | 30 | リクエストのタイムアウト(秒。0 より大きく 300 以下) |
| `OS_TRANSPORT_MAX_RETRIES` | 2 | 接続エラー・タイムアウト・502/503/504 の再試行回数(0〜5) |
| `OS_DELETE_BY_QUERY_TIMEOUT_SECONDS` | 600 | `delete_by_query` 専用のタイムアウト(秒。0 より大きく 3,600 以下)。専用クライアントはタイムアウトや 5xx で自動再送しない |
| `SEARCH_INDEX_NAME` | `loreley-documents` | 検索インデックス(エイリアス想定)の名前(仮名) |
| `DELETIONS_INDEX_NAME` | `loreley-deletions` | 削除記録のインデックス名(仮名) |
| `JOBS_INDEX_NAME` | `loreley-jobs` | ジョブ・ロック・メンテナンスフラグのインデックス名(仮名。読み取りのみ) |

### HTTP・ログ

| 環境変数 | 既定 | 説明 |
| --- | --- | --- |
| `HTTP_HOST` | `127.0.0.1` | 待ち受けアドレス(コンテナのイメージでは `0.0.0.0`) |
| `HTTP_PORT` | 8000 | 待ち受けポート(1〜65,535) |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR`(大文字小文字は区別しない) |

### サイズ上限(登録・抽出)

| 環境変数 | 既定 | 上限 | 説明 |
| --- | --- | --- | --- |
| `MAX_RAW_BYTES` | 20 MiB(20,971,520) | 100 MiB | 原本 1 件の上限(デコード後) |
| `MAX_BATCH_DOCUMENTS` | 50 | 500 | バッチ 1 回の文書数 |
| `MAX_BATCH_BYTES` | 64 MiB(67,108,864) | 256 MiB | バッチ 1 回のデコード後の合計 |
| `MAX_REQUEST_BODY_BYTES` | 100 MiB(104,857,600) | 512 MiB | リクエストボディ(base64 のまま)の上限 |
| `MAX_CONTENT_BYTES` | 5 MiB(5,242,880) | 50 MiB | 抽出後の本文の上限(UTF-8。超えると切り詰めて `truncated`) |
| `MAX_LAST_SEEN_IDS` | 1,000 | 10,000 | `last-seen` の `document_ids` の件数 |

下限は、いずれも 1 以上。

### 競合・再試行

| 環境変数 | 既定 | 上限 | 説明 |
| --- | --- | --- | --- |
| `WRITE_CONFLICT_MAX_REREADS` | 3 | 10 | 409 のときの読み直し回数(下限 1)。超えると `write_conflict` |
| `UPDATE_RETRY_ON_CONFLICT` | 3 | 10 | `last_seen_at` の Update の `retry_on_conflict`(下限 0) |
| `DELETE_BY_QUERY_MAX_RERUNS` | 5 | 20 | ソース削除 2 の `delete_by_query` の再実行回数(最初の 1 回に加えて。下限 1) |
| `RETRY_BACKOFF_INITIAL_SECONDS` | 1.0 | 60 | 削除エラー・要約の再試行の待ち(初回。秒。0 より大きい。ジッタあり) |
| `RETRY_BACKOFF_FACTOR` | 2.0 | 10 | 待ちの倍率(下限 1) |
| `RETRY_BACKOFF_MAX_SECONDS` | 30.0 | 300 | 待ちの上限(秒。0 より大きい) |

### 削除

| 環境変数 | 既定 | 上限 | 説明 |
| --- | --- | --- | --- |
| `SKIP_OVERSIZE_ID_LIMIT` | 10,000 | 100,000 | 終了通知の 2 つの ID 一覧(スキップ・サイズ超過)の合算件数の上限。超えると一覧を保存せず、`validation_failed` になる |
| `DELETION_BATCH_SIZE` | 100 | 1,000 | 削除 1 バッチの文書数 |
| `DELETION_RETENTION_COUNT` | 20 | 1,000 | ソースごとに残す終端状態の削除結果の件数 |
| `MAX_DELETION_TARGETS` | 200,000 | 2,000,000 | 削除対象の件数の上限。超えると `failed`(`delete_error`) |
| `SEARCH_AFTER_PAGE_SIZE` | 1,000 | 10,000 | `search_after` の 1 ページの件数 |
| `DELETION_POLL_INTERVAL_SECONDS` | 2.0 | 60 | 削除ワーカーの走査間隔(秒。0 より大きい) |
| `DELETION_POLL_BACKOFF_MAX_SECONDS` | 300.0 | 3,600 | 連続失敗時の走査間隔の上限(秒。0 より大きい) |
| `DELETE_ERROR_RETRY_ATTEMPTS` | 3 | 10 | 削除エラーの総試行回数(初回を含む。下限 1) |
| `DISCARD_MAX_ATTEMPTS` | 20 | 100 | ソース削除 1 の試行ラウンド数(下限 1) |

### 要約

| 環境変数 | 既定 | 上限 | 説明 |
| --- | --- | --- | --- |
| `SUMMARY_ENABLED` | `false` | — | 要約生成の有効化。**LLM プロバイダが未実装のため、`true` にすると起動に失敗する** |
| `SUMMARY_CONCURRENCY` | 1 | 8 | 要約生成の並列数 |
| `SUMMARY_MAX_ATTEMPTS` | 3 | 10 | LLM 呼び出しと書き戻しの試行回数 |
| `SUMMARY_QUEUE_SIZE` | 100 | 10,000 | 生成依頼キューの長さ。満杯なら断り、再走査に委ねる |
| `SUMMARY_RESCAN_PAGE_SIZE` | 100 | 1,000 | 再走査で `pending` を列挙する 1 ページの件数 |
| `SUMMARY_RESCAN_MIN_INTERVAL_SECONDS` | 60.0 | 3,600 | 再走査の最短間隔(秒。0 より大きい) |
| `SUMMARY_RESCAN_MAX_INTERVAL_SECONDS` | 3,600.0 | 86,400 | 再走査の間隔の上限(秒。0 より大きい) |
| `LLM_TIMEOUT_SECONDS` | 60.0 | 600 | LLM のタイムアウト(秒。具体プロバイダの実装後に使う) |
| `SUMMARY_INPUT_MAX_CHARS` | 30,000 | 1,000,000 | LLM に渡す本文の先頭からの文字数(下限 1) |

### 設定どうしの整合条件

次を満たさないと起動に失敗する。

- `MAX_RAW_BYTES` ≤ `MAX_BATCH_BYTES`
- `MAX_BATCH_BYTES` × 4/3 ≤ `MAX_REQUEST_BODY_BYTES`(base64 は元の約 4/3 倍になる。バッチ合計の上限まで届くリクエストが、ボディの上限で先に拒否されないように)。したがって `MAX_BATCH_BYTES` を 75 MiB より大きくするなら、`MAX_REQUEST_BODY_BYTES` も上げる(既定の 100 MiB の場合)。`MAX_RAW_BYTES` を 64〜75 MiB にするときに上げる必要があるのは、`MAX_BATCH_BYTES` だけ
- `SUMMARY_RESCAN_MAX_INTERVAL_SECONDS` ≥ `SUMMARY_RESCAN_MIN_INTERVAL_SECONDS`
- `DELETION_POLL_BACKOFF_MAX_SECONDS` ≥ `DELETION_POLL_INTERVAL_SECONDS`

## 4. API

契約の詳細(項目・条件・冪等性)は api(`indexer-api-v0.9.md`)を参照。パスとメソッドは設計書の案のとおり。

| API | メソッドとパス | 成功時の応答 |
| --- | --- | --- |
| 開始通知 | `POST /crawls/start` | 200 `{"crawl_id", "status": "running"}` |
| 終了通知 | `POST /crawls/{crawl_id}/finish` | 202(ボディなし) |
| Status | `GET /crawls/{crawl_id}` | 200 削除結果の状態(項目は api 4.5。値のない項目は省く) |
| バッチ登録 | `POST /sources/{source_id}/documents:batch` | 200 `{"results": [...]}`。文書ごとに `status` が `ok`(`change`: `created` / `updated` / `unchanged`、`extract_failed`)または `failed`(`failure_type`: `document_rejected` / `lock_not_owned` / `write_conflict` / `update_conflict` / `oversize`、`message`。扱いは 6 章) |
| `last_seen_at` 部分更新 | `POST /sources/{source_id}/last-seen` | 200 `{"results": [{"document_id", "result"}]}`(`updated` / `unchanged` / `not_found` / `update_conflict` / `lock_not_owned`) |
| ソース削除 1(破棄) | `POST /sources/{source_id}/deletions:discard` | 200 `{"discarded_crawl_ids": [...]}`。実行中の削除バッチの終了後に返る |
| ソース削除 2(文書の全削除) | `DELETE /sources/{source_id}/documents` | 200 `{"deleted_count": n}` |
| ソース削除 3(削除記録の削除) | `DELETE /sources/{source_id}/deletion-records` | 200 `{"deleted": true/false}` |
| ヘルスチェック(契約外) | `GET /healthz` | 200 `{"status": "ok"}` |

- 文書単位の結果は HTTP 200 の本文で返し、リクエスト全体の失敗だけ HTTP エラーにする
- エラー本文は共通形式 `{"error": {"code", "message", "retryable"}}`。`message` は固定文か、検証エラーの位置と型だけで、リクエストの値(本文・ID・秘密値)は含まない

| HTTP | `code` | 意味 |
| --- | --- | --- |
| 400 | `invalid_request` | 形式不正(サイズ上限超過を含む。413 は使わない) |
| 404 | `crawl_not_found` | Status の対象なし |
| 404 | `not_found` | 未定義のパス |
| 405 | `method_not_allowed` | 未定義のメソッド |
| 上記以外 | `http_error` | 上記以外の Starlette の HTTP 例外(HTTP ステータスはそのまま) |
| 409 | `crawl_already_finished`、`crawl_start_conflict`、`stale_crawl_started_at` | 開始通知の拒否 |
| 409 | `crawl_not_started`、`crawl_source_mismatch`、`crawl_started_at_mismatch`、`crawl_already_closed`、`crawl_finished` | 登録・`last-seen` の受理条件の拒否(1 件も書かない) |
| 409 | `finish_source_mismatch`、`finish_content_mismatch` | 終了通知の拒否 |
| 409 | `lock_not_owned` | ソース削除 2・3 のロック不所有(書かない) |
| 500 | `internal_error` | 想定外の異常 |
| 503 | `unavailable`(`retryable=true`) | OpenSearch の全体異常、起動時の整理が終わるまで |

## 5. 起動・停止の挙動

起動順(module 5.6。障害時の扱いは arch 12 章):

1. 設定の読み込み。要約が有効で LLM プロバイダが未設定なら起動を失敗させる
2. OpenSearch のクライアント(通常用と `delete_by_query` 専用の 2 つ)の作成
3. **起動時の整理**: `finish_received_at` があり終端状態でない削除結果(待機中・判定中・実行中)を `failed`(理由 `indexer_restart`)にする。**再起動前に受理した削除は再開されず、削除は次のクロールに委ねる**(保存した ID 一覧は同じ書き込みで削除する)。`finish_received_at` のない `running` は触れず、次の開始通知で `superseded` になる
4. 削除ワーカーの起動(整理より先に始めると、再起動前の削除を再開してしまう)
5. 要約ワーカーの起動(有効時のみ。起動時の再走査の要請を含み、受け付けと並行して進む)
6. HTTP の受け付けの開始

**1〜5 が終わるまでは、`/healthz` を含むすべてのパスが 503 `unavailable`(`retryable=true`)を返す**(二重の防御。実際には uvicorn がアプリケーションの起動完了まで接続自体を受け付けないので、外からは接続拒否に見える)。

停止(SIGTERM)は逆順: 受け付けを止め、要約ワーカー、削除ワーカーの順に止め、OpenSearch の接続を閉じる。ワーカーは実行中の処理(削除は 1 バッチ、要約は 1 件)を終えてから止まる(それぞれ最大 10 秒待つ)。途中だった削除結果は `running` のまま残り、次回の起動時の整理で `failed`(`indexer_restart`)になる。削除は期限(TTL)方式のため、遅れるだけで安全(arch 9.9)。プロセスの終了コードは、コンテナで PID 1 として動くときは、uvicorn が再送した SIGTERM が無視されるため **0** になる(`docker run --init` など PID 1 でなければ 143)。停止処理が走ったかは、ログで確認できる。

ログは標準エラー出力に `日時 レベル ロガー名 メッセージ` の形式で出す。アクセスログはメソッド・ルートのテンプレート・ステータス・所要時間だけで、実際のパス(ID を含む)・本文・秘密値は出さない。

## 6. Crawler 向けの契約・確認事項

Crawler の実装時に、次を設計・実装と突き合わせる。**確認が要る事項に「確認」と付けた。**

Crawler の義務の要点(詳細は api 4.1・4.4):

- 開始通知・終了通知の再送は、最初と同じ内容で送る。違うと 409(`crawl_start_conflict` / `finish_content_mismatch`)になる
- 未知の `crawl_id` の終了通知にも 202 が返る。**202 は受理の確認ではない**
- 終了通知の受理は、Status API の `finish_received_at` などで確認する

### バッチ登録の失敗種別と Crawler の扱い(api 3.5・4.3)

| `failure_type` | 意味 | Crawler の扱い |
| --- | --- | --- |
| `oversize` | 原本が `MAX_RAW_BYTES` 超 | リトライしない |
| `document_rejected` | 文書固有の拒否 | 設計書どおり、上限付きでリトライしたあとスキップ(api 3.5 / arch 4.4)。連続 20 件でジョブ `failed` にする打ち切りは Crawler 側の規則で、Indexer は実装しない |
| `lock_not_owned` | ロックの所有確認に失敗 | スキップ・リトライせず、ジョブ `failed` |
| `write_conflict` | 書き込みの 409 の読み直しが `WRITE_CONFLICT_MAX_REREADS` を超えた(再試行可能) | 上限付きでリトライし、解消しなければジョブ `failed`・期限削除なし(スキップの対象にしない) |
| `update_conflict` | 変更なしの文書の `last_seen_at` の補完 Update が `retry_on_conflict` を超えて 409(再試行可能) | `write_conflict` と同じ |

ロックを途中で失ったバッチは、確認済みの文書の結果を返し、以降の未処理の文書はすべて `lock_not_owned` にして書かない(API-U-13 は設計上未決で、この案を採用)。

### リクエストの形と上限

- **バッチのサイズ防御**: `documents` が空、または `MAX_BATCH_DOCUMENTS` 超なら全体 400。`raw_content`(base64)は**デコードする前に**長さからサイズを判定する
  - 推定したデコード後サイズ(base64 の長さから算出)が `MAX_RAW_BYTES` 超なら、デコードせず文書単位の `oversize`(リトライしない)。合計には数えない
  - 申告された `size` だけが `MAX_RAW_BYTES` 超のときは、デコードしたあとドメインが `oversize` にする。この場合は合計に含まれる
  - デコードする文書の合計が `MAX_BATCH_BYTES` 超なら全体 400
  - ただし、base64 を含むリクエストボディが `MAX_REQUEST_BODY_BYTES` を超える原本は、`oversize` にならず**リクエスト全体が 400**(`Content-Length` を先に見る。チャンク転送では読んだ量で判定する。`Content-Length` が不正・極端に長い桁数でも 400)
  - `raw_content` は標準の base64(パディングあり・改行なし)。不正なら全体 400
- **`last-seen`**: `document_ids` が `MAX_LAST_SEEN_IDS`(既定 1,000)超なら全体 400。分割して送る
- **`content_hash`**: 小文字 64 桁の 16 進のみ受理する(大文字は全体 400)。Indexer は再計算も照合もしない(**確認**: Crawler の算出が小文字 hex か)
- **ID の文字と長さ**:
  - `source_id`・`crawl_id`・`lock.owner`・`lock.job_id`(パスの `source_id`・`crawl_id` を含む): 空・制御文字(0x00〜0x1f、0x7f。改行を含む)・256 バイト(UTF-8)超は 400。ログに偽の行を注入されないため
  - `external_id`: 空・4,096 バイト超・NUL は**リクエスト全体**の 400。改行・タブなどの制御文字は**許可**する(Linux のファイル名として正当で、1 件のために全体が恒久的に失敗しないように)
  - `last-seen` の `document_ids`、終了通知の `skipped_document_ids`・`oversize_document_ids` の要素: 小文字 64 桁の 16 進
  - 長さの上限は仮値(設計書に規定なし)。超える ID があると全体 400 になる
- **孤立サロゲート**(JSON の `\ud800` など。Linux で CP932 のファイル名を読むと生じうる): `external_id`・ID 類・`content_hash`・日時・`raw_content` に入ると**リクエスト全体**が 400 で、再送しても直らない(**確認**: Crawler が事前に除く・置き換える)。`title`・`mime_type`・`path`・`url` は文書単位の `document_rejected`
- **DELETE は `lock` を JSON ボディで運ぶ**: ソース削除 2・3 は `{"lock": {"owner", "job_id"}}` が必須(ボディなしは 400。チャンク転送も可)。ソース削除 1(`POST`)は `{"lock", "reason"?}`(`reason` は `source_deleted` のみ)を受け取るが、所有確認はしない。api 3.2 は運び方を決めていない(**確認**: Crawler の HTTP クライアントが DELETE にボディを載せられること)
- **`skipped_count`**(終了通知): 型(非負整数)だけを検証し、値は使わない。ID 一覧の件数との一致も検証しない
- `enumeration_completed` の終了通知では `enumerated_count` と 2 つの ID 一覧が必須。`failed`・`cancelled` では省略できる(`finished_at` は形式の検証のみ。保存も比較もしない)
- 型は strict: `ttl`・`min_delete_count` は整数、`ratio_threshold` は有限の数値、`force_delete`・`rewrite_mode` は真偽値(`1.5` や `"true"` は 400)。**意味上の範囲は検証しない**(型と int64 の範囲は検証するが、`ttl` の 0・負値、`ratio_threshold` の 1 以上・負値、`min_delete_count` の極端な値も通る。9 章の「しきい値・TTL・最小件数の誤設定」を参照)。日時はタイムゾーン付きの ISO 8601。`fetched_at`・`metadata` を含む未知の項目は無視する

### `document_id` の算出

`document_id` = SHA-256(`source_id` + NUL + `external_id`) の小文字 16 進。`external_id` はハッシュの前に NFC に正規化し、`\` を `/` に統一する(大文字小文字は区別する)。**先頭の `/` は除去しない**: 設計書の「ルートからの相対パス、先頭に `/` を付けない」は Crawler が渡す値の前提と読み、Indexer が除く規則とはしていない。`last-seen` は Crawler が算出した `document_id` を受けるため、**Crawler 側の算出と一致するか確認する**(api 4.3 の応答例の `document_id`(`src-docs` + `page-10023` など)、および `apps/indexer/tests/documents/test_document_id.py` の `API_EXAMPLE_VECTORS` で確認できる。共有のテストベクタは設計上未決(API-U-7))。

### 仮定義(Crawler・infra の設計の確定時に再確認)

設計書に定義がなく、Indexer が仮に置いたもの。変更箇所は `infrastructure/opensearch/jobs.py` と `common/locks.py`(ロック・フラグ)、`infrastructure/opensearch/connection.py`(索引名)に隔離してある。実 OpenSearch と食い違うと、テストが通っても実機で失敗しうる。

| 対象 | 仮定義 |
| --- | --- |
| ロック文書 | `loreley-jobs` の ID `lock-{source_id}`、項目 `owner`・`job_id`・`lease_expires_at`(ISO 8601)。所有 = `owner` と `job_id` が一致し、`lease_expires_at` が現在時刻より後。文書なし・期限切れ・不一致・形式不正はすべて「所有していない」 |
| メンテナンスフラグ | `loreley-jobs` の ID `maintenance`、項目 `enabled`(bool)。**fail-closed**: 文書があり `enabled` が真偽値の `false` と明示されているときだけ「立っていない」。それ以外(`"true"`・`1`・欠落・非 bool)は「立っている」とみなし、record_id と項目名だけを WARNING に出す。文書がなければ「立っていない」 |
| インデックス名 | `loreley-documents`(エイリアス想定)、`loreley-deletions`、`loreley-jobs`。環境変数で変更できる |
| マッピング | Indexer は作らない。`document_id` を keyword としてソートに使える、削除記録の `record_type`・`status`・`source_id` などが keyword、という前提 |
| `loreley-deletions` の文書 | `deletion-{source_id}`(現行世代)と `deletion_result-{crawl_id}`(削除結果)を同じインデックスに置く |
| 失敗種別・理由コードの名前 | `oversize`、削除結果の `reason`(`outcome_failed` / `outcome_cancelled` / `maintenance` / `indexer_restart` / `delete_error`、`count_mismatch` / `id_limit_exceeded` / `target_exceeds_denominator`)は仮名。`extract_failed` の種別(`unsupported_mime_type` など)は Indexer 内部の理由名で API には出ない(応答は `extract_failed: true` の真偽値のみ) |

## 7. 要約

- 既定は無効(`SUMMARY_ENABLED=false`)で、LLM を呼ばない。登録した文書は `summary_status=disabled` になる
- **有効にすると起動に失敗する**(LLM の具体プロバイダが未実装のため。`StartupError`)
- 有効化後の既存の `disabled` 文書の一括生成は実装していない。要約ロジックやモデルを変えたとき・要約を有効にした後は、`rewrite_mode=true` でクロールして再登録する(arch 4.3・7.5)
- 要約の入力は本文の**先頭 `SUMMARY_INPUT_MAX_CHARS`(既定 30,000)文字だけ**。仮値で、モデルを選定した後に見直す(arch U-9)
- 生成・書き戻しが `SUMMARY_MAX_ATTEMPTS` 回で直らない文書は `pending` のまま残り(`failed` へは遷移しない)、再走査で再び試す。再走査は起動時に即時に 1 回、以後は書き戻しの成功がない限り間隔を `SUMMARY_RESCAN_MIN_INTERVAL_SECONDS` から倍々で `SUMMARY_RESCAN_MAX_INTERVAL_SECONDS`(既定 1 時間)まで伸ばしながら続ける(成功でリセット)

## 8. メンテナンス(再インデックス・`rewrite_mode`)

手順の全体は arch 11 章(`_reindex`、切り替え前の確認、エイリアスの切り替え)。Indexer 側の要点は次のとおり。

- **開始前に、実行中の書き込みが終わったことを確認する**: 対象のソースに `running` のクロールがなく、`loreley-deletions` に待機中・判定中・実行中の削除結果がなく、要約生成も終わっていること。要約生成はジョブ記録を持たないため、確実な確認手段は Indexer の停止。終わらないときは Crawler と Indexer を止めてから始める(メンテナンスフラグは、すでに始まっている書き込みを止めない)
- **メンテナンスフラグ**(6 章の仮定義): Indexer は、削除の判定の前と削除の各バッチの前、要約の生成の前と書き込みの前に確認し、立っていれば書かない。待機中の削除は、順番が来た時点で立っていれば `failed`(理由 `maintenance`)になる。**登録と `last-seen` ではフラグを確認しない**(Crawler 側で止める前提)。フラグの書き込み方法(運用者の手動か Crawler の固定経路か)は設計書で未決(arch U-24)
- **メンテナンス解除後の要約の再開**: 要約の再走査の間隔が伸びているため、最悪で `SUMMARY_RESCAN_MAX_INTERVAL_SECONDS` 遅れる(新規登録分はキュー経由で遅れない)
- **`rewrite_mode=true` のクロールの前**: Indexer の要約生成を止めて終えておく(旧い設定で生成中の要約が、本文が同じため書き戻されうるので。arch 4.3)。止める確実な手段は Indexer の停止
- `_reindex` は要約も `_source` から引き継ぐので、再生成は不要

## 9. 既知の制限・運用上の注意

- **しきい値・TTL・最小件数の誤設定**: 開始通知のスナップショットの値の意味上の範囲を、Indexer は検証しない(設計書 arch 9.3・9.13(9) のとおり。検証は Admin API だけの設計)。Admin API を経由しない経路(Crawler の設定受付への直接入力、開始通知の直接呼び出し、`loreley-sources` の直接書き込み・復元など)で範囲外の値が入ると、次のようになる。Crawler 側と設定経路で範囲を守る
  - `ratio_threshold` は 0 以上 1 未満が正しい範囲。1 以上だと、T÷D が 1 を超えないため割合ルールが働かず、TTL が経過した対象の全件が削除されうる(強制削除と同じ結果。ただし列挙の完了・件数照合・各文書の TTL の再確認は働く)。負の値は、必ず「しきい値を超える」になり、削除されない側に倒れる(対象が `min_delete_count` 以下なら先に削除される)。欠損・NaN などの挙動は設計書でも未定義
  - `min_delete_count` が大きいと、小さなソースでは対象件数がそれ以下になり、割合ルールを素通りして削除される。負の値などの挙動は未定義
  - `ttl` が 0・負値・クロール時間より短いと、今回のクロールが見た文書も削除対象になりうる(特に `min_delete_count` 以下の小さなソースでは、割合ルールも素通りする)。`ttl` に追加の条件を入れていない(ユーザー判断。設計書 arch 9.8 の式のとおり)
- **判定時の `MalformedRecordError` が待ち行列の先頭を詰まらせる**: 待機中の削除結果の必須項目の欠落など、再試行しても直らない異常があると、その結果より後ろの全ソースの削除が止まる(削除しない側に倒れる。遅れるだけで安全)。外部からの改変かバグのときだけ起きる。**WARNING `deletion processing failed: crawl_id=... error=MalformedRecordError ...` を監視する**。不正な記録は一覧から除外され `running` のまま残る(record_id だけがログに出る)
- **判定フェーズの全体異常**(OpenSearch の障害など): 結果は `running` のまま、走査ごとにやり直す。待ちは `DELETION_POLL_INTERVAL_SECONDS` から倍々で `DELETION_POLL_BACKOFF_MAX_SECONDS` まで伸ばし、連続失敗の 1・2・4・8… 回目だけ WARNING を出す。連続失敗で `failed` にはしない(上限なし)
- **要約**: 7 章のとおり、LLM 未実装のため有効化できない・先頭の一部だけを要約する・メンテナンス解除後の再開が最悪で上限間隔遅れる
- **巨大な HTML の処理時間**: 小さな要素が大量にある 20 MiB 級の HTML は、抽出に約 40 秒かかる(同じ大きさのテキストは約 0.5 秒)。登録はソース単位のロックを握ったまま抽出するため、その間、同じソースの `last-seen` と登録が待たされ、Crawler のタイムアウトと再送が重なりうる(正しさには影響しない)
- **抽出**: 対応は txt・Markdown・HTML・PDF。文字コードは UTF-8(BOM 可)の厳密デコード → CP932 の厳密デコードのみで、どちらも失敗すれば `extract_failed`(UTF-16・EUC-JP などの誤判定は完全には防げず、文字化けした本文として登録されうる)。日本語 PDF の抽出品質は未検証
- **メンテナンスフラグの不正値は fail-closed**(6 章)。形式は Crawler 設計の確定時に再確認する。不正値のままだと削除と要約の書き戻しが止まり続ける
- **`ValueError`**: ドメインの形式不正以外の `ValueError`(バグなど)も 400 `invalid_request` になり、Crawler には「リクエスト不正」としか伝わらない。サーバ側の手がかりは WARNING `domain rejected the request: error=... origin=ファイル:行 関数名`
- **ログ**: `opensearch`・`opensearchpy`(`.trace`・`.helpers` を含む)・`urllib3` のロガーは**ERROR 以上しか出ない**(ID を含む URL・本文を出さないため。`LOG_LEVEL=DEBUG` でも同じ)。ライブラリ由来の警告(接続の死活など)は出ない。500 のログは `error`・`error_type`・`origin` だけを出す。`crawl_id` は本文でも秘密でもないジョブ ID なので、`crawl_runs` のログ(削除の完了・失敗、未知の `crawl_id` の終了通知など)には出る。API 層のログには ID を出さない
- **404 の応答が JSON の配列・文字列・`null` のとき**(`Content-Type: application/json`): opensearch-py が想定外の例外(`AttributeError`)を送出し、通常の失敗の経路(`TransportError`)を外れる。API では 500 `internal_error` になる(ログは `origin` だけで、本文・ID は出ない)。OpenSearch 本体はこの形を返さないが、プロキシ・誤設定のエンドポイントが返しうる。実機確認(U-31)の対象
- **同一の `crawl_id`** を別の `source_id` で同時に開始通知すると、結果の作成が競合しうる(`crawl_id` はジョブ ID で一意という前提。単一 Crawler の MVP では起きない)

## 10. テスト方針

単体テストのみ(`uv run pytest`)。

- OpenSearch アクセス層と LLM は**インメモリの fake** に差し替える(`tests/fakes/`)。fake は `_seq_no` の楽観ロック、refresh による可視性、`delete_by_query` の競合を模擬し、409 の再現や割り込みのフック、応答の差し替え、実行ゲートを備える。時計は固定
- OpenSearch の実クライアント(opensearch-py)を通る経路(ログへの漏洩、404 の本文の形の分類、接続エラー)は、**127.0.0.1 のローカル HTTP スタブ**で確認する(`tests/infrastructure/opensearch/`)
- 競合・順序の問題は、実際の同時実行に頼らず、フック・ゲート・直列キュー制御で決定的に再現する(arch 16.1)。起動順・ログ・API は FastAPI の `TestClient` で確認する
- ログへの本文・秘密情報の漏洩(R9)は、センチネル文字列を使って全ロガーの出力を検査する(起動時の設定エラーは、`python -m loreley_indexer.main` を子プロセスで起動して標準エラー出力も検査する)。依存ルール(module の R1〜R9)は import を AST で検査する(R6〜R8 は部分検査)
- **fake の限界**: fake は設計書の理解を再現したもので、実 OpenSearch と食い違うことがある。U-31 の一部(painless の Update、日時の正規化と date 型での受理、`update` の 404 の本文、ソース削除の `delete_by_query` と実行前 refresh、`search_after` と `document_id` のソート)は結合テスト(OpenSearch 2.19.7 と 3.9.0、`tests/integration/indexer/`)で実機確認した(結果は `docs/v0.x/test-results/indexer-integration.md`)。次は実機でしか確認できず、**未実施(U-31)**: 競合(409)時の `_seq_no` による楽観ロックの動作と存在しない文書への `if_seq_no` 付き操作の応答(基本の `if_seq_no` 条件付き操作は確認済み)、`delete_by_query` の再実行の上限の数値(K48)、`delete_by_query` の競合と `version_conflicts`・タイムアウトの再送抑止、`retry_on_conflict`、`_reindex`、シャードの部分失敗の応答形(refresh・検索・件数)、404 の本文の形のうち `result:not_found` と、`update` 系・書き込み系の `index_not_found_exception`(`update` の `document_missing_exception` と `found:false` は確認済み。Status API の GET での `index_not_found_exception` は手動で再現して観測した。結果は `docs/v0.x/test-results/indexer-integration.md`)。なお「`Instant` で比較しているか」までは、結合テストでは判別できない(Indexer が固定幅 UTC・ミリ秒へ正規化してから比較するため、文字列比較と同値)。実 LLM・実 Crawler との接続、実 uvicorn 経由の接続切断も未確認
- Dockerfile は、ビルドと同じ手順(`uv sync --locked --no-dev --no-install-project`、起動、`/healthz`、SIGTERM)をローカルで再現して確認した。`docker build apps/indexer` は成功し、イメージの非 root での実行・依存(dev 依存と `uv` を含まない)・`HEALTHCHECK` の定義・URL 未設定での起動エラー(秘密値が出ない)を確認した。ベースイメージ(Python 3.12.16)のコンテナ内で全テストが通ることも確認した。OpenSearch に接続しての実コンテナの起動は、compose(`deploy/compose/`、OpenSearch 2.19.7 と 3.9.0)で確認した(結果は `docs/v0.x/test-results/indexer-integration.md`)
