# 0009 フェーズ3-1: E(フロントエンドアーキテクチャ)の完成

日付: 2026-11-22
担当: document-writer(メインが記録)

## 変更ファイル

- `docs/v0.x/system-design/ui-admin/frontend/ui-admin-frontend-architecture-v0.1.md`(733 行。新規)。A・B・DS・画面仕様・CLAUDE.md・apps/ は変更なし(writer が `git status` で確認)。

## 構成

0 この文書について / 1 位置づけ / 2 技術スタックとバージョン固定 / 3 ビルド・配信 / 4 アプリ構成 / 5 データ取得層(5.7=画面別の取得・エラー方針表、5.8=mutation と invalidate、5.9)/ 6 エラー処理(6.1〜6.7)/ 7 フォームと検証(7.1〜7.6)/ 8 状態管理 / 9 a11y・Vuetify 注意 / 10 テスト方針 / 11 静的解析・品質 / 12 確認状況(12.1〜12.6)

## ID

- FARC-K-1〜9(確定。DS 10.1・ユーザー確定・既承認文書の引用)、FARC-P-1〜28(案。承認済みの案(ゲート2)は P-1 Hey API、P-2 `/admin/` 配置・フォールバック、P-14 取消 409 の成功扱い)、FARC-U-1〜17(未決・実装時確認)、I-80〜87
- 主な案: P-3 Node 22.18 以上または 24 以上(推奨 24 LTS)、P-4 固定範囲、P-6 生成物のコミットと CI 差分検査、P-7 API クライアント(読 45 秒・書 90 秒の仮値)、P-8 Query 既定値と key factory、P-10 サーバー側ページング、P-12 S4 の編集専用取得、P-13 エラー変換表、P-15 結果不明の扱い、P-20 Docker 構成、P-21 Vitest、P-22 Playwright、P-23 静的解析、P-27 部分失敗、P-28 S4 `malformed`
- 不整合: I-80(DS の「vue-tsc が動かない」と「公式未対応」)、I-81(admin-view の route `path` と `/admin/`)、I-82(A 8「ビルドは apps/api」と compose のビルドコンテキストでは `apps/web` を含められない)、I-83(DS 5.3 の `meta.title` と admin-view 4.2 の動的 title)、I-84(sources 2.4 の `reason` 表に `range`・`exclusive`・`config_invalid` がない)、I-85(URL クエリ・`documentTabs` の kebab と API の表記差)、I-86(J1 の並べ替え列。解消寄り)、I-87(画面仕様に状態記述がない: O1 `truncated`、X1 データソース不在、S2・S4 `malformed`、J2 の `stalled`・`rerunnable` が `null`)

## B 本文に合わせて直した箇所(E 12.6)

`unavailable` の扱い(画面は理由を区別せず同表示)、J2 の `stalled`・`rerunnable`・`latest_for_source` が `null` のとき取消・再実行を出さない、番兵日時は「期限切れ」、EP-03・04 の入力(厳密な型、`ttl_days` か `ttl_seconds` の一方、小数第 2 位)、`reason` 8 値、EP-08 `lock_state=unknown`、EP-13 `reason` 6 値、EP-09 複合値 `active`、保存系 `crawler_response_lost` は再送が安全・解放は `released=false` になりうる、`/` を含む ID の 404、`web` ファイル欠落時の扱いと AAPI-U-10 への回答

## F への引き継ぎ

`apps/web/` の構成(生成コード、API ラッパー、key factory と composable、エラー変換表、Router と `meta`、テンプレート4型、DS 共通部品(`StatusTag`・`KeyValueList`・確認ダイアログ・`FilterBar`・`CountTabs`・`ShardMatrix`・`SummaryBand`・`ComponentTile`・`AutoRefreshSwitch`・`PatternListInput`・`SettingSwitch`・`FormDisclosure`・`StatList`・`WarningList`)、テスト、`mockApi`・フィクスチャ)/ E 5.7 の表を「画面→route→ページ→composable→EP」に展開 / 定義表の置き場(`navGroups`・`documentTabs`・`dashboardComponents`・URL↔API 対応・エラー変換表・フォーム `field` 対応)/ 依存ルール(ESLint `no-restricted-imports` を第一候補)/ トークンと `defaults` の共有置き場 / ルート遅延読み込みの判断(`router.onError`)

## 申し送り候補(A 9章へ)

- compose と A 8: `api` のビルドコンテキスト変更(I-82)、CI で型生成の再生成差分を検査する要求
- DS: 10.1 の「vue-tsc が動かない」→「公式未対応」(I-80)、Hey API・「API の型は別タスク」・案から確定になった構成要素の反映、5.3 の `meta.title` 動的化(I-83)
- 画面仕様: admin-view 4.2 の route `path` が `/admin/` からの相対である旨(I-81)、sources 2.4 の `reason` 表への追記(I-84)、状態の追記(I-87)
- README・導入手順: Node の版、型生成と生成物コミットの手順
- 実装時確認事項: FARC-U-1〜17

## writer の注記・未照合

- B の 11.1・11.2・11.6・11.7 は照合していない(E 12.1 に明記)→ R3 で確認
- 本文に「推測・実装時確認」と明記した3点: Vue Query v5 の `isLoading` の意味、Playwright の時計操作、compose の `additional_contexts` の対応版
- ゲート3で承認を取る項目: FARC-P の案全般(B の AAPI-P-16〜18・24〜34 に依存する P-27・P-28 を含む)

## 次

- R1(A・B)の結果待ち。R1 解消後に C → D と F(F は B 確定後)
- R3(E・F)は F 完成後
