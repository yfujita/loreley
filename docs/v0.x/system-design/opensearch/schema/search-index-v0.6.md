# 検索インデックス Schema 設計書 v0.6

## 0. この文書について

- 対象: 1文書 = 1検索レコードで全文検索に使う OpenSearch インデックス(以下「検索インデックス」)の Schema。文書の本文・メタデータ・要約・処理状態・`last_seen_at` の唯一の正本でもある。
- 区分の表記: 確定 = ユーザー確定、案 = ユーザー未確定、未決 = 決めていない、推測 = 根拠が弱い想定。第4章では、これに加えて方針・仮置き・プレースホルダを区分として使う(同章で定義)。「案(推奨。ユーザー承認待ち)」は推奨(承認待ち)の記述で、確定ではない。各項目の区分は第10章の表に集約する。本書は検索インデックスの Schema を単独で読めるようにまとめた文書である。
- 未決の ID: 本文書の `U-*` は**この文書だけで通用するローカル ID**。他文書の未決は『architecture U-16』のように文書名付きで書く。「architecture U-n と同じ論点」は、`indexer-architecture-v0.6.md` 17.3 の同じ判断事項を指す。欠番は第9章に示す。
- 関連文書:
  - `indexer-architecture-v0.6.md` — 書き込み種別と競合制御、再インデックス前の停止手順、要約の書き戻し、削除の判断・実行、復旧。
  - `indexer-api-v0.6.md` — Crawler から Indexer への登録・部分更新の契約。
  - `loreley-deletions-v0.6.md` — 削除の記録。
- 検索クエリ自体(Search API、MCP)は対象外。

## 1. 位置づけ

- 1文書 = 1検索レコードを基本とし、タイトル・要約・本文を BM25 で検索する。日本語を主な対象とし、英語も併せて解析する。
- チャンク分割・ベクトル検索は、評価結果を見て判断する(プロダクト側の判断)。
- 検索インデックスへの書き込みは Indexer だけが行う。
- 検索インデックスは、文書の本文(`content`)・メタデータ・要約・処理状態・`last_seen_at` の**唯一の正本**である。別に持つ写しはなく、すべての項目が正本である。
- **`_source` に `content` を含めて保持することが必須**である(マッピングで `_source` から除外しない)。`_reindex`(第6章)、書き込み前の読み直し、`get_document`(Search API が ID で取得して範囲を切り出す)が、`_source` の `content` を前提にしている。

## 2. フィールド

`_id` は `document_id`(SHA-256 の16進文字列、小文字。`SHA-256(source_id + "\0" + external_id)`。生成規則は `indexer-architecture-v0.6.md`)。

| フィールド | 用途 |
| --- | --- |
| `document_id` | 一意な識別 |
| `source_id` | データソースによる絞り込み |
| `external_id` | データソース内の識別子(削除対象の特定に使う) |
| `title` | タイトル検索 |
| `summary` | 文書全体の主題による検索 |
| `content` | 本文の正本(抽出・正規化後の本文。サイズ上限で切り詰めた後)。細かい語句・識別子による全文検索に使い、あわせて `_source` に原文のまま保持する。`extract_failed` の文書は持たない |
| `url`(案。U-1) | アクセス可能な原文の URL(表示のみ。任意) |
| `path`(案。U-1) | データソース内の文書パス(表示用。任意。`url` とは独立した項目)。検索・絞り込みに使うかと最大長は未決(U-8) |
| `mime_type` | 文書形式による絞り込み |
| `size` | 原本のサイズ(バイト)。メタデータの一つで、変更の有無の判定(architecture 4.3)に使う。差分検知を導入するときのスキップ判定にも使う(architecture 13.1) |
| `source_updated_at` | 更新日による絞り込み |
| `indexed_at` | インデックスに登録した日時 |
| `content_hash` | 原本の SHA-256。変更の有無の判定と、要約の書き戻しの条件に使う |
| `text_hash`(案。U-6) | 抽出後の本文(`content`)の SHA-256(UTF-8 バイト列。16進小文字)。変更の有無の判定と、要約の生成元の識別に使う(要約の書き戻しは、生成元の `content_hash` と `text_hash` が現在値と一致するときだけ行う)。全文書き込みで `content` と同時に書く。`extract_failed` の文書は持たない(案) |
| `summary_status` / `summary_model` | 要約の生成状態と、生成に使ったモデル・バージョン |
| `index_status` / `truncated` | 処理状態と、本文を切り詰めたかどうか |
| `last_seen_at` | 列挙クロールで最後に見つかった日時(期限による削除の判定) |
| `acl` | アクセス制御用の属性。MVP では使わない予約項目 |
| `summary_embedding` | 意味検索用のベクトル(任意)。位置づけは未決(U-2) |
| `extractor_version` / `extract_fail_count`(予約) | 差分検知を導入するときに使う項目(architecture 13.1)。MVP では書かず、マッピングにも入れない。導入するときにマッピングへ追加し、`_reindex` で反映する |

