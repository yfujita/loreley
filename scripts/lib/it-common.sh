# shellcheck shell=bash
# 結合テスト(IT)の実行スクリプト(scripts/run-{api,crawler,indexer}-integration-test.sh)の共通処理。
# 各スクリプトから `source` して使う。読み込んだだけでは何も実行しない(定数・関数の定義だけ。set もしない)。
#
# 呼び出し側が `run_integration_test` を呼ぶ前に用意するもの:
#   - `set -euo pipefail` と、リポジトリのルートへの cd(相対パスはルートが基準)
#   - usage 関数(--help で呼ばれる)
#   - export する固定値(ホスト側ポート・LORELEY_IT_*_URL・索引名など)と CRAWLER_DOCUMENTS_DIR
#   - 次の変数
#       IT_SCRIPT_NAME       info の接頭辞とロックの保持者名(例: run-api-integration-test)
#       IT_COMPOSE_TEST_FILE compose の上書きファイル(ルートからの相対パス)
#       IT_PORTS             配列 "表示名:ポート"(ポートの確認と --keep の案内に使う)
#       IT_SERVICES          配列。`compose up -d --build` に渡すサービス
#       IT_WAIT_CHECKS       配列 "サービス名:healthy" または "サービス名:exited_ok"
#       IT_DOCUMENTS_DIR     Crawler が読む文書の置き場所(絶対パス)。空なら扱わない
#       IT_RESULTS_DIR       pytest のログの置き場所(ルートからの相対パス)
#       IT_REQUIRE_UV        "true" のとき uv の存在を事前確認する
#       pytest_cmd           配列。pytest を起動するコマンド
#   - `parse_common_args "$@"`(引数と LORELEY_IT_WAIT_TIMEOUT_SECS の検証)

readonly PROJECT_NAME="loreley-it"
readonly POLL_INTERVAL_SECS=3
readonly LOG_TAIL_LINES=100
readonly MIN_MAX_MAP_COUNT=262144
readonly EXIT_USAGE_OR_PREREQUISITE=1
readonly EXIT_STARTUP_FAILED=10
readonly EXIT_CLEANUP_FAILED=11

# macOS の TMPDIR は "/" で終わるため、末尾の "/" を除いてから連結する。
_it_tmp_base="${TMPDIR:-/tmp}"
readonly IT_LOCK_DIR="${_it_tmp_base%/}/loreley-it.lock"
unset _it_tmp_base

wait_timeout_secs=300
keep_stack=false
pytest_args=()

# on_exit が何を後始末するかを決めるフラグ。ロックの取得と、スタック・data/ の後始末は別々に判定する。
#   lock_acquired:       自分がロックを取った(取れなかった側は、相手のロックに触れない)
#   stack_cleanup_armed: 事前確認を通過した(通過前の失敗で、残骸確認で見つけた他人のスタックや data/ を消さない)
lock_acquired=false
stack_cleanup_armed=false

error() {
  echo "Error: $*" >&2
}

info() {
  echo "[${IT_SCRIPT_NAME}] $*"
}

compose() {
  docker compose -p "$PROJECT_NAME" \
    -f deploy/compose/compose.yaml \
    -f "$IT_COMPOSE_TEST_FILE" "$@"
}

# 手動の後始末の案内に出す、スタックを消すコマンド。
manual_down_command() {
  echo "docker compose -p ${PROJECT_NAME} -f deploy/compose/compose.yaml -f ${IT_COMPOSE_TEST_FILE} down -v --remove-orphans"
}

# ---- 引数 ----

# -h/--help は呼び出し側の usage を表示して終了する。--keep 以外はすべて pytest に渡す。
parse_common_args() {
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

  wait_timeout_secs="${LORELEY_IT_WAIT_TIMEOUT_SECS:-300}"
  if [[ ! "$wait_timeout_secs" =~ ^[0-9]+$ ]] || [ "$wait_timeout_secs" -eq 0 ]; then
    error "LORELEY_IT_WAIT_TIMEOUT_SECS は 1 以上の整数(秒)で指定してください: ${wait_timeout_secs}"
    exit "$EXIT_USAGE_OR_PREREQUISITE"
  fi
}

# ---- 排他ロック ----

