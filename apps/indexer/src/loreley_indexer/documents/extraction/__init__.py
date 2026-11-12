"""本文の抽出・正規化(module 4.3)。他のモジュールに依存しない(抽出ライブラリを除く)。"""

from loreley_indexer.documents.extraction.extractor import ExtractionConfig, TextExtractor
from loreley_indexer.documents.extraction.results import (
    ExtractedText,
    ExtractionFailed,
    ExtractionFailureReason,
    ExtractionResult,
)

__all__ = [
    "ExtractedText",
    "ExtractionConfig",
    "ExtractionFailed",
    "ExtractionFailureReason",
    "ExtractionResult",
    "TextExtractor",
]