未決の点:

- **U-1 `url` / `path`**(architecture U-16 の一部と同じ論点): 「どちらか一方が入る1項目」か「2項目」かは未決。**2項目を案(推奨。ユーザー承認待ち)**とする。`url` はアクセス可能な原文の URL、`path` はデータソース内の文書パスで、どちらも独立した任意項目。`external_id` は ID の責務で、別。決定は2.4の対応表に反映する。
- **U-8 `path` の使い方と最大長**: `path` を検索・絞り込みに使うかと、`url` / `path` の最大長は未決。使う場合は、マッピングの `index` の指定と型(完全一致の `keyword` か、検索用の `text` か)を見直す。
- **U-2 `summary_embedding`**(architecture U-25 と同じ論点): 任意項目として挙がっているが、Embedding 生成は MVP で行わない。`acl` と違い予約とは明記されていない。MVP で未使用の予約項目として置くかは、ユーザー判断。
- **U-3 `fetched_at` / `metadata`**(architecture U-16 と同じ論点): Crawler から渡されるバッチ登録の文書(`indexer-api-v0.6.md` 4.3 の `documents[]`)にあるが、この表になく、保存先が決まっていない。検索インデックスに持つか、受け取るだけで持たないかはユーザー判断。持つ場合は、マッピングに項目を追加する(第4章)。

### 2.1 `last_seen_at` の意味

- バッチ登録の文書(`documents[]`)には含めない。クロールの実行コンテキストとして `crawl_started_at`(クロールの開始時刻)が Indexer に渡され、Indexer が `last_seen_at` に書く(渡し方は `indexer-api-v0.6.md`)。
- 渡された `crawl_started_at` は、Indexer が `deletion_result-{crawl_id}` に複写した `crawl_started_at` と照合し、不一致なら拒否する(案。architecture P36。詳細は `loreley-deletions-v0.6.md` 4章)。
- `fetched_at`(原本を取得した日時)とは別物で、`last_seen_at` は「列挙で見つかった日時」である。
- 全文書き込みで更新されるほか、取得に失敗してスキップした文書の誤削除を防ぐため、列挙で見つかった時点で `last_seen_at` だけを部分更新する(MVP は全件処理で、差分検知は将来拡張)。変更のない文書は全文書き込みをしないので、`last_seen_at` が古ければ部分更新で補う(architecture 4.3)。ただし、`last_seen_at` の部分更新の要請(`indexer-api-v0.6.md` 4.2)がすでに成功していれば補う必要はなく、補うのは 4.2 の要請が失敗・省略された場合に限る。
- 日時項目(`last_seen_at`、`source_updated_at`、`indexed_at` など)は、UTC・ISO 8601・ミリ秒精度(例 `2026-11-09T01:00:00.000Z`)に正規化して書く(案)。`date` 型での比較と、max 比較のスクリプト(文字列ではなく Instant にパースして比較する)が、入力の秒精度やタイムゾーンの違いに左右されないようにするため。確認は architecture U-31 に加える。
- 期限による削除の判定(`last_seen_at + TTL < 現在時刻`)と、削除前の件数照合(`last_seen_at >= crawl_started_at` の件数)に使う。詳細は `indexer-architecture-v0.6.md`。
- 消えた文書は、削除されるまで検索結果に残る。検索時に `last_seen_at` で除外はしない。

### 2.2 正本と読み出し

- すべての項目の正本は検索インデックスの文書にある。表示・絞り込み・書き込み前の判定は、この文書の値を使う。
- 本文は `_source.content` から読む。`get_document`(Search API 側)は、文書を ID で取得して `content` から指定範囲を切り出す。検索インデックスに専用のエンドポイントや別項目は追加しない。
- 1文書の全項目は1回の PUT で原子的に書かれるため、本文だけが新しく処理状態が古い、といった途中の状態は存在しない(architecture 5章、6章)。

### 2.3 状態値

- `summary_status`: `disabled`(要約が無効)、`pending`、`generated`、`failed`。
- `index_status`: `indexed`、`extract_failed`。`extract_failed` は、抽出に失敗してタイトルとメタデータだけを登録した文書で、`content`・`text_hash`・要約を持たない。この文書の `summary_status` は、要約の対象にならないので `disabled`(要約が無効のときと同じ値)とし、`pending` にしない(要約の再走査の対象から外す。architecture に合わせる。案)。
- `indexed` から `extract_failed` へ遷移するとき(抽出ロジックの変更、原本の破損など)に、旧 `content`・要約を残すか消すかは未決(architecture U-32 と同じ論点)。
- `summary_status` の遷移: 全文書き込みで本文が変わったときは `pending`(要約が無効なら `disabled`)。要約の書き戻し(PUT)の成功時に `generated`。本文が同じでメタデータだけが変わる全文書き込みは、読んだ要約と状態を引き継ぐ。

