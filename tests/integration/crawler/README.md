# 結合テスト(Crawler)

compose で起動した**実 OpenSearch・実 Indexer・実 Crawler**に対して、ホストの pytest から実行する結合テスト。テストは Crawler の HTTP API(`127.0.0.1:8001`)を呼んでクロールなどを起動し、結果を OpenSearch の実データ(`loreley-jobs`・`loreley-deletions`・`loreley-sources`・検索インデックス)を直接読んで確かめる。Crawler にはジョブの状態を取得する API がないため(Admin API が OpenSearch を読む設計)、判定は HTTP 応答と OpenSearch の実データの両方で行う。

> **確認状況**: 実行結果(passed 件数・所要時間・環境)は [docs/v0.x/test-results/crawler-integration.md](../../../docs/v0.x/test-results/crawler-integration.md) に書く。この文書には書かない。
> macOS(x86_64)・Docker 20.10.13・compose v2.3.3・uv 0.13.8 でのみ確認した(クリーンな状態からスクリプトを 2 回連続で実行し、どちらも 13 passed。PR レビュー対応でテストを 1 件足した最終版は 14 passed。2026-11-18)。Linux ホストなどは未確認。

## 目的

Crawler の単体テストは、OpenSearch・Indexer・ファイルシステムを fake やスタブに差し替えている(`apps/crawler/README.md` 7 章)。この結合テストは、`apps/crawler/README.md` 8 章の「fake だけでは検証できないこと」のうち、次を実機で確かめる。

- compose で起動した Crawler が、実 OpenSearch に接続して起動時の回復を終え、`healthy` になること
- 主要フロー(設定の登録 → クロール起動 → 列挙・取得 → Indexer へのバッチ登録・終了通知 → 削除結果の確認)が、実 Indexer との間で通り、件数照合(`enumerated_count == n_seen + e_missing`)が成立すること
- 2 回目のクロールでの TTL 削除、ソース削除ジョブ、原本サイズ超過、ロックの実体、メンテナンスフラグ

## 前提

| 項目 | 内容 |
| --- | --- |
| Docker | Docker と docker compose v2(確認した版: Docker 20.10.13、compose v2.3.3)。デーモンが起動していること |
| uv | 必要(確認した版: uv 0.13.8)。`tests/integration/crawler/uv.lock` で依存を固定している。依存を変えたら、`tests/integration/crawler` で `uv lock` を実行して更新する |
| メモリ | Docker に**約 4GB 以上**を推奨。OpenSearch + Indexer + Crawler を約 3.84GiB の VM で同時に起動して、全件成功した(使用量は測定していない)。ほかの重いコンテナを同時に動かさない |
| ポート | ホストの `9200`(OpenSearch)・`8000`(Indexer)・`8001`(Crawler)が空いていること。すべて `127.0.0.1` だけに publish する。**スクリプトは 3 つのポートに固定**し、`deploy/compose/.env` の値では変えられない(テストがこの 3 つに接続する)。手動で別のポートにしたときだけ、`LORELEY_IT_OPENSEARCH_URL`・`LORELEY_IT_INDEXER_URL`・`LORELEY_IT_CRAWLER_URL` でテストの接続先を合わせる |
| 索引名 | スクリプトは `LORELEY_JOBS_INDEX_NAME`・`LORELEY_SOURCES_INDEX_NAME` を既定値(`loreley-jobs`・`loreley-sources`)に固定する。手動で起動して索引名を変えたときは、**同じ環境変数を pytest にも渡す**(テストは同じ変数を読む。未指定は既定値) |
| ネットワーク | 初回は、ベースイメージ・OpenSearch のイメージ・Python の依存を取得する |

Linux の `vm.max_map_count` と SELinux(bind mount のラベル)は未確認(`deploy/compose/README.md` の前提を参照)。

**ポート 9200 を別のアプリが使っている・接続している場合**: スクリプトは事前確認で中止する(止めはしない)。また、実測では、起動した Loreley のテスト用 OpenSearch に `fess_config.coordinator` という索引が現れた。**索引名から Fess が書き込んだと推定**している(書き込んだプロセスの特定は未確認)。ホスト上の別アプリが `127.0.0.1:9200` に接続し続けていると、同様の索引が作られることがある(`loreley-*` には影響しなかった。`down -v` で消える)。

## 実行方法

### 一括で実行する(通常はこれ)

リポジトリのルートで、スクリプトを実行する。スタックの起動、起動の待機、pytest、後始末(`down -v` と `data/` の削除)までを行う。

