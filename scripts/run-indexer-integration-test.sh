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
#   1  引数・事前確認の失敗(pytest の終了コードと重なるが、事前確認の失敗は標準エラー出力に出る)
#   10 スタックの起動失敗(待機の上限超過・コンテナの異常終了を含む)
#   130/143 Ctrl-C(INT)/TERM で中断
#
# 環境変数:
#   LORELEY_IT_WAIT_TIMEOUT_SECS  起動後の待機の上限(秒)。既定 300
#   LORELEY_IT_PYTEST_CMD         pytest を起動するコマンドの置き換え(空白区切りで分割する)。
#                                 既定は `uv run --project tests/integration/indexer pytest tests/integration/indexer -v`。
#                                 uv が使えない環境で、用意済みの venv の pytest を使いたい場合だけ指定する。
#                                 指定すると uv の事前確認は行わない。スクリプトの引数はこのコマンドの後ろに付く。
#   OPENSEARCH_VERSION など         deploy/compose/.env.example の変数は、そのまま compose に渡る。
#
# 設計上の注意:
#   - `docker compose up --wait` は使わない。ホストの compose v2.3.3 では、使い捨てコンテナ
#     (opensearch-init)が正常終了したあとも戻らないことを確認したため(`up -d` + 自前のポーリング)。
#   - プロジェクト名は loreley-it で固定。開発用スタックや無関係なコンテナには触れない。
#   - ホスト側ポートは 9200(OpenSearch)と 8000(Indexer)で固定。テストがこの 2 つに接続する。
set -euo pipefail

readonly PROJECT_NAME="loreley-it"
readonly OPENSEARCH_PORT=9200
readonly INDEXER_PORT=8000
# compose は deploy/compose/.env やシェルの環境変数でホスト側ポートを変えられる。テストは 9200・8000 に
# 接続するので、ここで固定する(シェルの環境変数は .env より優先される)。固定しないと、ポート確認は
# 9200・8000 を見るのに、スタックは別のポートで起動し、テストが「起動していません」と誤って中止する。
export OPENSEARCH_HOST_PORT="$OPENSEARCH_PORT"
export INDEXER_HOST_PORT="$INDEXER_PORT"
readonly POLL_INTERVAL_SECS=3
readonly LOG_TAIL_LINES=100
readonly MIN_MAX_MAP_COUNT=262144
readonly EXIT_USAGE_OR_PREREQUISITE=1
readonly EXIT_STARTUP_FAILED=10

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root_dir"

wait_timeout_secs="${LORELEY_IT_WAIT_TIMEOUT_SECS:-300}"
default_pytest_cmd="uv run --project tests/integration/indexer pytest tests/integration/indexer -v"
pytest_cmd_string="${LORELEY_IT_PYTEST_CMD:-$default_pytest_cmd}"
keep_stack=false
pytest_args=()

usage() {
  sed -n '2,/^set -euo pipefail$/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//'
}

error() {
  echo "Error: $*" >&2
}

info() {
  echo "[run-indexer-integration-test] $*"
}

compose() {
  docker compose -p "$PROJECT_NAME" \
    -f deploy/compose/compose.yaml \
    -f tests/integration/indexer/compose.test.yaml "$@"
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

read -r -a pytest_cmd <<<"$pytest_cmd_string"
if [ "${#pytest_cmd[@]}" -eq 0 ]; then
  error "LORELEY_IT_PYTEST_CMD が空白だけです。pytest を起動するコマンドを指定してください。"
  exit "$EXIT_USAGE_OR_PREREQUISITE"
fi

# ---- 事前確認(失敗してもスタックは作られていないので、後始末は不要) ----

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
  if [ -z "${LORELEY_IT_PYTEST_CMD:-}" ] && ! command -v uv >/dev/null 2>&1; then
    error "uv が見つかりません。https://docs.astral.sh/uv/ の手順でインストールしてください(例: brew install uv)。"
    return 1
  fi
  for port in "$OPENSEARCH_PORT" "$INDEXER_PORT"; do
    if is_port_in_use "$port"; then
      error "ホストのポート ${port} が使用中です。使用中のプロセス(または起動したままの ${PROJECT_NAME} スタック)を止めてから再実行してください。"
      error "  確認: lsof -nP -iTCP:${port} -sTCP:LISTEN"
      error "  ${PROJECT_NAME} の残りなら: docker compose -p ${PROJECT_NAME} -f deploy/compose/compose.yaml -f tests/integration/indexer/compose.test.yaml down -v --remove-orphans"
      return 1
    fi
  done
  warn_if_max_map_count_is_low
}

# bash 組み込みの /dev/tcp で接続を試す。lsof や nc の有無・オプション差に依存せず、
# macOS と Linux の両方で動く。127.0.0.1 は compose が publish する先と同じ。
is_port_in_use() {
  (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null
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
    info "--keep が指定されたため、スタックを残しました(プロジェクト名: ${PROJECT_NAME})。"
    info "  OpenSearch: http://127.0.0.1:${OPENSEARCH_PORT}  Indexer: http://127.0.0.1:${INDEXER_PORT}"
    info "  後始末: docker compose -p ${PROJECT_NAME} -f deploy/compose/compose.yaml -f tests/integration/indexer/compose.test.yaml down -v --remove-orphans"
  else
    info "後始末します(docker compose -p ${PROJECT_NAME} down -v --remove-orphans)。"
    if ! compose down -v --remove-orphans; then
      error "後始末に失敗しました。手動で上のコマンドを実行してください。"
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

# opensearch と indexer が healthy、opensearch-init が正常終了になるまで待つ。
# 戻り値: 0=揃った / 1=失敗または上限超過(診断情報は cleanup で出る)
wait_for_stack() {
  local deadline_secs=$((SECONDS + wait_timeout_secs))
  local checks=("opensearch:healthy" "opensearch-init:exited_ok" "indexer:healthy")

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

info "スタックを起動します(プロジェクト名: ${PROJECT_NAME})。"
if ! compose up -d --build; then
  error "docker compose up に失敗しました(イメージの取得・ビルド、または依存サービスの起動失敗)。"
  exit "$EXIT_STARTUP_FAILED"
fi
if ! wait_for_stack; then
  exit "$EXIT_STARTUP_FAILED"
fi

# ---- テスト ----

results_dir="tests/integration/indexer/results"
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