### 2.4 フィールド対応表

検索インデックスの各フィールドについて、Crawler から渡される値と、書き込み種別(第3章)を対応づける。書き込み主体はすべて Indexer。

| 検索インデックス | Crawler の入力(`documents[]` ほか) | 書き込み種別 |
| --- | --- | --- |
| `document_id`(`_id`) | `source_id` と `external_id` から Indexer が算出 | 全文書き込み |
| `source_id` | パスの `source_id` | 全文書き込み |
| `external_id` | `external_id` | 全文書き込み |
| `title` | `title` | 全文書き込み |
| `url`(案) | `url`(任意) | 全文書き込み |
| `path`(案) | `path`(任意) | 全文書き込み |
| `mime_type` | `mime_type` | 全文書き込み |
| `size` | `documents[].size`(原本のサイズ。Crawler が渡す。`indexer-api-v0.6.md` 4.3) | 全文書き込み |
| `source_updated_at` | `source_updated_at` | 全文書き込み |
| `content` | `raw_content` を抽出・正規化した結果(Indexer。サイズ上限で切り詰め) | 全文書き込み |
| `text_hash`(案) | Indexer が `content` から算出 | 全文書き込み |
| `truncated` | Indexer が算出(サイズ上限での切り詰め) | 全文書き込み |
| `content_hash` | `content_hash` | 全文書き込み |
| `indexed_at` | Indexer が登録時に付与 | 全文書き込み |
| `index_status` | Indexer が判定(`indexed` / `extract_failed`) | 全文書き込み |
| `summary` | なし(Indexer が生成) | 全文書き込み(要約の書き戻し。本文が変わるときは書かない) |
| `summary_status` | なし | 全文書き込み(`pending` / `disabled` / 引き継ぎ。要約の書き戻しで `generated`) |
| `summary_model` | なし | 全文書き込み(要約の書き戻しで書く。それ以外は引き継ぎ) |
| `last_seen_at` | 実行コンテキストの `crawl_started_at` | 全文書き込み(max)、`last_seen_at` の部分更新 |
| `fetched_at` / `metadata` | `fetched_at` / `metadata`(任意) | 未決(U-3) |
| `acl` | なし | MVP では書かない(予約) |
| `summary_embedding` | なし | 未決(U-2) |
| `extractor_version` / `extract_fail_count` | なし | MVP では書かない(予約) |

## 3. 書き込み種別とフィールド

検索インデックスへの書き込みは、PUT(Index API)を基本として、Indexer が次の2種類で行う(`indexer-architecture-v0.6.md` 5章と同じ。競合時の扱いもそちら)。

| 種別 | 書くフィールド | 備考 |
| --- | --- | --- |
| 全文書き込み(PUT) | 全フィールド(文書全体を置き換える)。`last_seen_at` は、読んだ値と `crawl_started_at` の大きい方(新規作成時は `crawl_started_at`)。`content`・`content_hash`・`text_hash` は新しい値。`summary`・`summary_status`・`summary_model` は、`content_hash` と `text_hash` がともに既存と同じなら読んだ値を引き継ぎ、どちらかが違えば `summary` は書かず `summary_status=pending`(要約が無効なら `disabled`) | 既存の文書は、ID で取得(GET) → 組み立て → `if_seq_no`/`if_primary_term` 付きの index。新規は `op_type=create`。409 は読み直して再判定する。MVP は全件処理で、変更のある文書だけを書く |
| `last_seen_at` の部分更新(Update) | `last_seen_at` のみ(値は `crawl_started_at`) | max 比較。現在値以上なら書かない(noop)。検索インデックスに文書がなければ(404)何もしない(upsert しない) |

**要約の書き戻し(PUT)**: 非同期で生成した要約は、文書を ID で取得し、現在の `content_hash` と `text_hash` が、要約の生成元の値とともに一致するときだけ、`summary`・`summary_status`(`generated`)・`summary_model` を載せた全体を `if_seq_no`/`if_primary_term` 付きで PUT する。一致しない、または文書がなければ破棄する。409 は読み直して再判定する。生成元の `content_hash`・`text_hash` は、生成する非同期処理が自分のコンテキストとして保持し、文書には持たない(生成元のハッシュ用の項目は設けない)。要約専用の部分更新は持たない。`summary_embedding` を書く場合も同じ PUT に含める(U-2 の決定後)。

