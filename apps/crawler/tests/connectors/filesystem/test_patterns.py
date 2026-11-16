"""パターン構文(FS 設計書 2.2・2.3。10章 #5)。"""

import itertools
import time

import pytest

from loreley_crawler.connectors.filesystem.patterns import (
    compile_pattern,
    find_pattern_violation,
    matches_any,
)
from tests.unicode_samples import GA_NFC, GA_NFD

MAX_BYTES = 1024


def violation_of(pattern: str, *, max_bytes: int = MAX_BYTES) -> str | None:
    return find_pattern_violation(pattern, max_bytes=max_bytes)


def matches(pattern: str, relative_path: str) -> bool:
    assert violation_of(pattern) is None
    return matches_any((compile_pattern(pattern),), relative_path)


# FS 設計書 2.3 の「一致の例」の表。
@pytest.mark.parametrize(
    ("pattern", "matching", "not_matching"),
    [
        ("**/*.md", ["a.md", "x/y/a.md"], ["a.txt"]),
        ("*.md", ["a.md"], ["x/a.md"]),
        ("docs/**", ["docs", "docs/a.md", "docs/x/y.md"], ["docsx/a.md", "x/docs/a.md"]),
        ("**/drafts/**", ["drafts", "a/b/drafts/x.md"], ["a/drafts2/x.md"]),
        ("a/**/b.md", ["a/b.md", "a/x/y/b.md"], ["ab.md"]),
        ("**/lost+found", ["lost+found", "a/lost+found"], []),
        ("report-?.pdf", ["report-1.pdf"], ["report-10.pdf"]),
        ("a?b.txt", ["a\\b.txt"], ["a/b.txt"]),
        ("資料/**", ["資料/が.txt"], []),
        ("**/a/**/b", ["a/b", "x/a/y/z/b"], ["ab", "x/a/b/c"]),
    ],
)
def test_the_examples_of_the_design_match_as_documented(
    pattern: str, matching: list[str], not_matching: list[str]
) -> None:
    for relative_path in matching:
        assert matches(pattern, relative_path), relative_path
    for relative_path in not_matching:
        assert not matches(pattern, relative_path), relative_path


def test_a_star_does_not_cross_a_slash() -> None:
    assert not matches("a*b", "a/b")
    assert matches("a*b", "ab")
    assert matches("a*b", "axxb")
    assert not matches("*", "x/y")


def test_a_question_mark_matches_one_character_other_than_slash() -> None:
    assert matches("a?c", "a\nc")
    assert not matches("a?c", "a/c")
    assert not matches("a?c", "ac")


def test_a_lone_double_star_matches_everything() -> None:
    assert matches("**", "a")
    assert matches("**", "a/b/c.txt")


def test_matching_is_against_the_whole_path_and_case_sensitive() -> None:
    assert not matches("a.md", "x/a.md")
    assert not matches("a.md", "a.mdx")
    assert not matches("*.md", "A.MD")


def test_other_regex_and_glob_characters_are_literal() -> None:
    assert matches("a[1].md", "a[1].md")
    assert not matches("a[1].md", "a1.md")
    assert matches("{x,y}.md", "{x,y}.md")
    assert matches("a+b(c).md", "a+b(c).md")
    assert matches("a.b", "a.b")
    assert not matches("a.b", "axb")


def test_a_pattern_written_in_nfd_matches_a_path_in_nfc_after_normalization() -> None:
    nfd_pattern = f"{GA_NFD}/*.txt"
    nfc_path = f"{GA_NFC}/a.txt"

    assert matches(nfd_pattern, nfc_path)


@pytest.mark.parametrize(
    "pattern",
    [
        "**.md",  # `**` は単独のセグメントとしてだけ使える
        "a**",
        "***",
        "a/**b/c",
        "**/**",  # `**` のセグメントが隣り合う
        "a/**/**",
        "a/**/**/b",
        "/a",  # 先頭・末尾の `/`
        "a/",
        "a//b",  # 空のセグメント
        ".",
        "..",
        "a/../b",
        "./a",
        "a\\b",  # `\` は使えない
        "",
        "a\x00b",
        "a\ud800b",
    ],
)
def test_violating_patterns_are_reported(pattern: str) -> None:
    assert violation_of(pattern) is not None


