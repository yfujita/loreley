# Loreley Crawler

社内ドキュメントのデータソースを巡回し、Indexer に登録を依頼するコンポーネント。ジョブ・ロック・リースの管理、削除(ソース削除ジョブを含む)の起動と結果の確認、定期起動を担う。設計は `docs/v0.x/system-design/crawler/` の最新版(`crawler-architecture-v0.4.md`(以下 arch)、`crawler-api-v0.4.md`(以下 api)、`crawler-module-structure-v0.5.md`(以下 module)、`crawler-design-decisions-v0.4.md`、Connector は `connector/` の interface・file-system・web の v0.3)を正とし、本書は起動・設定・運用の要点をまとめる。

**設計書の位置づけ**: これらの設計書は、2026-11-16 にユーザーが現行版全体を承認した(`-P-` は**承認済みの案**。案を変えるにはユーザー判断が要る)。ただし「確定」(`-K-` の ID)は従来どおりユーザー回答・既承認文書の引用だけで、承認は確定への格上げでも仮値の確定でもない。承認の対象は decisions v0.3 の4章の10件(と CM-U-4・CA-U-3)を含み、それ以外の未決(`-U-`)は未決のまま(例: CA-U-18 実機確認、arch U-24 フラグの書き込み手段)。実装で決めた内容は設計書の新版に反映済みで、承認の対象ではない(各設計書の冒頭参照)。ID の接頭辞は、`CA-`=arch、`CAPI-`=api、`CM-`=module、`CFS-`=FileSystem Connector 設計書、`CI-`=Connector interface 設計書。本書で「案」と書いた挙動は承認済みの案を指す。未決と書いた挙動は変わりうる。

**作業記録への参照**: 採用した案の一覧・仮値一覧・決めた内容・持ち越し一覧・最終検証の結果は、`agent_tasks/20261113_implement_crawler/0021-final-summary.md`(P9 完了後の最終整理。作成時点の記録で、案が変わっても更新されない)にある。設計書の改版依頼は、同じ作業記録の §5(0006〜0020 の各作業記録の改版依頼を指す)に集約されていたもので、2026-11-16 に設計書の新版(arch v0.4・api v0.4・module v0.5・decisions v0.4・connector v0.3)へ反映した(`0023-approve-and-revise-design.md`)。

**用語**: 本書で「Crawler の HTTP API」は、Crawler が公開する 6 つの API(クロール起動など。api)と `GET /healthz` を指す。製品の Admin API(`apps/api`。管理者向けの窓口)とは別で、Crawler の HTTP API は Admin API から呼ばれる。

## 1. 概要

- **責務**: データソース(MVP は FileSystem)の列挙・取得、Indexer への開始通知・`last-seen`・バッチ登録・終了通知、削除結果の確認(Status API のポーリング)、ジョブとソース単位のロック(リース+ハートビート)の管理、ソース削除ジョブ(arch 8章)、定期起動(Scheduler)、Crawler の HTTP API(Admin API から呼ばれる)の受け口
- **MVP の前提**: 単一ホスト・単一 Crawler・直列実行(Job Runner は 1 スレッドで、ジョブを 1 件ずつ実行する)・認証なし。ソース単位のロック・Job Runner・取り消し要求・起床通知はプロセス内にあり、**複数プロセス・複数 Crawler は対象外**
- **認証・認可がない**: Crawler の HTTP API(クロール・ソース削除ジョブの起動、ロック解放、設定の登録・更新)は、内部ネットワークにだけ置き、ホストや外部に公開しない(api 3.1)
- **他モジュールとの関係**: Indexer と HTTP で直接通信する(メッセージブローカーなし)。OpenSearch の `loreley-sources`(データソース設定。Crawler だけが書く)と `loreley-jobs`(ジョブ・ロック・スキップ記録・原本サイズ超過記録。Crawler が書く。メンテナンスフラグは**読み取りのみ**)に読み書きする。検索インデックスと `loreley-deletions` は読まない・書かない(Indexer だけが書く)。**索引とマッピングは作らない**(作成は `opensearch-init`。9 章)
- **削除の判断・実行はしない**: 削除は Indexer の Deletion Manager が行う。Crawler は終了通知(列挙の完了と件数)を送り、結果を確認するだけ
- **スコープ外**: Web Connector(MVP は FileSystem のみ)、infra の前提作業(9 章)、結合テスト(8 章)
- **現在のステータス**: 単体テストのみ。実 OpenSearch・実 Indexer・実機の FileSystem・実 compose での動作は未確認(8 章)。infra の前提作業が済むまで実環境では動かない(9 章)

## 2. 構成

`src/loreley_crawler/` 以下のモジュールと、依存の向き(module 3章・6章。呼び出しは上から下へだけ)。

| モジュール | 役割 |
| --- | --- |
| `main.py` | エントリポイント(composition root)。組み立て、起動順・停止順、起動時の回復の呼び出し、スレッドの起動、Job Runner への実行対象(`crawl`・`source_delete`)の注入 |
| `config.py` | 環境変数の読み込みと、起動時の整合性検査(4 章) |
| `api` | Crawler の HTTP API(6 つ+`GET /healthz`)の受け口。形式の検証と受け渡しだけで、業務判断をしない |
| `scheduler` | 定期起動の時刻の判定と、受付の呼び出し |
| `sources` | `loreley-sources` のデータソース設定の登録・更新・読み取り・削除と、値の検証 |
| `jobs` | ジョブの記録(`records/`)、ロックとハートビート(`locks/`)、受付・取り消し・ロック解放・起動時の回復・Job Runner |
| `crawl` | クロールジョブの実行(列挙・`last-seen`・取得・バッチ登録・終了通知・ポーリング、リトライとスキップの判断) |
| `source_delete` | ソース削除ジョブの実行(arch 8.1 の順 0〜6) |
| `documents` | Connector の結果を Crawler の規則に合わせる共通処理(識別子の規則、`document_id`、`content_hash`、重複除去) |
| `connectors` | データソースの列挙・取得(`interface/` に型、`filesystem/` に FileSystem)と、`connector_type` から実装を引くレジストリ |
| `infrastructure/opensearch` | Store 層の Repository(取得・作成・版条件つきの置き換えと削除・一覧・全件走査・バルク削除) |
| `infrastructure/indexer_client` | Indexer の HTTP API のクライアント(urllib3) |
| `common` | 時計・日時・リトライ・ログ・表示用の文字列整形・エラー型(他に依存しない葉) |

依存(許可される import): `api`・`scheduler` → `jobs`・`sources`、`jobs` → `sources`・`opensearch`、`sources` → `opensearch`・`connectors`、`crawl` → `jobs`・`sources`・`documents`・`connectors`・`indexer_client`、`source_delete` → `jobs`・`sources`・`indexer_client`、`documents` → `connectors`。`jobs` は `crawl`・`source_delete` を import しない(実行対象は `main.py` が渡す)。`connectors` は他のモジュールに依存しない。**この規則は `tests/architecture/` が import を AST で検査する**(module の R1〜R7・R10。R7 は「`main` が作る Repository は 3 つ(`loreley-sources` 用・`loreley-jobs` 用・ハートビート専用)」の検査を含む)。

