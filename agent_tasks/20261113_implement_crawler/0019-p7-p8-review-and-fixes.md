# 0019 P7+P8 のレビューと修正

日付: 2026-11-14 / 実施: code-reviewer・test-reviewer(code 2回・test 1回)、code-implementer(修正)/ 記録・再検証: メインエージェント
レビュー対象: P7(`source_delete`・`scheduler`・`jobs/records/latest_crawl.py`・`JobHistory.find_latest_crawl_queued_at`)と P8(`api`・`config.py`・`main.py`)と対応テスト(`apps/crawler/` は未コミット。比較基準 HEAD `061dc7b196f67a689e0d834eb676ce356d6cdb34`)。**データ削除を含むため code-reviewer は省略していない**

## 1. 1回目のレビュー結果(ともに「軽微な修正で可」、Critical なし)

### code-reviewer の結論(依頼した2つの判断)

1. **メンテナンスフラグの範囲(0016 §3)は設計書どおり(順1・2・4の前だけ確認、順3・5は確認しない)のままでよい。順3・5をフラグで止める変更は勧めない**。根拠: (a) 順3は `loreley-jobs` の Crawler 自身の記録(skip・oversize)を消すだけで、検索インデックスにも Indexer の `loreley-deletions` にも書かない=architecture 7.9「メンテナンスの目的は検索インデックスの書き込みの停止」の対象外、(b) 順2の最中にフラグが立っても順3は実行され順4の前の確認で `failed(maintenance)` になり、再実行で復旧できる(止まった時点は「文書は削除済み・skip/oversize 記録は削除済み・削除記録は残存・設定は `deleting` で残存」。`deleting` が残るのでクロール・更新は拒否されたままで中間状態を悪用できない。再実行はフラグが下りた後=`accept_source_delete` が受付でフラグを確認する。再実行では順1 discard・順2 の0件削除・順3 の0件削除・順4・順5 が冪等に完了)、(c) 順3・5も止めても止まる位置が数手早まるだけで安全性は増えず、Store 層だけの後始末まで止まる、(d) 順5は順4成功後にしか到達せず、`delete` は `status=deleting` かつ読んだ版を条件にするので再登録された別の設定は消さない。関連所見: 順0の `mark_deleting` もフラグの確認前に実行される(受付の後・実行開始の前にフラグが立つと、文書を消さないまま設定が `deleting` になりクロール・更新が止まる。設計書は順0を確認対象にしておらず再実行で復旧できる。実害は小さい)
2. **停止時に OpenSearch・Indexer の接続を閉じない判断(0018 §3・§6-3)は妥当**。停止後も実行中のジョブ(daemon スレッド)は join 待ちの間・プロセスが終わるまで動き続け、接続を閉じると `_finish_as_failed` が閉じたクライアントで `failed` を書こうとして失敗する=CM-U-4(終了処理をしない)の趣旨と逆。リソースは OS がプロセス終了で回収する

### code-reviewer の指摘と対応

