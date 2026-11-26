# ui-admin フロントエンドアーキテクチャ設計書 v0.2

- 版: v0.2(ドラフト。v0.1 を書き直して再構成した。ゲート4・5(2026-11-26)の承認と、P7 のレビュー指摘(0011)への対応を反映済み。再レビュー済み(作業記録 0013)。実装はスコープ外で、実装時確認事項(FARC-U)と前提タスク(A・B+C)が残る)
- 更新日: 2026-11-26
- 前版: v0.1(`ui-admin-frontend-architecture-v0.1.md`。変更しない。承認済みの方針は中身を保って本書に引き継いだ)
- 位置づけ: Admin View(管理者向け Web UI)の**フロントエンドの技術構成**を定める。技術スタックとバージョン固定、ビルド・配信(`web` コンテナ(Nginx)での配信を含む)、アプリの組み立て(シェル・route `meta`・ガード)、データ取得層(型生成・API クライアント・TanStack Vue Query)、エラー処理の UI 対応、フォームと検証、状態管理、テスト方針、静的解析を書く。見た目・部品・画面ごとの仕様は DS と画面仕様、API の中身は A・B と**実装・OpenAPI**が正本で、本書は**参照して合わせる**。ディレクトリ・モジュール分割・画面×モジュールの対応は F(`ui-admin-frontend-module-structure-v0.2.md`)が正本。
- **本書だけで実装を始められる**ように書いた。v0.1 を読む必要はない(経緯・履歴は次節に要約した)。ただし、前提タスク A・B+C(本書 12.8)の完了に依存する箇所は、該当箇所に明記した。
- 本書は **Admin View のフロントエンド設計タスク(`20261126_create_admin_ui_system_design`)の成果物**で、SD・PD・DS・画面仕様・機能設計・A・B・C・D・crawler / indexer 設計を変更しない。既存設計と食い違う点・追従改訂が要る点は `I-n`(12.5)に挙げ、申し送りは A の 9章(HO)に集約する。A に追加した HO は 9.2.11 の HO-52〜68 で、本書の項目との対応は 12.8 にある。
- 出典の `0003`〜`0007`・`0012` は、本タスクの作業記録(`agent_tasks/20261126_create_admin_ui_system_design/`)の番号(0003 配信方式の変更の指示、0004 実 OpenAPI との照合・版確認、0005 技術検証、0006 変更点一覧、0007 ゲート4 の承認、0012 ゲート5 の承認)。他のタスクの記録は、タスク名を付けて書く(例: `implement_admin_api` の 0017)。

## 改訂履歴(v0.1 からの変更点)

v0.1(2026-11-23)は初版で、A・B 本文との照合、R1〜R4 のレビュー対応、ゲート3(2026-11-23)の承認を経た。v0.2 は、次の入力で v0.1 を直した。

- ユーザー指示(2026-11-26。0003): 静的コンテンツは `api` ではなく `web` コンテナ(Nginx)で配信し、Admin View から叩く API も Nginx 経由でプロキシする。要件 0000 の「API サーバーから静的配信する構成を基本とする」はこの指示で上書きされる。
- 実装済みの Admin API(14 EP)の OpenAPI との照合(0004)。**B と実装・OpenAPI が食い違うときは実装・OpenAPI が正**とし、B の差分は A 9章の HO で申し送る。
- 依存の版・Node 要件の再確認(0004)と、リポジトリ外の使い捨ての技術検証(0005): Hey API 0.99.0 による生成、Vite 8 + Vuetify 4.3.4 のビルド、Nginx 配信。
- ゲート4 の承認(2026-11-26。0007)と、ゲート5 の承認(2026-11-26。0012。G5-1=執筆中に決めた設計の詳細、G5-2=軽微な導出と誤記訂正、G5-3=レビュー対応で足した 3 案(`configureApiClient()` の冪等・依存ルール R17・R9/R16 の公開口統一))。

**1. 承認済みの方針の変更**(区分は、FARC-K-4 が確定(ユーザー指示)、他は承認済みの案(ゲート4。2026-11-26))

| ID | v0.1 | v0.2 | 章 |
| --- | --- | --- | --- |
| FARC-K-4 | Web UI は `api` が静的配信する | **`web` コンテナ(Nginx)が静的配信し、`/api/` を `api` へプロキシする**(ブラウザから見て同一オリジン。CORS 不要は維持) | 0・3.3・3.6 |
| FARC-P-2 | `app.frontend()` による配信。`/admin/` 配下だけ、`Accept: text/html` の GET/HEAD に `index.html` を返す | Nginx の `try_files`。`/admin/assets/` の欠落は 404、`/admin/` 配下のそれ以外の欠落ファイルは `index.html`(200)。`Accept` は見ない。`/admin` は 301、`/` は 302 `/admin/` | 3.2・3.3 |
| FARC-P-19 | 開発プロキシの `/api` の転送先は `127.0.0.1:8080`(`api`) | 転送先は compose の **`web` の公開ポート**(`api` は publish しない) | 3.4 |
| FARC-P-20 | Node ステージの成果物を `api` イメージへ | **`web` イメージ**(Node 24 でビルド → Nginx に `dist/` を載せる)。`api` イメージは Web に依存しない | 3.5 |
| FARC-P-30・4 | Vue Router 4 | **Vue Router 5.5.1**(`~5.5`) | 2.1・2.2 |
| FARC-P-3 | Node は 22.18 以上の 22 系・24 系・26 以上 | 下限を **`^22.22.2 \|\| ^24.15.0 \|\| >=26`** に引き上げ(jsdom 31 の要件)。推奨 24。`.nvmrc`・`engines`・`engine-strict=true` を置く | 2.1・2.2 |
| FARC-P-21 | jsdom は第一案 | **jsdom 31 を採用**(Node の下限と連動) | 2.1・10.1 |
| FARC-P-4 | 固定の範囲は方針のみ | 版と範囲を具体化(Vuetify・Hey API・Playwright は exact、Vite・`vue-tsc`・TypeScript・Vue Router は minor 固定など) | 2.1・2.2 |
| FARC-P-6 | OpenAPI JSON と生成コードをコミットし CI で再生成差分を検査 | 維持。生成は決定的(既定設定で同一入力 3 回と別ディレクトリの差分 0)で、`infiniteQueryOptions: false` なら 17 ファイル・約 111KB(既定は約 114KB)。コミットに問題がないと確認した | 5.2 |

**2. 新設した判断**(承認済みの案(ゲート4。2026-11-26)。FARC-P-44 の方式の細部は承認済みの案(ゲート5。2026-11-26。G5-1))

| ID | 内容 | 章 |
| --- | --- | --- |
| FARC-P-40 | Nginx の配信方針(`/admin/` のフォールバック・キャッシュ・リダイレクト) | 3.3 |
| FARC-P-41 | `/api/` のプロキシ(変数+`resolver`・タイムアウト・本文上限) | 3.3・3.6 |
| FARC-P-42 | 公開範囲: `web` だけを `127.0.0.1` に publish。`api` は publish しない | 3.6 |
| FARC-P-43 | Nginx 由来の失敗(502・503・504・413 の HTML)の扱い | 3.3・5.3・6.5 |
| FARC-P-44 | 実行時エラーの正規化層(生成クライアントが throw する値の形は型と食い違う) | 5.3 |
| FARC-P-45 | 生成設定とビルド設定(`vuetify/styles`・`sass`・`@types/node`・`exactOptionalPropertyTypes` を有効にしない など) | 3.1・5.2・11.1 |
| FARC-P-46 | DLG-4(再実行)で `force_delete`・`rewrite_mode` が null のときの扱い | 7.5 |
| FMOD-P-34・35 | F の `admin/api`(正規化・パス値検証)と、ルート直下の設定ファイルの追加。本書は参照のみ | 4.5・3.5 |

**3. 実装との照合による事実の訂正・拡張**(方針の変更ではない。ゲート4(G4-7)の承認と、ゲート5(G5-1・G5-2。0012)の承認・追認。0004)

- 最上位の `unavailable` が意味を持つのは EP-02・10・11 だけ(EP-01・09 の最上位は常に `{}`。EP-12・13・14 は持たない)。D1・O1 は `unavailable` を引かない(5.7・5.9)。
- S1 の `status`・`connector_type` は null になりうる。`status=null` の行は「削除中」の判定も操作も出さない(S2 の `status=null` も同じ)。EP-11 は行ごとの `expectedFields` を持つ。EP-12 の `cluster.status`・`shards[].role/state` は union+ガードで、未知値は中立表示(5.9)。EP-11 の `items`(4 型の `anyOf`)は、`documentTabs` の定義ごとに行の型とアダプタを持つ(F 3.5)。
- **EP-05 の 202 の直後に、S1 の行は「削除中」にならないことがある**(S2 のロック状態カードは即時 `held_delete`。5.8)。
- 本文の違反は 2 段階で返る。`invalid_request` で `details` がないのは想定外。`ttl_days` の排他・必須は TTL 欄に写す。添字なしの配列エラーは一覧の下、`connector_config` 単体は上部アラート(6.3・6.4)。
- `ttl_*` は null を送らずキーを省く(7.5)。DLG-4 の null は FARC-P-46。
- `stalled=true` かつ `lease_expires_at=null` は「期限を確認できません(期限切れ)」。EP-08 の `released=false` は成功文言にしない(5.10・6.5)。`existing_job` の `status`・`job_type` が null または未知の値のときは J2 へ導かない(6.3)。
- J1 の状態フィルタ `failed` にリース切れは含まれない。`deletion.fetched_at` は取得失敗時に取得時刻として出さない。Admin API は定義にないクエリ名を EP を問わず 400 `unknown_field` にし、EP-12・13・14 は query を一切受けないので付けない。`/meta` はクエリなし(5.3・5.7)。
- **パス値の送信前検証**: 生成 SDK は `.`・`..`・空文字を壊して別の EP へ送るため、**値全体が `.` または `..` に等しい、空、制御文字を 1 文字でも含む、文字列でない**値を拒否する(パスに入れる値すべて。`source_id`・`job_id` を含む。`my.source`・`a..b` のような正当な値は拒否しない。4.5・5.3)。
- `errorTable`(code は string)は手書きを正本とし、OpenAPI の description との契約テストを置く(10.1)。生成型は `{Op}Response2` を避けてスキーマ型を使う。`infiniteQueryOptions: false`。`SourceSettings` は 2 種類(5.2)。
- 軽微な追記(0004 の差分一覧): EP-01 は検索ベースで反映が遅れうる(5.4・5.8)、`last_completed_at`・`connector_type` は使わない(5.7)、小数桁の判定は `String(n)` に頼らない(7.7)、O1 の並びは API のまま使う。

**4. 構成の変更**

- v0.1 の章番号を保ち、節を足した: 3.3 を Nginx 配信に書き換え、3.6(`web` と `api` の関係)、12.7(実 OpenAPI との照合の要約・差分一覧)、12.8(前提タスク A・B+C と依存)を新設した。
- 経緯・履歴の記述(ゲートごとの区分の変遷、欠番の経緯、レビュー対応の記録、R1〜R4 への追従)は本文から外し、この節に要約した。ID は引き継ぎ、欠番(FARC-K-2・5〜8)は欠番のまま残した。
- 解消した FARC-U は削除せず、12.4 の状態欄に「解消(v0.2。根拠)」と書いた。
- 前提タスク(「前提タスク A・B・C」は文書 A・B・C・D とは別。12.8): **A**(OpenAPI の `ttl_*` の型・`openapi_export.py` の docstring)と **B+C**(`web` コンテナ・compose・`api` の `web` プローブの置換・結合テストの追従)。**A は型生成の前が望ましい(必須ではない。前でも `toRequest` が null を送らないので進められる)。B+C は `apps/web` の最初のスキャフォールドの後に着手し、`web` 経由の接続確認と初回リリースの前に完了させる**。詳細は 12.8。
- P7 のレビュー(0011)の指摘に対応した: 前提タスクの必要度の統一、パス値検証の対象、EP-11 の非 null 項目、確認範囲の限定(FARC-U-25・26 の追加)、12.8 に A の HO(HO-52〜68)の列、承認区分の整理(ゲート5)ほか。

## 0. この文書について

- 対象: `apps/web/` の Admin View(Vue 3 の SPA)。`web` コンテナ(Nginx)が `/admin/` 配下に静的に配信し、`/api/` を `api` コンテナへプロキシする(ブラウザから見て同一オリジン。FARC-K-4。`api` は静的ファイルを配信しない)。
- 範囲外(参照のみ): 見た目・部品・文言・レスポンシブ(DS・画面仕様)、エンドポイント・DTO・エラー code・環境変数(A・B・C と実装・OpenAPI)、ディレクトリ・モジュール分割(F)、Search View(配置の境界だけ。1章)、`web` の Dockerfile・Nginx 設定・compose の**実装**(前提タスク B+C。本書は方針と要求だけを書く)。
- 読み方: 1章で本書と他文書の分担、2〜3章で技術スタックとビルド・配信、4〜5章でアプリの組み立てとデータ取得、6〜7章でエラーとフォーム、8〜9章で状態管理と a11y、10〜11章でテストと静的解析、12章に確認状況(ID 付きの判断一覧・未確認・照合の要約・前提タスク)を置く。
- コード・設定ファイルは作らない。ファイル名・設定項目・型・Nginx の設定は「要点」「概形」として示す。
- 「確認(2026-11-26)」は、本タスクで実際に確かめた事実(出典は 0004・0005)。確認していない事実は、推測・実装時確認と書く。

区分の凡例(A 0章・B 0章と同じ。`crawler-api-v0.4.md` に合わせる):

| 区分 | 意味 |
| --- | --- |
| 確定 | ユーザーが明示的に回答・確定した事項(出典を書く)、または既承認文書(PD・SD・機能設計・DS・画面仕様・crawler / indexer 設計)の引用。FARC-K-4 は「確定(ユーザー指示 2026-11-26。0003)」 |
| 承認済みの案 | ユーザーが承認した設計の案。承認したゲートを書く。ゲート1(2026-11-22。方針)、ゲート2(2026-11-22。具体値・名前)、ゲート3(2026-11-23。v0.1 の案・導出・解釈の扱い)は v0.1 から引き継いだもの。**v0.2 で新規・変更した判断は「承認済みの案(ゲート4。2026-11-26)」**。ゲート4 の後に承認された設計の詳細と、軽微な導出・誤記訂正は「承認済みの案(ゲート5。2026-11-26)」(0012。G5-1=設計の詳細、G5-2=軽微な導出・誤記訂正の追認、G5-3=レビュー対応で足した 3 案)。既承認文書(DS・画面仕様など)の「承認済みの案」の引用で、本タスクのユーザー確認がないものも、確定にせずこの区分とし、出典を区分欄に書く。設計として承認済みだが、確定ではない。ID は `-P-` |
| 案 | まだユーザーが承認していない提案。確定(`-K-`)にしない。本書の本文に「案」と書いた判断は、v0.1 から引き継いだものは承認済みの案(ゲート3)に読み替える |
| 未決 | 決めていない。実装時に確認するものを含む |
| 推測 | 根拠が弱い想定 |
| 導出 | 他の記述から導いた事項 |

ID 体系: `FARC-K-n` / `FARC-P-n` / `FARC-U-n`(本書。欠番は欠番のまま残し、新規は続き番号)。既存設計との不整合は `I-n`(本書の予約範囲は I-80〜89 と I-120〜129。A は I-60〜69、B は I-70〜79、C は I-90〜99、F は I-100〜109 と I-130〜139、D は I-110〜119、既存設計は I-1〜52)。A の ID は `BAPI-*`、B は `AAPI-*`、F は `FMOD-*`。画面仕様の通し番号は `#n`(`admin-view-v0.1.md` 10.1)、機能設計は `AF-n`、DS・admin-view の節は `DS 4.5`・`admin-view 4.2` のように書く。エンドポイントは B の `EP-nn`。

関連文書(いずれも `docs/v0.x/` 配下):

| 略称 | 文書 | 本書との関係 |
| --- | --- | --- |
| DS | `ui-design/design-system-v0.1.md` | トークン・部品(4章)・シェル(5章)・テンプレート(6章)・a11y(8章)・`data-testid`(9章)・技術スタック(10章)の正本 |
| admin-view | `ui-design/admin-view-v0.1.md` | 画面一覧・route `meta`(4.2)・遷移・Admin API への申し送り(10.4) |
| 画面仕様 | `ui-design/admin/{dashboard,sources,jobs,documents,opensearch}-v0.1.md` | 画面ごとの状態・更新・エラー表示・データ項目 |
| 機能設計 | `system-design/ui-admin/ui-admin-functions-v0.1.md` | AF-1〜20 |
| A | `system-design/api/api-base-design-v0.1.md` | URL・エラー形式・OpenAPI・タイムアウトの正本。9章が申し送り(HO)の置き場。**静的配信を `api` が担う記述(2.1・2.2・BAPI-K-2・BAPI-P-2・BAPI-U-1・8章のビルド)は、本書の FARC-K-4(`web` が配信)に置き換わった**。A 本文は改訂せず、HO で申し送る |
| B | `system-design/api/admin/admin-api-v0.1.md` | EP・DTO・Admin 固有 code の正本。**実装・OpenAPI と食い違う箇所は実装・OpenAPI が正**(12.7)。B は改訂せず、HO で申し送る |
| C・D | `system-design/api/admin/admin-api-architecture-v0.1.md`、`admin-api-module-structure-v0.1.md` | Admin API の内部設計(導出・環境変数・モジュール構成)。本書は結果としての EP・code だけを使う。`web` の死活を `index.html` の存在で判定する前提(`web_dist.py`)は、前提タスク C で `HttpHealthCheck` に変わる(3.6)。B 8.1・10.2 の `web` の記述も同様に読み替える(HO で申し送る) |
| 実装・OpenAPI | `apps/api/`(OpenAPI は `uv run python -m loreley_api.admin.openapi_export <出力>` で書き出す) | EP・項目名・型・null 許容・列挙・code の最終的な正。照合の結果は 12.7 |
| F | `system-design/ui-admin/frontend/ui-admin-frontend-module-structure-v0.2.md` | ディレクトリ・モジュール・画面×モジュール |
| v0.1 | `ui-admin-frontend-architecture-v0.1.md`・`ui-admin-frontend-module-structure-v0.1.md` | 前版。変更しない。本書が置き換えるので、実装は本書と F v0.2 に従う |

---

## 1. 位置づけ

### 1.1 本書が決める範囲

| 事項 | 正本 | 本書での扱い |
| --- | --- | --- |
| 見た目・トークン・共通部品・シェル・テンプレート・状態表示・a11y・`data-testid` の命名 | DS | 参照のみ。Vuetify の設定値は DS 3章に従う |
| 画面一覧・route・`meta`・遷移、画面ごとの状態・更新間隔・文言 | admin-view、画面仕様 | 参照のみ。データ取得・エラーの方針を 5.7 に画面別にまとめる |
| URL 名前空間、エラー応答の形、OpenAPI の方針、タイムアウト | A | 参照のみ |
| エンドポイント・リクエスト・応答・Admin 固有 code | B と実装・OpenAPI(食い違うときは後者が正) | 参照のみ。EP 番号と code 名だけを引用し、内容は複製しない。実装との差は 12.7 |
| 静的配信の担い手(`web` コンテナ)と、Nginx の設定の方針・compose での位置 | **E(本書。3.3・3.6)** | 実装は前提タスク B+C。A 2.1・2.2 の「`api` が配信」は本書が置き換える |
| 技術スタックの版固定、ビルド、データ取得層、エラーの UI 対応、検証方針、テスト方針、静的解析 | **E(本書)** | — |
| ディレクトリ、モジュール分割、依存ルール、画面×モジュール対応 | F | 本書は制約だけを書く |

### 1.2 方針

- **DS・画面仕様と矛盾しない**。矛盾を見つけたときは、本文を DS・画面仕様に合わせ、`I-n` に挙げる(DS・画面仕様は変更しない)。
- **API は実装・OpenAPI が正**。B と食い違うときは実装・OpenAPI に合わせ、差を 12.7 に挙げる(B は変更しない)。
- **画面の文言は画面仕様が正**。本書は「どの `code` をどこに(どの variant で)出すか」だけを決める(6章)。
- **対応表は 1 か所に持つ**(DS 4.1・DS 12章と同じ考え方)。エラーの変換表、画面別の取得設定、URL クエリと API パラメータの対応を、それぞれ 1 つの表(データ)にし、画面ごとに分岐を散らさない。
- **サーバーの導出結果は画面で再計算しない**(`stalled`・`cancellable`・`rerunnable`・`lock_state`・`existence` など。B 2.9。画面は表示と操作の出し分けだけ)。導出フラグが `null` のとき(`stalled`・`rerunnable`・`latest_for_source`。ロック文書などを読めなかった。B 2.9・5.2)は**「不可」として扱う**: 取消・再実行の操作を出さない(B は `stalled=null` なら `cancellable=false`)。ジョブ記録の値が読めず `status=null` のジョブには、ステータスタグも操作も出さない(B 2.11。`stalled=false`・`cancellable=false`。FARC-P-36)。**S1 のデータソースの `status=null` の行も同様に、「削除中」の判定も操作も出さない**(FARC-P-36。5.9)。
- **Admin View は Admin API だけを呼ぶ**。Crawler・Indexer・OpenSearch に直接アクセスしない。ブラウザから見える接続先は `web` の同一オリジン(`/admin/` と `/api/`)だけで、外部 CDN など実行時の外部依存を持たない(FARC-K-9。3.1)。

### 1.3 Search View との境界

Search View は設計しない。本書の前提は「Admin View は `/admin/` 配下の 1 つの SPA(`base: '/admin/'`)」(BAPI-P-2)。**`web` コンテナ(Nginx)は将来、Search View も配信しうる**(Search View の置き場・同じビルドに同居させるか別の SPA にするかは未決。BAPI-U-4。FARC-U-17)。`web` の Nginx 設定は、Admin View について `/admin/` と `/api/` の location だけを決め、`/` の 302(`/admin/`)は Search View の置き場が決まるまでの暫定とする(3.3)。DS 11章のとおり、トークンと `defaults` は Admin・Search が共有する 1 組にするため、F はこれらを Admin 専用のコードと分けて置く。

---

## 2. 技術スタックとバージョン固定

### 2.1 構成(区分)

「確認版」は 2026-11-26 に確認した版(出典は 0004 の 4 章・0005。npm レジストリの package.json・公式ドキュメント・GitHub Releases による。主要な値は `npm view` と突き合わせた)。0005 の技術検証(P2-b)で `npm install`・`npm ci` とも peer・engines の警告・EBADENGINE・deprecated が 0 件、`npm audit` が 0 件だったのは、**Vite・Vuetify・`vite-plugin-vuetify`・`@vitejs/plugin-vue`・Vue Router・Vue・TypeScript・`vue-tsc`・`sass`・`@mdi/js`・`@types/node` を install した版**(上の表の確認版)の組み合わせだけ。**Vitest・jsdom・Playwright・ESLint・Prettier・`@vue/test-utils`・Hey API を Vite 系と同時に install した状態の `npm ci`・`npm audit` は未確認**(FARC-U-25)。

| 項目 | 採用 | 確認版 | 固定の範囲 | 区分 |
| --- | --- | --- | --- | --- |
| UI ライブラリ | Vuetify | 4.3.4(latest) | **exact pin** | 確定(DS 10.1 の引用。FARC-K-1) |
| 言語 | TypeScript | 6.0.3(6.1 なし。`latest` は 7.0.2) | `~6.0.3` | 6.x 固定=確定(DS 10.1 の引用。FARC-K-1)。`~6.0.3` は承認済みの案(ゲート4。FARC-P-4) |
| アイコン | `@mdi/js` + `vuetify/iconsets/mdi-svg` | 7.4.47 | caret + ロックファイル。**dependencies に明記** | 確定(DS 10.1 の引用。FARC-K-1)。社内ポリシー上の扱いは未確認(FARC-U-3) |
| ナビ | 自前(`VNavigationDrawer` + `VList` + route `meta`) | — | — | 確定(DS 10.1 の引用。FARC-K-1) |
| フレームワーク | Vue 3 | 3.5.46(3.6 は rc) | `^3.5`(Vuetify 4・Vue Router 5 の peer を満たす)+ ロックファイル | 承認済みの案(ゲート1。FARC-P-30) |
| ビルド | Vite + `@vitejs/plugin-vue` + `vite-plugin-vuetify`(tree-shaking・SASS 設定) | Vite 8.3.8、plugin-vue 6.0.11、`vite-plugin-vuetify` 2.1.3(2.2 なし) | Vite は **minor 固定**(`~8.3.8`)。plugin 2 つは確認版に固定(patch まで。`~`) | 承認済みの案(ゲート1。FARC-P-30)。範囲は承認済みの案(ゲート4。FARC-P-4)。`vite-plugin-vuetify` に Vite 8 の明示対応の記述がない点は FARC-U-20 |
| ルーター | **Vue Router 5** | 5.5.1(4.6.5 も保守) | **minor 固定**(`~5.5`) | 承認済みの案(ゲート4。2026-11-26。FARC-P-30・4。v0.1 は Vue Router 4) |
| データ取得 | `@tanstack/vue-query` v5 | 5.108.4 | caret(v5 系)+ ロックファイル | 承認済みの案(ゲート1。FARC-P-30) |
| 型・クライアント・Query 生成 | `@hey-api/openapi-ts` | 0.99.0(latest) | **exact pin**(0.x のため) | 承認済みの案(ゲート2。FARC-P-1。BAPI-P-10) |
| 型検査 | `vue-tsc` | 3.3.14 | **minor 固定**(`~3.3.14`) | 承認済みの案(ゲート3。FARC-P-4)。範囲は承認済みの案(ゲート4) |
| 単体テスト | Vitest + `@vue/test-utils` + **jsdom 31** | Vitest 5.1.2、jsdom 31.0.1 | caret + ロックファイル | Vitest は承認済みの案(ゲート1。FARC-P-30)。`@vue/test-utils` は案のまま(FARC-P-21)。**jsdom 31 は承認済みの案(ゲート4。2026-11-26。FARC-P-21)** |
| E2E | `@playwright/test` | 1.65.1 | **exact pin**(ブラウザの版と対にするため) | 承認済みの案(ゲート1。FARC-P-30)。exact は承認済みの案(ゲート3。FARC-P-4) |
| 静的解析 | ESLint(flat config)+ `typescript-eslint` + `eslint-plugin-vue`、Prettier | — | caret + ロックファイル | 承認済みの案(ゲート1。FARC-P-30)。構成は承認済みの案(ゲート3。FARC-P-23) |
| スタイル | `sass`(dart-sass。`vite-plugin-vuetify` の `styles.configFile`。DS 3.3) | 1.108.2 | caret + ロックファイル。**dependencies に明記**(`styles.configFile` を使うと必須。3.1) | 承認済みの案(ゲート4。FARC-P-45・4)。`sass-embedded` は不要 |
| Node の型 | `@types/node` | 24.19.4(検証時) | `^24`。devDependencies(導出)。`vite.config.ts` を型検査する場合に必要(3.1) | 承認済みの案(ゲート4。FARC-P-45・4) |
| パッケージ管理 | npm(`package-lock.json` をコミット。`npm ci`) | npm 11.6.2(検証時) | — | 承認済みの案(ゲート3。FARC-P-5) |
| ランタイム | Node.js **`^22.22.2 \|\| ^24.15.0 \|\| >=26`**。推奨は **24** | — | リポジトリに `.nvmrc`(推奨の 24 系)・`package.json` の `engines`(上の範囲)・`.npmrc` の `engine-strict=true` を置く。Docker のビルドステージと CI は **24.15.0 以上の 24 系**(`engine-strict=true` のため、24.15.0 未満だと `npm ci` が失敗する) | 承認済みの案(ゲート4。2026-11-26。FARC-P-3。v0.1 の下限は 22.18) |

### 2.2 固定の考え方

| 固定 | 対象 | 理由 |
| --- | --- | --- |
| exact | Vuetify、Hey API、Playwright | Vuetify 4 は新しく週次でリリースされ、DS 10.3 も exact pin・検証してから更新とする。Hey API は 0.x で、更新のたびに生成物が変わりうる。Playwright はブラウザバイナリの版と対になる |
| minor(`~`) | Vite、`vue-tsc`、TypeScript(`~6.0.3`)、Vue Router(`~5.5`)、`vite-plugin-vuetify`・`@vitejs/plugin-vue`(patch まで) | TypeScript の `latest` は 7.0.x だが、Vue の言語ツール(`vue-tsc`)は TypeScript 7 に**公式未対応**(公式ブログが Volar 系は 6.0 に留めると明言)で、`typescript-eslint` の peer も `<6.1.0`。6.0 に留める。Vite 8(Rolldown)と `vite-plugin-vuetify` は実機のビルドは通ったが明示対応の記述がなく(FARC-U-20)、minor を固定して検証してから上げる。Vue Router 5 は、ファイルベースルーティングを使わなければ非破壊とする公式の移行ガイドに従い、v0.1 の前提のコード(`createWebHistory`・`router-link`・`:to="{name}"`)が**無改変で動く**ことを確認した(2026-11-26。0005)。latest は 5.x で、4 は縮退していく(公式)ため 5 を採る |
| caret + ロックファイル | その他 | `package-lock.json` を正とし、更新は `npm update` を意図して行う |

- 依存の更新は、**再生成(`gen:api`)→ 型検査 → lint → Vitest → Playwright** を通してから行う(11.2)。
- **Node の下限**は、jsdom 30・31 の engines(`^22.22.2 || ^24.15.0 || >=26`)が最も厳しい(導出。ほかは Hey API `>=22.18`、Vite 8 `^20.19 || >=22.12`、Vitest 5 `^22.12 || ^24 || >=26`、Playwright は公式 docs が 22・24・26)。jsdom を 29(`^20.19 || ^22.13 || >=24`)や happy-dom に下げれば 22.18 を維持できたが、最新の jsdom を採る方を選んだ(承認済みの案(ゲート4))。
- Docker のビルドステージと CI の Node は、`engine-strict=true` により **24.15.0 以上の 24 系**にする(導出。範囲の `^24.15.0` のため)。
- **Node 25 は EOL(2026-06-01)**で、Vitest 5・Playwright の公式対象外であり、jsdom 31 の範囲にも入らない。LTS の状況(確認 2026-11-26): 22 は Maintenance(〜2027-04-30)、24 は Maintenance(〜2028-04-30)、26 は Active LTS(〜2029-04-30)。推奨は 24 に据え置き、26 への引き上げは CI で 26 を通してから行う。**開発者のローカルの Node が範囲外(例: 25)だと、`engine-strict=true` により `npm install` が失敗する**。`.nvmrc` の版に切り替える(導出)。
- Vuetify の公開パッケージに `engines` はなく、リポジトリ**ルート**の `engines.node >=24.11.1` は Vuetify の開発環境の要件で、利用側の要件ではない(確認 2026-11-26。0004。FARC-U-10 は解消)。

### 2.3 対応ブラウザ

Chromium 119+ / Firefox 128+ / Safari 16.4+(Vuetify 4 の要件。ユーザー了承済み。DS 10.1。FARC-K-3。Vuetify の公式 docs で裏取りした。2026-11-26)。

