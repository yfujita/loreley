# 0001 要件確認(確定した要件)

- 日付: 2026-11-13
- 実施: requirements-clarifier(結果の保存はメインエージェント)
- 結果: `STATUS: REQUIREMENTS_READY`(質問3点にユーザーが回答済み)

## 1. 要件の要約

- 目的: Indexer実装完了を受け、Crawler実装に向けた設計書6本を作成する。実装自体はスコープ外。
- 成果物: `docs/v0.x/system-design/crawler/` 配下。版は各文書 v0.1 から。
  - `crawler-architecture-v0.1.md`
  - `crawler-api-v0.1.md`
  - `crawler-module-structure-v0.1.md`(他が固まった後、最後に作成)
  - `connector/connector-interface-v0.1.md`
  - `connector/connector-file-system-v0.1.md`
  - `connector/connector-web-v0.1.md`
- スコープ外: Crawlerの実装、Web Connectorの詳細設計。
- 完了条件: 0000の完了条件7項目のとおり。
- 区分の表記: Indexer設計書の凡例(確定・案・未決・推測・導出)に揃える。ユーザー承認済みのものだけを「確定」とし、SD v0.8の「案」は案のまま引き継ぐ。
- Crawler関連の既存決定(ジョブ状態、リース、スキップ記録、登録結果、確認結果の区分など)はSD v0.8・PD v0.19から取り込み、Crawler設計で完結させる。SDはメンテナンスしない。Indexer v0.10と食い違う場合は独自に仕様変更せず I-n として記録する。

## 2. ユーザー確定事項(2026-11-13 回答)

- **Q1 crawler-apiの範囲**: Crawlerが受けるAPI(呼び出し元はAdmin API)のみ。クロール起動(`force_delete`・`rewrite_mode`指定を含む)/取り消し/ロック解放/データソース設定の登録・更新・削除/ソース削除ジョブ起動。Crawler→Indexerの呼び出し・リトライ・ポーリング・集計はcrawler-architectureの「Indexerとの連携」章に書く。Indexer契約はindexer-api-v0.10を参照のみで再掲しない。
- **Q2 FSコネクタの列挙対象**: データソース設定の包含・除外パターンで絞る。既定は対応形式の拡張子のみ(txt・md・markdown・html・htm・pdf)。対象外は列挙もlast-seen要請もせず、`enumerated_count`にも数えない。包含パターンは設定で追加可。
- **Q3 課題の記録先**: 各設計書の末尾章に自文書分の未決・課題を持ち、既存設計との不整合は専用分類 `I-n` で区別。crawler-architectureに横断一覧(ID・一行要約・参照先のみ)を置く。Indexer側設計書(v0.10)は書き換えない。

## 3. Indexer整合要件(根拠: indexer-api-v0.10、indexer-architecture-v0.10)

