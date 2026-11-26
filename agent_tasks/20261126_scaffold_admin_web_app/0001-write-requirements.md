# 0001 要件定義(0000)の記載

- 日付: 2026-11-26
- 経緯: ユーザーの依頼(「要件定義も記載して」)により、メインエージェントが `0000-requirements-definition.md` を記載した。通常は要件定義の記載はユーザーが行うが、今回はユーザーの明示的な依頼による
- 参照元: E v0.2(2 章・3.1〜3.5・11.1・12.8)、F v0.2(2.1・2.4・8.9)、`20261126_add_web_container_nginx` の 0000・0002、実環境(ホストの Node 25.2.1 が設計の範囲外。`apps/web` なし。`.gitignore` に `node_modules/`・`dist/` なし)
- 記載で決めた範囲: 設計で警告 0 件・`npm audit` 0 件と確認済みの 11 パッケージだけを入れ、`vite build`・`vue-tsc`・dev サーバーが動く最小構成にする。Vitest・ESLint・Hey API・Playwright・vue-query は後続タスク(FARC-U-25)。dev プロキシの既定の転送先は `http://127.0.0.1:8090`(B+C の `WEB_HOST_PORT` の既定値と整合)
- 「要確認」4 点を 0000 の末尾に列挙した(依存の範囲・Router の有無・検証用 Node の用意・`.gitignore` の置き場。推奨案つき)
- 変更したファイル: `0000-requirements-definition.md`、`STATUS.md`
- 未対応事項・次にやること: ユーザーが 0000 をレビューし、「要確認」に回答 → `requirements-clarifier` → プラン作成(ユーザー承認)→ 実施。完了後に `20261126_add_web_container_nginx` を再開する
