# Loreley Crawler のコンテナイメージ。
# ビルドコンテキストは `apps/crawler`: docker build -t loreley-crawler apps/crawler
#
# 再現性のため、ベースイメージ(タグ+ダイジェスト)と uv のバージョンを固定している。
# Python のバージョン(3.12)は `.python-version` と `pyproject.toml`(>=3.12,<3.13)に合わせる。
# 依存は `uv.lock`(ハッシュつき)から入れる。pydantic-core などのネイティブ依存は
# manylinux の wheel が `uv.lock` にあるので、Debian(glibc)系のイメージではコンパイラが要らない。
# musl 系(alpine)は wheel の種類が変わるため使わない。

# ベースイメージは 2026-11-12 に固定した(Python 3.12.16、OpenSSL 3.0.22。2026-11-05 ビルド)。
# 古いタグのままだと、Debian と OpenSSL の脆弱性修正が入らないため。
# 運用: 定期的に再ビルドし、そのとき `3.12-slim-bookworm` の最新の
#   タグとダイジェストに更新する。Renovate / Dependabot などで自動化してもよい(任意)。
#   更新したら、テストを通してから使う。Indexer(`apps/indexer/Dockerfile`)と同じ値にそろえる。
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
RUN groupadd --system --gid 10001 crawler \
    && useradd --system --uid 10001 --gid crawler --no-create-home --shell /usr/sbin/nologin crawler

WORKDIR /app
# 仮想環境の `python` は、ビルドステージと同じパスのシステム Python(/usr/local/bin)を指すので、
# 同じベースイメージを使うこと(`PYTHON_IMAGE` はステージ間で共通)。
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src

# PYTHONUNBUFFERED: ログを即座に出す。
# PYTHONDONTWRITEBYTECODE: 実行ユーザーが書けない場所へ .pyc を書こうとしない(作成済みを使う)。
# LORELEY_CRAWLER_HTTP_HOST: 既定の 127.0.0.1 ではコンテナの外(Admin API の呼び出し元)から届かない。
#   **この Admin API には認証・認可がない**(クロール・ソース削除ジョブの起動、ロック解放、設定の
#   登録・更新まで呼べる)。内部ネットワークにだけ置き、ホストや外部に公開しない(crawler-api 3.1)。
# 必須の設定(`LORELEY_CRAWLER_OWNER`・`..._OPENSEARCH_URL`・`..._INDEXER_URL`)や秘密値
# (`..._OPENSEARCH_PASSWORD`)は、イメージに焼き込まず、実行時に環境変数で渡す(現在の設定の
# 読み込みは、Docker の secrets や `_FILE` 形式を読めない)。環境変数は `docker inspect` で
# 見えるので、その権限を絞る。必須の設定がないと、起動に失敗して終了する。
# `FileSystem Connector` が読むディレクトリは、実行時に**読み取り専用(`:ro`)でマウント**する
# 前提で、イメージには含めない。Crawler は検索対象のファイルを書き換えない(compose は別タスク)。
#   Crawler は uid/gid 10001 で動く。マウントするディレクトリ・ファイルは、uid 10001(または others)が
#   読める権限にする(ディレクトリは実行権限も)。ホストの権限を変えたくなければ、compose の
#   `user:`(`docker run --user`)で、ファイルの所有者に合わせる。
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LORELEY_CRAWLER_HTTP_HOST=0.0.0.0

USER crawler

# 既定のポート(`LORELEY_CRAWLER_HTTP_PORT` の既定値。Indexer の 8000 とずらしてある)。
# 変えたときは、公開するポートも合わせる。
EXPOSE 8001

# `/healthz` は、起動時の回復(前回の `running` ジョブの `failed` 化とロックの削除。OpenSearch への
# 読み書き)が終わるまで接続できない(uvicorn は回復の後に始まる)。OpenSearch の応答が遅いと、
# 1 回のリクエストが最大 `LORELEY_CRAWLER_OS_STORE_REQUEST_TIMEOUT_SECONDS` ×
# `LORELEY_CRAWLER_RETRY_MAX_ATTEMPTS` + 待ち = 既定 30 × 3 + 約 3 = 約 93 秒かかる。回復は複数の
# リクエスト(`running` ジョブの一覧、ロックの一覧、記録ごとの更新・削除)なので、遅延が続くと
# Indexer の 120 秒を超えうる。回復が失敗すればプロセスが終了して再起動に任せるので、猶予は
# 「遅いが成功する回復」を待てる長さでよい。`--start-period` は、最悪のリクエスト約 2 回分に
# 近い 180 秒(約 186 秒。仮値で、実測ではない)にしている。起動が遅い環境では伸ばす。
# この間の失敗は unhealthy に数えない(成功すれば即 healthy)。タイムアウト・リトライの設定を
# 伸ばしたときも、あわせて伸ばす。
# curl は slim イメージにないので、標準ライブラリの urllib で確認する。2xx 以外(503 など)は
# 例外になり、終了コード 1(unhealthy)になる。ポートは設定に追従し、プロキシの環境変数は使わない。
# ホストは `127.0.0.1` 固定。`LORELEY_CRAWLER_HTTP_HOST` を特定の IP や IPv6 に変えるときは、
# HEALTHCHECK のホストも合わせる。
HEALTHCHECK --interval=15s --timeout=5s --start-period=180s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request as u; u.build_opener(u.ProxyHandler({})).open('http://127.0.0.1:%s/healthz' % os.environ.get('LORELEY_CRAWLER_HTTP_PORT', '8001'), timeout=3)"]

# 単一プロセスで動かす(ワーカー数は増やさない。`--workers`・`--reload` は使わない)。
# ソース単位のロック・Job Runner・取り消し要求・起床通知はプロセス内にあり、複数プロセスは対象外。
#
# 停止(SIGTERM。`docker stop`)の時間の目安: uvicorn の graceful shutdown(最大 10 秒)→
# Scheduler・Job Runner の停止の待ち(各最大 5 秒。Scheduler のリトライの待ち(最大約 3 秒)は
# この中)で、足して最悪 約 20 秒。処理中の HTTP ハンドラ(Store 層のリトライで最大約 90 秒)が
# あると、さらに遅れる。Docker の既定の猶予(10 秒)では足りないことがあるので、compose の
# `stop_grace_period`(`docker stop --time`)は **30 秒以上**にする(別タスク)。猶予を超えて
# SIGKILL されても、実行中のジョブは次回の起動時の回復が `failed`(`crawler_restart`)にするので
# 安全性は変わらない。実行中のジョブの完了は待たず、終了処理もしない(README の「運用」)。
# `STOPSIGNAL` は既定の SIGTERM のまま(uvicorn が受けて停止処理が走る。PID 1 でも確認済み)。
# 単一プロセスで子プロセスを作らないので、init(tini)も不要。
CMD ["python", "-m", "loreley_crawler.main"]
