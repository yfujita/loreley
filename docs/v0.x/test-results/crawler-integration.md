# Crawler 結合テスト(compose + 実 OpenSearch + 実 Indexer)の結果

| 項目 | 内容 |
| --- | --- |
| 状態 | **実施済み**(2026-11-16。13 件すべて成功。2026-11-18 の PR レビュー対応でテストを 1 件足し、最終版は 14 件成功。8 章。権限エラー・`skip` 記録・並行・運用系などは**未実施**。未実施・未確認の一覧は 6 章、項目別の判定は 4.3) |
| 作成日 | 2026-11-16 |
| 参照する設計書 | `docs/v0.x/system-design/crawler/crawler-architecture-v0.4.md`(3.1、4.5、5.1、6.4・6.5、7.5〜7.9、8.1、10、12)、`crawler-api-v0.4.md`(3.3、4.1、4.4.2、4.6、4.7)、`connector/connector-file-system-v0.3.md`、`docs/v0.x/system-design/indexer/indexer-architecture-v0.10.md`(9.6 の件数照合) |
| 関連 | `tests/integration/crawler/README.md`(実行・シナリオ一覧)、`deploy/compose/README.md`(起動)、`apps/crawler/README.md` 8 章(fake だけでは検証できないこと)、`docs/v0.x/test-results/indexer-integration.md`(9 章に Indexer の回帰確認を追記)、`agent_tasks/20261116_create_it_for_crawler/`(作業の経緯。レビューの指摘と対応は 0008・0009) |

## 1. 目的

Crawler(`apps/crawler`。FileSystem Connector のみ)を compose で起動し、実 OpenSearch・実 Indexer(別コンテナ。HTTP 直接通信。mock にしない)に対して、fake の単体テストでは確認できなかった挙動(`apps/crawler/README.md` 8 章)を実機で確認する。結果は設計書とは別にここへ記録する。シナリオの内容と実行方法は `tests/integration/crawler/README.md` を正とし、ここには複製しない。

## 2. 記録のルール

- 実際に実行・確認した結果だけを書く。推測や期待値を結果として書かない。
- 未実施の項目は「未実施」、実機で確認していない項目は「未確認」と書く。
- 再実行は、上書きせず新しい行・節として追記する。
- 設計書の内容は複製せず、参照だけにする。結果が設計の変更を要する場合は、「評価・発見事項」に書き、設計書側への反映はユーザーが判断する。

## 3. 環境と実行条件

| 項目 | 内容 |
| --- | --- |
| 実施日・実施者 | 2026-11-16。Claude Code。ユーザー指示のもとで実施 |
| 基準コミット | `6970478ececf57b1421c55dcc7f704fecf735c4a`。本タスクの変更は**未コミット**(コミット SHA での再現はできない) |
| ホスト | macOS(x86_64)。Docker 20.10.13(Docker Desktop)。Docker VM のメモリ約 3.84GiB(4125892608 バイト)・CPU 2 |
| docker compose / uv | compose v2.3.3(`up --wait` は戻らないため使っていない。Indexer の結果記録 5 章の発見事項 1)、uv 0.13.8 |
| OpenSearch | `opensearchproject/opensearch:3.9.0`(compose の既定。`OPENSEARCH_VERSION` 未指定)。単一ノード、セキュリティプラグイン無効、ヒープ 512m。ダイジェストは今回確認していない。**`indexer-integration.md` の 1〜7 章(2.19.7)とは別の版**(8 章は 3.9.0) |
| Crawler / Indexer | `apps/crawler`・`apps/indexer` の Dockerfile からビルドしたイメージ。`apps/crawler` は本タスクで**変更していない**。Indexer の要約は無効 |
| スキーマ | `infra/opensearch/schema/{search-index,deletions,jobs,sources}.json`(`opensearch-init` が作成)。`jobs.json` を拡張し、`sources.json` を新設した(`loreley-sources` は `dynamic: strict`) |
| compose の構成 | `deploy/compose/compose.yaml` に `crawler` サービスを追加。**ホストには公開しない**(2026-11-18 の PR レビュー対応で、`127.0.0.1:8001` の publish を `compose.test.yaml` へ移した。8 章)。`stop_grace_period: 30s`、検索対象ディレクトリを `:ro` で `/data/documents` に mount、Indexer の上限 6 項目と `loreley-jobs` の索引名を Indexer・Crawler に同じ変数で渡す |
| テスト用の設定 | `tests/integration/crawler/compose.test.yaml`: Crawler を `127.0.0.1:8001` に publish(2026-11-18 から)、Indexer・Crawler とも `MAX_RAW_BYTES=65536`(Crawler が検査に使う Indexer の値も同じ)、Indexer の `DELETION_POLL_INTERVAL_SECONDS=1`、Crawler の `POLLING_INTERVAL_SECONDS=2`・`POLLING_TIMEOUT_SECONDS=120`・`RUNNER_SCAN_INTERVAL_SECONDS=1`、`crawler` の healthcheck の `interval: 3s`・`start_period: 180s`(`test` はイメージのものを継承) |
| 実行方法 | `scripts/run-crawler-integration-test.sh`(`-p loreley-it`。`up -d --build opensearch opensearch-init indexer crawler` + 自前ポーリング → pytest → `down -v --remove-orphans` と `tests/integration/crawler/data` の削除)。手動起動も併用した |
| pytest の起動 | uv 経由の既定起動(`uv run --project tests/integration/crawler pytest tests/integration/crawler -v`)。CPython 3.13.4、pytest 9.2.0、httpx 0.28.1(`uv.lock` で固定した 15 パッケージ) |
| 起動所要時間・メモリ | 起動の所要時間とメモリ使用量は**測定していない**。OpenSearch + Indexer + Crawler を約 3.84GiB の VM で同時に起動して全実行が成功し、メモリ起因の失敗は記録されていない |

