# 結合テスト(Indexer)

compose で起動した**実 OpenSearch と実 Indexer**に対して、ホストの pytest から実行する結合テスト。テストが Crawler の役を務め、Indexer の HTTP API を呼び、OpenSearch の実データを直接読んで確かめる。

> **確認状況**: 実行結果(passed 件数・所要時間・環境)は [docs/v0.x/test-results/indexer-integration.md](../../docs/v0.x/test-results/indexer-integration.md) に書く。この文書には書かない。
> **uv 経由の既定起動は確認済み**(uv 0.13.8。スクリプトを 2 回連続で実行し、どちらも 40 passed。結果記録 4.2 の ④⑤)。`tests/integration/uv.lock` で依存を固定している。macOS(x86_64)・Docker 20.10.13・compose v2.3.3 でのみ確認した。

## 目的

Indexer の単体テストは、OpenSearch を**インメモリの fake** に差し替えている(`apps/indexer/README.md` 10 章)。fake は設計書の理解を再現したもので、実 OpenSearch と食い違うことがある。この結合テストは、次を実機で確かめる。

- compose で起動した Indexer が、実 OpenSearch に接続して起動時の整理まで終えること(`opensearch-init` が作った実際のマッピングの上で動くこと)
- 主要フロー(開始通知 → バッチ登録 → `last-seen` → 終了通知 → Status → 期限(TTL)による削除、ソース削除 1〜3)が、実際の OpenSearch で設計どおりに動くこと
- 設計書の実機確認項目 U-31 のうち、自然に通るもの(painless の max 比較、`search_after`、`delete_by_query`、404 の応答形、日時形式)

## 前提

| 項目 | 内容 |
| --- | --- |
| Docker | Docker と docker compose v2(確認した版: Docker 20.10.13、compose v2.3.3)。デーモンが起動していること |
| uv | 必要(確認した版: uv 0.13.8)。`tests/integration/uv.lock` で依存を固定している。依存を変えたら、`tests/integration` で `uv lock` を実行して更新する |
| メモリ | Docker に **約 4GB 以上**を推奨(OpenSearch のヒープ 512m の既定は、約 3.8GiB の VM で確認した)。ほかの重いコンテナを同時に動かさない |
| ポート | ホストの `9200`(OpenSearch)と `8000`(Indexer)が空いていること。どちらも `127.0.0.1` だけに publish する |
| ネットワーク | 初回は、ベースイメージ・OpenSearch のイメージ・Python の依存を取得する |

Linux の `vm.max_map_count` と SELinux は未確認(`deploy/compose/README.md` の前提を参照)。

## 実行方法

### 一括で実行する(通常はこれ)

リポジトリのルートで、スクリプトを実行する。スタックの起動、起動の待機、pytest、後始末(`down -v`)までを行う。

```sh
scripts/run-indexer-integration-test.sh                  # 全シナリオ
scripts/run-indexer-integration-test.sh --keep           # 終了後もスタックを残す(デバッグ用)
scripts/run-indexer-integration-test.sh -k test_30_deletion   # 1 ファイルだけ(ファイル名の語で絞る)
scripts/run-indexer-integration-test.sh -k test_ttl_deletion_runs_in_multiple_batches_and_pages   # 1 テストだけ(テスト名の語で絞る)
scripts/run-indexer-integration-test.sh -k deletion      # 名前に deletion を含むテスト
```

- `--keep` と `-h` 以外の引数は、そのまま pytest に渡る。**絞り込みには `-k` を使う**。ファイルやノード ID(`ファイル::テスト名`)をパス引数で渡しても、既定のコマンドの末尾に `tests/integration` があるため絞られず、全テストが走る(`LORELEY_IT_PYTEST_CMD` で既定のコマンドを置き換えたときは別)。ノード ID で 1 テストを指定したいときは、「手動で実行する」の手順で pytest を直接実行する
- スクリプトは、`docker compose -p loreley-it -f deploy/compose/compose.yaml -f tests/integration/compose.test.yaml up -d --build` で起動する。**`up --wait` は使わず**、`docker compose ps` 相当の確認を 3 秒間隔で繰り返して、`opensearch`・`indexer` が healthy、`opensearch-init` が Exited(0) になるのを待つ(compose v2.3.3 では `--wait` が戻らないため。`deploy/compose/README.md` を参照)
- 異常終了したときは、`docker compose ps -a` と各サービスのログの末尾 100 行を表示してから、後始末する
- ホスト側のポートは、スクリプトが 9200・8000 に固定する(`deploy/compose/.env` で変えていても上書きする)

