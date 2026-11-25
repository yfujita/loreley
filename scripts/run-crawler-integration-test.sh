#!/usr/bin/env bash
# Crawler の結合テストを、compose の起動 → 待機 → pytest → 後始末まで一括で実行する。
#
# 使い方: scripts/run-crawler-integration-test.sh [--keep] [pytest の引数...]
#   例: scripts/run-crawler-integration-test.sh              # 全シナリオ
#       scripts/run-crawler-integration-test.sh --keep       # 終了後もスタックと data/ を残す(デバッグ用)
#       scripts/run-crawler-integration-test.sh -k test_30_ttl  # テストを絞る(-k。ファイル名の語でも絞れる)
#   ※ 絞り込みは `-k` を使う。ファイルやノード ID(`ファイル::テスト名`)をパス引数で渡しても、既定のコマンドの
#     末尾に `tests/integration/crawler` があるため絞られず、全テストが走る。1 テストだけを指定したいときは、
#     `--keep` でスタックを残し、pytest を直接実行する。
#   ※ シナリオ ID(CIT-nn)はテスト名に含まれないため、`-k CIT-30` では 0 件になる(終了コード 5)。
#
# 終了コード:
#   pytest の終了コード(0=全成功。1〜5 は pytest の定義どおり)
#   1  引数・事前確認の失敗(pytest の終了コードと重なるが、事前確認の失敗は標準エラー出力に出る)
#   10 スタックの起動失敗(待機の上限超過・コンテナの異常終了を含む)
#   130/143 Ctrl-C(INT)/TERM で中断
#
# 環境変数:
#   LORELEY_IT_WAIT_TIMEOUT_SECS  起動後の待機の上限(秒)。既定 300
#   OPENSEARCH_VERSION など         deploy/compose/.env.example の変数は、そのまま compose に渡る。
#
# 設計上の注意:
#   - `docker compose up --wait` は使わない。ホストの compose v2.3.3 では、使い捨てコンテナ
#     (opensearch-init)が正常終了したあとも戻らないことを確認したため(`up -d` + 自前のポーリング)。
#   - プロジェクト名は loreley-it で固定。開発用スタックや無関係なコンテナには触れない。
#     Indexer・api の結合テストとはプロジェクト名・ポートが同じなので、同時には動かせない。
#   - ホスト側ポートは 9200(OpenSearch)・8000(Indexer)・8001(Crawler)で固定。テストがこの 3 つに接続する。
#   - Crawler が読む文書は tests/integration/crawler/data に置く。Docker に root 所有で作らせないよう、
#     起動前にこのスクリプトが作り、終了時に削除する(--keep のときは残す)。
#   - 終了時の `down -v` と `rm -rf` が、利用者のデータを消さないよう、事前確認で loreley-it の
#     コンテナ・名前付きボリューム・空でない data/ のどれかが残っていたら、何も消さずに中止する。
set -euo pipefail

readonly PROJECT_NAME="loreley-it"
readonly OPENSEARCH_PORT=9200
readonly INDEXER_PORT=8000
readonly CRAWLER_PORT=8001
# compose は deploy/compose/.env やシェルの環境変数でホスト側ポートを変えられる。テストは 9200・8000・8001 に
# 接続するので、ここで固定する(シェルの環境変数は .env より優先される)。固定しないと、ポート確認は
# 9200・8000・8001 を見るのに、スタックは別のポートで起動し、テストが「起動していません」と誤って中止する。
export OPENSEARCH_HOST_PORT="$OPENSEARCH_PORT"
export INDEXER_HOST_PORT="$INDEXER_PORT"
export CRAWLER_HOST_PORT="$CRAWLER_PORT"
# 索引名も同じ理由で固定する。テストは loreley-jobs・loreley-sources を読むので、シェルや
# deploy/compose/.env で別の名前にされていると、スタックだけが別の索引を使って、テストが失敗する。
# 削除記録・検索エイリアスはこのテストでは読まないが、compose が opensearch-init と Indexer に渡すので、
# 既定値に揃える。
export LORELEY_JOBS_INDEX_NAME="loreley-jobs"
export LORELEY_SOURCES_INDEX_NAME="loreley-sources"
export LORELEY_DELETIONS_INDEX_NAME="loreley-deletions"
export LORELEY_SEARCH_INDEX_ALIAS="loreley-documents"
readonly POLL_INTERVAL_SECS=3
readonly LOG_TAIL_LINES=100
readonly MIN_MAX_MAP_COUNT=262144
readonly EXIT_USAGE_OR_PREREQUISITE=1
readonly EXIT_STARTUP_FAILED=10

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root_dir"

