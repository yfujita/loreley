# 0011 設計書レビュー(P7)

- 日付: 2026-11-26
- 実施: `document-reviewer` × 4(R-E1=E の冒頭〜7 章、R-E2=E の 8〜12 章、R-F=F 全体と A の差分、R-X=文書間の整合と事実確認)。E が約 235KB と大きいため、プランの 3 並列から E を前半・後半に分けて 4 並列にした
- 比較基準: 基準 SHA `6a8b685`。対象: E v0.2・F v0.2(新規)、A(9 章・冒頭・9.1・9.4)
- 実 OpenAPI(sha256 `ce60fc1a…bf51`)は 4 人とも一致を確認
- 結果: **Critical なし**。Important は重複を除き 10 件、Suggestion・Nitpick は多数。観点 1(正確性)・2(承認済み方針の保存)・6(スコープ)は大きな問題なし(以下「問題がなかった点」)

## 問題がなかった点(4 本の共通)

14 EP の対応表(operationId・SDK 名・応答スキーマ・本文・query・`unavailable`・null 許容・列挙・code)が実 OpenAPI と一致。v0.1 の FARC-K/P/U・FMOD-K/P/U・I-n の全 ID が内容を保って全件ある(欠落・すり替えなし)。変更は 0006・0007 の範囲内。E・F・A のどこにも「`api` が `/admin/` を静的配信する」「`api` を `127.0.0.1:8080` に publish」が現在の設計として残っていない(G4-2 が E 3.3〜3.6・12.8、F 2.1・8.9、A HO-53〜57 で一貫)。節番号・HO 番号・ID の相互参照は全件実在。A の差分は 9 章・冒頭・9.1・9.4 に限られ、HO の状態変更の根拠は `compose.yaml`・README・実装で確認できる。`git diff --stat 6a8b685` の変更は A と E・F v0.2・`agent_tasks/` のみ(`apps/`・`deploy/`・`tests/`・B・C・D・DS・画面仕様・v0.1 は未変更、`apps/web` なし)。

## 指摘(統合。対応方針つき)

