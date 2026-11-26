# タスク状態

## 基本情報

- 状態: done
- 現在工程: 完了(実装・検証・コードレビュー・修正済み。コミットは未実施)
- 最終更新: 2026-11-26
- 最新作業記録: 0005-code-review-and-fixes.md

## 現在の状況

`apps/web` の最小スキャフォールドを作り、`docker run node:24` で検証した(0004)。`npm ci`(警告 0)・`npm audit` 0 件・`typecheck`・`build`・dev(`/admin/` 200、`/admin` 404、`/api` の転送)・ブラウザ描画・`node:25` での `engine-strict` 失敗を確認。`code-reviewer` の指摘(README の記述、macOS の `fsevents` 警告)を修正した(0005)。0000 の完了条件はすべて満たしている。

## 次のアクション

1. ユーザーが `apps/web` の差分を確認し、コミット・PR にする(未コミット)
2. `20261126_add_web_container_nginx` を再開する(B+C)

## 未解決事項

- 設計 E への反映の検討: `allowScripts`(`@parcel/watcher`・`fsevents`)、`typecheck` が 2 回の `vue-tsc` になる点
- 運用メモ「api を自分で publish」は、B+C の前は compose がすでに publish しているため、B+C の作業で読み替える
- `tsconfig.json` の references に `composite` なし(必要になった時点で対応)

## ユーザー判断待ち

なし
