# 0020 タスクレビューへの対応と最終まとめ

日付: 2026-11-12 / 対象: タスク全体(0000〜0019)/ レビュー: task-reviewer、code-reviewer、test-reviewer(最終修正の独立レビュー)/ 修正: code-implementer
比較基準: HEAD c065b9e(`apps/indexer` は未コミットの新規ファイル全体。**コミットは未実施**)

## 1. task-reviewer の結果(総合判定: 修正後可。Critical なし、Important 3件)

- 要件(Indexer の実装・単体テスト・仕様確認)は、実ファイル・テスト実行・設定値の照合で裏取りできた。スコープ外の変更なし(`git status`: `apps/indexer` と `agent_tasks` 以外は無関係の `.obsidian/workspace.json` のみ)。`api/routes.py` の9ルート(8 API+`/healthz`)を api v0.9 と照合して一致。`config.py` の44項目の既定値・上限が 0018 の表(0002 §4 と 0014 の追加分)と一致。`src` に TODO・FIXME・`print(`・`breakpoint(`・`ignore=` なし。0003〜0019 の連番に欠落・重複なし。監査ログ(`events.jsonl`)で `agent_tasks` への Write/Edit 54件がすべてメインエージェントによるものであること(サブエージェントによる書き込みなし)、0000 の差分はユーザー記載分のみであることを確認
- **Important I-1**: P6 の src 変更(R9 修正)と P5 最終修正(0017)の差分に、独立したコード・テストレビューがない(P6 のレビューは Dockerfile=code-reviewer、README=document-reviewer に限られ、テスト変更があるのに test-reviewer を省略した理由も記録なし)→ **対応済み**: 下記 §2 で code-reviewer と test-reviewer を実施し、指摘を反映した
- **Important I-2**: 完了条件12の「起動して `/healthz` に応答」がコンテナでは未確認(Docker は使えたが `/healthz` 200 の確認はローカル再現のみ)→ **対応済み**: 下記 §3 でメインが実コンテナで確認した
- **Important I-3**: STATUS.md に古い記述・矛盾が残っている(`urllib3` を WARNING 固定と書いている、0009 の方針変更を承認待ちと書いている(0014 で承認済み)、消化済みの申し送りが未解決事項に残っている、環境メモに「Docker デーモン停止中」とある 等)→ **対応済み**: 本記録とともに STATUS.md を整理した
- Suggestion: 未承認事項の集約が 0018・0019 に分かれ、仮定義の本体がない → 本記録 §6 に最終一覧を集約、仮定義は README §6 を参照先とする / プラン承認の記録と P2 を P2a/P2b に分けた理由の記録がない → 本記録 §5 に追記 / 設計書・要件定義の更新が必要になりうる事項が散らばっている → 本記録 §7 に「設計書改訂の候補一覧」として集約 / README の「PID 1 では終了コード 0」がメイン未確認 → §3 でメインが実機確認した(0) / `pydantic_core` の直接依存宣言がない(Nitpick。pydantic が `pydantic-core` を完全一致で固定し公開 API のため現状は問題なし)/ `.obsidian/workspace.json` が作業ツリーに残っている(コミットする際は含めない)

## 2. 最終修正(0017・0019 §1)の独立レビューと指摘対応

