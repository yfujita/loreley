# 0002 作業プラン: Crawler の結合テスト(compose 起動 + pytest)

日付: 2026-11-16
タスク: 20261116_create_it_for_crawler
作成: planner(Bash を使えないため、Docker・compose・uv・git の状態は未確認。フェーズ 0 で確認する)
承認状況: **ユーザー承認待ち**(STATUS.md を参照)
入力: 0000、0001(確定要件)、先行タスク `20261112_create_compose_and_indexer_test` の 0002、既存資材、`apps/crawler`、`crawler-architecture-v0.4.md`

## 1. 目的とゴール

- **目的**: 実装済みの Crawler(`apps/crawler`、FileSystem Connector のみ)を compose で起動し、実 OpenSearch・実 Indexer(別コンテナ・HTTP 直接通信。mock にしない)に対する結合テストを作って実行し、成功させる。
- **完了条件(受け入れ基準)**
  1. `deploy/compose/` の compose で `opensearch`・`opensearch-init`・`indexer`・`crawler` が起動し、`crawler` が healthy になる。
  2. `scripts/run-crawler-integration-test.sh` 1 本で、起動 → 待機 → pytest → 後始末が完走する。**クリーンな状態から 2 回連続で、全テスト成功(終了コード 0)**。
  3. Indexer の結合テスト 40 件が、スキーマ・compose・スクリプトの変更後も成功する(回帰確認)。
  4. Crawler を修正した場合は、Crawler の単体テスト(`uv run pytest`)・`ruff check`・`ruff format --check` も成功する。
  5. 結果が `docs/v0.x/test-results/crawler-integration.md` に残る。実際に実行して確認したことだけを書き、未実施は「未実施」と書く。
  6. 手順書(`tests/integration/crawler/README.md`、`deploy/compose/README.md` の更新)がある。
  7. 結合テストのコードに、何をテストしているかが分かるコメントが豊富に付いている(Indexer の結合テストと同じ作法)。
- **スコープ外**(0001): 10,001 件超の全件走査、実 NFS/SMB、Web Connector、並行時の `create` の原子性、運用系(起動時の回復、`docker stop` の所要時間、ロック解放 API、取り消し API)、CI 組み込み、設計書の改版。

## 2. 確定事項・前提

### 2.1 確定事項(0001 から引き継ぎ)

- テスト範囲は主要フロー + 件数照合 + ソース削除(Q1)。compose は `deploy/compose/compose.yaml` に `crawler` を追加(Q2)。テスト文書はホストの作業ディレクトリを `:ro` バインドマウント(Q3)。
- 0000 の `apps/cawler` は `apps/crawler` の誤記。対象範囲は `apps/crawler`、`infra`、`deploy`、`tests` に加え、`scripts/`、`docs/v0.x/test-results/`、`apps/crawler/README.md` の 1・8・9 章(最小限の更新)。
- スキーマ: `loreley-sources` を新設(`dynamic: strict`)。`jobs.json` は `dynamic: false` のまま arch 3.1 の項目を追加(Indexer が読む 4 項目 `owner`・`job_id`・`lease_expires_at`・`enabled` の型は変えない)。`init-indices.sh` に作成を追加(冪等)。毎回 `down -v` なので put mapping はしない。
- テストは `tests/integration/crawler/` に専用 pyproject と `uv.lock`、ホストの pytest。compose プロジェクト名は `loreley-it`。`up --wait` は使わず自前ポーリング。ジョブ状態は OpenSearch の `loreley-jobs`・`loreley-deletions`・検索インデックスを直接読む。
- 失敗が見つかったとき: 軽微なものは Crawler(単体テストも追加)かテストを修正。設計に関わる食い違いは止めてユーザーに報告。
- 「軽微」の定義(本プランで置く): 変更が `apps/crawler` かテストの内側に収まり、API の契約・設計書の決定事項・Indexer・スキーマの意味を変えないもの。それ以外は「設計に関わる」として止める。

### 2.2 「プラン作成時に決める事項」への決定

