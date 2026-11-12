# Indexer 結合テスト(compose + 実 OpenSearch)の結果

| 項目 | 内容 |
| --- | --- |
| 状態 | **実施済み**(2026-11-12〜13。uv 経由の既定起動を含む。U-31 の一部と、5・6 章に書いた項目は未実施・未確認) |
| 作成日 | 2026-11-12 |
| 参照する設計書 | `docs/v0.x/system-design/indexer/indexer-api-v0.10.md`、`indexer-architecture-v0.10.md`(9.3、9.14、U-31)、`docs/v0.x/system-design/opensearch/schema/search-index-v0.10.md`、`loreley-deletions-v0.10.md` |
| 関連 | `deploy/compose/README.md`(起動)、`tests/integration/README.md`(実行・シナリオ一覧)、`agent_tasks/20261112_create_compose_and_indexer_test/`。U-31 の実機確認の結果は、`opensearch-performance.md`(性能測定・実機確認の雛形。未実施のまま)ではなく、**本書の 4.3** に記録した |

## 1. 目的

Indexer を、compose で起動した実 OpenSearch に接続して動かし、fake の単体テストでは確認できなかった挙動(`apps/indexer/README.md` 10 章、設計書 U-31 の一部)を実機で確認する。結果は設計書とは別にここへ記録する。シナリオの内容と実行方法は `tests/integration/README.md` を正とし、ここには複製しない。

## 2. 記録のルール

- 実際に実行・確認した結果だけを書く。推測や期待値を結果として書かない。
- 未実施の項目は「未実施」と書く。
- 再実行は、上書きせず新しい行・節として追記する。
- 設計書の内容は複製せず、参照だけにする。結果が設計の変更を要する場合は、「評価・発見事項」に書き、設計書側への反映はユーザーが判断する。

## 3. 環境と実行条件

| 項目 | 内容 |
| --- | --- |
| 実施日・実施者 | 2026-11-12(4.2 の ④⑤ と、`deploy/compose/README.md` の手動手順の確認は 2026-11-13)。Claude Code(メインエージェントと code-implementer)。ユーザー指示のもとで実施。uv はユーザーが導入した |
| ホスト | macOS(x86_64)。Docker 20.10.13(Docker Desktop)、メモリ約 3.8GiB・CPU 2 |
| docker compose | v2.3.3(`up --wait` が戻らないため使っていない。5 章の発見事項 1) |
| OpenSearch | `opensearchproject/opensearch:2.19.7`(ダイジェスト `sha256:3bfa1ec74d56928c2e018033d45c460ce2c0ea65a5cedd577de3102326c31b89`、build_hash `6dd9a042`、JDK 21.0.12.1)。単一ノード、セキュリティプラグイン無効、ヒープ最大 512MiB(`536870912` B) |
| Indexer | `apps/indexer` の Dockerfile からビルドしたイメージ(`loreley-it_indexer`)。実装開始時点のコミットは `c59fea7`、本タスクの変更は**未コミット**(コミット SHA での再現はできない)。要約は無効 |
| スキーマ | `infra/opensearch/schema/{search-index,deletions,jobs}.json`(`opensearch-init` が作成。`loreley-documents-000001` + エイリアス `loreley-documents`) |
| テスト用の Indexer 設定 | `tests/integration/compose.test.yaml`: `MAX_RAW_BYTES=65536`、`DELETION_BATCH_SIZE=2`、`SEARCH_AFTER_PAGE_SIZE=2`、`DELETION_POLL_INTERVAL_SECONDS=1` |
| 実行方法 | `scripts/run-indexer-integration-test.sh`(`-p loreley-it`。`up -d --build` + 自前ポーリング → pytest → `down -v --remove-orphans`)。ただし 4.2 の ①② は、実装担当がスクリプトを使わず手動で同じ手順(同じ compose ファイルでの起動、自前ポーリング、pytest、`down -v`)を行った。③ はスクリプト経由 |
| pytest の起動 | 4.2 の ①②③ は、**一時 venv(Python 3.13.4、pytest 9.2.0、httpx 0.28.1。実装担当が作成し、③ も同じ venv)で実行した**(その時点でホストに uv が無く、スクリプトでは `LORELEY_IT_PYTEST_CMD` で差し替えた)。**④⑤(2026-11-13)は uv 経由の既定起動**(`uv run --project tests/integration pytest tests/integration -v`。uv 0.13.8、CPython 3.13.4、pytest 9.2.0、`tests/integration/uv.lock` で固定した 15 パッケージ。`uv.lock` は同日に `uv lock` で生成した)。pytest の rootdir は `tests/integration`、configfile は `tests/integration/pyproject.toml` で、設定が読み込まれることを確認した |
| 起動所要時間(1 回の実測、目安) | クリーン状態から、イメージビルドを含む `up -d` が初回約 90 秒、その後 healthy まで約 20 秒(**実装担当の報告による。ログは保存していない**)。スクリプト全体(ビルドはキャッシュ済み)は約 2 分 20 秒(142 秒。メインエージェントの ③) |
| アイドル時のメモリ | OpenSearch 約 855MiB、Indexer 約 56MiB |