- **呼び出し順**: ロック取得 → 開始通知(`POST /crawls/start`)→ last-seen要請(取得より前)→ バッチ登録 → 全応答確認後に終了通知(202)→ Status APIポーリング(終端まで)。ロックは削除結果が終端になるまで保持。ポーリング失敗・上限時間超過は警告と区分(`unconfirmed`/`unknown`)を残すだけで、ジョブstatusは変えない。
- **ジョブごとの固定**: 設定スナップショット(`crawl_started_at`、`ttl`、`ratio_threshold`、`min_delete_count`、`force_delete`、`rewrite_mode`)をジョブごとに保持し、開始通知の再送では同一値を送る。終了通知の内容も`loreley-jobs`に保存して固定し、再送では同じ内容を送る。型はstrict。`crawl_id`は`job_id`と同値。
- **document_id**: Crawlerが算出。`SHA-256(source_id + "\0" + external_id)`の小文字hex。`external_id`はNFC正規化、パス区切り`/`統一、先頭に`/`を付けない(IndexerはK58で除去しない)、大文字小文字は区別。
- **content_hash**: 原本のSHA-256を小文字64桁hexで渡す。Indexerは再計算・照合しない。
- **ID制約**: `source_id`・`crawl_id`・`lock.*`は256バイト以内・制御文字なし。`external_id`は4096バイト以内・NULなし(改行・タブ可)。孤立サロゲートが`external_id`に入ると全体400になるため、Crawlerが事前に除去または置換する。
- **DELETEボディ**: CrawlerのHTTPクライアントは`DELETE`にJSONボディ(`lock`)を載せられること。
- **ロック**: 文書形式は`lock-{source_id}`に`owner`・`job_id`・`lease_expires_at`(ISO 8601)。Indexerが仮定義で採用中のためCrawler設計で確定または修正する。文書なし・期限切れ・不一致は「所有していない」扱い。同期HTTP待ち中もリース更新を途切れさせない。
- **メンテナンスフラグ**: `loreley-jobs`のID`maintenance`、項目`enabled`(bool)。Indexerの読み取りはfail-closed(K63)。書き込み手段は未決(arch U-24)。
- **リトライ/スキップ**: 最大3回、バックオフ初回1秒・2倍・上限30秒・ジッタあり(案)。スキップ対象は`document_rejected`のみ、連続20件で`failed`(案・Crawler側規則)。`oversize`はリトライしない。`write_conflict`/`update_conflict`は上限付きリトライ、解消しなければジョブ`failed`で期限削除なし(K51)。`lock_not_owned`はスキップもリトライもせず`failed`。開始通知・登録の409はリトライせず`failed`。500・503・接続エラーはリトライし、直らなければ`failed`。
- **終了通知**: `enumerated_count`は`document_id`で重複を除いた件数(スキップ・抽出失敗の文書を含む)。`skipped_document_ids`と`oversize_document_ids`は別項目。Crawlerは文書単位の`oversize`結果からIDを集める。`outcome`は`enumeration_completed`/`failed`/`cancelled`。取り消しは終了通知送信前のみ有効。202は受理確認ではなく、受理はStatus API(`finish_received_at`、または`failed`+`outcome_*`)で確認。
- **登録結果の集計**: Crawlerが`loreley-jobs`に保持。項目は`enumerated_count`/`created_count`/`updated_count`/`unchanged_count`/`skipped_count`/`oversize_count`/`error_count`/`partial`(名称は案)。再送時は`document_id`ごとに最初に受け取れた結果を保持し数え直さない。
- **ソース削除ジョブ(K29確定)**: discard(順1)→ 文書全削除(順2)→ skip記録削除(Crawler)→ 削除記録削除(順3)→ データソース設定削除 → ロック文書削除(最後)。ロックは最後まで保持しリース更新を続ける。所有権喪失時は後続削除を停止し再実行で復旧。削除中のデータソースに新規クロールを起動しない。
- **rewrite_mode**: 起動APIで指定可能にし手動実行のみ(想定)。定期実行は`force_delete`と同様に常に`false`(案)。
- **FSのMIME対応(導出)**: `.txt`=`text/plain`、`.md`/`.markdown`=`text/markdown`、`.html`/`.htm`=`text/html`、`.pdf`=`application/pdf`。包含パターンで対応外拡張子を追加した場合、Indexerが`unsupported_mime_type`の`extract_failed`として登録する旨を注記する。
- **前提**: 単一ホスト・単一Crawler・直列実行。CrawlerとIndexerは同一ホストの時計を使う。

## 4. 責務分担

| 文書 | 担う内容 |
| --- | --- |
| crawler-architecture | Crawlerの責務と境界、ジョブ状態遷移、ロック・リース・ハートビート、リトライ・スキップ、登録結果の集計、スキップ記録、`loreley-jobs`・`loreley-sources`のデータモデル、削除結果の確認と区分、Indexerとの連携、最小限のコンテナ・マウント、課題の横断一覧 |
| crawler-api | Admin API→Crawlerのみ。起動、取り消し、ロック解放、データソース設定の登録・更新・削除(しきい値検証はAdmin API側)、ソース削除ジョブ起動 |
| connector-interface | 列挙と取得の抽象、文書メタデータ、エラー分類、`external_id`規則、`document_id`算出、`content_hash`。FS/Web両方に適用可能な形(列挙と取得を分離しつつストリーミング列挙も許す) |
| connector-file-system | 包含・除外パターン、既定の拡張子絞り込み、MIME対応、`external_id`(ルートからの相対パス)、`path`、`url`なし、`title`、`source_updated_at`(mtime)、`size`、列挙エラー、シンボリックリンク・隠しファイル、孤立サロゲートのエスケープ案、マウント外れ検知 |
| connector-web | 概要のみ。位置づけ(非MVP・将来拡張)、インタフェース対応(`external_id`=正規化URL等)、列挙の完全性と削除安全性の論点、詳細設計が必要な箇所の一覧 |
| crawler-module-structure | 他が固まった後に最後に作成 |

