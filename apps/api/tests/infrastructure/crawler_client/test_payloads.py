"""Crawler に送る本文の形(B 9.2)。"""

import json

import pytest

from loreley_api.infrastructure.crawler_client import CrawlerSourceSettings, payloads

SETTINGS = CrawlerSourceSettings(
    connector_config={"root": "/data/documents/share", "include_patterns": ["*.md"]},
    ttl_seconds=2_592_000,
    ratio_threshold=0.2,
    min_delete_count=10,
    schedule_cron="0 3 * * *",
)


def test_the_register_payload_has_the_seven_fields_of_the_crawler_api() -> None:
    payload = payloads.register_payload("docs-share", "file_system", SETTINGS)

    assert payload == {
        "source_id": "docs-share",
        "connector_type": "file_system",
        "connector_config": {"root": "/data/documents/share", "include_patterns": ["*.md"]},
        "ttl": 2_592_000,
        "ratio_threshold": 0.2,
        "min_delete_count": 10,
        "schedule_cron": "0 3 * * *",
    }


def test_the_update_payload_is_a_full_replacement_without_source_id_and_connector_type() -> None:
    payload = payloads.update_payload(SETTINGS)

    assert set(payload) == {
        "connector_config",
        "ttl",
        "ratio_threshold",
        "min_delete_count",
        "schedule_cron",
    }


def test_a_missing_schedule_cron_is_sent_as_null_not_omitted() -> None:
    payload = payloads.update_payload(
        CrawlerSourceSettings(
            {}, ttl_seconds=1, ratio_threshold=0, min_delete_count=0, schedule_cron=None
        )
    )

    assert payload["schedule_cron"] is None
    assert "schedule_cron" in json.loads(payloads.encode_json(payload))


@pytest.mark.parametrize(
    ("force_delete", "rewrite_mode"), [(False, False), (True, False), (True, True)]
)
def test_both_crawl_options_are_always_sent_explicitly(
    force_delete: bool, rewrite_mode: bool
) -> None:
    payload = payloads.crawl_payload(force_delete=force_delete, rewrite_mode=rewrite_mode)

    assert payload == {"force_delete": force_delete, "rewrite_mode": rewrite_mode}


def test_the_json_is_ascii_utf8_with_booleans_not_numbers() -> None:
    encoded = payloads.encode_json({"name": "日本語", "flag": True})

    assert encoded.decode("ascii") == '{"name": "\\u65e5\\u672c\\u8a9e", "flag": true}'


def test_a_lone_surrogate_is_encodable_and_left_to_the_crawler_to_reject() -> None:
    assert payloads.encode_json({"root": "\ud800"}) == b'{"root": "\\ud800"}'


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_a_non_finite_number_is_a_bug_and_is_not_sent(value: float) -> None:
    with pytest.raises(ValueError, match="Out of range float values"):
        payloads.encode_json({"ratio_threshold": value})
