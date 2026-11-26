# 0005 技術検証(P2-a・P2-b)

- 日付: 2026-11-26
- 実施: `code-implementer` × 2(リポジトリ外のスクラッチのみ。`apps/web/` は作っていない。git 操作なし)
- 環境: **Node v24.22.3**(スクラッチに `npm i node@24`。ローカル既定の Node 25.2.1 は EOL・Vitest/jsdom/Playwright の公式対象外のため不使用)、npm 11.6.2、Docker 20.10.13(`nginx:alpine` = nginx/1.31.10)
- スクラッチ: `/private/tmp/claude-501/-Users-yfujita-fuji-private-github-loreley/6b66f4c5-c46e-4d69-9dac-badfbe781e6b/scratchpad/`(`p2a/`・`p2b/`)。消えても本記録の設定と手順で再現できる
- 入力: 0004 の実 OpenAPI(sha256 `ce60fc1a…bf51`)
- 判定: 全項目 **OK**(ただし注意点あり。下記 3 章)。未検証は 4 章

## 1. P2-a: Hey API 0.99.0 × 実 Admin OpenAPI

入った版: `@hey-api/openapi-ts` 0.99.0(exact)、`@tanstack/vue-query` 5.108.4、`vue` 3.5.46、`typescript` 6.0.3、`vue-tsc` 3.3.14。生成設定(`openapi-ts.config.ts`)は次のとおり:

```ts
import { defineConfig } from '@hey-api/openapi-ts';
export default defineConfig({
  input: './admin-openapi.json',
  output: 'src/client',
  plugins: ['@hey-api/client-fetch', '@hey-api/typescript', '@hey-api/sdk', '@tanstack/vue-query'],
});
```

