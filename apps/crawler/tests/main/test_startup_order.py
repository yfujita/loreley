"""起動順(module 5.7。architecture 10章。CA-P-40)。

`main()` を、本物の組み立てで動かす(外への入り口 `create_backends`・`uvicorn.run` だけ差し替える)。
失敗したときは、HTTP の受け付けを始めない(`uvicorn.run` に届かない・アプリケーションを作らない)。
"""

import pytest

from loreley_crawler import main as main_module
from loreley_crawler.common.errors import StoreUnavailableError
from loreley_crawler.config import ConfigError
from tests.fakes import in_memory_repository as ops
from tests.main.support import (
    OPENSEARCH_PASSWORD,
    Fakes,
    install_backends,
    install_uvicorn,
    record_startup,
    set_env,
    started_threads,
)

MIB = 1024 * 1024


def run_main(monkeypatch: pytest.MonkeyPatch, fakes: Fakes, **env: str) -> list[str]:
    events: list[str] = []
    set_env(monkeypatch, **env)
    record_startup(monkeypatch, events)
    install_backends(monkeypatch, fakes, events)
    install_uvicorn(monkeypatch, events)
    main_module.main()
    return events


def test_the_startup_runs_in_the_documented_order_and_stops_in_reverse(
    monkeypatch: pytest.MonkeyPatch, restore_logging: None
) -> None:
    events = run_main(monkeypatch, Fakes())

    assert events == [
        "load_config",
        "configure_logging",
        "warn_about_unchecked_indexer_limits",
        "create_backends",
        "assemble",
        "recovery.run",
        "runner.start",
        "scheduler.start",
        "create_app",
        "uvicorn.run",
        "scheduler.stop",
        "runner.stop",
    ]


def test_the_app_is_created_and_http_is_opened_only_after_the_recovery_finished(
    monkeypatch: pytest.MonkeyPatch, restore_logging: None
) -> None:
    """アプリケーションがなければ uvicorn は接続を受け付けず、回復中は `/healthz` も応答しない。"""
    fakes = Fakes()
    events: list[str] = []
    seen_during_recovery: list[list[str]] = []
    set_env(monkeypatch)
    record_startup(monkeypatch, events)
    install_backends(monkeypatch, fakes)
    install_uvicorn(monkeypatch, events)
    fakes.jobs.behavior.before(
        ops.LIST, lambda: seen_during_recovery.append(list(events))
    )  # 回復の最初の読み取り

    main_module.main()

    [during_recovery] = seen_during_recovery
    assert "recovery.run" in during_recovery
    assert not {"create_app", "uvicorn.run", "runner.start", "scheduler.start"} & set(
        during_recovery
    )


def test_uvicorn_gets_the_configured_host_and_port_and_a_single_quiet_process(
    monkeypatch: pytest.MonkeyPatch, restore_logging: None
) -> None:
    events: list[str] = []
    set_env(monkeypatch, http_host="0.0.0.0", http_port="9123")
    install_backends(monkeypatch, Fakes())
    captured = install_uvicorn(monkeypatch, events)

    main_module.main()

    assert (captured["host"], captured["port"]) == ("0.0.0.0", 9123)
    assert captured["log_config"] is None
    assert captured["access_log"] is False
    assert "workers" not in captured  # アプリケーションのオブジェクトを渡す = 単一プロセス
    assert captured["lifespan"] == "off"


def test_the_threads_are_stopped_after_uvicorn_returns(
    monkeypatch: pytest.MonkeyPatch, restore_logging: None
) -> None:
    before = started_threads()

    run_main(monkeypatch, Fakes())

    assert not {"job-runner", "scheduler"} & (started_threads() - before)


def test_an_exception_while_serving_still_stops_the_threads(
    monkeypatch: pytest.MonkeyPatch, restore_logging: None
) -> None:
    events: list[str] = []
    set_env(monkeypatch)
    record_startup(monkeypatch, events)
    install_backends(monkeypatch, Fakes())

    def failing(app: object, **kwargs: object) -> None:
        raise OSError("address already in use")

    monkeypatch.setattr(main_module.uvicorn, "run", failing)

    with pytest.raises(OSError, match="address already in use"):
        main_module.main()

    assert events[-2:] == ["scheduler.stop", "runner.stop"]


# --- 失敗したら、HTTP を開かずに異常終了する ---


def assert_nothing_started(events: list[str], threads_before: set[str]) -> None:
    assert not {"uvicorn.run", "create_app", "runner.start", "scheduler.start"} & set(events)
    assert not {"job-runner", "scheduler"} & (started_threads() - threads_before)


