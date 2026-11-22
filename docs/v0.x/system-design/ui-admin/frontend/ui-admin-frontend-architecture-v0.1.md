# ui-admin フロントエンドアーキテクチャ設計書 v0.1

- 版: v0.1(ドラフト。A・B 本文に基づく。ゲート3(2026-11-23)の承認を反映済み。実装はスコープ外で、実装時確認事項(FARC-U)が残る)
- 更新日: 2026-11-23
- 前版: なし(初版)
- 位置づけ: Admin View(管理者向け Web UI)の**フロントエンドの技術構成**を定める。技術スタックとバージョン固定、ビルド・配信、アプリの組み立て(シェル・route `meta`・ガード)、データ取得層(型生成・API クライアント・TanStack Vue Query)、エラー処理の UI 対応、フォームと検証、状態管理、テスト方針、静的解析を書く。見た目・部品・画面ごとの仕様は DS(`design-system-v0.1.md`)と画面仕様、API の中身は A・B が正本で、本書は**参照して合わせる**。ディレクトリ・モジュール分割・画面×モジュールの対応は F(`ui-admin-frontend-module-structure-v0.1.md`。v0.1。作成済み)が正本。
- 本書は **Admin 画面の詳細設計タスク(`20261122_create_admin_system_design`)の成果物**で、SD・PD・DS・画面仕様・機能設計・crawler / indexer 設計を変更しない。既存設計と食い違う点・追従改訂が要る点は `I-n`(12.5)に挙げ、申し送りは A の 9章(HO-1〜HO-50)に集約する。本書は申し送りを持たない。
- 改訂履歴: v0.1 は初版(フェーズ3-1)。初稿は B 骨子に基づいて書き、B 本文の完成後に照合して直し、さらに B・A の R1 修正に追従した(`unavailable` の正式なパス、`lock_state` の排他、Content-Type の規約、`ttl` 下限 1、しきい値の桁、`connector_config` 自身の `config_invalid`、K の区分整理。12.6)。前者の照合では(部分失敗の `unavailable` のキーと理由コード、`stalled`・`rerunnable` の `null`、`deletion.fetched_at`、番兵の日時、EP-03・04 の入力の規約、保存系の再送など。12.6)。その後、R3 の指摘(区分の統一、`viewState`・パンくず・`featureFlag`・ロック状態の写像、マウント時の再取得ほか)と、0020・0022 の B・A の追従(値の読めない `null`、`source_missing`)に対応した(12.6)。フェーズ5の統合(2026-11-23): 申し送りへの参照を A 9章の実番号に置き換え、関連文書の表に C・D を足し、更新日を統一した。R4 指摘の反映(2026-11-23): FARC-K-8 を欠番にして FARC-P-38(承認済みの案(ゲート1)。「テストコード」の部分は案)へ移し、4.5 に `.`・`..` だけの ID の例外を足し、12.6 の B の案 ID の範囲を 12.4 に揃えた。B の内容は複製せず、EP 番号・code 名・項目名の引用に限る。 ゲート3の承認(2026-11-23)の反映: 案の区分を承認済みの案(ゲート3。2026-11-23)に更新した(設計の内容は変更なし)。PR #10 のレビュー指摘への対応(2026-11-23。0037・0038): 一覧の `unavailable` を行単位にする B の変更(AAPI-P-42)に追従した(5.7・5.9・6.2。FARC-P-27・36 を修正、FARC-P-39 を新設。区分は承認済みの案(ゲート3)の修正で、`-K-` は増やしていない)。

## 0. この文書について

- 対象: `apps/web/` の Admin View(Vue 3 の SPA)。`api` コンテナが静的に配信する(A 2.1。同一オリジン)。
- 範囲外(参照のみ): 見た目・部品・文言・レスポンシブ(DS・画面仕様)、エンドポイント・DTO・エラー code・環境変数(A・B・C)、ディレクトリ・モジュール分割(F)、Search View(配置の境界だけ。1章)。
- 読み方: 1章で本書と他文書の分担、2〜3章で技術スタックとビルド・配信、4〜5章でアプリの組み立てとデータ取得、6〜7章でエラーとフォーム、8〜9章で状態管理と a11y、10〜11章でテストと静的解析、12章に確認状況(ID 付きの判断一覧・未確認・B への依存)を置く。
- コード・設定ファイルは作らない。ファイル名・設定項目・型は「要点」「概形」として示す。

区分の凡例(A 0章・B 0章と同じ。`crawler-api-v0.4.md` に合わせる):

| 区分 | 意味 |
| --- | --- |
| 確定 | ユーザーが明示的に回答・確定した事項(出典を書く)、または既承認文書(PD・SD・機能設計・DS・画面仕様・crawler / indexer 設計)の引用 |
| 案 | ユーザーが承認していない提案。確定(`-K-`)にしない。本書の案は、ゲート3(2026-11-23)ですべて承認され、承認済みの案(ゲート3)になった(本文中で「案」と書いた判断は、ID の区分欄が正で、承認済みの案に読み替える) |
| 承認済みの案 | ゲート1(2026-11-22。ユーザー承認)で**方針**、ゲート2(2026-11-22。ユーザー承認)で**具体値・名前**、またはゲート3(2026-11-23。ユーザー承認)で本タスクの案・導出・解釈の扱いが承認されたもの。設計として承認済みだが確定ではない。**既承認文書(DS・画面仕様など)の「承認済みの案」「承認済み」の引用で、本タスクのユーザー確認がないものも、確定にせずこの区分とし、出典を区分欄に書く**。区分欄に承認したゲートを書く。ID は `-P-` のまま。ゲート2の回答で採用が選ばれなかった案は「不採用として扱った(解釈)」とし、ID は欠番として残す(ゲート3(2026-11-23)で不採用のままでよいと確認済み) |
| 未決 | 決めていない。実装時に確認するものを含む |
| 推測 | 根拠が弱い想定 |
| 導出 | 他の記述から導いた事項 |

ID 体系: `FARC-K-n` / `FARC-P-n` / `FARC-U-n`。既存設計との不整合は `I-n`(本書の予約範囲は I-80〜89 と I-120〜129。A は I-60〜69、B は I-70〜79、既存設計は I-1〜52)。A の ID は `BAPI-*`、B は `AAPI-*`。画面仕様の通し番号は `#n`(`admin-view-v0.1.md` 10.1)、機能設計は `AF-n`、DS・admin-view の節は `DS 4.5`・`admin-view 4.2` のように書く。エンドポイントは B の `EP-nn`。

関連文書(いずれも `docs/v0.x/` 配下):

| 略称 | 文書 | 本書との関係 |
| --- | --- | --- |
| DS | `ui-design/design-system-v0.1.md` | トークン・部品(4章)・シェル(5章)・テンプレート(6章)・a11y(8章)・`data-testid`(9章)・技術スタック(10章)の正本 |
| admin-view | `ui-design/admin-view-v0.1.md` | 画面一覧・route `meta`(4.2)・遷移・Admin API への申し送り(10.4) |
| 画面仕様 | `ui-design/admin/{dashboard,sources,jobs,documents,opensearch}-v0.1.md` | 画面ごとの状態・更新・エラー表示・データ項目 |
| 機能設計 | `system-design/ui-admin/ui-admin-functions-v0.1.md` | AF-1〜20 |
| A | `system-design/api/api-base-design-v0.1.md`(v0.1。作成済み) | URL・エラー形式・OpenAPI・静的配信・タイムアウトの正本。9章が申し送り(HO-1〜)の置き場 |
| B | `system-design/api/admin/admin-api-v0.1.md`(v0.1。作成済み) | EP・DTO・Admin 固有 code の正本 |
| C・D | `system-design/api/admin/admin-api-architecture-v0.1.md`、`admin-api-module-structure-v0.1.md`(いずれも v0.1。作成済み) | Admin API の内部設計(導出・環境変数・モジュール構成)。本書は結果としての EP・code だけを使う |
| F | `system-design/ui-admin/frontend/ui-admin-frontend-module-structure-v0.1.md`(v0.1。作成済み) | ディレクトリ・モジュール・画面×モジュール |

---

## 1. 位置づけ

### 1.1 本書が決める範囲

| 事項 | 正本 | 本書での扱い |
| --- | --- | --- |
| 見た目・トークン・共通部品・シェル・テンプレート・状態表示・a11y・`data-testid` の命名 | DS | 参照のみ。Vuetify の設定値は DS 3章に従う |
| 画面一覧・route・`meta`・遷移、画面ごとの状態・更新間隔・文言 | admin-view、画面仕様 | 参照のみ。データ取得・エラーの方針を 5.7 に画面別にまとめる |
| URL 名前空間、エラー応答の形、OpenAPI の方針、静的配信 | A | 参照のみ |
| エンドポイント・リクエスト・応答・Admin 固有 code | B | 参照のみ。EP 番号と code 名だけを引用し、内容は複製しない |
| 技術スタックの版固定、ビルド・配信、データ取得層、エラーの UI 対応、検証方針、テスト方針、静的解析 | **E(本書)** | — |
| ディレクトリ、モジュール分割、依存ルール、画面×モジュール対応 | F | 本書は制約だけを書く |

### 1.2 方針

- **DS・画面仕様と矛盾しない**。矛盾を見つけたときは、本文を DS・画面仕様に合わせ、`I-n` に挙げる(DS・画面仕様は変更しない)。
- **画面の文言は画面仕様が正**。本書は「どの `code` をどこに(どの variant で)出すか」だけを決める(6章)。
- **対応表は 1 か所に持つ**(DS 4.1・DS 12章と同じ考え方)。エラーの変換表、画面別の取得設定、URL クエリと API パラメータの対応を、それぞれ 1 つの表(データ)にし、画面ごとに分岐を散らさない。
- **サーバーの導出結果は画面で再計算しない**(`stalled`・`cancellable`・`rerunnable`・`lock_state`・`existence` など。B 2.9。画面は表示と操作の出し分けだけ)。導出フラグが `null` のとき(`stalled`・`rerunnable`・`latest_for_source`。ロック文書などを読めなかった。B 2.9・5.2)は**「不可」として扱う**: 取消・再実行の操作を出さない(B は `stalled=null` なら `cancellable=false`)。ジョブ記録の値が読めず `status=null` のジョブには、ステータスタグも操作も出さない(B 2.11。`stalled=false`・`cancellable=false`。FARC-P-36)。

### 1.3 Search View との境界

Search View は設計しない。本書の前提は「Admin View は `/admin/` 配下の 1 つの SPA(`base: '/admin/'`)」(BAPI-P-2)。Search View の配置と、同じビルドに同居させるかは未決(BAPI-U-4。FARC-U-17)。DS 11章のとおり、トークンと `defaults` は Admin・Search が共有する 1 組にするため、F はこれらを Admin 専用のコードと分けて置く。

---

## 2. 技術スタックとバージョン固定

### 2.1 構成(区分)

| 項目 | 採用 | 固定の範囲 | 区分 |
| --- | --- | --- | --- |
| UI ライブラリ | Vuetify 4.3.4 | **exact pin** | 確定(DS 10.1 の引用。FARC-K-1) |
| 言語 | TypeScript | `~6.0.x`(6.x 固定は承認済み。パッチの範囲は案) | 6.x 固定=確定(DS 10.1 の引用。FARC-K-1)。`~6.0.x` は案(FARC-P-4) |
| アイコン | `@mdi/js` + `vuetify/iconsets/mdi-svg` | caret + ロックファイル | 確定(DS 10.1 の引用。FARC-K-1)。社内ポリシー上の扱いは未確認(FARC-U-3) |
| ナビ | 自前(`VNavigationDrawer` + `VList` + route `meta`) | — | 確定(DS 10.1 の引用。FARC-K-1) |
| フレームワーク | Vue 3(`^3.5`。Vuetify 4 の peer) | caret + ロックファイル | 承認済みの案(ゲート1。FARC-P-30) |
| ビルド | Vite(確認時点 8.3.x)+ `vite-plugin-vuetify`(確認時点 2.1.x。tree-shaking・SASS 設定) | Vite は **minor 固定**。plugin は caret | 承認済みの案(ゲート1。FARC-P-30)。固定範囲は案(FARC-P-4)。組み合わせの実機確認は FARC-U-1 |
| ルーター | Vue Router 4 | caret | 承認済みの案(ゲート1。FARC-P-30) |
| データ取得 | `@tanstack/vue-query` v5 | caret(v5 系) | 承認済みの案(ゲート1。FARC-P-30) |
| 型・クライアント・Query 生成 | `@hey-api/openapi-ts`(確認時点 0.99.0) | **exact pin**(0.x のため) | 承認済みの案(ゲート2。FARC-P-1。BAPI-P-10) |
| 型検査 | `vue-tsc`(確認時点 3.3.x) | **minor 固定** | 承認済みの案(ゲート3。2026-11-23。FARC-P-4) |
| 単体テスト | Vitest(確認時点 5.1.x)+ `@vue/test-utils` | caret | Vitest は承認済みの案(ゲート1。FARC-P-30)。`@vue/test-utils` と jsdom は案(FARC-P-21) |
| E2E | `@playwright/test`(確認時点 1.65.x) | **exact pin**(ブラウザの版と対にするため) | 承認済みの案(ゲート1。FARC-P-30)。exact は案(FARC-P-4) |
| 静的解析 | ESLint(flat config)+ `typescript-eslint` + `eslint-plugin-vue`、Prettier | caret | 承認済みの案(ゲート1。FARC-P-30)。構成は案(FARC-P-23) |
| スタイル | `sass`(`vite-plugin-vuetify` の `styles.configFile`。DS 3.3) | caret | 推測(必要になる想定。FARC-U-1) |
| パッケージ管理 | npm(`package-lock.json` をコミット。`npm ci`) | — | 承認済みの案(ゲート3。2026-11-23。FARC-P-5) |
| ランタイム | Node.js **22.18 以上の 22 系、24 系、または 26 以上**(Vitest 5 が 23・25 を含まないため)。推奨は **24 LTS** | `engines` に範囲、Docker ビルドステージと CI は 24 に揃える | 承認済みの案(ゲート3。2026-11-23。FARC-P-3) |

「確認時点」の版は、フェーズ0の tech-advisor の報告(作業記録 0004。調査日 2026-11-22)による。本書の作成者は再確認していない。

### 2.2 固定の考え方

| 固定 | 対象 | 理由 |
| --- | --- | --- |
| exact | Vuetify、Hey API、Playwright | Vuetify 4 は新しく週次でリリースされ、DS 10.3 も exact pin・検証してから更新とする。Hey API は 0.x で、更新のたびに生成物が変わりうる。Playwright はブラウザバイナリの版と対になる |
| minor | Vite、`vue-tsc`、TypeScript(`~6.0.x`) | TypeScript の `latest` は 7.0.x(ネイティブ版)だが、`vue-tsc` は TypeScript 7 に**公式未対応**(0004)。6.x に留める。Vite は 8 系の Rolldown と `vite-plugin-vuetify` の組み合わせが未確認(FARC-U-1)のため、minor を固定して検証してから上げる |
| caret + ロックファイル | その他 | `package-lock.json` を正とし、更新は `npm update` を意図して行う |

- 依存の更新は、**再生成(`gen:api`)→ 型検査 → lint → Vitest → Playwright** を通してから行う(11.2)。
- Node の最小は、Hey API(`>=22.18`)・Vite 8(`^20.19 || >=22.12`)・Vitest 5(`^22.12 || ^24 || >=26`)の要件のうち最も厳しいものから導いた(導出)。Vuetify 4.3.4 公式の Node 最小要件は第三者ミラーの値(24.11.1)しか確認できておらず、実装時に確認する(FARC-U-10)。

### 2.3 対応ブラウザ

Chromium 119+ / Firefox 128+ / Safari 16.4+(Vuetify 4 の要件。ユーザー了承済み。DS 10.1。FARC-K-3)。次は未確認(FARC-U-10・15): Vite 8 の既定の `build.target` がこの要件を満たすか、Firefox 128・Safari 16.4 での実機の動き(コンテナクエリ・`<dialog>` まわり)。自動 E2E は Chromium で行い(10.2)、他は実機で確認する。

### 2.4 入れないもの

Pinia、Tailwind、vue-i18n(日本語のみ。DS 10.1)は入れない(承認済みの案(ゲート3)。FARC-P-26)。次も、必要になるまで足さない(承認済みの案(ゲート3)。FARC-P-26): VueUse(DS 4.3 が「使うなら 10章の依存に足す」とする)、フォーム検証ライブラリ(7章)、日時ライブラリ(5.9)、axios などの HTTP クライアント(生成した fetch クライアントを使う。5.3)。