```sh
scripts/run-crawler-integration-test.sh                  # 全シナリオ
scripts/run-crawler-integration-test.sh --keep           # 終了後もスタックと data/ を残す(デバッグ用)
scripts/run-crawler-integration-test.sh -k test_30_ttl   # 1 ファイルだけ(ファイル名の語で絞る)
scripts/run-crawler-integration-test.sh -k oversize      # 名前に oversize を含むテスト
```

- `--keep` と `-h` 以外の引数は、そのまま pytest に渡る。**絞り込みには `-k` を使う**(「シナリオ ID でテストを選べない」を参照)
- スクリプトは `docker compose -p loreley-it -f deploy/compose/compose.yaml -f tests/integration/crawler/compose.test.yaml up -d --build opensearch opensearch-init indexer crawler` で起動する。**`up --wait` は使わず**、3 秒間隔で状態を確認して、`opensearch`・`indexer`・`crawler` が healthy、`opensearch-init` が Exited(0) になるのを待つ(compose v2.3.3 では `--wait` が戻らないため。`deploy/compose/README.md` を参照)
- 異常終了したときは、`docker compose ps -a` と各サービスのログの末尾 100 行を表示してから、後始末する
- 起動前に、`loreley-it` の前回のコンテナの残り(停止中を含む)・名前付きボリュームの残り・空でない `data/`・ポートの使用中を確認し、あれば原因と対処を出して中止する(スタックにも、ボリュームにも、`data/` にも触れない)。終了時の `down -v` と `data/` の削除が、前回 `docker compose down`(`-v` なし)で止めただけのボリュームや、利用者が `data/` に置いたファイルを消さないため

#### 終了コード

| コード | 意味 |
| --- | --- |
| 0 | 全テスト成功 |
| 1 | pytest のテスト失敗、**または**引数・事前確認の失敗(Docker・uv が無い、ポート使用中、前回の `loreley-it` の残りなど)。事前確認の失敗は標準エラー出力に理由が出るので区別できる |
| 2〜5 | pytest の終了コードのまま(2=中断。スタックに接続できない・メンテナンスフラグが残っている・`data/` がない、4=pytest の使い方の誤り、5=該当テストなし) |
| 10 | スタックの起動失敗(`up` の失敗、待機の上限超過、コンテナの異常終了) |
| 130 / 143 | Ctrl-C(INT)/ TERM で中断(どちらも後始末まで行う) |

#### 環境変数

| 変数 | 既定 | 説明 |
| --- | --- | --- |
| `LORELEY_IT_WAIT_TIMEOUT_SECS` | `300` | 起動後の待機の上限(秒)。1 以上の整数 |

`OPENSEARCH_VERSION`・`OPENSEARCH_HEAP_SIZE`・`CRAWLER_LOG_LEVEL` などの compose の変数は、そのまま compose に渡る(`deploy/compose/.env.example`)。ただしホスト側ポートと `CRAWLER_DOCUMENTS_DIR` はスクリプトが固定する。あわせて、Crawler と api に同じ変数から渡る `LORELEY_CRON_TIMEZONE=UTC`・`LORELEY_ADMITTING_LOCK_GRACE_SECONDS=60`(compose の既定値)も固定し、シェルや `deploy/compose/.env` の値に左右されないようにしている(この Crawler の IT に、この 2 変数を使うテストはない)。

### 手動で実行する(スタックを起動して pytest を直接実行する)

テストを繰り返し実行するときなど、スクリプトを使わずに起動と pytest を分ける手順。リポジトリのルートで実行する。

```sh
# 1. 検索対象のディレクトリを作る(Docker に作らせると root 所有になりうる。想定。未確認)
mkdir -p tests/integration/crawler/data && chmod 755 tests/integration/crawler/data

# 2. 起動(`--wait` は使わない。CRAWLER_DOCUMENTS_DIR は絶対パスで渡す)
CRAWLER_DOCUMENTS_DIR="$PWD/tests/integration/crawler/data" \
  docker compose -p loreley-it -f deploy/compose/compose.yaml -f tests/integration/crawler/compose.test.yaml \
  up -d --build opensearch opensearch-init indexer crawler

# 3. opensearch・indexer・crawler が healthy になるまで待つ(opensearch-init は Exited (0) になる)。
#    crawler が healthy になる前に pytest を始めると、疎通確認で中止される(終了コード 2)。
#    crawler は起動時の回復が終わるまで接続できない(healthcheck の start_period は 180 秒)
docker compose -p loreley-it -f deploy/compose/compose.yaml -f tests/integration/crawler/compose.test.yaml ps

# 4. テストを実行する
uv run --project tests/integration/crawler pytest tests/integration/crawler -v

# 5. 後始末(ボリュームも消す。コンテナを消してから data/ を削除する)
docker compose -p loreley-it -f deploy/compose/compose.yaml -f tests/integration/crawler/compose.test.yaml down -v --remove-orphans
rm -rf tests/integration/crawler/data
```

