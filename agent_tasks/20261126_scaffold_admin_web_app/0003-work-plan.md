# 0003 作業プラン

- 日付: 2026-11-26
- 前提: 0000 要件定義、0002 確定した要件(依存 11 個のみ・Router 最小組み込み・`docker run node:24` で検証・`apps/web/.gitignore`)

## フェーズ

1. **設計の確認(メイン)**: E 2・3.1〜3.5・11.1、F 2.4 を読み、設定ファイルの中身の要点を確認する
2. **実装(`code-implementer`)**: `apps/web` に次を作る
   - `package.json`(11 依存・固定の範囲は E 2.1・2.2。`engines`・scripts `dev`/`build`/`preview`/`typecheck`)、`.nvmrc`(24.15.0)、`.npmrc`(`engine-strict=true`)、`.gitignore`(`node_modules/`・`dist/`)
   - `index.html`、`vite.config.ts`(`base: '/admin/'`、vue・vuetify プラグイン、`/api` プロキシ。既定 `http://127.0.0.1:8090`、上書き用の環境変数 `LORELEY_DEV_API_TARGET`(`VITE_` なし))
   - `tsconfig.json`・`tsconfig.app.json`・`tsconfig.node.json`(`strict`、`exactOptionalPropertyTypes` なし、node 側 `types: ["node"]`)
   - `src/main.ts`、`src/admin/app/App.vue`、最小の router、`src/shared/theme/settings.scss`(変数上書きなし)、`src/env.d.ts` 相当
   - `README.md`(Node の合わせ方・コマンド・プロキシ上書き・範囲外 Node の対処)
   - `package-lock.json` は `docker run node:24` 内の `npm install` で生成し、コミット対象にする
3. **検証(メイン。`docker run node:24` を使用)**: クリーンな状態から `npm ci`(警告・エラーなし)→ `npm audit`(0 件)→ `typecheck` → `build`。`dist/` の構成・`/admin/assets/` URL・外部参照 grep 0 件。`npm run dev` で `/admin/` のプレースホルダー、`/admin` が 404、`/api/` が転送先(ダミー待ち受け)に届くこと。Node 25 相当(`node:25`)で `npm install` が `engine-strict` で失敗すること。`git status` で `node_modules/`・`dist/` が管理外。Docker の最小コピー(`package.json`・`package-lock.json`・`.npmrc` のみ)で `npm ci` が通ること
4. **レビュー(`code-reviewer`)**: `apps/web` 全体を、設計 E・F・0000 との整合の観点でレビュー。テストコードはないので `test-reviewer`・`web-ui-reviewer` は省略(プレースホルダー 1 画面で、描画は検証フェーズで確認するため)
5. **記録(メイン)**: 作業記録(実際の版・環境変数名・Node の用意の仕方・設計との乖離・未対応事項)と `STATUS.md` を更新。`task-reviewer` は小規模のため省略(完了チェックリストをメインが確認する)

## 方針・注意

- Docker の `node:24` が 24.15.0 以上であることを確認する。満たさない場合は、タグ(`node:24.15` 以降)を固定して使う
- docker run のボリューム経由で `node_modules` がホストに残らないよう、検証はコピーした作業ディレクトリ(スクラッチ)で行うか、終了後に削除する。`package-lock.json` だけを `apps/web` に持ち込む
- 実際の版が設計の確認版(E 2.1)から大きく外れる場合は、理由を作業記録に残す
- 範囲外の依存・機能は足さない
