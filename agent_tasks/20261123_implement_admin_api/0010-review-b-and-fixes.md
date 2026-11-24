# 0010 レビュー R-B(P3・P4)と指摘対応

日付: 2026-11-24

## レビュー結果

比較基準 `aa88b9b..d681ae8`。`code-reviewer`・`test-reviewer` を並列実施。

### code-reviewer: 指摘なし(Critical 0 / Important 0 / Suggestion 4 / Nitpick 3)
- B の DTO・`unavailable` の帰属・導出(`lock_state` 10 行、`stalled`、`rerun`、`units`)・stalled の確認読み・ページング・EP-11・EP-12・依存ルール・R8・秘密値は指摘なし。申し送り 10 件(0008 の 6 件・0009 の 4 件)の判断も妥当
- Suggestion: (1) EP-09 のクエリ検証が複数の違反を一緒に返さない(EP-11 と流儀が違う)/ (2) `SourceSettings` の nullable 化が P5 の EP-03・04 の応答にも波及する / (3) `job_queries.get_job` の失敗集約が文字列キーと可変の辞書に依存 / (4) EP-12・14 に `unavailable` を付けない判断は妥当(B 2.2 の列挙を設計書側で直す)
- Nitpick: `_index_order` の三項演算、`NO_QUERY_NAMES`・`reject_unknown_query(frozenset())` の重複、`brief_fields` の型なし展開

### test-reviewer: Important 2(Critical 0 / Suggestion 6 / Nitpick 3)
- 49 件のミューテーションのうち 41 件検出。未検出の意味あるものは 3 点(I1・I2・S1)。逆順・乱数シャッフル実行でも 1936 passed(順序依存・flake なし)
- **I1**: stalled の確認読み「ロックが別ジョブ + 読み直しで終端」が未検証(`_judge_after_confirmation` (a) を狭めても全件通過)
- **I2**: EP-10 `get_job` の `refreshed_job` 反映(`job_queries.py:137-138`)が未実行・未検証(`if False:` にしても全件通過)
- Suggestion: S1(確認読み後の行の `finished_at` 等と EP-02 の検索 stale)/ S2(Protocol 整合テストの厳密化、`FakeBehavior` の未知操作名)/ S3(fake 自身が並べ替えを実装、EP-09 の同順位のページ跨ぎ)/ S4(R7 が相対 import を検査しない)/ S5(配線テストが既定の索引名)/ S6(ヘルパー重複)
- Nitpick: N1(`_cat_int` の巨大桁)/ N2(`test_the_detail_accepts_only_get` の for ループ)/ N3(成功パスのアクセスログ確認)

## 指摘対応(code-implementer。メインエージェントが検証を再実行)

- **I1**: `test_stalled_check.py` に別ジョブのロック + 終端のテスト、EP-09 にも同条件のテストを追加。`_judge_after_confirmation` (a) を `lock.value is None` に狭めると新テストだけが失敗することを確認(復元済み)
- **I2**: `test_job_queries.py` に、確認読みの途中でジョブが終わる競合のテスト(`on_nth_call` で 2 回目の `jobs.get_locks` の中でジョブ更新とロック削除)を追加。`if outcome.refreshed_job is not None:` を `if False:` にすると失敗することを確認(復元済み)。既存の「finished after the snapshot」テストは実態に合わせて改名
- **S1**: EP-01 の確認読み後の行を `started_at`・`finished_at`・`job_id`・`status`・`trigger`・`queued_at` まで assert。EP-02 の検索 stale → 終了のテストを追加。`_judge_stalled` の `job_fields` を `('status',)` にすると 3 件失敗(復元済み)
- **S2**: Protocol 整合テストを書き直し(`ports` の Protocol 自動列挙、`iscoroutinefunction`、パラメータの名前・種別・デフォルト、`OPERATIONS` の過不足なし)。`FakeBehavior(known_operations=...)` で未知の操作名を `ValueError` に(未指定は従来どおり任意名。OpenSearch client の fake と共有のため)
- **S3(部分)**: EP-09 に 60 件・同順位がページ境界を跨ぐテストを追加。`in_memory_readers.py` の docstring に「fake が並べ替えを実装しており services/routers のテストは素通し確認。実クエリの sort は P2 の `test_queries.py` と P7 スモーク」と明記
- **S4**: `dependency_rules.absolute_base_of_from_import` を公開し、R7 の検査に相対 import を取り込み。負例 4 件・正例 3 件を追加
- **S5**: 配線テスト 3 件を非既定の索引名(`configured-sources` 等)で実施
- **S6**: `at`・`seed_job`・`errors_of`・`SENTINEL`・`on_nth_call` を `tests/admin/factories.py` に、`SEARCH_UNAVAILABLE`・`SEARCH_TIMEOUT` を `in_memory_readers.py` に集約
- **N1**: `test_cluster_view.py:98` に既に巨大桁のケースがあり追加不要。`except ValueError` を `KeyError` に変えると失敗することを確認(復元済み)
- **N2**: `parametrize("method", ["post","put","delete"])` に(P5 でメソッドを外す旨のコメント付き)
- **code Nitpick**: `_index_order` を `_STATUS_RANK.get(index.status or "", _OTHER_STATUS_RANK)` に、`request_input.reject_any_query` を追加して 4 ルーターの重複を整理(挙動不変)

## 検証(メインエージェントが再実行、`apps/api`)

- `uv run pytest`: 1956 passed(修正前 1936)
- `uv run ruff check`: All checks passed / `uv run ruff format --check`: 183 files already formatted / `uv lock --check`: OK
- `src` の差分は Nitpick 対応の 6 ファイル(計 14 行)のみ。`services/`・`infrastructure/` に差分なし。検出力確認の一時変更が残っていないこと(`lock.value is None`・`if False` の grep)を確認

## 対応しなかった項目と理由

- EP-09 の複数違反の集約(code Suggestion 1): B 2.12 の「違反はすべて返す」は本文の項目が対象で、現状は許容範囲。EP-09 のクエリ違反は依存関係ごとに最初の 1 群のみ返す。**申し送り**として記録
- `SourceSettings` の nullable 分離(code Suggestion 2): P5 の EP-03・04 実装時に判断(厳格な型と EP-02 用の nullable 版に分けるか)
- `job_queries.get_job` の失敗集約の整理(code Suggestion 3)、`brief_fields` の型付け(code Nitpick): 挙動は正しく、好みの範囲。P7 以降に余裕があれば
- EP-12・14 の `unavailable`(code Suggestion 4): 現状維持。設計書追従改訂に「B 2.2 の単一応答の列挙から EP-12・14 を外す」を申し送る
- test N3(成功パスのアクセスログ確認): P7 の手動スモークで確認

## 設計書追従改訂の申し送りの追加

- B 2.2 の単一応答の列挙から EP-12・14 を外す(0008 申し送り 1 に追記)
- EP-09 のクエリ違反は依存関係ごとに最初の 1 群のみ返す(B 2.12 の「違反はすべて返す」との差。必要なら B に明記)

## 未対応事項・次にやること

- `test-reviewer` による再レビュー(Important I1・I2 の解消確認)。`code-reviewer` は Important なしのため再レビュー不要(src は Nitpick の 14 行のみ)
- 解消後、P5(書き込み系 EP-03〜08・Crawler 中継)。P5 の最初に Crawler の実 API と B 9.2 を突き合わせる。`SourceSettings` の共用の扱いを判断する