| 決める事項 | 決定(推奨案) | 根拠・却下した案 |
| --- | --- | --- |
| TTL 削除の時刻の作り方 | クロール A の後、`loreley-documents` の当該 `source_id` の全文書の `last_seen_at` を OpenSearch へ直接書いて 2 時間前にする(`_update_by_query`。Indexer の IT の `force_last_seen_at`(`tests/integration/indexer/support.py:389`)と同じ前例)。ソースは `ttl=600`、`ratio_threshold=0.5`、`min_delete_count=0`。クロール B は実時刻で動かす | Crawler は `crawl_started_at` を自分の時計で決めるのでテストから過去にできない。小さい `ttl` + 実時間待ちはジョブ所要時間との兼ね合いで不安定。全文書を過去にするので、B で残る文書は Crawler の `last-seen`(と登録)が更新したから残るという強い確認になる。割合ルール: A は 5 件、B で消えるのは 2 件(`T=2`)、B が新規 1 件を足して `D=6`、`T/D=0.33 ≤ 0.5` かつ `min_delete_count=0`。境界値は避ける |
| 実行スクリプトの共通化か複製か | **複製**(`scripts/run-crawler-integration-test.sh` を新設。`run-indexer-integration-test.sh` から必要な部分を写して調整)。`LORELEY_IT_PYTEST_CMD` の逃げ道は持ち込まない(uv は導入済み) | 共通化は検証済みの Indexer 用スクリプト(約320行)を触って再レビュー・再検証を要する。モジュール2つの MVP では複製が小さく安全。3つ目で共通化(結果記録に負債として書く)。Indexer 用スクリプトの変更は `up` に起動サービス(`opensearch opensearch-init indexer`)を明示する 1 点のみ |
| サンプル文書 | **独立に保持**。`tests/integration/crawler/samples/` に Indexer の `sample.{txt,md,html,pdf}` をコピーし、対象外ファイル(`ignored.csv`、`.hidden.txt`)とサブディレクトリ(`nested/sample-nested.txt`)を足す。サイズ超過ファイルはテストが実行時に生成(70,000 バイト)。`corrupt.pdf` は使わない | モジュール間 import は避け複製が基本。Crawler の IT は抽出結果の詳細(Indexer の IT-10・11 の範囲)を再確認せず、検索用の語が命中することだけ確認する |
| スキップの再現方法 | **Crawler 側の原本サイズ超過**(70,000 バイト > Crawler の `MAX_RAW_BYTES=65536`)を 1 件とする。`fetch_permission_denied` は入れず、結果記録に「未実施」 | 権限は Docker Desktop(macOS)のバインドマウントで uid 10001 への `chmod 000` が再現するか環境依存で不安定。サイズ超過は決定的で、`oversize` 記録・`oversize_document_ids`・`E_missing` の件数照合まで確認できる。確認できないもの: `skip` 記録と `partially_succeeded` への遷移(単体テストで確認済み) |

### 2.3 置いた前提(承認時にユーザーへ再確認する)

1. **Crawler のホスト公開**: `127.0.0.1:8001` だけに publish する。arch 10 章は「ホストに公開しない」だが、ホストの pytest から呼ぶために必要。Crawler の API は認証がない(クロール起動・ソース削除・ロック解放まで可能)ためループバック限定とし、compose.yaml 冒頭コメントと README に理由を書く(設計書は改版しない)。
2. **`INDEXER_*` 上限の単一定義元**: ベース `compose.yaml` で、Crawler の `LORELEY_CRAWLER_INDEXER_<名前>` 6つと Indexer の `LORELEY_INDEXER_<名前>` 6つに、同じ変数 `${INDEXER_<名前>:-<Indexer のコード既定値>}` を渡す(arch 10 章「同じ定義元」)。既定値は Indexer の `config.py` のとおり(`MAX_RAW_BYTES=20971520`、`MAX_BATCH_DOCUMENTS=50`、`MAX_BATCH_BYTES=67108864`、`MAX_REQUEST_BODY_BYTES=104857600`、`MAX_LAST_SEEN_IDS=1000`、`SKIP_OVERSIZE_ID_LIMIT=10000`)。Indexer のサービスに環境変数が増えるが値は既定値と同じ。Indexer の IT の `compose.test.yaml` の上書きは優先されるので影響しない(回帰確認で確かめる)。
3. 索引名は `LORELEY_JOBS_INDEX_NAME`(`opensearch-init` の `JOBS_INDEX_NAME`、Indexer の `LORELEY_INDEXER_JOBS_INDEX_NAME`、Crawler の `LORELEY_CRAWLER_JOBS_INDEX_NAME` の 3 者に同値)と `LORELEY_SOURCES_INDEX_NAME`(`opensearch-init` と Crawler の 2 者)の compose 変数で渡す。
4. メモリ約 3.8GiB で OpenSearch(ヒープ 512m)+ Indexer + Crawler を同時起動する。逼迫したら症状と対処を結果に記録する。
5. compose は現在 OpenSearch `3.9.0` を既定にしている(`deploy/compose/compose.yaml:26`)が、`docs/v0.x/test-results/indexer-integration.md` は 2.19.7 で記録している。食い違いの経緯は未確認。フェーズ 0 で実際に動いている版を記録し、フェーズ 6 の Indexer 回帰確認は同書に再実行として追記する。
6. ユーザー回答中の「ロック解放」は「実行中のロックが `loreley-jobs` に存在し、ジョブ終了後に解放される」と解釈する(ロック解放 API は対象外)。
7. 実装は `code-implementer`、compose 起動・テスト実行・作業記録・STATUS.md はメインエージェント、文書は `document-writer`、レビューは実装担当と別のエージェント。サブエージェントは `STATUS.md` と `NNNN-*.md` を書かない。

