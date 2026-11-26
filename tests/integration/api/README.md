# 結合テスト(Admin API)

compose で起動した**実 OpenSearch・実 Indexer・実 Crawler・実 api(Admin API)・実 web(Nginx)**に対して、ホストの pytest から実行する結合テスト。テストは Admin API の HTTP(`127.0.0.1:8080`、`/api/admin/v1`)を呼び、必要に応じて OpenSearch を直接読んで期待値を独立に計算し、API の応答と突き合わせる。障害系では、`docker compose -p loreley-it stop/start` で Crawler・Indexer・OpenSearch・web を止めて戻す。

> **確認状況**: 実行結果(passed 件数・所要時間・環境・観測値)は [docs/v0.x/test-results/admin-api-integration.md](../../../docs/v0.x/test-results/admin-api-integration.md) に書く。この文書には書かない。
> macOS(x86_64)・compose v2.3.3・uv 0.13.8 でのみ確認した。Linux ホストなどは未確認。
> 2026-11-26 に、実行スクリプトを共通化し排他ロックなどを入れた版で再実行し、23 passed(終了コード 0、実行後の残骸なし。同環境。詳細は結果文書の 10 章)。

## 目的

Admin API の単体テストは、OpenSearch・Crawler・Indexer を fake やローカルのスタブに差し替えている。この結合テストは、単体テストでは確認できない次の点を実機で確かめる。重複を避けるため、入力検証の全パターン・エラーコードの全分岐・`lock_state` の全分岐・タイムアウトと再試行などは単体テストに任せ、ここでは再検証しない。

- 実 Crawler への中継(登録・更新・クロール起動・ソース削除・取消・ロック解放)と、実 Crawler・Connector が返す応答の形
- 実 OpenSearch に対するクエリ(集計・`top_hits`・`mget`・`msearch`・`ids`・並べ替え・`from`/`size`・`cat.*`)の妥当性。OpenSearch を直接読んだ独立計算の期待値と照合する
- 実行中ジョブがロックを持つ間の状態(EP-02 の `lock`、EP-09 の実行中ジョブ、409 `lock_held`・`lock_in_use`)と、取消・ロック解放
- compose が渡す共通変数・索引名・`web` の確認先 URL が api に届き、api が実 `web` の `/admin/` を確認できること
- Crawler・Indexer・OpenSearch・web の停止中の応答(読み取りの継続・書き込みの失敗・部分失敗・EP-13 の `web` の異常)と、復旧後の動作

## 前提

| 項目 | 内容 |
| --- | --- |
| Docker | Docker と docker compose v2(確認した版: compose v2.3.3)。デーモンが起動していること |
| uv | 必要(確認した版: uv 0.13.8)。`tests/integration/api/uv.lock` で依存(`pytest`・`httpx`。dev に `ruff`)を固定している。依存を変えたら、`tests/integration/api` で `uv lock` を実行して更新する |
| メモリ | Docker に**約 4GB 以上**を推奨(5 サービスが常駐する。`opensearch-init` は完了後に終了する)。この IT での Docker VM のメモリは**未記録**(既存の結合テストは約 3.8GiB で成功した)。ほかの重いコンテナを同時に動かさない。メモリ使用量は測定していない |
| ポート | ホストの `9200`(OpenSearch)・`8000`(Indexer)・`8001`(Crawler)・`8080`(api)・`8090`(web)が空いていること。すべて `127.0.0.1` だけに publish する。テストが接続するのは `8090` を除く 4 つ。`8090` を固定するのは、compose のマージは `ports` を消せず、本番用の `compose.yaml` の `web` の publish が IT でも有効になるため(`api` の `8080` は `compose.test.yaml` だけが publish する)。**スクリプトは 5 つのポートと、テストの接続先 URL(`LORELEY_IT_*_URL`)を `8090` を除く 4 つに固定**し、`deploy/compose/.env` やシェルに残った環境変数の値では変えられない(別の環境に書き込まないため)。pytest を直接実行して別のポートにしたときだけ、`LORELEY_IT_OPENSEARCH_URL`・`LORELEY_IT_INDEXER_URL`・`LORELEY_IT_CRAWLER_URL`・`LORELEY_IT_API_URL` でテストの接続先を合わせる |
| 索引名 | スクリプトは `LORELEY_JOBS_INDEX_NAME`・`LORELEY_SOURCES_INDEX_NAME`・`LORELEY_DELETIONS_INDEX_NAME`・`LORELEY_SEARCH_INDEX_ALIAS` を既定値(`loreley-jobs`・`loreley-sources`・`loreley-deletions`・`loreley-documents`)に固定する。手動で起動して索引名を変えたときは、**同じ環境変数を pytest にも渡す**(未指定は既定値) |
| ネットワーク | 初回は、ベースイメージ・OpenSearch のイメージ・Python の依存・npm の依存を取得し、`apps/api`・`apps/crawler`・`apps/indexer`・`apps/web` をビルドする。**`web` は実物のビルド(`apps/web` の Docker ビルド。npm レジストリへの接続が要る)が前提**で、IT はフロントエンドのビルドに依存する |

