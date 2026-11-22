# 0002 作業プラン: Crawler 実装

日付: 2026-11-13 / 作成: planner(保存: メインエージェント) / 対象: `apps/crawler` / 要件: `0000`、確定要件: `0001`
状態: **ユーザー承認待ち**(承認を得るまで実装に進まない)

## 1. 目的とゴール

Crawler(`apps/crawler`、パッケージ `loreley_crawler`)を `docs/v0.x/system-design/crawler/` の最新版(architecture v0.2、crawler-api v0.2、decisions v0.2、module-structure v0.3、connector-interface v0.2、connector-file-system v0.2)どおりに実装し、単体テストを通す。Connector は FileSystem のみ。Integration Test と infra 前提作業はスコープ外(0001 Q2)。

完了条件は 0001「完了条件」の 1〜10(承認時に最終確認。§9)。フェーズとの対応は §7。

## 2. 確定事項・前提

### 2.1 確定事項(0001、ユーザー回答済み)

- Q1: 全モジュール+単体テスト+Dockerfile・README
- Q2: infra 前提作業は本タスクに含めない(別タスクとして未対応事項に記録)
- Q3: 未承認の設計判断(decisions 4章の10件、CM-U-4、CA-U-3)は案どおり実装。採用案の一覧を作業記録に残す。案の採用は設計書の承認ではない
- 設計書(docs)、`apps/indexer`、Indexer 設計書は変更しない

### 2.2 前提(0001。プラン承認時に最終確認)

- 技術スタックは Indexer に揃える: Python `>=3.12,<3.13`、uv、FastAPI+uvicorn(workers=1、同期ハンドラ)、pydantic v2、pydantic-settings(接頭辞 `LORELEY_CRAWLER_`)、opensearch-py(同期)、pytest、ruff(line-length 100、select E,F,I,UP,B,SIM,RUF)、dev 依存の TestClient 用 `httpx2`、hatchling
- 並行モデルは module-structure 2.2(HTTP ハンドラ・Job Runner・ハートビート・Scheduler の4スレッド)
- 数値は architecture 11章の仮値を設定可能な値として実装。空欄は実装者が仮値を置いて記録
- 実装は `code-implementer`、レビューは別エージェント。メインエージェントは実装しない

### 2.3 Indexer 契約(v0.9→v0.10)の差分確認(プラン作成時の結果)

差分は「新しい要件」ではなく、Indexer 実装(2026-11-11〜12)で採用された内容の記録。`apps/indexer/src/loreley_indexer/api/routes.py` の8エンドポイント(`POST /crawls/start`、`POST /crawls/{id}/finish`、`GET /crawls/{id}`、`POST /sources/{id}/documents:batch`、`POST /sources/{id}/last-seen`、`POST /sources/{id}/deletions:discard`、`DELETE /sources/{id}/documents`、`DELETE /sources/{id}/deletion-records`)は api v0.10 のパス・メソッドと一致。

`indexer_client` に影響する v0.10 の主な確定事項:

- `DELETE`(ソース削除2・3)の `lock` は JSON ボディ。2・3は必須で所有確認(409 `lock_not_owned`)、1(discard)は受け取るが確認しない(K60)
- discard の試行上限超過・`delete_by_query` 再実行上限超過は再試行可能な503 `unavailable`(K61)
- バッチ登録・`last-seen` のロック失敗は確認済みの結果を返し、最初の失敗以降の未処理文書も文書単位 `lock_not_owned`、全体は200(K66)
- `failure_type`: `document_rejected`・`oversize`・`lock_not_owned`・`write_conflict`・`update_conflict`(`store_error` は返さない)。OpenSearch 全体異常はリクエスト全体の503 `unavailable`
- `last-seen` は Crawler 算出の `document_ids` 配列、件数上限超過は400
- 入力検証: 型は strict、範囲は検証しない、`fetched_at`・`metadata`・未知項目は無視、`content_hash` は照合しない、`skipped_count` は任意
- Status は `waiting_for` と404 `crawl_not_found`。未知 `crawl_id` の終了通知は202。削除結果の `reason` に `validation_failed` 追加
- `/healthz` は起動時整理の完了後だけ応答し、それまで全パス503(外からは接続拒否に見える)。Crawler は503と接続エラーの両方をリトライ(Crawler 領域・案)

残る確認(**P2 の最初の作業**): 上記は設計書の変更表からの要約で、`apps/indexer` の実スキーマ(`api/schemas.py`、`api/errors.py`)・テスト(`tests/api/`)との突き合わせは未実施。`code-implementer` が v0.10 の3・4章と実装・テストを読み、契約表(エンドポイント、リクエスト項目、応答、エラーコード、HTTPステータス、retryable)を作業記録用に報告する。食い違いは Indexer を直さず報告(Crawler は api v0.10 を正とする)。既知: `apps/indexer/README.md` が api v0.9 を参照(Indexer 側の課題。本タスクでは変更しない)。

