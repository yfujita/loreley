# 検索インデックス Schema 設計書 v0.3

## 0. この文書について

- 対象: 1文書 = 1検索レコードで全文検索に使う OpenSearch インデックス(以下「検索インデックス」)の Schema。
- 区分の表記: 確定 = ユーザー確定、案 = ユーザー未確定、未決 = 決めていない、推測 = 根拠が弱い想定。第4章では、これに加えて方針・仮置き・プレースホルダを区分として使う(同章で定義)。各項目の区分は第10章の表に集約する。本書は検索インデックスの Schema を単独で読めるようにまとめた文書である。
- 未決の ID: 本文書の `U-*` は**この文書だけで通用するローカル ID**。他文書の未決は『architecture U-16』のように文書名付きで書く。「architecture U-n と同じ論点」は、`indexer-architecture-v0.3.md` 17.3 の同じ判断事項を指す。
- 関連文書:
  - `indexer-architecture-v0.3.md` — 書き込み種別と競合制御、再インデックス前の停止手順、要約生成の整合、削除の判断・実行。
  - `indexer-api-v0.3.md` — Crawler から Indexer への登録・部分更新の契約。
  - `loreley-texts-v0.3.md` — 正の保存先(Store 層)。
  - `loreley-deletions-v0.3.md` — 削除の記録。
- 検索クエリ自体(Search API、MCP)は対象外。

## 1. 位置づけ

- 1文書 = 1検索レコードを基本とし、タイトル・要約・本文を BM25 で検索する。日本語を主な対象とし、英語も併せて解析する。
- チャンク分割・ベクトル検索は、評価結果を見て判断する(プロダクト側の判断)。
- 検索インデックスへの書き込みは Indexer だけが行う。
- 文書の本文・要約・処理状態の**正は Store 層**(`loreley-texts`)で、検索インデックスはそこから作る派生物である。ただし `last_seen_at` だけは検索インデックスが唯一の保存場所である。

## 2. フィールド

`_id` は `document_id`(SHA-256 の16進文字列、小文字。`SHA-256(source_id + "\0" + external_id)`。生成規則は `indexer-architecture-v0.3.md`)。

| フィールド | 用途 |
| --- | --- |
| `document_id` | 一意な識別 |
| `source_id` | データソースによる絞り込み |
| `external_id` | データソース内の識別子(突合と、削除対象の特定に使う) |
| `title` | タイトル検索 |
| `summary` | 文書全体の主題による検索 |
| `content` | 細かい語句・識別子による全文検索(抽出・正規化後の本文) |
| `url` / `path` | 原文への参照(表示のみ)。項目数は未決(U-1) |
| `mime_type` | 文書形式による絞り込み |
| `source_updated_at` | 更新日による絞り込み |
| `indexed_at` | インデックスに登録した日時 |
| `content_hash` | 要約の条件付き更新の判定に使う |
| `summary_status` / `summary_model` | 要約の生成状態と、生成に使ったモデル・バージョン |
| `index_status` / `truncated` | 抽出状態と、本文を切り詰めたかどうか |
| `last_seen_at` | 列挙クロールで最後に見つかった日時(期限による削除の判定) |
| `acl` | アクセス制御用の属性。MVP では使わない予約項目 |
| `summary_embedding` | 意味検索用のベクトル(任意)。位置づけは未決(U-2) |

未決の点:

- **U-1 `url` / `path`**(architecture U-16 の一部と同じ論点): 「どちらか一方が入る1項目」か「2項目」か決まっていない。マッピング化の前に決める必要がある。
- **U-2 `summary_embedding`**(architecture U-25 と同じ論点): 任意項目として挙がっているが、Embedding 生成は MVP で行わない。`acl` と違い予約とは明記されていない。MVP で未使用の予約項目として置くかは、ユーザー判断。
- **U-3 `fetched_at` / `metadata`**(architecture U-16 と同じ論点): Crawler から渡されるバッチ登録の文書(`indexer-api-v0.3.md` 4.3 の `documents[]`)にあるが、この表にも `loreley-texts` にもなく、保存先が決まっていない。保存するか、受け取るだけにするかはユーザー判断。

### 2.1 `last_seen_at` の意味

