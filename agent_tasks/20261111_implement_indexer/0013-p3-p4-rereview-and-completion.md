# 0013 P3+P4 再レビューと完了

日付: 2026-11-12 / 対象: 0012 の修正後の P3+P4 / レビュー: code-reviewer、test-reviewer(再レビュー)
比較基準: HEAD c065b9e(`apps/indexer` は未コミットの新規ファイル全体)

## 再レビュー結果

### code-reviewer(可。Critical/Important なし)
- 前回 A1〜A7 は**すべて解消**。修正で「削除の安全性が退行する経路」は読み取れなかった(判定順・T>D ガード・条件付き削除・TTL 再確認・`source_id` 照合は不変。A2/A6/D-93 の変更は削除対象を増やす方向に働かない)
- A1: n の数え方(走査失敗・処理失敗のどちらも数え、例外なく終わった `run_once` でリセット)、`min(poll×2^n, 上限)` でオーバーフローなし、wake で即再試行し連続失敗数は保つ、`stop()` が wake も立てるので300秒待ちも即中断、WARNING は 1・2・4・8… 回目のみで R9 に適合。(b)(c) の見送りは妥当(全体障害で `failed` にするとその削除機会を恒久的に失う、(c) は全体障害では効果がなく並行度は U-14 未決)
- A6: 後続の削除が先行の未完了削除と並行して走る経路はない(ワーカーは1スレッドで、実行する記録は直前に `from_body` を通ったものだけ)。後続 B の削除対象は B 自身の複写値・件数照合・T>D・割合ルール・文書ごとの TTL 再確認と `source_id` 照合で決まり、先行 A の記録内容に依存しない。判定時の欠落は `MalformedRecordError` を送出して削除しない(fail-closed)のまま
- A2/D-93 と K43 は矛盾しない(K43 は `running` 中の表示の話、D-93 は終端状態の事実の記録)
- opensearch-py の `Transport` を実読して `retry_on_status=()` が有効なこと、`ConnectionTimeout` は `retry_on_timeout` で判定されることを確認
- Suggestion S1: 不正記録を `_list` が走査のたびに WARNING で出し続けるため、同じ record_id の行が約2秒ごとに永続的に出る(A1 のログ抑制の趣旨と逆。`DeletionResults` に「ログ済み record_id」の set を持たせて1回だけ WARNING にする案)
- Suggestion S2: 判定時の `MalformedRecordError`(再試行しても直らない異常)が先頭にあると全ソースが恒久的に止まる。fail-closed は正しく 9.9 の受容事項の範囲。発生は外部改変かバグのときだけ。コード変更不要。「再試行不能な異常は先頭を詰まらせる」と記録し、`deletion processing failed ... MalformedRecordError` の WARNING 監視を P5/運用へ申し送る(ERROR にして抑制しない案もある)
- Nitpick: `connection.py` の docstring が不正確(送信後のコネクションリセットも `ConnectionError` として再送される。`delete_by_query` は `conflicts=proceed` で再実行しても安全)/ 復旧時の INFO ログが無い
- ユーザー判断待ち事項への意見: **TTL 0・負値の追加条件(`last_seen_at < min(cutoff, record.crawl_started_at)`)は採用を推奨**(削除対象を狭めるだけ。判定の cutoff と `_is_still_deletable` の両方に必要。`n_seen` が既に「このクロールが見た文書」と同じ定義。TTL がクロール時間より短い場合に、クロール中に見た文書が削除される問題も防げる。採用なら 9.8 の cutoff の式と D-xx のテストの更新が必要。代替の `ttl <= 0` を 400 にする案は 9.13(9) と直接衝突する)。**メンテナンスフラグの不正値は fail-closed を推奨**(文書が存在し `enabled` が `False` と明示されたとき以外は「立っている」とみなし、record_id・項目名だけを WARNING。文書がなければ従来どおり「立っていない」。書式は Crawler 設計の確定時に再確認)