| 重要度 | 指摘 | 対応 |
| --- | --- | --- |
| Important | **SIGTERM で `main()` の `finally`(停止処理)が走らない**。uvicorn の `capture_signals` は graceful shutdown 後に元のシグナルハンドラを復元して `signal.raise_signal` で再送出する。SIGTERM の元ハンドラは SIG_DFL なので PID 1 でないとき `uvicorn.run` から戻る前にプロセスが即死(実測 exit=143)し、`stop_components` と停止ログが走らない。データの安全性には影響しない(CM-U-4)が、docstring・0018 §5 の記述と実挙動が食い違い、`uvicorn.run` を差し替えるテストでは検出できない | **(a) を採用**: `uvicorn.run` の前後だけ SIGTERM・SIGINT を「何もしない関数」に差し替える `_return_normally_after_a_stop_signal`(`signal.signal` の戻り値で復元、例外・`SystemExit` でも `finally` で復元)。再送出を受けても `uvicorn.run` が正常に戻り `finally` の `stop_components` が走る(PID 1 かどうかに依らず同じ挙動)。実プロセスに SIGTERM・SIGINT を送るテスト(終了コード0・停止完了ログ・停止後にポートが閉じる)を追加。(b)(シグナル受信時に `request_stop`)は再送出でプロセスが死ぬ根本原因を直さないため不採用 |
| Suggestion | "the crawler is ready" が uvicorn の bind 成功前に出る | 文言を "starting the HTTP server: owner=..." に変更(bind 成功を意味しない) |
| Nitpick | `start_components` の途中(`runner.start`・`scheduler.start`・`create_app`)で例外が出ると `stop_components` が走らない | 例外時に `stop_components` してから再送出(回復失敗時は何も開始していないので止めない)。テスト追加 |
| Suggestion | Scheduler の見送り(`maintenance_enabled`・`source_deleting`)が周期ごと INFO、ソース単位の例外ログに種別名がない | `lock_held`・`maintenance_enabled`・`source_deleting` の見送りを DEBUG に。例外ログに型名・固定の理由名・種別名(`StoreUnexpectedResponseError(malformed_job_record)` など。値は出さない) |
| Suggestion | `/healthz` のアクセスログが compose のヘルスチェック間隔で1日約2,900行 | `/healthz` だけ DEBUG(他は INFO。ルートのテンプレートのみ) |
| Nitpick | `scheduler/waiter.py` が `TickWaiter` の形を再宣言、`Components.heartbeat_factory` が本体で未使用、`config.py` `_pick` の docstring の参照先 | `TickWaiter`・`EventTickWaiter` を `jobs/__init__` で再公開し `scheduler/waiter.py` を削除(依存ルール `scheduler`→`jobs` は許可済み)、コメント・docstring を修正 |
| Suggestion(対応せず) | 更新(PUT)で `api` が `sources.fetch` を余分に1回読む設計(0017 §3-2)。`SourceStore.update` に検証コールバックを渡す案など | 現状維持。設計書にない詳細として改版依頼に載せる(R4 の違反とまでは言えない。Store の読み取りは R9 が許す) |
| Suggestion(対応せず) | `ConnectorRegistry`・`ConnectorError`・`ErrorCategory` を `sources` 経由で再公開するのは R4 の迂回に近い | 現状維持(安全上の問題なし)。改版依頼に載せる |
| Suggestion(対応せず) | リクエスト本文のサイズ上限がない(50MB の本文が登録できる) | 設計書に規定がなく改版が先。改版依頼に載せる |
| Nitpick(対応せず) | `ttl` 等の int64 超の整数が400でなく500になりうる/405 の `Allow` ヘッダが落ちる | P4 から申し送り済み(設計書は範囲を検証しない)/契約外 |

code-reviewer が重点観点で指摘なしと確認: ソース削除の全経路で後続の破壊的操作を行わず `failed` で止まる(確認点の位置・リトライの各試行前・409 `lock_not_owned`・`finish` の False・順5の `deleting` 限定・他ソースの記録を消さない・冪等性)、Scheduler(期限判定・起点・拒否の見送り・エラーの隔離・`force_delete`/`rewrite_mode` が常に false)、api(契約・R4・結果型の写像の網羅・厳密な JSON・R11・CAPI-P-17)、config(秘密・整合性検査・CM-U-9)、main(起動順・Repository 3つ・`JobRunner` に両実行対象・`JobAdmission` 共有・uvicorn の引数)。

### test-reviewer(Important 4、Suggestion 8、Nitpick。約95件の変異をほぼ検出。実質的な生存は9件)

