# 0007 crawler-module-structure 作成(P5)とR5レビュー

- 日付: 2026-11-13
- 実施: P5(document-writer)、R5(document-reviewer)、R5修正の反映(document-writer)、他文書への追従修正(FS 9.2 / architecture 7.5・11章・13.7・13.8 / api 5.4)
- 結果: R5 の指摘(Critical 0 / Important 6 / Suggestion 10 / Nitpick 9)をすべて反映。R5 の修正は最終レビューで再確認する(レビュアーは「Important の修正確認だけで足りる」としたため、最終レビューに組み込む)

## 成果物(新規)

- `docs/v0.x/system-design/crawler/crawler-module-structure-v0.1.md`(約830行)

## 設計内容(すべて案。ユーザー承認済みのモジュール分割はない)

- 層構成は Indexer に倣う: 入口層(`api`・`scheduler`)/アプリケーション機能(`sources`・`jobs`・`crawl`・`source_delete`・`documents`)/`infrastructure`(`opensearch`・`indexer_client`・`connectors`)と、層の外の `common`。機能間依存は6本(R3)。`jobs` は `records/`(`loreley-jobs` の記録)と `locks/`(ロック文書とハートビート)に分け、直下に受付・取り消し・ロック解放・回復・Job Runner・`JobContext` を置く。`crawl`・`source_delete` は `main.py` から Job Runner に注入し、`jobs` は両者を import しない(循環回避)。
- 並行モデル(CA-U-10・CI-U-9 への回答。CM-P-13〜16): 単一プロセスで HTTP ハンドラ/Job Runner/ハートビート/Scheduler の4スレッド。Connector と Indexer の呼び出しは同期で Job Runner のスレッドだけが行う。ハートビートは専用スレッド(専用の Store クライアント)でメモリ上の所有状態を持ち、Job Runner の所有確認は「喪失フラグ、または現在時刻が最後に成功したリース期限以降」(I/Oなし)。ハートビートスレッドの例外は握りつぶさず喪失扱い。ウォッチドッグなし(脱出は再起動のみ)。asyncio・別プロセスのハートビートは採らない。スレッド間の共有状態は6つ(取り消し要求・ハートビートの所有状態・Store クライアント・時計・起床通知・停止要求)。
- 終了処理の分担(R5-I-2): 実行対象(`crawl`/`source_delete`)は最終状態の記録まで。ハートビート停止とロック文書削除は、正常・例外終了のいずれでも Job Runner が必ず1回行う(所有権喪失を記録しているときは削除しない)。`crawl` は想定外の例外を自分で捕捉し、開始通知後なら終了通知 `failed` を試みてから再送出する。
- 受付の共通化(CA-P-43): `jobs` の受付3入口(手動クロール/定期クロール/ソース削除)を `api` と `scheduler` が呼ぶ。`force_delete`・`rewrite_mode` を受け取るのは手動クロールの入口だけ。取り消し要求は `jobs` のメモリ上レジストリ(CA-P-44。uvicorn ワーカー1固定)。
- 共通処理 `documents`(識別子規則・`document_id`・`content_hash`・重複除去・衝突検出・列挙済みID集合・例外変換): `document_id` 算出関数はここに置き、共有ライブラリは作らない(CI-U-1)。ずれの検出は実行時照合(CA-P-27)と、interface 5.2 の全行を1つのデータファイルにしたテストベクタ。`validate_config`・`create` の例外変換は `connectors/interface/` の関数を `ConnectorType` の保護ラッパ(レジストリ)から使い、`sources`・`crawl` が `documents` に依存しないようにする(R3 維持)。
- `connectors`: `connectors` 直下のレジストリ → `filesystem/` → `interface/`。FS の OS 呼び出しは `FsOps` として注入(FS 9.2 の注入点への回答)。MVP では `web/` を作らない。
- `opensearch`: Repository 抽象(`create`・版条件つき更新/削除を含む)と実装。索引・マッピングの作成は現時点では含めない(CM-U-7)。`indexer_client`: 1 API 1 操作の同期クライアント(厳密なJSON、base64、`source_id` のパーセントエンコード、`DELETE` のJSONボディ、APIごとのタイムアウト)。リトライの汎用機構は `common`、確認点つきで束ねるのは `JobContext`。

