# deploy/compose

OpenSearch・Indexer・Crawler を起動する compose 構成(MVP)。`compose.yaml` が `opensearch`・`opensearch-init`・`indexer`・`crawler` の 4 サービスを定義する。

> **確認状況**: 特記がない限り、次の環境で実機確認した事実だけを書いている。「未確認」「想定(未確認)」と書いた箇所は、実機で確認していない。
>
> - 確認環境: macOS(x86_64)、Docker 20.10.13(Docker Desktop。VM のメモリ約 3.8GiB、CPU 2)、docker compose v2.3.3
> - 結合テスト(`tests/integration/indexer`・`tests/integration/crawler`)は、この構成を専用のプロジェクト名 `loreley-it` で起動して実行する。手順と結果は [tests/integration/indexer/README.md](../../tests/integration/indexer/README.md)・[tests/integration/crawler/README.md](../../tests/integration/crawler/README.md) を参照
> - `crawler` サービス(2026-11-16 に追加)の確認は、Crawler の結合テストの手動起動と一括スクリプトによる(結果は [crawler-integration.md](../../docs/v0.x/test-results/crawler-integration.md))。`docker compose up -d --build`(サービス名なし)を `.env` の設定なしで直接実行した確認は未実施

## 構成

| サービス | 役割 | ホストへの公開 |
| --- | --- | --- |
| `opensearch` | 検索インデックスと Store 層のバックエンド(単一ノード、セキュリティ無効) | `127.0.0.1:9200` |
| `opensearch-init` | インデックス(`loreley-documents-000001` とエイリアス `loreley-documents`、`loreley-deletions`、`loreley-jobs`、`loreley-sources`)を作る使い捨てコンテナ。冪等。作成後は終了する | なし |
| `indexer` | `apps/indexer` をビルドして起動。`opensearch` が healthy で、`opensearch-init` が正常終了してから起動する | `127.0.0.1:8000` |
| `crawler` | `apps/crawler` をビルドして起動。`opensearch` が healthy、`opensearch-init` が正常終了、`indexer` が healthy になってから起動する。検索対象のディレクトリを `:ro` で mount する(後述の「`crawler` サービス」) | なし(設計書どおり。結合テストの上書き `tests/integration/crawler/compose.test.yaml` だけが `127.0.0.1:8001` に publish する。後述「ループバックのみ公開する理由」) |

スキーマと init スクリプトは `infra/opensearch/` にある。

## 前提

- Docker と docker compose v2(確認した版: Docker 20.10.13、compose v2.3.3。`up --wait` は使わない。後述)
- Docker に割り当てるメモリは **4GB 以上を推奨**。OpenSearch の JVM ヒープは既定 512m(最大 512MiB を実測で確認)で、Docker VM のメモリが約 4GB の環境を想定している。確認環境(約 3.8GiB)でのアイドル時の使用メモリは、OpenSearch 約 855MiB、Indexer 約 56MiB(OpenSearch 2.19.7 での測定。Crawler と 3.9.0 の使用量は測定していない)。OpenSearch・Indexer・Crawler を同時に起動して、Crawler の結合テストは全件成功した。ほかの重いコンテナを同時に動かさない
- ホストのポート `9200`(OpenSearch)・`8000`(Indexer)が空いていること(`.env` で変えられる)。Crawler はホストに公開しない(結合テストの実行時だけ `8001`)
- **未確認**(Mac でのみ実施):
  - Linux の `vm.max_map_count`。262144 未満だと OpenSearch が起動しない場合がある。必要なら `sysctl -w vm.max_map_count=262144`(Docker Desktop(Mac)では必要なかった)。`scripts/run-indexer-integration-test.sh` は、Linux で値が低いと警告を出す(この警告も未確認)
  - SELinux が有効なホスト。`opensearch-init` は `infra/opensearch` を bind mount(読み取り専用)で読むため、SELinux のラベルによっては読めない場合がある(`:z` の要否は未確認)

## 設定(`.env`)

`.env` は任意。無くても既定値で動く。変えたいときだけ作る。