| # | 重大度 | 箇所 | 内容 | 対応方針(P8) |
| --- | --- | --- | --- | --- |
| 1 | Important | E 66 行・12.8、F 27 行・8.9 | **前提タスク A の必要度が文書間で食い違う**(E 改訂履歴は「実装の着手と初回リリースの前に必要」、12.8 は「望ましい」、F は「完了後」、A の HO-52 は「必須ではない」、0006 は当初「必要」)。B+C を「実装着手前に必要」と読める記述もある | **A は型生成の前が望ましい(必須ではない。前でも `toRequest` が null を送らず進められる)**。**B+C は `apps/web` の最初のスキャフォールドの後に着手し、`web` 経由の接続確認と初回リリースの前に完了**。E 66 行・12.8(初回リリース行)・F 27 行・8.9 を揃える。12.8 の初回リリース行に A が要る理由がなければ「B+C の完了(A は望ましい)」 |
| 2 | Important | E 358・56 行、F 278 行 | **パス値検証の対象が「`.`・`..` を含む」と読める**(`my.source` のような正当な `source_id` を拒否する恐れ)。F 277 行は `.`・`..` を API が 404 で拒否と書くが、404 は `job_id`(`source_id` は 400) | 「**値全体が `.` または `..` に等しい、空、制御文字を 1 文字でも含む、文字列でない**」に統一(E 4.5・改訂履歴・5.3、F 3.3・2.1)。契約テストに `a.b`・`..a`・`a..` が通ることを追加。F の「404」は `job_id` に限定 |
| 3 | Important | E 586 行(5.7) | **EP-11 の行の非 null 項目が事実と違う**(「`existence` だけが非 null」)。実 OpenAPI では `SkippedDocument.existence`、`ExtractFailedDocument.document_id`、`SummaryPendingDocument.document_id`、各行の `unavailable` が非 null | E 12.7 と同じ文に揃える。正確な一覧は `expectedFields` の表に持たせる |
| 4 | Important | E 2.1(138 行)・12.1(3) | **「この版の組み合わせで `npm install`・`npm ci` が警告 0・audit 0」が 0005 の検証範囲を超えている**(Vitest 5・jsdom 31・Playwright・ESLint・Prettier・`@vue/test-utils`・Hey API と Vite 系の同時 install は未検証) | 範囲を「P2-b で install した版(Vite・Vuetify・vite-plugin-vuetify・plugin-vue・Vue Router・Vue・TypeScript・vue-tsc・sass・@mdi/js・@types/node)」に限定。依存全体の `npm ci`・`npm audit` は未確認で、FARC-U として 1 件足す(FARC-U-25) |
| 5 | Important | F 764・771・893 行(8.1・8.7) | **古い記述が残っている**(「E の 8 章以降は未照合・執筆中」「E 4.1 は未追記」)。E 4.1 には追記済み。契約テストの置き場・実 API 接続確認の置き場・除外パス・FARC-U-22 は E と一致を確認(R-F・R-X) | 8.1・8.7 を「E v0.2 全章と照合済み(2026-11-26)。E 4.1 は追記済み」に更新し、「未照合」の項を削除 |
| 6 | Important | F 721・727 行、2.1 | **`tests/integration/<名前>/` が `apps/web/tests/` かリポジトリ直下か読み取れない** | 「**リポジトリ直下の `tests/integration/<名前>/`(`apps/web/` の外)**」と明記。lint・R2/R3 の適用範囲も整理(`apps/web` の ESLint の対象外であることを書く)。E 10.2・F 6 章・7.1 を揃える |
| 7 | Important | F 631・624 行(5.2・5.1) | **`timeout` も「1 回だけ再試行」に見える**(E 5.4・6.5、F 3.4 は `timeout` を再試行しない。`invalid_response` は 502・503・504 のときだけ) | 「`timeout` は再試行せずエラーブロック、`network`・`retryable=true` の 5xx・`invalid_response`(502・503・504)は 1 回だけ再試行」に直す |
| 8 | Important | E 12.4(U-18・U-11・U-7) | **「解消」とした U に確認が残っている**。U-18 は v0.1 の「Crawler までの挙動」が残る(A の HO-46 は「一部確認。残り: Crawler の実 uvicorn と Nginx 越し」)。U-11 は Node ベースイメージのタグ・ダイジェストが前提タスク B に残る。U-7 は入れ子マウント・`root_path` が未検証で、Nginx がパスを変えないことが前提 | U-18=「一部解消(v0.2。0005: SDK 側確認済み)。残り: Crawler の実 uvicorn(AAPI-U-12・HO-46)・Nginx 越し(FARC-U-21)」、U-11=「一部解消。決める場所は前提タスク B」、U-7=「一部解消(`servers` 固定・`paths` 相対は確認済み。`root_path` 不要は Nginx がパスを変えないことが前提)」 |
| 9 | Important | E 12.8・7 行・12.5(I-80・I-122〜124) | **12.8 の HO 候補表が A の HO-52〜68 と突き合わされていない**(「番号は別途採番」)。C・D(HO-65)、DS(HO-68)、EP-10 `deletion`(HO-64)、dev プロキシ(HO-57)が候補表にない | 12.8 に「A の HO」列を足して HO-52〜68 と対応づけ、C・D・DS・`deletion` の行を足す。I-122・123 に HO-66、I-124 に HO-67、I-80 に HO-68(DS の版)を足す。7 行・12.8 の「採番せず」「別途採番」を「A 9.2.11 の HO-52〜68」に更新 |
| 10 | Important | E 12.3(FARC-P-1・7・25・26・29・44)、F 8.3(FMOD-P-5・11・34)、A HO-38 | **承認区分が承認範囲より広く見える**(0006 が承認したのは「正規化層を置く」「パス値を検証する」まで。方式の細部・導出が「承認済みの案(ゲート4)」に見える。P-1・25・26 は本文を変えたが区分に v0.2 の注記がない。HO-38 は「確定」と書いたが G4-3 は「承認」) | **G5-1・G5-2(0012)で細部と導出が追認されたので、区分を「承認済みの案(ゲート5。2026-11-26)」とする**(FARC-P-7 の `baseUrl` 不設定・request interceptor・自前 fetch、P-44、FMOD-P-34・5・11 の追記、S2 の `status=null`、R3 の tests 適用、S-E5・E6・E7・X-ED5・J-O4)。P-1・25・26 は「v0.2 の追記は導出(0004・0005)」と注記。HO-38 は「承認(G4-3)」に直す。F 3.3 の表見出しは `TimeoutError`・`AbortError` の行が「設計で未確認」と分かるように |
| 11 | Important | E 12.6〜12.8・A | **「前提タスク A・B・C」と文書 A・B・C・D の記号が衝突**(E 12.7 の「前提 A」「前提 C」は「前提タスク」の語が落ちている) | bare な「前提 A/C」を「前提タスク A/C」に統一し、12.8 に「前提タスク A・B・C は文書 A・B・C・D とは別」の注記を 1 行足す(記号の変更は行わない) |
| 12 | Important | A 3・4・27・249 行、HO-59 | **A 冒頭が 9 章の更新と食い違う**(27 行「HO-1〜51」「G3-1〜23」のまま、4 行の更新日、249 行「すべて未対応」と 257 行の対応済みの食い違い、0 章の「読み方」が 9.4 に触れない)。HO-59 の対象に A の 10 章(BAPI-K-2・U-1 の行)と 27 行がない | A の該当箇所を直す(冒頭・27 行・249 行・「読み方」・HO-59 に 10 章を追加)。HO-55 の `services/dashboard.py` は `admin/services/dashboard.py`、`ports.py` は `infrastructure/probes/ports.py`、HO-64 の B の節は 5.2(EP-10)に |
| 13 | Suggestion | E 451・55・61 行 | 「EP-12・13・14 だけが query を受けない」と読める。実装は定義にないクエリ名を EP を問わず 400 `unknown_field` にする | 「Admin API は定義にないクエリ名を EP を問わず 400 `unknown_field` にする。EP-12・13・14 は query を一切受けない。URL の名前(`size`・`source`・`q`・`state`)は API の名前に写してから渡す(5.6)」 |
| 14 | Suggestion | E 32・1061 行、F 157・766 行 | 生成物の量の数値が混在(114KB と 111KB) | 「`infiniteQueryOptions: false` で約 111KB・17 ファイル・約 4,260 行・約 286 行(vue-query)、既定は 114KB・375 行」に揃え、決定性は既定設定で確認した旨を U-5 に添える |
| 15 | Suggestion | E 49・616 行 | 最上位 `unavailable` の説明の揺れ | 「最上位が意味を持つのは EP-02・10・11。EP-01・09 の最上位は常に `{}`。EP-12・13・14 は持たない」に統一 |
| 16 | Suggestion | E 411〜414・595〜597 行(5.2・5.8) | EP-05・06 の 202 `JobAccepted` が表に出てこない | 5.2 の EP-05・06 行に「202 `JobAccepted`(スナックバーの `job_id` と J2 への遷移に使う。`status`・`job_type` を前提にした分岐はしない)」を追記 |
| 17 | Suggestion | F 197・236・736 行 | `configureApiClient()` の「2 回呼ばない」が規約だけで、テスト項目が曖昧 | 関数を冪等にする(2 回目は何もしない)案に直し、単体テストの項目を「2 回呼んでも interceptor が二重に登録されない」に |
| 18 | Suggestion | F 682・689 行(R9・R16) | `admin/api/errors/` を直接 import させている(公開口との二重化) | 例外を削除し `@/admin/api` 経由に統一 |
| 19 | Suggestion | F 6 章 R5 | `admin/api` が他の `admin/*` を import しない規則がない(循環の防止) | 「`admin/api` は `admin/` 内の他モジュールを import しない(`shared/api` のみ可)」を R に追加 |
| 20 | Suggestion | F 807 行(FMOD-P-18) | tests への R3 の適用範囲が 670 行と食い違う | 807 行を 670 行の表現に揃える(導出。G5-2 で追認) |
| 21 | Suggestion | F 7 行 | 「A を変更しない」が 9 章の変更と食い違う | 「A は 9 章(HO の追記・状態更新)と冒頭を除き変更しない」 |
| 22 | Suggestion | F 726・843 行、E 873 行 | jsdom の相対 `baseUrl`: E は「setup で絶対 `baseUrl` を設定」、F は `client.ts` にテスト用の形を持たせる。E 873 行の論理が逆転(「失敗する。そのため jsdom」) | 「Node 単体では失敗する。jsdom で解決するかは未確認(FARC-U-9。FMOD-U-6・U-12 と合わせる)。解決しなければ setup で `client.setConfig({ baseUrl: 絶対 URL })`」に統一し、F は E に揃える(`client.ts` に持たせない) |
| 23 | Suggestion | F 236 行、E 5.3 | E2E の setup でも `configureApiClient()` は不要(実アプリが呼ぶ) | 「単体テストの setup」に限定 |
| 24 | Suggestion | E 2.2・3.5、F 2.4 | Docker・CI の Node は `engine-strict=true` のため 24.15.0 以上が必要 | 「24.15.0 以上の 24 系」と書く |
| 25 | Suggestion | E 10.2(905 行)、F 7.1(727 行) | 実 API 接続確認の期待値と固定ポート。期待値(`GET …/jobs/a%2Fb` → 404 `not_found`、`…/%2E` → 404 `job_not_found`)、固定ポートは 9200・8000・8001・8080(+`WEB_HOST_PORT`) | 追記 |
| 26 | Suggestion | E 12.1 | 「確認していないこと」の一部(Docker マルチステージ化、EP-09 の複数ページ・10,000 件の窓、S1 の `status=null` が実データで出るか、`isLoading`)に ID も対応先もない | 12.4 に FARC-U-26 として 1 件にまとめるか、対応先(前提タスク B・HO-48)を明記 |
| 27 | Suggestion | E 12.6 | v0.1 の「B・C の確定に依存する箇所」の個別項目(`just_acquired`・`unknown`、AAPI-U-3、AAPI-P-20、`operationId` が生成名に直結)が消えた | 12.6 に 1〜2 行ずつ残す(例: `operationId` の変更は 11.2 の生成差分ゼロ検査で検出) |
| 28 | Suggestion | E 4.5・1077 行 | 相互参照のミス(パス値の検証は 5.3、FARC-U-21 の参照は 3.3・5.3) | 直す |
| 29 | Suggestion | E 5.7(569 行)・F 479 行 | S2 の `status=null` の区分が E は案、F は承認済み | G5-1 で承認されたので両方「承認済みの案(ゲート5)」 |
| 30 | Nitpick | E 244・245・259 行 | Nginx の既定 60 秒・1m、Vite の 5173 を確認済みのように書いている(0004 は「一般知識・未参照」、0005 は 1m を明示して検証) | 「Nginx の既定は公式ドキュメント上 60 秒(本タスクでは未測定)」「`client_max_body_size 1m` を明示した検証で +1 バイトが 413」「5173 は Vite の既定」 |
| 31 | Nitpick | E 646・1149 行、F 782 行 | 「0017」「0001 Q2」が本タスクの作業記録と区別できない | 「`implement_admin_api` の 0017」「`create_admin_system_design`(前タスク)の 0001 Q2」と書く |
| 32 | Nitpick | E 491 行 | OpenSearch のタイムアウトが A 5.6 と合わない(「10 秒×最大 3 回」) | 「接続 10 秒+読み取り 10 秒、再試行 2 回」 |
| 33 | Nitpick | F 823 行(FMOD-P-34)、F 277 行、E 5.3、E 820 行、E U-20 の文、E 13 行(U-21 の決める場所)、E 1224〜1225 行 | 太字の閉じ忘れ、「`AbortError` を除き」の補足、8 章の「(v0.1 から変更なし)」→「追記のみ」、U-20 の「何の版を調整するか」(`vite-plugin-vuetify` の版)、U-21 に HO-58、末尾の空行 | 直す |
| 34 | Nitpick | E 5.2・12.1 | 範囲外: S-D6・J-O1・X-BD5 の個別行(12.7)が省略されている | 12.7 に 1 行ずつ追加 |

## ユーザーへの確認事項(レビュアーの指摘から)

1. 要件 0000 の「APIサーバーから静的配信する構成を基本とする」は 0003 のユーザー指示で上書きされた。0000 はユーザー記載の文書のため書き換えていない(E 改訂履歴・FARC-K-4・0003 に記録)。**0000 に反映するかはユーザーの判断**(完了報告で伝える)
2. 0000 の「既存の公開範囲およびセキュリティに関する制約を維持する」は、G4-2 で `web` に入口を一本化した。承認済み(0007)
3. 前提タスク A・B+C を本タスクで起票しない扱いでよいか(完了報告で確認)

## 次にやること

P8: 上の指摘のうち 1〜34 を直し(E・F・A)、指摘したレビュアーに再レビューを依頼する → `0013-review-fixes.md`
