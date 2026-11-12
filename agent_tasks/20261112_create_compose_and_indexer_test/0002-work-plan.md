# 0002 作業プラン: compose の作成と Indexer の結合テスト

日付: 2026-11-12
タスク: 20261112_create_compose_and_indexer_test
入力: 0000(要件定義)、0001(確定要件・ユーザー回答)、STATUS.md、`apps/indexer`(Dockerfile・README・pyproject・src)、設計書(indexer-api v0.10、indexer-architecture v0.10、indexer-module-structure v0.4、search-index v0.10、loreley-deletions v0.10)、`docs/v0.x/test-results/opensearch-performance.md`(結果記録の形式)

> planner の作成したプラン。ユーザー承認前(承認状況は STATUS.md を参照)。planner は Bash を使えず、Docker・docker compose・uv の有無は未確認(フェーズ 0 で確認する)。

## 1. 目的とゴール

- **目的**: Indexer だけがある状態で compose を作り、`opensearch` と `indexer` を起動する。実 OpenSearch に対する結合テストで Indexer の主要フローを確認し、これまで fake でしか確認できていない挙動(README 10 章・arch U-31 の一部)を実機で確かめる。
- **完了条件(受け入れ基準)**
  1. `deploy/compose/` の compose で `opensearch`・`opensearch-init`・`indexer` が起動し、`indexer` が healthy になる。
  2. `scripts/` の実行スクリプト 1 本で `up --wait` → `pytest` → `down -v` が完走し、`tests/integration/` の全シナリオが成功する(0000 の完了条件「compose を利用したテストが成功」)。
  3. 結果が作業記録と `docs/v0.x/test-results/indexer-integration.md` に残っている。実際に実行して確認したことだけを書き、未実施の項目は「未実施」とする。
  4. 手順書(`deploy/compose/README.md`、`tests/integration/README.md`)がある。
  5. 結合テストのコードに、何をテストしているかが分かるコメントが豊富に付いている(0000 の制約)。
- **スコープ外**: Indexer 以外のモジュールの compose、CI 組み込み、日本語アナライザ、認証・TLS 経路、409 競合・`_reindex`・要約(0001 Q2)。

## 2. 確定事項・前提

確定事項(0001 から引き継ぎ):
- スキーマは `infra/opensearch/schema/{search-index,deletions,jobs}.json` に置く。compose の `opensearch-init` が OpenSearch healthy 後に一度だけ作成し、`indexer` は `depends_on` で完了を待つ。OpenSearch は公式イメージ(日本語プラグインなし)、単一ノード、ヒープ小さめ、セキュリティプラグイン無効。バージョンはフェーズ 2 で安定版を選んで固定し、結果に記録する。
- compose は `deploy/compose/{compose.yaml,.env.example,README.md}`。`compose.dev.yaml` は作らない。
- OpenSearch は `127.0.0.1:9200`、Indexer は `127.0.0.1:8000` のループバックだけに publish する(Indexer は認証なしのため)。Indexer は要約無効で、接続先は `http://opensearch:9200`。
- テストはルート `tests/integration/` に pytest で置き、ホストから実行する。専用 pyproject で依存を分離する。`source_id` / `crawl_id` はテストごとに一意にし、固定サンプル文書を `tests/integration/samples/` に置く。
- 不具合・設計との食い違い: 軽微なものは `apps/indexer` で修正する(単体テストを併せて追加)。設計に関わるものはユーザーに報告して判断を仰ぐ。
- 対象範囲は 0000 に `infra/opensearch`、`scripts/`、`docs/v0.x/test-results/` を加えたもの。

置いた前提:
- 設計書は変更しない。実機で分かった食い違いは結果記録に書き、設計書への反映はユーザーが判断する。
- 実装は `code-implementer`、実行(起動確認・動作確認)と作業記録はメインエージェント、文書は `document-writer`。**レビューは実装担当と別のエージェント**が行う。
- 作業記録・`STATUS.md` はメインエージェントのみが書く。

## 3. 影響範囲(新規ファイルが中心。既存の変更は最小)

