# 0019 フェーズ2-2: C(Admin API アーキテクチャ)の完成

日付: 2026-11-22
担当: document-writer(メインが記録)

## 変更ファイル

`docs/v0.x/system-design/api/admin/admin-api-architecture-v0.1.md`(920 行。新規。C のみ変更。他文書は無変更=writer が `git status` で確認)

## 構成

1 位置づけ・設計原則 / 2 責務と境界(論理構成図、読み取り専用の保証 5 層、EP と呼び先の対応表 2.4)/ 3 データアクセス(索引表、共通規約、クエリ形 R-1〜R-12、3.4 `cat.*`・`cluster.health`、3.5 スキーマ依存と契約テスト、3.6 IA U-30 への回答、3.7 OpenSearch クライアントの設定)/ 4 Crawler 連携(4.1〜4.5、4.4 写像のデータ表、4.5 `config_invalid` 分解)/ 5 導出ロジック(5.10 に B の応答項目との対応表)/ 6 死活判定 / 7 設定(環境変数の個別一覧、起動時検証)/ 8 エラー処理・並行性 / 9 非機能・仮値 / 10 コンテナ・デプロイ / 11 テスト観点(16 項目)/ 12 確認状況(12.7 が B 11.10 の対応表)

## ID

- AAA-K-1〜8(確定): ユーザー回答(0001 Q1・Q1'・Q2、0004)と確定として書かれた既承認文書(CAPI-K-1・K-3・K-5、CA-K-2・K-16・K-19、IA K53)の引用。書き込みなし・`/healthz` 直取得・cron TZ・`config_invalid` 分解方式・しきい値検証・検索インデックスの読み取り許可・固定 6 経路・`api` 内 admin パッケージ
- AAA-P-1〜38(案): 承認済みの案の引用(出典 ID つき。実装形は案)= P-4・8・10・13・18・20・21・22・23・26・28・29・32(一部)。純粋な案= それ以外
- AAA-U-1〜8(未決・実装時確認): `cluster.health`・`cat.*` の項目名と型、`mget`・`msearch` の細部、refresh、`Connection: close`・Crawler 起動直後の見え方、ロックなし `running` の扱い、猶予の同期、同時実行上限と負荷の実測、最小権限
- I-90: 検索インデックスのエイリアス名(schema 設計書は未決、実装は `loreley-documents`)。I-91: ロック猶予の環境変数名(`LORELEY_CRAWLER_ADMITTING_LOCK_GRACE_SECONDS`)が設計書にない

## B 11.10 の割り当て

すべて 12.7 の表に割り当て(導出=5.1〜5.9、データアクセス=3章、環境変数=7.2・7.3、仮値=9章、Crawler クライアントと枯渇対策=4.1〜4.5・8.1〜8.3、死活=6章、部分失敗・`malformed`・`warnings`=5.8・5.4、R1 追加分=4.8・5.1・5.2・6.1・6.4・5.7・5.8、EP-07 の 404 写像・CORS のテスト観点=4.4・11章、テスト観点=11章)

## ゲート3で承認を取る案(重点)

AAA-P の「案」全件。特に: P-1〜3(読み取り API の許可リストと `mget` の使い分け)、P-5(検索インデックスの読み取り条件=IA U-30 への回答)、P-18(`stalled` の偽陽性対策。B 2.9「ロック→ジョブ」は `lock_state` では満たす。一覧はロックと食い違う `running` 行だけ、ロック→ジョブの順で読み直す)、P-19・P-25(`rerunnable` の評価順、読めない値は `null`)、P-24(ロック猶予の同期=環境変数+compose の同値定義)、P-30(OpenSearch の認証・TLS など C で足した環境変数)、P-33(`async def` + 区分別の同時実行上限 opensearch 16・crawler 4・probe 8。`/healthz` はスレッドを使わない)

## A/B への修正依頼(C から。C では変更していない)

- **B**: (1) DTO・2.2 に「ジョブ記録・削除記録由来の項目は保存値が読めないとき `null`(`unavailable` には載せない)」の注記。`JobBrief` の `status`・`job_type`・`trigger`・`queued_at`、`registration` の件数などの型に `null` を許す (2) 2.9 の「ロック→ジョブの順」に、一覧・EP-10 は確認読みで満たす旨を補足。ロックが別のジョブのものである `running` も `stalled=true` (3) 2.9・EP-10 の `rerun_blocked_reason`: データソース設定がないときの値が B にない(C は `source_deleting` に寄せた)。専用値を足すか判断。`rerunnable=null` の条件に「設定の読み取りの失敗」を追加 (4) 2.2・5.8: 理由コードは `timeout` 優先。EP-02 の `ttl_days` の `unavailable` は `ttl_seconds` のキーだけ
- **A**: (1) 4 章: OpenSearch の接続情報(`OPENSEARCH_USERNAME`・`PASSWORD`・`VERIFY_CERTS`・`CA_CERTS_PATH`。Crawler・Indexer と同じ)は任意、共通設定に索引名 4 つ(`SEARCH_INDEX_NAME` を含む)と `ADMITTING_LOCK_GRACE_SECONDS` を追加 (2) 5.6: OpenSearch の再試行条件を、接続エラー(接続タイムアウトを含む)・429・5xx は再試行、読み取りタイムアウトは再試行しない、に明確化 (3) 2.1・BAPI-U-6: 「同期関数は anyio のスレッドプール」を `async def` + 区分別の上限(C 8.1)に更新 (4) 8 章: compose で `ADMITTING_LOCK_GRACE_SECONDS` を Crawler と同じ変数から渡す。`SEARCH_INDEX_NAME` と OpenSearch の認証も渡す

## D への引き継ぎ

層: `infrastructure/opensearch`(R-1〜R-12。許可リストのクライアントのラッパー)・`infrastructure/crawler_client`(固定 6 経路、例外分類 4.3)・`infrastructure/probes`(urllib3 と opensearch のプローブ)/ 導出は純粋関数(`now` は引数)/ Crawler 写像は B 9.2 と 1 対 1 の表(データ)を 1 か所に / `config_invalid` 分解は独立関数 / `Ok / Failed(理由)` の結果型と `unavailable` キー(正式パス)の組み立て 1 か所 / 起動・停止(設定の起動時検証、値を出さない、クライアントの生成・解放 8.4)/ 区分別 `CapacityLimiter`(8.1)/ tests/fakes(OpenSearch の偽物=許可リスト外で失敗・障害注入、Crawler の HTTP スタブ=受信回数・パス記録、時計)/ tests/architecture(許可リスト外 API を呼ばない検査=Indexer の `test_write_rules.py` に倣う、`urllib3`・`opensearchpy` の import 場所の検査、スキーマ JSON との契約テスト 3.5)

## 申し送り候補(A 9章へ)

- indexer-architecture U-30(検索インデックスの読み取り条件)に C 3.6 で回答 → Indexer 設計への反映
- crawler-architecture 11章・crawler-api 4.3 に猶予の環境変数名を追記(I-91)。Admin API と同値で運用
- `search-index-v0.10.md` のエイリアス名を `loreley-documents` に確定(I-90)
- compose の環境変数: 猶予の同値、索引名、OpenSearch の認証
- 運用前提: ロック猶予のずれの影響(表示と操作がずれるだけでデータは壊れない。AAA-U-6)
- 実機・結合テストで確認する点は 12.4

## 自己検算(writer)

EP-01〜14 が 2.4 の表に対応 / B の導出項目が 5.10 に対応 / 環境変数が A・B の名前と一致 / AAA の ID 参照に未定義・未参照 0、AAPI・BAPI の参照は定義あり、表の列数・フェンス崩れ 0 / ライブラリ実物確認: opensearch-py 3.2.0(`ConnectionError` は再試行、読み取りタイムアウトだけ `ConnectionTimeout`、`str(例外)` に `root_cause` の理由とリソース ID が含まれる)・urllib3 2.8.0(`NewConnectionError` は `ConnectTimeoutError` の子)のソースを `apps/crawler/.venv` で確認 / 実機未確認は AAA-U に記載

## 未対応事項

- 上記の A/B への修正は未反映(次作業で反映)
- C 本文の `HO-n`(6 か所)はフェーズ5で A 9章の番号に置換
- D は次フェーズ。AAA-U-1〜8 は実機・実測待ち
