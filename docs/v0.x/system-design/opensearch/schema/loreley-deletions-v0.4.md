# `loreley-deletions` Schema 設計書 v0.4

## 0. この文書について

- 対象: Indexer の Deletion Manager が、削除の判断・実行を記録する Store 層のインデックス。**インデックス名は仮名**(確定は未決)。
- 区分の表記: 確定 = ユーザー確定、案 = ユーザー未確定、未決 = 決めていない。各項目の区分は第9章の表に集約する。本書は `loreley-deletions` の Schema を単独で読めるようにまとめた文書である。
- 未決の ID: 本文書の `U-*` は**この文書だけで通用するローカル ID**。他文書の未決は『architecture U-14』のように文書名付きで書く。「architecture U-n と同じ論点」は、`indexer-architecture-v0.4.md` 17.3 の同じ判断事項を指す。
- 関連文書:
  - `indexer-architecture-v0.4.md` — 削除の判断・実行(削除判定の順1〜6、割合ルールの判定1〜3)、直列化、書き込み役の分担。
  - `indexer-api-v0.4.md` — 開始通知・終了通知・Status API。
  - `loreley-texts-v0.4.md` — 同じ Store 層のインデックス(マッピング方針の元)。

## 1. 位置づけ

- Indexer は、クロール 1 回ごとの削除の判断・実行を「削除結果」として記録する。この記録を持つのが `loreley-deletions` である。
- **書き込むのは Indexer(Deletion Manager)だけ**。Crawler も Admin API も書かない。
- Admin API は、`loreley-deletions` を読み取りのみで直接読んで表示する(Indexer を経由しない。案)。Status API を使うのは Crawler で、Admin View の表示は Admin API 経由である。
- Indexer は `loreley-sources` を読まない(TTL などは開始通知で渡される)。
- `crawl_id` は Crawler のジョブ ID をそのまま使う(新しい ID を採番しない)。現行世代は、そのソースで最後に受理した開始通知の `crawl_id`。実行中のクロールは通常 1 つだが、削除結果は、旧い削除の待機・判定・実行と重なって複数ありうる(直列に処理する。`indexer-architecture-v0.4.md`)。

## 2. 記録(ドキュメント)

| ID | 内容 |
| --- | --- |
| `deletion-{source_id}` | ソースごとの現行世代 |
| `deletion_result-{crawl_id}` | クロールごとの削除結果 |

### 2.1 `deletion-{source_id}`(ソースごとの現行世代)

- 項目: `crawl_id`、`crawl_started_at`、設定スナップショット(TTL、しきい値、最小件数)、`force_delete`、更新日時。
- 開始通知で更新する。直近の開始通知の内容である。
- **削除の判断・実行には使わない**(使うのは `deletion_result-{crawl_id}` に複写した値)。ソース削除の停止にも使わない(停止は自分の削除結果を読んで行う)。
- 実際に使う場面は、開始通知の 409 判定(現行世代の `crawl_started_at` より古い通知の拒否。案)のみに見える。これは他の記述からの推測で、用途の追加はしない。

### 2.2 `deletion_result-{crawl_id}`(削除結果)

| 項目 | 説明 |
| --- | --- |
| `source_id` | |
| `status` | 第3章の状態値 |
| `reason` | `failed` の理由コード、または `discarded` の理由(第3章) |
| `outcome` | 終了通知の `outcome`(`enumeration_completed` / `failed` / `cancelled`) |
| `enumerated_count` | Crawler が `document_id` で重複を除いて数えた、列挙で見つかった文書の数(スキップ・抽出失敗の文書を含む) |
| `n_seen` | 当該 `source_id` で `last_seen_at >= crawl_started_at` の件数(リフレッシュ後の検索インデックス) |
| `e_missing` | `skipped_document_ids` と `oversize_document_ids`(原本サイズ超過で登録されなかった文書の ID。案。architecture P32)のうち、検索インデックスにないものの件数 |
| `target_count`(T) | 削除対象の件数。判定時刻を固定して取り込んだ ID の件数(案。architecture P33) |
| `denominator`(D) | 割合ルールの分母 |
| `deleted_count` | 削除した件数 |
| `forced` | 強制削除モードで実行したか。複写した `force_delete` そのもので、別の項目を重ねて持たない |
| 設定スナップショットの複写 | `ttl`、`ratio_threshold`、`min_delete_count`、`force_delete`、`crawl_started_at`(案。第4章)。項目名は未決(U-1) |
| `finish_received_at` | 終了通知(`enumeration_completed`)を最初に受理した日時。永続化してから 202 を返す。再送(2 回目以降)では書き換えない(先着採用。案。architecture P34。下記) |
| `deletion_started_at` | 待機から判定への遷移で書く(`if_seq_no` の条件付き更新。案) |
| 開始・終了日時 | |

