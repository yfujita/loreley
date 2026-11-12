#!/usr/bin/env python3
"""Claude Code Hooks から呼ばれ、実行イベントを JSON Lines で監査ログに追記する。

出力先:
  - 作業中のタスクが特定できた場合: agent_tasks/{タスク名}/audit/events.jsonl
  - 特定できていない場合:             .claude/audit/events.jsonl

作業中のタスクは、セッションごとに .claude/audit/state/{session_id}.json へ記憶する。
特定のルール:
  - プロンプト本文にタスク名(ディレクトリ名、または日付を除いた名前)が1つだけ含まれる
    場合、または agent_tasks/{タスク名}/ 配下のファイルを Write / Edit した場合は、
    そのタスクに切り替える
  - Read / Bash で agent_tasks/{タスク名}/ に触れた場合は、タスク未特定のときだけ採用する
  - 特定前のイベントは .claude/audit/events.jsonl に残り、後から移し替えない

プロンプト本文は UserPromptSubmit イベントの "prompt" として保存する(audit/ は gitignore 対象)。
Bash コマンド・ツール応答は機密情報を含み得るため、ログには保存しない
(タスク特定のための照合にのみ使う)。
フックの失敗でセッションを妨げないよう、例外は握りつぶして .claude/audit/hook-errors.log に残す。
"""

import fcntl
import json
import os
import re
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

TASKS_DIR_NAME = "agent_tasks"
AUDIT_DIR_NAME = "audit"
LOG_FILE_NAME = "events.jsonl"
DATE_PREFIX = re.compile(r"^\d{8}_")
EXIT_CODE_LINE = re.compile(r"^Exit code (\d+)")
SAFE_SESSION_ID = re.compile(r"[^A-Za-z0-9_-]")


def list_task_names(root: Path) -> list[str]:
    tasks_dir = root / TASKS_DIR_NAME
    if not tasks_dir.is_dir():
        return []
    return sorted(p.name for p in tasks_dir.iterdir() if p.is_dir())


def find_task_in_text(text: str, task_names: list[str]) -> str | None:
    """テキストに含まれるタスクを返す。0件または複数件で曖昧な場合は None。"""
    full_matches = [name for name in task_names if name in text]
    if len(full_matches) == 1:
        return full_matches[0]
    if full_matches:
        return None

    short_matches = [
        name for name in task_names if DATE_PREFIX.sub("", name) in text
    ]
    return short_matches[0] if len(short_matches) == 1 else None


def find_task_in_path(file_path: str, root: Path, task_names: list[str]) -> str | None:
    try:
        relative = Path(file_path).resolve().relative_to((root / TASKS_DIR_NAME).resolve())
    except (ValueError, OSError):
        return None
    if relative.parts and relative.parts[0] in task_names:
        return relative.parts[0]
    return None


def state_path(root: Path, session_id: str) -> Path:
    safe_id = SAFE_SESSION_ID.sub("_", session_id)
    return root / ".claude" / AUDIT_DIR_NAME / "state" / f"{safe_id}.json"


def load_current_task(root: Path, session_id: str) -> str | None:
    try:
        return json.loads(state_path(root, session_id).read_text(encoding="utf-8")).get("task")
    except (OSError, ValueError):
        return None


def save_current_task(root: Path, session_id: str, task: str) -> None:
    path = state_path(root, session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"task": task}), encoding="utf-8")


def detect_task(event: dict, root: Path, task_names: list[str]) -> tuple[str | None, bool]:
    """イベントから読み取れるタスクと、既存のタスクを上書きしてよいかを返す。"""
    tool_input = event.get("tool_input") or {}
    file_path = tool_input.get("file_path")

    if event.get("hook_event_name") == "UserPromptSubmit":
        return find_task_in_text(event.get("prompt") or "", task_names), True

    if event.get("tool_name") in ("Write", "Edit") and file_path:
        return find_task_in_path(file_path, root, task_names), True

    if file_path:
        return find_task_in_path(file_path, root, task_names), False

    if event.get("tool_name") == "Bash":
        return find_task_in_text(tool_input.get("command") or "", task_names), False

    return None, False


def resolve_task(event: dict, root: Path) -> str | None:
    session_id = event.get("session_id")
    if not session_id:
        return None

    current = load_current_task(root, session_id)
    task_names = list_task_names(root)
    detected, can_override = detect_task(event, root, task_names)

    if detected and detected != current and (can_override or current is None):
        save_current_task(root, session_id, detected)
        return detected
    return current if current in task_names else None


def display_path(file_path: str, root: Path) -> str:
    try:
        return str(Path(file_path).resolve().relative_to(root.resolve()))
    except (ValueError, OSError):
        return file_path


def build_record(event: dict, root: Path, task: str | None) -> dict:
    name = event.get("hook_event_name")
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": name,
        "session_id": event.get("session_id"),
        "prompt_id": event.get("prompt_id"),
        "agent_id": event.get("agent_id"),
        "agent_type": event.get("agent_type"),
        "task": task,
        "tool_name": event.get("tool_name"),
        "tool_use_id": event.get("tool_use_id"),
    }

    file_path = (event.get("tool_input") or {}).get("file_path")
    if file_path:
        record["file_path"] = display_path(file_path, root)

    if name == "PostToolUse" and event.get("tool_name") in ("Write", "Edit"):
        response = event.get("tool_response")
        is_create = isinstance(response, dict) and response.get("type") == "create"
        record["action"] = "ARTIFACT_CREATED" if is_create else "ARTIFACT_UPDATED"

    if name == "PostToolUseFailure":
        record["is_interrupt"] = event.get("is_interrupt")
        match = EXIT_CODE_LINE.match(event.get("error") or "")
        if match:
            record["exit_code"] = int(match.group(1))

    if name == "UserPromptSubmit":
        record["prompt"] = event.get("prompt")

    if name == "SessionStart":
        record["source"] = event.get("source")
    if name == "SessionEnd":
        record["reason"] = event.get("reason")

    return {key: value for key, value in record.items() if value is not None}


def append_line(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def project_root(event: dict) -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or os.getcwd())


def main() -> None:
    event = json.load(sys.stdin)
    root = project_root(event)

    task = resolve_task(event, root)
    record = build_record(event, root, task)

    if task:
        audit_dir = root / TASKS_DIR_NAME / task / AUDIT_DIR_NAME
    else:
        audit_dir = root / ".claude" / AUDIT_DIR_NAME
    append_line(audit_dir / LOG_FILE_NAME, json.dumps(record, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        try:
            root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
            error_log = root / ".claude" / AUDIT_DIR_NAME / "hook-errors.log"
            append_line(error_log, f"{datetime.now(timezone.utc).isoformat()} {traceback.format_exc()}")
        except Exception:
            pass
    sys.exit(0)
