# 0012 P3+P4 レビューと指摘対応

日付: 2026-11-12 / 対象: 0010(P3)・0011(P4)/ レビュー: code-reviewer、test-reviewer / 修正: code-implementer
比較基準: HEAD c065b9e(`apps/indexer` は未コミットの新規ファイル全体)

## レビュー結果

### code-reviewer(修正後可。Critical なし、Important 1件)
- **削除の安全性を最重点で確認した結果、「削除されてはならない文書が消える」経路は読み取れなかった**。判定順(先行待ち→メンテナンス→ID 上限→refresh→件数照合→T=0→T>D→割合・最小件数)は arch 9.7 と一致、強制削除が迂回するのは割合・最小件数だけ。ID 一覧の異常(上限超過・欠落・重複)、cutoff の向きと境界(切り捨てで削除が少ない側に倒れる)、条件付き削除と409、ソース削除2(`source_id` 条件・再実行前のロック再確認・`_count` 確認)・3(別ソースを消さない)、`SourceBatchExclusion`(デッドロック・飢餓なし)、wake の取りこぼしなし、R5・R6・R8・R9 を確認済み
- **Important A1**: 処理の例外で結果が `running` のまま、バックオフなしで2秒ごとに全体(refresh・複数 count・最大200,000件の ID 取り込み)を再実行し続ける(fail-closed なので誤削除には至らないが、クラスタ負荷とログ洪水。先頭の結果が詰まると全ソースが止まる)
- Suggestion: 再実行で `deleted_count`・判定数値が上書きされる(A2)/ refresh のシャード部分失敗を見ていない(A3)/ 文書ごとの再確認で本文ごと取得している(A4)/ 終端遷移の prune 失敗が遷移の失敗として伝播(A5)/ 記録1件の形式不正で list 系が全体失敗し起動時整理も落ちて再起動ループになりうる(A6)/ **TTL が 0・負値の誤設定で、今回のクロールが見た文書も削除対象になりうる(設計判断。ユーザー判断が必要)**/ `crawl_id`・`source_id` に長さ上限がない
- Nitpick: 専用クライアントの `retry_on_status`、未使用 `logger`、既定値600の二重定義、列挙値の過剰、など
- 0010・0011 の未承認の判断の評価: TTL 再確認の source_id 照合、ソース削除2の再実行ごとのロック再確認、`SourceBatchExclusion`、専用 `delete_by_query` クライアント、`discard_max_attempts`=ラウンド数、`LockInfo` の common 移動、`os_delete_by_query_timeout_seconds`、P3 の書き込み順(世代→superseded→結果作成)、受理の409超過を `UnavailableError("write_conflict")` にすること、ID 一覧件数・フラグの常時記録、`failed`/`cancelled` はダイジェストのみ保存、空文字拒否、`finished_at` 非保存 = いずれも妥当(採用推奨)。限界1(判定フェーズの全体異常を上限なしで再実行)は fail-closed で許容だが実行フェーズにも及ぶため A1 の対象、限界2(先頭の結果が壊れると待ち行列が止まる)は先頭に限らない(未完了のどれか1件)ため評価を引き上げ A6 の対象、限界3(`_count` が古いまま0)は同期 refresh なら発生しにくく残るのは部分シャード失敗だけで A3 で実質解消

### test-reviewer(概ね十分。Critical なし、Important 3件)
- 信頼度は高めだが削除の負例に抜けが数点。74件のミューテーションで62件検出・8件生存(実質的な抜けは5件)
- **Important I1**: 他ソースの文書が分母 D と `N_seen` に混ざる退行が判定テストで検出されない(非強制モードで削除が拡大する方向)
- **Important I2**: 壊れた待機中レコード(`skipped_document_ids`・`oversize_document_ids`・`enumerated_count` の欠落)に対する「削除しない」ガードが無テスト
- **Important I3**: メンテナンスフラグ・ロック文書が読めない(OpenSearch 障害)ときに削除しないことが未検証
- Suggestion: T>D の境界(S1)、終端遷移の409上限超過(S2)、`delete_source_documents` のバッチ排他(S3)、arch 対応表と実テストのずれ(D-10・D-93)と D-4・D-27 の欠落(S4)、呼び出し順に結合したフック(S5)、ID 上限超過の `forced` parametrize(S6)、重複(S7)
- 0010・0011 の対応表はほぼ一致(不一致は D-10 と D-93)

