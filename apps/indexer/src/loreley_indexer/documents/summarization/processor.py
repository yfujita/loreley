"""1 件の生成依頼の処理: 読み出し → 生成 → 書き戻し(arch 7.4、5章)。

- 生成元は、生成を始めた時点の文書の `content_hash`・`text_hash`(と本文)。この処理が保持する。
- 書き戻しは、文書が `pending` で、両ハッシュが生成元と一致するときだけ行う。
  不一致・文書なしは破棄する。409 は読み直して再判定し、上限を超えたら `pending` のまま残す(R8)。
- メンテナンス中は、LLM を呼ぶ前にも確認して生成しない(生成して捨てることを繰り返さないため)。
  書き込みの直前にも確認する(生成の最中にメンテナンスが始まりうるため)。
- LLM の失敗は例外にせず `pending` のまま残す。登録には影響しない(隔離)。
- 本文・プロンプト・要約をログや例外に出さない(R9)。
"""

import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from loreley_indexer.documents.summarization.config import SummarizationConfig
from loreley_indexer.documents.summarization.prompt import build_summary_prompt
from loreley_indexer.documents.summarization.status import SummaryOutcome, SummaryStatus
from loreley_indexer.infrastructure.llm import LlmClient, LlmCompletion, LlmFailure
from loreley_indexer.infrastructure.opensearch import (
    Conflict,
    JobsReader,
    NotFound,
    Rejected,
    SearchIndexRepository,
    Written,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Origin:
    """要約の生成元。文書には持たず、この処理が自分のコンテキストとして保持する。"""

    content_hash: str
    text_hash: str
    title: str | None
    content: str

    def matches(self, source: Mapping[str, Any]) -> bool:
        return (
            source.get("summary_status") == SummaryStatus.PENDING
            and source.get("content_hash") == self.content_hash
            and source.get("text_hash") == self.text_hash
        )


class SummaryProcessor:
    def __init__(
        self,
        *,
        config: SummarizationConfig,
        search_index: SearchIndexRepository,
        jobs: JobsReader,
        llm: LlmClient,
        sleep: Callable[[float], object] = time.sleep,
        should_stop: Callable[[], bool] = lambda: False,
    ) -> None:
        self._config = config
        self._search_index = search_index
        self._jobs = jobs
        self._llm = llm
        self._sleep = sleep
        self._should_stop = should_stop

    def process(self, document_id: str) -> SummaryOutcome:
        """OpenSearch の全体異常は伝播する(呼び出し側が `pending` のまま再走査に委ねる)。"""
        if not self._config.enabled:
            return SummaryOutcome.DISABLED
        origin = self._read_origin(document_id)
        if origin is None:
            return SummaryOutcome.DISCARDED
        if self._jobs.is_maintenance_enabled():
            return SummaryOutcome.PAUSED_BY_MAINTENANCE
        completion = self._with_attempts(lambda: self._generate(document_id, origin))
        if completion is None:
            return SummaryOutcome.LEFT_PENDING
        written = self._with_attempts(lambda: self._write_back(document_id, origin, completion))
        return written if written is not None else SummaryOutcome.LEFT_PENDING

    def _read_origin(self, document_id: str) -> _Origin | None:
        stored = self._search_index.fetch(document_id)
        if stored is None or stored.source.get("summary_status") != SummaryStatus.PENDING:
            return None
        source = stored.source
        content_hash = source.get("content_hash")
        text_hash = source.get("text_hash")
        content = source.get("content")
        required = (content_hash, text_hash, content)
        if not all(isinstance(value, str) for value in required):
            return None
        return _Origin(
            content_hash=content_hash,
            text_hash=text_hash,
            title=source.get("title"),
            content=content,
        )

    def _generate(self, document_id: str, origin: _Origin) -> LlmCompletion | None:
        prompt = build_summary_prompt(
            title=origin.title,
            content=origin.content,
            max_content_chars=self._config.input_max_chars,
        )
        result = self._llm.generate(prompt)
        if isinstance(result, LlmFailure):
            logger.warning(
                "summary generation failed: document_id=%s kind=%s", document_id, result.kind
            )
            return None
        if not result.text.strip():
            logger.warning("summary generation returned no text: document_id=%s", document_id)
            return None
        return result

    def _write_back(
        self, document_id: str, origin: _Origin, completion: LlmCompletion
    ) -> SummaryOutcome | None:
        """1 回の書き戻し。None は「直らなかった」(呼び出し側が試行回数の上限まで繰り返す)。"""
        for _ in range(self._config.write_conflict_max_rereads + 1):
            # 要約の書き込みはロック所有確認ではなく、メンテナンスフラグで守る(arch 8章、L-9)。
            if self._jobs.is_maintenance_enabled():
                return SummaryOutcome.PAUSED_BY_MAINTENANCE
            current = self._search_index.fetch(document_id)
            if current is None or not origin.matches(current.source):
                return SummaryOutcome.DISCARDED
            written = self._search_index.replace_if_unchanged(
                document_id,
                {
                    **current.source,
                    "summary": completion.text,
                    "summary_status": SummaryStatus.GENERATED,
                    "summary_model": completion.model,
                },
                seq_no=current.seq_no,
                primary_term=current.primary_term,
            )
            match written:
                case Written():
                    return SummaryOutcome.WRITTEN
                case Rejected(error_type=error_type):
                    # 文書固有の拒否は繰り返しても直らない。
                    logger.warning(
                        "summary write rejected: document_id=%s error_type=%s",
                        document_id,
                        error_type,
                    )
                    return SummaryOutcome.LEFT_PENDING
                case Conflict() | NotFound():
                    continue  # 読み直す。文書が消えていれば次の fetch で破棄になる。
        return None

    def _with_attempts[T](self, attempt: Callable[[], T | None]) -> T | None:
        """`attempt` が None を返す間、バックオフを挟んで `max_attempts` 回まで繰り返す。

        停止が要請されたら、残りの試行を行わずに None を返す(最初の試行は、停止の要請より前に
        始まった処理を終えるために行う)。
        """
        for attempt_number in range(1, self._config.max_attempts + 1):
            if attempt_number > 1:
                self._sleep(self._backoff_seconds(attempt_number - 1))
                if self._should_stop():
                    return None
            result = attempt()
            if result is not None:
                return result
        return None

    def _backoff_seconds(self, failed_attempts: int) -> float:
        delay = self._config.retry_backoff_initial_seconds * (
            self._config.retry_backoff_factor ** (failed_attempts - 1)
        )
        return min(delay, self._config.retry_backoff_max_seconds)
