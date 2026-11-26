# 0006 P2: `api` の `web` 判定の置換(C)

- 日付: 2026-11-26
- 実施: code-implementer(実装・検証)→ メインエージェントが ruff・OpenAPI diff・grep・pytest を再実行

## 決めたこと

- 環境変数: `LORELEY_API_WEB_URL`(**必須**。`CRAWLER_URL`・`INDEXER_URL` と同じ `_validate_base_url`: http のみ・パス/クエリなし・末尾 `/` 除去)。必須の環境変数は 3 → 4 つ。compose の値は `http://web:80`(P3)
- 確認先: `{WEB_URL}/admin/`。パスは `dashboard.py` の定数 `WEB_HEALTH_PATH = "/admin/"`(`HttpHealthProbe` はリダイレクトに従わないため末尾スラッシュ必須。コメントに理由を記載)
- `web` は `probe` の枠(`runner.run_all`)で並行実行し全体期限に含める。順は crawler・indexer・opensearch・web・任意。R9 の例外(`DIRECT_CHECK_RECEIVERS`)は空集合に
- `ProbeReason` の `"missing"` は残す(消すと EP-13 の `reason` 列挙が変わり OpenAPI に差分が出る)。`probe_outcome.py` に理由のコメントを追加

## 変更ファイル(`apps/api/` 配下)

- src: `config.py`・`admin/settings.py`・`admin/services/dashboard.py`・`admin/dependencies.py`・`admin/openapi_export.py`(`web_url="http://web.invalid"`)・`main.py`・`infrastructure/probes/__init__.py`・`infrastructure/probes/ports.py`・`common/probe_outcome.py`・`admin/base/codes.py`(コメントのみ。下記)・`Dockerfile`(コメント)。削除: `infrastructure/probes/web_dist.py`
- tests: `test_config.py`・`test_main.py`・`api_config.py`・`fakes/fake_probes.py`・`fakes/test_fake_probes_protocol.py`・`admin/services/test_dashboard.py`・`admin/routers/test_dashboard.py`・`admin/routers/test_dashboard_over_http.py`(web もローカル HTTP スタブ: normal・`connection_refused`・301 を追わず `unexpected_status`・遅延は `timeout`)・`architecture/test_http_rules.py`・`architecture/test_read_only_rules.py`。削除: `infrastructure/probes/test_web_dist.py`

## 要件内の衝突と判断

0000 は「`ComponentId` の docstring を直す」と「`ComponentId`・`reason` の OpenAPI に差分がない(完了条件)」の両方を求めているが、docstring は OpenAPI の `components.schemas.ComponentId.description` にそのまま出るため両立しない(実際に直すと差分が 1 行出ることを実装担当が確認)。

**判断**: 完了条件(OpenAPI 差分ゼロ。画面側の変更を要らなくするための制約)を優先し、docstring の文面(「`web` は compose のサービスではなく、`api` が配信する Web UI の表示名」)は変えない。代わりにクラス本体に「説明が古いが OpenAPI を変えないため直していない」旨の `#` コメントを足した。**申し送り**: docstring の文言修正は OpenAPI の更新(と、生成型の再生成)を伴う別タスクで行う。

## 検証結果(メインエージェントが再実行)

- `uv run ruff check .`: All checks passed / `ruff format --check .`: 247 files already formatted
- OpenAPI: 変更前(P0)と変更後を書き出して `diff` → **差分ゼロ**
- `pytest`: 実装担当の報告は 3425 passed(ベースライン 3429 から `test_web_dist.py` の削除分と新規分の差)。メインエージェントの再実行でも **3425 passed**(124 秒)
- grep `web_dist|WebDist|WEB_DIST|/app/web`(`apps deploy tests scripts`): `apps/api` の `src`・`tests` は 0 件。残りは **P3・P4・P6 の担当**のもの: `apps/api/README.md`(14・97・152 行目。P6)、`deploy/compose/README.md:109`(P6)、`deploy/compose/compose.yaml:245`(P3)、`tests/integration/api/` の `compose.test.yaml`・`test_01_startup.py`・`README.md`(P4)

## 次の作業(他フェーズへの引き継ぎ)

- P3: `compose.yaml` の `api` に `LORELEY_API_WEB_URL: http://web:80` を足す(足さないと `api` が起動しない)
- P4: IT の `api` の環境変数(`compose.test.yaml` が `compose.yaml` を継承するので確認)に `LORELEY_API_WEB_URL` が渡ること、`LORELEY_API_WEB_DIST_DIR`・`/app/web` の mount の撤去
- P6: `apps/api/README.md`(必須環境変数 4 つ・`WEB_URL` 行・`WEB_DIST_DIR` と `/app/web`・「`web` は異常と表示される」の削除)
