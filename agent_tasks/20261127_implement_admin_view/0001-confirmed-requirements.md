# 0001 確定した要件(要件確認の結果)

作成日: 2026-11-27 / 工程: 要件確認

`requirements-clarifier` の洗い出し(STATUS: NEEDS_USER_INPUT)と、ユーザーの回答を踏まえた確定事項。`0000-requirements-definition.md` は書き換えていない。

## ユーザーの回答(確定)

| # | 質問 | 回答 |
| --- | --- | --- |
| Q1 | 実機確認・UIレビューで行ってよい変更操作の範囲 | **専用環境で全操作を許可**。本タスク用に別の compose プロジェクト名・テスト用 `CRAWLER_DOCUMENTS_DIR`(既存ボリュームと分離)で起動し、登録・編集・クロール起動/取消/再実行・ロック解放・削除まで実施して後始末する。他のコンテナは止めない |
| Q2 | 実装時確認事項の結果・設計との差異の反映先 | **作業記録のみ**。設計書(E/F v0.2・DS・画面仕様・A/B)は改訂せず、追従は別タスクへ申し送る。更新するのは `apps/web/README.md` と、実装で古くなる運用文書(`deploy/compose/README.md` など)のみ |
| Q3 | アイコンに `@mdi/js`(Apache-2.0)を使ってよいか | **使ってよい**。DS ゲートBの構成(`@mdi/js` + `vuetify/iconsets/mdi-svg`)のまま進める |

## 確定した要件(clarifier 報告より)

- 対象: 機能設計 AF-1〜AF-20 の MVP 機能を、9画面(D1・S1〜S4・J1・J2・X1・O1)、共通シェル、SPA内404、ダイアログ DLG-1〜5 で実装する。AF-19(メンテナンス中)は DLG-1 の拒否表示と J2 の理由、AF-20(Dashboards 導線)はサイドバーの外部リンクで扱う。cron のタイムゾーン表示(UC-19)は S2・S4 に EP-14 の値を出す。
- 前提タスクは完了済み: OpenAPI 型修正(8732c2a)、web コンテナ Nginx(PR #26 / 8a20d67。`web` は `127.0.0.1:8090` 公開、`api` は非公開)。FARC-U-21(Nginx 越しの `%2F`・`%2E` 保持)は `20261126_add_web_container_nginx/0009` で解消済み。
- OpenAPI 書き出し手段は実装済み: `uv run python -m loreley_api.admin.openapi_export <出力パス>`(`apps/api/src/loreley_api/admin/openapi_export.py`)。
  - `gen:api` は「書き出し(`apps/web/openapi/admin-v1.json`、F 2.4)→ `openapi-ts`(Hey API、`infiniteQueryOptions: false`)→ `src/admin/api/generated/`」の2段。OpenAPI JSON と生成コードはコミットする。
- CI はスコープ外。「再生成で差分ゼロ」は、ローカルの npm スクリプト(`gen:api` 後に `git diff --exit-code` と `git status --porcelain`)として用意し、品質ゲート手順(E 11.2)にまとめる。
- 設計 F 7.1 / E 10.2 の `tests/integration/<名前>/`(`web` 経由の実 API スモーク)は**作らない**(スコープ外「実環境を対象とした独立した結合テストスイート」に該当)。代わりに要件6の実機確認を手動で行い、作業記録に残す。
- テストは E 10 / F 7 のとおり: Vitest(jsdom)による単体・コンポーネント・契約テスト、Playwright(Chromium、`page.route` による API モック、未モックの `/api/` は失敗扱い)。フィクスチャは共有し、生成型で `satisfies` する。
- 依存ルール(R1〜R17)は ESLint `no-restricted-imports` で検査。表現しきれなければ `eslint-plugin-boundaries` / `dependency-cruiser`(FMOD-U-1)。
- 開発サーバーの `/api` 転送先は既定 `http://127.0.0.1:8090`(`LORELEY_DEV_API_TARGET` で上書き。`apps/web/vite.config.ts` で実装済み)。
- `apps/web/Dockerfile` は `COPY` を個別列挙しているため、ビルドに必要なファイル(`public/` など)を足したら更新する(`20261126_add_web_container_nginx/0012` の申し送り)。

## 前提として置く事項

- ブラウザ確認: 自動 E2E は Chromium のみ。Firefox 128・Safari 16.4 の実機確認(FARC-U-15)は手元で可能な範囲(Playwright の Firefox・WebKit 等)で最小限に行い、指定版で確認できなかったものは未確認として記録する。
- X1 の「要約未生成」タブは要約機能(LLM)未実装のため実データでは確認できない。モックで検証する。
- 実装時確認事項(FARC-U-2・8・9・13・16・20・22〜26、FMOD-U-1・4〜6・9〜13)は実装中に検証し結果を作業記録に記録する。設計の方式が変わるもの(例: FARC-U-22 の `withKey` → 独自 Options、jsdom 不可で Browser Mode へ変更)はユーザーに確認する。
- 実機確認の compose でポート 9200 が別プロジェクト(Fess)と衝突しても、他のコンテナは止めず報告する。
- コミット・PR はユーザーの指示があるまで行わない。
- ライブラリの版は E 2 章の固定方針に従う。設計に挙がっていないライブラリは追加しない。

## プラン作成時に決める事項

- フェーズの分け方と、各フェーズのレビュアー(code-reviewer / test-reviewer / web-ui-reviewer / task-reviewer)の割り当て。
- Q2 の回答により、設計書改訂は行わないため document-reviewer は原則不要(README・運用文書の更新分のみ要否を判断)。設計書追従の申し送り先(別タスク起票)をプランの最終フェーズで扱う。
- 実機確認(専用 compose 環境・テストデータ・後始末)の手順。

## 未対応事項

- なし(上記はプランで扱う)。