#### 終了コード

| コード | 意味 |
| --- | --- |
| 0 | 全テスト成功 |
| 1 | pytest のテスト失敗、**または**引数・事前確認の失敗(Docker・uv が無い、ポート使用中など)。事前確認の失敗は標準エラー出力に理由が出るので区別できる |
| 2〜5 | pytest の終了コードのまま(2=中断・スタックに接続できない、5=該当テストなし) |
| 10 | スタックの起動失敗(`up` の失敗、待機の上限超過、コンテナの異常終了)。実機で確認したのは `up` の失敗と待機の上限超過。**コンテナの異常終了(init の非 0 終了、unhealthy・restarting)の判定は、コードの確認のみで実機では再現していない** |
| 130 / 143 | Ctrl-C(INT)/ TERM で中断(どちらも後始末まで行う) |

#### 環境変数

| 変数 | 既定 | 説明 |
| --- | --- | --- |
| `LORELEY_IT_WAIT_TIMEOUT_SECS` | `300` | 起動後の待機の上限(秒)。1 以上の整数 |
| `LORELEY_IT_PYTEST_CMD` | `uv run --project tests/integration pytest tests/integration -v` | pytest を起動するコマンド全体の置き換え(空白区切り。スクリプトの引数はこの後ろに付く)。**uv が使えない環境で、用意済みの venv の pytest を使うための逃げ道**で、通常は指定しない。指定すると uv の事前確認を省略する |

`OPENSEARCH_VERSION`・`OPENSEARCH_HEAP_SIZE`・`INDEXER_LOG_LEVEL` などの compose の変数は、そのまま compose に渡る(`deploy/compose/.env.example`)。

### 手動で実行する(スタックを起動して pytest を直接実行する)

スクリプトを使わずに、スタックの起動と pytest を分けたいとき(テストを繰り返し実行するときなど)の手順。リポジトリのルートで実行する。

```sh
# 1. 起動(`--wait` は使わない)
docker compose -p loreley-it -f deploy/compose/compose.yaml -f tests/integration/compose.test.yaml up -d --build

# 2. opensearch・indexer が healthy になるまで待つ(opensearch-init は Exited (0) になる)。
#    indexer が healthy になる前に pytest を始めると、疎通確認で中止される(終了コード 2)
docker compose -p loreley-it -f deploy/compose/compose.yaml -f tests/integration/compose.test.yaml ps

# 3. テストを実行する
uv run --project tests/integration pytest tests/integration -v

# 4. 後始末(ボリュームも消す)
docker compose -p loreley-it -f deploy/compose/compose.yaml -f tests/integration/compose.test.yaml down -v --remove-orphans
```

- テストは `compose.test.yaml` の値(Indexer の原本上限 64 KiB、削除のバッチ・ページ 2 件、走査間隔 1 秒)を前提にしている。`deploy/compose/compose.yaml` だけで起動したスタックに向けて実行しない(IT-14・IT-31 などが前提を満たさず失敗する)
- ホスト側のポートを `.env` で変えている場合は、テストの接続先を環境変数 `LORELEY_IT_OPENSEARCH_URL`・`LORELEY_IT_INDEXER_URL` で合わせる(既定は `http://127.0.0.1:9200`・`http://127.0.0.1:8000`)。スクリプトを使う場合は不要
- スタックが起動していないと、pytest は接続できなかった理由と起動手順を表示して、終了コード 2 で中止する

### 専用プロジェクトで実行し、開発用スタックと分ける

結合テストは、専用の compose プロジェクト名 `loreley-it` で実行する。開発用のスタック(`deploy/compose` を `-p` なしで起動したもの)とは、コンテナ・ボリューム・ネットワークが別になる。

