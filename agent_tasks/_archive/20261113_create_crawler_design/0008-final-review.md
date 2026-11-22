# 0008 最終レビュー(全6本の横断)と反映

- 日付: 2026-11-13
- 実施: 最終レビュー A(責務・一貫性・課題一覧)・B(Indexer突き合わせ・完了条件)を document-reviewer 2名で並列実施。指摘を各文書のライターに差し戻して反映。メインが機械的な整合チェックを実施
- 結果: Critical 0 / Important 5(A: 3、B: 2。重複なし)をすべて反映。Suggestion・Nitpick も反映(対応しなかったものは下記)

## レビュー結果(要旨)

**観点A(横断)**: 責務分担は 0002 4.0 の正本表どおりで、規則の再掲による食い違いなし。ID(CA/CI/CAPI/CFS/CW/CM の K・P・U、I-n)は機械照合で参照切れ・番号重複・定義漏れなし。章・手順の相互参照約586件が実在する内容を指す。ジョブ状態6種・理由コード15種の表記が全文書で一致。横断一覧13.8に全ての未決・不整合が掲載され、一行要約・参照先が実文書と一致。R5 で書き換えた箇所(終了処理の分担・所有確認・共有状態・CM-K-3 の出典・I-50/I-51 の解消)は大筋で整合。

**観点B(Indexer突き合わせ・完了条件)**: チェックリスト1〜6はいずれも一致(サンプルベクタ全10組を独立に再計算して一致を確認。ロック文書・設定スナップショットの型・件数照合 `enumerated_count == N_seen + E_missing`・ソース削除のK29順序・ポーリング区分は Indexer 設計 v0.10 と実装に一致。Indexer 設計・実装は未変更)。完了条件7項目は、満たす5・一部2(Important 修正前)。

## Important と対応

| # | 指摘 | 対応 |
|---|---|---|
| A-1 | Web 文書が I-43 の解消・I-41/I-42 の反映・`message` 緩和を取り込んでいない | Web 文書を現状(I-43 解消済み、I-40・I-44 未決、I-41・I-42 は interface に反映済み、`message` は CI-P-17 で緩和済み)に更新 |
| A-2 | `enumeration_completed` の送信開始後の異常で `failed` 通知を送る規則の穴(別内容は 409 `finish_content_mismatch` になり、`failure_reason` を上書きしうる) | architecture 4.8・5.7・CA-P-7・CA-P-28・9章を修正。`failed` 通知は開始通知の後で `send_started_at` の記録前に限る。送信開始後は送らない(取り消しと同じ扱い)。テスト観点 #31。module-structure 4.5 も整合 |
| A-3 | ロック文書を削除してよいかの基準が3通り(architecture 5.5・5.7 / module-structure 4.4 の2箇所) | 保守側に統一: 所有権喪失を記録しているときは、ロック文書が自分の owner・job_id のままでも削除しない(回復 5.8 か管理者の解放に委ねる)。停止待ち上限超過は喪失として扱い削除せず終了処理を続ける。architecture 5.7・CA-P-8、module-structure 2.2(正)・4.4・5.4・CM-P-14 を修正。テスト観点 #32 |
| B-1 | PD v0.19(L211・L144)は権限エラーも「数回リトライ」と書くが、本設計は `retry=permanent` の `fetch_permission_denied` を即スキップとしており、不整合として未記録。FS の CFS-K-6(確定欄)と 6.3 も食い違い | **I-8** を新設(architecture 13.5・13.8)。本設計の案を維持(再試行で直らないため。「その文書だけスキップ」という PD の趣旨は満たす)。CFS-K-6 の確定欄を「読めない文書はその文書だけスキップし、Admin View で確認して解消する」に絞り、「数回リトライ」は案(CA-P-19)・I-8 に移した |
| B-2 | ソース削除ジョブの実行中にメンテナンスフラグが立った場合が未定義(Indexer 11章は書き込み停止の対象を Crawler と Indexer の両方としている) | **CA-U-17**(未決)を新設。案: 順1・2・4(Indexer API のソース削除 1〜3)の送信前にフラグを確認し、立っていれば後続を止めて `failed`(`maintenance`)。ロックは終了処理まで保持、再実行で復旧。Indexer 11章の開始前チェックリストに `source_delete` ジョブが含まれない点を確認事項として併記。architecture 7.9・8章、crawler-api 4.6、module-structure 4.4・4.6・5.6 に反映。テスト観点 #34 |

## Suggestion・Nitpick の対応

