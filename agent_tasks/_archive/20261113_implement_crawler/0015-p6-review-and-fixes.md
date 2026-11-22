# 0015 P6 全体(6a+6b)のレビューと修正

日付: 2026-11-14 / 実施: code-reviewer・test-reviewer(各2回)、code-implementer(修正2回)/ 記録・再検証: メインエージェント
レビュー対象: P6 で追加・変更した `crawl/`・`jobs/records_facade.py`・`jobs/__init__.py` の公開と対応テスト(`apps/crawler/` は未コミット。比較基準 HEAD `061dc7b196f67a689e0d834eb676ce356d6cdb34`)

## 1. 1回目のレビュー結果(ともに「軽微な修正で可」、Critical なし)

### code-reviewer(Critical・Important なし。Suggestion 4、Nitpick 3)

総評: 削除の起点になる終了通知(`enumeration_completed`)の経路は、正常・例外・競合のどの経路を追っても安全側に倒れている。

**0014 §4-1 の結論(ロック喪失時も `failed` 通知を送る実装は Indexer 側に害がない。設計書どおりで変更不要)**。`apps/indexer`(参照のみ)の実コードで確認した根拠:
- 影響は自分の `crawl_id` の結果だけ: `crawl_runs/lifecycle/finish.py` の `_try_accept` は `crawl_id` の結果を1件読んで判定する。結果がなければ何も書かない(未知の `crawl_id`)、`source_id` が違えば409 `finish_source_mismatch`、すでに終端なら何も書かない(遅れた通知)、それ以外の `failed`・`cancelled` は `_record_failed` がその `crawl_id` の結果だけを `failed` にする。`wake` は呼ばず、世代(generation)も `last_seen_at` も触らない
- 他の Crawler のクロールを巻き込まない: ロックを引き継いだ別ジョブ B の開始通知は、`lifecycle/start.py` の `_supersede_unfinished_results` が `finish_received_at` のない running の旧結果(A)を `discarded(superseded)` にする。その後に A が `failed` を送っても A の結果は終端なので何も書かれず、B の結果・世代・削除判断には触れない。先行する削除結果(`preceding_results`)は `finish_received_at` のあるものだけなので、`failed` の結果は B の待ち行列に入らない
- `crawl_id` は一意(`jobs/records/job_ids.py`、衝突はジョブ記録の `create` で検出)
- 再送・内容違いの409: ダイジェスト(`finished_at` は含まない)が記録済みなら比較し、違えば409 `finish_content_mismatch`。Crawler は `enumeration_completed` の送信開始後には `failed`・`cancelled` を送らないのでこの409は起きない

| 指摘 | 対応 |
| --- | --- |
| Suggestion: 終了通知の送信前に `enumerated_count == 登録+skipped+oversize` の局所的な不変条件を確認する(削除のトリガなので安価な二重防御) | 採用。`RegistrationTally.registered_count` を足し、不一致なら `enumeration_completed` を送らず `CrawlFailure(INTERNAL_ERROR)`(固定文、値なし)で `failed`(`failed` 通知は送る) |
| Suggestion: 整理の判定が種別共通のため、前回スキップ・今回サイズ超過の `skip` 記録が残る(0013 §4-8) | 採用。`_should_delete_record(record_type, document_id)` で、`skip` の走査は「今回 `skipped` に載っていない」、`oversize` の走査は「今回 `oversize` に載っていない」、今回列挙されなかった文書は両種別とも削除。他ソース・失敗/取り消しされたクロール・`document_id` が読めない記録は消さない(不変) |
| Suggestion: テスト用入口 `run_until_finish_notice` が `_run_to_the_end` と手順を二重に持つ | 共通の `_run_until_finish_notice(run)` に統一。`ReadyToFinish`・`FailureRecorded`・`StageResult` は `crawl/__init__.py` から外した(テストは `crawl.executor` から import) |
| Suggestion: `finish_notice`(ID 一覧 SHA-256 64文字×最大約8,000〜10,000件)をジョブ記録に2回書く | P8 への申し送り(§5) |
| Nitpick: `finish` が False でも「finished」とログに出る/`interrupted_polling_result` が副作用を持つ/`StatusPoller.poll` が長い | 戻り値でログ文言を変える(すでに終端のときは warning)、`abort_on_cancel` に改名、`_FailureStreak` を切り出し |

### test-reviewer(Important 4、Suggestion 10、Nitpick 6。約135件の変異のうち実質的な生存は8件)

