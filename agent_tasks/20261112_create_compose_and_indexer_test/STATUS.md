# タスク状態

## 基本情報

- 状態: done
- 現在工程: 完了(ユーザーへの最終報告待ち。ユーザー判断が必要な発見事項が 2 件、確認事項が 1 件ある)
- 最終更新: 2026-11-13
- 最新作業記録: 0016-reorganize-tests-by-module.md

## 現在の状況

- 0016(ユーザー指示): `tests/integration/` 直下の Indexer 用資材を `tests/integration/indexer/` へ移動し、参照パスを更新した(作業記録 0001〜0015 は当時のパスのまま)。移動後も 40 passed。別モジュールは `tests/integration/{モジュール名}/` に追加する。
全フェーズ(0〜7)、レビュー(R1〜R3、タスクレビュー、各再レビュー)と指摘対応が完了した。完了条件「composeを利用したテストが成功」を満たした。
- 成果物: compose(`deploy/compose/`: opensearch / opensearch-init / indexer)、OpenSearch スキーマと init(`infra/opensearch/`)、結合テスト(`tests/integration/indexer/`: 全16シナリオ・40テスト、`uv.lock` 含む)、実行スクリプト(`scripts/run-indexer-integration-test.sh`)、手順書(`deploy/compose/README.md`、`tests/integration/indexer/README.md`)、結果記録(`docs/v0.x/test-results/indexer-integration.md`)。`apps/indexer` のコードは変更していない(README の 9〜10 章のみ更新)。
- **uv 経由の既定起動で、スクリプトを 2 回連続実行して 40 passed**(13.40s / 13.13s、終了コード 0、残骸なし)。pytest の rootdir・設定ファイルの読み込みも確認。`deploy/compose/README.md` の手動手順も、書かれたとおりに実行して確認(0015、結果記録 4.1)。
- OpenSearch は `opensearchproject/opensearch:2.19.7` に固定(ダイジェスト sha256:3bfa1ec7…)。ホスト: Docker 20.10.13 / compose v2.3.3 / メモリ約3.8GiB・2CPU / x86_64(macOS)。
- uv: `brew install uv` は約8時間後に失敗(llvm と rust のみ導入)。ユーザー自身が uv 0.13.8 を導入した。
- 変更は**未コミット**(コミットの指示がないため行っていない)。`.obsidian/workspace.json` は本タスクと無関係な変更なのでコミット時に除外する。

## 次のアクション

1. ユーザーへの最終報告(0015 の 5 章)
2. ユーザーの判断に応じて: 設計書または Indexer の修正(別タスク)、U-8 の扱い、`LORELEY_IT_PYTEST_CMD` の削除の可否、コミット

## 未解決事項

- 結合テストで**未実施**(ユーザー承認済みの除外): `skipped_by_ratio`(割合ルールによる削除見送り)、`validation_failed`(件数照合の不一致)、409 競合、`_reindex`、要約、メンテナンスフラグ、認証・TLS、日本語アナライザ。U-31 の未実施項目は結果記録 4.3 に記載((1)(2)(3)(4)(8)(10)(13) と (5) の K48)
- IT-31 のバッチ数(`DELETION_BATCH_SIZE`)は直接観測できず推定。IT-41 の実行前 refresh と IT-31 の tiebreak は、実装を欠落させた状態での確認は未実施(レビューによる判断)
- 未確認: Linux ホスト(`vm.max_map_count`、SELinux `:z`)、他の OS、他の OpenSearch / compose のバージョン、init が非 0 で終了する経路などの実機での再現、shellcheck(未導入)、登録系での `loreley-deletions` 喪失時の挙動、`tests/integration/README.md` の手動実行手順どおりの実行
- ①②(30.49s、22.42s)と起動所要時間は実装担当の報告で、ログ未保存
- `up --wait` は compose v2.3.3 で戻らないため、自前ポーリングに変更した(0001 Q3 からの逸脱。最終報告で明記)
- CI 組み込みは対象外

## ユーザー判断待ち

- 作業を止めている判断待ちはない。最終報告でユーザーに判断を求める事項:
  1. `loreley-deletions` 索引自体が無い状態の Status が 503 `unavailable` になる(実機で再現済み)。設計 K66・api 4.5 は「`loreley-deletions` を失った場合」を 404 `crawl_not_found` と区別しないと定める。「索引は残り記録が消えた」の意味なら一致、「索引ごと失った」の意味なら実装との差。arch 14.2 は後者の可能性に読めるが断定できない。補足(推測・未確認): 索引が無い状態で書き込むと、自動作成された索引が `dynamic: strict` を持たない恐れがある
  2. search-index の U-8(`url`・`path` の `doc_values`)は設計書の JSON のまま未対応
  3. `LORELEY_IT_PYTEST_CMD`(uv が使えない環境向けの逃げ道)を、uv 導入後も残すか削除するか