| # | 項目 | 判定 | 結果 |
| --- | --- | --- | --- |
| 1 | 生成物の構成・公開名(FMOD-U-3) | OK | **17 ファイル・4,349 行・約 114KB**。`client/index.ts`(再 export)、`client.gen.ts`(クライアント。`baseUrl '/api/admin/v1'` は spec の `servers[0].url` から**自動で入る**)、`sdk.gen.ts`(SDK 関数 14)、`types.gen.ts`(1,918 行)、`@tanstack/vue-query.gen.ts`(375 行)、`client/`・`core/`(ランタイム)。名前: SDK は operationId の camelCase(`getDashboard`・`listJobs`・`getJob`・`cancelJob`・`getMeta`・`getCluster`・`listSources`・`registerSource`・`getSource`・`updateSource`・`startCrawl`・`startSourceDelete`・`listDocuments`・`releaseLock`)。Query: GET は `{fn}Options`・`{fn}QueryKey`、POST/PUT/DELETE は `{fn}Mutation`。型は `{Op}Data`・`{Op}Responses`・`{Op}Errors` など |
| 1a | 名前の衝突 | 注意 | スキーマ `CancelJobResponse`・`ReleaseLockResponse` と EP 側の `{Op}Response` が衝突し、EP 側が `CancelJobResponse2`・`ReleaseLockResponse2` になる(FMOD-U-3: 生成型を直接使わず、スキーマ型を使う方針が安全) |
| 1b | Infinite 系 | 注意 | `page` を持つ `list_jobs`・`list_documents` に `*InfiniteOptions` が自動生成され、内部に `@ts-ignore`・`as any` を含む。`{ name: '@tanstack/vue-query', infiniteQueryOptions: false }` で消える(375 → 286 行)。MVP は通常のページ送りなので **`infiniteQueryOptions: false` を採用する案** |
| 1c | `register_source` | OK | 200・201 とも `SourceSettings`(`RegisterSourceResponses` は `{200, 201}` の union) |
| 2 | `throwOnError`(FARC-U-4) | OK(注意あり) | **既定は throw しない**(SDK は `{data, request, response}` または `{error, request, response}` を返す)。**生成された `queryFn`・`mutationFn` は内部で `throwOnError: true` を渡す**ので、TanStack Query の `error` は `ErrorResponse \| null`(vue-tsc 通過)。ただし**実行時の形は型と食い違う場合がある**: 404 JSON はパース済み `ErrorResponse`、**502 の HTML は `string`**、**通信断は `TypeError`**(`throwOnError: true` で throw されるのは `Error` インスタンスではないパース済み JSON/文字列)。→ 実行時は `unknown` 扱いにして型ガード(または `interceptors.error`)で正規化する層が要る。設定は `client.setConfig({ baseUrl, throwOnError, fetch })`、`interceptors.{request,response,error}`、EP 単位の `client` 差し替えが使える |
| 3 | パス値のエンコード(FARC-U-18・FMOD-U-2・HO-46) | **一部 NG** | 実装は `encodeURIComponent`。`a%b?c#d` → `a%25b%3Fc%23d` OK、`a/b` → `a%2Fb` OK、日本語 OK。**`.` → `/jobs/`(一覧 EP を叩く)、`..` → `/api/admin/v1/`(1 階層上)に正規化される**(WHATWG URL)。`%2e%2e` は二重エンコードされ回避にならない。空文字は `/jobs/`、`undefined` はプレースホルダ `%7Bjob_id%7D` が残る。→ **`job_id`(と空文字)の送信前検証が必須**(`.`・`..`・空・制御文字を拒否)。API 側は `.`・`..` を 404 `job_not_found` で拒否するが(0012・0018)、SDK が URL を壊すので FE で弾く。`source_id` は `[A-Za-z0-9._-]` で `.`・`..` を含みうるので同様に検証する(API の形式は先頭が英数字なので `.`・`..` は 400) |
| 3a | Node 固有 | 注意 | Node 単体では相対 `baseUrl` の `new Request()` が Invalid URL になり、生成クライアントは `{error: TypeError}` として黙って返す(`throwOnError: false` 時)。Vitest は happy-dom/jsdom 環境か絶対 `baseUrl` を使う |
| 4 | `ttl_days`/`ttl_seconds`(前提タスク A の影響) | OK | `RegisterSourceBody`・`UpdateSourceBody` は `ttl_days?: number \| null`・`ttl_seconds?: number \| null`(optional かつ nullable)。キーを省くのは型・実行時とも OK、`undefined` はキーごと JSON から消える、`null` は `"ttl_days":null` で送られ実行時に 400。→ フォーム用の型(`{ttl_days:number} \| {ttl_seconds:number}`)を自前で作るか、前提タスク A の後に再生成する。応答側は `SourceSettings.ttl_seconds: number`、`SourceDetailResponse.ttl_days/ttl_seconds: number \| null` |
| 5 | 決定性と量(FARC-P-6) | OK | 同一入力 3 回+別ディレクトリで `diff -r` の差分 0。タイムスタンプ・絶対パスの埋め込みなし。生成物は 4 スペース・クォート混在のため lint/format 対象外にする。→ **コミットしても spec 更新時以外のノイズは出ない。CI で再生成して差分ゼロを検証する運用が向く** |
| 6 | `vue-tsc --noEmit`(strict) | OK(注意あり) | A: strict+skipLibCheck → 0 件。B: skipLibCheck false → 0 件。C: `noUncheckedIndexedAccess`・`noUnusedLocals`・`noUnusedParameters`・`noImplicitOverride` 追加 → 0 件。**D: `exactOptionalPropertyTypes` → 生成コード内に 12 件(TS2379)**、さらに `@tanstack/vue-query` の d.ts でも TS2416。→ `exactOptionalPropertyTypes` は有効にしない(または生成ディレクトリを別 tsconfig で検査)。`useQuery(computed(() => getJobOptions(...)))` の `.data` は `JobDetailResponse \| undefined`、`.error` は `ErrorResponse \| null` |
| 7 | 型の形 | OK | `ErrorResponse = { error: ErrorBody }`、`ErrorBody = { code: string; message: string; retryable: boolean; details?: ErrorDetails \| null }`。**`code` は string(union でない)**。どの code が返るかは `{Op}Errors` の JSDoc にしか出ない(= 手書きの `errorTable` が要る。S-D7)。`{Op}Errors` はステータス別だが値は全部 `ErrorResponse`。`ErrorDetails` は全キー任意の 1 型。**日時は素の `string`**(`format` なし。`responseTransformer` 未使用)。列挙は union 型(`DocumentTab`・`JobStatus`・`JobType` など。`@ts-expect-error` で不正値が弾かれる) |

## 2. P2-b: Vite 8 + Vuetify 4.3.4 のビルドと Nginx 配信

