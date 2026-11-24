# 0013 P5b: 書き込み系 EP-03〜08(Crawler 中継)

日付: 2026-11-24

## 実施内容

`code-implementer` が P5b を実装。メインエージェントが検証を再実行して確認した。これで P5(書き込み系)が完了した。

## 検証(メインエージェントが再実行、`apps/api`)

- `uv run pytest`: 3032 passed(P5a 後 2608)
- `uv run ruff check`: All checks passed / `uv run ruff format --check`: 222 files already formatted / `uv lock --check`: OK
- `apps/api` 以外に差分なし。`pyproject.toml`・`uv.lock` 未変更。起動プロセス・待受ポートの残りなし。`if False`・`return days$` などの検出力確認の残骸なし
- 実 Crawler・実 OpenSearch・実ネットワークには接続していない(`FakeCrawlerClient` とローカル HTTP スタブのみ)

## 変更ファイル(`apps/api/` 配下)

- src 新規: `admin/services/{crawler_relay,crawler_responses,source_commands,crawl_commands}.py`、`admin/routers/crawl_operations.py`
  - `crawler_relay`: 中継の共通手順。`crawler` 枠で 1 回だけ送り `translate` で写す。409 `lock_held`・`lock_in_use` のときだけ Crawler の応答の後に `lock_view`(R-4 → R-5)で `lock_state` を読む(読めなければ `unknown`)。`WithStatus[T]` で Crawler の 200/201/202 を引き継ぐ
  - `crawler_responses`: Crawler の成功本文を DTO にする。型が読めなければ `None` → 呼び出し側が 502 `crawler_error`
- src 変更: `schemas/common.py`(`RequestModel`(strict・未知項目拒否)、厳格な `SourceSettings`(EP-03・04)、`JobAccepted`、従来の nullable 版は `StoredSourceSettings` に改名)、`schemas/sources.py`・`schemas/jobs.py`(リクエスト・応答 DTO)、`routers/sources.py`(POST EP-03・05、PUT EP-04)、`routers/request_input.py`(`read_body_as(model)`、`SOURCE_ID_PATTERN` を `base/constants.py` へ)、`routers/jobs.py`(import 元のみ)、`routers/__init__.py`・`app.py`・`dependencies.py`・`main.py`(配線、`HttpCrawlerClient` を closers に)
- tests 新規: `admin/write_requests.py`、`admin/crawler_mapping/mapping_rows.py`(B 9.2 の全 35 行)、`admin/routers/test_{source_commands,crawl_operations,crawler_mapping_through_endpoints,write_eps_over_http}.py`、`admin/services/test_{crawler_relay,source_commands,crawl_commands}.py`
- tests 変更: `admin/factories.py`・`admin/conftest.py`・`admin/crawler_mapping/test_translate.py`・`admin/routers/test_sources.py`(一覧の POST は EP-03 のため 405 の期待を `put/patch/delete` に、詳細は `test_the_detail_accepts_only_get_and_put`)・`test_main.py`(Crawler URL への中継と停止時 close)

## 判断・設計上の理由

- **`SourceSettings` は分けた**(推奨どおり): 厳格版 `SourceSettings`(EP-03・04。`connector_type`・`status`・`updated_at` が非 null、null を許すのは `ttl_days`(日で割り切れないとき)と `schedule_cron` のみ)。nullable 版は `StoredSourceSettings`(EP-02 の `SourceDetailResponse` の基底)。EP-01・02 のワイヤ形式・既存テストは不変。Crawler が返した本文は `read_source_settings` で読み、読めない項目があれば 502(保存・登録は実行済みの可能性。B 10.2)
- 検証は 2 段: ルーターで形(型・必須・未知項目)、`services` で排他・範囲・桁。形の違反があれば範囲の検証はしない(B 2.12 の順序)。範囲・排他・必須の違反はまとめて返す(B 3.3 の例)
- `ttl_days`・`ttl_seconds` の両方指定/両方なしの違反は `field` を `ttl_days`(B 3.3 の例)。明示的な `null` は `type`、省略は「指定なし」。Crawler の `ttl` 違反は送った方の項目名で返す
- `ratio_threshold_percent` は strict の `float`(`int | float` の union だと違反の項目名が `ratio_threshold_percent.int` のように型名つきになるため)。副作用として `10**400` のような巨大整数は `range` でなく `type`
- `connector_config` 内の `NaN`・無限大(`1e999` は `inf` に読まれ、`allow_nan=False` の送信で 500 になる)は、送信前に 400(`connector_config` の `type`)。中身の検証ではなく送信の前提を守る処置
- `lock_state` を読む時刻は Crawler の応答後の `clock.now()`(D 5.0 の「リクエスト先頭」と異なる。60 秒の猶予 `just_acquired` の判定がずれないように)
- EP-05 の `JobAccepted` は Crawler の応答に `force_delete`・`rewrite_mode` が含まれていても読まず `null`(B 3.5)
- ルーターの配置は D 3章・4.3 に従い、`sources.py` に EP-01〜05、`crawl_operations.py` に EP-06〜08(依頼文の「sources.py に EP-06・08」より D を優先)
- 登録の 201/200、取消の 200/202 は Crawler のものを `response.status_code` で引き継ぐ

