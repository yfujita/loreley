# タスク状態

## 基本情報

- 状態: not_started
- 現在工程: 要件確認(要件定義の記載済み。ユーザーのレビュー待ち)
- 最終更新: 2026-11-26
- 最新作業記録: 0001-write-requirements.md

## 現在の状況

要件定義(0000-requirements-definition.md)を記載した(ユーザーの依頼により、メインエージェントが元タスク `20261126_create_admin_ui_system_design` の設計・調査をもとに記載。0001)。内容は前提タスク A: `RegisterSourceBody`・`UpdateSourceBody` の `ttl_days`・`ttl_seconds` を OpenAPI 上「任意かつ非 null」にし、`openapi_export.py` の docstring を直す(`apps/api` のみ。実行時の挙動は変えない)。まだ要件確認・プラン作成には進んでいない。

## 次のアクション

1. 要件定義(0000)をユーザーがレビューし、必要なら修正する
2. 要件確認(`requirements-clarifier`)→ プラン作成(ユーザー承認)→ 実施
3. 型生成(フロントの実装)の前に終わっていることが望ましいが、必須ではない。`20261126_add_web_container_nginx` とは独立(どちらが先でもよい)

## 未解決事項

- 任意項目(jobs の `sort` の列挙化、`warnings[].code` の型)をやるかは、プランで判断する
- 「どちらか一方が必須」を OpenAPI に出すかは、出さない方針で 0000 に書いた(ユーザー確認が要る場合は要件確認で聞く)

## ユーザー判断待ち

- なし
