# `loreley-texts` Schema 設計書 v0.3

## 0. この文書について

- 対象: Store 層のインデックス `loreley-texts`(文書ごとの抽出済みテキストと処理状態)の Schema。
- 区分の表記: 確定 = ユーザー確定、案 = ユーザー未確定、未決 = 決めていない。各項目の区分は第8章の表に集約する。本書は Store 層のインデックス `loreley-texts` の Schema を単独で読めるようにまとめた文書である。
- 未決の ID: 本文書の `U-*` は**この文書だけで通用するローカル ID**。他文書の未決は『architecture U-16』のように文書名付きで書く。「architecture U-n と同じ論点」は、`indexer-architecture-v0.3.md` 17.3 の同じ判断事項を指す。
- 関連文書:
  - `indexer-architecture-v0.3.md` — 書き込み役の分担、Store 層の位置づけ、整合性、要約の整合、削除の判断・実行。
  - `indexer-api-v0.3.md` — Crawler から Indexer への登録の契約。
  - `search-index-v0.3.md` — 派生物である検索インデックス。
  - `loreley-deletions-v0.3.md` — 削除の記録。

## 1. 位置づけ

- MVP の Store 層は専用 DB を置かず、OpenSearch を KVS のように使う。用途ごとに検索インデックスとは別のインデックスを分け、ID をキーに get / put / delete する。
- `loreley-texts` は、文書ごとの抽出済みテキストと処理状態を持つ。
- 文書の本文・要約・処理状態の**正は `loreley-texts`**。検索インデックスはそこから作る派生物である。ただし `last_seen_at` は検索インデックスだけに持つ。
- 書き込みは Indexer だけが行う。
- 文書 ID(`_id`)は `document_id`(`SHA-256(source_id + "\0" + external_id)` の16進文字列、小文字。生成規則は `indexer-architecture-v0.3.md`)。検索インデックスと同じ ID を使う。
- 読み出しは ID による `_source` の取得(リアルタイム)で行う。検索(ニアリアルタイム)は使わない。
- `loreley-texts` を廃止するかどうかは未決(U-2。architecture U-21 と同じ論点)。廃止した場合の影響は 3.2 を参照。

## 2. 項目一覧

項目ごとの型・マッピングは第3章を参照(型は未決)。

| 項目 | 備考 |
| --- | --- |
| `document_id` | |
| `source_id` | |
| `external_id` | |
| `title` | |
| `url` / `path` | 項目数は未決(U-1。architecture U-16 の一部と同じ論点) |
| `mime_type` | |
| `text` | 抽出・正規化後のテキスト(サイズ上限で切り詰め後)。検索インデックスの `content` と同じ内容 |
| `truncated` | 本文をサイズ上限で切り詰めたか |
| `content_hash` | 確定済み。原本の SHA-256 |
| `pending_content_hash` | MVP でも使う |
| `source_updated_at` | MVP でも使う |
| `indexed_at` | |
| `size` | MVP でも使う。原本のサイズ(バイト) |
| `extractor_version` | 予約項目。MVP では使わない |
| `index_status` | 2.1 の値 |
| `extract_fail_count` | 予約項目。MVP では使わない |
| `pending_since` | `pending_index` になった日時。登録に成功して解消するまで更新しない |
| `summary` | |
| `summary_content_hash` | 要約の生成元の `content_hash` |
| `summary_status` | 2.1 の値 |
| `summary_model` | 要約の生成に使ったモデル名・バージョン |

- `extractor_version` と `extract_fail_count` は、差分検知(将来拡張)で使う予約項目。
- 取得・登録の失敗回数は、この文書ではなく `loreley-jobs` のスキップ記録(Crawler 領域)に持つ(新規の文書も含む)。
- **U-3 `fetched_at` / `metadata`**(architecture U-16 と同じ論点): Crawler から渡されるバッチ登録の文書(`indexer-api-v0.3.md` 4.3 の `documents[]`)にあるが、この項目一覧にも検索インデックスにもなく、保存先が決まっていない。保存するか、受け取るだけにするかはユーザー判断。

### 2.1 状態値

