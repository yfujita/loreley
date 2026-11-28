# 0007 フェーズ 4: D1 Loreley ダッシュボード・O1 OpenSearch ダッシュボード(読み取り専用)

作成日: 2026-11-28 / 工程: 実施(フェーズ 4 完了。**ユーザー指示によりここで一旦中断**)
ブランチ: `feature/implement-admin-view` / 比較基準: `6cf23ba`(フェーズ 3 完了時)/ 終了時 HEAD: `91098e3`(本記録のコミットは含まない)

## 1. 実施した作業の概要

0002 フェーズ 4 に従い、フェーズ 3 のスタブを D1(30 秒の自動更新・手動更新・取得失敗時の降格)と O1(クラスタ概況・インデックスの絞り込み(URL 同期)・ノード × インデックスのシャード行列・ページ送り・`truncated`)の本実装に差し替えた。`code-implementer` が実装し、`code-reviewer`・`test-reviewer` を並列に実施して修正し、専用 compose 環境と dev サーバーで `web-ui-reviewer`(中間 1)を実施した。UI レビューの修正後に再確認を行い、すべて解消した。ユーザー確認が必要な方式変更は発生しなかった。

**ユーザー指示(2026-11-27〜28)**: フェーズ 4 が完了したら一旦作業を止め、PR を作成する。PR のレビューと、ここまでの振り返りはユーザーと行う。このためフェーズ 5 以降には着手していない。

## 2. コミット

| コミット | 内容 |
| --- | --- |
| `0182323` | 実装(D1・O1・共通部品の最小の拡張・テスト) |
| `0e9e744` | コード・テストレビューの修正(stale アラートの余白・自動更新オン時の即時再取得・境界のテスト・E2E のフレーク解消 ほか) |
| `91098e3` | UI レビューの修正(スイッチ・チェックボックスのフォーカスリング・リサイズ時のフォーカス・favicon・404 の見出し) |

## 3. 変更ファイル(`apps/web/` 配下。累積 約 65 ファイル)

- D1: `src/admin/features/dashboard/`(`pages/DashboardPage.vue`・`composables/useDashboardPage.ts`・`models/dashboardViewModel.ts`・`dashboardComponents.ts`)、`src/admin/components/dashboard-parts/`(`SummaryBand`・`ComponentTile`・`types`)、`src/admin/components/auto-refresh-switch/AutoRefreshSwitch.vue`
- O1: `src/admin/features/opensearch/`(`pages/OpenSearchPage.vue`・`composables/useOpenSearchPage.ts`・`opensearchParams.ts`・`models/{indexFilter,matrixModel,clusterNotices}.ts`)、`src/admin/components/shard-matrix/`(`ShardMatrix`・`ShardPager`・`ShardChip`・`ShardLegend`・`ClusterSummary`・`IndexFilter`・`columnsPerPage.ts`・`pageWindow.ts`・`types.ts`)
- 共通部品の変更: `templates/{PageHeader,DashboardPage,DetailPage,FormPage,ViewStateBody}.vue`、`shared/lib/datetime.ts`(`formatTimeOfDay`)、`lib/clusterValues.ts`(`classifyShard`)、`shared/theme/{icons.ts,global.css}`、`admin/shell/AppShell.vue`(リサイズ時のフォーカス)、`admin/router/NotFoundPage.vue`、`index.html`(favicon)
- テスト: 各ファイルの隣の `*.test.ts`、`tests/e2e/{dashboard,opensearch}.spec.ts`(新規)、`shell.spec.ts`・`smoke.spec.ts`(更新)、`tests/support/{resizeObserverStub.ts,fixtures/{dashboard,opensearch}.ts,fixtures.test.ts,dependencyRules.test.ts,e2eTest.ts}`
- 変更していない: `eslint.config.js`(新ファイルは既存ゾーンに収まる)、生成コード・`openapi/`・Nginx・compose。

## 4. 検証結果(メインエージェントが再実行。Node 24.22.3)

| コマンド | 結果 |
| --- | --- |
| `gen:api:check`・`typecheck`・`lint`(警告 0)・`format:check`・`build` | 成功。ビルドは JS 475.6KB・CSS 334.6KB(未圧縮。フェーズ 3 時点は 386KB・271KB。FMOD-U-11 の測定値) |
| `npm run test` | 114 ファイル 1890 件成功(3 回連続で安定) |
| `npm run test:e2e` | 178 件成功(専用ポート 15173)。CPU 高負荷下でも成功 |
| `docker build -t loreley-web-check apps/web` | 成功 |

## 5. 実装時確認事項の結果