- 手順 1 の `chmod 755` は、umask が 077 のユーザーでも、uid 10001 の Crawler がディレクトリを列挙できるようにするため
- **`up` のときに `CRAWLER_DOCUMENTS_DIR` を渡さないと、compose の既定(`deploy/compose/documents`。無ければ自動作成される)が mount され、テストが `data/` に置いた文書を Crawler が読めず、0 件列挙で失敗する**。`ps`・`down` では不要
- テストは `compose.test.yaml` の値(原本の上限 64 KiB、ポーリング間隔 2 秒など)を前提にしている。`deploy/compose/compose.yaml` だけで起動したスタックに向けて実行しない(CIT-21・CIT-23・CIT-40 のサイズ超過の前提が崩れて失敗する)
- スタックが起動していないと、pytest は接続できなかった理由と起動手順を表示して、終了コード 2 で中止する

### Indexer の結合テストと同時に動かせない

Indexer の結合テスト(`scripts/run-indexer-integration-test.sh`)とは、**compose のプロジェクト名(`loreley-it`)とホストのポート(9200・8000)が同じ**ため、同時には実行できない(同時に動かすと、事前確認がポート使用中で中止する)。どちらかを終えて `down -v` してから、もう一方を実行する。

- Indexer 用のスクリプトは、起動するサービスを `opensearch opensearch-init indexer` に明示しており、`crawler` は起動しない。Crawler 用のスクリプトが使う `compose.test.yaml` も別のファイルで、重ねて使わない
- 両方とも、テスト用の上書き(`MAX_RAW_BYTES` などの値)が違う。他方のスタックに向けて実行しない

### api の結合テストと同時に動かせない

api の結合テスト(`scripts/run-api-integration-test.sh`)とも、**compose のプロジェクト名(`loreley-it`)とホストのポート(9200・8000・8001)が同じ**ため、同時には実行できない。どちらかを終えて `down -v` してから、もう一方を実行する。api の結合テストは、`api` のポート(8080)も使う。

## 結果の見方

- スクリプトで実行すると、pytest の出力が標準出力と `tests/integration/crawler/results/pytest-YYYYMMDD-HHMMSS.log` に残る(実行のたびに増える。`.gitignore` 済み)
- 失敗したテストの詳細は、このログの `FAILURES` の節にある。スタックの状態は、同じ実行の最後に出る `docker compose ps -a` と各サービスのログの末尾(異常終了のとき)を見る。`--keep` で残したスタックなら、`docker compose -p loreley-it -f deploy/compose/compose.yaml -f tests/integration/crawler/compose.test.yaml logs crawler`で全体を見られる
- 実行結果の記録は [docs/v0.x/test-results/crawler-integration.md](../../../docs/v0.x/test-results/crawler-integration.md)

## シナリオ一覧

各テストの docstring に、【何を確認するか】【前提と手順】【期待する結果とその根拠(設計書の章)】【fake では確認できず実機で確認する点】がある。表の「設計書」は、期待値の根拠にした章(arch = `crawler-architecture-v0.4.md`、api = `crawler-api-v0.4.md`、FS = `connector/connector-file-system-v0.3.md`、Indexer arch = `indexer-architecture-v0.10.md`)。全部で 14 テスト。