Linux の `vm.max_map_count` と SELinux(bind mount のラベル)は未確認(`deploy/compose/README.md` の前提を参照)。

**Crawler・Indexer の結合テストと同時に実行できない**: 3 つの結合テストは、compose のプロジェクト名(`loreley-it`)とホストのポート(9200・8000。Crawler・api のテストは 8001 も、api のテストは 8080・8090 も)が同じため、同時には実行できない。排他ロックで同時実行を拒否する(「実行方法」の「結合テスト同士は同時に実行できない」)。テスト用の上書き(`compose.test.yaml`)もそれぞれ別で、重ねない。

**ポート 9200 を別のアプリ(Fess など)が使っている場合**: スクリプトは事前確認で中止し、使用中の相手を表示する(止めはしない)。

## 実行方法

### 一括で実行する(通常はこれ)

リポジトリのルートで、スクリプトを実行する。スタックの起動、起動の待機、pytest、後始末(`down -v` と `data/` の削除)までを行う。

```sh
scripts/run-api-integration-test.sh                  # 全シナリオ(24 テスト)
scripts/run-api-integration-test.sh --keep           # 終了後もスタックと data/ を残す(デバッグ用)
scripts/run-api-integration-test.sh -k test_30       # 1 ファイルだけ(ファイル名の語で絞る)
scripts/run-api-integration-test.sh -k "test_30 or test_40"   # 複数ファイル
```

- `--keep` と `-h`/`--help` 以外の引数は、そのまま pytest に渡る。**絞り込みには `-k` を使う**。ファイルやノード ID(`ファイル::テスト名`)をパス引数で渡しても、既定のコマンドの末尾に `tests/integration/api` があるため絞られず、全テストが走る
- シナリオ ID(`AIT-nn`)はテスト関数名に含まれない(ファイル冒頭の docstring にある)。`-k AIT-30` は **0 件になる**(終了コード 5)。ファイル名の語(`-k test_30`)かテスト名の語で選ぶ
- スクリプトは `docker compose -p loreley-it -f deploy/compose/compose.yaml -f tests/integration/api/compose.test.yaml up -d --build opensearch opensearch-init indexer crawler api web` で起動する。**`up --wait` は使わず**、3 秒間隔で状態を確認して、`opensearch`・`indexer`・`crawler`・`api`・`web` が healthy、`opensearch-init` が Exited(0) になるのを待つ(compose v2.3.3 では `--wait` が戻らないため)
- pytest の既定の引数は `-v -rP`(成功したテストの標準出力も表示する。障害系の観測値 `[observed]` がログに残る)
- 出力は標準出力と `tests/integration/api/results/pytest-YYYYMMDD-HHMMSS.log` に残る(`.gitignore` 済み)
- 異常終了したときは、`docker compose ps -a` と各サービスのログの末尾 100 行を表示してから、後始末する
- 障害系(AIT-90〜93)は、スクリプトが `LORELEY_IT_ALLOW_COMPOSE_CONTROL=1` を渡したときだけ動く。pytest を直接実行したときは skip される(下の「障害系の安全策」)

#### 終了コード

| コード | 意味 |
| --- | --- |
| 0 | 全テスト成功 |
| 1 | pytest のテスト失敗、**または**引数・事前確認の失敗(Docker・uv が無い、ポート使用中、前回の `loreley-it` の残りなど)、**または**ロックを取れなかった(別の結合テストが実行中、残ったロック、`TMPDIR` にロックを作れない場合)。事前確認・ロックの失敗は標準エラー出力に理由が出るので区別できる |
| 2〜5 | pytest の終了コードのまま(2=中断。スタックに接続できない・メンテナンスフラグが残っている・`data/` がない、4=pytest の使い方の誤り、5=該当テストなし) |
| 10 | スタックの起動失敗(`up` の失敗、待機の上限超過、コンテナの異常終了) |
| 11 | テストは成功したが、後始末(`down -v`・`data/` の削除・ロックの解除)に失敗した。テスト失敗のときは、後始末に失敗しても pytest の終了コードのまま。後始末に失敗したら、標準エラー出力の手順で手動で消す |
| 130 / 143 | Ctrl-C(INT)/ TERM で中断(どちらも後始末まで行う) |