## 指摘対応(code-implementer。メインが検証を再実行して確認)

検証: `uv run pytest` → **1328 passed**(P4 後の 1274 から +54。3回連続で同数、約8.5秒)。`ruff check` 全通過、`ruff format --check` 160 files already formatted。`apps/indexer` と `agent_tasks` 以外の変更なし。実装担当のミューテーション確認は31件すべてで該当テストが失敗(生存0)。

### 実装
- **A1(Important。(a) のみ対応)**: ワーカーが連続失敗数に応じて待ちを `min(poll×2^n, 上限)` に延ばす。走査失敗・処理失敗のどちらも数え、例外なく終わった `run_once`(空の待ち行列・WAITING・FINISHED を含む)でリセット。走査が成功しても処理が失敗していればリセットしない。起床通知(wake)では待たずに再試行し連続失敗数は保つ。ログは連続失敗の 1・2・4・8… 回目だけ WARNING(他は DEBUG)で、内容は crawl_id・例外クラス名・連続失敗数のみ(R9)。ジッタは入れていない(ワーカーは1本で、ジッタで通常間隔を下回りうるため。`wait` は注入可能)。**(b)(c)(連続失敗で `failed` にする・先頭が失敗したら次のソースへ進む)は arch 9.9 の直列の意味を変えるため見送り**
- **A2**: 実行は記録済みの `deleted_count` を起点にし、`progress_update` は記録済みの値より減らさない(「再実行で対象0件になり `deleted(0)` で上書き」する経路も塞ぐ。指摘にない追加)
- **A3**: `indices.refresh` 応答の `_shards.failed > 0` なら `OpenSearchUnavailableError("refresh_incomplete")`(検索インデックス・Store の両方。`_shards` が無い応答は従来どおり成功扱い)
- **A4**: `SearchIndexRepository.fetch_for_deletion`(`_source_includes=["source_id","last_seen_at"]`)を追加し、executor はそれを使う。`advance` の毎バッチ全文書書き直しは見送り
- **A5**: prune の `UnavailableError` はベストエフォートで握り、例外クラス名のみ WARNING。想定外応答は伝播
- **A6**: 3つの list(`list_unfinished_received`・`list_running_without_finish`・`list_non_terminal`)は不正記録を record_id だけログに出して除外し、他の記録の処理を続ける。**待機中レコードの判定時の欠落は従来どおり `MalformedRecordError` を送出して削除しない(フェイルクローズ)**。ID 指定の `fetch_result` も従来どおり送出
- **A7**: 専用クライアントに `retry_on_status=()`(通常クライアントは (502,503,504) のまま)、未使用 `logger` 削除、既定値600の一本化、列挙値の整理(bool 戻り値、挙動不変)。`DeleteByQueryResult.failure_count`・`version_conflicts` は本体未使用(変更なし)

### テスト
- **I1**: 他ソースの文書が D・`N_seen` に混ざらない(`other_source_expired=100` でも `SKIPPED_BY_RATIO`、D=10、書き込みなし / 他ソース文書を `SEEN_AT` で置いて `DELETED`、`n_seen==seen`)
- **I2**: 3ケース(skipped=None・oversize=None・enumerated_count=None)で `MalformedRecordError`、結果は `RUNNING` のまま、検索インデックスの読み書きなし、`run_once()` は False、ログに値が出ない
- **I3**: メンテナンスフラグの読み取り失敗を判定前・初回バッチ前・2バッチ目前で注入(例外が伝播し結果は `RUNNING`、削除は確認できたバッチ分だけ)、`lock-<source>` の読み取り障害で `delete_source_documents`・`delete_source_records` が例外になり `DELETE_BY_QUERY` なし・記録・文書不変
- **S1**: T>D の境界(依頼の「T=D+1 は通る」は実コード `len(targets) > denominator` と合わないため、実コードの境界 T=D は通る、T=D+1 は止まる で検証)。**S2**: 終端書き込みの409上限超過(実行側・判定側)。**S3**: `delete_source_documents` のバッチ排他。**S6**: ID 上限超過を `forced` で parametrize。**S7**: `remaining`・`process`・`received_at`・`Background` などを `scenario.py`・`tests/fakes/concurrency.py` に集約。**N2〜N4**: スレッド判定、TTL テストの名前・件数、`started_at` を変えたケース
- **S4(arch 対応表の訂正)**: D-10 の本旨のテストを追加(T=4、D=11 で `skipped_by_ratio`。閾値0.4では同じ構成が `DELETED`。T にスキップ文書を含める/D から除く誤りで反転)。D-93 のラベルを実態に合わせた(`test_after_a_restart_neither_of_two_waiting_deletions_is_resumed`。A が実行中の構成は `test_restart.py` の executing パラメータで `deleted_count=4` を維持)。D-4・D-27 のテストを追加
- **D-93 の `deleted_count`**: 設計書(`indexer-architecture-v0.9.md` の D-93 行)に「B による文書の削除は 0 件。`deleted_count=0`」とあるため、コードとテストを None から 0 に修正(`restart.py`。未記録なら 0 を付け、記録済みの値は減らさない)。K43(未記録の進捗を推測して表示しない)との緊張関係があるが、K43 は表示の話、D-93 は終端状態の事実の記録と読んだ

