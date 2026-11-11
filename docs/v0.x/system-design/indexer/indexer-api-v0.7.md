# Indexer API リファレンス v0.7

- 版: v0.7
- 更新日: 2026-11-10

## 0. この文書について

- 対象: Crawler から Indexer への内部 API の契約(開始通知、バッチ登録、`last_seen_at` の部分更新、終了通知、Status API、ソース削除の呼び出し)。
- 位置づけ: Indexer の API 契約を定める文書。プロダクト・設計判断を伴うものは決めず、第 6 章に「未決(ユーザー判断)」として集約した。本書の「未定義」「未決」は、本書でまだ決めていないことを指す。
- 読み方: 第 1 章で API の全体を確認し、第 4 章で各 API を同じ書式(概要 / エンドポイント / 呼び出し元 / リクエスト / レスポンス / エラー / 冪等性・注意事項 / 確認状況)で読む。
- 確認状況の区分: **確定**(ユーザー確定)、**案**(ユーザー未確定)、**提案**(本書の提案。案と同様に未確定)、**未決**(決めていない)、**推測**(根拠が弱い想定)。本文中の `(案)` などはこの区分。
- **案(推奨。ユーザー承認待ち)**: 推奨(承認待ち)の記述。ユーザーの承認ではなく、確定ではない。承認されるまで確定扱いにしない。
- **エンドポイント形・応答コード・JSON のキー名・型はすべて案**(項目の意味だけを定めている)。型は例 JSON からの推定で、各表の「型」列は案。
- 関連文書: `indexer-architecture-v0.7.md`(同じ `indexer/` 配下。責務、登録処理、書き込みの競合制御、削除の判断・実行、整合性、障害、将来拡張)。`opensearch/schema/` 配下: `search-index-v0.7.md`(検索インデックスのスキーマ)、`loreley-deletions-v0.7.md`(削除結果の構造と状態の意味)。
- 未決の ID は本書内の `API-U-n`。`indexer-architecture-v0.7.md` に対応する決定・案・未決があるものは「architecture K-n」「architecture P-n」「architecture U-n」と参照する(本書に関わるのは K7、K12、K18〜K30、P16、P25、P29、P32、P38、U-4、U-14、U-16、U-26、U-31 など)。本書で新たに確定扱いにするのは K12、K18〜K30 で、ほかの確定行は architecture の既存の K 番号に対応する。それ以外は案・未決である(K22 の `text_hash` は変更の有無の判定と要約の整合のための内部処理で、API 契約に現れない)。

## 1. API 一覧

| API | メソッド + パス(案) | 呼び出し元 | 用途 | 冪等性 | 確認状況 | 詳細 |
| --- | --- | --- | --- | --- | --- | --- |
| 開始通知 | `POST /crawls/start` | Crawler | クロールの開始を伝え、現行世代と削除結果(`running`)を作る | 冪等(同じ `crawl_id` で `running` かつ複写済みの項目が一致すれば状態を変えず成功。不一致は 409 で状態不変。architecture K24) | 存在は確定、契約の形は案 | 4.1 |
| `last_seen_at` 部分更新 | `POST /sources/{source_id}/last-seen` | Crawler | 列挙で見つかった文書の `last_seen_at` を `crawl_started_at` に更新(取得より前に要請。Update API の max 比較)。`crawl_id`・`crawl_started_at` は必須で、削除結果が受理可能な状態のときだけ受理する(architecture K23) | 冪等(max 比較) | 提案 | 4.2 |
| バッチ登録 | `POST /sources/{source_id}/documents:batch` | Crawler | 文書を同期で登録(文書単位の結果を返す)。受理条件は 4.2 と同じ(architecture K23) | 冪等(`document_id` と、検索インデックスの現在の文書との比較。変更のない文書は書かない) | 提案 | 4.3 |
| 終了通知 | `POST /crawls/{crawl_id}/finish` | Crawler | 列挙の終了を伝え、削除の判断・実行を非同期に起動(202) | 冪等(同じ内容の再送は 202。内容が異なる再送は 409。architecture K25) | 存在は確定、契約の形は案 | 4.4 |
| Status API | `GET /crawls/{crawl_id}` | Crawler | 削除結果を読み取りで返す | 読み取り(影響なし) | 存在は確定、契約の形は案 | 4.5 |
| ソース削除 1 | `POST /sources/{source_id}/deletions:discard` | Crawler | 終端状態でない削除結果を `discarded`(`source_deleted`)にする | 冪等。応答は実行中バッチの終了後(architecture P29) | 提案 | 4.6 |
| ソース削除 2 | `DELETE /sources/{source_id}/documents` | Crawler | 検索インデックスから `source_id` の文書を全削除(`delete_by_query` を再実行して消し切る。architecture K20、K28) | 冪等(再送では 0 件でも成功。何度でも再実行できる) | 提案 | 4.7 |
| ソース削除 3 | `DELETE /sources/{source_id}/deletion-records` | Crawler | `loreley-deletions` の当該ソースの記録を削除 | 冪等(何度でも再実行できる) | 提案 | 4.8 |

- Status API の利用者は Crawler。Admin View の削除結果の表示は、Admin API が `loreley-deletions` を直接読んで行い、`api` から `indexer` への通信は置かない。
- 文書の取得(`get_document`)は Search API が検索インデックスを ID で取得して行う。Indexer API にエンドポイントはない。
- 原本サイズ超過は独立した API ではなく、バッチ登録に関わる未決事項(4.9)。

## 2. 概要(通信の流れ)

Crawler がソースのロックを取得してから、次の順に Indexer を呼ぶ。

1. 開始通知(ロック取得後・列挙前)。章 4.1。
2. 見つかった文書の `last_seen_at` 部分更新の要請。**取得より前に行う**。章 4.2。
3. 文書のバッチ登録(同期。文書単位の結果が返る)。章 4.3。
4. 終了通知(202 で受理)。すべてのバッチ登録と `last_seen_at` 部分更新の応答を確認してから送る。章 4.4。
5. 削除結果の確認(Status API のポーリング)。章 4.5。

- 削除の判断・実行は、終了通知を受けた Indexer が非同期に行う。期限による削除を Crawler は要請しない。ソース削除での削除要請だけは Crawler が要請する(4.6〜4.8)。
- 同期 HTTP では遅い Indexer がクロール全体の所要時間を決める。MVP では許容する。

## 3. 共通事項

### 3.1 通信方式

- Crawler と Indexer は別コンテナ。メッセージブローカーを使わず HTTP で直接通信する(確定)。内部ネットワークだけで通信し、ホストに公開しない。単一ホスト、単一 Crawler、単一 Indexer、直列実行、認証なし。
- 契約は、将来 HTTP 部分をメッセージングに置き換えられるよう明確にする(重複して届いても安全であること、文書単位の結果が互いに依存しないこと)。
- 書き込み役は `indexer-architecture-v0.7.md` の責務表が正本。要点: 検索インデックスと `loreley-deletions`(仮名)に書くのは Indexer だけ。`loreley-jobs` に書くのは Crawler だけ。Admin API は書かず、読み取りのみで直接読む。
- 検索インデックスは、文書の本文・メタデータ・要約・処理状態・`last_seen_at` の唯一の正本である(architecture K18)。書き込みは PUT(Index API)を基本とし、`last_seen_at` だけの更新は Update API で行う(architecture K19)。

### 3.2 ロック所有情報の運び方(提案)

- 書き込みを伴う要請(バッチ登録、`last_seen_at` 部分更新、ソース削除の順 1)には、ロック所有情報 `lock`(`owner`、`job_id`)を添える。バッチ登録と `last_seen_at` 部分更新には、さらに `crawl_id`(= `job_id`)と `crawl_started_at` を**必須**で添え、受理条件の判定(下記。4.2、4.3。architecture K23)に使う。ソース削除の要請は開始通知を伴わず `deletion_result` を持たないため、別のエンドポイント(4.6〜4.8)で受け、この判定の対象外とする(`deletion_result` を要求しない。案)(提案)。
- **呼び出し種別の区別**(architecture K23): バッチ登録(`documents:batch`)と `last-seen` は `crawl_id`・`crawl_started_at` を必須とし、省略を許さない。省略できると、`crawl_id` を落とすだけで判定を回避できてしまうため。ソース削除は別のエンドポイントで区別する。
- **登録の受理条件**(architecture K23。確定): バッチ登録と `last_seen_at` 部分更新は、次をすべて満たすときだけ受理する。(1) `deletion_result-{crawl_id}` が存在する。(2) `source_id` が `deletion_result` のものと一致する。(3) `crawl_started_at` が複写値と一致する。(4) `status` が `running`。(5) `finish_received_at` が存在しない。(6) Crawler のロック所有確認に成功する。
  - 終端状態(`superseded` / `discarded` / `failed` / 判断済みの `deleted`・`skipped_by_ratio`・`validation_failed`)の `deletion_result` への登録は拒否する。終了通知の受理後(`finish_received_at` あり)の登録も拒否する。理由: 終了通知の受理後に登録すると、件数照合の前提(列挙の完了時点)が崩れ、終端状態の結果は旧世代の遅れた書き込みになるため。
  - 保持期間を超えて消えた `deletion_result` は「存在しない」として拒否する(消えた理由を区別しない)。
  - (1)〜(5) はリクエストの先頭で 1 回、(6) は文書ごとに確認する(下記の所有確認のとおり)。(6) の失敗は文書単位の `lock_not_owned`(3.4、API-U-13)で、リクエスト全体の拒否ではないため、拒否の 5 つの名称(`crawl_not_started`、`crawl_source_mismatch`、`crawl_started_at_mismatch`、`crawl_already_closed`、`crawl_finished`)には含めない。拒否の種類ごとにエラー名を分ける(3.4。API-U-19)。
- Indexer は書き込み前に、ロック文書(`loreley-jobs` の `lock-{source_id}`)を ID で取得し、要請したジョブの所有者で期限内であることを確認する。Indexer は要請を直列に処理し、所有確認を文書ごとに行う(案)。
- 確認できなければ書き込みを中止し、スキップ・リトライの対象にせずジョブ `failed`・削除しない(案)。文書単位の結果には `lock_not_owned` を返す(3.4、API-U-13)。
- 確認と書き込みの間の窓は MVP では既知の制限として許容する。確認の対象は登録と `last_seen_at` の更新。要約の書き込みと削除の実行は対象外。
- ソース削除の順 2・3(4.7・4.8)には、ジョブがロックを最後まで保持する(architecture K29)ので、ロック所有情報を添える。Crawler 側のロック設計の具体は Crawler 設計で決める(API-U-14)。

### 3.3 ID

- `document_id` = `SHA-256(source_id + "\0" + external_id)` の 16 進文字列(小文字)。NUL 文字で区切る。
- `external_id` は、ハッシュの前に Unicode NFC へ正規化し、パス区切りを `/` に統一する(ルートからの相対パス、先頭に `/` を付けない)。大文字小文字は区別したまま扱う。
- 同じ文書を再取得すると同じ ID になるため、再実行しても重複しない。検索インデックスは `document_id` を文書 ID(`_id`)として使う。
- `source_id` は登録後に変更できない。パスの変更・リネームは「旧 ID の削除 + 新 ID の追加」として扱う(リネームの追跡は初期要件にしない)。
- `crawl_id` は Crawler のジョブ ID をそのまま使う(Indexer は採番しない)。

### 3.4 エラー応答の形と HTTP ステータス(提案)

- 文書単位の結果は常に HTTP 200 の本文で返す。リクエスト全体の失敗だけ HTTP エラーコードを使う。
- エラー本文の形(提案):

```json
{
  "error": {
    "code": "invalid_request",
    "message": "documents must not be empty",
    "retryable": false
  }
}
```