Vite 8 の既定の `build.target` は `baseline-widely-available`(chrome111・edge111・firefox114・safari16.4・ios16.4。`cssTarget` も同じ)で、Vuetify の下限より低いため、変換不足は生じない(確認 2026-11-26。0005)。成果物の CSS は `:has()`・`color-mix()`・`@layer`・`@property`・`dvh` を変換せずに使う。これらは Firefox 128+・Safari 16.4+ で動く範囲で、Firefox 114〜127 では動かないため、`target` を下げても意味がない。Firefox 128・Safari 16.4 の**実機**(コンテナクエリ・`<dialog>` まわり)は未確認(FARC-U-15)。自動 E2E は Chromium で行い(10.2)、他は実機で確認する。

### 2.4 入れないもの

Pinia、Tailwind、vue-i18n(日本語のみ。DS 10.1)は入れない(承認済みの案(ゲート3)。FARC-P-26)。次も、必要になるまで足さない(承認済みの案(ゲート3)。FARC-P-26): VueUse(DS 4.3 が「使うなら 10章の依存に足す」とする)、フォーム検証ライブラリ(7章)、日時ライブラリ(5.9)、axios などの HTTP クライアント(生成した fetch クライアントを使う。5.3)。`sass-embedded` も不要(dart-sass の `sass` で足りる。確認 2026-11-26)。

---

## 3. ビルド・配信

### 3.1 Vite の設定の要点(FARC-P-19・45)

| 項目 | 設定 | 理由 |
| --- | --- | --- |
| `base` | `'/admin/'` | Admin View は `/admin/` 配下(BAPI-P-2)。アセットの URL が `/admin/assets/…` になる(確認 2026-11-26。0005) |
| プラグイン | `@vitejs/plugin-vue`、`vite-plugin-vuetify`(`autoImport: true`。`styles: { configFile: … }` で SASS 変数を上書き。DS 3.3) | tree-shaking とフォント・影などの SASS 設定(DS 3.3)。この組み合わせで Vite 8 のビルドが通り、`styles.configFile` の変数が成果物の CSS と実機の `getComputedStyle` に反映されることを確認した(2026-11-26。0005)。ただし `vite-plugin-vuetify` に Vite 8 の明示対応の記述はない(FARC-U-20) |
| **`vuetify/styles`** | **`main.ts` で `import 'vuetify/styles'` する(必須)** | `vite-plugin-vuetify` はコンポーネント単位の CSS しか入れない。これがないと、リセット CSS・タイポグラフィ・ユーティリティ(`d-flex` など)が入らず、ブラウザ既定のフォント(Times)になる(確認 2026-11-26。0005)。`styles.configFile` の変数もここに効く |
| **`sass`** | dependencies に入れる | `styles.configFile` を使うと必須で、ないと `Preprocessor dependency "sass-embedded" not found` でビルドが失敗する(`styles: true` なら不要。確認 2026-11-26。0005)。DS は `configFile` を使う |
| **`@types/node`** | `^24` と、tsconfig の `types: ["node"]` | `vite.config.ts` を tsconfig の `include` に入れて `process.env`(開発プロキシの転送先。3.4)を使うとき必要。ないと `TS2591`(確認 2026-11-26。0005)。`vite.config.ts` を型検査しない場合は不要 |
| `build.target` | **既定のまま** | 既定は対応ブラウザの下限より低く、明示は不要(2.3) |
| `build.outDir` | `dist/`。**`index.html` を直下に置く** | `web` イメージが `dist/` をそのまま `/usr/share/nginx/html/admin` に載せる(3.5)。`index.html` が直下にあれば `/admin/` で配信できる。成果物は `dist/index.html`(約 0.4KB)と `dist/assets/index-<hash>.{js,css}`(確認 2026-11-26。0005) |
| 型検査 | `vite build` の前に `vue-tsc`。`exactOptionalPropertyTypes` は**有効にしない** | Vite は型を検査しない(11.2)。`exactOptionalPropertyTypes` を有効にすると、生成コードが通らない(生成コード内で 12 件のエラー。確認 2026-11-26。0005。5.2・11.1) |
| テスト | Vitest は同じ Vite 設定を共有 | 10.1 |
| 実行時の設定 | **持たない**(`VITE_*` を画面の挙動に使わない) | 同じ成果物をどの環境でも使えるようにする。環境で変わる値(cron のタイムゾーン、Dashboards の URL)は EP-14 `/meta` から取る(B 8.2。FARC-P-25) |

- `index.html` は `<html lang="ja">`(DS 8章)で、外部のフォント・CSS・スクリプトを読まない(外部フォント・CDN を使わない方針は FARC-K-9、外部通信の禁止全般は DS 3.1・FARC-P-32)。成果物に googleapis・gstatic・cdn・jsdelivr・unpkg・`@import url`・`url(http` が 0 件であることを確認した(2026-11-26。0005)。
- tree-shaking は効く(確認 2026-11-26。0005)。本 SPA に近い構成(VApp・VAppBar・VMain・VContainer・VBtn・VDataTable)で、JS 420KB(gzip 142KB)、CSS 311KB(gzip 44KB)。CSS の約 190KB は `vuetify/styles` の固定分(ユーティリティは tree-shaking されない)で、DS 10.1 の「フルビルド CSS 538KB・JS 735KB」と整合する。VDataTable を入れると JS が約 190KB、CSS が約 94KB 増える。

### 3.2 Router の `base` と URL

- `createWebHistory(import.meta.env.BASE_URL)`(= `/admin/`。FARC-P-2)。実 URL は `/admin/`・`/admin/sources`・`/admin/jobs/{jobId}` …。admin-view 4.2 の `path`(`/`・`/sources` …)は **Router の `base` からの相対**と読む(I-81)。
- `/admin/` 配下の未知のパスは、`web`(Nginx)が `index.html` を返し(3.3)、画面側の `not-found` route(admin-view 4.2。`/:pathMatch(.*)*`)が「ページが見つかりません」を描く。つまり**未知の `/admin/…` の HTTP ステータスは 200**(SPA)で、404 はクライアントで表す(導出)。Vue Router の公式も、この構成ではサーバーが 404 を返さなくなるため、アプリ内に catch-all の 404 route が要るとする。
- **`/admin/` 配下の `assets/` 以外の欠落ファイル**(`/admin/favicon.ico` など `dist/` にないもの)も、深い SPA パス(`/admin/sources/xxx`)と区別できないため、200 の `index.html` になる。**この挙動は許容する**(承認済みの案(ゲート4)。FARC-P-2・40。3.3)。実在させたいファイル(`favicon.ico` など)は `dist/` に含める。
- 同じ SPA 内のリンクは `router-link` / `router.push` を使い、`/admin/` を手で書かない(`base` の一元化)。

### 3.3 本番の配信(`web` コンテナ(Nginx)。FARC-P-2・40・41・43)

**配信の担い手**(確定(ユーザー指示 2026-11-26。0003)。FARC-K-4): `web` コンテナ(Nginx)が `dist/` を `/admin/` に静的配信し、`/api/` を `api` コンテナへリバースプロキシする。ブラウザから見て同一オリジンのままなので CORS は要らない。`api` は静的ファイルを配信しない(`app.frontend()` を使わない)。

以下は**設計の方針**で、設定ファイル(`apps/web/nginx/default.conf`。F 2.4。FMOD-P-35)の実装は前提タスク B+C。設定案は `nginx:alpine`(nginx/1.31.10)で `nginx -t` が通り、短時間のコンテナで curl と Chromium(playwright-cli)により挙動を確認した(**確認 2026-11-26。0005**)。**確認した範囲**と、**実装時に確認する範囲**(各表の注と下の「実装時確認」)を区別する。数値(タイムアウト・上限・ヘッダ)の**最終値は実装時確認**で、本書の値は仮値。

**(1) 配信と SPA のフォールバック(FARC-P-2・40)**

| 要求 | 方針 | 確認(2026-11-26。0005) |
| --- | --- | --- |
| `/admin/` と配下(`/admin/sources/xxx` など) | `try_files $uri /admin/index.html`+`Cache-Control: no-cache` | `/admin/` は 200 `text/html`・`no-cache`。深いパスは 200 で `index.html`(405 バイト)・`no-cache`。実機で `/admin/sources` の直開きで VDataTable が描画され、未知パスで SPA が起動した |
| `/admin/assets/`(ハッシュ付きの JS・CSS) | `try_files $uri =404`+`Cache-Control: public, max-age=31536000, immutable`。gzip | 200・`immutable`・`Content-Type` 正しい。JS の実転送は 165KB。**欠落(`/admin/assets/存在しない.js`)と `/admin/assets/` は 404**(`index.html` を返さない)。404 に `Cache-Control` は付かない(`add_header` に `always` を付けていないため) |
| `/admin`(末尾スラッシュなし) | 301 `/admin/`。`absolute_redirect off`(`Location` は相対) | 301 `Location: /admin/`。`absolute_redirect` を外すと、ポートのマッピング越しで壊れる |
| `/` | 302 `/admin/`(Search View の置き場が決まるまでの暫定。BAPI-U-4) | 302。書かないと既定の「Welcome to nginx」が出る |
| `/api`(末尾スラッシュなし) | 301 `/api/`(Nginx の既定の挙動) | 301 `/api/` |
| 上記以外(`/healthz` など) | location を置かない(404) | `/healthz` は 404(`api` の `/healthz` は Nginx から届かない) |
| `POST /admin/`、`GET /admin/../etc/passwd` | — | 405、404(`--path-as-is`) |

- **キャッシュの理由**: `index.html` は再検証(`no-cache`)、ハッシュ付きの `assets/` は長期キャッシュ。再配備で古いチャンクが消えると、開いたままのタブの動的 import が失敗するため、`index.html` を常に再検証する(Vite 公式の注意)。`assets/` の欠落を 404 にするのは、HTML が JS として読まれる紛らわしい失敗を避けるため(導出)。
- **`add_header` は子 location に継承されない**ため、`/admin/` と `/admin/assets/` の location ごとに `Cache-Control` を書く。`server` 以上には `Cache-Control` を置かない(確認 2026-11-26。0005)。セキュリティ関連ヘッダー(CSP など)を足す場合も location ごとに書く。足すか、`add_header ... always` を付けるかは実装時確認。
- **配置**: `dist/` を `/usr/share/nginx/html/admin/` に置き(3.5)、`root /usr/share/nginx/html` を使う。`alias` は使わない(検証した設定がそうだった)。gzip は `text/css`・`text/javascript`・`application/javascript`・`application/json`・`image/svg+xml` を対象にする(仮値。`gzip_min_length` も実装時確認)。
- **`/admin/` 配下の `assets/` 以外の欠落ファイルは 200 の `index.html`**(確認 2026-11-26。`/admin/favicon.ico` で確かめた)。深い SPA パスと区別できないため、**許容する**(承認済みの案(ゲート4)。FARC-P-2・40)。v0.1 の `app.frontend()` の「`Accept: text/html` の GET/HEAD だけ」とは異なり、Nginx は `Accept` を見ない。`/api/` は別 location なので、JSON を取る `/api/...` の誤りが `index.html` で隠れることはない。
- **ブラウザの暗黙の `/favicon.ico`**(`/admin/` の外)は 404 になり、コンソールにエラーが 1 件出る(確認 2026-11-26)。アイコンを `index.html` で明示するかは実装時確認。

**(2) `/api/` のプロキシ(FARC-P-41)**

| 項目 | 方針 | 理由・確認 |
| --- | --- | --- |
| 宛先 | `set $api_upstream http://api:8080;`+`proxy_pass $api_upstream;`+`resolver 127.0.0.11`(`valid=10s ipv6=off`。仮値) | `proxy_pass` にリテラルのホスト名を書くと、`api` 未起動の起動順で `host not found in upstream` により `nginx -t`・起動が失敗する。変数+`resolver`(Docker の内部 DNS)で、`api` が未起動でも nginx が起動する(確認 2026-11-26)。`resolver 127.0.0.11` は user-defined network でのみ有効(既定の bridge では 502)。compose のプロジェクトネットワークは user-defined |
| URI | `proxy_pass` に **URI 部を付けない**(元のリクエスト URI をそのまま渡す) | URI 部のない変数の `proxy_pass` は元の URI を渡すことを確認した。**`%2F`・`%2E` を含む実リクエスト(`job_id` のエンコード)での保持は未検証**(FARC-U-21。前提タスク B+C の実機確認) |
| キャッシュ | `proxy_cache` なし。upstream の `Cache-Control` を素通し。`/api/` に `add_header` を足さない | `api` が `/api/` に付ける `Cache-Control: no-store` が素通しされることを確認した(`/api/admin/v1/meta`) |
| `proxy_connect_timeout` | 数秒(仮値 5 秒) | 接続できないときに早く失敗させる |
| `proxy_read_timeout` | **90 秒以上**(仮値 90 秒。E 5.3 の書き込みタイムアウト以上) | `api` は Crawler を接続 3 秒+応答 60 秒(設定の上限は 600 秒)で待ち、書き込みは約 63 秒で JSON の 504 `crawler_response_lost`(`outcome_unknown=true`)を返す(0004)。Nginx の既定(公式ドキュメント上は 60 秒。本タスクでは未測定)のままだと先に切れて、結果不明を示す JSON が届かず HTML の 504 になる。`api` の Crawler 待ちの設定を上げたときは、これも追従が要る(導出)。`proxy_send_timeout` は仮値 30 秒 |
| `client_max_body_size` | `api` の本文上限(1 MiB)**より少し大きく**する(0004 の例は 2 MiB) | `api` は 1 MiB 超を JSON の 400 で返す(A 5.1)。Nginx の既定は公式ドキュメント上 1m(本タスクでは既定値のままの測定はしていない)で、1 MiB 超は **Nginx が HTML の 413** を返し、`api` の JSON が届かない。`client_max_body_size 1m` を明示した検証で、ちょうど 1 MiB は届き、+1 バイトで 413 になった(確認 2026-11-26。0005)。判定を `api` に任せる(承認済みの案(ゲート4。G4-5))。大きくした値で `api` の JSON 400 が返ることの確認は実装時 |
| ヘッダ | `proxy_http_version 1.1`、`Connection ""`、`Host`、`X-Real-IP`、`X-Forwarded-For`、`X-Forwarded-Proto` | `Host` を `$host` にするとポートが落ち、`$http_host` ならポート付き(どちらにするかは実装時確認)。`X-Forwarded-For` はクライアント指定値の後ろに追記される(認証なしの内部用のため問題としない。確認 2026-11-26) |
| エラー応答 | **`error_page` で JSON を返さない** | 502・503・504・413 は Nginx の HTML のまま、フロントが扱う(承認済みの案(ゲート4。G4-5)。下の(3)) |

実機の確認(2026-11-26。0005): `/api/admin/v1/meta` が upstream の 200・`application/json`・`Cache-Control: no-store` で素通しされ、Dashboard のボタンでプロキシ越しに 200 を得た。upstream 停止(接続拒否)は HTML の 504(環境により 502)。ただし、これは**ダミーの upstream**での確認で、**実際の `api` との結合**(compose の `web`)は前提タスク B+C の後に確認する(FARC-U-6)。

**(3) Nginx 由来の失敗(FARC-P-43。承認済みの案(ゲート4))**: 502・503・504・413 は HTML のため、`ApiError.kind='invalid_response'` になる(5.3)。**読み取り**(`invalid_response` は 502・503・504 のとき)は 1 回だけ再試行してエラーブロックにする。**書き込み(EP-03〜08)の 502・504・`invalid_response`・通信断は結果不明**(`api` が Crawler を呼んだ後かもしれない)で、再試行を出さず確認を促す(FARC-P-15 の拡張。6.5)。ただし保存系(EP-03・04)は、再送が安全なため再保存を出してよい(例外を維持)。