## 4. 結果

### 4.1 起動確認(compose。手動起動)

`CRAWLER_DOCUMENTS_DIR=$PWD/tests/integration/crawler/data` で、`compose.yaml` + `compose.test.yaml` を `up -d --build`(`--wait` なし)して確認した。

| 項目 | 結果 |
| --- | --- |
| Crawler イメージのビルド・起動 | 成功。`startup recovery finished: failed_jobs=0 deleted_locks=0 kept_locks=0`、`owner=crawler-1` |
| healthy | `crawler`・`indexer`・`opensearch` が healthy、`opensearch-init` が Exited(0)。`GET /healthz` は 200 |
| healthcheck の `test` の継承 | **保持されている**。`docker inspect` で、イメージの `test` に `compose.test.yaml` の `Interval=3s`・`StartPeriod=180s` が重なっていることを確認した(compose への `test` の明示は不要) |
| 起動ログの警告 | なし(「Indexer の上限が未設定」を含め 0 件) |
| 公開ポート | 9200・8000・8001 のすべてが `127.0.0.1` のみ |
| マッピング | `loreley-sources` は `dynamic: strict`(9 項目)、`loreley-jobs` は `dynamic: false`(既存 4 項目 + 拡張項目) |
| init の冪等性 | 再実行で全て `skip`(alias・3 索引) |
| 手動のスモーク | `POST /sources` が 201、`POST .../crawl-jobs` が 202 → 約 3 秒で `succeeded`(`enumerated_count=2`、`created_count=2`)、検索インデックスに 2 件 |

### 4.2 シナリオ別の結果(13 テスト)

最終のテストコード・スクリプトでの実行(`data/` の削除条件・`chmod 755`・`describe_port_owner` などの修正を入れた版。基準コミット `6970478`、変更は未コミット): **`scripts/run-crawler-integration-test.sh` をクリーンな状態から 2 回連続で実行し、どちらも全件成功した**。

| 回 | 結果 | ログ(`.gitignore` 済み) |
| --- | --- | --- |
| 1 回目 | **13 passed in 44.54s**、終了コード 0 | `tests/integration/crawler/results/pytest-20261116-165128.log` |
| 2 回目 | **13 passed in 43.88s**、終了コード 0 | `tests/integration/crawler/results/pytest-20261116-165404.log` |

どちらも終了後、`loreley-it` のコンテナの残りはなく(`ps -a` が空)、`tests/integration/crawler/data` も残らなかった。この最終版の 2 回では、失敗・不安定なテストはなかった。この 2 回は、毎回 `down -v` 済みのクリーンなスタックで実行しているため、テスト間・実行間で干渉がないことの根拠にはならない。干渉がなかった根拠は、同じスタックでの 2 回連続の実行(下の表の 1 行目。`source_id` はテストごとに一意)に限る。

途中の実行(参考。コードは最終版の一つ前以前):

| 実行 | 結果 |
| --- | --- |
| 同じスタックで 2 回(手動起動) | 13 passed(47.49s / 41.61s)。このほか、テストの誤りを直す前に 1 件失敗した実行があった(ログは保存していない。実施者の報告による)。原因はテストの誤り(`fetch_document()` の戻り値から `["_source"]` を引いていた)で、テストを修正した。Crawler の不具合ではない |
| クリーンなスタックを手動起動 → healthy 待ち → pytest | 13 passed(53.48s)、終了コード 0 |
| スクリプト(`data/` の削除条件・`chmod 755`・`describe_port_owner` の修正前の版)。別々に 2 回 | 13 passed(47.72s / 38.09s)、終了コード 0 |

`tests/integration/crawler/results/` には、スクリプト実行のログが 5 件ある。最終の 2 件は上の表のとおり。残る 3 件は途中の実行のログで、`pytest-20261116-163345.log`(47.72s)・`pytest-20261116-163851.log`(38.09s)は、上の表の「スクリプト(修正前の版)」に当たる(ファイルの更新時刻と所要時間の一致による対応づけ)。`pytest-20261116-164835.log`(13 passed in 48.11s)は、実行の経緯を示す記録がなく、経緯は未確認(更新時刻 16:48 から、修正後・最終の 2 回の前の実行と推定)。

