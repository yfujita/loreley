# 0029 R2 指摘のうち C・D 側の修正

日付: 2026-11-23
担当: document-writer(C・D 修正の新しい writer。メインが記録)

## 変更ファイル

- C `admin-api-architecture-v0.1.md`(921→960 行)、D `admin-api-module-structure-v0.1.md`(910→953 行)のみ。A・B・E・F・SD・PD・DS・画面仕様・CLAUDE.md・apps/・agent_tasks は無変更。更新日は A・B と同じ 2026-11-22 のまま
- D の前任 writer の報告が未入手のため、D 8.6 の修正依頼の内容は 0027 の I-9 と D の記述から再構成した(8.6 に注記済み)

## Important の対応

- I-1(`job_id` の `.`): C 4.8 に `quote(safe="")` の後に `.`→`%2E` を明記(理由と代案=`.`・`..` だけの `job_id` を B 2.12 の検証で拒否)。`source_id` の `.` も同様。AAA-U-4 に実機確認を追加。C 11 観点 3 の期待値を「スタブが生のリクエスト行で `/jobs/%2E%2E/cancel` を受けること」に。AAA-P-14 を「案。ゲート3で確認」に。D 4.9 `routes.py`・7.2 のスタブ
- I-2(部分的な失敗): C 3.2 に新規則 **AAA-P-39**: `mget` の `docs[i].error` や `found` が真偽値でない文書は `Failed`、検索・`msearch` の `timed_out=true`・`_shards.failed>0`・形の異常も `Failed`。C 3.3 の R-4・R-5・R-7・R-8、5.1 順1、5.8(`timed_out` は `timeout`、それ以外は対象別)、11 観点6 に注入ケース、AAA-U-2 に実機確認。D 4.8(Reader が応答を検査し `mget` 系は文書ごとに `Ok/Failed`)、7.1・7.2、AAM-P-9
- I-3(`urllib3.exceptions`): (a) 案で対応(**AAA-P-40・I-92** 新設)。C 2.3(3)・4.1・5.8・6.2。D: R5・許可表・2.1 の注・4.8 の依存・AAM-P-12・8.7・**I-110**(Crawler の `dependency_rules.py` が `urllib3` の所有者をモジュール単位でしか持てず、検査器の拡張が要る)
- I-4(uvicorn): D 4.1 手順6・5.9 に `log_config=None`・`access_log=False`、ワーカー数は指定しない(Crawler・Indexer と同じ)。AAM-P-15。C 8.5・AAA-P-38: `uvicorn.access` を ERROR 以上に制限、`uvicorn.error` は制限しない、想定外の例外は middleware が 500 に変換して再送出しない(Starlette の `Exception` ハンドラは応答後に再送出し uvicorn がトレースバックを出すため。Crawler の `api/middleware.py` と同じ理由)。D の `handlers.py` から想定外の例外を外し middleware の担当に
- I-5: D 2.1 の図を修正(`server --> adminEntry`、`main --> adminEntry`、`main --> infra` を追加、`server --> routers` を削除)
- I-6: (b) で対応。D 8.5 の左列を「C 本文中の『(D)』の注」に書き直し、C の各章との対応を別表に分け、改訂履歴と 8.1 も修正
- I-7: C 10(2)・7.2・I-90 を実物どおりに書き直し(`SOURCES_INDEX_NAME`・`JOBS_INDEX_NAME` は Crawler と、`DELETIONS_INDEX_NAME` は Indexer と、検索エイリアスは init の `SEARCH_INDEX_ALIAS` と Indexer の `LORELEY_INDEXER_SEARCH_INDEX_NAME` と同じ変数から。init の `SEARCH_INDEX_NAME` は実体名で別物なので渡さない)。**I-93** 新設(現在の compose が検索・削除記録の索引名を Indexer と init に渡していない事実)
- I-8: AAA-P-8 を「承認済みの案(値)+再試行条件は案」に。12.6 に追加。`retry_on_status` が A 5.6 の「5xx」より狭いことを 3.7・9 に明記
- I-9: D 8.6 に A・B・C への修正依頼を表(11 件、状態つき)で記載

## Suggestion・Nitpick の対応(要旨)