| ID | 結果 |
| --- | --- |
| **FMOD-U-6**(ShardMatrix の列数・列見出しの読み上げ) | jsdom は要素の幅が常に 0 なので、`tests/support/resizeObserverStub.ts`(観測要素と callback を記録する偽の `ResizeObserver`)で幅の通知を駆動する。`useContainerWidth` の初期値は `getBoundingClientRect()` で 0、このときは 1 列になりクラッシュしない。narrow(600px 未満)は `useDisplay().xs` に依存するため、テストは `window.innerWidth` を変えてからマウント。検算表 7 組(1280→7・1145→6・1024→5・840→3・768→5・375→2・320→1)を単体と実ブラウザ(E2E・UI レビュー)で網羅。列幅は全ページ同じ、ページ全体・表内に横スクロールなし。読み上げ名(Chromium のアクセシビリティツリー): 列見出し「demo-docs-000003 ドキュメント 8,402,117 件 yellow」、件数が取れない列「… — ドキュメント件数を取得できません green」、行見出し「node-1 シャード 16 (全インデックスの合計)」、セル「P0 (プライマリ。割り当て済み)」「— シャードなし」。冗長ではなく `aria-describedby` による分離は不要と判断。**実機のスクリーンリーダーは未確認(フェーズ 10)** |
| **FARC-U-26 (4)**(`isLoading`・`enabled:false`・stale の見え方) | D1・O1 は `enabled:false` を使わない。`isLoading` は取得中にスケルトン(D1 はタイル、O1 はカード内+無効フォーム)。見出し・操作行は先に出て、`aria-busy` と隠した `role=status` も出る。再試行する失敗(503 など)は 1 回だけ再試行し、その 1 秒間もスケルトンのまま。stale: 前回データがあるときの再取得失敗はアラートと前回の値(D1 は降格したタイル)、成功すると通常表示に戻る |
| 実機(専用 compose 環境)での確認 | D1: 実 API で正常・異常(crawler・indexer・opensearch の各停止)・復旧を確認。O1: 実 API で通常・OpenSearch 停止のエラー・復旧を確認。実 API で出せない状態(stale・部分失敗・多数インデックス・`truncated`・red・移動中・初期化中)は、ネットワークモックでの表示確認のみ(API 契約との整合は E2E のフィクスチャ(生成型で `satisfies`)で担保) |

## 6. 設計・DS・モックとの差異(設計書は改訂しない。Q2)

1. **O1 は `ViewStateBody` を 2 つ重ね、テンプレートには `READY_VIEW_STATE` を渡す**(仕様: 読み込み中・エラーでもカードの `h2` を残す。テンプレートの標準の状態出し分けはカードごと置き換える)。外側は stale のアラートだけ、内側(カード内)は読み込み中・エラーなど(`ready`・`stale` 以外はそのまま渡す)。進行バーもテンプレート側は止め、カード上端に置いた。
2. **共通部品の最小の拡張**: `PageHeader.aside`(O1 の「最終更新+更新」)、`ViewStateBody` の `stale-message`(D1 の仕様の文言)・`error-actions`(O1 の「ダッシュボードを開く」)。`card` を渡すテンプレート(Dashboard・Detail・Form)では、stale アラートの下に 16px の余白を付ける(**UI の実測で 0px になる退行を修正**)。Detail・Form の stale の実寸は、実画面が揃うフェーズ 5〜7 で確認する(現状は単体で構造を固定)。
3. **D1**: 判定不能のタイルに「最後に確認できた状態(日時)」を出さない(API にコンポーネントごとの最終成功が無く、仕様に「取得できないときは省略」とあるため)。異常のタイルは `reason` によらず仕様 3.3 の固定の 1 文を出す(`reason` は診断用で、画面側に文言を分ける規定がない)。操作行(最終取得成功・スイッチ・更新)は、読み込み中・エラーでも出す(仕様 2 章と整合。モックの `d1-error`・`d1-loading`・`o1-error` は操作行が無い)。
4. **自動更新**: オフからオンに戻したとき、即時に 1 回再取得する(コード・UI レビューの指摘。停止中の古い「正常」を最大 30 秒現在値として見せるのは AF-18「結果が古いときも正常と断定しない」と緊張するため)。タブへの復帰は現状維持(E 5.4 の方針。`refetchIntervalInBackground: false`)。
5. **Vuetify 4.3.4 の実測**: `VSwitch` の `<input>` は `role="switch"` を持たない(明示した)。`VSwitch`・`VCheckbox` は、ネイティブの `<input>` が `opacity:0` のため `:focus-visible` の outline が描画されず、Vuetify の 12% の重ねしか見えない。**`global.css` で共通に直した**(`v-selection-control--focus-visible` を判定に、スイッチのトラック・チェックボックス/ラジオのボックスの周囲に `2px solid #0B57D0`、12% の重ねは `opacity: 0`)。`.v-field` を 14px・左右 12px(Vuetify 既定は 16px・16px)、`.v-btn[aria-disabled=true]` を無効ボタンと同じ見た目にした。Playwright は `aria-disabled="true"` のボタンを無効として扱うので、「何も起きない」の確認は `click({ force: true })`。
6. **`matrixModel` の安全網**: `nodes[]` に無いノード名のシャードがあれば末尾に行を足す(チップが黙って消えるのを避ける)。インデックスは補完しない(API が補完する)。
7. **仕様に記載がなく暫定で決めた扱い**: 未知の役割・状態のチップは中立の見た目で値をそのまま読み上げる(凡例には出さない)。状態が `null` のインデックスは「—」+隠した「状態を取得できません」。`truncated` の注記の「1,000」は固定値でなく `indices.length`。件数はすべて 3 桁区切り。red のアラートは未割り当てプライマリが 1 つ以上あることを条件にし、10 インデックスまで列挙(絞り込みの影響を受けない。stale 中も前回データから出す)。IME の `compositionend` は debounce(250ms)を待たず即適用。
8. **リサイズ時のフォーカス**(UI レビューの指摘): ウィンドウ幅の変更(`mobile` の切替)でドロワーが自動で閉じる場合は、フォーカスがドロワー内にあるときだけメニューのボタンへ戻す(操作していないのにリングが出ない)。Esc・スクリム・メニューのボタン・項目選択では従来どおり戻す。`mobile` の同期 watcher で「リサイズ由来」を判定する。
9. **favicon**: `index.html` にインライン SVG の data URI(サイドバーのロゴと同じ絵柄。外部要求を増やさない)。404 ページのブロックの見出しを「URL を確認してください」に(h1 の「ページが見つかりません」との二重表示を避ける。仕様はブロックの見出し文言を指定していない)。
10. **Playwright の時計**: D1 の E2E は `clock.install()`(一時停止しない)+ `fastForward` で駆動(`pauseAt` は TanStack Query の通知が `setTimeout(0)` を使うため使わない)。実時間も進むので、表示時刻は日付と分までを確かめる。次の定期更新のタイマーは直前の取得が終わってから作り直されるため、取得数の確認は `expect.poll` で待つ(フレーク解消)。
11. **補助ファイル**(F の一覧にないもの): `components/shard-matrix/{pageWindow,types}.ts`、`components/dashboard-parts/types.ts`、`features/opensearch/models/clusterNotices.ts`、`tests/support/resizeObserverStub.ts`。

