# 0027 R2 レビュー結果(C・D)

日付: 2026-11-22
レビュアー: document-reviewer(メインが記録)

## 結論

Critical なし。Important 9 件、Suggestion 12 件、Nitpick 5 件。C・D は B の EP-01〜14・導出項目・環境変数名・エラー写像とおおむね一致し、C は軽微な修正で使える。D は大筋が通るが、依存ルールと C の記述の間に実装を止めうる食い違い 2 件(I-3、I-4)。他文書は無変更(`git diff --stat 2cb500fa` は空)。C の追従修正(`source_missing` 等)は実施済みと確認。**D 作成者の最終報告は未入手のため、D の新規 ID は実物から一覧化**(下記)。フェーズ5へは Important を C・D(および A)に反映してから進む。

## Important(9 件)

1. **I-1 `job_id` の全文字エンコードが `.`・`..` で成立しない**(C 4.8・11 観点3、B 2.12・9.1): `urllib.parse.quote(value, safe="")` は `.` を符号化せず、urllib3 の `PoolManager.urlopen` は URL を `parse_url` で正規化してドットセグメントを除去する(urllib3 2.8.0 で確認: `job_id=".."`→`/jobs/../cancel`→送出 `/cancel`、`"."`→`/jobs/cancel`。`%2E%2E`・`%2E` は保持)。「6 つの固定の経路だけ」(AAA-K-7、C 2.3(4))が崩れる。提案: `quote(value, safe="")` の後に `.` を `%2E` に置換と明記、観点3の期待値を「スタブが `%2E%2E` を受けること」に。代案(`.`・`..` だけの `job_id` を B 2.12 の検証で拒否)は AAPI-P-24 の変更でゲート3確認が要る
2. **I-2 `mget` の文書単位エラーと `search` の `_shards.failed` が失敗として扱われていない**(C 3.2・3.3 の R-4・R-5・R-7・R-8、5.8): `mget` は HTTP 200 で `docs[i].error` を返しうる、`search` も 200 で `_shards.failed>0` になりうる。`found` を持たない文書を「記録なし」と読むと、実在するロックを `lock_state=none`、EP-10 を 404 と誤判定する。提案: 「`docs[i]` に `error` がある、または `found` が真偽値でないものは `Failed`」「`_shards.failed>0`・`timed_out=true` の検索結果は `Failed`」と書き、契約テスト・偽物の注入ケースに足し、AAA-U-2 に実機確認項目を追加
3. **I-3 D の R5(urllib3 の所有者)が C 5.8・6.2 の例外分類と両立しない**(D 6章 R5・許可表・4.8、C 5.8・6.2、A 3): OpenSearch 例外の分類が `ConnectionError.info` の `urllib3.exceptions` 型で決まり、判定は `infrastructure/opensearch/failure.py`・`health_probe.py` に置く設計だが、R5 と A 3 は「urllib3 は `crawler_client` と `probes` だけ」。Crawler の `tests/architecture/dependency_rules.py` は urllib3 の所有者を `indexer_client` だけにしている。提案: (a) `urllib3.exceptions` の import を `infrastructure.opensearch`(`failure.py`・`health_probe.py`)に限って許す(`EXTERNAL_LIBRARY_OWNERS` に追加、A 3 も直す)、または (b) クラス名・MRO の文字列比較(理由を書く)。AAM-P-12 の確認要点に足す
4. **I-4 D の uvicorn 起動に `access_log=False`・`log_config=None` がない**(D 4.1・5.9、A 5.5、C 8.5): 既定だと `job_id` を含むパスがアクセスログに出る(A 5.5 違反)。Crawler・Indexer は `access_log=False`、Crawler は `log_config=None`。提案: 4.1 手順6・5.9 に明記し、`uvicorn`・`uvicorn.error` のロガーの扱いを C 8.5 と同じ流儀で
5. **I-5 D 2.1 の図が `server --> routers` で R3・許可表と矛盾**(D 91 行、R3、許可表): `server` が import してよいのは `admin` の入口(`create_admin_app`)だけ。図を `server --> admin(create_admin_app)` に直し、`main --> admin`・`main --> infra` を足す
6. **I-6 D が参照する C の「D への引き継ぎ」の節が C にない**(D 改訂履歴・8.5・8.1): 引き継ぎ一覧は作業記録 0019 にある(推測)。提案: (a) C に節を足す、または (b) D 8.5 の左列を「C 本文中の『(D)』の注(2.3・3.2・4.4・5章冒頭・5.0・8.6・10・11)」に書き直し、列名と改訂履歴も直す
7. **I-7 索引名の環境変数の渡し方が compose・init の実際の変数名と意味がずれている**(C 10・7.2・12.5 I-90、A 8・4): `infra/opensearch/init-indices.sh` では `SEARCH_INDEX_NAME` が実体名(既定 `loreley-documents-000001`)、`SEARCH_INDEX_ALIAS` がエイリアス(既定 `loreley-documents`)。Indexer の `search_index_name` 既定は `loreley-documents`(エイリアス)。現在の compose は Indexer に検索・削除記録の索引名を渡さず、Crawler は検索・削除の索引名を持たない。「opensearch-init・Indexer・Crawler と同じ変数から渡す」を字義どおり実装すると実体名が入り、再インデックス後に古い索引を読む。提案: I-90 を「init の `SEARCH_INDEX_ALIAS` と Indexer の `LORELEY_INDEXER_SEARCH_INDEX_NAME`(エイリアス)に揃える。init の `SEARCH_INDEX_NAME` は実体名で別物」と正確に。C 10(2)・A 8 の「同じ変数」を「検索エイリアスは init の `SEARCH_INDEX_ALIAS` と同じ変数から」に。「Crawler と同じ」は `sources`・`jobs` の 2 つだけ(`deletions` は Indexer と、`search` は Indexer と init)
8. **I-8 AAA-P-8 の区分に BAPI-P-12 の「再試行条件は案(ゲート3)」が反映されていない**(C 3.7・12.3 の AAA-P-8・12.6、A BAPI-P-12): 該当は `retry_on_timeout=False`・接続エラーの再試行・`retry_on_status=(429, 500, 502, 503, 504)`。提案: AAA-P-8 を「承認済みの案(値: BAPI-P-12。ゲート2)。再試行の条件は案(BAPI-P-12 の明確化分。ゲート3)」に、12.6 に AAA-P-8 を足し、`retry_on_status` が A 5.6 の「5xx」より狭いことも明記
9. **I-9 D が出した A・B・C への修正依頼がどこにも記録されていない**(D 8.6): D から読み取れる依頼(未反映): A 3章(L113)「ヘルスプローブ」の範囲(urllib3 の HTTP プローブと opensearchpy の `cluster.health` プローブを区別)/ A 5.4(L192)のタグ(A は 6 種と書くが B の領域列には「クロール操作」(EP-06〜08)があり 7 種に見える。D は EP-06・08 を `sources`、EP-07 を `jobs` のタグにした)/ A 7章(L226)の「Repository」(D は Reader。C 2.3(2) L85 にも同語)/ C 2.3・6.2 の OpenSearch プローブの置き場(D は `infrastructure/opensearch`)。提案: 8.6 に表で内容を書く

