"""AIT-01: 起動疎通(compose で起動した直後の Admin API の状態の確認)。

目的:
    compose(`opensearch` → `opensearch-init` → `indexer` → `crawler`、`api`)で立ち上げた Admin API が、
    実コンテナ・実 OpenSearch の上で動いていることを確かめる。単体テストでは、compose が渡す環境変数
    (共通変数・索引名・`web` の確認先 URL)が実際に api に届くこと、実 Crawler・Indexer・OpenSearch への
    死活確認、実 `cat.*` の応答を確認できない。

参照する設計書の章:
    - admin-api-v0.1.md 7.1(EP-12)、8.1(EP-13)、8.2(EP-14)
    - api-base-design-v0.1.md 8 章(compose)、6 章(`/healthz`)
    - deploy/compose/compose.yaml(`api` の環境変数・共通変数)、apps/web(実 `web`。api が `http://web:80/admin/` を確認する)

扱うシナリオ: AIT-01
"""

from support import EXPECTED_INDEX_NAMES, AdminApi, expect_json, parse_instant

# スクリプト(scripts/run-api-integration-test.sh)が `LORELEY_CRON_TIMEZONE` に渡す値。Crawler と api に
# 同じ変数から届くこと(HO-43)を、EP-14 の値で確かめる。
EXPECTED_CRON_TIMEZONE = "Asia/Tokyo"

# EP-13 の `components[]` の固定の順(admin-api 8.1)。
DASHBOARD_COMPONENT_IDS = [
    "crawler",
    "indexer",
    "opensearch",
    "api",
    "web",
    "opensearch-dashboards",
    "embedding",
    "llm",
]
# 確認用の URL を設定していない任意コンポーネント。compose は設定しないので `not_configured` になる。
NOT_CONFIGURED_COMPONENT_IDS = ["opensearch-dashboards", "embedding", "llm"]


def test_healthz_returns_ok_without_checking_other_components(api: AdminApi) -> None:
    """【何を確認するか】
    api の `GET /healthz` が 200 `{"status": "ok"}` を返すこと。

    【前提と手順】
    前提: compose で起動済み。手順: ルート直下の `/healthz` を呼ぶ。

    【期待する結果とその根拠】
    200 と `{"status": "ok"}`。`/healthz` は何にも接続せず、受け付けを始めていれば 200 を返す
    (api-base-design 6 章)。コンテナの HEALTHCHECK が使う経路でもある。

    【単体テストでは確認できず実機で確認する点】
    実コンテナで、ホストの 127.0.0.1:8080 から到達でき(publish の確認)、イメージの HEALTHCHECK が通ること。
    """
    body = expect_json(api.healthz(), 200)

    assert body == {"status": "ok"}, f"/healthz must return only the status: {body}"


def test_dashboard_lists_eight_components_in_fixed_order_with_web_normal(api: AdminApi) -> None:
    """【何を確認するか】
    EP-13 `GET /dashboard` が 8 件のコンポーネントを固定の順で返し、実 Crawler・Indexer・OpenSearch・
    api・`web` が `normal`、確認用 URL のない 3 つが `not_configured` であること。

    【前提と手順】
    前提: スクリプトが 5 サービス(opensearch・indexer・crawler・api・web)の healthy を待った後。`web` は
    実 `web`(apps/web のビルド)で、api が `LORELEY_API_WEB_URL`(`http://web:80`)の `/admin/` を確認する。
    手順: EP-13 を呼ぶ。

    【期待する結果とその根拠】
    - `components[].id` が `crawler`・`indexer`・`opensearch`・`api`・`web`・`opensearch-dashboards`・
      `embedding`・`llm` の順で 8 件(B 8.1)。
    - `crawler`・`indexer`・`opensearch`・`api`・`web` は `state=normal`・`reason=null`。
    - `opensearch-dashboards`・`embedding`・`llm` は `state=not_configured`・`reason=null`(確認用 URL が
      未設定なら確認せず `not_configured`。B 8.1)。
    - トップの `checked_at` は、各 `components[].checked_at` 以上(B 8.1)。

    【単体テストでは確認できず実機で確認する点】
    コンテナ内の api から、内部ネットワークのサービス名(`crawler:8001`・`indexer:8000`・`opensearch:9200`・
    `web:80`)で実コンポーネントの `/healthz`・`cluster.health`・`/admin/` の 200 に届くこと(HO-55 の実効の
    確認。compose が `LORELEY_API_WEB_URL` を渡し、実 `web` が `/admin/` に 200 を返すこと)。
    """
    body = expect_json(api.dashboard(), 200)

    components = body["components"]
    assert [component["id"] for component in components] == DASHBOARD_COMPONENT_IDS, (
        f"EP-13 must return the 8 components in the fixed order: {components}"
    )
    for component in components:
        expected_state = (
            "not_configured" if component["id"] in NOT_CONFIGURED_COMPONENT_IDS else "normal"
        )
        assert component["state"] == expected_state, (
            f"{component['id']} must be {expected_state}: {component}"
        )
        assert component["reason"] is None, (
            f"{component['id']} must have no reason when {expected_state}: {component}"
        )

    top_checked_at = parse_instant(body["checked_at"])
    for component in components:
        assert parse_instant(component["checked_at"]) <= top_checked_at, (
            f"checked_at of the response must not precede that of {component['id']}: {body}"
        )


