"""データソース設定の更新(crawler-api 4.4.3)。"""

import pytest

from loreley_crawler.common.errors import StoreUnavailableError
from loreley_crawler.connectors.interface import ConnectorError, ErrorCategory
from loreley_crawler.sources import SourceStatus
from tests.api.support import SOURCE_ID, ApiEnv, new_source_body, update_body
from tests.fakes.fake_connector import VALIDATE_CONFIG
from tests.fakes.in_memory_repository import FETCH

URL = f"/sources/{SOURCE_ID}"
SEEDED_UPDATED_AT = "2026-11-13T00:00:00.000Z"


def update(api: ApiEnv, **overrides):
    return api.put(URL, update_body(**overrides))


def test_an_update_replaces_the_changeable_fields_and_keeps_connector_type_and_status(
    api: ApiEnv,
) -> None:
    api.jobs.seed_source()
    api.jobs.clock.advance(seconds=60)

    response = update(api, ttl=7, ratio_threshold=0.5, connector_config={"root": "/other"})

    assert response.status_code == 200
    assert response.json() == {
        "source_id": SOURCE_ID,
        "connector_type": "file_system",
        "connector_config": {"root": "/other"},
        "ttl": 7,
        "ratio_threshold": 0.5,
        "min_delete_count": 10,
        "schedule_cron": "0 3 * * *",
        "status": "active",
        "updated_at": "2026-11-13T00:01:00.000Z",
    }
    assert api.sources_repository.body_of(SOURCE_ID)["ttl"] == 7


def test_the_schedule_cron_is_replaced_and_null_makes_it_manual_only(api: ApiEnv) -> None:
    api.jobs.seed_source()
    api.jobs.clock.advance(seconds=60)

    changed = update(api, schedule_cron="*/30 9-17 * * 1-5")
    cleared = update(api, schedule_cron=None)

    assert changed.status_code == 200
    assert changed.json()["schedule_cron"] == "*/30 9-17 * * 1-5"
    assert cleared.status_code == 200
    assert cleared.json()["schedule_cron"] is None
    assert api.sources_repository.body_of(SOURCE_ID)["schedule_cron"] is None


@pytest.mark.parametrize(
    ("value", "reason"),
    [("0 0 3 * * *", "format"), ("@daily", "format"), ("", "format"), (3600, "type")],
)
def test_an_invalid_schedule_cron_is_400_and_leaves_the_stored_one(
    api: ApiEnv, value: object, reason: str
) -> None:
    api.post("/sources", new_source_body(source_id=SOURCE_ID))  # `schedule_cron` は `0 3 * * *`

    response = update(api, schedule_cron=value)

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "invalid_request"
    assert error["details"]["errors"] == [{"field": "schedule_cron", "reason": reason}]
    assert api.sources_repository.body_of(SOURCE_ID)["schedule_cron"] == "0 3 * * *"


def test_a_schedule_cron_that_differs_is_a_change_and_the_same_one_is_not(api: ApiEnv) -> None:
    api.post("/sources", new_source_body(source_id=SOURCE_ID))  # `schedule_cron` は `0 3 * * *`
    api.jobs.clock.advance(seconds=60)

    same = update(api, schedule_cron="0 3 * * *")
    different = update(api, schedule_cron="0 4 * * *")

    assert same.json()["updated_at"] == SEEDED_UPDATED_AT  # 内容が同じなら書き込まない
    assert different.json()["updated_at"] == "2026-11-13T00:01:00.000Z"


def test_an_omitted_schedule_replaces_the_stored_one_with_null(api: ApiEnv) -> None:
    api.jobs.seed_source()
    api.jobs.clock.advance(seconds=60)
    body = update_body()
    del body["schedule_cron"]

    response = api.put(URL, body)

    assert response.status_code == 200
    assert response.json()["schedule_cron"] is None


