# 0032 R4 レビュー結果(6 文書+CLAUDE.md の横断整合)

日付: 2026-11-23
レビュアー: document-reviewer(メインが記録)

## 結論

Critical なし。Important 3 件、Suggestion 8 件、Nitpick 6 件。「軽微な修正で可」。A〜F の ID・EP 番号・code 名・環境変数名・タグ・章番号参照・HO 参照は一致。R2・R3 後の重点箇所も、実物(urllib3 2.8.0・anyio 4.16.0・infra・compose・apps)と矛盾なし。Important 3 件(文書の追記・修正のみ)を直せばゲート3に進んでよい。他文書は無変更(`git diff --stat 2cb500fa` は `CLAUDE.md` の 2 行追記のみ。未追跡は `agent_tasks/…`・`docs/v0.x/system-design/api/`・`docs/v0.x/system-design/ui-admin/frontend/`)。

## Important

1. **I-1 ゲート3表(A 9.3)が C・D の案の一部を対象にしていない**(A 383〜385 行の G3-21〜23): G3-21(C)・G3-22(D)は重点案のみ、G3-23「上記以外の案の一括承認」は A・B・E・F の ID だけで C・D を含まない。C 12.6・D 8.7 は「案はすべてゲート3で承認を取る」と書くが、AAA-P-6・7・9〜12・15〜17・20〜23・26〜29・31・32・34〜38、AAM-P-9・13・14・18・20・21・24・25 などがどの G3 行にも入っていない。B 11.9 の AAPI-P-35・36(ゲート1承認済みの区分訂正)も A 9.3 にない。提案: G3-23 に「C の AAA-P・D の AAM-P のうち G3-17〜22 に挙げた以外」を追記、「AAPI-P-35・36 はゲート1承認済みの区分訂正のみで判断不要」と注記
2. **I-2 FARC-K-8 を確定(`-K-`)にしている根拠が弱い**(E 684 行。対比 E 678 行の FARC-K-2 欠番理由): 出典は「0001(ユーザー確定)」だが 0001 の該当文は「確定した要件(requirements-clarifier 報告より)」ブロックの記述で個別のユーザー回答ではない。E は同じブロックを根拠に FARC-K-2 を欠番にし、BAPI-P-20 も同理由で降格済み。FARC-K-8 だけ K のまま。F の FMOD-K-2 末尾の「(コード・設定ファイルは作らない)」も同種。提案: FARC-K-8 を欠番にし FARC-P-n(承認済みの案。ゲート1。0003 で 0002 を承認)へ移す。または出典を 0000 のスコープ外(ユーザー記載)に限り「テストコード」の部分は案とする
3. **I-3 A 4 の `WEB_DIST_DIR` の注記が古く他文書と矛盾**(A 132 行): 「既定は C 7.2(案。イメージ内の固定パスは D・E で確定)」と書くが、C 7.2/AAA-P-43 が `/app/web` を決めており、HO-36・G3-16・E 3.5 もそれを前提にしている。D 8.5 の行「C 7.2: WEB_DIST_DIR の既定(D・E で確定)」は A の文言を誤って引いている。提案: A 132 行を「既定 `/app/web`(C 7.2。AAA-P-43。G3-16 で確認)」に直し、D 8.5 の該当行も合わせる

## Suggestion(8 件)

S-1 C 2.3(2)(87 行)が A 7 章にない語「Repository」を参照(「Reader(A 7章の読み取り専用の層。D)」に)/ S-2 D 2.1 の図が許可表と完全には一致しない(`routers/services/cmap → base`、`adminEntry → schemas/base/infra`、`config` の辺がない。注記は `common` の省略だけ。「`base`・`config` への辺も省略」と注記するか辺を足す。D 682 行の「R1〜R7 / R5・R6・R8 / R9・R10」の分類が重複しているので整理)/ S-3 D 4.1 の uvicorn 引数を「Crawler・Indexer と同じ」と書くが、実物の `apps/crawler/.../main.py` 309〜316 行は `lifespan="off"` と `timeout_graceful_shutdown` も指定し、D の停止方式(lifespan 終了でクローズ)は Indexer 型で Crawler の `close_clients` 型ではない(「ログ関連の 2 引数が同じ。停止は Indexer と同じ lifespan 方式」と限定、`timeout_graceful_shutdown` を決めるかも書く)/ S-4 E 12.4 の FARC-U-12(748 行)と E 12.6(821 行)で B の案 ID 範囲が食い違う(748 行に揃える)/ S-5 E 4.5 の「ID はクライアントで検証しない」と F 3.3 の例外(`.`・`..` だけの ID は取得せず見つかりません)が整合していない(E 4.5 に例外を 1 行)/ S-6 HO の「状態」の付け方が不統一(HO-34・37・38 は由来が案なのに「未対応」、HO-35・36 は「ゲート3待ち」。揃えるか 9.1 に「G3-23 一括承認の対象は未対応と表記」)/ S-7 A 9 の位置づけ文(A 359 行、244・248 行): E 12.3・F 8.3 を「ゲート3表」と呼ぶが実体は案(P)の ID 一覧。B 11.10・E 12.6・D 8.6 の引き継ぎ・修正依頼はタスク内部の事項で A 9 の申し送りに入らない(9.1 に一文)/ S-8 G3-2 の判断材料に PD §2 を加える(PD v0.19 §2 リスク表は「Admin View を保護しない」を許容する制約として載せ(145 行)、MCP の DNS rebinding は Origin 検証を MVP に含めるとする(153 行)。A 2.3 または G3-2 に引用)

