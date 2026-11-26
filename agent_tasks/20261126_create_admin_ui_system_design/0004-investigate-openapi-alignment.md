# 0004 既存設計と実 OpenAPI の照合(P1)・依存の版確認(P2-c)

- 日付: 2026-11-26
- 実施: `tech-advisor` × 4(P1-1・P1-2・P1-3・P2-c。いずれも読み取りのみ)。メインエージェントが統合
- 基準: ブランチ `feature/create-admin-ui-system-design`、基準 SHA `6a8b685f121616a5d3171df99f75eb4ebad3ed88`
- 照合対象の OpenAPI: `uv run python -m loreley_api.admin.openapi_export` で書き出し(OpenAPI 3.1.0、12 パス・14 EP、`servers=[{url:/api/admin/v1}]`、sha256 `ce60fc1a4d67071c805a3328ccbb2b3bdb327f4fd23e332df5d4a4f5b3f9bf51`)。同 SHA で再書き出し可能(出力は決定的: `sort_keys=True`・`indent=2`)
- 方針: API の正本は実装と OpenAPI(B と食い違えば実装が正)。0003 により静的配信は `web`(Nginx)に変わった
- 確認の限界: サーバー・Nginx・Hey API は起動・生成していない。実行時の挙動は、コード・テスト・実装記録(0017・0018・0021)・IT 記録(`docs/v0.x/test-results/admin-api-integration.md`)の読解による。IT で確認済みのものだけ「実機確認」と書く

担当別の ID 接頭辞: **S**=P1-1(データソース S1〜S4・EP-01〜05)、**J**=P1-2(クロール操作・ジョブ・ダッシュボード D1・J1・J2・EP-06〜10・13)、**X**=P1-3(ドキュメント X1・OpenSearch O1・シェル・EP-11・12・14、共通、配信撤去の影響)。

## 1. 結論

- EP-01〜14 のパス・メソッド・本文項目・応答の主要項目・HTTP ステータス・`code` は、B・E・F と実装・OpenAPI で**大筋一致**している(IT の AIT-10・11・12・20・31・41・50・51・60・90〜92 でも設計どおり)。E・F が実装で壊れる箇所はなく、v0.2 での追記・修正で足りる
- 差分は 4 種類: (1) 型の粒度(null 許容・列挙・`anyOf`)、(2) 事実の誤り(E・F の記述が実装と合わない)、(3) B と実装の差(B は改訂せず HO)、(4) **0003(Nginx 配信)に伴う影響**
- **最大の影響(0003)**: `api` の EP-13 は `web` を `WEB_DIST_DIR/index.html` が読めるかで判定する(`services/dashboard.py:93-94`、`infrastructure/probes/web_dist.py`)。`web` が別コンテナになると、何もしなければ全環境で `web=abnormal(missing)` となり、D1 が常に「異常あり」を示す。前提タスク C は「静的配信の撤去」ではなく **プローブの置換**を含む(`src` 6 ファイル・テスト 11 ファイル・IT の compose と fixtures に波及)
- `/healthz` は `dist/` に依存しない(影響なし)。`app.frontend()`・静的配信は `apps/api/src` に存在しない(未実装を確認)

## 2. 差分一覧

