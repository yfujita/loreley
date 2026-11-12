# `loreley-deletions` Schema 設計書 v0.10

- 版: v0.10(2026-11-12)
- 前版: `loreley-deletions-v0.9.md`

## 0. この文書について

- 対象: Indexer の Deletion Manager が、削除の判断・実行を記録する Store 層のインデックス。**インデックス名は仮名**(確定は未決)。
- 区分の表記: 確定 = ユーザー確定、案 = ユーザー未確定、未決 = 決めていない。各項目の区分は第9章の表に集約する。本書は `loreley-deletions` の Schema を単独で読めるようにまとめた文書である。
- v0.10 の反映範囲: Indexer の実装(2026-11-11〜12)で決めた事項のうち、ユーザーが承認したものを「確定」にし、根拠に承認日と作業記録の番号を書く。作業記録の番号は `agent_tasks/20261111_implement_indexer/` の `NNNN-*.md` を指す(0002 §3 = 2026-11-11、0014・0021 = 2026-11-12)。Crawler・Admin API・インフラの設計に依存する名称・形式は、案のまま「実装で採用中」と注記する。実装の数値の既定値・上限値は設計書では未決のままとし、`apps/indexer/README.md` を参照する(architecture K39)。
- 未決の ID: 本文書の `U-*` は**この文書だけで通用するローカル ID**。他文書の未決は『architecture U-14』のように文書名付きで書く。「architecture U-n と同じ論点」は、`indexer-architecture-v0.10.md` 17.3 の同じ判断事項を指す。
- 関連文書:
  - `indexer-architecture-v0.10.md` — 削除の判断・実行(削除判定の順1〜6、割合ルールの判定1〜3)、直列化、書き込み役の分担。
  - `indexer-api-v0.10.md` — 開始通知・終了通知・Status API。
  - `search-index-v0.10.md` — 検索インデックス(削除の対象の文書。マッピングの共通方針)。

## 1. 位置づけ

- Indexer は、クロール 1 回ごとの削除の判断・実行を「削除結果」として記録する。この記録を持つのが `loreley-deletions` である。
- **書き込むのは Indexer(Deletion Manager)だけ**。Crawler も Admin API も書かない。
- Admin API は、`loreley-deletions` を読み取りのみで直接読んで表示する(Indexer を経由しない。案)。Status API を使うのは Crawler で、Admin View の表示は Admin API 経由である。
- Indexer は `loreley-sources` を読まない(TTL などは開始通知で渡される)。
- `crawl_id` は Crawler のジョブ ID をそのまま使う(新しい ID を採番しない)。現行世代は、そのソースで最後に受理した開始通知の `crawl_id`。実行中のクロールは通常 1 つだが、削除結果は、旧い削除の待機・判定・実行と重なって複数ありうる(直列に処理する。`indexer-architecture-v0.10.md`)。

## 2. 記録(ドキュメント)

| ID | 内容 |
| --- | --- |
| `deletion-{source_id}` | ソースごとの現行世代 |
| `deletion_result-{crawl_id}` | クロールごとの削除結果 |

2種類の記録は同じインデックスに置き、項目 `record_type`(`deletion` / `deletion_result`)で区別する(案。実装で採用中。Indexer 実装の仮定義で、Crawler・infra 設計の確定時に再確認する。architecture U-34)。値のない項目は保存しない。日時の項目は、UTC・ISO 8601・ミリ秒精度の文字列で保存する(architecture 3.3 の日時の形式と同じ)。

### 2.1 `deletion-{source_id}`(ソースごとの現行世代)

- 項目: `record_type`、`source_id`、`crawl_id`、`crawl_started_at`、設定スナップショット(TTL、しきい値、最小件数)、`force_delete`、更新日時(`record_type` と `source_id` は実装で採用中。案)。
- 開始通知で更新する。直近の開始通知の内容である。
- **削除の判断・実行には使わない**(使うのは `deletion_result-{crawl_id}` に複写した値)。ソース削除の停止にも使わない(停止は自分の削除結果を読んで行う)。
- 実際に使う場面は、開始通知の 409 判定(現行世代の `crawl_started_at` より古い通知の拒否。案)のみに見える(K24 の再送の比較には、`deletion_result-{crawl_id}` に複写した値を使い、現行世代は使わない)。これは他の記述からの推測で、用途の追加はしない。

### 2.2 `deletion_result-{crawl_id}`(削除結果)

| 項目 | 説明 |
| --- | --- |
| `record_type` | `deletion_result`(上記。案。実装で採用中) |
| `crawl_id` | クロールのジョブ ID。ID の `{crawl_id}` と同じ値(案。実装で採用中) |
| `source_id` | |
| `status` | 第3章の状態値 |
| `reason` | `failed` の理由コード、または `discarded` の理由(第3章)。`validation_failed` では、件数照合の不一致、スキップ文書 ID 一覧とサイズ超過文書 ID 一覧の合算件数の上限超過、T > D(下記。確定。architecture K69)を区別する(理由コード名は案。実装で採用中。第3章) |
| `reason_detail` | `failed` の理由 `delete_error` の詳細。削除のエラーの種類、または削除対象の件数が保持できる上限(仮値。値は未決)を超えたことを示す `target_limit_exceeded`。種類だけを持ち、文書の内容は含めない。ほかの場面では保存しない(案。実装で採用中) |
| `outcome` | 終了通知の `outcome`(`enumeration_completed` / `failed` / `cancelled`) |
| `enumerated_count` | Crawler が `document_id` で重複を除いて数えた、列挙で見つかった文書の数(スキップ・抽出失敗の文書を含む) |
| `n_seen` | 当該 `source_id` で `last_seen_at >= crawl_started_at` の件数(リフレッシュ後の検索インデックス) |
| `e_missing` | スキップ文書 ID 一覧(終了通知の `skipped_document_ids`)とサイズ超過文書 ID 一覧(終了通知の `oversize_document_ids`。原本サイズ超過で登録されなかった文書の ID の一覧。案。architecture P32)に含まれる文書 ID のうち、検索インデックスにないものの件数 |
| `skipped_document_ids` | 保存したスキップ文書 ID 一覧。終了通知の `skipped_document_ids`(重複除去・ソート済みの正規化したもの)。`enumeration_completed` の終了通知の受理時に、`finish_request_digest` と同じ書き込みで保存する。合算件数が上限を超える通知では保存しない。`failed` / `cancelled` の終了通知でも保存しない。`deletion_result` が終端状態へ遷移する書き込みと同じ書き込みで削除する(architecture K31、K34、K35、K36。確定) |
| `oversize_document_ids` | 保存したサイズ超過文書 ID 一覧。終了通知の `oversize_document_ids`(正規化したもの)。保存・削除の規則は `skipped_document_ids` と同じ |
| `skip_and_oversize_id_count` | スキップ文書 ID 一覧とサイズ超過文書 ID 一覧の合算件数。合算件数が上限を超えた通知では、2つの ID 一覧を保存せずに、この件数を記録する(architecture K34、K42。確定)。`enumeration_completed` の受理では、上限以内でも件数を記録する(案。実装で採用中) |
| `skip_and_oversize_id_limit_exceeded` | 2つの ID 一覧の合算件数が上限を超えたか。上限を超えた通知の事実を残す。削除の判定の順番が来たときに `validation_failed` にする(architecture K34、K42。確定)。`enumeration_completed` の受理では、上限以内でもフラグ(偽)を記録する(案。実装で採用中) |
| `target_count`(T) | 削除対象の件数。同一リフレッシュ後に取得した ID の件数(ID の取得時点の保証はしない。architecture K47。下記) |
| `denominator`(D) | 割合ルールの分母 |
| `deleted_count` | 削除した件数。進捗として各バッチの前に、そこまでの累計を記録する(第6章。確定。architecture K62)。記録済みの件数は減らさない。再起動の整理での扱いは第5章 |
| `forced` | 強制削除モードで実行したか。複写した `force_delete` そのもので、別の項目を重ねて持たない |
| 設定スナップショットの複写 | `ttl`、`ratio_threshold`、`min_delete_count`、`force_delete`、`crawl_started_at`、`rewrite_mode`(再書き込みモード。architecture K33。省略は `false` に正規化して複写する。K37。確定)(第4章)。項目名は未決(U-1) |
| `finish_received_at` | 終了通知(`enumeration_completed`)を最初に受理した日時。永続化してから 202 を返す。再送(2 回目以降)では書き換えない(architecture K25。下記) |
| `finish_request_digest` | 終了通知のダイジェスト。最初に受理した終了通知の内容のダイジェスト(下記)。`finish_received_at` と同じ書き込みで保存する(`outcome` が `failed` / `cancelled` でも保存する)。`source_id` は含めない前提(任意。architecture K32。照合は受理前の確認で行う)。項目名は architecture K42 で確定。終端状態になっても残す |
| `deletion_started_at` | 待機から判定への遷移で書く(`if_seq_no` の条件付き更新。案) |
| `started_at` | 開始通知を受理して結果を作成した日時(案。実装で採用中) |
| `ended_at` | 終端状態へ遷移した日時。終端状態への遷移の書き込みで記録する。Status API の `finished_at` の元になる値(`indexer-api-v0.10.md` 4.5)(案。実装で採用中) |

