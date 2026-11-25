#!/usr/bin/env bash
# Admin API(api)の結合テストを、compose の起動 → 待機 → pytest → 後始末まで一括で実行する。
#
# 使い方: scripts/run-api-integration-test.sh [--keep] [pytest の引数...]
#   例: scripts/run-api-integration-test.sh              # 全シナリオ
#       scripts/run-api-integration-test.sh --keep       # 終了後もスタックと data/ を残す(デバッグ用)
#       scripts/run-api-integration-test.sh -k test_01   # テストを絞る(-k。ファイル名の語でも絞れる)
#   ※ 絞り込みは `-k` を使う。ファイルやノード ID(`ファイル::テスト名`)をパス引数で渡しても、既定のコマンドの
#     末尾に `tests/integration/api` があるため絞られず、全テストが走る。1 テストだけを指定したいときは、
#     `--keep` でスタックを残し、pytest を直接実行する。
#   ※ シナリオ ID(AIT-nn)はテスト名に含まれないため、`-k AIT-30` では 0 件になる(終了コード 5)。
#
# 終了コード:
#   pytest の終了コード(0=全成功。1〜5 は pytest の定義どおり)
#   1  引数・事前確認の失敗、またはロックを取れなかった(pytest の終了コードと重なるが、これらの失敗は標準エラー出力に出る)
#   10 スタックの起動失敗(待機の上限超過・コンテナの異常終了を含む)
#   11 pytest は成功したが、後始末(`down -v`・data/ の削除・ロックの解除)に失敗した(テスト失敗のときは pytest の終了コードを優先)
#   130/143 Ctrl-C(INT)/TERM で中断
#
# 環境変数:
#   LORELEY_IT_WAIT_TIMEOUT_SECS  起動後の待機の上限(秒)。既定 300
#   OPENSEARCH_VERSION など         deploy/compose/.env.example の変数は、そのまま compose に渡る。
#                                   ただし、下の「固定する値」(ポート・索引名・cron のタイムゾーン)は上書きされる。
#
# 固定する値(テストが前提にする):
#   ホスト側ポート 9200・8000・8001・8080、テストの接続先 URL(LORELEY_IT_{OPENSEARCH,INDEXER,CRAWLER,API}_URL を
#   上のポートの 127.0.0.1 に)、索引名 4 つ(既定値)、LORELEY_CRON_TIMEZONE=Asia/Tokyo
#   (Crawler と api に同じ変数から届くことを AIT-01 が確かめる)、LORELEY_IT_ALLOW_COMPOSE_CONTROL=1
#   (障害系のテストが `docker compose -p loreley-it stop/start` を実行してよいことの許可。AIT-90〜92)。
#
# 設計上の注意:
#   - `docker compose up --wait` は使わない。ホストの compose v2.3.3 では、使い捨てコンテナ
#     (opensearch-init)が正常終了したあとも戻らないことを確認したため(`up -d` + 自前のポーリング)。
#   - プロジェクト名は loreley-it で固定。開発用スタックや無関係なコンテナには触れない。
#     Crawler・Indexer の結合テストとはプロジェクト名・ポートが同じなので、同時には動かせない。
#     排他ロック(${TMPDIR:-/tmp}/loreley-it.lock)で同時実行を拒否する。
#   - 排他ロックは事前確認の直前に取り、終了時(--keep・INT・TERM を含む)に解除する。取れなかったとき
#     (別の結合テストが実行中、または SIGKILL などで残った)は、何も消さず、保持者の PID・開始時刻・
#     スクリプト名を表示して終了コード 1 で中止する。残ったロックは自動では解除しない。保持者が
#     動いていないことを確かめてから、表示される手順(rm -rf)で手動で解除する。
#   - ホスト側ポートは 9200(OpenSearch)・8000(Indexer)・8001(Crawler)・8080(api)で固定。
#     テストがこの 4 つに接続する。
#   - Crawler が読む文書は tests/integration/api/data に置く(api は mount しない)。Docker に root 所有で作らせないよう、
#     起動前にこのスクリプトが作り、終了時に削除する(--keep のときは残す)。
#   - 終了時の `down -v` と `rm -rf` が、利用者のデータを消さないよう、事前確認で loreley-it の
#     コンテナ・名前付きボリューム・空でない data/ のどれかが残っていたら、何も消さずに中止する。
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
readonly CRAWLER_PORT=8001
readonly API_PORT=8080
# compose は deploy/compose/.env やシェルの環境変数でホスト側ポートを変えられる。テストは 9200・8000・
# 8001・8080 に接続するので、ここで固定する(シェルの環境変数は .env より優先される)。固定しないと、
# ポート確認は 4 つを見るのに、スタックは別のポートで起動し、テストが「起動していません」と誤って中止する。
export OPENSEARCH_HOST_PORT="$OPENSEARCH_PORT"
export INDEXER_HOST_PORT="$INDEXER_PORT"
export CRAWLER_HOST_PORT="$CRAWLER_PORT"
export API_HOST_PORT="$API_PORT"
# テストの接続先も、compose が publish するポートに固定する。固定しないと、シェルに残った
# LORELEY_IT_*_URL が、ソース登録・削除やクロール起動、OpenSearch への直接書き込みを、このスクリプトが
# 起動したのとは別の環境に向けてしまう(pytest を直接実行するときだけ、環境変数で変えられる)。
export LORELEY_IT_OPENSEARCH_URL="http://127.0.0.1:${OPENSEARCH_PORT}"
export LORELEY_IT_INDEXER_URL="http://127.0.0.1:${INDEXER_PORT}"
export LORELEY_IT_CRAWLER_URL="http://127.0.0.1:${CRAWLER_PORT}"
export LORELEY_IT_API_URL="http://127.0.0.1:${API_PORT}"
# 索引名も同じ理由で固定する。テストは 4 つの索引(ジョブ・データソース設定・削除記録・検索エイリアス)を
# 読むので、シェルや deploy/compose/.env で別の名前にされていると、スタックだけが別の索引を使って、
# テストが失敗する。
export LORELEY_JOBS_INDEX_NAME="loreley-jobs"
export LORELEY_SOURCES_INDEX_NAME="loreley-sources"
export LORELEY_DELETIONS_INDEX_NAME="loreley-deletions"
export LORELEY_SEARCH_INDEX_ALIAS="loreley-documents"
# cron のタイムゾーン。既定(UTC)と違う値にして、共通変数が api に実際に届くことを AIT-01 で確かめる。
export LORELEY_CRON_TIMEZONE="Asia/Tokyo"
# 障害系のテスト(test_90_*)がコンテナを止めてよいことの許可。pytest を直接実行したときは付かないので、
# 障害系は skip される(テストが意図せずコンテナを止めないため)。
export LORELEY_IT_ALLOW_COMPOSE_CONTROL=1