```sh
cd deploy/compose
cp .env.example .env
```

| 変数 | 既定 | 説明 |
| --- | --- | --- |
| `OPENSEARCH_VERSION` | `3.9.0` | OpenSearch のイメージのタグ |
| `OPENSEARCH_HEAP_SIZE` | `512m` | JVM ヒープ(`-Xms` と `-Xmx` の両方に使う) |
| `OPENSEARCH_HOST_PORT` | `9200` | OpenSearch のホスト側ポート |
| `INDEXER_HOST_PORT` | `8000` | Indexer のホスト側ポート |
| `INDEXER_LOG_LEVEL` | `INFO` | Indexer のログレベル |
| `CRAWLER_LOG_LEVEL` | `INFO` | Crawler のログレベル |
| `CRAWLER_DOCUMENTS_DIR` | `./documents` | Crawler が読む検索対象のディレクトリ(ホスト側のパス)。コンテナ内では `/data/documents` に読み取り専用で mount される。**注意点は「`crawler` サービス」を参照** |
| `LORELEY_JOBS_INDEX_NAME` | `loreley-jobs` | `loreley-jobs` の索引名。`opensearch-init`・Indexer・Crawler に同じ値が渡る |
| `LORELEY_SOURCES_INDEX_NAME` | `loreley-sources` | `loreley-sources` の索引名。`opensearch-init`・Crawler に同じ値が渡る。`LORELEY_JOBS_INDEX_NAME` とは別の名前にする |
| `INDEXER_MAX_RAW_BYTES` ほか 5 項目 | Indexer のコードの既定値 | Indexer の上限(`INDEXER_MAX_RAW_BYTES`・`INDEXER_MAX_BATCH_DOCUMENTS`・`INDEXER_MAX_BATCH_BYTES`・`INDEXER_MAX_REQUEST_BODY_BYTES`・`INDEXER_MAX_LAST_SEEN_IDS`・`INDEXER_SKIP_OVERSIZE_ID_LIMIT`)。Indexer と Crawler の両方に同じ値が渡る。既定値と意味は `.env.example` |

秘密値はない。

## 起動・停止・初期化

`deploy/compose` で実行する。

```sh
docker compose up -d --build          # 起動(`--wait` は使わない。後述)。crawler も起動する(`CRAWLER_DOCUMENTS_DIR` の既定 `./documents` が無ければ作られる。後述)
docker compose ps                     # 状態の確認。opensearch・indexer・crawler が healthy になるまで待つ(opensearch-init は Exited (0) になる)
curl http://127.0.0.1:9200/_cluster/health
curl http://127.0.0.1:8000/healthz
# crawler はホストに公開しない。healthy は `docker compose ps` で確認する(起動時の回復が終わるまで接続できず、healthcheck の start_period は 180 秒)

docker compose up -d --build opensearch opensearch-init indexer   # Indexer だけを起動する(crawler を起動しない)

docker compose down                   # 停止(データは残る)
docker compose down -v                # 停止してデータ(名前付きボリューム)も削除
```

