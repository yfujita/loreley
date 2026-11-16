"""実 uvicorn・実プロセス・実シグナルでの起動と停止(A1)。

メモリ上の Repository と fake の Indexer(`process_entry.py`)で `main()` を動かす。待ちは、行の
読み取りスレッドのキュー(上限つき)で行い、スリープに頼らない。
"""

import json
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
import uvicorn

from loreley_crawler import main as main_module
from tests.main.conftest import PREFIX
from tests.main.support import REQUIRED, make_components, make_config

CRAWLER_ROOT = Path(__file__).resolve().parents[2]
WAIT_TIMEOUT_SECONDS = 30.0
PORT_PATTERN = re.compile(r"Uvicorn running on http://127\.0\.0\.1:(\d+)")


def process_environment() -> dict[str, str]:
    """インストール済みでなくても動くよう、`src` とリポジトリのルートを `PYTHONPATH` に入れる。"""
    environment = {name: value for name, value in os.environ.items() if not name.startswith(PREFIX)}
    environment["PYTHONPATH"] = os.pathsep.join([str(CRAWLER_ROOT / "src"), str(CRAWLER_ROOT)])
    environment.update({PREFIX + name: value for name, value in REQUIRED.items()})
    environment[PREFIX + "RETRY_INITIAL_BACKOFF_SECONDS"] = "0"
    environment[PREFIX + "RETRY_MAX_BACKOFF_SECONDS"] = "0"
    environment[PREFIX + "HTTP_HOST"] = "127.0.0.1"
    return environment


class RunningCrawler:
    """起動した `main()` のプロセス。stderr の行を、キューで受け取る。"""

    def __init__(self) -> None:
        self.process = subprocess.Popen(
            [sys.executable, "-m", "tests.main.process_entry"],
            cwd=CRAWLER_ROOT,
            env=process_environment(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.lines: queue.Queue[str | None] = queue.Queue()
        self.seen: list[str] = []
        self._reader = threading.Thread(target=self._read_stderr, daemon=True)
        self._reader.start()

    def _read_stderr(self) -> None:
        assert self.process.stderr is not None
        for line in self.process.stderr:
            self.lines.put(line)
        self.lines.put(None)

    def wait_for_line(self, pattern: re.Pattern[str] | str) -> re.Match[str]:
        compiled = re.compile(pattern) if isinstance(pattern, str) else pattern
        while True:
            line = self.lines.get(timeout=WAIT_TIMEOUT_SECONDS)
            if line is None:
                raise AssertionError("the process ended: " + "".join(self.seen))
            self.seen.append(line)
            if match := compiled.search(line):
                return match

    def drain(self) -> str:
        """プロセスが終わるまで、残りの行を読む。"""
        while (line := self.lines.get(timeout=WAIT_TIMEOUT_SECONDS)) is not None:
            self.seen.append(line)
        return "".join(self.seen)

    def get_json(self, port: int, path: str) -> tuple[int, dict]:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=10) as response:
            return response.status, json.load(response)


@contextmanager
def running_crawler() -> Iterator[tuple[RunningCrawler, int]]:
    crawler = RunningCrawler()
    try:
        port = int(crawler.wait_for_line(PORT_PATTERN).group(1))
        yield crawler, port
    finally:
        if crawler.process.poll() is None:
            crawler.process.kill()
        crawler.process.wait(timeout=WAIT_TIMEOUT_SECONDS)
        if crawler.process.stdout is not None:
            crawler.process.stdout.close()
        if crawler.process.stderr is not None:
            crawler.process.stderr.close()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
@pytest.mark.parametrize("stop_signal", [signal.SIGTERM, signal.SIGINT], ids=["SIGTERM", "SIGINT"])
def test_a_stop_signal_stops_the_server_and_runs_the_stop_sequence_then_exits_zero(
    stop_signal: signal.Signals,
) -> None:
    with running_crawler() as (crawler, port):
        assert crawler.get_json(port, "/healthz") == (200, {"status": "ok"})

        crawler.process.send_signal(stop_signal)
        output = crawler.drain()
        exit_code = crawler.process.wait(timeout=WAIT_TIMEOUT_SECONDS)

    assert exit_code == 0
    assert "starting the HTTP server" in output
    assert "the crawler stopped" in output  # 停止処理(`stop_components`)まで走った
    assert "Traceback" not in output
    assert output.index("startup recovery finished") < output.index("starting the HTTP server")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
def test_after_the_stop_no_port_is_left_listening() -> None:
    with running_crawler() as (crawler, port):
        crawler.process.send_signal(signal.SIGTERM)
        crawler.drain()
        crawler.process.wait(timeout=WAIT_TIMEOUT_SECONDS)

    with pytest.raises(OSError):
        urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=2)


def test_the_real_uvicorn_serves_healthz_with_the_options_main_uses_and_stops_on_request() -> None:
    """`main()` と同じ引数(ポートだけ空き)で、実 uvicorn が `/healthz` に 200 を返し、停止する。"""
    config = make_config(http_host="127.0.0.1")
    components, _ = make_components(config=config)
    app = main_module.create_app(components.api_dependencies)
    options = {**main_module.http_server_options(config), "port": 0}
    server = uvicorn.Server(uvicorn.Config(app, **options))
    assert server.config.workers == 1
    assert (server.config.log_config, server.config.access_log) == (None, False)
    assert server.config.lifespan == "off"
    assert server.config.timeout_graceful_shutdown == main_module.HTTP_GRACEFUL_SHUTDOWN_SECONDS
    started = threading.Event()
    original_startup = server.startup

    async def startup(sockets=None):  # type: ignore[no-untyped-def]
        await original_startup(sockets=sockets)
        started.set()

    server.startup = startup  # type: ignore[method-assign]
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        assert started.wait(WAIT_TIMEOUT_SECONDS)
        port = server.servers[0].sockets[0].getsockname()[1]
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=10) as response:
            assert (response.status, json.load(response)) == (200, {"status": "ok"})
    finally:
        server.should_exit = True
        thread.join(timeout=WAIT_TIMEOUT_SECONDS)

    assert not thread.is_alive()
