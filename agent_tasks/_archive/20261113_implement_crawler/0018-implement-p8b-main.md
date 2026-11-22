# 0018 P8b: `main.py`(組み立て・起動順・停止順)

日付: 2026-11-14 / 実施: code-implementer / 記録・再検証: メインエージェント
フェーズ開始時点の HEAD: `061dc7b196f67a689e0d834eb676ce356d6cdb34`(`apps/crawler/` は未コミット)。P7+P8 の code + test レビューを次に実施(データ削除を含むため code-reviewer 省略不可)。

## 1. 検証結果(メインが再実行、`apps/crawler`)

```
$ uv run pytest -q           -> 3199 passed, 3 skipped in 27.45s(P8a 後 3153 → +46)
$ uv run ruff check          -> All checks passed!
$ uv run ruff format --check -> 273 files already formatted
$ uv lock --check            -> Resolved 39 packages
```

`git status` は `apps/crawler/` のみ。残りのプロセス・待ち受けポートなし。実装担当は3回連続成功を確認。変異確認(scratchpad の別コピー、22件)は全件検出(初回20件のうち変異文が効いていなかった2件は直して再実行)。

## 2. 実装内容

- `src/loreley_crawler/main.py`(新規。composition root): `Backends`・`Components` の dataclass、`create_backends`、`assemble`、`start_components`、`stop_components`、`main`
- `tests/main/`(新規37件): `support.py`・`conftest.py`・`test_startup_order.py`・`test_assembly.py`・`test_shutdown.py`・`test_end_to_end.py`・`test_process.py`
- `tests/architecture/test_write_rules.py`(追記): R7「`main` が作る Repository は3つ」の機械検査。`tests/architecture/test_dependency_rules.py`(追記): `main` が全機能モジュールを使い許可範囲だけを import すること、`main` を import するモジュールがないこと。許可表は無変更

## 3. 判断・設計

**起動順(`main()`)**: (1) `load_config()`、(2) `configure_logging`、(3) `warn_about_unchecked_indexer_limits`、(4) `create_backends`(クライアント生成のみで接続はしない)、(5) `assemble`(I/O もスレッドもない)、(6) `StartupRecovery.run()`、(7) `JobRunner.start()`、(8) `Scheduler.start()`、(9) `create_app`、(10) `uvicorn.run`。`ConfigError`・回復失敗・接続失敗は捕捉せず、HTTP を開く前に非0で終わる。**アプリは回復の後に作る**(uvicorn はアプリを受け取るまで接続を受け付けないので、回復中は `/healthz` を含め応答しない。`api` に ready フラグは持たせていない)。uvicorn は host・port(config)、`log_config=None`、`access_log=False`、ワーカー数1、加えて `lifespan="off"`・`timeout_graceful_shutdown=10`(仮値)

**組み立て**: Repository はちょうど3つ(`loreley-sources` 用と `loreley-jobs` 用は Store 層クライアントを共有、ハートビート専用の `loreley-jobs` 用は専用クライアント)。`JobRunner` に `{CRAWL: CrawlExecutor, SOURCE_DELETE: SourceDeleteExecutor}`。Scheduler と API は同じ `JobAdmission` を共有。`SourceStore` は `api` と `source_delete` で共有。ハートビートは専用クライアントの `LockStore` を使う `heartbeat_factory`。リトライは確認点なしの `Retrier(config.retry_policy)`。テスト用の差し替え口 `assemble(..., clock=, connector_registry=None)`

**停止順**: uvicorn が SIGTERM/SIGINT で止まって戻った後、`main()` の `finally` で `stop_components`。順序は Scheduler → JobRunner の `request_stop()` → 各 `join`(上限5秒。仮値)。上限までに終わらないスレッド名を警告して返す。**実行中ジョブの完了を待たず、最終状態の記録・ロック解放もしない**(ジョブは `running` のまま、ロックも残り、次回の回復が `failed(crawler_restart)` にする。CM-U-4。理由は docstring)。**OpenSearch・Indexer の接続は閉じない**(閉じると実行中ジョブが途中で失敗記録を試み「終了処理をしない」方針とずれる。プロセス終了に任せる)。ハートビートはデーモンスレッドでロックは削除しない

## 4. テスト