## 3. 影響範囲(新規作成物)

`apps/crawler/` 配下(現在は存在しない)。既存ファイルの変更なし(docs・`apps/indexer`・infra・compose は変更しない)。

- ルート: `pyproject.toml`、`uv.lock`、`.python-version`、`.gitignore`、`.dockerignore`、`Dockerfile`、`README.md`
- `src/loreley_crawler/`: `main.py`、`config.py`、`common/`、`api/`、`scheduler/`、`sources/`、`jobs/`(直下+`records/`+`locks/`)、`crawl/`、`source_delete/`、`documents/`、`connectors/`(レジストリ+`interface/`+`filesystem/`)、`infrastructure/opensearch/`、`infrastructure/indexer_client/`
- `tests/`: srcに対応する単体テスト、`tests/fakes/`(メモリ上 Repository、偽 Indexer クライアント、固定時計、偽 Connector、偽 `FsOps`)、`tests/architecture/`(依存ルール検査)、`document_id` テストベクタのデータファイル

## 4. 実装者が決めてよい事項と、決めてはいけない事項

### 4.1 決めてよい(決めたら作業記録に残す)

| 事項 | 備考(推奨の出発点) |
| --- | --- |
| 数値の仮値(architecture 11章の空欄: Scheduler 周期、Job Runner 走査間隔、ハートビート再試行間隔、Store 層タイムアウト、停止待ち上限、走査・条件指定削除のタイムアウト) | すべて設定可能にし、`config.py` で上下限を検証。関係式(再試行間隔<ハートビート間隔<リース、停止待ち上限≥Store 層タイムアウト)を満たす。根拠 ID を一覧に書く |
| 同期 HTTP クライアントのライブラリ(CM-U-2) | 条件: `DELETE` にボディ可、API ごとのタイムアウト、スレッドから使える。推奨は urllib3(opensearch-py の既存依存)。選定理由と `DELETE` ボディ契約テスト結果を記録 |
| CM-U-9 の採用内容 | 0001 の仮置き(a): Indexer の上限値を `LORELEY_CRAWLER_` 接頭辞つきの名前で読み、未設定の項目は警告して検査を省略。環境変数名はこの範囲で決める |
| CA-P-49(マッピング)、CA-P-53・54 の細部 | マッピングは README かコメントに参照として残すだけ。全件走査のタイブレークは `document_id`(keyword)が第一候補。ソース削除の順3は「全件走査+バルク削除」を推奨(条件指定削除を Repository に置かず契約を単純にする) |
| `owner` の既定 | 設定で与える安定した ID(CA-P-3)。未設定時は起動失敗を推奨。256バイト以内・制御文字なしを検証 |
| ファイル名・テスト配置・fake の作り | module 3章・7.7 のとおり |
| Dockerfile の細部 | Indexer の Dockerfile に倣う(変更はしない) |

### 4.2 決めてはいけない(案どおり実装、必要なら報告・設計書の改版提案)

- 未承認の設計判断10件・CM-U-4・CA-U-3(0001 Q3)
- CM-U-5(`/healthz` の要否): **実装者は `/healthz` を追加しない。Dockerfile に `HEALTHCHECK` も付けない**(契約外 API になるため。§9-2)
- CA-U-14、CAPI-U-9 などの運用・改版時の判断、Admin API 設計時に決める事項(CA-U-12、CAPI-U-1・2・5・6。メンテナンス中は409の案で実装)
- 案がなく「決めてよい」にも当たらない判断は、推測で確定せず作業を止めて報告。削除に関わる判断は安全側(ジョブを `failed` にして削除させない)
- 案に依存する箇所(source_id の文字種、glob 構文と `include_patterns` の意味、失敗分類の定義、設定値)は1か所に局所化

## 5. 実装フェーズ

共通手順:

1. メインが `code-implementer` に依頼。依頼文に タスク名、読むファイル(`STATUS.md`、0000、0001、本プラン、該当設計書の章)、作業範囲、禁止事項(作業記録・`STATUS.md`・0000・docs・`apps/indexer` を書かない)、報告形式(結果・変更ファイル・判断理由・未対応事項・次のアクション・検証コマンド出力)
2. 実装担当が検証コマンド(`apps/crawler` で `uv run pytest`、`uv run ruff check`、`uv run ruff format --check`)の出力を報告
3. メインが作業記録(新規 `NNNN-*.md`)を作り、同時に `STATUS.md` を更新
4. §6 のレビューを指定の時点で実施
5. フェーズ開始時点の HEAD SHA を作業記録に控える(レビューの比較基準)。コミットはユーザー指示がある場合のみ

依存: P1→P2→P3(P2・P3は独立だが既定は直列)→P4→P5→P6→P7→P8→P9。