`oversize_document_ids` は終了通知で `skipped_document_ids` とは別の項目として渡される(案。architecture P32)。スキップした文書も原本サイズを超過した文書も、検索インデックスに登録されていなければ `e_missing` に数え、件数照合(`enumerated_count` = `n_seen` + `e_missing`)を成り立たせる。ID リストの上限は両リストの合計(上限の値は未決。API-U-5)。誰が上限・サイズ超過を拒否するか(Crawler の送信前か Indexer の拒否か)は未決(U-5。architecture U-5、`indexer-api-v0.4.md` の API-U-4)。

**終了通知の再送(案。architecture P34)**: 最初に受理した終了通知の内容を採用し(先着採用)、2 回目以降は、内容が同じでも異なっても、再処理せず `finish_received_at` も書き換えず、冪等に 202 を返す。内容が異なる再送を 409 にする取り扱いはしない(U-6)。`outcome` が `failed` / `cancelled` の通知は、`finish_received_at` を記録せず `failed` を記録する。この結果に対する再送も、終端状態なので 202 を返すだけである。

T・D の定義は割合ルール(`indexer-architecture-v0.4.md`)を参照。

**`crawl_started_at` の複写は照合元でもある(案。architecture P36)**: `deletion_result-{crawl_id}` の複写 `crawl_started_at` は、件数照合と削除対象の判定に使うほか、バッチ登録と `last_seen_at` の部分更新で Crawler が渡す `crawl_started_at` の検証元にもなる(第4章)。

**U-1 設定スナップショットの項目名**(architecture U-14 の一部と同じ論点): 関連する記述の間で表記が揃っていない。

| 場所 | 表記 |
| --- | --- |
| 開始通知 | `ttl` / `ratio_threshold` / `min_delete_count` / `force_delete` |
| `deletion-{source_id}` | 「TTL、しきい値、最小件数」と `force_delete` |
| `deletion_result` | 複写項目に加えて `forced` |
| Status API | 「しきい値」 |

複写の項目名は未決で、`ratio_threshold` などの名称は案である。

保持と整理:

- ソースごとに、**終端状態の結果を**直近 N 件保持し、古いものは Indexer が消す。N は未決(U-3。architecture U-2 の保持件数 N と同じ論点)。
- 整理の対象は終端状態の結果だけ。`running`(待機中を含む)は数えず、消さない。

### 2.3 入力と記録の対応表

開始通知・終了通知で受け取る値が、どの記録のどの項目になるかの対応。書き込み主体はすべて Indexer(Deletion Manager)。

| 入力 | `deletion-{source_id}` | `deletion_result-{crawl_id}` | 備考 |
| --- | --- | --- | --- |
| 開始通知の `crawl_id` | `crawl_id` | ID の一部(`deletion_result-{crawl_id}`) | 世代判定と記録の特定に使う |
| 開始通知の `crawl_started_at` | `crawl_started_at`(世代判定のみ) | `crawl_started_at`(複写。照合元。判定・実行に使う) | 判定・実行・照合には複写を使う |
| 開始通知の `ttl`、`ratio_threshold`、`min_delete_count`、`force_delete` | 設定スナップショット(判断には使わない) | 複写(`forced` は複写した `force_delete`) | 項目名は未決(U-1) |
| 終了通知の `outcome` | なし | `outcome`、`status`、`reason` | `failed` / `cancelled` は `failed` を記録 |
| 終了通知の `enumerated_count` | なし | `enumerated_count` | 件数照合の左辺 |
| 終了通知の `skipped_document_ids`、`oversize_document_ids` | なし | `e_missing`(検索インデックスにない文書の件数) | ID リスト自体の保存先は本書では未記載 |