(a) 起動順: 実行順が `load_config → configure_logging → warn → create_backends → assemble → recovery.run → runner.start → scheduler.start → create_app → uvicorn.run → scheduler.stop → runner.stop` と一致。回復中に `create_app`・uvicorn・Runner/Scheduler スレッドがまだ無い。`owner` 未設定・整合性検査違反は ConfigError で `create_backends` に到達せず(パスワードを含まない)、回復失敗では Runner・Scheduler・アプリ・uvicorn のどれも始まらない。uvicorn 内で例外が出ても停止処理が走る。(b) 組み立て: スレッドも Store・Indexer への呼び出しも無い、両実行対象の型、`JobAdmission`・`SourceStore` の共有、ハートビートが専用 Repository、`create_backends` が Repository 3つ(クライアントは store×2・heartbeat×1、索引名は sources・jobs・jobs)、閉じたポートへの実クライアントで `StoreUnavailableError`。(c) 停止: ジョブを列挙の手前で止めて停止、join がタイムアウトで戻り(5秒未満)ジョブは `running`・ロック残存・終了通知なし、別の組み立て(再起動を模す)の回復で `failed(crawler_restart)` になりロックが消える、停止順は Scheduler → Runner、待機中の停止は即座に完了、起動前の停止は無害。(d) R7 の機械検査: Repository・クライアントの生成は `main.py`(と定義元)だけ、`OpenSearchRepository(...)` はちょうど3つ、`create_store_client`・`create_heartbeat_client` は各1回、合成ソースで4つ目・別索引・ハートビート用が store クライアントの場合を検出できる。(e) 依存ルール: `main.py` の import は許可表の範囲で全機能モジュールを使い、`main` を import するモジュールはない。(f) センチネル: `main()` 経由で起動〜API〜ジョブ実行〜停止まで DEBUG ログを stderr に取り、OpenSearch のパスワード・`connector_config` の秘密・文書本文がログにもエラー応答(`config_invalid` の400を含む)にも出ない、設定エラーの文言にもパスワードは出ない(登録の201だけは保存した設定を返す契約なので対象外)。(g) E2E: `main()` の本物の組み立てで `/healthz` → `POST /sources` → `POST /sources/docs/crawl-jobs` → Job Runner が一時ディレクトリの FS Connector(2文書)を処理 → Indexer の呼び出し順 `start → last_seen → register → finish:enumeration_completed → status` → ジョブ `succeeded`・ロック解放。待ちはロック削除の直前に立つ `Event`(上限10秒)、スリープなし。プロセス: `python -m loreley_crawler.main` を実プロセスで起動し、必須設定なし・整合性違反・到達不能な OpenSearch(閉じたローカルポート)のいずれも非0で終了、到達不能なら `the crawler is ready` が出ずパスワードも出ない

## 5. 起動方法・シグナル(P9 の Dockerfile `CMD` 用)

`CMD ["python", "-m", "loreley_crawler.main"]`。環境変数は 0017 §5(必須は `OWNER`・`OPENSEARCH_URL`・`INDEXER_URL`)。設定エラー・整合性違反・回復失敗はトレースバックを stderr に出して終了コード1(メッセージに値・秘密は含まない)。シグナルは uvicorn が扱う(`main` が独自のシグナルハンドラは持たない)。**HEALTHCHECK は、起動時の回復が終わるまで接続できないため `--start-period` を十分に取る**

## 6. 設計書との食い違い・不明点

1. architecture 10章・module 5.7 の起動順に「ログの設定」「未設定の Indexer 上限の警告」の段階がない。実装では (2)(3) として設定の読み込み直後に置いた
2. module R7 の「Repository 3つ」は、ハートビート専用を含めた3つで実装した
3. 停止時にクライアントを閉じない判断は Indexer の `main`(接続を閉じる)と異なる。CM-U-4 の「終了処理をしない」に合わせた
4. 停止のタイムアウト5秒、HTTP の graceful shutdown 10秒は設計書にない仮値
5. 実機でしか確認できないもの: SIGTERM を受けた実 uvicorn の挙動(テストでは `uvicorn.run` を差し替えている)、実 OpenSearch・実 Indexer との組み合わせ、`/healthz` の `healthy` 化

## 7. 設計書の改版依頼リスト(提案。P8b 分)

1. architecture 10章・module 5.7: 起動順に「ログの設定」「未設定の Indexer 上限の警告」を足す。アプリケーションの作成と uvicorn の開始は、回復・スレッド起動の後
2. module 5.7・CM-U-4: 停止の実装を明記(uvicorn 停止 → Scheduler → Job Runner の `request_stop` と join(タイムアウトつき)/接続は閉じない/ジョブは放置)
3. architecture 11章: 停止の join 上限5秒、HTTP graceful shutdown 10秒を採用値として追記
4. module R7: 「`main` が作る Repository は3つ」の機械検査の方法(`OpenSearchRepository(...)` の生成箇所の AST 検査と、検出できない限界)

## 8. 未対応事項・次のアクション

- Dockerfile・README(P9)は未実装。実機でしか確認できない項目(§6-5)は持ち越し
- 次: P7+P8 の code-reviewer・test-reviewer を並列レビュー。重点: メンテナンスフラグの範囲(0016 §3)、起動順・停止順(停止時に接続を閉じない判断を含む)、ログ流出、データ削除の安全側、`api` の更新時の `connector_type` の読み取り(0017 §3-2)、R4・R7
