# 0020 P9: Dockerfile・README・最終検証とそのレビュー

日付: 2026-11-14 / 実施: code-implementer、code-reviewer(Dockerfile)、document-reviewer(README)/ 記録・再検証: メインエージェント
フェーズ開始時点の HEAD: `061dc7b196f67a689e0d834eb676ce356d6cdb34`(`apps/crawler/` は未コミット)

## 1. 実装内容(`apps/crawler/`)

- `Dockerfile`(新規): `apps/indexer/Dockerfile` に倣う。マルチステージ、ベースイメージ(`PYTHON_IMAGE`)・`UV_VERSION=0.13.7` は Indexer と完全に同一、`uv sync --locked --no-dev --no-install-project`、`compileall`、非 root(`crawler`、uid/gid 10001、ホームなし、nologin)、`ENV LORELEY_CRAWLER_HTTP_HOST=0.0.0.0`(認証のない HTTP API を外に公開しない旨のコメント)、`EXPOSE 8001`、`CMD ["python","-m","loreley_crawler.main"]`(単一プロセス)。`HEALTHCHECK` は Indexer と同形(urllib、`127.0.0.1`、プロキシ無効、2xx 以外は unhealthy、ポートは `LORELEY_CRAWLER_HTTP_PORT` に追従)、interval 15s・timeout 5s・retries 3・**`--start-period=180s`(仮値。実測ではない)**。FS Connector の対象ディレクトリは実行時に `:ro` マウントする前提で、uid/gid 10001 が読める権限が要る旨をコメントに。停止の時間予算(uvicorn graceful 10秒+join 5秒×2+Scheduler retrier 約3秒。`stop_grace_period` は30秒以上が目安)と `STOPSIGNAL` は既定の SIGTERM のまま・init 不要を `CMD` の直前に
- `README.md`(新規): 10章構成(概要・構成・起動方法・設定(環境変数64項目)・API(+最初の一歩)・運用・テスト方針(+Linux Docker 手順)・fake だけでは検証できないこと(持ち越し)・前提とスコープ外・既知の限界と運用に影響する未承認の挙動)
- `.dockerignore` は既存(Indexer と同形)を確認し変更なし。`src`・`tests` は変更なし

**`--start-period=180s` の根拠(仮値)**: 回復中は接続自体できない。OpenSearch の1リクエストは最悪約93秒(30秒×3試行+待ち約3秒。opensearch-py の自動再送は `max_retries=0`、リトライは Crawler の `Retrier` のみ)。回復は複数リクエストなので、最悪のリクエスト約2回分(約186秒)に近い180秒とした(Indexer の120秒より長い)。回復が失敗すればプロセスが終了して再起動に任せるので、猶予は「遅いが成功する回復」を待てる長さでよい

## 2. 検証結果

### 実装担当の報告とメインの独立確認

| 項目 | 結果 |
| --- | --- |
| `uv run pytest -q`(3回連続) | 3249 passed, 3 skipped(メインも再実行して一致。skip は macOS 固有の3件) |
| `uv run ruff check`・`ruff format --check`・`uv lock --check` | 成功(277 files already formatted、39 packages。メインも再実行) |
| `docker build -t <tag> apps/crawler` | **成功**(メインも独立にビルド) |
| (i) 必須設定なしで `docker run` | 終了コード1、`invalid settings: LORELEY_CRAWLER_OWNER: missing; ...`(環境変数名と種別のみ。メインも確認) |
| (ii-a) `INDEXER_MAX_RAW_BYTES=1000` | 終了コード1、`startup consistency check failed: max_raw_bytes=20971520 exceeds MAX_RAW_BYTES=1000` |
| (ii-b) `SOURCES_INDEX_NAME` と `JOBS_INDEX_NAME` が同じ | 終了コード1、`startup consistency check failed: sources_index_name and jobs_index_name must differ` |
| (iii) 到達不能な OpenSearch(`127.0.0.1:1`、パスワード設定) | 終了コード1、`StoreUnavailableError: connection_error`、HTTP を開かない(`starting the HTTP server` が出ない)、パスワードは出力に0件 |
| (iv) 実行ユーザー | `uid=10001(crawler)`、`docker inspect` で `User=crawler`・`ExposedPorts 8001/tcp`・Healthcheck(15s/5s/StartPeriod 180s/retries 3)(メインも確認) |
| (v) `import loreley_crawler.main` | ok。dev 依存の pytest はイメージに入っていない |
| (d) Linux(Docker `python:3.12.16-slim-bookworm`、`-e LORELEY_REQUIRE_LINUX_NAMES=1`、`:ro` マウント+コンテナ内コピー+`uv sync --locked`) | **非 root: 3255 passed・skip 0**(macOS の skip 3件も Linux で通る)、root: 3250 passed・5 skipped(権限エラーの5件) |

後始末: 検証用のイメージ・コンテナは削除済み(メインが確認: `crawler` を含むイメージ0件、コンテナはユーザーの既存の `fess-opensearch`・`opensearch-opensearch-1` のみ)。ユーザーの既存の OpenSearch(`127.0.0.1:9200`)には接続していない。

### Dockerfile のレビュー(code-reviewer。実機確認つき): 軽微な修正で可(Critical・Important なし)