## 採番ID

- CM-K-1〜8(確定。他文書・CLAUDE.md の引用のみ。CM-K-3 は CA-K-2 と CA-K-19 に出典を分け、メンテナンスフラグの書き込み手段は案と併記)
- CM-P-1〜21(案)
- CM-U-1〜8(未決): 1 opensearch-py のスレッド安全性(ハートビート専用クライアントの前提確認)/2 同期HTTPライブラリの選定/3 テストベクタを Indexer 側にも置くか・実 Indexer での照合/4 SIGTERM 時の扱い/5 `/healthz`(CAPI-U-9)/6 Scheduler 周期・Job Runner 走査間隔・ハートビート再試行間隔・Store クライアントのタイムアウト・ハートビート停止の待ち上限の仮値/7 索引・マッピング作成の置き場所(CA-U-11・I-6)/8 Web Connector 追加時の構成(CI-U-9・CW-U-16・I-40)
- I-n: なし(I-50・I-51 は欠番。下記)

## 他文書の修正(R5 由来)

- I-50(FS 9.2 の「ロック解放かコンテナ再起動で解消」は誤り。ハートビートが独立して続くためリース期限内の `running` はロック解放できず(crawler-api 4.3: 409 `lock_in_use`)、脱出は再起動による回復だけ。architecture 4.7・5.8)→ FS 9.2 を修正して解消。
- I-51(architecture 7.5 の「共通処理が保持するメモリ上の集合」が interface 2章の共通処理の定義とずれる)→ architecture 7.5・4.6・CA-P-21・CA-P-26 を修正して解消(`skipped_document_ids`・`oversize_document_ids` の元集合は `crawl` の実行状態。共通処理が持つのは列挙済みID集合だけ)。
- architecture 11章: Scheduler の判定周期・Job Runner の走査間隔・ハートビート再試行間隔・Store クライアントのタイムアウト・ハートビート停止の待ち上限を仮値行として追加。13.7: module-structure の項を反映済みに。13.8: CM-U-1〜8 を追記(横断一覧の完成)。crawler-api 5.4: CAPI-U-9 に CM-U-5 への参照を追加。

## 変更ファイル

- `docs/v0.x/system-design/crawler/crawler-module-structure-v0.1.md`(新規)
- `docs/v0.x/system-design/crawler/crawler-architecture-v0.1.md`(7.5・4.6・11章・13.7・13.8 ほか)
- `docs/v0.x/system-design/crawler/connector/connector-file-system-v0.1.md`(9.2)
- `docs/v0.x/system-design/crawler/crawler-api-v0.1.md`(5.4)

## 未対応事項・ユーザー判断候補(設計書内では案・未決として記録済み。承認時にまとめて確認)

- **最優先**: 索引・マッピングの作成担当(CM-U-7、CA-U-11、I-6)。実装着手の前提になる唯一の事項(現行の `loreley-jobs` のマッピングは4項目だけの `dynamic: false` で、`record_type` での一覧や `queued_at` での並べ替えが動かない。`loreley-sources` の索引は作成物がない)。
- SIGTERM 時の扱い(CM-U-4)、`/healthz`(CM-U-5)、`document_id` テストベクタを Indexer 側にも置くか(CM-U-3。Indexer 側の変更を伴う)。
- 0005・0006 の候補(I-40、Q1「設定の削除」の解釈、glob確定・include_patterns の意味、title の取得、衝突時のジョブfailed、周期形式、メンテナンスフラグの書き込み手段、`source_id` の文字種 など)。
- mermaid はレンダリング未確認(構文を目視確認)。
- 次: 最終レビュー(全6本の横断。(a)(b)(c) と (d)(e) の2名並列。R5 修正の再確認を含む)→ task-reviewer。
