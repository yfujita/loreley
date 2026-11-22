# 0005 フェーズ1: A(api 共通基本設計)と B 骨子(Admin API 仕様書)のドラフト

日付: 2026-11-22
担当: document-writer(メインが記録)

## 成果物(新規2文書。いずれもドラフト v0.1)

- `docs/v0.x/system-design/api/api-base-design-v0.1.md`(A。318 行。9章の申し送りは見出しのみ=フェーズ5で統合)
- `docs/v0.x/system-design/api/admin/admin-api-v0.1.md`(B 骨子。608 行。9・10章は次フェーズ。11章に確認状況・ゲート2確認事項 24 項目(11.7)・検算結果)
- 変更範囲の確認(メイン): `git status` で新規は上記2文書(`docs/v0.x/system-design/api/`)と `agent_tasks/20261122_create_admin_system_design/` のみ。SD・PD・apps・CLAUDE.md は無変更。

## 構成

- A: 0 この文書について / 1 位置づけ / 2 コンテナ・URL・公開範囲と安全性 / 3 技術スタック / 4 設定 / 5 共通 HTTP 規約(エラー形式、検証、OpenAPI・型生成・構成、Origin 検査、アクセスログ、タイムアウト)/ 6 ヘルスチェック / 7 構成の共通方針 / 8 compose への要求 / 9 申し送り(未統合)/ 10 確認状況
- B: エンドポイント EP-01〜15。1章に API 一覧、AF-1〜20 のトレーサビリティ、画面×EP 対応、画面データ項目の検算。2章に共通事項(ページング、部分失敗、Admin 固有 code、`details.errors`、`config_invalid` 分解、Crawler 写像、`lock_held` 409、単位変換、ロック状態)

## ID(区分)

- A(`BAPI-`): K-1〜8(確定=ユーザー回答・既承認文書の引用)、P-1〜3・5・12・13(承認済みの案。ゲート1)、P-4・6〜11・14〜19(案)、U-1〜8(未決)、I-60〜64
- B(`AAPI-`): K-1〜9、P-1・2・4〜10・23(承認済みの案)、P-3・11〜22(案。G2 含む)、U-1〜8、I-70〜72。事項1〜14 との対応表は B 11.6

## ゲート2確認事項(全 24 項目。B 11.7。案の値)

1 深いページ上限 `page×items_per_page ≤ 10,000`(超過 400)/ 2 既定の並び(J1 `-queued_at`、X1 各タブ日時降順、25/50/100)/ 3 エラー code 名(Admin 固有 15+共通 7)/ 4 `config_invalid` 分解仕様(最初の `: ` で分け前半が項目名パターンなら成功。分解不能は `errors` 空で上部アラート)/ 5 `lock_held` 409 の形(`options_applied=false`・`requested`・`existing_job`・`lock_state`)/ 6 登録文書数=検索インデックスの `source_id` 全文書 / 7 X1 一括検索上限 100 / 8 O1 件数上限 1,000+`truncated` / 9 D1 タイムアウト 3 秒、異常=接続拒否・名前解決失敗・2xx 以外、判定不能=タイムアウト等 / 10 `web` 判定=`WEB_DIST_DIR` の `index.html` / 11 D1 の環境変数名 / 12 `LORELEY_API_DASHBOARDS_URL` / 13 `LORELEY_API_CRON_TIMEZONE` / 14 OpenAPI `/api/admin/v1/openapi.json`・既定無効・`LORELEY_API_OPENAPI_ENABLED`・Swagger UI/ReDoc 常時無効 / 15 型生成 Hey API / 16 Admin API はサブアプリのマウント(代替 APIRouter)/ 17 Web UI `/admin/` 配下、フォールバックは `/admin/` 配下のみ / 18 単位変換は Admin API(`ttl_days` or `ttl_seconds`、`ratio_threshold_percent`)/ 19 再実行専用 EP `POST /jobs/{id}/rerun`、不可は 409 `job_not_rerunnable` / 20 取消の 409 `job_already_finished` は変換せず画面が成功扱い / 21 Crawler 呼び出し 接続 3 秒・応答 60 秒・自動再送なし、`crawler_unreachable`(503)・`crawler_response_lost`(504)/ 22 `connector_config` は不透明に中継、上限値は返さない / 23 **Origin 検査(writer の追加提案。要件外)** / 24 `apps/api`(`loreley_api`)・`apps/web`・コンテナ内 8080

writer が依頼範囲を超えて追加した案(要承認): #19 再実行 EP、#23 Origin 検査、#18 単位変換の受け方、#21 Crawler 起因 code、EP-15 `/meta`。
writer の解釈: ゲート1の「`/api/` 以外の未知パスは `index.html`」を「`/admin/` 配下の未知パスのみ」と読んだ(#17。ゲート1の文言と異なるため要確認)。

## 申し送り候補(フェーズ5で A の9章に HO-n として統合)

- SD(v0.9 想定): §7.3(`api`→`indexer` `/healthz` 許可。I-60)、§7.2(web 静的配信)、§7.5・§12.1 #5(Web UI 技術スタック)、§14.4(lock_held 冪等成功案の不採用。I-62)、§14.2(中継操作にソース削除ジョブ・設定登録更新が含まれない。I-20 関連)、§6.1・§6.2(Origin 許可リスト。案承認時。I-64)
- crawler-api: §4.7・CAPI-P-19(`/healthz` の位置づけ)、CAPI-U-1・U-3・U-5・U-10 の反映、`config_invalid` の `message` 形式依存(Crawler が項目別構造を返せば分解不要)
- indexer-api: §1・IA K67(`/healthz` は契約外)
- PD: 追記4点、§3・§4 の読み取り範囲(I-63)、§6.1 の README 明示
- 機能設計: AF-17 に O1 の絞り込み追記、AF-U-1・3・5・6・7・9・10・13 の解消反映、AF-5 は専用再実行 EP
- admin-view 10.4: `config_invalid` を案(a)に決定(I-71。推奨が (b) だったため)、取得設定の上限値・要約有効/無効は返さない
- 運用前提: cron TZ 一致(compose の共通変数)、受付途中の猶予 60 秒の同期、起動直後は「異常」に見える
- infra: compose に `api` サービス追加(127.0.0.1 publish、`crawler`・`indexer` を待たない、Node ビルドステージ)
- 実装時確認: Vuetify 4.3.4、`@mdi/js`、DS 10 章の TS7「動かない」→「公式未対応」
- 0000 のパス記載の差

## 自己検算(writer)と メインの確認

- writer: AF-1〜20 は B 1.2 で全件対応(AF-19 は専用 EP なし。409 `maintenance_enabled`+失敗理由表示)。D1・S1〜S4・J1・J2・X1・O1 の全項目を応答項目名に割当(「最終取得成功日時」はクライアント保持、S3・S4 の取得設定上限値は返さない)。Crawler 6 API はすべて EP が対応。ID 参照の未定義・未参照なしをスクリプトで確認。
- メイン: ファイルの存在・行数・変更範囲のみ確認。内容の精査は R1(document-reviewer)で行う。

## 未対応事項

- ゲート2(B 11.7 の 24 項目)のユーザー確認
- K の付け方(`-K-` は明示回答・既承認文書の引用のみ)の妥当性は R1 で確認
- B 本文(各 EP の全項目・全エラー・9章・10章)、C、D、E、F
