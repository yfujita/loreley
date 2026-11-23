"""Crawler の `config_invalid` の `message` の分解(B 2.5。C 4.5。D 4.9)。

`message` は「項目名(配列は添字): 違反の種類」の固定文(最初の違反 1 件)で、Crawler は項目別の
構造を返さない。Connector の検証規則は複製せず、この形式だけに依存する。形式が変わっても、分解不能
(`violation=None`)に落ちるだけで、操作は止まらない(画面は上部のアラートにする)。この依存は、この
ファイルに閉じる。
"""

import re

from loreley_api.infrastructure.crawler_client.client import ConfigInvalidMessage, ConfigViolation

# Crawler は説明文を 512 文字で切り詰める(crawler-api 3.3)。これ以上は切り詰めの疑いがある。
MESSAGE_MAX_CHARS = 512
_FIELD_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(\[[0-9]+\])?")
_CONNECTOR_CONFIG = "connector_config"
_SEPARATOR = ": "


def decompose(message: object) -> ConfigViolation | None:
    """分解できなければ `None`。前半の判定は `fullmatch`(`match` と `$` は末尾の改行を許す)。"""
    if not isinstance(message, str) or len(message) >= MESSAGE_MAX_CHARS:
        return None
    head, separator, detail = message.partition(_SEPARATOR)
    if not separator or not detail or _FIELD_NAME.fullmatch(head) is None:
        return None
    # `file_system` Connector は、特定の項目に結びつかない違反を `connector_config` 自身の名前で
    # 返す。そのときだけプレフィックスを付けない(`connector_config.connector_config` にしない)。
    field = head if head == _CONNECTOR_CONFIG else f"{_CONNECTOR_CONFIG}.{head}"
    return ConfigViolation(field=field, detail=detail)


def describe(message: str) -> ConfigInvalidMessage:
    """`message` を分解し、`crawler_message` には 512 文字以内にした元の文字列を載せる。"""
    return ConfigInvalidMessage(
        crawler_message=message[:MESSAGE_MAX_CHARS], violation=decompose(message)
    )