# 取れなかった理由と、保持者の情報・手動で解除する手順を表示する。何も消さない。
report_lock_unavailable() {
  if [ ! -e "$IT_LOCK_DIR" ] && [ ! -L "$IT_LOCK_DIR" ]; then
    error "ロックを作成できません: ${IT_LOCK_DIR}(TMPDIR の存在・権限・空き容量を確認してください)"
    return 0
  fi

  error "別の結合テストが実行中か、前回の実行が異常終了してロックが残っています: ${IT_LOCK_DIR}"

  local owner_file="${IT_LOCK_DIR}/owner"
  local owner_content=""
  if [ -r "$owner_file" ]; then
    owner_content="$(cat "$owner_file" 2>/dev/null)" || owner_content=""
  fi

  local owner_pid=""
  if [ -n "$owner_content" ]; then
    error "  保持者の情報:"
    while IFS= read -r line; do
      error "    ${line}"
    done <<<"$owner_content"
    owner_pid="$(printf '%s\n' "$owner_content" | sed -n 's/^pid=//p')"
  else
    error "  保持者の情報を読めません(作成直後の可能性があります)。"
  fi

  error "  実行中の結合テストがあるなら、その終了を待ってから再実行してください。"
  error "  ロックが残っているだけなら、保持者が動いていないことを確かめてから、手動で解除してください(このスクリプトは自動では解除しません):"
  if [[ "$owner_pid" =~ ^[0-9]+$ ]]; then
    error "    確認: ps -p ${owner_pid}"
  else
    error "    確認: ps などで、結合テストの実行スクリプトが動いていないこと"
  fi
  error "    解除: rm -rf '${IT_LOCK_DIR}'"
}

# mkdir の原子性で排他する(flock は macOS に無い)。成功したらすぐ lock_acquired を立て、
# 以降の終了では on_exit が必ず解除する。取れなかったときは何も消さずに終了コード 1 で中止する。
acquire_lock() {
  if ! mkdir "$IT_LOCK_DIR" 2>/dev/null; then
    report_lock_unavailable
    exit "$EXIT_USAGE_OR_PREREQUISITE"
  fi
  lock_acquired=true

  local owner_content
  owner_content="pid=$$
started_at=$(date '+%Y-%m-%dT%H:%M:%S%z')
script=${IT_SCRIPT_NAME}"
  if ! printf '%s\n' "$owner_content" >"${IT_LOCK_DIR}/owner"; then
    error "ロックの保持者の情報を書き込めませんでした: ${IT_LOCK_DIR}/owner"
    exit "$EXIT_USAGE_OR_PREREQUISITE"
  fi
}

# 自分が取ったロックだけを解除する。解除に失敗したら 1 を返す(残ると次の実行が止まるため)。
release_lock() {
  if [ "$lock_acquired" != true ]; then
    return 0
  fi

  local owner_file="${IT_LOCK_DIR}/owner"
  if [ -e "$owner_file" ]; then
    local owner_pid
    owner_pid="$(sed -n 's/^pid=//p' "$owner_file")" || {
      error "ロックの保持者を確認できませんでした。手動で解除してください: rm -rf '${IT_LOCK_DIR}'"
      return 1
    }
    # owner が空(書き込みに失敗した)のときは、自分が作った直後とみなして解除する。
    if [ -n "$owner_pid" ] && [ "$owner_pid" != "$$" ]; then
      echo "Warning: ロックの保持者(PID ${owner_pid})が自分(PID $$)と違うため、解除しませんでした: ${IT_LOCK_DIR}" >&2
      return 0
    fi
  fi

  # `:?` は、変数が空になる事故のときに rm を実行せず止めるための保険。
  if ! rm -rf "${IT_LOCK_DIR:?}"; then
    error "ロックを解除できませんでした。手動で解除してください: rm -rf '${IT_LOCK_DIR}'"
    return 1
  fi
}

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
  local entry
  local port
  local any_in_use=false
  for entry in "${IT_PORTS[@]}"; do
    port="${entry##*:}"
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
  # `||` の文脈では set -e が効かないので、docker の失敗(空の出力と区別できない)は明示的に止める。
  leftover_containers="$(docker ps -a --filter "label=com.docker.compose.project=${PROJECT_NAME}" --format '{{.Names}} ({{.Status}})')" || {
    error "docker ps に失敗しました。残骸の有無を確認できないため中止します。"
    return 1
  }
  if [ -n "$leftover_containers" ]; then
    error "前回の ${PROJECT_NAME} スタックのコンテナが残っています:"
    while IFS= read -r line; do
      error "  ${line}"
    done <<<"$leftover_containers"
    error "  不要なら: $(manual_down_command)"
    return 1
  fi
}

