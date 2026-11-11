# Indexer API リファレンス v0.3

## 0. この文書について

- 対象: Crawler から Indexer への内部 API の契約(開始通知、バッチ登録、`last_seen_at` の部分更新、終了通知、Status API、ソース削除・突合の呼び出し)。
- 位置づけ: Indexer の API 契約を定める文書。プロダクト・設計判断を伴うものは決めず、第 6 章に「未決(ユーザー判断)」として集約した。本書の「未定義」「未決」は、本書でまだ決めていないことを指す。
- 読み方: 第 1 章で API の全体を確認し、第 4 章で各 API を同じ書式(概要 / エンドポイント / 呼び出し元 / リクエスト / レスポンス / エラー / 冪等性・注意事項 / 確認状況)で読む。
- 確認状況の区分: **確定**(ユーザー確定)、**案**(ユーザー未確定)、**提案**(本書の提案。案と同様に未確定)、**未決**(決めていない)、**推測**(根拠が弱い想定)。本文中の `(案)` などはこの区分。
- **エンドポイント形・応答コード・JSON のキー名・型はすべて案**(項目の意味だけを定めている)。型は例 JSON からの推定で、各表の「型」列は案。
- 関連文書(同じ `indexer/` 配下): `indexer-architecture-v0.3.md`(責務、登録処理、削除の判断・実行、整合性、障害、将来拡張)。`opensearch/schema/` 配下: `search-index-v0.3.md`、`loreley-texts-v0.3.md`、`loreley-deletions-v0.3.md`(削除結果の構造と状態の意味)。
- 未決の ID は本書内の `API-U-n`。`indexer-architecture-v0.3.md` に対応する未決・採番済みの案があるものは「architecture U-n」「architecture P-n」と参照する(新規の案は P26〜P34)。

## 1. API 一覧

| API | メソッド + パス(案) | 呼び出し元 | 用途 | 冪等性 | 確認状況 | 詳細 |
| --- | --- | --- | --- | --- | --- | --- |
| 開始通知 | `POST /crawls/start` | Crawler | クロールの開始を伝え、現行世代と削除結果(`running`)を作る | 冪等(同じ `crawl_id` で `running` なら状態を変えず成功) | 存在は確定、契約の形は案 | 4.1 |
| `last_seen_at` 部分更新 | `POST /sources/{source_id}/last-seen` | Crawler | 列挙で見つかった文書の `last_seen_at` を `crawl_started_at` に更新(取得より前に要請) | 冪等(max 比較) | 提案 | 4.2 |
| バッチ登録 | `POST /sources/{source_id}/documents:batch` | Crawler | 文書を同期で登録(文書単位の結果を返す) | 冪等(`document_id` と `content_hash`。同一ハッシュの扱いは architecture P26) | 提案 | 4.3 |
| 終了通知 | `POST /crawls/{crawl_id}/finish` | Crawler | 列挙の終了を伝え、削除の判断・実行を非同期に起動(202) | 冪等(再送は常に 202。最初に受理した内容を採用。案。architecture P34) | 存在は確定、契約の形は案 | 4.4 |
| Status API | `GET /crawls/{crawl_id}` | Crawler | 削除結果を読み取りで返す | 読み取り(影響なし) | 存在は確定、契約の形は案 | 4.5 |
| ソース削除 1 | `POST /sources/{source_id}/deletions:discard` | Crawler | 終端状態でない削除結果を `discarded`(`source_deleted`)にする | 冪等。応答は実行中バッチの終了後(architecture P29) | 提案 | 4.6 |
| ソース削除 2 | `DELETE /sources/{source_id}/documents` | Crawler | 文書を Store 層、検索インデックスの順にすべて削除 | 冪等(再送では 0 件でも成功) | 提案 | 4.7 |
| ソース削除 3 | `DELETE /sources/{source_id}/deletion-records` | Crawler | `loreley-deletions` の当該ソースの記録を削除 | 冪等 | 提案 | 4.8 |
| 突合 | `POST /sources/{source_id}/reconcile` | Crawler | 突合ジョブの実処理を Indexer に要請 | 未定義。検索のみの文書は検出・表示のみ(architecture P28) | 提案(分担は案) | 4.9 |

- Status API の利用者は Crawler。Admin View の削除結果の表示は、Admin API が `loreley-deletions` を直接読んで行い、`api` から `indexer` への通信は置かない。
- 原本サイズ超過は独立した API ではなく、バッチ登録に関わる未決事項(4.10)。

## 2. 概要(通信の流れ)

Crawler がソースのロックを取得してから、次の順に Indexer を呼ぶ。

1. 開始通知(ロック取得後・列挙前)。章 4.1。
2. 見つかった文書の `last_seen_at` 部分更新の要請。**取得より前に行う**。章 4.2。
3. 文書のバッチ登録(同期。文書単位の結果が返る)。章 4.3。
4. 終了通知(202 で受理)。すべてのバッチ登録と `last_seen_at` 部分更新の応答を確認してから送る。章 4.4。
5. 削除結果の確認(Status API のポーリング)。章 4.5。

- 削除の判断・実行は、終了通知を受けた Indexer が非同期に行う。期限による削除を Crawler は要請しない。ソース削除と突合ジョブでの削除要請だけは Crawler が要請する(4.6〜4.9)。
- 同期 HTTP では遅い Indexer がクロール全体の所要時間を決める。MVP では許容する。

## 3. 共通事項

### 3.1 通信方式

