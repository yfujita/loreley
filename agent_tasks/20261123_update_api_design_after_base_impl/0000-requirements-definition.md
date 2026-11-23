# 20261123_update_api_design_after_base_impl

> 下書き(Claude が `20261123_implement_api_base` の申し送り HO-51 から作成)。内容を確認し、修正・確定してください。「要確認」の項目は、プラン作成前にユーザー判断が必要です。

## 背景・目的

API 基盤の実装タスク(`20261123_implement_api_base`。PR #16)で、`apps/api` の実装が設計書(`docs/v0.x/system-design/api/` 配下の D など)と異なる構成になった。ヘルスチェックを独立した機能パッケージ `health/` にし、`server` を機能パッケージに依存しない汎用の口にしたため。

差分は `docs/v0.x/system-design/api/api-base-design-v0.1.md` の 9章 HO-51 に申し送ってあり、**Admin API の実装の前に、設計書を実装に追従させる**ことが前提条件になっている。設計書を正として参照する後続タスクが、実装済みの構成と衝突しないようにするのが目的。

## 要件

### 現状(As-Is)

- 設計書 D(`admin/admin-api-module-structure-v0.1.md`)は、`server/health.py` に `/healthz` を置き、`server` が `admin` を import して `create_app(settings, admin_app)` で組み立てる構成を前提としている
- 実装は、`health/` パッケージ、`server` の汎用の入口 `create_app(*, routers, mounts, debug_access_log_paths, lifespan)`、`main` による組み立てになっている
- アクセスログの分担が、設計書(AAM-P-23。ゲート3で承認済みの案)と逆になっている(設計書: 外側はサブアプリ担当パスを除き、サブアプリ側が出す。実装: 外側だけが 1 回出し、サブアプリは `log_access=False`)
- 設計書の HO 範囲表記が、A は `HO-1〜HO-51`、B・D・`admin-api-architecture` は `HO-1〜HO-50` で食い違っている

### あるべき姿(To-Be)

- 設計書 D・A が、実装済みの `apps/api` の構成と一致している
- AAM-U-2(マウント下のアクセスログの方式)が「実装時確認」から確定に移り、BAPI-U-2・HO-48 の扱いも更新されている
- HO-51 が「対応済み」になっている
- 後続の Admin API 実装タスクが、設計書だけを読んで基盤に載せられる

### 具体的にやること

HO-51 の内訳(`api-base-design-v0.1.md` 9.2.10)に従う。

- **D の改訂(章別)**
  - 3章・4.2: `server/health.py` → `health/` パッケージ。`server` は汎用の口で、入口は `create_app(routers, mounts, …)`・`SubAppMount`。組み立ては `main`。`server` 専用の設定 dataclass(4.1)は作っていない。README は `apps/api/README.md` として存在する
  - 6章 R3・許可表: `server` は機能パッケージを import しない。`main` と `health` の行を足す。`starlette` の扱い
  - 6章 R9: ルート関数を `async def` にする対象の移動。`Depends` の検査は未実装(admin 実装時に足す)
  - 7.1・7.3: health のテストの配置(`tests/health/`)
  - D 全体の洗い出し: `server` が `admin` を import する記述、`server/health.py`、`create_app(settings, admin_app)` を grep して改める(少なくとも 2.1 の `server` の行・図・「import するのは `admin` の入口だけ」、4.1 手順5、5.9、6章 R1、8.3 の AAM-P-2・AAM-P-3、7.3)
  - 4.2「ログと例外ハンドラ」・8.3 AAM-P-23・8.4 AAM-U-2: AAM-U-2 の確定方式(外側が 1 回ログを出し、サブアプリは `log_access=False`。テンプレートは `root_path` から `app_root_path` を除いた部分と `route.path`。`methods` を持たない route は `-`)に合わせる
  - 4.11: `ApiError` の署名(`retryable`・`details` はキーワード専用)、`error_response` の `headers` 引数、422 の項目名整形は `handlers.py` 内
- **A の改訂**: 7章の層の記述に `server` と `health` を加える(2.1 は変更なし)。10.4 の BAPI-U-2 と HO-48 の AAM-U-2 の扱いを更新する
- **実装上の注意の反映**(admin 実装時の前提として、D・A のどこに置くかを決めて反映する): サブアプリの lifespan は実行されない、OpenAPI は `create_admin_app(...).openapi()` で生成する、OpenAPI の 422 を 400 に合わせる、想定外例外を 500 にして再送出しない保証の範囲(`StreamingResponse`・`BackgroundTask` は対象外)、`ClientDisconnect` の扱い、サブアプリを素の `FastAPI(...)` で作ると `/openapi.json` が既定で公開される
- **基盤が未実装のもの**(本文上限 1 MiB、厳密 JSON、422 の `exclusive`・Admin 固有 code、`BlockingRunner`、`/admin/` の静的配信、`OPENAPI_ENABLED`、`WEB_DIST_DIR`、OpenSearch・Crawler 関連の設定など)が、「admin 実装時に追加するもの」として設計書から読み取れるようにする
- **他文書の表記の統一**: B・D・`admin-api-architecture` の「HO-1〜HO-50」、D 冒頭の「本書に関わるものは HO-39」を HO-51 を含めて更新する
- HO-51 の状態を「対応済み」にする(`api-base-design-v0.1.md` 9.2.10)

## 対象範囲

- `docs/v0.x/system-design/api/api-base-design-v0.1.md`
- `docs/v0.x/system-design/api/admin/admin-api-module-structure-v0.1.md`(D)
- `docs/v0.x/system-design/api/admin/admin-api-architecture-v0.1.md`
- `docs/v0.x/system-design/api/admin/admin-api-v0.1.md`(B。HO 範囲表記のみ)

## スコープ外

- Admin API の実装(エンドポイント・DTO・OpenSearch / Crawler 接続など)
- `apps/api` のコードの変更(設計書を実装に合わせる方向のみ。実装を設計書に合わせて戻さない)
- SD・PD・crawler / indexer 設計・画面仕様など、api 以外の設計書の変更
- 純粋な ASGI middleware への置き換え(`StreamingResponse`・`BackgroundTask` を使う機能が入るときに別途検討)

## 制約・前提条件

- 実装(`apps/api`、PR #16 でマージ済み)が正。設計書を実装に追従させる
- **要確認(ユーザー判断)**: AAM-P-23 は承認済みの案(ゲート3)であり、アクセスログの分担を逆にする改訂になる。実装の方式で確定してよいか、ユーザー確認を取る(HO-51 に「D の改訂時にユーザー確認を取る」と記載済み)
- **要確認(ユーザー判断)**: 改訂の方法。(a) 既存の v0.1 を直接改訂し、冒頭の改訂履歴に追記する、(b) 新版(v0.2)のファイルを作る。プロジェクトの規約は「版番号が最大のファイルが最新」。HO-51 の追加は v0.1 への追記で行った前例がある
- 設計書の記述は、実装・テスト(`apps/api/src`・`tests/`)と突き合わせて事実確認する
- `docs/` の変更が中心のため、レビューは document-reviewer を使う想定

## 完了条件

- [ ] 設計書 D・A が、実装済みの `apps/api` の構成と一致している(HO-51 の内訳の各項目が反映されている)
- [ ] D に、旧構成(`server/health.py`、`create_app(settings, admin_app)`、`server` が `admin` を import する記述)が残っていない(grep で確認)
- [ ] AAM-U-2 が確定に移り、AAM-P-23・BAPI-U-2・HO-48 の記述が更新されている(AAM-P-23 の変更は、ユーザー確認の記録がある)
- [ ] HO の範囲表記と D 冒頭の HO 番号が揃っている
- [ ] HO-51 の状態が「対応済み」になっている
- [ ] document-reviewer のレビューで Critical・Important が解消されている

## 成果物

- 改訂した設計書(対象範囲に挙げたもの)

## 補足・参考情報

- 申し送り: `docs/v0.x/system-design/api/api-base-design-v0.1.md` 9.2.10 の HO-51 とその内訳
- 実装: `apps/api/`(PR #16)、実装時の判断は `agent_tasks/_archive/` 配下ではなく現時点では `agent_tasks/20261123_implement_api_base/`(0004〜0009。AAM-U-2 の確定は 0004、レビュー対応は 0006・0007・0009)
- 実装に対応するテスト: `apps/api/tests/server/test_mounts.py`(AAM-U-2 の方式を固定)、`tests/architecture/`(依存規則)
