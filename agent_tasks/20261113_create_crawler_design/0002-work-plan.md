# 0002 作業プラン: Crawler設計書6本の作成

- 日付: 2026-11-13
- タスク: 20261113_create_crawler_design
- 作成: planner(保存はメインエージェント)
- 状態: **ユーザー承認待ち**
- 前提文書: `0000-requirements-definition.md`、`0001-clarify-requirements.md`(以下「0001」)、`STATUS.md`

## 1. 目的とゴール

Indexer実装完了を受け、Crawler実装に着手できる設計書6本を `docs/v0.x/system-design/crawler/` 配下に作成する(版は各 v0.1)。実装・コードは対象外。

| # | 成果物 | 備考 |
| --- | --- | --- |
| 1 | `crawler/connector/connector-interface-v0.1.md` | 先に固める |
| 2 | `crawler/crawler-architecture-v0.1.md` | 先に固める。Indexer連携を含む |
| 3 | `crawler/crawler-api-v0.1.md` | Admin API -> Crawler のみ |
| 4 | `crawler/connector/connector-file-system-v0.1.md` | 実装着手可能な粒度 |
| 5 | `crawler/connector/connector-web-v0.1.md` | 概要のみ |
| 6 | `crawler/crawler-module-structure-v0.1.md` | 最後に作成 |

受け入れ基準は 0000 の完了条件7項目(対応表は11章)。

## 2. 確定事項・前提

### 2.1 確定事項(0001より。ユーザー回答済み)

- crawler-api は Admin API が呼ぶ口のみ。Crawler->Indexer の呼び出し・リトライ・ポーリング・集計は architecture の「Indexerとの連携」章。Indexer契約は `indexer-api-v0.10.md` を参照のみで再掲しない。
- FSコネクタの列挙対象は包含・除外パターンで絞る。既定は拡張子(txt・md・markdown・html・htm・pdf)のみ。対象外は列挙もlast-seen要請もせず `enumerated_count` にも数えない。
- 課題は各文書末尾に自文書分 + 既存設計との不整合は `I-n`。architecture に横断一覧(ID・一行要約・参照先のみ)。Indexer側設計書(v0.10)は書き換えない。
- 責務分担(0001 4章)、Indexer整合要件(0001 3章)、I-1〜I-6(0001 5章)、前提(0001 6章)、案・未決の扱い(0001 7章)に従う。
- 区分は Indexer 設計書の凡例(確定・案・未決・推測・導出)。ユーザー承認済みのみ「確定」。SD v0.8 の「案」は案のまま引き継ぐ。数値は「仮値・設定可能・未決」(Indexer K39準拠)。

### 2.2 本プランで置く前提(案。承認時に異論があれば修正)

1. **ID体系**: 未決・案・確定の番号は文書別の接頭辞で採番する(例: architecture `CA-K/CA-P/CA-U`、api `CAPI-U`、interface `CI-U`、FS `CFS-U`、Web `CW-U`、module `CM-`)。Indexer設計書の `K/P/U/API-U/M` と衝突しないための案。
2. **I-n の採番**: I-1〜I-6 は既定。並列作成での衝突を避けるため、新規の I-n は範囲を予約する(欠番は許容)。architecture 追加 I-7〜I-9、interface I-10〜I-19、api I-20〜I-29、FS I-30〜I-39、Web I-40〜I-49、module I-50〜。重複・追加はメインが調整する。
3. **`connector_config` は不透明に扱う**: architecture は `loreley-sources` の共通項目と `connector_type`、`connector_config`(不透明)だけを定義。固有項目の定義と検証は各コネクタ文書が持つ。crawler-api の登録・更新は共通項目 + `connector_config` を受け、`connector_config` の検証は Crawler(コネクタ)、しきい値の範囲検証は Admin API。
4. **interface は言語非依存の疑似シグネチャ**で書く(型は module-structure でPython実装に落とす)。
5. FS のパターン構文は glob を第一案とする(FS文書で案として確定要否を明記)。
6. Crawler の周期形式(cron式か間隔か)は architecture に案として置く。
7. 参照: Indexer の既存設計は `indexer-api-v0.10.md`、`indexer-architecture-v0.10.md`、`indexer-module-structure-v0.4.md`、`apps/indexer/README.md` 6章、`apps/indexer/tests/documents/test_document_id.py` の `API_EXAMPLE_VECTORS`。SD v0.8 と PD v0.19 は決定事項の取り込み元。SD v0.8 は廃止予定なので Crawler 設計は自文書で完結させ、SD への参照は出典の注記にとどめる。

