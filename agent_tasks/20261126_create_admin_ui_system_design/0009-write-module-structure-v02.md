# 0009 F(module-structure)v0.2 の作成(P5)

- 日付: 2026-11-26
- 実施: `document-writer` × 3(P5-1: 冒頭〜4 章、P5-2: 5〜8 章、P5-3: E v0.2 の 5〜7 章への整合)。メインエージェントが確認・修正
- 成果物: `docs/v0.x/system-design/ui-admin/frontend/ui-admin-frontend-module-structure-v0.2.md`(約 172KB)。v0.1(約 92KB)は未変更

## 構成

1〜8 章。v0.1 の章番号を保ち、4.3(EP-01〜14 と operationId・SDK 名・応答スキーマ・本文・query・`unavailable` の対応表)・8.9(前提タスクへの依存)を新設。冒頭に改訂履歴「v0.1 からの変更点」。

## 確認結果(メインエージェント)

- v0.1 の FMOD-K/P/U と I-n の全 ID が v0.2 にある(grep 照合。欠落なし)。新規: FMOD-P-34・35、FMOD-U-12・13、I-130〜138(I-139 は予備)
- 画面 × EP の対応は、実 OpenAPI の `paths` と B 1.3 に一致(P5-1 が確認)。生成 SDK 関数名・Query の名前・key で書き直し済み
- **E と F の食い違い 3 点を E 側に揃えた(P5-3)**: (1) 正規化は `interceptors.error`(Options ラッパーを廃止)、(2) パス値検証は `interceptors.request`(`isValidPathId` は画面側ガードと共有する純関数として残す)、(3) `baseUrl` は設定しない(生成物が `servers` から持つ)。FMOD-U-12 は E の FARC-U-22 に従う内容に整理
- 生成物の置き場 `src/admin/api/generated/`(F 3.3 の判断)を E 5.2・11.1 が採用。`.prettierignore` に `openapi/admin-v1.json` を追加(E 11.1 との整合。メインエージェントが修正)。F 8.1 の E 10〜12 の照合の記述を更新

## 判断・導出

- 生成物を `src/admin/api/` 直下ではなく `generated/` に置く(手書きの `client.ts` と生成の `client/`・`client.gen.ts` が紛らわしいため)
- tests に適用する R3 は「`fetch`・`XMLHttpRequest` の呼び出しと `@hey-api/*` の import の禁止のみ」と読む(`fetchStub.ts`・`mockApi.ts` との矛盾回避。導出。承認済みの方針を変える意図はない)
- 0004 X-BD1 の訂正: EP-11 の `ExtractFailedDocument`・`SummaryPendingDocument` の `document_id` も非 null(実 OpenAPI を正とする。F 8.1・I-130)
- `existingJob.ts`・`clusterValues.ts` を追加(J-E9・X-BD2 の置き場)

## 未対応・次にやること

- E 8 章以降(10〜12)との整合の残りは P7 のレビューで確認(F 8.7)
- 次: P6(A 9 章)、P7(`document-reviewer`)
