# 0016 P5 レビューと指摘対応

日付: 2026-11-12 / 対象: 0015(P5)/ レビュー: code-reviewer、test-reviewer / 修正: code-implementer
比較基準: HEAD c065b9e(`apps/indexer` は未コミットの新規ファイル全体)

## レビュー結果

### code-reviewer(修正後可。Critical なし、Important 2件)
- 実 uvicorn に生ソケットを送る(Content-Length 超過・チャンク超過・NaN・BOM・深いネスト・不正パス)、base64 と pydantic の strict 挙動、ローカルの偽 OpenSearch(404 を返すだけの HTTP サーバ)に対する opensearch-py のログ取得、まで実測して確認した
- **Important**: 通常運用の OpenSearch 404 で、ID を含む URL が WARNING として出る(R9・ログ洪水)。`opensearch` ロガーを WARNING 以上に固定しているだけで、opensearch-py の `log_request_fail` 自体が WARNING のため、2xx 以外の応答(ignore 指定なしの 404 を含む)ごとに `GET http://host/loreley-jobs/_doc/lock-<source_id> [status:404 ...]` がフル URL で出る。「メンテナンスフラグなし」は正常状態で、判定・バッチ・要約のたびに出る。`SecretRedactionFilter` では防げない
- **Important**: 想定外の `ValueError` がログなしの 400 `invalid_request`(retryable=false)になる(ドメインの形式不正以外の ValueError も同じ経路。Crawler にはリクエスト不正としか伝わらずジョブが恒久 `failed`、サーバ側の診断手がかりがない)
- Suggestion: バッチ合計に、デコードしない(上限超過)文書の推定サイズも数えている / サイズ設定どうしの整合を `Settings` で検証していない / ID に制御文字(改行)を許している(偽ログ行の注入)/ 500 のログがクラス名だけで原因を特定できない / メンテナンスフラグの不正 WARNING に抑制がない / lifespan の停止処理で片方が例外を投げるともう片方が止まらない
- Nitpick: `ClientDisconnect` が ERROR 扱いの500 / `log_level` が大文字のみ / `status_code=202` の二重指定 / `ready` ゲートは実運用では到達しない二重防御 / `fastapi>=0.115` の下限が未検証
- 0015 の「ユーザー未承認の判断」の妥当性評価: DELETE の `lock` をボディで受ける=妥当(api 4.6 の例がボディ形式。リスクは Crawler 側の HTTP クライアント)/ `skipped_count` を型だけ検証して使わない=妥当(K25 のダイジェストは ID 一覧から決まる)/ 孤立サロゲートの分担=妥当(ただしファイル名由来のものは `external_id`(パス)にも入り `document_id` を計算できず全体 400 のまま。Crawler 設計の確認事項として README に)/ ID 長の仮値=妥当 / `content_hash` を小文字64桁に限定=許容(Crawler と突き合わせ。大文字は 400)/ 起動前の全パス 503=妥当(ただし uvicorn の lifespan 完了前は接続自体を受けないので実効は限定的)/ 追加設定=妥当 / **`httpx2`=妥当。レビュアーが PyPI で確認**(`pydantic/httpx2` の 2.16.0、2026-10-21。starlette の TestClient が要求する。dev グループのみで本番イメージには含まれない。`uv.lock` のハッシュも固定)/ 許可表の変更(config→api、httpx2)=妥当

### test-reviewer(おおむね十分。Critical なし、Important 5件)
- **Important I1**: ログ検査が実 OpenSearch クライアントのログ経路を通らず(インメモリ fake のみ)、実機では URL が WARNING に出る(スクラッチで再現)
- **Important I2**: `RESTRICTED_LOGGER_NAMES` の `opensearch.trace` が実在のロガー名(`opensearchpy.trace`)と違い、テストも同じ誤名で通る
- **Important I3**: `indexer_records()` が `loreley_indexer*` 以外のロガー(uvicorn・starlette・anyio・asyncio・opensearch など)を検査対象から除外している(`logging.getLogger('uvicorn.error').debug('body %r', body)` の追加が生存)
- **Important I4**: 起動順テストで `ready` を立てる位置(ワーカー起動の前後)と停止時の `ready.clear()` が固定されていない
- **Important I5**: Content-Length の不正値のテストが 400 であることしか見ておらず、検査(`isdigit`)が無くても通る
- Suggestion S1〜S8: base64 不正形の網羅、原本上限の +1 境界、検証エラーの件数上限、日時・整数の極端値、メンテナンスフラグ不正値の一覧(`""`・`[]`・`0.0`)、ログテストの期待ステータスの固定、非同期ログの取りこぼし、AST によるログ呼び出し検査の変数名依存。Nitpick N1〜N3(重複、許可表の `httpx2`、スレッド名での検査)
- 自前のミューテーション(スクラッチ上で32件、killed 22 / survived 10)。実 OpenSearch クライアントのログ再現(ローカル HTTP スタブ)で I1 を確認
- fail-closed のテストは削除(判定前・バッチ前・バッチ間)・要約(生成前・生成中)の7形式すべてで止まることを確認。TTL の追加条件のテストがないことも確認(ユーザー判断どおり)

