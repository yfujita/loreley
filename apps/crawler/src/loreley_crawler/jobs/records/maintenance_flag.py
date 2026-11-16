"""メンテナンスフラグの読み取り(architecture 7.9。CA-P-34)。

形式は Indexer の仮定義: `loreley-jobs` の ID `maintenance`、項目 `enabled`(真偽値)。書き込みは
運用者の手動手順で、Crawler は読むだけ(CA-U-3)。

**fail-closed**(確定。CA-K-18): 文書がなければ「立っていない」。文書があって `enabled` が真偽値の
`false` と明示されているときだけ「立っていない」で、それ以外(真偽値でない値・項目の欠落)は
「立っている」とみなす。形式の食い違いが、Indexer の書き込みを止めたまま Crawler だけ進む状態を
作らないため、Indexer と同じ規則で読む。
"""

from loreley_crawler.infrastructure.opensearch import Repository

MAINTENANCE_RECORD_ID = "maintenance"


def is_maintenance_enabled(repository: Repository) -> bool:
    record = repository.fetch(MAINTENANCE_RECORD_ID)
    if record is None:
        return False
    return record.source.get("enabled") is not False