## Suggestion(12 件。要旨)

S-1 urllib3 の `SSLError` が 504(結果不明)に分類される(C 4.3 順5、7.3)→ 503 `crawler_unreachable` に、または MVP は `CRAWLER_URL`・`INDEXER_URL` を http 限定 / S-2 `abandon_on_cancel` と「スレッドは 28 以内」の主張(anyio 4.16.0 の既定 `abandon_on_cancel=False` ではキャンセルがスレッド終了まで無視される。EP-13 の期限(確認+1 秒)で `undetermined` は `True` が前提。C 6.1・8.1 に「期限後も確認のスレッドは自身のタイムアウト(最大約 6 秒)まで残る。EP-13 は 30 秒間隔なので無害」を書き、AAM-U-1 とそろえる。プローブの urllib3 に `Timeout(total=…)` を使うかを決める)/ S-3 D の `web` 確認(`stat`+1 バイト読み)が R9 の例外になっている / S-4 D 4.3 の `request_input.py` を `Depends` の同期関数で書くと共通スレッドプールで走る(依存関係はすべて `async def` と明記)/ S-5 D R8(a)の許可リストを最後の属性名でなく `名前空間.メソッド` で定義(`cluster.health`・`cat.indices`・`cat.shards`・`cat.nodes`・`search`・`msearch`・`mget`)。ラッパーの公開メソッドは明示の引数のみ、`**kwargs` の素通し禁止 / S-6 `infrastructure` が `common.http` 経由で fastapi を間接 import しうる(「`infrastructure` は `common.http` を import しない」を許可表に)/ S-7 D 4.1 の「`main.py` だけが生のクライアント(`PoolManager`)を作る」が R5 と衝突(「`main` が各モジュールの生成関数を呼ぶ」に)/ S-8 `WEB_DIST_DIR` の既定値がどの文書でも未決(A 4 は「D・E で確定」。既定パスを 1 つ決めるか AAM-U に)/ S-9 C 3.5 の表の列見出し「`_source` からだけ読む項目(未マップまたは `enabled: false`)」が事実と違う(`loreley-sources`・`loreley-deletions` は `connector_config` 以外マップ済み、`loreley-jobs` の `trigger` もマップ済み keyword。見出しを「フィルタ・並べ替え・集計に使わず `_source` から読む項目」に)/ S-10 D 4.2 の見出しの ID(`AAM-P-3・P-24`→`AAM-P-3・P-23`)/ S-11 `JobBrief` の各項目の導出規則が C に表で揃っていない(5.4 に `failure_reason`・`force_delete`・`rewrite_mode`・`trigger` の通し方と `failed` 以外で `null` にする規則、5.3 順1・4 の `status=null`・`job_type=null` の扱い)/ S-12 `no-store` を付ける範囲(API の応答だけ。静的アセットは対象外)

## Nitpick

