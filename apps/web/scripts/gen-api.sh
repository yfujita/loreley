#!/bin/sh
# Admin API の OpenAPI を書き出し、型・SDK・Query を生成する(2 段)。
#   1. apps/api の Python 環境(uv)で openapi/admin-v1.json を書き出す
#   2. openapi-ts で src/admin/api/generated/ を生成する
# LORELEY_GEN_OUT を指定すると、apps/web の代わりにそのディレクトリへ書き出す(gen:api:check 用)。
set -eu

cd "$(dirname "$0")/.."
out_dir="$(cd "${LORELEY_GEN_OUT:-.}" && pwd)"

mkdir -p "$out_dir/openapi"
# --locked: uv.lock を書き換えない(gen:api:check が作業ツリーを変更しないため)。
uv run --locked --project ../api python -m loreley_api.admin.openapi_export "$out_dir/openapi/admin-v1.json"
LORELEY_GEN_OUT="$out_dir" openapi-ts