| 区分 | パス | フェーズ |
| --- | --- | --- |
| スキーマ | `infra/opensearch/schema/search-index.json`、`deletions.json`、`jobs.json` | 1 |
| 初期化 | `infra/opensearch/init-indices.sh`(冪等) | 1 |
| compose | `deploy/compose/compose.yaml`、`.env.example` | 2 |
| テスト用上書き | `tests/integration/compose.test.yaml`(Indexer の小さい上限・バッチ値) | 4 |
| 結合テスト | `tests/integration/{pyproject.toml,uv.lock,conftest.py,test_*.py,samples/*,README.md}` | 4、7 |
| 実行 | `scripts/run-indexer-integration-test.sh` | 5 |
| 結果 | `docs/v0.x/test-results/indexer-integration.md` | 6 |
| 手順書 | `deploy/compose/README.md`、`tests/integration/README.md` | 2(雛形)、7 |
| 既存の軽微な更新 | `apps/indexer/README.md` 10 章の最終文(「OpenSearch に接続しての実コンテナの起動は未確認」)を実績に合わせる。`.gitignore`(`tests/integration/.venv`、結果出力先) | 7 |
| 条件付き | `apps/indexer/src/...` と単体テスト(実機で不具合が出た場合のみ) | 3・6 |

参照した主な既存コード: `apps/indexer/Dockerfile:15,74-102`、`apps/indexer/src/loreley_indexer/infrastructure/opensearch/jobs.py:19-20`、`crawl_runs/lifecycle/records.py:85-239`、`crawl_runs/lifecycle/results.py:114-266`、`documents/search_document.py:55-90`。

## 4. マッピング案(設計書の前提を満たす最小案。承認時に確認)

設計書は deletions・jobs のマッピングを未決とし、前提(deletions 7 章、search-index 4 章)だけを置いている。

### 4.1 `search-index.json`
- search-index v0.10 の 4.1 の JSON をそのまま使う(`dynamic: strict`、shards 1、replicas 0。アナライザなし)。
- 実体は `loreley-documents-000001`、エイリアス `loreley-documents`(search-index 5.2「エイリアス経由」、README 3 章)。Indexer の既定 `SEARCH_INDEX_NAME=loreley-documents` はエイリアスに読み書きする。
- 問題が出たら、実インデックス名を `loreley-documents` にする案へ切り替え、結果に記録する。

### 4.2 `deletions.json`(`loreley-deletions`)
- `dynamic: strict`。`records.py` の全項目を定義する(Indexer が定義外の項目を書いたら実機で失敗として検出できるため)。shards 1、replicas 0。

```json
{
  "settings": { "index": { "number_of_shards": 1, "number_of_replicas": 0 } },
  "mappings": {
    "dynamic": "strict",
    "properties": {
      "record_type": { "type": "keyword" },
      "source_id": { "type": "keyword" },
      "crawl_id": { "type": "keyword" },
      "status": { "type": "keyword" },
      "reason": { "type": "keyword" },
      "reason_detail": { "type": "keyword" },
      "outcome": { "type": "keyword" },
      "finish_request_digest": { "type": "keyword" },
      "crawl_started_at": { "type": "date" },
      "started_at": { "type": "date" },
      "ended_at": { "type": "date" },
      "finish_received_at": { "type": "date" },
      "deletion_started_at": { "type": "date" },
      "updated_at": { "type": "date" },
      "ttl": { "type": "long" },
      "ratio_threshold": { "type": "double" },
      "min_delete_count": { "type": "long" },
      "enumerated_count": { "type": "long" },
      "skip_and_oversize_id_count": { "type": "long" },
      "n_seen": { "type": "long" },
      "e_missing": { "type": "long" },
      "target_count": { "type": "long" },
      "denominator": { "type": "long" },
      "deleted_count": { "type": "long" },
      "force_delete": { "type": "boolean" },
      "forced": { "type": "boolean" },
      "rewrite_mode": { "type": "boolean" },
      "skip_and_oversize_id_limit_exceeded": { "type": "boolean" },
      "skipped_document_ids": { "type": "keyword", "index": false, "doc_values": false },
      "oversize_document_ids": { "type": "keyword", "index": false, "doc_values": false }
    }
  }
}
```

- 根拠: `record_type`・`status`・`source_id` は term/terms で絞るので keyword。`crawl_id` は並べ替えに使うので keyword(doc_values あり)。`started_at`・`ended_at` は並べ替え、`finish_received_at` は exists で絞るので date。ID 一覧 2 項目は設計書 7 章(K52)の指定どおり。
- 実装者は、マッピングの項目が `records.py` の `to_body()` の全キーを漏れなく含むことを突き合わせる(漏れは実機で `strict_dynamic_mapping_exception` として現れる)。

