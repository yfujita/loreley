# 0002 作業プラン: Admin API(EP-01〜14)の実装

日付: 2026-11-23
状態: **ユーザー承認待ち**(planner が作成。2.2 の前提は承認をもって確定する)

## 1. 目的とゴール

`apps/api` に Admin API(サブアプリ `/api/admin/v1`、EP-01〜14)を実装する。正本は設計書の A(`api-base-design-v0.1.md`)、B(`admin-api-v0.1.md`)、C(`admin-api-architecture-v0.1.md`)、D(`admin-api-module-structure-v0.1.md`)。D 4.12(b) の「admin 実装時に追加するもの」のうち、2.1 で範囲外としたものは除く。

### 受け入れ基準(0001 の完了条件の解釈 ①〜④ を具体化したもの)

- [ ] ① EP-01〜14 が B の仕様どおりに応答する(単体テスト・アプリ全体テストで確認し、手動スモークで実機でも確認する)
- [ ] ② `cd apps/api` で `uv run pytest`、`uv run ruff check`、`uv run ruff format --check`、`uv lock --check` がすべて通る
- [ ] ③ `tests/architecture` を D 6章のとおりに拡張し、すべて通る。対象は許可表の admin・infrastructure の行、R4・R5(所有者と `urllib3.exceptions` のファイル単位の例外)、R6、R8(`test_read_only_rules.py`)、R9 の `Depends` の検査
- [ ] ④ `admin/openapi_export.py` が外部に接続せずに OpenAPI JSON を書き出せる。`OPENAPI_ENABLED=true` のときだけ `/api/admin/v1/openapi.json` が出て、既定では JSON の 404 になる
- [ ] Admin API が OpenSearch・Store 層に書き込まない(R8 の AST 検査と許可リスト方式の偽物で確認)。Crawler へは固定の 6 経路だけを送る
- [ ] `apps/api/README.md` を更新している(環境変数の一覧(C 7.2)、HO-40・HO-41 の注意書き、冒頭の古い記述(「実装は D と一部異なる」)の修正、Docker 起動例への必須環境変数の追記)
- [ ] 設計書(A〜D ほか)は変更していない。食い違いは作業記録で申し送っている

## 2. 確定事項・前提

### 2.1 確定事項(0001 から引き継ぐ。再確認しない)

- 範囲: EP-01〜14 の全 14 本。フェーズの順は「共通部品 → 読み取り系 → 書き込み系(Crawler 中継)→ EP-13」。各フェーズの終わりにテストが通る状態を保つ
- 含めるもの: `admin/openapi_export.py`、`OPENAPI_ENABLED`、README の更新、EP-13 に要る `WEB_DIST_DIR` の設定と `infrastructure/probes/web_dist.py`
- 含めないもの: `/admin/` の静的配信と SPA フォールバック(`server/static_web.py`)、compose への api サービス追加(HO-35)、Dockerfile の Node ステージ(HO-36)、フロントエンド(View)
- 検証: 単体テスト、アーキテクチャテスト、手動スモーク(実 OpenSearch 9200・実 Crawler 8001)。自動の結合テストは作らない
- 依存の追加は `opensearch-py`・`urllib3`・`anyio`。Crawler クライアントは urllib3 で、接続 3 秒・応答 60 秒、再送なし
- Indexer とのやり取りは EP-13 の `GET /healthz` だけ

### 2.2 前提(本プランで置く。承認をもって確定)

