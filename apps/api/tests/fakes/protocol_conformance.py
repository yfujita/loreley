"""偽物が本物の Protocol と同じ形であることを確かめる、共通の補助(D 7.2)。

型検査を使わないので、Protocol に足したメソッドを偽物に足し忘れると、偽物を使うテストが
`AttributeError` になる。`test_*_protocol*.py` がこの補助で、足し忘れと引数・同期/非同期の食い違いを
1 か所で知らせる。

Python 3.12 前提: `inspect._ParameterKind`・`_is_protocol` は非公開の属性に依存する。Python を
上げるときは、公開された `typing.is_protocol` などへ置き換える(`typing.is_protocol` は 3.13 以降)。
"""

import inspect
from types import ModuleType
from typing import Any


def public_methods(protocol: type) -> dict[str, Any]:
    return {
        name: method
        for name, method in inspect.getmembers(protocol, inspect.isfunction)
        if not name.startswith("_")
    }


def parameters_of(method: Any) -> list[tuple[str, inspect._ParameterKind, Any]]:
    """名前・種別(位置/キーワード専用など)・デフォルト値。`self` は除く。"""
    return [
        (parameter.name, parameter.kind, parameter.default)
        for parameter in inspect.signature(method).parameters.values()
        if parameter.name != "self"
    ]


def protocols_defined_in(module: ModuleType) -> dict[str, type]:
    """`module` 自身が定義した Protocol(クラス名 → クラス)。import しただけのものは含めない。"""
    return {
        name: member
        for name, member in vars(module).items()
        if inspect.isclass(member)
        and getattr(member, "_is_protocol", False)
        and member.__module__ == module.__name__
    }


def assert_same_methods_as_protocol(candidate: object, protocol: type, *, label: str) -> None:
    """`candidate` が、`protocol` のすべての公開メソッドを、同じ引数・同じ同期/非同期で持つ。"""
    for name, protocol_method in public_methods(protocol).items():
        method_label = f"{label}.{name}"
        assert hasattr(candidate, name), f"{method_label} is missing"
        method = getattr(candidate, name)
        # 同期/非同期の食い違いは、`await` や `runner.run` の使い方を静かに変える。
        assert inspect.iscoroutinefunction(method) == inspect.iscoroutinefunction(
            protocol_method
        ), method_label
        # 名前に加えて、キーワード専用かどうか・デフォルト値も同じであること。
        assert parameters_of(method) == parameters_of(protocol_method), method_label
