# 0002 作業プラン: Indexer 実装

日付: 2026-11-11 / 作成: planner / 対象: `apps/indexer` / 要件: `0000`、確定要件: `0001`
状態: **ユーザー承認待ち**(承認を得るまで実装に進まない)

## 1. 目的とゴール

Indexer を設計書(arch v0.9、api v0.9、module v0.3、loreley-deletions v0.9、search-index v0.9)どおりに `apps/indexer` へ実装する。Indexer 以外(Crawler、api、web、OpenSearch 実体、compose)は対象外。OpenSearch 層と LLM はインメモリ fake に差し替えて単体テストする。

完了条件は 0001 の 1〜13 をそのまま使う。各フェーズとの対応は §7。

## 2. 確定事項・前提

### 2.1 確定事項(0001、ユーザー回答済み)

- Q1: 全モジュール実装。LLM の具体プロバイダは除く。
- Q2: 設計書の「案」は実装仕様として採用する。未決の数値は設定可能な仮値とし、必ず上限を設ける(K39)。未決の挙動は案に近い側に倒し、一覧を作業記録に残す。
- Q3: テストは OpenSearch アクセス層と LLM を fake に差し替える(競合再現フック付き)。U-31 の実機確認は範囲外で持ち越す。

### 2.2 技術選定の前提(承認対象)

| 項目 | 選定 |
| --- | --- |
| 言語・ツール | Python 3.12、uv(`pyproject.toml` + `uv.lock`)、ruff、pytest |
| Web | FastAPI + uvicorn(単一プロセス、workers=1) + pydantic v2 |
| 設定 | pydantic-settings(環境変数 `LORELEY_INDEXER_*`) |
| OpenSearch | opensearch-py の**同期クライアント**(理由は §3 の項目 9) |
| 抽出 | HTML は beautifulsoup4 + lxml、PDF は pypdf、文字コードは標準 codecs(UTF-8 厳密 → CP932 厳密) |
| テスト補助 | httpx(TestClient 用)のみ追加。型チェッカーは導入しない |
| 範囲 | 追加依存は最小限。すべて `apps/indexer` 内で完結させる |

### 2.3 置いた仮定

- OpenSearch のインデックス作成・マッピング定義は Indexer の範囲外(`infra/opensearch/schema` の領域)。Indexer は既存インデックスに読み書きするだけで、起動時に作成しない。
- 認証なし、単一ホスト、単一 Indexer、直列実行(MVP 前提)。
- 日時は UTC・ISO 8601・ミリ秒(`2026-11-09T01:00:00.000Z`)に正規化して保存・比較する(api 3.6)。
- 実装は `code-implementer` が行う。メインエージェントは実装せず、レビューは別エージェントが行う。

## 3. 未決挙動の一覧と、倒す側の案(承認時に判断する)

「案」が採用する側。「代替」が採らなかった側。