### code-reviewer(可。Critical・Important なし)
- 設定エラーの R9 修正は、実プロセスの `env -i` でセンチネルを入れて確認(URL 省略+パスワード、int・bool・Literal の不正値、整合違反、10件超、パスワードに JSON・不完全な JSON、URL へのパスワード埋め込み)。出力はすべて `loc: type` のみ、`__context__`・`__cause__`・`__notes__` は `None`。`env_file` は未設定で `.env` は読まれない。`ValueError` を送出する各設定 dataclass の `__post_init__` のメッセージは値を含まない
- `ignore=404` の撤回は、P1 でレビュー済みの `classify_failure` に正しく戻っている(優先順位: タイムアウト・接続エラー→全体異常、`index_not_found_exception` 等→全体異常、401・403・429・5xx→全体異常、409→`Conflict`、404 かつ文書不在→`NotFound`、それ以外→`Rejected(http_404)`)。削除の安全性は増減していない(`NotFound` を「削除済み」と扱う箇所は増えていない)
- `external_id` の制御文字許可: ログに `external_id` が出る経路がない、応答 JSON は `<0x20` をエスケープする、NUL 区切りの曖昧さは生じない(`compute_document_id` が NUL を拒否、`source_id` は制御文字を拒否)
- Suggestion S1: 起動前の別経路(`OpenSearchConnectionConfig.__post_init__` の `urlsplit`)で、URL 由来の値が例外メッセージ経由で標準エラー出力に出る(実測: `http://u:SENTINEL-SECRET-PW@host℀:9200` で stdlib の `_checknetloc` が netloc をそのまま例外に入れる)→ **対応**
- Suggestion S2: `external_id` の NUL が位置不明の汎用 400 になった(撤回前は位置付き)→ **対応**
- Suggestion S3: 404 の応答が JSON の配列・文字列・`null` だと opensearch-py の `_raise_error` が `AttributeError` を送出し `TransportError` の経路を外れる(`ignore` の有無にかかわらず発生。API では 500 `internal_error`、R9 は保たれる)→ **持ち越し**(README の既知の制限・U-31 に記載)
- Nitpick: Content-Length の先頭ゼロ埋め(21桁以上)が「ボディ過大」の400になる(実害なし。仕様として維持)、`pydantic_core` の直接依存宣言(不要)

### test-reviewer(Critical なし。信頼度「十分」。Important 2件)
- 約45種のミューテーションの多くを検出(`ignore=404` の再導入、404 の全 NotFound 化、`delete` の NotFound 固定、`index_not_found` の全体異常外し、`str(error)` の出力、`except` 内 raise、捕捉の除去、`external_id`・ID・Content-Length の各変更 など)
- **Important**: 整合検証4件のうち、検証名が固定されているのは1件だけ(起動時の出力に出るのは検証名だけで運用者が見る唯一の診断情報)→ **対応**
- **Important**: 実クライアント+スタブのログ漏洩テストが、チェーンした例外(`from None` の除去)を検出できない(スタブの `error_body` に `root_cause` がない、行列が `repr(error)` しか見ていない)→ **対応**
- Suggestion: 表示形式が部分一致で `msg`・`ctx` を出す変更が生き残る / 子プロセスの検査が OpenSearch 不達の起動失敗を通っていない → **対応**。Nitpick: `external_id` 4097バイトのテストがステータスのみ、Content-Length の桁数ガードの境界 → **対応**

### 指摘対応(code-implementer。メインが検証を再実行して確認)
- `connection.py`: `OpenSearchConnectionConfig.__post_init__` で `urlsplit` と `parts.port` を `try/except ValueError` で囲み、`except` の外で固定文 `ValueError("the OpenSearch URL is invalid")` を送出。`main.py`: `create_backends` で接続設定の生成とクライアント2つの作成を囲み、`ValueError` を `StartupError("invalid OpenSearch connection settings (the URL must be valid and must not contain credentials)")` に変換(`except` の外で送出。`__context__`・`__cause__` は `None`)
- `api/schemas.py`: `_check_external_id` に NUL だけを拒否するチェック(`id_invalid_character`、固定文)を追加し位置付きの 400 に戻した(`compute_document_id` の拒否は防御として残す。改行・タブ・ESC・DEL は従来どおり許可)
- テスト: 整合検証4件の検証名を `str(error) == "invalid settings: settings: <検証名>"` で固定(子プロセスは2件)、`test_startup_errors.py` の部分一致を完全一致に、URL 5種(`℀` を含む netloc+パスワード、不正ポート、範囲外ポート、IPv6 の括弧欠け、認証情報の埋め込み)をプロセス内と子プロセスで検査、スタブの `error_body` に `root_cause` を追加し `assert_no_sentinel_in(error)`(`str`・`repr`・連鎖を含む traceback。連鎖の区切り文がないことも検査)に、`timeout` 応答の追加、閉じたローカルポートへの起動(終了コード3、`connection_error`、センチネルなし)、`external_id` 4097バイトのテスト強化、Content-Length 先頭ゼロ埋めの明文化。実装担当のミューテーション確認: 22種中21種を検出(生存1件は等価な変異。`transport_error` 経路の `from None` 除去は HTTP スタブでは到達できず未検出)
- **メイン確認**: 実プロセスで URL に `SENTINEL-SECRET-PW` を埋め込んだ3パターン(`http://u:…@host℀:9200`、`http://host:xyz`、`http://u:…@host:9200`)を起動 → いずれも終了コード1、センチネル0件、最後の行が固定文の `StartupError`。一時ファイル(`out.txt`・`err.txt`)は残っていない

