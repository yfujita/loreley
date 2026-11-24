"""`deletion.*` の元(C 5.4・5.7)。"""

from typing import Any

import pytest

from loreley_api.admin.base.codes import DeletionConfirmation
from loreley_api.admin.derivation.deletion_view import (
    DeletionSettingsView,
    read_deletion_confirmation,
    read_deletion_current,
    read_deletion_settings,
    read_deletion_summary,
)

SUMMARY = {
    "status": "completed",
    "reason": "ok",
    "forced": False,
    "target_count": 12,
    "denominator": 1000,
    "deleted_count": 12,
    "enumerated_count": 1000,
    "n_seen": 990,
    "e_missing": 2,
    "finish_received_at": "2026-11-22T15:10:05.000Z",
    "deletion_started_at": "2026-11-22T15:10:06+09:00",
    "finished_at": "2026-11-22T15:10:09.999Z",
    "observed_at": None,
}


def test_the_summary_passes_the_documented_items_with_datetimes_in_utc() -> None:
    summary = read_deletion_summary({"deletion_summary": SUMMARY})

    assert summary is not None
    assert (summary.status, summary.reason, summary.forced) == ("completed", "ok", False)
    assert (summary.target_count, summary.denominator, summary.deleted_count) == (12, 1000, 12)
    assert (summary.enumerated_count, summary.n_seen, summary.e_missing) == (1000, 990, 2)
    assert summary.finish_received_at == "2026-11-22T15:10:05.000Z"
    assert summary.deletion_started_at == "2026-11-22T06:10:06.000Z"
    assert summary.finished_at == "2026-11-22T15:10:09.999Z"
    assert summary.observed_at is None


def test_an_item_missing_from_the_summary_is_none() -> None:
    summary = read_deletion_summary({"deletion_summary": {"status": "completed"}})

    assert summary is not None
    assert summary.status == "completed"
    assert summary.target_count is None
    assert summary.observed_at is None


@pytest.mark.parametrize("value", [None, "text", [], 3])
def test_a_summary_that_is_not_an_object_is_none(value: object) -> None:
    assert read_deletion_summary({"deletion_summary": value}) is None
    assert read_deletion_summary({}) is None


def test_unreadable_summary_items_are_none_one_by_one() -> None:
    summary = read_deletion_summary(
        {
            "deletion_summary": {
                "status": 1,
                "forced": "no",
                "target_count": True,
                "finished_at": "x",
            }
        }
    )

    assert summary is not None
    assert summary.status is None
    assert summary.forced is None
    assert summary.target_count is None
    assert summary.finished_at is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("confirmed", DeletionConfirmation.CONFIRMED),
        ("unconfirmed", DeletionConfirmation.UNCONFIRMED),
        ("unknown", DeletionConfirmation.UNKNOWN),
        # 確認に入っていないジョブ・許される値にない値は `null`。
        (None, None),
        ("pending", None),
        (1, None),
    ],
)
def test_the_confirmation_is_one_of_the_three_values(
    value: object, expected: DeletionConfirmation | None
) -> None:
    assert read_deletion_confirmation({"confirmation": value}) is expected


def test_the_current_value_is_read_from_the_deletion_result() -> None:
    current = read_deletion_current(
        {
            "record_type": "deletion_result",
            "status": "completed",
            "reason": "ok",
            "reason_detail": "detail",
            "forced": True,
            "target_count": 5,
            "denominator": 50,
            "deleted_count": 5,
            "ended_at": "2026-11-22T15:20:00.000Z",
        }
    )

    assert (current.status, current.reason, current.reason_detail) == ("completed", "ok", "detail")
    assert (current.forced, current.target_count, current.denominator) == (True, 5, 50)
    assert (current.deleted_count, current.ended_at) == (5, "2026-11-22T15:20:00.000Z")


def test_unreadable_values_of_the_deletion_result_are_none() -> None:
    current = read_deletion_current({"status": 5, "forced": "x", "ended_at": "yesterday"})

    assert (current.status, current.forced, current.ended_at, current.target_count) == (
        None,
        None,
        None,
        None,
    )


def test_the_settings_are_converted_from_the_snapshot_to_seconds_and_percent() -> None:
    settings = read_deletion_settings(
        {"settings_snapshot": {"ttl": 2_592_000, "ratio_threshold": 0.2, "min_delete_count": 10}}
    )

    assert settings == DeletionSettingsView(2_592_000, 20, 10)


def test_a_ratio_is_converted_without_float_error() -> None:
    settings = read_deletion_settings({"settings_snapshot": {"ratio_threshold": 0.29}})

    assert settings is not None
    assert settings.ratio_threshold_percent == 29


@pytest.mark.parametrize("snapshot", [None, "text", 5, []])
def test_no_snapshot_means_no_settings(snapshot: object) -> None:
    assert read_deletion_settings({"settings_snapshot": snapshot}) is None
    assert read_deletion_settings({}) is None


@pytest.mark.parametrize(
    "snapshot",
    [
        {"ttl": "30", "ratio_threshold": "0.2", "min_delete_count": 1.5},
        {"ttl": True, "ratio_threshold": True, "min_delete_count": None},
        {},
    ],
)
def test_unreadable_snapshot_items_are_none_item_by_item(snapshot: dict[str, Any]) -> None:
    settings = read_deletion_settings({"settings_snapshot": snapshot})

    assert settings == DeletionSettingsView(None, None, None)


def test_a_readable_item_survives_an_unreadable_neighbour() -> None:
    settings = read_deletion_settings({"settings_snapshot": {"ttl": 60, "ratio_threshold": "x"}})

    assert settings == DeletionSettingsView(60, None, None)