- `index_status`: `pending_index`(登録前。**Store 層のみ**)、`indexed`、`extract_failed`。
- `summary_status`: `disabled`(要約が無効)、`pending`、`generated`、`failed`。
- **`pending` の意味の拡張(案。architecture P30)**: `pending` は「要約が未生成」に加え、「要約を生成して保存済みだが、検索インデックスへの反映が済んでいない」状態も表す。`generated` になるのは検索インデックスへの反映に成功した後である。項目は追加しない。両者は、`summary` の有無と `summary_content_hash` で区別する(4.2)。

### 2.2 `content` の意味(場所ごとの対応)

| 場所 | 名前 | 意味 |
| --- | --- | --- |
| Crawler → Indexer | `raw_content` | 取得済みの原本(抽出前。MVP では原本そのものを渡す。保存しない) |
| Store 層(`loreley-texts`) | `text` | 抽出・正規化後のテキスト(サイズ上限で切り詰め後) |
| 検索インデックス | `content` | `text` と同じ内容を検索用に解析したもの |
| `get_document` の応答 | `content` | `text` の指定範囲 |

## 3. マッピング

### 3.1 方針

- `dynamic: strict` にして、未定義のフィールドの混入を防ぐ。
- 検索や集計の対象にしない大きな文字列(`text` など)は、解析も索引化もしない(`index: false`、またはオブジェクトの `enabled: false`)。取得は ID による `_source` の読み出しで行う。
- 条件で一覧する項目(`source_id`、`index_status`、`summary_status` など)は `keyword` にする。
- MVP は単一ノード前提で、`number_of_shards: 1`、`number_of_replicas: 0` とする。

これらは Store 層のインデックスに適用する方針である。`loreley-texts` のマッピング全体(項目ごとの型)は定義がなく、未決。

### 3.2 マッピングの提案(案)

3.1 の方針を JSON にした**提案(案)**。確定ではなく、機械可読にしただけで方針が決まったことを意味しない。項目ごとの型は定義がなく、項目の用途からの案(仮置き)。`url` / `path`(U-1)は含めない。

```json
{
  "settings": {
    "index": {
      "number_of_shards": 1,
      "number_of_replicas": 0
    }
  },
  "mappings": {
    "dynamic": "strict",
    "properties": {
      "document_id":          { "type": "keyword" },
      "source_id":            { "type": "keyword" },
      "external_id":          { "type": "keyword" },
      "title":                { "type": "text", "index": false },
      "mime_type":            { "type": "keyword" },
      "text":                 { "type": "text", "index": false },
      "truncated":            { "type": "boolean" },
      "content_hash":         { "type": "keyword" },
      "pending_content_hash": { "type": "keyword" },
      "source_updated_at":    { "type": "date" },
      "indexed_at":           { "type": "date" },
      "size":                 { "type": "long" },
      "extractor_version":    { "type": "keyword" },
      "index_status":         { "type": "keyword" },
      "extract_fail_count":   { "type": "integer" },
      "pending_since":        { "type": "date" },
      "summary":              { "type": "text", "index": false },
      "summary_content_hash": { "type": "keyword" },
      "summary_status":       { "type": "keyword" },
      "summary_model":        { "type": "keyword" }
    }
  }
}
```

**注意**: このままでは `url` / `path` を含む文書が `dynamic: strict` で拒否される(Indexer の書き込みが失敗する)。未決(U-1)の決定後に追加が必要。`acl` と `summary_embedding` は検索インデックス側の項目で、MVP で書き込まない予約項目のため、この Store 層のマッピングには含めていない。

## 4. 状態遷移と書き込み

全件更新でのこのインデックスの更新順(Indexer が文書ごとに行う)。文書単位の処理は、検索インデックスへの書き込みと同じ書き込み排他の中で行う(4.1。architecture P27)。

