"""0 件列挙の警告のための、直前に完了したクロールの取得(architecture 7.7。#36 の取得部分)。"""

from typing import Any

import pytest

from loreley_crawler.jobs.records import PreviousCrawl, find_previous_completed_crawl
from tests.fakes.in_memory_repository import InMemoryRepository
from tests.jobs.records.support import job_fields

CURRENT = "job-20261113T000500Z-00000009"


def seed_job(
    repository: InMemoryRepository,
    number: int,
    *,
    registration: Any = None,
    source_id: str = "docs",
    job_type: str = "crawl",
    **overrides: Any,
) -> str:
    job_id = f"job-20261113T00{number:02d}00Z-{number:08x}"
    fields = job_fields(
        job_id,
        source_id=source_id,
        job_type=job_type,
        queued_at=f"2026-11-13T00:{number:02d}:00.000Z",
        **overrides,
    )
    if registration is not None:
        fields["registration"] = registration
    repository.seed(job_id, fields)
    return job_id


def completed(count: int) -> dict[str, Any]:
    return {"enumerated_count": count, "partial": False}


def find(
    repository: InMemoryRepository, *, excluding: str = CURRENT, max_jobs: int = 10
) -> PreviousCrawl | None:
    return find_previous_completed_crawl(
        repository, source_id="docs", excluding_job_id=excluding, max_jobs=max_jobs
    )


def test_the_newest_completed_crawl_is_returned() -> None:
    repository = InMemoryRepository()
    seed_job(repository, 1, registration=completed(5))
    newest = seed_job(repository, 2, registration=completed(7))

    assert find(repository) == PreviousCrawl(newest, 7)


def test_a_previous_crawl_with_zero_documents_is_returned_as_is() -> None:
    repository = InMemoryRepository()
    previous = seed_job(repository, 1, registration=completed(0))

    assert find(repository) == PreviousCrawl(previous, 0)


def test_the_own_job_is_excluded_even_if_it_has_a_completed_registration() -> None:
    repository = InMemoryRepository()
    older = seed_job(repository, 1, registration=completed(5))
    repository.seed(
        CURRENT,
        {
            **job_fields(CURRENT, queued_at="2026-11-13T00:09:00.000Z"),
            "registration": completed(0),
        },
    )

    assert find(repository) == PreviousCrawl(older, 5)


def test_a_crawl_whose_registration_is_still_partial_is_skipped() -> None:
    repository = InMemoryRepository()
    done = seed_job(repository, 1, registration=completed(5))
    seed_job(repository, 2, registration={"enumerated_count": 3, "partial": True})
    seed_job(repository, 3)  # registration なし(queued など)

    assert find(repository) == PreviousCrawl(done, 5)


def test_other_sources_and_other_job_types_are_ignored() -> None:
    repository = InMemoryRepository()
    mine = seed_job(repository, 1, registration=completed(5))
    seed_job(repository, 2, registration=completed(9), source_id="other")
    seed_job(repository, 3, registration=completed(9), job_type="source_delete")

    assert find(repository) == PreviousCrawl(mine, 5)


def test_records_that_are_not_jobs_are_ignored() -> None:
    repository = InMemoryRepository()
    repository.seed(
        "lock-docs",
        {"record_type": "lock", "source_id": "docs", "registration": completed(9)},
    )

    assert find(repository) is None


def test_no_previous_completed_crawl_is_none() -> None:
    repository = InMemoryRepository()
    seed_job(repository, 1, registration={"enumerated_count": 3, "partial": True})

    assert find(repository) is None
    assert find(InMemoryRepository()) is None


def test_the_search_is_limited_to_max_jobs_newest_jobs() -> None:
    repository = InMemoryRepository()
    seed_job(repository, 1, registration=completed(5))  # 古い完了済み
    for number in (2, 3, 4):
        seed_job(repository, number, registration={"enumerated_count": 1, "partial": True})

    assert find(repository, max_jobs=3) is None  # 新しい 3 件に完了済みがない
    assert find(repository, max_jobs=4) is not None


def test_the_own_job_does_not_use_up_the_limit() -> None:
    repository = InMemoryRepository()
    previous = seed_job(repository, 1, registration=completed(5))
    repository.seed(CURRENT, job_fields(CURRENT, queued_at="2026-11-13T00:09:00.000Z"))

    assert find(repository, max_jobs=1) == PreviousCrawl(previous, 5)


@pytest.mark.parametrize(
    "registration",
    [
        {"enumerated_count": "3", "partial": False},
        {"enumerated_count": True, "partial": False},
        {"enumerated_count": None, "partial": False},
        {"partial": False},
        "oops",
    ],
)
def test_a_malformed_registration_is_skipped_in_favour_of_an_older_crawl(
    registration: Any,
) -> None:
    repository = InMemoryRepository()
    older = seed_job(repository, 1, registration=completed(5))
    seed_job(repository, 2, registration=registration)

    assert find(repository) == PreviousCrawl(older, 5)


def test_partial_must_be_the_boolean_false() -> None:
    repository = InMemoryRepository()
    seed_job(repository, 1, registration={"enumerated_count": 5, "partial": None})
    seed_job(repository, 2, registration={"enumerated_count": 5, "partial": 0})
    seed_job(repository, 3, registration={"enumerated_count": 5})

    assert find(repository) is None


def test_a_non_positive_limit_is_rejected() -> None:
    with pytest.raises(ValueError):
        find(InMemoryRepository(), max_jobs=0)


def test_crawls_queued_at_the_same_instant_are_ordered_by_job_id_descending() -> None:
    """同時刻の `queued_at` は `job_id` の降順(新しい順の並べ替えの、一意なタイブレーク)。"""
    repository = InMemoryRepository()
    for job_id in ("job-a", "job-c", "job-b"):
        repository.seed(
            job_id,
            job_fields(job_id, queued_at="2026-11-13T00:01:00.000Z", registration=completed(3)),
        )

    assert find(repository) == PreviousCrawl("job-c", 3)