---

## 3. ビルド・配信

### 3.1 Vite の設定の要点(FARC-P-19)

| 項目 | 設定 | 理由 |
| --- | --- | --- |
| `base` | `'/admin/'` | Admin View は `/admin/` 配下(BAPI-P-2。承認済みの案(ゲート1・2))。アセットの URL が `/admin/assets/…` になる |
| プラグイン | `@vitejs/plugin-vue`、`vite-plugin-vuetify`(`styles.configFile` で SASS 変数を上書き。DS 3.3) | tree-shaking とフォント・影などの SASS 設定(DS 3.3) |
| `build.outDir` | `dist/`。**`index.html` を直下に置く** | B 8.1: `web` の死活は `LORELEY_API_WEB_DIST_DIR` 直下の `index.html` が読めること |
| 型検査 | `vite build` の前に `vue-tsc` | Vite は型を検査しない(11.2) |
| テスト | Vitest は同じ Vite 設定を共有 | 10.1 |
| 実行時の設定 | **持たない**(`VITE_*` を画面の挙動に使わない) | 同じ成果物をどの環境でも使えるようにする。環境で変わる値(cron のタイムゾーン、Dashboards の URL)は EP-14 `/meta` から取る(B 8.2。FARC-P-25) |

`index.html` は `<html lang="ja">`(DS 8章)で、外部のフォント・CSS・スクリプトを読まない(外部フォント・CDN を使わない方針は FARC-K-9、外部通信の禁止全般は DS 3.1・FARC-P-32)。

### 3.2 Router の `base` と URL

- `createWebHistory(import.meta.env.BASE_URL)`(= `/admin/`。FARC-P-2)。実 URL は `/admin/`・`/admin/sources`・`/admin/jobs/{jobId}` …。admin-view 4.2 の `path`(`/`・`/sources` …)は **Router の `base` からの相対**と読む(I-81)。
- `/admin/` 配下の未知のパスは、サーバーが `index.html` を返し(A 2.2。承認済みの案)、画面側の `not-found` route(admin-view 4.2。`/:pathMatch(.*)*`)が「ページが見つかりません」を描く。つまり**未知の `/admin/…` の HTTP ステータスは 200**(SPA)で、404 はクライアントで表す(導出)。
- 同じ SPA 内のリンクは `router-link` / `router.push` を使い、`/admin/` を手で書かない(`base` の一元化)。

### 3.3 本番の配信(A 2.2 を参照)

- `api` が `dist/` を `/admin` に静的配信する。実装は FastAPI の `app.frontend()` を第一候補とする(BAPI-P-2)。JS・CSS など**静的ファイルの欠落は 404**(`index.html` を返さない)、`/api/` と `/healthz` は API が優先(A 2.2)。フォールバックは `Accept: text/html` の GET/HEAD だけ(0004)なので、`fetch` で JSON を取る `/api/...` の誤りが `index.html` で隠れることはない(導出)。
- `/admin`(末尾スラッシュなし)の扱い、`/admin/` 配下の存在しないアセットの 404、`index.html` と `assets/` のキャッシュヘッダー(案: `index.html` は再検証、ハッシュ付きの `assets/` は長期キャッシュ)は**実装時に確認**(BAPI-U-1。FARC-U-6)。
- `web` の死活は静的ファイル(`index.html`)の存在で判定される(B 8.1)。本書はビルド成果物の直下に `index.html` を置くことだけを要求する。
- **`web` のファイルがないとき(B 10.2。ブラウザ側の扱い)**: `index.html` が配信できなければ SPA が起動せず、Admin View は開けない(API だけが動く。画面側から表示できるものはない。運用は `api` の `/healthz`・ログで確認する)。すでに開いているタブでは、D1 に `web` の異常が出る。再配備でハッシュ付きのアセットが入れ替わった後に、開いたままのタブが旧アセットを取りに行って失敗する場合(ルートごとの遅延読み込みを使うときだけ。使うかは F と実測で決める)は、`router.onError` で「画面を再読み込みしてください」とアラートを出す(承認済みの案(ゲート3)。FARC-P-18)。

### 3.4 開発サーバー(FARC-P-19)

- `vite`(既定 5173)を `base: '/admin/'` で起動し、`http://localhost:5173/admin/` を開く。
- `server.proxy` で `/api` を `http://127.0.0.1:8080`(A 8 の `api` のホスト publish)に転送する。ブラウザから見て同一オリジンのままなので、CORS は要らない(FARC-K-4)。転送先は dev 専用の環境変数で上書きできるようにする(名前は実装で決める)。
- 型生成は開発サーバーに依存しない(5.2)。OpenAPI の実行時公開(`LORELEY_API_OPENAPI_ENABLED`)も要らない。

### 3.5 Docker のビルド(FARC-P-20)

A 8 は「ビルドは `apps/api`(Web UI のビルド成果物を含むマルチステージ。ビルドステージの Node の版は E で指定)」とする。本書の要求:

- **Node ビルドステージ**: ベースは Node 24(タグ + ダイジェストで固定。Indexer の Dockerfile と同じ流儀。A 8)。`package.json`・`package-lock.json` を先にコピーして `npm ci`(依存の層をキャッシュ)→ ソースをコピー → `vue-tsc` と `vite build`。成果物 `dist/` を `api` の最終イメージの `LORELEY_API_WEB_DIST_DIR` にコピーする。
- **ビルドステージで型生成はしない**(生成には Python 側の `app.openapi()` が要るため)。生成コードと書き出した OpenAPI JSON はリポジトリに置く(5.2。FARC-P-6)。
- **ビルドコンテキスト**: 既存の compose は `build: ../../apps/<名前>`(コンテキスト=アプリのディレクトリ)で、`apps/api` を文脈にすると `apps/web` が見えない(I-82)。解決策の候補は、コンテキストをリポジトリの `apps` 以上にする、または compose の `additional_contexts`(推測。対応する Compose の版は未確認)で `apps/web` を足すこと。どれにするかは infra の前提作業(HO-37。FARC-U-11)。

---

## 4. アプリ構成

### 4.1 起動の組み立て

`main.ts` は次の順に組み立てる(Pinia はない。FARC-P-17)。

1. Vuetify: `createVuetify`(`theme.defaultTheme: 'light'` と色・variables(DS 3.1)、`defaults`(DS 3.2)、`display.mobileBreakpoint: 'md'`(DS 3.1・7。公式ソースの読解による設定で、実機 4.3.4 で要確認)、アイコン `mdi-svg`)
2. Router(4.3)
3. `VueQueryPlugin`(`QueryClient` の既定値は 5.4)
4. マウント(`#app`)

### 4.2 シェル(DS 5章を参照)

| 要素 | 実装方針 |
| --- | --- |
| 全体 | `VApp` + 左サイドバー(`VNavigationDrawer`。DS 3.2 のとおり静的な `permanent` を付けず `:permanent="mdAndUp"` か既定挙動)+ `VMain`(`RouterView`)。幅 840px 未満だけ `VAppBar` を置く(DS 5.1) |
| ナビ項目 | **`router.getRoutes()` から `meta.nav` を持つ route を抽出**して描く(DS 5.3。route の項目の定義は route `meta` だけ。外部リンクは route でないため下の「外部リンク」の行の定義表)。順は「`navGroups` のグループ順 → `nav.order`」。未定義のグループ ID は開発時に警告して末尾へ |
| 外部リンク | OpenSearch Dashboards は route を持たない外部リンクの項目(admin-view 4.2 の `nav.external` の行)で、定義表(`shell/externalLinks.ts`。F 3.5)に持つ。`SideNav` の外部リンク領域が `GET /meta`(EP-14)の `dashboards_url` を見て、`null`(EP-14 の失敗を含む)なら**領域ごと出さない**(AF-20。B 8.2)。**`featureFlag` の評価はここだけ**(4.5。I-89)。`target="_blank" rel="noopener"` と「(別タブで開く)」(DS 5.1) |
| パンくず | 2 階層以上の画面だけ。`meta.parent` を辿り、親の route に**現在の `params` を引き継いで** URL を作る(S4 の親 S2 に `sourceId` が要る)。末尾は現在のページ(リンクにしない。DS 5.2) |
| スキップリンク・見出し | 先頭に「メインコンテンツへ移動」。ページごとに `h1` を 1 つ(DS 8章) |
| スナックバー | **アプリで 1 つだけ**(`VSnackbar`。同時に 1 つ、新しい通知で置き換える。DS 4.7)。呼び出しは小さな composable(8章) |

### 4.3 route `meta`(FARC-P-18)

DS 5.3 の表をそのまま型にする。型の概形(コードではない):

```text
RouteMeta {
  title:    string | (route) => string      // 動的な見出しは関数(I-83)
  template: 'list' | 'detail' | 'form' | 'dashboard'
  parent?:  route 名
  nav?:     { label, icon(@mdi/js の名前), group(navGroups の ID), order }   // 外部リンクは route でないため含めない(4.2。I-89)
  featureFlag?: string                      // /meta 由来のフラグ名。評価はナビ(SideNav・外部リンク領域)だけ(4.5)
}
```

- route の一覧(`name`・`path`・`title`・`template`・`parent`・`nav`)は **admin-view 4.2 の表をそのまま実装**する(D1 `dashboard`、S1 `sources`、S3 `source-new`、S2 `source-detail`、S4 `source-edit`、J1 `jobs`、J2 `job-detail`、X1 `documents`、O1 `opensearch`、`not-found`)。`/sources/new` を `/sources/:sourceId` より先に定義する。`:sourceId`・`:jobId` は URL エンコードする(`job_id` は `%`・`?`・`#` などを含みうるため。B 2.12。生成 SDK がパスの値をエンコードして送るかは実装時確認。FARC-U-18)。
- **`meta.title`**: 一覧系は文字列。S2・J2(識別子・ジョブ ID)のような**動的な見出しは `route` を受ける関数**にする。DS 5.3 は「文字列」だが admin-view 4.2 が動的な title を要するための拡張(I-83)。`document.title` は「title - Loreley 管理」(DS 5.3)。
- `navGroups` は DS 5.3 の定義表(`overview`・`operate`・`inspect`)を 1 つの配列で持つ。新しいグループが要るときだけ 1 行足す。
- 将来機能(AF-21〜32)は route を足すだけでナビに出る(admin-view 8章)。MVP にダミー項目は置かない。

### 4.4 テンプレート 4 型(DS 6章を参照。FARC-P-32)

`meta.template` で、ページ見出し領域(パンくず・`h1`・説明・主操作 `acts`)と本文の骨格を決める。型ごとの共通部品(テンプレートの Vue 部品の名前・置き場は F)は、次を担う。

| 型 | 使う画面 | テンプレートが担うこと |
| --- | --- | --- |
| `list` | S1・J1・X1・404 | ツールバー(件数・最終更新・更新ボタン)、stale アラートの置き場、表、ページング |
| `detail` | S2・J2 | 見出し+状態タグ、操作(DS 4.13 の出し分け)、カードの並び、見つからない状態 |
| `form` | S3・S4 | DS 6.3・sources 2.7 の最大幅の 1 列、エラー要約、保存・キャンセル |
| `dashboard` | D1・O1 | 見出し右の最終取得日時+更新ボタン、カード・タイルの縦並び |

**状態ブロック(読み込み中・空・エラー・見つからない・stale)は、共通の部品**にする(6.2)。画面側(`features` の composable)が、主たる Query の状態と `describeError`(エラー変換表。6.1)から **`viewState`**(`loading`・`empty`・`error`・`notfound`・`stale`・`ready` と、更新中・更新時刻・診断・再試行の可否)を作り、**テンプレートは `viewState` だけを props で受ける**(テンプレートは Query・API に依存しない。F 3.7。FARC-P-32)。画面は状態の出し分けを自前で書かない。

### 4.5 ガードと遷移後の処理(FARC-P-18)

| 項目 | 内容 |
| --- | --- |
| 認証ガード | **なし**(MVP は認証なし。PD §6.1。BAPI-K-4)。認証が入るときは `beforeEach` に足す(BAPI-U-3) |
| `featureFlag` | **`beforeEach` では評価しない**。`meta.featureFlag`(型は DS 5.3 に合わせて残す)の評価は `SideNav`・外部リンク領域が、`/meta` 由来のフラグ(`queries/meta`)で行い、偽ならナビから外す(4.2)。MVP で `featureFlag` を持つのは route でない外部リンク項目だけで、ルート自体を隠す処理は置かない。DS 5.3 は「ナビとルートを隠す」とするため、差を I-89 に挙げる(ゲート3でユーザー確認済み。2026-11-23) |
| 未保存の離脱確認 | **置かない**(DS 6.3。要件にない) |
| 遷移後 | `afterEach` で `document.title` を更新し、**パス(route の `name` または `params`)が変わったときだけ**フォーカスを `h1`(`tabindex=-1`)に移す(DS 8章)。クエリだけの変化(ページ・タブ・並べ替え)ではフォーカスを動かさない |
| スクロール | `scrollBehavior`: 画面が変わるときは先頭へ。クエリだけの変化では動かさない(X1 のタブ移動は表の上端までだけ戻す。documents 9章) |
| URL の ID・クエリの不正値 | ID の形式は**クライアントで検証しない**(サーバーの 400 `invalid_request`、`/` を含む ID の 404 `not_found` を「見つかりません」と同じに扱う。6.2。B 2.12)。**例外**: `.`・`..` だけの ID は、ブラウザの URL の正規化で別のパスになるため API を呼ばず、「見つかりません」と同じに扱う(F 3.3。FMOD-P-4・FMOD-U-9)。クエリ(`page`・`size`・`sort`・`tab`・`status` など)の不正値は、既定値に正規化して `replace` する(5.6) |

---

## 5. データ取得層

### 5.1 全体の流れ

```text
Admin API(FastAPI サブアプリ。A 5.4)
  └ app.openapi() ─▶ OpenAPI JSON(ファイルに書き出し。サーバー起動不要)
        └ Hey API(openapi-ts) ─▶ 型(DTO・エラー)・SDK 関数・Query 用 xxxOptions
              └ 画面側の composable が「ドメインの key factory」で包む(5.4)
                    └ 画面。失敗は変換表(6章)で表示先を決める
```

### 5.2 型生成(承認済みの案(ゲート2)。FARC-P-1。BAPI-P-10)

- **入力**: Admin API サブアプリの `openapi()` を JSON に書き出したファイル(`LORELEY_API_OPENAPI_ENABLED` に依存しない。A 5.4)。書き出しの Python 側(コマンド・置き場)は D。
- **生成物**: DTO・エラー応答の型、SDK 関数、`@tanstack/vue-query` 用の `xxxOptions` / `xxxMutation`(Hey API の公式プラグイン。0004)。`operationId` は A 5.4 のとおり安定した関数名で、生成される名前がそのまま使われる。エラーの共通スキーマ(A 5.2)は各操作に宣言される。
- **運用**(承認済みの案(ゲート3)。FARC-P-6): 書き出した OpenAPI JSON と生成コードを**リポジトリにコミット**する(Docker の Node ステージが Python に依存しない。差分でレビューできる)。CI は再生成して**差分がないこと**を確認する。生成コードは手で編集せず、lint・format の対象から外す。コミットするかは Hey API 0.x の出力の安定性を見て実装時に確定する(FARC-U-5)。
- **更新手順**: Hey API を上げる、または Admin API の定義が変わったら、再生成 → 差分確認 → 型検査 → テスト。API の変更は、生成型を使うモック(10.2)の `satisfies` で型エラーとして現れる。
- **サブアプリのマウント**: 生成される `paths` が `/sources`(サブアプリ基準)か `/api/admin/v1/sources` かは、サブアプリの `root_path`・`servers` の確認結果(BAPI-U-2。FARC-U-7)で決まる。**クライアントの `baseUrl` を設定する箇所を 1 か所に集約**し、どちらでも変更が 1 か所で済むようにする。

### 5.3 API クライアント(FARC-P-7)

生成された fetch ベースのクライアントに、薄いラッパーを 1 つ置く(置き場は F)。

