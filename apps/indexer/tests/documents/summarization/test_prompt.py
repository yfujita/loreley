from loreley_indexer.documents.summarization.prompt import build_summary_prompt


def test_prompt_contains_the_title_and_the_body() -> None:
    prompt = build_summary_prompt(title="Setup guide", content="step one", max_content_chars=100)

    assert "Setup guide" in prompt
    assert "step one" in prompt


def test_prompt_asks_for_subject_concepts_and_answerable_questions() -> None:
    prompt = build_summary_prompt(title="t", content="c", max_content_chars=100)

    for required in ("主題", "重要な概念", "答えられる質問"):
        assert required in prompt


def test_body_over_the_limit_is_cut_from_the_end() -> None:
    prompt = build_summary_prompt(title="t", content="0123456789", max_content_chars=4)

    assert "0123" in prompt
    assert "4567" not in prompt


def test_body_at_the_limit_is_kept_whole() -> None:
    assert "0123" in build_summary_prompt(title="t", content="0123", max_content_chars=4)


def test_missing_title_is_marked() -> None:
    assert "タイトルなし" in build_summary_prompt(title=None, content="c", max_content_chars=10)
