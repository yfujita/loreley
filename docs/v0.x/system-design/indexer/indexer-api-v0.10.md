# Indexer API リファレンス v0.10

- 版: v0.10
- 更新日: 2026-11-12
- 前版: `indexer-api-v0.9.md`

## 0. この文書について

- 対象: Crawler から Indexer への内部 API の契約(開始通知、バッチ登録、`last_seen_at` の部分更新、終了通知、Status API、ソース削除の呼び出し)。
- 位置づけ: Indexer の API 契約を定める文書。プロダクト・設計判断を伴うものは決めず、第 6 章に「未決(ユーザー判断)」として集約した。本書の「未定義」「未決」は、本書でまだ決めていないことを指す。
- 読み方: 第 1 章で API の全体を確認し、第 4 章で各 API を同じ書式(概要 / エンドポイント / 呼び出し元 / リクエスト / レスポンス / エラー / 冪等性・注意事項 / 確認状況)で読む。
- 確認状況の区分: **確定**(ユーザー確定)、**案**(ユーザー未確定)、**提案**(本書の提案。案と同様に未確定)、**未決**(決めていない)、**推測**(根拠が弱い想定)。本文中の `(案)` などはこの区分。
- **案(推奨。ユーザー承認待ち)**: 推奨(承認待ち)の記述。ユーザーの承認ではなく、確定ではない。承認されるまで確定扱いにしない。
- **エンドポイント形・応答コード・JSON のキー名・型は案**(項目の意味だけを定めている)。型は例 JSON からの推定で、各表の「型」列は案。**v0.10 の扱い**: Indexer の実装(2026-11-11〜12)が採用し、ユーザーが承認した事項は「確定」とし、根拠に承認日と architecture の K 番号を書く。承認は、2026-11-11 の実装プランの 22 項目(作業記録 `0002` §3)と、2026-11-12 の追加承認(同 `0021` の §1・§2。節番号まで書いたものが確定の根拠)、同日の TTL・メンテナンスフラグに関するユーザー判断(同 `0014`。K63 の fail-closed)。記録番号は `agent_tasks/20261111_implement_indexer/` の作業記録を指す。承認の個別の記録がない部分(エンドポイント形、キー名、上記に含まれないコード名・失敗種別名、受理まわりの細目(0020 §6-2。0021 で全て承認)など)は確定とせず、案のままで、実装は案どおりに実装している(「実装で採用中」)。Crawler・infra の設計の確定時に再確認する(API-U-23、API-U-24)。
- 関連文書: `indexer-architecture-v0.10.md`(同じ `indexer/` 配下。責務、登録処理、書き込みの競合制御、削除の判断・実行、整合性、障害、将来拡張)。`opensearch/schema/` 配下: `search-index-v0.10.md`(検索インデックスのスキーマ)、`loreley-deletions-v0.10.md`(削除結果の構造と状態の意味)。
- 未決の ID は本書内の `API-U-n`。`indexer-architecture-v0.10.md` に対応する決定・案・未決があるものは「architecture K-n」「architecture P-n」「architecture U-n」と参照する(本書に関わるのは K7、K12、K18〜K71 のうち 4.x に関わるもの、P16、P25、P29、P32、U-4、U-14、U-26、U-31、U-34 など)。本書で確定扱いにするのは K12、K18〜K56 と、v0.10 で加わった K57〜K63、K65〜K67 で、確定行は architecture の K 番号に対応する(K66 は削除結果の状態名・理由コード名・`finished_at` を含まず、K67 は `/healthz`・実行モデル・ソース単位の直列化・起動前の 503 に限る。起動順・停止順は案)。それ以外は案・未決である(K22 の `text_hash` は変更の有無の判定と要約の整合のための内部処理で、API 契約に現れない)。

## 1. API 一覧

| API | メソッド + パス(案) | 呼び出し元 | 用途 | 冪等性 | 確認状況 | 詳細 |
| --- | --- | --- | --- | --- | --- | --- |
| 開始通知 | `POST /crawls/start` | Crawler | クロールの開始を伝え、現行世代と削除結果(`running`)を作る | 冪等(同じ `crawl_id` で `running` かつ複写済みの項目(`rewrite_mode` を含む)が一致すれば状態を変えず成功。不一致は 409 で状態不変。architecture K24、K33) | 存在は確定、契約の形は案 | 4.1 |
| `last_seen_at` 部分更新 | `POST /sources/{source_id}/last-seen` | Crawler | 列挙で見つかった文書の `last_seen_at` を `crawl_started_at` に更新(取得より前に要請。Update API の max 比較)。`crawl_id`・`crawl_started_at` は必須で、削除結果が受理可能な状態のときだけ受理する(architecture K23) | 冪等(max 比較) | 提案(一部確定。architecture K66) | 4.2 |
| バッチ登録 | `POST /sources/{source_id}/documents:batch` | Crawler | 文書を同期で登録(文書単位の結果を返す)。受理条件は 4.2 と同じ(architecture K23) | 冪等(`document_id` と、検索インデックスの現在の文書との比較。変更のない文書は書かない) | 提案(一部確定。architecture K66) | 4.3 |
| 終了通知 | `POST /crawls/{crawl_id}/finish` | Crawler | 列挙の終了を伝え、削除の判断・実行を非同期に起動(202)。受理時に、件数照合に使うスキップ文書 ID 一覧とサイズ超過文書 ID 一覧を `deletion_result` に保存する(architecture K31。2つの合算件数が上限を超えるときは保存しない。K34) | 冪等(同じ内容の再送は 202。内容が異なる再送は 409。`source_id` が `deletion_result` と一致しなければ処理前に 409。architecture K25、K32) | 存在は確定、契約の形は案 | 4.4 |
| Status API | `GET /crawls/{crawl_id}` | Crawler | 削除結果を読み取りで返す | 読み取り(影響なし) | 存在は確定、契約の形は案 | 4.5 |
| ソース削除 1 | `POST /sources/{source_id}/deletions:discard` | Crawler | 終端状態でない削除結果を `discarded`(`source_deleted`)にする。`lock` は受け取るが所有を確認しない(3.2) | 冪等。削除専用の排他でソース削除を優先する(architecture K61)。試行の上限を超えたら再試行可能な 503(K61)。応答の時点の意味は architecture P29(案。実装で採用中) | 提案(`lock` の扱いは確定。architecture K60。排他による優先と、試行上限超過の 503 は確定。K61) | 4.6 |
| ソース削除 2 | `DELETE /sources/{source_id}/documents` | Crawler | 検索インデックスから `source_id` の文書を全削除(`delete_by_query` を再実行して消し切る。architecture K20、K28)。`lock` を JSON ボディで運び、所有を確認する(3.2) | 冪等(再送では 0 件でも成功。何度でも再実行できる)。再実行の上限を超えたら再試行可能な 503(K61) | 提案(`lock` の運び方・所有確認は確定。architecture K60。排他と、再実行の上限超過の 503 は確定。K61) | 4.7 |
| ソース削除 3 | `DELETE /sources/{source_id}/deletion-records` | Crawler | `loreley-deletions` の当該ソースの記録を削除。`lock` を JSON ボディで運び、所有を確認する(3.2) | 冪等(何度でも再実行できる) | 提案(`lock` の運び方・所有確認は確定。architecture K60) | 4.8 |