| # | ID | 論点 | 案(採用) | 理由 | 代替 |
| --- | --- | --- | --- | --- | --- |
| 1 | U-5 / API-U-4,8 | 原本サイズ超過の拒否主体 | Indexer も防御的に拒否する。申告 `size` または推定デコード長が `max_raw_bytes` を超えたら文書単位 `status=failed`、`failure_type=oversize`(仮名)を返す。抽出せず、既存文書も書き換えない。`last_seen_at` は列挙時の更新に委ねる。Crawler 側の送信前拒否と二重防御 | メモリ無制限を避ける(K39)。設計の確定範囲と整合する | Crawler のみが拒否し、Indexer は拒否しない |
| 2 | U-14 | 削除処理の開始契機・並行度 | 走査型 + 起床通知。ワーカースレッドが `loreley-deletions` を走査する(終了通知受理済みで非終端のもの、`finish_received_at` と `crawl_id` の順で先頭)。終了通知の受理後に `crawl_runs` の入口が `wake()` で起こす。定期走査間隔は `deletion_poll_interval_seconds`。並行度は全ソース直列で 1 | module R5(`deletion/` → `lifecycle/` の一方向)を保つ。待ち行列を別に持たない(9.9) | イベント駆動(R5 の見直しが必要)。ソース別並行 |
| 3 | U-20 | 再起動時の整理の対象 | `finish_received_at` があり非終端の結果(待機中・判定中・実行中)を `failed(indexer_restart)` にする。ID 一覧は同じ書き込みで削除する。`finish_received_at` の無い `running` には触れない | arch 9.8 の記述どおり。無いものは次の開始通知で `superseded` になる | `running` を全件 `failed` にする |
| 4 | U-26 / API-U-15 | `content_hash` の照合 | 照合しない(Crawler の値を信用)。再計算しない | 契約に失敗種別がなく、MVP を簡潔に保つ | 照合して不一致を文書単位の失敗にする |
| 5 | API-U-13 | ロック失敗時の部分結果 | 文書単位 `lock_not_owned`。確認済みの結果はそのまま返し、最初の失敗以降の未処理文書も `lock_not_owned`(書かない)にする。リクエスト全体は HTTP 200。ロック文書なし・期限切れ・所有者不一致はすべて不所有 | api 3.4 の提案どおり | リクエスト全体を 409 にする |
| 6 | API-U-7 | `last-seen` の要請単位 | Crawler が算出した `document_ids`(64 桁小文字 hex)の配列。件数上限 `max_last_seen_ids`。`update_conflict` は文書単位。インデックス全体の異常はリクエスト全体の 503 `unavailable` | api 4.2 の案を採用 | `external_id` 配列を受けて Indexer が算出 |
| 7 | 4.3 未決 | `fetched_at` / `metadata` を含む入力 | 無視する(保存せず、エラーにしない)。未知項目も無視(`extra=ignore`) | MVP で未使用(K45)。将来の追加でも Crawler が壊れない | 400 で拒否する |
| 8 | M-7 / API-U-14 | ソース削除 2・3 のロック所有確認 | 順 2・3 は `lock` を必須とし、所有確認に失敗したら書かずに 409 `lock_not_owned`(`retryable=false`)。順 1(discard)は `lock` を受け取るが確認しない(応答待ちでリースが切れうるため。再実行を妨げない) | api 4.7・4.8 の案に沿う。順 1 は 4.6 のリース切れの懸念を避ける | 順 1〜3 すべて確認しない / すべて確認する |
| 9 | 技術 | opensearch-py の同期/非同期 | 同期。FastAPI は同期 `def` ハンドラ、削除・要約は `threading` ワーカー | 単一 Indexer・直列前提。fake とフックが単純で競合再現が決定的。非同期は aiohttp 依存が増える | AsyncOpenSearch + asyncio |
| 10 | U-33 | T > D のガード | 採用。`validation_failed`(reason=`target_exceeds_denominator`)。強制削除モードでも適用 | arch 9.7 順 5 | ガードなし |
| 11 | U-12 | メンテナンスフラグの確認 | 削除は判定前と各バッチ前、要約の書き戻しは書き込み前に確認。登録・`last-seen` では確認しない(Crawler 側で停止する前提) | arch 11章の記述範囲 | 登録でも確認して 503 |
| 12 | U-9 / K54 | 要約の失敗・再試行・有効化後 | LLM 失敗・書き戻し失敗は `summary_max_attempts` まで再試行し、直らなければ `pending` のまま残す(`failed` へは遷移させない)。再走査は起動時と、書き戻し失敗後(間隔下限つきで 1 回)。有効化後の既存 `disabled` 文書の一括生成は実装しない(`rewrite_mode` を手段とし README に記載) | `failed` の遷移条件が設計未決のため、無制限化しない側に倒す | `failed` を導入し明示再実行の手段を作る |
| 13 | U-10 | 抽出・正規化の具体 | mime で分岐(text/plain、text/markdown・x-markdown、text/html、application/pdf。パラメータは除去)。未知 mime は `extract_failed`。文字コードは UTF-8(BOM 可)厳密デコード → CP932 厳密デコード、双方失敗なら `extract_failed`。HTML は script・style を除去して `get_text`。Markdown は原文のまま。PDF は pypdf(暗号化・破損は `extract_failed`)。正規化は NFC、改行を `\n` に統一、NUL と制御文字(タブ・改行を除く)を除去、行末空白除去、3 連続以上の空行を 2 に圧縮。NFKC は使わない。切り詰めは UTF-8 バイト数上限で文字境界。`text_hash` は切り詰め後本文の UTF-8 の SHA-256(小文字 hex) | 設計に具体規則がない。決定的であることを最優先 | chardet 等の自動判定、NFKC |
| 14 | U-15 / API-U-5 | 開始通知の型 | `ttl` は整数秒、`ratio_threshold` は小数(NaN・Inf は形式不正)、`min_delete_count` は整数、`force_delete`・`rewrite_mode` は真偽値。**範囲は検証しない**(確定事項)。再送比較は正規化後の値の完全一致 | arch 9.3 の確定事項 | 範囲検証を足す(確定事項と矛盾) |
| 15 | API-U-19/20 | エラー名・HTTP | api 3.4 の表どおり。`unavailable` は 503(`retryable=true`)、想定外は 500 `internal_error`。`lock_not_owned`(ソース削除 2・3)は 409 | 案を採用 | 名称変更 |
| 16 | P16 / K7 | 未知 `crawl_id` の終了通知 | 202 を返し、結果は作らずログに ID のみ残す | 案どおり。件数上限が不要 | 記録して件数上限を設ける |
| 17 | P25 / API-U-10 | Status の `waiting_for`、404 | `waiting_for` を実装(先行する非終端結果の `crawl_id`)。結果が無ければ 404 `crawl_not_found` | 案どおり。先行判定は削除側で必須のため低コスト | `waiting_for` を省略 |
| 18 | 9.8 | `deleted_count` の進捗更新 | バッチごとに `if_seq_no` の条件付き更新で書く。自分の結果の終端確認も兼ねる | 途中経過を記録できる(K43) | 終端のみ記録 |
| 19 | arch 8 | 登録処理の直列化 | ソース単位の `threading.Lock` で `documents:batch` と `last-seen` を直列処理。開始・終了通知の受理も別のソース単位ロックで直列化 | arch 8・9.9 | ロックなし |
| 20 | M-16 | 共通部品の置き場 | `loreley_indexer/common/`(依存先を持たない葉モジュール)にエラー型、日時正規化、ロック所有の純粋判定、ログのマスキングを置く。依存ルールテストで「全層から参照可、`common` は誰にも依存しない」を許可 | ソース削除 2・3 と `documents` が同じロック判定を使う。R3 を守りつつ重複を避ける | 各モジュールに重複実装 |
| 21 | U-19 | ヘルスチェック | `GET /healthz`(契約外)を最小限で追加。起動時整理の完了後にのみ応答 | 完了条件 12 の確認に必要 | なし |
| 22 | 4.4 | リクエスト・バッチ上限超過 | リクエスト全体を 400 `invalid_request` で拒否。バッチ件数とデコード後の合計サイズが対象 | 契約に超過時の規定がなく、形式不正として扱う | 413 を返す |

