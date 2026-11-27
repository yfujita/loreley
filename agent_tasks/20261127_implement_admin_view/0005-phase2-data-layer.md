# 0005 フェーズ 2: データ取得層と純粋ロジック

作成日: 2026-11-27 / 工程: 実施(フェーズ 2 完了)
ブランチ: `feature/implement-admin-view` / 比較基準: `6cd6210`(フェーズ 1 完了時)/ 終了時 HEAD: `3aae595`(本記録のコミットは含まない)

## 1. 実施した作業の概要

0002 フェーズ 2 に従い、API クライアント、エラー正規化、Query 層(キー・ポーリング・invalidation・EP ごとの読み取りと mutation)、`lib` の純関数、`composables`、バリデーション、テスト支援(フィクスチャ・fetchStub・mockApi)、契約テスト、実 Chromium での API クライアント E2E を実装した。UI・画面・シェル・テーマには進んでいない。`code-implementer` が実装し、`code-reviewer`・`test-reviewer` を初回 + 再レビュー 2 回で実施し、Critical・Important を解消した。ユーザー確認が必要な方式変更は発生しなかった(`withKey` 維持、`TimeoutError`/`AbortError` は E 5.3 のまま)。

## 2. コミット

| コミット | 内容 |
| --- | --- |
| `28db13e` | 実装 |
| `d1c0ddc` | レビュー指摘の修正 1(409 の invalidate・`networkMode`・テストの強化) |
| `3aae595` | レビュー指摘の修正 2(`Content-Length: 0` による 2xx 検査の迂回を塞ぐ ほか) |

## 3. 変更ファイル(`apps/web/` 配下。累積 112 ファイル、`*.test.ts` 44 本を含む)

- 実装(`src/`): `shared/api/{apiError,unicode}.ts`、`shared/lib/{datetime,number}.ts`、`admin/api/{client,pathParams,index}.ts`、`admin/api/errors/{toApiError,errorTable,describeError}.ts`、`admin/queries/{keys,params,withKey,queryClient,polling,placeholder,invalidation,meta,dashboard,sources,jobs,documents,opensearch}.ts`、`admin/queries/mutations/{createSource,updateSource,startCrawl,deleteSource,cancelJob,releaseLock}.ts`、`admin/lib/{unavailable,expectedFields,leaseExpiry,existingJob,clusterValues,routeNames,actions,units,lockStateView,viewState,injectionKeys,pagination}.ts`、`admin/lib/validation/{limits,patterns,rules}.ts`、`admin/composables/{useListParams,useDebouncedRef,useDocumentTitle,useViewState}.ts`
- テスト支援・E2E(`tests/`): `support/{apiErrors,fetchStub,mockApi,queryTesting,composableTesting,viteReady}.ts`、`support/fixtures/{meta,dashboard,sources,jobs,documents,opensearch}.ts`、`e2e/{apiClient.spec,mockApi.spec,globalSetup}.ts`、`support/{setup,mount}.ts`(更新)
- 設定: `eslint.config.js`(素の `setTimeout`・`setInterval` の禁止)、`vite.config.ts`(`unstubGlobals: true`)、`playwright.config.ts`(`globalSetup`)
- 変更していない: 生成コード・`openapi/admin-v1.json`・`src/main.ts`・Nginx・compose・`apps/api`

## 4. 検証結果(メインエージェントが再実行。Node 24.22.3)

| コマンド | 結果 |
| --- | --- |
| `gen:api:check`・`typecheck`・`lint`・`format:check`・`build` | 成功 |
| `npm run test` | 45 ファイル 1150 件成功(3 回連続で安定。`--sequence.shuffle` も成功) |
| `npm run test:e2e` | 28 件成功(専用ポート 15173)。CPU 高負荷下(vitest 並列)でも成功 |
| `docker build -t loreley-web-check apps/web` | 成功 |

## 5. 実装時確認事項の結果