入った版(`npm ls`・`npm ci` でも同一): `vite` 8.3.8、`vuetify` 4.3.4、`vite-plugin-vuetify` 2.1.3、`@vitejs/plugin-vue` 6.0.11、`vue-router` 5.5.1、`vue` 3.5.46、`typescript` 6.0.3、`vue-tsc` 3.3.14、`sass` 1.108.2、`@mdi/js` 7.4.47、`@types/node` 24.19.4。`npm install`・`npm ci` とも peer/engines 警告・EBADENGINE・deprecated 0 件、`npm audit` 0 件。

| # | 項目 | 判定 | 結果 |
| --- | --- | --- | --- |
| 1 | ビルド(FARC-U-1) | OK | `base: '/admin/'`、`createWebHistory(import.meta.env.BASE_URL)`、`@mdi/js` を `vuetify/iconsets/mdi-svg` で使用。`vue-tsc --noEmit && vite build` が通る(713 モジュール、約 9.5 秒)。**`vue-router` 5.5.1 は v0.1 の Vue Router 4 前提のコード(`createWebHistory`・`router-link`・`:to="{name}"`)が差分なしで動く**。`VDataTable` の型は `VDataTable['$props']['headers']` で付く(`VDataTableServer` は未確認) |
| 2 | 開発サーバー | OK | `/admin/` 200、`/admin/sources` 200。`server.proxy['/api']` で別ポートに転送でき、転送先は環境変数で上書き可。**`/admin`(末尾スラッシュなし)は dev では 404**。dev サーバーは `localhost`(`::1` 含む)で待ち受け、`127.0.0.1` 指定の curl は接続できない |
| 3 | `styles.configFile` | OK | `@use 'vuetify/settings' with ($body-font-family: …, $button-border-radius: 1px)` が成果物の CSS と実機の `getComputedStyle` に反映(Vuetify 4 は見出しも `$body-font-family` に連動) |
| 4 | tree-shaking | OK | JS/CSS(raw/gzip): VBtn のみ 228KB/83KB・218KB/32KB、今回の SPA(VApp・VAppBar・VMain・VContainer・VBtn・VDataTable)420KB/142KB・311KB/44KB、全 import(上限)796KB/255KB・541KB/72KB。VDataTable で JS +約 190KB、CSS +約 94KB。CSS の約 190KB は `vuetify/styles` の固定分(ユーティリティは tree-shaking されない)。DS 10.1 の「フルビルド CSS 538KB・JS 735KB」と整合 |
| 5 | 出力構成・外部参照 | OK | `dist/index.html`(0.4KB)が直下、`dist/assets/index-<hash>.{js,css}`。`/admin/assets/…` を指す。googleapis・gstatic・cdn・jsdelivr・unpkg・`@import url`・`url(http` は 0 件(`http(s)://` は XML 名前空間と Vue のエラー参照文字列のみ)。外部フォントなし |
| 6 | `build.target` | OK | 既定 `baseline-widely-available` = `['chrome111','edge111','firefox114','safari16.4','ios16.4']`(`cssTarget` も同じ)。Vuetify 下限(Chromium 119/Firefox 128/Safari 16.4)より低く、変換不足はない。成果物の CSS は `:has()`・`color-mix()`・`@layer`・`@property`・`dvh` を変換せず使う(Firefox 128+・Safari 16.4+ で動く範囲。Firefox 114〜127 では動かないので `target` を下げても意味がない) |
| 7 | Nginx 配信 | OK | 下の設定で `nginx -t` 成功、短時間コンテナ(`127.0.0.1:18080`)で curl・playwright-cli(Chromium)確認。コンテナ・ネットワーク・ダミー upstream は削除済み(`nginx:alpine` のイメージのみ残る)。結果は 2.2 |
| 8 | 依存の警告 | OK | 警告なし |

### 2.1 注意点(設計・実装に効く発見)

