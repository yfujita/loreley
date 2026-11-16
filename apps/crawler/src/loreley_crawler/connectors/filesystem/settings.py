"""FS Connector の数値(仮値。設定可能。FS 設計書 CFS-P-21・CFS-U-6)。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FileSystemSettings:
    """`FileSystemConnectorType` の生成時に渡す。既定値は FS 設計書の仮値。

    - `max_patterns`・`max_pattern_bytes`: `include_patterns`・`exclude_patterns` の 1 配列の件数と
      1 パターンの UTF-8 のバイト数の上限(2.2)
    - `read_chunk_bytes`: 取得の 1 回の読み取りの単位(6.1)
    - `message_path_max_chars`: 説明文に入れるパスの長さの上限(7.3)
    """

    max_patterns: int = 100
    max_pattern_bytes: int = 1024
    read_chunk_bytes: int = 1024 * 1024
    message_path_max_chars: int = 200

    def __post_init__(self) -> None:
        if self.max_patterns < 1:
            raise ValueError("max_patterns must be at least 1")
        if self.max_pattern_bytes < 1:
            raise ValueError("max_pattern_bytes must be at least 1")
        if self.read_chunk_bytes < 1:
            raise ValueError("read_chunk_bytes must be at least 1")
        if self.message_path_max_chars < 1:
            raise ValueError("message_path_max_chars must be at least 1")