| ID | 結果 |
| --- | --- |
| **FARC-U-22 = FMOD-U-12** | (1) interceptor が受ける値と正規化は、E 5.3 の表の全行を jsdom で、主要 8 行を実 Chromium で確認。request interceptor の例外は error interceptor を通って合成の 400 `invalid_request` になる。(2) `AbortError`(Query のキャンセル)と `TimeoutError`(クライアントの時間切れ)は区別できる。時間切れは `{kind:'timeout'}`、中断は `kind` を持たない。実 Chromium で Playwright の時計を 45 秒進めて確認。(3) `AbortSignal.any` は使わない(Chrome 116・Firefox 124・Safari 17.4。設計の推測どおり Safari 16.4 で不可)。呼び出し側のシグナルは `abort` リスナーで内側の `AbortController` に転送。(4) `withKey` は実ブラウザ(Chromium)の取得で動き、prefix の invalidate が意図どおり働く。型のキャストは 1 か所。(5) 本文受信の完了までを時間切れの対象にする方式は、fetch の中で `arrayBuffer` まで読み切って `Response` を再構築し、abort を待つ Promise と `race` させる。本文受信が止まった場合・途中で止まった場合とも 45 秒で `timeout`。(6) **`withKey` を維持**(独自 Options への切替は不要と判断。ユーザー確認なし)。相対 `baseUrl`: jsdom では解決されず、実 Chromium では解決される |
| **FMOD-U-9**(`.`・`..` の ID、純関数側) | `encodeURIComponent` 後も `.`・`..`・空文字は URL で化ける(実測: `.`→`/jobs/`、`..`→`/api/admin/v1/`、空→`/jobs/`)。`a.b`・`..a`・`a..` は無変化。`%2e%2e` は SDK が `%252e%252e` に二重エンコード。`isValidPathId` と request interceptor で「送信しない」を jsdom・実 Chromium の両方で確認(全 EP のパス値・mutation の対象 ID)。孤立サロゲートは SDK の `encodeURIComponent` が request interceptor より前に `URIError` を投げるため、`toApiError` が合成 400 に写す。Vue Router の `/jobs/%2e%2e` の復号は**フェーズ 7 の E2E で確認** |
| **FMOD-U-13**(EP-11 の `expectedFields`) | B 6.1 が null と明記する項目以外は expected とした(`lib/expectedFields.ts`)。skipped は `document_id`・`external_id`・`stage`・`reason`・`attempts`・`consecutive_skips`・`first_skipped_at`・`last_skipped_at`・`last_job_id`、extract_failed は `title` を除く、oversize は `size` を除く、summary_pending は `title` を除く。表の項目名は `satisfies` で生成型のキーに束縛し、フィクスチャの正常な行で expected 項目がすべて非 null であることをテストで確認 |
| **FARC-U-26 (4)** | `enabled: false` のとき `isPending` は true のまま、`isLoading` は false、`fetchStatus` は `idle`。取得中は `isLoading` が true。スケルトンは `isLoading` で出す設計の推測は正しい(`useViewState` は `isLoading` を使う) |

## 6. 設計との差異・判断(設計書は改訂しない。Q2。追従は別タスクへ申し送り)

