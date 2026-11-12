# 0008 P2 レビューと指摘対応

日付: 2026-11-11 / 対象: 0006(P2a)・0007(P2b)/ レビュー: code-reviewer、test-reviewer / 修正: code-implementer
比較基準: HEAD c065b9e(`apps/indexer` は未コミットの新規ファイル全体)

## レビュー結果

### code-reviewer(修正後可。Critical なし、Important 3件)
- **Important A1**: メンテナンスフラグ中、LLM の結果を毎回捨てて再生成し続ける(フラグ確認が書き込み直前のみ。再走査が最短60秒ごとに全 pending を再生成)
- **Important A2**: 要約の自動再試行が時間方向に無制限(K54(3)・案12の趣旨に反する。`failed` 未実装の代わりに無制限化しない方針のはずが、LLM 停止中は最短60秒ごとに全 pending を叩き続ける。`summary_enabled=True` かつ DisabledLlmClient の設定食い違いでも同じ)
- **Important A3**: メタデータ(title・path・url・external_id)の孤立サロゲートで、バッチ全体が 500/400 になり再送でも直らない(CP932 のファイル名を Linux でマウントすると surrogateescape で実際に生じうる)
- Suggestion: `last_seen_at` の「古い」判定がミリ秒切り捨てと食い違う / 停止要請で試行自体が中断されない / 巨大入力の処理時間(20MiB: テキスト約3.6秒、小要素大量のHTML約40秒、PDFは全ページ処理) / 文字コード判定(CP932 が UTF-16・EUC-JP を弾かず文字化けで索引化)
- Nitpick: 制御文字 `\x0b`/`\x0c` の除去で語が連結 / pypdf ロガー設定が import 時の副作用 / 「最初の失敗以降を打ち切る」処理が2か所に重複 / stop() 後の再 start 不可 / `close()` 後も `submit` を受け付ける
- 確認済み: 登録の骨格が設計と1対1(ロック確認→サイズ→抽出→取得→判定→書き込み)、409 読み直しの境界、K30、受理条件の判定順、HTML 抽出は20,000件のファジングと10万段ネストで例外なし、PDF 不正入力4種は `extract_failed`
- 0007 の「ユーザー確認が必要な点」の妥当性評価: **判断8(連続20件打ち切りを Indexer に実装しない)=妥当**(arch 4.4・api 3.5・module 4.3「やらないこと」で Crawler 側の規則)/ **判断12(生成依頼を ID のみに)=妥当・承認を推奨**(arch 7.4 の文言は満たされる。逸脱は module 4.3 の内部入口の記述のみで次の版で直せる)/ **判断17(`summary_input_max_chars`)=妥当だが制限の明記が必要**(先頭30,000文字だけを要約する実装になる。仮値であり U-9 のモデル選定後に見直す旨を README に残す)

### test-reviewer(概ね十分。Critical なし、Important 4件)
- 0007 の arch テストID対応表は中身まで実テストと一致。P2 の範囲で抜けている C/E/L/D ケースなし
- **Important I1**: 本文同一判定で `text_hash` が見られていない(C-3/C-12 の後半。`_body_is_unchanged` を content_hash のみにしても生き残る)
- **Important I2**: ワーカーの再走査の失敗を隔離するテストがない(try/except を外しても生き残る)
- **Important I3**: R9 のログ漏洩テストが一部のみ(pypdf ロガー抑止・ワーカーの例外メッセージ非出力が固定されていない)
- **Important I4**: `test_close_wakes_a_waiting_taker` が起床を検証していない(`notify_all()` を外しても通る)
- Suggestion S1〜S6、Nitpick N1・N2(抽出失敗の完全一致、PDF の細部、現実の再送テスト、要約まわりの小さな穴、起動停止テストの頑健性、重複と配置、表の過大表記など)
- ミューテーション(レビュアーが22通り): 8件検出・14件生存 → 上記 Important/Suggestion の根拠