@pytest.mark.parametrize(
    "pattern",
    ["**", "a/**", "**/a", "**/a/**/b", "*.md", "a/*/b", "a?b", "[x]{y}", "..a", "a..", ".hidden"],
)
def test_valid_patterns_are_accepted(pattern: str) -> None:
    assert violation_of(pattern) is None


def test_the_length_limit_counts_utf8_bytes() -> None:
    assert violation_of("a" * 1024, max_bytes=1024) is None
    assert violation_of("a" * 1025, max_bytes=1024) is not None
    assert violation_of("あ" * 341 + "a", max_bytes=1024) is None  # 1024 バイト
    assert violation_of("あ" * 341 + "aa", max_bytes=1024) is not None  # 1025 バイト
    assert violation_of("あ" * 342, max_bytes=1024) is not None  # 342 文字でも 1026 バイト


def test_the_violation_text_never_contains_the_pattern() -> None:
    violation = violation_of("SECRET-PATTERN\\")

    assert violation is not None
    assert "SECRET" not in violation


def test_double_star_and_a_trailing_double_star_match_names_with_a_newline() -> None:
    # `**`・`P/**` は改行を含む名前にも当たる。
    assert matches("**", "a\nb")
    assert matches("**", "dir/a\nb/c")
    assert matches("docs/**", "docs/a\nb")
    assert matches("docs/**", "docs/a\nb/c\nd")
    assert matches("**/*.md", "x\ny/z\nw.md")
    assert matches("a*b", "a\nb")
    assert matches("a?b", "a\nb")


def test_the_number_of_double_stars_is_not_limited() -> None:
    # 照合が多項式の時間なので、`**` の個数の上限はない(設計書にない設定値を増やさない)。
    pattern = "/".join(["**", "a"] * 100 + ["b"])

    assert violation_of(pattern) is None
    assert matches(pattern, "/".join(["a"] * 100 + ["b"]))
    assert matches(pattern, "/".join(["x", "a"] * 100 + ["b"]))
    assert not matches(pattern, "/".join(["a"] * 99 + ["b"]))


# --- 照合の仕様の確認(一致の位置・`**` の 0 個・`*` の戻り) ---


@pytest.mark.parametrize(
    ("pattern", "path", "expected"),
    [
        # `**`(中)は 0 個以上のセグメント。
        ("a/**/b", "a/b", True),
        ("a/**/b", "a/x/b", True),
        ("a/**/b", "a/x/y/b", True),
        ("a/**/b", "a/x/c", False),
        ("**/x", "x", True),
        ("**/x", "a/b/x", True),
        ("**/x", "a/b/xx", False),
        ("**/a/**/b", "a/b", True),
        ("**/a/**/b", "x/a/y/b", True),
        ("**/a/**/b", "x/b/a", False),
        # `P/**` は `P` 自体と配下。
        ("a/**", "a", True),
        ("a/**", "a/b/c", True),
        ("a/**", "b/a", False),
        ("a/*/**", "a", False),
        ("a/*/**", "a/b", True),
        ("**/a/**", "x/a", True),
        ("**/a/**", "x/a/y", True),
        ("**/a/**", "x/y", False),
        # セグメント内の `*` は戻りながら照合する。
        ("*a*b", "aab", True),
        ("*a*b", "xaxbxb", True),
        ("*a*b", "xaxbx", False),
        ("a*a*a", "aaa", True),
        ("a*a*a", "aa", False),
        ("*ab*ab*", "xxabxabxx", True),
        ("*ab*ab*", "xxabxbaxx", False),
        ("a*?", "a", False),
        ("a*?", "ab", True),
        ("*?*?*", "x", False),
        ("*?*?*", "xy", True),
        ("?*", "", False),
        ("**/*.md", "a.md", True),
        ("**/*.md", ".md", True),  # 隠しファイルの扱いは列挙の規則(4.1 の順 1)。ここは構文だけ
        # `*`・`?` は `/` に当たらない。
        ("a*", "a/b", False),
        ("a?b", "a/b", False),
        ("*/*", "a/b", True),
        ("*/*", "a", False),
        ("*/*", "a/b/c", False),
    ],
)
def test_matching_semantics(pattern: str, path: str, expected: bool) -> None:
    assert matches(pattern, path) is expected


# --- 独立した素朴な実装との突き合わせ ---