「扱い」: **v0.2**=v0.2 本文で直す/**HO**=A 9 章に申し送り(B・C・D・A 本文・画面仕様は改訂しない)/**前提**=前提タスク/**G4**=ゲート4 の確認事項。

### 2.1 前提タスクに関わるもの

| ID | 内容 | 根拠 | 扱い |
| --- | --- | --- | --- |
| S-D1 | `ttl_days`・`ttl_seconds` が OpenAPI で `integer\|null`(既定 null)。実行時は明示的な null を `type` で拒否(`schemas/sources.py:76-91`)。「どちらか一方が必須」も OpenAPI で表現されない。型生成すると `null` を送れる型になる | OpenAPI の `RegisterSourceBody`・`UpdateSourceBody` | **前提タスク A**。v0.2 は修正後に再生成する前提で書く。暫定は E 7.5 に「`toRequest` は null を送らずキーを省く。排他は画面側で保証」と明記 |
| X-ED2 | `openapi_export.py` の docstring(10-11 行)は「リポジトリにコミットしない」。E 5.2・FARC-P-6・HO-38 は「コミットする」。出力は決定的(`sort_keys`・`indent=2`)で差分検査に使える | `openapi_export.py:10-11,95-97` | **前提タスク A**(docstring)+コミット方針は **G4**(P2-a の生成の安定性・量で判断) |
| X-C1 / J-E2 | `web` プローブの置換(上記)。案 (a) `HttpHealthCheck` で `web` の URL(例 `LORELEY_API_WEB_URL`)を確認(推奨・`ComponentId`/`reason` の OpenAPI は不変)/(b) `web` を常に normal/(c) ボリューム共有(非推奨)/(d) D1 から `web` を外す(画面仕様・B・IT の変更が大きく不推奨) | 下記 2.4 | **前提タスク C**(案の選択は **G4**) |
| X-C1(影響範囲) | 撤去・変更: `probes/web_dist.py`・`probes/__init__.py`・`ports.py`(`WebDistCheck`)、`admin/dependencies.py`・`services/dashboard.py`・`admin/settings.py`・`config.py`・`main.py`・`openapi_export.py` の `web_dist_dir`/`web_probe` 配線、`LORELEY_API_WEB_DIST_DIR`(既定 `/app/web`)、`ComponentId` の docstring・B 8.1・10.2、README・`apps/api/Dockerfile:10` の古いコメント、`deploy/compose/README.md:10,109`・`compose.yaml:1,12,245` のコメント、テスト 11 ファイル、IT の `compose.test.yaml:56-59`・`fixtures/web/index.html`・`test_01_startup.py`・`test_90_component_failures.py` | P1-3 C-1 | **前提タスク C** |
| X-C2 | compose の `api` は `127.0.0.1:${API_HOST_PORT:-8080}:8080` で公開。**IT(`tests/integration/api/support.py:39`、`scripts/run-api-integration-test.sh`)が `127.0.0.1:8080` を直接呼ぶため、`api` の publish は IT のために残す必要がある**。`web` は `127.0.0.1` のみ・他と重ならないポート(8080・8000・8001・9200 以外) | P1-3 C-2・C-3 | **G4**(`api` の publish を開発・IT 用に残すか) |

### 2.2 型の粒度・事実の誤り(v0.2 で直す)

| ID | 内容 | 影響 ID | 扱い |
| --- | --- | --- | --- |
| S-D2 | EP-01 の `status`・`connector_type`、EP-02 の設定項目・`updated_at` が null 許容(保存値が読めないとき)。S1 で `status=null` の行の扱いが E・F にない | FARC-P-36・P-27、FMOD-P-31、E 5.9(b)、F 3.9 `sourceRow.ts`・`expectedFields` | v0.2: `expectedFields` に追加。`status=null` の行は「削除中」判定も操作も出さない案。HO: B 3.1 |
| S-D3 | `SourceSettings` が 2 種類: EP-02 は null 許容版(`SourceDetailResponse`)、EP-03・04 は厳格版(`SourceSettings`)。B 2.11 は共通と記載 | F 3.9 `fromSettings.ts`・`toRequest.ts` | v0.2: 生成型が 2 種類になることを F に明記。HO: B 2.11 |
| S-D4 / BD-5 | 本文の違反が 2 段階で返る(形 → 範囲・桁・排他)。EP-09 も依存関係ごとに最初の 1 群のみ。B 2.12「すべて返す」と不一致 | FARC-P-13・P-16、E 6.4 | v0.2: E 6.4 に注記(再送で別の違反が出うる。画面側検証が同じ規則を持つので通常は出ない)。HO: B 2.12 |
| S-D5 | `ttl_days`/`ttl_seconds` の排他・必須の `field` は両方 `ttl_days` 固定 | E 6.4、F 3.5 `fieldMap` | v0.2: `fieldMap` に明記。HO(軽微): B 2.4 |
| S-D6 | `connector_config` 内の NaN・Infinity は 400。B に記載なし | — | 対応不要。HO(軽微) |
| S-D7 / J-O5 / X-BD7 | `ErrorBody.code` は string(列挙なし。0017 の意図的な判断)、`details` は全キー任意。404・405・500 は OpenAPI に宣言なし。code は Admin 固有 14+共通 6(`invalid_request`・`not_found`・`method_not_allowed`・`http_error`・`internal_error`・`unavailable`) | FMOD-P-6 `errorTable`、E 10.1 | v0.2: `errorTable` は B 2.3 と A 5.2 から手書きを正本。OpenAPI の description との**契約テスト**を案に。列挙化は推奨しない(将来の code で型生成が壊れる) |
| S-E1 | **E 5.8・F 4.2「EP-05 の 202 直後に S1 の行が『削除中』になる」は誤り**。受付直後は設定 `status` が `active` のまま、`deleting` は削除ジョブ開始後。直後の S1 は変わらず `delete_job=null`。EP-02 の `lock.state` は即時 `held_delete` | AIT-60(IT 記録 85 行)、`source_catalog.py:241` | v0.2: 「S1 の行は変わらないことがある。S2 のロック状態カードは即時に `held_delete`」。スナックバーに `job_id` は維持 |
| S-E3 | `fieldMap` に添字なしの配列エラー(`connector_config.include_patterns`/`exclude_patterns` の 100 件超)と `connector_config` 自身のエラーが未記載 | F 3.5・3.9、E 6.4 | v0.2: 添字なし配列は一覧の下、`connector_config` 単体は上部アラート |
| S-E4 | `invalid_request` で `details` なし(本文が読めない・Content-Type 違い・1 MiB 超)が E 6.3 にない | FARC-P-13 | v0.2: 「`details.errors` がなければ想定外(上部アラート。診断に code と HTTP ステータス)」 |
| S-E5 | EP-01 は検索ベースで反映が遅れうる(EP-02 は ID 指定で即時)。登録直後の EP-01 に新規ソースが見えない例あり(最大遅延は未測定) | E 5.4・5.8 | v0.2 に注記。実装時確認 |
| S-E6 | `last_completed_at`・`connector_type`(EP-01)を使う画面仕様がない(B 1.4 は S1 が使うとする。AF-U-9 未決) | F 3.9 | v0.2: 使わないと明記(要件にない追加をしない)。HO |
| S-E7 | 小数桁の判定を `String(n)` で行うと極小値で指数表記になる | FARC-P-29 | v0.2: 一言追記(軽微) |
| J-E1 / X(B-2) | **E 5.9・5.7・FARC-P-27・39・FMOD-P-14・33 は単一応答の最上位 `unavailable` を EP-02・10・12・13・14 とするが、実装・OpenAPI で持つのは EP-02・10・11**。EP-12・13・14 は持たない | `topUnavailableReason`・`topCell` | v0.2: 適用対象を EP-02・10・11 に。D1・O1 は `unavailable` を引かない。HO: B 2.2 |
| J-E5 | J2 のリース切れ: `stalled=true` でも `lease_expires_at=null` になりうる(ロック文書がない・別ジョブ・期限が読めない)。E 5.9 の null の扱いは 409 の `existing_job` に限った説明 | FARC-P-34・24、FMOD-P-15・30 | v0.2: 「`stalled=true` かつ `lease_expires_at=null` は『期限を確認できません(期限切れ)』」(AAPI-U-9 は未検証=推測を含む) |
| J-E6 | DLG-5 で、ロック文書がない `stalled` ジョブでは EP-08 は 200 `released=false`・`failed_job_id=null`(ジョブは `running` のまま)。E 5.8 は 200 → スナックバーのみ | FARC-P-15・34 | v0.2: `released=false` は「解放するロックがありませんでした」とし成功文言にしない(実機未検証) |
| J-E7 | J1 の状態フィルタ: API の `status=failed` にリース切れは含まれない。「失敗(リース切れ)」の行は `active` でしか出ない | FARC-P-10・31 | v0.2: E 5.7 に注記。HO: 画面仕様 jobs 1.5 |
| J-E8 | DLG-4 で J2 の `force_delete`/`rewrite_mode`(`boolean\|null`)を「そのまま渡す」とあるが、EP-06 本文は null を受けない(400 `type`) | FARC-P-16・37、FMOD-P-32 | v0.2 で決める。案: null は「指定なし(false)」で送り、DLG-4 に「記録なし(なしとして実行)」を読み取り専用で表示(破壊的指定を推測で付けない)。**G4** |
| J-E9 / J-O9 | `lock_held`・`lock_in_use` の `existing_job` の `job_type`/`status`/`trigger` は OpenAPI で enum だが実装は Crawler の文字列を通す(未知値がありうる) | FARC-P-35 | v0.2: E 6.3 の「`status=null` なら J2 に導かない」を「null または未知の値」に広げる |
| J-E10 / J-B4 | `deletion.fetched_at`: 実装は `queued` 以外で、読み取り失敗時も「読もうとした時刻」を入れる | FARC-P-11 | v0.2: 失敗時は取得時刻として出さない。HO |
| J-O2 | EP-09 の `sort` は素の string(許容は `queued_at`・`-queued_at`)。`items_per_page` は enum 反映済み(0022) | FARC-P-10、FMOD-P-13 | v0.2: `jobsParams.ts` が union を持つ。任意で前提タスク A に enum 化 |
| J-O3 / X-BD6 / J-O1 | `page×items_per_page ≤ 10,000`、ID の pattern/maxLength は OpenAPI に出ない(実行時の 400) | FARC-P-10・16、FMOD-P-4 | v0.2: FE で守る(E 5.6 と一致)。ID は型で縛らず 400 を想定内 |
| J-O4 | `warnings[]` の要素が `{[k:string]: unknown}`(`code` が型に出ない) | FMOD-P-31 | v0.2: `catalogs/` に型ガード(`typeof code==='string'`) |
| J-O6・O7 | EP-07 の 200・202 は同一スキーマ(`status` は全 6 値)。`JobAccepted` の `job_type`/`status`/`trigger` は全列挙(EP-06 は実際は `crawl`/`queued`/`manual`) | FARC-P-14 | v0.2: 分岐は本文の `status`。絞り込みは FE |
| X-BD1・BD2・BD3 / X-ED1 | EP-11 の行は B が null と書く項目以外も null 可(skipped の `existence` のみ非 null)。EP-12 の `status`・`role`・`state` は enum でなく string。EP-11 の `items` は判別子のない 4 型の `anyOf` で、E・F に絞り込み方針がない | FARC-P-36、FMOD-P-12・`matrixModel`・`documentTabs` | v0.2: `documentTabs` の各定義に行の型とアダプタ(型ガード)を持たせ、`DocumentsTable` は `tab` ごとの行型を受ける。状態値は FE で union とガードを 1 か所に定義し未知値は中立表示。HO: B |
| X-BD4 | EP-12・13・14 は query を一切受けず、未知のクエリは 400 `unknown_field`(B 8.1・8.2 は「エラーなし」) | E 5.3 API クライアント | v0.2: クライアントは EP-12・13・14 に cache-busting 等の query を付けない。HO: B |
| X-ED5 | O1 の `matrixModel` の補完・並び(API が両方保証済み) | F 3.9 | v0.2: API の並びをそのまま使い補完は実装しない(二重実装を避ける) |
| X-ED3 / S-E2 / J-O8 | `servers=[{url:/api/admin/v1}]` 固定・`paths` 相対(確認済み)。Hey API が相対 `servers.url` を `baseUrl` にどう扱うかは未確認 | FARC-U-7、BAPI-U-2 | v0.2: E 5.2 の二択を確定に書き換え。`baseUrl` 設定は 1 か所に集約。生成側は P2-a で確認 |

### 2.3 B と実装の差(HO で申し送る。B は改訂しない)

J-B1(EP-13 の未知クエリは 400)、J-B3(`deletion` は `job_type` が読めないときも null)、J-B4(`deletion.fetched_at`)、J-B5/S-D4(違反の返し方)、S-D3(`SourceSettings`)、S-D5・S-D6、X-BD1〜BD7(上記)、X-BD8(HO-34・35・43・44 は compose 実装済み、HO-40・41 は `deploy/compose/README.md` に追記済み、HO-45 は実機確認が一部 → 状態更新)、J-B6(B 8.1 の `web` 判定・注記「`web` は compose のサービスではなく `api` が配信」は 0003 で逆になる。B 10.2・I-72・11.7 #10・AAPI-P-8 も)。

### 2.4 0003(Nginx 配信)の影響

| ID | 内容 | 扱い |
| --- | --- | --- |
| S-N1 | 配信が `api` から `web` に変わる(E 3.3・3.5・FARC-K-4・P-2・P-20・FMOD-K-4、B 8.1・11.9)。E 3.3 の「`Accept: text/html` の GET/HEAD だけフォールバック」は `app.frontend()` の挙動で、Nginx の `try_files` は Accept を見ない(`/api/` は別 location なので影響なし) | v0.2 で E 3 を書き直し |
| S-N2 / J-E4 / X-C3 | **タイムアウト**: Nginx の `proxy_read_timeout` 既定 60 秒(一般知識・未参照)。`api` の Crawler 待ちは接続 3 秒+応答 60 秒(設定上限 600)で書き込みは約 63 秒で JSON の 504 `crawler_response_lost`(`outcome_unknown=true`)。E 5.3 のクライアントは読み 45 秒・書き 90 秒。Nginx が先に切ると HTML の 504 が返り結果不明の JSON が届かない | Nginx への要求: `/api/` の `proxy_read_timeout` は **90 秒以上**(E 5.3 の書き込みと同等以上)、`proxy_connect_timeout` は数秒。値の確定は実装時確認。P2-b で確認 |
| S-N3 / X-C3 | 本文上限: `api` は 1 MiB 超を JSON の 400。Nginx 既定の `client_max_body_size` は 1m で超過は HTML の 413 | Nginx 側を `api` より大きく(例 2m)し判定を `api` に任せる |
| S-N4 / J-E3 / X-ED6 | Nginx 由来の 502・503・504・413 は HTML → `invalid_response`。**書き込み(EP-03〜08)の 502・504 は `api` が Crawler を呼んだ後かもしれない** | v0.2: 書き込みの `invalid_response`(status 502・504 等)は「結果不明」(FARC-P-15)、読み取りは再試行 1 回→エラーブロック。保存系(EP-03・04)は再送が安全の例外を維持。または Nginx の `error_page` で A 5.2 形式の JSON を返す案。**G4** |
| S-N5 / X-C3 | `/api/` は `proxy_cache` を使わず `Cache-Control: no-store`(`api` が `/api/` に付与)を素通し。`http`/`server` レベルに `add_header Cache-Control` を置かない(継承で重複)。`index.html` は再検証、`assets/` は長期キャッシュ | v0.2 の Nginx 方針 |
| S-N6 / X-C3 | 公開範囲: `/api/` を proxy すると `web` の公開範囲に認証なしの破壊的操作が出る。HO-40・41 の注意書きは `web` にも適用。`web` も `127.0.0.1` のみ | **G4**(`api` の publish を残すか) |
| X-C3 | プロキシ: **URI 部なしの `proxy_pass http://api:8080;`**(元の URI をそのまま渡す)。末尾 `/` や変数の使い方で `%2F`・`%2E`・`//` が正規化されると `job_id` のエンコード(B 2.12・FMOD-P-4)が崩れうる。静的な `proxy_pass` は起動時に名前解決するため `depends_on: api: service_healthy`(または `resolver 127.0.0.11`+変数)。SPA フォールバック: `assets/` は `try_files $uri =404`。`/admin`(末尾スラッシュなし)は明示的に 301(推測)。`/` は BAPI-U-4 に絡み未決。`web` のヘルスチェック手段(`curl`/`wget` の有無か専用 `/healthz`)も確認が要る | P2-b で確認(`nginx -t`・curl) |

### 2.5 確認済みで変わらないもの(参考)

ID のエンコードの API 側(`.`・`..`・`%2E`・`?`・`#` は 404 `job_not_found`、`%2F` は 404 `not_found`)、番兵日時(`0001-01-01T00:00:00.000Z` は 409 の `details.existing_job.lease_expires_at` に限る。EP-02・10 の `lease_expires_at` は読めなければ null)、404/409 の `details`、`lock_state` の実機確認値(`none`・`held_crawl`・`held_delete`・`orphan`)、`rerunnable`/`rerun_blocked_reason`、`lock_held` の `details` の形、画面 × EP の対応(B 1.3・F 4.1)、日時は `format` なしの string(UTC・ミリ秒・`Z`)、ページング(`window_limit`=10000)、`unavailable` は行ごとに常に存在(`{}`)。

## 3. FARC-U / FMOD-U / BAPI-U / AAPI-U の状態変化

| ID | 新しい状態 | 根拠 |
| --- | --- | --- |
| FARC-U-6 / BAPI-U-1(`app.frontend()` の細部) | **消滅**。後継は Nginx 設定の確認(`try_files`・欠落アセットの 404・`/admin` 末尾スラッシュ・キャッシュ) | 0003。`apps/api/src` に `frontend(`・`StaticFiles` なし |
| FARC-U-7 / BAPI-U-2 | **部分解消**(`servers` 固定・`paths` 相対は確認済み)。入れ子マウント・`FastAPI(root_path=…)` は未検証(Nginx がパスを変えなければ `root_path` 不要) | 0017・0018、IT 4.4 |
| FARC-U-11 / HO-37(ビルドコンテキスト) | **読み替え**: `web` 自身の Dockerfile(`build: ../../apps/web`)なら `apps/api` を文脈にする問題は消える | 0003 |
| FARC-U-18 / FMOD-U-2 | API 側は**確認済み**(AAPI-U-12・AAA-U-4)。**SDK 側のエンコードは P2-a で確認**。`source_id` は `[A-Za-z0-9._-]` の ASCII で `encodeURIComponent` で変わらないため、対象は実質 `job_id` | 0012・0018 |
| FARC-U-12 | 本照合が B と実装の再照合にあたる(差分は 2 章) | — |
| FARC-U-16(タイムアウトの実測) | **未測定のまま**。Nginx との整合要件が追加 | IT 4.4・6 |
| FARC-U-5 | 未確定。出力は決定的 | `openapi_export.py` |
| AAPI-U-11 | **確認済み**(接続拒否・名前解決失敗)。タイムアウト・HTTP エラーは未検証 | 0018、AIT-92 |
| AAPI-U-1 | 一部確認(停止中は `name_not_resolved`(IT)/`connection_refused`(ホスト))。起動直後・回復中は未検証 | AIT-90〜92 |
| AAPI-U-2 | 一部確認(AIT-11)。HO-11 は残る | — |
| AAPI-U-3 | 観測のみ(`indexer_unavailable`・`polling_aborted`・`skipped_by_ratio`・`deleted`)。API は未知コードを通すので E の「未知は一般文言」と整合 | — |
| AAPI-U-4・U-7 | 一部確認(単一ノード、AIT-32・41) | — |
| AAPI-U-5・U-8・U-9、AAA-U-7・U-10 | 未検証のまま(`stalled=true` の経路は推測のまま。J-E5・E6 はこれに依存) | IT 7 章 |
| AAPI-U-6 | compose の共通変数で担保。ずれた時は未検証 | IT 9 章 |
| AAPI-U-10 | API 側は実装済み。FE 側(E 7.6)は案のまま | — |
| FMOD-U-8(実 API スモークの置き場) | `tests/integration/api/` が実在するので、候補 (b)「`tests/integration/<名前>/` の慣習」が現実的 | — |
| BAPI-U-8 | 受け入れ済みのリスク。注意書きは `deploy/compose/README.md` に追記済み | — |
| 変化なし | FARC-U-1・2・3・4・8・9・10・13〜15・17・19、FMOD-U-1・3〜7・9〜11、BAPI-U-3・4・5・6・7 | — |

## 4. 依存の版・Node 要件(P2-c。確認日 2026-11-26)

出典は npm レジストリの package.json、公式ドキュメント、GitHub Releases・リポジトリの raw ファイル。重要な値は `npm view` と突き合わせて一致を確認。

| 項目 | v0.1 | 2026-11-26 | 要件 | 所見 |
| --- | --- | --- | --- | --- |
| Vue | `^3.5` | 3.5.46(3.6 は rc) | — | 差なし。Vue Router 5 の peer が `^3.5.34` |
| TypeScript | `~6.0.x` | **6.0.3**(6.1 なし)。`latest` は 7.0.2 | engines `>=16.20` | `~6.0.3`。TS 7 は安定 API を持たず Volar 系は 6.0 に留めると公式ブログが明言(`@typescript/typescript6`)。typescript-eslint の peer は `<6.1.0` |
| `vue-tsc` | 3.3.x | 3.3.14 | peer `typescript >=5.0.0` | peer は TS 7 を弾かないため TS 側を固定。TS 7 で動かす公式手順は未確認 |
| Vite | 8.3.x | 8.3.8 | `^20.19 \|\| >=22.12` | `~8.3.8`。既定 `build.target` は `baseline-widely-available`(chrome111・edge111・firefox114・safari16.4・ios16.4)で Vuetify 下限(Chromium 119/Firefox 128/Safari 16.4)より低く矛盾しない |
| `@vitejs/plugin-vue` | — | 6.0.11 | `^20.19 \|\| >=22.12` | Vite 8 公式対応 |
| Vuetify | 4.3.4 exact | **4.3.4 が latest**(2026-11-18) | 公開パッケージに engines なし | リポジトリ**ルート**の `engines.node >=24.11.1` は開発環境の要件(利用側ではない)。Node 下限は Vite・Vitest・Hey API・jsdom で決まる。対応ブラウザ(Chromium 119/Firefox 128/Safari 16.4)は公式 docs で裏取りできた |
| `vite-plugin-vuetify` | 2.1.x | 2.1.3(2.2 なし) | engines `^18 \|\| >=20`、peer `vite >=5` | CHANGELOG に「support vuetify 4」。**Vite 8/Rolldown の明示記述は見つからず**、FARC-U-1 は実機確認が必要 |
| `sass` | 推測 | 1.108.2 | `>=20.19` | caret |
| **Vue Router** | **4** | **5.5.1**(4.6.5 も保守) | peer `vue ^3.5.34 \|\| ^4` | **差あり**。公式移行ガイドは、ファイルベースルーティングを使わなければ破壊的変更なし。5 は依存が増える。推奨は 5 採用(判断は G4) |
| TanStack Vue Query | v5 | 5.108.4 | — | 差なし |
| Hey API | 0.99.0 exact | **0.99.0 が latest**(2026-06-22) | engines `>=22.18` | 差なし。`throwOnError` の既定は `false`(main ブランチのソースの `@default false`。0.99.0 タグは未確認)。fetch クライアントは本体に同梱。生成 `queryFn` が内部で throw するかは未確認 → P2-a |
| Vitest | 5.1.x | 5.1.2 | **`^22.12 \|\| ^24 \|\| >=26`** | Node 25 は範囲外 |
| jsdom | 案 | 31.0.1 | 30/31: **`^22.22.2 \|\| ^24.15.0 \|\| >=26`**(29: `^20.19 \|\| ^22.13 \|\| >=24`) | 最新を採ると Node 下限が上がる。happy-dom 21 は `>=20` |
| Playwright | 1.65.x exact | 1.65.1 | 公式 docs は 22/24/26 | Node 25 は対象外 |
| `@mdi/js` | caret | 7.4.47 | — | ライセンスの社内ポリシーは未確認(FARC-U-3) |

**Node の LTS(2026-11-26)**: 22=Maintenance(〜2027-04-30)、24=Maintenance(2026-10-20〜、〜2028-04-30)、25=EOL(2026-06-01)、26=Active LTS(2026-10-28〜、〜2029-04-30)。**ローカルの Node 25.2.1 は EOL・公式対象外**のため、P2-a・P2-b は Node 24 で実施する。

**方針変更の候補(G4 で承認を取る)**:
1. FARC-P-3(Node): 下限を jsdom 30 以降の採否で `^22.22.2 || ^24.15.0 || >=26` に上げるか、jsdom 29 / happy-dom で `22.18` を維持するか(FARC-P-21 が未確定の案なのでここで決める)。推奨 Node は 24 据え置き(26 への引き上げは CI で 26 を通した後)
2. Vue Router を 4 から 5.5.1 へ
3. FARC-P-4: TypeScript `~6.0.3`、`vue-tsc ~3.3.14`、Vite `~8.3.8`、Hey API `0.99.0`、Vuetify `4.3.4`、Playwright `1.65.1` で具体化(方針変更ではない)

Nginx 配信の観点(P2-c。公式): Vite は `base` 変更で HTML・CSS・JS のアセット URL を自動書き換え。古いチャンクが消えると動的 import が失敗するため HTML に `Cache-Control: no-cache`(または `vite:preloadError` で再読み込み)。Vue Router 公式の Nginx 例は `try_files $uri $uri/ /index.html`(サブフォルダでは読み替え)で、サーバーが 404 を返さなくなるためアプリ内に catch-all の 404 ルートが要る。

## 5. 未確認事項

- Hey API の生成物(`servers` → `baseUrl`、`throwOnError`、パスのエンコード、`ttl_*` の型、`SourceSettings` 2 種類、`warnings`・`ErrorBody.code` の生成型)→ P2-a
- Vite 8 + `vite-plugin-vuetify` + Vuetify 4.3.4 のビルド、`styles.configFile`、tree-shaking → P2-b
- Nginx の既定値(`proxy_read_timeout` 60 秒、`client_max_body_size` 1m)・URI 保持(`%2F`・`%2E`)・`/admin` 末尾スラッシュ・ヘルスチェック手段(P1-1・P1-2・P1-3 は公式未参照)→ P2-b
- `stalled=true` の経路、EP-09 の複数ページ、10,000 件の窓、複数ノードの `cat.*`、S1 の `status=null` が実データで出るか、EP-01 の反映遅れの最大値は IT でも未検証
- Vuetify の利用側の Node 要件の公式記述、`vue-tsc` を TS 7 で動かす公式手順、Firefox 128・Safari 16.4 の実機(FARC-U-15)

## 6. 次にやること

1. P2-a・P2-b の報告を受けて `0005-tech-verification.md` を作る
2. P3: 上記を変更点一覧・前提タスク案(0003 の再定義: A=OpenAPI の型・docstring、B=`web` コンテナ(Nginx)、C=`api` の `web` プローブ置換と静的配信前提の撤去。推奨は A と B+C の 2 本)にまとめ、ゲート4 でユーザー承認を取る
3. ゲート4 の確認事項: ①配信方式の変更(FARC-K-4・BAPI-K-2 を覆す)②方針変更(Node 下限・jsdom・Vue Router 5)③前提タスクの切り方とコミット方針 ④`web` プローブの置換案 ⑤`api` の publish を残すか ⑥Nginx 越しの失敗の扱い(書き込みの 502・504 を結果不明に含めるか/`error_page` で JSON か)⑦DLG-4 の null の扱い
