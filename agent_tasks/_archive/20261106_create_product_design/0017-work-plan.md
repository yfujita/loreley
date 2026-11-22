# 0017 作業プラン:Crawler / Indexer のコンテナ分離とHTTP直接通信への変更

> 状態:**ユーザー承認待ち**(承認前は設計書に着手しない)。planner の報告をもとにメインエージェントが作成した。

## 背景・決定事項

ユーザーの指示(2026-11-08):メッセージブローカーを使わず、HTTPで直接通信する。Crawler と Indexer は別コンテナに分け、ジョブの起動もHTTPにする。
将来キューが必要になったとき、HTTP部分をメッセージングに置き換えられるよう、コンポーネント間の契約(API)を明確に定義する。

方針を変える指示(構成・設計判断が変わる)なので、プランを更新する作業記録として残す。

### ユーザー確認済み(AskUserQuestion の回答)

| # | 論点 | 決定 |
| --- | --- | --- |
| Q1 | ジョブの起動と記録 | **Crawler が受信時に記録する**。Admin API は `loreley-jobs` に書かない。Crawler がロック `lock-{source_id}` を create し、ジョブを `queued` で保存してから 202 と `job_id` を返す。同一ソースが実行中・待機中なら 409(既存の `job_id` 付き)。Admin API は 409 を成功として扱う。Crawler は起動時に `queued` を再投入し、`running` を `failed` にする。実行は Crawler 内の FIFO で直列 |
| Q2 | 責務境界 | **データは Indexer、ジョブは Crawler**。Indexer は `loreley-texts` と検索インデックスの唯一の書き込み役(全文upsert、`last_seen_at` 部分更新、削除、要約生成、突合の実処理)。Crawler は `loreley-jobs` の唯一の書き込み役(ジョブ、ロック、リース、スキップ記録、削除保留)。リトライ・スキップ判断(最大3回、4xx連続20件)は Crawler、Indexer は文書単位のエラー種別を返す。書き込み前のロック所有確認は Indexer が行い、Crawler は `owner` と `job_id` を渡す。削除前は Crawler も確認する。要約生成は Indexer 内部。§4.4「クロール中は要約を書かない」は `content_hash` の条件付き更新で代替し、緩和する |
| Q3 | バッチ契約 | **同期 multipart**:`POST /internal/v1/documents:batch`。メタデータ配列と原本バイナリ。応答は文書単位の結果(`succeeded` / `skipped` / `failed` + エラー種別)を HTTP 200 で返す。上限(案):件数20以下、合計32MiB、1文書16MiB(超えるものは単独バッチ)、絶対上限50MiB(超過は Crawler が送信前に `too_large` でスキップ。Admin View に表示。`last_seen_at` は更新済みなので削除はされない)。タイムアウト120秒(案)、並列度1、失敗した文書だけ再送。`document_id` と `content_hash` で冪等 |

### 前提として置く案(**未確認。承認時に異論がなければ採用**)

- **メンテナンス**:メンテナンスフラグは Indexer が書き込み前に確認し、立っていれば 503 `maintenance`。Crawler はジョブ開始時と各バッチ間でも確認し、503 を受けたら理由付きの `failed`(削除なし)にする。§2.5 の「Worker を停止」は「Crawler と Indexer を停止」に読み替える。
- **`:ro` マウント**:Crawler のみ。Indexer は不要。
- **`last_seen_at` の部分更新**:Crawler が列挙を一定件数ずつまとめ、取得より前に `POST /internal/v1/sources/{source_id}/seen` を呼ぶ(`document_id` 配列と `crawl_started_at`)。応答は文書単位の `updated` / `not_found` / `failed`。`failed` が1件でもあればジョブを `failed` にして削除しない。
- **Indexer ダウン・遅延**:接続不可、タイムアウト、502/503/504 は OpenSearch 全体の異常と同じ扱い(リトライして直らなければ `failed`、削除なし)。文書固有の 4xx(`document_rejected`)だけをスキップ対象にし、連続20件で `failed`。ハートビートは別スレッドで送る。
- **ネットワーク**:Crawler と Indexer は Compose の内部ネットワークのみ。`ports:` を公開しない。内部APIは `/internal/v1/`。認証なしの前提は変えない。`GET /healthz` を用意し、`depends_on` と healthcheck で起動順を制御する。
- **Admin API**:`api` コンテナに同居。ジョブ状態の表示は `loreley-jobs` を読み取りのみで直接読む。更新(`POST /crawl`、cancel、ロック解放、削除保留の承認・却下、全件削除の確認、突合の起動)はすべて Crawler のHTTP経由。固定の endpoint だけを中継し、任意パスの転送はしない。定期実行は Crawler 内蔵のスケジューラ。
- **ソース削除(§1.2)・突合(§3.6)**:ジョブとして Crawler が持ち、検索インデックスと Store層の操作は Indexer のAPIを呼ぶ。
- **成果物**:`system-design-v0.3.md` を新規作成(v0.2 は変更しない)。`product-design-v0.9.md` を新規作成(最小差分)。`docs/v0.x/system-design/crawler/`・`indexer/` は今回使わず、契約は v0.3 の新章に集約する。

