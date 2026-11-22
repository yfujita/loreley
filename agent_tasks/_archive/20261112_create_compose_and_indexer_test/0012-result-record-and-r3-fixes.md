# 0012 結果記録の作成とレビュー R3 の指摘対応

日付: 2026-11-12
作成・修正: メインエージェント / レビュー: document-reviewer(読み取りのみ)

## 実施内容

1. `docs/v0.x/test-results/indexer-integration.md`(結果記録)を作成した(フェーズ 6 のうち uv 以外の部分)。`apps/indexer/README.md` の 9〜10 章の更新箇所(U-31 の一部を結合テストで実機確認、実コンテナの起動を確認、未実施の一覧から確認済み項目を除く)を行った。
2. R3(`document-reviewer`)を実施し、指摘に対応した。

## 結果記録の根拠(原典の整理。R3 I6 への対応)

| 値 | 原典 |
| --- | --- |
| ③ 40 passed in 33.64s、スクリプト全体 142 秒、終了コード 0 | メインエージェントの実行(`tests/integration/results/pytest-20261112-201837.log` で確認可能。0011 §3) |
| ① 40 passed in 30.49s、② 40 passed in 22.42s | **実装担当の最終報告による**(IT-31 の文書数増加・IT-41 の注記後の実行。実装担当が手動で compose 起動 → 自前ポーリング → pytest → `down -v` を行った。**スクリプトは経由していない。ログは保存していない**)。結果記録にその旨を明記した |
| 36 passed in 38.32s(手動)、36 passed in 22.93s(スクリプト経由) | 0008(実装担当の手動)、0009(実装担当のスクリプト経由) |
| 起動所要時間(初回 `up -d --build` 約 90 秒、healthy まで約 20 秒) | **実装担当の報告による(1 回の実測、ログは保存していない)**。結果記録・README に条件と出典を明記した |
| IT-30 の実測値(A: `deleted_count=0`、B: 5/4/1/3/7/3)、IT-31 の 21/22/21 と `query_total` 差分 13(= `_count` 2 + ページ 11)、IT-41 の `scroll_total` 差分 1 | 実装担当の報告(0008・0011)。R3 が作業記録・コードと一致することを確認 |
| メモリ(OpenSearch 約 855MiB、Indexer 約 56MiB)、ダイジェスト、build_hash、JDK、ヒープ | 0006(メインエージェントの実測) |
| 503 の再現(索引削除後の Status) | **メインエージェントが実機で再現**(下記) |

### 503 の再現(R3 I1 への対応。2026-11-12、メインエージェント)

`loreley-it` スタック(`deploy/compose/compose.yaml` + `tests/integration/compose.test.yaml`)で実施した。

1. `loreley-deletions` が存在する状態で `GET /crawls/unknown-crawl-r3-check` → **404** `{"error":{"code":"crawl_not_found","message":"the crawl was not found","retryable":false}}`
2. `DELETE /loreley-deletions`(OpenSearch、`{"acknowledged":true}`)
3. 同じ `GET` → **503** `{"error":{"code":"unavailable","message":"the service is temporarily unavailable","retryable":true}}`。Indexer のログ: `WARNING ... the indexer is unavailable: reason=index_not_found_exception`、`GET /crawls/{crawl_id} 503`。削除ワーカーも `deletion queue scan failed: error=OpenSearchUnavailableError` を WARNING で記録した
4. `down -v --remove-orphans` で後始末(`loreley-it` の残りなし)

これにより、結果記録 5 章の発見事項 2 は「実機で再現した事実」になった。登録系(409 `crawl_not_started` など)での同じ状態の挙動は未確認と明記した。

## R3 の判定と指摘への対応

判定: 品質は高い。軽微〜中程度の修正で可。**Critical なし、Important 6 件(I1〜I6)**。未実施事項(uv 経由の既定起動、一時 venv、コミット SHA で再現できない点、`skipped_by_ratio`・`validation_failed`、IT-31 のバッチ数が推定、U-31(7) の限界)は一貫して明記されていると評価された。数値(40 テスト、33.64s、IT-30・31・41、メモリ、ダイジェスト等)は作業記録と一致。

