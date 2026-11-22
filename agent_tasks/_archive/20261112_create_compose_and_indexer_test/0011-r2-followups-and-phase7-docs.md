# 0011 R2 の対応完了、フェーズ7(手順書)、スクリプトの再確認

日付: 2026-11-12
実装: code-implementer / 文書: document-writer / 再レビュー: test-reviewer / 確認・記録: メインエージェント

## 1. R2 のテスト指摘への対応と再レビュー(0010 の続き)

実装担当が A・B・C・E・N・R・S・T と Nitpick 1〜4 に対応した(0010 の方針どおり)。D(シナリオ ID でテストを選べない)はマーカー付与を見送り、スクリプトの使用例を修正し README に書いた。Q(truncated.pdf)は見送り。

### 実装時に分かったこと(指示から変わった点)

- **A(IT-41)の検出方法を変更した**: 指示は「実行前 refresh が欠ければ `deleted_count` が 0 になる」だったが、実機では `deleted_count` では区別できなかった(`source_deletion.py` が完了後に refresh と `_count` で残りを見つけて再実行し、**合算**するため、refresh が欠けても合計は 3)。そこで `refresh_interval=-1`(try/finally で復元)下で、`deleted_count == 3` に加え、`GET /loreley-documents/_stats/search` の `scroll_total` の差分が 1 であること(欠ければ 1 回目が空振りして `delete_by_query` が 2 回走り差分 2)で実行前 refresh を検出する。事前確認として、GET では 3 件読めるが refresh なしの `_count` は 0 であること(検索可能でない状態を作れていること)を assert する。実測: 素の `_delete_by_query` は `deleted: 0`、Indexer の DELETE は `deleted_count: 3` かつ `scroll_total` 差分 1。Indexer の不具合ではなく、指示の想定とテストの検出方法の差。
- **B(IT-31)**: `query_total` の差分でページ数を実測する。当初 7 件で実測 6(`_count` 2 回 + ページ 4 回)、閾値 `>= 4` に対し既定ページサイズ(1000)の推定 3 で余裕が 1 しかなかったため、test-reviewer の提案(再レビュー)で gone を 21 件に増やした(A に 22 件登録)。期待値は設計書 9.3 から導き直した(`target_count=21`、`deleted_count=21`、`denominator=22`、`enumerated_count` は A が 22・B が 1)。IT-31 は `min_delete_count=100` の最小件数ルールで削除する(`T/D = 21/22 > 0.5` で割合ルールでは削除されない。割合ルールの確認ではない)。**実測 `query_total` 差分は 13**(`_count` 2 回 + `search_after` ページ 11 回)で、4 回の実行で安定。閾値は `>= 10`。既定ページサイズなら約 3 は**未実測の推定**であることを docstring に明記。バッチ数(`DELETION_BATCH_SIZE=2`)は API・ログ・統計のいずれでも直接観測できない(設定値と件数からの推定で、設定が効かなくても通る)ことも明記。`last_seen_at` が gone 文書で同値なので、`document_id` の tiebreak を欠く実装なら取りこぼして落ちる性質も記載。
- C: `EXPIRED_LEASE_AGE = timedelta(hours=1)` を定数化。E: IT-42 に「同一ソースに複数の `deletion_result`(C0 終了済み → C1)」のテストを追加。N: IT-21 の docstring の誤りを訂正し、限界(painless が動くことと正規化の結果まで。`Instant` 比較かは判別できない)を明記。R: IT-02 に `/a.txt`・`a.txt`・`A.txt`、NFD のみ、バックスラッシュのみを追加。S・T: IT-01 の docstring を重複した簡易確認に下げ、IT-22・IT-40 で `deletion_result` を直接読んで `status`・`reason` を確認。
- IT-41 の docstring に、検出が依存する前提(`runs == 1` は 1 シャード・スライスなしに依存、realtime GET が refresh を起こさないこと(2.19.7 で実測)、素の `delete_by_query` が 0 件を返す事実はこのテストでは確認していない)を追記。

### 再レビュー(test-reviewer)の結果

**新たな Critical・Important なし**。A・B・C・E・N・R・S・T と Nitpick 1〜4 の対応は妥当(D は使用例の訂正で許容)。IT-41 は実行前 refresh、IT-31 はページサイズ、IT-42 は複数結果の各ミューテーションを検出できる。テストの信頼度は「十分」。Suggestion(IT-31 の文書数増加)と Nitpick(推定の明記、IT-41 の前提の注記、スクリプトの `-k deletion` 説明)は上記のとおり対応済み。**R2 完了**。