# 前回の ${PROJECT_NAME} のデータ(名前付きボリュームと、あれば検索対象のディレクトリ)が残っていないかを確認する。
# このスクリプトは終了時に `down -v`(ボリュームの削除)と、検索対象のディレクトリがあれば `rm -rf`(その削除)をする。
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
    error "  不要なら: $(manual_down_command)"
    return 1
  fi

  if [ -z "$IT_DOCUMENTS_DIR" ]; then
    return 0
  fi
  # ディレクトリがあって空でないとき(存在しない、または空なら問題ない)。
  # 存在しないことと、一覧を取れないこと(権限など)を区別し、後者は安全側に倒して中止する。
  if [ -e "$IT_DOCUMENTS_DIR" ] || [ -L "$IT_DOCUMENTS_DIR" ]; then
    local documents_listing
    documents_listing="$(ls -A "$IT_DOCUMENTS_DIR")" || {
      error "${IT_DOCUMENTS_DIR} の内容を確認できませんでした(権限など)。削除してよいか判断できないため中止します。"
      return 1
    }
    if [ -n "$documents_listing" ]; then
      error "${IT_DOCUMENTS_DIR} が空ではありません(このスクリプトは終了時にディレクトリごと削除します)。"
      error "  残したいファイルなら別の場所へ移し、不要なら削除してから再実行してください: rm -rf '${IT_DOCUMENTS_DIR}'"
      return 1
    fi
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
  if [ "$IT_REQUIRE_UV" = true ] && ! command -v uv >/dev/null 2>&1; then
    error "uv が見つかりません。https://docs.astral.sh/uv/ の手順でインストールしてください(例: brew install uv)。"
    return 1
  fi
  check_no_leftover_stack || return 1
  check_no_leftover_data || return 1
  check_ports_are_free || return 1
  warn_if_max_map_count_is_low
}

# ---- 後始末 ----

print_diagnostics() {
  echo "----- docker compose ps -a -----"
  compose ps -a || true
  echo "----- docker compose logs (各サービスの末尾 ${LOG_TAIL_LINES} 行) -----"
  compose logs --no-color --tail "$LOG_TAIL_LINES" || true
  echo "----- ここまで -----"
}

# スタック(と、あれば data/)の後始末。on_exit から、事前確認を通過したときだけ呼ばれる。
# 引数: 終了コード。失敗した後始末があれば 1 を返す。
cleanup_stack() {
  local exit_status="$1"
  local cleanup_failed=false

  if [ "$exit_status" -ne 0 ]; then
    print_diagnostics
  fi

  if [ "$keep_stack" = true ]; then
    local kept_description="スタックを"
    local manual_cleanup_command
    manual_cleanup_command="$(manual_down_command)"
    if [ -n "$IT_DOCUMENTS_DIR" ]; then
      kept_description="スタックと ${IT_DOCUMENTS_DIR} を"
      manual_cleanup_command="${manual_cleanup_command} && rm -rf '${IT_DOCUMENTS_DIR}'"
    fi
    local endpoints=""
    local entry
    for entry in "${IT_PORTS[@]}"; do
      endpoints="${endpoints:+${endpoints}  }${entry%%:*}: http://127.0.0.1:${entry##*:}"
    done
    info "--keep が指定されたため、${kept_description}残しました(プロジェクト名: ${PROJECT_NAME})。"
    info "  ${endpoints}"
    info "  後始末: ${manual_cleanup_command}"
    return 0
  fi

  info "後始末します(docker compose -p ${PROJECT_NAME} down -v --remove-orphans)。"
  local compose_down_succeeded=true
  if ! compose down -v --remove-orphans; then
    compose_down_succeeded=false
    cleanup_failed=true
    error "後始末に失敗しました。手動で上のコマンドを実行してください。"
  fi

  if [ -n "$IT_DOCUMENTS_DIR" ]; then
    # コンテナを消したあとに削除する(:ro の mount 元を、使われている間に消さない)。
    # down に失敗したときはコンテナが残っているかもしれないので、削除しない。
    # `:?` は、変数が空になる事故のときに rm を実行せず止めるための保険。
    if [ "$compose_down_succeeded" = true ]; then
      info "検索対象のディレクトリを削除します(${IT_DOCUMENTS_DIR})。"
      if ! rm -rf "${IT_DOCUMENTS_DIR:?}"; then
        cleanup_failed=true
        error "${IT_DOCUMENTS_DIR} を削除できませんでした。手動で削除してください。"
      fi
    else
      error "コンテナが残っている可能性があるため、${IT_DOCUMENTS_DIR} は削除しませんでした。コンテナを止めてから、手動で rm -rf '${IT_DOCUMENTS_DIR}' を実行してください。"
    fi
  fi

  [ "$cleanup_failed" = false ]
}

