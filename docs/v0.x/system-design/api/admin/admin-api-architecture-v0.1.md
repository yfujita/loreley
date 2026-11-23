# Admin API アーキテクチャ設計書 v0.1

- 版: v0.1(ドラフト。ゲート3(2026-11-23)の承認を反映済み。実装はスコープ外で、実装時確認事項(AAA-U)が残る)
- 更新日: 2026-11-23
- 前版: なし(初版)
- 位置づけ: Admin API(`api` コンテナの admin パッケージ)の**実装レベルの設計**。B(`admin-api-v0.1.md`)が「C が決める」とした事項(導出ロジック、データアクセスのクエリ形、Crawler クライアントの実装方針、死活判定、環境変数の個別一覧、仮値、部分失敗の理由コードの付け方、テスト観点)を定める。エンドポイント・DTO・Admin 固有 code・Crawler 写像は B が、エラー応答の形式・共通 code・共通の設定規則・タイムアウトとリトライの共通方針は `../api-base-design-v0.1.md`(以下 A)が正本で、本書は**参照のみ**で複製しない。Search API・MCP の設計は含まない。
- 本書は Admin 画面の詳細設計タスク(`20261122_create_admin_system_design`)の成果物で、SD・PD・crawler / indexer 設計・機能設計・画面仕様を変更しない。既存設計と食い違う点は I-90 以降に、追従改訂は A 9章(申し送り一覧。HO-1〜HO-51)に集約する。
- 改訂履歴: v0.1 は初版(フェーズ2-2)。B の R1 レビュー(作業記録 0010〜0014)で C に引き継がれた事項(ロックとジョブの読み順、`lock_state` の排他定義、プローブのリダイレクト非追従と確認先 URL の環境変数限定、`job_id`・`source_id` の全文字エンコード、EP-07 の `job_id` 起因の 400・404 を 404 `job_not_found` に写すこと、`unavailable` の正式パス、CORS を許可しないことのテスト観点)をすべて含めた。B 11.10 との対応は 12.7。A・B の C 追従(作業記録 0020)を受け、5.0・5.2・5.3(`source_missing`)・5.4・12章を更新した。R2(作業記録 0027)の指摘を反映した: `job_id` の `.` の符号化(4.8)、`mget`・検索の部分的な失敗の扱い(3.2・5.8)、`urllib3.exceptions` の import 範囲(2.3・5.8)、索引名の渡し方(10章・I-90)、再試行条件の区分(3.7)、`SSLError` の分類と `CRAWLER_URL`・`INDEXER_URL` の http 限定(4.3・7.3)、`WEB_DIST_DIR` の既定(7.2)、EP-13 の期限と放棄(6.1・8.1)、uvicorn のログ(8.5)、`JobBrief` の各項目の規則(5.4)、ほか。フェーズ5の統合(2026-11-23): 申し送りへの参照を A 9章の実番号に置き換え、関連文書の表に D・E・F を足し、更新日を統一した。R4 指摘の反映(2026-11-23): 2.3(2)の「Repository」の語を A 7章の語に合わせた。 ゲート3の承認(2026-11-23)の反映: 案の区分を承認済みの案(ゲート3。2026-11-23)に更新した(設計の内容は変更なし)。PR #10 のレビュー指摘への対応(2026-11-23): 一覧の EP(EP-01・09・11)の `unavailable` を行単位にした(B 2.2・AAPI-P-42)。キーは行の中の相対パスで、最上位は行に属さない項目だけ。失敗の帰属の規則(5.8)を足し、3.2・3.3・5.2・5.5・5.6・5.10・8.6・11章・12章を更新した(AAA-P-45。AAA-P-25・P-35 などの区分は承認済みの案(ゲート3)の修正)。 API 基盤の実装に合わせた追従改訂(`20261123_update_api_design_after_base_impl`。2026-11-23): 他文書の HO 範囲の表記を「HO-1〜HO-51」に統一した(設計の内容は変更していない)。

## 0. この文書について

- 対象: Admin API の内部の設計(データの読み方、Crawler・OpenSearch・各コンポーネントとのやり取り、導出、設定、並行性、テスト観点)。モジュール・ディレクトリ・依存規則は D(`admin-api-module-structure-v0.1.md`)が正本。
- 読み方: 1〜2章で原則と境界、3章でデータアクセス(クエリ形)、4章で Crawler 連携、5章で導出、6章で死活判定、7章で設定、8〜9章で並行性と仮値、10章でコンテナ、11章でテスト観点、12章に確認状況(ID・B 11.10 との対応表)。
- コード・設定ファイルは作らない。クエリの JSON・短い関数の概形・表は示す(実装の正本ではない)。

区分の凡例は A 0章と同じ(確定 / 案 / 承認済みの案 / 未決 / 推測 / 導出)。**`-K-` にしたのは、ユーザーの明示回答と、確定として書かれた既承認文書の引用だけ**。B・A のゲート1・2 で承認済みの案は「承認済みの案」として出典の ID を書いて引用し、本書で新たに決めた判断は、ゲート3(2026-11-23)で承認され、「承認済みの案(ゲート3。2026-11-23)」とした(確定にはしていない)。承認済みの案の実装形(クエリの形、関数の置き方)が本書の追加の場合は、区分欄に「実装形はゲート3で承認」と書く。

ID 体系: `AAA-K-n` / `AAA-P-n` / `AAA-U-n`。既存設計との不整合は `I-n`(本書の予約範囲は I-90〜99。A は I-60〜69、B は I-70〜79、D は I-110〜119、E は I-80〜89 と I-120〜129、F は I-100〜109 と I-130〜139)。A の ID は `BAPI-*`、B の ID は `AAPI-*`。EP は B の通し番号(`EP-01`〜`EP-14`)。読み取りの単位は本書の通し番号 `R-1`〜`R-12`(3.3)。

関連文書(いずれも `docs/v0.x/` 配下):

| 略称 | 文書 | 本書との関係 |
| --- | --- | --- |
| A | `system-design/api/api-base-design-v0.1.md`(v0.1。作成済み) | エラー形式・共通 code・共通の設定規則・タイムアウトとリトライの共通方針の正本 |
| B | `system-design/api/admin/admin-api-v0.1.md`(v0.1。作成済み) | EP・DTO・Admin 固有 code・Crawler 写像の正本。11.10 が本書への引き継ぎ |
| D | `system-design/api/admin/admin-api-module-structure-v0.1.md`(v0.1。作成済み) | 本書の設計を担うモジュール・依存ルール。本文中の「(D)」の注の割り当て先 |
| E・F | `system-design/ui-admin/frontend/ui-admin-frontend-architecture-v0.1.md`、`ui-admin-frontend-module-structure-v0.1.md`(いずれも v0.1。作成済み) | Admin API の呼び手(Web UI)。EP・code は B を参照する側 |
| crawler-api / crawler-architecture | `system-design/crawler/crawler-api-v0.4.md`、`crawler-architecture-v0.4.md` | Crawler の 6 API、`loreley-jobs`・ロック文書・リース・ジョブ状態の事実の正本 |
| schema | `infra/opensearch/schema/*.json`、`system-design/opensearch/schema/` の各設計書 | 索引・フィールド・型の事実の正本 |
| indexer-api / indexer-architecture | `system-design/indexer/indexer-api-v0.10.md`、`indexer-architecture-v0.10.md` | `/healthz`(契約外)、検索インデックスの読み取り(K53・U-30) |

---

## 1. 位置づけ・設計原則

Admin API は、Admin View の操作と表示のための窓口で、状態を持たない。次の原則に従う(導出。出典は各行)。

| # | 原則 | 出典・理由 |
| --- | --- | --- |
| 1 | **何にも書かない**。書き込みは Crawler の HTTP(固定の 6 経路)だけを通す。Store 層・検索インデックス・メンテナンスフラグ・索引の設定には書かない | AAA-K-1 |
| 2 | **読み取りは Crawler・Indexer の停止に影響されない**。Crawler・Indexer が止まっていても、画面の表示は OpenSearch だけで動く | B 10章、SD §14.5 |
| 3 | **失敗は局所化する**。主たる読み取りの失敗は 503、付随する読み取りの失敗は該当項目を `null` にして `unavailable` に理由を載せる | B 2.2 |
| 4 | **Crawler への書き込みは自動再送しない**。結果が不明なときは、不明であることをそのまま返す | A 5.6、B 2.3 |
| 5 | **外部の値を信用しすぎない**。OpenSearch・Crawler から読んだ値は、型を確かめてから使い、読めない値は安全側(`null`・`unknown`・停止している扱い)に倒す | crawler-architecture 5.1 の読み取り規則に倣う |
| 6 | **入力値・パス・認証情報・例外メッセージを、応答にもログにも出さない** | A 2.3・5.2・5.5 |
| 7 | **外部の仕様への依存を 1 か所に集める**。`loreley-jobs` の項目名、`cat.*` の列、Crawler の `message` の形式への依存は、読み取りの層・Crawler クライアントの層に閉じ、導出は純粋な関数にする(D) | R1 の指摘(`message` の形式依存。AAPI-U-2)に対する構造上の対策(導出) |

---

## 2. 責務と境界

### 2.1 論理構成

```text
Admin View(ブラウザ)
   │  HTTP(同一オリジン。/api/admin/v1/…。CORS は許可しない)
   ▼
api コンテナ(uvicorn 単一プロセス)── admin パッケージ(本書の対象)
   │ ①読み取りのみ          │ ②操作 6 API のみ        │ ③GET /healthz         │ ④設定・ファイル
   ▼                       ▼                        ▼                       ▼
 OpenSearch               Crawler                  Crawler・Indexer          環境変数・WEB_DIST_DIR
  ├ loreley-sources         (POST /sources            (任意コンポーネントは
  ├ loreley-jobs             PUT /sources/{id}         設定された URL だけ)
  ├ loreley-deletions        POST …/crawl-jobs
  ├ 検索インデックス(エイリアス) POST …/delete-jobs
  └ クラスタ情報               POST /jobs/{id}/cancel
    (cluster.health・cat.*)   DELETE …/lock)
```

- **Store 層(`loreley-sources`・`loreley-jobs`・`loreley-deletions`)と検索インデックスへは読み取りだけ**。書き込む経路は、Crawler の HTTP クライアント(②)以外にない(AAA-K-1)。
- ③の確認先は、環境変数の URL だけ(リクエストから受け取らない。6.4)。

### 2.2 責務

| Admin API が持つ | Admin API が持たない |
| --- | --- |
| Crawler への 6 操作の中継と、エラーの写像(B 9章) | ジョブ・ロック・リースの管理、削除の判断(Crawler・Indexer) |
| `loreley-*`・検索インデックス・クラスタ情報の読み取りと、画面向けの導出(5章) | Connector の検証規則(`connector_config` の中身・`schedule_cron` の書式。複製しない。AAA-K-4) |
| しきい値・TTL・`min_delete_count` の範囲の検証と単位変換(B 2.4・2.8。AAA-K-5) | メンテナンスフラグの読み書き(AF-19 は表示のみ。AAPI-P-36) |
| 各コンポーネントの死活確認(6章) | 状態の保持(最終取得成功日時はクライアントが持つ。AAPI-P-8) |

### 2.3 読み取り専用の保証(書き込む経路がないこと)

破られても見つかるよう、複数の層で保証する(導出)。

1. **OpenSearch へ呼んでよい API は許可リストで固定**する(AAA-P-1): `search`・`msearch`・`mget`・`cluster.health`・`cat.indices`・`cat.shards`・`cat.nodes`。`search`・`msearch` は HTTP の POST を使うが読み取りである。`index`・`create`・`update`・`delete`・`bulk`・`*_by_query`・`reindex`・`indices.*`(`refresh` を含む)・スクリプト・`scroll`・PIT は呼ばない。
2. **Reader(読み取りの層。A 7章の読み取り専用の層。D)は書き込みのメソッドを持たない**(型で書けない構成)。生のクライアントを包むラッパーは、公開メソッドを(1)の 7 つだけにし、引数は明示のものだけを受ける(`**kwargs` を素通しして、許可した API に任意の引数を渡さない。AAA-P-1)。
3. **機械検査**: `tests/architecture/` に、クライアント由来の呼び出しの名前が許可リストの外にあれば失敗する検査を置く(Indexer の `test_write_rules.py` と同じ流儀。AST。限界: 動的な呼び出し・`transport.perform_request` は検出できない。D)。`opensearchpy` を import してよい場所は OpenSearch アクセスの層(`cluster.health` のプローブを含む)だけ、`urllib3` は Crawler クライアントと HTTP のプローブだけ(A 3章)。例外として、OpenSearch の例外の分類(接続のタイムアウトと接続拒否の区別。5.8・6.2)に `urllib3.exceptions` の型が要るため、**`urllib3.exceptions` の import に限り `infrastructure.opensearch`(`failure.py`・`health_probe.py`)にも許す**(AAA-P-40。I-92)。
4. **Crawler クライアントは任意のパスを受け取らない**。固定の 6 ルート(4.8。AAA-K-7)の関数だけを公開し、`request(method, path)` のような汎用の入口を持たない。
5. OpenSearch のセキュリティを有効にする運用では、`api` 用のユーザーに読み取りの権限だけを与える(BAPI-U-7。最小権限は実装時・運用で確認。AAA-U-8)。

### 2.4 EP と呼び先の対応(B の全 EP が本書のどこに対応するか)

| EP | 読む(読み取り単位。3.3) | Crawler | 導出(5章) | 6章・8章 |
| --- | --- | --- | --- | --- |
| EP-01 `GET /sources` | R-1、R-3、R-4・R-5(`stalled` の確認)、R-9 の件数集計 | — | 5.2、5.5、5.8 | — |
| EP-02 `GET /sources/{id}` | R-2、R-3、R-4、R-5、R-9 | — | 5.1、5.2、5.5、5.7、5.8 | — |
| EP-03 `POST /sources` | — | 4章(`POST /sources`) | 5.7、4.5 | 8.2 |
| EP-04 `PUT /sources/{id}` | — | 4章(`PUT /sources/{id}`) | 5.7、4.5 | 8.2 |
| EP-05 `POST …/delete-jobs` | 409 の付随情報として R-4・R-5 | 4章 | 5.1(`lock_state`) | 8.2 |
| EP-06 `POST …/crawl-jobs` | 同上 | 4章 | 5.1 | 8.2 |
| EP-07 `POST /jobs/{id}/cancel` | — | 4章 | 4.4(404 写像) | 8.2 |
| EP-08 `DELETE …/lock` | 409 の付随情報として R-4・R-5 | 4章 | 5.1 | 8.2 |
| EP-09 `GET /jobs` | R-6、R-4・R-5(`stalled` の確認) | — | 5.2、5.8 | — |
| EP-10 `GET /jobs/{id}` | R-5、R-4、R-7、R-2(再実行の判定)、R-8 | — | 5.2〜5.4、5.7、5.8 | — |
| EP-11 `GET …/documents` | R-2(存在確認)、R-10、R-9、R-11 | — | 5.6、5.8 | — |
| EP-12 `GET /opensearch/cluster` | R-12 | — | 3.4 | 8.3 |
| EP-13 `GET /dashboard` | `cluster.health`(プローブ用クライアント) | — | 6章 | 6章 |
| EP-14 `GET /meta` | — | — | — | 設定のみ |

---

## 3. データアクセス

### 3.1 読む索引と用途

索引名は設定で与える(7.2)。検索インデックスは**エイリアス**で読む(索引の実体名は使わない)。

| 索引 | 読む内容 | 読む EP | 書く者(参考) |
| --- | --- | --- | --- |
| `loreley-sources` | データソース設定(`connector_config` を含む)。ID は `source_id` | EP-01・02・10(状態)・11(存在確認) | Crawler |
| `loreley-jobs` | `record_type` ごとに ID の形が違う: `job`(`{job_id}`)、`lock`(`lock-{source_id}`)、`skip`(`skip-{source_id}-{document_id}`)、`oversize`(`oversize-{source_id}-{document_id}`)。`maintenance` は読まない | EP-01・02・09・10・11(+ 409 の付随情報) | Crawler |
| `loreley-deletions` | `deletion_result-{job_id}` だけ(ID で取得) | EP-10 | Indexer |
| 検索インデックス(エイリアス) | 件数、`extract_failed`・`summary_pending` の一覧、`document_id` の有無。本文・要約は読まない(3.6) | EP-01・02・11 | Indexer |
| クラスタ情報 | `cluster.health`・`cat.indices`・`cat.shards`・`cat.nodes` | EP-12・13 | — |

### 3.2 共通のクエリ規約

- **ID での取得は `mget`**(AAA-P-2): ID を本文(`ids`)に載せ、パスに埋めない。理由: (1) ジョブ ID は `%`・`?`・`#` を含みうるため(B 2.12)、パスに埋めると崩れる(opensearch-py がパスの ID をどう符号化するかはソースで確認していない)、(2) `mget` は書き込み直後でも見える(リアルタイム。3.3 の refresh の項)。取得した文書は `found=true` かつ `record_type` が期待のもの(`job`・`lock`・`deletion_result`)であることを確かめる(ロック・スキップ記録の ID を `job_id` として渡されたときに 404 にするため。crawler-api 3.2、B 5.2)。
- **`_source` は常に必要な項目だけを指定する**(AAA-P-3): ジョブ記録の `finish_notice`(ID 一覧を持つ)、削除結果の `skipped_document_ids`・`oversize_document_ids`、検索インデックスの `content`・`summary` を読まない(転送量と情報の最小化)。`loreley-jobs` は `dynamic: false` で、`failure_reason`・`force_delete`・`rewrite_mode`・`confirmation`・`registration` などは検索・並べ替えに使えず、`_source` からだけ読める(3.5)。
- **ページング**: `from = (page-1) × items_per_page`、`size = items_per_page`。API 層で `page × items_per_page ≤ 10,000` を検証済みのため(AAA-P-4)、OpenSearch の `max_result_window`(既定 10,000)を超えない(承認済みの案。AAPI-P-1。ゲート2)。`track_total_hits: true` で総件数を正確に取る(既定の 10,000 での頭打ちを避ける)。並べ替えは、指定の項目+ ID(`job_id`・`document_id`)の昇順で、同順位でも取りこぼし・重複が出ないようにする。
- **件数だけの取得**は `size: 0` の検索(`track_total_hits: true`)。`count` API は使わない(`msearch` にまとめるため)。
- **集計の `size`** は、対象のソース数(上限 10,000)に合わせる。
- **部分的な失敗を成功と読まない**(AAA-P-39): OpenSearch は HTTP 200 のまま一部の失敗を返しうる。応答を使う前に、(a) `mget`: `docs[i]` に `error` がある、または `found` が真偽値でない文書は、その文書の取得が `Failed`(`found=false` の「記録なし」とは読まない。読み違えると、実在するロックを `lock_state=none` に、実在するジョブを EP-10 の 404 にしてしまう)。他の文書の結果は使う。(b) `search`・`msearch`(サブ要求ごと): `timed_out` が `true`、`_shards.failed` が 0 より大きい、または `_shards`・`hits` が期待の形でない応答は `Failed`(部分的な結果を使わない)。(c) 理由コードは、`timed_out=true` を `timeout`、それ以外を対象別(5.8)とし、`error.type`・理由文は読まず出さない。(d) 失敗は、その結果が担う行(または最上位の項目)に帰属させる(`mget` の文書単位の失敗はその文書の行、`msearch` の `responses[i].error` はそのサブ要求が担う項目。5.8。AAA-P-45)。実機での応答の形は AAA-U-2。
- **失敗の分類**は 5.8。OpenSearch の例外は、`str(例外)` を応答・ログに出さない(`root_cause` の理由・リソース ID を含みうる。opensearch-py 3.2.0 の `TransportError.__str__` で確認)。
- **refresh 遅延**(AAA-P-6): `mget` は書き込みの直後でも見える(リアルタイム)。`search`・`msearch` は最大でおよそ 1 秒古い(`refresh_interval` は索引の設定に書かれておらず既定の 1 秒のはず。推測。実機で確認。AAA-U-3)。このため、起動・登録の直後に一覧を取り直すと、最大約 1 秒は反映されないことがある。Admin API は `refresh` を呼ばない(索引管理系の API を呼ばないため)。画面は次の取得で追いつく(E)。