実行の単位(単一プロセス・4 つ): HTTP ハンドラ(uvicorn。同期ハンドラ)、Job Runner(1 スレッド)、ハートビート(1 スレッド。ロック文書のリース更新)、Scheduler(1 スレッド)。

## 3. 起動方法

### ローカル

Python 3.12 と [uv](https://docs.astral.sh/uv/) を使う。必須の設定が 3 つある(4 章)。

```sh
cd apps/crawler
uv sync
LORELEY_CRAWLER_OWNER=crawler-1 \
LORELEY_CRAWLER_OPENSEARCH_URL=http://localhost:9200 \
LORELEY_CRAWLER_INDEXER_URL=http://localhost:8000 \
  uv run python -m loreley_crawler.main
```

`python -m loreley_crawler.main` は単一プロセスで uvicorn を起動する(`--workers`・`--reload` は使わない)。既定の待ち受けは `127.0.0.1:8001`(Indexer の 8000 と重ならない)。

### Docker

ビルドコンテキストは `apps/crawler`。

```sh
docker build -t loreley-crawler apps/crawler
docker run --restart unless-stopped \
  --network <OpenSearch・Indexer と共通のネットワーク> \
  --stop-timeout 30 \
  -v /path/to/documents:/data/documents:ro \
  -e LORELEY_CRAWLER_OWNER=crawler-1 \
  -e LORELEY_CRAWLER_OPENSEARCH_URL=http://opensearch:9200 \
  -e LORELEY_CRAWLER_INDEXER_URL=http://indexer:8000 \
  loreley-crawler
```

- **認証がないので、外部に公開しない**(1 章)。上の例は、ポートを publish していない。Crawler の HTTP API を呼ぶ側(Admin API など)と同じ Docker ネットワークに置く。ホストから確認するなら、ループバックだけに publish する(`-p 127.0.0.1:8001:8001`)。`0.0.0.0` への publish(`-p 8001:8001`)はしない
- `--rm` は、再起動ポリシーと併用できない(Docker がエラーにする)ので付けていない。`--network` は、`http://opensearch:9200` のような名前を解決するために指定する
- **`FileSystem Connector` が読むディレクトリは `:ro` でマウントする**(上の例の `-v ...:ro`)。Crawler は検索対象のファイルを書き換えない。マウント先のパスは、データソース設定の `connector_config` の `root` に書く(Connector 文書 `connector-file-system-v0.3.md`。5 章の例)
- **マウントしたファイルの権限**: Crawler は uid/gid 10001 で動く。マウントするディレクトリ・ファイルは、uid 10001(または others)が読める権限にする(ディレクトリは実行権限も)。ディレクトリが `0700`(他の所有者)だと列挙が失敗し、`0600` のファイルは `fetch_permission_denied` で、その文書だけスキップ(記録を残す)になる。ホスト側の権限を変えたくなければ、compose の `user:`(`docker run --user`)で、ファイルの所有者に合わせる
- OpenSearch に到達できない・設定が不正だと、起動時の処理(6 章)が失敗してプロセスが異常終了(終了コード非 0)する。再起動ポリシー(`--restart unless-stopped` など)を付ける。Compose なら、OpenSearch の `depends_on`(`condition: service_healthy`)と、索引を作る `opensearch-init` の正常終了(`service_completed_successfully`)で起動を待たせる。Indexer の起動は待たない(接続エラーはリトライの対象。arch 2.4)
- イメージは Python 3.12(slim。ベースイメージはタグとダイジェストで固定。Indexer と同じ値。運用は `Dockerfile` の冒頭のコメント)で、依存は `uv.lock` から入れる(dev 依存は含まない)。**非 root(uid 10001、ユーザー名 `crawler`)** で動く。ビルドツールは最終イメージに含まれない
- コンテナでは `LORELEY_CRAWLER_HTTP_HOST=0.0.0.0` が設定済み(既定の `127.0.0.1` では外から届かない)。`LORELEY_CRAWLER_HTTP_PORT` を変えたら、公開するポートも合わせる
- 接続先・認証情報などの設定は、イメージに焼き込まず実行時に環境変数で渡す(Docker の secrets や `_FILE` 形式は読めない)。環境変数は `docker inspect` で見えるので、その権限を絞る
- `HEALTHCHECK` は `GET /healthz`(間隔 15 秒、タイムアウト 5 秒、再試行 3 回)。**起動時の回復(OpenSearch への読み書き)が終わるまで接続自体できない**ため、`--start-period` を **180 秒**にしている(6 章)。起動が遅い環境や、タイムアウト・リトライの設定を伸ばしたときは、`--start-period` も伸ばす(`docker run --health-start-period 300s`、compose なら `healthcheck.start_period: 300s` で上書きできる)。`HEALTHCHECK` のホストは `127.0.0.1` 固定で、`HTTP_HOST` を特定の IP や IPv6 に変えるなら、`HEALTHCHECK` も合わせる
- 停止は SIGTERM(`docker stop`)。**停止の猶予は 30 秒以上にする**(Docker の既定 10 秒では足りないことがある。6 章。上の例の `--stop-timeout 30`)

### 開発

```sh
cd apps/crawler
uv sync                      # dev 依存(pytest、ruff、httpx2)を含めて入れる
uv run pytest
uv run ruff check
uv run ruff format --check
uv lock --check              # uv.lock が pyproject.toml と一致していること
```

`httpx2` は FastAPI の `TestClient` が要求するテスト用の依存で、本番イメージには含まれない。

`cronsim`(定期起動の cron 式の解釈。5 項目の厳密なパーサ)は本番の依存で、公開から 2 週間以上経った 2.7 を `>=2.7,<2.8` で固定している(2.8 は 2026-11-05 の公開。上げるときは、公開から 2 週間以上経ってから、テストを通して範囲を広げる)。

## 4. 設定(環境変数)

設定は環境変数のみ(`.env` は読まない)。接頭辞は `LORELEY_CRAWLER_`(下の表では省略)。値の形式が不正、または整合性検査に違反すると起動に失敗する。

**必須は 3 つ**: `OWNER`・`OPENSEARCH_URL`・`INDEXER_URL`。未設定だと、`invalid settings: LORELEY_CRAWLER_OWNER: missing; ...` のように、**環境変数名と検証の種別だけ**を標準エラー出力に出して終了する(終了コード 1)。値は、秘密値(`OPENSEARCH_PASSWORD` など)の漏洩を防ぐため出さない。

**数値の既定値は設計書で未決のため仮値**(arch 11章。ジッタの割合 0.2、HTTP の待ち受け `127.0.0.1:8001`、Store 層・ハートビート専用のタイムアウト、停止の待ちなど、設計書にない仮値も含む)。実測して決める前提で、無制限のリトライにならないよう、リトライは必ず有限にしている。

### 必須・接続・HTTP・ログ

| 環境変数 | 既定 | 説明 |
| --- | --- | --- |
| `OWNER` | (必須) | Crawler の安定した ID。再起動の前後で同じ値にする(ロックの所有者。256 バイト以内・制御文字なし) |
| `OPENSEARCH_URL` | (必須) | Store 層の OpenSearch の URL。認証情報を URL に埋め込めない(次の項目で渡す) |
| `INDEXER_URL` | (必須) | Indexer の URL(パス・クエリなし) |
| `HTTP_HOST` | `127.0.0.1` | 待ち受けアドレス(コンテナのイメージでは `0.0.0.0`) |
| `HTTP_PORT` | `8001` | 待ち受けポート(1〜65,535) |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR`(小文字も可) |
| `OPENSEARCH_USERNAME` / `OPENSEARCH_PASSWORD` | 未設定 | Basic 認証。両方を指定するか、両方なし。パスワードは秘密値(ログでは伏せる) |
| `OPENSEARCH_VERIFY_CERTS` | `true` | TLS 証明書の検証 |
| `OPENSEARCH_CA_CERTS_PATH` | 未設定 | CA 証明書のパス |
| `OS_STORE_REQUEST_TIMEOUT_SECONDS` | `30.0` | Store 層の通常のリクエストのタイムアウト(秒) |
| `OS_HEARTBEAT_REQUEST_TIMEOUT_SECONDS` | `10.0` | ハートビート専用クライアントのタイムアウト(秒) |
| `SOURCES_INDEX_NAME` / `JOBS_INDEX_NAME` | `loreley-sources` / `loreley-jobs` | 索引名。2 つは別の名前にする(同じだと起動に失敗する。記録 ID の衝突を防ぐため)。**`JOBS_INDEX_NAME` は、Indexer の `LORELEY_INDEXER_JOBS_INDEX_NAME`・`opensearch-init` の `JOBS_INDEX_NAME` と同じ値にする**(Indexer はロックとメンテナンスフラグをここから読む) |
| `SCAN_PAGE_SIZE` / `SCAN_PIT_KEEP_ALIVE_SECONDS` / `SCAN_REQUEST_TIMEOUT_SECONDS` / `BULK_DELETE_BATCH_SIZE` | `1000` / `60` / `60.0` / `1000` | 全件走査(PIT+`search_after`)とバルク削除 |

### Indexer への要請

| 環境変数 | 既定 | 説明 |
| --- | --- | --- |
| `INDEXER_CONNECT_TIMEOUT_SECONDS` | `10.0` | 接続のタイムアウト(秒) |
| `INDEXER_START_TIMEOUT_SECONDS` / `INDEXER_FINISH_TIMEOUT_SECONDS` / `INDEXER_STATUS_TIMEOUT_SECONDS` | `30.0` | 開始通知・終了通知・Status |
| `INDEXER_LAST_SEEN_TIMEOUT_SECONDS` | `60.0` | `last-seen` |
| `INDEXER_REGISTER_BATCH_TIMEOUT_SECONDS` | `300.0` | バッチ登録 |
| `INDEXER_DISCARD_DELETIONS_TIMEOUT_SECONDS` | `600.0` | ソース削除 1(破棄) |
| `INDEXER_DELETE_DOCUMENTS_TIMEOUT_SECONDS` | `4200.0` | ソース削除 2(文書の全削除) |
| `INDEXER_DELETE_DELETION_RECORDS_TIMEOUT_SECONDS` | `60.0` | ソース削除 3(削除記録の削除) |
| `RETRY_MAX_ATTEMPTS` / `RETRY_INITIAL_BACKOFF_SECONDS` / `RETRY_BACKOFF_MULTIPLIER` / `RETRY_MAX_BACKOFF_SECONDS` / `RETRY_JITTER_RATIO` | `3` / `1.0` / `2.0` / `30.0` / `0.2` | リトライ(最初の 1 回を含む試行回数、待ちの初回・倍率・上限、ジッタの割合) |

### Indexer の上限(起動時の整合性検査用)

Indexer のリクエストの上限(超えるとリクエスト全体が 400 になる)を、Crawler の値と突き合わせるために渡す。**Indexer の設定名(`LORELEY_INDEXER_` を除いた名前)の前に `INDEXER_` を付けた名前**で読む(CM-U-9 の仮置き(a)。Crawler 自身の `LORELEY_CRAWLER_MAX_RAW_BYTES`(原本 1 件の上限)と取り違えないため)。Indexer に渡した値と**同じ値**を渡す。

| 環境変数 | 既定 | 対応する Indexer の設定(`LORELEY_INDEXER_...`) | 比べる Crawler の値 |
| --- | --- | --- | --- |
| `INDEXER_MAX_RAW_BYTES` | 未設定 | `MAX_RAW_BYTES` | `MAX_RAW_BYTES`(原本 1 件) |
| `INDEXER_MAX_BATCH_DOCUMENTS` | 未設定 | `MAX_BATCH_DOCUMENTS` | `BATCH_MAX_DOCUMENTS` |
| `INDEXER_MAX_BATCH_BYTES` | 未設定 | `MAX_BATCH_BYTES` | `BATCH_MAX_RAW_BYTES` |
| `INDEXER_MAX_REQUEST_BODY_BYTES` | 未設定 | `MAX_REQUEST_BODY_BYTES` | `BATCH_MAX_RAW_BYTES` の 4/3 倍(base64 後) |
| `INDEXER_MAX_LAST_SEEN_IDS` | 未設定 | `MAX_LAST_SEEN_IDS` | `LAST_SEEN_MAX_IDS` |
| `INDEXER_SKIP_OVERSIZE_ID_LIMIT` | 未設定 | `SKIP_OVERSIZE_ID_LIMIT` | `FINISH_ID_LIST_WARNING_THRESHOLD` |

- **未設定の項目は、警告を出して、その項目の検査を省略する**(起動は続く。警告は、検査を省略した項目の名前だけを出す)。Indexer は既定値で動くことが多いので、Indexer の上限を環境変数で変えていないときも、本番では上の 6 つを Indexer の実際の値に合わせて渡すこと(検査が素通りすると、上限超過が本番のジョブの途中の 400 で初めて分かる)

### ジョブ・ハートビート・Scheduler・実行

| 環境変数 | 既定 | 説明 |
| --- | --- | --- |
| `RUNNER_SCAN_INTERVAL_SECONDS` | `5.0` | Job Runner の走査間隔(秒。起床通知の取りこぼし対策) |
| `ADMITTING_LOCK_GRACE_SECONDS` | `60.0` | 受付の途中とみなすロックの長さ(秒) |
| `HEARTBEAT_LEASE_SECONDS` / `HEARTBEAT_INTERVAL_SECONDS` / `HEARTBEAT_RETRY_INTERVAL_SECONDS` / `HEARTBEAT_STOP_TIMEOUT_SECONDS` | `300` / `100` / `10` / `30` | リース・更新間隔・更新失敗の再試行間隔・停止の待ち(秒)。再試行間隔 < 更新間隔 < リース。停止の待ち ≥ `OS_HEARTBEAT_REQUEST_TIMEOUT_SECONDS` の 2 倍 |
| `SCHEDULER_CHECK_INTERVAL_SECONDS` | `30.0` | Scheduler の判定周期(秒) |
| `TIMEZONE` | `UTC` | 定期起動の `schedule_cron` を解釈するタイムゾーン(IANA 名。例 `Asia/Tokyo`。全ソース共通)。不正な名前は起動に失敗する(`invalid scheduler settings: timezone must be an IANA time zone name`。値は出さない)。`UTC` は OS のタイムゾーンデータを使わない。ほかの名前のデータはイメージの OS(`/usr/share/zoneinfo`)のものを使う。夏時間のある TZ の存在しない時刻(春)は cronsim に従い、2 回ある時刻(秋)は 1 回だけ起動する |
| `CHUNK_SIZE` | `500` | チャンクの文書数 |
| `LAST_SEEN_MAX_IDS` | `500` | 1 回の `last-seen` の `document_ids` の件数 |
| `BATCH_MAX_DOCUMENTS` / `BATCH_MAX_RAW_BYTES` | `20` / `33554432`(32 MiB) | バッチ登録 1 回の文書数・原本の合計バイト数 |
| `CONSECUTIVE_SKIP_LIMIT` | `20` | 連続スキップでジョブを `failed` にする件数 |
| `INVALID_ID_EXAMPLE_LIMIT` | `20` | 識別子エラーの例として記録する件数 |
| `FINISH_ID_LIST_WARNING_THRESHOLD` | `8000` | 終了通知の ID 一覧(スキップ・サイズ超過)の合算件数の警告閾値 |
| `POLLING_INTERVAL_SECONDS` / `POLLING_TIMEOUT_SECONDS` / `POLLING_MAX_CONSECUTIVE_FAILURES` | `5.0` / `1800.0` / `3` | 削除結果(Status)のポーリング |
| `WARNINGS_MAX_ENTRIES` / `PREVIOUS_CRAWL_LOOKUP_JOBS` | `20` / `10` | ジョブの `warnings` の件数上限・0 件列挙の警告のために見る過去のジョブの件数 |
| `MAX_RAW_BYTES` | `20971520`(20 MiB) | **Crawler 自身の**原本 1 件の上限(`INDEXER_MAX_RAW_BYTES` とは別。取り違えない) |
| `MAX_ENUMERATED_DOCUMENTS` / `DISPLAY_MAX_CHARS` | `500000` / `200` | 列挙の上限件数・ログと応答に出す文字列の長さ |
| `FS_MAX_PATTERNS` / `FS_MAX_PATTERN_BYTES` / `FS_READ_CHUNK_BYTES` / `FS_MESSAGE_PATH_MAX_CHARS` | `100` / `1024` / `1048576` / `200` | FileSystem Connector(パターンの数・長さ、読み取りの単位、説明文のパスの長さ) |

### 起動時の整合性検査

次を満たさないと、OpenSearch への接続・起動時の回復・HTTP の受け付けのどれも始めずに、起動に失敗する(arch 10章)。違反は、項目名と数値だけを出す(Indexer の上限・ハートビートの停止の待ちは、まとめて `startup consistency check failed: max_raw_bytes=20971520 exceeds MAX_RAW_BYTES=1000` の形式)。ハートビートの大小関係は `invalid heartbeat settings: require 0 < retry_interval < interval < lease`、索引名の同一は `startup consistency check failed: sources_index_name and jobs_index_name must differ`(数値なし)。

- Crawler の値 ≤ Indexer の上限(前節の表。上限を渡した項目だけ)
- `MAX_RAW_BYTES` ≤ `BATCH_MAX_RAW_BYTES`(原本 1 件がバッチに入らないと、上限内の文書が登録できない)
- `HEARTBEAT_STOP_TIMEOUT_SECONDS` ≥ `OS_HEARTBEAT_REQUEST_TIMEOUT_SECONDS` の 2 倍(ちょうど 2 倍は可)
- 再試行間隔 < 更新間隔 < リース(`HEARTBEAT_*`)
- `SOURCES_INDEX_NAME` ≠ `JOBS_INDEX_NAME`

## 5. API

契約の詳細(項目・条件・冪等性・エラー)は api(`crawler-api-v0.4.md`)を参照。**パスとメソッドは設計書の承認済みの案**(CAPI-P)のとおり(エンドポイントの追加・変更は設計書の改版が先)。ヘルスチェック用の API を**置くこと自体はユーザー確定**(CAPI-K-9)。パス・応答の形は承認済みの案(CAPI-P-19・27)。

| API | メソッドとパス | 成功時の応答 |
| --- | --- | --- |
| クロール起動 | `POST /sources/{source_id}/crawl-jobs` | 202(受け付けたジョブ)。`force_delete`・`rewrite_mode` を指定できる |
| ソース削除ジョブ起動 | `POST /sources/{source_id}/delete-jobs` | 202(受け付けたジョブ) |
| 取り消し | `POST /jobs/{job_id}/cancel` | 200(`queued` を取り消した)、202(`running` への取り消し要求を受けた。完了はジョブ記録で確認) |
| ロック解放 | `DELETE /sources/{source_id}/lock` | 200(ロックがなければ何もしない) |
| 設定の登録 | `POST /sources` | 201(同じ内容の再送は 200) |
| 設定の更新 | `PUT /sources/{source_id}` | 200 |
| ヘルスチェック(契約外。**案**) | `GET /healthz` | 200 `{"status": "ok"}` |

- エラー本文は共通形式 `{"error": {"code", "message", "retryable", "details"?}}`。`message` は固定文か、検証エラーの位置と型だけで、リクエストの値(本文・設定の中身・秘密値)は含まない。拒否は 404(`source_config_not_found`)、409(`source_deleting`・`maintenance_enabled`・`lock_held` など)、400(`invalid_request` など)、503(Store 層が使えない。`retryable=true`)、500(想定外)
- **`GET /healthz` は、6 つの API に数えない運用上の API**(置くことは確定、パス・応答の形は承認済みの案。上記)。ジョブ・設定・OpenSearch・Indexer の状態を調べず、200 を返すだけ。**起動時の回復が終わるまで、接続自体できない**(HTTP を開くのが回復の後のため。6 章)
- 設定の取得・一覧、ジョブの状態の取得、メンテナンスフラグの操作、設定レコードだけの削除の API はない(ジョブ状態・削除結果は、Admin API が `loreley-jobs`・`loreley-deletions` を読み取りのみで直接読む設計。api 1章)。**データソース設定の取得・一覧の経路は未決**(CAPI-U-2)。確認の手段は 6 章の curl の例(OpenSearch への直接の読み取り)
- 取り消しの対象は `crawl` ジョブだけ。`source_delete` ジョブは状態を問わず 409 `job_not_cancellable`(終了済みのジョブは 409 `job_already_finished`、存在しなければ 404 `job_not_found`)。ロック解放は**実行中でない**ロック(リース切れ・孤児ロック)だけで、実行中のジョブのロックは 409 `lock_in_use`(api 4.2・4.3)
- 定期起動は Scheduler が内部で行い、API ではない。定期起動は `force_delete`・`rewrite_mode` を常に `false` にする

### 最初の一歩: データソースの登録とクロールの起動

Crawler の HTTP API は、Crawler の内部ネットワークから呼ぶ(以下は、`<crawler>` をコンテナのホスト名とポート(例 `crawler:8001`)に置き換える)。データソース設定の登録(`POST /sources`)。必須の項目は `source_id`・`connector_type`・`connector_config`・`ttl`・`ratio_threshold`・`min_delete_count`。`schedule_cron` は省略または `null` で、定期起動なし(手動のみ)。

```sh
curl -X POST "http://<crawler>/sources" -H 'Content-Type: application/json' -d '{
  "source_id": "docs-share",
  "connector_type": "file_system",
  "connector_config": {"root": "/data/documents"},
  "ttl": 2592000,
  "ratio_threshold": 0.3,
  "min_delete_count": 10,
  "schedule_cron": "0 3 * * *"
}'
```

- `connector_config` の項目(`root`・`include_patterns`・`exclude_patterns`・`follow_symlinks`・`include_hidden`)は FileSystem Connector 設計書(`connector-file-system-v0.3.md`)。`root` は、コンテナ内の絶対パス(`:ro` マウント先。3 章)。`ttl` は期限の秒数(例は 30 日)。`ratio_threshold`・`ttl`・`min_delete_count` は削除の判定に使う値で、Crawler は範囲を検証しない(0 以上 1 未満など。設計書では Admin API の領域。誤った値の影響は、`apps/indexer/README.md` の 9 章)。
- 登録に成功すると 201(`status: active`)。同じ内容の再送は 200。例のリクエストは、`file_system` の Connector を組み込んだ API を単体テストの fake 上で動かして、201 になることを確認した。
- **定期起動を有効にする**: `schedule_cron` に、標準の 5 項目の cron 式(分 時 日 月 曜日。例の `0 3 * * *` は毎日 03:00)を指定する(登録または `PUT /sources/{source_id}` の全置換で)。秒つきの 6 項目や `@daily` などの別名は受け付けず、400(`invalid_request`。`details.errors` の `schedule_cron` が、不正な式なら `format`、文字列でなければ `type`)になる。時刻は `LORELEY_CRAWLER_TIMEZONE`(未設定は UTC。全ソース共通)の暦で解釈する。式の解釈は cronsim に任せるので、英語名(`MON`・`JAN`)や `L` などの拡張も通る。夏時間のあるタイムゾーンでの存在しない・2 回ある時刻の扱いも cronsim に従う(運用は UTC・`Asia/Tokyo` の想定)。Scheduler は、前回の判定時刻(プロセスの起動時刻から始まり、判定のたびに進む)より後で最初に式に合う時刻が現在以前なら、1 回だけ起動する。**Crawler が動いていない間(停止・再起動・起動時の回復)に過ぎた時刻は起動しない**。ロック保持中・メンテナンス中などで見送った時刻も取り返さない。直前の手動クロールや設定の更新時刻は判定に使わない
- **クロールの手動起動**: `curl -X POST "http://<crawler>/sources/docs-share/crawl-jobs"`(ボディは省略可。`{"force_delete": false, "rewrite_mode": false}` と同じ)。202 のとき、本文に受け付けたジョブ(`job_id`)が返る。進捗・結果は `loreley-jobs` のジョブ記録で確認する(Admin API が読む)。

## 6. 運用

### 起動順と起動の失敗

起動順(module 5.7。arch 10章): 設定の読み込みと整合性検査 → ログの設定 → 未設定の Indexer 上限の警告 → OpenSearch のクライアントの作成(接続はしない)→ 組み立て → **起動時の回復**(arch 5.8。前回の `running` ジョブを `failed`(`crawler_restart`)にし、不要なロックを削除する)→ Job Runner → Scheduler → HTTP の受け付け(uvicorn)。

- **回復が終わるまで、`/healthz` を含めて、どの API にも接続できない**(接続拒否に見える)。回復は OpenSearch への読み書きで、OpenSearch の応答が遅いと、1 回のリクエストが最大 `OS_STORE_REQUEST_TIMEOUT_SECONDS` × `RETRY_MAX_ATTEMPTS` + 待ち = 既定 30 × 3 + 約 3 = 約 93 秒かかる。`HEALTHCHECK` の `--start-period` は、これを踏まえて 180 秒にしている(最悪のリクエスト約 2 回分(約 186 秒)に近い値。仮値で、実測ではない)。Compose などで独自のヘルスチェックを設定するときも、同じ考え方で猶予を取る
- 設定エラー・整合性検査の違反・OpenSearch に接続できない・回復の失敗は、**HTTP を開く前に**、トレースバックを標準エラー出力に出して終了コード非 0 で終了する(メッセージに値・秘密は含まない)。再起動ポリシーに任せる

### 停止(SIGTERM)

**以下の挙動は設計書の承認済みの案**(CM-U-4。2026-11-16 に案どおり承認)。停止は SIGTERM(`docker stop`)で、uvicorn が受け付けを止め、続けて Scheduler・Job Runner に停止を要求して終了を待つ(各最大 5 秒)。

- **実行中のジョブの完了は待たず、最終状態の記録・ロックの解放といった終了処理もしない**(CM-U-4)。ジョブは `running` のまま、ロックも残り、**次回の起動時の回復が `failed`(`crawler_restart`)にしてロックを削除する**。これは承認済みの案(CM-U-4)のとおりで、データの安全性は変わらない(削除は Indexer の期限方式で、遅れるだけ)。再実行は管理者が改めてクロールを起動する
- OpenSearch・Indexer の接続は閉じない(閉じると、実行中のジョブが途中で失敗の記録を試み、「終了処理をしない」方針とずれる。プロセスの終了に任せる)
- プロセスの終了コードは 0(uvicorn が再送した SIGTERM を受け流して正常に戻る)。**PID 1 の Linux コンテナでも終了コード 0**(fake のバックエンド・実 uvicorn で確認済み)。停止処理が走ったかは、ログ `the crawler stopped` で確認できる

**停止の時間予算と `stop_grace_period`**: 停止にかかる最大の時間は、uvicorn の graceful shutdown(最大 10 秒。接続が残っているとき)+ Scheduler の停止の待ち(最大 5 秒。Scheduler のリトライの待ち最大約 3 秒を含む)+ Job Runner の停止の待ち(最大 5 秒)で、足して **最悪約 20 秒**。Docker の既定の停止猶予(10 秒)を超えうる。さらに、処理中の HTTP ハンドラ(Store 層のリトライで最大約 90 秒)があると、終了はそれだけ遅れる。uvicorn の graceful shutdown の 10 秒と、join の 5 秒は、環境変数ではなく `main.py` の固定値(仮値)で、`HEARTBEAT_STOP_TIMEOUT_SECONDS`(ロックの解放のためにハートビートの停止を待つ上限)とは別。**compose の `stop_grace_period`(`docker run` なら `--stop-timeout`)は 30 秒以上にする**(compose は別タスク)。猶予を超えて SIGKILL されても、ジョブは次回の回復で `failed(crawler_restart)` になるので、安全性は変わらない。

### メンテナンスフラグ(運用者の手動手順)

**以下の手順・形式は設計書の承認済みの案**(CA-U-3・CA-U-17 は案どおり承認。書き込み手段(arch U-24)は未決のまま)。メンテナンス(再インデックスなど。手順の全体は Indexer の arch 11章と `apps/indexer/README.md` の 8 章)では、**運用者が手動でフラグを立てる**(承認済みの案)。**Crawler はフラグを読むだけで、書かない**(Crawler の HTTP API にもフラグの操作はない)。Indexer も同じフラグを読む(登録と `last-seen` では確認せず、削除の判定・書き込み・要約の前に確認する)。

- **記録の形式**: `loreley-jobs`(`JOBS_INDEX_NAME`)の ID が `maintenance` の文書。項目は `enabled`(真偽値。Indexer の仮定義と同じ形式)。`record_type` は `maintenance`(arch 3.3 の記録種別。案。CA-P-37)。Crawler が読むのは `enabled` だけ
- **立てる**(以下の curl の `<OpenSearch の URL>` は `LORELEY_CRAWLER_OPENSEARCH_URL` の値、`<JOBS_INDEX_NAME>` は `LORELEY_CRAWLER_JOBS_INDEX_NAME` の値(既定 `loreley-jobs`)に置き換える。認証が要る OpenSearch では、`-u` などで認証情報を付ける):

  ```sh
  curl -X PUT "<OpenSearch の URL>/<JOBS_INDEX_NAME>/_doc/maintenance" \
    -H 'Content-Type: application/json' \
    -d '{"record_type": "maintenance", "enabled": true}'
  ```

- **下ろす**: 同じ文書を `"enabled": false` で置き換える(または `DELETE <OpenSearch の URL>/<JOBS_INDEX_NAME>/_doc/maintenance` で文書を消す。文書がなければ「立っていない」)
- **fail-closed**(Indexer の読み取りは設計書で確定(CA-K-18)。Crawler も同じ規則で読むのは承認済みの案): 文書があって `enabled` が**真偽値の `false` と明示されているときだけ**「立っていない」。`"false"`(文字列)・`0`・`null`・項目の欠落・真偽値でない値はすべて「立っている」とみなす(Indexer と同じ規則。形式の食い違いで、Indexer の書き込みを止めたまま Crawler だけ進む状態を作らないため)。意図せず立ったままにならないよう、下ろしたあとは文書を読み直して確認する
- **立っている間の Crawler**: クロール起動・ソース削除ジョブ起動は 409(`maintenance_enabled`)で受け付けない(定期起動も見送る)。実行中のクロールは、実行開始・開始通知・`last-seen`・バッチ登録の各試行の前と、終了通知(`enumeration_completed`)の初回送信の前の 1 回の確認で、フラグを見つけると以降の要請を止めて `failed`(`maintenance`)にする(終了通知の送信そのもの、リトライを含めては確認しない。確認点は取り消しだけ)。ソース削除ジョブは、Indexer への要請(順 1・2・4)の前だけ確認し、`failed`(`maintenance`)にして止まる(再実行で冪等に完了する)。**設定の登録・更新・取り消し・ロック解放は、フラグの影響を受けない**(api CAPI-P-17)。ソース削除ジョブの順 3(スキップ・サイズ超過記録の削除)と順 5(設定の削除)は、Crawler 自身の記録の削除なので確認しない
- **すでに始まっている書き込みは止めない**。フラグを立てる前に、実行中のジョブと Indexer の削除・要約が終わったことを確認する(Indexer の README 8 章)。終わらないときは、Crawler と Indexer を止めてから始める。Crawler 側の確認の手段(OpenSearch への読み取り。**実機では未確認**。標準の OpenSearch の API):
  - ソースのロックの有無(ロックがあれば、ジョブが実行中または受付中): `curl "<OpenSearch の URL>/<JOBS_INDEX_NAME>/_doc/lock-<source_id>"`(`"found": true` ならロックあり。404 ならなし)。ID 指定の読み取りなので、マッピングに依らず動く
  - 実行中のジョブの一覧:

    ```sh
    curl -X POST "<OpenSearch の URL>/<JOBS_INDEX_NAME>/_search" \
      -H 'Content-Type: application/json' \
      -d '{"query": {"bool": {"filter": [{"term": {"record_type": "job"}}, {"term": {"status": "running"}}]}}}'
    ```

    **9 章のとおり、現行の `jobs.json` では `record_type`・`status` が検索できないため、`jobs.json` の拡張が済むまで、0 件が返っても「実行中のジョブがない」とは言えない**(Crawler 自身の一覧も同じ条件で検索するので、同じく動かない)。拡張前は、`GET .../_doc/<job_id>`(ジョブ ID が分かるとき)と、ロックの有無で確認する

### 形式不正な記録の解消

`loreley-jobs`・`loreley-sources` の記録は Crawler だけが書くので、形式不正は通常起きない(外部からの改変かバグ)。起きたときは、fail-closed(削除・解放しない側)に倒れる。

- ロックが指すジョブ記録の `status` が形式不正だと、起動時の回復はそのロックを削除せず、ジョブ記録も変更せずに警告して続行する。管理者のロック解放も 409 `lock_in_use` になる。**解消手段は、OpenSearch で該当のジョブ記録(または孤児になったロック文書)を手で直す・削除すること**(ソース削除ジョブの再実行は解消手段にならない: ロックが残るので受付が 409 `lock_held` で拒否し、順 3 もジョブ記録・ロックを消さない。コード読みによる判断で、実機では未確認)
- `queued` の先頭のジョブ記録が形式不正だと、Job Runner はその例外をログに出して走査を続け、後続のジョブが実行されない(先頭ブロック)。該当の記録を手で直す
- 形式不正なデータソース設定は、クロールが `config_invalid` で `failed` になる。更新(`PUT`)で直せる場合がある(`status` と `connector_type` が読めるとき)

### ログ

標準エラー出力に `日時 レベル ロガー名 メッセージ` の形式で出す。

- **文書の本文・認証情報・`connector_config` の値・Indexer への要請の本文は出さない**。秘密値(`OPENSEARCH_PASSWORD`)は、メッセージに混ざっても伏せる(`***`)。識別子・パス・説明文は、切り詰めと制御文字のエスケープを通して出す
- アクセスログは、メソッド・**ルートのテンプレート**・ステータス・所要時間だけ(実際のパス(ID を含む)・本文は出さない)。`/healthz` のアクセスログは DEBUG(ヘルスチェックの間隔で、ログが増えすぎないため)
- `opensearch`・`opensearchpy`・`urllib3` のロガーは ERROR 以上しか出ない(ID を含む URL・本文を出さないため。`LOG_LEVEL=DEBUG` でも同じ)。失敗は、例外のクラス名・固定の理由名・発生箇所(`ファイル:行 関数名`)だけをログに出す
- Scheduler の見送り(ロック保持中・メンテナンス中・削除中)は DEBUG。`INFO` では出ない

## 7. テスト方針

単体テストのみ(`uv run pytest`。結合テストは本タスクのスコープ外)。

- 外部システムは**メモリ上の fake**に差し替える(`tests/fakes/`): OpenSearch(Repository。`create` と `if_seq_no` の楽観ロック、全件走査、バルク削除)、Indexer のクライアント、時計、FileSystem の OS 呼び出し(`FsOps`)。FileSystem は一時ディレクトリでも確認する。スレッドを使うテストは `Event`・固定時計・ゲートで決定的に書き、スリープに頼らない
- Indexer のクライアントは、**127.0.0.1 のローカル HTTP スタブ**で、DELETE のボディ(`lock`)が届くことなどの契約を確認する(`tests/infrastructure/indexer_client/`)。OpenSearch の実クライアントを通る経路(ログへの漏洩、失敗の分類)も、ローカルのスタブで確認する
- 起動順・API・停止は、FastAPI の `TestClient` と、`python -m loreley_crawler.main` の実プロセス(必須設定なし・整合性違反・到達不能な OpenSearch での異常終了、SIGTERM・SIGINT での終了コード 0 と停止処理)で確認する
- ログへの本文・秘密情報の漏洩(R11)は、センチネル文字列で全ロガーの出力と全エラー応答を検査する。依存ルール(module の R1〜R7・R10)は import を AST で検査する
- **skip の理由**: 次の 3 件は、**macOS(既定の大文字小文字を区別しない APFS)では skip になる**。ファイルシステムが、非 UTF-8 のファイル名、大文字小文字だけが違う名前、NFC と NFD の併存した名前を作れないため(skip メッセージに実測の理由が出る)。また、**root で実行すると、ファイルの権限エラーを再現できない 5 件が skip になる**(root は権限を無視するため)。skip 以外はすべて通ること
- **`LORELEY_REQUIRE_LINUX_NAMES=1`**: Linux 専用のテストが、環境の都合で黙って skip されないよう、skip でなく**失敗**にする(`=1` のとき、上の 3 件が作れない環境ではテストが失敗する。macOS で `=1` を付けると、3 件が失敗する)。CI や Linux では付ける

### Linux(Docker)でのテストの実行

macOS で skip になる 3 件を含めて検証するため、Linux のコンテナで、非 root(権限エラーのテストも走る)で実行する。リポジトリは `:ro` でマウントし、コンテナ内にコピーして使う(ホストを汚さない)。

```sh
cd apps/crawler
docker run --rm -e LORELEY_REQUIRE_LINUX_NAMES=1 -v "$PWD":/work:ro \
  python:3.12.16-slim-bookworm sh -c '
    set -e
    pip install -q --no-cache-dir --disable-pip-version-check --root-user-action=ignore "uv==0.13.7"
    mkdir /tmp/w
    cp -R /work/src /work/tests /work/pyproject.toml /work/uv.lock /work/.python-version /tmp/w/
    cd /tmp/w
    UV_PYTHON_DOWNLOADS=never uv sync --locked
    chmod -R a+rwX /tmp/w
    useradd -m tester
    su tester -c "cd /tmp/w && .venv/bin/python -m pytest -q -p no:cacheprovider -rs"
  '