## 3. 影響範囲

| 区分 | パス | フェーズ |
| --- | --- | --- |
| スキーマ | `infra/opensearch/schema/sources.json`(新規)、`jobs.json`(項目追加)、`init-indices.sh`(`loreley-sources` 作成と `SOURCES_INDEX_NAME` 追加) | 1 |
| compose | `deploy/compose/compose.yaml`(`crawler` 追加。`indexer`・`opensearch-init` に変数追加)、`deploy/compose/.env.example` | 2 |
| テスト用上書き | `tests/integration/crawler/compose.test.yaml` | 2 |
| Indexer 用スクリプト | `scripts/run-indexer-integration-test.sh`(`up` に起動サービスを明示。1点のみ) | 2 |
| 結合テスト | `tests/integration/crawler/{pyproject.toml,uv.lock,conftest.py,support.py,test_*.py,samples/**,README.md}` | 3・4 |
| 実行 | `scripts/run-crawler-integration-test.sh`(新規) | 5 |
| gitignore | `.gitignore`(`tests/integration/*/data/` を追加) | 3 |
| 結果 | `docs/v0.x/test-results/crawler-integration.md`、`indexer-integration.md`(回帰確認の追記のみ) | 6 |
| 手順書・README | `tests/integration/crawler/README.md`、`deploy/compose/README.md`、`apps/crawler/README.md` の 1・8・9 章、`jobs.json` が仮定義だと書いてある箇所(`deploy/compose/README.md`、`tests/integration/indexer/README.md`、`apps/indexer/README.md` を grep して最小限更新) | 6 |
| 条件付き | `apps/crawler/src/...` と単体テスト(実機で不具合が出た場合のみ) | 4 |

## 4. スキーマ(フェーズ 1 の仕様)

### 4.1 `sources.json`(`loreley-sources`)
- shards 1、replicas 0、`dynamic: strict`。項目は arch 3.1・3.2。
  - keyword: `source_id`、`connector_type`、`status`、`schedule_cron`
  - long: `ttl`、`min_delete_count` / double: `ratio_threshold` / date: `updated_at`
  - object(索引しない): `connector_config` → `{"type": "object", "enabled": false}`
- 実装者は `apps/crawler/src/loreley_crawler/sources/records.py` の `build_body()` の全キーが漏れなく入っていることを突き合わせる(漏れは `strict_dynamic_mapping_exception` として実機で現れる)。

### 4.2 `jobs.json`(`loreley-jobs`)の拡張
- `dynamic: false` のまま。既存4項目(`owner`・`job_id` keyword、`lease_expires_at` date、`enabled` boolean)は変えない。
- 追加(arch 3.1):
  - keyword: `record_type`、`source_id`、`job_type`、`status`、`trigger`、`document_id`、`last_job_id`
  - date: `queued_at`、`started_at`、`finished_at`、`heartbeat_at`、`acquired_at`、`first_skipped_at`、`last_skipped_at`、`first_detected_at`、`last_detected_at`、`settings_source_updated_at`
  - object(索引しない、`enabled: false`): `settings_snapshot`、`finish_notice`、`registration`、`deletion_summary`、`warnings`
- 実装者は Crawler が絞り込み・並べ替え・`exists` に使う項目が全て定義されていることを grep(`RecordFilter(`、`SortKey(`)で再確認する。

### 4.3 `init-indices.sh`
- `SOURCES_INDEX_NAME`(既定 `loreley-sources`)を追加し、`create_index_if_absent "$SOURCES_INDEX_NAME" sources.json` を追加。冪等性は既存関数のとおり。冒頭の環境変数一覧コメントにも追記。

## 5. 実装フェーズ

各フェーズの終了時にメインエージェントが作業記録を残し、`STATUS.md` を更新する。

### フェーズ 0: 前提確認とベースライン(メイン)
- 内容: `docker --version`、`docker compose version`、`docker info`、`uv --version`、ポート 9200・8000・8001 の空き、アーキテクチャ。`git rev-parse HEAD` を基準コミットとして記録(プラン作成時点は `6970478`)。**変更前に** `scripts/run-indexer-integration-test.sh` を 1 回実行し 40 passed を確認(実際の OpenSearch バージョンも記録)。
- Docker・compose・uv が使えない場合は `blocked` にしてユーザーに報告する。推測で成功と書かない。