### 3.3 読み取り単位と各 EP のクエリ形(AAA-P-3)

以下の JSON は形を示すもので、実装の正本ではない。`<…>` は設定・入力から埋める。

**R-1 データソースの全件(EP-01)**

```text
POST <sources>/_search
{ "size": 10000, "track_total_hits": true, "sort": [{"source_id": "asc"}],
  "_source": {"excludes": ["connector_config"]}, "query": {"match_all": {}} }
```

`hits.total.value` が 10,000 を超えたら、取りこぼしを避けるため失敗として扱う(503。B 3.1)。

**R-2 データソースの取得(EP-02・10・11)**: `mget` `index=<sources>` `ids=[source_id]`。EP-02 は全項目、EP-10 は `status` だけ(`_source_includes`)、EP-11 は存在確認(`_source: false`)。

**R-3 ソースごとの最新ジョブ(EP-01・02)**: 1 回の検索で、ソースごとの最新の `crawl`・最新の `source_delete`・最終完了日時を取る(AAA-P-3。対象は R-1 / R-2 で得たソース ID)。

```text
POST <jobs>/_search
{ "size": 0,
  "query": {"bool": {"filter": [{"term": {"record_type": "job"}}, {"terms": {"source_id": ["…"]}}]}},
  "aggs": {"by_source": {"terms": {"field": "source_id", "size": <ソース数>},
    "aggs": {
      "crawl": {"filter": {"term": {"job_type": "crawl"}}, "aggs": {
        "latest": {"top_hits": {"size": 1, "sort": [{"queued_at": "desc"}, {"job_id": "asc"}], "_source": {"includes": ["<JobBrief の項目>"]}}},
        "completed": {"filter": {"terms": {"status": ["succeeded", "partially_succeeded"]}},
                      "aggs": {"at": {"max": {"field": "finished_at"}}}}}},
      "delete": {"filter": {"term": {"job_type": "source_delete"}}, "aggs": {
        "latest": {"top_hits": {"size": 1, "sort": [{"queued_at": "desc"}, {"job_id": "asc"}], "_source": {"includes": ["<JobBrief の項目>"]}}}}}}}} }
```

`<JobBrief の項目>` は `job_id`・`source_id`・`job_type`・`trigger`・`status`・`force_delete`・`rewrite_mode`・`queued_at`・`started_at`・`finished_at`・`failure_reason`。`max` は `value`(エポックミリ秒。該当なしは `null`)を使い、UTC ミリ秒の文字列にして返す。`last_completed_at` は `completed.at`、`last_crawl` は `crawl.latest`、`delete_job` は `delete.latest`(ソースが `deleting` のときだけ使う。5.5)。R-3 は 1 回の検索なので、成否は全行で同じになる(失敗は全行。5.5・5.8)。

**R-4 ロック文書(EP-01・02・09・10、409 の付随情報)**: `mget` `index=<jobs>` `ids=["lock-<source_id>", …]` `_source_includes=[record_type, source_id, job_id, lease_expires_at, acquired_at]`。文書ごとに、3.2 の部分的な失敗でなければ、`found=true` かつ `record_type=lock` のものを「ロックあり」、`found=false` または `record_type` が `lock` でないものを「ロックなし」とする(`Failed` はロックなしとは読まない)。失敗は、その文書のソースの行(`running` のジョブを持つ行)の `stalled` のキーになる(5.2・5.8)。

**R-5 ジョブ記録の取得(EP-10、`stalled` の確認、`lock_state`)**: `mget` `index=<jobs>` `ids=[job_id, …]`、`_source_includes` は用途で変える(JobBrief の項目。EP-10 はさらに `failure_detail`・`warnings`・`registration`・`deletion_summary`・`confirmation`・`settings_snapshot`・`finish_notice.send_started_at`)。文書ごとの部分的な失敗(3.2)は `Failed`。`record_type=job` でなければ「ジョブ記録なし」。

**R-6 ジョブ一覧(EP-09)**

```text
POST <jobs>/_search
{ "from": <(page-1)*n>, "size": <n>, "track_total_hits": true,
  "sort": [{"queued_at": "<desc または asc>"}, {"job_id": "asc"}],
  "_source": {"includes": ["<JobBrief の項目>"]},
  "query": {"bool": {"filter": [{"term": {"record_type": "job"}},
      {"term": {"source_id": "…"}},                                  // 指定時だけ
      {"term": {"status": "…"}}  または  {"terms": {"status": ["queued", "running"]}}  // 指定時だけ(`active` は後者)
  ]}} }
```

**R-7 そのソースの最新の `crawl` の ID(EP-10 の `latest_for_source`)**: `search` `size: 1`、`_source: false`、フィルタ `record_type=job`・`job_type=crawl`・`source_id`、`sort: queued_at desc, job_id asc`。先頭の `_id` が対象の `job_id` と一致するか。`crawl` ジョブだけ実行する。検索の部分的な失敗(3.2)は `Failed`(`latest_for_source=null`)。

**R-8 削除結果(EP-10)**: `mget` `index=<deletions>` `ids=["deletion_result-<job_id>"]`、`_source_includes=[record_type, status, reason, reason_detail, forced, target_count, denominator, deleted_count, ended_at]`。`record_type=deletion_result` でなければ「記録なし」。文書の `Failed`(3.2)は「記録なし」と読まない(`unavailable.deletion.current`)。

**R-9 件数**: `msearch`(サブ要求ごとに成否が分かれる)。

| 用途 | 対象 | 条件(`size: 0`、`track_total_hits: true`) |
| --- | --- | --- |
| EP-01 の行の `document_count` | 検索インデックス | `terms` クエリ(`source_id` の一覧)+ `terms` 集計(`source_id`、`size` はソース数)。バケットのないソースは `0` |
| EP-02 の `index.document_count`、EP-11 の `document_count` | 検索インデックス | `term source_id`(`index_status` は問わない。AAPI-P-23) |
| EP-11 の `tab_counts.skipped`・`oversize` | `loreley-jobs` | `record_type=skip` / `oversize`、`term source_id` |
| EP-11 の `tab_counts.extract_failed`・`summary_pending` | 検索インデックス | `term source_id` + `term index_status=extract_failed` / `term summary_status=pending` |

EP-11 は、要求されたタブの件数を一覧(R-10)の `total` から取り、他の 3 タブと `document_count` を `msearch` で取る(件数の食い違いを避けるため)。**失敗の帰属**: EP-01 の件数は 1 つのサブ要求が全行を担うので、失敗は全行の `unavailable.document_count`。EP-11 の `tab_counts.<タブ>`・`document_count` は行に属さないので、サブ要求ごとの失敗は最上位の `unavailable` のそのキー(5.8)。

**R-10 X1 の一覧(EP-11)**: 並び・出所・`_source` はタブごと(B 6.1 の表に従う)。共通の形は R-6 と同じ(`from`・`size`・`track_total_hits`・並べ替え+ ID)。

| タブ | 索引 | フィルタ | 既定の並び | `_source` の項目 |
| --- | --- | --- | --- | --- |
| `skipped` | `loreley-jobs` | `record_type=skip`、`source_id` | `last_skipped_at desc` → `document_id asc` | `document_id`・`external_id`・`stage`・`reason`・`attempts`・`consecutive_skips`・`first_skipped_at`・`last_skipped_at`・`last_job_id` |
| `extract_failed` | 検索インデックス | `source_id`、`index_status=extract_failed` | `last_seen_at desc` → `document_id asc` | `title`・`external_id`・`mime_type`・`size`・`source_updated_at`・`last_seen_at`(`document_id` は `_id`) |
| `oversize` | `loreley-jobs` | `record_type=oversize`、`source_id` | `last_detected_at desc` → `document_id asc` | `document_id`・`external_id`・`detected_by`・`size`・`first_detected_at`・`last_detected_at`・`last_job_id` |
| `summary_pending` | 検索インデックス | `source_id`、`summary_status=pending` | `indexed_at desc` → `document_id asc` | `title`・`external_id`・`mime_type`・`source_updated_at`・`indexed_at` |

`sort` の指定は B 2.1 のとおり各タブの 1 項目だけで、上の既定の項目を昇順にするか降順にするかだけを受ける。

**R-11 `existence`(EP-11 の `skipped`)**: 検索インデックスに `ids` クエリ(`values` はそのページの `document_id`。最大 100 件)、`size` はその件数、`_source: false`、`track_total_hits: false`。返った `_id` の集合にあれば `existing`、なければ `new`。`document_id` が読めない行は `unknown`。 R-11 は 1 回の `ids` クエリなので、失敗(部分的な失敗を含む)はページの全行の `unavailable.existence` になる(5.6・5.8)。

**R-12 クラスタ情報(EP-12)**: 3.4。

### 3.4 `cluster.health`・`cat.*`(EP-12。AAA-P-9)

呼び出しは**逐次で、最初の失敗で打ち切る**(どれかが失敗したら全体を 503。B 7.1)。

| 呼び出し | 指定 | 使う項目 |
| --- | --- | --- |
| `cluster.health` | なし(`wait_for_*` は付けない) | `cluster_name`・`status`・`number_of_nodes`・`active_shards`・`relocating_shards`・`initializing_shards`・`unassigned_shards`(いずれも標準の項目名。実機では未確認。AAA-U-1) |
| `cat.indices` | `format=json`・`h=index,health,docs.count`・`bytes=b`・`expand_wildcards=all` | `index`・`health`・`docs.count` |
| `cat.shards` | `format=json`・`h=index,shard,prirep,state,node`・`bytes=b` | 同左 |
| `cat.nodes` | `format=json`・`h=name`・`bytes=b` | `name` |

- 選んだ列にバイト量はなく `bytes=b` は効かないが、列を足したときに単位が揺れないよう指定する(導出)。`expand_wildcards=all` は、`cat.shards` がクローズ済み・隠しインデックスを含めて返す(推測。AAA-U-1)のに合わせ、`indices[]` に抜けが出ないようにする(クローズ済みインデックスの件数は `null` で返る。B 7.1)。
- **値は文字列で受けて変換する**: 整数の列は `^[0-9]+$` に一致すれば整数、それ以外(空・`null`・非数)は `null`。`health`・`state`・`prirep` は小文字にし、空は `null`。`prirep` は `p` → `primary`、`r` → `replica`(未知の値は小文字のまま通す)。
- **`shards[].node`**: 未割り当ては `null`。`state=relocating` で値に ` -> ` を含むときは、その前(移動元のノード名)だけを使う(`cat.shards` の表示が `移動元 -> IP ID 移動先` の形になる、という OpenSearch の仕様による推測。B 7.1 の「移動元」と同じ。AAA-U-1)。
- **そろえ方・上限・並び**(B 7.1・AAPI-P-6・P-31): シャード一覧にあってインデックス一覧にないインデックスを `status=null`・`document_count=null` で補う。インデックスは (状態の悪い順 red → yellow → green → その他・`null`、名前の昇順(コードポイント順))に並べ、1,000 件で切り詰めて `truncated`・`total_indices`(補った分を含む切り詰め前の数)を返す。`shards[]` は切り詰め後のインデックスのものだけを、(インデックス名、シャード番号、primary を先、ノード名)の順で返す。`nodes[]` は名前の昇順(並びは B に規定がなく本書の案)。
- `cluster.health` や `cat.*` の応答が期待の形でない(必須の項目がない、型が違う)ときは、503 `unavailable` にし、ログにクラス名と固定の理由名だけを出す(AAA-P-9)。

### 3.5 スキーマ依存の扱い(AAA-P-7)

| 索引 | フィルタ・並べ替え・集計に使う項目(マップ済み。型) | フィルタ・並べ替え・集計に使わず `_source` から読む項目(マップ済みのものも含む。`connector_config` などの object は `enabled: false`、`loreley-jobs` の多くは未マップ) |
| --- | --- | --- |
| `loreley-sources`(`dynamic: strict`) | `source_id`(keyword。並べ替え) | `connector_type`・`status`・`schedule_cron`・`ttl`・`ratio_threshold`・`min_delete_count`・`updated_at`・`connector_config` |
| `loreley-jobs`(`dynamic: false`) | `record_type`・`source_id`・`job_type`・`status`・`job_id`・`document_id`(keyword)、`queued_at`・`finished_at`・`last_skipped_at`・`last_detected_at`(date) | `trigger`・`force_delete`・`rewrite_mode`・`failure_reason`・`failure_detail`・`confirmation`・`registration`・`deletion_summary`・`settings_snapshot`・`warnings`・`finish_notice`・`stage`・`reason`・`attempts`・`consecutive_skips`・`external_id`・`size`・`detected_by`・`lease_expires_at`・`acquired_at`(後 2 つはマップ済みだが `mget` で読むだけ) |
| `loreley-deletions` | (ID の取得だけ) | `status`・`reason`・`reason_detail`・`forced`・`target_count`・`denominator`・`deleted_count`・`ended_at` |
| 検索インデックス(`dynamic: strict`) | `source_id`・`index_status`・`summary_status`・`document_id`(keyword)、`last_seen_at`・`indexed_at`(date)、`_id` | `title`・`external_id`・`mime_type`・`size`・`source_updated_at` |

- 索引のスキーマを変えると、本書のクエリが動かなくなる(例: 並べ替えに使う項目が未マップになる)。**契約テスト**: `infra/opensearch/schema/*.json` を読み、上の表の「マップ済み」の項目が、期待の型(keyword・date)でマップされていることを確かめる(11章)。スキーマの変更時にテストが落ちるので、本書の更新漏れに気づける(導出)。
- 検索・フィルタに使えない項目(`failure_reason` など)での絞り込みや並べ替えは、本書の範囲(B の EP)に要らない。必要になったときは、スキーマの変更とあわせて検討する。

### 3.6 検索インデックスの読み取り条件(indexer-architecture U-30 への回答。AAA-P-5)

IA K53(読み取り専用で参照してよい。AAA-K-6)を受けて、具体を次のように決める(案。IA U-30 の「取得条件・API の形」への回答。Indexer 設計への反映は HO-15)。

| 項目 | 決め |
| --- | --- |
| 対象 | **エイリアス**(`SEARCH_INDEX_NAME`)だけ。実体の索引名は使わない |
| 呼ぶ API | `search`・`msearch` だけ(3.2 の許可リスト) |
| 使うフィルタ | `term source_id`、`term index_status=extract_failed`、`term summary_status=pending`、`ids`(`_id`) |
| 読む項目 | 3.3 の R-9〜R-11 の表の項目だけ。**`content`・`summary`・`url`・`path`・ハッシュ類は読まない**(`_source` で限定) |
| 件数 | 1 回の取得は最大 100 件(`items_per_page` の上限。X1 の一括検索も同じ)。`from + size` ≤ 10,000 |
| 数え方 | `index_status`・`summary_status` を問わない(登録文書数。AAPI-P-23)。`extract_failed` の件数と一覧は `index_status=extract_failed`(IA E-44)、要約未生成は `summary_status=pending` |
| しないこと | `scroll`・PIT・`_count` の多用・集計での本文の読み取り・検索ランキングの利用 |

### 3.7 OpenSearch クライアントの設定(AAA-P-8)

値(タイムアウト 10 秒・再試行 2 回)は承認済みの案(A 5.6。BAPI-P-12。ゲート2)。**再試行の条件**(`retry_on_timeout=False`、接続エラーの再試行、`retry_on_status` の 5 値)は BAPI-P-12 の明確化分で、**承認済みの案(ゲート3。2026-11-23)**。2 つのクライアントを起動時に作る(8.4)。ライブラリの挙動は opensearch-py 3.2.0 のソースで確認した(12.1)。

| 項目 | 読み取り用 | プローブ用(`cluster.health` だけ。6.2) |
| --- | --- | --- |
| `timeout`(接続・読み取りそれぞれの上限) | `OPENSEARCH_REQUEST_TIMEOUT_SECONDS`(既定 10 秒) | `HEALTH_PROBE_TIMEOUT_SECONDS`(既定 3 秒) |
| `max_retries` | `OPENSEARCH_MAX_RETRIES`(既定 2) | 0 |
| `retry_on_timeout` | `False`(A 5.6: 読み取りのタイムアウトは再試行しない) | `False` |
| `retry_on_status` | `(429, 500, 502, 503, 504)`(A 5.6 の「429・5xx」より狭く、再試行の意味がある 5 値に限る。501・505 などの 5xx は再試行しない。案) | `()` |
| `pool_maxsize` | 16(`opensearch` の枠と同じ。8.1) | 8 |
| 認証・TLS | `OPENSEARCH_USERNAME`・`PASSWORD`・`VERIFY_CERTS`・`CA_CERTS_PATH`(7.2) | 同じ |
| ノードの探索(sniff) | しない | しない |

- **接続エラー(`ConnectionError`)は、`max_retries` まで必ず再試行される**(opensearch-py の挙動。`transport.py`)。`ConnectTimeoutError`(接続のタイムアウト)も `ConnectionError` として扱われるので再試行の対象になる。読み取りのタイムアウト(`ConnectionTimeout`)は `retry_on_timeout=False` で再試行されない。再試行の間に待ち時間を置く処理は確認できなかった。
- `timeout` は urllib3 では接続と読み取りそれぞれの上限になる(1 回の試行の最悪は両方の合計)。

---

## 4. Crawler 連携

### 4.1 クライアントの設定(AAA-P-10)