| 項目 | 方針 |
| --- | --- |
| `baseUrl` | `/api/admin/v1`(BAPI-P-1)。同一オリジンで、認証情報・CORS の設定は不要 |
| エラーの正規化 | 失敗をすべて `ApiError`(下の概形)に変換して送出する。Query・mutation は `ApiError` だけを扱う |
| タイムアウト | クライアント側で `AbortSignal` により切る。**読み取り 45 秒・書き込み 90 秒**(仮値。Admin API 側の OpenSearch 10 秒×最大 3 回、Crawler 応答 60 秒(A 5.6)を、Admin API 自身のエラー応答(503・504)より**先に切らない**ため。実測後に見直す。複数の読み取りを順に行う EP(EP-01・02・10)では Admin API 側の最悪の合計が 45 秒を超えうるため、実測で確認する。FARC-U-16) |
| 再送 | クライアントは**自動再送しない**(Query の再試行だけ。5.4)。書き込みは再送しない(A 5.6・作業プラン P-5) |
| 通知 | クライアントは通知を出さない(通知は画面が決める。6.6) |
| `throwOnError` | 生成クライアントの設定で失敗を例外にし、Query の `error` に載せる。**既定値と Query のエラー処理(stale 表示)の接続は実装時に確認**(FARC-U-4) |

`ApiError` の概形(コードではない):

```text
ApiError =
  | { kind: 'api', status, code, retryable, details?, outcomeUnknown }   // A 5.2 の形で返った
  | { kind: 'network' }                                                    // 接続できない・切断された
  | { kind: 'timeout' }                                                    // クライアント側のタイムアウト
  | { kind: 'invalid_response', status }                                   // JSON でない・形が違う(プロキシの HTML など)
```

`outcomeUnknown` は `details.outcome_unknown`(B 2.3 の `crawler_response_lost`。A 5.2)から作る。`message`(固定の英語文)は画面に出さない(A 5.2)。

### 5.4 TanStack Vue Query の既定値と key(承認済みの案(ゲート3)。FARC-P-8。ライブラリの採用はゲート1で承認済みの案(FARC-P-30))

`QueryClient` の既定(案):