### 4.3 `jobs.json`(`loreley-jobs`。Crawler 領域で設計未決のため、Indexer が読む最小限のみ)
- Indexer は `GET /{index}/_doc/{id}` で読むだけ。ロックとメンテナンスフラグの項目だけ型を付け、その他は `dynamic: false`(Crawler 設計確定までの項目追加を妨げないため strict にしない)。

```json
{
  "settings": { "index": { "number_of_shards": 1, "number_of_replicas": 0 } },
  "mappings": {
    "dynamic": false,
    "properties": {
      "owner": { "type": "keyword" },
      "job_id": { "type": "keyword" },
      "lease_expires_at": { "type": "date" },
      "enabled": { "type": "boolean" }
    }
  }
}
```

- 文書の形(README 6 章の仮定義): ロック=ID `lock-{source_id}`、`owner`、`job_id`、`lease_expires_at`(ISO 8601)。メンテナンスフラグ=ID `maintenance`、`enabled`(bool)。今回メンテナンスは書かない(Q2 対象外)。
- 結合テスト用の最小定義で、Crawler 設計確定時に置き換える。手順書に「仮定義」であることを明記する。

## 5. 実装フェーズ

依存順。各フェーズ完了時にメインエージェントが作業記録を残し、`STATUS.md` を更新する。

### フェーズ 0: 前提確認(実装前)
- 内容: `docker --version`、`docker compose version`(v2、`up --wait`/`--wait-timeout` が使えること)、`docker info`(デーモン起動・VM メモリ)、`uv --version`、ポート 9200・8000 の空き、ホストの CPU アーキテクチャを確認。
- 成果物: 確認結果(作業記録)。
- **Docker / compose が使えない場合**: 資材の作成まではできるが、検証・結合テスト実行ができず完了条件 2 を満たせない。**`done` にせず `blocked` にしてユーザーに報告**する。選択肢は (a) Docker Desktop・colima・podman 等を導入して再開、(b) 資材の作成までで止め、実行は後日。OpenSearch を tarball で直接起動する代替は「composeを使う」要件を満たさないため採らない。推測で成功と書かない(結果記録は「未実施」)。

### フェーズ 1: OpenSearch スキーマ定義
- 成果物: 4 章の 3 ファイルと `infra/opensearch/init-indices.sh`。
- init スクリプト仕様: 同じ公式イメージ内の `curl` で動く。各インデックスについて存在確認(HEAD)→ なければ PUT(`@file`)→ `acknowledged` 確認。既存なら何もしない(冪等。`resource_already_exists_exception` は成功扱い)。失敗時は非 0 で終了し HTTP ステータスと応答本文を出す。インデックス名は環境変数(既定: `loreley-documents-000001`/エイリアス `loreley-documents`、`loreley-deletions`、`loreley-jobs`)。
- 検証: 3 つの JSON が構文として正しい(`python -m json.tool`)。`records.py` の `to_body()` 全キー、`search_document.py:55-90` の書き込み項目、search-index 4.1 との項目突き合わせ表を作業記録に載せる。`sh -n`、使えれば `shellcheck`。