### P1: 基盤・`common`・依存ルール検査

- 成果物: `pyproject.toml`、`uv.lock`、`.python-version`、`.gitignore`、`.dockerignore`、ruff・pytest 設定、`src/loreley_crawler/` 雛形、`common/`(時計、UTCミリ秒日時形式、リトライ汎用機構(試行回数・バックオフ・ジッタ・中断できる待ち。乱数元差し替え可)、表示用文字列整形(切り詰め・制御文字エスケープ・孤立サロゲート置換)、ログのマスキングと出力設定、共有エラー型)、`config.py` のうち起動時整合性検査の純粋関数と設定 dataclass の置き場の雛形、`tests/fakes/clock.py`、`tests/architecture/`(R1〜R6・R10 の import 検査、R7 の部分検査。Indexer の `tests/architecture/dependency_rules.py` に倣う。計画した全ディレクトリ構成に対して検査できる形)
- 検証: pytest・ruff。リトライ機構、日時形式、文字列整形、ログのマスキングの単体テスト。整合性検査の純粋関数(architecture 12章 #39 の単体部分)。依存ルール検査が、違反 import を含む偽ファイルで失敗し現状で成功すること
- 完了条件: ruff・pytest 成功。完了条件1(テスト作成)、2の一部、8の部品

### P2: `infrastructure`(Repository・`indexer_client`)と fakes

- 最初の作業: §2.3 の契約表を作業記録用にまとめる(Indexer は変更しない)
- 成果物:
  - `infrastructure/opensearch/`: Repository インターフェース(版つき取得、`create`、版条件つき置き換え/削除、一覧、全件走査(PIT+`search_after`、ページ単位反復、終了・失敗・中断いずれでも PIT を閉じる、開始前 refresh を契約に含める)、IDバルク削除(件数上限ごとに分割、存在しないIDは成功、部分失敗は失敗IDの一覧で返す))、結果区分(成功・競合・存在しない・すでに存在する・全体異常)、opensearch-py 例外・応答の分類、索引ごとのインスタンス+ハートビート専用クライアント。索引・マッピングは作らない
  - `infrastructure/indexer_client/`: 1API1操作(開始通知・`last-seen`・バッチ登録・終了通知・Status・ソース削除1〜3)、厳密な JSON(型変換なし、`NaN` 不可)、`raw_content` は標準 base64(パディングあり・改行なし)、`source_id` のパーセントエンコード、`DELETE` の JSON ボディ(`lock`)、APIごとのタイムアウト、型付き結果(成功、`IndexerUnavailable`(500・503・接続エラー・タイムアウト)、`IndexerRejected`(400・409・404・405・その他))。リトライ・確認点・ジョブの扱いは持たない。本文・秘密をログに出さない
  - `tests/fakes/`: メモリ上 Repository(opensearch 実装と同じ契約・結果区分。バルク削除の部分失敗を注入可能)、偽 Indexer クライアント(応答差し替え、エラー注入、呼び出し順記録)
- 検証: アダプタのリクエスト形テスト、例外分類テスト(接続エラー、タイムアウト、429、5xx、`cluster_block_exception`、`circuit_breaking_exception`、`index_not_found_exception`→全体異常、409→競合、404→存在しない)、PIT を失敗・中断時に閉じること、メモリ上 Repository の自己テスト(同じ契約テストを両実装に流せる形)、`indexer_client` のリクエスト組み立て、**architecture 12章 #17**(`DELETE` ボディが落ちないことをローカル簡易 HTTP サーバ(`http.server`、ポート0)で確認)、APIごとのタイムアウト、ログに本文・秘密が出ないこと
- 完了条件: ruff・pytest 成功。完了条件3(`DELETE` ボディ部分)、7、8の部品。契約表が作業記録に残る

### P3: `connectors`(interface・filesystem・レジストリ)と `documents`

- 成果物:
  - `connectors/interface/`: `ConnectorType`(`validate_config`・`create`)、`Connector`(`enumerate`・`fetch`・`close`)、`EnumerationStream`(`next`・`close`。`next()` は `DocumentRef` か `Completed` を返し `StopIteration` を使わない)、`DocumentRef`・`FetchedDocument`・`DocumentMetadata`(frozen データクラス)、`ConnectorError`(`category`・`scope`・`retry`・`message`)、想定外例外を `connector_internal_error` に変換する関数
  - `connectors/filesystem/`: FS 設計書2〜9章(設定検証、glob 構文(`*` は `/` をまたがない、`**` の規則、違反は `config_invalid`)、`include_patterns` は既定拡張子への追加、`os.scandir` 自前走査、シンボリックリンク・隠しファイル(両方 false 既定)、errno 対応、`oversize`、マウント外れ検知、取得中変更検出、`title` はファイル名のみ)。OS 呼び出しは `FsOps` に集約し注入(既定は `os`)
  - `connectors/` 直下: レジストリ(`file_system` のみ。保護ラッパで想定外例外を `connector_internal_error` に変換)
  - `documents/`: `external_id` 規則適用(孤立サロゲートのID用エスケープ→NFC→`\` 置換→検証。`invalid_external_id`)、`document_id` 算出関数(単独関数)、列挙の包み(重複除去、衝突検出 `external_id_collision`、ID集合保持、`max_enumerated_documents` 超過、列挙済み件数・ID照会)、取得の包み(`max_bytes`・`size_hint` による `oversize`、`content_hash`・`size` 算出、表示用文字列の孤立サロゲート置換)、列挙・取得の例外変換
  - `tests/documents/` に `document_id` テストベクタ(interface 5.2 の全行。出典つきデータファイル1つ。共通処理を通さず算出関数に直接入力する行を含む)
  - `tests/fakes/`: 偽 Connector、偽 `FsOps`
- 検証: FS 設計書10章 #1〜23(一時ディレクトリと偽 `FsOps`。#13・#15・#17 は偽 `FsOps` で決定的に)。権限エラー(#4・#12・#16)は root で skip、Linux 専用(#18・#19 の該当部分、大文字小文字)は macOS で skip。interface 10章の契約テスト。テストベクタ全行一致。識別子エラー・衝突・重複除去・上限超過・`oversize`
- 完了条件: ruff・pytest 成功。完了条件4、6

### P4: `sources` と `jobs/records`・`jobs/locks`(ハートビート)

- 成果物:
  - `sources/`: `loreley-sources` の登録(存在しない場合のみ成功・同内容再送は成功・異なる内容か `deleting` は競合)、更新(全置換・版条件・`status` 保持・同内容なら書かない)、読み取り(1回の読み取りでレコード全体を1つの値として返す)、一覧、`status=deleting` への更新と削除、値の規則の検証関数(`source_id` 文字種(案 CAPI-P-15)、`ttl`・`min_delete_count` 整数、`ratio_threshold` 有限数、`schedule_interval_seconds` 1以上の整数か null、`connector_type` 登録済み)、`validate_config` 確認。`loreley-sources` に書く唯一のモジュール
  - `jobs/records/`: ジョブ記録・スキップ記録・原本サイズ超過記録・メンテナンスフラグの形式と読み書き(ジョブ記録更新は読んだ版を条件)。メンテナンスフラグは fail-closed(形式不正は「立っている」)。ジョブID生成(256バイト以内)。記録の整理・一括削除(全件走査+バルク削除、`record_type` ごとに1回。部分失敗は失敗IDだけを `common` のリトライで再送、尽きたら Store 層書き込み失敗)、そのソースの `skip`・`oversize` 記録削除、0件列挙警告用の直前完了クロールの登録結果取得
  - `jobs/locks/`: ロック文書(`create` による取得、リース設定、読み取り、版条件つき削除)とハートビート(専用スレッド・専用クライアント・所有状態(最後の版・最後に成功したリース期限・喪失の有無)をメモリ上に保持・I/Oなしの所有確認・喪失の記録・喪失後は更新しない・停止待ち上限)
- 検証: crawler-api 4.4 の登録・更新の分岐、検証関数の `reason` 対応、メンテナンスフラグ fail-closed、整理・一括削除の分岐とバルク削除部分失敗、直前完了クロール取得、ロック `create` 衝突(原子性自体は持ち越し)、ハートビート(固定時計と `Event` で決定的に。#13・#32 の単体部分)。スレッドのテストはスリープに頼らない
- 完了条件: ruff・pytest 成功。完了条件2・7の一部

### P5: `jobs` 直下(受付・取り消し・解放・回復・Job Runner・`JobContext`)

- 成果物: 受付(手動クロール・定期クロール・ソース削除の3入口が architecture 4.3 手順1〜5を共有。`force_delete`・`rewrite_mode` は手動クロール入口だけ。`lock_held` は既存ジョブ情報を返す。メンテナンス・`deleting`・設定状態の判断。受付の巻き戻し)、取り消し(`queued` は版条件つきで `cancelled`+ロック解放、`running` は取り消し要求のメモリ上レジストリ。crawler-api 4.2 の判定順)、ロック解放(管理者。`queued` のロックと受付途中のロックは対象外。`running` があれば `failed`(`lock_released`)、リース内は `lock_in_use` で拒否)、起動時回復(architecture 5.8 手順1〜4)、Job Runner(`queued_at` 順に1件ずつ、リース設定→ハートビート開始→実行対象呼び出し。実行対象は `main.py` から注入され `crawl`・`source_delete` を import しない。取り消し負けの停止。ロック解放は終わり方を問わず1回。喪失記録時はロック文書を削除しない。停止待ち上限超過は喪失扱い。最後の手段の `failed`(`internal_error`))、`JobContext`(版条件つき更新と読み直し・所有権喪失検知、確認点(所有・取り消し・メンテナンス)、中断できる待ち、リトライ、`settings_snapshot`・`settings_source_updated_at` 追記、最終状態記録)、起床通知と走査間隔
- 検証: architecture 12章 #13(単体部分)・#14・#15・#18・#25〜#29・#32・#33 の `jobs` 側。取り消しと実行開始の競合、取り消し要求の伝達・終端後消去・重ねた要求・再起動で消えること、ロック解放と Job Runner の競合(両先後)、解放しないロック、喪失時にロック文書を削除しないこと、Store 層書き込みがリトライを尽くして `failed`(`store_unavailable`)、受付の同時実行で1つだけ成功(fake の割り込みフック)。Job Runner が `crawl`・`source_delete` を import しないこと(依存ルール検査)
- 完了条件: ruff・pytest 成功。完了条件1(R3・R6 含め成功)、5の一部

### P6: `crawl`(クロールジョブの実行)

- 成果物: 実行開始(`queued`→`running`→設定の1回読み取り→`settings_snapshot` 6項目+`settings_source_updated_at` 追記→メンテナンス再確認→`validate_config`・`create`。設定なし・`deleting`・欠落・型違いは `config_invalid`。`connector_config` は `crawl` の実行状態だけに持ちログ・ジョブ記録に出さない)、開始通知(再送は同一値)、チャンク処理(`last-seen`→取得→バッチ登録を交互に。バッチの閉じ条件、失敗文書だけ再送)、リトライ(確認点つき)、スキップ・原本サイズ超過・連続スキップ(取得段階と登録段階の別カウンタ、20件)・識別子エラー(`partially_succeeded`)・`external_id` 衝突(`failed`)、スキップ記録・サイズ超過記録の書き込みと整理、登録結果集計(再送時は最初の結果を保持、`partial` の遷移)、0件列挙警告、`warnings`・`failure_detail` 組み立て、`document_id` 照合(`document_id_mismatch`)、終了通知の組み立て・固定・送信(`send_started_at`)、`failed`・`cancelled` 通知、ポーリングと確認結果区分(`confirmed`/`unconfirmed`/`unknown`)、取り消し・喪失・メンテナンス対応、最終状態と理由コード、想定外例外の扱い(送信開始前に限り終了通知 `failed`)、`EnumerationStream.close()`・`Connector.close()` 呼び出し
- 使うサブエージェント: `code-implementer`(規模が大きいため、必要なら 6a: 実行開始〜チャンク処理、6b: 終了通知・ポーリング・異常系 の2回に分けてよい。その場合は6a完了後に作業記録を残す)
- 検証: architecture 12章 #1〜#12・#19〜#22・#24・#25・#30・#31・#33・#35・#36・#38(単体で可能な部分)。呼び出し順(終了通知は全応答の確認後)、`crawl_id`=`job_id` と `crawl_started_at` の同一性、型 strict、終了通知の内容が最初の送信前に保存され再送で同一、202を受理として扱わない、`enumerated_count`、件数照合(登録されなかった文書が `skipped_document_ids` に載る)、リトライ・バックオフ・最大3回、`write_conflict`・`update_conflict` は `failed`、連続スキップ(別カウンタ、散在は打ち切らない、`oversize`・識別子エラーは計数もリセットもしない)、400・409はリトライしない/500・503・接続エラーはリトライ、ポーリング区分、`send_started_at` 前後の取り消し、`failed` 通知の条件、設定の1回読み取り、0件警告、スキップ記録整理(失敗したクロールでは整理されない)、`document_id` 不一致で `failed`。センチネル文字列で全ログを検査(完了条件8)
- 完了条件: ruff・pytest 成功。完了条件5(`crawl` 側)、8(`crawl`)

### P7: `source_delete` と `scheduler`

- 成果物:
  - `source_delete/`: 実行開始(`running`、`sources` を `status=deleting`。順0)、順1・2・4(`indexer_client` のソース削除1・2・3を `lock` つきで。各呼び出し前に確認点(所有・メンテナンス)。所有権喪失は `failed`(`lock_lost`)、メンテナンスは `failed`(`maintenance`)。ロックは終了処理まで保持)、順3(そのソースの `skip`・`oversize` 記録削除。尽きたら `failed`(`store_unavailable`))、順5(設定の削除)、順6(最終状態 `succeeded`。ロック文書削除は Job Runner)。再実行は順3・5を削除済みなら成功扱い。ハートビートは最後まで続く
  - `scheduler/`: 周期的起床、`schedule_interval_seconds` 設定済み `active` ソース取得、直近クロールジョブの受付時刻から次回起動時刻を判定(ジョブなしは設定の登録・更新時刻が起点)、`jobs` の定期受付呼び出し(`force_delete`・`rewrite_mode` は常に false)、拒否(ロック保持中・メンテナンス・削除中)は見送るだけで待ち行列を作らず取り返さない
- 検証: architecture 12章 #16・#23・#33(順3・5)・#34。順0〜6の順序(偽 Indexer の呼び出し記録)、ロックが最後まで残る、所有権喪失・メンテナンスで後続が止まり `failed`、再実行で完了、`deleting` のソースにクロールを起動できない、順3の削除が他ソースの記録・ロック文書・ジョブ記録を消さない、Scheduler の判定(期限前後、ジョブなし、停止中の起動を取り返さない、拒否を見送る)。安全側(`failed`)の分岐を網羅
- 完了条件: ruff・pytest 成功。完了条件5(ソース削除・定期起動)

### P8: `api`・`config.py` 完成・`main.py`

- 成果物:
  - `api/`: crawler-api の6エンドポイント(`POST /sources/{source_id}/crawl-jobs`、`POST /sources/{source_id}/delete-jobs`、`POST /jobs/{job_id}/cancel`、`DELETE /sources/{source_id}/lock`、`POST /sources`、`PUT /sources/{source_id}`)。JSON の厳密な型、必須・未知項目・読み取り専用項目・`job_id` 形式の検証と `reason`(`required`・`type`・`format`・`read_only`・`unknown_field`・`unsupported`)、共通エラー形式、受付拒否の409 3種(`source_deleting`・`maintenance_enabled`・`lock_held`)、形式不正・未知項目は400。400本文に入力値を含めない。業務判断はしない(R4)
  - `config.py` 完成: `LORELEY_CRAWLER_` の設定読み込み(OpenSearch 接続先、Indexer URL、索引名、`owner`、仮値、Indexer 上限)、各モジュール設定 dataclass への詰め込み、整合性検査の呼び出しと設定エラー送出
  - `main.py`: 起動順(整合性検査→OpenSearch 接続→起動時回復→ハートビート・Job Runner・Scheduler スレッド→HTTP 受付開始)、モジュール組み立て、実行対象(`crawl`・`source_delete`)の注入、取り消し要求レジストリの共有、停止順(実行中ジョブの完了を待たず終了処理もしない。CM-U-4)、uvicorn workers=1
- 検証: TestClient で6エンドポイント(正常・400・404・409各種・メンテナンス中409・共通エラー形式)、起動順テスト(整合性検査違反で異常終了し OpenSearch に接続しない、回復前に HTTP を受け付けない)、`main.py` 組み立てテスト、全体の依存ルール検査再実行(R1〜R6・R10、R7の部分、R4)、全ログ・エラー応答にセンチネルの本文・秘密・`connector_config` が出ないこと、`/healthz` が存在しないこと
- 完了条件: ruff・pytest 成功。完了条件1(最終確認)、3、8

### P9: Dockerfile・README・最終検証

- 成果物:
  - `Dockerfile`: `apps/indexer/Dockerfile` に倣う(マルチステージ、`uv sync --locked --no-dev --no-install-project`、非 root、環境変数で設定、単一プロセス、`CMD` は `python -m loreley_crawler.main`)。`HEALTHCHECK` は付けない(§4.2)
  - `README.md`: 起動・設定(環境変数一覧、仮値一覧)・テスト手順、メンテナンスフラグは運用者の手動手順(CA-U-3)、SIGTERM の扱い(CM-U-4)、アーキテクチャ対応表、**fake だけでは検証できないこと**(§10)、マッピング案(architecture 3.1、CA-P-49)への参照、infra 前提作業が未実施であること
  - 作業記録の最終整理: 仮値一覧、採用した案の一覧(Q3の10件+CM-U-4・CA-U-3)、決めてよい事項で決めた内容、持ち越し一覧、完了条件1〜10の検証結果(pytest・ruff 出力)
- 使うサブエージェント: `code-implementer`(Dockerfile・README 草案)、作業記録はメイン
- 検証: 全体の pytest・ruff check・ruff format --check。`docker build apps/crawler` 成功。起動確認は `/healthz` がないため (a) 必須設定なし/Indexer 上限超過の仮値で `docker run` し整合性検査違反メッセージを出して異常終了(fail-fast)、(b) 非 root・`python -c "import loreley_crawler.main"` が通ること。Docker が使えなければ未実施・持ち越しと記録。使える場合は任意で、ビルド済みイメージ(Linux)で `pytest` を実行し macOS で skip した Linux 専用テストを走らせる(root 実行で権限エラーのテストは skip になる)
- 完了条件: 完了条件2・9・10

## 6. レビューフェーズ

レビュアーは `code-implementer` と別エージェント。`code-reviewer` と `test-reviewer` は並列。比較基準は「フェーズ(群)開始時点の HEAD SHA」(作業記録に控える)。作業ツリーに無関係な変更があるため、`git diff` だけに委ねず対象ファイルのパスを明示する。

| 実施時点 | レビュー | 対象 | 備考 |
| --- | --- | --- | --- |
| P2完了後(P1+P2) | code + test | 設定ファイル、`common/`、`config.py`(純粋関数)、`infrastructure/`、`tests/{fakes,architecture,infrastructure,common}` | バルク削除・PIT 管理は削除に関わるため code-reviewer 必須 |
| P3完了後 | code + test | `connectors/`、`documents/`、対応テスト・テストベクタ | FS の errno 分類・`FsOps`、`document_id` |
| P5完了後(P4+P5) | code + test | `sources/`、`jobs/`、対応テスト・fakes 変更 | 並行性(ハートビート・所有確認・解放)。ロック・削除に関わる |
| P6完了後 | code + test | `crawl/`、対応テスト | 終了通知の固定・件数照合・`failed` 通知の条件を重点確認 |
| P8完了後(P7+P8) | code + test | `source_delete/`、`scheduler/`、`api/`、`config.py`、`main.py`、対応テスト | データ削除を含むため code-reviewer 省略不可。起動順・ログ流出を重点確認 |
| P9完了後 | code(Dockerfile)+ document-reviewer(README・作業記録) | `Dockerfile`、`README.md`、作業記録の最終整理 | テスト変更がなければ test-reviewer は省略(Dockerfile・README・作業記録のみのため) |

- 渡す文脈(共通): `0000`、`0001`、本プラン、該当作業記録、設計書。観点: 設計書との整合、依存ルール R1〜R11、「案どおり実装」(未承認案の局所化)、削除の安全側、ログへの流出、テストが仕様(テスト観点番号)を検証していること
- 指摘への対応: Critical / Important は `code-implementer` に差し戻し、同じレビュアーで再レビュー。Suggestion / Nitpick は対応可否を判断し理由とともに作業記録に残す。「指摘なし」または Critical / Important 解消済みになるまでそのレビューフェーズを完了としない
- 実行はメインエージェント

## 7. 完了条件との対応

| 完了条件(0001) | 主なフェーズ |
| --- | --- |
| 1 構成・依存ルール | P1(テスト作成)、P5・P8(最終確認) |
| 2 pytest・ruff・format、結果を作業記録に貼る | 全フェーズ。最終は P9 |
| 3 Admin API 6エンドポイント | P8 |
| 4 FS Connector・interface 契約テスト | P3 |
| 5 architecture 12章の単体で可能なもの | P4〜P7 |
| 6 `document_id` テストベクタ | P3 |
| 7 メモリ上 Repository が opensearch と同じ契約 | P2(P4 で整理・一括削除の使用を確認) |
| 8 ログに本文・秘密・`connector_config` を出さない | P1(部品)、P6・P8(検査) |
| 9 `docker build` と起動確認 | P9 |
| 10 作業記録(仮値・採用案・決めた内容・持ち越し) | P9(各フェーズで蓄積) |

## 8. タスクレビューフェーズ(必須)

実施する。理由: 複数フェーズ・複数セッションにまたがる、削除に関わる実装を含む、未承認の設計判断を多数「案」で実装し記録漏れ・逸脱が起きやすい。

- 実施順: P9 のレビュー完了と、すべての作業記録・`STATUS.md` 更新が終わった後
- 入力: タスク名のみ
- 確認内容: 要件・プラン・作業記録・実変更の突き合わせ。案の採用一覧と実装の一致、決めてよい事項の記録、仮値一覧・持ち越し一覧の有無、スコープ外(infra・Indexer・設計書)に手を入れていないこと、完了条件1〜10の根拠、`STATUS.md` と作業記録の一致
- 対応: Critical / Important は該当工程に差し戻して修正し再レビュー。Suggestion / Nitpick は判断して作業記録に残す。解消するまでタスクを完了としない

## 9. プラン承認時にユーザーに確認すべき事項

1. 0001 の完了条件1〜10と前提事項(技術スタック、並行モデル、仮値の方針、CM-U-9の仮置き(a))を、提案どおりで確定してよいか(0001では個別承認未取得)
2. 完了条件9「起動を確認する」の方法。Crawler に `/healthz` はない(CM-U-5 は運用・crawler-api 改版時の判断で実装者は追加できない)ため `HEALTHCHECK` も付けない。代わりに `docker run` で整合性検査違反を起こして fail-fast を確認する方法と import 確認で「起動確認」とすることでよいか。実 OpenSearch・実 Indexer での起動確認は Integration Test(スコープ外)に持ち越す。`/healthz` を追加したい場合は crawler-api の改版が先
3. フェーズ順とレビューの区切り(P2・P3・P5・P6・P8・P9の6回)でよいか。P2とP3を並行させるか(既定は直列)
4. 「採用した案の一覧」を設計書の承認とみなさないこと(設計書 v0.2 の承認と decisions 4章の10件の最終確定は引き続きユーザー判断待ち)の確認
5. infra 前提作業の別タスク起票はユーザー判断(提案のみ。本タスクでは起票しない)
6. コミットはユーザーの指示があるときだけ行う(既定: 行わない)

## 10. テスト方針とリスク

### テスト方針

- 単体テストのみ。FS は一時ディレクトリと偽 `FsOps`、OpenSearch はメモリ上 Repository、Indexer は偽クライアント、時間は固定時計。スレッドのテストは `Event`・固定時計・ゲートで決定的に書き、スリープに頼らない
- 競合・割り込み(受付の同時実行、取り消しと実行開始、ロック解放と Job Runner、ハートビート停止)は fake のフックと応答差し替えで再現
- `DELETE` ボディ(#17)はローカル簡易 HTTP サーバに対する契約テスト
- 権限エラーは root で skip、Linux 専用は macOS で skip(理由を skip メッセージに書く)
- fake だけでは検証できず持ち越す項目: 実 OpenSearch・実 Indexer が必要なもの(architecture 12章 #37(10,001件以上、PIT、refresh、バルク削除の部分失敗)、#39の統合部分、`create` と `if_seq_no` の原子性、opensearch-py のスレッド安全性(CM-U-1、CA-U-18)、実 Indexer のバッチ応答の `document_id` 照合(CM-U-3)、実機 FS の errno・マウント外れ・取得中変更検出(CFS-U-4)、Linux コンテナ・NFS/SMB でのブロッキング I/O 中のスレッド挙動、GIL を長く保持する処理の間のハートビート)。README と作業記録に明記

### リスクと対策

| # | リスク | 対策 |
| --- | --- | --- |
| 1 | Indexer 契約 v0.9→v0.10 差分と `apps/indexer` の実挙動・README の食い違い | §2.3。P2の最初に実装・テストと突き合わせて契約表を作る。食い違いは Indexer を直さず報告 |
| 2 | 未承認の設計判断が後から変わる(特に `source_id` 文字種、glob 構文と `include_patterns`) | 設定値や1か所の定義に局所化。差し替え影響範囲を作業記録に。変更は設計書改版が先 |
| 3 | 並行処理(ハートビート・所有確認・解放・取り消し)の取りこぼし。fake は実 OpenSearch と食い違いうる | P4・P5を独立フェーズにし並行性を重点レビュー。`Event`・固定時計で決定的に。実機確認事項は持ち越し明記 |
| 4 | 削除に関わる実装の誤り(終了通知固定、件数照合、ソース削除順序、バルク削除対象選択) | 安全側(`failed`)。P6・P8 で code-reviewer を省略しない。`source_delete` の安全側分岐を網羅。タスクレビューで確認 |
| 5 | `crawl` が最大規模でフェーズ肥大 | P6を6a・6bに分けてよい |
| 6 | 全件走査の PIT・`search_after`、バルク削除部分失敗、refresh は fake で再現できない | リクエスト形テスト+契約テストで補い、実機は統合テスト(スコープ外)に持ち越し。#37は未検証と記録 |
| 7 | HTTP クライアントが `DELETE` ボディを落とす | #17契約テストをライブラリ選定条件にする(P2) |
| 8 | uv・Docker・ネットワークの可否 | できなければ未実施として記録し持ち越し |
| 9 | ログへの本文・`connector_config`・認証情報参照名の流出(pydantic 検証エラーは入力値を含む) | API の例外ハンドラは位置と型だけ返す。全ログ・エラー応答をセンチネル文字列で検査(P6・P8) |
| 10 | 複数の案が同一ファイルに集中し見落とす | 案ごとに「局所化箇所」を採用案一覧に書く |

ロールバック: 新規作成物は `apps/crawler` に閉じる。各フェーズの変更は git で戻せる。

## 11. 作業記録・STATUS.md の更新

メインエージェントのみが行う。サブエージェントは `STATUS.md` と `NNNN-*.md` を書かない(報告に現在の状況・次のアクション・未解決事項を含める)。各フェーズ・各レビュー完了時に作業記録を新規作成し同時に `STATUS.md` を更新する。P9の作業記録に仮値一覧・採用案一覧・決めた内容・持ち越し一覧・最終検証結果を集約する。

## 12. 未解決事項

- 設計書 v0.2 のユーザー承認と decisions 4章の10件の最終確定(案どおり実装、未承認のまま)
- infra 前提作業の別タスク起票(ユーザー判断)
- Dockerfile のビルド検証は Docker の可否により持ち越しの可能性
- §9 の確認事項(特に2: 起動確認の方法)
- 実機でしか確認できない項目(§10)は持ち越し
