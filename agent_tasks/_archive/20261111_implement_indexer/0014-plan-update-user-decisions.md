# 0014 プラン更新: ユーザー判断(2026-11-12)

日付: 2026-11-12 / 対象: 0002-work-plan.md(§3 案11・12、§4)/ 契機: 0009・0012・0013 でユーザー判断待ちにしていた3件

## ユーザー回答

1. **TTL が 0・負値の誤設定**(今回のクロールが見た文書まで削除対象になりうる件): 追加条件 `last_seen_at < min(cutoff, crawl_started_at)` を**入れない(設計書どおり)**
2. **メンテナンスフラグの不正値**(文書があるのに `enabled` が真偽値でない): **fail-closed に変える**(推奨案)
3. **要約の再走査の方針変更**(案12 → 指数バックオフの永続再走査): **承認する**(推奨案)

## プランへの反映

### 案12(要約の失敗・再試行・有効化後)の差し替え(0002 §3 項目12)
- 旧: LLM 失敗・書き戻し失敗は `summary_max_attempts` まで再試行し、直らなければ `pending` のまま残す。再走査は起動時と、書き戻し失敗後(間隔下限つきで1回)
- 新: LLM 失敗・書き戻し失敗は `summary_max_attempts` まで再試行し、直らなければ `pending` のまま残す(`failed` へは遷移させない)点は変わらない。**再走査は、起動時の最初の1回は即時、以後は「成果(走査間に書き戻し成功が1件以上)がない限り、間隔を `min × 2^n` で最長 `summary_rescan_max_interval_seconds`(既定 3600秒)まで伸ばしながら永続的に繰り返す。成功でリセット」**。`failed` への遷移が設計上未決(U-9・K54)の間の代替であり、メンテナンス解除後の再開が最悪で上限間隔遅れうることを README に記載する(P6)
- 承認の根拠: 0009・0012 の code-reviewer 評価(K54(3) の「無制限に自動で再試行しない」の趣旨を、時間方向のバックオフで実質的に満たす妥協)

### §4 仮値の表への追加
| 設定名 | 既定 | 上限 | 根拠 |
| --- | --- | --- | --- |
| `summary_rescan_max_interval_seconds` | 3600 | 86400(`summary_rescan_min_interval_seconds` 以上を検証) | 案12(更新)、K54(3)、0008 |
| `deletion_poll_backoff_max_seconds` | 300 | 3600(`deletion_poll_interval_seconds` 以上を検証) | arch 9.9、0012(削除ワーカーの連続失敗バックオフ上限) |
| `os_delete_by_query_timeout_seconds` | 600 | 3600 | arch 4.4・U-3、0005・0011(`delete_by_query` 専用タイムアウト) |
| `summary_input_max_chars` | 30,000 | 1,000,000 | K39、0007 判断17(要約入力の上限。先頭のみ要約。U-9 のモデル選定後に見直す) |

※ `deletion_poll_backoff_max_seconds`・`os_delete_by_query_timeout_seconds`・`summary_input_max_chars` は、実装時点でユーザー未承認のまま実装されていた(0007・0011・0012)。本記録ではプランの仮値表に反映するが、**承認は未取得**(完了報告時に確認する)

### 案11(メンテナンスフラグの確認)の追記(0002 §3 項目11)
- メンテナンスフラグは、`loreley-jobs` の ID `maintenance` の文書が存在し、`enabled` が真偽値の `False` と**明示されている場合のみ**「立っていない」。**文書が存在し `enabled` が `False` 以外(`"true"`・`1`・欠落・非 bool など)の場合は「立っている」とみなす**(fail-closed)。文書がなければ従来どおり「立っていない」。不正値のときは record_id と項目名のみを WARNING に出す(値は出さない。R9)
- 変更点は `infrastructure/opensearch/jobs.py` とそのテスト(P1 の `test_maintenance_flag_ignores_non_boolean_values` の更新)に隔離する。実機の形式は Crawler 設計の確定時に再確認する(P6 の申し送り)

### 見送り(ユーザー判断により実装しない)
- TTL の追加条件: 設計書 9.8 の式(`last_seen_at + TTL < 判定時刻`)と 9.13(9)(範囲検証なし)のとおりとする。**誤設定時のリスク(TTL が 0・負値・クロール時間より短い場合に、対象件数が `min_delete_count` 以下の小さいソースで、割合ルールを素通りして今回のクロールが見た文書も削除されうる)は受け入れた既知の制限**として、README(P6)の運用上の注意に記載する。テストは足さない(現状の挙動を固定するテストも、追加条件のテストも不要)

## 次のアクション

1. P5 の依頼の先頭項目に、メンテナンスフラグの fail-closed 化(`jobs.py`・テスト更新)と、0013 の残り Suggestion(テスト・ログ・docstring)を組み込む
2. P6 の README に、TTL 誤設定のリスク、要約の再開遅延、メンテナンスフラグ形式の再確認、判定時の `MalformedRecordError` が先頭を詰まらせる既知の制限(WARNING 監視)を記載する
