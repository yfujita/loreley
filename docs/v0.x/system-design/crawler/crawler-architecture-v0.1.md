# Crawler アーキテクチャ設計書 v0.1

- 版: v0.1
- 更新日: 2026-11-13
- 前版: なし(初版)
- 位置づけ: Crawler の設計(責務と境界、データモデル、ジョブ、ロック・リース、リトライ・スキップ、Indexer との連携、ソース削除、障害)を、Indexer 設計書と突き合わせたうえで本書だけで読めるようにまとめた設計書。あわせて、Crawler 設計書全体の課題の横断一覧(13.8)を持つ。
- 本書は「案」「推測」「未決」を確定扱いにしない。ユーザー承認済みの事項だけを「確定」とし、本書の確定は Indexer 設計書(`indexer-api-v0.10.md`、`indexer-architecture-v0.10.md`)・PD v0.19 でユーザーが承認済みの事項と、ユーザー回答(Q1〜Q3)の内容に限る(13.2)。SD v0.8 の「案」と、Indexer 設計書の「案(Indexer 実装で採用中)」は案のまま扱う。数値は「仮値・設定可能・未決」とする(CA-U-1)。

区分の凡例(Indexer 設計書に合わせる):

| 区分 | 意味 |
| --- | --- |
| 確定 | ユーザーが確定した事項(出典を書く) |
| 案 | ユーザー未確定。確定扱いにしない |
| 未決 | 決めていない |
| 推測 | 根拠が弱い想定。推測と注記した事項 |
| 導出 | 他の仕様から導いた事項(明示された記述がなく、本書で導いた事項) |

ID 体系: 本書の確定・案・未決は `CA-K-n` / `CA-P-n` / `CA-U-n`。既存設計との不整合は `I-n`(本書の予約範囲は I-7〜I-9。I-1〜I-6 の定義は 13.5、interface の I-10・I-11 は 13.8 に載せる)。interface の `CI-K` / `CI-P` / `CI-U` は `connector/connector-interface-v0.1.md` のもの。

関連文書:

| 文書 | 内容 | 本書との関係 |
| --- | --- | --- |
| `crawler/connector/connector-interface-v0.1.md`(以下 interface) | Connector の抽象、`external_id`・`document_id`・`content_hash` の規則、エラー分類名と属性 | 識別子規則とエラー分類名の正本。本書は再掲せず参照する |
| `crawler/crawler-api-v0.1.md` | Admin API -> Crawler の契約 | 本書はジョブ側の挙動だけを書く |
| `crawler/connector/connector-file-system-v0.1.md`、`connector-web-v0.1.md` | Connector 固有の設定・列挙・取得 | `connector_config` は本書では不透明に扱う |
| `crawler/crawler-module-structure-v0.1.md` | モジュール構成 | 本書の責務・並行モデルの要件を実装に落とす |
| `indexer/indexer-api-v0.10.md`(以下 api) | Crawler -> Indexer の契約 | 契約は再掲せず参照する。本書は呼び出し順と Crawler 側の扱いを書く |
| `indexer/indexer-architecture-v0.10.md`(以下 arch) | Indexer の設計(K 番号、P 番号、U 番号) | 同上 |
| `apps/indexer/README.md` 3・6・9 章、`apps/indexer/src/loreley_indexer/infrastructure/opensearch/jobs.py`、`common/locks.py`、`infra/opensearch/schema/jobs.json` | Indexer 実装の事実の確認元(13.1) | ロック文書・メンテナンスフラグの形式の確認 |

決定事項の出典として、SD v0.8(1.2、1.3、3.1、3.3、4.1〜4.7、14 章)と PD v0.19(4.1、4.7、4.8、5.1、5.2、9.2)を参照した。SD v0.8 は廃止予定のため、本書は自文書で完結させ、SD への参照は出典の注記にとどめる。

---

## 1. 位置づけと前提

### 1.1 範囲

- 本書が定める: ジョブの状態と遷移、ロック・リース・ハートビート、リトライ・スキップ・連続 20 件の規則、スキップ記録、登録結果の集計、削除結果の確認結果の区分、`loreley-sources`・`loreley-jobs` のデータモデル、Crawler -> Indexer の連携(呼び出し順・バッチ化・再送・終了通知・ポーリング・エラー別の扱い)、ソース削除ジョブ、障害と再起動。
- 本書が定めない(参照のみ): Indexer API の契約(api)、`external_id` 規則・`document_id` 算出・`content_hash`・エラー分類名(interface)、Admin API -> Crawler の契約(crawler-api)、Connector 固有の設定・列挙・取得(各 Connector 文書)、Python のモジュール構成(crawler-module-structure)。

### 1.2 前提

- MVP は単一ホスト・単一 Crawler・単一 Indexer・直列実行・認証なし(プロダクト設計の前提)。バックエンドは Python。
- Crawler と Indexer は同じホストの時計で動く(arch 2.5。時刻ずれは想定しない)。
- 数値(バッチ件数・サイズ、タイムアウト、リース時間、ハートビート間隔、ポーリング間隔・上限時間、リトライ回数)は「仮値・設定可能・未決」とする(arch K39 に準拠。11章。CA-U-1)。

### 1.3 本書が正本となる事項

ジョブ状態、ロック・リース・ハートビート、リトライ・スキップ・連続 20 件の規則、スキップ記録、登録結果の集計、確認結果の区分、`loreley-jobs`・`loreley-sources` のデータモデル、Crawler -> Indexer の連携。他文書は参照のみとする。

### 1.4 設計原則(導出)

1. **削除は安全側に倒す**。迷ったときは、ジョブを `failed` にして終了通知で削除させない。誤削除は取り返しがつかず、削除の遅れは次のクロールで取り戻せるため(arch 9.13)。
2. **Indexer に見せる値は固定する**。設定スナップショットと終了通知の内容はジョブごとに固定し、再送では同じ値を送る(CA-K-5、CA-K-6)。
3. **ジョブの status と削除結果は切り離す**(CA-K-4)。ジョブは列挙と登録の結果だけを表す。
4. **Crawler は検索インデックスと `loreley-deletions` を読まない**。Indexer の状態は Indexer API(Status API)だけで知る。
5. **所有権は常に確かめる**。ロックを失った Crawler は、以降 Indexer に書き込みを要請しない(5章)。

---

## 2. 責務と境界

### 2.1 論理構成

```text
Admin API(別コンテナ `api`)
        |  HTTP(クロール起動・取り消し・ロック解放・設定の登録/更新/削除・ソース削除。契約は crawler-api)
Crawler(別コンテナ `crawler`)
 受付 / Job Runner(直列実行) / Scheduler(定期起動) / ハートビート / Indexer クライアント
        |                         |                              |
 データソース                   Indexer(別コンテナ)           Store 層(OpenSearch)
 (Connector 経由。FS は :ro)      HTTP: 開始通知・last-seen・     loreley-sources
                                  バッチ登録・終了通知・Status・    loreley-jobs
                                  ソース削除 1〜3
```

- Crawler は Connector(interface)を呼んでデータソースを列挙・取得し、Indexer に渡す。Connector は Indexer・ジョブ・ロックを知らない(interface 1.4)。
- Admin API は `loreley-jobs` を読み取りのみで直接読み、起動などの操作だけを Crawler に中継する(CA-K-2、CA-K-19)。データソース設定の表示(PD 4.6 の Admin View)のために、`loreley-sources` も読み取りのみで直接読む経路を想定する(案。CA-P-46。経路の決定は Admin API 設計時。CA-U-12、crawler-api の CAPI-U-2)。

### 2.2 責務分担

| 責務 | 担当 |
| --- | --- |
| ジョブ(状態、起動の受付、直列実行)、ロック、リース、ハートビート | Crawler |
| `loreley-jobs` と `loreley-sources` への書き込み | Crawler(唯一)。Admin API は書かない。メンテナンスフラグの書き込み手段だけは別(運用者の手動手順。案。3.4。CA-U-3) |
| `loreley-deletions` と検索インデックスへの書き込み | Indexer(唯一)。Crawler は書かない(期限による削除も要請しない。ソース削除の要請だけが例外。8章) |
| データソースの列挙、原本の取得、定期起動 | Crawler(Connector を使う) |
| `external_id`・`document_id`・`content_hash` の算出と検証、孤立サロゲートの処理 | Crawler(共通処理。interface 5章) |
| リトライ・スキップの判断、連続 20 件の打ち切り | Crawler(6章)。Indexer は文書単位の失敗種別を返すだけ |
| 開始通知・終了通知の送信、Status API のポーリング、結果の要約と確認結果の区分の記録、バッチ応答の集計 | Crawler(7章) |
| 削除の判断(割合ルール、件数照合、対象の決定)、世代の管理、削除の実行 | Indexer。Crawler は関与しない |
| 抽出・正規化、要約、書き込み前のロック所有確認 | Indexer(Crawler は `lock` を要請に添える) |
| しきい値の範囲の検証 | Admin API(CA-K-16)。Crawler は検証しない |
| ジョブ状態・登録結果・削除結果の表示 | Admin API(`loreley-jobs`・`loreley-deletions` を読み取りのみで読む) |
| データソース設定の表示 | Admin API(`loreley-sources` を読み取りのみで読む。案。CA-P-46) |

### 2.3 インデックスごとの書き込み役

| インデックス | 内容 | 書く | Crawler が読むか |
| --- | --- | --- | --- |
| `loreley-sources` | データソース設定(3.2)。Admin API は表示のために読み取りのみで直接読む(案。CA-P-46) | Crawler(Admin API は crawler-api 経由で中継) | 読む |
| `loreley-jobs` | ジョブ、ロック文書、スキップ記録、原本サイズ超過記録、メンテナンスフラグ(3.3) | Crawler(メンテナンスフラグだけ運用者の手動手順。案) | 読む |
| `loreley-deletions`(仮名) | 削除の記録 | Indexer のみ | 読まない(Status API 経由) |
| 検索インデックス | 文書の唯一の正本 | Indexer のみ | 読まない |

- `loreley-texts` は使わない。文書の正本は検索インデックスで、Crawler は本文を保存しない(I-3)。
- Indexer は `loreley-sources` を読まず、`loreley-jobs` からはロック文書とメンテナンスフラグだけを読む(arch 2.3)。

### 2.4 通信方針

- Crawler と Indexer は別コンテナで、メッセージブローカーを介さず HTTP で直接通信する(確定。CA-K-1)。内部ネットワークだけで通信し、ホストに公開しない。Indexer API は認証がなく、`DELETE` でソースの全文書を削除できる(api 3.1)。
- Crawler から Indexer への登録は同期 HTTP で、応答を確認しながら進める(api 2)。遅い Indexer がクロール全体の所要時間を決める。MVP では許容する。
- Crawler の HTTP クライアントの要件は 7.10 にまとめる(`DELETE` の JSON ボディを含む)。

### 2.5 時刻の前提

- 時刻はすべて UTC の ISO 8601・ミリ秒精度(例 `2026-11-13T01:02:03.456Z`)で書く(案。CA-P-38)。Indexer が同じ形式に正規化して扱うため(api 3.6)、揃えておくと比較でずれない。
- ロック文書の `lease_expires_at` はタイムゾーン付きでなければならない。オフセットのない値は、Indexer の実装がロックを所有していないものとして扱う(13.1)。

---

## 3. データモデル

### 3.1 Repository と索引の作成担当

- Crawler は Store 層(`loreley-sources`、`loreley-jobs`)を Repository インターフェース経由で読み書きする(arch 3.5 と同じ方針)。必要な操作(案。CA-P-37): ID による取得、存在しない場合だけ成功する作成(`create`)、読んだ版を条件にした置き換え(`if_seq_no`/`if_primary_term`)、読んだ版を条件にした削除、単純な条件での一覧、ID の一括削除。
- Indexer 実装の Store 層の操作は、取得・一覧・無条件の保存・条件付きの置き換え・無条件の削除で、`create` と条件付きの削除はない(13.1)。ロックの取得(5.2)には `create` が要るため、Crawler 側で用意する。
- **索引とマッピングの作成担当は未決**(I-6、CA-U-11)。Indexer は索引を作らない。現行の `infra/opensearch/schema/jobs.json` は、Indexer が読む 4 項目(`owner`・`job_id`・`lease_expires_at`・`enabled`)だけを定義した、結合テスト用の仮定義(`dynamic: false`)である(13.1)。Crawler が 3.3 の項目を一覧・並べ替えに使うには、定義の追加が要る。そのとき、Indexer が読む 4 項目の型(`owner`・`job_id` は keyword、`lease_expires_at` は date、`enabled` は boolean)は変えられない(型に合わない値は書き込みが拒否される。13.1)。`loreley-sources` の索引は、現状作成物がない。
- **マッピングの案**(案。CA-P-49。決定は CA-U-11 のまま。3.2・3.3 の項目から導ける範囲):

  | 索引 | 項目 | 型 | 使う場面 |
  | --- | --- | --- | --- |
  | `loreley-jobs` | `record_type`、`source_id`、`job_id`、`job_type`、`status`、`trigger`、`owner`、`document_id`、`last_job_id` | keyword | 種類・ソース・状態での一覧、スキップ記録の整理(6.4)、ジョブの取得。`owner`・`job_id` は Indexer が読むので keyword で固定 |
  | `loreley-jobs` | `queued_at`、`started_at`、`finished_at`、`heartbeat_at`、`acquired_at`、`first_skipped_at`、`last_skipped_at`、`first_detected_at`、`last_detected_at` | date | 並べ替え(`queued_at` の順の実行)、定期起動の起点(4.3)、受付途中のロックの判定(5.4) |
  | `loreley-jobs` | `lease_expires_at` | date | Indexer が読む。null を許す(`queued` のロック)。型は変えられない |
  | `loreley-jobs` | `enabled` | boolean | Indexer が読むメンテナンスフラグ。型は変えられない |
  | `loreley-jobs` | `settings_snapshot`、`finish_notice`、`registration`、`deletion_summary`、`warnings` | object(索引しない) | 表示用。`_source` から読む(件数が多い ID 一覧を含みうる) |
  | `loreley-sources` | `source_id`、`connector_type`、`status` | keyword | 一覧・絞り込み |
  | `loreley-sources` | `ttl`、`min_delete_count`、`schedule_interval_seconds` | long(整数) | Indexer に渡す値の型を保つ |
  | `loreley-sources` | `ratio_threshold` | double | 同上 |
  | `loreley-sources` | `updated_at` | date | 更新日時 |
  | `loreley-sources` | `connector_config` | object(索引しない) | 不透明 |

  `dynamic` の設定(`strict` にするか)と、作成の担当は未決(CA-U-11)。型に合わない値は書き込みが拒否される(13.1)。
- Crawler の Store 層への書き込みに失敗したときの扱いは 9章。

### 3.2 `loreley-sources`(データソース設定)

ID は `source_id`。共通項目と `connector_type`、`connector_config` だけを本書が定める(案。CA-P-36)。

| 項目 | 型 | 説明 |
| --- | --- | --- |
| `source_id` | string | ID と同じ値。登録後は変更できない。Indexer の検証(空でない、制御文字なし、UTF-8 で 256 バイト以内)を満たす値だけを登録できる(CA-K-13。文字種の制限は CA-U-15。案は crawler-api の CAPI-P-15) |
| `connector_type` | string | Connector の実装を選ぶ識別子。値は `file_system`(MVP)、`web`(将来)とする(案。綴りは各 Connector 文書と合わせる。interface 8章) |
| `connector_config` | object | Connector 固有の設定。本書と crawler-api は中身を見ない(不透明)。固有項目の定義と検証は各 Connector 文書と Connector が持つ(interface 8章)。認証情報は参照名だけを持ち、平文を保存しない(PD 4.8) |
| `ttl` | integer | 期限の秒数(開始通知の設定スナップショット。型は arch K59)。既定値は Indexer 側でも未決(arch U-1) |
| `ratio_threshold` | number | 割合ルールのしきい値。範囲(0 以上 1 未満)の検証は Admin API だけ(CA-K-16)。Crawler は検証しない |
| `min_delete_count` | integer | 削除の最小件数 |
| `schedule_interval_seconds` | integer または null | 定期起動の間隔(秒)。null は手動のみ(案。周期形式は CA-U-8) |
| `status` | `active` / `deleting` | `deleting` は、ソース削除ジョブの実行中・中断中(8章。案。置き場所の最終決定は CA-U-2) |
| `updated_at` | datetime | 更新日時 |

- `ttl`・`ratio_threshold`・`min_delete_count` の未指定(欠損)の扱いと、更新で値が省略されたときの扱いは、Admin API・crawler-api の領域で未決(arch U-1、U-15)。Crawler は、ジョブの開始時に値が欠けている、または型が合わない場合は、開始通知を送らずジョブを `failed`(理由 `config_invalid`)にする(案)。範囲は検証しない。
- 実行中のジョブは、開始時点(4.5 の手順 6)の設定を使い続ける。設定を更新しても実行中のジョブには反映されず、次のジョブから反映される(案。interface 8章と同じ前提)。ただし `connector_config` はスナップショットの 6 項目に含まれず、手順 8 の `validate_config`・`create` が `loreley-sources` を読んだ時点で確定する。手順 6 と 8 の間の更新は反映されうる(案。許容する)。手順 8 より後は変わらない。
- 設定レコードを削除するのは、ソース削除ジョブの手順 5 だけとする(8章。案)。設定だけを先に消すと、検索インデックスに文書が残るため。

### 3.3 `loreley-jobs`

1 つの索引に、次の 5 種類の記録を置く(案。CA-P-37)。ID の接頭辞が重ならないようにする。

| `record_type` | ID | 書き手 | 内容 |
| --- | --- | --- | --- |
| `job` | `{job_id}`(`job-{UTC 日時}-{16 進 8 桁の乱数}` の形。CA-P-1) | Crawler | ジョブ(3.3.1) |
| `lock` | `lock-{source_id}` | Crawler | ソースごとの実行ロック(3.3.2。5章) |
| `skip` | `skip-{source_id}-{document_id}` | Crawler | スキップ記録(3.3.3。6.4) |
| `oversize` | `oversize-{source_id}-{document_id}` | Crawler | 原本サイズ超過記録(3.3.4。6.5) |
| `maintenance` | `maintenance` | 運用者(手動手順。案。CA-U-3) | メンテナンスフラグ(7.9) |

`job_id` は全ソースを通じて一意でなければならない(Indexer は `crawl_id` だけで削除結果を管理するため。13.1)。ジョブ記録は `create`(存在しない場合だけ成功)で保存するので、`job_id` が衝突すれば保存に失敗して検出できる(導出)。`job_id` で記録を取得したときは、`record_type=job` の記録だけをジョブとみなす(ロック・スキップ記録などの ID を `job_id` として渡されても、ジョブとして扱わない。crawler-api 3.2)。

#### 3.3.1 ジョブ記録(案。CA-P-37)