| 重要度 | 指摘 | 対応 |
| --- | --- | --- |
| Important 1 | `main()` が秘密のマスキングを配線していることを検証していない(`secrets=config.log_secrets` を `()` に変えても通る) | HTTP が開いている間に `logging.warning("password=%s", PASSWORD)` を出し stderr に `password=***` が出てパスワードが出ないことを検査 |
| Important 2 | 実 uvicorn の起動と停止が一度も実行されない(`uvicorn.run` を差し替え) | `tests/main/test_real_server.py`・`process_entry.py`: 実プロセス(`port=0`・起動ログからポートを得る)で `/healthz` 200 → SIGTERM・SIGINT で終了コード0・停止ログ・停止後にポートが閉じる。同一プロセスの実 uvicorn で `main()` と同じ `http_server_options` を検査(`workers == 1`・`log_config=None`・`access_log=False`・`lifespan="off"`・graceful 10秒)。`uvicorn.run` の引数を `http_server_options(config)` に切り出し。subprocess の env に `PYTHONPATH` を追加 |
| Important 3 | 順2の最中にメンテナンスフラグが立つ場合を固定していない(順5の前にフラグ確認を足す変異 SD18 が生存) | `tests/source_delete/test_maintenance_scope.py`: フラグの読み取りは順1・2・4の前だけで合計3回、順2の最中に立っても順3は実行され順4の前で `failed(maintenance)`・設定は `deleting` のまま・フラグを下ろして再実行すると `succeeded` で設定とロックが消える、順4の最中に立っても順5は実行される、順1の最中は順2の前で止まり順3に進まない。順3・順5・順1〜5の前にフラグ確認を足す3種の変異を検出 |
| Important 4 | 破壊的な `POST /sources/{source_id}/delete-jobs` の `source_id` 検証テストがない(`check_source_id_path` を外す変異が全件を通過) | `delete-jobs`・`crawl-jobs` の両方で不正な `source_id`(`-bad`・257文字・改行・空白・`%`・`.dot`・`é`)が400 `source_id: format` で、ジョブ・ロックが作られず書き込みもない |
| Suggestion | エラー応答の `message`・`details` の不在を固定、`http_port` の範囲、深い入れ子(`RecursionError` の分岐に到達)、`config_invalid` の `message` の512文字切り詰め、PUT の保存済み設定の `fetch` が `deps.retrier` を通ること、重複キーの現状挙動 | すべて対応 |
| Suggestion | 再実行・途中停止のシナリオ、main の起動失敗点の網羅 | 失敗点(順4の Indexer 失敗・順5の Store 失敗・ロック喪失)をパラメータ化して最後の再実行で `succeeded` と設定・ロック・スキップ記録の削除まで確認(`tests/source_delete/test_rerun.py`)。`running` の `source_delete` を残して停止→`crawler_restart` の回復→再度の受付で完了。`runner.start`・`scheduler.start`・`create_app` が例外を出す場合に HTTP を開かず・スレッドが残らず・`stop_components` が走る |
| Suggestion | タイミング・環境依存(`join_timeout_seconds=0.1`、`threading.active_count()` の等価比較、`closed_port()` の競合) | join 上限を1秒に、名前の集合の比較に、`port=0`+起動ログでポートを得る |
| Suggestion | fake の忠実度の限界 | メモリ上 Repository の `scan` が `document_id` を持たない同種の記録が2件以上ある場合の `non_unique_sort` を再現しない/降順ソートの実マッピングは fake で検証できない/`FakeIndexerClient.delete_*` が `lock` の値を検証しない。**docstring に記録し P9 の実機確認(持ち越し)へ** |
| Nitpick | `test_scheduler_thread.py` の join 済み後にアサートして空振りしているテスト等 | 実質的な検証に置換、タイミングで結果が変わるテストは結果が依らないことを docstring に明記 |

## 2. 2回目のレビュー(code-reviewer、SIGTERM 修正などの変更点に絞る): **可**(Critical・Important なし)

- A1(シグナル処理): 実プロセスで実測(SIGTERM 1回・2回連続・SIGINT のいずれも `RETURNED`・`FINALLY` が出力され exit=0。daemon スレッド(`sleep(1000)`)が動いていても即座に終了)。`signal.signal` の戻り値で復元、`uvicorn.run` が例外・`SystemExit`(bind 失敗の `sys.exit(1)` を含む)で終わっても `finally` で復元される。起動前・回復中のシグナルは既定のまま(プロセスが即終了。回復は冪等で、`running` のジョブは次回の回復が `failed(crawler_restart)` にする)。PID 1 の場合との挙動差はなくなった。**データの安全性(CM-U-4)は変わらない**(`stop_components` は `request_stop` と `join` だけで、ジョブの完了を待たず・状態も書かず・ロックも削除しない)。終了コード0は妥当(`on-failure` では再起動されず、bind 失敗や例外は非0のまま)
- A3: `recovery.run()` を `try` の外に置き、その後を `except BaseException: stop_components(...); raise`。部分的に起動した状態の停止・二重停止なし・例外の握りつぶしなし
- A4〜A6・ready 文言・`http_server_options` の切り出し: 問題なし(`uvicorn.run` の引数は変更前と同一)
- **指摘(いずれも対応しない。許容)**:
  - Suggestion: uvicorn の signal 差し替え直後〜uvicorn が自分のハンドラを入れるまでの数ミリ秒の窓で SIGTERM が無視される(オーケストレーターが猶予後に SIGKILL するだけでデータ上の問題なし)
  - Suggestion: 処理中の同期ハンドラ(Store のリトライで最大約90秒)があると、`finally` 後もワーカースレッド(非 daemon)の終了を待つため終了が遅れる(実測で約20秒後も残った)。変更前も PID 1 のコンテナでは同じ。**compose の `stop_grace_period` を uvicorn の graceful(10秒)と join(5秒×2)を足した値より長く取る運用で足りる=P9 の README に書く**
  - Nitpick: `start_components` の戻りから `main` の `try` に入るまでの窓の SIGINT(実害なし、次回の回復が拾う)

## 3. 検証結果(メインが再実行、`apps/crawler`)