1. **`parseAs: 'json'` を `setConfig` に追加**: 生成クライアントの既定 `parseAs: 'auto'` では、Content-Type が `text/html` の 2xx が失敗にならず文字列が `data` に載る。E 5.3 の「2xx で JSON でない → SyntaxError」は JSON を宣言した場合だけ成り立つ。
2. **`responseValidator`(2xx の空・非オブジェクト本文を `invalid_response` に)**: E 5.3 の表にない追加。OpenAPI の 2xx 全 16 件が、必須項目を持つオブジェクトで `{}` を返す EP がないことをスクリプトで確認したうえで採用。生成クライアントは `Content-Length: 0` と 204 を検査に通さないため、`fetchWithTimeout` が Response を再構築する際に `content-length` を外す(本文はデコード済みで元の値は不正確)。実 204 は SDK の挙動のとおり `{}`(Admin API は返さない。`client.test.ts` で固定)。
3. **`networkMode: 'always'`**(queries・mutations): E 5.3・5.4 にない追加。既定の `online` だとオフライン中に mutation が paused になり、再接続後に削除・取消・ロック解放が遅れて実行され得るため。
4. **取消の 409 `job_already_finished`(成功扱い)でも invalidate**(`useInvalidatingMutation` の `onError`): E 5.8 の表のとおりに実装を直した。
5. **公開口 `@/admin/api` は `client` を再 export しない**(F 3.3: SDK・client は Query・mutation 経由のみ)。このため `tests/support/setup.ts` の `client` 直 import の理由付き `eslint-disable` は残る(理由文を更新)。`environment.test.ts` の SDK 直 import は公開口経由に置換して外した。
6. **`configureApiClient()` は引数なしで baseUrl に触れない**(E 5.3)。`setup.ts` が `configureApiClient()` の後に絶対 baseUrl を上書きするため衝突しない。本番の相対 `baseUrl` は `vi.resetModules()` で生成直後のモジュールを読んで固定。
7. **`fetchStub`**: `vi.stubGlobal('fetch')` + `afterEach` の `unstubAllGlobals`(`configureApiClient` の fetch は差し替えない。申し送り 4 の「client.setConfig の fetch を戻す」とは実装が異なるが、目的(テスト間の漏れ防止)は満たす)。`unmatched` 検査と `unstubGlobals: true` を併用。
8. **追加した抽象**: `lib/pagination.ts`(`25|50|100`・既定 25。lib 以外に `ItemsPerPage` の置き場がない)、`queries/params.ts`(`JobsQuery`・`DocumentsQuery` とスコープ関数。`keys.ts` の相互 import を解消)、`shared/api/unicode.ts`(R17 は `admin/api` が import できる shared を `shared/api` だけと定めるため)、`useInvalidatingMutation`(mutation 6 本で共有)。`daysToSeconds` は設計に使う予定がなく削除。
9. **`describeError` の返り値を拡張**: 設計の `{target, variant, retryable, outcomeUnknown, fieldErrors, diagnostic}` に `notFound`・`resendSafe`・`unexpected`・`crawlerMessage`・`lockState` を追加(画面が `error.code` を判定しないため)。`just_acquired` の variant は設計に明記がなく error とした。`target: 'field'` は暫定で、表にない field・`detail` は features の `fieldMap`(フェーズ 6)が form-alert に落とす。
10. **`useViewState`**: 取得していない(`enabled:false`)状態は `empty` として扱う(kind を増やさない)。呼び出し側(X1 のソース未選択など)が先に判定する前提(コメントで明記)。
11. **タイマー規約**: `src/` の非テストでは `window.setTimeout` / `window.setInterval`(bare は ESLint で禁止)。
12. **E2E 基盤**: dev サーバーの事前ウォームアップ(`globalSetup.ts`)と `viteReady.ts` を追加(dev サーバーが Vue Query を初めて見つけて再読込する挙動への対策)。フェーズ 3 で `main.ts` が Vue Query を import すれば不要になる。

## 7. レビュー結果

- 初回: code-reviewer は Critical 0・Important 2(409 の invalidate、`networkMode`)、test-reviewer は Critical 0・Important 6(タイムアウト値の固定、`describeError` 書き込み側、`enabled:false` の検証、J1 の `sourceId` スコープ、E2E の安定性、フィクスチャの欠落)。変異 138 件のうち 23 件が生存。
- 再レビュー(`d1c0ddc`): code-reviewer は Important 1(`Content-Length: 0` が `responseValidator` を迂回)、test-reviewer は **Critical・Important なし**(Suggestion 2: `toApiError` の `outcome_unknown:false`、サロゲート境界)。E2E は通常 3 回・CPU 高負荷下 2 回とも成功。
- 確認(`3aae595`): code-reviewer は **指摘なし(可)**。

見送りの判断:

