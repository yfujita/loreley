# 0012 ゲート5 の承認(2026-11-26)

- 日付: 2026-11-26
- 対象: P7 のレビュー(0011)で、区分(承認済みの案(ゲート4))が承認範囲より広いと指摘された事項。ユーザーが `AskUserQuestion` で回答

| ID | 確認事項 | 回答 |
| --- | --- | --- |
| G5-1 | E・F の執筆中に決めた設計の詳細(正規化は `interceptors.error` に 1 つ登録し request interceptor でパス値を検証(不正は合成した 400 `invalid_request`)、`main.ts` で `configureApiClient()` を 1 回呼ぶ、`baseUrl` は設定せず生成物の `servers` から持つ、タイムアウトは自前の `AbortController` 付き fetch(`AbortSignal.any` は使わない)、`withKey`、生成物の置き場 `src/admin/api/generated/`、S2 の `status=null` は S1 と同様に削除中判定・操作なし、書き込みの `invalid_response` は `status` を問わず結果不明)を承認するか | **承認**。区分は「承認済みの案(ゲート5。2026-11-26)」。実機確認の残り(FARC-U-22)は実装時確認 |
| G5-2 | 軽微な導出と誤記訂正(FARC-P-43 の書き込み EP は EP-03〜08(0006 の「EP-04〜08」は誤記)、EP-01 の反映遅れの注記、`last_completed_at`・`connector_type` は使わない、しきい値の小数桁判定は `Number(n.toFixed(2)) !== n`、O1 は API の並びをそのまま使う、`warnings` の `code` は型ガード、tests に適用する R3 は `fetch` の呼び出しと `@hey-api/*` の import 禁止だけに絞る)を追認するか | **追認**。区分は「承認済みの案(ゲート5。2026-11-26)」 |
| G5-3 | レビュー指摘への対応で新しく足した 3 つの設計案を承認するか: (1) `configureApiClient()` を冪等にする(2 回目以降は何もしない。単体テストに「2 回呼んでも二重にならない」を追加)、(2) 依存ルール R17 を追加(`admin/api` は `admin/` 内の他モジュールを import しない。`shared/api` と自分の `generated/` のみ可)、(3) R9・R16 の例外を削除し `admin/api/errors/` を直接 import せず公開口 `@/admin/api` に統一 | **3 つとも承認**(P7 の再レビュー後。2026-11-26)。区分は「承認済みの案(ゲート5。G5-3)」 |

この表は P6 と同様に A 9 章の 9.4 に転記する(P8)。G5-3 は P8 の最終修正で転記する。