## 3. 完了条件12(docker build と実コンテナ)の実機確認(メインが実施)

- 修正後の `docker build apps/indexer` は成功(約189MB)。Python 3.12.16、非 root(uid 10001)、`uv` なし、`pytest`・`httpx2`・`ruff` なし、`fastapi`・`loreley_indexer` あり
- **実コンテナでの起動と `/healthz`**: ホスト側で標準ライブラリの偽 OpenSearch(`_refresh`・`_search`・`_count` に空ヒットを返す)を起動し、コンテナ(`--add-host host.docker.internal:host-gateway`、`-p 127.0.0.1:18000:8000`)から接続 → `/healthz` が約2秒で 200(`{"status":"ok"}`)。ログは「unfinished deletion results were failed after the restart: count=0 → the indexer is ready → Application startup complete」の順(起動順の確認)。**HEALTHCHECK は `healthy`**(exit=0)
- **停止**: `docker stop` は 0.86 秒で graceful に終了(`Shutting down → Application shutdown complete → Finished server process [1]`)、**終了コード 0**(PID 1)。README の「PID 1 では終了コード 0」を実機で確認
- 確認用のコンテナ・イメージ(`loreley-indexer:smoke` ほか)・偽 OpenSearch は片付けた。取得したベースイメージ(`python:3.12.16-slim-bookworm`・`python:3.12.11-slim-bookworm`)は残っている
- 限界: 接続先は偽の OpenSearch(空ヒットを返すだけ)であり、実 OpenSearch に対する登録・削除・検索の動作は未確認(U-31)

## 4. 最終検証(メインが実施。2026-11-12)

- `uv run pytest` → **2119 passed**(3回連続で同数、約40秒)
- `uv run ruff check` → All checks passed、`uv run ruff format --check` → 191 files already formatted、`uv lock --check` → Resolved 43 packages(一致)
- Python 3.12.16 のコンテナ内でも全テスト 2098 passed(0019 時点。実装担当が確認)
- `git status`: `apps/indexer`(新規ファイル全体と `Dockerfile` の変更)と `agent_tasks` 以外は `.obsidian/workspace.json`(無関係の既存変更。コミットする際は含めない)のみ。**コミット未実施**(HEAD は c065b9e のまま)

## 5. プラン承認の記録・プランからの乖離の記録(task-reviewer の Suggestion への対応)

- **プラン 0002 は 2026-11-11 にユーザーが「全て案どおり承認」した**(AskUserQuestion の回答。0002 の §3 の22項目の案・§2.2 の技術選定の前提・§6 のフェーズ分割・§8 のレビュー計画を含む)。0002 冒頭の「ユーザー承認待ち」の表記は承認前の状態のまま残っているが、0002 は既存の作業記録を書き換えない方針のため、承認の事実は STATUS.md・0014・本記録に記録する
- **P2 を P2a(0006)と P2b(0007)の2回の実装依頼に分けた理由**: P2 の規模(ID 算出・抽出・lifecycle の最小部分と、登録・last-seen・要約)が大きく、1回の依頼では実装担当の文脈が溢れるため。レビューは P2 全体で1回(P2a+P2b)実施した(プラン §8 のとおり)
- **P3 と P4 をまとめてレビュー**(プラン §8 のとおり)、**P1・P2・P3+P4・P5 は再レビューまで実施**。再々レビューを省略した箇所とその理由は各記録に記載(0005: P1 の最後の修正はテストと log_masking の文言に限られるためミューテーションと検証コマンドで確認、0017: `ignore=404` の撤回は P1 で2回レビューした経路への復帰のため)。**ただし 0017 の最終修正と 0019 §1(R9 修正)に独立レビューがなかった点は、task-reviewer の指摘を受けて本記録 §2 で補った**
- P6 のレビューは、プラン §8 の「`Dockerfile`=code-reviewer、`README`・作業記録=document-reviewer、テスト変更がなければ test-reviewer を省略」に従って実施したが、P6 の途中で src・tests の変更(R9 修正)が入ったため、test-reviewer の省略は妥当でなくなった(§2 で補った)
- `ignore=404` を P5 で導入し(0015・0016)、再レビューで退行を指摘され撤回した(0017)経緯は 0016・0017 に記録済み。`src` に `ignore=` は残っていない