### フェーズ 1: スキーマ(`code-implementer`)
- 成果物: 4 章の `sources.json`、`jobs.json` 拡張、`init-indices.sh` 変更。
- 検証: 3 JSON が `python -m json.tool` を通る、`sh -n`、書き込み項目とマッピングの突き合わせ表を作業記録に載せる、`opensearch` + `opensearch-init` を起動して `_mapping` で 4 索引の存在・`dynamic`(sources=strict、jobs=false)・型を確認、init 再実行で全て skip(冪等)。
- **回帰確認**: Indexer の IT 40 passed(IT-01 が `loreley-jobs` の `dynamic: false` を検証)。

### フェーズ 2: compose と Indexer 用スクリプトの調整(`code-implementer`)
- `deploy/compose/compose.yaml` の `crawler`: `build: ../../apps/crawler`、`restart: unless-stopped`、`stop_grace_period: 30s`、環境変数(`LORELEY_CRAWLER_OWNER=crawler-1`、`..._OPENSEARCH_URL`、`..._INDEXER_URL=http://indexer:8000`、`..._LOG_LEVEL`、`..._JOBS_INDEX_NAME`・`..._SOURCES_INDEX_NAME`、`..._INDEXER_<6項目>`)、`depends_on`(`opensearch` healthy、`opensearch-init` completed_successfully、`indexer` healthy)、ポート `127.0.0.1:${CRAWLER_HOST_PORT:-8001}:8001` のみ、healthcheck の `start_period: 180s`(`test` はイメージのものを使う)、ボリューム `${CRAWLER_DOCUMENTS_DIR:-./documents}:/data/documents:ro`(`:?` は使わない。起動しないサービスでも解釈時に失敗し Indexer 用スクリプトが壊れるため)、冒頭コメントに公開範囲の理由を追記。
- `opensearch-init` に `SOURCES_INDEX_NAME`・`JOBS_INDEX_NAME`、`indexer` に `LORELEY_INDEXER_JOBS_INDEX_NAME` と上限6つを追加。
- `deploy/compose/.env.example` に `CRAWLER_HOST_PORT`、`CRAWLER_LOG_LEVEL`、`CRAWLER_DOCUMENTS_DIR`、`LORELEY_JOBS_INDEX_NAME`、`LORELEY_SOURCES_INDEX_NAME`、`INDEXER_*` 6つ。
- `tests/integration/crawler/compose.test.yaml`(7 章の値。YAML アンカーで `MAX_RAW_BYTES` の 65536 を 1 か所に定義)。
- `scripts/run-indexer-integration-test.sh`: `compose up -d --build` に `opensearch opensearch-init indexer` を明示。
- 検証: `docker compose ... config` が通る(公開ポートが `127.0.0.1` のみ、整合性検査が通る値)。手動起動して `crawler` が healthy、`GET http://127.0.0.1:8001/healthz` が 200、起動ログに「Indexer の上限が未設定」の警告が出ない、`docker inspect` でイメージの healthcheck `test` が保持されている(保持されない場合は compose に明示し理由を記録)。
- **回帰確認**: Indexer 用スクリプトで 40 passed(crawler が起動しないこと、既定上限の変数が影響しないこと)。

### レビュー R1(フェーズ 1・2 の後)— 6 章

### フェーズ 3: テスト資材(`code-implementer`)
- 成果物(`tests/integration/crawler/`):
  - `pyproject.toml`(Indexer 用に倣う: `httpx`、`pytest`、dev に `ruff`。`package = false`、`pythonpath`、E501 対象外設定)、`uv.lock`。
  - `samples/`(2.2 のとおり)と `samples/README.md`。
  - `support.py`: 定数、`unique_id`(`source_id` の文字種 `[A-Za-z0-9][A-Za-z0-9._-]*`)、`compute_document_id`(SHA-256(`source_id` + NUL + `external_id`)のテスト側独立実装。Indexer の IT の `support.py:120` に倣い複製)、`OpenSearchProbe`(必要分を複製)、`CrawlerApi`、`wait_for_job`、`SourceDirectory`(サンプルのコピー・削除・書き換え。ファイル 0644、ディレクトリ 0755。teardown で削除)。
  - `conftest.py`: 疎通確認(OpenSearch・Indexer・Crawler の `/healthz`。落ちていたら原因の分かるメッセージで `pytest.exit`)、`source_id` 等のフィクスチャ、`documents_dir`、`registered_source`。
