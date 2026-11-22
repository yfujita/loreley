# 0001 要件確認(確定した要件)

日付: 2026-11-13 / 実施: requirements-clarifier(2回)+ユーザー回答(AskUserQuestion)

## ユーザー回答(いずれも推奨案を選択)

- Q1 成果物の範囲: Crawler 全モジュール + 単体テスト + Dockerfile・README
- Q2 infra 前提作業: 本タスクに含めない。別タスクとして未対応事項に記録する
- Q3 未承認の設計判断: decisions v0.2 の4章の未承認10件、CM-U-4、CA-U-3 は設計書の案どおり実装する。採用した案の一覧を作業記録に残す

「完了条件の具体化」と「前提として置く事項」は、ユーザーの個別承認を得ていない。確定ではなく「提案どおり進める」扱いとし、**プラン承認時にユーザーへ改めて確認する**。

## 確定した要件

### 目的・位置づけ

- Crawler(`apps/crawler`、Python パッケージ `loreley_crawler`)を設計書に従って実装し、単体テストを通す。
- Crawler の役割: データソースの列挙・取得、ジョブ・ロック・リースの管理、Indexer への開始通知・登録・終了通知・ポーリング、ソース削除ジョブ、Admin API 向け HTTP 受け口。
- 現状は設計書のみで `apps/crawler/` は存在しない。
- Connector は FileSystem のみ。Web Connector は対象外(CW-K-1・2)。

### 仕様の正本

- `docs/v0.x/system-design/crawler/` の最新版(要件定義の `docs/system-design/crawler` は読み替え)
  - `crawler-architecture-v0.2.md` / `crawler-api-v0.2.md` / `crawler-design-decisions-v0.2.md` / `crawler-module-structure-v0.3.md`
  - `connector/connector-interface-v0.2.md` / `connector/connector-file-system-v0.2.md`
- Indexer 契約は `docs/v0.x/system-design/indexer/indexer-api-v0.10.md` を正とする(Crawler は呼び出し側)。
- 要件定義(0000)は書き換えない。

### 実装範囲(Q1)

- `apps/crawler/src/loreley_crawler/` に module-structure v0.3 の全モジュール
  - 入口層: `api`(Admin API 6エンドポイント)、`scheduler`
  - アプリケーション機能: `sources`、`jobs`(`records/`・`locks/`)、`crawl`、`source_delete`、`documents`、`connectors`(`interface/`・`filesystem/`・レジストリ)
  - `infrastructure`: `opensearch`(Repository 実装)、`indexer_client`
  - 層の外: `common`
  - `main.py`、`config.py`(起動時の整合性検査を含む)
- 成果物: `pyproject.toml`、`uv.lock`、ruff・pytest 設定、`.python-version`、`.gitignore`、`tests/`(`fakes/`・`architecture/` 含む)、`Dockerfile`、`README.md`(起動・設定・テスト手順、fake だけでは検証できないことの明記)
- ConnectorType は `file_system` のみをレジストリに登録する。

### スコープ外

- Crawler の Integration Test。
- infra 前提作業(Q2)。次を別タスクとして未対応事項に記録する。
  - `infra/opensearch/schema/` への `loreley-sources` 追加、`jobs.json` 拡張(Indexer 結合テストと共有のため同時更新が必要。Indexer が読む4項目 `owner`・`job_id`・`lease_expires_at`・`enabled` の型は維持)
  - `infra/opensearch/init-indices.sh` への `loreley-sources` 作成と索引名の環境変数追加
  - 既存索引への反映(put mapping またはボリューム再作成)
  - `deploy/compose/compose.yaml` への `crawler` サービス追加(`opensearch-init` 完了待ち、Indexer 上限値の受け渡し、`:ro` マウント)
- マッピング案(architecture 3.1 の表、CA-P-49)は README かコードのコメントで参照として残す。
- 設計書(docs)は変更しない。案を変えたい場合は設計書の新版を提案する。
- Indexer(`apps/indexer`・Indexer 設計書)は変更しない。契約の食い違いは報告する。
- Web Connector、複数 Crawler・キュー化は対象外。

