# `loreley-deletions` Schema 設計書 v0.7

## 0. この文書について

- 対象: Indexer の Deletion Manager が、削除の判断・実行を記録する Store 層のインデックス。**インデックス名は仮名**(確定は未決)。
- 区分の表記: 確定 = ユーザー確定、案 = ユーザー未確定、未決 = 決めていない。各項目の区分は第9章の表に集約する。本書は `loreley-deletions` の Schema を単独で読めるようにまとめた文書である。
- 未決の ID: 本文書の `U-*` は**この文書だけで通用するローカル ID**。他文書の未決は『architecture U-14』のように文書名付きで書く。「architecture U-n と同じ論点」は、`indexer-architecture-v0.7.md` 17.3 の同じ判断事項を指す。
- 関連文書:
  - `indexer-architecture-v0.7.md` — 削除の判断・実行(削除判定の順1〜6、割合ルールの判定1〜3)、直列化、書き込み役の分担。
  - `indexer-api-v0.7.md` — 開始通知・終了通知・Status API。
  - `search-index-v0.7.md` — 検索インデックス(削除の対象の文書。マッピングの共通方針)。

## 1. 位置づけ

- Indexer は、クロール 1 回ごとの削除の判断・実行を「削除結果」として記録する。この記録を持つのが `loreley-deletions` である。
- **書き込むのは Indexer(Deletion Manager)だけ**。Crawler も Admin API も書かない。
- Admin API は、`loreley-deletions` を読み取りのみで直接読んで表示する(Indexer を経由しない。案)。Status API を使うのは Crawler で、Admin View の表示は Admin API 経由である。
- Indexer は `loreley-sources` を読まない(TTL などは開始通知で渡される)。
- `crawl_id` は Crawler のジョブ ID をそのまま使う(新しい ID を採番しない)。現行世代は、そのソースで最後に受理した開始通知の `crawl_id`。実行中のクロールは通常 1 つだが、削除結果は、旧い削除の待機・判定・実行と重なって複数ありうる(直列に処理する。`indexer-architecture-v0.7.md`)。

## 2. 記録(ドキュメント)

| ID | 内容 |
| --- | --- |
| `deletion-{source_id}` | ソースごとの現行世代 |
| `deletion_result-{crawl_id}` | クロールごとの削除結果 |

### 2.1 `deletion-{source_id}`(ソースごとの現行世代)

- 項目: `crawl_id`、`crawl_started_at`、設定スナップショット(TTL、しきい値、最小件数)、`force_delete`、更新日時。
- 開始通知で更新する。直近の開始通知の内容である。
- **削除の判断・実行には使わない**(使うのは `deletion_result-{crawl_id}` に複写した値)。ソース削除の停止にも使わない(停止は自分の削除結果を読んで行う)。
- 実際に使う場面は、開始通知の 409 判定(現行世代の `crawl_started_at` より古い通知の拒否。案)のみに見える(K24 の再送の比較には、`deletion_result-{crawl_id}` に複写した値を使い、現行世代は使わない)。これは他の記述からの推測で、用途の追加はしない。

### 2.2 `deletion_result-{crawl_id}`(削除結果)

