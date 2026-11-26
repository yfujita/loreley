# タスク状態

## 基本情報

- 状態: done
- 現在工程: 完了(実装・検証・レビュー済み。コミットは未実施)
- 最終更新: 2026-11-26
- 最新作業記録: 0003-implement-and-review.md

## 現在の状況

`RegisterSourceBody`・`UpdateSourceBody` の `ttl_days`・`ttl_seconds` を OpenAPI 上「任意かつ非 null の整数」にし、`openapi_export.py` の docstring と README の旧方針の記述を直した。OpenAPI の前後差分はこの 4 か所だけ。`ruff` 通過、`pytest` 3429 件通過。code-reviewer・test-reviewer の指摘は反映済み。変更は作業ツリーにあり、コミット・PR は未実施。

## 次のアクション

1. ユーザーが変更を確認し、コミット・PR を指示する
2. (別タスク)フロントの型生成時に OpenAPI を書き出してコミットする

## 未解決事項

- 任意項目(jobs の `sort` の列挙化、`warnings[].code` の型)は行っていない(プラン承認どおり。フロントは型ガードで対処)

## ユーザー判断待ち

- なし