| 項目 | 値 | 理由 |
| --- | --- | --- |
| `retry`(query) | **1 回**。ただし `network` と `retryable=true` の 5xx に限る(`timeout` は 45 秒×2 で長く待たせるため再試行しない)。400・404・409 は再試行しない | DS 10.1・admin-view 7.11 の `retry: 1`。再試行しても変わらないエラーで待たせない |
| `retryDelay` | 1 秒(固定) | 管理画面向けに短く |
| `staleTime` | `0` | **マウント時(画面を開く・戻る)は再取得する**(S2 の「開いたとき再取得」。#33。J1・S1・X1・O1 も同じ)。画面仕様の「手動のみ」は、**定期更新と、フォーカス・再接続による自動再取得をしない**の意で、マウント時の再取得は含まない。戻る操作で古い一覧が最新の状態を隠さないため、マウント時の再取得を止める案(`refetchOnMount: false`)は採らない(案) |
| `refetchOnWindowFocus` / `refetchOnReconnect` | `false` | 「手動更新のみ」の画面で、フォーカス復帰・再接続による予期しない再取得をしない(FARC-P-31)。更新は更新ボタン・マウント時・D1 と J2 のポーリングだけ |
| `gcTime` | 既定(5 分) | 戻る操作で前回の値を使えるように |
| mutation の `retry` | `0` | 書き込みは再送しない(5.3) |
| グローバルの通知 | **置かない**(`QueryCache`・`MutationCache` の `onError` でスナックバーを出さない) | 自動更新の失敗は通知を出さずページ内の警告に留める(DS 4.7)。操作の失敗は各ダイアログが扱う(6.3) |

**key**: 生成された `queryKey` は使わず、**ドメインごとの key factory で上書きする**(`{ ...xxxOptions(...), queryKey: keys.… }`。案)。理由: DS 4.3・admin-view 7.11 の key の書き方(`['sources', …]`)に合わせ、invalidate を prefix で意図どおり指定でき、Hey API 0.x の key の形の変更に引きずられない。

| 領域 | key(`params` は URL から正規化した条件。5.6) | 画面 |
| --- | --- | --- |
| メタ | `['meta']` | シェル、S1〜S4 |
| ダッシュボード | `['dashboard']` | D1 |
| データソース | `['sources','list']`、`['sources','detail',sourceId]`、`['sources','edit',sourceId]` | S1・J1・X1(選択肢)、S2、S4 |
| ジョブ | `['jobs','list',params]`、`['jobs','detail',jobId]` | J1、J2 |
| 文書 | `['documents',sourceId,params]`(`params` に `tab`) | X1 |
| OpenSearch | `['opensearch','cluster']` | O1 |

`['sources','list']` は S1・J1(データソースの選択肢)・X1(選択肢)で**共有**する(EP-01)。

### 5.5 ポーリング・stale・更新(FARC-P-9。更新間隔は FARC-P-31)

| 画面 | 更新 | 実装 |
| --- | --- | --- |
| D1 | 30 秒ごと(承認済み(ゲート C。#26))。一時停止スイッチ。手動の「更新」 | `refetchInterval: 自動更新が入のときだけ 30000`、`refetchIntervalInBackground: false`(タブが見えない間は止める。dashboard 4.1)。スイッチの状態は保存しない(再読み込みで入) |
| J2 | **実行待ち・実行中のときだけ 10 秒ごと**(#8)。終端で停止。取消を要求した後も終端まで続ける | `refetchInterval` を**関数**にし、直近のデータの `status` が `queued`・`running` のときだけ 10000、それ以外は `false` |
| S1・S2・J1・X1・O1 | **手動のみ**(ポーリングなし。フォーカス・再接続でも再取得しない。**マウント時=画面を開く・戻るときは再取得する**。S2 は更新ボタンなし。#33) | 更新ボタンは `refetch()`(再取得中も押せるが二重送信しない。DS 4.5) |

- `stalled`(保存上は `running` でリース切れ)の J2 も `status=running` のためポーリングが続く(導出)。ロック解放後は `failed` になり止まる。
- **最終取得成功日時**は API が持たず、**Query の `dataUpdatedAt` をクライアントが保持**する(AAPI-P-8)。取得失敗が続いても変わらない(dashboard 4.2)。ページの再読み込みで失われる(永続化しない。FARC-P-17)。
- 取得状態の画面への写像(初回・再取得中・空・エラー・stale・見つからない)は 6.2。

### 5.6 サーバー側ページングと `VDataTableServer`(FARC-P-10)

対象は J1(EP-09)・X1(EP-11)。S1(EP-01)・O1(EP-12)は全件を返すため、**クライアント側**(`VDataTable`。ページ・並べ替え・絞り込みは画面)。

**URL ↔ Vuetify ↔ API の対応**(I-85。B 2.1 が E・F に委ねた対応):

| 項目 | URL のクエリ(画面仕様) | Vuetify(`VDataTableServer`) | API(B 2.1) |
| --- | --- | --- | --- |
| ページ | `page`(1 起点。既定は省略) | `page` | `page` |
| 件数 | `size`(25・50・100。既定 25 は省略) | `itemsPerPage` | `items_per_page` |
| 並べ替え | `sort`(**API の値と同じ**。例 `-queued_at`。既定は省略) | `sortBy: [{ key, order }]`(**列の `key` を API の項目名**にする) | `sort`(先頭 `-` で降順。単一項目) |
| データソース | J1・X1 は `source`(識別子) | — | J1 は `source_id`(クエリ)、X1 は**パスの** `{source_id}` |
| 状態(J1) | `status` | — | `status`(`queued`・`running`・…・複合 `active`) |
| タブ(X1) | `tab`(`skipped`・`extract-failed`・`oversize`・`summary-pending`) | — | `tab`(`skipped`・`extract_failed`・`oversize`・`summary_pending`) |

- **URL が唯一の正**(8章): route の `query` から正規化した `params`(型付き)を作り、key・API 呼び出し・`VDataTableServer` の `page`/`itemsPerPage`/`sortBy` はすべて `params` から導く。ローカルに複製しない。
- **正規化**: 不正値(範囲外の `page`、未知の `sort`・`tab`・`size`)は既定値にして `router.replace`。`sort` は単一項目だけ(複数ソートを無効にする。実装時確認。FARC-U-2)。並べ替えが「なし」になったときは `sort` を省略し、既定の並び(B 2.1)に戻す。
- **履歴**: 条件の変更(ページ・件数・並べ替え・絞り込み・タブ)は `router.push`(戻る・再読み込み・共有で再現。画面仕様)。O1 の `q`・`state` は `router.replace`(opensearch 3.5)。
- **条件を変えたら 1 ページ目に戻る**(絞り込み・件数・タブ・データソース。画面仕様)。ページと並べ替えだけの変更では戻らない。
- **取得中の前回データ**: `placeholderData: keepPreviousData`(TanStack Query v5。DS 4.3)を、**同じスコープ(同じ絞り込み・同じデータソース・同じタブ)のページ・並べ替えの変更**に限って使う(案)。絞り込み・タブ・データソースが変わったときは前回の行を見せず、スケルトンにする(別の条件の行を「古いデータ」として見せない。X1 の `tab_counts` も、データソースが同じ間だけ前回の値を残す)。
- **深いページ**: `page × items_per_page ≤ 10,000`(B 2.1)。画面は上限を超えるページへの移動を出さず、`total` が上限を超えるときは `window_limit` を使って「表示できるのは先頭 N 件までです」と案内する(documents 8章)。
- `VDataTableServer` の `@update:options` が初期表示で発火して**二重に取得しない**こと、`hover` の有無、`aria-sort` は実装時に確認する(DS 4.3・DS 3.2。FARC-U-2)。

### 5.7 画面別のデータ取得・エラー表示の方針(FARC-P-11)

F はこの表を「画面 → route → ページ → composable → EP」に展開する(F 4章)。エラーの表示は 6章。`—` は該当なし。

| 画面 | 読み取り(EP。key) | 更新 | 初回の失敗 | 更新の失敗(前回データあり) | 部分失敗・補足 |
| --- | --- | --- | --- | --- | --- |
| D1 | EP-13(`['dashboard']`)だけ(EP-14 はシェルが取得する。dashboard 画面仕様に cron のタイムゾーン・Dashboards の URL を使う項目はない) | 30 秒+手動(5.5) | エラーブロック(`d1-state-error`)。通知なし | 警告アラート+**前回「正常」「異常」だったタイルを判定不能に降格**し「前回の状態」を添える。「未設定」は維持(dashboard 4.3。#25)。`dataUpdatedAt` を最終取得成功日時に | 下の「D1 の補足」 |
| S1 | EP-01(`['sources','list']`)、EP-14 | 手動のみ | エラーブロック(`s1-state-error`) | stale アラート(`s1-state-stale`)。操作は無効にしない | 取得失敗は**各行の `items[i].unavailable`**(常に存在。キーは行内の相対パス `last_crawl`・`last_completed_at`・`delete_job`・`last_crawl.stalled`・`delete_job.stalled`・`document_count`。最上位 `unavailable` は常に `{}`。B 2.2・3.1。AAPI-P-42)で判定する。行の値が `null` で**その行の** `unavailable` にキーがあれば「取得できません」、キーがなければ値がない(`last_crawl=null` は「未実行」。source-a が未実行、source-b が読み取り失敗でも区別できる)。主たる読み取りや検索インデックスの全体の失敗は全行に同じキーが付く。`document_count` は「—」+「取得できません」。`last_crawl.stalled` は DS 4.1 のタグ(リース切れ) |
| S2 | EP-02(`['sources','detail',id]`)、EP-14 | 画面を開いたとき・操作の後 | 404 `source_config_not_found` → 「見つかりません」(`s2-state-notfound`)。その他は取得できません(`s2-state-error`) | stale アラート(`s2-state-stale`)。404 になったら stale にせず「見つかりません」に切り替える | `unavailable` のキー `lock`・`last_crawl`・`last_completed_at`・`delete_job`・`last_crawl.stalled`・`delete_job.stalled`・`index.document_count` は各カードで「取得できません」(ロック状態カードの写像は 5.10)。設定の項目が読めない(`unavailable.<項目名>=malformed`)ときの表示は I-87。`lock.job.lease_expires_at` は読めなければ `null`(番兵は出ない。期限切れかどうかは `lock.state`(`lease_expired` など)で表す。B 3.2)。`status=deleting` は操作を出し分ける(DS 4.13。sources 1.8) |
| S3 | —(EP-14 のみ) | — | EP-14 の失敗はタイムゾーン警告(sources 2.4。`cron_timezone=null` と同じ扱い) | — | — |
| S4 | EP-02(編集用 `['sources','edit',id]`)、EP-14 | 開くたびに取得 | **フォームを出さず**エラーブロック(`s4-…`。現在値がないまま全置換しない。B 3.2、sources 2.6) | — (編集中は再取得しない。5.8) | 404 → 見つかりません。`status=deleting` → 編集不可(sources 2.6)。**`unavailable` に設定の項目があるとき**(`malformed`)は 7.6 |
| J1 | EP-09(`['jobs','list',params]`)、EP-01(選択肢) | 手動のみ | エラーブロック(`j1-state-error`) | stale アラート(`j1-state-stale`。「実行中のジョブの状態が実際と異なる可能性」) | ジョブ記録の値が読めず `status=null` の行は、状態列を「—」にし、ステータスタグも取消も出さない(5.9)。`status` の絞り込みは保存上の状態で、画面の「実行待ち・実行中」は複合値 `active`。未登録の `source_id` は 404 にならず空の結果(B 5.1)。その行の `unavailable` に `stalled` があるとき、その行の `stalled` は `null`・`cancellable=false`(取消を出さない。他の行には影響しない。最上位 `unavailable` は常に `{}`。AAPI-P-42)。EP-01 が失敗しても一覧は出し、選択肢は「すべて」と URL の指定値だけにする(案) |
| J2 | EP-10(`['jobs','detail',jobId]`) | 実行待ち・実行中は 10 秒(5.5) | 404 `job_not_found` → 見つかりません。その他は取得できません(`j2-state-error`) | stale アラート(`j2-state-stale`)。404 は「見つかりません」に切り替え | `unavailable` のキー: `stalled`・`lease_expires_at`・`latest_for_source`・`rerunnable`・`deletion.current`。**`stalled`・`rerunnable`・`latest_for_source` が `null` のときは再実行・取消の操作を出さない**(1.2)。`status=null` ならタグ・操作とも出さず、`registration` の件数・`partial`・`phase` の `null` は「—」(5.9)。`rerun_blocked_reason=source_missing`(データソースの設定がない)は出さない(6.7)。`deletion.current_state=unavailable`・`not_found` は「結果不明」の説明(jobs 2.9)で、`deletion.fetched_at` を現在値の「取得時刻」に出す。`registration.phase` で途中/確定を示す。未知の `failure_reason`・警告コードは一般的な文言(B 5.2。jobs 2.5・2.7) |
| X1 | EP-11(`['documents',sourceId,params]`)、EP-01(選択肢) | 手動のみ | **パネルだけ**エラーブロック(`x1-state-error`)。タブ名の件数は「—」。データソース未選択は `enabled: false` | パネル上部の stale アラート(`x1-state-stale`) | 最上位 `unavailable` は行に属さない `tab_counts.<タブ>`・`document_count` だけ。各行の `unavailable` のキーは `existence`(B 2.2・6.1。AAPI-P-30・42)。`tab_counts.<タブ>`・`document_count` の `null` は「—」。`existence` が `unknown`(その行の `unavailable` に `existence`。一括検索の全体の失敗は全行、文書単位の失敗はその行だけ)は「確認できません」。`tab` は必須(画面は常に送る)。404 `source_config_not_found` は I-87 |
| O1 | EP-12(`['opensearch','cluster']`) | 手動のみ | カード内のエラーブロック(`o1-state-error`)。**1 取得=カード全体**(どれかの読み取りが失敗したら全体が 503。B 7.1) | ページ上部の stale アラート+カード全体を前回の値で(`o1-state-stale`) | 絞り込み(`q`・`state`)は画面側。`indices[].status`・`document_count` の `null` は「—」。`truncated=true` は I-87 |
| シェル | EP-14(`['meta']`。`staleTime: Infinity`。FARC-P-25) | 再読み込みまで | 失敗してもシェルを止めない。Dashboards リンクは出さず、タイムゾーンは「取得できません」の警告(sources 2.4) | — | — |

**D1 の補足**:

- `components[]` は常に 8 件(固定の順)。`state`(`normal`・`abnormal`・`undetermined`・`not_configured`)は DS 4.1 の 正常・異常・判定不能・未設定に 1 対 1。
- `reason`(`connection_refused`・`name_not_resolved`・`unexpected_status`・`missing`・`timeout`・`connection_error`)は診断用の補足で、未知の値は一般的な文言(B 8.1)。
- `id` は画面の表示名と同じで、`web` は compose のサービスではなく `api` が配信する Web UI(B 8.1)。
- トップの `checked_at` は全確認が終わった時刻で、**最終取得成功日時(クライアントの `dataUpdatedAt`)とは別**。タイルの「確認 hh:mm:ss」は `components[].checked_at`。
- Admin API に届く限り EP-13 は 200 で、コンポーネントの失敗は `state` に載る。

- **EP-14 `/meta` の失敗**は、`dashboards_url=null`・`cron_timezone=null` と同じに扱う(導出。「取得できないとき」の画面の挙動が画面仕様にある)。
- X1 の `enabled: false` のとき、`isPending` は true のままで取得は走らない。スケルトンは `isPending` ではなく**取得中を表す状態**(v5 の `isLoading`。推測。実装時確認)で出す。

### 5.8 操作(mutation)と invalidate(FARC-P-11)

| 操作(ダイアログ) | EP | 成功の扱い | invalidate(prefix) |
| --- | --- | --- | --- |
| DLG-1 クロール起動(S1・S2) | EP-06 | 202 → スナックバー「…を受け付けました(ジョブ ID: …)」+「ジョブを表示」 | `['sources']`、`['jobs']` |
| DLG-4 再実行(J2) | EP-06(J2 の `source_id`・`force_delete`・`rewrite_mode` を渡す。B 4.1) | 新しいジョブの J2 へ移動+スナックバー(#32) | 同上 |
| DLG-2 削除・削除の再実行(S1・S2・J2) | EP-05 | 202 → スナックバー+行が「削除中」 | `['sources']`、`['jobs']` |
| DLG-3 取消(J1・J2) | EP-07 | 200・202 → スナックバー(文言は `status` で分岐。jobs 2.10)。**409 `job_already_finished` も成功扱い**(6.3) | `['jobs']`、`['sources']` |
| DLG-5 ロック解放(J2・S2) | EP-08 | 200 → スナックバー | `['sources']`、`['jobs']` |
| S3 登録 | EP-03 | 201 または 200(冪等)→ S2 へ移動+スナックバー | `['sources']` |
| S4 保存 | EP-04 | 200 → S2 へ移動+スナックバー | `['sources']`(編集用の key は `gcTime: 0` で残らない) |

- 実行中は実行ボタンを無効にし(mutation の `isPending`)二重送信を防ぐ。ダイアログは**失敗時に開いたまま**(6.3)、成功時だけ閉じてスナックバーを出す(DS 4.8)。
- **S4 の取得(FARC-P-12)**: S4 は S2 と**別の key**(`['sources','edit',id]`)で、`gcTime: 0`・`staleTime: Infinity`・ウィンドウフォーカスなどによる再取得なしにする。画面を開くたびに必ず取得し、**取得結果でフォームを 1 度だけ初期化**する(キャッシュ済みの古い値で全置換しない。編集中にバックグラウンドで値が差し替わらない)。

### 5.9 Vue で使うときの注意

- Hey API の `xxxOptions({ query, path })` は、Vue では**リアクティブな値を直接受けない**。`useQuery(computed(() => xxxOptions({ … })))` のように `computed` で包み、URL から導いた `params`・`enabled` を中に入れる(0004)。
- 日時は `Intl.DateTimeFormat`(ブラウザのローカル時刻。`YYYY-MM-DD HH:mm`。DS 4.9。FARC-P-33)で整形し、日時ライブラリを足さない(承認済みの案(ゲート3)。FARC-P-24)。
- 時刻の比較・並べ替えは API の ISO 8601 文字列(UTC・ミリ秒精度。A 5.1)を `Date` に変換してから行う。
- **番兵の日時**: 409 の `details.existing_job.lease_expires_at`(`lock_held`・`lock_in_use`)は、Crawler が値を日時として読めないときだけ `0001-01-01T00:00:00.000Z` を返す(B 2.11・I-73)。**日時として整形せず「期限切れ」として扱う**(「0001-01-01 …」を表示しない)。`null` は「期限なし(実行待ち)」で、番兵とは別。S2 の `lock.job.lease_expires_at` は Admin API が読むため、読めなければ `null` で番兵は出ない(期限切れは `lock.state` で分かる。B 3.2)。整形関数は番兵を判定する 1 か所に置く(案)。
- **`null` の 2 種類(FARC-P-36。B 2.2・2.11)**: (a) **取得失敗**=`unavailable` にキーがある `null` → 「—」+「取得できません」。**表示は画面仕様に従う**(表のセル(S1 の登録文書数・X1 の件数など)は視覚的に隠した「取得できません」、S2 のカードは見える文言)。(b) **値が読めない**=ジョブ記録・削除記録・ロック文書など Crawler・Indexer が書いた値が欠落・型違いで `null`(`unavailable` には載らない。`malformed` は EP-02 の設定項目だけ)→ 「—」+視覚的に隠した「読み取れません」(見える文言は足さない)。表のセルでは、いずれも見た目は「—」で、読み上げ(視覚的に隠した文言)と診断で区別する。`JobBrief` の `status`・`job_type`・`trigger`・`queued_at`、`registration` の件数・`partial`・`phase` は、**値があるはずの項目**で、`null` は (b) として扱う(`started_at`・`finished_at` などの `null` は「値がない」で「—」+「なし」)。`status=null` のジョブには**ステータスタグ・操作を出さない**。画面仕様に定義がないため案(I-120)。
- **`unavailable` の位置とキー(B 2.2。AAPI-P-42。FARC-P-39)**: 単一の応答(EP-02・10・12・13・14)は**最上位の `unavailable`**で、キーは応答の項目の正式なパス(`deletion.current`・`index.document_count`・`last_crawl.stalled` など)。**一覧の EP(EP-01・09・11)は各行 `items[i].unavailable`(常に存在)**で、キーはその行の中の相対パス(`last_crawl`・`last_crawl.stalled`・`document_count`・`stalled`・`existence` など)。一覧の最上位 `unavailable` は、行に属さない項目(EP-11 の `tab_counts.<タブ>`・`document_count`)だけで、EP-01・09 では常に `{}`。**判定は「その行(または最上位)の `unavailable` のキー」で行う**: 値が `null` でキーがあれば取得失敗、`null` でキーがなければ値がない(読めない値は (b))。旧規則の「一覧でキーがあり行が `null` なら取得できません(安全側)」は廃止した(行ごとに失敗が区別できるため)。画面は行の `unavailable` を引く関数と、最上位を引く関数の 2 つを通す(F 3.5。FMOD-P-14・FMOD-P-33)。

### 5.10 ロック状態の写像(S2 のロック状態カード。FARC-P-34)

S2 の `lock.state`(B 2.9。7 値)を、画面仕様の 6 種+取得失敗(sources 1.5)に対応づける。写像は 1 つの表(関数。F 3.5 の `lockStateView`)に持ち、S2・J2・DLG が共通に使う。

| `lock.state` | ロック状態カード(sources 1.5) | 操作 |
| --- | --- | --- |
| `none` | ロックなし | なし |
| `held_crawl`(`lock.job.status=running`) | 実行中のジョブが保持(リース期限内)。解放できない旨と取消の案内 | 「ジョブを表示」(J2) |
| `held_crawl`(`queued`) | 上と同じ構成で、タグは「実行待ち」(画面仕様は実行中だけを書く。`held_*` は実行待ちを含む B 2.9 への対応。案) | 「ジョブを表示」(J2) |
| `held_delete`(`queued`・`running`) | 削除ジョブが保持(リース期限内)。タグ「削除中」。完了を待つ案内 | なし |
| `lease_expired` | リース切れのジョブが保持(warning)。ジョブ ID・リース期限(`formatLeaseExpiry`。5.9) | 「ロックを解放…」(DLG-5)・「ジョブを表示」 |
| `orphan` | 孤児ロック(warning)。ジョブ記録がない、またはジョブが終了済み | 「ロックを解放…」(DLG-5 孤児版) |
| `just_acquired` | ロック取得の直後(受付の途中の可能性)。解放できない旨 | 「再読み込み」(`refetch`) |
| `unknown` | 「ロック状態を確認できません」(理由を断定しない。解放は出さない。画面仕様にない。I-87) | 「再読み込み」 |
| (`lock=null`・`unavailable` に `lock`) | 取得失敗(「取得できません」。画面仕様の部分失敗) | 「再読み込み」 |

- `lock.job` の `job_type`・`status` が `null`(ジョブ記録がない・読めない)のときは、「ジョブを表示」を出さない(6.3。FARC-P-35)。
- J2 のロックカードは、`stalled=true`(リース切れ)のときだけ出し、上の `lease_expired` の行と同じ内容(J2 の応答の `lease_expires_at`)。

---

## 6. エラー処理

### 6.1 方針(FARC-P-13)

- 失敗は 5.3 の `ApiError` に正規化し、**1 つの変換表(データ)**で `code` → 表示先・variant・再試行の可否に写す。画面は変換結果を表示するだけ(DS 4.1 と同じ「対応を 1 か所に」)。文言は画面仕様が正で、`message` は使わない(A 5.2)。
- 表示先は 4 つ: (1) **項目別**(フォームの入力欄の下+エラー要約。DS 4.6)、(2) **ダイアログ内アラート**(操作の失敗・拒否。閉じるまで残る。`role="alert"`。DS 4.7)、(3) **状態ブロック**(読み取りの失敗。6.2)、(4) **スナックバー**(受付・保存の**成功**だけ。失敗には使わない。DS 4.7)。
- 想定外のエラー(`crawler_error`・`internal_error`・`http_error`・`not_found`・`method_not_allowed`・`invalid_response`)は、一般的な文言と、診断用に補助文字で **`code` と HTTP ステータス**(`message` は出さない)を出す(案)。入力値・パスは出さない(A 2.3・5.2)。

### 6.2 読み取りの失敗(Query の状態 → 画面の状態。DS 4.5)

`features` の composable が、主たる Query の状態と `describeError`(6.1)の結果から **`viewState`** を作る(F 3.7 の `useViewState`)。テンプレートは `viewState` だけを props で受け、`error.code` を判定しない(層の依存。F 6章 R7)。下の表は、その写像の定義。

| 画面の状態 | Query の条件 | 表示 |
| --- | --- | --- |
| 初回の読み込み中 | データなしで取得中 | スケルトン+`aria-busy`+視覚的に隠した「読み込み中」 |
| 再取得中 | データあり・取得中 | データは消さず、カード上端の進行バー |
| 空 | 成功・0 件 | 空ブロック(画面ごとの文言) |
| エラー(データなし) | `isLoadingError` | エラーブロック(`role="alert"`)+「再試行」(`refetch`)+試行時刻 |
| 古いデータ(stale) | `isRefetchError`(404 を除く) | warning アラート(`role="alert"`)+前回のデータ+「再読み込み」+`dataUpdatedAt`(最終更新(成功)時刻)。操作は無効にしない |
| 見つかりません | `error.code` が `source_config_not_found`・`job_not_found`(EP-07 の取消でも、`job_id` 起因の Crawler の 400・404 `not_found` がこの code に写る。6.3)、400 `invalid_request`(パスの ID の形式違反)、404 `not_found`(`/` を含む ID は Admin API のルーティングで 404。B 2.12)。**データの有無を問わない** | 「見つかりません」ブロック(S2・S4・J2・X1)。前回データがあっても stale にせず切り替える(消えたリソースを「最新ではない」と読ませない) |

- 503 `unavailable`(A 5.2。OpenSearch の読み取りの失敗)と、`network`・`timeout`・`invalid_response` は、エラーブロックまたは stale になる。文言は画面仕様(例: `s2-error` の「データソースの詳細を取得できません」)。
- **部分失敗**(B 2.2。FARC-P-27): 200 の本体(一覧は各行・単一の応答は最上位)の `unavailable` にキーがあるときは、その項目だけ「—」+視覚的に隠した「取得できません」にする(画面仕様どおり)。理由コード(`store_unavailable`・`search_index_unavailable`・`timeout`・`malformed`)は画面では**区別せず**同じ表示にする(案。`malformed` だけ S4 で扱いが違う。7.6)。主たる読み取りの失敗は 503 `unavailable` で、部分失敗ではなく上の「エラー」の表示になる(B 2.2)。
- 自動更新(D1・J2)の失敗は通知を出さず、ページ内の stale に留める(DS 4.7)。

### 6.3 書き込みの失敗(`code` → 表示。承認済みの案(ゲート2)の code 名は B 2.3。A 5.2)

| `code`(HTTP) | EP | 表示先・扱い |
| --- | --- | --- |
| `invalid_request`(400) | 全般 | **S3・S4**: `details.errors[].field` から入力欄を決め、`reason` を DS 4.6 の文言に対応づけて項目の下に出す(6.4)。ダイアログ系・パス ID の違反: 画面が送らない値のため想定外(上の「見つかりません」の扱いは読み取りのみ) |
| `config_invalid`(400) | EP-03・04 | S3・S4: `details.errors[]` の `connector_config.…`(`include_patterns[2]` など)を該当の行・項目の下に(`detail` の固定文を画面の文言に対応づける)。**`errors` が空、`field` が `connector_config`(プレフィックスなし。「オブジェクトでない」「未知の項目がある」の違反。特定の入力欄に結びつかない。B 2.5)、または `detail` が完全一致の対応表にないとき**は、フォーム上部のアラートに **`details.crawler_message`(Crawler の固定文。入力値・パスを含まない)をそのまま出す**(sources 2.4)。入力内容は残す |
| `source_config_not_found`(404) | EP-02・04・05・06・11 | 読み取りは 6.2。**DLG-1・DLG-4**: ダイアログ内 error「データソースが見つかりません」+「一覧を更新」(admin-view 7.7)。DLG-2: 同様。S4 の保存: フォーム上部アラート |
| `job_not_found`(404) | EP-07・10 | J2 は 6.2。DLG-3: ダイアログ内 error+「ジョブ一覧を更新」。EP-07 では、`job_id` に `%`・`?` などを含み Crawler が 400 `invalid_request`・404 `not_found` を返した場合も、この 404 に写る(B 4.2・2.6。AAPI-P-39。案。表示は上と同じ) |
| `lock_held`(409) | EP-05・06 | **ダイアログ内アラート**(DLG-1・DLG-4・DLG-2・削除の再実行)。実行ボタンは「閉じる」に置き換える(admin-view 7.7)。`options_applied=false` のとき、`requested` の指定が**反映されていない**ことを太字で出す(EP-05 には `requested` がない)。**`details.lock_state` 別の variant と次の行動(FARC-P-35)**: `lease_expired`(ジョブ記録があり、リース切れ)→ warning+「ジョブ詳細でロックを解放」(J2。DLG-5)。`orphan`(ジョブ記録がない、または終端。取得から 60 秒超)→ warning+「ロック状態を確認」(**S2 のロック状態カード**)。`just_acquired`(ジョブ記録がなく取得から 60 秒以内。`orphan` と排他。受付の途中の可能性)→ 「ジョブを表示」を出さず、しばらく待ってから確認するよう案内(S2 へのリンク)。`held_crawl`・`held_delete`(ジョブ記録あり)→ error+「ジョブを表示」(`existing_job`)。`unknown`(ジョブの `status`・`job_type` が読めない場合を含む)→ error。理由を断定せず S2 を案内。**`existing_job.status`(または `job_type`)が `null` のとき(ジョブ記録がない・読めない)は、`existing_job.job_id` があっても「ジョブを表示」(J2)を出さない**(EP-10 が 404 になりうる。孤児ロックの解放の入口は S2 だけ。sources 1.5)。admin-view 7.7 の「失効したロック → J2 → DLG-5」との差は I-88(ゲート3でユーザー確認済み。2026-11-23) |
| `lock_in_use`(409) | EP-08 | DLG-5 内のアラート(解放できない理由。sources 1.5 の案内。`existing_job`・`lock_state`)。`lock_state` が `unknown` のこともある(ロック文書・ジョブ記録を読めなかった、またはジョブの `status` が読めない。B 2.9・4.3)。その場合は理由を断定せず「状態を確認できないため解放しませんでした」の旨 |
| `source_deleting`(409) | EP-04・06 | DLG-1・DLG-4: ダイアログ内 error「データソースは削除中」。**S4 の保存**: S4 を「削除中」状態(編集不可。sources 2.6)に切り替え、入力は残す |
| `maintenance_enabled`(409) | EP-05・06 | ダイアログ内 error。次の行動なし(閉じる)。フラグの操作は画面にない(AF-19) |
| `source_already_exists`(409) | EP-03 | S3: 識別子の項目の下。`details.status=deleting` のときは補足(sources 2.4) |
| `job_not_cancellable`(409) | EP-07 | ダイアログ内 error。画面は `cancellable=false` の行に操作を出さないため通常は出ない(想定外の扱い) |
| `job_already_finished`(409) | EP-07 | **成功扱い**(承認済みの案(ゲート2)。AAPI-P-21。FARC-P-14): ダイアログを閉じ、スナックバー「ジョブはすでに終了しています(状態: …)」(`details.status`。jobs 2.10)。invalidate は 5.8 |
| `crawler_error`(502) | EP-03〜08 | 想定外(6.1)。再試行は出さない |
| `crawler_unavailable`(503・`retryable`) | EP-03〜08 | 「Store 層の一時的な障害」の旨+**再試行**(実行ボタンを再試行として残す。admin-view 7.7) |
| `crawler_unreachable`(503・`retryable`) | EP-03〜08 | 「Crawler に接続できません」(起動時の回復中を含む)+**再試行**。S3・S4 は入力内容を残し、フォーム上部の消えないアラート(sources 2.4) |
| `crawler_response_lost`(504・`outcome_unknown`) | EP-03〜08 | **結果不明**(6.5) |
| `unavailable`(503) | EP-01・02・09〜12 | 読み取り(6.2) |
| `not_found`・`method_not_allowed`・`http_error`・`internal_error` | 全般 | 想定外(6.1) |

- `retryable=true` のときだけ「再試行」を出す(`retryable` を再試行の可否の正とする。A 5.2)。起動系の再試行は、状況が変わっていないことの確認を促す文言を画面仕様に従って添える。**例外**: 保存系(EP-03・04)の `crawler_response_lost`(`retryable=false`)は、再送が安全なため「もう一度保存」を出してよい(6.5。B 9.2.4・9.2.5)。
- EP-04 の `config_invalid` は 404・409 より先に返りうる(B 3.4)。画面は返ってきた `code` に従い、順序に依存しない。

### 6.4 項目別エラー(`details.errors[]`)の写像(FARC-P-13)

- `field` は **Admin API のリクエストの項目名**(`ttl_days`・`ttl_seconds`・`ratio_threshold_percent`・`min_delete_count`・`schedule_cron`・`source_id`・`connector_config.root`・`connector_config.include_patterns[2]` など。B 2.4)。画面は項目名 → 入力欄の対応表(1 つの表)で入力欄・行を決める。**表にない `field`、または対応できない `reason`**(`invalid_request` など)は、フォーム上部のアラートに「想定外の応答です」+診断用の項目名(値は出さない。A 5.2)。`config_invalid` の `errors` が空・`field=connector_config`・照合不能の `detail` は「想定外」ではなく、`crawler_message` をそのまま出す(6.3)。
- Admin API が本文の項目エラーで返す `reason` は `required`・`type`・`format`・`range`・`exclusive`・`unknown_field`・`unsupported`・`config_invalid`(B 2.4・2.12。Crawler の `read_only` は 502 `crawler_error` になり、画面には届かない。B 2.6)。`reason` → 文言は sources 2.4 の表(`required`・`format`・`type`・`unsupported`・`unknown_field`・409)に従う。同表にない B の値の扱い(I-84): `range` はクライアント検証と**同じ範囲の文言**、`exclusive` は想定外(画面は `ttl_days` と `ttl_seconds` の一方だけを送るため通常は出ない)、`config_invalid` は `detail`(固定文)を画面の文言に対応づける(sources 2.3.2)。
- S4 の `ttl_seconds` の入力は、日で割り切れない既存値を秒で編集するモードのときだけ(7.3)。

### 6.5 接続エラー・タイムアウト・結果不明(FARC-P-15)

- **読み取り**: `network`・`timeout` は 6.2(エラーブロックまたは stale)。
- **書き込み**: `crawler_response_lost`(504)は「**操作が実行されたか確認できません**」とする。**起動系(EP-05・06)**は、再試行を出さず、状態を確認する導線を出す(J1 または S2。再送すると、受付済みなら 409 `lock_held` で既存ジョブが分かる。B 2.3)。**保存系(EP-03・04)**は、再送しても同じ内容なら安全(200 の冪等応答か 409。B 9.2.4・9.2.5)なので、「S2 で確認する」と「もう一度保存」の両方を出してよい(案)。**取消・解放(EP-07・08)**は、J2・S2 を再取得して確認する導線を出す(解放は再送で `released=false` になりうる。B 9.2.3)。
- **クライアント側の `timeout`、および書き込みの `network`(送信後の切断かどうかをクライアントは区別できない)**も、同じく結果不明として扱う(案)。Admin API の 504 を待たずに切れないよう、タイムアウトの仮値を置いた(5.3)。
- 書き込みの `network` が確実に「送信前の失敗」(接続拒否)と分かる場合の扱いは区別しない(安全側。導出)。

### 6.6 通知のルール

- スナックバー=操作の**受付・保存の成功だけ**。失敗・拒否はダイアログ内またはフォーム上部のアラート(DS 4.7)。
- 取得失敗は `role="alert"`、読み込み後の情報(警告・O1 の red のアラート(opensearch 4章)など)は `role="status"`(画面仕様)。自動更新の結果は読み上げない(DS 8章)。

### 6.7 画面仕様にない状態(I-87)

B の応答から必要になるが、画面仕様に状態の記述がないもの。暫定の扱い(案)を置き、画面仕様の追記は A 9章(HO-29・HO-30)に委ねる。

- O1 の `truncated=true`(B 7.1。「画面は警告を出す」): カード上部に warning の注記(「インデックスが多いため先頭 1,000 件だけを表示しています(全 N 件)」)。
- X1 の `source` が指すデータソースが存在しない(404 `source_config_not_found`): 「データソースが見つかりません」ブロック+データソースの選択へ(documents 8章の「データソース未選択」と同じ置き場)。
- S2 の `SourceSettings` の項目が読めない(`unavailable.<項目名>=malformed`。B 3.2・AAPI-P-34): 該当の項目を「—」+「保存されている値を読めません」とする。S4 は 7.6。
- S2 のロック状態カードで `lock.state=unknown`(B 2.9)のとき: 理由を断定しない表示(5.10)。
- J2 で `stalled`・`rerunnable` が `null` のとき: 取消・再実行の操作を出さず、「リース切れかどうかを確認できません」の旨を補足に出す(案。操作は出さないが、理由は画面に示す)。`rerunnable=null` には、データソースの設定の読み取り失敗も含まれる(B 2.9。AAPI-P-41)。
- J2 で `rerun_blocked_reason=source_missing`(データソースの設定がない=削除済み。B 2.9。AAPI-P-41。案)のとき: **「再実行」を出さない**(削除済みのソースは再実行しない。`source_deleting` と同じ扱いで、「削除中」とは表示しない)。専用の文言は画面仕様 jobs 2.3 に定義がなく、足すかは画面仕様側の追記(HO-30)で、それまでは補足なし、または一般的な文言(未知の値は一般文言。I-121)。
- 値が読めない `null`(`status=null` のジョブ、`registration` の件数など): 5.9 の (b)。画面仕様にない(I-120)。

---

## 7. フォームと検証

### 7.1 検証の層(FARC-P-16)

| 層 | 担当 | 内容 |
| --- | --- | --- |
| 画面(クライアント) | 画面仕様の検証規則(sources 2.3・2.4)。**フォーカスが外れたとき**と**送信時**に検証 | 必須・形式・範囲・パターンの件数とバイト数など。画面は送信前にエラー要約を出し、送信しない |
| Admin API | B 2.4 | `ttl`・`min_delete_count`・`ratio_threshold_percent`・ID の形式・ページングなど、Admin API 自身の責務の範囲だけ。`connector_config`・`schedule_cron`・`connector_type` は**検証しない**(複製しない。AAPI-K-5) |
| Crawler(Connector) | `config_invalid`・`schedule_cron` の `format` | 最終の判定。画面側の検証規則は Connector の規則の**複製**で、ずれたときの安全網がサーバーの `config_invalid`(6.3・6.4) |

- 検証ライブラリは足さない(案)。検証規則は**項目 → 規則の表と純関数**にし、Vitest で単体テストする(10.1)。エラーの表示(要約・`aria-invalid`・`aria-describedby`)は DS 4.6 に従い、Vuetify の `VForm` の `rules` だけでは足りない点(要約・サーバーエラーの合流)は自前で組む。
- サーバー(`details.errors`)の項目別エラーは、**その項目が編集されたら消す**(案)。クライアント検証と同じ形(同じ入力欄の下)で出す(DS 4.6)。
- 画面の定数(パターンの最大 100 件・1,024 バイト。**仮値**)は 1 か所に定義する。API は上限値を返さず(AAPI-P-20)、最終の判定はサーバー。

### 7.2 値の扱い

- 数値(`ttl_days`・`ratio_threshold_percent`・`min_delete_count`)は、**文字列のまま形式を検証してから**数値にする(例: しきい値は `^\d{1,3}(\.\d{1,2})?$`。小数第 2 位まで。浮動小数の誤差を持ち込まない)。`ttl`(日・秒とも)は **1 以上**、最小件数は 0 以上で、いずれも**9 桁まで**(承認済み(ゲート C。#3))、JavaScript の安全整数に収まる。`ttl` の下限 1 は、B がゲート1の「非負」から画面仕様に合わせて変えたもの(承認済みの案(ゲート3)。AAPI-P-37。画面仕様と一致するため画面の挙動は変わらない)。9 桁を超える既存値(Crawler API を直接使った登録)の編集時の扱いは未決(FARC-U-13)。
- 空文字・前後の空白: パターンは前後の空白を注意(エラーにしない。DS 4.18)。識別子の入力確認は前後の空白を無視して完全一致(DS 4.8)。
- `schedule_cron`: 画面は書式を検証せず(Crawler に任せる。AAPI-K-5)、空は `null`(手動のみ)として送る。S4 は全置換のため省略すると `null` になる(B 3.4)。

### 7.3 単位変換(B 2.8。承認済みの案(ゲート2)。AAPI-P-14)

**変換は Admin API が行う**。画面は入力単位のまま送る。

| 項目 | 画面の入力 | リクエスト | 応答 |
| --- | --- | --- | --- |
| TTL | 日(整数) | `ttl_days` | `ttl_seconds`、`ttl_days`(日で割り切れるときだけ整数。それ以外 `null`) |
| TTL(秒モード) | 「N 秒」(S4 で `ttl_days=null` のとき画面が切り替える) | `ttl_seconds` | 同上 |
| しきい値 | %(小数第 2 位まで。0 以上 100 未満) | `ratio_threshold_percent` | `ratio_threshold_percent` |
| 最小件数 | 件(0 以上) | `min_delete_count` | 同名 |

- リクエストは `ttl_days` か `ttl_seconds` の**どちらか一方だけ**を送る(両方・どちらもなしは 400)。応答の `ratio_threshold_percent` が小数第 3 位以下を持つときの扱いは 7.7。フォームのモデルは「TTL のモード(日・秒)と値」を持ち、モードは S4 の読み込み時に応答の `ttl_days` の有無で決める。
- 既定値は**補わない**(必須。B 2.8・画面仕様 #2)。

### 7.4 確認ダイアログと送信(DS 4.8。FARC-P-32)

- ダイアログの水準(要確認・標準 / 警告つき / 要入力確認)の割当は admin-view 6 章。本書は**実行の流れ**だけを決める: 実行 → mutation(`isPending` の間は実行ボタン・入力を無効にして二重送信を防ぐ)→ 成功: 閉じる+スナックバー+invalidate(5.8)/ 失敗: 開いたまま内側にアラート(6.3)。
- 「要確認・警告つき」「要入力確認」は `persistent`。要入力確認(データソースの削除)は、前後の空白を除いた識別子の**完全一致**(大文字小文字を区別)でだけ実行ボタンを有効にする(DS 4.8)。
- S3・S4 の保存の送信中表示・成功後の移動は sources 2.5 に従う。

### 7.5 リクエスト本文の作り方(B 2.12・3.3・3.4・4.1。FARC-P-16)

- **型は厳密**(B 2.12。JSON の型を変換しない。`30.0` は整数でない): 整数の項目(`ttl_days`・`ttl_seconds`・`min_delete_count`)は整数の JSON、`ratio_threshold_percent` は JSON の数値、真偽値は真偽値で送る。**文字列で送らない**(入力欄の文字列を送る直前に数値へ変換する。7.2)。未知の項目を足さない(400 `unknown_field`)。
- **S3(EP-03)**: `source_id`・`connector_type`・`connector_config`(`file_system` の 5 項目を**常に全部**。空配列・`false` も省略しない。admin-view 10.4)・`ttl_days` か `ttl_seconds` の一方・`ratio_threshold_percent`・`min_delete_count`・`schedule_cron`(空は `null`)。
- **S4(EP-04)**: 上から **`source_id`・`connector_type` を除く**(含めると 400 `unknown_field`)。全置換なので、必須項目を省略しない。
- **`Content-Type`**: 本文があるとき(EP-03・04・06)は `application/json` を必ず付ける(B 2.12。ないと 400)。本文が空なら Content-Type は問われず `{}` として扱われるが、EP-06 も画面は常に JSON 本文を付ける。
- **EP-06**: `{ "force_delete": <真偽値>, "rewrite_mode": <真偽値> }`(画面は常に両方を明示する。再実行は J2 の元ジョブの値をそのまま)。EP-05・07・08 は**本文なし**。

### 7.6 S4 で読めない設定項目があるとき(FARC-P-28。AAPI-U-10・AAPI-P-34 への回答)

EP-02 は、保存済みの設定項目が読めないとき、その項目を `null` にして `unavailable.<項目名>=malformed` を付ける(B 3.2。S4 が修復できるようにするため)。S4 は全置換のため、`null` のままの項目を送ると、読めなかった値を別の値で上書きする。そこで(案):

- 読めない項目があるときは、フォームの上部に warning アラート「保存されている値を読めない項目があります。入力し直して保存してください」を出し、その項目を**空欄・必須**にする(画面仕様の検証の対象。既定値は補わない)。
- **`connector_config` が読めないとき**(5 項目をまとめて再入力させると、意図しない設定になりうる)は、フォームを出さず、S4 の取得失敗と同じエラーブロックにする(`config_invalid` などで直せる範囲を超えるため。Crawler API で直す旨を案内する)。
- この状態は画面仕様にない(I-87)。画面仕様の追記は HO-29。

### 7.7 保存値が小数第 3 位以下を持つしきい値(FARC-P-29。AAPI-P-38 への対応。案)

Crawler の API を直接使って登録された値(例 `0.12345` → 応答は 12.345 %)は、応答の `ratio_threshold_percent` が小数第 2 位を超える(B 2.8)。そのまま再保存するとリクエストの検証で `format` になる(秒指定のような逃げ道は B にない)。画面の扱い(B 2.8 が画面の責務とした点。画面仕様にない。I-87):

- S4 の読み込み時、応答の値が小数第 2 位を超えるかを判定する(数値から文字列表現にして桁を数える)。超えるときは、入力欄に**小数第 2 位に丸めた値**を入れ、項目の下に注意(「保存されている値は 12.345 % で、小数第 3 位以下があるため、12.35 % に丸めて保存されます」。丸め方は四捨五入を案とし、文言は画面仕様に委ねる)を出す。
- 利用者が丸めた値を見て保存することを確認とみなす(追加の確認チェックは置かない)。値を変えずに他の項目だけ編集して保存しても、しきい値は丸めた値に更新される点を注意に含める。
- S2 は、保存値を丸めずに表示する(応答の値のまま)。判断が変わる(API が丸めを受ける)なら B のゲート3で決まる(B 2.8)。

---

## 8. 状態管理

**Pinia は使わない**(承認前の DS 10.1 の案を踏襲。FARC-P-17)。状態は次の 4 か所に置く。

| 種類 | 置き場 | 例 |
| --- | --- | --- |
| サーバーの状態 | TanStack Query(5章) | 一覧・詳細・ダッシュボード・メタ。**最終取得成功日時**は `dataUpdatedAt` |
| 画面の条件 | **URL のクエリ**(唯一の正。5.6) | `page`・`size`・`sort`・`source`・`status`・`tab`・O1 の `q`・`state` |
| 画面内の一時の状態 | コンポーネントの `ref`(フォームの値、ダイアログの開閉、折りたたみ、D1 の自動更新スイッチ) | S4 のフォーム値、DLG の入力確認の文字列 |
| アプリ全体で 1 つの UI | 小さな composable(モジュール内の `ref`)。**永続化しない** | スナックバー、ドロワーの開閉 |

- `localStorage` などへの保存はしない(ユーザー設定を持たない。dashboard 4.1)。
- クエリの値を `ref` に**複製して二重に持たない**(ズレの原因になる)。

---

## 9. アクセシビリティ・Vuetify 利用上の注意

### 9.1 アクセシビリティ

方針・規約は DS 8章が正(キーボード・フォーカス・ラベル・状態の伝え方・動的更新・コントラスト)。本書が決める実装上の要点:

| 項目 | 方針 |
| --- | --- |
| 画面遷移 | パスが変わったときだけ `h1`(`tabindex=-1`)にフォーカス。`document.title` を更新(4.5) |
| 動的更新 | ポーリング・自動更新は読み上げない(`aria-live` なし)。操作の成功は `role="status"`、取得失敗は `role="alert"`(6.6) |
| 状態ブロック | 読み込み中は `aria-busy="true"` と視覚的に隠した `role="status"`(DS 4.5) |
| ダイアログ | フォーカスの閉じ込め・復帰・Esc は DS 4.8。**Vuetify の `VDialog` で実際に満たされるかは実機確認**(DS 8章。FARC-U-14) |
| 外部通信 | ランタイムで外部へ取得しない(フォント・アイコン・CSS・CDN。DS 3.1)。Playwright で、同一オリジン以外への要求がないことを確認する(10.2) |

### 9.2 Vuetify の設定・注意(参照)

設定値の正本は DS 3章。実装時に守る点:

- `createVuetify` に `display.mobileBreakpoint: 'md'` を**明示**(既定は `lg`)。`VNavigationDrawer` に静的な `permanent` を付けない(DS 3.1・3.2・7)。
- `vite-plugin-vuetify` で必要な部品だけを取り込む(tree-shaking)。アイコンは `@mdi/js` から**名前付き import**し、`@mdi/font`・CDN の `<link>` は使わない(DS 3.1)。
- `defaults` のマージ規則が v3 と異なる(DS 3.2)。見え方は画面で確認する。
- Vuetify の部品の props・挙動(`VDataTableServer` の `hover`、`VAlert` の左帯の色、`VBreadcrumbs` の `divider`、`VExpansionPanels` の遅延描画と検証、`VBtn` の `aria-disabled`、density と高さ)は DS が「実機 4.3.4 で要確認」とする。本書は新しい確認事項を足さず、実装後に `web-ui-reviewer` が確認する(DS 14章。FARC-U-14)。
- Vuetify は週次でリリースされる。exact pin し、更新は検証してから行う(DS 10.3)。

---

## 10. テスト方針

テストコード・設定ファイルは作らない(FARC-P-38)。方針と設定の要点だけを書く。ディレクトリ・フィクスチャの置き場は F。

### 10.1 Vitest(FARC-P-21)

- **対象**: 純粋なロジックを中心にする。エラー変換表(6.3 の全 code)、URL ↔ `params` の変換・正規化、`refetchInterval` の関数(D1・J2)、検証規則の純関数、単位・モード(日・秒)の扱い、`StatusTag` の対応表、key factory、ナビの抽出・並び(`meta`)。コンポーネントは props と状態の出し分け(ダイアログの有効・無効、状態ブロック)まで。**レイアウト・コンテナクエリ・フォーカスの実挙動は Playwright と実機**(10.2・10.3)。
- **設定の要点**(DS 10.1): Vuetify を使うため `test.server.deps.inline: ['vuetify']`、`ResizeObserver` のモック(setup)、マウントは `createVuetify()` と `VLayout` で包む共通ヘルパー。環境は **jsdom を第一案**(DS 10.1 の前提)。jsdom で Vuetify 4.3.4 の部品(`VDataTableServer`・`VDialog`・`VNavigationDrawer`)が動かない場合は Browser Mode に替える(未決。FARC-U-9)。
- **API の扱い**: ネットワーク層(fetch)を差し替え、生成クライアントを実際に通す。`QueryClient` はテストごとに新しく作り、`retry: false`。ライブラリによるモックサーバー(MSW など)は足さない(案)。
- **時刻**: `TZ` を固定し(`Asia/Tokyo`。ブラウザのローカル時刻の表示を再現可能にする。DS 4.9)、ポーリングは偽のタイマーで検証する。
- **エラー変換表**は、B 2.3 の全 `code`(Admin 固有 14 種+共通 6 種)を 1 件ずつ、表のデータから網羅するテストにする(code を足したときテストが落ちる構成)。

### 10.2 Playwright(E2E。FARC-P-22)

範囲は**方針まで**(FARC-P-38)。

| 項目 | 方針 |
| --- | --- |
| 主たる方法 | **`page.route` による API モック**(`**/api/admin/v1/**`)。画面のフロー(遷移・ガード・ダイアログ・フォーム・エラー表示・SPA 内の 404)と a11y の振る舞い(フォーカスの移動・ダイアログの閉じ込めと復帰・`aria-sort`。DS 8章)を検証する |
| 実 API | **少数のスモーク**(読み取りのみ): D1・S1・O1 が開く、`/admin/sources` の再読み込みが SPA を返す(フォールバック)、`/admin/assets/` の欠落ファイルが 404、`/api/admin/v1/…` の未知のパスが JSON の 404(A 2.2。BAPI-U-1 の確認を兼ねる)。変更操作は含めない。起動する環境(compose の `api`・OpenSearch)は、既存の結合テストと**ホストのポートが衝突しうる**(固定の 9200・8000・8001。`tests/integration/crawler/README.md`)ため、同時に動かさない |
| モック応答 | **生成した型で `satisfies`** して型付けする(API の変更が型エラーになる)。エラー応答も A 5.2 の型で書く。1 つのフィクスチャ集と `mockApi` ヘルパーに集約する |
| 未モックの要求 | `/api/` への**未モックの要求はテストを失敗**させる(`route` の最後に補足して記録)。開発プロキシの先(8080)に要求を流さない |
| `baseURL` | `http://localhost:5173/admin/`(**末尾のスラッシュを含める**)。遷移は**先頭にスラッシュのない相対パス**(`goto('sources')`)で書く。`goto('/sources')` は `/admin` を落として origin 直下に解決される。`request` フィクスチャの相対パスも同様に `/admin/` の下になる。実機での挙動は確認する(FARC-U-8) |
| サーバー | `webServer` は `url` を `http://localhost:5173/admin/`、`reuseExistingServer: !process.env.CI`(0004)。CI では `vite preview`(ビルド成果物)を使う案。その場合、`baseURL`・`webServer` の `url` を preview のポート(既定 4173)に合わせる |
| ロケーター | ロールとラベルを第一にし、`data-testid` は DS 9章の命名に従う(`s1-sources-table`・`dlg-crawl-start`・`nav-{route 名}`・各 `*-state-*`)。本書で `data-testid` を追加しない(FARC-K-9) |
| タイムゾーン・時計 | `timezoneId: 'Asia/Tokyo'` を固定。ポーリング(30 秒・10 秒)は Playwright の時計の操作で進める(推測。実機で確認。FARC-U-8) |
| ブラウザ | 自動 E2E は **Chromium 1 つ**。Firefox 128・Safari 16.4 は実機で最小限の確認(FARC-U-15) |
| 外部通信 | 全画面の読み込みで、同一オリジン以外への要求が 0 件であることを確認する(DS 3.1) |
| 幅 | 375 / 768 / 840 / 1024 / 1280px(admin-view 8.4)で、ページ全体の横スクロールがないこと、サイドバーの出し分け(840px の境)を確認する |

- 代表フローの最低限(案): D1(正常・異常・stale 降格)、S1→DLG-1(受付・`lock_held` の拒否)、S3 の項目別エラー(`config_invalid`)、S4 の取得失敗でフォームを出さない、J1 のページング・絞り込みの URL 同期、J2 のポーリング停止、DLG-3 の `job_already_finished` を成功扱い、X1 のタブ・`existence`、O1 の絞り込み・stale。

### 10.3 実機確認が必要な点

自動テスト(jsdom・モック)では確かめられず、実機(Vuetify 4.3.4・実ブラウザ・実 API)で確認する点。DS が挙げるものを再掲せず参照する。

| 点 | 内容 | ID |
| --- | --- | --- |
| Vuetify の挙動 | DS が「実機 4.3.4 で要確認」とする項目(`mobileBreakpoint`・`permanent`・`VTabs`・`VDialog` のフォーカス・`VDataTable` の `hover`・`VBreadcrumbs`・`VExpansionPanels`・`VBtn` の `aria-disabled`・高さ・J1 の最小幅のフォント依存) | FARC-U-14 |
| ビルド | `vite-plugin-vuetify` と Vite 8、SASS の設定、既定の `build.target` | FARC-U-1・10 |
| 配信 | `app.frontend("/admin")` の細部、キャッシュヘッダー | FARC-U-6 |
| 生成 | Hey API の `throwOnError`・生成 key・生成物の安定性 | FARC-U-4・5 |
| ブラウザ | Firefox 128・Safari 16.4 | FARC-U-15 |
| スクリーンリーダー | 列見出し(O1)の読み上げなどは実機のスクリーンリーダーで(opensearch 7章) | — |

---

## 11. 静的解析・品質

### 11.1 構成(FARC-P-23)

- **ESLint**(flat config): `eslint-plugin-vue`(推奨)+`typescript-eslint`。Prettier との衝突は設定の無効化で避け、整形は Prettier だけが行う。生成コード(5.2)と `dist/` は対象外。
- **TypeScript**: `strict: true`。`vue-tsc` で `.vue` を含めて検査する(`vite build` の前)。
- **依存方向の機械検査**は F が定める(Crawler・Indexer の AST 検査に相当)。手段の第一候補は ESLint の `no-restricted-imports`(例: 生成クライアントと `fetch` を使えるのは API 層だけ。`/api/admin/v1` の文字列は `baseUrl` の設定箇所だけ。`@mdi/font` の禁止)。
- スクリプト(要点): `dev`・`build`(型検査 → `vite build`)・`preview`・`typecheck`・`lint`・`format` / `format:check`・`test`・`test:e2e`・`gen:api`。

### 11.2 品質ゲートの順(案)

`gen:api`(再生成して差分なし)→ `typecheck` → `lint` → `format:check` → `test`(Vitest)→ `build` → `test:e2e`(Playwright)。依存の更新(2.2)もこの順で通す。CI の定義は infra の作業(コード・設定ファイルは本タスクで作らない)。

---

## 12. 確認状況

### 12.1 確認した事実(2026-11-22)

- PR #10 のレビュー指摘(0037)に基づく B・A の修正(0038。AAPI-P-42。一覧の `unavailable` を行単位に)を読み、5.7・5.9・6.2 を B 2.2・2.11・3.1・5.1・6.1 と再照合した。
- R3 の修正(0018)と、0020・0022 後の B・A(`JobBrief`・`registration` の `null` 許容、`rerun_blocked_reason=source_missing`、AAPI-P-39・41)を読んで、5.7・5.9・6.3・6.7 を B と再照合した。
- 読んだ文書: A(R1 の修正後)、B(初稿は骨子。本文の完成後に 2〜8章・9章・10章・11.3〜11.5・11.8〜11.10 を読んで照合し、**R1 の修正後に、2・3・8 章の変更部分と 11.1・11.2・11.6・11.7 を読んで再照合した**。11.1 は事実の確認範囲、11.2 は K の整理(AAPI-K-6 欠番・K-9 の出典)、11.6 は AF-U の状態表、11.7 はゲート2の回答表で、E の記述と食い違いはない)、DS(0・2〜5・7〜10・14章)、admin-view(4・5・7・8・10章)、画面仕様 5 本(各状態・更新・データ項目)、作業記録 0001・0002・0004・0006・0007。
- リポジトリ: `apps/web/` は存在しない(新規)。`apps/crawler`・`apps/indexer` の Dockerfile のコンテキストはアプリのディレクトリ(`build: ../../apps/<名前>`)で、Indexer の Dockerfile はベースイメージをタグとダイジェストで固定している。`tests/integration/crawler/README.md` はホストの固定ポート(9200・8000・8001)と同時実行不可を述べる。
- 技術事実(版、Node の要件、Hey API の対応、FastAPI の `app.frontend()`、Playwright の `page.route`・`webServer`、TypeScript 7 の `vue-tsc` 公式未対応など)は、フェーズ0の tech-advisor の報告(0004。調査日 2026-11-22)による。**本書の作成者は再確認していない**。

確認していないこと: 12.4 の FARC-U。ほかに、Vue Query v5 の `isLoading` の意味・Playwright の時計の操作・compose の `additional_contexts` の対応版は作成者の知識による推測(該当箇所に明記)。

### 12.2 確定(FARC-K)

確定にしたのは、ユーザー回答と既承認文書(ユーザー承認済みの画面仕様・DS)の引用だけ。承認済みの案を引用したもの、ゲート1・2で承認された方針・値は確定にしない(12.3)。FARC-K-2 は B の整理(R1 I-5)に合わせて、FARC-K-5・K-6・K-7 は DS・画面仕様のゲート B・C の承認事項の引用のため(R3)、欠番にして FARC-P-30〜33 に移した。FARC-K-8 は、0001 の「確定した要件」ブロックがユーザーの個別回答ではないため(R4)、欠番にして FARC-P-38 に移した。

| ID | 内容 | 出典 |
| --- | --- | --- |
| FARC-K-1 | Vuetify 4.3.4(exact pin)、TypeScript 6.x 固定、`@mdi/js`(`vuetify/iconsets/mdi-svg`)、自前ナビ(`VNavigationDrawer` + route `meta`) | DS 10.1(承認済み(ゲート B 2026-11-21)) |
| FARC-K-2 | (欠番。確定ではなく承認済みの案(ゲート1)のため FARC-P-30 に移した。要件 0000 はこれらを「技術スタック案」と書き、0001 の「確定した要件」はユーザーの個別回答ではない。B の BAPI-K-3 の区分整理(R1 I-5)に合わせた) | — |
| FARC-K-3 | 対応ブラウザ: Chromium 119+ / Firefox 128+ / Safari 16.4+ | DS 10.1(ユーザー了承済み) |
| FARC-K-4 | Web UI は `api` が静的配信する(同一オリジン。CORS 不要) | BAPI-K-2(ユーザー回答 2026-11-22。0001 Q2) |
| FARC-K-5 | (欠番。確定ではなく承認済みの案(DS のゲート B・C の承認事項の引用)のため FARC-P-32 に移した。R3 の指摘。FARC-K-6 → P-31 と同じ整理) | — |
| FARC-K-6 | (欠番。確定ではなく承認済みの案(画面仕様のゲート B・C の承認事項の引用)のため FARC-P-31 に移した。B の AAPI-K-9 → AAPI-P-40 と同じ整理) | — |
| FARC-K-7 | (欠番。確定ではなく承認済みの案(DS 4.9・ゲート C #36 の引用)のため FARC-P-33 に移した。R3 の指摘) | — |
| FARC-K-8 | (欠番。確定ではなく承認済みの案(ゲート1。作業プラン 0002 の承認)のため FARC-P-38 に移した。0001 の「確定した要件」ブロックはユーザーの個別回答ではなく、FARC-K-2 と同じ整理。R4 の指摘) | — |
| FARC-K-9 | 日本語のみ・ライトテーマのみ・システムフォントを使い外部フォントと CDN を使わない(DS 前提 2〜4)。要素の特定はロール・ラベル基準で、必要な箇所だけ `data-testid`(前提 6) | DS 0.1 の前提 2〜4・6(承認済み)の引用。ランタイムの外部通信全般の禁止(DS 3.1)は DS 3 章(案のまま)で、本書は同じ方針を採る(FARC-P-32) |

### 12.3 案・承認済みの案(FARC-P)

ここにある案は、すべてゲート3(2026-11-23)で承認された(承認済みの案(引用)・導出・解釈の扱いは G3-3 でユーザー確認済み)。

区分欄は承認したゲートを書いた(ゲート1=方針、ゲート2=具体値・名前。いずれも 2026-11-22)。確定(`-K-`)にはしていない。

| ID | 内容 | 区分 | 章 |
| --- | --- | --- | --- |
| FARC-P-1 | 型・クライアント・Query 生成は Hey API(`@hey-api/openapi-ts`。exact pin)。入力は `app.openapi()` の書き出し | 承認済みの案(ゲート2。BAPI-P-10) | 2.1・5.2 |
| FARC-P-2 | `base: '/admin/'`、history モード、`/admin/` 配下だけ `index.html` にフォールバック。実装は `app.frontend()` | 承認済みの案(方針はゲート1、範囲と `app.frontend()` の第一候補はゲート2。BAPI-P-2) | 3.2・3.3 |
| FARC-P-3 | Node: 22.18 以上の 22 系・24 系・26 以上(Vitest 5 の要件 `^22.12`・`^24`・`>=26` のいずれか、かつ Hey API の `>=22.18` を満たす)。推奨 24 LTS。Docker・CI は 24 | 承認済みの案(ゲート3。2026-11-23。推奨は tech-advisor。0004) | 2.1 |
| FARC-P-4 | 固定範囲: exact(Vuetify・Hey API・Playwright)、minor(Vite・`vue-tsc`)、`~6.0.x`(TypeScript)、その他は caret + ロック | 承認済みの案(ゲート3。2026-11-23)。ただし Vuetify の exact pin と TypeScript 6.x 固定は確定(FARC-K-1)、Hey API の exact pin は承認済みの案(ゲート2。FARC-P-1)。minor 固定・caret・Playwright の exact は承認済みの案(ゲート3) | 2.1・2.2 |
| FARC-P-5 | npm と `package-lock.json`(`npm ci`) | 承認済みの案(ゲート3。2026-11-23) | 2.1 |
| FARC-P-6 | 書き出した OpenAPI JSON と生成コードをコミットし、CI で再生成の差分を検査 | 承認済みの案(ゲート3。2026-11-23。確定は FARC-U-5) | 5.2 |
| FARC-P-7 | API クライアント: 生成 fetch クライアント+薄いラッパー(`baseUrl` の集約、`ApiError` への正規化、タイムアウト 読 45 秒・書 90 秒、自動再送なし) | 承認済みの案(ゲート3。2026-11-23。タイムアウトは仮値) | 5.3 |
| FARC-P-8 | Query の既定値(`retry` 1(`timeout` は再試行しない)・`staleTime` 0・フォーカス・再接続での再取得なし・マウント時は再取得・mutation の再試行なし・グローバル通知なし)と key factory | 承認済みの案(ゲート3。2026-11-23。`retry: 1` は DS 10.1 の案。ライブラリの採用は FARC-P-30) | 5.4 |
| FARC-P-9 | ポーリングの実装(D1 `refetchInterval` 30 秒+スイッチ、J2 は状態に応じた関数で 10 秒) | 承認済みの案(ゲート3。2026-11-23。更新間隔は承認済みの案 FARC-P-31) | 5.5 |
| FARC-P-10 | サーバー側ページング: URL ↔ Vuetify ↔ API の対応、URL を唯一の正、`push`/`replace`、同スコープだけ前回データを保持 | 承認済みの案(ゲート3。2026-11-23) | 5.6 |
| FARC-P-11 | 画面別の取得方針の表、mutation と invalidate の表 | 承認済みの案(ゲート3。2026-11-23) | 5.7・5.8 |
| FARC-P-12 | S4 は編集専用の key・`gcTime: 0`・1 度だけ初期化 | 承認済みの案(ゲート3。2026-11-23) | 5.8 |
| FARC-P-13 | エラー変換表(1 か所)、表示先 4 つ、項目別エラーの写像、想定外の診断表示 | 承認済みの案(ゲート3。2026-11-23。code 名は B 2.3。承認済みの案(ゲート2)) | 6.1〜6.4 |
| FARC-P-14 | 取消の 409 `job_already_finished` は成功扱い。`lock_held` はダイアログ内アラート+「反映されていない」の明示 | 承認済みの案(ゲート2。AAPI-P-21・AAPI-P-13。表示は admin-view 7.7=ゲート B) | 6.3 |
| FARC-P-15 | 結果不明: 504・クライアントのタイムアウト・書き込みのネットワーク断は、起動系・取消・解放では再試行を出さず確認を促す。保存系(EP-03・04)は再送が安全なので再保存も出してよい | 承認済みの案(ゲート3。2026-11-23) | 6.5 |
| FARC-P-16 | 検証: 自前の純関数・表(`ttl` は 1 以上)。単位変換は Admin API(B 2.8)で、画面は日・%・秒モードで入力。数値は文字列で検証してから数値化。本文は B 2.12 の型の規約どおりに作る | 承認済みの案(ゲート3。2026-11-23。単位変換の担当は承認済みの案(ゲート2。AAPI-P-14)) | 7章 |
| FARC-P-17 | 状態管理: Pinia なし。Query・URL・`ref`・小さな composable。永続化なし | 承認済みの案(ゲート3。2026-11-23。DS 10.1 の案を踏襲) | 8章 |
| FARC-P-18 | Router: `meta` の型(`title` は関数を許す)、`afterEach` のフォーカス・タイトル、クエリの正規化、`featureFlag` は `/meta` 由来でナビ(`SideNav`・外部リンク領域)だけが評価(I-89)、認証・離脱ガードなし、遅延読み込みを使う場合の `router.onError` | 承認済みの案(ゲート3。2026-11-23) | 3.3・4.3・4.5 |
| FARC-P-19 | Vite 設定(`base`・`outDir`・プラグイン)、開発プロキシ(`/api` → `127.0.0.1:8080`)、ランタイム設定を持たない | 承認済みの案(ゲート3。2026-11-23) | 3.1・3.4 |
| FARC-P-20 | Docker: Node 24 のビルドステージ(タグ+ダイジェスト固定)、`npm ci`、成果物を `api` イメージへ。ビルドステージで型生成をしない | 承認済みの案(ゲート3。2026-11-23。コンテキストは FARC-U-11) | 3.5 |
| FARC-P-21 | Vitest: 純粋ロジック中心、jsdom 第一案、`TZ` 固定、fetch 差し替え、エラー変換表の網羅 | 承認済みの案(ゲート3。2026-11-23。DS 10.1 の設定要点は案) | 10.1 |
| FARC-P-22 | Playwright: `page.route` モック主・実 API は読み取りのスモーク少数、生成型の `satisfies`、未モックの要求は失敗、`baseURL` は `/admin/`、Chromium のみ | 承認済みの案(ゲート3。2026-11-23) | 10.2 |
| FARC-P-23 | ESLint(flat)+ `typescript-eslint` + `eslint-plugin-vue` + Prettier、`vue-tsc`・`strict`、品質ゲートの順 | 承認済みの案(ゲート3。2026-11-23) | 11章 |
| FARC-P-24 | 日時の整形は `Intl.DateTimeFormat` のみ(日時ライブラリなし)。409 の `existing_job.lease_expires_at` の番兵 `0001-01-01T00:00:00.000Z` は「期限切れ」として扱い、整形しない(B 2.11・I-73) | 承認済みの案(ゲート3。2026-11-23) | 5.9 |
| FARC-P-25 | `/meta`(EP-14)は `staleTime: Infinity`。失敗は Dashboards リンク非表示・タイムゾーン警告 | 承認済みの案(ゲート3。2026-11-23) | 3.1・5.7 |
| FARC-P-26 | 入れないもの: Pinia・Tailwind・vue-i18n・VueUse・検証ライブラリ・日時ライブラリ・axios | 承認済みの案(ゲート3。2026-11-23。DS 10.1 の案を踏襲) | 2.4 |
| FARC-P-27 | 部分失敗(B 2.2。AAPI-P-25・42。`unavailable` に載る取得失敗と、載らない値の読めない `null` は別。FARC-P-36): 単一の応答は最上位、**一覧の EP は各行の `unavailable`**(キーは行内の相対パス)を、それぞれ引く関数を通す。`null` でキーがあれば取得できない、キーがなければ値がない。理由コードは画面では区別しない | 承認済みの案(ゲート3。2026-11-23)の修正(PR #10 のレビュー指摘への対応。AAPI-P-42。B の側は同じ修正) | 5.9・6.2 |
| FARC-P-28 | S4 で保存済みの設定項目が読めないとき(`malformed`): 該当項目を空欄・必須にして再入力させる。`connector_config` が読めないときはフォームを出さない(AAPI-U-10 への回答) | 承認済みの案(ゲート3。2026-11-23) | 7.6 |
| FARC-P-29 | 保存値のしきい値が小数第 3 位以下を持つとき(応答が小数第 2 位を超える): S4 は丸めた値(四捨五入が案)を入力欄に入れて注意を出し、保存を確認とみなす。S2 は丸めずに表示(AAPI-P-38 への対応) | 承認済みの案(ゲート3。2026-11-23。B の側は同じゲート3で承認) | 7.7 |
| FARC-P-30 | 構成要素: Vue 3、Vite、Vue Router、TanStack Vue Query、Vitest、`vite-plugin-vuetify`、ESLint / Prettier、Playwright(旧 FARC-K-2) | 承認済みの案(ゲート1。2026-11-22。0002 2章がこれらを 0001 の確定事項として挙げ、ゲート1で承認された。0003。DS 10.1 では案。区分の変更はゲート3でユーザー確認済み。2026-11-23) | 2.1 |
| FARC-P-31 | 更新間隔: D1 は 30 秒(一時停止スイッチあり。タブが見えない間は止める)、J2 は実行待ち・実行中のみ 10 秒、S1・S2・J1・X1・O1 は手動のみ(旧 FARC-K-6。B の AAPI-P-40 と対応) | 承認済みの案(画面仕様のゲート B・C の承認事項の引用: dashboard 4.1・admin-view #26(D1)・#8(J2)・#33(S2)。ユーザー確認済み(ゲート3。2026-11-23)) | 5.5 |
| FARC-P-32 | ナビは route `meta` で一元管理、ページテンプレート 4 型、状態表示(読み込み中・空・エラー・stale)の規約、危険度別の確認ダイアログ(旧 FARC-K-5)。外部通信の禁止(DS 3.1)も同じ方針を採る | 承認済みの案(DS 4.5・4.8・5.3・6章のゲート B・C の承認事項の引用。ユーザー確認済み(ゲート3。2026-11-23)。DS 3 章は案のまま) | 4.4・7.4・9.1 |
| FARC-P-33 | 日時はブラウザのローカル時刻(`YYYY-MM-DD HH:mm`。タイムゾーン略称なし)で表示する(旧 FARC-K-7)。API の時刻の形式(UTC の ISO 8601)は BAPI-P-20(承認済みの案。ゲート3でユーザー確認済み。2026-11-23)。**ブラウザと Crawler のタイムゾーンが異なる場合の表示は DS 4.9・14章で未決**(FARC-U-19) | 承認済みの案(DS 4.9・ゲート C #36 の引用。ユーザー確認済み(ゲート3。2026-11-23)) | 5.9 |
| FARC-P-34 | S2 のロック状態カード(と J2 のリース切れのカード)の写像: `lock.state` 7 値+取得失敗 → 画面仕様の 6 種+取得失敗。`held_*` の実行待ちは「実行待ち」のタグ、`unknown` は「状態を確認できません」 | 承認済みの案(ゲート3。2026-11-23) | 5.10 |
| FARC-P-35 | `lock_held`・`lock_in_use` の導線: `existing_job.status`(または `job_type`)が `null`(`orphan`・`just_acquired`・`unknown`)のとき、「ジョブを表示」(J2)を出さず、S2 のロック状態カードへ導く。admin-view 7.7 との差は I-88 | 承認済みの案(ゲート3。2026-11-23。ゲート3でユーザー確認済み。2026-11-23) | 6.3 |
| FARC-P-36 | 値の読めない `null`(ジョブ記録・削除記録・ロック文書など。B 2.2・2.11。AAPI-P-25)と取得失敗(`unavailable`。一覧は各行・単一は最上位)の表示: どちらも「—」で、取得失敗は「取得できません」(表示の見える・隠すは画面仕様に従う)、読めない `null` は視覚的に隠した「読み取れません」。`status=null` のジョブにはタグ・操作を出さない | 承認済みの案(ゲート3。2026-11-23)の修正(PR #10 のレビュー指摘への対応。AAPI-P-42) | 5.9・5.7 |
| FARC-P-37 | `rerun_blocked_reason=source_missing` は「再実行」を出さない(削除済みのソースを再実行しない)。`rerunnable=null`(設定の読み取り失敗を含む)も出さない。専用文言は画面仕様に足す(HO-30) | 承認済みの案(ゲート3。2026-11-23。AAPI-P-41) | 6.7 |
| FARC-P-38 | E2E は方針までを設計し、テストコード・設定ファイルは作らない(旧 FARC-K-8) | 承認済みの案(ゲート1。0003 で作業プラン 0002 を承認)。「方針までを設計し、実装コードは作らない」は要件 0000 のスコープ外(ユーザー記載)と 0002 に基づく。「テストコード」の部分は承認済みの案(ゲート3。2026-11-23)(0001 の確定ブロックはユーザーの個別回答ではないため) | 10 |
| FARC-P-39 | 一覧の EP(EP-01・09・11)の `unavailable` を**行単位**で判定する: 各 `items[i].unavailable`(キーは行内の相対パス)で取得失敗を判定し、最上位の `unavailable` は行に属さない項目(EP-11 の `tab_counts.<タブ>`・`document_count`)だけ。旧規則「一覧でキーがあり行が `null` なら取得できません」は廃止。単一の応答は最上位のまま | 承認済みの案(ゲート3。2026-11-23)の修正(PR #10 のレビュー指摘への対応。2026-11-23。AAPI-P-42)。**`-K-` ではない** | 5.7・5.9 |

### 12.4 未決・実装時確認(FARC-U)

| ID | 内容 | 決める場所 |
| --- | --- | --- |
| FARC-U-1 | `vite-plugin-vuetify` 2.1.x と Vite 8(Rolldown)の組み合わせ(開発・ビルド・`styles.configFile`)、`sass` の要否(0004) | 実装時 |
| FARC-U-2 | Vuetify 4.3.4 の `VDataTableServer`(`@update:options` の初期発火、単一ソートの設定、`hover`、`aria-sort`)と、jsdom で動くか(0004) | 実装時 |
| FARC-U-3 | `@mdi/js`(Apache-2.0)の社内ポリシー上の扱い(DS 14章) | 運用・ユーザー確認 |
| FARC-U-4 | Hey API 0.99 の `throwOnError` の既定、Query のエラー処理(stale 表示)との接続、生成 key の形、プラグインの設定(BAPI-U-5。0004) | 実装時 |
| FARC-U-5 | 生成コード・OpenAPI JSON のコミット方針(FARC-P-6)の確定(出力の安定性・差分の大きさ。BAPI-U-5) | 実装時 |
| FARC-U-6 | `app.frontend("/admin")` の細部(`/admin` 末尾スラッシュなし、`/admin/` 配下の欠落アセットの 404、`/api/` との優先)、`index.html` と `assets/` のキャッシュヘッダー(BAPI-U-1。0004) | 実装時 |
| FARC-U-7 | サブアプリのマウント時の OpenAPI の `paths`・`servers` と `baseUrl`(BAPI-U-2) | 実装時 |
| FARC-U-8 | Playwright: `baseURL` に `/admin/` を含めたときの相対遷移・`request` フィクスチャの解決、時計の操作(0004) | 実装時 |
| FARC-U-9 | Vitest を jsdom にするか Browser Mode にするか、`test.server.deps.inline` が Vitest 5 で有効か、`ResizeObserver` のモック(0004、DS 10.1) | 実装時 |
| FARC-U-10 | Vuetify 4.3.4 公式の Node 最小要件(第三者ミラーで 24.11.1)、TypeScript 6.x の最新パッチ、Vite 8 の既定の `build.target` とブラウザ要件の整合(0004) | 実装時 |
| FARC-U-11 | Docker のビルドコンテキスト(I-82)と Node ベースイメージのタグ・ダイジェスト | infra の前提作業 |
| FARC-U-12 | B の案(AAPI-P-16〜18・24〜34・37〜39・41・42。ゲート3で承認済み。P-16・25・27・30 は PR #10 のレビュー指摘で修正)が変わったときの追従と、C(導出ロジック。B 11.10)の確定後の再確認(12.6) | C 確定後 |
| FARC-U-13 | 9 桁を超える既存値(Crawler API を直接使って登録された `ttl_seconds` など)の編集時の扱い | 実装時 |
| FARC-U-14 | DS が「実機 4.3.4 で要確認」とする Vuetify の挙動(9.2・10.3) | 実装後(`web-ui-reviewer`) |
| FARC-U-15 | Firefox 128・Safari 16.4 の実機確認の範囲(自動 E2E は Chromium のみ) | 実装後 |
| FARC-U-16 | クライアントのタイムアウトの仮値(読 45 秒・書 90 秒)の実測(BAPI-U-6) | 実装後 |
| FARC-U-17 | Search View と同じビルドにするか(`base: '/admin/'` の前提。BAPI-U-4) | Search View の設計 |
| FARC-U-18 | 生成 SDK がパスの値(`job_id`・`source_id`)を全文字エンコードして送るか。`%`・`?`・`#`・`.` を含む `job_id` の Crawler までの挙動(AAPI-U-12 の画面側) | 実装時 |
| FARC-U-19 | ブラウザと Crawler(`cron_timezone`)のタイムゾーンが異なるときの日時の表示(DS 4.9・14章。未決。FARC-P-33。ゲート3(G3-13。2026-11-23)で「決めず画面設計に任せる」ことを了承) | 画面設計(持ち越し) |

### 12.5 既存設計との不整合(I-n)

| ID | 内容 | 本書での扱い |
| --- | --- | --- |
| I-80 | DS 10.1 は TypeScript 7 を「`vue-tsc` が動かない報告がある」とするが、一次情報では「公式未対応(コミュニティの橋渡しで動く例はある)」(0004) | 結論(6.x 固定)は同じ。本書は「公式未対応」と書く。DS の記述の更新は HO-23 |
| I-81 | admin-view 4.2 の route `path`(`/`・`/sources` …)は `/admin/` を含まないが、A 2.2 は Admin View を `/admin/` 配下に置く | 画面仕様の `path` を Router の `base` からの相対と読む(3.2)。画面仕様への注記は HO-22 |
| I-82 | A 8 は「ビルドは `apps/api`」とするが、既存の compose のコンテキスト(アプリのディレクトリ)では `apps/web` を取り込めない | 3.5 に要求を書き、FARC-U-11 で確定。A 8 への追従は HO-37 |
| I-83 | DS 5.3 は `meta.title` を「文字列」とするが、admin-view 4.2 は S2・J2 などの動的な title(識別子・ジョブ ID)を要する | `title` を `string \| (route) => string` とする(4.3)。静的な場合は DS のとおり。DS の型記述の補足は HO-25 |
| I-84 | sources 2.4 の `reason` → 文言の表に、B の `range`・`exclusive`・`config_invalid` がない | 6.4 の扱い(案)。画面仕様への追記は HO-28 |
| I-85 | URL クエリ・`documentTabs` の表記と API の表記が違う: `source`(URL)↔ `source_id`、`size` ↔ `items_per_page`、`extract-failed`・`summary-pending`(kebab)↔ `extract_failed`・`summary_pending`(snake)。B 2.1 が E・F に対応づけを委ねている | 5.6 の対応表で 1 か所に定義する(不整合ではなく表記の差) |
| I-86 | J1 の並べ替えは、画面が「開始」列(実行待ちは受付日時を出す)の昇降順、B は `sort=queued_at`(受付日時。B 5.1 が画面の「開始」列に対応と明記)。`started_at` とは別の項目 | 本書は列の `key` を API の項目名(`queued_at`)にする。B 2.1 のとおり直列実行のため受付の順と開始の順は一致する(導出)ので、表示と並びのずれは生じない想定。実機で確認する |
| I-87 | 画面仕様に、B の応答から必要な状態の記述がない: O1 の `truncated=true`、X1 の `source` が存在しないとき、S2・S4 で設定項目が読めない(`malformed`)とき、J2 の `stalled`・`rerunnable` が `null` のとき、S4 で保存値のしきい値が小数第 3 位以下を持つとき(B 2.8。7.7)、S2 のロック状態が `unknown` のとき(5.10) | 6.7・7.6・7.7 の暫定の扱い(案)。画面仕様への追記は HO-29 |
| I-88 | admin-view 7.7 は `lock_held` で「ジョブを表示」(J2)を出し、失効したロックでは「ジョブ詳細でロックを解放」(J2 → DLG-5)とするが、孤児ロック・取得直後はジョブ記録がなく(`existing_job.status=null`。B 2.9・2.11)J2(EP-10)が 404 になりうる。孤児ロックの解放の入口は S2 だけ(sources 1.5・admin-view 4.1) | 6.3 のとおり、`status=null` では「ジョブを表示」を出さず S2 へ導く(承認済みの案(ゲート3)。FARC-P-35)。ゲート3でユーザー確認済み(2026-11-23)。画面仕様の追記は HO-31 |
| I-89 | DS 5.3 は `featureFlag` を「設定されていないときにナビとルートを隠す」とし、ナビ項目の定義を「route `meta` にだけ」持つ(`nav.external` も `meta` のキー)とするが、本書は (1) ナビ(外部リンク項目)だけを `SideNav` で隠し、ルートは隠さない(MVP に `featureFlag` を持つ route がなく、外部リンクは route を持たない。admin-view 4.2)、(2) **外部リンク項目を route `meta` でなく定義表 `shell/externalLinks.ts` に持つ**(`RouteMeta` から `nav.external` を外した) | 4.5 のとおり(承認済みの案(ゲート3)。FARC-P-18)。ゲート3でユーザー確認済み(2026-11-23)。DS 5.3 の追記は HO-26 |
| I-120 | 画面仕様に、Crawler・Indexer が書いた値が読めず `null` になる場合(B 2.2・2.11。`status=null` のジョブ、`registration` の件数・`partial`・`phase`)の表示の定義がない(画面仕様の「値がない」は「—」+「未設定」「なし」、取得失敗は「—」+「取得できません」) | 5.9 の (b)(「—」+視覚的に隠した「読み取れません」。`status=null` はタグ・操作なし。承認済みの案(ゲート3)。FARC-P-36)。画面仕様への追記候補は HO-30 |
| I-121 | `rerun_blocked_reason=source_missing`(B 2.9。AAPI-P-41)の理由の文言が画面仕様 jobs 2.3 にない(削除中・削除済みの文言もない) | 「再実行」を出さない案(6.7。FARC-P-37)。専用の文言は画面仕様に足す。HO-30 |

### 12.6 B・A への依存と引き継ぎ

**F 8.6 により、この節の「F への引き継ぎ」は全件割り当て済み**。F の I-104(D1 の EP-14)は**解消済み(作業記録 0017)**: E 5.4・5.7 から D1 の EP-14 を外した(画面仕様 dashboard の全文と admin-view 3章・10.4 で、D1 が EP-14 の項目を使わないことを確認)。B 1.3 の D1 の行の EP-14 も B 側で解消済み(0017)。

**B 本文に合わせて直した箇所**(B 本文の完成後に照合。2026-11-22):

1. 部分失敗: `unavailable` は最上位でキーは項目のパス(R1 後の追従で正式なパスにし、その後、一覧は行単位に変更した。12.6 の末尾)、理由コードは `store_unavailable`・`search_index_unavailable`・`timeout`・`malformed`(B 2.2。5.7・5.9・6.2。FARC-P-27)。
2. J2 の `stalled`・`rerunnable`・`latest_for_source` が `null` になりうる: 取消・再実行を出さない(1.2・5.7・6.7)。`deletion.fetched_at` を「取得時刻」に(5.7)。
3. 番兵の日時 `0001-01-01T00:00:00.000Z`(B 2.11・I-73): 「期限切れ」として扱う(5.9。FARC-P-24)。
4. EP-03・04 の入力: 型は厳密、`ttl_days` か `ttl_seconds` の一方、`ratio_threshold_percent` は小数第 2 位まで、EP-04 は `source_id`・`connector_type` を含めない(7.2・7.5)。
5. 項目エラーの `reason`: `required`・`type`・`format`・`range`・`exclusive`・`unknown_field`・`unsupported`・`config_invalid`(`read_only` は 502 になり画面に届かない)(6.4)。
6. EP-08 の `lock_in_use` の `lock_state` は `unknown` になりうる(6.3)。EP-13 の `reason` 6 値は診断用で、未知の値は一般的な文言(5.7)。EP-09 の `status` の複合値 `active`、未登録の `source_id` は空の結果(5.7)。
7. 保存系(EP-03・04)の `crawler_response_lost` は再送が安全(B 9.2.4・9.2.5)。解放の再送は `released=false` になりうる(B 9.2.3)(6.5)。
8. `/` を含む ID は 404 `not_found`(B 2.12): 「見つかりません」と同じ扱い(4.5・6.2)。
9. `web` のファイルがない場合のブラウザ側の扱い(B 10.2 が E に委ねた点。3.3)。
10. S4 の読めない設定項目(`malformed`。AAPI-U-10 が E・F に委ねた点)への回答(7.6。FARC-P-28)。
11. J1 の `sort`: B 5.1 が画面の「開始」列に対応と明記したため、I-86 を更新。

**B・A の追従(0020。2026-11-22)**: (1) ジョブ記録などの値が読めない `null`(`JobBrief` の `status`・`job_type`・`trigger`・`queued_at`、`registration` の件数・`partial`・`phase`)と取得失敗の表示の区別(5.9・5.7・6.7。FARC-P-36。I-120)。(2) `rerun_blocked_reason=source_missing`(AAPI-P-41)は「再実行」を出さない案、`rerunnable=null` の条件の増加(6.7。FARC-P-37。I-121)。(3) AAPI-P-25・P-27 の引用は、`null` を許す型と部分失敗の整理に合わせた。

**PR #10 のレビュー指摘への追従(0037・0038。2026-11-23)**: 一覧の EP(EP-01・09・11)の `unavailable` が行単位になった(AAPI-P-42)ため、5.7(S1・J1・X1)・5.9・6.2 を、行の `unavailable`(キーは相対パス)と最上位(行に属さない項目だけ)に分けて判定する形に直した。旧規則(一覧でキーがあり行が `null` なら取得できません)と `items[].…` 形式のキーは廃止した。FARC-P-39 を新設し、FARC-P-27・36 の区分を「承認済みの案(ゲート3)の修正」とした。

**R3 の指摘への対応(2026-11-22)**:

1. 区分: DS・画面仕様のゲート B・C の承認事項の引用は、A・B の基準に合わせて承認済みの案に統一した。FARC-K-5・K-7 を欠番にして FARC-P-32・P-33 へ移した(K-6 → P-31 と同じ)。K は FARC-K-1・3・4・9(K-8 は R4 の指摘で欠番にして FARC-P-38 へ)(K-9 は DS 前提 2〜4・6 の範囲に絞った)。
2. 5.4 の見出しと FARC-P-4・P-8 の区分欄を整理した。12.3 の冒頭に、ゲート3の対象である旨を足した(R3 時点の記録)。
3. `lock_held` の導線(`existing_job.status=null` は J2 でなく S2。6.3。FARC-P-35。I-88)、`featureFlag` の評価をナビ(`SideNav`・外部リンク領域)に一本化(4.2・4.5。I-89)、`config_invalid` のフォールバックは `crawler_message` をそのまま出す(6.3・6.4)、ロック状態の写像表(5.10。FARC-P-34)、マウント時の再取得の明記(5.4・5.5)、`viewState` を features の composable が作りテンプレートは props で受ける(4.4・6.2)。
4. 軽微: `timeout` を再試行しない(5.3・5.4)、保存系の `retryable` の例外(6.3)、D1 の補足を箇条書きに(5.7)、Node の範囲(2.1)、関連文書の表の F・C の状態(作成済みへ)、`vite preview` のポート(10.2)ほか。

**B・A の R1 修正への追従(2026-11-22)**:

1. `unavailable` のキーを正式なパスに(B 2.2・3.1・3.2・5.1)。一覧の扱いは、その後 AAPI-P-42 で行単位に変更した(12.6 の末尾。この時点の「一覧でキーがあり行が `null` なら取得できません」は廃止)。
2. `lock_state`: `orphan`(取得から 60 秒超)と `just_acquired`(60 秒以内)は排他、ジョブの `status`・`job_type` が読めなければ `unknown`(B 2.9。6.3)。
3. 本文が空なら Content-Type は問われない(`{}`)、本文があれば `application/json` 必須(B 2.12。7.5)。
4. `ttl` の下限 1(AAPI-P-37。案)、しきい値の小数第 3 位以下の保存値の注意と丸め(AAPI-P-38。案)(7.2・7.7。FARC-P-29)。
5. `config_invalid` の `field="connector_config"`(プレフィックスなし)は上部アラート(B 2.5。6.3・6.4)。
6. EP-13: トップ `checked_at` は全確認が終わった時刻(最終取得成功日時とは別)、`id` は compose のサービス名ではない(`web`。5.7)。EP-02: `lock.job.lease_expires_at` は読めなければ `null`、番兵は 409 の `existing_job` だけ(5.7・5.9)。
7. `job_id` は特殊文字を含みうるため、画面のルートの `:jobId` も URL エンコードする(B 2.12・AAPI-U-12。4.3。FARC-U-18)。
8. ID の区分: BAPI-K-6・AAPI-K-6 は欠番(BAPI-P-20・AAPI-P-35 へ)。E の FARC-K-7 から BAPI-K-6 を外し、画面のローカル時刻表示(DS 4.9。ゲート C)だけにした(その後、R3 の指摘で FARC-K-7 も欠番にして FARC-P-33 へ移した)。FARC-K-6 の出典を B の AAPI-K-9 に合わせた(その後 R1 再確認で B が AAPI-K-9 を欠番にしたため、FARC-K-6 も欠番にして FARC-P-31 へ移した。下の再追従)。**FARC-K-2 は欠番にし、FARC-P-30(承認済みの案(ゲート1))に移した**(BAPI-K-3 の整理と同じ理由)。
9. 参照している B の新規 ID: AAPI-P-35〜38、AAPI-U-12、I-75(AF-5 の読み替え。E の 5.8 の再実行の流れと一致)。

**B・A の R1 再確認(N-1〜N-5)への追従(2026-11-22)**:

1. AAPI-K-9 の欠番(→ AAPI-P-40。承認済みの案(画面仕様ゲート B・C の引用。ユーザー確認済み(ゲート3。2026-11-23)))に合わせ、FARC-K-6 を欠番にして FARC-P-31 に移した(A の凡例: 既承認文書の承認済みの案の引用は確定にせず、出典を区分欄に書く)。(この時点で K のまま残した FARC-K-5・K-7 は、後の R3 の指摘で FARC-P-32・P-33 へ移した。現在の K は FARC-K-1・3・4・9(K-8 は R4 の指摘で欠番にして FARC-P-38 へ)。)
2. EP-07 の取消で、`job_id` を理由とする Crawler の 400 `invalid_request`・404 `not_found` は 404 `job_not_found` に写る(AAPI-P-39。案。6.2・6.3)。画面の表示は既存の 404 の扱いのまま。
3. EP-11 の `existence` の `unavailable` は、その後、行単位(各行の `unavailable`)に変更した(AAPI-P-30・42。12.6 の末尾)。
4. N-1(ブラウザの単純なリクエストで届くのは本文なし POST の EP-05・06・07。EP-04・08 は preflight 対象。B 2.10・A 2.3): E に Origin 検査・書き込みの保護の記述はないため、追記しない。E は同一オリジン・CORS 不要(FARC-K-4)のみを述べ、CORS を許可する設定を持たない。
5. AAPI-P-7 の注記(`ttl` 下限を除く。P-37)、BAPI-P-20(承認済みの案(引用)。ゲート3)、BAPI-P-21(導出)と E の記述(7.2・FARC-P-33)に食い違いはない。

**なお B・C の確定に依存する箇所**(FARC-U-12): B の案(AAPI-P-16〜18・24〜34・37〜39・41。ゲート3で承認済み)が変わったとき。`lock_state` 7 値(B 2.9。案)の `just_acquired`・`unknown` の画面での扱い(6.3 は error 扱い)。失敗理由・警告・削除結果のコード(B 5.2。AAPI-U-3)と未知のコードの扱い。`connector_config` の既定値の補完の境界(AAPI-P-20)。OpenAPI の `operationId`(生成される `xxxOptions` の名前に直結。5.2)。C の導出ロジック(B 11.10)で `stalled` などの意味が変わらないこと。

**F への引き継ぎ**: (1) `apps/web/` のディレクトリ構成(生成コード・API ラッパー・key factory と composable・エラー変換表・Router と `meta`・テンプレート 4 型・DS の共通部品・画面ごとのモジュール・テスト・`mockApi` とフィクスチャ)。(2) 5.7 の画面別の表を、画面 → route → ページ → composable → EP の対応表に展開する。(3) DS 4章の全部品(`StatusTag`・`KeyValueList`・確認ダイアログ・`FilterBar`・`CountTabs`・`ShardMatrix`・`SummaryBand`・`ComponentTile`・`AutoRefreshSwitch`・`PatternListInput`・`SettingSwitch`・`FormDisclosure`・`StatList`・`WarningList`)の置き場。(4) 依存ルール(11.1)。(5) 定義表(`navGroups`・`documentTabs`・`dashboardComponents`・URL ↔ API の対応・エラー変換表・画面の入力 → `field` の対応)の置き場。(6) トークン・`defaults` を Search View と共有できる置き場(1.3)。

A への依存: A 2.2(フォールバック・URL)、5.2(エラー形式)、5.4(OpenAPI・サブアプリ)、5.6(タイムアウト)、8(compose・ビルド。I-82)。