## 3. 削除結果の状態(`status`)

状態名の一覧と各状態の意味は案(`indexer-architecture-v0.4.md` P25)。確定は、旧い削除を止めないこと、`interrupted` / `stale` の廃止、`discarded` の理由が `superseded` / `source_deleted` の 2 つであること、`failed` の範囲まで。

| 状態 | 意味 |
| --- | --- |
| `running` | 開始通知を受けてから終端状態になるまで(終了通知待ち、待機中、判定中、削除中を含む) |
| `deleted` | 判断を通り、削除を完了した(対象が 0 件の場合を含む)。`deleted_count` を記録する。強制削除モードなら `forced=true` |
| `skipped_by_ratio` | 割合ルールで削除しなかった。T、D、しきい値を記録する |
| `validation_failed` | 件数照合の不一致、またはスキップ文書 ID(`oversize_document_ids` を含む合計。案)の上限超過。数値を記録する |
| `discarded` | 次のいずれか。`reason` に区別を記録する(理由は 2 つ)。(1) 終了通知が届かなかった旧い世代の整理(新しい開始通知による。理由 `superseded`。`finish_received_at` の無いものに限る)。(2) ソース削除で破棄された(理由 `source_deleted`)。`superseded` の結果に遅れて届いた終了通知は何もしない。未知の `crawl_id` は記録しない |
| `failed` | 削除が完了しなかった、または行わなかった。理由コードを `reason` に記録する。再開しない。削除結果の状態であり、ジョブの status は変えない |

`running` 以外が終端状態である。

### 3.1 `failed` の理由コード(案。コードの名称は実装時に調整する)

| 理由コード | 場面 |
| --- | --- |
| `outcome_failed` / `outcome_cancelled` | 終了通知の `outcome` が `failed` / `cancelled`(列挙の失敗、取り消し)。削除しない |
| `maintenance` | メンテナンスフラグが立っていた(判定の前、バッチの前。待機中だったものが順番が来た時点で立っていた場合を含む) |
| `indexer_restart` | 待機中、判定中、削除の実行中に Indexer が再起動した |
| `delete_error` | 削除のエラーが、リトライ設定の回数まで試しても直らなかった(エラーの種類も記録する) |

## 4. 設定スナップショットの複写(案)

旧い削除が、あとから届いた新しい世代の設定で動かないようにするために、この複写を置く(案)。

- 開始通知を受理するとき、通知の `ttl`、`ratio_threshold`、`min_delete_count`、`force_delete`、`crawl_started_at` を `deletion_result-{crawl_id}` に複写する。
- 判定と実行は、常にこの複写した値を使い、`deletion-{source_id}`(新しい開始通知で上書きされる)からは読まない。
- 旧い削除は、待機中や実行中に新しい開始通知が来て設定が変わっても(強制削除モードの指定の有無を含む)、自分のクロールの設定で最後まで動く。
- `crawl_started_at` を複写するのは、件数照合の `n_seen`(`last_seen_at >= crawl_started_at` の件数)と削除対象の判定が、新しい世代の `deletion-{source_id}`(上書きされる)ではなく、自分のクロールの開始時刻で行われるようにするため。複写がないと、待機中に世代が進んだ旧い削除が、新しい `crawl_started_at` で照合・判定してしまう。

### 4.1 バッチ登録・`last_seen_at` の `crawl_started_at` の照合(案。architecture P36。U-8)