### 3.1 仮定義(設計書に未定義。作業記録に残し、変更点を 1 か所に隔離する)

| 対象 | 仮定義 |
| --- | --- |
| インデックス名(設定で変更可) | 検索インデックス `loreley-documents`(エイリアス想定)、`loreley-deletions`、`loreley-jobs` |
| ロック文書 | `loreley-jobs` の `lock-{source_id}`。項目 `owner`、`job_id`、`lease_expires_at`(ISO 8601)。所有 = `owner` と `job_id` が一致し、`lease_expires_at` > 現在時刻 |
| メンテナンスフラグ | `loreley-jobs` の ID `maintenance`、項目 `enabled`(bool)。文書なしは「立っていない」 |
| `loreley-deletions` の文書 | `deletion-{source_id}` と `deletion_result-{crawl_id}` を同じインデックスに置く。項目 `record_type`(`deletion` / `deletion_result`)、`source_id`、`status` は keyword 前提 |
| `validation_failed` の reason | `count_mismatch` / `id_limit_exceeded` / `target_exceeds_denominator` |
| `failed` の reason | `outcome_failed` / `outcome_cancelled` / `maintenance` / `indexer_restart` / `delete_error`(詳細項目に種別) |
| 検索インデックスのソートキー | `document_id`(keyword、doc_values 前提) |

