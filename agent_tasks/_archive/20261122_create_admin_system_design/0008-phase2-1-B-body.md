# 0008 フェーズ2-1: B(Admin API 仕様書)本文の完成

日付: 2026-11-22
担当: document-writer(メインが記録)

## 変更ファイル

- `docs/v0.x/system-design/api/admin/admin-api-v0.1.md`(1272 行。骨子 610 行から増加)。A は変更なし。

## 内容

- 3〜8章: EP-01〜14 の本文(概要、リクエスト(型・必須・検証・既定)、応答(型・`null` 条件・出所)、エラー(HTTP・code・`details`・発生条件)、注意、JSON 例(15 個))
- 9章: Crawler 6 API の写像表(9.1 共通、9.2 API ごと)
- 10章: 失敗時の振る舞い(10.1 原則、10.2 障害別、10.3 画面別)
- 11章: 確認状況(11.7 ゲート2、11.8 検算、11.9 ゲート3で承認を取る案、11.10 C への引き継ぎ)
- 2章に 2.11(共通 DTO)・2.12(入力規約)を新設、2.2(`unavailable` のキー規則と理由コード 4 種)・2.9(`stalled` の補足)を追加、1.4 に J2 削除結果の「取得時刻」の行を追加

## 新規 ID(`-K-` は増やしていない)

- AAPI-P-24〜34(案。ゲート3で承認を取る): 入力規約、共通 DTO・`unavailable`、`GET /jobs` の未登録 `source_id` は空結果、`stalled` の補足(推測)、Crawler クライアント規約、J2 の `deletion` 読み取り規則、X1 補足、O1 値の正規化(`relocating` の `node` は移動元=推測)、障害別挙動、D1 の `reason` 値と `opensearch` 判定、設定項目が読めないとき `null`+`malformed`
- AAPI-P-16・17・18(部分失敗の表現、ロック状態 7 値、導出フラグ)はゲート2の一覧に行がなかったため「案(ゲート3で承認を取る)」と明記
- AAPI-U-9〜11(実行中でロック文書がないジョブの扱い、読めない設定項目の画面での扱い、opensearch-py 例外と D1 判定の対応・`relocating` の `node` の形)。U-4 に `cluster.health`・`cat.*` の項目名が実機未確認と追記
- I-73(crawler-api 4.1 の番兵値 `0001-01-01T00:00:00.000Z`)、I-74(画面仕様 dashboard の判定不能の理由「結果が古い」は Admin API からは返らない)

## E に影響する点(追加・明確化。承認済みの EP 番号・パス・code・項目名は不変)

- J2 に `deletion.fetched_at`、`stalled`・`rerunnable` は `null` になりうる(`stalled=null` なら `cancellable=false`、`rerunnable=null` なら画面は再実行を出さない)
- 部分失敗は `unavailable` に項目パスで入る(例 `deletion.current`、`tab_counts.skipped`、`document_count`、`existence`)。`items[]` の同名項目の全件に適用される規則は EP-01・09
- EP-03・04 の入力は `ttl_days` か `ttl_seconds` の一方、`ratio_threshold_percent` は小数第 2 位まで
- 本文の項目が不正なときの `details.errors[].reason`: `required`・`type`・`format`・`range`・`exclusive`・`unknown_field`・`unsupported`・`config_invalid`
- EP-08 の `lock_in_use` の `lock_state` は `unknown` になりうる。EP-13 の `reason` 値: `connection_refused`・`name_not_resolved`・`unexpected_status`・`missing`・`timeout`・`connection_error`。EP-09 の `status` には複合値 `active`
- 再実行は EP-06 を呼ぶ(`source_id`・`force_delete`・`rewrite_mode`)

## C への引き継ぎ(B 11.10)

導出ロジック(`lock_state` 7 値の判定順序、`stalled`、`cancellable`、`latest_for_source`、`rerunnable`、`registration.phase`、`last_crawl`、`last_completed_at`、`delete_job`、`existence`、十進数変換、`just_acquired` の猶予 60 秒の同期)/ データアクセス(最新ジョブ集計、ロック文書 `mget`、件数 `msearch`、`deletion_result-{job_id}`、`cat.*` の `h=`・`bytes=b`、窓 10,000 件、読み取り専用)/ 環境変数と仮値(Crawler 接続 3 秒・応答 60 秒、OpenSearch 10 秒・再試行 2 回、確認 3 秒、O1 上限 1,000、X1 一括 100)/ Crawler クライアント実装(urllib3、例外分類、`config_invalid` 分解)とスレッドプール対策 / 死活確認 / 部分失敗の理由コード・`malformed` 判定 / テスト観点

## A への修正提案(writer。軽微)

- A 5.2 の `reason` 共通値に B が Admin 固有の値(`config_invalid`)を追加できる旨の1文
- `unavailable` オブジェクトの正本は B 2.2 である旨の1文
→ R1 後の修正でまとめて A に反映する

## 申し送り候補の増減

- 追加: crawler-api 4.1 の番兵値の扱い、`config_invalid` の message 形式依存(Crawler が項目別構造を返せば分解不要)、Crawler の回復中は最大約 3 分接続拒否に見える(運用の注意)
- 減少: なし(Origin 関連は 0007 で除外済み)

## writer の自己検算

- エラー code の 2.3 と各 EP の一致(`crawler_*` 4 つは共通行で代表)、EP-01〜14 と見出しが 1:1、AF-1〜20 全件、画面データ項目の応答定義(不足 0)、ID 参照の未定義 0、JSON 例 15 個が解釈可能、不採用項目の残りは記録のみ
- 推測として明記したもの: OpenSearch 標準の項目名(実機未確認)、`relocating` の `node`、ロック文書がない実行中ジョブは `stalled=true`

## 次

- R1: A・B を document-reviewer でレビュー(Critical / Important 解消後に C へ)
- E 執筆中の writer に B 本文の追加点を伝達。E 完了後、R1 結果を待って F
