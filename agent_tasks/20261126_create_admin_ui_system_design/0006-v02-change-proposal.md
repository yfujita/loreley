# 0006 v0.2 の変更点一覧と前提タスク案(P3。ゲート4 への提案)

- 日付: 2026-11-26
- 入力: 0003(Nginx 配信の指示)、0004(照合・版確認)、0005(技術検証)
- 目的: v0.1 の承認済み方針(FARC-P / FMOD-P)のうち v0.2 で変えるものと、新規の判断(案)、前提タスクの切り方を一覧にし、ゲート4 でユーザー承認を取る。変更しない方針は「引き継ぐ」(ID・内容とも維持)
- 承認状況: **ユーザー承認待ち**(承認された内容は 0007 に記録する)

## 1. v0.1 の承認済み方針の変更点

### 1.1 ユーザー指示(0003)による変更

| ID | v0.1 | v0.2(案) | 理由 | 影響範囲 |
| --- | --- | --- | --- | --- |
| FARC-K-4・FMOD-K-4(確定)・BAPI-K-2・HO-2 | Web UI は `api` が静的配信する(同一オリジン) | **Web UI は `web` コンテナ(Nginx)が静的配信し、`/api/` を `api` へリバースプロキシする**(ブラウザから見て同一オリジン。CORS 不要は維持)。区分は「確定(ユーザー指示 2026-11-26。0003)」 | ユーザー指示 | E 3 章・4.1・5.3・12、F 1.1・2.1・6 章、A(BAPI-K-2・P-2・U-1・G3-16・HO-2・36・37 は HO で申し送り)、前提タスク B・C |
| FARC-P-2 | `app.frontend()` による配信・`/admin/` 配下だけ `index.html` フォールバック(`Accept: text/html` の GET/HEAD のみ) | Nginx の `try_files`。範囲は `/admin/` 配下。`assets/` の欠落は 404、それ以外の欠落ファイルは `index.html`(200)。`Accept` 判定はしない(Nginx は見ない)。`/admin` は 301、`/` は 302 `/admin/`(案) | 配信担当の変更。0005 で実機確認済み | E 3.2・3.3 |
| FARC-P-20 | Node 24 のビルドステージで `dist/` を `api` イメージへ | `web` イメージの Dockerfile(Node 24 でビルド → Nginx イメージに `COPY dist /usr/share/nginx/html/admin`)。`api` イメージは Web に依存しない | 同上 | E 3.5、前提タスク B(HO-36・37 の読み替え。ビルドコンテキストは `build: ../../apps/web` で解消) |
| FARC-P-19 | 開発プロキシ `/api` → `127.0.0.1:8080` | **維持**(`api` の `127.0.0.1:8080` publish を開発・IT 用に残す前提。G4-2) | — | E 3.4 |

### 1.2 実測・版確認による変更

| ID | v0.1 | v0.2(案) | 理由 | 影響範囲 |
| --- | --- | --- | --- | --- |
| FARC-P-30(構成要素)・FARC-P-4 | Vue Router 4(caret) | **Vue Router 5.5.1**(minor 固定 `~5.5`)。公式移行ガイドは非破壊で、P2-b で v0.1 の前提のコードが無改変で動いた | latest は 5.x で v4 は縮退していく(公式) | E 2.1・2.2 |
| FARC-P-3 | Node: 22.18 以上の 22 系・24 系・26 以上、推奨 24 | **下限を `^22.22.2 \|\| ^24.15.0 \|\| >=26` に引き上げる**(jsdom 30 以降を採るため)。推奨は 24 のまま、Docker・CI は 24。リポジトリに `.nvmrc`・`engines`・`engine-strict=true` を置く | jsdom 31 の engines。Node 25 は EOL で Vitest 5・Playwright の公式対象外 | E 2.1・3.5、F 2.4(`.nvmrc` の追加) |
| FARC-P-21 | Vitest + jsdom 第一案 | **jsdom 31 を採用**(上の Node 下限と連動)。FARC-U-9(jsdom で動くか・Browser Mode)は実装時確認のまま | 同上 | E 10.1 |
| FARC-P-4 | 固定範囲(exact/minor/`~6.0.x`/caret) | 具体化: Vuetify `4.3.4`・Hey API `0.99.0`・Playwright `1.65.1` exact、Vite `~8.3.8`・`vue-tsc ~3.3.14`・`typescript ~6.0.3`・Vue Router `~5.5`・`vite-plugin-vuetify 2.1.3`・`@vitejs/plugin-vue 6.0.11`、その他 caret+ロック。`sass`・`@mdi/js`・`@types/node ^24` は dependencies/devDependencies に明記 | P2-b の確認 | E 2.1・2.2 |
| FARC-P-6 | OpenAPI JSON と生成コードをコミットし CI で再生成差分を検査 | **維持(確定案)**。生成は決定的で 17 ファイル・約 114KB のためコミットで問題ない。生成物は lint/format の対象外。書き出しは `uv run python -m loreley_api.admin.openapi_export <出力>`(`openapi_export.py` の docstring の修正は前提タスク A) | P2-a の 5 | E 5.2 |