承認済みの値(A 5.6。BAPI-P-12。ゲート2)を、urllib3 の設定に落とす。実装の流儀は Crawler の Indexer クライアント(CM-P-29。`apps/crawler/.../indexer_client/http_client.py`)と同じ。

| 項目 | 決め |
| --- | --- |
| ライブラリ | urllib3(`PoolManager`。スレッドから使える)。使ってよい場所は Crawler クライアントと HTTP のプローブだけ(A 3章。`urllib3.exceptions` の型だけは OpenSearch の例外の分類にも使う。2.3) |
| タイムアウト | `Timeout(connect=<CRAWLER_CONNECT_TIMEOUT_SECONDS>, read=<CRAWLER_RESPONSE_TIMEOUT_SECONDS>)`(既定 3 秒・60 秒。承認済みの案。仮値。CAPI-U-10)。`read` は 1 回の受信ごとの待ち(応答が少しずつ届き続けると超えうるが、Crawler は応答を 1 回で返す。導出) |
| 再送 | **しない**(`retries=False`。接続の確立の失敗も含めて Admin API は再送しない。A 5.6。冪等でない API を含むため) |
| リダイレクト | **追従しない**(`redirect=False`)。3xx は契約外として 502 `crawler_error`(B 9.1) |
| 接続の再利用 | **しない**(リクエストごとに新しい接続。`Connection: close`)。理由: 使い回した接続が相手に閉じられていたときの失敗は、「送る前」か「送った後」かが区別できず、起動系の結果判定があいまいになる。管理操作の頻度は低く、内部ネットワークなので接続のコストは無視できる(導出)。実装で実際に新しい接続になるかは確認する(AAA-U-4) |
| 本文 | UTF-8 の JSON(`Content-Type: application/json`)。数値の NaN・Infinity は出さない(`allow_nan=False`)。本文を読まない API(取消・ロック解放・削除ジョブ起動)には付けない(B 9.1) |
| 応答の読み取り | 本文は 1 MiB まで読む(Crawler の正常な応答は小さい。超えたら 502 `crawler_error`。導出)。JSON として読めない・オブジェクトでない・`error.code` がない本文は 502 |
| ログ | 呼び出しごとに、ルートのテンプレート・結果の区分・所要時間だけを DEBUG・INFO に出す。ID を含むパス・本文・Crawler の `message` は出さない(8.5) |

### 4.2 呼び出しの手順

1. 検証済みの入力から固定の経路と本文を組み立てる(4.8)。
2. 1 回だけ送る(再送しない)。
3. 例外なら 4.3 で 503 / 504 に分類して返す。
4. ステータスを見る: その API の成功のステータス(B 9.2。EP-03 は 200・201、EP-04・08 は 200、EP-05・06 は 202、EP-07 は 200・202)なら本文を DTO に変換して返す。**期待以外の 2xx は契約外として 502**(成功の本文が読めないときも 502。操作は実行済みの可能性がある。B 10.2 の「契約外の応答」と同じ扱いで、画面は状態を確認する)。
5. エラーなら `error.code` と `details` で 4.4 の写像表に当てはめる。

### 4.3 例外の分類(接続前の失敗 = 503、送信後の応答喪失 = 504。AAA-P-11)

urllib3 2.8.0 の例外の継承(`NewConnectionError` は `ConnectTimeoutError` の子。`NameResolutionError` は `NewConnectionError` の子。ソースで確認)に合わせ、**狭いほうから順に判定する**。

| 順 | 例外 | 送ったか | Admin API の応答 | 補足 |
| --- | --- | --- | --- | --- |
| 1 | `NameResolutionError` | 送っていない | 503 `crawler_unreachable` | 名前解決の失敗 |
| 2 | `NewConnectionError` | 送っていない | 503 `crawler_unreachable` | 接続拒否・到達不能。**起動時の回復中を含む**(4.7) |
| 3 | `ConnectTimeoutError`(上の子を除く) | 送っていない | 503 `crawler_unreachable` | 接続のタイムアウト |
| 4 | `SSLError`(`HTTPError` の直接の子。`ProtocolError` ではない) | 送っていない(接続の確立中の失敗) | 503 `crawler_unreachable` | TLS のハンドシェイク・証明書の検証の失敗。MVP は `CRAWLER_URL` が `http` 限定(7.3)なので通常は起きない(AAA-P-41) |
| 5 | `ReadTimeoutError` | 送った | 504 `crawler_response_lost`(`outcome_unknown=true`) | 応答のタイムアウト |
| 6 | `ProtocolError`(切断・不完全な応答を含む)、その他の `urllib3.exceptions.HTTPError` | 送った可能性がある | 504 `crawler_response_lost` | 安全側(結果不明)に倒す |
| 7 | `urllib3` 以外の想定外の例外 | — | 500 `internal_error`(8.5) | 不具合。握りつぶさない |

接続を使い回さない設計(4.1)なので、1〜3 は確実に「送る前」の失敗になる(導出。実機で確認。AAA-U-4)。4 は接続の確立中の失敗として「送る前」に分類する。ただし、送った後の TLS の失敗も同じ型になりうるため、`https` を許す将来は分類を見直す(AAA-U-9)。

### 4.4 エラー写像の実装方針(結果の正本は B 2.6・9.2。AAA-P-12)

- **表駆動**: 写像は `(API, ステータス, code, 項目)` から Admin API の応答への 1 つの表(データ)として持ち、API ごとの分岐を書かない(B 9.2 の表と 1 対 1 にして保守する。D)。
- **未知のもの**: 表にない `code`・ステータス・形は 502 `crawler_error`。`code` が B 2.3 の Crawler 由来の code に含まれても、その API で想定されない組み合わせは 502。
- **400 `invalid_request` の分岐**(B 2.6): `details.errors[].field` が `connector_type`・`connector_config`・`ttl`・`ratio_threshold`・`min_delete_count`・`schedule_cron` のものが 1 件以上あれば、**そのものだけ**を Admin の項目名に写して 400 にする(`ttl` → `ttl_days` または `ttl_seconds`(送ったほう)、`ratio_threshold` → `ratio_threshold_percent`)。それ以外の項目(`body`・`unknown_field`・`read_only`・`source_id`)だけなら 502。`field` が `job_id` の 400 と 404 `not_found` は、**EP-07 では 404 `job_not_found`**(AAPI-P-39。下記)。
- **EP-07 の `job_id` 起因の写像**(AAPI-P-39): `%`・`?`・`#`・`.` などを含む `job_id` は Admin API の検証を通り、全文字エンコードして送る(4.8)。Crawler がパスとして扱えずに返す 400(項目 `job_id`)・404 `not_found` は、Crawler が生成する ID の形ではない = 存在しない ID と同義なので 404 `job_not_found` に写す。`source_id` は文字種を検証済みなので、同じ応答は 502(B 2.6)。実 uvicorn の挙動は未確認(AAPI-U-12)。
- **`existing_job` の取り込み**(409 `lock_held`・`lock_in_use`): Crawler の `details.existing_job` から `job_id`・`job_type`・`status`・`trigger`・`lease_expires_at` だけを、文字列または `null` であることを確かめて取り込む(それ以外の項目は捨てる)。`lease_expires_at` は文字列ならそのまま通す(番兵値 `0001-01-01T00:00:00.000Z` も変換しない。I-73)。`details.status`(`source_already_exists`・`job_already_finished`)も文字列または `null` だけを通す。
- **`message` は `config_invalid` 以外では読まない**(B 9.1)。応答の `message` は A 5.2 の固定文。

### 4.5 `config_invalid` の分解(実装。規則と例は B 2.5。AAA-P-13)

```python
FIELD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(\[[0-9]+\])?")

def decompose(message):                       # Crawler の message → (field, detail) または None
    if not isinstance(message, str) or len(message) >= 512:
        return None                           # 切り詰めの疑い(512 文字で打ち切られる)
    head, sep, detail = message.partition(": ")      # 最初の「コロン+空白」で分ける
    if not sep or not detail or FIELD.fullmatch(head) is None:   # fullmatch(末尾の改行を許さない)
        return None
    field = "connector_config" if head == "connector_config" else "connector_config." + head
    return field, detail
```

- 成功: `details.errors=[{field, reason:"config_invalid", detail}]`、`details.crawler_message` に元の `message`。失敗: `errors=[]`、`crawler_message` だけ(画面が上部のアラートにする)。
- `re.fullmatch` を使う理由: `re.match` と `$` では、末尾の改行を含む文字列が一致してしまう(導出)。
- 依存: Crawler の `message` の形式(「項目名(配列は添字): 違反の種類」)と日本語の固定文。壊れたときは分解不能に落ちて画面のフォールバックになり、操作は止まらない(AAPI-U-2)。`crawler_message` は Crawler が入力値・errno・パスを含めない固定文なのでそのまま載せる(B 2.5)。念のため 512 文字を超える場合は切り詰める。

### 4.6 409 の付随情報(AAA-P-15)

`lock_held`(EP-05・06)・`lock_in_use`(EP-08)の応答に付ける `lock_state` は、Crawler の 409 を受けた後に、R-4(ロック文書)→ R-5(`lock.job_id` のジョブ記録)の順に読み、5.1 で導出する(ロックから始める。B 2.9 の順序)。**読み取りが失敗しても `lock_state=unknown` にするだけで、409 のステータス・`existing_job` は変えない**(付随情報のために失敗にしない)。OpenSearch が遅いと 409 の応答が遅れる(最大でも 8.3 の見積もり)。

### 4.7 起動時の回復中・起動直後(B 9.1。AAA-P-12)

Crawler は起動時の回復が終わるまで受付を始めず、接続できない(crawler-api 3.1)。Admin API からは 4.3 の 2(接続拒否)に見え、503 `crawler_unreachable`(`retryable=true`)になる。専用の分岐は置かない。最大約 3 分(Crawler の `HEALTHCHECK` の `--start-period` 180 秒。仮値)続き、終われば自然に応じる。実機でどう見えるか(接続拒否か名前解決の失敗か)は AAA-U-4(AAPI-U-1)。

### 4.8 固定の経路とパスの組み立て(AAA-P-14)

Crawler に送る経路は次の 6 つだけ(B 1.1。ほかに 6 章のプローブの `GET /healthz`)。

| EP | メソッド | パスのテンプレート |
| --- | --- | --- |
| EP-03 | POST | `/sources` |
| EP-04 | PUT | `/sources/{source_id}` |
| EP-05 | POST | `/sources/{source_id}/delete-jobs` |
| EP-06 | POST | `/sources/{source_id}/crawl-jobs` |
| EP-07 | POST | `/jobs/{job_id}/cancel` |
| EP-08 | DELETE | `/sources/{source_id}/lock` |

- **`source_id`・`job_id` は全文字をパーセントエンコード**してから埋める(`urllib.parse.quote(value, safe="")` の結果の `.` を `%2E` に置換する。R1 I-1・R2 I-1。AAPI-P-24。承認済みの案(ゲート3。2026-11-23))。理由: (1) `job_id` は検証が緩く(`%`・`?`・`#`・`.` を含みうる)、エンコードしないとパスが崩れ、固定の経路にならない。(2) `quote(safe="")` は `.` を符号化せず、urllib3 の `PoolManager.urlopen` は URL を `parse_url` で正規化してドットセグメントを除去する(urllib3 2.8.0 で確認: `job_id=".."` は `/jobs/../cancel` が `/cancel` として、`"."` は `/jobs/cancel` として送られる。`%2E%2E`・`%2E` は保持される)。別の経路に落ちると「固定の 6 経路だけ」(AAA-K-7)が崩れるため、`.` も `%2E` にする。`source_id` の `.` も `%2E` になる(Crawler が復号して受ける想定。実機未確認。AAA-U-4)。代案: `.`・`..` だけの `job_id` を B 2.12 の検証で拒否する(AAPI-P-24 の検証規則の変更になる。ゲート3(G3-6)で採らないと承認済み)。
- ベース URL は `CRAWLER_URL`(7章)。末尾のスラッシュは取り除き、パスのテンプレートを足す。

---

## 5. 導出ロジック

各導出は純粋な関数にする(入力は読み取りの結果と現在時刻、出力は B の応答項目。D)。5.10 に、B の応答項目との対応表がある。

### 5.0 共通の読み方(AAA-P-16)

- **現在時刻 `now`** は、1 回のリクエストの先頭で 1 回だけ取り(UTC)、そのリクエストの導出すべてに使う(`fetched_at`・`checked_at`・`lease` の判定・`just_acquired`)。テストでは差し替える(D)。Crawler・Indexer・Admin API は同じホストで時計を共有する前提(単一ホスト。SD §4.2)。
- **日時の読み方**: ISO 8601 の文字列でタイムゾーン(`Z` またはオフセット)を持つものだけ。オフセットのない値・日時として読めない値・UTC にして表せる範囲を超える値は「読めない日時」(crawler-architecture 2.5)。出力は UTC ミリ秒(`2026-11-22T01:02:03.456Z`。ミリ秒未満は切り捨て)。
- **数値・文字列・真偽値の読み方**: 整数は `bool` を除く整数、小数は有限の整数または浮動小数。型が違う値は「読めない値」。
- **読めない値の扱い**(AAA-P-25): ジョブ記録・削除記録・ロック文書など、Crawler・Indexer が書いた値で読めないものは、**その項目を `null` にする**(DTO の型が `string` などでも)。例外は 5.8 の `malformed`(EP-02 の設定項目だけ。`unavailable` に載せる)。判定に使う値(`status`・`lease_expires_at` など)が読めないときの扱いは各項で決める。B 2.2・2.11・EP-10 が `null` を許す型を定めた(AAPI-P-25): `JobBrief` の `status`・`job_type`・`trigger`・`queued_at`、EP-10 の `registration` の件数・`partial`・`phase`。**`job_id`・`source_id` は `null` にしない**(`job_id` は文書の `_id`、`source_id` は集計のバケットのキー・要求の値・`_source` の順で補う)。**`status` が読めない(`null`)ジョブは `stalled=false`・`cancellable=false`** とし、画面は `null` を「—」として扱う(B 2.2)。

### 5.1 `lock_state` の 7 値(B 2.9。AAA-P-17)

**ロック文書から始め、ジョブ記録は `lock.job_id` で引く**(読む順序はロック文書 → ジョブ記録。B 2.9)。ジョブ記録は R-5(`mget`。リアルタイム)で読むので、検索の遅れによる食い違いは出ない。

| 順 | 条件 | `lock_state` |
| --- | --- | --- |
| 1 | ロック文書の読み取りが失敗(`mget` 全体の失敗、またはその文書の `docs[i].error`・`found` が真偽値でない。3.2) | EP-02 は `lock=null`(`unavailable.lock`)。409 の付随情報は `unknown`(4.6) |
| 2 | ロック文書がない(`found=false`、または `record_type` が `lock` でない) | `none` |
| 3 | ロック文書が読めない形(オブジェクトでない) | `unknown` |
| 4 | `job_id` が文字列で空でなく、ジョブ記録の読み取りが失敗 | `unknown` |
| 5 | `job_id` が欠落・文字列でない・空、またはジョブ記録がない(`record_type=job` でない) | `acquired_at` が読めて `now - acquired_at < 猶予`(7章。既定 60 秒)なら **`just_acquired`**、それ以外(猶予を超えた、`acquired_at` が読めない)は **`orphan`**(猶予の境界はちょうど `猶予` で `orphan`) |
| 6 | ジョブの `status` が `queued`・`running`・終端の 4 値のいずれでもない、または `job_type` が `crawl`・`source_delete` でない(読めない) | `unknown` |
| 7 | `status` が終端(`succeeded`・`partially_succeeded`・`failed`・`cancelled`) | `orphan` |
| 8 | `status=queued` | `held_crawl` / `held_delete`(`job_type` による。`lease_expires_at` は見ない) |
| 9 | `status=running`。`lease_expires_at` が読めて `now < lease_expires_at` | `held_crawl` / `held_delete` |
| 10 | `status=running` で、`lease_expires_at` が `null`・読めない・`now ≥ lease_expires_at` | `lease_expired` |

- `just_acquired` と `orphan` は取得から猶予で分かれ、排他(B 2.9)。猶予は Crawler の「受付の途中のロックとみなす `acquired_at` の長さ」と同じ値でなければならない(5.9)。
- `lock.job`(`ExistingJob`)は、`job_id` が読めるとき `{job_id, job_type・status・trigger(ジョブ記録から。なければ null), lease_expires_at(ロック文書から。読めなければ null)}`。`job_id` が読めなければ `null`。`lock.acquired_at` は読めなければ `null`。

### 5.2 `stalled`・`cancellable`(B 2.9。定義は承認済みの案: AAPI-P-4。判定手順は承認済みの案(ゲート3)。AAA-P-18)

**定義(AAPI-P-4。ゲート1)**: 実行中(保存上 `running`)で、リース期限を過ぎている。期限が `null`・形式不正も過ぎたとみなす。ロック文書がない `running` も `true`(推測。AAPI-P-27・AAPI-U-9。実機での確認は AAA-U-5)。

**偽陽性を避ける手順**(R1 S-9。ロックの解放・ジョブの終了の途中を `stalled` と誤判定しない):

`running` と読めたジョブ行 `J` ごとに:

1. `J` のソースのロック文書を R-4 で読む(行ごとにではなく、対象ソースをまとめて 1 回の `mget`)。**読み取りに失敗したら `stalled=null`**(その行の `unavailable` の該当キー(EP-01 は `last_crawl.stalled`・`delete_job.stalled`、EP-09 は `stalled`)。単一の応答は最上位。理由は 5.8)。`mget` は文書単位に失敗しうるので、失敗した文書のソースの行だけが `null` になり、他の行は影響を受けない。`mget` 全体が失敗したときは、`running` を持つ全行に同じキーが付く(5.8)。
2. ロック文書の `job_id` が `J.job_id` と一致するなら: `now < lease_expires_at`(読めた場合)なら `false`、それ以外(`null`・読めない・期限切れ)なら `true`。
3. **ロック文書がない、または別のジョブのもの**なら、**確認読み**をする: ロック文書(R-4)→ ジョブ記録(R-5。リアルタイム)の順に 1 回読み直し、(a) ジョブがもう `running` でなければ `false`(行の `status` も読み直した値にする)、(b) ロックが一致するようになっていれば手順 2、(c) ロックが一致せずジョブがまだ `running` なら `true`。確認読みが失敗したら `null`。