### フェーズ 2: compose の作成
- 成果物: `deploy/compose/compose.yaml`、`.env.example`、`deploy/compose/README.md`(雛形)。
- **opensearch**: 公式イメージ。バージョンは `web-researcher` で調べ、最新の安定版を**パッチまでのタグで固定**(`latest` 不可)。opensearch-py 3.2.0(`apps/indexer/uv.lock`)との対応と arm64 イメージの有無を確認。環境変数: `discovery.type=single-node`、`DISABLE_SECURITY_PLUGIN=true`、`DISABLE_INSTALL_DEMO_CONFIG=true`、`OPENSEARCH_JAVA_OPTS=-Xms512m -Xmx512m`(`.env` で変更可)。ポート `127.0.0.1:9200:9200` のみ(9600 は publish しない)。名前付きボリューム。healthcheck: `curl -fsS "http://localhost:9200/_cluster/health?wait_for_status=yellow&timeout=5s"`、`start_period` 長め。
- **opensearch-init**: 同じイメージ、entrypoint を init スクリプトに上書き、`infra/opensearch` を読み取り専用 mount。`depends_on: opensearch: service_healthy`、`restart: "no"`。
- **indexer**: `build: ../../apps/indexer`。`depends_on`: opensearch は `service_healthy`、opensearch-init は `service_completed_successfully`。環境変数: `LORELEY_INDEXER_OPENSEARCH_URL=http://opensearch:9200`、`LOG_LEVEL`、`SUMMARY_ENABLED=false`。ポート `127.0.0.1:8000:8000`(0.0.0.0 への publish はしない)。`restart: unless-stopped`、`stop_grace_period: 30s`。healthcheck はイメージの HEALTHCHECK(start-period 120 秒)。
- プロジェクト名は結合テストでは専用(`loreley-it`)で動かし、開発用スタックと衝突させない。`.env.example`: OpenSearch のバージョン、ヒープ、ホスト側ポート、Indexer のログレベル(秘密値なし)。
- 検証: `docker compose -f deploy/compose/compose.yaml config` が通る。公開ポートがループバックだけであることを `config` 出力で目視確認。依存: フェーズ 1。

### フェーズ 3: 起動確認(メインエージェントが実行)
- 手順(`loreley-it`):
  1. `docker compose up -d --build --wait --wait-timeout 300`
  2. `curl 127.0.0.1:9200/_cluster/health`
  3. `GET /_mapping`(search-index はエイリアス経由、deletions、jobs)で 3 つが作られたこと
  4. `curl 127.0.0.1:8000/healthz` が 200
  5. `docker compose logs indexer`(起動時の整理が成功しているか)
  6. `docker compose up -d` 再実行で init が冪等であること
  7. `docker compose stop indexer` の所要時間が猶予内であること
  8. `down -v`
- 成果物: 作業記録に起動所要時間・バージョン・ログ抜粋・発見事項。
- **Indexer が実 OpenSearch に接続する最初の機会**。不具合・設計との食い違いが出たら、軽微なものは `apps/indexer` で修正(単体テスト併せて追加、レビュー対象に含める)。設計に関わるものは作業を止めてユーザーに報告。
- `up --wait` が one-shot の `opensearch-init`(正常終了)で失敗する場合は、`up -d` のあとスクリプトで indexer の health と init の終了コードを自前で待つ形に切り替え、理由を記録(0001 Q3 の `up --wait` からの逸脱になるので報告)。

### レビュー R1(フェーズ 1〜3 の後)— 6 章参照

### フェーズ 4: 結合テスト資材
- 成果物(`tests/integration/`):
  - `pyproject.toml`(依存は `pytest` と `httpx`。`uv.lock` も生成)
  - `compose.test.yaml`: Indexer のテスト用の値を上書き。`LORELEY_INDEXER_MAX_RAW_BYTES=65536`、`..._DELETION_BATCH_SIZE=2`、`..._SEARCH_AFTER_PAGE_SIZE=2`、`..._DELETION_POLL_INTERVAL_SECONDS=1`。本番用 `deploy/compose` には混ぜない。
  - `samples/`: `sample.txt`(UTF-8、日本語・英語)、`sample.md`、`sample.html`(タグ・script を含む)、`sample.pdf`(ASCII テキストの最小 PDF。日本語 PDF の抽出品質は未検証のため使わない)、`corrupt.pdf`(PDF ではないバイト列)。サンプルごとに期待する抽出結果の要点をコメントで残す。
  - `conftest.py`: 環境の疎通確認(スタックが無ければ `scripts/run-indexer-integration-test.sh` を使うか先に compose を起動するよう明示して失敗)、一意 ID 生成、**Crawler 役のクライアント**(ロック書込=`lock-{source_id}` を `loreley-jobs` へ直接 PUT、開始通知、バッチ登録、`last-seen`、終了通知、Status、Status のポーリング、ソース削除 1〜3。DELETE の JSON ボディは `httpx` の `request("DELETE", ..., json=...)`)、OpenSearch 検証用ヘルパ(`_refresh` してから `_count`・`_search`、ID 取得)、`document_id` の独立実装(Indexer コードは import せず、README 6 章・`test_document_id.py` の `API_EXAMPLE_VECTORS` と一致することを IT-02 で確認)。
  - テスト本体はシナリオ別ファイル(7 章)。