| 重要度 | 指摘 | 対応 |
| --- | --- | --- |
| Important I1(削除に関わる・最優先) | 終了通知の送信直前の所有確認(`Check.ALL`)が未検証(OWNERSHIP を外す変異が通る) | 固定保存(`send_started_at` は null)の直後に、所有喪失・メンテナンス・取り消しを起こすテスト。期待: `enumeration_completed` は送られず、`failed(lock_lost)`/`failed(maintenance)`/`cancelled` と通知 `["failed"]`/`["cancelled"]`。OWNERSHIP・MAINTENANCE・取り消しのそれぞれを外す変異が検出される |
| Important I2 | `force_delete` と `rewrite_mode` の取り違えを検出できない | 逆の組を含む3通りを parametrize、開始通知の引数と `settings_snapshot` の両方で確認 |
| Important I3 | last-seen・バッチ登録・終了通知の `crawl_id` が未検証 | 通常終了・`failed`・`cancelled` の3経路で全呼び出しの `crawl_id` が `job_id` と一致。fake も未開始の `crawl_id` を409にする(二重) |
| Important I4 | ID 一覧の警告閾値が合算でない実装を検出できない | skipped 1+oversize 2(閾値2で警告、閾値3でちょうどは出ない)など |
| Suggestion | `send_started_at` 記録直後・初回送信前の取り消しの境界(#30)、ポーリングで成功が入った後の404区分のリセット、バッチ原本バイト数がちょうど上限、`BaseException` の crawl レベル、Runner 結合の e2e、整理の最中の取り消し、メンテナンスがポーリング・リトライを止めない(仕様どおり固定)、開始通知の再送で時計を進める、`failed` 通知が固定済み・未送信の内容を置き換える | すべて対応 |
| Suggestion S4 | fake の忠実度: 実 Indexer の `AdmissionChecker` と同じ判定順で409(`crawl_not_started`・`crawl_source_mismatch`・`crawl_started_at_mismatch`・`crawl_finished`・`crawl_already_closed`)、`failed`/`cancelled` の通知では `finish_received_at` を付けない(`finish.py::_record_failed`) | `FakeIndexerClient`・`RecordingIndexerClient` を実 Indexer に合わせ、fake の自己テストを追加 |
| Suggestion S10 | 件数照合の独立した検証(fake に N_seen+E_missing) | **P9 の実機確認に回す**(Crawler 側は不変条件で二重防御) |
| Nitpick | `run_full`・`outcomes`・`finish_calls` の重複、リソース解放テストの parametrize、テスト名 | support.py に集約、5経路に parametrize、名前を実範囲に |

## 2. 2回目のレビュー(再レビュー)結果

- code-reviewer: **「指摘なし」**。A1 の不変条件は正常なクロールで誤って不一致にならない(`registered_count` は `document_id` ごとに1回だけ数え、再送・重複で二重計上せず、`extract_failed` も `ok` として1件、識別子エラーは `enumerated_count` にも含まれない)。A2 の整理は誤って消してはいけない記録を守りつつ 0013 §4-8 を解消。A3・ログ・改名・`_FailureStreak` で区分や本番経路は変わっていない
- test-reviewer: **「軽微な修正で可」**。Important 4件はすべて解消(Check.ALL の各要素を外す4変異、`force_delete`/`rewrite_mode` の3変異、`crawl_id` の5変異、閾値の3変異がいずれも検出)。変異38件中1件生存(S-new1)。誤検知がないことを、ランダムクロールのプローブ(300シード)で独自に確認。fake は実 Indexer の `AdmissionChecker` と判定順・エラーコードが一致
- 新規 Suggestion: S-new1(不変条件は「列挙数>合計」の向きしか検証していない)、**S-new2(不変条件の確認が整理の後ろにある=タリーが壊れていても、壊れたタリーをもとに記録を消した後に止まる。削除の安全性)**、S-new3(多様なクロールで恒等式が成り立つことを固定する性質テストがない)

## 3. 3回目の修正(再レビューは省略)

- S-new2: 件数の不変条件の確認を `CrawlRun.check_the_counts_add_up()` として公開し、`CrawlExecutor._run_until_finish_notice` で `finalize_registration` の直後・`purge_document_records` の前に呼ぶ。集計が壊れていれば整理も終了通知も行わず、`CrawlFailure(INTERNAL_ERROR)`→`failed`+`failed` 通知。`send_finish_notice` 側にも確認を残す(二重防御。`ReadyToFinish` の `run` を直接使って `send_finish_notice` を呼ぶテストで検出可能に)。テスト: 不一致のとき古い `skip` 記録・消えた文書の `oversize` 記録が残る、走査(`SCAN`)も一括削除(`DELETE_IDS`)も1回も呼ばれない
- S-new1: 合計が列挙数を超える向き(登録された文書をスキップにも載せる)も追加。`!=` を `>`/`<` に変える両変異が検出
- S-new3: `tests/crawl/test_properties.py`(seed 25件、約0.4秒、決定的)。結果の種類(成功・取得できない・一時失敗が続く・サイズ超過(取得時・Indexer)・拒否・1度だけ拒否・抽出失敗・重複・識別子エラー)、チャンクやバッチの大きさ、`last-seen` の分割をランダムにし、`enumerated_count`・恒等式・`skipped_document_ids`/`oversize_document_ids` の集合と重複なし・整理後の記録を確認
- Nitpick: `after_the_content_is_fixed`/`OnlyOnce` をクロージャのフラグ1つに。fake の自己テストに、判定の順(ソース不一致かつ終了済みなら `crawl_source_mismatch`、次に `crawl_started_at`、最後に終了済み)と `crawl_started_at` のミリ秒未満の差は拒否しないことを追加
- **再レビューを省略した理由**: 修正がレビュアーの提案どおりの小さな移動・テスト追加で、不変条件の確認を整理の前に移すだけであり、メインが検証を再実行して確認したため。変異確認7件はすべて検出(生存なし)

## 4. 検証結果(メインが再実行、`apps/crawler`)

```
$ uv run pytest -q           -> 2583 passed, 3 skipped in 15.87s(P6b 後 2516 → 2554 → 2583)
$ uv run ruff check          -> All checks passed!
$ uv run ruff format --check -> 222 files already formatted
$ uv lock --check            -> Resolved 39 packages
```

`git status` は `apps/crawler/` のみ。skip 3件は macOS 固有(0009 §4)。残骸ファイル・プロセスなし。

## 5. 設計書の改版依頼リスト(提案。P6 のレビュー修正分。0013 §9・0014 §5 に追加)

1. architecture 6.4 の (a)(b): 整理の判定は種別ごと。`skip` 記録は「今回スキップした文書」のものだけ、`oversize` 記録は「今回サイズ超過だった文書」のものだけ残す。それ以外(今回登録できた・別の種別の結果になった・列挙されなかった文書)の記録は消す。0013 §4-8 は解消
2. architecture 7.5・6.4: 件数の不変条件(`enumerated_count` = 登録+スキップ+サイズ超過)の確認は、登録結果の確定の直後・記録の整理の前に置く(壊れた集計をもとに記録を消さないため)。終了通知の送信前にも確認する(二重防御)。不一致なら整理も `enumeration_completed` も行わず `failed(internal_error)` にして `failed` 通知を送る

## 6. P7・P8 への申し送り

- P8: `finish_notice`(ID 一覧を含む)をジョブ記録に2回書く。**P8 の Admin API の一覧・取得の応答からは `finish_notice.content` の ID 一覧を除く**。`find_previous_completed_crawl` は現状の `list_records` が `_source` を絞れないため全項目を読む(最大10件で影響は小さい。`registration` への絞り込みは Repository の拡張が要るので見送り)
- P7(`source_delete`): `DocumentRecords.delete_all_of_source`(0013 §7)、`SourceStore.mark_deleting`/`delete`、`IndexerClient` のソース削除1〜3(`lock` つき)、確認点 `Check.OWNERSHIP | Check.MAINTENANCE`(取り消しは対象外)、`failed` の理由 `lock_lost`・`maintenance`・`store_unavailable`・`internal_error`、`JobContext.finish` の False は再判定しない、`changes` は JSON 型。`scheduler` 向けに `JobHistory` に「直近のクロールジョブの `queued_at`」を返す関数を足す(P7)

## 7. 持ち越し

- 実機でしか確認できないもの: 実 Indexer の Status 項目(`finish_received_at` の有無、`waiting_for` の出方)、終了通知の409の出方、実ポーリング間隔と30分の妥当性、スレッド・GIL 下のハートビート(0014 §7)
- **P9 の実機確認に回すもの**: 件数照合の独立検証(Indexer 側の N_seen+E_missing。S10)

## 8. 次のアクション

P7(`source_delete`・`scheduler`)を `code-implementer` に依頼する(0010 §5・0011 §6・0012 §6・0013 §7・本記録 §6 を含める)。完了後、P8(`api`・`config.py` 完成・`main.py`)→ P7+P8 のレビュー → P9。