root_dir="$(cd "${script_dir}/.." && pwd)"
cd "$root_dir"

# Crawler に :ro で mount する検索対象のディレクトリ。compose には絶対パスで渡す
# (相対パスは compose ファイル(deploy/compose/)の位置が基準になり、意図した場所にならない)。
IT_DOCUMENTS_DIR="${root_dir}/tests/integration/api/data"
export CRAWLER_DOCUMENTS_DIR="$IT_DOCUMENTS_DIR"

usage() {
  sed -n '2,/^set -euo pipefail$/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//'
}

IT_SCRIPT_NAME="run-api-integration-test"
IT_COMPOSE_TEST_FILE="tests/integration/api/compose.test.yaml"
IT_PORTS=("OpenSearch:${OPENSEARCH_PORT}" "Indexer:${INDEXER_PORT}" "Crawler:${CRAWLER_PORT}" "api:${API_PORT}")
IT_SERVICES=(opensearch opensearch-init indexer crawler api)
IT_WAIT_CHECKS=("opensearch:healthy" "opensearch-init:exited_ok" "indexer:healthy" "crawler:healthy" "api:healthy")
IT_RESULTS_DIR="tests/integration/api/results"
IT_REQUIRE_UV=true
pytest_cmd=(uv run --project tests/integration/api pytest tests/integration/api -v -rP)

parse_common_args "$@"
run_integration_test
