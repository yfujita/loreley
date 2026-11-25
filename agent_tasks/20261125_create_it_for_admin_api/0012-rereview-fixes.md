# 0012 再レビュー指摘への対応(AIT-30 の size 検出力ほか)

日付: 2026-11-25
担当: code-implementer(コード)、document-writer(文書)、メインエージェント(結果文書の最終整合)

## 再レビューの結果(0011 の対応後。比較基準 d3250ee)

- test-reviewer: 前回の Important 2 件のうち I1(AIT-91 の `failure_reason` 断定)は解消。**I2(AIT-30 の `terms` の `size`)は実質未解消**。足した「クロールしない登録だけのソース」は、api の `terms` 集計(`loreley-jobs` と検索インデックスの `source_id` 別。`apps/api/src/loreley_api/infrastructure/opensearch/queries.py` 111 行目・223 行目)のバケットを作らないので、`size` が既定の 10 に退行しても `len(rows) > 10` は通ってしまい、検出力がない。AAA-U-1 の判定も強く書きすぎていた。Suggestion: AIT-91 (a) の `latest_for_source`・`rerunnable` に反映遅れに頼る直接アサートが残っている。Nitpick: `failure_detail` が `None` のとき `TypeError`。他の前回指摘はすべて解消
- document-reviewer: 前回の Important 7 件はすべて解消、新規の Important なし。Suggestion: 4.3 のシナリオ別結果に追加アサートが反映されていない、`caffeinate` 付きの回数・回番号が古い、AAA-U-1 の根拠(パス)と 7 章の表現が曖昧、Crawler 側の文書の追随なし。Nitpick: 一人称、ログ本数・所要時間の目安の更新漏れ、状態行の範囲、判定凡例に「対象外」がない

## 対応

- **AIT-30(I2)**: クロールしない登録だけのソースを足すロジックを削除し、`loreley-jobs` に `crawl` のジョブ記録と文書(1 件以上)を持つ登録済みソースが 11 件(`MIN_SOURCES_WITH_JOBS = TERMS_DEFAULT_SIZE + 1`)以上になるまで、md 1 件のソース(`q-filler`)を実際にクロールして補うようにした。アサートは `len(rows) > 10` をやめ、独立計算側で `last_crawl` を持つ行が 10 超、api 応答で `last_crawl` が null でない行が 10 超、api 応答で `document_count > 0` の行が 10 超、の 3 つ。`OpenSearchProbe.source_ids_with_crawl_jobs()`(読み取りのみ)を追加(書き込み口は増やしていない)。削除済みソースは `loreley-sources` との積集合で除く。EP-01 で `last_crawl=null` を確認する 0 回クロールのソースは残した
- **AIT-91**: (a) の `latest_for_source`・`rerunnable`・`rerun_blocked_reason` を `poll_until`(`READ_LAG_*`)で待ってから断定。クロール・削除の 2 か所で `failure_detail is not None` を先に断定してから部分一致
- **文書**: 4.3 の冒頭と AIT-20・30・40・60・91 の備考に追加アサート(7・8 回目、AIT-30 は 9・10 回目)の確認を追記、4.1・4.6 に 9・10 回目を追加、AAA-U-1 の判定と根拠(フルパス・行番号)を書き直し(AIT-30 の旧方式の誤りも記録)、AAPI-U-7 の `oversize` の行、`caffeinate` の回数、7 章の `MAX_SOURCES`(`apps/api/src/loreley_api/infrastructure/opensearch/ports.py` 26 行目の 10,000)、一人称、ログ本数・所要時間・状態行・判定凡例、`tests/integration/crawler/README.md` に Crawler IT スクリプトが `LORELEY_CRON_TIMEZONE=UTC`・`LORELEY_ADMITTING_LOCK_GRACE_SECONDS=60` を固定する旨(この IT にこの 2 変数を使うテストはない)

## 変更したファイル

`tests/integration/api/{support.py,test_30_queries.py,test_90_component_failures.py,README.md}`、`docs/v0.x/test-results/admin-api-integration.md`、`tests/integration/crawler/README.md`

## 検証結果

- `ruff check`・`ruff format --check`(11 files)・`pytest --collect-only`(23 件): OK(メインエージェントが再実行)
- クリーンな状態から `caffeinate -i scripts/run-api-integration-test.sh`(`--keep` なし)を 2 回連続で全件実行: 23 passed(pytest 442.12 秒・441.50 秒、スクリプト全体 541.64 秒・532.19 秒)。AIT-30 の実測は両回とも `rows=15`、`last_crawl` を持つ行は独立計算 11・api 応答 11、`document_count > 0` の行も 11
- 終了後 `loreley-it` のコンテナ・ボリューム・ネットワーク・`data/` なし、`docker ps -a` は他プロジェクトの `opensearch-opensearch-1` のみ(メインエージェントが再確認)

## 判断・留意点

- 7・8 回目の AIT-30(クロールしない登録だけのソース)は検出力がなかった。結果文書にこの誤りと置き換えの経緯を残した(4.4 の AAA-U-1、4.6)
- 11 件は `terms` の既定 `size` 10 に対する下限ちょうど。`size` が 10 に退行すれば 1 件欠けて AIT-30 が落ちるはずだが、**`size` を 10 に固定して落ちることの実機確認はしていない**(`apps/` を変更しない方針のため。IT の検出力を実機で確かめる方法がない)。結果文書にその旨を明記した。AAA-U-1 の判定は「確認済み」のまま、根拠と限界を併記した
- test_30 だけの所要時間は未計測。pytest 全体が 7・8 回目より約 65 秒長い(補いのクロール増と推測)
- `docs/v0.x/test-results/crawler-integration.md`(Crawler IT の結果記録)は、スクリプトの 2 変数の固定が結果に影響しない(Crawler IT は 14 passed を維持)ので変更しない。再実行の事実(14 passed、38.87 秒)は api IT の結果文書 4.6 に記録した

## 未対応事項・次にやること

- test-reviewer による AIT-30 の再確認(範囲を絞った再レビュー)と、task-reviewer によるタスク全体のレビュー
- 据え置き: shellcheck 未実施、`apps/api/Dockerfile` の古いコメント(「現時点の `api` は基盤だけ…」)、設計書の追従改訂(HO-34・35・40・41・43・44・45。結果文書 9 章)
