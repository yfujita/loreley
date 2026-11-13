# Connector 共通インタフェース設計書 v0.2

- 版: v0.2
- 更新日: 2026-11-13
- 前版: `connector-interface-v0.1.md`
- v0.2 の改訂: architecture v0.2(外部レビューへの対応)への追従のみ。契約・規則・ID の変更はない。8章の `connector_config` の確定時点を architecture 4.5 の手順 6(1 度だけ読む。CA-P-51)に合わせた。関連文書の表に `crawler-design-decisions-v0.1.md` を追加した。7章に Crawler 側の上限と Indexer 側の上限の起動時の検査(CA-P-55)への参照、11.6 に識別子エラーと削除判定(architecture 7.7、CA-U-7)への参照を追記した。
- 位置づけ: Crawler の Connector(データソースから文書を列挙・取得する部品)と Crawler 本体の境界を定める。FileSystem(MVP)と Web(将来)の両方に適用できる共通の抽象、文書メタデータ、識別子規則(`external_id`・`document_id`・`content_hash`)、エラー分類を扱う。
- 本書は「案」「推測」「未決」を確定扱いにしない。ユーザー承認済みの事項だけを「確定」とし、本書の確定は Indexer API・Indexer 設計書・PD 由来の整合要件と、ユーザー回答(Q2)の内容に限る(11.2)。Indexer 設計書の「案(実装で採用中)」は案のまま扱う。数値は「仮値・設定可能・未決」とする。

区分の凡例(Indexer 設計書に合わせる):

| 区分 | 意味 |
| --- | --- |
| 確定 | ユーザーが確定した事項(出典を書く) |
| 案 | ユーザー未確定。確定扱いにしない |
| 未決 | 決めていない |
| 推測 | 根拠が弱い想定。推測と注記した事項 |
| 導出 | 他の仕様から導いた事項(明示された記述がなく、本書で導いた事項) |

ID 体系: 本書の確定・案・未決は `CI-K-n` / `CI-P-n` / `CI-U-n`。既存設計との不整合は `I-n`(本書の予約範囲は I-10〜I-19。I-1〜I-6 の所在は 11.5)。

関連文書:

| 文書 | 内容 | 本書との関係 |
| --- | --- | --- |
| `indexer/indexer-api-v0.10.md` | Crawler -> Indexer の契約。3.3(ID と入力の検証)、4.3(バッチ登録)、4.9(原本サイズ超過) | 契約は再掲せず参照する |
| `indexer/indexer-architecture-v0.10.md` | Indexer の設計(K58・K59・K65・K66 ほか) | 同上 |
| `apps/indexer/README.md` 6章、`apps/indexer/src/loreley_indexer/documents/` | Indexer 実装の Crawler 向け確認事項と、`document_id` 算出・抽出の実装 | 実装の事実の確認元 |
| `crawler/crawler-architecture-v0.2.md` | ジョブ、ロック、リトライ・スキップ、登録結果の集計、Indexer との連携 | 本書の範囲外。本書はエラー分類名と「リトライ可否の属性」までを定める |
| `crawler/connector/connector-file-system-v0.2.md` | FS 固有の設定・列挙・取得 | 本書は抽象のみ |
| `crawler/connector/connector-web-v0.2.md` | Web の概要 | 9章の対応表に Web 概要の確認結果を反映した |
| `crawler/crawler-design-decisions-v0.1.md` | 実装着手のための決定事項の要約(採用方針、ユーザー確定事項、実装着手を妨げる未決、実装者が決めてよい事項) | 要約で、詳細は本書と各設計書が正 |
| `crawler/crawler-module-structure-v0.2.md` | Crawler のモジュール分割と依存・呼び出しの流れ | 本書の型・共通処理・`ConnectorType` の配置を実装に落とす。本書の申し送りへの回答は同書 7.6 |

決定事項の出典として、SD v0.8(3.1)と PD v0.19(4.1、4.2)を参照した。SD v0.8 は廃止予定のため、本書は自文書で完結させ、SD への参照は出典の注記にとどめる。

---

## 1. 位置づけと前提

### 1.1 範囲

- 本書が定める: Connector の操作と戻り値、列挙の契約、文書メタデータ、識別子規則、エラー分類名と属性、設定の責務境界。
- 本書が定めない(参照のみ):
  - ジョブ状態、ロック・リース、リトライ回数・バックオフ、スキップ、連続 20 件の打ち切り、登録結果の集計、Indexer 呼び出し(crawler-architecture)
  - FS・Web 固有の設定・列挙・取得(各 Connector 文書)
  - Python の型・モジュール配置(crawler-module-structure)

### 1.2 前提

- MVP は単一ホスト・単一 Crawler・単一 Indexer・直列実行・認証なし。MVP の Connector は FileSystem のみ、Web は将来(PD v0.19 4.1)。
- データソース(`source_id`)ごとに Connector は 1 つ。同一ジョブ内で同じ Connector インスタンスの操作は同時に実行されない(導出。直列実行から)。
- `document_id`・`content_hash` などの形は Indexer API の契約に合わせる(Indexer の既存設計と矛盾する場合は仕様を変えず、I-n として記録する)。

### 1.3 本書が正本となる事項

`external_id` 規則、`document_id` 算出、`content_hash`、エラー分類名。他文書は参照のみとする。

### 1.4 設計原則(導出)

1. **列挙と取得を分離する**。Indexer API は、見つけた文書の `last_seen_at` 更新を「取得より前」に要請させる(`indexer-api-v0.10.md` 2章)。列挙結果(`external_id`)だけで ID を決められる必要がある。
2. **列挙の完了を明示させる**。列挙が一部でも欠けたまま「完了」とすると、欠けた文書が存在しない扱いになり誤削除につながる(SD v0.8 3.1 の列挙中のエラーの方針)。
3. **Connector は Indexer・ジョブ・ロックを知らない**。依存は Crawler 本体 -> Connector の一方向。
4. **FS 固有・Web 固有の都合を共通部分に持ち込まない**。差は `connector_config` と各 Connector 文書に閉じる。

---

## 2. 用語

| 用語 | 意味 |
| --- | --- |
| データソース | `source_id` で識別される文書の取得元。設定(`connector_type`・`connector_config` ほか)を持つ |
| Connector | データソースの列挙と取得を行う部品。`connector_type` で実装が決まる(FS・Web) |
| 文書参照(`DocumentRef`) | 列挙が返す 1 件分の参照。取得に必要な情報を含む |
| 列挙 | データソースの対象文書をすべて見つけること |
| 取得 | 文書参照から原本(抽出前のバイト列)とメタデータを得ること |
| 原本 | 抽出前のデータ。Indexer のバッチ登録の `raw_content`(検索インデックスの `content` とは別物) |
| 共通処理 | Crawler 本体側の、Connector 呼び出しの結果の処理。識別子の正規化・検証、孤立サロゲートの処理、`document_id` 算出、`content_hash`・`size` の導出、列挙の重複除去と衝突検出、想定外の例外の変換(3.2)。全 Connector で 1 つの実装を使う |

---

## 3. Connector の抽象

### 3.1 責務の分担

