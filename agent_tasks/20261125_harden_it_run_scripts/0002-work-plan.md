# 0002 作業プラン: IT 実行スクリプト 3 本の安全性の統一と排他ロック

日付: 2026-11-26 / 作成: planner(メインエージェントが保存)/ 状態: **ユーザーの承認待ち**
参照: `0000-requirements-definition.md`、`0001-clarify-requirements.md`(0000 より優先)

## 1. 目的とゴール

Crawler・Indexer・api の IT 実行スクリプト 3 本を、api IT(PR #19 の対応後)と同じ安全性の方針に揃える。あわせて、共通の排他ロックで同時実行を拒否し、重複している処理を `scripts/lib/` の共通ファイルにまとめる。

受け入れ基準(0001「完了条件と検証方法」1〜6 と同じ):
1. 3 本とも次の方針が同じ: URL の固定、事前確認の安全側の失敗処理(`docker ps -a`・`docker volume ls` の失敗で中止、`data/` は存在確認と一覧取得を分ける、Indexer にコンテナ・ボリュームの残骸確認を追加)、後始末に失敗したときの終了コード 11
2. 同時実行を拒否できる。後から起動した側は終了コード 1 で、保持者の情報を表示して中止し、何も消さない
3. 残ったロックは自動では消さない。INT・TERM・`--keep` の後にロックが残らない。`--help` と引数エラーではロックを作らない
4. Crawler 14 件・Indexer 40 件・api 23 件が終了コード 0 で成功し、実行後に残骸がない(コンテナ・ボリューム・`data/`・ロック)
5. `bash -n` を通る。shellcheck は使えれば実行し、使えなければ未実施と明記する
6. README 3 つと結果文書 3 つが更新されている(結果文書は追記のみ)

## 2. 確定事項・前提

### 0001 から引き継ぐ確定事項
- Q1: Indexer IT に残骸の確認を追加する(コンテナ・ボリューム・ポート使用中の相手の表示。`data/` は確認しない)
- Q2: 共通の関数ファイルを `scripts/lib/` に作り、3 本から `source` する。usage の表示(ヘッダコメントを読む方式)と `info` の接頭辞は、スクリプトごとに残す
- Q3: 通常終了と INT・TERM ではロックを必ず解除する。SIGKILL などで残ったロックは自動では消さず、保持者の PID・開始時刻・スクリプト名を表示し、`rm -rf <ロック>` の手順を案内して中止する
- ロック: `mkdir` 方式、`${TMPDIR:-/tmp}/loreley-it.lock`、引数解析と環境変数の検証の後・事前確認の直前に取得、取れなければ終了コード 1(新しい終了コードは作らない)、`--keep` でも終了時に解除
- 固定する環境変数の差(Crawler の `LORELEY_CRON_TIMEZONE=UTC`・`LORELEY_ADMITTING_LOCK_GRACE_SECONDS=60`、api の `Asia/Tokyo`・`LORELEY_IT_ALLOW_COMPOSE_CONTROL=1` など)は今のまま残す
- スコープ外: `apps/`、テストケース、`deploy/compose/`、CI、並行実行の実現、pytest・compose を手で実行したときの排他

### このプランで決める事項(0001「プランで決める事項」への回答)

**(a) 共通ファイル**: `scripts/lib/it-common.sh`。実行権限と shebang は付けない。先頭に `# shellcheck shell=bash`。定数・関数の定義だけを持ち、読み込んだだけでは何も実行しない(`set` もしない。`set -euo pipefail` は呼び出し側)。

**(b) 読み込み方(各スクリプトの冒頭)**:
```bash
set -euo pipefail
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
it_common="${script_dir}/lib/it-common.sh"
if [ ! -f "$it_common" ] || [ ! -r "$it_common" ]; then
  echo "Error: 共通ファイルが見つからないか、読めません: ${it_common}" >&2
  exit 1
fi
# shellcheck source=lib/it-common.sh
source "$it_common"
```
- `source ... || exit 1` とは書かない(`||` の文脈では読み込み中に `set -e` が効かないため)
- `usage` は `sed -n '2,/^set -euo pipefail$/p'` でヘッダを読む。`set -euo pipefail` の行はヘッダの直後に残す

**(c) インタフェース**(各スクリプトが `run_integration_test` を呼ぶ前に定義する変数)

| 変数 | 型・用途 | Crawler | Indexer | api |
| --- | --- | --- | --- | --- |
| `IT_SCRIPT_NAME` | `info` の接頭辞・ロックの保持者名 | `run-crawler-integration-test` | `run-indexer-integration-test` | `run-api-integration-test` |
| `IT_COMPOSE_TEST_FILE` | ルートからの相対パス | `tests/integration/crawler/compose.test.yaml` | `.../indexer/...` | `.../api/...` |
| `IT_PORTS` | 配列 `"表示名:ポート"`(ポート確認・`--keep` の表示) | OpenSearch:9200 Indexer:8000 Crawler:8001 | OpenSearch:9200 Indexer:8000 | 左の 3 つ + api:8080 |
| `IT_SERVICES` | 配列(`up -d --build` に渡す) | opensearch opensearch-init indexer crawler | opensearch opensearch-init indexer | 左 + api |
| `IT_WAIT_CHECKS` | 配列 `"サービス:healthy\|exited_ok"` | 現行の `checks` と同じ | 同左 | 同左 |
| `IT_DOCUMENTS_DIR` | 絶対パス。空なら `data/` を扱わない | `${root_dir}/tests/integration/crawler/data` | 空 | `.../api/data` |
| `IT_RESULTS_DIR` | 相対パス | `tests/integration/crawler/results` | `.../indexer/results` | `.../api/results` |
| `IT_REQUIRE_UV` | `true`/`false` | true | `LORELEY_IT_PYTEST_CMD` 指定時だけ false | true |
| `pytest_cmd` | 配列 | 現行どおり | 現行どおり(`LORELEY_IT_PYTEST_CMD` の分割と空白だけの検証は Indexer に残す) | 現行どおり(`-v -rP`) |

- `export` する固定値(ポート、`LORELEY_IT_*_URL`、索引名、タイムゾーンなど)と `CRAWLER_DOCUMENTS_DIR` は各スクリプトに残す。Crawler・Indexer に URL の固定を追加する(Crawler: OPENSEARCH・INDEXER・CRAWLER、Indexer: OPENSEARCH・INDEXER)
- ポートの数値は `readonly OPENSEARCH_PORT=9200` などを各スクリプトに残し、`export` と `IT_PORTS` の両方で使う

**共通ファイルの定数**: `PROJECT_NAME=loreley-it`、`POLL_INTERVAL_SECS=3`、`LOG_TAIL_LINES=100`、`MIN_MAX_MAP_COUNT=262144`、`EXIT_USAGE_OR_PREREQUISITE=1`、`EXIT_STARTUP_FAILED=10`、`EXIT_CLEANUP_FAILED=11`、`IT_LOCK_DIR`(`${TMPDIR:-/tmp}` の末尾の `/` を除いたもの + `/loreley-it.lock`。macOS の `TMPDIR` は `/` で終わるため)

**共通ファイルの関数**:
- `error` / `info`(接頭辞は `[${IT_SCRIPT_NAME}]`)、`compose`(`-p loreley-it -f deploy/compose/compose.yaml -f "$IT_COMPOSE_TEST_FILE"`)
- `parse_common_args "$@"`: `-h`/`--help` は各スクリプトの `usage` を呼んで `exit 0`。`--keep` を解釈し、それ以外は `pytest_args` へ。`LORELEY_IT_WAIT_TIMEOUT_SECS` も検証(現行 3 本と同じ)
- `acquire_lock` / `release_lock`((d) 参照)
- `check_prerequisites`: docker・compose・デーモン・uv(`IT_REQUIRE_UV` のとき)→ `check_no_leftover_stack` → `check_no_leftover_data` → `check_ports_are_free` → `warn_if_max_map_count_is_low`。api の現行実装(`scripts/run-api-integration-test.sh:141-281`)をそのまま移し、`data/` の確認は `IT_DOCUMENTS_DIR` が空でないときだけ行う。案内に出す compose コマンドは `IT_COMPOSE_TEST_FILE` から組み立てる
- `is_port_in_use`・`describe_port_owner`・`probe_service`・`wait_for_stack`(`IT_WAIT_CHECKS` を使う)・`print_diagnostics`
- `on_exit`(現行 `cleanup` を広げたもの。(d) 参照)
- `run_integration_test`: trap 登録 → ロック取得 → 事前確認 → 後始末の有効化 → `data/` の作成と `chmod 755`(`IT_DOCUMENTS_DIR` があるとき)→ `compose up -d --build "${IT_SERVICES[@]}"` → 待機 → pytest と `tee` → `exit`(後半は現行 `run-api-integration-test.sh:438-473` と同じ)
- 各スクリプトの本体: ヘッダ、`set`、`source`、`export`、変数定義、`usage`、`parse_common_args "$@"`、(Indexer のみ)`LORELEY_IT_PYTEST_CMD` の処理、`run_integration_test`。Indexer の「起動するサービスを明示している理由」のコメント(現行 295-296 行)は `IT_SERVICES` の定義の横に移す

**bash 3.2 との互換**(macOS の `/bin/bash`): 連想配列、`declare -n`、`mapfile`、`${var,,}` を使わない。空の配列は `${arr[@]+"${arr[@]}"}` の形で展開する。

**(d) trap の登録順とロック**: 先に trap を登録し、ロックの取得と後始末の要否はフラグで判定する。
```
lock_acquired=false
stack_cleanup_armed=false
trap on_exit EXIT; trap 'exit 130' INT; trap 'exit 143' TERM
acquire_lock                      # 成功したら lock_acquired=true
check_prerequisites || exit 1     # 失敗: スタック・data/ に触れず、ロックだけ解除
stack_cleanup_armed=true          # ここから先の失敗では down -v などを行う
mkdir data / compose up / wait / pytest
```
- `acquire_lock`: `mkdir "$IT_LOCK_DIR"` に成功したら、まず `lock_acquired=true`、続けて `owner` ファイルに `pid=$$`・`started_at=$(date '+%Y-%m-%dT%H:%M:%S%z')`・`script=${IT_SCRIPT_NAME}` を書く。書き込み失敗は `exit 1`(trap がロックを解除)
  - `mkdir` 失敗でロックが存在: 「別の結合テストが実行中か、前回の実行が異常終了してロックが残っています」と出し、`owner` の内容を表示して終了コード 1 で中止。`owner` が読めないときは「保持者の情報を読めません(作成直後の可能性があります)」。手順として、`ps -p <PID>` で保持者が動いていないことを確かめてから `rm -rf '<ロック>'` するよう案内。何も消さない
  - `mkdir` 失敗でロックも存在しない(`TMPDIR` の権限など): 「ロックを作成できません」で終了コード 1
- `release_lock`: `lock_acquired=true` のときだけ。`owner` の pid が `$$` と一致するとき(`owner` が無ければ自分で作ったとみなす)に `rm -rf "${IT_LOCK_DIR:?}"`。不一致なら消さずに警告。取得に失敗した側は `lock_acquired=false` なので相手のロックに触れない
- `on_exit`: 終了コードを控える → `trap - EXIT INT TERM`・`set +e` → `stack_cleanup_armed=true` のときだけ現行の後始末(終了コード非 0 なら診断表示、`--keep` なら残す、それ以外は `down -v` が成功したときだけ `data/` を削除、`cleanup_failed` を記録。Indexer は `data/` なし)→ `release_lock`(失敗したら `cleanup_failed=true`)→ 終了コード 0 で `cleanup_failed=true` なら 11、それ以外は控えた終了コード
- `--help` と引数エラーは `run_integration_test` より前に `exit` するので、trap もロックも作らない
- 残るリスク: `mkdir` 成功から `lock_acquired=true` までの間にシグナルを受けるとロックが残る(手動解除。Q3 と同じ扱い)

**(e) 検証用の偽の `docker`**: スクラッチパッド(例 `<scratchpad>/fake-docker/docker`、`chmod +x`)に置き、リポジトリには入れない。全文は作業記録に残す。
```bash
#!/usr/bin/env bash
# 検証専用。指定した 1 種類の呼び出しだけを失敗させ(または待たせ)、それ以外は本物の docker に渡す。
set -u
real="${FAKE_DOCKER_REAL:?本物の docker の絶対パスを指定する}"
has_arg() { local a; for a in "${@:2}"; do [ "$a" = "$1" ] && return 0; done; return 1; }
case "${FAKE_DOCKER_MODE:-}" in
  fail-ps-a)         [ "${1:-}" = ps ] && has_arg -a "$@" && { echo "fake: docker ps -a を失敗させた" >&2; exit 1; } ;;
  fail-volume-ls)    [ "${1:-}" = volume ] && [ "${2:-}" = ls ] && { echo "fake: docker volume ls を失敗させた" >&2; exit 1; } ;;
  fail-compose-down) [ "${1:-}" = compose ] && has_arg down "$@" && { echo "fake: compose down を失敗させた" >&2; exit 1; } ;;
  hang-info)         [ "${1:-}" = info ] && exec sleep 120 ;;
esac
exec "$real" "$@"
```
使い方: `PATH="<fake-dir>:$PATH" FAKE_DOCKER_REAL="$(command -v docker)" FAKE_DOCKER_MODE=fail-ps-a scripts/run-crawler-integration-test.sh`。偽の `docker` は失敗させるか待たせるだけで、何かを消すことはしない。

## 3. 影響範囲

| ファイル | 変更 |
| --- | --- |
| `scripts/lib/it-common.sh` | 新規。共通の定数・関数・`run_integration_test` |
| `scripts/run-api-integration-test.sh` | 共通化(事前確認 `:141-281`、後始末 `:289-346`、起動・待機・pytest `:350-473` を共通ファイルへ)。ロック追加。ヘッダの「同時には動かせない」(`:35`)をロックで拒否する内容に |
| `scripts/run-crawler-integration-test.sh` | 共通化。URL 固定。`docker ps` 失敗の扱い(現行 `:176`)。`data/` の存在確認と一覧取得の分離(現行 `:208`)。終了コード 11(現行 `:268-301`)。ヘッダ更新 |
| `scripts/run-indexer-integration-test.sh` | 共通化。URL 固定。残骸確認とポート使用中の相手の表示を追加(現行 `:113-139`)。`down -v` 失敗で終了コード 11(現行 `:177-197`)。ヘッダ更新 |
| `tests/integration/crawler/README.md` | 前提のポート(`:23`)、事前確認(`:47`)、終了コード表(`:49-57`)、「同時に動かせない」(`:98-107`)、ロックの置き場所と手動解除 |
| `tests/integration/indexer/README.md` | `:45`、終了コード表(`:47-55`)、`:86`(URL 固定)、`:95-96`、事前確認の条件(追加分)、ロック |
| `tests/integration/api/README.md` | `:31`(同時実行)、`:179`(事前確認)、終了コード 11(`:64`。ロック解除失敗を含める)、ロック |
| `docs/v0.x/test-results/{crawler,indexer,admin-api}-integration.md` | 末尾に再実行の記録の章を追記(既存の章は変えない) |

変更しないもの: `apps/`、`tests/integration/*/` の Python・compose、`deploy/compose/`。

## 4. 実装フェーズ

各フェーズが終わるたびに、メインエージェントが作業記録を作り、`STATUS.md` を更新する。

### Phase 0: 基準の記録(メインエージェント)
- 基準のコミット SHA(`git rev-parse HEAD`)を記録する。必要なら作業ブランチを作る
- 実行前の状態を控える: `docker ps -a` 全体(他プロジェクトのコンテナ。例 `opensearch-opensearch-1`)、`loreley-it` のコンテナ・ボリュームが無いこと、ロックが無いこと、ポート 9200・8000・8001・8080 が空いていること
- 各スクリプトの `--help` の出力を比較用にスクラッチパッドへ保存する
- 9200 などが別アプリ(Fess など)に使われていたら、止めずにユーザーへ報告して待つ
- 依存: なし

### Phase 1: 共通ファイルの実装と api の移行(`code-implementer`)
- `scripts/lib/it-common.sh` を 2 章 (a)〜(d) のとおりに作る
- api のスクリプトを移行する。api は基準の実装なので、事前確認と後始末の方針を変えずに移すことを最優先にする
- 検証: `bash -n`(2 ファイル)。`--help` の出力を Phase 0 と比べ、差分が意図したヘッダの追記だけであること。`LORELEY_IT_WAIT_TIMEOUT_SECS=abc` で終了コード 1、ロックが作られないこと
- 依存: Phase 0

### Phase 2: Crawler・Indexer の移行(`code-implementer`。Phase 1 と同じ依頼にまとめてもよい)
- 2 本を共通ファイルへ移行し、URL の固定・残骸の確認(Indexer は追加)・終了コード 11 を反映。ヘッダコメントも更新
- 検証: `bash -n`、`--help` の比較、引数エラーで終了コード 1・ロックが作られないこと(Indexer は `LORELEY_IT_PYTEST_CMD="  "` も確認)
- 依存: Phase 1

### Phase 3: Docker を起動しない検証(メインエージェント)
スタックは作られない。数秒〜数十秒。
1. `fail-ps-a` を 3 本で確認。終了コード 1、「docker ps に失敗」と表示、何も作られない(コンテナ・ボリューム・`data/`)、終了後にロックが無い
2. `fail-volume-ls` を Crawler・Indexer で確認(期待は 1 と同じ)
3. Crawler の `data/` を `chmod 000` にして、終了コード 1 で中止し `data/` が残ること。その後権限を戻して削除
4. 残ったロック: `hang-info` で起動(バックグラウンド)し、ロックができたら `kill -9`(`sleep` の子プロセスも止める)。ロックが残ることを確認。次に Crawler を実行し、終了コード 1、保持者の PID(kill した PID と一致)・開始時刻・スクリプト名・`rm -rf` の手順が表示され、何も消さないこと。手動で `rm -rf` したあと `fail-ps-a` で実行し、ロックを取ってから docker ps の失敗で止まり、終了後にロックが無いこと
5. INT: `hang-info` で待機中に INT を送る。終了コード 130、ロックが無い、`down` が呼ばれていないこと。注意: 非対話シェルのバックグラウンド実行では SIGINT が無視されるため、`perl -e '$SIG{INT}="DEFAULT"; exec @ARGV' scripts/...` で起動するか `set -m` のもとで起動する
6. `--help`(3 本)が終了コード 0 で、ロックを作らないこと
- 依存: Phase 2

### Phase 4: コードのレビュー(5 章 R1)
Docker を使う検証は時間がかかるため、先にレビューで修正を済ませ、Phase 5 を最終のコードで 1 回だけ実行する。

### Phase 5: Docker を使う検証と全件実行(メインエージェント。Phase 4 の修正後のコードで)
各実行に `caffeinate -i` を付ける。長い実行はバックグラウンドで走らせ、ログとロックを見ながら待つ。各実行の前後で `loreley-it` のコンテナ・ボリュームの一覧と `docker ps -a` 全体(他プロジェクト)を控える。
1. Crawler の終了コード 11 と URL 固定: `fail-compose-down` と `LORELEY_IT_{OPENSEARCH,INDEXER,CRAWLER}_URL=http://127.0.0.1:9999` を指定し、`-k test_01_startup` で実行。テストが成功し終了コード 11、`data/` を削除しない案内が出て、ロックが無いこと。その後、本物の docker で `docker compose -p loreley-it -f deploy/compose/compose.yaml -f tests/integration/crawler/compose.test.yaml down -v --remove-orphans` を実行し、`data/` を削除
2. Indexer: (i) `fail-compose-down` と URL 上書きで `-k test_01` を実行し、終了コード 11(スタックは残る)。(ii) そのまま Indexer を実行し、残ったコンテナを検出して終了コード 1 で中止、コンテナ ID が変わらないこと。(iii) 本物の docker で `down`(`-v` なし)してから Indexer を実行し、残ったボリュームを検出して中止。(iv) `down -v --remove-orphans` で片付ける
3. Indexer の `--keep`: `--keep -k test_01` で実行。終了後にロックが無く、スタックが残っていること。その後 `down -v` で片付ける
4. TERM: Indexer の起動待機中に TERM を送る。終了コード 143、後始末が行われてコンテナ・ボリュームが残らず、ロックが無いこと
5. 同時実行の拒否: 1 本目に Crawler の全件をバックグラウンドで起動。ロックができ、ログに「スタックの起動を待っています」が出たら、2 本目として Indexer と Crawler を 1 回ずつ起動。どちらも終了コード 1 で保持者の情報が表示されること。2 本目の前後で `loreley-it` のコンテナ ID・ボリューム・Crawler の `data/` が変わらないこと。1 本目が 14 passed・終了コード 0 で終わり、残骸が無いこと(受け入れ基準 4 の Crawler を兼ねる)
6. 全件実行: Indexer(40 件)、api(23 件)をそれぞれ終了コード 0 で終える。終了後にコンテナ・ボリューム・`data/`・ロックが無く、他プロジェクトのコンテナが Phase 0 と同じであること
7. `command -v shellcheck` を確認(無ければ未実施と記録)。`bash -n` を 4 ファイルで実行
- 結果(終了コード・件数・所要時間・ログのファイル名・偽の `docker` の全文)を作業記録に残す
- 依存: Phase 4 の Critical・Important がすべて解消していること

### Phase 6: README と結果文書の更新(`document-writer`)
- README 3 つ(3 章の箇所)を更新: 終了コード 11、接続先 URL の固定(Crawler・Indexer)、事前確認で中止する条件(Indexer は追加分)、同時実行をロックで拒否すること、ロックの置き場所(`${TMPDIR:-/tmp}/loreley-it.lock`)と手動解除の手順(保持者の PID の確認 → `rm -rf`)、`--keep` でもロックは解除されること、`TMPDIR` が異なる環境(別ユーザー・`sudo` など)から起動したものとは排他されないこと
- 結果文書 3 つに Phase 3・5 の結果を章として追記(既存の章は書き換えない)
- 依存: Phase 5

### Phase 7: 文書のレビュー(5 章 R2)
### Phase 8: タスクレビュー(7 章)

## 5. レビューフェーズ

基準: Phase 0 で記録したコミット SHA からの差分。すべてのレビューに、`agent_tasks/20261125_harden_it_run_scripts/` の 0000・0001・このプラン・該当する作業記録を渡す。

### R1(Phase 4): `code-reviewer` と `test-reviewer`(並列)
- 対象: `scripts/lib/it-common.sh`、`scripts/run-{api,crawler,indexer}-integration-test.sh`
- `code-reviewer`(必須。`down -v`・`rm -rf` によるデータ削除と安全確認に直結するため)の重点:
  - 事前確認が安全側に倒れているか(`||` の文脈での `set -e`、失敗と空の出力の区別)
  - trap とフラグの順序。事前確認の失敗・ロック未取得のときに、スタック・`data/`・相手のロックを消さないか
  - 終了コードの優先順位
  - bash 3.2 との互換
  - api の挙動を変えていないか
- `test-reviewer`(実行スクリプトは IT の土台なので実施)の重点:
  - 3 本の pytest の起動(コマンド・既定の引数・環境変数)が移行の前後で変わらないか
  - Phase 3・5 の検証手順が受け入れ基準 1〜5 を漏れなく示せるか(偽の `docker` を含む)
  - Phase 3 の結果
- Phase 5 の後にスクリプトを変えた場合は、変えた差分について R1 をもう一度受け、関わる Phase 5 の項目を再実行する。共通の流れ(`on_exit`・`run_integration_test`・ロック)を変えた場合は全件実行(5-5・5-6)も再実行する

### R2(Phase 7): `document-reviewer`
- 対象: `tests/integration/{crawler,indexer,api}/README.md`、`docs/v0.x/test-results/{crawler,indexer,admin-api}-integration.md`
- 重点: スクリプトの実際の挙動(終了コード・中止条件・ロック)と記述の一致、結果文書が追記だけか、未検証のことを「確認済み」と書いていないか

`web-ui-reviewer` は実施しない(Web UI の変更がないため)。

## 6. レビュー指摘への対応

- Critical・Important: 該当フェーズに戻って修正し、同じレビュアーに再レビューを依頼。修正に関わる検証(Phase 3・5 の該当項目)を再実行。すべて解消するまでレビューフェーズを完了としない
- Suggestion・Nitpick: 対応の要否を判断し、判断と理由を作業記録に残す。0001 に無い機能を足す提案は原則見送る(MVP)

## 7. タスクレビューフェーズ

実施する(フェーズが複数あり、データ削除の安全性に関わり、複数セッションにまたがる見込みのため)。
- 時期: R1・R2 が完了し(Critical・Important 解消済み)、すべての作業記録を作った後
- 担当: `task-reviewer`。渡す文脈はタスク名(`agent_tasks/20261125_harden_it_run_scripts/` 配下すべて)
- 観点: 0001 の要件・完了条件とこのプラン、作業記録、実際の差分、検証結果の突き合わせ(コードそのもののレビューは R1 と重複させない)
- 指摘対応: Critical・Important は該当工程へ差し戻して修正し、再度レビュー。Suggestion・Nitpick は判断を作業記録に残す

## 8. テスト方針

- 静的検査: `bash -n`(4 ファイル)。shellcheck は使えれば実行し、使えなければ未実施と明記
- 擬似的な故障の注入(Phase 3): 偽の `docker` を PATH の先頭に置き、`docker ps -a`・`docker volume ls`・`compose down` の失敗と `docker info` の待ちを作る。シグナル(INT・SIGKILL)と `data/` の権限で異常系を作る
- 実際のスタック(Phase 5): 終了コード 11、URL の上書きが効かないこと、Indexer の残骸の検出、`--keep`、TERM、同時実行の拒否、3 本の全件実行
- 判定の根拠: 終了コード、標準エラー出力の文言、実行前後の `docker ps -a` / `docker volume ls`(`loreley-it` と全体)、`data/` とロックの有無、pytest の件数
- アプリと IT のテストケースは変えないので、単体テストは再実行しない

## 9. リスクと対策

| リスク | 対策 |
| --- | --- |
| Docker を使う IT は時間がかかる(api は 1 回 5〜10 分) | 検証を Phase 3(Docker なし)と Phase 5 に分ける。R1 を Phase 5 の前に行い、Phase 5 を最終コードで 1 回だけ実行。同時実行確認の 1 本目を Crawler 全件実行と兼ねる。バックグラウンドで実行しログを見て待つ |
| 他プロジェクトのコンテナ(9200 の Fess、`opensearch-opensearch-1` など)に触れる | スクリプトは `-p loreley-it` だけを操作する。手動の後始末も必ず `-p loreley-it` と compose ファイルを指定。`docker rm`・`docker volume prune`・`docker system prune` は使わない。ポート使用中なら止めずにユーザーへ報告。前後の `docker ps -a` 全体を比べる |
| 偽の `docker` の検証でスタックが残る | 直後に本物の docker で `-p loreley-it` の `down -v --remove-orphans` を実行し、`data/` を削除。残骸が無いことを確かめてから次へ |
| 非対話シェルのバックグラウンド実行で SIGINT が無視される | perl で SIGINT を既定に戻して exec、または `set -m`(Phase 3-5) |
| `kill -9` で `sleep` の子プロセスやロックが残る | 子プロセスの PID を控えて止める。ロックは手動解除の手順で消す(検証の一部) |
| ホストのスリープで IT が失敗する | `caffeinate -i` を付ける |
| `TMPDIR` が異なる環境間では排他されない | 0001 の前提(MVP)として README に明記。検証は同じシェル環境から行う |
| macOS の bash 3.2 で動かない書き方 | 2 章の互換規則を守る。R1 の重点に含める。macOS で実際に実行して確かめる |
| 共通化で api の挙動が変わる | Phase 1 で `--help` を比べ、Phase 3 で故障注入、Phase 5 で全件実行。R1 の重点に含める |
| ロールバック | 変更はスクリプト 4 つと文書だけ。基準 SHA へ `git checkout`/`git revert`(`scripts/lib/` を削除) |

## 10. 判断理由(planner)

- 共通ファイルに `run_integration_test`(起動〜pytest)まで含める: Q2 で「起動するサービスと待つ条件」「pytest のコマンドと既定の引数」を変数で渡すと決めたため、起動と pytest も共通側で行う前提と読める。後半はほぼ同じ内容なので、共通側に置けば安全性の修正が 1 か所で済む
- trap を先に登録しフラグで判定: ロックは事前確認より前に取るので、事前確認が失敗してもロックを解除する必要がある。一方 `down -v` は事前確認を通るまで行ってはならない。そこで後始末を `lock_acquired`・`stack_cleanup_armed` の 2 フラグで分けた。後から trap を登録する方式は、取得から登録までの間のシグナルでロックが残るので選ばない
- ロック解除の失敗も終了コード 11 に含める: ロックが残ると次の実行が止まるので「残骸あり」として扱う(軽微な扱いの決定。README に書く)
- `test-reviewer` を実施: 実行スクリプトは IT の土台で、受け入れ基準のほとんどは検証手順で示すため
- R1 を Docker の検証より前に置く: 検証 → README → レビューの順だと、レビューの修正のたびに時間のかかる実行をやり直すことになるため
- 追加しないもの: ロックの自動解除、保持者が生きているかの自動判定、並行実行、CI(0001 の範囲外。MVP)

## 11. 未解決事項

- 0000 の As-Is(14 行目)は Indexer の現状と合っておらず、対象範囲に結果文書がない(0001 で補った。0000 を直すかはユーザー判断)
- shellcheck は現ホストに無い見込み(Phase 5-7 で確認し、無ければ未実施と明記)