- `.gitignore` に `tests/integration/*/data/` を追加。
- コメント方針(Indexer の IT と同じ): 各ファイル冒頭に目的・設計書の章・シナリオ ID。各テストの docstring に【何を確認するか】【前提と手順】【期待する結果とその根拠】【fake では確認できず実機で確認する点】。手順の各ステップに 1 行の意図コメント。`assert` にメッセージ。
- 検証: `uv run --project tests/integration/crawler pytest --collect-only`、`ruff check`、`ruff format --check`。

### フェーズ 4: テスト本体の実装と実行・修正(`code-implementer` が実装、メインが実行)
- 手動でスタックを起動(`CRAWLER_DOCUMENTS_DIR` を `tests/integration/crawler/data` の絶対パスにして `up -d --build`)。まず CIT-01・10・20 で縦に通し、次に CIT-21・22・30・40・50。
- 失敗の切り分け: テストの誤り / Crawler の不具合 / スキーマの誤り / 設計との食い違い。2.1 の方針で対応(Crawler の修正は単体テストを併せて追加し `uv run pytest`・`ruff check`・`ruff format --check` を通す。設計に関わるものは止めてユーザーに報告)。
- 検証: 手動起動のスタックで全テスト成功。続けて 2 回実行しても干渉しない。

### フェーズ 5: 実行スクリプト(`code-implementer`)
- `run-indexer-integration-test.sh` を写して調整:
  - プロジェクト名 `loreley-it`、ポート 9200・8000・8001、compose ファイルは `deploy/compose/compose.yaml` + `tests/integration/crawler/compose.test.yaml`。
  - `CRAWLER_DOCUMENTS_DIR` を `tests/integration/crawler/data` の絶対パスに export し、起動前に `mkdir -p`、終了時(`trap`)に削除(`rm -rf "${var:?}"`)。
  - 起動待機: `opensearch:healthy`、`opensearch-init:exited_ok`、`indexer:healthy`、`crawler:healthy`。上限 300 秒(`LORELEY_IT_WAIT_TIMEOUT_SECS`)。
  - pytest: `uv run --project tests/integration/crawler pytest tests/integration/crawler -v`(出力は `tests/integration/crawler/results/pytest-*.log` にも保存)。
  - 終了コードは Indexer 用と同じ体系(pytest / 1=事前確認 / 10=起動失敗 / 130・143=中断)。異常終了時は `ps -a` と各サービスのログ末尾を出してから `down -v --remove-orphans`。
- 検証(メイン): 成功経路 1 回。失敗経路(`LORELEY_IT_WAIT_TIMEOUT_SECS=1` で終了コード 10、ポートを塞いだ事前確認失敗)で後始末と終了コードが正しいこと(終了後 `ps -a` が空、`data/` が残らない)。

### レビュー R2(フェーズ 3〜5 の後)— 6 章

### フェーズ 6: 動作確認・結果・手順書(メイン + `document-writer`)
- 実施(R2 の指摘対応後の最終コードで):
  1. クリーンな状態から `scripts/run-crawler-integration-test.sh` を **2 回連続**で全テスト成功(終了コード 0、残骸なし)。ログ保存。
  2. `scripts/run-indexer-integration-test.sh` で 40 passed(回帰)。実際の OpenSearch バージョンを記録。
  3. Crawler を修正した場合は `apps/crawler` で `uv run pytest`、`uv run ruff check`、`uv run ruff format --check`、`uv lock --check`。
- 文書(`document-writer`。メインが実測値・ログ抜粋を渡す):
  - `docs/v0.x/test-results/crawler-integration.md`: `indexer-integration.md` の形式(ヘッダ表、目的、記録のルール、環境、シナリオ別結果、`apps/crawler/README.md` 8 章の項目との対応表、発見事項、再実行手順)。**未実施は「未実施」**(10,001 件超の走査、`create` の並行原子性、`docker stop`、起動時の回復、ロック解放 API・取り消し API、`skip` 記録と `partially_succeeded`(権限エラー)、実 NFS/SMB、Web Connector など)。`indexer-integration.md` に回帰確認を追記。
  - `tests/integration/crawler/README.md`、`deploy/compose/README.md` 更新(`crawler` サービス、ループバック公開の理由、`CRAWLER_DOCUMENTS_DIR`、`jobs.json` 拡張済み)。
  - `apps/crawler/README.md` の 1・8・9 章を実績に合わせて最小限に。設計書は改版しない。
- 検証: 手順書どおり(スクリプトと手動)に実行して通る(手動手順は 1 回)。

### レビュー R3(フェーズ 6 の後)とタスクレビュー — 6 章

## 6. レビューフェーズ