1. 取得した原本の `content_hash` が、`loreley-texts` の確定済みの `content_hash` と**同じ**場合、今回抽出した `text`(正規化・サイズ上限による切り詰め後)を、確定済みの `text` と比較する(案。U-4。architecture P26)。`index_status` も見る。`pending_index`(または `extract_failed`)の文書は、`content_hash` と `text` が同じでも、常に確定まで進める。(b)経路の全文 upsert が失敗すると、`loreley-texts` に新しい `text` と `pending_index` が残り、次回のクロールで `content_hash` と `text` が一致して見えるため、`index_status` を見ないと確定更新が行われず `pending_index` が永続してしまう。
   - **一致**(確定済みの `content_hash` と同じ、かつ `index_status` が `indexed`、かつ `text` も同じ): `loreley-texts` は書き換えず(`pending_index` に遷移せず、`text` も更新しない)、検索インデックスへの全文 upsert(`last_seen_at` の更新を含む。要約は引き継ぐ)だけを行う。
   - **不一致**(抽出ロジックの変更などで、原本は同じまま抽出結果が変わった場合、または `index_status` が `indexed` でない場合): 手順 2 以降(`pending_index` を経由する経路)で `text` を更新し、要約は無効化する(手順 4)。
   - 比較は `text` 同士の直接比較とする。`text_hash` のような項目は導入しない(`extractor_version` を使う段階で再検討する。architecture P26)。
2. **変わった(または新規の)場合のみ**、`text`・`pending_content_hash`・`index_status=pending_index` を書いてから、検索インデックスへ全文 upsert する。変更のない文書で `pending_since` や `index_status` が毎回変わるのを防ぐための、書き込み状態の判定である(差分検知ではない)。
3. 全文 upsert に成功したら、**最後に** `content_hash`・`index_status` などを確定し、`pending_index` を解消する。途中で失敗すると確定されないので、次回のクロールで再処理される。
4. 原本の `content_hash` が同じで、かつ `text` も同じ(手順 1 の一致。`index_status` が `indexed` であることを含む)なら要約を引き継ぐ。それ以外(`content_hash` が違う、または `content_hash` は同じでも `text` が不一致)は、要約を引き継がず、`summary` と `summary_content_hash` を消して `summary_status=pending` に戻す(要約が無効なら `disabled`)。この消去は、手順 2 の `pending_index` にする書き込みと同時に行う(案。`content_hash` が同じでも `text` が不一致のとき、`pending_content_hash` は確定済みの `content_hash` と同じ値になりうる。消去しないと、4.2 のハッシュの一致判定が古い要約を通してしまうため)。

- 新規文書の `text` は、登録前(`pending_index` にする時点)に `loreley-texts` へ書く(仮決定)。通常は、初回登録の失敗後も本文を返せる。読み出し側(`get_document`。仕様は対象外)は、確定済みの `text` がない場合に `index_status` を含み `content` なしの応答を返す(仮決定)。
- `extract_failed` の文書は、タイトルとメタデータだけが登録される。`extract_failed`・`pending_index` の文書は、次のクロールで再処理される(回数の上限はない)。
- 手順 3 の確定更新(`content_hash`・`index_status` などの条件付き更新)が 404(Store 層の文書が消えていた。削除の窓などによる)になった場合は、その文書の処理の失敗として扱い、リトライする(案。U-6)。リトライでは存在しない文書として、`create` から再実行する。
- 未決(U-5。architecture U-17 と同じ論点): `text` を書いた直後に失敗した場合の、`title` など他項目の書き込み順は未文書化。

### 4.1 削除時の順序

- 期限による削除では、`loreley-texts`、検索インデックスの順に削除する(各文書の削除直前に TTL を再確認する。判断・実行は `indexer-architecture-v0.3.md`)。TTL の再確認は、検索インデックスの文書を読み直した `last_seen_at` で行う。`loreley-texts` 側の削除条件は `if_seq_no` / `if_primary_term` である。
- **書き込み排他と条件付き削除(案。architecture P27)**: 削除の文書単位の処理(TTL の再確認から、`loreley-texts` の削除、検索インデックスの削除まで)を、登録・`last_seen_at` の部分更新と同じ書き込み排他に含める(単一 Indexer のプロセス内ロック。分散ロックではない)。`loreley-texts` の削除は `if_seq_no` / `if_primary_term` の条件付きにし、検索インデックスの削除には TTL の再確認(読み直した `last_seen_at`)と同じ条件を付ける。再確認の後に、登録などで文書が更新されていれば、条件が合わず削除は行われず、文書は残る。
- **条件が外れた場合の扱い(案)**: 要約の保存は書き込み排他の外で `loreley-texts` の `seq_no` を更新するため、排他があっても条件が外れうる。条件が外れた文書、および TTL の再確認で除外した文書は、`deleted_count` に数えない。削除結果は `deleted` のまま終了し(失敗にしない)、その文書は次の期限削除に委ねる。
- `loreley-texts` の削除の後に止まった場合は、`loreley-texts` だけが消えて検索インデックスに文書が残る。この文書は、次の全件更新で全文 upsert され、`loreley-texts` も復旧する(自己修復)。突合ジョブが先に走っても、検索インデックスにだけある文書は MVP では削除せず検出・表示だけを行う(案。architecture P28)ので、次の全件更新で復旧する。排他の外(突合の再登録など)で `loreley-texts` の文書が消えた場合の確定更新の 404 は、4 章のとおり文書単位の失敗としてリトライする(案)。
- この窓は、`loreley-texts` を廃止すると消える。廃止の可否は未決(U-2。architecture U-21 と同じ論点)。

