# Crawler API リファレンス v0.2

- 版: v0.2
- 更新日: 2026-11-13
- 前版: `crawler-api-v0.1.md`
- 位置づけ: Admin API が Crawler に対して呼ぶ内部 API(クロール起動、取り消し、ロック解放、データソース設定の登録・更新、ソース削除ジョブの起動)の契約を定める。入出力・拒否条件・エラー・冪等性だけを書き、ジョブの内部挙動(状態遷移、ロック、リース、リトライなど)は `crawler-architecture-v0.2.md` を参照する。
- 本書は「案」「推測」「未決」を確定扱いにしない。本書で「確定」にできるのは、ユーザー回答(Q1、および 2026-11-13 の確定。作業記録 0010)と、Indexer 設計書・PD v0.19・`crawler-architecture-v0.2.md` で既に確定している事項だけ(5.2)。**エンドポイントのメソッド・パス、リクエスト/レスポンスの形、JSON のキー名、エラーコード名は案**。数値は「仮値・設定可能・未決」とする。
- Admin API の設計書がまだないため、本書が契約を先行定義する(CAPI-U-1)。
- v0.2 の改訂: architecture v0.2(外部レビューの反映。ユーザーが確定したものだけを確定とした)への追従。
  - `connector_config` の確定時点を、architecture 4.5 の手順 6 の 1 回の読み取りに改めた(2.2、4.4.1、5.7。architecture CA-P-51)。
  - 確定(ユーザー回答 2026-11-13。作業記録 0010): データソース設定の「削除」はソース削除ジョブの起動で、設定だけを消す API は置かない(4.5。CAPI-K-8。architecture CA-K-22)。CAPI-P-11 は CAPI-K-8 に移した。CAPI-U-1 のうち「設定の削除」の解釈の確認は解消し、Admin API 設計の不在は未決のまま残した。
  - 新規 ID: CAPI-K-8。解消: CAPI-P-11(CAPI-K-8 へ移行)、CAPI-U-1 の一部。更新: CAPI-K-1、CAPI-U-1。関連文書に `crawler-design-decisions-v0.1.md` を追加。
  - 本書の応答には `settings_snapshot`・`warnings` の項目がないため(読み取りは Admin API が `loreley-jobs` を直接読む。2.3)、`settings_source_updated_at`(`settings_snapshot` の外の最上位項目。architecture 3.3.1)と 0 件警告(CA-P-52)に伴う変更はない。起動時の整合性検査(CA-P-55)は受付に影響せず、本書の対象外。

## 0. この文書について

- 対象: Admin API -> Crawler の呼び出し(1章の 6 つの API)。
- 範囲外(参照のみ):
  - Crawler -> Indexer の呼び出し(architecture 7章)
  - ジョブの内部挙動(architecture 3〜9章)
  - `connector_config` の項目と検証の中身(各 Connector 文書)
  - Admin API -> Web UI の契約(Admin API 設計。未作成)
- 読み方: 1章で API の全体、2章で呼び出しの流れ、3章で共通事項、4章で各 API を同じ書式(概要 / エンドポイント / 呼び出し元 / リクエスト / レスポンス / エラー / 冪等性・注意事項 / 確認状況)で読む。5章に確認状況と未決をまとめた。

区分の凡例(Indexer 設計書に合わせる):

| 区分 | 意味 |
| --- | --- |
| 確定 | ユーザーが確定した事項(出典を書く) |
| 案 | ユーザー未確定。確定扱いにしない |
| 未決 | 決めていない |
| 推測 | 根拠が弱い想定。推測と注記した事項 |
| 導出 | 他の仕様から導いた事項(明示された記述がなく、本書で導いた事項) |

ID 体系: 本書の確定・案・未決は `CAPI-K-n` / `CAPI-P-n` / `CAPI-U-n`。既存設計との不整合は `I-n`(本書の予約範囲は I-20〜I-29。I-1〜I-7 は architecture 13.5、I-10・I-11 は interface 11.5 を参照するだけで、本書では定義しない)。`CA-*` は architecture、`CI-*` は interface のもの。

関連文書:

| 文書 | 内容 | 本書との関係 |
| --- | --- | --- |
| `crawler/crawler-architecture-v0.2.md`(以下 architecture) | ジョブ状態、受付の手順、ロック・リース、`loreley-sources`・`loreley-jobs` のデータモデル、ソース削除ジョブ | 正本。本書は再掲せず、章を参照する |
| `crawler/crawler-design-decisions-v0.1.md`(以下 decisions) | 実装着手のための短い決定事項(採用方針、ユーザー確定事項、実装を妨げる未決、実装者が決めてよい事項) | 要約。本書・architecture が正本で、食い違えば本書・architecture を正とする |
| `crawler/connector/connector-interface-v0.2.md`(以下 interface) | `connector_type`・`connector_config` の責務境界(8章)、`validate_config`(3.2)、エラー分類 | 同上 |
| `crawler/connector/connector-file-system-v0.2.md`、`connector-web-v0.2.md` | `connector_config` の項目と検証 | 本書は中身を見ない(不透明) |
| `indexer/indexer-api-v0.10.md`(以下 indexer-api) | Crawler -> Indexer の契約 | 範囲外。エラー応答の書き方(3.4)だけ参考にした |

決定事項の出典として、SD v0.8(14.2、14.4、14.7)と PD v0.19(4.6、4.7、5.2)を参照した。SD v0.8 は廃止予定のため、本書は自文書で完結させ、SD への参照は出典の注記にとどめる。

---

## 1. API 一覧

| API | メソッド + パス(案) | 呼び出し元 | 用途 | 冪等性 | 確認状況 | 詳細 |
| --- | --- | --- | --- | --- | --- | --- |
| クロール起動 | `POST /sources/{source_id}/crawl-jobs` | Admin API | 手動でクロールジョブを起動する。`force_delete`・`rewrite_mode` を指定できる | 冪等でない。重複起動はロックで拒否される(409 `lock_held`)。応答が失われた後の再送も同じ 409 になり、受付済みのジョブを確認できる | 操作は確定(Q1)、パス・入出力は案 | 4.1 |
| 取り消し | `POST /jobs/{job_id}/cancel` | Admin API | `crawl` ジョブを取り消す | 冪等(重複しても 1 回と同じ。終了済みは 409 でジョブの状態を返す) | 同上 | 4.2 |
| ロック解放 | `DELETE /sources/{source_id}/lock` | Admin API | 実行中でないロック(リース切れ・孤児ロック)を解放する | 冪等(ロックがなければ何もせず 200) | 同上 | 4.3 |
| 設定の登録 | `POST /sources` | Admin API | データソース設定を新規登録する | 冪等(同じ内容の再送は 200。内容が異なれば 409) | 同上 | 4.4 |
| 設定の更新 | `PUT /sources/{source_id}` | Admin API | データソース設定を置き換える | 冪等(同じ内容は書き込まず 200) | 同上 | 4.4 |
| ソース削除ジョブ起動 | `POST /sources/{source_id}/delete-jobs` | Admin API | データソースの削除(全文書・記録・設定の削除)をジョブとして起動する | 冪等でない(クロール起動と同じ) | 同上 | 4.6 |

本書に置かないもの:

- **設定レコードだけを削除する API**: 置かない。データソースの削除はソース削除ジョブ起動(4.6)で行う(確定。4.5。CAPI-K-8)。
- **読み取り API**: ジョブ状態・登録結果・確認結果の区分・削除結果は Admin API が `loreley-jobs`・`loreley-deletions` を読み取りのみで直接読むため、置かない(2.3)。データソース設定の取得・一覧の経路は未決(CAPI-U-2)。
- **定期起動**: Scheduler が Crawler 内部で行い、API ではない(architecture 4.3)。
- **メンテナンスフラグの操作**: 置かない(Q1 の範囲外。architecture 7.9)。
- **ヘルスチェック**: 要否は未決(CAPI-U-9)。