- Crawler と Indexer は別コンテナ。メッセージブローカーを使わず HTTP で直接通信する(確定)。内部ネットワークだけで通信し、ホストに公開しない。単一ホスト、単一 Crawler、単一 Indexer、直列実行、認証なし。
- 契約は、将来 HTTP 部分をメッセージングに置き換えられるよう明確にする(重複して届いても安全であること、文書単位の結果が互いに依存しないこと)。
- 書き込み役は `indexer-architecture-v0.3.md` の責務表が正本。要点: 検索インデックス、`loreley-texts`、`loreley-deletions`(仮名)に書くのは Indexer だけ。`loreley-jobs` に書くのは Crawler だけ。Admin API は書かず、読み取りのみで直接読む。

### 3.2 ロック所有情報の運び方(提案)

- 書き込みを伴う要請(バッチ登録、`last_seen_at` 部分更新、ソース削除の順 1、突合)には、ロック所有情報 `lock`(`owner`、`job_id`)と `crawl_id`(= `job_id`)を添える(提案)。
- Indexer は書き込み前に、ロック文書(`loreley-jobs` の `lock-{source_id}`)を ID で取得し、要請したジョブの所有者で期限内であることを確認する。Indexer は要請を直列に処理し、所有確認を文書ごとに行う(案)。
- 確認できなければ書き込みを中止し、スキップ・リトライの対象にせずジョブ `failed`・削除しない(案)。文書単位の結果には `lock_not_owned` を返す(3.4、API-U-13)。
- 確認と書き込みの間の窓は MVP では既知の制限として許容する。確認の対象は登録と `last_seen_at` の更新。要約の書き込みと削除の実行は対象外。
- ソース削除の順 2・3(4.7・4.8)には、ジョブがロックを最後まで保持する(architecture P29)ことを前提に添えられる(案)。ただし Crawler 側のロック設計の決定が前提で未決(API-U-14)。

### 3.3 ID

- `document_id` = `SHA-256(source_id + "\0" + external_id)` の 16 進文字列(小文字)。NUL 文字で区切る。
- `external_id` は、ハッシュの前に Unicode NFC へ正規化し、パス区切りを `/` に統一する(ルートからの相対パス、先頭に `/` を付けない)。大文字小文字は区別したまま扱う。
- 同じ文書を再取得すると同じ ID になるため、再実行しても重複しない。検索インデックスと Store 層のどちらも `document_id` を文書 ID として使う。
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
| 5xx / 接続エラー / タイムアウト | `unavailable` など | Indexer の異常 | リトライ、直らなければジョブ `failed` |

- 終了通知の再送は 409 にせず、常に冪等な 202 を返す(案。4.4、architecture P34)。開始通知の 409 を除き、コード名・HTTP の割り当ては未定義。`retryable` は Crawler のリトライ判断に使う補助で、必須ではない。
- **`lock_not_owned`**: 所有確認は文書ごとに行う(案)ため、リクエスト全体の 409 に固定せず、提案(案)として 4.3 の文書単位の結果に `failure_type: lock_not_owned`(4.2 は `result: lock_not_owned`)を加え、Crawler はそれをスキップ・リトライの対象にせずジョブ `failed` として扱う。バッチの途中でロックを失った場合の部分結果の返し方(確認済みの文書の結果と、未処理の文書の扱い)と、バッチの先頭で失敗した場合に全体のエラーにするかは未決(API-U-13)。

### 3.5 冪等性・リトライ方針

- 全 API は重複して届いても結果が変わらない(Status API は読み取り)。再送は安全。
- **登録の失敗の扱い**(バッチ登録、`last_seen_at` 部分更新):
  - 検索インデックスへの登録失敗は、Indexer が文書単位の失敗種別を返し、Crawler が最大試行回数までリトライして、それでも失敗したらスキップ。リトライは Crawler 側の既定値(最大 3 回、バックオフは初回 1 秒・2 倍・上限 30 秒・ジッタあり。いずれも案)。
  - スキップの対象は**文書固有の拒否**(マッピング違反、文書の内容に起因する 4xx など)だけ。文書固有の 4xx のスキップが連続 20 件(案。設定可能)に達したら `failed`。
  - 接続エラー、タイムアウト、HTTP 429、5xx、`cluster_block_exception`、circuit breaker は OpenSearch 全体の異常として、スキップせずジョブ `failed`。Indexer の異常(接続不可、タイムアウト、5xx 等)も同様で、リトライしても直らなければジョブ `failed`・削除しない。「Indexer・Store 層の障害でクロールが失敗扱いのときは削除しない」は確定。リトライ回数・連続 20 件・エラー種別・`failed` の対象範囲の細部は案。
  - ジョブ `failed` の対象は、開始通知、登録、`last_seen_at` の部分更新、終了通知の失敗に限る。Status API のポーリングの失敗は含まない。`last_seen_at` を保存できなければクロールを完了扱いにしない、は案(ユーザー未確認)。
  - 抽出の失敗はスキップではなく `extract_failed`(タイトルとメタデータを登録)として扱い、リトライしない。
- 通知(開始・終了)の失敗(リトライ設定の回数まで試しても直らない場合)はジョブ `failed`。削除が行われないだけで安全。
- 数値(バッチの件数と合計サイズ、タイムアウト、並列度、リトライ・ポーリングの回数や間隔)は未決(API-U-5、API-U-6)。

### 3.6 時刻の扱い

- 時刻(`crawl_started_at`、`last_seen_at`、TTL の判定)は、Crawler と Indexer が同じホストの時計で動く前提。
- 例 JSON の時刻は ISO 8601(UTC)で示す(形式は案)。

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