マッピングが前提と違えば実機で失敗する(持ち越し、§12)。変更点はアダプタ層とロック判定に隔離する。

## 4. 仮値の方針(K39。すべて設定で変更可、`config.py` で `ge`/`le` 検証)

| 設定名 | 既定 | 上限 | 根拠 |
| --- | --- | --- | --- |
| `max_raw_bytes` | 20 MiB | 100 MiB | U-3、U-5、15.4 |
| `max_batch_documents` | 50 | 500 | U-3、API-U-6 |
| `max_batch_bytes`(デコード後合計) | 64 MiB | 256 MiB | U-3 |
| `max_request_body_bytes`(Content-Length で検査) | 100 MiB | 512 MiB | U-3、API-U-17 |
| `max_content_bytes`(抽出後本文、UTF-8) | 5 MiB | 50 MiB | U-8、15.2 |
| `max_last_seen_ids` | 1,000 | 10,000 | API-U-7 |
| `write_conflict_max_rereads` | 3 | 10 | U-31(4)、R8 |
| `update_retry_on_conflict` | 3 | 10 | U-31(3) |
| `delete_by_query_max_reruns` | 5 | 20 | K48、U-31(5) |
| `skip_oversize_id_limit`(両 ID 一覧の合算件数) | 10,000 | 100,000 | K34、U-2、API-U-5 |
| `deletion_batch_size` | 100 | 1,000 | U-2 |
| `deletion_retention_count`(N) | 20 | 1,000 | U-2 |
| `max_deletion_targets` | 200,000 | 2,000,000 | K47、15.4。超過は `failed(delete_error、target_limit_exceeded)` |
| `search_after_page_size` | 1,000 | 10,000 | 9.8 |
| `deletion_poll_interval_seconds` | 2.0 | 60 | U-14 |
| `delete_error_retry_attempts` | 3 | 10 | 4.4 |
| `retry_backoff_initial / factor / max`(秒) | 1.0 / 2.0 / 30 | 固定上限あり | 4.4(ジッタあり) |
| `discard_max_attempts` | 20 | 100 | P7、P29 |
| `summary_enabled` | false | - | 7.1 |
| `summary_concurrency` | 1 | 8 | K49 |
| `summary_max_attempts` | 3 | 10 | 7.4 |
| `summary_queue_size` | 100 | 10,000 | K39 |
| `summary_rescan_page_size` | 100 | 1,000 | 7.4 |
| `summary_rescan_min_interval_seconds` | 60 | 3,600 | P15 |
| `llm_timeout_seconds` | 60 | 600 | 7.1 |
| `os_request_timeout_seconds` | 30 | 300 | U-3 |
| `os_transport_max_retries` | 2 | 5 | 4.4 |

接続設定(`opensearch_url`、認証、`verify_certs`、CA パス)は必須または既定あり。秘密値は `SecretStr`。

## 5. 影響範囲(新規作成物)

`apps/indexer/` 配下(既存は空の `Dockerfile` のみ)。

- `pyproject.toml`、`uv.lock`、`.python-version`、ruff・pytest 設定、`README.md`、`Dockerfile`
- `src/loreley_indexer/`: `main.py`、`config.py`、`common/`、`api/`、`crawl_runs/`(`lifecycle/`、`deletion/`、入口ファサード)、`documents/`(直下に登録・`last-seen`、`extraction/`、`summarization/`)、`infrastructure/opensearch/`、`infrastructure/llm/`
- `tests/`: 単体テスト、`tests/fakes/`(インメモリ OpenSearch、fake LLM、固定時計)、抽出サンプル、依存ルールテスト