共通事項:
- 実装担当とレビュー担当は別のエージェント。実行はメインエージェント。
- 比較基準: フェーズ 0 で記録する基準コミット(プラン作成時点の HEAD は `6970478`。未コミットの変更が中心なので**対象はパスを列挙**。途中でコミットした場合は基準 SHA を更新して明示)。
- 渡す文脈: `0000`、`0001`、本プラン、作成済みの作業記録、`STATUS.md`。
- 指摘への対応: Critical / Important は該当フェーズに戻して修正し、同じレビュアーで再レビュー。Suggestion / Nitpick は対応可否を判断し理由とともに作業記録に残す。「指摘なし」または Critical / Important 解消済みになるまで完了としない。

| レビュー | 時点 | 担当 | 対象パス | 観点・理由 |
| --- | --- | --- | --- | --- |
| R1 | フェーズ 2 の後 | `code-reviewer` | `infra/opensearch/**`、`deploy/compose/compose.yaml`、`deploy/compose/.env.example`、`tests/integration/crawler/compose.test.yaml`、`scripts/run-indexer-integration-test.sh` の差分 | **省略不可**: 認証なしの Crawler API を新たにホストへ publish するためアクセス制御に直結。観点: 公開ポートがループバックのみ、`:ro` マウントの範囲、上限・索引名の同値定義、`depends_on`・healthcheck、init の冪等性、スキーマと書き込み項目の突き合わせ、Indexer 用スクリプトの変更が最小か |
| R2 | フェーズ 5 の後 | `code-reviewer` + `test-reviewer`(並列) | `tests/integration/crawler/**`(`.venv`・`results`・`data` を除く)、`scripts/run-crawler-integration-test.sh`、`.gitignore`、フェーズ 4 で変えた `apps/crawler`(あれば) | `test-reviewer`: シナリオの過不足(0001 の対象外に踏み込んでいないか)、期待値の根拠、再現性(時刻依存・待ち・干渉・偽陽性)、TTL の前提作りが「Crawler の last-seen のおかげで残る」ことを検証できているか、メンテナンスフラグの後始末、コメントの作法。`code-reviewer`: スクリプトの `trap`・後始末・`rm -rf` の安全性・終了コード、ポート、ファイル権限、Crawler 修正があればその正しさと単体テスト |
| R3 | フェーズ 6 の後 | `document-reviewer` | `docs/v0.x/test-results/crawler-integration.md`、`indexer-integration.md`(追記部分)、`tests/integration/crawler/README.md`、`deploy/compose/README.md`、`apps/crawler/README.md`(1・8・9 章)、他 README の `jobs.json` 関連更新箇所 | 結果記録が実行ログと一致するか(未実施を成功と書いていない)、手順書で再現できるか、設計書(arch 3.1・10・12 章)との整合と食い違いが「発見事項」に書かれているか |

### タスクレビュー(最後)
- **実施する**。理由: フェーズが多く複数セッションにまたがる見込み、認証なし API の公開というアクセス制御に関わる変更を含み、要件・プランからの乖離(TTL の前提作り、スキップ再現の代替、`jobs.json` 拡張、Indexer サービスへの変数追加、Crawler 修正の有無)を工程全体で確認する価値があるため。
- R1〜R3 完了、作業記録と `STATUS.md` の更新後に `task-reviewer` で実施。コード・テスト単体のレビューは R1〜R3 の担当で重複させない。指摘対応は R と同様。

## 7. テストシナリオ(`tests/integration/crawler/`)

共通: 各テストは一意の `source_id` と専用の `tests/integration/crawler/data/<source_id>/`(= コンテナ内 `/data/documents/<source_id>`)。`connector_config` の `root` はこのパス。OpenSearch を直接読む(検索系の前に `_refresh`)。待ちは間隔と上限を明示したポーリングで、`sleep` に頼らない。

