# 0003 実装・検証・レビュー

作成日: 2026-11-26

## 実施内容

プラン(0002。ユーザー承認済み)の実装・検証・レビューを実施した(メインエージェントが直接実装)。

### 変更したファイル

- `apps/api/src/loreley_api/admin/schemas/sources.py`: `OptionalTtl = Annotated[int | None, Field(json_schema_extra=_non_null_integer_schema)]` を追加し、`UpdateSourceBody` の `ttl_days`・`ttl_seconds` に適用(`RegisterSourceBody` は継承)。Python の型・既定値 `None`・`_reject_explicit_null` は変えていない(実行時の挙動は同じ)。スキーマ関数は `anyOf`・`default` を外して `type: integer` にする
- `apps/api/src/loreley_api/admin/openapi_export.py`: docstring を「コミットする(FARC-P-6)。置き場・再生成の差分検査は型生成の手順が決める」に修正
- `apps/api/README.md`: 同じ旧方針の記述(「コミットしない」)を修正(code-reviewer の指摘)
- `apps/api/tests/admin/test_openapi.py`: 回帰テスト `test_the_request_ttl_is_an_optional_non_null_integer`(2 スキーマ × 2 項目。`{"title", "type": "integer"}` の完全一致と `required` に含まれないこと)
- `apps/api/tests/admin/routers/test_source_commands.py`: `TYPE_VIOLATIONS` に `ttl_seconds: None` → 400 `type` を追加(test-reviewer の指摘)

### 判断

- `WithJsonSchema` ではなく `json_schema_extra` の関数を採用。`WithJsonSchema` は `default: null` が残り、非 null の型と食い違うため
- 任意項目(jobs の `sort` の列挙化、`warnings[].code` の型)は行わない(0002 の承認どおり)

## 検証

- OpenAPI の前後比較(修正前のコミットで書き出した `before.json` と修正後):差分は `RegisterSourceBody`・`UpdateSourceBody` の `ttl_days`・`ttl_seconds` の 4 か所だけ。`anyOf[integer, null]`・`default: null` が、`{"title", "type": "integer"}` に変わった。`required` は元から含まない
- `ruff check`・`ruff format`: 通過
- `pytest`(apps/api 全件): 3429 件すべて通過

## レビュー

- code-reviewer: 修正後可。指摘 [Important] README の旧方針 → 修正済み。[Suggestion/Nitpick] `OptionalTtl` のコメントの置き場所 → 対応せず(現状でも `_non_null_integer_schema` の直前のコメントで理由が分かる)
- test-reviewer: [Important] `ttl_seconds: None` の検証なし → 追加済み。[Suggestion] OpenAPI 全体の差分の恒久テスト → 要件上は前後比較の手動確認で足りるため対応せず。[Nitpick] title の期待値 → 具体値にした
- task-reviewer: 省略(変更が数行で、完了条件を前後比較とテストで確認できるため。0002 に記載)

## 未対応事項

- 任意項目(jobs の `sort` の列挙化、`warnings[].code` の型)は行っていない。フロントは型ガードで対処する予定で支障はない
- 書き出した OpenAPI のコミット、Hey API の生成・CI の差分検査はフロントの実装タスクで行う
- 結合テスト(IT)は実行していない(実行時の挙動を変えていないため)