### 1.3 引き継ぐ(変更なし)

FARC-K-1・K-3・K-9、FARC-P-1・5・7〜14・16〜18・22〜26・28・29・31〜38(P-36 は S-D2 で拡張、P-27・39 は 1.4 の事実訂正)、FMOD-K-2・K-3、FMOD-P-1〜3・5〜13・15・16〜30(P-4・P-14・P-31・P-32・P-33 は 1.4)。

### 1.4 事実の訂正・拡張(方針ではなく、実装との照合で直す記述。承認は一括)

| 対象 | 内容(0004 の ID) |
| --- | --- |
| FARC-P-27・P-39・FMOD-P-14・P-33 | 単一応答の最上位 `unavailable` を持つのは EP-02・10・11 のみ(EP-12・13・14 は持たない)。D1・O1 は `unavailable` を引かない(J-E1) |
| FARC-P-36・FMOD-P-31 | S1 の `status`・`connector_type` の null と、`status=null` の行は「削除中」判定・操作を出さない(S-D2)。EP-11 の行ごとの `expectedFields`(X-BD1)。`cluster.status`・`shards[].role/state` は union+ガードで未知値は中立表示(X-BD2) |
| FMOD-P-12・`documentTabs` | EP-11 の `items`(4 型 `anyOf`)の絞り込み: 各 `documentTabs` 定義が行の型とアダプタを持ち、`DocumentsTable` は `tab` ごとの行型を受ける(X-ED1) |
| FARC-P-11(E 5.8・F 4.2) | **S-E1: EP-05 の 202 直後に S1 の行は「削除中」にならないことがある**。S2 のロック状態カードは即時 `held_delete` |
| FARC-P-13・E 6.4 | `invalid_request` で `details` なしは想定外(S-E4)。本文の違反は 2 段階で返る(S-D4)。`ttl_days` の `exclusive`/`required` は TTL 欄に写像(S-D5)。添字なし配列エラーは一覧の下、`connector_config` 単体は上部アラート(S-E3) |
| FARC-P-16・E 7.5 | `ttl_*` は null を送らずキーを省く(前提タスク A 完了前も後も)。フォーム用の型を自前で持つか A の後に再生成(S-D1) |
| FARC-P-34・15・E 5.10・6.5 | `stalled=true` かつ `lease_expires_at=null` は「期限を確認できません(期限切れ)」(J-E5)。EP-08 の `released=false` は成功文言にしない(J-E6) |
| FARC-P-35・E 6.3 | `existing_job` の `status`・`job_type` が null **または未知の値**のとき J2 へ導かない(J-E9) |
| FARC-P-11・E 5.7 | J1 の状態フィルタ `failed` にリース切れは含まれない(J-E7)。`deletion.fetched_at` は取得失敗時に取得時刻として出さない(J-E10)。EP-12・13・14 には query を付けない(X-BD4)。`/meta` はクエリなし |
| FMOD-P-4・FARC-U-18 | **パス値の送信前検証**: 生成 SDK は `.`・`..`・空文字を壊して別 EP へ送る(P2-a)ため、`.`・`..`・空・制御文字を拒否する(`source_id`・`job_id` とも) |
| FMOD-P-6・E 10.1 | `errorTable`(code は string)は B 2.3・A 5.2 から手書きを正本とし、OpenAPI の description と突き合わせる契約テストを案に(S-D7) |
| E 5.2・F 3.3 | `{Op}Response2`(スキーマ型を使う)、`infiniteQueryOptions: false`、`SourceSettings` が 2 種類(S-D3) |
| FARC-P-9・E 5.5 | 変更なし(J2 10 秒・D1 30 秒) |