---

## 2. 概要

### 2.1 呼び出しの流れ

```text
Admin View -> Admin API --HTTP(本書の API)--> Crawler
                 |                              受付(同期): 検査 -> ロック取得 -> ジョブ `queued` を保存 -> 応答
                 |                              Job Runner(非同期、直列): ジョブを実行(architecture 4.5)
                 +-- 読み取りのみ --> loreley-jobs / loreley-deletions(ジョブ状態・登録結果・削除結果)
```

- Admin API は、起動などの「操作」だけを Crawler に中継する。状態の表示は Admin API が自分で読む(2.3)。
- 起動系 API(4.1、4.6)の受付は同期で、成功すれば `queued` のジョブを保存して `job_id` を返す。実行は応答の後に非同期で進む。

### 2.2 同期・非同期の別

| API | 応答の時点で済んでいること | 応答の後に進むこと |
| --- | --- | --- |
| クロール起動 | 検査、ロック取得、ジョブ(`queued`)の保存 | ジョブの実行(architecture 4.5) |
| ソース削除ジョブ起動 | 同上 | ソース削除の手順(architecture 8.1。実行開始時に `status=deleting`) |
| 取り消し | `queued` のジョブ: 取り消し完了(200)。`running` のジョブ: 要求の受付のみ(202) | Job Runner が次の確認点で止め、`cancelled` にする(architecture 4.6、4.7) |
| ロック解放 | ロック文書の削除、`running` のジョブの `failed` 化 | なし |
| 設定の登録・更新 | `loreley-sources` への保存 | なし(反映の境界は、ジョブが `loreley-sources` を読む時点(手順 6。`queued` -> `running` の遷移の直後)。それより前の更新は反映され、後の更新は反映されない。`connector_config` も同じ読み取りで確定する。4.4.1) |

### 2.3 状態の読み取り API を置かない理由

- `loreley-jobs` に書くのは Crawler だけで、Admin API は読み取りのみで直接読む(確定。CAPI-K-5)。ジョブの状態・登録結果・確認結果の区分・削除結果の表示は、この直接読み取りで足りる(architecture 2.1、2.2。CAPI-P-16)。
- 本書の応答にジョブの情報を載せるのは、受付直後に `job_id` と受付結果を知るための最小限の項目と、拒否時の既存ジョブの情報(4.1 の `details.existing_job`)だけ。
- Crawler に届かないときも、ジョブ状態と削除結果の表示は読み取りで続けられる(推測。architecture 9)。

---

## 3. 共通事項

### 3.1 通信方式と公開範囲

- Admin API(別コンテナ `api`)から Crawler(別コンテナ `crawler`)への HTTP。リクエスト・レスポンスは UTF-8 の JSON(`Content-Type: application/json`)。メッセージブローカーは使わない(architecture CA-K-1)。呼び出しは同期。
- 内部ネットワークだけで通信し、ホストに公開しない。Web UI や外部のクライアントから直接呼ばない(案。CAPI-P-1。architecture 10 の方針に合わせる)。
- **認証はない(MVP。確定。CAPI-K-7)**。到達できる呼び出し元は、ソース削除ジョブ(4.6)で任意のデータソースの全文書を消せ、ロック解放(4.3)や取り消し(4.2)もできる。公開しないことが唯一の防御になる(Indexer API と同じ前提。indexer-api 3.1)。
- ベース URL・ポートは本書では決めない(デプロイ設定。architecture 10)。
- Crawler は、起動時の回復(architecture 5.8)が終わるまで受付を始めない(architecture 10、CA-P-40)。Admin API からは接続エラーに見える。Admin API の扱いは Admin API 設計(CAPI-U-1)。

### 3.2 ID と入力の検証

- **`source_id`**(パスと本文): 空でない、制御文字を含まない、UTF-8 で 256 バイト以内(確定。CAPI-K-6)。加えて、文字種を「半角英数字で始まり、半角英数字・`.`・`_`・`-` だけ」とする(案。CAPI-P-15。architecture CA-U-15 への対応。最終決定は CAPI-U-4)。理由: `source_id` は URL のパス(`/sources/{source_id}/...`。Indexer への呼び出しを含む)と、`lock-{source_id}` などの記録の ID に使われるため、`/`・`%`・`?`・`#`・`..` などを入れさせない(導出)。違反は 400 `invalid_request`。`source_id` は大文字と小文字を区別する(OpenSearch の ID が区別するため。導出)。
- **`job_id`**(パス): 256 バイト以内・制御文字なしの検証(CA-K-13 と同じ規則。違反は 400 `invalid_request`)の後、`loreley-jobs` の `record_type=job` の記録だけをジョブとみなす(案。CAPI-P-18)。`loreley-jobs` にはジョブのほかにロック(`lock-*`)・スキップ記録・原本サイズ超過記録・メンテナンスフラグが同居するので、それらの ID は 404 `job_not_found` とする。architecture 3.3 も同じ扱いを定めている。
- **JSON は厳密(strict)に扱う**(案。CAPI-P-14)。数値・真偽値を文字列などから変換しない(例: `force_delete` が `"true"`、`ttl` が小数は 400)。Crawler はこれらの値を、そのまま Indexer に厳密な型で送るため(architecture 7.4)。`NaN`・`Infinity` など JSON にない定数は 400。
- **未知の項目は 400**(案。CAPI-P-14)。Admin API の項目名の取りこぼしや綴りの誤りを検出するため。indexer-api 3.3 は未知の項目を無視するので、逆の方針になる(本 API は、Admin API との契約違反を早く見つける側に倒した。導出)。読み取り専用の項目(4.4 の表)を含めた場合も 400。`connector_config` の中身は Connector が検証する(4.4)。
- 400 のエラー本文には、入力の値を含めない(認証情報の参照名などが漏れないように。導出)。

### 3.3 エラー応答の形

Indexer API(indexer-api 3.4)と同じ形にそろえ、`details` を加える(案。CAPI-P-13)。

```json
{
  "error": {
    "code": "lock_held",
    "message": "the source is locked by another job",
    "retryable": false,
    "details": { }
  }
}
```

- Crawler 自身のエラーの `message` は固定文で、文書の本文・認証情報を含めない。`config_invalid`(4.4)だけは、Connector の説明文(項目名・違反の種類など。errno 名・切り詰めた相対パスを含みうる)をそのまま入れる(interface 6.1、CI-P-17)。
- `retryable` は、503 `unavailable` だけ `true`。
- `details` は任意。`invalid_request` では `errors`(`field`・`reason` の配列)、拒否では `existing_job`(4.1)などを入れる。
- `reason` の値(案):

  | `reason` | 意味 |
  | --- | --- |
  | `required` | 必須の項目がない |
  | `type` | 型が違う(厳密な型。3.2)。`NaN` などの JSON にない定数、有限でない数値を含む |
  | `format` | 形式の違反(`source_id` の文字種・長さ・制御文字、`schedule_interval_seconds` が 1 未満など) |
  | `read_only` | 変更できない項目を含めた(`status`・`updated_at`、更新での `source_id`・`connector_type`) |
  | `unknown_field` | 定義にない項目を含めた |
  | `unsupported` | 登録されていない `connector_type` |

全 API に共通のエラー:

| HTTP | `code`(案) | 意味 |
| --- | --- | --- |
| 400 | `invalid_request` | 形式不正(3.2)。JSON として不正な本文を含む |
| 404 | `not_found` | 未定義のパス(indexer-api 3.4 の `not_found` に倣う) |
| 405 | `method_not_allowed` | 未定義のメソッド(同上) |
| 404・405 以外 | `http_error` | 上記以外の HTTP 例外(同上。HTTP ステータスはそのまま) |
| 500 | `internal_error` | Crawler の想定外の異常(Connector の `connector_internal_error` を含む)。`retryable=false` |
| 503 | `unavailable` | Store 層(OpenSearch)の読み書きがリトライしても失敗した(architecture 9)。`retryable=true` |

- 起動系の受付の途中(ロック取得の後、ジョブ保存の前)で 503 になると、ジョブのないロック(孤児ロック)が残りうる(architecture 4.3 の手順 5)。孤児ロックは Crawler の起動時の回復(architecture 5.8)か、ロック解放(4.3)で消す(ロック解放は、取得から直近の間は 409 `lock_in_use` で拒否する。4.3)。

### 3.4 冪等性・再送

- Admin API は、応答が失われたときに再送しうる。各 API の再送時の結果は 1 章の表と 4章に書いた。
- 起動系(4.1、4.6)は冪等でないが、ロックがあるので二重には起動しない。再送が 409 `lock_held` になった場合、`details.existing_job`(4.1 の表の項目)で受付済みのジョブを確認できる。それを成功とみなすかは Admin API の扱い(CAPI-U-5)。

### 3.5 時刻

- 応答の時刻(`queued_at`、`updated_at`、`lease_expires_at`)は UTC の ISO 8601・ミリ秒精度(例 `2026-11-13T01:02:03.456Z`)(architecture 2.5。CA-P-38)。リクエストに時刻はない。

---

## 4. API リファレンス

### 4.1 クロール起動

**概要**: 手動でクロールジョブ(`job_type=crawl`、`trigger=manual`)を起動する。受付は同期で、architecture 4.3 の手順 1〜5 を行い、`job_id` を返す。実行(architecture 4.5)は非同期。受付の手順と実行の流れは architecture が正本で、本節は入出力と拒否だけを書く。

**エンドポイント**: `POST /sources/{source_id}/crawl-jobs`(案)

**呼び出し元**: Admin API(管理者の手動実行)

**リクエスト**(ボディは任意。省略は `{}` と同じ):

| 名前 | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `source_id`(パス) | string | ○ | データソース ID(3.2) |
| `force_delete` | boolean | 任意(既定 `false`) | 強制削除モード。指定できるのは手動実行のこの API だけ(確定。CAPI-K-2)。定期起動は常に `false`。ジョブに記録される(architecture 4.4)。厳密な真偽値 |
| `rewrite_mode` | boolean | 任意(既定 `false`) | 再書き込みモード。`force_delete` と同じく手動実行だけで指定でき、定期起動は常に `false`(案。CAPI-P-3。architecture 4.4)。`true` で運用する前の準備(要約生成の停止など)は Indexer の運用手順で、本書は定めない(architecture 4.4) |

```json
{ "force_delete": false, "rewrite_mode": false }
```

**レスポンス**(202。ジョブを `queued` で受け付けた):

| 名前 | 型 | 説明 |
| --- | --- | --- |
| `job_id` | string | ジョブ ID。Indexer の `crawl_id` と同値(architecture CA-P-1) |
| `job_type` | string | `crawl` |
| `source_id` | string | データソース ID |
| `status` | string | `queued` |
| `trigger` | string | `manual` |
| `force_delete`、`rewrite_mode` | boolean | ジョブに記録した値 |
| `queued_at` | datetime | 受付の日時 |

```json
{
  "job_id": "job-20261113T010203Z-3fa9c2d1",
  "job_type": "crawl",
  "source_id": "docs-share",
  "status": "queued",
  "trigger": "manual",
  "force_delete": false,
  "rewrite_mode": false,
  "queued_at": "2026-11-13T01:02:03.456Z"
}
```

(`job_id` の形式は architecture 3.3 の案。例の値は説明用。)

**エラー**(共通のエラーは 3.3):

| HTTP | `code`(案) | 条件 |
| --- | --- | --- |
| 404 | `source_config_not_found` | `loreley-sources` に設定がない(architecture 4.3 の手順 1) |
| 409 | `source_deleting` | ソース削除中のため新しいクロールを起動しない(確定の要件。CAPI-K-4)。その判定を設定の `status=deleting` で行うこと自体は案(architecture CA-U-2)。手順 4 の再確認でソース削除が入っていた場合を含む(architecture 4.3 の手順 4) |
| 409 | `maintenance_enabled` | メンテナンスフラグが立っている(architecture 7.9。`enabled` が真偽値の `false` と明示されていなければ「立っている」) |
| 409 | `lock_held` | そのソースのロック文書がすでにある(実行中・実行待ちのジョブ、またはリース切れ・孤児ロック) |

**`lock_held` の `details.existing_job`**(案。architecture 4.3 の「既存ジョブの状態を応答に含める」に対応):

| 名前 | 型 | 説明 |
| --- | --- | --- |
| `job_id` | string | ロック文書が指すジョブの ID |
| `job_type` | string または null | `crawl` / `source_delete`。ジョブ記録がない(孤児ロック)ときは null |
| `status` | string または null | ジョブ記録の状態。ジョブ記録がないときは null |
| `trigger` | string または null | `manual` / `schedule` |
| `lease_expires_at` | datetime または null | ロック文書のリース期限。`queued` のジョブのロックは null(architecture 5.1) |

`queued_at`・`force_delete`・`rewrite_mode` などの詳細は載せない。必要なら Admin API が `loreley-jobs` を直接読む(2.3)。

**冪等性・注意事項**:

- 拒否の判定順は architecture 4.3 の手順どおり(設定 -> メンテナンスフラグ -> ロック -> 再確認)。複数に当たるときは先に判定したエラーを返す。
- 重複起動(`lock_held`)で受け取った `force_delete`・`rewrite_mode` の指定は、既存のジョブに反映されない(architecture 4.4)。指定が無視されたことの通知は Admin API の領域(CAPI-U-5)。
- 設定の値(`ttl` など)が欠けている・型が合わない場合は、受付では検査せず、実行開始時にジョブが `failed`(`config_invalid`)になる(architecture 3.2)。4.4 の登録・更新で検査するため、通常は起きない。
- 受付の拒否を 409 の 3 種類に分けたのは、Admin API が原因ごとに表示を変えられるようにするため(案。CAPI-P-4)。メンテナンス中を 503 にする案もあるが、503 は Store 層の障害(`unavailable`)と区別しにくいため採らない。

**確認状況**: 操作の存在と `force_delete` の手動限定は確定(Q1。CA-K-17)。「削除中のデータソースに新しいクロールを起動しない」は確定(architecture CA-K-11 の要件(4))で、`status=deleting` で判定することは案(CA-U-2)。受付の手順は architecture 4.3 の案。パス、ボディ、ジョブの項目、202、エラーコード名、409 の分割、`details.existing_job`、`rewrite_mode` の手動限定は案(CAPI-P-2〜4)。

### 4.2 取り消し

**概要**: `crawl` ジョブを取り消す。対象は `crawl` ジョブだけで、`source_delete` ジョブは取り消せず、再実行で復旧する(案。architecture 4.7、CA-P-33)。状態別の扱いは architecture 4.7 が正本で、本節は受付と応答だけを書く。

**エンドポイント**: `POST /jobs/{job_id}/cancel`(案)

**呼び出し元**: Admin API(管理者の操作)

**リクエスト**: パスの `job_id` だけ。ボディは不要。

**レスポンス**:

| HTTP | 本文 | 意味 |
| --- | --- | --- |
| 200 | `{ "job_id": "...", "status": "cancelled" }` | `queued` のジョブを取り消した(取り消し完了) |
| 202 | `{ "job_id": "...", "status": "running" }` | `running` のジョブへの取り消し要求の受付のみ(取り消しは完了していない)。最終状態はジョブ記録で確認する |

- **202 の意味**: 要求は Crawler の実行中に保持され、ジョブ実行が次の確認点(architecture 4.6)で `cancelled` にする(伝達方式は architecture 4.7。Crawler プロセス内のメモリ上のフラグ。CA-P-44)。リース切れの `running`(Crawler が止まっている場合など)では、確認点に達せず完了しないことがある。その場合は 4.3(ロック解放)を使う。

**エラー**(判定はこの順。上から最初に当たったものを返す):

| 順 | HTTP | `code`(案) | 条件 |
| --- | --- | --- | --- |
| 1 | 404 | `job_not_found` | その `job_id` のジョブがない(3.2。ジョブ以外の記録の ID を含む) |
| 2 | 409 | `job_not_cancellable` | ジョブの種別が `source_delete`(状態を問わない。終了済みの `source_delete` もこれ) |
| 3 | 409 | `job_already_finished` | `crawl` ジョブがすでに終端状態(`succeeded` / `partially_succeeded` / `failed` / `cancelled`)。`details.status` に状態を入れる |

**冪等性・注意事項**:

- 取り消し要求が複数届いても、`running` のジョブには 202 を返すだけで結果は 1 回と同じ。すでに `cancelled` なら 409 `job_already_finished`(`details.status=cancelled`)で、Admin API は成功として扱える。
- `queued` の取り消しと実行開始が競合したときは、先に条件付き更新に勝った側が有効(architecture 4.7)。取り消しが負けたときは `running` として扱い、202 を返す。
- 202 は取り消しの受付だけを示す。受付の後にジョブが別の理由で `failed` などで終わることもある。
- **終了通知の送信を始めた後の取り消しは、Indexer の削除を止めない**(確定。architecture CA-K-9)。応答は同じ 202。送信を始めたかどうかは、ジョブ記録の `finish_notice.send_started_at` から読める(architecture 3.3.1)。Admin View でどう示すかは Admin API の領域(CAPI-U-6)。
- メンテナンスフラグは確認しない(architecture 7.9 の確認点に含まれないため。導出。CAPI-P-17)。

**確認状況**: 操作の存在は確定(Q1)。対象を `crawl` のみとすること、状態別の扱いは architecture の案。パス、200/202 の使い分け、判定順、エラーコード名は案(CAPI-P-5)。

### 4.3 ロック解放

**概要**: 管理者が、実行中でないロックを解放する。ロックがあるとそのソースのクロール・ソース削除を起動できないため(4.1 の `lock_held`)、止まったジョブ(リース切れ)や孤児ロックの後始末に使う。解放の手順は architecture 5.4 が正本で、本節は対象と入出力を書く。

**エンドポイント**: `DELETE /sources/{source_id}/lock`(案)

**呼び出し元**: Admin API(管理者の操作)

**リクエスト**: パスの `source_id` だけ。ボディは不要。データソース設定が存在しなくてもよい(ソース削除ジョブが設定を削除した後、ロック文書だけが残った場合に解放できるようにする。architecture 8.3)。

**レスポンス**(200):

| 名前 | 型 | 説明 |
| --- | --- | --- |
| `source_id` | string | データソース ID |
| `released` | boolean | ロック文書を削除したら `true`。ロック文書がなければ `false`(何もしていない) |
| `failed_job_id` | string または null | `failed`(`lock_released`)にした `running` ジョブの ID。なければ null |

**解放できるロック**(architecture 5.4 に基づく。`queued` のロックと受付途中のロックを対象外とすることは architecture の案。CA-P-47。最終決定は CAPI-U-7):

| ロック文書の状態 | 結果 |
| --- | --- |
| ジョブ記録がなく、`acquired_at` が直近でない(孤児ロック)。`acquired_at` が欠落・形式不正なら直近でないとみなす | 解放する |
| ジョブが終端状態(孤児ロック) | 解放する |
| ジョブが `running` で、`lease_expires_at` を過ぎている(リース切れ)。null・形式不正も期限切れとみなす(Indexer が null・形式不正を「所有していない」とするため。導出) | 解放し、ジョブを `failed`(`lock_released`)にする |
| ジョブが `running` で、リース期限内 | 解放しない。409 `lock_in_use`。`crawl` ジョブは取り消し(4.2)を使う。`source_delete` ジョブは待つ |
| ジョブが `queued`(`lease_expires_at` は null) | 解放しない。409 `lock_in_use`。`crawl` ジョブは取り消し(4.2)を使う(案。architecture 5.4、CA-P-47) |
| ジョブ記録がないが、ロック文書の `acquired_at` が直近(仮値。architecture 11章は 60 秒) | 解放しない。409 `lock_in_use`。受付の途中(ロック取得後・ジョブ保存前。architecture 4.3 の手順 3〜5)の可能性があるため(案。下記) |
| ロック文書がない | 何もしない。200(`released=false`) |

**エラー**:

| HTTP | `code`(案) | 条件 |
| --- | --- | --- |
| 409 | `lock_in_use` | 上表で解放しないロック。`details.existing_job`(4.1 と同じ形) |

**冪等性・注意事項**:

- **受付の途中との競合**: 受付はロック取得(手順 3)とジョブ保存(手順 5)の間に、ジョブ記録のないロックを一時的に作る。この間に解放を受けると、受付の途中のロックを孤児ロックと誤認して消しうる。防ぐために、ロック文書の `acquired_at`(`create` 時に設定しハートビートでは更新しない。architecture 5.1)が直近のものは解放しない(案。architecture 5.4、CA-P-47。直近の長さは仮値で、architecture 11章は 60 秒。最終決定は CAPI-U-7)。受付と解放を Crawler 内で直列に処理する方法でもよい。
- 読んだ版を条件にロック文書を削除する。条件が外れたら読み直して判定し直す(architecture 5.5 と同じ)。繰り返しても競合が解けないときは 503。
- `source_delete` ジョブが `running`(リース期限内)のまま止まって動かない場合の脱出手段は、Crawler の再起動による回復(architecture 5.8、9)だけ(MVP)。リース切れになれば、この API で解放できる。
- 解放の後も動いている Crawler(リースの更新が遅れただけの場合)は、次のハートビートで所有権の喪失を知り、ジョブを止める(architecture 5.7)。
- ソース削除ジョブが所有権を失って止まったとき、設定の `status=deleting` は残る。解放の後に、ソース削除ジョブ起動(4.6)で再実行して復旧する(案。architecture 8.3)。`deleting` が残ったソースは、更新もクロールもできず、再実行で完了させる以外に戻す手段がない。
- この API はジョブを起動しない。解放の後のクロールの再実行は 4.1。
- メンテナンスフラグは確認しない(導出。CAPI-P-17)。
- 冪等: 同じ要求を重ねても、2 回目以降は `released=false` の 200 になる。

**確認状況**: 操作の存在は確定(Q1)。解放の対象(実行中でないロックだけ)は architecture 5.4 の案。パス、応答、`lock_in_use`、`queued` の扱い、受付の途中のロックの保護、null・形式不正の扱いは案(CAPI-P-6)。

### 4.4 データソース設定の登録・更新

**概要**: `loreley-sources` のデータソース設定を登録・更新する。共通項目と `connector_type`・`connector_config` の名称・型・意味は architecture 3.2 が正本で、本節はそれらの受け方、検証する主体、エラーを書く。`connector_config` は Crawler も本 API も中身を見ず、Connector が `ConnectorType.validate_config` で検証する(interface 3.2、8章)。