- コメント方針(0000 の制約): 各ファイル冒頭に目的・参照する設計書の章・扱うシナリオ ID。各テストの docstring に【何を確認するか】【前提と手順】【期待する結果とその根拠(設計書の章)】【fake では確認できず実機で確認する点】。期待値には「なぜこの値か」。手順の各ステップに 1 行の意図コメント。`assert` にはメッセージを付ける。
- TTL の扱い: 実時間で待たない。クロール A の `crawl_started_at` を現在の 2 時間前、クロール B を 1 分前、`ttl=600`。A でしか見ていない文書は期限切れ、B で見た文書は期限内になり sleep なしで決定的。待つのは削除ワーカーの走査(1 秒間隔)だけで、ポーリングのタイムアウトは 30 秒程度。
- 検証: `uv run --project tests/integration pytest --collect-only`、`ruff check`。スタックを起動して順に実行。依存: フェーズ 3。

### フェーズ 5: 実行スクリプト
- 成果物: `scripts/run-indexer-integration-test.sh`。
- 仕様: `set -euo pipefail`。事前確認(`docker`・`docker compose`・`uv` の有無、ポート 9200・8000 の空き、Linux なら `vm.max_map_count` の警告)。`docker compose -p loreley-it -f deploy/compose/compose.yaml -f tests/integration/compose.test.yaml up -d --build --wait --wait-timeout 300`(フェーズ 3 の結果に応じて変更)。`uv run --project tests/integration pytest tests/integration -v`(出力は `tee` で結果ファイルにも保存。保存先は gitignore)。`trap` で EXIT 時に、失敗時は `docker compose logs` を出力してから `down -v --remove-orphans`(`--keep` で残す指定も可)。終了コードは pytest のものを返す。
- 検証: 成功経路で 1 回。失敗経路(存在しない設定で起動失敗させる等)で `trap` の後始末と終了コードが正しいこと(終了後 `docker compose -p loreley-it ps -a` が空)。依存: フェーズ 4。

### レビュー R2(フェーズ 4・5 の後、フェーズ 6 の前)— 6 章参照

### フェーズ 6: 動作確認の実施と結果記録(メインエージェント)
- クリーンな状態からスクリプトで全シナリオを実行。**2 回連続で成功**することを確認。失敗したら原因を切り分け(テストの誤り/Indexer の不具合/スキーマの誤り/設計との食い違い)、2 章の方針で対応。
- `docs/v0.x/test-results/indexer-integration.md` を `opensearch-performance.md` の形式に合わせて作成: ヘッダ表、目的、記録のルール(実際に確認した結果のみ、未実施は「未実施」、再測定は追記)、環境(実施日、ホスト、Docker/compose バージョン、OpenSearch バージョン・イメージ、JVM ヒープ、Indexer イメージと commit SHA、実行コマンド)、シナリオ別結果表、U-31 実機確認結果表(対象外は「未実施(スコープ外)」)、発見事項、再実行手順。
- 作業記録: 実行ログの要点、発見事項、修正内容。依存: フェーズ 5、R2 指摘対応の完了。

### フェーズ 7: 手順書
- `deploy/compose/README.md`: 前提(Docker・メモリ・`vm.max_map_count`)、`.env` の作り方、起動・停止・初期化、ループバックのみ公開の理由(認証なし)、トラブルシュート(OOM、ポート衝突、init 失敗、unhealthy)、jobs マッピングが仮定義であること、OpenSearch バージョン固定方針。
- `tests/integration/README.md`: 実行方法(スクリプト、手動、特定シナリオのみ)、シナリオ一覧、設計書との対応、結果の見方、サンプルの追加方法。
- `apps/indexer/README.md` 10 章の最終文を実績に合わせて更新(軽微)。
- 検証: 手順書どおりにクリーンな状態から実行して通る。依存: フェーズ 6。

### レビュー R3(フェーズ 7 の後)とタスクレビュー — 6 章参照

## 6. レビューフェーズ

