# api 共通基本設計 v0.1

- 版: v0.1(ドラフト。ゲート3(2026-11-23)の承認を反映済み。API 基盤(`apps/api`)は実装済み(PR #16)で、設計書は HO-51 により実装に追従した。Admin API は未実装で、実装時確認事項が残る)
- 更新日: 2026-11-23
- 前版: なし(初版)
- 位置づけ: `api` コンテナ(Admin API・将来の Search API・MCP Server が同居する)の**共通の土台**を定める。コンテナ・プロセス構成、URL の名前空間、技術スタック、設定(環境変数)の命名、共通の HTTP 規約(**エラー応答の統一形式と共通 code**、時刻、OpenAPI の方針)、ヘルスチェックの位置づけ、構成の共通方針、compose への要求を書く。Admin API のエンドポイント・DTO・Admin 固有のエラー code・Crawler への写像は `admin/admin-api-v0.1.md`(以下 B)が正本。Search API・MCP Server の設計は本書の対象外(境界だけを書く)。
- 本書は **Admin 画面の詳細設計タスク(`20261122_create_admin_system_design`)の成果物**で、SD・PD・crawler / indexer 設計を変更しない。既存設計と食い違う点・追従改訂が要る点は 9章(申し送り一覧 HO-1〜HO-51。ゲート3の確認事項と回答 G3-1〜G3-23)に集約し、本書の他の章は該当する HO 番号で参照する。
- 改訂履歴: v0.1 は初版。フェーズ1(A→B 骨子)で作成した。ゲート1(2026-11-22。ユーザー承認)で承認された方針は「承認済みの案」とした(確定にしていない)。具体値・名前はゲート2(2026-11-22。B 11.7)で承認された(確定にはしていない)。再実行の専用エンドポイントと書き込み系の `Origin` 検査の2件は、ゲート2の回答で採用が選ばれなかったため、**不採用として扱った(当初は解釈。ゲート3(2026-11-23)で「不採用のままでよい」と明示回答を得た)**。`Origin` 検査を採用しなかったことに伴い、2.3 に未対応のリスクを明記し、BAPI-U-8 に登録した。R1(document-reviewer)の指摘を反映した(`-K-` の出典と区分の見直し、`job_id` のエンコード、`Content-Type` の扱いほか)。フェーズ5の統合(2026-11-23)で、9章に申し送り(HO-1〜HO-50)とゲート3の確認事項(G3-1〜G3-23)を集約し、本文中の申し送りへの参照を実番号に置き換えた。6 文書の参照・ID・表の整合を機械チェックし、更新日を統一した。R4 指摘の反映(2026-11-23): 9.3 の G3-23 を C・D の案の ID の列挙に拡張(G3-3 に FARC-P-38、G3-22 に AAM-P-28)、9.1 に状態の付け方と「タスク内の引き継ぎは申し送りでない」、2.3 に PD §2 の引用、4 の `WEB_DIST_DIR` の既定を `/app/web` に、5.6 のプローブの時間、3・7 の `anyio`、10.3 の BAPI-P の並び、HO-5 の注記、レビュー記号の削除。ゲート3の承認(2026-11-23)の反映: 9.3 に回答の列を足して G3-1〜G3-23 の承認を記録し(G3-1=不採用のまま、G3-2=リスクは受け入れ・README に注意書き、G3-13=画面設計に任せる)、案の区分を承認済みの案(ゲート3。2026-11-23)に、HO の状態「ゲート3待ち」を「未対応」に、BAPI-P-15・BAPI-U-8・2.3 の記述をゲート3の明示回答に更新した(設計の内容は変更なし。リスクは受け入れた未対応のリスクとして残る)。API 基盤の実装タスク(`20261123_implement_api_base`。2026-11-23)で、9章に HO-51(D の追従改訂の前提条件。実装が D と異なる点と実装上の注意)を追記した(設計の本文は変更していない)。HO-51 に対応する追従改訂(`20261123_update_api_design_after_base_impl`。2026-11-23): 7章の層に `server` と `health` を加え、5.4 に OpenAPI の生成元・422・`openapi_url` の明示を、5.5 に 500 変換の保証の範囲を足した(詳細は D 4.12)。10.1 と 10.4 の BAPI-U-2 を、サブアプリへの `FastAPI(root_path=…)`・入れ子のマウント・OpenAPI の `servers`・`paths` に絞り(外側アプリの `root_path`・例外ハンドラ・アクセスログの適用範囲は D の AAM-K-5 で確定)、HO-48 の AAM-U-2 を確定にし、HO-51 を対応済みにした(AAM-P-23 の分担の変更はユーザー確認済み。2026-11-23)。

## 0. この文書について

- 対象: `api` コンテナの共通事項(Admin API・Search API・MCP が同じく従う規約)。
- 範囲外: Admin API の個別仕様(B)、導出ロジック・死活判定・データアクセスの詳細・環境変数の個別一覧(C)、モジュール構成(D)、フロントエンド(E・F)、Search API・MCP の設計。
- 読み方: 1〜2章で範囲と構成、3〜4章で技術スタックと設定、5章で共通の HTTP 規約(エラー形式はここが正本)、6〜8章でヘルスチェック・構成方針・compose への要求、9章に申し送り一覧とゲート3の確認事項・回答、10章に確認状況(ID 付きの判断一覧)を置く。

区分の凡例(`crawler-api-v0.4.md` に合わせる):

| 区分 | 意味 |
| --- | --- |
| 確定 | ユーザーが明示的に回答・確定した事項(出典を書く)、または既承認文書(PD・SD・機能設計・DS・crawler / indexer 設計)の引用 |
| 案 | ユーザーが承認していない提案。確定(`-K-`)にしない。本書の案は、ゲート3(2026-11-23)ですべて承認され、承認済みの案(ゲート3)になった(本文中で「案」と書いた判断は、ID の区分欄が正で、承認済みの案に読み替える) |
| 承認済みの案 | ゲート1(2026-11-22。ユーザー承認)で**方針**、ゲート2(2026-11-22。ユーザー承認)で**具体値・名前**、またはゲート3(2026-11-23。ユーザー承認)で本タスクの案・導出・解釈の扱いが承認されたもの。設計として承認済みだが確定ではない。**既承認文書(画面仕様・CA-P など)の「承認済みの案」を引用したものも、確定にせずこの区分とし、出典を区分欄に書く**。区分欄に承認したゲートを書く。ID は `-P-` のまま。ゲート2の回答で採用が選ばれなかった案は「不採用として扱った(解釈)」とし、ID は欠番として残す(ゲート3(2026-11-23)で不採用のままでよいと確認済み) |
| 未決 | 決めていない |
| 推測 | 根拠が弱い想定 |
| 導出 | 他の記述から導いた事項 |

ID 体系: 確定・案(承認済みの案を含む)・未決は `BAPI-K-n` / `BAPI-P-n` / `BAPI-U-n`。既存設計との不整合は `I-n`(本書の予約範囲は I-60〜69。既存設計は I-1〜52 を使用)。申し送りは `HO-1`〜`HO-51`(9章が唯一の置き場)、ゲート3の確認事項と回答は `G3-1`〜`G3-23`(9.3)。B の ID は `AAPI-*`。他文書の ID は `CAPI-*`(crawler-api)、`CA-*`(crawler-architecture)、`IA K n`(indexer-architecture)、`AF-*`(機能設計)のように引用する。

関連文書(いずれも `docs/v0.x/` 配下):

| 略称 | 文書 | 本書との関係 |
| --- | --- | --- |
| B | `system-design/api/admin/admin-api-v0.1.md`(v0.1。作成済み) | Admin API の仕様。エンドポイント・DTO・Admin 固有 code・Crawler 写像の正本 |
| C・D | `system-design/api/admin/admin-api-architecture-v0.1.md`、`admin-api-module-structure-v0.1.md`(いずれも v0.1。作成済み) | 導出ロジック・環境変数の個別一覧(C)、モジュール構成(D) |
| E・F | `system-design/ui-admin/frontend/ui-admin-frontend-architecture-v0.1.md`、`ui-admin-frontend-module-structure-v0.1.md`(いずれも v0.1。作成済み) | Web UI の構成。型生成・配信の詳細は E |
| 機能設計 | `system-design/ui-admin/ui-admin-functions-v0.1.md` | AF-1〜20 |
| 画面仕様 | `ui-design/admin-view-v0.1.md`、`admin/*.md`、`design-system-v0.1.md` | 10.4(Admin API への申し送り)、各画面のデータ項目 |
| crawler-api | `system-design/crawler/crawler-api-v0.4.md` | Admin API が呼ぶ Crawler の 6 API と `/healthz`(契約外) |
| indexer-api | `system-design/indexer/indexer-api-v0.10.md` | Indexer の `/healthz`(契約外) |
| SD | `system-design/system-design-v0.8.md`(補助) | §6.3・§7.2・§7.3・§14 |
| PD | `product-design/product-design-v0.19.md` | §6.1(アクセス制御と運用前提) |

---

## 1. 位置づけと範囲

- `api` は、検索・管理操作の窓口となるコンテナで、将来は Search API・MCP Server・Admin API を同じプロセスで動かす(SD §7.2)。本タスクの範囲は **Admin API と Web UI の静的配信**だけで、Search API・MCP は設計しない。Search API・MCP を足すときに、本書の規約(URL の名前空間、エラー形式、設定の命名、依存ルール)をそのまま使えるようにすることが、本書を別文書にした目的(導出)。
- Admin API は、`crawler` への操作(6 API の中継)と、OpenSearch(Store 層・検索インデックス・クラスタ情報)・`crawler`・`indexer` の**読み取り**だけを行い、**Store 層・検索インデックスには何も書かない**(BAPI-K-8。メンテナンスフラグも書かない)。
- MVP の前提は、単一ホスト・単一 Crawler・単一 Indexer・直列実行・認証なし(PD §6.1。CAPI-K-7)。

## 2. コンテナ・プロセス構成

### 2.1 構成

```text
ブラウザ ─HTTP─▶ api(1 コンテナ・1 プロセス。uvicorn 単一プロセス)
                   ├ /admin/…            Web UI(Vite のビルド成果物を静的配信。同一オリジン。CORS 不要)
                   ├ /api/admin/v1/…     Admin API(admin パッケージ。B)
                   ├ /healthz            api 自身のヘルスチェック(契約外。6章)
                   └ (将来)Search API・MCP(本書の対象外)
api ─読み取りのみ(opensearch-py。同期)─▶ opensearch
        loreley-sources / loreley-jobs / loreley-deletions、検索インデックス、クラスタ情報
api ─HTTP(操作 6 API。冪等でないものは自動再送しない)─▶ crawler
api ─GET /healthz(2xx かどうかだけを見る)─▶ crawler・indexer(任意コンポーネントは設定時のみ)
```

- Admin API は `api` コンテナ内の **admin パッケージ**(BAPI-K-1。ユーザー確定 2026-11-22。0001 Q2)。`web` は独立コンテナではなく、`api` が静的ファイルを配信する(同一オリジンで CORS は要らない。BAPI-K-2。同)。SD §7.2 の `web`(「API と同居してもよい」)の同居形態の確定にあたる。
- 単一プロセス(uvicorn のワーカー 1)。状態をプロセス内に持たない(D1 の「最終取得成功日時」はクライアントが持つ。AAPI-P-8)ため、将来ワーカーを増やしても動作は変わらない(導出)。同期関数(`def`)のエンドポイントは共通のスレッドプール(既定 40)で動き、Crawler への呼び出しが長いと枯渇して他の EP も止まりうるため、**ハンドラは `async def` とし、ブロッキングの処理を区分ごとの上限つきでスレッドに渡す**(C 8.1 の承認済みの案(ゲート3)。AAA-P-33。`api` 自身の `/healthz` はスレッドを使わない。BAPI-U-6)。

### 2.2 URL の名前空間

| パス | 内容 | 備考 |
| --- | --- | --- |
| `/api/admin/v1/…` | Admin API | 承認済みの案(BAPI-P-1。ゲート1)。`v1` は互換を壊す変更のときに上げる(導出) |
| `/admin/…` | Admin View(Web UI) | 承認済みの案(BAPI-P-2。ゲート1)。history モード。**`/admin/` 配下の未知のパスだけ `index.html` を返す**(SPA フォールバック)。`/api/` 配下と、`/admin/` 配下でも静的ファイルの欠落(JS・CSS など)は返さない |
| `/healthz` | `api` 自身のヘルスチェック | 契約外(6章) |
| `/api/` のその他 | 将来の Search API など | 本書では決めない。未知のパスは JSON の 404(5.2) |
| 上記以外 | JSON の 404 | `/`(ルート)と Search View の配置は未決(BAPI-U-4) |

- フォールバックの範囲を `/admin/` 配下に限るのは、ゲート1の「`/api/` 以外の未知パスは `index.html` へ」を、Admin View の配置(`/admin/` 配下)に合わせて読んだため(解釈。ゲート2で承認 2026-11-22。B 11.7)。Search View の配置は Search View の設計時に決める(BAPI-U-4)。
- 実装は、FastAPI の `app.frontend()`(0.138.0 で追加)を第一候補とする(承認済みの案(ゲート3)。BAPI-P-2。出典: 0004 の tech-advisor 報告)。`/admin` へのマウントの細部(末尾スラッシュなしの `/admin`、`/admin/` 配下で存在しないアセットの 404、`/api/` との優先)は実装時に確認する(BAPI-U-1)。パス操作(`/api/…`、`/healthz`)がフォールバックに優先する(0004 で確認済み)。

### 2.3 公開範囲と認証なし(安全性。BAPI-K-4)

- **認証がない**(MVP。PD §6.1。CAPI-K-7)。到達できる人は、`api` を通して次の**破壊的・影響の大きい操作**を実行できる: 強制削除モードでのクロール起動(`force_delete`)、データソース削除ジョブの起動(そのソースの全文書・記録・設定が消える。取り消せない)、ロック解放、クロールの取消、データソース設定の登録・更新。Admin API 自体には確認や二重送信の防止がなく、誤操作の防止は Admin View の確認ダイアログ(画面仕様の危険度の段階)に委ねる(crawler-api 4.6 と同じ前提)。
- **`connector_config` の `root` に、Crawler のコンテナから見える任意のパスを指定できる**(PD §6.1「任意のローカルパスを登録できる」)。Admin API はこの値を検証せず Crawler に中継する(検証は Connector。B)。読めるパスは、Crawler にだけ `:ro` でマウントしたディレクトリに限られる(SD §6.4。compose の定義)。
- **既定の公開範囲は localhost のみ**(PD §6.1「既定では localhost だけで待ち受ける。社内ネットワークへ公開するには、バインド先を設定で明示的に変更する」。SD §6.3)。`api` のホストへの publish は 127.0.0.1 に限る(8章。BAPI-P-14)。社内ネットワークへ公開すると、到達できる全員に上の操作が開かれる。これは README と導入手順で明示する(HO-40。9章)。
- **エラー応答・ログに、入力値・認証情報・原本のパスを出さない**(5.2、5.5)。
- OpenAPI の定義も同じ公開範囲に載るため、**実行時の公開は既定で無効**にする(5.4)。
- Search API・MCP が将来この `api` に同居したときに、Admin API の破壊的操作が Search API と同じ公開範囲になる問題は、本タスクでは決めない(BAPI-U-3。認証の追加が前提)。
- **受け入れた未対応のリスク(BAPI-U-8。ゲート3(2026-11-23)で受け入れを確認済み。リスクは残る)**: 認証なしで localhost に公開される `api` には、**悪意あるウェブページが、ユーザーのブラウザを経由して書き込み要求を送る攻撃**(本文のない POST、DNS rebinding など。導出)への保護がない。
  - ブラウザの単純なリクエスト(CORS 上の単純なリクエストは GET・HEAD・POST だけ)で届くのは、`Content-Type` を要しない本文なしの POST の **EP-05(ソース削除ジョブ。そのソースの全文書の削除)、EP-06(`force_delete` は既定 `false` で、`true` にするには JSON の本文が要る)、EP-07(取消)**。EP-03(POST)・EP-04(PUT)は本文に `Content-Type: application/json` を要するため単純なリクエストでは書き込めない(B 2.12)。EP-04(PUT)・EP-08(DELETE。ロック解放)は、クロスサイトでは preflight が要り、CORS を許可していないため届かない。**EP-08 は DNS rebinding でのみ到達しうる。DNS rebinding なら、全 EP(読み取りを含む)が対象**になる。
  - SD §6.1・§6.2 が MCP に定める `Origin` 検査に倣う案を検討したが、**ゲート2の回答で採用が選ばれなかったため、不採用として扱った**(当初は解釈で、ゲート2の時点ではユーザーがリスクを受け入れたわけではなかった。ゲート3(2026-11-23)で「不採用のままでよい」と明示回答を得た)。全 POST での `Content-Type` 必須化などの軽い緩和は、要件にない追加のため足していない。
  - 判断材料(PD v0.19 §2 のリスク表): 「Admin View を保護しない」を許容する制約として載せ、信頼できる利用者だけの検証環境向けで認証は将来の版とする。一方、MCP の DNS rebinding(悪意あるウェブページからの呼び出し)には Origin 検証を MVP に含める(§6.1)。Admin API の同種のリスクに `Origin` 検査を含めていない点が、MCP との差になる。
  - **ゲート3(2026-11-23)で、リスクは受け入れ、README に注意書きを置く(HO-41)、軽い緩和は足さない、と明示回答があった**。リスクがなくなったわけではなく、受け入れた未対応のリスクとして残る。MVP の運用前提(信頼できる利用者だけの検証環境。PD §6.1)は変わらない。将来の認証の導入時に、保護を再検討する(BAPI-U-3 と合わせる)。

## 3. 技術スタック

API の技術スタックは Indexer・Crawler に揃える(`apps/crawler/pyproject.toml`・`apps/indexer/pyproject.toml` で確認)。

| 項目 | 採用 | 区分 |
| --- | --- | --- |
| 言語 | Python 3.12(`>=3.12,<3.13`) | 導出(BAPI-P-21。出典: `apps/crawler/pyproject.toml`・`apps/indexer/pyproject.toml`)。「Indexer・Crawler と揃える」ことは確定(BAPI-K-3) |
| Web フレームワーク・サーバー | FastAPI、uvicorn(単一プロセス) | 導出(BAPI-P-21)。「単一プロセス」は Crawler・Indexer も単一プロセスであることによる導出 |
| モデル・設定 | pydantic(`>=2.9,<3`)、pydantic-settings(`>=2.6,<3`) | 導出(BAPI-P-21) |
| OpenSearch クライアント | opensearch-py(`>=3.2,<4`。同期。3.2.0 で確認済み。0004) | 導出(BAPI-P-21) |
| Crawler への HTTP | urllib3(`>=2.2,<3`)。`DELETE`・各 API のタイムアウトを扱え、opensearch-py が依存済みで追加の依存が増えないため(CM-P-29 に倣う) | 承認済みの案(ゲート3。2026-11-23。BAPI-P-7) |
| fastapi の下限 | `>=0.143.2`(`app.frontend()`(0.138.0〜)とその修正を含むため。0004) | 承認済みの案(ゲート3。2026-11-23。BAPI-P-8) |
| パッケージ管理・テスト・静的解析 | uv(`uv.lock`)、hatchling、pytest、ruff。既存の `apps/crawler`・`apps/indexer` と同じ | 承認済みの案(ゲート3。2026-11-23。BAPI-P-11) |
| 環境変数の接頭辞 | `LORELEY_API_`(Crawler の `LORELEY_CRAWLER_`、Indexer の `LORELEY_INDEXER_` に倣う) | 承認済みの案(ゲート3。2026-11-23。BAPI-P-6) |
| 実装ディレクトリ・パッケージ | `apps/api/`(パッケージ `loreley_api`)、`apps/web/`(Web UI) | 承認済みの案(ゲート3。2026-11-23。BAPI-P-11。作業プラン P-1) |

- **Web UI の技術スタック**(Vue 3、Vuetify 4.3.4 など)は E が正本。本書は、`api` がビルド成果物を静的に配信することだけを定める。
- **外部ライブラリを import してよい場所**(7章。機械検査。D): `urllib3` は `infrastructure` の Crawler クライアントと、**HTTP のヘルスプローブ**(Crawler・Indexer・任意コンポーネントの `/healthz`)だけ。`opensearchpy` は OpenSearch アクセス(**`cluster.health` のプローブを含む**。これは opensearchpy で行い、urllib3 の HTTP プローブとは別)だけ。`anyio`(スレッドへの受け渡し)は `common` の並行の部品(`concurrency.py`)だけ(D R5)。**例外として、OpenSearch の例外の分類(接続のタイムアウトと接続拒否の区別など)に `urllib3.exceptions` の型が要るため、`urllib3.exceptions` の import を `infrastructure.opensearch`(`failure.py`・`health_probe.py`)に限って許す**(承認済みの案(ゲート3。2026-11-23)。BAPI-P-22。C・D の案(AAM-P-12)と同じ)。

## 4. 設定

- 設定は環境変数で与える。`pydantic-settings` の `BaseSettings`(`env_prefix="LORELEY_API_"`)で読み、フィールド名の大文字が環境変数名になる(例 `LORELEY_API_OPENSEARCH_URL`)。命名は Crawler・Indexer と同じ規則(承認済みの案(ゲート3)。BAPI-P-6)。
- **`CRAWLER_URL`・`INDEXER_URL` は MVP では `http` 限定**(内部ネットワーク前提。TLS の検証設定は持たない。承認済みの案(ゲート3。2026-11-23)。BAPI-P-24。C・D の案と同じ)。
- 必須の設定が欠けている、または値が不正(URL として解釈できない、IANA 名でないタイムゾーンなど)のときは、**起動時に失敗**する(fail fast。ログに出すのは環境変数名・項目名だけで、値は出さない)。
- 秘密情報は、**OpenSearch の接続情報だけ**を任意で持つ(`OPENSEARCH_USERNAME`・`OPENSEARCH_PASSWORD`・`OPENSEARCH_VERIFY_CERTS`・`OPENSEARCH_CA_CERTS_PATH`。セキュリティを有効にした OpenSearch に接続するとき。Crawler・Indexer と同じ。C 7.2 の承認済みの案(ゲート3)。AAA-P-30)。パスワードはログ・エラー本文に出さない。認証なしの `api` 自身には認証情報がなく、PD §4.8 に従い Connector の認証情報は `api` が扱わない。
- `api` が共通で持つ設定(承認済みの案(ゲート3)。BAPI-P-6。Admin API 固有の設定の名前は B 11.7(ゲート2)、個別の一覧・既定・検証は C 7.2 が正本):

| 環境変数(`LORELEY_API_` を除く) | 意味 | 既定 |
| --- | --- | --- |
| `OPENSEARCH_URL` | OpenSearch の接続先(必須) | なし |
| `OPENSEARCH_USERNAME`・`OPENSEARCH_PASSWORD`・`OPENSEARCH_VERIFY_CERTS`・`OPENSEARCH_CA_CERTS_PATH` | OpenSearch の認証・TLS(任意。C の案 AAA-P-30) | なし(`VERIFY_CERTS` は `true`) |
| `SOURCES_INDEX_NAME`・`JOBS_INDEX_NAME`・`DELETIONS_INDEX_NAME`・`SEARCH_INDEX_NAME` | 索引名(`SEARCH_INDEX_NAME` は検索インデックスの**エイリアス**で、`opensearch-init` の実体名の変数とは別。C の案 AAA-P-30) | `loreley-sources`・`loreley-jobs`・`loreley-deletions`・`loreley-documents` |
| `ADMITTING_LOCK_GRACE_SECONDS` | `just_acquired` の猶予(秒)。Crawler の `LORELEY_CRAWLER_ADMITTING_LOCK_GRACE_SECONDS` と同じ値(C の案 AAA-P-24) | `60` |
| `HOST` / `PORT` | 待ち受けのアドレス・ポート | `127.0.0.1`(コンテナでは `0.0.0.0`)/ `8080` |
| `LOG_LEVEL` | ログの水準 | `INFO` |
| `OPENAPI_ENABLED` | OpenAPI JSON の実行時公開(5.4) | `false` |
| `WEB_DIST_DIR` | Web UI のビルド成果物の置き場(2.2) | 既定 `/app/web`(C 7.2。AAA-P-43。イメージ内の固定パス。G3-16 で確認) |

- 索引名の**渡し方**(8章。作業記録 0027 の指摘): `sources`・`jobs` の索引名は Crawler と同じ変数から、`deletions` は Indexer と同じ変数から、**検索インデックスのエイリアス**は `opensearch-init` の `SEARCH_INDEX_ALIAS` と Indexer の `LORELEY_INDEXER_SEARCH_INDEX_NAME`(エイリアス)と同じ値にする。**`opensearch-init` の `SEARCH_INDEX_NAME` は実体名(既定 `loreley-documents-000001`)で別物**であり、`api` の `SEARCH_INDEX_NAME`(エイリアス)に渡してはならない(再インデックスの後に古い索引を読むため)。既定は `infra/opensearch/init-indices.sh` の既定(`loreley-sources`、`loreley-jobs`、`loreley-deletions`、検索エイリアス `loreley-documents`)に合わせる(確認済み)。

## 5. 共通 HTTP 規約

### 5.1 基本

- リクエスト・レスポンスは UTF-8 の JSON(`Content-Type: application/json`)。項目名は `snake_case`。項目は省略せず、値がないときは `null` を返す(承認済みの案(ゲート3)。BAPI-P-16)。
- **時刻は UTC の ISO 8601・ミリ秒精度**(例 `2026-11-22T01:02:03.456Z`)。リクエストに時刻はない。画面がブラウザのローカル時刻に変換する(DS 4.9)。承認済みの案(BAPI-P-20。既承認文書の引用: CA-P-38(承認済みの案)・admin-view 10.4。ユーザー確認済み(ゲート3。2026-11-23))。
- 末尾スラッシュ付きのパスはリダイレクトせず 404 にする(`redirect_slashes` を無効にする。案。Crawler の 307 の挙動に合わせない)。
- API の応答に `Cache-Control: no-store` を付ける(状態は常に最新を返す。案)。**対象は API の応答(`/api/…`)だけで、静的アセット(`/admin/…`)には付けない**(ハッシュ付きのアセットはキャッシュしてよい)。
- リクエスト本文の上限は 1 MiB(仮値。超過は 400 `invalid_request`・`details` なし。案。Crawler の 10 MiB より小さい。Admin API の本文は設定 1 件分だけのため。導出)。
- JSON は厳密に扱う(型の変換をしない。未知の項目は 400)。Crawler の CAPI-P-14 と同じ方針(承認済みの案(ゲート3)。BAPI-P-16)。

### 5.2 エラー応答の統一形式と共通 code(正本。承認済みの案。BAPI-P-5)

形式は Crawler・Indexer と同じ(crawler-api 3.3 に合わせ、`details` を持つ)。

```json
{
  "error": {
    "code": "invalid_request",
    "message": "the request is invalid",
    "retryable": false,
    "details": { "errors": [ { "field": "ttl_days", "reason": "range" } ] }
  }
}
```

- `code`: 小文字の `snake_case`。画面の文言は `code`(と `details`)から E が決める。`message` は**固定の英語文(診断用)**で、入力値・パス・認証情報・例外メッセージを含めない。
- `retryable`: 同じ要求の再試行で成功しうるとき `true`(503 の `unavailable` など)。操作の結果が不明な場合は `false` で、`details.outcome_unknown=true` を付ける(B 2.3)。
- `details`: 任意。入力の違反は `errors`(`field`・`reason` の配列。必要なら `detail`)。項目名は `connector_config.include_patterns[2]` のようにドット区切り・添字つきで書く。**値は載せない**。未知の項目名は、孤立サロゲートの置換・制御文字のエスケープ・100 文字への切り詰めをして載せる(CAPI-P-22 と同じ)。
- 部分失敗を表す応答の項目 `unavailable`(取得できなかった項目と理由)は、下の 503 の code `unavailable` とは別のもので、**形とキーの規則は B 2.2 が正本**(本書は定めない。一覧の EP は各行に持ち、単一の応答は最上位に持つ。B AAPI-P-42)。
- 共通 code(Admin API 固有の code は B 2.3 が正本。名前は承認済みの案(ゲート2。2026-11-22)):

| HTTP | `code` | `retryable` | 意味 |
| --- | --- | --- | --- |
| 400 | `invalid_request` | false | 形式・型・範囲の違反、JSON として読めない本文、本文が上限超過。`details.errors` に項目と理由 |
| 404 | `not_found` | false | 未定義のパス(リソースの不在は、各 API の固有 code) |
| 405 | `method_not_allowed` | false | 未定義のメソッド |
| 上記以外の 4xx・5xx | `http_error` | false | 上記以外の HTTP 例外(HTTP ステータスはそのまま) |
| 500 | `internal_error` | false | 想定外の異常。`message` は固定文。例外の内容はログにも出さない(5.5) |
| 503 | `unavailable` | true | OpenSearch の読み取りが、再試行しても失敗した |

- `details.errors[].reason` の共通の値(案。Crawler の `reason`(crawler-api 3.3)に `range`・`exclusive` を加え、Admin API が使わない `read_only` を除いた。B は Admin 固有の値(`config_invalid`)を追加できる): `required`(必須の項目がない)、`type`(型が違う)、`format`(形式の違反)、`range`(範囲外)、`exclusive`(同時に指定できない項目を併記した)、`unknown_field`(定義にない項目)、`unsupported`(対応していない値)。
- 想定外の例外は 500 `internal_error` にして握りつぶさず、ログにはクラス名・送出元の位置だけを出す(5.5)。FastAPI の標準の検証エラー(422)・`HTTPException` の本文は使わず、すべて上の形式に変換する(案)。

### 5.3 検証の方針

- 入力は FastAPI(pydantic)のモデルで検証する。**Admin API が検証するのは、Admin API 自身の責務の範囲だけ**とし、Crawler・Connector が持つ検証規則(`connector_config` の中身、`schedule_cron` の書式)は複製しない(BAPI-P-16。AAPI-K-5)。
- パスの ID は、`source_id`(半角英数字で始まり、半角英数字・`.`・`_`・`-` だけ、256 バイト以内。CAPI-K-6・CAPI-P-15)と `job_id`(空でない、256 バイト以内、制御文字なし。CAPI-P-18)を、Crawler に渡す前に検証する(同じ規則で 400 `invalid_request`)。`job_id` は `%`・`?`・`#`・`.` などの記号を含みうるため、**Crawler の URL に埋めるときは `quote(value, safe="")` の後に `.` を `%2E` に置換する**(`.`・`..` は urllib3 のドットセグメント除去で崩れるため。`source_id` の文字種は符号化で変わらない。B 2.12・9.1。承認済みの案(ゲート3。2026-11-23)。作業記録 0010・0027 の指摘)。
- 検証の順序は、パス → クエリ → 本文の形式 → 範囲 → Crawler・OpenSearch の呼び出し(案)。

### 5.4 OpenAPI・型生成・Admin API の構成

- **OpenAPI は内部向けに用意し、フロントエンドの型生成に使う**(承認済みの案。BAPI-P-3。ゲート1)。実行時の公開は環境変数で制御し、認証なしの `api` に公開範囲を広げないため、**既定は無効**とする(承認済みの案(ゲート2。2026-11-22)。BAPI-P-4。tech-advisor の推奨。0004)。
  - パス: `/api/admin/v1/openapi.json`(承認済みの案(ゲート2))。有効化は `LORELEY_API_OPENAPI_ENABLED=true`(承認済みの案(ゲート2))。
  - 対話型のドキュメント(Swagger UI・ReDoc)は**常に無効**にする(`docs_url`・`redoc_url` を `None`)。標準の UI が外部の CDN から JS を読み、外部通信を必須としない方針(SD §7。PD)に反するため(承認済みの案(ゲート2。2026-11-22)。導出)。
  - **型生成は実行時の公開に依存しない**: `app.openapi()` で OpenAPI の JSON をファイルに書き出して入力にする(サーバー起動不要・CI で再現可。承認済みの案(ゲート3)。BAPI-P-10)。
- **型生成ツールは Hey API(`@hey-api/openapi-ts`。exact pin)を推奨**する(承認済みの案(ゲート2。2026-11-22)。BAPI-P-10)。理由: TanStack Vue Query 向けの `queryOptions` / `mutationOptions` を公式プラグインで生成でき、TypeScript 6 に対応する。0.x のため、更新のたびに移行を確認する。詳細(生成コードのコミット方針、`throwOnError` と stale 表示の接続)は E が正本(BAPI-U-5)。代替の `openapi-typescript` は TypeScript 6 の対応が未整備、`openapi-react-query` は React 専用で採らない(出典: 0004)。
- **Admin API の構成は、サブアプリのマウントを推奨**する(承認済みの案(ゲート2。2026-11-22)。BAPI-P-9): Admin API を独立した `FastAPI` アプリとして `/api/admin/v1` にマウントする。理由: (1) Admin 専用の OpenAPI を独立に出せ、型生成の入力が Search API・MCP の追加で混ざらない、(2) 例外ハンドラ・ミドルウェアを Admin API ごとに持てる、(3) Search API・MCP を別のマウントとして足せる。代替は、1 つの `FastAPI` アプリに `APIRouter` を足す方式(単純だが OpenAPI が 1 つに混ざる)。外側アプリの `root_path`(プロキシ配下)・例外ハンドラ・アクセスログの適用範囲は基盤の実装で確定した(D の AAM-K-5)。サブアプリへの `FastAPI(root_path=…)`・入れ子のマウント・OpenAPI の `servers`・`paths` は未検証で、admin 実装時に確認する(BAPI-U-2)。サブアプリの OpenAPI は `create_admin_app(...).openapi()` で生成する(外側の `app.openapi()` には集約されない)。FastAPI は検証のある操作に 422 の応答を既定で足すが、基盤は検証エラーを 400 `invalid_request` に変えるため、422 の宣言を除いて 400 の共通エラースキーマを宣言する。サブアプリを素の `FastAPI(...)` で作ると `/openapi.json` が既定で公開されるため、`docs_url`・`redoc_url`・`openapi_url` を明示する(D 4.12)。どちらでも URL・エラー形式は変わらない。
- OpenAPI の `operationId` は安定した名前(関数名)にし、生成物の名前が版で揺れないようにする。エラー応答の共通スキーマ(5.2)を各操作に宣言する。タグは **6 種**(sources・jobs・documents・opensearch・dashboard・meta)で、**操作の対象のリソースで決める**: EP-06(クロール起動)・EP-08(ロック解放)は `sources`(ソースに対する操作)、EP-07(取消)は `jobs`(ジョブに対する操作)。B 1.1 の「領域」列の「クロール操作」は章立ての区分で、タグではない(承認済みの案(ゲート3。2026-11-23)。BAPI-P-23。D の AAM-P-4 と同じ)。

### 5.5 アクセスログ

- 出すのは**メソッド・ルートのテンプレート・ステータス・所要時間(ミリ秒)だけ**。ID を含む実際のパス・クエリ・本文・ヘッダーは出さない(CAPI-P-27 と同じ。承認済みの案(ゲート3)。BAPI-P-17)。ルートに当たらないリクエストはパスの代わりに `-`。水準は INFO(`GET /healthz` は DEBUG)。**uvicorn は `log_config=None`・`access_log=False` で起動し、標準のアクセスログ(ID を含むパスを出す)は使わず、アクセスログは自前で出す**(Crawler・Indexer と同じ。D 4.1、C 8.5 の承認済みの案(ゲート3)。AAA-P-38)。
- 想定外の例外は、ログにクラス名・理由名・送出元の位置(ファイル:行・関数名)だけを出し、メッセージ・入力値は出さない。**想定外の例外は middleware が 500 `internal_error` に変換し、再送出しない**(再送出すると uvicorn が例外のメッセージを含むトレースバックを出すため。C 8.5 の承認済みの案(ゲート3)。AAA-P-38)。この保証は、**応答の開始前(ハンドラの中)に起きた例外に限る**。`StreamingResponse` の本文の生成中や `BackgroundTask` の中の例外は対象外(基盤・Admin API は JSON の応答だけを返す前提。D 4.12)。

### 5.6 タイムアウト・リトライの共通方針(承認済みの案。BAPI-P-12)

| 通信先 | 方針 | 仮値(設定可能。環境変数名は C が正本) |
| --- | --- | --- |
| OpenSearch(読み取り) | 1 リクエストのタイムアウトを設ける。**接続エラー(接続のタイムアウトを含む)と、HTTP ステータス 429・500・502・503・504 は少数回(2 回)再試行し、読み取りのタイムアウトは再試行しない**(遅いのか止まっているのかを区別するため。再試行するステータスは 5 値で、「5xx すべて」より狭い(例 501・505 は再試行しない)。C 3.7 の `retry_on_status`。承認済みの案(ゲート3)。AAA-P-8)。尽きたら 503 `unavailable` | 10 秒(接続・読み取りそれぞれ) |
| Crawler(操作 6 API) | **自動再送しない**(冪等でない API を含むため。P-5。crawler-api 3.4)。接続前の失敗と、送信後の応答喪失を区別して返す(B 2.3、2.6) | 接続 3 秒・応答 60 秒 |
| `/healthz` のプローブ・EP-13 の `opensearch` の確認(`cluster.health`) | 再試行しない(上の OpenSearch の既定の例外。**EP-13 の `opensearch` の確認は 3 秒・再試行なし**)。`/healthz` は 2xx かどうかだけを判定し、本文を解釈しない(P-5。応答形が契約外のため) | 確認ごとに 3 秒(B 11.7。承認済みの案(ゲート2))。HTTP のプローブは合計 3 秒、`cluster.health` は接続・読み取りそれぞれに適用され最大約 6 秒。EP-13 全体の期限は確認のタイムアウト + 1 秒(4 秒)で、超えた確認は判定不能として応答する(C 6.1) |

- Crawler の応答 60 秒(仮値)について。Crawler の Store 層の 1 操作は、再試行を含め最悪約 90 秒(crawler-architecture 10章の「最大約 90 秒」「約 93 秒」の記述と、11章の値(クライアントのタイムアウト 30 秒・最大試行 3 回)からの導出)で、受付は複数の読み書きを行う(導出)。応答 60 秒はこれより短い仮値で、これを超える受付は 504 になりうる。実測後に見直す(CAPI-U-10。BAPI-U-6)。

## 6. ヘルスチェック

- **`api` 自身**: `GET /healthz`(契約外の運用上の API。承認済みの案(ゲート3)。BAPI-P-13)。アプリケーションが作られ、受付を始めていれば 200・`{"status": "ok"}`(Indexer・Crawler と同形)。OpenSearch・Crawler・Indexer への到達性は見ない(内部情報は返さない)。コンテナの `HEALTHCHECK` に使う。
- **他コンテナの `/healthz`**: Admin API は Crawler・Indexer の `GET /healthz` を直接読む(確定。BAPI-K-5。ユーザー回答 2026-11-22。0001 Q1')。これは、
  - SD §7.3「`api` は `indexer` に接続しない」(起動順や稼働確認の方法は実装時に決めるとも書く。§12.5)の緩和を前提とし(I-60。HO-1)、
  - crawler-api の「`/healthz` は Admin API の契約外」(CAPI-P-19、§4.7)と indexer-api の同様の記述(§1。IA K67)に食い違う(I-61。HO-8・HO-14)。
  - 両者の `/healthz` は契約外のため、**2xx かどうかだけを判定し、本文は解釈しない**(承認済みの案。BAPI-P-13。作業プラン P-5)。応答形が変わっても Admin API は壊れない。Indexer は起動時の整理の完了まで接続拒否に見え(indexer-api §1)、Crawler は起動時の回復が終わるまで接続できない(crawler-api §3.1)ので、起動直後は「異常」に見える(B 8.1)。
- **確認先の URL は環境変数だけで決め、リクエストからは受け取らない**。確認のプローブは**リダイレクトに従わず、3xx は 2xx 以外として扱う**(B 8.1 の `unexpected_status`)。確認先を外から変えられる経路や、内部ネットワークの別のサービスへ誘導されうる経路を作らないため(導出)。
- 判定の詳細(異常と判定不能の境界、`web`・任意コンポーネントの判定)は B 8章(結果)と C(導出ロジック)。

## 7. 構成の共通方針(承認済みの案(ゲート3)。BAPI-P-18)

具体的なディレクトリ・モジュールは D が正本。本書は、Search API・MCP を足しても崩れない共通の規則だけを定める(Crawler・Indexer の構成に倣う)。

- **層**: エントリ(`main`・設定の読み込み)→ `server`(外側のアプリの汎用の口。機能パッケージを import しない)→ 機能パッケージ(`health`・`admin`。将来 `search`・`mcp`)→ `infrastructure`(外部システムへのアクセス)→ `common`(共通部品。葉で、誰にも依存しない)。機能パッケージを組み立てて `server` に渡すのは `main` だけ(D 4.1・4.2)。`health`(`GET /healthz`)は最初の機能パッケージで、`common` だけに依存する。
- **機能パッケージどうしは依存しない**(`admin` は `search`・`mcp` を import しない)。共通のものは `common` か `infrastructure` に置く。
- **外部システムへのアクセスは `infrastructure` だけ**: `opensearchpy` は OpenSearch アクセス(`cluster.health` のプローブを含む)、`urllib3` は Crawler クライアントと HTTP のヘルスプローブだけ、`anyio` は `common` の並行の部品だけが import する(D R5)。例外として `urllib3.exceptions` は、OpenSearch の例外の分類のため `infrastructure.opensearch`(`failure.py`・`health_probe.py`)に限って import してよい(3章。BAPI-P-22)。
- **Store 層へは読み取りだけ**: OpenSearch アクセスの Reader(許可リストのラッパー。D の語)は、書き込みのメソッドを**持たない**(型で書けない構成にする)。書き込みの経路は Crawler の HTTP クライアントだけ。
- 依存規則は AST(import 文)で機械検査し(`tests/architecture/`。Crawler・Indexer と同じ流儀)、外部アクセスの偽物は `tests/fakes/` に置く(D)。

## 8. コンテナ・compose への要求(承認済みの案(ゲート3)。BAPI-P-19)

本タスクは compose・Dockerfile を作らない。`api` サービスを足す infra の前提作業への要求を書く(9章)。

- サービス名 `api`。ビルドは `apps/api`(Web UI のビルド成果物を含むマルチステージ。ビルドステージの Node の版は E で指定。ベースイメージ・uv は Indexer の Dockerfile に倣い固定する)。
- **ホストへの publish は 127.0.0.1 に限る**(`127.0.0.1:${API_HOST_PORT:-8080}:8080`。コンテナ内のポートは固定の 8080(案)。Indexer の 8000・Crawler の 8001 と重ならない)。`0.0.0.0` を省いた書き方はしない(既存の compose の「公開範囲」の注意と同じ)。
- 環境変数: `LORELEY_API_OPENSEARCH_URL`、`LORELEY_API_CRAWLER_URL`(`http://crawler:8001`)、`LORELEY_API_INDEXER_URL`(`http://indexer:8000`)など(B 11.7 の名前。C の一覧)。索引名は次のように渡す(作業記録 0027 の指摘。実物 `infra/opensearch/init-indices.sh`・`deploy/compose/compose.yaml`・Indexer・Crawler の `config.py` で確認): **`sources`・`jobs` の索引名は Crawler と同じ変数から、`deletions` は Indexer と同じ変数から、検索インデックスのエイリアス(`api` の `SEARCH_INDEX_NAME`)は `opensearch-init` の `SEARCH_INDEX_ALIAS`(既定 `loreley-documents`)と Indexer の `LORELEY_INDEXER_SEARCH_INDEX_NAME`(エイリアス)と同じ変数から渡す。`opensearch-init` の `SEARCH_INDEX_NAME` は実体名(既定 `loreley-documents-000001`)で別物なので、`api` に渡さない**。現在の compose は Indexer に検索・削除記録の索引名を渡していないため、`api` を足す前提作業で変数を揃える(infra)。OpenSearch の認証・TLS(`OPENSEARCH_USERNAME`・`PASSWORD`・`VERIFY_CERTS`・`CA_CERTS_PATH`)を使うときは、Crawler・Indexer と同じ変数から渡す(C の案 AAA-P-30)。**`just_acquired` の猶予は、Crawler の `LORELEY_CRAWLER_ADMITTING_LOCK_GRACE_SECONDS` と Admin API の `LORELEY_API_ADMITTING_LOCK_GRACE_SECONDS` に同じ値を渡す**(1 つの変数から両方へ。ずれると画面の表示と Crawler の拒否がずれる。データは壊れない。C 5.9 の承認済みの案(ゲート3)。AAA-P-24)。**cron のタイムゾーンは、Crawler の `LORELEY_CRAWLER_TIMEZONE` と Admin API の変数に同じ値を渡す**(1 つの変数から両方へ。ずれると画面の表示と実際の実行時刻がずれる。運用前提。AAPI-P-11)。
- `depends_on`: `opensearch`(`service_healthy`)と `opensearch-init`(`service_completed_successfully`)。**`crawler`・`indexer` は待たない**(落ちていてもダッシュボードで異常を表示するため。BAPI-P-19)。
- `healthcheck`: `GET /healthz`。再起動ポリシー `unless-stopped`。`stop_grace_period` は既定で足りる(処理中のリクエストの完了を待つ程度。仮)。
- `api` に検索対象のディレクトリはマウントしない(`:ro` のマウントは `crawler` だけ。SD §6.4)。

## 9. 申し送り(追従改訂)一覧

本タスクの 6 文書(A〜F)が、本タスクの範囲の外にある文書・ファイルに求める変更と、運用・実装時に引き継ぐ事項を、**この章だけ**に集める(他の 5 文書は申し送りを持たず、該当する HO 番号を参照する)。9.2 が申し送りの一覧(`HO-1`〜`HO-51`)、9.3 がゲート3(2026-11-23)の確認事項と回答(`G3-1`〜`G3-23`)。

### 9.1 読み方

- 本タスクは SD・PD・crawler / indexer 設計・機能設計・画面仕様・DS・compose・Dockerfile・README を**変更していない**。変更が要るものは、すべて 9.2 に書き、各文書の担当(別タスク)が反映する。状態は、ゲート3(2026-11-23)の承認後は、すべて「未対応」(承認済みで、改訂・実施は別タスク。実装中に確認するものは「実装時確認」)。
- SD は補助文書で、crawler-api v0.4 の I-20 は「SD は廃止予定のため修正しない」とする。SD への申し送り(HO-1〜HO-5)は、SD を改訂する場合(v0.9 想定)、または同じ記述を持つ後継の文書への反映として読む。本タスクはどちらも決めない。
- 種別: **既存設計の改訂要求**(既存設計の記述と食い違う、または前提を変える)/ **追記**(食い違いはなく、決まったことの追加・更新。追加作業を含む)/ **運用前提**(README・運用手順・compose の値で守る前提)/ **実装時確認**(実装・結合テストで確かめる)/ **将来課題**(本タスクの範囲外で再検討)。
- 緊急度: **高**=`api` の実装・infra 作業に着手する前、または初回リリース前に反映・合意が要る / **中**=実装期間中に反映 / **低**=記述の整理で、いつでもよい。
- **HO-51 だけは、設計タスクの後に API 基盤の実装タスク(`20261123_implement_api_base`)が追加した**(他の HO-1〜HO-50 は設計タスクが出した。内訳は 9.2.10 の表の直後)。
- 「出典」は本タスクの文書の ID(`I-n` は各文書の表。A は I-60〜、B は I-70〜、C は I-90〜、D は I-110〜、E は I-80〜89・I-120〜、F は I-100〜)。既存設計の ID(`CAPI-*`・`IA K n`・`AF-U-n`)は引用。
- 本タスク内の引き継ぎ(B 11.10 の C への引き継ぎ、E 12.6 の F への引き継ぎ、D 8.6 の A・B・C への修正依頼)は、6 文書の間で完結する作業の記録で、申し送りではない(HO には入れない)。
- 状態の付け方: ゲート3の承認後は、承認を待つものはなく、「未対応」(別タスクでの改訂・実施待ち)と「実装時確認」を使う。HO-50(0000 のパス記載の差)はユーザー判断待ち。**HO-51 だけは、追従改訂を終えたので「対応済み」(2026-11-23)**。
- 申し送りにしなかったもの: SD §6.1・§6.2 の `Origin` 検査(ゲート2で不採用として扱った。BAPI-P-15。リスクは HO-41 と G3-2)、機能設計の「AF-5 は専用再実行 EP」(不採用のため。読み替えを HO-19 に書いた)、admin-view 10.4 の `web` と `api` の同居の扱い(I-72。画面は返された `state` を表示するだけで更新不要)。

### 9.2 申し送り一覧

#### 9.2.1 システム設計(SD。system-design-v0.8)

| ID | 対象 | 内容 | 出典 | 種別 | 緊急度 | 状態 |
| --- | --- | --- | --- | --- | --- | --- |
| HO-1 | SD §7.3 | 「`api` は `indexer` に接続しない」を緩和する。Admin API が Indexer の `GET /healthz` を直接読む(2xx かどうかだけ。本文は解釈しない)。`api`→`indexer` の通信経路が増える。起動順・稼働確認の方法(§12.5)は本設計(A 6章)に従う | BAPI-K-5・I-60・AAA-K-2。ユーザー回答(0001 Q1') | 既存設計の改訂要求 | 高 | 未対応 |
| HO-2 | SD §7.2 | `web` は独立コンテナにせず、`api` が Web UI を `/admin/` 配下に同一オリジンで静的配信すると書く。「Admin API もここに置く想定(案)」は、`api` 内の admin パッケージで確定 | BAPI-K-1・K-2・P-2 | 追記 | 中 | 未対応 |
| HO-3 | SD §7.5、§12.1 #5 | Web UI の技術スタック「未決定」を、E 2章の構成(Vue 3・Vuetify 4.3.4・Vite・TypeScript 6.x ほか)で更新する。API 側は Crawler・Indexer と揃える(A 3章) | FARC-K-1・FARC-P-30・BAPI-K-3 | 追記 | 低 | 未対応 |
| HO-4 | SD §14.4 | 重複起動の 409 `lock_held` を Admin API が通常は成功として扱う案は採らない。成功扱いにせず 409 で、既存ジョブと「指定は反映されていない」(`options_applied=false`)を返す(ゲート1で承認)。リース切れ・失効ロックの警告は `lock_state` で表示する。画面仕様 7.7 の「SD §14.4 の案になる場合も…」は、この設計で足りる | I-62・I-70・AAPI-P-35 | 既存設計の改訂要求 | 中 | 未対応 |
| HO-5 | SD §14.2 | 「Admin API が Crawler に中継する操作」の行に、ソース削除ジョブの起動とデータソース設定の登録・更新を加える(固定の 6 経路。crawler-api の I-20 と同じ指摘)。同じ行の「突合の起動」は MVP にない(crawler-architecture I-2)ので、あわせて整理する | B 1.1・AAA-K-7、crawler-api I-20 | 追記 | 低 | 未対応 |

#### 9.2.2 プロダクト設計(PD。product-design-v0.19)

| ID | 対象 | 内容 | 出典 | 種別 | 緊急度 | 状態 |
| --- | --- | --- | --- | --- | --- | --- |
| HO-6 | PD §4.6・§6.2・§9.2 #13 | 機能設計 6.1 の追記 4 点のうち 1・3・4 を追記する: OpenSearch 最小ビュー(AF-17。EP-12)、Loreley ダッシュボード(AF-18。EP-13)、`rewrite_mode` の画面指定(AF-3。EP-06)。いずれも機能設計でユーザー確認済み(UC-12・UC-16)。2 点目は HO-7 | 機能設計 6.1・AF-U-2、B 1.2 | 既存設計の改訂要求 | 低 | 未対応 |
| HO-7 | PD §3・§4 | Admin API の読み取り範囲を「Store 層」に限る書き方を広げる。検索インデックス(IA K53)と OpenSearch のクラスタ情報(`cluster.health`・`cat.*`)も読み取り専用で読む。書き込みはしない(BAPI-K-8) | I-63・機能設計 6.1 の 2・AAA-K-6・AAA-P-1 | 既存設計の改訂要求 | 低 | 未対応 |

#### 9.2.3 crawler 設計(crawler-api-v0.4・crawler-architecture-v0.4)

| ID | 対象 | 内容 | 出典 | 種別 | 緊急度 | 状態 |
| --- | --- | --- | --- | --- | --- | --- |
| HO-8 | crawler-api §4.7・CAPI-P-19 | `/healthz` は「Admin API の契約外」のまま、Admin API が 2xx かどうかだけを読んで死活の判定に使うと追記する(応答形は契約外のまま。変わっても Admin API は壊れない) | I-61・BAPI-P-13・BAPI-K-5 | 追記 | 中 | 未対応 |
| HO-9 | crawler-api CAPI-U-1・U-3・U-5・U-6・U-10 | 本設計での扱いを反映し、解消または一部解消とする。U-1: Admin API 設計(B・C)ができた(409 の扱いは AAPI-P-35)。U-3: 単位変換(日→秒、%→割合)と範囲検証は Admin API(AAPI-P-7・P-14)、既定値の補完は画面(AAPI-P-20)。U-5: `lock_held` は成功扱いにせず、409 で既存ジョブ・「指定は反映されていない」・`lock_state` を返す(AAPI-P-35)。U-6: `cancel_after_finish_notice`(EP-10)で「取消は削除を止めていない」を示し、取消の完了は J2 の `status` の自動更新で確認する。U-10: Crawler への接続 3 秒・応答 60 秒は仮値(BAPI-P-12。実測は BAPI-U-6・AAA-U-7) | B 11.6・A 5.6 | 追記 | 低 | 未対応 |
| HO-10 | crawler-api 4.4.3「順序の帰結」 | 文言を直す。設定があり保存済みの `connector_type` が読めるときだけ先に検証する。設定がなければ検証せず 404、種別が読めなければ 500(手順 3・4 が正)。`config_invalid` が先に返りうるのは 409 `source_deleting` に対してだけ。現行の文言は 404 についても先に検証されるように読めて曖昧 | B 3.4(EP-04)・9.2.5(作業記録 0010・0011 の指摘) | 追記 | 低 | 未対応 |
| HO-11 | crawler-api 3.3・4.4、connector-file-system(`config_invalid` の `message`) | Admin API は `config_invalid` の `message`(「項目名(配列は添字): 違反の種類」)と、Connector が定める日本語の固定文(`detail`)を、分解・完全一致で照合して項目別エラーにする(ユーザー回答で方式を承認。Connector の検証規則は複製しない)。`message` の形式や固定文を変えるときは、B 2.5・C 4.5・画面の対応表も更新する。Crawler が項目別の構造を返せば分解は不要になる | AAPI-U-2・AAA-K-4(0004) | 追記 | 中 | 未対応 |
| HO-12 | crawler-api 4.1 | `existing_job.lease_expires_at` が日時として読めないときだけ番兵値 `0001-01-01T00:00:00.000Z` を返す(他は `null`)。Admin API はそのまま通し、画面は「期限切れ」として扱う。この番兵値を契約として維持する | I-73・B 2.11・FARC-P-24 | 追記 | 低 | 未対応 |
| HO-13 | crawler-architecture 11章、crawler-api 4.3 | 受付の途中のロックとみなす `acquired_at` の猶予(60 秒。仮値)の環境変数名 `LORELEY_CRAWLER_ADMITTING_LOCK_GRACE_SECONDS`(既定 60。実装にはある)を書く。Admin API が同じ値を持つ必要があるため | I-91・AAA-P-24 | 追記 | 中 | 未対応 |

#### 9.2.4 indexer 設計(indexer-api-v0.10・indexer-architecture-v0.10)・検索インデックス設計

| ID | 対象 | 内容 | 出典 | 種別 | 緊急度 | 状態 |
| --- | --- | --- | --- | --- | --- | --- |
| HO-14 | indexer-api §1、IA K67 | `/healthz` は契約外のまま、Admin API が 2xx かどうかだけを読んで死活の判定に使うと追記する。Indexer は起動時の整理が終わるまで接続拒否に見える(§1) | I-61・BAPI-P-13 | 追記 | 中 | 未対応 |
| HO-15 | indexer-architecture U-30(K53) | Admin API の検索インデックスの読み取り条件への回答を反映し、U-30 を解消する。エイリアスだけを読む、`search`・`msearch` だけ(書き込み・`scroll`・PIT・スクリプトは呼ばない)、本文・要約は読まない、1 回に最大 100 件 | AAA-P-5(C 3.6) | 追記 | 中 | 未対応 |
| HO-16 | `opensearch/schema/search-index-v0.10.md` 4.1 | 「エイリアス名・実インデックス名は未決」を、エイリアス `loreley-documents`・実体 `loreley-documents-000001`(`init-indices.sh` と Indexer の既定)に確定する | I-90 | 追記 | 低 | 未対応 |

#### 9.2.5 機能設計(ui-admin-functions-v0.1)

| ID | 対象 | 内容 | 出典 | 種別 | 緊急度 | 状態 |
| --- | --- | --- | --- | --- | --- | --- |
| HO-17 | AF-17(3.7) | O1 にインデックスの絞り込み(画面仕様 opensearch の #37 で追加された絞り込みフォーム)を追記する。絞り込み・並べ替え・ページ分けは画面側で、EP-12 にパラメータはない | AAPI-P-6・画面仕様 opensearch 0章・admin-view 10.3 | 追記 | 低 | 未対応 |
| HO-18 | AF-U-1・3・5・6・7・9・10・13 | 解消を反映する(状態は B 11.6 の表)。U-1: 死活は `/healthz` の直接取得(HO-1)。U-3: 通知は 409 の `options_applied=false`・`requested`、ダッシュボードの更新間隔は 30 秒、「停止中」表示は将来拡張。U-5: 原本サイズ超過は専用タブ、「既存/新規」は検索インデックスの `document_id` の有無、本文の切り詰めの表示先は後続。U-6: `stalled`・登録文書数・取消の確認。U-7: Admin API が検証・変換(`ttl` 下限 1 は案)。U-9: 最終クロール完了日時は成功・一部成功の `finished_at` の最大値。U-10: 形は EP-10 の `registration`、数え方・保持は後続。U-13: cron のタイムゾーンは Admin API の環境変数を EP-14 で返す(次回実行予定日時は MVP に含めない) | B 11.6 | 追記 | 低 | 未対応 |
| HO-19 | AF-5(再実行) | 「元ジョブの両指定(`force_delete`・`rewrite_mode`)を Admin API が読んで起動の指定に渡す」(導出)を、「専用の再実行 EP を採用しなかったため、Admin View が EP-10 の応答(`force_delete`・`rewrite_mode`・`rerunnable`)をもとに EP-06 を呼ぶ」に読み替える | I-75・BAPI-P-15・AAPI-P-15(ゲート2 #19。ゲート3 G3-1 で不採用のままでよいと確認済み) | 追記 | 中 | 未対応 |
| HO-20 | AF-18・AF-20 | ダッシュボードの更新間隔 30 秒と Dashboards への外部リンクの出典は、機能設計(AF-U-3(c)・AF-U-11 で後続に委ねていた)ではなく、画面仕様 dashboard 4.1(#26。ゲート C)と admin-view 3章(ゲート B)と書く | AAPI-P-40(作業記録 0010 の指摘) | 追記 | 低 | 未対応 |

#### 9.2.6 画面仕様・デザインシステム(admin-view・DS・画面仕様 5 本)

| ID | 対象 | 内容 | 出典 | 種別 | 緊急度 | 状態 |
| --- | --- | --- | --- | --- | --- | --- |
| HO-21 | admin-view 10.4 | (1) `config_invalid` の項目別表示は案(a)(Admin API が Crawler の `message` を分解)に決まったと書く(推奨は案(b)だった。ユーザー回答で変更)。(2) 取得設定の上限値(100・1,024)と要約の有効 / 無効は API が返さない(画面が既定値・条件付き文言で表示し、最終判定はサーバー)と回答する | I-71・AAPI-K-5・AAPI-P-9・AAPI-P-20 | 追記 | 低 | 未対応 |
| HO-22 | admin-view 4.2 | route の `path`(`/`・`/sources` …)は `/admin/` からの相対(Router の `base: '/admin/'`)と注記する | I-81・FARC-P-2 | 追記 | 低 | 未対応 |
| HO-23 | DS 10.1 | TypeScript 7 の「`vue-tsc` が動かない報告がある」を「公式未対応(コミュニティの橋渡しで動く例はある)」に直す。結論(TypeScript 6.x 固定)は同じ | I-80(0004) | 追記 | 低 | 未対応 |
| HO-24 | DS 10.1 | 案として残る記述を更新する。Hey API の採用(exact pin。ゲート2)、「API の型は別タスク」は本タスクで決まった(E 5.2)、技術スタックの構成要素(Vue 3・Vite・Vue Router・TanStack Vue Query・Vitest・`vite-plugin-vuetify`・ESLint / Prettier・Playwright)はゲート1で承認済み | FARC-P-1・FARC-P-30(0013) | 追記 | 低 | 未対応 |
| HO-25 | DS 5.3 | `meta.title` は「文字列」だけでなく、`string` または `(route) => string`(S2・J2 の識別子・ジョブ ID を入れる動的な title)を許すと補足する | I-83・FMOD-U-10 | 追記 | 低 | 未対応 |
| HO-26 | DS 5.3 | `featureFlag` と外部リンクの扱い。本設計は、ナビ(`SideNav`・外部リンク領域)だけで評価しルートは隠さない。外部リンク項目は route を持たないため、route `meta` でなく定義表(`shell/externalLinks.ts`)で持つ。DS 5.3 の「ナビとルートを隠す」「定義は route `meta` にだけ」との差を、DS を直すか本設計を直すかで解消する | I-89・FARC-P-18・FMOD-P-29 | 既存設計の改訂要求 | 中 | 未対応 |
| HO-27 | DS 4章・6章 | 部品名・節を足す。`PageHeader`(DS 6.1 の「ページ見出し領域」)、注記ブロック(アイコン+文。`role` なし)、確認ダイアログ(本設計の `ConfirmDialog`・`ConfirmCheck`・`TypeToConfirm`)、`ShardMatrix` の部品群(DS 4.15 に独立した節・部品名の一覧がない) | I-100〜I-103 | 追記 | 低 | 未対応 |
| HO-28 | sources 2.4 | `reason` → 文言の表に、B の `range`・`exclusive`・`config_invalid` を追記する | I-84・E 6.4 | 追記 | 中 | 未対応 |
| HO-29 | 画面仕様(opensearch・documents・sources・jobs) | B の応答から必要になる状態を追記する。O1 の `truncated=true`、X1 の `source` が存在しないとき、S2・S4 で設定項目が読めない(`malformed`)とき、J2 の `stalled`・`rerunnable` が `null` のとき、S4 で保存値のしきい値が小数第 3 位以下を持つとき(丸め注意)、S2 のロック状態が `unknown` のとき。暫定の扱いは E 6.7・7.6・7.7・5.10 | I-87・FARC-P-27〜29・FARC-P-34 | 追記 | 中 | 未対応 |
| HO-30 | jobs 2.3、画面仕様の全般 | (1) 値の読めない `null`(`status=null` のジョブ、`registration` の件数・`partial`・`phase`)の表示を定義する(本設計の案は「—」+視覚的に隠した「読み取れません」。`status=null` はタグ・操作なし)。(2) `rerun_blocked_reason=source_missing` の理由文言を足す(削除中・削除済みの文言もない。本設計の案は「再実行」を出さない) | I-120・I-121・FARC-P-36・P-37・AAPI-P-41 | 追記 | 中 | 未対応 |
| HO-31 | admin-view 7.7、sources 1.5 | 孤児ロック・取得直後の `lock_held`(`existing_job.status=null`)では J2(EP-10)が 404 になりうる。本設計の案は「ジョブを表示」を出さず、S2 のロック状態カードへ導く(孤児ロックの解放の入口は S2 だけ)。J2 へ導く 7.7 の記述との差を直す | I-88・FARC-P-35 | 既存設計の改訂要求 | 中 | 未対応 |
| HO-32 | dashboard 3.3 | 判定不能の理由に「結果が古い」を挙げるが、Admin API は毎回確認するためこの理由を返さない(古さはクライアントが前回データを降格して表す。同 4.3)。画面側で足りるため更新は不要。理由コードの一覧は B 8.1 | I-74 | 追記(任意) | 低 | 未対応 |
| HO-33 | DS 4.9・14章 | ブラウザと Crawler(`cron_timezone`)のタイムゾーンが異なるときの日時の表示は未決。本設計はローカル時刻の表示(FARC-P-33)のままで、決めない | FARC-U-19、ゲート3 G3-13(決めず画面設計に任せる) | 将来課題 | 低 | 未対応 |

#### 9.2.7 compose・Dockerfile・CI・検査器(infra の前提作業)

| ID | 対象 | 内容 | 出典 | 種別 | 緊急度 | 状態 |
| --- | --- | --- | --- | --- | --- | --- |
| HO-34 | `deploy/compose/compose.yaml` | `api` サービスを足す。ビルドは `apps/api`、ホストの publish は `127.0.0.1:${API_HOST_PORT:-8080}:8080`(`0.0.0.0` を省いた書き方はしない)、`depends_on` は `opensearch`(`service_healthy`)と `opensearch-init`(`service_completed_successfully`)だけで `crawler`・`indexer` は待たない(落ちていても異常を表示するため)、`healthcheck` は `GET /healthz`、再起動は `unless-stopped`。`api` に検索対象のディレクトリはマウントしない | A 8・BAPI-P-14・P-19 | 追記 | 高 | 未対応 |
| HO-35 | compose の環境変数 | `api` に次を渡す。(1) `ADMITTING_LOCK_GRACE_SECONDS` は Crawler の `LORELEY_CRAWLER_ADMITTING_LOCK_GRACE_SECONDS` と同じ変数から。(2) 索引名: `sources`・`jobs` は Crawler と、`deletions` は Indexer と同じ変数から。検索エイリアス(`api` の `SEARCH_INDEX_NAME`)は `opensearch-init` の `SEARCH_INDEX_ALIAS` と Indexer の `LORELEY_INDEXER_SEARCH_INDEX_NAME` と同じ値にし、init の `SEARCH_INDEX_NAME`(実体名)は渡さない。現在の compose は Indexer に検索・削除記録の索引名を渡していないため、変数を揃える。(3) OpenSearch の認証・TLS(使うとき)は Crawler・Indexer と同じ変数から。(4) cron のタイムゾーンは Crawler の `LORELEY_CRAWLER_TIMEZONE` と同じ変数から(HO-43) | A 4・8、I-90・I-93、AAA-P-24・P-30、AAPI-P-11 | 追記 | 高 | 未対応 |
| HO-36 | `apps/api` の Dockerfile | Node のビルドステージを足す(Node 24 LTS。タグ+ダイジェスト固定、`npm ci`。型生成はビルドステージで行わない)。成果物 `dist/` を `api` イメージの `/app/web`(`LORELEY_API_WEB_DIST_DIR` の既定)にコピーする | FARC-P-3・P-20、AAA-P-43、E 3.5 | 追記 | 高 | 未対応 |
| HO-37 | compose・Dockerfile のビルドコンテキスト | 既存の compose は `build: ../../apps/<名前>`(コンテキスト=アプリのディレクトリ)で、`apps/api` を文脈にすると `apps/web` が見えない。コンテキストをリポジトリの `apps` 以上にするか、compose の `additional_contexts`(対応する Compose の版は推測で未確認)で足す。A 8 の「ビルドは `apps/api`」はこれに合わせて追従する | I-82・FARC-U-11 | 追記 | 高 | 未対応 |
| HO-38 | CI | 書き出した OpenAPI JSON と Hey API の生成コードをコミットし、CI で再生成の差分を検査する。静的解析・テストの実行順は E 10・11章 | FARC-P-6・P-23・BAPI-P-10 | 追記 | 中 | 未対応 |
| HO-39 | `apps/api` の `tests/architecture/`(Crawler の `dependency_rules.py` を流用) | Crawler の検査器は `urllib3` の所有者をモジュール単位で `indexer_client` だけとし、`opensearch` に使わせない前提。`urllib3.exceptions` をファイル単位(`infrastructure.opensearch` の `failure.py`・`health_probe.py`)で許す拡張が要る。読み取り専用の検査は許可リスト方式(Indexer の拒否リスト方式からの変更) | I-92・I-110・AAM-P-12・P-19 | 実装時確認 | 中 | 未対応 |

#### 9.2.8 README・導入手順

| ID | 対象 | 内容 | 出典 | 種別 | 緊急度 | 状態 |
| --- | --- | --- | --- | --- | --- | --- |
| HO-40 | README・導入手順(PD §6.1 に対応) | `api` は認証がなく、既定は localhost だけで待ち受ける(ホストへの publish は 127.0.0.1)。社内ネットワークへ公開すると、到達できる全員が破壊的操作(強制削除モードのクロール、データソース削除ジョブ、ロック解放、取消、設定の登録・更新)を実行できる。`connector_config` の `root` に Crawler のコンテナから見える任意のパスを指定できる(読めるのは `:ro` のマウントだけ)。これらを明示する | A 2.3・BAPI-K-4・PD §6.1 | 運用前提 | 高 | 未対応 |
| HO-41 | README・導入手順 | ブラウザ経由の書き込み要求への保護がないことを注意書きにする。悪意あるウェブページが、ユーザーのブラウザから本文なしの POST(EP-05・06・07)を送る攻撃で、DNS rebinding なら全 EP が対象。将来の認証設計に引き継ぐ(BAPI-U-3 と合わせる)。ゲート3(G3-2。2026-11-23)でリスクの受け入れと README の注意書きが承認済み。注意書きは未対応 | BAPI-U-8・A 2.3 | 運用前提 | 高 | 未対応 |
| HO-42 | README・導入手順(`apps/web`) | Node の版(22.18 以上の 22 系・24 系・26 以上。推奨 24 LTS)、型生成の手順(`app.openapi()` で OpenAPI JSON を書き出し、Hey API で生成して生成物をコミットする)、OpenAPI の実行時公開は既定で無効(`LORELEY_API_OPENAPI_ENABLED`)で型生成には不要、を書く | FARC-P-3・P-6・U-5、BAPI-P-4・P-10 | 追記 | 中 | 未対応 |

#### 9.2.9 運用前提

| ID | 対象 | 内容 | 出典 | 種別 | 緊急度 | 状態 |
| --- | --- | --- | --- | --- | --- | --- |
| HO-43 | 運用手順・compose | cron のタイムゾーンは、Crawler の `LORELEY_CRAWLER_TIMEZONE` と Admin API の `LORELEY_API_CRON_TIMEZONE` に同じ値を渡す(compose の共通変数)。ずれると、画面の表示と実際の実行時刻がずれる | AAPI-P-11・BAPI-K-7・BAPI-P-19 | 運用前提 | 中 | 未対応 |
| HO-44 | 運用手順・compose | 受付途中の猶予(60 秒)は、Crawler の `LORELEY_CRAWLER_ADMITTING_LOCK_GRACE_SECONDS` と Admin API の `LORELEY_API_ADMITTING_LOCK_GRACE_SECONDS` に同じ値を渡す。Crawler の値を Admin API が読む手段はない。ずれると、ロック状態の表示と操作の可否がずれる(データは壊れない) | AAA-P-24・AAA-U-6・AAPI-U-6 | 運用前提 | 中 | 未対応 |
| HO-45 | 運用手順 | 起動直後はダッシュボードが「異常」、Crawler への操作が 503 に見える。Indexer は起動時の整理が終わるまで接続拒否に見え、Crawler は起動時の回復が終わるまで(最大約 3 分。Dockerfile の `--start-period` 180 秒。仮値)接続できない。回復後は自動で応じる。Crawler・Indexer の停止中も、読み取りの EP は OpenSearch だけで応答する | A 6、B 8.1・9.1・10章、AAPI-U-1 | 運用前提 | 低 | 未対応 |

#### 9.2.10 実装時確認事項・将来課題・その他

| ID | 対象 | 内容 | 出典 | 種別 | 緊急度 | 状態 |
| --- | --- | --- | --- | --- | --- | --- |
| HO-46 | crawler-api 3.3「パスの扱い」(実機確認) | `job_id`(`%`・`?`・`#`・`.`・`%2F` など)を全文字符号化(`quote(safe="")` の後に `.` を `%2E` に置換)して送ったときの Crawler の挙動を、実 uvicorn で確認する(現在の記述は TestClient の実測)。400・404 が返れば EP-07 では 404 `job_not_found` に写す。生成 SDK がパスの値をどうエンコードするかも確認する | AAPI-U-12・AAA-U-4・FARC-U-18・FMOD-U-2 | 実装時確認 | 中 | 実装時確認(符号化の方式は G3-6) |
| HO-47 | E・F(フロントエンド) | 実装時に確認する。Vuetify 4.3.4(`VDataTableServer` の挙動、公式の Node 要件、DS が「実機で要確認」とする挙動)、`@mdi/js`(Apache-2.0)の社内ポリシー、`vite-plugin-vuetify` 2.1.x と Vite 8(Rolldown)の組み合わせ、Hey API 0.99 の `throwOnError` の既定と stale 表示の接続・生成コードのコミット方針、`app.frontend("/admin")` の細部、Playwright の `baseURL`・時計操作、Vue Query v5 の `isLoading` の意味(推測として本文に明記した点のひとつ)ほか。生成型は B の `null` 許容(`registration.partial` ほか)をそのまま反映する。一覧は E 12.4(FARC-U-1〜19)・F 8.4(FMOD-U-1〜11) | FARC-U・FMOD-U・B 2.2 | 実装時確認 | 中 | 実装時確認 |
| HO-48 | A・B・C・D(API) | 実装・結合テストで確認する。A 10.4(BAPI-U-1〜7)、B 11.4(AAPI-U-1〜12。上流の状態名・理由コードの確定時の再確認 U-3、要約未生成タブの実データでの検証 U-8 を含む)、C 12.4(AAA-U-1〜10。`cluster.health`・`cat.*`・`mget`・`msearch` の応答の形、`Connection: close` の挙動、実行中でロックなしの `stalled`、同時実行の上限と所要時間の実測、最小権限、EP-13 の期限後に残るスレッド)、D 8.4(AAM-U-1・3〜9。AAM-U-2 は基盤の実装とユーザー回答で確定した。AAM-K-5。HO-51)。A 10.4 の BAPI-U-2 は、サブアプリへの `FastAPI(root_path=…)`・入れ子のマウント・OpenAPI の `servers`・`paths` に絞って残る | BAPI-U・AAPI-U・AAA-U・AAM-U | 実装時確認 | 中 | 実装時確認 |
| HO-49 | Search API・MCP の設計時 | 再検討する。Admin API の破壊的操作が Search API と同じ公開範囲になる問題(認証の追加が前提。BAPI-U-3)、`/`(ルート)と Search View の配置・`/admin/` 以外のフォールバック(BAPI-U-4)、`search`・`mcp` を `admin` の兄弟に置く構成(AAM-U-6)、`shared/` の範囲と Search View と同じビルドにするか(FMOD-U-7・FARC-U-17) | BAPI-U-3・U-4、AAM-U-6、FMOD-U-7、FARC-U-17 | 将来課題 | 低 | 未対応 |
| HO-50 | 要件 0000(`agent_tasks/20261122_create_admin_system_design/`) | 成果物パスの記載(`ui-admins/api/ui-admin-api-*`)が、ユーザー確認済みの構成(`docs/v0.x/system-design/api/` と `ui-admin/frontend/`)と異なる(0001 Q3)。0000 はユーザー記載のため、本タスクでは修正していない | 0001 Q3 | 追記 | 低 | 未対応(ユーザー判断) |
| HO-51 | D(`admin/admin-api-module-structure-v0.1.md`)・A 7章(admin 実装前) | **admin の実装(Admin API のタスク)の前に、D を追従改訂する**(前提条件)。API 基盤の実装(`apps/api`)で、ヘルスチェックを独立した機能パッケージ `health/` にしたため、D と構成が異なる。D の章別の改訂内容・実装上の注意は、この表の直後の「HO-51 の内訳」に書く。承認済みの案(AAM-P-23)の一部を変える点を含むため、D の改訂時にユーザー確認を取る(**確認済み。2026-11-23**)。 | 作業記録 `agent_tasks/20261123_implement_api_base/`(完了後は `agent_tasks/_archive/` 配下)の 0002 2.2・0003・0004・0005・0006(確定内容は内訳に書いたので、作業記録は参考)。AAM-P-23 の承認は D 8.7。AAM-P-23・AAM-U-2、BAPI-P-9・BAPI-P-10 | 既存設計の改訂要求 | 高 | **対応済み**(`20261123_update_api_design_after_base_impl`。2026-11-23。D・A・B・C を改訂した) |

**HO-51 の内訳**(設計タスクの後に、API 基盤の実装タスクが追加した申し送り。9.2.1〜9.2.10 の他の HO は設計タスクが出したもの)

> 以下は申し送り当時の記述(2026-11-23 に対応済み。反映先は D の改訂履歴と 4.12)。「改める」「更新する」は未来形のまま残し、旧名称(`server/health.py`・`create_app(settings, admin_app)` など)も経緯の記録として残している。

- **D の改訂(章別)**
  - D 3章・4.2: `server/health.py` は `health/` パッケージ(`create_health_router()`・`HEALTH_PATH`)になった。`server` は機能パッケージを import しない汎用の口で、入口は `create_app(settings, admin_app)` ではなく `create_app(*, routers, mounts, debug_access_log_paths, lifespan)`(`SubAppMount(prefix, app)`)。組み立ては `main` が行い、admin は `main` で `SubAppMount("/api/admin/v1", create_admin_app(...))` を渡すだけ。`server` 専用の設定 dataclass(D 4.1)は作っていない。`README` は `apps/api/README.md` として作った(D 3章の「README は本タスクでは作らない」は設計タスクの記述)。
  - D 6章 R3・許可表: `server` は機能パッケージを import しない(許可表より厳しい)。`main` の行に `health` を足し、`health` の行(import は `common` だけ)を足した。許可表は `FEATURE_PACKAGES` から作る。基盤は `starlette` を制限せず、`server` が `fastapi`・`starlette` を使う(D R5 は `infrastructure` についてのみ記述)。
  - D 6章 R9: ルート関数を `async def` にする対象が `server/health.py` から `health/` に移った。`Depends` に渡す関数の `async def` 検査は未実装(基盤に `Depends` がないため。admin 実装時に足す)。
  - D 7.1: health のテストは `tests/server/` から `tests/health/` に移った。
  - **D 全体の洗い出し**: `server` が `admin` を import する記述、`server/health.py`、`create_app(settings, admin_app)` を D 全体で grep して改める。少なくとも次を含む: 2.1(`server` の行・図・「`server` が import するのは `admin` の入口だけ」の記述)、4.1 手順5、5.9、6章 R1、8.3 の AAM-P-2・AAM-P-3、7.3(`/healthz` のテスト配置)。旧構成の記述を残すと D 内で矛盾する。
  - D 4.2「ログと例外ハンドラ」・8.3 AAM-P-23・8.4 AAM-U-2: 「AAM-U-2 の確定」の項に合わせて改める。A 10.4 の BAPI-U-2 と HO-48 の AAM-U-2 の扱い(実装時確認)も更新する。
  - D 4.11: `ApiError(status_code, code, message, *, retryable=False, details=None)` は `retryable`・`details` がキーワード専用。`error_response` は `headers` 引数を持つ(405 の `Allow` のため)。422 の項目名の整形(孤立サロゲートの置換・制御文字のエスケープ・100 文字への切り詰め。Crawler の `display_text.py` 相当)は `common/http/handlers.py` 内に小さく実装した(`common/` に独立の部品は作っていない)。ログ AST 検査の対象メソッドは `debug`・`info`・`warning`・`warn`・`error`・`critical`・`fatal`・`exception`・`log`。
- **A の改訂**: A 7章の層の記述(エントリ → 機能パッケージ(`admin`。将来 `search`・`mcp`)→ …)に、`server`(汎用の口。機能を import しない)と `health`(最初の機能パッケージ)を加える。A 2.1 は `/healthz` を `api` の URL として列挙するだけで、`health` の導入による変更は不要(`health` のルーターは外側のアプリに載せている)。
- **AAM-U-2 の確定**: アクセスログは**外側のアプリの middleware だけが、サブアプリの処理後に 1 回出す**。サブアプリには `install_common_http(app, log_access=False)` で例外の吸収と `no-store` だけを設置する(**2026-11-23 の訂正**: サブアプリ側は例外の吸収を担当し、`/api/` の `no-store` は外側が付ける。D 4.2・AAM-K-5)。D の「外側はサブアプリ担当パスを除き、サブアプリ側が出す」(**AAM-P-23 は承認済みの案(ゲート3)であり、その分担を逆にする変更のため、D の改訂時にユーザー確認を取る。確認済み(2026-11-23。D の AAM-K-5)**)とは逆の分担になる。テンプレートは `scope["root_path"]` から `scope["app_root_path"]` を除いた部分と `scope["route"].path` で組み立てる。`route` が `methods` を持たない(Starlette の `Mount` など)ときは `-`(接頭辞が二重になるため)。同じ `scope` が共有される Starlette の挙動に依存する(FastAPI 0.165.0・Starlette 1.10.0 で確認。`tests/server/test_mounts.py` が固定し、更新時に検知する)。`FastAPI(root_path=...)` をサブアプリに設定すると壊れうる(2026-11-23 の対応で、推測・未検証と整理した。BAPI-U-2)。サブアプリ内の `Mount` 配下と外側アプリの `root_path`(プロキシ配下)はテストで固定済み。サブアプリの中にサブアプリをマウントする入れ子は未検証。`create_app` は `redirect_slashes=False` をサブアプリにも強制する。サブアプリ側(admin の factory)では `install_common_http` を呼ばない(二重になる)。
- **実装上の注意(admin 実装時)**
  - マウントしたサブアプリ自身の lifespan は実行されない(クライアントを閉じる処理は `create_app(lifespan=...)` に渡す)。
  - OpenAPI: 外側の `app.openapi()` にサブアプリのスキーマは集約されない。Admin API の OpenAPI は `create_admin_app(...).openapi()` で生成する(型生成の入力。BAPI-P-9・BAPI-P-10)。外側アプリは `openapi_url=None` のため、実行時に公開する場合はサブアプリ側(`create_admin_app`)の設定で行う。サブアプリを素の `FastAPI(...)` で作ると `/openapi.json` が既定で公開されるため、`docs_url`・`redoc_url`・`openapi_url` を明示すること(A 5.4)。
  - **想定外の例外を 500 にして再送出しない保証(A 5.5)の範囲**: レスポンスの開始前(ハンドラの中)に起きた例外だけ。`StreamingResponse` の本文の生成中や `BackgroundTask` の中の例外は、middleware(`BaseHTTPMiddleware`)が `call_next` の後で起きるため捕捉できず、送信を始めた応答は 500 に差し替えられない(uvicorn がメッセージを含むトレースバックを出しうる)。Admin API・基盤は JSON の応答だけを返す前提で、これらを使い始めるときは、純粋な ASGI middleware への置き換えなどを再検討する。
  - **OpenAPI の 422**: FastAPI は検証のある操作の OpenAPI に 422 の応答を既定で足す。基盤は `RequestValidationError` を 400 `invalid_request` に変えるため、Admin API の OpenAPI を生成するときは、400 の共通エラースキーマを宣言し、422 の宣言を除く(A 5.4。実際の応答と仕様を一致させる)。
  - `ClientDisconnect`(本文を読む POST・PUT で、クライアントが切断したとき)は、現状は想定外の例外として ERROR ログ・500 のアクセスログになる。admin 実装時に別扱い(ログ水準を下げるなど)を検討する。
  - 孤立サロゲートを含む JSON のキーは、pydantic が `loc=("body",)` の `format` にする。
  - ロガー制限の対象(opensearch・urllib3 など)と外部ライブラリの所有者(D R5)は、ライブラリの導入時に足す。
- **基盤が未実装のもの(admin 実装時に追加)**: 本文上限 1 MiB(超過は 400 `invalid_request`・`details` なし。D 3章の `common/http/body.py`)、厳密 JSON(型変換なし・未知項目は 400。A 5.1)、422 の reason `exclusive` と Admin 固有の値(`config_invalid` など)、`BlockingRunner`(`anyio`)、`/admin/` の静的配信と `WEB_DIST_DIR`、OpenAPI の書き出しと実行時公開の有効化(`OPENAPI_ENABLED`)、`infrastructure`、OpenSearch・Crawler 関連の設定(`ADMITTING_LOCK_GRACE_SECONDS` を含む。A 4章の表のうち実装済みは `HOST`・`PORT`・`LOG_LEVEL` だけ)。
- **他文書の表記**: B・D・`admin-api-architecture` の「HO-1〜HO-50」と、D 冒頭の「本書に関わるものは HO-39」は、D の追従改訂時に HO-51 を含めて更新した(2026-11-23。B・C・D は「HO-1〜HO-51」、D の関連 HO は HO-39・HO-48・HO-49・HO-51)。

### 9.3 ゲート3の確認事項と回答(2026-11-23)

**ゲート3(2026-11-23)で、ユーザーは G3-1〜G3-23 のすべてを現案(推奨)どおり承認した**(回答は右端の列)。決定の承認が必要な案のうち、ユーザーの判断が分かれうるものを抜き出した表で、推奨は各文書の現案、選択肢は各文書の記述から整理した。B 11.9・C 12.6・D 8.7・A 10.3 の表と、E 12.3・F 8.3 の ID 一覧は、ID 単位の全件の表として残してあり、ここはその要点。上記のどの行にも挙げていない案は、G3-23 に ID を列挙した。承認の結果は、各文書の区分(承認済みの案(ゲート3。2026-11-23))に反映済み。

| ID | 確認する事項 | 推奨(現案) | 選択肢 | 関連 ID・申し送り | 回答(2026-11-23) |
| --- | --- | --- | --- | --- | --- |
| G3-1 | 再実行の専用 EP と書き込み系の `Origin` 検査を「不採用として扱った」解釈(ゲート2の複数選択で `/meta` だけが選ばれたため) | 不採用のまま(再実行は画面が EP-06 を呼ぶ) | (a) 不採用でよい (b) 再実行の専用 EP を採用(EP を足し、HO-19 を変える) (c) `Origin` 検査を採用(SD §6.1・§6.2 の MCP 向け検査に倣う。G3-2 の緩和になる) | BAPI-P-15・AAPI-P-15、B 11.7 #19・#23、HO-19 | 承認(現案)。不採用のままでよい(再実行は画面が EP-06 を呼ぶ。`Origin` 検査は入れない) |
| G3-2 | 未対応のリスク(ブラウザ経由の書き込み要求への保護がない)を受け入れるか、軽い緩和を足すか | 受け入れる(MVP の運用前提=信頼できる利用者・localhost。軽い緩和は要件外のため足していない)。判断材料: PD v0.19 §2 のリスク表は「Admin View を保護しない」を許容する制約として載せ(信頼できる利用者だけの検証環境向け)、MCP の DNS rebinding には Origin 検証を MVP に含める(§6.1) | (a) 受け入れ、README に注意書き (b) 全 POST で `Content-Type` 必須などの軽い緩和を足す(要件の追加。現案では本文なしの POST の EP-05・06・07 が保護されない) (c) `Origin` 検査(G3-1(c)) | BAPI-U-8、A 2.3(PD §2 の引用)、HO-41 | 承認(現案)。リスクは受け入れ、README に注意書き(HO-41)。軽い緩和は足さない。リスクは残る |
| G3-3 | 区分の確認: 既承認文書の「承認済みの案」の引用(時刻の UTC ISO 8601、更新間隔 30 秒・外部リンク、DS・画面仕様のゲート B・C の承認事項)と、導出・解釈の扱い(個別の技術選定、EP 一覧をゲート2の承認として扱った解釈、FARC-P-30 を確定から承認済みの案に変えたこと) | そのまま承認(区分欄を「承認済みの案(ゲート3)」に) | (a) 承認 (b) 個別に変更(内容を指定) | BAPI-P-20・P-21、AAPI-P-3・P-40、FARC-P-30〜33・38、FMOD-P-26、AAPI-P-35・36(ゲート1承認済みの区分訂正のみで判断不要) | 承認(現案) |
| G3-4 | `ttl` の下限を 1 にする(ゲート1の「非負」からの変更。画面仕様 sources 2.3 の「1 以上の整数」に合わせた) | 1 以上 | (a) 1 以上 (b) 0 以上(ゲート1どおり。画面仕様との調整が要る) | AAPI-P-37 | 承認(現案) |
| G3-5 | 保存済みのしきい値が小数第 3 位以下を持つとき(Crawler の API 直接登録など)、応答は厳密変換し、再保存は 400 `format` になる。画面が注意を出し丸めさせる(S4 は丸めた値を入力欄に入れる。四捨五入が案) | 現案 | (a) 現案 (b) 別の逃げ道(秒指定など)を足す(要件の追加) | AAPI-P-38、FARC-P-29 | 承認(現案) |
| G3-6 | `job_id` に含まれる `.` の扱い | `.` を `%2E` に置換して送る(検証規則は変えない) | (a) `%2E` に置換 (b) `.`・`..` だけの `job_id` を B 2.12 の検証で拒否(AAPI-P-24 の変更) | AAPI-P-24・U-12、AAA-P-14、HO-46 | 承認(現案) |
| G3-7 | 取消(EP-07)で、`job_id` を理由とする Crawler の 400 `invalid_request`・404 `not_found` の写像 | 404 `job_not_found` | (a) 404 `job_not_found` (b) 502(Crawler の応答不整合として扱う) | AAPI-P-39 | 承認(現案) |
| G3-8 | `rerun_blocked_reason` の新値 `source_missing`(設定がない=削除済み)と、「再実行」を出さない扱い | 専用値。「再実行」は出さず、専用の文言は確認後に画面仕様へ | (a) 専用値 `source_missing` (b) `source_deleting` に寄せる(削除済みのソースを「削除中」と誤表示するため非推奨) | AAPI-P-41、FARC-P-37、FMOD-P-32、I-121、HO-30 | 承認(現案) |
| G3-9 | 値の読めない `null`(`status=null` のジョブなど。取得失敗とは別)の表示 | 「—」+視覚的に隠した「読み取れません」。`status=null` のジョブはタグ・操作なし | (a) 現案 (b) 画面仕様で別の表示を決める(HO-30 で追記) | FARC-P-36、I-120、HO-30 | 承認(現案) |
| G3-10 | 孤児ロック・取得直後の `lock_held` の導線(ジョブ記録がなく J2 が 404 になりうる) | 「ジョブを表示」を出さず S2 のロック状態カードへ導く(admin-view 7.7 を追従改訂) | (a) 現案 (b) 7.7 のとおり J2 へ導き、ジョブ記録がないときの J2 の表示を足す(追加の設計が要る) | FARC-P-35、I-88、HO-31 | 承認(現案) |
| G3-11 | `featureFlag` はナビ(`SideNav`・外部リンク領域)だけで評価し、外部リンク項目を route `meta` でなく定義表(`shell/externalLinks.ts`)に持つ(DS 5.3 との差) | 現案(DS 5.3 を追従改訂) | (a) 現案 (b) DS 5.3 のとおり route `meta` に持つ(外部リンクを route として扱う必要があり、admin-view 4.2 と合わない) | I-89、FARC-P-18、FMOD-P-29、HO-26 | 承認(現案) |
| G3-12 | ルートを遅延読み込みしない(ビルドサイズの実測前の判断) | しない(実装後に実測して再判断) | (a) しない (b) 最初から遅延読み込み(`router.onError` を足す) | FMOD-P-17・U-11 | 承認(現案) |
| G3-13 | ブラウザと Crawler のタイムゾーンが異なるときの日時の表示(DS 4.9・14章で未決) | 本タスクでは決めない(ローカル時刻の表示のまま) | (a) 決めずに画面設計へ (b) 不一致時の注意などを今決める(画面設計が要る) | FARC-U-19・P-33、HO-33 | 承認(現案)。決めず画面設計に任せる(FARC-U-19 は未決のまま持ち越し) |
| G3-14 | OpenSearch の再試行の条件: `retry_on_timeout=False`、接続エラーの再試行、`retry_on_status=(429, 500, 502, 503, 504)`(A 5.6 の「5xx」より狭い) | 現案 | (a) 現案(5 値) (b) 5xx をすべて再試行 | AAA-P-8、BAPI-P-12 | 承認(現案) |
| G3-15 | Crawler・Indexer への接続を MVP では `http` に限る(TLS の検証設定を持たない。`SSLError` は 503 `crawler_unreachable`) | `http` 限定 | (a) `http` 限定 (b) TLS 検証(CA)の設定を持つ(AAA-U-9) | BAPI-P-24、AAA-P-41 | 承認(現案) |
| G3-16 | `WEB_DIST_DIR` の既定を `/app/web`(Dockerfile が `dist/` をコピーする固定パス) | `/app/web` | (a) `/app/web` (b) 別の固定パス (c) 既定なし(必須の設定) | AAA-P-43、HO-36 | 承認(現案) |
| G3-17 | 検索インデックスの読み取り条件(indexer-architecture U-30 への回答): エイリアスだけ、`search`・`msearch` だけ、本文・要約を読まない、最大 100 件 | 現案(Indexer 設計へ反映=HO-15) | (a) 承認 (b) 条件を変更(内容を指定) | AAA-P-5、HO-15 | 承認(現案) |
| G3-18 | `just_acquired` の猶予(60 秒)の同期方法 | 環境変数+compose の同値定義(Crawler の値を Admin API が読む手段はない) | (a) 現案 (b) Crawler に読み取りの手段を足す(Crawler 設計の変更) | AAA-P-24・U-6、I-91、HO-13・35・44 | 承認(現案) |
| G3-19 | 索引名の渡し方: 検索エイリアスは init の `SEARCH_INDEX_ALIAS` と Indexer の `LORELEY_INDEXER_SEARCH_INDEX_NAME` と同じ値。init の `SEARCH_INDEX_NAME`(実体名)は `api` に渡さない | 現案(infra の前提作業) | (a) 現案 (b) compose では渡さず、`api` の既定値 `loreley-documents` に頼る | I-90・I-93、HO-35 | 承認(現案) |
| G3-20 | `urllib3.exceptions` の import を `infrastructure.opensearch`(`failure.py`・`health_probe.py`)に限って許すこと(検査器の拡張が要る)と、OpenAPI のタグを 6 種にすること(EP-06・08 は `sources`、EP-07 は `jobs`) | 現案 | (a) 承認 (b) 例外分類をクラス名・MRO の文字列比較にして許可しない(理由を書く) (c) タグを別の割り当てにする | BAPI-P-22・P-23、AAA-P-40、AAM-P-4・P-12、I-92・I-110、HO-39 | 承認(現案) |
| G3-21 | C の重点案(実装形はゲート3で承認のもの) | 承認 | 個別に外す・変更する ID を指定。P-1〜3(読み取りの許可リストと `mget`)、P-18・19・25(`stalled`・`rerunnable`・読めない値の `null`)、P-30(足した環境変数)、P-33・42(`async def` と区分別の上限、EP-13 の期限後の放棄)、P-39(部分的な失敗を成功と読まない)、P-44(`JobBrief` の各項目の規則)。P-5・24・40・41・43 は G3-17・18・20・15・16 でも確認 | AAA-P | 承認(現案。一括) |
| G3-22 | D の重点案 | 承認 | 個別に外す・変更する ID を指定。P-2・17(層の並びと兄弟)、P-4(タグ)、P-5(`async def`+`BlockingRunner`、`web` の例外)、P-8・19(許可リスト方式)、P-10〜12(Crawler クライアント・`crawler_mapping`・プローブの置き場)、P-15(uvicorn の起動引数)、P-16(OpenAPI の書き出し)、P-18(依存ルール)、P-21〜23(偽物の水準、依存パッケージ、サブアプリ下のハンドラ)、P-26・27(`no-store`、期限後の放棄)、P-28(uvicorn の停止と `timeout_graceful_shutdown`) | AAM-P | 承認(現案。一括) |
| G3-23 | G3-1〜22 に挙げていない案の一括承認 | 承認 | 個別に外す・変更する ID を指定。A: BAPI-P-6〜8・11(一部)・13(一部)・16〜19。B: AAPI-P-16〜18・24〜34(P-24 の `.` は G3-6)。C: AAA-P-4・6・7・9〜13・15〜17・20〜23・26〜29・31・32・34〜38(P-4・13 は承認済みの案で、実装形のみの確認)。D: AAM-P-1・3・6・7・9・13・14・20・24・25(P-1・3 は承認済みの案で、実装形のみの確認)。E: FARC-P(案)全件(P-18 は G3-11、P-35 は G3-10、P-36 は G3-9、P-37 は G3-8 でも確認)。F: FMOD-P(案)全件(P-17 は G3-12、P-29 は G3-11、P-32 は G3-8 でも確認)。AAPI-P-35・36 はゲート1承認済みの区分訂正のみで判断不要 | 各文書の表 | 承認(現案。一括) |

## 10. 確認状況

### 10.1 確認した事実(2026-11-22)

- PD v0.19 §6.1(認証なし、任意のローカルパス、既定は localhost)、SD v0.8 §6.1〜6.4(Origin 検査は MCP 向け、バインド先、`:ro`)・§7.2・§7.3(`api` は `indexer` に接続しない)・§14.2・§14.4(`lock_held` の冪等成功の案)を読んだ。PD v0.19 §2(主要リスクと許容する制約。リスク表の「Admin View を保護しない」「MCP の公開(認証なし)」。145・153 行)も読んだ(R4 の指摘で追加)。
- crawler-api v0.4: 1章(6 API)、3.1(内部のみ・認証なし・回復中は接続エラー)、3.3(エラー形式)、3.6(アクセスログ)、4.7(`/healthz` は契約外)、CAPI-P-19・CAPI-U-1・5・10 を読んだ。indexer-api v0.10 の 1章(`/healthz` は契約外。起動前は接続拒否に見える)を読んだ。
- `apps/crawler/pyproject.toml`・`apps/indexer/pyproject.toml`(Python・FastAPI・uvicorn・pydantic・opensearch-py・urllib3 の版)、`apps/crawler/tests/architecture/dependency_rules.py`(AST の依存検査)、`deploy/compose/compose.yaml`(ホストの publish は 127.0.0.1、Crawler は publish なし、Indexer 8000・Crawler 8001、索引名の同値定義)、`infra/opensearch/init-indices.sh`(既定の索引名・エイリアス)を確認した。`apps/api/`・`apps/web/` は存在しない(新規)。
- 技術事実(FastAPI の `app.frontend()`、OpenAPI の無効化、Hey API、opensearch-py 3.2.0)は、フェーズ0の tech-advisor の報告(0004。調査日 2026-11-22)による。本書の作成者は再確認していない。

確認していないこと: `app.frontend("/admin", …)` の細部(BAPI-U-1)、サブアプリへの `FastAPI(root_path=…)`・入れ子のマウント・サブアプリのマウントでの OpenAPI の `servers`・`paths`(BAPI-U-2。外側アプリの `root_path`(プロキシ配下)・例外ハンドラ・アクセスログの適用範囲は確定済み。D の AAM-K-5)、Hey API の生成物と `app.openapi()` の組み合わせ、セキュリティ有効時の OpenSearch の最小権限(BAPI-U-7)。

### 10.2 確定(BAPI-K)

確定にしたのは、ユーザー回答と、確定として書かれている既承認文書の引用だけ。承認済みの案を引用したものは確定にしない。ゲート1の承認は、案を確定に付け替えるものではない(10.3)。

| ID | 内容 | 出典 |
| --- | --- | --- |
| BAPI-K-1 | Admin API は `api` コンテナ内の admin パッケージ。Search API・MCP は設計対象外 | ユーザー回答(2026-11-22。0001 Q2) |
| BAPI-K-2 | Web UI は `api` が静的配信する(同一オリジン。CORS 不要) | 同上 |
| BAPI-K-3 | API の技術スタックは Indexer・Crawler と揃える。個別の選定(Python 3.12・FastAPI・uvicorn・pydantic・pydantic-settings・opensearch-py)は導出で、BAPI-P-21 | 要件 0000「APIの技術スタックはindexerやcrawlerと揃える」(ユーザー記載) |
| BAPI-K-4 | MVP は認証なしで、任意のローカルパスを登録できる。既定は localhost だけで待ち受ける | PD §6.1、CAPI-K-7(引用) |
| BAPI-K-5 | Indexer・Crawler の死活は、Admin API が各 `/healthz` を直接読む。SD §7.3 の緩和が前提(SD は改訂せず申し送る) | ユーザー回答(2026-11-22。0001 Q1') |
| BAPI-K-6 | (欠番。確定ではなく承認済みの案(既承認文書の引用)のため BAPI-P-20 に移した。作業記録 0010 の指摘) | — |
| BAPI-K-7 | cron のタイムゾーンは Admin API の環境変数で持つ(名前は AAPI-P-11) | ユーザー回答(2026-11-22。0001 Q1) |
| BAPI-K-8 | Admin API は Store 層・検索インデックスに書かない(読み取りのみ。メンテナンスフラグも書かない) | CAPI-K-5(確定。`loreley-jobs` に書くのは Crawler だけ)、SD §14.2・§14.4(引用)。メンテナンスフラグの書き込み手段(運用者の手動手順)は承認済みの案(CA-U-3) |

### 10.3 案・承認済みの案(BAPI-P)

「0002 4章」列は、作業プラン 4章の事項番号。区分欄に承認したゲート(ゲート1=方針、ゲート2=具体値・名前。いずれも 2026-11-22)を書いた。確定(`-K-`)にはしていない。

| ID | 内容 | 区分 | 0002 4章 | 章 |
| --- | --- | --- | --- | --- |
| BAPI-P-1 | API の URL は `/api/admin/v1/...` | 承認済みの案(ゲート1。2026-11-22) | 12 | 2.2 |
| BAPI-P-2 | Admin View は `/admin/` 配下・history モード。`/admin/` 配下の未知パスだけ `index.html`。実装は `app.frontend()` を第一候補 | 承認済みの案(配置・フォールバックの方針はゲート1。フォールバックの範囲の解釈と `app.frontend()` の第一候補はゲート2。2026-11-22) | 14 | 2.2 |
| BAPI-P-3 | OpenAPI は内部向けに用意し、型生成に使う。公開の既定と無効化は環境変数 | 承認済みの案(ゲート1。2026-11-22) | 12 | 5.4 |
| BAPI-P-4 | OpenAPI の具体値: パス `/api/admin/v1/openapi.json`、既定は無効、`LORELEY_API_OPENAPI_ENABLED`、対話型ドキュメントは常に無効 | 承認済みの案(ゲート2。2026-11-22) | 12 | 5.4 |
| BAPI-P-5 | エラー応答の統一形式(`error.code`・`message`・`retryable`・`details.errors`)と共通 code。code 名はゲート2で承認 | 承認済みの案(形式はゲート1、code 名はゲート2。2026-11-22) | 2 | 5.2 |
| BAPI-P-6 | 環境変数の接頭辞 `LORELEY_API_` と命名規則、共通の設定項目(OpenSearch の認証・TLS、索引名 4 つ、`ADMITTING_LOCK_GRACE_SECONDS` を含む。C の案 AAA-P-30・P-24) | 承認済みの案(ゲート3。2026-11-23) | — | 4 |
| BAPI-P-7 | Crawler への HTTP は urllib3 | 承認済みの案(ゲート3。2026-11-23) | — | 3 |
| BAPI-P-8 | fastapi の下限 `>=0.143.2` | 承認済みの案(ゲート3。2026-11-23) | — | 3 |
| BAPI-P-9 | Admin API はサブアプリのマウントで構成する(代替: `APIRouter`) | 承認済みの案(ゲート2。2026-11-22) | — | 5.4 |
| BAPI-P-10 | 型生成は Hey API(exact pin)。入力は `app.openapi()` の書き出し | 承認済みの案(ゲート2。2026-11-22) | — | 5.4 |
| BAPI-P-11 | 実装ディレクトリ `apps/api/`(パッケージ `loreley_api`)・`apps/web/`。パッケージ管理・テストは既存に揃える | 承認済みの案(ゲート2。2026-11-22。パッケージ管理・テストの揃えは承認済みの案(ゲート3。2026-11-23)) | — | 3 |
| BAPI-P-12 | タイムアウト・リトライの共通方針(Crawler への書き込みは自動再送しない。読み取りは少数回の再試行。再試行は接続エラーと 429・500・502・503・504 で、読み取りのタイムアウトは再試行しない) | 承認済みの案(自動再送しない方針はゲート1・作業プラン P-5、仮値はゲート2。2026-11-22)。再試行条件の明確化は承認済みの案(ゲート3。2026-11-23。C 3.7 の AAA-P-8) | 2 | 5.6 |
| BAPI-P-13 | `api` 自身の `GET /healthz`(契約外)。他コンテナの `/healthz` は 2xx だけを判定する | 承認済みの案(2xx だけを判定する方針はゲート1・作業プラン P-5)。`api` 自身の `/healthz` は承認済みの案(ゲート3。2026-11-23) | 9 | 6 |
| BAPI-P-14 | 公開範囲: ホストの publish は 127.0.0.1 のみ。コンテナ内のポートは 8080 | 承認済みの案(ゲート2。2026-11-22) | — | 2.3、8 |
| BAPI-P-15 | (不採用)書き込み系の `Origin` 検査。要件にない追加の提案として挙げたが、ゲート2の回答で採用が選ばれなかった。代わりに 2.3 に未対応のリスクを書き、BAPI-U-8 に登録した | 不採用として扱った(ゲート2の回答で採用が選ばれなかったため。解釈。ゲート3(2026-11-23)で「不採用のままでよい」と明示回答)。ID は欠番として残す | — | 2.3 |
| BAPI-P-16 | 共通の HTTP 規約の細部(`snake_case`、`null` の明示、厳密な JSON、本文の上限 1 MiB、末尾スラッシュは 404、`no-store`、検証の範囲) | 承認済みの案(ゲート3。2026-11-23) | 2 | 5.1、5.3 |
| BAPI-P-17 | アクセスログは メソッド・ルートのテンプレート・ステータス・所要時間だけ。uvicorn は `log_config=None`・`access_log=False` で起動し自前で出す。想定外の例外は middleware が 500 に変換して再送出しない | 承認済みの案(ゲート3。2026-11-23) | — | 5.5 |
| BAPI-P-18 | 構成の共通方針(層、機能パッケージどうしは依存しない、外部アクセスは `infrastructure`、読み取り専用の Reader、AST 検査) | 承認済みの案(ゲート3。2026-11-23) | — | 7 |
| BAPI-P-19 | compose への要求(127.0.0.1 の publish、`crawler`・`indexer` を待たない、cron のタイムゾーンの同値定義) | 承認済みの案(ゲート3。2026-11-23) | 13 | 8 |
| BAPI-P-20 | 時刻は UTC の ISO 8601・ミリ秒で返す(CA-P-38 の形式。admin-view 10.4 が API の時刻を ISO 8601(UTC)とする) | 承認済みの案(既承認文書の引用。ユーザー確認済み(ゲート3。2026-11-23)) | — | 5.1 |
| BAPI-P-21 | API の個別の技術選定: Python 3.12、FastAPI、uvicorn、pydantic、pydantic-settings、opensearch-py(同期)。「単一プロセス」も Crawler・Indexer が単一プロセスであることによる導出 | 承認済みの案(ゲート3でユーザー確認済み。2026-11-23。導出。出典: `apps/crawler/pyproject.toml`・`apps/indexer/pyproject.toml`) | — | 3 |
| BAPI-P-22 | 外部ライブラリの import の所有: `urllib3.exceptions` を OpenSearch の例外の分類のために `infrastructure.opensearch`(`failure.py`・`health_probe.py`)に限って許す。`cluster.health` のプローブは opensearchpy、HTTP のプローブは urllib3 | 承認済みの案(ゲート3。2026-11-23) | — | 3・7 |
| BAPI-P-23 | OpenAPI のタグは 6 種で、操作の対象のリソースで決める(EP-06・08 は `sources`、EP-07 は `jobs`)。B の「領域」列の「クロール操作」はタグではない | 承認済みの案(ゲート3。2026-11-23) | — | 5.4 |
| BAPI-P-24 | `CRAWLER_URL`・`INDEXER_URL` は MVP では `http` 限定(内部ネットワーク前提。TLS の検証設定は持たない) | 承認済みの案(ゲート3。2026-11-23) | — | 4 |

**ゲート3(2026-11-23)で承認した ID**(ゲート1・2の対象外、または解釈・導出だったもの。ユーザーの判断が分かれうるものの要点と回答は 9.3):

| ID | 区分 | 確認の要点 |
| --- | --- | --- |
| BAPI-P-22・23・24 | 承認済みの案(ゲート3。2026-11-23) | `urllib3.exceptions` の import の許可範囲、OpenAPI のタグ 6 種の割り当て、Crawler・Indexer への接続を http 限定にすること |
| BAPI-P-6・7・8 | 承認済みの案(ゲート3。2026-11-23) | 環境変数の接頭辞 `LORELEY_API_`、urllib3、fastapi の下限 `>=0.143.2` |
| BAPI-P-11(一部) | 承認済みの案(ゲート3。2026-11-23) | パッケージ管理・テストを既存に揃えること |
| BAPI-P-13(一部) | 承認済みの案(ゲート3。2026-11-23) | `api` 自身の `GET /healthz`(契約外) |
| BAPI-P-15 | 不採用として扱った(解釈)。ゲート3(2026-11-23)で不採用のままでよいと確認済み | `Origin` 検査を採用しなかったことと、リスクの扱い(BAPI-U-8) |
| BAPI-P-16・17・18・19 | 承認済みの案(ゲート3。2026-11-23) | 共通 HTTP 規約の細部、アクセスログ、構成の共通方針、compose への要求 |
| BAPI-P-20 | 承認済みの案(既承認文書の引用。ゲート3でユーザー確認済み。2026-11-23) | 時刻を ISO 8601(UTC)で返すこと(0001 の「既存設計でそのまま使うもの」をユーザーが確認したか) |
| BAPI-P-21 | 承認済みの案(導出。ゲート3でユーザー確認済み。2026-11-23) | 個別の技術選定(FastAPI ほか)を、既存の `pyproject.toml` に揃えること |
| BAPI-U-8 | 未決 | 未対応のリスク(ブラウザ経由の書き込み要求)を受け入れるか、軽い緩和を足すか(ゲート3で、受け入れ・軽い緩和は足さないと確認済み) |

### 10.4 未決(BAPI-U)

| ID | 内容 | 決める場所 |
| --- | --- | --- |
| BAPI-U-1 | `app.frontend("/admin", …)` の細部(`/admin` 末尾スラッシュなし、`/admin/` 配下の存在しないアセットの 404、`/api/` との優先)。0004 の未確認事項 | 実装時 |
| BAPI-U-2 | サブアプリへの `FastAPI(root_path=…)`・入れ子のマウント・サブアプリのマウント時の OpenAPI の `servers`・`paths`(外側アプリの `root_path`(プロキシ配下)・例外ハンドラ・アクセスログの適用範囲は、基盤の実装で確定した。D の AAM-K-5。D 4.2) | admin 実装時 |
| BAPI-U-3 | Search API が同居・公開されたときの Admin API の扱い(認証の追加まで、破壊的操作が同じ公開範囲になる) | 別タスク(認証の設計) |
| BAPI-U-4 | `/`(ルート)と Search View の配置、`/admin/` 以外のフォールバック | Search View の設計 |
| BAPI-U-5 | Hey API 0.x の更新の影響、`throwOnError` と stale 表示の接続、生成コードのコミット方針 | E |
| BAPI-U-6 | スレッドの枯渇対策は C 8.1(`async def` + 区分別の上限。承認済みの案(ゲート3)。AAA-P-33)で決めた。区分別の上限(16・4・8。仮値)と、Crawler・OpenSearch のタイムアウトの実測 | 実装後の実測(CAPI-U-10。C の AAA-U-7) |
| BAPI-U-7 | セキュリティを有効にした OpenSearch での、読み取り専用の最小権限(`cluster_monitor`・`indices_monitor` 系。0004) | 実装時・運用 |
| BAPI-U-8 | **受け入れた未対応のリスク(ゲート3で受け入れを確認済み。2026-11-23)**: 認証なしの localhost 公開で、悪意あるウェブページからブラウザ経由で送られる書き込み要求への保護がない。ブラウザの単純なリクエスト(GET・HEAD・POST)で届くのは、本文なしの POST の EP-05(ソース削除ジョブ。全文書の削除)・EP-06(`force_delete` は既定 `false`)・EP-07(取消)。EP-04(PUT)・EP-08(DELETE)は preflight が要り CORS 未許可のため届かず、EP-08 は DNS rebinding でのみ到達しうる。DNS rebinding なら全 EP が対象。`Origin` 検査は、ゲート2の回答で採用が選ばれなかったため不採用として扱った(解釈)。ゲート3(2026-11-23)で、リスクは受け入れ(README に注意書き。HO-41)、軽い緩和(全 POST で `Content-Type` 必須など。要件にない追加)は足さないと明示回答があった。リスクはなくなっておらず、将来の認証導入時に再検討する(BAPI-U-3 と合わせる) | 認証の設計(別タスク) |

### 10.5 既存設計との不整合(I-n)

| ID | 内容 | 本書での扱い |
| --- | --- | --- |
| I-60 | SD §7.3「`api` は `indexer` に接続しない」と、Admin API が Indexer の `/healthz` を読むこと(BAPI-K-5) | 緩和を前提にする。SD は改訂せず、HO-1(9章)に「SD v0.9 での §7.3 改訂」を書いた |
| I-61 | crawler-api の CAPI-P-19・§4.7、indexer-api の §1(IA K67)は `/healthz` を「Admin API の契約外」とするが、Admin API はそれを読む | 2xx だけを判定し本文を解釈しない(P-5)。契約外であることは変えず、HO-8・HO-14 に位置づけの追記を書いた |
| I-62 | SD §14.4 は、重複起動の 409 を Admin API が通常は成功として扱う案とするが、本設計は成功扱いにせず 409 で返す(AAPI-P-35) | 逸脱として HO-4 に書いた(B 2.7) |
| I-63 | PD §3・§4 は Admin API の読み取りを Store 層に限る書き方だが、検索インデックス・OpenSearch のクラスタ情報も読む | 機能設計 6.1 で既出の PD 追従改訂の対象(HO-7) |
