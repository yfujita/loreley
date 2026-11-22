# 0001 要件確認

日付: 2026-11-22
工程: 要件確認(requirements-clarifier 2回呼び出し+ユーザー確認)

## 実施内容

- `0000` / `STATUS.md` と関連設計(機能設計 ui-admin-functions-v0.1、admin-view-v0.1、design-system-v0.1、SD v0.8 §7、crawler-api v0.4、crawler/indexer module-structure)を確認。
- requirements-clarifier の質問を AskUserQuestion でユーザーに確認し、回答を確定した。`0000` は変更していない。

## ユーザー確定事項(2026-11-22)

| # | 論点 | 確定内容 |
|---|---|---|
| Q1 | 持ち越し論点(AF-U-1 死活、AF-U-13 cron TZ、要約有効/無効) | 本設計で決める。既存設計(SD・crawler-api・indexer-api)は変えず、変更が要るものは「追従改訂の申し送り」に書く。cron TZ は Admin API の環境変数で持つ |
| Q1' | Indexer の死活 | **SD §7.3(api は indexer に接続しない)の緩和を前提に、Admin API が Indexer の `/healthz` を直接読む**(当初の「ハートビート等から推定」案から変更)。SD は本タスクで改訂せず、「SD v0.9 での §7.3 改訂(`api`→`indexer` の `/healthz` 読み取りの許可)が前提」と申し送りに明記する |
| Q2 | 配置 | Admin API は `api` コンテナ内の admin パッケージ。Web UI は `api` が静的配信(同一オリジン、CORS 不要)。Search API/MCP は設計対象外 |
| Q3 | パス | `ui-admins` ではなく `ui-admin` |
| Q3-a | 構成 | API 設計書は `docs/v0.x/system-design/api/admin/`、api 共通の基本設計を `docs/v0.x/system-design/api/` に別文書で追加。フロント2文書は `docs/v0.x/system-design/ui-admin/frontend/`。空の `search-api/` は触らない |
| Q3-b | 追従改訂 | `CLAUDE.md` の参照先追記のみ本タスクで実施。SD・PD・crawler-api 等は変更せず申し送り |

## 確定した要件(requirements-clarifier 報告より)

- 目的: Admin 画面の詳細設計(Admin API と Admin UI フロントエンド)。実装・コード・テスト作成はスコープ外。
- API 技術スタック: Python 3.12、FastAPI、uvicorn(単一プロセス)、pydantic / pydantic-settings、opensearch-py(同期)。Crawler への HTTP は urllib3(CM-P-29 に倣う案)。環境変数接頭辞は `LORELEY_API_`(推奨案)。AST 依存ルール検査・`tests/fakes/` の慣習を踏襲。
- フロント技術スタック: 承認済み = Vuetify 4.3.4(exact pin)、TypeScript 6.x、`@mdi/js`、自前ナビ。案から確定 = Vue 3、Vite、Vue Router、TanStack Vue Query、Vitest、`vite-plugin-vuetify`、ESLint/Prettier、Playwright(E2E テスト方針までを設計対象とし、テストコード・設定ファイルは作らない)。
- 既存設計でそのまま使うもの: ダッシュボード更新間隔 30 秒、メンテナンスフラグは Admin API が書かない(AF-19 は表示のみ)、Dashboards への導線は外部リンク(AF-20)、しきい値検証は Admin API のみ(SD §3.5)、時刻は ISO 8601(UTC)で返す。

## 成果物(6文書。すべて新規 v0.1)

1. `docs/v0.x/system-design/api/api-base-design-v0.1.md`(api 共通基本設計)
2. `docs/v0.x/system-design/api/admin/admin-api-v0.1.md`(API 仕様書)
3. `docs/v0.x/system-design/api/admin/admin-api-architecture-v0.1.md`
4. `docs/v0.x/system-design/api/admin/admin-api-module-structure-v0.1.md`
5. `docs/v0.x/system-design/ui-admin/frontend/ui-admin-frontend-architecture-v0.1.md`
6. `docs/v0.x/system-design/ui-admin/frontend/ui-admin-frontend-module-structure-v0.1.md`

`0000` の成果物パス(`ui-admins/api/ui-admin-api-*`)から、API 系の配置と名称が変わる(ユーザー確認済み。`0000` はユーザー記載のため未修正)。更新する既存文書は `CLAUDE.md` の参照先のみ。

## 受け入れ基準案(完了条件の具体化)

