"""OpenAPI 文書の構造検査(`openapi-spec-validator` を dev 依存に足さず、必要な範囲だけ確かめる)。

型生成の入力として壊れていないこと(参照先がある・必須のキーがある・パスの引数が宣言されている)を
確かめる。OpenAPI 3.1 の完全な検証ではない。
"""

import re
from collections.abc import Iterator
from typing import Any

HTTP_METHODS = frozenset({"get", "put", "post", "delete", "options", "head", "patch", "trace"})
SCHEMA_REF_PREFIX = "#/components/schemas/"
_PATH_TEMPLATE_NAME = re.compile(r"{([^{}]+)}")


def iter_refs(node: Any) -> Iterator[str]:
    """文書の中のすべての `$ref` の値。"""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref":
                yield value
            else:
                yield from iter_refs(value)
    elif isinstance(node, list):
        for item in node:
            yield from iter_refs(item)


def iter_operations(schema: dict[str, Any]) -> Iterator[tuple[str, str, dict[str, Any]]]:
    """`(HTTP メソッド(小文字), パス, operation)`。"""
    for path, path_item in schema["paths"].items():
        for method, operation in path_item.items():
            if method in HTTP_METHODS:
                yield method, path, operation


def structure_problems(schema: dict[str, Any]) -> list[str]:
    """構造の問題の一覧(空なら問題なし)。"""
    problems: list[str] = []
    if not str(schema.get("openapi", "")).startswith("3."):
        problems.append("openapi must be a 3.x version")
    for key in ("title", "version"):
        if not isinstance(schema.get("info", {}).get(key), str):
            problems.append(f"info.{key} must be a string")
    if not schema.get("paths"):
        problems.append("paths must not be empty")

    component_schemas = schema.get("components", {}).get("schemas", {})
    for ref in iter_refs(schema):
        name = ref.removeprefix(SCHEMA_REF_PREFIX)
        if not ref.startswith(SCHEMA_REF_PREFIX) or name not in component_schemas:
            problems.append(f"unresolved $ref: {ref}")

    operation_ids: list[str] = []
    for method, path, operation in iter_operations(schema):
        where = f"{method.upper()} {path}"
        if not path.startswith("/"):
            problems.append(f"{where}: the path must start with /")
        operation_id = operation.get("operationId")
        if not isinstance(operation_id, str) or not operation_id:
            problems.append(f"{where}: operationId is required")
        else:
            operation_ids.append(operation_id)
        responses = operation.get("responses")
        if not responses:
            problems.append(f"{where}: responses must not be empty")
        for status, response in (responses or {}).items():
            if not isinstance(response.get("description"), str):
                problems.append(f"{where}: response {status} needs a description")
        declared = {
            parameter["name"]
            for parameter in operation.get("parameters", [])
            if parameter["in"] == "path" and parameter.get("required") is True
        }
        if declared != set(_PATH_TEMPLATE_NAME.findall(path)):
            problems.append(f"{where}: the path parameters are not declared as required")
        if "requestBody" in operation and "content" not in operation["requestBody"]:
            problems.append(f"{where}: requestBody needs content")
    if len(operation_ids) != len(set(operation_ids)):
        problems.append("operationId is not unique")
    return problems
