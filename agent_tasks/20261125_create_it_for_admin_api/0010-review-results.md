# 0010 レビューフェーズの結果と対応方針

日付: 2026-11-25
比較基準: `55dce2f` から `d3250ee`。レビュアー 3 名を並列で実施(code-reviewer・test-reviewer・document-reviewer)。web-ui-reviewer は Web UI の変更がないため省略(プラン 8 章)。

## 総評

いずれも Critical なし。code-reviewer は「可」(公開範囲・共通変数の配線・`ComposeControl` の安全性・スクリプトの `down -v`/削除の安全性・直接書き込みの範囲に問題なし)。test-reviewer は「十分(軽微な補強あり)」。document-reviewer は文書の事実と推測の混同を中心に Important 7 件。

## 指摘と対応方針

### code-reviewer(Suggestion 2・Nitpick 3)

| 指摘 | 対応 |
| --- | --- |
| S: `OpenSearchProbe.request` が未使用で任意メソッドの書き込み口 | 削除する |
| S: Crawler IT スクリプトが新しく Crawler に渡る `LORELEY_CRON_TIMEZONE`・`LORELEY_ADMITTING_LOCK_GRACE_SECONDS` を固定していない | 既定値(UTC・60)で export する(Indexer IT スクリプトは Crawler に渡らないので対象外) |
| N: `start` の `TimeoutExpired` で healthy 待ちが走らない / SIGTERM の遅れ(既存と同じ)/ `--keep` で pytest を繰り返すとソース 100 件上限 | 対応しない。最後の項目は README に一文追記 |

### test-reviewer(Important 2・Suggestion 7・Nitpick 3)

| 指摘 | 対応 |
| --- | --- |
| I1: AIT-91 の停止中クロール・削除が `failure_reason` を断定していない | `failure_reason == "indexer_unavailable"` を追加(`failure_detail` は部分一致) |
| I2: AIT-30 の `terms` の `size` が 8 ソースでは区別できない(既定 10) | フィクスチャでクロールしないソースを追加登録して 12 件以上にし、`len(rows) > 10` をアサート。結果文書の判定も追従 |
| S1: AIT-20 で 409 再送の `force_delete` が走行中ジョブに適用されていないことをジョブ側で見ていない | 終了後の EP-10 で `(force_delete, rewrite_mode) == (False, False)` を追加 |
| S2: AIT-20 の窓で検索系の待ちを先に、即時の 409 群を後に回している。compose.test.yaml の Indexer 走査 5 秒の根拠が観測(終了通知で起床、0.4〜1.1 秒)と食い違う | 409 群と EP-02 の `lock` を前に出す。コメントを観測に合わせる(値は変えない。5 秒で全件 6 回中 5 回成功しており、値の変更は再検証が要るため) |
| S3: 反映遅れに時間の余裕で頼っている箇所 5(test_20:133、test_30:251-273、test_40:146、test_90:401、test_90:332) | 少なくとも test_20:133・test_40:146・test_90:401 を `poll_until` で包む(他も可能なら) |
| S4: AIT-60 で S のジョブ記録が残ること(EP-10)を未確認 | `get_job(doomed_crawl)` が 200・ジョブ記録が残ることを追加。スキップ記録の削除は未検証として結果文書に残す |
| S5: AIT-40 の `external_id` が所属確認のみ | `document_id_of(external_id) == document_id` に強化 |
| S6: EP-07 の終了通知送信前の取消(`cancel_after_finish_notice=false`)は未検証 | 結果文書 7 章に追記 |
| S7: `request` の削除 | code-reviewer と同じ |
| N1: AIT-91 docstring と実コードの不一致 / N2: 引数順(`registered_source` が `compose_control` より先) / N3: `EXPECTED_INDEX_NAMES`・`_row_of` の重複 | 直す(docstring を実コードに合わせる、引数順、重複を `support.py` に集約) |

### document-reviewer(Important 7・Suggestion 9・Nitpick 2)

- Important: 起動直後の見え方が実機確認済みに読める(compose README)/ 1 秒の反映遅れを観測と書いているが設計値のみ・実測の最大値は未記録 / 4.4 の判定表が自身の定義と矛盾(AAA-U-1・EP-08 実ロック解放は一部確認)/ 反映遅れの対象に `last_completed_at` が抜けている / 手動手順を通しで実行していない旨の注記なし / スリープ原因を事実として書いている(推定。pytest の経過 318.78 秒と壁時計約 1 時間 42 分を根拠に)/ 9 章末尾の古い文言
- Suggestion・Nitpick: README 31 行目のポート/残骸の事前確認の書き分け、Dockerfile の行番号(10 行目。引用で示す)、所要時間の範囲(334〜358 秒)、4.6 の数値の出所(0009 に追記)、静的検査の再実行記録、`.env.example` の索引名コメントの正確化、compose README の OpenAPI パス(`/api/admin/v1/openapi.json`)、HO-40 の文言差の申し送り、メモリ推奨の根拠(未記録)と「4 サービスが常駐」、compose README 10 行目の追記、略号の凡例、compose README の結合テスト一覧に api IT を追加
- 対応: すべて document-writer に反映させる。ただし 4.4 の AAA-U-1 の判定は I2 の結果(ソース 12 件以上での確認)次第で、メインエージェントが最後に整合させる

## 対応の進め方

1. code-implementer がコード・スクリプト・compose コメントの指摘に対応し、api IT を全件 2 回連続で実行(`caffeinate -i`)
2. 並行して document-writer が文書の指摘に対応(docker・コード変更は不可)
3. 結果を踏まえ、結果文書(AAA-U-1 の判定・実行履歴・所要時間)をメインエージェントが整合させる
4. 必要なら同じレビュアーに再レビューを依頼 → task-reviewer
