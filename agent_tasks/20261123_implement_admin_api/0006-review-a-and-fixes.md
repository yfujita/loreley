# 0006 レビュー R-A(P1〜P2)と指摘対応

日付: 2026-11-24

## レビュー結果

比較基準: 開始 SHA `cedcd56` → `2c29b7e`(P2 完了)。`code-reviewer`・`test-reviewer` を並列実施。

### code-reviewer(Critical 0 / Important 1 / Suggestion 3 / Nitpick 2)
- **Important**: R-3・R-7 のクエリに `track_total_hits` がなく、ジョブ記録が 10,000 件を超えると `relation: gte` となり `_parse_total` が恒常的に Failed(EP-01・02・10 に直結)
- Suggestion: mget の文書単位失敗ごとの WARNING(ログ洪水)/ `dependencies.py` の docstring と実装の食い違い / 窓などの定数二重定義と同名 `PageRequest`
- Nitpick: Content-Length が 4,300 桁超で `int()` が ValueError(500 化)/ `ErrorCode` に対し `_MESSAGES` が不足
- 指摘なし: R8(読み取り専用)、依存ルール・循環、設定検証と秘密、`BlockingRunner`、Reader の部分失敗、クエリ本文と窓境界、申し送りの妥当性(`create_admin_router()` 引数なし、`PageRequest` の `ValueError` 方針)

### test-reviewer(Critical 0 / Important 4 / Suggestion 7 / Nitpick 5)
- **I-1**: イベントループ非ブロックのテストが空振り(`ticks == 20` が常に真。`run` を同期化しても通る)
- **I-2**: 秘密値センチネルの非出力が未検証
- **I-3**: `test_main.py` の 1 テストが `restore_logging` なしでログのグローバル状態を汚染
- **I-4**: 本文上限テストに名前どおりの検証がない(`chunks_sent` を assert していない)
- Suggestion: R8 の検出強化(`READER_FILES` の glob・`WRITE_VERBS`)、偽物のダンダー名、本物クライアントとの transport スタブ照合、契約テストの `_source.includes`、入力値非出力の強化、窓定数の整合、concurrency 細部、tzdata の暗黙依存
- 判定: P1 のログテスト修正(`propagate=True` の monkeypatch)は妥当。自作ミューテーション約 25 件のうち有効なものはほぼ検出(未検出は I-1 のみ)

## 指摘対応(code-implementer。メインエージェントが検証を再実行)

対応した項目:
1. R-3・R-7 に `"track_total_hits": False` を追加。`responses.parse_uncounted_search` を新設し R-3・R-7 だけ切り替え(total ありの gte 応答でも Ok)。総件数を使う側(`parse_search`・`parse_counted_search`)は gte で Failed のまま。C 3.3 の R-3・R-7 の JSON 例は `track_total_hits` を明記しておらず、C 3.2 は総件数を使う問い合わせの規約なので矛盾なし
2. `failure.classify_failure`(ログなし)を分離。`parse_mget` は 1 回につき「失敗 N 件」の 1 行のみログ(ID・例外文なし)
3. `dependencies.py`・`create_admin_app` の docstring を実装に合わせ、`deps` 未使用が意図的と明記
4. `tests/admin/base/test_constants.py` で窓・ソース上限・existence 上限・ページサイズ上限の一致を検査。routers 側 `PageRequest` を `PageParams` に改名
5. `read_limited_body`: 先頭ゼロを除き 19 桁超の Content-Length は数値化せず上限超過として 400
6. `ErrorCode` 全メンバーの固定英語文を `errors.py` に追加し、網羅テストを追加(旧テスト `test_a_code_without_a_message_is_a_programming_error` は成り立たなくなったため置き換え)
7. I-1: 各 sleep の実測間隔の最大値 < 0.5 秒を assert。`run` を同期化すると最大間隔 20.0 秒で失敗することを確認し、元へ戻した
8. I-2: `tests/secret_assertions.py` の `assert_secret_absent` を新設。`test_main.py` に lifespan・未知パス 404 での非出力テスト、`test_secret_output.py` に実 `create_read_connection` の失敗時のログ非出力テストを追加(ロガーを DEBUG に緩めると失敗することを確認し、戻した)
9. I-3: `restore_logging` を付与(他に同様のテストなし)
10. I-4: 呼び出し回数を数える偽 `receive` で、chunked は超過後に追加 `receive` を呼ばないこと、`Content-Length` 超過は `receive` 0 回を検証
11. 偽クライアントのダンダー名は `AttributeError`
12. 本物の `OpenSearch` の `transport.perform_request` をスタブにして `ReadOnlyOpenSearch` の 7 メソッドの HTTP メソッド・パス・パラメーター・本文を検証(`test_readonly_client_transport.py`)
13. 契約テストに `dynamic: strict` 索引の `_source.includes/excludes` ⊆ マップ済み項目の検査
14. `*_reader.py` の glob 検査、`WRITE_VERBS` を全語判定にし `purge`・`erase`・`mark` を追加、負例を追加
15. timeout テストの種別を完全一致に強化

## 検証(メインエージェントが再実行、`apps/api`)

- `uv run pytest`: 1150 passed(修正前 1096)
- `uv run ruff check`: All checks passed / `uv run ruff format --check`: 120 files already formatted / `uv lock --check`: OK
- `tests/common/test_concurrency.py` を 3 回連続: すべて 18 passed(実装担当は 5 回連続)
- `common/concurrency.py` に差分なし(検出力確認の一時変更が残っていない)

## 判断・申し送り

- B の `ErrorCode` ごとの `message` は `config_invalid`・`lock_held` 以外に規定がない。他 10 件(`lock_in_use`・`source_deleting`・`maintenance_enabled`・`source_already_exists`・`job_not_cancellable`・`job_already_finished`・`crawler_error`・`crawler_unavailable`・`crawler_unreachable`・`crawler_response_lost`)は同じ書き方の固定文を実装側で補った。**設計書追従改訂の申し送り**(文言を固定したい場合は B への追記)
- `count_by_source_body`(R-9 の EP-01 行)は `track_total_hits: True` で `parse_search` を使うが `hits.total` は使っていない。今回の範囲外で変更せず

## 後続フェーズへ送ったもの(今回対応しない)

- `tzdata` の直接依存化(P7)/ S-4 入力値非出力の網羅(P3 以降のルーター追加時に `assert_secret_absent` を使い回す)/ S-6 concurrency 細部(`BlockingRunner()` 既定値の実使用、複数例外の「最初」)/ `InlineRunner.run_all` への `Abandoned` 注入(P6)/ `FakeBehavior` の挙動確認(P3)/ `health_probe` 実在検査(P6)

## 未対応事項・次にやること

- 修正差分(`2c29b7e` 以降)を同じレビュアーで再レビューし、Critical・Important が解消してから P3 へ