| 項目 | 説明 |
| --- | --- |
| `job_id` | ID と同じ値。`crawl_id` として Indexer に送る(CA-P-1) |
| `job_type` | `crawl` / `source_delete` |
| `source_id`、`trigger` | 対象のソース。起動の種別(`manual` / `schedule`) |
| `owner` | 実行している Crawler の ID(5.1) |
| `status` | 4.2 の状態 |
| `queued_at`、`started_at`、`finished_at` | 受付・実行開始・終了の日時 |
| `force_delete`、`rewrite_mode` | 受付時の指定(4.4)。スナップショットの元になる |
| `settings_snapshot` | 設定スナップショット(下記)。`queued` -> `running` の遷移時に書き、以降変えない |
| `finish_notice` | 終了通知の固定した内容と、初回の送信の開始時刻(`send_started_at`)(下記) |
| `registration` | 登録結果(7.7) |
| `deletion_summary`、`confirmation` | 削除結果の要約と、確認結果の区分(7.6) |
| `failure_reason`、`failure_detail` | `failed` の理由コード(4.8)と説明。説明は分類名を基本とし、列挙失敗・`create` 失敗では Connector の説明文(固定文 + errno 名 + 切り詰めた相対パス)を、`external_id_collision` では、後に検出された 1 件の切り詰めた `external_id` と、共有する `document_id` を載せてよい(案。CA-P-45。先に列挙された 1 件の文字列は保持していない。7.7)。保存する前に、共通処理が文字数の切り詰め、制御文字のエスケープ、孤立サロゲートの置換を適用する(Connector の担保に加えた二重の防御。案。CA-P-48)。文書の本文・認証情報は含めない。長さの上限は仮値(11章)。interface 6.1 の説明文(`message`)の定義は、interface 側で緩和済み(CI-P-17。長さの上限は本書の仮値に従う) |
| `warnings` | 警告(固定文のコードと件数。件数に上限を置く。仮値) |

- **設定スナップショット**(確定。CA-K-5): `crawl_started_at`、`ttl`、`ratio_threshold`、`min_delete_count`、`force_delete`、`rewrite_mode` の 6 項目。ジョブごとに 1 度だけ組み立てて保存し、開始通知の再送では保存した値をそのまま送る(7.4)。再送のたびに設定を読み直さない(読み直すと、設定変更が間に入ったとき値が変わって 409 `crawl_start_conflict` になり、ジョブが `failed` になる。api 4.1)。
- **終了通知の固定した内容**(確定。CA-K-6): 送る JSON 本文(`outcome`、`enumerated_count`、ID 一覧、`finished_at` など)を、最初の送信の前に `finish_notice` に保存する。送信の開始の時刻は別に `send_started_at` に記録する(案。CA-P-42。7.5)。再送では常に保存した内容を送る(7.5。再送で内容が変わると 409 `finish_content_mismatch`)。

#### 3.3.2 ロック文書

形式と運用は 5章。Indexer が読む項目は `owner`・`job_id`・`lease_expires_at` の 3 つ(13.1)。

#### 3.3.3 スキップ記録(案。CA-P-22)

SD v0.8 3.1(案)の項目を引き継ぐ。`document_id` は interface 5.2 の算出値。

| 項目 | 内容 |
| --- | --- |
| `source_id`、`document_id`、`external_id` | 対象の識別(`external_id` は規則適用後の値) |
| `stage` | 失敗した段階(`fetch` / `index`) |
| `reason` | 失敗の分類(interface 6.2 の分類名、または Indexer の失敗種別名)と短い固定文。本文・秘密情報は含めない |
| `attempts` | 直近のクロールでの試行回数 |
| `consecutive_skips` | 連続してスキップされたクロール数 |
| `first_skipped_at`、`last_skipped_at`、`last_job_id` | 最初・直近にスキップした日時と、直近のジョブ ID |

#### 3.3.4 原本サイズ超過記録(案。CA-P-23)

| 項目 | 内容 |
| --- | --- |
| `source_id`、`document_id`、`external_id` | 対象の識別 |
| `detected_by` | 拒否した側(`crawler` / `indexer`) |
| `size` | 原本のサイズ(バイト)。分かる場合だけ(`size_hint` か申告値) |
| `first_detected_at`、`last_detected_at`、`last_job_id` | 最初・直近に検出した日時と、直近のジョブ ID |