## 指摘対応(code-implementer。メインが検証を再実行して確認)

検証: `uv run pytest` → **2032 passed**(P5 実装時の 1774 から +258。3回連続で同数、約31秒)。`ruff check` 全通過、`ruff format --check` 187 files already formatted、`uv lock --check` OK。`apps/indexer` と `agent_tasks` 以外の変更なし。ローカル HTTP スタブ関連の84件を単独で5回連続実行して安定(ポートは自動割当て、`finally` で shutdown と close)。ミューテーションはスクラッチのコピー上で約20種類すべてテストが失敗(検出)

### 実装
- **A1(Important)**: 修正前に実クライアントとスタブで再現(404・400・503・切断のすべてで ID 入り URL の WARNING とトレースバック)。**実在ロガー名**(opensearch-py 3.2 のソースから調査: `opensearch`・`opensearchpy`・`opensearchpy.trace`・`opensearchpy.helpers`、`urllib3`。誤名 `opensearch.trace` は実在しない)を **ERROR に固定**。`common` は R2 により opensearchpy を import できないためロガー名は文字列で持ち、ライブラリとの一致はテストで検査する(`logger.name` の実体、ソース中の全 `getLogger("...")` の実効レベルが ERROR 以上、`urllib3.connectionpool`)。あわせて通常経路の 404 に **`ignore=404`**(`client_calls.IGNORE_NOT_FOUND`。`get`・`delete`、`raise_last_seen_at` の `update`)を渡し、ライブラリが失敗扱いしないようにした(`found:false`/`result:not_found` は `NotFound`、`index_not_found_exception` は従来どおり全体異常、JSON でない本文は `http_404` の想定外応答。判別は既存の `classify_failure` に `NotFoundError(404, "", 本文)` を通す)。実際には ERROR 固定だけで漏れは止まり、`ignore=404` は通常経路の二重防御
- **A2(Important)**: ValueError ハンドラが `domain rejected the request: error=<クラス名> origin=<dir/file.py:行 関数名>` の WARNING を出す(値・メッセージ・ローカル変数は出さない)。500 のログも `request failed unexpectedly: error=X [error_type=Y] origin=...`。**専用例外 `InvalidInputError` への切り替えは P2〜P4 の変更を伴うため見送り**(ドメインの形式不正以外の ValueError は 400 のまま。warning の `origin` が手がかり)
- **A3**: 上限超過でデコードしない文書をバッチ合計に数えない(5000バイトの原本は `max_batch_bytes`=2048 を超えても 400 にならず文書単位 `oversize`)/ `Settings` に `max_raw_bytes ≤ max_batch_bytes` と `max_batch_bytes×4 ≤ max_request_body_bytes×3` の整合検証(既定 20/64/100MiB と上限 100/256/512MiB は矛盾しない)/ ID の制御文字(0x00〜0x1f・0x7f)を `id_invalid_character` で拒否(`external_id` も対象。空白・日本語・U+0080 以上は許可)/ 500 のログに origin と `error_type` / メンテナンスフラグの不正 WARNING をリーダーごと・1回だけ(以降 DEBUG。判定は毎回 True)/ lifespan を `ExitStack` による LIFO 停止(`ready.clear`・`summarization.stop`・`deletion.stop`・接続のクローズ。片方が例外でも残りが実行される)/ `ClientDisconnect` は 400 `InvalidRequestError`(ERROR を出さず 500 を試みない)/ `log_level` は大文字小文字非区別 / 202 の二重指定を `Response(202)` に一本化