| 項目 | 説明 |
| --- | --- |
| `source_id` | |
| `status` | 第3章の状態値 |
| `reason` | `failed` の理由コード、または `discarded` の理由(第3章)。`validation_failed` では、件数照合の不一致、スキップ文書 ID の上限超過、T > D(案。architecture P33)を区別する(案。理由コード名は未決) |
| `outcome` | 終了通知の `outcome`(`enumeration_completed` / `failed` / `cancelled`) |
| `enumerated_count` | Crawler が `document_id` で重複を除いて数えた、列挙で見つかった文書の数(スキップ・抽出失敗の文書を含む) |
| `n_seen` | 当該 `source_id` で `last_seen_at >= crawl_started_at` の件数(リフレッシュ後の検索インデックス) |
| `e_missing` | `skipped_document_ids` と `oversize_document_ids`(原本サイズ超過で登録されなかった文書の ID。案。architecture P32)のうち、検索インデックスにないものの件数 |
| `target_count`(T) | 削除対象の件数。同一リフレッシュ後に取得した ID の件数(ID の取得時点の保証はしない。案。architecture P33。下記) |
| `denominator`(D) | 割合ルールの分母 |
| `deleted_count` | 削除した件数 |
| `forced` | 強制削除モードで実行したか。複写した `force_delete` そのもので、別の項目を重ねて持たない |
| 設定スナップショットの複写 | `ttl`、`ratio_threshold`、`min_delete_count`、`force_delete`、`crawl_started_at`(案。第4章)。項目名は未決(U-1) |
| `finish_received_at` | 終了通知(`enumeration_completed`)を最初に受理した日時。永続化してから 202 を返す。再送(2 回目以降)では書き換えない(architecture K25。下記) |
| 終了通知のダイジェスト | 最初に受理した終了通知の内容のダイジェスト(下記)。`finish_received_at` と同じ書き込みで保存する(`outcome` が `failed` / `cancelled` でも保存する)。項目名は未決(U-1 と同様) |
| `deletion_started_at` | 待機から判定への遷移で書く(`if_seq_no` の条件付き更新。案) |
| 開始・終了日時 | |

`oversize_document_ids` は終了通知で `skipped_document_ids` とは別の項目として渡される(案。architecture P32)。スキップした文書も原本サイズを超過した文書も、検索インデックスに登録されていなければ `e_missing` に数え、件数照合(`enumerated_count` = `n_seen` + `e_missing`)を成り立たせる。ID リストの上限は両リストの合計(上限の値は未決。API-U-5)。誰が上限・サイズ超過を拒否するか(Crawler の送信前か Indexer の拒否か)は未決(U-5。architecture U-5、`indexer-api-v0.7.md` の API-U-4)。

**終了通知の再送(architecture K25。確定)**: 最初に受理した終了通知の内容を基準にする。2 回目以降は、再処理せず `finish_received_at` も書き換えない。内容が最初と同じなら冪等に 202、異なれば 409 を返し、状態を変えない。比較のため、最初の通知の**ダイジェスト**(`outcome`、`enumerated_count`、重複除去・ソート済みの `skipped_document_ids` / `oversize_document_ids` の正規化 SHA-256。`finished_at` は除く)を `deletion_result` に保存する。Crawler は最初の通知内容を `loreley-jobs` に保存して固定し、再送では同じ内容を送る。`outcome` が `failed` / `cancelled` の通知は、`finish_received_at` を記録せず `failed` を記録する(ダイジェストは保存する)。再送かどうかは、ダイジェストが記録済みかで判定する(`finish_received_at` や終端状態の有無は使わない)。ダイジェストが記録済みの結果に対する再送は、同じ内容なら 202、異なれば 409 を返す。ダイジェストが未記録のまま終端状態になった結果(終了通知が届かないまま `superseded` になった旧世代など)への遅れた終了通知は、比較せず 202 を返す。受理の書き込みは、開始通知と同じソース単位の直列処理の中で、`if_seq_no` の条件付き更新で行う(architecture 9.5、9.9(4))。409 の本文に受理済みの状態を載せるかは未決(`indexer-api-v0.7.md` の API-U-21。受理の有無の読み方は同 4.5)。コード名は案。

T・D の定義は割合ルール(`indexer-architecture-v0.7.md`)を参照。T と D は同一リフレッシュ後にそれぞれ取得するが、取得の間の更新(D の増減)を排除する取得方式(読み取りの固定)は保証しない(案。architecture P33)。D を減らす操作は削除だけで、削除は直列化されている。ただし T > D となった場合は件数の食い違いとして削除を見送る(`validation_failed` として記録する案。architecture P33)。

