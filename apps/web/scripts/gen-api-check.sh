#!/bin/sh
# OpenAPI と生成コードが、Admin API の現在の実装から再生成した結果と一致することを確かめる。
# Git に依存しない。一時ディレクトリへ生成して作業ツリーと比べるので、作業ツリーは変更しない。
# 内容の差・追加されたファイル・欠けたファイルのいずれも、非 0 で終了する。
set -eu

cd "$(dirname "$0")/.."
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT INT TERM

LORELEY_GEN_OUT="$tmp_dir" sh scripts/gen-api.sh

status=0
diff -r "$tmp_dir/openapi" openapi || status=1
diff -r "$tmp_dir/src/admin/api/generated" src/admin/api/generated || status=1

if [ "$status" -ne 0 ]; then
  echo "gen:api:check: 再生成の結果が作業ツリーと一致しません。npm run gen:api を実行して差分を確認してください。" >&2
fi
exit "$status"
