"""`GET /healthz`(案: CAPI-P-19・CM-P-27。契約外の運用用 API)。

担当機能(`jobs`・`sources`)を呼ばずに 200 を返す。回復の完了前は応答しない(アプリケーションを
回復の後に作る起動順)ことは、起動順を組み立てる `main.py` のテストの範囲。
"""

from typing import Any

from fastapi.testclient import TestClient

from loreley_crawler.api import ApiDependencies, create_app
from tests.api.support import ApiEnv


class Tripwire:
    """どの属性に触れても失敗する。担当機能を呼んだことを検出する。"""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"the health check must not touch a feature: {name}")


def test_healthz_is_200_with_status_ok(api: ApiEnv) -> None:
    response = api.client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_healthz_does_not_call_any_feature() -> None:
    tripwire: Any = Tripwire()
    dependencies = ApiDependencies(
        job_admission=tripwire,
        job_cancellation=tripwire,
        lock_release=tripwire,
        source_store=tripwire,
        connector_registry=tripwire,
        retrier=tripwire,
    )
    client = TestClient(create_app(dependencies), raise_server_exceptions=False)

    response = client.get("/healthz")

    assert response.status_code == 200


def test_healthz_does_not_read_or_write_the_stores(api: ApiEnv) -> None:
    api.client.get("/healthz")

    assert api.jobs.jobs_repository.behavior.calls == []
    assert api.sources_repository.behavior.calls == []
    assert api.connector_type.behavior.calls == []


def test_healthz_does_not_depend_on_the_state_of_the_jobs_and_the_maintenance_flag(
    api: ApiEnv,
) -> None:
    api.jobs.seed_maintenance()
    api.jobs.seed_lock("job-1")

    assert api.client.get("/healthz").status_code == 200


def test_healthz_returns_no_internal_information(api: ApiEnv) -> None:
    assert set(api.client.get("/healthz").json()) == {"status"}


def test_only_get_is_defined_for_healthz(api: ApiEnv) -> None:
    response = api.client.post("/healthz")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


def test_no_endpoint_other_than_the_six_apis_and_healthz_exists(api: ApiEnv) -> None:
    # FastAPI は取り込んだルーターを遅延展開するので、公開される経路は OpenAPI の定義から読む
    # (ドキュメントのエンドポイントは公開しないが、`openapi()` は呼べる)。
    routes = {
        (method.upper(), path)
        for path, operations in api.app.openapi()["paths"].items()
        for method in operations
    }

    assert routes == {
        ("GET", "/healthz"),
        ("POST", "/sources/{source_id}/crawl-jobs"),
        ("POST", "/sources/{source_id}/delete-jobs"),
        ("POST", "/jobs/{job_id}/cancel"),
        ("DELETE", "/sources/{source_id}/lock"),
        ("POST", "/sources"),
        ("PUT", "/sources/{source_id}"),
    }


def test_the_api_documentation_endpoints_are_not_published(api: ApiEnv) -> None:
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert api.client.get(path).status_code == 404