- テストは、後始末として、作成したデータ(ソース・文書・記録)を**削除しない**(IT-41・IT-42 のように削除 API を確認するものを除く)。後始末はスタックごと `down -v` で消すことに任せている。**開発用のスタックに向けて実行しない**(テストのデータが残る)
- IT-41 は、検索インデックスの `refresh_interval` を一時的に変更し、終了時に戻す(失敗しても戻す)
- ホストの `9200`・`8000` を開発用スタックが使っていると、スクリプトは事前確認で中止する

### シナリオ ID でテストを選べない

テスト関数の名前には `IT-nn` が含まれない(ID は各ファイルの冒頭と、テストの docstring にだけある)。`-k IT-30` は **0 件になる**(終了コード 5)。ファイル名か、テスト名の語で選ぶ。

- ファイル名の語を `-k` に渡す: 次の「シナリオ一覧」の表のファイル名から、例 `-k test_30_deletion`(`test_30_deletion.py` の 2 件に絞れることを確認した)
- 名前のキーワードを使う: 例 `-k deletion`(ファイル名 `test_30_deletion.py`・`test_40_source_deletion.py` と、名前に `deletion` を含むテスト)、`-k document_id`(`test_02_document_id.py`)。キーワードはほかのファイルのテストにも一致しうるので、`--collect-only -q` で対象を確認してから実行する
- 1 テストを指定する: テスト名の語を `-k` に渡す(例 `-k test_ttl_deletion_runs_in_multiple_batches_and_pages` で 1 件に絞れることを確認した)。テスト関数名は `--collect-only -q` で分かる
- **スクリプトにファイルやノード ID(`ファイル::テスト名`)をパス引数で渡しても、絞られず全テストが走る**(既定のコマンドの末尾に `tests/integration` があるため。`pytest tests/integration … tests/integration/test_30_deletion.py` で 40 件が収集されることを確認した)。ノード ID で指定したいときは、「手動で実行する」の手順で pytest を直接実行する
- 収集だけ確認したいときは、スクリプトを使わず、ホストで `uv run --project tests/integration pytest tests/integration --collect-only -q` を実行する(**スタックは不要**。スタックを止めた状態で実行して 40 件が収集されることを確認した)。スクリプト経由で `--collect-only` を渡すと、スタックを起動してから収集する

## 結果の見方

- スクリプトで実行すると、pytest の出力が標準出力と `tests/integration/results/pytest-YYYYMMDD-HHMMSS.log` に残る(実行のたびに増える。`.gitignore` 済み)
- 失敗したテストの詳細は、このログの `FAILURES` の節にある。スタックの状態は、同じ実行の最後に出る `docker compose ps -a` と各サービスのログの末尾(異常終了のとき)を見る。`--keep` で残したスタックなら、`docker compose -p loreley-it ... logs indexer` で全体を見られる
- 実行結果の記録は [docs/v0.x/test-results/indexer-integration.md](../../docs/v0.x/test-results/indexer-integration.md)

## シナリオ一覧

全シナリオは、設計書と実装の理解を実 OpenSearch で確かめるもの。各テストの docstring に、【何を確認するか】【前提と手順】【期待する結果とその根拠(設計書の章)】【fake では確認できず実機で確認する点】がある。表の「設計書」は、期待値の根拠にした章(api = `indexer-api-v0.10.md`、arch = `indexer-architecture-v0.10.md`)。

