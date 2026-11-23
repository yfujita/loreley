"""admin のテストが使う、偽物での組み立て。"""

from loreley_api.admin import (
    AdminDependencies,
    AdminReaders,
    AdminSettings,
    build_admin_dependencies,
)
from tests.api_config import make_admin_settings
from tests.fakes.clock import FixedClock
from tests.fakes.in_memory_readers import InMemoryReaders
from tests.fakes.inline_runner import InlineRunner

ADMIN_PREFIX = "/api/admin/v1"


def make_admin_dependencies(
    readers: InMemoryReaders,
    clock: FixedClock,
    runner: InlineRunner,
    settings: AdminSettings | None = None,
) -> AdminDependencies:
    return build_admin_dependencies(
        settings=settings if settings is not None else make_admin_settings(),
        clock=clock,
        # `BlockingRunner` の偽物(スレッドなし。実物は `tests/common/test_concurrency.py`)。
        runner=runner,  # type: ignore[arg-type]
        readers=AdminReaders(
            sources=readers.sources,
            jobs=readers.jobs,
            deletions=readers.deletions,
            cluster=readers.cluster,
        ),
    )