- 対象: 開始通知を伴うクロールの、バッチ登録(`documents:batch`)と `last_seen_at` の部分更新(`last-seen`)のリクエストに含まれる `crawl_started_at`(`indexer-api-v0.4.md`)に限る(案)。突合・ソース削除の要請は開始通知を伴わず `deletion_result` が存在しないため対象外で、`deletion_result` を要求しない。
- 終端状態の `deletion_result-{crawl_id}` でも、`crawl_started_at` が複写値と一致すれば受理する(照合のみで状態は問わない。案。architecture 9.5 と同じ)。
- 照合先: `deletion_result-{crawl_id}`(リクエストの `crawl_id`)に複写した `crawl_started_at`。`deletion-{source_id}` の値は新しい開始通知で上書きされるため、照合には使わない。
- 不一致: リクエスト全体のエラーとし(文書単位ではない)、再試行しても直らないため非リトライとする。Crawler はジョブを `failed` にする。`last_seen_at` は書かない。
- `deletion_result-{crawl_id}` がない場合(開始通知を受けていない `crawl_id`、保持件数を超えて消えた結果、`loreley-deletions` の喪失。7章): 照合先がないため、リクエストを拒否し、Crawler はジョブを `failed` にする(案)。削除が遅れるだけで安全側に倒れる。照合を省略して受理する選択肢は U-8 に残す。
- 照合しない場合は、誤った `crawl_started_at` が `last_seen_at` に書かれても安全側(削除が遅れる側)に倒れるが、誤りの検出が遅れる。
- **U-8(案。architecture P36。`indexer-api-v0.4.md` の `crawl_started_at` 検証の未決と同じ論点)**: 選択肢は (1) 不一致はリクエスト全体のエラー、`deletion_result` がなければ拒否(案) (2) 不一致のみ拒否し、`deletion_result` がなければ照合を省略して受理 (3) 検証しない。ほか、ユーザー判断。

## 5. 待ち行列

- 専用の待ち行列は持たない(案)。待ち行列は、`loreley-deletions` の状態(`finish_received_at` があって終端状態でない削除結果。`finish_received_at` の順)から導く。
- Indexer の再起動では待機中のものも `failed`(`indexer_restart`)になるので、待ち行列を復元する必要はない。
- 先行する削除結果(案): 同じ `source_id` で、`finish_received_at` が自分より前(同値なら `crawl_id` の辞書順など、決定的な規則)かつ終端状態でない削除結果。順序の規則は未決(U-4。architecture U-14 の一部と同じ論点)。
- 判定・実行の順序と直列化の方式は `indexer-architecture-v0.4.md`、Status API で待機中を見せる任意項目 `waiting_for`(案)は `indexer-api-v0.4.md` を参照。

## 6. 書き込みの整合に関わる規則(Schema に影響する範囲)

- **条件付き削除が条件外れになった場合(案)**: 要約の保存は書き込み排他の外で `loreley-texts` の `seq_no` を更新するため、条件付き削除の条件が外れうる。条件が外れた文書と、TTL の再確認で除外した文書は `deleted_count` に数えない。削除結果は `deleted` のまま終了し、その文書は次の期限削除に委ねる(`loreley-texts-v0.4.md` 4.1)。
- ソース削除の停止確認や状態遷移の書き込みは、`if_seq_no` の条件付き更新で行い、終端状態(ソース削除の `discarded`)を上書きしない(案)。自分の削除結果が読めない(404。記録ごと削除された場合)ときも、書き換えずに止まる。
- 受理済みの旧い削除は、新しい開始通知で `discarded` にならない。新しい開始通知が `discarded`(`superseded`)にするのは、`finish_received_at` の無い旧い結果だけ。この `superseded` 化と終了通知の受理(`finish_received_at` の記録)が競合しないよう、Deletion Manager はソースごとに受理を直列に処理する(案。代わりに、`superseded` 化を「`finish_received_at` が無い」ことを条件にした条件付き更新にしてもよい)。
- データソースを削除するとき、そのソースの `deletion-{source_id}` と `deletion_result-*` はすべて削除される(実行は Crawler のジョブ。破棄・削除は Indexer に要請する。`indexer-architecture-v0.4.md`)。
- **ソース削除の排他と `discarded` への応答(案。architecture P29)**: ソース削除のジョブは、`source_id` 単位のロックを最後まで保持し、ロック文書の削除は最後に行う。削除結果を `discarded`(`source_deleted`)にする要請は、Deletion Manager のソース単位の直列実行で最優先とする。実行中のバッチの完了直後、次のバッチの前確認や待機中の判定より前に `discarded` を書き、そのソースの終端でない削除結果(待機中を含む)をすべて `discarded` にしてから応答する。応答の時点で、そのソースの削除バッチは実行されていない。`discarded` への更新が完了しても、実行中のバッチが止まったことにはならないため、`discarded` の書き込みだけでは、`deletion_result-*` の削除や検索インデックス・Store 層の文書の削除に進まない。バッチ内でハングした場合は、応答を待ち続ける(受容事項。ハング保護は設けない確定事項と整合する)。ソース削除のジョブがロックを取ること自体は Crawler 側のロック設計の決定が前提で、未決(U-7。architecture P29、U-4)。
- **ソース削除の操作は冪等で、再実行できる(案。architecture P29)**: Indexer へのソース削除の要請(`discarded` への更新、`deletion_result-*` の削除、検索インデックス・Store 層の文書の削除)は、何度実行しても結果が変わらない(`discarded` は終端状態を上書きせず、すでに削除された記録・文書は何もしない)。ソース削除のジョブがロックのリース切れ(`lock_not_owned`)で `failed` になっても、再実行すれば途中から完了する。Indexer はロックの採否(ジョブがロックを取るか)に依存せずに正しく動く。ロックの採否は Crawler 領域の決定として未決(U-7)のまま。