## 満たした C 11章の観点

1(`ROWS` 全 35 行を EP 経由で確認、表にない組み合わせの 502、`config_invalid` の分解、TTL 違反の項目名の写し)/ 2(6 操作すべての接続前失敗・応答喪失・契約外応答、実クライアントで 503・500・非 JSON・リダイレクト・切断・途中切断・巨大遅延、6 EP すべてで応答がなくても再送しない=受信 1 回)/ 3(生のリクエスト行が EP 経由でも全文字エンコード。EP-07 は `not_found`・400 を 404 `job_not_found` に写し、`source_id` を使う EP では 502。`/` を含む `job_id` は Crawler に送られず 404)/ 4(`config_invalid` の分解を EP 経由・実クライアント経由で)/ **11(c)**(本文なしの POST が `Origin`(なし・他オリジン・`null`)を問わず処理されることを EP-05・06・07 で記録。CORS ヘッダーなし。EP-03 は `text/plain` だと 400)/ 12(センチネルが不正入力・`connector_config`・`job_id`・Crawler の `message` で応答本文・`caplog`・DEBUG ログのいずれにも出ない。実クライアント経由の DEBUG ログも含む)

P5 の完了条件: 409 の付随情報の読み取り失敗(EP-05・06・08 × `get_locks`/`get_jobs` × unavailable/timeout の 4 通り)でもステータスと `existing_job` は変わらず `lock_state=unknown`。ロック状態 6 値の導出、「Crawler の後に読む」順序、`crawler` 枠と `opensearch` 枠の使い分けも確認

データ削除に関わる取り違え(`force_delete`・`rewrite_mode` の 4 通りを Crawler への引数・応答・409 の `requested` で確認、EP-05・06・07・08 がそれぞれ自分の操作だけを呼ぶ、EP-05 は指定を持たない、誤って `true` を送る不正本文は 400 で Crawler に送らない)も表駆動で確認

## 検出力確認(実装担当。21 件を一時変更し全件検出。復元済み)

`force_delete`/`rewrite_mode` の入れ替え(サービス・ルーター・`requested`)、EP-08 が削除ジョブを呼ぶ、EP-05 がクロールを呼ぶ、`lock_state` を `none` に固定/常に `unknown`/Crawler の前に読む/成功時にも読む、`ttl_days` を換算しない、TTL 項目名の反転、排他検証の削除、ステータス 202→200、Crawler のステータスを引き継がない、strict の無効化、未知項目の許可、`source_id` 形式検証の削除、EP-05 のクエリ拒否の削除、EP-06 の必須チェックの削除、`connector_config` の無限大チェックの削除

## 設計書との食い違い・申し送り(設計書は未変更)

1. B 2.11: `SourceSettings` は EP-02〜04 共通と書かれているが、実装は EP-02 が nullable 版・EP-03・04 が厳格版(ワイヤ形式は B のまま)。B に「EP-03・04 は非 null」と明記したい
2. B 2.4・3.3: `ttl_days`・`ttl_seconds` の `exclusive`・`required` の `field` 名が未指定。例に合わせて `ttl_days`
3. B 2.12・3.3: 違反の返し方を型と範囲の 2 段にした(形の違反があれば範囲は見ない)。B の例は排他と範囲を併記
4. B 2.12: `connector_config` 内の `NaN`・無限大を 400(`connector_config` の `type`)にした。B に記載なし
5. B 2.12 と実装: `job_id` に改行(`%0A`)を含むと Starlette の `Mount` の正規表現で 404 `not_found`(400 `format` に届かない)。EP-07 でも EP-10 と同じ。どちらも Crawler には届かない
6. C 4.2・D 5.0: `lock_state` を読む時刻は、リクエスト先頭ではなく Crawler の応答後
7. `ratio_threshold_percent` に `10**400` を送ると `range` でなく `type`

## P7 への要対応(重要)

- **OpenAPI の `requestBody` が出ない**: 本文を依存関係(`read_body_as`)で読むため、`POST /sources`・`PUT /sources/{id}`・EP-06 の operation に `requestBody` がなく、`PUT /sources/{source_id}` などの `responses` に `422` が出る。型生成の入力に関わる。P7 で `requestBody` の宣言(`openapi_extra` で `RegisterSourceBody` などを参照)と 422 の除去が必要

## 未対応事項・次にやること

- P6(EP-13・プローブ)、P7(OpenAPI の `requestBody`・`operationId`・tags・README・スモーク)
- 実 Crawler に対する EP-03〜08 の通しは P7 のスモークで行う
- レビュー: プランの R-C は P7 完了後だが、P5・P6 が大きくデータ削除の中継を含むため、**P6 完了後に R-C(前半: P5a・P5b・P6)を実施し、P7 後に R-C(後半: P7・全体の最終確認)を実施する**(プランの区切りの細分化。レビュー範囲を狭めて見落としを減らす目的で、レビュー対象の追加はない)