**4.4.1 項目と検証の分担**(案。CAPI-P-7、CAPI-P-8):

| 項目 | 型 | 登録 | 更新 | 検証する主体と内容 |
| --- | --- | --- | --- | --- |
| `source_id` | string | 本文で必須 | パスで指定(本文に含めると 400、`reason=read_only`) | Crawler: 3.2 |
| `connector_type` | string | 必須 | 本文に含めない(登録後は変更できない。含めると 400、`reason=read_only`。案。CAPI-U-8) | Crawler: 登録されている `ConnectorType` の値であること(MVP は `file_system`。architecture 3.2。違反は `reason=unsupported`) |
| `connector_config` | object | 必須 | 必須 | **Connector**(`validate_config`。I/O をしない。interface 8章)。Crawler は JSON のオブジェクトであることだけを見る |
| `ttl` | integer | 必須 | 必須 | Crawler: 整数であること。範囲は検証しない |
| `ratio_threshold` | number | 必須 | 必須 | **範囲(0 以上 1 未満)は Admin API だけが検証する**(確定。CAPI-K-3)。Crawler は有限の数値であることだけを見る。値は、Indexer が削除対象の割合(T÷D)と比べる割合そのもの。Admin View の入力単位(%)からの変換は Admin API の領域(CAPI-U-3) |
| `min_delete_count` | integer | 必須 | 必須 | Crawler: 整数であること。範囲は検証しない |
| `schedule_interval_seconds` | integer または null | 任意(省略は null=手動のみ) | 任意(省略は null に置き換える) | Crawler: 1 以上の整数、または null。周期の形式自体は未決(architecture CA-U-8) |
| `status` | `active` / `deleting` | 受け付けない(登録時は `active`) | 受け付けない(現在の値を保つ) | `deleting` にするのはソース削除ジョブだけ(architecture 8.1)。含めると 400(`reason=read_only`) |
| `updated_at` | datetime | 受け付けない | 受け付けない | Crawler が設定する。含めると 400(`reason=read_only`) |

- `ttl`・`ratio_threshold`・`min_delete_count` を必須にするのは、既定値が決まっていないため(Indexer 側も未決。architecture 3.2)。既定値が決まれば、Admin API が補う案も取れる(CAPI-U-3)。
- 型の検証を Crawler が行うのは、型が合わないと実行開始時にジョブが `failed` になり(architecture 3.2)、Indexer も厳密な型を要求するため(CA-K-5。導出)。範囲の検証をしないのは CA-K-16(確定)による。
- 登録・更新は**接続確認をしない**(`validate_config` は I/O をしない。interface 8章、CI-P-9)。接続の不備は、ジョブ開始時の `create`(architecture 4.5 の手順 8)で検出される。
- 認証情報は参照名だけを持つ(architecture 3.2、PD 4.8)。
- 反映の境界は、ジョブが `loreley-sources` を読む時点(architecture 4.5 の手順 6。`queued` -> `running` の遷移の後に 1 度だけ読む。案。CA-P-51)。その読み取りで、`ttl`・`ratio_threshold`・`min_delete_count` と `connector_config` を同じ版で確定する。読む時点より前の更新は、そのジョブに反映される(受付済みで `queued` の間の更新を含む。導出)。後の更新は、そのジョブに反映されない。手順 8 の `validate_config`・`create` は、手順 6 で保持した `connector_config` を使い、`loreley-sources` を読み直さない(architecture 3.2・4.5)。
- `schedule_interval_seconds` の変更は、次の定期起動の判定から有効になる(次回の起動時刻は、直近に受け付けたクロールジョブの `queued_at` に間隔を足した時刻。architecture 4.3)。`updated_at` が起点になるのは、そのソースにクロールジョブが 1 件もないときだけ(案。architecture 4.3)。
- `connector_config` のうち `external_id` の導出に影響する項目(例: FS のルート)を変えると文書の同一性が変わりうる。その扱いは各 Connector 文書が定める(interface 8章)。本 API は、そのことを理由に更新を拒否しない(案。CAPI-U-8)。

**共通のエラー**(4.4.2・4.4.3):

| HTTP | `code`(案) | 条件 |
| --- | --- | --- |
| 400 | `invalid_request` | 4.4.1 の Crawler の検証に違反(`details.errors` に項目と理由。理由の値は 3.3)。`connector_type` が登録されていない値のときは `reason=unsupported`。更新の本文に `source_id`・`connector_type`(パスまたは登録時に決まる項目)を含めたときは `reason=read_only` |
| 400 | `config_invalid` | `validate_config` が `connector_config` の違反を返した(interface 6.2 の `config_invalid`)。`message` は Connector の説明文(3.3) |
| 500 | `internal_error` | `validate_config` が `connector_internal_error`(想定外の例外。interface 6.2)を返した |

#### 4.4.2 登録

**エンドポイント**: `POST /sources`(案)

**呼び出し元**: Admin API(しきい値の範囲の検証を済ませてから呼ぶ。CAPI-K-3)

**リクエスト**: 4.4.1 の「登録」列のとおり。

```json
{
  "source_id": "docs-share",
  "connector_type": "file_system",
  "connector_config": { "...": "Connector 固有の項目(各 Connector 文書で定義)" },
  "ttl": 2592000,
  "ratio_threshold": 0.3,
  "min_delete_count": 10,
  "schedule_interval_seconds": 86400
}
```

(数値は説明用で、既定値ではない。既定値は未決。)

**レスポンス**: 201(新規に保存した)、または 200(同じ内容がすでに登録されていた。下記)。本文は保存した設定で、4.4.1 の全項目(`source_id`・`status`・`updated_at` を含む)。

**エラー**: 共通のエラーに加えて、

| HTTP | `code`(案) | 条件 |
| --- | --- | --- |
| 409 | `source_already_exists` | 同じ `source_id` の設定がすでにあり、内容が異なる、または `status=deleting`。`details.status` に既存の `status` を入れる |

**冪等性・注意事項**:

- 保存は「存在しない場合だけ成功する作成」で行う(architecture 3.1 の `create`)。同時に 2 つの登録が来ても 1 つだけ成功する。
- 同じ `source_id` に同じ内容の再送は、200 で既存の設定を返す(応答が失われた再送を成功にするため。案。CAPI-P-10)。`status=deleting` のものは、同じ内容でも 409。
- **内容の比較規則**(登録・更新で共通。案): `schedule_interval_seconds` の省略は `null` に正規化してから、JSON のキーの順を無視して値で比べる。`ratio_threshold` は数値として比べる(`1` と `1.0` は等しい)。`status`・`updated_at` は比べない。
- ソース削除が完了した後(設定が消えた後)は、同じ `source_id` で再登録できる。ただし、孤児ロックが残っているときは、ロック解放(4.3)で消すまで、クロールを起動できない(4.1 の `lock_held`)。

#### 4.4.3 更新

**エンドポイント**: `PUT /sources/{source_id}`(案)

**呼び出し元**: Admin API(しきい値の範囲の検証を済ませてから呼ぶ。CAPI-K-3)

**リクエスト**: 4.4.1 の「更新」列のとおり。登録と同じ形で、`source_id` と `connector_type` は含めない。**更新は、変更できる項目の全置換**(案。CAPI-P-7)。必須項目の省略は 400 で、保存済みの値を保つ部分更新はしない(「更新で値が省略されたときの扱い」は architecture 3.2 が本書に委ねた事項)。

**レスポンス**: 200。本文は保存した設定(登録と同じ形)。

**エラー**: 共通のエラーに加えて、