### 未承認の設計判断の扱い(Q3)

decisions v0.2 の4章の10件は設計書の案どおり実装する。

- source_id の文字種: 半角英数字で始まり、半角英数字・`.`・`_`・`-` のみ(CAPI-P-15)
- glob 構文と `include_patterns` は「既定拡張子への追加」(CFS-U-1)
- `external_id` 衝突はジョブ `failed`(CA-P-24)
- 「削除中」は `loreley-sources.status=deleting`(CA-P-35)
- 連続スキップは取得段階と登録段階の別カウンタ(CA-P-20)
- ソース削除の順1・2・4の送信前にメンテナンスフラグを確認し、立っていれば `failed`(`maintenance`)(CA-U-17)
- 設定項目は必須・既定値なし・全置換、`connector_type` は変更不可、メンテナンス中は409(CAPI-P-4・7・9)
- 識別子エラーは `partially_succeeded`、原本サイズ超過は別記録でジョブ status に影響しない(CA-P-25・23)
- `follow_symlinks`・`include_hidden` は両方 `false`、`title` はファイル名のみ
- 0件列挙は現状維持(警告のみ。CA-P-52)

その他:

- CM-U-4(SIGTERM): 実行中ジョブの完了を待たず終了処理もしない。次回起動時の回復で `failed`(`crawler_restart`)にする。
- CA-U-3(メンテナンスフラグの書き込み手段): 運用者の手動手順とし、Crawler は読み取りのみ。
- 案に依存する箇所は局所化する(設定値・分類定義・パターン構文など)。
- 採用した案の一覧を作業記録に残す。案は「実装仕様としての採用」であり設計の承認ではない。設計書の承認は引き続きユーザー判断待ち。
- 実装者が決めてよい事項(decisions 5章)は決めて作業記録に残す: 数値の仮値、実機確認事項、HTTP クライアントライブラリ(CM-U-2)、CM-U-9、CA-P-49・53・54の細部、モジュール内部のファイル名。
- 案がなく決めてよい事項にも当たらない判断は、推測で確定せずユーザーに確認する。削除に関わる判断は安全側(ジョブを `failed` にして削除させない)に倒す。

### 完了条件(提案どおり進める扱い。プラン承認時に確認)

0000 の完了条件「Crawler が実装され、単体テストが通っている」を次のとおり具体化する。