- **`up --wait` は使わない**: compose v2.3.3 では、全サービスが Healthy / Exited(0) になったあとも `up -d --wait` が戻らない(2 回再現。原因の特定はしていない)。起動済みのスタックに対して `--wait` なしの `up -d` を再実行すると 3 秒で戻った(クリーン起動では次の「起動の所要時間」のとおり時間がかかる)。`up -d` は、`opensearch` が healthy になり `opensearch-init` が正常終了するのを待ってから `indexer` を起動し、`indexer` が healthy になってから `crawler` を起動する。起動完了は `docker compose ps` で確認する。`--wait-timeout` もこの版には無い。待機つきで起動したいときは、`docker compose ps` を一定間隔で確認する形にする(`scripts/run-indexer-integration-test.sh` が実装している)
- **起動の所要時間**(1 回の実測。目安。実装担当の報告による。ログは保存していない): クリーンな状態からイメージのビルドを含めた `up -d --build` が初回約 90 秒、そのあと healthy になるまで約 20 秒(いずれも OpenSearch 2.19.7 での値。3.9.0 は後述の「OpenSearch のバージョン固定方針」)。ビルドのキャッシュがあれば短い
- **初期化**: インデックスは `opensearch-init` が起動のたびに確認し、無いものだけ作る(冪等)。既存のインデックスは変更しない。再実行すると、すべて `skip` と表示して終了する(確認済み)。検索インデックスは、エイリアス `loreley-documents` の有無で判定する。再インデックスでエイリアスを `-000002` に付け替えて `-000001` を削除した状態でも、空の `-000001` は作り直さない(その状態を模擬して確認済み)
- **マッピングを変えたいとき**: `infra/opensearch/schema/*.json` を直しても、既存のインデックスは、`loreley-jobs` を除いて変わらない(init は既存を変更しない。検索インデックスと `loreley-deletions`・`loreley-sources` は `dynamic: strict` なので、定義にない項目を書くと拒否される)。`loreley-jobs` だけは、init が起動のたびに `jobs.json` の項目のうち不足しているものを `PUT _mapping` で足す(拡張前に作ったボリュームでも、Crawler が使う `record_type`・`status` などで検索できる。型が違う項目は 400 で init が失敗して止まる。実機で確認済み)。足した項目は、すでに入っている文書を再索引しない(ジョブ記録は Crawler が更新のたびに書き直す)。ほかのインデックスは、開発用のデータを消してよいなら、`docker compose down -v` でボリュームごと消して、`up -d` で作り直す。**データを残したまま変える手順(再インデックス)は、本タスクでは未確認**(対象外。設計は `apps/indexer/README.md` 8 章と arch 11 章)
- **停止**: Indexer は SIGTERM を受けると `Shutting down` → `Application shutdown complete` と出して、1 秒で終了コード 0 で止まる(`stop_grace_period` は 30 秒)
- 結合テストなど、開発用スタックと分けたい場合は `-p <プロジェクト名>` を付ける(ボリュームも別になる)。結合テストは `scripts/run-indexer-integration-test.sh`(`opensearch opensearch-init indexer` だけを起動)と `scripts/run-crawler-integration-test.sh`(`crawler` も起動)が `-p loreley-it` で起動して実行し、終わると `down -v` で消す。**2 つのスクリプトはプロジェクト名とホストのポート(9200・8000)が同じため、同時には実行できない**。開発用のスタックに向けて結合テストを実行しない(テストはデータを削除しない)

## `crawler` サービス

- **起動順**: `opensearch` が healthy、`opensearch-init` が正常終了、`indexer` が healthy になってから起動する。`indexer` の healthy を待つのは、起動直後のクロールが失敗しないようにするため(Crawler の設計は Indexer の起動を待たなくても動く)。`restart: unless-stopped`
- **healthcheck**: イメージの `HEALTHCHECK`(`GET /healthz`、`start-period` 180 秒)をそのまま使う。Crawler は起動時の回復(OpenSearch への読み書き)が終わるまで HTTP を開かないため、healthy まで時間がかかりうる。結合テスト用の上書き(`tests/integration/crawler/compose.test.yaml`)で `interval` と `start_period` だけを指定しても、イメージの `test` は保持された(`docker inspect` で確認)ので、`compose.yaml` に `test` は書いていない
- **停止**: `stop_grace_period: 30s`(Crawler の設計の目安。Docker の既定 10 秒では足りないことがある)。実行中のジョブがある状態での `docker stop` の所要時間は**未実施**
- **検索対象のディレクトリ(`CRAWLER_DOCUMENTS_DIR`)**: ホスト側のパスを、コンテナ内の `/data/documents` に **`:ro`** で mount する。データソース設定の `connector_config.root` には、**コンテナ内のパス**(例 `/data/documents/<source_id>`)を書く。Crawler は uid 10001 で動くので、ファイルは others が読める権限(ディレクトリは実行権限も)にする。注意点:
  - **未指定だと `./documents`(`deploy/compose/documents`)が mount され、無ければ `up` のときに自動作成される**(`.gitignore` には入れていない)。パスを打ち間違えても、`up` は失敗せず、空のディレクトリが mount されて、クロールは 0 件列挙になる(コードと compose の読解による。実機では未確認)。Crawler を使うときは、`.env` か環境変数で、存在するディレクトリを指定する。結合テストでは、スクリプトが `tests/integration/crawler/data` の絶対パスを渡す
  - **`:ro` が守るのはホスト側のファイル**(Crawler が書き換えない)。FileSystem Connector の `root` はコンテナ内の任意の絶対パスを受け付け、`/data/documents` 配下に制限されない(コードからの推測。実行は未確認)。設定を登録できる者は、コンテナ内の読める範囲を列挙対象にできる(Crawler API は認証なしのため、本番用の compose はホストに公開しない。次節)
  - **パスに `:` を含むと使えない**(短縮形の `ホスト側:コンテナ側:ro` の区切りと衝突するため。実機では未確認)
  - 相対パスは、`compose.yaml` のあるディレクトリ(`deploy/compose`)が基準になる。結合テストのスクリプトは絶対パスで渡す