必須/任意は内容の列挙に基づく(案)。

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
| 409(案) | `stale_crawl_started_at` | `crawl_started_at` が現行世代のそれより古い(世代の巻き戻り防止) |
| 400 | `invalid_request` | リクエストの形式不正 |
| 5xx / 接続エラー | `unavailable` | Indexer の異常 |

- 判定の順序: (1) 終端状態なら 409 → (2) 同じ `crawl_id` で `running` なら状態を変えずに成功(再送) → (3) 世代が古ければ 409。
- Crawler は 409 をジョブ `failed` として扱う。

**冪等性・注意事項**:

- 同じ `crawl_id` で削除結果が `running` なら再送として成功を返す(冪等)。
- **即時の受理**: 旧い削除が待機中・判定中・実行中でも待たせず、すぐに受理する。
- **Indexer の動作**(判定を通ったとき): `deletion-{source_id}`(現行世代。用途は開始通知の世代判定と直近の開始通知の記録)を更新し、`deletion_result-{crawl_id}` を設定スナップショットの複写つきで `running` で作る(複写は案)。同じソースに、`finish_received_at` の無い `running` の旧い削除結果(終了通知が届かなかった世代)があれば `discarded`(理由 `superseded`)にする。`finish_received_at` のある結果には何もしない。判定と実行は複写した値を使い、`deletion-{source_id}` からは読まない。
- 通知の失敗(リトライ設定の回数まで試しても直らない場合)はジョブ `failed`。開始通知の失敗は、削除が行われないだけで安全。

**確認状況**: 開始通知の存在は確定。エンドポイント形、応答コード、409、設定スナップショットの複写、キー名は案。未決: API-U-1(項目名)、API-U-12(409 条件)、API-U-5(設定値)。

### 4.2 `last_seen_at` の部分更新(提案)

**概要**: Crawler が列挙で見つけたすべての文書について、**取得より前に**要請する。Indexer は現在値との max 比較(スクリプト更新)で、新しい値のときだけ `last_seen_at` を書く。ほかのフィールドは変更しない。文書がなければ(`not_found`)何もしない(upsert しない)。取得・抽出・登録が失敗しても更新済みのまま残るので、取得に失敗してスキップした文書が TTL で誤削除されない。

**エンドポイント**: `POST /sources/{source_id}/last-seen`(案)

**呼び出し元**: Crawler(列挙で見つかった文書。取得より前)

**リクエスト**: 要請する単位は文書 ID の配列(提案。単位と件数は未決)。バッチ登録では Indexer が `document_id` を算出して返すのに対し、ここでは Crawler が 3.3 の規則で算出して渡す(非対称)。`external_id` の配列を渡して Indexer が算出する形にするかは未決(API-U-7)。

| 名前 | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `source_id`(パス) | string | ○ | データソース ID |
| `crawl_id` | string | ○ | クロール ID(= `job_id`) |
| `lock` | object(`owner`, `job_id`) | ○ | ロック所有情報(3.2) |
| `crawl_started_at` | datetime | ○ | 書き込む値 |
| `document_ids` | string[] | ○ | 3.3 の規則で Crawler が算出した ID。件数の上限は未決 |

```json
{
  "crawl_id": "job-20261109-0001",
  "lock": { "owner": "crawler-1", "job_id": "job-20261109-0001" },
  "crawl_started_at": "2026-11-09T01:00:00Z",
  "document_ids": [
    "05d5868e1431979f741c1343912eedffa3eb2bdfadbabe0c8408e6bd902e63c0",
    "27d5b4ef2f8e7dd2d5986774a5beb37fee200750fab4ffdf48cc0d570ae8b480"
  ]
}
```

**レスポンス**(文書単位):

| 名前 | 型 | 説明 |
| --- | --- | --- |
| `results[].document_id` | string | 対象の文書 ID |
| `results[].result` | string | `updated` / `unchanged` / `not_found` / `lock_not_owned` |

```json
{
  "results": [
    { "document_id": "05d5868e1431979f741c1343912eedffa3eb2bdfadbabe0c8408e6bd902e63c0", "result": "updated" },
    { "document_id": "27d5b4ef2f8e7dd2d5986774a5beb37fee200750fab4ffdf48cc0d570ae8b480", "result": "not_found" }
  ]
}
```

- `updated`: 新しい値を書いた。`unchanged`: 現在値以上のため書かない。`not_found`: 索引に文書がなく何もしない(新規文書では正常)。この 3 つは成功扱いで、スキップ扱いにしない。
- `lock_not_owned`: 所有確認に失敗した文書(提案(案)。成功扱いではなくジョブ `failed`。3.4)。

**エラー**:

| ステータス | コード(提案) | 条件 |
| --- | --- | --- |
| 400 | `invalid_request` | リクエストの形式不正 |
| 5xx | `unavailable` | 書き込み不可(OpenSearch への書き込み失敗など)。Crawler はジョブ `failed`・削除しない |

**冪等性・注意事項**: 重複して届いても結果は変わらない(max 比較)。確認と書き込みの間の窓は既知の制限(3.2)。

**確認状況**: 提案(案)。`last_seen_at` を検索インデックスの文書に持ち、`crawl_started_at` を渡して Indexer が書くことは確定。要請の単位・`document_id` の算出主体は未決(API-U-7)。ロック失敗時の返し方は未決(API-U-13)。

### 4.3 バッチ登録(提案)

**概要**: 文書を同期 HTTP で登録する。応答は文書単位で、失敗した文書だけを再送できる。新規か更新かも含める(案。項目の形は未決)。集計して `loreley-jobs` に記録するのは Crawler。Indexer の登録処理(抽出、Store 層・検索インデックスへの書き込み順、競合時の扱い、同一 `content_hash` の扱い)は `indexer-architecture-v0.3.md` を参照。