`oversize_document_ids` は終了通知で `skipped_document_ids` とは別の項目として渡される(案。architecture P32)。スキップした文書もサイズ超過の文書も、検索インデックスに登録されていなければ `e_missing` に数え、件数照合(`enumerated_count` = `n_seen` + `e_missing`)を成り立たせる。ID 一覧の件数の上限は、スキップ文書 ID 一覧とサイズ超過文書 ID 一覧の合算件数に対する上限で、値は実測後に確定する(設計書上は未決。API-U-5(architecture U-2 と同じ論点。architecture K39)。保存する ID 一覧の件数もこの上限に従う)。上限は HTTP リクエストのボディサイズ上限とは別の制限である。原本サイズ超過の文書は、Crawler の送信前だけでなく Indexer も拒否する(二重防御。確定。U-5。architecture K65。ユーザー承認 2026-11-11。0002 §3 #1)。Indexer が拒否した文書は、すでに検索インデックスにある同じ文書を書き換えない。Crawler 側の拒否の有無・エラーの記録先・ジョブの `status` への影響は未決のまま(architecture U-5 の残り)。

**保存した ID 一覧と、その保存・削除(architecture K31、K34、K35、K36。確定)**: 待機中の削除(先行する削除が実行中の間、順番を待つ削除)が、`E_missing` の計算と削除対象からの除外(architecture 9.5、9.6)に使うスキップ文書 ID 一覧とサイズ超過文書 ID 一覧を、判定の時点まで参照できるようにするため、`enumeration_completed` の終了通知の受理時に、`finish_request_digest` と同じ書き込みで、2つの ID 一覧(正規化したもの)を `deletion_result` に保存する。削除の判定は、待機中だったものを含め、保存した ID 一覧を使う。`outcome` が `failed` / `cancelled` の通知は件数照合も削除の判定も行わないので、2つの ID 一覧が含まれていても保存せず、ダイジェストだけを保存する(K36)。2つの ID 一覧の合算件数が上限を超える通知は、202 で受理し、ID 一覧そのものは保存せず、`skip_and_oversize_id_count` と `skip_and_oversize_id_limit_exceeded` を記録する。削除の判定の順番が来たときに `validation_failed` にして削除しない(それまで `status` は `running` のまま。K34)。`deletion_result` が終端状態へ遷移する書き込みと同じ書き込みで、保存した ID 一覧を削除する(ダイジェストは残す。再送の比較に使うため。K35)。件数照合の結果である `e_missing` は残る。専用の待ち行列を持たない方針(第5章)を変えず、待ち行列の導出に必要な状態も `loreley-deletions` に持つ。

**終了通知の `source_id` の照合(architecture K32。確定)**: 終了通知は、受理時の分岐(再送かどうかの判定を含む)より前に、リクエストの `source_id` と `deletion_result.source_id` の一致を確認する。不一致なら 409(`finish_source_mismatch`。architecture K40。`indexer-api-v0.10.md` 3.4、4.4)を返し、状態を変えず、何も書かない。ダイジェストに `source_id` を含めない前提(任意。K32)なのは、この照合を受理前に行うため。未知の `crawl_id`(`deletion_result` が存在しない)は照合できないので、202 を返して破棄する(`indexer-api-v0.10.md` 4.4 の分岐 2)。

**終了通知の再送(architecture K25。確定)**: 最初に受理した終了通知の内容を基準にする。2 回目以降は、再処理せず `finish_received_at` も書き換えない。内容が最初と同じなら冪等に 202、異なれば 409 を返し、状態を変えない。比較のため、最初の通知の**終了通知のダイジェスト**(`finish_request_digest`。`outcome`、`enumerated_count`、重複除去・ソート済みのスキップ文書 ID 一覧とサイズ超過文書 ID 一覧の正規化 SHA-256。`finished_at` は除く。`source_id` も含めない前提(任意。K32))を `deletion_result` に保存する。Crawler は最初の通知内容を `loreley-jobs` に保存して固定し、再送では同じ内容を送る。`outcome` が `failed` / `cancelled` の通知は、`finish_received_at` を記録せず `failed` を記録する(ダイジェストは保存する)。再送かどうかは、ダイジェストが記録済みかで判定する(`finish_received_at` や終端状態の有無は使わない)。ダイジェストが記録済みの結果に対する再送は、同じ内容なら 202、異なれば 409 を返す。ダイジェストが未記録のまま終端状態になった結果(終了通知が届かないまま `superseded` になった旧世代など)への遅れた終了通知は、比較せず 202 を返す。受理の書き込みは、開始通知と同じソース単位の直列処理の中で、`if_seq_no` の条件付き更新で行う(architecture 9.5、9.9(4))。409 の本文は共通エラー形式でコード(`finish_content_mismatch`)と短いメッセージだけを返す。最初に受理した終了通知の全文・ダイジェスト・受理済みの状態の詳細は返さず、Status API で確認する(architecture K40、K43。受理の有無の読み方は `indexer-api-v0.10.md` 4.5)。

T・D の定義は割合ルール(`indexer-architecture-v0.10.md`)を参照。T と D は同一リフレッシュ後にそれぞれ取得するが、取得の間の更新(D の増減)を排除する取得方式(読み取りの固定)は保証しない。PIT なしの取得が厳密なスナップショットを保証するとは扱わない(architecture K47。現行方針を採用し、競合試験で検証する。安全性に問題が見つかったら PIT の利用を再検討する)。D を減らす操作は削除だけで、削除は直列化されている。ただし T > D となった場合は件数の食い違いとして削除を見送る(`validation_failed` として記録する。`reason` は `target_exceeds_denominator`)。このガードは強制削除モードでも適用し、割合ルールの判定より前に確認する(確定。architecture K69。ユーザー承認 2026-11-11。0002 §3 #10)。対象が 0 件のときは T > D にならず、`deleted`(0 件)になる。K47 で確定したのは、取得方式の現行案(PIT なし)、実機での検証、問題があれば PIT を再検討することまで。

**`crawl_started_at` の複写は照合元でもある(architecture K23。確定)**: `deletion_result-{crawl_id}` の複写 `crawl_started_at` は、件数照合と削除対象の判定に使うほか、バッチ登録と `last_seen_at` の部分更新で Crawler が渡す `crawl_started_at` の検証元にもなる(第4章)。

**複写項目は開始通知の再送の比較元でもある(architecture K24。確定。U-9)**: 同じ `crawl_id` で `running` のときに開始通知が再送されたら、複写した `source_id`、`crawl_started_at`、`ttl`、`ratio_threshold`、`min_delete_count`、`force_delete`(`forced`)、`rewrite_mode`(architecture K33)と今回の内容を直接比較する。一致なら成功(状態不変)、不一致なら 409(状態不変)。`rewrite_mode` は、省略を `false` に正規化した複写済みの値と、今回の値(同じく省略は `false`)を比べる。省略と `false` の違いでは 409 にしない(architecture K37)。比較には `deletion-{source_id}` を使わない(上書きされるため)。

**U-1 設定スナップショットの項目名**(architecture U-14 の一部と同じ論点): 関連する記述の間で表記が揃っていない。

| 場所 | 表記 |
| --- | --- |
| 開始通知 | `ttl` / `ratio_threshold` / `min_delete_count` / `force_delete` |
| `deletion-{source_id}` | 「TTL、しきい値、最小件数」と `force_delete` |
| `deletion_result` | 複写項目に加えて `forced` |
| Status API | 「しきい値」 |

複写の項目名は未決で、`ratio_threshold` などの名称は案である。

開始通知の任意項目 `rewrite_mode`(再書き込みモード。採用は architecture K26、名称と指定経路は K41 で確定)は、設定スナップショットの一部として `deletion_result` に複写して保持する(architecture K33。確定)。バッチ登録では、受理条件の確認で取得した `deletion_result` から参照する。削除の判断・実行には使わない。省略は `false` に正規化して複写する(architecture K37)。

保持と整理:

- ソースごとに、**終端状態の結果を**直近 N 件保持し、古いものは Indexer が消す。N は未決(U-3。architecture U-2 の保持件数 N と同じ論点)。
- 整理の対象は終端状態の結果だけ。`running`(待機中を含む)は数えず、消さない。
- 整理の規則(案。実装で採用中。0020 §6-2(0021 で全て承認)。architecture 9.4): 結果が終端状態へ遷移する書き込みの後に、そのソースの終端状態の結果を新しい順(`ended_at`、`started_at`、`crawl_id` の降順)に並べ、N 件を超えるものを消す。ソースごとの現行世代 `deletion-{source_id}` は整理の対象外。OpenSearch の一時的な異常で整理に失敗しても終端状態の書き込みは成功のまま残り、次の終端遷移で整理される(案。実装で採用中)。この規則の確定、N の値(U-3)、マッピング全体(U-2)は未決のまま。

### 2.3 入力と記録の対応表

開始通知・終了通知で受け取る値が、どの記録のどの項目になるかの対応。書き込み主体はすべて Indexer(Deletion Manager)。

| 入力 | `deletion-{source_id}` | `deletion_result-{crawl_id}` | 備考 |
| --- | --- | --- | --- |
| 開始通知の `crawl_id` | `crawl_id` | ID の一部(`deletion_result-{crawl_id}`) | 世代判定と記録の特定に使う |
| 開始通知の `crawl_started_at` | `crawl_started_at`(世代判定のみ) | `crawl_started_at`(複写。照合元。判定・実行に使う) | 判定・実行・照合には複写を使う |
| 開始通知の `ttl`、`ratio_threshold`、`min_delete_count`、`force_delete` | 設定スナップショット(判断には使わない) | 複写(`forced` は複写した `force_delete`) | 項目名は未決(U-1) |
| 開始通知の `rewrite_mode` | なし | 複写(architecture K33。省略は `false` に正規化して保存。K37) | バッチ登録が参照する。判断・実行には使わない。項目名は未決(U-1) |
| 終了通知の `outcome` | なし | `outcome`、`status`、`reason` | `failed` / `cancelled` は `failed` を記録 |
| 終了通知の `enumerated_count` | なし | `enumerated_count` | 件数照合の左辺 |
| 終了通知の `skipped_document_ids`、`oversize_document_ids` | なし | `e_missing`(検索インデックスにない文書の件数)と、保存した ID 一覧(`skipped_document_ids`、`oversize_document_ids`。architecture K31。合算件数が上限を超える通知、`failed` / `cancelled` の通知では保存しない。K34、K36) | 保存した ID 一覧は終端状態へ遷移する書き込みと同じ書き込みで削除する(K35)。上限超過時は `skip_and_oversize_id_count` と `skip_and_oversize_id_limit_exceeded` を記録する |
| 終了通知の `source_id` | なし | なし(`source_id` と照合し、不一致なら 409。architecture K32) | 保存しない。ダイジェスト(`finish_request_digest`)にも含めない前提(任意。K32) |

## 3. 削除結果の状態(`status`)

状態名の一覧と各状態の意味は案(`indexer-architecture-v0.10.md` P25。実装で採用中で、実装の状態値はこの表と同じ)。確定は、旧い削除を止めないこと、`interrupted` / `stale` の廃止、`discarded` の理由が `superseded` / `source_deleted` の 2 つであること、`failed` の範囲まで。

| 状態 | 意味 |
| --- | --- |
| `running` | 開始通知を受けてから終端状態になるまで(終了通知待ち、待機中、判定中、削除中を含む) |
| `deleted` | 判断を通り、削除を完了した(対象が 0 件の場合を含む)。`deleted_count` を記録する。強制削除モードなら `forced=true` |
| `skipped_by_ratio` | 割合ルールで削除しなかった。T、D、しきい値を記録する |
| `validation_failed` | 次のいずれか。区分: (1)(2)(3)とも確定。(1) 件数照合の不一致(`reason` は `count_mismatch`)。(2) スキップ文書 ID 一覧とサイズ超過文書 ID 一覧の合算件数の上限超過(判定の順番が来たときに記録する。architecture K34。`reason` は `id_limit_exceeded`)。(3) T > D(件数の食い違いとして削除を見送る。強制削除モードでも適用する。architecture K69。`reason` は `target_exceeds_denominator`)。`reason` で区別して記録する(理由コードの名称は案。実装で採用中)。数値を記録する |
| `discarded` | 次のいずれか。`reason` に区別を記録する(理由は 2 つ)。(1) 終了通知が届かなかった旧い世代の整理(新しい開始通知による。理由 `superseded`。`finish_received_at` の無いものに限る)。(2) ソース削除で破棄された(理由 `source_deleted`)。`superseded` の結果に遅れて届いた終了通知は何もしない。未知の `crawl_id` は記録しない |
| `failed` | 削除が完了しなかった、または行わなかった。理由コードを `reason` に記録する。再開しない。削除結果の状態であり、ジョブの status は変えない |

`running` 以外が終端状態である。

### 3.1 `failed` の理由コード(案。実装で採用中。Crawler・Admin API の設計の確定時に名称を再確認する)

| 理由コード | 場面 |
| --- | --- |
| `outcome_failed` / `outcome_cancelled` | 終了通知の `outcome` が `failed` / `cancelled`(列挙の失敗、取り消し)。削除しない |
| `maintenance` | メンテナンスフラグが立っていた(判定の前、バッチの前。待機中だったものが順番が来た時点で立っていた場合を含む)。フラグの文書があって `enabled` が真偽値の `false` と明示されていないとき(欠落・真偽値以外)も「立っている」とみなす(fail-closed。確定。architecture K63。ユーザー承認 2026-11-12。0014)。フラグの形式は Crawler・infra の設計の確定時に再確認する(architecture U-34) |
| `indexer_restart` | 待機中、判定中、削除の実行中に Indexer が再起動した |
| `delete_error` | 削除のエラーが、リトライ設定の回数まで試しても直らなかった(エラーの種類を `reason_detail` に記録する)。また、削除対象の件数が保持できる上限(仮値。値は未決)を超えた(`reason_detail` は `target_limit_exceeded`。案。実装で採用中) |

## 4. 設定スナップショットの複写(案)

旧い削除が、あとから届いた新しい世代の設定で動かないようにするために、この複写を置く(案)。

- 開始通知を受理するとき、通知の `ttl`、`ratio_threshold`、`min_delete_count`、`force_delete`、`crawl_started_at`、`rewrite_mode`(省略は `false` に正規化して複写する。architecture K37)を `deletion_result-{crawl_id}` に複写する(`source_id` は `deletion_result` の項目として持つ)。
- 判定と実行は、常にこの複写した値を使い、`deletion-{source_id}`(新しい開始通知で上書きされる)からは読まない。
- 旧い削除は、待機中や実行中に新しい開始通知が来て設定が変わっても(強制削除モードの指定の有無を含む)、自分のクロールの設定で最後まで動く。同様に、判定に使うスキップ文書 ID 一覧とサイズ超過文書 ID 一覧も、自分の `deletion_result` に保存した ID 一覧を使う(architecture K31。第2.2章)。
- `rewrite_mode` を複写するのは、バッチ登録が、リクエストごとのモード指定ではなく、受理条件の確認で取得した `deletion_result` の値で動くようにするため(architecture K33)。同じクロールのすべてのバッチに同じモードが適用される。
- `crawl_started_at` を複写するのは、件数照合の `n_seen`(`last_seen_at >= crawl_started_at` の件数)と削除対象の判定が、新しい世代の `deletion-{source_id}`(上書きされる)ではなく、自分のクロールの開始時刻で行われるようにするため。複写がないと、待機中に世代が進んだ旧い削除が、新しい `crawl_started_at` で照合・判定してしまう。

### 4.1 バッチ登録・`last_seen_at` の受理条件(architecture K23。確定。U-8)

- 対象: 通常クロール(開始通知を伴う)の、バッチ登録(`documents:batch`)と `last_seen_at` の部分更新(`last-seen`)のリクエスト(`indexer-api-v0.10.md`)に限る。これらは `crawl_id` と `crawl_started_at` を必須とする。ソース削除の要請は開始通知を伴わず `deletion_result` が存在しないため、別の要請として扱い、この判定の対象外とする。`deletion_result` を要求しない。`crawl_id` を省略することでは区別しない。
- **受理条件**: 次のすべてを満たすときだけ受理する。(1) `deletion_result-{crawl_id}` が存在する。(2) `source_id` が一致する。(3) `crawl_started_at` が複写値と一致する。(4) `status` が `running`。(5) `finish_received_at` が存在しない。(6) Crawler のロック所有確認に成功する。(1)〜(5) はリクエストの先頭で 1 回確認し、(6) は文書ごとに確認する。(6) の失敗は文書単位の `lock_not_owned` で、下記の拒否の名称(5 つ)には含めない(`indexer-api-v0.10.md` 3.2、API-U-13)。
- **終端状態への登録は拒否**: `superseded` / `discarded` / `failed` / 判断済み(`deleted`・`skipped_by_ratio`・`validation_failed`)の `deletion_result` には登録しない。`crawl_started_at` が一致していても同じ。終了通知を受理済み(`finish_received_at` あり)の結果も拒否する。登録後に件数照合の前提(列挙の完了時点)が崩れるのを避けるため。
- 照合先: `deletion_result-{crawl_id}`(リクエストの `crawl_id`)に複写した `crawl_started_at`。`deletion-{source_id}` の値は新しい開始通知で上書きされるため、照合には使わない。
- 拒否はいずれもリクエスト全体のエラーとし(文書単位ではない)、再試行しても直らないため非リトライとする。Crawler はジョブを `failed` にする。`last_seen_at` は書かない。拒否の種類ごとにエラー名を分ける(`crawl_not_started` / `crawl_source_mismatch` / `crawl_started_at_mismatch` / `crawl_already_closed` / `crawl_finished`。名称は確定。architecture K66。ユーザー承認 2026-11-11。0002 §3 #15。`indexer-api-v0.10.md` 3.4)。
- `deletion_result-{crawl_id}` が存在しない場合は、開始通知を受けていない `crawl_id`、保持件数を超えて消えた結果、`loreley-deletions` の喪失(7章)を区別せず、「存在しない」として拒否する。削除が遅れるだけで安全側に倒れる。
- 受理条件を課さない場合は、誤った `crawl_started_at` や旧世代の遅れた書き込みが `last_seen_at` に反映されても安全側(削除が遅れる側)に倒れるが、誤りの検出が遅れる。
- **U-8(確定。architecture K23。`indexer-api-v0.10.md` の API-U-18 と同じ論点)**: 上記の受理条件を課し、終端状態・受理済み・存在しない結果への登録は拒否する。拒否のエラー名は確定(architecture K66。API-U-19)。

## 5. 待ち行列

- 専用の待ち行列は持たない(確定。architecture K68。ユーザー承認 2026-11-11。0002 §3 #2)。待ち行列は、`loreley-deletions` の状態(`finish_received_at` があって終端状態でない削除結果。`finish_received_at` の順で、同値なら `crawl_id` の辞書順)から導く。待機中の削除の判定に必要な ID 一覧(スキップ文書 ID 一覧とサイズ超過文書 ID 一覧)も、その削除結果に保存されている(architecture K31。合算件数が上限を超えた通知を除く)。
- Indexer の再起動では待機中のものも `failed`(`indexer_restart`)になり、削除は実行しない。待ち行列を復元する必要はなく、このとき `failed` が終端状態なので、保存した ID 一覧は同じ書き込みで削除する(architecture K31、K35)。整理の対象は、`finish_received_at` があって終端状態でない結果(待機中・判定中・実行中)で、HTTP の受け付けを始める前に行う。`finish_received_at` のない `running` には触れず、次の開始通知で `superseded` になる(確定。architecture K68。ユーザー承認 2026-11-11。0002 §3 #3)。このとき `deleted_count` が未記録なら 0 を記録し、記録済みの件数は減らさない(進捗は各バッチの前に書くので、未記録なら削除は 1 件も実行されていない。Status API が `running` の間は未記録の進捗を推測して表示しない(architecture K43)ことと、終端状態の事実として 0 を記録することは別の話である。architecture D-93。確定。architecture K62)。
- 先行する削除結果(確定。architecture K68): 同じ `source_id` で、`finish_received_at` が自分より前(同値なら `crawl_id` の辞書順)かつ終端状態でない削除結果。`finish_received_at` のない `running` は先行にならない。同値の順序の規則(U-4)は確定した。
- 削除ワーカーは、全ソースを通して直列に、待ち行列の先頭の 1 件だけを処理する。走査の契機は、終了通知の受理による起床通知と、一定間隔の走査(確定。architecture K68。ユーザー承認 2026-11-11。0002 §3 #2)。先行する削除が終端状態になるまで、待機中の結果は何も書かず、検索インデックスも読まない。
- **不正な記録の扱い**(確定。architecture K62。ユーザー承認 2026-11-12。0021 §1): 削除結果の一覧を読む場面(待ち行列、先行する結果、再起動の整理、`superseded` 化、ソース削除の破棄)では、形式が不正な記録(項目の型や値が不正)を一覧から除き、`record_id` だけをログに出す。不正な記録は、読まず、書き換えもしない。そのため、先行する結果とは扱われず、終端状態にならず `running` のまま残り、後続の削除は自分の記録だけで判定を進める。削除対象は TTL の再確認と `source_id` の照合で守られるので、削除の量は増えない。
- **判定時に必須項目を欠く結果**(受容事項。architecture 9.13(11)。個別の承認の記録はない。`apps/indexer/README.md` の既知の制限): 待機中の削除結果が判定のときに必須項目を欠いていると(形式は正しいが ID 一覧や `enumerated_count` がない場合など)、削除せず、その結果が待ち行列の先頭に残って後続の全ソースの削除が止まる(削除しない側に倒れる)。判定の失敗を示す WARNING のログを監視する前提で、受容する。
- **判定・実行の全体異常(文書ごとの削除エラーを除く)**(確定。architecture K62。ユーザー承認 2026-11-12。0021 §1): OpenSearch の全体異常などで判定や実行が失敗したときは、`status` を変えず `running` のまま(判定の前に `deletion_started_at` は書かれる)、走査ごとに再実行する。再実行は判定(件数・T・D の取り直し)からやり直すが、`deleted_count` は引き継ぐ(減らさない)。連続して失敗する間は走査の間隔を倍々に伸ばす(上限あり)。連続失敗の回数で `failed` にはしない(ハング保護を設けない方針と同じ。architecture 9.9)。連続失敗で `failed` にする案と、先頭の結果が失敗したときに次のソースへ進む案は、直列の意味が変わるため採らない。削除の実行フェーズで、文書の削除のエラーだけは、リトライ設定の回数まで試したあと `failed`(`delete_error`)にする(第3.1章)。
- 判定・実行の順序と直列化の方式は `indexer-architecture-v0.10.md`、Status API で待機中を見せる任意項目 `waiting_for`(確定。architecture K66。ユーザー承認 2026-11-11。0002 §3 #17)は `indexer-api-v0.10.md` を参照。値は、直前に先行する結果の `crawl_id` で、結果が `running` で先行する結果があるときだけ返る。

## 6. 書き込みの整合に関わる規則(Schema に影響する範囲)

- **検索インデックスの文書の条件付き削除が競合したら読み直して再判定する(案。architecture 9.8)**: 削除は、削除の直前に読んだ文書の `_seq_no` / `_primary_term` を `if_seq_no` / `if_primary_term` に付けた条件付き削除である。要約の書き戻しや新しいクロールの登録などで文書が更新されると 409(条件外れ)になり、更新された文書は消えない。409 のときは文書を読み直し、TTL を再判定して(満たさなければ削除しない)、満たせば読み直した値で再び削除する。TTL の再確認は、`last_seen_at + TTL < 現在時刻` に加えて、読み直した文書の `source_id` が自分の結果の `source_id` と同じことも確認する(他のソースの文書を消さないための安全側の追加で、削除の保証は増減しない。`last_seen_at` が読めない、または無い文書は期限切れとみなさない。確定。architecture K61。ユーザー承認 2026-11-12。0021 §2)。TTL の判定に、今回のクロールが見た文書を除くための追加の条件は設けない。TTL が極端に短いときに今回のクロールが見た文書も削除対象になりうる点は、受容事項(architecture 9.13(9))である(確定。architecture K70。ユーザー承認 2026-11-12。0014)。読み直しの回数はリトライ設定の回数までで、超えたら削除せず、その文書は次の期限削除に委ねる。条件外れの上限超過、TTL の再確認で除外した文書、すでにない文書は `deleted_count` に数えない。削除結果は `deleted` のまま終了する。
- **保存した ID 一覧の削除**(architecture K31、K35。確定): スキップ文書 ID 一覧とサイズ超過文書 ID 一覧は、`deletion_result` が終端状態へ遷移する書き込みと同じ書き込みで削除する。`deleted` / `skipped_by_ratio` / `validation_failed` / `failed` / `discarded` のいずれでも同じ。ダイジェスト(`finish_request_digest`)と、件数照合の結果(`e_missing` など)は残す。
- ソース削除の停止確認や状態遷移の書き込みは、`if_seq_no` の条件付き更新で行い、終端状態(ソース削除の `discarded`)を上書きしない(案)。自分の削除結果が読めない(404。記録ごと削除された場合)ときも、書き換えずに止まる。
- **`deleted_count` の進捗の記録**(確定。architecture K62。ユーザー承認 2026-11-11。0002 §3 #18): 削除の各バッチの前に、自分の削除結果を読み直して終端状態でないことを確認し、`deleted_count`(そこまでの累計)と判定の数値(`n_seen`、`e_missing`、T、D)を `if_seq_no` の条件付き更新で書く。この書き込みが、自分の結果の終端確認を兼ねる。バッチの途中の削除は、次の記録(または終端状態への遷移の書き込み)まで反映されない。記録済みの `deleted_count` は減らさない(判定からやり直す再実行で、削除済みの件数を消さないため)。
- 受理済みの旧い削除は、新しい開始通知で `discarded` にならない。新しい開始通知が `discarded`(`superseded`)にするのは、`finish_received_at` の無い旧い結果だけ。この `superseded` 化と終了通知の受理(`finish_received_at` の記録)が競合しないよう、Deletion Manager はソースごとに受理を直列に処理する(確定。architecture K67。ユーザー承認 2026-11-11。0002 §3 #19。開始通知と終了通知の受理は、同じソース単位の排他で直列化する)。`superseded` 化も、読み直して「`finish_received_at` が無い」ことを確かめたうえで、条件付き更新で行う。
- データソースを削除するとき、そのソースの `deletion-{source_id}` と `deletion_result-*` はすべて削除される(実行は Crawler のジョブ。破棄・削除は Indexer に要請する。`indexer-architecture-v0.10.md`)。
- **ソース削除の排他と `discarded` への応答**(ロックの保持は architecture K29。確定。削除のバッチとソース削除の要請(ソース削除 1 の `discarded` への更新と、ソース削除 2 の文書の全削除。ソース削除 3 の `deletion_result-*` の削除は排他を使わない)を同じソース単位の排他で直列化し、ソース削除を優先する専用の排他を採用していること(architecture K61。ユーザー承認 2026-11-12。0021 §2)も確定。`discarded` の最優先処理は案(実装で採用中。architecture P29)): ソース削除のジョブは、`source_id` 単位のロックを最後まで保持し、ロック文書の削除は最後に行う。削除結果を `discarded`(`source_deleted`)にする要請は、Deletion Manager のソース単位の直列実行で最優先とする。実行中のバッチの完了直後、次のバッチの前確認や待機中の判定より前に `discarded` を書き、そのソースの終端でない削除結果(待機中を含む)をすべて `discarded` にしてから応答する。応答の時点で、そのソースの削除バッチは実行されていない。`discarded` への更新が完了しても、実行中のバッチが止まったことにはならないため、`discarded` の書き込みだけでは、`deletion_result-*` の削除や検索インデックスの文書の削除に進まない。バッチ内でハングした場合は、応答を待ち続ける(受容事項。ハング保護は設けない確定事項と整合する)。Crawler 向け要件(architecture K29。確定。9.14): (1) 削除中はジョブがロックのリースを更新し続ける、(2) 所有権を失ったら後続の削除操作を停止する、(3) 再実行で復旧する、(4) 削除中のデータソースに新しいクロールを起動しない。「削除中」状態をどこに持つか、Crawler 側のロック設計の具体は未決(Crawler 領域。U-7。architecture U-4)。
- **ソース削除の操作は冪等で、再実行できる(案。architecture P29)**: Indexer へのソース削除の要請(`discarded` への更新、`deletion_result-*` の削除、検索インデックスの文書の削除)は、何度実行しても結果が変わらない(`discarded` は終端状態を上書きせず、すでに削除された記録・文書は何もしない)。検索インデックスの文書は、`delete_by_query` を、実行前の refresh と完了後の `_count`=0 の確認つきで、0 になるまで再実行して消す(architecture K20、K28。確定。再実行の上限を設ける(数値は実測後に確定する。設計書上は未決。指定回数の再実行でも完了しなければソース削除のジョブは `failed` になり、残った文書は後続の再実行で削除する。architecture K48、U-31(5))。ロック保持=削除中は新しいクロールを起動しないことが前提。`indexer-api-v0.10.md` 4.7)。ソース削除のジョブがロックのリース切れ(`lock_not_owned`)で `failed` になっても、再実行すれば途中から完了する。Indexer はロックの具体に依存せずに正しく動く。ロックの保持は architecture K29 で確定し、Crawler 側のロック設計の具体は未決(U-7)。

## 7. マッピングと運用

- `loreley-deletions` のマッピング全体(`dynamic: strict` の適用、ID、保持件数を超えた削除結果の削除方法)は未決(U-2。architecture U-6 のうち、保存した ID 一覧の項目を除く部分と同じ論点)。保存した ID 一覧の項目のマッピングは確定している(下記。architecture K52)。
- **実装が前提としているマッピング**(案。実装で採用中。Indexer 実装の仮定義で、Crawler・infra 設計の確定時に再確認する。architecture U-34。実機での確認は architecture U-31): Indexer はインデックスの作成もマッピングの定義もせず、既存のマッピングに従って読み書きする。次を前提とする。(1) `record_type`・`status`・`source_id` は、`term` / `terms` で絞り込むので keyword。(2) `crawl_id`・`started_at`・`ended_at` は、保持件数の整理で新しい順に並べるので、並べ替えに使える型(`crawl_id` は keyword。日時は固定長の UTC ミリ秒文字列なので、keyword でも `date` でも時刻順になる)。(3) `finish_received_at` の有無で絞り込む。値のない項目は保存しないので、項目がないことが「なし」を表す。`dynamic: strict` を適用する場合は、第2章の項目をすべて定義する必要がある。マッピングが前提と違うと、テストが通っても実機で失敗しうる。
- 検索インデックスの共通方針(`dynamic: strict`、`keyword` 化、`number_of_shards: 1`、`number_of_replicas: 0`。`search-index-v0.10.md` 第4章。これ自体が推測で、ユーザー未確認)を、このインデックス(Store 層)に適用するかも未決である(適用するかは決めておらず、確定扱いにしない。`indexer-architecture-v0.10.md` 3.5 も、Store 層のマッピング方針は本書を参照するとしており、同じく未決)。そのため、`loreley-deletions` 全体のマッピングの JSON は載せない。
- **保存した ID 一覧のマッピング**(architecture K52。確定): スキップ文書 ID 一覧(`skipped_document_ids`)とサイズ超過文書 ID 一覧(`oversize_document_ids`)は、`_source` に保持するが、検索・集計の対象にしない。どちらも文字列配列なので、`keyword` 型に `index: false` と `doc_values: false` を指定する。`enabled: false` は通常のオブジェクトフィールド向けの指定なので、文字列配列にはそのまま指定しない。

```json
{
  "skipped_document_ids":  { "type": "keyword", "index": false, "doc_values": false },
  "oversize_document_ids": { "type": "keyword", "index": false, "doc_values": false }
}
```

- インデックス名は仮名。
- **Schema 検証観点**(architecture K52): 保存したスキップ文書 ID 一覧とサイズ超過文書 ID 一覧が `_source` から読めること、および検索・集計(`term` 検索、`terms` 集計、ソート)の対象にならないこと(`keyword` / `index: false` / `doc_values: false`)を、実機で確認する。
- **保存した ID 一覧の容量と保持期間**(architecture K31、K34、K35): 保存した ID 一覧を持つのは、終了通知を受理してから終端状態になるまでの `deletion_result` だけ(待機中・判定中・削除中。通常は短期間)。件数の上限は、スキップ文書 ID 一覧とサイズ超過文書 ID 一覧の合算件数の上限(API-U-5。architecture U-2 と同じ論点)に従う。上限を超える通知は、ID 一覧を保存せず、`skip_and_oversize_id_count` と `skip_and_oversize_id_limit_exceeded` だけを記録し、判定の順番が来たときに `validation_failed` にする(`reason` で区別。第3章。それまで `status` は `running` のまま)。`enumeration_completed` の受理では、上限以内でも件数とフラグ(偽)を記録する(案。実装で採用中)。終端状態になれば保存した ID 一覧は削除されるため、保持件数 N(U-3)による整理の対象にも、長期の容量にも含まれない(ダイジェストは残る)。上限の値と、保存した ID 一覧を持つ `deletion_result` 1 件あたりのサイズの見積もりは実測後に確定する(設計書上は未決。architecture K39)。
- **再起動と保存した ID 一覧**: Indexer の再起動で未完了の削除(待機中を含む)は `failed`(`indexer_restart`)になり、削除は実行されない。保存した ID 一覧はこの終端状態への遷移と同じ書き込みで削除する(第5章、第6章)。整理の対象は確定(第5章。architecture K68。U-20 を解消)。
- スナップショットは運用者の責務であり、本書は手順を仕様として定めない(architecture K21。確定)。Store 層(`loreley-sources`、`loreley-jobs`、`loreley-deletions`)と検索インデックスは同じ OpenSearch にあるため、運用者が取る 1 つのスナップショットで、設定・ジョブ・削除結果・文書を、取得時点の状態に復元できる(`search-index-v0.10.md` 6章)。整合した復元を求める場合は、関連する書き込み(クロール、削除、要約の書き戻し)を止めてから取得する。停止せずに取得したスナップショットの保証範囲(アプリケーション全体の整合は保証しない)は `indexer-architecture-v0.10.md` 14.1 を正本とする。検索インデックスだけを失った場合は Store 層(本書の削除結果を含む)は残り、再クロールのみで戻る(データソースの再登録は不要)。OpenSearch 全体を失い、スナップショットもない場合は、データソース設定の再登録が必要で、ジョブ履歴・削除結果は失われる(architecture 14.2)。
- **`loreley-deletions` を失った場合**(スナップショットなどからも復元できない): 次のクロールの開始通知で、現行世代が作り直される。それまでに届く終了通知は未知の `crawl_id` として破棄され、削除は行われない。進行中のクロールのバッチ登録と `last_seen_at` の部分更新は、照合先(`deletion_result-{crawl_id}`)がないため拒否される(4.1)。削除結果の履歴は失われる。削除が遅れるだけで安全である(検索インデックスの文書には影響しない)。Status API は該当の `crawl_id` について 404 を返す(確定。architecture K66)。

## 8. 利用側との関係(境界)

- Status API(`GET /crawls/{crawl_id}`。案。実装で採用中)は削除結果を読み取りで返す。利用者は Crawler である。404 を返す条件(確定。architecture K66。ユーザー承認 2026-11-11。0002 §3 #17): 削除結果が存在しないとき。保持件数を超えて消えた `crawl_id`、開始通知を受けていない `crawl_id`、`loreley-deletions` を失った場合は区別せず、同じ 404(`crawl_not_found`)を返す。詳細は `indexer-api-v0.10.md`。
- Admin View の表示は、Admin API が `loreley-deletions` から直接読んだ内容による。確認結果の区分(`confirmed` / `unconfirmed` / `unknown`。案)と登録結果は `loreley-jobs`(Crawler 領域)にあり、この文書の対象外。
- 保持件数 N を超えて削除結果が消えている場合と `loreley-deletions` の喪失は区別できない。どちらも Admin View は「結果不明」と表示する(案)。あとから復元されて現在値が読める場合は、「結果不明」に現在値を併記し、区分は書き換わらない(案)。

## 9. 確認状況

区分: 確定 = ユーザー確定、案 = ユーザー未確定、未決 = 決めていない。確定は architecture の K12、K18〜K56、K57〜K71 に対応する。「実装で採用中」は、Indexer の実装が仮に採用している案で、Crawler・Admin API・infra の設計の確定時に再確認する(architecture U-34)。

| 項目 | 区分 | 備考 |
| --- | --- | --- |
| `loreley-deletions` は Indexer だけが書く(インデックス名は仮名) | 確定 | |
| 削除の判断・実行は Indexer の内部モジュール Deletion Manager | 確定 | |
| 状態名の一覧(`running` ほか 6 つ)と各状態の意味 | 案 | architecture P25。実装で採用中 |
| `interrupted` 廃止(`failed` + 理由コード)、`stale` 廃止(`discarded` の理由は `superseded` / `source_deleted`) | 確定 | |
| 同じソースの削除は直列(方式は案 B。ユーザー承認)、ハング保護は設けない(ユーザー決定) | 確定 | 待ち行列の持ち方などの細部は、下の architecture K68 の行で確定 |
| 削除結果の項目名(`n_seen`、`e_missing`、`deletion_started_at` など)と設定スナップショットの複写 | 案 | 複写の項目名は未決(U-1)。実装で採用中の追加項目(`record_type`、`crawl_id`、`reason_detail`、`started_at`、`ended_at`。第2章。0020 §6-2(0021 で全て承認))を含む |
| 2種類の記録(`deletion-*` と `deletion_result-*`)を同じインデックスに置き、`record_type` で区別する。マッピングは Indexer が作らず、`record_type`・`status`・`source_id` が keyword、`crawl_id`・`started_at`・`ended_at` が並べ替えに使える型、という前提(第2章、第7章) | 案 | 実装で採用中。マッピング全体は未決(U-2)。architecture U-31(実機確認)、U-34(Crawler・infra との突き合わせ) |
| `failed` の理由コード一覧と名称、`validation_failed` の理由コード(`count_mismatch`、`id_limit_exceeded`、`target_exceeds_denominator`)、`delete_error` の `reason_detail` のうち削除対象の件数の上限超過(`target_limit_exceeded`)(第2.2章、第3章) | 案 | 実装で採用中。理由コードの名称は Crawler・Admin API の設計の確定時に再確認する。件数の上限の値は未決 |
| メンテナンスフラグの文書があって `enabled` が真偽値の `false` と明示されていないときは、立っているとみなす(fail-closed)(第3.1章) | 確定 | architecture K63(ユーザー承認 2026-11-12。0014)。フラグの形式は案(architecture U-34) |
| 待ち行列を `loreley-deletions` の状態から導く(専用キューなし)、先行する削除結果の定義(第5章) | 確定 | architecture K68(ユーザー承認 2026-11-11。0002 §3 #2) |
| ソース削除の停止確認(`if_seq_no` の条件付き更新、404 でも書き換えず止まる) | 案 | |
| `waiting_for`、Status API の 404 の条件(削除結果がなければ 404。消えた・開始通知がない・喪失は区別しない)(第5章、第7章、第8章) | 確定 | architecture K66(ユーザー承認 2026-11-11。0002 §3 #17)。API-U-10 を解消 |
| Admin API が `loreley-deletions` を直接読む | 案 | |
| `deletion-{source_id}` の用途(開始通知の世代判定のみに見える) | 推測 | 他の記述からの推測。用途の追加はしない |
| U-1 設定スナップショットの複写の項目名(architecture U-14 の一部と同じ論点) | 未決 | |
| U-2 `loreley-deletions` のマッピング全体、保持件数超過分の削除方法、インデックス名、検索インデックスの共通方針(推測。ユーザー未確認)の適用(architecture U-6 のうち保存した ID 一覧の項目を除く部分と同じ論点。architecture 3.5 も未決) | 未決 | 保存した ID 一覧のマッピングは確定(architecture K52)。実装は、保持件数の整理の規則と、OpenSearch の一時的な異常による整理の失敗を握る挙動(第2.2章。案。0020 §6-2(0021 で全て承認))と、前提とするマッピング(第7章。案)を採用中 |
| U-3 保持件数 N(ソースごと。architecture U-2 と同じ論点) | 未決 | 数値は実測後に確定(architecture K39) |
| U-4 同時刻の `finish_received_at` の順序(`crawl_id` の辞書順。architecture U-14 の一部と同じ論点) | 確定(K68) | 第5章。ユーザー承認 2026-11-11(0002 §3 #2) |
| `crawl_started_at` を設定スナップショットの複写に加える(第4章) | 案 | 複写の項目名は未決(U-1) |
| `e_missing` に `oversize_document_ids` を含める。上限は2つの ID 一覧の合算件数(第2.2章) | 案 | architecture P32。ユーザー未確認。実装で採用中 |
| U-5 原本サイズ超過の拒否主体(Crawler の送信前か Indexer の拒否か。architecture U-5、API-U-4 と同じ論点)。Indexer も拒否し、すでにある同じ文書は書き換えない | 確定(K65) | ユーザー承認 2026-11-11(0002 §3 #1)。エラーの記録先・ジョブの `status` への影響は未決のまま(architecture U-5 の残り)。P32 の構成の前提 |
| 終了通知の再送は、最初に受理した内容と同じなら 202、異なれば 409(案 B)。ダイジェストを `deletion_result` に保存する(第2.2章) | 確定 | architecture K25(2026-11-10)。409 のコード名は architecture K40 で確定 |
| U-6 終了通知の再送で内容が異なる場合の扱い。案 B(異なる内容は 409。ダイジェストを `deletion_result` に保存、Crawler は最初の通知内容を固定)で確定。409 の本文は共通エラー形式でコードと短いメッセージだけを返し、詳細は返さず Status API で確認する(architecture K43) | 確定(K25、K43) | 旧 architecture U-29(K25 で確定)。API-U-21 |
| ソース削除のジョブが `source_id` ロックを最後まで保持し、ロック文書の削除は最後に行う。Crawler 向け要件(1)〜(4)(第6章) | 確定 | architecture K29(2026-11-10) |
| `discarded` は直列実行で最優先(実行中バッチの完了直後、そのソースの終端でない結果を全て `discarded` にしてから応答)、バッチ内ハングは待ち続ける(第6章) | 案 | architecture P29。実装で採用中(個別の承認の記録はない)。ソース削除を優先する専用のソース単位の排他(ソース削除 1・2 が使う。3 は使わない)の採用は architecture K61(ユーザー承認 2026-11-12。0021 §2)で確定 |
| 条件付き削除の条件外れ・TTL 再確認で除外した文書は `deleted_count` に数えず、`deleted` のまま次の期限削除に委ねる(第6章) | 案 | ユーザー未確認。実装で採用中 |
| TTL の再確認に、文書の `source_id` が自分の結果と同じことの確認を加える。`last_seen_at` が読めない・無い文書は期限切れとみなさない(第6章) | 確定 | architecture K61(ユーザー承認 2026-11-12。0021 §2) |
| TTL の判定に、今回のクロールが見た文書を除くための追加の条件を設けない。TTL の誤設定で今回のクロールが見た文書も削除対象になりうることは受容事項(第6章) | 確定 | architecture K70(ユーザー承認 2026-11-12。0014) |
| U-7 ソース削除ジョブのロック(architecture P29、U-4)。ジョブがロックを最後まで保持することと、Crawler 向け要件(削除中のリース更新の継続、所有権喪失時の後続停止、再実行で復旧、削除中のソースに新クロールを起動しない)は確定。「削除中」状態の置き場所と Crawler 側のロック設計の具体は未決 | 確定(K29)。未決部分は Crawler 領域 | architecture 9.14 |
| 通常クロールのバッチ登録・`last_seen_at` の受理条件(`deletion_result` が存在、`source_id` 一致、`crawl_started_at` 一致、`status` が `running`、`finish_received_at` なし、ロック所有確認に成功)。終端状態・受理済み・存在しない結果への登録は拒否。拒否はリクエスト全体のエラー(非リトライ、ジョブ `failed`)。ソース削除は別の要請として扱い対象外(4.1) | 確定 | architecture K23(2026-11-10)。U-8。拒否のエラー名は architecture K66 で確定(ユーザー承認 2026-11-11。0002 §3 #15。API-U-19) |
| U-8 受理条件を課すか、終端状態・存在しない結果への扱い(`indexer-api-v0.10.md` の API-U-18 と同じ論点) | 確定(K23) | 4.1 |
| 開始通知の再送の一致検証(複写項目との直接比較。一致なら成功、不一致なら 409。状態不変) | 確定 | architecture K24(2026-11-10)。U-9。コード名は architecture K66 で確定(ユーザー承認 2026-11-11。0002 §3 #15) |
| U-9 開始通知の再送を複写項目と比較して検証するか(`indexer-api-v0.10.md` の API-U-20 と同じ論点) | 確定(K24) | 検証する |
| ソース削除の操作は冪等で再実行できる。ロックの具体に Indexer は依存しない(第6章) | 案 | architecture P29。ロックの具体は U-7 |
| ソース削除の文書の削除は、`delete_by_query` を `_count`=0 まで再実行して消す。再実行の上限を設け、上限でも完了しなければソース削除のジョブは `failed`、残った文書は後続の再実行で削除する(第6章) | 確定 | architecture K20、K28、K48。再実行の上限の数値は実測後に確定(未決。architecture U-31(5)) |
| スナップショットは運用者の責務。Store 層と検索インデックスは同じ OpenSearch にあり、1 つのスナップショットで取得時点の状態に復元できる。整合した復元を求める場合は、関連する書き込みを止めてから取得する。停止せずに取得したスナップショットは、アプリケーション全体の整合を保証しない。設計書は手順を定めない(第7章) | 確定 | architecture K21(2026-11-10) |
| `rewrite_mode` を設定スナップショットとして `deletion_result` に複写して保持する。バッチ登録は受理条件の確認で取得した `deletion_result` から参照し、開始通知の再送の一致検証の比較項目に加える(異なれば 409)(第2.2章、第4章) | 確定 | architecture K33(2026-11-10)。再書き込みモードの採用は K26 |
| `rewrite_mode` の省略は `false` に正規化して複写し、再送の比較も正規化後の値で行う(省略と `false` の違いでは 409 にしない)。名称 `rewrite_mode` と指定経路(開始通知の任意項目) | 確定 | architecture K37、K41 |
| 終了通知の受理時に、`finish_request_digest` と同じ書き込みで、スキップ文書 ID 一覧(`skipped_document_ids`)とサイズ超過文書 ID 一覧(`oversize_document_ids`)を正規化して `deletion_result` に保存する。待機中の削除の判定もこの保存した ID 一覧を使う(第2.2章、第5章、第6章、第7章) | 確定 | architecture K31(2026-11-10) |
| 2つの ID 一覧の合算件数が上限を超える通知は 202 で受理し、ID 一覧は保存せず `skip_and_oversize_id_count` と `skip_and_oversize_id_limit_exceeded` を記録して、削除の判定の順番が来たときに `validation_failed` にする。保存した ID 一覧は終端状態へ遷移する書き込みと同じ書き込みで削除する(`finish_request_digest` は残す)。`failed` / `cancelled` の終了通知は ID 一覧を保存せずダイジェストだけ保存する。HTTP リクエストのボディサイズ上限は別の制限(受信可能なサイズを超えた場合まで 202 を保証しない)(第2.2章、第6章、第7章) | 確定 | architecture K34、K35、K36 |
| 項目名 `finish_request_digest`(終了通知のダイジェスト)、`skipped_document_ids`(保存したスキップ文書 ID 一覧)、`oversize_document_ids`(保存したサイズ超過文書 ID 一覧)、`skip_and_oversize_id_count`(2つの ID 一覧の合算件数)、`skip_and_oversize_id_limit_exceeded`(合算件数が上限を超えたか) | 確定 | architecture K42 |
| 保存した ID 一覧(`skipped_document_ids`、`oversize_document_ids`)は `_source` に保持し、検索・集計の対象にしない。`keyword` 型に `index: false` と `doc_values: false`(`enabled: false` は文字列配列にそのまま指定しない)(第7章) | 確定 | architecture K52 |
| 合算件数の上限の値、保持件数 N、削除バッチ件数、ポーリング間隔、リトライ回数、`retry_on_conflict`、読み直しの回数は実測後に確定する(実装の仮の初期値は設定として管理する) | 未決(方針は確定) | architecture K39 |
| 終了通知は、処理の前に `source_id` と `deletion_result.source_id` の一致を確認し、不一致なら 409(状態不変)。未知の `crawl_id` は 202 のまま(第2.2章) | 確定 | architecture K32(2026-11-10)。ダイジェストに `source_id` を含めない前提は任意(K32)。エラー名 `finish_source_mismatch`、`finish_content_mismatch` は architecture K40 で確定。未知の `crawl_id` では結果を作らず、ログに `crawl_id` だけを残す(architecture K66。ユーザー承認 2026-11-11。0002 §3 #16) |
| `target_count`(T)は同一リフレッシュ後に取得した ID の件数(ID の取得時点の保証はしない)。現行方針(PIT なし)を採用し、競合試験で検証する。問題があれば PIT の利用を再検討する。PIT なしの取得が厳密なスナップショットを保証するとは扱わない | 確定 | architecture K47 |
| T > D なら削除を見送り `validation_failed`(`reason` は `target_exceeds_denominator`。名称は案)にするガード。強制削除モードでも適用する(2.2、第3章) | 確定 | architecture K69(ユーザー承認 2026-11-11。0002 §3 #10)。architecture U-33 を解消 |
| 待機中の削除結果を進める契機(終了通知の受理による起床通知と一定間隔の走査)。削除の並行度は全ソースを通して 1(第5章) | 確定 | architecture K68(ユーザー承認 2026-11-11。0002 §3 #2)。architecture U-14 のうち契機・順序・並行度を解消(設定スナップショットの項目名は U-1 に残る) |
| Indexer 再起動時の整理の対象(`finish_received_at` があって終端状態でない結果を `failed`(`indexer_restart`)にする。`finish_received_at` のない `running` には触れない)(第5章) | 確定 | architecture K68(ユーザー承認 2026-11-11。0002 §3 #3)。architecture U-20 を解消 |
| 不正な記録を一覧から除きログに残す(先行する結果とは扱わず、`running` のまま残す)。判定・実行の全体異常(文書ごとの削除エラーを除く)は、`status` を変えず `running` のまま走査ごとに再実行し、再実行は判定からやり直すが `deleted_count` は引き継ぐ。連続失敗で `failed` にはしない(第5章) | 確定 | architecture K62(ユーザー承認 2026-11-12。0021 §1) |
| 判定時に必須項目を欠く待機中の結果は、削除せず待ち行列の先頭を止める(後続の全ソースの削除が止まる。削除しない側に倒れる)(第5章) | 案 | 受容事項(architecture 9.13(11))。個別の承認の記録はない。実装で採用中。README の既知の制限。WARNING のログを監視する前提 |
| `deleted_count` は各バッチの前に条件付き更新で記録し、記録済みの件数は減らさない。再起動の整理で未記録なら 0 を記録する(第2.2章、第5章、第6章) | 確定 | architecture K62(ユーザー承認 2026-11-11 = 0002 §3 #18、2026-11-12 = 0021 §1)。K43 は Status API の表示(未記録の進捗を推測しない)、architecture D-93 は終端状態の事実の記録 |
| 開始通知と終了通知の受理は、同じソース単位の排他で直列化する(第6章) | 確定 | architecture K67(ユーザー承認 2026-11-11。0002 §3 #19) |

---

## v0.9 からの変更点

変更は、Indexer の実装(2026-11-11〜12)で決めた事項の反映である。削除の判断・実行の仕様(判定の順序、割合ルール、状態の意味)は変えていない。数値の既定値・上限値は設計書では未決のままで、`apps/indexer/README.md` を参照する(architecture K39)。確定にしたのは、ユーザーが承認したものだけで、根拠の承認日と作業記録の番号を本文の各所に書いた。

| v0.9 | v0.10 |
| --- | --- |
| T > D のガードは案(writer の導出。ユーザー未確認) | 確定(architecture K69)。強制削除モードでも適用する。`reason` は `target_exceeds_denominator`(名称は案) |
| 待ち行列の導出・先行する結果の定義は案、同時刻の順序(U-4)・待機中を進める契機・再起動の整理の対象(architecture U-20)は未決 | 確定(architecture K68)。順序は `finish_received_at`、同値なら `crawl_id` の辞書順。契機は起床通知と一定間隔の走査。並行度は全ソースで 1。再起動の整理の対象は `finish_received_at` があって終端状態でない結果 |
| 原本サイズ超過の拒否主体(U-5)は未決 | 確定(architecture K65)。Indexer も拒否し、すでにある同じ文書は書き換えない。エラーの記録先・ジョブの `status` への影響は未決のまま |
| `waiting_for` と Status API の 404 の条件は案・未決。拒否・開始通知のエラー名は案 | 確定(architecture K66)。削除結果がなければ 404 で、消えた・開始通知がない・喪失は区別しない。エラー名は api 3.4 の表のとおり |
| 受理の直列処理は案(`superseded` 化の条件付き更新でもよい) | 確定(architecture K67)。開始通知と終了通知の受理は同じソース単位の排他で直列化し、`superseded` 化も条件付き更新で行う |
| 不正な記録、判定・実行の全体異常、`deleted_count` の記録の規則は記載なし | 確定(architecture K62)。不正な記録は一覧から除きログに残す。判定・実行の全体異常(文書ごとの削除エラーを除く)は `status` を変えず `running` のまま走査ごとに再実行し(判定からやり直し、`deleted_count` は引き継ぐ)、連続失敗で `failed` にはしない。`deleted_count` は各バッチの前に条件付き更新で記録し、減らさない。再起動の整理で未記録なら 0 を記録する |
| 判定時に必須項目を欠く結果の扱いは記載なし | 待機中の結果が判定時に必須項目を欠くと、削除せず待ち行列の先頭を止める。確定ではなく受容事項(architecture 9.13(11)。個別の承認の記録はない。案。実装で採用中) |
| TTL の再確認は `last_seen_at + TTL < 現在時刻` だけ | 文書の `source_id` の一致も確認する(確定。architecture K61)。TTL の判定に、今回のクロールが見た文書を除くための追加の条件は設けない(確定。architecture K70) |
| `maintenance` の理由に、フラグの文書の値が不正なときの扱いの記載なし | フラグの文書があって `enabled` が真偽値の `false` と明示されていないときは、立っているとみなす(fail-closed。確定。architecture K63。ユーザー承認 2026-11-12。0014)。`maintenance` の説明に追記。フラグの形式は案 |
| `deletion_result` に `record_type`・`crawl_id`・`reason_detail`・`started_at`・`ended_at` の項目がない(開始・終了日時は項目名なし)。2種類の記録を同じインデックスに置く前提は記載なし | `record_type`、`crawl_id`、`reason_detail`、`started_at`、`ended_at` を追加し、2種類の記録を同じインデックスに置いて `record_type` で区別する(案。実装で採用中。項目の追加は 0020 §6-2(0021 で全て承認)) |
| 保持件数の整理の規則は記載なし(N 件保持、古いものは消す) | 終端状態への遷移の後に、新しい順(`ended_at`、`started_at`、`crawl_id` の降順)に N 件残す規則を追記(案。実装で採用中)。`running` と世代の記録は対象外。OpenSearch の一時的な異常で整理に失敗しても終端状態の書き込みは成功のまま残り、次の終端遷移で整理される(案。実装で採用中。0020 §6-2(0021 で全て承認)) |
| マッピングの前提は記載なし(全体は未決) | 実装が前提とするマッピング(`record_type`・`status`・`source_id` は keyword、並べ替えに使う項目、項目の有無での絞り込み)を第7章に追記(案。実装で採用中。マッピング全体は未決のまま。U-2) |
| `validation_failed` の理由コード名は未決 | `count_mismatch`、`id_limit_exceeded`、`target_exceeds_denominator`(案。実装で採用中)。`failed` の理由コードも案のまま実装で採用中。`delete_error` に、削除対象の件数が保持できる上限(仮値。値は未決)を超えた場合(`reason_detail` は `target_limit_exceeded`)を追記(案。実装で採用中) |
| 終了通知の `skip_and_oversize_id_count`・`skip_and_oversize_id_limit_exceeded` の記録の条件は、上限超過時のみ | `enumeration_completed` の受理では、上限以内でも件数とフラグ(偽)を記録する(案。実装で採用中。0020 §6-2(0021 で全て承認)) |

- 区分を変えなかったもの: `discarded` の最優先処理とソース削除の冪等性(architecture P29)、条件付き削除の競合の扱い(第6章)、ソース削除の停止確認、設定スナップショットの複写、`deletion-{source_id}` の用途、`e_missing` に `oversize_document_ids` を含めること(architecture P32)。実装済みでも、個別のユーザー承認がないため案のまま。ソース削除を優先する専用のソース単位の排他(ソース削除 1・2 が使う。3 は使わない)の採用だけは、architecture K61(0021 §2)で確定した。
- 承認の表記: 0021 §1・§2 が名指しした事項は、節番号まで書いて確定にした。名指しされていない実装の細目(記録の追加項目、保持件数の整理など)は、案(実装で採用中)のままとし、根拠は 0020 §6-2(0021 で全て承認)と書いた。0021 の「全て承認」は区分を確定に変えるものではない。
- 残す未決: U-1(設定スナップショットの項目名)、U-2(マッピング全体、保持件数超過分の削除方法、インデックス名)、U-3(保持件数 N の値)、U-7 のうち Crawler 領域、数値の既定値・上限値(architecture K39)。
- Crawler・infra の設計と突き合わせる事項(索引名、マッピングの前提、ロック文書・メンテナンスフラグの形式、理由コード名)は architecture U-34 に置く。実機での確認は architecture U-31。
- 参照している文書は、architecture・api・search-index の v0.10 に更新した。