# Crawler に :ro で mount する検索対象のディレクトリ。compose には絶対パスで渡す
# (相対パスは compose ファイル(deploy/compose/)の位置が基準になり、意図した場所にならない)。
documents_dir="${root_dir}/tests/integration/crawler/data"
export CRAWLER_DOCUMENTS_DIR="$documents_dir"

wait_timeout_secs="${LORELEY_IT_WAIT_TIMEOUT_SECS:-300}"
pytest_cmd=(uv run --project tests/integration/crawler pytest tests/integration/crawler -v)
keep_stack=false
pytest_args=()

usage() {
  sed -n '2,/^set -euo pipefail$/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//'
}

error() {
  echo "Error: $*" >&2
}

info() {
  echo "[run-crawler-integration-test] $*"
}

compose() {
  docker compose -p "$PROJECT_NAME" \
    -f deploy/compose/compose.yaml \
    -f tests/integration/crawler/compose.test.yaml "$@"
}

# ---- 引数 ----

while [ $# -gt 0 ]; do
  case "$1" in
    -h | --help)
      usage
      exit 0
      ;;
    --keep)
      keep_stack=true
      ;;
    *)
      # --keep と -h/--help 以外は、すべて pytest にそのまま渡す。
      pytest_args+=("$1")
      ;;
  esac
  shift
done

if [[ ! "$wait_timeout_secs" =~ ^[0-9]+$ ]] || [ "$wait_timeout_secs" -eq 0 ]; then
  error "LORELEY_IT_WAIT_TIMEOUT_SECS は 1 以上の整数(秒)で指定してください: ${wait_timeout_secs}"
  exit "$EXIT_USAGE_OR_PREREQUISITE"
fi

# ---- 事前確認(失敗してもスタックは作られていないので、後始末は不要) ----

