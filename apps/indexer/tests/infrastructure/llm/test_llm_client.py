import pytest

from loreley_indexer.infrastructure.llm import (
    DisabledLlmClient,
    LlmCompletion,
    LlmDisabledError,
    LlmFailure,
    LlmFailureKind,
)
from tests.fakes.llm import DEFAULT_MODEL, FakeLlmClient


def test_disabled_client_refuses_to_call_out() -> None:
    with pytest.raises(LlmDisabledError):
        DisabledLlmClient().generate("prompt")


def test_fake_returns_a_completion_by_default_and_records_prompts() -> None:
    llm = FakeLlmClient()
    assert llm.generate("p1") == LlmCompletion(text="summary #1", model=DEFAULT_MODEL)
    assert llm.prompts == ["p1"]


def test_fake_returns_queued_results_in_order_including_failures_and_errors() -> None:
    llm = FakeLlmClient()
    llm.queue_result(LlmFailure(LlmFailureKind.TIMEOUT))
    llm.queue_result(RuntimeError("boom"))

    assert llm.generate("p") == LlmFailure(LlmFailureKind.TIMEOUT)
    with pytest.raises(RuntimeError):
        llm.generate("p")
    assert isinstance(llm.generate("p"), LlmCompletion)


def test_on_generate_runs_before_the_result_is_returned() -> None:
    order: list[str] = []
    llm = FakeLlmClient(on_generate=lambda prompt: order.append(f"hook:{prompt}"))

    result = llm.generate("p")
    order.append("returned")

    assert order == ["hook:p", "returned"]
    assert isinstance(result, LlmCompletion)