1. **`main.ts` で `import 'vuetify/styles'` が必須**。`vite-plugin-vuetify` はコンポーネント単位の CSS しか入れず、これが無いとリセット CSS・タイポグラフィ・ユーティリティ(`d-flex` など)が入らない(ブラウザ既定の Times になった)。`styles.configFile` の変数もここに効く
2. **`sass` は `styles.configFile` を使うときだけ必須**。`styles: true` なら sass なしで通る。`configFile` を使い sass が無いと `Preprocessor dependency "sass-embedded" not found` でビルドが失敗する。DS が `configFile` を使うので `sass`(dart-sass。sass-embedded は不要)を dependencies に入れる
3. `vite.config.ts` を tsconfig の `include` に入れて `process.env` を使うなら、`@types/node`(`^24`)と `"types": ["node"]` が必要(無いと `TS2591`)
4. Nginx の `proxy_pass` にリテラルのホスト名(`http://api:8080`)を書くと、`api` 未起動の起動順で `host not found in upstream` により `nginx -t`・起動が失敗する。**`set $api_upstream http://api:8080;` + `proxy_pass $api_upstream;` + `resolver 127.0.0.11`(Docker の内部 DNS)で回避**でき、URI 部のない変数 `proxy_pass` は元のリクエスト URI(`%2F` 等を含む)をそのまま渡す(`%2F`・`%2E` の保持そのものは今回の確認項目に含めておらず未検証。4 章)。`resolver 127.0.0.11` は user-defined network でのみ有効(既定の bridge では 502)。compose のプロジェクトネットワークは user-defined
5. `add_header` は子 location に継承されない(`/admin/assets/` は自分で `Cache-Control` を書く)。セキュリティ関連ヘッダー(CSP 等)を足すなら各 location に書く
6. `Host` は `$host` だとポートが落ちる(`$http_host` ならポート付き)。`X-Forwarded-For` はクライアント指定値の後ろに追記される(認証なしの内部用なので問題としない)

### 2.2 Nginx の確認結果(コンテナ `p2b-nginx-check`、`127.0.0.1:18080` のみ公開)

| 要求 | 結果 |
| --- | --- |
| `/admin/` | 200 `text/html`、`Cache-Control: no-cache` |
| `/admin/sources/xxx`(深い SPA パス) | 200 で `index.html`(405 バイト)、`no-cache` |
| `/admin/assets/<hash>.js`・`.css` | 200、`Cache-Control: public, max-age=31536000, immutable`、`Content-Type` 正しい、gzip 対応(JS の実転送 165KB) |
| `/admin/assets/存在しない.js`、`/admin/assets/` | **404**(`index.html` を返さない)。404 に `Cache-Control` は付かない(`add_header` に `always` なし) |
| `/api/admin/v1/meta` | upstream の 200・`application/json`・`Cache-Control: no-store` が**素通し** |
| `/admin`(末尾スラッシュなし) | 301 `Location: /admin/`(`absolute_redirect off` で相対 Location。外すとポートマッピングで壊れる) |
| `/`(ルート) | 302 `/admin/`(案。書かないと既定の「Welcome to nginx」が出る) |
| `/api`(末尾スラッシュなし) | 301 `/api/` |
| `/healthz` | 404(`api` の `/healthz` は Nginx から届かない) |
| `/admin/favicon.ico`(dist に無いファイル) | **200 で `index.html`**(`assets/` 以外の欠落ファイルは SPA に落ちる。A の「`Accept: text/html` の GET/HEAD だけ」とは異なる挙動 → 許容するか G4 ではなく v0.2 で決める) |
| `POST /admin/`、`GET /admin/../etc/passwd`(`--path-as-is`) | 405、404 |
| 本文 1 MiB ちょうど(`client_max_body_size 1m`) | upstream に届く |
| 本文 1 MiB + 1 バイト | **Nginx が HTML の 413**(A 5.1 は API が JSON の 400 を返すと定めるため、1 MiB 超だけ API のエラー形式にならない) |
| upstream 停止(接続拒否) | **HTML の 504**(環境により 502 の場合あり) |
| 実機(playwright-cli) | `/admin/sources` の直開きで VDataTable 描画、Dashboard のボタンで `/api/admin/v1/meta` がプロキシ越しに 200、未知パスで SPA 起動、コンソールエラーは `/favicon.ico` の 404 のみ |

使った Nginx 設定(`/etc/nginx/conf.d/default.conf`、`dist/` は `/usr/share/nginx/html/admin/` に置く = Dockerfile の `COPY dist /usr/share/nginx/html/admin` 相当。`alias` は使わない):

```nginx
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    absolute_redirect off;

    gzip on;
    gzip_types text/css text/javascript application/javascript application/json image/svg+xml;
    gzip_min_length 1024;

    location = / { return 302 /admin/; }          # Search View の置き場が未決(BAPI-U-4)のため当面 /admin/ へ
    location = /admin { return 301 /admin/; }

    location /admin/ {
        add_header Cache-Control "no-cache";
        try_files $uri /admin/index.html;
    }
    location /admin/assets/ {
        add_header Cache-Control "public, max-age=31536000, immutable";
        try_files $uri =404;
    }
    location /api/ {
        resolver 127.0.0.11 valid=10s ipv6=off;
        set $api_upstream http://host.docker.internal:18081;   # 検証用ダミー。本番想定: http://api:8080
        client_max_body_size 1m;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 5s;
        proxy_send_timeout    30s;
        proxy_read_timeout    90s;   # 仮値(E 5.3 の書き込み 90 秒以上。実装時確認)
        proxy_pass $api_upstream;    # proxy_cache は使わない。Cache-Control は素通し
    }
}
```

