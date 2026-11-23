# タスク状態

## 基本情報

- 状態: done
- 現在工程: 完了
- 最終更新: 2026-11-23
- 最新作業記録: 0008-task-review-and-completion.md

## 現在の状況

API 基盤(`apps/api`)を実装した。`GET /healthz` を独立した機能パッケージ `health/` として実装し、`server` の汎用の口(`create_app(routers, mounts, …)`)に載せる構成。pytest 309 passed、ruff・uv lock 通過、最終コードで docker 検証(build・healthy・200/404/405)済み。code・test・document のレビューと再レビュー、task-reviewer(Critical・Important なし)を完了。変更はコミットしていない。

## 次のアクション

1. 設計書 D の追従改訂タスクを作成するか、ユーザーが判断する(HO-51。admin 実装の前提条件。AAM-P-23 の分担変更はユーザー確認が必要)
2. 変更のコミット・PR をユーザーが指示する

## 未解決事項

- 設計書 D への追従改訂(HO-51)。AAM-P-23(承認済みの案)の分担変更はユーザー確認を取る
- admin 実装時に足すもの(`Depends` の `async def` 検査、本文上限、厳密 JSON、`OPENAPI_ENABLED` など)は HO-51 に記載
- Starlette の scope 共有挙動への依存(AAM-U-2 の方式)。`tests/server/test_mounts.py` で固定済み

## ユーザー判断待ち

- 設計書 D の追従改訂タスクの作成の要否
- コミット・PR の要否