**`crawl_started_at` の複写は照合元でもある(architecture K23。確定)**: `deletion_result-{crawl_id}` の複写 `crawl_started_at` は、件数照合と削除対象の判定に使うほか、バッチ登録と `last_seen_at` の部分更新で Crawler が渡す `crawl_started_at` の検証元にもなる(第4章)。

**複写項目は開始通知の再送の比較元でもある(architecture K24。確定。U-9)**: 同じ `crawl_id` で `running` のときに開始通知が再送されたら、複写した `source_id`、`crawl_started_at`、`ttl`、`ratio_threshold`、`min_delete_count`、`force_delete`(`forced`)と今回の内容を直接比較する。一致なら成功(状態不変)、不一致なら 409(状態不変)。比較には `deletion-{source_id}` を使わない(上書きされるため)。

**U-1 設定スナップショットの項目名**(architecture U-14 の一部と同じ論点): 関連する記述の間で表記が揃っていない。

| 場所 | 表記 |
| --- | --- |
| 開始通知 | `ttl` / `ratio_threshold` / `min_delete_count` / `force_delete` |
| `deletion-{source_id}` | 「TTL、しきい値、最小件数」と `force_delete` |
| `deletion_result` | 複写項目に加えて `forced` |
| Status API | 「しきい値」 |

複写の項目名は未決で、`ratio_threshold` などの名称は案である。

開始通知の任意項目 `rewrite_mode`(再書き込みモード。採用は architecture K26 で確定。名称は仮)を、このクロールの文脈として `deletion_result` に複写して保持するかは未決(`indexer-api-v0.7.md` の API-U-22)。削除の判断・実行には使わない。

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

状態名の一覧と各状態の意味は案(`indexer-architecture-v0.7.md` P25)。確定は、旧い削除を止めないこと、`interrupted` / `stale` の廃止、`discarded` の理由が `superseded` / `source_deleted` の 2 つであること、`failed` の範囲まで。

| 状態 | 意味 |
| --- | --- |
| `running` | 開始通知を受けてから終端状態になるまで(終了通知待ち、待機中、判定中、削除中を含む) |
| `deleted` | 判断を通り、削除を完了した(対象が 0 件の場合を含む)。`deleted_count` を記録する。強制削除モードなら `forced=true` |
| `skipped_by_ratio` | 割合ルールで削除しなかった。T、D、しきい値を記録する |
| `validation_failed` | 次のいずれか。(1) 件数照合の不一致。(2) スキップ文書 ID(`oversize_document_ids` を含む合計。案)の上限超過。(3) T > D(件数の食い違いとして削除を見送る。案。architecture P33)。`reason` で区別して記録する(案。理由コード名は未決)。数値を記録する |
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

- 開始通知を受理するとき、通知の `ttl`、`ratio_threshold`、`min_delete_count`、`force_delete`、`crawl_started_at` を `deletion_result-{crawl_id}` に複写する(`source_id` は `deletion_result` の項目として持つ)。
- 判定と実行は、常にこの複写した値を使い、`deletion-{source_id}`(新しい開始通知で上書きされる)からは読まない。
- 旧い削除は、待機中や実行中に新しい開始通知が来て設定が変わっても(強制削除モードの指定の有無を含む)、自分のクロールの設定で最後まで動く。
- `crawl_started_at` を複写するのは、件数照合の `n_seen`(`last_seen_at >= crawl_started_at` の件数)と削除対象の判定が、新しい世代の `deletion-{source_id}`(上書きされる)ではなく、自分のクロールの開始時刻で行われるようにするため。複写がないと、待機中に世代が進んだ旧い削除が、新しい `crawl_started_at` で照合・判定してしまう。

### 4.1 バッチ登録・`last_seen_at` の受理条件(architecture K23。確定。U-8)

