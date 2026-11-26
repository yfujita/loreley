# 0005 code-reviewer のレビューと修正

- 日付: 2026-11-26
- レビュー: `code-reviewer`(`apps/web` 全体を要件・設計 E・F と照合)。Critical なし。修正後可(軽微)
- `test-reviewer`・`web-ui-reviewer`・`task-reviewer` は省略(0003 のとおり。テストコードなし、プレースホルダー 1 画面はメインがブラウザで確認済み、小規模)

## 指摘と対応

1. [Important] README・`vite.config.ts` のコメントの「`api` は compose でホストに publish されない」は現状と異なる(現行の `compose.yaml:241` は `127.0.0.1:${API_HOST_PORT:-8080}:8080` で publish している。外すのは B+C) → 修正した。B+C の前は `api` が `127.0.0.1:8080` に publish されているのでそれを指定し、B+C の後は既定の `web`(8090)経由になる、と書いた。0000 の運用メモ(「自分で publish して」)の記述が現状と異なる点は、設計側の乖離として申し送る
2. [Suggestion] `allowScripts` が `@parcel/watcher` だけでは、macOS で `fsevents` の警告が出る可能性 → macOS(ホスト)で `npm@11.19.1 ci` を実行して確認したところ、警告 `fsevents@2.3.3 (install)` が出た。`allowScripts` に `"fsevents": false` を追加した。再確認で警告 0・脆弱性 0・`npm run build` 成功。`fsevents.node`(ビルド済みバイナリ)は同梱されたまま
3. [Nitpick] `tsconfig.json` の references 先に `composite` がない → 対応しない(`typecheck` は `-p` で個別に実行する。`tsc -b` やエディタで問題が出たら、lint 導入時などに直す)

実装者の 4 判断(typecheck の 2 回実行、`allowScripts`、`@` エイリアス、`PlaceholderPage.vue`)はレビューで妥当とされた。

## 変更したファイル

- `apps/web/README.md`、`apps/web/vite.config.ts`(コメント)、`apps/web/package.json`(`allowScripts`)

## 完了条件の確認

0000 の完了条件はすべて満たした(0004・本記録の検証による)。`git status` で `apps/web/` は未追跡(コミット前)。`node_modules/`・`dist/` は作っていない。

## 未対応事項・申し送り

- 設計 E への反映の検討: `package.json` の `allowScripts`(`@parcel/watcher`・`fsevents`。npm 11.16 以降の警告対策。npm 12 では既定で拒否の予定)、`typecheck` が 2 回の `vue-tsc`(`-p tsconfig.app.json`・`-p tsconfig.node.json`)になる点
- `20261126_add_web_container_nginx` の 0000・0002 などの運用メモ「api を自分で publish」は、B+C 前は compose がすでに publish しているため、読み替える(B+C の作業で整理)
- コミットは未実施(ユーザーの指示待ち)
- 完了後、`20261126_add_web_container_nginx` を再開する