| 責務 | 担当 |
| --- | --- |
| `connector_config` の検証(構文・型・値域・項目間の整合) | Connector |
| 文書の列挙(対象範囲の絞り込みを含む) | Connector |
| 文書の取得(原本とメタデータ) | Connector |
| `external_id` の組み立て(規則適用前の値) | Connector |
| `external_id` への規則の適用と検証(5.1)、孤立サロゲートの処理、`document_id` 算出、`content_hash`・`size` の導出、列挙の重複除去と衝突検出 | 共通処理(案。CI-P-2、CI-P-3、CI-P-10) |
| 取得の上限値(`max_bytes`)の決定と Connector への受け渡し | 共通処理(設定値を渡す。案。CI-P-14) |
| エラーの分類と属性の付与(6章)。識別子由来のエラー(`invalid_external_id`・`external_id_collision`)は共通処理が付与する | Connector / 共通処理 |
| リトライ・スキップ・ジョブ `failed` の判断 | Crawler 本体(crawler-architecture) |
| ロック・リース更新、Indexer との通信、登録結果の集計 | Crawler 本体(同上) |

- Connector は内部でリトライしない(案。CI-P-5)。リトライ回数の規則を Crawler 本体に一本化するため(SD v0.8 3.1 は取得の失敗を Crawler 自身がリトライ・スキップすると定める)。リクエスト間隔の制御のような待機(ペーシング)は、リトライとは別に Connector 内部で行ってよい。Web で列挙中の一時失敗を吸収できない問題があり、この方針の見直しの要否は CI-U-11。
- Connector の操作は、Crawler 本体のリース更新(ハートビート)を妨げない形で呼べること(導出。同期 HTTP 待ち中もリース更新を途切れさせない要件の延長。ブロッキング呼び出しの扱いは module-structure で決める。CI-U-9)。

### 3.2 操作(言語非依存の疑似シグネチャ)

```
ConnectorType                                  # connector_type ごとに 1 つ(8章)
  validate_config(connector_config) -> ok | raise ConnectorError(config_invalid)   # I/O をしない
  create(source_id, connector_config) -> Connector | raise ConnectorError

Connector
  enumerate() -> EnumerationStream             # 3.3
  fetch(ref: DocumentRef, max_bytes: integer) -> FetchedDocument | raise ConnectorError   # 7章。何度でも呼べる
  close() -> void                              # 接続・ハンドルなど保持している資源の解放

EnumerationStream
  next() -> DocumentRef | Completed | raise ConnectorError   # 送出が列挙の Failed(3.3)
  close() -> void                              # 列挙だけを打ち切る(Connector は fetch に使い続けられる)

DocumentRef                                    # 列挙の 1 件
  external_id : string                         # 規則適用前の値(5.1)
  locator     : opaque                         # Connector が fetch で再解決に使う。本体は中身を見ない
  size_hint   : integer?                       # 取得前に分かる原本サイズ(任意。7章)

FetchedDocument                                # 取得の結果
  content  : bytes                             # 原本の全体
  metadata : DocumentMetadata

DocumentMetadata                               # 4章
  title : string, mime_type : string, source_updated_at : datetime(タイムゾーン付き),
  path : string?, url : string?

ConnectorError { category: 6.2 の分類名, scope: source|document, retry: transient|permanent|unknown, message: string }   # message の内容は 6.1
```

(案。CI-P-6、CI-P-8、CI-P-14。型の表記は説明用で、Python への落とし込みは module-structure。)

- **失敗の表現**: 操作の失敗は `ConnectorError` の送出で表す。`next()` が送出した場合を、列挙の `Failed` と呼ぶ。`create`・`validate_config` の失敗も同じ(`validate_config` は `config_invalid`、`create` はその他の該当分類)。
- **想定外の例外**: `ConnectorError` 以外の例外が Connector から出たとき、共通処理が `connector_internal_error`(6.2)に変換する(案。CI-P-12)。変換の主体を共通処理にするのは、Connector 実装ごとの変換漏れで分類のない失敗が出ないようにするため。実装上、`validate_config`・`create` の変換は `ConnectorType` の保護ラッパが同じ変換関数で行ってよい(`crawler-module-structure-v0.2.md` CM-P-7)。論理上は共通処理の責務。
- **2 層(`ConnectorType` / `Connector`)にする理由**(案): データソース設定の登録・更新時の検証(crawler-api)を、接続やインスタンスなしで呼べるようにするため。実装上は Connector クラスの静的関数でもよい(module-structure)。
- **`close()` が 2 つある理由**(案): 列挙だけを打ち切って(取り消し・異常時)、同じ Connector で取得を続ける場合があるため。
- **`size_hint` の位置づけ**(案): 取れれば、上限超過を読む前に先行判定できる補助情報(7章)。Crawler 側の `oversize` 拒否の方式が決まるまで(CI-U-3)は任意項目で、省略してもよい。
- 列挙開始前の事前確認(接続・起点の存在)を行う操作は置かない(CI-P-9。要否は CI-U-6)。

### 3.3 列挙の契約

