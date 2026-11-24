"""Admin API のサブアプリ(`/api/admin/v1`。D 4.2・4.12(c))。

`install_common_http` は呼ばない(外側の `create_app` がマウント時に設置する。二重になるため)。
対話型ドキュメントは常に無効、末尾スラッシュはリダイレクトしない(A 5.1・5.4)。
サブアプリを素の `FastAPI(...)` で作ると `/openapi.json` が既定で公開されるので、`openapi_url` も
明示する(`tests/architecture/test_http_rules.py` が強制する)。OpenAPI JSON を公開するのは
`openapi_enabled` のときだけ(`OPENAPI_ENABLED`。既定は無効)。公開しなくても、`app.openapi()` で
書き出せる(`openapi_export.py`)。

OpenAPI は、FastAPI が作ったものを `_adjust_openapi` で直す(型生成の入力にするため)。
"""

from collections.abc import Sequence
from typing import Any, NamedTuple

from fastapi import FastAPI
from fastapi.routing import APIRoute
from pydantic.json_schema import models_json_schema

from loreley_api.admin.base.codes import DocumentTab, JobStatus
from loreley_api.admin.base.constants import ITEMS_PER_PAGE_CHOICES
from loreley_api.admin.dependencies import AdminDependencies
from loreley_api.admin.routers import create_admin_router
from loreley_api.admin.routers.jobs import ACTIVE_FILTER
from loreley_api.admin.schemas.request_bodies import REQUEST_BODY_MODELS

# 外側のアプリがサブアプリをマウントする位置。OpenAPI の `servers` にも書く。
ADMIN_API_PREFIX = "/api/admin/v1"
# サブアプリの中のパス。公開するときは `ADMIN_API_PREFIX` の下の `/api/admin/v1/openapi.json`。
OPENAPI_PATH = "/openapi.json"

# 型生成の入力になる OpenAPI の `info`。`version` は API の版(URL の `v1`)で、変更で揺れない。
OPENAPI_TITLE = "Loreley Admin API"
OPENAPI_VERSION = "v1"

# FastAPI が、検証のある操作に既定で足す 422 の応答と、そのスキーマ。
_VALIDATION_ERROR_SCHEMAS = ("HTTPValidationError", "ValidationError")


class _QueryParameterRule(NamedTuple):
    """OpenAPI のクエリパラメータに反映する、必須性と取りうる値(列挙)。"""

    operation_id: str
    parameter_name: str
    choices: Sequence[str | int]
    # 実行時の検証が「欠落は 400 `required`」にしているものだけ True。
    required: bool = False


# 実行時の検証は、違反をまとめて返すために `str`・`int` で受けて自分で調べる(`read_document_query`・
# `read_job_list_filters`・`resolve_paging`)ので、FastAPI が作る OpenAPI は任意の文字列・整数に
# なる。
# 型生成(Hey API)が受け付けられないリクエストを許さないよう、ここで必須性と列挙を足す。
# 値は実装の定数から導く(手書きで複製すると、片方だけ変わって食い違う)。`sort` は、タブごとに
# 許容する項目が違うので列挙にしない。
_QUERY_PARAMETER_RULES = (
    _QueryParameterRule(
        "list_jobs", "status", [ACTIVE_FILTER, *(status.value for status in JobStatus)]
    ),
    _QueryParameterRule("list_jobs", "items_per_page", ITEMS_PER_PAGE_CHOICES),
    _QueryParameterRule("list_documents", "tab", [tab.value for tab in DocumentTab], required=True),
    _QueryParameterRule("list_documents", "items_per_page", ITEMS_PER_PAGE_CHOICES),
)


def _operation_id_of(route: APIRoute) -> str:
    """`operationId` はルート関数の名前にする(FastAPI の既定は、パスと HTTP メソッドを含み長い)。

    生成物の名前が、パスの変更で揺れないようにするため(A 5.4)。関数名は全体で一意。
    """
    return route.name


def _apply_query_parameter_rule(schema: dict[str, Any], rule: _QueryParameterRule) -> None:
    """対象のクエリパラメータの `required` と、`schema` の型・列挙を直す。

    `anyOf[string, null]`(既定が `None` の引数)は、列挙の文字列に置き換える。省略できるかどうかは
    `required` が表すので、`null` は要らない。`default` と `title` は残す。
    """
    for path_item in schema["paths"].values():
        for operation in path_item.values():
            if operation["operationId"] != rule.operation_id:
                continue
            for parameter in operation["parameters"]:
                if parameter["in"] == "query" and parameter["name"] == rule.parameter_name:
                    parameter["required"] = rule.required
                    parameter_schema = parameter["schema"]
                    parameter_schema.pop("anyOf", None)
                    parameter_schema["type"] = (
                        "integer" if isinstance(rule.choices[0], int) else "string"
                    )
                    parameter_schema["enum"] = list(rule.choices)
                    return
    # 黙って飛ばすと、操作やパラメータの名前を変えたときに、反映が外れたことに気づけない。
    raise ValueError(
        f"OpenAPI query parameter not found: {rule.operation_id} {rule.parameter_name}"
    )


