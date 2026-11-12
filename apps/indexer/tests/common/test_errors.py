import pytest

from loreley_indexer.common.errors import (
    AdmissionRejectedError,
    ContractError,
    CrawlAlreadyClosedError,
    CrawlAlreadyFinishedError,
    CrawlFinishedError,
    CrawlNotFoundError,
    CrawlNotStartedError,
    CrawlSourceMismatchError,
    CrawlStartConflictError,
    CrawlStartedAtMismatchError,
    FinishContentMismatchError,
    FinishSourceMismatchError,
    IndexerError,
    LockNotOwnedError,
    NotificationRejectedError,
    StaleCrawlStartedAtError,
    UnavailableError,
)


def test_unavailable_error_is_an_indexer_error_carrying_only_a_reason() -> None:
    error = UnavailableError("http_503")
    assert isinstance(error, IndexerError)
    assert error.reason == "http_503"
    assert str(error) == "http_503"


@pytest.mark.parametrize(
    "error_type",
    [
        CrawlNotStartedError,
        CrawlSourceMismatchError,
        CrawlStartedAtMismatchError,
        CrawlAlreadyClosedError,
        CrawlFinishedError,
    ],
)
def test_admission_rejections_are_non_retryable_409_contract_errors(
    error_type: type[AdmissionRejectedError],
) -> None:
    error = error_type()
    assert isinstance(error, ContractError)
    assert isinstance(error, IndexerError)
    assert error.status_code == 409
    assert error.retryable is False
    assert str(error) == error.message


def test_admission_rejection_codes_are_distinct() -> None:
    codes = {error_type.code for error_type in AdmissionRejectedError.__subclasses__()}
    assert codes == {
        "crawl_not_started",
        "crawl_source_mismatch",
        "crawl_started_at_mismatch",
        "crawl_already_closed",
        "crawl_finished",
    }


@pytest.mark.parametrize(
    ("error_type", "code"),
    [
        (CrawlAlreadyFinishedError, "crawl_already_finished"),
        (CrawlStartConflictError, "crawl_start_conflict"),
        (StaleCrawlStartedAtError, "stale_crawl_started_at"),
        (FinishSourceMismatchError, "finish_source_mismatch"),
        (FinishContentMismatchError, "finish_content_mismatch"),
    ],
)
def test_notification_rejections_are_non_retryable_409_contract_errors(
    error_type: type[NotificationRejectedError], code: str
) -> None:  # api 3.4
    error = error_type()
    assert isinstance(error, ContractError)
    assert (error.status_code, error.code, error.retryable) == (409, code, False)
    assert str(error) == error.message


def test_notification_rejection_codes_are_distinct_from_admission_rejections() -> None:
    notification_codes = {e.code for e in NotificationRejectedError.__subclasses__()}
    admission_codes = {e.code for e in AdmissionRejectedError.__subclasses__()}
    assert len(notification_codes) == 5
    assert notification_codes.isdisjoint(admission_codes)


def test_crawl_not_found_is_a_non_retryable_404_contract_error() -> None:
    error = CrawlNotFoundError()
    assert isinstance(error, ContractError)
    assert (error.status_code, error.code, error.retryable) == (404, "crawl_not_found", False)


def test_lock_not_owned_is_a_non_retryable_409_contract_error() -> None:  # api 3.4、4.7、4.8
    error = LockNotOwnedError()
    assert isinstance(error, ContractError)
    assert not isinstance(error, AdmissionRejectedError)  # 登録の受理条件の拒否とは別
    assert (error.status_code, error.code, error.retryable) == (409, "lock_not_owned", False)
    assert str(error) == error.message