PD v0.19 4.2 が、原本サイズ超過を「文書単位のエラーに記録し、Admin View で確認できる」と決めているため、記録を持つ。記録先・項目の最終決定は CA-U-4(PD 9.2 #8 が未決)。

### 3.4 メンテナンスフラグ

形式は 7.9。書き込み手段は未決(arch U-24。CA-U-3)。

### 3.5 保持期間

ジョブ記録の保持期間は未決(CA-U-5。arch の `deletion_result` の保持件数 N とは別)。スキップ記録・原本サイズ超過記録は、6.4 の規則で消す。

---

## 4. ジョブとライフサイクル

### 4.1 ジョブの種別

| 種別 | 内容 | 起動 |
| --- | --- | --- |
| `crawl` | 列挙クロール。Indexer への通知・登録・削除結果の確認を含む(4.5) | 手動(Admin API 経由)・定期 |
| `source_delete` | データソースの削除(8章) | 手動(Admin API 経由) |

突合ジョブは MVP にない(I-2)。要約生成は Indexer 内部の処理で、ジョブの対象ではない(arch 7.2)。

### 4.2 状態と遷移(案。CA-P-10。SD v0.8 4.1 の状態名を引き継ぐ)

`queued` -> `running` -> `succeeded` / `partially_succeeded` / `failed` / `cancelled`

| 遷移 | 条件 |
| --- | --- |
| `queued` -> `running` | Job Runner が選び、条件付き更新で遷移する(4.5 の手順 6)。このとき設定スナップショットを書く |
| `queued` -> `cancelled` | 実行前に取り消された(4.7) |
| `running` -> `succeeded` | 列挙が最後まで完了し、終了通知の 202 を確認し、ポーリングを終えた(確認結果の区分は 7.6)。スキップ・識別子エラー(下記)がない。成否は、受理の確認の結果に依存しない |
| `running` -> `partially_succeeded` | 同上で、スキップした文書(`skipped_count` が 1 以上)、または識別子エラー(`invalid_external_id`。CA-P-25)がある |
| `running` -> `failed` | 4.8 の異常 |
| `running` -> `cancelled` | 取り消された(4.7) |

- `running` の間は、列挙・登録・終了通知・削除結果のポーリング(7.6)のすべてを含む。ジョブは、Indexer の削除結果が終端状態になる(またはポーリングを打ち切る)まで完了しない(PD 4.7。CA-K-4)。最終状態は、ポーリングの終了後に記録する。
- 抽出失敗(`extract_failed`)と原本サイズ超過(`oversize`)は、ジョブの最終状態に影響しない(案。CA-P-10、CA-P-23。サイズ超過の影響の最終決定は CA-U-4)。
- 削除結果が `skipped_by_ratio` や `validation_failed` などで削除されなかったことは、ジョブの失敗にしない(確定。CA-K-4。削除結果の状態は Indexer が持ち、ジョブには要約を残すだけ)。
- 終端状態は `succeeded` / `partially_succeeded` / `failed` / `cancelled`。リース切れの `running` は、Admin API が `failed` として表示する(5.4。表示の詳細は CA-U-12)。

### 4.3 起動

- **手動**: Admin API が crawler-api 経由で要求する。`force_delete`・`rewrite_mode` を指定できる(4.4)。
- **定期**: Scheduler が `schedule_interval_seconds` ごとに起動する(案。CA-P-12)。次回の起動時刻は、直近に受け付けたクロールジョブの `queued_at` に間隔を足した時刻とする(状態を別に持たない。導出)。そのソースのロックを保持するジョブがあるときは、その回を見送る(受付の待ち行列を作らない)。Crawler が止まっていた間の複数回分の起動は取り返さない(再開後に、期限を過ぎていれば 1 回だけ起動する)。そのソースで初めて定期起動する場合(クロールジョブがない場合)の起点は、設定の登録・更新時刻とする(案)。`status=deleting` のソースは起動しない。起動は、Scheduler が受付と同じ処理(下記の受付の手順)を呼んで行う(受付処理の共通化は module-structure で決める前提。5.3)。
- **受付の手順**(案。CA-P-4)。受付は同期で、成功なら受付応答(ジョブ ID)を返す。
  1. `loreley-sources` を読む。設定がない、または `status=deleting` なら拒否する(ソース削除中は新しいクロールを起動しない。確定。CA-K-11 の要件(4))。
  2. メンテナンスフラグを読む。立っていれば拒否する(7.9。CA-P-34)。
  3. ロック文書を `create` する(5.2)。すでにあれば拒否する(既存ジョブの状態を応答に含める。拒否の応答形式は crawler-api)。
  4. `loreley-sources` を読み直す。手順 1〜3 の間にソース削除が入っていれば、ロック文書を削除して拒否する(導出。ソース削除ジョブも同じロックを取るため、手順 3 に成功した側だけが進める)。
  5. ジョブ記録(`queued`)を保存して応答する。手順 3 と 5 の間で止まるとジョブのないロック(孤児ロック)が残る。起動時の回復で消す(5.8)。
- 実行は直列で、Job Runner は `queued` のジョブを `queued_at` の順に 1 件ずつ実行する(案。CA-P-11)。同じソースに `queued` または `running` のジョブは 1 つしか存在できない(ロックが 1 つだけのため)。

### 4.4 `force_delete`・`rewrite_mode`(案。CA-P-13)

- `force_delete` は手動実行の起動時だけ指定でき(確定。CA-K-17)、`rewrite_mode` も手動実行だけにする(案)。定期起動では、どちらも常に `false` にする(案。SD v0.8 14.4 の `force_delete` の規則に合わせる)。
- 指定はジョブ記録に残し、設定スナップショット(3.3.1)の元にする。実行中のジョブが同じソースの重複起動で受け取った指定は反映しない(拒否される。4.3)。
- `rewrite_mode` を起動の指定に加えるのは本書の追加(I-4。SD v0.8 14.4 に記載がない)。Indexer 側の根拠は arch K26・K41(確定)。`rewrite_mode=true` のクロールの前に Indexer の要約生成を止めて終えておく手順は運用の事項で、Indexer の README が定める(README 8章。本書は定めない)。

### 4.5 クロールジョブの処理フロー

呼び出しの詳細は 7章、リトライ・スキップは 6章。実行は Job Runner が直列に行う。

| 手順 | 内容 |
| --- | --- |
| 1〜5 | **受付**(4.3。crawler-api からの起動の同期処理。ロックの取得とジョブ `queued` の保存を含む) |
| 6 | **実行開始**: ロック文書の `lease_expires_at` を設定する(所有の確認を兼ねる)。続けて、ジョブ記録を条件付き更新で `queued` -> `running` にし、`started_at` と設定スナップショット(`crawl_started_at` は、この時点の時刻。CA-P-14)を書く。設定の値が欠けている・型が合わないときは `config_invalid` で `failed`(3.2)。条件付き更新に負けた(取り消された)ときは、ロックを解放して止める |
| 7 | メンテナンスフラグを再度確認する(立っていれば `failed`、理由 `maintenance`) |
| 8 | `loreley-sources` を読み(`connector_config` はこの時点で確定。3.2)、`ConnectorType.validate_config` で保存済みの設定を確認し、`create` で Connector を作る(interface 3.2)。失敗したら(`transient` はリトライ後。6.2)、開始通知を送らずに `failed` にする(`config_invalid` または `enumeration_failed`)。このため、事前確認の専用操作は置かない(CA-P-15。interface CI-U-6 への対応) |
| 9 | **開始通知**を送る(7.2、7.4) |
| 10 | **列挙・last-seen・取得・登録**をチャンク単位で繰り返す(4.6) |
| 11 | 列挙が `Completed` で、すべての応答を確認し終えたら、登録結果を `partial=false` で確定し(7.7)、スキップ記録・原本サイズ超過記録を整理し(6.4)、**終了通知**(`enumeration_completed`)の内容を固定して送る(7.5)。202 を確認する |
| 12 | **削除結果のポーリング**(7.6)。ポーリング中もジョブは `running` で、ハートビートを続ける |
| 13 | 登録結果・削除結果の要約・確認結果の区分を記録し、最終状態を書く。最後にロックを解放する(5.5) |

手順 8 以降で失敗したときの扱いは 4.8。

### 4.6 チャンク処理(案。CA-P-16)

interface の列挙はストリーミングで、`next()` が 1 件ずつ `DocumentRef` を返す。Indexer は、見つけた文書の `last_seen_at` の更新を**取得より前**に要請させる(api 2)。両立させるため、列挙を一定件数(チャンク。仮値)ごとに区切って処理する。

1. 列挙から `DocumentRef` を受け取り、共通処理で `external_id` を処理して `document_id` を算出する(interface 5章)。次の場合を除き、チャンクに加える。
   - `invalid_external_id`: 記録して除外する(CA-P-25。7.7)。
   - 同じ `document_id` が列挙済み: 元の `external_id`(規則適用前)が同じなら重複として捨てる。異なれば `external_id_collision` で、ジョブを `failed` にする(案。CA-P-24。最終決定は CA-U-6。理由は 4.8)。
2. チャンクが満ちる、または列挙が `Completed` になったら、チャンクの `document_id` を **`last-seen` で要請する**(`document_ids` の上限以下に分割する。7.3)。応答の `update_conflict` は上限付きでリトライし、解消しなければ `failed`(6.2)。
3. チャンクの文書を順に取得し(`fetch(ref, max_bytes)`。6.5 の原本サイズ超過の判定を含む)、取得できた原本をバッチに加える。取得に失敗した文書は 6.2 に従い、バッチには入れない。バッチの閉じ条件(7.3)に達したら、手順 4 でそのバッチを登録し、バッチ分の原本を解放してから、取得を続ける(取得と登録はチャンク内で交互に進める)。保持する原本はバッチ 1 つ分まで。
4. バッチを登録し、応答の文書単位の結果を集計する(7.7)。失敗した文書は 6.2 に従って再送またはスキップする。チャンクの最後の文書を取得し終えたら、残りのバッチを閉じて登録する。
5. 次のチャンクへ進む。

- 取り消し・所有権の喪失・メンテナンスフラグは、各リクエストの前と文書の区切りで確認する(4.7、5.7、7.9)。
- 列挙が `Failed` になったら、以降のチャンクは処理しない。それまでに登録した文書はそのまま残る。ジョブを `failed` にし、終了通知は `outcome=failed` で送る(4.8)。
- 共通処理は、列挙した `document_id` の集合を持つ(CA-P-26。7.7)。スキップ・原本サイズ超過の ID の集合と、登録結果の集計(最初の結果の保持を含む)は、`crawl` の実行状態としてジョブ実行が持つ(7.5、7.7)。

### 4.7 取り消し

取り消しは `crawl` ジョブだけを対象にする(案。CA-P-33、CA-P-42。`source_delete` は取り消さず、再実行で復旧する)。契約は crawler-api。ジョブ記録の書き込みは 5.3 の書き手の表。

| 取り消しのとき | 扱い |
| --- | --- |
| `queued` | 条件付き更新でジョブを `cancelled` にし、ロックを解放する(実行開始の条件付き更新と競合したら、先に勝った側が有効) |
| `running` で、終了通知(`enumeration_completed`)の初回の送信を始める前(列挙・登録中。内容の固定後を含む) | 列挙を `close()` し、終了通知を `outcome=cancelled` で送る(内容を固定して送る。届かなくても削除されないので安全。7.5)。ジョブを `cancelled`、登録結果は、集計の確定前なら `partial=true` のまま、確定後(`partial=false` で確定した後。終了通知の内容の固定後を含む)なら `partial=false` のまま記録し、ロックを解放する |
| `running` で、終了通知(`enumeration_completed`)を送った後(ポーリング中を含む) | 削除処理は止まらない(CA-K-9)。ポーリングを打ち切り(確認結果の区分は `unconfirmed`。案)、ジョブを `cancelled`、登録結果は `partial=false` のままにし、ロックを解放する |

「送った後」とは、`outcome=enumeration_completed` の終了通知の初回の送信を始めた時点(`finish_notice` に `send_started_at` を記録した時点)以降とする(その後は Indexer が受理しているかもしれないため。導出)。送信を始めた後に取り消されたときは、送信中(リトライ中)ならリトライをやめ、Indexer に届いたかどうかは不明のまま確認結果の区分は書かない(削除が進みうることは CA-K-9 のとおり。案。CA-P-42)。内容の固定だけで送信を始めていない間の取り消しは「送る前」として扱い、`enumeration_completed` を送らずに `outcome=cancelled` を新たに固定して送る(7.5。案)。`failed`・`cancelled` の通知の記録は、これに当たらない。

**取り消し要求の伝達**(案。CA-P-44): `running` のジョブへの取り消しは、API 側が、`job_id` をキーにした Crawler プロセス内のメモリ上の取り消し要求(フラグ)に記録して 202 を返す(単一 Crawler の前提。ジョブ記録は書かない)。

- Job Runner は、確認点(4.6 の「各リクエストの前と文書の区切り」、リトライの待ち、ポーリングの待ち)でフラグを参照し、立っていれば上の表の扱いにする。長い待ちの間も、一定の間隔でフラグを見られるようにする(待ちを中断できること。connector-web 4.3 の論点 D、interface 3.1 のペーシングの記述)。ジョブが終端状態になったら、フラグを消す。
- 要求を受け付ける側は、ジョブ記録を読んで状態を判定する(`queued` なら上の表の `queued` の行、`running` ならフラグ、終端状態なら拒否。crawler-api 4.2)。同じ要求が重なってもフラグは 1 つで、結果は 1 回と同じ。
- Crawler が再起動するとフラグは失われる。しかし再起動で `running` のジョブは 5.8 で `failed`(`crawler_restart`)になるので、取り消し要求の消失と整合する(取り消し要求を受け付けたまま再起動したジョブは、`cancelled` ではなく `failed` で終わる)。
- リース切れの `running`(Crawler が止まっている、ハートビートが切れているなど)は、確認点に達せず取り消しが完了しないことがある。その場合は、ロック解放(5.4。crawler-api 4.3)で `failed`(`lock_released`)にする。
- `crawl` ジョブも同じで、確認点に達しない(中断できない呼び出しの途中など)ときの脱出は、Crawler の再起動による回復(5.8)だけ(MVP)。その間もハートビートは独立して続くので、リースは切れない。
- この方式は、API 側の処理と Job Runner が同一の Crawler プロセスにあること(単一プロセス。MVP)を前提にする(案)。
- crawler-api 4.2 の「要求は実行中に保持され、次の確認点で反映される」と整合する(その方式をここで定めた)。

### 4.8 異常系と終了状態(案。CA-P-10)

`failure_reason` は Crawler が付ける理由コード(名称は案)。Indexer 側の `reason`(削除結果の `failed` の理由など)とは別の名前空間。

| 状況 | ジョブ | `failure_reason` | 終了通知 |
| --- | --- | --- | --- |
| `validate_config`・`create` の失敗(開始通知の前) | `failed` | `config_invalid` / `enumeration_failed`(Connector の説明文を `failure_detail` に。3.3.1) | 送らない |
| 開始通知の失敗(リトライ尽き、409、400) | `failed` | `indexer_unavailable` / `indexer_rejected` | 送らない |
| 列挙の `Failed`(`source_*`、`enumeration_incomplete`、`connector_internal_error`(列挙時)) | `failed` | `enumeration_failed`(分類名と Connector の説明文を `failure_detail` に。3.3.1) | `failed` |
| `external_id` の衝突 | `failed` | `external_id_collision`(後に検出された 1 件の切り詰めた `external_id` と、共有する `document_id` を `failure_detail` に。3.3.1) | `failed` |
| 列挙した文書数が上限を超えた(CA-P-26) | `failed` | `enumeration_too_large` | `failed` |
| 連続スキップが規定の件数に達した(6.3) | `failed` | `skip_limit_exceeded` | `failed` |
| `write_conflict`・`update_conflict` が解消しない(確定。CA-K-10) | `failed` | `conflict_unresolved` | `failed` |
| Indexer への要請が 500・503・接続エラーなどで直らない(7.8) | `failed` | `indexer_unavailable` | `failed`(届かなくてよい) |
| Indexer が 400・409 で拒否した、契約外の応答(7.8) | `failed` | `indexer_rejected` | `failed` |
| `lock_not_owned`、リース切れ・ハートビート失敗(5.7) | `failed` | `lock_lost` | 下記の条件を満たすときのみ `failed`(届かなくてよい) |
| バッチ応答の `document_id` が Crawler の算出値と一致しない(CA-P-27) | `failed` | `document_id_mismatch` | `failed` |
| メンテナンスフラグが立っている(7.9) | `failed` | `maintenance` | 下記の条件を満たすときのみ `failed` |
| 終了通知(`enumeration_completed`)を送れない(リトライ尽き、409) | `failed` | `finish_notice_failed` | (これ以上送らない) |
| Crawler の想定外の例外 | `failed` | `internal_error` | 下記の条件を満たすときのみ `failed`(できれば) |
| Store 層(`loreley-jobs`・`loreley-sources`)への書き込みが、リトライを尽くしても失敗した(9章。CA-P-50) | `failed`(記録できる場合) | `store_unavailable` | 下記の条件を満たすときのみ `failed`(できれば) |
| Crawler の再起動(5.8) | `failed` | `crawler_restart` | 送らない |
| 管理者によるロック解放 | `failed` | `lock_released` | 送らない |

- 「終了通知 `failed`」は、**開始通知が成功した後で、かつ `enumeration_completed` の初回の送信を始める前**(`finish_notice.send_started_at` の記録前)に限り、可能なら送る(CA-P-28)。送信を始めた後(ポーリング中の `lock_lost`、想定外の例外など)は、`failed` の通知を送らない。受理の有無が不明で、別の内容は Indexer が 409 `finish_content_mismatch` で拒否し、7.8 でその 409 が `finish_notice_failed` に写って元の理由を上書きしかねないため(削除が進みうることは 4.7・CA-K-9 と同じ)。内容は `outcome`・`source_id`・`finished_at` だけで、最初の送信前に `finish_notice` に固定する。届かなくても削除されない(arch 4.4)ので、リトライは 7.5 の設定に従い、尽きたら諦める。
- 終了通知が Indexer に受理される前にクロールが失敗した場合は、削除しない。受理された後は、応答が失われてジョブが失敗扱いになっても、削除処理が続きうる(確定。CA-K-9)。このときの結果は、削除結果に残る。

---

## 5. ロック・リース・ハートビート

### 5.1 ロック文書の形式(I-5 への対応。案。CA-P-2)

Indexer が仮に置いた形式(13.1)を、そのまま採用する。食い違いはなく、Indexer 側の修正は要らない。

| 項目 | 型 | 説明 |
| --- | --- | --- |
| ID | | `lock-{source_id}` |
| `owner` | string | 実行している Crawler の ID。安定した ID を設定で与える(再起動の前後で同じ値。案。CA-P-3)。256 バイト以内・制御文字なし |
| `job_id` | string | ロックを持つジョブの ID(`crawl` と `source_delete` の両方) |
| `lease_expires_at` | datetime(タイムゾーン付き)または null | リースの期限。`queued` の間は null(下記)。2.5 の形式で書く |
| `record_type`、`source_id`、`heartbeat_at` | | Crawler が足す項目(Indexer は読まない) |
| `acquired_at` | datetime | ロックを `create` した時刻。`create` 時に必ず設定し、ハートビートでは更新しない。受付の途中のロックの保護(5.4)に使う。Crawler が足す項目(Indexer は読まない) |

- Indexer の所有判定は、`owner` と `job_id` が書き込み要請の `lock` と一致し、かつ現在時刻が `lease_expires_at` より前であること。文書がない・期限切れ・不一致・形式不正は、すべて「所有していない」(13.1。arch 8章)。
- 要請に添える `lock` は、ロック文書の `owner`・`job_id` と同じ値にする(7.2)。
- `queued` のジョブが持つロックは、`lease_expires_at` を null にする(案。リースの失効判定の対象にしない。SD v0.8 4.3 の考え方)。Indexer は null を「所有していない」と扱うが、`queued` の間は Indexer を呼ばないので問題ない。リースは `running` への遷移で設定する(4.5 の手順 6)。リースの値を持つのはロック文書だけで、ジョブ記録には持たない(二重管理を避けるため。案)。
- この形式が確定になるのは、本書の承認後。Indexer 設計書の記述は案(実装で採用中)のままである(I-5)。

### 5.2 取得(案。CA-P-4)

- ロックの取得は、ロック文書の `create`(存在しない場合だけ成功)で行う。すでに存在すれば取得に失敗し、起動を拒否する。
- 取得は受付の時点で行う(4.3)。クロールとソース削除は同じロックを取るので、同じソースで両方が同時に進むことはない。
- リース期限が切れたロックを、別のジョブが自動で引き継ぐことはない(5.6)。

### 5.3 更新(ハートビート。案。CA-P-5)

- ハートビートは、`running` の間、ジョブの実行(同期 HTTP の待ち、リトライの待ち、Connector の呼び出し、ポーリング、ソース削除の応答待ちを含む)とは独立して続ける。ジョブ実行が長い呼び出しの中にいても、リースを更新できること(要件。SD v0.8 4.3 と arch 9.11 の記述。ソース削除については確定。CA-K-11 の要件(1))。実現方法(別スレッドなど)は module-structure で決める(CA-U-10。interface CI-U-9)。
- 間隔はリース時間の 3 分の 1 程度(仮値。リース時間 5 分、間隔 100 秒を仮に置く。リース時間の既定値は PD 9.2 #4 が未決で、確定ではない。CA-U-1)。
- 更新は、自分が直前に書いた版(`_seq_no`・`_primary_term`)を条件にした置き換えで、`lease_expires_at` を現在時刻 + リース時間に、`heartbeat_at` を現在時刻にする。ロック文書を書くのは、受付時の `create`(5.2)、受付の巻き戻し(4.3 の手順 4)、実行開始時のリース設定(4.5 の手順 6)と、実行開始の条件付き更新に負けたときの解放(同手順 6)、この更新、`queued` の取り消し時の解放(4.7)、通常の解放(5.5)、管理者の解放、起動時の回復での削除(5.8)。ハートビートはジョブ記録を書かない。ジョブ記録の書き手は次の表(CA-P-43)。
  - 条件が外れた(409)ときは、ロック文書を読み直す。自分の `owner`・`job_id` で期限内なら、読んだ版で更新をやり直す。文書がない・他のジョブのもの・期限切れなら、所有権の喪失(5.7)とする。
  - Store 層の書き込みが失敗したときは、次の間隔を待たず、短い間隔でやり直す。最後に成功した更新の `lease_expires_at` を過ぎたら、所有権の喪失とする。

- **ジョブ記録の書き手**(案。CA-P-43): ジョブ記録は、Job Runner と、API 側の処理(crawler-api の受付・取り消し・ロック解放)が書く。同時に書く者がいるため、すべての更新は読んだ版(`_seq_no`・`_primary_term`)を条件にし、条件が外れたら読み直して判定し直す。

  | 書く内容 | 書き手 | 方式 |
  | --- | --- | --- |
  | `queued` のジョブ記録の保存(4.3 の手順 5) | API 側(受付)と Scheduler(受付と同じ処理を呼ぶ) | `create` |
  | `queued` -> `cancelled`(4.7) | API 側(取り消し) | 読んだ版を条件にした更新。Job Runner の `queued` -> `running` と競合したら、先に条件に勝った側が有効。取り消しが負けたら読み直し、`running` なら取り消し要求を伝える(4.7) |
  | `running` への遷移と、`running` 以降のすべての更新(登録結果、`finish_notice`、削除結果の要約、確認結果の区分、最終状態) | Job Runner | 自分が最後に書いた版を条件にした更新。条件が外れたら読み直し、状態が `failed`(`lock_released`)などに変わっていれば所有権の喪失(5.7)として止める |
  | `running` -> `failed`(`lock_released`。管理者のロック解放。5.4) | API 側(ロック解放) | 読んだ版を条件にした更新。リース切れの `running` だけが対象。Job Runner の更新が先に入って条件が外れたら、読み直して判定し直す(終端状態か、リース更新が再開していれば何もしない) |
  | `running` -> `failed`(`crawler_restart`)ほか(5.8) | 起動時の回復 | 受付・Job Runner の開始前に行うので、他の書き手と競合しない |

  受付処理を API 側と Scheduler で共通にすることは、module-structure で決める前提とする。Job Runner とハートビートと API 側は別の実行単位で、実現方法(スレッド・非同期など)は module-structure で決める(CA-U-10)。ここで定めるのは、書き手の分担と条件付き更新による競合の防止まで。

### 5.4 リース切れ

- `lease_expires_at` を過ぎたロックは、Indexer から見て「所有していない」。`running` のジョブでリースが切れたものは、Admin API が `failed` として表示する(SD v0.8 4.3。案。判定の方法は Admin API の設計で再確認する。CA-U-12)。
- リース切れだけでは、別のジョブも Crawler もロックを自動で引き継がない。前の Crawler が止まったのか遅いだけなのか区別できないため(案。CA-P-6)。引き継ぎは、Crawler の再起動時の回復(5.8)と、管理者のロック解放(crawler-api)に限る。
- 管理者のロック解放は、ロックを持つジョブが実行中でない(リース切れ、または孤児ロックの)場合だけ受け付ける(案)。解放するときは、読んだ版を条件にロック文書を削除し、`running` のジョブがあれば `failed`(`lock_released`)にする(ジョブ記録の書き込みは 5.3 の書き手の表)。実行中のジョブの中止には取り消し(4.7)を使う。
- **`queued` のジョブのロック**(`lease_expires_at` が null)は、解放の対象にしない(案。CA-P-47。crawler-api 4.3。`crawl` ジョブは取り消しを使う)。**受付の途中のロック**(ロック取得後・ジョブ保存前。4.3 の手順 3〜5)は、ジョブ記録がなくても、`acquired_at` が直近(仮値。11章)のものは孤児ロックとみなさず、解放しない(案。CA-P-47)。受付と解放を直列に処理する方法でもよい。最終決定は crawler-api の CAPI-U-7。

### 5.5 解放(案。CA-P-8)

- ジョブの最終状態を記録した後に、**ハートビートを止めてから**、読んだ版を条件にロック文書を削除する(解放の後にハートビートが書き込まないため。止めた後に更新が走っても、状態を変えない)。読んだ版を条件にするのは、他のジョブのロックを消さないため。条件が外れたときは読み直し、自分のものなら再試行し、そうでなければ何もしない。解放するのは、所有権の喪失を記録しておらず、かつ自分のロックのときだけ(5.7)。
- ロックは、削除結果が終端状態になるまで保持する(api 5、arch 9.11。案)。ポーリングの失敗や上限時間の超過で確認を終えた後は、解放する(同上)。
- 最終状態の記録とロックの解放の間で止まったときは、状態が終端のジョブのロック(孤児ロック)が残る。起動時の回復で消す(5.8)。
- `source_delete` ジョブは、手順の最後(8章)までロックを保持する(確定。CA-K-11)。

### 5.6 引き継ぎ

5.4 のとおり、引き継ぎは Crawler の再起動時の回復と管理者の解放だけ(案)。前の Crawler の停止を確認する方法は、単一 Crawler・単一ホストの前提で、再起動 = 前のインスタンスは停止済み、とみなす(案。SD v0.8 4.3、PD の未決 #14 の MVP での扱い)。

### 5.7 所有権の喪失(案。CA-P-7)

ハートビートの失敗、ロック文書の消失、`lock_not_owned`(7.8)、リース切れのいずれかで、所有権を失ったと分かったときの扱い。

- ジョブ実行は、以降 Indexer に書き込み(last-seen、バッチ登録、ソース削除)を要請しない。各リクエストの前に、所有を保っているかを確認する(ハートビートの状態を見る)。
- すでに送ったリクエストは取り消せない(Indexer は文書ごとに所有を確認するので、書き込みは拒否される。api 3.2)。
- `crawl` ジョブは `failed`(`lock_lost`)にする。終了通知 `outcome=failed` は、`enumeration_completed` の初回の送信を始める前に限り、可能なら送る(終了通知は所有確認の対象外。届かなくてよい。4.8)。送信を始めた後(ポーリング中など)は送らない。`enumeration_completed` は新たに送らない。
- **ロックの解放の基準**(保守側。案。CA-P-8): 所有権の喪失を記録しているときは、ロック文書が自分の `owner`・`job_id` のままでも削除しない(起動時の回復 5.8 か、管理者のロック解放 5.4 に委ねる)。解放(5.5)は、所有権の喪失を記録しておらず、かつロック文書が自分のものであるときだけ行う。ハートビートの停止の待ちが上限(11章)を超えたときは、所有権の喪失として扱い、ロック文書は削除せずに終了処理を続ける。
- `source_delete` ジョブは、後続の削除を止めて `failed` にする(確定。CA-K-11 の要件(2))。再実行で復旧する(8章)。

### 5.8 Crawler 起動時の回復(案。CA-P-9)

Crawler は、crawler-api の受付と Job Runner・Scheduler を始める前に、次を行う。対象は `owner` が自分のロックと、そのジョブだけ。

1. `running` のジョブ(`crawl`・`source_delete`)を `failed`(`crawler_restart`)にする。登録結果は最後に記録した値のままにする(集計の確定前なら `partial=true`、確定後なら `partial=false`。終了通知の送信の有無を問わない。7.7)。ポーリング中だったジョブには、確認結果の区分を書かない(案。回復時に書くかは CA-U-13)。終了通知は送らない。
2. 終端状態のジョブのロック、ジョブ記録のないロック(孤児ロック)、手順 1 で `failed` にしたジョブのロックを、読んだ版を条件に削除する。
3. `queued` のジョブは、そのまま残して `queued_at` の順に実行する(ロックは保持したまま。`lease_expires_at` は null)。
4. `owner` が自分以外のロックは触らず、警告をログに出す(単一 Crawler の前提では起きない)。

`source_delete` ジョブが中断した場合、`loreley-sources` の `status=deleting` は残る(8章)。新しいクロールは起動できず、ソース削除の再実行で復旧する。

---

## 6. 取得とリトライ・スキップ

### 6.1 リトライ設定(案。CA-P-18)

| 設定 | 仮値 | 内容 |
| --- | --- | --- |
| 最大試行回数 | 3 回(最初の 1 回 + リトライ 2 回) | リクエスト単位(Indexer API の呼び出し)と、文書ごと・処理段階(取得、登録)ごとに数える |
| バックオフ | 初回 1 秒、2 倍、上限 30 秒、ジッタあり | 指数バックオフ |

- 値は arch 4.4(案)と SD v0.8 3.1(案)の既定値に合わせる。設定可能で、未決(CA-U-1)。無制限のリトライにならないよう、必ず上限を置く。
- Connector は内部でリトライしない(interface CI-P-5)。リトライの回数の規則は、ここに一本化する。
- リトライの待ちの間もハートビートは続く(5.3)。

### 6.2 失敗の種別と Crawler の扱い(案。CA-P-19)

interface 6章の属性(`scope`・`retry`)に合わせる。`retry` が `transient` または `unknown` ならリトライし、`permanent` ならリトライしない(SD v0.8 3.1 の案は、`permanent` も同じ回数を試すとしていたが、interface が属性を用意したため、属性に従う)。**PD v0.19 との差**(I-8): PD(4.2 など)は、取得できない文書(権限エラーなど)も数回リトライしてからスキップすると読めるが、本書は `retry=permanent` の属性に従い、権限エラー(`fetch_permission_denied`)をリトライせず、即時にその文書だけをスキップする(再試行で直らないため。PD の趣旨である「その文書だけスキップ」は満たす)。例外が 2 つある。列挙の `Failed` は、ストリーミング列挙を途中から再開できないため、`retry` に関わらずリトライしない。`create` の失敗は列挙の前なので、`retry` が `transient`(例: `source_unreachable`)ならリトライする(開始通知の前。4.5 の手順 8)。リトライを尽くしてもだめなときの扱いは次の表。

| 失敗 | 出所 | リトライ | 尽きたら、または即時 | 連続スキップの計数 |
| --- | --- | --- | --- | --- |
| `fetch_transient`(document・transient) | 取得 | する | その文書をスキップ(`stage=fetch`) | 数える(取得段階) |
| `fetch_permission_denied`(document・permanent。I-8) | 取得 | しない | その文書をスキップ | 数える(取得段階) |
| `fetch_not_found`(document・permanent) | 取得 | しない | その文書をスキップ(下記) | 数える(取得段階) |
| `connector_internal_error`(取得時。document・unknown) | 取得 | する | その文書をスキップ。連続して規定の件数に達したらジョブ `failed`(6.3。interface 6.2 の申し送りへの対応) | 数える(取得段階) |
| `oversize`(document・permanent。取得時) | 取得 | しない | スキップではなく、原本サイズ超過として記録(6.5) | 数えない |
| `invalid_external_id`(document・permanent) | 共通処理 | しない | 登録せず、識別子エラーとして記録(CA-P-25)。スキップではない | 数えない |
| `external_id_collision`(document・permanent) | 共通処理 | しない | ジョブ `failed`(CA-P-24) | |
| 列挙の `Failed`(source) | 列挙 | しない(列挙のやり直しはしない) | ジョブ `failed`(4.8) | |
| Indexer の文書単位 `document_rejected` | 登録 | する(その文書だけを再送) | その文書をスキップ(`stage=index`) | 数える(登録段階) |
| Indexer の文書単位 `oversize` | 登録 | しない | スキップではなく、原本サイズ超過として記録(6.5) | 数えない |
| Indexer の文書単位 `lock_not_owned` | 登録・last-seen | しない | スキップもしない。ジョブ `failed`(`lock_lost`。5.7) | |
| Indexer の文書単位 `write_conflict`・`update_conflict` | 登録・last-seen | する(上限付き) | 解消しなければジョブ `failed`(`conflict_unresolved`)。期限削除は行われない。スキップの対象にしない(確定。CA-K-10) | 数えない(K51 からの導出。arch 3.5 の案) |
| リクエスト全体の 500・503・接続エラー・タイムアウト | 全 API(Status API を除く。7.6) | する | ジョブ `failed`(スキップにしない。7.8) | |
| リクエスト全体の 400・409 | 全 API | しない | ジョブ `failed`(7.8) | |

- `fetch_not_found` をスキップにするのは、件数照合を保つためである(導出)。その文書が列挙の対象だったのに登録されなかったとき、スキップ一覧に載せないと `enumerated_count` と `N_seen + E_missing` が合わなくなる(7.5)。実際にファイルが消えていた場合は、次のクロールで列挙されず、記録も消える(6.4)。
- 抽出の失敗(`extract_failed`)は、Indexer が `status: ok` で返すため、リトライもスキップもしない(arch 4.3)。
- OpenSearch 全体の異常は、Indexer がリクエスト全体の 503 で返す(`store_error` という失敗種別はない。api 4.3)ので、文書単位のスキップにならない。

### 6.3 連続スキップの打ち切り(案。CA-P-20)

- スキップの連続を、**取得段階と登録段階で別々に**数える。
  - 取得段階: 取得でのスキップ(`fetch_*`、取得時の `connector_internal_error`)。**取得に成功した**(`fetch` が原本を返した)文書が入るとリセットする。
  - 登録段階: Indexer の `document_rejected` によるスキップ。Indexer が **`status: ok` を返した**文書が入るとリセットする。
- どちらかが規定の件数(仮値 20 件。設定可能。CA-U-1)に達したら、ジョブを `failed`(`skip_limit_exceeded`。`failure_detail` に段階と直近の失敗の分類名)にする。`oversize` と識別子エラーは、計数を増やさず、リセットもしない。
- 例: 500 件の列挙のうち、読めないファイルが散在して 20 件ある。間に取得に成功する文書が入るので、取得段階の連続は 20 件に達しない。20 件はスキップされ、ジョブは `partially_succeeded` になる。一方、マウント切れなどで取得が連続して 20 件失敗すれば、`failed` になる。
- この打ち切りの主体は Crawler で、Indexer は `document_rejected` の連続を数えない(確定。CA-K-10。api 3.5)。件数の 20 は案(設定可能)。
- **登録段階の連続 20 件は api 3.5・SD v0.8 3.1 の案どおり。取得段階への拡張は、それらにない本書の独自の拡張**(案。取得の失敗が連続するのは、マウント切れなどの全体の異常の疑いがあるため。拡張自体の是非は CA-U-16)。
- `connector_internal_error`(取得時)の連続は、取得段階の計数に含める。専用の閾値は置かない(MVP。interface 6.2 が委ねた「連続発生時の打ち切り」の本書での答え)。

### 6.4 スキップ記録(案。CA-P-22)

- 文書をスキップするとき、その文書の `skip` 記録を書く(なければ作り、あれば `attempts`・`last_skipped_at`・`last_job_id` を更新し、`consecutive_skips` を 1 増やす)。書く内容は 3.3.3。本文・秘密情報は書かない。
- スキップ記録は、クロールの最後(終了通知の前。手順 11)に整理する。そのソースの `skip` と `oversize` の記録を一覧し、次のどちらかに当てはまるものを削除する。
  - (a) 今回のクロールで列挙され、スキップにも原本サイズ超過にもならなかった文書(登録に成功した)。
  - (b) 今回のクロールで列挙されなかった文書(元ファイルが消えた)。
- 整理は、列挙が `Completed` で、すべての応答を確認し終えた後にだけ行う(失敗したクロールで消すと、残すべき記録を失うため)。1 件ずつ登録のたびに削除するのではなく、一覧して 1 回で行う(導出。件数が多いときの呼び出しを減らす)。
- ソース削除では、そのソースの記録をすべて削除する(8章)。
- Indexer はスキップ記録を読まない(arch 2.3)。スキップした文書の ID は、終了通知で Indexer に渡す(7.5)。

### 6.5 原本サイズ超過(案。CA-P-23。interface CI-U-3 への対応)

Crawler 側でも上限を超えた原本を拒否する(確定。CA-K-14。Indexer との二重防御)。拒否の方式・記録・影響は次のとおり(案。最終決定は CA-U-4)。

- **方式**: 上限は Crawler の設定 `max_raw_bytes`(仮値。Indexer の `MAX_RAW_BYTES` 以下にする。CA-U-14)。共通処理が `fetch` の `max_bytes` として渡し、Connector が読み取り中の超過で `oversize` を送出する(interface 7章)。`DocumentRef` に `size_hint` があり、それが上限を超えるときは、読まずに `oversize` にする(案)。
- **Indexer 側の拒否**: Crawler の上限が Indexer の上限以下なら、通常は Indexer の拒否は起きない。起きた場合(Crawler の設定の不整合や、申告 `size` の食い違い)は、バッチ応答の `oversize` として同じ扱いにする。
- **記録**: `oversize` 記録(3.3.4)を書く。スキップ記録とは別にする(PD 4.2「スキップではなく」)。整理は 6.4。
- **ジョブの status への影響**: なし(案)。原本サイズ超過だけで `partially_succeeded` にはしない。登録結果の `oversize_count` で数える(7.7)。
- **終了通知**: Crawler 側の拒否と Indexer 側の `oversize` の結果から `document_id` を集め、重複を除いて `oversize_document_ids` に載せる(7.5)。新規文書は Indexer に送られず索引にないので、載せないと件数照合が合わなくなる(interface 7章)。
- すでに索引にある同じ文書は、Indexer に送らないので書き換わらない(確定。CA-K-14)。`last_seen_at` は列挙時に更新済みで、削除対象にならない。

---

## 7. Indexer との連携

契約(エンドポイント、項目、エラー)は api が正本で、本書は再掲しない。エンドポイントの形・キー名・失敗種別名は api では案(Indexer 実装で採用中)で、本書はその名前で参照する(I-5)。

### 7.1 呼び出し順(確定。CA-K-3)

| 段階 | 内容 | api | 備考 |
| --- | --- | --- | --- |
| 1 | ロック取得(受付) | | 4.3、5.2 |
| 2 | 実行開始(設定スナップショットの確定)、`validate_config`・`create` | | 4.5。Indexer を呼ばない |
| 3 | 開始通知 | 4.1 | ロック取得後・列挙前 |
| 4 | `last-seen` の要請(チャンクごと) | 4.2 | 取得より前 |
| 5 | バッチ登録(チャンクごと) | 4.3 | 同期。文書単位の結果 |
| 6 | 終了通知 | 4.4 | すべての `last-seen` とバッチ登録の応答を確認した後。202 |
| 7 | 削除結果のポーリング | 4.5 | 終端状態になるまで。ロックは保持 |
| 8 | 記録とロックの解放 | | 5.5 |

段階 2 は Crawler 内部の処理で、Indexer の契約ではない(案。4.5)。ソース削除は別の順序(8章。api 4.6〜4.8)。

### 7.2 各 API の使い方

Crawler が何を送り、応答をどう扱うか。エラー別の扱いは 7.8。

| API | 送る内容(Crawler 側の出どころ) | 応答の扱い |
| --- | --- | --- |
| 開始通知 | `crawl_id`(= `job_id`)、`source_id`、設定スナップショットの 6 項目(`crawl_started_at`、`ttl`、`ratio_threshold`、`min_delete_count`、`force_delete`、`rewrite_mode`。`settings_snapshot` の値) | 200 で次へ。再送は同一値(7.4) |
| `last-seen` | `crawl_id`、`crawl_started_at`(スナップショットと同じ文字列)、`lock`(`owner`・`job_id`)、`document_ids`(Crawler が算出した小文字 64 桁の 16 進) | `updated`・`unchanged`・`not_found` は成功(新規文書の `not_found` は正常)。`update_conflict` は上限付きでリトライ。`lock_not_owned` は `failed`(6.2) |
| バッチ登録 | `crawl_id`、`crawl_started_at`、`lock`、`documents[]`(interface 4章の項目。`external_id` は interface 5.1 の最終形、`raw_content` は標準の base64、`content_hash`・`size` は共通処理の導出値) | 文書単位の結果を集計(7.7)。`status: failed` は 6.2。`status: ok` は成功(`extract_failed: true` も成功) |
| 終了通知 | `source_id`、`outcome`、(`enumeration_completed` のとき)`enumerated_count`・`skipped_document_ids`・`oversize_document_ids`、`finished_at`。固定した内容(7.5) | 202 は冪等に処理されたことだけを示す(7.5) |
| Status API | `crawl_id` | 7.6 |
| ソース削除 1〜3(8.1 の順 1・2・4) | 8章 | 8章 |

### 7.3 バッチ化と `last-seen` の分割(案。CA-P-17)

- `last-seen`: チャンク内の `document_id` を、`document_ids` の件数上限(Indexer の `MAX_LAST_SEEN_IDS`。仮値は README 3章)以下に分割して送る。
- バッチ登録: 次のいずれかに達したらバッチを閉じる(仮値。設定可能。CA-U-1)。
  - 文書数(Indexer の `MAX_BATCH_DOCUMENTS` 以下)
  - 原本のバイト数の合計(Indexer の `MAX_BATCH_BYTES` 以下で、base64 後のリクエストボディが `MAX_REQUEST_BODY_BYTES` 以下になる値)
- Crawler の仮値は、Indexer の設定の上限以下でなければならない(超えるとリクエスト全体が 400 になり、ジョブが `failed` になる)。上限は Indexer の設定で、API からは取得できない(CA-U-14)。
- 失敗した文書だけを再送する(その文書を含む新しいバッチで送る。Indexer は冪等。api 3.5)。バッチ応答の文書の結果が一部だけ得られないとき(リクエスト全体の失敗)は、バッチ全体を同じ内容で再送する。
- 取得した原本は、バッチを登録して応答を集計するまでメモリに持ち、その後に解放する(4.6。interface 7章)。保持する原本はバッチ 1 つ分までで、バッチの合計バイト数(仮値)が Crawler のメモリの上限を決める。チャンクの件数は原本の保持量を決めない(チャンクに残るのは `DocumentRef` と ID だけ)。

### 7.4 設定スナップショットと再送時の同一値(確定。CA-K-5)

- 設定スナップショットは、実行開始の時点で 1 度だけ組み立てて `settings_snapshot` に保存し、開始通知・`last-seen`・バッチ登録の `crawl_started_at` を含め、同じ値(同じ文字列)を使う。
- 型は strict に送る(確定。arch K59): `ttl` と `min_delete_count` は整数、`ratio_threshold` は有限の数値、`force_delete` と `rewrite_mode` は真偽値。`"true"` や `1` などに変換して送らない(7.10)。`rewrite_mode` は省略せず、常に真偽値で送る(省略と `false` は同じ扱いだが、固定のためにそろえる。導出)。
- Indexer は意味上の範囲を検証しない(arch K59)。Crawler も範囲を検証しない(CA-K-16)。
- 開始通知のリトライ(7.8)は、同じスナップショットを送るので、応答が失われても冪等に収束する(api 4.1)。

### 7.5 終了通知

- **内容の組み立て**(`enumeration_completed`。項目名は api 4.4。案で、Indexer 実装で採用中):
  - `enumerated_count`: 列挙した文書の `document_id` の集合の件数(重複を除く)。スキップした文書・抽出失敗の文書・原本サイズ超過の文書を含む。FS の対象外のファイルは列挙しないので含まない(確定。CA-K-7。ユーザー回答 Q2)。識別子エラーの文書は `document_id` を持たないので含まない(CA-P-25)。
  - `skipped_document_ids`: スキップした文書(6.2。`fetch_not_found` を含む)の ID(重複を除く)。`oversize_document_ids` とは別項目(案。arch P32)。
  - `oversize_document_ids`: 原本サイズ超過の文書(Crawler 側・Indexer 側)の ID(重複を除く)。
  - `skipped_count`(任意): `skipped_document_ids` の件数。`finished_at`: 内容を固定する時刻。
- **件数照合を成り立たせる規則**(導出。CA-P-21): Indexer は `enumerated_count == N_seen + E_missing` のときだけ削除を判断する(式は確定。CA-K-7)。`N_seen` は `last_seen_at >= crawl_started_at` の件数(api 4.4)、`E_missing` は `skipped_document_ids` と `oversize_document_ids` の和集合のうち、索引にないものの件数。したがって、列挙した文書は、(a) 索引にあって `last-seen` で更新されたか、(b) `skipped_document_ids` または `oversize_document_ids` に載っているか、のどちらかでなければならない。登録に至らなかった列挙済みの文書(新規で索引にないもの)をどちらにも載せないと、件数が合わず、削除が見送られる(`validation_failed`)。Crawler は索引を読めないので、登録されなかった列挙済みの文書は、すべてどちらかに載せる。`skipped_document_ids` と `oversize_document_ids` は、今回のクロールの `crawl` の実行状態(ジョブ実行が保持するメモリ上の集合)から作る(永続のスキップ記録・原本サイズ超過記録からは作らない)。共通処理が持つのは列挙済みの ID の集合(CA-P-26)だけで、スキップ・サイズ超過の ID の集合は持たない(interface 2章の共通処理の定義)。
- **ID の合算件数の上限**(S-1): `skipped_document_ids` と `oversize_document_ids` の合算件数が Indexer の `SKIP_OVERSIZE_ID_LIMIT`(既定 10,000。13.1)を超えると、Indexer は終了通知を 202 で受理したうえで、削除の判定を `validation_failed`(`id_limit_exceeded`)にする(削除されない。api 4.4)。上限は Indexer の設定で、API から取得できない(CA-U-14)。Crawler は、合算件数が警告閾値(11章の仮値。Indexer の `SKIP_OVERSIZE_ID_LIMIT` に合わせて設定する)を超えそうなとき、ジョブ記録の `warnings` に警告を残す(案。CA-P-41)。
- **固定**(確定。CA-K-6): 初回の送信を始める前に、内容を `finish_notice` に保存する。再送は保存した内容をそのまま送る。`failed`・`cancelled` の通知も同じ(固定の対象)。
- **送信の開始の記録**(`send_started_at`。案。CA-P-42): 初回の送信を始める直前に、`finish_notice` に記録する。取り消しが有効かどうかの境界に使う(4.7)。
- **`failed`・`cancelled` の通知内容の省略**(案。Indexer 実装で採用中。api 4.4、API-U-12): 内容は `outcome`・`source_id`・`finished_at` だけにする。Indexer は省略を受理し、ID 一覧は保存しない。省略が受理されなくなった場合は、api 4.4 の「可能な範囲で送る」に従い、`enumerated_count` と ID 一覧を含めて固定する。
- **固定後・初回送信前の取り消し**(案。CA-P-42): まだ Indexer に届いていないので、取り消しは有効とする。固定済みの `enumeration_completed` は送らず、`outcome=cancelled` の通知を新たに固定して送る。K24・K25 の「再送では同一内容」は、送信を始めた通知に対する規則と解釈する(導出。4.7)。
- **202 は受理の確認ではない**(確定。CA-K-8): 遅れた通知や未知の `crawl_id` にも 202 が返るため。受理の有無は、ポーリング(7.6)の最初の応答で確認する。根拠は、`finish_received_at` があること、または `status=failed` かつ `reason` が `outcome_failed` / `outcome_cancelled` であること(api 4.5)。根拠が得られない終端状態(例: `discarded`)は、警告をジョブ記録に残す(案。CA-P-29)。202 の後の最初の応答が `running` かつ `finish_received_at` なしのときも、警告を残してポーリングを続け、上限時間で `unconfirmed` にする(通常は起きない。Indexer は `finish_received_at` を永続化してから 202 を返す。api 4.4)。
- **リトライ**: 6.1 の設定に従う。500・503・接続エラー・タイムアウトはリトライし、直らなければ `finish_notice_failed` でジョブを `failed` にする(削除が行われないだけで安全。応答だけが失われた場合は、削除が進みうる。CA-K-9)。409(`finish_content_mismatch`・`finish_source_mismatch`)は Crawler の不具合の検出で、リトライしない。
- **取り消し**: 4.7(案。CA-P-42)。初回の送信を始めた後の取り消しは、削除を止められない。送信中(リトライ中)に取り消されたときは、リトライをやめる。Indexer に届いたかどうかは不明のままで、確認結果の区分は書かない(削除が進みうることは CA-K-9 のとおり)。

### 7.6 Status API のポーリングと確認結果の区分

- 終了通知(`enumeration_completed`)の 202 を確認したら、`status` が終端状態(`running` 以外)になるまでポーリングする(確定。CA-K-3)。間隔・上限時間・失敗の連続回数は仮値(CA-U-1)。待機中(`waiting_for` あり)も `running` のままなので、続ける。
- 列挙の失敗・取り消し(終了通知の前)・開始通知の失敗のときは、ポーリングしない(確認に入らない)。
- ポーリングの失敗(リクエストのタイムアウト、接続エラー・5xx、404)は、成功の応答が入るたびに連続の数え直しとする。連続が失敗の連続回数(リトライ設定の回数。6.1)に達したら、またはポーリング全体の上限時間を超えたら、確認を打ち切る。**打ち切った場合は、警告と確認結果の区分をジョブ記録に残すだけで、ジョブの status は変えず、再確認しない**(確定。CA-K-4)。
- **確認結果の区分**(名称と対応は案。CA-P-30):

  | 区分 | 条件 |
  | --- | --- |
  | `confirmed` | 削除結果が終端状態になったことを確認できた |
  | `unconfirmed` | ポーリング全体の上限時間を超えた(待機中のままを含む)。または、連続した失敗に 404 以外(接続エラー・5xx・タイムアウト)が 1 つでも含まれて、連続回数に達した。終了通知後の取り消しで確認を打ち切った |
  | `unknown` | 404 だけが、連続回数に達するまで続いた |
  | (記録しない) | 確認に入っていない・終えられなかったジョブ(列挙の失敗、終了通知前の取り消し、開始通知・終了通知の失敗、ポーリング中の Crawler の停止と回復。回復時に区分を書くかは CA-U-13) |

- 404 は、保持件数を超えて消えた、または `loreley-deletions` を失った場合を意味し、Crawler は区別できない(api 4.5。「結果不明」に統一する)。
- 終端状態を確認したら、削除結果の要約(`status`、`reason`、`forced`、`target_count`、`denominator`、`deleted_count`、`enumerated_count`、`n_seen`、`e_missing`、`finish_received_at`、`deletion_started_at`、`finished_at`)を `deletion_summary` に写す(案。CA-P-32)。打ち切ったときは、最後に読めた応答の項目と読めた日時を写す。
- 削除結果の `failed`・`skipped_by_ratio`・`validation_failed`・`discarded` は、ジョブの status を変えない(確定。CA-K-4)。
- ポーリング中もジョブは `running` で、ハートビートを続ける(5.3)。ロックは、確認を終えるまで保持し、その後に解放する(5.5)。
- Admin View は、確認結果の区分と `loreley-deletions` の現在値を併記して「結果未確認」「結果不明」を表示する(arch 2.2。Admin API の領域)。

### 7.7 登録結果の集計と再送規則(案。CA-P-31)

Crawler が `loreley-jobs` のジョブ記録 `registration` に持つ(確定。CA-K-15)。項目名は案。

| 項目 | 内容 |
| --- | --- |
| `enumerated_count` | 列挙した文書の `document_id` の集合の件数(7.5 と同じ値) |
| `created_count` / `updated_count` / `unchanged_count` | バッチ応答の `change` の `created` / `updated` / `unchanged`(確定。arch K50)。`last_seen_at` の `result: unchanged` とは別(api 4.2) |
| `skipped_count` | スキップした文書の数 |
| `oversize_count` | 原本サイズ超過の文書の数(Crawler 側・Indexer 側の合計。重複を除く) |
| `error_count` | 抽出に失敗した文書(`extract_failed: true`)の数(仮の定義。最終決定は CA-U-4) |
| `invalid_id_count` | 識別子エラーの文書の数(CA-P-25) |
| `partial` | 集計途中の値か |

- **再送時の規則**(案。api の API-U-16): `document_id` ごとに、**最初に受け取れた `status: ok` の結果**を保持し、再送の結果で数え直さない。応答を受け取れずに再送した文書は、再送の結果で数える。このため、`created` が `unchanged` と数えられうる(集計は厳密でない。契約に含めない。api 4.3)。`rewrite_mode=true` のクロールでは、既存の文書も `updated` になる。
- **途中の値**(案。SD v0.8 3.3 を引き継ぐ): バッチの応答を集計するたびにジョブ記録を更新し、`partial=true` にしておく。すべての応答を確認し終えたら、終了通知の前に `partial=false` で確定する。確定前にジョブが `failed`・`cancelled` で終わったときは、集計途中の値を `partial=true` のまま保持する(集計が 1 件もない段階の `failed` は、0 件・`partial=true`。確定。CA-K-15)。集計の確定後(終了通知の内容の固定後・送信の前後を問わない)の取り消しや失敗は、`partial=false` のまま(戻さない)。
- 集計の反映は、バッチの応答ごと(案。頻度は SD v0.8 12.5 の未決)。
- **識別子エラー**(CA-P-25): `invalid_external_id` の文書は、登録も `last-seen` の要請もできず、`enumerated_count` にも終了通知の `skipped_document_ids`・`oversize_document_ids` にも載せない。`invalid_id_count` で数え、ジョブ記録の `warnings` に件数と、上限付き(仮値)の例(分類名と、共通処理が見える規則適用前の `external_id` を切り詰めた表示用の文字列。孤立サロゲートは表示用置換。interface 5.1。保存前に共通処理が文字数の切り詰めと制御文字のエスケープも適用する。CA-P-48)を残す。`locator` は不透明で本体は中身を見ないので使わない(interface 3.2。I-43 は本書で解消。interface 3.2 は変更なし)。秘密情報を含みうる Connector(将来の Web。URL のクエリなど)では、除去・伏字が前提(connector-web の CW-U-17)。ジョブは `partially_succeeded` にする。個別の永続的な記録は持たない(次のクロールで同じ結果になるため。最終決定は CA-U-7)。
- **ID 集合の保持**(案。CA-P-26。interface CI-U-10 への対応): 共通処理は、列挙した文書について `document_id`(32 バイトの値でよい)と、元の `external_id`(規則適用前)の SHA-256(32 バイト)を持つ。同じ `document_id` で元の値の SHA-256 が違えば衝突と判定できる。文字列は持たないので、衝突の検出時に手元にあるのは後に検出された 1 件の `external_id` だけである。`failure_detail` には、その 1 件の切り詰めた `external_id` と共有する `document_id` を載せる(案。CA-P-45)。もう 1 件は、同じ `document_id` になる別表記(NFC/NFD の違い、`\` と `/` の違いなど。interface 5.1、I-10)で、管理者は表示された側を(FS では `exclude_patterns` で)除けば衝突を避けられる。列挙を再実行して 1 件目を回収する案は、失敗経路だけの例外として実装コストが高いので採らない(案)。1 件あたりの大きさは、オブジェクトのオーバーヘッドを含めて 200 バイト前後と見積もる(推測。実測していない)。想定規模(10 万文書。arch 15.1。目標値ではない)で 20 MB 前後。保持する件数に上限 `max_enumerated_documents`(仮値)を置き、超えたらジョブを `failed`(`enumeration_too_large`)にする。保持できない規模の扱い(外部の領域に持つなど)は MVP では扱わない。

### 7.8 エラー別の扱い(案。CA-P-19)

api 3.4 の「Crawler の扱い」は案(ユーザー未確認)で、本書もその案を採る。リトライは 6.1 の設定。

| 応答 | 対象 API | Crawler の扱い |
| --- | --- | --- |
| 400 `invalid_request` | 全 | リトライしない。ジョブ `failed`(`indexer_rejected`)。ID・型・サイズなど Crawler 側の不整合の疑い(7.10) |
| 409 `crawl_already_finished`・`stale_crawl_started_at`・`crawl_start_conflict` | 開始通知 | リトライしない。ジョブ `failed`(`indexer_rejected`)。終了通知は送らない |
| 409 `crawl_not_started`・`crawl_source_mismatch`・`crawl_started_at_mismatch`・`crawl_already_closed`・`crawl_finished` | `last-seen`・バッチ登録 | リトライしない。ジョブ `failed`(`indexer_rejected`)。開始通知を送り直さない(api 4.2) |
| 409 `finish_content_mismatch`・`finish_source_mismatch` | 終了通知 | リトライしない。ジョブ `failed`(`finish_notice_failed`)。受理の有無は Crawler の不具合の検出で、優先度は低い(api 4.4) |
| 409 `lock_not_owned` | ソース削除 2・3(8.1 の順 2・4) | リトライしない。ジョブ `failed`(`lock_lost`)。再実行で復旧する(8章) |
| 文書単位の `lock_not_owned` | `last-seen`・バッチ登録 | リトライもスキップもしない。ジョブ `failed`(`lock_lost`) |
| 404 `crawl_not_found` | Status API | ポーリングの失敗(7.6) |
| 500 `internal_error` | 全 | リトライ。直らなければジョブ `failed`(`indexer_unavailable`)。Status API ではポーリングの失敗 |
| 503 `unavailable`、接続エラー、タイムアウト | 全 | 同上。接続エラーは Indexer の起動前の接続拒否を含む(arch 2.4)。ソース削除 1・2(8.1 の順 1・2)の 503(試行・再実行の上限超過)も同じ扱いで、再実行で続きから完了する(8章) |
| 404 `not_found`・405 `method_not_allowed`・`http_error` | 全 | 契約外の呼び出し(Crawler の不整合)。リトライしない。ジョブ `failed`(`indexer_rejected`) |

- 区分: 呼び出しごとの Status API の失敗の扱い(ジョブの status を変えない)は確定(CA-K-4)。`write_conflict`・`update_conflict` は確定(CA-K-10)。それ以外の最右列は案。
- Indexer が応答を失った(タイムアウトした)後も、処理が続く窓がありうる。Indexer は同じソースの要請を直列に処理し、所有確認を文書ごとに行う(arch 8章)。残る窓は、MVP では既知の制限として許容する。

### 7.9 メンテナンスフラグ(案。CA-P-34。I-5 への対応)

- 形式は Indexer の仮定義を採用する: `loreley-jobs` の ID `maintenance`、項目 `enabled`(真偽値)。文書がない場合は「立っていない」。文書があって `enabled` が真偽値の `false` と明示されているときだけ「立っていない」で、それ以外(真偽値でない値、欠落)は「立っている」とみなす(fail-closed。Indexer の読み取りは確定。CA-K-18。Crawler の読み取りも同じ規則にする。案)。形式の食い違いは、Indexer の削除と要約の書き込みを止め続けるため(arch U-34)、同じ規則で読む。
- Indexer は、登録と `last-seen` ではフラグを確認せず、不正な値は fail-closed で読む(確定。K63)。したがって書き込みを止める役は Crawler に置く(導出。arch 11章は案)。Crawler は、次の時点でフラグを読み、立っていれば書き込みの要請を止める。
  - 起動の受付(4.3)と、実行開始・`create` の前(4.5 の手順 7)。立っていれば拒否または `failed`(`maintenance`)。
  - `source_delete` ジョブ(8章)の、8.1 の順 1・2・4(Indexer API のソース削除 1・2・3)の送信の前(案。CA-U-17)。立っていれば、後続を止めて `failed`(`maintenance`)にする(ロックは終了処理まで保持し、再実行で復旧する。8.3)。Indexer の arch 11章の開始前チェック(対象のソースに `running` のクロールがない、など)に `source_delete` ジョブは含まれていない点は、確認事項(CA-U-17)。
  - チャンク処理の各 `last-seen`・バッチ登録の送信の前(4.6)。立っていれば、以降の要請を止めて `failed`(`maintenance`)にし、終了通知は `outcome=failed` を(4.8 の条件で)可能なら送る(導出。メンテナンスの目的は検索インデックスの書き込みの停止で、`loreley-deletions` に `failed` を記録する終了通知は止める対象に含めないと解釈する)。
- 書き込み手段は未決(arch U-24。CA-U-3)。Indexer の README にはフラグを書く具体的な手順がなく(8章はフラグを確認する挙動だけ)、運用手順は未整備(CA-U-3)。MVP では運用者の手動の書き込みを想定する(案)。crawler-api にフラグの操作は置かない(Q1 の範囲外)。停止中の応答・再開の手順など細部は arch U-12 が未決。

### 7.10 ID 制約の担保と HTTP クライアントの要件

Indexer の検証(arch K59。確定)に対する、Crawler 側の担保。違反は、リクエスト全体の 400 になり、再送しても直らない。規則は api 3.3 が正本で、数値(256 バイト、4096 バイトなど)は検証の規則としての仮値であり、Indexer 側の変更に追随する。

| 対象 | 担保 |
| --- | --- |
| `source_id` | 登録時に検証する(空でない、制御文字なし、UTF-8 で 256 バイト以内。3.2)。URL のパスに使われるので、送るときはパーセントエンコードする(導出。文字種の制限は CA-U-15。案は crawler-api の CAPI-P-15) |
| `crawl_id`(= `job_id`)、`lock.owner`、`lock.job_id` | Crawler が生成・設定する値で、256 バイト以内・制御文字なしにする(CA-P-1、CA-P-3) |
| `external_id` | 共通処理が interface 5.1 の規則で処理・検証し、孤立サロゲートを事前に置き換える(CI-K-4)。4096 バイト以内、NUL なし |
| `title`・`path`・`url`・`mime_type` | 孤立サロゲートの表示用置換(interface 4章)。置換しないと文書が `document_rejected` になり、スキップになる |
| `content_hash` | 小文字 64 桁の 16 進(共通処理が算出。interface 5.4) |
| `document_ids`・ID 一覧 | 小文字 64 桁の 16 進(interface 5.2) |
| 型 | strict(7.4)。日時はタイムゾーン付き |
| `raw_content` | 標準の base64(パディングあり・改行なし) |

HTTP クライアントの要件(案。CA-P-39):

- `DELETE` に JSON ボディ(`{"lock": {"owner": "...", "job_id": "..."}}`)を載せられること(確定。CA-K-12。ソース削除 2・3 は `lock` が必須で、ボディなしは 400)。クライアントによっては `DELETE` のボディを落とすので、契約テストで確認する(12章)。
- JSON の数値・真偽値を文字列に変換しないこと。base64 は改行を入れない形式を使うこと。
- タイムアウトは API ごとに設ける(11章。仮値)。ソース削除 1(`deletions:discard`)は、実行中の削除バッチの完了を待つ(api 4.6)ので長く、ソース削除 2(`DELETE .../documents`)は `delete_by_query` を含み、さらに長い。待ちの間もハートビートは続く(5.3)。
- 呼び出しは同期。接続エラー・タイムアウトは 6.1 のリトライの対象。

### 7.11 `document_id` の二重実装対策(interface CI-U-1 への対応)

- Crawler がバッチ応答の `results[].document_id`(Indexer が算出)を、自分の算出値と**実行時に照合する**(案。CA-P-27。interface CI-P-4 の 2 案目)。不一致は、`last-seen` と終了通知の ID が Indexer の ID とずれることを意味する(削除が止まる、または意図しない対象を指す)ので、ジョブを `failed`(`document_id_mismatch`)にする。
- 共有テストベクタ・共有ライブラリの採否と、Indexer 側のテストにベクタを置くかは未決(CA-U-9)。

---

## 8. ソース削除ジョブ

データソースを削除するジョブ(`source_delete`)。Indexer の手順は api 4.6〜4.8、arch 9.14。ここでは Crawler 側の手順と扱いを定める。

### 8.1 手順

ロックを最後まで保持し、ロック文書の削除は最後に行う(確定。CA-K-11。arch K29)。手順の順序と、スキップ記録の削除を Crawler が行うことは arch 9.14 に従う(案。実行は Crawler のジョブ)。表の「順」は本書の手順の番号で、Indexer API の「ソース削除 1〜3」(api 4.6〜4.8)は順 1・2・4 に当たる。

| 順 | 内容 | 主体 | 失敗時 |
| --- | --- | --- | --- |
| 0 | 受付: `crawl` と同じ手順(4.3。ただし `status=deleting` のソースも受け付ける。8.3)でロック文書を `create` し、ジョブ(`source_delete`)を `queued` にする。Job Runner が実行を始めるとき、`running` にし、`loreley-sources` を `status=deleting` に更新する | Crawler | ロックが取れなければ拒否 |
| 1 | ソース削除 1: `POST .../deletions:discard`。そのソースの終端でない削除結果を `discarded` にする。`lock` は添えるが所有は確認されない | Indexer | 503 はリトライ。尽きたらジョブ `failed` |
| 2 | ソース削除 2: `DELETE .../documents`。`lock` を JSON ボディで添える。そのソースの文書をすべて削除する | Indexer | 409 `lock_not_owned` はジョブ `failed`(`lock_lost`)。503 はリトライし、尽きたらジョブ `failed`(再実行で続きから消せる) |
| 3 | そのソースの `skip` 記録と `oversize` 記録を削除する | Crawler | リトライし、尽きたらジョブ `failed`(`store_unavailable`。4.8) |
| 4 | ソース削除 3: `DELETE .../deletion-records`。`lock` を JSON ボディで添える | Indexer | 順 2 と同じ |
| 5 | `loreley-sources` のデータソース設定を削除する | Crawler | リトライし、尽きたらジョブ `failed`(`store_unavailable`。4.8) |
| 6 | ジョブの最終状態(`succeeded`)を記録し、最後にロック文書を削除する(5.5) | Crawler | |

- 「削除中」の状態(CA-P-35): `loreley-sources` の `status=deleting`(順 0 の実行開始で設定し、順 5 の設定削除でレコードごと消える)。ジョブが失敗してロックを失っても、`deleting` が残るので、新しいクロールは起動されない(確定の要件。CA-K-11 の要件(4))。置き場所の最終決定は CA-U-2(arch U-4。他の候補は、ロック文書とジョブの状態)。
- **メンテナンスフラグ**(案。CA-U-17): 順 1・2・4(Indexer API のソース削除 1・2・3)の送信の前に、フラグを確認する。立っていれば、後続を止めて `failed`(`maintenance`)にする。ロックは終了処理まで保持し、再実行で復旧する(8.3)。7.9。
- 設定の削除(順 5)は、文書・スキップ記録・削除の記録の削除が終わってから行う(途中で止まった場合に再実行できるように。arch 9.14)。

### 8.2 ハートビートと所有権(確定。CA-K-11)

- 順 0 から 6 まで、ハートビートを続ける(要件(1))。順 1 の応答待ち(実行中のバッチを待つ。ハングした場合は待ち続ける。arch 9.13(10))の間も、独立したハートビートでリースは切れない。discard の応答待ち中のリース切れの扱い(api の API-U-14 の未決)は、この設計では独立したハートビートで解消する(案)。
- 所有権を失った(ハートビートの失敗、`lock_not_owned`、リース切れ)ときは、後続の削除操作を止めて `failed`(`lock_lost`)にする(要件(2)。5.7)。
- 順 2・4 は、リースが切れていれば Indexer が 409 `lock_not_owned` で拒否し、何も書かない。

### 8.3 再実行と復旧

- 途中で止まったジョブ(`failed`)は、再度 `source_delete` を起動して復旧する(要件(3))。`status=deleting` のソースに対して、`source_delete` の受付を許す(案)。順 1・2・4 は冪等で(api 4.6〜4.8)、何度でも再実行できる。順 3・5 も、すでに削除済みなら成功として扱う(導出)。
- 順 5 の後(設定がない)に止まった場合は、ロック文書だけが残る。起動時の回復(5.8)か、管理者のロック解放で消す。そのソースの再実行は要らない(導出)。
- ソース削除中のソースに、新しいクロールを起動しない(確定。CA-K-11 の要件(4))。受付(4.3 の手順 1・4)と Scheduler がそれぞれ確認する。

---

## 9. 障害と再起動

| 状況 | 扱い |
| --- | --- |
| Indexer のダウン・遅延(接続不可、タイムアウト、5xx) | リトライし、直らなければジョブ `failed`(スキップにしない)。終了通知は届かなくてよい(削除されない)(7.8。arch 12章) |
| Indexer の再起動(Crawler のポーリング中) | Indexer が待機中・判定中・実行中の削除結果を `failed`(`indexer_restart`)にする。Indexer の再起動からの復帰がポーリングの打ち切り(連続失敗の回数・上限時間)より早ければ、ポーリングは終端状態を読んで区分は `confirmed`、遅ければ `unconfirmed`(接続エラーが続くため)。ジョブの status は変えない(CA-K-4)。Indexer の起動には時間がかかる(README 2章の HEALTHCHECK の `--start-period` は 120 秒)ので、ポーリングの仮値(連続失敗の回数・間隔)は CA-U-1 で再検討する |
| Crawler の OpenSearch(Store 層)に書き込めない・読めない | ジョブ記録・ロックの書き込みはリトライし、尽きたら `failed`(`store_unavailable`。4.8。CA-P-50)にする。ハートビートが継続できずリースが切れたら、所有権の喪失(5.7)としてジョブを止める。Store 層に書けないため、`failed` の記録も残らないことがある(復旧後の起動時の回復で `failed` にする。5.8) |
| Crawler の停止・再起動 | リース切れで `failed` と表示され、再起動時の回復(5.8)で `failed` にする。終了通知を送った後の停止では、Indexer は受理済みで削除が続きうる(区分は残らない) |
| 終了通知の応答の喪失 | 同じ内容で再送する(7.5)。受理済みなら 202(冪等)。受理後に応答だけが失われ、再送もすべて失敗したときは、ジョブは `failed` でも削除が進みうる(CA-K-9) |
| ポーリングの失敗・上限時間の超過 | 警告と区分だけを残し、ジョブの status は変えない(7.6) |
| Admin API から Crawler に届かない | 起動・操作はできないが、ジョブ状態と削除結果の表示は、読み取りで続けられる(推測。arch 12章) |
| データソースのマウント切れ(FS) | 列挙の失敗として `failed`(interface 6章)。取得段階では取得の失敗が連続し、連続スキップの打ち切り(6.3)にかかりうる。判定は FS 文書(connector-file-system 3.3) |
| メンテナンスフラグが立っている | 起動を受け付けず、実行中は要請を止めて `failed`(7.9) |
| 定期起動を逃した | 取り返さない(4.3) |
| 想定外の例外(Crawler) | ジョブ `failed`(`internal_error`)にする。終了通知は、`enumeration_completed` の初回の送信を始める前に限り、可能なら `failed` で送る(4.8) |

---

## 10. コンテナ・マウント(最小限)

- `crawler` は独立したコンテナで、バックエンドは Python。検索対象ディレクトリの読み取り専用(`:ro`)マウントは `crawler` だけに付ける(arch 2.4 の案)。マウントの具体は FS 文書。
- 設定は環境変数で与える(案): OpenSearch の接続先(Store 層)、Indexer の URL、`loreley-jobs` の索引名(Indexer の `JOBS_INDEX_NAME`、既定 `loreley-jobs` と一致させる必要がある。CA-U-14)、`owner` に使う安定した Crawler の ID(CA-P-3)、11章の仮値。秘密情報は Store 層に保存しない(PD 4.8)。
- 起動順(案。CA-P-40): OpenSearch への接続 -> 起動時の回復(5.8) -> Job Runner・Scheduler・ハートビートの起動 -> crawler-api の受付開始。Indexer の起動は待たない(接続エラーはリトライの対象。arch 2.4)。
- 現在のリポジトリの compose(`deploy/compose/`)は OpenSearch と Indexer だけを定義している(13.1)。`crawler` の追加は実装時に行う。
- ポートは内部ネットワークだけで、ホストに公開しない。認証はない(MVP)。

---

## 11. 非機能・仮値

すべて「仮値・設定可能・未決」(CA-U-1)。Indexer の値(README 3章)との関係を右の列に示す。Crawler の値が Indexer の上限を超えると、リクエスト全体が 400 になる(CA-U-14)。

| 項目 | 仮値 | Indexer の値との関係 |
| --- | --- | --- |
| リース時間 | 300 秒 | |
| ハートビート間隔 | 100 秒(リース時間の 1/3) | |
| 最大試行回数 | 3 回 | arch 4.4 の案と同じ |
| バックオフ | 初回 1 秒、2 倍、上限 30 秒、ジッタあり | 同上 |
| 連続スキップの打ち切り | 20 件 | api 3.5 の案と同じ |
| チャンクの件数(`last-seen`・取得の単位) | 500 件 | `MAX_LAST_SEEN_IDS` 以下 |
| バッチの文書数 | 20 件 | `MAX_BATCH_DOCUMENTS` 以下 |
| バッチの原本の合計 | 32 MiB | `MAX_BATCH_BYTES` 以下(base64 後が `MAX_REQUEST_BODY_BYTES` 以下) |
| 原本 1 件の上限 `max_raw_bytes` | 20 MiB | `MAX_RAW_BYTES` 以下 |
| 列挙した文書数の上限 `max_enumerated_documents` | 500,000 件 | 想定規模は 1 万〜10 万文書(arch 15.1。目標値ではない)。Indexer の `MAX_DELETION_TARGETS` とは別 |
| HTTP のタイムアウト: 開始通知・終了通知・Status API | 30 秒 | |
| HTTP のタイムアウト: `last-seen` | 60 秒 | |
| HTTP のタイムアウト: バッチ登録 | 300 秒 | 抽出に時間がかかる文書がある(README 9章) |
| HTTP のタイムアウト: ソース削除 1(discard) | 600 秒 | 実行中の削除バッチの完了を待つ |
| HTTP のタイムアウト: ソース削除 2(文書の全削除) | 4,200 秒 | Indexer の設定に依存する。最悪の所要時間は `OS_DELETE_BY_QUERY_TIMEOUT_SECONDS` ×(1 + `DELETE_BY_QUERY_MAX_RERUNS`)で、既定では 600 × 6 = 3,600 秒(README 3章)。これに余裕を持たせた値。再実行回数を上げたら合わせて延ばす |
| HTTP のタイムアウト: ソース削除 3 | 60 秒 | |
| Status API のポーリング間隔 | 5 秒 | |
| ポーリング全体の上限時間 | 30 分 | PD 9.2 #11 が未決 |
| ポーリングの失敗の連続回数 | 3 回(リトライ設定と同じ) | |
| `warnings` の件数、識別子エラーの例の件数の上限 | 20 件 | |
| `failure_detail` 全体の長さの上限 | 512 文字 | 切り詰めた `external_id`・相対パスの表示は 1 件 200 文字まで(`warnings` の例も同じ)。切り詰め・制御文字のエスケープ・孤立サロゲートの置換は共通処理が適用する(CA-P-48) |
| 受付の途中のロックとみなす `acquired_at` の長さ | 60 秒 | 受付は Store 層の読み書きを数回行う。crawler-api は長さを未決としている(CAPI-U-7、CAPI-U-10) |
| Scheduler の判定周期 | (空欄。仮値・未決) | module-structure の CM-U-6 と合わせて決める(同 2.2 に数値の案はない) |
| Job Runner の走査間隔(起床通知の取りこぼし対策) | (空欄。仮値・未決) | 同上 |
| ハートビート更新の失敗時の再試行間隔(5.3) | (空欄。仮値・未決) | 同上。ハートビート間隔(100 秒)より十分短くする |
| Store 層のクライアントのタイムアウト | (空欄。仮値・未決) | 仮値・未決。module-structure の CM-U-6 と合わせて決める(同 7.4 に数値の案はない)。ハートビート専用のものは、再試行間隔とリース時間に収まる短さにする |
| ハートビートの停止の待ちの上限 | (空欄。仮値・未決) | 仮値・未決。CM-U-6 と合わせて決める。Store 層のタイムアウト以上にする(module-structure 4.4) |
| 終了通知の ID 一覧(`skipped_document_ids` + `oversize_document_ids`)の警告閾値 | 8,000 件 | Indexer の `SKIP_OVERSIZE_ID_LIMIT`(既定 10,000)以下に合わせる。超えると削除が `validation_failed` になる(CA-U-14) |
| 定期起動の間隔 | データソースごとの設定(`schedule_interval_seconds`) | TTL はクロールの間隔より長くする(SD v0.8 3.4) |

- 想定規模は 1 万〜10 万文書(arch 15.1。目標値ではない)。同期 HTTP のため、Indexer が遅いとクロール全体の所要時間が延びる(arch 15.3)。クロールの所要時間は実装後に実測して決める。
- 定期起動の間隔は、クロールの所要時間より長く設定する(arch 15.3 の緩和策)。

---

## 12. テスト観点

実装時のテストの観点。Indexer との連携は、Indexer の結合テストと同じ構成(OpenSearch と Indexer を compose で起動)でも確認する(推奨。README 10章)。

| # | 観点 | 期待 |
| --- | --- | --- |
| 1 | `document_id` の算出(サンプルベクタ。interface 5.2) | 期待値と一致する。バッチ応答の `document_id` と実行時に照合し、不一致なら `failed`(`document_id_mismatch`) |
| 2 | 呼び出し順 | 開始通知 -> `last-seen`(取得より前)-> バッチ登録 -> 終了通知 -> ポーリング。すべての応答を確認する前に終了通知を送らない |
| 3 | `crawl_id` と設定スナップショット | `crawl_id` が `job_id` と同値。開始通知・`last-seen`・バッチ登録の `crawl_started_at` が同じ文字列。開始通知の再送が同一値(応答の喪失を模擬) |
| 4 | 型の strict | `ttl`・`min_delete_count` は整数、`ratio_threshold` は数値、`force_delete`・`rewrite_mode` は真偽値で送られる。`rewrite_mode` を省略しない |
| 5 | 終了通知の固定 | 内容が最初の送信前に保存される。再送が同じ内容(`finished_at` を含む)。再送で 409 にならない |
| 6 | 202 と受理 | 202 を受理の確認として扱わない。`finish_received_at` または `failed` + `outcome_*` で受理を確認する |
| 7 | `enumerated_count` | 重複を除く。スキップ・抽出失敗・原本サイズ超過を含む。FS の対象外ファイルを含まない。識別子エラーの文書を含まない |
| 8 | 件数照合 | 列挙済みで登録されなかった文書(`fetch_not_found` を含む)が `skipped_document_ids` に載る。実 Indexer で `validation_failed` にならない |
| 9 | リトライとスキップ | チャンク内で取得とバッチ登録が交互に進み、保持する原本がバッチ 1 つ分を超えない。取得に失敗した文書はバッチに入らず、登録に失敗した文書だけが再送される(取得失敗と登録失敗が同じチャンクに混在してもよい)。6.2 の表の各行。最大 3 回、バックオフ。`document_rejected` のみ Indexer 由来のスキップ。`oversize` はリトライしない。`write_conflict`・`update_conflict` は上限付きリトライ後 `failed`(スキップしない) |
| 10 | 連続スキップ | 取得段階と登録段階で別々に数える。取得段階は取得の成功、登録段階は `status: ok` でリセットされ、どちらかが連続 20 件に達したら `failed`(`skip_limit_exceeded`)。500 件中 20 件の読めないファイルが散在するだけでは打ち切られない。連続 20 件の取得失敗は打ち切られる。登録段階の `document_rejected` が連続 20 件でも打ち切られる。`connector_internal_error`(取得時)の連続は取得段階として打ち切られる。`oversize`・識別子エラーは計数もリセットもしない |
| 11 | エラー別の扱い(7.8) | 400・409 はリトライしない。500・503・接続エラーはリトライし、直らなければ `failed`。ポーリングの失敗はジョブの status を変えない |
| 12 | ポーリングの区分 | 404 のみ -> `unknown`。混在・上限時間 -> `unconfirmed`。成功が入ると連続が数え直される。区分を残した後に再確認しない |
| 13 | ロックとハートビート | `create` の原子性(同時に 2 つの受付で 1 つだけ成功)。同期 HTTP の待ち中・Connector の呼び出し中・ポーリング中もリースが更新される。所有権の喪失でリクエストが止まる。解放の後にハートビートが起きても、ロック文書と状態を変えない |
| 14 | 取り消し | `queued` / 終了通知の前 / 後。終了通知の後は削除が止まらず、ポーリングを打ち切る(`unconfirmed`) |
| 15 | 起動時の回復 | `running` が `failed`(`crawler_restart`)。孤児ロックが消える。`queued` が実行される |
| 16 | ソース削除 | 順 0〜6 の順序。ロックが最後まで残る。所有権を失うと止まる。再実行で完了する。`deleting` のソースにクロールを起動できない |
| 17 | `DELETE` のボディ | ソース削除 2・3(8.1 の順 2・4)が `lock` を JSON ボディで送る(HTTP クライアントがボディを落とさない) |
| 18 | メンテナンスフラグ | 立っていると起動を拒否し、実行中は要請を止める。形式が不正(`enabled` が真偽値でない)なら「立っている」 |
| 19 | ID 制約 | 孤立サロゲートを含むファイル名で、バッチ全体が 400 にならない。`source_id` の違反を登録時に拒否する。256 バイトを超える `job_id` を生成しない |
| 20 | 登録結果の集計 | 再送で数え直さない(最初の `ok` の結果を保持)。`partial` の遷移。`rewrite_mode` で既存の文書が `updated` |
| 21 | 識別子の例外 | `invalid_external_id`(登録されず、`invalid_id_count`、`partially_succeeded`)。`external_id_collision`(ジョブ `failed`) |
| 22 | 原本サイズ超過 | Crawler 側で上限を超える原本を拒否して `oversize_document_ids` に載せる。既存の文書は書き換わらない。ジョブの status が変わらない |
| 23 | 定期起動 | `force_delete`・`rewrite_mode` が常に `false`。ロックがあるときは見送る。停止中の起動を取り返さない |
| 24 | スキップ記録の整理 | 成功した文書・列挙されなかった文書の記録が消え、スキップした文書の記録が残る。失敗したクロールでは整理されない |
| 25 | 取り消しと実行開始の競合 | `queued` の取り消しと Job Runner の実行開始が競合したとき、先に条件付き更新に勝った側が有効。取り消しが負けたら `running` として取り消し要求が伝わる |
| 26 | 取り消し要求の伝達 | `running` への要求が確認点で反映される。ジョブの終端後にフラグが消える。重ねた要求は 1 回と同じ |
| 27 | 再起動と取り消し要求 | 再起動で要求が消え、`running` のジョブは `failed`(`crawler_restart`)になる |
| 28 | ロック解放と Job Runner の競合 | リース切れの `running` をロック解放で `failed`(`lock_released`)にした後、Job Runner の更新が条件で外れ、Job Runner が所有権の喪失として止まる。Job Runner の更新が先なら、解放側が判定し直す |
| 29 | 解放しないロック | `queued` のジョブのロックと、受付途中のロック(ジョブ記録がなく `acquired_at` が直近)を解放しない |
| 30 | `send_started_at` の前後の取り消し | 記録の前は `enumeration_completed` を送らず `outcome=cancelled` を新たに固定して送る。記録の後は削除を止めず、リトライをやめる |
| 31 | 終了通知 `failed` の条件 | 開始通知の後で `send_started_at` の記録前なら、`lock_lost`・`maintenance`・想定外の例外で `failed` を送る。送信開始後(ポーリング中)の `lock_lost`・想定外の例外では `failed` を送らず、元の `failure_reason` が `finish_notice_failed` に上書きされない |
| 32 | ロック解放の基準 | 所有権の喪失を記録しているときは、ロック文書が自分の `owner`・`job_id` のままでも削除しない。ハートビート停止の待ちが上限を超えたら喪失として扱い、ロック文書を削除せずに終了処理を続ける |
| 33 | Store 層の書き込み失敗 | リトライを尽くしたら `failed`(`store_unavailable`)になる。ソース削除の順 3・5 でも同じ |
| 34 | ソース削除中のメンテナンスフラグ | 順 1・2・4 の送信の前にフラグが立っていれば、後続を止めて `failed`(`maintenance`)にし、ロックは終了処理まで保持する(案。CA-U-17) |

---

## 13. 確認状況

### 13.1 確認した事実(2026-11-13)

- **ロック文書**(`apps/indexer/src/loreley_indexer/infrastructure/opensearch/jobs.py`、`common/locks.py`): Indexer は `loreley-jobs` の ID `lock-{source_id}` を ID で取得(GET。リアルタイム)する。項目は `owner`・`job_id`・`lease_expires_at`(すべて文字列)で、1 つでも文字列でなければ、または `lease_expires_at` にタイムゾーンのオフセットがなければ「所有していない」。所有は、要請の `owner`・`job_id` が一致し、現在時刻が `lease_expires_at` より前(厳密に小さい)こと。書き込みの所有確認は文書ごと、ソース削除 2・3(api の 4.7・4.8。本書 8.1 の順 2・4)は実行(再実行を含む)の前ごとに行う(`documents/ownership.py`、`crawl_runs/deletion/source_deletion.py`)。ソース削除 1 が所有を確認しないことは、api 4.6 の記述と、`discard_source_crawls`(`source_deletion.py` L52〜70。ロックの確認を呼ばない)で確認した。
- **メンテナンスフラグ**(同上): ID `maintenance`、項目 `enabled`。文書がなければ「立っていない」、`enabled` が真偽値の `False` のときだけ「立っていない」、それ以外は「立っている」(初回だけ WARNING)。
- **`loreley-jobs` の現行マッピング**(`infra/opensearch/schema/jobs.json`、`deploy/compose/README.md`): `owner`・`job_id` は keyword、`lease_expires_at` は date、`enabled` は boolean の 4 項目だけで `dynamic: false`。「結合テスト用の仮定義で、Crawler の設計確定時に置き換える」と README に書かれている。型に合わない値は書き込みが拒否される。`loreley-sources` の索引は作成物にない(`init-indices.sh` は検索インデックス・`loreley-deletions`・`loreley-jobs` を作る)。
- **Indexer 実装の Store 層**(`infrastructure/opensearch/store.py`): 取得・一覧・無条件の保存・条件付きの置き換え・無条件の削除。`create` と条件付きの削除はない。
- **Indexer の既定の上限(仮値。`apps/indexer/README.md` 3章)**: `MAX_RAW_BYTES` 20 MiB、`MAX_BATCH_DOCUMENTS` 50、`MAX_BATCH_BYTES` 64 MiB、`MAX_REQUEST_BODY_BYTES` 100 MiB、`MAX_LAST_SEEN_IDS` 1,000、`SKIP_OVERSIZE_ID_LIMIT` 10,000、`OS_DELETE_BY_QUERY_TIMEOUT_SECONDS` 600、`DELETE_BY_QUERY_MAX_RERUNS` 5。すべて設定で、設計書の値ではない。
- **`crawl_id` の一意性**(README 9章): 同じ `crawl_id` を別の `source_id` で同時に開始通知すると、結果の作成が競合しうる。`job_id` は全ソースで一意にする。
- **README の記述が古い**: `apps/indexer/README.md` は冒頭で `indexer-api-v0.9.md` などを参照し、6章で「API-U-13 は設計上未決」「api 3.2 は運び方(`DELETE` の `lock`)を決めていない」と書くが、api v0.10 は両方を確定(K66、K60)している(I-7)。
- **compose**(`deploy/compose/compose.yaml`): OpenSearch・`opensearch-init`・Indexer だけを定義している。Indexer は既定のポート 8000。
- `DELETE` の JSON ボディ、`document_id` の算出とサンプルベクタ(interface 5.2 が `API_EXAMPLE_VECTORS` と一致を確認済み)、孤立サロゲートの扱いは、api 3.2・3.3 と interface に従う。

確認していないこと: OpenSearch の実機での `create`・`if_seq_no` の挙動(Indexer の実機確認は README 10章の範囲)、Crawler 側の HTTP クライアントの実装、ロック文書を Crawler が書いた場合の Indexer 実機での読み取り。これらは未決として CA-U-18 に登録した(module-structure の CM-U-1 のスレッド安全性の確認とも関係する)。

### 13.2 確定(CA-K)

確定にしたのは、Indexer 設計書・PD でユーザーが承認済みの事項と、ユーザー回答(Q1〜Q3)の内容だけ。

| ID | 内容 | 出典 |
| --- | --- | --- |
| CA-K-1 | Crawler と Indexer は別コンテナで、メッセージブローカーを介さず HTTP で直接通信する | arch K13、api 3.1 |
| CA-K-2 | 書き込み役: `loreley-jobs` は Crawler のみ、`loreley-deletions` と検索インデックスは Indexer のみ。Admin API は読み取りのみ。例外(メンテナンスフラグの書き込み手段)は確定でなく案(CA-U-3) | arch K2、2.2、2.3 |
| CA-K-3 | 呼び出し順: ロック取得 -> 開始通知(列挙前)-> `last-seen`(取得より前)-> バッチ登録 -> 全応答を確認して終了通知(202)-> Status API のポーリング(終端状態まで) | PD 5.1・5.2、arch K3・K12、api 2 |
| CA-K-4 | ジョブの status と削除結果は切り離す。ポーリングの失敗・上限時間の超過は、警告と確認結果の区分を残すだけで、ジョブの status を変えず、再確認しない。ジョブは削除結果が終端状態になる(または確認を打ち切る)まで完了しない。確認結果の区分は Crawler がジョブ記録に持つ | arch K3、PD 4.7・9.2 #11(ユーザー確定) |
| CA-K-5 | 設定スナップショット(`crawl_started_at`、`ttl`、`ratio_threshold`、`min_delete_count`、`force_delete`、`rewrite_mode`)をジョブごとに保持し、開始通知の再送で同一値を送る。型は strict(`ttl`・`min_delete_count` は整数、`ratio_threshold` は有限の数値、`force_delete`・`rewrite_mode` は真偽値)。範囲は検証されない | arch K24・K33・K37・K59、api 4.1 |
| CA-K-6 | 終了通知の最初の内容を `loreley-jobs` に保存して固定し、再送では同じ内容を送る | arch K25、api 4.4 |
| CA-K-7 | 件数照合の式 `enumerated_count == N_seen + E_missing`。FS の対象外のファイルは列挙も `enumerated_count` への算入もしない。(`enumerated_count` を Crawler が `document_id` で重複を除いて数える定義は api 4.4 の記述で、項目の定義は案。Indexer 実装で採用中) | arch K7(式)、ユーザー回答 Q2(FS)、api 4.4(定義) |
| CA-K-8 | 202 は受理の確認ではない。受理は Status API(`finish_received_at`、または `failed` + `outcome_*`)で確認する | arch K25、api 4.4・4.5 |
| CA-K-9 | 終了通知が Indexer に受理される前にクロールが失敗した場合は削除しない。受理された後は、応答喪失などでジョブが失敗扱いになっても削除処理が続きうる。(終了通知の受理後に Crawler が取り消しても Indexer の削除は止まらないことは Indexer の動作で、arch 9.11・api 4.4 に記載。ジョブ側の扱いは案) | arch K12(前半)、arch 9.11・api 4.4(後半) |
| CA-K-10 | `write_conflict`・`update_conflict` は、上限付きでリトライし、解消しなければジョブ `failed`・期限削除なし。スキップの対象にしない。連続 20 件の打ち切りの主体は Crawler(Indexer は数えない。件数 20 は案) | arch K51、api 3.5(ユーザー承認 2026-11-12) |
| CA-K-11 | ソース削除ジョブは `source_id` 単位のロックを最後まで保持し、ロック文書の削除を最後に行う。(1)リースを更新し続ける、(2)所有権を失ったら後続の削除を止める、(3)再実行で復旧する、(4)削除中のデータソースに新しいクロールを起動しない | arch K29 |
| CA-K-12 | ソース削除 2・3 は `lock`(`owner`・`job_id`)を JSON ボディで運ぶ(`DELETE` を含む)。ソース削除 1 は `lock` を受け取るが所有を確認しない | arch K60、api 3.2 |
| CA-K-13 | ID の検証: `source_id`・`crawl_id`・`lock.*` は空でなく、制御文字を含まず、UTF-8 で 256 バイト以内(256 は Indexer 側では検証規則としての仮値。api 3.3)。`external_id`・`content_hash`・ID 一覧・孤立サロゲートの規則は interface 5章(CI-K-3〜CI-K-5)。違反はリクエスト全体の 400 | arch K59 |
| CA-K-14 | 上限を超えた原本は Crawler(取得)と Indexer(登録)の両方で拒否する(二重防御)。すでに索引にある同じ文書は書き換えない。スキップでもリトライでもなく、`last_seen_at` は更新済みで削除されない | PD 4.2、arch K65 |
| CA-K-15 | 登録結果は Crawler が集計して `loreley-jobs` に持ち、Admin API が読み取りで返す。Status API は削除結果のみ。集計が 1 件もない段階の `failed` は 0 件・`partial=true`。バッチ応答の `change` は `created` / `updated` / `unchanged` で、`unchanged_count` も集計する | PD 9.2 #12(ユーザー確定)、SD v0.8 3.3(ユーザー確定と記載)、arch K50 |
| CA-K-16 | しきい値の範囲(0 以上 1 未満)の検証は Admin API だけ。Crawler と Indexer は検証しない | arch K10 |
| CA-K-17 | 強制削除(`force_delete`)は、手動実行のクロールの起動時にだけ指定できる | arch K5 |
| CA-K-18 | Indexer のメンテナンスフラグの読み取りは fail-closed(文書があり `enabled` が真偽値の `false` と明示されているときだけ「立っていない」)。Indexer は登録と `last-seen` でフラグを確認しない | arch K63 |
| CA-K-19 | crawler-api は Admin API が呼ぶ Crawler の口だけを定義する(起動・取り消し・ロック解放・データソース設定の登録/更新/削除・ソース削除の起動)。Crawler -> Indexer の呼び出し・リトライ・ポーリング・集計は本書に書く。Indexer の契約は参照のみ | ユーザー回答 Q1 |
| CA-K-20 | 各設計書は末尾に自文書分の未決・課題を持つ。既存設計との不整合は `I-n` で区別し、本書に課題の横断一覧(ID・一行要約・参照先のみ)を置く。Indexer 設計書は書き換えない | ユーザー回答 Q3 |

### 13.3 案(CA-P)

| ID | 内容 | 章 |
| --- | --- | --- |
| CA-P-1 | `crawl_id` = `job_id`。形式は `job-{UTC 日時}-{16 進 8 桁の乱数}`、全ソースで一意 | 3.3、7.10 |
| CA-P-2 | ロック文書は Indexer の仮定義(`lock-{source_id}`、`owner`・`job_id`・`lease_expires_at`)をそのまま採用。Crawler が `record_type`・`source_id`・`heartbeat_at`・`acquired_at`(`create` 時に設定。更新しない)を足す。`queued` の間は `lease_expires_at` を null、リースの値はロック文書だけが持つ | 5.1 |
| CA-P-3 | `owner` は設定で与える安定した Crawler の ID(再起動の前後で同じ) | 5.1、10 |
| CA-P-4 | 受付: ソース確認 -> メンテナンス確認 -> ロック `create` -> ソース再確認 -> ジョブ `queued` を保存。ロックの取得は受付の時点 | 4.3、5.2 |
| CA-P-5 | ハートビートはジョブ実行と独立。リースの仮値 5 分、間隔 100 秒。版を条件に更新し、失敗時は短い間隔でやり直す | 5.3 |
| CA-P-6 | リース切れだけでは自動で引き継がない。引き継ぎは再起動時の回復と管理者の解放だけ | 5.4、5.6 |
| CA-P-7 | 所有権の喪失時は Indexer への要請を止め、`failed`(`lock_lost`)にする。終了通知 `failed` は、`enumeration_completed` の初回の送信を始める前に限り、可能なら送る | 5.7 |
| CA-P-8 | ロックの解放は、最終状態の記録の後、ハートビートを止めてから、読んだ版を条件に削除する。所有権の喪失を記録しているときは(ロック文書が自分のままでも)削除しない。ハートビート停止の待ちが上限を超えたら喪失として扱う | 5.5、5.7 |
| CA-P-9 | 起動時の回復: `running` -> `failed`、孤児ロックと終端ジョブのロックの削除、`queued` は実行 | 5.8 |
| CA-P-10 | ジョブ状態名(`queued`、`running`、`succeeded`、`partially_succeeded`、`failed`、`cancelled`)と遷移。`partially_succeeded` はスキップまたは識別子エラーがあるとき。理由コードの一式 | 4.2、4.8 |
| CA-P-11 | 直列実行: Job Runner が `queued` を `queued_at` の順に 1 件ずつ実行 | 4.3 |
| CA-P-12 | 定期起動: 間隔(秒)の形式。起動時刻は直近のクロールジョブの `queued_at` + 間隔。ロックがあるときは見送り、取り返さない | 3.2、4.3 |
| CA-P-13 | `force_delete`・`rewrite_mode` は手動実行のみ、定期起動は常に `false`。受付時にジョブへ記録 | 4.4 |
| CA-P-14 | 設定スナップショットは `queued` -> `running` の遷移時に 1 度だけ確定。`crawl_started_at` はその時刻 | 4.5 |
| CA-P-15 | `create` を開始通知の前に呼び、失敗なら開始通知を送らない。事前確認の専用操作は置かない | 4.5 |
| CA-P-16 | チャンク処理: 列挙を区切り、チャンクごとに `last-seen` -> 取得 -> バッチ登録 | 4.6 |
| CA-P-17 | バッチ化: 文書数・バイト数・`last-seen` の件数の仮値(Indexer の上限以下)。失敗した文書だけを再送 | 7.3 |
| CA-P-18 | リトライ: 最大 3 回、バックオフ 1 秒・2 倍・上限 30 秒・ジッタあり | 6.1 |
| CA-P-19 | 失敗種別ごとの扱い(`retry` 属性に従う)とエラー別の扱いの表 | 6.2、7.8 |
| CA-P-20 | 連続スキップ: 取得段階(取得の成功でリセット)と登録段階(`status: ok` でリセット)を別々に数え、どちらかが 20 件で `failed`。`connector_internal_error`(取得時)は取得段階。取得段階への拡張は本書の独自の拡張(CA-U-16) | 6.3 |
| CA-P-21 | 列挙済みで登録されなかった文書(`fetch_not_found` を含む)は、すべて終了通知の `skipped_document_ids`(または `oversize_document_ids`)に載せる。件数照合を成り立たせる規則。ID の集合は `crawl` の実行状態(ジョブ実行が保持)から作る | 7.5 |
| CA-P-22 | スキップ記録の項目と、クロールの最後に一覧して整理する規則 | 3.3.3、6.4 |
| CA-P-23 | 原本サイズ超過: Crawler の `max_raw_bytes`、`size_hint` の事前判定、別記録(`oversize`)、ジョブの status に影響しない、`oversize_document_ids` へ Crawler 側と Indexer 側の両方を載せる | 3.3.4、6.5 |
| CA-P-24 | `external_id` の衝突はジョブ `failed`(`external_id_collision`) | 4.6、6.2 |
| CA-P-25 | `invalid_external_id` の文書は、登録しない・`enumerated_count` と一覧に載せない・ジョブ記録に件数と例(規則適用前の `external_id` の切り詰め。`locator` は使わない)を残す・`partially_succeeded` | 6.2、7.7 |
| CA-P-26 | 共通処理が列挙済みの `document_id` と元の `external_id` の SHA-256 の集合を保持する(スキップ・サイズ超過の集合は持たない)。件数に上限を置き、超えたら `failed` | 7.7、11 |
| CA-P-27 | バッチ応答の `document_id` を実行時に照合し、不一致なら `failed` | 7.11 |
| CA-P-28 | 終了通知 `failed` / `cancelled` は、開始通知が成功した後で、`enumeration_completed` の初回の送信を始める前に限り、内容を固定して可能なら送る(送信開始後は送らない) | 4.8、7.5 |
| CA-P-29 | 受理の確認はポーリングの最初の応答で行い、根拠のない終端状態は警告を残す | 7.5 |
| CA-P-30 | 確認結果の区分(`confirmed` / `unconfirmed` / `unknown`)の名称と判定。ポーリングの間隔・失敗の連続回数 | 7.6 |
| CA-P-31 | 登録結果の項目名、最初の結果の保持、バッチ応答ごとの反映、`partial` の遷移、`error_count` の暫定定義 | 7.7 |
| CA-P-32 | 削除結果の要約をジョブ記録に写す | 7.6 |
| CA-P-33 | 取り消しは `crawl` ジョブのみ。`queued`・終了通知の前・後で扱いを分ける | 4.7 |
| CA-P-34 | メンテナンスフラグは Indexer の仮定義の形式を採用し、Crawler も fail-closed で読む。受付・実行開始・各リクエストの前に確認する | 7.9 |
| CA-P-35 | 「削除中」は `loreley-sources.status=deleting`。ソース削除の手順 0〜6 と、再実行・設定の削除はソース削除ジョブの中だけ | 8章 |
| CA-P-36 | `loreley-sources` の共通項目、`connector_type` の値(`file_system`・`web`)、`connector_config` は不透明、実行中ジョブに設定変更を反映しない(`connector_config` の確定は手順 8) | 3.2、4.5 |
| CA-P-37 | `loreley-jobs` の記録の種類・ID・項目、Repository の操作(`create`、条件付き置き換え・削除ほか) | 3.1、3.3 |
| CA-P-38 | 時刻は UTC・ISO 8601・ミリ秒精度で書く | 2.5 |
| CA-P-39 | HTTP クライアントの要件(`DELETE` のボディ、strict な型、base64 の形式、タイムアウト) | 7.10 |
| CA-P-40 | コンテナの設定と起動順 | 10 |
| CA-P-41 | 終了通知の ID 一覧の合算件数が警告閾値(仮値)を超えそうなとき、ジョブ記録に警告を残す | 7.5、11 |
| CA-P-42 | 初回の送信の開始の記録(`send_started_at`)、固定後・初回送信前の取り消しの扱い(`outcome=cancelled` を新たに固定)、送信開始後の取り消し | 4.7、7.5 |
| CA-P-43 | ジョブ記録の書き手の分担(受付・`queued` の取り消し・ロック解放は API 側、`running` 以降は Job Runner、回復は起動時)と、すべて読んだ版を条件にした更新で競合を防ぐこと | 5.3 |
| CA-P-44 | 取り消し要求の伝達: `job_id` をキーにしたメモリ上のフラグ。Job Runner が確認点で参照。再起動で消えても `running` は回復で `failed`。リース切れの `running` はロック解放を使う | 4.7 |
| CA-P-45 | `failure_detail` に、列挙失敗・`create` 失敗では Connector の説明文(固定文 + errno 名 + 切り詰めた相対パス)、衝突では後に検出された 1 件の切り詰めた `external_id` と共有する `document_id` を載せてよい(先の 1 件は保持しない)。長さの上限は仮値 | 3.3.1、4.8、7.7 |
| CA-P-46 | Admin API が `loreley-sources` を読み取りのみで直接読む経路(決定は Admin API 設計時) | 2.1〜2.3 |
| CA-P-47 | ロック解放の対象外: `queued` のジョブのロック、受付の途中のロック(ジョブ記録がなく `acquired_at` が直近)。`acquired_at` は `create` 時に設定しハートビートで更新しない | 5.1、5.4 |
| CA-P-48 | `failure_detail` と `warnings` に保存する表示用の文字列に、共通処理が文字数の切り詰め・制御文字のエスケープ・孤立サロゲートの置換を適用する(Connector の担保に加えた二重の防御) | 3.3.1、7.7 |
| CA-P-49 | `loreley-jobs`・`loreley-sources` のマッピングの案(項目・型・使う場面。Indexer が読む 4 項目の型は変えない) | 3.1 |
| CA-P-50 | Store 層への書き込みがリトライを尽くしても失敗したときの理由コード `store_unavailable` を新設する(`internal_error` は流用しない。原因が Store 層であると分けるため) | 4.8、8.1、9 |

### 13.4 未決(CA-U)

| ID | 内容 | 決める場所 |
| --- | --- | --- |
| CA-U-1 | 数値の正式値(リース、ハートビート、バッチ、チャンク、タイムアウト、ポーリング間隔・上限時間、リトライ、連続スキップ件数、列挙の上限)。実測後に決める(arch K39 に準拠)。実測項目に、Indexer README 9章の「20 MiB 級の HTML の抽出に約 40 秒」と、バッチ 20 件 × 40 秒 = 800 秒がバッチ登録のタイムアウトの仮値(300 秒)を超えうる関係を含める | 実装後の実測 |
| CA-U-2 | 「削除中」状態の置き場所の最終決定(案は `loreley-sources.status`。他の候補はロック文書、ジョブの状態。arch U-4、K29 の要件(4)) | ユーザー判断 |
| CA-U-3 | メンテナンスフラグの書き込み手段(運用者の手動手順か、Crawler の固定経路。arch U-24)。案は手動手順 | ユーザー判断(運用) |
| CA-U-4 | 原本サイズ超過の記録先・項目・ジョブの status への影響・利用者への表示(PD 9.2 #8)と、`error_count` の定義。案は 6.5・7.7 | ユーザー判断 |
| CA-U-5 | ジョブ記録・原本サイズ超過記録の保持期間 | ユーザー判断 |
| CA-U-6 | `external_id` の衝突時の扱いの最終決定(案はジョブ `failed`。interface CI-U-2) | ユーザー判断 |
| CA-U-7 | `invalid_external_id` の文書の記録方法とジョブの status への影響の最終決定(interface CI-U-4) | ユーザー判断 |
| CA-U-8 | 定期起動の周期形式(案は間隔(秒)。cron 式にするか) | ユーザー判断 |
| CA-U-9 | `document_id` の二重実装対策のうち、共有テストベクタ・共有ライブラリの採否と、Indexer 側のテストにベクタを置くか(実行時の照合は本書の案。interface CI-U-1 の残り) | module-structure(回答案: CM-P-6・CM-U-3) |
| CA-U-10 | Connector の呼び出し・Indexer の同期呼び出しと、ハートビートの並行モデル(スレッド・非同期など。interface CI-U-9) | module-structure(回答案: CM-P-13・CM-P-14) |
| CA-U-11 | `loreley-jobs`・`loreley-sources` の索引・マッピングの作成担当と詳細(I-6) | ユーザー判断(インフラ) |
| CA-U-12 | Admin API の設計の不在。crawler-api は Admin API の設計より先に契約を定義するため、Admin API の設計時に再確認する(リース切れの `failed` 表示の判定方法、ジョブ・設定の読み取りを含む) | Admin API 設計時 |
| CA-U-13 | ポーリング中の Crawler の停止と回復で `failed` になったジョブに、確認結果の区分を書くか(案は書かない。arch 9.11) | ユーザー判断 |
| CA-U-14 | Crawler の仮値が Indexer の設定上限(バッチ・`last-seen` の件数、サイズ)以下であることを確認する手段(Indexer の上限は設定で、API から取得できない)。案は compose の環境変数で両者をそろえる運用。対象に、終了通知の ID 一覧の合算件数の上限(`SKIP_OVERSIZE_ID_LIMIT`。超えると削除が `validation_failed` になる)と、`loreley-jobs` の索引名(Indexer の `JOBS_INDEX_NAME`、既定 `loreley-jobs` と一致させる)を含める。バッチ登録のタイムアウトと Indexer の抽出時間の関係(CA-U-1)も実測項目 | 運用・インフラ設計 |
| CA-U-15 | `source_id` の文字種の制限(URL のパスに使われる)。案は crawler-api の CAPI-P-15(半角英数字で始まり、半角英数字・`.`・`_`・`-` だけ)。最終決定は CAPI-U-4 | ユーザー判断(crawler-api) |
| CA-U-16 | 連続スキップの打ち切りを取得段階にも広げること(api 3.5・SD v0.8 3.1 にない本書の独自の拡張。案は CA-P-20)の是非 | ユーザー判断 |
| CA-U-17 | ソース削除ジョブの実行中にメンテナンスフラグが立ったときの扱い。案は、8.1 の順 1・2・4(Indexer API のソース削除 1・2・3)の送信の前にフラグを確認し、立っていれば後続を止めて `failed`(`maintenance`)にする(ロックは終了処理まで保持し、再実行で復旧)。あわせて、Indexer arch 11章の開始前チェックの一覧に `source_delete` ジョブが含まれないことを確認事項とする | ユーザー判断(運用) |
| CA-U-18 | OpenSearch の実機での `create`・`if_seq_no` の挙動(ロックの原子性)と、Crawler が書いたロック文書を Indexer が実機で読めることの確認(13.1 の「確認していないこと」。module-structure の CM-U-1 と関係) | 実装時の実機確認 |

### 13.5 既存設計との不整合(I-n)

I-1〜I-6 は Crawler 設計全体の既存設計との不整合で、定義は本節に置く(interface 11.5 は本節を参照する)。I-7・I-8 は本書で見つけた分。I-10・I-11 は interface の項目で、13.8 の横断一覧から参照する。Indexer 設計書(v0.10)は書き換えない。

| ID | 内容 | Crawler 設計での扱い |
| --- | --- | --- |
| I-1 | ソース削除でのロック文書の削除タイミング。SD v0.8 1.2・4.6(案)は、ソース削除ジョブが自分のロックを手順の途中で先に削除するとするが、Indexer の arch K29(確定)と api 4.6〜4.8 は、ロックを最後まで保持して最後に削除するとする | K29 に従う(8章)。SD は廃止予定で修正しない |
| I-2 | 突合ジョブ。SD v0.8 3.6・14.2 は定義するが、PD v0.19 は MVP から削除し(ユーザー確定)、Indexer API にもエンドポイントがない | Crawler 設計に含めない(4.1) |
| I-3 | `loreley-texts` の位置づけ。SD v0.8 1.3・3.2 と `loreley-texts-v0.5` は文書の正とするが、PD v0.19 4.2・4.8 と Indexer の arch K18 は、検索インデックスを唯一の正本とする | Crawler は `loreley-texts` に依存しない(2.3) |
| I-4 | SD v0.8 14.4 のクロール起動の指定に `rewrite_mode` の記載がない。Indexer は開始通知の任意項目として確定している(arch K26・K41) | 本書で起動の指定に追加する(4.4)。crawler-api の起動パラメータにも反映する |
| I-5 | Indexer が設計書の定義なしに仮に置いた事項: ロック文書の形式、メンテナンスフラグの形式、索引名、失敗種別名(`oversize` など)、削除結果の理由コード名(api の API-U-23・API-U-24、arch U-34) | ロック文書・メンテナンスフラグの形式は、Crawler 設計として採用する(5.1、7.9)。食い違いはなく、Indexer の修正課題はない。索引名は仮名のまま。`oversize` は Crawler の分類名にも採用する(interface CI-P-11)。承認までは案 |
| I-6 | `loreley-jobs`・`loreley-sources` の索引・マッピングを作る担当が未定。Indexer は作らない。現行の `jobs.json` は Indexer が読む 4 項目だけの仮定義で、`loreley-sources` の索引は作成物にない(13.1) | 未決(CA-U-11)。Crawler が 3.3 の項目を使うには、マッピングの追加が要る(3.1) |
| I-7 | Indexer の `apps/indexer/README.md` 6章が、設計書 v0.9 を参照したまま、v0.10 で確定した事項を「未決」「決めていない」と書く(API-U-13 の部分結果、`DELETE` の `lock` の運び方。13.1) | Crawler の実装は api v0.10 に従う。README の更新は Indexer 側の課題(本書では書き換えない) |
| I-8 | PD v0.19(4.2、4.1 付近)は、取得できない文書(権限エラーなど)や登録に失敗した文書を「数回リトライし、それでも失敗したらその文書だけスキップ」と書くが、本設計は `fetch_permission_denied`(`retry=permanent`)を、再試行しても直らないためリトライせず即時にスキップとしている | 本設計の案を維持する(6.2。PD の趣旨である「その文書だけスキップ」は満たす)。FS の 6.3・CFS-K-6 は FS 文書で整合させる |

I-9 は使わない(欠番。再利用しない)。

### 13.6 interface からの申し送りへの対応

| interface の項目 | 本書での対応 |
| --- | --- |
| CI-U-1 二重実装対策 | 実行時の照合は案(7.11。CA-P-27)。共有テストベクタ・共有ライブラリは未決(CA-U-9。回答案: module-structure CM-P-6・CM-U-3) |
| CI-U-2 `external_id` の衝突 | 案: ジョブ `failed`(4.6、CA-P-24)。最終決定は CA-U-6 |
| CI-U-3 原本サイズ超過 | 案: 6.5(方式・記録先・影響・ID 一覧への載せ方。CA-P-23)。最終決定は CA-U-4 |
| CI-U-4 `invalid_external_id` の記録 | 案: 7.7(CA-P-25)。最終決定は CA-U-7 |
| CI-U-6 事前確認の要否 | 事前確認の操作は置かない(4.5 の手順 8。CA-P-15) |
| CI-U-9 並行モデル | CA-U-10(module-structure。回答案: CM-P-13・CM-P-14) |
| CI-U-10 ID 集合の保持量 | 案: 7.7(CA-P-26) |
| `connector_internal_error`(取得時)の連続の打ち切り | 6.3(CA-P-20) |
| リトライ・スキップと interface 6章の属性の整合 | 6.2(`retry` の属性に従う。CA-P-19) |

### 13.7 他文書への依頼

初版の依頼のうち、反映・回答済みのものは「反映済み」とする。

- connector-file-system: 反映済み。`create` でルートの存在確認を行う(FS 3.2)、`size_hint` は返さない(FS 5.5)、マウント外れは errno で分類する(FS 3.3、7.2)。FS からの修正要望は、本書の 3.3.1・4.8(`failure_detail`。衝突は後に検出された 1 件と `document_id` を載せる。CA-P-45。FS 8.4・11.6 にも反映済み)、9章(FS 3.3 への参照)、13.8(`CFS-U`、I-30)に反映した。
- crawler-api: 反映済み(crawler-api 5.6 に対応表がある)。受付の拒否条件、`force_delete`・`rewrite_mode` の手動のみ、ロック解放の対象、`source_delete` が `status=deleting` を受け付けること、設定の削除とソース削除ジョブ起動の関係、設定レコードの `status` を登録・更新で変更しないこと。crawler-api から本書への修正要望(5.3 の書き手、4.7 の取り消しの伝達、3.3 の `record_type`、2.2・2.3 の `loreley-sources` の経路、5.1・5.4 の `acquired_at` と `queued` のロック、3.2・4.5 の `connector_config` の確定時点、`source_id` の文字種の案 CAPI-P-15、横断一覧)は、本書に反映した(CA-P-43〜47、CA-U-15、13.8)。
- connector-web: 本書への修正要望(I-43 の `warnings` の表示用の値、横断一覧)は、本書に反映した(7.7、13.8)。I-40(列挙中の一時失敗の扱い。interface の CI-U-11)は、6.2 の列挙のリトライしない方針にも関わる、Web の詳細設計の前の判断事項で、本書は変更していない(13.8 に掲載)。
- crawler-module-structure: 反映済み(module-structure 側。7.6 に回答がある)。ハートビートの並行モデル(CA-U-10)は専用スレッドと専用の Store 層のクライアント(CM-P-13・CM-P-14)、受付処理の共通化(CA-P-43)は `jobs` の受付を `api` と `scheduler` が呼ぶ(CM-P-5)、API と Job Runner が同一プロセスであること(取り消しのフラグ。CA-P-44)は CM-P-15、共通処理・Indexer クライアント・Repository(`create`・条件付き削除)の配置は CM-P-6・CM-P-11・CM-P-10、`document_id` の二重実装対策(CA-U-9)は CM-P-6 と CM-U-3。本書への修正要望(7.5 の ID 集合の保持主体、11章の仮値の行)は反映済み。13.8 に CM-U を追記した。
- interface への修正要望: 反映済み(interface 側で反映を確認済み)。11.5 は本書 13.5 を参照する形に差し替えられている。FS・Web からの要望も、6.1(説明文の緩和。CI-P-17)、9章の結論、3.3 の 2(I-41)、10章 #8(I-42)に反映されている。Web からの I-40 は、interface の新規の未決 CI-U-11 として記録されている(列挙中の一時失敗の扱い。本書 6.2 の方針にも関わる。13.8)。interface 自体は本書では変更していない。

### 13.8 課題の横断一覧

Crawler 設計書全体の課題(未決と既存設計との不整合)を、ID・一行要約・参照先だけで示す(確定。CA-K-20)。本文の再掲はしない。この版は、本書(architecture)、interface、crawler-api(`CAPI-U`)、connector-file-system(`CFS-U`)、connector-web(`CW-U`)、crawler-module-structure(`CM-U`)と、I-1〜I-8、I-10、I-11、I-20、I-30、I-40〜I-44 を載せる(module-structure の I-50・I-51 は欠番で、載せない)。

| ID | 一行要約 | 参照先 |
| --- | --- | --- |
| CA-U-1 | 数値(リース、バッチ、タイムアウト、ポーリングなど)の正式値 | architecture 13.4、11章 |
| CA-U-2 | 「削除中」状態の置き場所の最終決定 | architecture 13.4、8章 |
| CA-U-3 | メンテナンスフラグの書き込み手段 | architecture 13.4、7.9 |
| CA-U-4 | 原本サイズ超過の記録先・影響・表示と `error_count` の定義 | architecture 13.4、6.5、7.7 |
| CA-U-5 | ジョブ記録などの保持期間 | architecture 13.4、3.5 |
| CA-U-6 | `external_id` 衝突時の扱い | architecture 13.4、4.6 |
| CA-U-7 | `invalid_external_id` の記録方法と影響 | architecture 13.4、7.7 |
| CA-U-8 | 定期起動の周期形式 | architecture 13.4、4.3 |
| CA-U-9 | `document_id` の二重実装対策(共有ベクタ・ライブラリ) | architecture 13.4、7.11(回答案: module-structure CM-P-6・CM-U-3) |
| CA-U-10 | ハートビートと Connector・同期呼び出しの並行モデル | architecture 13.4、5.3(回答案: module-structure CM-P-13・CM-P-14) |
| CA-U-11 | `loreley-jobs`・`loreley-sources` の索引・マッピングの作成担当 | architecture 13.4、3.1 |
| CA-U-12 | Admin API 設計の不在(契約の先行定義) | architecture 13.4、5.4 |
| CA-U-13 | ポーリング中の停止の回復時に確認結果の区分を書くか | architecture 13.4、5.8、7.6 |
| CA-U-14 | Crawler の仮値と Indexer の上限設定の整合の確認手段 | architecture 13.4、7.3 |
| CA-U-15 | `source_id` の文字種の制限 | architecture 13.4、7.10、crawler-api 3.2(CAPI-P-15、CAPI-U-4) |
| CA-U-16 | 連続スキップの打ち切りを取得段階にも広げること(独自の拡張)の是非 | architecture 13.4、6.3 |
| CA-U-17 | ソース削除ジョブの実行中にメンテナンスフラグが立ったときの扱い | architecture 13.4、7.9、8章 |
| CA-U-18 | OpenSearch 実機での `create`・`if_seq_no` とロック文書の読み取りの確認 | architecture 13.4、13.1(CM-U-1 と関係) |
| CI-U-1 | `document_id` の二重実装対策の最終採否 | interface 11.4、architecture 13.6(回答案: module-structure CM-P-6・CM-U-3) |
| CI-U-2 | `external_id` 衝突の扱い | interface 11.4、architecture 13.6 |
| CI-U-3 | 原本サイズ超過の方式・記録先・影響 | interface 11.4、architecture 13.6 |
| CI-U-4 | `invalid_external_id` の記録方法 | interface 11.4、architecture 13.6 |
| CI-U-5 | `source_updated_at` が取れないときの値 | interface 11.4(FS・Web 文書で対応) |
| CI-U-6 | 事前確認の要否(本書は置かない案) | interface 11.4、architecture 13.6 |
| CI-U-7 | 認証情報の参照名の解決 | interface 11.4(Web 文書で対応) |
| CI-U-8 | `title`・`path` の欠落・長さ | interface 11.4(各 Connector 文書で対応) |
| CI-U-9 | Connector 呼び出しとリース更新の並行モデル | interface 11.4、architecture CA-U-10(回答案: module-structure CM-P-13・CM-P-14) |
| CI-U-10 | 共通処理の ID 集合の保持量 | interface 11.4、architecture 13.6 |
| CI-U-11 | 列挙中の一時失敗の扱い(I-40 の interface 側。Web の詳細設計の前に判断) | interface 11.4、architecture 6.2、connector-web 4.5 |
| I-1 | ソース削除でのロック文書の削除タイミング(SD と Indexer K29) | architecture 13.5 |
| I-2 | 突合ジョブ(SD にあり、PD で削除) | architecture 13.5 |
| I-3 | `loreley-texts` の位置づけ(SD と PD・Indexer K18) | architecture 13.5 |
| I-4 | 起動の指定に `rewrite_mode` がない(SD 14.4) | architecture 13.5 |
| I-5 | Indexer が仮に置いた形式・名前(ロック文書、フラグ、索引名、失敗種別名) | architecture 13.5 |
| I-6 | `loreley-jobs`・`loreley-sources` の索引・マッピングの作成担当 | architecture 13.5 |
| I-7 | Indexer README 6章の記述が古い(v0.10 で確定した事項を未決と記載) | architecture 13.5 |
| I-8 | PD が権限エラーも数回リトライと読めるのに対し、本設計は `permanent` をリトライしない(本設計の案を維持) | architecture 13.5、6.2 |
| I-10 | `\` の置換と NFC/NFD による `document_id` の衝突 | interface 11.5 |
| I-11 | 原本サイズ超過の Crawler 側の拒否に関する記述の食い違い(PD・K65 と api 4.9) | interface 11.5 |
| CAPI-U-1 | Admin API 設計の不在(契約の先行定義)。メンテナンス中の応答(409 / 503)と、「設定の削除」の解釈の確認を含む | crawler-api 5.4、architecture CA-U-12 |
| CAPI-U-2 | データソース設定の取得・一覧の経路(Admin API の直接読み取りか、Crawler の読み取り API か) | crawler-api 5.4、architecture 2.1(CA-P-46) |
| CAPI-U-3 | 設定項目の必須・既定値・範囲、`ratio_threshold` の入力単位、更新の全置換 | crawler-api 5.4 |
| CAPI-U-4 | `source_id` の文字種の最終決定と、表示名の要否 | crawler-api 5.4、architecture CA-U-15 |
| CAPI-U-5 | 重複起動(`lock_held`)の扱いと、無視された指定・リース切れの警告の通知 | crawler-api 5.4 |
| CAPI-U-6 | 終了通知送信後の取り消しが削除を止めないことの Admin View での示し方 | crawler-api 5.4 |
| CAPI-U-7 | ロック解放の細部(`queued` のロック、受付途中のロックの保護、`owner` が自分以外のロック) | crawler-api 5.4、architecture 5.4(CA-P-47) |
| CAPI-U-8 | `connector_type` を登録後に変更できないことの是非と、`external_id` に影響する設定の変更の扱い | crawler-api 5.4 |
| CAPI-U-9 | Crawler のヘルスチェックの要否 | crawler-api 5.4 |
| CAPI-U-10 | Admin API から Crawler への HTTP タイムアウトなど数値の正式値 | crawler-api 5.4 |
| CFS-U-1 | パターン構文(glob)を確定にするか、`include_patterns` の意味(追加か置き換えか) | connector-file-system 11.4 |
| CFS-U-2 | `follow_symlinks`・`include_hidden` の初期値 | connector-file-system 11.4 |
| CFS-U-3 | `title` を内容から取るか | connector-file-system 11.4 |
| CFS-U-4 | 実機での確認(マウント外れの errno、取得中の変更の検出、エンコーディングの確認方式など) | connector-file-system 11.4 |
| CFS-U-5 | 衝突が 1 組でも残るとソース全体が毎回 `failed` になる影響の緩和 | connector-file-system 11.4、architecture CA-U-6 |
| CFS-U-6 | FS の数値(パターンの上限、読み取りの単位、説明文の長さ)の正式値と実測 | connector-file-system 11.4 |
| CW-U-1 | URL 正規化の規則と `external_id` に含める範囲、URL 長超過の扱い | connector-web 5章 |
| CW-U-2 | 同一内容の複数 URL・リダイレクトと、`external_id` の確定点 | connector-web 5章 |
| CW-U-3 | 探索の範囲(起点、ホスト・パス、絞り込み、深さ、探索順、リンクの種類) | connector-web 5章 |
| CW-U-4 | サイトマップの併用(発見手段か、完全性の根拠か) | connector-web 5章 |
| CW-U-5 | robots.txt の扱い | connector-web 5章 |
| CW-U-6 | 認証(方式、参照名の解決、認証切れの検知) | connector-web 5章 |
| CW-U-7 | レート制限・ペーシング(429・`Retry-After`)と、連続スキップ・バックオフとの関係 | connector-web 5章 |
| CW-U-8 | 列挙中の一時失敗の吸収(I-40 の判断を受けた具体化) | connector-web 5章 |
| CW-U-9 | 判定不能・到達不能の判定表と、遮断・ログイン画面の検知 | connector-web 5章 |
| CW-U-10 | `source_updated_at` が取れないときの値 | connector-web 5章、interface CI-U-5 |
| CW-U-11 | `title`・`path`・`url` の取得元と欠落時の値 | connector-web 5章、interface CI-U-8 |
| CW-U-12 | `mime_type` の決定と文字コード | connector-web 5章 |
| CW-U-13 | 「原本」とするバイト列(展開後・レンダリング)と `size_hint`・`max_bytes` の測定対象 | connector-web 5章 |
| CW-U-14 | 列挙中に得た内容の再利用と、件数に比例する状態の見積もり | connector-web 5章 |
| CW-U-15 | 上限(ページ数・時間)到達時の列挙の終端、クロールトラップ、Indexer・Crawler の件数上限との関係 | connector-web 5章 |
| CW-U-16 | 所要時間と TTL・定期起動の両立、`next()` の長時間ブロック時の取り消し・メンテナンスの反映 | connector-web 5章 |
| CW-U-17 | URL 内の秘密情報・セッション ID の除去・伏字 | connector-web 5章 |
| CW-U-18 | エラー分類の対応の確定(TLS、DNS、リダイレクト異常、robots 拒否など) | connector-web 5章 |
| CW-U-19 | `connector_config` の項目と `validate_config` の範囲、`create` での到達確認 | connector-web 5章 |
| CW-U-20 | 起点 URL・ホスト・スキームを変更したときの文書の同一性 | connector-web 5章 |
| I-20 | SD v0.8 14.2 の中継操作の行に、ソース削除ジョブ起動と設定の登録・更新・削除がない | crawler-api 5.5 |
| I-30 | SD v0.8 3.1 の `os.walk` の `onerror` では一部の列挙エラーを検出できない | connector-file-system 11.5 |
| I-40 | 未決。Web で列挙中の一時失敗 1 件が列挙全体の失敗になる(CI-U-11 と対応。MVP 影響なし) | connector-web 4.5 |
| I-41 | interface に反映済み。「存在し続けた文書は必ず返す」の範囲の補足(低) | connector-web 4.5、interface 3.3 |
| I-42 | interface に反映済み。テスト観点 #8 と Web の保持量の補足(低) | connector-web 4.5、interface 10章 |
| I-43 | 解消済み。`warnings` の表示用の値を規則適用前の `external_id` の切り詰めに変更(interface 3.2 は変更なし) | connector-web 4.5、architecture 7.7 |
| I-44 | 未決。Indexer の文字コード対応が UTF-8・CP932 のみ(Web で顕在化する既存制約) | connector-web 4.5 |
| CM-U-1 | opensearch-py のクライアントを複数スレッドから使えるかの確認(ハートビート専用クライアントの要否の最終決定に関わる) | module-structure 7.4 |
| CM-U-2 | 同期 HTTP クライアントのライブラリの選定(`DELETE` のボディ、API ごとのタイムアウト、スレッド) | module-structure 7.4、architecture 7.10 |
| CM-U-3 | `document_id` のテストベクタを Indexer 側のテストにも置くか、実 Indexer での照合を結合テストにするか | module-structure 7.4、architecture CA-U-9、interface CI-U-1 |
| CM-U-4 | 停止(SIGTERM)時の扱い(実行中のジョブを待たず、次回の回復で `failed` にする案) | module-structure 7.4、architecture 9章 |
| CM-U-5 | Crawler のヘルスチェックの要否 | module-structure 7.4、crawler-api CAPI-U-9 |
| CM-U-6 | architecture 11章にない仮値(Scheduler の判定周期、Job Runner の走査間隔、ハートビート失敗時の再試行間隔、Store 層クライアントのタイムアウト、ハートビート停止の待ち上限) | module-structure 7.4、architecture 11章、CA-U-1 |
| CM-U-7 | 索引・マッピングの作成を Crawler が担う場合の置き場所 | module-structure 7.4、architecture CA-U-11(I-6) |
| CM-U-8 | Web Connector を追加するときの構成(`next()` の最大ブロック時間、列挙中の一時失敗) | module-structure 7.4、interface CI-U-9・CI-U-11、connector-web CW-U-16(I-40) |
