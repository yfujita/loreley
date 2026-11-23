"""外部システム(OpenSearch・Crawler・死活確認の対象)へのアクセス。名前空間だけを持つ。

`opensearch`・`crawler_client`・`probes` は互いに依存しない(共有する型は `common`)。
"""