| ID | ファイル | 0001 の項目 | 確認すること |
| --- | --- | --- | --- |
| CIT-01 | `test_01_startup.py` | 1 | `crawler` の `/healthz` が 200。4 索引(`loreley-documents` エイリアス、`loreley-deletions`、`loreley-jobs`、`loreley-sources`)が存在し、`loreley-sources` が `dynamic: strict`、`loreley-jobs` が `dynamic: false` で `record_type`・`status`・`queued_at` などが定義されている |
| CIT-10 | `test_10_source_registration.py` | 2 | `POST /sources` が 201、同内容の再送が 200、`loreley-sources` の文書の型が strict マッピングに受け入れられる。未知の `connector_config` 項目は 400 `invalid_request`。存在しない `source_id` へのクロール起動は 404 `source_config_not_found` |
| CIT-20 | `test_20_crawl.py` | 3・4・5・6 | `sample.{txt,md,html,pdf}` + `nested/sample-nested.txt` + 対象外(`ignored.csv`、`.hidden.txt`)で `POST .../crawl-jobs`(202)→ ジョブが `succeeded`(`confirmation=confirmed`、`registration.enumerated_count=5`)。検索インデックスに 5 件(`document_id` がテスト側独立実装の SHA-256 と一致)、検索語で命中、対象外は入らない。`loreley-deletions` の `deletion_result-{job_id}` が `deleted`・`enumerated_count == n_seen + e_missing`(5 == 5 + 0)・`validation_failed` でない。クロール終了後の整理(PIT・`search_after`)が実 OpenSearch で通る |
| CIT-21 | `test_20_crawl.py` | 9 | 通常ファイル 1 件 + 70,000 バイトのファイル(Crawler の `MAX_RAW_BYTES=65536` 超過)。ジョブは `succeeded`(arch 6.5)。`oversize-{source_id}-{document_id}` 記録(`detected_by=crawler`)、`finish_notice.content.oversize_document_ids` に載り、索引には入らない。`enumerated_count == n_seen + e_missing`(2 == 1 + 1)で `validation_failed` でない |
| CIT-22 | `test_20_crawl.py` | 10 | 実行中に `lock-{source_id}` が存在し、`owner=crawler-1`、`job_id` がジョブ ID、`lease_expires_at` が未来(0.2 秒間隔で観測。`POLLING_INTERVAL_SECONDS=2` で窓がある)。終了後はロック文書が消える |
| CIT-30 | `test_30_ttl_deletion.py` | 7 | クロール A(5 件: kept1・kept2・kept3・gone1・gone2。`ttl=600`、`ratio_threshold=0.5`、`min_delete_count=0`)が `succeeded`。全文書の `last_seen_at` を 2 時間前に書き換え。gone1・gone2 を削除、kept2 の本文を変更、new1 を追加。クロール B が `succeeded`。B の結果: `deleted`、`enumerated_count=4`、`n_seen=4`、`e_missing=0`、`target_count=2`、`denominator=6`、`deleted_count=2`(`skipped_by_ratio` にならない)。gone1・gone2 は消え、kept1・kept2(updated)・kept3・new1 は残る。他ソースの文書は残る |
| CIT-40 | `test_40_source_deletion.py` | 8 | 2 つのソースをクロール(片方にサイズ超過ファイルを含め `oversize` 記録を作る)。片方に `POST .../delete-jobs`(202)→ `succeeded`。当該ソースの文書 0 件、`loreley-deletions` の当該記録が消え、`oversize` 記録が消え、`loreley-sources` の設定が 404、ロック文書なし。もう片方の文書・記録・設定は残る。削除後のクロール起動は 404 `source_config_not_found` |
| CIT-50 | `test_50_maintenance.py` | 11 | `loreley-jobs` に ID `maintenance`、`{"record_type": "maintenance", "enabled": true}` を書くと `POST .../crawl-jobs` が 409 `maintenance_enabled`、ジョブ記録・ロック文書が作られない。フラグは `try/finally` で必ず削除(残ると Indexer の削除判断も止める)。削除後はクロール起動が 202 |

### 具体値

| 項目 | 値 | 理由 |
| --- | --- | --- |
| compose プロジェクト名 | `loreley-it` | 先行タスクと同じ。Indexer の IT と同時には動かせない(README に明記) |
| ホストのポート | 9200 / 8000 / 8001(すべて 127.0.0.1) | スクリプトが export |
| `LORELEY_CRAWLER_OWNER` | `crawler-1` | ロックの `owner` で検証 |
| `MAX_RAW_BYTES` | 65536(Indexer・Crawler・`CRAWLER_INDEXER_MAX_RAW_BYTES` の 3 者が同値。アンカーで 1 か所定義) | Crawler 既定 20MiB は Indexer の 64KiB を超え整合性検査で失敗するため、Indexer 用の上書きは流用せず両方を明示 |
| 他の Indexer 上限 | 既定のまま(両者に同じ変数) | Crawler の既定は Indexer の上限以下 |
| `LORELEY_INDEXER_DELETION_POLL_INTERVAL_SECONDS` | 1 | 待ちを減らす |
| `LORELEY_CRAWLER_POLLING_INTERVAL_SECONDS` | 2 | 既定 5 秒より短く、CIT-22 の窓を確保 |
| `LORELEY_CRAWLER_POLLING_TIMEOUT_SECONDS` | 120 | 既定 1800 秒だと居座るジョブが直列の Job Runner で後続をブロックするため |
| `LORELEY_CRAWLER_RUNNER_SCAN_INTERVAL_SECONDS` | 1 | 既定 5 秒 |
| Crawler の healthcheck(テスト用) | `interval: 3s`、`start_period: 180s` | healthy 判定を早める |
| ジョブ完了のポーリング | 間隔 0.5 秒、上限 90 秒 | |
| ロック観測 | 間隔 0.2 秒、上限 30 秒 | |
| TTL 関連 | `ttl=600`、バックデート先 2 時間前 | 2.2 |
| 起動待機の上限 | 300 秒 | Indexer 用と同じ |
| ファイル権限 | ファイル 0644、ディレクトリ 0755 | Crawler は uid 10001 で動く |