## 4. 結果

### 4.1 起動確認(compose)

| 項目 | 結果 |
| --- | --- |
| `opensearch`・`indexer` が healthy、`opensearch-init` が Exited(0) | 確認した |
| `_cluster/health` | green、ノード 1 |
| インデックスとエイリアス | `loreley-documents-000001`、`loreley-deletions`、`loreley-jobs` が green/open。`loreley-documents → loreley-documents-000001` |
| マッピングの `dynamic` | documents=`strict`、deletions=`strict`、jobs=`false` |
| Indexer の起動 | `unfinished deletion results were failed after the restart: count=0` → `the indexer is ready`。**実 OpenSearch への接続と起動時の整理(`loreley-deletions` の読み取り)まで完了**(`apps/indexer/README.md` 10 章で未確認だった点) |
| `/healthz` | 200 `{"status":"ok"}` |
| init の冪等性 | 再実行で全て skip。再インデックス模擬(`-000002` にエイリアスを付け替えて `-000001` を削除)後も `-000001` を作り直さない |
| Indexer の停止 | `stop` で 1 秒、終了コード 0(SIGTERM で `Shutting down` → `Application shutdown complete`)。OOMKilled なし |
| 公開ポート | `127.0.0.1:9200`(OpenSearch)、`127.0.0.1:8000`(Indexer)のみ。環境変数でホスト側ポートを変えても、スクリプトは 9200/8000 に固定して起動する(`OPENSEARCH_HOST_PORT=19200`・`INDEXER_HOST_PORT=18000` を設定して実行し、テストが通ることで確認した) |
| `deploy/compose/README.md` の手動手順(2026-11-13) | `deploy/compose` で、README の「起動・停止・初期化」のコマンドをそのまま実行した(`.env` なし、プロジェクト名は指定せず既定の `compose`)。`docker compose up -d --build` が 36 秒で戻り、`docker compose ps` で opensearch・indexer が healthy・opensearch-init が Exited (0) になった(開始から約 52 秒)。`curl http://127.0.0.1:9200/_cluster/health` は green、`curl http://127.0.0.1:8000/healthz` は `{"status":"ok"}`。`docker compose down -v` で、コンテナ・ボリューム・ネットワークの残りなし。イメージのビルド・取得はキャッシュ済みの状態 |

### 4.2 シナリオ別の結果(40 テスト)

最終のテストコードでの実行: ①実装担当がクリーン起動から 1 回(**40 passed in 30.49s**)、②同じスタックで再実行(**40 passed in 22.42s**)、③メインエージェントがスクリプトで 1 回(**40 passed in 33.64s**、終了コード 0。ログ `tests/integration/results/pytest-20261112-201837.log`)。**①② の件数・所要時間は実装担当の報告による(ログは保存していない。手動実行でスクリプトは経由していない)。③ はログで確認した**。**①②③ は一時 venv の pytest で実行した**。④⑤(2026-11-13、メインエージェント): **uv 経由の既定起動で、スクリプトを 2 回連続で実行**(クリーンな状態から、それぞれ `up -d --build` → 自前ポーリング → `uv run … pytest` → `down -v`)。**④ 40 passed in 13.40s(終了コード 0、スクリプト全体 70 秒。ログ `tests/integration/results/pytest-20261113-034228.log`)、⑤ 40 passed in 13.13s(終了コード 0、全体 61 秒。ログ `pytest-20261113-034340.log`)**。どちらも終了後に `loreley-it` のコンテナ・ボリューム・ネットワークの残りはなかった。④⑤ のコードは、①②③ と同じテストコード(その間にテスト・スクリプト・compose の変更はない)。失敗・不安定なテストはなかった。再実行しても一意 ID のため干渉しなかった。なお、ここに至る途中の版(36 テスト、R2 の指摘対応前)でも全件通過している(36 passed in 38.32s、実装担当による手動実行。スクリプト経由では 36 passed in 22.93s)。