- バッチ登録の文書(`documents[]`)には含めない。クロールの実行コンテキストとして `crawl_started_at`(クロールの開始時刻)が Indexer に渡され、Indexer が `last_seen_at` に書く(渡し方は `indexer-api-v0.3.md`)。
- `fetched_at`(原本を取得した日時)とは別物で、`last_seen_at` は「列挙で見つかった日時」である。
- 毎回の全文 upsert で更新されるほか、取得に失敗してスキップした文書の誤削除を防ぐため、列挙で見つかった時点で `last_seen_at` だけを部分更新する(MVP は全件更新で、差分検知は将来拡張)。
- 期限による削除の判定(`last_seen_at + TTL < 現在時刻`)と、削除前の件数照合(`last_seen_at >= crawl_started_at` の件数)に使う。詳細は `indexer-architecture-v0.3.md`。
- 消えた文書は、削除されるまで検索結果に残る。検索時に `last_seen_at` で除外はしない。

### 2.2 写しと正

`summary` / `summary_status` / `summary_model` / `index_status` / `truncated` は、検索結果の表示と絞り込みのための**写し**である。正は Store 層(`loreley-texts`)に置く。

### 2.3 状態値

- `summary_status`: `disabled`(要約が無効)、`pending`、`generated`、`failed`。
- **`pending` の意味の拡張(案。architecture P30)**: Store 層の `summary_status` は、要約が検索インデックスへ反映されるまで `pending` のままにする(生成済みで未反映の状態も `pending`)。`generated` になるのは検索インデックスへの反映に成功した後である。項目は追加しない。検索インデックス側の `summary_status` は、要約の部分更新の成功時に `generated` を書く。
- `index_status`: `pending_index`(**Store 層のみ**。登録前)、`indexed`、`extract_failed`。検索インデックスに現れる値は `indexed` と `extract_failed`。

### 2.4 突合との関係(案)

突合ジョブが、検索インデックスにあって Store 層にない文書(検索インデックスだけにある文書)を見つけたときは、MVP では削除せず、検出して表示するだけにする(案。architecture P28)。削除や再登録の扱いは `indexer-architecture-v0.3.md` 10章。

## 3. 書き込み種別とフィールド

検索インデックスへの書き込みは、Indexer が次の3種類で行う(競合時の扱いは `indexer-architecture-v0.3.md`)。

| 種別 | 書くフィールド | 備考 |
| --- | --- | --- |
| 全文 upsert | 全フィールド。`last_seen_at` は既存値と `crawl_started_at` の大きい方(新規作成時は `crawl_started_at`)、`content_hash` は新しい値。`summary` と `summary_status` は、`content_hash` が既存と同じなら既存の値を保持し、違えば `summary` は書かず `summary_status=pending`(要約が無効なら `disabled`) | MVP は全件更新で、すべての文書を全文 upsert する |
| `last_seen_at` の部分更新 | `last_seen_at` のみ(値は `crawl_started_at`) | max 比較。検索インデックスに文書がなければ(404)何もしない(upsert しない) |
| 要約の部分更新 | `summary`、`summary_status`、`summary_model`、`summary_embedding` | 検索インデックス上の `content_hash` が生成元と一致するときだけ書く |

要約の反映規則(案。architecture P30): 要約テキストと生成元の `summary_content_hash` を先に Store 層へ保存し、そのうえで要約の部分更新を行う(Store 層の規則は `loreley-texts-v0.3.md` 4.2)。反映に失敗して再走査で見つかった文書は、Store 層が `pending` かつ `summary_content_hash` が本文のハッシュと一致するなら、要約を再生成せず検索インデックスへの反映(要約の部分更新)だけを行う。不一致なら要約を再生成する。

全文 upsert の `summary` / `summary_status` の保持は、Indexer が「原本ハッシュ一致かつ抽出 text 一致かつ Store 層の `index_status` が `indexed`」と判断した場合に限る(案。architecture P26)。`pending_index`(または `extract_failed`)の文書は、`content_hash` と text が同じでも、常に確定更新まで進める。(b)経路の全文 upsert が失敗して `pending_index` が残った文書が、次回クロールで(a)と誤判定されて永続するのを防ぐため。原本ハッシュが一致しても text が不一致のときは、`content_hash` が同じでも要約を保持せず、`summary` は書かずに `summary_status=pending`(要約が無効なら `disabled`)とする。

保証の範囲: リース切れ後の旧 Crawler による全文 upsert は原子的には拒否できず、保証するのは `last_seen_at` が古い値に戻らないことまでである。完全な分散フェンシングは複数 Crawler 化の際の将来拡張。

## 4. Mapping・Analyzer・Shard/Replica

検索インデックスのマッピング全体は未決(architecture U-7 と同じ論点)。実装時に確定する。以下は要素ごとに、確かさを区分して並べる。区分の意味: 方針 = 本書として定めている内容、推測 = 根拠が弱い想定、仮置き = 4.1 の JSON を成り立たせるために置いた値、プレースホルダ = 暫定の指定で品質は出ない。

