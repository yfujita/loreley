# 0014 P6: EP-13(ダッシュボード)とプローブ

日付: 2026-11-24

## 実施内容

`code-implementer` が P6 を実装。メインエージェントが検証を再実行して確認した。これで EP-01〜14 の実装がそろった(残りは P7 の OpenAPI・README・手動スモーク)。

## 検証(メインエージェントが再実行、`apps/api`)

- `uv run pytest`: 3252 passed(P5b 後 3032)
- `uv run ruff check`: All checks passed / `uv run ruff format --check`: 240 files already formatted / `uv lock --check`: OK
- `apps/api` 以外に差分なし。`pyproject.toml`・`uv.lock` 未変更。起動プロセスの残りなし
- 実 Crawler・実 Indexer・実 OpenSearch・実ネットワークには接続していない(ローカル HTTP スタブ 127.0.0.1 と偽物のみ。名前解決失敗のテストは `.invalid` ホストを引くため DNS 問い合わせは発生する。0012 の既存テストと同じ流儀)

## 変更ファイル(`apps/api/` 配下)

- src 新規: `infrastructure/probes/{ports,classification,http_probe,web_dist}.py`、`infrastructure/opensearch/health_probe.py`(`urllib3.exceptions` を import する例外ファイル)、`admin/schemas/dashboard.py`、`admin/services/dashboard.py`、`admin/routers/dashboard.py`
- src 変更: `admin/base/codes.py`(`ComponentId`。宣言順が応答の固定順)、`admin/dependencies.py`(`AdminProbes`、`AdminDependencies.dashboard`、`build_admin_dependencies(..., probes=)`)、`routers/__init__.py`・`app.py`・`admin/__init__.py`、`main.py`(プローブ用接続・`HttpHealthProbe`・`WebDistProbe` を組み立て、closers に追加)、`infrastructure/probes/__init__.py`・`infrastructure/opensearch/__init__.py`
- tests 新規: `fakes/fake_probes.py`・`fakes/test_fake_probes_protocol.py`、`infrastructure/probes/{test_classification,test_http_probe,test_web_dist}.py`、`infrastructure/opensearch/test_health_probe.py`、`admin/services/test_dashboard.py`、`admin/routers/{test_dashboard,test_dashboard_over_http}.py`
- tests 変更: `fakes/inline_runner.py`(`abandoned_indexes`・`run_all_deadlines`)、`admin/factories.py`、`test_main.py`、`architecture/test_read_only_rules.py`(R8 (e))、`architecture/test_http_rules.py`(R9 の例外)

## Indexer・Crawler の `GET /healthz`(プラン 2.2-9 の確認)

差分なし。どちらも `GET /healthz` が 200 `{"status":"ok"}`。Admin API は 2xx かどうかだけを見る前提でそのまま成立する。Indexer は `RequestGuardMiddleware` が起動時の整理が終わる(`ready`)までは全パスに 503(C 6.2 の「Indexer の起動前の 503」の行と一致。lifespan の順序上、外からは接続拒否に見えるはず)。Crawler の `healthz` は何も呼ばず、受付開始前は接続を受け付けない

## 判断・設計上の理由

- `HttpHealthProbe.check(url)`(D 4.10 の `check(url, timeout)` から変更)。タイムアウトは `HttpProbeConfig` をコンストラクタで受ける。確認は `Timeout(total=)`・`retries=False`・`redirect=False`・`preload_content=False`。D・C にない追加として `Connection: close`(30 秒間隔なので閉じられた keep-alive の再利用による誤検知を避ける)
- `WebDistProbe`: `index.html` が通常ファイルで先頭 1 バイトを読めれば `normal`。空ファイル・権限なし・ディレクトリ・壊れたシンボリックリンクはすべて `abnormal`/`missing`。`services.dashboard` が直接呼ぶ(R9 の例外)
- `DashboardService` は URL などの値をキーワード引数で受ける(`services` は `admin.settings` を import できない。R4。`MetaService` と同じ流儀)。確認先は `{crawler_url}/healthz`・`{indexer_url}/healthz` と設定された `*_HEALTH_URL` の完全な URL だけで、リクエスト入力は一切使わない。`run_all` の期限は `probe_timeout_seconds + 1.0`。呼び出し順は crawler・indexer・opensearch・設定された任意
- `components[].checked_at`: スレッド内で確認が終わった時刻。期限超過(`Abandoned`)・`api`・`web`・`not_configured` は応答を組み立てる時刻。トップの `checked_at` は最後に取る
- 期限超過は `undetermined`/`timeout`。WARNING で成分 ID だけをログに出す。URL・例外メッセージは出さない(`state`・`reason`・例外クラス名のみ)
- EP-13 の応答に `unavailable` は含めない(B 8.1 の定義と例は `checked_at`・`components` の 2 キーのみ)
- R9 の例外は AST 検査: `admin/` のうちプローブの Protocol を使うファイルで、メソッド本体から直接呼べる `.check(...)` は `self._web_probe` だけ。他は `runner.run_all` に渡す lambda の中にだけある(D 6章は runner 経由を「テスト」としていたが AST 検査にした。`StalledCheck.check` と衝突するためプローブの Protocol を使うファイルに絞った)

