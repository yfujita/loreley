# 0008 P3: 読み取り系 EP その 1(EP-09・10・12・14)と導出

日付: 2026-11-24

## 実施内容

`code-implementer` が P3 を実装(R-A 取り込み分 (a)(b)(c) を含む)。メインエージェントが検証を再実行して確認した。

## 検証(メインエージェントが再実行、`apps/api`)

- `uv run pytest`: 1735 passed(P2 後 1150)
- `uv run ruff check`: All checks passed / `uv run ruff format --check`: 169 files already formatted / `uv lock --check`: OK
- `apps/api` 以外に差分なし。`pyproject.toml`・`uv.lock` 未変更。リポジトリ直下に作業中に誤作成されたファイル(`common.py` 等)が残っていないことを確認
- 実装担当の検出力確認(一時的に壊して失敗を確認し復元): R7 違反の `import random`、`lock_state` の猶予・期限境界、`stalled` の期限境界、確認読みの順序、窓比較 `>=`、`failure_detail` の限定、読み直しの反映、行ごとの帰属、`relocating` 分解、シャード primary 順、404/503 混同(計 12 件すべて検出)

## 変更ファイル(`apps/api/` 配下)

- src 新規: `admin/derivation/`(10 ファイル: `values`・`lock_state`・`stalled`・`rerun`・`job_view`・`deletion_view`・`source_summary`・`settings_view`・`units`・`cluster_view`)、`admin/schemas/{common,jobs,opensearch,meta}.py`、`admin/services/{stalled_check,lock_view,job_queries,cluster_overview,meta}.py`、`admin/routers/{jobs,opensearch,meta}.py`
- src 変更: `admin/__init__.py`・`app.py`・`dependencies.py`(サービスの束・`AdminReaders`・`build_admin_dependencies`)・`base/codes.py`(列挙型追加)・`routers/__init__.py`・`main.py`(Reader 4 種の生成と配線、`ReadOnlyConnection.close` を closers に)、`infrastructure/opensearch/responses.py`(docstring)
- tests 新規: `fakes/in_memory_readers.py`、`admin/conftest.py`・`factories.py`、`admin/derivation/test_*.py`(10)、`admin/services/test_*.py`(5)、`admin/routers/test_{jobs,opensearch,meta}.py`、`architecture/test_derivation_purity_rules.py`(R7)
- tests 変更: `admin/base/test_errors.py`((b)。B 出典の 2 文言を `==` で固定)、`common/http/test_body.py`((c))、`admin/test_app.py`・`test_main.py`(配線テスト)

## 判断・設計上の理由

1. `AdminDependencies` はサービスの束(`job_queries`・`cluster_overview`・`meta`)。組み立ては `build_admin_dependencies(settings, clock, runner, readers)`。`create_admin_router` は `job_queries=`・`cluster_overview=`・`meta=` のキーワード引数。`app.py` が個別に渡す形(0004 申し送り 1)を踏襲。`MetaService` は設定値を引数で受ける(`services` が `admin` 直下を import できないため。R4)
2. `stalled` の確認読み: ロックを 1 回の `mget` でまとめて読み、不一致のジョブだけ「ロック → ジョブ」の順に読み直す。読み直しでジョブが `running` でなければ `false`、ロックが一致するようになっていればそのロックで判定、それ以外は `true`。読み直しの読み取りが 1 つでも失敗したら `null`。読み直したジョブ記録を `refreshed_job` として行・EP-10 本体にそろえる
3. 再実行の判定のデータソース設定の読み取りは、C 5.3 の順 7〜10 でしか使わないため `failed` の `crawl` のときだけ読む(結果は同じ、読み取りが減るだけ)
4. `rerunnable=null` の `unavailable` 理由は原因の失敗と同じ。`stalled` の失敗時は `unavailable` に `stalled` と `lease_expires_at` を付ける(C 5.8)
5. `deletion` は `crawl` ジョブだけオブジェクト、`source_delete`・種別不明は `null`。実行待ちのジョブは削除結果を読まない。`fetched_at` は読み取りを試みたとき(失敗含む)に `now`、読んでいなければ `null`
6. services のテストは `@pytest.mark.anyio`(`anyio_backend` は asyncio 固定)。`InlineRunner` は duck typing で渡し `# type: ignore`
7. `InMemoryReaders` は P3 で使うメソッドのみ。`SearchIndexReader`・`CountsReader`・`latest_by_source`・`list_skipped`・`list_oversize` は P4
8. tags・operationId・エラースキーマは P7(プランどおり)

## 満たした C 11章の観点

5(導出: `lock_state` 10 行、`stalled` 確認読み、`rerunnable` 評価順、`units` 境界)/ 6(EP-09 の行ごと `stalled`、`mget` 全体失敗時の全 `running` 行、最上位 `unavailable` は常に `{}`、EP-10 の最上位 `unavailable`、読み取り失敗は 404 でなく 503、`malformed`)/ 7(ページング窓 10,000 ちょうどは 200、10,025/10,050/10,100 は 400 `range`。10,030 件でも `total` は 10,030、同順位は `job_id` 昇順)/ 16(検索は古い `running`、`mget` は終了済み・ロックなしで `stalled=false` かつ `status` も読み直した値)/ EP-12(切り詰め 1,000 件・状態の悪い順・正規化・補完)/ EP-10 の 404 / 12(`assert_secret_absent` を応答本文とログの両方に使用)

## 設計書との食い違い・申し送り(設計書は未変更)

1. **EP-12・EP-14 に `unavailable` を付けていない**: B 2.2 は「単一の応答(EP-02・10・12・13・14)は最上位 `unavailable`」と書くが、EP-12(7.1)・EP-14(8.2)の応答定義と例には `unavailable` がない(EP-12 は全体 503、EP-14 は設定だけ)。各 EP の定義と例に従った
2. **`failure_detail` は `failed` のときだけ**: B 5.2「`failed` 以外は `null`」と C 5.4「文字列ならそのまま」が食い違う。B に従った
3. **`cat.shards` の必須項目**: C 3.4 は「整数列の非数・空は `null`」だが、`shards[].shard`・`state`・`role` は B で非 null。`shard` 非数・`state`/`prirep` 空は `null` にせず形の異常(503、ログは固定の理由名のみ)。`indices[].document_count` は C どおり `null`
4. **改行(`%0A`)を含む `job_id`**: Starlette の `Mount` の正規表現(`.` が改行に一致しない)で外側が 404 `not_found` になり、B 2.12 の 400 `format` にならない。現状を `test_jobs.py` に記録。他の制御文字は 400 `format`
5. 未配線: `LockViewService` と `lock_state`・`settings_view`・`source_summary`・`units` のリクエスト側は導出表とテストまで(使う EP は P4 以降)。`SourceSettings`・`JobAccepted`・`ExistingJob` の DTO は未作成。`AdminReaders` に `SearchIndexReader`・`CountsReader` は未追加(P4)
6. `ErrorCode` の固定文 10 件の追従改訂は 0006 のまま

## 未対応事項・次にやること

- 次: P4(EP-01・02・11)。`search_index_reader` の `parse_uncounted_search` 切り替え(0007 据え置き)は P4 で `count_by_source` を扱うときに再検討
- 実機確認(P7 スモーク): クエリの意味(AAA-U-1〜3)、`cat.*` の実際の列、`relocating` の `node` 表記
- レビュー R-B は P4 完了後(比較基準 R-A 完了コミット `aa88b9b`)
