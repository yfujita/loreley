from collections import deque
from collections.abc import Callable

from loreley_indexer.infrastructure.llm import LlmClient, LlmCompletion, LlmResult

DEFAULT_MODEL = "fake-model-1"


class FakeLlmClient(LlmClient):
    """決定的な LLM の代役。

    - `queue_result()` で、次の呼び出しの結果を指定できる(LlmFailure や例外も可)。
    - `on_generate` は結果を返す前に呼ばれる。生成中に本文の更新や遷移を差し込んでから
      生成を完了させる(C-1、C-15、C-24(b)、E-45b)ために使う。別スレッドで止めたいときは
      `Gate().pass_through` を渡す。
    """

    def __init__(self, on_generate: Callable[[str], None] | None = None) -> None:
        self.prompts: list[str] = []
        self.on_generate = on_generate
        self._queued: deque[LlmResult | BaseException] = deque()

    def queue_result(self, result: LlmResult | BaseException) -> None:
        self._queued.append(result)

    def generate(self, prompt: str) -> LlmResult:
        self.prompts.append(prompt)
        if self.on_generate is not None:
            self.on_generate(prompt)
        if not self._queued:
            return LlmCompletion(text=f"summary #{len(self.prompts)}", model=DEFAULT_MODEL)
        queued = self._queued.popleft()
        if isinstance(queued, BaseException):
            raise queued
        return queued