- **Indexer の上限と索引名は同値で渡す**: Crawler は起動時に、自分の上限(原本 1 件・バッチ・`last-seen` の件数など)が Indexer の上限以下かを検査し、超えていると起動に失敗する。Indexer の上限 6 項目(`INDEXER_MAX_RAW_BYTES`・`INDEXER_MAX_BATCH_DOCUMENTS`・`INDEXER_MAX_BATCH_BYTES`・`INDEXER_MAX_REQUEST_BODY_BYTES`・`INDEXER_MAX_LAST_SEEN_IDS`・`INDEXER_SKIP_OVERSIZE_ID_LIMIT`)は、**Indexer の `LORELEY_INDEXER_*` と Crawler の `LORELEY_CRAWLER_INDEXER_*` の両方に、同じ変数・同じ既定値(Indexer のコードの既定値)**で渡している(渡さないと、Crawler は検査を省略して警告を出すだけになる)。値を変えるときは、同じ変数 1 か所を変えれば両方に反映される。ただし、Crawler 自身の値(`LORELEY_CRAWLER_*`)が上限を超えないかは、別に確認する。索引名は、`LORELEY_JOBS_INDEX_NAME` を `opensearch-init`・Indexer・Crawler に、`LORELEY_SOURCES_INDEX_NAME` を `opensearch-init`・Crawler に渡す(2 つは別の名前にする。同じだと Crawler が起動に失敗する)

## ループバックのみ公開する理由

- Indexer API には認証・認可がない。`DELETE` でソースの文書を全削除することまで呼べる
- Crawler API にも認証・認可がない。クロール・ソース削除ジョブの起動、ロック解放、データソース設定の登録・更新まで呼べる
- OpenSearch もセキュリティプラグインを無効にしている(認証・TLS なし)
- そのため、ホストへの publish は `127.0.0.1`(同じホストからのみ)に限っている。`0.0.0.0`(全 NIC)への公開は、同じネットワークの誰でも削除などを実行できるようになるのでしない
- OpenSearch・Indexer のホスト側ポートは `.env` で変えられるが、バインド先は常に `127.0.0.1`
- **Crawler は、この compose ではホストに公開しない**(設計書 `crawler-architecture-v0.4.md` 10 章のとおり)。`127.0.0.1` への公開でも、認証・認可の代わりにならない。ホスト上の任意のプロセスが、FileSystem Connector の `connector_config.root` に `/data/documents` 以外のコンテナ内のパスを登録して、Crawler の実行ユーザーが読める(対象の拡張子の)ファイルを OpenSearch に索引できてしまうため。ホストの結合テスト(pytest)だけは、`tests/integration/crawler/compose.test.yaml` が `127.0.0.1:8001` に publish する(`CRAWLER_HOST_PORT` でホスト側のポート番号だけ変えられる)。Admin API など内部ネットワークから呼ぶ側を compose に加えるときも、Crawler の publish は不要。将来は、Connector が許可するルートディレクトリを制限する仕組みが望ましい(未対応)
- コンテナ間は、compose の内部ネットワークでサービス名(`http://opensearch:9200`)で通信する。ホストへの publish は、開発者が `curl` などで確認するためのもの
- 他のホストから使う必要が出たら、認証付きのリバースプロキシなどを前に置く(MVP の対象外)