### 2.3 調査で見つけた注意点(設計書で扱う)

- **`\` の扱い**: Indexer 実装は `document_id` 算出の前に `external_id` を NFC 化し `\` を `/` に統一する(README 6章)。Linux では `\` がファイル名として正当なため `a\b` と `a/b` が同一 `document_id` になる衝突が起こり得る。interface に規則を明記し、衝突は I-n 候補として記録する(要否はライターが indexer-api 3.3・4.3 で確認)。
- batch の `documents[]` に `document_id` を含めるか、Indexer が再計算・照合するかは、ライターが indexer-api 4.3 で確認して書く(確認できなければ未決)。
- サンプルベクタを載せる場合は `API_EXAMPLE_VECTORS` と照合する。一時的な計算は scratchpad で行いリポジトリに残さない。

## 3. 影響範囲

追加のみ(既存ファイルは変更しない)。

- `docs/v0.x/system-design/crawler/` 配下の設計書6本(上記)
- `agent_tasks/20261113_create_crawler_design/` 配下の作業記録・STATUS.md(メインのみ)

変更しない: Indexer設計書・SD v0.8・PD・`apps/` 配下のコード。

## 4. 実施(作成)フェーズ

### 4.0 共通ルール

- 1本の文書は1人の document-writer が書く(章間の矛盾を避けるため分割しない)。
- 文書冒頭は Indexer 設計書の形式に倣う(版・更新日・前版なし・位置づけ・区分の凡例・関連文書表・「案を確定扱いにしない」旨)。末尾に確認状況章(区分ごとの一覧、自文書の未決 ID、I-n)を置く。
- 各文書は「他文書で決めることは参照のみ(再掲しない)」。定義箇所は次の正本表に従う。

| 規則・事項 | 正本 | 他文書での扱い |
| --- | --- | --- |
| `external_id` 規則、`document_id` 算出、`content_hash`、エラー分類名 | interface | 参照のみ |
| リトライ・スキップ・連続20件規則、スキップ記録 | architecture | interface はエラー分類と「リトライ可否の属性」までに限る |
| ジョブ状態、ロック・リース・ハートビート、登録結果の集計、確認結果の区分、データモデル | architecture | api・module は参照のみ |
| Indexer契約(エンドポイント・項目・エラー) | indexer-api-v0.10(既存) | 再掲しない。呼び出し順と Crawler 側の扱いのみ architecture |
| Admin API -> Crawler の契約 | crawler-api | architecture はジョブ側の挙動のみ |
| FS 固有の設定・列挙・取得・マッピング | FS | interface は抽象のみ |
| Web 固有の論点 | Web(概要) | interface に Web 都合を混ぜない |

### P0: 準備(メイン)

- `docs/v0.x/system-design/crawler/` と `connector/` を作成。
- 基準SHA(現HEAD `5eeb7a4`)を記録。新規ファイルは「ファイル全体」をレビュー対象とする。
- 5.2 の共通依頼文を確定(ID接頭辞・I-n 範囲・読むべきファイル)。P0 の記録は P1 の作業記録に含めてよい。

### P1: connector-interface(単独。他は待つ)

- ライター: document-writer 1名。
- 入力: 0000・0001・STATUS.md、indexer-api-v0.10(3.3、4.2、4.3、4.9、6章)、README 6章、SD v0.8 3.1・3.2、PD v0.19 4.1。
- 先に作る理由: architecture・FS・Web・api が参照する識別子規則とエラー分類の正本で、規模が小さく修正コストも小さい。
- 章立て(案):
  1. 位置づけと前提(MVP前提、適用対象 FS=MVP / Web=将来、範囲外=リトライ・スキップ・ジョブ・ロックは architecture)
  2. 用語
  3. Connector の抽象(責務表、列挙と取得の分離、ストリーミング列挙を許す形、列挙完了の明示と列挙失敗の区別、設定検証・接続確認の要否、疑似シグネチャ)
  4. 文書メタデータ(`external_id`、`title`、`path`、`url`、`mime_type`、`size`、`source_updated_at`。Indexer batch の項目対応は参照のみ。原本取得日時・Connector固有属性は MVP で保存しない[indexer K44/K45])
  5. 識別子規則(`external_id` 規則と制約、`document_id` 算出と二重実装対策の案[API-U-7。共有テストベクタ]、サンプルベクタ、`content_hash`)
  6. エラー分類(列挙/取得[権限・一時・不在・サイズ超過]/設定。分類名・リトライ可否の属性。判断は architecture)
  7. 取得の契約(取得結果、サイズ上限と `oversize` の送信前拒否の有無=PD 9.2 #8 は未決として論点のみ)
  8. 設定の扱い(`connector_type`、`connector_config` の責務境界と検証主体)
  9. FS / Web への適用性(対応表。Web側の齟齬確認の叩き台)
  10. テスト観点
  11. 確認状況(`CI-U-n`、I-n)
- 完了時: 作業記録 `0003-write-connector-interface.md`、STATUS更新(メイン)。

**ゲート R1**: document-reviewer 1名で interface をレビュー。Critical / Important は修正してから P2 へ。

### P2: crawler-architecture(単独。最大の文書)

- ライター: document-writer 1名(章立ては固定し、増減は報告に理由を書く)。
- 入力: 0000・0001・STATUS.md、確定済み connector-interface、indexer-api-v0.10(全章。特に 2、3.2〜3.6、4.1〜4.8、5)、indexer-architecture-v0.10(1.2、2、8、9、12、17)、README 6章、SD v0.8(1.2・1.3・3.1・3.3・4.1〜4.7・14.x)、PD v0.19(4.1・4.7・4.8・5.1・5.2・9.2)。
- 章立て(案):
  1. 位置づけと前提
  2. 責務と境界(論理構成図、責務分担表[Crawler/Indexer/Admin API]、インデックスごとの書き込み役、通信方針、時刻の前提)
  3. データモデル(`loreley-sources`、`loreley-jobs`[ジョブ・ロック文書・スキップ記録・メンテナンスフラグ]、設定スナップショットと終了通知の固定保存、Repository と索引・マッピング作成担当[I-6]、保持期間[未決])
  4. ジョブとライフサイクル(種別: クロール/ソース削除、状態遷移、起動[手動・定期、周期形式(案)、直列実行、削除中ソースへの起動拒否、`force_delete`・`rewrite_mode` の規則]、クロール処理フロー、取り消し、異常系と終了状態)
  5. ロック・リース・ハートビート(ロック文書形式の確定/修正[I-5]、取得の原子性、更新、リース切れ、解放、同期HTTP待ち中の更新継続、所有権喪失時、再起動時の残存ロック整理)
  6. 取得とリトライ・スキップ(リトライ設定、失敗種別×Crawlerの扱い表、連続20件規則、スキップ記録、`oversize`)
  7. Indexerとの連携(呼び出し順と各APIの使い方[契約は再掲しない]、バッチ化と `last-seen` の分割、設定スナップショットと再送時の同一値、終了通知、Status APIポーリングと確認結果の区分、登録結果の集計と再送規則、エラー別の扱い、メンテナンスフラグ、ID制約の担保)
  8. ソース削除ジョブ(K29順序、「削除中」状態の置き場所[未決]、所有権喪失時の停止と再実行、新規クロール禁止)
  9. 障害と再起動
  10. コンテナ・マウント(最小限)
  11. 非機能・仮値(数値表。すべて仮値・設定可能・未決)
  12. テスト観点
  13. 確認状況(`CA-U-n`、自文書分の I-n)と、全文書の課題の**横断一覧**(ID・一行要約・参照先のみ。P4 で完成)
- 完了時: 作業記録 `0004-write-crawler-architecture.md`、STATUS更新。

**ゲート R2**: document-reviewer 1名。Indexer突き合わせ(5.3)最重視。Critical / Important は修正・再レビューしてから P3 へ。

### P3: api / FS / Web(並列)

- ライター: document-writer 3名を並列。入力は確定済み interface・architecture。
- 並列にできる理由: 共通規則は interface・architecture が正本で、3本は互いに参照しない。接点 `connector_config` は2.2(3)で境界を決めてある。
- 衝突防止: 各ライターは自分の文書だけを書く。interface・architecture の修正が必要な場合は直さず「他文書への修正要望」として報告(メインがまとめて反映)。I-n は予約範囲を使う。

**crawler-api-v0.1**(Indexer API書の形式に倣う)
  0. この文書について(範囲: Admin API -> Crawler のみ、凡例、`CAPI-U-n`)
  1. API一覧(メソッド+パス(案)/呼び出し元/用途/冪等性/確認状況)
  2. 概要(呼び出しの流れ、同期/非同期の別、状態は Admin API が `loreley-jobs` を直接読む=読み取りAPIは置かない旨)
  3. 共通事項(通信方式、認証なし、ID検証、エラー形式、冪等性、時刻)
  4. リファレンス: クロール起動(`force_delete`・`rewrite_mode`、拒否条件: ロック保持中・削除中・メンテナンス中)/取り消し/ロック解放/データソース設定の登録・更新・削除(`connector_config` 検証主体、しきい値検証は Admin API 側)/ソース削除ジョブ起動
  5. 確認状況(`CAPI-U-n`、I-n。Admin API設計の不在=契約先行定義でありAdmin API設計時に再確認)
  - ジョブの内部挙動は書かず architecture を参照する。

**connector-file-system-v0.1**(実装着手可能な粒度)
  1. 位置づけと範囲
  2. 設定(`connector_config`: ルート、包含・除外パターン、既定拡張子、シンボリックリンク・隠しファイル。項目名は案、検証)
  3. マウントとルート(読み取り専用、ルート存在確認、マウント外れ検知)
  4. 列挙(再帰、パターン適用順、対象外は `enumerated_count` に数えない、シンボリックリンク・隠しファイル[初期値は案]、列挙エラーを握りつぶさずジョブ `failed`、ストリーミング)
  5. 文書メタデータ(`external_id`=ルートからの相対パス、`path`、`url` なし、`title`、`source_updated_at`=mtime、`size`、MIME対応表[導出]、対応外拡張子を包含パターンで追加した場合の `unsupported_mime_type` による `extract_failed` の注記)
  6. 取得(読み取り、取得中の変更、サイズ上限、`content_hash`、権限エラーの分類)
  7. エラー分類(interface との対応表)
  8. ファイル名・文字の扱い(NFD/NFC、孤立サロゲートのエスケープ案、`\`・改行・タブ)
  9. 実装に必要な細目(処理手順、規模の見積もり)
  10. テスト観点
  11. 確認状況(`CFS-U-n`、I-n)

**connector-web-v0.1**(外枠のみ。詳細設計はスコープ外)
  1. 位置づけ(非MVP・将来拡張)
  2. interface 対応表(`external_id`=正規化URL、`url`/`path`、`title`、`source_updated_at`=Last-Modified、`mime_type`=Content-Type、`size`、`content_hash`)
  3. 列挙の完全性と削除安全性の論点(部分列挙時は `failed` とする方針の確認、robots・認証・レート、深さ・範囲、サイトマップ併用)
  4. 共通 interface への適用結果(齟齬の有無。あれば interface 修正要望と I-n)
  5. 詳細設計が必要な箇所の一覧(論点・影響する interface 要素・状態)
  6. 確認状況(`CW-U-n`、I-n)

- 完了時: 作業記録 `0005-write-api-fs-web.md`、STATUS更新。「他文書への修正要望」の有無を記す。

**ゲート R3**: document-reviewer 3名を並列(api / FS / Web)。Web は interface との齟齬確認、FS は実装着手粒度を主観点とする。Critical / Important は差し戻し・再レビュー。修正要望が出ていれば、メインが interface / architecture(v0.1 を直接修正)に反映してから該当部分を再確認する。

### P4: 横断整合と課題の集約(メインまたはライター1名)

- architecture 13章の横断一覧を完成させる(各文書末尾の課題と I-n を集約。ID・一行要約・参照先のみ)。I-n の重複・欠番を確認。
- 用語ゆれ(状態名、項目名、失敗種別名)を点検。
- 完了時: 作業記録 `0006-consolidate-issues.md`、STATUS更新。

### P5: crawler-module-structure(最後に単独)

- ライター: document-writer 1名。入力は確定した5本と `indexer-module-structure-v0.4.md`、`apps/indexer/` のディレクトリ構成(参考)。
- 章立て(案): 1 概要(モジュール表。実装言語は Python)/2 構成図(mermaid)/3 ディレクトリ構成(`apps/crawler/src/loreley_crawler/` 以下・案)/4 モジュール詳細(候補: `api`、ジョブ管理、`scheduler`、`indexer_client`、`connectors`、`infrastructure`、`common`。最終案はライターが検討)/5 主要シナリオ別の呼び出しの流れ/6 依存ルール/7 確認状況(`CM-n`、I-n)
- 完了時: 作業記録 `0007-write-module-structure.md`、STATUS更新。

**ゲート R5**: document-reviewer 1名。観点は architecture・interface・api・FS との整合、Indexer module-structure との形式の整合。

## 5. 実施体制

### 5.1 委任方針

- 設計書の作成は document-writer に委任する(1本1名)。並列化できるのは P3 の3本のみ。P1→P2→P3→P5 は前の文書を入力にするため直列。
- P1 と P2 を並列にしない理由: architecture のリトライ章が interface のエラー分類に依存し、interface が architecture の責務分担に依存する循環があるため。小さい interface を先に確定する。
- document-writer・document-reviewer は `agent_tasks` 配下の `STATUS.md`・`NNNN-*.md` を書かない。報告に「結果・変更ファイル・判断理由・未対応事項・次のアクション・他文書への修正要望・採番した I-n と CA/CI 等のID」を含め、メインが保存する。
- 作業記録・STATUS.md の更新はメインが各フェーズ・各ゲートの完了時に行う。

### 5.2 ライターへの共通依頼文(必須項目)

- タスク名、読むべきファイル(`STATUS.md`、`0000`、`0001`、`0002`、`CLAUDE.md`、`.claude/rules/task-workflow.md`、フェーズ指定の入力)
- 作業範囲: 担当1本のみ、出力先パス、章立て(増減は理由を報告)
- 禁止事項: `agent_tasks` 配下の `STATUS.md`・`NNNN-*.md`・`0000` を書かない。Indexer設計書・SD・PD・コードを変更しない。ユーザー未承認の事項を「確定」と書かない。確認していないことを書かない。数値は仮値・設定可能・未決。他文書で決める規則を再掲しない。
- 区分の凡例、ID接頭辞、I-n の予約範囲、文書冒頭・末尾の形式
- 報告形式: 結果・変更ファイル・判断理由・未対応事項・次のアクション・他文書への修正要望・採番ID一覧

### 5.3 レビューの観点(R1〜R5・最終レビュー共通)

document-reviewer への依頼には、Git差分に頼らず次を明示する: レビュー対象ファイルのパス一覧(新規のため「ファイル全体」)、比較基準(参考SHA `5eeb7a4`)、参照文書(`0000`、`0001`、`0002`、確定済みの他の Crawler 設計書、Indexer設計書)。

**Indexer突き合わせチェックリスト**(architecture・api は必須、他は該当部分):

1. **document_id**: 算式 `SHA-256(source_id + "\0" + external_id)` の小文字hex、`external_id` の NFC・`/` 統一(Indexer実装は `\`→`/` も実施)・先頭 `/` なし・大文字小文字区別、4096バイト・NUL なし、孤立サロゲートの事前処理、`content_hash` の小文字64桁hex、`last-seen` の `document_ids` が Crawler 算出であること、サンプルベクタが `API_EXAMPLE_VECTORS` と一致すること。
2. **ジョブライフサイクル**: 呼び出し順、`crawl_id`=`job_id`、設定スナップショット項目名と型(strict)、開始・終了通知の再送で同一内容、202は受理確認でない、`outcome` 3値、`failed`/`cancelled` で項目省略可、取り消しは送信前のみ、ポーリング失敗はジョブ status を変えず区分のみ。
3. **ロック・リース**: `lock-{source_id}` の項目と所有判定、リース切れ=不所有、同期HTTP待ち中の更新、`lock_not_owned` はリトライせず `failed`、`DELETE` のJSONボディ、discard は所有確認なし・順2/3は確認あり、メンテナンスフラグ(`maintenance`/`enabled`/fail-closed)。
4. **再クロール時の削除**: last-seen を取得より前に要請、`enumerated_count` の定義、`skipped_document_ids` と `oversize_document_ids` は別項目、列挙失敗時は `failed` を送り削除させない、ソース削除は K29 順序、削除中は新規クロール不可。
5. **リトライ・スキップ**: 最大3回・バックオフ値(案)、スキップ対象は `document_rejected` のみ、連続20件で `failed`、`oversize` リトライなし、`write_conflict`/`update_conflict` は上限付きリトライ後 `failed`、409はリトライせず `failed`、500・503・接続エラーはリトライ。
6. 区分の誤用(未承認を「確定」と書いていないか)、Indexer v0.10 の書き換え・独自仕様変更がないこと(食い違いは I-n)。

**Web Connector と共通インタフェースの齟齬確認**(R3-Web・最終レビュー): interface の各要素が Web で成立するか、Web固有の都合が interface に混入していないか、齟齬が修正要望または I-n として記録されているか。

## 6. レビューフェーズ

成果物は設計書のみなので `document-reviewer` を適用する。`code-reviewer`・`test-reviewer` は、コード・テストの変更がなく実装変更も含まないため省略する。

| レビュー | 対象 | 並列 | 備考 |
| --- | --- | --- | --- |
| R1 | connector-interface | - | P2 の前のゲート |
| R2 | crawler-architecture | - | P3 の前のゲート。Indexer突き合わせ重視 |
| R3 | api / FS / Web | 3名並列 | Web は interface 齟齬、FS は実装着手粒度 |
| R5 | crawler-module-structure | - | 5文書との整合 |
| 最終 | 全6本の横断 | 1〜2名 | 下記 |

**最終レビュー(R5の後)**: 全6本を対象に、(a) 責務の重複・矛盾(4.0の正本表)、(b) 用語・ID・状態名・項目名の一貫性、(c) I-n・未決の漏れと横断一覧の完全性、(d) 5.3 の Indexer 突き合わせ、(e) 0000 の完了条件との対応(11章)。(a)(b)(c) と (d)(e) の2名並列でよい。

**指摘への対応**: Critical / Important は該当ライターに差し戻して修正し再レビュー(他文書に影響する場合は影響先も確認)。Suggestion / Nitpick は対応可否を判断し作業記録に残す(対応しないものは理由つき)。「指摘なし」または Critical / Important 解消済みになるまでレビューフェーズを完了としない。ユーザー承認前の修正は v0.1 を直接修正する。

## 7. タスクレビューフェーズ(最後。実施する)

- 理由: 実施フェーズが複数で複数セッションにまたがる見込みで、プランから乖離しやすく、Indexer整合のような工程全体の妥当性は個別レビューで見えにくいため。
- 実施順: 全文書のレビュー完了と、全作業記録・STATUS.md の作成後。
- 担当: `task-reviewer`(`agent_tasks/20261113_create_crawler_design/` 配下すべてと成果物6本のパスを渡す)。
- 観点: 要件・プラン・作業記録・実際の文書の突き合わせ、完了条件の充足、判断の妥当性、未決・I-n の記録漏れ。
- 指摘への対応: Critical / Important は差し戻し・再レビュー。Suggestion / Nitpick は判断を作業記録に残す。
- 作業記録: `0008-final-review-and-task-review.md`。

## 8. 記録・STATUS更新のタイミング(メイン)

| 区切り | 作業記録(案) |
| --- | --- |
| プラン保存・承認 | `0002-work-plan.md`(本書) |
| P0+P1、R1 完了 | `0003-write-connector-interface.md` |
| P2、R2 完了 | `0004-write-crawler-architecture.md` |
| P3、R3 完了 | `0005-write-api-fs-web.md` |
| P4 完了 | `0006-consolidate-issues.md` |
| P5、R5 完了 | `0007-write-module-structure.md` |
| 最終レビュー・タスクレビュー完了 | `0008-final-review-and-task-review.md`(状態 `done`) |

各更新で、ユーザー判断待ちが出た場合は質問と確定済みの回答を「ユーザー判断待ち」に記録し `blocked` にする。最新作業記録には必ず「未対応事項」を書く。

## 9. 検証方針

コードは書かないため、検証は文書レビューと突き合わせで行う: document-reviewer によるレビュー、Indexer突き合わせ(5.3。サンプルベクタを載せる場合は照合結果を作業記録に残す)、横断一覧の網羅確認、Web概要と interface の適用性確認表の整合。

## 10. リスクと対策

| リスク | 対策 |
| --- | --- |
| 文書間の責務の重複・矛盾 | 正本表、ライター依頼文で「再掲しない」明記、最終レビュー(a)(b) |
| interface と architecture の循環依存 | P1 を先に確定し R1 ゲート。リトライ・スキップは architecture が正本 |
| 並列ライターの用語・ID 衝突(P3) | ID接頭辞・I-n 範囲の予約。他文書の修正は要望として報告。P4 で点検 |
| SD v0.8・PD の「案」を確定扱いにする | 依頼文で禁止。区分の誤用を R2・最終レビューの必須観点に |
| Indexer 既存設計・実装との食い違いの見落とし(`\` 変換、ロック文書形式、メンテナンスフラグ、`oversize` 名) | 5.3 のチェックリスト。食い違いは I-n に記録 |
| `document_id` の二重実装による不一致 | interface にサンプルベクタと共有テストベクタの案(API-U-7 は案・未決)。`API_EXAMPLE_VECTORS` と照合 |
| architecture の肥大化 | 章立て固定、Indexer契約は参照のみ |
| 数値を確定扱いにする | 「仮値・設定可能・未決」で統一(K39準拠) |
| Admin API 設計なしで api を先行定義 | 未決として記録し Admin API 設計時に再確認 |
| ライターが `agent_tasks` を書いてしまう | 依頼文で禁止。報告のみ |
| ロールバック | 追加ファイルのみ。削除・git revert で戻せる |

## 11. 完了条件(0000)との対応

| 完了条件 | 対応 |
| --- | --- |
| 6つの設計書が作成されている | P1・P2・P3・P5。最終レビューでパス・版・存在を確認 |
| CrawlerとIndexerの連携仕様が整合している | architecture 7・8章、api。R2・最終レビュー(d)の突き合わせ結果を作業記録に残す |
| 責務が明確で矛盾・不要な重複がない | 正本表、R1〜R5、最終レビュー(a)(b) |
| Connector共通IFがFSとWebの両方に適用可能 | interface 9章、Web 4章、R3-Web、最終レビュー |
| FSコネクタが実装着手可能な粒度 | FS 2〜9章、R3-FS の「着手粒度」観点 |
| Webコネクタは概要にとどめ詳細設計箇所を明示 | Web 5章、R3-Web |
| 未決・不整合が一覧化されている | 各文書末尾の確認状況と I-n、architecture 13章の横断一覧(P4)、最終レビュー(c) |

## 12. 未解決事項(プラン時点)

- 0001 7章の未決事項はすべて「設計書内で案・未決として扱う」(ユーザー判断不要)。
- 2.2 の前提(ID体系、I-n 予約範囲、`connector_config` の不透明扱い、glob構文など)は案。承認時に変更があれば反映する。
- 追加 I-n 候補: `\`→`/` の正規化と Linux のファイル名の衝突(2.3)。ライターが indexer-api 3.3・4.3 で事実確認してから記載する。
