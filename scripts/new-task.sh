#!/usr/bin/env bash
# agent_tasks 配下にタスクディレクトリと要件定義・STATUS.md の雛形を作成する。
# 使い方: scripts/new-task.sh  (タスク名は対話的に入力する)
# ディレクトリ名は {YYYYMMDD}_{タスク名} になる。
set -euo pipefail

read -r -p "タスク名 (例: create_login_api): " input_name
if [ -z "$input_name" ]; then
  echo "Error: task name is empty" >&2
  exit 1
fi
if [[ ! "$input_name" =~ ^[A-Za-z0-9_-]+$ ]]; then
  echo "Error: task name may contain only letters, numbers, underscores, and hyphens" >&2
  exit 1
fi

root_dir="$(cd "$(dirname "$0")/.." && pwd)"
task_name="$(date +%Y%m%d)_${input_name}"
task_dir="${root_dir}/agent_tasks/${task_name}"

if [ -e "$task_dir" ]; then
  echo "Error: already exists: ${task_dir}" >&2
  exit 1
fi

mkdir -p "$task_dir"
cat > "${task_dir}/0000-requirements-definition.md" <<TEMPLATE
# ${task_name}

## 背景・目的

(なぜこのタスクが必要か、何を達成したいか)

## 要件

### 現状(As-Is)

(いまどうなっているか)

### あるべき姿(To-Be)

(どうなっていてほしいか)

### 具体的にやること

- (やることを箇条書きで)

## 対象範囲

- (対象とするファイル・機能・領域)

## スコープ外

- (このタスクでは扱わないこと)

## 制約・前提条件

- (守るべき制約、前提とすること)

## 完了条件

- [ ] (完了と判断できる条件)

## 成果物

- (作成・変更するもの)

## 補足・参考情報

- (関連資料、リンク、メモなど)
TEMPLATE

cat > "${task_dir}/STATUS.md" <<TEMPLATE
# タスク状態

## 基本情報

- 状態: not_started
- 現在工程: 要件確認
- 最終更新: $(date +%Y-%m-%d)
- 最新作業記録: なし

## 現在の状況

タスクを作成した。要件定義(0000-requirements-definition.md)の記載待ち。

## 次のアクション

1. 要件定義を記載する(ユーザ)
2. 要件確認・プラン作成に進む

## 未解決事項

- なし

## ユーザー判断待ち

- なし
TEMPLATE

echo "Created: ${task_dir}"