## 7. マッピングと運用

- `loreley-deletions` のマッピング(`dynamic: strict` の適用、ID、保持件数を超えた削除結果の削除方法)は未決(U-2。architecture U-6 と同じ論点)。
- `loreley-texts` と同じ Store 層の方針(`dynamic: strict`、`keyword` 化、`number_of_shards: 1`、`number_of_replicas: 0`。`loreley-texts-v0.4.md` 第3章)をこのインデックスに適用するかも未決。Store 層のインデックスに適用する書き方になっているが、`loreley-deletions` のマッピングは未決と別に明記しているため、確定扱いにしない。そのため、この文書にはマッピングの JSON を載せない。
- インデックス名は仮名。
- バックアップ: OpenSearch のスナップショットに `loreley-deletions` も含める(Store 層のインデックスをすべて対象にする)。
- **`loreley-deletions` を失った場合**(復元できない): 次のクロールの開始通知で、現行世代が作り直される。それまでに届く終了通知は未知の `crawl_id` として破棄され、削除は行われない。進行中のクロールのバッチ登録と `last_seen_at` の部分更新は、照合先(`deletion_result-{crawl_id}`)がないため拒否される(案。4.1)。削除結果の履歴は失われる。削除が遅れるだけで安全である。Status API は該当の `crawl_id` について 404 を返す(案)。

## 8. 利用側との関係(境界)

- Status API(`GET /crawls/{crawl_id}`。案)は削除結果を読み取りで返す。利用者は Crawler である。404 を返す条件(案): 保持件数を超えて消えた `crawl_id`、開始通知を受けていない `crawl_id`、`loreley-deletions` を失った場合。条件の具体の確定は未決(`indexer-api-v0.4.md` の API-U-10。architecture 9.5 の P1)。詳細は `indexer-api-v0.4.md`。
- Admin View の表示は、Admin API が `loreley-deletions` から直接読んだ内容による。確認結果の区分(`confirmed` / `unconfirmed` / `unknown`。案)と登録結果は `loreley-jobs`(Crawler 領域)にあり、この文書の対象外。
- 保持件数 N を超えて削除結果が消えている場合と `loreley-deletions` の喪失は区別できない。どちらも Admin View は「結果不明」と表示する(案)。あとから復元されて現在値が読める場合は、「結果不明」に現在値を併記し、区分は書き換わらない(案)。

## 9. 確認状況

区分: 確定 = ユーザー確定、案 = ユーザー未確定、未決 = 決めていない。