# EXIT で必ず呼ばれる(INT/TERM も trap が exit に変換するので、ここを通る)。
# 終了コードは最初に控える。テストや起動が失敗していたら、その終了コードをそのまま返す(後始末の結果で
# 隠さない)。成功していたのに後始末(ロックの解除を含む)に失敗したときは、EXIT_CLEANUP_FAILED を返す
# (CI でテスト用リソースの残りを成功と扱わないため)。
on_exit() {
  local exit_status=$?
  local cleanup_failed=false
  trap - EXIT INT TERM
  set +e

  if [ "$stack_cleanup_armed" = true ]; then
    cleanup_stack "$exit_status" || cleanup_failed=true
  fi
  # スタックの後始末のあとに解除する(後始末の途中で、次の実行にスタックを触らせない)。
  release_lock || cleanup_failed=true

  if [ "$exit_status" -eq 0 ] && [ "$cleanup_failed" = true ]; then
    error "テストは成功しましたが、後始末に失敗したため、終了コード ${EXIT_CLEANUP_FAILED} で終了します。"
    exit "$EXIT_CLEANUP_FAILED"
  fi
  exit "$exit_status"
}

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

# IT_WAIT_CHECKS のすべてが期待する状態になるまで待つ。
# 戻り値: 0=揃った / 1=失敗または上限超過(診断情報は on_exit で出る)
wait_for_stack() {
  local deadline_secs=$((SECONDS + wait_timeout_secs))

  info "スタックの起動を待っています(上限 ${wait_timeout_secs} 秒)..."
  while true; do
    local all_ready=true
    local check probe_status
    for check in "${IT_WAIT_CHECKS[@]}"; do
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

# ---- 実行 ----

# ロック取得 → 事前確認 → 起動 → 待機 → pytest → 後始末。pytest の終了コードで exit する。
run_integration_test() {
  # trap を最初に登録する。ロックの取得・`up` の途中で失敗・中断しても、on_exit がフラグに応じて後始末する。
  trap on_exit EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM

  acquire_lock

  # 失敗しても、スタックと data/ は(他人のものかもしれないので)触らない。ロックだけが on_exit で解除される。
  if ! check_prerequisites; then
    exit "$EXIT_USAGE_OR_PREREQUISITE"
  fi

  # ここから先は自分のスタックなので、失敗・中断したら on_exit が down -v などで後始末する。
  stack_cleanup_armed=true

  if [ -n "$IT_DOCUMENTS_DIR" ]; then
    # Docker に作らせると root 所有になり、テスト(ホストのユーザー)が文書を置けず、後始末でも消せなくなる。
    mkdir -p "$IT_DOCUMENTS_DIR"
    # umask が 077 のユーザーでも、uid 10001 の Crawler がディレクトリを列挙できるようにする。
    chmod 755 "$IT_DOCUMENTS_DIR"
  fi

  info "スタックを起動します(プロジェクト名: ${PROJECT_NAME})。"
  if ! compose up -d --build "${IT_SERVICES[@]}"; then
    error "docker compose up に失敗しました(イメージの取得・ビルド、または依存サービスの起動失敗)。"
    exit "$EXIT_STARTUP_FAILED"
  fi
  if ! wait_for_stack; then
    exit "$EXIT_STARTUP_FAILED"
  fi

  mkdir -p "$IT_RESULTS_DIR"
  local result_file
  result_file="${IT_RESULTS_DIR}/pytest-$(date +%Y%m%d-%H%M%S).log"

  info "テストを実行します: ${pytest_cmd[*]}${pytest_args[*]:+ ${pytest_args[*]}}"
  info "出力は ${result_file} にも保存します。"

  # パイプの右端(tee)の成功で pytest の失敗が隠れないよう、PIPESTATUS から pytest の終了コードを取る。
  # set -e のままだとパイプが失敗した時点でスクリプトが終わり PIPESTATUS を読めないので、ここだけ外す。
  set +e
  "${pytest_cmd[@]}" ${pytest_args[@]+"${pytest_args[@]}"} 2>&1 | tee "$result_file"
  local pytest_status="${PIPESTATUS[0]}"
  set -e

  if [ "$pytest_status" -eq 0 ]; then
    info "結合テストに成功しました。"
  else
    error "結合テストが失敗しました(pytest の終了コード ${pytest_status})。ログ: ${result_file}"
  fi
  exit "$pytest_status"
}
