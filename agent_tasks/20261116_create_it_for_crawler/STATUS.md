# タスク状態

## 基本情報

- 状態: done
- 現在工程: 完了(ユーザーへの最終報告待ち。ユーザー判断が必要な事項が 3 件ある)
- 最終更新: 2026-11-16
- 最新作業記録: 0013-task-review-and-closing.md

## 現在の状況

- 全フェーズ(0〜6)、レビュー(R1・R2・R3 と再レビュー、タスクレビュー)と指摘対応が完了した。完了条件「Integration Test が成功する」を満たした。
- 成果物: Compose(`deploy/compose/compose.yaml` に `crawler` 追加、`.env.example`、`tests/integration/crawler/compose.test.yaml`)、スキーマ(`infra/opensearch/schema/sources.json` 新設、`jobs.json` 拡張、`init-indices.sh`)、テスト(`tests/integration/crawler/`、13 件 CIT-01〜50)、実行スクリプト(`scripts/run-crawler-integration-test.sh`)、結果記録(`docs/v0.x/test-results/crawler-integration.md`)、手順書(`tests/integration/crawler/README.md`、`deploy/compose/README.md`)。修正した Crawler はなし(`apps/crawler` のコードは未変更。README のみ更新)。
- **最終コードで一括スクリプトをクリーンな状態から 2 回連続: 13 passed(44.54s / 43.88s)・終了コード 0**。Indexer IT の回帰: 40 passed(37.69s)。README の手動手順も実行して 13 passed。最終版のスクリプトの失敗経路(待機超過=10、ポート占有=1)も確認済み。OpenSearch は 3.9.0。
- 変更は**未コミット**(コミットの指示がないため行っていない)。

## 次のアクション

1. ユーザーへの最終報告(0013 の最終報告に含める事項)
2. ユーザーの判断に応じて: 設計書の反映(別タスク)、`fess-opensearch` の再作成、コミット(コミット後に結果記録 3 章へ実施時点の SHA を追記)

## 未解決事項

- 結果記録 3 章の実施時点のコミット SHA はコミット後に追記が必要
- 未実施・未確認(結果記録 6 章): 権限エラーの `skip` 記録・`partially_succeeded`、ソース削除時のメンテナンス 409、`enabled:false` で下ろす手順、10,001 件超、`create` の並行原子性、`docker stop`、起動時の回復、ロック解放 API・取消 API、実 NFS/SMB、Web Connector ほか。スクリプトのシグナル・`--keep`・残骸検出の失敗経路・コンテナ占有時のポート表示・`compose down` 失敗時の分岐・`shellcheck` は未確認
- 不確実点: ロック観測の窓(約 3.3 秒)への依存、ホストと VM の時計差、TTL の前提作りが Indexer 内部の項目名 `last_seen_at` に依存
- スクリプトの重複(Indexer 用・Crawler 用)は 3 つ目のモジュールのときの負債。CI 組み込みは対象外

## ユーザー判断待ち

作業を止めている判断待ちはない。最終報告でユーザーに判断を求める事項:

1. `fess-opensearch`(別プロジェクト)は、ユーザーが停止した後、コンテナ自体が存在しない状態になっている(私は操作していない)。必要なら再作成が要る可能性がある。また Fess アプリが(推定)テスト用 OpenSearch に書き込んだ。テストは 9200 固定のため、Fess 稼働中は混入し得る(`loreley-*` には無影響)
2. arch 10 章との差(Crawler をループバックに publish、Indexer に上限 6 項目を明示的に渡す)と、`loreley-sources` の `dynamic: strict` の決定(arch 3.1 は「実装時に決める」)を、設計書に反映するか
3. FileSystem Connector の `root` はコンテナ内の任意の絶対パスを受け付ける(`:ro` が守るのはホスト側のファイル。API は認証なしでループバックのみ)。このままでよいか