**方針**

- アクセスはエイリアス経由とする(第5章)。
- ハイライトに使うフィールド(n-gram などのサブフィールドを含む)は `index_options: offsets` でオフセットを保存する(第5章)。どのフィールドがハイライト対象かは未定義。
- アナライザは、日本語を形態素解析(kuromoji または Sudachi)、英語を標準アナライザとし、識別子・型番の検索漏れを防ぐために n-gram のサブフィールドの追加を検討する。選定は評価セットの Recall@10・MRR で行う(未決)。
- 専用プラグインを導入した独自の OpenSearch イメージを使う(第7章)。

**推測**(方針として定めているのは Store 層のインデックスだけ(`loreley-texts-v0.3.md` 第3章)で、検索インデックスへの適用は推測。実装時に確認する)

- 単一ノード前提の MVP での `number_of_shards: 1`、`number_of_replicas: 0`。
- `dynamic: strict`。
- 絞り込みに使う項目(`source_id`、`mime_type`、`index_status`、`summary_status`)の `keyword` 化。

**仮置き**(定義がなく、4.1 の JSON を成り立たせるために置いた値)

- `title`・`summary`・`content` に `index_options: offsets` を付けること(ハイライト対象の推定)。
- 上記以外の項目の型(`document_id`、`external_id`、`content_hash`、`summary_model` の `keyword`、`date`、`boolean`)。項目の用途からの案。

**プレースホルダ(検索品質は出ない)**

- `title`・`summary`・`content` はアナライザ未指定の `text` 型で、既定の標準アナライザで解析される。日本語アナライザと n-gram が未決のため、日本語の検索品質は期待できない。

### 4.1 マッピングの提案(案)

次の JSON は、上記の要素を並べた**提案(案)**であり、確定ではない。機械可読にしただけで、方針が決まったことを意味しない。方針で決まっていない部分は創作せず、次のとおり除いてある。

