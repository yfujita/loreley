# ファイルシステムコネクタ設計書 v0.3

- 版: v0.3
- 更新日: 2026-11-16
- 前版: `connector-file-system-v0.2.md`
- 位置づけ: MVP で唯一の Connector である FileSystem(以下 FS)の設計。マウント済みのローカルディレクトリ・ファイル共有を読み、`connector-interface-v0.3.md` の抽象に従って文書を列挙・取得する。実装に着手できる粒度(設定、走査の規則、errno とエラー分類の対応、取得手順、疑似コード、テスト観点)まで定める。
- 区分の扱い(v0.3 から): 「確定(`-K-`)」は、ユーザー回答(Q2)、PD v0.19 でユーザーが承認済みの事項、interface・architecture の確定事項だけ(11.2)。v0.2 までの「案」(`-P-`)は、ユーザー指示 2026-11-16 により**ユーザー承認済みの案**になった(設計として承認済み。変更にはユーザー判断が要る。ID は付け替えず `-P-` のまま。`-K-` でもない)。ただし CFS-P-24 は、CFS-U-7 の選択肢 (c) の中身で、案 (a)「現状維持」の承認により**採用しない**案である。数値は承認後も「仮値・設定可能」で、確定ではない(CFS-U-6)。推測(実機未確認)も承認で確定しない。v0.3 で追加した CFS-P-25〜31 は実装で決めた内容で、ユーザーが個別に確定したものではない。
- v0.3 の改訂(2026-11-16。承認の反映と、実装結果の反映):
  - 承認の出典: ユーザー指示 2026-11-16(「未確認事項について、設計書は承認する。2設計書の改版に反映する。それ以外は別タスク」。「2設計書の改版」は、STATUS.md の「ユーザー判断待ち」の2番『設計書の改版』の意。「それ以外」は同3〜5番(infra 前提作業の起票・コミット・Integration Test)で、この改版では扱わない)。作業記録 `agent_tasks/20261113_implement_crawler/0023-approve-and-revise-design.md`。承認の対象は Crawler 設計書の現行版全体(architecture・crawler-api・module-structure・decisions と、connector 配下の interface・file-system・web)。
  - 承認で解消した未決: CFS-U-1(glob 構文と `include_patterns` は「既定の拡張子への追加」)、CFS-U-2(`follow_symlinks`・`include_hidden` の初期値は両方 `false`)、CFS-U-3(`title` はファイル名のみ)、CFS-U-5(`external_id` の衝突に FS 固有の回避を置かず、ジョブ `failed`)、CFS-U-7(0 件列挙のときの削除の保留は、案 (a)「現状維持」で承認。警告 CA-P-52 で気づく。実装も (a))。いずれも案どおり承認(decisions v0.3 の4章の表の ID 列に対応)。(b)(c) は採らない。CFS-P-24(目印ファイル)は採用しない案になった。
  - 承認で解消しなかった未決: CFS-U-4(実機での確認)、CFS-U-6(数値は仮値のまま。実測後)。CFS-U-4 のうち「エンコーディングの確認方式」だけは実装で決めた(CFS-P-27)。
  - 実装で決めた内容(実装タスク 20261113_implement_crawler。ユーザー指示 2026-11-16 で反映): glob の照合は正規表現を使わず多項式時間のアルゴリズムにした(CFS-P-25。2.2・2.3・9.1・9.2・9.3)、OS 呼び出しを `FsOps` に集約(CFS-P-26。9.2)、エンコーディングの確認(CFS-P-27。8.1・9.1)、エラー変換で元の例外を traceback に出さない(`from None`)・説明文に入力値を入れない(CFS-P-28。7.3)、列挙ストリームの終端後・`close()` 後の振る舞い(CFS-P-29。4.5)、テスト実行環境の判定(CFS-P-30。10章)、最悪入力の照合時間の許容(CFS-P-31。9.3)。
  - 変更した節: 冒頭の区分の扱いと凡例、関連文書の表、2.1・2.2・2.3(未確定の表現の更新と照合方式)、3.2・3.4.3(注記)、4.5、5.3・5.4、6.1(注記)、7.1・7.3、8.1・8.4、9.1〜9.4、10章(#5、#18・#19 の判定、#24〜#26 の追加、実行環境の注意、注入点)、11.1〜11.4・11.6。設計の方針(絞り込みの規則、errno の分類、取得の手順、0 件の扱い)は変えていない。
  - 新規 ID: CFS-P-25〜31。更新: CFS-P-3・21・22。解消: CFS-U-1・2・3・5・7(CFS-P-24 は採用しない案)。
  - 実装と設計書の食い違い: 照合方式の 1 点(CFS-P-25)だけ。それ以外の 10章のテスト観点 #1〜#23 は実装のテストで対応づけた(10章)。
- **追補(2026-11-16。出典: ユーザーの回答。作業記録 0025)**: crawler-api の CAPI-U-8 の残り(`external_id` に影響する設定を変えたときの扱い)は、2.4 のとおり、移行処理・警告を置かなくてよいと回答された(ユーザー回答 2026-11-16。解消)。FS の ID・仕様の変更はない(2.4 の記述を明確にしただけ)。CI-U-6(事前確認を置かない)、CI-U-4・CA-U-7(識別子エラーは警告のみ)も回答済みで、FS の規則は変えていない。CFS-U-4・6 は未決のまま(実機・実測)。
- v0.2 の改訂: architecture v0.2(外部レビュー反映)への追従。ユーザーが確定していない事項は案・未決のままにした。
  - 0 件列挙の扱い(3.4): architecture の 0 件警告(CA-P-52)を、管理者が気づく手段に加えた。マウント外れで空になったときの確認手順を追加(CFS-P-23)。削除を保留する挙動は architecture の未決 CA-U-19 で、本書では確定せず、FS 固有の案(ルート直下の目印ファイル。CFS-P-24)と未決(CFS-U-7)を記録した。
  - 設定変更の影響(2.4): 実行中のジョブは、手順 6 で 1 度だけ読んだ設定で動き続ける(CA-P-51)ことを追記。
  - `include_patterns` の意味(2.1、CFS-U-1): 現行の「追加」の案は維持し、確定扱いにしない。置き換え・名称変更の選択肢と、設定画面での注意を追記。
  - 索引・マッピングの記述は本書にない(architecture CA-K-21 への追従は不要)。
  - 新規 ID: CFS-P-23・24、CFS-U-7。更新: CFS-U-1。参照している architecture の章・ID は v0.2 でも存在する(11.1)。関連文書に `crawler-design-decisions-v0.1.md` を追加。他文書への依頼は 11.6。

区分の凡例(Indexer 設計書に合わせる):

| 区分 | 意味 |
| --- | --- |
| 確定 | ユーザーが確定した事項(出典を書く) |
| 案 | v0.2 まではユーザー未確定。2026-11-16 のユーザー承認により、**承認済みの案**(設計として承認済み。変更にはユーザー判断が要る。CFS-P-24 は案 (a) の承認により採用しない案)。`確定`(`-K-`)とは別。v0.3 で実装から追加した案(CFS-P-25〜31)は「実装で決めた内容」で、個別の確定ではない |
| 未決 | 決めていない。承認では解消しない(案が無いもの、実機でしか確認できないもの、個別の判断が要るもの) |
| 推測 | 根拠が弱い想定。推測と注記した事項(実機未確認を含む)。承認で確定しない |
| 導出 | 他の仕様から導いた事項(明示された記述がなく、本書で導いた事項) |

ID 体系: 本書の確定・案・未決は `CFS-K-n` / `CFS-P-n` / `CFS-U-n`。既存設計との不整合は `I-n`(本書の予約範囲は I-30〜I-39。使用は I-30 のみ)。`CI-` は interface、`CA-` は architecture のID。

関連文書:

| 文書 | 内容 | 本書との関係 |
| --- | --- | --- |
| `connector/connector-interface-v0.3.md`(以下 interface) | Connector の抽象、メタデータ、`external_id` 規則(孤立サロゲートの処理を含む)、`document_id`、`content_hash`、エラー分類、`fetch(ref, max_bytes)` | 正本。再掲せず参照する。11.6 の申し送りには 11.6 で回答する |
| `crawler-architecture-v0.4.md`(以下 architecture) | ジョブ、リトライ・スキップ、連続スキップの打ち切り、`create` の呼び出し位置、設定の読み取り(CA-P-51)、0 件列挙の警告(CA-P-52)、13.7 の依頼 | 正本。13.7 の FS への依頼には 11.6 で回答する |
| `crawler/crawler-design-decisions-v0.4.md`(以下 decisions) | 実装着手のための短い決定事項の文書(採用方針、ユーザー確定事項、実装着手を妨げる未決、実装者が決めてよい事項) | 本書の要約。理由・詳細は本書が正 |
| `crawler-api-v0.4.md` | データソース設定の登録・更新(`validate_config` を呼ぶ) | 本書 2章が `connector_config` の検証規則 |
| `crawler-module-structure-v0.5.md`(以下 module-structure) | `connectors` の構成、`FsOps`(CM-P-9)、共通処理の配置 | 本書 9.2 の `FsOps` の操作の一覧は本書が、注入の方式は module-structure が定める |
| `connector/connector-web-v0.3.md` | Web の概要 | 互いに参照しない |
| `indexer/indexer-api-v0.10.md`(以下 api) 3.3・4.3 | `external_id`・メタデータの検証規則 | 契約は再掲しない |
| `apps/indexer/.../documents/extraction/extractor.py` | 抽出が対応する基準 MIME | MIME 対応表(5.2)の根拠 |
| PD v0.19 4.1・4.2・5.2・8.1・8.2 | MVP の範囲、列挙の失敗・0 件列挙・読み取り専用マウント | 確定事項の出典 |

SD v0.8(1.1、3.1、6.4)の決定事項を出典として参照した。SD は廃止予定のため、本書は自文書で完結させ、SD への参照は出典の注記にとどめる。

---

## 1. 位置づけと範囲

### 1.1 位置づけ

- FS は MVP で唯一の Connector(PD v0.19 4.1・8.1。確定。CFS-K-1)。`connector_type` の値は `file_system`(architecture 3.2 の案に従う)。
- ファイル共有は、OS がマウント済みのパスとして扱う。SMB・NFS のクライアントは実装しない(案。CFS-P-9)。Office 形式は次版で、対象外(PD v0.19 4.2。確定)。

### 1.2 範囲

- 本書が定める: `connector_config` の項目と検証(2章)、ルートの確認とマウント外れ・0 件の扱い(3章)、列挙の規則(4章)、文書メタデータの値(5章)、取得の手順(6章)、errno とエラー分類の対応(7章)、ファイル名の扱い(8章)。
- 本書が定めない(参照のみ): `external_id` 規則・孤立サロゲートの処理方式・`document_id`・`content_hash`・`size`(interface 5章。共通処理)、リトライ・スキップ・連続 20 件の打ち切り・ジョブの状態(architecture)、Indexer の契約(api)、原本の抽出・文字コードの判定(Indexer)。

### 1.3 interface の要素と本書の対応

| interface の要素 | FS での実現 | 章 |
| --- | --- | --- |
| `validate_config` | I/O をしない検証 | 2.2 |
| `create` | ルートの確認(`stat` と `scandir` の開始)。開始通知の前に失敗を検出する | 3.2 |
| `enumerate()` / `EnumerationStream` | ディレクトリの再帰走査。`DocumentRef` を 1 件ずつ返し、最後に `Completed` か `Failed` | 4章 |
| `DocumentRef.external_id` / `locator` / `size_hint` | ルートからの相対パス(規則適用前)/ 同じ相対パス / 返さない | 4.5、5.5 |
| `fetch(ref, max_bytes)` | `open` -> `fstat` -> 上限確認 -> 読み取り -> 変更の確認 | 6章 |
| `DocumentMetadata` | `title`・`path`・`mime_type`・`source_updated_at`(`url` なし) | 5章 |
| `ConnectorError` | errno からの分類(表 7.1) | 7章 |
| `close()` | `Connector.close()` は何もしない(保持する資源がない)。`EnumerationStream.close()` は走査を打ち切る | 9.1 |

### 1.4 設計方針(導出)

1. 列挙は読み取りだけで、失敗を握りつぶさない。判断に迷う列挙エラーはジョブを `failed` にする側に倒す(architecture 1.4 の 1)。
2. 絞り込みは「既定の拡張子 + glob の包含・除外 + 2 つの真偽値」に限る。
3. 識別子の正規化・検証・`document_id` 算出は共通処理に任せ、FS は規則適用前の値を OS から読んだまま返す。

---

## 2. 設定(`connector_config`)

### 2.1 項目(承認済みの案。CFS-P-1、CFS-P-2)

| 項目 | 型 | 必須 | 既定 | 説明 |
| --- | --- | --- | --- | --- |
| `root` | string | ○ | | Crawler コンテナ内の、検索対象ディレクトリの絶対パス。`external_id` の起点(5.1) |
| `include_patterns` | string[] | 任意 | `[]` | 既定の拡張子(下記)に**追加**で対象にする glob(2.3) |
| `exclude_patterns` | string[] | 任意 | `[]` | 対象から除く glob。ファイルにもディレクトリにも適用し、一致したディレクトリは配下を走査しない(4.1) |
| `follow_symlinks` | boolean | 任意 | `false` | シンボリックリンクをたどるか(4.2。初期値は承認済みの案。CFS-U-2 は解消) |
| `include_hidden` | boolean | 任意 | `false` | 名前が `.` で始まるファイル・ディレクトリを対象にするか(4.3。初期値は承認済みの案。CFS-U-2 は解消) |

- **既定の拡張子**(Q2。確定。CFS-K-3): `.txt`、`.md`、`.markdown`、`.html`、`.htm`、`.pdf`。固定の集合で、設定項目にしない(承認済みの案。CFS-P-2)。
- 「包含パターンは設定で追加可」(Q2)の実現は、`include_patterns` が既定の拡張子に**加わる**形にした(承認済みの案。CFS-P-2)。代替の「`include_patterns` を指定したら既定を置き換える」は、既定を残したまま 1 種類だけ足すのに既定の 6 件を書き直す必要があるため、採っていない(2026-11-16 のユーザー承認で、追加の形で案どおり承認。CFS-U-1 は解消)。一部の拡張子だけに絞りたいときは `exclude_patterns` を使う(例: `**/*.pdf`)。
- 注意: `include_patterns` は「既定の拡張子への追加」であり、サブツリーだけに絞る用途には使えない(絞るには `root` を狭めるか `exclude_patterns` を使う)。`docs/**` のようなパターンを入れると、拡張子を問わず `docs` 配下の全ファイルが対象になり、対応外のものは `application/octet-stream` で取得されて Indexer の `extract_failed` が大量に出うる(5.2)。追加の形はユーザー承認済み(2026-11-16。CFS-U-1 は解消)。置き換えや名称変更((ii)(iii))に変えるときは、ユーザー判断と本書の改版・既存設定の見直しが要る。
- **設定画面(Admin View)を作るときの注意**(承認済みの案): `include_patterns` は一般の glob の「対象を絞る」直感と逆に、既定の拡張子へ**加える**項目である。項目名の表示と説明文に、「既定の拡張子(`.txt`・`.md`・`.markdown`・`.html`・`.htm`・`.pdf`)への追加であり、対象を絞る用途ではない。絞るには `exclude_patterns` を使う」と示す。将来、項目名を変える((iii)。CFS-U-1 で退けた選択肢)場合は、画面の表示名もそれに合わせる。
- 共通項目(`ttl`・`ratio_threshold` など)は `connector_config` に含めない(interface 8章)。

### 2.2 検証(`validate_config`。承認済みの案。CFS-P-1)

I/O をしない。違反は `config_invalid`(7章)。説明文は固定文で、項目名(配列は添字)と違反の種類だけを入れる(crawler-api は、孤立サロゲートの置換・制御文字のエスケープ・512 文字以内への切り詰めを通して応答に載せる。crawler-api v0.4 CAPI-P-23)。入力値は入れない。未知のキーの名前も入れず、「未知の項目がある」とだけ書く(項目名は `connector_config`。CFS-P-28)。

- `connector_config` は JSON のオブジェクト。上記以外のキーは拒否する(綴りの誤りを見逃さないため)。省略は既定値で、`null` は型の違反とする。
- `root`: 空でない文字列で、`/` で始まる。NUL と UTF-8 にできない文字(孤立サロゲート)を含まない。`.`・`..` のセグメントと連続する `/` を含まない。末尾の `/` は除いて保持する(`/` だけの場合を除く。`/` は有効で、結合は 9.1 の規則に従う)。存在の確認はしない(3.2)。
- `include_patterns`・`exclude_patterns`: 文字列の配列。1 つのパターンは 1〜1024 バイト(UTF-8)、配列は 100 件まで(仮値・設定可能。CFS-P-21)。各パターンは、NUL・孤立サロゲート・`\` を含まず、`/` で始まらず終わらず、空のセグメントと `.`・`..` のセグメントを含まず、`**` は単独のセグメントとしてだけ使え(`**.md` は拒否。`**/*.md` と書く)、`**` のセグメントが隣り合う(`**/**`、`a/**/**`)ものは拒否する(同じ意味の書き方が複数でき、表記を 1 つに絞るため。意味は一意に決まり、照合の負荷が理由でもない。実装は隣り合う `**` も照合できる。`**/a/**/b` のように離れていれば有効)。
- `follow_symlinks`・`include_hidden`: 真偽値(`0`・`1`・文字列は拒否)。

### 2.3 パターン構文(glob。承認済みの案。CFS-P-3、CFS-P-4、CFS-P-25)

構文は glob で、ユーザー承認済み(2026-11-16。CFS-U-1 は解消)。確定(`-K-`)ではなく、変更にはユーザー判断と、本書の改版・既存設定の見直しが要る。

- 照合の対象は、ルートからの相対パス(区切りは `/`)。パターンは常にルートからの相対パスの**全体**に一致させる(`*.md` はルート直下の `.md` だけ。どの深さでもなら `**/*.md`)。
- パターンと相対パスは、どちらも NFC に正規化して照合する(macOS 由来の NFD の名前でも同じパターンで一致させるため。8.2)。大文字小文字は区別する(`external_id` と同じ。CFS-K-7)。
- 特別な文字は `*`、`?`、`**` の 3 つだけ。`[`・`]`・`{`・`}` などは文字そのもので、`\` によるエスケープはない(`\` はパターンで使えない)。

| 記法 | 意味 |
| --- | --- |
| `*` | `/` 以外の 0 文字以上(名前が `.` で始まるものにも一致する。隠しファイルは 4.3 の別の規則で扱う) |
| `?` | `/` 以外の 1 文字(`\` や改行にも一致する) |
| `**`(単独のセグメント) | 0 個以上のセグメント。末尾の `P/**` は、`P` 自体と `P` の配下すべてに一致する |

**照合の方式**(実装で決めた内容。CFS-P-25): 上の表の意味を満たす照合を、**正規表現を使わず、最悪の入力でも多項式時間で終わる**アルゴリズムで行う。正規表現はバックトラックで、`*a*a*a*a*a*a*b` のようなパターンや離して並べた `**` で、照合の時間が指数的に延びる(正規表現による旧実装では `*a` 6 組で約 2.0 秒、7 組で約 13.6 秒。実装中のレビューで判明し、置き換えた)。照合は中断できず(Job Runner が止まる)、入力は管理者の設定と共有の中の名前なので、時間の上限を保証できる方式にした。実装の方式は次のとおりで、意味(上の表と下の例)を変えない限り、方式を入れ替えてよい。

- パターンもパスも `/` でセグメントに分ける。
- セグメント内の `*`・`?`: 貪欲な 2 ポインタ法(最後に見た `*` の位置にだけ戻る)。パターンのセグメントの長さと名前の長さの積に比例する時間。
- セグメントどうし: パターンのセグメントを順に進めながら、「次に照合するパスのセグメント位置」の集合を持つ。`**` はその集合の各位置から、0 個以上の(空でない)セグメントの分だけ位置を進める。末尾の `**` は、残りが何であれ一致する(`P/**` は `P` 自体と配下すべて、`**` だけなら全部)。セグメント内の照合の回数は、パターンのセグメント数とパスのセグメント数の積以下。
- 空のセグメントは、検証(2.2)とエントリ名(`/` を含まない)から現れない前提。

一致の例(実装のテストで全件の結果を確認した。11.1):

| パターン | 一致する | 一致しない |
| --- | --- | --- |
| `**/*.md` | `a.md`、`x/y/a.md` | `a.txt` |
| `*.md` | `a.md` | `x/a.md` |
| `docs/**` | `docs`、`docs/a.md`、`docs/x/y.md` | `docsx/a.md`、`x/docs/a.md` |
| `**/drafts/**` | `drafts`、`a/b/drafts/x.md` | `a/drafts2/x.md` |
| `a/**/b.md` | `a/b.md`、`a/x/y/b.md` | `ab.md` |
| `**/lost+found` | `lost+found`、`a/lost+found` | |
| `report-?.pdf` | `report-1.pdf` | `report-10.pdf` |
| `a?b.txt`(`?` は `\` に一致) | `a\b.txt` | `a/b.txt` |
| `資料/**`(NFC) | NFD で書かれた `資料/が.txt` | |
| `**/a/**/b`(離れた `**` は有効) | `a/b`、`x/a/y/z/b` | `ab`、`x/a/b/c` |
| `**/**`、`a/**/**`(`**` の連続) | (`config_invalid`。2.2) | |

既定の拡張子は glob ではなく、ファイル名の**最後の拡張子**(最後の `.` 以降。名前の先頭だけの `.` は拡張子ではない。`os.path.splitext` と同じ)を小文字にして照合する(承認済みの案。CFS-P-4)。`A.PDF` も対象で、`a.tar.gz` の拡張子は `.gz`(対象外)。

### 2.4 設定変更の影響(導出)

`external_id` はルートからの相対パスなので、変更が文書の同一性に与える影響は次のとおり(interface 8章が各 Connector 文書に委ねた事項)。特別な移行処理・警告は置かない(ユーザー回答 2026-11-16。crawler-api の CAPI-U-8 の残りを解消)。

| 変更 | 影響 |
| --- | --- |
| `root` を、同じ構造の別のパスに変える(マウント先の移動など) | 相対パスが同じなので同じ文書。影響なし |
| `root` を配下のサブディレクトリに狭める / 親に広げる | 相対パスが変わり、旧 ID は列挙されず期限削除の対象、新 ID は新規になる(`document_id` が変わるため。リネームと同じ。CI-K-9) |
| 包含・除外パターン、`follow_symlinks`、`include_hidden` を変えて対象外になった文書 | 列挙されず、期限削除の対象になる(interface 3.3 の 4)。大量に外れると割合ルール(Indexer)にかかり、削除は見送られる。全件を意図して消す場合は手動クロールの強制削除 |

変更は次のジョブから反映される(architecture 3.2)。ジョブの実行開始(architecture 4.5 の手順 6)で `loreley-sources` が 1 度だけ読まれ、`connector_config` は `ttl` などと同じ版で確定する。実行中のジョブの途中で `connector_config` が切り替わらないので、`create`・列挙・取得は、すべて手順 6 で読んだ同じ設定で行われる(案。architecture CA-P-51)。手順 6 の後に更新した設定は、次のジョブから反映される。

### 2.5 例

```json
{
  "root": "/mnt/docs",
  "include_patterns": ["**/*.rst"],
  "exclude_patterns": ["**/lost+found", "archive/**"],
  "follow_symlinks": false,
  "include_hidden": false
}
```

(`.rst` は対応形式でないため、Indexer が `unsupported_mime_type` の `extract_failed` として登録する。5.2)

---

## 3. マウントとルート

### 3.1 マウント(CFS-K-2、CFS-P-9)

- 検索対象のディレクトリは、`crawler` コンテナにだけ**読み取り専用(`:ro`)**でマウントする(PD v0.19 8.2。確定。`crawler` だけに付けるのは architecture 10 の案)。FS は読み取りしかせず、書き込み・削除・属性変更をしない。
- ホスト側のファイル共有(SMB・NFS など)は、運用者が OS でマウントし、そのパスをコンテナにバインドマウントする(案)。マウントの方法・オプションは運用の領域で、本書は定めない。
- `root` は**コンテナ内のパス**で指定する。コンテナにマウントしていない場所は、設計上は見せない(SD v0.8 6.4)。ただし MVP は認証がなく、登録できるルートを制限しない(将来の版。PD v0.19 2章)ため、コンテナ内の任意のパスを `root` に登録できる。

compose での例(実装時に `deploy/compose/` へ追加。architecture 10):

```yaml
services:
  crawler:
    volumes:
      - /srv/docs:/mnt/docs:ro   # ホストのパス : コンテナ内のパス : 読み取り専用
```

### 3.2 `create` でのルート確認(architecture 13.7 への回答。承認済みの案。CFS-P-10)

**行う**。`create` は次の確認をし、失敗すれば 7.1 の分類で `ConnectorError`(source)を送出する。

1. `root` を `stat` する(`root` 自体がシンボリックリンクでもたどる。`follow_symlinks` は `root` の配下だけに効く)。存在しない、またはディレクトリでなければ失敗。
2. `root` を `scandir` で開いて閉じる(中身は読まない)。権限・I/O の失敗を検出するため。
3. `follow_symlinks=true` なら、`root` の実パス(`realpath`)を求めて保持する(4.2)。

この確認の前に、`create` はファイルシステムエンコーディングが UTF-8 であることを確認する(8.1。CFS-P-27)。確認の OS 呼び出しはすべて `FsOps` 経由(9.2)。

理由:

- architecture 4.5 の手順 8 は、`create` の失敗なら開始通知を送らずジョブを `failed` にする。ルートの確認を `create` に置くと、マウント外れ・ルートの誤記は開始通知の前に検出され、Indexer に「失敗した世代」の記録(`loreley-deletions`)が残らない(導出)。
- `create` の `transient` の失敗は architecture 6.2 に従いリトライされるので、共有の一時的な不調を吸収できる。
- 専用の事前確認の操作は置かない(CI-P-9、CA-P-15)。`validate_config` は I/O をしないため、`root` の誤記は最初のクロール(`create`)で `source_not_found` になる。

### 3.3 マウント外れの検知(承認済みの案。CFS-P-11)

マウント外れの症状は 1 つではないため、検知できるものとできないものを分ける。実機での症状は推測で、確認は CFS-U-4。

| 症状 | 検知 | 扱い |
| --- | --- | --- |
| `root` のパスが存在しない(マウント元が無いまま起動したなど) | できる | `source_not_found` |
| 共有に到達できない(`ESTALE`、`EIO`、`ETIMEDOUT`、`ENOTCONN` など。7.1 の集合 T) | できる(`create`・列挙・取得で errno が返る場合) | ルート: `source_unreachable`。配下の走査: `enumeration_incomplete`。取得: `fetch_transient` |
| 走査の途中で配下のディレクトリが消えた | できる | `enumeration_incomplete`(列挙の失敗。ジョブ `failed`) |
| `root` は存在するが空になっている(マウントされず、空のマウントポイントだけが見える) | **できない** | 0 件の列挙として完了する(3.4) |
| 入出力が戻らない(ハードマウントの共有の停止など) | できない | 9.2 の注意 |

分類の判定(interface 6.2 が委ねた判断への答え。案): **errno で分ける**。

- 起点のパスが存在しない・たどれない(`ENOENT`・`ENOTDIR`・`ELOOP`・`ENAMETOOLONG`)は `source_not_found`(permanent)にする。理由: (1) 「起点が存在しない」という定義に一致する。(2) 実行中のコンテナで外れたバインドマウントは、ホスト側で共有を再マウントしても元に戻らず、コンテナの再起動が要ると想定される(推測。実機未確認)ため、同じジョブ内のリトライ(1 秒・2 秒の待ち)で直らない。(3) 誤記との区別がつかず、いずれも運用者の対応が要る。
- 到達できないだけの errno(集合 T)は `source_unreachable`(transient)にする。共有側の一時的な不調で、待てば直りうるため。
- ジョブの結果はどちらも `failed`(`enumeration_failed`。architecture 4.8)で、削除は起きない(PD v0.19 5.2。確定。CFS-K-4)。両者の差は、`create` でリトライするか(`transient` のみ)と、管理者が切り分けるときの手がかり(再マウント・コンテナの再起動か、共有側の復旧待ちか)にある。

### 3.4 0 件の扱い(導出。管理者が気づく手段と確認手順は承認済みの案。CFS-P-23。削除の保留は案 (a) で承認、CFS-P-24 は採用しない。CFS-U-7 は解消)

列挙が 0 件でも異常にしない。`Completed` で終える(PD v0.19 5.2「0 件列挙は異常とはせず、列挙の完了」。確定。CFS-K-5)。理由: 全ファイルを消したデータソースを、手動クロールの強制削除で空にできる必要がある(PD v0.19 5.2・8.2)。ルートが空であることを失敗にすると、これができなくなる。

マウント外れで空になった場合の保護は Indexer の割合ルール・TTL・件数照合が担う(PD v0.19 2章)。削除対象が最小件数以下の小さなソースでは、0 件列挙でも TTL 経過後に削除されうる(PD v0.19 が MVP の制約として記録済み)。管理者は、ジョブの登録結果の `enumerated_count` が 0 になっていること、割合ルールで見送られた場合は削除結果が `skipped_by_ratio` になっていることで気づける(architecture 7.7、7.6)。

#### 3.4.1 管理者が気づく手段(承認済みの案。CFS-P-23)

0 件のクロールは `succeeded` で終わり、ジョブの status・終了通知は変わらないため、一覧の status だけでは気づけない。次の 3 つが手がかりになる。

1. **0 件列挙の警告**(architecture 7.7。案。CA-P-52): 今回が 0 件で、直前に列挙を完了したクロールが 1 件以上だったとき、ジョブ記録の `warnings` に固定文のコード(例 `enumerated_zero_after_nonzero`。名称は architecture の案)と前回の件数・`job_id` が残る。FS はこの警告を作らない(共通処理の責務)。FS が守ることは、マウント外れで空に見える場合も 0 件の `Completed` を返す(失敗にしない)ことだけ。前回も 0 件、または前回がないときは警告は出ない(初回の登録で `root` を誤って空のディレクトリにした場合などは検出できない)。
2. 登録結果の `enumerated_count`(0)。
3. 削除結果(割合ルールで見送られたときは `skipped_by_ratio`。architecture 7.6)。

`warnings` の表示は Admin API の設計で決まる(Admin API は `loreley-jobs` を直接読む。architecture 2.2、CA-U-12)。crawler-api の応答には `warnings` はない。

#### 3.4.2 マウント外れが疑われるときの確認手順(承認済みの案。CFS-P-23)

実機で確認していない。マウント外れの症状・復旧は推測を含む(3.3、CFS-U-4)。

1. 直近のジョブの `enumerated_count` と `warnings` を確認する。0 件警告があるか、前回の件数はいくつだったかを見る。ジョブが `failed`(`source_not_found`・`source_unreachable` など)なら、マウント外れでも 0 件ではなく失敗の側に出ているので、`failure_detail` の errno とパスを見る(3.3)。
2. `crawler` コンテナ内で `root` の中身を確認する(例: `docker compose exec crawler ls <root>`)。空、または以前あったディレクトリがなければ、マウント外れの疑いが強い。
3. ホスト側で、共有が OS にマウントされているかと、compose のバインドマウント元(ホストのパス)の中身を確認する。
4. 症状は 2 通りに分けて考える(どちらも推測。実機未確認)。
   - **実行中に共有が外れた場合**: コンテナ内のバインドマウントが `ESTALE`・`EIO` などのエラーを返す可能性が高い。この場合は 0 件ではなく、ルートまたは配下の失敗(`source_unreachable`・`enumeration_incomplete`)としてジョブが `failed` になる(3.3、7.1)。ホストで共有を再マウントしても、実行中のコンテナのバインドマウントは元に戻らず、`crawler` コンテナの再起動が要ると想定される(3.3 と同じ)。
   - **共有が外れた状態でコンテナを起動した場合**: 空のディレクトリ(マウントポイント)が見える可能性がある。この場合は 0 件の `Completed` になり、0 件警告が手がかりになる。ホストで共有をマウントしたうえで、`crawler` コンテナを再起動する(想定)。

   復旧したら、手動クロールを実行して、`enumerated_count` が前回の件数に戻ったことを確認する。
5. 削除されるかどうかは、Indexer の `ttl`・割合ルール・件数照合による(3.4 の冒頭)。意図しない 0 件のとき、`ttl` が経過する前に復旧して再クロールすれば、`last_seen_at` が更新される(導出。Indexer の判定は arch・api に従う。実機未確認)。
6. 意図して全件を消したときの 0 件(全ファイルを削除したなど)は、警告が残るのが正常で、対応は要らない。確実に削除したいときは、手動クロールの強制削除を使う(CFS-K-5)。

#### 3.4.3 削除を保留する挙動(案 (a) 現状維持で承認。CFS-U-7・architecture CA-U-19 は解消。(b)(c) は採用しない)

ユーザー承認(2026-11-16)で、案 (a)「現状維持」(0 件を異常とせず `Completed` にし、警告 CA-P-52 と運用手順で気づく)で承認された。実装も (a) で、(b)(c) は実装していない(`connector_config` に目印の項目はなく、2.2 の未知のキーとして拒否される)。

0 件のときに削除を保留するかは、architecture の CA-U-19 の選択肢だった。以下は、検討した選択肢と FS との関係の記録(v0.2 の記述。(b)(c) を将来採る場合は、ユーザー判断と改版が要る)。

| 選択肢(CA-U-19) | FS への影響 |
| --- | --- |
| (a) 現状維持(0 件を異常とせず、運用手順と警告で気づく) | 変更なし。3.4.1・3.4.2 が運用手段 |
| (b) 前回 1 件以上・今回 0 件のとき、`force_delete=true` でなければ終了通知を `failed` にして削除させない(ジョブも `failed`) | 共通処理(Crawler)の挙動で、FS の変更は要らない。PD v0.19 5.2「0 件列挙は異常としない」との関係の確認が要る(CFS-K-5 との整合は PD 側の判断) |
| (c) Connector 固有の目印で、マウントされた共有かを確かめる | FS 固有の案を下に書く(CFS-P-24) |

**FS 固有の案(c)の中身**(CFS-P-24。案 (a) の承認により採用しない。検討の記録として残す):

- `connector_config` に任意の項目(例 `required_marker`。名称は案)を足す。値は `root` 直下の通常ファイルの**ファイル名のみ**で、`validate_config` が `/`・`..` を含まない文字列かを検証する(I/O なし。`config_invalid`)。運用者が共有の中に置く(例: `.loreley-mounted`)。**`.` で始まる名前を推奨する**: 隠しファイルは既定(`include_hidden=false`)で列挙されず(4.3)、検索対象にならない。`.` で始まらない名前(例: `mounted.txt`)にすると、既定の拡張子や `include_patterns` に一致した場合に列挙・索引化されうる(`include_hidden=true` のときも同じ)。
- `create` が `stat(root/<目印>)` を確かめ、なければ `source_not_found`(または `source_unreachable` の新しい用途。どちらにするかは未決)にする。ジョブは開始通知の前に `failed` になるので、Indexer に「失敗した世代」の記録も残らず、削除も起きない(3.2 と同じ理由。導出)。共有が外れた状態でコンテナを起動し、空のマウントポイントが見えている場合は、目印が見えないので検出できる。実行中に外れた場合は、目印がなくても `ESTALE`・`EIO` などの errno で既に失敗側に出ると想定される(3.4.2 の手順 4)。どちらも推測で、実機未確認。
- 全ファイルを意図して消すときは、目印を残したまま他を消せば、0 件の `Completed` になり、強制削除でも空にできる(CFS-K-5 は変わらない)。
- 欠点: 項目と運用の手間が増える(共有の中に書き込み権限で目印を置く。本書の読み取り専用マウントとは別に、共有側の操作になる)。目印を誤って消すと、そのソースのクロールが毎回失敗する。設定した場合だけに効き、設定しなければ(a)と同じ。Web には効かない(architecture CA-U-19 の (c) と同じ)。
- 目印の確認が不要な、より弱い代替(推測。採るなら実機確認が要る): `root` がマウントポイントか(`os.path.ismount` や親ディレクトリとの `st_dev` の比較)を確かめる。設定は不要だが、`root` がマウントポイントの配下のサブディレクトリのときは使えず、コンテナのバインドマウントでの挙動も未確認。

---

## 4. 列挙

### 4.1 走査の規則(承認済みの案。CFS-P-5、CFS-P-8)

`root` から再帰的に走査する。各エントリ(`root` の配下の名前)に、次の順で判定する。

| 順 | 判定 | 該当したときの扱い |
| --- | --- | --- |
| 1 | 名前が `.` で始まる(`include_hidden=false` のとき。4.3) | 無視する。ディレクトリは走査しない |
| 2 | 種別。シンボリックリンクは 4.2 に従う。通常ファイル・ディレクトリ以外(FIFO、ソケット、デバイス)は対象外 | 対象外は無視する |
| 3 | `exclude_patterns` に一致する(ディレクトリにもファイルにも適用) | 無視する。ディレクトリは**開かず**、配下も走査しない |
| 4 | (通常ファイルだけ)既定の拡張子に一致する、または `include_patterns` のいずれかに一致する | どちらにも一致しなければ無視する |

順 1〜4 をすべて通った通常ファイルだけを `DocumentRef` として返す。

- 「無視する」は、列挙しない・`last_seen_at` を要請しない・`enumerated_count` に数えないことを意味する(Q2。確定。CFS-K-3。interface 3.3 の 4)。
- 除外が包含に優先する(`include_patterns` に一致しても、除外に一致すれば対象外)。包含はファイルにだけ適用し、ディレクトリの枝刈りには使わない(`**/` を含む包含パターンのため)。
- 除外に一致したディレクトリを開かないので、権限がなく読めないディレクトリ(例: `lost+found`、Windows 共有の `System Volume Information`。いずれも推測。実機未確認)は、`exclude_patterns` で除けば列挙の失敗にならない。これが読めないディレクトリへの管理者の対処になる(4.4)。
- 通常ファイルだけを返すのは、FIFO などを開く・読むと戻らなくなるため(導出)。列挙は種別の判定(`stat` 相当)だけで、ファイルを `open` しない。取得でも、列挙後に FIFO に差し替えられた場合に備えて `O_NONBLOCK` で開く(6.1)。

### 4.2 シンボリックリンク(承認済みの案。CFS-P-6)

- `follow_symlinks=false`(既定): ファイル・ディレクトリを問わず、シンボリックリンクは列挙せず、たどらない。リンクを経由した重複や、ルートの外のファイルの読み取り(コンテナ内の別のパスを含む)を避けるため、安全側を既定にした。
- `follow_symlinks=true`: リンクの先が通常ファイルなら、そのリンクの相対パスを `external_id` として列挙する。先がディレクトリなら、その配下を走査する。ただし次のリンクは**無視する**(エラーにしない)。
  - 壊れたリンク: 先がない(`ENOENT`。Python は例外にせず「ファイルでもディレクトリでもない」と返す)、リンクの循環(`ELOOP`)、先に至る途中が通常ファイルなど(`ENOTDIR`)。種別の判定でこれらの `OSError` が出たときも同じく無視する。
  - 先の実パスが `root` の外にあるもの。内外の判定: リンクの実パス(`realpath`)を `p`、`root` の実パスを `root_real` として、`os.path.commonpath([root_real, p]) == root_real`(`p` が `root_real` と等しいか配下)なら内。コンテナ内の別のパスを読まないための制限で、ホスト側の絶対パスを指すリンクは、コンテナにマウントされていなければ壊れたリンクと同じ扱いになる。`root_real` が `/` なら、すべて内になる。
  - 先のディレクトリが、現在の走査の経路にすでにある(祖先へのループ。`root` 自身を指すリンクを含む)。判定は、リンクで入るディレクトリ(`DirEntry.is_symlink()` が真)だけに行い、経路上のディレクトリの `(st_dev, st_ino)` との一致で見る。この組は `follow_symlinks=true` のときだけ、ディレクトリに入るたびに求めて持つ(`st_ino` が不安定なファイルシステムの可能性は 11.1)。
  - 上記以外の `OSError`(リンクの先の親が通れない `EACCES` など)は無視せず、列挙の失敗にする(4.4)。
- 同じファイルへ複数のリンクがあれば、パスごとに別の文書になる(`external_id` が別のため)。
- 取得時のリンクの検査は、`follow_symlinks=false` のときの最後の構成要素に限る(6.1)。列挙と取得の間でリンクに差し替える操作は防がない(共有への書き込み権限を持つ者に限られるため、MVP の信頼の前提で許容する。導出)。

### 4.3 隠しファイル(承認済みの案。CFS-P-7)

- 隠しファイル・ディレクトリは、名前が `.` で始まるもの(`.git`、`.DS_Store`、`._foo` など)。Unix の慣習だけを見る。Windows の「隠し」属性は見ない(共有のマウントでは属性が見えない場合があるため。推測)。
- 既定は対象外(`include_hidden=false`)。`.git` や macOS の付属ファイルなどを除くため。
- `root` 自体や、`root` より上のパスに `.` で始まる名前があっても影響しない(`root` の配下の名前だけを見る)。

### 4.4 エラー(承認済みの案。CFS-P-11)

列挙のエラーを握りつぶさない。一部でも列挙できなければ `Completed` にせず `Failed` にする(interface 3.3 の 2。PD v0.19 5.2・8.2。確定。CFS-K-4)。architecture 4.8 により、ジョブは `failed`(`enumeration_failed`)になり、終了通知は `outcome=failed` で、削除は起きない。

| 箇所 | 失敗 | 結果 |
| --- | --- | --- |
| `root` のディレクトリの読み取り | 7.1 の root の行 | `source_not_found` / `source_access_denied` / `source_unreachable` |
| `root` 以外のディレクトリ | 開けない、走査の途中で読み取りに失敗する(`ENOENT`・`EACCES` を含むすべての `OSError`) | `enumeration_incomplete` |
| エントリの種別の判定、`realpath`・`stat`(祖先の判定)など走査ループ内の呼び出し | `OSError`。ただし「エントリが消えていた」(`ENOENT`。Python が吸収して存在しない扱い)と、`follow_symlinks=true` のリンクの `ENOENT`・`ELOOP`・`ENOTDIR`(壊れたリンク。4.2)は無視する | 上記以外は `enumeration_incomplete` |

走査ループ全体の `OSError` は、上の表に載る箇所を問わず `enumeration_incomplete` にする(無視するのは表の例外だけ)。

- エントリが読み取りの間に消えたのは、interface 3.3 の 2(列挙の間ずっと存在し続けた文書は必ず返す)に反しないので無視してよい。一方、ディレクトリが開く前に消えた場合(`read_dir` は走査の順番が来たときに呼ぶので、一覧を得てから開くまでに間が空く。9.1)は、マウントの外れと区別できないため `enumeration_incomplete` にする(安全側。導出)。共有が活発で走査中にディレクトリが削除されると、そのクロールは `failed` になりうる(次のクロールで取り戻せるため許容する)。
- 説明文には errno 名と該当ディレクトリの相対パスを入れる(7.3)。管理者がどのディレクトリを `exclude_patterns` で除くか判断できるようにするため。ジョブ記録の `failure_detail` に載る(architecture 3.3.1・4.8、CA-P-45。7.3)。ログ(9.4)にも出る。
- 管理者の対処: 権限の修正、または `exclude_patterns` でそのディレクトリを除く(4.1)。

### 4.5 ストリーミング・順序・重複(承認済みの案。CFS-P-12、CFS-P-29)

- `next()` は走査しながら 1 件ずつ返す。深さ優先で、スタックには未走査のディレクトリの `(パス, 相対パス, 祖先)` だけを積み、`read_dir` はスタックから取り出したときに呼ぶ。エントリ一覧がメモリに載るのは処理中の**1 ディレクトリだけ**で、一覧は全件読み切って `scandir` を閉じてから処理する(開いたままにしない)。文書の全件は持たない(interface 3.3 の 6)。スタックは未走査のディレクトリの数だけ伸びる(1 件は小さい。9.3)。
- 返す順序は規定しない(並べ替えない。同じディレクトリのエントリの順、ファイルを返してからサブディレクトリへ入るか否かも規定しない)。テストは集合で比較する。
- `follow_symlinks=false` なら同じパスを 2 度返さない。`true` でも、パスは走査の経路で一意(重複は共通処理が除く。interface 3.3 の 5)。
- `DocumentRef` は `external_id`(ルートからの相対パス。区切りは `/`)と `locator`(同じ相対パス)を持つ。どちらも OS の名前を加工しない(8.1)。`size_hint` は返さない(5.5)。
- **終端後・`close()` 後の `next()`**(実装で決めた内容。CFS-P-29): 列挙が失敗(`ConnectorError` などの例外)で終わった後の `next()` は、同じ例外をもう一度送出する(例外で終わったジェネレータをそのまま進めて `Completed` を返さないため)。`Completed` を返した後の `next()` は `Completed` を返し続ける。`close()` の後の `next()` は、契約外の呼び出しとして例外(`RuntimeError`)にする。この例外は共通処理が `connector_internal_error` に変換する。`close()` は走査のジェネレータを閉じて、未走査のディレクトリのスタックを捨てる(未完了のまま終わる。interface 3.3 の 1)。

---

## 5. 文書メタデータ

### 5.1 項目の値

| 項目 | FS の値 | 得る時点 |
| --- | --- | --- |
| `external_id` | ルートからの相対パス(区切りは `/`、先頭に `/` を付けない)。**規則適用前**の値を返す(NFC・`\` の置換・検証は共通処理。interface 5.1)。CFS-K-7 | 列挙 |
| `path` | `external_id` と同じ相対パスを NFC にした値(5.3) | 取得 |
| `url` | なし(渡さない。CFS-K-8) | |
| `title` | ファイル名(拡張子を含み、ディレクトリを含まない)を NFC にした値(5.3) | 取得 |
| `mime_type` | 5.2 | 取得 |
| `source_updated_at` | ファイルの `mtime`(5.4) | 取得 |
| `size`・`content_hash` | 渡さない(共通処理が送る原本から導出。interface 5.4) | |

### 5.2 MIME 対応表(導出。承認済みの案 CFS-P-16)

拡張子(最後の拡張子を小文字にしたもの)から決める。Indexer の抽出が対応する基準 MIME(`text/plain`、`text/markdown`、`text/x-markdown`、`text/html`、`application/pdf`。`extractor.py`)に合わせた。パラメータ(`charset` など)は付けない(文字コードは Indexer が判定する。PD v0.19 4.2)。

| 拡張子 | `mime_type` |
| --- | --- |
| `.txt` | `text/plain` |
| `.md`、`.markdown` | `text/markdown` |
| `.html`、`.htm` | `text/html` |
| `.pdf` | `application/pdf` |
| 上記以外(`include_patterns` で追加した拡張子、拡張子なし) | `application/octet-stream`(案) |

- 対応外の拡張子を包含パターンで追加した場合、FS は拒否せず `application/octet-stream` で取得する(CI-P-16)。Indexer は抽出できず、`unsupported_mime_type` の `extract_failed` として、タイトルとメタデータだけを登録する(interface 4章。README 6章)。本文は検索できない。このとき `extract_failed` は `error_count` に数えられるが、ジョブの状態には影響しない(architecture 4.2、7.7)。

### 5.3 `title`・`path`(CI-U-8 への回答。承認済みの案。CFS-P-14)

- `title` = ファイル名(拡張子を含む)。ファイル名は空にならないため、取得できない場合の値は不要。拡張子を含めるのは、SD v0.8 1.1・api 4.3 の「ファイル名」の字義どおりにし、同じ場所の `a.pdf` と `a.txt` を区別できるようにするため。
- 内容から `title` を取らない(HTML の `<title>`、Markdown の見出し、PDF のメタデータなど)。Indexer の抽出は本文だけを返し、`title` を返さないため、内容から取るには Crawler に形式ごとの解析が要る。MVP の範囲を超えるので、含めない(2026-11-16 のユーザー承認で、ファイル名のみで案どおり承認。CFS-U-3 は解消)。内容から取る場合は、Crawler の形式ごとの解析と Indexer 設計との分担を決める改版が先で、ユーザー判断が要る。
- `title`・`path` は NFC にする。Indexer は `external_id` と本文だけを NFC にし、`title`・`path` は正規化しない(`document_id.py`、`normalization.py` で確認)ため、macOS 由来の NFD の名前がそのまま検索・表示に出るのを避ける。孤立サロゲートは変えず、そのまま返す(共通処理が表示用に置換する。interface 4章)。
- 改行・タブを含む名前もそのまま返す(api 3.3 の検証規則に `title`・`path` の制御文字の規則はない。確認)。長さは、ファイル名が 255 バイト(Linux の `NAME_MAX`)、相対パスが 4096 バイト未満(`PATH_MAX` に `root` を含むため)に収まる(一般的な Linux の上限。推測。実機未確認)。

### 5.4 `source_updated_at`(CI-U-5 への回答。承認済みの案。CFS-P-15)

- ファイルの `mtime` を、取得時に開いたファイルの `fstat`(`st_mtime_ns`)から得て、UTC のタイムゾーン付きの日時にする。ナノ秒からマイクロ秒への変換は `ns // 1000`(切り捨て。Indexer がミリ秒精度に正規化する。api 3.6)とする(SD v0.8 1.1・api 4.3 の「ローカルでは `mtime`」。いずれも案・提案)。内容と同じ読み取りで得る(interface 4章)。
- `mtime` は必ず得られる。日時として表せない値(年が 1〜9999 の範囲外。求め方により `ValueError`(`datetime.fromtimestamp`。確認)か `OverflowError`(実装の式。下)になるので、どちらも対象にする)のときだけ、固定値 `1970-01-01T00:00:00Z` にする(取得のたびに値が変わってメタデータが毎回更新されるのを避けるため。導出)。
- 実装は `1970-01-01T00:00:00Z + timedelta(microseconds=mtime_ns // 1000)` で求める(浮動小数の丸めを避ける)。範囲外のとき実際に出る例外は `OverflowError` で、`ValueError` も同じく固定値にする。`1970` 年より前の `mtime` は、年が範囲内なら、そのまま日時になる(実装のテストで、年 0・10000・巨大値を固定値にすることを確認した。0008 §5)。

### 5.5 `size_hint`(architecture 13.7 への回答。承認済みの案。CFS-P-13)

**返さない**(`None`)。理由: (1) 列挙で `size_hint` を得るにはファイルごとに `stat` が要り、列挙が重くなり、`stat` の失敗の扱いも増える。(2) 取得で `open` 後の `fstat` の大きさを確認すれば、**内容を読む前に**上限超過を判定でき(6.1)、`size_hint` による事前判定(architecture 6.5)と同じ効果になる。(3) 列挙と取得の間で大きさが変わっても、取得時の値が正になる。

---

## 6. 取得

### 6.1 手順(`fetch(ref, max_bytes)`。承認済みの案。CFS-P-17)

1. `ref.locator`(相対パス)を検査する。絶対パス、`..` のセグメント、NUL を含むなら `fetch_not_found`(`locator` は列挙が返した値なので通常は起きない。`root` の外を読まないための防御)。`root` と `/` で結合してパスにする。
2. `os.open` で `O_RDONLY | O_NONBLOCK | O_CLOEXEC`(`follow_symlinks=false` のときは `O_NOFOLLOW` を加える。最後の構成要素がリンクなら `ELOOP`)で開く。`O_NONBLOCK` は、列挙の後で FIFO に差し替えられても `open` が戻らなくなるのを防ぐためで、通常ファイルの読み取りには影響しない。
3. `fstat` で 1 回目の状態(`st_size`、`st_mtime_ns`)を得る。通常ファイルでなければ(列挙の後でディレクトリ・FIFO などに変わった。この確認の前に内容を読まない)`fetch_not_found`。`st_size > max_bytes` なら、**読まずに** `oversize`。
4. `max_bytes + 1` バイトまでを上限に読み切る(読み取りの単位は 1 MiB。仮値)。`max_bytes` を超えたら中断して `oversize`(ファイルが大きくなった場合)。
5. もう一度 `fstat` する。`st_size` と `st_mtime_ns` が 1 回目と違う、または読んだバイト数が `st_size` と違うなら、取得中に変更されたとして `fetch_transient`(interface 7章)。
6. 5.1 のメタデータ(`source_updated_at` は 2 回目の `fstat` の値)とバイト列を返す。ファイルは必ず閉じる。

- 読み取り中の `OSError` は 7.1 の分類にする。サイズの確認から読み取りまでは同じ `fd` を使い、確認と読み取りの間でファイルが差し替わる食い違いを避ける。
- 契約外の引数は例外にする(実装で決めた内容): `max_bytes` が負、または `ref.locator` が文字列でないときは、`ValueError`・`TypeError` を送出する。呼び出し側の不具合で、共通処理が `connector_internal_error`(document)に変換する(7.3)。
- 取得中の変更の検出は最善の努力にとどまる(`mtime` の粒度が粗い、サイズが同じ書き換え、共有側が `mtime` を遅れて更新する場合は検出できない。推測)。検出できなくても、`content_hash` と `size` は共通処理が送るバイト列から算出するため、Indexer に送る値の間は食い違わない(interface 5.4)。
- `fstat` の大きさが実際の内容と一致しないファイルシステム(推測。一部の特殊なファイルシステム)では、手順 5 が毎回失敗する。対象は通常のローカル・NFS・SMB のファイルとする。

### 6.2 `oversize`(CFS-K-9。CI-K-10、CI-U-3 への対応)

- `max_bytes` は共通処理が渡す(Crawler の `max_raw_bytes`。architecture 6.5)。FS は上限の値を持たない。
- 上限を超える原本は、手順 3(読む前)か手順 4(読み取り中)で `oversize` にする。メモリには `max_bytes` を超える内容を載せない。リトライ・記録・終了通知への載せ方は architecture 6.5。

### 6.3 権限エラー

読めないファイル(`EACCES`・`EPERM`)は `fetch_permission_denied`(permanent)。architecture 6.2 により、リトライせずその文書をスキップし、スキップ記録を残す(CFS-K-6)。PD v0.19 は「数回リトライしても失敗したらスキップ」と書くが、権限エラーは再試行しても直らないため、本設計は即スキップの案を維持する(architecture 6.2、CA-P-19。PD との差は architecture 13.5 の I-8)。管理者は Admin View で確認し、アクセス権の修正か `exclude_patterns` での除外で解消して再実行する(PD v0.19 2章・4.6)。スキップ記録の `reason` は分類名と短い固定文で、対象の文書は記録の `external_id` で分かるため、errno・パスの説明文は要らない(architecture 3.3.3)。読めない**ディレクトリ**は、文書単位でなく列挙の失敗になる(4.4。管理者に説明文を届ける経路は 7.3・11.6)。

---

## 7. エラー分類

### 7.1 errno と分類名の対応(承認済みの案。CFS-P-11)

分類名・`scope`・`retry` は interface 6.2 のとおり。ここでは FS の発生条件との対応を示す。

**集合 T**(到達不能・一時障害の errno。暫定。承認後も実機での確認後に見直す。CFS-U-4): `EIO`、`ESTALE`、`ETIMEDOUT`、`ENOTCONN`、`EHOSTDOWN`、`EHOSTUNREACH`、`ENETDOWN`、`ENETUNREACH`、`ECONNREFUSED`、`ECONNRESET`、`ECONNABORTED`、`ENODEV`、`EBUSY`。

| 発生点 | 条件 | 分類名(scope・retry) |
| --- | --- | --- |
| `validate_config` | 2.2 の違反 | `config_invalid`(source・permanent) |
| `create`、列挙の `root` の読み取り | `ENOENT`、`ENOTDIR`、`ELOOP`、`ENAMETOOLONG`(ルートが存在しない・ディレクトリでない・たどれない) | `source_not_found`(source・permanent) |
| 同上 | `EACCES`、`EPERM` | `source_access_denied`(source・permanent) |
| 同上 | 集合 T の errno | `source_unreachable`(source・transient) |
| 同上 | 上記以外の `OSError` | そのまま送出(共通処理が `connector_internal_error` に変換。source・unknown) |
| 列挙の `root` 以外 | 4.4 の失敗(errno を問わない) | `enumeration_incomplete`(source・unknown) |
| `fetch` | `ENOENT`、`ENOTDIR`、`EISDIR`、`ELOOP`(`O_NOFOLLOW`)、通常ファイルでなくなった | `fetch_not_found`(document・permanent) |
| `fetch` | `EACCES`、`EPERM` | `fetch_permission_denied`(document・permanent) |
| `fetch` | 集合 T の errno、取得中の変更 | `fetch_transient`(document・transient) |
| `fetch` | 原本が `max_bytes` を超える | `oversize`(document・permanent) |
| `fetch` | 上記以外の `OSError`(`EMFILE` など Crawler 側の資源の不足を含む) | そのまま送出(共通処理が `connector_internal_error` に変換。document・unknown) |
| 共通処理 | 相対パスの先頭が `/` になる(先頭が `\` のファイル名)、空・NUL・4096 バイト超(8.5) | `invalid_external_id`(document・permanent) |
| 共通処理 | `\`・NFC/NFD で同じ `document_id` になる別のファイル(8.4) | `external_id_collision`(document・permanent) |

- 表の「そのまま送出」は、`FileSystemConnector` が `OSError` を分類せずに投げることを指す。`validate_config`・`create` の分は `connectors` のレジストリの保護ラッパが、列挙・取得の分は `documents` が、`connector_internal_error` に変換する(interface 3.2、module-structure CM-P-7)。
- 実装の errno の集合は、表と集合 T のとおり(`connectors/filesystem/errors.py`)。`fetch` の `fetch_not_found` の errno は `ENOENT`・`ENOTDIR`・`EISDIR`・`ELOOP`、ルートは `ENOENT`・`ENOTDIR`・`ELOOP`・`ENAMETOOLONG`。

### 7.2 マウント外れの判定

3.3 のとおり、起点のパスがない・たどれない(`ENOENT`・`ENOTDIR`・`ELOOP`・`ENAMETOOLONG`)は `source_not_found`、到達できないだけ(集合 T)は `source_unreachable` とする。判定は errno で行い、ルートの確認は `create` で行う(3.2)。

### 7.3 説明文と例外の変換(承認済みの案 CFS-P-18。実装で決めた内容 CFS-P-28)

説明文は、固定文に errno 名と該当パスを足した形にする(例: 「ディレクトリを読み取れない: ESTALE, `docs/a`」)。パスは、ルートの失敗では `root`、配下の失敗では相対パスで、長さを 200 文字に切り詰め(仮値)、制御文字は `\n` のようにエスケープする。ファイルの内容・認証情報は含めない。管理者が、どのディレクトリを権限修正・除外すべきか判断するのに必要なため(4.4)。

この説明文は、architecture 3.3.1・4.8 の `failure_detail`(分類名に加えて Connector の説明文を載せてよい。案。CA-P-45)に載り、管理者に届く(Admin View に出る)。interface 6.1 の説明文の定義も同様に緩和されている(案。CI-P-17)。ログ(9.4)にも出る。

実装で決めた内容(CFS-P-28):

- **分類した `ConnectorError` は、元の `OSError` を traceback に出さない**(`raise ... from None`。元の例外は Python の仕様で `__context__` に残るが、`__suppress_context__` が真で、`logger.exception` などの出力に出ない)。`OSError` は、制御文字を含みうる未加工のパス(ファイル名の `repr`)を持っていて、`logger.exception` で出るとログの行の偽造になる(architecture CA-P-48、module-structure R11)。管理者や診断に必要な情報(errno 名と、切り詰め・エスケープ済みのパス)は説明文が持つ。トレードオフ: 元の例外の発生箇所(ファイル名・行)が、ログの出力から失われる(診断の方法は interface 3.2 の提案)。
- 分類できない `OSError` は、そのまま送出する(上の注記)。共通処理の変換でも `from None` で元の例外を出さず、`connector_internal_error` の説明文は**例外の型名(`OSError` なら errno 名)だけ**にする。例外のメッセージにはパスや設定値が入りうるため。
- 設定違反の説明文(2.2)にも入力値を入れない(未知のキーの名前、パターンの内容を含む)。

---

## 8. ファイル名・文字の扱い

識別子の規則(NFC、`\` の置換、孤立サロゲートのエスケープと表示用置換、検証)は共通処理が一律に適用する(interface 5.1)。ここでは、FS で何が起きるかと、FS が守ることだけを書く。

### 8.1 孤立サロゲートの発生状況(説明のみ。承認済みの案 CFS-P-20)

- Linux のファイル名は、`/` と NUL を除く任意のバイト列として扱われる(一般的な Linux の仕様。実機未確認のため推測)。UTF-8 でない名前(CP932・EUC-JP の旧環境で作られた名前、文字コードを指定せずに展開した zip、文字コードの設定がない共有)が存在しうる。
- Python は OS の名前を `os.fsdecode`(UTF-8 と `surrogateescape`)で `str` にする。UTF-8 として不正な 1 バイト 0xXX は、孤立サロゲート U+DC00 + 0xXX(U+DC80〜U+DCFF)の 1 文字になる(確認: `\x82\xa0` は `'\udc82\udca0'`)。`os.fsencode` で元のバイト列に戻せるため、この `str` のまま `open` でき、`locator` に使える。
- FS が守ること: `external_id`・`locator` は OS の名前を加工せずに返す(NFC・置換・トリムをしない。ID 用エスケープは共通処理が NFC の前に行う前提のため)。`title`・`path` は NFC だけを適用し、孤立サロゲートは変えない(`unicodedata.normalize` は孤立サロゲートを変えない。確認)。
- Crawler の Python のファイルシステムエンコーディングが UTF-8 であることを前提とする(確認した環境では `utf-8` と `surrogateescape`。コンテナでの確認はテスト 18)。前提が崩れると、どのバイトが孤立サロゲートになるかが変わり `external_id` が変わるため、`create` で `FsOps.filesystem_encoding()`(既定は `sys.getfilesystemencoding()`)が UTF-8 であることを確認し、違えば `connector_internal_error`(source。説明文は「ファイルシステムのエンコーディングが UTF-8 でない: 名前」)で失敗させる(承認済みの案 CFS-P-22)。実装はこの方式を選んだ(CFS-P-27。実装で決めた内容)。確認は `FsOps` 経由なので、テストは偽の `FsOps` で UTF-8 でない場合を再現できる。比較は `codecs.lookup(名前).name == "utf-8"` で行い、`UTF-8`・`utf8` などの別名も UTF-8 とみなす。エラーハンドラ(`surrogateescape`)は確認しない。代替の「名前を `bytes` で受けて UTF-8 と `surrogateescape` で明示的に復号する方法(ロケールに依存しない)」は採っていない。実運用のコンテナイメージでの確認は残る(CFS-U-4)。

### 8.2 NFD / NFC

- macOS 由来のファイル名は NFD で保存されうる(推測)。共通処理が NFC にするので、NFC の名前と同じ `external_id` になる(interface 5.1)。`title`・`path`・パターンの照合も NFC にそろえる(5.3、2.3)。
- 同じディレクトリに、見た目が同じ NFC の名前と NFD の名前が併存すると、同じ `document_id` になる(衝突。8.4)。確認した macOS(APFS)では、NFC と NFD の名前を同じファイルとして扱い、併存できなかった。併存できるのは Linux のファイルシステムの場合(推測。実機未確認)。

### 8.3 `\`・改行・タブ

- `\` を含む名前: FS は加工せず返し、共通処理が `external_id` で `/` に置き換える(interface 5.1。I-10)。`path`・`title` には `\` が残る。パターンでは `\` を書けないので、`?` で一致させる(2.3)。
- 改行・タブを含む名前: `external_id` で許可される(K59)。FS は加工せず返す。ログ・説明文では制御文字をエスケープする(7.3、9.4)。

### 8.4 衝突への対応(interface 5.3、I-10。承認済みの案。CFS-P-19)

FS で起きうる衝突は 2 つ: (a) ルート直下の `a\b.txt` とディレクトリ `a` の中の `b.txt`(`\` の置換)、(b) NFC と NFD で同じになる名前の併存(8.2)。

- 検出は共通処理が行う(interface 5.3)。扱いは architecture の案(ジョブ `failed`。CA-P-24。2026-11-16 のユーザー承認で案どおり承認。CA-U-6・CFS-U-5 は解消)に従い、FS は**特別な回避をしない**。理由: (1) 発生は稀と見込まれる(推測)。(2) どちらかを黙って外すと、列挙の完全性の説明が曖昧になる。(3) FS は、どちらを残すべきか判断できない。
- この案では、衝突が残る間、そのソースのクロールは毎回 `failed` になる(1 組で全体が止まる)。architecture の案(CA-P-45)では、`failure_detail` には後に検出された 1 件の(切り詰めた)`external_id` と共有する `document_id` だけが載る(先に列挙された 1 件の文字列は手元に残らないため)。もう 1 件は、同じ `document_id` になる別表記(NFC/NFD、`\` と `/` の違い)のファイルである。管理者は、表示された側を `exclude_patterns` で除く(`\` は `?` で一致させる)か、ファイルの名前を変えて、衝突を避ける。影響が大きい場合の緩和(例: `\` を含む名前を FS が列挙しない)は、MVP では運用で対応し、必要になった時点で本書の改版とユーザー判断で決める(承認の際の方針。CFS-U-5 は解消)。
- 大文字小文字だけが違う名前は、別の文書になる(確定。CFS-K-7)。大文字小文字を区別しないファイルシステム(確認した macOS の APFS は区別せず、`Case.txt` と `case.txt` が同じファイルになった)では併存できない。この場合、大文字小文字だけの名前変更は、旧 ID の削除と新 ID の追加になる(CI-K-9)。

### 8.5 長いパス

`external_id` は UTF-8 で 4096 バイト以内(K59)。Linux の `PATH_MAX` は 4096 バイト(`root` を含む。一般的な上限。推測)なので通常は収まるが、不正なバイトを含む名前は、ID 用エスケープで 1 バイトが 8 バイト(U+FFFD の 3 バイト + `u` + 4 桁)に増えるため、超えることがある。超えた文書は `invalid_external_id` で、登録されず、`invalid_id_count` に数えられる(architecture 7.7)。

---

## 9. 実装に必要な細目

### 9.1 処理手順(疑似コード)

```
# OS 呼び出し(stat・scandir・realpath・open・fstat・read・close・filesystem_encoding)は、すべて FsOps 経由(9.2)。
create(source_id, connector_config):
    config = validate_config(connector_config)      # 2.2。I/O なし。patterns は NFC にしてセグメントに分ける(正規表現にしない。2.3)
    if fs.filesystem_encoding() が UTF-8 でない: raise connector_internal_error   # 8.1(CFS-P-27)
    stat(config.root)                               # ルート自体のリンクはたどる
        # 失敗 -> 7.1 の root の行。ディレクトリでなければ source_not_found
    scandir(config.root) を開いて閉じる             # 権限・I/O の確認
    root_real = realpath(config.root) if config.follow_symlinks
    return FileSystemConnector(config, root_real)

# join(base, name) = base.rstrip("/") + "/" + name。root が "/" のとき "//name" にしない
enumerate():                                        # EnumerationStream
    # ancestors: 経路上のディレクトリの (st_dev, st_ino)。follow_symlinks=true のときだけ持つ(4.2)
    stack = [ Dir(path=root, rel_prefix="", is_root=True,
                  ancestors=(dev_ino(root),) if follow_symlinks else ()) ]
    while stack:
        d = stack.pop()
        entries = read_dir(d.path, d.is_root)       # 取り出したときに読む。メモリに載るのは 1 ディレクトリ分
        # 以下のループ内の OSError(stat・realpath・dev_ino・inside を含む)は
        # enumeration_incomplete(4.4)。classify が無視すると決めた errno だけを除く
        for e in entries:
            if not include_hidden and e.name.startswith("."): continue            # 順1
            rel = d.rel_prefix + e.name             # 区切りは "/"。加工しない
            kind = classify(e)                      # 順2。"file" | "dir" | None(対象外)
            if kind is None: continue
            key = nfc(rel) if (exclude または include のパターンあり) else None   # matches_any は多項式時間(2.3)
            if kind == "dir":
                if matches_any(exclude, key): continue                            # 順3。開かない
                anc = ()
                if follow_symlinks:
                    di = dev_ino(e.path)
                    if e.is_symlink() and di in d.ancestors: continue             # 祖先へのループ
                    anc = d.ancestors + (di,)
                stack.push(Dir(path=e.path, rel_prefix=rel + "/", is_root=False, ancestors=anc))
            else:                                   # "file"
                if matches_any(exclude, key): continue                            # 順3
                if not (default_ext(e.name) or matches_any(include, key)): continue   # 順4
                yield DocumentRef(external_id=rel, locator=rel, size_hint=None)
        # ファイルを返してからサブディレクトリへ入る順序は規定しない(4.5)
    return Completed                                # 終端なしで終わらない(interface 3.3)

read_dir(path, is_root):
    try:    with scandir(path) as it: return list(it)      # 全件読み切って閉じる(9.2)
    except OSError as x:
        raise map_root_errno(x) if is_root else enumeration_incomplete(x, path)

classify(e):
    try:
        if not e.is_symlink():
            if e.is_dir(follow_symlinks=False):  return "dir"
            if e.is_file(follow_symlinks=False): return "file"
            return None                             # FIFO・ソケット・デバイス・消えたエントリ
        if not follow_symlinks: return None
        if not inside(root_real, realpath(e.path)): return None   # 先が root の外(4.2)
        if e.is_dir(): return "dir"                 # 壊れたリンクは False
        return "file" if e.is_file() else None
    except OSError as x:
        if e.is_symlink() and follow_symlinks and x.errno in (ENOENT, ELOOP, ENOTDIR):
            return None                             # 壊れたリンク(4.2)
        raise enumeration_incomplete(x, e.path)     # EACCES など

inside(root_real, p) = commonpath([root_real, p]) == root_real

fetch(ref, max_bytes):                              # 6.1
    rel = ref.locator;  rel が絶対・".."・NUL を含む -> fetch_not_found
    flags = O_RDONLY | O_NONBLOCK | O_CLOEXEC | (0 if follow_symlinks else O_NOFOLLOW)
    try:
        fd = open(join(root, rel), flags)
        try:
            s1 = fstat(fd)
            if not is_regular(s1): raise fetch_not_found     # FIFO などは読まない
            if s1.size > max_bytes: raise oversize
            data = read_up_to(fd, max_bytes + 1)         # 1 MiB ずつ
            if len(data) > max_bytes: raise oversize
            s2 = fstat(fd)
            if (s2.size, s2.mtime_ns) != (s1.size, s1.mtime_ns) or len(data) != s2.size:
                raise fetch_transient                    # 取得中の変更
        finally: close(fd)
    except OSError as x: raise map_fetch_errno(x)        # 7.1。未分類の errno はそのまま送出
    return FetchedDocument(data, DocumentMetadata(
        title=nfc(basename(rel)), path=nfc(rel), mime_type=mime_of(rel),
        source_updated_at=utc(s2.mtime_ns // 1000 µs) または範囲外なら 1970-01-01T00:00:00Z))   # url なし

EnumerationStream.close(): スタックを捨てる。close() の後の next() は例外にする(4.5。CFS-P-29)
                           (列挙は Completed にも Failed にもならず未完了のまま終わる。interface 3.3 の 1)
Connector.close():         何もしない(保持する資源がない)
```

### 9.2 実装上の注意(Python)

- **`os.walk`・`glob`・`pathlib` の `rglob` は使わない**(案。CFS-P-12)。いずれも `OSError` を握りつぶす。CPython の 3.12.11 と 3.13.4 のソースで確認した: `os.walk` は `entry.is_dir()` の `OSError` を「ディレクトリでない」として扱い(`onerror` では検出できない)、`glob` は `scandir` の `OSError` を無視し、`pathlib.Path.rglob` は権限のないディレクトリを黙って飛ばす(11.1)。SD v0.8 3.1 の「`os.walk` の `onerror` で検出する」では不十分(I-30)。`os.scandir` を直接使い、4.4 の規則で例外を送出する。
- **`scandir` は全件を読み切って閉じる**(`list(it)`)。深い木で、走査の経路の分だけ `fd` を開いたままにしないため(CPython の `glob` も同じ理由で閉じている)。1 つのディレクトリの全エントリがメモリに載る(9.3)。
- `DirEntry.is_dir()`・`is_file()` は、エントリが存在しない(壊れたリンク、消えた)ときは例外にせず `False` を返す。リンクの循環は `ELOOP`、リンクの先に至る途中が通常ファイルなら `ENOTDIR`、先の親ディレクトリが通れなければ `EACCES` を `OSError` として送出する(確認)。`follow_symlinks=true` のリンクの `ENOENT`・`ELOOP`・`ENOTDIR` は壊れたリンクとして無視し、`EACCES` などは列挙の失敗にする(4.2、4.4)。種別の判定を `follow_symlinks=False` で行えば、通常のエントリはリンクをたどらない。
- 名前は `str` のまま扱う(OS が返す名前を `surrogateescape` で受ける。8.1)。`bytes` のパスと混在させない。
- 読み取りは `os.open`・`os.fstat`・`os.read`(同じ `fd` を使い、サイズの確認と読み取りの食い違いを避ける)。時刻は `st_mtime_ns` から整数演算で求める(浮動小数の丸めを避ける)。
- パターンは `create`(と `validate_config`)で 1 度だけ NFC にしてセグメントに分け、照合は 2.3 の多項式時間のアルゴリズムで行う。**正規表現(`re`)は使わない**(CFS-P-25)。
- **OS 呼び出しの窓口 `FsOps`**(CFS-P-26。実装で決めた内容。注入の方式は module-structure CM-P-9): FS は OS を直接呼ばず、すべて `FsOps` を通す。`FileSystemConnectorType` の生成時に渡し、既定は `os` を呼ぶ実装。テストは、呼び出しの時点を制御できる偽の `FsOps` を渡して、列挙・取得の途中の変更(消失・差し替え・サイズ変更)を再現する(10章のテスト 13・15・17)。失敗は `OSError` で表す(`os` と同じ)。操作は読み取りだけで、書き込み・削除・属性変更を持たない(CFS-K-2)。
  - `scandir(path)`(`os.scandir`。`DirEntry` 相当は `name`・`path`・`is_symlink`・`is_dir`・`is_file` を使う)、`stat(path)`(リンクをたどる)、`realpath(path)`、`open(path, flags)`、`fstat(fd)`、`read(fd, 最大バイト数)`、`close(fd)`、`filesystem_encoding()`。
  - `stat`・`fstat` の結果は、使う項目だけの値(種別を表す `mode`、`size`、`mtime_ns`、`st_dev`、`st_ino`)にする。
- **入出力の停止**: ハードマウントの共有が応答しないと、`scandir`・`read` が戻らず、Python の呼び出しは中断できない(推測)。ハートビートはジョブ実行から独立して続くので(architecture 5.3)リースは切れないが、ジョブは進まない。リース期限内の `running` はロック解放できず(crawler-api 4.3: 409 `lock_in_use`)、脱出は Crawler の再起動による回復だけ(MVP。architecture 4.7、5.8、crawler-api 4.3)。並行モデルは module-structure の案に従う(CM-P-13。architecture CA-U-10)。NFS の `soft` マウントなどでの緩和は運用の領域で、実機で確認する(CFS-U-4)。

### 9.3 規模の見積もり(推測。実測していない。CFS-U-6)

想定規模は 1 万〜10 万文書(architecture 11章。目標値ではない)。

- Connector のメモリ: 処理中の 1 ディレクトリのエントリ一覧が主。`DirEntry` 1 件を数百バイトと見ると、1 万エントリのディレクトリで数 MB、10 万エントリで数十 MB(推測)。スタックは未走査のディレクトリ 1 件あたりパス・相対パス・祖先で数百バイト程度で、ディレクトリ数が 1 万なら数 MB(推測)。それ以外に、取得中の原本 1 件(最大 `max_raw_bytes`、仮値 20 MiB)。共通処理が持つ `document_id` の集合は architecture 7.7(10 万文書で 20 MB 前後)。
- 時間: 列挙はディレクトリの読み取りと、ファイルごとのパターンの照合(パターン 1 件あたり)が主で、取得(全件の読み取り。PD v0.19 4.1 の全件更新。CFS-K-10)に比べて小さい見込み。取得はファイルの大きさとストレージ・ネットワークの帯域に比例する(10 万ファイル・平均 100 KB で約 10 GB)。所要時間は実装後に実測する。
- 並行: MVP は直列(interface 1.2)。1 ファイルずつ取得する。
- **照合の最悪入力**(実装で決めた内容。CFS-P-31): 照合は多項式時間だが、細工した最悪に近い入力(1024 バイトのパターンと 4096 バイトのパス)では 0.2〜0.5 秒/件/パターンかかる(実装中のレビューでの実測。最大 100 パターンを細工し、名前も特殊な形に揃えた場合に限り影響する)。パターンは管理者が設定する値で、MVP は認証がなく、通常の運用では起きないため、許容した。必要になれば、(a) パスのセグメント数がパターンの `**` 以外のセグメント数に満たなければ即座に不一致とする、(b) `max_pattern_bytes` の既定値を下げる、を検討する(改版とユーザー判断が要る)。通常のパターンでの実測は、`*a` を 30 組並べたパターンと 60〜255 文字の名前で 0.03〜0.05 ミリ秒。

### 9.4 ログ

- 列挙の終了時に件数だけを INFO で出す: `source_id`、走査したディレクトリ数、返した文書数、無視した件数の内訳(隠し、リンク、その他の種別、除外、包含外、壊れたリンク、`root` の外を指すリンク、祖先へのループ)。ファイル名は出さない。
- エラー時だけ該当の相対パスを出す。長さを切り詰め、制御文字をエスケープする(`repr` 相当。7.3)。改行を含む名前でログの行を偽造されないため。
- ファイルの内容・認証情報を出さない。

---

## 10. テスト観点

interface 10章の共通の契約テストに加えて、FS 固有の観点。ファイルシステムの実物(一時ディレクトリ)で行う。

| # | 観点 | 期待 |
| --- | --- | --- |
| 1 | 既定の拡張子 | `.txt`・`.md`・`.markdown`・`.html`・`.htm`・`.pdf`(大文字の `.PDF` を含む)だけが返る。`.docx`・拡張子なし・`a.tar.gz` は返らない |
| 2 | 再帰 | 深い階層のファイルが返り、`external_id` がルートからの相対パス(先頭に `/` なし)になる |
| 3 | `include_patterns` | 追加した拡張子(`**/*.rst`)も返る。既定の拡張子は引き続き返る。`mime_type` は `application/octet-stream` |
| 4 | `exclude_patterns` | 一致するファイル・ディレクトリが返らず、除外ディレクトリを開かない(権限のないディレクトリを除外すると失敗しない)。包含に一致しても除外が優先 |
| 5 | パターン構文 | 2.3 の例の一致・不一致。`*` は `/` をまたがない。NFD の名前と NFC のパターンが一致する。違反(`**.md`、`**/**`・`a/**/**`、先頭の `/`、`\`、`..`)は `config_invalid`。`**/a/**/b` は有効。照合の計算量は #24 |
| 6 | 隠しファイル | 既定で `.hidden.md` と `.git/` 配下が返らない。`include_hidden=true` で返る。`root` の上位に `.` の名前があっても影響しない |
| 7 | シンボリックリンク(false) | ファイルへのリンク・ディレクトリへのリンクとも返らず、たどらない |
| 8 | シンボリックリンク(true) | ルート内を指すリンクは返る。壊れたリンク、循環(`ELOOP`・祖先へのリンク)、リンク先の途中が通常ファイル(`ENOTDIR`)、`root` の外を指すリンクは無視され、列挙は `Completed` になる。`root` 自身を指すリンクは祖先ループとして無視される。リンク先の親が通れない(`EACCES`)と `Failed`。`root=/` で内外の判定がすべて「内」になり、`external_id` に `//` が現れない。`root` 自体がシンボリックリンクでも列挙できる(`follow_symlinks=false` でも) |
| 9 | 通常ファイル以外 | FIFO・ソケットは返らず、列挙が止まらない |
| 10 | `Completed` と 0 件 | 空のルート、すべてが対象外のルートは、0 件で `Completed` になる(失敗にならない)。0 件警告(CA-P-52)は共通処理の責務で、architecture 12章のテスト 36 で確認する(FS 単体では、警告の有無でなく `Completed` と 0 件までを確認する) |
| 11 | `create` の確認 | ルートがない -> `source_not_found`。ファイルをルートにした -> `source_not_found`。権限なし -> `source_access_denied` |
| 12 | 列挙の失敗 | 読めない(権限のない)サブディレクトリがあると `Completed` にならず `Failed`(`enumeration_incomplete`)。説明文に相対パスと errno 名が入る。走査の途中でディレクトリを消すと `Failed` |
| 13 | 列挙中に消えたファイル | 種別の判定の前に消えたファイルは無視され、列挙は失敗しない |
| 14 | 取得 | 内容がそのまま返る。`mtime` が `source_updated_at` になる(範囲外の `mtime`(模擬。`ValueError`・`OverflowError`)は `1970-01-01T00:00:00Z`。ナノ秒は切り捨て)。`title`・`path`・`mime_type` が 5章の値。`url` なし。同じ `ref` を 2 回取得できる |
| 15 | `oversize` | `st_size > max_bytes` は読まずに `oversize`。読み取り中に大きくなるファイルも `oversize`。`max_bytes` ちょうどは成功 |
| 16 | 取得の失敗 | 列挙後に削除 -> `fetch_not_found`。権限なし -> `fetch_permission_denied`。ディレクトリに差し替え -> `fetch_not_found`。リンクに差し替え(`follow_symlinks=false`)-> `fetch_not_found`。FIFO に差し替え -> `fetch_not_found` で、ブロックしない(`O_NONBLOCK`) |
| 17 | 取得中の変更 | 読み取りの途中で内容(サイズ)を変えると `fetch_transient` |
| 18 | 文字(作成できる環境のみ。Linux) | 非 UTF-8 の名前(`b"\x82\xa0.txt"`)が `surrogateescape` の名前で返り、`locator` で取得できる。`external_id` は共通処理で ID 用エスケープされる。ファイルシステムエンコーディングが `utf-8` |
| 19 | `\`・改行・タブ・NFD | `a\b.txt`、改行・タブを含む名前が返り、取得できる。NFD の名前の `title`・`path` が NFC になる。`a\b.txt` と `a/b.txt` の併存を共通処理が検出する(扱いは CA-U-6) |
| 20 | errno の対応 | 7.1 の各 errno(`ENOENT`・`EACCES`・集合 T の代表)が表の分類名になる(`OSError` の模擬でよい)。表にない `OSError` は分類せず送出される |
| 21 | 設定の検証 | 未知のキー、`null`、`root` が相対パス・`..` を含む・連続する `/`・末尾の `/`(除かれる)・`/` だけ(有効)、真偽値に `0`・`1`・文字列、パターンが 100 件(有効)と 101 件、1024 バイト(有効)と 1025 バイトの境界、すべて期待どおり(`config_invalid` か有効)。I/O をしない |
| 22 | `locator` の検査 | `..`・絶対パス・NUL を含む `locator` は `fetch_not_found` |
| 23 | 読み取り専用 | FS が書き込み系の呼び出しをしない(`open` が読み取りのフラグだけ)。コンテナでは `:ro` のマウントに書き込めない(運用の確認) |
| 24 | 照合の計算量と正しさ(CFS-P-25) | `*a` を多数並べたパターン、離して並べた `**/a` などの指数的に延びる退行(正規表現のバックトラック)が起きないことを、時間の閾値(0.5 秒)で検出する。テストの入力は、実測が 50 ミリ秒以下のものに限り、9.3 の最悪ケース(0.2〜0.5 秒/件/パターン)は含まない(閾値は、爆発の退行だけを検出するためのもの)。小さいパターンとパスの全組み合わせで、素朴な参照実装(メモ化した再帰)と結果が一致する。2.3 の例の全行が期待どおり |
| 25 | `scandir` を閉じる(CFS-P-12) | `scandir` は全件を読み切ってから閉じ、深い階層でも同時に開くのは 1 つ。列挙の完了後・失敗後・`close()` 後に開いたままのものがない(偽の `FsOps` が開閉を数える) |
| 26 | 例外の変換(CFS-P-28) | 分類した `ConnectorError` は、元の `OSError`(未加工のパスの `repr`)を `from None` で隠し、ログに出る traceback に偽造された行や未加工のパスが出ない。分類できない例外の `connector_internal_error` の説明文は、型名(と errno 名)だけ |

- **注入点**: 13・15・17 は、ファイルシステムの実物のタイミングに依存すると不安定になるため、9.2 の `FsOps` に偽の実装(実際のファイルシステムへの呼び出しに、操作ごとの前処理と応答・例外の差し替えを足したもの)を渡して、`scandir`・`read` などの呼び出しの時点を制御し、決定的に書く。スレッドで待つ必要があるのは、FIFO を開いて戻らない退行をハングでなく失敗として検出するテスト(#9・#16)だけで、時間の経過を待つテストはない。
- **実行環境の注意**(CFS-P-30): 権限エラーのテスト(4、12、16)は、root で実行すると権限が効かずに成功してしまうため、root 以外で実行するか、root では skip する。非 UTF-8 の名前、NFC と NFD の名前の併存、大文字小文字だけが違う名前(#18・#19 の該当部分と大文字小文字のテスト)は、**OS の名前ではなく、実際にその名前を作れて、別のエントリとして残るかで判定**し、作れない環境では skip する。確認した macOS(APFS)は、非 UTF-8 の名前を作れず(`EILSEQ`)、NFC・NFD の名前、大文字小文字だけが違う名前を併存させられない(11.1)ので、これらは skip になる。Linux のコンテナで実行する。環境変数 `LORELEY_REQUIRE_LINUX_NAMES=1` を付けると、作れない環境でも黙って skip せず**失敗**にする(CI や Linux では付ける。macOS で付けると 3 件が失敗する)。

---

## 11. 確認状況

### 11.1 確認した事実(2026-11-13)

- interface 5.1・6.2・11.6、architecture 4.5・4.8・6.2・6.5・13.7、api 3.3・4.3、PD v0.19 4.1・4.2・5.2・8.1・8.2・2章、SD v0.8 1.1・3.1・6.4 の記述を読んだ。
- Indexer の抽出が対応する基準 MIME は `text/plain`、`text/markdown`、`text/x-markdown`、`text/html`、`application/pdf`。`;` 以降を除き小文字にして比較する(`extractor.py`)。
- api 3.3 の検証規則に、`title`・`path` の制御文字・長さの規則はなく、孤立サロゲートだけが文書単位の `document_rejected` になる。
- Indexer は `external_id` と本文だけを NFC にし、`title`・`path` は正規化しない(`apps/indexer/src` の `unicodedata` の使用箇所は `document_id.py` と `normalization.py` だけ)。
- Python 3.12.11 と 3.13.4 の標準ライブラリで: `os.walk` は `entry.is_dir()` の `OSError` を握りつぶす。`glob` は `scandir` の `OSError` を無視する(ソースで確認)。`pathlib.Path.rglob` は、権限のないディレクトリを例外にせず結果から黙って除く(両版で実行して確認)。
- Python 3.13.4(macOS)で: ファイルシステムエンコーディングは `utf-8`(`surrogateescape`)。`os.fsdecode(b"\x82\xa0")` は `'\udc82\udca0'` で、`os.fsencode` で元に戻る。`unicodedata.normalize("NFC", …)` は孤立サロゲートを変えない。`os.path.splitext(".md")` は `('.md', '')`。`datetime.fromtimestamp` は年が範囲外で `ValueError`。`DirEntry.is_dir()` は壊れたリンクで `False`、リンクの循環で `OSError(ELOOP)`、FIFO の `is_file()` は `False`、`O_NOFOLLOW` でリンクを開くと `ELOOP`、権限のないディレクトリの `scandir` は `EACCES`。リンク先の途中が通常ファイルだと `DirEntry.is_file()` が `ENOTDIR`、リンク先の親が通れないと `EACCES` を送出する。
- macOS(APFS。この環境)で: 非 UTF-8 の名前は作れない(`EILSEQ`)。`\` を含む名前は作れる。NFC と NFD の名前、大文字小文字だけが違う名前は同じファイルになる。
- v0.2 作成時(2026-11-13): `crawler-architecture-v0.2.md` の冒頭、3.2、3.3.1、4.5(手順 6・8)、7.7、9章、10章、13.4 の CA-U-19、13.7、13.8 を読み、本書が参照する architecture の章・ID(3.2、3.3.1、3.3.3、4.2、4.5、4.8、5.3、5.8、6.2、6.5、7.6、7.7、9、10、11、12、13.5、13.7、13.8、CA-P-15・19・24・45、CA-U-6・10、I-8)が v0.2 にも存在することを確認した。v0.2 で意味が変わった箇所は 3.2・4.5(CA-P-51)と 7.7(CA-P-52)で、本書は 2.4・3.4 で追従した。それ以外の章(4.2、4.8、6.2、6.5 など)は、章の存在と本書の参照先との対応を確かめたが、全文の差分は精査していない。索引・マッピング(CA-K-21)に関する記述は本書にない。
- (v0.2 時点)パターンの正規表現への変換は、作業用の一時領域で試作し、本書の例を含む 30 件の一致・不一致が期待どおりになることを確認した(リポジトリには残していない)。v0.3 では正規表現を使わない(CFS-P-25)。意味(2.3 の表)は変わらない。
- v0.3 作成時(2026-11-16): 実装 `apps/crawler/src/loreley_crawler/connectors/`(`filesystem/` の `config.py`・`patterns.py`・`enumeration.py`・`fetch.py`・`errors.py`・`fs_ops.py`・`settings.py`・`connector.py`、`registry.py`)を読み、本書の 2〜9章と照合した。差は、照合方式(CFS-P-25)と、本書に書いていなかった実装の決定(CFS-P-26〜31)だけ。設定の検証、走査の規則(適用順 1〜4)、errno の集合 T と分類、取得の手順(`O_NONBLOCK`・`O_NOFOLLOW`、2 回の `fstat`)、MIME 対応表、`title`・`path` の NFC は、設計書どおりだった。実装のテスト結果は作業記録 0008・0009・0021 による(Linux の Docker・非 root で skip 0 を含む。本書の作成時には再実行していない)。
- v0.3 作成時: 本書が参照する architecture の ID(CA-P-15・19・24・45・48・51・52・55、CA-U-6・10・19、CA-K-7・9・21)と章(3.2、3.3.1、3.3.3、4.2、4.5、4.8、5.3、5.8、6.2、6.5、7.6、7.7、9、10、11、12、13.5、13.7、13.8)が architecture v0.3 に存在することを確認した。architecture v0.4 についても、主な参照先の章(3.2、4.5、5.8、6.5、7.6、7.7、13.5、13.7、13.8)が存在することを見出しで確認した(それ以外の章と、章の中身の変更は精査していない)。

確認していないこと(実機未確認。CFS-U-4): Linux のファイルシステム・NFS・SMB での、マウント外れの errno と症状(Docker のバインドマウントの挙動を含む)、`d_type` が不明なファイルシステムでの `scandir` の挙動、`\`・非 UTF-8・NFD の名前の実際の発生、取得中の変更の検出精度、コンテナ内の Python のファイルシステムエンコーディング、`:ro` マウントの挙動、`st_ino` の信頼性(SMB・FUSE の一部で不安定な可能性。祖先ループの判定に使う。推測)、列挙・取得の所要時間。

### 11.2 確定(CFS-K)

確定にしたのは、ユーザー回答(Q2)、PD v0.19 でユーザーが承認済みの事項、interface の確定事項だけ。2026-11-16 の承認で、案(CFS-P)を新たに確定(CFS-K)へ付け替えてはいない。

| ID | 内容 | 出典 |
| --- | --- | --- |
| CFS-K-1 | MVP の Connector はローカルディレクトリ・ファイル共有だけ。対応形式は txt・Markdown・HTML・PDF。Office は次版 | PD v0.19 4.1・4.2・8.1 |
| CFS-K-2 | 検索対象ディレクトリのマウントは読み取り専用 | PD v0.19 8.2 |
| CFS-K-3 | FS の列挙対象は、設定の包含・除外パターンで絞る。既定は対応形式の拡張子(txt・md・markdown・html・htm・pdf)。対象外は列挙も `last_seen_at` の要請もせず、`enumerated_count` に数えない。包含パターンは設定で追加できる | ユーザー回答 Q2(CI-K-7) |
| CFS-K-4 | 列挙の失敗・マウント外れなど、クロール全体の異常では文書を削除しない | PD v0.19 5.2・8.2 |
| CFS-K-5 | 0 件列挙は異常とせず、列挙の完了として扱う。全ファイルを消したデータソースは、手動クロールの強制削除で削除できる | PD v0.19 5.2・8.2 |
| CFS-K-6 | 読めない文書(権限エラーなど)は、その文書だけスキップし、Admin View で確認して、アクセス権の修正やデータソース設定の除外条件で解消する(PD は「数回リトライしても失敗したら」と書くが、権限エラーのリトライは本設計では案。architecture CA-P-19、I-8) | PD v0.19 2章・4.2・4.6 |
| CFS-K-7 | `external_id` はルートからの相対パス。NFC、パス区切り `/`、先頭に `/` を付けない、大文字小文字を区別 | interface CI-K-2、api 3.3 |
| CFS-K-8 | `url` と `path` は独立した任意の 2 項目。原本の取得日時・Connector 固有属性は送らない | interface CI-K-8 |
| CFS-K-9 | 上限を超えた原本は、Crawler(取得)でも拒否する | interface CI-K-10 |
| CFS-K-10 | MVP は、追加・更新の検知をせず、毎回すべての文書を取得して登録する(全件更新) | PD v0.19 4.1 |

### 11.3 案(CFS-P。CFS-P-1〜23 は 2026-11-16 のユーザー承認で承認済みの案。CFS-P-24 は CFS-U-7 の選択肢 (c) で、案 (a) の承認により採用しない案。CFS-P-25〜31 は実装で決めた内容)

| ID | 内容 | 章 |
| --- | --- | --- |
| CFS-P-1 | `connector_config` の項目(`root`・`include_patterns`・`exclude_patterns`・`follow_symlinks`・`include_hidden`)と検証(未知のキー拒否、`null` 不可、I/O なし) | 2.1、2.2 |
| CFS-P-2 | `include_patterns` は既定の拡張子に追加する形。既定の拡張子は固定で設定項目にしない | 2.1 |
| CFS-P-3 | パターン構文: glob(`*`・`?`・`**` のみ)、ルート相対の全体一致、NFC で照合、大文字小文字を区別、`\` は使えない、`**` の連続は `config_invalid`(v0.3: 理由は意味の一意性。照合の方式は CFS-P-25) | 2.2、2.3 |
| CFS-P-4 | 既定の拡張子は最後の拡張子を小文字にして照合する | 2.3 |
| CFS-P-5 | 適用順(隠し -> 種別 -> 除外 -> 包含)。除外が優先、除外ディレクトリは開かない、包含はファイルだけ | 4.1 |
| CFS-P-6 | シンボリックリンク: 既定はたどらず列挙しない。`true` はルート内(`commonpath` で判定)を指すリンクだけ。壊れたリンク(`ENOENT`・`ELOOP`・`ENOTDIR`)・祖先ループ・外向きは無視し、他の `OSError` は列挙の失敗 | 4.2、4.4 |
| CFS-P-7 | 隠しファイル: 名前が `.` で始まるもの。既定は対象外 | 4.3 |
| CFS-P-8 | 通常ファイルだけを列挙する | 4.1 |
| CFS-P-9 | マウント済みパスとして扱い、SMB・NFS のクライアントを実装しない。`root` はコンテナ内のパス | 1.1、3.1 |
| CFS-P-10 | `create` でルートを確認する(`stat` と `scandir` の開始) | 3.2 |
| CFS-P-11 | errno による分類(ルート・配下・取得)と、マウント外れの判定(パスなし = `source_not_found`、到達不能 = `source_unreachable`)。集合 T | 3.3、4.4、7.1 |
| CFS-P-12 | `os.scandir` の自前走査(`os.walk` 等は使わない)、深さ優先でスタックに積み `read_dir` は取り出し時、ディレクトリ単位で全件読み切って閉じる、並べ替えない、ループ内の `OSError` は一括で `enumeration_incomplete` | 4.4、4.5、9.2 |
| CFS-P-13 | `size_hint` は返さない。上限超過は `fstat` と読み取り中の確認で判定 | 5.5、6.1 |
| CFS-P-14 | `title` = ファイル名(拡張子を含む、NFC)、`path` = 相対パス(NFC)、`url` なし | 5.3 |
| CFS-P-15 | `source_updated_at` = `mtime`(取得時の `fstat`)。範囲外の日時は固定値 | 5.4 |
| CFS-P-16 | 対応外の拡張子は `application/octet-stream`(MIME 対応表自体は導出) | 5.2 |
| CFS-P-17 | 取得の手順(`open`(`O_NONBLOCK`、`O_NOFOLLOW`)-> `fstat` -> 上限 -> 読み取り -> 変更の確認) | 6.1 |
| CFS-P-18 | 説明文に errno 名と該当パスを含める(interface 6.1 の「固定文」の拡張) | 7.3 |
| CFS-P-19 | 衝突に対して FS 固有の回避を置かない。運用は除外パターンか名前の変更 | 8.4 |
| CFS-P-20 | `external_id`・`locator` は OS の名前を加工せず返す(`surrogateescape`)。`title`・`path` は NFC だけ | 8.1 |
| CFS-P-21 | 仮値(設定可能。環境変数 `LORELEY_CRAWLER_FS_MAX_PATTERNS`・`_FS_MAX_PATTERN_BYTES`・`_FS_READ_CHUNK_BYTES`・`_FS_MESSAGE_PATH_MAX_CHARS`): パターン 100 件・1024 バイト、読み取りの単位 1 MiB、説明文のパスの長さ 200 文字。承認後も仮値で、確定ではない | 2.2、6.1、7.3 |
| CFS-P-22 | `create` でファイルシステムエンコーディングが `utf-8` であることを確認し、違えば失敗させる(代替は `bytes` の明示復号。v0.3: 確認方式は CFS-P-27 で決まった) | 8.1 |
| CFS-P-23 | 0 件列挙は `Completed` のまま(CFS-K-5)。管理者が気づく手段に architecture の 0 件警告(CA-P-52)を加え、マウント外れが疑われるときの確認手順を定める(推測を含む) | 3.4.1、3.4.2 |
| CFS-P-24 | 削除の保留の FS 固有の案(c): `root` 直下の目印ファイルを `create` で確かめる任意の項目。案 (a) の承認により採用しない(CFS-U-7 は解消)。実装していない | 3.4.3 |
| CFS-P-25 | (実装で決めた内容)glob の照合は正規表現を使わず、最悪の入力でも多項式時間のアルゴリズムで行う。セグメント内は貪欲な 2 ポインタ法、セグメント間は到達しうる位置の集合。意味は 2.3 の表で、方式は入れ替えてよい。隣り合う `**` の拒否理由は、同じ意味の書き方を複数認めず表記を 1 つに絞ること(意味は一意)だけ | 2.2、2.3、9.2 |
| CFS-P-26 | (実装で決めた内容)OS 呼び出しを `FsOps` に集約する。操作は読み取りだけ(`scandir`・`stat`・`realpath`・`open`・`fstat`・`read`・`close`・`filesystem_encoding`)。`FileSystemConnectorType` の生成時に渡し、既定は `os`。テストは偽の `FsOps`。注入の方式は module-structure CM-P-9 | 9.2 |
| CFS-P-27 | (実装で決めた内容)エンコーディングの確認は `create` で `FsOps.filesystem_encoding()` が UTF-8 かを見る方式(`bytes` の明示復号は採らない)。違えば `connector_internal_error`(source) | 8.1、9.1 |
| CFS-P-28 | (実装で決めた内容)分類した `ConnectorError` は元の `OSError` を traceback に出さない(`from None`。R11 の根拠)。分類できない例外の `connector_internal_error` の説明文は型名(と errno 名)だけ。設定違反の説明文に入力値を入れない(未知のキーの名前も) | 2.2、7.3 |
| CFS-P-29 | (実装で決めた内容)列挙ストリーム: 失敗後の `next()` は同じ例外を再送出、`Completed` の後は `Completed` を返し続ける、`close()` の後は `RuntimeError` | 4.5 |
| CFS-P-30 | (実装で決めた内容)テスト環境の判定は OS の名前でなく、名前を実際に作れるかで行う。`LORELEY_REQUIRE_LINUX_NAMES=1` で、作れない環境の skip を失敗にできる | 10章 |
| CFS-P-31 | (実装で決めた内容)細工した最悪の入力での照合時間(0.2〜0.5 秒/件/パターン)を許容する。対策の選択肢は 9.3 | 9.3 |

### 11.4 未決(CFS-U)

2026-11-16 のユーザー承認後の状態: CFS-U-1・2・3・5・7 は**解消**(案どおり承認。実装も案どおり。decisions v0.3 の4章の表の ID 列に対応)。CFS-U-4・6 は**未決のまま**(ID 列にないため。残る論点は、CFS-U-4 が実機でしか確認できない errno・症状・精度などの確認、CFS-U-6 が数値の実測)。解消した行も ID と本文は消さず、「内容」の末尾に状態を付けた。

| ID | 内容 | 決める場所 |
| --- | --- | --- |
| CFS-U-1 | パターン構文(glob)を確定にするか。案のまま実装でき、変更は本書の改版と既存設定の見直しになる。あわせて `include_patterns` の意味の確認。案は (i) 既定の拡張子への追加(現行)。選択肢: (ii) 指定したら既定を置き換える、(iii) 名称を `additional_include_patterns` などに変え、「追加」であることを名前で示す(一般の glob の「絞る」直感と違うため)。いずれも確定扱いにしない(承認前の記述)。(iii) を採るなら項目名・2.1・2.5 の例・テスト 3・検証の説明文を改める。設定画面での注意は 2.1。**【解消。案(glob、既定拡張子への追加)どおり承認】** | ユーザー判断(承認済み) |
| CFS-U-2 | `follow_symlinks`・`include_hidden` の初期値(案は両方 `false`)。**【解消。案どおり承認】** | ユーザー判断(承認済み) |
| CFS-U-3 | `title` を内容から取るか(HTML の `<title>`、Markdown の見出し、PDF のメタデータ)。案は MVP ではファイル名のみ。取るなら Crawler に形式ごとの解析が要り、Indexer 設計との分担を決める。**【解消。案(ファイル名のみ)どおり承認】** | ユーザー判断(承認済み) |
| CFS-U-4 | 実機での確認(11.1 の「確認していないこと」)。マウント外れの errno の集合 T(`ENXIO`・`ENOMEDIUM`・`EREMOTEIO`・`ENOLINK` などを入れるかの検討を含む)、取得中の変更の検出、`st_ino` の信頼性、入出力の停止への緩和(NFS の設定など)、ファイルシステムエンコーディングの確認方式(8.1。**v0.3 で方式は決定**: CFS-P-27。実運用イメージでの確認は残る)。**【未決のまま】** | 実装時の実機確認 |
| CFS-U-5 | 衝突(8.4)が 1 組でも残るとソース全体が毎回 `failed` になる影響の緩和(例: `\` を含む名前を FS が列挙しない)。CA-U-6 の決定とあわせて。**【解消。FS 固有の回避を置かず、ジョブ `failed`(CA-P-24)の案どおり承認。緩和は運用で検討】** | ユーザー判断(承認済み) |
| CFS-U-6 | 数値(パターンの上限、読み取りの単位、説明文の長さ)の正式値と、列挙・取得の所要時間・メモリの実測。CA-U-1 と同じく実測後に決める。**【未決のまま。仮値・設定可能】** | 実装後の実測 |
| CFS-U-7 | 0 件列挙のときの削除の保留(architecture CA-U-19)のうち、FS に関わる部分。(a) 現状維持(案。運用手順と警告で気づく。3.4.1・3.4.2)、(b) 前回 1 件以上・今回 0 件のとき、`force_delete=true` でなければ終了通知を `failed` にして削除させない(ジョブも `failed`。共通処理。PD v0.19 5.2 との関係の確認が要る)、(c) FS 固有の目印ファイル(CFS-P-24)。**【解消。案 (a) 現状維持で承認・実装済み。(b)(c) は採用しない】** | ユーザー判断(承認済み。CA-U-19 とあわせて) |

### 11.5 既存設計との不整合(I-n)

| ID | 内容 | 扱い |
| --- | --- | --- |
| I-30 | SD v0.8 3.1 は、列挙のエラーを握りつぶさない実装として「`os.walk` は既定でエラーを無視するので、`onerror` でエラーを検出して列挙を失敗させる」と書く。しかし `os.walk` は `entry.is_dir()` の `OSError` を `onerror` に渡さずに「ディレクトリでない」として扱う(Python 3.12.11・3.13.4 のソースで確認)ため、`onerror` だけでは一部の列挙エラーを検出できない | 本書は `os.scandir` の自前走査とし、`os.walk` を使わない(4.4、9.2)。SD は廃止予定で修正しない |

`PD v0.19` と本設計の権限エラーのリトライの不整合(I-8)は architecture 13.5 で定義される(本書の I-n ではない。6.3、CFS-K-6)。

I-31〜I-39 は使わない。interface の I-10(`\`・NFC/NFD の衝突)は 8.4 で対応を定めた。

### 11.6 他文書の依頼への回答と修正要望

interface 11.6(FS への依頼):

| 依頼 | 回答 |
| --- | --- |
| 孤立サロゲートの発生状況の説明 | 8.1(方式は共通処理。FS は説明と、名前を加工せず返すことだけ) |
| `title` の取得できないときの値(CI-U-8) | 5.3(ファイル名。取得できない場合がない)。`title`・`path` の長さと空文字の制約は、ファイル名が空にならず長さも上限内に収まる(推測)ため FS では不要 |
| `source_updated_at` が取れないときの値(CI-U-5) | 5.4(`mtime` は必ず得られる。範囲外のときだけ固定値) |
| MIME の対応表 | 5.2 |
| `size_hint` の有無 | 5.5(返さない) |
| 衝突への対応(I-10) | 8.4(FS 固有の回避を置かない。CFS-U-5) |
| マウント外れの `source_unreachable` / `source_not_found` の判定 | 3.3、7.2(errno で分ける) |

architecture 13.7(FS への依頼):

| 依頼 | 回答 |
| --- | --- |
| `create` でルートの存在確認を行うか | 3.2(行う) |
| `size_hint` を返すか | 5.5(返さない) |
| マウント外れの分類 | 3.3、7.2 |

architecture v0.2 の 13.7(FS への依頼。v0.2 での追加分。承認前の記述):

| 依頼 | 回答 |
| --- | --- |
| 3.4 に 0 件列挙の警告(CA-P-52)と管理者の確認手順を追記 | 3.4.1、3.4.2 |
| 削除を保留する選択肢(CA-U-19 の (b))と、FS 固有の選択肢 (c) を追記 | 3.4.3(v0.3: 案 (a) の承認により (b)(c) は採用しない。CFS-U-7 は解消、CFS-P-24 は採用しない案) |
| CFS-U-1(`include_patterns` の意味)を確定しない(承認前の記述) | 2.1、CFS-U-1(選択肢と設定画面の注意を追記。確定扱いにしない。承認前の記述。v0.3: 案どおり承認、CFS-U-1 は解消) |

他文書への修正要望(本書では直さない。宛先・要点・緊急度):

| 宛先 | 要点 | 緊急度 |
| --- | --- | --- |
| architecture 3.3.1・4.8 と interface 6.1 | 列挙失敗・`create` 失敗の `failure_detail` に、分類名に加えて Connector の説明文(固定文 + errno 名 + 切り詰めた相対パス。7.3)を載せてよいと定める。interface 6.1 の説明文(`message`)の定義もこれに合わせる(内容・認証情報は含めない)。`external_id_collision` の `failure_detail` には、後に検出された 1 件の切り詰めた `external_id` と共有する `document_id` を載せる(管理者が 8.4 の解消をするため) | 反映済み(案。architecture 3.3.1・4.8・CA-P-45、interface 6.1・CI-P-17)。本書の管理者向けの対処(4.4、7.3)の前提は満たされた |
| architecture 9章 | 「データソースのマウント切れ(FS)」の行に、本書 3.3 への参照を足す | 低(反映済み) |
| architecture 13.8 | 横断一覧に `CFS-U-1`〜`6`(11.4)と `I-30` を追記する(P4) | 低(反映済み) |

v0.2 で足した他文書への要望:

| 宛先 | 要点 | 緊急度 |
| --- | --- | --- |
| architecture 13.8 | 横断一覧に `CFS-U-7`(0 件列挙のときの削除の保留の FS 部分。CA-U-19 と対)を追記し、`CFS-U-1` の要約に「名称変更の選択肢を含む」を足す | 反映済み(v0.2) |
| decisions | 実装者が決めてよい事項・ユーザー判断待ちに、`include_patterns` の意味(CFS-U-1。Admin View 実装時の項目名・説明文の注意は 2.1)と、0 件列挙の FS 部分(CFS-U-7)を載せる | 低 |
| crawler-api | 確認依頼は、crawler-api 側で回答済み(該当なし。crawler-api の応答に `warnings` はなく、Admin API が `loreley-jobs` を直接読む)。`warnings` の表示は Admin API の設計(architecture 2.2、CA-U-12)に引き継ぐ | 該当なし |

v0.3 で足した他文書への要望(実装結果の反映。本書では直さない):

| 宛先 | 要点 | 緊急度 |
| --- | --- | --- |
| interface 3.2・6.1 | 想定外の例外の変換と、分類済みの errno 変換で、元の例外を traceback に出さない(`from None`。R11)。`connector_internal_error` の説明文は型名(と errno 名)だけ(CFS-P-28) | interface v0.3 で反映(CI-P-18) |
| module-structure 4.7・4.10 | `documents` の取得の包みは、Connector の戻り値の検査と後処理も `connector_internal_error`(document)の変換範囲に含める。列挙の包みは `Completed` を受けた後は Connector を呼ばず `Completed` を返す。FS の `FsOps` の操作の一覧は本書 9.2(CFS-P-26) | module-structure v0.5 の作業で反映(別の作業。本書は確認していない) |
| architecture 11章 | FS の仮値(パターン 100 件・1024 バイト、読み取り 1 MiB、説明文のパス 200 文字)を採用値として追記する(CFS-P-21) | 低(architecture v0.4 の作業。本書は確認していない) |
| apps/crawler の README | 10章の「既知の限界」(照合の最悪入力。CFS-P-31)、`LORELEY_REQUIRE_LINUX_NAMES=1`(CFS-P-30)、本書のファイル名(`connector-file-system-v0.3.md`)への更新 | 実装側の文書。設計書の改版の範囲外(メインエージェントへの申し送り) |

crawler-api への要望はない。crawler-api v0.4 は、`config_invalid` の説明文を 512 文字以内に整形(孤立サロゲートの置換・制御文字のエスケープ・切り詰め)して応答に載せる(CAPI-P-23。v0.3 までの「そのまま」を改めた)。FS の説明文は短く(項目名と違反の種類だけ。入力値を入れない。未知のキーの名前も入れない。2.2、CFS-P-28)、この整形の影響を受けない。
