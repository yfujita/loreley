# deploy/compose

OpenSearch と Indexer を起動する compose 構成(MVP)。`compose.yaml` が `opensearch`・`opensearch-init`・`indexer` の 3 サービスを定義する。

> **確認状況**: 特記がない限り、次の環境で実機確認した事実だけを書いている。「未確認」「想定(未確認)」と書いた箇所は、実機で確認していない。
>
> - 確認環境: macOS(x86_64)、Docker 20.10.13(Docker Desktop。VM のメモリ約 3.8GiB、CPU 2)、docker compose v2.3.3
> - 結合テスト(`tests/integration/indexer`)は、この構成を専用のプロジェクト名 `loreley-it` で起動して実行する。手順と結果は [tests/integration/indexer/README.md](../../tests/integration/indexer/README.md) を参照

## 構成

| サービス | 役割 | ホストへの公開 |
| --- | --- | --- |
| `opensearch` | 検索インデックスと Store 層のバックエンド(単一ノード、セキュリティ無効) | `127.0.0.1:9200` |
| `opensearch-init` | インデックス(`loreley-documents-000001` とエイリアス `loreley-documents`、`loreley-deletions`、`loreley-jobs`)を作る使い捨てコンテナ。冪等。作成後は終了する | なし |
| `indexer` | `apps/indexer` をビルドして起動。`opensearch` が healthy で、`opensearch-init` が正常終了してから起動する | `127.0.0.1:8000` |

スキーマと init スクリプトは `infra/opensearch/` にある。

## 前提

- Docker と docker compose v2(確認した版: Docker 20.10.13、compose v2.3.3。`up --wait` は使わない。後述)
- Docker に割り当てるメモリは **4GB 以上を推奨**。OpenSearch の JVM ヒープは既定 512m(最大 512MiB を実測で確認)で、Docker VM のメモリが約 4GB の環境を想定している。確認環境(約 3.8GiB)でのアイドル時の使用メモリは、OpenSearch 約 855MiB、Indexer 約 56MiB。ほかの重いコンテナを同時に動かさない
- ホストのポート `9200`(OpenSearch)と `8000`(Indexer)が空いていること(`.env` で変えられる)
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
| `OPENSEARCH_VERSION` | `2.19.7` | OpenSearch のイメージのタグ |
| `OPENSEARCH_HEAP_SIZE` | `512m` | JVM ヒープ(`-Xms` と `-Xmx` の両方に使う) |
| `OPENSEARCH_HOST_PORT` | `9200` | OpenSearch のホスト側ポート |
| `INDEXER_HOST_PORT` | `8000` | Indexer のホスト側ポート |
| `INDEXER_LOG_LEVEL` | `INFO` | Indexer のログレベル |

秘密値はない。

## 起動・停止・初期化

`deploy/compose` で実行する。

```sh
docker compose up -d --build          # 起動(`--wait` は使わない。後述)
docker compose ps                     # 状態の確認。opensearch・indexer が healthy になるまで待つ(opensearch-init は Exited (0) になる)
curl http://127.0.0.1:9200/_cluster/health
curl http://127.0.0.1:8000/healthz

docker compose down                   # 停止(データは残る)
docker compose down -v                # 停止してデータ(名前付きボリューム)も削除
```

- **`up --wait` は使わない**: compose v2.3.3 では、全サービスが Healthy / Exited(0) になったあとも `up -d --wait` が戻らない(2 回再現。原因の特定はしていない)。起動済みのスタックに対して `--wait` なしの `up -d` を再実行すると 3 秒で戻った(クリーン起動では次の「起動の所要時間」のとおり時間がかかる)。`up -d` は、`opensearch` が healthy になり `opensearch-init` が正常終了するのを待ってから `indexer` を起動する。起動完了は `docker compose ps` で確認する。`--wait-timeout` もこの版には無い。待機つきで起動したいときは、`docker compose ps` を一定間隔で確認する形にする(`scripts/run-indexer-integration-test.sh` が実装している)
- **起動の所要時間**(1 回の実測。目安。実装担当の報告による。ログは保存していない): クリーンな状態からイメージのビルドを含めた `up -d --build` が初回約 90 秒、そのあと healthy になるまで約 20 秒。ビルドのキャッシュがあれば短い
- **初期化**: インデックスは `opensearch-init` が起動のたびに確認し、無いものだけ作る(冪等)。既存のインデックスは変更しない。再実行すると、すべて `skip` と表示して終了する(確認済み)。検索インデックスは、エイリアス `loreley-documents` の有無で判定する。再インデックスでエイリアスを `-000002` に付け替えて `-000001` を削除した状態でも、空の `-000001` は作り直さない(その状態を模擬して確認済み)
- **マッピングを変えたいとき**: `infra/opensearch/schema/*.json` を直しても、既存のインデックスは変わらない(init は既存を変更しない。検索インデックスと `loreley-deletions` は `dynamic: strict` なので、定義にない項目を書くと拒否される)。開発用のデータを消してよいなら、`docker compose down -v` でボリュームごと消して、`up -d` で作り直す。**データを残したまま変える手順(再インデックス)は、本タスクでは未確認**(対象外。設計は `apps/indexer/README.md` 8 章と arch 11 章)
- **停止**: Indexer は SIGTERM を受けると `Shutting down` → `Application shutdown complete` と出して、1 秒で終了コード 0 で止まる(`stop_grace_period` は 30 秒)
- 結合テストなど、開発用スタックと分けたい場合は `-p <プロジェクト名>` を付ける(ボリュームも別になる)。結合テストは `scripts/run-indexer-integration-test.sh` が `-p loreley-it` で起動して実行し、終わると `down -v` で消す。開発用のスタックに向けて結合テストを実行しない(テストはデータを削除しない)

