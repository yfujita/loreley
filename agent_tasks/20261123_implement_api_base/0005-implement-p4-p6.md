# 0005 実装 P4〜P6(main・architecture・Dockerfile・README・設計書への申し送り)

日付: 2026-11-23
実施: P4・P5 は code-implementer、docker 検証と P6 はメインエージェント

## P4: main.py と tests/architecture

- `src/loreley_api/main.py`(`build_app()`・`main()`)、`tests/architecture/{__init__,dependency_rules,test_dependency_rules,test_http_rules}.py`、`tests/test_main.py` を追加
- 許可表は `build_allowed(feature_packages)` で `FEATURE_PACKAGES={"health"}` から作る。合成の2つ目の機能 `dummy` で R2 を確かめる自己テスト入り。`fastapi`・`starlette` は制限しない。`opensearchpy`・`urllib3`・`requests`・`httpx`・`httpx2`・`aiohttp`・`anyio` は所有者なし(`src` 配下のみ検査)
- 変異テストで検査の有効性を確認済み(`server/app.py` で `health` を import → 失敗、`redirect_slashes=False` を消す → 失敗、`health` に `import httpx2` → 失敗。すべて復元済み)
- 手動検証(8080 で起動): `/healthz` が 200・`{"status":"ok"}`、`/nope` が 404・JSON `not_found`、`/healthz/` が 404。アクセスログは INFO で `GET - 404 0.5ms`、`/healthz` は DEBUG のみ。SIGINT で正常停止。プロセスは残っていない

## P5: Dockerfile・.dockerignore・README

- Indexer の流儀に合わせて作成(同じタグ+ダイジェスト、`uv==0.13.7`、uid/gid 10001 の `api`、`EXPOSE 8080`、`HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3`、Node ステージなし)。README は概要・設計書参照先・起動方法・環境変数・テスト実行・公開範囲の注意
- **docker 検証**(code-implementer 実施時は Docker デーモン停止で未実施 → ユーザーが Docker Desktop を起動した後、メインエージェントが実施。他プロジェクトのコンテナは触っていない。既存の `opensearch-opensearch-1`(Exited)はそのまま):
  1. `docker build -t loreley-api apps/api`: 成功
  2. `docker run -d --name loreley-api-check -p 127.0.0.1:18080:8080`、20 秒後に `healthy`
  3. `/healthz` が 200・`{"status":"ok"}`、`/nope` が 404・JSON `not_found`
  4. `id -u` が `10001`。イメージで `import pytest` が `ModuleNotFoundError`(dev 依存なし)
  5. `LORELEY_API_PORT=SENTINEL-PORT` で終了コード 1、出力は `invalid settings: port: int_parsing` でセンチネルなし
  6. `docker stop` は 1 秒
  7. 作成した `loreley-api-check` コンテナと `loreley-api` イメージだけを削除

## P6: 設計書 9章への申し送り

- `docs/v0.x/system-design/api/api-base-design-v0.1.md` に `HO-51`(9.2.10 の末尾。既存設計の改訂要求・緊急度 高・未対応)を追記。内容: admin 実装前に D を追従改訂する前提条件、D 3章・4.2・R3・許可表・R9・7.1 の差分、AAM-U-2 の確定方式、`redirect_slashes` の強制、サブアプリの lifespan、OpenAPI の生成(`create_admin_app(...).openapi()`)、孤立サロゲートの扱い、`starlette` の扱い、`Depends` 検査が未実装であること
- **0003 からの軽微な逸脱**: 0003 は「追記のみ」としていたが、HO の範囲表記(`HO-1〜HO-50` を `HO-1〜HO-51` に)を 3 か所(冒頭の説明、ID 体系、9章冒頭)更新した。範囲外の番号が残ると設計書内で矛盾するため。設計の本文(他の章)は変更していない
- 差分: 4 行追加・3 行変更(上記の範囲表記のみ)

## 検証(メインエージェントが再実行)

`cd apps/api` で `uv run pytest`: **300 passed**、`uv run ruff check`: 通過、`uv run ruff format --check`: 36 files formatted、`uv lock --check`: 通過。

## 未対応事項・次にやること

- レビュー(code-reviewer・test-reviewer・document-reviewer)→ task-reviewer
- 完了報告で、設計書 D の追従改訂タスクの作成を提案する
- R9 の `Depends` 検査は未実装(基盤に `Depends` がないため)。admin 実装時に足す(HO-51 に記載)
