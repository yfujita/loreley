# Loreley Indexer のコンテナイメージ。
# ビルドコンテキストは `apps/indexer`: docker build -t loreley-indexer apps/indexer
#
# 再現性のため、ベースイメージ(タグ+ダイジェスト)と uv のバージョンを固定している。
# Python のバージョン(3.12)は `.python-version` と `pyproject.toml`(>=3.12,<3.13)に合わせる。
# 依存は `uv.lock`(ハッシュつき)から入れる。lxml・pydantic-core などのネイティブ依存は
# manylinux の wheel が `uv.lock` にあるので、Debian(glibc)系のイメージではコンパイラが要らない。
# musl 系(alpine)は wheel の種類が変わるため使わない。

# ベースイメージは 2026-11-12 に固定した(Python 3.12.16、OpenSSL 3.0.22。2026-11-05 ビルド)。
# 古いタグのままだと、Debian と OpenSSL の脆弱性修正が入らないため。
# 運用: 定期的に再ビルドし、そのとき `3.12-slim-bookworm` の最新の
#   タグとダイジェストに更新する。Renovate / Dependabot などで自動化してもよい(任意)。
#   更新したら、テストを通してから使う。
ARG PYTHON_IMAGE=python:3.12.16-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df

# --- ビルドステージ: 依存を仮想環境に入れる(最終イメージには uv を持ち込まない) ---
FROM ${PYTHON_IMAGE} AS builder

# uv はビルドの再現性のためバージョンを固定する。公式イメージ(ghcr.io/astral-sh/uv)ではなく
# pip で入れるのは、ベースイメージと同じ取得元(PyPI)だけで済み、動作を確認した版を
# そのまま指定できるため。
ARG UV_VERSION=0.13.7
RUN pip install --no-cache-dir --disable-pip-version-check --root-user-action=ignore \
    "uv==${UV_VERSION}"

# UV_COMPILE_BYTECODE: 起動を速くする。最終イメージは読み取り専用の root 所有で、実行ユーザーは
#   .pyc を書けないため、ビルド時に作っておく。
# UV_LINK_MODE=copy: 仮想環境を次のステージへコピーするので、キャッシュへのリンクにしない。
# UV_PYTHON_DOWNLOADS=never: ベースイメージの Python を使い、別の Python を取得しない。
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# 依存だけを先に入れる。ソースを変えても、この層はキャッシュが効く。
# `--locked`: `uv.lock` を更新せず、そのとおりに入れる。ロックが `pyproject.toml` に対して古いと
#   ビルドが失敗する(古いロックのまま気づかずに出荷しないため)。ビルドの前に
#   `uv lock --check` で先に確認しておくと、失敗が早く分かる(補助)。
# `--no-dev`: `httpx2`・pytest・ruff はテスト用なので本番イメージに含めない。
# `--no-install-project`: アプリ自身は、ビルドバックエンド(hatchling。`uv.lock` に固定されない)の
#   取得を避けるため、パッケージとして入れず `PYTHONPATH` で参照する(下のランタイムステージ)。
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

# 起動時にコンパイルされないよう、ソースのバイトコードもここで作る。
COPY src ./src
RUN python -m compileall -q src


# --- ランタイムステージ ---
FROM ${PYTHON_IMAGE} AS runtime

# 非 root で動かす。ユーザーを持たせるだけで、ホームも作らない(書き込む場所は不要。
# ログは標準エラー出力に出す)。
RUN groupadd --system --gid 10001 indexer \
    && useradd --system --uid 10001 --gid indexer --no-create-home --shell /usr/sbin/nologin indexer

WORKDIR /app
# 仮想環境の `python` は、ビルドステージと同じパスのシステム Python(/usr/local/bin)を指すので、
# 同じベースイメージを使うこと(`PYTHON_IMAGE` はステージ間で共通)。
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src

# PYTHONUNBUFFERED: ログを即座に出す。
# PYTHONDONTWRITEBYTECODE: 実行ユーザーが書けない場所へ .pyc を書こうとしない(作成済みを使う)。
# LORELEY_INDEXER_HTTP_HOST: 既定の 127.0.0.1 ではコンテナの外(Crawler)から届かない。
#   **この API には認証・認可がない**(`DELETE` でソースの文書の全削除まで呼べる)。Crawler と
#   同じ内部ネットワークにだけ置き、ホストや外部に公開しない(api 3.1)。
# 秘密値(`LORELEY_INDEXER_OPENSEARCH_PASSWORD` など)や接続先(`..._OPENSEARCH_URL`)は、
# イメージに焼き込まず、実行時に環境変数で渡す(現在の設定の読み込みは、Docker の secrets や
# `_FILE` 形式を読めない)。環境変数は `docker inspect` で見えるので、その権限を絞る。
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LORELEY_INDEXER_HTTP_HOST=0.0.0.0

USER indexer

# 既定のポート(`LORELEY_INDEXER_HTTP_PORT` の既定値)。変えたときは、公開するポートも合わせる。
EXPOSE 8000

# `/healthz` は、起動時の整理(再起動前に受理した削除結果の `failed` 化。OpenSearch への読み書き)が
# 終わるまで 503 を返し、uvicorn も接続を受け付けない。OpenSearch の応答が遅いと、1 回の
# リクエストが最大 `LORELEY_INDEXER_OS_REQUEST_TIMEOUT_SECONDS` ×(1 + `..._OS_TRANSPORT_MAX_RETRIES`)
# = 既定 30 × 3 = 90 秒かかる。起動時の整理は複数のリクエストなので、OpenSearch の遅延が続くと
# 120 秒を超えうる。`--start-period` は 120 秒にしているが、起動が遅い環境では伸ばす。
# この間の失敗は unhealthy に数えない(成功すれば即 healthy)。タイムアウト設定を伸ばしたときも、
# あわせて伸ばす。
# curl は slim イメージにないので、標準ライブラリの urllib で確認する。HTTP 200 以外(503 を含む)は
# 例外になり、終了コード 1(unhealthy)になる。ポートは設定に追従し、プロキシの環境変数は使わない。
# ホストは `127.0.0.1` 固定。`LORELEY_INDEXER_HTTP_HOST` を特定の IP や IPv6 に変えるときは、
# HEALTHCHECK のホストも合わせる。
HEALTHCHECK --interval=15s --timeout=5s --start-period=120s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request as u; u.build_opener(u.ProxyHandler({})).open('http://127.0.0.1:%s/healthz' % os.environ.get('LORELEY_INDEXER_HTTP_PORT', '8000'), timeout=3)"]

# 単一プロセスで動かす(ワーカー数は増やさない。`--workers`・`--reload` は使わない)。
# ソース単位のロック・削除ワーカー・起床通知はプロセス内にあり、複数プロセスは対象外。
# `uvicorn` は SIGTERM で受け付けを止め、停止処理(要約・削除ワーカー、接続のクローズ)を行う。
CMD ["python", "-m", "loreley_indexer.main"]