## フェーズ

| フェーズ | 内容 | 担当 | レビュー |
| --- | --- | --- | --- |
| P0 | 上記の承認を得る | ユーザー | - |
| P1 | v0.3 の新章:責務表、内部API契約(起動、バッチ登録、seen、削除、メンテナンス、healthz)、メッセージング移行の前提(少なくとも1回配送でも安全、順序非依存、同期応答は結果イベントに置換可能) | document-writer(必要なら事前に tech-advisor で multipart・サイズ上限・タイムアウトの相場を調査) | general-purpose(責務の重複・空白、全 endpoint が冪等、文書単位の結果を返せる、同期応答が必須になっていない) |
| P2a | v0.3 本体:§1.1、§1.5、§2.4、§2.5、§3(概要、§3.1、§3.4〜§3.6)、§4 全体、§8 | document-writer | general-purpose |
| P2b | v0.3 本体:§6.3、§6.4、§7(論理構成図、Compose分割、ネットワーク、`:ro`)、§10、§12、§13(用語集)、改訂履歴、v0.2 との差分対応表 | document-writer | general-purpose。「Worker」の残存を grep、§番号参照の整合、`last_seen_at` の流れが契約と一致 |
| P3 | §11 のテスト設計:新規の契約テスト(仮ID I-n:202/409、バッチの部分成功、タイムアウト後の再送が冪等、Indexer ダウン、サイズ超過、メンテナンス中の503、内部endpointの非公開、cancel)。影響を受ける E-3、E-4、E-7、E-18、E-21、E-23、C-1、C-8、C-9、L-1、L-3、L-5、L-8、L-9、R-2、R-3 を更新。C-8(同一ソースの二重起動要求へ)、L-6(窓が Indexer 側にも広がる)は前提が変わる | document-writer | test-reviewer |
| P4 | product-design-v0.9:§3 構成図の注記、§4.7 と §7 のコンテナ記述、「単一Worker・直列実行」→「単一Crawler・直列実行」、疎結合方針を1〜2行、大きな原本が検索対象外になる挙動を1行、v0.3 への参照更新、改訂履歴 | document-writer | general-purpose(プロダクト判断を変えていないこと) |
| P5 | 両文書の整合レビュー(v0.2 との矛盾、前提の維持)。Critical / Important は修正して再レビュー | general-purpose | - |
| P6 | タスクレビュー。未解決事項を最新の作業記録に書く | task-reviewer | - |

各フェーズの終了ごとに、メインエージェントが作業記録 `0018-` 以降を残す。サブエージェントは作業記録を書かない。

## リスク・前提

- 置き換え漏れ:v0.2 の「Worker」は §2.4、§2.5、§4、§7、§11、用語集に多数ある。P2b の末尾で grep による残存確認を必須にする。
- 窓の拡大:Indexer による所有確認でも、確認から書き込みまでの窓は残る。完全な分散フェンシングは将来拡張(§4.7)のまま。`last_seen_at` が戻らないことだけを保証する(L-6)。
- ブロッキング:同期HTTPでは、遅い Indexer がクロール全体を律速する。MVPでは許容する(並列度1、タイムアウト、バッチ上限)。
- 上限超過の原本が検索対象外になるのは、ユーザー向けの仕様変更。
- 前提は維持する:単一ホスト、単一 Crawler・単一 Indexer の直列実行、認証なし、OpenSearch を Store層とする、MVPで異常系を作り込みすぎない。
- 要件定義(0000)は書き換えない。

## 未対応事項

- 「前提として置く案」と、数値の案(上限、タイムアウト、リトライ)のユーザー確認。
- 0016 から持ち越し:§3.7 冒頭の表現のずれ、0010・0011 の仮決定、削除保留の最小件数ルール(9.1)、system-design の通読による整合確認。
