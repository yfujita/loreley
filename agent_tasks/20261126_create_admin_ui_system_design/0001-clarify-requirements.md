# 0001 要件確認の結果

- 日付: 2026-11-26
- 実施者: `requirements-clarifier`(報告)/ メインエージェント(保存)
- 結果: `STATUS: REQUIREMENTS_READY`(1 回目は `NEEDS_USER_INPUT`。ユーザーが Q1〜Q3 に回答して解消)

## 目的

Admin View を実装できるように、フロントエンドのシステム設計を整える。実装済みの Admin API(実際の OpenAPI)との整合を取り、構成・責務・依存関係、画面と API の対応、ビルド・配信・テストの方針をはっきりさせる。実装開始を妨げる未決事項は、解消するか前提タスクとして示す。

## 成果物

1. `docs/v0.x/system-design/ui-admin/frontend/ui-admin-frontend-architecture-v0.2.md`(新規)
2. `docs/v0.x/system-design/ui-admin/frontend/ui-admin-frontend-module-structure-v0.2.md`(新規)
3. 既存設計との不整合・未決事項・申し送りの整理(各 v0.2 の確認状況の章と、`docs/v0.x/system-design/api/api-base-design-v0.1.md` 9 章の HO の表)
4. フロント実装の前提タスクの一覧(v0.2 と HO に記載)

v0.1 の 2 本は残し、変更しない。

## ユーザーの回答(確定)

| # | 質問 | 回答 |
|---|---|---|
| Q1 | v0.2 の作り方 | **書き直して再構成する**。v0.2 だけ読めば実装を始められる内容にする。FARC-P / FMOD-P の承認済み方針は中身を保って引き継ぎ、ID 体系(FARC-K/P/U、FMOD-K/P/U、I-n)も引き継ぐ。経緯・履歴は改訂履歴の「v0.1 からの変更点」にまとめる |
| Q2 | 技術検証の範囲 | **型生成とビルドに直結する点だけ、使い捨ての検証**(下記) |
| Q3 | API 修正の扱い | **整理のみ・前提タスク化**(下記) |

承認済みの方針を変える場合は、変更理由と影響範囲を整理してユーザーの承認を取る(要件 0000 の制約)。

## スコープ

含む: 技術スタックと依存 / アプリ構成・ルーティング・状態管理 / API クライアントと型生成 / データ取得・キャッシュ・ポーリング・更新 / エラー処理・フォームと検証 / ビルドと静的配信・開発環境 / ディレクトリ・モジュールの分割と責務・依存ルール・共通化 / 画面とモジュールの対応、Search View と共有する部分の分け方 / 5 画面群と Admin API の対応 / テスト・品質の方針 / Docker・compose のビルド・配信の方針 / 設計書のレビュー

含まない: Admin View の本実装と `apps/web/` の作成 / Admin API・Crawler・Indexer の実装変更 / Dockerfile・compose の実装変更 / テストコードの本実装 / 機能追加・UI の再設計 / Search View・Search API・MCP の設計 / 認証・認可

## 技術検証の範囲(Q2)

リポジトリの外(スクラッチ)で行う使い捨てに限る。結果は作業記録と v0.2 に書く。

- (a) `python -m loreley_api.admin.openapi_export` で書き出した実際の OpenAPI から、Hey API で型・クライアント・Query を生成できるか。生成物の構成、`throwOnError` の既定、パス値のエンコードも見る(FARC-U-4・5・18、FMOD-U-2・3)
- (b) Vite 8 + `vite-plugin-vuetify` + Vuetify 4.3.4 の組み合わせでビルドできるか(FARC-U-1)
- (c) 依存の最新版と Node 要件の再確認(FARC-U-10)

上記以外の FARC-U / FMOD-U は実装時の確認事項として申し送る。

## API 側の修正事項(Q3)

本タスクでは実装を変えない。次の 3 件を「フロント実装の前提タスク」として一覧化し、v0.2 にそれぞれへの依存を書く。

- (a) OpenAPI の `ttl_days` / `ttl_seconds` が `integer | null`(既定 null)だが、実行時は明示的な null を拒否する。型生成の前に直す必要がある(implement_admin_api 0017・0021 の申し送り)
- (b) `/admin/` の静的配信と SPA フォールバックが未実装(`web_dist.py` は死活確認のみ)。Dockerfile の Node ビルドステージとビルドコンテキスト(HO-36・37)も同じ扱い
- (c) `openapi_export.py` の docstring は「書き出した JSON はコミットしない」だが、FARC-P-6 / HO-38 は「OpenAPI JSON と生成コードをコミットする」。どちらに揃えるか

前提タスクを 1 本にまとめるか分けるかは、設計の作業中に案を出す。

## 前提(ユーザーの異議なし。採用)

- API の正本: Admin API 設計書(B = admin-api-v0.1)と実装・OpenAPI が食い違うときは、実装と OpenAPI を正とする。B 側の差分は申し送りにし、B の追従改訂は本タスクでは行わない
- 申し送りは `api-base-design-v0.1.md` 9 章に集約する。追従改訂は HO の追加と状態更新に限り、画面仕様・DS・B / C / D の本文は改訂しない
- 整合性の確認方法: 書き出した実 OpenAPI と画面別 EP 対応表を照合し、EP・項目・code の対照と差分の一覧を作業記録と v0.2 に残す
- 設計書のレビューは `document-reviewer`。Critical / Important が解消されていれば完了とする
- E2E は方針設計まで(FARC-P-38 を維持)
- Docker / compose はビルド・配信の方針と HO-36 / 37 への要求まで

## 完了条件

要件 0000 の 9 項目に従う。「整合性が確認されている」は OpenAPI 照合の記録で、「実装開始を妨げる未決事項の解消、または前提タスクの明確化」は検証 (a)〜(c) の結果と前提タスク一覧で満たす。

## 未解決事項・次にやること

- v0.1 の承認済み方針のうち変更が必要になる項目は、調査・検証の後に一覧にしてユーザー承認を取る(プランに承認ゲートを入れる)
- 前提タスクの切り方(1 本か分割か)は設計の作業中に案を出す
- 次: `planner` で作業プラン(`0002-work-plan.md`)を作り、ユーザーの承認を得る
