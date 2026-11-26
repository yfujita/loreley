# 20261126_fix_admin_openapi_types

## 背景・目的

Admin View のフロントエンドは、Admin API の OpenAPI から Hey API で型・クライアントを生成する。現状の OpenAPI は `ttl_days`・`ttl_seconds` の型が実行時の挙動と食い違っており、生成された型のまま使うと誤った値(null)を送れてしまう。また、OpenAPI の書き出しスクリプトの docstring が、フロント設計(OpenAPI JSON と生成コードをコミットする)と食い違っている。これらを直し、型生成の入力として正しい OpenAPI にする。

## 要件

### 現状(As-Is)

- OpenAPI の `RegisterSourceBody`・`UpdateSourceBody` で、`ttl_days`・`ttl_seconds` が `integer | null`(既定 null)になっている。実行時は明示的な null を 400(`type`)で拒否する。「どちらか一方が必須」という排他も OpenAPI に出ていない
- `apps/api/src/loreley_api/admin/openapi_export.py` の docstring が「書き出した JSON はリポジトリにコミットしない」と書いており、フロント設計(FARC-P-6)の「コミットして CI で再生成差分を検査する」と食い違っている

### あるべき姿(To-Be)

- `ttl_days`・`ttl_seconds` が OpenAPI 上で「任意かつ非 null」になり、実行時の挙動と一致する
- `openapi_export.py` の docstring が、コミットする方針に合っている

### 具体的にやること

- `ttl_days`・`ttl_seconds` の型を「任意かつ非 null」に直す(実行時の検証・挙動は変えない)
- `openapi_export.py` の docstring を、コミットする方針に合わせて直す
- OpenAPI の書き出しを再実行し、型の変更が出力に反映されていることを確認する
- 既存のテスト(`apps/api` の単体テスト、OpenAPI の公開・書き出しのテスト)を通す。型の変更に対するテストを必要に応じて追加する
- (任意)jobs の `sort` の列挙化、`warnings[].code` の型。実害は小さいので、やるなら小さく

## 対象範囲

- `apps/api/`(Admin API のスキーマ・OpenAPI の書き出し)

## スコープ外

- `ErrorBody.code` の列挙化(将来の code で型生成が壊れるため行わない。`implement_admin_api` の判断)
- Admin API の機能追加・挙動の変更
- フロントエンド(`apps/web`)、`web` コンテナ・compose(別タスク `20261126_add_web_container_nginx`)
- 設計書の改訂(必要な追従は A の HO で申し送り済み)

## 制約・前提条件

- 実行時の挙動は変えない(OpenAPI の型を実行時に合わせる)
- フロントの型生成の前に終わっていることが望ましいが、必須ではない(前でもフロントは `ttl_*` の null を送らずキーを省く)
- フロントの OpenAPI 生成は決定的に保つ(`sort_keys`・`indent` を変えない)

## 完了条件

- [ ] OpenAPI の `ttl_days`・`ttl_seconds` が任意かつ非 null になっている(書き出した JSON で確認)
- [ ] `openapi_export.py` の docstring がコミットする方針に合っている
- [ ] `apps/api` のテスト・lint が通る
- [ ] レビュー(`code-reviewer`・`test-reviewer`)で Critical・Important が解消されている

## 成果物

- `apps/api/` の変更(スキーマ・docstring・テスト)

## 補足・参考情報

- `docs/v0.x/system-design/api/api-base-design-v0.1.md` の HO-52・HO-38
- `docs/v0.x/system-design/ui-admin/frontend/ui-admin-frontend-architecture-v0.2.md` の 5.2・12.7(S-D1・X-ED2)・12.8
- `agent_tasks/20261126_create_admin_ui_system_design/` の 0004(照合結果)・0005(型生成の検証。`ttl_*` が `number | null | undefined` になること)