## OpenSearch のバージョン固定方針

- イメージは `opensearchproject/opensearch:3.9.0`。パッチまでのタグで固定し、`latest` は使わない(取得のたびに変わらないため、再現できる)。ダイジェストは固定しない(タグの固定で足りると判断した)
- 3.9.0 を選んだ理由: 2026-11-13 時点で Docker Hub にある最新の版のため。Indexer が使う opensearch-py は 3.2.0(PyPI の最新)。この組み合わせで結合テストが通ることを確認した。以前の既定は 2.19.7(2.19 は maintenance 系列で、opensearch-py 3.2.0 の CI が検証対象とする系列)で、同じ結合テストが通っていた
- バージョンは `.env` の `OPENSEARCH_VERSION` で変えられる。上げるときは、結合テスト(`tests/integration/indexer`)を通してから使う
- 確認した実体(参考): `opensearchproject/opensearch:3.9.0`(ダイジェスト `sha256:3b55f6b6249cfdb92b52ee59adc8a266203ba9ef9f5d82544fad6f1af2f3609e`、build_hash `4ee42a94`、Lucene 10.5.1、JDK 25.0.4.1)。単一ノード・セキュリティプラグイン無効(`DISABLE_SECURITY_PLUGIN`)で起動し、Indexer が接続して起動時の整理まで完了し、結合テスト 40 件が通ることを確認した(結果は [indexer-integration.md](../../docs/v0.x/test-results/indexer-integration.md))
- 3.9.0 は、ヒープ 512m の環境で起動に 1〜2 分かかった(1 回の測定の目安。2.19.7 より遅い)。ヘルスチェックの `start_period` は 60 秒のまま(猶予は 60 秒 + 10 秒 × 12 回)で、結合テストは 3.9.0 で 2 回成功した。ただし初回の 1 回は、`opensearch` が unhealthy になって起動に失敗した(原因は未特定)。環境が遅く、この猶予を超える場合は、`compose.yaml` の `start_period` を延ばす
- 2.19.7 と 3.9.0 以外のバージョンは未確認

## `loreley-deletions` のマッピングは仮定義、`loreley-jobs`・`loreley-sources` は Crawler に合わせて定義

- `infra/opensearch/schema/deletions.json`: 設計書(loreley-deletions v0.10)は、マッピング全体を未決(U-2)とし、Indexer が実装で前提とする項目だけを置いている。Indexer が書く項目(`records.py` の `to_body()` の全キー)を `dynamic: strict` で定義した仮定義であり、設計確定時に置き換える。
- `infra/opensearch/schema/jobs.json`: Indexer が読む 4 項目(`owner`・`job_id`・`lease_expires_at`・`enabled`。型は変えていない)に、Crawler が絞り込み・並べ替えに使う項目(`record_type`・`source_id`・`status`・`queued_at` など。`crawler-architecture-v0.4.md` 3.1 のマッピング案)を足して**拡張した**。`dynamic: false` のまま(未定義の項目は索引せず保存する)。`settings_snapshot`・`finish_notice`・`registration`・`deletion_summary`・`warnings` は索引しない object。Crawler の結合テスト(13 件)と Indexer の結合テスト(40 件)が、この定義で通ることを確認した。
  - 制約: `enabled` は boolean、`lease_expires_at` は date で定義しているため、型に合わない値の文書(例: `enabled` が真偽値でない)は OpenSearch が書き込みを拒否する。Indexer の fail-closed 分岐(不正なロック文書の扱い)は、この環境では実機で再現できない。