## ユーザー未承認の新設定・仮名・設計判断(追加分)

1. 新設定 `deletion_poll_backoff_max_seconds`(既定300、le 3600、`deletion_poll_interval_seconds` 以上を検証。`DeletionConfig.poll_backoff_max_seconds`)。A1 のバックオフの挙動(倍々、リセット条件、ログ抑制は2のべき乗回目、wake では待たず再試行)もあわせて承認事項
2. `SearchIndexRepository.fetch_for_deletion` の追加(公開インターフェース変更)、`create_opensearch_client` の `retry_on_timeout` 引数の廃止(P4 で入れたばかりで他の利用なし)
3. `progress_update` が `deleted_count` を減らさない変更(A2 の延長)
4. 再起動時の整理で `deleted_count` が未記録なら 0 を付ける変更(D-93 準拠)
5. A6 の副作用: `preceding_results` は `list_unfinished_received` を使うため、不正記録の先行結果は先行扱いされなくなり、後続の削除は自分の記録だけで判定を進める。削除対象は TTL 再確認と `source_id` 照合で守られるので削除量は増えないが、不正記録は終端にならず `running` のまま残る(ログのみ)

## ユーザー判断待ち事項(実装していない。STATUS.md に記録)

- **TTL が 0・負値の誤設定**: 今回のクロールが見た文書も削除対象になりうる。設計書の式(`last_seen_at + TTL < 判定時刻`)と範囲検証なしの確定事項(9.13(9))からの逸脱になるため判断が必要。追加条件 `last_seen_at < min(cutoff, record.crawl_started_at)` を判定と TTL 再確認の両方に入れるかどうか。入れない場合、対象件数が `min_delete_count` 以下の小さいソースでは割合ルールを素通りして見たばかりの全文書が消えうる(誤設定の場合に限る)
- **メンテナンスフラグの不正値**(非 bool の `"enabled"`)を「立っていない」(削除続行=fail-open)とする P1 の判断。削除の安全性の観点では fail-closed(不正なら立っているとみなす)が保守的だが、フラグの実形式は Crawler 設計が未確定の仮定義のため、現状維持としている

## P5 への申し送り(追加)

- `crawl_id`・`source_id` の長さ上限(`_id` 512バイト)は api 層で 400 にする
- `create_deletion_manager` に追加の引数はなく、`settings.deletion_config()` が新設定を詰める
- `refresh_incomplete` は `OpenSearchUnavailableError` のため api 層では 503(retryable)
- 通常クライアントと `delete_by_query` 専用クライアントの2つを作る(0011)。`create_opensearch_client` のシグネチャが変わった(`retry_on_timeout` 引数なし)

## 見送り・持ち越し

- A1(b)(c)、A4 の `advance` の毎バッチ全文書書き直し、S5(呼び出し順に結合したフック)、N1(`SourceBatchExclusion` の待機状態を private でしか観測できず、テスト専用 API を本体に足すより見送りが妥当)
- docs・README への新設定(`deletion_poll_backoff_max_seconds`、`os_delete_by_query_timeout_seconds` など)の反映は P6
- U-31(実機): refresh のシャード失敗の応答形、`_source_includes` の挙動、`retry_on_status` の実効果、ほか従来の項目
- 起動時整理のループは、不正記録で一覧が満杯になる極端なケースで早く終わりうる(無限ループを避ける側に倒している)
- コミット未実施

## 次のアクション

1. 再レビュー(code-reviewer: A1〜A6 と専用クライアント・D-93 の変更、test-reviewer: Important 3件の解消と追加テスト)
2. 解消確認後、P5(api・main・起動順)へ
