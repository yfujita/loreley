# 0009 P4: 読み取り系 EP その 2(EP-01・02・11)

日付: 2026-11-24

## 実施内容

`code-implementer` が P4 を実装。メインエージェントが検証を再実行して確認し、報告で判断を求められた EP-10 の検証順序を直接修正した。

## 検証(メインエージェントが再実行、`apps/api`)

- `uv run pytest`: 1936 passed(P3 時点 1735。実装担当の報告は 1935、EP-10 の順序修正のテスト 1 件を追加)
- `uv run ruff check`: All checks passed / `uv run ruff format --check`: 183 files already formatted / `uv lock --check`: OK
- `apps/api` 以外に差分なし
- 実装担当の検出力確認(一時的に壊して失敗を確認し復元): `delete_job` のキー付与条件、件数失敗のキー、先頭行だけへの帰属、`existence` 失敗の帰属、要求タブの件数、`items[].` 形式のキー、`tab` 違反の脱落、読めない ID 行の `unknown`、`existing_ids` を `parse_search` に戻す、偽物のメソッド名(8+2 件)

## 変更ファイル(`apps/api/` 配下)

- src 新規: `admin/services/{source_catalog,document_review,job_brief}.py`、`admin/routers/{sources,documents}.py`、`admin/schemas/{sources,documents}.py`、`admin/derivation/document_view.py`
- src 変更: `schemas/common.py`(`SourceSettings`・`ExistingJob`)、`base/codes.py`(`DocumentTab`・`DocumentExistence`・`SkipStage`・`OversizeDetector`)、`derivation/job_view.py`(`existence_of`)、`derivation/settings_view.py`(`read_source_row`)、`routers/request_input.py`(`resolve_paging` を切り出し)、`services/stalled_check.py`(`JudgedJob`・`apply_outcome`・`StalledCheck.judge`)、`services/job_queries.py`(共通部品への置き換え)、`dependencies.py`(`AdminReaders` に `search_index`・`counts`、`AdminDependencies` に `source_catalog`・`document_review`)、`routers/__init__.py`・`app.py`・`main.py`(配線)、`infrastructure/opensearch/search_index_reader.py`(`existing_ids` を `parse_uncounted_search` に)、`routers/jobs.py`(EP-10 の検証順序。下記)
- tests 新規: `admin/services/test_{source_catalog,document_review}.py`、`admin/routers/test_{sources,documents}.py`、`admin/derivation/test_document_view.py`、`fakes/test_in_memory_readers_protocols.py`。拡張: `fakes/in_memory_readers.py`・`admin/factories.py`・各既存テスト・`test_main.py`

## 判断・設計上の理由

1. **`parse_uncounted_search`(0007 据え置き分の再検討)**: `existing_ids`(R-11)は本文が `track_total_hits: false` で総件数を使わないため切り替えた(`parse_search` に戻すとテスト失敗)。`count_by_source`(R-9)は本文が `track_total_hits: true`(C 3.3)で `relation` は常に `eq`、`hits.total` も使わないため `parse_search` のまま
2. **stalled の共通化**: `StalledCheck.judge(briefs, ...)` が `running` の行だけを判定し、確認読みで読み直したジョブを行に反映(入力と同順)。EP-01・02・09 で共有。EP-01 は `last_crawl`・`delete_job` をまとめて 1 回の `mget`。読み直した行の `source_id` が欠けても元の行の値を引き継ぐ(P3 は `""` に落ちていた)
3. **EP-11 の流れ**: 設定の存在確認 → タブの一覧 → 件数 → `existence`(D 5.7)。要求タブの件数は一覧の `total` を使い `count_for_source` の対象から外す。`existence` の一括検索は読める `document_id` が 0 件なら呼ばず、失敗したら全行 `unknown` + 全行の `unavailable.existence`。`document_id` が読めない行は `unknown` でキーなし
4. **EP-11 の入力検証**: パス → 未知のクエリ → 値。`tab` が必須・不正のとき `items_per_page`・`sort` の違反も一緒に返す。`sort` はタブごとの 1 項目のみ。`tab` が決まらないときはどのタブの項目でも受ける
5. **EP-10 の検証順序(メインエージェントが修正)**: P3 の EP-10 は `dependencies=[reject_unknown_query(...)]` で未知クエリを先に判定していた(パス引数より先に実行される)。A 5.3 は パス → クエリ(案)で、EP-02・11 は適合済み。EP-02 と同じ `_query: Annotated[None, Depends(...)]` を `job_id` の後に置く形に直し、`test_the_detail_validates_the_path_before_the_query`(`/jobs/a%00b?verbose=1` は `job_id` の違反だけ)を追加。修正前のコードでこのテストが失敗することを確認

## 満たした C 11章の観点

6(source-a / source-b の行ごとの成否を service・router の両方で確認。R-3 失敗は全行にキー、`delete_job` は `deleting` の行のみ、件数失敗は全行の `document_count`、ロック `mget` 全体失敗は `running` を持つ全行、EP-11 の `existence`・`tab_counts.<タブ>`・`document_count`、EP-01 の最上位 `unavailable` は常に `{}`、`timeout` 優先、`malformed`、主たる読み取りの 503)/ 7(EP-11 の窓 10,000 ちょうどは 200、10,001 は 400 `range`、10,030 件でも `total`・`tab_counts` は正確、同順位は ID 昇順でページ間の重複・欠落なし)/ 5・16(EP-01 で検索は古い `running`、`mget` は終了済み・ロックなしの場合の偽陽性なし、行の `status` も読み直した値、読む順序 ロック → ジョブ)/ 12(`assert_secret_absent` を応答本文とログの両方に)/ 8(既存 AST 検査・R7・R4 が新ファイルでも通る)

## 設計書との食い違い・申し送り(設計書は未変更)

1. **DTO の null 許容**: B の型は `connector_type`・`status` などを非 null とするが、B 2.2 の「読めない値は `null`」に従い、`SourceListItem`・`SourceSettings` の `connector_type`・`status`・`updated_at`・`schedule_cron` を nullable に。EP-11 の `skipped`・`oversize` の `document_id` も nullable(B 6.1「`document_id` が読めない行は `unknown`」と整合)
2. **EP-02 の `delete_job` の失敗キー**: C 5.5 は EP-02 に「`status=deleting` のときだけ」と明記していない。EP-01 と同じく `deleting` のときだけキーを付けた
3. **D 3章の表にないファイル**: `derivation/document_view.py`・`services/job_brief.py` を追加(AAM-P-25 の範囲内)。`existence` は D どおり `job_view.py`
4. **OpenAPI**: `DocumentListResponse.items` は `anyOf`(4 種の行)になる。生成は成功することを確認済み。`operationId`・tags・エラースキーマ・discriminator は P7

## 未対応事項・次にやること

- 実機確認(P7 スモーク): クエリの意味(R-3 の `top_hits`・`terms` の `size`、`ids` クエリの `_id` と `document_id` の一致 = AAPI-U-7)。要約未生成タブの実データ確認は要約機能の実装後
- `InMemoryReaders` の `refresh_search()` 前後の挙動(検索は古く、`mget` はリアルタイム)は一覧系にも広げた。P5 以降の偽物も同じ流儀にする
- 次: レビュー R-B(`code-reviewer`+`test-reviewer` 並列。比較基準は R-A 完了コミット `aa88b9b`、P3・P4 が対象)。その後 P5(書き込み系・Crawler 中継)