**エンドポイント**: `POST /sources/{source_id}/documents:batch`(案)

**呼び出し元**: Crawler(取得・抽出対象の文書ごと)

**リクエスト**: `raw_content` は JSON で運ぶため base64 とする(提案。上限と運び方の最終形は未決)。base64 は原本より約 33% 大きくなり、JSON の解析と複写でメモリも使う。運び方は multipart(原本をバイナリのまま送る)や文書ごとの個別送信などの選択肢を残す(案。API-U-17。実測項目は architecture 15.4)。`document_id` は Indexer が 3.3 の規則で算出して返す(Crawler が付けた値との照合はしない提案)。

| 名前 | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `source_id`(パス) | string | ○ | データソース ID |
| `crawl_id` | string | ○ | クロール ID(= `job_id`) |
| `crawl_started_at` | datetime | ○ | クロールの開始時刻。Indexer が `last_seen_at` に書く値(4.2 と同じ値) |
| `lock` | object(`owner`, `job_id`) | ○ | ロック所有情報(3.2) |
| `documents[]` | object[] | ○ | 登録する文書(要素の項目は下表)。件数・合計サイズは未決(API-U-6) |

`documents[]` の要素(Connector(Crawler)が Indexer に渡す文書。項目名・型は案。`source_id` はパスから取るため要素には含めない):

| 名前 | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `external_id` | string | ○ | データソース内で一意な識別子(ルートからの相対パス、ページ ID 等)。3.3 の正規化を適用する |
| `title` | string | ○ | タイトル(取得できなければファイル名) |
| `url` / `path` | string | 任意 | 原文への参照(表示用)。1 項目か 2 項目かは未決(API-U-3。architecture U-16) |
| `mime_type` | string | ○ | 文書形式 |
| `raw_content` | string(base64) | ○ | 取得済みの原本(MVP では参照ではなく原本そのものを渡す。base64 は提案)。抽出前のデータで、検索インデックスの `content`(抽出後の本文)とは別物 |
| `content_hash` | string | ○ | 原本の SHA-256 |
| `source_updated_at` | datetime | ○ | データソース上の更新日時(ローカルでは `mtime`) |
| `size` | integer | ○ | 原本のサイズ(バイト) |
| `fetched_at` | datetime | 任意 | 原本を取得した日時。取得を省略した場合は更新しない(MVP は全件取得で省略しない) |
| `metadata` | object | 任意 | Connector 固有の追加属性 |

必須/任意は例 JSON と各項目の意味からの推定(案)。

- `fetched_at` と `metadata` の保存先は未定義。保存するか受け取るだけかは未決(API-U-2。architecture U-16)。
- `last_seen_at` は要素に含めない。Crawler はリクエストの `crawl_started_at`(クロールの開始時刻)を渡し、Indexer が `last_seen_at` に書く(4.2)。開始通知(4.1)の値と異なる値が来たときの検証は必須にしない(案。API-U-18)。`fetched_at` は「取得した日時」、`last_seen_at` は「列挙で見つかった日時」。
- `content` の意味は場所ごとに異なる: Connector → Indexer は `raw_content`(原本)、Store 層は `text`(抽出・正規化後のテキスト)、検索インデックスは `content`(`text` と同じ内容を検索用に解析したもの)。