1. 6文書が所定パスに存在し、冒頭に版・改訂履歴・参照元がある
2. 機能設計の MVP 全機能(AF-1〜20)が API エンドポイントに対応づけられ(トレーサビリティ表)、画面仕様 D1・S1〜S4・J1・J2・X1・O1 の必要項目がすべて API 応答で定義されている
3. 各エンドポイントに パス・メソッド・リクエスト・応答・エラー・Crawler/Indexer/OpenSearch/Store層との対応がある。Crawler 6 API の写像(400・404・409・503 等)と接続エラー時の扱いを含む
4. SD の制約(`loreley-jobs`/`loreley-deletions` は読み取りのみ、しきい値検証は Admin API 等)に反しない。反する点(SD §7.3 の緩和)は申し送りに明記
5. 持ち越し論点(AF-U-1・3・5・6・7・9・10・13、admin-view 10.4)が「決めた/案/後続」で状態表示されている
6. フロント設計が design-system 10 章・admin-view の route `meta`・テンプレート4型・共通コンポーネントと矛盾せず、Router・Query・API クライアント層・テスト方針(Vitest・Playwright・`data-testid`)が定義されている
7. 決定・案・未決を区別する ID 表記(CAPI-K/P/U 型に倣う)がある
8. 申し送り(SD §7.2・§7.3・§7.5・§12.1、PD 追記 4 点、crawler-api の `/healthz` 位置づけ、機能設計 AF-17 追記など)が 1 か所にまとまっている
9. document-reviewer を通し Critical 指摘なし
10. `CLAUDE.md` 参照先が更新済み。コード・テスト作成なし。SD・PD・既存機能設計・画面仕様は未変更

## planner / 設計に委ねる事項(推奨案つき。プランで提示し承認を得る)

- ページング: S1 は全件返却(クライアント側)。J1・X1 はサーバー側(`page`/`itemsPerPage`/`sortBy`)、深いページ上限あり
- エラー応答: 統一形式(`code`/`message`/項目別 `details`)。Crawler 400・404 は写像、409 は拒否理由 code と既存ジョブ情報、503・接続エラーは読み取りは継続し書き込み系のみ失敗
- `config_invalid`: 案(b)=Admin API が送信前に項目別検証、Crawler の message は上部アラートのフォールバック
- `lock_held`: 成功扱いにせず 409 で既存ジョブと「指定は反映されていない」を返す(SD §14.4 の冪等成功案は不採用)
- AF-U-6/9/10: リース切れ=実行中かつリース期限超過、最終クロール完了日時=成功・一部成功の `finished_at` 最大値、登録結果=`loreley-jobs` 保存値(途中/確定を示す)
- X1: タブ件数は各取得で併せて返す。スキップ文書の「既存/新規/確認できません」は検索インデックスの `external_id` 有無で導出
- O1: クラスタヘルス・インデックス・シャード・ノード名を1応答で全件返却、絞り込みは画面側
- `ttl`・`min_delete_count`: 型・非負・int64 範囲のみ検証
- D1: 取得タイムアウトは数秒、失敗は「判定不能」。**Indexer・Crawler は `/healthz` を直接取得**(Q1' により変更)。`api` は応答できていれば正常、`web` は静的ファイルの存在で判定、任意コンポーネントは環境変数 URL の有無で判定
- 要約の有効/無効: 二重管理を避け Admin API は「返さない」(画面は条件付き文言のまま)
- Dashboards 導線: `api` の環境変数でブラウザ到達可能な URL を設定可、未設定ならリンク非表示
- URL: `/api/admin/v1/...`。OpenAPI は内部向けに公開しフロントの型生成に使う

## 留意点

- Admin API が Crawler/Indexer の `/healthz` を呼ぶことは crawler-api の「Admin API 契約外」(CAPI-P-19、§4.7)と食い違う → 申し送りに明記
- cron TZ を Admin API 環境変数で持つため Crawler の TZ と不一致が起こりうる → 運用前提として記載
- Crawler 起動時の回復中は接続エラー(crawler-api §3.1、CAPI-U-1)→ Admin API での返し方は必須設計項目
- 実機 Vuetify 4.3.4 での確認、`@mdi/js` の社内ポリシー扱いは実装時の確認事項として引き継ぐ

## 未対応事項

- 上記「委ねる事項」はプランで提示してユーザー承認を得る
- 次: planner でプラン作成 → ユーザー承認