- S-1(AAA-P-41・U-9): `SSLError` は 503 `crawler_unreachable`(C 4.3 に順4として追加し以降を繰り下げ)。`CRAWLER_URL`・`INDEXER_URL` は MVP では http 限定(7.2・7.3・6.4)。D は `urls.py`・`config` に反映
- S-2(AAA-P-42・U-10、AAM-P-27): EP-13 の期限は `abandon_on_cancel=True` が前提(anyio 4.16.0 のソースで既定 `False`、`True` のとき取消でトークンが返ることを確認)。「スレッドは 28 以内」は放棄分を除くと書き直し、残る時間は HTTP プローブ最大約 3 秒(`Timeout(total=…)` 採用)、opensearch プローブ最大約 6 秒。名前解決は urllib3 の `Timeout` の対象外(推測)=AAA-U-10。C 6.1・8.1・9、D 2.2・4.10・4.11・AAM-U-1
- S-3: `web` の確認は枠に渡さない明示の例外(D R9、C 6.3)。枠に渡すと期限超過時の `state` が B にない(web は判定不能なし)ため
- S-4: `Depends` もすべて `async def`(D 4.3・R9。AST 検査の限界は AAM-U-9)
- S-5: D R8(a)(b)・4.8・AAM-P-8 で許可リストを `名前空間.メソッド` 7 つで定義し `**kwargs` の素通し禁止。C 2.3(2)も同様
- S-6: 許可表・R12・R5 に「`infrastructure` は `common.http` を import しない」
- S-7: 生成関数は `infrastructure` が持ち `main` が呼ぶ形(D 4.1・R6・AAM-P-15)
- S-8(AAA-P-43): C 7.2 の `WEB_DIST_DIR` の既定を `/app/web`、C 10(4)に Dockerfile の `dist/` コピー先を追加(E 3.5 と整合)
- S-9: C 3.5 の列見出し修正 / S-10: D 4.2 の見出しの ID を `AAM-P-3・P-23` に / S-11(AAA-P-44): C 5.4 に `JobBrief` の項目ごとの導出表(`failure_reason` は `status=failed` のときだけ通す、列挙外は `null`。`job_type=null` は `not_crawl`、`status=null` は `not_failed`)/ S-12(AAM-P-26): `no-store` は `/api/` の応答だけ
- N-2: C の「作成予定」を削除 / N-3: D 6 前文を、自動検査・各機能のテスト・機械検査不可に区別して書き直し / N-4: D 7.3 / N-5: C 12.2 の AAA-K-7 の出典に SD §14.4 の 6 を追記
- 追従: B の最新(0026)に合わせ C 5.4 の `phase` を `partial` が真偽値でない場合と `partial=true` で `status` が読めない場合に `null`、D 4.4 を「件数・`partial`・`phase`」に

## 新規・変更 ID

- C: 新規 AAA-P-39〜44(すべて案。実機確認が要るものは AAA-U-2)、AAA-U-9・10、I-92・93。区分変更: AAA-P-8(承認済みの案(値)+再試行条件は案)、AAA-P-14(`.` の置換は案)。追記: AAA-P-11・28・33・38、AAA-U-2・U-4、I-90。`-K-` の新規なし(AAA-K-7 の出典のみ追記)
- D: 新規 AAM-P-26(`no-store`)・P-27(`run_all` の放棄)、AAM-U-9(`Depends` の AST 検査)、I-110。更新: AAM-P-5・8・9・12・15・18、AAM-U-1。`-K-` の新規なし

## ゲート3の確認事項の増減

増(C): `.`→`%2E` か検証での拒否か(I-1)、AAA-P-8 の再試行条件(I-8)、AAA-P-39(部分的な失敗)、AAA-P-40・41(`urllib3.exceptions`・http 限定。A の BAPI-P-22・24 と同じ)、AAA-P-42(`abandon_on_cancel`)、AAA-P-43(`WEB_DIST_DIR`)、AAA-P-44、I-90・93(索引名の渡し方。infra の前提作業に直結)。増(D): AAM-P-4(タグ 6 種)、AAM-P-5 の `web` 例外、AAM-P-12(`urllib3.exceptions`)、AAM-P-15(uvicorn 引数)、AAM-P-16・22・23・26・27。減なし

## A・B への修正依頼(残り)

- A 5.6: `retry_on_status` は `(429, 500, 502, 503, 504)` の 5 値で「429・5xx」より狭い(AAA-P-8)
- A 5.5(任意): uvicorn は `log_config=None`・`access_log=False` で起動(C 8.5・D 4.1)
- B 9.1 の例外分類表に `SSLError`(503)が要るか確認(B の writer)
- その他は A・B の writer がすでに反映済み(BAPI-P-22・23・24、索引名、`WEB_DIST_DIR`、`no-store`、`%2E`)

## 申し送り候補の増減(フェーズ5で A 9 章へ)

追加: compose の索引名の渡し方(I-90・93)、Dockerfile が `dist/` を `/app/web` にコピーすること(E 3.5、AAA-P-43)、検査器の拡張(`urllib3.exceptions` のファイル単位の許可。D の I-110、C の I-92)。`HO-n`(C 本文の 6 か所)はフェーズ5で置換

## 自己検算(writer)

表の列数は C 32 表・D 17 表で不一致 0(バッククォート内の `|` も区切りとして数える方式)、コードフェンスは C 14・D 24 でいずれも偶数、ID 参照(AAA 定義 62・AAM 定義 40)に未定義 0・未参照 0、C→D・D→C の相互参照に未定義 0、欠番 ID への参照なし、C・D のバッククォート内のエラー code はすべて B にある、EP-01〜14 の対応は無変更、環境変数名は A・B・C・D で一致(`LORELEY_API_` の有無のみ)。mermaid の構文はツールで未確認。実機で確認できなかった点は AAA-U-2・U-4・U-9・U-10

## レビュー計画の判断

R2 の個別の再確認は実施せず、R4(6 文書+CLAUDE.md の横断整合)で C・D の今回の変更(AAA-P-39〜44、AAM-P-26・27、I-92・93・110)を重点的に確認する。理由: 修正の反映箇所が多く、A・B・E・F との横断的な整合(環境変数名、`urllib3` の許可範囲、タグ、索引名)を別々に確認するより R4 で一度に確認するほうが重複が少ない。R4 で Critical / Important が出たら修正し、再確認する。

## 次

A の小修正(5.5・5.6)と B 9.1 の `SSLError` の確認 → フェーズ5(統合)