## Nitpick

A 5.3 の「R1 I-1・R2 I-1」や A 134 行の「R2 I-7」のレビュー記号は D の依存ルール R1〜R12・F の R1〜R16・`I-n` と紛らわしい(「作業記録 0010/0027」と書くか削除)/ A 438〜441 行(10.3 の表)で BAPI-P-22〜24 が 20・21 より前 / HO-5 に SD §14.2 の「突合の起動」が MVP にない(crawler-architecture I-2)ことを 1 句 / A 3・7 に `anyio` の所有場所(D R5)の記述がない / A 5.6 のプローブ行「3 秒」は C 6.1 では接続 3 秒+読み取り 3 秒(最大約 6 秒。EP-13 全体は期限 4 秒)/ D 8.1 の「確認した事実(2026-11-22)」に R2 後の確認が混ざる

## 受け入れ基準 1〜10

1〜6・8・10 は充足(6 はゲート3待ち)、7 は一部(FARC-K-8 の区分=I-2、G3 の網羅=I-1)、9 は R4(本レビュー)が最終の文書レビューで Important 解消後に充足(task-reviewer は後続)

## 確認できた点(要旨)

EP-01〜14・code(Admin 固有 14+共通 6)・タグ 6 種・環境変数名・タイムアウトの仮値(10・2・3/60・3)・スレッドの上限(16・4・8)は A〜D で一致 / E 5.7 と F 4.1 は画面ごとの EP の組が完全一致、`PageBreadcrumbs`・`useViewState`・`externalLinks.ts`・`lockStateView`・`cellState`・`expectedFields`・R1〜R16 も整合 / ID 未定義参照 0・`I-n` 重複 0・章番号参照不在 0、表の列数不一致 0・フェンス偶数・mermaid 目視 OK / 欠番 ID は欠番説明・旧番号の注記以外で参照されていない / `job_id` の `quote(safe="")`+`.`→`%2E`、uvicorn の `log_config=None`・`access_log=False`、想定外例外の middleware 変換と `no-store`、`mget`・`_shards.failed`、`urllib3.exceptions` の範囲、`SSLError`・http 限定、`abandon_on_cancel`、`JobBrief` の導出表は A〜D で一致し実物で確認(urllib3 2.8.0、anyio 4.16.0、init-indices.sh、compose.yaml、Crawler の Dockerfile・設定、Indexer の設定)/ crawler-api・SD・機能設計・PD・IA の引用は正確 / `CLAUDE.md` は追記 2 行のみ

## 確認できなかった点

外部ライブラリの事実は 0004 に依存(FastAPI `app.frontend()`、Hey API 0.99、Vite 8・Vitest 5・Playwright、Vuetify 4.3.4)/ 実機でしか分からない事項(OpenSearch の応答形、実 uvicorn の `job_id` 特殊文字、Crawler 回復中)/ mermaid の描画 / B 3.3〜4.3・5.1・6・7 の本文は R1 済みとして再読せず

## ユーザー確認(ゲート3)

G3-1・G3-2(#19・#23 の不採用の解釈とブラウザ経由の書き込みのリスク受容)、G3-6・G3-4・G3-5・G3-8〜11(`.` の扱い、`ttl` の下限、`source_missing`、導線の変更など)。C・D の残りの案を G3-23 で一括承認とするか個別にするか。FARC-K-8 の降格(承認済みの案(ゲート1))でよいか。HO-50(0000 のパス記載の差)

## メインの対応方針

I-1〜I-3・S-1〜S-8・Nitpick を、フェーズ5の writer に依頼(設計判断が変わるものは対応せず報告)。FARC-K-8 は降格する。修正後に機械チェック → ゲート3

## 次

writer の修正 → ゲート3(ユーザー最終確認)→ フェーズ7(task-reviewer)