## 5. 既存設計との不整合(I-n)

- **I-1**: ソース削除でのロック文書削除タイミング。SD v0.8 1.2・4.6(ロックを先に削除・案)と Indexer K29・API 4.6〜4.8(最後まで保持・確定)が食い違う → K29に従う。
- **I-2**: 突合ジョブ。SD v0.8 3.6・14.2は定義、PD v0.19はMVPから削除済み、Indexer APIにもエンドポイントなし → Crawler設計に含めない。
- **I-3**: `loreley-texts`を文書の正とするSD v0.8 1.3・3.2・`loreley-texts-v0.5`と、検索インデックスを唯一の正本とするPD v0.19 4.3・Indexer K18が食い違う → Crawler設計は`loreley-texts`に依存しない。
- **I-4**: SD v0.8 14.4の起動APIに`rewrite_mode`の記載がない → Crawler設計で追加。
- **I-5**: Indexerが仮定義した事項(ロック文書形式、メンテナンスフラグ、索引名、`oversize`等の失敗種別名・理由コード名。API-U-23・24、arch U-34)→ Crawler設計で確定または修正。不一致はIndexer修正課題として記録。
- **I-6**: `loreley-jobs`・`loreley-sources`のインデックス作成・マッピング担当が未定(Indexerは作らない)→ 未決として記録。

## 6. 前提として置く事項

- 数値(バッチ件数・サイズ、タイムアウト、リース時間、ハートビート間隔、ポーリング間隔・上限時間、リトライ回数)は「仮値・設定可能・未決」(Indexer K39準拠)。
- ファイル共有はOSのマウント済みパスとして扱い、SMB・NFSクライアントは実装しない。マウントは読み取り専用。
- FS列挙エラーは握りつぶさず、列挙できないディレクトリがあれば列挙失敗としてジョブ`failed`。シンボリックリンク・隠しファイルは設定項目とし初期値は案。
- 定期実行の周期形式(cron式か間隔か)は案としてarchitectureに置く。
- 版の運用: 初版v0.1。ユーザー承認前のレビュー修正はv0.1を直接修正、承認後の変更は新版ファイル。
- 検証方法: document-reviewerによるレビューと、Indexer API・実装(`apps/indexer/README.md` 6章、`apps/indexer/tests/documents/test_document_id.py`の`API_EXAMPLE_VECTORS`)との突き合わせ。コードは書かない。
- Crawlerのコンテナ・インフラ詳細はarchitectureに最小限のみ。

## 7. 設計書内で案・未決として扱う事項

- `document_id`算出の二重実装対策(API-U-7。案: 共有テストベクタ)
- ロックのリース時間、ハートビート間隔、discard応答待ち中のリース切れの扱い(API-U-14)
- 「削除中」状態の置き場所(`loreley-sources`/ロック文書/ジョブ状態)
- メンテナンスフラグの書き込み手段(arch U-24)
- 原本サイズ超過の記録先・項目・ジョブstatusへの影響、Crawlerの送信前拒否の有無(PD 9.2 #8)
- 再送時の集計規則(API-U-16。案: 最初の結果を保持)
- ジョブ記録の保持期間
- Admin API設計の不在(crawler-apiが契約を先行定義するため、Admin API設計時に再確認)
- I-6のインデックス・マッピング作成担当

## 8. 未対応事項・次にやること

- 要件確認としての未解決事項はなし。
- 次: plannerで作業プラン(`0002-work-plan.md`)を作成し、ユーザー承認を得る。プランには作成順(architecture / interface → FS / Web / API → module-structure)とdocument-reviewer・task-reviewerの要否を含める。
- 備考: 依頼文で挙げた `agent_tasks/20261109_create_indexer_design/STATUS.md` は存在しなかった(影響なし)。
