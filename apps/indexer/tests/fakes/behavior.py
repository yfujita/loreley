"""インメモリ fake に共通の、割り込みフックと応答の差し替え(arch 16.1)。"""

import copy
import threading
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class Intercepted:
    """差し替えた応答。None 自体が正常な戻り値(文書なし)のため、箱に入れて区別する。"""

    value: Any


@dataclass
class _Hook:
    callback: Callable[[], None]
    key: str | None  # None は全キーが対象


@dataclass
class _Injection:
    outcome: Any
    remaining: int | None  # None は無制限
    key: str | None  # None は全キーが対象

    def applies_to(self, key: str | None) -> bool:
        return self.key is None or self.key == key


@dataclass(frozen=True)
class Call:
    operation: str
    key: str | None


class FakeBehavior:
    """操作の直前に呼ばれるフックと、操作の代わりに返す応答を管理する。

    複数スレッドから `enter` を呼んでも、フックと差し替えを二重に消費しない。
    フックは内部のロックの外で呼ぶ(フックの中でブロックしても、他スレッドを止めないため)。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._calls: list[Call] = []
        self._hooks: dict[str, list[_Hook]] = defaultdict(list)
        self._injections: dict[str, list[_Injection]] = defaultdict(list)

    @property
    def calls(self) -> list[Call]:
        with self._lock:
            return list(self._calls)

    def before(
        self, operation: str, callback: Callable[[], None], *, key: str | None = None
    ) -> None:
        """次の `operation` の直前に 1 回だけ `callback` を呼ぶ。

        読み(GET)と書き込みの間に、別の書き込みを差し込む(C-18〜C-20、D-87)のに使う。
        `callback` の中から同じ操作を呼んでもフックは再入しない(呼ぶ前に取り除くため)。
        `key`(文書 ID など)を指定すると、そのキーの呼び出しだけが対象になる。
        別のキーの呼び出しでは消費されず、一致するまで残る。
        1 回の呼び出しで消費するフックは 1 つで、複数登録したフックは登録順に使う。
        """
        with self._lock:
            self._hooks[operation].append(_Hook(callback, key))

    def inject(
        self, operation: str, outcome: Any, *, key: str | None = None, times: int | None = 1
    ) -> None:
        """次の `times` 回(None なら以後ずっと)の `operation` を、`outcome` を返す呼び出しにする。

        `outcome` が例外なら送出する。差し替えた呼び出しは、状態を変えない。
        例外は呼び出しごとに複製して送出する(同じインスタンスだと traceback が累積するため)。
        `times` は 1 以上か None(不正な値は ValueError)。
        `key` を指定すると、そのキーの呼び出しだけが対象になる(`before` と同じ)。
        """
        if times is not None and times < 1:
            raise ValueError(f"times must be None or >= 1: {times}")
        with self._lock:
            self._injections[operation].append(_Injection(outcome, times, key))

    def enter(self, operation: str, key: str | None = None) -> Intercepted | None:
        """各操作の先頭で呼ぶ。差し替えがあれば応答を返すので、操作はそのまま返すこと。

        フック、差し替えの順に処理する(フックが差し込んだ状態を、差し替えの前に反映するため)。
        """
        with self._lock:
            self._calls.append(Call(operation, key))
            hook = self._take_hook(operation, key)
        if hook is not None:
            hook.callback()
        with self._lock:
            injection = self._take_injection(operation, key)
        if injection is None:
            return None
        if isinstance(injection.outcome, BaseException):
            raise copy.copy(injection.outcome)
        return Intercepted(copy.deepcopy(injection.outcome))

    def calls_of(self, *operations: str) -> list[Call]:
        return [call for call in self.calls if call.operation in operations]

    def _take_hook(self, operation: str, key: str | None) -> _Hook | None:
        hooks = self._hooks[operation]
        for index, hook in enumerate(hooks):
            if hook.key is None or hook.key == key:
                return hooks.pop(index)
        return None

    def _take_injection(self, operation: str, key: str | None) -> _Injection | None:
        injections = self._injections[operation]
        for index, injection in enumerate(injections):
            if not injection.applies_to(key):
                continue
            if injection.remaining is not None:
                injection.remaining -= 1
                if injection.remaining <= 0:
                    injections.pop(index)
            return injection
        return None