### テスト
- 新規 `tests/infrastructure/opensearch/test_log_leak.py` + `http_stub.py`(実クライアントを 127.0.0.1 のスタブにつなぎ、9種の応答(404 文書なし・`document_missing`・索引なし、400、409、503、切断、200×2)× アダプタの全16メソッドで、センチネル(ID・本文・エラー reason・パスワード)が出力文字列にも `LogRecord`(引数・`exc_info`)にも出ないこと。通常の 404 経路はログがゼロ)
- I3: 除外を `httpx`・`httpx2`・`httpcore`・`httpcore2` に絞り、残りの全ロガーを検査(`crawl_id` の許容は `crawl_runs` のロガー限定)。I4: `DeletionManager.start`・`Summarization.start` の呼び出し時点で `/healthz` が 503、停止中・停止後も 503。I5: `-5`・`+5`・`""`・空白・`1e3`・`0x10`・`1_0`・`5.0`・アラビア数字・全角数字を固定メッセージ付きで parametrize(latin-1 上付き文字は `read_limited_body` の直接テスト)
- S1〜S8: base64 不正形(改行・CRLF・`====`・非 ASCII・URL セーフ・パディング後データ・途中の `=`)と `raw_content=""`、原本上限の ±境界(1022〜1027)、エラー13件で10件に打ち切り `; and 3 more`、日時・整数の極端値(`2**63`、5000桁、BOM、DELETE のチャンク転送・ボディなし)、フラグ不正値に `""`・`[]`・`{}`・`0.0`・`1.0`、モードごとの期待ステータス表(ok・invalid・domain-value-error・conflict・unavailable・unexpected)、終端まで待ってからログ検査、AST 検査を `getLogger` の代入先の名前と属性名ベースに。N1〜N3: `wait_until` を `tests/fakes/waiting.py` に統合・重複削除、`httpx2` と config→api の入口経由テスト、`worker_threads` fixture

## ユーザー未承認の設計判断(追加分)

1. `common/errors.py` に基底クラス `UnexpectedResponseError(IndexerError)` を新設し、`OpenSearchUnexpectedResponseError` をその継承にした(api は infrastructure を import できないため。公開 I/F の追加であって変更ではない)
2. `Backends.close_connections`(既定は何もしない)と `infrastructure.opensearch.close_clients` を新設(`main.py` は opensearchpy を import できないため infrastructure に置いた)
3. `ignore=404` を `get`・`delete` に加えて `update`(`raise_last_seen_at`)にも付けた
4. `opensearch`・`urllib3` などの制限レベルを WARNING から **ERROR** に変更した(ライブラリ由来の警告(接続の死活など)も出なくなる)
5. ログ文言を変更した(診断情報の追加)。運用の監視で文言を拾う場合は影響する
6. 設定の整合検証により、`max_raw_bytes` を 64MiB より大きくするには `max_batch_bytes`(と `max_request_body_bytes`)も上げる必要がある
7. `ClientDisconnect` は 400 `invalid_request` 扱いにした(応答は届かない)

## P6 の README への申し送り(追加分)

- Crawler 向け契約: `max_batch_bytes` はデコードする文書の合計の上限で、超えると一括 400 / `max_raw_bytes` 超過の文書は文書単位の `oversize`(base64 がボディ上限内の場合)/ base64 でリクエストボディが `max_request_body_bytes` を超える原本は `oversize` にならずリクエスト全体が 400 / 整合条件 `max_raw ≤ max_batch`、`max_batch×4/3 ≤ max_request_body_bytes` / `content_hash` は小文字64桁 hex のみ受理(大文字は 400。Crawler 側の算出と突き合わせ)/ ID は制御文字を含められない(`external_id` も対象。改行を含むファイル名があると全体 400)/ 孤立サロゲートがファイル名由来で `external_id`(パス)に入ると全体 400 のまま / DELETE は `lock` を JSON ボディで運ぶ(チャンク転送も可。ボディなしは 400)
- 運用: `HEALTHCHECK` の `start_period`(起動時の整理が終わるまで `/healthz` を含む全パスが 503)/ `log_level` は大文字小文字非区別 / opensearch-py と urllib3 のログは ERROR 以上しか出ない / ログに 500 の `origin`(ファイル:行 関数名)が出る / ドメインの形式不正以外の `ValueError` は 400 のままで warning の `origin` が手がかり
- 既知の制限として、前回までの申し送りどおり TTL 0・負値の誤設定リスク(受け入れ済み)、要約の再開遅延と先頭30,000文字、判定時の `MalformedRecordError` が先頭を詰まらせる件、巨大 HTML の処理時間

## 見送り・持ち越し

- 専用例外 `InvalidInputError` への切り替え(P2〜P4 の変更を伴う)
- U-31(実機)。特に `ignore=404` で返る 404 の本文の形(`found:false`、`result:not_found`、`document_missing_exception`、`index_not_found_exception`)は、opensearch-py の挙動とスタブで確認したが実機では未確認
- `ClientDisconnect` は ASGI 直叩きのテストで確認したが、実際の uvicorn 経由での切断は未確認
- `test_failures_of_the_backends_never_log_a_value` は、ワーカーの非同期ログを待つ処理を足していない(S7 の対象外)
- コミット未実施

## 次のアクション

再レビュー(code-reviewer: A1〜A3、test-reviewer: Important 5件の解消と追加テスト)。解消確認後、P6(Dockerfile・README・最終検証)へ。