| ID | ファイル | テスト関数 | 何を確認するか | 設計書 |
| --- | --- | --- | --- | --- |
| CIT-01 | `test_01_startup.py` | `test_crawler_is_healthy_after_the_startup_recovery` | `/healthz` が 200 `{"status":"ok"}`(起動時の回復を終えている) | api 4.7、arch 5.8・10 章 |
| CIT-01 | `test_01_startup.py` | `test_all_four_indices_exist_and_the_search_index_is_an_alias` | 4 索引(検索インデックスはエイリアス `loreley-documents` が実体 1 つを指す、`loreley-deletions`、`loreley-jobs`、`loreley-sources`)が存在する | arch 3.1 |
| CIT-01 | `test_01_startup.py` | `test_sources_index_is_strict_and_jobs_index_defines_the_fields_crawler_queries` | `loreley-sources` が `dynamic: strict` で 9 項目の型が定義されている。`loreley-jobs` が `dynamic: false` で、Crawler が絞り込み・並べ替えに使う主要項目(`record_type`・`source_id`・`job_type`・`status`・`document_id`・`queued_at`)と Indexer の 4 項目(`owner`・`job_id`・`lease_expires_at`・`enabled`)の型を定義している(それ以外の項目はアサートしない) | arch 3.1 |
| CIT-01 | `test_01_startup.py` | `test_init_adds_the_missing_fields_to_an_existing_jobs_index` | 拡張前の定義(4 項目・`dynamic: false`)の索引では `status` の検索が 0 件。`opensearch-init` のスクリプトをその索引名で再実行すると、不足項目が足され(型が正しく、既存 4 項目は不変)、同じ検索が 1 件ヒットする(既存のボリュームでも Job Runner が動く) | arch 3.1 |
| CIT-10 | `test_10_source_registration.py` | `test_register_source_is_stored_and_a_resend_is_accepted_as_is` | `POST /sources` が 201 で、`loreley-sources` に strict のまま保存される。同内容の再送は 200 | api 4.4.2、arch 3.1・3.2 |
| CIT-10 | `test_10_source_registration.py` | `test_register_source_rejects_an_unknown_connector_config_item` | 未知の `connector_config` 項目は 400 `config_invalid`、保存されない | api 3.3、FS 2 章 |
| CIT-10 | `test_10_source_registration.py` | `test_start_crawl_of_an_unregistered_source_is_rejected_with_404` | 設定のないソースのクロール起動は 404 `source_config_not_found`、ジョブ記録・ロックは作られない | api 4.1 |
| CIT-20 | `test_20_crawl.py` | `test_crawl_indexes_the_documents_and_the_counts_reconcile` | txt/md/html/pdf + サブディレクトリの 5 件が索引され、`.csv`・隠しファイルは索引されない。`document_id` が独立実装と一致。`enumerated_count == n_seen + e_missing`(5 == 5 + 0)で `validation_failed` にならない | arch 4.5・7.5〜7.7、FS、Indexer arch 9.6 |
| CIT-21 | `test_20_crawl.py` | `test_crawl_records_an_oversize_document_and_the_counts_still_reconcile` | Crawler 側の原本サイズ超過(70,000 バイト)が `oversize` 記録になり、`oversize_document_ids` に載って、索引されない。ジョブは `succeeded`、件数照合は 2 == 1 + 1 | arch 6.5・7.5 |
| CIT-22 | `test_20_crawl.py` | `test_lock_exists_while_the_crawl_runs_and_is_released_afterwards` | 実行中に `lock-{source_id}` が実在し(`owner=crawler-1`、`job_id`、未来の `lease_expires_at`)、終了後に消える | arch 5.1・4.5 |
| CIT-23 | `test_20_crawl.py` | `test_oversize_record_is_purged_when_the_file_is_removed` | (当初案にない追加)サイズ超過のファイルを消して再クロールすると、その `oversize` 記録が整理される | arch 6.4 の (b) |
| CIT-30 | `test_30_ttl_deletion.py` | `test_files_that_disappeared_are_deleted_and_the_files_that_remain_survive` | 2 回目のクロール(B)で、消えたファイルの文書だけが TTL 削除され、残ったファイル・新しいファイルの文書は残る。他のソースは残る。`T=2`・`D=6`・`deleted_count=2` | arch 4.6・7.5・7.6、Indexer arch 9.3・9.6〜9.8 |
| CIT-40 | `test_40_source_deletion.py` | `test_source_delete_removes_everything_of_the_source_and_leaves_the_other_source` | ソース削除ジョブ(順 0〜6)で、対象ソースの文書・記録・`oversize` 記録・設定・ロックが消え、他のソースは残る。削除後のクロール起動は 404 | arch 8.1・8.3、api 4.1・4.6 |
| CIT-50 | `test_50_maintenance.py` | `test_crawl_is_rejected_while_the_maintenance_flag_is_set` | メンテナンスフラグがあるとクロール起動が 409 `maintenance_enabled`(ジョブ記録・ロックなし)。フラグを削除すると 202 で `succeeded` | arch 7.9・4.3、api 4.1 |

### シナリオ ID でテストを選べない

