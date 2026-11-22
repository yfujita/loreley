# 0017 P5 再レビューと完了

日付: 2026-11-12 / 対象: 0016 の修正後の P5 / レビュー: code-reviewer、test-reviewer(再レビュー)/ 修正: code-implementer
比較基準: HEAD c065b9e(`apps/indexer` は未コミットの新規ファイル全体)

## 再レビュー結果

### code-reviewer(修正後可。Critical なし、Important 1件)
- A1(通常運用の 404 で ID を含む URL が WARNING に出る)= **解消**。インストール済みライブラリ(opensearch-py 3.2.0・urllib3 2.8.0)の `getLogger` を全件実読し、実在名(`opensearch`・`opensearchpy.trace`・`opensearchpy.helpers`、親の `opensearchpy`、`urllib3`)に取りこぼしがないことを確認。ルート DEBUG で 404 の各形・200・500・503・接続拒否を試して漏れなしを実測。ライブラリ側に `logger.error`・`exception` の呼び出しはなく、ERROR 固定で情報は失われない
- A2(想定外の ValueError がログなしの 400)= **解消**。`describe_origin` は最内フレームの `親ディレクトリ/ファイル:行 関数名` だけで、メッセージ・引数・ローカル変数は出さない。500 のログは `error`・`error_type`・`origin` のみ、middleware が例外を再送出しないので uvicorn が traceback を出さない。専用例外化の見送りは MVP として妥当
- A3 = ほぼ解消。バッチ合計の数え方は正しい(`_check_total_size` と `prepare_raw_content` が同じ条件 `estimated > max_raw` を使う)、整合検証の式は既定値・上限値と矛盾しない、フラグ WARNING は毎回 `True`(fail-closed 維持)、lifespan は LIFO 停止(起動途中の失敗でも後始末が連鎖する)、`ClientDisconnect` は 400
- **Important(新規。`ignore=404` の導入による退行)**: 404 の本文が非 JSON・未知の Content-Type(プロキシ・Ingress の `text/html` など)・壊れた JSON のとき、`ignore=404` を付けると opensearch-py はエラー処理を通さず transport が通常の応答として本文をデシリアライズするため `SerializationError` になり、`TransportError` ではないので `except TransportError` に当たらず、fetch・delete・update のすべてで素通りした。`ignore` なしなら `TransportError(404)` → `Rejected("http_404")` になる。削除 executor の `Rejected` に対する有界リトライ(`delete_error_retry_attempts`)が効かず、設定不備が続くとバックオフしながら永久に再試行する。壊れた JSON の `SerializationError` の `str()` には生の本文が入る(現状 `str()` を出力する箇所はなく R9 の漏洩は起きていない)。スタブが常に正常な JSON を返していたためテストで見つからなかった。0016 の「JSON でない本文は `http_404` の想定外応答」の記述は、空本文・配列・文字列の場合にしか当たらない
  - 提案 (a): `ignore=404` と関連コードを外して例外経路(`classify_failure` のみ)に戻す(ERROR 固定で漏れは止まることを実測済み)
- Suggestion: `external_id` の制御文字拒否は、`external_id` の値がログに出る経路がなく(応答 JSON に入るだけで改行はエスケープされる)ログ注入対策として効かず、Linux では改行・タブを含むファイル名も正当で、1件でバッチ全体が恒久 400 になる → `external_id` は空・長さ・NUL のみにする。`source_id`・`crawl_id`・`lock.*`・パス ID の拒否は維持
- Nitpick: メンテナンスフラグ不正 WARNING が再武装されない(判定は常に `True` で fail-closed に影響なし。任意)/ Content-Length が4300桁超だと `int()` が ValueError(Python 3.12 の桁数制限)になり誤解を招く warning が出る(結果は 400 で正しい)
- 0016 のユーザー未承認の追加は、`UnexpectedResponseError` を common に置く判断・`close_clients`・ERROR 固定・ログ文言変更・整合検証・`ClientDisconnect` の400扱いをいずれも妥当と評価(`ignore=404` の `update` への適用は上記 Important の対象)