## 8. テスト方針

- 層: 結合テストのみ(ホスト pytest → 127.0.0.1 の Crawler・Indexer・OpenSearch)。Crawler 内部は fake の単体テストが既にあり重複させない。
- 判定は HTTP 応答と OpenSearch の実データの両方。
- 非決定性対策: 一意 `source_id`、検索系の前に `_refresh`、ポーリングは間隔と上限を明示、TTL は `last_seen_at` 書き換えで決定的、メンテナンスフラグは `try/finally`、テスト間の順序依存なし、2 回連続実行。
- 期待値は設計書の章を根拠にコメントへ。実機の挙動が設計・README と違った場合、テストを実機に合わせて変えず発見事項として扱う(2.1)。
- 回帰: スキーマ・compose・スクリプトを触ったフェーズ(1・2・6)で Indexer の IT(40 件)を再実行。Crawler を修正した場合は単体テスト・`ruff` を再実行。

## 9. リスクと対策

| リスク | 対策 |
| --- | --- |
| Crawler のイメージが初めて実 compose でビルド・起動される | フェーズ 2 で手動起動して確認。不具合は 2.1 の方針で対応・記録 |
| Docker Desktop のバインドマウントの可視性の遅れ | フェーズ 4 で実機確認。再現したら `SourceDirectory` に有限ポーリングを足す(sleep しない) |
| ファイル権限(uid 10001 が読めない) | 0644/0755 を明示。失敗時はログから原因が分かる |
| TTL の前提作りが Indexer 内部の `last_seen_at` に依存 | Indexer の IT が同じ前例。項目名変更は Indexer の IT も壊れるので検出できる。R2 で確認 |
| ロック観測の窓が足りない | `POLLING_INTERVAL_SECONDS=2`。足りなければ値を伸ばして記録 |
| メンテナンスフラグが残って他テスト・Indexer の削除判断を止める | `try/finally`、teardown。復旧手順を README に(`down -v` で消える) |
| 直列 Job Runner が居座るジョブで後続をブロック | `POLLING_TIMEOUT_SECONDS=120`、完了ポーリング上限 90 秒 |
| compose v2.3.3 での healthcheck 部分上書き・アンカー・`depends_on` | フェーズ 2 で `config` と実起動で確認。不可なら明示指定に変更し記録 |
| 認証なし Crawler API の公開 | ループバックのみ publish。R1 で必ず確認。README に理由 |
| `jobs.json` 拡張が Indexer の IT を壊す | フェーズ 1・2・6 で Indexer の IT を再実行 |
| メモリ不足 | ヒープ 512m。逼迫したら症状と対処を記録 |
| OpenSearch バージョンの食い違い(compose 3.9.0 / 結果記録 2.19.7) | フェーズ 0 で実測し結果記録に明記 |

**ロールバック**: 追加物は新規ファイル中心で、削除で戻る。既存ファイルの変更は差分を個別に戻す。実行中のスタックは `docker compose -p loreley-it -f deploy/compose/compose.yaml -f tests/integration/crawler/compose.test.yaml down -v --remove-orphans`。

## 10. 未解決事項

- 実機で設計との食い違いが見つかった場合: 設計書の改版は本タスクでは行わず、発見事項に記録しユーザー判断。arch 10 章「Crawler はホストに公開しない」との差(2.3 の 1)は承認時に確認。
- OpenSearch の実バージョン(フェーズ 0)、compose v2.3.3 の挙動(フェーズ 2)。
- スクリプトの重複(Indexer 用・Crawler 用)は 3 つ目のモジュールのときの負債として結果記録に残す。
- CI への組み込みは対象外。

## 11. 承認時に確認したい論点

1. TTL: `last_seen_at` を OpenSearch へ直接書いて過去にする方式(Indexer の IT の前例どおり)でよいか
2. スクリプトは複製でよいか(共通化は 3 つ目のモジュールのとき)
3. スキップの再現は Crawler 側のサイズ超過とし、権限エラー(`skip` 記録・`partially_succeeded`)は「未実施」としてよいか
4. Crawler の API を `127.0.0.1:8001` に publish する(arch 10 章「ホストに公開しない」との差。ループバック限定)
5. ベース compose の `indexer` に、Crawler と同じ上限・索引名の変数を渡す変更を入れてよいか(値は既定と同じ。Indexer の IT で回帰確認)