## 6. 実装フェーズ

順序: P1 → P2 → P3 → P4 → P5 → P6。P2 は `crawl_runs` の受理条件照会(R3)に依存するため、P2 に lifecycle の最小部分(レコード定義と受理条件の読み取り)を含める(推奨分割からの唯一のずれ)。

各フェーズの手順:
1. メインが `code-implementer` に依頼(タスク名、読むべきファイル、作業範囲、禁止事項、報告形式を含める)
2. 実装担当が検証コマンドを実行
3. メインが作業記録と `STATUS.md` を更新
4. §8 のレビューを実施

検証コマンド(`apps/indexer`): `uv run pytest`、`uv run ruff check`、`uv run ruff format --check`。

### P1: 基盤・infrastructure

- プロジェクト雛形、設定(`config.py` と各モジュール用の frozen な設定 dataclass)、`common/`
- `infrastructure/opensearch`: Repository インターフェース(検索インデックス窓口: ID 取得(`_seq_no`・`_primary_term` つき)、`op_type=create`、条件付き書き込み、`last_seen_at` の Update(max 比較スクリプトを params 渡しで固定)、条件付き削除、`search_after` 検索、件数、ID 存在件数、refresh、`delete_by_query`(`conflicts=proceed`)。Store 窓口: ID 取得・保存・削除、条件指定の列挙(並び順つき)、条件付き更新。`loreley-jobs` は読み取りのみ)
- 結果区分(成功 / 409 / 文書なし / 文書固有の拒否 / 全体異常)と、opensearch-py の例外・レスポンスからの分類
- `infrastructure/llm`: インターフェースと無効な既定実装(R9)
- `tests/fakes`: インメモリ OpenSearch(`_seq_no`・`_primary_term` 模擬、create 衝突、max 比較 Update、`delete_by_query` 競合模擬、refresh 可視性モデル、`search_after`、割り込みフック、応答差し替えと 409 連続注入、実行ゲート)、fake LLM(完了待ちゲート)、固定時計
- ログのマスキング(R9)、依存ルールテスト(R1〜R9。AST で import を検査)
- 検証: アダプタのリクエスト形テスト(MagicMock で `if_seq_no`、`op_type`、script と params、`conflicts`、refresh を検査)、例外分類テスト(接続エラー、タイムアウト、429、5xx、`cluster_block_exception`、`circuit_breaking_exception`、`index_not_found_exception` は全体異常。409 は競合。404 `document_missing_exception` は文書なし。その他 4xx は文書固有)、fake の自己テスト、依存ルールテスト(完了条件 1)、pytest/ruff

### P2: documents(+ lifecycle の最小部分)

- ID 算出(NFC、区切り統一、NUL 区切り、SHA-256)とテストベクタ
- extraction(§3 項目 13)
- 登録(`documents:batch`): 受理条件の照会(`crawl_runs` の読み取りのみ。拒否 5 種を例外で返し、1 件も書かない)、文書ごとのロック確認、抽出、取得、新規・更新・変更なし判定、`rewrite_mode`、メタデータのみ変更時の要約引き継ぎ、`extract_failed` の書き込み(K30)、409 の読み直し(上限 → `write_conflict`)、補完 Update(→ `update_conflict`)、結果区分
- `last-seen` 部分更新(`updated` / `unchanged` / `not_found` / `update_conflict` / `lock_not_owned`)
- summarization: 生成依頼キューと有界ワーカー、プロンプト組み立て、書き戻し(`pending` かつ `content_hash`・`text_hash` 一致のみ。メンテナンスフラグ確認、409 読み直し、上限超過で `pending` 維持)、起動時再走査、LLM 失敗の隔離。既定は無効で LLM を呼ばない
- lifecycle の最小部分: レコード(`deletion_result` 等)のモデルと直列化、受理条件の照会(`rewrite_mode` を返す)
- 検証: 完了条件 3、4、5、8。登録の分岐と区分、受理条件拒否で 1 件も書かないこと、ロック不所有の打ち切り、競合の再現(arch 16.1)、抽出サンプル(txt、Markdown、HTML、ASCII 最小 PDF、UTF-8、CP932、切り詰めと `truncated`、`text_hash` 決定性)、要約テスト。arch 16.2〜16.3、16.9 から Indexer 単体で再現できるケースを抽出し、ID 対応表を作業記録に残す

