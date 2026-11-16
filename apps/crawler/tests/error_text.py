"""例外が、ログ(`logger.exception`)にどう出るかの確認用。"""

import traceback


def logged_text(error: BaseException) -> str:
    """`logger.exception` が出す traceback の文字列(連鎖した原因・文脈を含む)。

    `from None` の例外は、`__cause__` がなく `__suppress_context__` が真で、元の例外は出ない。
    """
    return "".join(traceback.format_exception(error))