```
$ uv run pytest -q           -> 3249 passed, 3 skipped in 49.30s(P8b 後 3199 → +50)
$ uv run ruff check          -> All checks passed!
$ uv run ruff format --check -> 276 files already formatted
$ uv lock --check            -> Resolved 39 packages
```

`git status` は `apps/crawler/` のみ。残りのプロセス・待ち受けポートなし。実装担当は `tests/source_delete tests/scheduler tests/api tests/main` を5回連続成功(508件)。変異確認(scratchpad のコピー、15件)はすべて検出(SIGTERM の差し替えを外す→終了コード143、起動途中の失敗で停止しない、`secrets` の配線を `()`、停止の join 上限10倍、順3・順5・順1〜5の前にフラグ確認を足す3種、`delete-jobs` の `source_id` 検証を外す、PUT の `fetch` を retrier なしに、Scheduler の見送りを INFO に戻す/種別名を落とす、`/healthz` を INFO に戻す、`http_port` の `ge`・`le` を外す、512文字の切り詰めを外す、`RecursionError` の分岐を外す)。

## 4. 設計書の改版依頼リスト(提案。P7+P8 のレビュー修正分。0016 §6・0017 §8・0018 §7 に追加)

1. SIGTERM/SIGINT の扱い(module 5.7・CM-U-4): uvicorn が graceful shutdown → 元ハンドラを復元して再送出 → `main` の停止処理。再送出で停止処理が飛ぶのを避けるため、`uvicorn.run` の前後だけ再送出を無害に受けるハンドラを入れる。終了コードは0
2. メンテナンスフラグの範囲の結論(architecture 8.1・7.9、module 4.6): 確認するのは順1・2・4の前だけで順3・5の前では確認しない(順0の `mark_deleting` も確認前)。順2の最中に立っても順3は実行され順4の前で `failed(maintenance)`、再実行で冪等に完了。順4の最中に立っても順5は実行される。順3は Crawler 自身の記録の削除でフラグの目的の対象外。実行中のフラグ読み取りは合計3回
3. 停止時に OpenSearch・Indexer の接続を閉じない判断(CM-U-4)
4. **停止の時間予算**: uvicorn の graceful 10秒+join 5秒×2(Scheduler・Runner)+Scheduler の retrier の最大約3秒が Docker の既定の停止猶予10秒を超えうる。処理中の同期ハンドラがあると終了がさらに遅れる。compose の `stop_grace_period` の設定と README(P9)での注意を要する(超えても次回の回復が `failed(crawler_restart)` にするので安全性は変わらない)
5. ログの水準: `/healthz` のアクセスログは DEBUG、Scheduler の見送り(`lock_held`・`maintenance_enabled`・`source_deleting`)は DEBUG、Scheduler のエラーログに種別名を付ける
6. ready ログは bind の成功を意味しない(文言は "starting the HTTP server")
7. 起動途中の失敗(`runner.start`・`scheduler.start`・`create_app`)では、開始したスレッドを止めてから異常終了する
8. リクエスト本文のサイズ上限は規定なし(必要なら改版が先)
9. 更新(PUT)で `api` が保存済み設定を読んで `connector_type` を得ること(0017 §3-2)
10. `ConnectorRegistry`・`ConnectorError` を `sources` 経由で再公開すること

## 5. 持ち越し(P9 の実機確認・統合テストへ)

- コンテナの PID 1 での SIGTERM、実 OpenSearch・実 Indexer との組み合わせ、実 Docker での停止猶予、`/healthz` の `healthy` 化
- fake の限界: メモリ上 Repository の `scan` が `non_unique_sort` を再現しない、降順ソートの実マッピング(`queued_at`・`job_id`)は fake で検証できない、`FakeIndexerClient.delete_*` が `lock` の値を検証しない
- 件数照合の独立検証(Indexer 側の N_seen+E_missing。0015 §7)

## 6. 次のアクション

P9(Dockerfile・README・最終検証)を `code-implementer` に依頼する(0018 §5 の起動方法・HEALTHCHECK の `--start-period`、0017 §5 の環境変数一覧、0009 §3 の `LORELEY_REQUIRE_LINUX_NAMES`、本記録 §4-4 の停止の時間予算と `stop_grace_period` を README に)。P9 完了後に Dockerfile を code-reviewer、README・作業記録を document-reviewer でレビュー(0002 §6)→ 作業記録の最終整理(仮値一覧・採用案一覧・決めた内容・持ち越し一覧・完了条件の検証結果。メインが作成)→ task-reviewer(0002 §8)。
