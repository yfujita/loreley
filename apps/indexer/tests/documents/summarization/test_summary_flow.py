"""登録から要約の書き戻しまでの流れ(M-9)。登録の処理と要約ワーカーを、実際に組み合わせて確認する。"""

import pytest

from loreley_indexer.documents import DocumentRegistrar
from loreley_indexer.documents.summarization import (
    SummaryOutcome,
    SummaryProcessor,
    SummaryRequestQueue,
)
from tests.documents.factories import id_of, make_context, make_document, stored_document
from tests.fakes.in_memory_search_index import InMemorySearchIndex
from tests.fakes.llm import FakeLlmClient

pytestmark = pytest.mark.usefixtures("running_crawl")


def test_registered_document_gets_its_summary_after_the_registration_returned(
    summary_registrar: DocumentRegistrar,
    make_processor,
    summary_requests: SummaryRequestQueue,
    search_index: InMemorySearchIndex,
    llm: FakeLlmClient,
) -> None:
    """登録の応答は要約より先に返り(`pending`)、依頼を処理すると `generated` になる。"""
    document = make_document()
    summary_registrar.register(make_context(), [document])
    assert stored_document(search_index, document)["summary_status"] == "pending"
    assert llm.prompts == []
    processor: SummaryProcessor = make_processor()

    document_id = summary_requests.take()
    assert document_id == id_of(document)
    outcome = processor.process(document_id)

    assert outcome is SummaryOutcome.WRITTEN
    stored = stored_document(search_index, document)
    assert stored["summary_status"] == "generated"
    assert stored["content"] == "hello\nworld\n"


def test_body_updated_during_generation_gets_a_new_summary_for_the_new_body(
    summary_registrar: DocumentRegistrar,
    make_processor,
    summary_requests: SummaryRequestQueue,
    search_index: InMemorySearchIndex,
    llm: FakeLlmClient,
) -> None:
    """C-1: 生成中に原本が更新されると、旧本文向けの要約は破棄され、新しい本文向けに生成される。"""
    summary_registrar.register(make_context(), [make_document(text="old body")])
    llm.on_generate = lambda _prompt: summary_registrar.register(
        make_context(), [make_document(text="new body")]
    )
    processor: SummaryProcessor = make_processor()

    first = processor.process(summary_requests.take())
    llm.on_generate = None
    second = processor.process(summary_requests.take())

    assert first is SummaryOutcome.DISCARDED
    assert second is SummaryOutcome.WRITTEN
    assert "new body" in llm.prompts[1]
    stored = stored_document(search_index, "docs/a.txt")
    assert stored["content"] == "new body"
    assert stored["summary_status"] == "generated"