#### 環境変数

| 変数 | 既定 | 説明 |
| --- | --- | --- |
| `LORELEY_IT_WAIT_TIMEOUT_SECS` | `300` | 起動後の待機の上限(秒)。1 以上の整数 |

`OPENSEARCH_VERSION`・`OPENSEARCH_HEAP_SIZE` などの compose の変数は、そのまま compose に渡る(`deploy/compose/.env.example`)。ただし次はスクリプトが固定し、上書きされない。

- ホスト側ポート 5 つ(`OPENSEARCH_HOST_PORT`・`INDEXER_HOST_PORT`・`CRAWLER_HOST_PORT`・`API_HOST_PORT`・`WEB_HOST_PORT`)と索引名 4 つ
- `LORELEY_CRON_TIMEZONE=Asia/Tokyo`: 既定(UTC)と違う値にして、共通変数が Crawler と api の両方に届くことを AIT-01(EP-14 の `cron_timezone`)で確かめる
- `LORELEY_IT_ALLOW_COMPOSE_CONTROL=1`: 障害系の許可
- `CRAWLER_DOCUMENTS_DIR`: `tests/integration/api/data` の絶対パス

テストが読む環境変数(スクリプトが渡す。pytest を直接実行するときは自分で渡す): `LORELEY_IT_{OPENSEARCH,INDEXER,CRAWLER,API}_URL`(接続先。既定は `http://127.0.0.1:{9200,8000,8001,8080}`)、索引名 4 つ、`CRAWLER_DOCUMENTS_DIR`(未指定は `tests/integration/api/data`)、`LORELEY_IT_ALLOW_COMPOSE_CONTROL`。

### 手動で実行する(スタックを起動して pytest を直接実行する)

テストを繰り返し実行するときなど、スクリプトを使わずに起動と pytest を分ける手順。リポジトリのルートで実行する。

> **未確認**: この手順は、スクリプトと同じコマンドを書き出したもので、**通しの実行はしていない**。スクリプト経由の実行だけを確認した。

```sh
# 1. 検索対象のディレクトリを作る(Docker に作らせると root 所有になりうる(想定。未確認))
mkdir -p tests/integration/api/data && chmod 755 tests/integration/api/data

# 2. 起動(`--wait` は使わない。CRAWLER_DOCUMENTS_DIR は絶対パスで渡す。
#    AIT-01 が cron のタイムゾーンを確かめるので LORELEY_CRON_TIMEZONE も渡す)
CRAWLER_DOCUMENTS_DIR="$PWD/tests/integration/api/data" LORELEY_CRON_TIMEZONE=Asia/Tokyo \
  docker compose -p loreley-it -f deploy/compose/compose.yaml -f tests/integration/api/compose.test.yaml \
  up -d --build opensearch opensearch-init indexer crawler api web

# 3. opensearch・indexer・crawler・api・web が healthy になるまで待つ(opensearch-init は Exited (0) になる)。
#    crawler は起動時の回復が終わるまで接続できない(healthcheck の start_period は 180 秒)
docker compose -p loreley-it -f deploy/compose/compose.yaml -f tests/integration/api/compose.test.yaml ps

# 4. テストを実行する(障害系も動かすときだけ LORELEY_IT_ALLOW_COMPOSE_CONTROL=1 を付ける)
CRAWLER_DOCUMENTS_DIR="$PWD/tests/integration/api/data" LORELEY_IT_ALLOW_COMPOSE_CONTROL=1 \
  uv run --project tests/integration/api pytest tests/integration/api -v -rP

# 5. 後始末(ボリュームも消す。コンテナを消してから data/ を削除する)
docker compose -p loreley-it -f deploy/compose/compose.yaml -f tests/integration/api/compose.test.yaml down -v --remove-orphans
rm -rf tests/integration/api/data
```

- **`up` のときに `CRAWLER_DOCUMENTS_DIR` を渡さないと、compose の既定(`./documents`)が mount されるため、テストが `data/` に置いた文書を Crawler が読めず、失敗するはず**(想定。未確認)。`ps`・`down` では不要(想定。未確認)
- ノード ID で 1 テストだけ実行したいときは、この手順で pytest を直接実行する(例: `... pytest "tests/integration/api/test_20_crawl.py::<テスト名>"`)
- テストは `compose.test.yaml` の値(原本の上限 64 KiB、Crawler のポーリング間隔 10 秒、api の `127.0.0.1:8080` への publish など)を前提にしている。`deploy/compose/compose.yaml` だけで起動したスタックに向けて実行しない(本番用の `compose.yaml` は api を publish しない)
- スタックが起動していないと、pytest は接続できなかった理由と起動手順を表示して、終了コード 2 で中止する
- 手動の手順 5 は、手順 1〜4 を実行した場合の後始末。スクリプトの後始末と同じコマンド(スクリプトの読解による)