| ID | シナリオ | 結果 | 備考(実測値) |
| --- | --- | --- | --- |
| IT-01 | 起動疎通・スキーマ | passed | |
| IT-02 | `document_id` のテスト側算出と Indexer との一致 | passed | NFD・バックスラッシュ・先頭 `/`・大文字小文字を含む |
| IT-10 | 形式別登録(txt/md/html/pdf) | passed | 日時はミリ秒精度 UTC に正規化され date 型に受理された |
| IT-11 | 抽出失敗(`extract_failed`) | passed | |
| IT-12 | 再登録 `unchanged` | passed | `_seq_no` が変化しない(全文書き込みなし) |
| IT-13 | 再登録 `updated` と `last_seen_at` の max 比較 | passed | `force_last_seen_at` による直接書き込みで前提を作成 |
| IT-14 | サイズ超過(`oversize`) | passed | |
| IT-15 | ロック不所有 | passed | 登録・`last-seen` で、別 owner・別 job_id・期限切れ・ロック文書なし |
| IT-20 | 開始通知 | passed | |
| IT-21 | `last-seen` の部分更新 | passed | `updated`・`unchanged`・`not_found` |
| IT-22 | 終了通知と Status | passed | |
| IT-30 | TTL 削除(`deleted`) | passed | A: `deleted`(`deleted_count=0`)。B: `enumerated_count=5`・`n_seen=4`・`e_missing=1`・`target_count=3`・`denominator=7`・`deleted_count=3` |
| IT-31 | TTL 削除の分割実行 | passed | `target_count=21`・`denominator=22`・`deleted_count=21`。`loreley-documents` の `query_total` 差分 13(`_count` 2 回 + `search_after` 11 ページ。4 回の実行で安定)。閾値は `>= 10` |
| IT-40 | ソース削除 1(`deletions:discard`) | passed | |
| IT-41 | ソース削除 2(`DELETE .../documents`) | passed | `refresh_interval=-1` 下で `deleted_count=3`、`scroll_total` 差分 1(`delete_by_query` が 1 回で完了) |
| IT-42 | ソース削除 3(`DELETE .../deletion-records`) | passed | 同一ソースに複数の `deletion_result` がある場合も全て削除 |

### 4.3 設計書 U-31 の実機確認

| U-31 の項目 | 対応 | 結果 |
| --- | --- | --- |
| (6) Update のスクリプト(params で値を渡す形) | IT-12・IT-21 | 実機で動作した |
| (7) 日時の `Instant` パース・比較、date 型との整合 | IT-10・IT-20・IT-21 | 正規化の結果と date 型での受理・range 検索を確認。ただし「`Instant` で比較しているか(文字列比較でないか)」までは、このテストでは判別できない(Indexer が固定幅 UTC・ミリ秒へ正規化してから比較するため、両者は同値) |
| (9) 404 の本文の形 | IT-21・IT-01・IT-22 | `update` の `document_missing_exception`(→ `not_found`)と `found:false` の 404 を確認。`index_not_found_exception` は、Status API の GET(`loreley-deletions` を削除した後)を**手動で再現して観測した**(5 章の発見事項 2。結合テストには含めていない)。`update` 系・書き込み系の `index_not_found_exception` の 404 本文、`result:not_found` は未実施 |
| (5)(11) ソース削除の `delete_by_query`、実行前 refresh、完了後 `_count` | IT-41 | 実行前 refresh・完了後 `_count` の動作は確認した。実行前 refresh が欠ければ `delete_by_query` が 2 回走る(`scroll_total` 差分 2)ことで検出する設計(`deleted_count` は再実行分を合算するため区別できない)。ただし**実装から実行前 refresh を取り除いた状態での確認は未実施**(レビューによる判断)。**素の `delete_by_query` が未 refresh の文書に 0 件を返すこと**は実装担当が実機で確認したが、テストには含めていない。**(5) の前半「再実行の上限の数値」(K48)は未実施**(スコープ外) |
| (12) `search_after` と `document_id` のソート | IT-31 | 21 件・ページサイズ 2 で漏れ・重複なく削除。ページ数は `query_total` 差分で実測(13)。**バッチ数(`DELETION_BATCH_SIZE`)は API・ログ・統計のいずれでも直接観測できず、設定値と件数からの推定** |
| 副次: `if_seq_no` の基本動作 | IT-12・IT-13・IT-30・IT-31 | `_seq_no` の変化と、条件付き削除の動作を確認 |
| (1)(2) Delete の `not_found`、存在しない文書への `if_seq_no` 付き操作 | — | **未実施**(スコープ外) |
| (3)(4) `retry_on_conflict` の値、競合の読み直しの上限(409 の再現) | — | **未実施**(スコープ外) |
| (8) `_reindex` で `dynamic: strict` に定義が欠けたとき | — | **未実施**(スコープ外) |
| (10) `delete_by_query` のタイムアウト・`version_conflicts` の再送抑止 | — | **未実施**(スコープ外) |
| (13) シャードの部分失敗の応答形 | — | **未実施**(スコープ外) |