## 6. ユーザー確認が必要な事項の最終一覧(承認未取得。0018・0019・0020 の集約)

2026-11-11〜12 にユーザーが承認したもの: Q1〜Q3(0001)、プラン §3 の22項目の案(0002。全て案どおり)、0014 の3件(TTL の追加条件は入れない/メンテナンスフラグは fail-closed/要約の再走査の方針変更)。以下は**承認を取得していない**(プラン §3「案に近い側に倒す」「未決の数値は設定可能な仮値」の範囲として実装したもの)。詳細は各作業記録を参照。

### 6-1. 設計書からの逸脱・設計判断を伴うもの(優先して確認)
1. **要約の生成依頼を文書 ID のみにした**(0007 判断12。module 4.3「ID・content_hash・text_hash・本文」からの逸脱。メモリ上限のため。code-reviewer は妥当・承認推奨と評価)
2. **開始通知の書き込み順を「世代→superseded化→結果作成」にした**(0010 判断4。設計書の記述順は世代・結果作成・supersede。途中失敗後の再送で収束させるため)
3. **文書固有拒否の連続20件打ち切りを Indexer に実装しない**(0007 判断8。Crawler 側の規則と読んだ。api 3.5・arch 4.4・module 4.3 に沿う)
4. **DELETE の `lock` を JSON ボディで受ける**(0015。api 3.2 は運び方が未確定、4.6 の例がボディ形式。Crawler 側の HTTP クライアントが DELETE にボディを載せられる必要がある)
5. **不正記録を list から除外してログのみ**(0012。後続の削除が不正な先行記録を無視して進む。削除量は TTL 再確認と `source_id` 照合で守られ増えない。不正記録は `running` のまま残る)
6. **再起動整理で未記録の `deleted_count` に 0 を付ける**(0012。D-93 準拠)、**`progress_update` は `deleted_count` を減らさない**
7. **判定フェーズの全体異常は `running` のまま走査ごとに再実行する**(0011。上限なし・バックオフ付き(0012)。連続失敗で `failed` にする案、先頭失敗時に次のソースへ進む案は arch 9.9 の直列の意味が変わるため見送り)
8. **`document_id` の先頭 `/` を除去しない**(0006 判断1をメインが修正。設計書の「先頭に `/` を付けない」は入力の前提であって除去規則ではないと読んだ。last-seen は Crawler が算出した `document_id` を受けるため、Crawler 側と突き合わせが必要)
9. **ID・入力の検証規則**(0015・0016・0017): `content_hash` は小文字64桁 hex のみ(大文字は 400)、ID 長の上限(`source_id`・`crawl_id`・`lock.*` 256バイト、`external_id` 4096バイト)、`source_id`・`crawl_id`・`lock.*`・パス ID は制御文字を拒否(`external_id` は許可・NUL のみ拒否)、孤立サロゲートの分担(`external_id` など ID 類は API 層で 400、`title`・`mime_type`・`path`・`url` はドメインが文書単位 `document_rejected`)、`skipped_count` は型のみ検証して値を使わない、起動前は `/healthz` を含め全パス 503
10. **メンテナンスフラグ・ロック文書・索引名・マッピングの仮定義**(0002 §3.1。実機・Crawler/infra 設計の確定時に再確認。README §6 に記載)