## 7. レビュー結果

- コード・テスト(初回、`6cf23ba..0182323`): code-reviewer は Critical 0・Important 1(D1 の stale 時にアラートと概況バーの間隔が 0px)。test-reviewer は Critical 0・Important 5(red アラートの 10 件上限、red の絞り込み非依存、`isPaged` の境界、600px の境界、`e2eTest.ts` の `assertNone()` の組み込み)。変異 104 件のうち非等価の生存は 7 件。→ `0e9e744` で修正。
- 中間 UI レビュー(中間 1。専用 compose 環境+dev サーバー。実 API の異常系はコンテナの停止・復旧で確認): Critical 0・Important 1(スイッチ・チェックボックスのフォーカスリングが DS 2.6 を満たさない)・Suggestion 4。→ `91098e3` で修正。**再確認: 可**(新たな Critical・Important なし)。D1・O1・シェルは DS・モックにほぼ一致。全幅(1280〜320px)で横スクロール 0、コンソールエラーは favicon の 404 のみだったが解消。外部ドメインへの要求 0 件。

見送りの判断:

| 指摘 | 判断 |
| --- | --- |
| 異常タイルの文言を `reason` 別に差し替える案 | 見送り(仕様 3.3 は固定の 1 文) |
| stale 中の red アラートに「前回取得時の値」の旨を添える | 見送り(stale の warning アラートが必ず並び、全体が前回値であることはそこで伝わる) |
| `VInput` の空の `role="alert" aria-live="polite"`(O1 に 1 件) | 当面許容。フェーズ 5(フォーム・ダイアログ)で `role` の扱いを共通で決める |
| 404 ブロックの見出し「URL を確認してください」と説明文「URL が間違っているか…」が似た語で始まる | 任意。支障なし |
| `ResizeObserver loop completed with undelivered notifications`(dev サーバーのログに 5 件。ブラウザの無害な通知) | 見送り。必要ならフェーズ 3 の `useContainerWidth` を `requestAnimationFrame` 化 |
| `useViewState` の `idle` kind | 見送り(0005 のとおり。X1 で再確認) |

## 8. 後続フェーズへの申し送り(フェーズ 5 以降)