1. **パッケージパスの読み替え**: 要件の `apps/api/src/admin/` は、実在する `apps/api/src/loreley_api/admin/` と読む。組み込みに必要な `main.py`・`config.py`・`common/` の残り・`infrastructure/`・`tests/`・`pyproject.toml`・`uv.lock`・`README.md` も変更対象に含める(D 4.12(b))
2. **ブランチ**: `main`(HEAD `cedcd56`)から `feature/implement-admin-api` を切る。開始時の SHA を最初の作業記録に残し、レビューの比較基準にする
3. **コミットと PR**: フェーズごとに 1 コミット以上、レビュー指摘への対応は別コミット。PR は前タスク(PR #16)に倣い最後に 1 本。2 本(P1〜P4 の読み取り系、P5〜P7)に分けたい場合は、承認時に指示してもらえればレビューの区切り R-B で分ける
4. **設計書との食い違い**: 設計書は直接直さない。作業記録の「申し送り」に、項目・設計書の箇所・実装の判断を残す(追従改訂は別タスク)。B 9.2 と実 Crawler の応答が違う場合も同じ
5. **ファイル名**: D 3章の表を目安にする。追加・改名してよいが、モジュールの境界・入口・依存は変えない(AAM-P-25)
6. **実装時に決める事項**(既定で決めて作業記録に残す): `timeout_graceful_shutdown` は指定しない(AAM-P-28)/ `BlockingRunner.run_all` の API の細部(AAM-U-8)/ 422 の `reason` に `exclusive` と Admin 固有の値を足す(AAM-U-3)/ `ClientDisconnect` の挙動確認とログ水準(D 4.12(c))/ OpenAPI の `servers`・`paths`(BAPI-U-2 の残り)/ anyio の版と `abandon_on_cancel` の挙動(AAM-U-1)
7. **OpenAPI JSON の書き出し**: `python -m loreley_api.admin.openapi_export <出力パス>`(出力先は引数)。書き出した JSON はコミットしない(置き場はフロントエンドのタスクで決める。FARC-P-6・FARC-U-5)
8. **実装時確認事項**: AAPI-U・AAA-U・AAM-U は、手動スモークや実装中に確認できたものだけ作業記録に残す
9. **Crawler API・Indexer API の確認**: P5 で `apps/crawler/src/loreley_crawler/api/` を読み B 9.2 の写像表と突き合わせる。P6 で `apps/indexer/src/loreley_indexer/api/routes.py` の `GET /healthz` を確認する。差分は作業記録に残す。Crawler・Indexer のコードは変更しない
10. **作業記録と STATUS.md**: 各フェーズ完了時にメインエージェントが `NNNN-*.md` を作成し STATUS.md を更新する。サブエージェントは書かない

## 3. 影響範囲

基準は `apps/api/`。

既存の主な変更点:
- `src/loreley_api/main.py`(`build_app` に admin のマウントと lifespan。`main()` を `load_config()` に)
- `src/loreley_api/config.py`(C 7.2 の環境変数、起動時検証、`ApiConfig`・`load_config()`)
- `src/loreley_api/common/logging_setup.py`(`RESTRICTED_LOGGER_NAMES`)
- `tests/architecture/dependency_rules.py`(`FEATURE_PACKAGES` に admin、infrastructure の分類、許可表、`EXTERNAL_LIBRARY_OWNERS`、`urllib3.exceptions` のファイル単位の例外)
- `tests/architecture/test_http_rules.py`(`Depends` 関数が `async def` であることの検査)
- `tests/test_config.py`、`tests/test_main.py`、`pyproject.toml`、`uv.lock`、`README.md`

新規:
- `common/` に `clock.py`・`timestamps.py`・`results.py`・`concurrency.py`・`urls.py`・`probe_outcome.py`・`http/body.py`
- `admin/` 一式(`app.py`・`dependencies.py`・`settings.py`・`openapi_export.py`、配下に `base/`・`schemas/`・`routers/`・`services/`・`derivation/`・`crawler_mapping/`・`failures/`)
- `infrastructure/{opensearch,crawler_client,probes}/` 一式
- `tests/` に `fakes/`・`contract/test_schema_contract.py`・`architecture/test_read_only_rules.py`・`common/`・`infrastructure/`・`admin/{derivation,crawler_mapping,failures,services,routers}/`・`server/` の追加分

参照のみ(変更しない): `infra/opensearch/schema/*.json`、`apps/crawler/`、`apps/indexer/`、`deploy/compose/compose.yaml`、`tests/integration/crawler/compose.test.yaml`、`apps/api/Dockerfile`

## 4. 実装フェーズ

全フェーズ共通:
- 実装は `code-implementer`。依頼文にタスク名、読むファイル(STATUS.md・0000・0001・本プラン・D の該当節・B/C の該当節)、範囲、禁止事項(作業記録・STATUS.md・設計書を書かない)、報告形式を含める
- 共通の完了条件: `uv run pytest`・`ruff check`・`ruff format --check`・`uv lock --check` が通る。メインエージェントが再実行して作業記録に残す
- テストは C 11章の観点と D 7.3 の配置表に従う

### P0: 準備(メインエージェント)
- `git switch -c feature/implement-admin-api`。開始 SHA を記録。基準として `uv run pytest`(310 passed の想定)
- 完了条件: ブランチと基準結果が作業記録にある

### P1: 共通部品と admin の骨格
- 依存: P0
- 内容:
  - `pyproject.toml` に `opensearch-py`・`urllib3`・`anyio` を足し `uv lock`(版は `apps/crawler` に揃える)
  - `common` の残り(D 4.11)。`BlockingRunner` は `run` と、期限・放棄つき `run_all`(AAM-P-27)
  - `config.py`: C 7.2 の全変数と 7.3 の検証。値を出さない `ConfigError`。各モジュールの設定 dataclass を `ApiConfig` に詰める
  - `logging_setup` にロガー制限を追加
  - `admin/base`(code・理由コード・`AdminApiError`・固定上限)、`admin/failures`(`reasons`・`unavailable`。AAM-P-29)
  - `admin/app.py` の `create_admin_app(deps)`(ルーターは空。`docs_url`・`redoc_url`・`redirect_slashes`・`openapi_url` を明示)
  - `admin/dependencies.py`、`routers/request_input.py`(すべて `async def`)、`common/http/body.py`(1 MiB 上限)
  - `main.py`: `SubAppMount("/api/admin/v1", …)` と外側 lifespan でクライアントを閉じる処理(最小形)
  - `tests/fakes` の時計・`InlineRunner`・`behavior`
  - architecture 拡張(admin・infrastructure の行、R4・R5・R6・R12、`Depends` 検査)
- 完了条件: 設定の欠落・不正は値を出さずに起動失敗(`test_config.py` が C 11章 13 を網羅)/ `/api/admin/v1/<未知>` が JSON 404 + `no-store` / `concurrency` のテスト(上限・区分分離・期限放棄)/ architecture 自己テスト(正例・負例)

### P2: OpenSearch 読み取り層
- 依存: P1
- 内容: `infrastructure/opensearch` の `ports`・`readonly_client`(許可リスト 7 メソッド。`**kwargs` 素通し禁止)・`connection`・`queries`(R-1〜R-12)・`failure`・各 Reader(Sources・Jobs・Deletions・SearchIndex・Counts・Cluster)/ `tests/fakes/fake_opensearch_client.py` / `tests/infrastructure/opensearch/`(クエリ本文、部分失敗、例外分類)/ `contract/test_schema_contract.py` / `test_read_only_rules.py` の OpenSearch 側(R8 (a)〜(c))。`health_probe` は P6
- 完了条件: Reader が例外を漏らさず `Ok`・`Failed` を返す。R8 の負例(合成ソース)が検出される

### P3: 読み取り系 EP その 1(EP-09・10・12・14)と導出
- 依存: P2
- 内容: `admin/derivation`(D 4.6、純粋関数)/ `schemas/common.py` と該当 DTO / `services/lock_view`・`stalled_check`・`job_queries`・`cluster_overview`・`meta` / `routers/jobs.py`・`opensearch.py`・`meta.py` / `tests/fakes/in_memory_readers.py` / テスト(derivation は表駆動・固定時刻、services は障害注入、routers は `TestClient`)
- 完了条件: C 11章 5・6・7・16 の該当部分 / ページング窓 10,000 の境界(ちょうど 10,000 は通り 10,001 は 400 `range`)/ EP-10 の 404、EP-12 の切り詰めと正規化

### P4: 読み取り系 EP その 2(EP-01・02・11)
- 依存: P3
- 内容: `services/source_catalog`・`document_review`、`routers/sources.py`(GET のみ)・`documents.py`、該当 DTO(行の `unavailable`)
- 完了条件: 行ごとの成否を区別(C 11章 6)/ EP-01・09 の最上位 `unavailable` が常に `{}` / EP-11 の `existence` と `tab_counts` / `malformed`

### P5: 書き込み系(Crawler 中継。EP-03〜08)
- 依存: P4
- 内容:
  - まず Crawler の実 API と B 9.2 を突き合わせ、差分を報告に含める
  - `infrastructure/crawler_client` 一式(固定 6 経路、`%2E` を含む全文字エンコード、例外分類、`config_invalid` の分解、本文 1 MiB 上限、再送なし、リダイレクト非追従)
  - `admin/crawler_mapping`(`table` は B 9.2 をデータとして持つ。`translate` は EP-07 の 404 写像を含む)
  - `services/source_commands`・`crawl_commands`、`routers/sources.py` に POST・PUT、`crawl_operations.py`
  - `tests/fakes/local_http_server.py`・`fake_crawler_client.py`、`test_read_only_rules.py` の Crawler 側(R8 (d))
- 完了条件: C 11章 1〜4(写像表の表駆動、障害別、受信回数 1 回、生リクエスト行のパス、`config_invalid` のベクタ)/ 409 付随情報の取得失敗でもステータスと `existing_job` が変わらない / 本文なし POST が `Origin` を問わず処理される現状の記録(C 11章 11(c))

### P6: EP-13(ダッシュボード)
- 依存: P5(技術的依存は P1・P2 のみだが、順序は確定事項に従う)
- 内容: `infrastructure/probes`(`http_probe`・`classification`・`web_dist`・`config`)/ `infrastructure/opensearch/health_probe.py`(`urllib3.exceptions` import の例外ファイル)/ `services/dashboard`(`run_all`、期限=確認タイムアウト+1 秒、固定順 8 件)/ `routers/dashboard.py`、`tests/fakes/fake_probes.py` / `test_read_only_rules.py` のプローブ側(R8 (e)。GET のみ)/ Indexer `GET /healthz` の確認(2.2-9)
- 完了条件: C 11章 10・14(1 件が遅くても期限内に応答、`not_configured`、確認先が環境変数以外から決まらない)/ `WebDistProbe` だけはハンドラから直接呼ぶ(R9 の例外)

### P7: OpenAPI・README・仕上げ・手動スモーク
- 依存: P6
- 内容: `OPENAPI_ENABLED`(サブアプリ側で公開)/ 共通エラースキーマ 400 の宣言と 422 の除去(D 4.12(c))/ `operationId` とタグ 6 種(AAM-P-4)/ `openapi_export.py` とそのテスト(外部接続なし)/ `server/` の追加テスト(`OPENAPI_ENABLED`、Crawler 遅延でも他が応答)/ README 更新 / Docker 確認(`docker build -t loreley-api apps/api` 成功、必須環境変数なしでは値を出さず起動失敗。他のコンテナは止めず、後始末は自分で作ったものだけ)/ 手動スモーク(4.1)
- 完了条件: 受け入れ基準をすべて満たし、スモーク結果(確認できた AAPI-U・AAA-U・AAM-U を含む)が作業記録にある

### 4.1 手動スモークの手順(P7。メインエージェントが実施)

- **変更操作の可否**: 可。ただし対象は、本手順で起動する専用 compose プロジェクト `loreley-admin-smoke` と、その一時データ(一時ディレクトリの文書、登録したテスト用データソース)だけ。開発用スタック・`loreley-it`・他プロジェクトのコンテナには触れない(プラン承認で許可を得る)
- **使用ポート**: 9200(OpenSearch)、8000(Indexer)、8001(Crawler)、8080(api)。8080 使用中なら `LORELEY_API_PORT` を変える

1. 事前確認: 9200・8000・8001・8080 の占有を `lsof -nP -iTCP:<port> -sTCP:LISTEN` と `docker ps --filter publish=<port>` で調べる。**9200 を別プロジェクト(Fess など)が使っていたら止めずにユーザーに報告し判断を待つ**。`loreley-admin-smoke` のコンテナ/ボリュームが残っていたら中止して報告
2. 文書ディレクトリ: `mktemp -d` + `chmod 755`。通常の `.md` 数件、70,000 バイト超のファイル(oversize。`MAX_RAW_BYTES` は 64 KiB)、対象外拡張子(skipped の想定)
3. スタック起動:
   ```
   CRAWLER_DOCUMENTS_DIR=<dir> OPENSEARCH_HOST_PORT=9200 INDEXER_HOST_PORT=8000 CRAWLER_HOST_PORT=8001 \
   docker compose -p loreley-admin-smoke -f deploy/compose/compose.yaml -f tests/integration/crawler/compose.test.yaml \
     up -d --build opensearch opensearch-init indexer crawler
   ```
   `--wait` は使わず、`docker compose ps` で healthy を待つ
4. api 起動(`apps/api`):
   ```
   LORELEY_API_OPENSEARCH_URL=http://127.0.0.1:9200 LORELEY_API_CRAWLER_URL=http://127.0.0.1:8001 \
   LORELEY_API_INDEXER_URL=http://127.0.0.1:8000 LORELEY_API_CRON_TIMEZONE=Asia/Tokyo \
   LORELEY_API_WEB_DIST_DIR=<index.html を置いた一時ディレクトリ> LORELEY_API_OPENAPI_ENABLED=true \
   uv run python -m loreley_api.main
   ```
5. curl で確認する EP(ベース `http://127.0.0.1:8080/api/admin/v1`): EP-14(`cron_timezone`・`dashboards_url=null`)/ EP-13(crawler・indexer・opensearch・api・web が normal、任意の 3 つは `not_configured`)/ EP-12 / EP-03(`connector_config.root` は `/data/documents`。不正設定は `config_invalid` 400)/ EP-01・02(`lock_state`)/ EP-04 / EP-06(連続送信で 409 `lock_held` と `existing_job`)/ EP-09・10(`registration`・`stalled`)/ EP-11(skipped・oversize・extract_failed・summary_pending)/ EP-07(存在しない・`.` を含む `job_id` で 404 `job_not_found`、AAA-U-4)/ EP-08 / EP-05(削除ジョブ → EP-10 の `deletion.*`)/ 障害系(`docker compose -p loreley-admin-smoke stop crawler` 後に EP-06 が 503 `crawler_unreachable`、EP-13 の crawler が abnormal、EP-01 は影響なし。確認後 `start`)/ OpenAPI(`/api/admin/v1/openapi.json` が出る。`OPENAPI_ENABLED` を外すと 404)
6. ログ: アクセスログが 1 リクエスト 1 行でテンプレート表記。ID・本文・`connector_config` が出ていない
7. 後始末: api 停止 / `docker compose -p loreley-admin-smoke -f deploy/compose/compose.yaml -f tests/integration/crawler/compose.test.yaml down -v --remove-orphans` / 一時ディレクトリ削除。自分が作ったものだけ

## 5. レビューフェーズ

- **方針**: フェーズごとではなく 3 つの区切り(R-A・R-B・R-C)。理由: 最後にまとめると差分が数十ファイルで見落としが増え、7 回全部だと重い。データ削除(EP-05、`force_delete`、ロック解放)を中継するので `code-reviewer` は省略しない
- 各区切りで `code-reviewer` と `test-reviewer` を**並列**に実施

| 区切り | 時点 | 対象(比較基準) | 重点 |
| --- | --- | --- | --- |
| R-A | P2 完了後 | P0 の開始 SHA から P2 完了コミットまで | 読み取り専用の保証(R8)、依存ルール、設定検証と秘密非出力、`BlockingRunner` の上限と放棄、Reader の部分失敗 |
| R-B | P4 完了後 | R-A 完了(指摘対応含む)コミットから P4 完了まで | B の DTO・`unavailable` の行への帰属、導出の正しさ、ページング、C 11章 5〜7・16 |
| R-C | P7 完了後 | R-B 完了コミットから P7 完了まで(必要なら開始 SHA からの全体も参照) | Crawler 写像表と B 9.2 の一致、6 経路とエンコード、障害別挙動、EP-13 の期限、OpenAPI(400 宣言・422 除去)、README の正確さ(HO-40・41) |

- **渡す文脈**: タスク名、0000・0001・本プラン・該当フェーズの作業記録、対象ファイル一覧、比較基準 SHA、設計書 A・B・C・D の該当章
- **省略**: `web-ui-reviewer`(Web UI 変更なし)、`document-reviewer`(設計書を変更しない。README は R-C の code-reviewer が確認)

## 6. レビュー指摘への対応

- Critical / Important: 修正し、共通検証をやり直し、同じレビュアーで再レビュー。「指摘なし」か「解消済み」になるまで区切りを完了にせず次へ進まない
- Suggestion / Nitpick: 対応可否を判断し理由を作業記録に残す
- 修正は `code-implementer`(レビュアーと別)。指摘対応ごとに作業記録と STATUS.md を更新

## 7. タスクレビューフェーズ

- **実施する**。理由: 7 フェーズで複数セッションにまたがり、データ削除を中継する高リスク変更を含み、設計書との食い違いの申し送りの妥当性確認が要るため
- R-C 完了(指摘対応と作業記録を含む)後に `task-reviewer`。渡す文脈: `agent_tasks/20261123_implement_admin_api/` 配下すべてと、開始 SHA から HEAD までの差分
- 観点: 要件・0001・本プランと実変更・作業記録の突き合わせ / 範囲外(静的配信・compose・Dockerfile・View)の混入なし / 設計書食い違い・実装時確認事項の申し送り漏れ / スモーク記録 / 完了チェックリスト
- Critical / Important は差し戻して修正し再レビュー。「指摘なし」か「解消済み」になってから PR を作る

## 8. テスト方針

- 外部システムなしの単体テストとアプリ全体テスト(`TestClient`、httpx2)が主体。偽物は D 7.2 の水準
- C 11章の 16 観点を D 7.3 の配置表どおりに置き、各フェーズの作業記録に満たした観点を書く
- 秘密値・入力値はセンチネルで確認し、応答本文と `caplog` の両方に出ないこと
- アーキテクチャテストは実ソース検査と合成ソースの自己テスト(負例が空振りしない)の両方
- 実機確認は手動スモーク(4.1)のみ。クエリの意味の正しさ(AAA-U-1〜3)はスモークで分かる範囲に限る

## 9. リスクと対策

| リスク | 対策 |
| --- | --- |
| 実 Crawler の応答が B 9.2 と違う | P5 の最初にコードと突き合わせ、申し送る。実物に合わせるか 502 にするかを作業記録で判断。重大な差はユーザーに報告 |
| 偽物はクエリの意味を実行しないため集計・並べ替えの誤りが残る(AAM-U-5) | 契約テストと手動スモークで部分的に補い、残りは未解決として申し送る |
| 9200 を別プロジェクトの Fess が使っている | スモーク前に確認し、使われていれば止めずユーザー判断を待つ。他の検証は外部非依存で進行可 |
| anyio・FastAPI の版による挙動差 | テストで固定し、確認した版を作業記録に残す |
| 規模が大きくセッションをまたぐ | フェーズを小さくし、作業記録と STATUS.md で引き継ぐ。`code-implementer` は 1 フェーズずつ |
| 必須環境変数増で既存の Docker 起動例が動かない | P7 で README の例を更新し、起動失敗時に値が出ないことを確認 |
| ロールバック | 変更は `apps/api/` とブランチ内のみ。スモーク環境は `down -v` と一時ディレクトリ削除で戻る |

## 10. 未解決事項

- PR を 1 本にするか 2 本に分けるか(既定 1 本)
- AAM-U-1・3・7・8、BAPI-U-2 の残り、`ClientDisconnect`: 実装時に確認して作業記録に残す
- AAA-U-1〜4・7: スモークで分かった範囲のみ記録し、残りは結合テストのタスクへ申し送る
- 設計書の追従改訂(食い違いがあれば別タスク)