### 6-2. 追加した設定・依存・運用(承認のうえ、docs への反映も要検討)
- **新設定**: `summary_input_max_chars`(既定30,000、上限1,000,000。0007 判断17。要約は先頭30,000文字のみ)、`deletion_poll_backoff_max_seconds`(既定300、上限3,600。0012)、`os_delete_by_query_timeout_seconds`(既定600、上限3,600。0011)、`HTTP_HOST`(既定127.0.0.1)・`HTTP_PORT`(既定8000)・`LOG_LEVEL`(既定INFO。0015)。`summary_rescan_max_interval_seconds`(既定3600、上限86,400)は 0014 で承認済み
- **設定の整合検証4件**(0016。`max_raw ≤ max_batch`、`max_batch×4/3 ≤ max_request_body`、`summary_rescan_max ≥ min`、`deletion_poll_backoff_max ≥ poll_interval`。うち後ろ2つは 0014 に記載)と、起動時の設定エラーを `StartupError` の固定形式(フィールド名と種別のみ。値は出さない)に変換したこと(0019 §1・0020 §2)
- **依存**: `fastapi`・`uvicorn`(本体)、**`httpx2`(dev。PyPI の Pydantic 組織のリポジトリ `pydantic/httpx2` の 2.16.0。starlette の `TestClient` が要求する。通常の `httpx` ではなく見慣れない名前。code-reviewer が PyPI で確認済み。本番イメージには含まれない)**。`beautifulsoup4`・`lxml`・`pypdf`・`opensearch-py`・`pydantic-settings` は 0002 §2.2 の技術選定の前提(承認済み)
- **削除の実行**: 削除専用ソース単位排他 `SourceBatchExclusion`(ソース削除優先)、`delete_by_query` 専用クライアント(`retry_on_timeout=False`、`retry_on_status=()`)、TTL 再確認に文書の `source_id` 一致を追加(安全側)、ソース削除2は再実行ごとにロック所有を再確認、`discard_max_attempts` は試行ラウンド数、`delete_error_retry_attempts` は初回を含む総試行回数、`SearchIndexRepository.fetch_for_deletion` の追加、`LockInfo` を common へ移動
- **ログ・R9**: `opensearch`・`opensearchpy`・`opensearchpy.trace`・`opensearchpy.helpers`・`urllib3` のロガーを ERROR 固定(ライブラリ由来の警告も出なくなる)、500 のログに診断情報 `origin`(`file:line function`)を追加(ログ文言の変更。監視で文言を拾う場合は影響)、`UnexpectedResponseError` 基底クラスと `close_clients` の新設、`ClientDisconnect` は 400、Content-Length の20桁超は 400
- **P2〜P3 の細目**(0006・0007・0008・0010): レコードに `crawl_id`・`reason_detail`・`started_at`/`ended_at` を追加、正規化でサロゲートを除去、抽出失敗種別の仮名、`failure_type=oversize` の仮名、受理の 409 が上限超過なら `UnavailableError("write_conflict")`、`SourceLocks` を common へ移動、ID 一覧の件数とフラグを上限以内でも記録、`failed`/`cancelled` はダイジェストのみ保存、`crawl_id`/`source_id` の空文字拒否、`finished_at` は保存・比較しない、メタデータ検査に `mime_type` を含める、`DOCUMENT_REJECTED` の基本メッセージ変更、検査順(oversize→メタデータ→抽出)、PDF 打ち切りは正規化後の長さで判定、`should_stop` の追加
- **Docker(P6)**: ベースイメージ `python:3.12.16-slim-bookworm@sha256:935c3c5b…`(タグ+ダイジェスト固定。2026-11-12 時点の最新パッチ版。更新の運用は定期的な再ビルド)、uv は `pip install uv==0.13.7`(builder のみ。ハッシュ固定はしていない)、アプリ本体は `PYTHONPATH=/app/src` で参照(hatchling が `uv.lock` に載らないため)、`uv sync --locked`、uid 10001、HEALTHCHECK の値(start-period 120秒)、停止猶予「30秒以上」の推奨、README にメンテナンスの章を追加

### 6-3. 撤回済み(承認不要。経緯の記録のみ)
- `ignore=404`(0015・0016 で導入し、0017 で撤回。退行: 404 の本文が非 JSON のとき `SerializationError` が漏れ、削除の再試行上限が効かなくなる)、`external_id` の制御文字拒否(0016 で導入し 0017 で撤回。改行を含むファイル名1件でバッチ全体が恒久400になるため)

## 7. 設計書・要件定義の改訂候補(`apps/indexer` 以外は変更していない。扱いはユーザー判断)

- 新設定6件(`summary_input_max_chars`、`summary_rescan_max_interval_seconds`、`deletion_poll_backoff_max_seconds`、`os_delete_by_query_timeout_seconds`、`HTTP_*`、`LOG_LEVEL`)と整合検証の docs への反映
- module 4.3 からの逸脱(要約依頼は文書 ID のみ)、開始通知の書き込み順(arch 9.5 の記述順との差)、D-93 の `deleted_count=0`(設計書どおりに実装した。K43 との関係の注記)、DELETE の `lock` を JSON ボディにしたこと(api 3.2 の運び方の確定)、`document_id` の先頭 `/` を除去しないこと(api 4.3・arch の記述の明確化)、メンテナンスフラグ・ロック文書の形式(Crawler 設計との突き合わせ)
- 0000 の空欄(制約・前提条件、完了条件、成果物)への反映はユーザー任意(0001 の案で補完した)。0000 の参照パス誤り(`opensearch/schema/` の欠落)、product-design v0.18 の存在(仕様差なし)、module v0.3 が存在しない過去タスク `20261110_implement_indexer` を参照している点(いずれも軽微で実装に影響しない)