### 結合テスト同士は同時に実行できない(排他ロック)

Crawler の結合テスト(`scripts/run-crawler-integration-test.sh`)・Indexer の結合テスト(`scripts/run-indexer-integration-test.sh`)とは、**プロジェクト名(`loreley-it`)とホストのポートが同じ**ため、同時には実行できない。3 本のスクリプトは**排他ロック**で同時実行を拒否する。どれかを終えてから、別の 1 本を実行する。

- 後から起動した側は、**何も消さずに終了コード 1 で中止**し、ロックの保持者の PID・開始時刻・スクリプト名を表示する
- ロックは `${TMPDIR:-/tmp}/loreley-it.lock`(ディレクトリ)。リポジトリの外に置くため、別の clone・worktree で起動した実行とも排他される。事前確認の直前に取り、通常終了・INT・TERM・`--keep` のときも終了時に解除する(`--help` と引数エラーでは作らない)。`--keep` で残したスタックはロックでは守られず、次の実行は事前確認(コンテナの残り)で中止する
- **SIGKILL・電源断などで残ったロックは、自動では解除されない**。次の実行が終了コード 1 で中止し、保持者の PID と解除の手順を表示するので、`ps -p <PID>` で保持者が動いていないことを確かめてから、表示される手順(`rm -rf '<ロックのパス>'`)で手動で解除する
- **実行中のロックを誤って手動で解除すると、排他が破れる**。別の実行がロックを取り直したあとに先発が終わると、先発は保持者の PID が自分と違うため、そのロックを消さずに警告を出すだけで終わる
- 排他されないもの: `TMPDIR` が実行ごとに異なる環境(macOS の別ユーザーなど)から起動した実行、pytest や `docker compose` を手で直接実行した場合

## 結果の見方

- 失敗したテストの詳細は、`results/` のログの `FAILURES` の節にある。スタックの状態は、同じ実行の最後に出る `docker compose ps -a` と各サービスのログの末尾(異常終了のとき)を見る。`--keep` で残したスタックなら、`docker compose -p loreley-it -f deploy/compose/compose.yaml -f tests/integration/api/compose.test.yaml logs api`(`crawler`・`indexer` も同様)で全体を見られる
- `--keep` で残したスタックに対して pytest を繰り返すと、テストが作るソース(`it-` で始まる。削除しない)が積み上がる。`support.py` の `OpenSearchProbe` は、ソースの全件を 1 回の検索(上限 100 件)で読み、上限に達するとアサートで失敗する(AIT-30 の全行照合など)。**100 件に達する前に、`down -v` でスタックごと作り直す**
- 窓を見逃したときのテスト(AIT-20・50・60)は、見逃したことが分かるメッセージで失敗する。待ちが上限を超えたときは、最後に観測した状態が付く
- 障害系は、設計が複数の値を許す箇所の実測値を `[observed]` 付きで出力する(`-rP` でログに残る)
- 実行結果の記録は [docs/v0.x/test-results/admin-api-integration.md](../../../docs/v0.x/test-results/admin-api-integration.md)

## シナリオ一覧

各テストの docstring に、【何を確認するか】【前提と手順】【期待する結果とその根拠(設計書の章)】【単体テストでは確認できず実機で確認する点】がある。EP は `admin-api-v0.1.md` の通し番号(EP-01〜14)。全部で 24 テスト(AIT-11 のパラメータ 2 件と AIT-93 を含む)。EP-01〜14 のすべてを、少なくとも 1 つのシナリオが実コンポーネント経由で呼ぶ。