## ループバックのみ公開する理由

- Indexer API には認証・認可がない。`DELETE` でソースの文書を全削除することまで呼べる
- OpenSearch もセキュリティプラグインを無効にしている(認証・TLS なし)
- そのため、ホストへの publish は `127.0.0.1`(同じホストからのみ)に限っている。`0.0.0.0`(全 NIC)への公開は、同じネットワークの誰でも削除などを実行できるようになるのでしない
- ホスト側ポートは `.env` で変えられるが、バインド先は常に `127.0.0.1`
- コンテナ間は、compose の内部ネットワークでサービス名(`http://opensearch:9200`)で通信する。ホストへの publish は、開発者が `curl` などで確認するためのもの
- 他のホストから使う必要が出たら、認証付きのリバースプロキシなどを前に置く(MVP の対象外)

## OpenSearch のバージョン固定方針

- イメージは `opensearchproject/opensearch:2.19.7`。パッチまでのタグで固定し、`latest` は使わない(取得のたびに変わらないため、再現できる)。ダイジェストは固定しない(タグの固定で足りると判断した)
- 2.19 を選んだ理由: 2.19 は maintenance 系列で、Indexer が使う opensearch-py 3.2.0 の CI が検証対象としている系列のため(調査による。出典の再確認はしていない)
- バージョンは `.env` の `OPENSEARCH_VERSION` で変えられる。上げるときは、結合テスト(`tests/integration/indexer`)を通してから使う
- 確認した実体(参考): `opensearchproject/opensearch:2.19.7`(ダイジェスト `sha256:3bfa1ec74d56928c2e018033d45c460ce2c0ea65a5cedd577de3102326c31b89`、build_hash `6dd9a042`、JDK 21.0.12.1)。単一ノードで起動し、Indexer が接続して起動時の整理まで完了し、結合テストが通ることを確認した(結果は [indexer-integration.md](../../docs/v0.x/test-results/indexer-integration.md))
- 2.19 以外のバージョンは未確認

## `loreley-deletions` と `loreley-jobs` のマッピングは仮定義

- `infra/opensearch/schema/deletions.json`: 設計書(loreley-deletions v0.10)は、マッピング全体を未決(U-2)とし、Indexer が実装で前提とする項目だけを置いている。Indexer が書く項目(`records.py` の `to_body()` の全キー)を `dynamic: strict` で定義した仮定義であり、設計確定時に置き換える。
- `infra/opensearch/schema/jobs.json`: Crawler の設計が未決のため、Indexer が読む最小限の項目(`owner`・`job_id`・`lease_expires_at`・`enabled`)だけを定義し、`dynamic: false` にしている。結合テスト用の仮定義であり、Crawler の設計確定時に置き換える。
  - 制約: `enabled` は boolean、`lease_expires_at` は date で定義しているため、型に合わない値の文書(例: `enabled` が真偽値でない)は OpenSearch が書き込みを拒否する。Indexer の fail-closed 分岐(不正なロック文書の扱い)は、この環境では実機で再現できない。

## トラブルシュート

実機で起きた事象と、起きていない(想定の)事象を分けて書く。**想定(未確認)**は、実機で再現していない。

### `docker compose up -d --wait` が戻らない(実機で確認)

- 事象: compose v2.3.3 で、全サービスが `Healthy` / `Exited(0)` になったあとも、コマンドが戻らない(2 回再現)
- 対処: `--wait` を付けずに `docker compose up -d` を使い、`docker compose ps` で opensearch・indexer が healthy になるのを確認する。すでに待ち続けている場合は、そのコマンドを中断してよい(実機では、中断したあともスタックは起動したままだった。`ps` で確認する。なお、`timeout` 相当で docker CLI だけを止めると、compose のプロセスが残ることがあった)
- 原因は特定していない(`opensearch-init` のような終了済みの使い捨てサービスを待ち続けている可能性があるが、未確認)。新しい compose では直っている可能性があるが、未確認

### ポートが衝突する

- 実機で確認したこと: 9200 を別のプロセスが使っているとき、`scripts/run-indexer-integration-test.sh` が事前確認で検出し、原因と対処を表示して終了コード 1 で中止する(スタックには触れない)
- 想定(未確認): `docker compose up` を直接実行した場合は、`bind: address already in use` で `opensearch` または `indexer` の起動に失敗する
- 対処(案): 使用中のプロセスを止める。または `.env` の `OPENSEARCH_HOST_PORT` / `INDEXER_HOST_PORT` を変える(結合テストのスクリプトは 9200・8000 に固定するので、変えられない)

### OpenSearch が OOM で落ちる(exit 137)(想定。未確認)

- 想定: Docker に割り当てたメモリが足りない。`docker compose ps -a` で `opensearch` が `Exited (137)` になる。確認環境(約 3.8GiB)では起きなかった
- 対処(案): Docker のメモリを増やす、または `OPENSEARCH_HEAP_SIZE` を下げる

### `opensearch-init` が失敗する(想定。未確認)

- 想定: `docker compose logs opensearch-init` に HTTP ステータスと応答本文が出る(スクリプトは失敗時に非 0 で終了する。コードの確認で、実機で失敗させてはいない)。`indexer` は起動しない
- 対処: 原因を直して `docker compose up -d` をやり直す(冪等)

### `opensearch` / `indexer` が unhealthy のまま(想定。未確認)

- 想定: `opensearch` は JVM の起動待ち(`start_period` 60 秒)、`indexer` は起動時の整理待ち(イメージの `start-period` 120 秒)。正常な起動では、この待ちは 20 秒程度だった(上記の目安)
- 対処(案): `docker compose logs` で原因を確認し、待っても変わらなければメモリを確認する
