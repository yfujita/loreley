#!/usr/bin/env bash
# Indexer の結合テストを、compose の起動 → 待機 → pytest → 後始末まで一括で実行する。
#
# 使い方: scripts/run-indexer-integration-test.sh [--keep] [pytest の引数...]
#   例: scripts/run-indexer-integration-test.sh              # 全シナリオ
#       scripts/run-indexer-integration-test.sh --keep       # 終了後もスタックを残す(デバッグ用)
#       scripts/run-indexer-integration-test.sh -k test_30_deletion  # テストを絞る(-k。ファイル名の語でも絞れる)
#   ※ 絞り込みは `-k` を使う。ファイルやノード ID(`ファイル::テスト名`)をパス引数で渡しても、既定のコマンドの
#     末尾に `tests/integration/indexer` があるため絞られず、全テストが走る。1 テストだけを指定したいときは、
#     `--keep` でスタックを残し、pytest を直接実行する(tests/integration/indexer/README.md の「手動で実行する」)。
#   ※ シナリオ ID(IT-nn)はテスト名に含まれないため、`-k IT-30` では 0 件になる(終了コード 5)。
#     ID とファイルの対応は tests/integration/indexer/README.md を参照。
#
# 終了コード:
#   pytest の終了コード(0=全成功。1〜5 は pytest の定義どおり)
#   1  引数・事前確認の失敗、またはロックを取れなかった(pytest の終了コードと重なるが、これらの失敗は標準エラー出力に出る)
#   10 スタックの起動失敗(待機の上限超過・コンテナの異常終了を含む)
#   11 pytest は成功したが、後始末(`down -v`・ロックの解除)に失敗した(テスト失敗のときは pytest の終了コードを優先)
#   130/143 Ctrl-C(INT)/TERM で中断
#
# 環境変数:
#   LORELEY_IT_WAIT_TIMEOUT_SECS  起動後の待機の上限(秒)。既定 300
#   LORELEY_IT_PYTEST_CMD         pytest を起動するコマンドの置き換え(空白区切りで分割する)。
#                                 既定は `uv run --project tests/integration/indexer pytest tests/integration/indexer -v`。
#                                 uv が使えない環境で、用意済みの venv の pytest を使いたい場合だけ指定する。
#                                 指定すると uv の事前確認は行わない。スクリプトの引数はこのコマンドの後ろに付く。
#   OPENSEARCH_VERSION など         deploy/compose/.env.example の変数は、そのまま compose に渡る。
#                                 ただし、下の「固定する値」(ポート・索引名)は上書きされる。
#
# 固定する値(テストが前提にする):
#   ホスト側ポート 9200・8000、テストの接続先 URL(LORELEY_IT_{OPENSEARCH,INDEXER}_URL を上のポートの 127.0.0.1 に)、
#   削除記録・検索エイリアスの索引名(既定値)。
#
# 設計上の注意:
#   - `docker compose up --wait` は使わない。ホストの compose v2.3.3 では、使い捨てコンテナ
#     (opensearch-init)が正常終了したあとも戻らないことを確認したため(`up -d` + 自前のポーリング)。
#   - プロジェクト名は loreley-it で固定。開発用スタックや無関係なコンテナには触れない。
#     Crawler・api の結合テストとはプロジェクト名・ポートが同じなので、同時には動かせない。
#     排他ロック(${TMPDIR:-/tmp}/loreley-it.lock)で同時実行を拒否する。
#   - 排他ロックは事前確認の直前に取り、終了時(--keep・INT・TERM を含む)に解除する。取れなかったとき
#     (別の結合テストが実行中、または SIGKILL などで残った)は、何も消さず、保持者の PID・開始時刻・
#     スクリプト名を表示して終了コード 1 で中止する。残ったロックは自動では解除しない。保持者が
#     動いていないことを確かめてから、表示される手順(rm -rf)で手動で解除する。
#   - ホスト側ポートは 9200(OpenSearch)と 8000(Indexer)で固定。テストがこの 2 つに接続する。
#   - 終了時の `down -v` が、利用者のデータを消さないよう、事前確認で loreley-it のコンテナ・
#     名前付きボリュームのどちらかが残っていたら、何も消さずに中止する。
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
it_common="${script_dir}/lib/it-common.sh"
if [ ! -f "$it_common" ] || [ ! -r "$it_common" ]; then
  echo "Error: 共通ファイルが見つからないか、読めません: ${it_common}" >&2
  exit 1