- 手順 3 が要る理由: 一覧では、どの行が `running` か(= どのロックを読むべきか)がジョブを読むまで分からないため、ロックを先に読めない。ジョブを検索で読む(最大約 1 秒古い)間にジョブが終了してロックが消えていると、ロックなしの `running` に見えて偽陽性になる。**ロックの不一致を見たときに、ロック → ジョブの順で新しく読み直せば**、ジョブは `running` → 終端の順にしか変わらず、ロックはジョブの最終状態の記録の後にしか消えない(crawler-architecture 5.5)ため、読み直しで `running` かつロックなしなら本当に止まっている(導出)。B 2.9 の「ロック文書 → ジョブ記録」は、この「読み直しの順序」と `lock_state` の導出(5.1)で満たす(B 2.9 に補足済み。AAPI-P-27)。
- 管理者のロック解放の途中(ロック削除後・ジョブが `failed` になる前)は、短い間 `true` になる。解放の操作の直後なので許容する(導出)。
- 読み直しは、不一致の行があるときだけで、ふつうは起きない(性能。AAA-U-7)。
- **`cancellable`**: `job_type=crawl` かつ(`status=queued`、または `status=running` で `stalled=false`)。`stalled=null` のとき `false`(安全側。AAPI-P-27)。`source_delete`・終端・`stalled=true` は `false`。
- `JobBrief.stalled` は `status=running` 以外(`status` が読めず `null` の場合を含む)では `false`(読み取りなし)。`cancellable` も `status` が読めなければ `false`(5.0)。EP-10 の `lease_expires_at` は、`J` が `running` で、ロック文書が一致し日時として読めるときだけその値(それ以外 `null`)。

### 5.3 `latest_for_source`・`rerunnable`・`rerun_blocked_reason`・`cancel_after_finish_notice`(EP-10。AAA-P-19)

- **`latest_for_source`**: `job_type=crawl` のとき R-7 の先頭の `_id` と `job_id` を比べる(一致で `true`)。それ以外(`source_delete`・読めない `null`)は `false`(読み取りなし)。読み取りの失敗は `null`(`unavailable.latest_for_source`)。
- **`rerunnable`・`rerun_blocked_reason`**(画面の出し分け用。サーバーでは強制しない。B 2.9)を、次の順に評価し、最初に決まったところで終える(AAA-P-19)。

| 順 | 条件 | `rerunnable` | `rerun_blocked_reason` |
| --- | --- | --- | --- |
| 1 | `job_type` が `crawl` でない(`source_delete` と、読めない `null` を含む。確かめられないものは再実行を出さない安全側。AAA-P-44) | `false` | `not_crawl` |
| 2 | `status=running` で `stalled=true` | `false` | `stalled` |
| 3 | `status=running` で `stalled=null` | `null` | `null`(`unavailable.rerunnable` に `stalled` の失敗の理由) |
| 4 | `status` が `failed` でない(`queued`・`running`・終端のうち `failed` 以外。読めない `null` を含む。安全側) | `false` | `not_failed` |
| 5 | `latest_for_source=false` | `false` | `superseded` |
| 6 | `latest_for_source=null` | `null` | `null`(同上) |
| 7 | データソースの設定(R-2)の読み取りが失敗 | `null` | `null`(`unavailable.rerunnable`) |
| 8 | 設定がない(削除済み。`found=false`) | `false` | `source_missing` |
| 9 | 設定の `status=deleting` | `false` | `source_deleting` |
| 10 | 上のいずれでもない | `true` | `null` |

  順 8 の `source_missing` は B の専用値(AAPI-P-41。案。削除済みのソースを「削除中」と誤って示さないため)。順 7(設定の読み取りの失敗で `rerunnable=null`)は B 2.9・EP-10 の `rerunnable=null` の条件(AAPI-P-41)。
- **`cancel_after_finish_notice`**: `status=cancelled` かつ `finish_notice.send_started_at` が読める日時(null でない)なら `true`、それ以外 `false`(CAPI-U-6)。

### 5.4 `JobBrief` の各項目・`registration.phase`・`deletion.*`(EP-10。AAA-P-20・P-44)

**`JobBrief` の各項目の導出**(AAA-P-44。案。B 2.11 の型と 5.0 の「読めない値は `null`」に従う。許される値の列挙(B 2.11)にない値は読めない値として `null` にし、未知の値を通さない):

| 項目 | 元(ジョブ記録) | 規則 |
| --- | --- | --- |
| `job_id` | 文書の `_id` | `null` にしない |
| `source_id` | `source_id` | 文字列でなければ、集計のバケットのキー・要求の値で補う(`null` にしない。5.0) |
| `job_type` | `job_type` | `crawl`・`source_delete` 以外(欠落・型違い・未知の値)は `null` |
| `trigger` | `trigger` | `manual`・`schedule` 以外は `null` |
| `status` | `status` | `queued`・`running`・`succeeded`・`partially_succeeded`・`failed`・`cancelled` 以外は `null`(このとき `stalled=false`・`cancellable=false`。5.0) |
| `force_delete`・`rewrite_mode` | 同名 | 真偽値でなければ `null`(`source_delete` は記録にないので `null`) |
| `queued_at`・`started_at`・`finished_at` | 同名 | 読める日時を UTC ミリ秒に。欠落・読めない値は `null`(未到達の `started_at`・`finished_at` も `null`) |
| `failure_reason` | `failure_reason` | **`status=failed` のときだけ**、空でない文字列ならそのまま(未知のコードも解釈しない。AAPI-U-3)。`failed` 以外、文字列でない・空は `null` |
| `stalled`・`cancellable` | 5.2 | 5.2 |

- **`registration`**: `source_delete` と、ジョブ記録に `registration` がないとき(実行待ち)は `null`。あるときは、B の項目(`enumerated_count`・`created_count`・`updated_count`・`unchanged_count`・`skipped_count`・`oversize_count`・`error_count`・`invalid_id_count`・`partial`)だけを通す(保存値のまま。読めない件数・`partial` は 5.0 の規則で `null`。B の型が `null` を許す。AAPI-P-25)。
- **`registration.phase`**(承認済みの案。AAPI-P-4。ゲート1): `partial=false` → `final`、`partial=true` かつ `status` が `queued`・`running` → `in_progress`、`partial=true` かつ終端 → `incomplete`。`partial` が真偽値でないとき、または `partial=true` で `status` が読めない(`null`)ときは `null`(B の型が `null` を許す。AAPI-P-25。B 2.2)。
- **`deletion`**: `source_delete` は `null`、`crawl` は常にオブジェクト(B 5.2)。
  - `summary`: ジョブ記録の `deletion_summary` から B の項目(`status`・`reason`・`forced`・`target_count`・`denominator`・`deleted_count`・`enumerated_count`・`n_seen`・`e_missing`・`finish_received_at`・`deletion_started_at`・`finished_at`・`observed_at`)だけを通し、なければ `null`。
  - `confirmation`: `confirmed`・`unconfirmed`・`unknown` の文字列。ないとき `null`。
  - `current`・`current_state`・`fetched_at`: `status=queued` のジョブは読まず `current_state=not_found`・`current=null`・`fetched_at=null`(AAPI-P-29)。それ以外は R-8 を読み(`fetched_at` は読み取りを始めた `now`)、見つかれば `available`、なければ `not_found`、失敗なら `unavailable`(`current=null`、`unavailable.deletion.current`)。
  - `settings`: ジョブ記録の `settings_snapshot` から `ttl`・`ratio_threshold`・`min_delete_count` を読み、5.7 で `ttl_seconds`・`ratio_threshold_percent` に変換する。スナップショットがない(開始前に失敗)ときは `null`。項目ごとに読めなければその項目 `null`。
- **`warnings`**: ジョブ記録の配列のうち、オブジェクトで `code` が文字列のものだけを、そのまま通す(コード名・項目は Crawler 設計の案(CA-P-73)で、解釈しない。AAPI-U-3)。配列でなければ `[]`。`failure_detail` は文字列ならそのまま、そうでなければ `null`(Crawler が切り詰め・エスケープ済み。CA-P-45・48)。

### 5.5 `last_crawl`・`last_completed_at`・`delete_job`(EP-01・02。承認済みの案: AAPI-P-4。クエリ形は承認済みの案(ゲート3)。AAA-P-21)

R-3 の結果から作る。

- `last_crawl`: `crawl.latest` のジョブ(なければ `null`)。`JobBrief` の `stalled`・`cancellable` は 5.2。
- `last_completed_at`: `crawl.completed.at.value`(エポックミリ秒)を UTC ミリ秒の文字列に。なければ `null`。`succeeded`・`partially_succeeded` の `finished_at` の最大値(AAPI-P-4。AF-U-9)。
- `delete_job`: **ソースの `status=deleting` のときだけ** `delete.latest` のジョブ(`JobBrief`。`stalled` は 5.2)、なければ `null`。`active` のソースは常に `null`。
- R-3 は 1 回の検索なので、失敗したら全行が失敗する。EP-01 は全行の `last_crawl`・`last_completed_at` を `null` とし、**各行の `unavailable`** に `last_crawl`・`last_completed_at` を付ける。`delete_job` は `status=deleting` の行だけ `null`+キー(`active` の行は値がないので `null`・キーなし)。理由は 5.8(B 3.1・AAPI-P-42)。EP-02 は最上位の `unavailable`(`last_crawl`・`last_completed_at`・`delete_job`)。

### 5.6 `existence`(EP-11 の `skipped`。承認済みの案: AAPI-P-5。実装形はゲート3で承認(2026-11-23)。AAA-P-22)

ページ内の `document_id` を R-11(1 回の `ids` クエリ。最大 100 件)で検索インデックスに問い合わせ、見つかれば `existing`、なければ `new`。`document_id` が読めない行は `unknown`。R-11 が失敗したらページ全件を `unknown` にし、**全行の `unavailable`** に `existence` の理由を付ける(ページ全体は返す。R-11 は 1 回の一括検索なので、行ごとに成否が分かれることはない。AAPI-P-42)。スキップ記録の `document_id` は検索インデックスの `_id` と同じ算出値(interface 5.2。実機での一致の確認は AAPI-U-7)。

### 5.7 TTL・しきい値の変換(B 2.8。承認済みの案: AAPI-P-14。小数の扱いの細部は承認済みの案(ゲート3)。AAA-P-23)

十進数(`Decimal`)で計算し、浮動小数の誤差を出さない。

```python
def percent_to_ratio(p):     # 要求 → Crawler。p は JSON の数値(bool は検証済みで来ない)
    d = Decimal(repr(p)) if isinstance(p, float) else Decimal(p)
    # 小数第 3 位以下があれば format(B 2.4)、範囲は 0 以上 100 未満(range)。検証は d.normalize().as_tuple().exponent >= -2 など
    return float(d / 100)   # 例 0.29 → 0.0029、20 → 0.2

def ratio_to_percent(r):     # 保存値 → 応答。r は int または float(有限)
    d = Decimal(repr(r)) if isinstance(r, float) else Decimal(r)
    v = d * 100             # 例 0.29 → 29。浮動小数なら 28.999999999999996 になるところ
    return int(v) if v == v.to_integral_value() else float(v)   # 整数値は整数で出す(20)
```

- `repr(float)` は、15 桁以内の十進表記なら入力どおりの十進表記に戻る(最短表現。導出)。これで、画面で打ち込んだ `0.29` が `0.29` として扱われる。
- 保存値が小数第 3 位以下を持つ(例 `0.12345` → `12.345`)と、応答の `ratio_threshold_percent` は小数第 2 位を超える(AAPI-P-38)。変換はそのまま行い、画面が丸めを確認する(E・F)。
- `ttl_seconds`: `ttl_days × 86,400`(整数。`int64` に収まることを確かめる。`ttl_days` も 1 以上。AAPI-P-37)。応答の `ttl_days` は `ttl_seconds % 86,400 == 0` のときだけ `ttl_seconds // 86,400`、それ以外は `null`。
- 保存値の `ttl`・`min_delete_count` が整数でない、`ratio_threshold` が数値でない場合は 5.8 の `malformed`(EP-02)。EP-10 の `deletion.settings` では項目 `null`。

### 5.8 部分失敗の理由コードの付け方と `malformed` の判定(B 2.2。AAA-P-25)

**理由コード**: 失敗した読み取りの対象と例外から決める。

```python
def reason_of(exc, target):                 # target: "store"(loreley-*)または "search_index"
    if is_timeout(exc):                     # opensearchpy.ConnectionTimeout、または
        return "timeout"                    # ConnectionError で info が ConnectTimeoutError(NewConnectionError を除く)
    return "store_unavailable" if target == "store" else "search_index_unavailable"
```

- **タイムアウトを優先する**(遅いのか止まっているのかを区別する。案)。`opensearchpy` は urllib3 の読み取りのタイムアウトだけを `ConnectionTimeout` にし、接続のタイムアウト(`ConnectTimeoutError`)は `ConnectionError` として扱う(`connection/http_urllib3.py` で確認)ので、`ConnectionError` の `info` も見る。
- `msearch` のサブ要求のエラー(応答の `responses[i].error`)は、`error.type` などを使わず、対象で `store_unavailable` / `search_index_unavailable`。`msearch` 全体が例外なら全サブ要求が同じ理由で失敗。サブ要求の失敗は、そのサブ要求が担う項目に帰属する(行に属さない `tab_counts.<タブ>`・`document_count` は最上位、EP-01 の `document_count` は 1 つのサブ要求が全行を担うので全行。下の「失敗の帰属」)。
- **部分的な失敗**(3.2。AAA-P-39): `timed_out=true` は `timeout`。`mget` の文書単位の `error`・`found` が真偽値でない、`search`・`msearch` の `_shards.failed>0`・形の異常は、`error.type` などを使わず対象別(`store_unavailable` / `search_index_unavailable`)。
- **例外の型の判定に `urllib3.exceptions` を使う**(`failure.py`・`health_probe.py`。AAA-P-40): `opensearchpy.ConnectionError` は元の例外を `info` に持ち、接続のタイムアウト・接続拒否・名前解決の失敗の区別はその型でしかできない。クラス名の文字列比較は、継承(`NewConnectionError` は `ConnectTimeoutError` の子)を表せず、名前の変更に弱いので採らない。
- `TransportError` のうち 400(`RequestError`)は、実装・スキーマの不一致を示すことが多いので、ログに **ERROR** でクラス名・ステータス・`error.type` だけを出す(値・理由文は出さない)。応答の扱いは他の OpenSearch の失敗と同じ(`unavailable`)。

**`unavailable` の位置とキー**(B 2.2・AAPI-P-42。AAA-P-45): 一覧の EP(EP-01・09・11)は**各 `items[i]` に `unavailable`**(常に存在。なければ `{}`)を持ち、キーは**行の中の項目の相対パス**。最上位の `unavailable` は行に属さない項目(EP-11 の `tab_counts.<タブ>`・`document_count`)だけで、EP-01・09 では常に `{}`。単一の応答(EP-02・10・12〜14)は最上位で、キーは応答の項目の正式なパス。**`items[].…` 形式のキーは使わない**。読み方は「`null` でキーあり=取得できなかった」「`null` でキーなし=値がない(未実行・該当なし)、または保存値が読めない(5.0)」。

**キーと理由コードの対応**(AAPI-P-25・P-42)。

| `unavailable` のキー(位置) | 失敗した読み取り | 対象 | 理由コード |
| --- | --- | --- | --- |
| `last_crawl`・`last_completed_at`・`delete_job`(EP-01 は各行。EP-02 は最上位) | R-3 | store | `store_unavailable` / `timeout` |
| `last_crawl.stalled`・`delete_job.stalled`(EP-01 は各行。EP-02 は最上位)、`stalled`(EP-09 は各行。EP-10 は最上位)、`lease_expires_at`(EP-10。最上位) | R-4・R-5(確認読みを含む) | store | 同上 |
| `lock`(EP-02。最上位) | R-4 | store | 同上 |
| `latest_for_source`(EP-10。最上位) | R-7 | store | 同上 |
| `rerunnable`(EP-10。最上位) | `stalled`・`latest_for_source` の失敗、または R-2(状態) | store | 原因と同じ |
| `deletion.current`(EP-10。最上位) | R-8 | store | 同上 |
| `document_count`(EP-01 は各行)、`existence`(EP-11 は各行)、`index.document_count`(EP-02。最上位)、`document_count`・`tab_counts.extract_failed`・`tab_counts.summary_pending`(EP-11。最上位) | R-9・R-11 | search_index | `search_index_unavailable` / `timeout` |
| `tab_counts.skipped`・`tab_counts.oversize`(EP-11。最上位) | R-9 | store | `store_unavailable` / `timeout` |
| (`SourceSettings` の項目名。EP-02。最上位) | 保存値の読み取り | — | `malformed` |

**失敗の帰属**(一覧の EP。AAA-P-45): 失敗は、その読み取りの結果が担う行にだけキーを付ける。

| 読み取り | 失敗の単位 | キーを付ける場所 |
| --- | --- | --- |
| R-3(EP-01) | 1 回の検索 | 全行(`delete_job` は `status=deleting` の行だけ) |
| 件数(EP-01 の R-9) | 1 つのサブ要求が全行を担う | 全行の `document_count` |
| ロック文書の `mget`(R-4。EP-01・09) | 文書単位 | 失敗した文書のソースの行のうち、`running` のジョブを持つ行(EP-01 は `last_crawl`・`delete_job` のうち `running` のもの) |
| 同上の `mget` 全体の失敗 | 全体 | `running` のジョブを持つ全行 |
| 確認読み(R-4 → R-5。5.2) | 確認の対象の行ごと | 失敗した行 |
| R-11(EP-11) | 1 回の一括検索 | 全行の `existence` |
| R-9(EP-11 の `tab_counts.<タブ>`・`document_count`) | サブ要求ごと | 最上位の該当キー(行には付けない) |

**主たる読み取りの失敗は 503**(`unavailable`。B 2.2): EP-01 の R-1、EP-02 の R-2、EP-09 の R-6、EP-10 の R-5(ジョブ記録)、EP-11 の設定の存在確認と R-10、EP-12 の全体。

**`malformed` の判定**(EP-02 の設定項目。AAPI-P-34。AAA-P-25): 保存値(`_source`)が次の条件を満たさない項目は `null` にし、`unavailable.<項目名>=malformed` を付ける。`ttl_days` は `ttl_seconds` から導出するので、`ttl_seconds` が `malformed` なら `null`(キーは `ttl_seconds` だけ)。

| 項目 | 読めるとみなす条件 |
| --- | --- |
| `connector_type` | 文字列 |
| `connector_config` | オブジェクト(中身は見ない。AAPI-P-20) |
| `ttl_seconds` | `bool` でない整数(範囲は見ない) |
| `ratio_threshold_percent` | 有限の整数または浮動小数(範囲は見ない) |
| `min_delete_count` | `bool` でない整数 |
| `schedule_cron` | 文字列または `null`(キーがない場合も `null`として読む。`null` は手動のみで正当な値) |
| `status` | `active` または `deleting` |
| `updated_at` | 読める日時 |
| `source_id` | ドキュメント ID を使う(`_source` の値は見ない) |

### 5.9 `just_acquired` の猶予と Crawler の仮値の同期(AAPI-U-6。AAA-P-24)

