"""プローブ(Protocol)の偽物(D 7.2)。

`services` のテストで、HTTP・OpenSearch・ファイルの確認(本物は `infrastructure/probes/`・
`infrastructure/opensearch/health_probe.py` のテストが確かめる)を持ち込まずに、台本の結果と
呼び出しの記録を使う。

- 結果の差し替え: `probe.behavior.inject("check", ProbeOutcome("abnormal", "missing"), key=url)`。
  `key` は、HTTP のプローブでは確認先の URL、`web` のプローブではディレクトリ、`opensearch` の
  プローブでは指定しない。差し替えがなければ `normal` を返す。
- 呼び出しの記録: `probe.checked`(確認先の URL・ディレクトリ。`opensearch` は空文字)。
- 遅延の再現: `probe.behavior.before("check", release.wait, key=url)` のように、確認の直前に
  待たせる(実物の `BlockingRunner` のスレッドの中で呼ばれる)。

操作名は `OPERATIONS`(`check` だけ)にあるものだけで、それ以外(打ち間違い)は `ValueError`。
Protocol のメソッドと過不足がないことは `test_fake_probes_protocol.py` が確かめる。
"""

from loreley_api.admin import AdminProbes
from loreley_api.common.probe_outcome import ProbeOutcome
from tests.fakes.behavior import FakeBehavior

OPERATIONS = frozenset({"check"})
NORMAL = ProbeOutcome("normal")


class _FakeProbe:
    def __init__(self) -> None:
        self.behavior = FakeBehavior(known_operations=OPERATIONS)
        self.checked: list[str] = []

    def _check(self, target: str, key: str | None) -> ProbeOutcome:
        self.checked.append(target)
        intercepted = self.behavior.enter("check", key)
        return NORMAL if intercepted is None else intercepted.value


class FakeHttpHealthProbe(_FakeProbe):
    def check(self, url: str) -> ProbeOutcome:
        return self._check(url, url)


class FakeOpenSearchHealthProbe(_FakeProbe):
    def check(self) -> ProbeOutcome:
        return self._check("", None)


class FakeWebDistProbe(_FakeProbe):
    def check(self, directory: str) -> ProbeOutcome:
        return self._check(directory, directory)


class FakeProbes:
    """3 つのプローブの偽物。既定はすべて `normal`。"""

    def __init__(self) -> None:
        self.http = FakeHttpHealthProbe()
        self.opensearch = FakeOpenSearchHealthProbe()
        self.web_dist = FakeWebDistProbe()

    def as_admin_probes(self) -> AdminProbes:
        return AdminProbes(http=self.http, opensearch=self.opensearch, web_dist=self.web_dist)
