# 0010 A(api-base-design)9 章の HO 追加と状態更新(P6)

- 日付: 2026-11-26
- 実施: `document-writer`(P6)。メインエージェントが確認
- 変更ファイル: `docs/v0.x/system-design/api/api-base-design-v0.1.md` の 1 本のみ(`git diff --stat`: +69/-20)。版は上げない(HO-51 の前例)。B・C・D・E・F・DS・画面仕様・`apps/`・`deploy/` は未変更

## 変更した箇所(A)

- 冒頭の改訂履歴(8 行目の末尾に 1 項目)、7 行目の「HO-1〜HO-51」→「HO-1〜HO-68」(メインエージェントが追加で修正。9 章への参照文)
- 9.1 の注記(HO-52〜68 は本タスクが追加、既存 HO の状態を更新した旨。状態の語「対応済み」「一部対応」の説明)
- 9 章: 導入文、9.2.1〜9.2.10 の既存 HO、**9.2.11 新設(HO-52〜68)**、**9.4 新設(ゲート4 の確認事項 G4-1〜G4-7 と回答、G4-2 の影響)**
- A の 9 章以外の本文(2・5・8 章、BAPI-K・P・U など)は変えていない(追従改訂は HO-59 で申し送り)

## 追加した HO(HO-52〜68)

| HO | 内容 |
| --- | --- |
| 52 | 前提タスク A: `ttl_*` を任意かつ非 null に。`openapi_export.py` の docstring を FARC-P-6(コミットする)に。`ErrorBody.code` は列挙化しない |
| 53 | 前提タスク B+C(B): `apps/web/Dockerfile`・`nginx/default.conf`・compose の `web`。`web` イメージのビルドはフロントの最初のスキャフォールドの後 |
| 54 | G4-2: `api` の `ports` を外す、`web` を `127.0.0.1` のみ publish、`WEB_HOST_PORT` 新設、compose 冒頭の注意書き・README、HO-40・41 を `web` に適用 |
| 55 | 前提タスク B+C(C): EP-13 の `web` 判定を `HttpHealthCheck` に置換。`web_dist.py`・`LORELEY_API_WEB_DIST_DIR`・配線・テスト 11 ファイルの更新。B の公開前に必須 |
| 56 | IT の追従: `compose.test.yaml` が `api` を `127.0.0.1:8080` に publish。`/app/web` の mount・fixtures は不要 |
| 57 | dev プロキシの転送先は `web` の公開ポート(FARC-P-19) |
| 58 | Nginx の実装時確認(数値・`Host`・`%2F`・`%2E`・ヘルスチェック・CSP・`/` の扱い・`api` との結合) |
| 59 | A 本文の追従(2.1・2.2・2.3・3・4・8 章、BAPI-K-2・P-2・P-8・P-14・P-19・U-1、G3-16) |
| 60 | B の `web` 判定・配信の追従(8.1・10.2・11.7・11.9・I-72・AAPI-P-8)。前提 C の後 |
| 61 | B の `SourceSettings` 2 種類・EP-01・11 の null 許容・EP-12 の状態値 string |
| 62 | B の最上位 `unavailable` は EP-02・10・11 のみ。EP-12・13・14 は query を受けず 400 |
| 63 | B 2.4・2.12: 違反の 2 段階返却、`ttl` の `field` 固定、NaN |
| 64 | B の EP-10 `deletion`: `job_type` が読めないとき null、`fetched_at` の意味 |
| 65 | C・D の配信と `web` プローブの追従。前提 C の後 |
| 66 | admin-view 7.8・jobs 1.5(202 直後の「削除中」、`failed` フィルタ) |
| 67 | 画面仕様にない状態(S1 の `status=null`、DLG-4 の null、DLG-5 の `released=false`、`stalled` かつ `lease_expires_at=null`) |
| 68 | DS 10.1 の版の記述(Vue Router 5.5.1、jsdom 31・Node 下限、`vuetify/styles`・`sass`) |

## 状態を変えた既存 HO

HO-2(内容を逆に: `web`(Nginx)が配信。旧文は残す)、HO-34・35・43・44(compose で実装済み → 対応済み)、HO-36・37(`apps/web` の Dockerfile・compose への読み替え。HO-37 は FARC-U-11 解消)、HO-38(FARC-P-6 維持を確定)、HO-40・41(`api` は README 追記済み → 対応済み。`web` への適用は HO-54)、HO-42(Node の版・型生成の手順)、HO-45(一部対応)、HO-46(SDK 側は確認済み → 一部確認)、HO-47(解消した FARC-U を外し E 12.4・F 8.4 を正とする)、HO-48・49・24(追記)。根拠は 0004・0005・`compose.yaml` の読解(推測で状態を変えていない)。

## 確認結果・残り

- E・F が言及する HO-n と A の状態に矛盾なし(P6 が grep で照合)
- 範囲外のため直していない: B・C・D の「HO-1〜HO-51」(HO-65 で追従改訂の対象)、A 3 行目・27 行目の ID 体系の記述(A 3 行目・27 行目は 9 章の範囲外。内容の確認はレビュー(P7)に回す)
- 判断に迷った点(P6 の報告): HO-64 の B の節番号は未確認、HO-65 の C・D の節は grep(2026-11-26)による(網羅は改訂時に確認)、HO-45 は「一部対応」、HO-46 の Crawler 側は残す、B 2.3 は差がなく HO にしていない
