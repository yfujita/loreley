# 0007 再レビューと最終修正

日付: 2026-11-23

## 再レビュー結果

| レビュー | 結果 |
| --- | --- |
| test-reviewer(再) | 1回目の Important 3件は解消済み。Critical・Important なし。Suggestion 2、Nitpick 1。13種の変異で検出を確認(`removeprefix` の削除のみ生存) |
| document-reviewer(再) | Important 4件のうち3件は解消済み、1件(A 2.1・7章)は部分解消。新たな Important 2件(A 2.1 の引用が A に存在しない、D の改訂箇所の列挙漏れ)、Suggestion 5、Nitpick 3 |

## 対応

### 設計書 api-base-design-v0.1.md(メインエージェント)
- A 2.1 の記述を実際の A の内容に合わせて修正(「`/healthz` を `api` の URL として列挙するだけで、`health` の導入による変更は不要」)
- D の改訂箇所に「D 全体の洗い出し」を追加(2.1 の `server` 行・図・「`server` が import するのは `admin` の入口だけ」、4.1 手順5、5.9、6章 R1、8.3 の AAM-P-2・P-3、7.3)
- 基盤が未実装のものを具体化(`OPENAPI_ENABLED`・`WEB_DIST_DIR`・`ADMITTING_LOCK_GRACE_SECONDS`。A 4章の表のうち実装済みは HOST・PORT・LOG_LEVEL だけ)
- 他文書の「HO-1〜HO-50」表記と D 冒頭の「HO-39」を、D の追従改訂時に更新する旨を追記
- 出典に 0006 を追加、完了後は `_archive/` 配下になる旨と、AAM-P-23 の承認は D 8.7 にある旨を追記
- `display_text` の説明、`Mount` 判定の記述(`methods` を持たない route)、9.1 に「HO-51 だけは実装タスクが追加した」の1行、空行の重複を修正
- サブアプリ内の `Mount` 配下と外側アプリの `root_path` は検証済み、サブアプリの中にサブアプリをマウントする入れ子は未検証、に更新
- **対応しなかった**: AAM-U-2 の箇条書きを小項目に分ける提案(内容は揃っており、読みづらさは許容範囲と判断)

### テスト(code-implementer。309 passed)
- 外側アプリが `root_path`(プロキシ配下)を持つとき、ログのテンプレートが `GET /api/dummy-a/v1/items/{item_id} 200` になることを固定。`removeprefix` を壊す変異で検出されることを確認
- サブアプリ内の入れ子 `Mount` の正常系(200)で、ログが `GET /api/dummy-a/v1/m/k/{id} 200` になり ID を含む実パスが出ないことを固定
- `middleware.py` の `_route_template` の docstring を、上記の検証状況に合わせて更新(メインエージェント)
- 対応しなかった: `restore_logging` の `propagate`・`disabled` の復元(現状の `configure_logging` は触らず実害なし)

## 検証(メインエージェントが再実行)

`cd apps/api`: `uv run pytest` 309 passed、`uv run ruff check` 通過、`uv run ruff format --check` 36 files formatted、`uv lock --check` 通過。`git status`: 変更は `apps/api/`(新規)、`agent_tasks/`(新規)、`docs/.../api-base-design-v0.1.md`(HO-51 の追記と範囲表記・改訂履歴・9.1 の1行)のみ。

## 次にやること

task-reviewer でタスク全体をレビューする。完了報告で、設計書 D の追従改訂タスクの作成を提案する(AAM-P-23 の分担変更はユーザー確認が必要)。