| HTTP | `code` の例(提案) | 意味 | Crawler の扱い |
| --- | --- | --- | --- |
| 400 | `invalid_request` | リクエストの形式不正 | ジョブ `failed` |
| 404 | `crawl_not_found` | Status API の 404 条件(4.5) | ポーリングの失敗(第 5 章) |
| 409 | `crawl_already_finished` / `stale_crawl_started_at` | 開始通知の 409(順 1・3。4.1) | ジョブ `failed` |
| 409 | `crawl_start_conflict`(案) | 開始通知の再送で、同じ `crawl_id` の複写済み項目と内容が一致しない(4.1 の順 2。architecture K24。コード名は案) | ジョブ `failed` |
| 409 | `crawl_not_started`(案) | `deletion_result-{crawl_id}` が存在しない(開始通知の未送信、保持期間超過での消去、`loreley-deletions` の喪失。4.2、4.3。architecture K23。コード名は案) | リトライせずジョブ `failed` |
| 409 | `crawl_source_mismatch`(案) | `source_id` が `deletion_result` のものと一致しない(4.2、4.3。案) | リトライせずジョブ `failed` |
| 409 | `crawl_started_at_mismatch`(案) | バッチ登録・`last-seen` 部分更新の `crawl_started_at` が、`deletion_result-{crawl_id}` の複写値と一致しない(4.2、4.3。案) | リトライせずジョブ `failed` |
| 409 | `crawl_already_closed`(案) | `deletion_result` が終端状態(`superseded` / `discarded` / `failed` / `deleted` / `skipped_by_ratio` / `validation_failed`。4.2、4.3。案) | リトライせずジョブ `failed` |
| 409 | `crawl_finished`(案) | `deletion_result` が `running` だが、終了通知を受理済み(`finish_received_at` あり。4.2、4.3。案) | リトライせずジョブ `failed` |
| 409 | `finish_content_mismatch`(案) | 終了通知の再送で、内容が最初に受理した内容と異なる(4.4。architecture K25。コード名は案) | ジョブ `failed`(案) |
| 5xx / 接続エラー / タイムアウト | `unavailable` など | Indexer の異常 | リトライ、直らなければジョブ `failed` |

- 上表の 409 は、Crawler と Indexer の間の応答である。検索インデックスへの書き込みで起きる 409(`if_seq_no` / `if_primary_term` の不一致、`op_type=create` の競合)は Indexer の内部で読み直して再判定し(4.3)、そのまま Crawler への HTTP 409 にはしない。
- 開始通知の `crawl_already_finished`(4.1)と登録の `crawl_already_closed`(4.2、4.3)は、開始通知用と登録用の意図的な区別とする(案)。コード名を 1 つに統一するかは API-U-19 で併せて検討する。
- 終了通知の再送は、同じ内容なら冪等な 202、最初に受理した内容と異なれば 409(4.4、architecture K25。コード名は案。API-U-21)。開始通知の 409 と、上表の登録の拒否(`crawl_not_started` から `crawl_finished` までの 5 件。拒否そのものは architecture K23 で確定。コード名・HTTP は案。API-U-19。architecture では「案: 409(API-U-19)」と併記)と、終了通知の 409 を除き、コード名・HTTP の割り当ては未定義。`retryable` は Crawler のリトライ判断に使う補助で、必須ではない。
- **`lock_not_owned`**: 所有確認は文書ごとに行う(案)ため、リクエスト全体の 409 に固定せず、提案(案)として 4.3 の文書単位の結果に `failure_type: lock_not_owned`(4.2 は `result: lock_not_owned`)を加え、Crawler はそれをスキップ・リトライの対象にせずジョブ `failed` として扱う。バッチの途中でロックを失った場合の部分結果の返し方(確認済みの文書の結果と、未処理の文書の扱い)と、バッチの先頭で失敗した場合に全体のエラーにするかは未決(API-U-13)。

### 3.5 冪等性・リトライ方針

- 全 API は重複して届いても結果が変わらない(Status API は読み取り)。再送は安全。
- **登録の失敗の扱い**(バッチ登録、`last_seen_at` 部分更新):
  - 検索インデックスへの登録失敗は、Indexer が文書単位の失敗種別を返し、Crawler が最大試行回数までリトライして、それでも失敗したらスキップ。リトライは Crawler 側の既定値(最大 3 回、バックオフは初回 1 秒・2 倍・上限 30 秒・ジッタあり。いずれも案)。
  - スキップの対象は**文書固有の拒否**(マッピング違反、文書の内容に起因する 4xx など)だけ。文書固有の 4xx のスキップが連続 20 件(案。設定可能)に達したら `failed`。
  - 接続エラー、タイムアウト、HTTP 429、5xx、`cluster_block_exception`、circuit breaker は OpenSearch 全体の異常として、スキップせずジョブ `failed`。Indexer の異常(接続不可、タイムアウト、5xx 等)も同様で、リトライしても直らなければジョブ `failed`。リトライ回数・連続 20 件・エラー種別・`failed` の対象範囲の細部は案。
  - 終了通知が Indexer に受理される前にクロールが失敗した場合は、削除しない。受理された後は、応答喪失などで Crawler 側のジョブが失敗扱いになっても削除処理が継続しうる(確定。architecture K12。4.4)。
  - ジョブ `failed` の対象は、開始通知、登録、`last_seen_at` の部分更新、終了通知の失敗に限る。Status API のポーリングの失敗は含まない。`last_seen_at` を保存できなければクロールを完了扱いにしない、は案(ユーザー未確認)。
  - 抽出の失敗はスキップではなく `extract_failed`(タイトルとメタデータを登録)として扱い、リトライしない。
  - 検索インデックスへの書き込みの競合(409)は文書固有の拒否ではないので、上記のスキップの対象に含めない。Indexer が文書を読み直して再判定し、読み直しの上限を超えたときだけ文書単位の失敗(`write_conflict`。名称は仮)として返す(4.3。上限の値は architecture U-31)。Crawler はリトライするが、リトライしても直らない場合の扱い(スキップするか、ジョブ `failed` にするか。連続 20 件の計数に含めるか)は未決(API-U-7)。`last_seen_at` の Update の競合上限超過(`update_conflict`。4.2、4.3 (b))も同様に、リトライし、直らなければ Crawler の扱いは未決(API-U-7)。ただし、`last_seen_at` を保存できないまま(要請の失敗が解消しないまま)クロールを完了扱いにはしない(本節の下記の案)。
- 通知(開始・終了)の失敗(リトライ設定の回数まで試しても直らない場合)はジョブ `failed`。削除が行われないだけで安全。
- 数値(バッチの件数と合計サイズ、タイムアウト、並列度、リトライ・ポーリングの回数や間隔)は未決(API-U-5、API-U-6)。

### 3.6 時刻の扱い

- 時刻(`crawl_started_at`、`last_seen_at`、TTL の判定)は、Crawler と Indexer が同じホストの時計で動く前提。
- 例 JSON の時刻は ISO 8601(UTC)で示す(形式は案)。
- **日時の正規化**(案): 保存・比較する日時(`last_seen_at`、`crawl_started_at`、`source_updated_at` など)は、Indexer が UTC・ISO 8601・ミリ秒精度(例 `2026-11-09T01:00:00.000Z`)に正規化して扱う。Crawler の入力が秒精度やタイムゾーン付きでも、検索インデックスの `date` 型と max 比較のスクリプト(Instant にパースして比較する)で同じ値として扱うため。本書の例 JSON は読みやすさのためミリ秒を省いている。実機での確認項目は architecture U-31 に追加する(確認は architecture U-31(7))。

## 4. API リファレンス

### 4.1 開始通知

**概要**: ロック取得後、列挙の前に送る。Indexer は現行世代と、`running` の削除結果を作る。現行世代は、そのソースで最後に受理した開始通知の `crawl_id`。

**エンドポイント**: `POST /crawls/start`(案)

**呼び出し元**: Crawler(ロック取得後・列挙前)

**リクエスト**(項目名は案。API-U-1、architecture U-14):

| 名前 | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `crawl_id` | string | ○ | Crawler のジョブ ID |
| `source_id` | string | ○ | データソース ID |
| `crawl_started_at` | datetime | ○ | クロールの開始時刻 |
| `ttl` | 未定 | ○ | 設定スナップショット。値は未決 |
| `ratio_threshold` | 未定 | ○ | 設定スナップショット。値は未決 |
| `min_delete_count` | 未定 | ○ | 設定スナップショット。値は未決 |
| `force_delete` | boolean | 任意(既定 `false`) | 削除結果の `forced` として複写して持つ値そのもの。別の項目は重ねない |
| `rewrite_mode` | boolean | 任意(既定 `false`) | 再書き込みモード(採用は architecture K26 で確定。**名称は仮。指定の経路は推測。保持先は未決**。API-U-22)。`true` のとき、このクロールのバッチ登録は、変更なしの判定(4.3 の (b))をせず、本文ごと全文書き込みし、要約は引き継がず `pending` に戻す。削除の判断には影響しない。手動実行のクロールの起動時のみ指定できる想定 |

必須/任意は内容の列挙に基づく(案)。下の例の `"<値は未決>"` は、型と値が未決のため置いたプレースホルダ(文字列ではない。実際の値ではない)。

```json
{
  "crawl_id": "job-20261109-0001",
  "source_id": "src-docs",
  "crawl_started_at": "2026-11-09T01:00:00Z",
  "ttl": "<値は未決>",
  "ratio_threshold": "<値は未決>",
  "min_delete_count": "<値は未決>",
  "force_delete": false
}
```

**レスポンス**(成功。ボディは未定義で、空でもよい。案):

| 名前 | 型 | 説明 |
| --- | --- | --- |
| `crawl_id` | string | 受理した `crawl_id` |
| `status` | string | `running` |

```json
{ "crawl_id": "job-20261109-0001", "status": "running" }
```

**エラー**:

| ステータス | コード(提案) | 条件 |
| --- | --- | --- |
| 409(案) | `crawl_already_finished` | `deletion_result-{crawl_id}` がすでに終端状態(終了したクロールの通知が再送されても `running` に戻さない) |
| 409(案) | `crawl_start_conflict` | 同じ `crawl_id` で `running` の再送が、複写済みの項目(`source_id`、`crawl_started_at`、`ttl`、`ratio_threshold`、`min_delete_count`、`force_delete`)のどれかと一致しない(architecture K24。コード名は案)。状態は変えない |
| 409(案) | `stale_crawl_started_at` | `crawl_started_at` が現行世代のそれより古い(世代の巻き戻り防止) |
| 400 | `invalid_request` | リクエストの形式不正 |
| 5xx / 接続エラー | `unavailable` | Indexer の異常 |

- 判定の順序: (1) 終端状態なら 409(`crawl_already_finished`)→ (2) 同じ `crawl_id` で `running` なら、複写済みの項目と今回のリクエストを直接比較し、すべて一致すれば状態を変えずに成功(再送)、1 つでも不一致なら状態を変えずに 409(`crawl_start_conflict`)→ (3) 世代が古ければ 409(`stale_crawl_started_at`)。
- Crawler は 409 をジョブ `failed` として扱う。

**冪等性・注意事項**:

- **再送の一致検証**(architecture K24。確定): 同じ `crawl_id` で削除結果が `running` のときは、内容を見ずに成功にせず、`deletion_result-{crawl_id}` に複写済みの項目と今回のリクエストを直接比較する。比較するのは `source_id`、`crawl_started_at`、`ttl`、`ratio_threshold`、`min_delete_count`、`force_delete`(省略時は `false` として複写値の `forced` と比べる)。すべて一致なら成功(冪等。状態不変)、不一致なら 409 `crawl_start_conflict`(状態不変)。現行世代 `deletion-{source_id}` は新しい開始通知で上書きされるため、比較には使わない。`rewrite_mode` を比較項目に含めるかは未決(API-U-22)。
- **Crawler の義務**(Crawler 設計への要件。architecture K24 の検証が成り立つための前提): Crawler は、最初に組み立てた設定スナップショット(`crawl_started_at`、`ttl`、`ratio_threshold`、`min_delete_count`、`force_delete`)をジョブごとに保持し、開始通知の再送では同一の値を送る。再送のたびに設定を読み直すと、設定変更が間に入った場合に値が変わり、`crawl_start_conflict`(409)になってジョブが `failed` になる(設定を途中で変えたことの検出としては意図どおりだが、Crawler が値を固定していれば起きない)。`ttl` などの値の型が未決のため、表記の揺れの扱い(比較前の正規化)は未決(API-U-20)。
- **即時の受理**: 旧い削除が待機中・判定中・実行中でも待たせず、すぐに受理する。
- **Indexer の動作**(判定を通ったとき): `deletion-{source_id}`(現行世代。用途は開始通知の世代判定と直近の開始通知の記録)を更新し、`deletion_result-{crawl_id}` を設定スナップショットの複写つきで `running` で作る(複写は案)。同じソースに、`finish_received_at` の無い `running` の旧い削除結果(終了通知が届かなかった世代)があれば `discarded`(理由 `superseded`)にする。`finish_received_at` のある結果には何もしない。判定と実行は複写した値を使い、`deletion-{source_id}` からは読まない。
- 通知の失敗(リトライ設定の回数まで試しても直らない場合)はジョブ `failed`。開始通知の失敗は、削除が行われないだけで安全。

**確認状況**: 開始通知の存在は確定。エンドポイント形、応答コード、409、設定スナップショットの複写、キー名は案。再送の一致検証は確定(architecture K24)。`crawl_start_conflict` のコード名は案。再書き込みモードの採用は確定(architecture K26)で、`rewrite_mode` の名称・指定経路・保持先は未決(API-U-22)。未決: API-U-1(項目名)、API-U-12(409 条件)、API-U-5(設定値)、API-U-20(比較前の正規化・コード名)、API-U-22(再書き込みモードの名称・指定経路・保持先)。

### 4.2 `last_seen_at` の部分更新(提案)

**概要**: Crawler が列挙で見つけたすべての文書について、**取得より前に**要請する。Indexer は Update API のスクリプトで現在値と max 比較し、新しい値のときだけ `last_seen_at` を書く(現在値以上なら noop)。ほかのフィールドは変更しない。文書がなければ(`not_found`)何もしない(upsert しない)。`not_found` にするのは、検索インデックスの 404 のうち `document_missing_exception`(文書がない)のときだけ。`index_not_found_exception` などインデックス不在・設定の異常は文書がないこととは別なので、`not_found` にせず OpenSearch 全体の異常(5xx `unavailable`)として扱う(案)。取得・抽出・登録が失敗しても更新済みのまま残るので、取得に失敗してスキップした文書が TTL で誤削除されない。書き込みの前に、登録の受理条件(3.2。`crawl_started_at` が `deletion_result-{crawl_id}` に複写された値と一致することを含む)を判定する(architecture K23)。

**エンドポイント**: `POST /sources/{source_id}/last-seen`(案)

**呼び出し元**: Crawler(列挙で見つかった文書。取得より前)

**リクエスト**: 要請する単位は文書 ID の配列(提案。単位と件数は未決)。バッチ登録では Indexer が `document_id` を算出して返すのに対し、ここでは Crawler が 3.3 の規則で算出して渡す(非対称)。`external_id` の配列を渡して Indexer が算出する形にするかは未決(API-U-7)。

| 名前 | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `source_id`(パス) | string | ○ | データソース ID |
| `crawl_id` | string | ○ | クロール ID(= `job_id`)。必須で、省略できない(3.2) |
| `lock` | object(`owner`, `job_id`) | ○ | ロック所有情報(3.2) |
| `crawl_started_at` | datetime | ○ | 書き込む値。`deletion_result-{crawl_id}` の複写値と一致している必要がある(下記) |
| `document_ids` | string[] | ○ | 3.3 の規則で Crawler が算出した ID。件数の上限は未決 |

```json
{
  "crawl_id": "job-20261109-0001",
  "lock": { "owner": "crawler-1", "job_id": "job-20261109-0001" },
  "crawl_started_at": "2026-11-09T01:00:00Z",
  "document_ids": [
    "6b5851d90534fc00e388eeb8bd8c79ae48b8bf5c58e4fb0191e708afa28674d7",
    "7f2216b2a91e74fe53ce071ed0bd8dcebccaa904f9a8d8004f592b0a4210a9c5"
  ]
}
```

**レスポンス**(文書単位):

| 名前 | 型 | 説明 |
| --- | --- | --- |
| `results[].document_id` | string | 対象の文書 ID |
| `results[].result` | string | `updated` / `unchanged` / `not_found` / `update_conflict` / `lock_not_owned` |

```json
{
  "results": [
    { "document_id": "6b5851d90534fc00e388eeb8bd8c79ae48b8bf5c58e4fb0191e708afa28674d7", "result": "updated" },
    { "document_id": "7f2216b2a91e74fe53ce071ed0bd8dcebccaa904f9a8d8004f592b0a4210a9c5", "result": "not_found" }
  ]
}
```

- `updated`: 新しい値を書いた。`unchanged`: 現在値以上のため書かない(noop)。`not_found`: 検索インデックスに文書がなく何もしない(新規文書では正常)。この 3 つは成功扱いで、スキップ扱いにしない。
- `update_conflict`(名称は仮): Update が `retry_on_conflict` の回数を超えて 409 になった文書(文書単位の失敗。再試行可能)。成功扱いにしない。Crawler はリトライし、直らなければ Crawler の扱いは未決(API-U-7。3.5)。ただし `last_seen_at` を保存できないままクロールを完了扱いにはしない(3.5 の案)。文書単位ではなくリクエスト全体の失敗にするかも未決(API-U-7)。
- `lock_not_owned`: 所有確認に失敗した文書(提案(案)。成功扱いではなくジョブ `failed`。3.4)。
- **用語の区別**: ここでの `unchanged` は「`last_seen_at` を書かなかった(現在値以上)」の意味で、文書の内容は関係しない。4.3 の `change: unchanged`(変更がなく全文書き込みをしなかった)とは別の概念。

**エラー**:

| ステータス | コード(提案) | 条件 |
| --- | --- | --- |
| 400 | `invalid_request` | リクエストの形式不正 |
| 409(案) | `crawl_not_started`(案) | `deletion_result-{crawl_id}` が存在しない(開始通知の未送信、保持期間超過での消去、`loreley-deletions` の喪失)。書き込まずに拒否し、リトライせず Crawler はジョブ `failed`(案) |
| 409(案) | `crawl_source_mismatch`(案) | `source_id` が `deletion_result` のものと一致しない |
| 409(案) | `crawl_started_at_mismatch`(案) | `crawl_started_at` が複写値と一致しない。リクエスト全体のエラー(文書単位の結果は返さない)。リトライせず Crawler はジョブ `failed`(案) |
| 409(案) | `crawl_already_closed`(案) | `deletion_result` が終端状態(`superseded` / `discarded` / `failed` / `deleted` / `skipped_by_ratio` / `validation_failed`) |
| 409(案) | `crawl_finished`(案) | `deletion_result` が `running` だが終了通知を受理済み(`finish_received_at` あり) |
| 5xx | `unavailable` | 書き込み不可(OpenSearch への書き込み失敗、インデックス不在など。文書がないこと(`document_missing_exception`)は含まない)。Crawler はジョブ `failed`・削除しない |

**冪等性・注意事項**:

- 重複して届いても結果は変わらない(max 比較。architecture K27。確定)。確認と書き込みの間の窓は既知の制限(3.2)。
- `last_seen_at` の Update は、検索インデックスの内部で文書全体を再インデックスするため、列挙したすべての文書で発生する。この負荷(処理時間・インデックスサイズ・マージ負荷)は architecture 15.4 の測定項目に含まれる(設計は変えない)。
- Update API の内部の競合は `retry_on_conflict` で再試行する(値は未決。実機確認。architecture U-31)。再試行を超えて 409 になった文書は、文書単位の `result: update_conflict`(名称は仮)として返す。登録や要約の書き戻しの PUT と並行しても、互いの内容を失わない(architecture 5章)。
- **受理条件の判定**(architecture K23。確定): 3.2 の受理条件の (1)〜(5) を、所有確認や文書ごとの処理より前に 1 回だけ判定する。満たさなければリクエスト全体をエラーにして何も書かない(文書単位の結果は返さない)。(6) のロック所有確認は文書ごとで、失敗は文書単位の `result: lock_not_owned`(API-U-13。上記 5 つの拒否名には含めない)。
- **`crawl_started_at` の照合の目的**: 誤った `crawl_started_at` で `last_seen_at` を書くと、件数照合や TTL 判定の基準がずれる。Crawler の取り違えを早く検出する。照合しなくても削除は安全側(件数照合の不一致で削除されない)に倒れるが、誤りの検出が遅れる。
- 対象は通常クロールの `last_seen_at` 部分更新(バッチ登録も同じ)に限る。ソース削除の要請は別のエンドポイント(4.6〜4.8)で、`deletion_result` を要求しない。
- 終端状態の `deletion_result`、終了通知の受理後の `deletion_result`(`finish_received_at` あり)は、`crawl_started_at` が一致していても拒否する。保持期間超過で消えた `deletion_result` は存在しないものとして拒否する(エラー名は `crawl_not_started`。案)。Crawler は開始通知を送り直さずジョブ `failed` とする(クロールの途中で世代の前提を失っているため。案)。

**確認状況**: 提案(案)。`last_seen_at` を検索インデックスの文書に持ち、`crawl_started_at` を渡して Indexer が書くことは確定。`last_seen_at` だけの更新を Update API で行うことは architecture K19 で確定。max 比較のスクリプト、文書なし(404)・競合(409)の扱いは architecture K27 で確定。`update_conflict` の名称は仮、`retry_on_conflict` の値は未決(architecture U-31)。受理条件の判定(`crawl_started_at` の照合、終端状態・受理後の拒否、`crawl_id` の必須化)は architecture K23 で確定。エラー名は案(API-U-19)。要請の単位・`document_id` の算出主体は未決(API-U-7)。ロック失敗時の返し方は未決(API-U-13)。

### 4.3 バッチ登録(提案)

**概要**: 文書を同期 HTTP で登録する。応答は文書単位で、失敗した文書だけを再送できる。新規・更新・変更なしの区分も含める(案・推奨。ユーザー承認待ち。API-U-9。architecture P38)。受理条件は 3.2、4.2 と同じ。集計して `loreley-jobs` に記録するのは Crawler。Indexer の登録処理(抽出、検索インデックスとの比較、書き込み、競合時の読み直し)は `indexer-architecture-v0.7.md` の 4.3 と 5章を参照。

Indexer が文書ごとに行う書き込みは、次のとおり(architecture 4.3、K27。確定。変更のない文書を PUT しないこと、変更なしの文書の `last_seen_at` を補う Update、max 比較を含む)。

1. 抽出・正規化したあと、検索インデックスから文書を ID で取得する(GET)。
2. 次のいずれかになる。
   - (a) **文書がない(新規)**: 全フィールドを組み立て、`op_type=create` の PUT で書く(`change: created`)。
   - (b) **文書があり、`content_hash`・`text_hash`・`index_status`・メタデータ(`title`、`source_updated_at`、`mime_type`、`size`、`url`、`path`)がすべて同じ**: 書かない。要約も更新しない(日時は 3.6 の正規化後の値で比べる)。`last_seen_at` が `crawl_started_at` より古ければ、`last_seen_at` だけを Update で補う(`change: unchanged`)。この補完は、4.2 の要請がすでに成功していれば不要(`last_seen_at` は `crawl_started_at` 以上になっている)で、4.2 が失敗・省略された場合にだけ補う(architecture K27。確定)。補完の Update が `retry_on_conflict` を超えて 409 になったときは、その文書の失敗として `update_conflict`(4.2 と同じ。名称は仮)を返す。
   - (c) **文書があり、いずれかが違う**(再書き込みモード(4.1)のときは、(b) の判定をせず、常にここへ進む。要約は引き継がず `pending` に戻す): 読んだ `_seq_no` / `_primary_term` を `if_seq_no` / `if_primary_term` に付けて全体を PUT する(`change: updated`)。メタデータだけが変わった場合(`content_hash` と `text_hash` が同じ)は、要約を引き継ぐ。本文が変わった場合は要約を `pending` に戻す。例外として、抽出に失敗して `extract_failed` になる書き込みは、`content`・`text_hash`・`summary` を書かず `summary_status=disabled` とする。`summary_model` も書かず、`content_hash` は新しい値を書く(architecture K30、E-45。旧い値は置き換えで消える)。
