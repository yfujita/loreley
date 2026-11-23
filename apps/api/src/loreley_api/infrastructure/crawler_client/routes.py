"""Crawler に送る固定の 6 経路と、パスの組み立て(C 4.8。D 4.9)。

**パスのリテラルを持つ唯一のファイル**(R8 (d)。`test_read_only_rules.py` が検査する)。
経路は 6 つだけで、メソッドとパスのテンプレートを組にして持つ。ID は全文字をパーセントエンコードして
テンプレートに埋めるので、ID の値で別の経路に落ちることはない。
"""

from dataclasses import dataclass
from urllib.parse import quote


@dataclass(frozen=True)
class CrawlerRoute:
    method: str
    # ログ用(ID を含まない。R11)。
    template: str
    # 送るパス(エンコード済みの ID を埋めたもの)。
    path: str


@dataclass(frozen=True)
class _Template:
    method: str
    template: str

    def fill(self, **ids: str) -> CrawlerRoute:
        encoded = {name: encode_path_segment(value) for name, value in ids.items()}
        return CrawlerRoute(self.method, self.template, self.template.format(**encoded))


_REGISTER_SOURCE = _Template("POST", "/sources")
_UPDATE_SOURCE = _Template("PUT", "/sources/{source_id}")
_START_DELETE_JOB = _Template("POST", "/sources/{source_id}/delete-jobs")
_START_CRAWL = _Template("POST", "/sources/{source_id}/crawl-jobs")
_CANCEL_JOB = _Template("POST", "/jobs/{job_id}/cancel")
_RELEASE_LOCK = _Template("DELETE", "/sources/{source_id}/lock")

# Admin API が Crawler に送る経路のすべて(EP-03〜08。C 4.8)。
ROUTE_TEMPLATES: frozenset[tuple[str, str]] = frozenset(
    (template.method, template.template)
    for template in (
        _REGISTER_SOURCE,
        _UPDATE_SOURCE,
        _START_DELETE_JOB,
        _START_CRAWL,
        _CANCEL_JOB,
        _RELEASE_LOCK,
    )
)


def encode_path_segment(value: str) -> str:
    """ID を全文字パーセントエンコードする(B 2.12・9.1)。

    `quote` は `.` を符号化しないが、urllib3 は URL の正規化でドットセグメントを除去する
    (`job_id=".."` が `/jobs/../cancel` → `/cancel` に崩れ、別の経路に落ちる)。`%2E` は保持される
    ので、`.` も `%2E` にする。
    """
    return quote(value, safe="").replace(".", "%2E")


def register_source() -> CrawlerRoute:
    return _REGISTER_SOURCE.fill()


def update_source(source_id: str) -> CrawlerRoute:
    return _UPDATE_SOURCE.fill(source_id=source_id)


def start_delete_job(source_id: str) -> CrawlerRoute:
    return _START_DELETE_JOB.fill(source_id=source_id)


def start_crawl(source_id: str) -> CrawlerRoute:
    return _START_CRAWL.fill(source_id=source_id)


def cancel_job(job_id: str) -> CrawlerRoute:
    return _CANCEL_JOB.fill(job_id=job_id)


def release_lock(source_id: str) -> CrawlerRoute:
    return _RELEASE_LOCK.fill(source_id=source_id)
