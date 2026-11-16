import re
from datetime import UTC, datetime, timedelta, timezone

from loreley_crawler.jobs.records import generate_job_id
from tests.fakes.clock import FixedClock

JOB_ID_FORMAT = re.compile(r"job-\d{8}T\d{6}Z-[0-9a-f]{8}")


def test_job_id_has_the_documented_format(clock: FixedClock) -> None:
    clock.set(datetime(2026, 11, 13, 1, 2, 3, 999000, tzinfo=UTC))

    job_id = generate_job_id(clock, lambda: "3fa9c2d1")

    assert job_id == "job-20261113T010203Z-3fa9c2d1"


def test_the_timestamp_is_utc_whatever_the_offset_of_the_clock(clock: FixedClock) -> None:
    clock.set(datetime(2026, 11, 13, 10, 0, 0, tzinfo=timezone(timedelta(hours=9))))

    assert generate_job_id(clock, lambda: "00000000") == "job-20261113T010000Z-00000000"


def test_the_default_random_part_is_eight_hex_digits(clock: FixedClock) -> None:
    assert JOB_ID_FORMAT.fullmatch(generate_job_id(clock))


def test_job_ids_generated_at_the_same_instant_are_told_apart_by_the_random_part(
    clock: FixedClock,
) -> None:
    tokens = iter(f"{number:08x}" for number in range(200))  # 乱数元を固定して決定的にする

    job_ids = {generate_job_id(clock, lambda: next(tokens)) for _ in range(200)}

    assert len(job_ids) == 200


def test_a_generated_job_id_fits_the_256_byte_limit_with_no_control_characters(
    clock: FixedClock,
) -> None:
    job_id = generate_job_id(clock)

    assert len(job_id.encode("utf-8")) <= 256
    assert job_id.isprintable()