- 対象: 通常クロール(開始通知を伴う)の、バッチ登録(`documents:batch`)と `last_seen_at` の部分更新(`last-seen`)のリクエスト(`indexer-api-v0.7.md`)に限る。これらは `crawl_id` と `crawl_started_at` を必須とする。ソース削除の要請は開始通知を伴わず `deletion_result` が存在しないため、別の要請として扱い、この判定の対象外とする。`deletion_result` を要求しない。`crawl_id` を省略することでは区別しない。
- **受理条件**: 次のすべてを満たすときだけ受理する。(1) `deletion_result-{crawl_id}` が存在する。(2) `source_id` が一致する。(3) `crawl_started_at` が複写値と一致する。(4) `status` が `running`。(5) `finish_received_at` が存在しない。(6) Crawler のロック所有確認に成功する。(1)〜(5) はリクエストの先頭で 1 回確認し、(6) は文書ごとに確認する。(6) の失敗は文書単位の `lock_not_owned` で、下記の拒否の名称(5 つ)には含めない(`indexer-api-v0.7.md` 3.2、API-U-13)。
- **終端状態への登録は拒否**: `superseded` / `discarded` / `failed` / 判断済み(`deleted`・`skipped_by_ratio`・`validation_failed`)の `deletion_result` には登録しない。`crawl_started_at` が一致していても同じ。終了通知を受理済み(`finish_received_at` あり)の結果も拒否する。登録後に件数照合の前提(列挙の完了時点)が崩れるのを避けるため。
- 照合先: `deletion_result-{crawl_id}`(リクエストの `crawl_id`)に複写した `crawl_started_at`。`deletion-{source_id}` の値は新しい開始通知で上書きされるため、照合には使わない。
- 拒否はいずれもリクエスト全体のエラーとし(文書単位ではない)、再試行しても直らないため非リトライとする。Crawler はジョブを `failed` にする。`last_seen_at` は書かない。拒否の種類ごとにエラー名を分ける(`crawl_not_started` / `crawl_source_mismatch` / `crawl_started_at_mismatch` / `crawl_already_closed` / `crawl_finished`。名称は案。`indexer-api-v0.7.md` 3.4、API-U-19)。
- `deletion_result-{crawl_id}` が存在しない場合は、開始通知を受けていない `crawl_id`、保持件数を超えて消えた結果、`loreley-deletions` の喪失(7章)を区別せず、「存在しない」として拒否する。削除が遅れるだけで安全側に倒れる。
- 受理条件を課さない場合は、誤った `crawl_started_at` や旧世代の遅れた書き込みが `last_seen_at` に反映されても安全側(削除が遅れる側)に倒れるが、誤りの検出が遅れる。
- **U-8(確定。architecture K23。`indexer-api-v0.7.md` の API-U-18 と同じ論点)**: 上記の受理条件を課し、終端状態・受理済み・存在しない結果への登録は拒否する。拒否のエラー名は案(API-U-19)。

## 5. 待ち行列

- 専用の待ち行列は持たない(案)。待ち行列は、`loreley-deletions` の状態(`finish_received_at` があって終端状態でない削除結果。`finish_received_at` の順)から導く。
- Indexer の再起動では待機中のものも `failed`(`indexer_restart`)になるので、待ち行列を復元する必要はない。
- 先行する削除結果(案): 同じ `source_id` で、`finish_received_at` が自分より前(同値なら `crawl_id` の辞書順など、決定的な規則)かつ終端状態でない削除結果。順序の規則は未決(U-4。architecture U-14 の一部と同じ論点)。
- 判定・実行の順序と直列化の方式は `indexer-architecture-v0.7.md`、Status API で待機中を見せる任意項目 `waiting_for`(案)は `indexer-api-v0.7.md` を参照。

## 6. 書き込みの整合に関わる規則(Schema に影響する範囲)