| 指摘 | 判断 |
| --- | --- |
| `useViewState` に `idle` kind を足す案 | 見送り。`networkMode: 'always'` で paused が消え、`enabled:false` は呼び出し側が先に判定する前提(設計の 6 種 kind に収める)。フェーズ 8(X1)で再確認 |
| `describeError` の `target:'field'` の再分類 | フェーズ 6 の `fieldMap` で扱う |
| `fieldErrorsResponse`(フィクスチャ)の未使用 | フェーズ 6 で S3・S4 の E2E が使う |
| `fetchStub` の `unmatched` 検査自体の自己検証 | 見送り(メタな安全網。変異は一時テストで確認済み) |
| `queryClient.test.ts` の 20ms 実時間待ち | 見送り(「再送されない」「paused のまま」という否定の検証で `vi.waitFor` にしにくい) |
| `refetchOnMount: 'always'`(`sources.ts`)の変異生存 | 見送り(`gcTime: 0` と等価に近い) |
| `lockRefusals` を `formatLeaseExpiry`・`canLinkToJob`・`describeError` へ通す結合的なテスト | フェーズ 5・7 の E2E |
| `waitForViteReady`・`globalSetup` の削除 | フェーズ 3(`main.ts` が Vue Query を import したら) |
| `evaluateInBrowser` が文字列コード(型検査が効かない)、`pathParams.test` の `expect.assertions` | 見送り(実害なし) |

## 8. 後続フェーズへの申し送り

- **フェーズ 3**: (1) `main.ts` を作り直し、`configureApiClient()` を admin/app の起動より前に 1 回呼ぶ。暫定の `eslint-disable` を削除。(2) `tests/support/mount.ts` を本番の `setupVuetify` に差し替え(`mobileBreakpoint` を本番設定と一致させる)。(3) `smoke.spec.ts` が `PlaceholderPage` に依存しているため書き換える。(4) `tsconfig.test.json` に `src/**/*.d.ts` を追加(`meta.d.ts` を足すとき)。(5) `QueryClient` のテスト後 `clear()`。(6) `viteReady.ts`・`globalSetup.ts`・`apiClient.spec.ts` の `beforeEach` の待機は、`main.ts` が Vue Query を import すれば不要になる。外してよいかを確認。(7) `BreadcrumbItem = {title, to: string|null}`(`lib/injectionKeys.ts`)に `useBreadcrumbs` を合わせる。(8) `ActionSpec` は設計どおりの 5 項目のみ(「主操作は 1 つ」は PageActions で必要なら検討)。
- **フェーズ 5〜7**: `describeError` の `resendSafe`・`outcomeUnknown`・`lockState`・`crawlerMessage` を使う。`lockRefusals`(`tests/support/apiErrors.ts`)を DLG-1・4・5 の E2E で使う。`fieldMap`(フェーズ 6)が `target:'field'` の再分類を担う。`/jobs/%2e%2e` の Vue Router の復号をフェーズ 7 の E2E で確認(FMOD-U-9)。
- **フェーズ 8(X1)**: `documents` クエリの `enabled:false`(ソース未選択)は `empty` になる。画面側が先に判定する。
- **フェーズ 10**: Firefox・Safari での挙動(FARC-U-15)、本文受信停止の実ブラウザ版(Playwright の route では再現できない。jsdom の単体のみ)、Nginx 越しの挙動。
- **フェーズ 11(README)**: `npm run test` は `apps/web` で実行する前提。
- **設計書の追従改訂の申し送り候補**(別タスク): 上記 6 章の差異(`parseAs`・`responseValidator`・`networkMode`・`content-length` の除去・公開口の方針・`describeError` の拡張・`pagination.ts`・`params.ts`)。FARC-U-22 の (1)〜(6) の結果。

## 9. 未対応事項

- 上記 7・8 章のとおり。実機(Nginx 越し)・Firefox・Safari での確認は未実施。
- 作業ツリーには、停止した対話コマンドや変異試験の復元漏れがないことを確認済み。

## 10. 次のアクション

- フェーズ 3(テーマ・共通 UI・シェル・ルーティング・アプリ組み立て)を `code-implementer` に依頼する。比較基準は本記録のコミットの SHA。
