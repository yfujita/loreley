"""`SourceSettings` の元と `malformed`(C 5.7・5.8。EP-02)。"""

from typing import Any

import pytest

from loreley_api.admin.base.codes import SourceStatus
from loreley_api.admin.derivation.settings_view import read_source_settings

VALID: dict[str, Any] = {
    "connector_type": "file_system",
    "connector_config": {"root": "/data/documents", "include_patterns": ["**/*.md"]},
    "ttl": 2_592_000,
    "ratio_threshold": 0.2,
    "min_delete_count": 10,
    "schedule_cron": "0 3 * * *",
    "status": "active",
    "updated_at": "2026-11-22T10:00:00+09:00",
}


def test_valid_settings_are_converted_to_the_response_units() -> None:
    view = read_source_settings("docs", VALID)

    assert view.source_id == "docs"
    assert view.connector_type == "file_system"
    assert view.connector_config == VALID["connector_config"]
    assert (view.ttl_seconds, view.ttl_days) == (2_592_000, 30)
    assert view.ratio_threshold_percent == 20
    assert view.min_delete_count == 10
    assert view.schedule_cron == "0 3 * * *"
    assert view.status is SourceStatus.ACTIVE
    assert view.updated_at == "2026-11-22T01:00:00.000Z"
    assert view.malformed == ()


def test_the_ratio_is_not_polluted_by_float_error() -> None:
    assert (
        read_source_settings("docs", {**VALID, "ratio_threshold": 0.29}).ratio_threshold_percent
        == 29
    )


def test_ttl_days_is_none_without_a_malformed_mark_when_the_seconds_do_not_divide_by_a_day() -> (
    None
):
    view = read_source_settings("docs", {**VALID, "ttl": 90})

    assert (view.ttl_seconds, view.ttl_days) == (90, None)
    assert view.malformed == ()


@pytest.mark.parametrize("schedule_cron", [None, "@daily"])
def test_a_null_schedule_is_a_valid_manual_only_setting(schedule_cron: str | None) -> None:
    view = read_source_settings("docs", {**VALID, "schedule_cron": schedule_cron})

    assert view.schedule_cron == schedule_cron
    assert view.malformed == ()


def test_a_missing_schedule_key_is_read_as_null() -> None:
    settings = {key: value for key, value in VALID.items() if key != "schedule_cron"}

    view = read_source_settings("docs", settings)

    assert view.schedule_cron is None
    assert view.malformed == ()


@pytest.mark.parametrize(
    ("stored_key", "bad_value", "field"),
    [
        ("connector_type", 1, "connector_type"),
        ("connector_type", None, "connector_type"),
        ("connector_config", "text", "connector_config"),
        ("connector_config", None, "connector_config"),
        ("ttl", "30", "ttl_seconds"),
        ("ttl", True, "ttl_seconds"),
        ("ttl", 1.5, "ttl_seconds"),
        ("ratio_threshold", "0.2", "ratio_threshold_percent"),
        ("ratio_threshold", True, "ratio_threshold_percent"),
        ("ratio_threshold", float("nan"), "ratio_threshold_percent"),
        ("min_delete_count", 1.5, "min_delete_count"),
        ("min_delete_count", False, "min_delete_count"),
        ("schedule_cron", 5, "schedule_cron"),
        ("status", "weird", "status"),
        ("status", None, "status"),
        ("updated_at", "2026-11-22T10:00:00", "updated_at"),
        ("updated_at", None, "updated_at"),
    ],
)
def test_an_unreadable_stored_value_is_none_and_marked_malformed(
    stored_key: str, bad_value: object, field: str
) -> None:
    view = read_source_settings("docs", {**VALID, stored_key: bad_value})

    assert view.malformed == (field,)
    assert getattr(view, field) is None


def test_ttl_days_is_none_when_the_seconds_are_malformed_and_only_the_seconds_are_marked() -> None:
    view = read_source_settings("docs", {**VALID, "ttl": "30"})

    assert (view.ttl_seconds, view.ttl_days) == (None, None)
    assert view.malformed == ("ttl_seconds",)


def test_every_malformed_item_is_reported_in_the_field_order() -> None:
    view = read_source_settings("docs", {})

    assert view.malformed == (
        "connector_type",
        "connector_config",
        "ttl_seconds",
        "ratio_threshold_percent",
        "min_delete_count",
        "status",
        "updated_at",
    )


def test_the_source_id_is_the_document_id_whatever_the_source_says() -> None:
    assert (
        read_source_settings("document-id", {**VALID, "source_id": "other"}).source_id
        == "document-id"
    )
