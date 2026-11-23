# 0009 PR #16 のレビュー指摘への対応

日付: 2026-11-23
対象: PR #16(`feature/implement-api-base`)に対する外部レビュー(ユーザーが提示)

## 指摘の確認と判断

| 指摘 | 確認結果 | 判断 |
| --- | --- | --- |
| P2: `root_path` があると `Cache-Control: no-store` が付かない | **再現した**(`TestClient(root_path="/proxy")` で `/proxy/api/x/v1/items/1` の応答に `cache-control` がない)。`request.url.path` が `root_path` を含むため | **修正**(下記) |
| P2: `StreamingResponse`・`BackgroundTask` の例外を捕捉できない | 構造上そのとおり(`BaseHTTPMiddleware` は `call_next` が返った後の例外を捕捉できない。応答の開始後は 500 に差し替えられない)。基盤は `/healthz` だけで、Admin API も JSON の応答のみの前提 | **保証の範囲を明文化**(middleware の docstring と HO-51)。実装の置き換え(純粋な ASGI middleware 化)は、これらを使い始めるときに再検討 |
| P3: OpenAPI の 422 宣言 | そのとおり(FastAPI は 422 を既定で宣言する。基盤は 400 に変換する)。OpenAPI は本タスクのスコープ外 | **HO-51 に申し送り**(400 の共通エラースキーマを宣言し 422 の宣言を除く) |
| P3: 設計書 D との不一致 | 既知(HO-51) | 対応済み(追加対応なし) |

## 修正内容

- `src/loreley_api/common/http/middleware.py`: `no-store` の判定を `request.url.path` から `starlette.routing.get_route_path(request.scope)`(`root_path` を除いたアプリから見たパス)に変更。**判定は `call_next` の前に行う**(サブアプリの処理で `scope["root_path"]` が変わるため、後で判定すると、サブアプリのパスが相対になり `/api/` に当たらず、マウント下の全テストが落ちた。実験で確認)。docstring に「保証の範囲」を追記
- `tests/server/test_mounts.py`: `test_no_store_is_set_by_the_path_seen_by_the_app_under_a_root_path` を追加(`/proxy` 配下で `/api/` の応答には付き、`/proxy/nope`(404)には付かない)。変異(`request.url.path` に戻す)でこのテストだけが落ちることを確認し、元に戻した
- `docs/v0.x/system-design/api/api-base-design-v0.1.md`: HO-51 の内訳「実装上の注意」に、上記の保証の範囲と OpenAPI の 422 を追記(追記のみ)

## 検証

`cd apps/api`: `uv run pytest` 310 passed(309 + 1)、`uv run ruff check` 通過、`uv run ruff format --check` 通過、`uv lock --check` 通過。

## 未対応事項

- 純粋な ASGI middleware への置き換え(`StreamingResponse`・`BackgroundTask` を使う機能が入るとき)
- 設計書 D の追従改訂(HO-51)。AAM-P-23 の分担変更はユーザー確認が必要