- Status API の利用者は Crawler。Admin View の削除結果の表示は、Admin API が `loreley-deletions` を直接読んで行い、`api` から `indexer` への通信は置かない。
- 文書の取得(`get_document`)は Search API が検索インデックスを ID で取得して行う。Indexer API にエンドポイントはない。
- 原本サイズ超過は独立した API ではなく、バッチ登録に関わる事項(4.9。Indexer も拒否することと、既存の文書を書き換えないことは確定。architecture K65)。
- `GET /healthz`(Crawler・Admin API の契約には含めない運用上のヘルスチェック。architecture K67。確定。ユーザー承認 2026-11-11(0002 §3 #21))。Indexer の起動時の整理(再起動前に受理した削除結果の `failed` 化。architecture 9.8)が終わるまでは、`/healthz` を含むすべてのパスが 503 `unavailable`(`retryable=true`)を返し、終わると `/healthz` は 200 `{"status": "ok"}` を返す。内部情報(版・設定・ログ)は返さない。実装上の 503 は `ready` ガードによる二重の防御で、実際には uvicorn がアプリケーションの起動完了まで接続自体を受け付けないため、外からは 503 ではなく**接続拒否に見える**(`apps/indexer/README.md` の 5 章)。Crawler が 503 と接続エラーの両方をリトライすること自体は Crawler 領域(案。3.4)。停止猶予・`HEALTHCHECK` の値は README を正とする。

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
- **認証なしの API を外部に公開しない**(architecture 2.4 の前提の明確化): Indexer API には認証・認可がない。ホストや外部のネットワークに公開せず、Crawler と同じ内部ネットワークからだけ到達できるようにする(待ち受けアドレスの既定はループバックで、コンテナでは公開ポートをホストのループバックに限る。運用は `apps/indexer/README.md` の 2 章)。到達できる呼び出し元は、`DELETE /sources/{source_id}/documents`(4.7)でソースの全文書を削除できる。`lock` の所有確認は、リクエストの `owner`・`job_id` をロック文書と照合するだけで、呼び出し元の認証ではない。ソース削除 1(4.6)は所有確認もしない。
- 契約は、将来 HTTP 部分をメッセージングに置き換えられるよう明確にする(重複して届いても安全であること、文書単位の結果が互いに依存しないこと)。
- 書き込み役は `indexer-architecture-v0.10.md` の責務表が正本。要点: 検索インデックスと `loreley-deletions`(仮名)に書くのは Indexer だけ。`loreley-jobs` に書くのは Crawler だけ。Admin API は書かず、読み取りのみで直接読む。
- 検索インデックスは、文書の本文・メタデータ・要約・処理状態・`last_seen_at` の唯一の正本である(architecture K18)。書き込みは PUT(Index API)を基本とし、`last_seen_at` だけの更新は Update API で行う(architecture K19)。

### 3.2 ロック所有情報の運び方(提案。`DELETE` の運び方・所有確認は確定)

- 書き込みを伴う要請(バッチ登録、`last_seen_at` 部分更新、ソース削除の順 1〜3)には、ロック所有情報 `lock`(`owner`、`job_id`)を添える。バッチ登録と `last_seen_at` 部分更新には、さらに `crawl_id`(= `job_id`)と `crawl_started_at` を**必須**で添え、受理条件の判定(下記。4.2、4.3。architecture K23)に使う。ソース削除の要請は開始通知を伴わず `deletion_result` を持たないため、別のエンドポイント(4.6〜4.8)で受け、この判定の対象外とする(`deletion_result` を要求しない。案)(提案)。
- **呼び出し種別の区別**(architecture K23): バッチ登録(`documents:batch`)と `last-seen` は `crawl_id`・`crawl_started_at` を必須とし、省略を許さない。省略できると、`crawl_id` を落とすだけで判定を回避できてしまうため。ソース削除は別のエンドポイントで区別する。
- **登録の受理条件**(architecture K23。確定): バッチ登録と `last_seen_at` 部分更新は、次をすべて満たすときだけ受理する。(1) `deletion_result-{crawl_id}` が存在する。(2) `source_id` が `deletion_result` のものと一致する。(3) `crawl_started_at` が複写値と一致する。(4) `status` が `running`。(5) `finish_received_at` が存在しない。(6) Crawler のロック所有確認に成功する。
  - 終端状態(`superseded` / `discarded` / `failed` / 判断済みの `deleted`・`skipped_by_ratio`・`validation_failed`)の `deletion_result` への登録は拒否する。終了通知の受理後(`finish_received_at` あり)の登録も拒否する。理由: 終了通知の受理後に登録すると、件数照合の前提(列挙の完了時点)が崩れ、終端状態の結果は旧世代の遅れた書き込みになるため。
  - 保持期間を超えて消えた `deletion_result` は「存在しない」として拒否する(消えた理由を区別しない)。
  - (1)〜(5) はリクエストの先頭で 1 回、(6) は文書ごとに確認する(下記の所有確認のとおり)。(6) の失敗は文書単位の `lock_not_owned`(3.4、API-U-13)で、リクエスト全体の拒否ではないため、拒否の 5 つの名称(`crawl_not_started`、`crawl_source_mismatch`、`crawl_started_at_mismatch`、`crawl_already_closed`、`crawl_finished`)には含めない。拒否の種類ごとにエラー名を分ける(3.4。API-U-19)。
- Indexer は書き込み前に、ロック文書(`loreley-jobs` の `lock-{source_id}`)を ID で取得し、要請したジョブの所有者で期限内であることを確認する。同じソースへのバッチ登録と `last_seen_at` 部分更新は、ソース単位で直列に処理する(architecture K67)。所有確認は文書ごとに行い、毎回ロック文書を取得し直す(確定。architecture K66。ユーザー承認 2026-11-11(0002 §3 #5))。ロック文書がない、リースが期限切れ、`owner` か `job_id` が不一致、のいずれも「所有していない」として扱う。ロック文書の形式(項目 `owner`・`job_id`・`lease_expires_at`)は設計書に定義がなく、Indexer の実装が仮に置いた(案。実装で採用中。Crawler 設計の確定時に再確認。API-U-23)。
- 確認できなければ書き込みを中止し、スキップ・リトライの対象にせずジョブ `failed`・削除しない(案)。文書単位の結果には `lock_not_owned` を返す(3.4)。
- **部分結果**(architecture K66。確定。ユーザー承認 2026-11-11(0002 §3 #5)。API-U-13): バッチ登録と `last_seen_at` 部分更新の途中でロックを失ったときは、確認済みの文書の結果をそのまま返し、最初の失敗以降の未処理の文書も、書かずに `lock_not_owned` とする(一度失敗したら、以降の文書では確認し直さない)。リクエスト全体は HTTP 200 で、全体の 409 にはしない。バッチの先頭で失敗した場合も、すべての文書が `lock_not_owned` の 200 になる。
- 確認と書き込みの間の窓は MVP では既知の制限として許容する。確認の対象は登録と `last_seen_at` の更新。要約の書き込みと削除の実行は対象外。
- ソース削除の順 2・3(4.7・4.8)には、ジョブがロックを最後まで保持する(architecture K29)ので、ロック所有情報を添え、Indexer が所有を確認する(次の項目)。Crawler 側のロック設計の具体は Crawler 設計で決める(API-U-14)。
- **ソース削除の `lock` の運び方と所有確認**(architecture K60。確定。ユーザー承認 2026-11-11(0002 §3 #8)・2026-11-12(0021 §1)。API-U-14 の Indexer 側): `lock` は **JSON ボディ**で運ぶ。`DELETE`(順 2・3)も同じで、ボディは `{"lock": {"owner": "...", "job_id": "..."}}`。ヘッダやクエリでは運ばない。順 2・3 は `lock` が必須で、ボディがない・`lock` が欠けているときは 400 `invalid_request`。所有を確認できなければ、何も書かずに 409 `lock_not_owned`(`retryable=false`。リクエスト全体のエラーで、登録・`last-seen` の文書単位の `lock_not_owned` とは別。3.4)。順 1(`POST`。ボディは `{"lock": {...}, "reason": "source_deleted"}`。`reason` は任意で、値は `source_deleted` だけ)も `lock` は必須項目だが、所有は確認しない(応答待ちの間にリースが切れても再実行を妨げないため。4.6)。**Crawler との突き合わせが必要**(architecture U-34。API-U-23): Crawler の HTTP クライアントが `DELETE` にボディを載せられること。

### 3.3 ID と入力の検証規則

- `document_id` = `SHA-256(source_id + "\0" + external_id)` の 16 進文字列(小文字)。NUL 文字で区切る。
- `external_id` は、ハッシュの前に Unicode NFC へ正規化し、パス区切りを `/` に統一する(ルートからの相対パス、先頭に `/` を付けない)。大文字小文字は区別したまま扱う。
- 同じ文書を再取得すると同じ ID になるため、再実行しても重複しない。検索インデックスは `document_id` を文書 ID(`_id`)として使う。
- `source_id` は登録後に変更できない。パスの変更・リネームは「旧 ID の削除 + 新 ID の追加」として扱う(リネームの追跡は初期要件にしない)。
- `crawl_id` は Crawler のジョブ ID をそのまま使う(Indexer は採番しない)。
- **`external_id` の先頭の `/`**(architecture K58。確定。ユーザー承認 2026-11-12(0021 §1)): 「先頭に `/` を付けない」は Crawler が渡す値の前提で、Indexer が除去する規則ではない。Indexer は先頭の `/` を除去しない(`/a` と `a` は別の `document_id` になる)。`last_seen_at` 部分更新は Crawler が算出した `document_id` をそのまま受けるため、Indexer だけが除去すると、同じ文書の ID が Crawler と食い違う。**Crawler との突き合わせが必要**(architecture U-34。API-U-23): Crawler が、上記の規則(NFC、パス区切りの `/` への統一、先頭の `/` は除去しない)で `document_id` を算出していること。4.3 の応答例の `document_id` は、`source_id` が `src-docs` のとき `external_id` の `page-10023`・`page-10024`・`page-10025` から上記の規則で算出した値で、算出の一致の確認に使える(共有のテストベクタの採否は API-U-7 で未決)。

#### 入力の検証規則(architecture K59。確定。ユーザー承認 2026-11-11(0002 §3 #7、#14、#22)・2026-11-12(0021 §1・§2))

Indexer が受ける JSON の検証の規則。違反は、リクエスト全体の 400 `invalid_request`(3.4)で、応答には位置(項目名と配列の添字)と検証の種別だけを示し、入力の値は含めない。上限の値は設計書に書かない(設定で変えられる。値は `apps/indexer/README.md` の 3 章)。

| 対象 | 規則 |
| --- | --- |
| ボディ | UTF-8 の JSON であること。JSON でない、`NaN`・`Infinity` のような JSON にない定数を含む、送信途中で切れて読み切れない、`Content-Length` が不正、は 400 |
| 型 | 厳密(strict)。数値・真偽値を文字列などから黙って変換しない(例: `ttl` が小数、`rewrite_mode` が `"true"` や `1` は 400)。`ttl`・`min_delete_count`・`enumerated_count`・`size` は整数、`ratio_threshold` は有限の数値、`force_delete`・`rewrite_mode` は真偽値。値の**意味上の範囲は検証しない**(`ttl` の 0・負値、`ratio_threshold` の範囲、`min_delete_count` の極端な値も受理する。確定事項。architecture 9.3、9.13(9))。検証するのは型と、整数の 64 ビットの範囲(`enumerated_count`・`size` は 0 以上。64 ビットの範囲は検証の規則として実装が置いた仮値) |
| 日時 | タイムゾーン付きの ISO 8601(3.6)。オフセットのないものは 400 |
| 未知の項目 | 無視する(保存せず、エラーにしない。`fetched_at`・`metadata` を含む。4.3) |
| `source_id`・`crawl_id`・`lock.owner`・`lock.job_id`(パスの `source_id`・`crawl_id` を含む) | 空文字、制御文字(0x00〜0x1f、0x7f。改行・タブを含む)、UTF-8 で 256 バイトを超えるものは 400。256 バイトは検証の規則としての仮値(設計書に規定がなく、実装が置いた)。制御文字を拒否するのは、ログに偽の行を注入されないため |
| `external_id` | 空文字、UTF-8 で 4096 バイトを超えるもの、NUL を含むものは 400(位置つき)。NUL 以外の制御文字(改行・タブ)は許可する(Linux のファイル名として正当で、1 件のためにバッチ全体が恒久的に 400 にならないように)。4096 バイトは検証の規則としての仮値 |
| `content_hash` | 小文字 64 桁の 16 進だけ(大文字は 400)。Indexer は再計算も照合もしない(4.3) |
| ID 一覧の要素(`last-seen` の `document_ids`、終了通知の `skipped_document_ids`・`oversize_document_ids`) | 小文字 64 桁の 16 進。1 つでも違えば 400 |
| 孤立サロゲート(JSON の `\ud800` など。Linux で CP932 のファイル名を読むと生じうる) | `title`・`mime_type`・`path`・`url` に入ると、その文書だけ文書単位の `document_rejected`(4.3)。それ以外の文字列(`external_id`・ID 類・`content_hash`・日時・`raw_content` など)に入ると、リクエスト全体の 400(再送しても直らない)。**Crawler との突き合わせが必要**(architecture U-34。API-U-23): Crawler が事前に除く、または置き換えること |
| `skipped_count`(終了通知) | 必須にしない。型(非負整数)だけを検証し、値は使わない(`skipped_document_ids` の件数との一致も検証しない。4.4) |
| サイズ・件数の上限 | バッチの件数、デコード後の合計サイズ、リクエストボディのサイズ、`last-seen` の `document_ids` の件数には上限がある(4.2、4.3)。超過は 413 ではなく、リクエスト全体の 400 `invalid_request`(architecture K59。API-U-6 の一部) |
| 起動前 | 起動時の整理が終わるまで、`/healthz` を含むすべてのパスが 503 `unavailable`(`retryable=true`)。外からは接続拒否に見える(1章)。Crawler が 503 と接続エラーの両方をリトライすること自体は Crawler 領域(案。3.4) |

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
| 400 | `invalid_request` | リクエストの形式不正(3.3 の「入力の検証規則」。サイズ・件数の上限超過を含む。413 は使わない) | ジョブ `failed` |
| 404 | `crawl_not_found` | Status API の 404 条件(4.5) | ポーリングの失敗(第 5 章) |
| 404 | `not_found`(案。実装で採用中) | 未定義のパス | (契約外の呼び出し) |
| 405 | `method_not_allowed`(案。実装で採用中) | 未定義のメソッド | (契約外の呼び出し) |
| 404・405 以外の HTTP エラー | `http_error`(案。実装で採用中) | 上記以外の HTTP 例外(HTTP ステータスはそのまま返す) | (契約外の呼び出し) |
| 409 | `crawl_already_finished` / `stale_crawl_started_at` | 開始通知の 409(順 1・3。4.1) | ジョブ `failed` |
| 409 | `crawl_start_conflict` | 開始通知の再送で、同じ `crawl_id` の複写済み項目と内容が一致しない(4.1 の順 2。architecture K24、K66) | ジョブ `failed` |
| 409 | `crawl_not_started` | `deletion_result-{crawl_id}` が存在しない(開始通知の未送信、保持期間超過での消去、`loreley-deletions` の喪失。4.2、4.3。architecture K23、K66) | リトライせずジョブ `failed` |
| 409 | `crawl_source_mismatch` | `source_id` が `deletion_result` のものと一致しない(4.2、4.3。architecture K66) | リトライせずジョブ `failed` |
| 409 | `crawl_started_at_mismatch` | バッチ登録・`last-seen` 部分更新の `crawl_started_at` が、`deletion_result-{crawl_id}` の複写値と一致しない(4.2、4.3。architecture K66) | リトライせずジョブ `failed` |
| 409 | `crawl_already_closed` | `deletion_result` が終端状態(`superseded` / `discarded` / `failed` / `deleted` / `skipped_by_ratio` / `validation_failed`。4.2、4.3。architecture K66) | リトライせずジョブ `failed` |
| 409 | `crawl_finished` | `deletion_result` が `running` だが、終了通知を受理済み(`finish_received_at` あり。4.2、4.3。architecture K66) | リトライせずジョブ `failed` |
| 409 | `finish_content_mismatch` | 終了通知の再送で、内容が最初に受理した内容と異なる(4.4。architecture K25、K40) | ジョブ `failed`(案) |
| 409 | `finish_source_mismatch` | 終了通知の `source_id` が `deletion_result` のものと一致しない(4.4。architecture K32、K40) | リトライせずジョブ `failed`(案) |
| 409 | `lock_not_owned` | ソース削除 2・3 のロック不所有(リクエスト全体のエラー。何も書かない。4.7、4.8。architecture K60) | リトライせずジョブ `failed`(案) |
| 500 | `internal_error`(`retryable=false`) | 想定外の異常(下位システムの想定外の応答、不正な記録、想定外の例外)。本文は固定文で、原因の詳細は返さない | リトライ、直らなければジョブ `failed`(案) |
| 503 | `unavailable`(`retryable=true`) | OpenSearch の全体異常、受理の書き込みの競合が読み直しの上限を超えた(4.1、4.4)、ソース削除の試行・再実行の上限超過(4.6、4.7。architecture K61)、起動時の整理が終わるまで(1章。外からは接続拒否に見える) | リトライ、直らなければジョブ `failed` |
| 接続エラー / タイムアウト | — | Indexer に届かない(起動前の接続拒否を含む。1章) | リトライ、直らなければジョブ `failed` |

- 上表の区分: `finish_content_mismatch` と `finish_source_mismatch` のエラー名と 409 は確定(architecture K40)。v0.10 で、`crawl_start_conflict`、`crawl_not_started` から `crawl_finished` までの 5 件、`crawl_already_finished`、`stale_crawl_started_at`、`crawl_not_found`、`lock_not_owned`、`internal_error`、`unavailable` のコード名と HTTP も、実装で採用し、ユーザーが承認したため確定(architecture K66、K60。ユーザー承認 2026-11-11(0002 §3 #15)・2026-11-12(0021 §1)。API-U-19、API-U-20)。`retryable` は、実装では `unavailable` だけが `true` で、ほかは `false`。`not_found`・`method_not_allowed`・`http_error` は実装が割り当てた名前で、承認の記録がなく案のまま(実装で採用中)。最右列の Crawler の扱い(ジョブ `failed` など)は Crawler 設計の領域で、案のまま(ユーザー未確認)。
- 上表の 409 は、Crawler と Indexer の間の応答である。検索インデックスへの書き込みで起きる 409(`if_seq_no` / `if_primary_term` の不一致、`op_type=create` の競合)は Indexer の内部で読み直して再判定し(4.3)、そのまま Crawler への HTTP 409 にはしない。
- 開始通知の `crawl_already_finished`(4.1)と登録の `crawl_already_closed`(4.2、4.3)は、開始通知用と登録用の意図的な区別とし、実装も別名で返す(確定。architecture K66。API-U-19)。
- 終了通知の再送は、同じ内容なら冪等な 202、最初に受理した内容と異なれば 409(`finish_content_mismatch`。4.4、architecture K25、K40)。終了通知の `source_id` の不一致も 409(`finish_source_mismatch`。4.4、architecture K32、K40)。この 2 つの 409 は上記の共通エラー形式で、コードと短いメッセージだけを返す。最初に受理した終了通知の全文・ダイジェスト・受理済みの状態の詳細は返さず、Status API(4.5)で確認する(architecture K43)。開始通知の 409 と、上表の登録の拒否(`crawl_not_started` から `crawl_finished` までの 5 件。拒否そのものは architecture K23 で確定し、コード名・HTTP は K66 で確定。API-U-19)と、終了通知の 409 は、上表のとおり。上表のほかに、個別のコード名を割り当てたエラーはない。`retryable` は Crawler のリトライ判断に使う補助で、必須ではない。
- **`lock_not_owned`**(architecture K66、K60。確定。API-U-13): 登録・`last_seen_at` 部分更新の所有確認は文書ごとに行うので、リクエスト全体の 409 にせず、文書単位の結果に `failure_type: lock_not_owned`(4.2 は `result: lock_not_owned`)を返す。バッチの途中でロックを失った場合の部分結果は 3.2 のとおり(確認済みの結果を返し、最初の失敗以降の未処理の文書も `lock_not_owned`。リクエスト全体は 200)。Crawler はそれをスキップ・リトライの対象にせずジョブ `failed` として扱う(案)。ソース削除 2・3 は、リクエスト全体の 409 `lock_not_owned`(上表)。

### 3.5 冪等性・リトライ方針

- 全 API は重複して届いても結果が変わらない(Status API は読み取り)。再送は安全。
- **登録の失敗の扱い**(バッチ登録、`last_seen_at` 部分更新):
  - 検索インデックスへの登録失敗は、Indexer が文書単位の失敗種別を返し、Crawler が最大試行回数までリトライして、それでも失敗したら、**文書固有の拒否に限り**スキップ(下記の 2 つ目の項目)。文書固有でない失敗(書き込みの競合、OpenSearch 全体の異常など)はスキップせず、下記のとおりジョブ `failed` にする。リトライは Crawler 側の既定値(最大 3 回、バックオフは初回 1 秒・2 倍・上限 30 秒・ジッタあり。いずれも案)。
  - スキップの対象は**文書固有の拒否**(マッピング違反、文書の内容に起因する 4xx など)だけ。文書固有の 4xx のスキップが連続 20 件(案。設定可能)に達したら `failed`。この連続 20 件の打ち切りは Crawler 側の規則で、Indexer は `document_rejected` の連続を数えず、打ち切りもしない(ユーザー承認 2026-11-12(0021 §1))。
  - 接続エラー、タイムアウト、HTTP 429、5xx、`cluster_block_exception`、circuit breaker は OpenSearch 全体の異常として、スキップせずジョブ `failed`。Indexer の異常(接続不可、タイムアウト、5xx 等)も同様で、リトライしても直らなければジョブ `failed`。Indexer は OpenSearch 全体の異常を文書単位の失敗にせず、リクエスト全体の 503 `unavailable`(`retryable=true`)で返す(4.3。`store_error` という失敗種別は返さない)。リトライ回数・連続 20 件・エラー種別・`failed` の対象範囲の細部は案。
  - 終了通知が Indexer に受理される前にクロールが失敗した場合は、削除しない。受理された後は、応答喪失などで Crawler 側のジョブが失敗扱いになっても削除処理が継続しうる(確定。architecture K12。4.4)。
  - ジョブ `failed` の対象は、開始通知、登録、`last_seen_at` の部分更新、終了通知の失敗に限る。Status API のポーリングの失敗は含まない。`last_seen_at` を保存できなければクロールを完了扱いにしない、は案(ユーザー未確認)。
  - 抽出の失敗はスキップではなく `extract_failed`(タイトルとメタデータを登録)として扱い、リトライしない。
  - 検索インデックスへの書き込みの競合(409)は文書固有の拒否ではないので、上記のスキップの対象に含めない。Indexer が文書を読み直して再判定し、読み直しの上限を超えたときだけ文書単位の失敗(`write_conflict`)として返す(4.3。上限の値は architecture U-31)。Crawler は上限付きでリトライし、解消しなければジョブ `failed` にして期限削除を行わない。この競合を文書固有のスキップの対象にしないこと、上限付きリトライで解消しなければジョブ `failed` にすること、期限削除を行わないことは確定(architecture K51)。連続 20 件の計数に含めないことは、K51 からの導出(案。ユーザー未確認)で、連続 20 件そのものも案のままである。`last_seen_at` の Update の競合上限超過(`update_conflict`。4.2、4.3 (b))も同じ扱いである(architecture K51)。`last_seen_at` を保存できないまま(要請の失敗が解消しないまま)クロールを完了扱いにはしない(本節の上記の案)。
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
| `ttl` | integer | ○ | 設定スナップショット。整数の秒(確定。architecture K59。ユーザー承認 2026-11-11(0002 §3 #14))。範囲は検証しない(0・負値も受理。3.3)。既定値は未決(architecture U-1) |
| `ratio_threshold` | number | ○ | 設定スナップショット。有限の数値(小数。整数も可。確定。K59)。範囲は検証しない(3.3) |
| `min_delete_count` | integer | ○ | 設定スナップショット。整数(確定。K59)。範囲は検証しない(3.3) |
| `force_delete` | boolean | 任意(既定 `false`) | 削除結果の `forced` として複写して持つ値そのもの。別の項目は重ねない。厳密な真偽値(`"true"` や `1` は 400。3.3) |
| `rewrite_mode` | boolean | 任意。省略は `false` と同じ意味で、`false` に正規化して複写する(architecture K37) | 再書き込みモード(採用は architecture K26、開始通知の任意項目とすることは K41 で確定)。`true` のとき、このクロールのバッチ登録は、変更なしの判定(4.3 の (b))をせず、本文ごと全文書き込みし、要約は引き継がず `pending` に戻す。削除の判断には影響しない。手動実行のクロールの起動時のみ指定できる想定。設定スナップショットの一部として `deletion_result` に保持し、バッチ登録は受理条件の確認で取得した `deletion_result` から参照する(architecture K33) |

必須/任意は内容の列挙に基づく(案)。下の例の `ttl`・`ratio_threshold`・`min_delete_count` は、値が未決のため `"<値は未決>"` と書く(architecture U-1。v0.9 と同じ)。`rewrite_mode` も `force_delete` と同じ厳密な真偽値(K59)。

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

**レスポンス**(成功。ボディは未定義で、空でもよい。案。実装は 200 で下記のボディを返す):

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
| 409 | `crawl_already_finished` | `deletion_result-{crawl_id}` がすでに終端状態(終了したクロールの通知が再送されても `running` に戻さない) |
| 409 | `crawl_start_conflict` | 同じ `crawl_id` で `running` の再送が、複写済みの項目(`source_id`、`crawl_started_at`、`ttl`、`ratio_threshold`、`min_delete_count`、`force_delete`、`rewrite_mode`)のどれかと一致しない(`rewrite_mode` は `false` に正規化した値で比べる。architecture K24、K33、K37、K66)。状態は変えない |
| 409 | `stale_crawl_started_at` | `crawl_started_at` が現行世代のそれより古い(世代の巻き戻り防止) |
| 400 | `invalid_request` | リクエストの形式不正(型の不一致を含む。3.3) |
| 503 | `unavailable`(`retryable=true`) | OpenSearch の全体異常。または、世代・結果の書き込みの競合(409)が読み直しの上限を超えた(案。実装で採用中。0020 §6-2(0021 で全て承認))。結果を作らずに止まる(世代の更新まで済んでいることがある)再試行可能な 503 で、結果の作成が最後の書き込みなので、再送は最初から判定し直して収束する(architecture K57) |
| 500 | `internal_error`(`retryable=false`) | Indexer の想定外の異常(3.4)。リトライし、直らなければジョブ `failed` |
| 接続エラー / タイムアウト | — | Indexer に届かない(起動前の接続拒否を含む。1章)。リトライし、直らなければジョブ `failed` |

- 判定の順序: (1) 終端状態なら 409(`crawl_already_finished`)→ (2) 同じ `crawl_id` で `running` なら、複写済みの項目と今回のリクエストを直接比較し、すべて一致すれば状態を変えずに成功(再送)、1 つでも不一致なら状態を変えずに 409(`crawl_start_conflict`)→ (3) 世代が古ければ 409(`stale_crawl_started_at`)。
- Crawler は 409 をジョブ `failed` として扱う。

**冪等性・注意事項**:

- **再送の一致検証**(architecture K24。確定): 同じ `crawl_id` で削除結果が `running` のときは、内容を見ずに成功にせず、`deletion_result-{crawl_id}` に複写済みの項目と今回のリクエストを直接比較する。比較するのは `source_id`、`crawl_started_at`、`ttl`、`ratio_threshold`、`min_delete_count`、`force_delete`(省略時は `false` として複写値の `forced` と比べる)、`rewrite_mode`(省略は `false` に正規化した値で比べ、省略と `false` の違いでは 409 にしない。architecture K33、K37。確定)。比較は正規化後の値で行う(architecture K59、K66): `crawl_started_at` は 3.6 のミリ秒精度の UTC に揃えて比べ(表記の違いでは 409 にしない)、`ratio_threshold` は数値として比べる(整数 `1` と小数 `1.0` は同じ値)。`ttl`・`min_delete_count` は整数、`force_delete`・`rewrite_mode` は真偽値の一致。すべて一致なら成功(冪等。状態不変)、不一致なら 409 `crawl_start_conflict`(状態不変)。現行世代 `deletion-{source_id}` は新しい開始通知で上書きされるため、比較には使わない。`rewrite_mode` の省略と `false` は同じ値として扱う(architecture K37)。
- **Crawler の義務**(Crawler 設計への要件。architecture K24 の検証が成り立つための前提): Crawler は、最初に組み立てた設定スナップショット(`crawl_started_at`、`ttl`、`ratio_threshold`、`min_delete_count`、`force_delete`、`rewrite_mode`)をジョブごとに保持し、開始通知の再送では同一の値を送る。再送のたびに設定を読み直すと、設定変更が間に入った場合に値が変わり、`crawl_start_conflict`(409)になってジョブが `failed` になる(設定を途中で変えたことの検出としては意図どおりだが、Crawler が値を固定していれば起きない)。`ttl` などの値の型は確定したため(3.3)、比較は上記の正規化後の値で行う(API-U-20)。
- **即時の受理**: 旧い削除が待機中・判定中・実行中でも待たせず、すぐに受理する。
- **Indexer の動作**(判定を通ったとき。書き込みの順は architecture K57。確定。ユーザー承認 2026-11-12(0021 §1)): 次の順に書く(以下「書き込みの (1)〜(3)」)。(1) `deletion-{source_id}`(現行世代。用途は開始通知の世代判定と直近の開始通知の記録)を更新する。(2) 同じソースに、`finish_received_at` の無い `running` の旧い削除結果(終了通知が届かなかった世代)があれば `discarded`(理由 `superseded`)にする。`finish_received_at` のある結果には何もしない。(3) `deletion_result-{crawl_id}` を設定スナップショット(`rewrite_mode` を含む)の複写つきで `running` で作る(複写は案。`rewrite_mode` の複写は architecture K33 で確定)。判定と実行は複写した値を使い、`deletion-{source_id}` からは読まない。
- **結果の作成を最後の書き込み(コミット点)にする理由と、再送時の収束**(architecture K57): 再送の判定(上の「判定の順序」の (1)(2))は、`deletion_result-{crawl_id}` がすでにあることを根拠にする。結果の作成を先にすると、書き込みの (1)(2) の途中で失敗したあとの再送が「結果がある=成功」と判定され、世代の更新と旧い結果の整理が行われないままになる。結果の作成を最後にすれば、途中で失敗しても結果はまだなく、再送は書き込みの (1) から実行し直して収束する(同じ `crawl_started_at` は古い世代とみなさない)。
- 通知の失敗(リトライ設定の回数まで試しても直らない場合)はジョブ `failed`。開始通知の失敗は、削除が行われないだけで安全。

**確認状況**: 開始通知の存在は確定。エンドポイント形、キー名、設定スナップショットの複写は案(実装で採用中)。再送の一致検証は確定(architecture K24)。再書き込みモードの採用は確定(architecture K26)。`rewrite_mode` の `deletion_result` への保持と再送の一致検証の比較項目への追加は architecture K33、開始通知の任意項目とすること(名称 `rewrite_mode`)は K41、省略を `false` に正規化することは K37 で確定。v0.10 で確定: 書き込みの順(architecture K57)、`ttl`・`ratio_threshold`・`min_delete_count`・`force_delete`・`rewrite_mode` の型と、再送の比較を正規化後の値で行うこと(K59)、409 のコード名(`crawl_start_conflict` を含む)と HTTP(K66。API-U-19、API-U-20)。承認: 2026-11-11(0002 §3 #14、#15)・2026-11-12(0021 §1)。未決: API-U-1(項目名)、API-U-12(409 条件)、API-U-5(設定値)。

### 4.2 `last_seen_at` の部分更新(提案)

**概要**: Crawler が列挙で見つけたすべての文書について、**取得より前に**要請する。Indexer は Update API のスクリプトで現在値と max 比較し、新しい値のときだけ `last_seen_at` を書く(現在値以上なら noop)。ほかのフィールドは変更しない。文書がなければ(`not_found`)何もしない(upsert しない)。`not_found` にするのは、検索インデックスの 404 のうち `document_missing_exception`(文書がない)のときだけ。`index_not_found_exception` などインデックス不在・設定の異常は文書がないこととは別なので、`not_found` にせず OpenSearch 全体の異常(503 `unavailable`)として扱う(確定。architecture K66。ユーザー承認 2026-11-11(0002 §3 #6))。取得・抽出・登録が失敗しても更新済みのまま残るので、取得に失敗してスキップした文書が TTL で誤削除されない。書き込みの前に、登録の受理条件(3.2。`crawl_started_at` が `deletion_result-{crawl_id}` に複写された値と一致することを含む)を判定する(architecture K23)。

**エンドポイント**: `POST /sources/{source_id}/last-seen`(案)

**呼び出し元**: Crawler(列挙で見つかった文書。取得より前)

**リクエスト**: 要請する単位は、Crawler が算出した `document_id`(小文字 64 桁の 16 進)の配列(確定。architecture K66。ユーザー承認 2026-11-11(0002 §3 #6)。API-U-7)。バッチ登録では Indexer が `document_id` を算出して返すのに対し、ここでは Crawler が 3.3 の規則で算出して渡す(非対称)。`external_id` の配列を渡して Indexer が算出する形は採らない。

| 名前 | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `source_id`(パス) | string | ○ | データソース ID |
| `crawl_id` | string | ○ | クロール ID(= `job_id`)。必須で、省略できない(3.2) |
| `lock` | object(`owner`, `job_id`) | ○ | ロック所有情報(3.2) |
| `crawl_started_at` | datetime | ○ | 書き込む値。`deletion_result-{crawl_id}` の複写値と一致している必要がある(下記) |
| `document_ids` | string[] | ○ | 3.3 の規則で Crawler が算出した ID(小文字 64 桁の 16 進)。件数に上限があり(設定 `max_last_seen_ids`。値は `apps/indexer/README.md` の 3 章)、超えると全体 400 `invalid_request`。分割して送る。空配列は受理し、`results` は空配列(受理条件の判定は行う。バッチ登録の `documents` が空なら 400。案。実装で採用中) |

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
- `update_conflict`(architecture K51): Update が `retry_on_conflict` の回数を超えて 409 になった文書(文書単位の失敗。再試行可能)。成功扱いにしない。Crawler は上限付きでリトライし、解消しなければジョブ `failed` にして期限削除を行わない(文書固有のスキップの対象にしない。3.5)。文書単位の失敗で、リクエスト全体の失敗にはしない(確定。architecture K66。API-U-7)。
- `lock_not_owned`: 所有確認に失敗した文書(確定。architecture K66)。最初の失敗以降の未処理の文書も、書かずに `lock_not_owned` とする(3.2)。成功扱いではなくジョブ `failed`(案。3.4)。
- **用語の区別**: ここでの `unchanged` は「`last_seen_at` を書かなかった(現在値以上)」の意味で、文書の内容は関係しない。4.3 の `change: unchanged`(変更がなく全文書き込みをしなかった)とは別の概念。

**エラー**:

| ステータス | コード(提案) | 条件 |
| --- | --- | --- |
| 400 | `invalid_request` | リクエストの形式不正(`document_ids` の件数超過・ID の形式不正を含む。3.3) |
| 409 | `crawl_not_started` | `deletion_result-{crawl_id}` が存在しない(開始通知の未送信、保持期間超過での消去、`loreley-deletions` の喪失)。書き込まずに拒否し、リトライせず Crawler はジョブ `failed`(案) |
| 409 | `crawl_source_mismatch` | `source_id` が `deletion_result` のものと一致しない |
| 409 | `crawl_started_at_mismatch` | `crawl_started_at` が複写値と一致しない。リクエスト全体のエラー(文書単位の結果は返さない)。リトライせず Crawler はジョブ `failed`(案) |
| 409 | `crawl_already_closed` | `deletion_result` が終端状態(`superseded` / `discarded` / `failed` / `deleted` / `skipped_by_ratio` / `validation_failed`) |
| 409 | `crawl_finished` | `deletion_result` が `running` だが終了通知を受理済み(`finish_received_at` あり) |
| 503 | `unavailable`(`retryable=true`) | 書き込み不可(OpenSearch への書き込み失敗、インデックス不在など。文書がないこと(`document_missing_exception`)は含まない)。Crawler はジョブ `failed`・削除しない |

**冪等性・注意事項**:

- 重複して届いても結果は変わらない(max 比較。architecture K27。確定)。確認と書き込みの間の窓は既知の制限(3.2)。
- `last_seen_at` の Update は、検索インデックスの内部で文書全体を再インデックスするため、列挙したすべての文書で発生する。この負荷(処理時間・インデックスサイズ・マージ負荷)は architecture 15.4 の測定項目に含まれる(設計は変えない)。
- Update API の内部の競合は `retry_on_conflict` で再試行する(値は未決。実機確認。architecture U-31)。再試行を超えて 409 になった文書は、文書単位の `result: update_conflict` として返す。登録や要約の書き戻しの PUT と並行しても、互いの内容を失わない(architecture 5章)。
- **受理条件の判定**(architecture K23。確定): 3.2 の受理条件の (1)〜(5) を、所有確認や文書ごとの処理より前に 1 回だけ判定する。満たさなければリクエスト全体をエラーにして何も書かない(文書単位の結果は返さない)。(6) のロック所有確認は文書ごとで、失敗は文書単位の `result: lock_not_owned`(API-U-13。上記 5 つの拒否名には含めない)。
- **`crawl_started_at` の照合の目的**: 誤った `crawl_started_at` で `last_seen_at` を書くと、件数照合や TTL 判定の基準がずれる。Crawler の取り違えを早く検出する。照合しなくても削除は安全側(件数照合の不一致で削除されない)に倒れるが、誤りの検出が遅れる。
- 対象は通常クロールの `last_seen_at` 部分更新(バッチ登録も同じ)に限る。ソース削除の要請は別のエンドポイント(4.6〜4.8)で、`deletion_result` を要求しない。
- 終端状態の `deletion_result`、終了通知の受理後の `deletion_result`(`finish_received_at` あり)は、`crawl_started_at` が一致していても拒否する。保持期間超過で消えた `deletion_result` は存在しないものとして拒否する(エラー名は `crawl_not_started`。architecture K66)。Crawler は開始通知を送り直さずジョブ `failed` とする(クロールの途中で世代の前提を失っているため。案)。

**確認状況**: 提案(案。下記の確定部分を除く)。`last_seen_at` を検索インデックスの文書に持ち、`crawl_started_at` を渡して Indexer が書くことは確定。`last_seen_at` だけの更新を Update API で行うことは architecture K19 で確定。max 比較のスクリプト、文書なし(404)・競合(409)の扱いは architecture K27 で確定。`update_conflict` の名称と Crawler の扱いは architecture K51 で確定、`retry_on_conflict` の値は未決(architecture U-31)。受理条件の判定(`crawl_started_at` の照合、終端状態・受理後の拒否、`crawl_id` の必須化)は architecture K23 で確定。エラー名・HTTP は K66 で確定(API-U-19)。要請の単位と `document_id` の算出主体(Crawler)、`update_conflict` が文書単位であること、インデックス全体の異常が 503 であること、ロック失敗時の返し方(確認済みの結果を返し、最初の失敗以降の未処理の文書も `lock_not_owned`)は、architecture K66 で確定(API-U-7、API-U-13。ユーザー承認 2026-11-11(0002 §3 #5、#6))。

### 4.3 バッチ登録(提案)

**概要**: 文書を同期 HTTP で登録する。応答は文書単位で、失敗した文書だけを再送できる。新規・更新・変更なしの区分も含める(確定。architecture K50)。受理条件は 3.2、4.2 と同じ。集計して `loreley-jobs` に記録するのは Crawler。Indexer の登録処理(抽出、検索インデックスとの比較、書き込み、競合時の読み直し)は `indexer-architecture-v0.10.md` の 4.3 と 5章を参照。

Indexer が文書ごとに行う書き込みは、次のとおり(architecture 4.3、K27。確定。変更のない文書を PUT しないこと、変更なしの文書の `last_seen_at` を補う Update、max 比較を含む)。

1. 抽出・正規化したあと、検索インデックスから文書を ID で取得する(GET)。
2. 次のいずれかになる。
   - (a) **文書がない(新規)**: 全フィールドを組み立て、`op_type=create` の PUT で書く(`change: created`)。
   - (b) **文書があり、`content_hash`・`text_hash`・`index_status`・メタデータ(`title`、`source_updated_at`、`mime_type`、`size`、`url`、`path`)がすべて同じ**: 書かない。要約も更新しない(日時は 3.6 の正規化後の値で比べる)。`last_seen_at` が `crawl_started_at` より古ければ、`last_seen_at` だけを Update で補う(`change: unchanged`)。この補完は、4.2 の要請がすでに成功していれば不要(`last_seen_at` は `crawl_started_at` 以上になっている)で、4.2 が失敗・省略された場合にだけ補う(architecture K27。確定)。補完の Update が `retry_on_conflict` を超えて 409 になったときは、その文書の失敗として `update_conflict`(4.2 と同じ)を返す。
   - (c) **文書があり、いずれかが違う**(再書き込みモード(4.1。受理条件の確認で取得した `deletion_result` の `rewrite_mode` による。architecture K33)のときは、(b) の判定をせず、常にここへ進む。要約は引き継がず `pending` に戻す): 読んだ `_seq_no` / `_primary_term` を `if_seq_no` / `if_primary_term` に付けて全体を PUT する(`change: updated`)。メタデータだけが変わった場合(`content_hash` と `text_hash` が同じ)は、要約を引き継ぐ。本文が変わった場合は要約を `pending` に戻す。例外として、抽出に失敗して `extract_failed` になる書き込みは、`content`・`text_hash`・`summary` を書かず `summary_status=disabled` とする。`summary_model` も書かず、`content_hash` は新しい値を書く(architecture K30、E-45。旧い値は置き換えで消える)。
3. PUT が 409(読んだあとに別の書き込みが先に入った)なら、手順 1 から読み直して再判定する。読み直しの回数がリトライ設定の回数を超えたら、文書単位の失敗(再試行可能)として返す(上限の値は architecture U-31)。

**エンドポイント**: `POST /sources/{source_id}/documents:batch`(案)

**呼び出し元**: Crawler(取得・抽出対象の文書ごと)

**リクエスト**: `raw_content` は JSON で運ぶため base64 とする(提案。実装で採用中。標準の base64 でパディングあり・改行なし。不正なら全体 400。上限と運び方の最終形は未決)。base64 は原本より約 33% 大きくなり、JSON の解析と複写でメモリも使う。運び方は multipart(原本をバイナリのまま送る)や文書ごとの個別送信などの選択肢を残す(案。API-U-17。実測項目は architecture 15.4)。`document_id` は Indexer が 3.3 の規則で算出して返す(Crawler が付けた値との照合はしない提案)。

| 名前 | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `source_id`(パス) | string | ○ | データソース ID |
| `crawl_id` | string | ○ | クロール ID(= `job_id`) |
| `crawl_started_at` | datetime | ○ | クロールの開始時刻。Indexer が `last_seen_at` に書く値(4.2 と同じ値)。`deletion_result-{crawl_id}` の複写値と一致している必要がある(下記)。`crawl_id` とともに必須で、省略できない(3.2) |
| `lock` | object(`owner`, `job_id`) | ○ | ロック所有情報(3.2) |
| `documents[]` | object[] | ○ | 登録する文書(要素の項目は下表)。空は 400。件数・デコード後の合計サイズ・リクエストボディのサイズに上限がある(下記「サイズの防御」。値は未決(API-U-6)で、仮値は設定として管理する) |

`documents[]` の要素(Connector(Crawler)が Indexer に渡す文書。項目名・型は案。`source_id` はパスから取るため要素には含めない):

| 名前 | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `external_id` | string | ○ | データソース内で一意な識別子(ルートからの相対パス、ページ ID 等)。`document_id` の素材になる ID の責務で、`url` / `path` とは別。3.3 の正規化を適用する。空文字・UTF-8 で 4096 バイト超・NUL は全体 400(3.3) |
| `title` | string | ○ | タイトル(取得できなければファイル名)。孤立サロゲートを含むと、その文書だけ `document_rejected`(3.3) |
| `url` | string | 任意 | アクセス可能な原文の URL(`path` とは独立した項目。architecture K44) |
| `path` | string | 任意 | データソース内の文書パス(`url` とは独立した項目。architecture K44)。どちらか一方だけでも、両方でも渡せる。検索・絞り込みへの使用と最大長は未決 |
| `mime_type` | string | ○ | 文書形式(孤立サロゲートの扱いは `title` と同じ) |
| `raw_content` | string(base64) | ○ | 取得済みの原本(MVP では参照ではなく原本そのものを渡す。base64 は提案)。抽出前のデータで、検索インデックスの `content`(抽出後の本文)とは別物 |
| `content_hash` | string | ○ | 原本の SHA-256。小文字 64 桁の 16 進だけ(大文字は全体 400)。Indexer は照合も再計算もしない(確定。architecture K66。ユーザー承認 2026-11-11(0002 §3 #4))。保存した値との比較(変更なしの判定。手順 2 (b))には、Crawler の値をそのまま使う |
| `source_updated_at` | datetime | ○ | データソース上の更新日時(ローカルでは `mtime`) |
| `size` | integer | ○ | 原本のサイズ(バイト。0 以上の整数)。原本 1 件の上限を超える申告は、文書単位の `oversize`(4.9) |

必須/任意は例 JSON と各項目の意味からの推定(案)。

- `url` と `path` を独立した 2 項目とするのは、`external_id`(ID)・`url`(アクセス先)・`path`(データソース内の位置)の役割を分けるため(architecture K44)。Wiki のようにページ ID を `external_id` にする場合など、3 つは同じ値にならない。
- 原本の取得日時と Connector 固有の追加属性は、MVP では保存せず、`documents[]` にも含めない(将来必要になった時点で追加する。architecture K45)。要素に `fetched_at` や `metadata` を含む文書を受け取ったときは、無視する(保存せず、エラーにもしない。ほかの未知の項目も同じ)(確定。architecture K59。ユーザー承認 2026-11-11(0002 §3 #7))。MVP では使わないため、将来項目が加わっても Crawler が壊れないことを優先した。
- `last_seen_at` は要素に含めない。Crawler はリクエストの `crawl_started_at`(クロールの開始時刻)を渡し、Indexer が `last_seen_at` に書く(4.2)。書き込みの前に、3.2 の受理条件を判定し(`deletion_result-{crawl_id}` に複写された値(開始通知の値)との照合を含む)、満たさなければリクエスト全体のエラーにする(architecture K23)。
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
      "size": 5
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
| `results[].change` | string | `created` / `updated` / `unchanged`(`ok` のとき。本文・メタデータに関する変更区分。architecture K50)。`created`: 新規の文書(上記 (a))。`updated`: 本文(抽出後)またはメタデータの変更があり、全文書き込みをした(メタデータだけの変更を含む。(c))。`unchanged`: 原本ハッシュ・抽出後の本文・メタデータ・処理状態がすべて同じで、全文書き込みをしなかった((b)。`last_seen_at` の Update だけを行う場合を含む)。再書き込みモード(4.1)では、既存の文書も `updated` になる。`last_seen_at` だけの更新は `updated` に含めず `unchanged` とする |
| `results[].extract_failed` | boolean | 抽出に失敗し、タイトルとメタデータを登録した場合 `true` |
| `results[].failure_type` | string | `failed` のとき。値は下記(`write_conflict`・`update_conflict` の名称は確定(architecture K51)。ほかの名称は案で、実装で採用中) |
| `results[].message` | string | 失敗の説明(案)。実装は `failed` の文書に必ず付ける。固定文で、文書の内容を含まない(`document_rejected` は OpenSearch のエラー種別名か検査の内容が括弧で付く) |

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
      "message": "the document was rejected (mapper_parsing_exception)"
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

`message` は例(実装の文言の形: 固定文に、`document_rejected` では OpenSearch のエラー種別名か検査の内容が括弧で付く)。

`failure_type` の値(実装が返すもの。名称は、`write_conflict`・`update_conflict` を除いて案で、実装で採用中。API-U-24):

| 値 | 意味 | Crawler の扱い |
| --- | --- | --- |
| `document_rejected` | 文書固有の拒否(OpenSearch が文書固有に拒否した、または `title`・`mime_type`・`path`・`url` が UTF-8 にできない(孤立サロゲート。3.3)) | リトライ後スキップ(連続 20 件でジョブ `failed` にする打ち切りは Crawler 側の規則で、Indexer は数えない。3.5) |
| `oversize` | 原本が上限(`max_raw_bytes`)を超えた(4.9)。抽出も書き込みもしない | リトライしない(案) |
| `lock_not_owned` | 所有確認の失敗(3.2、3.4) | スキップ・リトライの対象にせずジョブ `failed` |
| `write_conflict` | 書き込みの競合(409)の読み直しが上限を超えた(再試行可能。手順 3) | 上限付きでリトライし、解消しなければジョブ `failed`・期限削除なし。文書固有のスキップの対象にしない(architecture K51。3.5) |
| `update_conflict` | 手順 2 (b) の補完 Update が `retry_on_conflict` を超えて 409 になった(再試行可能。4.2 と同じ) | `write_conflict` と同じ(architecture K51)。`last_seen_at` を保存できないままクロールを完了扱いにはしない(3.5) |

- **`store_error` は返さない**(v0.9 の候補から外した。architecture K66。ユーザー承認 2026-11-11(0002 §3 #15)): OpenSearch 全体の異常(接続エラー、タイムアウト、429、5xx、`cluster_block_exception`、circuit breaker、索引の不在など)は、文書単位の失敗にせず、リクエスト全体の 503 `unavailable`(`retryable=true`。3.4、3.5)で返す。Crawler はジョブ `failed` にする(3.5)。

**エラー**:

| ステータス | コード(提案) | 条件 |
| --- | --- | --- |
| 400 | `invalid_request` | リクエストの形式不正(例: `documents` が空、件数・サイズの上限超過、`raw_content` が base64 でない。3.3) |
| 409 | `crawl_not_started` | `deletion_result-{crawl_id}` が存在しない(開始通知の未送信、保持期間超過での消去、`loreley-deletions` の喪失)。何も書かずに拒否し、リトライせず Crawler はジョブ `failed`(architecture K23、K66) |
| 409 | `crawl_source_mismatch` | `source_id` が `deletion_result` のものと一致しない |
| 409 | `crawl_started_at_mismatch` | `crawl_started_at` が複写値と一致しない。リクエスト全体のエラー(文書単位の結果は返さない)。リトライせず Crawler はジョブ `failed`(案) |
| 409 | `crawl_already_closed` | `deletion_result` が終端状態(`superseded` / `discarded` / `failed` / `deleted` / `skipped_by_ratio` / `validation_failed`) |
| 409 | `crawl_finished` | `deletion_result` が `running` だが終了通知を受理済み(`finish_received_at` あり) |
| 503 | `unavailable`(`retryable=true`) | OpenSearch の全体異常(文書単位の失敗にはしない。上記の `failure_type` に全体異常の種別はない)。リトライし、直らなければジョブ `failed` |
| 500 | `internal_error`(`retryable=false`) | Indexer の想定外の異常(3.4)。リトライし、直らなければジョブ `failed` |
| 接続エラー / タイムアウト | — | Indexer に届かない(起動前の接続拒否を含む。1章)。リトライし、直らなければジョブ `failed` |

**冪等性・注意事項**:

- **受理条件の判定**(architecture K23。確定): 4.2 と同じ(3.2)。文書の処理(抽出、検索インデックスへの書き込み)の前に、`deletion_result-{crawl_id}` の存在、`source_id` の一致、`crawl_started_at` の複写値との一致、`status` が `running`、`finish_received_at` がないこと((1)〜(5))を 1 回だけ判定し、満たさなければリクエスト全体のエラーにして何も書かない。(6) のロック所有確認は文書ごとで、失敗は文書単位の `failure_type: lock_not_owned`(最初の失敗以降の未処理の文書も `lock_not_owned` で、書かない。3.2、3.4。API-U-13)であり、上記 5 つの拒否名には含めない。終端状態や終了通知の受理後の `deletion_result` は、`crawl_started_at` が一致していても拒否する。保持期間超過で消えた `deletion_result` は存在しないものとして拒否する。いずれの拒否もリトライしても直らないため、リトライ対象にせずジョブ `failed` とする。コード名と HTTP の割り当ては確定(architecture K66。API-U-19)。
- 再送しても登録の状態が変わらない。同じ内容の再送は、検索インデックスの現在の文書と比べて変更なし((b))になり、書き込まれない。Indexer は `raw_content` の SHA-256 を計算せず、`content_hash` と照合しない(確定。architecture K66。ユーザー承認 2026-11-11(0002 §3 #4)。API-U-15。architecture U-26)。`content_hash` は Crawler の値を信用する。
- **再書き込みモードの適用**(architecture K33。確定): バッチ登録は、リクエストにモードの指定を持たない。受理条件の確認(3.2)で取得した `deletion_result` の `rewrite_mode` を参照するため、同じ `crawl_id` のすべてのバッチに同じモードが適用される。
- **文書ごとの処理の順**(案。実装で採用中。0020 §6-2(0021 で全て承認)): 文書ごとに、(1) ロック所有確認 → (2) 原本サイズの確認(`oversize`) → (3) メタデータの検査(孤立サロゲートは `document_rejected`) → (4) 抽出 → (5) 取得・判定・書き込み、の順に行い、結果を入力と同じ順で返す。ロックを失ったあとの文書は (1) で `lock_not_owned` になり、(2) 以降を行わない。
- **サイズの防御**(architecture K59、K65。確定。ユーザー承認 2026-11-11(0002 §3 #1、#22)): `documents` が空、または件数が上限を超えると、リクエスト全体が 400 `invalid_request`。`raw_content` は、デコードする前に、base64 の長さからデコード後のサイズを推定して判定する。(a) 推定したデコード後のサイズが原本 1 件の上限(`max_raw_bytes`)を超える文書は、デコードせず、文書単位の `oversize` にする(バッチの合計に数えない。1 件のためにバッチ全体が、再送しても直らない 400 にならないように)。(b) 申告された `size` だけが上限を超える文書は、デコードしたあとに文書単位の `oversize` にする(この場合は合計に含まれる)。いずれの `oversize` も、抽出せず、検索インデックスの既存の文書は書き換えない(4.9)。(c) デコードする文書のデコード後の合計が上限(`max_batch_bytes`)を超えると、リクエスト全体が 400。(d) base64 のままのリクエストボディが上限(`max_request_body_bytes`)を超えると、(a) の文書も `oversize` にならず、リクエスト全体が 400(`Content-Length` を先に見て、読む前に拒否する。チャンク転送では読んだ量で止める)。413 は使わない。上限の値は未決(API-U-6。architecture K39)で、仮値は設定として管理する(値は `apps/indexer/README.md` の 3 章)。
- **1 文書の書き込みは原子的**: 全フィールドは 1 回の PUT で書かれる。成功が登録の完了で、本文だけが新しく処理状態が古い、といった途中の状態は存在しない。
- 抽出の失敗は `status: ok` かつ `extract_failed: true`(失敗ではなくタイトルとメタデータの登録。リトライしない)。`extract_failed` の文書は `content` と `text_hash` を持たず、要約も生成しない。すでに `indexed` の文書が抽出失敗になったときは、`index_status` が変わるため (c) に進み、全体の PUT で旧 `content`・`text_hash`・要約を消して `extract_failed`(`summary_status=disabled`)にする(architecture K30)。最終成功時の本文は保持しない(MVP)。
- **要約**: 本文が変わらない文書の要約は更新しない。要約ロジックやモデルの変更などで再生成が必要な場合は、再書き込みモード(4.1。architecture K26)でクロールして本文ごと登録する。
- **`change` の区分と集計**(architecture K50): 変更がなく書かなかった場合を `unchanged` とし、「更新」に混ぜない。Crawler は `created_count` / `updated_count` に加えて `unchanged_count` を集計する(Crawler 領域の集計項目。名称は案。5 章)。
- **再送時の集計と、その厳密でない点**(案。API-U-16): Crawler は `document_id` ごとに**最初に受け取れた結果**を保持して数え、再送の結果では数え直さない。ただし集計は厳密ではない。応答が失われて再送した場合、最初の登録(`created`)は Crawler に届かず、再送の結果(同じ内容なので `unchanged`)を最初に受け取れた結果として保持するため、`created` が `unchanged` と数えられうる。件数の厳密な保証は契約に含めない。
- 原本サイズ超過は文書単位の `failure_type: oversize`(4.9)。件数照合では `oversize_document_ids` として別に送る(4.4)。Crawler が `oversize` の結果から ID を集めて送ることは Crawler 領域(案。API-U-23 の (7))。

**確認状況**: 同期 HTTP、文書単位の結果、冪等、失敗した文書だけ再送は確定(方式。数値・形式は未決)。書き込みを PUT 基本とすること(全文書き込みは PUT、`last_seen_at` だけの更新は Update)は architecture K19 で確定。新規・変更あり・変更なしの 3 分岐、変更なしの判定、読み直し、`op_type=create`、`if_seq_no`、max 比較は architecture K27 で確定(`retry_on_conflict` と読み直しの上限の値は architecture U-31)。抽出失敗時の旧 `content`・`text_hash`・要約の削除は architecture K30 で確定。エンドポイント、リクエスト/レスポンスの形、`write_conflict`・`update_conflict` 以外の失敗種別名(`oversize` を含む)、バッチ登録の `lock` の運び方(JSON ボディ)は提案(実装で採用中)。`write_conflict`・`update_conflict` の名称と扱いは architecture K51 で確定。新規・更新・変更なしの 3 区分は architecture K50、`url` / `path` の 2 項目は K44、原本の取得日時と追加属性を保存せず `documents[]` に含めないことは K45 で確定。受理条件の判定は architecture K23 で確定(エラー名・HTTP は K66 で確定。API-U-19)。再書き込みモードの採用は architecture K26 で確定。保持先(`deletion_result` の設定スナップショット)は K33 で確定。名称・指定経路は未決(API-U-22)。v0.10 で確定: `content_hash` を照合しないこと、`fetched_at`・`metadata` と未知の項目を無視すること、サイズ・件数の上限超過を 400 とすること(K59)、ロック失敗時の部分結果、`store_error` を返さず全体異常を 503 にすること(K66)、原本サイズ超過を Indexer も拒否すること(K65)。承認: 2026-11-11(0002 §3 #1、#4、#5、#7、#15、#22)。

### 4.4 終了通知

**概要**: 列挙の終了を伝える。Indexer は、処理の前に `source_id` を `deletion_result` と照合し(architecture K32)、受理(202)したのち、削除の判断・実行を非同期に行う。受理時に、件数照合と削除対象の除外に使うスキップ文書 ID 一覧とサイズ超過文書 ID 一覧を `deletion_result` に保存する(architecture K31。合算件数が上限を超えるときは保存しない)。判断の結果は応答に含めず、Crawler は Status API で確認する。

**エンドポイント**: `POST /crawls/{crawl_id}/finish`(案)

**呼び出し元**: Crawler。すべてのバッチ登録と `last_seen_at` 部分更新の応答を確認したあと。列挙の失敗・取り消しの場合は `outcome=failed` または `cancelled` を可能なら送る(届かなくても削除されないので安全)。取り消しが有効なのは、終了通知を送る前だけ。送ったあとに取り消しても削除処理は止まらない(ジョブは `cancelled` になり、結果は削除結果に残る)。

**リクエスト**:

| 名前 | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `crawl_id`(パス) | string | ○ | 開始通知と同じ ID |
| `source_id` | string | ○ | データソース ID |
| `outcome` | string | ○ | `enumeration_completed` / `failed` / `cancelled` |
| `enumerated_count` | integer | `enumeration_completed` のとき ○ | Crawler が `document_id` で重複を除いて数えた列挙件数(0 以上)。スキップ・抽出失敗の文書を含む |
| `skipped_document_ids` | string[] | 同上 | スキップした文書の ID の一覧(スキップ文書 ID 一覧。要素は小文字 64 桁の 16 進。3.3)。上限は `oversize_document_ids` との合算件数で、値は実測後に確定する(設計書上は未決。API-U-5) |
| `oversize_document_ids` | string[] | 同上 | 原本サイズ超過の文書の ID の一覧(サイズ超過文書 ID 一覧。要素は小文字 64 桁の 16 進。スキップとは別項目。architecture P32) |
| `skipped_count` | integer | 任意 | `skipped_document_ids` の件数(`oversize_document_ids` は含まない)。実装は必須にせず、型(非負整数)だけを検証して値を使わない(`skipped_document_ids` の件数との一致も検証しない。3.3。architecture K59) |
| `finished_at` | datetime | ○ | 終了時刻。形式(タイムゾーン付きの ISO 8601)だけを検証し、保存も、再送の比較への使用もしない |

失敗時(`failed` / `cancelled`)の `outcome` 以外の件数は、可能な範囲で送る。実装は省略を受理し(`enumeration_completed` のときだけ、`enumerated_count` と 2 つの ID 一覧を必須とする)、送られた値はダイジェストにだけ含める(保存はしない。下記の受理時の分岐 3)。省略可否は未決のまま(API-U-12。実装で採用中)。

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

**レスポンス**: `202 Accepted`(ボディなし。実装はボディなしで返す。案)。判断の結果は含めない。`source_id` が `deletion_result` と一致しないとき、および記録済みの再送で内容が異なるときは 409(下記。共通エラー形式でコードと短いメッセージだけを返し、最初に受理した終了通知の全文・ダイジェスト・受理済みの状態の詳細は返さない。architecture K43。受理の有無は Status API で確認する)。

**エラー**:

| ステータス | コード(提案) | 条件 |
| --- | --- | --- |
| 400 | `invalid_request` | リクエストの形式不正(`enumeration_completed` で `enumerated_count` か ID 一覧が欠けている場合を含む。3.3) |
| 409 | `finish_source_mismatch` | リクエストの `source_id` が `deletion_result-{crawl_id}` の `source_id` と一致しない。処理の前に確認し、状態は変えない(architecture K32、K40) |
| 409 | `finish_content_mismatch` | 記録済みの終了通知の再送で、内容(終了通知のダイジェスト)が最初に受理した内容と異なる。状態は変えない(architecture K25、K40) |
| 503 | `unavailable`(`retryable=true`) | 受理の書き込みの競合(409)が読み直しの上限を超えた。何も書かずに止まり、受理は冪等なので再送で収束する(案。実装で採用中。0020 §6-2(0021 で全て承認))。OpenSearch の全体異常も同じ |
| 500 | `internal_error`(`retryable=false`) | Indexer の想定外の異常(3.4)。リトライし、直らなければジョブ `failed` |
| 接続エラー / タイムアウト | — | Indexer に届かない(起動前の接続拒否を含む。1章)。リトライし、直らなければジョブ `failed`。届かなければ削除が行われないだけで安全 |

**冪等性・注意事項**:

- **処理順**(architecture K38。確定): (1) リクエスト形式の検証(不正なら 400)→ (2) `source_id` の照合(不一致なら 409。`finish_source_mismatch`)→ (3) 終了通知のダイジェストによる再送の判定(下記)→ (4) 初回の通知としての受理処理(下記の受理時の分岐)。形式が不正なら `source_id` が違っていても 400、形式が正しく `source_id` だけ違えば 409、内容も `source_id` も違う再送は `source_id` 違いの 409 として扱う(どれも状態不変)。開始通知・終了通知のソース単位の直列処理の方針は変えない。
- **`source_id` の照合**(architecture K32。確定。API-U-21): 終了通知の処理の前に、リクエストの `source_id` と `deletion_result-{crawl_id}` の `source_id` の一致を確認する。不一致なら 409(`finish_source_mismatch`)を返し、状態を変えず、何も書かない。`outcome` の値に関わらず確認する。`deletion_result-{crawl_id}` が存在しない未知の `crawl_id` は照合できないため、この確認の対象外で、下記の分岐 2 のとおり 202 を返して破棄する。Crawler は、通常は開始通知と同じ `source_id` を送るので、409 は取り違え(Crawler 側のバグ)の検出になる。
- **再送の扱い**(architecture K25。確定。API-U-21): `source_id` の照合のあと、受理時の分岐の先頭で判定する。ダイジェストが記録済みの再送は、世代を見ず再処理しない。内容が最初に受理した内容と同じなら 202、異なれば 409(`finish_content_mismatch`)を返し、状態を変えない(後の内容は採用しない)。比較のため、最初の通知の**終了通知のダイジェスト**(項目名 `finish_request_digest`。`outcome`、`enumerated_count`、重複を除いてソートした `skipped_document_ids` と `oversize_document_ids` を正規化した SHA-256。`finished_at` は除く。実装の正規形は、この 4 項目を、キーをソートし区切りの空白なしの JSON にして SHA-256(16 進)にしたもので、`source_id`・`skipped_count`・`finished_at` を含めない。省略(null)と空の配列は別の値として扱うため、`failed`・`cancelled` で ID 一覧を省略した通知と、空の配列で送った再送は一致しない。実装で採用中)を、`finish_received_at` と同じ書き込みで `deletion_result` に保存する(`failed`・`cancelled` でも保存する)。再送かどうかの判定は「ダイジェストが記録済みか」だけで行い、`finish_received_at` や終端状態の有無は使わない(`outcome=failed` / `cancelled` は `finish_received_at` を記録しないが、ダイジェストは記録するため)。ダイジェストが未記録の場合(下記 (1) の遅れた終了通知など)は比較せず 202 を返す。終了通知の受理の書き込みは、開始通知と同じソース単位の直列処理の中で、`if_seq_no` の条件付き更新で行う(architecture 9.5、9.9(4))。409 になったら読み直して最初から判定し直し、読み直しが上限(設定 `write_conflict_max_rereads`)を超えたら、何も書かずに 503 `unavailable` を返す(`retryable=true`。受理は冪等で、再送で収束する。案。実装で採用中。0020 §6-2(0021 で全て承認))。ダイジェストに `source_id` は含めない前提(任意。K32。照合は上記のとおり処理の前に行うため)。409 の本文は共通エラー形式(`error.code`、`error.message`、`error.retryable` など)で、コードと短いメッセージだけを返す。最初に受理した終了通知の全文・ダイジェスト・受理済みの状態の詳細は返さず、Status API(4.5)で確認する(architecture K43)。
- **Crawler の義務**(Crawler 設計への要件。K25 の検証が成り立つための前提): Crawler は最初の通知内容を `loreley-jobs` に保存して固定し、再送では常に同じ内容を送る。応答が失われたあとの同じ内容の再送には 202 が返る。ただし 202 は、再送が冪等に処理されたことを示すだけで、受理の確認ではない((1) の遅れた通知と (2) の未知の `crawl_id` にも 202 が返るため)。受理の有無と削除の進行は Status API(4.5 の「終了通知の受理の有無の読み方」)で確認する(`finish_received_at` の有無、または `status=failed` かつ `reason=outcome_*`。遅れた通知は終端状態のまま、未知の `crawl_id` は 404)。409 で得られるのは Crawler 側のバグの検出で、優先度は低い。409 の本文は詳細を返さないので、受理の有無は Status API で確認する。
- **受理時の分岐**(世代の判定はこの受理時に 1 回だけ行う。(1)〜(4) のどの分岐でも、初回の通知への応答は 202):
  1. ダイジェストが未記録で、その `crawl_id` の削除結果がすでに終端状態(`superseded` など。終了通知が届かないまま新しい開始通知で `superseded` になった旧世代への遅れた終了通知など): 何もしない。状態を変えず、削除しない。
  2. 開始通知を受けていない未知の `crawl_id`: 削除に使わず破棄する(確定。architecture K7)。削除結果は作らず、ログに `crawl_id` だけを残す(確定。architecture K66。ユーザー承認 2026-11-11(0002 §3 #16)。P16。記録しないので、件数の上限は要らない)。
  3. `outcome` が `failed` または `cancelled`: 待たずに `failed`(理由 `outcome_failed` または `outcome_cancelled`)を記録して削除しない(`finish_received_at` は記録しない)。削除結果を `failed` にしてから 202 を返す。この通知にスキップ文書 ID 一覧やサイズ超過文書 ID 一覧が含まれていても、2 つの ID 一覧は保存せず、終了通知のダイジェスト(`finish_request_digest`)だけを保存する(architecture K36)。この通知から保存するのは、`outcome`・ダイジェスト・理由・終端状態になった時刻で、`enumerated_count` は保存せず、待ち行列にも入れない(削除ワーカーも起こさない)(案。実装で採用中。0020 §6-2(0021 で全て承認))。
  4. `enumeration_completed`: `finish_received_at` を `loreley-deletions` に永続化してから 202 を返す(202 のあとに再起動しても、受理した事実が残り、再起動時に `failed`(`indexer_restart`)にできる)。スキップ文書 ID 一覧とサイズ超過文書 ID 一覧(正規化したもの)を、終了通知のダイジェスト(`finish_request_digest`)と同じ書き込みで `deletion_result` に保存する(項目名は `skipped_document_ids`、`oversize_document_ids`。architecture K31。確定)。ただし 2 つの合算件数が上限を超える場合は、2 つの ID 一覧を保存せず、合算件数(`skip_and_oversize_id_count`)と上限を超えた事実(`skip_and_oversize_id_limit_exceeded`)を記録する(下記の件数照合の節。architecture K34)。合算件数と超過フラグは、上限以内でも記録する(フラグは `false`。案。実装で採用中。0020 §6-2(0021 で全て承認))。ソースごとの待ち行列に入れ、先行する削除結果が終端状態になってから判定に進む。待機中の判定も、保存した ID 一覧を使う。保存した ID 一覧は、`deletion_result` が終端状態へ遷移する書き込みと同じ書き込みで削除する(終了通知のダイジェストは残す。architecture K35。確定)。Indexer の再起動で待機中の削除は `failed`(`indexer_restart`)になり、実行されない(保存した ID 一覧も同じ書き込みで削除する)。判定の順(順 1〜6)と実行は `indexer-architecture-v0.10.md` を参照。割合ルール内の判定 1〜3 は `loreley-deletions-v0.10.md` と `indexer-architecture-v0.10.md` を参照。
- **応答が失われた場合**(確定。architecture K12): 終了通知が Indexer に受理される前にクロールが失敗した場合は、削除しない。受理された後は、応答が失われただけなら Indexer は受理済みで削除が進みうる(Crawler からは届かなかった場合と区別できない)。Crawler が再送もすべて失敗してジョブ `failed` にしても削除が進みうるが、各文書の削除直前の TTL 再確認で、更新された文書は消えない。結果は削除結果に残る。「安全」の根拠は、前提(列挙の完了、全バッチの登録の確認)が送信前に確認済みであることと、実行時の各文書の削除直前の TTL 再確認。

**件数照合**(終了通知の値の定義): Indexer は次が成立するときだけ削除の判断に進む。不一致なら削除せず `validation_failed` として記録する(許容差なし。案)。

```text
enumerated_count == N_seen + E_missing
  N_seen    = 当該 source_id で last_seen_at >= crawl_started_at の件数(リフレッシュ後の検索インデックス)
  E_missing = skipped_document_ids と oversize_document_ids の和集合のうち、検索インデックスにないものの件数(重複は 1 件。architecture P32)
```

- スキップ文書 ID 一覧とサイズ超過文書 ID 一覧の合算件数が上限を超えるときも、終了通知は 202 で受理する(architecture K34)。2 つの ID 一覧そのものは保存せず、合算件数(`skip_and_oversize_id_count`)と上限を超えた事実(`skip_and_oversize_id_limit_exceeded`)だけを `deletion_result` に記録する。削除の判定の順番が来たときに `validation_failed`(`reason` で区別)にして削除しない。判定の順番が来るまで `status` は `running` のままである。上限の値と送り方(エンコード、分割)は実測後に確定する(設計書上は未決。API-U-5。architecture U-2)。上限は合算件数に対する制限で、HTTP リクエストのボディサイズ上限(受信可能なサイズ)とは別の制限である。ボディが受信可能なサイズを超えた場合まで 202 を保証しない。
- `E_missing` の計算と削除対象からの除外(architecture 9.5、9.6)は、`deletion_result` に保存した ID 一覧(スキップ文書 ID 一覧とサイズ超過文書 ID 一覧)を使う(architecture K31)。先行する削除が実行中で待機した場合も、判定の時点まで保存した ID 一覧が保持される。
- 抽出に失敗した文書(`extract_failed`。タイトルとメタデータを登録)は検索インデックスにあるので `N_seen` に数えられる。
- 旧い削除の待機中に新しいクロールが `last_seen_at` を更新して不一致になる場合は、削除しない側に倒れるだけなので許容(案)。
- 同じ ID が `skipped_document_ids` と `oversize_document_ids` の両方にあっても、`E_missing` の上では和集合で 1 件と数える(`skipped_count` は `skipped_document_ids` の件数のまま)。
- 新規の原本サイズ超過文書は `oversize_document_ids` で数える(architecture P32)。Indexer も拒否することは確定(4.9。architecture K65)で、上限の値などの残りは未決(API-U-8)。

**確認状況**: 終了通知の存在、202、世代 `crawl_id`、未知の `crawl_id` の破棄、件数照合は確定。応答喪失時の削除の継続(受理前は削除しない、受理後は継続しうる)は確定(architecture K12)。再送で内容が異なる場合の 409(案 B)は architecture K25 で確定。`source_id` の事前照合と不一致の 409(未知の `crawl_id` は 202 のまま)は architecture K32 で確定。受理時に 2 つの ID 一覧を `deletion_result` に保存することは architecture K31 で確定。上限超過時の 202 での受理と ID 一覧を保存しない扱い(K34)、終端状態へ遷移する書き込みと同じ書き込みでの削除(K35)、`failed` / `cancelled` で ID 一覧を保存しないこと(K36)、処理順(K38)、409 のコード名 `finish_content_mismatch`・`finish_source_mismatch`(K40)、409 の本文(K43)、`deletion_result` の項目名(K42)も確定。エンドポイント形、`oversize_document_ids`(P32)は案(実装で採用中)。未知の `crawl_id` の終了通知に 202 を返し、削除結果を作らずログに `crawl_id` だけを残す扱いは architecture K66 で確定(P16。ユーザー承認 2026-11-11(0002 §3 #16))。受理の書き込みの競合が上限を超えたときの 503、`failed`・`cancelled` で保存する項目、ID 一覧の件数とフラグを上限以内でも記録することは、案(実装で採用中。0020 §6-2(0021 で全て承認))。未決: API-U-12(`failed` 時の項目省略)、API-U-5(合算件数の上限の値。実測後に確定)。

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
| `reason` | string | `failed`(理由コード)、`discarded`(理由)、`validation_failed`(理由)のとき |
| `forced` | boolean | `force_delete` の複写 |
| `target_count`(T) / `denominator`(D) | integer | 削除対象件数 / 割合の分母 |
| `ttl` / `ratio_threshold` / `min_delete_count` | integer / number / integer | しきい値(開始通知の値の複写。4.1) |
| `deleted_count` | integer | 削除した件数(記録の規則は下記) |
| `enumerated_count` / `n_seen` / `e_missing` | integer | 件数照合の値 |
| `finish_received_at` / `deletion_started_at` / `finished_at` | datetime | 時刻。`finished_at` は削除結果が終端状態になった時刻(削除結果の `ended_at`。案。実装で採用中) |
| `waiting_for` | string | 待機中のみ・任意。先行する削除結果の `crawl_id`(確定。architecture K66。下記) |

- 値のない項目(未記録・該当しない)は、キーごと省く。応答は上記の項目だけで、`outcome`・`reason` の詳細・ID 一覧・`rewrite_mode` などは返さない。
- **`status` の値**(状態名の一覧は案。architecture P25): `running`(終了通知待ち・待機中・判定中・削除中を含む) / `deleted` / `skipped_by_ratio` / `validation_failed` / `discarded` / `failed`。`running` 以外が終端状態。待機中も `running` のままで、状態は増やさない。
- **「削除中」の見せ方**(architecture K43): `status` に「削除中」を加えず、`status=running` のままとする。進捗が必要なときは `deletion_started_at` と、実際に記録済みの `deleted_count` を使う。削除件数の途中経過がまだ保存されていなければ、未記録の進捗を推測して表示しない。
- **`deleted_count` の記録**(architecture K62。確定。ユーザー承認 2026-11-11(0002 §3 #18)・2026-11-12(0021 §1)): 削除バッチごとに、そのバッチの前に、それまでの累計を条件付き更新で書く(自分の結果が終端状態でないことの確認を兼ねる)。終端状態の書き込みで最終値にする。記録済みの値は減らさない(進捗の更新でも、再実行でも)。起動時の整理で `failed`(`indexer_restart`)にするときは、`deleted_count` が未記録なら 0 を付け(進捗は各バッチの前に書かれるので、未記録は削除が 1 件も実行されていないことを意味する)、記録済みなら減らさない。上記の「削除中」の見せ方は、`running` の間に未記録の進捗を推測して表示しない、という意味で、終端状態で 0 を記録する規則とは別である。
- **`waiting_for`**(architecture K66。確定。ユーザー承認 2026-11-11(0002 §3 #17)): `status=running` で `finish_received_at` があり、同じソースに先行する(受理順で前の)終端状態でない結果があるときだけ返す。値は直前の先行結果の `crawl_id`(A→B→C のとき、C は B)。受理順は `(finish_received_at, crawl_id)` の順。`finish_received_at` のない `running` は先行にならず、`waiting_for` も返さない。
- **`failed` の理由コード**(案。名称は実装で採用中。API-U-24): `outcome_failed` / `outcome_cancelled` / `maintenance` / `indexer_restart` / `delete_error`。**`validation_failed` の理由**(案。実装で採用中): `count_mismatch` / `id_limit_exceeded` / `target_exceeds_denominator`。
- **`discarded` の理由**: `superseded`(終了通知が届かなかった旧世代の整理)、`source_deleted`(ソース削除による破棄)。
- 各状態の意味と記録項目は `loreley-deletions-v0.10.md` を参照。

**終了通知の受理の有無の読み方**(4.4。応答の項目は増やさず、既存の項目だけで読む):

| 終了通知の扱い | Status API の応答 |
| --- | --- |
| `enumeration_completed` を受理する前 | `status=running` かつ `finish_received_at` なし |
| `enumeration_completed` を受理した後(待機中・判定中・削除中を含む) | `finish_received_at` あり(`running` のままのことも、終端状態のこともある) |
| `failed` / `cancelled` を受理した結果 | `finish_received_at` は未記録のまま `status=failed`、`reason=outcome_failed` または `outcome_cancelled` |
| 遅れた通知(4.4 の分岐 1。旧世代で、すでに終端状態) | その `crawl_id` が終端状態のまま(`superseded` など)。受理されていない |
| 未知の `crawl_id`(4.4 の分岐 2) | 404。受理されていない |

受理の根拠は、`finish_received_at` があること、または `status=failed` かつ `reason` が `outcome_*` であることのどちらか。`failed` / `cancelled` の受理は `finish_received_at` を持たないため、`finish_received_at` の有無だけで受理を判断してはならない。応答に `outcome` を持たせる仕様は、ここでは追加しない。

応答例(待機中。待機中は定義上、終了通知を受理済み。`waiting_for` は任意項目。例は一部の項目だけを示し、実際の応答には `forced`・`ttl`・`ratio_threshold`・`min_delete_count` など値のある項目も含まれる):

```json
{
  "crawl_id": "job-20261109-0002",
  "source_id": "src-docs",
  "status": "running",
  "finish_received_at": "2026-11-09T01:20:05Z",
  "waiting_for": "job-20261108-0007"
}
```

応答例(削除完了。`ttl` などの値は未決):

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
| 404 | `crawl_not_found` | 保持件数を超えて消えた `crawl_id`、開始通知を受けていない `crawl_id`、`loreley-deletions` を失った場合 |
| 503 | `unavailable`(`retryable=true`) | OpenSearch の全体異常、起動時の整理が終わるまで(1章) |
| 500 | `internal_error`(`retryable=false`) | Indexer の想定外の異常(3.4) |
| 接続エラー / タイムアウト | — | Indexer に届かない(起動前の接続拒否を含む。1章) |

404 の条件(保持件数を超えて消えた、開始通知を受けていない、`loreley-deletions` を失った)は区別せず、同じ 404 `crawl_not_found` を返す(確定。architecture K66。ユーザー承認 2026-11-11(0002 §3 #17)。API-U-10)。保持件数 N の値は未決(API-U-5。architecture U-2)。

**冪等性・注意事項**: 読み取りのみ。**返すのは削除結果のみ**で、登録結果と確認結果の区分は含まない(確定)。

**確認状況**: Status API の存在、削除結果のみを返すことは確定。v0.10 で確定: `waiting_for`、404 の条件(architecture K66。API-U-10)、`deleted_count` の記録の規則(K62)。エンドポイント形、状態名の一覧(P25)、理由コード名、`finished_at`(=`ended_at`)の項目、キー名は案(実装で採用中)。未決: API-U-1。

### 4.6 ソース削除 1: 削除結果の破棄(提案)

**概要**: ソース削除は Crawler のジョブで、期限削除の判断(割合ルール)は通らない。全体の順序は次のとおり。そのソースの終端状態でない削除結果を `discarded`(理由 `source_deleted`)にする(本 API)→ 検索インデックスから `source_id` の文書をすべて削除(4.7)→ スキップ記録(Crawler が削除。案)と、削除の記録(`deletion-{source_id}` と `deletion_result-*`)を削除(4.8 など)→ データソース設定を削除 → **ロック文書の削除は最後**。ジョブは `source_id` 単位のロックを最後まで保持する(architecture K29。確定。Crawler 設計への要件。API-U-14)。この要請は Deletion Manager のソース単位の直列実行で最優先とする(「最優先」の意味は下記。案)。Indexer に要請するのは 4.6〜4.8 の 3 つ(提案)。いずれも再送しても結果は変わらず、何度でも再実行できる。ロックの具体(Crawler 側の設計)によらず、Indexer 側の動作は次のとおり成立する(4.7・4.8 の注意事項)。

**エンドポイント**: `POST /sources/{source_id}/deletions:discard`(案)

**呼び出し元**: Crawler(ソース削除ジョブ)

**リクエスト**:

| 名前 | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `source_id`(パス) | string | ○ | データソース ID |
| `lock` | object(`owner`, `job_id`) | ○ | ロック所有情報。形式だけを検証し、所有は確認しない(確定。architecture K60。3.2) |
| `reason` | string | 任意 | `source_deleted`(これ以外の値は 400) |

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

**エラー**: 400 `invalid_request`(ボディがない・`lock` が欠けている場合を含む)、503 `unavailable`(3.4。試行の上限を超えて終端でない結果が残った場合を含む。下記)。`lock` の所有は確認しないので、409 `lock_not_owned` は返さない。

**冪等性・注意事項**:

- **排他によるソース削除の優先**(確定。architecture K61。ユーザー承認 2026-11-12(0021 §2)): 実装は、削除バッチとソース削除の処理を、同じソース単位の削除専用の排他で直列にし、ソース削除が待っている間は、削除側が同じソースの次のバッチを先に取らない(ソース削除を優先する)。この排他は、開始通知・終了通知のソース単位の直列処理とは別で、互いを待たせない(通知は削除バッチの完了を待たずに即時に受理する)。この排他に入るのはソース削除 1・2(4.6・4.7)で、3(4.8。削除記録の削除)は使わない。
- **最優先の意味と応答の時点**(案。実装で採用中。architecture P29): この要請は Deletion Manager のソース単位の直列実行で最優先とし、実行中の削除バッチの完了直後、次のバッチの前確認や待機中の判定より前に `discarded` を書く。そのソースの終端でない削除結果(待機中を含む)をすべて `discarded` にしてから応答する。応答の時点で、そのソースの削除バッチは実行されていない。応答までバッチ 1 回分の時間がかかりうるため、Crawler のタイムアウトはこれを見込む(値は API-U-6)。バッチ内でハングした場合は待ち続ける(受容事項。architecture P29)。
- **ロックのリースとの関係は未決**(Crawler 領域。API-U-14): ジョブがロックを保持したまま、バッチ内のハングなどで応答を待ち続けると、ロックのリースが切れうる。その場合の、後続の 4.7・4.8 の所有確認(`lock_not_owned`)との関係は決めていない。
- 書き込みは `if_seq_no` の条件付き更新で、すでに終端状態の結果は上書きしない。衝突したら読み直して再試行し、終端状態になるか `discarded` にできるまで繰り返す(確定。architecture K61)。繰り返しは、終端でない結果を一覧して順に書くラウンドを単位とし、ラウンド数に上限がある(設定 `discard_max_attempts`。値は `apps/indexer/README.md` の 3 章)。間隔は置かない。上限を超えても終端でない結果が残ったときは、503 `unavailable`(`retryable=true`)を返す(確定。K61。ユーザー承認 2026-11-12(0021 §2)。エラー名 `unavailable` は 0002 §3 #15)。応答には理由を出さず、ログに理由 `discard_conflict` を残す(ログの理由名は案。実装で採用中。0020 §6-2(0021 で全て承認))。再実行すると残りから完了する(冪等)。実行中の削除側の停止確認は `indexer-architecture-v0.10.md` を参照。
- **ソース削除ジョブの Crawler 向け要件**(architecture K29。確定。9.14。API-U-14): Crawler 領域の設計に対する要件(1)〜(4)で、Crawler の設計は本書では決めない。(1) 削除中(4.6 から最後のロック文書の削除まで)は、ジョブがロックのリースを更新し続ける。(2) リースの更新に失敗するなどで所有権を失ったら、後続の削除操作(4.7、4.8、データソース設定とロック文書の削除)を停止する。(3) 停止したジョブは再実行で復旧する(4.7・4.8 は冪等)。(4) 削除中のデータソースに、新しいクロールを起動しない。(1)〜(3) は、応答待ちが長引いてリースが切れたあとに別のジョブがロックを取り、削除と新しい登録が重なることを防ぐための要件。(4) も同じ理由。「削除中」の状態をどの記録に持つかは未決(Crawler 領域)。

**確認状況**: 提案(案。下記の確定部分を除く)。ジョブがロックを最後まで保持すること(ロック文書の削除は最後)と、Crawler 向け要件(1)〜(4)は architecture K29 で確定。ソース削除での分担(Crawler が起動・管理、Indexer が実処理)は案(実装で採用中)。v0.10 で確定: `lock` を必須項目として受け取り所有を確認しないこと(architecture K60。ユーザー承認 2026-11-11(0002 §3 #8)・2026-11-12(0021 §1))、削除専用の排他によるソース削除の優先と、試行上限を超えたときの 503(K61。ユーザー承認 2026-11-12(0021 §2)。エラー名 `unavailable` は 0002 §3 #15)。案(実装で採用中): 「最優先」の意味(応答の時点で削除バッチが動いていないこと。architecture P29)、ログの理由名 `discard_conflict`。未決: API-U-14(Crawler 側の具体)。

### 4.7 ソース削除 2: 文書の全削除(提案)

**概要**: 検索インデックスから、その `source_id` の文書をすべて削除する。最終的にそのソースの文書を残さないことが目的で、`delete_by_query`(`conflicts=proceed`)を、**再実行して消し切る**(architecture K20、K28。確定)。検索インデックスが唯一の正本なので、これ以外に消す場所はない(下記の前提のもとで、完了後は `_count`=0)。

**エンドポイント**: `DELETE /sources/{source_id}/documents`(案)

**呼び出し元**: Crawler(ソース削除ジョブ。4.6 のあと)

**リクエスト**: パス `source_id`(string・必須)。ロック所有情報 `lock` は、JSON ボディ `{"lock": {"owner": "...", "job_id": "..."}}` で添える(必須。ボディがない・`lock` が欠けているときは 400。architecture K60。3.2)。ジョブがロックを最後まで保持する(architecture K29)ので、Indexer が所有を確認する。

**レスポンス**:

| 名前 | 型 | 説明 |
| --- | --- | --- |
| `deleted_count` | integer | 実行した `delete_by_query`(再実行を含む)が返した削除件数の合計。すでに削除済みの文書は数えない(推測。architecture U-31 で実機確認)。再送では 0 でも成功 |

```json
{ "deleted_count": 1215 }
```

**エラー**: 400 `invalid_request`(ボディがない・`lock` が欠けている場合を含む)、409 `lock_not_owned`(ロックを所有していない。何も書かない。3.2)、503 `unavailable`(3.4)。再実行の上限(設定 `delete_by_query_max_reruns`。最初の 1 回に加えての再実行回数。値は `apps/indexer/README.md` の 3 章)を超えても文書が残る場合は 503 `unavailable`(`retryable=true`。応答には理由を出さず、ログに理由 `documents_remaining` を残す。Crawler はジョブ `failed` とし、再実行で続きから消せる。503 は確定。architecture K61。ユーザー承認 2026-11-12(0021 §2)。ログの理由名は案。実装で採用中。0020 §6-2(0021 で全て承認))。

**冪等性・注意事項**:

- **何度でも再実行できる**(冪等)。すでに削除済みの文書に対しては 0 件でも成功を返す。
- **消し方**(architecture K20、K28。確定。上限の値と `delete_by_query` の動作は実機で確認する。architecture U-31(5)):
  1. 実行前に検索インデックスを refresh する。直前の書き込みが未 refresh だと、`delete_by_query` にヒットしないため。
  2. `delete_by_query`(`source_id` で絞る。`conflicts=proceed`)を実行する。クロールなどが先に更新した文書とは競合して、その実行では消えないことがある。
  3. 完了後に refresh し、`source_id` の `_count` が 0 であることを確認する。
  4. 0 でなければ手順 2 に戻って再実行する(再実行の上限を設ける。数値は実測後に確定する。設計書上は未決。architecture K48、U-31(5))。指定回数の再実行でも 0 にならなければ、上記のエラーで止まり、ソース削除のジョブは `failed` になる。残った文書は後続の再実行で削除する(無限に再実行しない)。
- **前提**: ソース削除中は、そのソースに新しいクロールを起動しない。ジョブがロックを最後まで保持するから(architecture K29。4.6 の Crawler 向け要件(4))。この前提があるので、競合した文書も再実行で消える。前提が守られず削除中に新しい登録が入ると、文書が残りうる(Crawler 側で防ぐ事項)。
- **リース切れ**: ロック所有情報(JSON ボディの `lock`)で所有確認し、リースが切れて 409 `lock_not_owned` になった場合は、何も書かず(確定。architecture K60。3.2)、Crawler はジョブ `failed` で止まる(案)。所有確認は、実行(再実行を含む)の前ごとに行う(architecture K61。確定): 別のジョブがロックを取ったあとの再実行が、新しい登録を消さないため。再度ジョブを実行すれば、残りの文書の削除と後続の手順が完了する。
- **排他と専用クライアント**(architecture K61。確定。ユーザー承認 2026-11-12(0021 §2)): 処理は、削除バッチと同じソース単位の削除専用の排他に入り、同じソースの実行中の削除バッチが終わってから始める(ソース削除を優先する。4.6)。`delete_by_query` は専用の OpenSearch クライアント(専用のタイムアウト設定 `os_delete_by_query_timeout_seconds`。タイムアウトや 5xx で自動再送しない)で呼ぶ。
- **Indexer 側はロックの具体に依存しない**: 本 API は冪等で再実行できる。ただし文書が残らないことの保証は、上記の前提(削除中に新しいクロールが登録しない。Crawler 側の要件)に依る。
- 所要時間が長い場合の非同期化(202 とポーリング)は提案に含めない。要否は未決(API-U-12)。

**確認状況**: 再実行で消す方針(`delete_by_query` を、実行前の refresh と完了後の `_count`=0 の確認つきで再実行する)は architecture K20、`delete_by_query` の採用と再実行の上限を設けることは K28 で確定。再実行の上限超過時の 503 と、`lock` の運び方・所有確認(再実行ごと)は v0.10 で確定(architecture K61。ユーザー承認 2026-11-12(0021 §2)、K60。同 0021 §1)。再実行の上限の値は設計書上は未決(architecture K39)、エンドポイント形は案(実装で採用中)。未決: API-U-12(非同期化)。

### 4.8 ソース削除 3: 削除記録の削除(提案)

**概要**: `loreley-deletions` の当該ソースの記録(`deletion-{source_id}` と `deletion_result-*`)を削除する。

**エンドポイント**: `DELETE /sources/{source_id}/deletion-records`(案)

**呼び出し元**: Crawler(ソース削除ジョブ。4.7 のあと)

**リクエスト**: パス `source_id`(string・必須)。ロック所有情報 `lock` は 4.7 と同じく JSON ボディで添える(必須。architecture K60。3.2)。

**レスポンス**:

| 名前 | 型 | 説明 |
| --- | --- | --- |
| `deleted` | boolean | 削除した場合 `true`。すでに記録がなければ `false`(成功。案) |

```json
{ "deleted": true }
```

**エラー**: 400 `invalid_request`(ボディがない・`lock` が欠けている場合を含む)、409 `lock_not_owned`(ロックを所有していない。何も書かない。3.2)、503 `unavailable`(3.4)。

**冪等性・注意事項**:

- 再送しても結果は変わらない。何度でも再実行できる(削除済みなら `deleted` は `false` でも成功。案)。
- **リース切れ**: ロック所有情報(JSON ボディの `lock`)で所有確認し、リースが切れて 409 `lock_not_owned` になった場合は、何も書かず(確定。architecture K60)、Crawler はジョブ `failed` で止まる(案)。再度ジョブを実行すれば、4.7 は 0 件で成功し、本 API で記録が削除されて完了する。
- **Indexer 側はロックの具体に依存しない**: 本 API は冪等で再実行できるため、結果は正しい。
- **ソース削除ジョブのロック**(architecture K29。確定): ジョブは `source_id` 単位のロックを最後まで保持(リースを更新し続ける)し、ロック文書の削除は手順の最後(本 API のあと)にする。Crawler 向けの要件の全体は 4.6。このため本 API の時点でもロック文書は存在し、4.7・4.8 の要請にロック所有情報を添えて所有確認できる。Crawler 側のロック設計の具体は、Crawler 設計で決める(API-U-14。architecture 9.14、U-4)。

**確認状況**: 提案(案。下記の確定部分を除く)。ジョブがロックを最後まで保持することは architecture K29 で確定。`lock` の運び方(JSON ボディ)と所有確認は architecture K60 で確定(ユーザー承認 2026-11-11(0002 §3 #8)・2026-11-12(0021 §1))。ほかは案(実装で採用中)。未決: API-U-14(Crawler 側の具体)。

### 4.9 補足: 原本サイズ超過(API ではない)

バッチ登録(4.3)に関わる事項をまとめる。

- 確定の範囲: 上限を超えた原本は取り込まず、原本サイズ超過として文書単位のエラーに記録する。スキップではなく、リトライもしない。`last_seen_at` は列挙時に更新済みで、削除対象にならない。
- **Indexer も拒否する**(architecture K65。確定。ユーザー承認 2026-11-11(0002 §3 #1)。API-U-4。Crawler の送信前の拒否との二重防御): `raw_content`(base64)の長さから推定したデコード後のサイズが原本 1 件の上限(`max_raw_bytes`)を超える文書(デコードしない)と、申告された `size` だけが上限を超える文書(デコード後に判定)は、いずれも、抽出も書き込みもせず、文書単位の `status: failed`・`failure_type: oversize`(名称は案。実装で採用中)で返す。リトライしない(4.3 の「サイズの防御」)。**すでに検索インデックスにある同じ文書は書き換えず、そのまま残す**(原本が上限を超えたことで、旧い内容を消さない。API-U-8 の一部)。
- 未決: 上限の値と形式(仮値は設定として管理する。architecture K39)。Crawler の送信前の拒否の有無と、エラーの記録先・項目、ジョブ status への影響(Crawler の領域)。API-U-8 の残り。
- 新規文書が索引にないときの件数照合は、終了通知の `oversize_document_ids` を `skipped_document_ids` と別項目にして E_missing の対象に含める(案。4.4、architecture P32)。含めないと `enumerated_count` と `N_seen + E_missing` が合わない。
- 4.3 の応答例には原本サイズ超過の形を含めない(形は 4.3 の `failure_type: oversize` のとおり)。

## 5. Crawler 側のポーリング規約(Indexer が前提とする部分)

この章は Indexer が前提とする範囲にとどめる。正本は Crawler 設計であり、ここでは決めない。

- Crawler は終了通知の 202 を確認したあと、Status API をポーリングして削除結果が終端状態になるのを待つ。間隔・上限時間・リトライ回数は未決(API-U-5)。
- ポーリングの失敗(リクエストのタイムアウト、接続エラー・5xx、404)が連続でリトライ回数まで続いた場合、またはポーリング全体の上限時間を超えた場合は、警告と確認結果の区分をジョブ記録に残すだけで、ジョブの status は変えない(確定)。区分の名称・対応は案(404 のみが続けば `unknown`、それ以外は `unconfirmed`)。Crawler は区分を残したあと再確認しない(確定)。
- ロックは削除結果が終端状態になるまで保持する。ポーリングの失敗・上限時間の超過のあとは解放する(案)。待機中のまま上限を超えた場合も同じで、削除結果は `running` のまま待機を続ける。
- 登録結果(`enumerated_count` / `created_count` / `updated_count` / `unchanged_count`(architecture K50)/ `skipped_count` / `oversize_count` / `error_count` / `partial`。名称は案)は、Crawler がバッチ応答を集計して `loreley-jobs` に持つ。Indexer が返すのは文書単位の応答(4.3)だけ。`unchanged_count` は 4.3 の `change: unchanged` の集計で、4.2 の `result: unchanged` とは別。応答が失われた場合の集計は厳密でなく、再送時は Crawler が `document_id` ごとに最初に受け取れた結果を保持する(4.3)。

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
| バッチ登録・`last_seen_at` 部分更新の受理条件(`deletion_result` が存在、`source_id` 一致、`crawl_started_at` 一致、`status` が `running`、`finish_received_at` がない、ロック所有確認に成功)。終端状態・受理後・存在しない結果への登録は拒否する。`crawl_id`・`crawl_started_at` を必須とし、ソース削除の要請は対象外(3.2、4.2、4.3。architecture K23。2026-11-10 確定)。拒否のエラー名・HTTP は K66 で確定(API-U-19) | 確定 |
| 開始通知の再送の一致検証(複写済みの項目と直接比較。一致なら成功、不一致なら 409。状態不変)(4.1。architecture K24。2026-11-10 確定)。コード名 `crawl_start_conflict` と HTTP は K66 で確定 | 確定 |
| 終了通知の再送で、内容が最初に受理した内容と異なる場合は 409(案 B。再送の判定は終了通知のダイジェストの記録の有無)。同じ内容は 202(4.4。architecture K25。2026-11-10 確定)。エラー名 `finish_content_mismatch` は architecture K40 で確定 | 確定 |
| 再書き込みモードの採用(本文が変わらない文書の要約を再生成するため、変更なしの判定をせず本文ごと全文書き込みする)(4.1、4.3。architecture K26。2026-11-10 確定)。名称 `rewrite_mode` と指定経路(開始通知の任意項目)は architecture K41 で確定 | 確定 |
| 終了通知の受理時に、終了通知のダイジェスト(`finish_request_digest`)と同じ書き込みで、スキップ文書 ID 一覧(`skipped_document_ids`)とサイズ超過文書 ID 一覧(`oversize_document_ids`)を正規化して `deletion_result` に保存する。待機中の削除の判定もこの保存した ID 一覧を使い、`deletion_result` が終端状態へ遷移する書き込みと同じ書き込みで削除する(ダイジェストは残す)(4.4。architecture K31、K35、K42。2026-11-10 確定) | 確定 |
| 2つの ID 一覧の合算件数が上限を超えるときも終了通知は 202 で受理し、2つの ID 一覧は保存せず合算件数(`skip_and_oversize_id_count`)と上限超過の事実(`skip_and_oversize_id_limit_exceeded`)だけを記録して、削除の判定の順番が来たときに `validation_failed` にする。HTTP リクエストのボディサイズ上限は別の制限で、受信可能なサイズを超えた場合まで 202 を保証しない。`failed` / `cancelled` の終了通知は ID 一覧を保存せず、ダイジェストだけ保存する(4.4。architecture K34、K36) | 確定 |
| 終了通知の処理順: (1) 形式の検証(400)→ (2) `source_id` の照合(409)→ (3) ダイジェストによる再送の判定 → (4) 初回通知の受理(4.4。architecture K38) | 確定 |
| 終了通知は、処理の前に `source_id` と `deletion_result.source_id` の一致を確認し、不一致なら 409(状態不変)。未知の `crawl_id` は 202 のまま(3.4、4.4。architecture K32。2026-11-10 確定)。ダイジェストに `source_id` を含めない前提は任意(K32)。エラー名 `finish_source_mismatch` は architecture K40 で確定 | 確定 |
| 終了通知の 409(`finish_source_mismatch`、`finish_content_mismatch`)は、共通エラー形式でコードと短いメッセージだけを返し、最初に受理した終了通知の全文・ダイジェスト・受理済みの状態の詳細は返さず、Status API で確認する。「削除中」は `status` に加えず `status=running` のまま、進捗は `deletion_started_at` と記録済みの `deleted_count` で見せる(途中経過が未保存なら推測して表示しない)(3.4、4.4、4.5。architecture K43) | 確定 |
| `rewrite_mode` を `deletion_result` の設定スナップショットに保持する。バッチ登録は受理条件の確認で取得した `deletion_result` から参照し、開始通知の再送の一致検証の比較項目に加える(異なれば 409)(4.1、4.3。architecture K33。2026-11-10 確定)。省略は `false` に正規化して複写し、再送の比較も正規化後の値で行う(省略と `false` の違いでは 409 にしない)(architecture K37) | 確定 |
| `documents[]` の `url` と `path` は独立した 2 項目(architecture K44)。原本の取得日時と Connector 固有の追加属性は MVP では保存せず、`documents[]` に含めない(architecture K45)(4.3) | 確定 |
| バッチ登録応答の `change` は `created` / `updated` / `unchanged`(本文・メタデータに関する変更区分。`last_seen_at` だけの更新は `unchanged`)(4.3。architecture K50) | 確定 |
| 書き込みの競合の上限超過の失敗種別名は `write_conflict`(全文書き込み)、`update_conflict`(`last_seen_at` の部分更新)。上限付きでリトライし、解消しなければジョブ `failed`、期限削除を行わない、文書固有のスキップの対象にしない(3.5、4.2、4.3。architecture K51) | 確定 |
| ソース削除の `delete_by_query` の再実行の上限を設ける(数値は実測後に確定)。上限でも完了しなければソース削除のジョブは `failed` で、残った文書は後続の再実行で削除する(4.7。architecture K48) | 確定 |
| 数値(合算件数の上限、保持件数、削除バッチ件数、ポーリング間隔、リトライ回数、`retry_on_conflict`、競合時の読み直し回数など)は実測後に確定する。実装の仮の初期値は設定として管理し、設計書上は未決のままとする(architecture K39) | 確定(方針。数値は未決) |
| 書き込みの細部: GET → `if_seq_no`/`if_primary_term` 付きの PUT(新規は `op_type=create`)、新規・変更あり・変更なしの 3 分岐、`last_seen_at` の Update の max 比較、409 は読み直して再判定(4.2、4.3。architecture K27。2026-11-10 確定)。`retry_on_conflict` と読み直しの上限の値は未決(architecture U-31) | 確定 |
| ジョブはソース削除の間 `source_id` 単位のロックを最後まで保持し、ロック文書の削除は最後に行う。Crawler 向け要件(1)〜(4)を含む(4.6〜4.8。architecture K29。2026-11-10 確定) | 確定 |
| `indexed` の文書が抽出失敗になったときは、旧 `content`・`text_hash`・要約を消して `extract_failed`(`summary_status=disabled`)にする(4.3。architecture K30。2026-11-10 確定) | 確定 |
| 原本サイズ超過の決定済み範囲(取り込まず文書単位のエラー、スキップ・リトライではない) | 確定 |
| `last_seen_at` を検索インデックスの文書に持つ。`crawl_started_at` を渡して Indexer が書く | 確定 |
| 開始通知の書き込みの順は、世代の更新 → 旧い結果の `superseded` 化 → 新しい結果の作成(結果の作成を最後のコミット点にし、途中で失敗した後の再送を収束させる)(4.1。architecture K57。ユーザー承認 2026-11-12(0021 §1)) | 確定 |
| `external_id` の先頭の `/` を除去しない(「先頭に `/` を付けない」は Crawler が渡す値の前提)(3.3。architecture K58。ユーザー承認 2026-11-12(0021 §1))。Crawler との突き合わせは API-U-23 | 確定(Crawler との突き合わせが必要) |
| 入力の検証規則: 型は strict で範囲は検証しない、未知の項目は無視(`fetched_at`・`metadata` を含む)、ID の文字・長さ、`content_hash` は小文字 64 桁の 16 進、ID 一覧の要素は 64 桁の 16 進、孤立サロゲートの分担、`skipped_count` は型のみ、サイズ・件数の上限超過は 400(413 は使わない)、起動前は全パス 503(3.3、3.4、4.1〜4.4。architecture K59。ユーザー承認 2026-11-11(0002 §3 #7、#14、#22)・2026-11-12(0021 §1・§2))。上限の値は未決(API-U-6)。Crawler との突き合わせは API-U-23 | 確定(Crawler との突き合わせが必要) |
| ソース削除の `lock` は JSON ボディで運び、順 2・3 は必須で所有を確認し(409 `lock_not_owned`)、順 1 は受け取るが確認しない(3.2、4.6〜4.8。architecture K60。ユーザー承認 2026-11-11(0002 §3 #8)・2026-11-12(0021 §1))。Crawler の HTTP クライアントが `DELETE` にボディを載せられることの確認は API-U-23 | 確定(Crawler との突き合わせが必要) |
| ソース削除の実行の細部: 削除専用のソース単位の排他(ソース削除を優先。ソース削除 1・2 が使い、3 は使わない)、`delete_by_query` 専用クライアント、順 2 の所有確認は実行(再実行を含む)の前ごと、discard の試行ラウンド数の上限と `delete_by_query` の再実行の上限を超えたときの再試行可能な 503(`unavailable`)(4.6、4.7。architecture K61。ユーザー承認 2026-11-12(0021 §2)) | 確定 |
| `deleted_count` は削除バッチごとに記録し、減らさない。起動時の整理で未記録なら 0 を付ける(4.5。architecture K62。ユーザー承認 2026-11-11(0002 §3 #18)・2026-11-12(0021 §1)) | 確定 |
| 原本サイズ超過は Indexer も拒否し(文書単位の `oversize`。名称は案)、すでに索引にある文書は書き換えない。リトライしない(4.3、4.9。architecture K65。ユーザー承認 2026-11-11(0002 §3 #1)) | 確定 |
| API 契約の採用: `content_hash` を照合しない、`last-seen` は Crawler が算出した `document_id` の配列(件数上限あり。`update_conflict` は文書単位、索引全体の異常は 503)、ロック失敗時の部分結果(文書単位の `lock_not_owned`。確認済みの結果を返し、最初の失敗以降の未処理の文書も `lock_not_owned`。全体は 200)、エラー名・HTTP(`unavailable` は 503)、未知の `crawl_id` の終了通知は 202、Status の `waiting_for` と 404、`store_error` を返さない(3.2、3.4、4.2〜4.5。architecture K66。ユーザー承認 2026-11-11(0002 §3 #4〜#6、#15〜#17)) | 確定 |
| `GET /healthz`(契約外)は起動時の整理の完了後にだけ応答し、それまで全パスが 503(1章。architecture K67。ユーザー承認 2026-11-11(0002 §3 #21。`/healthz` の応答)・2026-11-12(0021 §1。全パスの 503)) | 確定 |
| 文書固有の拒否(`document_rejected`)の連続 20 件でジョブ `failed` にする打ち切りは Crawler 側の規則で、Indexer は数えない(3.5。ユーザー承認 2026-11-12(0021 §1)) | 確定 |
| エンドポイント形(`POST /crawls/start` 等)、設定スナップショットの複写、削除結果の状態名の一覧(architecture P25)、`failed`・`validation_failed` の理由コード名、`oversize_document_ids` を別項目にすること(architecture P32)、キー名、`not_found`・`method_not_allowed`・`http_error` のエラーコード。実装は案どおりに実装している(実装で採用中。Crawler・infra の設計の確定時に再確認。API-U-24) | 案 |
| 日時の UTC・ISO 8601・ミリ秒への正規化(3.6。実装で採用中)、`last_seen_at` を保存できなければクロールを完了扱いにしない、Crawler 側のリトライ既定値・連続 20 件の数と規則(打ち切りの主体は Crawler。確定の部分は上の行) | 案 |
| ソース削除での分担(Crawler が起動・管理、Indexer が実処理)、ソース削除の文書の削除の細部のうち `conflicts=proceed`(architecture K28 の細部)(実装で採用中) | 案 |
| Status API の `finished_at`(削除結果の `ended_at`)の項目(4.5)、ソース削除 1 の「最優先」の意味(応答の時点で削除バッチが動いていないこと。4.6。architecture P29。排他によるソース削除の優先と、試行上限を超えたときの 503 は K61 で確定)、503 のログの理由名(`discard_conflict`、`documents_remaining`。4.6、4.7)、受理まわりの細目(受理の書き込みの競合上限超過の 503、`failed`・`cancelled` で保存する項目、ID 一覧の件数とフラグの記録、文書ごとの処理の順、開始通知の書き込み競合上限超過の 503。4.1、4.3、4.4)、`last-seen` の空の `document_ids` の受理(4.2)。実装で採用中(0020 §6-2。0021 で全て承認) | 案 |
| 登録の拒否の種類ごとのエラー名・HTTP(`crawl_not_started`、`crawl_source_mismatch`、`crawl_started_at_mismatch`、`crawl_already_closed`、`crawl_finished`)(3.2、3.4。architecture K66。ユーザー承認 2026-11-11(0002 §3 #15)。API-U-19) | 確定 |
| 4.2、4.3、4.6〜4.8 の提案のうち確定しない部分(エンドポイント、リクエスト/レスポンス例、エラー応答の形、`oversize` などの失敗種別名、バッチ登録・`last_seen_at` 部分更新の `lock` の運び方(JSON ボディ)。実装で採用中)。4.7・4.8 は何度でも再実行でき、リース切れの `lock_not_owned` でジョブが `failed` で止まっても再実行で完了し、ロックの扱いによらず Indexer 側は正しいこと | 案(本書の提案) |
| 数値の既定値・上限(ポーリング間隔・上限時間・リトライ回数、保持件数 N、スキップ文書 ID 一覧とサイズ超過文書 ID 一覧の合算件数の上限、バッチの件数・合計サイズ、タイムアウト、並列度、原本の上限、書き込み競合の読み直し上限、`retry_on_conflict` の値) | 未決(実測後に確定。architecture K39) |
| 下表の `API-U-*` のうち未決の項目(設定スナップショットと複写の項目名、`path` の検索・絞り込み要否・最大長、原本サイズ超過の上限の値・記録先・ジョブ status への影響、ソース削除ジョブの Crawler 側のロック設計の具体(API-U-14)、再送時の集計規則、`raw_content` の運び方と実測、Crawler との突き合わせ(API-U-23)、仮定義の再確認(API-U-24)など) | 未決(ユーザー判断) |

### 未決(ユーザー判断)の一覧

欠番(再利用しない): API-U-11(検索インデックスを唯一の正本にする決定。architecture K18 で確定したため)。確定した項目は欠番にせず、「確定(Kxx)」として表に残す(API-U-2、API-U-3、API-U-4、API-U-6、API-U-7、API-U-8、API-U-9、API-U-10、API-U-13、API-U-14、API-U-15、API-U-16、API-U-18、API-U-19、API-U-20、API-U-21、API-U-22 の確定部分)。確定は K12、K18〜K56、K57〜K63、K65〜K67(K57 以降は v0.10 で加わった。ユーザー承認 2026-11-11(0002 §3)または 2026-11-12(0021 の §1・§2)、K63 は 0014。K66・K67 の範囲は 0 章のとおり)。

| ID | 内容 | 選択肢(あれば) |
| --- | --- | --- |
| API-U-1 | 設定スナップショットの項目名(開始通知、`deletion_result` の複写、Status API のしきい値)の統一(architecture U-14) | 開始通知の名称(`ttl` / `ratio_threshold` / `min_delete_count` / `force_delete`)に揃える。複写先では `force_delete` を `forced` として持つ |
| API-U-2 | **確定(architecture K45)**: 原本の取得日時と Connector 固有の追加属性は MVP では保存せず、`documents[]` にも含めない(将来必要になった時点で追加する) | 確定(K45) |
| API-U-3 | **確定(architecture K44)**: `url`(アクセス可能な原文の URL)と `path`(データソース内の文書パス)を独立した任意項目 2 つとして採用する。`external_id` は ID の責務で別。`path` を検索・絞り込みに使うかと最大長は未決(`search-index-v0.10.md`) | 確定(K44) |
| API-U-4 | **確定(architecture K65。ユーザー承認 2026-11-11(0002 §3 #1))**: 原本サイズ超過は Indexer も拒否する(Crawler の送信前の拒否との二重防御)。申告 `size` か、推定したデコード後のサイズが上限を超えたら、文書単位の `oversize` にする(architecture U-5 の拒否主体) | 確定(K65) |
| API-U-5 | ポーリング間隔・上限時間・リトライ回数、保持件数 N、スキップ文書 ID 一覧とサイズ超過文書 ID 一覧の合算件数の上限と送り方、削除バッチ件数、しきい値・最小件数の既定値(architecture U-1、U-2)。実測後に確定する(設計書上は未決。実装の仮の初期値は設定として管理する。architecture K39) | なし |
| API-U-6 | バッチの件数・合計サイズ、タイムアウト、並列度の値(architecture U-3)。**確定(architecture K59。ユーザー承認 2026-11-11(0002 §3 #22))**: 件数・サイズの上限超過は、リクエスト全体の 400 `invalid_request`(413 は使わない)。値は未決(仮値は設定として管理する) | 確定(K59)。値は未決 |
| API-U-7 | **確定(architecture K66、K60、K51。ユーザー承認 2026-11-11(0002 §3 #4〜#8、#15)・2026-11-12(0021 §1))**: `last_seen_at` 部分更新の要請の単位(Crawler が算出した `document_id` の配列。算出主体は Crawler。4.2)、ソース削除の呼び出し形(`lock` は JSON ボディ。3.2)、エラーコードの割り当て(API-U-19)、`write_conflict`・`update_conflict` の名称と、解消しない場合の Crawler の扱い(ジョブ `failed`、期限削除を行わない、文書固有のスキップの対象にしない)。**案のまま(実装で採用中)**: 内部 API の契約本体のうちエンドポイント・リクエスト/レスポンスの形・ロック所有情報の形(API-U-23)・`oversize` などの失敗種別名(API-U-24)。**未決**: `document_id` の算出と `external_id` の正規化(3.3)は Crawler(4.2)と Indexer(4.3)で二重に実装することになるため、対策として共有ライブラリ、またはテストベクタ(入力と期待 ID の組)の共有を選択肢とする(構成は変えない) | 確定(K66、K60)。未決部分: 二重実装の対策(共有ライブラリ / テストベクタ / 対策しない)、失敗種別名の仮名(API-U-24) |
| API-U-8 | 原本サイズ超過の具体(上限、記録先・項目、ジョブ status への影響。件数照合は `oversize_document_ids` を別項目にする案。4.4)(architecture U-5)。**確定(architecture K65。ユーザー承認 2026-11-11(0002 §3 #1))**: すでに索引にある同じ文書は書き換えず、そのまま残す | 確定(K65)の部分あり。上限の値・記録先・ジョブ status への影響は未決 |
| API-U-9 | **確定(architecture K50)**: バッチ登録応答の `change` は `created`(新規)/ `updated`(本文またはメタデータの変更があり全文書き込みをした。メタデータのみの更新を含む)/ `unchanged`(変更がなく全文書き込みをしなかった)。`last_seen_at` だけの更新は `updated` に含めず `unchanged`。再送の数え直しは API-U-16 | 確定(K50) |
| API-U-10 | **確定(architecture K66。ユーザー承認 2026-11-11(0002 §3 #17))**: Status API の 404 条件(保持件数を超えて消えた、開始通知を受けていない、`loreley-deletions` を失った場合を区別せず 404 `crawl_not_found`)(architecture 9.5。P1)。`waiting_for` の実装も同じ承認。**案のまま(実装で採用中)**: `finished_at`(削除結果の `ended_at`)の項目(4.5)。状態名の一覧(architecture P25)も案(4.5) | 確定(K66)。`finished_at` の項目は案 |
| API-U-12 | 開始通知の 409 条件、`failed` 時の終了通知の項目省略可否、ソース削除の順 2(4.7)の非同期化(終了通知の再送の扱いは確定。architecture K25。API-U-21)。実装は、`failed`・`cancelled` の終了通知で項目の省略を受理し、順 2 は同期で応答する(実装で採用中) | 案の確定 / 修正 |
| API-U-13 | **確定(architecture K66。ユーザー承認 2026-11-11(0002 §3 #5))**: `lock_not_owned` を文書単位の結果に加える。バッチ途中でロックを失ったときは、確認済みの文書の結果を返し、最初の失敗以降の未処理の文書も書かずに `lock_not_owned` とし、リクエスト全体は 200(バッチの先頭での失敗も同じ)(3.2、3.4、4.2、4.3)。ロック文書なし・リース切れ・所有者不一致はすべて不所有(architecture U-4) | 確定(K66) |
| API-U-14 | **確定(architecture K60。ユーザー承認 2026-11-11(0002 §3 #8)・2026-11-12(0021 §1))**: ソース削除の `lock` は JSON ボディで運ぶ(`DELETE` も)。順 2・3 は必須で所有を確認し(409 `lock_not_owned`)、順 1 は受け取るが確認しない(3.2、4.6〜4.8)。**確定(architecture K29。2026-11-10)**: ジョブが `source_id` 単位のロックを最後まで保持し、ロック文書の削除を最後にする。4.7・4.8 の要請にロック所有情報を添える。Crawler 向け要件(4.6): (1) 削除中はリースを更新し続ける、(2) 所有権を失ったら後続の削除操作を停止する、(3) 再実行で復旧する、(4) 削除中のデータソースに新しいクロールを起動しない。**未決(Crawler 領域)**: 「削除中」状態の置き場所、Crawler 側のロック設計の具体、discard の応答待ちの間にリースが切れた場合の扱い(4.6)(architecture U-4、9.14)。4.7・4.8 は何度でも再実行でき、リース切れの `lock_not_owned` はジョブ `failed` で止まり再実行で完了する | 確定(K29、K60)。未決部分は Crawler 設計で決める |
| API-U-15 | **確定(architecture K66。ユーザー承認 2026-11-11(0002 §3 #4))**: Indexer は `raw_content` の SHA-256 を計算せず、`content_hash` と照合しない(Crawler の値を信用する)(4.3。architecture U-26) | 確定(K66) |
| API-U-16 | 再送時の `created` / `updated` / `unchanged` の集計(`change` の区分は architecture K50 で確定)。案は、Crawler が `document_id` ごとに最初に受け取れた結果を保持し、再送の結果では数え直さない規則。応答が失われた場合の集計は厳密でない(`created` が `unchanged` と数えられうる)。`unchanged_count` は Crawler 領域の集計項目(名称は案)。メタデータのみの更新は `updated`(確定。architecture K50。API-U-9) | 推奨を採用 / 修正 |
| API-U-17 | `raw_content` の運び方と上限。base64 は約 33% 増えるため、原本の上限・バッチの件数と合計サイズ・メモリ使用量を実測して決める(architecture 15.4) | JSON + base64 / multipart / 文書ごとの個別送信 |
| API-U-18 | **確定(architecture K23。2026-11-10)**: 登録の受理条件の採否(旧 architecture U-28。K23 で確定)。バッチ登録・`last_seen_at` 部分更新を、`deletion_result` の存在・`source_id` 一致・`crawl_started_at` の照合・`running`・終了通知の受理前・ロック所有、のすべてを満たすときだけ受理する(3.2、4.2、4.3)。終端状態への登録の拒否、存在しない `deletion_result` の扱い、ソース削除の要請を対象外とすることを含む。拒否のコード名は API-U-19 | 確定(K23。受理条件を課し、終端状態・受理済み・存在しない結果は拒否) |
| API-U-19 | **確定(architecture K66。ユーザー承認 2026-11-11(0002 §3 #15))**: 登録の拒否のエラーコード名・HTTP(すべて 409)。`crawl_not_started`(`deletion_result` が存在しない。未送信、保持期間超過、`loreley-deletions` の喪失)、`crawl_source_mismatch`(`source_id` 不一致)、`crawl_started_at_mismatch`、`crawl_already_closed`(終端状態)、`crawl_finished`(`running` だが終了通知の受理後)。開始通知の再送の不一致は `crawl_start_conflict`(API-U-20)。いずれも Crawler はリトライせずジョブ `failed`。architecture K23。受理条件そのものは architecture K23 で確定。Crawler の扱い(リトライせずジョブ `failed`)は Crawler の領域(案) | 確定(K66) |
| API-U-20 | 開始通知の再送の一致検証(4.1)。**確定(architecture K24。2026-11-10)**: 同じ `crawl_id` で `running` のとき、複写済みの項目(`source_id`、`crawl_started_at`、`ttl`、`ratio_threshold`、`min_delete_count`、`force_delete`)と直接比較し、一致なら成功(状態不変)、不一致なら 409(状態不変)。**確定(architecture K33、K37)**: 比較項目に `rewrite_mode` を加える。省略は `false` に正規化して複写し、比較も正規化後の値で行う(省略と `false` の違いでは 409 にしない)。**確定(architecture K66、K59。ユーザー承認 2026-11-11(0002 §3 #14、#15))**: コード名 `crawl_start_conflict`(409)。`ttl` などの値の型(整数・有限の数値・整数・真偽値)が確定し、比較は正規化後の値で行う(`crawl_started_at` はミリ秒精度の UTC、`ratio_threshold` は数値として) | 確定(K24、K33、K37、K59、K66) |
| API-U-21 | 終了通知の再送(4.4)。**確定(architecture K25。2026-11-10)**: 案 B。記録済みの再送で内容が最初に受理した内容と異なれば 409、同じなら 202。終了通知のダイジェスト(`finish_request_digest`。`outcome`、`enumerated_count`、重複除去・ソート済みのスキップ文書 ID 一覧とサイズ超過文書 ID 一覧の正規化 SHA-256。`finished_at` は除く)を `deletion_result` に保存し、Crawler は最初の通知内容を `loreley-jobs` に保存して固定する。受理の有無は Status API の現状の項目で読める(4.5)。**確定(architecture K32。2026-11-10)**: 処理の前に `source_id` と `deletion_result.source_id` の一致を確認し、不一致なら 409(状態不変)。未知の `crawl_id` は 202 のまま。**確定(architecture K38、K40、K43)**: 処理順は形式検証(400)→ `source_id` の照合(409)→ ダイジェストによる再送判定 → 初回受理。409 のエラー名は `finish_source_mismatch`、`finish_content_mismatch`。409 は共通エラー形式でコードと短いメッセージだけを返し、最初に受理した終了通知の全文・ダイジェスト・受理済みの状態の詳細は返さず、Status API で確認する | 確定(K25、K32、K38、K40、K43) |
| API-U-22 | 再書き込みモード(**採用は確定。architecture K26。2026-11-10**)。**保持先と再送判定は確定(architecture K33)**: `deletion_result` の設定スナップショットに保持し、バッチ登録は受理条件の確認で取得した `deletion_result` から参照する。開始通知の再送の一致検証(API-U-20)の比較項目に含める。**確定(architecture K41)**: 名称は `rewrite_mode`、指定経路は開始通知の任意項目 | 確定(K41) |
| API-U-23 | Crawler との突き合わせ(architecture U-34。**項目番号は architecture U-34 と同じではない**。対応は、本欄の (1)(2)(3)(6)(7) が U-34 の (1)(2)(3)(6)(8)、本欄の (4) が U-34 の (5)、本欄の (5) が U-34 の (4)。U-34 の (6) のうちメンテナンスフラグの形式と、(7) のインデックス名・マッピングの前提は API-U-24)。Indexer の実装が採った規則のうち、Crawler の設計・実装が前提を満たす必要があるもの。(1) `external_id` の先頭の `/` を Indexer は除去しない(Crawler が `document_id` を同じ規則で算出すること。3.3)。(2) `content_hash` は小文字 64 桁の 16 進(大文字は全体 400。4.3)。(3) `DELETE` に `lock` のボディを載せられること(3.2、4.7、4.8)。(4) ID の長さの上限(`source_id`・`crawl_id`・`lock.*` は 256 バイト、`external_id` は 4096 バイト。いずれも検証の規則としての仮値。超えると全体 400。3.3)。(5) 孤立サロゲート(Linux で CP932 のファイル名を読むと生じうる)を `external_id` などの ID 類に含めないこと(全体 400。`title`・`mime_type`・`path`・`url` は文書単位の `document_rejected`。3.3)。(6) ロック文書の形式(項目 `owner`・`job_id`・`lease_expires_at`。3.2)。(7) Crawler が、文書単位の `oversize` の結果から ID を集めて、終了通知の `oversize_document_ids` に入れること(Crawler 領域。案。architecture U-34 の (8)、P32。4.3、4.4、4.9) | Crawler の設計を Indexer の実装に合わせる / 規則を変える(Indexer を修正する) |
| API-U-24 | 設計書に定義がなく、Indexer の実装が仮に置いた名前・形式(案のまま。実装で採用中。Crawler・infra の設計の確定時に再確認)。失敗種別名 `oversize`(4.3)、削除結果の理由コード名(`failed` と `validation_failed`。4.5)、`not_found`・`method_not_allowed`・`http_error` のエラーコード(3.4)、索引名(`loreley-documents`(エイリアス想定)・`loreley-deletions`・`loreley-jobs`。仮名)、メンテナンスフラグの形式(`loreley-jobs` の ID `maintenance`、項目 `enabled`。文書があり `enabled` が真偽値の `false` と明示されているときだけ「立っていない」とみなし、それ以外は「立っている」とみなす(fail-closed。architecture K63))、マッピングの前提(`document_id` を keyword としてソートに使える。削除記録の `record_type`・`status`・`source_id` が keyword。実機での確認は architecture U-31) | 案を採用 / 修正 |

---

## v0.9 からの変更点

Indexer の実装(2026-11-11〜12)で採用され、ユーザーが承認した内容の記録である。新しい要件は加えていない。数値の既定値・上限値は書かず、設定名だけを示す(値は `apps/indexer/README.md` の 3 章)。承認の記録がなく案のままのもの(エンドポイント形、キー名、`oversize` などの名前)は、区分を変えず「実装で採用中」と注記した。architecture の K57〜K71 は `indexer-architecture-v0.10.md` の 17章に対応する。

| v0.9 | v0.10 |
| --- | --- |
| 1章: `/healthz` の記述なし。3.1: 認証なしの注意なし | 1章: `GET /healthz`(契約外)は起動時の整理の完了後にだけ応答し、それまで全パスが 503(K67)。外からは接続拒否に見える(3.3、3.4 も同じ表現に統一)。Crawler が 503 と接続エラーの両方をリトライすることは「Crawler 領域。案」と注記。3.1: 認証なしの API を外部に公開しない注意と、`DELETE` で全文書を削除できること |
| 3.2: `lock` の運び方は提案。`DELETE` での運び方は未定。ロック失敗時の部分結果は未決(API-U-13) | `DELETE` の `lock` は JSON ボディ。ソース削除 2・3 は必須で所有確認(409 `lock_not_owned`)、1 は受け取るが確認しない(K60)。登録・`last-seen` の部分結果は、確認済みの結果を返し、最初の失敗以降の未処理の文書も `lock_not_owned`、全体は 200(K66) |
| 3.3: `external_id` は「先頭に `/` を付けない」とだけ記載。検証規則の記述なし | 先頭の `/` は除去しない(Crawler の前提。K58)。「入力の検証規則」の小節を追加(型は strict で範囲は検証しない、未知の項目は無視、ID の文字・長さ、`content_hash` は小文字 64 桁の 16 進、ID 一覧の要素、孤立サロゲートの分担、`skipped_count` は型のみ、上限超過は 400、起動前は 503。K59) |
| 3.4: コード名・HTTP は案。`not_found` などの行なし | 登録の拒否・開始通知・`crawl_not_found`・`lock_not_owned`・`internal_error`・`unavailable` のコード名と HTTP は確定(K66、K60)。`not_found`・`method_not_allowed`・`http_error` の行を追加(案。実装で採用中)。`retryable` の値を明記 |
| 3.5: 連続 20 件の打ち切りの主体の記述なし。`store_error` を候補に記載(4.3) | 連続 20 件の打ち切りは Crawler 側の規則で、Indexer は数えない。OpenSearch 全体の異常はリクエスト全体の 503 で、`store_error` は返さない(K66) |
| 4.1: `ttl` などの型は未定。書き込み順は「更新→作成→superseded 化」の記述。再送の比較前の正規化は未決(API-U-20) | `ttl`(整数)・`ratio_threshold`(有限の数値)・`min_delete_count`(整数)・`force_delete`/`rewrite_mode`(真偽値)に確定し、再送は正規化後の値で比較(K59)。書き込み順は世代の更新→旧い結果の `superseded` 化→結果の作成(結果の作成を最後のコミット点にして再送を収束させる。K57)。書き込み競合が上限を超えたら、結果を作らずに止まる 503(案。実装で採用中) |
| 4.2: 要請の単位は未決。`update_conflict` を全体の失敗にするかは未決 | 要請の単位は Crawler が算出した `document_id` の配列で、件数に上限あり(超えると 400)。`update_conflict` は文書単位、索引全体の異常は 503(K66) |
| 4.3: `content_hash` の照合は未決。`fetched_at`・`metadata` の扱いは未決。サイズ上限超過の応答は未決。`failure_type` に `store_error` | `content_hash` は照合しない。`fetched_at`・`metadata` と未知の項目は無視(K59、K66)。「サイズの防御」(推定サイズが上限を超える文書は文書単位の `oversize`、合計・ボディ超過は全体 400。K59、K65)と「文書ごとの処理の順」を追加。`failure_type` は `document_rejected`・`oversize`・`lock_not_owned`・`write_conflict`・`update_conflict`(`store_error` を削除) |
| 4.4: `skipped_count` は必須。ダイジェストの正規形、`failed`・`cancelled` の保存項目、ID 一覧の件数・フラグの記録の細目なし。未知の `crawl_id` を記録しない扱いは案(P16) | `skipped_count` は任意で、型のみ検証し値を使わない。ダイジェストの正規形(省略と空配列は別の値)、`failed`・`cancelled` の保存項目、件数・フラグは上限以内でも記録、受理の書き込み競合が上限を超えたら 503 を追記(これらの細目は案。実装で採用中)。未知の `crawl_id` は 202 で、ログに `crawl_id` だけを残す(確定。K66) |
| 4.5: `waiting_for` は任意で要否は未決。404 条件は未決。`reason` は `failed`・`discarded` のみ。`deleted_count` の記録の規則なし。しきい値の型は未定 | `waiting_for` と 404 の条件を確定(K66)。`finished_at` は削除結果の `ended_at`(案。実装で採用中)。`reason` に `validation_failed` を追加。`deleted_count` はバッチごとに記録して減らさず、起動時の整理で未記録なら 0(K62)。値のない項目は省く。しきい値の型を確定 |
| 4.6〜4.8: `lock` の運び方・所有確認は案。discard の試行上限超過・再実行の上限超過の応答は案。排他の記述なし | `lock` は JSON ボディ(K60)。discard の試行ラウンド数と `delete_by_query` の再実行の上限を超えたときは再試行可能な 503 `unavailable`(確定。K61。応答に理由は出さず、ログの理由名 `discard_conflict`・`documents_remaining` は案。実装で採用中)、削除専用のソース単位の排他(ソース削除を優先。K61。ソース削除 1・2 が使い、3 は使わない)、`delete_by_query` 専用クライアント、順 2 の所有確認は実行(再実行を含む)の前ごと(K61)。「最優先」の意味(応答の時点で削除バッチが動いていないこと。P29)は案のまま |
| 4.9: 拒否主体・既存の索引データを残すかは未決(API-U-4、API-U-8) | Indexer も拒否し(文書単位の `oversize`)、すでに索引にある文書は書き換えない(K65) |
| 6章: 確定は K12、K18〜K56。API-U-4、API-U-6〜API-U-8、API-U-10、API-U-13、API-U-15、API-U-19、API-U-20 は未決または案 | これらを「確定(Kxx)」として表に残し(欠番にしない)、確定は K57〜K63、K65〜K67 を加えた。区分ごとの整理に確定行を追加し、案の行から確定した項目を外した。API-U-10 は 404・`waiting_for` を確定とし、`finished_at` の項目は案に残した。実装で採用中の細目(`finished_at`、P29 の意味、ログの理由名、受理まわりの細目、`last-seen` の空配列)は案の行にまとめた。新しい未決として API-U-23(Crawler との突き合わせ。architecture U-34。項目番号は U-34 と同じではなく、対応を欄内に注記。(7) として、Crawler が `oversize` の結果から `oversize_document_ids` を集めることを含む。Crawler 領域・案)と API-U-24(実装が仮に置いた名前・形式)を追加。承認の根拠は、0021 の §1・§2 が名指ししたものだけ節番号まで書いて確定とし(K60 は「0002 §3 #8、0021 §1」)、名指しされていないものは「案(実装で採用中)。0020 §6-2(0021 で全て承認)」に揃えた |
| 例 JSON: 開始通知・Status の `ttl` などは `"<値は未決>"`。4.3 の `message` の例は `mapping violation`。4.2 の空の `document_ids`、4.1〜4.5 のエラー表の「5xx / 接続エラー」行、3.3 の見出し、4.9 の導入文は旧記述 | 例 JSON の `ttl` などは v0.9 のまま `"<値は未決>"`(具体値の例は載せない。ユーザー判断 2026-11-12)。4.3 の `message` の例を実装の文言の形に寄せ、4.5 の例に「一部の項目だけ」の注記を足した。`last-seen` の空の `document_ids` の扱いを追記(案。実装で採用中)。エラー表の重複行を 3.4 の表に合わせて 503・500・接続エラーの行に整理(4.5 に 503 の行を追加)。3.3 の見出しを「ID と入力の検証規則」に、4.9 の導入文を「未決事項」から「事項」に変更。ID 長・整数の 64 ビットの範囲は検証の規則としての仮値と注記 |
| 関連文書: architecture・search-index・loreley-deletions の v0.9 | 同 v0.10(ファイル名の参照を新しい版に更新) |

- 変えていないもの: エンドポイント形、JSON のキー名、5 章(Crawler 側のポーリング規約)、API-U-1・API-U-5・API-U-12・API-U-16・API-U-17 の未決、API-U-14 の Crawler 領域の未決(Indexer 側の `lock` の部分だけ K60 で確定)。状態名の一覧(architecture P25)は案のまま(実装で採用中)。
- 確定にしたのは、ユーザーが承認したもの(2026-11-11 の実装プランの 22 項目(作業記録 `0002` §3)と、2026-11-12 の追加承認(同 `0021` の §1・§2)、K63 の `0014`)に限る。個別の承認記録がないもの(0020 §6-2。0021 で全て承認)は案(実装で採用中)にとどめた。Crawler・infra の設計に依存する名前・形式(ロック文書、メンテナンスフラグ、索引名、`oversize` など)は案のままで、API-U-23・API-U-24 に集約した。
