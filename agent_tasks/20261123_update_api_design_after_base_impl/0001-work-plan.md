# 0001 作業プラン: API 基盤の実装に合わせた api 設計書の追従改訂(HO-51)

タスク名: 20261123_update_api_design_after_base_impl
作成: planner が作成、メインエージェントが保存(2026-11-23)
状態: **ユーザー承認待ち**

## 0. ユーザー確認の記録(2026-11-23)

要件確認の「要確認」2 点に、ユーザーが次のとおり回答した。D の AAM-K-5 の出典は、この記録を参照する。

1. **AAM-P-23(アクセスログの分担。ゲート3で承認済みの案)**: 実装の方式で確定してよい。外側のアプリの middleware だけがサブアプリの処理後に 1 回ログを出し、サブアプリには `install_common_http(app, log_access=False)` を設置する。AAM-U-2 を確定に移し、AAM-P-23・BAPI-U-2・HO-48 を更新する。(HO-51 の「D の改訂時にユーザー確認を取る」に対する確認)
2. **改訂方法**: 既存の v0.1 を直接改訂し、各文書冒頭の改訂履歴に追記する(v0.2 は作らない)。

## 1. 目的とゴール

API 基盤(`apps/api`、PR #16 でマージ済み。コミット `c0b6e40`)の構成に、設計書 A・D(B・C は HO 範囲表記のみ)を合わせる。後続の Admin API 実装タスクが、設計書だけを読んで基盤に載せられるようにする。

受け入れ基準:

1. D・A の記述が、実装済みの構成(`health/`、`server` の汎用の口 `create_app(*, routers, mounts, debug_access_log_paths, lifespan)`・`SubAppMount`、`main` での組み立て)と一致している。HO-51 の内訳の各項目に反映先の節がある(P4 の突き合わせ表で確認)。
2. D に旧構成(`server/health.py`、`create_app(settings, admin_app)`、`server` が `admin` を import する記述)が残っていない。P5 の grep で確認し、ヒットが許されるのは冒頭の改訂履歴だけ。
3. AAM-U-2 が確定に移り、AAM-P-23・BAPI-U-2・HO-48 も更新済み。ユーザー確認の記録(本ファイル 0 節)があり、D の出典欄から参照している。
4. B・C・D の HO 範囲表記が「HO-1〜HO-51」。D 冒頭の関連 HO 番号も更新済み。
5. HO-51 の状態が「対応済み」(A 9.2.10)。
6. 基盤で未実装のものが「admin 実装時に追加するもの」として、D から一覧で読み取れる。
7. `apps/` のコードに変更がない(`git diff --stat c0b6e40 -- apps/` が空)。
8. document-reviewer のレビューと task-reviewer のタスクレビューで、Critical / Important が解消している。

## 2. 確定事項・前提

### 確定事項

0 節のとおり。

### 前提(planner が置いた仮定。承認時に確認)

- **P-a(D の書き方)**: D は admin 実装後の「あるべき構成」を示す設計書のままにする。基盤で実装済みの部分は実装の事実(名前・署名・配置)に合わせ、未実装の部分は「admin 実装時に追加」と明記する。D を「現在の実装の記述」に縮めない。
- **P-b(HO-51 にない差異)**: 実装済み部分の事実(例: `config.py` の入口は `load_settings()`・`Settings`・`ConfigError`、ログ設定は `configure_logging`)は実装に合わせる。admin 実装時の設計判断で承認済みの案のもの(例: AAM-P-14 の `ApiConfig`。許可表の `config` の行)は現案を残して「admin 実装時」と書く。承認済みの案の内容そのものを変える必要が出たら、その項目は改訂を止め、メインエージェントがユーザーに確認する。
- **P-c(ID の扱い。D の区分規則「`-K-` はユーザーの明示回答だけ」に従う)**:
  - AAM-K-5 を新設し、確定した方式を書く。出典は「ユーザー回答(2026-11-23)。本タスクの作業記録(0 節)」。
  - AAM-U-2 は行を消さず、区分を「確定(AAM-K-5 に移した)」にする。
  - AAM-P-23 は内容を新しい方式に改め、区分欄に「ゲート3で承認した分担を、ユーザー回答(2026-11-23)で逆にして確定した(AAM-K-5)」と書く。8.7 の行にも注記する。
- **P-d(BAPI-U-2 の分割)**: 基盤の実装で決まったのは `root_path` の扱い・例外ハンドラ・アクセスログの適用範囲だけ(AAM-K-5)。OpenAPI の `servers`・`paths` は未実装なので、BAPI-U-2 は「OpenAPI の `servers`・`paths`(admin 実装時)」に絞って未決に残し、決まった部分は AAM-K-5 を参照する。E の FARC-U-7 はこの未決に依存したままで、E は変更しない。A 10.1「確認していないこと」の `servers` の記述も残す。
- **P-e(節番号)**: D の既存の節番号は変えない(他文書が「D 4.x」で参照するため)。`health` は 4.2 に入れ、見出しを「4.2 `server`・`health`」にする。基盤の実装状況と admin 実装時の注意は、4章末尾に新節「4.12 基盤の実装状況と admin 実装時に追加するもの」として置く。
- **P-f(実装上の注意の置き場)**: 正本は D 4.12。A には、全 API 共通の規約の範囲が変わる 2 点だけ短く足し、D 4.12 を参照させる。
  - A 5.5: 想定外の例外を 500 にして再送出しない保証は、応答の開始前の例外に限る(`StreamingResponse`・`BackgroundTask` は対象外)。
  - A 5.4: サブアプリの OpenAPI は `create_admin_app(...).openapi()` で生成する。422 の宣言を除いて 400 を宣言する。サブアプリでは `openapi_url` などを明示する。
- **P-g(HO-51 の内訳本文)**: 内訳は経緯の記録なので旧構成の名前を残してよい。行の状態を「対応済み(本タスク名。2026-11-23)」にし、「D の改訂時にユーザー確認を取る」の後に「確認済み(2026-11-23)」と足す。
- **P-h(範囲外の同種の表記)**: E・F(`ui-admin/frontend/`)にも「HO-1〜HO-50」があるが、対象範囲外なので変更しない。HO-39 の状態(`tests/architecture` は一部実装済み)の見直しも範囲外。どちらも最終の作業記録の未対応事項に書く。
- **P-i(改訂履歴の日付)**: 更新日は 2026-11-23 とし、4 文書で揃える。

## 3. 影響範囲

変更するファイル(コードの変更なし):

- `docs/v0.x/system-design/api/admin/admin-api-module-structure-v0.1.md`(D): 冒頭、1章、2.1、3章、4.1、4.2、4.11、4.12(新設)、5.9、6章(R1・R3・R5・R9・R10・許可表)、7章(7.1・7.3・7.4)、8章(8.1・8.2・8.3・8.4・8.7)
- `docs/v0.x/system-design/api/api-base-design-v0.1.md`(A): 版・更新日・改訂履歴、5.4・5.5、7章の層、9.2 の HO-48・HO-51・内訳、10.3 の BAPI-P-18、10.4 の BAPI-U-2
- `docs/v0.x/system-design/api/admin/admin-api-architecture-v0.1.md`(C): HO 範囲、改訂履歴・更新日
- `docs/v0.x/system-design/api/admin/admin-api-v0.1.md`(B): 同上

事実確認に使う実装(読むだけ): `apps/api/src/loreley_api/`(`server/app.py`、`main.py`、`health/router.py`、`config.py`、`common/http/*`、`common/logging_setup.py`)、`apps/api/tests/`(`architecture/`、`server/`、`health/`、`common/test_logging_calls.py`)、`apps/api/README.md`、`agent_tasks/20261123_implement_api_base/`(0002・0004・0009)。

## 4. 実装フェーズ

### P1 事前準備(メインエージェント)

1. 比較基準 `c0b6e40` を記録し、対象 4 文書が未変更であることを確認する。
2. 0 節を、D の AAM-K-5 の出典から参照できるファイル名で確定する(本ファイル)。
3. `cd apps/api && uv run pytest` が通ることを確認する(前回は 310 passed)。
4. 旧構成の grep のベースライン(P5 のパターン)を取り、D でのヒット件数と行番号を作業記録に書く。

検証: SHA・テスト結果・ベースラインのヒット一覧が作業記録にある。

### P2 D の改訂(document-writer に依頼)

依存: P1。依頼には 0000・本プラン・A 9.2.10・D 全文・実装ファイルと、前提 P-a〜P-g、禁止事項(A・B・C・コード・agent_tasks への書き込み)、報告形式(変更節の一覧と HO-51 内訳の反映先)を含める。

改訂内容(章別):

1. 冒頭: 版の「実装はスコープ外」を、基盤が実装済み(PR #16)で admin が未実装であることに改める。HO 範囲は「HO-1〜HO-51」、関連 HO は grep で確定する。改訂履歴に追記する。
2. 1章: `server` の行を「汎用の口(外側のアプリ。機能パッケージを import しない)」に。`health` の行を追加。
3. 2.1: 図の `server --> adminEntry` を削除し、`main --> server`・`main --> health` を追加。注を `main` が `create_health_router()`・`create_admin_app(...)` を作り `create_app(routers=…, mounts=[SubAppMount("/api/admin/v1", …)])` に渡す、に改める。
4. 3章: ツリーに `health/` を追加。`server/` は `app.py`・`static_web.py`(admin 実装時)。README は作成済み(`apps/api/README.md`)。マウントは `main` が `mounts` に渡す。
5. 4.1: `server` の設定 dataclass を削除。起動順を `load_settings`・`configure_logging` に。手順5を `create_app(routers, mounts, debug_access_log_paths={HEALTH_PATH}, lifespan=…)` に。クライアントを閉じる処理は外側の `lifespan`(サブアプリの lifespan は実行されない)。`ApiConfig` への詰め替えは admin 実装時。
6. 4.2(見出し「`server`・`health`」): `server` の責務、入口 `create_app`・`SubAppMount`、依存は `common` だけ、`health`(`create_health_router()`・`HEALTH_PATH`)。「ログと例外ハンドラ」は AAM-K-5 の方式(テンプレートは `root_path` から `app_root_path` を除いた部分と `route.path`、`methods` を持たない route は `-`、Starlette の `scope` 共有への依存と `tests/server/test_mounts.py` での固定、入れ子マウント未検証、admin の factory で `install_common_http` を呼ばない)に置き換える。
7. 4.11: `ApiError(status_code, code, message, *, retryable=False, details=None)`、`error_response` の `headers` 引数(405 の `Allow`)、422 の項目名整形は `handlers.py` 内、`body.py` は admin 実装時。
8. 4.12(新設):
   - (a) 実装済みのもの
   - (b) admin 実装時に追加するもの: 本文上限 1 MiB(`body.py`)、厳密 JSON、422 の `exclusive` と Admin 固有 code、`BlockingRunner`、`/admin/` の静的配信と `WEB_DIST_DIR`、OpenAPI の書き出しと `OPENAPI_ENABLED`、`infrastructure`、OpenSearch・Crawler 関連の設定、R5 の外部ライブラリの所有者、R8 の `test_read_only_rules.py`、R9 の `Depends` の検査、許可表の admin の行と `config` の設定型 import
   - (c) 実装上の注意: サブアプリの lifespan、OpenAPI の生成元と 422、素の `FastAPI(...)` の `/openapi.json`(`test_http_rules` が `openapi_url` の明示を強制)、500 の保証の範囲、`ClientDisconnect`、孤立サロゲートのキー
9. 5.9: シーケンス図を `create_app(routers=[health], mounts=[SubAppMount(admin)], …, lifespan)` に。停止の注記は外側の lifespan。
10. 6章: R1(`main` が組み立て、`server` は `common` だけ)、R3(`server` は機能パッケージを import しない。機能追加は `main` と `FEATURE_PACKAGES`)、R5(`fastapi`・`starlette` の扱い)、R9(対象を `health/` に。`Depends` の検査は admin 実装時)、R10(`openapi_url` の明示)、許可表(`main` に `health`、`config` から `server` を外す、`server`・`health` は `common` だけ)。
11. 7章: 7.1 に `health/` を追加、`server/` は `test_app`・`test_mounts`・`dummy_features`。7.3 の 11・14・15 行と 7.4 を更新。
12. 8章: 8.1 に確認した事実を追加。8.2 に AAM-K-5 を新設。8.3 の AAM-P-2・P-3・P-17・P-23 を改め、P-14 の `server` の設定を外す。8.4 の AAM-U-2(確定)・U-6・U-9 を改める。8.7 の AAM-P-2・P-17・P-23 に注記。

検証(メイン): 報告の反映先を HO-51 内訳と 1 項目ずつ照合。mermaid 2 図のノード定義と参照を目視確認。

### P3 A・B・C の改訂(メインエージェントが直接)

依存: P2(AAM-K-5 の ID と D 4.12 の節番号)。

1. A: 版・更新日・改訂履歴。7章の層(エントリ → `server` と機能パッケージ → `infrastructure` → `common`)。10.3 の BAPI-P-18 を 7章に合わせる。5.4 の BAPI-U-2 参照を P-d に合わせ、5.4・5.5 に P-f の 2 点を追加。10.4 の BAPI-U-2 を OpenAPI の `servers`・`paths` に絞る。HO-48 を「AAM-U-1・U-3〜9。AAM-U-2 は確定(AAM-K-5)」に。HO-51 を「対応済み」にし、「確認済み(2026-11-23)」を追記。
2. B・C: 「HO-1〜HO-50」→「HO-1〜HO-51」、更新日・改訂履歴。

検証: 4 文書の更新日が揃っている。`grep -n "HO-1〜HO-5"` で `HO-50` が改訂履歴にしか残っていない。

### P4 実装との突き合わせ(メインエージェント)

依存: P2・P3。基盤について書いた D・A の記述ごとに、根拠(`path:line`)と一致・不一致の表を作業記録に残す。最低限: `create_app` の引数と `SubAppMount`、サブアプリへの `redirect_slashes=False`・`log_access=False`、`install_common_http` の署名と `_route_template`、`no-store` の判定、`HEALTH_PATH`・`main.build_app`・`uvicorn.run`、`Settings` のフィールド、`ApiError`・`error_response` の署名、`FEATURE_PACKAGES`・許可表・`EXTERNAL_LIBRARY_OWNERS`、`test_http_rules` の検査項目、tests の構成、A 5.5 の保証の範囲。不一致は D・A を直す(P-b。承認済みの案を変える必要があれば止めて報告)。

### P5 grep による旧構成の残存確認(メインエージェント)

依存: P4。対象 `docs/v0.x/system-design/api/`。P1 のベースラインと比較して記録する。

| パターン | 対象 | 期待 |
| --- | --- | --- |
| `server/health` | D | 改訂履歴以外 0 件 |
| `create_app\(settings` / `admin_app` | D | 同上 |
| `server --> adminEntry` | D | 0 件 |
| `server` が `admin` を import する記述(複数表記) | D | 0 件(文脈を読んで判断) |
| `server` の設定型 | D | 0 件 |
| `server` のマウント | D・A | 0 件(`main` に改める) |
| `tests/server/` 配下の healthz | D | 0 件 |
| 「本タスクでは作らない」「`apps/api/` は存在しない」 | D | 0 件 |
| `load_config` / `ApiConfig` | D | 「admin 実装時」と明記した箇所だけ |
| `HO-1〜HO-50` | B・C・D | 改訂履歴以外 0 件 |
| `AAM-U-2` | D・A | 全行が確定(AAM-K-5)を指す |
| `BAPI-U-2` | A・D | 絞った後の内容と矛盾しない |
| HO-51 の状態列 | A | 「対応済み」 |

あわせて `git diff --stat c0b6e40 -- apps/` が空であること。

## 5. レビューフェーズ

`document-reviewer` で行う(コード・テスト・UI の変更がないため、code-reviewer・test-reviewer・web-ui-reviewer は行わない)。

- 時期: P5 完了と作業記録作成の後
- 対象: A・B・C・D の 4 文書。比較基準 `c0b6e40`(`git diff c0b6e40 -- docs/v0.x/system-design/api/`)。依頼前に他タスクの変更が混ざっていないことを確認する
- 渡す文脈: 0000・本プラン、P4 の突き合わせ表と P5 の grep 結果、`apps/api/src`・`apps/api/tests`(読むだけ)
- 観点: HO-51 内訳の網羅、D 内部の矛盾(旧構成の残り・図と本文・許可表と R1〜R12)、実装との一致、ID の扱い(AAM-K-5・AAM-U-2・AAM-P-23・BAPI-U-2・HO-48)と区分凡例、節番号と他文書からの参照、要件外の追加がないこと

指摘対応: Critical / Important は該当文書を直す(D の大きな修正は document-writer、小さな修正はメイン)。直した後に P5 の grep を再実行し再レビュー。Suggestion / Nitpick は対応可否を作業記録に残す。承認済みの案の内容を変える指摘はユーザーに確認する。

## 6. タスクレビューフェーズ

実施する(`task-reviewer`)。理由: 実装フェーズが複数あり、承認済みの案(AAM-P-23)を変える判断と ID の扱い(P-c・P-d)を含むため。

- 時期: レビューフェーズ完了と作業記録作成の後
- 渡す文脈: `agent_tasks/20261123_update_api_design_after_base_impl/` 配下すべてと比較基準 `c0b6e40`
- 観点: 完了条件・プラン・作業記録・差分の整合、ユーザー確認の記録と AAM-K-5 の出典のつながり、範囲外事項(E・F の HO 表記、HO-39)が未対応事項に残っているか
- 指摘対応: Critical / Important は該当工程に戻して直し再レビュー。Suggestion / Nitpick は作業記録に残す

## 7. テスト方針

文書だけの変更。P1 で `uv run pytest` を通す、P4 の突き合わせ表、P5 の grep と `apps/` の差分なし確認、mermaid の目視、document-reviewer と task-reviewer。

## 8. リスクと対策

| リスク | 対策 |
| --- | --- |
| D(約 960 行)に旧構成が残り矛盾する | P5 のベースライン比較、レビュー観点 |
| D を現状実装に寄せすぎ、承認済みの案を消す | P-a・P-b を依頼に明示、4.12 で実装済みと未実装を分ける、P4 |
| ID・区分が凡例と食い違う | P-c・P-d で先に決める |
| 節番号変更による参照切れ | P-e(番号を変えない) |
| HO-51 にない差異が承認済みの案の変更に及ぶ | P-b: その項目で止めてユーザーに確認 |
| 手戻り | `git checkout c0b6e40 -- <4 文書>` で戻せる |

## 9. 範囲外で残すもの(最終の作業記録の未対応事項に書く)

- E・F の「HO-1〜HO-50」の表記
- HO-39 の状態の見直し
- BAPI-U-2 のうち OpenAPI の `servers`・`paths`(admin 実装時。E の FARC-U-7 と連動)

## 10. 承認時に確認してほしい前提

P-c(AAM-K-5 の新設)、P-d(BAPI-U-2 を絞って未決に残す)、P-f(実装上の注意の正本を D 4.12 に置き、A には 2 点だけ足す)。