(`api` のポートは compose の `8080`。P2-b のダミーは 8000 と書いていたため、本記録では `api:8080` に直した。)

使った `vite.config.ts`(`src/styles/settings.scss` は `@use 'vuetify/settings' with (...)`):

```ts
import vue from '@vitejs/plugin-vue'
import vuetify from 'vite-plugin-vuetify'
import { defineConfig } from 'vite'
const devApiTarget = process.env.P2B_DEV_API_TARGET ?? 'http://127.0.0.1:18081'
export default defineConfig({
  base: '/admin/',
  plugins: [vue(), vuetify({ autoImport: true, styles: { configFile: 'src/styles/settings.scss' } })],
  server: { proxy: { '/api': { target: devApiTarget, changeOrigin: false } } },
  build: { outDir: 'dist' },
})
```

## 3. 設計への反映候補(P3 の入力)

- E 3(ビルド・配信): `import 'vuetify/styles'`、`sass` を dependencies に、`@types/node`、`infiniteQueryOptions: false`、`exactOptionalPropertyTypes` は有効にしない、生成物を lint/format の対象外にして CI で再生成差分ゼロを検証、`build.target` は既定のまま(明示は任意)
- E 3(配信): 上の Nginx 設定を方針として採用する案(`/admin/` の SPA フォールバック、`assets/` は 404+長期キャッシュ、`/admin` の 301、`/` の 302、`/api/` のプロキシ(変数+resolver、`proxy_cache` なし、`proxy_read_timeout` ≥ 90s)。数値は実装時確認
- E 5・6(データ取得・エラー): 実行時 `error` は `unknown` 扱いで `ErrorResponse` かを型ガードし、`string`(HTML)・`TypeError`・`ErrorResponse` を `ApiError` に正規化する層、`job_id`/`source_id` の送信前検証(`.`・`..`・空・制御文字を拒否)、`errorTable` は手書き(code は string のため)、日時は string のまま画面側で変換
- F: 生成型は `{Op}Response2` を避けスキーマ型を使う、Infinite 系なし、`SourceSettings` が 2 種類
- コミット方針(FARC-P-6): 決定的で量は 17 ファイル・約 114KB のため、コミットして CI で再生成差分を検査する運用が成立(G4 で確定)
- FARC-U の状態: U-1 解消(ビルド OK。ただし `vite-plugin-vuetify` の Vite 8 明示対応は無く、実機で通ったことのみ確認)、U-4 解消(上記)、U-5 解消(決定性・量)、U-6 は Nginx 版として一部解消(設定案の確認済み。本番の compose 結合は前提タスク B)、U-10 解消(0004 の 4 章)、U-18 は SDK 側の挙動を確認(要検証層)、FMOD-U-2 解消、FMOD-U-3 解消(命名・衝突を確認)

## 4. 未検証・未対応

- `VDataTableServer` の挙動(FARC-U-2)、Firefox 128・Safari 16.4 の実機(FARC-U-15)、`vite build` の Docker マルチステージ化、実 API サーバーへの接続(fetch 差し替えで検証)、zod/valibot の `responseValidator`
- Nginx 越しの `%2F`・`%2E` の保持(`job_id` のエンコード)は今回の確認項目に含めなかった。`proxy_pass` を URI 部なしの変数にした場合に元の URI が渡ることは確認したが、`%2F` を含む実リクエストでの実測は無い → 前提タスク B の実装時確認(HO)に回す
- `proxy_read_timeout`・`client_max_body_size` の最終値、`Host` を `$host` か `$http_host` にするか、`/` の扱い(BAPI-U-4)、`error_page` で JSON を返すか、`add_header ... always`・セキュリティヘッダー(CSP 等)は実装時確認
- `/admin/` 配下の `assets/` 以外の欠落ファイルが 200 の `index.html` になる点の扱い(許容案: SPA の深いパス `/admin/sources/xxx` と区別できないため。`/favicon.ico` 等は `dist/` に置く)