**共通事項**
- 実装担当とレビュー担当は別のエージェント。
- 比較基準: 実装フェーズ開始時点のコミット `c59fea7`。変更は未コミットの新規ファイルが中心なので、**対象はパスを列挙して指定**。途中でコミットした場合は基準 SHA を更新して明示。
- 渡す文脈: `0000-requirements-definition.md`、`0001-clarify-requirements.md`、本プラン(0002)、作成済みの作業記録。
- 指摘対応: Critical / Important は該当フェーズに戻して修正し、**同じレビュアーで再レビュー**。Suggestion / Nitpick は対応可否を判断し理由とともに作業記録に残す。「指摘なし」または Critical / Important 解消までレビューフェーズを完了としない。

| レビュー | 時点 | 担当 | 対象パス | 理由 |
| --- | --- | --- | --- | --- |
| R1 | フェーズ 3 の後 | `code-reviewer` | `infra/opensearch/**`、`deploy/compose/**`、フェーズ 3 で `apps/indexer` を直した場合はその差分 | スキーマ・compose・init は本体コードに準ずる。**認証なし Indexer とセキュリティ無効 OpenSearch の公開範囲(ループバックのみか)はアクセス制御に直結するため省略不可**。観点: ポート公開、イメージ固定、init の冪等性・エラー処理、`depends_on`/healthcheck、マッピングと `records.py` の突き合わせ。`apps/indexer` を直した場合は `test-reviewer` も追加 |
| R2 | フェーズ 5 の後 | `code-reviewer` + `test-reviewer`(並列) | `tests/integration/**`、`scripts/run-indexer-integration-test.sh`、(あれば)フェーズ 4〜5 で変えた `apps/indexer` | `test-reviewer` 観点: Q2 範囲の過不足、期待値の根拠、再現性(非決定性・時刻依存・待ち)、テスト間干渉、偽陽性、コメントが 0000 の制約を満たすか。`code-reviewer` 観点: `trap`・後始末・終了コード、DELETE の JSON ボディ、依存固定、クリーンアップ漏れ |
| R3 | フェーズ 7 の後 | `document-reviewer` | `docs/v0.x/test-results/indexer-integration.md`、`deploy/compose/README.md`、`tests/integration/README.md`、`apps/indexer/README.md`(更新箇所) | 観点: 結果記録が実際の実行ログと一致するか(未実施を成功と書いていない)、未実施が「未実施」か、手順書で再現できるか、設計書との整合 |

### タスクレビューフェーズ(最後)
- **実施する**。理由: 実装フェーズが 7 つで複数セッションにまたがる見込み、認証なしサービスの公開範囲を扱い、要件・プランからの乖離(`up --wait` の変更、マッピング案、スコープ内外の判断)を工程全体で確認する価値があるため。
- 順序: R1〜R3 完了、フェーズ 0〜7 の作業記録と `STATUS.md` 更新後。担当 `task-reviewer`(コード・テスト単体は R1〜R3 の担当で重複させない)。Critical / Important は差し戻し→再レビュー。「指摘なし」または解消済みまで完了としない。

## 7. テストシナリオ一覧(0001 Q2 の範囲)

共通: 各テストは専用の `source_id` / `crawl_id` と有効なロック文書を用意。検証は Indexer の応答だけでなく OpenSearch を直接読む(`_refresh` してから `_count` / `_search`)。