| ID | ファイル | EP | 何を確認するか |
| --- | --- | --- | --- |
| AIT-01 | `test_01_startup.py`(5 テスト) | `/healthz`・13・14・12 | `/healthz` が 200。EP-13 が 8 件を固定順で返し、crawler・indexer・opensearch・api・web が `normal`、他 3 つが `not_configured`。EP-14 が `cron_timezone=Asia/Tokyo`・`dashboards_url=null`(共通変数が届いている)。EP-12 に 4 索引(`loreley-documents-000001`・`loreley-deletions`・`loreley-jobs`・`loreley-sources`)が含まれる。`/api/admin/v1/openapi.json` は 404(`OPENAPI_ENABLED` は既定の無効) |
| AIT-10 | `test_10_sources.py` | 3・4・1・2 | 登録 201(`loreley-sources` に `ttl`(秒)・`ratio_threshold`(割合)へ変換して保存)、同内容の再送 200、内容違いは 409 `source_already_exists`、EP-02 の初期状態、更新、EP-01 の昇順 |
| AIT-11 | `test_10_sources.py`(3 テスト) | 3・4 | 実 Connector の違反(相対 `root`・未知項目)が 400 `config_invalid`。`field`・`reason`・`detail`・`crawler_message` が付き、保存されない(EP-03・04) |
| AIT-12 | `test_10_sources.py` | 2・4・5・6・8・11 | 未登録ソースへの操作: EP-04・05・06 は 404 `source_config_not_found`、EP-02・11 は 404、EP-08 は 200 `released=false` |
| AIT-20 | `test_20_crawl.py` | 6・10・2・9・5・8・1 | クロール起動(202)→ `running` を観測。実行中: EP-02 `held_crawl`、EP-06 再送・EP-05 は 409 `lock_held`、EP-08 は 409 `lock_in_use`(ID 指定で読むロックと 409 を先に確認し、検索で読む EP-02 の最終クロールと EP-09 の実行中ジョブは反映を待って後に確認)。終了後: EP-10 `succeeded`・登録件数・削除結果、EP-02・01 の更新。実行中の 409 で再送した `force_delete=true` が走行中のジョブに適用されていないこと(EP-10 の `force_delete`・`rewrite_mode` が `false`)。OpenSearch のジョブ記録と突き合わせる |
| AIT-21 | `test_20_crawl.py` | 6・10・1 | `force_delete=true`・`rewrite_mode=true` の中継。クロール A(4 件)→ 2 件削除 → 通常のクロール B は割合ルールで削除が止まる → `force_delete=true` のクロール C で削除される。TTL は実時間で待つ(約 55 秒) |
| AIT-30 | `test_30_queries.py` | 1 | EP-01 の全行の `last_crawl`・`last_completed_at`・`document_count` を、OpenSearch 直読みの独立計算と照合(2 回・1 回・0 回クロールした 3 ソースと、`loreley-jobs` に `crawl` のジョブ記録と文書を持つ登録済みソースが 11 件以上になるまで md 1 件のソースを実際にクロールして補った状態の全ソース。`terms` 集計の既定 `size`(10)を超える数のジョブ・文書を持つ行が返ることを、独立計算側と api の応答側の両方で確認する。登録だけでクロールしないソースは `terms` のバケットを作らず検出力がないので、補いに使わない)。`source_id` 昇順 |
| AIT-31 | `test_30_queries.py` | 9・10 | `source_id`・`status` の絞り込みと `total`、`sort=queued_at`/`-queued_at` の順序逆転、範囲外ページは `items=[]`、`window_limit=10000`、`latest_for_source` |
| AIT-32 | `test_30_queries.py` | 12 | EP-12 の `indices`・`shards`・`nodes`・`cluster` を `_cat/*`・`_cluster/health` の直読みと照合 |
| AIT-40 | `test_40_documents.py` | 11・10・1 | 通常の md・壊れた PDF 26・上限超過 2 を 1 回クロール。`tab_counts`・`document_count`、`extract_failed` のページング(25 件 + 1 件、重複なし)、既定・昇順の並びと同順位の `document_id` 昇順、`oversize` の項目(各行の `external_id` を独立実装でハッシュした値が `document_id` と一致することを含む)、EP-10 の件数 |
| AIT-41 | `test_40_documents.py` | 11 | スキップ記録 2 件(OpenSearch へ直接書き込み)の `existence`(`existing`・`new`)が `ids` クエリで決まる。`tab_counts.skipped` |
| AIT-50 | `test_50_cancel_and_lock.py` | 6・7・9・10・2 | 実行待ちのジョブは 200 で取消。実行中のジョブ(終了通知の送信開始後)は 202 で受け付けられ `cancelled`、`cancel_after_finish_notice`・警告 `polling_aborted` が付く。終端のジョブの再取消は 409 `job_already_finished` |
| AIT-51 | `test_50_cancel_and_lock.py` | 2・6・8 | 孤児ロック(OpenSearch へ直接書き込み)が EP-02 で `orphan`、EP-06 は 409 `lock_held`、EP-08 で解放(`released=true`・`failed_job_id=null`)、再送は `released=false`、解放後のクロールが成功する |
| AIT-60 | `test_60_source_deletion.py` | 5・7・6・1・2・10・11・8 | 別ソースのクロール実行中にソース削除(EP-05)を起動: 実行待ちの間は EP-02 `held_delete`、EP-06 は 409 `lock_held`、削除ジョブの取消は 409 `job_not_cancellable`、EP-08 は 409 `lock_in_use`。完了後に対象ソースの文書・記録・設定が消え、別ソースは残る。対象ソースの過去のクロールのジョブと削除ジョブは、削除後も EP-10 で読め `loreley-jobs` に残る(スキップ記録の削除は、スキップ記録を作れないため未検証) |
| AIT-90 | `test_90_component_failures.py` | 全 | Crawler 停止: EP-13 の `crawler` が `abnormal`。EP-03〜08 は 503 `crawler_unreachable`、他の EP は 200。復旧後にクロールが成功する |
| AIT-91 | `test_90_component_failures.py` | 全 | Indexer 停止: EP-13 の `indexer` が `abnormal`、読み取りの EP は 200。停止中に始めたクロールとソース削除は Crawler 側で `failed`・`failure_reason=indexer_unavailable`(`failure_detail` は「Indexer が応答しない」を含む)になる(部分失敗)。クロールのロックは解放され EP-02 の `last_crawl` がそのジョブになる。削除は `deleting` の状態の見え方を確認する。復旧後の再実行で完了する |
| AIT-92 | `test_90_component_failures.py` | 全 | OpenSearch 停止: 読み取りの EP は 503 `unavailable`、EP-13 の `opensearch` が `abnormal`、EP-14 と `/healthz` は 200、EP-06 は 503。復旧後に 4 サービスが healthy になり、読み取りとクロールが戻る |
| AIT-93 | `test_90_component_failures.py` | 全 | web 停止: EP-13 の `web` だけが `abnormal`(`reason` は `connection_refused` か `name_not_resolved`。実測値を `[observed]` で記録)、他は `normal`。EP-01・09・12・14 と `/healthz` は 200。復旧後に EP-13 の 5 つが `normal` に戻る |