テストで確認していないその他の項目(要件で除外): `skipped_by_ratio`(割合ルールによる削除見送り)、`validation_failed`(件数照合の不一致)、要約、メンテナンスフラグ、認証・TLS、日本語アナライザ、Crawler との接続。**割合ルールによる削除見送りの安全機構は、結合テストでは確認していない。**

### 4.4 実行スクリプト(`scripts/run-indexer-integration-test.sh`)の確認

実装担当が実機で確認した(`LORELEY_IT_PYTEST_CMD` による一時 venv での実行。成功経路の uv 経由の既定起動は 4.2 の ④⑤ で確認した)。成功経路の終了後と、全検証の終了後に、`loreley-it` のコンテナ・ボリューム・ネットワークの残りがないことを確認した。**失敗経路・シグナル・`--keep` の確認は、R2 のレビュー指摘への修正(ホスト側ポートの固定など)の前の版のスクリプトで行った。修正後に再確認したのは、成功経路(4.2 の ③)と空白だけの `LORELEY_IT_PYTEST_CMD` のみ**。

| 項目 | 結果 |
| --- | --- |
| 成功経路(別ディレクトリから呼び出し) | 36 passed、終了コード 0、全体 2 分 11 秒。後始末まで完了 |
| テスト失敗(該当テストなし `-k` 指定) | pytest の終了コード 5 をそのまま返す。`ps -a` とログ末尾を出力し、`down -v` で後始末 |
| 起動失敗(存在しないバージョンタグ) | イメージ取得失敗で 6 秒、終了コード 10。診断情報を出力して後始末 |
| 待機の上限超過(`LORELEY_IT_WAIT_TIMEOUT_SECS=1`) | indexer が starting のまま上限超過で終了コード 10。後始末 |
| ポート 9200 使用中 | 原因と対処を出して終了コード 1(スタックには触れない) |
| uv なし(`LORELEY_IT_PYTEST_CMD` 未指定) | uv が無いと案内して終了コード 1 |
| `--keep` | スタックが残り、`/healthz` が 200。表示された `down -v` で撤去できた |
| シグナル(`up` の最中) | INT で 130、TERM で 143。どちらも `down -v` まで実行 |
| 空白だけの `LORELEY_IT_PYTEST_CMD` | メインエージェントが確認。終了コード 1(スタック起動前に中止) |
| 環境変数でホスト側ポートを変更(`OPENSEARCH_HOST_PORT=19200`、`INDEXER_HOST_PORT=18000`) | メインエージェントが確認(4.2 の ③)。スクリプトが 9200/8000 に固定して起動し、40 passed |

**未再現**: init が非 0 で終了する早期失敗の経路、unhealthy・restarting の判定(`up` 自体が先に失敗するため。コードレビューで確認したのみ)、shellcheck(未導入)。なお、実行時に Docker デーモンが止まっていた(夜間のスリープ等と思われる)ときは、スクリプトの事前確認が「Docker デーモンに接続できません」と案内して 3 秒で終了コード 1 で中止した(2026-11-13 に偶然確認。デーモンが戻った後は成功した)。

## 5. 評価・発見事項

