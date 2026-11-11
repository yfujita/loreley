# `loreley-texts` Schema 設計書 v0.1

## 0. この文書について

- 対象: Store 層のインデックス `loreley-texts`(文書ごとの抽出済みテキストと処理状態)の Schema。
- 版: v0.1。`docs/v0.x/system-design/system-design-v0.8.md`(以下 SD v0.8)から該当部分を抽出したもの。仕様・数値は変えていない。SD 内の「案」「推測」「未決」は残している。
- 食い違い・要確認の点は解消せず、「要確認」として明記した(解消は v0.2 で行う)。
- 関連文書(同じ v0.1 の抽出版):
  - `docs/v0.x/system-design/indexer/indexer-architecture-v0.1.md` — 書き込み役の分担、Store 層の位置づけ、整合性、要約の整合。
  - `docs/v0.x/system-design/indexer/indexer-api-v0.1.md` — Crawler から Indexer への登録の契約。
  - `docs/v0.x/system-design/opensearch/schema/search-index-v0.1.md` — 派生物である検索インデックス。
  - `docs/v0.x/system-design/opensearch/schema/loreley-deletions-v0.1.md` — 削除の判断・実行の記録。

## 1. 位置づけ

- MVP の Store 層は専用 DB を置かず、OpenSearch を KVS のように使う。用途ごとに検索インデックスとは別のインデックスを分け、ID をキーに get / put / delete する。
- `loreley-texts` は、文書ごとの抽出済みテキストと処理状態を持つ。
- 文書の本文・要約・処理状態の**正は `loreley-texts`**。検索インデックスはそこから作る派生物である。ただし `last_seen_at` は検索インデックスだけに持つ。
- 書き込みは Indexer だけが行う。
- 文書 ID(`_id`)は `document_id`(`SHA-256(source_id + "\0" + external_id)` の16進文字列、小文字。生成規則は `indexer-architecture-v0.1.md` を参照)。検索インデックスと同じ ID を使う。
- 読み出しは ID による `_source` の取得(リアルタイム)で行う。検索(ニアリアルタイム)は使わない。

要確認(X2): SD v0.8 は、`loreley-texts` の廃止は未決で、本書(SD)v0.5 でも扱っていないと記す。一方、削除の「順序と窓」の記述(下記 3.2)は「`loreley-texts` を廃止すると窓が消える」と書く。v0.1 では SD どおり写し、廃止の可否は未決(下記の確認状況)とする。

## 2. 項目一覧

SD v0.8 が定める項目(型・マッピングは SD に定義なし。第3章参照)。

| 項目 | 備考 |
| --- | --- |
| `document_id` | |
| `source_id` | |
| `external_id` | |
| `title` | |
| `url` / `path` | 要確認(X8): 1項目か2項目か未決。SD は「`url`/`path`」と書く |
| `mime_type` | |
| `text` | 抽出・正規化後のテキスト(サイズ上限で切り詰め後)。検索インデックスの `content` と同じ内容 |
| `truncated` | 本文をサイズ上限で切り詰めたか |
| `content_hash` | 確定済み。原本の SHA-256 |
| `pending_content_hash` | MVP でも使う |
| `source_updated_at` | MVP でも使う |
| `indexed_at` | |
| `size` | MVP でも使う。原本のサイズ(バイト) |
| `extractor_version` | ※予約項目。MVP では使わない |
| `index_status` | 下記の値 |
| `extract_fail_count` | ※予約項目。MVP では使わない |
| `pending_since` | `pending_index` になった日時。登録に成功して解消するまで更新しない |
| `summary` | |
| `summary_content_hash` | 要約の生成元の `content_hash` |
| `summary_status` | 下記の値 |
| `summary_model` | |

※ `extractor_version` と `extract_fail_count` は、差分検知(将来拡張)で使う予約項目。新しい項目ではなく、プロダクト設計書の旧版から残している。SD 旧版にあった `fetch_fail_count`(恒久失敗の判定用)は削除済みで、取得・登録の失敗回数は `loreley-jobs` のスキップ記録(Crawler 領域)に持つ(新規の文書も含む)。

要確認(X7): 共通ドキュメント形式(Crawler から渡される形式)にある `fetched_at` と `metadata` は、この項目一覧にも検索インデックスにもない。保存先は SD に書かれておらず、保存するか受け取るだけにするかは未決(ユーザー判断)。