## テスト設計上の注意

- **データの分離**: `source_id` はテストごとに作る(`it-` で始まり、半角英数字・`-` だけ。フィクスチャ `source_id`)。テストはデータ(OpenSearch 上のソース・文書・記録)を**削除しない**(削除を確認する AIT-60・AIT-91 を除く)。後始末はスタックごと `down -v` で消すことに任せている。**開発用のスタックに向けて実行しない**
- **窓への依存(AIT-20・50・60)**: 実行中のジョブを観測・操作できるのは、ジョブがロックを持つ間だけ。Crawler は終了通知の直後に Indexer の削除結果を 1 回読み、その後ポーリング間隔ごとに読むため、ロックを持つ時間はほぼその間隔になる。そこで `compose.test.yaml` で Crawler のポーリング間隔を **10 秒**(Crawler IT は 2 秒)にして、HTTP 数回の操作(1 秒未満)が収まる窓を作っている。Indexer の削除ワーカーの走査間隔は **5 秒**(既定 2 秒、Crawler IT は 1 秒)にしている。これは、Crawler の最初の確認までに Indexer の削除が終わって窓が閉じる競合に備える保険で、実測では削除ワーカーは終了通知の受理で起床し、`crawl_started_at` から削除判定の開始まで 0.4〜1.1 秒だった(走査間隔を待たない)。5 秒にした効果は未検証で、値を変えたときは再検証が要る。クロール 1 回は約 10〜12 秒かかる。操作の前に `running`(AIT-50 は `finish_notice.send_started_at` も)を観測し、窓を見逃したときは、見逃したことが分かるメッセージで失敗する。極端に遅い環境では失敗しうる。値を変えるときは、`compose.test.yaml` のコメントと `support.py` の待ちの定数も確認する
- **検索で読む EP の反映遅れ**: EP-01・09・11、EP-02 の最終クロール・最終完了時刻(`last_completed_at`)・文書数は、検索で読むので、書き込みの反映が遅れうる。設計(AAA-P-6)は、遅れを**最大約 1 秒と推測**している(`refresh_interval` が既定の 1 秒のはずという推測)。この IT では、少なくとも 1 回の取りこぼし(EP-03 直後の EP-01 でソースが見えない)を観測したが、**最大遅延は測っておらず、`refresh_interval` の設定値も読んでいない**(結果文書 4.4・5.3)。ID 指定で読む EP-10 のジョブ本体とロックは即時。待ちの方針: **確認する値は、読む EP ごとに待ち条件に含める**(間隔 0.3 秒・上限 10 秒でポーリングしてから確認する。アサートの値は曲げない)。AIT-20 の不安定さ(結果文書 4.6 の 4 回目の失敗)は、この条件の不足(`last_completed_at` と文書数を待ち条件に入れていなかった)だった。EP-10 の `latest_for_source`・`rerunnable`(再実行の可否)、EP-02 の `delete_job` は、テストのコメントでは検索の結果から導くとされ、これらも待ち条件に含めている
- **OpenSearch への直接書き込みは前提作りだけ**: 次の 2 か所に限る。判定は Admin API と実 Crawler の応答で行う。形式は crawler-architecture 3.3・5.1 と `infra/opensearch/schema/jobs.json` に合わせている。**Crawler・Indexer の内部の記録形式に依存する**(形式が変わるとテストが壊れ、変更に気づける)
  - AIT-51: 孤児ロック(終端ジョブの `job_id`、2 時間前の `acquired_at`)。Crawler は起動時の回復で自分のロックを消すため、実 Crawler には孤児ロックを作らせられない
  - AIT-41: スキップ記録 2 件。取得の権限エラーを macOS の bind mount で確実に作れないため。Crawler が書いた記録との形式の照合(AAPI-U-7)は未検証