3. PUT が 409(読んだあとに別の書き込みが先に入った)なら、手順 1 から読み直して再判定する。読み直しの回数がリトライ設定の回数を超えたら、文書単位の失敗(再試行可能)として返す(上限の値は architecture U-31)。

**エンドポイント**: `POST /sources/{source_id}/documents:batch`(案)

**呼び出し元**: Crawler(取得・抽出対象の文書ごと)

**リクエスト**: `raw_content` は JSON で運ぶため base64 とする(提案。上限と運び方の最終形は未決)。base64 は原本より約 33% 大きくなり、JSON の解析と複写でメモリも使う。運び方は multipart(原本をバイナリのまま送る)や文書ごとの個別送信などの選択肢を残す(案。API-U-17。実測項目は architecture 15.4)。`document_id` は Indexer が 3.3 の規則で算出して返す(Crawler が付けた値との照合はしない提案)。

| 名前 | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `source_id`(パス) | string | ○ | データソース ID |
| `crawl_id` | string | ○ | クロール ID(= `job_id`) |
| `crawl_started_at` | datetime | ○ | クロールの開始時刻。Indexer が `last_seen_at` に書く値(4.2 と同じ値)。`deletion_result-{crawl_id}` の複写値と一致している必要がある(下記)。`crawl_id` とともに必須で、省略できない(3.2) |
| `lock` | object(`owner`, `job_id`) | ○ | ロック所有情報(3.2) |
| `documents[]` | object[] | ○ | 登録する文書(要素の項目は下表)。件数・合計サイズは未決(API-U-6) |

`documents[]` の要素(Connector(Crawler)が Indexer に渡す文書。項目名・型は案。`source_id` はパスから取るため要素には含めない):

| 名前 | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `external_id` | string | ○ | データソース内で一意な識別子(ルートからの相対パス、ページ ID 等)。`document_id` の素材になる ID の責務で、`url` / `path` とは別。3.3 の正規化を適用する |
| `title` | string | ○ | タイトル(取得できなければファイル名) |
| `url` | string | 任意 | アクセス可能な原文の URL(案・推奨。ユーザー承認待ち。API-U-3。architecture U-16) |
| `path` | string | 任意 | データソース内の文書パス(案・推奨。ユーザー承認待ち。API-U-3)。`url` とは独立した任意項目で、どちらか一方だけでも、両方でも渡せる。検索・絞り込みへの使用と最大長は未決 |
| `mime_type` | string | ○ | 文書形式 |
| `raw_content` | string(base64) | ○ | 取得済みの原本(MVP では参照ではなく原本そのものを渡す。base64 は提案)。抽出前のデータで、検索インデックスの `content`(抽出後の本文)とは別物 |
| `content_hash` | string | ○ | 原本の SHA-256 |
| `source_updated_at` | datetime | ○ | データソース上の更新日時(ローカルでは `mtime`) |
| `size` | integer | ○ | 原本のサイズ(バイト) |
| `fetched_at` | datetime | 任意 | 原本を取得した日時。取得を省略した場合は更新しない(MVP は全件取得で省略しない) |
| `metadata` | object | 任意 | Connector 固有の追加属性 |

必須/任意は例 JSON と各項目の意味からの推定(案)。

- `url` / `path` を 2 項目とする案(推奨)は、`external_id`(ID)・`url`(アクセス先)・`path`(データソース内の位置)の役割を分けるためのもの。Wiki のようにページ ID を `external_id` にする場合など、3 つは同じ値にならない。
- `fetched_at` と `metadata` の保存先は未定義。保存するか受け取るだけかは未決(API-U-2。architecture U-16)。
- `last_seen_at` は要素に含めない。Crawler はリクエストの `crawl_started_at`(クロールの開始時刻)を渡し、Indexer が `last_seen_at` に書く(4.2)。書き込みの前に、3.2 の受理条件を判定し(`deletion_result-{crawl_id}` に複写された値(開始通知の値)との照合を含む)、満たさなければリクエスト全体のエラーにする(architecture K23)。`fetched_at` は「取得した日時」、`last_seen_at` は「列挙で見つかった日時」。
- `content` の意味は場所ごとに異なる: Connector → Indexer は `raw_content`(原本)、検索インデックスは `content`(抽出・正規化後の本文。検索用に解析され、`_source` にも保持される唯一の正本)。

```json
{
  "crawl_id": "job-20261109-0001",
  "crawl_started_at": "2026-11-09T01:00:00Z",
  "lock": { "owner": "crawler-1", "job_id": "job-20261109-0001" },
  "documents": [
    {
      "external_id": "page-10023",
      "title": "セットアップ手順",
      "url": "https://wiki.example.com/pages/10023",
      "path": "開発ガイド/セットアップ手順",
      "mime_type": "text/markdown",
      "raw_content": "aGVsbG8=",
      "content_hash": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
      "source_updated_at": "2026-11-08T12:00:00Z",
      "size": 5,
      "fetched_at": "2026-11-09T01:02:00Z",
      "metadata": {}
    }
  ]
}
```

リクエスト例は 1 文書目だけを示す(応答例は `page-10023`、`page-10024`、`page-10025` の 3 文書を送った場合。例では `external_id` を Wiki のページ ID とし、`url`(アクセス先)と `path`(データソース内の位置)は別の値にしている)。

**レスポンス**(HTTP 200。文書単位):

| 名前 | 型 | 説明 |
| --- | --- | --- |
| `results[].external_id` | string | 送られた `external_id` |
| `results[].document_id` | string | Indexer が算出した ID |
| `results[].status` | string | `ok` / `failed` |
| `results[].change` | string | `created` / `updated` / `unchanged`(`ok` のとき。案・推奨。ユーザー承認待ち。architecture P38)。`created`: 新規の文書(上記 (a))。`updated`: 本文(抽出後)またはメタデータの変更があり、全文書き込みをした(メタデータだけの変更を含む。(c))。`unchanged`: 原本ハッシュ・抽出後の本文・メタデータ・処理状態がすべて同じで、全文書き込みをしなかった((b)。`last_seen_at` の Update だけを行う場合を含む)。再書き込みモード(4.1)では、既存の文書も `updated` になる。区分の採否と境界は未決(API-U-9) |
| `results[].extract_failed` | boolean | 抽出に失敗し、タイトルとメタデータを登録した場合 `true` |
| `results[].failure_type` | string | `failed` のとき。候補は下記(提案。具体名は未決) |
| `results[].message` | string | 失敗の説明(任意。案) |

```json
{
  "results": [
    {
      "external_id": "page-10023",
      "document_id": "6b5851d90534fc00e388eeb8bd8c79ae48b8bf5c58e4fb0191e708afa28674d7",
      "status": "ok",
      "change": "created",
      "extract_failed": false
    },
    {
      "external_id": "page-10024",
      "document_id": "7f2216b2a91e74fe53ce071ed0bd8dcebccaa904f9a8d8004f592b0a4210a9c5",
      "status": "failed",
      "failure_type": "document_rejected",
      "message": "mapping violation"
    },
    {
      "external_id": "page-10025",
      "document_id": "48ea91b73f76334d8cf88f6a77438e740ba9d54a338970ad1433aa2f504c2c40",
      "status": "ok",
      "change": "unchanged",
      "extract_failed": false
    }
  ]
}
```

`failure_type` の候補(提案):

| 値 | 意味 | Crawler の扱い |
| --- | --- | --- |
| `document_rejected` | 文書固有の拒否 | リトライ後スキップ(連続 20 件でジョブ `failed`。3.5) |
| `store_error` | OpenSearch 全体の異常 | ジョブ `failed` |
| `lock_not_owned` | 所有確認の失敗(3.2、3.4) | スキップ・リトライの対象にせずジョブ `failed` |
| `write_conflict`(名称は仮) | 書き込みの競合(409)の読み直しが上限を超えた(再試行可能。手順 3) | リトライする。直らなければ Crawler の扱いは未決(API-U-7。文書固有の拒否ではないため、3.5 のスキップの対象には含めない) |
| `update_conflict`(名称は仮) | 手順 2 (b) の補完 Update が `retry_on_conflict` を超えて 409 になった(再試行可能。4.2 と同じ) | `write_conflict` と同じ。リトライし、直らなければ Crawler の扱いは未決(API-U-7)。`last_seen_at` を保存できないままクロールを完了扱いにはしない(3.5) |

**エラー**:

| ステータス | コード(提案) | 条件 |
| --- | --- | --- |
| 400 | `invalid_request` | リクエストの形式不正(例: `documents` が空) |
| 409(案) | `crawl_not_started`(案) | `deletion_result-{crawl_id}` が存在しない(開始通知の未送信、保持期間超過での消去、`loreley-deletions` の喪失)。何も書かずに拒否し、リトライせず Crawler はジョブ `failed`(architecture K23。コード名は案) |
| 409(案) | `crawl_source_mismatch`(案) | `source_id` が `deletion_result` のものと一致しない |
| 409(案) | `crawl_started_at_mismatch`(案) | `crawl_started_at` が複写値と一致しない。リクエスト全体のエラー(文書単位の結果は返さない)。リトライせず Crawler はジョブ `failed`(案) |
| 409(案) | `crawl_already_closed`(案) | `deletion_result` が終端状態(`superseded` / `discarded` / `failed` / `deleted` / `skipped_by_ratio` / `validation_failed`) |
| 409(案) | `crawl_finished`(案) | `deletion_result` が `running` だが終了通知を受理済み(`finish_received_at` あり) |
| 5xx / 接続エラー / タイムアウト | `unavailable` など | Indexer の異常。リトライし、直らなければジョブ `failed` |

**冪等性・注意事項**:

- **受理条件の判定**(architecture K23。確定): 4.2 と同じ(3.2)。文書の処理(抽出、検索インデックスへの書き込み)の前に、`deletion_result-{crawl_id}` の存在、`source_id` の一致、`crawl_started_at` の複写値との一致、`status` が `running`、`finish_received_at` がないこと((1)〜(5))を 1 回だけ判定し、満たさなければリクエスト全体のエラーにして何も書かない。(6) のロック所有確認は文書ごとで、失敗は文書単位の `failure_type: lock_not_owned`(3.4、API-U-13)であり、上記 5 つの拒否名には含めない。終端状態や終了通知の受理後の `deletion_result` は、`crawl_started_at` が一致していても拒否する。保持期間超過で消えた `deletion_result` は存在しないものとして拒否する。いずれの拒否もリトライしても直らないため、リトライ対象にせずジョブ `failed` とする。コード名と HTTP の割り当ては案(API-U-19)。
- 再送しても登録の状態が変わらない。同じ内容の再送は、検索インデックスの現在の文書と比べて変更なし((b))になり、書き込まれない。Indexer が `raw_content` の SHA-256 を計算して `content_hash` と照合するかは未決(API-U-15。architecture U-26)。
- **1 文書の書き込みは原子的**: 全フィールドは 1 回の PUT で書かれる。成功が登録の完了で、本文だけが新しく処理状態が古い、といった途中の状態は存在しない。
- 抽出の失敗は `status: ok` かつ `extract_failed: true`(失敗ではなくタイトルとメタデータの登録。リトライしない)。`extract_failed` の文書は `content` と `text_hash` を持たず、要約も生成しない。すでに `indexed` の文書が抽出失敗になったときは、`index_status` が変わるため (c) に進み、全体の PUT で旧 `content`・`text_hash`・要約を消して `extract_failed`(`summary_status=disabled`)にする(architecture K30)。最終成功時の本文は保持しない(MVP)。
- **要約**: 本文が変わらない文書の要約は更新しない。要約ロジックやモデルの変更などで再生成が必要な場合は、再書き込みモード(4.1。architecture K26)でクロールして本文ごと登録する。
- **`change` の区分と集計**(案・推奨。ユーザー承認待ち。architecture P38): 変更がなく書かなかった場合を `unchanged` とし、「更新」に混ぜない。Crawler は `created_count` / `updated_count` に加えて `unchanged_count` を集計する(Crawler 領域の集計項目。名称は案。5 章)。
- **再送時の集計と、その厳密でない点**(案。API-U-16): Crawler は `document_id` ごとに**最初に受け取れた結果**を保持して数え、再送の結果では数え直さない。ただし集計は厳密ではない。応答が失われて再送した場合、最初の登録(`created`)は Crawler に届かず、再送の結果(同じ内容なので `unchanged`)を最初に受け取れた結果として保持するため、`created` が `unchanged` と数えられうる。件数の厳密な保証は契約に含めない。
- 原本サイズ超過の応答は未決(4.9)。件数照合では `oversize_document_ids` として別に送る(4.4)。

**確認状況**: 同期 HTTP、文書単位の結果、冪等、失敗した文書だけ再送は確定(方式。数値・形式は未決)。書き込みを PUT 基本とすること(全文書き込みは PUT、`last_seen_at` だけの更新は Update)は architecture K19 で確定。新規・変更あり・変更なしの 3 分岐、変更なしの判定、読み直し、`op_type=create`、`if_seq_no`、max 比較は architecture K27 で確定(`retry_on_conflict` と読み直しの上限の値は architecture U-31)。抽出失敗時の旧 `content`・`text_hash`・要約の削除は architecture K30 で確定。エンドポイント、リクエスト/レスポンスの形、失敗種別名、`lock` の運び方は提案(API-U-7)。新規/更新/変更なしを含めることは案(推奨。ユーザー承認待ち。API-U-9)。`url` / `path` の 2 項目は案(推奨。ユーザー承認待ち。API-U-3)。受理条件の判定は architecture K23 で確定(エラー名は案。API-U-19)。再書き込みモードの採用は architecture K26 で確定(名称・指定経路・保持先は未決。API-U-22)。

### 4.4 終了通知

**概要**: 列挙の終了を伝える。Indexer は受理(202)したのち、削除の判断・実行を非同期に行う。判断の結果は応答に含めず、Crawler は Status API で確認する。

**エンドポイント**: `POST /crawls/{crawl_id}/finish`(案)

**呼び出し元**: Crawler。すべてのバッチ登録と `last_seen_at` 部分更新の応答を確認したあと。列挙の失敗・取り消しの場合は `outcome=failed` または `cancelled` を可能なら送る(届かなくても削除されないので安全)。取り消しが有効なのは、終了通知を送る前だけ。送ったあとに取り消しても削除処理は止まらない(ジョブは `cancelled` になり、結果は削除結果に残る)。

**リクエスト**:

| 名前 | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `crawl_id`(パス) | string | ○ | 開始通知と同じ ID |
| `source_id` | string | ○ | データソース ID |
| `outcome` | string | ○ | `enumeration_completed` / `failed` / `cancelled` |
| `enumerated_count` | integer | `enumeration_completed` のとき ○ | Crawler が `document_id` で重複を除いて数えた列挙件数。スキップ・抽出失敗の文書を含む |
| `skipped_document_ids` | string[] | 同上 | スキップした文書の ID。上限は `oversize_document_ids` との合計で未決(API-U-5) |
| `oversize_document_ids` | string[] | 同上 | 原本サイズ超過の文書の ID(スキップとは別項目。architecture P32) |
| `skipped_count` | integer | 同上 | `skipped_document_ids` の件数(`oversize_document_ids` は含まない) |
| `finished_at` | datetime | ○ | 終了時刻 |

失敗時(`failed` / `cancelled`)の `outcome` 以外の件数は、可能な範囲で送る。省略可否は未決(API-U-12)。

```json
{
  "source_id": "src-docs",
  "outcome": "enumeration_completed",
  "enumerated_count": 1203,
  "skipped_document_ids": [
    "7f2216b2a91e74fe53ce071ed0bd8dcebccaa904f9a8d8004f592b0a4210a9c5"
  ],
  "skipped_count": 1,
  "oversize_document_ids": [],
  "finished_at": "2026-11-09T01:12:30Z"
}
```

(`skipped_document_ids` の ID は 4.3 の応答例で `document_rejected` になった文書。)列挙の失敗の例:

```json
{ "source_id": "src-docs", "outcome": "failed", "finished_at": "2026-11-09T01:03:10Z" }
```

**レスポンス**: `202 Accepted`(ボディなし、または 4.1 と同形。案)。判断の結果は含めない。記録済みの再送で内容が異なるときは 409(下記)。

**エラー**:

| ステータス | コード(提案) | 条件 |
| --- | --- | --- |
| 400 | `invalid_request` | リクエストの形式不正 |
| 409(案) | `finish_content_mismatch`(案) | 記録済みの終了通知の再送で、内容(ダイジェスト)が最初に受理した内容と異なる。状態は変えない(architecture K25) |
| 5xx / 接続エラー / タイムアウト | `unavailable` など | Indexer の異常(リトライし、直らなければジョブ `failed`。届かなければ削除が行われないだけで安全) |

**冪等性・注意事項**:

- **再送の扱い**(architecture K25。確定。API-U-21): 受理時の分岐の先頭で判定する。ダイジェストが記録済みの再送は、世代を見ず再処理しない。内容が最初に受理した内容と同じなら 202、異なれば 409(`finish_content_mismatch`。名称は案)を返し、状態を変えない(後の内容は採用しない)。比較のため、最初の通知の**ダイジェスト**(`outcome`、`enumerated_count`、重複を除いてソートした `skipped_document_ids` と `oversize_document_ids` を正規化した SHA-256。`finished_at` は除く)を、`finish_received_at` と同じ書き込みで `deletion_result` に保存する(`failed`・`cancelled` でも保存する)。再送かどうかの判定は「ダイジェストが記録済みか」だけで行い、`finish_received_at` や終端状態の有無は使わない(`outcome=failed` / `cancelled` は `finish_received_at` を記録しないが、ダイジェストは記録するため)。ダイジェストが未記録の場合(下記 (1) の遅れた終了通知など)は比較せず 202 を返す。終了通知の受理の書き込みは、開始通知と同じソース単位の直列処理の中で、`if_seq_no` の条件付き更新で行う(architecture 9.5、9.9(4))。ダイジェストの対象に `source_id` は含まない(`crawl_id` が `source_id` 単位の結果を指すため。意図)。409 の本文に受理済みの状態を載せるかは未決(API-U-21。受理の有無は Status API で読める。4.5)。
- **Crawler の義務**(Crawler 設計への要件。K25 の検証が成り立つための前提): Crawler は最初の通知内容を `loreley-jobs` に保存して固定し、再送では常に同じ内容を送る。応答が失われたあとの同じ内容の再送には 202 が返る。ただし 202 は、再送が冪等に処理されたことを示すだけで、受理の確認ではない((1) の遅れた通知と (2) の未知の `crawl_id` にも 202 が返るため)。受理の有無と削除の進行は Status API(4.5 の「終了通知の受理の有無の読み方」)で確認する(`finish_received_at` の有無、または `status=failed` かつ `reason=outcome_*`。遅れた通知は終端状態のまま、未知の `crawl_id` は 404)。409 で得られるのは Crawler 側のバグの検出で、優先度は低い。409 の本文との関係は API-U-21 に未決として置く。
- **受理時の分岐**(世代の判定はこの受理時に 1 回だけ行う。(1)〜(4) のどの分岐でも、初回の通知への応答は 202):
  1. ダイジェストが未記録で、その `crawl_id` の削除結果がすでに終端状態(`superseded` など。終了通知が届かないまま新しい開始通知で `superseded` になった旧世代への遅れた終了通知など): 何もしない。状態を変えず、削除しない。
  2. 開始通知を受けていない未知の `crawl_id`: 削除に使わず破棄する(確定。architecture K7)。削除結果を作らずログに残すだけとする扱いは案(architecture P16。記録する場合は件数の上限を設ける選択肢がある)。
  3. `outcome` が `failed` または `cancelled`: 待たずに `failed`(理由 `outcome_failed` または `outcome_cancelled`)を記録して削除しない(`finish_received_at` は記録しない)。削除結果を `failed` にしてから 202 を返す。
  4. `enumeration_completed`: `finish_received_at` を `loreley-deletions` に永続化してから 202 を返す(202 のあとに再起動しても、受理した事実が残り、再起動時に `failed`(`indexer_restart`)にできる)。ソースごとの待ち行列に入れ、先行する削除結果が終端状態になってから判定に進む。判定の順(順 1〜6)と実行は `indexer-architecture-v0.7.md` を参照。割合ルール内の判定 1〜3 は `loreley-deletions-v0.7.md` と `indexer-architecture-v0.7.md` を参照。
- **応答が失われた場合**(確定。architecture K12): 終了通知が Indexer に受理される前にクロールが失敗した場合は、削除しない。受理された後は、応答が失われただけなら Indexer は受理済みで削除が進みうる(Crawler からは届かなかった場合と区別できない)。Crawler が再送もすべて失敗してジョブ `failed` にしても削除が進みうるが、各文書の削除直前の TTL 再確認で、更新された文書は消えない。結果は削除結果に残る。「安全」の根拠は、前提(列挙の完了、全バッチの登録の確認)が送信前に確認済みであることと、実行時の各文書の削除直前の TTL 再確認。

**件数照合**(終了通知の値の定義): Indexer は次が成立するときだけ削除の判断に進む。不一致なら削除せず `validation_failed` として記録する(許容差なし。案)。

```text
enumerated_count == N_seen + E_missing
  N_seen    = 当該 source_id で last_seen_at >= crawl_started_at の件数(リフレッシュ後の検索インデックス)
  E_missing = skipped_document_ids と oversize_document_ids の和集合のうち、検索インデックスにないものの件数(重複は 1 件。architecture P32)
```

- `skipped_document_ids` と `oversize_document_ids` の合計が上限を超えるときも、削除せず `validation_failed`(案)。上限の値と送り方(エンコード、分割)は未決(API-U-5)。
- 抽出に失敗した文書(`extract_failed`。タイトルとメタデータを登録)は検索インデックスにあるので `N_seen` に数えられる。
- 旧い削除の待機中に新しいクロールが `last_seen_at` を更新して不一致になる場合は、削除しない側に倒れるだけなので許容(案)。
- 同じ ID が `skipped_document_ids` と `oversize_document_ids` の両方にあっても、`E_missing` の上では和集合で 1 件と数える(`skipped_count` は `skipped_document_ids` の件数のまま)。
- 新規の原本サイズ超過文書は `oversize_document_ids` で数える(architecture P32)。拒否主体などの残りは未決(4.9、API-U-8)。

**確認状況**: 終了通知の存在、202、世代 `crawl_id`、未知の `crawl_id` の破棄、件数照合は確定。応答喪失時の削除の継続(受理前は削除しない、受理後は継続しうる)は確定(architecture K12)。再送で内容が異なる場合の 409(案 B)は architecture K25 で確定。エンドポイント形、409 のコード名(`finish_content_mismatch`)、`oversize_document_ids`、未知の `crawl_id` を記録しない扱いは案。未決: API-U-12(`failed` 時の項目省略)、API-U-5(ID リストの上限)、API-U-21(409 の本文)。