## 2. 新規の判断(案。承認で「承認済みの案(ゲート4)」にする)

| ID(案) | 内容 | 根拠 |
| --- | --- | --- |
| FARC-P-40 | **Nginx の配信方針**: `/admin/` は `try_files $uri /admin/index.html`+`Cache-Control: no-cache`、`/admin/assets/` は `try_files $uri =404`+`public, max-age=31536000, immutable`、`/admin` は 301、`/` は 302 `/admin/`(Search View の置き場が決まるまで。BAPI-U-4)、`/api/` は `proxy_cache` なしで upstream の `Cache-Control` を素通し、`absolute_redirect off`、gzip。`add_header` は子 location に継承されないため location ごとに書く。数値(タイムアウト・上限・ヘッダ)の最終値は実装時確認 | 0005 の 2 章(実機確認) |
| FARC-P-41 | **`/api/` のプロキシ**: `set $api_upstream http://api:8080;`+`proxy_pass $api_upstream;`+`resolver 127.0.0.11`(`api` 未起動でも nginx が起動)。URI 部なしで元の URI を渡す。`proxy_read_timeout` は E 5.3 の書き込みタイムアウト(90 秒)以上(仮値 90s)、`proxy_connect_timeout` は数秒。`web` は `depends_on: api` の `service_healthy`。`web` のヘルスチェックの手段は実装時確認 | 0005 の 2.1・2.2、P1-3 C-3 |
| FARC-P-42 | **公開範囲**: `web` は `127.0.0.1` のみ publish(他のポートと重ならない値)。`/api/` を proxy するので `web` の公開範囲に認証なしの破壊的操作が出る(HO-40・41 の注意書きを `web` にも適用。compose 冒頭の「公開範囲」に追記は前提タスク B) | S-N6、P1-3 C-3 |
| FARC-P-43 | **Nginx 由来の失敗**: 502・503・504・413 は HTML のため `ApiError.kind='invalid_response'`。**読み取り**は 1 回だけ再試行しエラーブロック。**書き込み(EP-04〜08)の 502・504・`invalid_response`・通信断は結果不明**(再試行を出さず確認を促す。FARC-P-15 の拡張)。保存系(EP-03・04)は再送が安全の例外を維持 | S-N4、J-E3、X-ED6 |
| FARC-P-44 | **実行時エラーの正規化層**: 生成 `queryFn`/`mutationFn` は `throwOnError: true` で `ErrorResponse`・`string`(HTML)・`TypeError`・`Error` でない値を throw しうる。TanStack Query の `error` を `unknown` 扱いとし、型ガードで `ApiError` に正規化する(`interceptors.error` またはラッパー)。本文が JSON で `error.code` を持つかで JSON エラーと Nginx の HTML を区別 | P2-a の 2 |
| FARC-P-45 | **生成設定とビルド設定**: `@hey-api/client-fetch`・`typescript`・`sdk`・`@tanstack/vue-query`(`infiniteQueryOptions: false`)。`exactOptionalPropertyTypes` は有効にしない(生成コードが通らない)。`main.ts` で `import 'vuetify/styles'`、`sass` を dependencies に(`styles.configFile` 使用時に必須)、`vite.config.ts` を型検査するなら `@types/node ^24` と `types: ["node"]`、`build.target` は既定のまま。生成ディレクトリは lint/format 対象外 | P2-a・P2-b |
| FARC-P-46 | **DLG-4(再実行)の `force_delete`/`rewrite_mode` が null のとき**: null は「指定なし(false)」として送り、DLG-4 に「記録なし(なしとして実行)」と読み取り専用で表示する。破壊的な指定(`force_delete=true`)を推測で付けない | J-E8 |
| FMOD-P-34 | `admin/api` に実行時エラーの正規化(FARC-P-44)とパス値の検証(FMOD-P-4 の拡張)を置く。`shared/api` の `ApiError` に `invalid_response` の status を持たせる | E 5.3 の展開 |
| FMOD-P-35 | `.nvmrc`・`engines`・`.npmrc` の `engine-strict=true`・`Dockerfile`(web)・`nginx/default.conf` をルート直下の設定ファイル一覧に追加(名前のみ。内容は実装時) | F 2.4 |