- 次の項目は含めない: `url` / `path`(U-1)、`acl`(型が未定義)、`summary_embedding`(U-2。ベクトルの次元・方式が未定義)。
- アナライザは指定しない(日本語アナライザと n-gram は未決)。

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
      "title":             { "type": "text", "index_options": "offsets" },
      "summary":           { "type": "text", "index_options": "offsets" },
      "content":           { "type": "text", "index_options": "offsets" },
      "mime_type":         { "type": "keyword" },
      "source_updated_at": { "type": "date" },
      "indexed_at":        { "type": "date" },
      "content_hash":      { "type": "keyword" },
      "summary_status":    { "type": "keyword" },
      "summary_model":     { "type": "keyword" },
      "index_status":      { "type": "keyword" },
      "truncated":         { "type": "boolean" },
      "last_seen_at":      { "type": "date" }
    }
  }
}
```

**注意**: このままでは `url` / `path` を含む文書が `dynamic: strict` で拒否される(Indexer の書き込みが失敗する)。未決(U-1)の決定後に追加が必要。`acl` と `summary_embedding` は MVP で書き込まない予約項目だが、書き込む場合(要約の部分更新が `summary_embedding` を含む場合など)も同様に追加が必要になる。

エイリアス名・実インデックス名は未決。

## 5. 検索方式とインデックス運用

### 5.1 検索方式(Schema に関わる範囲)

- 基本は BM25 による全文検索とし、タイトル・要約・本文の重みを調整する(重みの値は未記載)。
- 日本語は形態素解析(kuromoji または Sudachi。評価して決める)、英語は標準アナライザで解析する。n-gram のサブフィールドの追加も検討する。
- ユーザー辞書・同義語辞書はファイルで管理し、更新したら再インデックスで反映する(第6章)。
- 将来は、要約 Embedding によるベクトル検索やハイブリッド検索を追加する。

### 5.2 エイリアス・ハイライト・補助インデックス

- インデックスにはエイリアス経由でアクセスする。マッピングや辞書を変えるときは、新しいインデックスを作ってからエイリアスを切り替える。
- ハイライトに使うフィールド(サブフィールドを含む)は `index_options: offsets` でオフセットを保存する。ハイライタは unified(既定)を使う。オフセットがあると unified ハイライタは本文を再解析しないため、解析上限(`index.highlight.max_analyzed_offset`、既定は100万文字)は適用されない。**この上限を理由に長い文書の本文を切り詰めない**。
- plain ハイライタは常に再解析し、上限を超えると検索リクエスト全体が失敗するため使わない。
- オフセットの保存でインデックスサイズが増える。増え方は実装時に計測する(未決)。
- 本文サイズの上限(索引化の上限)は、リクエストサイズ・インデックスサイズ・処理時間などの観点で決める(未決。architecture U-8 と同じ論点)。上限を超える場合は、上限までを索引化して `truncated=true` にする。
- 長い文書で検索精度に問題が出た場合は、見出し・セクション単位の補助インデックスを追加できる構成にする。固定長チャンクへの分割は初期要件にしない。

## 6. 再インデックス

マッピングや辞書を変えるとき、またはインデックスを作り直すときは、次の2つの手段を使い分ける。どちらも、対象のデータソース(インデックス全体を作り直すときはすべて)のクロールと要約の書き込み(および削除の実行)を止めてから行う。停止の方法・実行中の書き込みの終了確認(メンテナンスフラグ。案)は `indexer-architecture-v0.3.md`。

| 手段 | 内容 | `last_seen_at` | 要約 | 使う場面 |
| --- | --- | --- | --- | --- |
| (a) `_reindex` で旧インデックスからコピー | 新しいインデックスを作り、旧インデックスの文書をコピーしてエイリアスを切り替える | 保持される | 保持される | マッピング・辞書・アナライザの変更(通常はこちら) |
| (b) Store 層からの再構築 | Store 層の抽出済みテキストから、検索インデックスを新しく作る。再クロールは不要 | 再構築時刻に初期化される(TTL の時計が再構築時から始まる) | Store 層の要約のうち、生成元の `content_hash` が本文と一致するものだけが保持される。不一致は `pending` に戻す | **旧インデックスを失った場合に限る**(案)。抽出ロジックを変えたときは使わず、全件更新の再クロールで反映する |

検索インデックスと Store 層の両方を失った場合は再クロールが必要。`loreley-deletions` を失った場合は `loreley-deletions-v0.3.md` を参照。

## 7. OpenSearch イメージ・バージョン

前提(実装時に確認する)。

- kuromoji も Sudachi も OpenSearch の既定の配布イメージには含まれない前提で、プラグインを導入した**独自の OpenSearch イメージ**をビルドして配布する。Sudachi は、辞書の入手とライセンスの確認も必要になる。
- OpenSearch 本体とプラグインのバージョンは一致させて固定する。OpenSearch を更新するときは、プラグインも同時に更新して、再インデックスの要否を確認する。

## 8. テスト観点

観点のみ。ID(E-6、R-4 など)は `indexer-architecture-v0.3.md` のテスト観点 ID と同じもので、この表は同じ観点のうち Schema に関わるものを抜き出している。Schema と再インデックスに関わる粒度の観点だけを載せる。

| ID | 観点 | 期待結果 |
| --- | --- | --- |
| E-6 | 本文がサイズ上限を超える(抽出後の本文) | 上限までが索引化され、`truncated=true` になる。ハイライトが長文でも失敗しない |
| R-4 | (a) `_reindex` でコピーする | `last_seen_at` と要約が保持される |
| R-5 | (b) Store 層から再構築する | `last_seen_at` が再構築時刻に初期化される。生成元の `content_hash` が本文と一致する要約だけが保持され、不一致は `pending` に戻る |
| R-6 | 辞書を更新する | 再インデックスで反映される |
| R-7 | 抽出ロジックを変更する(原本は変わらず、抽出結果の text だけが変わる。`content_hash` は同じ) | Store 層からの再構築ではなく、次の全件更新の再クロールで反映される。再クロールでは text が不一致と判定され(案。architecture P26)、`pending_index` 経路で `loreley-texts` の `text` と検索インデックスの `content` が更新され、要約は無効化(`pending` に戻る。要約が無効なら `disabled`)される |
| S-10 | 日本語検索 | 評価セットで Recall@10・MRR を測定し、アナライザ候補(kuromoji、Sudachi、n-gram)を比較する |

次の観点は `indexer-architecture-v0.3.md` のテスト観点を参照する(ID は同書のもので、本書では再掲しない)。

- 同一ハッシュで抽出 text も同じ文書の再登録(Store 層を書かず全文 upsert のみ。案。P26): C-10
- 原本の `content_hash` は同じで抽出 text が違う場合の `pending_index` 経路と要約の無効化(案。P26): C-12
- 要約が Store 層に保存済みで検索インデックスへの反映前に止まった場合(案。P30): C-13
- 検索インデックスにだけある文書を突合ジョブが見つけた場合(削除せず検出・表示のみ。案。P28): E-42

Schema 検証観点(番号なし):

- 原本の `content_hash` が同じで抽出 text が違い、(b)経路の全文 upsert が失敗して Store 層に `pending_index` と新しい `text` が残った後の次回クロールで、`content_hash`・`text` が一致して見えても `index_status` が `pending_index` のため(a)に入らず、全文 upsert と確定更新まで進んで `pending_index` が解消される(案。P26)。

## 9. 未決事項(ユーザー判断)

ID は文書ローカル。

| ID | 内容 | 選択肢 |
| --- | --- | --- |
| U-1 | `url` / `path` の項目数(architecture U-16 の一部と同じ論点) | (1) どちらか一方が入る1項目 (2) 2項目 |
| U-2 | `summary_embedding` の位置づけ(architecture U-25 と同じ論点) | (1) MVP 未使用の予約項目として明記 (2) 項目から外す。ほか、ユーザー判断 |
| U-3 | `fetched_at` / `metadata` の保存先(architecture U-16 と同じ論点) | (1) 保存しない(受け取るだけ) (2) 検索インデックスまたは `loreley-texts` に項目を追加 |
| U-4 | 突合で検索インデックスにだけある文書を、MVP では削除せず検出・表示のみとするか(案。architecture P28) | (1) 検出のみ(案) (2) 削除する。ほか、ユーザー判断 |
| U-5 | `pending` の意味の拡張(検索反映成功まで Store 層は `pending`)と、要約の反映規則(案。architecture P30) | (1) 案どおり (2) 項目を追加して未反映を区別。ほか、ユーザー判断 |

## 10. 確認状況

| 項目 | 区分 | 備考 |
| --- | --- | --- |
| `last_seen_at` を検索インデックスの文書に持つ。`crawl_started_at` を渡して Indexer が書く。全件更新(差分検知は将来拡張) | 確定 | 負荷はリスクとして扱い、実測方針は維持する |
| 書き込みは Indexer だけ。正は Store 層、検索インデックスは派生物 | 確定 | |
| Store 層からの再構築は旧インデックスを失った場合に限る | 案 | ユーザー未確認の仮決定 |
| メンテナンスフラグによる書き込み停止 | 案 | `indexer-architecture-v0.3.md` |
| 検索インデックスにも `number_of_shards: 1`、`number_of_replicas: 0`、`dynamic: strict`、keyword 化を適用 | 推測 | 方針として定めているのは Store 層のみ |
| 4.1 の JSON の `index_options: offsets` を付けるフィールド(`title`・`summary`・`content`)、および各項目の型 | 仮置き | 定義なし。用途からの案 |
| 4.1 の JSON の `text` 型(アナライザ未指定) | プレースホルダ | 日本語の検索品質は出ない。アナライザは未決 |
| 4.1 の JSON に `url` / `path`・`acl`・`summary_embedding` がない | 未決 | `dynamic: strict` のため、書き込む項目は追加が必要 |
| 第4.1章のマッピング JSON 全体 | 案(提案) | 要素ごとの区分は第4章。方針外の項目・アナライザは含めていない |
| 検索インデックスのマッピング全体(アナライザ、n-gram、フィールド型) | 未決 | |
| 日本語アナライザ(kuromoji か Sudachi)と n-gram 併用 | 未決 | 評価セットの Recall@10・MRR で選定 |
| BM25 の重み(タイトル・要約・本文) | 値の記載なし | 「調整する」とのみ記載 |
| 本文サイズの上限(索引化の上限)、オフセット保存による増加量 | 未決 | 実測して決める |
| 要約モデル・コスト・時間 | 未決 | |
| 同一 `content_hash` のときの text 比較方式(原本ハッシュ一致かつ text 一致なら Store 層を書かず全文 upsert のみ、不一致なら `pending_index` 経路。`text_hash` は導入しない) | 案 | architecture P26。`extractor_version` 導入時に再検討 |
| 要約の反映規則(`pending` の意味の拡張、`summary_content_hash` を先に保存、再走査で反映のみ/再生成) | 案 | architecture P30。ユーザー未確認 |
| 突合は検索インデックスにだけある文書を検出のみとする(2.4) | 案 | architecture P28。U-4 |
| U-4 突合で検索のみの文書を検出のみとするか | 案(ユーザー判断) | architecture P28 |
| U-5 `pending` の意味の拡張と要約の反映規則 | 案(ユーザー判断) | architecture P30 |
| U-1 `url` / `path` の項目数 | 未決(ユーザー判断) | |
| U-2 `summary_embedding` の位置づけ | 未決(ユーザー判断) | |
| U-3 `fetched_at` / `metadata` の保存先 | 未決(ユーザー判断) | |
| 独自 OpenSearch イメージ、プラグイン・本体のバージョン一致 | 前提 | 実装時に確認 |