### 4.5 Status API

**概要**: 削除結果を読み取りで返す。

**エンドポイント**: `GET /crawls/{crawl_id}`(案)

**呼び出し元**: Crawler(終了通知の 202 のあと、終端状態になるまでポーリング。第 5 章)

**リクエスト**:

| 名前 | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `crawl_id`(パス) | string | ○ | 確認する `crawl_id` |

**レスポンス**(正式なスキーマとキー名は未決。API-U-1):

| 名前 | 型 | 説明 |
| --- | --- | --- |
| `crawl_id` / `source_id` | string | 対象 |
| `status` | string | 下記の値 |
| `reason` | string | `failed`(理由コード)、`discarded`(理由)のとき |
| `forced` | boolean | `force_delete` の複写 |
| `target_count`(T) / `denominator`(D) | integer | 削除対象件数 / 割合の分母 |
| `ttl` / `ratio_threshold` / `min_delete_count` | 未定 | しきい値(複写。値は未決) |
| `deleted_count` | integer | 削除した件数 |
| `enumerated_count` / `n_seen` / `e_missing` | integer | 件数照合の値 |
| `finish_received_at` / `deletion_started_at` / `finished_at` | datetime | 時刻 |
| `waiting_for` | string | 待機中のみ・任意。先行する削除結果の `crawl_id`(案。要否は未決) |

- **`status` の値**(状態名の一覧は案。architecture P25): `running`(終了通知待ち・待機中・判定中・削除中を含む) / `deleted` / `skipped_by_ratio` / `validation_failed` / `discarded` / `failed`。`running` 以外が終端状態。待機中も `running` のままで、状態は増やさない。
- **`failed` の理由コード**(案。名称は実装時に調整): `outcome_failed` / `outcome_cancelled` / `maintenance` / `indexer_restart` / `delete_error`。
- **`discarded` の理由**: `superseded`(終了通知が届かなかった旧世代の整理)、`source_deleted`(ソース削除による破棄)。
- 各状態の意味と記録項目は `loreley-deletions-v0.7.md` を参照。

**終了通知の受理の有無の読み方**(4.4。応答の項目は増やさず、既存の項目だけで読む):

| 終了通知の扱い | Status API の応答 |
| --- | --- |
| `enumeration_completed` を受理する前 | `status=running` かつ `finish_received_at` なし |
| `enumeration_completed` を受理した後(待機中・判定中・削除中を含む) | `finish_received_at` あり(`running` のままのことも、終端状態のこともある) |
| `failed` / `cancelled` を受理した結果 | `finish_received_at` は未記録のまま `status=failed`、`reason=outcome_failed` または `outcome_cancelled` |
| 遅れた通知(4.4 の分岐 1。旧世代で、すでに終端状態) | その `crawl_id` が終端状態のまま(`superseded` など)。受理されていない |
| 未知の `crawl_id`(4.4 の分岐 2) | 404。受理されていない |

受理の根拠は、`finish_received_at` があること、または `status=failed` かつ `reason` が `outcome_*` であることのどちらか。`failed` / `cancelled` の受理は `finish_received_at` を持たないため、`finish_received_at` の有無だけで受理を判断してはならない。応答に `outcome` を持たせる仕様は、ここでは追加しない。

応答例(待機中。待機中は定義上、終了通知を受理済み。`waiting_for` は任意項目):

```json
{
  "crawl_id": "job-20261109-0002",
  "source_id": "src-docs",
  "status": "running",
  "finish_received_at": "2026-11-09T01:20:05Z",
  "waiting_for": "job-20261108-0007"
}
```

応答例(削除完了):

```json
{
  "crawl_id": "job-20261109-0001",
  "source_id": "src-docs",
  "status": "deleted",
  "forced": false,
  "enumerated_count": 1203,
  "n_seen": 1202,
  "e_missing": 1,
  "target_count": 12,
  "denominator": 1215,
  "ttl": "<値は未決>",
  "ratio_threshold": "<値は未決>",
  "min_delete_count": "<値は未決>",
  "deleted_count": 12,
  "finish_received_at": "2026-11-09T01:12:31Z",
  "deletion_started_at": "2026-11-09T01:12:40Z",
  "finished_at": "2026-11-09T01:12:55Z"
}
```

応答例(失敗):

```json
{ "crawl_id": "job-20261109-0003", "source_id": "src-docs", "status": "failed", "reason": "indexer_restart" }
```

**エラー**:

| ステータス | コード(提案) | 条件 |
| --- | --- | --- |
| 404(案) | `crawl_not_found` | 保持件数を超えて消えた `crawl_id`、開始通知を受けていない `crawl_id`、`loreley-deletions` を失った場合 |
| 5xx / 接続エラー / タイムアウト | `unavailable` など | Indexer の異常 |

保持件数 N の値と、404 の条件の確定は未決(API-U-10)。

**冪等性・注意事項**: 読み取りのみ。**返すのは削除結果のみ**で、登録結果と確認結果の区分は含まない(確定)。

**確認状況**: Status API の存在、削除結果のみを返すことは確定。エンドポイント形、状態名の一覧、理由コード名、404 条件、`waiting_for`、キー名は案。未決: API-U-1、API-U-10。

### 4.6 ソース削除 1: 削除結果の破棄(提案)

**概要**: ソース削除は Crawler のジョブで、期限削除の判断(割合ルール)は通らない。全体の順序は次のとおり。そのソースの終端状態でない削除結果を `discarded`(理由 `source_deleted`)にする(本 API)→ 検索インデックスから `source_id` の文書をすべて削除(4.7)→ スキップ記録(Crawler が削除。案)と、削除の記録(`deletion-{source_id}` と `deletion_result-*`)を削除(4.8 など)→ データソース設定を削除 → **ロック文書の削除は最後**。ジョブは `source_id` 単位のロックを最後まで保持する(architecture K29。確定。Crawler 設計への要件。API-U-14)。この要請は Deletion Manager のソース単位の直列実行で最優先とする。Indexer に要請するのは 4.6〜4.8 の 3 つ(提案)。いずれも再送しても結果は変わらず、何度でも再実行できる。ロックの具体(Crawler 側の設計)によらず、Indexer 側の動作は次のとおり成立する(4.7・4.8 の注意事項)。

**エンドポイント**: `POST /sources/{source_id}/deletions:discard`(案)

**呼び出し元**: Crawler(ソース削除ジョブ)

**リクエスト**:

| 名前 | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `source_id`(パス) | string | ○ | データソース ID |
| `lock` | object(`owner`, `job_id`) | 例では添付(ロック所有情報の運び方は 3.2) | ロック所有情報 |
| `reason` | string | 例では添付 | `source_deleted` |

```json
{ "lock": { "owner": "crawler-1", "job_id": "job-20261109-0010" }, "reason": "source_deleted" }
```

**レスポンス**:

| 名前 | 型 | 説明 |
| --- | --- | --- |
| `discarded_crawl_ids` | string[] | `discarded` にした `crawl_id` |

```json
{ "discarded_crawl_ids": ["job-20261109-0009"] }
```

**エラー**: 400 `invalid_request`、5xx `unavailable`(3.4)。個別のコードは未定義。

**冪等性・注意事項**:

- **最優先で処理し、応答の時点で削除バッチは動いていない**(案。architecture P29)。この要請は Deletion Manager のソース単位の直列実行で最優先とし、実行中の削除バッチの完了直後、次のバッチの前確認や待機中の判定より前に `discarded` を書く。そのソースの終端でない削除結果(待機中を含む)をすべて `discarded` にしてから応答する。応答の時点で、そのソースの削除バッチは実行されていない。応答までバッチ 1 回分の時間がかかりうるため、Crawler のタイムアウトはこれを見込む(値は API-U-6)。バッチ内でハングした場合は待ち続ける(受容事項。architecture P29)。
- **ロックのリースとの関係は未決**(Crawler 領域。API-U-14): ジョブがロックを保持したまま、バッチ内のハングなどで応答を待ち続けると、ロックのリースが切れうる。その場合の、後続の 4.7・4.8 の所有確認(`lock_not_owned`)との関係は決めていない。
- 書き込みは `if_seq_no` の条件付き更新で、すでに終端状態の結果は上書きしない。衝突したら読み直して再試行し、終端状態になるか `discarded` にできるまで繰り返す(案。回数・間隔は未決)。実行中の削除側の停止確認は `indexer-architecture-v0.7.md` を参照。
- **ソース削除ジョブの Crawler 向け要件**(architecture K29。確定。9.14。API-U-14): Crawler 領域の設計に対する要件(1)〜(4)で、Crawler の設計は本書では決めない。(1) 削除中(4.6 から最後のロック文書の削除まで)は、ジョブがロックのリースを更新し続ける。(2) リースの更新に失敗するなどで所有権を失ったら、後続の削除操作(4.7、4.8、データソース設定とロック文書の削除)を停止する。(3) 停止したジョブは再実行で復旧する(4.7・4.8 は冪等)。(4) 削除中のデータソースに、新しいクロールを起動しない。(1)〜(3) は、応答待ちが長引いてリースが切れたあとに別のジョブがロックを取り、削除と新しい登録が重なることを防ぐための要件。(4) も同じ理由。「削除中」の状態をどの記録に持つかは未決(Crawler 領域)。

**確認状況**: 提案(案)。ジョブがロックを最後まで保持すること(ロック文書の削除は最後)と、Crawler 向け要件(1)〜(4)は architecture K29 で確定。ソース削除での分担(Crawler が起動・管理、Indexer が実処理)、応答を実行中バッチの終了後にすることは案。未決: API-U-7、API-U-14(Crawler 側の具体)。

### 4.7 ソース削除 2: 文書の全削除(提案)

**概要**: 検索インデックスから、その `source_id` の文書をすべて削除する。最終的にそのソースの文書を残さないことが目的で、`delete_by_query`(`conflicts=proceed`)を、**再実行して消し切る**(architecture K20、K28。確定)。検索インデックスが唯一の正本なので、これ以外に消す場所はない(下記の前提のもとで、完了後は `_count`=0)。

**エンドポイント**: `DELETE /sources/{source_id}/documents`(案)

**呼び出し元**: Crawler(ソース削除ジョブ。4.6 のあと)

**リクエスト**: パス `source_id`(string・必須)。ロック所有情報 `lock` は、ジョブがロックを最後まで保持する(architecture K29)ので添える(3.2)。

**レスポンス**:

| 名前 | 型 | 説明 |
| --- | --- | --- |
| `deleted_count` | integer | 完了時点の削除件数。すでに削除済みの文書は数えない(推測。architecture U-31 で実機確認)。再送では 0 でも成功 |

```json
{ "deleted_count": 1215 }
```

**エラー**: 400 `invalid_request`、5xx `unavailable`(3.4)。個別のコードは未定義。再実行の上限を超えても文書が残る場合は 5xx `unavailable`(案。Crawler はジョブ `failed` とし、再実行で続きから消せる)。

**冪等性・注意事項**:

- **何度でも再実行できる**(冪等)。すでに削除済みの文書に対しては 0 件でも成功を返す。
- **消し方**(architecture K20、K28。確定。上限の値と `delete_by_query` の動作は実機で確認する。architecture U-31(5)):
  1. 実行前に検索インデックスを refresh する。直前の書き込みが未 refresh だと、`delete_by_query` にヒットしないため。
  2. `delete_by_query`(`source_id` で絞る。`conflicts=proceed`)を実行する。クロールなどが先に更新した文書とは競合して、その実行では消えないことがある。
  3. 完了後に refresh し、`source_id` の `_count` が 0 であることを確認する。
  4. 0 でなければ手順 2 に戻って再実行する(上限を設ける。値は未決。architecture U-31(5))。上限を超えても 0 にならなければ、上記のエラーで止まる。