- **検索インデックスの文書の条件付き削除が競合したら読み直して再判定する(案。architecture 9.8)**: 削除は、削除の直前に読んだ文書の `_seq_no` / `_primary_term` を `if_seq_no` / `if_primary_term` に付けた条件付き削除である。要約の書き戻しや新しいクロールの登録などで文書が更新されると 409(条件外れ)になり、更新された文書は消えない。409 のときは文書を読み直し、TTL を再判定して(満たさなければ削除しない)、満たせば読み直した値で再び削除する。読み直しの回数はリトライ設定の回数までで、超えたら削除せず、その文書は次の期限削除に委ねる。条件外れの上限超過、TTL の再確認で除外した文書、すでにない文書は `deleted_count` に数えない。削除結果は `deleted` のまま終了する。
- ソース削除の停止確認や状態遷移の書き込みは、`if_seq_no` の条件付き更新で行い、終端状態(ソース削除の `discarded`)を上書きしない(案)。自分の削除結果が読めない(404。記録ごと削除された場合)ときも、書き換えずに止まる。
- 受理済みの旧い削除は、新しい開始通知で `discarded` にならない。新しい開始通知が `discarded`(`superseded`)にするのは、`finish_received_at` の無い旧い結果だけ。この `superseded` 化と終了通知の受理(`finish_received_at` の記録)が競合しないよう、Deletion Manager はソースごとに受理を直列に処理する(案。代わりに、`superseded` 化を「`finish_received_at` が無い」ことを条件にした条件付き更新にしてもよい)。
- データソースを削除するとき、そのソースの `deletion-{source_id}` と `deletion_result-*` はすべて削除される(実行は Crawler のジョブ。破棄・削除は Indexer に要請する。`indexer-architecture-v0.7.md`)。
- **ソース削除の排他と `discarded` への応答**(ロックの保持は architecture K29。確定。`discarded` の最優先処理は案。architecture P29): ソース削除のジョブは、`source_id` 単位のロックを最後まで保持し、ロック文書の削除は最後に行う。削除結果を `discarded`(`source_deleted`)にする要請は、Deletion Manager のソース単位の直列実行で最優先とする。実行中のバッチの完了直後、次のバッチの前確認や待機中の判定より前に `discarded` を書き、そのソースの終端でない削除結果(待機中を含む)をすべて `discarded` にしてから応答する。応答の時点で、そのソースの削除バッチは実行されていない。`discarded` への更新が完了しても、実行中のバッチが止まったことにはならないため、`discarded` の書き込みだけでは、`deletion_result-*` の削除や検索インデックスの文書の削除に進まない。バッチ内でハングした場合は、応答を待ち続ける(受容事項。ハング保護は設けない確定事項と整合する)。Crawler 向け要件(architecture K29。確定。9.14): (1) 削除中はジョブがロックのリースを更新し続ける、(2) 所有権を失ったら後続の削除操作を停止する、(3) 再実行で復旧する、(4) 削除中のデータソースに新しいクロールを起動しない。「削除中」状態をどこに持つか、Crawler 側のロック設計の具体は未決(Crawler 領域。U-7。architecture U-4)。
- **ソース削除の操作は冪等で、再実行できる(案。architecture P29)**: Indexer へのソース削除の要請(`discarded` への更新、`deletion_result-*` の削除、検索インデックスの文書の削除)は、何度実行しても結果が変わらない(`discarded` は終端状態を上書きせず、すでに削除された記録・文書は何もしない)。検索インデックスの文書は、`delete_by_query` を、実行前の refresh と完了後の `_count`=0 の確認つきで、0 になるまで再実行して消す(architecture K20、K28。確定。再実行の上限を設ける(値は未決。architecture U-31(5))。ロック保持=削除中は新しいクロールを起動しないことが前提。`indexer-api-v0.7.md` 4.7)。ソース削除のジョブがロックのリース切れ(`lock_not_owned`)で `failed` になっても、再実行すれば途中から完了する。Indexer はロックの具体に依存せずに正しく動く。ロックの保持は architecture K29 で確定し、Crawler 側のロック設計の具体は未決(U-7)。

## 7. マッピングと運用

