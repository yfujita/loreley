"""`external_id` への規則の適用と検証(interface 5.1。案: CI-P-1・CI-P-2・CI-P-10・CI-P-15)。

Connector は規則適用前の値を返し、ここが次の順に処理する(順序を変えると、送る値と Indexer が
算出する `document_id` の値がずれる)。

1. 孤立サロゲートを ID 用エスケープで置き換える(以降の処理が孤立サロゲートを扱わないよう最初に行う)
2. NFC に正規化する
3. `\\` を `/` に置き換える
4. 検証する(空・NUL・UTF-8 で 4096 バイト超・先頭が `/` は `invalid_external_id`)

先頭の `/` は除去しない。除去すると `/a` と `a` が同じ文書になるため(Indexer も除去しない)。
"""

import re
import unicodedata

from loreley_crawler.connectors.interface import ConnectorError, ErrorCategory

# 検証規則としての仮値(Indexer 実装が置いた。interface 5.1 の規則 5)。
MAX_EXTERNAL_ID_BYTES = 4096

# U+FFFD。フォーマッタが見えにくい文字に書き換えないよう、`chr` で組み立てる。
REPLACEMENT_CHARACTER = chr(0xFFFD)
_ESCAPE_TARGETS = re.compile(f"[{REPLACEMENT_CHARACTER}\ud800-\udfff]")


def escape_lone_surrogates_for_id(value: str) -> str:
    """孤立サロゲート 1 文字(U+D800〜U+DFFF)を、U+FFFD + `u` + 4 桁の大文字 16 進にする。

    入力中の U+FFFD 1 文字は U+FFFD 2 文字にする。性質: 決定的、単射(導入する文字自体を
    エスケープするので、別の入力が同じ出力にならない)、`\\` と NUL を含まない。
    表示用の置換(`common` の `replace_lone_surrogates`)とは別物で、単射を求める点が違う。
    """
    return _ESCAPE_TARGETS.sub(_escape_one, value)


def normalize_path_form(external_id: str) -> str:
    """NFC に正規化し、`\\` を `/` に置き換える(規則 1・2)。冪等。

    `document_id` の算出も同じ正規化を行う(Indexer の `normalize_external_id` と同じ)。
    """
    return unicodedata.normalize("NFC", external_id).replace("\\", "/")


def apply_external_id_rules(raw_external_id: str) -> str:
    """規則適用前の値から、Indexer に送る最終形を作る。規則に合わなければ `invalid_external_id`。

    説明文には違反の種類だけを入れ、`external_id` の値は含めない(値は呼び出し側が表示用に整形する)。
    """
    final_form = normalize_path_form(escape_lone_surrogates_for_id(raw_external_id))
    violation = _find_violation(final_form)
    if violation is not None:
        raise ConnectorError.of(
            ErrorCategory.INVALID_EXTERNAL_ID, f"external_id が規則に違反している: {violation}"
        )
    return final_form


def _escape_one(match: re.Match[str]) -> str:
    character = match.group()
    if character == REPLACEMENT_CHARACTER:
        return REPLACEMENT_CHARACTER * 2
    return f"{REPLACEMENT_CHARACTER}u{ord(character):04X}"


def _find_violation(final_form: str) -> str | None:
    if final_form == "":
        return "空"
    if "\0" in final_form:
        return "NUL を含む"
    if len(final_form.encode("utf-8")) > MAX_EXTERNAL_ID_BYTES:
        return f"UTF-8 で {MAX_EXTERNAL_ID_BYTES} バイトを超える"
    if final_form.startswith("/"):
        return "先頭が `/`"
    return None