- **前提**: ソース削除中は、そのソースに新しいクロールを起動しない。ジョブがロックを最後まで保持するから(architecture K29。4.6 の Crawler 向け要件(4))。この前提があるので、競合した文書も再実行で消える。前提が守られず削除中に新しい登録が入ると、文書が残りうる(Crawler 側で防ぐ事項)。
- **リース切れ**: ロック所有情報を添えて所有確認し、リースが切れて `lock_not_owned` になった場合は、書き込まずにジョブ `failed` で止まる(案。3.2)。再度ジョブを実行すれば、残りの文書の削除と後続の手順が完了する。
- **Indexer 側はロックの具体に依存しない**: 本 API は冪等で再実行できる。ただし文書が残らないことの保証は、上記の前提(削除中に新しいクロールが登録しない。Crawler 側の要件)に依る。
- 所要時間が長い場合の非同期化(202 とポーリング)は提案に含めない。要否は未決(API-U-12)。

**確認状況**: 再実行で消す方針(`delete_by_query` を、実行前の refresh と完了後の `_count`=0 の確認つきで再実行する)は architecture K20、`delete_by_query` の採用と再実行の上限を設けることは K28 で確定。再実行の上限の値と、エラー応答、エンドポイント形は案・未決。未決: API-U-7、API-U-12。

### 4.8 ソース削除 3: 削除記録の削除(提案)

**概要**: `loreley-deletions` の当該ソースの記録(`deletion-{source_id}` と `deletion_result-*`)を削除する。

**エンドポイント**: `DELETE /sources/{source_id}/deletion-records`(案)

**呼び出し元**: Crawler(ソース削除ジョブ。4.7 のあと)

**リクエスト**: パス `source_id`(string・必須)。ロック所有情報 `lock` は 4.7 と同じく添える(3.2)。

**レスポンス**:

| 名前 | 型 | 説明 |
| --- | --- | --- |
| `deleted` | boolean | 削除した場合 `true`。すでに記録がなければ `false`(成功。案) |

```json
{ "deleted": true }
```

**エラー**: 400 `invalid_request`、5xx `unavailable`(3.4)。個別のコードは未定義。

**冪等性・注意事項**:

- 再送しても結果は変わらない。何度でも再実行できる(削除済みなら `deleted` は `false` でも成功。案)。
- **リース切れ**: ロック所有情報を添えて所有確認し、リースが切れて `lock_not_owned` になった場合は、書き込まずにジョブ `failed` で止まる(案)。再度ジョブを実行すれば、4.7 は 0 件で成功し、本 API で記録が削除されて完了する。
- **Indexer 側はロックの具体に依存しない**: 本 API は冪等で再実行できるため、結果は正しい。
- **ソース削除ジョブのロック**(architecture K29。確定): ジョブは `source_id` 単位のロックを最後まで保持(リースを更新し続ける)し、ロック文書の削除は手順の最後(本 API のあと)にする。Crawler 向けの要件の全体は 4.6。このため本 API の時点でもロック文書は存在し、4.7・4.8 の要請にロック所有情報を添えて所有確認できる。Crawler 側のロック設計の具体は、Crawler 設計で決める(API-U-14。architecture 9.14、U-4)。

**確認状況**: 提案(案)。ジョブがロックを最後まで保持することは architecture K29 で確定。未決: API-U-7、API-U-14(Crawler 側の具体)。

### 4.9 補足: 原本サイズ超過(API ではない)

バッチ登録(4.3)に関わる未決事項をまとめる。

- 確定の範囲: 上限を超えた原本は取り込まず、原本サイズ超過として文書単位のエラーに記録する。スキップではなく、リトライもしない。`last_seen_at` は列挙時に更新済みで、削除対象にならない。
- 未決: 上限の値と形式。誰が拒否するか(Crawler の送信前か Indexer の拒否か。API-U-4。architecture U-5)。エラーの記録先・項目。ジョブ status への影響。既存の索引データを残すか(API-U-8)。
- 新規文書が索引にないときの件数照合は、終了通知の `oversize_document_ids` を `skipped_document_ids` と別項目にして E_missing の対象に含める(案。4.4、architecture P32)。含めないと `enumerated_count` と `N_seen + E_missing` が合わない。
- このため 4.3 の応答例に原本サイズ超過の形は含めない。

## 5. Crawler 側のポーリング規約(Indexer が前提とする部分)

この章は Indexer が前提とする範囲にとどめる。正本は Crawler 設計であり、ここでは決めない。

- Crawler は終了通知の 202 を確認したあと、Status API をポーリングして削除結果が終端状態になるのを待つ。間隔・上限時間・リトライ回数は未決(API-U-5)。
- ポーリングの失敗(リクエストのタイムアウト、接続エラー・5xx、404)が連続でリトライ回数まで続いた場合、またはポーリング全体の上限時間を超えた場合は、警告と確認結果の区分をジョブ記録に残すだけで、ジョブの status は変えない(確定)。区分の名称・対応は案(404 のみが続けば `unknown`、それ以外は `unconfirmed`)。Crawler は区分を残したあと再確認しない(確定)。
- ロックは削除結果が終端状態になるまで保持する。ポーリングの失敗・上限時間の超過のあとは解放する(案)。待機中のまま上限を超えた場合も同じで、削除結果は `running` のまま待機を続ける。
- 登録結果(`enumerated_count` / `created_count` / `updated_count` / `unchanged_count`(案・推奨。architecture P38)/ `skipped_count` / `oversize_count` / `error_count` / `partial`。名称は案)は、Crawler がバッチ応答を集計して `loreley-jobs` に持つ。Indexer が返すのは文書単位の応答(4.3)だけ。`unchanged_count` は 4.3 の `change: unchanged` の集計で、4.2 の `result: unchanged` とは別。応答が失われた場合の集計は厳密でなく、再送時は Crawler が `document_id` ごとに最初に受け取れた結果を保持する(4.3)。

## 6. 確認状況

### 区分ごとの整理

| 論点 | 区分 |
| --- | --- |
| Crawler と Indexer は別コンテナ、HTTP 直接通信 | 確定 |
| 開始通知、終了通知(202)、Status API の存在。ポーリングの失敗・上限時間超過は警告のみ。ジョブ status と削除結果は切り離す | 確定(契約の形は案) |
| 世代 `crawl_id`、未知の `crawl_id` の終了通知を削除に使わず破棄すること、件数照合(`enumerated_count == N_seen + E_missing`) | 確定 |
| 削除の判断・実行は Indexer(Deletion Manager)。`loreley-deletions` に書くのは Indexer だけ。`loreley-jobs` に書くのは Crawler だけ | 確定(インデックス名は仮名) |
| Status API は削除結果のみ。登録結果は `loreley-jobs`(Crawler が集計、Admin API が読む) | 確定 |
| 終了通知が Indexer に受理される前にクロールが失敗した場合は削除しない。受理後は、応答喪失などで Crawler 側のジョブが失敗扱いになっても削除処理が継続しうる(architecture K12。2026-11-10 確定) | 確定(ユーザー確認済み) |
| 検索インデックスを、本文・メタデータ・要約・処理状態・`last_seen_at` の唯一の正本にする(architecture K18。2026-11-10 確定。API-U-11 は欠番(再利用しない)) | 確定 |
| 書き込みは PUT(Index API)を基本とし、`last_seen_at` だけの更新は Update API。書き込み種別は全文書き込み(PUT)と `last_seen_at` の部分更新(Update)(architecture K19。2026-11-10 確定) | 確定 |
| ソース削除の文書の削除は、`delete_by_query` を、実行前の refresh と完了後の `_count`=0 の確認つきで、0 になるまで再実行して消す。`delete_by_query` を採用し、再実行の上限を設ける(値は未決。architecture U-31(5))(architecture K20、K28。2026-11-10 確定。ロック保持=削除中は新しいクロールを起動しないことが前提) | 確定 |
| スナップショットによる復元は運用者の責務で、設計書は手順を定めない。Store 層と検索インデックスは同じ OpenSearch にあるため、1 つのスナップショットで取得時点の状態に復元できる。整合した復元(ジョブ・削除結果・文書の時点が揃うこと)を求める場合は、クロール・削除・要約の書き戻しなどの書き込みを止めてから取得する。停止せずに取得したスナップショットは、アプリケーション全体の整合を保証しない(architecture K21。search-index 6章) | 確定 |
| 抽出後の本文の SHA-256(`text_hash`)を検索インデックスの文書に持ち、変更の有無の判定と要約の書き戻しの条件に使う。API 契約には現れない(architecture K22。2026-11-10 確定) | 確定 |
| バッチ登録・`last_seen_at` 部分更新の受理条件(`deletion_result` が存在、`source_id` 一致、`crawl_started_at` 一致、`status` が `running`、`finish_received_at` がない、ロック所有確認に成功)。終端状態・受理後・存在しない結果への登録は拒否する。`crawl_id`・`crawl_started_at` を必須とし、ソース削除の要請は対象外(3.2、4.2、4.3。architecture K23。2026-11-10 確定)。拒否のエラー名・HTTP は案(API-U-19) | 確定 |
| 開始通知の再送の一致検証(複写済みの項目と直接比較。一致なら成功、不一致なら 409。状態不変)(4.1。architecture K24。2026-11-10 確定)。コード名 `crawl_start_conflict` は案 | 確定 |
| 終了通知の再送で、内容が最初に受理した内容と異なる場合は 409(案 B。再送の判定はダイジェストの記録の有無)。同じ内容は 202(4.4。architecture K25。2026-11-10 確定)。コード名 `finish_content_mismatch` は案 | 確定 |
| 再書き込みモードの採用(本文が変わらない文書の要約を再生成するため、変更なしの判定をせず本文ごと全文書き込みする)(4.1、4.3。architecture K26。2026-11-10 確定)。名称・指定経路・保持先は未決(API-U-22) | 確定 |
| 書き込みの細部: GET → `if_seq_no`/`if_primary_term` 付きの PUT(新規は `op_type=create`)、新規・変更あり・変更なしの 3 分岐、`last_seen_at` の Update の max 比較、409 は読み直して再判定(4.2、4.3。architecture K27。2026-11-10 確定)。`retry_on_conflict` と読み直しの上限の値は未決(architecture U-31) | 確定 |
| ジョブはソース削除の間 `source_id` 単位のロックを最後まで保持し、ロック文書の削除は最後に行う。Crawler 向け要件(1)〜(4)を含む(4.6〜4.8。architecture K29。2026-11-10 確定) | 確定 |
| `indexed` の文書が抽出失敗になったときは、旧 `content`・`text_hash`・要約を消して `extract_failed`(`summary_status=disabled`)にする(4.3。architecture K30。2026-11-10 確定) | 確定 |
| 原本サイズ超過の決定済み範囲(取り込まず文書単位のエラー、スキップ・リトライではない) | 確定 |
| `last_seen_at` を検索インデックスの文書に持つ。`crawl_started_at` を渡して Indexer が書く | 確定 |
| エンドポイント形(`POST /crawls/start` 等)、応答コード、開始通知の 409、設定スナップショットの複写、`waiting_for`、削除結果の状態名の一覧(architecture P25)、`failed` の理由コード名、Status API の 404 条件、未知の `crawl_id` について削除結果を作らず記録しない扱い(記録する場合は件数の上限を設ける選択肢。architecture P16)、`oversize_document_ids` を別項目にすること(architecture P32)、キー名 | 案 |
| 書き込みの競合の上限超過の失敗種別名(`write_conflict`、`update_conflict`。名称は仮。architecture K27 の細部)、日時の UTC・ISO 8601・ミリ秒への正規化(3.6)、`last_seen_at` を保存できなければクロールを完了扱いにしない、リトライ既定値・連続 20 件、ロック所有確認の方式(Indexer が文書ごとに確認、要請を直列処理。部分結果の返し方は未決) | 案 |
| ソース削除での分担(Crawler が起動・管理、Indexer が実処理)、ソース削除の文書の削除の細部(`conflicts=proceed`、再実行の上限超過時のエラー応答。architecture K28 の細部)、discard 要請の応答を実行中バッチの終了後にすること(architecture P29) | 案 |
| 案(推奨。ユーザー承認待ち。推奨(承認待ち)で、確定ではない): (a) 拒否の種類ごとのエラー名(3.2、3.4。API-U-19)。(b) `change` の `unchanged` の追加と `unchanged_count`(4.3、5 章。architecture P38。API-U-9、API-U-16)。(c) `url` / `path` の 2 項目(4.3。architecture U-16。API-U-3) | 案(推奨。ユーザー承認待ち) |
| 4.2、4.3、4.6〜4.8 の提案(エンドポイント、リクエスト/レスポンス例、エラー応答の形、失敗種別名、`lock` の運び方)。4.7・4.8 は何度でも再実行でき、リース切れの `lock_not_owned` でジョブが `failed` で止まっても再実行で完了し、ロックの扱いによらず Indexer 側は正しいこと | 案(本書の提案) |
| 数値の既定値・上限(ポーリング間隔・上限時間・リトライ回数、保持件数 N、`skipped_document_ids` と `oversize_document_ids` の合計の上限、バッチの件数・合計サイズ、タイムアウト、並列度、原本の上限、書き込み競合の読み直し上限、`retry_on_conflict` の値) | 未決 |
| 下表の `API-U-*` の各項目(設定スナップショットと複写の項目名、`fetched_at`・`metadata` の保存先、`url` / `path` の 2 項目の採否と `path` の検索・絞り込み要否・最大長、原本サイズ超過の拒否主体と具体、ロック所有確認の部分結果の返し方、ソース削除ジョブの Crawler 側のロック設計の具体(API-U-14)、`content_hash` の照合、再送時の集計規則、終了通知の 409 の本文(API-U-21)、開始通知の再送の比較前の正規化(API-U-20)、再書き込みモードの名称・指定経路・保持先(API-U-22)、`raw_content` の運び方と実測など) | 未決(ユーザー判断) |