### P3: crawl_runs / lifecycle

- 開始通知(判定順 `crawl_already_finished` → 再送の複写値比較 → `stale_crawl_started_at`。結果作成、世代更新、`finish_received_at` の無い旧結果の `superseded` 化)
- 終了通知(形式 400 → `source_id` 照合 → ダイジェスト再送判定 → 受理分岐 1〜4。ID 一覧の保存、上限超過時の件数と超過フラグ記録、`failed`・`cancelled` の扱い)
- 開始・終了の受理をソース単位で直列化(`if_seq_no` 条件付き更新と上限つき読み直し)
- Status 応答(`waiting_for` を含む)
- 起動時整理(§3 項目 3)
- 終端遷移の書き込みヘルパー(ID 一覧を同じ書き込みで削除、保持件数 N の整理)
- 検証: 完了条件 6。世代更新、`superseded`、再送の 202 と 409、`source_id` 不一致の 409、未知 `crawl_id`、同一ソース直列、Status、起動時整理、D-40 の直列キュー制御

### P4: crawl_runs / deletion

- 削除ワーカー(走査と `wake()`)
- 判定(arch 9.7): 先行待ち、メンテナンス、件数照合、上限超過、対象決定、T > D、割合・最小件数ルール、強制削除モード
- 実行(arch 9.8): バッチごとの確認と更新、文書ごとの TTL 再確認と条件付き削除、409 の読み直し(上限で次回に委ねる)、削除エラーの有界リトライと `delete_error`
- 自分の結果が終端・404 の場合の停止
- ソース削除 1〜3: discard はバッチ排他の取得後に全非終端結果を `discarded(source_deleted)` にする(`if_seq_no` の衝突再試行)。全削除は refresh → `delete_by_query` → refresh → `_count` を上限回数まで繰り返す。削除記録の削除。順 2・3 のロック確認(§3 項目 8)
- 検証: 完了条件 7。判定の各終端状態、バッチ実行ゲート(D-12、D-19、D-31〜D-33、D-74(b))、競合再現(D-87、D-88)、discard 割り込み(D-41、D-42)、`delete_by_query` 再実行上限(D-90(a)(c))と refresh 停止(D-90(b))、待機中の旧い削除と再起動(D-92、D-93)、ソース削除の冪等性、削除バッチ中に新しい開始通知が入っても旧い削除が止まらないこと

### P5: api・main・起動順

- 8 API とエンドポイント(api 1章の案どおり)
- pydantic の形式検証。共通エラー形式への変換と例外ハンドラ(400 の本文に入力値を一切含めない。位置と型のみ)
- ボディサイズ、バッチ件数・サイズの検査
- `main.py`: 依存の組み立て、FastAPI lifespan、起動時整理(HTTP 受付前に完了)、削除ワーカーと要約ワーカーの起動停止、要約再走査の並行起動
- `/healthz`。要約を有効にしてプロバイダ未設定なら起動失敗
- 検証: 完了条件 2、9、10。TestClient で 8 API(正常、400、409 各種、`unavailable`)、起動順テスト、ログ検査(本文・秘密のセンチネル文字列が全ログ・エラー応答に出ないこと)、依存ルールテスト再実行

### P6: Dockerfile・README・最終検証

- `Dockerfile`: マルチステージ、`uv sync --frozen`、非 root、`CMD` は uvicorn、`HEALTHCHECK` は `/healthz`
- `README.md`: 起動・設定・テスト手順、仮値一覧、メンテナンス手順(`rewrite_mode` 前に要約生成を止める運用を含む)
- 作業記録の最終整理: 仮値一覧、案の採用一覧、仮定義、U-31 と未対応の持ち越し一覧
- 検証: 完了条件 11、12、13。pytest/ruff の全体結果を作業記録に貼る。`docker build apps/indexer` と起動して `/healthz` 応答。Docker が使えなければ未実施・持ち越しと記録