**(4) `web` がないとき・古いタブ(B 10.2 が E に委ねた点)**: `web` コンテナが動いていない、または `index.html` が配信できなければ SPA が起動せず、Admin View は開けない(`api` だけが動く。画面側から表示できるものはない。`api` はホストに公開しないため、運用は `docker compose ps`・`docker compose logs web api` で確認する。`api` の `/healthz` を直接確認するときは、`docker compose exec` でコンテナ内から行う。手順は前提タスク B+C の README に書く(A の HO-54)。PR #21 のレビュー指摘への対応。ユーザー指示 2026-11-26)。すでに開いているタブでは、`api` が `web` へ HTTP で確認した結果として D1 に `web` の異常が出る(前提タスク C。3.6)。再配備でハッシュ付きのアセットが入れ替わった後に、開いたままのタブが旧アセットを取りに行って失敗する場合(ルートごとの遅延読み込みを使うときだけ。使うかは F と実測で決める)は、`assets/` の欠落が 404 になるので、`router.onError` で「画面を再読み込みしてください」とアラートを出す(承認済みの案(ゲート3)。FARC-P-18)。

**実装時確認(前提タスク B+C。FARC-U-6)**: `proxy_read_timeout`・`client_max_body_size`・`proxy_connect_timeout` ほか数値の最終値、`Host` を `$host` か `$http_host` にするか、`add_header ... always` とセキュリティヘッダー(CSP など)、404 に `Cache-Control` を付けるか、`/` の扱い(BAPI-U-4)、`web` のヘルスチェックの手段(3.6)、`%2F`・`%2E` の素通し(FARC-U-21)、実際の `api` との結合。

### 3.4 開発サーバー(FARC-P-19)

- `vite`(5173 は Vite の既定のポート)を `base: '/admin/'` で起動し、`http://localhost:5173/admin/` を開く(確認 2026-11-26。0005)。dev サーバーは `localhost`(`::1` を含む)で待ち受け、`127.0.0.1` 指定の curl は接続できない。**`/admin`(末尾スラッシュなし)は dev では 404**(本番は Nginx が 301 にする)。
- `server.proxy` で `/api` を、**compose で起動した `web` の公開ポート**(`http://127.0.0.1:<WEB_HOST_PORT>`)に転送する(承認済みの案(ゲート4。2026-11-26。G4-2。FARC-P-19 の変更)。v0.1 は `api` の `127.0.0.1:8080`)。`api` は compose でホストに publish しないため、dev サーバーは `api` に直接つながらない(3.6)。ブラウザから見て同一オリジンのままなので、CORS は要らない(FARC-K-4)。
- 転送先は dev 専用の環境変数で上書きできるようにする(名前は実装で決める。0005 の検証では環境変数で上書きできた)。**前提タスク B+C の完了前、または `web` を起動しない場合**は、この変数で転送先を変える(例: `api` を自分で publish する compose の上書き。結合テストの `compose.test.yaml` と同じ流儀)。
- つまり開発は、「`web`・`api`・OpenSearch・Crawler・Indexer を compose で起動し、Vite の dev サーバー(HMR は Vite が持つ。ブラウザは 5173 を開く)から `web` 経由で `api` を使う」。`web` に載るのは本番ビルドの `dist/` で、開発中の画面は dev サーバーが配信する。dev サーバー → `web` → `api` の連鎖の実機確認は、前提タスク B+C の後(0005 は Vite → ダミーの upstream と、Nginx → ダミーの upstream を別々に確認した)。
- 型生成は開発サーバーにも `api` の起動にも依存しない(5.2)。OpenAPI の実行時公開(`LORELEY_API_OPENAPI_ENABLED`)も要らない。

### 3.5 Docker のビルド(`web` イメージ。FARC-P-20。前提タスク B+C の完了後に有効)

`web` は `apps/web/` 自身の Dockerfile(`apps/web/Dockerfile`。F 2.4。FMOD-P-35)でビルドする。`api` イメージは Web に依存しない(Node のステージを持たない)。本書の要求:

- **ビルドコンテキスト**: compose の `web` サービスは `build: ../../apps/web`(コンテキスト=アプリのディレクトリ)。既存の `crawler`・`indexer` と同じ流儀で、v0.1 の「`apps/api` を文脈にすると `apps/web` が見えない」問題(旧 I-82)は消える(承認済みの案(ゲート4。0003))。A の HO-36・37(「`api` の Dockerfile に Node ステージ」)は読み替えになる(A 9章の HO-36・37 に注記があり、HO-53 で申し送る。本書は A を変更しない)。
- **Node ビルドステージ**: ベースは Node 24.15.0 以上の 24 系(`engine-strict=true` のため。タグ + ダイジェストで固定。Indexer の Dockerfile と同じ流儀。実際のタグ・ダイジェストは前提タスク B で決める。FARC-U-11)。`package.json`・`package-lock.json`・`.npmrc` を先にコピーして `npm ci`(依存の層をキャッシュ。`engine-strict=true` も効かせる)→ ソースをコピー → `vue-tsc` と `vite build`。
- **配信ステージ**: Nginx のイメージ(タグ + ダイジェストで固定。検証は `nginx:alpine`。実際のタグは前提タスク B)に、`COPY dist /usr/share/nginx/html/admin` と `nginx/default.conf`(`/etc/nginx/conf.d/default.conf`)を載せる(3.3 の検証と同じ配置)。
- **ビルドステージで型生成はしない**(生成には Python 側の `app.openapi()` が要るため)。生成コードと書き出した OpenAPI JSON はリポジトリに置く(5.2。FARC-P-6)。
- **外部への依存**: ビルド時に npm レジストリへ接続するが、成果物は外部 CDN・外部フォントを参照しない(3.1)。実行時(`web`)は外部通信をしない。

### 3.6 `web` と `api` の関係(FARC-P-41・42。前提タスク B+C の完了後に有効)

| 項目 | 方針 |
| --- | --- |
| compose 上の位置 | `web` は `api` などと同じ compose のサービス(`build: ../../apps/web`)。同じプロジェクトネットワーク(user-defined)に属し、`api` へは**サービス名とコンテナ内のポート**(`api:8080`)で到達する |
| 公開範囲(FARC-P-42。承認済みの案(ゲート4。2026-11-26。G4-2)) | **`web` だけを `127.0.0.1` に publish する**(コンテナ内は 80。ホスト側は `WEB_HOST_PORT`。既定値は 8080・8000・8001・9200 と重ならない値で、実装時に決める)。**`api` は compose の `ports` を持たず、内部ネットワークのサービス名(`api:8080`)だけで到達できる**。ブラウザ・開発・結合テストのすべてが `web` 経由、または自前の上書きで接続する。認証なしの破壊的操作の入口が 1 つになる。`/api/` をプロキシするので、`web` の公開範囲に認証なしの破壊的操作が出るため、HO-40・41 の注意書きは `web` に対して適用する |
| `api` の publish の扱い | 本番用の `compose.yaml` から `api` の `ports`(現状 `127.0.0.1:${API_HOST_PORT:-8080}:8080`)を外す。`API_HOST_PORT` は本番用では不要になる。結合テスト(`tests/integration/api/support.py`・`scripts/run-api-integration-test.sh`)は `127.0.0.1:8080` の `api` を直接呼ぶため、**結合テスト用の上書き `compose.test.yaml` が `api` を `127.0.0.1:8080` に publish する**(Crawler と同じく診断・テスト用の上書き。本番用の `compose.yaml` には書かない)。`compose.yaml` 冒頭の「公開範囲」の注意書きと `deploy/compose/README.md`・`apps/api/README.md` の更新も要る(いずれも前提タスク B+C) |
| 起動順 | `web` は `depends_on: api`(`service_healthy`)。`api` 側の `/healthz` は `dist/` に依存しない(確認 2026-11-26。0004)。`api` は `web` を `depends_on` に入れない(`web` の死活は `api` が実行時に確認するもので、起動順に使わない。導出)。nginx 自体は、変数+`resolver` により `api` が未起動でも起動できる(3.3) |
| `web` のヘルスチェック | 手段は**実装時確認**(`curl`・`wget` の有無に頼るか、専用の `/healthz` の location を置くか。現状の設定案では `/healthz` は 404。3.3) |
| D1 の `web` の判定(前提タスク C) | EP-13 の `web` は現状、`api` が `LORELEY_API_WEB_DIST_DIR/index.html` を読めるかで判定する(`web_dist.py`)。`web` が別コンテナになると、何もしなければ全環境で `web` が異常(`missing`)になり、D1 が常に「異常あり」になる。**`api` が `HttpHealthCheck` で `web` の URL(0004 の例は `LORELEY_API_WEB_URL`)を確認する方式に置き換える**(承認済みの案(ゲート4。G4-4)。`ComponentId`・`reason` の OpenAPI は不変)。環境変数名・確認先は前提タスク C で決める。**B と C は同時に完了させる**(B だけでは D1 の `web` が壊れる)。B の公開前に必須 |
| Search View との関係 | 将来、同じ `web` が Search View も配信しうる(1.3)。本タスクは設計しない |

**この章が依存する前提タスク**: 3.3(Nginx 設定の実装)・3.4(既定の転送先)・3.5・3.6 は **B+C** の完了後に有効。**A** には依存しない(A は型生成。5.2)。実装の着手は、dev サーバーの転送先を上書きすれば B+C の前でも始められる(3.4)。詳細は 12.8。

---

## 4. アプリ構成

(`web` コンテナでの配信に変わっても、アプリの組み立ては v0.1 から変わらない。ここでは、`web` 前提と実測に合わせて記述を整えた。)

### 4.1 起動の組み立て

`main.ts` は次の順に組み立てる(Pinia はない。FARC-P-17)。

0. API クライアントの設定: **`configureApiClient()` を呼ぶ**(5.3。1〜4 より前。呼び出しは `main.ts` の 1 か所。関数は冪等で、2 回目以降は何もしない(冪等にする点は承認済みの案(ゲート5。G5-3。2026-11-26))。F 3.3)
1. Vuetify: **`import 'vuetify/styles'`(必須。3.1)**。`createVuetify`(`theme.defaultTheme: 'light'` と色・variables(DS 3.1)、`defaults`(DS 3.2)、`display.mobileBreakpoint: 'md'`(DS 3.1・7。公式ソースの読解による設定で、実機 4.3.4 で要確認。FARC-U-14)、アイコン `mdi-svg`)
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

- route の一覧(`name`・`path`・`title`・`template`・`parent`・`nav`)は **admin-view 4.2 の表をそのまま実装**する(D1 `dashboard`、S1 `sources`、S3 `source-new`、S2 `source-detail`、S4 `source-edit`、J1 `jobs`、J2 `job-detail`、X1 `documents`、O1 `opensearch`、`not-found`)。`/sources/new` を `/sources/:sourceId` より先に定義する。
- `:sourceId`・`:jobId` は URL エンコードする(`job_id` は `%`・`?`・`#` などを含みうるため。B 2.12)。**生成 SDK がパスの値を送るときのエンコードは確認した**(2026-11-26。0005): `encodeURIComponent` で、`a%b?c#d`・`a/b`・日本語は正しく送られる。ただし `.`・`..`・空文字は SDK が壊して別の EP へ送る(`.` は一覧の EP、`..` は 1 階層上)ため、**送信前に検証する**(5.3・4.5。FMOD-P-34・F 3.3)。Nginx を越えた `%2F`・`%2E` の保持は未検証(FARC-U-21。3.3)。
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
| URL の ID・クエリの不正値 | **ID の形式はクライアントで検証しない**(サーバーの 400 `invalid_request`、`/` を含む ID の 404 `not_found` を「見つかりません」と同じに扱う。6.2。B 2.12)。**例外(パス値の送信前検証。5.3。FMOD-P-4・34。承認済みの案(ゲート4))**: 値全体が `.` または `..` に等しい、空、制御文字を 1 文字でも含む、文字列でないパス値(`source_id`・`job_id` をはじめ、パスに入れる値すべて。`my.source` のように `.` を含むだけの値は対象外)は、生成 SDK が URL を壊して別の EP を呼ぶ(5.3)ため、**API を呼ばず**「見つかりません」と同じに扱う(検証は `admin/api` に置く。F 3.3)。クエリ(`page`・`size`・`sort`・`tab`・`status` など)の不正値は、既定値に正規化して `replace` する(5.6) |

---

## 5. データ取得層

### 5.1 全体の流れ(FARC-P-1・44)

```text
ブラウザ ─ /api/admin/v1/… ─▶ web(Nginx。3.3) ─▶ api(Admin API。FastAPI サブアプリ。A 5.4)

Admin API の OpenAPI(openapi_export.py がファイルに書き出す。サーバー起動不要)
  └ openapi/admin-v1.json(コミット)
        └ Hey API(openapi-ts 0.99.0) ─▶ generated/(型・SDK 関数・Query 用 xxxOptions / xxxMutation。コミット)
              └ API クライアントの設定(5.3): タイムアウト付き fetch・request interceptor(パス値の検証)
                    ・error interceptor(ApiError への正規化)。baseUrl は生成物が持つ
                    └ queries(5.4): ドメインの key factory で生成 Options の key を差し替える
                          └ 画面。失敗は変換表(6章)で表示先を決める
```

- 画面のコードは URL を組み立てない。生成された SDK の関数と `xxxOptions` / `xxxMutation` だけを通す。
- 本章は、生成物の使い方・API クライアントの設定・Query の既定値と key・画面ごとの取得と更新を決める。失敗の表示は 6 章。

### 5.2 型生成(承認済みの案(ゲート2・3・4。2026-11-26)。FARC-P-1・6・45。BAPI-P-10)

**入力**: `uv run python -m loreley_api.admin.openapi_export <出力パス>`(実行場所は `apps/api` の環境。実装時確認)で書き出した JSON。サーバー・OpenSearch・Crawler に接続せず、`LORELEY_API_OPENAPI_ENABLED` にも依存しない。出力はキー順とインデントが固定で決定的(確認 2026-11-26。0004)。置き場は `openapi/admin-v1.json`(F 2.4)。確認した OpenAPI は 3.1.0・12 パス・14 EP・`servers=[{url:/api/admin/v1}]`・`paths` は相対(基準 SHA `6a8b685`。sha256 `ce60fc1a…bf51`。0004)。

**生成設定**(FARC-P-45。`openapi-ts.config.ts`。出力先は F 3.3 の `generated/`):

| plugin | 設定 | 理由 |
| --- | --- | --- |
| `@hey-api/client-fetch` | 既定 | fetch ベースのクライアントを生成物に同梱する(axios などは足さない。2.4) |
| `@hey-api/typescript` | 既定 | DTO・エラー・列挙(union 型)の型 |
| `@hey-api/sdk` | 既定 | SDK 関数(14 EP に 1 つずつ) |
| `@tanstack/vue-query` | **`infiniteQueryOptions: false`** | 既定だと `page` を持つ EP-09・11 に `*InfiniteOptions` が出て、内部に `@ts-ignore`・`as any` を含む。MVP は通常のページ送り(5.6)で使わない。`false` で `vue-query.gen.ts` が 375 行から 286 行になる(確認 2026-11-26。0005) |

**生成物の構成**(確認 2026-11-26。0005。`infiniteQueryOptions: false` でスクラッチに再生成し、17 ファイル・約 4,260 行・約 111KB(`@tanstack/vue-query.gen.ts` は約 286 行)。既定設定では 4,349 行・約 114KB(同ファイルは 375 行)。決定性の確認は既定設定で行った):

| ファイル | 内容 |
| --- | --- |
| `index.ts` | 再 export |
| `client.gen.ts` | クライアント `client`。`createClient(createConfig({ baseUrl: '/api/admin/v1' }))`。`baseUrl` は spec の `servers[0].url` から**自動で入る** |
| `sdk.gen.ts` | SDK 関数 14 個。operationId の camelCase |
| `types.gen.ts` | DTO・エラー・列挙。`{Op}Data`・`{Op}Responses`・`{Op}Errors`・`{Op}Response`・`{Op}Error` |
| `@tanstack/vue-query.gen.ts` | GET は `{fn}Options`・`{fn}QueryKey`、POST・PUT・DELETE は `{fn}Mutation` |
| `client/`(4)・`core/`(8) | 実行時(fetch クライアント・シリアライザ)。`client/` の `interceptors` を 5.3 で使う |

**EP と生成された名前の対応**(確認 2026-11-26。0005。F 4章・本書 5.7・5.8 はこの名前で書く):

| EP | メソッドとパス | SDK 関数 | Query 用 | 備考 |
| --- | --- | --- | --- | --- |
| EP-01 | `GET /sources` | `listSources` | `listSourcesOptions` | |
| EP-02 | `GET /sources/{source_id}` | `getSource` | `getSourceOptions` | 応答は `SourceDetailResponse`(null 許容。下の 2) |
| EP-03 | `POST /sources` | `registerSource` | `registerSourceMutation` | 200・201 とも `SourceSettings`(`RegisterSourceResponses` は `{200, 201}` の union) |
| EP-04 | `PUT /sources/{source_id}` | `updateSource` | `updateSourceMutation` | |
| EP-05 | `POST /sources/{source_id}/delete-jobs` | `startSourceDelete` | `startSourceDeleteMutation` | 本文なし。202 `JobAccepted`(スナックバーの `job_id` と J2 への遷移に使う。`status`・`job_type` を前提にした分岐はしない) |
| EP-06 | `POST /sources/{source_id}/crawl-jobs` | `startCrawl` | `startCrawlMutation` | 本文 `StartCrawlBody`(`force_delete`・`rewrite_mode`)。SDK が `Content-Type: application/json` を付ける。202 `JobAccepted`(EP-05 と同じ扱い) |
| EP-07 | `POST /jobs/{job_id}/cancel` | `cancelJob` | `cancelJobMutation` | 応答の型が `CancelJobResponse2`(下の 1) |
| EP-08 | `DELETE /sources/{source_id}/lock` | `releaseLock` | `releaseLockMutation` | 応答の型が `ReleaseLockResponse2`(下の 1) |
| EP-09 | `GET /jobs` | `listJobs` | `listJobsOptions` | |
| EP-10 | `GET /jobs/{job_id}` | `getJob` | `getJobOptions` | |
| EP-11 | `GET /sources/{source_id}/documents` | `listDocuments` | `listDocumentsOptions` | `tab` が必須 |
| EP-12 | `GET /opensearch/cluster` | `getCluster` | `getClusterOptions` | 引数なし(query を付けない。5.3) |
| EP-13 | `GET /dashboard` | `getDashboard` | `getDashboardOptions` | 同上 |
| EP-14 | `GET /meta` | `getMeta` | `getMetaOptions` | 同上 |

**型の使い方の規則**:

1. **`{Op}Response2` を使わない**(確認 2026-11-26。0005): スキーマ `CancelJobResponse`・`ReleaseLockResponse` と EP 側の `{Op}Response` が同名になり、EP 側が `CancelJobResponse2`・`ReleaseLockResponse2` になる。手書きのコードは、**スキーマ名の型**(`CancelJobResponse`・`ReleaseLockResponse`・`SourceSettings` …)を import し、`{Op}Response`・`{Op}Response2` を使わない。生成の命名が変わっても影響を受けない。
2. **`SourceSettings` が 2 種類**(S-D3。確認 2026-11-26。0004): EP-02 の応答は `SourceDetailResponse`(`connector_config`・`connector_type`・`status`・`min_delete_count`・`ratio_threshold_percent`・`ttl_days`・`ttl_seconds`・`updated_at` が null 許容。保存値が読めないとき `malformed` で null になる)、EP-03・04 の応答は厳格な `SourceSettings`(`status`・`ttl_seconds`・`updated_at` などが非 null)。B 2.11 は共通と書くが、実装は 2 種類で、**実装が正**(HO で申し送る)。フォームの初期化(S4)は前者を読む。
3. **`ttl_days`・`ttl_seconds` の型**(S-D1。確認 2026-11-26。0004・0005): `RegisterSourceBody`・`UpdateSourceBody` では、どちらも `integer | null`・省略可(既定 null)。実行時は明示的な null を 400 `type` で拒否し、「どちらか一方が必須」は OpenAPI に出ない。型どおりに作ると null を送れてしまうため、**null を送らずキーを省く**(7.5)。**前提タスク A**(「任意かつ非 null」に直す)の完了前も後も、同じコードで動く(A の後は再生成で型が `ttl_days?: number` になるだけ)。
4. **型で守られないもの**(確認 2026-11-26。0004): 日時は `format` のない string(UTC・ミリ秒・`Z`。5.9)。`ErrorBody.code` は **string**(列挙でない。どの code が返るかは `{Op}Errors` の JSDoc にしか出ない)で、`details` は全キー任意の 1 型。このため `errorTable` は手書きを正本とする(6.1・10.1)。EP-09 の `sort` は素の string(許容は `queued_at`・`-queued_at`)、EP-11 の `items` は判別子のない 4 型の `anyOf`、`warnings[]` の要素は `{[k: string]: unknown}`、EP-12 の `cluster.status`・`indices[].status`・`shards[].role/state` は string。これらは画面側で union とガードを 1 か所に定義する(F 3.5。5.7・5.9)。`page × items_per_page ≤ 10,000`・ID の形式は OpenAPI に出ず、実行時の 400 で返る(5.6)。
5. **`exactOptionalPropertyTypes` を有効にしない**(FARC-P-45。確認 2026-11-26。0005): 有効にすると生成コード内で 12 件の型エラー(TS2379)と、`@tanstack/vue-query` の d.ts のエラーが出る。`strict`・`noUncheckedIndexedAccess`・`noUnusedLocals` などは通る。省略可のキーは、条件付きの展開で省く書き方にする(7.5)。

**運用**(FARC-P-6。維持。承認済みの案(ゲート3。2026-11-23)。ゲート4 でコミット方針の維持を承認):

- 書き出した OpenAPI JSON と生成コードを**リポジトリにコミット**する。生成は決定的(同一入力 3 回と別ディレクトリで差分 0。既定設定での確認。タイムスタンプ・絶対パスの埋め込みなし)で、量は `infiniteQueryOptions: false` で 17 ファイル・約 111KB のため、仕様が変わるとき以外にノイズは出ない(確認 2026-11-26。0005)。Docker の Node ステージが Python に依存しない(3.5)。
- 生成コードは手で編集せず、**lint・format の対象から外す**(4 スペース・クォート混在。11.1)。
- **CI は再生成して差分がないこと**を確認する(`gen:api` → `git diff --exit-code`。11.2)。`gen:api` は「OpenAPI の書き出し → `openapi-ts`」の 2 段。
- **更新手順**: Hey API を上げる、または Admin API の定義が変わったら、再生成 → 差分確認 → 型検査 → テスト。API の変更は、生成型を使うモック(10.2)の `satisfies` で型エラーとして現れる。
- **前提タスク A への依存**: `ttl_*` の型の修正と、`openapi_export.py` の docstring(現状は「リポジトリにコミットしない」と書いており、本書の方針と逆)の修正は A の作業。**型生成の前に A の完了が望ましい**が、`ttl_*` は上の 3 のとおり A の前でも動くので必須ではない(12.8)。

### 5.3 API クライアント(承認済みの案(ゲート3・4・5)。FARC-P-7・44)

生成された fetch クライアント(`client.gen.ts` の `client`)を**1 つだけ**使い、薄い設定関数 1 つ(`configureApiClient`。名前と置き場は F 3.3 の `client.ts`)で設定する。EP 単位の `client` の差し替えはしない。

| 項目 | 方針 |
| --- | --- |
| `baseUrl` | **設定しない**。生成物が spec の `servers[0].url`(`/api/admin/v1`)から入れる(確認 2026-11-26。0005)。v0.1 の「`baseUrl` を設定する 1 か所」は「生成物が持つ 1 か所」になった。`servers` が変われば再生成で追従する。単体テストで `client.getConfig().baseUrl` が `/api/admin/v1` であることを確認する(10.1。導出)。同一オリジンで、認証情報・CORS の設定は不要 |
| `throwOnError` | クライアントの既定は `false` のまま。**生成された `queryFn`・`mutationFn` が内部で `throwOnError: true` を渡して失敗を例外にし**、TanStack Query の `error` に載せる(確認 2026-11-26。0005)。SDK 関数を画面・composable から直接呼ばない(Query・mutation 経由だけ) |
| fetch | `setConfig({ fetch })` に、**タイムアウト付きの fetch**を渡す(下の「タイムアウト」) |
| `interceptors.request` | パス値の送信前検証(下) |
| `interceptors.error` | 実行時エラーの `ApiError` への正規化(下) |
| query | Admin API は**定義にないクエリ名を EP を問わず 400 `unknown_field`** にする(X-BD4。確認 2026-11-26。0004)。**EP-12・13・14 は query を一切受けない**ので付けない(`getClusterOptions()`・`getDashboardOptions()`・`getMetaOptions()` は引数なしで呼ぶ。cache-busting 用の `_=` なども足さない。B 8.1・8.2 の「エラーなし」とは異なる。実装が正)。URL の名前(`size`・`source`)は API の名前(`items_per_page`・`source_id`)に写してから渡し、O1 の `q`・`state` は画面側の絞り込みで API に渡さない(5.6)。EP-12・13・14 の URL にクエリが付かないことをテストで確認する(10.1) |
| 再送 | クライアントは**自動再送しない**(Query の再試行だけ。5.4)。書き込みは再送しない(A 5.6・作業プラン P-5) |
| 通知 | クライアントは通知を出さない(通知は画面が決める。6.6) |

**起動時の設定(4.1 の補足)**: `configureApiClient()` は `main.ts` で**1 回だけ**呼び、4.1 の 1〜4 より前に置く(最初のリクエストはマウント後の Query の取得なので、マウント(4.1 の 4)より前であればよい)。関数は冪等(2 回目以降は何もしない。interceptor が二重に登録されない。F 3.3。承認済みの案(ゲート5。G5-3。2026-11-26))にするが、呼び出しは 1 か所にする。単体テストの setup も同じ関数を呼ぶ(E2E は実アプリの `main.ts` が呼ぶので不要)。この 1 行は 4.1 の起動順に足してある。

**実行時エラーの形と正規化**(FARC-P-44。正規化層を置くことは承認済みの案(ゲート4。2026-11-26)。方式の細部は承認済みの案(ゲート5。2026-11-26。G5-1)): 生成された `{Op}Errors` の型はすべて `ErrorResponse` だが、**実行時に投げられる値は型と食い違う**(確認 2026-11-26。0005。加えて本節の作成時に、生成クライアント 0.99.0 をスクラッチで動かし、`error` interceptor が受け取る値と、request interceptor の例外が `error` interceptor を通ることを確認した)。

| 状況 | `error` interceptor が受け取る値 | 応答 | 正規化後(`ApiError`) |
| --- | --- | --- | --- |
| 4xx・5xx で本文が A 5.2 の JSON(`error.code` が string) | パース済みの `ErrorResponse` オブジェクト | あり | `kind: 'api'`(`status`・`code`・`retryable`・`details`・`outcomeUnknown`) |
| 4xx・5xx で本文が JSON だが `error.code` を持たない | オブジェクト | あり | `invalid_response`(`status`) |
| Nginx の HTML(502・503・504・413 など)、空の本文 | `string`(空の本文は `''`) | あり | `invalid_response`(`status`) |
| 2xx で本文が JSON でない(誤配信の HTML など) | `SyntaxError` | あり(200) | `invalid_response`(`status` 200) |
| 接続できない・切断 | `TypeError` | なし | `network` |
| クライアントのタイムアウト | `TimeoutError`(下) | なし | `timeout` |
| 利用者側の中断(`AbortError`。Query の破棄・キャンセル) | `AbortError` | なし | `ApiError` にせず、そのまま通す(導出: Query の破棄・キャンセルの結果は使われないため) |
| パス値の検証の拒否(下) | request interceptor の例外 | なし | 合成した `kind: 'api'`・`status: 400`・`code: 'invalid_request'`・`retryable: false`(読み取りでは 6.2 の「見つかりません」と同じ扱い) |

- **JSON のエラーと Nginx の HTML は、本文が JSON で `error.code` が string かどうか**で区別する(FARC-P-44)。
- **実装**: `client.interceptors.error.use(…)` に正規化の関数を 1 つ登録し、**`AbortError`(上の表。そのまま通す。導出: Query の破棄・キャンセルの結果は使われないため)を除き、投げられる値を `ApiError` にする**(interceptor が返した値がそのまま投げられる。確認 2026-11-26)。さらに、Query 側は `error` を **`unknown` として扱い**、型ガード `isApiError(e: unknown)` で確認して、`ApiError` でなければ `invalid_response` として扱う(生成型の `ErrorResponse` を信用しない二重の備え)。`useQuery`・`useMutation` の `error` の型が `ErrorResponse | null` に見えても、直接 `error.error.code` を読まない。代案のラッパー関数(14 EP を `try/catch` で包む)は、interceptor 1 つで足りるため採らない(承認済みの案(ゲート5。2026-11-26。G5-1))。実機での確認は FARC-U-22。
- `ApiError` の概形(コードではない。置き場は F `shared/api`。FMOD-P-34):

```text
ApiError =
  | { kind: 'api', status, code, retryable, details?, outcomeUnknown }   // A 5.2 の形で返った(`api` が返した JSON)
  | { kind: 'network' }                                                    // 接続できない・切断された
  | { kind: 'timeout' }                                                    // クライアント側のタイムアウト
  | { kind: 'invalid_response', status? }                                  // JSON でない・形が違う(Nginx の HTML・空の本文など)。応答がなければ status なし
```

`outcomeUnknown` は `details.outcome_unknown`(B 2.3 の `crawler_response_lost`。A 5.2)から作る。`message`(固定の英語文)は画面に出さない(A 5.2)。

**パス値の送信前検証**(検証することは承認済みの案(ゲート4)。request interceptor での検証と合成エラーの方式は承認済みの案(ゲート5。G5-1)。FMOD-P-4・34。確認 2026-11-26。0005): 生成 SDK は `encodeURIComponent` でパスの値を送り、`a%b?c#d`・`a/b`・日本語は正しく送られる。ただし、`.` は一覧の EP(`/jobs/`)、`..` は 1 階層上(`/api/admin/v1/`)、空文字は `/jobs/` に正規化されて**別の EP へ送られ**、`undefined` はプレースホルダ(`{job_id}`)が残る(`%2e%2e` は二重にエンコードされ回避にならない)。本節の作成時に、request interceptor に渡る `opts.path` は元の値(`.` など)のままであることを確認した。

- **拒否する値**: `source_id`・`job_id` をはじめ**パスに入れる値すべて**で、**値全体が `.` または `..` に等しい、空、制御文字(U+0000〜U+001F・U+007F)を 1 文字でも含む、文字列でない**もの。`.` を含むだけの値(`my.source`・`a.b`・`..a`・`a..`)は拒否しない(URL の `.`・`..` の正規化は、パスの 1 区間が値全体として `.`・`..` のときに働く。導出。`a.b`・`..a`・`a..` が正しく送られることは契約テストで確かめる。10.1)。それ以外(`%`・`?`・`#`・`/`・空白・日本語)は SDK のエンコードに任せ、API の判断(400・404)を 6.2 の「見つかりません」で扱う。
- **二重の保証**: (1) 画面・Query 側は、URL から取った値を使う前に同じ検証関数を通し、不正なら API を呼ばず「見つかりません」と同じにする(4.5。Query は `enabled: false`)。(2) クライアント側の最終防衛として、`interceptors.request` が `opts.path` のすべての値を検証し、不正なら**送信せずに**例外にする(上の表の合成エラー)。mutation の対象 ID(API の応答から取る値を含む)もここを通る。
- 検証関数は 1 つで、`admin/api` に置く(F 3.3)。
- Nginx を越えた `%2F`・`%2E` の保持は未検証(FARC-U-21。3.3)。

**タイムアウト**(仮値。承認済みの案(ゲート3)。FARC-U-16): **読み取り 45 秒・書き込み 90 秒**。`api` 側の OpenSearch(接続 10 秒+読み取り 10 秒、再試行 2 回)、Crawler の接続 3 秒+応答 60 秒(A 5.6)を、`api` 自身のエラー応答(503・504)より先に切らないための値。複数の読み取りを順に行う EP(EP-01・02・10)では `api` 側の最悪の合計が 45 秒を超えうるため、実測で確認する。

- **実装**: `setConfig({ fetch })` に、メソッドで時間を切り替える fetch(GET は 45 秒、それ以外は 90 秒)を渡す。自前の `AbortController` と `setTimeout` で中断し、呼び出し側の `signal`(Query が破棄したとき)の中断も伝え、時間切れは `TimeoutError` として投げて `timeout` に正規化する(承認済みの案(ゲート5。2026-11-26。G5-1))。`AbortSignal.any` は、対応下限の Safari 16.4 で使えない可能性があるため使わない(推測。未確認。FARC-U-22)。
- **タイムアウトの対象**: 時間切れの対象は、応答ヘッダーの受信までではなく**本文の取得完了まで**とする。`fetch` の Promise はヘッダーを受信した時点で解決し、本文の受信はその後も続くため、ヘッダー受信の時点でタイマーを止めると、本文の受信が途中で止まったときに時間切れが働かない(生成 SDK は fetch の解決後に本文を読む)。呼び出し側の `signal` の中断も、本文の取得完了まで内側の `AbortController` に伝える。実装方式(例: fetch の中で本文を読み切ってから `Response` を返す)は実装時に確認し(FARC-U-22 の (5))、ヘッダー受信後に本文が止まったケースを単体テストで確かめる(10.1)。承認済みの案(PR #21 のレビュー指摘への対応。ユーザー指示 2026-11-26)。
- **Nginx との整合**(3.3。FARC-P-41): 書き込みの最長は、`api` が Crawler を待って返す JSON の 504 `crawler_response_lost`(約 63 秒)。順序は「`api` の最長(約 63 秒)< クライアントの書き込み(90 秒)≤ Nginx の `proxy_read_timeout`(90 秒以上)」とする。Nginx が先に切ると、結果不明の JSON が届かず HTML の 504 になる。クライアントが先に切ると `timeout` になる。**どちらも書き込みでは「結果不明」で、画面の挙動は同じ**(6.5)。`api` の Crawler 待ちの設定(上限 600 秒)を上げたときは、クライアントと Nginx の値も追従する(導出)。

### 5.4 TanStack Vue Query の既定値と key(承認済みの案(ゲート3・4・5)。FARC-P-8・43。ライブラリの採用はゲート1で承認済みの案(FARC-P-30))

`QueryClient` の既定:

| 項目 | 値 | 理由 |
| --- | --- | --- |
| `retry`(query) | **1 回**。対象は、`network`、`retryable=true` の `api`(5xx)、`invalid_response` のうち `status` が 502・503・504(Nginx 由来の一時的な失敗。FARC-P-43。導出)。**`timeout`**(45 秒×2 で長く待たせる)、400・404・409、`invalid_response` のその他(形が違うだけで、再試行しても変わらない。導出)は再試行しない。判定は `error` を `unknown` として `isApiError`(5.3)で確認して行う | DS 10.1・admin-view 7.11 の `retry: 1`。再試行しても変わらないエラーで待たせない |
| `retryDelay` | 1 秒(固定) | 管理画面向けに短く |
| `staleTime` | `0` | **マウント時(画面を開く・戻る)は再取得する**(S2 の「開いたとき再取得」。#33。J1・S1・X1・O1 も同じ)。画面仕様の「手動のみ」は、**定期更新と、フォーカス・再接続による自動再取得をしない**の意で、マウント時の再取得は含まない。戻る操作で古い一覧が最新の状態を隠さないため、マウント時の再取得を止める案(`refetchOnMount: false`)は採らない |
| `refetchOnWindowFocus` / `refetchOnReconnect` | `false` | 「手動更新のみ」の画面で、フォーカス復帰・再接続による予期しない再取得をしない(FARC-P-31)。更新は更新ボタン・マウント時・D1 と J2 のポーリングだけ |
| `gcTime` | 既定(5 分) | 戻る操作で前回の値を使えるように |
| mutation の `retry` | `0` | 書き込みは再送しない(5.3) |
| グローバルの通知 | **置かない**(`QueryCache`・`MutationCache` の `onError` でスナックバーを出さない) | 自動更新の失敗は通知を出さずページ内の警告に留める(DS 4.7)。操作の失敗は各ダイアログが扱う(6.3) |

**key**: 生成された `queryKey` は使わず、**ドメインごとの key factory で上書きする**(承認済みの案(ゲート3))。理由: DS 4.3・admin-view 7.11 の key の書き方(`['sources', …]`)に合わせ、invalidate を prefix で意図どおり指定でき、Hey API 0.x の key の形の変更に引きずられない。

**上書きの書き方**(確認 2026-11-26。本節の作成時に、生成物 0.99.0 と `@tanstack/vue-query` 5.108.4 でスクラッチ上に確認): `{ ...xxxOptions(…), queryKey: keys.… }` をそのまま `useQuery` に渡すと**型検査が通らない**(TS2769。`staleTime` などの型が、生成された key の型に結びつくため)。**key の型を合わせる 1 つのヘルパー(`withKey(options, key)`。キャストを 1 か所に閉じ込める)**を通すと通る(承認済みの案(ゲート5。2026-11-26。G5-1)。F 3.4)。実行時は、生成された `queryFn` が `xxxOptions` の引数(クロージャ)から URL を作り、key から作らない。key を差し替えても正しい URL へ送られる(`['sources','detail',id]` で `/sources/{id}` への送信を確認)。`queryKey[0]` が文字列のとき、生成 `queryFn` は `...queryKey[0]` を展開してしまうが、リクエストには影響しない。代案(自前の `queryFn` で SDK 関数を `throwOnError: true` と `signal` つきで呼ぶ)は、キャストは要らないが生成 Options の型の追従を失うため採らない。 なお、この方式は Hey API の内部実装(生成された `queryFn` が `xxxOptions` の引数から URL を作ること)に依存する。依存が重くなったときの代替(SDK 関数から独自の Options を組み立てる)は FARC-U-22 の (6)。

| 領域 | key(`params` は URL から正規化した条件。5.6) | 画面 |
| --- | --- | --- |
| メタ | `['meta']` | シェル、S1〜S4 |
| ダッシュボード | `['dashboard']` | D1 |
| データソース | `['sources','list']`、`['sources','detail',sourceId]`、`['sources','edit',sourceId]` | S1・J1・X1(選択肢)、S2、S4 |
| ジョブ | `['jobs','list',params]`、`['jobs','detail',jobId]` | J1、J2 |
| 文書 | `['documents',sourceId,params]`(`params` に `tab`) | X1 |
| OpenSearch | `['opensearch','cluster']` | O1 |

`['sources','list']` は S1・J1(データソースの選択肢)・X1(選択肢)で**共有**する(EP-01)。EP-01 は検索ベースで、**反映が遅れうる**(EP-02 は ID 指定で即時。S-E5。確認 2026-11-26。0004。注記は承認済みの案(ゲート5。2026-11-26。G5-2))。登録・削除の直後に、一覧に新規のソースが見えない・消えたソースが残る例があり、最大の遅延は未測定(FARC-U-23)。

### 5.5 ポーリング・stale・更新(FARC-P-9。更新間隔は FARC-P-31。v0.1 から変更なし)

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

**URL ↔ Vuetify ↔ API の対応**(I-85。B 2.1 が E・F に委ねた対応。確認 2026-11-26。0004・OpenAPI):

| 項目 | URL のクエリ(画面仕様) | Vuetify(`VDataTableServer`) | API(B 2.1。OpenAPI の型) |
| --- | --- | --- | --- |
| ページ | `page`(1 起点。既定は省略) | `page` | `page`(integer。最小 1。既定 1) |
| 件数 | `size`(25・50・100。既定 25 は省略) | `itemsPerPage` | `items_per_page`(25・50・100 の列挙。既定 25) |
| 並べ替え | `sort`(**API の値と同じ**。例 `-queued_at`。既定は省略) | `sortBy: [{ key, order }]`(**列の `key` を API の項目名**にする) | `sort`(先頭 `-` で降順。単一項目。EP-09 は string で `queued_at`・`-queued_at` だけ。EP-11 は string \| null でタブごとの項目) |
| データソース | J1・X1 は `source`(識別子) | — | J1 は `source_id`(クエリ。任意)、X1 は**パスの** `{source_id}` |
| 状態(J1) | `status` | — | `status`(`queued`・`running`・`succeeded`・`partially_succeeded`・`failed`・`cancelled`・複合 `active`) |
| タブ(X1) | `tab`(`skipped`・`extract-failed`・`oversize`・`summary-pending`) | — | `tab`(**必須**。`skipped`・`extract_failed`・`oversize`・`summary_pending`) |

- **URL が唯一の正**(8章): route の `query` から正規化した `params`(型付き)を作り、key・API 呼び出し・`VDataTableServer` の `page`/`itemsPerPage`/`sortBy` はすべて `params` から導く。ローカルに複製しない。
- **型**: `items_per_page`・`status`・`tab` は生成型が union になるが、**EP-09 の `sort` は string**(J-O2)なので、`jobsParams.ts`(F 3.5)が union を持つ。`page × items_per_page ≤ 10,000` は OpenAPI に出ない(実行時の 400)ため画面が守る(下の「深いページ」)。
- **正規化**: 不正値(範囲外の `page`、未知の `sort`・`tab`・`size`)は既定値にして `router.replace`。`sort` は単一項目だけ(複数ソートを無効にする。実装時確認。FARC-U-2)。並べ替えが「なし」になったときは `sort` を省略し、既定の並び(B 2.1)に戻す。
- **履歴**: 条件の変更(ページ・件数・並べ替え・絞り込み・タブ)は `router.push`(戻る・再読み込み・共有で再現。画面仕様)。O1 の `q`・`state` は `router.replace`(opensearch 3.5)。
- **条件を変えたら 1 ページ目に戻る**(絞り込み・件数・タブ・データソース。画面仕様)。ページと並べ替えだけの変更では戻らない。
- **取得中の前回データ**: `placeholderData: keepPreviousData`(TanStack Query v5。DS 4.3)を、**同じスコープ(同じ絞り込み・同じデータソース・同じタブ)のページ・並べ替えの変更**に限って使う。絞り込み・タブ・データソースが変わったときは前回の行を見せず、スケルトンにする(別の条件の行を「古いデータ」として見せない。X1 の `tab_counts` も、データソースが同じ間だけ前回の値を残す)。**前回データを表示している間(`isPlaceholderData` が `true`)は、行単位の更新操作(J1 の取消など)を無効にする**。URL・ページネーションは次のページなのに、表の行が前のページのものである間に、意図しないジョブを操作しないため(取得が終われば有効になる)。X1・O1 のような読み取りだけの表には関係しない。テストは 10.1(承認済みの案(PR #21 のレビュー指摘への対応。ユーザー指示 2026-11-26))。
- **深いページ**: `page × items_per_page ≤ 10,000`(B 2.1)。画面は上限を超えるページへの移動を出さず、`total` が上限を超えるときは `window_limit` を使って「表示できるのは先頭 N 件までです」と案内する(documents 8章)。
- `VDataTableServer` の `@update:options` が初期表示で発火して**二重に取得しない**こと、`hover` の有無、`aria-sort` は実装時に確認する(DS 4.3・DS 3.2。FARC-U-2)。

### 5.7 画面別のデータ取得・エラー表示の方針(FARC-P-11。実 OpenAPI で照合。確認 2026-11-26。0004)

F はこの表を「画面 → route → ページ → composable → EP」に展開する(F 4章)。エラーの表示は 6章。`—` は該当なし。EP は 5.2 の対応表の SDK 関数名で書き、key は 5.4。

| 画面 | 読み取り(EP・SDK 関数・key) | 更新 | 初回の失敗 | 更新の失敗(前回データあり) | 部分失敗・補足 |
| --- | --- | --- | --- | --- | --- |
| D1 | EP-13 `getDashboard`(`['dashboard']`)だけ(EP-14 はシェルが取得する。dashboard 画面仕様に cron のタイムゾーン・Dashboards の URL を使う項目はない)。**応答に最上位の `unavailable` はない**(D1 は `unavailable` を引かない) | 30 秒+手動(5.5) | エラーブロック(`d1-state-error`)。通知なし | 警告アラート+**前回「正常」「異常」だったタイルを判定不能に降格**し「前回の状態」を添える。「未設定」は維持(dashboard 4.3。#25)。`dataUpdatedAt` を最終取得成功日時に | 下の「D1 の補足」 |
| S1 | EP-01 `listSources`(`['sources','list']`)、EP-14 `getMeta` | 手動のみ | エラーブロック(`s1-state-error`) | stale アラート(`s1-state-stale`)。操作は無効にしない | 取得失敗は**各行の `items[i].unavailable`**(常に存在。キーは行内の相対パス `last_crawl`・`last_completed_at`・`delete_job`・`last_crawl.stalled`・`delete_job.stalled`・`document_count`。最上位 `unavailable` は常に `{}`。B 2.2・3.1。AAPI-P-42)で判定する。行の値が `null` で**その行の** `unavailable` にキーがあれば「取得できません」、キーがなければ値がない(`last_crawl=null` は「未実行」)。`document_count` は「—」+「取得できません」。`last_crawl.stalled` は DS 4.1 のタグ(リース切れ)。**`status`・`connector_type` は `null` になりうる**(保存値が読めないとき。S-D2。`status` は `active`・`deleting`)。**`status=null` の行は、「削除中」の判定も操作(クロール起動・削除など)も出さない**(FARC-P-36 の拡張。状態の列は「—」+視覚的に隠した「読み取れません」(5.9 の (b))。識別子のリンク(S2 への遷移)は残す。導出)。**`last_completed_at`・`connector_type` は S1 で使わない**(S-E6。使う画面仕様がない。要件にない追加をしない。承認済みの案(ゲート5。2026-11-26。G5-2))。EP-01 は検索ベースで反映が遅れうる(5.4) |
| S2 | EP-02 `getSource`(`['sources','detail',id]`)、EP-14 `getMeta` | 画面を開いたとき・操作の後 | 404 `source_config_not_found` → 「見つかりません」(`s2-state-notfound`)。その他は取得できません(`s2-state-error`) | stale アラート(`s2-state-stale`)。404 になったら stale にせず「見つかりません」に切り替える | **最上位**の `unavailable` のキー `lock`・`last_crawl`・`last_completed_at`・`delete_job`・`last_crawl.stalled`・`delete_job.stalled`・`index.document_count` は各カードで「取得できません」(ロック状態カードの写像は 5.10)。設定の項目が読めない(`unavailable.<項目名>=malformed`)ときの表示は I-87。`status=null` は S1 と同じく「削除中」の判定・操作の出し分けをしない(承認済みの案(ゲート5。2026-11-26。G5-1)。EP-02 の `status` も null 許容)。`lock.job.lease_expires_at` は読めなければ `null`(番兵は出ない。期限切れかどうかは `lock.state`(`lease_expired` など)で表す。B 3.2)。`status=deleting` は操作を出し分ける(DS 4.13。sources 1.8) |
| S3 | —(EP-14 `getMeta` のみ) | — | EP-14 の失敗はタイムゾーン警告(sources 2.4。`cron_timezone=null` と同じ扱い) | — | — |
| S4 | EP-02 `getSource`(編集用 `['sources','edit',id]`)、EP-14 `getMeta` | 開くたびに取得 | **フォームを出さず**エラーブロック(`s4-…`。現在値がないまま全置換しない。B 3.2、sources 2.6) | — (編集中は再取得しない。5.8) | 404 → 見つかりません。`status=deleting` → 編集不可(sources 2.6)。**`unavailable` に設定の項目があるとき**(`malformed`)は 7.6 |
| J1 | EP-09 `listJobs`(`['jobs','list',params]`)、EP-01 `listSources`(選択肢) | 手動のみ | エラーブロック(`j1-state-error`) | stale アラート(`j1-state-stale`。「実行中のジョブの状態が実際と異なる可能性」) | ジョブ記録の値が読めず `status=null` の行は、状態列を「—」にし、ステータスタグも取消も出さない(5.9)。**`status` の絞り込みは保存上の状態**で、画面の「実行待ち・実行中」は複合値 `active`。**`failed` の絞り込みに、リース切れ(保存上は `running`)は含まれない**(J-E7。B 5.1)。「失敗(リース切れ)」の行は `active`(または `running`)の絞り込みでだけ出る。画面仕様 jobs 1.5 への追記は HO(I-123)。未登録の `source_id` は 404 にならず空の結果(B 5.1)。その行の `unavailable` に `stalled` があるとき、その行の `stalled` は `null`・`cancellable=false`(取消を出さない。他の行には影響しない。最上位 `unavailable` は常に `{}`。AAPI-P-42)。EP-01 が失敗しても一覧は出し、選択肢は「すべて」と URL の指定値だけにする(案) |
| J2 | EP-10 `getJob`(`['jobs','detail',jobId]`) | 実行待ち・実行中は 10 秒(5.5) | 404 `job_not_found` → 見つかりません。その他は取得できません(`j2-state-error`) | stale アラート(`j2-state-stale`)。404 は「見つかりません」に切り替え | **最上位**の `unavailable` のキー: `stalled`・`lease_expires_at`・`latest_for_source`・`rerunnable`・`deletion.current`。**`stalled`・`rerunnable`・`latest_for_source` が `null` のときは再実行・取消の操作を出さない**(1.2)。`status=null` ならタグ・操作とも出さず、`registration` の件数・`partial`・`phase` の `null` は「—」(5.9)。`rerun_blocked_reason=source_missing`(データソースの設定がない)は出さない(6.7)。`stalled=true` かつ `lease_expires_at=null` は「期限を確認できません(期限切れ)」(5.10)。`force_delete`・`rewrite_mode` が `null`(読めない)ときの DLG-4 は 7.5。`deletion.current_state`: **`available` のときだけ** `deletion.fetched_at` を現在値の「取得時刻」に出す。**`unavailable`(読み取りの失敗)と `not_found`(現在値がない)のときは、`fetched_at` が入っていても取得時刻として出さない**(J-E10。実装は失敗時も「読もうとした時刻」を入れる。取得時刻は現在値を読んだ時刻を表すので、現在値がないときは出さず、取得に成功した時刻と失敗した時刻を混同しない。`unavailable`・`not_found` は「結果不明」の説明。jobs 2.9。F 3.9 と同じ。PR #21 のレビュー指摘への対応。ユーザー指示 2026-11-26)。`registration.phase` で途中/確定を示す。未知の `failure_reason`・警告コードは一般的な文言(B 5.2。jobs 2.5・2.7)。`warnings[]` の要素は型が `{[k: string]: unknown}` なので、`code` は `typeof code === 'string'` の型ガードで読む(J-O4。承認済みの案(ゲート5。2026-11-26。G5-2)。F 3.5 の `catalogs/`) |
| X1 | EP-11 `listDocuments`(`['documents',sourceId,params]`)、EP-01 `listSources`(選択肢) | 手動のみ | **パネルだけ**エラーブロック(`x1-state-error`)。タブ名の件数は「—」。データソース未選択は `enabled: false` | パネル上部の stale アラート(`x1-state-stale`) | **最上位**の `unavailable` は行に属さない `tab_counts.<タブ>`・`document_count` だけ。各行の `unavailable` のキーは `existence`(B 2.2・6.1。AAPI-P-30・42)。`tab_counts.<タブ>`・`document_count` の `null` は「—」。`existence` が `unknown`(その行の `unavailable` に `existence`。一括検索(1 回の `ids` クエリ)の失敗は全行。行ごとに成否が分かれることはない)は「確認できません」。`tab` は必須(画面は常に送る)。404 `source_config_not_found` は I-87。**`items` の絞り込み**と行ごとの `expectedFields`は下の「X1 の `items`」 |
| O1 | EP-12 `getCluster`(`['opensearch','cluster']`)。**応答に `unavailable` はない**(O1 は `unavailable` を引かない) | 手動のみ | カード内のエラーブロック(`o1-state-error`)。**1 取得=カード全体**(どれかの読み取りが失敗したら全体が 503。B 7.1) | ページ上部の stale アラート+カード全体を前回の値で(`o1-state-stale`) | 絞り込み(`q`・`state`)は画面側。`indices[].status`・`document_count` の `null` は「—」。`truncated=true` は I-87。`cluster.status`・`indices[].status`・`shards[].role/state` は OpenAPI で string のため、**union とガードを 1 か所に定義し、未知の値は中立表示**(X-BD2。F 3.5)。**O1 の並び・欠けの補完は API が保証する**ので、`nodes`・`indices`・`shards` を API の並びのまま使い、画面で補完しない(X-ED5。承認済みの案(ゲート5。2026-11-26。G5-2)。二重実装を避ける) |
| シェル | EP-14 `getMeta`(`['meta']`。`staleTime: Infinity`。FARC-P-25)。**クエリなし**(5.3) | 再読み込みまで | 失敗してもシェルを止めない。Dashboards リンクは出さず、タイムゾーンは「取得できません」の警告(sources 2.4) | — | 応答に `unavailable` はない |

**D1 の補足**:

- `components[]` は常に 8 件(固定の順)。`state`(`normal`・`abnormal`・`undetermined`・`not_configured`)は DS 4.1 の 正常・異常・判定不能・未設定に 1 対 1。
- `reason`(`connection_refused`・`name_not_resolved`・`unexpected_status`・`missing`・`timeout`・`connection_error`)は診断用の補足で、未知の値は一般的な文言(B 8.1)。
- `id`(`crawler`・`indexer`・`opensearch`・`api`・`web`・`opensearch-dashboards`・`embedding`・`llm`)は画面の表示名と同じ。**`web` は、v0.2 では `web` コンテナ(Nginx)で、`api` が HTTP で確認する**(**前提タスク C の後に有効**。3.6)。現状の実装は `index.html` の存在で判定し、OpenAPI の `ComponentId` の説明も「compose のサービスではなく `api` が配信する」と書いているため、C の完了までは食い違う(12.8)。
- トップの `checked_at` は全確認が終わった時刻で、**最終取得成功日時(クライアントの `dataUpdatedAt`)とは別**。タイルの「確認 hh:mm:ss」は `components[].checked_at`。
- `api` に届く限り EP-13 は 200 で、コンポーネントの失敗は `state` に載る。

**X1 の `items`**(X-BD1・X-ED1。承認済みの案(ゲート4。2026-11-26)。実装の構成は F 3.5・3.9): EP-11 の `items` は、判別子のない 4 型の `anyOf`(`SkippedDocument`・`ExtractFailedDocument`・`OversizeDocument`・`SummaryPendingDocument`)で、型からは行が絞れない。**`documentTabs` の各定義が、そのタブの行の型とアダプタ(型ガード)を持ち**、`DocumentsTable` は `tab` ごとの行型を受ける。応答の `tab` を判別子にして行を絞り、行に `tab` 固有のキー(確認 2026-11-26。OpenAPI。skipped は `existence`、extract_failed は `last_seen_at`、oversize は `detected_by`、summary_pending は `indexed_at`。いずれも必須キー)があることを型ガードで確かめる(案)。合わないときは想定外として診断に出す。各行の項目は、B が null と書く項目以外も null 許容で、非 null なのは `SkippedDocument.existence`、`ExtractFailedDocument`・`SummaryPendingDocument` の `document_id`、各行の `unavailable` だけ(確認 2026-11-26。OpenAPI)。**行ごとの `expectedFields`**(「値があるはずの項目」。5.9)をタブごとに持ち、正確な一覧はその表に持たせる。

- **EP-14 `/meta` の失敗**は、`dashboards_url=null`・`cron_timezone=null` と同じに扱う(導出。「取得できないとき」の画面の挙動が画面仕様にある)。
- X1 の `enabled: false` のとき、`isPending` は true のままで取得は走らない。スケルトンは `isPending` ではなく**取得中を表す状態**(v5 の `isLoading`。推測。実装時確認)で出す。

### 5.8 操作(mutation)と invalidate(FARC-P-11・46)

| 操作(ダイアログ) | EP・SDK 関数(Mutation) | 成功の扱い | invalidate(prefix) |
| --- | --- | --- | --- |
| DLG-1 クロール起動(S1・S2) | EP-06 `startCrawl`(`startCrawlMutation`)。本文は常に `{force_delete, rewrite_mode}` | 202 `JobAccepted` → スナックバー「…を受け付けました(ジョブ ID: …)」+「ジョブを表示」(ジョブ ID は応答の `job_id`。`status`・`job_type` では分岐しない。J-O7) | `['sources']`、`['jobs']` |
| DLG-4 再実行(J2) | EP-06 `startCrawl`(J2 の `source_id`・`force_delete`・`rewrite_mode` を渡す。B 4.1)。**`null` は `false` として送る**(FARC-P-46。7.5) | 新しいジョブの J2 へ移動+スナックバー(#32) | 同上 |
| DLG-2 削除・削除の再実行(S1・S2・J2) | EP-05 `startSourceDelete`(`startSourceDeleteMutation`)。本文なし | 202 → スナックバー。**S2 のロック状態カードは invalidate 後の EP-02 で即時に `held_delete`** になる。**S1 の行は「削除中」にならないことがある**(下) | `['sources']`、`['jobs']` |
| DLG-3 取消(J1・J2) | EP-07 `cancelJob`(`cancelJobMutation`) | 200・202 → スナックバー(文言は応答の `status` で分岐。jobs 2.10)。**409 `job_already_finished` も成功扱い**(6.3) | `['jobs']`、`['sources']` |
| DLG-5 ロック解放(J2・S2) | EP-08 `releaseLock`(`releaseLockMutation`) | 200 かつ `released=true` → スナックバー。**`released=false` は成功文言にしない**(6.3) | `['sources']`、`['jobs']` |
| S3 登録 | EP-03 `registerSource`(`registerSourceMutation`) | 201 または 200(冪等)→ S2 へ移動+スナックバー | `['sources']` |
| S4 保存 | EP-04 `updateSource`(`updateSourceMutation`) | 200 → S2 へ移動+スナックバー | `['sources']`(編集用の key は `gcTime: 0` で残らない) |

- 実行中は実行ボタンを無効にし(mutation の `isPending`)二重送信を防ぐ。ダイアログは**失敗時に開いたまま**(6.3)、成功時だけ閉じてスナックバーを出す(DS 4.8)。
- **EP-05 の 202 の直後、S1 の行は「削除中」にならないことがある**(S-E1。承認済みの案(ゲート4。2026-11-26)。確認 2026-11-26。0004。IT の AIT-60): 受付の時点では設定の `status` は `active` のままで、`deleting` になるのは削除ジョブの開始後。直後の EP-01 は `delete_job=null` のままのことがある(EP-01 は検索ベースで反映も遅れうる。5.4)。EP-02 の `lock.state` は即時に `held_delete`。したがって、受付の確認は**スナックバー(`job_id` つき)と S2 のロック状態カード**で行い、S1 の行は「更新」・次のマウントで「削除中」になる。v0.1 と admin-view 7.8 の「その行は『削除中』になり」は、直後には成り立たない(I-122)。
- **S3 の登録直後**: S2 へ移動して EP-02(ID 指定で即時)を取得する。S1 に戻ったときの EP-01 は、新規のソースがすぐに見えないことがある(5.4。FARC-U-23)。
- **S4 の取得(FARC-P-12)**: S4 は S2 と**別の key**(`['sources','edit',id]`)で、`gcTime: 0`・`staleTime: Infinity`・ウィンドウフォーカスなどによる再取得なしにする。画面を開くたびに必ず取得し、**取得結果でフォームを 1 度だけ初期化**する(キャッシュ済みの古い値で全置換しない。編集中にバックグラウンドで値が差し替わらない)。**「1 度だけ」の単位は、コンポーネントの生存期間ではなく編集対象の `sourceId`**とする。Vue Router はルートパラメータだけが変わる遷移(`/sources/a/edit` → `/sources/b/edit`。戻る・進む・URL の直接変更)では同じコンポーネントを再利用するため、`SourceEditPage` を `sourceId` で `:key` し(ID が変わったら再マウントする)、フォームの値・検証エラー・サーバーエラー・送信状態をすべて作り直す。別の ID の設定を、前の ID の入力で全置換して送らない(`toRequest` はいま表示している ID の値だけを使う)。テストは 10.1(承認済みの案(PR #21 のレビュー指摘への対応。ユーザー指示 2026-11-26))。

### 5.9 Vue で使うときの注意

- Hey API の `xxxOptions({ query, path })` は、Vue では**リアクティブな値を直接受けない**。`useQuery(computed(() => withKey(xxxOptions({ … }), keys.…)))` のように `computed` で包み、URL から導いた `params`・`enabled` を中に入れる(0004。`withKey` は 5.4)。`useQuery` の `error` は生成型で `ErrorResponse | null` に見えるが、`unknown` として扱う(5.3)。
- 日時は `Intl.DateTimeFormat`(ブラウザのローカル時刻。`YYYY-MM-DD HH:mm`。DS 4.9。FARC-P-33)で整形し、日時ライブラリを足さない(承認済みの案(ゲート3)。FARC-P-24)。日時は OpenAPI で `format` のない string(`responseTransformer` は使わない)。
- 時刻の比較・並べ替えは API の ISO 8601 文字列(UTC・ミリ秒精度。A 5.1)を `Date` に変換してから行う。
- **番兵の日時**: 409 の `details.existing_job.lease_expires_at`(`lock_held`・`lock_in_use`)は、Crawler が値を日時として読めないときだけ `0001-01-01T00:00:00.000Z` を返す(B 2.11・I-73)。**日時として整形せず「期限切れ」として扱う**(「0001-01-01 …」を表示しない)。`null` は「期限なし(実行待ち)」で、番兵とは別。S2 の `lock.job.lease_expires_at` は `api` が読むため、読めなければ `null` で番兵は出ない(期限切れは `lock.state` で分かる。B 3.2)。整形関数は番兵を判定する 1 か所に置く(F 3.5 の `formatLeaseExpiry`)。
- **`null` の 2 種類(FARC-P-36。B 2.2・2.11)**: (a) **取得失敗**=`unavailable` にキーがある `null` → 「—」+「取得できません」。**表示は画面仕様に従う**(表のセル(S1 の登録文書数・X1 の件数など)は視覚的に隠した「取得できません」、S2 のカードは見える文言)。(b) **値が読めない**=ジョブ記録・削除記録・ロック文書など Crawler・Indexer が書いた値が欠落・型違いで `null`(`unavailable` には載らない。`malformed` は EP-02 の設定項目だけ)→ 「—」+視覚的に隠した「読み取れません」(見える文言は足さない)。表のセルでは、いずれも見た目は「—」で、読み上げ(視覚的に隠した文言)と診断で区別する。`JobBrief` の `status`・`job_type`・`trigger`・`queued_at`、`registration` の件数・`partial`・`phase` は、**値があるはずの項目**で、`null` は (b) として扱う(`started_at`・`finished_at` などの `null` は「値がない」で「—」+「なし」)。`status=null` のジョブには**ステータスタグ・操作を出さない**。S1 の `status=null` の行も同じ(5.7)。画面仕様に定義がないため案(I-120)。
- **`expectedFields`(X-BD1。承認済みの案(ゲート4))**: OpenAPI では B が「null」と書く項目以外の多くも null 許容になっている(EP-01・02・09・10・11 の行型・EP-11 の行の項目など。確認 2026-11-26。0004)。どの項目が「値があるはずの項目」(`null` なら (b))かは、**EP・行型(EP-11 は `tab`)ごとに 1 つの表(F 3.5 の `expectedFields`)に持つ**。画面は項目ごとに判断を散らさず、`cellState(unavailable, path, value, { expected })`(F 3.5)が、(a)・(b)・「値がない」・値の 4 つのどれかを返す。
- **`unavailable` の位置とキー(B 2.2。AAPI-P-42。FARC-P-27・39。承認済みの案(ゲート4。2026-11-26)で訂正)**: **最上位の `unavailable` が意味を持つのは EP-02・10・11 だけ**(EP-01・09 の最上位は常に `{}`。EP-12・13・14 は持たない。確認 2026-11-26。0004 J-E1。OpenAPI で `unavailable` を持つのは `SourceDetailResponse`・`JobDetailResponse`・`DocumentListResponse`・`SourceListResponse`・`JobListResponse` と各行の型)。キーは応答の項目の正式なパス(`deletion.current`・`index.document_count`・`last_crawl.stalled` など)。**一覧の EP(EP-01・09・11)は各行 `items[i].unavailable`(常に存在)**で、キーはその行の中の相対パス(`last_crawl`・`last_crawl.stalled`・`document_count`・`stalled`・`existence` など)。一覧の最上位 `unavailable` は、行に属さない項目(EP-11 の `tab_counts.<タブ>`・`document_count`)だけで、EP-01・09 では常に `{}`。**判定は「その行(または最上位)の `unavailable` のキー」で行う**: 値が `null` でキーがあれば取得失敗、`null` でキーがなければ値がない(読めない値は (b))。画面は行の `unavailable` を引く関数と、最上位を引く関数の 2 つを通す(F 3.5。FMOD-P-14・33)。**D1・O1 は `unavailable` を引かない**。
- **状態値の union とガード**(X-BD2): OpenAPI で string の状態値(`cluster.status`・`indices[].status`・`shards[].role/state`)は、画面側で既知の値の union と型ガードを 1 か所に定義し、未知の値は中立の表示にする(`StatusTag` は未登録の値を中立+開発時に警告)。列挙型のもの(`JobStatus` など)も、実装が Crawler の文字列をそのまま通す箇所(409 の `existing_job` など)では未知の値がありうる(6.3)。

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
- **`stalled=true` かつ `lease_expires_at=null`**(ロック文書がない・別ジョブのロック・期限が読めない。J-E5。承認済みの案(ゲート4。2026-11-26)。確認 2026-11-26。0004): リース期限は日時を出さず、**「期限を確認できません(期限切れ)」**とする(S2 の `lease_expired` で `lock.job.lease_expires_at` が `null` のときも同じ)。リース切れの判定自体は `stalled`・`lock.state` に従い、画面で再計算しない(1.2)。この経路(`stalled=true`)は IT でも未検証で、推測を含む(FARC-U-24)。

---

## 6. エラー処理

### 6.1 方針(FARC-P-13・43・44)

- 失敗は 5.3 の `ApiError`(`interceptors.error` が正規化する)に揃え、**1 つの変換表(データ)**で `code` → 表示先・variant・再試行の可否に写す。画面は変換結果を表示するだけ(DS 4.1 と同じ「対応を 1 か所に」)。文言は画面仕様が正で、`message` は使わない(A 5.2)。
- **`errorTable` の `code` は string**(OpenAPI は `ErrorBody.code` を列挙にしない。`implement_admin_api` の 0017 の意図的な判断)ため、**手書きを正本**にし、Admin 固有 14 種(`config_invalid`・`source_config_not_found`・`job_not_found`・`lock_held`・`lock_in_use`・`source_deleting`・`maintenance_enabled`・`source_already_exists`・`job_not_cancellable`・`job_already_finished`・`crawler_error`・`crawler_unavailable`・`crawler_unreachable`・`crawler_response_lost`)と共通 6 種(`invalid_request`・`not_found`・`method_not_allowed`・`http_error`・`internal_error`・`unavailable`)を網羅する(確認 2026-11-26。0004・OpenAPI)。OpenAPI の各操作の description と突き合わせる契約テストを置く(10.1)。
- 表示先は 4 つ: (1) **項目別**(フォームの入力欄の下+エラー要約。DS 4.6)、(2) **ダイアログ内アラート**(操作の失敗・拒否。閉じるまで残る。`role="alert"`。DS 4.7)、(3) **状態ブロック**(読み取りの失敗。6.2)、(4) **スナックバー**(受付・保存の**成功**だけ。失敗には使わない。DS 4.7)。
- 想定外のエラー(`crawler_error`・`internal_error`・`http_error`・`not_found`・`method_not_allowed`・`invalid_response`)は、一般的な文言と、診断用に補助文字で **`code` と HTTP ステータス**(`message` は出さない。`invalid_response` は `code` がなく HTTP ステータスだけ)を出す(案)。入力値・パスは出さない(A 2.3・5.2)。

### 6.2 読み取りの失敗(Query の状態 → 画面の状態。DS 4.5)

`features` の composable が、主たる Query の状態と `describeError`(6.1)の結果から **`viewState`** を作る(F 3.7 の `useViewState`)。`error` は `unknown` として `isApiError` で確認してから使う(5.3)。テンプレートは `viewState` だけを props で受け、`error.code` を判定しない(層の依存。F 6章 R7)。下の表は、その写像の定義。

| 画面の状態 | Query の条件 | 表示 |
| --- | --- | --- |
| 初回の読み込み中 | データなしで取得中 | スケルトン+`aria-busy`+視覚的に隠した「読み込み中」 |
| 再取得中 | データあり・取得中 | データは消さず、カード上端の進行バー |
| 空 | 成功・0 件 | 空ブロック(画面ごとの文言) |
| エラー(データなし) | `isLoadingError` | エラーブロック(`role="alert"`)+「再試行」(`refetch`)+試行時刻 |
| 古いデータ(stale) | `isRefetchError`(404 を除く) | warning アラート(`role="alert"`)+前回のデータ+「再読み込み」+`dataUpdatedAt`(最終更新(成功)時刻)。操作は無効にしない |
| 見つかりません | `error.code` が `source_config_not_found`・`job_not_found`(EP-07 の取消でも、`job_id` 起因の Crawler の 400・404 `not_found` がこの code に写る。6.3)、400 `invalid_request`(パスの ID の形式違反。**送信前のパス値の検証の拒否(5.3)も含む**)、404 `not_found`(`/` を含む ID は Admin API のルーティングで 404。B 2.12)。**データの有無を問わない** | 「見つかりません」ブロック(S2・S4・J2・X1)。前回データがあっても stale にせず切り替える(消えたリソースを「最新ではない」と読ませない) |

- 503 `unavailable`(A 5.2。OpenSearch の読み取りの失敗)と、`network`・`timeout`・`invalid_response`(Nginx 由来の HTML を含む。6.5)は、エラーブロックまたは stale になる。文言は画面仕様(例: `s2-error` の「データソースの詳細を取得できません」)。
- **部分失敗**(B 2.2。FARC-P-27): 200 の本体の `unavailable` にキーがあるときは、その項目だけ「—」+視覚的に隠した「取得できません」にする(画面仕様どおり)。**一覧の EP(EP-01・09・11)は各行の `unavailable`、単一の応答は EP-02・10 の最上位**で、EP-12・13・14 には部分失敗がない(5.9)。理由コード(`store_unavailable`・`search_index_unavailable`・`timeout`・`malformed`)は画面では**区別せず**同じ表示にする(案。`malformed` だけ S4 で扱いが違う。7.6)。主たる読み取りの失敗は 503 `unavailable` で、部分失敗ではなく上の「エラー」の表示になる(B 2.2)。
- 自動更新(D1・J2)の失敗は通知を出さず、ページ内の stale に留める(DS 4.7)。

### 6.3 書き込みの失敗(`code` → 表示。承認済みの案(ゲート2・4)の code 名は B 2.3。A 5.2)

| `code`(HTTP) | EP | 表示先・扱い |
| --- | --- | --- |
| `invalid_request`(400) | 全般 | **S3・S4**: `details.errors[].field` から入力欄を決め、`reason` を DS 4.6 の文言に対応づけて項目の下に出す(6.4)。**`details` がない(または `errors` がない)ものは想定外**(S-E4): 本文が JSON として読めない・`Content-Type` が違う・1 MiB 超(6.5)など。フォーム上部のアラートに「想定外の応答です」+診断(`code` と HTTP ステータス)。ダイアログ系・パス ID の違反: 画面が送らない値のため想定外(上の「見つかりません」の扱いは読み取りのみ) |
| `config_invalid`(400) | EP-03・04 | S3・S4: `details.errors[]` の `connector_config.…`(`include_patterns[2]` など)を該当の行・項目の下に(`detail` の固定文を画面の文言に対応づける)。**添字なしの配列エラー**(`connector_config.include_patterns`・`exclude_patterns` の件数超過)は、該当の一覧の下に出す(特定の行に結びつけない。S-E3)。**`errors` が空、`field` が `connector_config`(プレフィックスなし。「オブジェクトでない」「未知の項目がある」の違反。特定の入力欄に結びつかない。B 2.5)、または `detail` が完全一致の対応表にないとき**は、フォーム上部のアラートに **`details.crawler_message`(Crawler の固定文。入力値・パスを含まない)をそのまま出す**(sources 2.4)。入力内容は残す |
| `source_config_not_found`(404) | EP-02・04・05・06・11 | 読み取りは 6.2。**DLG-1・DLG-4**: ダイアログ内 error「データソースが見つかりません」+「一覧を更新」(admin-view 7.7)。DLG-2: 同様。S4 の保存: フォーム上部アラート |
| `job_not_found`(404) | EP-07・10 | J2 は 6.2。DLG-3: ダイアログ内 error+「ジョブ一覧を更新」。EP-07 では、`job_id` に `%`・`?` などを含み Crawler が 400 `invalid_request`・404 `not_found` を返した場合も、この 404 に写る(B 4.2・2.6。AAPI-P-39。案。表示は上と同じ) |
| `lock_held`(409) | EP-05・06 | **ダイアログ内アラート**(DLG-1・DLG-4・DLG-2・削除の再実行)。実行ボタンは「閉じる」に置き換える(admin-view 7.7)。`options_applied=false` のとき、`requested` の指定が**反映されていない**ことを太字で出す(EP-05 には `requested` がない)。**`details.lock_state` 別の variant と次の行動(FARC-P-35)**: `lease_expired`(ジョブ記録があり、リース切れ)→ warning+「ジョブ詳細でロックを解放」(J2。DLG-5)。`orphan`(ジョブ記録がない、または終端。取得から 60 秒超)→ warning+「ロック状態を確認」(**S2 のロック状態カード**)。`just_acquired`(ジョブ記録がなく取得から 60 秒以内。`orphan` と排他。受付の途中の可能性)→ 「ジョブを表示」を出さず、しばらく待ってから確認するよう案内(S2 へのリンク)。`held_crawl`・`held_delete`(ジョブ記録あり)→ error+「ジョブを表示」(`existing_job`)。`unknown`(ジョブの `status`・`job_type` が読めない場合を含む)→ error。理由を断定せず S2 を案内。**`existing_job.status`(または `job_type`)が `null`(ジョブ記録がない・読めない)、または未知の値のとき**(J-E9。承認済みの案(ゲート4。2026-11-26)。OpenAPI の `existing_job` は列挙型だが、実装は Crawler の文字列をそのまま通すため未知の値がありうる。確認 2026-11-26。0004)は、`existing_job.job_id` があっても「ジョブを表示」(J2)を出さない(EP-10 が 404 になりうる。孤児ロックの解放の入口は S2 だけ。sources 1.5)。admin-view 7.7 の「失効したロック → J2 → DLG-5」との差は I-88(ゲート3でユーザー確認済み。2026-11-23) |
| `lock_in_use`(409) | EP-08 | DLG-5 内のアラート(解放できない理由。sources 1.5 の案内。`existing_job`・`lock_state`)。`lock_state` が `unknown` のこともある(ロック文書・ジョブ記録を読めなかった、またはジョブの `status` が読めない。B 2.9・4.3)。その場合は理由を断定せず「状態を確認できないため解放しませんでした」の旨。`existing_job` の扱いは `lock_held` と同じ(`null`・未知の値は J2 へ導かない) |
| `source_deleting`(409) | EP-04・06 | DLG-1・DLG-4: ダイアログ内 error「データソースは削除中」。**S4 の保存**: S4 を「削除中」状態(編集不可。sources 2.6)に切り替え、入力は残す |
| `maintenance_enabled`(409) | EP-05・06 | ダイアログ内 error。次の行動なし(閉じる)。フラグの操作は画面にない(AF-19) |
| `source_already_exists`(409) | EP-03 | S3: 識別子の項目の下。`details.status=deleting` のときは補足(sources 2.4) |
| `job_not_cancellable`(409) | EP-07 | ダイアログ内 error。画面は `cancellable=false` の行に操作を出さないため通常は出ない(想定外の扱い) |
| `job_already_finished`(409) | EP-07 | **成功扱い**(承認済みの案(ゲート2)。AAPI-P-21。FARC-P-14): ダイアログを閉じ、スナックバー「ジョブはすでに終了しています(状態: …)」(`details.status`。jobs 2.10)。invalidate は 5.8 |
| `crawler_error`(502) | EP-03〜08 | 想定外(6.1)。再試行は出さない |
| `crawler_unavailable`(503・`retryable`) | EP-03〜08 | 「Store 層の一時的な障害」の旨+**再試行**(実行ボタンを再試行として残す。admin-view 7.7) |
| `crawler_unreachable`(503・`retryable`) | EP-03〜08 | 「Crawler に接続できません」(起動時の回復中を含む)+**再試行**。S3・S4 は入力内容を残し、フォーム上部の消えないアラート(sources 2.4) |
| `crawler_response_lost`(504・`outcome_unknown`) | EP-03〜08 | **結果不明**(6.5) |
| `invalid_response`・`network`・`timeout`(`ApiError` の kind。code なし) | EP-03〜08 | **結果不明**(6.5。FARC-P-43)。読み取りは 6.2 |
| (200 で `released=false`) | EP-08 | **成功の文言にしない**(J-E6。承認済みの案(ゲート4。2026-11-26)。確認 2026-11-26。0004): ロック文書がない `stalled` のジョブでは、EP-08 は 200 `released=false`・`failed_job_id=null` を返し、ジョブは `running` のままになる(実機未検証。FARC-U-24)。ダイアログは閉じず、内側に info アラート「解放するロックがありませんでした」を出して「閉じる」に置き換え、`['sources']`・`['jobs']` を invalidate して実態に追従させる(表示は導出。文言は画面仕様に委ね、HO)。スナックバー(成功の通知)は使わない |
| `unavailable`(503) | EP-01・02・09〜12 | 読み取り(6.2) |
| `not_found`・`method_not_allowed`・`http_error`・`internal_error` | 全般 | 想定外(6.1) |

- `retryable=true` のときだけ「再試行」を出す(`retryable` を再試行の可否の正とする。A 5.2)。起動系の再試行は、状況が変わっていないことの確認を促す文言を画面仕様に従って添える。**例外**: 保存系(EP-03・04)の `crawler_response_lost`(`retryable=false`)は、再送が安全なため「もう一度保存」を出してよい(6.5。B 9.2.4・9.2.5)。
- EP-04 の `config_invalid` は 404・409 より先に返りうる(B 3.4)。画面は返ってきた `code` に従い、順序に依存しない。

### 6.4 項目別エラー(`details.errors[]`)の写像(FARC-P-13)

- `field` は **Admin API のリクエストの項目名**(`ttl_days`・`ttl_seconds`・`ratio_threshold_percent`・`min_delete_count`・`schedule_cron`・`source_id`・`connector_config.root`・`connector_config.include_patterns[2]` など。B 2.4)。画面は項目名 → 入力欄の対応表(1 つの表。F 3.5 の `fieldMap`)で入力欄・行を決める。**表にない `field`、または対応できない `reason`**(`invalid_request` など)は、フォーム上部のアラートに「想定外の応答です」+診断用の項目名(値は出さない。A 5.2)。**`details` がない、または `errors` がない `invalid_request`** も想定外(S-E4。6.3)。`config_invalid` の `errors` が空・`field=connector_config`・照合不能の `detail` は「想定外」ではなく、`crawler_message` をそのまま出す(6.3)。
- **添字なしの配列エラーと `connector_config` 単体**(S-E3。承認済みの案(ゲート4。2026-11-26)): `connector_config.include_patterns`・`connector_config.exclude_patterns`(添字なし。件数の超過など)は、該当のパターン一覧の下に出す。`connector_config` 自身(プレフィックスなし)は、フォーム上部のアラート(6.3)。いずれも `fieldMap` に書く。
- **`ttl_days` の `exclusive`・`required`**(S-D5。承認済みの案(ゲート4。2026-11-26)。確認 2026-11-26。0004): `ttl_days` と `ttl_seconds` の排他・必須の違反は、**どちらの場合も `field` が `ttl_days` 固定**で返る。画面は `ttl_days` の `exclusive`・`required` を **TTL の欄**(日・秒のモードを切り替える 1 つの欄)の下に出す。画面は一方だけを送るため通常は出ない。
- **本文の違反は 2 段階で返る**(S-D4。承認済みの案(ゲート4。2026-11-26)。確認 2026-11-26。0004): 実装は、まず「形」(`required`・`type`・`unknown_field` など)を返し、通れば「範囲・桁・排他」(`range`・`format`・`exclusive`)を返す。**1 回の応答にすべての違反は載らない**(B 2.12 の「すべて返す」とは異なる。実装が正)。画面側の検証が同じ規則を持つので通常は出ないが、再送で別の違反が出うる。項目別エラーは「返ってきた分」を表示し、次の段階の違反は次の応答で表示してよい。
- Admin API が本文の項目エラーで返す `reason` は `required`・`type`・`format`・`range`・`exclusive`・`unknown_field`・`unsupported`・`config_invalid`(B 2.4・2.12。OpenAPI の `Reason`。Crawler の `read_only` は 502 `crawler_error` になり、画面には届かない。B 2.6)。`reason` → 文言は sources 2.4 の表(`required`・`format`・`type`・`unsupported`・`unknown_field`・409)に従う。同表にない B の値の扱い(I-84): `range` はクライアント検証と**同じ範囲の文言**、`exclusive` は上の TTL 欄、`config_invalid` は `detail`(固定文)を画面の文言に対応づける(sources 2.3.2)。
- S4 の `ttl_seconds` の入力は、日で割り切れない既存値を秒で編集するモードのときだけ(7.3)。

### 6.5 接続エラー・タイムアウト・結果不明(FARC-P-15・43。承認済みの案(ゲート3・4・5))

**読み取り**: `network`・`timeout`・`invalid_response` は 6.2(エラーブロックまたは stale)。再試行は **1 回だけ**(5.4。`network`・`retryable=true` の `api`・`invalid_response` の 502・503・504。`timeout` は再試行しない)で、それでも失敗したらエラーブロックにする(FARC-P-43)。

**Nginx 由来の失敗**(FARC-P-43。3.3): `web` の Nginx 自身が返す 502・503・504・413 は **HTML** で(`error_page` で JSON は返さない。承認済みの案(ゲート4。G4-5))、`ApiError.kind='invalid_response'`(`status` つき)になる(5.3)。`api` が返す JSON の 5xx(`crawler_*`・`unavailable`)とは、本文が JSON で `error.code` を持つかで区別する。

**書き込み(EP-03〜08)**: 次はすべて **結果不明**とする(FARC-P-15 の拡張。承認済みの案(ゲート4。2026-11-26)。`invalid_response` を `status` を問わず含める点は承認済みの案(ゲート5。2026-11-26。G5-1)): `crawler_response_lost`(504。`outcomeUnknown`)、**`invalid_response`(502・504 を含め、`status` を問わない)**、クライアント側の `timeout`、書き込みの `network`(送信後の切断かどうかをクライアントは区別できない)。理由: Nginx の 502・504 は、`api` が Crawler を呼んだ後かもしれず、`api` の JSON が届かなかっただけの可能性がある(Nginx の `proxy_read_timeout` が先に切れた場合を含む。5.3)。接続拒否など確実に送信前と分かる場合も区別しない(安全側。導出)。表示は「**操作が実行されたか確認できません**」。

- **起動系(EP-05・06)**: 再試行を出さず、状態を確認する導線を出す(J1 または S2。再送すると、受付済みなら 409 `lock_held` で既存ジョブが分かる。B 2.3)。
- **保存系(EP-03・04)**: 再送しても同じ内容なら安全(200 の冪等応答か 409。B 9.2.4・9.2.5)なので、「S2 で確認する」と「もう一度保存」の両方を出してよい(例外を維持。案)。
- **取消・解放(EP-07・08)**: J2・S2 を再取得して確認する導線を出す(解放は再送で `released=false` になりうる。B 9.2.3。6.3)。

**1 MiB 超の本文(413)**: `api` は 1 MiB 超を JSON の 400 `invalid_request`(`details` なし)で返す(A 5.1)。Nginx の既定の本文上限(公式ドキュメント上は 1m)のままだと、1 MiB 超は **Nginx が HTML の 413** を返し、`api` の JSON が届かない(`client_max_body_size 1m` を明示した検証で、+1 バイトが 413。確認 2026-11-26。0005)。そこで **Nginx の `client_max_body_size` を `api` の上限より少し大きくし、判定を `api` に任せる**(承認済みの案(ゲート4。G4-5)。3.3)。画面では、`invalid_request`+`details` なしは想定外(6.3)。画面の検証(パターンの件数・バイト数の上限。7.1)により、画面から送る本文が 1 MiB に届くことは通常ない(導出)。413(HTML)が出るのは設定が合っていないときで、`invalid_response` と同じに扱う(書き込みの結果不明。リクエストが `api` に届いていないが、区別しない。導出)。大きくした値で `api` の JSON 400 が返ることの確認は実装時(3.3。FARC-U-6)。

### 6.6 通知のルール

- スナックバー=操作の**受付・保存の成功だけ**。失敗・拒否はダイアログ内またはフォーム上部のアラート(DS 4.7)。EP-08 の `released=false` は成功ではないので、スナックバーを使わない(6.3)。
- 取得失敗は `role="alert"`、読み込み後の情報(警告・O1 の red のアラート(opensearch 4章)など)は `role="status"`(画面仕様)。自動更新の結果は読み上げない(DS 8章)。

### 6.7 画面仕様にない状態(I-87・I-124)

B・実装の応答から必要になるが、画面仕様に状態の記述がないもの。暫定の扱い(案)を置き、画面仕様の追記は A 9章(HO)に委ねる。

- O1 の `truncated=true`(B 7.1。「画面は警告を出す」): カード上部に warning の注記(「インデックスが多いため先頭 1,000 件だけを表示しています(全 N 件)」)。
- X1 の `source` が指すデータソースが存在しない(404 `source_config_not_found`): 「データソースが見つかりません」ブロック+データソースの選択へ(documents 8章の「データソース未選択」と同じ置き場)。
- S2 の `SourceSettings` の項目が読めない(`unavailable.<項目名>=malformed`。B 3.2・AAPI-P-34): 該当の項目を「—」+「保存されている値を読めません」とする。S4 は 7.6。
- S2 のロック状態カードで `lock.state=unknown`(B 2.9)のとき: 理由を断定しない表示(5.10)。
- J2 で `stalled`・`rerunnable` が `null` のとき: 取消・再実行の操作を出さず、「リース切れかどうかを確認できません」の旨を補足に出す(案。操作は出さないが、理由は画面に示す)。`rerunnable=null` には、データソースの設定の読み取り失敗も含まれる(B 2.9。AAPI-P-41)。
- J2 で `stalled=true` かつ `lease_expires_at=null`: 「期限を確認できません(期限切れ)」(5.10。I-124)。
- J2 で `rerun_blocked_reason=source_missing`(データソースの設定がない=削除済み。B 2.9。AAPI-P-41。案)のとき: **「再実行」を出さない**(削除済みのソースは再実行しない。`source_deleting` と同じ扱いで、「削除中」とは表示しない)。専用の文言は画面仕様 jobs 2.3 に定義がなく、足すかは画面仕様側の追記(HO)で、それまでは補足なし、または一般的な文言(未知の値は一般文言。I-121)。
- S1 の `status=null` の行(5.7)、EP-08 の `released=false`(6.3)、DLG-4 の `force_delete`・`rewrite_mode` が `null`(7.5): 画面仕様に定義がない(I-124)。
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
- サーバーの本文の検証は 2 段階で返る(形 → 範囲・桁・排他。6.4)。画面側の検証が同じ規則を持つことで、通常は 1 回の送信で通る。
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

### 7.5 リクエスト本文の作り方(B 2.12・3.3・3.4・4.1。FARC-P-16・46)

- **型は厳密**(B 2.12。JSON の型を変換しない。`30.0` は整数でない): 整数の項目(`ttl_days`・`ttl_seconds`・`min_delete_count`)は整数の JSON、`ratio_threshold_percent` は JSON の数値、真偽値は真偽値で送る。**文字列で送らない**(入力欄の文字列を送る直前に数値へ変換する。7.2)。未知の項目を足さない(400 `unknown_field`)。
- **フォーム用の型と送信用の型を分ける**(S-D1。承認済みの案(ゲート4。2026-11-26)): フォームのモデルは自前の型(入力欄の文字列と「TTL のモード(日・秒)と値」を持つ。F 3.9 の `fromSettings`・`toRequest`)で、**生成型をフォームのモデルに使わない**。`toRequest` が検証済みの値から、生成型 `RegisterSourceBody`・`UpdateSourceBody` を作る。`fromSettings` は EP-02 の `SourceDetailResponse`(null 許容)を読む(`SourceSettings` が 2 種類ある。5.2)。
- **`ttl_days`・`ttl_seconds` は `null` を送らず、使う方だけをキーに持たせ、もう一方はキーごと省く**(承認済みの案(ゲート4。2026-11-26)。確認 2026-11-26。0005): OpenAPI は現状 `integer | null`・省略可で `null` を型の上では許すが、実行時は `null` を 400 `type` で拒否する(S-D1)。`undefined` は JSON からキーごと消える(確認)ので、条件付きの展開でキーを組み立てる。**前提タスク A の完了前も後も同じコード**で動く(A の後は型が「任意かつ非 null」になるだけ)。排他(どちらか一方)は画面側で保証する。
- **`exactOptionalPropertyTypes` を使わない**(5.2。FARC-P-45): 有効にすると生成コードが通らない。省略可のキーは上のとおり条件付きの展開で省き、`undefined` の明示で省く書き方に頼らない。
- **S3(EP-03 `registerSource`)**: `source_id`・`connector_type`・`connector_config`(`file_system` の 5 項目を**常に全部**。空配列・`false` も省略しない。admin-view 10.4)・`ttl_days` か `ttl_seconds` の一方・`ratio_threshold_percent`・`min_delete_count`・`schedule_cron`(空は `null`)。
- **S4(EP-04 `updateSource`)**: 上から **`source_id`・`connector_type` を除く**(含めると 400 `unknown_field`)。全置換なので、必須項目を省略しない。
- **`Content-Type`**: 本文があるとき(EP-03・04・06)は `application/json` を必ず付ける(B 2.12。ないと 400)。生成 SDK の該当 3 関数は自動で付ける(確認 2026-11-26。0005 の生成物)。本文が空なら Content-Type は問われず `{}` として扱われるが、EP-06 も画面は常に JSON 本文を付ける。
- **EP-06(`startCrawl`)**: `{ "force_delete": <真偽値>, "rewrite_mode": <真偽値> }`(画面は常に両方を明示する)。EP-05・07・08 は**本文なし**。
- **DLG-4(再実行)で `force_delete`・`rewrite_mode` が `null` のとき**(FARC-P-46。承認済みの案(ゲート4。2026-11-26。G4-6)。確認 2026-11-26。0004 J-E8): 再実行は J2 の元ジョブの値を引き継ぐ(AF-U-7。読み取り専用で提示する)。しかし J2 の `force_delete`・`rewrite_mode` は `boolean | null` で、記録が読めないと `null` になる。EP-06 の本文は `null` を受けない(400 `type`)ため、そのまま渡せない。**`null` は「指定なし」として `false` を送り、DLG-4 には「記録なし(なしとして実行)」と読み取り専用で表示する**。破壊的な指定(`force_delete=true`)を推測で付けない。

| J2 の値 | 送る値 | DLG-4 の表示(読み取り専用) |
| --- | --- | --- |
| `true` | `true` | 画面仕様どおり(jobs 2.10) |
| `false` | `false` | 画面仕様どおり |
| `null` | `false` | 「記録なし(なしとして実行)」。項目ごとに判定する(片方だけ `null` でもよい) |

J2 の概要の「起動時の指定」で `null` のとき(DLG-4 の外)は、5.9 の (b)(「—」+視覚的に隠した「読み取れません」。導出)。DLG-4 の文言は画面仕様にないため、画面仕様への追記は HO(I-124)。

### 7.6 S4 で読めない設定項目があるとき(FARC-P-28。AAPI-U-10・AAPI-P-34 への回答)

EP-02 は、保存済みの設定項目が読めないとき、その項目を `null` にして `unavailable.<項目名>=malformed` を付ける(B 3.2。S4 が修復できるようにするため)。EP-02 の応答型は、設定項目がすべて null 許容(5.2)。S4 は全置換のため、`null` のままの項目を送ると、読めなかった値を別の値で上書きする。そこで(案):

- 読めない項目があるときは、フォームの上部に warning アラート「保存されている値を読めない項目があります。入力し直して保存してください」を出し、その項目を**空欄・必須**にする(画面仕様の検証の対象。既定値は補わない)。
- **`connector_config` が読めないとき**(5 項目をまとめて再入力させると、意図しない設定になりうる)は、フォームを出さず、S4 の取得失敗と同じエラーブロックにする(`config_invalid` などで直せる範囲を超えるため。Crawler API で直す旨を案内する)。
- この状態は画面仕様にない(I-87)。画面仕様の追記は HO。

### 7.7 保存値が小数第 3 位以下を持つしきい値(FARC-P-29。AAPI-P-38 への対応。案)

Crawler の API を直接使って登録された値(例 `0.12345` → 応答は 12.345 %)は、応答の `ratio_threshold_percent` が小数第 2 位を超える(B 2.8)。そのまま再保存するとリクエストの検証で `format` になる(秒指定のような逃げ道は B にない)。画面の扱い(B 2.8 が画面の責務とした点。画面仕様にない。I-87):

- S4 の読み込み時、応答の値が小数第 2 位を超えるかを判定する。**判定に `String(n)`(文字列表現の桁を数える方法)を使わない**(S-E7。確認 2026-11-26): 極小の値は指数表記になり(`String(1e-7)` は `'1e-7'`。Node で実行して確認)、桁を数え誤る。`Number(n.toFixed(2)) !== n` なら小数第 3 位以下を持つ、とする(承認済みの案(ゲート5。2026-11-26。G5-2)。導出: 小数第 2 位までの十進数は `toFixed(2)` で往復しても同じ値になる。`12.35`・`99.99`・`12` は偽、`12.345`・`1e-7`・`0.12345` は真になることを確認)。実装は F 3.5 の `units.ts`。
- 超えるときは、入力欄に**小数第 2 位に丸めた値**を入れ、項目の下に注意(「保存されている値は 12.345 % で、小数第 3 位以下があるため、12.35 % に丸めて保存されます」。丸め方は四捨五入を案とし、文言は画面仕様に委ねる)を出す。**丸めに `toFixed(2)` をそのまま使わない**(2 進の誤差で `(2.675).toFixed(2)` は `'2.67'`、`(1.005).toFixed(2)` は `'1.00'` になり、四捨五入の期待とずれる。確認 2026-11-26。Node で実行)。丸めの実装は十進で行い、境界値(`2.675`・`1.005` など)を単体テストで確認する(10.1)。
- 利用者が丸めた値を見て保存することを確認とみなす(追加の確認チェックは置かない)。値を変えずに他の項目だけ編集して保存しても、しきい値は丸めた値に更新される点を注意に含める。
- S2 は、保存値を丸めずに表示する(応答の値のまま)。判断が変わる(API が丸めを受ける)なら B のゲート3で決まる(B 2.8)。

---

## 8. 状態管理

**Pinia は使わない**(DS 10.1 の案を踏襲。承認済みの案(ゲート3)。FARC-P-17)。状態は次の 4 か所に置く(v0.1 から追記のみ。末尾の箇条書きに API クライアントの設定を足した)。

| 種類 | 置き場 | 例 |
| --- | --- | --- |
| サーバーの状態 | TanStack Query(5章) | 一覧・詳細・ダッシュボード・メタ。**最終取得成功日時**は `dataUpdatedAt` |
| 画面の条件 | **URL のクエリ**(唯一の正。5.6) | `page`・`size`・`sort`・`source`・`status`・`tab`・O1 の `q`・`state` |
| 画面内の一時の状態 | コンポーネントの `ref`(フォームの値、ダイアログの開閉、折りたたみ、D1 の自動更新スイッチ) | S4 のフォーム値、DLG の入力確認の文字列 |
| アプリ全体で 1 つの UI | 小さな composable(モジュール内の `ref`)。**永続化しない** | スナックバー、ドロワーの開閉 |

- `localStorage` などへの保存はしない(ユーザー設定を持たない。dashboard 4.1)。
- クエリの値を `ref` に**複製して二重に持たない**(ズレの原因になる)。key・API 呼び出し・`VDataTableServer` の表示は、URL から正規化した `params` だけから作る(5.6)。
- API クライアントの設定(5.3)は、起動時に 1 回だけ行うモジュール単位の設定で、画面の状態ではない。

---

## 9. アクセシビリティ・Vuetify 利用上の注意

### 9.1 アクセシビリティ

方針・規約は DS 8章が正(キーボード・フォーカス・ラベル・状態の伝え方・動的更新・コントラスト)。本書が決める実装上の要点(v0.1 から変更なし。外部通信の行だけ `web` 前提に合わせた):

| 項目 | 方針 |
| --- | --- |
| 画面遷移 | パスが変わったときだけ `h1`(`tabindex=-1`)にフォーカス。`document.title` を更新(4.5) |
| 動的更新 | ポーリング・自動更新は読み上げない(`aria-live` なし)。操作の成功は `role="status"`、取得失敗は `role="alert"`(6.6) |
| 状態ブロック | 読み込み中は `aria-busy="true"` と視覚的に隠した `role="status"`(DS 4.5) |
| ダイアログ | フォーカスの閉じ込め・復帰・Esc は DS 4.8。**Vuetify の `VDialog` で実際に満たされるかは実機確認**(DS 8章。FARC-U-14) |
| 外部通信 | ランタイムで外部へ取得しない(フォント・アイコン・CSS・CDN。DS 3.1)。ブラウザから見える接続先は `web` の同一オリジン(`/admin/` と `/api/`。3.3)だけ。Playwright で、同一オリジン以外への要求がないことを確認する(10.2) |

### 9.2 Vuetify の設定・注意(参照)

設定値の正本は DS 3章。実装時に守る点:

- **`main.ts` で `import 'vuetify/styles'` する(必須)**。`vite-plugin-vuetify` はコンポーネント単位の CSS しか入れず、これがないとリセット CSS・タイポグラフィ・ユーティリティ(`d-flex` など)が入らず、ブラウザ既定のフォントになる(確認 2026-11-26。0005。3.1)。`styles.configFile` の変数もここに効く。
- **`styles.configFile` を使う(DS 3.3)ので `sass` が必須**。dependencies に入れる(ないと `Preprocessor dependency "sass-embedded" not found` でビルドが失敗する。`sass-embedded` は不要。確認 2026-11-26。0005。3.1)。`styles.configFile` の SASS 変数が成果物の CSS と実機の表示に反映されることは確認した(0005)。
- `createVuetify` に `display.mobileBreakpoint: 'md'` を**明示**(既定は `lg`)。`VNavigationDrawer` に静的な `permanent` を付けない(DS 3.1・3.2・7。4.1)。
- `vite-plugin-vuetify` で必要な部品だけを取り込む(tree-shaking。`autoImport: true`)。アイコンは `@mdi/js` から**名前付き import**し、`@mdi/font`・CDN の `<link>` は使わない(DS 3.1)。`vite-plugin-vuetify` に Vite 8 の明示対応の記述がない点は FARC-U-20(実機でビルドは通った。3.1)。
- `defaults` のマージ規則が v3 と異なる(DS 3.2)。見え方は画面で確認する。
- Vuetify の部品の props・挙動(`VDataTableServer` の `hover`、`VAlert` の左帯の色、`VBreadcrumbs` の `divider`、`VExpansionPanels` の遅延描画と検証、`VBtn` の `aria-disabled`、density と高さ)は DS が「実機 4.3.4 で要確認」とする。本書は新しい確認事項を足さず、実装後に `web-ui-reviewer` が確認する(DS 14章。FARC-U-14)。`VDataTable` の列定義の型は `VDataTable['$props']['headers']` で付けられる(確認 2026-11-26。0005)。**`VDataTableServer` は未確認**(FARC-U-2)。
- Vuetify は週次でリリースされる。exact pin し、更新は検証してから行う(DS 10.3。2.2)。

---

## 10. テスト方針

テストコード・設定ファイルは作らない(FARC-P-38)。方針と設定の要点だけを書く。ディレクトリ・フィクスチャ・モジュール別のテストの種類は F 7章が正本。

### 10.1 Vitest(FARC-P-21。承認済みの案(ゲート3・4))

- **対象**: 純粋なロジックを中心にする。エラー変換表(6.3 の全 code)・実行時エラーの正規化(5.3 の表の全行)・パス値の検証、URL ↔ `params` の変換・正規化、`refetchInterval` の関数(D1・J2)、検証規則の純関数、単位・モード(日・秒)の扱い、`StatusTag` の対応表、key factory(`withKey` を含む)、ナビの抽出・並び(`meta`)、`toRequest`、`cellState`・`expectedFields`(5.9)。コンポーネントは props と状態の出し分け(ダイアログの有効・無効、状態ブロック)まで。**レイアウト・コンテナクエリ・フォーカスの実挙動は Playwright と実機**(10.2・10.3)。モジュール別の対応は F 7.2。
- **環境と Node の要件**(承認済みの案(ゲート4。2026-11-26)): **jsdom 31 を採用**する(FARC-P-21)。jsdom 31 の engines が Node の下限 `^22.22.2 || ^24.15.0 || >=26` を決める(2.2。FARC-P-3)ので、CI とローカルは 24.15.0 以上の 24 系(`.nvmrc`。`engine-strict=true`)で実行する。Vuetify 4.3.4 の部品(`VDataTableServer`・`VDialog`・`VNavigationDrawer`)が jsdom で動くかは**未確認**で、動かなければ Browser Mode に替える(FARC-U-9)。
- **設定の要点**(DS 10.1): Vuetify を使うため `test.server.deps.inline: ['vuetify']`、`ResizeObserver` のモック(setup)、マウントは `createVuetify()` と `VLayout` で包む共通ヘルパー(F 7.1)。
- **API の扱い**: ネットワーク層(`fetch`)を差し替え、**生成クライアントを実際に通す**。`QueryClient` はテストごとに新しく作り、`retry: false`。ライブラリによるモックサーバー(MSW など)は足さない(案)。
  - **相対 `baseUrl` の扱い**(確認 2026-11-26。0005 の 3a): 生成クライアントの `baseUrl` は相対(`/api/admin/v1`)で、**Node 単体では `new Request()` が `Invalid URL` になり、生成クライアントは `{error: TypeError}` を黙って返す**(`throwOnError: false` のとき)。**jsdom 環境で相対 `baseUrl` の `Request` が解決されるかは未確認**(0005 は確かめていない。Node 標準の `Request` が使われるなら解決されない可能性がある。推測。FARC-U-9。F の FMOD-U-6・U-12 と合わせて確認する)。**実装時に確認し**、解決しないときは、**テストの setup で `client.setConfig({ baseUrl: <絶対 URL> })`**(例 `http://localhost/api/admin/v1`)を呼ぶ(`client.ts` にテスト用の形は持たせない。F 3.3)。その場合も、`baseUrl` が `/api/admin/v1` であることの確認(5.3)は、`configureApiClient()` 直後の上書き前の値で別に行う。
- **時刻**: `TZ` を固定し(`Asia/Tokyo`。ブラウザのローカル時刻の表示を再現可能にする。DS 4.9。setup で固定する。プロセスの開始後の変更が効かない場合は起動時の環境変数にする。実装時確認)、ポーリングは偽のタイマーで検証する。
- **エラー変換表**は、B 2.3 の全 `code`(Admin 固有 14 種+共通 6 種)を 1 件ずつ、表のデータから網羅するテストにする(code を足したときテストが落ちる構成)。
- **契約テスト**(承認済みの案(ゲート4。2026-11-26)。対象の隣の `*.contract.test.ts`。F 7.1)。モックで固定した応答では、API の変更もパスの化けも検出できないため、**コミット済みの OpenAPI JSON と、実際に送られる URL を正**とする。

| 契約テスト | 内容 |
| --- | --- |
| **`errorTable` ↔ OpenAPI の description**(FARC-P-13。S-D7) | OpenAPI の `ErrorBody.code` は string で列挙がなく、**どの code が返るかは各 EP の `responses` の説明文(`Conflict. error.code: a, b` の書式)にしか出ない**。`openapi/admin-v1.json` を読んで説明文から code を集め、(1) **OpenAPI に出る code が全部 `errorTable` にある**、(2) **`errorTable` の Admin 固有 14 種が OpenAPI のどれかの説明文に出る**ことを検証する。説明文に出る code は Admin 固有 14 種+`invalid_request`・`unavailable` の計 16 種で、`not_found`・`method_not_allowed`・`http_error`・`internal_error` は OpenAPI に宣言がない(確認 2026-11-26)ので、A 5.2・B 2.3 から作った表の側だけで網羅する。JSON は CI の「再生成して差分ゼロ」(11.2)で実装と一致が保たれるので、実行時に API を呼ばない。説明文の書式が変わるとテストが落ちる(それで検出してよい) |
| **パス値**(FARC-P-44。5.3) | `fetch` の差し替えで**実際に送られる URL**を捕捉し(生成 SDK を通す)、`job_id='a%b?c#d'` → `/jobs/a%25b%3Fc%23d`、`a/b` → `%2F`、日本語が正しくエンコードされることを検証する。**値全体が `.`・`..`・空文字、制御文字を含む値、文字列でない値は、リクエストを送らず拒否される**こと(送ると `/jobs/`・1 階層上など別の EP に化ける。確認 2026-11-26)。**`a.b`・`..a`・`a..`・`my.source` は拒否されず、そのままのパスで送られる**こと(`.` を含むだけの正当な ID を誤って拒否しない) |

- **そのほか、v0.2 で必ず置く単体テスト**:
  - `toRequest`: **`ttl_days` と `ttl_seconds` の使わない方が、キーごと存在しない**こと(`'ttl_seconds' in body` が偽。`JSON.stringify` した結果に `null` の `ttl_*` が現れない)。日・秒の両モード。前提タスク A の前(生成型が `number | null`)でも後でも同じ出力であること(7.5)。S4 は `source_id`・`connector_type` を含めない。`connector_config` は 5 項目を常に全部。
  - **PR #21 のレビュー指摘への対応で追加するテスト**(承認済みの案(PR #21 のレビュー指摘への対応。ユーザー指示 2026-11-26)): (a) S4 の `sourceId` が変わったとき(`/sources/a/edit` → `/sources/b/edit`)、フォームの値・検証エラー・サーバーエラー・送信状態が作り直され、`updateSource` に前の ID の入力が送られないこと(5.8)、(b) ヘッダー受信後に本文の受信が止まったとき、時間切れ(`timeout`)になること(5.3)、(c) `isPlaceholderData` が `true` の間、J1 の行の取消が無効になること(5.6)
  - 実行時エラーの正規化(5.3 の表の全行): 生成 SDK を通した JSON のエラー・HTML の 502・504・空本文・2xx で JSON でない本文・通信断が、すべて `ApiError` として投げられること。Query の `AbortError`(キャンセル)とタイムアウトの区別は FARC-U-22 の確認結果に合わせる。
  - `configureApiClient()` は冪等: 2 回呼んでも interceptor が二重に登録されないこと(5.3。F 7.2。承認済みの案(ゲート5。G5-3。2026-11-26))。
  - `baseUrl`: `client.getConfig().baseUrl` が `/api/admin/v1` であること(5.3)。**EP-12・13・14 のリクエスト URL に query が付かない**こと(`?` の不在。5.3)。
  - 数値の丸め・桁判定(7.7): `Number(n.toFixed(2)) !== n` の判定で `12.35`・`99.99`・`12` が偽、`12.345`・`1e-7`・`0.12345` が真。丸めの境界値(`2.675`・`1.005`)が四捨五入の期待どおりになること。

### 10.2 Playwright(E2E。FARC-P-22。承認済みの案(ゲート3・4))

範囲は**方針まで**(FARC-P-38)。画面のフローは API モックで検証し、**実 API(`web` 経由)の接続確認は別立て**にする。

| 項目 | 方針 |
| --- | --- |
| 主たる方法 | **`page.route` による API モック**(`**/api/admin/v1/**`)。画面のフロー(遷移・ガード・ダイアログ・フォーム・エラー表示・SPA 内の 404)と a11y の振る舞い(フォーカスの移動・ダイアログの閉じ込めと復帰・`aria-sort`。DS 8章)を検証する。**compose の `web`・`api` を要しない**(開発サーバーの `/api` の転送先は使われない) |
| モック応答 | **生成した型(スキーマ名の型。`{Op}Response2` は使わない。5.2)で `satisfies`** して型付けする(API の変更が型エラーになる)。エラー応答も A 5.2 の型で書く。**Nginx 由来の失敗(`text/html` の 502・503・504・413 と通信断(`route.abort()`))も作れる**ようにする(FARC-P-43。F 7.3)。1 つのフィクスチャ集と `mockApi` ヘルパーに集約する |
| 未モックの要求 | `/api/` への**未モックの要求はテストを失敗**させる(`route` の最後に補足して記録)。開発プロキシの先(`web`)に要求を流さない |
| `baseURL` | `http://localhost:5173/admin/`(**末尾のスラッシュを含める**)。遷移は**先頭にスラッシュのない相対パス**(`goto('sources')`)で書く。`goto('/sources')` は `/admin` を落として origin 直下に解決される。`request` フィクスチャの相対パスも同様に `/admin/` の下になる(実機での挙動は確認する。FARC-U-8)。`/admin`(末尾スラッシュなし)は dev サーバーでは 404(確認 2026-11-26。0005)なので、`/admin/` から始める |
| サーバー | `webServer` は `url` を `http://localhost:5173/admin/`、`reuseExistingServer: !process.env.CI`。CI では `vite preview`(ビルド成果物)を使う案。その場合、`baseURL`・`webServer` の `url` を preview のポート(既定 4173)に合わせる |
| ロケーター | ロールとラベルを第一にし、`data-testid` は DS 9章の命名に従う(`s1-sources-table`・`dlg-crawl-start`・`nav-{route 名}`・各 `*-state-*`)。本書で `data-testid` を追加しない(FARC-K-9) |
| タイムゾーン・時計 | `timezoneId: 'Asia/Tokyo'` を固定。ポーリング(30 秒・10 秒)は Playwright の時計の操作で進める(推測。実機で確認。FARC-U-8) |
| ブラウザ | 自動 E2E は **Chromium 1 つ**。Firefox 128・Safari 16.4 は実機で最小限の確認(FARC-U-15) |
| 外部通信 | 全画面の読み込みで、同一オリジン以外への要求が 0 件であることを確認する(DS 3.1) |
| 幅 | 375 / 768 / 840 / 1024 / 1280px(admin-view 8.4)で、ページ全体の横スクロールがないこと、サイドバーの出し分け(840px の境)を確認する |
| **実 API の接続確認(`web` 経由。前提タスク B+C の完了後に有効)** | **`web`(Nginx)経由で実 `api` に接続する少数のスモーク**(読み取りのみ)。**前提タスク B+C(`web` コンテナ・compose。12.8)が終わるまで実施できない**(それまでは API モックの E2E と単体テストで進める)。置き場は**リポジトリ直下**の `tests/integration/<名前>/`(`apps/web/` の外。`apps/web` の ESLint・`vue-tsc`・Vitest の対象外。F 7.1。FMOD-U-8。名前・ツールは実装時)。`baseURL` は compose の `web` の公開ポート(`http://127.0.0.1:<WEB_HOST_PORT>/admin/`)。内容(案): D1・S1・O1 が開く、`/admin/sources` の再読み込みが SPA を返す(フォールバック)、`/admin/assets/` の欠落ファイルが 404、`/api/admin/v1/…` の未知のパスが `api` の JSON の 404(A 2.2。BAPI-U-1 の確認を兼ねる)、`%2F`・`%2E` を含む `job_id` が Nginx で壊れずに `api` へ届く(FARC-U-21。期待値は `api` を直接呼んだときと同じ: `GET /api/admin/v1/jobs/a%2Fb` → 404 `not_found`、`GET /api/admin/v1/jobs/%2E` → 404 `job_not_found`。0004 の 2.5・HO-46)。変更操作は含めない。**Nginx の挙動(フォールバック・301・302・`assets/` の 404・413・タイムアウト)は、dev サーバーや `vite preview` では確かめられない**(dev サーバーでは `/admin` が 404 になるなど、Nginx と挙動が違う。確認 2026-11-26。`vite preview` は Nginx と別の実装であり、同じ挙動とは限らない。推測)ので、この接続確認(compose)で行う。起動する環境(compose の `web`・`api`・OpenSearch など)は、既存の結合テストと**ホストのポートが衝突しうる**(固定の 9200・8000・8001・8080(`api` の IT の上書き)に、`web` の `WEB_HOST_PORT` が加わる。`tests/integration/crawler/README.md`)ため、**同時に動かさない**(排他ロックと共通ファイルは `scripts/lib/` の流儀に揃える。F 7.1) |

- 代表フローの最低限(案): D1(正常・異常・stale 降格)、S1→DLG-1(受付・`lock_held` の拒否)、S3 の項目別エラー(`config_invalid`)、S4 の取得失敗でフォームを出さない、J1 のページング・絞り込みの URL 同期、J2 のポーリング停止、DLG-3 の `job_already_finished` を成功扱い、X1 のタブ・`existence`、O1 の絞り込み・stale、**書き込みの結果不明(HTML の 502・504・通信断で再試行を出さない。保存系は「もう一度保存」)**(6.5)、EP-05 の 202 の後に S2 のロック状態カードが `held_delete` になる(S1 の行はすぐ「削除中」にならない前提。5.8)。

### 10.3 実機確認が必要な点

自動テスト(jsdom・モック)では確かめられず、実機(Vuetify 4.3.4・実ブラウザ・実 API・compose の `web`)で確認する点。DS が挙げるものを再掲せず参照する。

| 点 | 内容 | ID |
| --- | --- | --- |
| Vuetify の挙動 | DS が「実機 4.3.4 で要確認」とする項目(`mobileBreakpoint`・`permanent`・`VTabs`・`VDialog` のフォーカス・`VDataTable` の `hover`・`VBreadcrumbs`・`VExpansionPanels`・`VBtn` の `aria-disabled`・高さ・J1 の最小幅のフォント依存)と `VDataTableServer`(`@update:options` の初期発火・単一ソート・`aria-sort`) | FARC-U-2・14 |
| テスト環境 | jsdom 31 で Vuetify の部品が動くか、相対 `baseUrl` の `Request`、`ResizeObserver` のモック | FARC-U-9 |
| ビルド | `vite-plugin-vuetify` と Vite 8 の明示対応がないこと(ビルドは通った) | FARC-U-20 |
| 配信(`web`) | Nginx の数値の最終値・ヘルスチェック・`Host`・CSP・実 `api` との結合(compose)、`%2F`・`%2E` の素通し | FARC-U-6・21 |
| API クライアント | `AbortError`・`TimeoutError` の区別、key の差し替え(`withKey`)、`AbortSignal.any` を使わない理由 | FARC-U-22 |
| API の挙動 | EP-01 の反映遅れの最大値、`stalled=true` の経路(EP-08 の `released=false` を含む) | FARC-U-23・24 |
| タイムアウト | クライアントの仮値(読 45 秒・書 90 秒)と Nginx の `proxy_read_timeout` の実測 | FARC-U-16 |
| ブラウザ | Firefox 128・Safari 16.4 | FARC-U-15 |
| スクリーンリーダー | 列見出し(O1)の読み上げなどは実機のスクリーンリーダーで(opensearch 7章) | — |

---

## 11. 静的解析・品質

### 11.1 構成(FARC-P-23。承認済みの案(ゲート3・4))

- **ESLint**(flat config): `eslint-plugin-vue`(推奨)+`typescript-eslint`。Prettier との衝突は設定の無効化で避け、整形は Prettier だけが行う。**対象外(lint・format とも)**: 生成ディレクトリ(`src/admin/api/generated/`。F 3.3)と `dist/`。生成コードは手で編集せず、4 スペース・クォート混在のため(5.2。確認 2026-11-26。0005)。**`openapi/admin-v1.json` も format の対象外にする**(API が書き出す形(`indent=2`・`sort_keys`)が正で、CI の「再生成して差分ゼロ」(11.2)が検査するため。Prettier が整形し直すと差分が出る可能性がある。推測・未検証)。
- **TypeScript**: `strict: true`。`vue-tsc --noEmit` で `.vue` を含めて検査する(`vite build` の前。Vite は型を検査しない)。**生成ディレクトリは型検査の対象に含める**(除外するのは lint・format だけ。F 2.4)。**`exactOptionalPropertyTypes` は有効にしない**(FARC-P-45。確認 2026-11-26。0005): 有効にすると生成コード内で 12 件の型エラー(TS2379)と、`@tanstack/vue-query` の d.ts のエラー(TS2416)が出る。`strict`・`noUncheckedIndexedAccess`・`noUnusedLocals`・`noUnusedParameters`・`noImplicitOverride` は、`skipLibCheck` の有無にかかわらず通る(確認。追加の採否は実装時)。省略可のキーは条件付きの展開で省く(7.5)。`vite.config.ts` を型検査する場合は `tsconfig.node.json` に `@types/node`(`^24`)と `"types": ["node"]` が要る(3.1)。
- **依存方向の機械検査**は F 6章(R1〜R17)が定める(Crawler・Indexer の AST 検査に相当。R17 は「`admin/api` は `admin/` 内の他モジュールを import しない(`shared/api` と自分の `generated/` のみ可)」で、`admin/api/errors/` などは公開口 `@/admin/api` 経由に統一する。承認済みの案(ゲート5。G5-3。2026-11-26))。手段の第一候補は ESLint の `no-restricted-imports`(例: 生成クライアントと `fetch` を使えるのは `admin/api` だけ。`/api/admin/v1` の文字列は `admin/api/` と `shared/api/` の中だけ。`@mdi/font` の禁止)。生成ディレクトリは検査の対象外だが、生成ディレクトリを外から import することの禁止(R2)は import する側に掛かる。
- スクリプト(要点): `dev`・`build`(`vue-tsc --noEmit` → `vite build`)・`preview`・`typecheck`・`lint`・`format` / `format:check`・`test`・`test:e2e`・**`gen:api`(「OpenAPI の書き出し → `openapi-ts`」の 2 段。書き出しは `apps/api` の Python 環境を要する。5.2)**。`web` イメージのビルドでは `gen:api` を実行しない(3.5)。
- Node は `.nvmrc`・`engines`・`engine-strict=true` で固定する(2.2。FARC-P-3)。

### 11.2 品質ゲートの順(承認済みの案(ゲート3)。FARC-P-6・23。ゲート4 で生成の再実行を維持。FARC-P-45)

| 順 | 手順 | 内容・失敗の意味 |
| --- | --- | --- |
| 0 | `npm ci` | `package-lock.json` を正にする。Node が範囲外なら `engine-strict` で失敗する |
| 1 | **`gen:api`(OpenAPI の書き出し → 生成 → 差分ゼロ)** | `uv run python -m loreley_api.admin.openapi_export` で `openapi/admin-v1.json` を書き出し、`openapi-ts` で `src/admin/api/generated/` を再生成して、**コミット済みのものと差分がないこと**を確認する(`git diff --exit-code`。新規ファイルも検出するため、`git status --porcelain` が空であることでも確かめる。導出)。差分が出たら、API の定義か Hey API の版が変わったのに再生成・コミットを忘れている。以降のステップは生成コードに依存するため最初に行う(FARC-P-6) |
| 2 | `typecheck` | `vue-tsc --noEmit`(生成コードを含む) |
| 3 | `lint` | ESLint(依存方向の検査を含む) |
| 4 | `format:check` | Prettier |
| 5 | `test` | Vitest(契約テストを含む。10.1) |
| 6 | `build` | 型検査 → `vite build` |
| 7 | `test:e2e` | Playwright(API モック。10.2) |

- 依存の更新(2.2)もこの順で通す。
- **品質ゲートに含めないもの**: `web` イメージのビルドと、`web` 経由の実 API の接続確認(10.2)は compose を要するため別立てにする(前提タスク B+C の完了後。12.8)。
- CI の定義は infra の作業(コード・設定ファイルは本タスクで作らない)。手順 1 は Node と Python(`uv`)の両方が要るため、CI のジョブの環境に注意する(実装時確認)。

---

## 12. 確認状況

### 12.1 確認した事実(2026-11-26)

本書の作成時に確かめた事実と出典。「確認 2026-11-26」と本文に書いたものは、ここのいずれかによる。

1. **実 Admin API の OpenAPI との照合**(0004): 基準 SHA `6a8b685`、OpenAPI 3.1.0・12 パス・14 EP・`servers=[{url:/api/admin/v1}]`(sha256 `ce60fc1a…bf51`)。実装・テスト・実装記録・結合テスト(IT)の記録を**読解**した結果で、EP-01〜14 のパス・メソッド・本文項目・応答の主要項目・HTTP ステータス・`code` は大筋一致。差分は 12.7。「実機確認」は IT で確認済みのもの(AIT-10・11・12・20・31・41・50・51・60・90〜92)に限る。サーバー・Nginx は 0004 では起動していない。
2. **依存の版・Node 要件**(0004 の 4 章): npm レジストリの package.json・公式ドキュメント・GitHub Releases による(主要な値は `npm view` と突き合わせた)。2.1・2.2。Node の LTS の状況も同じ。
3. **リポジトリ外の使い捨ての技術検証**(0005。Node 24.22.3・npm 11.6.2・Docker 20.10.13・nginx/1.31.10。`apps/web/` は作っていない):
   - Hey API 0.99.0 による生成(既定設定で 17 ファイル・4,349 行・約 114KB。同一入力 3 回と別ディレクトリで差分 0)、`vue-tsc` strict での通過、`throwOnError`・実行時エラーの形、パスのエンコード、`exactOptionalPropertyTypes` での 12 件の型エラー、Node 単体の相対 `baseUrl` の失敗。
   - Vite 8.3.8 + Vuetify 4.3.4 のビルド(`vuetify/styles`・`sass`・`@types/node` の要否)、`styles.configFile`、tree-shaking、外部参照 0 件、既定の `build.target`、`vue-router` 5.5.1 の無改変動作、開発サーバーとプロキシ。
   - Nginx 配信(`nginx -t`・curl・Chromium(playwright-cli)): `/admin/` のフォールバック、`assets/` の 404 とキャッシュ、301・302、プロキシの素通し、1 MiB の 413、upstream 停止時の HTML の 504。**upstream はダミー**。
   - P2-b で install した版(Vite・Vuetify・`vite-plugin-vuetify`・`@vitejs/plugin-vue`・Vue Router・Vue・TypeScript・`vue-tsc`・`sass`・`@mdi/js`・`@types/node`)の `npm install`・`npm ci` で、peer・engines の警告・deprecated が 0 件、`npm audit` 0 件。Vitest・jsdom・Playwright・ESLint・Prettier・`@vue/test-utils`・Hey API との同時 install は含まない(FARC-U-25)。
4. **E v0.2 の 5・7 章の執筆時に、リポジトリ外のスクラッチで追加確認**(作業記録 0004・0005 にはない。本書が記録する):
   - **生成物の規模**: `infiniteQueryOptions: false` で 17 ファイル・4,260 行・約 111KB。5.2 の「約 111KB」はこの値(`@tanstack/vue-query.gen.ts` は 375 行から 286 行。0005)。
   - **生成クライアント 0.99.0 の挙動**: `error` interceptor が受け取る値は、JSON のエラー(`error.code` を持つ)でパース済みオブジェクト、HTML・空の本文で `string`(空は `''`)、2xx で JSON でない本文で `SyntaxError`、接続失敗で `TypeError`。**interceptor が返した値がそのまま投げられる**。request interceptor の例外は `error` interceptor を通る。request interceptor に渡る **`opts.path` は元の値(`.` など)のまま**で、URL だけが壊れる。
   - **key の差し替え**: `{ ...xxxOptions(…), queryKey: … }` をそのまま `useQuery` に渡すと**型エラー(TS2769)**になる(key の型に `staleTime` などの型が結びつくため)。key の型を合わせるヘルパー `withKey(options, key)` を通すと通る。実行時は、生成された `queryFn` が `xxxOptions` の引数から URL を作るので、key を差し替えても正しい URL へ送られる(`['sources','detail',id]` で確認)。
   - **数値**: `String(1e-7)` は `'1e-7'`、`(1.005).toFixed(2)` は `'1.00'`、`(2.675).toFixed(2)` は `'2.67'`(Node で実行)。`Number(n.toFixed(2)) !== n` は、`12.35`・`99.99`・`12` で偽、`12.345`・`1e-7`・`0.12345` で真。
5. **実 OpenAPI の再読**(本節の作成時。上と同じ JSON): 14 EP・12 パス・`servers`・EP-12・13・14 が query を持たないこと、`unavailable` を持つスキーマ(`SourceDetailResponse`・`JobDetailResponse`・`DocumentListResponse`・`SourceListResponse`・`JobListResponse` と各行の型)、各 EP の `responses` の説明文に出る code(16 種)、`ErrorBody` の項目、`RegisterSourceBody`・`UpdateSourceBody` の `ttl_*`(`integer | null`・既定 null)、`SourceSettings` と `SourceDetailResponse` の `required`、`ReleaseLockResponse`、`ComponentId` の説明文(「`web` は compose のサービスではなく、`api` が配信する Web UI の表示名」)。
6. **v0.1 の確認**(2026-11-22・23): A・B・DS・画面仕様・作業記録との照合。ゲート3で承認済み。v0.2 の本文は、これを実 OpenAPI と 0003〜0007 で更新した。

**確認していないこと**: 12.4 の FARC-U 全件。特に次。
- Nginx 越しの `%2F`・`%2E` の保持、実際の `api`(compose の `web`)との結合、`proxy_read_timeout`・`client_max_body_size` の最終値(0005 はダミーの upstream。FARC-U-6・21)。
- `VDataTableServer` の挙動(FARC-U-2)、Firefox 128・Safari 16.4 の実機(FARC-U-15)、`vite build` の Docker マルチステージ化(FARC-U-26)。zod・valibot の `responseValidator`(0005 の未検証)は本書が使わないので、FARC-U にしない。
- 依存全体(Vitest・jsdom・Playwright・ESLint・Prettier・`@vue/test-utils`・Hey API を Vite 系と同時に install した状態)の `npm ci`・`npm audit`(FARC-U-25)。
- `TimeoutError`・`AbortError` が `error` interceptor に届くか(5.3 の表のこの 2 行は設計で、確認していない)、`AbortSignal.any` が Safari 16.4 で使えないこと(推測)。FARC-U-22。
- jsdom 31 で相対 `baseUrl` の `Request` が解決されるか、Vuetify の部品が動くか(10.1。FARC-U-9)。
- `stalled=true` の経路・EP-08 の `released=false`(FARC-U-24)、EP-01 の反映遅れの最大値(FARC-U-23)、S1 の `status=null` が実データで出るか・EP-09 の複数ページ・10,000 件の窓(FARC-U-26。IT でも未検証)。
- Playwright の時計の操作(FARC-U-8)、Vue Query v5 の `isLoading` の意味(5.7。推測。FARC-U-26)。

### 12.2 確定(FARC-K)

確定にしたのは、ユーザーの回答・指示と、既承認文書(ユーザー承認済みの DS・画面仕様)の引用だけ。承認済みの案の引用や、ゲート1〜5 で承認された方針・値は確定にしない(12.3)。FARC-K-2・5〜8 は欠番。

| ID | 内容 | 出典 |
| --- | --- | --- |
| FARC-K-1 | Vuetify 4.3.4(exact pin)、TypeScript 6.x 固定、`@mdi/js`(`vuetify/iconsets/mdi-svg`)、自前ナビ(`VNavigationDrawer` + route `meta`) | DS 10.1(承認済み(ゲート B 2026-11-21)) |
| FARC-K-2 | (欠番) | — |
| FARC-K-3 | 対応ブラウザ: Chromium 119+ / Firefox 128+ / Safari 16.4+ | DS 10.1(ユーザー了承済み) |
| FARC-K-4 | **(v0.2 で更新)** Web UI は **`web` コンテナ(Nginx)が静的配信し、`/api/` を `api` へプロキシする**(ブラウザから見て同一オリジン。CORS 不要)。`api` は静的ファイルを配信しない | **確定(ユーザー指示 2026-11-26。作業記録 0003)**。v0.1 の「`api` が静的配信する」(BAPI-K-2。ユーザー回答 2026-11-22。`create_admin_system_design`(前タスク)の 0001 Q2)と要件 0000 の「API サーバーから静的配信する構成を基本とする」を上書きする |
| FARC-K-5〜8 | (欠番) | — |
| FARC-K-9 | 日本語のみ・ライトテーマのみ・システムフォントを使い外部フォントと CDN を使わない(DS 前提 2〜4)。要素の特定はロール・ラベル基準で、必要な箇所だけ `data-testid`(前提 6) | DS 0.1 の前提 2〜4・6(承認済み)の引用。ランタイムの外部通信全般の禁止(DS 3.1)は DS 3 章(案のまま)で、本書は同じ方針を採る(FARC-P-32) |

### 12.3 案・承認済みの案(FARC-P)

v0.1 の FARC-P-1〜39 は、ゲート3(2026-11-23)で承認された内容を保って引き継いだ(承認済みの案(引用)・導出・解釈の扱いは G3-3 でユーザー確認済み)。**v0.2 で変更・追加したものは、区分欄に「承認済みの案(ゲート4。2026-11-26)」と書いた**。ゲート4 の後に承認された設計の詳細と軽微な導出・誤記訂正は「承認済みの案(ゲート5。2026-11-26)」(G5-1〜G5-3。0012)と書き、FARC-P-1・25・26 の v0.2 の追記は「導出(0004・0005)」と注記した。区分欄は承認したゲートを書く(ゲート1=方針、ゲート2=具体値・名前。いずれも 2026-11-22)。確定(`-K-`)にはしていない。

| ID | 内容 | 区分 | 章 |
| --- | --- | --- | --- |
| FARC-P-1 | 型・クライアント・Query 生成は Hey API(`@hey-api/openapi-ts`。exact pin)。入力は Admin API の OpenAPI の書き出し(`openapi_export`。サーバー起動不要)。生成設定は FARC-P-45 | 承認済みの案(ゲート2。BAPI-P-10)。v0.2 の追記(生成設定は FARC-P-45)は導出(0004・0005) | 2.1・5.2 |
| FARC-P-2 | **(v0.2 で変更)** `base: '/admin/'`、history モード。**配信は `web`(Nginx)の `try_files`**: `/admin/assets/` の欠落は 404、`/admin/` 配下のそれ以外の欠落ファイルは `index.html`(200)。`Accept` は見ない。`/admin` は 301、`/` は 302 `/admin/`(v0.1 は `app.frontend()` で、`/admin/` 配下の `Accept: text/html` の GET/HEAD だけ `index.html`) | 承認済みの案(方針はゲート1、範囲はゲート2。BAPI-P-2)。**変更は承認済みの案(ゲート4。2026-11-26)** | 3.2・3.3 |
| FARC-P-3 | **(v0.2 で変更)** Node: **`^22.22.2 \|\| ^24.15.0 \|\| >=26`**(jsdom 31 の engines が最も厳しい)。推奨 24。`.nvmrc`・`engines`・`engine-strict=true`。Docker・CI は 24.15.0 以上の 24 系(v0.1 の下限は 22.18) | 承認済みの案(ゲート3。2026-11-23。推奨は tech-advisor。0004)。**下限の引き上げは承認済みの案(ゲート4。2026-11-26)** | 2.1・2.2 |
| FARC-P-4 | **(v0.2 で具体化)** 固定範囲: exact(Vuetify `4.3.4`・Hey API `0.99.0`・Playwright `1.65.1`)、minor(Vite `~8.3.8`・`vue-tsc ~3.3.14`・Vue Router `~5.5`)、TypeScript `~6.0.3`、`vite-plugin-vuetify`(2.1.3)・`@vitejs/plugin-vue`(6.0.11)は patch まで(`~`)、`sass`・`@mdi/js` は dependencies に明記、`@types/node ^24`、その他は caret + ロック | 承認済みの案(ゲート3。2026-11-23)。ただし Vuetify の exact pin と TypeScript 6.x 固定は確定(FARC-K-1)、Hey API の exact pin は承認済みの案(ゲート2。FARC-P-1)。**具体化は承認済みの案(ゲート4。2026-11-26)** | 2.1・2.2 |
| FARC-P-5 | npm と `package-lock.json`(`npm ci`) | 承認済みの案(ゲート3。2026-11-23) | 2.1 |
| FARC-P-6 | 書き出した OpenAPI JSON と生成コードをコミットし、CI で再生成の差分を検査(**v0.2 で維持**: 生成は決定的(既定設定(約 114KB)での確認)で、`infiniteQueryOptions: false` なら 17 ファイル・約 111KB のため、コミットで問題ない) | 承認済みの案(ゲート3。2026-11-23)。**維持はゲート4(G4-3)で承認(2026-11-26)** | 5.2・11.2 |
| FARC-P-7 | API クライアント: 生成 fetch クライアント 1 つ+薄い設定関数 `configureApiClient`(タイムアウト付き fetch(読 45 秒・書 90 秒)、`interceptors.request`(パス値の検証)、`interceptors.error`(`ApiError` への正規化))、自動再送なし。**v0.2: `baseUrl` は設定せず、生成物が spec の `servers` から持つ**(v0.1 は設定する 1 か所)。`configureApiClient()` は `main.ts` の 1 か所で呼ぶ(冪等) | 承認済みの案(ゲート3。2026-11-23。タイムアウトは仮値)。`configureApiClient()` を冪等にする点は承認済みの案(ゲート5。G5-3。2026-11-26)。v0.2 の変更(`baseUrl` 不設定・`configureApiClient()` の呼び出し・request interceptor でのパス値の検証・自前の `AbortController` 付き fetch で `AbortSignal.any` は使わない)は承認済みの案(ゲート5。2026-11-26。G5-1)。実機確認は FARC-U-22 | 5.3 |
| FARC-P-8 | Query の既定値(`retry` 1(**v0.2: `invalid_response` の 502・503・504 も対象。`timeout` は再試行しない**)・`staleTime` 0・フォーカス・再接続での再取得なし・マウント時は再取得・mutation の再試行なし・グローバル通知なし)と key factory(生成 key は差し替える。`withKey`) | 承認済みの案(ゲート3。2026-11-23。`retry: 1` は DS 10.1 の案。ライブラリの採用は FARC-P-30)。v0.2 の追記は承認済みの案(ゲート4。2026-11-26。FARC-P-43)。`withKey` は承認済みの案(ゲート5。2026-11-26。G5-1)、EP-01 の反映遅れの注記は承認済みの案(ゲート5。G5-2) | 5.4 |
| FARC-P-9 | ポーリングの実装(D1 `refetchInterval` 30 秒+スイッチ、J2 は状態に応じた関数で 10 秒)。v0.2 で変更なし | 承認済みの案(ゲート3。2026-11-23。更新間隔は承認済みの案 FARC-P-31) | 5.5 |
| FARC-P-10 | サーバー側ページング: URL ↔ Vuetify ↔ API の対応、URL を唯一の正、`push`/`replace`、同スコープだけ前回データを保持。**v0.2: EP-09 の `sort` は string で、画面側(`jobsParams.ts`)が union を持つ** | 承認済みの案(ゲート3。2026-11-23) | 5.6 |
| FARC-P-11 | 画面別の取得方針の表、mutation と invalidate の表。**v0.2: 実 OpenAPI で照合し、生成 SDK の関数名・key に直した。EP-05 の 202 の直後に S1 の行が「削除中」にならないことがある、J1 の `failed` にリース切れは含まれない、`deletion.fetched_at` は失敗時に取得時刻として出さない、EP-12・13・14 に query を付けない** | 承認済みの案(ゲート3。2026-11-23)。v0.2 の訂正・拡張は承認済みの案(ゲート4。2026-11-26。G4-7)。EP-01 の反映遅れの注記・`last_completed_at`・`connector_type` を使わない・O1 は API の並びのまま使う・`warnings[].code` は型ガードで読む、は承認済みの案(ゲート5。2026-11-26。G5-2)。S2 の `status=null` は G5-1 | 5.7・5.8 |
| FARC-P-12 | S4 は編集専用の key・`gcTime: 0`・1 度だけ初期化 | 承認済みの案(ゲート3。2026-11-23) | 5.8 |
| FARC-P-13 | エラー変換表(1 か所)、表示先 4 つ、項目別エラーの写像、想定外の診断表示。**v0.2: `errorTable`(code は string)は手書きを正本とし OpenAPI の説明文との契約テストを置く。`details` なしの `invalid_request` は想定外。本文の違反は 2 段階で返る。`ttl_days` の排他・必須は TTL 欄。添字なしの配列エラーは一覧の下、`connector_config` 単体は上部アラート** | 承認済みの案(ゲート3。2026-11-23。code 名は B 2.3。承認済みの案(ゲート2))。v0.2 の訂正・拡張は承認済みの案(ゲート4。2026-11-26。G4-7) | 6.1〜6.4・10.1 |
| FARC-P-14 | 取消の 409 `job_already_finished` は成功扱い。`lock_held` はダイアログ内アラート+「反映されていない」の明示 | 承認済みの案(ゲート2。AAPI-P-21・AAPI-P-13。表示は admin-view 7.7=ゲート B) | 6.3 |
| FARC-P-15 | 結果不明: 504・クライアントのタイムアウト・書き込みのネットワーク断は、起動系・取消・解放では再試行を出さず確認を促す。保存系(EP-03・04)は再送が安全なので再保存も出してよい。**v0.2: Nginx 由来の `invalid_response`(502・504 など。`status` を問わない)も結果不明に含める(FARC-P-43)** | 承認済みの案(ゲート3。2026-11-23)。拡張は承認済みの案(ゲート4。2026-11-26)。書き込みの `invalid_response` を `status` を問わず結果不明とする点は承認済みの案(ゲート5。2026-11-26。G5-1) | 6.5 |
| FARC-P-16 | 検証: 自前の純関数・表(`ttl` は 1 以上)。単位変換は Admin API(B 2.8)で、画面は日・%・秒モードで入力。数値は文字列で検証してから数値化。本文は B 2.12 の型の規約どおりに作る。**v0.2: フォーム用の型と送信用の型を分け、`ttl_days`・`ttl_seconds` は null を送らずキーを省く(前提タスク A の前後で同じコード)** | 承認済みの案(ゲート3。2026-11-23。単位変換の担当は承認済みの案(ゲート2。AAPI-P-14))。v0.2 の追記は承認済みの案(ゲート4。2026-11-26。G4-7) | 7章 |
| FARC-P-17 | 状態管理: Pinia なし。Query・URL・`ref`・小さな composable。永続化なし | 承認済みの案(ゲート3。2026-11-23。DS 10.1 の案を踏襲) | 8章 |
| FARC-P-18 | Router: `meta` の型(`title` は関数を許す)、`afterEach` のフォーカス・タイトル、クエリの正規化、`featureFlag` は `/meta` 由来でナビ(`SideNav`・外部リンク領域)だけが評価(I-89)、認証・離脱ガードなし、遅延読み込みを使う場合の `router.onError`。**v0.2: パス値の送信前検証の例外(値全体が `.` または `..` に等しい、空、制御文字を 1 文字でも含む、文字列でない、のいずれかのパス値は API を呼ばず「見つかりません」)** | 承認済みの案(ゲート3。2026-11-23)。v0.2 の追記は承認済みの案(ゲート4。2026-11-26) | 3.3・4.3・4.5 |
| FARC-P-19 | **(v0.2 で変更)** Vite 設定(`base`・`outDir`・プラグイン。`vuetify/styles`・`sass`・`@types/node`)、開発プロキシは `/api` を **compose の `web` の公開ポート**(`http://127.0.0.1:<WEB_HOST_PORT>`)へ転送(dev 専用の環境変数で上書き可)、ランタイム設定を持たない(v0.1 は `api` の `127.0.0.1:8080`) | 承認済みの案(ゲート3。2026-11-23)。**変更は承認済みの案(ゲート4。2026-11-26。G4-2)** | 3.1・3.4 |
| FARC-P-20 | **(v0.2 で変更)** Docker: **`web` イメージ**(`apps/web/Dockerfile`。Node 24 のビルドステージ(タグ+ダイジェスト固定)で `npm ci`・`vue-tsc`・`vite build` → Nginx イメージに `dist/` と設定を載せる)。ビルドステージで型生成をしない。`api` イメージは Web に依存しない(v0.1 は成果物を `api` イメージへ) | 承認済みの案(ゲート3。2026-11-23)。**変更は承認済みの案(ゲート4。2026-11-26)。前提タスク B+C の完了後に有効** | 3.5 |
| FARC-P-21 | Vitest: 純粋ロジック中心、**jsdom 31 を採用**(v0.1 は第一案)、`TZ` 固定、`fetch` 差し替え、エラー変換表の網羅、契約テスト | 承認済みの案(ゲート3。2026-11-23。DS 10.1 の設定要点は案)。**jsdom 31 の採用は承認済みの案(ゲート4。2026-11-26。G4-3)** | 10.1 |
| FARC-P-22 | Playwright: `page.route` モック主、生成型の `satisfies`、未モックの要求は失敗、`baseURL` は `/admin/`、Chromium のみ。**v0.2: 実 API の接続確認は、前提タスク B+C の完了後の `web` 経由のスモーク(読み取りのみ。`tests/integration/<名前>/`)** | 承認済みの案(ゲート3。2026-11-23)。v0.2 の変更は承認済みの案(ゲート4。2026-11-26) | 10.2 |
| FARC-P-23 | ESLint(flat)+ `typescript-eslint` + `eslint-plugin-vue` + Prettier、`vue-tsc`・`strict`、品質ゲートの順。**v0.2: 生成ディレクトリを lint・format の対象外にする。`exactOptionalPropertyTypes` は有効にしない。品質ゲートに「OpenAPI の書き出し → 生成 → 差分ゼロ」** | 承認済みの案(ゲート3。2026-11-23)。v0.2 の追記は承認済みの案(ゲート4。2026-11-26。FARC-P-45) | 11章 |
| FARC-P-24 | 日時の整形は `Intl.DateTimeFormat` のみ(日時ライブラリなし)。409 の `existing_job.lease_expires_at` の番兵 `0001-01-01T00:00:00.000Z` は「期限切れ」として扱い、整形しない(B 2.11・I-73) | 承認済みの案(ゲート3。2026-11-23) | 5.9 |
| FARC-P-25 | `/meta`(EP-14)は `staleTime: Infinity`。失敗は Dashboards リンク非表示・タイムゾーン警告。クエリなし | 承認済みの案(ゲート3。2026-11-23)。v0.2 の追記(クエリなし)は導出(0004・0005) | 3.1・5.7 |
| FARC-P-26 | 入れないもの: Pinia・Tailwind・vue-i18n・VueUse・検証ライブラリ・日時ライブラリ・axios(`sass-embedded` も不要) | 承認済みの案(ゲート3。2026-11-23。DS 10.1 の案を踏襲)。v0.2 の追記(`sass-embedded` も不要)は導出(0005) | 2.4 |
| FARC-P-27 | 部分失敗(B 2.2。AAPI-P-25・42。`unavailable` に載る取得失敗と、載らない値の読めない `null` は別。FARC-P-36): **単一の応答は最上位(EP-02・10・11)**、**一覧の EP は各行の `unavailable`**(キーは行内の相対パス)を、それぞれ引く関数を通す。`null` でキーがあれば取得できない、キーがなければ値がない。理由コードは画面では区別しない。**v0.2 の訂正: EP-12・13・14 は `unavailable` を持たない(D1・O1 は引かない)** | 承認済みの案(ゲート3。2026-11-23)の修正(PR #10 のレビュー指摘への対応。AAPI-P-42)。訂正は承認済みの案(ゲート4。2026-11-26) | 5.9・6.2 |
| FARC-P-28 | S4 で保存済みの設定項目が読めないとき(`malformed`): 該当項目を空欄・必須にして再入力させる。`connector_config` が読めないときはフォームを出さない(AAPI-U-10 への回答) | 承認済みの案(ゲート3。2026-11-23) | 7.6 |
| FARC-P-29 | 保存値のしきい値が小数第 3 位以下を持つとき(応答が小数第 2 位を超える): S4 は丸めた値(四捨五入が案)を入力欄に入れて注意を出し、保存を確認とみなす。S2 は丸めずに表示(AAPI-P-38 への対応)。**v0.2: 桁の判定に `String(n)` を使わない(指数表記になる)** | 承認済みの案(ゲート3。2026-11-23。B の側は同じゲート3で承認)。v0.2 の追記は承認済みの案(ゲート5。2026-11-26。G5-2) | 7.7 |
| FARC-P-30 | 構成要素: Vue 3、Vite、**Vue Router(v0.2 は 5.5.1。v0.1 は 4)**、TanStack Vue Query、Vitest、`vite-plugin-vuetify`、ESLint / Prettier、Playwright(旧 FARC-K-2) | 承認済みの案(ゲート1。2026-11-22。0002 2章がこれらを 0001 の確定事項として挙げ、ゲート1で承認された。DS 10.1 では案。区分の変更はゲート3でユーザー確認済み。2026-11-23)。**Vue Router 5 は承認済みの案(ゲート4。2026-11-26。G4-3)** | 2.1 |
| FARC-P-31 | 更新間隔: D1 は 30 秒(一時停止スイッチあり。タブが見えない間は止める)、J2 は実行待ち・実行中のみ 10 秒、S1・S2・J1・X1・O1 は手動のみ(旧 FARC-K-6。B の AAPI-P-40 と対応) | 承認済みの案(画面仕様のゲート B・C の承認事項の引用: dashboard 4.1・admin-view #26(D1)・#8(J2)・#33(S2)。ユーザー確認済み(ゲート3。2026-11-23)) | 5.5 |
| FARC-P-32 | ナビは route `meta` で一元管理、ページテンプレート 4 型、状態表示(読み込み中・空・エラー・stale)の規約、危険度別の確認ダイアログ(旧 FARC-K-5)。外部通信の禁止(DS 3.1)も同じ方針を採る | 承認済みの案(DS 4.5・4.8・5.3・6章のゲート B・C の承認事項の引用。ユーザー確認済み(ゲート3。2026-11-23)。DS 3 章は案のまま) | 4.4・7.4・9.1 |
| FARC-P-33 | 日時はブラウザのローカル時刻(`YYYY-MM-DD HH:mm`。タイムゾーン略称なし)で表示する(旧 FARC-K-7)。API の時刻の形式(UTC の ISO 8601)は BAPI-P-20(承認済みの案。ゲート3でユーザー確認済み。2026-11-23)。**ブラウザと Crawler のタイムゾーンが異なる場合の表示は DS 4.9・14章で未決**(FARC-U-19) | 承認済みの案(DS 4.9・ゲート C #36 の引用。ユーザー確認済み(ゲート3。2026-11-23)) | 5.9 |
| FARC-P-34 | S2 のロック状態カード(と J2 のリース切れのカード)の写像: `lock.state` 7 値+取得失敗 → 画面仕様の 6 種+取得失敗。`held_*` の実行待ちは「実行待ち」のタグ、`unknown` は「状態を確認できません」。**v0.2: `stalled=true` かつ `lease_expires_at=null` は「期限を確認できません(期限切れ)」** | 承認済みの案(ゲート3。2026-11-23)。v0.2 の追記は承認済みの案(ゲート4。2026-11-26) | 5.10 |
| FARC-P-35 | `lock_held`・`lock_in_use` の導線: `existing_job.status`(または `job_type`)が `null`(`orphan`・`just_acquired`・`unknown`)のとき、「ジョブを表示」(J2)を出さず、S2 のロック状態カードへ導く。admin-view 7.7 との差は I-88。**v0.2: `null` に加え、未知の値のときも J2 へ導かない** | 承認済みの案(ゲート3。2026-11-23。ゲート3でユーザー確認済み)。v0.2 の追記は承認済みの案(ゲート4。2026-11-26) | 6.3 |
| FARC-P-36 | 値の読めない `null`(ジョブ記録・削除記録・ロック文書など。B 2.2・2.11。AAPI-P-25)と取得失敗(`unavailable`。一覧は各行・単一は最上位)の表示: どちらも「—」で、取得失敗は「取得できません」(表示の見える・隠すは画面仕様に従う)、読めない `null` は視覚的に隠した「読み取れません」。`status=null` のジョブにはタグ・操作を出さない。**v0.2 の拡張: S1 の `status=null` の行も(S2 も)「削除中」の判定も操作も出さない。値があるはずの項目の表 `expectedFields` は EP・行型ごとに持つ。EP-12 の状態値は union+ガードで未知値は中立表示** | 承認済みの案(ゲート3。2026-11-23)の修正(PR #10 のレビュー指摘への対応。AAPI-P-42)。拡張は承認済みの案(ゲート4。2026-11-26。G4-7)。S2 の `status=null` は承認済みの案(ゲート5。2026-11-26。G5-1) | 5.9・5.7 |
| FARC-P-37 | `rerun_blocked_reason=source_missing` は「再実行」を出さない(削除済みのソースを再実行しない)。`rerunnable=null`(設定の読み取り失敗を含む)も出さない。専用文言は画面仕様に足す(HO-30) | 承認済みの案(ゲート3。2026-11-23。AAPI-P-41) | 6.7 |
| FARC-P-38 | E2E は方針までを設計し、テストコード・設定ファイルは作らない(旧 FARC-K-8) | 承認済みの案(ゲート1。0003 で作業プラン 0002 を承認)。「方針までを設計し、実装コードは作らない」は要件 0000 のスコープ外(ユーザー記載)と 0002 に基づく。「テストコード」の部分は承認済みの案(ゲート3。2026-11-23) | 10 |
| FARC-P-39 | 一覧の EP(EP-01・09・11)の `unavailable` を**行単位**で判定する: 各 `items[i].unavailable`(キーは行内の相対パス)で取得失敗を判定し、最上位の `unavailable` は行に属さない項目(EP-11 の `tab_counts.<タブ>`・`document_count`)だけ。旧規則「一覧でキーがあり行が `null` なら取得できません」は廃止。単一の応答は最上位のまま(**v0.2 の訂正: 最上位が意味を持つのは EP-02・10・11 だけ。EP-01・09 の最上位は常に `{}`**) | 承認済みの案(ゲート3。2026-11-23)の修正(PR #10 のレビュー指摘への対応。AAPI-P-42)。**`-K-` ではない**。訂正は承認済みの案(ゲート4。2026-11-26) | 5.7・5.9 |
| **FARC-P-40** | **Nginx の配信方針**: `/admin/` は `try_files $uri /admin/index.html`+`Cache-Control: no-cache`、`/admin/assets/` は `try_files $uri =404`+`public, max-age=31536000, immutable`、`/admin` は 301、`/` は 302 `/admin/`(Search View の置き場が決まるまで。BAPI-U-4)、`/api/` は `proxy_cache` なしで upstream の `Cache-Control` を素通し、`absolute_redirect off`、gzip。`add_header` は子 location に継承されないため location ごとに書く。数値の最終値は実装時確認 | 承認済みの案(ゲート4。2026-11-26。G4-1)。実機確認は 0005 | 3.3 |
| **FARC-P-41** | **`/api/` のプロキシ**: `set $api_upstream http://api:8080;`+`proxy_pass $api_upstream;`+`resolver 127.0.0.11`(`api` 未起動でも nginx が起動)。URI 部なしで元の URI を渡す。`proxy_read_timeout` は 5.3 の書き込みタイムアウト(90 秒)以上(仮値 90 秒)、`proxy_connect_timeout` は数秒、`client_max_body_size` は `api` の上限(1 MiB)より少し大きく。`web` は `depends_on: api`(`service_healthy`)。`web` のヘルスチェックの手段は実装時確認 | 承認済みの案(ゲート4。2026-11-26。G4-1・G4-5) | 3.3・3.6 |
| **FARC-P-42** | **公開範囲(0007 の 2 章で置き換え後の内容)**: **`web` だけを `127.0.0.1` に publish する**(ホスト側のポートは `WEB_HOST_PORT`。既定値は 8080・8000・8001・9200 と重ならない値で、実装時に決める)。**`api` は compose の `ports` を持たず、内部ネットワークのサービス名(`api:8080`)だけで到達できる**。ブラウザ・開発・結合テストのすべてが `web` 経由、または自前の上書き(IT は `compose.test.yaml` が `api` を `127.0.0.1:8080` に publish)で接続する。認証なしの破壊的操作の入口が 1 つになる。HO-40・41 の注意書きは `web` に対して適用する | 承認済みの案(ゲート4。2026-11-26。G4-1・G4-2。0007 の 2 章) | 3.6 |
| **FARC-P-43** | **Nginx 由来の失敗**: 502・503・504・413 は HTML のため `ApiError.kind='invalid_response'`(`status` つき)。**読み取り**は 1 回だけ再試行しエラーブロック。**書き込み(EP-03〜08)の 502・504・`invalid_response`・通信断は結果不明**(再試行を出さず確認を促す。FARC-P-15 の拡張)。保存系(EP-03・04)は再送が安全の例外を維持。1 MiB 超の 413 は `client_max_body_size` を `api` の上限より少し大きくして `api` の JSON 400 を出させる。Nginx の `error_page` で JSON は返さない(0006 の「EP-04〜08」は誤記で、書き込みは EP-03〜08) | 承認済みの案(ゲート4。2026-11-26。G4-5)。書き込みの EP を EP-03〜08 とする訂正は承認済みの案(ゲート5。2026-11-26。G5-2。追認) | 3.3・5.4・6.5 |
| **FARC-P-44** | **実行時エラーの正規化層**: 生成クライアントが投げる値は型(`ErrorResponse`)と食い違い、`string`(HTML)・`TypeError`・`SyntaxError` などになる。`client.interceptors.error` に正規化の関数を 1 つ登録して、`AbortError` を除き、投げる値を `ApiError` にし、Query 側は `error` を `unknown` として型ガード `isApiError` で確認する。本文が JSON で `error.code` が string かどうかで、JSON のエラーと Nginx の HTML を区別する。代案のラッパー関数は採らない(実機確認は FARC-U-22) | 正規化層を置くことは承認済みの案(ゲート4。2026-11-26。G4-7)。方式の細部(`interceptors.error` への 1 つの登録・request interceptor でのパス値の検証と合成した 400 `invalid_request`・自前のタイムアウト)は承認済みの案(ゲート5。2026-11-26。G5-1)。`AbortError` をそのまま通す点は導出(Query の破棄・キャンセルの結果は使われないため) | 5.3 |
| **FARC-P-45** | **生成設定とビルド設定**: `@hey-api/client-fetch`・`typescript`・`sdk`・`@tanstack/vue-query`(`infiniteQueryOptions: false`)。`exactOptionalPropertyTypes` は有効にしない(生成コードが通らない)。`main.ts` で `import 'vuetify/styles'`、`sass` を dependencies に(`styles.configFile` 使用時に必須)、`vite.config.ts` を型検査するなら `@types/node ^24` と `types: ["node"]`、`build.target` は既定のまま。生成ディレクトリは lint・format の対象外 | 承認済みの案(ゲート4。2026-11-26。G4-7)。実機確認は 0005。生成物の置き場 `src/admin/api/generated/`(F 3.3)は承認済みの案(ゲート5。2026-11-26。G5-1) | 3.1・5.2・11.1 |
| **FARC-P-46** | **DLG-4(再実行)の `force_delete`・`rewrite_mode` が null のとき**: null は「指定なし(false)」として送り、DLG-4 に「記録なし(なしとして実行)」と読み取り専用で表示する。破壊的な指定(`force_delete=true`)を推測で付けない | 承認済みの案(ゲート4。2026-11-26。G4-6) | 5.8・7.5 |

### 12.4 未決・実装時確認(FARC-U)

解消したものは削除せず、状態欄に「解消(v0.2。根拠)」と書く。FARC-U-1〜19 は v0.1 の ID、20〜26 は v0.2 の新規。

| ID | 内容 | 状態(v0.2) | 決める場所 |
| --- | --- | --- | --- |
| FARC-U-1 | `vite-plugin-vuetify` 2.1.x と Vite 8(Rolldown)の組み合わせ(開発・ビルド・`styles.configFile`)、`sass` の要否 | **解消(v0.2。0005)**: Vite 8.3.8 + Vuetify 4.3.4 で開発・ビルドが通り、`styles.configFile` の変数が反映され、`sass` は `configFile` を使うと必須と確認した(3.1)。ただし `vite-plugin-vuetify` に Vite 8 の明示対応の記述がない点は FARC-U-20 | — |
| FARC-U-2 | Vuetify 4.3.4 の `VDataTableServer`(`@update:options` の初期発火、単一ソートの設定、`hover`、`aria-sort`)と、jsdom で動くか | 未決(維持。`VDataTable` の型は確認したが `VDataTableServer` は 0005 でも未確認) | 実装時 |
| FARC-U-3 | `@mdi/js`(Apache-2.0)の社内ポリシー上の扱い(DS 14章) | 未決(維持) | 運用・ユーザー確認 |
| FARC-U-4 | Hey API 0.99 の `throwOnError` の既定、Query のエラー処理(stale 表示)との接続、生成 key の形、プラグインの設定 | **解消(v0.2。0005 の 1 章の 2・1b)**: 既定は throw しない。生成 `queryFn`・`mutationFn` は内部で `throwOnError: true` を渡す。実行時の値は型と食い違うため正規化層を置く(FARC-P-44。5.3)。生成 key は差し替える(5.4)。プラグイン設定は 5.2。interceptor・key 差し替えの実機確認は FARC-U-22 | — |
| FARC-U-5 | 生成コード・OpenAPI JSON のコミット方針(FARC-P-6)の確定(出力の安定性・差分の大きさ) | **解消(v0.2。0005 の 1 章の 5)**: 決定的(既定設定で、同一入力 3 回と別ディレクトリの差分 0)で、`infiniteQueryOptions: false` なら 17 ファイル・約 111KB(既定は約 114KB)。コミットを維持(G4-3) | — |
| FARC-U-6 | v0.1: `app.frontend("/admin")` の細部と、`index.html`・`assets/` のキャッシュヘッダー。**v0.2: Nginx の設定・配信の確認** | **一部解消(v0.2。0003・0005)**: `app.frontend()` は使わなくなった。Nginx の設定案は `nginx -t` と curl・Chromium で確認した(3.3)。**残り(前提タスク B+C の実装時に確認)**: `proxy_read_timeout`・`client_max_body_size`・`proxy_connect_timeout` ほか数値の最終値、`Host` を `$host` か `$http_host` にするか、`add_header ... always` とセキュリティヘッダー(CSP など)、404 に `Cache-Control` を付けるか、`/` の扱い(BAPI-U-4)、`web` のヘルスチェックの手段(3.6)、実際の `api` との結合(compose)。`%2F`・`%2E` は FARC-U-21 | 実装時(前提タスク B+C) |
| FARC-U-7 | サブアプリのマウント時の OpenAPI の `paths`・`servers` と `baseUrl` | **一部解消(v0.2。0004・0005)**: `servers=[{url:/api/admin/v1}]` 固定・`paths` 相対は確認し、Hey API が `servers` から `baseUrl` を作ることも確認した(5.2・5.3)。**残り**: 入れ子マウント・`FastAPI(root_path=…)` は未検証。「`root_path` は不要」は、**Nginx がパスを変えない**(元の URI をそのまま渡す。3.3)ことが前提で、`%2F`・`%2E` を含む実リクエストでの保持は FARC-U-21 | 前提タスク B の実機確認(FARC-U-21。HO-58) |
| FARC-U-8 | Playwright: `baseURL` に `/admin/` を含めたときの相対遷移・`request` フィクスチャの解決、時計の操作 | 未決(維持。実機で確認) | 実装時 |
| FARC-U-9 | Vitest を jsdom にするか Browser Mode にするか、`test.server.deps.inline` が Vitest 5 で有効か、`ResizeObserver` のモック。**v0.2 追記: jsdom 31 で相対 `baseUrl` の `Request` が解決されるか(10.1)** | 未決(維持。jsdom 31 は採用した(FARC-P-21)が、Vuetify 4.3.4 の部品が動くかと相対 `baseUrl` は未確認) | 実装時 |
| FARC-U-10 | Vuetify 4.3.4 の Node の最小要件、TypeScript 6.x の最新パッチ、Vite 8 の既定の `build.target` とブラウザ要件の整合 | **解消(v0.2。0004 の 4 章)**: Vuetify の公開パッケージに `engines` はない(ルートの `engines.node` は開発環境の要件)。TypeScript は 6.0.3(`~6.0.3`)。既定の `build.target` は下限より低く矛盾しない(0005)(2.2・2.3) | — |
| FARC-U-11 | Docker のビルドコンテキストと Node ベースイメージのタグ・ダイジェスト | **一部解消(v0.2。0003)**: `web` が自前の Dockerfile を持ち(`build: ../../apps/web`)、コンテキストの問題は消えた(3.5)。**残り**: Node ベースイメージのタグ・ダイジェストは前提タスク B で決める(HO-53) | 前提タスク B |
| FARC-U-12 | B の案が変わったときの追従と、C(導出ロジック。B 11.10)の確定後の再確認 | **解消(v0.2。0004)**: 実装・OpenAPI との照合で完了し(12.7)、B の差は HO-61〜64 で申し送る。B が改訂されたときは本書と 12.7 を再照合する | — |
| FARC-U-13 | 9 桁を超える既存値(Crawler API を直接使って登録された `ttl_seconds` など)の編集時の扱い | 未決(維持) | 実装時 |
| FARC-U-14 | DS が「実機 4.3.4 で要確認」とする Vuetify の挙動(9.2・10.3) | 未決(維持) | 実装後(`web-ui-reviewer`) |
| FARC-U-15 | Firefox 128・Safari 16.4 の実機確認の範囲(自動 E2E は Chromium のみ) | 未決(維持) | 実装後 |
| FARC-U-16 | クライアントのタイムアウトの仮値(読 45 秒・書 90 秒)の実測(BAPI-U-6) | 未決(維持。未測定のまま。**Nginx の `proxy_read_timeout` との整合要件が加わった**。3.3・5.3) | 実装後 |
| FARC-U-17 | Search View と同じビルドにするか(`base: '/admin/'` の前提。BAPI-U-4) | 未決(維持。`web` が将来 Search View も配信しうる。1.3) | Search View の設計 |
| FARC-U-18 | 生成 SDK がパスの値(`job_id`・`source_id`)を全文字エンコードして送るか。`%`・`?`・`#`・`.` を含む `job_id` の Crawler までの挙動 | **一部解消(v0.2。0005 の 3: SDK 側は確認済み)**: SDK 側は確認済み(`encodeURIComponent`。値全体が `.`・`..`・空文字のときは URL が壊れる)で、送信前検証で対処する(5.3。FMOD-P-4)。**残り**: Crawler の実 uvicorn での挙動(AAPI-U-12。HO-46)と、Nginx 越しの保持(FARC-U-21) | 前提タスク B・実装時(HO-46・58) |
| FARC-U-19 | ブラウザと Crawler(`cron_timezone`)のタイムゾーンが異なるときの日時の表示(DS 4.9・14章。FARC-P-33。ゲート3(G3-13)で「決めず画面設計に任せる」ことを了承) | 持ち越し(維持) | 画面設計 |
| **FARC-U-20** | **(新規)** `vite-plugin-vuetify` 2.1.3 に Vite 8(Rolldown)の**明示対応の記述がない**(CHANGELOG は「support vuetify 4」まで)。実機でビルド・`styles.configFile`・開発サーバーは通った(0005)。更新のたびに再確認し、問題が出たら `vite-plugin-vuetify` の版を調整する(Vite は minor 固定(`~8.3.8`)のまま) | 未決(新規。v0.2) | 実装時・依存の更新時 |
| **FARC-U-21** | **(新規)** Nginx 越しの `%2F`・`%2E` を含む `job_id` の保持。URI 部のない変数 `proxy_pass` は元の URI を渡すことは確認したが、`%2F`・`%2E` を含む実リクエストでは未実測(`job_id` のエンコード。B 2.12。3.3・5.3) | 未決(新規。v0.2) | 前提タスク B の実機確認(HO-46 の追従。HO-58) |
| **FARC-U-22** | **(新規)** API クライアントの設定の実機確認: (1) `error` interceptor に届く値(確認済みの種類は 12.1 の 4。**`TimeoutError`・`AbortError` は未確認**)と、Query・実ブラウザ経由で投げられる値が `ApiError` になること、(2) **`AbortError`(Query のキャンセル)と `TimeoutError`(クライアントのタイムアウト)の区別**、(3) **自前のタイムアウトで `AbortSignal.any` を使わない理由**(対応下限の Safari 16.4 で使えない可能性。推測。未確認)、(4) key の差し替え(`withKey`)が実ブラウザ・invalidate で期待どおり動くこと、(5) **タイムアウトが本文の取得完了までを対象にすること**(ヘッダー受信後に本文が止まったとき時間切れになる。5.3。PR #21 のレビュー指摘への対応。ユーザー指示 2026-11-26)、(6) **`withKey` は Hey API の内部実装(生成された `queryFn` がクロージャの引数から URL を作ること)に依存する**ため、実装時にコストが高い・生成物の更新で壊れるなら、SDK 関数から独自の Options を組み立てる方式(`queryOptions({ queryKey: keys.…, queryFn: ({ signal }) => getSource({ …, throwOnError: true, signal }) })`。入出力の型は生成 SDK から推論できる。14 EP なので記述量の増加は小さい)への切り替えを再検討する(5.4。現案はユーザー承認済みで、変更は必須としない。PR #21 のレビュー指摘への対応。ユーザー指示 2026-11-26)。F の FMOD-U-12 と同じ論点 | 未決(新規。v0.2) | 実装時 |
| **FARC-U-23** | **(新規)** EP-01 の反映遅れの最大値。EP-01 は検索ベースで、登録・削除の直後に新規ソースが見えない・消えたソースが残る例がある(EP-02 は ID 指定で即時。S-E5)が、遅延の最大は未測定(5.4・5.8) | 未決(新規。v0.2) | 実装時(IT・実機) |
| **FARC-U-24** | **(新規)** `stalled=true`(保存上は `running` でリース切れ)の経路。IT でも未検証で、J-E5(`lease_expires_at=null` の表示)・J-E6(EP-08 の `released=false`)の記述はこれに依存し、推測を含む(5.10・6.3。AAPI-U-5・8・9、AAA-U-7・10) | 未決(新規。v0.2) | 実装時(結合テスト・実機) |
| **FARC-U-25** | **(新規)** 依存全体の `npm ci`・`npm audit`・peer の警告。0005 が確認したのは、P2-b で install した版(Vite・Vuetify・`vite-plugin-vuetify`・`@vitejs/plugin-vue`・Vue Router・Vue・TypeScript・`vue-tsc`・`sass`・`@mdi/js`・`@types/node`)だけ。Vitest 5・jsdom 31・Playwright・ESLint・`typescript-eslint`・Prettier・`@vue/test-utils`・Hey API・`@tanstack/vue-query` を Vite 系と同時に install した状態は未確認(2.1) | 未決(新規。v0.2) | 実装時(最初のスキャフォールドで `npm ci`・`npm audit` を通す) |
| **FARC-U-26** | **(新規)** 実データ・実環境で未確認の点: (1) `web` イメージの Docker マルチステージビルド(Node → Nginx。3.5。0005 は `vite build` とダミーの upstream の Nginx を別々に確認)、(2) EP-09 の複数ページと `page × items_per_page ≤ 10,000` の窓(IT でも未検証。5.6)、(3) S1 の `status=null` の行が実データで出るか(出なくても 5.7 の方針は変えない)、(4) Vue Query v5 の `isLoading` の意味(`enabled: false` のときの状態。5.7。推測) | 未決(新規。v0.2) | (1) 前提タスク B(HO-53)、(2)〜(4) 実装時(IT・実機。HO-47) |

### 12.5 既存設計との不整合(I-n)

本書の予約範囲は I-80〜89 と I-120〜129。B・A・DS・画面仕様・C は変更せず、追従改訂は A 9章の HO-52〜68(9.2.11)に集約する。F の I-130〜138 は同じ事実を指すものがある(下の表の「F」)。

| ID | 内容 | 本書での扱い |
| --- | --- | --- |
| I-80 | DS 10.1 は TypeScript 7 を「`vue-tsc` が動かない報告がある」とするが、一次情報では「公式未対応(コミュニティの橋渡しで動く例はある)」(0004) | 結論(6.x 固定)は同じ。本書は「公式未対応」と書く(2.2)。DS の記述の更新は HO-23(版・構成の更新は HO-68) |
| I-81 | admin-view 4.2 の route `path`(`/`・`/sources` …)は `/admin/` を含まないが、Admin View は `/admin/` 配下に置く | 画面仕様の `path` を Router の `base` からの相対と読む(3.2)。画面仕様への注記は HO-22 |
| I-82 | (**解消**)A 8 は「ビルドは `apps/api`」とし、既存の compose のコンテキスト(アプリのディレクトリ)では `apps/web` を取り込めなかった | 0003 により `web` が自前の Dockerfile を持つ(`build: ../../apps/web`)ため消えた(3.5)。A 8・HO-37 の読み替えは HO(I-125。HO-53) |
| I-83 | DS 5.3 は `meta.title` を「文字列」とするが、admin-view 4.2 は S2・J2 などの動的な title(識別子・ジョブ ID)を要する | `title` を `string \| (route) => string` とする(4.3)。静的な場合は DS のとおり。DS の型記述の補足は HO-25 |
| I-84 | sources 2.4 の `reason` → 文言の表に、B の `range`・`exclusive`・`config_invalid` がない | 6.4 の扱い(案)。画面仕様への追記は HO-28 |
| I-85 | URL クエリ・`documentTabs` の表記と API の表記が違う: `source`(URL)↔ `source_id`、`size` ↔ `items_per_page`、`extract-failed`・`summary-pending`(kebab)↔ `extract_failed`・`summary_pending`(snake)。B 2.1 が E・F に対応づけを委ねている | 5.6 の対応表で 1 か所に定義する(不整合ではなく表記の差) |
| I-86 | J1 の並べ替えは、画面が「開始」列(実行待ちは受付日時を出す)の昇降順、B は `sort=queued_at`(受付日時。B 5.1 が画面の「開始」列に対応と明記)。`started_at` とは別の項目 | 列の `key` を API の項目名(`queued_at`)にする(5.6)。B 2.1 のとおり直列実行のため受付の順と開始の順は一致する(導出)ので、表示と並びのずれは生じない想定。実機で確認する |
| I-87 | 画面仕様に、B の応答から必要な状態の記述がない: O1 の `truncated=true`、X1 の `source` が存在しないとき、S2・S4 で設定項目が読めない(`malformed`)とき、J2 の `stalled`・`rerunnable` が `null` のとき、S4 で保存値のしきい値が小数第 3 位以下を持つとき(B 2.8)、S2 のロック状態が `unknown` のとき | 6.7・7.6・7.7・5.10 の暫定の扱い(案)。画面仕様への追記は HO-29 |
| I-88 | admin-view 7.7 は `lock_held` で「ジョブを表示」(J2)を出し、失効したロックでは「ジョブ詳細でロックを解放」(J2 → DLG-5)とするが、孤児ロック・取得直後はジョブ記録がなく(`existing_job.status=null`。B 2.9・2.11)J2(EP-10)が 404 になりうる。孤児ロックの解放の入口は S2 だけ(sources 1.5・admin-view 4.1) | 6.3 のとおり、`status=null`(**v0.2: または未知の値**)では「ジョブを表示」を出さず S2 へ導く(FARC-P-35)。ゲート3でユーザー確認済み(2026-11-23)。画面仕様の追記は HO-31 |
| I-89 | DS 5.3 は `featureFlag` を「設定されていないときにナビとルートを隠す」とし、ナビ項目の定義を「route `meta` にだけ」持つ(`nav.external` も `meta` のキー)とするが、本書は (1) ナビ(外部リンク項目)だけを `SideNav` で隠し、ルートは隠さない(MVP に `featureFlag` を持つ route がなく、外部リンクは route を持たない。admin-view 4.2)、(2) **外部リンク項目を route `meta` でなく定義表 `shell/externalLinks.ts` に持つ**(`RouteMeta` から `nav.external` を外した) | 4.2・4.5 のとおり(FARC-P-18)。ゲート3でユーザー確認済み(2026-11-23)。DS 5.3 の追記は HO-26 |
| I-120 | 画面仕様に、Crawler・Indexer が書いた値が読めず `null` になる場合(B 2.2・2.11。`status=null` のジョブ、`registration` の件数・`partial`・`phase`)の表示の定義がない(画面仕様の「値がない」は「—」+「未設定」「なし」、取得失敗は「—」+「取得できません」) | 5.9 の (b)(「—」+視覚的に隠した「読み取れません」。`status=null` はタグ・操作なし。FARC-P-36)。画面仕様への追記候補は HO-30 |
| I-121 | `rerun_blocked_reason=source_missing`(B 2.9。AAPI-P-41)の理由の文言が画面仕様 jobs 2.3 にない(削除中・削除済みの文言もない) | 「再実行」を出さない案(6.7。FARC-P-37)。専用の文言は画面仕様に足す。HO-30 |
| I-122 | admin-view 7.8(と、v0.1 の本書・F の同旨)の「S1 の行は『削除中』になり」は、**EP-05 の 202 の直後には成り立たない**。受付の時点で設定の `status` は `active` のままで、`deleting` になるのは削除ジョブの開始後。S2 のロック状態カードは即時に `held_delete`(S-E1。確認 2026-11-26。0004。AIT-60) | 5.8 のとおり、受付の確認はスナックバー(`job_id` つき)と S2 のロック状態カードで行う。画面仕様への追記は HO-66 |
| I-123 | jobs 1.5(J1 の状態フィルタ)に、**`status=failed` の絞り込みにリース切れ(保存上は `running`)は含まれない**旨がない。「失敗(リース切れ)」の行は `active`(または `running`)でしか出ない(J-E7。B 5.1。F の I-135) | 5.7 の J1 の注記。画面で補わない。画面仕様への追記は HO-66 |
| I-124 | 画面仕様に、実装・OpenAPI から必要になる**状態が 4 つ**ない: (1) S1 の `status=null` の行(「削除中」の判定も操作も出さない)、(2) EP-08 の `released=false`(「解放するロックがありませんでした」の info。成功文言にしない)、(3) DLG-4 の `force_delete`・`rewrite_mode` が null のときの指定(false で送り「記録なし(なしとして実行)」と表示。FARC-P-46)、(4) `stalled=true` かつ `lease_expires_at=null` の「期限を確認できません(期限切れ)」(S-D2・J-E6・J-E8・J-E5) | 5.7・5.10・6.3・6.7・7.5 の暫定の扱い。画面仕様への追記は HO-67 |
| I-125 | A 2.1・2.2・8章(BAPI-K-2・BAPI-P-2・BAPI-U-1・G3-16・HO-2・HO-36・HO-37 を含む)は、`api` が Web UI を静的配信し、ビルドは `apps/api` とするが、ユーザー指示(0003)で `web` コンテナ(Nginx)が配信する(FARC-K-4。F の I-134) | 本書の FARC-K-4・P-2・P-20 に置き換える。A は改訂せず HO-59 で申し送る(HO-2・36・37 は読み替え。HO-53。C・D は HO-65) |
| I-126 | B 8.1 の `web` の判定(「`web` は compose のサービスではなく `api` が配信する」)、B 10.2・I-72・11.7 の #10・AAPI-P-8、OpenAPI の `ComponentId` の説明文は、`api` が `index.html` の有無で `web` を判定する前提(J-B6・X-C1。F の I-134) | 前提タスク C で `HttpHealthCheck` に置き換える(3.6・12.8)。B・`ComponentId` の docstring の追従は HO-60(前提タスク C は HO-55) |
| I-127 | B 2.11 は `SourceSettings` を EP-02〜04 で共通とするが、実装・OpenAPI では 2 種類(EP-02 は null 許容の `SourceDetailResponse`、EP-03・04 は厳格な `SourceSettings`)。B 3.1・6章の EP-01・11 の行の項目も、B が null と書く項目以外が null 許容(S-D3・S-D2・X-BD1。F の I-131) | 5.2・5.9 の `expectedFields`。HO-61(B 2.11・3.1・6章・1.4) |
| I-128 | B 2.2 は最上位の `unavailable` を EP-12・13・14 にも想定し、B 8.1・8.2 は EP-12・13・14 のクエリを「エラーなし」とするが、実装・OpenAPI では最上位の `unavailable` が意味を持つのは EP-02・10・11 だけ(EP-01・09 は常に `{}`)で、EP-12・13・14 は未知のクエリを 400 `unknown_field` で拒否する(J-E1・X-BD4・J-B1。F の I-132) | D1・O1・シェルは `unavailable` を引かず、EP-12・13・14 に query を付けない(5.3・5.9)。HO-62(B 2.2・8.1・8.2) |
| I-129 | B 2.12 は本文の違反を「すべて返す」とするが、実装は 2 段階(形 → 範囲・桁・排他)で最初の 1 群だけを返す。B 2.4 は `ttl_days`・`ttl_seconds` の排他・必須の `field` を区別するが、実装は両方 `ttl_days` 固定(S-D4・S-D5・J-B5。F の I-133) | 6.4 のとおり(再送で別の違反が出うる前提。TTL 欄に写す)。HO-63(B 2.12・2.4) |

F の I-135(J1 の `failed`)・I-136(`last_completed_at`・`connector_type` を S1 で使わない)・I-137(`deletion.fetched_at`)・I-138(`openapi_export.py` の docstring)と同じ事実は、本書では I-123・12.7 の S-E6・J-E10・X-ED2 が扱う。

### 12.6 B・A への依存と引き継ぎ

**F への引き継ぎ**: v0.1 の引き継ぎ(ディレクトリ構成・5.7 の展開・DS 4章の部品の置き場・依存ルール・定義表の置き場・トークンと `defaults` の共有)は、**F v0.2 の 8.6 で全件割り当て済み**。v0.2 で増えたもの(実行時エラーの正規化・生成とビルドの設定・DLG-4 の null・`web` の Dockerfile と Nginx 設定の置き場)も同じ表にある。v0.1 の I-104(D1 が EP-14 を使うとした記述)は解消済みで、本書の 5.4・5.7 は D1 を EP-13 だけとしている(dashboard 画面仕様に cron のタイムゾーン・Dashboards の URL を使う項目がない)。

**B への依存**(**実装・OpenAPI と食い違う箇所は実装・OpenAPI が正**。12.7): 本書が使う B の節は、1.3(画面 × EP)・2.1(ページング)・2.2(`unavailable`)・2.3(code)・2.4・2.5(項目エラー)・2.8(単位変換)・2.9(導出フラグ・`lock_state`)・2.11(DTO)・2.12(本文・ID)・3章(データソースの EP)・4章(起動・取消・解放の EP)・5章(J1・J2)・7.1(O1)・8.1・8.2(D1・`/meta`)・9.2(再送)。B は改訂せず、差は HO で申し送る。B の案が変わったとき(AAPI-P-16〜18・24〜34・37〜39・41・42)は、本書と 12.7 を再照合する。

**A への依存**: A 5.1(本文 1 MiB 上限・時刻の形式)・5.2(エラー形式。`ApiError` の元)・5.4(OpenAPI・サブアプリ)・5.6(タイムアウト)・2.2(URL 名前空間。ただし静的配信の記述は FARC-K-4 に置き換わった。I-125)。

**C(導出ロジック)への依存**: `stalled`・`cancellable`・`rerunnable`・`lock_state` などの意味が変わらないこと(B 11.10)。`stalled=true` の経路は未検証(FARC-U-24)。

**B・C の確定に依存する個別の点**(FARC-U-12。B・C が変わったときに本書を直す箇所): (1) `lock_state` 7 値のうち `just_acquired`・`unknown` の画面での扱い(5.10・6.3。B 2.9 の案)。(2) 失敗理由・警告・削除結果のコード(B 5.2。AAPI-U-3)と未知のコードの扱い(一般的な文言。5.7)。(3) `connector_config` の既定値の補完の境界(AAPI-P-20。7.5 で `file_system` の 5 項目を常に全部送る前提)。(4) OpenAPI の `operationId`(生成される SDK 関数名・`xxxOptions` の名前に直結する。5.2。変更は 11.2 の「生成して差分ゼロ」の検査で検出される)。(5) C の導出ロジックで `stalled` などの意味が変わらないこと(B 11.10)。

**前提タスク A・B+C への依存**は 12.8。

### 12.7 実 OpenAPI との照合の要約と差分一覧(新設)

**範囲と方法**(0004。確認 2026-11-26): ブランチ `feature/create-admin-ui-system-design`、基準 SHA `6a8b685` の実装から書き出した OpenAPI(3.1.0。14 EP・12 パス・`servers=[{url:/api/admin/v1}]`。sha256 `ce60fc1a…bf51`。出力は決定的)を、B・A・本書(v0.1 時点)・F と照合した。実装・テスト・実装記録・IT の記録を読む方法で、**実機確認は IT で確認済みのものに限る**。Hey API の生成・Nginx は 0005 で別に確認した(12.1)。

**結論**: (1) EP-01〜14 のパス・メソッド・本文項目・応答の主要項目・ステータス・code は大筋一致で、E・F が実装で壊れる箇所はない。(2) 差分は 4 種類: 型の粒度(null 許容・列挙・`anyOf`)、事実の誤り(v0.1 の E・F の記述が実装と合わない)、B と実装の差、配信方式の変更(0003)の影響。(3) **最大の影響は 0003**: `api` の EP-13 は `web` を `index.html` の有無で判定するため、`web` が別コンテナになると全環境で `web=abnormal(missing)` になり、D1 が常に「異常あり」になる(前提タスク C。12.8)。`/healthz` は `dist/` に依存せず影響なし。

**「v0.2 での扱い」の読み方**: 数字は本書で直した節、HO は A 9章の申し送り(9.2.11 の HO-52〜68。B・A・C・D・画面仕様は改訂しない。対応は 12.8)、前提は前提タスク A・B+C(12.8)。ID の接頭辞は 0004 のもの(S=データソース S1〜S4・EP-01〜05、J=ジョブ・D1・J1・J2・EP-06〜10・13、X=X1・O1・シェル・EP-11・12・14・共通)。

**(1) 前提タスクに関わるもの**

| ID | 内容 | 影響する ID | v0.2 での扱い |
| --- | --- | --- | --- |
| S-D1 | `ttl_days`・`ttl_seconds` が `integer \| null`(既定 null)で、実行時は明示的な null を 400 `type` で拒否する。「どちらか一方が必須」は OpenAPI に出ない。型どおりに作ると null を送れてしまう | FARC-P-16 | **前提タスク A**(「任意かつ非 null」に直す)。v0.2 は A の前後で同じコード: null を送らずキーを省く、排他は画面側(5.2・7.5・10.1) |
| X-ED2 | `openapi_export.py` の docstring は「リポジトリにコミットしない」とするが、FARC-P-6 は「コミットする」。出力は決定的で差分検査に使える | FARC-P-6 | **前提タスク A**(docstring)。コミット方針は維持(G4-3)。5.2・11.2 |
| X-C1・J-E2 | EP-13 の `web` 判定を、`index.html` の有無から、`api` が `web` の URL を `HttpHealthCheck` で確認する方式へ(承認済みの案(ゲート4。G4-4)。`ComponentId`・`reason` の OpenAPI は不変)。影響範囲(`apps/api/src/loreley_api/` からの相対。A の HO-55 と同じ表記)は `infrastructure/probes/web_dist.py`・`infrastructure/probes/ports.py`・`admin/dependencies.py`・`admin/services/dashboard.py`・`admin/settings.py`・`config.py`・`main.py`・`openapi_export.py` の `web_dist_dir`・`web_probe` の配線、`LORELEY_API_WEB_DIST_DIR`・README・テスト 11 ファイル・IT の `compose.test.yaml`・fixtures | FARC-P-20、B 8.1・10.2 | **前提タスク C**(3.6・5.7 の D1 の補足・12.8) |
| X-C2 | compose の `api` は `127.0.0.1:${API_HOST_PORT:-8080}:8080` で publish され、IT(`tests/integration/api/support.py`・`scripts/run-api-integration-test.sh`)が `127.0.0.1:8080` を直接呼ぶ | FARC-P-42 | G4-2 で **`web` 経由に一本化**。`api` の `ports` を外し、IT の上書きで publish(前提タスク B+C。3.6・12.8) |

**(2) 型の粒度・事実の誤り(v0.2 で直したもの)**

| ID | 内容 | 影響する ID | v0.2 での扱い |
| --- | --- | --- | --- |
| S-D2 | EP-01 の `status`・`connector_type`、EP-02 の設定項目・`updated_at` が null 許容(保存値が読めないとき)。S1 の `status=null` の行の扱いがなかった | FARC-P-36・27、FMOD-P-31 | 5.7(S1)・5.9。「削除中」の判定も操作も出さない。HO(B 3.1)。I-124・I-127 |
| S-D3 | **`SourceSettings` が 2 種類**: EP-02 は null 許容の `SourceDetailResponse`、EP-03・04 は厳格な `SourceSettings`。B 2.11 は共通と書く | FMOD-P-16 | 5.2(型の使い方 2)・7.5。HO(B 2.11)。I-127 |
| S-D4・X-BD5・J-B5 | **本文の違反は 2 段階**(形 → 範囲・桁・排他)で返る。EP-09 も最初の 1 群のみ。B 2.12 の「すべて返す」と不一致 | FARC-P-13・16 | 6.4。HO(B 2.12)。I-129 |
| S-D5 | `ttl_days`・`ttl_seconds` の排他・必須の `field` は両方 `ttl_days` 固定 | FARC-P-13、F `fieldMap` | 6.4(TTL 欄に写す)。HO(B 2.4。軽微) |
| S-D6 | `connector_config` 内の NaN・Infinity は 400。B に記載なし | — | 対応不要。HO(軽微) |
| S-D7・J-O5・X-BD7 | `ErrorBody.code` は string(列挙なし。`implement_admin_api` の 0017 の意図的な判断)、`details` は全キー任意、404・405・500 は OpenAPI に宣言なし。code は Admin 固有 14 種+共通 6 種 | FARC-P-13、FMOD-P-6 | 6.1・10.1(`errorTable` は手書き。OpenAPI の説明文との契約テスト)。列挙化は推奨しない(将来の code で型生成が壊れる) |
| S-E1 | **EP-05 の 202 の直後に S1 の行は「削除中」にならないことがある**。受付直後は設定の `status` が `active` のままで、直後の EP-01 は `delete_job=null`。EP-02 の `lock.state` は即時に `held_delete`(IT の AIT-60) | FARC-P-11、F 4.2 | 5.8。I-122 |
| S-E3 | `fieldMap` に、添字なしの配列エラー(パターンの 100 件超)と `connector_config` 自身のエラーがない | FARC-P-13 | 6.3・6.4(一覧の下 / 上部アラート) |
| S-E4 | `invalid_request` で `details` なし(本文が読めない・Content-Type 違い・1 MiB 超)が想定外として書かれていない | FARC-P-13 | 6.3(想定外。診断に code と HTTP ステータス) |
| S-E5 | EP-01 は検索ベースで反映が遅れうる(EP-02 は ID 指定で即時)。最大の遅延は未測定 | FARC-P-8・11 | 5.4・5.8。FARC-U-23 |
| S-E6 | `last_completed_at`・`connector_type`(EP-01)を使う画面仕様がない(B 1.4 は S1 が使うとする。AF-U-9 未決) | F 3.9 | 5.7 で「使わない」と明記(要件にない追加をしない)。HO。F の I-136 |
| S-E7 | 小数桁の判定を `String(n)` で行うと極小値が指数表記になる | FARC-P-29 | 7.7 |
| J-E1 | **最上位の `unavailable` が意味を持つのは EP-02・10・11 だけ**(EP-01・09 の最上位は常に `{}`。EP-12・13・14 は持たない。v0.1 は EP-02・10・12・13・14) | FARC-P-27・39、FMOD-P-14・33 | 5.7・5.9。D1・O1 は引かない。HO(B 2.2)。I-128 |
| J-E5 | J2 の `stalled=true` でも `lease_expires_at=null` になりうる(ロック文書がない・別ジョブ・期限が読めない)。未検証の経路で推測を含む | FARC-P-34、FMOD-P-15 | 5.10(「期限を確認できません(期限切れ)」)。FARC-U-24。I-124 |
| J-E6 | ロック文書がない `stalled` のジョブでは、EP-08 は 200 `released=false`・`failed_job_id=null`(ジョブは `running` のまま。実機未検証) | FARC-P-15・34 | 6.3(成功文言にしない)。FARC-U-24。I-124 |
| J-E7 | J1 の `status=failed` にリース切れは含まれない。「失敗(リース切れ)」の行は `active` でしか出ない | FARC-P-10・31 | 5.7。HO(jobs 1.5)。I-123 |
| J-E8 | DLG-4 の `force_delete`・`rewrite_mode`(`boolean \| null`)を EP-06 にそのまま渡せない(本文は null を受けない) | FARC-P-16・37 | 7.5(**FARC-P-46**。G4-6)。I-124 |
| J-E9・J-O9 | `lock_held`・`lock_in_use` の `existing_job` の `job_type`・`status`・`trigger` は OpenAPI で列挙だが、実装は Crawler の文字列を通すため未知の値がありうる | FARC-P-35 | 6.3(`null` または未知の値のとき J2 へ導かない) |
| J-E10・J-B4 | `deletion.fetched_at` は `queued` 以外で、読み取りに失敗したときも「読もうとした時刻」を入れる | FARC-P-11 | 5.7(失敗時は取得時刻として出さない)。HO。F の I-137 |
| J-O2 | EP-09 の `sort` は素の string(許容は `queued_at`・`-queued_at`)。`items_per_page` は列挙 | FARC-P-10 | 5.6(`jobsParams.ts` が union を持つ)。前提タスク A の任意項目(enum 化) |
| J-O1・J-O3・X-BD6 | `page × items_per_page ≤ 10,000` と ID の pattern・maxLength は OpenAPI に出ない(実行時の 400) | FARC-P-10・16 | 5.6(画面が守る)。ID は型で縛らず、400 を想定内とする |
| J-O4 | `warnings[]` の要素が `{[k: string]: unknown}`(`code` が型に出ない) | FMOD-P-31 | 5.7(J2。`typeof code === 'string'` の型ガード) |
| J-O6・J-O7 | EP-07 の 200・202 は同一スキーマ(`status` は全 6 値)。`JobAccepted` の列挙は全値(EP-06 は実際は `crawl`・`queued`・`manual`) | FARC-P-14 | 5.8(分岐は本文の `status`) |
| X-BD1・X-BD2・X-BD3 | EP-11 の行は B が null と書く項目以外も null 許容(非 null は `SkippedDocument.existence`、`ExtractFailedDocument`・`SummaryPendingDocument` の `document_id`、各行の `unavailable`)。EP-12 の `cluster.status`・`indices[].status`・`shards[].role/state` は列挙でなく string | FARC-P-36、FMOD-P-12 | 5.9(`expectedFields`・union とガード)。HO(B 6章・7.1)。**0004 の X-BD1 は「`existence` のみ非 null」としたが、実 OpenAPI を読むと `document_id`・`unavailable` も非 null(F の I-130)** |
| X-ED1 | EP-11 の `items` は判別子のない 4 型の `anyOf` で、絞り込みの方針がなかった | FMOD-P-12 | 5.7(X1 の `items`。`documentTabs` が行型とアダプタを持つ) |
| X-BD4・J-B1 | **EP-12・13・14 は query を一切受けず、未知のクエリは 400 `unknown_field`**(B 8.1・8.2 は「エラーなし」) | FARC-P-7 | 5.3(query を付けない。10.1 でテスト)。HO(B 8.1・8.2)。I-128 |
| X-ED5 | O1 の行列の補完・並びは API が保証済み | F 3.9 | 5.7(API の並びのまま使い、補完は実装しない) |
| X-ED3・S-E2・J-O8 | `servers=[{url:/api/admin/v1}]` 固定・`paths` 相対。Hey API が `servers` から `baseUrl` を作るかは未確認だった | FARC-U-7 | 0005 で確認(5.2・5.3)。FARC-U-7 は解消 |

**(3) B と実装の差で、HO のみのもの**(B は改訂しない): J-B3(EP-10 の `deletion` は `job_type` が読めないときも null になる)と、X-BD8 の HO の状態更新(HO-34・35・43・44 は compose に実装済み、HO-40・41 は `deploy/compose/README.md` に追記済み、HO-45 は実機確認が一部。0004 の読解による)。

**(4) 配信方式の変更(0003)の影響**

| ID | 内容 | v0.2 での扱い |
| --- | --- | --- |
| S-N1 | 配信が `api` から `web` に変わる。v0.1 の「`Accept: text/html` の GET/HEAD だけフォールバック」は `app.frontend()` の挙動で、Nginx は `Accept` を見ない(`/api/` は別 location なので影響なし) | 3.3(FARC-P-2・40) |
| S-N2・J-E4・X-C3 | Nginx の `proxy_read_timeout` の既定(公式ドキュメント上 60 秒。未測定)では、`api` の Crawler 待ち(約 63 秒で JSON の 504)より先に切れ、結果不明の JSON が届かず HTML の 504 になる | 3.3・5.3(90 秒以上。FARC-P-41)。最終値は実装時 |
| S-N3・X-C3 | `api` は 1 MiB 超を JSON の 400 で返すが、Nginx の本文上限(既定は公式ドキュメント上 1m。1m を明示した検証で +1 バイトが 413)では HTML の 413 が先に返る | 3.3・6.5(`client_max_body_size` を少し大きく。FARC-P-43) |
| S-N4・J-E3・X-ED6 | Nginx 由来の 502・503・504・413 は HTML で `invalid_response`。**書き込み(EP-03〜08)の 502・504 は `api` が Crawler を呼んだ後かもしれない** | 5.3・6.5(結果不明。FARC-P-43) |
| S-N5・X-C3 | `/api/` は `proxy_cache` を使わず `Cache-Control: no-store` を素通し。`add_header` の継承に注意。`index.html` は再検証、`assets/` は長期キャッシュ | 3.3(FARC-P-40) |
| S-N6・X-C3 | `/api/` をプロキシすると `web` の公開範囲に認証なしの破壊的操作が出る。HO-40・41 の注意書きは `web` に適用 | 3.6(FARC-P-42。G4-2) |
| X-C3 | URI 部なしの `proxy_pass`(元の URI をそのまま渡す)。`%2F`・`%2E` の保持は未実測。`api` 未起動でも起動できる構成(変数+`resolver`)。`/admin` の 301。`web` のヘルスチェックの手段 | 3.3・3.6。FARC-U-6・21 |

### 12.8 前提タスク A・B+C と依存(新設)

本タスクは前提タスクを起票しない。内容と、何が終わるまで何ができないかを書く(承認済みの案(ゲート4。2026-11-26。G4-4): **A と B+C の 2 本**)。**「前提タスク A・B・C」は作業のまとまりで、文書 A・B・C・D(0 章の関連文書)とは別のもの**。「前提タスク」を付けずに書いた A・B・C・D は文書を指す。代替の 3 本(B と C を別々)・1 本(A も同じタスクに含める)は採らない(B と C は同じ `web` サービスの配線で、同時に直さないと D1 の `web` が壊れる。A の小さな修正を B・C に引きずらせると型生成の着手が遅れる)。

| タスク | 内容 | 対象 |
| --- | --- | --- |
| **A: OpenAPI の型の修正** | `ttl_days`・`ttl_seconds` を「任意かつ非 null」にする(S-D1)。`openapi_export.py` の docstring を、本書の方針(OpenAPI JSON をコミットする。FARC-P-6)に合わせる(X-ED2)。任意: jobs の `sort` の列挙化、`warnings[].code` の型(J-O2・O4)。`ErrorBody.code` の列挙化は行わない(`implement_admin_api` の 0017 の判断。将来の code で型生成が壊れる) | `apps/api` のみ |
| **B+C: `web` コンテナの追加と、`api` の `web` プローブの置換** | **B**: `apps/web` の `Dockerfile`・`nginx/default.conf`(3.3・3.5)、compose の `web` サービス(`build: ../../apps/web`、`127.0.0.1:${WEB_HOST_PORT}` に publish、`depends_on: api`(`service_healthy`))、**`api` の `ports` を `compose.yaml` から外す**、`compose.yaml` 冒頭の「公開範囲」の注意書きと `deploy/compose/README.md`・`apps/api/README.md` の更新、`%2F`・`%2E` を含む `job_id` の素通しの実機確認。**C**: EP-13 の `web` 判定を `HttpHealthCheck`(`web` の URL。0004 の例は `LORELEY_API_WEB_URL`)に置換し、`web_dist.py`・`LORELEY_API_WEB_DIST_DIR`・配線・README・Dockerfile のコメント・テストを更新、IT の上書き `compose.test.yaml` が `api` を `127.0.0.1:8080` に publish し、`/app/web` の fixtures を不要にする。環境変数名・確認先は C で決める | `apps/web`・`deploy/`・`apps/api`・`tests/` |

**何が終わるまで何ができないか**(F 8.9 と同じ内容):

| 作業 | 前提 | 説明 |
| --- | --- | --- |
| フロントの最初のスキャフォールド(`apps/web` の `package.json`・`vite build` が通る最小の構成) | なし | **B+C の `web` イメージのビルド(Node 24 でビルド → Nginx。3.5)は、`package.json` と `vite build` が通ることを前提にする**ため、B+C はフロントの最初のスキャフォールドの後に着手できる |
| 型生成(`gen:api`)と、それに依存する実装 | **A の完了後が望ましい(必須ではない)** | A の前に生成すると `ttl_*` が `number \| null` になる。やむを得ず A の前に生成したときは、`toRequest` が null を送らない単体テスト(10.1)で補い、A の後に再生成して差分をレビューする(5.2) |
| 開発サーバー(Vite の dev + `/api` プロキシ)での開発 | A・B+C のどちらも不要 | 転送先は dev 専用の環境変数で上書きできる(3.4)。B+C の前は、転送先を現行の compose の `api` の公開ポート(`http://127.0.0.1:8080`)に上書きして着手できる。B+C の後の既定の転送先は `web` の公開ポート |
| 単体テスト・API モックの E2E | A・B+C のどちらも不要 | 10.1・10.2 |
| D1 の `web` タイルの正しい表示 | **C の完了後** | C の前は、`web` が別コンテナになる前提では `web=abnormal` に見える(コードの読解。0004)。フロントの変更は要らない(5.7) |
| `web` の配信と `web` 経由の接続確認(10.2) | **B+C の完了後** | `web` コンテナ・compose の `web` サービス・`api` の publish の外しと IT の上書きが要る。`%2F`・`%2E` の素通し(FARC-U-21)も B |
| 初回リリース | **B+C の完了**(A は望ましいが必須ではない) | B の公開前に C は必須(B だけでは D1 の `web` が壊れる)。A は、前でも後でも `toRequest` が同じ出力のため、初回リリースの条件にしない(HO-52) |

順序の目安: スキャフォールド → (A の完了後が望ましい)型生成 → 実装・単体テスト・E2E(API モック) → (B+C の完了後)`web` 経由の接続確認・初回リリース。B+C は、スキャフォールドの後ならいつでも着手できる。

**本書で前提タスクに依存する箇所**: 3.3(Nginx 設定)・3.4(既定の転送先)・3.5(`web` イメージ)・3.6(`web` と `api` の関係)・5.7(D1 の `web`)・10.2(実 API の接続確認)は B+C、5.2(`ttl_*` の型と docstring)は A。

**HO との対応**(A の 9.2.11 の HO-52〜68 と、A 9章の既存の HO の更新。B・C・D・A・DS・画面仕様は改訂しない。A の HO の状態は、確認時点(2026-11-26)のもの):

| 対象 | 内容 | 本書の ID | A の HO |
| --- | --- | --- | --- |
| 前提タスク A(`apps/api`) | `ttl_*` の型、`openapi_export.py` の docstring、任意の enum 化 | S-D1・X-ED2 | HO-52(HO-38 の docstring の修正も A) |
| 前提タスク B+C の B(`apps/web`・`deploy/compose/`) | `web` の Dockerfile・Nginx 設定・compose の `web` サービス。スキャフォールドの後に着手 | 3.3・3.5・FARC-P-20・40・41 | HO-53(HO-36・37 は読み替え) |
| 同(公開範囲) | `api` の `ports` を外し、`web` だけを `127.0.0.1` に publish。README の注意書きを `web` に適用 | FARC-P-42 | HO-54(HO-34・40・41) |
| 前提タスク B+C の C(`apps/api`) | EP-13 の `web` 判定を `HttpHealthCheck` に置換。B と同時に完了 | I-126・X-C1 | HO-55 |
| 同(結合テスト) | `compose.test.yaml` が `api` を `127.0.0.1:8080` に publish。`web` の fixtures を不要に | X-C2 | HO-56 |
| dev サーバーの転送先(`apps/web` の `vite.config.ts`) | `/api` の転送先を `web` の公開ポートに | FARC-P-19 | HO-57 |
| Nginx の実装時確認 | 数値の最終値・`%2F`・`%2E` の保持・ヘルスチェック・CSP など | FARC-U-6・21 | HO-58(HO-46 の追従) |
| A の本文(2.1・2.2・2.3・3・4・8 章ほか。BAPI-K-2・P-2・U-1、G3-16) | 静的配信を `web` が担う(FARC-K-4)。HO-2・36・37 は読み替え。HO-38・42・46・47 の内容は更新 | I-125 | HO-59。あわせて HO-2・36・37・38・42・46・47 の内容を更新済み |
| B 8.1・10.2・I-72・11.7 の #10・AAPI-P-8、`ComponentId` の説明文(docstring) | `web` の判定が `index.html` の有無でなくなる(前提タスク C。`api` が配信する旨の記述を直す) | I-126 | HO-60(HO-55) |
| B 1.4・2.11・3.1・6章・7.1 | `SourceSettings` の 2 種類、EP-01・11 の null 許容、S1 の `status`・`connector_type` の null、OpenSearch の状態値は string、S1 が `last_completed_at`・`connector_type` を使わない | I-127。12.7 | HO-61 |
| B 2.2・8.1・8.2 | 最上位の `unavailable` の対象(EP-02・10・11)、EP-12・13・14 の未知クエリは 400 | I-128 | HO-62 |
| B 2.4・2.12 | `ttl_days` 固定の `field`、本文の違反の 2 段階 | I-129 | HO-63 |
| B 5 章(EP-10)の `deletion` | `job_type` が読めないときも null、`fetched_at` は失敗時も入る | J-E10(F の I-137) | HO-64 |
| C・D(`admin/` の設計書) | 配信担当の変更と `web` プローブの置換への追従(前提タスク C の後) | I-125・I-126 | HO-65 |
| admin-view 7.8、jobs 1.5 | EP-05 の 202 の直後は「削除中」にならない。`failed` の絞り込みにリース切れは含まれない | I-122・I-123 | HO-66 |
| 画面仕様(sources・jobs・admin-view) | S1 の `status=null`・DLG-4 の null の指定・DLG-5 の `released=false`・「期限を確認できません(期限切れ)」 | I-124 | HO-67(HO-29・30) |
| DS 10.1 | 版・構成を v0.2 に合わせる(Vue Router 5・jsdom 31・Node の下限・`vuetify/styles`・`sass`) | I-80。FARC-P-3・4・21・30 | HO-68(HO-23・24) |
| 既存 HO の状態更新 | HO-34・35・43・44(compose 実装済み)、HO-40・41(`deploy/compose/README.md` に追記済み。`web` への適用が残る)、HO-45(実機確認が一部) | 0004 の X-BD8 | A 9.2 の各 HO の状態欄(更新済み) |