- **TTL は実時間で待つ**: AIT-21 は `last_seen_at` を書き換えず、ttl 15 秒のソースで実際に期限切れになるまで待つ(Admin API の `/healthz` の `Date` ヘッダを現在時刻に使い、ホストの時計のずれを避ける)
- **実行中はホスト(Mac など)をスリープさせない**: 実行中にホストが止まるとコンテナも止まり、Crawler のロックのリースが切れて `lock_lost`(`lease_expired`)でクロールが失敗する、と推定している。2026-11-25 に、AIT-60 が `lock_lost`(`lease_expired`)で失敗した実行が 1 回あった。**原因はスリープと推定**(スリープの記録はない)。根拠は、pytest の経過が 318.78 秒なのに実行全体の壁時計が約 1 時間 42 分で、Crawler のログが約 1 時間 38 分途切れていたこと(結果文書 4.6)。Mac では `caffeinate -i scripts/run-api-integration-test.sh` のように実行するとよい。`caffeinate -i` 付きの 6 回(結果文書 4.6 の 3〜8 回目)では `lock_lost` は出ていない
- **待ちは上限つきのポーリング**(`support.py` の `poll_until`): ジョブの終了 90 秒、`running` の観測 30 秒(間隔 0.2 秒)、ロックの解放 30 秒、アイドル待ち 120 秒、サービスの復旧 300 秒、検索の反映 10 秒。`sleep` に頼らない
- **テスト間の独立**: `conftest.py` が各テストの前後で、実行中・実行待ちのジョブが 0 になるのを待つ(Job Runner は直列で、前のテストのジョブが次の窓を乱すため)。障害系は最後のファイル(`test_90_*`)に集め、止める区間の外でだけこの待ちが動く
- **api は検索対象の文書を mount しない**: Crawler だけが `tests/integration/api/data` を `:ro` で `/data/documents` に mount する。EP-13 の `web` は、fixture ではなく実 `web`(Nginx)を api が `http://web:80/admin/` で確認した結果で、`normal` になる
- **EP-13 の `reason` など、設計が複数の値を許す箇所**は、どちらも受け入れ、実測値を `[observed]` で出力する
- **実機が設計と違ったとき**: テストを実機に合わせて変えず、発見事項として扱う(設計書の改版はユーザー判断)
- **セキュリティ**: api は認証がなく、`127.0.0.1:8080` だけに publish する(破壊的操作を含む)。結合テストのスタックでも `0.0.0.0` へ公開しない。api の `8080` と Crawler の `8001` は、テスト用の上書き(`compose.test.yaml`)だけが `127.0.0.1` に publish する(本番用の `compose.yaml` は公開しない)。本番用の `compose.yaml` が `127.0.0.1:8090` に publish する `web` は、IT でも有効になる(テストは `web` 経由では呼ばない)。詳細は `deploy/compose/README.md` の公開範囲の注意(HO-40・41)

### 障害系の安全策(AIT-90〜93)

障害系は、実コンテナを止めるため、次の制限をかけている(`support.py` の `ComposeControl`)。

- 操作できるのは、プロジェクト `loreley-it` と compose ファイル 2 つ(定数で固定)に対する **`stop`・`start` だけ**。引数リストで `docker compose` を実行し、shell は使わない。`subprocess` にはタイムアウトを付ける
- 止めてよいサービスは**許可リスト `crawler`・`indexer`・`opensearch`・`web` だけ**。`api`・`opensearch-init` や他のプロジェクトのコンテナは、docker を呼ぶ前に `ValueError` になる
- 止める区間は `compose_control.stopped(...)`。テストが途中で失敗しても、区間を抜けるときに `finally` で必ず `start` し、healthy になるまで待つ(上限 300 秒。OpenSearch の停止後は opensearch・indexer・crawler・api の 4 つ。`web` の停止後は web)。復旧に失敗したときは例外にする
- `LORELEY_IT_ALLOW_COMPOSE_CONTROL=1` がないと、4 テストとも skip する(pytest を直接実行したときに、意図せずコンテナを止めないため)。スクリプトが渡す