1. **終端**: 列挙は 0 件以上の `DocumentRef` のあと、必ず `Completed` か `Failed`(`next()` による `ConnectorError` の送出)のどちらか 1 つで終わる。終端なしで途切れた列挙(本体が `close()` した、プロセスが終了した)は完了とみなさない(案。CI-P-7)。
2. **完全性**: `Completed` を返してよいのは、列挙の対象範囲内の文書を取りこぼしなく返したときだけ。列挙の開始から `Completed` までの間ずっと存在し続けた文書は、必ず返す(導出。1.4 の 2)。対象範囲の定義は Connector が与える。範囲がデータソースの内部構造(参照関係など)に依存する場合は、到達可能性を範囲の定義に含める(導出。I-41)。一部でも列挙できなかったときは `Completed` にせず `Failed`(`enumeration_incomplete`。6章)にする。
3. **過剰は許容**: 列挙したあと取得までに消えた文書は、取得側で `fetch_not_found`(6章)になるだけで、列挙の違反ではない。列挙は原子的なスナップショットではない(導出)。
4. **対象範囲**: 設定による包含・除外で対象外とした文書は、列挙しない。対象外の文書には、`last_seen_at` の要請も `enumerated_count` への算入もない(FS の列挙対象についてのユーザー回答 Q2。CI-K-7。他の Connector への一般化は導出)。結果として、設定変更で対象外になった文書は列挙されず、期限削除の対象になりうる(導出。扱いは Indexer の削除判断)。
5. **重複と順序**: 同じ文書を複数回返してよい(共通処理が `document_id` で除く。5.3)。返す順序は規定しない。
6. **ストリーミング**: `next()` で 1 件ずつ返す。Connector は `DocumentRef` を全件保持しなくてよい(許容規定。保持しないことの検証は 10章 #8。導出)。Crawler 本体は受け取りながら `last_seen_at` の要請をバッチ化できる。全件を一括で得る実装も、`EnumerationStream` に包めば適用できる。共通処理は重複除去・衝突検出のために ID の集合を保持する(CI-U-10)。
7. **列挙と取得の独立**: `fetch` は、列挙が終わる前でも、返された `DocumentRef` に対して呼べる(呼ぶ順序は architecture が決める)。列挙は文書の内容の読み取りを要求しない(読んでもよいが、取得とは別の操作として扱う)。列挙中に得た内容の再利用は Connector 内部の最適化で、インタフェースには出ない。

---

## 4. 文書メタデータ

Connector が決める値と、Indexer のバッチ登録 `documents[]`(`indexer-api-v0.10.md` 4.3)の項目との対応。項目の意味・必須は 4.3 を正とし、ここでは Connector 側の責務だけを書く。

| 項目 | 得る時点 | 型 | 必須 | 備考 |
| --- | --- | --- | --- | --- |
| `external_id` | 列挙 | string | ○ | 5.1 の規則。ID の責務で、`url`・`path` とは別(K44。CI-K-8) |
| `title` | 取得 | string | ○ | 取得できないときの値(例: ファイル名)は各 Connector 文書で定める(CI-U-8) |
| `mime_type` | 取得 | string | ○ | 下記の注記 |
| `source_updated_at` | 取得 | datetime | ○ | タイムゾーン付き(オフセットなしは Indexer が全体 400。K59)。Indexer が UTC・ミリ秒精度に正規化する(案。`indexer-api-v0.10.md` 3.6) |
| `path` | 取得 | string | 任意 | データソース内の文書パス(表示・位置の情報。`external_id` とは別。K44)。検索・絞り込みへの使用と最大長は Indexer 側で未決 |
| `url` | 取得 | string | 任意 | アクセス可能な原文の URL(K44)。持たない Connector(FS)は渡さない |
| `size` | 導出 | integer | ○ | 共通処理が、送る原本のバイト数(0 以上)として設定する(5.4) |
| `content_hash` | 導出 | string | ○ | 共通処理が算出する(5.4) |

- `mime_type` の語彙(導出): Indexer の抽出(`apps/indexer/src/loreley_indexer/documents/extraction/extractor.py`)が対応する基準 MIME は、`text/plain`、`text/markdown`、`text/x-markdown`、`text/html`、`application/pdf`(`;` 以降のパラメータを除き小文字にして比較する)。これ以外は抽出に失敗し、Indexer が `unsupported_mime_type` の `extract_failed`(タイトルとメタデータの登録)として扱う(README 6章)。したがって Connector が渡す MIME の語彙は Indexer の対応形式に依存し、拡張子などとの対応表は FS 文書で定める。Connector は対応外の MIME を理由に文書を拒否しない(案。CI-P-16)。
- `last_seen_at` は項目に含まれない(Crawler は `crawl_started_at` を渡し、Indexer が書く。`indexer-api-v0.10.md` 4.3)。
- 原本の取得日時(`fetched_at`)と Connector 固有の追加属性(`metadata`)は MVP では保存せず、`documents[]` に含めない(確定。K45。CI-K-8)。Connector はこれらを返さない。
- `title`・`mime_type`・`path`・`url` に孤立サロゲートが入ると、その文書は Indexer で文書単位の `document_rejected` になる(K59)。リトライしても直らないため、共通処理が送る前に 5.1 の表示用置換を適用する(案。CI-P-10)。
- メタデータは取得時に、読み取った内容と同じ読み取りで得る(導出)。内容とメタデータの整合(7章)を保つため。

---

## 5. 識別子規則

### 5.1 `external_id`

意味: データソース内で文書を一意に識別する値。同じ文書は(設定が変わらない限り)クロールをまたいで同じ値になる。パスの変更・リネームは「旧 ID の削除 + 新 ID の追加」になり、追跡しない(確定。`indexer-api-v0.10.md` 3.3。CI-K-9)。

Indexer に送る最終形が満たす規則:

| # | 規則 | 区分・出典 |
| --- | --- | --- |
| 1 | Unicode NFC に正規化する | 確定(`indexer-api-v0.10.md` 3.3。CI-K-2) |
| 2 | パス区切りは `/` に統一する(ルートからの相対パス)。`\` は `/` に置き換える | `/` への統一は確定(同上。CI-K-2)。`\` の置換は案(Indexer 実装 `document_id.py`・README 6章が行う。`indexer-api-v0.10.md` 3.3 は「パス区切りを `/` に統一」とだけ書き、`\` を明示しない。I-10。CI-P-1) |
| 3 | 先頭に `/` を付けない。Indexer は先頭の `/` を除去しない(`/a` と `a` は別 ID になる) | 確定(K58。Crawler が渡す値の前提。CI-K-2) |
| 4 | 大文字小文字を区別する(変換しない) | 確定(`indexer-api-v0.10.md` 3.3) |
| 5 | 空文字にしない。NUL を含めない。UTF-8 で 4096 バイト以内。改行・タブは許可 | 規則は確定(K59。CI-K-3)、4096 は検証規則としての仮値(Indexer 実装が置いた) |
| 6 | 孤立サロゲートを含めない。含めば Indexer はバッチ全体を 400 にする(再送しても直らない) | 確定(K59。CI-K-4) |

- **規則 2 の `\` の置換は事実上必須**(導出): Crawler が置換しないと、`\` を含む名前では、Indexer 実装が置換して算出する `document_id`(バッチ登録の応答)と、Crawler が算出する `last-seen` の `document_id` が食い違う。規則自体の是非は Indexer 設計の課題(I-10)で、本書は決めない。
- **分担と適用順序**(案。CI-P-2): Connector は規則適用前の値を `DocumentRef.external_id` に入れる。共通処理が次の順に処理する。
  1. 孤立サロゲートを下記の ID 用エスケープで置き換える(規則 6 を満たす。以降の処理が孤立サロゲートを扱わないよう最初に行う)
  2. NFC に正規化する(規則 1)
  3. `\` を `/` に置き換える(規則 2)
  4. 検証する: 規則 3(先頭が `/` でない)と規則 5。適合しなければ `invalid_external_id`(6章)
  - 先頭の `/` は除去せず `invalid_external_id` にする(案。CI-P-15)。除去すると `/a` と `a` が同じ文書になるため。手順 3 の置換後に先頭が `/` になるもの(例: 先頭が `\` のファイル名)も同じ。
  - Indexer が検証するのは受け取った値で、その後 NFC と `\` の置換を行うだけなので、送る値は手順 3 までの適用後の値にする(適用は冪等)。
- **孤立サロゲートの処理**(案。CI-P-10)は共通処理が一律に適用する(MVP で実装を 1 つにするため)。発生状況(Linux でファイル名を CP932 などで読んだ場合など)の説明は FS 文書が行う。
  - **ID 用エスケープ**(`external_id`): 孤立サロゲート 1 文字(U+D800〜U+DFFF)を、U+FFFD + `u` + 4 桁の大文字 16 進に置き換える(例: U+DC80 -> U+FFFD,`u`,`D`,`C`,`8`,`0`)。入力中の U+FFFD 1 文字は U+FFFD 2 文字に置き換える。性質: 決定的(同じ入力は常に同じ出力)、単射(導入文字自体をエスケープするため、別の入力が同じ出力にならない)、`\` と NUL を含まない。エスケープ文字列の各文字は NFC で不変(ただし文脈によっては後続の結合文字と合成されうる。例: 末尾の 16 進文字 `E` + U+0301。単射性は保たれる)。順序(エスケープ -> NFC -> 送信)を守れば、Indexer の NFC は冪等で、送る値と算出値は一致する。
  - **表示用置換**(`title`・`path`・`url`・`mime_type`): 孤立サロゲート 1 文字を U+FFFD 1 文字に置き換える。表示用で、単射は求めない。
  - 方式の細部(導入文字の選択など)は案で、見直しは本書(共通処理)の改訂で行う。
- 孤立サロゲートの除去(削除するだけ)は採らない。別名のファイルを同じ `external_id` にしやすいため。

### 5.2 `document_id`

```
document_id = SHA-256( source_id + "\0" + external_id(5.1 の最終形) ) の小文字 16 進(64 桁)    # CI-K-1
```

- 文字列を UTF-8 でバイト列にして計算する。`\0` は NUL。`source_id` は正規化しない(Indexer 実装のテストで確認。導出)。`source_id` と `external_id` に NUL を含む入力は計算しない(Indexer 実装も拒否する)。
- 算出主体(確定。K66、`indexer-api-v0.10.md` 4.2・4.4。CI-K-6): `last-seen` の `document_ids`、終了通知の `skipped_document_ids`・`oversize_document_ids` は、Crawler が算出した値。バッチ登録では、Indexer が同じ規則で算出して応答に返す。
- バッチ登録の `documents[]` の項目に `document_id` はなく(`indexer-api-v0.10.md` 4.3 の項目表。項目名・型は案)、Indexer は Crawler の値との照合をしない(同 4.3 の「照合しない提案」)。そのため、Crawler と Indexer の算出がずれても Indexer 側では検出されない。
- 二重実装対策(`indexer-api-v0.10.md` API-U-7 の未決部分): 案は次の 2 つ(CI-P-4)。最終の採否と、共有ライブラリの要否は未決(CI-U-1)。
  1. 共有テストベクタ: 入力と期待 ID の組(下記)を Crawler のテストにも置く。
  2. 実行時の照合: バッチ登録の応答の `document_id` を、Crawler が自分の算出値と比べる。不一致時の扱いは architecture が決める。

サンプルベクタ:

| `source_id` | `external_id` | `document_id` | 出典 |
| --- | --- | --- | --- |
| `src-docs` | `page-10023` | `6b5851d90534fc00e388eeb8bd8c79ae48b8bf5c58e4fb0191e708afa28674d7` | `indexer-api-v0.10.md` 4.3 の応答例。`API_EXAMPLE_VECTORS` と一致 |
| `src-docs` | `page-10024` | `7f2216b2a91e74fe53ce071ed0bd8dcebccaa904f9a8d8004f592b0a4210a9c5` | 同上 |
| `src-docs` | `page-10025` | `48ea91b73f76334d8cf88f6a77438e740ba9d54a338970ad1433aa2f504c2c40` | 同上 |
| `src-fs` | `docs/guide.md` | `62a016d377e1f1d16870407d482a404dbd18891784a35825ec5bee062386501f` | 導出 |
| `src-fs` | `/docs/guide.md`(先頭に `/` あり) | `805b7b88bf1762ed070e57e377bb5be133f124c163f227edd9e810e07912ae91` | 導出。上の行と別 ID になる(K58)。`document_id` 算出関数への直接入力で、共通処理は通さない(通すと `invalid_external_id`) |
| `src-fs` | `Docs/Guide.md`(大文字小文字違い) | `7ee0706f071514209f89045c27777064068ac4720c7d1aa3ff5923eec0934881` | 導出。別 ID になる |
| `src-fs` | `資料/がぎ.txt`(NFC)。NFD の入力でも同じ | `61333b3265b1d26d226ced9296e0e072de607e1e7a09f84ff797de59bfb2738f` | 導出。NFC に正規化してから計算 |
| `src-fs` | `a\b.txt` と `a/b.txt` | `acf087b56a18acd68b1b30209882aaa1a42c6cf2000f423c8982a227ec80f83d`(両方同じ) | 導出。5.3 の衝突の例 |

- 上の 3 行は、`indexer-api-v0.10.md` の応答例・`apps/indexer/tests/documents/test_document_id.py` の `API_EXAMPLE_VECTORS` と、本書の算式の計算が一致することを 2026-11-13 に確認した。
- 「導出」の行は、本書が算式で計算し、Indexer の `compute_document_id`(`document_id.py`)の出力と一致することを同日に確認した。Indexer のテストには含まれない。共有テストベクタに採る場合は、Indexer 側のテストにも置くかを決める(CI-U-1)。

### 5.3 衝突

異なる 2 つの文書が同じ `document_id` になる場合がある(`apps/indexer` の実装を前提とした確認結果)。

- (a) `\`: Indexer 実装は `\` を `/` に置き換える。Linux では `\` はファイル名として使えるため、ルート直下の `a\b.txt` と、ディレクトリ `a` の中の `b.txt` が同じ `external_id`(`a/b.txt`)になる(上の最終行)。Linux の挙動は推測(実機未確認)。
- (b) NFC: Linux ではファイル名はバイト列で、NFC と NFD の異形が別ファイルとして共存しうる(推測。一般的な挙動で、実機未確認)。両者は NFC 後に同じ `external_id` になる。

衝突すると、2 件が同じ ID の 1 文書として扱われ、登録のたびに内容が入れ替わりうる。`enumerated_count` は `document_id` で重複を除くため件数の整合は崩れない(導出)。この衝突は Indexer の既存設計(`indexer-api-v0.10.md` 3.3 の規則と実装)から生じるため、Indexer 側の規則を本書で変えず、I-10 として記録する。

- 検出: 共通処理が、同じ列挙内で `document_id` が重複しつつ元の `external_id`(規則適用前)が異なるものを検出できる(導出。保持量は CI-U-10)。
- 検出時の扱い(ジョブ `failed` にするか、後に来た文書を分類 `external_id_collision` として扱うか)は architecture と合わせて決める(CI-U-2)。

### 5.4 `content_hash` と `size`

- `content_hash` = 送る原本のバイト列全体の SHA-256。小文字 16 進 64 桁(確定。K59、K66。CI-K-5。大文字は Indexer がバッチ全体を 400 にする)。Indexer は再計算も照合もしない。
- 共通処理が、バッチに載せるバイト列から算出する(案。CI-P-3)。算出元と送るバイト列を同じにするため。取得後にファイルが変わっても、ハッシュは送った内容と必ず一致する。0 バイトの原本のハッシュは `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`(`size` は 0。0 以上は有効)。
- `size` も同じバイト列の長さ(バイト)とする(案。CI-P-3)。
- 対象は原本であり、抽出後の本文・メタデータではない。変更なしの判定への使われ方は Indexer の領域(`indexer-api-v0.10.md` 4.3)。

---

## 6. エラー分類

### 6.1 属性

| 属性 | 値 | 意味 |
| --- | --- | --- |
| `scope` | `source` | データソース全体に影響する。列挙の完全性や継続を保証できない |
| | `document` | その文書だけに影響する |
| `retry` | `transient` | 再試行で直りうる |
| | `permanent` | 再試行しても直らない |
| | `unknown` | 判断できない |

- 属性は Connector(識別子由来のものは共通処理)が付ける事実情報で、本書が定めるのはここまで。リトライの回数・バックオフ、スキップするか、連続 20 件の打ち切り、ジョブ `failed` にするかは architecture が正本(参照のみ)。SD v0.8 3.1(案)は、`permanent` も区別せず同じ回数を試すとしており、属性を使うかも architecture が決める。
- **説明文(`message`)**(案。CI-P-17): 固定文に加えて、管理者が原因を特定できる情報(errno 名、切り詰めた相対パスや識別子)を含めてよい。文書の本文・認証情報は含めない。長さは切り詰める(上限は architecture の仮値に従う)。architecture の `failure_detail`(3.3.1・4.8)へ説明文を載せる扱いは architecture が定める(参照のみ)。識別子に秘密情報が含まれうる場合の除去は各 Connector 文書で定める。
- 各分類の `scope` と `retry` は、発生点ごとに 1 つに定まる(下表)。

### 6.2 分類名(案。CI-P-6)

| 分類名 | 発生点 | `scope` | `retry` | 意味 |
| --- | --- | --- | --- | --- |
| `config_invalid` | `validate_config`、`create` | source | permanent | `connector_config` が規則に違反している |
| `source_unreachable` | 列挙、`create`(接続を伴う場合のみ) | source | transient | データソースに到達できない(接続不可、タイムアウトなど。マウント外れを本分類(transient)と `source_not_found`(permanent)のどちらにするかの判定は FS 文書に委ねる) |
| `source_not_found` | 列挙、`create`(接続を伴う場合のみ) | source | permanent | データソースの起点(FS のルートなど)が存在しない |
| `source_access_denied` | 列挙、`create`(接続を伴う場合のみ) | source | permanent | 起点に対する権限・認証がない |
| `enumeration_incomplete` | 列挙 | source | unknown | 起点には到達したが、一部を列挙できず完全な列挙を保証できない(配下の権限エラー、途中の読み取りエラーなど) |
| `fetch_not_found` | 取得 | document | permanent | 列挙後、取得までに文書が消えた・見つからない |
| `fetch_permission_denied` | 取得 | document | permanent | 取得に必要な権限がない |
| `fetch_transient` | 取得 | document | transient | 一時的な読み取りエラー、タイムアウト、取得中の変更による不整合など |
| `oversize` | 取得 | document | permanent | 原本が `max_bytes` を超える(7章) |
| `invalid_external_id` | 識別子(共通処理) | document | permanent | 5.1 の規則 3 または 5 に適合しない(先頭が `/`、空、NUL、4096 バイト超) |
| `external_id_collision` | 識別子(共通処理) | document | permanent | 同じ `document_id` になる別の文書がある(5.3。扱いは CI-U-2) |
| `connector_internal_error` | 列挙・`create`・`validate_config` | source | unknown | 上記に分類できない想定外の例外 |
| `connector_internal_error` | 取得 | document | unknown | 同上 |

- 分類名のうち `oversize` は、Indexer のバッチ登録の `failure_type: oversize`(`indexer-api-v0.10.md` 4.3、4.9。Indexer が仮に置いた名前で案。API-U-24、I-5)と同名にする。Crawler 側の拒否と Indexer 側の拒否を記録上同じ種別で扱うため(案。CI-P-11)。名前は Indexer 側と合わせて再確認する。
- **`connector_internal_error` の `scope`**(案。CI-P-12): 列挙時などは、列挙の完全性を保証できないため source とする。取得時は、`last_seen_at` が列挙時に更新済みで、その文書の失敗が他の文書の削除判断に影響しないため document とする(SD v0.8 3.1 の発見と取得の分離の考え方。導出)。連続して起きた場合の打ち切りは architecture が決める。
- **列挙の `Failed` は `scope=source` のみ**(導出): 列挙は途中で 1 件ごとの失敗を返さず、`DocumentRef` を返すか、列挙全体を `Failed` にするかのどちらか。識別子由来の document スコープの失敗(`invalid_external_id`・`external_id_collision`)は、列挙結果を受け取る共通処理が付与し、`invalid_external_id` の文書は以降の処理(`last_seen_at` の要請・取得)に進めない(`document_id` を算出できないため。記録方法は CI-U-4)。`external_id_collision` の文書の扱いは CI-U-2(未決)で、処理フローは architecture の領域。
- 文書単位の取得の失敗は、取得で起きる(取得系の分類)。

### 6.3 Indexer 由来の文書単位結果との関係

Indexer のバッチ登録が返す失敗種別(`document_rejected`・`oversize`・`lock_not_owned`・`write_conflict`・`update_conflict`)は Indexer の契約で、本書は定義も改名もしない(`indexer-api-v0.10.md` 4.3、README 6章)。Connector のエラーではなく、Crawler 本体が Indexer 応答から受け取る結果である。扱いは architecture が正本。

---

## 7. 取得の契約

- 入力は列挙が返した `DocumentRef` と `max_bytes`。出力は `FetchedDocument`(原本の全体とメタデータ)。MVP は参照ではなく原本そのものを渡す(`indexer-api-v0.10.md` 4.3。確定の記述)。
- 読み取り専用で、原本を変更しない。同じ `DocumentRef` に何度でも呼べる(リトライのため。呼ぶたびに読み直す)(導出)。
- メタデータは、返す内容と同じ読み取りで得た値とする。取得中に原本が変化し、内容とメタデータの整合を保証できないときは `fetch_transient` にする(案)。
- 取得結果は原本全体をメモリに持つ(Indexer API が JSON + base64 で運ぶため。運び方は Indexer 側で未決。API-U-17)。運び方が変われば、ストリーム取得を再検討する(MVP では扱わない)(導出)。
- **サイズ上限**:
  - Crawler 側でも、上限を超えた原本を拒否する(Indexer との二重防御)。実施すること自体は確定(PD v0.19 4.2、`indexer-architecture-v0.10.md` K65。ユーザー承認 2026-11-11。CI-K-10)。
  - 方式(案。CI-P-14): 上限値は Crawler の設定 `max_raw_bytes`(architecture 6.5。仮値・設定可能・未決)とし、Indexer 側の上限 `MAX_RAW_BYTES`(`apps/indexer/README.md` 3章。原本 1 件の上限・デコード後)と整合させる(両者は別の設定。Crawler の値が Indexer の上限を超えていないかは、Crawler の起動時に検査する案。architecture CA-P-55)。共通処理が `fetch` の `max_bytes` として渡す。Connector は、読み取り中に `max_bytes` を超えた時点で中断し(全体を読み込まない)、`oversize` を送出する。`size_hint` が取れれば、読む前に超過を先行判定できる(補助。使うかは CI-U-3)。
  - 未決(CI-U-3): 上限値、`size_hint` による事前判定の要否、記録先・項目、ジョブ status への影響、`oversize_document_ids` への載せ方。
- 拒否した文書は Indexer に送られないため、新規文書(索引にない)の ID を終了通知の `oversize_document_ids` に載せないと、件数照合が合わず削除されない(導出。`indexer-api-v0.10.md` 4.9 の件数照合の案)。載せ方は architecture が決める。
- 既存設計の記述の食い違いがある(I-11)。
- `content_hash`・`size` は 5.4 のとおり共通処理が導出するため、`FetchedDocument` に含めない。

---

## 8. 設定の扱い

- `connector_type` は Connector の実装を選ぶ識別子(例: FS、Web。値の綴りは architecture と各 Connector 文書が定める)。`ConnectorType` が `connector_type` ごとに 1 つ登録される(案)。
- `connector_config` は、`loreley-sources` の共通項目とは別の、Connector 固有の設定。architecture と crawler-api は中身を定義せず不透明に扱い、項目の定義と検証は各 Connector 文書と Connector が持つ(作業プラン 2.2 の前提。案)。
- 検証(`validate_config`): 構文・型・値域・項目間の整合までで、I/O をしない(接続確認はしない。CI-P-9、事前確認の要否は CI-U-6)。呼び出しは、データソース設定の登録・更新時(crawler-api)と、ジョブ開始時(保存済み設定の確認)を想定する(案)。
- ジョブ内では、開始時点の `connector_config` を使い、実行中に変わらない前提(案)。architecture 4.5 の手順 6 が `loreley-sources` を 1 度だけ読んで `connector_config` を確定し(メモリ上の実行コンテキストだけに持つ。ジョブ記録には保存しない)、手順 8 の `validate_config`・`create` はその値を使う(案。CA-P-51)。この案では、手順 6 より後に設定を更新しても、そのジョブの Connector には反映されない。保持の詳細は architecture が決める。
- 共通項目(`ttl`・`ratio_threshold` など)は `connector_config` に含めない。範囲の検証は Admin API 側(`indexer-architecture-v0.10.md` K10)。
- `external_id` の導出に影響する項目(例: FS のルート)を変えると、文書の同一性が変わりうる(導出)。変更時の扱いは各 Connector 文書で定める。
- 認証情報は設定に直接書かず参照名で持つ(SD v0.8 の方針。案)。解決の仕組みは FS では不要で、Web 文書で扱う(CI-U-7)。

---

## 9. FS / Web への適用性

`connector-web-v0.2.md` 4章(Web 概要での適用結果)を反映した対応表。Web の列は Web 概要の想定(推測を含む)で、確定ではない。Web 固有の事情の詳細は Web 文書が持つ。

| インタフェース要素 | FS(MVP) | Web(将来。推測) | 適用 / 論点 |
| --- | --- | --- | --- |
| `external_id`(5.1) | ルートからの相対パス | 正規化した URL | 適用可。規則 5 の長さ(4096 バイト)は URL で通常収まる想定。`\` の置換は FS で衝突し(I-10)、URL では通常現れない(`%5C`)。URL の正規化は Connector が組み立て時に行う(Web 文書 2.2) |
| 列挙の完全性(3.3 の 2) | ディレクトリの再帰走査。読めなければ `enumeration_incomplete` で検知できる | リンク探索・サイトマップ。リンクで到達できない文書は返せない | **論点 A**: 範囲の定義を Connector が与える必要があり、3.3 の 2 に補足した(I-41)。範囲の案(設定した起点と範囲から到達可能と判定できた集合)と判定表は Web 文書 3.3(Web 側の案・未決) |
| 列挙と取得の分離(1.4 の 1) | 列挙は内容を読まない | リンクの発見に本文の取得が要る | **論点 B**: 変更不要(3.3 の 7)。ただし訪問済み集合・未処理の待ち行列の保持量は 10章 #8 の趣旨に関わる(I-42)。二重取得にするか有界の保持にするかは Web の詳細設計(Web 文書 CW-U-14) |
| ストリーミング列挙(3.3 の 6) | 走査しながら返す | 探索しながら返す | 適用可(保持量は I-42 のとおり) |
| `DocumentRef.locator` | 相対パス | URL と取得条件 | 適用可 |
| `size_hint`、`max_bytes` | ファイルサイズで事前判定、読み取り中も判定 | `Content-Length`(ないことがある)。読み取り中の判定で補える | 適用可(`size_hint` は任意項目) |
| `title` | ファイル名など(FS 文書) | HTML の `<title>` など | 取得時に得るため適用可 |
| `path` / `url` | `path` あり、`url` なし | `url` あり、`path` は未定 | 任意 2 項目で適用可 |
| `mime_type` | 拡張子から(FS 文書) | `Content-Type` | 適用可。Indexer の対応語彙に依存し、対応外は Indexer が `extract_failed`。CI-P-16 と範囲絞り(3.3 の 4)の関係、Indexer の文字コード対応(I-44)は Web の詳細設計で確認 |
| `source_updated_at` | `mtime`(FS 文書 5.4) | `Last-Modified`(ないことがある) | **論点 C**: 本書の変更は不要。値の方針は未決(CI-U-5。Web 文書 CW-U-10) |
| `content` / `content_hash` / `size` | ファイルの全体 | レスポンスボディ(レンダリングの要否は Web 文書) | 共通処理の導出で適用可 |
| エラー分類(6章)、`message` | `fetch_permission_denied` など | 分類名は 6.2 のものだけで足りる見込み(想定対応は Web 文書 4.4)。失敗した URL の診断情報は、`message` の緩和(6.1。CI-P-17)で載せられる | 適用可。robots・TLS・リダイレクト異常などの帰属は Web 文書(CW-U-18) |
| リトライ(3.1、CI-P-5) | 本体 | 本体。列挙中の取得の一時失敗が列挙全体の失敗になる | **論点 D / I-40**: ペーシングは Connector 内部で許せるが、429 の同じ要求の再送はリトライに当たる。列挙中の一時失敗の扱いは契約の設計判断で、CI-U-11 とする(Web の詳細設計の前に判断) |
| 取り消し・リース更新(3.1、3.2) | `close()`、短い呼び出し | `close()`、ネットワーク待ち | 適用可。`close()` の並行呼び出しの可否と `next()` の最大ブロック時間は詳細設計(CI-U-9。Web 文書 CW-U-16) |
| `connector_config`(8章) | ルート、パターンなど | 開始 URL、範囲、認証の参照名など | 不透明で適用可(認証の参照名の解決は CI-U-7。Web 文書 CW-U-6) |
| 並行取得・差分取得 | 直列・全件更新(MVP) | 将来 | 本書は求めない(1.2) |

現時点の結論: Web 概要(`connector-web-v0.2.md` 4章)で確認した結果、本書の要素・操作の構造は Web でも成立する(Web 文書の判定。確定ではない)。残る事項は次のとおり。

- **契約の設計判断(I-40。CI-U-11)**: 列挙中の一時失敗の扱いは、3.1 の CI-P-5 と architecture 6.2 の方針に関わり、Web の詳細設計の前に決める。選択肢は CI-U-11。
- **文言・テスト観点の補足(I-41、I-42)**: 3.3 の 2 と 10章 #8 に補足した。契約の変更は伴わない。
- **I-43**: architecture 7.7 の `warnings` の表示用文字列が `locator` を使う記述と、本書の `locator` 不透明の規定の矛盾。architecture 7.7 で解消済み(本書 3.2 は変更なし)。
- **I-44**: Indexer の文字コード対応(UTF-8・CP932)が Web で顕在化する既存制約。Indexer 設計の課題で、本書は変更しない。
- I-40〜I-44 の定義は `connector-web-v0.2.md` 4.5。

---

## 10. テスト観点

全 Connector 実装が通る共通の契約テストを用意する(案。CI-P-13)。

| # | 観点 | 期待 |
| --- | --- | --- |
| 1 | `document_id` 算出関数のサンプルベクタ(5.2 の全行。共通処理を通さず算出関数に直接入力する) | 期待値と一致する |
| 2 | `external_id` の規則 | NFD 入力が NFC と同じ ID。`\` が `/` として扱われる。大文字小文字が別 ID |
| 3 | `external_id` の検証と孤立サロゲート | 先頭が `/`(`\` 置換後を含む)・空・NUL は `invalid_external_id`(先頭の `/` は除去されない)。4096 バイトは通り 4097 バイトは拒否する(マルチバイトはバイト数で判定)。改行・タブは通る。孤立サロゲートは ID 用エスケープされ、同じ入力は同じ出力になり、出力に `\` を含まない。エスケープ -> NFC の結果を再度 NFC にしても変わらない(冪等)。後続の結合文字との合成(例: `E` + U+0301)があっても、別の入力が同じ出力にならない入力中の U+FFFD と、エスケープ結果が衝突しない |
| 4 | 衝突の検出 | `a\b.txt` と `a/b.txt` を同じ列挙で返したとき、検出される(扱いは CI-U-2) |
| 5 | `content_hash` と `size` | 小文字 64 桁。送るバイト列と一致する。0 バイトの原本で `size`=0 |
| 6 | 列挙の終端 | 完了時は `Completed`。一部を列挙できないとき `Completed` を返さず `Failed`。途中で `close()` したら完了にならない |
| 7 | 列挙の重複 | 同じ文書を 2 回返しても、`enumerated_count` で 1 件に数えられる |
| 8 | ストリーミング | Connector は列挙済みの `DocumentRef` を溜め込まない(3.3 の 6 の許容規定に対して、本項目が保持しないことを期待する側)。大量件数でも `DocumentRef` の保持量が件数に比例しない。重複判定・走査状態のための識別子の集合は除き、その量は CI-U-10(共通処理の ID 集合)と合わせて見積もる(I-42) |
| 9 | 取得 | 同じ `DocumentRef` を 2 回取得できる。原本が変更されない。`max_bytes` を超える原本は、全体を読み込まず `oversize` になる |
| 10 | エラー分類 | 各異常が 6.2 の分類名・属性になる(例: 起点が存在しない -> `source_not_found`・source・permanent。接続不可 -> `source_unreachable`・source・transient。配下の権限エラー -> `enumeration_incomplete`・source・unknown)。想定外の例外は `connector_internal_error`(列挙時 source、取得時 document)。説明文に、原因の特定に足る情報(errno 名・切り詰めた相対パスなど)が含まれ、本文・認証情報が入らない。長さが上限で切り詰められる |
| 11 | `validate_config` | I/O をしない。違反は `config_invalid` |

---

## 11. 確認状況

### 11.1 確認した事実(2026-11-13)

- バッチ登録の `documents[]` に `document_id` の項目はなく、Indexer が算出して応答に返す。Crawler の値との照合はしない(`indexer-api-v0.10.md` 4.3)。
- `last-seen` の `document_ids` と、終了通知の `skipped_document_ids`・`oversize_document_ids` は Crawler が算出する(同 4.2、4.4)。
- Indexer の実装は `external_id` を NFC にし `\` を `/` に置き換えてから算出する。先頭の `/` は除去しない。`source_id` は正規化しない(`document_id.py`、`test_document_id.py`)。
- Indexer の `external_id` の検証(空・長さ・NUL)は、受け取った値(正規化前)に対して行われる(`api/schemas.py`)。
- サンプルベクタは `API_EXAMPLE_VECTORS` と一致する(5.2。計算は作業用の一時領域で行い、リポジトリには残していない)。
- 原本サイズ超過: PD v0.19 4.2 は「取得(Crawler)と登録(Indexer)のどちらでも拒否する(二重防御)」と書く。PD v0.19 9.2 #8 が未決とするのは、利用者への表示方法(エラーの記録先、ジョブ status への影響)。`indexer-architecture-v0.10.md` K65 は「Crawler の送信前の拒否との二重防御」として確定(ユーザー承認 2026-11-11)。一方、`indexer-api-v0.10.md` 4.9 は「Crawler の送信前の拒否の有無」を未決と書く。
- Indexer の抽出が対応する基準 MIME は 4章の注記のとおり(`extractor.py`)。

### 11.2 確定(CI-K)

確定にしたのは、Indexer API・Indexer 設計書・PD 由来の整合要件と、ユーザー回答(Q2)の内容だけ。

| ID | 内容 | 出典 |
| --- | --- | --- |
| CI-K-1 | `document_id` = `SHA-256(source_id + "\0" + external_id)` の小文字 16 進 | `indexer-api-v0.10.md` 3.3 |
| CI-K-2 | `external_id` は NFC、パス区切りは `/`、先頭に `/` を付けない(Indexer は除去しない)、大文字小文字を区別 | 同 3.3、K58 |
| CI-K-3 | `external_id` は空・NUL・長さ超過で全体 400。改行・タブは許可(4096 バイトは検証規則としての仮値) | K59 |
| CI-K-4 | 孤立サロゲートが `external_id` に入るとバッチ全体が 400。Crawler が事前に除去または置換する | K59 |
| CI-K-5 | `content_hash` は小文字 64 桁の 16 進。Indexer は再計算も照合もしない | K59、K66 |
| CI-K-6 | `last-seen` の `document_ids` と、終了通知の `skipped_document_ids`・`oversize_document_ids` の `document_id` は Crawler が算出する | K66、`indexer-api-v0.10.md` 4.2・4.4 |
| CI-K-7 | FS の列挙対象は設定の包含・除外で絞る。対象外は列挙も `last_seen_at` 要請もせず、`enumerated_count` に数えない | ユーザー回答 Q2 |
| CI-K-8 | `url` と `path` は独立した任意の 2 項目。原本の取得日時・Connector 固有属性は MVP で保存せず、送らない | K44、K45 |
| CI-K-9 | リネーム・パス変更は「旧 ID の削除 + 新 ID の追加」。`source_id` は変更できない | `indexer-api-v0.10.md` 3.3 |
| CI-K-10 | 上限を超えた原本は、Crawler(取得)と Indexer(登録)の両方で拒否する(二重防御)。実施自体が確定で、方式・記録先などは未決(CI-U-3) | PD v0.19 4.2、K65(ユーザー承認 2026-11-11) |

### 11.3 案(CI-P)

| ID | 内容 | 章 |
| --- | --- | --- |
| CI-P-1 | `\` を `/` に置き換える規則を含める(Indexer 実装に合わせる。I-10) | 5.1 |
| CI-P-2 | Connector は規則適用前の `external_id` を返し、共通処理が適用順序(孤立サロゲート -> NFC -> `\` 置換 -> 検証)で適用・検証する | 3.1、5.1 |
| CI-P-3 | `content_hash`・`size` は共通処理が送るバイト列から導出する | 5.4 |
| CI-P-4 | 二重実装対策: 共有テストベクタと、応答 `document_id` との実行時照合 | 5.2 |
| CI-P-5 | Connector は内部でリトライしない(ペーシングは除く) | 3.1 |
| CI-P-6 | エラー分類名と属性(`scope`・`retry`)の一式、`ConnectorError` の形 | 3.2、6章 |
| CI-P-7 | 列挙の終端契約(`Completed` / `Failed`。終端なしは未完了) | 3.3 |
| CI-P-8 | `DocumentRef` の構成(`external_id`・`locator`・`size_hint`) | 3.2 |
| CI-P-9 | 接続確認を独立した操作にしない(`validate_config` は I/O をしない) | 3.2、8章 |
| CI-P-10 | 孤立サロゲートの処理は共通処理が一律に適用する。ID 用エスケープ(決定的・単射・`\` を含まない・エスケープ -> NFC の順で冪等)と表示用置換 | 4章、5.1 |
| CI-P-11 | Crawler 側の分類名にも `oversize` を使う(Indexer の仮名と同名。I-5) | 6.2 |
| CI-P-12 | 想定外の例外は共通処理が `connector_internal_error` に変換する。scope は列挙時 source、取得時 document | 3.2、6.2 |
| CI-P-13 | 全 Connector が通る共通の契約テスト | 10章 |
| CI-P-14 | `fetch(ref, max_bytes)`。上限値は Crawler 側の設定で共通処理が渡し、読み取り中の超過で中断して `oversize`。`size_hint` は事前判定の補助 | 3.2、7章 |
| CI-P-15 | 先頭が `/` の `external_id` は除去せず `invalid_external_id` にする | 5.1 |
| CI-P-16 | Connector は対応外の MIME を理由に拒否しない(Indexer が `extract_failed` にする) | 4章 |
| CI-P-17 | `ConnectorError.message` は固定文に加え、原因の特定に足る情報(errno 名・切り詰めた相対パスなど)を含めてよい。本文・認証情報は含めない | 6.1 |

### 11.4 未決(CI-U)

| ID | 内容 | 決める場所 |
| --- | --- | --- |
| CI-U-1 | 二重実装対策の最終採否(共有ライブラリ、テストベクタ、実行時照合。API-U-7 の未決部分)。テストベクタを Indexer 側にも置くか | architecture / module-structure |
| CI-U-2 | `external_id` の衝突(5.3)を検出したときの扱い | architecture |
| CI-U-3 | Crawler 側の `oversize` 拒否の方式: 上限値、`size_hint` による事前判定の要否、記録先・項目、ジョブ status への影響、`oversize_document_ids` への載せ方(PD v0.19 9.2 #8 の未決部分と連動) | architecture |
| CI-U-4 | `invalid_external_id` の文書(ID を算出できない)の記録方法と `enumerated_count` への影響 | architecture |
| CI-U-5 | `source_updated_at` が取れないデータソースでの値(例: 取得時刻にすると毎回メタデータが変わる) | 各 Connector 文書(Web で顕在化) |
| CI-U-6 | 列挙の開始前に事前確認(接続・起点の存在)を行う操作の要否。要る場合は `check_source()` を追加できる | architecture(クロール処理フロー) |
| CI-U-7 | 認証情報の参照名の解決の仕組み | Web 文書 |
| CI-U-8 | `title` が取れない・空のときの値、`title`・`path` の長さと空文字の制約(Indexer が空文字を受理するか未確認。`path` の最大長は Indexer 側で未決) | 各 Connector 文書 |
| CI-U-9 | Connector の呼び出しとリース更新の並行モデル(スレッド・非同期など) | module-structure |
| CI-U-10 | 共通処理が重複除去・衝突検出のために保持する ID の集合の量と、保持できない場合の扱い。1 件あたり `document_id`(64 文字)と元の `external_id` の分で、約 100 バイト台 + `external_id` の長さと見積もる(推測。実測していない)。文書数の想定規模は architecture の非機能の章で見積もる | architecture |
| CI-U-11 | 列挙中の一時失敗の扱い(I-40)。Connector は内部でリトライせず(CI-P-5)、列挙の `Failed` もリトライされない(architecture 6.2)ため、列挙が取得を含む Connector(Web)では、一時的な 5xx・429 が 1 件あるだけで列挙全体が失敗する(推測)。選択肢(決めない): (a) 3.1・CI-P-5 を変え、列挙中の取得に限り Connector 内の上限付きリトライを許す、(b) `EnumerationStream` に失敗後の再開の契約を追加する、(c) architecture 6.2 を変え、列挙全体の再実行を許す、(d) 現状維持。詳細は `connector-web-v0.2.md` 4.5。Web の詳細設計の前に決める。MVP(FS)には影響しない | 本書 3.1・CI-P-5 と architecture 6.2 |

### 11.5 既存設計との不整合(I-n)

I-1〜I-6 は Crawler 設計全体の既存設計との不整合で、`crawler/crawler-architecture-v0.2.md` 13.5 に定義がある。本書に関わるのは I-5(Indexer が仮に置いた失敗種別名など。CI-P-11 で再確認の対象)。

| ID | 内容 | 扱い |
| --- | --- | --- |
| I-10 | (a) `indexer-api-v0.10.md` 3.3 は「パス区切りを `/` に統一」と書くが、Indexer 実装(`document_id.py`、README 6章)は `\` も `/` に置き換える。Linux では `\` がファイル名として使え、`a\b.txt` と `a/b.txt` が同じ `document_id` になる(推測を含む。5.3)。(b) 同様に NFC と NFD の異形が同じ ID になりうる。いずれも Indexer の規則からの帰結 | 本書は Indexer の規則を変えず、実装に合わせて `\` の置換を案として含める(CI-P-1)。衝突は Crawler 側で検出し、扱いを CI-U-2 で決める。Indexer の規則を変える(例: `\` の置換をやめる)かは、Indexer 設計の課題として残す(本書では決めない) |
| I-11 | 原本サイズ超過の Crawler 側の拒否について、PD v0.19 4.2 と `indexer-architecture-v0.10.md` K65(ユーザー承認 2026-11-11)は Crawler の送信前の拒否を含む二重防御を確定として書く。一方 `indexer-api-v0.10.md` 4.9 は「Crawler の送信前の拒否の有無」を未決と書く(PD v0.19 9.2 #8 が未決とするのは記録先・ジョブ status への影響・表示のみ) | 本書は PD 4.2・K65 に従い、Crawler 側の拒否の実施を確定(CI-K-10)とし、方式を未決(CI-U-3)とする。`indexer-api-v0.10.md` 4.9 の記述の更新は Indexer 設計側の課題(本書では書き換えない) |

### 11.6 他文書への依頼と回答の所在

- crawler-architecture: CI-U-2、CI-U-3、CI-U-4、CI-U-6、CI-U-10 の案は architecture が置いた(6.5、7.7、4.5 の手順 8 ほか。対応は architecture 13.6)。最終決定は architecture 側の未決(CA-U)に残る。列挙中の一時失敗の扱い(CI-U-11)は architecture 6.2 と合わせて決める。`failure_detail` への説明文の載せ方(CI-P-17)は architecture 3.3.1・4.8 が定める。`invalid_external_id` の文書が削除判定に与える影響(識別子の規則や Connector の変更で、以前有効だった文書が不正になると期限削除の対象になりうる)と、削除を抑止する選択肢は architecture 7.7 と CA-U-7 にある(CI-U-4 の最終決定と合わせて決まる。本書の規則は変更しない)。
- connector-file-system: 回答済み(`connector-file-system-v0.2.md` 11.6)。孤立サロゲートの発生状況(8.1)、`title`(5.3。CI-U-8)、`source_updated_at`(5.4。CI-U-5)、MIME の対応表(5.2)、`size_hint` は返さない(5.5)、衝突への対応(8.4。FS 固有の回避は置かず CFS-U-5)。
- connector-web: 回答済み(`connector-web-v0.2.md` 4.3、4.5)。論点 A〜D への回答、CI-U-5(CW-U-10)、CI-U-7(CW-U-6)。本書への修正要望(I-40〜I-42)は、本書の 9章・3.3・10章・CI-U-11 に反映した。
- crawler-module-structure: 回答済み(`crawler-module-structure-v0.2.md` 7.6)。CI-U-1、CI-U-9、`ConnectorType`・共通処理の配置(CM-P-6、CM-P-7)は同書が定めている。