## 3. 前提タスク案(本タスクでは起票しない。v0.2 と HO に一覧を書く)

| タスク | 内容 | フロント実装との関係 |
| --- | --- | --- |
| **A: OpenAPI の型の修正**(`apps/api` のみ) | `ttl_days`・`ttl_seconds` を「任意かつ非 null」に(S-D1)。`openapi_export.py` の docstring を FARC-P-6(コミットする)に合わせる(X-ED2)。任意: jobs の `sort` の enum、`warnings[].code` の型(J-O2・O4。推奨しない: `ErrorBody.code` の enum 化は 0017 の判断により行わない) | **型生成の前に必要**(フロント実装の着手前) |
| **B: `web` コンテナ(Nginx)の追加**(`apps/web` の Dockerfile・Nginx 設定・compose) | Node 24 でビルド → Nginx。Nginx 設定(FARC-P-40・41)。compose に `web` サービス(`127.0.0.1` publish、`depends_on: api`)。公開範囲の注意書き更新。`%2F`・`%2E` を含む `job_id` の素通しの実機確認 | 初回リリース前に必要(開発は Vite の dev サーバーと `/api` プロキシで開始できる) |
| **C: `api` の `web` プローブ置換と静的配信前提の撤去**(`apps/api`、IT) | EP-13 の `web` 判定を `HttpHealthCheck` で `web` の URL(`LORELEY_API_WEB_URL`)を確認する方式へ(案 (a))。`web_dist.py`・`LORELEY_API_WEB_DIST_DIR`・配線・README・Dockerfile のコメント・テスト 11 ファイル・IT の `compose.test.yaml`・fixtures を更新。B・C・D・A 本文の追従は HO | B と同時に完了していないと D1 の `web` が常に異常に見える。**B の公開前に必須** |

推奨: **2 本 = A と、B+C**(B と C は同じ `web` サービスの配線で、同時に直さないと D1 が壊れるため)。代替: 3 本に分ける(B と C を別々。C が単独でもテストできる)/ 1 本にまとめる(A の小さな修正が B・C に引きずられ型生成の着手が遅れる)。

## 4. v0.2 の章立てと v0.1 → v0.2 の節の対応(P4・P5 が並列で書くための固定)

v0.1 の章番号を保ち、節を足す。解消した FARC-U・FMOD-U は削除せず、状態欄に「解消(v0.2。根拠)」と書く。ID の欠番は残し、新規は続き番号(FARC-P-40〜、FARC-U-20〜、FMOD-P-34〜、FMOD-U-12〜。I-n は E が I-122〜129、F が I-130〜139。HO は HO-52〜)。

### 4.1 E(architecture-v0.2)