テスト関数の名前には `CIT-nn` が含まれない(ID は各ファイルの冒頭にある。CIT-23 はテストの docstring にも)。`-k CIT-30` は **0 件になる**(終了コード 5)。ファイル名か、テスト名の語で選ぶ。

- ファイル名の語を `-k` に渡す: 例 `-k test_30_ttl`
- 名前のキーワードを使う: 例 `-k oversize`(CIT-21・CIT-23)。キーワードはほかのテストにも一致しうるので、`--collect-only -q` で対象を確認してから実行する
- **スクリプトにファイルやノード ID(`ファイル::テスト名`)をパス引数で渡しても、絞られず全テストが走る**(既定のコマンドの末尾に `tests/integration/crawler` があるため)。ノード ID で指定したいときは、「手動で実行する」の手順で pytest を直接実行する
- 収集だけ確認したいときは、スクリプトを使わず `uv run --project tests/integration/crawler pytest tests/integration/crawler --collect-only -q` を実行する(`--collect-only` では疎通確認のフィクスチャが走らないため、スタックは不要のはず。Crawler の IT では未確認)

## 未実施(スコープ外)

次は、このテストでは確認していない主なもの。**未実施・未確認の完全な一覧は [crawler-integration.md](../../../docs/v0.x/test-results/crawler-integration.md) の 6 章、項目別の判定の正本は同 4.3**(用語は同じで、未実施=テストを作っていない、未確認=実機で見ていない)。

- `fetch_permission_denied` / `skip` 記録 / `partially_succeeded`(権限エラー)、ソース削除の順 3 の `skip` 記録の削除
- 10,001 件超の全件走査、`create` の並行時の原子性、スレッド安全性
- 運用系: 起動時の回復、`docker stop` の所要時間、ロック解放 API・取り消し API、定期起動
- ソース削除ジョブ起動時のメンテナンス 409、メンテナンスフラグを `enabled: false` で下ろす手順
- 実 NFS/SMB、Web Connector

## テスト設計上の注意

- **ID はテストごとに一意**: `source_id` はテストごとに作る(フィクスチャ。`it-` で始まり、半角英数字・`-` だけ)。テストはデータ(OpenSearch 上のソース・文書・記録)を**削除しない**(CIT-40 のように削除ジョブを確認するものを除く)。後始末はスタックごと `down -v` で消すことに任せている。**開発用のスタックに向けて実行しない**
- **TTL は実時間で待たない**: CIT-30 は、クロール A のあとに OpenSearch へ直接書いて全文書の `last_seen_at` を 2 時間前にする(`support.py` の `force_last_seen_at`。`ttl=600`)。Crawler は `crawl_started_at` を自分の時計で決めるため、クロールの時刻を過去にはできない。クロール B で残る文書は、Crawler が `last_seen_at` を更新したから残る(更新されなかった文書だけが削除される)ことで、Crawler の `last-seen`・登録が文書を守ることを確認する。**Indexer 内部の項目名 `last_seen_at` に依存する**(Indexer の結合テストと同じ前例。項目名が変わると両方が壊れる)。割合ルールは、削除を妨げない値(`ratio_threshold=0.5`、`min_delete_count=0`、T/D = 2/6)にしてある
- **ロックの観測は窓に依存する**: CIT-22 は、ロックにリース期限が付いてからジョブが終わるまでの約 3.3 秒(削除結果のポーリング間隔 2 秒が決める)に、0.2 秒間隔で観測する。極端に速い環境では観測できず失敗しうる(失敗メッセージで原因が分かる)。リース期限の判定はホストと Docker VM の時計に依存する(許容幅は 1 時間)
- **メンテナンスフラグは必ず削除する**: CIT-50 は `try/finally` で削除し、削除を確認する。残ると、すべてのクロール起動が 409 になり、Indexer の削除判断も止まる
- **検証は Crawler の応答だけで済ませない**: OpenSearch を直接読む(検索系は `_refresh` してから `_count`・`_search`)。待ちは、間隔と上限を明示したポーリングで、`sleep` に頼らない
- **実機が設計と違ったとき**: テストを実機に合わせて変えず、発見事項として扱う(設計書の改版はユーザー判断)
- `connector_type` は `file_system`(`filesystem` は 400)

## メンテナンスフラグが残ったときの復旧

テストが途中で中断(強制終了など)すると、`loreley-jobs` の `maintenance` 文書が残りうる。残ったままだと、次の実行は conftest の確認で `pytest.exit`(終了コード 2)する。次のどちらかで復旧する。