| 項目 | 区分 | 備考 |
| --- | --- | --- |
| `loreley-deletions` は Indexer だけが書く(インデックス名は仮名) | 確定 | |
| 削除の判断・実行は Indexer の内部モジュール Deletion Manager | 確定 | |
| 状態名の一覧(`running` ほか 6 つ)と各状態の意味 | 案 | architecture P25 |
| `interrupted` 廃止(`failed` + 理由コード)、`stale` 廃止(`discarded` の理由は `superseded` / `source_deleted`) | 確定 | |
| 同じソースの削除は直列(方式は案 B。ユーザー承認)、ハング保護は設けない(ユーザー決定) | 確定 | 待ち行列の持ち方などの細部は案 |
| 削除結果の項目名(`n_seen`、`e_missing`、`deletion_started_at` など)と設定スナップショットの複写 | 案 | 複写の項目名は未決(U-1) |
| `failed` の理由コード一覧と名称 | 案 | |
| 待ち行列を `loreley-deletions` の状態から導く(専用キューなし)、先行する削除結果の定義 | 案 | |
| ソース削除の停止確認(`if_seq_no` の条件付き更新、404 でも書き換えず止まる) | 案 | |
| `waiting_for`、Status API の 404 の条件 | 案 | 条件の具体の確定は未決(API-U-10。architecture P1) |
| Admin API が `loreley-deletions` を直接読む | 案 | |
| `deletion-{source_id}` の用途(開始通知の世代判定のみに見える) | 推測 | 他の記述からの推測。用途の追加はしない |
| U-1 設定スナップショットの複写の項目名(architecture U-14 の一部と同じ論点) | 未決 | |
| U-2 `loreley-deletions` のマッピング、保持件数超過分の削除方法、インデックス名、Store 層の方針の適用(architecture U-6 と同じ論点) | 未決 | |
| U-3 保持件数 N(ソースごと。architecture U-2 と同じ論点) | 未決 | |
| U-4 同時刻の `finish_received_at` の順序(`crawl_id` 辞書順は案。architecture U-14 の一部と同じ論点) | 未決 | |
| `crawl_started_at` を設定スナップショットの複写に加える(第4章) | 案 | 複写の項目名は未決(U-1) |
| `e_missing` に `oversize_document_ids` を含める。上限は `skipped_document_ids` との合計(第2.2章) | 案 | architecture P32。ユーザー未確認 |
| U-5 原本サイズ超過の拒否主体(Crawler の送信前か Indexer の拒否か。architecture U-5、API-U-4 と同じ論点) | 未決(ユーザー判断) | P32 の構成の前提 |
| 終了通知の再送は先着採用で、2 回目以降は常に冪等な 202(409 にしない。第2.2章) | 案 | architecture P34。ユーザー未確認 |
| U-6 終了通知の再送で内容が異なる場合の 409 を廃止するか | 案(ユーザー判断) | architecture P34 |
| ソース削除のジョブが `source_id` ロックを最後まで保持、`discarded` は直列実行で最優先(実行中バッチの完了直後、そのソースの終端でない結果を全て `discarded` にしてから応答)、バッチ内ハングは待ち続ける(第6章) | 案 | architecture P29。ユーザー未確認 |
| 条件付き削除の条件外れ・TTL 再確認で除外した文書は `deleted_count` に数えず、`deleted` のまま次の期限削除に委ねる(第6章) | 案 | ユーザー未確認 |
| U-7 ソース削除ジョブがロックを取ること(Crawler 側のロック設計の決定が前提。architecture P29、U-4) | 未決(ユーザー判断) | Crawler 領域 |
| バッチ登録・`last_seen_at` の `crawl_started_at` を複写と照合し、不一致はリクエスト全体のエラー(非リトライ、ジョブ `failed`)、`deletion_result` がなければ拒否(4.1) | 案 | architecture P36。U-8。ユーザー未確認 |
| U-8 `crawl_started_at` の照合を行うか、`deletion_result` がないときに拒否か照合省略か(architecture P36、`indexer-api-v0.4.md` の `crawl_started_at` 検証の未決と同じ論点) | 案(ユーザー判断) | 選択肢は 4.1 のとおり |
| ソース削除の操作は冪等で再実行できる。ロックの採否に Indexer は依存しない(第6章) | 案 | architecture P29。ロックの採否は U-7 |
| `target_count`(T)は判定時刻を固定して取り込んだ ID の件数(2.2) | 案 | architecture P33。ユーザー未確認 |
| 待機中の削除結果を進める契機(イベントか定期走査か) | 未決 | architecture U-14 の一部 |
| Indexer 再起動時の整理の細部(待機中を含む対象判定) | 未決 | architecture U-20 |