| HTTP | `code`(案) | 条件 |
| --- | --- | --- |
| 404 | `source_config_not_found` | 設定がない |
| 409 | `source_deleting` | 設定の `status=deleting`(削除中の設定は変更しない。導出) |

**冪等性・注意事項**:

- 内容が現在の設定と等しいときは(比較規則は 4.4.2)、書き込まずに 200 を返し、`updated_at` も変えない(案。CAPI-P-10)。`updated_at` は、そのソースで初めて定期起動する場合の起点に使われるため(architecture 4.3)、同じ内容の更新で起点が動かないようにする。
- 受付済みで `queued` のジョブには、この更新が反映される(4.4.1 の反映の境界)。
- 読んだ版を条件に置き換え、`status` は常に現在の値を保つ(導出)。ソース削除ジョブが `status=deleting` に更新した直後に、更新が `active` に戻してしまうことを防ぐため。競合したら読み直し(その時点で `deleting` なら 409)、繰り返しても解けなければ 503。

**確認状況**: 登録・更新の操作の存在(Q1)と、しきい値の範囲検証の主体が Admin API であること(CA-K-16)は確定。`status` を登録・更新で変更させないこと(architecture 13.7 の依頼。「削除中」の置き場所自体が案。architecture CA-U-2)、`connector_config` の検証を Connector が行うこと、`ttl` などの型検証を Crawler が行うことは案。パス、必須項目、全置換、`source_already_exists`、冪等の扱いも案(CAPI-P-7〜10)。

### 4.5 データソース設定の削除(API を置かない)

- Q1 はデータソース設定の削除を対象に挙げる。一方、architecture は、設定レコードを削除するのをソース削除ジョブの手順 5 だけに限る(3.2、8章)。設定だけを先に消すと、検索インデックスに文書が残ってしまうため(architecture 3.2)。
- そこで、設定レコードだけを削除する API は置かない。データソースの削除は、ソース削除ジョブ起動(4.6)で行う。Admin API は、管理者の「データソースの削除」操作を 4.6 に対応づける。**確定**(ユーザー回答 2026-11-13。作業記録 0010。architecture CA-K-22。CAPI-K-8)。
- 確定した内容: 設定の「削除」は、そのソースの索引済み文書も削除する操作である。K29 の順序(設定の削除は文書などの削除の後、ロック文書の削除の前)は維持する。設定だけを消す API・操作は、今後置かない(置く場合は、K29 の順序の見直しになるため、ユーザーの再判断が要る)。

### 4.6 ソース削除ジョブ起動

**概要**: データソースの削除を `source_delete` ジョブとして起動する。ジョブの手順と所有権を失ったときの停止は architecture 8.1・8.2(CA-K-11)が正本で、本節は入出力と拒否だけを書く。受付は 4.1 と同じ手順だが、`status=deleting` のデータソースも受け付ける(案。architecture 8.3。途中で止まったジョブを再実行して復旧すること自体は確定(CAPI-K-4)で、再実行の手段をこの API の再呼び出しにすることと、受付で `deleting` を許すことは案。CAPI-P-12)。

**エンドポイント**: `POST /sources/{source_id}/delete-jobs`(案)

**呼び出し元**: Admin API(管理者の操作)

**リクエスト**: パスの `source_id` だけ。ボディは不要。

**レスポンス**(202): 4.1 と同じ項目で、`job_type` は `source_delete`、`status` は `queued`、`trigger` は `manual`。`force_delete`・`rewrite_mode` は含めない。

**エラー**(共通のエラーは 3.3):

| HTTP | `code`(案) | 条件 |
| --- | --- | --- |
| 404 | `source_config_not_found` | 設定がない。設定の削除(手順 5)の後にロック文書だけが残った場合は、再実行は不要で、ロック解放(4.3)で消す(architecture 8.3) |
| 409 | `maintenance_enabled` | メンテナンスフラグが立っている(クロールと同じ受付の手順を使うため。architecture 8.1 の順 0。導出) |
| 409 | `lock_held` | そのソースのロック文書がすでにある。`details.existing_job`(4.1 と同じ形)。`source_delete` ジョブがすでに実行待ち・実行中のときもこれ |

`source_deleting` は返さない(削除中でも受け付けるため)。

404 `source_config_not_found`(本書の API 全体で共通)は設定レコードがない場合で、interface 6.2 の分類名 `source_not_found`(データソースの起点が存在しない)とは別の意味。

**冪等性・注意事項**:

- **実行中のメンテナンス**: 409 `maintenance_enabled` は受付時だけ。受付の後、ジョブの開始後にメンテナンスフラグが立った場合は、architecture 7.9・CA-U-17 の確認点でジョブが `failed`(`maintenance`)になりうる(契約としては、受付の後に失敗しうる)。`failed` になったジョブは、フラグを下ろした後に再実行で復旧できる(確定。CAPI-K-4。再実行は本 API の再呼び出しで、案)。
- 受付では設定の `status` を変えない。`deleting` にするのは Job Runner が実行を始めるとき(architecture 8.1 の順 0)。受付の後は、ロックを持つため、そのソースのクロールの起動は `lock_held` になる。
- `source_delete` ジョブは取り消せない(4.2)。途中で止まって `failed` になったら、再実行して復旧する(確定。CAPI-K-4)。再実行の手段はこの API をもう一度呼ぶこと(案)で、各手順は冪等であり、すでに済んだ分は成功として扱われる(architecture 8.3)。
- 実行中(`running`、リース期限内)の `source_delete` ジョブが止まって動かなくなった場合の脱出手段は、Crawler の再起動による回復(architecture 5.8、9)だけ(MVP)。リース切れになれば 4.3 でも解放できる。
- `status=deleting` が残ったソースは、設定の更新(4.4)もクロールの起動(4.1)もできない。ソース削除の再実行で完了させる以外に、元に戻す手段はない。
- 削除は取り返しがつかない(そのソースの全文書、スキップ記録、削除の記録、設定が消える)。この API には確認や二重送信を防ぐ仕組みがなく、誤操作の防止は Admin API・Admin View の側に委ねる(認証がないため。3.1)。
- 完了は、ジョブ記録の状態(`succeeded`)で判断する(Admin API が読み取る)。設定が消えたことの確認方法は、設定の読み取り経路(CAPI-U-2)の結論による。

**確認状況**: 操作の存在は確定(Q1)。ジョブの手順の順序と、途中で止まったジョブを再実行で復旧することは確定(architecture CA-K-11)。受付に `status=deleting` を許すこと、再実行の手段、受付の拒否条件(メンテナンス中を含む)は architecture 8.1・8.3 の案で、本書はそれに従う。パス、応答、エラーコード名は案(CAPI-P-12)。

---

## 5. 確認状況

### 5.1 確認した事実(2026-11-13)