| ID | シナリオ | 何を確認するか |
| --- | --- | --- |
| IT-01 | 起動疎通・スキーマ | `/healthz` が 200。3 インデックスが存在し、検索インデックスがエイリアス経由で見え、deletions と search-index が `dynamic: strict`。Indexer が実 OpenSearch への接続と起動時の整理を終えている |
| IT-02 | `document_id` のテスト側算出 | SHA-256(`source_id` + NUL + `external_id`) のテスト側実装が README 6 章・`API_EXAMPLE_VECTORS` と一致 |
| IT-10 | 形式別登録(txt/md/html/pdf) | `ok`/`created`。`content`、`content_hash`、`text_hash`(テスト側再計算と一致)、`index_status=indexed`、`summary_status=disabled`、`last_seen_at=crawl_started_at` が保存。`content` の語句で `_search` に命中。HTML のタグ・script が本文に残らない。日時がミリ秒精度 UTC に正規化され date 型に受け入れられる |
| IT-11 | 抽出失敗 | 壊れた PDF が `ok` + `extract_failed: true`、`index_status=extract_failed`、`content`・`text_hash`・要約なし。後の `N_seen` に数えられる(IT-30) |
| IT-12 | 再登録 `unchanged` | 同内容の再登録は `unchanged` で全文書き込みなし(`_seq_no`・`indexed_at` 不変)。`last-seen` 省略の新クロールでは `last_seen_at` だけが補完 |
| IT-13 | 再登録 `updated` | 本文変更で `updated`。`content`・`text_hash` 更新、`last_seen_at` が古い値に戻らない(max 比較) |
| IT-14 | サイズ超過 `oversize` | `MAX_RAW_BYTES` 超過は文書単位 `failed`/`oversize` で索引されない。同バッチの他文書は成功。終了通知の `oversize_document_ids` に含めると `E_missing` に数えられ件数照合成立(IT-30) |
| IT-15 | ロック不所有 | 別 `owner` または期限切れリースで `failed`/`lock_not_owned`、何も書かれない。`last-seen` でも同様 |
| IT-20 | 開始通知 | 200 `running`。`deletion-{source_id}` と `deletion_result-{crawl_id}` が作られ設定スナップショットが複写される(deletions の strict マッピングに通る確認を兼ねる) |
| IT-21 | `last-seen`(部分更新) | 既存は `updated`、同値再送は `unchanged`(painless max 比較・`Instant` パース)、存在しない ID は `not_found`(404 `document_missing_exception` の応答形)。秒・マイクロ秒入力がミリ秒に正規化 |
| IT-22 | 終了通知と Status | 終了通知 202。Status に `finish_received_at`、終端状態になる。未知 `crawl_id` の Status は 404 `crawl_not_found`。未知 `crawl_id` への終了通知は 202 で Status は 404 のまま |
| IT-30 | TTL 削除(`deleted`) | A(2 時間前)で複数文書を登録、B(1 分前、`ttl=600`)で一部のみ見る(`unchanged`/`updated`/新規、`oversize`、`extract_failed` を含む)。終了通知後、B で見なかった文書だけ削除、見た文書は残る。Status は `deleted`、`enumerated_count`・`n_seen`・`e_missing`・`target_count`・`deleted_count` が設計書 9.3 の定義と一致(`denominator` は設計書の定義を確認して決める)。他ソースの期限切れ文書は消えない。A 自体の終了は対象 0 件で `deleted`(0 件) |
| IT-31 | TTL 削除の分割実行 | `DELETION_BATCH_SIZE=2`・`SEARCH_AFTER_PAGE_SIZE=2` で 5 件以上が複数バッチ・複数ページ(`search_after`、`document_id` ソート)で完了し `deleted_count` 一致 |
| IT-40 | ソース削除 1(`deletions:discard`) | 終了通知前の `running` が `discarded`(理由 `source_deleted`)になり `discarded_crawl_ids` に含まれる。再実行は空(冪等) |
| IT-41 | ソース削除 2(`DELETE .../documents`) | `deleted_count` が登録件数と一致し `_count` が 0。他ソースは残る。再実行は 0。ロック不所有は 409 `lock_not_owned` で何も消えない |
| IT-42 | ソース削除 3(`DELETE .../deletion-records`) | `deleted: true`、`deletion-*`・`deletion_result-*` が消え Status が 404。再実行は `deleted: false`(冪等) |

U-31 との対応: painless max 比較 → IT-21、`search_after` → IT-31、`delete_by_query` → IT-41、404 応答形 → IT-21・IT-22、日時形式 → IT-10・IT-21、楽観ロック(`if_seq_no`)の基本動作 → IT-12・IT-13・IT-30 の副次確認。**対象外**(「未実施(スコープ外)」と記録): 409 競合の再現、`version_conflicts` の再送抑止、`_reindex`、`retry_on_conflict` の上限、要約、シャード部分失敗。

範囲外の追加候補(承認時に判断): 割合ルールによる削除見送り(`skipped_by_ratio`)、件数照合の不一致(`validation_failed`)。既定では含めない。

## 8. テスト方針

- 層: 結合テストのみ(ホスト pytest → 127.0.0.1 の Indexer と OpenSearch)。Indexer 内部は fake の単体テストが既にあり重複させない。
- 判定は Indexer の応答と OpenSearch の実データの両方で行う。
- 非決定性対策: TTL は過去の `crawl_started_at` で作る(sleep しない)。非同期削除は間隔・上限を明示したポーリング。検索系確認の前に必ず `_refresh`。ID は一意。順序依存のテストを作らない。
- 期待値は設計書の章を根拠にコメントへ書く。実機の挙動が設計・README と違った場合、テストを実機に合わせて変えず発見事項として扱う(2 章の方針)。
- `apps/indexer` を変えた場合は既存単体テスト(`uv run pytest`・`ruff`)を再実行して通ることを確認する。

