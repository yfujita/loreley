# 20261126_fix_admin_openapi_types

## 背景・目的

Admin View のフロントエンド設計 v0.2(タスク `20261126_create_admin_ui_system_design`)で、実装済みの Admin API(EP-01〜14)の実 OpenAPI と設計を照合したところ、フロントの型生成(Hey API。生成コードと OpenAPI JSON はリポジトリにコミットする。FARC-P-6)の入力として好ましくない型の不一致が見つかった(前提タスク A)。

- `ttl_days`・`ttl_seconds`(EP-03・04 の要求本文)が OpenAPI 上は `integer | null` で、「null を送れる」型として生成される。実行時は明示的な null を 400 `type` で拒否するので、OpenAPI と実行時の挙動が食い違う
- `openapi_export.py` の docstring が「書き出した JSON はリポジトリにコミットしない」と書いており、「コミットする」方針(FARC-P-6)と食い違う

型生成の前に直しておくと、生成コードを作り直さずに済む。**必須ではない**(フロントは `ttl_*` の null を送らずキーを省くので、直す前でも動く)。

## 要件

### 現状(As-Is)

- `apps/api/src/loreley_api/admin/schemas/sources.py` の `UpdateSourceBody`(EP-04)と、それを継承する `RegisterSourceBody`(EP-03)は、`ttl_days: int | None = None`・`ttl_seconds: int | None = None` と宣言している。そのため OpenAPI は `integer | null`(既定 null)になる
- 同じ 2 項目に `@field_validator(..., mode="before")` があり、**明示的な `null` は 400 `type` で拒否**する(省略は「指定なし」)
- 「どちらか一方が必須」(両方・どちらもなしは `services` が `exclusive`・`required` で 400)は OpenAPI に出ない
- `apps/api/src/loreley_api/admin/openapi_export.py` の docstring に「書き出した JSON はリポジトリにコミットしない(置き場は、フロントエンドの型生成の手順が決める)」とある
- 応答側の `ttl_days`(`SourceDetailResponse`・`SourceSettings` など。`ttl_seconds` が日で割り切れないとき null)は `int | None` で、これは仕様どおり

### あるべき姿(To-Be)

- OpenAPI の `RegisterSourceBody`・`UpdateSourceBody` で、`ttl_days`・`ttl_seconds` が **「任意(required に含まれない)かつ非 null の整数」** になる。型生成すると `ttl_days?: number` になり、null を送れる型にならない
- **実行時の挙動は変えない**(省略は指定なし、明示的な `null` は 400 `type`、排他・必須・範囲の検証は従来どおり)
- `openapi_export.py` の docstring が、書き出した JSON をコミットする方針(FARC-P-6。置き場・再生成の差分検査はフロントの型生成の手順が決める)と矛盾しない記述になる

### 具体的にやること

- `UpdateSourceBody`(と継承する `RegisterSourceBody`)の `ttl_days`・`ttl_seconds` を、OpenAPI 上「任意かつ非 null」に直す(実現手段はプランで決める。検証の挙動は変えない)
- `openapi_export.py` の docstring を直す
- 書き出した OpenAPI(`python -m loreley_api.admin.openapi_export <出力パス>`)で、上記の 2 項目の型と `required` を確認する。確認は、既存の OpenAPI のテスト(`tests/admin/test_openapi.py`・`tests/admin/test_openapi_export.py`)に回帰テストとして足す
- **任意項目**(やる・やらないはプランで判断する。やる場合は、他の型・応答を変えないこと):
  - EP-09(jobs 一覧)の `sort` を素の string から列挙にする(許容は `queued_at`・`-queued_at`。`items_per_page` は列挙化済み)
  - `warnings[]` の要素の型を、`code` が型に出るものにする(現状は `{[k: string]: unknown}`。フロントは型ガードで対処する予定なので、やらなくても支障はない)

## 対象範囲