### 未決(ユーザー判断)の一覧

欠番(再利用しない): API-U-11(検索インデックスを唯一の正本にする決定。architecture K18 で確定したため)。確定した項目は欠番にせず、「確定(Kxx)」として表に残す(API-U-14、API-U-18、API-U-20、API-U-21、API-U-22 の確定部分)。

| ID | 内容 | 選択肢(あれば) |
| --- | --- | --- |
| API-U-1 | 設定スナップショットの項目名(開始通知、`deletion_result` の複写、Status API のしきい値)の統一(architecture U-14) | 開始通知の名称(`ttl` / `ratio_threshold` / `min_delete_count` / `force_delete`)に揃える。複写先では `force_delete` を `forced` として持つ |
| API-U-2 | `fetched_at`・`metadata` の保存先(architecture U-16) | 保存する(Schema に追加)/ 受け取るだけで保存しない(API 文書に明記) |
| API-U-3 | `url` / `path` の項目数(architecture U-16)。2 項目(`url` = アクセス可能な原文の URL、`path` = データソース内の文書パス。独立した任意項目。`external_id` は ID の責務で別)を案(推奨。ユーザー承認待ち)とする。`path` を検索・絞り込みに使うかと最大長は未決(`search-index-v0.7.md`) | 2 項目(案・推奨)/ どちらか一方が入る 1 項目 |
| API-U-4 | 原本サイズ超過の拒否主体(architecture U-5) | Crawler が送信前に弾く / Indexer が拒否する |
| API-U-5 | ポーリング間隔・上限時間・リトライ回数、保持件数 N、`skipped_document_ids` と `oversize_document_ids` の合計の上限と送り方、削除バッチ件数、しきい値・最小件数の既定値(architecture U-1、U-2) | なし |
| API-U-6 | バッチの件数・合計サイズ、タイムアウト、並列度(architecture U-3) | なし |
| API-U-7 | 内部 API の契約本体(4.2、4.3、4.6〜4.8 の提案の採否)、失敗種別・エラーコードの具体名(`write_conflict`、`update_conflict` の名称と、リトライしても直らない場合の Crawler の扱い(スキップするか、ジョブ `failed` にするか。連続 20 件の計数に含めるか)を含む)、ロック所有情報の形、`last_seen_at` 部分更新の要請の単位(`document_id` の算出主体を含む。4.2)、ソース削除の呼び出し形(architecture U-4)。`document_id` の算出と `external_id` の正規化(3.3)は Crawler(4.2)と Indexer(4.3)で二重に実装することになるため、対策として共有ライブラリ、またはテストベクタ(入力と期待 ID の組)の共有を選択肢とする(構成は変えない) | 提案を採用 / 修正。二重実装の対策は共有ライブラリ / テストベクタ / 対策しない |
| API-U-8 | 原本サイズ超過の具体(上限、記録先・項目、ジョブ status への影響、既存の索引データを残すか。件数照合は `oversize_document_ids` を別項目にする案。4.4)(architecture U-5) | なし |
| API-U-9 | バッチ登録応答の `change` の区分(architecture P38)。案(推奨。ユーザー承認待ち)は `created`(新規)/ `updated`(変更があり全文書き込みをした。メタデータのみの更新を含む)/ `unchanged`(変更がなく書かなかった)。再送の数え直しは API-U-16 | `unchanged` を加える(案・推奨)/ 変更なしを更新に数える / 数えない |
| API-U-10 | Status API の 404 条件の確定(architecture 9.5。P1) | 4.5 の案を確定 / 修正 |
| API-U-12 | 開始通知の 409 条件、`failed` 時の終了通知の項目省略可否、ソース削除の順 2(4.7)の非同期化(終了通知の再送の扱いは確定。architecture K25。API-U-21) | 案の確定 / 修正 |
| API-U-13 | ロック所有確認を文書ごとに行う(案)場合の、バッチ途中でロックを失ったときの部分結果の返し方(確認済みの文書の結果、未処理の文書の扱い、バッチの先頭での失敗を全体のエラーにするか)。`lock_not_owned` を文書単位の結果に加える提案(3.4)の採否(architecture U-4) | 文書単位の結果に加える / リクエスト全体の 409 にする / 併用 |
| API-U-14 | **確定(architecture K29。2026-11-10)**: ジョブが `source_id` 単位のロックを最後まで保持し、ロック文書の削除を最後にする。4.7・4.8 の要請にロック所有情報を添える。Crawler 向け要件(4.6): (1) 削除中はリースを更新し続ける、(2) 所有権を失ったら後続の削除操作を停止する、(3) 再実行で復旧する、(4) 削除中のデータソースに新しいクロールを起動しない。**未決(Crawler 領域)**: 「削除中」状態の置き場所、Crawler 側のロック設計の具体、discard の応答待ちの間にリースが切れた場合の扱い(4.6)(architecture U-4、9.14)。4.7・4.8 は何度でも再実行でき、リース切れの `lock_not_owned` はジョブ `failed` で止まり再実行で完了する | 確定(K29)。未決部分は Crawler 設計で決める |
| API-U-15 | バッチ登録で Indexer が `raw_content` の SHA-256 を計算して `content_hash` と照合するか(4.3。architecture U-26) | 照合して不一致は文書単位の失敗にする / 照合せず Crawler の値を信用する |
| API-U-16 | 再送時の `created` / `updated` / `unchanged` の集計(API-U-9 関連)。推奨(ユーザー承認待ち)は、Crawler が `document_id` ごとに最初に受け取れた結果を保持し、再送の結果では数え直さない規則。応答が失われた場合の集計は厳密でない(`created` が `unchanged` と数えられうる)。`unchanged_count` は Crawler 領域の集計項目(名称は案)。メタデータのみの更新は `updated`(案・推奨。API-U-9) | 推奨を採用 / 修正 |
| API-U-17 | `raw_content` の運び方と上限。base64 は約 33% 増えるため、原本の上限・バッチの件数と合計サイズ・メモリ使用量を実測して決める(architecture 15.4) | JSON + base64 / multipart / 文書ごとの個別送信 |
| API-U-18 | **確定(architecture K23。2026-11-10)**: 登録の受理条件の採否(旧 architecture U-28。K23 で確定)。バッチ登録・`last_seen_at` 部分更新を、`deletion_result` の存在・`source_id` 一致・`crawl_started_at` の照合・`running`・終了通知の受理前・ロック所有、のすべてを満たすときだけ受理する(3.2、4.2、4.3)。終端状態への登録の拒否、存在しない `deletion_result` の扱い、ソース削除の要請を対象外とすることを含む。拒否のコード名は API-U-19 | 確定(K23。受理条件を課し、終端状態・受理済み・存在しない結果は拒否) |
| API-U-19 | 登録の拒否のエラーコード名・HTTP(案: すべて 409)。`crawl_not_started`(`deletion_result` が存在しない。未送信、保持期間超過、`loreley-deletions` の喪失)、`crawl_source_mismatch`(`source_id` 不一致)、`crawl_started_at_mismatch`、`crawl_already_closed`(終端状態)、`crawl_finished`(`running` だが終了通知の受理後)。開始通知の再送の不一致は `crawl_start_conflict`(API-U-20)。いずれも Crawler はリトライせずジョブ `failed`。architecture K23(architecture は「案: 409(API-U-19)」と併記)。受理条件そのものは architecture K23 で確定 | 案を採用 / 修正(コード名、HTTP、ジョブ `failed` 以外の扱い) |
| API-U-20 | 開始通知の再送の一致検証(4.1)。**確定(architecture K24。2026-11-10)**: 同じ `crawl_id` で `running` のとき、複写済みの項目(`source_id`、`crawl_started_at`、`ttl`、`ratio_threshold`、`min_delete_count`、`force_delete`)と直接比較し、一致なら成功(状態不変)、不一致なら 409(状態不変)。**未決**: コード名 `crawl_start_conflict`、`ttl` などの値の型が未決のため比較前の正規化 | 確定(K24)。未決部分はコード名・正規化 |
| API-U-21 | 終了通知の再送(4.4。旧 architecture U-29。K25 で確定)。**確定(architecture K25。2026-11-10)**: 案 B。記録済みの再送で内容が最初に受理した内容と異なれば 409、同じなら 202。ダイジェスト(`outcome`、`enumerated_count`、重複除去・ソート済みの `skipped_document_ids` / `oversize_document_ids` の正規化 SHA-256。`finished_at` は除く)を `deletion_result` に保存し、Crawler は最初の通知内容を `loreley-jobs` に保存して固定する。受理の有無は、Status API の現状の項目で読める(4.5。`finish_received_at` の有無、または `status=failed` かつ `reason=outcome_*`)ため、202 の本文で区別して返す仕様は追加しない。**未決**: コード名 `finish_content_mismatch`、409 の本文に受理済みの状態を載せるか(読み方だけでは、409 を受けた Crawler が Status API を引かずに、最初に受理した内容を知ることはできない。本文に載せる場合の項目は未定) | 確定(K25)。未決部分は 409 のコード名・本文 |
| API-U-22 | 再書き込みモード(**採用は確定。architecture K26。2026-11-10**)の名称・指定経路・保持先(未決)。architecture は、手動実行のクロールの起動時に指定し、開始通知で Indexer へ渡す形を想定する(経路は推測)。本書は開始通知の任意項目 `rewrite_mode`(名称は仮)として記載した。Indexer がこのクロールの文脈としてどこに保持するか(`deletion_result` への複写か)、再送の一致検証(API-U-20)の比較項目に含めるかは未決 | 開始通知の任意項目(本書の記載)/ バッチ登録のリクエストの項目 / 別の経路 |