### 2.1 状態値

- `index_status`: `pending_index`(登録前。**Store 層のみ**)、`indexed`、`extract_failed`。
- `summary_status`: `disabled`(要約が無効)、`pending`、`generated`、`failed`。`summary_model` にモデル名・バージョンを持つ。

### 2.2 `content` の意味(場所ごとの対応)

| 場所 | 名前 | 意味 |
| --- | --- | --- |
| Crawler → Indexer | `raw_content` | 取得済みの原本(抽出前。MVP では原本そのものを渡す。保存しない) |
| Store 層(`loreley-texts`) | `text` | 抽出・正規化後のテキスト(サイズ上限で切り詰め後) |
| 検索インデックス | `content` | `text` と同じ内容を検索用に解析したもの |
| `get_document` の応答 | `content` | `text` の指定範囲 |

## 3. マッピング方針

(SD v0.8 §1.4。Store 層のインデックスに適用する方針)

- `dynamic: strict` にして、未定義のフィールドの混入を防ぐ。
- 検索や集計の対象にしない大きな文字列(`text` など)は、解析も索引化もしない(`index: false`、またはオブジェクトの `enabled: false`)。取得は ID による `_source` の読み出しで行う。
- 条件で一覧する項目(`source_id`、`index_status`、`summary_status` など)は `keyword` にする。
- MVP は単一ノード前提で、`number_of_shards: 1`、`number_of_replicas: 0` とする。

`loreley-texts` のマッピング全体(項目ごとの型)は SD に定義がなく、未決。上記の方針が `loreley-texts` に適用される。「Store 層の全インデックスに適用する」書き方だが、SD 内でプロダクト設計書が明記するのは Store 層である(`loreley-deletions` への適用は未決。`loreley-deletions-v0.1.md` 参照)。

### 3.1 状態遷移と書き込み

(SD v0.8 §3.2、§3.8 由来。全件更新でのこの文書の更新順。Indexer が文書ごとに行う)

1. 取得した `content_hash` が、`loreley-texts` の確定済みの `content_hash` と**同じ**なら、`pending_index` に遷移せず、検索インデックスへの全文 upsert(`last_seen_at` の更新を含む。要約は引き継ぐ)だけを行う。あわせて、`text` も抽出し直した内容で更新する(抽出ロジックを変えた場合に備える)。
   - **要確認(G-3)**: この `text` の更新は `pending_index` を経由しない。SD v0.8 は、これがプロダクト設計書の作成時に指示外で補われた点で、`loreley-texts` と検索インデックスの本文が食い違う余地があり、要否をユーザーに確認する、と記す。
2. **変わった(または新規の)場合のみ**、`text`・`pending_content_hash`・`index_status=pending_index` を書いてから、検索インデックスへ全文 upsert する。変更のない文書で `pending_since` や `index_status` が毎回変わるのを防ぐための、書き込み状態の判定である(差分検知ではない)。
3. 全文 upsert に成功したら、**最後に** `content_hash`・`index_status` などを確定し、`pending_index` を解消する。途中で失敗すると確定されないので、次回のクロールで再処理される。
4. 本文が前回と同じ(`content_hash` が同じ)なら要約を引き継ぐ。違うなら要約を引き継がず、`summary_status=pending` に戻す(要約が無効なら `disabled`)。

- 新規文書の `text` は、登録前(`pending_index` にする時点)に `loreley-texts` へ書く(仮決定)。通常は、初回登録の失敗後も本文を返せる。読み出し側(`get_document`。仕様は対象外)は、確定済みの `text` がない場合に `index_status` を含み `content` なしの応答を返す(仮決定)。
- `extract_failed` の文書は、タイトルとメタデータだけが登録される。`extract_failed`・`pending_index` の文書は、次のクロールで再処理される(回数の上限はない)。
- 未決(N-18): `text` を書いた直後に失敗した場合の、`title` など他項目の書き込み順は未文書化。

### 3.2 削除時の順序