## 7. 完了条件との対応

| 完了条件 | 主なフェーズ |
| --- | --- |
| 1 依存ルール | P1(テスト作成)、P5(最終確認) |
| 2 8 API | P5 |
| 3 登録 | P2 |
| 4 `last-seen` | P2 |
| 5 抽出 | P2 |
| 6 `crawl_runs` | P3(起動順は P5) |
| 7 削除 | P4 |
| 8 要約 | P2 |
| 9 起動順序 | P5 |
| 10 ログ | P1(部品)、P5(検査) |
| 11 pytest / ruff | 全フェーズ。最終は P6 |
| 12 docker build | P6 |
| 13 作業記録の一覧 | P6(各フェーズで蓄積) |

## 8. レビューフェーズ

実装担当(`code-implementer`)とレビューは別エージェント。`code-reviewer` と `test-reviewer` は独立しているので並列実行。削除・一括更新に当たる P4 では `code-reviewer` を省略しない。

| 実施時点 | レビュー | 対象 |
| --- | --- | --- |
| P1 完了後 | code + test | `pyproject.toml` ほか設定、`src/loreley_indexer/{config.py,common/,infrastructure/}`、`tests/{fakes,infrastructure,architecture}` |
| P2 完了後 | code + test | `documents/`、`crawl_runs/lifecycle` の最小部分、対応するテスト・サンプル |
| P4 完了後(P3 と P4 をまとめて) | code + test | `crawl_runs/` 全体、対応するテスト |
| P5 完了後 | code + test | `api/`、`main.py`、起動順・ログ・API のテスト。パッケージ全体の依存ルールも確認 |
| P6 完了後 | code(Dockerfile)+ document-reviewer(README・作業記録) | `Dockerfile`、`README.md`。テスト変更がなければ test-reviewer は省略 |

依頼文に必ず含める事項:
- レビュー対象ファイルのパス一覧、比較基準、参照文書
- 比較基準: `apps/indexer` が新規作成のためファイル全体を対象とする。前フェーズのファイルを変更した場合は、変更箇所を作業記録に明記し、フェーズ開始時の HEAD SHA との差分で示す
- 参照文書: `0000-requirements-definition.md`、`0001-clarify-requirements.md`、本プラン、該当する作業記録、設計書(arch / api / module / loreley-deletions / search-index)
- 作業ツリーに無関係な変更があるため、`git diff` だけに委ねずパスを明示する
- コミットはユーザーの指示がある場合のみ

指摘への対応: Critical / Important は `code-implementer` に差し戻して修正し、同じレビュアーで再レビュー。Suggestion / Nitpick は対応可否を判断し理由とともに作業記録へ。「指摘なし」または Critical / Important 解消済みになるまで完了としない。

## 9. タスクレビューフェーズ(必須)

複数フェーズ・複数セッションにまたがり、データ削除を含み、設計書の未決を多数「案」で倒したタスクのため、プランの最後に実施する。

- 実施順: P6 のレビュー完了と、すべての作業記録・`STATUS.md` の更新が終わったあと
- 入力: タスク名のみ(`agent_tasks/20261111_implement_indexer/` 配下すべて)
- 確認内容: 要件、プラン、作業記録、実変更の突き合わせ。§3 の判断の妥当性と記録漏れ、仮値・持ち越しの記録の有無
- 対応: Critical / Important は該当工程に差し戻して修正し再レビュー。「指摘なし」または解消済みになるまで完了としない

## 10. 作業記録・STATUS.md の更新

メインエージェントのみが行う。サブエージェントは `STATUS.md` と `NNNN-*.md` を書かない。