- `loreley-deletions` のマッピング(`dynamic: strict` の適用、ID、保持件数を超えた削除結果の削除方法)は未決(U-2。architecture U-6 と同じ論点)。
- 検索インデックスの共通方針(`dynamic: strict`、`keyword` 化、`number_of_shards: 1`、`number_of_replicas: 0`。`search-index-v0.7.md` 第4章。これ自体が推測で、ユーザー未確認)を、このインデックス(Store 層)に適用するかも未決である(適用するかは決めておらず、確定扱いにしない。`indexer-architecture-v0.7.md` 3.5 も、Store 層のマッピング方針は本書を参照するとしており、同じく未決)。そのため、この文書にはマッピングの JSON を載せない。
- インデックス名は仮名。
- スナップショットは運用者の責務であり、本書は手順を仕様として定めない(architecture K21。確定)。Store 層(`loreley-sources`、`loreley-jobs`、`loreley-deletions`)と検索インデックスは同じ OpenSearch にあるため、運用者が取る 1 つのスナップショットで、設定・ジョブ・削除結果・文書を、取得時点の状態に復元できる(`search-index-v0.7.md` 6章)。整合した復元を求める場合は、関連する書き込み(クロール、削除、要約の書き戻し)を止めてから取得する。停止せずに取得したスナップショットの保証範囲(アプリケーション全体の整合は保証しない)は `indexer-architecture-v0.7.md` 14.1 を正本とする。検索インデックスだけを失った場合は Store 層(本書の削除結果を含む)は残り、再クロールのみで戻る(データソースの再登録は不要)。OpenSearch 全体を失い、スナップショットもない場合は、データソース設定の再登録が必要で、ジョブ履歴・削除結果は失われる(architecture 14.2)。
- **`loreley-deletions` を失った場合**(スナップショットなどからも復元できない): 次のクロールの開始通知で、現行世代が作り直される。それまでに届く終了通知は未知の `crawl_id` として破棄され、削除は行われない。進行中のクロールのバッチ登録と `last_seen_at` の部分更新は、照合先(`deletion_result-{crawl_id}`)がないため拒否される(4.1)。削除結果の履歴は失われる。削除が遅れるだけで安全である(検索インデックスの文書には影響しない)。Status API は該当の `crawl_id` について 404 を返す(案)。

## 8. 利用側との関係(境界)