def test_the_same_content_is_200_without_writing_and_keeps_updated_at(api: ApiEnv) -> None:
    api.jobs.seed_source()
    api.jobs.clock.advance(seconds=60)
    writes_before = len(api.sources_repository.write_calls())
    same = update_body(connector_config={"root": "/data"}, ttl=2_592_000, ratio_threshold=0.3)
    same["schedule_cron"] = None

    response = api.put(URL, same)

    assert response.status_code == 200
    assert response.json()["updated_at"] == SEEDED_UPDATED_AT
    assert len(api.sources_repository.write_calls()) == writes_before


def test_a_missing_source_is_404_source_config_not_found(api: ApiEnv) -> None:
    response = update(api)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "source_config_not_found"


def test_a_deleting_source_is_409_source_deleting_and_is_not_changed(api: ApiEnv) -> None:
    api.jobs.seed_source(status=SourceStatus.DELETING)

    response = update(api, ttl=1)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "source_deleting"
    assert api.sources_repository.body_of(SOURCE_ID)["ttl"] != 1


def test_the_maintenance_flag_does_not_stop_a_configuration_update(api: ApiEnv) -> None:
    api.jobs.seed_source()
    api.jobs.seed_maintenance()  # 案どおり: 設定の更新は、受付の拒否(409)の対象にしない

    assert update(api, ttl=1).status_code == 200


# --- Connector の検証(保存済みの `connector_type` で行う) ---


def test_the_connector_config_is_validated_with_the_stored_connector_type(api: ApiEnv) -> None:
    api.jobs.seed_source()

    update(api, connector_config={"root": "/other"})

    assert api.connector_type.validated_configs == [{"root": "/other"}]


def test_a_config_invalid_update_is_400_and_the_stored_configuration_is_kept(api: ApiEnv) -> None:
    api.jobs.seed_source()
    api.connector_type.behavior.inject(
        VALIDATE_CONFIG, ConnectorError.of(ErrorCategory.CONFIG_INVALID, "root: 絶対パスでない")
    )

    response = update(api, ttl=1)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "config_invalid"
    assert response.json()["error"]["message"] == "root: 絶対パスでない"
    assert api.sources_repository.body_of(SOURCE_ID)["ttl"] != 1


def test_a_connector_internal_error_is_500(api: ApiEnv) -> None:
    api.jobs.seed_source()
    api.connector_type.behavior.inject(VALIDATE_CONFIG, RuntimeError("SENTINEL"))

    response = update(api)

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"


def test_a_missing_source_is_not_validated_by_the_connector(api: ApiEnv) -> None:
    update(api)

    assert api.connector_type.validated_configs == []


def test_a_malformed_record_is_repaired_by_an_update_validated_with_its_connector_type(
    api: ApiEnv,
) -> None:
    api.sources_repository.seed(
        SOURCE_ID,
        {"source_id": SOURCE_ID, "connector_type": "file_system", "status": "active", "ttl": "x"},
    )

    response = update(api)

    assert response.status_code == 200
    assert api.connector_type.validated_configs == [{"root": "/data"}]


@pytest.mark.parametrize(
    "stored",
    [
        {"source_id": SOURCE_ID, "connector_type": "file_system", "status": "garbage"},
        {"source_id": SOURCE_ID, "connector_type": 5, "status": "active"},
    ],
)
def test_a_record_whose_status_or_connector_type_cannot_be_kept_is_500_internal_error(
    api: ApiEnv, stored: dict
) -> None:
    api.sources_repository.seed(SOURCE_ID, stored)

    response = update(api)

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert api.sources_repository.body_of(SOURCE_ID) == stored


def test_a_transient_failure_of_reading_the_stored_connector_type_is_retried(api: ApiEnv) -> None:
    api.jobs.seed_source()
    api.sources_repository.behavior.inject(FETCH, StoreUnavailableError("blip"), times=1)

    response = update(api, ttl=7)

    assert response.status_code == 200
    assert api.connector_type.validated_configs == [{"root": "/data"}]


def test_a_persistent_failure_of_reading_the_stored_connector_type_is_503(api: ApiEnv) -> None:
    api.jobs.seed_source()
    api.sources_repository.behavior.inject(FETCH, StoreUnavailableError("down"), times=None)

    response = update(api, ttl=7)

    assert response.status_code == 503
    assert api.sources_repository.body_of(SOURCE_ID)["ttl"] != 7