- architecture 13.7 の「crawler-api への依頼」の 7 点(列挙された項目の数)を確認し、本書の該当箇所に対応した(5.6)。
- architecture 13.7 の「v0.2 での依頼」の crawler-api 向け 3 点を確認し、(1)(2)を反映した。(3)(`settings_snapshot`・`warnings` を記述している場合の追従)は、本書にその記述がないため変更なし。
- architecture 2.1・2.2 は、Admin API が `loreley-jobs`・`loreley-deletions` を読み取りのみで読むと書く。`loreley-sources` については、architecture 2.1〜2.3 が Admin API の読み取りのみの直接読み取りを案として想定する(CA-P-46)。経路の決定は Admin API 設計時(CAPI-U-2)。
- Admin API の設計書はない。`docs/v0.x/system-design/` に Admin API の設計はなく、`search-api/`・`web-ui/` は空で、`apps/` には `indexer/` しかない(CAPI-U-1)。
- SD v0.8 14.2 の「Admin API が Crawler に中継する操作」の行は「クロールの起動(強制削除モードの指定を含む)、取り消し、ロック解放、突合の起動」で、ソース削除ジョブの起動とデータソース設定の登録・更新・削除が含まれない。14.2 のしきい値の検証の行と 14.4(6) は設定の登録・更新の中継に触れるが、中継操作の行には含まれない。SD 1.2 はソース削除を Crawler のジョブとするが、起動の経路を書いていない(I-20。14.2 を再確認した)。
- SD v0.8 14.4: 重複起動は 409 で既存ジョブの状態を含める(案)。Admin API は通常これを成功として扱い、既存ジョブがリース切れの `failed`、または失効したロックのときは警告する(案)。本書の `lock_held` と `details.existing_job` はこれを受ける(Admin API の扱いは CAPI-U-5)。
- PD v0.19 4.6: Admin View にデータソース・実行周期・TTL・しきい値・最小件数の設定、クロールの手動実行、手動実行だけの強制削除がある。

確認していないこと: OpenSearch 実機での `create`・条件付き置き換えの挙動、Admin API 側の実装・期待、HTTP サーバの実装(パスのエンコードの扱いを含む)。

### 5.2 確定(CAPI-K)

確定にしたのは、ユーザー回答(Q1。2026-11-13 の確定を含む)と、Indexer 設計書・PD・architecture で確定済みの事項だけ。

| ID | 内容 | 出典 |
| --- | --- | --- |
| CAPI-K-1 | 本書の範囲は、Admin API が呼ぶ Crawler の口だけ。対象は、クロール起動(`force_delete`・`rewrite_mode` の指定を含む)、取り消し、ロック解放、データソース設定の登録・更新・削除(削除はソース削除ジョブの起動で実現する。CAPI-K-8)、ソース削除ジョブ起動。Crawler -> Indexer の呼び出しは含めず、Indexer の契約は参照のみ | ユーザー回答 Q1、architecture CA-K-19 |
| CAPI-K-2 | 強制削除(`force_delete`)は、手動実行のクロールの起動時にだけ指定できる | architecture CA-K-17 |
| CAPI-K-3 | しきい値の範囲(0 以上 1 未満)の検証は Admin API だけが行い、Crawler と Indexer は検証しない | architecture CA-K-16 |
| CAPI-K-4 | 削除中のデータソースに新しいクロールを起動しない。途中で止まったソース削除ジョブは、再実行で復旧する | architecture CA-K-11 の要件(3)(4)。「`source_delete` の受付で `status=deleting` を許すこと」と、再実行の手段(この API の再呼び出し)は含まない(案。CAPI-P-12) |
| CAPI-K-5 | `loreley-jobs` に書くのは Crawler だけ。Admin API は書かず、読み取りのみ。(メンテナンスフラグの書き込み手段は例外で、確定でなく案。architecture CA-K-2、CA-U-3) | architecture CA-K-2 |
| CAPI-K-6 | `source_id` は空でなく、制御文字を含まず、UTF-8 で 256 バイト以内(256 バイトは Indexer 側では検証規則としての仮値。indexer-api 3.3) | architecture CA-K-13 |
| CAPI-K-7 | MVP は認証なし | PD v0.19 8.1 |
| CAPI-K-8 | データソース設定の「削除」は、そのソースの索引済み文書も削除する操作で、ソース削除ジョブの起動(4.6)に対応づける。設定レコードだけを削除する API は置かない(CAPI-P-11 から移行) | ユーザー回答(2026-11-13。作業記録 0010)、architecture CA-K-22 |

### 5.3 案(CAPI-P)

| ID | 内容 | 章 |
| --- | --- | --- |
| CAPI-P-1 | HTTP + JSON(UTF-8)、同期呼び出し。内部ネットワークだけで通信し、ホストに公開しない | 3.1 |
| CAPI-P-2 | API の一覧(メソッドとパス)。クロール起動とソース削除ジョブ起動は別のエンドポイント(拒否条件が異なるため) | 1 |
| CAPI-P-3 | クロール起動: ボディは任意、`rewrite_mode` も手動実行だけで指定(定期は常に `false`)、202 とジョブの項目 | 4.1 |
| CAPI-P-4 | 受付の拒否を 409 の `source_deleting` / `maintenance_enabled` / `lock_held` に分ける。設定がなければ 404。`lock_held` は `details.existing_job` を返す | 4.1 |
| CAPI-P-5 | 取り消し: 対象は `crawl` のみ。`queued` は 200、`running` は 202(受付のみ)。409 は `job_already_finished` / `job_not_cancellable`。404 は `job_not_found`。判定順は `job_not_found` -> `job_not_cancellable` -> `job_already_finished` -> 200/202 | 4.2 |
| CAPI-P-6 | ロック解放: `DELETE /sources/{source_id}/lock`。孤児ロック・リース切れの `running`(`lease_expires_at` が null・形式不正を含む)を解放し、`queued` とリース期限内の `running`、取得直後(受付の途中)のロックは 409 `lock_in_use`。設定がなくても解放できる。ロックがなければ 200 `released=false` | 4.3 |
| CAPI-P-7 | 設定の項目の受け方: `ttl`・`ratio_threshold`・`min_delete_count` は必須で既定値なし。`ratio_threshold` は Indexer が比べる割合そのもの。更新は全置換で、必須項目の省略は 400 | 4.4 |
| CAPI-P-8 | 検証の分担: Crawler は `connector_type`・型・`schedule_interval_seconds`、`connector_config` は Connector(`validate_config`)、しきい値の範囲は Admin API。登録・更新では接続確認をしない | 4.4 |
| CAPI-P-9 | `status`・`updated_at` は受け付けない(400)。更新は `status` を変えず、`connector_type` も変更できない。削除中の設定の更新は 409 | 4.4 |
| CAPI-P-10 | 冪等: 登録は同じ内容の再送を 200、異なれば 409。更新は同じ内容なら書き込まず 200(`updated_at` も変えない) | 4.4 |
| CAPI-P-11 | (確定に移行した。CAPI-K-8 を参照。ユーザー回答 2026-11-13。ID は欠番にせず残す) | 4.5 |
| CAPI-P-12 | ソース削除ジョブ起動: `status=deleting` も受け付ける(architecture 8.3 の案)。再実行の手段をこの API の再呼び出しにする。設定がなければ 404、メンテナンス中は 409。受付では `status` を変えない | 4.6 |
| CAPI-P-13 | エラー形式: Indexer API と同じ `error.code`・`message`・`retryable` に `details` を加える。503 だけ `retryable=true` | 3.3 |
| CAPI-P-14 | JSON は厳密(型変換をしない)。未知の項目は 400 | 3.2 |
| CAPI-P-15 | `source_id` の文字種: 半角英数字で始まり、半角英数字・`.`・`_`・`-` だけ | 3.2 |
| CAPI-P-16 | 状態の読み取り API を置かない(Admin API が `loreley-jobs` を直接読む) | 2.3 |
| CAPI-P-17 | メンテナンスフラグを確認するのは起動系(4.1、4.6)だけ。取り消し・ロック解放・設定の登録・更新では確認しない | 4.2、4.3 |
| CAPI-P-18 | `job_id` の対象は `record_type=job` の記録だけ。ロック・スキップ記録・メンテナンスフラグなどのIDは 404 `job_not_found`。`job_id` も 256 バイト以内・制御文字なしを検証する | 3.2 |

### 5.4 未決(CAPI-U)

