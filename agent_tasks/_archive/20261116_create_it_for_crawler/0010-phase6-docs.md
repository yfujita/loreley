# 0010 フェーズ 6: 結果記録・手順書

日付: 2026-11-16
作成: document-writer / 手動手順の実行確認: メインエージェント

## 実施した作業の概要

結果記録・手順書・README を作成・更新した(動作確認の本体は 0009)。

## 変更したファイル

新規:
- `docs/v0.x/test-results/crawler-integration.md`(indexer-integration.md の形式。1 目的 / 2 記録のルール / 3 環境 / 4 結果(4.1 起動確認、4.2 シナリオ別 13 件、4.3 `apps/crawler/README.md` 8 章との対応表、4.4 スクリプト、4.5 Indexer 回帰)/ 5 発見事項 / 6 未実施・未確認 / 7 再実行手順)
- `tests/integration/crawler/README.md`(実行方法、シナリオ一覧、結果の見方、サンプルの追加、同時実行不可、メンテナンスフラグ残りの復旧、`data/`・`CRAWLER_DOCUMENTS_DIR`)

更新:
- `docs/v0.x/test-results/indexer-integration.md`(9 章を末尾に追記。既存の 1〜8 章は書き換えていない。回帰確認 40 passed)
- `deploy/compose/README.md`(4 サービス化、`crawler` サービスの節、ループバック公開の理由と arch 10 章との差、`CRAWLER_DOCUMENTS_DIR` の注意(R1 の S1・S2)、上限・索引名の同値定義、`jobs.json` 拡張済み・`sources.json`、トラブルシュート(8001・Fess))
- `apps/crawler/README.md`(1・6・7・8・9 章を最小限に。8 章は項目ごとに「確認 / 一部確認 / 未確認 / 未実施」、9 章は済みと未対応に分けた)

`tests/integration/indexer/README.md`・`apps/indexer/README.md` には `jobs.json` が仮定義だという記述はなく、更新していない(`apps/indexer/README.md` 6 章の「仮定義」表は Indexer 側の前提の話)。設計書・コード・`agent_tasks/` は変更していない。

## 判断・設計上の理由

- 8 章の対応表は README の実在する項目から作った(項目は作っていない)。テスト関数がない項目は「未実施」、動作はしたが専用アサートがない項目は「一部確認」とし、確認済みとは書いていない。
- 失敗経路(`LORELEY_IT_WAIT_TIMEOUT_SECS=1`・ポート占有)の確認は R2 反映前の版で行ったものである旨を、結果記録 4.4 に明記した。

## 作成者が挙げた確認事項(R3 で確認する)

- `deploy/compose/README.md` の既存記述「アイドル時のメモリ(OpenSearch 約 855MiB 等)」に「OpenSearch 2.19.7 での測定」と付記した。出典は `indexer-integration.md` 3 章(2026-11-12 の記録は 2.19.7)で、**推定**。誤りなら削除する。
- 未指定時の `deploy/compose/documents` の自動作成と 0 件列挙、`:` を含むパスの不可は、実機未確認と書いてある。
- 最終実行のログ名(`pytest-20261116-165128.log`、`pytest-20261116-165404.log`)は、ファイルの更新時刻と所要時間の一致から対応づけた。
- 結果記録 3 章の「実施時点の SHA」はコミット後に追記が必要(現在は基準コミット `6970478` と「未コミット」の記載)。

## 手動手順の実行確認(メインエージェント)

`tests/integration/crawler/README.md` の「手動で実行する」の手順 1〜5 を、書かれたとおりに実行した。起動(`up -d --build opensearch opensearch-init indexer crawler`)→ `opensearch`・`indexer`・`crawler` が healthy、`opensearch-init` が Exited(0) → `pytest` **13 passed(37.94s)、終了コード 0** → `down -v --remove-orphans` と `rm -rf data`(`ps -a` 空、`data/` なし、`deploy/compose/documents` も作られていない)。

## 未対応事項・次にやること

1. R3(`document-reviewer`)→ 指摘対応
2. タスクレビュー(`task-reviewer`)
3. 最終報告(Fess の件、`fess-opensearch` の再起動の要否、9200 固定、未コミット、arch 10 章との差を設計書に反映するかの判断)
