#!/bin/sh
# OpenSearch に Loreley のインデックスを作成する(冪等)。
# Indexer はインデックスを作成しないため、起動前に一度だけ実行する(compose では opensearch-init)。
# 公式の OpenSearch イメージ(curl あり・jq なし)で動くよう、POSIX sh と curl だけで書く。
#
# 環境変数(括弧内は既定値):
#   OPENSEARCH_URL          OpenSearch の URL (http://opensearch:9200)
#   SCHEMA_DIR              search-index.json などを置いたディレクトリ (/schema)
#   SEARCH_INDEX_NAME       検索インデックスの実体名 (loreley-documents-000001)
#   SEARCH_INDEX_ALIAS      検索インデックスのエイリアス (loreley-documents)
#   DELETIONS_INDEX_NAME    削除記録のインデックス名 (loreley-deletions)
#   JOBS_INDEX_NAME         ジョブ・ロックのインデックス名 (loreley-jobs)
set -eu

OPENSEARCH_URL="${OPENSEARCH_URL:-http://opensearch:9200}"
SCHEMA_DIR="${SCHEMA_DIR:-/schema}"
SEARCH_INDEX_NAME="${SEARCH_INDEX_NAME:-loreley-documents-000001}"
SEARCH_INDEX_ALIAS="${SEARCH_INDEX_ALIAS:-loreley-documents}"
DELETIONS_INDEX_NAME="${DELETIONS_INDEX_NAME:-loreley-deletions}"
JOBS_INDEX_NAME="${JOBS_INDEX_NAME:-loreley-jobs}"

REQUEST_TIMEOUT_SECS=30

response_body_file="$(mktemp)"
trap 'rm -f "$response_body_file"' EXIT

die() {
  echo "Error: $*" >&2
  exit 1
}

# HTTP リクエストを送り、ステータスコードを標準出力に出す。応答本文は $response_body_file に残す。
# 引数: メソッド パス [リクエストボディのファイル]。HEAD は send_head_request を使う。
send_request() {
  method="$1"
  path="$2"
  body_file="${3:-}"

  if [ -n "$body_file" ]; then
    curl -sS --max-time "$REQUEST_TIMEOUT_SECS" -X "$method" \
      -H 'Content-Type: application/json' --data-binary "@${body_file}" \
      -o "$response_body_file" -w '%{http_code}' "${OPENSEARCH_URL}${path}"
  else
    curl -sS --max-time "$REQUEST_TIMEOUT_SECS" -X "$method" \
      -o "$response_body_file" -w '%{http_code}' "${OPENSEARCH_URL}${path}"
  fi
}

# HEAD に `curl -X HEAD` を使うと、本文を待ち続けてタイムアウトするため、`--head` を使う。
send_head_request() {
  path="$1"
  curl -sS --max-time "$REQUEST_TIMEOUT_SECS" --head \
    -o "$response_body_file" -w '%{http_code}' "${OPENSEARCH_URL}${path}"
}

fail_with_response() {
  action="$1"
  status="$2"
  echo "Error: ${action} failed: HTTP ${status}" >&2
  cat "$response_body_file" >&2
  echo >&2
  exit 1
}

# 200 なら存在する、404 なら存在しない。それ以外は失敗にする(判定を誤って作成に進まないため)。
exists() {
  path="$1"
  status="$(send_head_request "$path")" || die "request to OpenSearch failed: ${OPENSEARCH_URL}"
  case "$status" in
    200) return 0 ;;
    404) return 1 ;;
    *) fail_with_response "HEAD ${path}" "$status" ;;
  esac
}

# 存在しなければ作成する。作成済みなら何もしない。
create_index_if_absent() {
  index_name="$1"
  schema_file="${SCHEMA_DIR}/$2"

  [ -f "$schema_file" ] || die "schema file not found: ${schema_file}"

  if exists "/${index_name}"; then
    echo "skip: index already exists: ${index_name}"
    return
  fi

  status="$(send_request PUT "/${index_name}" "$schema_file")" \
    || die "request to OpenSearch failed: ${OPENSEARCH_URL}"
  if [ "$status" = "200" ] && grep -q '"acknowledged":true' "$response_body_file"; then
    echo "created: index ${index_name}"
    return
  fi
  # 確認から作成までの間に別の実行が作成した場合は、作成済みと同じ扱いにする。
  if [ "$status" = "400" ] && grep -q 'resource_already_exists_exception' "$response_body_file"; then
    echo "skip: index already exists: ${index_name}"
    return
  fi
  fail_with_response "create index ${index_name}" "$status"
}

# エイリアスが存在しなければ付与する(呼び出し側でも確認しているが、単独でも安全にしておく)。
# 再インデックス後はエイリアスが別のインデックスを指すため、名前の存在だけで判定する。
# 存在するのに追加すると、エイリアスが複数のインデックスを指して書き込みに使えなくなる。
add_alias_if_absent() {
  index_name="$1"
  alias_name="$2"

  if exists "/_alias/${alias_name}"; then
    echo "skip: alias already exists: ${alias_name}"
    return
  fi

  status="$(send_request PUT "/${index_name}/_alias/${alias_name}")" \
    || die "request to OpenSearch failed: ${OPENSEARCH_URL}"
  if [ "$status" = "200" ] && grep -q '"acknowledged":true' "$response_body_file"; then
    echo "created: alias ${alias_name} -> ${index_name}"
    return
  fi
  fail_with_response "add alias ${alias_name} to ${index_name}" "$status"
}

# 検索インデックスは、エイリアスの有無で判定する。
# 再インデックスで別のインデックス(-000002 など)へ切り替えて -000001 を削除したあとに、
# 空の -000001 を毎回作り直さないため。エイリアスが無いときだけ「作成 → 付与」を行う。
# 作成のあと付与の前に失敗しても、再実行ではインデックスが存在済みで skip され、付与だけが補われる。
if exists "/_alias/${SEARCH_INDEX_ALIAS}"; then
  echo "skip: alias already exists: ${SEARCH_INDEX_ALIAS}"
else
  create_index_if_absent "$SEARCH_INDEX_NAME" search-index.json
  add_alias_if_absent "$SEARCH_INDEX_NAME" "$SEARCH_INDEX_ALIAS"
fi
create_index_if_absent "$DELETIONS_INDEX_NAME" deletions.json
create_index_if_absent "$JOBS_INDEX_NAME" jobs.json

echo "done: OpenSearch indices are ready"
