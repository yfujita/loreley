# 0008 E(architecture)v0.2 の作成(P4)

- 日付: 2026-11-26
- 実施: `document-writer` × 3(P4-1: 冒頭〜4 章、P4-2: 5〜7 章、P4-3: 8〜12 章)。メインエージェントが各回の後に確認・修正
- 成果物: `docs/v0.x/system-design/ui-admin/frontend/ui-admin-frontend-architecture-v0.2.md`(約 235KB、1,225 行)。v0.1(約 126KB)は未変更
- 入力: 0003・0004・0005・0006・0007(ゲート4)、v0.1 の E

## 構成(0006 の 4.1 の対応表どおり)

0〜12 章。v0.1 の章番号を保ち、3.6(`web` と `api` の関係)・12.7(実 OpenAPI との照合の要約と差分一覧)・12.8(前提タスク A・B+C と依存)を新設。冒頭に改訂履歴「v0.1 からの変更点」(変更表・新設表・事実の訂正・構成の変更)。

## 確認結果(メインエージェント)

- v0.1 の FARC-K/P/U と I-n の全 ID が v0.2 にある(grep 照合。差は `I-5`・`I-75` の 2 つだけで、v0.1 本文中の B 側の ID の引用であり E の ID ではない)。新規: FARC-P-40〜46、FARC-U-20〜24、I-122〜129(I-72・I-90・I-100・I-110 は参照の引用)・I-130〜138(F と共有の参照)
- ゲート4 の反映: FARC-K-4(確定・ユーザー指示)、FARC-P-2・3・4・6・19・20・21・30、新規 FARC-P-40〜46(P-42 は 0007 の 2 章の内容: `api` は publish しない、P-19 の転送先は `web` の公開ポート)、FARC-P-43 の書き込み EP は **EP-03〜08**(0006 の「EP-04〜08」は誤記。v0.1 の FARC-P-15・0004 S-N4 に合わせた)
- 事実の訂正を反映: EP-12・13・14 は最上位 `unavailable` を持たない(最上位を持つのは EP-02・10・11)、S-E1、`released=false`、`failed` フィルタ、`existing_job` の未知値 ほか(0006 の 1.4)
- 4.1 の起動順に `configureApiClient()` の 1 行を追記済み。E 5.3 の「追記は別途」の古い 1 文、4.5・改訂履歴のパス値検証の対象(`source_id`・`job_id` → パスに入れる値すべて)、0 章の「申し送りを持たない」(→ HO の番号は採番せず候補を 12.8 に一覧)を、メインエージェントが直した

## 判断・導出(承認済みの方針からの詳細。本文では「案」「導出」と明記)

API クライアントの初期化は `main.ts` で 1 回だけ(`interceptors` の二重登録を避ける)。正規化は `interceptors.error` に 1 つ登録し、Query 側は `error` を `unknown` として型ガード(FARC-P-44)。パス値検証は `interceptors.request` を最終防衛とし画面側のガードとは別(FARC-P-44・FMOD-P-4)。タイムアウトは自前の `AbortController`(`AbortSignal.any` を使わない。Safari 16.4 は推測)。`withKey`(TS2769 の回避)。`released=false` はダイアログ内の info アラート。S2 の `status=null` は S1 と同様。小数桁の判定は `Number(n.toFixed(2)) !== n`。`openapi/admin-v1.json` を format の対象外(推測・未検証)。

## 未対応・次にやること

- 12.8 の前提タスクの順序: B+C の `web` イメージのビルドは `apps/web` の最小の構成(`package.json`・`vite build`)があることが前提で、フロントの最初のスキャフォールドの後。dev サーバーは転送先の上書きで B+C 前でも着手可
- 未検証(FARC-U): FARC-U-20(`vite-plugin-vuetify` の Vite 8 明示対応なし)・21(Nginx 越しの `%2F`・`%2E`)・22(API クライアントの設定の実機確認)・23(EP-01 の反映遅れ)・24(`stalled=true` の経路)ほか
- 次: P6(A 9 章)、P7(`document-reviewer`)
