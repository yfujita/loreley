"""登録結果の集計(`RegistrationTally`。architecture 7.7。テスト観点 #20)と連続スキップの計数。"""

import pytest

from loreley_crawler.crawl import ConsecutiveSkipCounter, CrawlSettings, RegistrationTally
from loreley_crawler.infrastructure.indexer_client import Change, DocumentRegistered
from loreley_crawler.jobs import SkipStage


def registered(
    document_id: str, change: Change = Change.CREATED, *, extract_failed: bool = False
) -> DocumentRegistered:
    return DocumentRegistered(f"{document_id}.txt", document_id, change, extract_failed)


def test_a_new_tally_is_zero_and_partial() -> None:
    assert RegistrationTally().to_record(enumerated_count=0) == {
        "enumerated_count": 0,
        "created_count": 0,
        "updated_count": 0,
        "unchanged_count": 0,
        "skipped_count": 0,
        "oversize_count": 0,
        "error_count": 0,
        "invalid_id_count": 0,
        "partial": True,
    }


def test_the_record_contains_only_json_types() -> None:
    tally = RegistrationTally()
    tally.record_registered(registered("a"))
    tally.record_skipped("s")
    tally.record_oversize("o")
    tally.record_invalid_id()

    record = tally.to_record(enumerated_count=4)

    assert all(type(value) in (int, bool) for value in record.values())
    assert record["skipped_count"] == 1
    assert record["oversize_count"] == 1
    assert record["invalid_id_count"] == 1


def test_the_first_ok_result_of_a_document_is_kept_and_a_later_one_is_not_counted() -> None:
    tally = RegistrationTally()

    assert tally.record_registered(registered("a", Change.CREATED)) is True
    assert tally.record_registered(registered("a", Change.UNCHANGED)) is False
    assert tally.record_registered(registered("a", Change.UPDATED, extract_failed=True)) is False

    record = tally.to_record(enumerated_count=1)
    assert (record["created_count"], record["updated_count"], record["unchanged_count"]) == (
        1,
        0,
        0,
    )
    assert record["error_count"] == 0


def test_ids_are_deduplicated_and_keep_their_order() -> None:
    tally = RegistrationTally()
    for document_id in ["b", "a", "b"]:
        tally.record_skipped(document_id)
    tally.record_oversize("z")
    tally.record_oversize("y")
    tally.record_oversize("z")

    assert tally.skipped_document_ids == ("b", "a")
    assert tally.oversize_document_ids == ("z", "y")
    assert tally.to_record(enumerated_count=0)["skipped_count"] == 2
    assert tally.is_skipped("a")
    assert not tally.is_skipped("y")  # 種類ごとに照会する
    assert tally.is_oversize("y")
    assert not tally.is_oversize("a")
    assert not tally.is_skipped("c")
    assert not tally.is_oversize("c")


def test_registered_count_counts_documents_once() -> None:
    tally = RegistrationTally()

    tally.record_registered(registered("a"))
    tally.record_registered(registered("a", Change.UPDATED))
    tally.record_registered(registered("b"))

    assert tally.registered_count == 2


def test_finalize_makes_partial_false() -> None:
    tally = RegistrationTally()
    assert tally.partial is True

    tally.finalize()

    assert tally.partial is False
    assert tally.to_record(enumerated_count=0)["partial"] is False


# --- ConsecutiveSkipCounter ---


def test_the_limit_is_reached_after_that_many_consecutive_skips_of_a_stage() -> None:
    counter = ConsecutiveSkipCounter(3)

    assert [counter.record_skip(SkipStage.FETCH) for _ in range(3)] == [False, False, True]


def test_a_success_resets_only_its_own_stage() -> None:
    counter = ConsecutiveSkipCounter(3)
    counter.record_skip(SkipStage.FETCH)
    counter.record_skip(SkipStage.FETCH)
    counter.record_skip(SkipStage.INDEX)
    counter.record_skip(SkipStage.INDEX)

    counter.record_success(SkipStage.FETCH)

    assert counter.record_skip(SkipStage.FETCH) is False  # 取得段階は 1 に戻った
    assert counter.record_skip(SkipStage.INDEX) is True  # 登録段階は 3 件目(リセットされていない)


def test_the_stages_are_counted_separately() -> None:
    counter = ConsecutiveSkipCounter(3)

    assert counter.record_skip(SkipStage.FETCH) is False
    assert counter.record_skip(SkipStage.INDEX) is False
    assert counter.record_skip(SkipStage.FETCH) is False
    assert counter.record_skip(SkipStage.INDEX) is False


def test_the_counter_rejects_a_non_positive_limit() -> None:
    with pytest.raises(ValueError, match="limit"):
        ConsecutiveSkipCounter(0)


@pytest.mark.parametrize(
    "name",
    [
        "chunk_size",
        "last_seen_max_ids",
        "batch_max_documents",
        "batch_max_raw_bytes",
        "consecutive_skip_limit",
        "invalid_id_example_limit",
    ],
)
def test_settings_must_be_positive(name: str) -> None:
    with pytest.raises(ValueError, match=name):
        CrawlSettings(**{name: 0})


def test_default_settings_are_the_provisional_values_of_architecture_11() -> None:
    settings = CrawlSettings()

    assert settings.chunk_size == 500
    assert settings.last_seen_max_ids == 500
    assert settings.batch_max_documents == 20
    assert settings.batch_max_raw_bytes == 32 * 1024 * 1024
    assert settings.consecutive_skip_limit == 20
    assert settings.invalid_id_example_limit == 20