- `infra/opensearch/schema/sources.json`(新設): `loreley-sources`(データソース設定。Crawler だけが書く)を `dynamic: strict` で定義した(項目は `crawler-architecture-v0.4.md` 3.1・3.2。`connector_config` は索引しない object)。定義にない項目の書き込みは OpenSearch が拒否する。`opensearch-init` が `SOURCES_INDEX_NAME` の名前で作る。
- **既存のボリュームでも、`loreley-jobs` の拡張は init が `PUT _mapping` で足す**(`loreley-sources` は、無ければ作る)。拡張前の定義の索引で、足す前は `status` の検索が 0 件、足した後は 1 件になることと、再実行しても結果が変わらないことを実機で確認した。結合テスト `test_01_startup.py` に、旧定義の索引を使うテストを 1 件置いている。

## トラブルシュート

実機で起きた事象と、起きていない(想定の)事象を分けて書く。**想定(未確認)**は、実機で再現していない。

### `docker compose up -d --wait` が戻らない(実機で確認)

- 事象: compose v2.3.3 で、全サービスが `Healthy` / `Exited(0)` になったあとも、コマンドが戻らない(2 回再現)
- 対処: `--wait` を付けずに `docker compose up -d` を使い、`docker compose ps` で opensearch・indexer が healthy になるのを確認する。すでに待ち続けている場合は、そのコマンドを中断してよい(実機では、中断したあともスタックは起動したままだった。`ps` で確認する。なお、`timeout` 相当で docker CLI だけを止めると、compose のプロセスが残ることがあった)
- 原因は特定していない(`opensearch-init` のような終了済みの使い捨てサービスを待ち続けている可能性があるが、未確認)。新しい compose では直っている可能性があるが、未確認

### ポートが衝突する

- 実機で確認したこと: 9200 を別のプロセスが使っているとき、`scripts/run-indexer-integration-test.sh` が事前確認で検出し、原因と対処を表示して終了コード 1 で中止する(スタックには触れない)。`scripts/run-crawler-integration-test.sh` も、8001 を塞いだ状態で同様に中止した(スクリプトの修正前の版での確認)。実測では、起動した OpenSearch に `fess_config.coordinator` という索引が現れた。**索引名から Fess が書き込んだと推定**している(書き込んだプロセスの特定は未確認)。9200 を別のアプリが使う・接続している環境では、同様に索引が作られることがある(`loreley-*` には影響しなかった)
- 想定(未確認): `docker compose up` を直接実行した場合は、`bind: address already in use` で `opensearch` または `indexer` の起動に失敗する
- 対処(案): 使用中のプロセスを止める。または `.env` の `OPENSEARCH_HOST_PORT` / `INDEXER_HOST_PORT` を変える(結合テストのスクリプトは 9200・8000・8001 に固定するので、変えられない)

### OpenSearch が OOM で落ちる(exit 137)(想定。未確認)

- 想定: Docker に割り当てたメモリが足りない。`docker compose ps -a` で `opensearch` が `Exited (137)` になる。確認環境(約 3.8GiB)では起きなかった
- 対処(案): Docker のメモリを増やす、または `OPENSEARCH_HEAP_SIZE` を下げる

### `opensearch-init` が失敗する(想定。未確認)

- 想定: `docker compose logs opensearch-init` に HTTP ステータスと応答本文が出る(スクリプトは失敗時に非 0 で終了する。コードの確認で、実機で失敗させてはいない)。`indexer` は起動しない
- 対処: 原因を直して `docker compose up -d` をやり直す(冪等)

### `opensearch` / `indexer` が unhealthy のまま(想定。未確認)

- 想定: `opensearch` は JVM の起動待ち(`start_period` 60 秒)、`indexer` は起動時の整理待ち(イメージの `start-period` 120 秒)。OpenSearch 3.9.0 の JVM 起動は 1〜2 分かかった(1 回の測定の目安)。猶予(60 秒 + 10 秒 × 12 回)を超えると unhealthy になる(初回の結合テストで 1 回発生。原因は未特定)。OpenSearch 2.19.7 では、この待ちは 20 秒程度だった(上記の目安は 2.19.7 での値)
- 対処(案): `docker compose logs` で原因を確認し、待っても変わらなければメモリを確認する