Indexer の Dockerfile との diff で、ベースイメージ・uv・ENV・`uv sync`・`compileall`・`groupadd`/`useradd` が一致。実機で確認: 実行ユーザー・pyc(124個、`python -v` で「pyc matches source」)・`--read-only --cap-drop ALL --security-opt no-new-privileges` でも起動・イメージに tests・README・.git・uv が入らない・`HEALTHCHECK`(200 は exit 0、`HTTP_PROXY` を設定しても 0、503・302 は非0、ポートに追従)・**PID 1 の停止**: 最小限の偽 OpenSearch(別コンテナ、検証後に削除)を立てて起動し、回復完了→uvicorn 開始→`healthy`、`docker stop` は0.8秒、ログ `Shutting down` → `Finished server process [1]` → `the crawler stopped`、終了コード0(0019 §1 の再送出対策は PID 1 でも効く)。指摘: Suggestion(`:ro` マウントのコメントに uid 10001 の読み取り権限の注意)、Nitpick(`--start-period` の根拠文が数字と厳密に合わない、「HTTP 200 以外」は「2xx 以外」、停止コメントの位置と `STOPSIGNAL`・init の記載)→ **すべて対応**

### README のレビュー(document-reviewer。環境変数の機械照合つき): 軽微な修正で可(事実誤りなし)

環境変数の表は `Settings` の64項目すべてと名前・既定値が一致(漏れも余分もない)。API・起動順・停止・メンテナンスフラグ・モジュール構成・Linux テスト手順も実機で一致。持ち越し一覧(8章)は各作業記録の持ち越しを網羅。Important 5件と対応:

| 指摘 | 対応 |
| --- | --- |
| 案・未決が確定のように読める(「設計書の多くは案」、停止の「設計どおり」、メンテナンス手順) | 冒頭に「設計書の位置づけ」(版全体がユーザー承認前、確定 `-K-` 以外は案・未決、decisions 4章の10件が未回答、ID 接頭辞の凡例)。§6 の停止・メンテナンスフラグの冒頭に「案(CM-U-4・CA-U-3・CA-U-17。ユーザー判断待ち)」。「設計どおり」→「案(CM-U-4)のとおり」。`/healthz` は「置くこと自体はユーザー確定(CAPI-K-9)、パス・応答の形は案」 |
| §9「実 OpenSearch でのジョブ・ロックの書き込みは動かない」は不正確 | `infra/opensearch/schema/jobs.json`・`init-indices.sh` を実際に読んで書き直し: `jobs.json` は `dynamic:false` で4項目(`owner`・`job_id`・`lease_expires_at`・`enabled`)だけなので、書き込みと ID 指定の操作は受理されるが、`record_type`・`status`・`queued_at` などでの検索・絞り込み・並べ替え(Job Runner の `queued` 検出、回復での `running` 一覧、Scheduler の起点など)が動かない(実機は未確認と明記)。`loreley-sources` の索引は `init-indices.sh` にも `schema/` にもなく、書き込むと自動作成され動的マッピングで型が arch 3.1 の案と違う懸念 |
| PID 1 の SIGTERM の確認範囲が §6 と §8 で食い違う | §6=「PID 1 の Linux コンテナでも終了コード0(fake バックエンド・実 uvicorn で確認済み)」、§8=未確認の範囲(実 OpenSearch・実 Indexer と実行中ジョブがある状態での `docker stop` の所要時間・SIGKILL との関係) |
| 作業記録への参照先が存在しない | `0021-final-summary.md` を番号つきで参照(本記録と同時に作成) |
| メンテナンス手順の「確認」に実行手段がない | ロックの有無・実行中ジョブ一覧の curl 例(`<OpenSearch の URL>`・`<JOBS_INDEX_NAME>` に置き換え。一覧は `jobs.json` 拡張前は検索できない旨の警告つき) |

Suggestion も対応: 用語統一(Crawler の HTTP API と製品の Admin API を区別)、概要末尾に現在のステータス、`--start-period` の上書き方法、API 表の補足(取り消しの対象は `crawl` のみ・ロック解放は実行中でないロックのみ)、停止の定数が環境変数でないこと、マウント権限(uid 10001)、`POST /sources` の例(`TestClient` で実際の `file_system` レジストリを入れて 201・再送200・相対パスの `root` が400 `config_invalid`・`crawl-jobs` が202を確認)と定期起動の有効化方法、§10「既知の限界・運用に影響する未承認の挙動」を新設。Nitpick(章番号参照・違反メッセージの形・`:ro` と `pip install uv` のネットワーク・ID 接頭辞の凡例)も対応

**README の再レビューは省略**した。理由: 指摘どおりの記述修正であり、メインが ruff・format・docker 残骸・README の参照先を確認済み。README の最終確認はタスクレビュー(task-reviewer)に含める。

## 3. 未対応事項

- **`healthy` 化の確認(実 OpenSearch・実 Indexer を使うもの)は Integration Test(スコープ外)に持ち越し**。`/healthz` の応答自体は TestClient と実 uvicorn(fake バックエンド)で確認済み
- 持ち越しは README 8章と 0021 にまとめた
- 設計書のユーザー承認と decisions 4章の10件の確定はユーザー判断待ちのまま

## 4. 次のアクション

最終整理の作業記録 `0021-final-summary.md`(仮値一覧・採用案一覧・決めた内容・持ち越し一覧・完了条件1〜10の検証結果・設計書改版依頼リスト・ユーザー判断待ち)を作成し、タスクレビュー(task-reviewer。0002 §8)を実施する。