1. `apps/crawler` が module-structure v0.3 の構成で存在し、依存ルール R1〜R6・R10 に反しない(`tests/architecture` の import 検査。Indexer に倣う)。
2. `uv run pytest`・`uv run ruff check`・`uv run ruff format --check` がすべて成功する。結果を作業記録に貼る。
3. Admin API の6エンドポイントが crawler-api v0.2 の契約どおり応答する(形式不正・未知項目は400、共通エラー形式、受付拒否は409の3種 `source_deleting`・`maintenance_enabled`・`lock_held`)。TestClient で検証する。
4. FS Connector: FS 設計書10章のテスト #1〜23 と interface 10章の契約テストを、一時ディレクトリと偽の `FsOps` で実装する。権限エラーのテストは root で skip、Linux 専用テストは macOS で skip。
5. architecture 12章のうち単体テストで可能なものを、メモリ上の fake(Repository・Indexer 向け偽クライアント・固定時計・偽 Connector・偽 `FsOps`)で実装する(呼び出し順、設定スナップショット・終了通知の固定、型の strict、リトライ・スキップ・連続20件、ポーリングの区分、取り消し、ロック・ハートビート・所有権喪失、起動時の回復、ソース削除の順0〜6、メンテナンスフラグ、登録結果の集計、設定の1回読み取り、0件警告、起動時整合性検査の純粋関数)。`DELETE` のボディ(#17)はローカルの簡易 HTTP サーバに対する契約テスト。
6. `document_id` のテストベクタ(interface 5.2)を `tests/` のデータファイルとして置き、算出関数を検証する。
7. メモリ上の Repository は、全件走査・ID のバルク削除(部分失敗を注入可能)・条件指定の削除を含め、`opensearch` 実装と同じ契約を実装する。
8. ログに本文・秘密情報・認証情報の参照名・`connector_config` を出さない。テストで確認する。
9. `docker build apps/crawler` が成功し、起動を確認する。Docker が使えない場合は未実施・持ち越しと記録する。
10. 作業記録に、仮値一覧(設定名・既定値・根拠 ID)、採用した案の一覧(Q3)、決めてよい事項で決めた内容、持ち越し一覧を残す。

### 持ち越し(単体テストでは検証しない)

- 実 OpenSearch・実 Indexer が必要な項目: architecture 12章の #37(10,001件以上、PIT、refresh、バルク削除の部分失敗)、#39の統合部分、`create` と `if_seq_no` の原子性、opensearch-py のスレッド安全性(CM-U-1、CA-U-18)、実 Indexer とのバッチ応答の `document_id` 照合(CM-U-3)、実機での FS の errno・マウント外れ・取得中の変更検出(CFS-U-4)、Linux コンテナ・NFS/SMB でのブロッキング I/O 中のスレッド挙動。
- fake だけでは検証できないことを README と作業記録に明記する。

## 前提として置く事項(提案どおり進める扱い)

- 技術スタックは Indexer に揃える: Python 3.12(`>=3.12,<3.13`)、uv、FastAPI + uvicorn(単一プロセス、workers=1)、pydantic v2、pydantic-settings、opensearch-py(同期)、pytest、ruff。環境変数接頭辞は `LORELEY_CRAWLER_`。ruff 設定は Indexer と同じ(line-length 100、select は E,F,I,UP,B,SIM,RUF)。並行モデルは module-structure のとおり(同期ハンドラ、Job Runner・ハートビート・Scheduler は `threading`)。
- 同期 HTTP クライアントのライブラリは実装時に選ぶ(CM-U-2)。条件: `DELETE` にボディを載せられる、API ごとにタイムアウトを設定できる、スレッドから使える。候補は urllib3 か httpx 系。選定理由は作業記録に残す。Indexer の `httpx2` は TestClient 用の dev 依存で本番用ではない。
- CM-U-9(起動時整合性検査)の仮置き: Indexer の上限値は Crawler 接頭辞つきの名前で読む。未設定の項目は警告を出してその項目の検査を省略する(選択肢(a))。採用内容は作業記録に残す。
- 数値は architecture 11章の仮値を設定可能な値として実装する。空欄の項目(Scheduler 周期、Job Runner の走査間隔、ハートビート再試行間隔、Store 層のタイムアウト、停止待ちの上限、走査・条件指定の削除のタイムアウト)は実装者が仮値を置いて記録する。
- 要件定義の「対象範囲: docs/system-design/crawler」は変更対象ではなく参照先と解釈する。「Clawler」は Crawler と読み替える。
- フェーズの目安: 基盤・`common` → `infrastructure` → 共通処理(`documents`・`connectors`) → `jobs`・`sources` → `crawl`・`source_delete` → `api`・`scheduler`・`main` → Dockerfile・README。各フェーズでコード・テストのレビュー、最後に task-reviewer。実装は code-implementer、レビューは別エージェント。

## 未解決事項(次工程・別タスクで扱う)

- 設計書 v0.2 のユーザー承認と、decisions 4章の10件の最終確定(案どおり実装するが未承認のまま)。
- Indexer 契約の差分確認: `apps/indexer/README.md` は indexer-api v0.9 参照、Crawler 設計書は v0.10 前提。プラン作成時または実装時に v0.9→v0.10 の差分と `apps/indexer` の実挙動を確認し、食い違いは報告する(Indexer は変更しない)。
- infra 前提作業(Q2)の別タスク起票(ユーザー判断。提案のみ)。
- Dockerfile のビルド検証は Docker の可否により未実施・持ち越しの可能性。
- 完了条件の具体化と前提は、プラン承認時にユーザーが最終確認する。

## 次のアクション

1. STATUS.md を更新する(本記録で完了)
2. planner で作業プランを作成し `0002-work-plan.md` として保存する
3. ユーザーの承認を得てから実装に進む