### 4.2 条件付き更新と要約の保存

- 条件付き更新には `if_seq_no` / `if_primary_term` を使う。初回の作成は、存在しない場合だけ成功する作成(create)を使う。
- 要約を保存するときは、読み出した文書の現在の本文のハッシュ(確定前は `pending_content_hash`、確定後は `content_hash`)が生成元(`summary_content_hash`)と一致し、かつ `if_seq_no` / `if_primary_term` が一致するときだけ書く。
- 要約は、生成の完了後にまず `loreley-texts` へ要約テキストと `summary_content_hash` を保存し、そのうえで検索インデックスへ反映する(案。architecture P30)。この保存時、`summary_status` は `pending` のままにする。検索インデックスへの反映に成功した後に、`summary_status` を `generated` に確定する(`if_seq_no` / `if_primary_term` の条件付き更新)。
- 反映前に止まった文書は、再走査で次のように扱う(案。architecture P30)。
  - `summary_status=pending` で、`summary_content_hash` が現在の本文のハッシュと一致する: 要約を再生成せず、検索インデックスへの反映だけを行い、成功したら `generated` にする。
  - `summary_status=pending` で、`summary` がない、または `summary_content_hash` が不一致: 要約を再生成する。
- 本文が変わるとき(`content_hash` が既存と違うとき、または `content_hash` が同じでも `text` が不一致のとき。4章手順 1・4)は、`loreley-texts` の要約を消して `summary_status` を `pending`(要約が無効なら `disabled`)に戻す。
- `loreley-texts` と検索インデックスは別のインデックスで、またがるトランザクションはない。更新の途中では両者(`content_hash`、`index_status`)が一時的に食い違う。MVP では短時間の不一致を許容する(検出と復旧は突合ジョブ。`indexer-architecture-v0.3.md`)。

### 4.3 `pending_since` の扱い

`pending_since` は**削除条件にしない**(案)。期限を過ぎたことだけを理由に消すと、一時的な障害で登録できなかっただけの実在文書を誤って消すため。`pending_since` は異常検知(Admin View の警告)にだけ使う。警告までの期間は未決。Store 層だけにある文書は、MVP では自動削除しない(将来の方式は未決)。

## 5. バックアップ

- OpenSearch のスナップショットに、Store 層のインデックス(`loreley-texts` を含むすべて)を含める。ノードが 1 つなので、データの消失に備えてスナップショットを取る。
- `loreley-texts` は検索インデックスの再構築元になる(`search-index-v0.3.md` 第6章)。
- バックアップ・リストア手順の中身(保存先、周期、復元手順)は未決(手順は README に記載する予定とだけ決まっている。architecture U-13 と同じ論点)。

## 6. テスト観点

`get_document` 関連のケースは読み出し側の仕様で、この文書の対象外(`text` の存在、`truncated`、`index_status` に依存することのみ)。このインデックス固有のテスト観点は、`indexer-architecture-v0.3.md` のテスト観点に集約している。

## 7. 未決事項(ユーザー判断。案を含む)

ID は文書ローカル。