```sh
# 1. フラグだけ消す
curl -X DELETE http://127.0.0.1:9200/loreley-jobs/_doc/maintenance

# 2. スタックごと作り直す(通常はこちら。スクリプトの後始末と同じ)
docker compose -p loreley-it -f deploy/compose/compose.yaml -f tests/integration/crawler/compose.test.yaml down -v --remove-orphans
```

`down -v` は OpenSearch のデータ(名前付きボリューム)ごと消すので、フラグも消える。`down` に `CRAWLER_DOCUMENTS_DIR` は不要。

## `data/` と `CRAWLER_DOCUMENTS_DIR`

- `tests/integration/crawler/data/` は、Crawler に `:ro` で mount する検索対象の文書の置き場。**`.gitignore` 済み**で、リポジトリには含めない。コンテナ内では `/data/documents`
- スクリプトは、起動前に `data/` を作って `chmod 755` し、終了時に `compose down` のあとで削除する(使用中の mount 元を消さないため)。`compose down` が失敗したときは、コンテナが残っている可能性があるので `data/` を**削除せず**、手動で消すよう案内する。`--keep` のときは残す
- テストは、`data/<source_id>/`(コンテナ内 `/data/documents/<source_id>`)を作り、`samples/` のファイルや生成したファイルを置いて、テストの終了後に削除する(`support.py` の `SourceDirectory`)。設定の `connector_config.root` は、このコンテナ内のパス。ファイルは 0644、ディレクトリは 0755(Crawler は uid 10001 で動くため、others が読める権限にする)
- `CRAWLER_DOCUMENTS_DIR` は、compose の `crawler` サービスが `:ro` で mount するホスト側のパス(`deploy/compose/.env.example`)。**スクリプトは `data/` の絶対パスを export する**(相対パスは `compose.yaml` のあるディレクトリが基準になり、意図した場所にならない)。テスト側(`support.py`)も、同じ環境変数があればそれを、なければ `tests/integration/crawler/data` を使う。**両者が同じ場所でないと、テストが置いた文書を Crawler が読めない**
- マウントの可視性の遅れ(ホストで書いた直後にコンテナから見えるか)は、Docker Desktop(macOS)では観測されなかった(10 回)。Linux などは未確認

## サンプル文書を追加する

固定の原本は `samples/` にある。形式ごとの期待と PDF の生成方法は [samples/README.md](samples/README.md) を参照。Indexer の結合テスト(`tests/integration/indexer/samples/`)とはファイルを共有せず、複製している(片方の変更が他方のテストを壊さないため)。追加するときは次のとおり。

1. `samples/` にファイルを置く。権限は 0644(ディレクトリは 0755)。検索に使える一意の語を本文に入れる
2. `samples/README.md` の表に、取り込まれるか・理由・検索用の語を書く
3. 取り込まれるファイルなら、`test_20_crawl.py` の `INDEXED_SAMPLES` と `MARKERS`、および件数の期待値(`enumerated_count`・`created_count` の 5、`(5, 5, 0)`)を更新する。取り込まれないファイルなら `IGNORED_SAMPLES`・`IGNORED_MARKERS` に足す
4. 大きなファイル(サイズ超過など)は、容量を避けて置かず、テストが実行時に生成する(`support.py` の `OVERSIZE_RAW_BYTES`)

日本語の PDF は抽出品質が未検証のため使っていない。

## ファイル構成

| パス | 内容 |
| --- | --- |
| `pyproject.toml` / `uv.lock` | テスト専用の依存(`pytest`・`httpx`。dev に `ruff`)。Crawler・Indexer の依存とは分けている。`uv.lock` で固定している |
| `compose.test.yaml` | Crawler のテスト用の上書き(原本上限、ポーリング間隔、healthcheck の間隔)。`deploy/compose` には混ぜない。Indexer 用の `tests/integration/indexer/compose.test.yaml` とは別で、重ねない |
| `conftest.py` | フィクスチャと、起動済みのスタックへの疎通確認・メンテナンスフラグの残りの確認 |
| `support.py` | Crawler の API クライアント、OpenSearch の検証ヘルパ、`document_id` の独立実装(Crawler・Indexer のコードは import しない)、ジョブの完了待ち、検索対象ディレクトリ(`SourceDirectory`) |
| `test_*.py` | シナリオ別のテスト(上の表) |
| `samples/` | 固定のサンプル文書 |
| `data/` | 実行中の検索対象の文書(実行時に作られ、終了時に削除される。`.gitignore` 済み) |
| `results/` | スクリプトの実行ログ(`.gitignore` 済み) |
