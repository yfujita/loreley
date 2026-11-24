"""`web` の死活確認: `WEB_DIST_DIR` 直下の `index.html` が読めること(C 6.3。D 4.10)。

ローカルのファイルの確認と 1 バイトの読み取りだけで、ブロックする見込みが小さいので、
`BlockingRunner` を通さず `services.dashboard` が直接呼ぶ(R9 の明示の例外)。キャッシュせず、
呼ばれるたびに確認する。
"""

from pathlib import Path

from loreley_api.common.probe_outcome import ProbeOutcome

INDEX_FILE_NAME = "index.html"


class WebDistProbe:
    def check(self, directory: str) -> ProbeOutcome:
        index_path = Path(directory) / INDEX_FILE_NAME
        try:
            if not index_path.is_file():
                return ProbeOutcome("abnormal", "missing")
            with index_path.open("rb") as index_file:
                has_content = len(index_file.read(1)) == 1
        except OSError:
            # 権限がない・読み取りに失敗した。パスは出さない。
            return ProbeOutcome("abnormal", "missing")
        return ProbeOutcome("normal") if has_content else ProbeOutcome("abnormal", "missing")
