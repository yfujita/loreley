"""データソース設定の登録(crawler-api 4.4.2)。"""

from loreley_crawler.connectors.interface import ConnectorError, ErrorCategory
from loreley_crawler.sources import SourceStatus
from tests.api.support import CONNECTOR_TYPE, ApiEnv, new_source_body
from tests.fakes.fake_connector import VALIDATE_CONFIG

SOURCE_ID = "docs-share"
UPDATED_AT = "2026-11-13T00:00:00.000Z"


def register(api: ApiEnv, **overrides):
    return api.post("/sources", new_source_body(**overrides))


def test_a_new_source_is_201_and_the_response_is_the_saved_configuration(api: ApiEnv) -> None:
    response = register(api)

    assert response.status_code == 201
    assert response.json() == {
        "source_id": SOURCE_ID,
        "connector_type": CONNECTOR_TYPE,
        "connector_config": {"root": "/data"},
        "ttl": 2_592_000,
        "ratio_threshold": 0.3,
        "min_delete_count": 10,
        "schedule_cron": "0 3 * * *",
        "status": "active",
        "updated_at": UPDATED_AT,
    }
    stored = api.sources_repository.body_of(SOURCE_ID)
    assert stored is not None
    assert (stored["status"], stored["updated_at"]) == ("active", UPDATED_AT)


def test_the_schedule_may_be_omitted_or_null_for_manual_only(api: ApiEnv) -> None:
    omitted = new_source_body(source_id="omitted")
    del omitted["schedule_cron"]

    assert api.post("/sources", omitted).json()["schedule_cron"] is None
    assert register(api, source_id="explicit", schedule_cron=None).json()["schedule_cron"] is None


def test_a_schedule_cron_is_saved_as_given(api: ApiEnv) -> None:
    response = register(api, schedule_cron="*/15 * * * *")

    assert response.status_code == 201
    assert response.json()["schedule_cron"] == "*/15 * * * *"
    assert (api.sources_repository.body_of(SOURCE_ID) or {})["schedule_cron"] == "*/15 * * * *"


def test_the_old_interval_setting_is_an_unknown_field(api: ApiEnv) -> None:
    body = new_source_body()
    body["schedule_interval_seconds"] = 86_400

    response = api.post("/sources", body)

    assert response.status_code == 400
    assert response.json()["error"]["details"]["errors"] == [
        {"field": "schedule_interval_seconds", "reason": "unknown_field"}
    ]


def test_the_threshold_range_is_not_checked_here_because_the_admin_api_checks_it(
    api: ApiEnv,
) -> None:  # CAPI-K-3 / CA-K-16
    response = register(api, ratio_threshold=5, ttl=-1, min_delete_count=-3)

    assert response.status_code == 201


def test_the_connector_config_is_validated_by_the_connector_before_saving(api: ApiEnv) -> None:
    response = register(api, connector_config={"root": "/data", "x": [1, {"y": None}]})

    assert response.status_code == 201
    assert api.connector_type.validated_configs == [{"root": "/data", "x": [1, {"y": None}]}]


def test_the_same_content_again_is_200_with_the_saved_configuration(api: ApiEnv) -> None:
    first = register(api)
    api.jobs.clock.advance(seconds=60)

    second = register(api)

    assert (first.status_code, second.status_code) == (201, 200)
    assert second.json() == first.json()  # `updated_at` も変わらない


def test_the_key_order_and_numeric_type_of_the_threshold_do_not_matter(api: ApiEnv) -> None:
    register(api, ratio_threshold=1)

    response = api.post(
        "/sources",
        raw=(
            b'{"schedule_cron": "0 3 * * *", "min_delete_count": 10, "ratio_threshold": 1.0,'
            b' "ttl": 2592000, "connector_config": {"root": "/data"},'
            b' "connector_type": "file_system", "source_id": "docs-share"}'
        ),
    )

    assert response.status_code == 200


def test_a_different_content_is_409_source_already_exists_with_the_status(api: ApiEnv) -> None:
    register(api)

    response = register(api, ttl=1)

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "source_already_exists"
    assert error["retryable"] is False
    assert error["details"] == {"status": "active"}


def test_a_deleting_source_is_409_even_for_the_same_content(api: ApiEnv) -> None:
    register(api)
    api.sources_repository.seed(
        SOURCE_ID, {**api.sources_repository.body_of(SOURCE_ID), "status": "deleting"}
    )

    response = register(api)

    assert response.status_code == 409
    assert response.json()["error"]["details"] == {"status": SourceStatus.DELETING.value}


def test_an_existing_record_with_an_unreadable_status_is_409_with_a_null_status(
    api: ApiEnv,
) -> None:
    api.sources_repository.seed(SOURCE_ID, {"source_id": SOURCE_ID, "status": "garbage"})

    response = register(api)

    assert response.status_code == 409
    assert response.json()["error"]["details"] == {"status": None}


def test_a_source_can_be_registered_again_after_it_was_deleted(api: ApiEnv) -> None:
    register(api)
    # 設定の削除はソース削除ジョブだけが行う(`SourceStore` の順 0 と順 5)。
    api.source_store.mark_deleting(SOURCE_ID)
    api.source_store.delete(SOURCE_ID)

    assert register(api).status_code == 201


# --- Connector の検証 ---


def test_a_config_invalid_from_the_connector_is_400_with_its_message_and_nothing_is_saved(
    api: ApiEnv,
) -> None:
    api.connector_type.behavior.inject(
        VALIDATE_CONFIG, ConnectorError.of(ErrorCategory.CONFIG_INVALID, "root: 必須の項目がない")
    )

    response = register(api)

    assert response.status_code == 400
    error = response.json()["error"]
    assert (error["code"], error["message"], error["retryable"]) == (
        "config_invalid",
        "root: 必須の項目がない",
        False,
    )
    assert "details" not in error
    assert api.sources_repository.body_of(SOURCE_ID) is None


def test_a_connector_internal_error_is_500_internal_error_without_its_description(
    api: ApiEnv,
) -> None:
    api.connector_type.behavior.inject(VALIDATE_CONFIG, RuntimeError("SENTINEL-inner-description"))

    response = register(api)

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "SENTINEL" not in response.text
    assert api.sources_repository.body_of(SOURCE_ID) is None


def test_the_connector_is_not_asked_when_the_request_itself_is_malformed(api: ApiEnv) -> None:
    response = register(api, ttl="x")

    assert response.status_code == 400
    assert api.connector_type.validated_configs == []


def test_a_long_config_invalid_message_is_cut_to_512_characters(api: ApiEnv) -> None:
    api.connector_type.behavior.inject(
        VALIDATE_CONFIG, ConnectorError.of(ErrorCategory.CONFIG_INVALID, "x" * 600)
    )

    response = register(api)

    assert response.status_code == 400
    assert response.json()["error"]["message"] == "x" * 512


def test_control_characters_in_a_config_invalid_message_are_escaped(api: ApiEnv) -> None:
    api.connector_type.behavior.inject(
        VALIDATE_CONFIG,
        ConnectorError.of(ErrorCategory.CONFIG_INVALID, "line1\nline2\x00 \ud800"),
    )

    response = register(api)

    assert response.status_code == 400
    assert response.json()["error"]["message"] == "line1\\nline2\\x00 \ufffd"