def reference_segment_matches(pattern: str, name: str) -> bool:
    """素朴な再帰(指数時間だが、短い入力なら十分)。`*` は 0 文字以上、`?` は 1 文字。"""
    if not pattern:
        return not name
    if pattern[0] == "*":
        return any(
            reference_segment_matches(pattern[1:], name[skip:]) for skip in range(len(name) + 1)
        )
    if not name:
        return False
    return pattern[0] in ("?", name[0]) and reference_segment_matches(pattern[1:], name[1:])


def reference_matches(pattern: list[str], path: list[str]) -> bool:
    if not pattern:
        return not path
    head, rest = pattern[0], pattern[1:]
    if head == "**":
        if not rest:
            return True
        return any(reference_matches(rest, path[skip:]) for skip in range(len(path) + 1))
    return (
        bool(path)
        and reference_segment_matches(head, path[0])
        and reference_matches(rest, path[1:])
    )


def test_matching_agrees_with_a_naive_reference_on_all_small_patterns_and_paths() -> None:
    tokens = ["a", "*", "?", "**", "a*", "*a", "*a*"]
    patterns = [
        "/".join(combo)
        for size in range(1, 4)
        for combo in itertools.product(tokens, repeat=size)
        if violation_of("/".join(combo)) is None
    ]
    names = ["a", "b", "ab", "a\nb"]
    paths = [
        "/".join(combo) for size in range(1, 4) for combo in itertools.product(names, repeat=size)
    ]

    matched = 0
    for pattern in patterns:
        compiled = compile_pattern(pattern)
        for path in paths:
            expected = reference_matches(pattern.split("/"), path.split("/"))
            assert compiled.matches(path) is expected, (pattern, path)
            matched += expected

    assert len(patterns) * len(paths) > 15_000
    assert 1_000 < matched < len(patterns) * len(paths)  # 一致も不一致も十分に含む


# --- 最悪に近い入力でも、短時間で終わる(正規表現のバックトラックの爆発がない) ---

# 実測は最悪に近い入力でも 50 ミリ秒以下。CI の遅い環境でも超えない余裕を見た閾値。
TIME_LIMIT_SECONDS = 0.5


def timed_match(pattern: str, path: str) -> tuple[bool, float]:
    assert violation_of(pattern) is None
    compiled = compile_pattern(pattern)
    started = time.perf_counter()
    result = compiled.matches(path)
    return result, time.perf_counter() - started


@pytest.mark.parametrize("path", ["a" * 60 + "c", "a" * 255])
def test_many_stars_in_one_segment_do_not_blow_up(path: str) -> None:
    pattern = "*a" * 30 + "*b"  # 正規表現では、`*a` が 6 組で約 2 秒、10 組以上で戻らない

    result, elapsed = timed_match(pattern, path)

    assert result is False
    assert elapsed < TIME_LIMIT_SECONDS


def test_many_separated_double_stars_do_not_blow_up() -> None:
    pattern = "/".join(["**", "a"] * 204 + ["b"])  # 1021 バイト
    deep_path = "/".join(["a"] * 200 + ["c"])

    result, elapsed = timed_match(pattern, deep_path)

    assert len(pattern.encode()) <= MAX_BYTES
    assert result is False
    assert elapsed < TIME_LIMIT_SECONDS
    result, elapsed = timed_match(pattern, "/".join(["a"] * 400 + ["b"]))
    assert result is True
    assert elapsed < TIME_LIMIT_SECONDS


def test_the_longest_pattern_against_the_longest_names_stays_fast() -> None:
    star_heavy = "*a" * 511 + "*b"
    pattern = star_heavy[:MAX_BYTES]  # 1024 バイト
    result, elapsed = timed_match(pattern, "a" * 255)
    assert result is False
    assert elapsed < TIME_LIMIT_SECONDS

    segment = "*a" * 60 + "*b"
    deep_matching_names = "/".join(["a" * 130 + "b"] * 200)
    result, elapsed = timed_match("/".join([segment] * 8), deep_matching_names)
    assert result is False
    assert elapsed < TIME_LIMIT_SECONDS

    interleaved = "/".join(["**", segment] * 4)
    result, elapsed = timed_match(interleaved, "/".join(["a" * 130 + "b"] * 100 + ["c"]))
    assert result is False
    assert elapsed < TIME_LIMIT_SECONDS