def _adjust_openapi(schema: dict[str, Any]) -> None:
    """FastAPI の OpenAPI を、実際の応答と合わせる(A 5.4。D 4.12(c))。

    - 422 の宣言と、そのスキーマを取り除く。基盤が検証エラーを 400 `invalid_request` に変えるため。
    - 本文を依存関係で読む操作(`openapi_extra` で `requestBody` を宣言した)が参照する、
      本文のスキーマを `components` に足す。FastAPI は、依存関係の中の本文を出さない。
    - 実行時に検証しているクエリパラメータの必須性と列挙を足す(`_QUERY_PARAMETER_RULES`)。
    """
    for path_item in schema["paths"].values():
        for operation in path_item.values():
            operation["responses"].pop("422", None)

    for rule in _QUERY_PARAMETER_RULES:
        _apply_query_parameter_rule(schema, rule)

    component_schemas: dict[str, Any] = schema["components"]["schemas"]
    for name in _VALIDATION_ERROR_SCHEMAS:
        component_schemas.pop(name, None)

    _, definitions = models_json_schema(
        [(model, "validation") for model in REQUEST_BODY_MODELS],
        ref_template="#/components/schemas/{model}",
    )
    for name, definition in definitions["$defs"].items():
        if component_schemas.get(name, definition) != definition:
            # 応答用と本文用で、同じ名前の別のスキーマ。黙って上書きすると片方が壊れる。
            raise ValueError(f"conflicting OpenAPI component schema: {name}")
        component_schemas[name] = definition


def _install_openapi_adjustment(app: FastAPI) -> None:
    """`app.openapi()` を、FastAPI の生成の後に `_adjust_openapi` を適用するものにする。

    `/openapi.json` の応答も `app.openapi()` を呼ぶので、公開と書き出しは同じ内容になる。

    調整の要否は「FastAPI が返した dict が、調整済みとして記録した dict か」で決める。
    `app.openapi_schema` が None かどうかでは決めない。FastAPI は調整の前にキャッシュするので、
    調整が失敗した後の呼び出しが、未調整のスキーマを黙って返してしまう。また、ルートが変わって
    FastAPI がスキーマを作り直したときに、調整が走らず 422 が復活してしまう。調整は冪等なので、
    失敗後の再試行は安全で、失敗が続く限り、呼び出しのたびに同じ失敗が伝わる。
    """
    generate_openapi = app.openapi
    adjusted_schema: dict[str, Any] | None = None

    def openapi() -> dict[str, Any]:
        nonlocal adjusted_schema
        schema = generate_openapi()
        if schema is not adjusted_schema:
            _adjust_openapi(schema)
            adjusted_schema = schema
        return schema

    app.openapi = openapi  # type: ignore[method-assign]


def create_admin_app(deps: AdminDependencies, *, openapi_enabled: bool = False) -> FastAPI:
    """`deps` のサービスを、ルーターに個別に渡して組み立てる。"""
    app = FastAPI(
        title=OPENAPI_TITLE,
        version=OPENAPI_VERSION,
        docs_url=None,
        redoc_url=None,
        openapi_url=OPENAPI_PATH if openapi_enabled else None,
        redirect_slashes=False,
        generate_unique_id_function=_operation_id_of,
        # パスはマウント位置からの相対(`/sources`)なので、`servers` に位置を書く。FastAPI は
        # 公開時だけ `root_path` を足し、書き出しには足さない(両者が食い違う)ので、固定する。
        servers=[{"url": ADMIN_API_PREFIX}],
        root_path_in_servers=False,
    )
    app.include_router(
        create_admin_router(
            source_catalog=deps.source_catalog,
            source_commands=deps.source_commands,
            crawl_commands=deps.crawl_commands,
            document_review=deps.document_review,
            job_queries=deps.job_queries,
            cluster_overview=deps.cluster_overview,
            dashboard=deps.dashboard,
            meta=deps.meta,
        )
    )
    _install_openapi_adjustment(app)
    return app
