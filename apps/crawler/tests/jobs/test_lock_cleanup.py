"""版条件つきのロック文書の削除と、競合したときの読み直し(architecture 5.5)。"""

import pytest

from loreley_crawler.common.errors import StoreUnavailableError
from loreley_crawler.infrastructure.opensearch import NotFound
from loreley_crawler.jobs.lock_cleanup import delete_lock_unless_taken_over
from loreley_crawler.jobs.locks import LockDocument
from tests.fakes import in_memory_repository as ops
from tests.jobs.support import JOB_ID, LOCK_ID, OTHER_JOB_ID, OTHER_OWNER, SOURCE_ID, make_env


def is_ours(lock: LockDocument) -> bool:
    return lock.job_id == JOB_ID


def test_the_lock_is_deleted_with_the_version_read() -> None:
    env = make_env()
    lock = env.seed_lock(JOB_ID)

    assert delete_lock_unless_taken_over(env.lock_store, lock, is_target=is_ours) is True
    assert env.lock_body() is None


def test_a_moved_version_is_reread_and_the_lock_is_deleted_again() -> None:
    env = make_env()
    lock = env.seed_lock(JOB_ID)
    env.seed_lock(JOB_ID, lease_expires_at="2026-11-13T00:05:00.000Z")  # 版が進む

    assert delete_lock_unless_taken_over(env.lock_store, lock, is_target=is_ours) is True
    assert env.lock_body() is None


def test_a_lock_that_is_already_gone_counts_as_done() -> None:
    env = make_env()
    lock = env.seed_lock(JOB_ID)
    stored = env.jobs_repository.fetch(LOCK_ID)
    assert stored is not None
    env.jobs_repository.delete_if_unchanged(
        LOCK_ID, seq_no=stored.seq_no, primary_term=stored.primary_term
    )

    assert delete_lock_unless_taken_over(env.lock_store, lock, is_target=is_ours) is True


def test_a_lock_taken_over_by_another_job_is_left_alone() -> None:
    env = make_env()
    lock = env.seed_lock(JOB_ID)
    env.seed_lock(OTHER_JOB_ID, owner=OTHER_OWNER)  # 版が進み、別のジョブのロックになった

    assert delete_lock_unless_taken_over(env.lock_store, lock, is_target=is_ours) is False

    remaining = env.lock_body()
    assert remaining is not None
    assert remaining["job_id"] == OTHER_JOB_ID


def test_a_contention_that_never_resolves_raises() -> None:
    env = make_env()
    lock = env.seed_lock(JOB_ID)
    for _ in range(3):
        env.jobs_repository.behavior.before(ops.DELETE, lambda: env.seed_lock(JOB_ID), key=LOCK_ID)

    with pytest.raises(StoreUnavailableError) as raised:
        delete_lock_unless_taken_over(env.lock_store, lock, is_target=is_ours)

    assert raised.value.reason == "lock_cleanup_contention"
    assert env.lock_store.read(SOURCE_ID) is not None


def test_a_not_found_reply_to_the_delete_is_treated_as_a_conflict_and_the_lock_is_reread() -> None:
    env = make_env()
    lock = env.seed_lock(JOB_ID)
    env.jobs_repository.behavior.inject(ops.DELETE, NotFound(), key=LOCK_ID, times=1)

    assert delete_lock_unless_taken_over(env.lock_store, lock, is_target=is_ours) is True

    assert env.lock_body() is None  # 読み直して、もう一度消した
