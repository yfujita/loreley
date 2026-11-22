# 0005 P1 再レビューと完了

日付: 2026-11-11 / 対象: 0004 の修正後の P1 / レビュー: test-reviewer、code-reviewer(再レビュー)/ 修正: code-implementer
比較基準: HEAD c065b9e(`apps/indexer` は未コミットの新規ファイル全体)

## 再レビュー結果

### code-reviewer(可。Critical/Important なし)
- 401/403 の全体異常化は arch 4.4(スキップ対象は文書固有の4xxだけ)と矛盾しない。分類の優先順位(error_type → ステータス)が保たれ、既存 reason(`cluster_block_exception` 等)は不変
- log_masking: 整形失敗時に元の msg/args を出さず `record.args=None` まで徹底。秘密値が漏れる新しい経路なし
- 見送り・後続送り(delete_by_query 専用タイムアウト=P4、opensearch ロガー固定=P5、設定値整合検証=見送り)は妥当
- Suggestion: 整形失敗の固定文言に原因が追えない → **対応済み**(ロガー名と例外クラス名を追加)
- Nitpick: `stack_info` と `extra` は伏せ対象外 → **対応済み**(docstring に明記。P5 のログ検査テストで確認)

### test-reviewer
- 前回 Important 2件(fake のスレッド安全性、キー指定)は実装として解消。ロックの入れ子・逆順取得・デッドロック経路なし。キー指定は仕様どおり
- **新規 Important**: `test_hook_runs_outside_the_internal_lock` がフックをロック内に戻しても失敗しない(Gate の5秒タイムアウトで通る)→ **対応済み**
- Suggestion: SlowReadDict の重複、並行性テストが replace/replace のみ、`inject` の times 検証と例外インスタンス再利用、R7 検査が `client.indices.*` を見ない、request shape の呼び出し規約依存の記載、classification のフォールバック枝 → すべて**対応済み**
- 見送り: `delete_by_query` へのキー付与(P4 で必要になった時点)、fake と実アダプタの契約一致テスト(U-31 に持ち越し)、`InMemoryStore` の並行 delete/replace テスト(create 相当がなく、指示外)

## 対応内容(code-implementer。メインが検証を再実行して確認)

- `tests/infrastructure/test_fake_utilities.py`: `enter("other")` を別スレッドで走らせ、`gate.release()` の前に `done.wait(1.0)` で完了を要求
- `tests/fakes/concurrency.py`(新規): 共通 `SlowReadDict` と `run_concurrently`。fake 内部辞書名(`_documents`、`_records`)への依存をここに集約
- `tests/fakes/behavior.py`: `inject` の `times` 検証(`None` または 1 以上、不正は ValueError)、例外は呼び出しごとに `copy.copy` した複製を送出
- 並行性テストを追加: create/create(`[Conflict, Written]`)、delete_if_unchanged/replace_if_unchanged(同じ版)
- `tests/architecture/test_write_rules.py`: R7 の AST 検査を `*client*` を含む属性チェーンに拡張、`WRITE_METHODS` に reindex・put_mapping・put_settings・alias/template 系を追加。動的呼び出し・別名への再代入・低水準 `transport.perform_request` は検出できない旨を docstring に明記
- `test_request_shape.py` に opensearch-py 呼び出し規約への依存を追記、`test_classification.py` に `mapper_parsing_exception` のフォールバックケース追加
- `src/loreley_indexer/common/log_masking.py`: 整形失敗の文言を `"<log message could not be formatted> (logger=NAME, error=ExcClass)"` に変更

## 検証結果(メインが再実行)

- `uv run pytest` → **450 passed**(3回連続で同数、約2秒)
- `uv run ruff check` → All checks passed
- `uv run ruff format --check` → 59 files already formatted
- ミューテーション確認(メイン): スクラッチパッドのコピーで `behavior.py` のフック実行を `with self._lock` 内へ移すと、`test_hook_runs_outside_the_internal_lock` が約1秒で失敗することを確認(リポジトリのファイルは変更していない)。実装担当も同じ確認と、`InMemorySearchIndex` のロックを no-op にすると並行テスト3件が失敗することを確認済み

## P1 の結論

P1 は完了。code-reviewer・test-reviewer ともに Critical/Important は解消済み。最後の修正(上記 Important 1件と Suggestion)は、再々レビューを行わず、メインがミューテーションと検証コマンドで確認した(修正がテストと log_masking の文言に限られるため)。

## 持ち越し・後続フェーズへ送る事項

- P2: タイムアウト再送で `op_type=create`/`if_seq_no` 付き PUT が409になりうるケースを、登録テストで「409→読み直しで成立」として確認する
- P4: `delete_by_query` 専用の長いタイムアウトと、timeout 再試行の抑止。`delete_by_query` にキーを付ける必要があれば fake に追加
- P5: opensearch ロガーを WARNING 以上に固定、ログ検査テストで本文・秘密のセンチネル文字列(`extra`・`stack_info` 含む)が出ないことを確認。`urlsplit` 自体の ValueError(不正IPv6括弧)の再確認。設定値どうしの整合検証の要否を検討
- U-31: 実機確認(painless の max 比較、`delete_by_query` 競合、`search_after`、存在しない文書への `if_seq_no` 付き操作、`retry_on_conflict`)。fake と実アダプタの契約一致テストもここに含める。fake の `Instant.parse` はオフセット付き表記を受理するなど実機より寛容な可能性がある
- R6・R7・R8 は部分検査のみ(インターフェース面の固定、書き込み呼び出し位置の AST 検査、409でクライアント呼び出しが1回)。完全な機械検査ではない
- コミット未実施

## 次のアクション

P2(documents + lifecycle の最小部分)を `code-implementer` に依頼する(0002 §6 P2)。依頼に含める申し送りは 0003 の「次のアクション」と上記。