## 8. 持ち越し・未確認(最終)

- **U-31(実 OpenSearch での確認)**: `_seq_no` による楽観ロックと存在しない文書への `if_seq_no` 付き操作の応答、`delete_by_query` の競合・`version_conflicts`・タイムアウトの再送抑止、`search_after` と `document_id` のソート、painless の max 比較と `Instant` のパース(fake は実機より寛容な可能性)、`retry_on_conflict`、`_reindex`、refresh の挙動(シャード部分失敗の応答形、`_count` が古いまま0になる可能性)、404 の本文の形(特に `update`。JSON の配列・`null` の404は想定外例外になり API では 500)、D-86(PIT なし取得)、fake と実アダプタの契約一致テスト。**fake・ローカルスタブ・偽 OpenSearch のみでの検証であり、実 OpenSearch に対する動作は未確認**
- 実 OpenSearch に接続したコンテナの動作、実 uvicorn 経由の `ClientDisconnect`、実 LLM(具体プロバイダは未実装。有効化すると起動に失敗する)、実 Crawler との接続
- **Crawler との突き合わせ**: `document_id` の先頭 `/`、`content_hash` が小文字 hex か、DELETE にボディを載せられるか、ファイル名由来の孤立サロゲートの扱い(`external_id`(パス)に入ると全体400)、ID 長の上限、ロック文書・メンテナンスフラグの形式(fail-closed なので食い違うと削除・要約が止まり続ける)、索引名、マッピング前提(`document_id` のソート、`record_type`・`status` の keyword 前提)
- **既知の制限(README に記載)**: TTL・`ratio_threshold`・`min_delete_count` の誤設定リスク(TTL 0・負値・クロール時間より短い、`ratio_threshold` が1以上、`min_delete_count` が大きい場合に今回のクロールが見た文書も削除されうる。ユーザー判断で追加条件は入れない)、判定時の `MalformedRecordError` が待ち行列の先頭を詰まらせる(WARNING 監視)、要約の再開遅延(最悪 `summary_rescan_max_interval_seconds`)と先頭30,000文字のみ要約、巨大 HTML の処理時間(約40秒)とソース単位ロックの占有、同じ `crawl_id` を別 `source_id` で同時に開始通知した場合の競合、メンテナンスフラグ不正 WARNING の再武装、ドメインの形式不正以外の `ValueError` は 400 のまま(専用例外 `InvalidInputError` は P2〜P4 の変更を伴うため見送り)
- R6・R7・R8 の依存ルールは部分検査のみ(完全な機械検査ではない)
- uv のハッシュ固定、`/app/.venv/.lock`(0666、空)、ベースイメージの定期更新の運用
- 日本語 PDF の抽出品質は未検証、要約の `failed` 遷移と有効化後の既存文書の一括生成(未実装)

## 9. 完了チェックリスト(.claude/rules/task-workflow.md)

- [x] プランが作業記録として残っていて、ユーザーの承認を得ている(0002。承認は 2026-11-11、本記録 §5)
- [x] すべての作業に作業記録がある(0001〜0020)
- [x] プランで指定されたレビューを実施している(省略・追加した箇所とその理由は §5。最終修正の独立レビューは §2 で補った)
- [x] 未対応事項を、最新の作業記録(本記録 §8)に書いている
- [x] STATUS.md が最新の作業記録と一致している(本記録とともに更新)
- [ ] **ユーザーによる承認未取得の事項の確認(§6)**、コミットの要否

## 次のアクション

1. ユーザーへ完了報告し、§6 の承認未取得の事項を確認する(特に 6-1 の逸脱を伴うもの。`httpx2` の依存追加、docs 改訂の扱い(§7)も)
2. コミットは、ユーザーの指示があるまで行わない(コミットする場合、`.obsidian/workspace.json` は含めない)
