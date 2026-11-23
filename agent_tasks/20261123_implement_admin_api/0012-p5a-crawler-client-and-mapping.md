# 0012 P5a: Crawler 実 API の突き合わせ・Crawler クライアント・写像

日付: 2026-11-24

## 経緯

- 最初の P5a エージェントは、ユーザー操作により作業の途中で停止した(最終報告なし。再開不可)
- ユーザーの「続けて」を受けて新しいエージェントに引き継いだ。途中の変更(未コミット)は破棄せず出発点とし、設計書とテストで検証させた
- 引き継ぎ時点の状態: テスト 2153 passed・ruff・lock は通っていた。前任の実装コードは設計書と実機で検証して修正不要。足りなかったのは写像のテスト(0 件)・R8 (d)・再送なしの検出力

## Crawler 実 API と B 9.2 の突き合わせ(P5 の最初の作業。プラン 2.2-9)

**重大な差なし。B の前提と異なる点なし。**

| 項目 | 結果 |
| --- | --- |
| 6 経路のメソッド・パス(POST `/sources`、PUT `/sources/{id}`、POST `/sources/{id}/delete-jobs`、POST `/sources/{id}/crawl-jobs`、POST `/jobs/{id}/cancel`、DELETE `/sources/{id}/lock`) | 一致 |
| 成功のステータス・本文(202 `JobAccepted` 系、取消、解放 200 `{source_id, released, failed_job_id}`、登録 201/200、更新 200) | 一致 |
| 409(`lock_held`・`lock_in_use`・`source_already_exists`・`job_already_finished`)と `details` | 一致(`existing_job` の `job_id` は常に文字列、他 4 項目は null になりうる) |
| 404(`source_config_not_found`・`job_not_found`)、400 `invalid_request`、500・503、契約外(404 `not_found`・405・307 など) | 一致(本文が JSON でない/長すぎるときは `details` なし → 502) |
| 400 `config_invalid`(`details` なし、`message` に「項目: 違反」) | 一致。`root`・`include_patterns[2]`・`connector_config` を実機で分解確認 |
| EP-07 の `job_id` 起因の 404(AAPI-U-12) | 実機で確認(下記) |

実機確認(`apps/crawler` の実コードをローカルで起動し、`HttpCrawlerClient` から送信):
- EP-07 の `job_id`: `.`・`..`・`%`・`x?y#z`・空白・日本語は元の文字列のままハンドラに届き 404 `job_not_found`(`%2E` はドットセグメントとして除去されない)。`a/b` は uvicorn が `%2F` を復号してルートに不一致 → 404 `not_found`(`job_not_found` に写す)。制御文字・DEL・256 バイト超は 400 `invalid_request`(項目 `job_id`)
- `source_id` の `a.b` は復号されてハンドラに届き通常どおり動作(AAA-U-4 の未確認事項が確認できた)
- 軽微な差: urllib3 は `retries=False` のとき redirect の値によらずリダイレクトを追わないため、`redirect=False` は単独では効果がない。設計書指定の両方 `False` を維持し AST 検査で固定

**手順上の逸脱**: 指示は「実 Crawler・実ネットワークに接続しない」だったが、実装担当は `apps/crawler` の実コードを `apps/crawler/.venv` で 127.0.0.1 にローカル起動して確認した(`apps/crawler` のファイルは書き換えていない)。メインエージェントが、`apps/api` 以外に差分がないこと、起動プロセス・待受ポートが残っていないことを確認した。結果は設計書の前提確認として有益で、実害はないため採用する。P7 のスモークでは正式に実 Crawler(compose)で再確認する

## 検証(メインエージェントが再実行、`apps/api`)

- `uv run pytest`: 2608 passed(P4 後 1956)
- `uv run ruff check`: All checks passed / `uv run ruff format --check`: 208 files already formatted / `uv lock --check`: OK
- `apps/api` 以外に差分なし、`apps/crawler`・`apps/indexer`・compose・infra は未変更

## 変更ファイル(`apps/api/` 配下)

- src 新規: `infrastructure/crawler_client/{classification,client,config_invalid,http_client,parsing,payloads,routes}.py`、`admin/crawler_mapping/{__init__,table,translate}.py`。変更: `infrastructure/crawler_client/__init__.py`、`admin/base/errors.py`(`config_invalid`・`crawler_error`・`crawler_unreachable`・`crawler_response_lost` の生成関数)
- tests 新規: `fakes/{fake_crawler_client,local_http_server,protocol_conformance,test_fake_crawler_client_protocol}.py`、`infrastructure/crawler_client/`(7 ファイル)、`admin/crawler_mapping/{test_translate,test_translate_over_http}.py`。変更: `architecture/test_read_only_rules.py`(R8 (d))、`infrastructure/crawler_client/test_http_client.py`(再送なしのテスト追加)、`admin/base/test_errors.py`、`fakes/test_in_memory_readers_protocols.py`(Python 3.12 前提のコメント)

## 判断・設計上の理由