- P1〜P6 の各フェーズ完了時に、作業記録を新規作成し、同時に `STATUS.md` を更新
- 各レビューの結果と対応を作業記録に残す(同じタイミングで `STATUS.md` 更新)
- P6 の作業記録に、仮値一覧、§3 の採用一覧、§3.1 の仮定義、U-31 ほかの持ち越し一覧、最終の検証結果を集約
- ユーザー判断待ちやセッション中断の際は、状況を `STATUS.md` に記録してから止まる

## 11. テスト方針

- 単体テストのみ。fake は決定的に動かす(固定時計、スリープなし)。ワーカーは `run_once()` を直接呼べる設計にする
- 競合系は、実際の同時実行に頼らず、フック・応答差し替え・完了待ちゲート・バッチ実行ゲート・直列キュー制御・refresh 停止で再現(arch 16.1)
- 分類マッピングとリクエスト形はアダプタ単体テストで確認(P1)
- `/healthz` と起動順は TestClient の lifespan で確認
- 抽出サンプル: CP932 と UTF-8 のテキスト、HTML、ASCII の最小 PDF、破損・暗号化 PDF、未知 mime

## 12. リスクと持ち越し

| # | 内容 | 扱い |
| --- | --- | --- |
| 1 | U-31(1)〜(8)の実機確認 | 持ち越し。`_seq_no` 楽観ロック、`delete_by_query` の競合・`version_conflicts`、`search_after`、painless の max 比較スクリプトと Instant パース、`retry_on_conflict`、存在しない文書への `if_seq_no` 付き操作の応答、`_reindex` は fake では検証できない。アダプタのリクエスト形テストで補うが、実機の挙動は保証しない |
| 2 | fake の限界 | fake は設計書の理解を再現したもの。実 OpenSearch と食い違えば、テストが通っても実機で失敗しうる。D-86(PIT なし取得の検証)は実機でしか確認できない |
| 3 | マッピング未定義 | `loreley-deletions` と検索インデックスのマッピングは未決(U-6、U-7)。Indexer はインデックスを作らない。`document_id` のソート、`record_type`・`status` の keyword 前提は仮 |
| 4 | ロック文書・メンテナンスフラグの形式が仮 | Crawler 設計で決まったら、ジョブ読み取りアダプタとロック判定(`common/`)だけを直す |
| 5 | 範囲検証なし | `ttl`・`ratio_threshold`・`min_delete_count` の範囲は検証しない(確定事項)。arch 9.13(9) の既知の制限 |
| 6 | PDF の日本語サンプル | ASCII の最小 PDF のみでテスト。日本語 PDF の抽出品質は未検証 |
| 7 | 文字コード判定 | 厳密デコードの UTF-8 → CP932 のみ。他の文字コードや短い ASCII 互換データの誤判定は `extract_failed` |
| 8 | 要約の有効化後の既存文書・`failed` 遷移 | 未実装(U-9、K54)。`rewrite_mode` で代替 |
| 9 | uv・Docker・ネットワークの可否 | 依存解決や `docker build` ができなければ未実施として記録し持ち越す |
| 10 | 単一プロセス前提 | ソース単位ロック・ワーカー・起床通知はプロセス内。複数 Indexer・複数 worker は対象外(13.2) |
| 11 | ログへの本文流出 | pydantic の検証エラーは入力値を含む。P5 で例外ハンドラが入力値を返さないこと、全ログにセンチネルが出ないことをテスト |

ロールバック: 新規作成物は `apps/indexer` に閉じる。各フェーズの変更は git で戻せる(`Dockerfile` は空に戻す)。他モジュールへの影響なし。

## 13. 未解決事項

- ユーザー承認時に、§3 の案(特に項目 1、4、7、8、9、20、21)を確認する
- 要件定義の空欄は 0001 の案で補完。`0000` への反映はユーザー任意
- `0000` の参照パス誤り、product-design v0.18 の存在、module v0.3 が存在しない過去タスクを参照している点は軽微
- U-31、マッピング、ロック・フラグ形式の持ち越しは §12
- planner 注記: arch 16章(テスト観点)の詳細は未読。実装担当が P2 以降で 16.2〜16.9 を読み、ID 対応表を作る前提
