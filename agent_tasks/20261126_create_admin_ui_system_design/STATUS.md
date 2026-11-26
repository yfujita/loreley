# タスク状態

## 基本情報

- 状態: done
- 現在工程: 完了(PR #21 作成済み。外部レビュー指摘への対応を 0018 に記録。マージ待ち)
- 最終更新: 2026-11-26
- 最新作業記録: 0018-pr21-review-fixes.md

## 現在の状況

Admin View のフロントエンド設計 v0.2 を作成し、レビューを完了した。ブランチ `feature/create-admin-ui-system-design`(基準 SHA `6a8b685f121616a5d3171df99f75eb4ebad3ed88`)。コミット・push・PR 作成済み(ユーザーの指示。マージはしない)。

成果物:
- `docs/v0.x/system-design/ui-admin/frontend/ui-admin-frontend-architecture-v0.2.md`(E。新規。約 251KB)
- `docs/v0.x/system-design/ui-admin/frontend/ui-admin-frontend-module-structure-v0.2.md`(F。新規。約 180KB)
- `docs/v0.x/system-design/api/api-base-design-v0.1.md`(A。9 章に HO-52〜68 を追加し既存 HO の状態を更新、9.4 にゲート4・5 の記録。冒頭の索引的な記述も更新)

変更したのは上の 3 ファイルと `agent_tasks/` のみ。`apps/`・`deploy/`・`tests/`・B・C・D・DS・画面仕様・v0.1 の E・F は未変更。`apps/web` は作っていない。

主な結果:
- 実装済み Admin API の実 OpenAPI(14 EP)と B・E・F を照合し、差分を v0.2 に反映するか A の HO に申し送った(0004)
- 技術検証(使い捨て・リポジトリ外): Hey API 0.99.0 の生成、Vite 8 + Vuetify 4.3.4 のビルド、Nginx 配信を確認した(0005)
- ユーザー指示により、静的配信を `api` から `web` コンテナ(Nginx)に変更した(0003。FARC-K-4)。ゲート4(0007)・ゲート5(0012。G5-1〜G5-3)で承認済み。G4-2 は `web` 経由に一本化(`api` は publish しない)
- レビュー: `document-reviewer` 4 並列(Critical なし、指摘 34 件)→ 対応・再レビュー(Critical・Important なし)→ `task-reviewer`(Critical・Important なし)

## 次のアクション

1. PR のレビュー・マージ(ユーザー)
2. 前提タスク A・B+C の要件 0000 を記載する(ユーザー。枠は起票済み: `20261126_fix_admin_openapi_types`、`20261126_add_web_container_nginx`)
4. 前提タスク A(`apps/api`: `ttl_*` の OpenAPI 型・`openapi_export.py` の docstring)→ フロント実装(型生成の前が望ましい)。B+C(`web` コンテナ・compose・`api` の EP-13 の `web` 判定の置換・IT の追従)は `apps/web` の最初のスキャフォールドの後に着手し、`web` 経由の接続確認と初回リリースの前に完了(E 12.8、A の HO-52〜58)

## 未解決事項

- **実装時に確認する未検証事項**(FARC-U の一覧は E 12.4、F は 8.4): FARC-U-2(`VDataTableServer`)、U-9(jsdom の相対 `baseUrl`)、U-15(Firefox 128・Safari 16.4 の実機)、U-20(`vite-plugin-vuetify` の Vite 8 明示対応なし)、U-21(Nginx 越しの `%2F`・`%2E`)、U-22(API クライアントの設定の実機確認)、U-23(EP-01 の反映遅れ)、U-24(`stalled=true` の経路)、U-25(依存全体の `npm ci`・`npm audit`)、U-26(Docker マルチステージ・EP-09 の複数ページ・`status=null` の実データ・`isLoading`)、FMOD-U-12・13。Nginx の数値(`proxy_read_timeout`・`client_max_body_size`・ヘッダ)
- B・C・D・A 本文の追従改訂は A の HO-59〜65 で申し送り済み(本タスクでは行わない)
- implement_admin_api の申し送りのうちフロント非関連(D 5.0 の `lock_state`、`ErrorCode` の固定文 10 件、D 4.12(c)、C 4.1・9 章の 2 MiB)は本タスクの対象外(ユーザー確認済み。A の HO には足さない)で、implement_admin_api の STATUS に残る

## ユーザー判断待ち

- なし(完了報告での確認 4 点は解決済み。0017)