### test-reviewer(Critical/Important なし。信頼度「十分」)
- 前回 Important I1・I2・I3、S1〜S4・S6 は**すべて解消**、S5・N1 の見送りは妥当、S7 は概ね良好
- 約100件のミューテーションを自前で実施(スクラッチ上。リポジトリは未変更)。他ソース混入・スキップ除外・TTL 再確認・境界・フラグ/ロック障害の握りつぶし・先行待ち・件数照合・T>D・409・排他・バックオフ・D-93 などは検出
- Suggestion S1: 判定・再確認の時刻が `clock.now()` であることが固定されていない(基準を `crawl_started_at` に変えるミューテーションが生存。安全側にしか倒れないが TTL 期限の定義の取り違えを検出できない。`SEEN_AT - 2.5日` の文書を足す案)
- Suggestion S2: 不正記録の先行結果が先行扱いされなくなる挙動(0012 の未承認事項5)が、同一ソースでは固定されていない(ユーザーの採否が決まってから)
- Suggestion S3: `create_deletion_manager` の本番配線が未検証(`poll_interval_seconds`・`poll_backoff_max_seconds` の渡し間違い、既定 `sleep` が `stop_event.wait` でなく `time.sleep` になる変更が生存)
- Suggestion S4: 409 で読み直した進捗書き込みが「書かれたか」まで見ていない(`ResultWriter.advance` が読み直し後に更新を適用しない変更が生存)
- Nitpick: `DeletionConfig.poll_backoff_max_seconds` 検証が未テスト(N1)/ `deletion_started_at` の保持が未固定(N2)/ `OTHER_SOURCE` の定義が3か所(N3)/ `test_stop_ends_the_thread...` が `_thread` を直接読む等(N4)
- ユーザー判断待ち事項との関係: メンテナンスフラグが非 bool のとき「立っていない」とする現状は `test_maintenance_flag_ignores_non_boolean_values` で固定されている(fail-closed に決めたらこのテストの更新が必要)。TTL 0・負値の挙動を確認するテストは現状ない(巨大値の丸めのみ)。判断前に現状を固定するテストは足さなくてよい

## 判断

- P3+P4 は完了。Important はすべて解消済み
- 残りの Suggestion(code-reviewer S1・N1・N2、test-reviewer S1・S3・S4・N1〜N4)は、テスト・ログ・docstring のみで安全性に影響しないため、**P5 の実装依頼の先頭項目として組み込む**(再レビューの往復を増やさないため)
- code-reviewer S2(判定時の `MalformedRecordError` が先頭を詰まらせる)は**既知の制限**として記録し、運用での WARNING 監視を README(P6)に記載する
- test-reviewer S2(同一ソースで不正記録が先行・正常記録が後続の挙動)と、TTL 0・負値のテストは、**ユーザー判断後に追加する**

## 検証結果(メインが再実行して確認、0012 時点)

- `uv run pytest` → 1328 passed(3回連続)、`ruff check` 全通過、`ruff format --check` 160 files already formatted

## ユーザー判断待ち(STATUS.md に記録済み)

1. TTL 0・負値の追加条件(`last_seen_at < min(cutoff, crawl_started_at)`)を判定と TTL 再確認に入れるか(code-reviewer は採用推奨)
2. メンテナンスフラグの不正値の fail-closed 化(code-reviewer は推奨)
3. 要約の再走査の方針変更(案12 → 最長1時間間隔の永続再走査。0009)
4. 0007・0008・0010・0011・0012 のユーザー未承認の追加・判断(P5 以降の実装に影響しないもの)

## 次のアクション

1. 上記 1〜3 についてユーザーに確認する(1・2 は削除の挙動と P4 のテストに影響するため、P5 の前に確認する)
2. 確認結果を反映して P5(api・main・起動順)を `code-implementer` に依頼する(先頭に上記の残り Suggestion を組み込む。申し送りは 0007・0008・0010・0011・0012・0013)