N-1 索引名の既定値の根拠(I-7 で解消)/ N-2 C 0・A・B が D・C を「作成予定」と書く(フェーズ5で置換)/ N-3 D 6 前文の「一部は各機能のテストで確認」の範囲 / N-4 D 7.3 の「C 11 章の 8・9・11 と R8〜R10 が一致」→「8・11 と R8〜R10。9 は `contract/`」/ N-5 C 12.2 の AAA-K-7 の出典に SD §14.4(「固定の経路だけ中継し、任意のパスは転送しない」)を足す

## D の新規 ID(実物から)

- AAM-K-1〜4(引用のみ): admin パッケージ・同一オリジン静的配信(0001 Q2、BAPI-K-1・K-2、AAA-K-8)、Store 層・検索インデックスに書かない(CAPI-K-5・CA-K-2、AAA-K-1)、Crawler への中継は固定 6 経路(CAPI-K-1・CA-K-19、AAA-K-7)、技術スタックは Indexer・Crawler と揃える(0000、BAPI-K-3)
- AAM-P-1〜25: P-1 `apps/api/`・`loreley_api`(承認済みの案 BAPI-P-11)、P-2 層と並び、P-3 `server` の外側アプリ(承認済みの案 BAPI-P-9・P-2。実装形は案)、P-4 `admin` の内部分けとタグ 6 種、P-5 `async def` + `BlockingRunner`(AAA-P-33 の実装形)、P-6 `derivation` は純粋関数、P-7 `schemas` は strict・422 は A 5.2 の形に変換、P-8 許可リストのラッパー(公開メソッド 7)と Reader、P-9 Reader の戻り値 `Ok / Failed`、P-10 Crawler クライアントの 6 操作・返り値 4 種、P-11 `crawler_mapping` は B 9.2 のデータ表、P-12 プローブの置き場、P-13 `common` の中身、P-14 設定の流儀、P-15 `main.py` の起動順・停止順、P-16 `openapi_export.py`(方針は承認済みの案 BAPI-P-10)、P-17 `search`・`mcp` を兄弟、P-18 依存ルール R1〜R12 と許可表、P-19 読み取り専用の検査を許可リスト方式に(Indexer の拒否リスト方式からの変更)、P-20 テスト構成と C 11 章の 16 観点の配置、P-21 偽物の水準、P-22 依存パッケージ(`anyio` を直接 import として追加)、P-23 サブアプリ下のハンドラ・ログ、P-24 `lock_view`・`stalled_check`、P-25 ファイル名は目安
- AAM-U-1〜8: `CapacityLimiter`・`abandon_on_cancel`、サブアプリ下のログ・ハンドラ、422 の対応表、AST 検査の限界、偽物がクエリの意味を実行しないこと、Search/MCP 同居時の再検討、`openapi_export` と型生成、`BlockingRunner.run_all` の API
- I-110〜119: 新規なし

## ゲート3で承認を取る D の案

D 8.7 が明示: AAM-P-2・P-17、P-5、P-8・P-19、P-12、P-10・P-11、P-21。加えて確認すべき: P-22、P-23、P-16、P-4(タグ 6 種と A 5.4 の関係)、I-3(urllib3 の所有者=AAM-P-12 の関連)、I-4(uvicorn 起動引数=AAM-P-15)

## C の追従修正の実施状況

実施済み(`source_missing`=5.3 順 8・AAPI-P-41、`rerunnable=null` に設定の読み取り失敗=順 7・5.8、`null` を許す型=5.0、`timeout` 優先=5.8、`ttl_days` の `unavailable` は `ttl_seconds` のキーのみ、A 4・5.6・2.1・8 の反映=3.7・7.2・8.1・10)。未反映: D 作成を受けた C 2.3(Repository の語)・6.2(プローブの置き場)の追記(I-9)、「作成予定」の語(N-2)

## ユーザー確認(ゲート3に追加)

1. I-1: `.`・`..` を `%2E` に符号化(採用)か、`job_id` の検証で拒否(B 2.12 の変更)か
2. I-8: `retry_on_timeout=False`・`retry_on_status` の組み合わせ(区分を案に直す)
3. S-1: Crawler 接続を http 限定にするか TLS 検証(CA)の設定を持つか
4. S-8: `WEB_DIST_DIR` の既定値の決め方
5. I-7: A 8・C 10 の compose への要求が infra の前提作業に直結(フェーズ5の申し送り)

## メインの対応方針

- I-1: `%2E` 置換を案として採用(検証規則を変えない)。I-3: (a)(`urllib3.exceptions` の import を `infrastructure.opensearch` に限って許す)を案として採用し AAM-P-12 の確認要点に。S-1: 案として http 限定(MVP)・`SSLError` は 503。S-8: 既定パスを C 7.2 に案として置く。I-6: (b) で直す
- Important 全件・Suggestion・Nitpick を、C・D は別の writer(前任の C/D writer は報告が届かないため)、A は B 担当の writer に依頼する

## 次

C・D の修正、A の修正 → 差分確認(R2 再確認)→ フェーズ5