```json
{
  "crawl_id": "job-20261109-0001",
  "crawl_started_at": "2026-11-09T01:00:00Z",
  "lock": { "owner": "crawler-1", "job_id": "job-20261109-0001" },
  "documents": [
    {
      "external_id": "guide/setup.md",
      "title": "セットアップ手順",
      "path": "guide/setup.md",
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

リクエスト例は 1 文書目だけを示す(応答例は `guide/setup.md` と `guide/intro.md` の 2 文書を送った場合)。

**レスポンス**(HTTP 200。文書単位):

| 名前 | 型 | 説明 |
| --- | --- | --- |
| `results[].external_id` | string | 送られた `external_id` |
| `results[].document_id` | string | Indexer が算出した ID |
| `results[].status` | string | `ok` / `failed` |
| `results[].change` | string | `created` / `updated`(`ok` のとき。案)。原本ハッシュも抽出後の本文も同じで検索インデックスの全文 upsert だけを行った場合(architecture P26)を `updated` に数えるかは未決(API-U-9) |
| `results[].extract_failed` | boolean | 抽出に失敗し、タイトルとメタデータを登録した場合 `true` |
| `results[].failure_type` | string | `failed` のとき。候補は下記(提案。具体名は未決) |
| `results[].message` | string | 失敗の説明(任意。案) |

```json
{
  "results": [
    {
      "external_id": "guide/setup.md",
      "document_id": "05d5868e1431979f741c1343912eedffa3eb2bdfadbabe0c8408e6bd902e63c0",
      "status": "ok",
      "change": "created",
      "extract_failed": false
    },
    {
      "external_id": "guide/intro.md",
      "document_id": "27d5b4ef2f8e7dd2d5986774a5beb37fee200750fab4ffdf48cc0d570ae8b480",
      "status": "failed",
      "failure_type": "document_rejected",
      "message": "mapping violation"
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

**エラー**:

| ステータス | コード(提案) | 条件 |
| --- | --- | --- |
| 400 | `invalid_request` | リクエストの形式不正(例: `documents` が空) |
| 5xx / 接続エラー / タイムアウト | `unavailable` など | Indexer の異常。リトライし、直らなければジョブ `failed` |

**冪等性・注意事項**:

- 再送しても登録の状態が変わらない(`document_id` と `content_hash` で判定)。Indexer が `raw_content` の SHA-256 を計算して `content_hash` と照合するかは未決(API-U-15)。
- 同一 `content_hash` の文書の扱いは architecture P26(案)。原本ハッシュと抽出後の本文が一致すれば Store 層を書かず検索インデックスの全文 upsert のみ(要約は引き継ぐ)。原本ハッシュが一致して本文が不一致なら `pending_index` の経路に乗せ、要約を無効化する。いずれも応答の形は変わらない。
- 登録の途中で Store 文書が窓で消え、Store の確定更新が 404 になった場合は、文書単位の失敗としてリトライ対象にする(案。architecture P27。`failure_type` の名称は API-U-7)。
- 抽出の失敗は `status: ok` かつ `extract_failed: true`(失敗ではなくタイトルとメタデータの登録。リトライしない)。
- 本文が変わらない再登録を「更新」に数えるか、再送の数え直しは未決(API-U-9)。再送時の集計は、Crawler が `document_id` ごとに最初の成功結果を保持して数え、再送の成功では数え直さない規則を推奨とする(案。API-U-16)。
- 原本サイズ超過の応答は未決(4.10)。件数照合では `oversize_document_ids` として別に送る(4.4)。

**確認状況**: 同期 HTTP、文書単位の結果、冪等、失敗した文書だけ再送は確定(方式。数値・形式は未決)。エンドポイント、リクエスト/レスポンスの形、失敗種別名、`lock` の運び方は提案(API-U-7)。新規/更新を含めることは案(API-U-9)。

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
    "27d5b4ef2f8e7dd2d5986774a5beb37fee200750fab4ffdf48cc0d570ae8b480"
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

**レスポンス**: `202 Accepted`(ボディなし、または 4.1 と同形。案)。判断の結果は含めない。

**エラー**:

| ステータス | コード(提案) | 条件 |
| --- | --- | --- |
| 400 | `invalid_request` | リクエストの形式不正 |
| 5xx / 接続エラー / タイムアウト | `unavailable` など | Indexer の異常(リトライし、直らなければジョブ `failed`。届かなければ削除が行われないだけで安全) |

**冪等性・注意事項**:

- **再送は常に冪等な 202**(受理時の分岐の先頭で判定。案。architecture P34)。記録済み(`finish_received_at` が記録済み、または結果が `failed` など終端状態)の再送は、世代を見ず再処理せず、内容が異なっていても最初に受理した内容を採用して 202 を返す(409 は返さない。後の内容は採用せず、ログには残せる)。`outcome=failed` / `cancelled` は `finish_received_at` を記録しないため、結果が終端状態であることで再送を判定する。
- **受理時の分岐**(世代の判定はこの受理時に 1 回だけ行う。(1)〜(4) のどの分岐でも応答は 202):
  1. `finish_received_at` が未記録で、その `crawl_id` の削除結果がすでに終端状態(終了通知が届かないまま新しい開始通知で `superseded` になった旧世代への遅れた終了通知など): 何もしない。状態を変えず、削除しない。
  2. 開始通知を受けていない未知の `crawl_id`: 削除に使わず破棄する(確定)。削除結果を作らずログに残すだけとする扱いは案(architecture P16。記録する場合は件数の上限を設ける選択肢がある)。
  3. `outcome` が `failed` または `cancelled`: 待たずに `failed`(理由 `outcome_failed` または `outcome_cancelled`)を記録して削除しない(`finish_received_at` は記録しない)。削除結果を `failed` にしてから 202 を返す。
  4. `enumeration_completed`: `finish_received_at` を `loreley-deletions` に永続化してから 202 を返す(202 のあとに再起動しても、受理した事実が残り、再起動時に `failed`(`indexer_restart`)にできる)。ソースごとの待ち行列に入れ、先行する削除結果が終端状態になってから判定に進む。判定の順(順 1〜6)と実行は `indexer-architecture-v0.3.md` を参照。割合ルール内の判定 1〜3 は `loreley-deletions-v0.3.md` と `indexer-architecture-v0.3.md` を参照。
- **応答が失われた場合**(案。既存の仕様からの帰結): 応答が失われただけなら、Indexer は受理済みで削除が進みうる(Crawler からは届かなかった場合と区別できない)。結果は削除結果に残る。Crawler が再送もすべて失敗してジョブ `failed` にしても削除が進みうる点は、「Indexer・Store 層の障害で失敗扱いのときは削除しない」の適用範囲を受理されなかった場合に限る例外として扱う(案。ユーザー確認待ち。architecture P31)。「安全」の根拠は、前提(列挙の完了、全バッチの登録の確認)が送信前に確認済みであることと、実行時の各文書の削除直前の TTL 再確認。

**件数照合**(終了通知の値の定義): Indexer は次が成立するときだけ削除の判断に進む。不一致なら削除せず `validation_failed` として記録する(許容差なし。案)。

```text
enumerated_count == N_seen + E_missing
  N_seen    = 当該 source_id で last_seen_at >= crawl_started_at の件数(リフレッシュ後の検索インデックス)
  E_missing = skipped_document_ids と oversize_document_ids の和集合のうち、検索インデックスにないものの件数(重複は 1 件。architecture P32)
```

- `skipped_document_ids` と `oversize_document_ids` の合計が上限を超えるときも、削除せず `validation_failed`(案)。上限の値と送り方(エンコード、分割)は未決(API-U-5)。
- 抽出に失敗した文書(`extract_failed`。タイトルとメタデータを登録)は検索インデックスにあるので `N_seen` に数えられる。
- 突合ジョブの再登録など、列挙以外の書き込みで `N_seen` が増えると不一致になり、削除しない(安全側)。旧い削除の待機中に新しいクロールが `last_seen_at` を更新して不一致になる場合も、削除しない側に倒れるだけなので許容(案)。
- 同じ ID が `skipped_document_ids` と `oversize_document_ids` の両方にあっても、`E_missing` の上では和集合で 1 件と数える(`skipped_count` は `skipped_document_ids` の件数のまま)。
- 新規の原本サイズ超過文書は `oversize_document_ids` で数える(architecture P32)。拒否主体などの残りは未決(4.10、API-U-8)。

**確認状況**: 終了通知の存在、202、世代 `crawl_id`、未知の `crawl_id` の破棄、件数照合は確定。エンドポイント形、409 の廃止(再送は常に 202)、応答喪失の記述、`oversize_document_ids`、未知の `crawl_id` を記録しない扱いは案。未決: API-U-12(`failed` 時の項目省略)、API-U-5(ID リストの上限)。

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
- 各状態の意味と記録項目は `loreley-deletions-v0.3.md` を参照。

応答例(待機中。`waiting_for` は任意項目):

```json
{
  "crawl_id": "job-20261109-0002",
  "source_id": "src-docs",
  "status": "running",
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

**概要**: ソース削除は Crawler のジョブで、期限削除の判断(割合ルール)は通らない。全体の順序は次のとおり。そのソースの終端状態でない削除結果を `discarded`(理由 `source_deleted`)にする(本 API)→ 文書を Store 層、検索インデックスの順にすべて削除(4.7)→ スキップ記録(Crawler が削除。案)と、削除の記録(`deletion-{source_id}` と `deletion_result-*`)を削除(4.8 など)→ データソース設定を削除 → **ロック文書の削除は最後**。ジョブは `source_id` 単位のロックを最後まで保持する(案。architecture P29。Crawler 側のロック設計の決定が前提で未決。API-U-14)。この要請は Deletion Manager のソース単位の直列実行で最優先とする。Indexer に要請するのは 4.6〜4.8 の 3 つ(提案)。いずれも再送しても結果は変わらない。

**エンドポイント**: `POST /sources/{source_id}/deletions:discard`(案)

**呼び出し元**: Crawler(ソース削除ジョブ)

**リクエスト**:

| 名前 | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `source_id`(パス) | string | ○ | データソース ID |
| `lock` | object(`owner`, `job_id`) | 例では添付(要否は未決。API-U-14) | ロック所有情報 |
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
- 書き込みは `if_seq_no` の条件付き更新で、すでに終端状態の結果は上書きしない。衝突したら読み直して再試行し、終端状態になるか `discarded` にできるまで繰り返す(案。回数・間隔は未決)。実行中の削除側の停止確認は `indexer-architecture-v0.3.md` を参照。

**確認状況**: 提案(案)。ソース削除での分担(Crawler が起動・管理、Indexer が実処理)、応答を実行中バッチの終了後にすることは案。未決: API-U-7、API-U-14。

### 4.7 ソース削除 2: 文書の全削除(提案)

**概要**: そのソースの文書を Store 層、検索インデックスの順にすべて削除する。

**エンドポイント**: `DELETE /sources/{source_id}/documents`(案)

**呼び出し元**: Crawler(ソース削除ジョブ。4.6 のあと)

**リクエスト**: パス `source_id`(string・必須)。ロック所有情報 `lock` は、ジョブがロックを最後まで保持する前提で添えられる(案。Crawler 側のロック設計が前提で未決。API-U-14)。

**レスポンス**:

| 名前 | 型 | 説明 |
| --- | --- | --- |
| `deleted_count` | integer | 完了時点の削除件数。再送では 0 でも成功 |

```json
{ "deleted_count": 1215 }
```

**エラー**: 400 `invalid_request`、5xx `unavailable`(3.4)。個別のコードは未定義。

**冪等性・注意事項**: 再送しても結果は変わらない。書き込み排他の対象にするかは案として、ロックの保持と 4.6 の `discarded` 済みを前提に排他は不要とする(`indexer-architecture-v0.3.md` 8章の方針)。所要時間が長い場合の非同期化(202 とポーリング)は提案に含めない。要否は未決(API-U-12)。

**確認状況**: 提案(案)。未決: API-U-7、API-U-12、API-U-14。

### 4.8 ソース削除 3: 削除記録の削除(提案)

**概要**: `loreley-deletions` の当該ソースの記録(`deletion-{source_id}` と `deletion_result-*`)を削除する。

**エンドポイント**: `DELETE /sources/{source_id}/deletion-records`(案)

**呼び出し元**: Crawler(ソース削除ジョブ。4.7 のあと)

**リクエスト**: パス `source_id`(string・必須)。ロック所有情報 `lock` は 4.7 と同じく添えられる(案。API-U-14)。

**レスポンス**:

| 名前 | 型 | 説明 |
| --- | --- | --- |
| `deleted` | boolean | 削除した場合 `true` |

```json
{ "deleted": true }
```

**エラー**: 400 `invalid_request`、5xx `unavailable`(3.4)。個別のコードは未定義。

**冪等性・注意事項**:

- 再送しても結果は変わらない。
- **ソース削除ジョブのロック**(案。architecture P29): ジョブは `source_id` 単位のロックを最後まで保持し、ロック文書の削除は手順の最後(本 API のあと)にする。このため本 API の時点でもロック文書は存在し、4.7・4.8 の要請にロック所有情報を添えて所有確認できる。ジョブがロックを取ること自体と Crawler 側のロック設計は、Crawler 領域の決定が前提で未決(API-U-14。architecture 9.14、U-4)。

**確認状況**: 提案(案)。未決: API-U-7、API-U-14。

### 4.9 突合(提案)

**概要**: 実処理は Indexer、ジョブとしての起動・管理は Crawler(案)。同じソースのロックを取り、クロールと同時には動かさない。比較・修復の内容(比較対象、安全な再登録の範囲)は `indexer-architecture-v0.3.md` を参照。

**エンドポイント**: `POST /sources/{source_id}/reconcile`(案)

**呼び出し元**: Crawler(突合ジョブ)

**リクエスト**:

| 名前 | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `source_id`(パス) | string | ○ | データソース ID |
| `job_id` | string | ○(例の形) | 突合ジョブの ID |
| `lock` | object(`owner`, `job_id`) | ○(例の形) | ロック所有情報(3.2) |

```json
{ "job_id": "job-20261109-0020", "lock": { "owner": "crawler-1", "job_id": "job-20261109-0020" } }
```

検索インデックスにだけある文書(Store 層にない文書)は、MVP では削除せず検出・表示のみ(案。architecture P28)。Admin View で確認して扱う。

**レスポンス**(結果の項目は architecture の突合の内容に従う。以下は形の例。項目名とジョブ記録への反映は未決):

| 名前 | 型 | 説明 |
| --- | --- | --- |
| `job_id` | string | 突合ジョブの ID |
| `status` | string | 例: `completed` |
| `detected` / `re_registered` / `search_only` | integer | 結果の件数(形の例)。`search_only` は検索インデックスにだけある文書の検出件数(削除しない) |

```json
{ "job_id": "job-20261109-0020", "status": "completed", "detected": 3, "re_registered": 2, "search_only": 1 }
```

**エラー**: 400 `invalid_request`、5xx `unavailable`(3.4)。個別のコードは未定義。

**冪等性・注意事項**: 未定義。突合の再登録など列挙以外の書き込みで `N_seen` が増えると、件数照合が不一致になり削除しない(4.4。安全側)。

**確認状況**: 提案(案)。ソース削除・突合での分担は案。結果の項目名とジョブ記録への反映は未決(API-U-7)。

### 4.10 補足: 原本サイズ超過(API ではない)

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
- 登録結果(`enumerated_count` / `created_count` / `updated_count` / `skipped_count` / `oversize_count` / `error_count` / `partial`。名称は案)は、Crawler がバッチ応答を集計して `loreley-jobs` に持つ。Indexer が返すのは文書単位の応答(4.3)だけ。

## 6. 確認状況

### 区分ごとの整理

| 論点 | 区分 |
| --- | --- |
| Crawler と Indexer は別コンテナ、HTTP 直接通信 | 確定 |
| 開始通知、終了通知(202)、Status API の存在。ポーリングの失敗・上限時間超過は警告のみ。ジョブ status と削除結果は切り離す | 確定(契約の形は案) |
| 世代 `crawl_id`、未知の `crawl_id` の終了通知を削除に使わず破棄すること、件数照合(`enumerated_count == N_seen + E_missing`) | 確定 |
| 削除の判断・実行は Indexer(Deletion Manager)。`loreley-deletions` に書くのは Indexer だけ。`loreley-jobs` に書くのは Crawler だけ | 確定(インデックス名は仮名) |
| Status API は削除結果のみ。登録結果は `loreley-jobs`(Crawler が集計、Admin API が読む) | 確定 |
| Indexer・Store 層の障害でクロールが失敗扱いのときは削除しない | 確定(ユーザー確認済み) |
| 原本サイズ超過の決定済み範囲(取り込まず文書単位のエラー、スキップ・リトライではない) | 確定 |
| `last_seen_at` を検索インデックスの文書に持つ。`crawl_started_at` を渡して Indexer が書く | 確定 |
| エンドポイント形(`POST /crawls/start` 等)、応答コード、開始通知の 409、設定スナップショットの複写、`waiting_for`、削除結果の状態名の一覧(architecture P25)、`failed` の理由コード名、Status API の 404 条件、未知の `crawl_id` について削除結果を作らず記録しない扱い(記録する場合は件数の上限を設ける選択肢。architecture P16)、終了通知の応答喪失の記述(K12 の適用範囲の例外。architecture P31)、終了通知の再送を常に冪等な 202(先着採用)とし 409 を廃止すること(architecture P34)、`oversize_document_ids` を別項目にすること(architecture P32)、キー名 | 案 |
| バッチ登録に `crawl_started_at` を必須で加えること(4.2 と整合。開始通知と異なる値の検証は必須にしない)、同一ハッシュの扱いと Store 確定更新の 404 を文書単位のリトライにすること(architecture P26、P27)、バッチ応答に新規/更新を含める、ロック所有確認の方式(Indexer が文書ごとに確認、要請を直列処理。部分結果の返し方は未決)、`last_seen_at` を保存できなければクロールを完了扱いにしない、リトライ既定値・連続 20 件 | 案 |
| ソース削除・突合での分担(Crawler が起動・管理、Indexer が実処理)、ジョブがソースのロックを最後まで保持しロック文書の削除は最後にすること、discard 要請の応答を実行中バッチの終了後にすること(architecture P29。Crawler 側のロック設計が前提で未決)、突合で検索のみの文書を検出・表示のみにすること(architecture P28) | 案 |
| 4.2、4.3、4.6〜4.9 の提案(エンドポイント、リクエスト/レスポンス例、エラー応答の形、失敗種別名、`lock` の運び方) | 案(本書の提案) |
| 数値の既定値・上限(ポーリング間隔・上限時間・リトライ回数、保持件数 N、`skipped_document_ids` と `oversize_document_ids` の合計の上限、バッチの件数・合計サイズ、タイムアウト、並列度、原本の上限) | 未決 |
| 下表の `API-U-*` の各項目(`loreley-texts` の廃止、設定スナップショットと複写の項目名、`fetched_at`・`metadata` の保存先、`url`/`path` の項目数、原本サイズ超過の拒否主体と具体、ロック所有確認の部分結果の返し方、ソース削除ジョブのロック、`content_hash` の照合、再送時の集計規則、`raw_content` の運び方と実測など) | 未決(ユーザー判断) |

### 未決(ユーザー判断)の一覧

| ID | 内容 | 選択肢(あれば) |
| --- | --- | --- |
| API-U-1 | 設定スナップショットの項目名(開始通知、`deletion_result` の複写、Status API のしきい値)の統一(architecture U-14) | 開始通知の名称(`ttl` / `ratio_threshold` / `min_delete_count` / `force_delete`)に揃える。複写先では `force_delete` を `forced` として持つ |
| API-U-2 | `fetched_at`・`metadata` の保存先(architecture U-16) | 保存する(Schema に追加)/ 受け取るだけで保存しない(API 文書に明記) |
| API-U-3 | `url` / `path` の項目数(architecture U-16) | どちらか一方が入る 1 項目 / 2 項目 |
| API-U-4 | 原本サイズ超過の拒否主体(architecture U-5) | Crawler が送信前に弾く / Indexer が拒否する |
| API-U-5 | ポーリング間隔・上限時間・リトライ回数、保持件数 N、`skipped_document_ids` と `oversize_document_ids` の合計の上限と送り方、削除バッチ件数、しきい値・最小件数の既定値(architecture U-1、U-2) | なし |
| API-U-6 | バッチの件数・合計サイズ、タイムアウト、並列度(architecture U-3) | なし |
| API-U-7 | 内部 API の契約本体(4.2、4.3、4.6〜4.9 の提案の採否)、失敗種別・エラーコードの具体名、ロック所有情報の形、`last_seen_at` 部分更新の要請の単位(`document_id` の算出主体を含む。4.2)、ソース削除・突合の呼び出し形(architecture U-4)。`document_id` の算出と `external_id` の正規化(3.3)は Crawler(4.2)と Indexer(4.3)で二重に実装することになるため、対策として共有ライブラリ、またはテストベクタ(入力と期待 ID の組)の共有を選択肢とする(構成は変えない) | 提案を採用 / 修正。二重実装の対策は共有ライブラリ / テストベクタ / 現状 |
| API-U-8 | 原本サイズ超過の具体(上限、記録先・項目、ジョブ status への影響、既存の索引データを残すか。件数照合は `oversize_document_ids` を別項目にする案。4.4)(architecture U-5) | なし |
| API-U-9 | 本文が変わらない再登録(同一ハッシュで検索の全文 upsert のみの場合を含む。architecture P26)を「更新」に数えるか。再送の数え直しは API-U-16 | 更新に数える / 数えない / `change` に `unchanged` を加える |
| API-U-10 | Status API の 404 条件の確定(architecture 9.5。P1) | 4.5 の案を確定 / 修正 |
| API-U-11 | `loreley-texts` の廃止(architecture U-21) | 本書の契約には影響しない。`loreley-texts-v0.3.md` と `indexer-architecture-v0.3.md` を参照 |
| API-U-12 | 終了通知の再送を常に冪等な 202(先着採用)とし 409 を廃止する案(architecture P34)の採否、開始通知の 409 条件、`failed` 時の終了通知の項目省略可否、ソース削除の順 2(4.7)の非同期化 | 案の確定 / 修正 |
| API-U-13 | ロック所有確認を文書ごとに行う(案)場合の、バッチ途中でロックを失ったときの部分結果の返し方(確認済みの文書の結果、未処理の文書の扱い、バッチの先頭での失敗を全体のエラーにするか)。`lock_not_owned` を文書単位の結果に加える提案(3.4)の採否(architecture U-4) | 文書単位の結果に加える / リクエスト全体の 409 にする / 併用 |
| API-U-14 | ソース削除ジョブが `source_id` 単位のロックを最後まで保持し、ロック文書の削除を最後にする案(architecture P29)の採否、4.7・4.8 の要請にロック所有情報を添えるか。Crawler 側のロック設計の決定が前提(architecture U-4、9.14) | 案を採用 / 修正 / ロックを取らない |
| API-U-15 | バッチ登録で Indexer が `raw_content` の SHA-256 を計算して `content_hash` と照合するか(4.3) | 照合して不一致は文書単位の失敗にする / 照合せず Crawler の値を信用する |
| API-U-16 | 再送時の `created` / `updated` の集計(API-U-9 関連)。推奨は、Crawler が `document_id` ごとに最初の成功結果を保持し、再送の成功では数え直さない規則 | 推奨を採用 / 修正 |
| API-U-17 | `raw_content` の運び方と上限。base64 は約 33% 増えるため、原本の上限・バッチの件数と合計サイズ・メモリ使用量を実測して決める(architecture 15.4) | JSON + base64 / multipart / 文書ごとの個別送信 |
| API-U-18 | バッチ登録の `crawl_started_at` が開始通知(4.1)の値と異なるときの検証(必須にしないのは案) | 検証しない / 異なれば文書単位または全体のエラーにする |