- 期限による削除では、`loreley-texts`、検索インデックスの順に削除する(各文書の削除直前に TTL を再確認する。判断・実行は `indexer-architecture-v0.1.md`)。
- 再確認から `loreley-texts` の削除までの極小の窓で `last_seen_at` が更新された場合や、`loreley-texts` の削除の後に止まった場合は、`loreley-texts` だけが消えて検索インデックスに文書が残る。この文書は、次の全件更新で全文 upsert され、`loreley-texts` も復旧する(自己修復)。突合ジョブが先に走ると、検索インデックスの文書は削除され、次の全件更新で再登録される。
- この窓は、`loreley-texts` を廃止すると消える(SD v0.8 の記述。廃止の可否は未決。上記 X2)。

### 3.3 条件付き更新と要約の保存

- 条件付き更新には `if_seq_no` / `if_primary_term` を使う。初回の作成は、存在しない場合だけ成功する作成(create)を使う。
- 要約を保存するときは、読み出した文書の現在の本文のハッシュ(確定前は `pending_content_hash`、確定後は `content_hash`)が生成元(`summary_content_hash`)と一致し、かつ `if_seq_no` / `if_primary_term` が一致するときだけ書く。
- 要約は、生成の完了後にまず `loreley-texts` へ保存し、そのうえで検索インデックスへ反映する。
- 本文が変わるとき(`content_hash` が既存と違うとき)は、`loreley-texts` の要約を消して `summary_status` を `pending`(要約が無効なら `disabled`)に戻す。
- `loreley-texts` と検索インデックスは別のインデックスで、またがるトランザクションはない。更新の途中では両者(`content_hash`、`index_status`)が一時的に食い違う。MVP では短時間の不一致を許容する(検出と復旧は突合ジョブ。`indexer-architecture-v0.1.md`)。

### 3.4 `pending_since` の扱い

`pending_since` は**削除条件にしない**。期限を過ぎたことだけを理由に消すと、一時的な障害で登録できなかっただけの実在文書を誤って消すため。`pending_since` は異常検知(Admin View の警告)にだけ使う。警告までの期間は未決。Store 層だけにある文書は、MVP では自動削除しない(将来の方式は未決)。

## 4. バックアップ

- OpenSearch のスナップショットに、Store 層のインデックス(`loreley-texts` を含むすべて)を含める。ノードが 1 つなので、データの消失に備えてスナップショットを取る。
- `loreley-texts` は検索インデックスの再構築元になる(検索インデックスを失った場合の再構築は `search-index-v0.1.md` 第6章)。
- バックアップ・リストア手順の中身(保存先、周期、復元手順)は未決(SD は「README に記載」とだけ書く。SD 側で「導出」と注記されている)。

## 5. テスト観点(SD v0.8 由来。観点のみ)

SD 側の導出に基づく粒度。`get_document` 関連のケース(E-16、E-17。SD の ID)は読み出し側の仕様で、この文書の対象外(`text` の存在、`truncated`、`index_status` に依存することのみ記録した)。

## 6. 確認状況

区分: 確定 = ユーザー確定、案 = ユーザー未確定、未決 = 決めていない、推測 = SD が推測と注記。

| 項目 | 区分 | 備考 |
| --- | --- | --- |
| `loreley-texts` に書くのは Indexer だけ。正は `loreley-texts` | 確定(書き込み役の分担) | |
| `pending_since` は削除条件にしない(異常検知のみ) | 案(SD の「レビュー反映(要確認)」) | |
| `text` を `pending_index` にする時点で書く / 確定済み `text` がないとき `content` なしで応答 | 案(仮決定) | |
| 確定済みと同じ `content_hash` のときの `text` の更新(`pending_index` を経由しない) | 案(要否未確認。G-3) | |
| `extractor_version`・`extract_fail_count` は予約項目 | 前提(MVP では使わない) | |
| `loreley-texts` のマッピング全体(項目ごとの型) | 未決 | |
| `loreley-texts` の廃止(X2) | 未決 | 廃止すると、削除時の窓が消える |
| `url` / `path` の項目数(X8) | 未決 | |
| `fetched_at` / `metadata` の保存先(X7) | 未決 | ユーザー判断 |
| `text` 書き込み直後に失敗した場合の他項目の書き込み順(N-18) | 未決 | |
| `pending_index` 警告までの期間 | 未決 | |
| Store 層だけにある文書を期限で削除する方式 | 未決 | |
| Store 層 Repository インターフェースの詳細、他バックエンドに移る条件 | 未決 | |
| バックアップ・リストア手順の中身 | 未決 | |
| SD 全体の整合確認 | 未完了 | SD 自身が「全文の通読による整合確認は完了していない」と記す |