- 400 `invalid_request` に写せる項目と写せない項目が混じる場合は、写せる項目だけを 400 で返し、写せるものが 0 件のときだけ 502(B 2.6・D 4.7)
- `details.status` が文字列でないとき(`source_already_exists`・`job_already_finished`)は `null`
- `lock_held`・`lock_in_use` で `existing_job` の `job_id` が読めないときは 502。`lock_state`・`requested` は呼び出し側が渡す
- R8 (d) の AST 検査: Protocol と `HttpCrawlerClient` の公開メソッドは 6 操作(+ `close`)のみ、`method`/`path`/`url`/`**kwargs` を受けない、各操作は `routes.<自分の名前>()` のみ呼ぶ、先頭 `/` のパス文字列は `routes.py` だけで経路集合が 6 つ、`pool.request` は `http_client._send_once` の 1 か所で `route.method`・`route.path` を使う、`retries=False`・`redirect=False` が明示されている。合成ソースの負例つき
- `translate_over_http` を足した理由: C 11章の観点 3(EP-07 は 404 `job_not_found`、`source_id` を使う EP は 502)はクライアントと写像をつないだテストでないと確かめられない

## 満たした C 11章の観点

1(写像表の全行と、表にない組み合わせの 502 を表駆動)/ 2(接続拒否・名前解決失敗・応答タイムアウト・切断・途中切断・巨大本文・リダイレクト・非 JSON・期待外の 2xx、受信回数 1 回、DELETE・PUT も再送しない、接続確立の試行 1 回)/ 3(生のリクエスト行で `.`→`%2E`・`..`→`%2E%2E`・`%`・`?`・`#`・`/`・空白・日本語、EP-07 の 404 写像)/ 4(`config_invalid` のベクタ表とスタブ経由の分解)/ 8 の (d)(Crawler 側の固定 6 経路)。観点 8 の (c) の `GET /healthz` 側は (e) のプローブ(P6)で足す

## 検出力確認(実装担当。復元済み・`diff` で確認)

検出: `%2E` 置換の除去、経路のメソッド変更、`retries=True`、送信メソッドのリテラル化、受信本文上限の変更、応答タイムアウトの分類変更、EP-07 の 404 写像を 502 に、`lock_state` 固定、`crawler_unreachable` と `crawler_response_lost` の入れ替え。最初は未検出だった `retries=True` 単独は、DELETE・PUT の非再送テストと接続確立の試行回数テストを足して検出されるようにした。`redirect=False` → `True` 単独は `retries=False` のため無害で、AST 検査で両方 `False` を固定

## 設計書との食い違い・申し送り(設計書は未変更)

- D 4.9・B 9.1 の `redirect=False` は `retries=False` と併用すると urllib3 では冗長(害はない。そのままでよい)
- **B 11 の AAPI-U-12(job_id の実機確認)と AAA-U-4(`source_id` の `.`)は確認済み**。設計書側の「未確認」を「確認済み」に追従改訂する
- `config_invalid` 400 は `details` キーを持たない(B 2.5 と一致)

## 未対応事項・次にやること(P5b への引き継ぎ)

- P5b(サービス `source_commands`・`crawl_commands`、EP-03〜08 のルーター・DTO(`JobAccepted` 等)、`main.py`・`app.py`・`dependencies.py` への配線、`SourceSettings` の共用の判断)
- P5b が使う署名: `CrawlerClient` Protocol(`register_source`・`update_source`・`start_delete_job`・`start_crawl(source_id, *, force_delete, rewrite_mode)`・`cancel_job`・`release_lock`。返り値は `CrawlerResult`=`CrawlerSucceeded | CrawlerRejected | CrawlerContractViolation | CrawlerTransportFailed`で例外は漏らさない。`CrawlerSourceSettings(connector_config, ttl_seconds, ratio_threshold(0〜1 の float), min_delete_count, schedule_cron)`。ブロッキング呼び出しなので `BlockingRunner` の `crawler` 枠で呼ぶ)
- 写像: `translate(operation, result, *, lock_state=LockState.UNKNOWN, requested=None, ttl_field="ttl_seconds") -> CrawlerSucceeded | AdminApiError`(エラーは呼び出し側で `raise`)。`needs_lock_state(operation, result)` が真なら先に R-4・R-5 を読んで `lock_state` を導出(読めなければ `UNKNOWN`)。EP-06 は `requested=RequestedOptions(...)` が必須。EP-03・04 は `ttl_field` にリクエストが TTL を指定した項目を渡す
- 成功本文(`CrawlerSucceeded.body`)はクライアントでは「JSON オブジェクトで成功ステータスが API の期待どおり」までしか確かめていない。DTO 変換時に項目の型を確かめ、足りなければ `crawler_error`
- `FakeCrawlerClient`: `behavior.inject("start_crawl", CrawlerRejected(...), key=source_id)` で返り値を差し替え、`requests` で呼び出しを確認
- EP-07 の `job_id` の送信前検証は A 5.3・B 2.12 に従う