### test-reviewer(Critical なし、前回 Important 5件は解消。新規 Important 2件)
- 前回 Important I1〜I5 = **すべて解消**(スクラッチ上のミューテーションで各テストが退行を検出することを確認: `RESTRICTED_LOG_LEVEL` を WARNING に、`opensearch`・`urllib3` を制限対象から外す、`getLogger("uvicorn.error").debug("body %r", ...)` の追加、`ready.set()` を `deletion.start`/`summarization.start` の前へ、`isdigit()`/`isascii()` の単独化 など)。ローカル HTTP スタブのテストは構造・後始末・安定性とも良好(6並列でも46件すべて通過。ポート自動割当て、`finally` で shutdown・close・join、ライブラリを通ったことを毎回確認)
- **Important IM1**: `ignore=404` が削除の安全性(NotFound の扱い)を変えていないことの固定が `delete` 系にない(`delete_document` の末尾を `return NotFound()` に固定しても2032件が全件通過)。`delete` は `result:not_found` しか検証せず、`index_not_found_exception`(全体異常)・`document_missing_exception`・非 JSON(`http_404`)を固定していない。索引が消えている状態の削除を「すでに消えている」と誤判定すると、実在しない文書の削除を成功として数える恐れがある
- **Important IM2**: ログ漏洩テストの「全メソッド」が手書きの dict で、`SearchIndexRepository.__abstractmethods__` などとの一致を見るメタテストがなく、アダプタにメソッドが増えても黙って漏れる
- Suggestion: S1 弱いアサーション(`is not None`、文字列比較)/ S2 合計への算入境界(`>` を `>=` にしても生存)/ S3 `summarization.stop` の登録位置を `start()` の後ろに動かしても生存 / S4 応答種別(401・403・429・非 JSON 本文)がスタブにない
- Nitpick: `record_text` の重複、`opensearchpy.trace` の param が実質空振り(`propagate=False`)・ERROR の陽性対照がない、`serve_forever` のポーリング 0.5秒と `join` 失敗の黙殺、実クライアントを閉じていないテスト

## 指摘対応(code-implementer。メインが検証を再実行して確認)

検証: `uv run pytest` → **2083 passed**(0016 時点の 2032 から +51。3回連続で同数、約24秒)。`ruff check` 全通過、`ruff format --check` 189 files already formatted、`uv lock --check` OK。`apps/indexer` と `agent_tasks` 以外の変更なし。**メインの確認**: `src` に `ignore=`・`IGNORE_NOT_FOUND`・`classify_ignored` の記述が残っていない。実装担当のミューテーション確認は12件すべて KILLED(生存0): `delete_document` の戻りを `NotFound()` に固定、`delete`・`get`・`update` に `ignore=404` を再追加(いずれも `SerializationError` の漏れで失敗)、404 をすべて `NotFound` にする、`index_not_found_exception` を全体異常から外す、`>` を `>=` に、`summarization.stop` の登録を `start()` の後ろへ、`external_id` の制御文字拒否の復活、Content-Length の桁数ガード除去、`opensearch` ロガーの ERROR 固定を外す、`fetch` の NotFound 時の None 返却の除去

### 実装
- **`ignore=404` を全面撤回**(`get`・`delete`・`update`)。`IGNORE_NOT_FOUND`・`classify_ignored_not_found` を削除し、404 は例外経路の `classify_failure` のみで分類する(404 の本文が非 JSON・壊れた JSON でもライブラリは `TransportError`(`NotFoundError`)にするため、削除 executor の `Rejected` に対する有界リトライが効く。fail-closed は維持: `index_not_found` は全体異常、本文を判別できなければ `Rejected`)。**0016 の判断3(`ignore=404` の追加)は撤回**。通常運用の 404 でライブラリが WARNING を出す件は opensearch/opensearchpy/urllib3 の ERROR 固定(0016 の判断4、維持)で担保し、`test_the_normal_not_found_path_logs_nothing`(ログ出力ゼロかつ `LogRecord` ゼロ)で固定
- `external_id` は空・4096バイト超・NUL(`compute_document_id` が従来どおり拒否)のみの検査にし、制御文字(改行・タブなど)を許可。**0016 の ID 制御文字拒否のうち `external_id` を対象にした部分は撤回**。`source_id`・`crawl_id`・`lock.*`・パス ID の制御文字拒否は維持
- Content-Length が20桁を超えるときは `int()` の前に `BODY_TOO_LARGE`(400)

### テスト
- IM1: `test_not_found_bodies.py`(例外経路。本文6種(`found:false`・`result:not_found`・`document_missing_exception`・`index_not_found_exception`・非 JSON の html・`{}`)× 6操作(`repository.fetch`・`fetch_for_deletion`・`store.fetch`・`repository.delete_if_unchanged`・`store.delete`・`raise_last_seen_at`)の parametrize。文書なし系は `NotFound`(fetch 系は `None`)、`index_not_found_exception` は `OpenSearchUnavailableError`、html と `{}` は `Rejected("http_404")`(fetch 系は想定外応答の例外))、および実クライアント+スタブ(`test_log_leak.py` に `html_404`・`broken_json_404`・`unauthorized`(401)を追加。書き込み3種は `Rejected("http_404")`、取得3種は想定外応答の例外、例外の `traceback`・`repr`・`str` とログに生の本文が出ない、401 は `Unavailable(http_401)`、実クライアント経由の 200 の削除は `Deleted`)
- IM2: `test_every_repository_method_is_exercised_by_the_log_checks`(`operations()` のキーと `__abstractmethods__` の一致)。`SEARCH_INDEX_CALLS`/`STORE_CALLS` の共有 helper 化は引数が異なるため見送り
- S1〜S4: `== NotFound()` に強化(`raise_last_seen_at` と `store.fetch("maintenance")` も固定)、`max_raw_bytes` ちょうどの2件で `max_batch_bytes` が 2048 なら 200・2047 なら 400、1本目のスレッドを起動してから失敗する `start` の fake で `events == ["cleanup","deletion.start","summarization.stop","deletion.stop"]` と `worker_threads() == []`、`StubResponse` に `raw`・`content_type` を追加し 401 と `text/html` の404・壊れた JSON を追加
- Nitpick: `record_text` を `tests/log_records.py` に共通化、`opensearchpy.trace` の空振り param を削除(理由をコメント)し ERROR の陽性対照 `POSITIVE-CONTROL` を追加、スタブの `poll_interval=0.01` と `join` 失敗の検知、実クライアントを `finally` で閉じる。Content-Length 21・100・5000 桁のテスト、`external_id` の改行・タブ・`\x1b`・`\x7f` が通る e2e、NUL でバッチ全体 400・書き込みゼロの e2e