## 満たした C 11章の観点

10(2xx=normal、非 2xx(3xx 含む)=abnormal、接続拒否=abnormal/`connection_refused`、名前解決失敗=abnormal/`name_not_resolved`、遅延=undetermined/`timeout`、切断=undetermined/`connection_error`、OpenSearch の例外別 `state`・`reason`、`web` の `index.html` の有無、任意 3 つの `not_configured`、リダイレクトを追わない(転送先は 0 リクエスト)、確認先が環境変数以外から決まらない(クエリ・パス・Host 等のヘッダ・Cookie・本文を渡して確認)、8 件が固定の順)/ 14(実物の `BlockingRunner` で crawler・indexer・opensearch・任意のどれが遅くても他は normal で全体が期限内(確認 + 1 秒)に応答、複数が同時に遅い場合、待機中にイベントループが塞がれない)/ 8 の (c)・(e)(プローブの送信は `http_probe.py` の 1 か所のみで `"GET"` リテラル・URL は引数のみ・`retries=False`・`redirect=False`・`preload_content=False`。`probes` にパスのリテラルなし、`/healthz` は `services.dashboard` のみ。OpenSearch のプローブはラッパー経由の `cluster_health` だけ。合成ソースの負例つき)/ 12(URL・OpenSearch の例外メッセージのパスワードが応答・ログ(DEBUG)・出力に出ない)

## 検出力確認(実装担当。24 件を一時変更。復元済み)

GET→POST、`retries=True`、`redirect=True`、`preload_content=True`、URL 改変、タイムアウト変更、3xx を normal 扱い、例外分類の順序入れ替え、空ファイルを ok、OpenSearch の分類順序と SSL 判定の削除、期限マージン、期限超過を abnormal、web を確認しない、`api` を normal にしない、`not_configured` を normal、並び順の反転、indexer の URL を crawler に、任意を常に確認、web を runner 経由に、http を直接呼ぶ。すべて検出。`WebDistProbe` の `is_file()` → `exists()` は等価(ディレクトリ・壊れたシンボリックリンクはどちらでも `missing`)で未検出は妥当

## 設計書との食い違い・申し送り(設計書は未変更)

1. B 2.2 の単一応答の列挙に EP-13 が入っているが、B 8.1 の応答に `unavailable` はない(0010 の EP-12・14 と同様に列挙から外したい)
2. D 4.10 `HttpHealthProbe.check(url, timeout)` → 実装は `check(url)`(タイムアウトはコンストラクタ)。D 3章にない `probes/ports.py` を追加。`OpenSearchHealthCheck` の Protocol は `opensearch/ports.py` でなく `health_probe.py` に置いた(Reader 用の検査・テストから切り離すため)
3. D 4.1 `build_admin_dependencies` に `probes: AdminProbes` を追加。D 5.5 の `HealthProbe` は `OpenSearchHealthCheck` の名前
4. C 6.1: `Connection: close` を付けている
5. C 6.3 の `web`: 空ファイルは `missing`(「先頭 1 バイトを読めれば normal」の裏返し)
6. D 6章 R9: 「runner 経由はテスト」としていた部分に、`WebDistProbe` 以外のプローブの直接呼び出しを禁じる AST 検査を足した
7. 期限超過した確認の `checked_at` は応答を組み立てる時刻(C 6.1 は未記載)

## 未対応事項・次にやること

- 実機確認は P7 のスモーク: 実 Crawler・Indexer・OpenSearch の `GET /healthz` と `cluster.health`、`WEB_DIST_DIR`。AAPI-U-11(opensearch-py の例外と `abnormal`/`undetermined` の対応。接続拒否時の `ConnectionError.info` の型)、AAA-U-10(期限後に残るスレッドの数と時間)は未実測
- P7: OpenAPI の `requestBody`(0013)・422 の除去・`operationId`・tags・`OPENAPI_ENABLED` の公開配線・README・`server/` の「Crawler 遅延でも他が応答」の結合確認・手動スモーク
- R8 (e) の AST 検査の限界: 文字列連結や別名経由の送信は検出できない。送信呼び出しはメソッド名(`request` など)で判定する
- 据え置き: `test_secret_output.py` の DNS 依存(`probes` のテストにも `.invalid` による名前解決失敗があるが、一時的な DNS 失敗でも `NameResolutionError` になるので結果は安定)
- 次: レビュー R-C(前半: P5a・P5b・P6。比較基準 `5dc68c4`)。データ削除の中継を含むため `code-reviewer` は必須