**`text_hash` を条件に加える理由(案。architecture P35)**: 原本が同じで抽出結果の `content` だけが変わる場合、`content_hash` は変わらない。要約の生成中にこの変更が起きると、`content_hash` だけの条件では旧い本文向けの要約を通してしまう。`text_hash` を生成元と照合すれば、書き戻しの時点で本文が変わっていたことを検出できる。

**本文が変わらない文書の要約**は更新しない。要約ロジックやモデルを変えたときなど再生成が必要なときは、変更の有無の判定をしない再書き込みモード(案。architecture P39)でクロールし、本文ごと全文書き込みする。このとき要約は引き継がず `pending` に戻る。

保証の範囲: リース切れ後の旧 Crawler による全文書き込みは、`if_seq_no` では世代として拒否できず(読んだあとの更新を検出するだけ)、保証するのは `last_seen_at` が古い値に戻らないことまでである(全文書き込みも部分更新も max 比較)。完全な分散フェンシングは複数 Crawler 化の際の将来拡張。

## 4. Mapping・Analyzer・Shard/Replica

検索インデックスのマッピング全体は未決(architecture U-7 と同じ論点)。実装時に確定する。以下は要素ごとに、確かさを区分して並べる。区分の意味: 確定 = K18 など、ユーザー確定の内容、方針 = 本書として置いている内容(推測を含む。ユーザー未確認。第10章)、未決 = 決めていない、推測 = 根拠が弱い想定、仮置き = 4.1 の JSON を成り立たせるために置いた値、プレースホルダ = 暫定の指定で品質は出ない。

**確定**(architecture K18)

- **`_source` を除外しない**。`content` を含む全フィールドを `_source` に保持する(第1章。マッピングの `_source.excludes` や `enabled: false` を使わない)。`_reindex`・書き込み前の読み直し・`get_document` の前提である。

**方針**(推測。architecture G-1。ユーザー未確認。確定ではない)

- アクセスはエイリアス経由とする(第5章)。
- `dynamic: strict` にして、未定義のフィールドの混入を防ぐ。定義にない項目を含む文書は拒否される(Indexer の書き込みが失敗する)。項目を追加するときは、マッピングに先に追加する。
- 条件で絞り込む・一覧する項目(`source_id`、`mime_type`、`index_status`、`summary_status`)は `keyword` にする。
- 単一ノード前提の MVP で、`number_of_shards: 1`、`number_of_replicas: 0` とする。
- ハイライトに使うフィールド(n-gram などのサブフィールドを含む)は `index_options: offsets` でオフセットを保存する(第5章)。

**未決**

- どのフィールドをハイライト対象にするか。
- アナライザは、日本語を形態素解析(kuromoji または Sudachi)、英語を標準アナライザとし、識別子・型番の検索漏れを防ぐために n-gram のサブフィールドの追加を検討する。選定は評価セットの Recall@10・MRR で行う。
- 専用プラグインを導入した独自の OpenSearch イメージを使う前提(第7章)。実装時に確認する。

**仮置き**(定義がなく、4.1 の JSON を成り立たせるために置いた値)

- `title`・`summary`・`content` に `index_options: offsets` を付けること(ハイライト対象の推定)。
- 上記以外の項目の型(`document_id`、`external_id`、`content_hash`、`text_hash`、`summary_model` の `keyword`、`size` の `long`、`date`、`boolean`)。項目の用途からの案。
- `url`・`path`(U-1 の案)を、表示専用の `keyword` で `index: false` とすること。`path` を検索・絞り込みに使う場合は見直す(U-8)。`keyword` は長い値で文書の拒否(`document_rejected`)になりうる。最大長は未決で、実装時に確認する。表示専用なら、`doc_values: false`(並べ替え・集計用の列を持たない)を加える案、または `ignore_above` を付けて長い値を索引の対象から外す(拒否されず、`_source` には残る)案を併記する(いずれも案。値は実装時に決める)。

**プレースホルダ(検索品質は出ない)**

- `title`・`summary`・`content` はアナライザ未指定の `text` 型で、既定の標準アナライザで解析される。日本語アナライザと n-gram が未決のため、日本語の検索品質は期待できない。

**サイズへの影響(実測)**: `content` は検索用に解析・索引化され、さらに `_source` に原文のまま保持されるため、本文を二重に持つ。インデックスサイズの増加量と、`get_document` が文書全体を取得するときの取得量は、代表的な規模で実測する(architecture 15.4)。

### 4.1 マッピングの提案(案)

次の JSON は、上記の要素を並べた**提案(案)**であり、確定ではない。機械可読にしただけで、方針が決まったことを意味しない。方針で決まっていない部分は創作せず、次のとおり除いてある。