# bash 組み込みの /dev/tcp で接続を試す。lsof や nc の有無・オプション差に依存せず、
# macOS と Linux の両方で動く。127.0.0.1 は compose が publish する先と同じ。
is_port_in_use() {
  (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null
}

# ポートを使っている相手を表示する。調べるだけで、止めたり消したりはしない
# (相手は開発用の別スタックや無関係なアプリかもしれないため)。
describe_port_owner() {
  local port="$1"
  local docker_owners
  local owner_found=false
  docker_owners="$(docker ps --filter "publish=${port}" --format '{{.Names}} (プロジェクト: {{.Label "com.docker.compose.project"}}, イメージ: {{.Image}})' 2>/dev/null || true)"
  if [ -n "$docker_owners" ]; then
    owner_found=true
    error "  ポート ${port} を公開している Docker コンテナ:"
    while IFS= read -r line; do
      error "    ${line}"
    done <<<"$docker_owners"
  fi
  if command -v lsof >/dev/null 2>&1; then
    local listeners
    listeners="$(lsof -nP -iTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true)"
    if [ -n "$listeners" ]; then
      owner_found=true
      error "  ポート ${port} で待ち受けているプロセス(lsof):"
      while IFS= read -r line; do
        error "    ${line}"
      done <<<"$listeners"
    fi
  fi
  if [ "$owner_found" = false ]; then
    error "  使用中の相手を特定できませんでした(Docker コンテナには見つからず、lsof では確認できませんでした)。"
  fi
}

check_ports_are_free() {
  local port
  local any_in_use=false
  for port in "$OPENSEARCH_PORT" "$INDEXER_PORT" "$CRAWLER_PORT"; do
    if is_port_in_use "$port"; then
      any_in_use=true
      error "ホストのポート ${port} が使用中です。"
      describe_port_owner "$port"
    fi
  done
  if [ "$any_in_use" = true ]; then
    error "使用中のプロセス(または起動したままの ${PROJECT_NAME} スタック)を、利用者自身の判断で止めてから再実行してください。このスクリプトは止めません。"
    return 1
  fi
}

# 前回の実行が異常終了して残った ${PROJECT_NAME} のコンテナ(停止中のものを含む)を検出する。
# ポートが空いていても、残骸があると新しいスタックと名前やボリュームが衝突する。
check_no_leftover_stack() {
  local leftover_containers
  leftover_containers="$(docker ps -a --filter "label=com.docker.compose.project=${PROJECT_NAME}" --format '{{.Names}} ({{.Status}})')"
  if [ -n "$leftover_containers" ]; then
    error "前回の ${PROJECT_NAME} スタックのコンテナが残っています:"
    while IFS= read -r line; do
      error "  ${line}"
    done <<<"$leftover_containers"
    error "  不要なら: docker compose -p ${PROJECT_NAME} -f deploy/compose/compose.yaml -f tests/integration/crawler/compose.test.yaml down -v --remove-orphans"
    return 1
  fi
}

# 前回の ${PROJECT_NAME} のデータ(名前付きボリュームと検索対象のディレクトリ)が残っていないかを確認する。
# このスクリプトは終了時に `down -v`(ボリュームの削除)と `rm -rf`(検索対象のディレクトリの削除)をする。
# コンテナが無くても、`docker compose down`(-v なし)で止めただけのボリュームや、利用者が data/ に置いた
# ファイルが残っていることがあり、確認しないとそれらを消してしまう。検出したら、何も消さずに中止する。
check_no_leftover_data() {
  local leftover_volumes
  # `||` の文脈では set -e が効かないので、docker の失敗(空の出力と区別できない)は明示的に止める。
  leftover_volumes="$(docker volume ls --filter "label=com.docker.compose.project=${PROJECT_NAME}" --format '{{.Name}}')" || {
    error "docker volume ls に失敗しました。"
    return 1
  }
  if [ -n "$leftover_volumes" ]; then
    error "${PROJECT_NAME} のデータボリュームが残っています(このスクリプトは終了時に削除します):"
    while IFS= read -r line; do
      error "  ${line}"
    done <<<"$leftover_volumes"
    error "  残したいデータなら、別のプロジェクト名のスタックへ移すか、バックアップしてください。"
    error "  不要なら: docker compose -p ${PROJECT_NAME} -f deploy/compose/compose.yaml -f tests/integration/crawler/compose.test.yaml down -v --remove-orphans"
    return 1
  fi
  # ディレクトリがあって空でないとき(存在しない、または空なら問題ない)。
  if [ -n "$(ls -A "$documents_dir" 2>/dev/null)" ]; then
    error "${documents_dir} が空ではありません(このスクリプトは終了時にディレクトリごと削除します)。"
    error "  残したいファイルなら別の場所へ移し、不要なら削除してから再実行してください: rm -rf '${documents_dir}'"
    return 1
  fi
}

# OpenSearch は vm.max_map_count が低いと、環境によって起動に失敗する。Docker Desktop(macOS)では不要。
warn_if_max_map_count_is_low() {
  local max_map_count_file=/proc/sys/vm/max_map_count
  if [ "$(uname -s)" != "Linux" ] || [ ! -r "$max_map_count_file" ]; then
    return 0
  fi
  local current_value
  current_value="$(cat "$max_map_count_file")"
  if [ "$current_value" -lt "$MIN_MAX_MAP_COUNT" ]; then
    echo "Warning: vm.max_map_count が ${current_value} です(OpenSearch の推奨は ${MIN_MAX_MAP_COUNT} 以上)。" >&2
    echo "  起動に失敗する場合は: sudo sysctl -w vm.max_map_count=${MIN_MAX_MAP_COUNT}" >&2
  fi
}

check_prerequisites() {
  if ! command -v docker >/dev/null 2>&1; then
    error "docker が見つかりません。Docker Desktop などをインストールして PATH に通してください。"
    return 1
  fi
  if ! docker compose version >/dev/null 2>&1; then
    error "docker compose(v2 プラグイン)が使えません。Docker Desktop を更新するか、compose プラグインを入れてください。"
    return 1
  fi
  if ! docker info >/dev/null 2>&1; then
    error "Docker デーモンに接続できません。Docker Desktop などを起動してから再実行してください。"
    return 1
  fi
  if ! command -v uv >/dev/null 2>&1; then
    error "uv が見つかりません。https://docs.astral.sh/uv/ の手順でインストールしてください(例: brew install uv)。"
    return 1
  fi
  check_no_leftover_stack || return 1
  check_no_leftover_data || return 1
  check_ports_are_free || return 1
  warn_if_max_map_count_is_low
}

if ! check_prerequisites; then
  exit "$EXIT_USAGE_OR_PREREQUISITE"
fi

# ---- 後始末 ----

print_diagnostics() {
  echo "----- docker compose ps -a -----"
  compose ps -a || true
  echo "----- docker compose logs (各サービスの末尾 ${LOG_TAIL_LINES} 行) -----"
  compose logs --no-color --tail "$LOG_TAIL_LINES" || true
  echo "----- ここまで -----"
}

# EXIT で必ず呼ばれる(INT/TERM も下の trap が exit に変換するので、ここを通る)。
# 終了コードは、後始末のコマンドの結果に左右されないよう最初に控えて、最後にそのまま返す。
cleanup() {
  local exit_status=$?
  trap - EXIT INT TERM
  set +e

  if [ "$exit_status" -ne 0 ]; then
    print_diagnostics
  fi

  if [ "$keep_stack" = true ]; then
    info "--keep が指定されたため、スタックと ${documents_dir} を残しました(プロジェクト名: ${PROJECT_NAME})。"
    info "  OpenSearch: http://127.0.0.1:${OPENSEARCH_PORT}  Indexer: http://127.0.0.1:${INDEXER_PORT}  Crawler: http://127.0.0.1:${CRAWLER_PORT}"
    info "  後始末: docker compose -p ${PROJECT_NAME} -f deploy/compose/compose.yaml -f tests/integration/crawler/compose.test.yaml down -v --remove-orphans && rm -rf '${documents_dir}'"
  else
    info "後始末します(docker compose -p ${PROJECT_NAME} down -v --remove-orphans)。"
    local compose_down_succeeded=true
    if ! compose down -v --remove-orphans; then
      compose_down_succeeded=false
      error "後始末に失敗しました。手動で上のコマンドを実行してください。"
    fi
    # コンテナを消したあとに削除する(:ro の mount 元を、使われている間に消さない)。
    # down に失敗したときはコンテナが残っているかもしれないので、削除しない。
    # `:?` は、変数が空になる事故のときに rm を実行せず止めるための保険。
    if [ "$compose_down_succeeded" = true ]; then
      info "検索対象のディレクトリを削除します(${documents_dir})。"
      if ! rm -rf "${documents_dir:?}"; then
        error "${documents_dir} を削除できませんでした。手動で削除してください。"
      fi
    else
      error "コンテナが残っている可能性があるため、${documents_dir} は削除しませんでした。コンテナを止めてから、手動で rm -rf '${documents_dir}' を実行してください。"
    fi
  fi
  exit "$exit_status"
}

# `up` の途中で失敗・中断しても一部のコンテナが残るので、起動の前に登録する。
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# ---- 起動と待機 ----

# サービスの状態を調べる。
#   expected: "healthy"(running かつ healthcheck が healthy) または "exited_ok"(終了コード 0 で終了)
# 戻り値: 0=期待する状態 / 1=まだ待つ / 2=待っても回復しない(理由を failure_reason に入れる)
failure_reason=""
probe_service() {
  local service="$1"
  local expected="$2"

  local container_id
  container_id="$(compose ps -aq "$service")" || return 1
  if [ -z "$container_id" ]; then
    # 依存先の healthy を待っている間は、コンテナがまだ作られていない。
    return 1
  fi

  local inspect_output
  inspect_output="$(docker inspect -f \
    '{{.State.Status}} {{.State.ExitCode}} {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
    "$container_id")" || return 1
  local container_status exit_code health_status
  read -r container_status exit_code health_status <<<"$inspect_output"

  case "$expected" in
    exited_ok)
      if [ "$container_status" = "exited" ] && [ "$exit_code" -eq 0 ]; then
        return 0
      fi
      if [ "$container_status" = "exited" ] || [ "$container_status" = "dead" ]; then
        failure_reason="${service} が異常終了しました(終了コード ${exit_code})"
        return 2
      fi
      return 1
      ;;
    healthy)
      if [ "$container_status" = "running" ] && [ "$health_status" = "healthy" ]; then
        return 0
      fi
      # restart: unless-stopped なので、落ちたコンテナは restarting を経て戻ることがある。
      # 落ちた時点で原因は確定しているので、戻るのを待たずに失敗にする。
      if [ "$container_status" != "running" ] && [ "$container_status" != "created" ]; then
        failure_reason="${service} が ${container_status} です(終了コード ${exit_code})"
        return 2
      fi
      if [ "$health_status" = "unhealthy" ]; then
        failure_reason="${service} が unhealthy です"
        return 2
      fi
      return 1
      ;;
  esac
  error "probe_service の expected が不正です: ${expected}"
  return 2
}

