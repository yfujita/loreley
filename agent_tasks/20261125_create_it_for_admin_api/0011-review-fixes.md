# 0011 レビュー指摘への対応(コード・スクリプト・文書)

日付: 2026-11-25
担当: code-implementer(コード・スクリプト・compose コメント)、document-writer(文書)、メインエージェント(結果文書の最終整合・検証)。方針は 0010。

## コード・スクリプト(code-implementer)

| 指摘 | 対応 |
| --- | --- |
| code S / test S7: `OpenSearchProbe.request` | 削除(使用箇所なしを確認)。`support.py` の docstring に「任意のリクエストを送る口は持たない」を追記 |
| code S: Crawler IT スクリプトの共通変数 | `scripts/run-crawler-integration-test.sh` に `LORELEY_CRON_TIMEZONE=UTC`・`LORELEY_ADMITTING_LOCK_GRACE_SECONDS=60` の既定値 export を追加(Indexer・api のスクリプトは変更なし) |
| test I1: AIT-91 | (a) クロール・(b) ソース削除の失敗ジョブで `failure_reason == "indexer_unavailable"` と `failure_detail` に「Indexer が応答しない」を含むことを断定 |
| test I2: AIT-30 の `terms` の `size` | `crawled_sources` が、登録ソース総数 12 件以上になるよう、クロールしないソースを追加登録。`len(actual_rows) > 10` をアサート |
| test S1: AIT-20 | 終了後の EP-10 で `(force_delete, rewrite_mode) == (False, False)` を追加 |
| test S2: AIT-20 の窓の順序・compose コメント | 即時に見える確認(EP-02 の `lock`、409 群)を先に、検索系の待ちを後に。`compose.test.yaml` の Indexer 走査 5 秒のコメントを観測(終了通知で起床、0.4〜1.1 秒)に合わせて直した(値は変えない) |
| test S3: 反映遅れに時間の余裕で頼っていた箇所 | AIT-20 の終了直後の `latest_for_source`・`rerunnable`、AIT-40 の `tab_counts` 全値、AIT-90 の `superseded`、AIT-30 の `sort`・`status`・`page=2`、AIT-91 の EP-02 の `delete_job` を `poll_until`/`wait_for_*` で包んだ |
| test S4: AIT-60 | 削除後も S の過去のクロールが EP-10 で 200 で読めること、ジョブ記録が OpenSearch に残ること(クロールと削除ジョブ)を追加。スキップ記録の削除は未検証と docstring に明記 |
| test S5: AIT-40 | `external_id` を `document_id_of(external_id) == item["document_id"]`(独立実装のハッシュ)で確認 |
| test N1〜N3 | AIT-91 の docstring と実コードを合わせた(EP-10・11 の読み取りを追加、(a) の後の EP-02 の `last_crawl` と `lock.state=none` を追加)、`test_90` の引数順(`compose_control` を先に)、`EXPECTED_INDEX_NAMES`・`find_source_row` を `support.py` に集約 |
| test S6: EP-07 の終了通知送信前の取消 | 未検証として結果文書 7 章に追記(文書担当) |
| code N(`start` の `TimeoutExpired`、SIGTERM の遅れ、`--keep` で pytest を繰り返すと 100 件上限) | 対応しない(最後は README・結果文書 7 章に注記) |

## 文書(document-writer)

document-reviewer の Important 7 件・Suggestion・Nitpick に対応(`tests/integration/api/README.md`・`docs/v0.x/test-results/admin-api-integration.md`・`deploy/compose/README.md`・`deploy/compose/.env.example`)。要点: 起動直後の見え方を「設計書の記述(実機未確認)」と「実機確認したこと(AIT-90・91)」に分離、反映遅れを「少なくとも 1 回の取りこぼしを観測。約 1 秒は設計の推測で最大遅延は未測定」に、判定表を修正(EP-08 は一部確認、EP-07 も終了通知送信前の取消が未検証のため一部確認)、スリープ原因を推定と明記、手動手順は通しで実行していないと明記、略号の凡例、HO-40 の文言差の申し送り、OpenAPI パス、メモリ推奨の根拠(未記録)など。

文書担当が裏が取れず削除した記述: Crawler ログの途切れの具体時刻、`apps/api` 単体テストの所要時間、`docker ps -a` の前後確認(P5 分)。訂正した数値: 成功回数は P4 以降の 6 回(7 回ではない)、318.78 秒はスリープ中の時間を含まない(壁時計と大きく食い違う)。

## メインエージェントの最終整合

結果文書の AAA-U-1 の判定(AIT-30 が 12 件以上で `terms` の既定 `size` を超えても成功。数百件規模は未検証)、4.5 の静的検査(11 files、再実行で確認)、4.6 の実行履歴(7・8 回目)、6 章の所要時間、3 章のコミット、冒頭の状態行を更新した。

## 検証結果

- `ruff check`・`ruff format --check`(11 files)・`uv lock --check`・`pytest --collect-only`(23 件): OK(メインエージェントが再実行)
- api IT を `caffeinate -i` 付きで、クリーンな状態から 2 回連続で全件実行: 23 passed(pytest 380.75 秒・375.41 秒、スクリプト全体 482 秒・466 秒)。アプリ不具合なし
- Crawler IT(スクリプト変更のため): 14 passed(38.87 秒、全体 137 秒)
- 終了後: `loreley-it` のコンテナ・ボリューム・ネットワーク・`data/` なし、`docker ps -a` は他プロジェクトの `opensearch-opensearch-1` のみ(メインエージェントが再確認)

## 未対応事項・次にやること

- 再レビュー: test-reviewer と document-reviewer の Important 指摘への対応を、同じレビュアーで再レビュー。その後 task-reviewer
- shellcheck 未実施、Dockerfile の古いコメント(`apps/api/Dockerfile` の「現時点の `api` は基盤だけ…」)は据え置き
- `AIT-30` が実際に何行を見たかのログ出力はない(`> 10` のアサートが通ったことだけを確認)
