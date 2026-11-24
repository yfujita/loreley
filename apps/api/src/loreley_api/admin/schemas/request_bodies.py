"""リクエスト本文の OpenAPI 上の宣言(A 5.4)。

本文は、型の検証と一緒に FastAPI へ任せず、依存関係(`routers/request_input.py` の
`read_body_as`)で読む(1 MiB の上限・本文なしの扱い・A 5.2 の形のエラーのため)。FastAPI は
依存関係の中の本文を OpenAPI に出さないので、`requestBody` を操作に宣言し、本文のスキーマを
コンポーネントに足す(`app.py` が `REQUEST_BODY_MODELS` を足す)。
"""

from typing import Any

from pydantic import BaseModel

from loreley_api.admin.schemas.sources import RegisterSourceBody, StartCrawlBody, UpdateSourceBody

# `json_request_body` で宣言するモデルの全部。追加したら、ここに足す(足し忘れは、
# `$ref` の参照先がない OpenAPI になり、テストが失敗する)。
REQUEST_BODY_MODELS: tuple[type[BaseModel], ...] = (
    RegisterSourceBody,
    UpdateSourceBody,
    StartCrawlBody,
)


def json_request_body(model: type[BaseModel], *, required: bool) -> dict[str, Any]:
    """`openapi_extra=` に渡す、JSON の本文の宣言。`required=False` は、本文を省略できる EP。"""
    return {
        "requestBody": {
            "required": required,
            "content": {
                "application/json": {"schema": {"$ref": f"#/components/schemas/{model.__name__}"}}
            },
        }
    }