def test_an_unset_owner_fails_before_any_connection_and_http(
    monkeypatch: pytest.MonkeyPatch, restore_logging: None
) -> None:
    events: list[str] = []
    threads_before = started_threads()
    set_env(monkeypatch)
    monkeypatch.delenv("LORELEY_CRAWLER_OWNER")
    record_startup(monkeypatch, events)
    install_backends(monkeypatch, Fakes(), events)
    install_uvicorn(monkeypatch, events)

    with pytest.raises(ConfigError) as raised:
        main_module.main()

    assert str(raised.value) == "invalid settings: LORELEY_CRAWLER_OWNER: missing"
    assert events == ["load_config"]  # ログの設定も、OpenSearch の接続も始めない
    assert_nothing_started(events, threads_before)


def test_a_consistency_violation_fails_before_any_connection_and_http(
    monkeypatch: pytest.MonkeyPatch, restore_logging: None
) -> None:
    events: list[str] = []
    threads_before = started_threads()
    set_env(
        monkeypatch,
        max_raw_bytes=str(30 * MIB),
        batch_max_raw_bytes=str(40 * MIB),
        indexer_max_raw_bytes=str(20 * MIB),
        opensearch_username="crawler",
        opensearch_password=OPENSEARCH_PASSWORD,
    )
    record_startup(monkeypatch, events)
    install_backends(monkeypatch, Fakes(), events)
    install_uvicorn(monkeypatch, events)

    with pytest.raises(ConfigError) as raised:
        main_module.main()

    assert "startup consistency check failed" in str(raised.value)
    assert OPENSEARCH_PASSWORD not in f"{raised.value} {raised.value!r}"
    assert events == ["load_config"]
    assert_nothing_started(events, threads_before)


def test_a_failed_recovery_never_starts_the_runner_the_scheduler_or_http(
    monkeypatch: pytest.MonkeyPatch, restore_logging: None
) -> None:
    """OpenSearch に接続できない(Store 層の異常がリトライを尽くす)ときの異常終了。"""
    fakes = Fakes()
    fakes.jobs.behavior.inject(
        ops.LIST, StoreUnavailableError("opensearch_unavailable"), times=None
    )
    events: list[str] = []
    threads_before = started_threads()
    set_env(monkeypatch)
    record_startup(monkeypatch, events)
    install_backends(monkeypatch, fakes, events)
    install_uvicorn(monkeypatch, events)

    with pytest.raises(StoreUnavailableError):
        main_module.main()

    assert events[:5] == [
        "load_config",
        "configure_logging",
        "warn_about_unchecked_indexer_limits",
        "create_backends",
        "assemble",
    ]
    assert events[5:] == ["recovery.run"]
    assert_nothing_started(events, threads_before)


def test_no_thread_is_started_before_the_recovery(
    monkeypatch: pytest.MonkeyPatch, restore_logging: None
) -> None:
    fakes = Fakes()
    names_during_recovery: list[set[str]] = []
    before = started_threads()
    fakes.jobs.behavior.before(ops.LIST, lambda: names_during_recovery.append(started_threads()))
    set_env(monkeypatch)
    install_backends(monkeypatch, fakes)
    install_uvicorn(monkeypatch, [])

    main_module.main()

    assert names_during_recovery
    assert not {"job-runner", "scheduler"} & (names_during_recovery[0] - before)


def test_unchecked_indexer_limits_are_warned_after_the_logging_is_set_up(
    monkeypatch: pytest.MonkeyPatch, restore_logging: None, capsys: pytest.CaptureFixture[str]
) -> None:
    run_main(monkeypatch, Fakes(), indexer_max_raw_bytes=str(20 * MIB))

    stderr = capsys.readouterr().err
    assert "WARNING" in stderr and "MAX_BATCH_DOCUMENTS" in stderr
    assert "MAX_RAW_BYTES," not in stderr


@pytest.mark.parametrize(
    ("target", "name", "label"),
    [
        (main_module.JobRunner, "start", "runner.start"),
        (main_module.Scheduler, "start", "scheduler.start"),
        (main_module, "create_app", "create_app"),
    ],
    ids=["runner.start", "scheduler.start", "create_app"],
)
def test_a_failure_after_the_recovery_stops_the_started_threads_and_never_opens_http(
    monkeypatch: pytest.MonkeyPatch, restore_logging: None, target: object, name: str, label: str
) -> None:
    events: list[str] = []
    threads_before = started_threads()
    set_env(monkeypatch)
    record_startup(monkeypatch, events)
    install_backends(monkeypatch, Fakes())
    install_uvicorn(monkeypatch, events)

    def failing(*args: object, **kwargs: object) -> None:
        events.append(f"{label}!")
        raise RuntimeError("startup failure")

    monkeypatch.setattr(target, name, failing)

    with pytest.raises(RuntimeError, match="startup failure"):
        main_module.main()

    assert "uvicorn.run" not in events
    assert events[-2:] == ["scheduler.stop", "runner.stop"]  # 開始したものを止めた
    assert events.index("recovery.run") < events.index(f"{label}!")
    assert not {"job-runner", "scheduler"} & (started_threads() - threads_before)
