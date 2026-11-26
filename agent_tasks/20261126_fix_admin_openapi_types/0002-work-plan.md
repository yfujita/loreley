# 0002 作業プラン

作成日: 2026-11-26(承認待ち)

## 方針(要点)

- 対象は `apps/api` のみ。実行時の挙動(省略=指定なし、明示的な `null`=400 `type`、排他・必須・範囲の検証)は変えない。
- OpenAPI の `RegisterSourceBody`・`UpdateSourceBody` の `ttl_days`・`ttl_seconds` を「任意(`required` に含まない)かつ非 null の整数」にする。
- 実現手段: Python の型は `int | None = None` のまま(未指定を `None` で持つため。`_reject_explicit_null` も維持)、**JSON Schema の生成だけ**を `Annotated[..., WithJsonSchema(...)]` か `Field(json_schema_extra=...)` で `{"type": "integer"}` に差し替える。どちらにするかは、書き出した OpenAPI の出力(`title`・`default` が不要に消えない・増えないこと)を見て実装時に決める。
- 「どちらか一方が必須」は OpenAPI に出さない(要件どおり)。
- **任意項目(jobs の `sort` の列挙化、`warnings[].code` の型)はやらない**。理由: 要件に「型生成に支障はない」とあり、`sort` は共通のページング処理(`read_paging`)と app.py の OpenAPI 補正に波及するため、「要件にない変更をしない」を優先する。未対応事項として作業記録に残す。

## フェーズ

1. **修正前の OpenAPI を保存**(完了済み・スクラッチパッドの `before.json`。実装前にもう一度書き出して比較用に確定する)
2. **実装**(メインエージェントが直接。1 ファイル + テスト + docstring の軽微な変更)
   - `apps/api/src/loreley_api/admin/schemas/sources.py`: `UpdateSourceBody` の `ttl_days`・`ttl_seconds` の JSON Schema を非 null の整数にする(`RegisterSourceBody` は継承で追従)
   - `apps/api/src/loreley_api/admin/openapi_export.py`: docstring を「書き出した JSON はコミットする方針(置き場・再生成の差分検査はフロントの型生成の手順が決める)」に直す
   - `apps/api/tests/admin/test_openapi.py`: 回帰テスト(2 スキーマの `ttl_days`・`ttl_seconds` が `type: integer` で `null` を含まず、`required` に含まれない)を既存の流儀で追加
3. **検証**
   - 修正後の OpenAPI を書き出し、`before.json` と JSON 差分を取る。差分が 2 スキーマ × 2 項目だけであること
   - `ruff check`・`ruff format --check`・型検査(`pyproject.toml` の設定にあるもの)・`pytest`(単体テスト全件。明示的な `null` が 400 `type` になる既存テストを含む)
4. **レビュー**: `code-reviewer`(`sources.py`・`openapi_export.py`)と `test-reviewer`(追加テスト)。比較基準は実装開始前のコミット(`69dcc48`)と作業ツリーの差分
5. **タスクレビュー**: 省略(変更が `apps/api` の数行で、完了条件が OpenAPI の前後比較とテストで機械的に確認できるため)。省略理由は作業記録に残す
6. **作業記録・STATUS.md の更新**(各フェーズ後。最終は完了条件の確認結果と未対応事項を記載)

## リスク

- `WithJsonSchema` は生成されるスキーマ全体を置き換えるので、`default`・`title` の有無が変わりうる(差分確認で、想定外の変更がないことを見る)
- 結合テスト(IT)は Docker・固定ポートを使うため、本タスクでは実行しない(実行時の挙動を変えないため。単体テストで担保)