| ID | シナリオ | 結果 | 備考(実測値) |
| --- | --- | --- | --- |
| CIT-01 | Crawler が healthy(起動時の回復を終えて `/healthz` が 200 `{"status":"ok"}`) | passed | |
| CIT-01 | 4 索引(検索インデックスはエイリアス `loreley-documents`、`loreley-deletions`、`loreley-jobs`、`loreley-sources`)が存在 | passed | |
| CIT-01 | `loreley-sources` が `dynamic: strict` で 9 項目の型が定義され(`connector_config` は索引しない object)、`loreley-jobs` が `dynamic: false` で、Crawler が絞り込み・並べ替えに使う主要項目(`record_type`・`source_id`・`job_type`・`status`・`document_id`・`queued_at`)と Indexer の 4 項目(`owner`・`job_id`・`lease_expires_at`・`enabled`)の型を定義 | passed | `ratio_threshold` は double。`loreley-jobs` の上記以外の項目(`trigger`・`last_job_id`・`started_at` などの date 項目、索引しない object 項目)は、アサートしていない |
| CIT-10 | `POST /sources` が 201、再送が 200、`loreley-sources` に保存 | passed | strict マッピングが書き込み 9 項目を受け入れた。`connector_type` は `file_system` |
| CIT-10 | 未知の `connector_config` 項目は 400 `config_invalid`、保存されない | passed | 当初案の `invalid_request` は誤り(5 章の 2) |
| CIT-10 | 未登録のソースへのクロール起動は 404 `source_config_not_found`、ジョブ記録・ロックなし | passed | |
| CIT-20 | 主要フロー: txt/md/html/pdf + サブディレクトリの 5 件を索引。対象外(`.csv`・隠しファイル)は索引されない | passed | ジョブ `succeeded`・`confirmation=confirmed`、`registration` は `enumerated_count=5`・`created_count=5`・他 0。`document_id` の集合がテスト側の独立実装(SHA-256)と一致。件数照合 `enumerated_count == n_seen + e_missing`(5 == 5 + 0)、`deleted`、`target_count=0`。ジョブの `warnings` なし |
| CIT-21 | Crawler 側の原本サイズ超過(70,000 バイト > `MAX_RAW_BYTES` 65,536) | passed | ジョブ `succeeded`(`oversize_count=1`)。`oversize-*` 記録(`detected_by=crawler`)、`finish_notice` の `oversize_document_ids` に載り、索引に入らない。件数照合 2 == 1 + 1、`deleted` |
| CIT-22 | 実行中のロック `lock-{source_id}` の実体と、終了後の解放 | passed | `owner=crawler-1`、`job_id` が一致、`lease_expires_at` が未来(1 時間以内)。観測の窓は約 3.3 秒(0.2 秒間隔で約 16 回)。クロール 1 回は 3〜5 秒。終了後にロック文書が消える |
| CIT-23 | (当初案にない追加)ファイルを消して再クロールすると、サイズ超過記録が整理される | passed | 5 章の 4 |
| CIT-30 | 2 回目のクロールでの TTL 削除 | passed | クロール B: `deleted`、`enumerated_count=4`・`n_seen=4`・`e_missing=0`、`target_count=2`・`denominator=6`・`deleted_count=2`。残る 4 件(kept1・kept2・kept3・new1)の `last_seen_at` は 1 時間以内。kept2 は新しい本文で命中。`ttl`・`ratio_threshold`・`min_delete_count` = 600・0.5・0 が削除結果に載る。B の `registration` は `created=1`・`updated=1`。他ソースの文書は残る |
| CIT-40 | ソース削除ジョブ(順 0〜6) | passed | `succeeded`。対象の文書・`loreley-deletions` の記録・`oversize` 記録・設定・ロックが消え、他ソースは文書 2 件・記録・設定が残る。削除後のクロール起動は 404 `source_config_not_found`。DELETE のボディの `lock` が実 Indexer に受理された |
| CIT-50 | メンテナンスフラグ | passed | フラグ(`{"record_type":"maintenance","enabled":true}`)で `crawl-jobs` が 409 `maintenance_enabled`、ジョブ記録・ロックなし。削除後は 202 で `succeeded`。フラグは `finally` で削除 |

テストが確認していないこと(5 章・6 章を参照): `skip` 記録・`partially_succeeded`・権限エラー、ソース削除時のメンテナンス、並行動作、運用系(起動時の回復・`docker stop`・ロック解放 API・取り消し API)など。

### 4.3 `apps/crawler/README.md` 8 章の項目との対応

実在する 8 章の項目ごとに、この結合テストで何が分かったか。**この表が項目別の判定の正本**(6 章は未実施・未確認の一覧)。用語は `apps/crawler/README.md` 8 章と同じで、**「未実施」=テストを作っていない、「未確認」=実機で見ていない**(一部確認の項目の、見ていない部分にも使う)。「確認」はテストの成功で確認したもの、「一部確認」は一部だけ確認したもの。