- `apps/api/src/loreley_api/admin/schemas/sources.py`(`ttl_days`・`ttl_seconds`)
- `apps/api/src/loreley_api/admin/openapi_export.py`(docstring)
- `apps/api/tests/admin/`(OpenAPI の回帰テスト)
- (任意項目をやる場合)jobs の `sort` と `warnings[]` に関するスキーマ・ルーター

## スコープ外

- `ErrorBody.code` の列挙化(`implement_admin_api` の 0017 の判断。将来の code の追加で型生成が壊れるため行わない)
- 応答側の `ttl_days`・`ttl_seconds` の型(仕様どおり)
- 書き出した OpenAPI JSON のコミットと、Hey API の生成コード・CI の再生成差分検査(フロントの実装タスクで行う)
- `web` コンテナ・compose・EP-13 の `web` 判定(別タスク `20261126_add_web_container_nginx`)
- B・C・D・A(設計書)本文の追従改訂(A の申し送り HO-59〜65 ほか。別途)
- Admin API のその他の仕様変更・エラーコードの変更

## 制約・前提条件

- 設計と実装の整合を優先する。実行時の API の挙動(受け付ける・拒否する入力、エラーコード、`field`)を変えない(既存のテスト・結合テストが引き続き通ること)
- 要件にない型の変更をしない。OpenAPI の差分は、直す項目(任意項目をやる場合はその分)に限る。それ以外のスキーマが変わっていないことを確認する
- 「どちらか一方が必須」の OpenAPI での表現(`oneOf` など)は、型生成の結果を複雑にしうるので**このタスクでは行わない**(排他・必須は実行時の検証に任せ、フロントの画面側で保証する)
- 本タスクは `apps/api` のみ。ほかのタスクとは独立で、型生成(フロントの実装)の**前に終わっていることが望ましいが、必須ではない**。`web` コンテナのタスクとは依存関係がなく、どちらが先でもよい

## 完了条件

- [ ] 書き出した OpenAPI で、`RegisterSourceBody`・`UpdateSourceBody` の `ttl_days`・`ttl_seconds` が非 null の整数で、`required` に含まれない
- [ ] 上記を検証する回帰テストがある(既存の OpenAPI テストの流儀に合わせる)
- [ ] 明示的な `null` が 400 `type`、省略が指定なし、排他・必須・範囲が従来どおりであることが、既存のテストで確認できる(`apps/api` の単体テストがすべて通る)
- [ ] 直す項目以外の OpenAPI の差分がない(修正の前後に書き出した OpenAPI を比較して確認する)
- [ ] `openapi_export.py` の docstring が、コミットする方針と矛盾しない
- [ ] `apps/api` のリント・テストがすべて通る(`ruff` と `pytest`。`pyproject.toml` の設定に従う)
- [ ] 作業記録に、実施した確認(OpenAPI の前後比較、テスト結果)と未対応事項を残している

## 成果物

- `apps/api` の変更(スキーマ・`openapi_export.py`・テスト)
- 作業記録(`agent_tasks/20261126_fix_admin_openapi_types/NNNN-*.md`)

## 補足・参考情報

- 出典: `docs/v0.x/system-design/api/api-base-design-v0.1.md` 9 章の HO-52(前提タスク A。HO-38 の docstring の修正も含む)
- 出典: `docs/v0.x/system-design/ui-admin/frontend/ui-admin-frontend-architecture-v0.2.md` の 12.7(S-D1・X-ED2・J-O2・J-O4)・12.8、5.2(型生成)
- 調査の根拠: `agent_tasks/20261126_create_admin_ui_system_design/0004-investigate-openapi-alignment.md`(S-D1・X-ED2・J-O2・J-O4)
- 承認: ゲート4 の G4-3(コミット方針の維持)・G4-4(前提タスクを A と B+C の 2 本に切る)
- 依存と順序: A は型生成の前が望ましい。A の前に型生成した場合は、フロントの `toRequest` が null を送らない単体テストで補い、A の後に再生成して差分をレビューする(E 5.2)
- 関連タスク: `20261126_add_web_container_nginx`(前提タスク B+C)