| v0.2 | v0.1 | 変更 |
| --- | --- | --- |
| 0 この文書について | 0 | 版・位置づけ・改訂履歴「v0.1 からの変更点」(本 0006 の 1・2 章と 0003 を要約)。v0.2 だけで実装を始められる旨 |
| 1 位置づけ | 1.1〜1.3 | `web` コンテナ・Nginx 前提に直す。1.3(Search View との境界)は `web` が将来 Search View も配信しうることを注記 |
| 2 技術スタックとバージョン固定 | 2.1〜2.4 | 版の表を 0004 の 4 章で更新(Vue Router 5・Node 下限・jsdom 31・`sass`・`@types/node`) |
| 3 ビルド・配信 | 3.1〜3.5 | 3.1 Vite 設定(`vuetify/styles`・`sass`・`@types/node`)、3.2 Router の `base`、**3.3 本番の配信を Nginx に書き換え**(FARC-P-40・41・42)、3.4 開発サーバー、3.5 Docker(`web` イメージ。前提タスク B への依存)、**3.6 新設: `web` と `api` の関係(compose 上の位置・公開範囲・起動順)** |
| 4 アプリ構成 | 4.1〜4.5 | 変更小(`web` の記述の整合のみ) |
| 5 データ取得層 | 5.1〜5.10 | 5.2 型生成(0005 の結果。コミット・lint 除外・`infiniteQueryOptions: false`・`Response2`・前提タスク A)、5.3 API クライアント(FARC-P-44・パス値検証・EP-12〜14 は query なし・Nginx のタイムアウト整合)、5.7・5.8・5.9(1.4 の訂正)、5.10 |
| 6 エラー処理 | 6.1〜6.7 | 6.3・6.4 の訂正(1.4)、**6.5 を Nginx 由来の失敗(FARC-P-43)に拡張** |
| 7 フォームと検証 | 7.1〜7.7 | 7.5 の `ttl_*`(1.4)、DLG-4 の null(FARC-P-46) |
| 8〜9 | 8・9.1・9.2 | 変更なし |
| 10 テスト方針 | 10.1〜10.3 | 10.1 jsdom 31・契約テスト(errorTable)・Node 要件、10.2 実 API の接続確認(前提タスク B+C 後の `web` 経由のスモーク)、10.3 |
| 11 静的解析・品質 | 11.1・11.2 | 生成物の除外・`exactOptionalPropertyTypes` を有効にしない・品質ゲートに「生成の再実行と差分ゼロ」 |
| 12 確認状況 | 12.1〜12.6 | 12.1 確認した事実(2026-11-26)、12.2 K(FARC-K-4 を更新)、12.3 P(40〜46 追加)、12.4 U(状態付き。新規 FARC-U-20〜: Nginx の実機確認の残り・`%2F` の素通し・`vite-plugin-vuetify` の Vite 8 明示対応なし 等)、12.5 I-n、12.6 引き継ぎ、**12.7 新設: 実 OpenAPI との照合の要約と差分一覧(0004 の 2 章)**、**12.8 新設: 前提タスク A・B・C と依存** |

### 4.2 F(module-structure-v0.2)

| v0.2 | v0.1 | 変更 |
| --- | --- | --- |
| 1 概要 | 1.1・1.2 | FMOD-K-4 を更新。モジュール表に変更なし(`admin/api` の責務に正規化・パス値検証を追記) |
| 2 構成 | 2.1〜2.4 | 2.4 に `.nvmrc`・`engines`・Dockerfile・`nginx/default.conf` を追加(FMOD-P-35) |
| 3 モジュール詳細 | 3.1〜3.9 | 3.3 `admin/api`(FMOD-P-34・パス値検証・`Response2` 回避・生成設定)、3.5 定義表(`expectedFields`・`documentTabs` の行型・EP-12〜14 の `unavailable` なし)、3.9 features(S1 の `status=null`・DLG-4 の null・O1 の API 並び利用) |
| 4 画面 → EP の対応 | 4.1・4.2 | **実 OpenAPI で照合済みの形に直す**(生成 SDK の関数名・Query の名前・EP-12〜14 の `unavailable` なし・S-E1 の訂正) |
| 5 主要シナリオ | 5.1〜5.5 | 5.1・5.3 の訂正(S-E1、`config_invalid`) |
| 6 依存ルール | — | 変更なし(生成コードの扱いのみ注記) |
| 7 テスト構成 | 7.1〜7.3 | 契約テスト(errorTable ↔ OpenAPI)の置き場 |
| 8 確認状況 | 8.1〜8.8 | 8.2 K(FMOD-K-4 を更新)、8.3 P(34・35 追加)、8.4 U(状態付き。新規 FMOD-U-12〜)、**8.9 新設: 前提タスクへの依存** |

