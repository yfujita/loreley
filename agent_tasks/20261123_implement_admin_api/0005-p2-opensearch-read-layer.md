# 0005 P2: OpenSearch 読み取り層

日付: 2026-11-24

## 実施内容

`code-implementer` が P2 を実装。メインエージェントが検証を再実行して確認した。

## 検証(メインエージェントが再実行、`apps/api`)

- `uv run pytest`: 1096 passed(P1 時点 751)
- `uv run ruff check`: All checks passed
- `uv run ruff format --check`: 116 files already formatted
- `uv lock --check`: OK
- 実装担当のミューテーション確認: ラッパーに `indices.get` と `**kwargs` を足すと R8 テストが 3 件失敗/契約テストはスキーマの `queued_at` を `keyword` にすると検出(いずれも復元済み)

## 変更ファイル(`apps/api/` 配下)

- `src/loreley_api/infrastructure/opensearch/`: 新規 `ports.py`・`readonly_client.py`(許可リスト 7 メソッド)・`queries.py`(R-1〜R-11)・`failure.py`・`responses.py`・`reading.py`・`connection.py`・Reader 6 種(`sources_reader`・`jobs_reader`・`deletions_reader`・`search_index_reader`・`counts_reader`・`cluster_reader`)。変更 `__init__.py`
- `tests/fakes/fake_opensearch_client.py`
- `tests/infrastructure/opensearch/`(queries・readonly_client・fake・failure・responses・connection・各 Reader のテスト)
- `tests/contract/test_schema_contract.py`
- `tests/architecture/test_read_only_rules.py`(R8 (a)〜(c) の実ソース検査+合成ソース自己テスト)
- `tests/common/test_logging_setup.py`(P1 のテスト 1 か所修正。下記判断 12)

## 判断・設計上の理由

1. 偽物の失敗(`ForbiddenOpenSearchCall`・`UnscriptedOpenSearchCall`)は `BaseException` の子。Reader は `Exception` を `Failed` にするため、`Exception` の子だと許可リスト外呼び出しが握り潰される
2. `mget` 系の返り値は ID キーの `dict[str, Result[StoredRecord | None]]`。`get_locks` のキーは `source_id`。`mget` 全体の失敗は全 ID が同じ `Failed`(C 5.8 の帰属表を満たす)
3. `connection.py` は生クライアントではなく `ReadOnlyConnection(client, close)` を返す。`create_probe_connection` は P6 用に先置き(`health_probe.py` は未作成)
4. R8 (a) は名前に `client` を含む属性チェーンの呼び出しを対象(Indexer の流儀)。Reader はラッパーを `self._readonly` で持つ。限界: client 名の規約に依存
5. `PageRequest` は窓 10,000・上限 100・page≥1 違反で `ValueError`(呼び出し側の誤りは `Failed` にしない)。`MAX_RESULT_WINDOW` 等は `ports.py`。P3 で `admin.base.constants` に同値を持つ
6. `CountsReader.count_for_source(source_id, targets)`。対象は `document_count`・`skipped`・`oversize`・`extract_failed`・`summary_pending`
7. `SourcesReader.get(source_id, fields)`: `None`=全項目、空=存在確認のみ(`_source: false`)
8. `ClusterReader` の `Failed.target` は `store`(EP-12 は失敗を全体 503 にするだけ)
9. ログは固定の操作名・分類・例外クラス名・整数ステータスのみ(400 のときだけ `error.type`)。`str(例外)`・ID は出さない
10. R-1: `hits.total.value > 10,000` は `Failed`(`ResultLimitExceededError`)
11. `hits.total.relation` が `eq` 以外は形の異常
12. P1 のログテスト修正: opensearch-py は import 時に `opensearchpy.trace` の `propagate` を False にする。`config.py` が `infrastructure.opensearch` を import するため常に影響し、`restricted_logger` の正例が落ちた。テスト側で `monkeypatch` により `propagate=True` に揃えた(`configure_logging` の挙動は不変)

## 満たした C 11章の観点

6(OpenSearch 層: `docs[i].error`・`found` 非 bool・`_shards.failed`・`timed_out` 等。ロックを `none`、ジョブを 404 と読み違えない)/ 7(クエリ本文の `from`・`size`・`track_total_hits`・並べ替え+ID、窓境界)/ 8((a)(b)。(c) の Crawler 側は P5)/ 9(契約テスト)/ 12(部分: ログに理由文・ID なし)/ 10 の OpenSearch 例外分類(`health_probe` は P6)/ 16 の `mget` 前提は P3 の `InMemoryReaders` に残す

## 設計書との食い違い(申し送り。設計書は未変更)

1. D 4.8 `connection.py`: 生クライアントでなく許可リストラッパー付き `ReadOnlyConnection` を返す(D の意図の具体化)
2. D 4.8 `CountsReader.tab_counts` → `count_for_source`(`document_count` も扱う)
3. D 3章の表にない `responses.py`・`reading.py` を追加(AAM-P-25 の範囲内)
4. D の「`list_*` は窓を超えない」は Reader 内でなく `PageRequest` 生成時の `ValueError` で保証
5. C 3.3 R-3 の `terms` 集計は `size=len(source_ids)`。ソース ID 重複時は重複除外後の個数を使う

## 未対応事項・次にやること

- `main.py` は Reader を未配線。`AdminDependencies` への配線は P3・P4(クライアント close は `ReadOnlyConnection.close` を `closers` に足す)
- `health_probe.py`(P6)、Crawler 側 R8 (d)・(e)(P5・P6)は未着手
- クエリの意味(フィルタ・集計・並べ替え)の実機確認は P7 スモーク(AAA-U-1〜3)
- 次: レビュー R-A(`code-reviewer`+`test-reviewer` 並列)。重点: R8 の検出方法の限界、`BaseException` 偽物の設計、`PageRequest` の `ValueError` 方針、P1 ログテスト修正の妥当性
