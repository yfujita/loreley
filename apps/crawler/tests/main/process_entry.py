"""テスト用の起動スクリプト(`python -m tests.main.process_entry`)。

`loreley_crawler.main.main()` を、メモリ上の Repository と fake の Indexer で、実プロセスとして
起動する(実 OpenSearch・実 Indexer を使わずに、実 uvicorn・実シグナルを確かめるため)。待ち受けは
空きポート(`port=0`)にし、実際のポートは uvicorn の起動ログ(`Uvicorn running on ...`)に出る。
"""

from loreley_crawler import main as main_module
from tests.main.support import Fakes

fakes = Fakes()
original_options = main_module.http_server_options

main_module.create_backends = lambda config: fakes.backends
main_module.http_server_options = lambda config: {**original_options(config), "port": 0}

if __name__ == "__main__":
    main_module.main()