| ID | 内容 | 決める場所 |
| --- | --- | --- |
| CAPI-U-1 | Admin API の設計の不在。本書は Admin API の設計より先に契約を定義した。Admin API 設計時に、パス・応答・エラーコード(メンテナンス中を 409 にするか 503 にするかを含む)・Admin API 側のリトライと表示への対応づけを再確認する(architecture CA-U-12 と対応)。なお、Q1 の「設定の削除」と「ソース削除ジョブ起動」を同じ操作として扱う解釈の確認は、2026-11-13 に確定して解消した(CAPI-K-8) | Admin API 設計時 |
| CAPI-U-2 | データソース設定の取得・一覧の経路。Admin API が `loreley-sources` を読み取りで直接読むか、Crawler が読み取り API を持つか。architecture 2.1〜2.3 は直接読み取りを案として想定する(CA-P-46) | Admin API 設計時 |
| CAPI-U-3 | 設定項目の必須・既定値・範囲。`ttl`・`min_delete_count` の範囲検証の要否と担当、`ratio_threshold` の入力単位(Admin View の % から割合への変換)、既定値(Indexer の architecture U-1)、`schedule_interval_seconds` の下限・上限(architecture CA-U-8)。必須・全置換(CAPI-P-7)は、Admin View が現在値を取得する経路(CAPI-U-2)と連動して決める(全置換の更新には、現在値を読んで画面に出す経路が前提になる) | ユーザー判断、Admin API 設計時 |
| CAPI-U-4 | `source_id` の文字種の最終決定(案は CAPI-P-15。architecture CA-U-15)。表示用の名前の項目が要るか(architecture 3.2 の共通項目にはない) | ユーザー判断 |
| CAPI-U-5 | 重複起動(409 `lock_held`)を Admin API が成功として扱うか。無視された `force_delete`・`rewrite_mode` の通知。リース切れ・孤児ロックの警告(SD v0.8 14.4 の案) | Admin API 設計時(architecture CA-U-12) |
| CAPI-U-6 | 終了通知の送信開始後の取り消しが削除を止めないことの Admin View での示し方。取り消し完了の確認方法(読み取りの間隔) | Admin API・Web 設計時 |
| CAPI-U-7 | ロック解放の対象の細部: `queued` のジョブのロック、`source_delete` の `running`、`owner` が自分以外のロックの扱い(`queued` のロックを対象外とするのは architecture 5.4 の案。CA-P-47)。受付の途中(ロック取得後・ジョブ保存前)のロックを孤児ロックと誤認しないための保護(案は `acquired_at` が直近なら解放しない。直近の長さは仮値で、architecture 11章は 60 秒。受付との直列化でもよい) | architecture の確認、ユーザー判断 |
| CAPI-U-8 | `connector_type` を登録後に変更できないことの是非。`external_id` の導出に影響する `connector_config` の項目(FS のルートなど)を変えたときの扱い(interface 8章) | FS・Web 文書、ユーザー判断 |
| CAPI-U-9 | Crawler のヘルスチェック(`GET /healthz` 相当)の要否。Indexer のヘルスチェックは契約に含まれない(indexer-api 1章)。architecture 10 に記述がない。crawler-module-structure の CM-U-5 が案(`api` が担当機能を呼ばずに受付開始後に 200 を返す。契約外の API。compose のヘルスチェックの要否と合わせて決める)を持つ | module-structure(CM-U-5)、運用 |
| CAPI-U-10 | 数値(Admin API から Crawler への HTTP タイムアウト、更新・解放の競合の再試行回数)。すべて仮値・設定可能・未決(Indexer K39 に準拠)。受付は Store 層への読み書きを数回行うので、タイムアウトはそれを見込む | 実装後の実測 |

### 5.5 既存設計との不整合(I-n)

| ID | 内容 | 本書での扱い |
| --- | --- | --- |
| I-20 | SD v0.8 14.2 の「Admin API が Crawler に中継する操作」の行(クロールの起動、取り消し、ロック解放、突合の起動)に、ソース削除ジョブの起動と、データソース設定の登録・更新・削除がない。SD 14.2 のしきい値の検証の行と 14.4(6) は設定の登録・更新の中継に触れるが、中継操作の行には含まれない。SD 1.2 はソース削除を Crawler のジョブとするが、起動経路を書かない | Q1 に従い、本書で定義する(4.4〜4.6)。SD は廃止予定のため修正しない |

I-20 以外に、今回の範囲で新たな不整合は見つけていない(`rewrite_mode` の追加は I-4、突合ジョブは I-2 で、architecture 13.5 に記載済み)。I-21〜I-29 は未使用。

### 5.6 architecture 13.7「crawler-api への依頼」への対応

| 依頼 | 本書での対応 | 章 |
| --- | --- | --- |
| 受付の拒否条件(ロック保持中・削除中・メンテナンス中) | 409 `lock_held` / `source_deleting` / `maintenance_enabled`。設定がなければ 404 | 4.1 |
| `force_delete`・`rewrite_mode` を手動のみ受け付ける | 起動 API だけが受け取り、定期起動は常に `false`(`rewrite_mode` は案) | 4.1 |
| ロック解放の対象 | 孤児ロックとリース切れの `running`。`queued`・リース期限内の `running`・受付途中のロックは対象外(案。architecture 5.4、CA-P-47) | 4.3 |
| `source_delete` の受付で `status=deleting` を許す | 許す(案。architecture 8.3)。メンテナンス中と `lock_held` は拒否 | 4.6 |
| 「設定の削除」と「ソース削除ジョブ起動」の関係 | 設定レコードだけを削除する API は置かず、ソース削除ジョブ(手順 5)だけが削除する(確定。CAPI-K-8。ユーザー回答 2026-11-13) | 4.5 |
| `source_id` の検証(CA-U-15) | 文字種の案を置いた(CAPI-P-15)。最終決定は CAPI-U-4 | 3.2 |
| 設定レコードの `status` は登録・更新で変更不可 | `status` を受け付けず(400)、更新は現在値を保つ | 4.4 |

### 5.7 他文書への依頼

本書では他文書を直さない。本書から architecture への修正要望は、architecture に反映済みで(architecture 13.7)、本書の 3.2・4.2・4.3・4.4.1 は実在の章参照に直した。

| 要望(architecture の箇所) | 反映先 | 残る未決 |
| --- | --- | --- |
| ジョブ記録の書き手(5.3) | architecture 5.3(CA-P-43) | なし |
| 取り消し要求の伝達方式(4.7) | architecture 4.7(CA-P-44。メモリ上のフラグ) | なし |
| `record_type`(`job` だけがジョブ。3.3) | architecture 3.3 | なし |
| Admin API の `loreley-sources` 読み取り(2.1〜2.3) | architecture 2.1〜2.3(CA-P-46。案) | 経路の決定は CAPI-U-2、CA-U-12 |
| `acquired_at` の意味、`queued` のロック、受付途中のロック(5.1・5.4) | architecture 5.1・5.4(CA-P-47。仮値 60 秒は 11章) | 最終決定は CAPI-U-7 |
| `connector_config` の確定時点(3.2・4.5) | architecture 3.2・4.5(v0.2: 手順 6 の 1 回の読み取りで確定。CA-P-51) | なし |
| `source_id` の文字種(CA-U-15) | architecture 3.2・7.10・CA-U-15 に CAPI-P-15 を案として記載 | 最終決定は CAPI-U-4、CA-U-15 |
| 横断一覧(13.8) | architecture 13.8(CAPI-U-1〜10 と I-20 を掲載) | なし |

- interface: なし。
- FS・Web 文書: `connector_config` の `validate_config` が、データソース設定の登録・更新の API から呼ばれる(I/O なし、エラーは `config_invalid`)ことを前提にする(interface 8章に既出)。追加の依頼はない。