```

`su tester` を外す(root のまま実行する)と、権限エラーの 5 件が skip になる。`:ro` でマウントするのは `apps/crawler` だけで、`pip install uv` に外部ネットワーク(PyPI)が要る。最終検証の結果は、作業記録 `agent_tasks/20261113_implement_crawler/0021-final-summary.md` にある。

## 8. fake だけでは検証できないこと(持ち越し)

**単体テストは fake・スタブ・一時ディレクトリで通っているが、次は実 OpenSearch・実 Indexer・実機のファイルシステム・実コンテナでしか確認できず、未確認**。結合テスト(Indexer の結合テストと同じ構成の compose で OpenSearch と Indexer を起動して行う。arch 12章)の対象。

**実 OpenSearch が必要**

- `create`(存在しない場合だけ成功)と `if_seq_no`(読んだ版を条件にした置き換え・削除)の**並行時の原子性**(ロックの取得・解放、ジョブ記録の更新が依存する)
- opensearch-py のクライアントの**スレッド安全性**(CM-U-1)。Job Runner・HTTP ハンドラ・Scheduler が Store 層のクライアントを共有し、ハートビートだけが専用のクライアントを持つ構成が足りているか
- **10,001 件以上**の全件走査(PIT+`search_after`)・refresh の可視性・バルク削除の**部分失敗**(architecture 12章 #37)。fake は 10,000 件の上限・PIT・refresh の遅れを再現しない。`allow_partial_search_results=false`・`allow_partial_pit_creation=false` の**サーバー側の受理**(渡し方はダミー transport で確認済み)、PIT 期限切れの**実機の応答形**(404 の `search_context_missing_exception` は fake の再現)
- 実環境の **date 型のソート・絞り込み**(`queued_at` の順の実行、受付途中のロックの判定。降順ソートの実マッピング)と、マッピング案(arch 3.1 の表。CA-P-49)との整合
- fake の限界: メモリ上の Repository は、`document_id` を持たない同種の記録が 2 件以上あるときの `non_unique_sort`(実機の一意でないソート)を再現しない

**実 Indexer が必要**

- Status API の項目(`finish_received_at` の有無、`waiting_for` の出方)、終了通知の 409 の出方、実際のポーリング間隔(5 秒)・タイムアウト(30 分)の妥当性
- バッチ登録の応答の `document_id` の照合(CM-U-3。Crawler の算出と Indexer の算出の一致)
- `FakeIndexerClient` の `delete_*` が `lock` の値を検証しない(実 Indexer はロックの所有を検証する)
- **件数照合の独立検証**: Crawler の `enumerated_count` と、Indexer 側の N_seen + E_missing の一致を、実際のクロールで確認する(Crawler の件数の不変条件は単体テストで確認済みだが、Indexer 側の独立した検算は別)

**実機のファイルシステム(FileSystem Connector)**

- 実際の NFS/SMB・Docker のバインドマウントでの、**errno・マウント外れの症状**(集合 T の妥当性)、`st_ino` の信頼性、取得中の変更の検出
- **ブロッキング I/O 中のスレッド挙動**(CFS-U-4): ハードマウントの停止などで Job Runner が戻らなくなっても、ハートビートが進み続けるか(macOS・CPython 3.13.4 では確認。Linux コンテナ・NFS/SMB は未確認)。GIL を長く保持する処理の間のハートビートも未確認
- **実運用イメージの FS エンコーディング**(`python:3.12-slim-bookworm` では UTF-8)。`:ro` マウントの実機での動作

**実コンテナ・実 compose**

- **実 OpenSearch・実 Indexer に接続し、実行中のジョブがある状態での `docker stop`**: 所要時間と、猶予(`stop_grace_period`)を超えて SIGKILL されたときの挙動(uvicorn の `timeout_graceful_shutdown`・join の上限は仮値)。PID 1 の Linux コンテナでの SIGTERM は、fake のバックエンド・実 uvicorn で終了コード 0 を確認済み(6 章)
- **`/healthz` が `healthy` になること**: 本タスクでは、必須設定なし・整合性検査違反・到達不能な OpenSearch でのイメージの異常終了(HTTP を開かない)までを確認した。実 OpenSearch・実 Indexer に接続して回復が終わり、`HEALTHCHECK` が `healthy` になるところは、結合テストに持ち越す

## 9. 前提・スコープ外(別タスク)

本タスクは `apps/crawler/` の実装で、次は**別タスク**(infra の前提作業)。**これらが済むまで、実環境では正しく動かない**。現状(`infra/opensearch/init-indices.sh` と `schema/` を読んで確認した):

- `init-indices.sh` が作る索引は、検索インデックス(エイリアス)・`loreley-deletions`・`loreley-jobs` の 3 つだけで、**`loreley-sources` は作らない**(`schema/` にも定義がない)。
- `schema/jobs.json` は `dynamic: false` で、`owner`・`job_id`(keyword)、`lease_expires_at`(date)、`enabled`(boolean)の 4 項目だけを定義している。

この状態で Crawler を動かすと、次のようになる(Crawler のコードの検索条件・並べ替えから読み取った。**実機では未確認**)。

- `loreley-jobs`: ジョブ・ロック・スキップ記録などの**書き込みと、ID 指定の取得・版条件つきの置き換え・削除は受理される**(`dynamic: false` は未定義の項目を拒否せず、索引しないだけ)。一方、`record_type`・`source_id`・`status`・`queued_at`・`job_id` などでの**絞り込み・並べ替えを使う操作が、想定どおりに動かない**。該当は、Job Runner による `queued` のジョブの検出、起動時の回復でのロックの一覧、定期起動の起点(直近のクロールジョブ)、0 件列挙の警告のための過去のジョブの取得、スキップ・サイズ超過記録の整理とソース削除(`record_type`・`source_id` での走査)。未定義の項目の条件は 0 件になるか、並べ替えが失敗するかのいずれかと推測される(未確認)。
- `loreley-sources`: 索引がない状態で書き込むと、OpenSearch の自動作成(下の `action.auto_create_index` の項目)で、動的マッピングの索引ができうる。`ratio_threshold`(double の想定)が整数の値で始まると整数に推定されるなど、arch 3.1 の案と型が違う索引になる懸念がある(未確認)。

- **`loreley-sources` の索引定義**: 現状、作成物がない。マッピングの案は arch 3.1 の表(CA-P-49)。`infra/opensearch/schema/` への追加と、`init-indices.sh`(`create_index_if_absent`)への呼び出し・索引名の環境変数の追加
- **`loreley-jobs` の定義の拡張**: 上のとおり 4 項目だけの仮定義。Crawler が並べ替え・絞り込みに使う項目(`record_type`・`source_id`・`status`・`queued_at` など。arch 3.1 の表)の追加が要る(Indexer が読む 4 項目の型は変えない)。Indexer の結合テストも同じ `jobs.json` を使うので、同時に更新する
- **既存の環境への反映**: `init-indices.sh` は索引が既にあれば何もしないため、`jobs.json` を拡張しても既存の `loreley-jobs` には入らない(put mapping か、既存ボリュームの作り直し)
- **compose の `crawler` サービス**: ヘルスチェックの設定(間隔・猶予時間)、**`stop_grace_period`(30 秒以上。6 章)**、FileSystem の対象ディレクトリの `:ro` マウント、Indexer の上限値の Crawler への受け渡し(4 章。Indexer と同じ値)、`JOBS_INDEX_NAME` を Indexer・`opensearch-init`・Crawler で同じ値にすること
- **OpenSearch の `action.auto_create_index` の無効化の判断**: OpenSearch 3.9.0 は、存在しない索引への書き込みで索引を自動作成する(実機の使い捨て確認)。Crawler は索引を作らない前提のため、`opensearch-init` が作る前に Crawler が書くと、意図しないマッピングで索引ができうる。無効化するかは infra 側の判断
- **結合テスト**(8 章)。メンテナンスフラグの書き込み手段の確定(arch U-24。現状は 6 章の手動手順(承認済みの案))

## 10. 既知の限界・運用に影響する承認済みの案と未決の挙動

**既知の限界**(いずれも、安全側に倒れるか、通常の運用では起きない)

- **リクエスト本文のサイズの上限は 10 MiB(仮値)**: ユーザー指示(2026-11-16「一旦 10M にしておこう」)で決まった(crawler-api 3.2・CAPI-P-29。「10M」は 10 MiB と解釈)。超過は 413 ではなく 400 `invalid_request`(`details` なし)。設定にはせず固定の定数(`api/request_body.py`)。変えるときは設計書の改版が先
- **ソース削除の途中で設定だけが失われたとき(競合・手作業の削除。滅多に起きない)**: 専用の復旧手順は置かない(ユーザー判断 2026-11-16。CA-U-20 を解消)。競合で受付の後に設定が消えた場合、ジョブは順 1〜4 を進めて成功する。受付は設定がなければ拒否するので再実行はできず、Indexer 側にデータが残ったときは、同じ `source_id` で設定を登録し直してソース削除ジョブを起動する(受付の条件からの導出。実機では未確認)か、Indexer 側のデータを手で削除する
- **glob 照合の最悪入力**: `include_patterns`・`exclude_patterns` の照合は多項式時間だが、細工した最悪の入力(1024 バイトのパターンと 4096 バイトのパス)で 0.2〜0.5 秒/件/パターンかかる。100 パターンを細工した場合に限り影響する。パターンは管理者が設定する値(0009)
- **終了通知 `failed` は、Store 層が使えないと送れない**: 終了通知の内容は、最初の送信の前に Store 層へ保存する。Store 層が使えないと保存できず、送れない。最終状態を記録できなかったジョブは、次回の起動時の回復まで `running` のまま残る(0014 §7)
- **回復中(`uvicorn.run` の前)の SIGTERM**: 停止処理を通らず、プロセスがそのまま終わる(`main.py` の docstring)。回復は冪等で、`running` のジョブは次回の回復が `failed(crawler_restart)` にする
- **ロック解放の応答喪失・ロックのない `running` ジョブ**: 管理者のロック解放で、削除の応答が失われると `released` の真偽が曖昧になりうる(孤児ロックのとき)。ロックを削除した後でジョブの更新が Store 異常で失敗すると、ロックのない `running` のジョブが次回の起動時の回復まで残る(ロックがないのでそのソースは新規に受け付けられる。0011 §7)
- **一覧の上限**: 実行中ジョブとロックの一覧は 10,000 件に達すると例外になる(`lock_list_truncated` など。想定規模では起きない。0011 §7)
- **`ttl`・`min_delete_count` の範囲**: 設計書は値の範囲を検証しないとしており、`api` は型(整数)だけを検証する。int64 を超える整数は、400 ではなく Store 層の書き込み失敗(500)や Indexer 側の 400 になりうる(0012 §1)。ユーザー判断(2026-11-16)で、範囲外になるケースは考えない(検証を足さない。CAPI-U-11 を解消)
- **終了通知の ID 一覧による記録の肥大**: `finish_notice`(ID 一覧を含み、最大約 8,000〜10,000 件の SHA-256)をジョブ記録に 2 回書く。HTTP API の応答には ID 一覧を含めない(0015 §6)
- **`non_unique_sort`**: 同じソース・同じ種別で `document_id` を持たない記録が 2 件以上あると、ソース削除の順 3 の走査の並べ替えが一意にならず、`failed(internal_error)` になる(安全側。`jobs/records/purge.py`)。メモリ上の fake は再現しない(8 章。0010・0016 §4-3)

**運用に影響する、承認済みの案と未決の挙動**(承認済みの案を変えるにはユーザー判断が要る。未決のものは変わりうる)

- **`source_id` の文字種**: 半角英数字で始まり、半角英数字・`.`・`_`・`-` だけ、256 バイト以内(承認済みの案。CAPI-P-15。CAPI-U-4 は文字種について案どおり承認)。これ以外の `source_id` は 400
- **`external_id` の衝突**: 規則適用後の `document_id` が同じで、元の `external_id` が異なる文書があると、ジョブは `failed`(`external_id_collision`)になる(承認済みの案。CA-P-24。CA-U-6 は案どおり承認)
- **データソース設定の取得・一覧**の経路は未決(CAPI-U-2)
- **メンテナンスフラグの書き込み手段**(6 章)は未決(arch U-24)、**停止時の扱い**(6 章。CM-U-4)は承認済みの案、**定期起動の周期の形式**(CA-U-8)は、ユーザー回答 2026-11-16 で cron 式に変更(設計書の改版は別担当)