def test_meta_returns_the_cron_timezone_given_by_the_common_variable(api: AdminApi) -> None:
    """【何を確認するか】
    EP-14 `GET /meta` が、共通変数 `LORELEY_CRON_TIMEZONE` の値を `cron_timezone` に返し、
    `dashboards_url` が `null` であること。

    【前提と手順】
    前提: スクリプトが `LORELEY_CRON_TIMEZONE=Asia/Tokyo` を export して compose を起動した。
    手順: EP-14 を呼ぶ。

    【期待する結果とその根拠】
    `cron_timezone=Asia/Tokyo`、`dashboards_url=null`(未設定は `null`。B 8.2)。compose は
    `LORELEY_CRON_TIMEZONE` を Crawler(`LORELEY_CRAWLER_TIMEZONE`)と api(`LORELEY_API_CRON_TIMEZONE`)に
    同じ変数から渡す(HO-43)。

    【単体テストでは確認できず実機で確認する点】
    compose の変数の配線(共通変数 → api の環境変数 → 応答)が実際に通っていること。
    """
    body = expect_json(api.meta(), 200)

    assert body["cron_timezone"] == EXPECTED_CRON_TIMEZONE, (
        f"cron_timezone must follow LORELEY_CRON_TIMEZONE: {body}"
    )
    assert body["dashboards_url"] is None, f"dashboards_url must be null when unset: {body}"


def test_opensearch_cluster_lists_the_four_loreley_indices(api: AdminApi) -> None:
    """【何を確認するか】
    EP-12 `GET /opensearch/cluster` の `indices[]` に、`opensearch-init` が作った 4 つの索引が現れ、
    切り詰めがないこと。

    【前提と手順】
    前提: `opensearch-init` が 4 つの索引を作成済み。手順: EP-12 を呼ぶ。

    【期待する結果とその根拠】
    `loreley-documents-000001`(検索インデックスの実体)・`loreley-deletions`・`loreley-jobs`・
    `loreley-sources` が `indices[].name` に含まれる(B 7.1。`cat.indices` の `index`)。`truncated=false`、
    `total_indices` は `indices[]` の件数に等しい(切り詰めがなければ一致。B 7.1)。9200 を共有する他の
    索引が混ざっても壊れないよう、4 つが含まれることだけを確認する(部分集合)。

    【単体テストでは確認できず実機で確認する点】
    実 OpenSearch の `cat.indices`・`cat.shards`・`cat.nodes`・`cluster.health` を、api が実際に読めて
    DTO に変換できること(`format=json`・`bytes=b` の実応答)。個々の値の照合は AIT-32 が行う。
    """
    body = expect_json(api.opensearch_cluster(), 200)

    index_names = {index["name"] for index in body["indices"]}
    assert index_names >= EXPECTED_INDEX_NAMES, (
        f"the four Loreley indices must exist: missing {sorted(EXPECTED_INDEX_NAMES - index_names)}"
    )
    assert body["truncated"] is False, f"the index list must not be truncated: {body['truncated']}"
    assert body["total_indices"] == len(body["indices"]), (
        f"total_indices must equal the number of indices when not truncated: "
        f"{body['total_indices']} vs {len(body['indices'])}"
    )


def test_openapi_json_is_not_served_by_default(api: AdminApi) -> None:
    """【何を確認するか】
    `OPENAPI_ENABLED` が既定(無効)のとき、`openapi.json` が配信されないこと。

    【前提と手順】
    前提: compose は `LORELEY_API_OPENAPI_ENABLED` を設定しない(既定の無効)。
    手順: `GET /api/admin/v1/openapi.json` を呼ぶ。

    【期待する結果とその根拠】
    404。認証のない api が、API の全体像を既定では公開しない(api-base-design の設定の既定値)。

    【単体テストでは確認できず実機で確認する点】
    compose が `OPENAPI_ENABLED` を渡さないこと(既定のままであること)が、実コンテナでも効いていること。
    """
    response = api.openapi_json()

    assert response.status_code == 404, (
        f"openapi.json must not be served when disabled: {response.status_code} {response.text[:200]}"
    )
