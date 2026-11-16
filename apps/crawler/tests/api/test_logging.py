"""ログ・エラー応答に、本文・`connector_config`・秘密が出ないこと(R11。完了条件 8)。

センチネルの文字列を、リクエストの本文・`connector_config`・例外のメッセージに入れ、全ロガー
(DEBUG 以上)の出力に現れないことを確かめる。
"""

import logging

import pytest

from loreley_crawler.common.errors import StoreUnavailableError, StoreUnexpectedResponseError
from loreley_crawler.connectors.interface import ConnectorError, ErrorCategory
from loreley_crawler.jobs import JobStatus
from tests.api.support import (
    BODY_SENTINEL,
    CONFIG_SECRET,
    ApiEnv,
    new_source_body,
    update_body,
)
from tests.fakes.fake_connector import VALIDATE_CONFIG
from tests.fakes.in_memory_repository import FETCH
from tests.jobs.support import JOB_ID

SENTINELS = (BODY_SENTINEL, CONFIG_SECRET, "SENTINEL-exception-message")
ID_SENTINEL = "sentinel-source-id"
ACCESS_LOGGER = "loreley_crawler.api.access"


def assert_no_sentinel(text: str) -> None:
    for sentinel in SENTINELS:
        assert sentinel not in text, sentinel


def secret_config() -> dict:
    return {"root": "/data", "credential_ref": CONFIG_SECRET}


def test_requests_that_succeed_or_are_rejected_leave_no_sentinel_in_the_logs(
    api: ApiEnv, caplog: pytest.LogCaptureFixture
) -> None:
    api.jobs.seed_source()
    api.jobs.seed_job(JOB_ID, status=JobStatus.RUNNING)

    with caplog.at_level(logging.DEBUG):
        responses = [
            api.post("/sources", new_source_body(connector_config=secret_config())),
            api.post("/sources", new_source_body(connector_config=secret_config(), ttl=1)),
            api.post("/sources", new_source_body(connector_config=secret_config(), ttl="x")),
            api.post("/sources", new_source_body(note=BODY_SENTINEL)),
            api.put(
                "/sources/docs", update_body(connector_config=secret_config(), ttl=BODY_SENTINEL)
            ),
            api.put("/sources/docs", update_body(connector_config=secret_config())),
            api.post("/sources/docs/crawl-jobs", {"force_delete": BODY_SENTINEL}),
            api.post("/sources/docs/crawl-jobs", raw=BODY_SENTINEL.encode()),
            api.post("/sources/docs/crawl-jobs"),
            api.post("/sources/docs/crawl-jobs"),
            api.post("/sources/docs/delete-jobs"),
            api.post(f"/jobs/{JOB_ID}/cancel"),
            api.client.delete("/sources/docs/lock"),
        ]

    assert {response.status_code for response in responses} >= {200, 201, 202, 400, 409}
    assert_no_sentinel(caplog.text)
    # 400 の応答にも、入力値は出ない(正常な応答は、保存した設定を返すので対象外)。
    for response in responses:
        if response.status_code >= 400:
            assert_no_sentinel(response.text)


def test_the_connector_error_message_is_in_the_400_response_but_never_in_the_logs(
    api: ApiEnv, caplog: pytest.LogCaptureFixture
) -> None:
    message = "SENTINEL-connector-message"
    api.connector_type.behavior.inject(
        VALIDATE_CONFIG, ConnectorError.of(ErrorCategory.CONFIG_INVALID, message)
    )

    with caplog.at_level(logging.DEBUG):
        response = api.post("/sources", new_source_body())

    assert response.json()["error"]["message"] == message  # crawler-api 3.3 が許す唯一の例外
    assert message not in caplog.text


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("SENTINEL-exception-message"),
        StoreUnavailableError("fixed_reason"),
        StoreUnexpectedResponseError("fixed_type"),
        OSError(2, "SENTINEL-exception-message", "/SENTINEL-exception-message"),
    ],
)
def test_failures_log_only_the_class_name_and_fixed_diagnostics(
    api: ApiEnv, caplog: pytest.LogCaptureFixture, error: Exception
) -> None:
    api.jobs.seed_source()
    api.sources_repository.behavior.inject(FETCH, error, times=None)

    with caplog.at_level(logging.DEBUG):
        response = api.post("/sources/docs/crawl-jobs", {"note": CONFIG_SECRET})

    assert response.status_code in (500, 503, 400)
    assert_no_sentinel(caplog.text)
    assert_no_sentinel(response.text)
    assert not [record for record in caplog.records if record.exc_info]  # トレースバックは出さない


def test_the_connector_internal_error_description_is_not_logged(
    api: ApiEnv, caplog: pytest.LogCaptureFixture
) -> None:
    api.connector_type.behavior.inject(VALIDATE_CONFIG, RuntimeError("SENTINEL-exception-message"))

    with caplog.at_level(logging.DEBUG):
        response = api.post("/sources", new_source_body(connector_config=secret_config()))

    assert response.status_code == 500
    assert_no_sentinel(caplog.text)


def test_the_access_log_has_the_route_template_not_the_real_path(
    api: ApiEnv, caplog: pytest.LogCaptureFixture
) -> None:
    api.jobs.seed_source(ID_SENTINEL)

    with caplog.at_level(logging.INFO, logger=ACCESS_LOGGER):
        api.post(f"/sources/{ID_SENTINEL}/crawl-jobs")
        api.client.delete(f"/sources/{ID_SENTINEL}/lock")
        api.post("/jobs/job-sentinel/cancel")
        api.client.get(f"/no/such/{ID_SENTINEL}")

    lines = [record.getMessage() for record in caplog.records if record.name == ACCESS_LOGGER]
    assert [line.rsplit(" ", 1)[0] for line in lines] == [
        "POST /sources/{source_id}/crawl-jobs 202",
        "DELETE /sources/{source_id}/lock 409",
        "POST /jobs/{job_id}/cancel 404",
        "GET - 404",
    ]
    assert ID_SENTINEL not in caplog.text
    assert "job-sentinel" not in caplog.text


def test_the_health_check_is_logged_at_debug_and_the_other_paths_at_info(
    api: ApiEnv, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG, logger=ACCESS_LOGGER):
        api.client.get("/healthz")
        api.client.get("/nope")

    levels = {
        record.getMessage().rsplit(" ", 1)[0]: record.levelno
        for record in caplog.records
        if record.name == ACCESS_LOGGER
    }
    assert levels == {"GET /healthz 200": logging.DEBUG, "GET - 404": logging.INFO}