- Crawler の「受付の途中のロックとみなす `acquired_at` の長さ」は仮値 60 秒(crawler-architecture 11章)で、実装では環境変数 `LORELEY_CRAWLER_ADMITTING_LOCK_GRACE_SECONDS`(既定 60。`apps/crawler/src/loreley_crawler/config.py` の `Settings`。設計書には名前がない。I-91)。Crawler はこれより新しい `acquired_at` のロックを、ジョブ記録がなくても解放しない(409 `lock_in_use`)。
- Admin API の猶予は、**同じ値でなければならない**。Crawler の猶予が Admin API より長いと、Admin API が `orphan`(解放できる)と表示しても Crawler が 409 `lock_in_use` で拒否する。Crawler の猶予が Admin API より短いと、Admin API が `just_acquired`(待つよう案内)と表示している間に Crawler は解放できる。表示と操作がずれるだけで、データは壊れない(導出。AAA-U-6)。
- **同期の方法**(案): Admin API に環境変数 `LORELEY_API_ADMITTING_LOCK_GRACE_SECONDS`(既定 60)を置き、**compose で Crawler の `LORELEY_CRAWLER_ADMITTING_LOCK_GRACE_SECONDS` と同じ変数から渡す**(cron のタイムゾーンと同じ扱い。A 8。HO-35・HO-44)。Crawler 側の値を Admin API が読む手段はない(Crawler に読み取りの API はない。CAPI-P-16)ため、運用上の同値定義に頼る。

### 5.10 導出と B の応答項目の対応表

| 導出 | B の応答項目(EP) | 入力(読み取り単位) | 定義 |
| --- | --- | --- | --- |
| `lock_state`・`lock.job`・`lock.acquired_at` | `lock.state`・`lock.job`・`lock.acquired_at`(EP-02)、`details.lock_state`(EP-05・06・08 の 409) | R-4・R-5 | 5.1 |
| `stalled` | 行の中の `last_crawl.stalled`・`delete_job.stalled`(EP-01 の `items[]`)、`last_crawl.stalled`・`delete_job.stalled`(EP-02)、行の `stalled`(EP-09 の `items[]`)、`stalled`(EP-10)。失敗のキーは EP-01・09 は行の `unavailable`、EP-02・10 は最上位 | R-4・R-5 | 5.2・5.8 |
| `cancellable` | `JobBrief.cancellable`(EP-01・02・09・10) | 5.2 | 5.2 |
| `lease_expires_at` | `lease_expires_at`(EP-10) | R-4 | 5.2 |
| `latest_for_source` | `latest_for_source`(EP-10) | R-7 | 5.3 |
| `rerunnable`・`rerun_blocked_reason` | 同名(EP-10) | 5.2・5.3、R-2 | 5.3 |
| `cancel_after_finish_notice` | 同名(EP-10) | R-5 | 5.3 |
| `registration.phase`・`registration.*` | 同名(EP-10) | R-5 | 5.4 |
| `deletion.summary`・`confirmation`・`current`・`current_state`・`fetched_at`・`settings` | 同名(EP-10) | R-5・R-8 | 5.4 |
| `warnings`・`failure_detail` | 同名(EP-10) | R-5 | 5.4 |
| `last_crawl`・`last_completed_at`・`delete_job` | 同名(EP-01・02) | R-3 | 5.5 |
| `existence` | 行の `existence`(EP-11 の `items[]`)。失敗のキーは行の `unavailable` | R-11 | 5.6 |
| `document_count`・`tab_counts` | 行の `document_count`(EP-01 の `items[]`。失敗のキーは行の `unavailable`)、`index.document_count`(EP-02)、`document_count`・`tab_counts.*`(EP-11。失敗のキーは最上位) | R-9 | 3.3・5.8 |
| `ttl_days`・`ttl_seconds`・`ratio_threshold_percent` | `SourceSettings`(EP-02・03・04)、`deletion.settings`(EP-10) | 保存値・要求 | 5.7 |
| `unavailable`・`null` | 一覧の EP(EP-01・09・11)は各行の `unavailable`(相対パス)と、行に属さない項目だけの最上位。単一の応答(EP-02・10・12〜14)は最上位(正式なパス) | — | 5.8 |
| `total`・`page`・`items_per_page`・`window_limit` | EP-09・11 | R-6・R-10 | 3.2 |
| O1(`cluster`・`nodes`・`indices`・`shards`・`truncated`・`total_indices`・`fetched_at`) | EP-12 | R-12 | 3.4 |
| D1(`components[].state`・`reason`・`checked_at`、`checked_at`) | EP-13 | プローブ | 6章 |
| `cron_timezone`・`dashboards_url` | EP-14 | 設定 | 7章 |

---

## 6. 死活判定(EP-13。結果の正本は B 8.1。AAA-P-26〜28)

### 6.1 共通の方式

- **Indexer・Crawler は `GET {URL}/healthz` を直接取る**(AAA-K-2)。**2xx かどうかだけ**を判定し、本文は解釈しない(`/healthz` が契約外のため。BAPI-P-13)。本文は読まない(`preload_content=False` で状態行を見て接続を閉じる。応答が大きくても影響しない)。
- **リダイレクトに従わない**(`redirect=False`)。3xx は 2xx 以外として `unexpected_status`(abnormal)。確認先を外から変えられる経路・内部の別のサービスへ誘導される経路を作らない(SSRF の予防。R1 S-12)。
- **確認先の URL は環境変数だけで決め、リクエストから受け取らない**(6.4)。
- **並行して確認する**: 8 つのコンポーネントのうち、`crawler`・`indexer`・`opensearch`・設定された任意コンポーネントの確認は互いに独立に実行し、1 つが遅くても他を待たせない。確認ごとのタイムアウトは `HEALTH_PROBE_TIMEOUT_SECONDS`(既定 3 秒。承認済みの案。ゲート2)。全体の期限は**確認のタイムアウト + 1 秒**とし、これを過ぎても終わらない確認は `undetermined`(`timeout`)として応答する。**期限後も、その確認のスレッドは自身のタイムアウトまで残る**: anyio 4.16.0 の `to_thread.run_sync` は既定が `abandon_on_cancel=False` で、キャンセルされてもスレッドが終わるまで戻らない(ソースで確認)ため、期限で応答するには `abandon_on_cancel=True` で呼ぶことが前提になる(AAA-P-42。案)。放棄したスレッドの `CapacityLimiter` のトークンは放棄の時点で返り、スレッドはその後も走るので、`probe` の枠の上限(8)の外に残りうる(8.1)。残る時間は、HTTP の確認は `Timeout(total=HEALTH_PROBE_TIMEOUT_SECONDS)`(接続と読み取りの合計を確認のタイムアウトに収める。案)で最大約 3 秒、`opensearch` の確認は opensearch-py の接続 3 秒 + 読み取り 3 秒で最大約 6 秒(名前解決は urllib3 の `Timeout` の対象外で、これより長くなりうる。推測。AAA-U-10)。EP-13 の取得は 30 秒間隔(AAPI-P-40。画面仕様)なので、残ったスレッドは次の取得までにほぼ終わり、無害(導出)。再試行はしない(A 5.6)。
- 確認の実行はプローブ専用の枠(8.1。上限 8)で行い、通常の読み取りの枠を使わない(OpenSearch が遅くても、D1 は自分の確認の期限で応答する)。
- 各 `components[].checked_at` は、その確認が終わった時刻。トップの `checked_at` は、全確認が終わって応答を組み立てた時刻(B 8.1)。
- コンポーネントの固定の順・常に 8 件(B 8.1)。

### 6.2 例外・結果と `state`・`reason`(AAA-P-27。AAPI-U-11 への回答の案)

`crawler`・`indexer`・任意コンポーネント(urllib3)。狭いほうから順に判定する。

| 順 | 結果 | `state` | `reason` |
| --- | --- | --- | --- |
| 1 | 2xx | `normal` | `null` |
| 2 | 2xx 以外(3xx・4xx・5xx。Indexer の起動前の 503 を含む) | `abnormal` | `unexpected_status` |
| 3 | `NameResolutionError` | `abnormal` | `name_not_resolved` |
| 4 | `NewConnectionError`(上を除く。接続拒否・到達不能) | `abnormal` | `connection_refused` |
| 5 | `ConnectTimeoutError`(上を除く)、`ReadTimeoutError`、全体の期限を超過 | `undetermined` | `timeout` |
| 6 | その他の `urllib3.exceptions.HTTPError`(`ProtocolError` ほか)、想定外の例外 | `undetermined` | `connection_error` |

`opensearch`(`cluster.health` をプローブ用クライアント(タイムアウト 3 秒・再試行なし。3.7)で呼ぶ)。この確認は opensearchpy で行うため、`infrastructure/opensearch`(`health_probe.py`)に置く(`opensearchpy` の import を OpenSearch アクセスの層に限るため。A 3章。D 4.8)。urllib3 の HTTP の確認は `infrastructure/probes`(D 4.10)。

| 順 | 結果 | `state` | `reason` |
| --- | --- | --- | --- |
| 1 | 応答あり(`status` が `red` でも。詳細は O1) | `normal` | `null` |
| 2 | `TransportError` で `status_code` が整数(HTTP エラーの応答。401・403・5xx など) | `abnormal` | `unexpected_status` |
| 3 | `ConnectionError` で `info` が `NameResolutionError` | `abnormal` | `name_not_resolved` |
| 4 | `ConnectionError` で `info` が `NewConnectionError`(上を除く) | `abnormal` | `connection_refused` |
| 5 | `ConnectionTimeout`、`ConnectionError` で `info` が `ConnectTimeoutError`(上を除く)、全体の期限を超過 | `undetermined` | `timeout` |
| 6 | `SSLError`・その他の `ConnectionError`・想定外の例外 | `undetermined` | `connection_error` |

- `status_code` が `"N/A"`(接続の失敗)でないことで、2 と 3〜6 を分ける。`SSLError` は `ConnectionError` の子なので 6 より前に判定する(導出)。
- 例外の型(`NameResolutionError` など)は、`ConnectionError.info` の `urllib3.exceptions` の型で判定する(5.8。AAA-P-40)。
- 応答の形は見ない(`cluster.health` が 200 を返せば `normal`)。
- 1 つ目の表の `*_HEALTH_URL` は `https` も許すので、`urllib3.exceptions.SSLError`(証明書の検証の失敗など)は 6 行目の `connection_error`(判定不能)になる。`crawler`・`indexer` は `http` 限定(7.3)で起きない。

### 6.3 `api`・`web`・任意コンポーネント(AAA-P-28)

| コンポーネント | 判定 |
| --- | --- |
| `api` | 常に `normal`(応答を返せていること自体が根拠) |
| `web` | `WEB_DIST_DIR` 直下の `index.html` が通常のファイルで、先頭 1 バイトを読めれば `normal`。それ以外は `abnormal`(`missing`)。スレッドに渡さず(`probe` の枠を使わず)ハンドラの中で確認する(毎回確認する。キャッシュしない)。ローカルのファイルの `stat` と 1 バイトの読み取りだけでブロックする見込みが小さいため、「ブロッキングの呼び出しは枠を通す」原則(8.1)の明示的な例外とする(案。D 6章 R9) |
| `opensearch-dashboards`・`embedding`・`llm` | 対応する `*_HEALTH_URL` が**未設定(空文字を含む)なら確認せず `not_configured`**。設定されていれば `crawler` と同じ GET(6.2 の 1 つ目の表) |

### 6.4 確認先の URL(SSRF の経路がないこと)

- 確認先はすべて環境変数(`CRAWLER_URL`・`INDEXER_URL`・`*_HEALTH_URL`・`OPENSEARCH_URL`)で、起動時に検証する(7.3。scheme は `http`・`https` だけ(`CRAWLER_URL`・`INDEXER_URL` は `http` だけ)、ホストあり、ユーザー情報なし)。EP-13 は**パス・クエリ・本文からどんな入力も受け取らない**(B 8.1)。確認先を決める入力が実行時に存在しない(導出)。
- 確認は GET の `/healthz`(`crawler`・`indexer`)と、設定された URL への GET だけ。確認先のサーバーが 3xx を返しても追わない。

---

## 7. 設定

### 7.1 方針

A 4章に従う(`pydantic-settings` の `BaseSettings`、`env_prefix="LORELEY_API_"`、フィールド名の大文字が環境変数名、`extra="ignore"`)。名前の接頭辞 `LORELEY_API_` は案(BAPI-P-6)。**B・A で承認済みの名前は変えない**(AAA-P-29)。本書で足した名前は案(AAA-P-30)。型の列の「URL」は 7.3 の検証を指す。

### 7.2 環境変数の個別一覧(`LORELEY_API_` を除く)