# opensearch・indexer・crawler が healthy、opensearch-init が正常終了になるまで待つ。
# 戻り値: 0=揃った / 1=失敗または上限超過(診断情報は cleanup で出る)
wait_for_stack() {
  local deadline_secs=$((SECONDS + wait_timeout_secs))
  local checks=("opensearch:healthy" "opensearch-init:exited_ok" "indexer:healthy" "crawler:healthy")

  info "スタックの起動を待っています(上限 ${wait_timeout_secs} 秒)..."
  while true; do
    local all_ready=true
    local check probe_status
    for check in "${checks[@]}"; do
      probe_status=0
      probe_service "${check%%:*}" "${check##*:}" || probe_status=$?
      if [ "$probe_status" -eq 2 ]; then
        error "起動に失敗しました: ${failure_reason}"
        return 1
      fi
      if [ "$probe_status" -eq 1 ]; then
        all_ready=false
      fi
    done

    if [ "$all_ready" = true ]; then
      info "スタックの準備ができました。"
      return 0
    fi
    if [ "$SECONDS" -ge "$deadline_secs" ]; then
      error "起動の待機が上限(${wait_timeout_secs} 秒)を超えました。"
      return 1
    fi
    sleep "$POLL_INTERVAL_SECS"
  done
}

# Docker に作らせると root 所有になり、テスト(ホストのユーザー)が文書を置けず、後始末でも消せなくなる。
mkdir -p "$documents_dir"
# umask が 077 のユーザーでも、uid 10001 の Crawler がディレクトリを列挙できるようにする。
chmod 755 "$documents_dir"