| 重要度 | 指摘 | 対応 |
| --- | --- | --- |
| Important I1 | 「503 になった」がコード読解由来なのに実機観測として書かれている | **対応済み**: 上記のとおり実機で再現し、結果記録に条件・応答・ログを記載(実装担当の報告とも一致)。登録系は未確認と明記 |
| Important I2 | 「実機に合わせて期待値を変えたテストはない」が広すぎる | **対応済み**: 「食い違いに起因する期待値の変更はない。ただし IT-41 の検出方法と IT-31 の規模・閾値は実機の観測を受けて変更した」に修正 |
| Important I3 | U-31(5) の「再実行の上限の数値」(K48)の未実施が結果記録と apps/indexer README から抜けている | **対応済み**: 結果記録 4.3 と 6 章、apps/indexer README の未実施一覧に追記 |
| Important I4 | 「`up -d` は 3 秒」の条件(起動済みスタックへの再実行)が無く、約 90 秒と矛盾して読める | **対応済み**: 結果記録・compose README に条件を明記 |
| Important I5 | uv.lock が存在するかのように書かれているが未生成 | **対応済み**: tests/integration/README.md の前提・ファイル構成で「未生成」と明記 |
| Important I6 | 30.49s・22.42s・起動所要時間の出典が作業記録にない。①② の実行方法が不明 | **対応済み**: 上記の原典の整理を本記録に残し、結果記録に「実装担当の報告による、ログ未保存、手動(スクリプト非経由)」と明記 |
| Suggestion S1 | README 冒頭の確認状況が条件文で循環 | **対応済み**: 「未確認。確認したら注記と結果記録 6 章を更新する」に変更 |
| Suggestion S2 | スクリプトの確認結果が結果記録にない。README の「コンテナ異常終了」は未再現 | **対応済み**: 結果記録に 4.4 を追加し、README の終了コード表に未再現の注記 |
| Suggestion S3 | 「検出できる」「落ちる」が実装を壊した上での確認でない予測 | **対応済み**: 結果記録 4.3 と README、6 章に「実装から取り除いた状態での確認は未実施(レビューによる判断)」と明記 |
| Suggestion S4 | apps/indexer README の語の整合と OpenSearch のバージョン明記 | **対応済み**(「競合(409)時の楽観ロック…基本の `if_seq_no` は確認済み」、「OpenSearch 2.19.7」) |
| Suggestion S5 | U-8 の呼称と 32766 バイトの断定 | **対応済み**(U-8 は「`path` の最大長。対策の案」と書き、32766 は未検証と添えた) |
| Suggestion S6 | WARNING・ERROR がなかったとする確認時点 | **対応済み**(フェーズ 4 の 36 テストで確認、最終の 40 テストでは未確認) |
| Suggestion S7 | SHA の追記、U-31 の記録先が 2 か所、7 章の最小コマンド | **対応済み**(6 章に SHA 追記を追加、「関連」に注記、7 章に最小コマンド) |
| Suggestion S8 | 3 章の pytest 環境の記録が実装担当のものか | **対応済み**(「実装担当が作成し、③ も同じ venv」。③ は同じ `it-venv` を使ったことをメインエージェントが確認) |
| Nitpick N1 | 終了コード表に `1` が 2 行、`-h`/`--help` | **対応済み**(表を整理)。`--help` の併記は README の記述範囲で対応(`-h`/`--help`) |
| Nitpick N2〜N5 | GB/GiB の混在、「再現できる」の言い切り、`--collect-only` の案内、外部事実の出典 | **未対応(軽微)**: 次の再レビューで対応要否を判断する |

## 未対応事項・次にやること

- R3 の再レビュー(Important があったため、プランに従い同じレビュアーで)。
- **uv の導入待ち**(`brew install uv` は Rust 等のソースビルド中。ユーザーは待つ方針)。導入後: `tests/integration` で `uv lock`、スクリプトを既定(uv 経由)で通す(2 回連続成功)、pytest の rootdir・設定の読み込みを確認、結果記録 3・4・6 章と README の uv の注記を更新。
- タスクレビュー(task-reviewer)。最終報告にはユーザー判断事項(`loreley-deletions` 喪失時の 503/404、U-8)、`up --wait` の逸脱、未実施項目を明記する。
- Nitpick N2〜N5 の対応要否。
