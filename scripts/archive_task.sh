#!/usr/bin/env bash
# STATUS.md の状態が done のタスクを agent_tasks/_archive/ に移動する。
# 使い方: scripts/archive_task.sh [-n]
#   -n  実際には移動せず、移動対象を表示するだけにする(dry-run)
set -euo pipefail

dry_run=false
while getopts "n" opt; do
  case "$opt" in
    n) dry_run=true ;;
    *) echo "Usage: $0 [-n]" >&2; exit 2 ;;
  esac
done

root_dir="$(cd "$(dirname "$0")/.." && pwd)"
tasks_dir="${root_dir}/agent_tasks"
archive_dir="${tasks_dir}/_archive"

# STATUS.md の「- 状態: {値}」から値(最初の語)を取り出す
read_status() {
  sed -n 's/^- 状態:[[:space:]]*\([A-Za-z_]*\).*/\1/p' "$1" | head -n 1
}

moved=0
skipped=0
for task_dir in "${tasks_dir}"/*/; do
  task_name="$(basename "$task_dir")"
  # _archive など、先頭が _ のディレクトリはタスクではない
  [[ "$task_name" == _* ]] && continue

  status_file="${task_dir}STATUS.md"
  if [ ! -f "$status_file" ]; then
    echo "Skip: ${task_name} (STATUS.md がない)" >&2
    skipped=$((skipped + 1))
    continue
  fi

  [ "$(read_status "$status_file")" = "done" ] || continue

  if [ -e "${archive_dir}/${task_name}" ]; then
    echo "Skip: ${task_name} (移動先に同名のタスクが既にある)" >&2
    skipped=$((skipped + 1))
    continue
  fi

  if $dry_run; then
    echo "Would move: ${task_name}"
  else
    mkdir -p "$archive_dir"
    mv "${task_dir%/}" "${archive_dir}/${task_name}"
    echo "Moved: ${task_name}"
  fi
  moved=$((moved + 1))
done

if $dry_run; then
  echo "対象: ${moved} 件(dry-run。移動していない)"
else
  echo "移動: ${moved} 件"
fi
[ "$skipped" -eq 0 ] || echo "スキップ: ${skipped} 件" >&2