| 名前 | 型 | 既定 | 検証 | 用途 | 区分 |
| --- | --- | --- | --- | --- | --- |
| `OPENSEARCH_URL` | URL | **必須** | 7.3 | OpenSearch の接続先 | A 4(承認済みの案(ゲート3)。BAPI-P-6) |
| `OPENSEARCH_USERNAME` | 文字列・任意 | なし | `PASSWORD` と同時に指定 | Basic 認証(セキュリティ有効時) | 承認済みの案(ゲート3。2026-11-23。AAA-P-30。Crawler・Indexer と同じ) |
| `OPENSEARCH_PASSWORD` | 秘密の文字列・任意 | なし | 同上。ログ・エラーに出さない | 同上 | 同上 |
| `OPENSEARCH_VERIFY_CERTS` | 真偽値 | `true` | — | 証明書の検証 | 同上 |
| `OPENSEARCH_CA_CERTS_PATH` | パス・任意 | なし | — | CA 証明書 | 同上 |
| `OPENSEARCH_REQUEST_TIMEOUT_SECONDS` | 数値(秒) | `10` | `0 <` かつ `≤ 120` | OpenSearch の 1 リクエストのタイムアウト(接続・読み取りそれぞれ) | 承認済みの案(値: BAPI-P-12。名前は案) |
| `OPENSEARCH_MAX_RETRIES` | 整数 | `2` | `0〜5` | 読み取りの再試行回数(3.7) | 同上 |
| `SOURCES_INDEX_NAME` | 文字列 | `loreley-sources` | 非空。4 つの索引名は互いに異なる | データソース設定の索引 | 承認済みの案(ゲート3。2026-11-23。Crawler と同名) |
| `JOBS_INDEX_NAME` | 文字列 | `loreley-jobs` | 同上 | ジョブ・ロック等の索引 | 同上 |
| `DELETIONS_INDEX_NAME` | 文字列 | `loreley-deletions` | 同上 | 削除記録の索引 | 承認済みの案(ゲート3。2026-11-23。Indexer と同名) |
| `SEARCH_INDEX_NAME` | 文字列 | `loreley-documents` | 同上 | 検索インデックスの**エイリアス**(opensearch-init の `SEARCH_INDEX_ALIAS`・Indexer の `LORELEY_INDEXER_SEARCH_INDEX_NAME` と同じ値。init の `SEARCH_INDEX_NAME`(実体名)とは別物。I-90) | 承認済みの案(ゲート3。2026-11-23。Indexer と同じ値) |
| `CRAWLER_URL` | URL | **必須** | 7.3。`http` だけ | Crawler の接続先(操作 6 API・`/healthz`) | 承認済みの案(名前: B 11.7 #11。ゲート2)。`http` 限定は案(AAA-P-41) |
| `INDEXER_URL` | URL | **必須** | 7.3。`http` だけ | Indexer の接続先(`/healthz` だけ) | 同上 |
| `CRAWLER_CONNECT_TIMEOUT_SECONDS` | 数値(秒) | `3` | `0 <` かつ `≤ 60` | Crawler への接続のタイムアウト | 承認済みの案(値: BAPI-P-12。名前は案) |
| `CRAWLER_RESPONSE_TIMEOUT_SECONDS` | 数値(秒) | `60` | `0 <` かつ `≤ 600` | Crawler の応答のタイムアウト | 同上 |
| `HEALTH_PROBE_TIMEOUT_SECONDS` | 数値(秒) | `3` | `0 <` かつ `≤ 30` | 死活確認 1 件のタイムアウト | 承認済みの案(B 11.7 #9。ゲート2) |
| `DASHBOARDS_HEALTH_URL`・`EMBEDDING_HEALTH_URL`・`LLM_HEALTH_URL` | URL・任意 | なし(空文字も未設定) | 7.3 | 任意コンポーネントの確認先。未設定なら `not_configured` | 承認済みの案(B 11.7 #11。ゲート2) |
| `DASHBOARDS_URL` | URL・任意 | なし(空文字も未設定) | 7.3。**ブラウザへ返してリンクにするため scheme は `http`・`https` だけ** | ブラウザから到達できる Dashboards の URL(EP-14) | 承認済みの案(B 11.7 #12。ゲート2) |
| `CRON_TIMEZONE` | 文字列・任意 | なし(`null` で返す) | IANA 名として解釈できること(`zoneinfo`) | cron のタイムゾーン(EP-14)。Crawler の `LORELEY_CRAWLER_TIMEZONE` と同じ値を渡す(AAA-K-3) | 承認済みの案(名前: B 11.7 #13。ゲート2)。持つことは確定 |
| `ADMITTING_LOCK_GRACE_SECONDS` | 数値(秒) | `60` | `0 <` かつ `≤ 3600` | `just_acquired` の猶予(5.9)。Crawler と同じ値を渡す | 承認済みの案(ゲート3。2026-11-23。AAA-P-24) |
| `HOST`・`PORT`・`LOG_LEVEL` | 文字列・整数・列挙 | `127.0.0.1`(コンテナは `0.0.0.0`)・`8080`・`INFO` | `PORT` は 1〜65535、`LOG_LEVEL` は `DEBUG`・`INFO`・`WARNING`・`ERROR`(小文字可) | 待ち受け・ログ | A 4(承認済みの案(ゲート3)。BAPI-P-6) |
| `OPENAPI_ENABLED` | 真偽値 | `false` | — | OpenAPI JSON の実行時公開(`/api/admin/v1/openapi.json`) | 承認済みの案(B 11.7 #14。ゲート2) |
| `WEB_DIST_DIR` | パス | `/app/web` | 非空(存在は起動時に検査しない。`web` の死活で確かめる) | Web UI のビルド成果物。イメージの Dockerfile が `dist/` をここへコピーする(E 3.5。10章) | A 4(案)。既定のパスは案(AAA-P-43) |

### 7.3 起動時の検証(AAA-P-31)

- **URL**(`OPENSEARCH_URL`・`CRAWLER_URL`・`INDEXER_URL`・`*_HEALTH_URL`・`DASHBOARDS_URL`): scheme が `http`・`https`、ホストがある、ユーザー情報(`user:pass@`)がない(認証は専用の変数で渡す。Crawler・Indexer と同じ)、フラグメントがない。`CRAWLER_URL`・`INDEXER_URL` は、パスが空か `/` だけ(末尾のスラッシュは取り除く。固定のパスを足すため)。`*_HEALTH_URL` と `DASHBOARDS_URL` はパス・クエリを許す(完全な URL。クエリに秘密を入れない運用)。**`CRAWLER_URL`・`INDEXER_URL` は scheme を `http` だけにする**(MVP は内部ネットワーク前提で、Crawler・Indexer への TLS の検証設定(CA)を持たないため。`https` は起動失敗。AAA-P-41。A の BAPI-P-24 と同じ。AAA-U-9)。
- **`CRON_TIMEZONE`**: `zoneinfo.ZoneInfo(name)` で解釈できること(IANA 名。`..` などのパスを含む値は解釈できない)。空文字は未設定。
- **数値の範囲**は 7.2 のとおり。**4 つの索引名が互いに異なる**こと(Crawler の `sources_index_name` と `jobs_index_name` の検査に倣う)。
- 違反は起動時に失敗する(fail fast。A 4)。エラーの文言は**環境変数名と違反の種別だけ**で、値を出さない(秘密を含みうる。Crawler の `describe_settings_errors` と同じ流儀)。
- **起動時に OpenSearch・Crawler・Indexer へ接続しない**(AAA-P-34。8.4)。

### 7.4 仮値の一覧

9章。

---

## 8. エラー処理・並行性

### 8.1 実行モデル(AAA-P-33)

- **ハンドラは `async def`** で、ブロッキングの処理(OpenSearch・Crawler・プローブ)を **区分ごとの上限つきで `anyio.to_thread.run_sync(..., limiter=…)` に渡す**。区分と上限(仮値。設定にしない):

  | 区分 | 使う処理 | 同時実行の上限 |
  | --- | --- | --- |
  | `opensearch` | OpenSearch の読み取り(EP-01・02・09〜12、409 の付随情報) | 16 |
  | `crawler` | Crawler への操作の呼び出し(EP-03〜08) | 4 |
  | `probe` | EP-13 の確認 | 8 |

- 理由: 同期ハンドラ(`def`)は共通のスレッドプール(既定 40)で動き、Crawler の応答待ち(最大 60 秒)や OpenSearch の遅延でスレッドが埋まると、他の EP も、`api` 自身の `/healthz`(コンテナのヘルスチェック)も止まる(A 2.1・BAPI-U-6)。区分ごとの上限にすれば、**待っている要求はイベントループの上で待ち**(スレッドを占有しない)、使うスレッドは、通常は区分の上限の合計(28)以内に収まり(EP-13 の期限後に放棄された確認だけは、6.1 のとおりこの外に最大約 6 秒残りうる)、1 つの区分の遅延が他の区分に波及しない(導出)。
- **`GET /healthz`(`api` 自身)は `async def` で、何も呼ばない**(BAPI-P-13)。スレッドを使わないので、スレッドの枯渇の影響を受けない。
- `uvicorn` の `--limit-concurrency` は使わない(上限を超えると、A 5.2 の形式でない応答になるため)。
- `abandon_on_cancel=True` で呼ぶのは `probe` の区分の並行実行(EP-13 の期限。6.1)だけ。`opensearch`・`crawler` の区分は既定(`False`)で、スレッドが終わるまで待つ(AAA-P-42)。
- 上限の値(16・4・8)は仮値で、実測して見直す(AAA-U-7)。Crawler は単一・直列実行なので、Crawler 呼び出しの上限 4 を超える並行は意味が薄い(待たせれば足りる。導出)。

### 8.2 Crawler が遅いときの他の EP への影響

- EP-03〜08 は `crawler` の枠で待つ。枠が詰まると、後続の EP-03〜08 は、前の呼び出しが終わるまで待つ(最大で応答のタイムアウト 60 秒ずつ)。**EP-01・02・09〜14 は別の枠で、影響を受けない**(OpenSearch だけに依存する。B 10.1)。
- 待たされた操作は、待ち時間の分だけ応答が遅れる。待ちの長さに上限を設けるかは未決(AAA-U-7)。Crawler は単一・直列実行で、同じソースへの起動はロックで二重にならない(409 `lock_held`)ので、待ちが長引いても起動が重複することはない(導出)。

### 8.3 OpenSearch が遅い・止まっているときの EP の所要時間(見積もり)

- 1 回の読み取りの最悪(3.7): 読み取りのタイムアウトは再試行しない(A 5.6)ので、1 回の試行は接続 10 秒 + 読み取り 10 秒の最大約 20 秒。接続の失敗は opensearch-py が再試行する(接続のタイムアウトを含む)ので、接続が確立できない間は最大で 10 秒 ×(1 + 再試行 2 回)= 30 秒(接続拒否は即時に失敗)。HTTP の 429・5xx も再試行する。
- 主たる読み取りが失敗すれば、後続の読み取りはせず 503 にする(逐次で打ち切る。EP-12 も同じ)。付随する読み取りは、それぞれが同じ見積もりで失敗しうるため、EP-02 のように複数の読み取りが続く EP の最悪は、その合計になる(実測・上限の検討は AAA-U-7)。
- **EP-13 は独立**: OpenSearch が遅くても、D1 は自分の確認の期限(確認のタイムアウト + 1 秒)で応答する(6.1)。

### 8.4 起動・停止(AAA-P-34)

- 起動時に、OpenSearch・Crawler・Indexer へ接続しない(クライアントを作るだけ。接続は最初の使用時)。Crawler・Indexer が落ちていても `api` は起動し、D1 で異常を見せるため(A 8 の `crawler`・`indexer` を待たない方針)。OpenSearch は compose の `depends_on`(`service_healthy`)で待つ(A 8)。
- OpenSearch クライアント(読み取り用・プローブ用)と urllib3 のプールは、アプリケーションの起動時に 1 度作り、停止時に閉じる。クライアントは複数のスレッドから使う(opensearch-py のプールはスレッドから使える想定。Crawler の CM-U-1 と同じ未確認事項。実機で確認。AAA-U-2)。プールの大きさ(`pool_maxsize`)は `opensearch` の枠(16)に合わせる(案)。

### 8.5 例外の最終処理とログ(AAA-P-38)

- 想定外の例外は 500 `internal_error`(A 5.2)。ログには**クラス名・理由名・送出元の位置(ファイル:行・関数名)だけ**を出し、メッセージ・入力値は出さない(A 5.5)。FastAPI の 422・`HTTPException` は A 5.2 の形式に変換する。
- **`opensearch`・`opensearchpy`・`opensearchpy.trace`・`opensearchpy.helpers`・`urllib3` のロガーは ERROR 以上に制限する**(ID を含む URL・本文が INFO・DEBUG で出るため。Crawler の `common/log_setup` と同じ流儀)。`LOG_LEVEL=DEBUG` でも同じ。**uvicorn は `log_config=None`・`access_log=False` で起動する**(標準のアクセスログは ID を含むパスを出すため。A 5.5。Crawler・Indexer と同じ。D 4.1)。`uvicorn.access` のロガーは念のため ERROR 以上に制限し、`uvicorn.error`(起動・停止の固定文)は制限しない。**想定外の例外は middleware が 500 に変換して再送出しない**(再送出すると、uvicorn が例外のメッセージを含むトレースバックを出すため)。
- ログに出さないもの: 要求の本文・`connector_config`・Crawler の `message`・`crawler_message`・ID を含む実際のパス・OpenSearch の例外の文字列(`root_cause` の理由・リソース ID を含みうる)・`OPENSEARCH_PASSWORD`。出すもの: ルートのテンプレート・ステータス・所要時間・結果の区分(`crawler_unreachable` など)・例外のクラス名。

### 8.6 部分失敗の集約手順(AAA-P-35)

1. **主たる読み取りを先に実行**する。失敗(例外・上限超過)なら、他の読み取りをせず 503 `unavailable`。
2. 付随する読み取りは、**それぞれ独立に実行**し、結果を `Ok(値)` または `Failed(理由コード)` で持つ(例外を呼び出し側に漏らさない。D)。複数の独立な読み取りは、同じ枠(`opensearch`)の中で続けて実行する。
3. 応答を組み立てるとき、`Failed` の項目は `null` にし、単一の応答は最上位の `unavailable` に正式なパス → 理由コード、一覧の EP は**各行の `unavailable`** に相対パス → 理由コード(5.8)を載せる。失敗がなければ `{}`(最上位も各行も常に存在する。B 2.2)。
4. 一覧の EP では、失敗を**行ごとに帰属**させ(5.8 の表)、失敗した行の `unavailable` にだけキーを付ける。行ごとに成否が分かれる読み取りは失敗した行だけ、1 回の読み取りの失敗は全行に同じキーを付ける。最上位の `unavailable` には行に属さない項目だけを載せる。キーのない `null` は値がない(B 2.2・AAPI-P-42)。読み取りの結果は行の ID(`source_id`・`job_id`・`document_id`)で持つ(D)。

---

## 9. 非機能・仮値

すべて仮値で、「設定」の列が○のものだけ環境変数で変えられる(7章)。承認済みの案の値は出典を書く。設定にしない上限(定数)は AAA-P-32。

| 項目 | 値 | 設定 | 出典・区分 | 実測が要る点 |
| --- | --- | --- | --- | --- |
| Crawler への接続・応答のタイムアウト | 3 秒・60 秒 | ○ | 承認済みの案(BAPI-P-12。ゲート2) | 応答 60 秒は Crawler の Store 層の最悪(約 90 秒)より短い。受付の所要の実測(CAPI-U-10。AAA-U-7) |
| OpenSearch の 1 リクエストのタイムアウト・再試行 | 10 秒・2 回(接続エラー・429・500・502・503・504。読み取りのタイムアウトは再試行しない) | ○ | 承認済みの案(値: BAPI-P-12)。再試行の条件は案(AAA-P-8) | 8.3 の最悪の見積もり |
| 死活確認のタイムアウト・全体の期限 | 3 秒・3 秒 + 1 秒 | 前者のみ ○ | 承認済みの案(AAPI-P-8)・後者は案(AAA-P-42) | 期限後に残るスレッドの時間(6.1。AAA-U-10) |
| ページの窓 | `page × items_per_page ≤ 10,000` | — | 承認済みの案(AAPI-P-1。ゲート2) | `max_result_window` の既定が 10,000 であること(AAA-U-3) |
| `items_per_page` | 25・50・100(既定 25) | — | 承認済みの案(AAPI-P-1) | — |
| X1 の一括検索(`existence`)・1 回の取得の上限 | 100 件 | — | 承認済みの案(AAPI-P-5。ゲート2) | — |
| O1 のインデックス上限 | 1,000 件(超過は切り詰め) | — | 承認済みの案(AAPI-P-6。ゲート2) | シャード数が多いときの応答の大きさ |
| `loreley-sources` の全件取得の上限 | 10,000 件(超過は 503) | — | 承認済みの案(ゲート3。2026-11-23。B 3.1 の補足の具体化) | — |
| 集計の `size`(`terms`) | ソース数(上限 10,000) | — | 承認済みの案(ゲート3。2026-11-23) | `search.max_buckets` に収まること(AAA-U-2) |
| リクエスト本文の上限 | 1 MiB | — | 承認済みの案(ゲート3。2026-11-23。BAPI-P-16) | — |
| Crawler の応答本文の上限 | 1 MiB | — | 承認済みの案(ゲート3。2026-11-23。AAA-P-10) | — |
| `just_acquired` の猶予 | 60 秒 | ○ | 承認済みの案(ゲート3。2026-11-23。AAA-P-24。Crawler の仮値に合わせる) | Crawler の値と同期(5.9) |
| 同時実行の上限(`opensearch`・`crawler`・`probe`) | 16・4・8(EP-13 の期限後に放棄された確認は枠の外) | — | 承認済みの案(ゲート3。2026-11-23。AAA-P-33) | 8.1・AAA-U-7 |

- **想定規模**: データソースは数十件、文書は 1 万〜10 万件(arch 15.1。目標値ではない)。ジョブ記録は自動で消さず増え続ける(crawler-architecture 3.5)ので、R-3 の集計(全ジョブ記録を走査する)の負荷は、運用が長くなると増える(AAPI-U-5。AAA-U-7)。
- **実測が必要な点**: 受付(Crawler)の所要時間、EP-01 の集計と EP-02 の複数読み取りの所要時間、ジョブ記録が 10 万件規模のときの R-3・R-6、`stalled` の確認読みの頻度、O1 の応答の大きさ。実装後に測り、10章・7章の値を見直す。

---

## 10. コンテナ・デプロイ

- **配置**: `api` コンテナ内の admin パッケージ(AAA-K-8)。uvicorn は単一プロセス(A 2.1)。パッケージ構成・ディレクトリは D。
- **静的配信・URL・公開範囲**: A 2.1〜2.3(`/admin/` の配信、`/api/admin/v1`、ホストへの publish は 127.0.0.1)。本書は決めない。
- **compose・Dockerfile への要求**: A 8 のとおり。本書から加わる点は、(1) 環境変数 `LORELEY_API_ADMITTING_LOCK_GRACE_SECONDS` に、Crawler の `LORELEY_CRAWLER_ADMITTING_LOCK_GRACE_SECONDS` と**同じ値**を 1 つの変数から渡すこと(5.9)、(2) 索引名の渡し方(I-90): `SOURCES_INDEX_NAME`・`JOBS_INDEX_NAME` は Crawler(と opensearch-init)と同じ変数から、`DELETIONS_INDEX_NAME` は Indexer と同じ変数から、検索エイリアスの `SEARCH_INDEX_NAME` は opensearch-init の `SEARCH_INDEX_ALIAS` と Indexer の `LORELEY_INDEXER_SEARCH_INDEX_NAME`(どちらもエイリアス)と同じ変数から渡す。opensearch-init の `SEARCH_INDEX_NAME`(実体名。既定 `loreley-documents-000001`)は別物で渡さない(実体名を渡すと、再インデックスでエイリアスが付け替わった後も古い索引を読む)。現在の compose はこれらの変数をまだ揃えておらず、`api` を足す前提作業で揃える(I-93)、(3) OpenSearch のセキュリティを有効にする運用では、`OPENSEARCH_USERNAME`・`OPENSEARCH_PASSWORD` を渡すこと(秘密。ログに出さない)、(4) Dockerfile が Web UI のビルド成果物 `dist/` を `LORELEY_API_WEB_DIST_DIR` の既定 `/app/web` にコピーすること(E 3.5。AAA-P-43)。HO-35・HO-36(A 9章)。
- **Dockerfile の `HEALTHCHECK`**: `GET /healthz`(A 6)。`api` は起動時に外部へ接続しないので、起動の猶予は短くてよい(8.4。導出)。

---

## 11. テスト観点

偽物(`tests/fakes/`)を使い、実 OpenSearch・実 Crawler なしで確かめる(AAA-P-36)。実機での確認は結合テストで行う(12章の AAA-U)。偽物の置き方は D。

| # | 観点 | 方法 |
| --- | --- | --- |
| 1 | **Crawler 写像表**(B 9.2・2.6) | Crawler の偽物(ローカルの HTTP スタブ。応答を指定できる)で、API ごと・Crawler の応答(ステータス・`code`・`details`)ごとに、Admin API の応答が B の表に一致することを表駆動で確認。未知の `code`・JSON でない本文・期待以外の 2xx・3xx は 502 |
| 2 | **Crawler の障害別挙動**(B 10.2) | 接続拒否・名前解決失敗・接続のタイムアウト(`crawler_unreachable`)、応答のタイムアウト・切断(`crawler_response_lost`・`outcome_unknown=true`)、503 `unavailable`(`crawler_unavailable`)、起動時の回復中(接続拒否の再現)。**呼び出しが 1 回だけ**(再送しないこと。スタブの受信回数)・リダイレクトに従わないこと。`SSLError` は通信では再現しにくい(`http` 限定)ので、分類関数に例外を直接与える単体テスト(503) |
| 3 | **パスのエンコードと EP-07 の 404 写像** | `job_id` に `%`・`?`・`#`・`.`・`..`・`%2F` を含む値で、スタブが受けた**生のリクエスト行**のパスが全文字エンコードされていること(`.` は `/jobs/%2E/cancel`、`..` は `/jobs/%2E%2E/cancel` を受け、ドットセグメントとして除去されないこと。実際の urllib3 で確認する。`source_id` の `.` も `%2E`)。スタブが 400(`job_id`)・404 `not_found` を返したとき EP-07 は 404 `job_not_found`、`source_id` を使う EP では 502 |
| 4 | **`config_invalid` の分解**(4.5) | `include_patterns[2]: …`・`root: …`・`connector_config: …`(`field="connector_config"`)・末尾に改行を含む前半・512 文字・`: ` のない文字列・前半が形に一致しない文字列・`message` が文字列でない |
| 5 | **導出**(5章) | `lock_state` の 10 行の表を、時計の偽物(猶予の境界の前後)で表駆動。`stalled` の確認読み(ロックなし → 読み直しで終端 / まだ `running`、ロックが別のジョブ、読み取りの失敗)。`rerunnable` の評価順。`last_completed_at`・`delete_job` の条件。`ttl`・しきい値の変換(`0.29`・`0.1`・`12.345`・`1e-3`・`20`・範囲外・小数第 3 位以下)・`int64` の境界 |
| 6 | **部分失敗・障害別**(B 2.2・10.2) | OpenSearch の偽物に、索引単位・サブ要求単位の失敗を注入(`loreley-jobs` だけ、検索インデックスだけ、`msearch` の一部、タイムアウト)。主たる読み取りの失敗が 503、付随の失敗が `null`+`unavailable`(単一の応答は最上位の正式パス、一覧は**行の `unavailable` の相対パス**。`items[].…` 形式のキーが出ないこと)・理由コード(`timeout` が優先)。**行ごとの成否の区別**: EP-01 で、未実行の source-a(`last_crawl=null`・キーなし)と、ロック文書の `mget` が文書単位で失敗した source-b(`last_crawl.stalled=null`+キー。source-a は影響なし)を区別できること。R-3 の失敗は全行にキー(`delete_job` は `deleting` の行だけ)。EP-09 の `stalled`、EP-11 の `existence`(全行)と `tab_counts.<タブ>`(最上位)も同様で、EP-01・09 の最上位は常に `{}`。`malformed`(設定項目)。**部分的な失敗**(3.2): `mget` の `docs[i].error`・`found` が真偽値でない文書(他の文書は使えること)、検索の `_shards.failed>0`・`timed_out=true` を注入し、実在するロックを `lock_state=none` に、実在するジョブを EP-10 の 404 にしないこと |
| 7 | **ページングの窓** | `page × items_per_page` が 10,000 ちょうど(通る)と 10,001(400 `range`)、`total` が窓を超えても正確(`track_total_hits`)、同順位の ID の昇順(取りこぼし・重複なし) |
| 8 | **読み取り専用**(2.3) | (a) AST 検査: クライアント由来の呼び出しの名前が許可リストの中だけ・書き込み系の名前がない・`opensearchpy`・`urllib3` の import 場所(`urllib3.exceptions` は `infrastructure.opensearch` の `failure.py`・`health_probe.py` に限って可。`infrastructure` が `common.http` を import しない)。(b) OpenSearch の偽物が許可リスト外の呼び出しで失敗する。(c) Crawler クライアントが 6 経路と `GET /healthz` 以外を送れない |
| 9 | **契約テスト(スキーマ)**(3.5) | `infra/opensearch/schema/*.json` を読み、本書のフィルタ・並べ替え・集計の項目が期待の型でマップされていること |
| 10 | **死活**(6章) | Crawler・Indexer の偽物が 2xx(`normal`)・3xx(`abnormal`・`unexpected_status`。追わないこと)・5xx・接続拒否・名前解決失敗・遅延(`undetermined`・`timeout`)・切断を返す。OpenSearch の例外ごとの `state`・`reason`。`web`(`index.html` の有無)・任意コンポーネントの `not_configured`(空文字を含む)。**1 つが遅くても他を待たせず、全体が期限(確認 + 1 秒)内**(期限後も確認のスレッドが残る場合に、期限内に `undetermined`・`timeout` で応答すること。6.1)。確認先が環境変数以外から決まらないこと(EP-13 にパス・クエリを渡しても確認先が変わらない) |
| 11 | **CORS を許可しない**(AAA-P-37) | (a) `CORSMiddleware` を使っていない。(b) `Origin: https://example.invalid` を付けたリクエスト・preflight(`OPTIONS`)の応答に `Access-Control-Allow-*` が付かない(preflight は 405 `method_not_allowed`)。(c) 本文なしの `POST`(EP-05・06・07)が、`Origin` を問わず処理される現状を記録する(保護がないリスクの確認。BAPI-U-8) |
| 12 | **入力値・秘密を出さない** | 不正な値(制御文字・長い文字列・サロゲート・パスのような文字列・URL)を入力した応答本文に、その値が含まれないこと。ログ(`caplog`)に、`OPENSEARCH_PASSWORD`・本文・`connector_config`・Crawler の `message`・ID を含むパスが出ないこと。`opensearch`・`urllib3`・`uvicorn.access` のロガーが ERROR 以上に制限されていること。uvicorn のアクセスログが出ないこと。想定外の例外でトレースバックが出ないこと(8.5) |
| 13 | **設定** | 必須の欠落・URL の検証(ユーザー情報・scheme。`CRAWLER_URL`・`INDEXER_URL` に `https` を与えると失敗)・`CRON_TIMEZONE` の不正・索引名の重複・範囲外の数値が、値を出さずに起動失敗。未設定の任意項目(空文字を含む)が `null`・`not_configured` |
| 14 | **並行性**(8.1) | Crawler の偽物を遅延させても、EP-01・02・09〜14 と `/healthz` が応答すること。`crawler` の枠の上限を超える要求が待つこと。OpenSearch の偽物を遅延させても EP-13 が期限内に応答すること |
| 15 | **OpenAPI・ドキュメントの既定** | 既定で `/api/admin/v1/openapi.json`・`/docs`・`/redoc` が 404(JSON の `not_found`)。`OPENAPI_ENABLED=true` で JSON だけが出る(BAPI-P-4) |
| 16 | **`mget` と検索の使い分け** | 書き込み直後のロック・ジョブ(`mget`)が見え、検索は古い状態を返す偽物で、`stalled` が偽陽性にならないこと(5.2) |

---

## 12. 確認状況

### 12.1 確認した事実(2026-11-22)

- A・B を通読した。作業記録(0004・0008・0010〜0014)で、B の R1 修正と C への引き継ぎを確認した。
- 既存設計: crawler-architecture v0.4(2.5、3.2、3.3、4.2〜4.8、5.1〜5.9、7.6・7.7、11)、crawler-api v0.4(1・3・4.1〜4.3・4.7)、crawler-module-structure v0.5 の CM-P-29、indexer-api v0.10 の 1章(`/healthz`)、indexer-architecture v0.10 の K53・U-30・E-44、`search-index-v0.10.md`、`loreley-deletions-v0.10.md`、SD v0.8 §7.3・§14.2・§14.5、`deploy/compose/compose.yaml`、`infra/opensearch/init-indices.sh`、`infra/opensearch/schema/*.json`(`sources.json`・`jobs.json`・`deletions.json`・`search-index.json` のマッピング。3.5 の表の根拠)。
- 実装の慣習: `apps/crawler/src/loreley_crawler/config.py`(環境変数・整合性検査・`describe_settings_errors`。`admitting_lock_grace_seconds` の既定 60 を `jobs/settings.py` で確認)、`infrastructure/opensearch/connection.py`(`max_retries=0`・タイムアウト)、`infrastructure/indexer_client/http_client.py`(urllib3 の例外の分類)、`common/log_setup.py`(ロガーの制限)、`apps/indexer` の `connection.py`・`config.py`・`tests/architecture/test_write_rules.py`(書き込み検査)。
- **ライブラリのソース**(`apps/crawler/.venv` の opensearch-py 3.2.0 と urllib3 2.8.0): `opensearchpy/exceptions.py`(`TransportError` の `status_code`・`info`・`__str__` が `root_cause` の理由とリソース ID を含むこと、`ConnectionError`・`ConnectionTimeout`・`SSLError` の継承)、`transport.py`(`ConnectionError` は必ず、`ConnectionTimeout` は `retry_on_timeout` のとき、HTTP ステータスは `retry_on_status` のとき再試行すること、再試行の間の待ちがないこと)、`connection/http_urllib3.py`(`ReadTimeoutError` だけが `ConnectionTimeout` になり、接続のタイムアウトは `ConnectionError` になること。`pool_maxsize`)、`urllib3/exceptions.py`(`NewConnectionError` が `ConnectTimeoutError` の子、`NameResolutionError` が `NewConnectionError` の子)。
- **R2 の指摘への対応時の確認**: `python -I` で、urllib3 2.8.0 の `parse_url` が `/jobs/../cancel` を `/cancel`、`/jobs/./cancel` を `/jobs/cancel` にし、`%2E%2E`・`%2E` は保持すること、`quote("..", safe="")` が `..` のままであること、`SSLError` が `HTTPError` の直接の子であること(`ProtocolError` ではない)を確認した。anyio 4.16.0 は `to_thread.run_sync` の `abandon_on_cancel` の既定が `False` で、`True` のときは取消で `CapacityLimiter` のトークンが返る(`_backends/_asyncio.py` の `run_sync_in_worker_thread`)。`infra/opensearch/init-indices.sh`(`SEARCH_INDEX_NAME` が実体名、`SEARCH_INDEX_ALIAS` がエイリアス)、`deploy/compose/compose.yaml`(Indexer に検索・削除記録の索引名を渡さず、opensearch-init には `loreley-jobs`・`loreley-sources` だけ)、`apps/indexer`・`apps/crawler` の `config.py`・`main.py`(索引名、uvicorn の `log_config=None`・`access_log=False`)、`apps/crawler/tests/architecture/dependency_rules.py`(`urllib3` の所有者が `infrastructure.indexer_client` だけ。モジュール単位)、`infra/opensearch/schema/*.json`(3.5 の表の根拠)を読んだ。
- `apps/api/`・`apps/web/` は存在しない(新規)。コード・設定ファイルは作っていない。

**確認していないこと**: OpenSearch の実機(`cluster.health`・`cat.*` の項目名・値の型・クローズ済み・隠しインデックスの扱い・`relocating` の `node` の形、検索アイドル後の refresh、`mget` の `_source` 指定・`ids` クエリとエイリアス、`mget` の文書単位の `error` と検索の `_shards.failed`・`timed_out` の応答の形、`terms` 集計の上限、`search.max_buckets`)、Crawler・Indexer の実機での接続失敗の見え方と、`Connection: close` で実際に毎回新しい接続になること、実 uvicorn の `job_id` 特殊文字の扱い。テストの実行(コードがない)。

### 12.2 確定(AAA-K)

確定にしたのは、ユーザーの明示回答と、確定として書かれた既承認文書の引用だけ。

| ID | 内容 | 出典 |
| --- | --- | --- |
| AAA-K-1 | Admin API は Store 層・検索インデックスに書かない(読み取りのみ。メンテナンスフラグも書かない)。書き込みは Crawler の HTTP だけ | CAPI-K-5・CA-K-2(確定)、AAPI-K-1・BAPI-K-8 |
| AAA-K-2 | Indexer・Crawler の死活は、Admin API が各 `/healthz` を直接読む(SD §7.3 の緩和が前提) | ユーザー回答(2026-11-22。0001 Q1')、BAPI-K-5・AAPI-K-7 |
| AAA-K-3 | cron のタイムゾーンは Admin API の環境変数で持つ | ユーザー回答(2026-11-22。0001 Q1)、BAPI-K-7・AAPI-K-8 |
| AAA-K-4 | `config_invalid` は分解方式で、Connector の検証規則は複製しない(確定は方式のみ。細部は承認済みの案) | ユーザー回答(2026-11-22。0004)、AAPI-K-5 |
| AAA-K-5 | しきい値の範囲(0 以上 1 未満)の検証は Admin API だけが行う | CA-K-16・CAPI-K-3(確定)、AAPI-K-2 |
| AAA-K-6 | Admin API は検索インデックスを読み取り専用で参照してよい(`extract_failed` の一覧や文書数など。書き込まない)。具体は Admin API 設計で決める | IA K53(ユーザー確定 2026-11-10) |
| AAA-K-7 | Admin API が Crawler に中継する操作は、6 つの固定の経路だけ | CAPI-K-1・CA-K-19(確定)、SD §14.4 の 6(「固定の経路だけ Crawler に中継し、任意のパスは転送しない」) |
| AAA-K-8 | Admin API は `api` コンテナ内の admin パッケージ。Web UI は `api` が同一オリジンで静的配信する(CORS 不要) | ユーザー回答(2026-11-22。0001 Q2)、BAPI-K-1・K-2 |

### 12.3 案・承認済みの案(AAA-P)

区分欄の「承認済みの案」は、B・A のゲート1・2で承認された事項の引用(出典の ID を書く)。「実装形はゲート3で承認(2026-11-23)」は、本書が足した実装の具体。確定にはしていない。

| ID | 内容 | 区分 | 章 |
| --- | --- | --- | --- |
| AAA-P-1 | OpenSearch に呼んでよい API は許可リストで固定する(`search`・`msearch`・`mget`・`cluster.health`・`cat.*`)。書き込み・索引管理・`refresh`・`scroll`・PIT・スクリプトは呼ばない | 承認済みの案(ゲート3。2026-11-23) | 2.3 |
| AAA-P-2 | ID での取得は `mget`(ID は本文。リアルタイム。`record_type` を確かめる) | 承認済みの案(ゲート3。2026-11-23) | 3.2 |
| AAA-P-3 | 読み取り単位 R-1〜R-12 のクエリ形、`_source` の限定、`track_total_hits`、並べ替え + ID | 承認済みの案(ゲート3。2026-11-23。窓の値は承認済みの案: AAPI-P-1) | 3.2・3.3 |
| AAA-P-4 | ページの窓の値(`page × items_per_page ≤ 10,000`、`items_per_page` は 25・50・100、`track_total_hits`) | 承認済みの案(AAPI-P-1。ゲート2) | 3.2・9章 |
| AAA-P-5 | 検索インデックスの読み取り条件(IA U-30 への回答): エイリアスだけ、`search`・`msearch` だけ、本文・要約を読まない、最大 100 件 | 承認済みの案(ゲート3。2026-11-23) | 3.6 |
| AAA-P-6 | refresh 遅延の扱い(`mget` はリアルタイム、検索は最大約 1 秒古い。`refresh` を呼ばない) | 承認済みの案(ゲート3。2026-11-23) | 3.2 |
| AAA-P-7 | スキーマ依存: マップ済みの項目だけで絞り込み・並べ替え・集計。契約テストでスキーマ JSON と突き合わせる | 承認済みの案(ゲート3。2026-11-23) | 3.5 |
| AAA-P-8 | OpenSearch クライアントの設定: 読み取り用(10 秒・再試行 2 回・`retry_on_timeout=False`・`retry_on_status=(429, 500, 502, 503, 504)`)、プローブ用(3 秒・再試行なし) | 承認済みの案(値: BAPI-P-12。ゲート2)。再試行の条件(`retry_on_timeout=False`・接続エラーの再試行・`retry_on_status` の 5 値。A 5.6 の「5xx」より狭い)は承認済みの案(BAPI-P-12 の明確化分。ゲート3。2026-11-23) | 3.7・7.2 |
| AAA-P-9 | `cluster.health`・`cat.*` の取得(列・`expand_wildcards=all`・`relocating` の `->`・文字列の正規化・並び・切り詰め・形の異常は 503) | 承認済みの案(ゲート3。2026-11-23。AAPI-P-6・P-31 の具体化) | 3.4 |
| AAA-P-10 | Crawler クライアントの設定(urllib3、`Timeout`、`retries=False`、`redirect=False`、接続を使い回さない、応答本文は 1 MiB まで) | 承認済みの案(値: BAPI-P-12。ゲート2)。実装形はゲート3で承認(2026-11-23) | 4.1 |
| AAA-P-11 | 例外の分類(`NameResolutionError`・`NewConnectionError`・`ConnectTimeoutError`・`SSLError` → 503、`ReadTimeoutError`・`ProtocolError`・その他 → 504) | 承認済みの案(ゲート3。2026-11-23。結果は B 2.3。AAPI-P-28 に依存) | 4.3 |
| AAA-P-12 | エラー写像の実装方針(表駆動、未知は 502、400 の項目の分岐、`existing_job` の取り込み、期待以外の 2xx は 502、回復中は接続前の失敗) | 承認済みの案(ゲート3。2026-11-23。結果は B 2.6・9.2。AAPI-P-28 に依存) | 4.2・4.4・4.7 |
| AAA-P-13 | `config_invalid` の分解の実装(`partition` + `fullmatch`、512 文字、`field` の組み立て) | 承認済みの案(規則: AAPI-P-12。ゲート2)。実装の注意は承認済みの案(ゲート3。2026-11-23) | 4.5 |
| AAA-P-14 | 固定の 6 経路と、`source_id`・`job_id` の全文字パーセントエンコード(`quote(safe="")` の後に `.` を `%2E` に置換) | 承認済みの案(ゲート3。2026-11-23。AAPI-P-24 に依存。`.` の置換は作業記録 0027 の指摘による追加で、ゲート3で承認(G3-6)。代案の検証での拒否は採らない) | 4.8 |
| AAA-P-15 | 409 の付随情報 `lock_state` はロック → ジョブの順に読み、失敗は `unknown` で 409 は変えない | 承認済みの案(ゲート3。2026-11-23。形は承認済みの案: AAPI-P-13。ゲート2) | 4.6 |
| AAA-P-16 | 共通の読み方: `now` は 1 回、日時はオフセット必須・UTC ミリ秒、型の厳密な確認 | 承認済みの案(ゲート3。2026-11-23) | 5.0 |
| AAA-P-17 | `lock_state` の判定順序(10 行の表。`orphan` と `just_acquired` は排他、`status`・`job_type` が読めなければ `unknown`) | 承認済みの案(ゲート3。2026-11-23。AAPI-P-17 に依存) | 5.1 |
| AAA-P-18 | `stalled`・`cancellable`(定義)と、ロック不一致の確認読み(ロック → ジョブの順の読み直し) | 承認済みの案(定義: AAPI-P-4。ゲート1)。確認読みは承認済みの案(ゲート3。2026-11-23)(B 2.9・AAPI-P-27 に反映済み) | 5.2 |
| AAA-P-19 | `latest_for_source`・`rerunnable`・`rerun_blocked_reason` の評価順、設定がない・読み取り失敗の扱い | 承認済みの案(ゲート3。2026-11-23。AAPI-P-18・P-41 に依存。`source_missing` と `rerunnable=null` の条件は B に反映済み。作業記録 0020) | 5.3 |
| AAA-P-20 | `registration.phase`・`cancel_after_finish_notice`・`deletion.*` の読み方、`warnings`・`failure_detail` の通し方 | 承認済みの案(`phase`: AAPI-P-4。ゲート1)。他は承認済みの案(ゲート3。2026-11-23)(AAPI-P-29) | 5.4 |
| AAA-P-21 | `last_crawl`・`last_completed_at`・`delete_job` の集計(R-3) | 承認済みの案(定義: AAPI-P-4。ゲート1)。クエリ形は承認済みの案(ゲート3。2026-11-23)。失敗の帰属(全行)は AAA-P-45 | 5.5 |
| AAA-P-22 | `existence` の算出(1 回の `ids` クエリ。最大 100 件) | 承認済みの案(方針: AAPI-P-5。ゲート1・2)。実装形はゲート3で承認(2026-11-23)。失敗の帰属(全行)は AAA-P-45 | 5.6 |
| AAA-P-23 | TTL・しきい値の十進数での変換(`repr` 経由。整数値は整数で出す) | 承認済みの案(方針: AAPI-P-14。ゲート2)。細部は承認済みの案(ゲート3。2026-11-23)(AAPI-P-38 に依存) | 5.7 |
| AAA-P-24 | `just_acquired` の猶予を環境変数 `ADMITTING_LOCK_GRACE_SECONDS`(既定 60)で持ち、compose で Crawler と同じ値を渡す | 承認済みの案(ゲート3。2026-11-23) | 5.9・7.2 |
| AAA-P-25 | 部分失敗の理由コードの付け方(`timeout` 優先、対象別)、キーと理由の対応、`malformed` の判定、読めない値は `null` | 承認済みの案(ゲート3。2026-11-23。AAPI-P-25・P-34 に依存。`null` を許す型・`timeout` 優先・`ttl_days` のキーは B に反映済み。作業記録 0020)。キーの位置(一覧は行の相対パス)は AAPI-P-42 により修正(AAA-P-45) | 5.0・5.8 |
| AAA-P-26 | 死活確認の方式(GET・2xx だけ・本文を読まない・リダイレクト非追従・並行・全体の期限) | 承認済みの案(方針: BAPI-P-13・AAPI-P-8。ゲート1・2)。実装形はゲート3で承認(2026-11-23) | 6.1 |
| AAA-P-27 | 例外・結果と `state`・`reason` の対応(urllib3・opensearch-py) | 承認済みの案(ゲート3。2026-11-23。AAPI-P-33・U-11 への回答) | 6.2 |
| AAA-P-28 | `api`・`web`・任意コンポーネントの判定と、確認先の URL の扱い(環境変数のみ・scheme の検証) | 承認済みの案(AAPI-P-8。ゲート1・2)。検証は承認済みの案(ゲート3。2026-11-23)。`web` の確認を枠に渡さないこと(8.1 の原則の例外)も承認済みの案(ゲート3。2026-11-23) | 6.3・6.4 |
| AAA-P-29 | B・A で承認済みの環境変数名の個別一覧(型・既定・検証・用途) | 承認済みの案(名前: B 11.7 #9〜#14・A 5.4。ゲート2)。接頭辞は承認済みの案(ゲート3。2026-11-23)(BAPI-P-6) | 7.2 |
| AAA-P-30 | 本書で足した環境変数名(`OPENSEARCH_USERNAME` ほかの認証・TLS、`*_TIMEOUT_SECONDS`、`OPENSEARCH_MAX_RETRIES`、4 つの索引名、`ADMITTING_LOCK_GRACE_SECONDS`) | 承認済みの案(ゲート3。2026-11-23) | 7.2 |
| AAA-P-31 | 起動時の検証(URL・IANA 名・範囲・索引名の重複)と、値を出さない失敗 | 承認済みの案(ゲート3。2026-11-23。A 4 の具体化) | 7.3 |
| AAA-P-32 | 固定の上限(定数。設定にしない): `loreley-sources` 全件 10,000 件、集計の `size`、O1 の 1,000 件、X1 の 100 件、応答本文 1 MiB(9章) | 承認済みの案(O1・X1・窓の値: AAPI-P-5・P-6。ゲート2)。他は承認済みの案(ゲート3。2026-11-23) | 9章 |
| AAA-P-33 | 実行モデル: `async def` + 区分別の上限(`opensearch` 16・`crawler` 4・`probe` 8)+ `/healthz` はスレッドを使わない。EP-13 の期限後の放棄は AAA-P-42 | 承認済みの案(ゲート3。2026-11-23。BAPI-U-6 への回答) | 8.1〜8.3 |
| AAA-P-34 | 起動時に外部へ接続しない。クライアントは起動時に作り停止時に閉じる | 承認済みの案(ゲート3。2026-11-23) | 7.3・8.4 |
| AAA-P-35 | 部分失敗の集約手順(主たる読み取り → 付随を独立に → `unavailable`) | 承認済みの案(ゲート3。2026-11-23。AAPI-P-16 に依存)。一覧の `unavailable` を行単位にする修正を含む(AAPI-P-42。PR #10 のレビュー指摘への対応。AAA-P-45) | 8.6 |
| AAA-P-36 | テスト観点の方針(偽物・契約テスト・AST 検査・時計の偽物) | 承認済みの案(ゲート3。2026-11-23) | 11章 |
| AAA-P-37 | CORS を許可しない(ミドルウェアを入れず、`Access-Control-*` を付けない)。同一オリジンのため | 承認済みの案(ゲート3。2026-11-23。BAPI-K-2・A 2.3 に基づくテスト観点) | 11章 |
| AAA-P-38 | ログ: ロガーの制限(`uvicorn.access` を含む)、出すもの・出さないもの、uvicorn の起動引数(`log_config=None`・`access_log=False`)、想定外の例外を再送出しない | 承認済みの案(ゲート3。2026-11-23。A 5.5・BAPI-P-17 に依存) | 8.5 |
| AAA-P-39 | 部分的な失敗を成功と読まない: `mget` の `docs[i].error`・`found` が真偽値でない文書は `Failed`、検索の `timed_out=true`・`_shards.failed>0`・形の異常は `Failed`(部分的な結果を使わない) | 承認済みの案(ゲート3。2026-11-23。R2 I-2。実機での形は AAA-U-2) | 3.2・3.3・5.8 |
| AAA-P-40 | `urllib3.exceptions` の import を `infrastructure.opensearch`(`failure.py`・`health_probe.py`)に限って許す。OpenSearch の例外の分類は `ConnectionError.info` の `urllib3.exceptions` の型で行う | 承認済みの案(ゲート3。2026-11-23。A の BAPI-P-22 と同じ。作業記録 0027 の指摘) | 2.3・5.8・6.2 |
| AAA-P-41 | `CRAWLER_URL`・`INDEXER_URL` は MVP では `http` 限定(TLS の検証設定を持たない)。`SSLError` は 503 `crawler_unreachable` | 承認済みの案(ゲート3。2026-11-23。A の BAPI-P-24 と同じ。作業記録 0027 の指摘) | 4.3・7.3 |
| AAA-P-42 | EP-13 の全体の期限: `probe` の並行実行は `abandon_on_cancel=True` で呼び、期限後も確認のスレッドは自身のタイムアウトまで残る。HTTP のプローブは `Timeout(total=…)` | 承認済みの案(ゲート3。2026-11-23。AAA-P-26 の実装形。R2 S-2) | 6.1・8.1 |
| AAA-P-43 | `WEB_DIST_DIR` の既定を `/app/web`(イメージ内の固定パス。Dockerfile が `dist/` をコピーする) | 承認済みの案(ゲート3。2026-11-23。A 4 が「既定は C 7.2」とする。R2 S-8) | 7.2・10 |
| AAA-P-44 | `JobBrief` の各項目の導出規則(許される値の列挙にない値は `null`、`failure_reason` は `failed` のときだけ)と、`job_type`・`status` が読めないときの `rerunnable`(`not_crawl`・`not_failed`) | 承認済みの案(ゲート3。2026-11-23。AAPI-P-25 に依存。R2 S-11) | 5.3・5.4 |
| AAA-P-45 | 一覧の EP(EP-01・09・11)の `unavailable` は行単位: 各 `items[i]` に持ち(常に存在)、キーは行の中の相対パス。最上位は行に属さない項目だけ。失敗の帰属(1 回の読み取りの失敗は全行、文書単位・サブ要求単位の失敗は該当の行だけ、行に属さない項目は最上位)。キーのない `null` は値がない | 承認済みの案(ゲート3。2026-11-23)の修正(PR #10 のレビュー指摘への対応。AAPI-P-42 に依存。AAA-P-25・P-35 の修正) | 5.8・8.6 |

### 12.4 未決・実装時確認(AAA-U)

| ID | 内容 | 決める場所 |
| --- | --- | --- |
| AAA-U-1 | `cluster.health`・`cat.*` の項目名・値の型(文字列)、クローズ済みの `docs.count`・`health`、`cat.shards` が隠しインデックスを含むか(`expand_wildcards=all` との整合)、`relocating` の `node` の ` -> ` 区切り、未割り当ての `node`(推測。AAPI-U-4・U-11) | 実機・実装時 |
| AAA-U-2 | `mget` の `_source` 指定の渡し方、`msearch` のサブ要求のエラーの形、`mget` の文書単位の `error` と検索の `timed_out`・`_shards.failed` の応答の形(3.2。AAA-P-39)、`ids` クエリとエイリアスの動作、`terms` 集計の `size` と `search.max_buckets`、クライアントのスレッド間共有(`pool_maxsize`)(CM-U-1 と同じ) | 実機・実装時 |
| AAA-U-3 | 検索アイドル後の refresh の挙動と `refresh_interval`(推測。3.2)、`index.max_result_window` が既定の 10,000 であること | 実機 |
| AAA-U-4 | `Connection: close` で実際に毎回新しい接続になること、Crawler・Indexer の起動直後・回復中の接続失敗の見え方(AAPI-U-1)、実 uvicorn での `job_id` の特殊文字(`%2E` を含む。AAPI-U-12) | 実機・結合テスト |
| AAA-U-5 | 実行中でロック文書がないジョブを `stalled=true` とする扱い(推測。AAPI-U-9)と、確認読みの妥当性 | 実機 |
| AAA-U-6 | `just_acquired` の猶予が Crawler の設定とずれたときの運用(5.9。compose の同値定義に頼る) | 運用(A 9章 HO-44) |
| AAA-U-7 | 同時実行の上限(16・4・8)、Crawler の待ちの長さの上限、R-3・R-6・EP-02 の所要時間(ジョブ記録が増えたとき)、`stalled` の確認読みの頻度、O1 の応答の大きさ(AAPI-U-5。CAPI-U-10) | 実装後の実測 |
| AAA-U-8 | セキュリティを有効にした OpenSearch での読み取り専用の最小権限(`cluster.health`・`cat.*`・検索・`mget`)(BAPI-U-7) | 実装時・運用 |
| AAA-U-9 | `https` を許す将来の扱い: TLS の検証設定(CA)の持ち方、送った後の TLS の失敗(`SSLError`)の分類(4.3 の順 4)。MVP は `http` 限定(AAA-P-41) | 別タスク(`https` が要るとき) |
| AAA-U-10 | EP-13 の期限後に残るスレッドの数と時間(名前解決は urllib3 の `Timeout` の対象外という推測の確認を含む。6.1) | 実装後の実測 |

### 12.5 既存設計との不整合(I-n)

| ID | 内容 | 本書での扱い |
| --- | --- | --- |
| I-90 | 検索インデックスのエイリアス名: `search-index-v0.10.md`(4.1)は「エイリアス名・実インデックス名は未決」とするが、`init-indices.sh`・Indexer の実装の既定は `loreley-documents`(実体 `loreley-documents-000001`)。さらに `init-indices.sh` では `SEARCH_INDEX_NAME` が**実体名**、`SEARCH_INDEX_ALIAS` がエイリアスで、Indexer の `search_index_name`(`LORELEY_INDEXER_SEARCH_INDEX_NAME`。既定 `loreley-documents`)はエイリアスにあたる。Admin API の `SEARCH_INDEX_NAME` は**エイリアス**で、init の同名の変数とは意味が違う | Admin API の `SEARCH_INDEX_NAME` の既定を `loreley-documents` にし、compose で init の `SEARCH_INDEX_ALIAS` と Indexer の `LORELEY_INDEXER_SEARCH_INDEX_NAME` と同じ変数から渡す(init の `SEARCH_INDEX_NAME` は渡さない)(A 4・8。HO-16・HO-35) |
| I-91 | crawler-architecture 11章・crawler-api 4.3 は、受付の途中のロックとみなす `acquired_at` の猶予を「60 秒(仮値)」とし環境変数名を書かないが、実装には `LORELEY_CRAWLER_ADMITTING_LOCK_GRACE_SECONDS`(既定 60)がある。Admin API が同じ値を持つ必要がある(5.9) | 設計書への名前の追記は HO-13。Admin API は同名の趣旨の変数を持ち、compose で同値を渡す |
| I-92 | Crawler の `tests/architecture/dependency_rules.py` は `urllib3` の所有者を `infrastructure.indexer_client` だけ(モジュール単位)とし、`opensearch` は urllib3 を使わない前提。Admin API は OpenSearch の例外の分類に `urllib3.exceptions` の型が要る | `urllib3.exceptions` の import に限り `infrastructure.opensearch`(`failure.py`・`health_probe.py`)に許す(AAA-P-40。A 3・7 の案 BAPI-P-22)。検査器はファイル単位の例外を持てるようにする(D R5)。HO-39 |
| I-93 | `deploy/compose/compose.yaml` は Indexer に検索・削除記録の索引名を渡さず、opensearch-init にも `loreley-jobs`・`loreley-sources` の名前しか渡していない(検索・削除記録は既定に頼る)。Crawler は検索・削除記録の索引名を持たない | `api` を足す前提作業で、10章(2)の渡し方に揃える変数を足す(infra)。HO-35 |

### 12.6 ゲート3(2026-11-23)で承認した案

本書の ID のうち、区分が「案」だったもの(実装形が案を含むものを含む)は、すべてゲート3(2026-11-23)で現案どおり承認され、「承認済みの案(ゲート3。2026-11-23)」になった(A 9.3 の G3-6・G3-14〜21 に要点、G3-23 に残りの ID の列挙と回答がある)。承認済みの案の引用は、実装形の部分だけを確認した。特に確認した点:

| ID | 確認の要点 |
| --- | --- |
| AAA-P-1・P-2・P-3 | 読み取りの許可リストと `mget` の使い分け、クエリ形(読み取り専用の保証の具体) |
| AAA-P-5 | 検索インデックスの読み取り条件(IA U-30 への回答)。Indexer 設計への反映は HO-15 |
| AAA-P-18 | `stalled` の偽陽性を避ける確認読み(B 2.9 の「ロック → ジョブ」の実現方法。B 2.9・AAPI-P-27 に反映済み) |
| AAA-P-19・P-25 | `rerunnable` の評価順(`source_missing` は AAPI-P-41)、読めない値の `null`(B の型に反映済み。AAPI-P-25) |
| AAA-P-8 | 再試行の条件(`retry_on_timeout=False`・接続エラーの再試行・`retry_on_status` の 5 値)は BAPI-P-12 の明確化分で、承認済みの案(ゲート3。2026-11-23)。`retry_on_status` は A 5.6 の「5xx」より狭い |
| AAA-P-14 | `job_id` の `.` を `%2E` に置換する(代案は B 2.12 の検証で `.`・`..` だけの `job_id` を拒否) |
| AAA-P-24 | `just_acquired` の猶予の同期方法(環境変数 + compose の同値定義) |
| AAA-P-30 | 本書で足した環境変数(OpenSearch の認証・TLS を含む。A 4 に反映済み) |
| AAA-P-33・P-42 | `async def` + 区分別の上限による枯渇対策(A 2.1・BAPI-U-6 に反映済み)と、EP-13 の期限後の放棄(`abandon_on_cancel=True`。枠の外にスレッドが残る) |
| AAA-P-39 | 部分的な失敗(`mget` の文書単位の `error`、検索の `_shards.failed`・`timed_out`)を成功と読まない |
| AAA-P-40・P-41 | `urllib3.exceptions` の import 範囲、`CRAWLER_URL`・`INDEXER_URL` の `http` 限定と `SSLError` の 503(A の BAPI-P-22・24 と同じ) |
| AAA-P-43 | `WEB_DIST_DIR` の既定 `/app/web` |
| AAA-P-44 | `JobBrief` の各項目の規則(未知の値は `null`)と、読めない `job_type`・`status` の `rerunnable` |
| I-90・I-93 | 索引名の渡し方(compose への要求。infra の前提作業に直結。HO-35) |
| AAA-P-45 | 一覧の `unavailable` の行単位化(AAPI-P-42)と失敗の帰属の規則。AAA-P-25・P-35 の修正を含む(PR #10 のレビュー指摘への対応) |

### 12.7 B 11.10 の全項目の割り当て

| B 11.10 | 項目 | 本書 |
| --- | --- | --- |
| 1 | `lock_state` の 7 値の判定順序 | 5.1 |
| 1 | `stalled`・`cancellable` | 5.2 |
| 1 | `latest_for_source`・`rerunnable`・`rerun_blocked_reason`・`cancel_after_finish_notice` | 5.3 |
| 1 | `registration.phase` | 5.4 |
| 1 | `last_crawl`・`last_completed_at`・`delete_job`(`loreley-jobs` の集計の形) | 5.5、3.3 の R-3 |
| 1 | `existence` | 5.6、3.3 の R-11 |
| 1 | `ttl_days`・`ratio_threshold_percent` の変換(十進数) | 5.7 |
| 1 | `just_acquired` の猶予 60 秒と Crawler の仮値の同期(AAPI-U-6) | 5.9、7.2 |
| 2 | `loreley-sources` の全件取得 | 3.3 の R-1 |
| 2 | `loreley-jobs` の最新ジョブの集計、ロック文書の `mget` | 3.3 の R-3・R-4・R-5 |
| 2 | 検索インデックスの `source_id` ごとの件数、X1 の件数(`msearch`)、ID の一括取得 | 3.3 の R-9・R-11 |
| 2 | `deletion_result-{job_id}` の取得 | 3.3 の R-8 |
| 2 | `cluster.health`・`cat.*` の `h=`・`bytes=b`・`format=json` と値の型の正規化 | 3.4 |
| 2 | `track_total_hits`、取得の窓(10,000)、refresh 遅延、スキーマ依存 | 3.2、3.5 |
| 2 | 索引名の環境変数(エイリアス `loreley-documents`) | 7.2、I-90 |
| 2 | 検索インデックスの読み取り条件(IA U-30) | 3.6 |
| 2 | 読み取り専用の保証(書き込みメソッドを持たない) | 2.3、3.2 |
| 3 | 環境変数の個別一覧と既定 | 7.2・7.3 |
| 4 | 仮値(Crawler 3 秒・60 秒、OpenSearch 10 秒・2 回、確認 3 秒、窓、O1・X1 の上限、猶予 60 秒、本文 1 MiB) | 9章 |
| 5 | Crawler クライアント(urllib3 の設定・再送なし・リダイレクト非追従・タイムアウト) | 4.1 |
| 5 | 例外から 503 `crawler_unreachable`・504 `crawler_response_lost` への分類 | 4.3 |
| 5 | `message`・`details` の取り込みと `config_invalid` の分解の実装 | 4.4・4.5 |
| 5 | スレッドプールの枯渇対策(BAPI-U-6) | 8.1〜8.3 |
| 6 | `/healthz` と opensearch-py の例外の分類(`abnormal`・`undetermined`) | 6.2 |
| 6 | 並行確認の実装 | 6.1 |
| 6 | `web` の確認、任意コンポーネントの `not_configured` | 6.3 |
| 7 | 失敗の理由コードの付け方(例外の種類との対応) | 5.8 |
| 7 | `malformed` の判定規則 | 5.8 |
| 7 | `warnings` の通し方 | 5.4 |
| 8(a) | `job_id`・`source_id` の全文字パーセントエンコード、特殊文字の挙動(AAPI-U-12) | 4.8、4.4、AAA-U-4 |
| 8(b) | `lock_state` の排他的な定義、ロック → ジョブの順の読み(`stalled` の偽陽性) | 5.1、5.2 |
| 8(c) | 死活のプローブのリダイレクト非追従、確認先の URL は環境変数だけ(SSRF の予防) | 6.1、6.4 |
| 8(d) | 応答の `ratio_threshold_percent` の十進数の厳密な変換(AAPI-P-38) | 5.7 |
| 8(e) | `unavailable` のキーは正式なパス | 5.8 |
| 8(追加。作業記録 0014) | EP-07 の `job_id` 起因の 400・404 `not_found` を 404 `job_not_found` に写す(AAPI-P-39) | 4.4 |
| 8(追加。作業記録 0014) | CORS を許可しないことのテスト観点 | 11章の 11 |
| 9 | テスト観点(偽物での写像表・障害別挙動・部分失敗・ページングの窓) | 11章 |

(注: 本書の作成時に A・B へ依頼した追記は、A・B に反映済み(作業記録 0020): B の `null` を許す型(AAPI-P-25)、B 2.9 の確認読み(AAPI-P-27)、`rerun_blocked_reason` の `source_missing` と `rerunnable=null` の条件(AAPI-P-41)、`timeout` 優先と `ttl_days` の `unavailable` のキー、A 4 の OpenSearch の接続情報と共通設定、A 5.6 の再試行の条件、A 2.1・BAPI-U-6 の実行モデル、A 8 の環境変数。解消扱い。)
