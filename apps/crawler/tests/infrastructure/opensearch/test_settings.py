import pytest

from loreley_crawler.infrastructure.opensearch import LIST_MAX_SIZE, RepositorySettings


def test_the_defaults_are_the_provisional_values_of_architecture_11() -> None:
    settings = RepositorySettings()

    assert settings.scan_page_size == 1_000
    assert settings.scan_pit_keep_alive_seconds == 60
    assert settings.bulk_delete_batch_size == 1_000
    assert settings.scan_request_timeout_seconds > 0  # 仮値(architecture 11章では空欄)


@pytest.mark.parametrize(
    "overrides",
    [
        {"scan_page_size": 0},
        {"scan_pit_keep_alive_seconds": 0},
        {"scan_request_timeout_seconds": 0.0},
        {"bulk_delete_batch_size": 0},
    ],
)
def test_non_positive_values_are_rejected(overrides: dict[str, float]) -> None:
    with pytest.raises(ValueError, match="must be"):
        RepositorySettings(**overrides)


def test_the_scan_page_size_must_not_exceed_the_result_window() -> None:
    assert RepositorySettings(scan_page_size=LIST_MAX_SIZE).scan_page_size == LIST_MAX_SIZE
    with pytest.raises(ValueError, match="scan_page_size"):
        RepositorySettings(scan_page_size=LIST_MAX_SIZE + 1)
