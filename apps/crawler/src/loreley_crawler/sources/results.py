"""`SourceStore` の操作の結果区分(crawler-api 4.4。architecture 8.1・8.3)。

`api` が、HTTP のステータスとエラーコードに対応づける(`sources` は HTTP を知らない)。
Store 層の全体の異常は、結果ではなく `StoreUnavailableError` で伝播する。
"""

from dataclasses import dataclass

from loreley_crawler.sources.records import SourceRecord, SourceStatus


@dataclass(frozen=True)
class Registered:
    """新しく保存した(201)。"""

    record: SourceRecord


@dataclass(frozen=True)
class AlreadyRegistered:
    """同じ内容がすでに登録されていた(200)。応答が失われた再送を成功にするため。"""

    record: SourceRecord


@dataclass(frozen=True)
class RegistrationConflict:
    """同じ `source_id` があり、内容が異なる、または `status=deleting`(409)。

    `existing_status` は既存の設定の `status`(`details.status`)。読めないときは None。
    """

    existing_status: SourceStatus | None


@dataclass(frozen=True)
class Updated:
    record: SourceRecord


@dataclass(frozen=True)
class Unchanged:
    """内容が現在の設定と同じなので、書き込まなかった(`updated_at` も変えない)。"""

    record: SourceRecord


@dataclass(frozen=True)
class SourceNotFound:
    """設定がない(更新なら 404 `source_config_not_found`)。"""


@dataclass(frozen=True)
class SourceIsDeleting:
    """設定の `status=deleting`(更新は 409 `source_deleting`)。"""


@dataclass(frozen=True)
class MarkedDeleting:
    """`status=deleting` にした、またはすでに `deleting` だった(ソース削除の順 0。再実行で冪等)。"""


@dataclass(frozen=True)
class SourceDeleted:
    """設定を削除した、またはすでになかった(ソース削除の順 5。再実行で冪等)。"""


@dataclass(frozen=True)
class SourceNotDeleting:
    """設定が `status=deleting` でないので、削除しなかった。

    設定の削除は、順 0 で `deleting` にしたソース削除ジョブだけが行う(architecture 3.2)。
    起きたら呼び出し側の誤り(`failed(internal_error)`)。
    """


RegisterResult = Registered | AlreadyRegistered | RegistrationConflict
UpdateResult = Updated | Unchanged | SourceNotFound | SourceIsDeleting
MarkDeletingResult = MarkedDeleting | SourceNotFound
DeleteSourceResult = SourceDeleted | SourceNotDeleting