| 8 章の項目 | 結果 | 根拠・備考 |
| --- | --- | --- |
| **実 OpenSearch** `create`・`if_seq_no` の並行時の原子性 | **未実施** | 通常経路(ロックの取得・解放、ジョブ記録の更新、設定の登録 201・再送 200)は動いた。並行時の原子性のテストはない |
| opensearch-py のスレッド安全性(CM-U-1) | **未実施** | 専用の確認はしていない。クロール中は Job Runner・HTTP ハンドラ・ハートビートが同時に動くが、結合テストの実行で Crawler・Indexer のログに警告・エラーはなかった(スレッド安全性の確認とはみなさない) |
| 10,001 件以上の全件走査(PIT + `search_after`)・バルク削除の部分失敗・PIT 期限切れの応答形 | **未実施** | 小規模の走査(CIT-20・21 の整理は空、CIT-23 は記録 1 件を削除、CIT-40 の順 3)は OpenSearch 3.9.0 で成功した。コードが渡す `allow_partial_pit_creation=false`・`allow_partial_search_results=false`(`scan.py`)が受理されたことは、これらの成功からの読み取り(専用のアサートはない)。10,001 件超・部分失敗・PIT 期限切れの応答形・refresh の可視性は未実施(実機で見ていない) |
| date 型のソート・絞り込み、マッピング案(arch 3.1)との整合 | **一部確認** | マッピング(`jobs.json`・`sources.json`)の型は CIT-01 で確認。`queued` のジョブを Job Runner が検出して実行する経路(`queued_at` 昇順)が動いた。降順ソート(直近のクロールの取得)と、受付途中のロックの判定は、専用のテストがなく未実施 |
| fake の限界(`document_id` を持たない同種の記録が 2 件以上のときの `non_unique_sort`) | **未実施** | |
| **実 Indexer** Status API の項目(`finish_received_at`・`waiting_for`)、終了通知の 409、ポーリング間隔 5 秒・タイムアウト 30 分の妥当性 | **一部確認** | Status のポーリングで削除結果が終端になり `confirmation=confirmed` になる通常経路は動いた。`waiting_for` の出方、終了通知の 409、既定の 5 秒・30 分の妥当性は未確認(専用のテストを作っていない。テストは 2 秒・120 秒に短縮している) |
| バッチ登録の応答の `document_id` の照合(CM-U-3) | **確認** | CIT-20・30。Crawler が `document_id_mismatch` で失敗せず、索引の `document_id` がテスト側の独立実装と一致。ただし ASCII のパスだけ(NFC・`\` などの特殊な名前は未実施) |
| `FakeIndexerClient` の `delete_*` が `lock` を検証しない | **一部確認** | CIT-40: 実 Indexer が DELETE のボディの `lock` を受理した。所有していない `lock` が拒否される側(`lock_not_owned`)は、Crawler の結合テストにはない(Indexer 側は Indexer の IT-15・IT-41。ソース削除 3(IT-42)の不所有ロック拒否は Indexer の IT にもない) |
| 件数照合の独立検証(`enumerated_count` と Indexer の `n_seen + e_missing`) | **確認** | CIT-20(5 == 5 + 0)、CIT-21(2 == 1 + 1)、CIT-30(4 == 4 + 0)。`validation_failed` にならなかった |
| 起動時の整合性検査の統合部分(arch 12 章 #39) | **未実施** | Indexer の上限を超える値で起動が失敗する側と、上限ちょうどの値での通過(バッチ登録・`last-seen` が 400 にならないこと)のテストはない。compose の既定の値で、警告なしに起動できたことだけ(4.1) |
| **実機の FileSystem** NFS/SMB・bind mount の errno・マウント外れ、`st_ino` の信頼性、取得中の変更の検出 | **未実施** | 実 NFS/SMB は対象外。Docker Desktop(macOS)の bind mount の `:ro` 越しの列挙・取得(サブディレクトリ、隠しファイルの除外、`.csv` の対象外)は確認した。マウントの可視性の遅れは観測されなかった(ホストで書いた直後の `docker exec ls` で 10 回すべて即時。削除も即時) |
| ブロッキング I/O 中のスレッド挙動(CFS-U-4)、GIL を長く保持する処理の間のハートビート | **未実施** | 結合テストを作っていない。ハートビートが進み続けるかは、macOS・Linux コンテナ・NFS/SMB のいずれでも未確認 |
| 実運用イメージの FS エンコーディング、`:ro` マウントの実機での動作 | **一部確認** | `:ro` の bind mount で、uid 10001 がホストの 0644 / 0755 のファイルを読めた(Docker Desktop・macOS)。非 ASCII のファイル名は未実施 |
| **実コンテナ・実 compose** 実行中のジョブがある状態での `docker stop`(所要時間、SIGKILL 時) | **未実施** | `stop_grace_period: 30s` を設定しただけで、所要時間は測っていない |
| `/healthz` が `healthy` になること | **確認** | 実 OpenSearch・実 Indexer に接続して回復を終え、イメージの HEALTHCHECK が `healthy` になった(4.1)。スクリプトの起動待機(`crawler:healthy`)も 2 回通った |

テストの成功から読み取れること(専用のアサートはない): Crawler が書いたロック文書の形式(`owner`・`job_id`・`lease_expires_at`)を、実 Indexer が所有確認に使えた(登録が `lock_not_owned` にならずに成功した)。CIT-50 は、運用者が手動で書くメンテナンスフラグを Crawler が読めることを確認したが、Indexer がそのフラグを読んで書き込みを止める経路は、Crawler の結合テストでは確認していない。

### 4.4 実行スクリプト(`scripts/run-crawler-integration-test.sh`)の確認

実機で確認した。失敗経路(待機超過・ポート占有)は、`data/` の削除条件・`chmod 755`・`describe_port_owner` の表示などを直す前の版と、直した後の最終版の両方で確認した。

| 項目 | 結果 |
| --- | --- |
| 成功経路 | 4.2 のとおり。終了後に `ps -a` が空、`data/` なし |
| 手順書(手動)の実行 | `tests/integration/crawler/README.md` の「手動で実行する」手順 1〜5 を、書かれたとおりに実行: 13 passed in 37.94s、終了コード 0、`ps -a` 空、`data/`・`deploy/compose/documents` なし |
| 待機の上限超過(`LORELEY_IT_WAIT_TIMEOUT_SECS=1`) | 終了コード 10。`ps -a` とログ末尾を出力して `down -v`、後始末済み(`ps -a` 空、`data/` なし)。修正前の版(2 回の実行)と**最終版(1 回)**の両方で確認 |
| ポート占有(8001 を一時的に塞ぐ) | 終了コード 1。占有者を `lsof` で表示し、スタックは起動しない。塞いだ `http.server` は自分で停止し、8001 が空いたことを確認。修正前の版と**最終版**の両方で確認(最終版では `lsof` の結果と「使用中のプロセスを利用者自身の判断で止めてから再実行する」旨のメッセージを確認。`ps -a` 空、`data/` なし) |
| `bash -n` | 通過。`shellcheck` は未導入のため**未実施** |
| `ruff check`・`ruff format --check`(`tests/integration/crawler`)、`uv lock --check` | 通過(`ruff format` は 10 files already formatted、ロックは 15 パッケージ) |

実機で動かしていない経路(最終版でも): 残骸検出 `check_no_leftover_stack` の失敗経路(成功経路で空振りしないことのみ確認)、コンテナがポートを占有している場合の `describe_port_owner`、`compose down` 失敗時の分岐(`data/` を消さず手動削除を案内)、シグナル(INT・TERM)、`--keep`。

### 4.5 Indexer の結合テストの回帰確認

スキーマ(`jobs.json` の拡張、`sources.json`)・compose(`crawler` の追加、`indexer` と `opensearch-init` への変数追加)・Indexer 用スクリプト(`up` のサービス名の明示)を変えたあとも、Indexer の結合テスト 40 件が成功した。変更前 40 passed(19.47s)、compose・スキーマの変更直後 40 passed(23.41s)、最終コードの後 **40 passed(37.69s)**、終了コード 0。詳細は `indexer-integration.md` の 9 章。

## 5. 評価・発見事項

1. **`connector_type` の値は `file_system`**(`filesystem` は 400 `unsupported`)。`apps/crawler/src/loreley_crawler/connectors/registry.py` の定数。
2. **未知の `connector_config` 項目は 400 `config_invalid`**。当初のシナリオ案(`agent_tasks/20261116_create_it_for_crawler/0002-work-plan.md`。以下「当初案」)の CIT-10 は `invalid_request` と書いたが誤りで、訂正する。crawler-api 3.3 とコードはどちらも `config_invalid` で、設計とコードは一致している。テストは設計に従った。
3. **設計書 arch 10 章との差(ユーザーの承認済みの前提。設計書は改版していない。反映はユーザー判断)**:
   - arch 10 章は「ポートは内部ネットワークだけで、ホストに公開しない」。**当初は** `compose.yaml` が Crawler を `127.0.0.1:8001` に publish していたが、PR レビュー(認証なしの API で、`connector_config.root` からコンテナ内の任意のパスを読めうる)を受けて、**2026-11-18 に設計書どおり(公開しない)に戻した**。結合テストの pytest のために必要な publish は、`tests/integration/crawler/compose.test.yaml` だけが行う(8 章)。
   - arch 10 章の「限界」の段落は「既定の compose は Indexer に上限の変数を渡していない」と書く。この compose は、Indexer の上限 6 項目(`INDEXER_MAX_RAW_BYTES` など。既定値は Indexer のコードの既定値と同じ)と `loreley-jobs` の索引名を、Indexer・Crawler の両方に同じ変数で渡す。起動時の整合性検査が素通りしないため。
   - arch 10 章の「現在の compose は OpenSearch と Indexer だけ」は、`crawler` の追加で現状と合わない。`opensearch-init` 側の変数名(arch は「名前は実装時」)は `SOURCES_INDEX_NAME`、`.env` では `LORELEY_SOURCES_INDEX_NAME` とした。
4. **当初案にない追加テスト CIT-23**(`test_oversize_record_is_purged_when_the_file_is_removed`。arch 6.4 の (b)「列挙されなかった文書の記録を消す」)。CIT-20 では、クロール終了後の整理が空の走査になり、実 OpenSearch での記録の削除を確認できないため、記録がある状態の確認を足した。新機能ではなく、既存シナリオの確認を実効的にする目的。arch 6.4 の (a)(今回列挙され、その種類の結果にならなかった文書の記録の削除。ファイルを上書きして小さくした場合など)の変種は、要件外のため作っていない。
5. **Loreley のテスト用 OpenSearch に、Fess のものとみられる索引・文書が現れた**(手動起動で確認)。索引 `fess_config.coordinator` に、`instanceId=127.0.0.1:93982`・type=heartbeat の文書があった。**索引名から Fess が書き込んだと推定**しており、書き込んだプロセスの特定(接続元の確認)は**未確認**。テストの準備の確認で、別プロジェクトの `fess-opensearch` コンテナがポート 9200 を使っていたが、ユーザーの回答を受けて停止された(または削除された。私たち(Claude Code)は停止の操作をしていない)。その後、同じポートで Loreley のテスト用 OpenSearch が起動したので、ホスト上の Fess が 9200 に接続し続けて書き込んだ可能性がある(これも推定)。`loreley-*` 索引には影響しなかった(Indexer の IT 40 件・Crawler のスモークとも成功)。この索引はテスト終了時の `down -v` で消える。私たちは Fess のプロセスにも `fess-opensearch` にも触れていない。**ホスト側ポートが 9200 に固定**のままだと、Fess 稼働中は同様の混入が起こり得ると考えられる(ポートを変えるとテストの接続先も変える必要がある。`tests/integration/crawler/README.md` のポート)。停止された `fess-opensearch` の再起動の要否は、ユーザー判断。
6. **Crawler の不具合は見つからなかった**。設計との食い違いは、上の 3(compose の構成に関する承認済みの差)だけで、2 は設計とコードが一致している(当初案の誤り)。`apps/crawler` は変更していない。結合テストの実行で、Crawler・Indexer のログに警告・エラーはなく、ジョブ記録に `warnings` はなかった。
7. **実機で確認できたこと(設計どおり)**: 件数照合(5 == 5 + 0、2 == 1 + 1、4 == 4 + 0)、原本サイズ超過が `partially_succeeded` にならず件数照合に載ること、TTL 削除で Crawler の `last-seen`・登録が文書を守ること(CIT-30。更新されなかった 2 件だけが `deleted_count=2`)、ソース削除の順 0〜6 が他のソースに及ばないこと、運用者が手動で書くメンテナンスフラグ(`maintenance` 文書、`enabled: true`)を Crawler が読んで 409 にすること(`enabled` が `false` 以外のときの扱い(fail-closed)は、コードの確認のみで、このテストでは `true` と文書なしだけを確認した)。
8. **OpenSearch のバージョン**: compose の既定は 3.9.0 で、本記録の実測はすべて 3.9.0。`indexer-integration.md` の 1〜7 章が 2.19.7 なのは、タスク `20261113_upgrade_opensearch`(2026-11-13)で既定を 2.19.7 から 3.9.0 に更新したため(Indexer の結合テストの 3.9.0 での再実行は同 8 章)。
9. **healthcheck の部分上書き**: `compose.test.yaml` で `interval` と `start_period` だけを上書きしても、イメージの `test` は保持された(compose v2.3.3。4.1)。
10. **`loreley-sources` の `dynamic` は `strict` に決めた**: arch 3.1 は、`dynamic` の設定(`strict` にするか)を案のまま、`opensearch-init` の実装時に決めるとしていた(CA-P-49)。本タスクで `strict` に決めて `sources.json` に実装し、結合テストで Crawler の書き込み(9 項目)が受理されることを確認した(4.1・CIT-10)。設計書への反映はユーザー判断。

## 6. 未実施・未確認

**項目別の判定の正本は 4.3(`apps/crawler/README.md` 8 章の項目との対応)。この章は、未実施・未確認の一覧**。用語は 4.3 と同じで、「未実施」=テストを作っていない、「未確認」=実機で見ていない。通常経路が動いた「一部確認」の項目は、見ていない部分だけを挙げる。

### 未実施(テストを作っていない)

- 権限エラー: `fetch_permission_denied` / `skip` 記録 / `partially_succeeded`(ホスト権限で不安定になりうるため、サイズ超過で代替した)。ソース削除の順 3 での `skip` 記録の削除(`oversize` 記録の削除は CIT-40 で確認)
- ソース削除ジョブの起動時のメンテナンス 409(`apps/crawler/README.md` 6 章に記載はあるが未検証)
- メンテナンスフラグ
  - `enabled: false` で下ろす手順(削除で下ろすことは CIT-50 で確認)
  - `enabled` が `false` 以外(`"false"`・`0`・`null`・欠落など)のときの fail-closed(コードの確認のみ。CIT-50 は `true` と文書なしだけ)
  - Indexer がフラグを読んで書き込みを止める経路(Crawler の結合テストの範囲外)
- 実 OpenSearch
  - `create` と `if_seq_no` の並行時の原子性、スレッド安全性の実機確認
  - 10,001 件超の全件走査(PIT + `search_after`)、refresh の可視性、バルク削除の部分失敗、PIT 期限切れの応答形(arch 12 章 #37)
  - 降順ソート(直近のクロールの取得)、受付途中のロックの判定
  - `document_id` を持たない同種の記録が 2 件以上あるときの `non_unique_sort`
  - 既存の `loreley-jobs` への拡張の反映(put mapping・ボリュームの作り直し。`apps/crawler/README.md` 9 章)
- 実 Indexer
  - Status API の `waiting_for` の出方、終了通知の 409、既定のポーリング間隔 5 秒・タイムアウト 30 分の妥当性(テストは 2 秒・120 秒に短縮)
  - 所有していない `lock` が拒否される側(`lock_not_owned`。Indexer 側は Indexer の IT-15・IT-41。ソース削除 3(IT-42)の不所有ロック拒否は Indexer の IT にもない)
  - 非 ASCII・NFC・`\` を含むファイル名での `document_id` の一致(確認したのは ASCII のパスだけ)
- 起動時の整合性検査(arch 12 章 #39): Indexer の上限を超える値で起動が失敗する側と、上限ちょうどの値での通過・バッチ登録と `last-seen` が 400 にならないこと。実行したのは compose の既定の値での起動(警告なし。4.1)だけ
- 実機のファイルシステム: 実 NFS/SMB、errno・マウント外れの症状、`st_ino` の信頼性、取得中の変更の検出、ブロッキング I/O 中のスレッド挙動(CFS-U-4)・GIL を長く保持する処理の間のハートビート、非 ASCII のファイル名(実運用イメージの FS エンコーディング)
- 実コンテナ: `docker stop` の所要時間(`stop_grace_period` の妥当性)と SIGKILL 時の挙動
- 起動時の回復(`running` → `failed(crawler_restart)`、孤児ロックの削除)。起動ログは `failed_jobs=0 deleted_locks=0` の空の回復のみ
- ロック解放 API・取り消し API・定期起動(Scheduler)
- Web Connector

### 未確認(実機で見ていない)

- スクリプトの `check_no_leftover_stack` の失敗経路、コンテナがポートを占有している場合の `describe_port_owner`、`compose down` 失敗時の分岐
- スクリプトのシグナル(INT・TERM)・`--keep`(4.4)
- `shellcheck`(未導入)
- Linux ホスト(`vm.max_map_count`、SELinux の bind mount、uid のマッピング)、他の OS、OpenSearch 3.9.0 以外のバージョン
- マウントの可視性の遅れ(Docker Desktop(macOS)では観測されなかった。Linux などは未確認)
- 起動所要時間・メモリ使用量の測定

### 不確実点(テストが依存している前提)

- **ロック観測が約 3.3 秒の窓に依存**している(`POLLING_INTERVAL_SECONDS=2`)。極端に速い環境では観測できず CIT-22 が失敗しうる(失敗メッセージで原因は分かる)。
- **`lease_expires_at` の判定がホストと Docker VM の時計に依存**している(リースが未来、`last_seen_at` が 1 時間以内)。許容幅は広いが、時計が大きくずれた環境では誤って失敗しうる。
- **TTL の前提作りが Indexer 内部の項目名 `last_seen_at` に依存**している(`force_last_seen_at` で OpenSearch へ直接書く。Indexer の IT と同じ前例)。項目名が変わると、Indexer の IT とともに壊れて検出できる。

### 負債

- Indexer 用・Crawler 用の実行スクリプト(`scripts/run-indexer-integration-test.sh`・`run-crawler-integration-test.sh`)が重複している。3 つ目のモジュールで共通化する。
- CI への組み込みは対象外。
- 変更のコミット後に、実施時点のコミット SHA を 3 章に追記する。

## 7. 再実行の手順

`tests/integration/crawler/README.md` を参照。最小のコマンド:

```sh
scripts/run-crawler-integration-test.sh   # compose 起動 → pytest → 後始末まで一括(uv が必要)
```

Indexer の結合テストと同じプロジェクト名(`loreley-it`)・ポート(9200・8000)を使うため、**同時には実行できない**。

## 8. PR #3 のレビュー指摘への対応(2026-11-18)

PR #3 のレビューの指摘 1〜3 に対応した(指摘 4 のインデックス名の固定は対象外)。

| 指摘 | 対応 | 確認 |
| --- | --- | --- |
| 1. Crawler API の公開で、コンテナ内の任意のファイルを読ませうる | `compose.yaml` の `crawler` から `ports` を外し(設計書 arch 10 章どおり)、`compose.test.yaml` だけが `127.0.0.1:8001` に publish する | `docker compose config` で、`compose.yaml` 単体は 8000・9200 だけ、`compose.test.yaml` を重ねると crawler の 8001(`host_ip: 127.0.0.1`)が出ることを確認(レビュアーも確認) |
| 2. 既存の `loreley-jobs` では Job Runner がジョブを検索できない | `init-indices.sh` に `extend_mapping` を追加し、起動のたびに `jobs.json` の不足項目を `PUT _mapping` で足す | 旧 `jobs.json`(4 項目)の索引で、修正前は `status` 検索が 0 件、修正後は 1 件。再実行は同じ結果。型の衝突は HTTP 400 で init が失敗。結合テスト `test_init_adds_the_missing_fields_to_an_existing_jobs_index` を追加 |
| 3. スクリプトが既存のボリュームと `data/` を消しうる | 事前確認に `check_no_leftover_data` を追加。`loreley-it` のボリュームの残りと、空でない `data/` を検出したら、何も消さず終了コード 1 で中止する | ボリュームだけ残した状態と、`data/` に利用者のファイルを置いた状態で中止し、どちらも消えないことを確認 |

最終のテスト: `scripts/run-crawler-integration-test.sh` が **14 passed in 37.66s**、終了コード 0、後始末の後にコンテナ・ボリューム・`data/` なし。Indexer の結合テスト(同じ init を使う)の回帰: **40 passed in 21.30s**。

- 未対応: Indexer 用スクリプト(`run-indexer-integration-test.sh`)は同じプロジェクト名・ボリュームで `down -v` するが、残骸検出は入れていない(今回は Crawler 用のみ。スクリプトの重複の負債と同じ扱い)。
- 未対応: Connector が許可するルートディレクトリを制限する仕組み(将来の課題)。
- 未確認: Linux ホスト、`shellcheck`(未導入)。

## 9. 実行スクリプトの安全性の統一と排他ロック(再実行の記録。2026-11-26)

タスク `20261125_harden_it_run_scripts` で、Crawler・Indexer・api の実行スクリプト 3 本を、同じ安全性の方針に揃え、共通の排他ロックで同時実行を拒否するようにした。そのうえで Crawler の結合テストを再実行した。1〜8 章の結果は、履歴としてそのまま残す。

変更した資材(いずれも**未コミット**。基準コミットは `96a9b52`):

- `scripts/lib/it-common.sh`(新規): 3 本の実行スクリプトの共通処理(排他ロック・事前確認・起動と待機・後始末)。6 章の「負債」(8 章でも言及)としていた「スクリプトの重複」を解消した
- `scripts/run-crawler-integration-test.sh`: 共通ファイルへ移行。テストの接続先 URL(`LORELEY_IT_{OPENSEARCH,INDEXER,CRAWLER}_URL`)の固定、`docker ps -a` が失敗したときの中止、`data/` の存在確認と一覧取得の分離、後始末に失敗したときの終了コード 11、排他ロックの追加
- `scripts/run-indexer-integration-test.sh`・`scripts/run-api-integration-test.sh`: 同じく共通ファイルへ移行(Indexer には 8 章で未対応としていた残骸検出を追加。詳細は [indexer-integration.md](indexer-integration.md) の 10 章)

| 項目 | 内容 |
| --- | --- |
| 実施日・実施者 | 2026-11-26。Claude Code(メインエージェント)。ユーザー指示のもとで実施 |
| 実施した時点のコード | 基準コミット `96a9b52` の作業ツリー(上の変更は未コミット) |
| ホスト・実行方法 | macOS。`caffeinate -i` を付け、`scripts/run-crawler-integration-test.sh` を実行した。環境(実行後に同じホストで確認): macOS 15.8.3(x86_64)・Docker 20.10.13・compose v2.3.3・uv 0.13.8 |

### 9.1 全件実行の結果

| 実行 | 結果 | ログ |
| --- | --- | --- |
| 正式な記録(同時実行の拒否の検証で 1 本目として実行) | **14 passed in 36.99s**、終了コード 0。実行後にコンテナ・ボリューム・`data/`・ロックなし。`skipped`・`deselected`・`xfailed`・`warnings` の行なし | `tests/integration/crawler/results/pytest-20261126-041916.log` |
| 検証手順の誤りで意図せず実行された回 | 14 passed in 37.90s、終了コード 0 | `pytest-20261126-040531.log` |

他プロジェクトのコンテナ・ボリューム(`opensearch-opensearch-1` など)は、各実行の前後で変化がなかった。

### 9.2 この IT に関わる検証

| 検証 | 結果 |
| --- | --- |
| 後始末の失敗(終了コード 11)と URL の固定 | `docker compose down` だけを失敗させる偽の `docker` と、`LORELEY_IT_{OPENSEARCH,INDEXER,CRAWLER,API}_URL=http://127.0.0.1:9999` を指定し、`-k test_01_startup` で実行。`4 passed, 10 deselected`、終了コード **11**。コンテナ・ボリューム・`data/` は残り、`data/` を削除しなかった旨(コンテナが残っている可能性があるため)を表示し、ロックは解除された。URL を 9999 にしても成功した(スクリプトが固定したため) |
| `--keep` | `--keep -k test_01_startup` で終了コード 0。ロックは解除され、スタックと `data/` が残った。片付ける前の再実行は「コンテナが残っています」で終了コード 1(中止)。表示された後始末のコマンドをそのまま実行して、コンテナ・ボリューム・`data/` がすべて消えた |
| 同時実行の拒否 | 1 本目に Crawler の全件を実行し、スタックの準備ができた後に、2 本目として Indexer・Crawler・api を順に起動した。3 本とも終了コード **1** で、保持者(`script=run-crawler-integration-test` と PID)を表示した。2 本目の前後で、コンテナ ID・ボリューム・各コンテナの `StartedAt` は不変で、`docker events` はヘルスチェックの `exec_*` の 5 行だけ(destroy・die・kill・stop・remove なし)。1 本目は終了コード 0 |
| 事前確認の中止(スタックは作らない) | 偽の `docker` で、`docker ps -a` の失敗・`docker volume ls` の失敗は終了コード 1(「docker ps に失敗しました」「docker volume ls に失敗しました」)。`data/` を `chmod 000` にすると終了コード 1(「内容を確認できませんでした」)で `data/` は残る。空でない `data/`(`canary.txt`)は終了コード 1 で canary が残る。ポート 9200・8000・8001 をそれぞれ占有すると、いずれも終了コード 1 で、`compose up` は呼ばれない。ポート占有以外は、終了後にロックが残らないことも確認した |
| 残ったロック | 偽の `docker`(`docker info` を待たせる)で起動して `kill -9`。ロックが残り、次の Crawler の実行は終了コード 1 で、保持者の PID(kill したものと一致)・開始時刻・スクリプト名、`ps -p`・`rm -rf` の手順を表示し、何も消さなかった。手動で `rm -rf` した後は、ロックを取って実行できた |
| `--help`・引数エラー | `--help` は終了コード 0 でロックを作らない。`LORELEY_IT_WAIT_TIMEOUT_SECS=abc`・`=0` は終了コード 1 でロックを作らない |
| 旧スクリプト(`96a9b52`)との比較 | 偽の `docker` を使い、通常・`--keep`・`down` の失敗・uv の失敗・`-k foo -x` で、旧・新の終了コードと docker・uv の呼び出しを比べた。終了コードは一致し、意図した差は `down` 失敗時の終了コード(旧 0 → 新 11)と、`LORELEY_IT_*_URL` 3 つの追加だけ |

### 9.3 静的検査と未実施

- `bash -n`(`/bin/bash` 3.2.57 でも): 4 ファイル(`scripts/lib/it-common.sh` と実行スクリプト 3 本)すべて OK
- **`shellcheck` は未実施**(ホストに無い。8 章の「未確認」のまま)
- ロックの解除に失敗したときに終了コード 11 になる経路は、`scripts/lib/it-common.sh` を `source` した関数レベルの確認(ロックの親ディレクトリを書き込み不可にして解除を失敗させた)だけで、スクリプトを通した実機の再現はしていない
- Linux ホストは未確認のまま
- Crawler の実スタックでの INT・TERM は行っていない(共通の関数は、Indexer の実スタックで TERM、偽の `docker` で INT・TERM を確認した)
- 既知のリスク: ロックの `mkdir` が成功してから `lock_acquired` を立てるまでの間にシグナルを受けると、ロックが残る(残った場合は手動で解除する)