| ID | 内容 | 選択肢 |
| --- | --- | --- |
| U-1 | `url` / `path` の項目数(architecture U-16 の一部と同じ論点) | (1) どちらか一方が入る1項目 (2) 2項目 |
| U-2 | `loreley-texts` の廃止(architecture U-21 と同じ論点)。廃止すると 4.1 の窓が消える | (1) 残す (2) 廃止する(廃止時の再構築元・本文の正の置き場は別途設計が必要) |
| U-3 | `fetched_at` / `metadata` の保存先(architecture U-16 と同じ論点) | (1) 保存しない(受け取るだけ) (2) 項目を追加して保存 |
| U-4 | 確定済みと同じ `content_hash` のときの `text` の扱い。**解消(案。architecture P26)**: 原本ハッシュ一致かつ `text` 一致なら Store 層を更新しない。`text` 不一致なら `pending_index` 経路で更新し、要約を無効化する。`text_hash` は導入しない | (1) 案どおり(解消扱い) (2) 常に更新しない、または常に `pending_index` 経由など。ユーザー確認待ち |
| U-5 | `text` 書き込み直後に失敗した場合の他項目の書き込み順(architecture U-17 と同じ論点) | 未整理 |
| U-6 | 確定更新が 404(Store 層の文書が消えていた)のときの扱い(architecture P27 に関連) | (1) 文書単位の失敗としてリトライ(案) (2) その場で `create` し直す。ほか、ユーザー判断 |
| U-7 | `summary_status` の `pending` の意味の拡張と要約の反映規則(architecture P30) | (1) 案どおり(項目追加なし) (2) 未反映を表す項目を追加。ほか、ユーザー判断 |

## 8. 確認状況

| 項目 | 区分 | 備考 |
| --- | --- | --- |
| `loreley-texts` に書くのは Indexer だけ。正は `loreley-texts` | 確定 | 書き込み役の分担 |
| `pending_since` は削除条件にしない(異常検知のみ) | 案 | レビュー反映で加えた点で、ユーザー未確認 |
| `text` を `pending_index` にする時点で書く / 確定済み `text` がないとき `content` なしで応答 | 案 | 仮決定 |
| 確定済みと同じ `content_hash` のときの `text` の扱い(U-4。解消(案)): `text` 一致なら Store 層を更新しない、不一致なら `pending_index` 経路で要約を無効化。`text_hash` は導入しない | 案 | architecture P26。ユーザー未確認 |
| 削除の文書単位の処理を書き込み排他に含める、Store 層の削除を `if_seq_no` 条件付きにする(4.1) | 案 | architecture P27。ユーザー未確認 |
| 確定更新の 404 は文書単位の失敗としてリトライ(U-6) | 案 | architecture P27 に関連 |
| 要約の反映規則(`pending` の意味の拡張、`summary_content_hash` を先に保存、再走査で反映のみ/再生成。U-7) | 案 | architecture P30。ユーザー未確認 |
| 3.1 のマッピング方針(`dynamic: strict`、`index: false`、keyword 化、shard/replica) | 案(確定の明記なし) | Store 層のインデックスに適用する方針として書いているが、ユーザー確定とは明記されていない |
| 3.2 のマッピング JSON | 案(提案) | 各項目の型は仮置き(定義なし)。`url` / `path` を含まないため、`dynamic: strict` 下では追加が必要 |
| `extractor_version`・`extract_fail_count` は予約項目 | 前提 | MVP では使わない |
| `loreley-texts` のマッピング全体(項目ごとの型) | 未決 | |
| U-1 `url` / `path` の項目数 | 未決(ユーザー判断) | |
| U-2 `loreley-texts` の廃止 | 未決(ユーザー判断) | 廃止すると削除時の窓が消える |
| U-3 `fetched_at` / `metadata` の保存先 | 未決(ユーザー判断) | |
| U-5 `text` 書き込み直後の失敗時の書き込み順 | 未決 | |
| U-6 確定更新の 404 の扱い | 案(ユーザー判断) | |
| U-7 `pending` の意味の拡張 | 案(ユーザー判断) | architecture P30 |
| `pending_index` 警告までの期間 | 未決 | |
| Store 層だけにある文書を期限で削除する方式 | 未決 | |
| Store 層 Repository インターフェースの詳細、他バックエンドに移る条件 | 未決 | |
| バックアップ・リストア手順の中身 | 未決 | |