## 9. リスクと対策

| リスク | 対策 |
| --- | --- |
| OpenSearch バージョン選定 | フェーズ 2 で `web-researcher` に調べさせ、opensearch-py 3.2.0 との対応と arm64 の有無を確認、パッチまでのタグで固定。理由と実バージョンを結果に記録。問題が出たら 1 つ前の系列に戻す |
| メモリ不足(OOM) | ヒープ 512m 既定、`.env` で変更可。フェーズ 0 で VM メモリ確認。症状(exit 137)と対処を README に |
| `vm.max_map_count`(Linux) | single-node でブートストラップチェックは強制されないが、README に `sysctl -w vm.max_map_count=262144` を記載、スクリプトで警告。Docker Desktop(Mac)は不要 |
| 起動待ち | healthcheck の `start_period`、`--wait-timeout 300`、Indexer の 120 秒 start-period。`depends_on` で init 完了後に Indexer 起動 |
| `up --wait` が one-shot init で失敗 | フェーズ 3 で実機確認。失敗時は自前の待機に切り替え、理由を記録・報告 |
| TTL の待ち時間 | 過去の `crawl_started_at` で作るので実時間待ちなし。残るのは削除ワーカー走査(1 秒間隔)のみ |
| ホストと Docker VM の時計ずれ | A を 2 時間前、B を 1 分前、`ttl=600` で数分のずれに耐える余裕 |
| Indexer が実 OpenSearch で初めて動く | 想定内。2 章の方針で対応。作業増に備え余裕を見る |
| スキーマの誤り(strict の定義漏れ、型不一致) | フェーズ 1 で突き合わせ、フェーズ 3 で実書き込み確認。原因が設計書 4.1 の JSON の欠落なら設計との食い違いとして報告 |
| 認証なし Indexer とセキュリティ無効 OpenSearch の公開 | ループバックのみ publish。R1 で `code-reviewer` が必ず確認。README に理由 |
| イメージビルドの外部ネットワーク依存(ベースイメージ、PyPI、Apple Silicon でのダイジェストのアーキテクチャ差) | フェーズ 0 でネットワーク確認。失敗時は原因を記録・報告 |
| ポート衝突 | スクリプトの事前確認で検出して中止。ホスト側ポートは `.env` で変更可 |
| テストの偽陽性・干渉 | 一意 ID、OpenSearch 直接確認、2 回連続実行(フェーズ 6)、R2 の `test-reviewer` |
| DELETE に JSON ボディが必要 | `httpx` の `request("DELETE", ...)`。フェーズ 4 の最初に確認 |
| PDF サンプルが抽出できない | pypdf で抽出できる ASCII 最小 PDF を用意し、フェーズ 4 で IT-10 を先に通して確認 |

**ロールバック**: 追加物は新規ファイル中心なので削除で戻る。実行中スタックは `docker compose -p loreley-it down -v --remove-orphans`。`apps/indexer` の修正が入った場合はその差分のみ個別に戻す。

## 10. 未解決事項

- OpenSearch の具体的バージョン(フェーズ 2 で決定・記録)、`denominator` の期待値(設計書 9.3 の定義を確認)、`up --wait` の挙動(フェーズ 3 で確認)。
- 実機で設計との食い違いが見つかった場合: 設計書の改版は本タスクでは行わない。ユーザー判断。
- CI 組み込みは対象外。

## 11. 承認時に確認したい論点

1. マッピング案(4 章): deletions は `dynamic: strict`、jobs は最小項目のみ `dynamic: false`
2. 検索インデックスのエイリアス: 実体 `loreley-documents-000001` + エイリアス `loreley-documents`(問題が出たら実名 `loreley-documents` に切替)
3. テスト用上書き compose `tests/integration/compose.test.yaml`: `deploy/compose` には混ぜない
4. シナリオ追加: `skipped_by_ratio` と `validation_failed` を含めるか(既定は含めない)
5. Docker が使えない場合の扱い: `blocked` にしてユーザーに報告、成功とは書かない