## 判断

- P5 は完了。code-reviewer の Important(`ignore=404` の退行)はレビュアー提案 (a) で解消(P1 でレビュー済みの例外経路への復帰)、test-reviewer の Important(IM1・IM2)はテスト追加で解消。実装担当のミューテーション12件がすべて失敗し、メインが `src` に `ignore=404` が残っていないことを確認済み
- 最後の修正(撤回+テスト追加)は、再々レビューを行わず、メインが検証コマンドと `src` の確認で確かめた。撤回は P1 で 2回レビュー済みの経路に戻す変更で、追加されたテストはミューテーションで検出力が確認されているため
- タスクレビュー(task-reviewer)で、P5 の最終状態を全体として確認する

## ユーザー未承認の設計判断(0016 からの変更)

- `ignore=404` は全面撤回(0016 の判断3は撤回)。ERROR 固定(0016 の判断4)は維持
- `external_id` の制御文字拒否は撤回

## P6 の README への申し送り(0015・0016 からの変更点を含む)

- Crawler 向け契約: `max_batch_bytes` はデコードする文書の合計の上限で、超えると一括 400 / `max_raw_bytes` 超過の文書は文書単位の `oversize`(base64 がボディ上限内の場合)/ base64 でリクエストボディが `max_request_body_bytes` を超える原本は `oversize` にならずリクエスト全体が 400 / 整合条件 `max_raw ≤ max_batch`、`max_batch×4/3 ≤ max_request_body_bytes` / `content_hash` は小文字64桁 hex のみ受理(大文字は 400。Crawler 側の算出と突き合わせ)/ **`external_id` は制御文字(改行・タブなど)を許可し、空・4096バイト超・NUL のみがリクエスト全体の 400**。`source_id`・`crawl_id`・`lock.*`・パス ID は制御文字を拒否 / 孤立サロゲートがファイル名由来で `external_id`(パス)に入ると全体 400 のまま / DELETE は `lock` を JSON ボディで運ぶ(チャンク転送も可。ボディなしは 400)/ Content-Length の極端に長い桁数は「ボディ過大」の 400
- 運用: `HEALTHCHECK` の `start_period`(起動時の整理が終わるまで `/healthz` を含む全パスが 503)/ `log_level` は大文字小文字非区別 / opensearch-py と urllib3 のログは ERROR 以上しか出ない / ログに 500 の `origin`(ファイル:行 関数名)が出る / ドメインの形式不正以外の `ValueError` は 400 のままで warning の `origin` が手がかり
- U-31(実機)の確認事項: 404 の本文の形(`found:false`・`result:not_found`・`document_missing_exception`・`index_not_found_exception`)が例外経路で期待どおり分類されること(特に `update` の 404 の本文)
- 既知の制限(0013・0014 から): TTL 0・負値の誤設定リスク(受け入れ済み)、要約の再開遅延(最悪 `summary_rescan_max_interval_seconds`)と先頭30,000文字、判定時の `MalformedRecordError` が先頭を詰まらせる件(WARNING 監視)、巨大 HTML の処理時間(約40秒)、メンテナンスフラグ形式の再確認(fail-closed)

## 見送り・持ち越し

- メンテナンスフラグ不正 WARNING の再武装、`SEARCH_INDEX_CALLS`/`STORE_CALLS` の共有 helper 化、専用例外 `InvalidInputError`(P2〜P4 の変更を伴う)
- U-31(実機)。実 uvicorn 経由の `ClientDisconnect` は未確認
- コミット未実施

## 次のアクション

P6(Dockerfile・README・最終検証)を `code-implementer` に依頼する(申し送りは 0015・0016・0017・0014・0013 ほか)。レビューは code-reviewer(Dockerfile)+ document-reviewer(README・作業記録)。その後、タスクレビュー(task-reviewer)を実施し、完了報告前にユーザーへ未承認事項を確認する。