## 指摘対応(code-implementer。メインが検証を再実行して確認)

検証: `uv run pytest` → **863 passed**(P2b 後の 782 から +81。3回連続で同数、約5秒)。`ruff check` 全通過、`ruff format --check` 117 files already formatted。`apps/indexer` と `agent_tasks` 以外の変更なし。実装担当のミューテーション確認は21件すべて検出(当初2件生存 → テスト修正で検出)。

### 実装(A1〜A4)
- **A1**: `process()` が文書を読んで pending と確認した後、LLM 呼び出し前にもメンテナンスフラグを確認し、立っていれば LLM を呼ばず `PAUSED_BY_MAINTENANCE`。書き込み前の確認も残す。pending でない依頼はメンテナンス中でも DISCARDED。トレードオフ: メンテナンス解除後、最悪で上限間隔(3600秒)まで再走査を待つ場合がある
- **A2**: 成果なし(走査間に WRITTEN が1件もない)の走査が続くたびに再走査間隔を2倍ずつ上限まで伸ばす(`min × 2^n`、60/120/240/480/600…)。成功でリセット。起動時の最初の走査は常に即時。新設定 `summary_rescan_max_interval_seconds`(既定 3600、le 86400、min 以上を検証)
- **A3**: `_register_one` で oversize 確認の後・抽出の前に title・mime_type・path・url が UTF-8 にエンコードできるか検査し、できない文書は `DOCUMENT_REJECTED`(固定メッセージ)。`external_id`/`source_id` の孤立サロゲートは `compute_document_id` が固定メッセージの素の `ValueError` にする(バッチ全体 400)
- **A4**: `last_seen_at` 判定をミリ秒に揃えた / 停止要請で `_with_attempts` の2回目以降の試行を打ち切る(`should_stop`) / PDF は正規化後の長さが `max_content_bytes` を超えた時点でページループを打ち切る / `decoding.py` は UTF-16/32 の BOM と CP932 結果の私用領域(U+E000〜U+F8FF)を `UNDECODABLE_TEXT` にした(EUC-JP の誤判定は完全には防げない旨を docstring とテストで固定) / `normalization.py` の文字ごとのジェネレータを正規表現に置換(全コードポイントで旧実装と同一出力を確認、20MiB テキスト 約3.6秒→約0.46秒) / service・worker の docstring に二重 start・stop 後の再 start 不可を明記

### テスト(I1〜I4、S1〜S6、N2)
- I1: `text_hash` のみ変化→要約を引き継がず pending(`test_changed_text_hash_with_the_same_content_hash_resets_the_summary`)
- I2: 再走査の失敗が `run_once` から漏れず、再要請される
- I3: PDF は pypdf ロガーのレコードが0件・原本の先頭バイトがログに出ないこと(依頼どおりの `"SENTINEL"` 検査では pypdf が先頭5バイトしか出さず検出できなかったため `"SECRE"` とレコード0件に変更)、ワーカーは例外メッセージを出さず ID のみ出すこと
- I4: `take(30)` と `join(5)` 後の `not is_alive()`。待ち状態の保証はテスト内の `threading.Condition` 派生(`queue._condition` という private 名への依存が1か所)
- S1〜S6: 抽出失敗の完全一致、owner パスワードのみの暗号化PDF・2ページPDF・HTML `UnparsableHtmlError`(monkeypatch。本体は防御として残す)、現実の再送テスト(`before(ops.CREATE, ...)` で別スレッドから同じ registrar を起動→待たされ、完了後に `UNCHANGED`、CREATE 1回・409 0回)、`summary_status` なしの既存文書・`needs_rescan`・失敗後に依頼が積まれない、起動停止テストを `threading.enumerate()` ベースに、フィクスチャ・ヘルパの集約(`summary_registrar`、`register_one`、`source_of`/`status_of`、`CRAWL_STARTED_AT_TEXT`)、`__post_init__` 検証テスト
- N2: `last_seen` のメッセージ完全一致、NUL 拒否のメッセージに実在の値が出ないこと
- BOM 判定は CP932 が BOM を私用領域文字にデコードするため私用領域判定と冗長だが、`test_decoding.py` で私用領域判定を無効化しても `None` になることを固定