- `url` / `path` は 2 項目の案(U-1。ユーザー承認待ち)として含める(表示専用の `keyword`、`index: false`。仮置き)。
- 次の項目は含めない: `fetched_at` / `metadata`(U-3)、`acl`(型が未定義)、`summary_embedding`(U-2。ベクトルの次元・方式が未定義)、`extractor_version` / `extract_fail_count`(予約。MVP では書かない)。
- アナライザは指定しない(日本語アナライザと n-gram は未決)。
- `_source` の設定は書かない(既定のまま、全フィールドを保持する)。

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
      "document_id":       { "type": "keyword" },
      "source_id":         { "type": "keyword" },
      "external_id":       { "type": "keyword" },
      "url":               { "type": "keyword", "index": false },
      "path":              { "type": "keyword", "index": false },
      "title":             { "type": "text", "index_options": "offsets" },
      "summary":           { "type": "text", "index_options": "offsets" },
      "content":           { "type": "text", "index_options": "offsets" },
      "mime_type":         { "type": "keyword" },
      "size":              { "type": "long" },
      "source_updated_at": { "type": "date" },
      "indexed_at":        { "type": "date" },
      "content_hash":      { "type": "keyword" },
      "text_hash":         { "type": "keyword" },
      "summary_status":    { "type": "keyword" },
      "summary_model":     { "type": "keyword" },
      "index_status":      { "type": "keyword" },
      "truncated":         { "type": "boolean" },
      "last_seen_at":      { "type": "date" }
    }
  }
}
```

**注意**: `text_hash` は案(U-6)の項目で、導入しない場合はこの行を除く。`url` / `path` の 2 行は U-1 の案で、1 項目に変わる場合は差し替える。`path` の検索・絞り込みと最大長は未決(U-8。`keyword` は長い値で文書の拒否(`document_rejected`)になりうるため、実装時に確認する)。`dynamic: strict` のため、このままでは `fetched_at` / `metadata` を含む文書が拒否される(Indexer の書き込みが失敗する)。未決(U-3)の決定後に、追加が必要。`acl`、`summary_embedding`、`extractor_version`、`extract_fail_count` も、書き込む場合は同様に追加が必要になる。

エイリアス名・実インデックス名は未決。

## 5. 検索方式とインデックス運用

### 5.1 検索方式(Schema に関わる範囲)

- 基本は BM25 による全文検索とし、タイトル・要約・本文の重みを調整する(重みの値は未記載)。
- 日本語は形態素解析(kuromoji または Sudachi。評価して決める)、英語は標準アナライザで解析する。n-gram のサブフィールドの追加も検討する。
- ユーザー辞書・同義語辞書はファイルで管理し、更新したら再インデックスで反映する(第6章)。
- 将来は、要約 Embedding によるベクトル検索やハイブリッド検索を追加する。

### 5.2 エイリアス・ハイライト・補助インデックス

- インデックスにはエイリアス経由でアクセスする。マッピングや辞書を変えるときは、新しいインデックスを作ってからエイリアスを切り替える。切り替えは `_aliases` の remove と add を 1 つのリクエストで行い、原子的にする(案。architecture 11章に合わせる)。
- ハイライトに使うフィールド(サブフィールドを含む)は `index_options: offsets` でオフセットを保存する。ハイライタは unified(既定)を使う。オフセットがあると unified ハイライタは本文を再解析しないため、解析上限(`index.highlight.max_analyzed_offset`、既定は100万文字)は適用されない。**この上限を理由に長い文書の本文を切り詰めない**。
- plain ハイライタは常に再解析し、上限を超えると検索リクエスト全体が失敗するため使わない。
- オフセットの保存でインデックスサイズが増える。増え方は実装時に計測する(未決)。
- 本文サイズの上限(索引化の上限)は、リクエストサイズ・インデックスサイズ・処理時間などの観点で決める(未決。architecture U-8 と同じ論点)。上限を超える場合は、上限までを索引化して `truncated=true` にする。`_source` の `content` も、上限で切り詰めた後のテキストである。
- 長い文書で検索精度に問題が出た場合は、見出し・セクション単位の補助インデックスを追加できる構成にする。固定長チャンクへの分割は初期要件にしない。

## 6. 再インデックス

マッピングや辞書を変えるときの手段は `_reindex` である。新しいインデックスを作り、旧インデックスの文書を `_source` からコピーして、エイリアスを切り替える。`_source` に `content` を含む全フィールドを保持しているので、本文・要約・`last_seen_at`・処理状態は、再クロールなしで引き継がれる。

- 移行先のマッピングには、全フィールドの定義が要る。`dynamic: strict` のため、定義が欠けた項目を持つ文書は、その文書のコピーが失敗するだけでなく、`_reindex` 全体が中断しうる(`conflicts` などの設定による。実機で確認する。architecture U-31)。
- **切り替え前の確認**(案): `_reindex` の応答の `failures` が空であること、コピーした件数が一致すること、新旧インデックスの `_count` が一致することを確かめてから、エイリアスを切り替える。切り替えは `_aliases` の remove と add を 1 つのリクエストで行う(原子的。案)。
- `_reindex` で `_seq_no` が振り直されるため、切り替え前に取得した `if_seq_no` は無効になる。その後の書き込みは 409 になり、読み直しで収束する。
- 対象のデータソース(インデックス全体を作り直すときはすべて)のクロールと要約の書き込み(および削除の実行)を止めてから行う。停止の方法・実行中の書き込みの終了確認(メンテナンスフラグ。案)は `indexer-architecture-v0.6.md` 11章。
- 旧インデックスは、新インデックスの確認が済むまで残しておく(安全手順。必須とはしない)。

**スナップショットは運用者の責務**(architecture K21。確定): 取得の手順・周期・復元の手順は、本書も architecture も仕様として定めない。ただし、Store 層(`loreley-sources`、`loreley-jobs`、`loreley-deletions`)と検索インデックスは同じ OpenSearch にあるため、運用者が取る 1 つのスナップショットで、設定・ジョブ・削除結果・文書を、取得時点の状態に整合して復元できる。スナップショットがない場合は、再クロールで文書を戻す(下表)。

復旧範囲(`indexer-architecture-v0.6.md` 14.2 と同じ):

| 状況 | 対応 |
| --- | --- |
| マッピング・アナライザ・辞書の変更 | `_reindex`。`_source` から再構築され、再クロールは不要。`last_seen_at` と要約は保持される |
| 索引だけを失った(喪失・破損。Store 層は残る) | 再クロールのみ(データソースの再登録は不要)。すべて新規の文書として登録され、`last_seen_at` は初期化され(クロール開始時刻)、要約は再生成される。運用者のスナップショットがあれば、そこから復元してもよい |
| OpenSearch 全体を失った(索引と Store 層をまとめて失った) | スナップショットがあれば運用者が復元する(上記)。なければ再クロールで文書を戻す。データソース設定は再登録が要り、ジョブ履歴・削除結果は失われる。`last_seen_at` と要約は上の行と同じ |
| 抽出ロジックの変更 | 再クロール。`text_hash` が変わった文書が次の全件処理で全文書き込みされ、要約は `pending` に戻る。`_reindex` は使わない(`_source` の `content` は旧い抽出結果のため) |
| 要約ロジック・モデルの変更 | 再書き込みモード(案。architecture P39)でクロールする。本文ごと全文書き込みし、要約は `pending` に戻って再生成される。詳細は architecture 14.2 |

`loreley-deletions` だけを失った場合は `loreley-deletions-v0.6.md` 7章を参照。

## 7. OpenSearch イメージ・バージョン

前提(実装時に確認する)。

- kuromoji も Sudachi も OpenSearch の既定の配布イメージには含まれない前提で、プラグインを導入した**独自の OpenSearch イメージ**をビルドして配布する。Sudachi は、辞書の入手とライセンスの確認も必要になる。
- OpenSearch 本体とプラグインのバージョンは一致させて固定する。OpenSearch を更新するときは、プラグインも同時に更新して、再インデックスの要否を確認する。

## 8. テスト観点

観点のみ。ID(E-6、R-4 など)は `indexer-architecture-v0.6.md` のテスト観点 ID(16章)と同じもので、この表は同じ観点のうち Schema に関わるものを抜き出している。Schema と再インデックスに関わる粒度の観点だけを載せる。R-5 は欠番。

| ID | 観点 | 期待結果 |
| --- | --- | --- |
| E-6 | 本文がサイズ上限を超える(抽出後の本文) | 上限までが索引化され、`truncated=true` になる。ハイライトが長文でも失敗しない |
| R-4 | `_reindex` でコピーする(保持の確認) | `content`・`last_seen_at`・要約が保持される。移行全体(`dynamic: strict` の欠落、切り替え前の確認、409 での収束)は R-8 |
| R-6 | 辞書を更新する | 再インデックスで反映される |
| R-7 | 抽出ロジックを変更する(原本は変わらず、抽出結果の `content` だけが変わる。`content_hash` は同じ) | `_reindex` ではなく、次の全件処理の再クロールで反映される。`text_hash` が変わるため変更ありと判定され、全文書き込みで `content`・`text_hash` が更新され、要約は無効化される(`pending` に戻る。要約が無効なら `disabled`) |
| S-10 | 日本語検索 | 評価セットで Recall@10・MRR を測定し、アナライザ候補(kuromoji、Sudachi、n-gram)を比較する |

次の観点は `indexer-architecture-v0.6.md` のテスト観点を参照する(ID は同書のもので、本書では再掲しない)。

- 変更のない文書を再処理したときに書かない(C-10)、メタデータだけが変わったときの要約の引き継ぎ(C-2)、本文が変わったときの要約の無効化(C-3)
- 原本の `content_hash` は同じで抽出結果が違う場合の全文書き込みと要約の無効化(C-12)
- 要約の生成中に `text_hash` が変わった場合の、旧い要約の破棄(C-15)
- 登録・要約の書き戻しの PUT の 409 と読み直し、要約の書き戻しと `last_seen_at` の部分更新の並行(C-18、C-19、C-20)
- `last_seen_at` の部分更新の max 比較と 404(C-21)
- 再書き込みモードでの要約の再生成(C-22。案)
- `_source` に `content` が保持され、ID で取得できること(C-23)
- 抽出に失敗した文書の登録と一覧(E-44)
- `_reindex` での移行全体(R-8。R-4 は保持の確認に絞る。`failures` が空・件数一致・新旧 `_count` 一致の確認と、`dynamic: strict` に定義が欠けたときの失敗を含む)

Schema 検証観点(番号なし):

- `_source` の除外設定がないこと(`content` を含む全フィールドが ID の取得で返る)。
- `dynamic: strict` のマッピングに、書き込む全フィールドが定義されていること。欠けた項目を含む文書は拒否される(`_reindex` でも失敗する)。
- 原本の `content_hash` が同じで抽出結果の `content` だけが変わり、要約の生成中だった場合(C-12、C-15): 生成した要約は、書き戻しの時点で `text_hash` が生成元と不一致のため反映されない。
- 抽出に失敗した文書は `content`・`text_hash`・要約を持たず、`index_status=extract_failed` で検索により一覧できる(E-44)。

## 9. 未決事項(ユーザー判断)

ID は文書ローカル。欠番(再利用しない): U-4、U-5、U-7。

| ID | 内容 | 選択肢 |
| --- | --- | --- |
| U-1 | `url` / `path` の項目数(architecture U-16 の一部と同じ論点)。2項目(`url` = アクセス可能な原文の URL、`path` = データソース内の文書パス。独立した任意項目。`external_id` は ID の責務)を案(推奨。ユーザー承認待ち)とする | (1) 2項目(案・推奨) (2) どちらか一方が入る1項目 |
| U-2 | `summary_embedding` の位置づけ(architecture U-25 と同じ論点) | (1) MVP 未使用の予約項目として明記 (2) 項目から外す。ほか、ユーザー判断 |
| U-3 | `fetched_at` / `metadata` を検索インデックスに持つか(architecture U-16 と同じ論点) | (1) 保存しない(受け取るだけ) (2) 検索インデックスに項目を追加(マッピングにも追加) |
| U-6 | `text_hash` を検索インデックスの文書に持つこと(案。architecture P35)。変更の有無の判定(architecture 4.3)と、要約の書き戻しの条件(生成元の `content_hash` と `text_hash` が現在値と一致)に使い、原本が同じで抽出結果だけが変わる場合を区別する | (1) 案どおり持つ (2) 持たない(変更判定と、生成中の旧い要約の書き戻し防止は別の方法を検討)。ほか、ユーザー判断 |
| U-8 | `path` を検索・絞り込みに使うか、`url` / `path` の最大長(architecture U-16 に関連)。使う場合はマッピングの `index` と型を見直す | (1) 表示のみ(`index: false`。案) (2) 絞り込みに使う(`keyword` で索引化) (3) 全文検索に使う(`text`)。最大長は別途決める |

## 10. 確認状況

| 項目 | 区分 | 備考 |
| --- | --- | --- |
| `last_seen_at` を検索インデックスの文書に持つ。`crawl_started_at` を渡して Indexer が書く。全件処理(差分検知は将来拡張) | 確定 | 負荷はリスクとして扱い、実測方針は維持する |
| 書き込みは Indexer だけ。検索インデックスが本文・メタデータ・要約・処理状態・`last_seen_at` の唯一の正本 | 確定 | architecture K18 |
| `_source` に `content` を保持する(除外しない) | 確定 | 唯一の正本の前提(architecture K18、3.4) |
| 書き込みは PUT 基本。種別は全文書き込み(PUT)と `last_seen_at` の部分更新(Update)の2種。要約の書き戻しは PUT | 確定 | architecture K19。細部(GET → `if_seq_no`/`if_primary_term` 付き index、`op_type=create`、max 比較のスクリプト、409 は読み直し)は案(architecture P40) |
| `index_status` は `indexed` / `extract_failed` | 案 | `extract_failed` の文書は `content`・`text_hash`・要約を持たない(案) |
| `size` を検索インデックスの文書に持つ(型は `long`。仮置き) | 案 | 変更の有無の判定に使う。architecture 4.3 |
| `extractor_version` / `extract_fail_count` は予約項目で、MVP のマッピングに入れない | 案 | 差分検知の導入時に追加(architecture 13.1) |
| `_reindex` で再インデックスする。旧インデックスの保持は安全手順で必須としない。切り替え前の確認(`failures` が空、件数一致、新旧 `_count` 一致)と `_aliases` の remove+add の 1 リクエスト | 案 | architecture 11章 |
| スナップショットは運用者の責務で、設計書は手順を定めない。Store 層と検索インデックスは同じ OpenSearch にあり、1 つのスナップショットで取得時点の状態に整合して復元できる | 確定 | architecture K21(2026-11-10) |
| 復旧範囲(マッピング等の変更は `_reindex`、索引だけの喪失・破損と抽出ロジックの変更は再クロール、OpenSearch 全体の喪失はスナップショットまたは再クロール+データソース再登録) | 案 | architecture 14.2 |
| メンテナンスフラグによる書き込み停止 | 案 | `indexer-architecture-v0.6.md` 11章 |
| 検索インデックスの `number_of_shards: 1`、`number_of_replicas: 0`、`dynamic: strict`、keyword 化、エイリアス経由 | 方針(推測。ユーザー未確認) | architecture G-1 では適用する想定(推測)として扱っている。未決項目(ハイライト対象、アナライザ、プラグイン)は第4章で分けて記載 |
| `extract_failed` の文書の `summary_status` を `disabled` とし、要約の再走査の対象から外す | 案 | architecture の最終記述に合わせる |
| 日時項目を UTC・ISO 8601・ミリ秒に正規化する | 案 | 確認は architecture U-31 に追加(2.1) |
| 4.1 の JSON の `index_options: offsets` を付けるフィールド(`title`・`summary`・`content`)、および各項目の型(`text_hash`、`size` を含む) | 仮置き | 定義なし。用途からの案 |
| 4.1 の JSON の `text` 型(アナライザ未指定) | プレースホルダ | 日本語の検索品質は出ない。アナライザは未決 |
| 4.1 の JSON に `fetched_at` / `metadata`・`acl`・`summary_embedding`・`extractor_version`・`extract_fail_count` がない | 未決 | `dynamic: strict` のため、書き込む項目は追加が必要 |
| 4.1 の JSON の `url` / `path`(`keyword`、`index: false`) | 案(推奨。ユーザー承認待ち。仮置きの型) | 2 項目の案(U-1)。`path` の使い方と最大長は未決(U-8) |
| 第4.1章のマッピング JSON 全体 | 案(提案) | 要素ごとの区分は第4章。方針外の項目・アナライザは含めていない |
| 検索インデックスのマッピング全体(アナライザ、n-gram、フィールド型) | 未決 | architecture U-7 |
| 日本語アナライザ(kuromoji か Sudachi)と n-gram 併用 | 未決 | 評価セットの Recall@10・MRR で選定 |
| BM25 の重み(タイトル・要約・本文) | 値の記載なし | 「調整する」とのみ記載 |
| 本文サイズの上限(索引化の上限)、オフセット保存と `_source` 保持による増加量 | 未決 | 実測して決める(architecture 15.4) |
| 要約モデル・コスト・時間 | 未決 | |
| `text_hash` による変更の有無の判定と要約の書き戻しの条件 | 案 | architecture P35。U-6。ユーザー未確認 |
| `crawl_started_at` を `deletion_result` の複写と照合し、不一致は拒否 | 案 | architecture P36。`loreley-deletions-v0.6.md` U-8 |
| 再書き込みモード(本文が変わらない文書の要約を再生成するときに、変更なしの判定をしない) | 案(ユーザー承認待ち) | architecture P39 |
| 2.4 のフィールド対応表 | 案(整理) | 項目表・書き込み種別を対応づけた表。`url` / `path` は 2 項目の案(U-1)。`fetched_at` / `metadata` は決定待ち |
| `url` / `path` を 2 項目とする(`url` = アクセス可能な原文の URL、`path` = データソース内の文書パス。独立した任意項目) | 案(推奨。ユーザー承認待ち) | architecture U-16。U-1 |
| U-1 `url` / `path` の項目数 | 未決(ユーザー判断) | |
| U-8 `path` の検索・絞り込みの要否と最大長 | 未決(ユーザー判断) | |
| U-2 `summary_embedding` の位置づけ | 未決(ユーザー判断) | |
| U-3 `fetched_at` / `metadata` の保存先 | 未決(ユーザー判断) | |
| U-6 `text_hash` の導入 | 案(ユーザー判断) | architecture P35 |
| 独自 OpenSearch イメージ、プラグイン・本体のバージョン一致 | 前提 | 実装時に確認 |
