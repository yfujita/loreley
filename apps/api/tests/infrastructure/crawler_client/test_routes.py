"""固定の 6 経路とパスのエンコード(C 4.8。C 11章 3)。"""

import pytest

from loreley_api.infrastructure.crawler_client import routes


@pytest.mark.parametrize(
    ("value", "encoded"),
    [
        ("source-a", "source-a"),
        ("a_b-c", "a_b-c"),
        # `quote` は `.` を符号化しないが、urllib3 がドットセグメントを除去するので `%2E` にする。
        (".", "%2E"),
        ("..", "%2E%2E"),
        ("a.b", "a%2Eb"),
        ("%", "%25"),
        ("a%2Fb", "a%252Fb"),  # すでに符号化された形の文字列も、`%` から符号化する
        ("a/b", "a%2Fb"),
        ("x?y", "x%3Fy"),
        ("x#y", "x%23y"),
        ("a b", "a%20b"),
        ("日本", "%E6%97%A5%E6%9C%AC"),
        ("a\nb", "a%0Ab"),
    ],
)
def test_a_path_segment_is_encoded_in_every_character(value: str, encoded: str) -> None:
    assert routes.encode_path_segment(value) == encoded


def test_an_encoded_segment_never_contains_a_path_or_dot_character() -> None:
    nasty = "../..//%2e%2E/?#\\ ;"

    encoded = routes.encode_path_segment(nasty)

    assert not any(character in encoded for character in "/.?#\\ ;")


def test_the_six_routes_are_the_fixed_ones_of_the_architecture_document() -> None:
    assert routes.register_source() == routes.CrawlerRoute("POST", "/sources", "/sources")
    assert routes.update_source("docs") == routes.CrawlerRoute(
        "PUT", "/sources/{source_id}", "/sources/docs"
    )
    assert routes.start_delete_job("docs") == routes.CrawlerRoute(
        "POST", "/sources/{source_id}/delete-jobs", "/sources/docs/delete-jobs"
    )
    assert routes.start_crawl("docs") == routes.CrawlerRoute(
        "POST", "/sources/{source_id}/crawl-jobs", "/sources/docs/crawl-jobs"
    )
    assert routes.cancel_job("job-1") == routes.CrawlerRoute(
        "POST", "/jobs/{job_id}/cancel", "/jobs/job-1/cancel"
    )
    assert routes.release_lock("docs") == routes.CrawlerRoute(
        "DELETE", "/sources/{source_id}/lock", "/sources/docs/lock"
    )


def test_route_templates_list_exactly_the_six_routes() -> None:
    expected = {
        ("POST", "/sources"),
        ("PUT", "/sources/{source_id}"),
        ("POST", "/sources/{source_id}/delete-jobs"),
        ("POST", "/sources/{source_id}/crawl-jobs"),
        ("POST", "/jobs/{job_id}/cancel"),
        ("DELETE", "/sources/{source_id}/lock"),
    }

    listed = set(routes.ROUTE_TEMPLATES)

    assert listed == expected


def test_an_id_with_a_brace_cannot_change_the_template() -> None:
    """ID はテンプレートの書式ではなく値として埋める(`{}` は符号化されて残らない)。"""
    route = routes.cancel_job("{job_id}")

    assert route.path == "/jobs/%7Bjob_id%7D/cancel"


def test_the_template_for_logs_contains_no_id() -> None:
    assert "SENTINEL" not in routes.cancel_job("SENTINEL-JOB").template