### 再レビューで整理された設計上の論点(ユーザー判断事項)

`loreley-deletions` のインデックス自体が無い状態で未知の `crawl_id` の Status を呼ぶと **503 `unavailable`** になった(実装は `index_not_found_exception` を全体異常として扱う。`classification.py` の `UNAVAILABLE_ERROR_TYPES`)。設計書(indexer-api-v0.10 の 4.5、indexer-architecture-v0.10 の K66・9.5)は 404 `crawl_not_found` の条件に「`loreley-deletions` を失った場合」を含め、区別しないと定める。「索引は残り記録が消えた」の意味なら実装と一致する(実機で 404 を確認済み)。「索引ごと失った」の意味なら実装との差になる。arch 14.2 の障害表(喪失後も Indexer が動き、次の開始通知で現行世代が作り直される)は後者の可能性に読めるが、文言だけでは断定できない。test-reviewer による設計書の読み取りであり、メインエージェントは原文を確認していない。→ **ユーザー判断事項として最終報告で提示する**(本タスクでは設計書・Indexer を変更しない)。補足(推測、未確認、本タスクの範囲外): 索引が無い状態で書き込むと、自動作成された索引が `dynamic: strict` を持たない恐れがある。

## 2. フェーズ7: 手順書(document-writer)

- `deploy/compose/README.md` を完成: 確認環境と「未確認」の書き方の規則、前提(メモリ・ポート・Linux の `vm.max_map_count`・SELinux `:z` は「未確認」)、`up --wait` が戻らない件、起動所要時間の目安、init の冪等性と再インデックス後の挙動、マッピング変更の手順(`down -v` で作り直す。残したまま変える手順は未確認)、停止、結合テストは `loreley-it` で実行し開発用スタックに向けないこと、OpenSearch のバージョン節(ダイジェスト・build_hash・JDK)、トラブルシュート(「実機で確認」と「想定(未確認)」に分けた)。
- `tests/integration/README.md` を新規作成: 目的、前提、一括実行(`--keep`・ファイル/`-k` 指定・終了コード・環境変数 2 つ)、手動実行、`loreley-it` で実行する理由、結果の見方、シナリオ一覧(表)、U-31 との対応とスコープ外、テスト設計上の注意、サンプルの追加方法、ファイル構成。`-k IT-30` が 0 件になること、ID の代わりにファイル名・テスト名の語で選ぶことを明記。IT-31 の件数(21 件・13 回など)は README に書かない(将来変わるため。結果記録に書く)。
- 実行結果の数値は README に書かない(結果記録に書く)。
- 引き継ぎ: 起動所要時間「初回約 90 秒 + healthy まで約 20 秒」は実装担当の実測(1 回)で、README では「1 回の実測、目安」と書いた。uv 経由の既定起動を確認したら、`tests/integration/README.md` 冒頭の「uv 経由の実行は未確認」を更新する。結果記録 `docs/v0.x/test-results/indexer-integration.md`(両 README からリンク済み)は未作成。

## 3. スクリプトの再確認(メインエージェント)

code-reviewer の指摘対応(ポート固定、使用例、`requires-python` 等)後に、`LORELEY_IT_PYTEST_CMD`(一時 venv。uv が未導入のため)でスクリプトを 1 回実行した。**環境変数 `OPENSEARCH_HOST_PORT=19200`・`INDEXER_HOST_PORT=18000` を設定した状態**で実行し、スクリプトが 9200/8000 に固定してスタックを起動し、テストが接続できることを確認した。

- 結果: 終了コード 0、**40 passed in 33.64s**、スクリプト全体 142 秒。終了後に `loreley-it` のコンテナ・ボリュームの残りなし。
- これは uv 経由の既定起動の確認ではない(フェーズ 6 で確認する)。

## 4. 未対応事項・次にやること

- **uv が未導入**(`brew install uv` は Rust 等のソースビルド中で、5 時間以上経過。ユーザーは「brew待ってみよう」と回答済み。完了時刻は読めないため、フェーズ 6 に進めない時点で再度ユーザーに確認する)。
- フェーズ 6: uv 導入後に `tests/integration` で `uv lock`、スクリプトを既定(uv 経由)で 2 回連続成功させる。pytest が `tests/integration/pyproject.toml` の設定を読むか(rootdir)も確認。結果記録 `docs/v0.x/test-results/indexer-integration.md` を作成し、`apps/indexer/README.md` 10 章の最終文を更新、`tests/integration/README.md` の uv の注記を更新する。
- R3(document-reviewer)→ タスクレビュー(task-reviewer)。