info "スタックを起動します(プロジェクト名: ${PROJECT_NAME})。"
if ! compose up -d --build opensearch opensearch-init indexer crawler; then
  error "docker compose up に失敗しました(イメージの取得・ビルド、または依存サービスの起動失敗)。"
  exit "$EXIT_STARTUP_FAILED"
fi
if ! wait_for_stack; then
  exit "$EXIT_STARTUP_FAILED"
fi

# ---- テスト ----

results_dir="tests/integration/crawler/results"
mkdir -p "$results_dir"
result_file="${results_dir}/pytest-$(date +%Y%m%d-%H%M%S).log"

info "テストを実行します: ${pytest_cmd[*]}${pytest_args[*]:+ ${pytest_args[*]}}"
info "出力は ${result_file} にも保存します。"

# パイプの右端(tee)の成功で pytest の失敗が隠れないよう、PIPESTATUS から pytest の終了コードを取る。
# set -e のままだとパイプが失敗した時点でスクリプトが終わり PIPESTATUS を読めないので、ここだけ外す。
set +e
"${pytest_cmd[@]}" ${pytest_args[@]+"${pytest_args[@]}"} 2>&1 | tee "$result_file"
pytest_status="${PIPESTATUS[0]}"
set -e

if [ "$pytest_status" -eq 0 ]; then
  info "結合テストに成功しました。"
else
  error "結合テストが失敗しました(pytest の終了コード ${pytest_status})。ログ: ${result_file}"
fi
exit "$pytest_status"