- **フェーズ 5**(S1・S2・DLG-1/2/5): ConfirmDialog の実ブラウザ E2E(初期フォーカス・focus trap・`persistent` の Esc・背面クリック・キャンセルで戻り先へ復帰)、`RowActions` のメニュー項目から開いたダイアログのフォーカス復帰先(`⋮` ボタン)、失敗時のダイアログ内アラートへのフォーカス移動、`lockRefusals`(`tests/support/apiErrors.ts`)・`describeError` の `resendSafe`/`outcomeUnknown`/`lockState`/`crawlerMessage` の使用(0005)。`VInput` の `role="alert"` の扱いを共通で決める。**Detail・Form テンプレートの stale アラートと次の要素の間隔(16px)を実画面で実測**。`VRadio` のフォーカスリングは未実測(使う画面が出たら確認)。
- **フェーズ 6**: `fieldMap` が `describeError` の `target:'field'` を再分類する(0005)。中間 UI レビュー 2(フォーム・確認ダイアログ・破壊的操作の警告)。
- **フェーズ 7**: 表の見出しの Space キーでの並べ替え(Vuetify 標準は Enter のみ)を再検討。`/jobs/%2e%2e` の Vue Router の復号を E2E で確認(FMOD-U-9)。
- **フェーズ 8**: X1 の `documents` クエリの `enabled:false`(ソース未選択)は `empty` になるため、画面側が先に判定する。
- **フェーズ 9**: ビルドサイズの最終測定(FMOD-U-11。現時点で JS 475.6KB・CSS 334.6KB 未圧縮)。D1 のレスポンシブ幅、同一オリジン以外の要求 0 件の対象画面を網羅表で確認。
- **フェーズ 10**: 実機のスクリーンリーダー(`role="alert"` の空要素を含む)、タブ非表示中の更新停止、IME 変換中の絞り込み、200% 拡大、Firefox・Safari、Nginx 越しの favicon・SPA の直開き、`opensearch-dashboards` タイルと外部リンクの関係(`DASHBOARDS_URL` だけ設定され `DASHBOARDS_HEALTH_URL` が未設定だとタイルは「未設定」だがサイドバーのリンクは出る。API 設計どおり)。
- **フェーズ 11(README)**: `npm run test` は `apps/web` で実行する前提。
- **設計書の追従改訂の申し送り候補**(別タスク): 上記 6 章の差異(O1 の `ViewStateBody` 2 重、`PageHeader.aside`・`stale-message`・`error-actions`、`VSwitch` の `role` 欠落とフォーカスリング、`.v-field` の 14px・12px、判定不能タイルの「最後に確認できた状態」を出さない理由、件数の 3 桁区切り、`matrixModel` の安全網、自動更新オン時の即時再取得、リサイズ時のフォーカス、favicon)。

## 9. 専用 compose 環境の後始末(0003 3 章)

- プロジェクト名 `loreley-adminview`、ホストポート 19200・18000・18090(すべて 127.0.0.1)、`CRAWLER_DOCUMENTS_DIR` は scratchpad の専用ディレクトリ、`LORELEY_CRON_TIMEZONE=Asia/Tokyo`、`LORELEY_API_DASHBOARDS_URL=http://localhost:5601`(上書きファイルは scratchpad。リポジトリには置かない)。起動前に、同名のコンテナ・ボリューム・ネットワークの不在とポートの空きを確認した。`docker compose config` の展開結果(全ポートが 127.0.0.1、`api` は非公開、ボリューム名 `loreley-adminview_*`)を確認してから起動した。最初の起動は OpenSearch の起動が遅く compose の待機がタイムアウトしたが、`healthy` になってから同じ引数で残りを起動した。
- UI レビューのためにコンテナ(crawler・indexer・opensearch)を一時的に停止・復旧した。api・web は止めていない。
- 後始末: 起動記録を確認し、`docker compose -p loreley-adminview ... down -v --remove-orphans`、dev サーバー(5173)の停止、テスト用文書ディレクトリの削除、このプロジェクトのイメージ(`loreley-adminview_{web,api,crawler,indexer}`)の削除を実施した。別プロジェクトのコンテナ・ボリューム・イメージ(`loreley-it_*`・`loreley-webcheck_*`・既存の停止中の `opensearch-opensearch-1` など)には触れていない。
- なお Docker VM のメモリは約 4.1GB で、専用環境の起動は可能だった(OpenSearch が約 0.9GiB)。

## 10. 未対応事項

- 上記 7・8 章のとおり。フェーズ 5〜12 は未着手(ユーザー指示により中断)。
- 設計書の追従改訂は Q2 のとおり別タスク(フェーズ 11 でまとめる)。

## 11. 次のアクション

- PR を作成し、ユーザーがレビューする。ここまでの振り返りを行い、フェーズ 5 以降の進め方を相談する(振り返りの結果で、プランの見直しが必要なら 0002・0003 を更新する作業記録を残す)。