## ユーザー未承認の追加・判断(要確認事項。STATUS.md に記録)

0007 の判断8・12・17(上記レビューで妥当と評価)に加え、今回の修正で次を追加した。いずれもプラン§3「案に近い側に倒す」「未決の数値は設定可能な仮値(上限付き)」の範囲だが、承認は未取得:
1. 新設定 `summary_rescan_max_interval_seconds`(既定 3600、le 86400)。バックオフ倍率2倍は固定で設定化していない。「成果」の定義は「走査間に WRITTEN が1件以上」
2. メタデータ検査の対象に `mime_type` を追加(依頼は title・path・url。同じ JSON 化の経路で落ちるため)
3. `DOCUMENT_REJECTED` の基本メッセージを「the search index rejected the document」から「the document was rejected」に変更(検索インデックス由来でない拒否にも使うため。OpenSearch 由来の `(error_type)` 付加は従来どおり)
4. 検査順は oversize → メタデータ検査 → 抽出
5. PDF の打ち切り判定は生の長さでなく正規化後の長さ(生だと本文が収まるPDFを `truncated=true` で欠落させるため)
6. `SummaryProcessor` に `should_stop` を追加

## P5 への申し送り(追加)

- `external_id`/`source_id` の孤立サロゲート(JSON の `\ud800` 形式)は、固定メッセージの素の `ValueError`(入力値なし)として出る。NUL と同じくリクエスト全体の 400 にする。JSON 由来の lone surrogate を 400 で拒否するのが本来の置き場(Indexer 側は防御)
- `crawl_id`・`lock.owner`・`lock.job_id`・`content_hash` など他の文字列フィールドの検査はドメイン側では行っていない。API 層で形式検証する
- title・mime_type・path・url の孤立サロゲートは文書単位の `document_rejected` として処理される
- 巨大 base64 のデコード前サイズ判定、日時パース、結果型→JSON 写像は従来どおり P5 の責務(0007)
- README に、要約入力が先頭 `summary_input_max_chars`(既定30,000)文字までで仮値であること、メンテナンス解除後の再開が最悪で `summary_rescan_max_interval_seconds` 遅れうることを記載する(P6)

## 未対応事項・持ち越し

- 小要素が大量の HTML は約40秒(BeautifulSoup の構文解析と `get_text` が主因)。今回は未変更。ソース単位ロックを握ったまま抽出するため、Crawler のタイムアウトと再送が重なりうる(動作の正しさには影響しない)。P5/P6 で README の既知の制限に記載する
- 制御文字 `\x0b`/`\x0c` の除去で語が連結する(実害小。置換への変更は見送り)、pypdf ロガーの import 時副作用(R9 の目的は満たす。P5 のログ設定との整理は任意)
- docs への新設定(`summary_input_max_chars`、`summary_rescan_max_interval_seconds`)の反映は未実施(`apps/indexer` 以外は変更しない方針。タスクレビューで扱いを確認)
- 0007 の arch 対応表の軽微な過大表記(N1): C-24(b) は専用テストがなく processor の C-1 と同経路、C-6 は P1 の fake/adapter 層のテスト、L-6 は C-4 のテストが観測可能な部分を再現している。表の記載は 0007 を書き換えず、ここに訂正を残す
- U-31(実機)、`document_id`(先頭 `/` を除かない)の Crawler 側突き合わせは持ち越し
- コミット未実施

## 次のアクション

1. 再レビュー(code-reviewer: A1〜A4 と新設定、test-reviewer: Important 4件の解消と追加テスト)
2. 解消確認後、P3(crawl_runs / lifecycle)へ