- 反映したもの(主なもの): architecture 4.2 の遷移条件(202 は受理確認でない=CA-K-8 との整合)、202 後に `running` かつ `finish_received_at` なしの扱い、CA-K-13/CAPI-K-6 の 256 バイトは Indexer 側で検証規則としての仮値である旨、バッチ20件×40秒=800秒が登録タイムアウト仮値300秒を超えうる関係(CA-U-1・CA-U-14)、`loreley-jobs`/`loreley-sources` のマッピング案の表(CA-P-49。決定は CA-U-11 のまま)、Store 層の書き込み失敗の理由コード `store_unavailable`(CA-P-50)、実機確認事項を CA-U-18 に登録、13.8 の状態表記の統一と module-structure への導線、ロック文書の書き手の列挙の補完(5.3)、`K63` に関する区分の分離(確定部分と導出部分)、api の同名異義解消(HTTP 404 `source_not_found` → `source_config_not_found`)、interface 3.2 に例外変換の実装配置の注記と関連文書表・11.6 の更新、interface 7章の `max_raw_bytes`(Crawler 設定)/`MAX_RAW_BYTES`(Indexer 上限)の区別、FS の errno 記述の統一と完了済み事項の表現更新、module-structure の重複整理(2.2 を正)・共有状態への Scheduler の追加・I-50/I-51 の説明・引用元の修正 ほか
- 対応しなかったもの(理由): 略称の衝突(「api」「arch」が Indexer を指す/Crawler を指す)の全面統一は、文書数・分量が多く今回は見送り(Nitpick。必要なら後続で統一)。mermaid のレンダリング確認は環境に mmdc がなく未実施(構文は目視と機械で確認済み)

## メインが実施した機械的整合チェック

- 全文書の ID(CA-K 20 / CA-P 50 / CA-U 18 / CI-K 10 / CI-P 17 / CI-U 11 / CAPI-K 7 / CAPI-P 18 / CAPI-U 10 / CFS-K 10 / CFS-P 22 / CFS-U 6 / CW-K 5 / CW-P 6 / CW-U 20 / CM-K 8 / CM-P 21 / CM-U 8)について、参照が全て定義を持つこと・連番に欠落がないことを確認(参照切れ 0、欠番 0)。新規 ID(I-8、CA-U-17、CA-U-18、CA-P-49、CA-P-50、`store_unavailable`)が architecture に実在することを確認。
- module-structure と更新後の architecture の最終突き合わせは、module-structure のライターが実施し、食い違いのあった箇所(`store_unavailable`、ソース削除中のメンテナンス確認、CA-P-49、CA-U-18)を修正済み。

## 完了条件(0000)との対応(最終レビュー B の判定+修正後)

1. 6本作成: 満たす(`docs/v0.x/system-design/crawler/` 配下に6本、版 v0.1)
2. CrawlerとIndexerの連携仕様が整合: 満たす(Indexer 設計・実装と突き合わせ済み。B-2 を CA-U-17 として追記)
3. 責務が明確で矛盾・不要な重複なし: 満たす(B-1・A-1〜A-3 と体裁の食い違いを解消)
4. Connector共通IFがFS・Web両方に適用可能: 満たす(interface 9章・Web 4章。列挙中の一時失敗 I-40/CI-U-11 は Web 詳細設計の前の判断事項で MVP には影響しない)
5. FSコネクタが実装着手可能な粒度: 満たす
6. Webは概要設計にとどまり詳細設計が必要な箇所を明示: 満たす(CW-U-1〜20)
7. 未決・不整合が一覧化: 満たす(architecture 13.8。B-1 を I-8 として追記。CA-U-17・18 も追加)

## 変更ファイル(本記録の工程)

- `docs/v0.x/system-design/crawler/` 配下の6本すべて(crawler-architecture / crawler-api / crawler-module-structure / connector/connector-interface / connector/connector-file-system / connector/connector-web の各 v0.1)

## 未対応事項・ユーザー判断候補(設計書内では案・未決・I-n として記録済み。承認時にまとめて確認)

- **最優先**: 索引・マッピングの作成担当(CM-U-7、CA-U-11、I-6)。実装着手の前提。マッピング案は architecture 3.1(CA-P-49)に表で追記済み。
- 今判断が必要(実装前): Q1「設定の削除」の解釈=設定の直接削除 API を置かずソース削除ジョブ起動に対応づける案(CAPI-P-11/CAPI-U-1)、`source_id` の文字種(CAPI-U-4/CA-U-15)、glob の確定と `include_patterns` の意味(CFS-U-1)、`external_id` 衝突時のジョブ `failed`(CA-U-6/CFS-U-5)、「削除中」の置き場所(CA-U-2)、連続スキップの取得段階への拡張(CA-U-16)、ソース削除中のメンテナンス確認(CA-U-17)
- 実装時でよい: メンテナンスフラグの書き込み手段(CA-U-3)、周期形式(CA-U-8)、サイズ超過の記録先(CA-U-4)、`/healthz`(CM-U-5)、SIGTERM(CM-U-4)、`document_id` ベクタの置き場(CM-U-3)、Crawler と Indexer の上限整合(CA-U-14)、実機確認(CA-U-18)
- Web 詳細設計の前: I-40(CI-U-11)、I-44(Indexer の文字コード対応)
- 次: task-reviewer でタスク全体をレビュー(`0009` として記録)。