| ID | ファイル | 何を確認するか | 設計書 |
| --- | --- | --- | --- |
| IT-01 | `test_01_startup.py` | `/healthz` が 200(起動時の整理を終えている)。`loreley-deletions` を読める。検索インデックスがエイリアス `loreley-documents` 経由で見え、`dynamic: strict` で主要項目が定義されている。`loreley-deletions` は `dynamic: strict` で `record_type` などが keyword、`loreley-jobs` は存在し `dynamic: false` | api 1 章、arch 9.8・12 章、search-index 4.1・5.2、loreley-deletions 7 章 |
| IT-02 | `test_02_document_id.py` | テスト側の `document_id` の独立実装(SHA-256(`source_id` + NUL + `external_id`))が、api 4.3 の応答例、README 6 章の正規化規則、Indexer が実際に返す値と一致する(NFC・`\` → `/` を単独と複合で、先頭 `/` と大文字小文字は区別される)。以降のテストの土台 | api 3.3・4.3、`apps/indexer/README.md` 6 章 |
| IT-10 | `test_10_registration.py` | txt・Markdown・HTML・PDF を登録すると `ok` / `created`。抽出した `content`、`content_hash`、`text_hash`、`index_status=indexed`、`summary_status=disabled`、`last_seen_at` が保存され、本文の語句で `_search` に当たる。HTML のタグ・script は本文に残らない。日時は UTC・ミリ秒に正規化されて date 型に受理される | api 3.6・4.3、arch 4.2・5 章、search-index 4.1 |
| IT-11 | `test_10_registration.py` | 壊れた PDF は失敗ではなく `ok` + `extract_failed: true` で登録され、`index_status=extract_failed`。`content`・`text_hash`・要約は持たない | arch K30 |
| IT-12 | `test_10_registration.py` | 同じ内容の再登録は `unchanged` で、全文書き込みをしない(`_seq_no`・`indexed_at` が不変)。`last-seen` を省略した新しいクロールでは `last_seen_at` だけが補われる | arch K27・5 章 |
| IT-13 | `test_10_registration.py` | 本文が変わった再登録は `updated`。`content`・`text_hash`・`content_hash` が更新され、`last_seen_at` はより新しい値を持つ文書では古い値に戻らない(max 比較) | arch K27・5 章 |
| IT-14 | `test_10_registration.py` | `MAX_RAW_BYTES`(テスト用に 64 KiB)を超える原本は、文書単位の `failed` / `oversize` で索引されない。同じバッチの他の文書は成功する。すでに索引にある文書は、のちに上限超過で再送されても書き換わらない。終了通知の `oversize_document_ids` に含めると `E_missing` に数えられる(件数照合は IT-30) | api 4.9、arch K65 |
| IT-15 | `test_10_registration.py` | ロックを所有していない登録と `last-seen`(別の owner・別の `job_id`・期限切れのリース・ロック文書なし)は、文書単位の `failed` / `lock_not_owned` で、何も書かれない | api 3.2 |
| IT-20 | `test_20_crawl_lifecycle.py` | 開始通知が 200 `running`。`deletion-{source_id}`(現行世代)と `deletion_result-{crawl_id}` が `loreley-deletions` に作られ、設定スナップショットが複写される(`dynamic: strict` に通る確認を兼ねる) | api 4.1、arch 9.4・9.5 |
| IT-21 | `test_20_crawl_lifecycle.py` | `last-seen` の部分更新。既存は `updated`、同値の再送は `unchanged`、存在しない ID は `not_found`(404 `document_missing_exception`)。現在値が新しい文書は古い値で上書きしない(painless の max 比較)。秒・マイクロ秒・オフセット付きの入力が UTC・ミリ秒に正規化される | api 3.6・4.2、arch 5 章、U-31(6)(7)(9) |
| IT-22 | `test_20_crawl_lifecycle.py` | 終了通知が 202(ボディなし)。Status に `finish_received_at` が現れ、削除結果が終端状態に進む。未知の `crawl_id` の Status は 404 `crawl_not_found`。未知の `crawl_id` への終了通知は 202 で、記録は作られず Status は 404 のまま | api 4.4・4.5 |
| IT-30 | `test_30_deletion.py` | 期限(TTL)による削除。クロール A(2 時間前開始)で複数の文書を登録し、クロール B(1 分前開始、`ttl=600`)で一部だけを見て終了通知すると、B で見なかった文書だけが削除され、見た文書(新規・変更なし・抽出失敗など)は残る。Status は `deleted` で、`enumerated_count`・`n_seen`・`e_missing`・`target_count`・`denominator`・`deleted_count` が設計書の定義どおりの値になる(`denominator` は削除前の同ソースの索引件数)。他のソースの期限切れ文書は消えない。A 自体の終了は対象 0 件で `deleted` | arch 9.2・9.3・9.6〜9.8 |
| IT-31 | `test_30_deletion.py` | 削除対象が `DELETION_BATCH_SIZE`(2)と `SEARCH_AFTER_PAGE_SIZE`(2)の複数倍あるとき、複数ページ(`search_after`、`document_id` ソート)・複数バッチの削除が、漏れ・重複なく完了し `deleted_count` が対象件数と一致する。ページ数は、検索インデックスの検索回数(`_stats/search` の `query_total`)の差分で実測する。**バッチ数は直接観測できず、設定値と件数からの推定**(後述) | arch 9.8・K47、U-31(12) |
| IT-40 | `test_40_source_deletion.py` | ソース削除 1(`POST .../deletions:discard`)。終端でない削除結果(`running`)が `discarded`(理由 `source_deleted`)になり `discarded_crawl_ids` で返る。終端状態の結果と他のソースには触れない。再実行は空(冪等) | api 4.6、arch 9.14 |
| IT-41 | `test_40_source_deletion.py` | ソース削除 2(`DELETE .../documents`)。ソースの文書をすべて削除して件数を返し、完了後の `_count` は 0。他のソースは残る。再実行は 0 件で成功。ロックを所有していなければ 409 `lock_not_owned` で何も消えない。**登録直後で検索可能でない文書も削除できる**(実行前の refresh。`refresh_interval=-1` で作った状態で、`delete_by_query` の実行回数が 1 回であることで確認) | api 3.2・4.7、arch K20・K28・K60、U-31(5)(11) |
| IT-42 | `test_40_source_deletion.py` | ソース削除 3(`DELETE .../deletion-records`)。ソースの `deletion-*` と `deletion_result-*` が消え、Status は 404。他のソースの記録は残る。同じソースに複数の `deletion_result` があっても、すべて消える。再実行は `deleted: false`(冪等)。DELETE の JSON ボディ(`lock`)が実際の HTTP で通る | api 3.2・4.8、arch 9.14 |

## 設計書(U-31)との対応と、スコープ外

arch U-31(実機確認が必要な点)のうち、このテストで確認したもの・していないもの。

| U-31 の項目 | 状況 |
| --- | --- |
| (5) `delete_by_query` の実行前 refresh と完了後 `_count` | 確認(IT-41)。再実行の上限の数値は**未実施** |
| (6) Update のスクリプト(params で値を渡す形) | 確認(IT-21・IT-12) |
| (7) 日時の `Instant` パースと、date 型との整合 | 確認(IT-10・IT-20・IT-21) |
| (9) 404 の本文の形 | 一部を確認: `update` の `document_missing_exception`(IT-21)、`GET` で文書がないときの 404(`found: false`。IT-01・IT-22)。`index_not_found_exception` は、Status API の GET(`loreley-deletions` を削除した後)を手動で再現して観測した(結合テストには含めていない。結果記録 5 章の発見事項 2)。`update` 系・書き込み系の `index_not_found_exception`、`result:not_found` は**未実施** |
| (11) refresh 後の `_count` | 確認(IT-41) |
| (12) `search_after` と `document_id` のソート | 確認(IT-31)。複数ページになったことは検索回数の差分で実測、バッチ数は推定 |
| `if_seq_no`(楽観ロック)の基本動作 | IT-12・IT-13・IT-30・IT-31 で副次的に通る(U-31(2)の「存在しない文書への `if_seq_no` 付き操作の応答」は**未実施**) |

**スコープ外(未実施)**: 次は、このテストでは確認していない。

- **割合ルールによる削除の見送り**(`skipped_by_ratio`)と、**件数照合の不一致**(`validation_failed`)。削除の安全機構のため重要だが、範囲に含めない判断をした(IT-31 は `min_delete_count` を大きくして削除を通すので、割合ルールの確認ではない)
- 409 競合の再現(書き込みの 409、`write_conflict`・`update_conflict`)、`retry_on_conflict` の上限と読み直しの上限の値(U-31(3)(4))
- `delete_by_query` の `version_conflicts`・タイムアウトでの再送の抑止(U-31(10))
- 存在しない文書への Delete の `not_found` と `if_seq_no` 付き操作の応答(U-31(1)(2))
- `_reindex`(U-31(8))と、メンテナンスフラグ・`rewrite_mode`
- 要約(要約生成は無効。LLM プロバイダが未実装)
- シャードの部分失敗の応答形(U-31(13))
- 認証・TLS の経路、日本語アナライザ、日本語 PDF の抽出品質

## テスト設計上の注意

- **TTL は実時間で待たない**: クロール A の `crawl_started_at` を現在の 2 時間前、クロール B を 1 分前、`ttl=600` にして、「期限切れ」と「期限内」を `sleep` なしで決定的に作る(`support.py` の `EXPIRED_AGE`・`RECENT_AGE`・`TTL_SECONDS`)。数分のホストと Docker VM の時計のずれには耐える。待つのは削除ワーカーの走査だけ(`compose.test.yaml` で 1 秒間隔。Status を 0.5 秒間隔・上限 30 秒でポーリング)
- **IT-41 は `refresh_interval=-1` を使う**: 検索インデックスの自動 refresh を止めて登録し、「検索可能でない状態」を作ったうえで削除する。テスト側の `_count` は refresh してから数えるため、そのままでは、Indexer が `delete_by_query` の前に refresh しているかどうかを隠してしまう。設定はテストの最後(失敗時も)に既定へ戻す
- **`force_last_seen_at` の直接書き込みは前提作りに限る**: max 比較(`last_seen_at` が古い値に戻らない)の確認には、受理中のクロールより新しい `last_seen_at` を持つ文書が要るが、通常の API の流れでは作れない。そのため OpenSearch に直接書き込む(`support.py` の `OpenSearchProbe.force_last_seen_at`)。使うのは IT-13・IT-21 の前提作りだけで、確認の対象(結果の判定)には使わない
- **IT-31 のバッチ数は推定**: `DELETION_BATCH_SIZE=2` が効いていること(バッチ数)は、API・ログ・統計のいずれでも直接観測できず、設定値と件数からの推定である。バッチサイズが効いていなくてもテストは通る。ページ数は検索回数の差分で実測するので、`SEARCH_AFTER_PAGE_SIZE` の設定が効いていることは確認できる。全削除対象の `last_seen_at` が同値なので、`search_after` のソートに `document_id` の tiebreak がなければ、ページ境界の取りこぼし・重複で落ちるはず(実装から tiebreak を取り除いた状態での確認は未実施。レビューによる判断)
- **ID はテストごとに一意**: `source_id`・`crawl_id` はテストごとに作る(フィクスチャ)。テストはデータを削除しないので、一意でないと互いに干渉する。実行順に依存するテストは作らない
- **検証は Indexer の応答だけで済ませない**: OpenSearch を直接読む(検索系は `_refresh` してから `_count`・`_search`)
- **実機が設計と違ったとき**: テストを実機に合わせて変えず、発見事項として扱う(設計書の改版はユーザー判断)

## サンプル文書を追加する

登録に使う固定の原本は `samples/` にある。形式ごとの期待する抽出結果と、PDF の生成方法は [samples/README.md](samples/README.md) を参照。サンプルを追加するときは、そこに期待する抽出結果の要点を書き、検索に使える一意の語を入れる。日本語の PDF は抽出品質が未検証のため使っていない。

## ファイル構成

| パス | 内容 |
| --- | --- |
| `pyproject.toml` / `uv.lock` | テスト専用の依存(`pytest`・`httpx`。dev に `ruff`)。Indexer の依存とは分けている。`uv.lock` で固定している |
| `compose.test.yaml` | Indexer のテスト用の上書き(原本上限、削除のバッチ・ページの件数、走査間隔)。`deploy/compose` には混ぜない |
| `conftest.py` | フィクスチャと、起動済みのスタックへの疎通確認 |
| `support.py` | Crawler 役のクライアント、OpenSearch の検証ヘルパ、`document_id` の独立実装(Indexer のコードは import しない)、時刻ヘルパ |
| `test_*.py` | シナリオ別のテスト(上の表) |
| `samples/` | 固定のサンプル文書 |
| `results/` | スクリプトの実行ログ(`.gitignore` 済み) |