1. **compose v2.3.3 では `up --wait` が戻らない**。全サービスが Healthy / Exited(0) になったあとも終了しない(2 回再現。原因の特定はしていない)。起動済みのスタックに対して `--wait` なしの `up -d` を再実行すると 3 秒で戻った(クリーン起動では `depends_on` の healthy 待ちがあるため、3 秒では戻らない。3 章の起動所要時間を参照)。`--wait-timeout` も v2.3.3 に無い。対応として、実行スクリプトは `up -d --build` と自前のポーリング(上限 300 秒、早期失敗の判定つき)にした(確定要件の「`up --wait`」からの変更)。新しい compose で直るかは未確認。
2. **設計との食い違いの可能性(ユーザー判断事項)**: 実機で次を確認した(2026-11-12、メインエージェントが `loreley-it` スタックで手動で再現。結合テストには含めていない)。`loreley-deletions` が存在する状態で未知の `crawl_id` の Status を呼ぶと **404 `crawl_not_found`**。`loreley-deletions` のインデックスを削除(`DELETE /loreley-deletions`)してから同じ呼び出しをすると、**503 `unavailable`**(`retryable: true`)になり、Indexer のログに `the indexer is unavailable: reason=index_not_found_exception` が出た(原因は `classification.py` の `UNAVAILABLE_ERROR_TYPES` に `index_not_found_exception` が含まれること。コード読解でも一致)。設計書(indexer-api 4.5、indexer-architecture K66・9.5)は、404 `crawl_not_found` の条件に「`loreley-deletions` を失った場合」を含め、区別しないと定める。「索引は残り記録が消えた」の意味なら実装と一致する(上記の 404)。「索引ごと失った」の意味なら実装との差になる(上記の 503)。この再現は Status API だけで、登録系(409 `crawl_not_started` など)での同じ状態の挙動は未確認。障害表(arch 14.2: 喪失後も Indexer が動き、次の開始通知で現行世代が作り直される)は後者の可能性に読めるが、文言だけでは断定できない。**設計書・Indexer は変更していない**。設計の意図の確認と、必要なら修正をユーザーが判断する。補足(推測、未確認): 索引が無い状態で書き込むと、自動作成された索引が `dynamic: strict` を持たない恐れがある。
3. **search-index の U-8(`path` の最大長。`url`・`path` の拒否への対策として設計書が併記する `doc_values: false` / `ignore_above` の案)は未対応**: スキーマは設計書 4.1 の JSON のまま(`index: false` のみ、`doc_values` は既定の true)。keyword の `doc_values` に上限(32766 バイト)があり、長い値で文書が拒否される可能性が設計書の懸念事項として残る(この上限は OpenSearch/Lucene の仕様と理解しているもので、本タスクでは未検証)。設計に関わるためユーザー判断。
4. **Indexer の不具合は見つからなかった**。Indexer のログに WARNING・ERROR はなかった(フェーズ 4 の最初の実行(36 テスト)で確認した。最終の 40 テストの実行では確認していない)。発見事項 2 の再現では、意図的な索引削除に対して WARNING が出た。Indexer・設計書との食い違いに起因する期待値の変更はなかった(期待値は設計書から導いたものが初回で通った)。ただし次の 2 点は、実機の観測を受けてテストを変更した: IT-41 の検出方法(`deleted_count` では実行前 refresh の欠落を区別できなかったため、`scroll_total` 差分に変更。`deleted_count` は再実行分を合算する)、IT-31 の規模と閾値(7 → 21 件、`query_total` 差分の閾値 `>= 4` → `>= 10`。余裕が 1 しかなかったため)。
5. 設計書は、T=0(削除対象 0 件)のときに `denominator` を記録するかを明示していない。実機では、IT-30 のクロール A(対象 0 件、`deleted`)でも `denominator` は 5 と記録された。テストでは assert していない。
6. ホストと Docker VM の時計のずれは数秒以下で、TTL の余裕(10 分、1 分、2 時間、リース期限の 1 時間前)に影響しなかった。
7. `apps/indexer` の README 10 章で「実 OpenSearch に接続しての実コンテナの起動は未確認」としていた点は、本結果(4.1)で確認できた。

## 6. 未実施・今後

- (完了)uv 経由の既定起動と `tests/integration/uv.lock` の生成は、2026-11-13 に実施した(3 章、4.2 の ④⑤)。`uv run` がロックを自動生成するかどうかは、事前に `uv lock` を実行したため確認していない。
- `tests/integration/README.md` の「手動で実行する」の手順を、そのまま実行した確認(スクリプトが同じ手順を自動化しているが、README の手順どおりの実行は未実施)。`deploy/compose/README.md` の手動手順は 2026-11-13 に実行した(4.1 の最終行)。
- Linux ホスト(`vm.max_map_count`、SELinux の bind mount)と、OpenSearch 2.19 以外のバージョンでの確認。
- U-31 の未実施項目(4.3。(5) の再実行の上限の数値 K48 を含む)。
- 発見事項 2 の、登録系(409 `crawl_not_started` など)での `loreley-deletions` 喪失時の挙動。
- 変更をコミットしたあと、実施時点のコミット SHA を 3 章に追記する。
- 実装から実行前 refresh(IT-41)や `document_id` の tiebreak(IT-31)を取り除いた状態でテストが落ちることの確認(現在はレビューによる判断)。
- shellcheck(未導入)。

## 7. 再実行の手順

`tests/integration/README.md` を参照。最小のコマンド:

```sh
scripts/run-indexer-integration-test.sh   # compose 起動 → pytest → 後始末まで一括(uv が必要)
```