- Status API(`GET /crawls/{crawl_id}`。案)は削除結果を読み取りで返す。利用者は Crawler である。404 を返す条件(案): 保持件数を超えて消えた `crawl_id`、開始通知を受けていない `crawl_id`、`loreley-deletions` を失った場合。条件の具体の確定は未決(`indexer-api-v0.7.md` の API-U-10。architecture 9.5 の P1)。詳細は `indexer-api-v0.7.md`。
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
| U-2 `loreley-deletions` のマッピング、保持件数超過分の削除方法、インデックス名、検索インデックスの共通方針(推測。ユーザー未確認)の適用(architecture U-6 と同じ論点。architecture 3.5 も未決) | 未決 | |
| U-3 保持件数 N(ソースごと。architecture U-2 と同じ論点) | 未決 | |
| U-4 同時刻の `finish_received_at` の順序(`crawl_id` 辞書順は案。architecture U-14 の一部と同じ論点) | 未決 | |
| `crawl_started_at` を設定スナップショットの複写に加える(第4章) | 案 | 複写の項目名は未決(U-1) |
| `e_missing` に `oversize_document_ids` を含める。上限は `skipped_document_ids` との合計(第2.2章) | 案 | architecture P32。ユーザー未確認 |
| U-5 原本サイズ超過の拒否主体(Crawler の送信前か Indexer の拒否か。architecture U-5、API-U-4 と同じ論点) | 未決(ユーザー判断) | P32 の構成の前提 |
| 終了通知の再送は、最初に受理した内容と同じなら 202、異なれば 409(案 B)。ダイジェストを `deletion_result` に保存する(第2.2章) | 確定 | architecture K25(2026-11-10)。409 のコード名は案 |
| U-6 終了通知の再送で内容が異なる場合の扱い。案 B(異なる内容は 409。ダイジェストを `deletion_result` に保存、Crawler は最初の通知内容を固定)で確定。409 の本文に受理済みの状態を載せるかは未決 | 確定(K25) | 旧 architecture U-29(K25 で確定)。API-U-21 |
| ソース削除のジョブが `source_id` ロックを最後まで保持し、ロック文書の削除は最後に行う。Crawler 向け要件(1)〜(4)(第6章) | 確定 | architecture K29(2026-11-10) |
| `discarded` は直列実行で最優先(実行中バッチの完了直後、そのソースの終端でない結果を全て `discarded` にしてから応答)、バッチ内ハングは待ち続ける(第6章) | 案 | architecture P29。ユーザー未確認 |
| 条件付き削除の条件外れ・TTL 再確認で除外した文書は `deleted_count` に数えず、`deleted` のまま次の期限削除に委ねる(第6章) | 案 | ユーザー未確認 |
| U-7 ソース削除ジョブのロック(architecture P29、U-4)。ジョブがロックを最後まで保持することと、Crawler 向け要件(削除中のリース更新の継続、所有権喪失時の後続停止、再実行で復旧、削除中のソースに新クロールを起動しない)は確定。「削除中」状態の置き場所と Crawler 側のロック設計の具体は未決 | 確定(K29)。未決部分は Crawler 領域 | architecture 9.14 |
| 通常クロールのバッチ登録・`last_seen_at` の受理条件(`deletion_result` が存在、`source_id` 一致、`crawl_started_at` 一致、`status` が `running`、`finish_received_at` なし、ロック所有確認に成功)。終端状態・受理済み・存在しない結果への登録は拒否。拒否はリクエスト全体のエラー(非リトライ、ジョブ `failed`)。ソース削除は別の要請として扱い対象外(4.1) | 確定 | architecture K23(2026-11-10)。U-8。拒否のエラー名は案(API-U-19) |
| U-8 受理条件を課すか、終端状態・存在しない結果への扱い(`indexer-api-v0.7.md` の API-U-18 と同じ論点) | 確定(K23) | 4.1 |
| 開始通知の再送の一致検証(複写項目との直接比較。一致なら成功、不一致なら 409。状態不変) | 確定 | architecture K24(2026-11-10)。U-9。コード名は案 |
| U-9 開始通知の再送を複写項目と比較して検証するか(`indexer-api-v0.7.md` の API-U-20 と同じ論点) | 確定(K24) | 検証する |
| ソース削除の操作は冪等で再実行できる。ロックの具体に Indexer は依存しない(第6章) | 案 | architecture P29。ロックの具体は U-7 |
| ソース削除の文書の削除は、`delete_by_query` を `_count`=0 まで再実行して消す(第6章) | 確定 | architecture K20、K28(2026-11-10)。再実行の上限の値は未決(architecture U-31(5)) |
| スナップショットは運用者の責務。Store 層と検索インデックスは同じ OpenSearch にあり、1 つのスナップショットで取得時点の状態に復元できる。整合した復元を求める場合は、関連する書き込みを止めてから取得する。停止せずに取得したスナップショットは、アプリケーション全体の整合を保証しない。設計書は手順を定めない(第7章) | 確定 | architecture K21(2026-11-10) |
| `rewrite_mode` を `deletion_result` に複写して持つか(U-1 と同様、API-U-22 の一部。再書き込みモードの採用は architecture K26 で確定) | 未決 | `indexer-api-v0.7.md` API-U-22 |
| `target_count`(T)は同一リフレッシュ後に取得した ID の件数(ID の取得時点の保証はしない)。T > D なら削除を見送る(2.2) | 案 | architecture P33。ユーザー未確認 |
| 待機中の削除結果を進める契機(イベントか定期走査か) | 未決 | architecture U-14 の一部 |
| Indexer 再起動時の整理の細部(待機中を含む対象判定) | 未決 | architecture U-20 |