## 5. FARC-U / FMOD-U の状態(v0.2 での扱い)

| ID | 状態 | 根拠 |
| --- | --- | --- |
| FARC-U-1 | 解消(ビルド・`styles.configFile`・`sass` を確認)。ただし `vite-plugin-vuetify` の Vite 8 明示対応は無し → FARC-U-20 として実装時に再確認 | 0005 |
| FARC-U-2・3・8・9・13・14・15・16・17・19 | 実装時確認/実装後/持ち越し(状態を維持) | — |
| FARC-U-4 | 解消(0005 の 2) | P2-a |
| FARC-U-5 | 解消(決定的・17 ファイル。コミット維持) | P2-a |
| FARC-U-6 | Nginx 版に読み替えて一部解消(設定案は実機確認済み。compose 結合は前提タスク B)。`%2F` の素通しは FARC-U-21 | 0005 |
| FARC-U-7 | 解消(`servers` 固定・`paths` 相対。Hey API が `servers` から `baseUrl` を作ることを確認) | 0004・0005 |
| FARC-U-10 | 解消(0004 の 4 章) | P2-c |
| FARC-U-11 | 解消(`web` が自前の Dockerfile を持つ。Node ベースイメージのタグ・ダイジェストは前提タスク B) | 0003 |
| FARC-U-12 | 本照合で完了。B の差は HO | 0004 |
| FARC-U-18 | SDK 側は確認済み(`.`・`..` は壊れる)。送信前検証で対処(FMOD-P-4) | P2-a |
| FMOD-U-2・3 | 解消(P2-a) | P2-a |
| FMOD-U-8 | 候補 (b)「`tests/integration/<名前>/`」が現実的に | 0004 |
| FMOD-U-1・4〜7・9〜11 | 状態を維持 | — |

## 6. ゲート4 の確認事項

| ID | 確認事項 | 推奨 |
| --- | --- | --- |
| G4-1 | 配信方式の変更と、1.1 の変更点(FARC-K-4・P-2・P-20)の反映。Nginx の方針(FARC-P-40〜42)を承認済みの案にする | 承認 |
| G4-2 | `api` のホスト publish(`127.0.0.1:8080`)を、開発(Vite の `/api` プロキシ)と IT のために残すか、`web` 経由に一本化するか | **残す**(IT の変更が不要。`web` と `api` の両方が `127.0.0.1` のみ) |
| G4-3 | 1.2 の変更点(Vue Router 5・Node 下限 `^22.22.2 \|\| ^24.15.0 \|\| >=26`・jsdom 31)。コミット方針は FARC-P-6 を維持 | 承認 |
| G4-4 | 前提タスクの切り方(A と B+C の 2 本)と、EP-13 の `web` 判定を `HttpHealthCheck` による HTTP 確認にする案 (a) | 承認 |
| G4-5 | Nginx 由来の失敗(FARC-P-43): 書き込みの 502・504 を結果不明扱い(フロントで対処)。1 MiB 超の 413 は `client_max_body_size` を `api` の上限より少し大きくして `api` の JSON 400 を出させる(Nginx 側の `error_page` で JSON を返す案は採らない) | 承認 |
| G4-6 | DLG-4 の null の扱い(FARC-P-46) | 承認 |
| G4-7 | 1.4 の事実の訂正・拡張と、2 章のその他の新規案(FARC-P-44・45、FMOD-P-34・35)を一括承認 | 一括承認 |