fi
# shellcheck source=lib/it-common.sh
source "$it_common"

readonly OPENSEARCH_PORT=9200
readonly INDEXER_PORT=8000
# compose は deploy/compose/.env やシェルの環境変数でホスト側ポートを変えられる。テストは 9200・8000 に
# 接続するので、ここで固定する(シェルの環境変数は .env より優先される)。固定しないと、ポート確認は
# 9200・8000 を見るのに、スタックは別のポートで起動し、テストが「起動していません」と誤って中止する。
export OPENSEARCH_HOST_PORT="$OPENSEARCH_PORT"
export INDEXER_HOST_PORT="$INDEXER_PORT"
# テストの接続先も、compose が publish するポートに固定する。固定しないと、シェルに残った
# LORELEY_IT_*_URL が、ソース登録・削除や OpenSearch への直接書き込みを、このスクリプトが
# 起動したのとは別の環境に向けてしまう(pytest を直接実行するときだけ、環境変数で変えられる)。
export LORELEY_IT_OPENSEARCH_URL="http://127.0.0.1:${OPENSEARCH_PORT}"
export LORELEY_IT_INDEXER_URL="http://127.0.0.1:${INDEXER_PORT}"
# 削除記録・検索エイリアスの索引名も同じ理由で固定する。シェルや deploy/compose/.env で別の名前にされていると、
# スタックだけが別の索引を使って、テストが失敗する。
export LORELEY_DELETIONS_INDEX_NAME="loreley-deletions"
export LORELEY_SEARCH_INDEX_ALIAS="loreley-documents"

root_dir="$(cd "${script_dir}/.." && pwd)"
cd "$root_dir"

usage() {
  sed -n '2,/^set -euo pipefail$/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//'
}

IT_SCRIPT_NAME="run-indexer-integration-test"
IT_COMPOSE_TEST_FILE="tests/integration/indexer/compose.test.yaml"
IT_PORTS=("OpenSearch:${OPENSEARCH_PORT}" "Indexer:${INDEXER_PORT}")
# 起動するサービスを明示する。compose.yaml に crawler がある(依存先ではない)ので、指定しないと
# crawler まで起動してしまい、Indexer の結合テストの範囲外のビルド・メモリを使う。
IT_SERVICES=(opensearch opensearch-init indexer)
IT_WAIT_CHECKS=("opensearch:healthy" "opensearch-init:exited_ok" "indexer:healthy")
# Indexer の結合テストは検索対象の文書(data/)を使わない。
IT_DOCUMENTS_DIR=""
IT_RESULTS_DIR="tests/integration/indexer/results"

default_pytest_cmd="uv run --project tests/integration/indexer pytest tests/integration/indexer -v"
pytest_cmd_string="${LORELEY_IT_PYTEST_CMD:-$default_pytest_cmd}"
# LORELEY_IT_PYTEST_CMD を指定したときは、uv を使わないので事前確認しない。
if [ -n "${LORELEY_IT_PYTEST_CMD:-}" ]; then
  IT_REQUIRE_UV=false
else
  IT_REQUIRE_UV=true
fi

parse_common_args "$@"

read -r -a pytest_cmd <<<"$pytest_cmd_string"
if [ "${#pytest_cmd[@]}" -eq 0 ]; then
  error "LORELEY_IT_PYTEST_CMD が空白だけです。pytest を起動するコマンドを指定してください。"
  exit "$EXIT_USAGE_OR_PREREQUISITE"
fi

run_integration_test