## `data/` と後始末

- `tests/integration/api/data/` は、Crawler に `:ro` で mount する検索対象の文書の置き場(コンテナ内 `/data/documents`)。**`.gitignore` 済み**。テストは `data/<source_id>/` を作って文書を置き、テストの終了後に削除する(`support.py` の `SourceDirectory`)。ファイルは 0644、ディレクトリは 0755(Crawler は uid 10001 で動くため)
- スクリプトは、起動前に `data/` を作って `chmod 755` し、終了時に `compose down -v --remove-orphans` のあとで削除する(使用中の mount 元を消さないため)。`compose down` が失敗したときは、コンテナが残っている可能性があるので `data/` を**削除せず**、手動で消すよう案内する。`--keep` のときはスタックと `data/` を残し、後始末のコマンドを表示する
- **事前確認で中止する条件**(排他ロックを取ったあと。何も消さず終了コード 1。スタックにもボリュームにも `data/` にも触れない): (1) `loreley-it` のコンテナの残り(停止中を含む。`docker ps -a` が失敗して確認できないときも中止)、(2) `loreley-it` の名前付きボリュームの残り(`docker volume ls` が失敗して確認できないときも中止)、(3) 空でない `data/`(権限などで内容を確認できないときも中止)、(4) ホストのポート 9200・8000・8001・8080・8090 の使用中。終了時の `down -v` と `rm -rf` が、前回 `down`(`-v` なし)で止めただけのボリュームや、利用者が `data/` に置いたファイルを消さないため。ポートの使用中は、使っている Docker コンテナと `lsof` の結果を表示する(止めはしない)
- メンテナンスフラグが残ったとき(`loreley-jobs` の `maintenance` 文書。中断した実行の後)は、次の実行が conftest で終了コード 2 になる。スタックごと作り直す(`down -v --remove-orphans`)か、`curl -X DELETE http://127.0.0.1:9200/loreley-jobs/_doc/maintenance` で消す。この IT のテスト自身はメンテナンスフラグを書かないので、通常は残らない

## 未実施(スコープ外)

次は、このテストでは確認していない主なもの。**完全な一覧は [admin-api-integration.md](../../../docs/v0.x/test-results/admin-api-integration.md) の 7 章、申し送り項目別の判定は同 4.4**。

- EP-09 の複数ページ(26 件以上のジョブが必要)、10,000 件の窓、一部シャード障害、複数ノードの `cat.*`・`relocating`
- `stalled=true`・`lease_expired` などのロック状態、同時実行上限・期限後のスレッド(AAA-U-7・10)、`ClientDisconnect`
- 入れ子のマウント・`root_path`(BAPI-U-2)、AAPI-U-7(Crawler が書いたスキップ記録の `existence`)、`summary_pending`(LLM 要約の実装後)
- EP-07 の、終了通知の送信前の実行中取消(`cancel_after_finish_notice=false`。登録途中は `partial=true`)、ソース削除でのスキップ記録の削除(AIT-60)

## ファイル構成

| パス | 内容 |
| --- | --- |
| `pyproject.toml` / `uv.lock` | テスト専用の依存(`pytest`・`httpx`。dev に `ruff`)。アプリの依存とは分けている。`uv.lock` で固定している |
| `compose.test.yaml` | テスト用の上書き(原本の上限、Crawler のポーリング間隔、Indexer の走査間隔、Crawler・api の publish、`web`・api の healthcheck の間隔)。`deploy/compose` には混ぜない。Crawler・Indexer の IT 用とは別で、重ねない |
| `conftest.py` | フィクスチャと、起動済みのスタックへの疎通確認・メンテナンスフラグの残りの確認、各テスト前後のアイドル待ち |
| `support.py` | Admin API のクライアント、OpenSearch の検証ヘルパ(読み取りと前提作りの書き込み)、`document_id` の独立実装(アプリのコードは import しない)、待ちのヘルパ、検索対象ディレクトリ、障害系の `ComposeControl` |
| `test_*.py` | シナリオ別のテスト(上の表) |
| `data/` | 実行中の検索対象の文書(実行時に作られ、終了時に削除される。`.gitignore` 済み) |
| `results/` | スクリプトの実行ログ(`.gitignore` 済み) |

このディレクトリの外の `scripts/lib/it-common.sh` は、3 本の実行スクリプト(`scripts/run-{api,crawler,indexer}-integration-test.sh`)の共通処理(排他ロック・事前確認・起動と待機・後始末)。
