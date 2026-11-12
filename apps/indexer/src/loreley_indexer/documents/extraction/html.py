"""HTML からの本文抽出(beautifulsoup4 + lxml)。"""

from bs4 import BeautifulSoup
from bs4.exceptions import ParserRejectedMarkup

_NON_TEXT_TAGS = ("script", "style")


class UnparsableHtmlError(Exception):
    pass


def html_to_text(html: str) -> str:
    """script・style を除いた本文を返す。

    要素の境界で改行を入れる。入れないと `<p>a</p><p>b</p>` が `ab` に連結され、
    語が混ざって検索できなくなるため。HTML 上の空白だけの行は、後段の正規化で空行に畳まれる。
    """
    try:
        soup = BeautifulSoup(html, "lxml")
    except ParserRejectedMarkup:
        raise UnparsableHtmlError from None
    for element in soup(_NON_TEXT_TAGS):
        element.decompose()
    return soup.get_text(separator="\n")
