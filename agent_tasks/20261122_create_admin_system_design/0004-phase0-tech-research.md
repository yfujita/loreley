# 0004 フェーズ0 技術事実確認の結果と事項3の確定

日付: 2026-11-22

## 事項3(`config_invalid`)の再確認結果

ユーザー回答: **分解方式の案(a)で承認**。Admin API が Crawler の `message`(「項目名(配列は添字): 違反の種類」)を項目と違反の種類に分解して返す。分解不能・切り詰めのときは画面が上部アラートにフォールバック。connector の検証規則は複製しない。`message` の形式に依存する点は申し送りに書く。(案(b)は採らない。0003 の要確認は解消)

## tech-advisor 報告の要点(調査日 2026-11-22。ファイル変更なし。出典は報告に記載)

### 確認済み

- DS 10 章の記述(Vuetify 4.3.4 exact pin、TypeScript 6.x 固定、ブラウザ要件 Chromium 119+/Firefox 128+/Safari 16.4+、Vitest 設定)は一次情報と矛盾しない。食い違いなし。
  - Vuetify 4.3.4 は npm `latest`(11/18 公開)。peer: `vue ^3.5`、`vite-plugin-vuetify >=2.1.0`(optional)。
  - Vue 3.5.46、vite-plugin-vuetify 2.1.3(peer `vite >=5`)、Vite 8.3.8(Node `^20.19 || >=22.12`)、Vitest 5.1.1(Node `^22.12 || ^24 || >=26`)、TanStack Vue Query 5.108.2。
  - TypeScript は `latest` が 7.0.2(2026-07。ネイティブ版・プログラマティック API なし)。6.0.3 は実在。vue-tsc(3.3.x)は TS 7 で失敗(公式未対応。コミュニティの bridge で動く例はある)→「6.x 固定」は妥当。DS の「動かない」は「公式未対応」と書くほうが正確。
- OpenAPI→TS: **Hey API(`@hey-api/openapi-ts` 0.99.0、Node `>=22.18`、TS 6 対応)を推奨**。公式 `@tanstack/vue-query` プラグインで queryOptions/mutationOptions を生成。0.x のため exact pin と移行確認が必要。Vue では `computed(() => xxxOptions(...))` で包む。`openapi-typescript` は peer が TS 5.x(TS 6 対応 PR 未マージ)で不採用。`openapi-react-query` は React 専用。Orval は fetch の根拠が未確認。
- FastAPI: `openapi_url`・`docs_url`・`redoc_url` を `None` で無効化できる。**SPA 配信は `app.frontend(path, directory=..., fallback="index.html")`(0.138.0・2026-06-20 で追加)が第一候補**。`StaticFiles(html=True)` は SPA フォールバックを持たない。frontend のフォールバックは `Accept: text/html` の GET/HEAD のみ、JS/CSS の欠落は 404、path operation 優先。fastapi の下限は `>=0.143.2` を案(frontend の修正を含む)。indexer の lock は 0.162.4 で frontend を含む。
- opensearch-py 3.2.0(sync)で `client.cat.indices/shards/nodes(format="json", h=..., bytes="b", s=...)` が使える。`cluster.health` の応答フィールド(`status`、`number_of_nodes`、`active_shards_percent_as_number` ほか)。OpenSearch 3.9.0(compose)・セキュリティ無効(MVP)。`master_timeout` は非推奨で `cluster_manager_timeout`。権限(セキュリティ有効時)は `cluster_monitor`・`indices_monitor` 系。
- Playwright 1.65.1。`page.route` で API モック、`route.fetch()` で書き換え、`webServer` は `url`・`reuseExistingServer: !process.env.CI`。

### 未確認(実装時に確認。設計書では「実装時確認」として FARC-U / BAPI-U 等に載せる)

- vite-plugin-vuetify 2.1.3 と Vite 8(Rolldown)の実機組み合わせ、Vuetify 4.3.4 `VDataTableServer` の挙動、Vuetify 公式の Node 最小要件(第三者ミラーで 24.11.1)、`@mdi/js` の社内ポリシー、TS 6.x の最新パッチ
- Hey API の `throwOnError` の既定と Query のエラー処理(stale 表示)の接続、生成コードの Git コミット方針
- `app.frontend("/admin", ...)`(`/` 以外のマウント)の細部(`/admin` 末尾スラッシュなし、`/admin/` 配下の存在しないアセットの 404、`/api/` 配下の扱い)
- `cat.*` の `format=json` の値の型(文字列になる想定。クローズ済みインデックスの null)、未割り当てシャードの `node` null、`limit` を `params` で渡せるか、`cat.indices` の 3.9 追加列 `system`、セキュリティ有効時の最小権限
- Playwright の `baseURL` に `/admin/` を含めたときの相対遷移の解決、Vitest を jsdom にするか Browser Mode にするか(DS 10.1 は jsdom 前提)

### 設計書への反映事項(推奨)

1. Node の最小・推奨版を E に明記(推奨 Node 24 LTS。Dockerfile の build ステージも揃える)
2. 型生成は `app.openapi()` で OpenAPI JSON を書き出して入力にする(サーバー起動不要、CI で再現可)。実行時の OpenAPI 公開は環境変数で制御し、認証なし前提のため**既定は無効**を案とする(ゲート2で確認)
3. `api` の fastapi 下限は `>=0.143.2` を案。マウントパス `/admin` の細部は実装時確認
4. O1 の `cat.*` は `h=`・`bytes=b` を明示し、`format=json` の値は文字列として受け Admin API 側で int/null に変換して返す
5. Hey API は 0.x のため exact pin とリリースごとの移行確認
6. 固定範囲: Vuetify exact、TypeScript `~6.0.x`、vue-tsc・Vite は minor 固定
7. E2E は `page.route` モックを主とし、実 API は少数のスモーク。モック応答は生成した OpenAPI 型で `satisfies` 型付けする。Vitest は composable・フォーム検証・エラー表示・Query 設定、Playwright は遷移・ガード・画面フロー・SPA フォールバック
8. Admin API を (a) 1つの FastAPI アプリ内の `APIRouter` にするか、(b) マウントするサブアプリにするかは A の 5 章で案として決める(tech-advisor は両案の差を提示: (a) は Search API・MCP 追加で OpenAPI が1つに混ざる、(b) は Admin 専用 OpenAPI を独立に出せるが `root_path`・`servers` の確認が要る)

## ユーザー判断が要る点(ゲート2に載せる)

- 型生成ツール: Hey API(0.x の churn を許容するか)
- Admin API の構成: `APIRouter` かサブアプリのマウントか
- OpenAPI の実行時公開の既定(無効を推奨)

## 未対応事項

- フェーズ1(document-writer: A → B 骨子)の依頼
