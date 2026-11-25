# 0005 P2: IT の土台とスクリプト

日付: 2026-11-25
担当: code-implementer(実装)、メインエージェント(成果物・静的検査・残骸の再確認)

## 実施内容

- `tests/integration/api/` を新設: `pyproject.toml`(pytest・httpx、dev に ruff)、`uv.lock`、`compose.test.yaml`(プラン 4.2)、`fixtures/web/index.html`、`conftest.py`(4.5)、`support.py`(4.4)、`test_01_startup.py`(AIT-01 を 5 関数に分割。ID は docstring)
- `support.py`: 定数・`unique_id`・独立実装の `compute_document_id`・`expect_json`/`expect_error`・`poll_until`と待ちヘルパ(ジョブ終端・`running`・ロック解放・アイドル)・`AdminApi`(14 EP + `/healthz` + `openapi_json`)・`OpenSearchProbe`(読み取りのみ)・`SourceDirectory`・`register_source`・`ComposeControl`(プロジェクト `loreley-it` と compose ファイルを固定、操作は stop/start のみ、サービスは crawler・indexer・opensearch のみ、subprocess にタイムアウト、操作前に `ps -aq` で実在確認)
- `conftest.py`: session autouse で 4 サービスの疎通・`data/`・メンテナンスフラグ確認(失敗は `pytest.exit(2)`)、function autouse で前後に `wait_for_idle`、`compose_control` は `LORELEY_IT_ALLOW_COMPOSE_CONTROL=1` でなければ skip
- `scripts/run-api-integration-test.sh`: `run-crawler-integration-test.sh` を複製して改変(ポート 4 つ、索引名 export、`LORELEY_CRON_TIMEZONE=Asia/Tokyo`、`CRAWLER_DOCUMENTS_DIR=tests/integration/api/data`、起動 `opensearch opensearch-init indexer crawler api`、pytest 既定 `-v -rP`)

## 変更したファイル(すべて新規)

`scripts/run-api-integration-test.sh`、`tests/integration/api/{pyproject.toml,uv.lock,compose.test.yaml,conftest.py,support.py,test_01_startup.py,fixtures/web/index.html}`

## 検証結果

- `scripts/run-api-integration-test.sh -k test_01`: AIT-01 の 5 件成功(終了コード 0、初回ビルド込みで約 4〜5 分)。EP-13 は 8 件が固定順で crawler・indexer・opensearch・api・web が `normal`(`web` は fixtures の mount が効いている)、opensearch-dashboards・embedding・llm が `not_configured`(`reason` はすべて null)。EP-14 は `cron_timezone=Asia/Tokyo`・`dashboards_url=null`(共通変数が api に届いている)。実機と設計の食い違いなし
- 事前確認の中止: `data/` に空でないファイルを置くと何も消さず終了コード 1、コンテナ・ボリュームは作られない(確認後に削除)
- `ComposeControl` の許可リスト(docker 不使用): `stop api`・`stop opensearch-init`・`stop "crawler; rm -rf /"`・`down crawler`・`stop other-project-opensearch-1`・`rm indexer` はすべて `ValueError`。crawler・indexer・opensearch の stop/start は `-p loreley-it` 固定の引数リストになる
- ruff check・format、`uv lock --check`、`pytest --collect-only`(5 件)、`bash -n`: OK(メインエージェントが ruff・format・collect・`bash -n` を再実行して確認)。shellcheck は未インストールで未実施
- 終了後: `loreley-it` のコンテナ・ボリューム・ネットワーク・`data/` なし。他プロジェクトのコンテナ `opensearch-opensearch-1`(停止中)は操作していない(メインエージェントが `docker ps -a` で再確認)

## 判断・設計上の理由

- EP-12 は 4 索引の部分集合として確認(9200 を他の索引が共有しても壊れないようにするため)
- `wait_for_job_running` は窓を見逃して終端になっていた場合、そのことが分かるメッセージで失敗する
- Admin API は `/api/admin/v1` 配下(`apps/api` の `ADMIN_API_PREFIX` を確認して固定)

## 発見事項

- 実機と設計の食い違いなし
- `./run-api-integration-test.sh --help` をスクリプトのディレクトリ内から実行すると `usage()` が失敗する(既存 crawler スクリプトと同じ。リポジトリルートからは動く。通常利用に影響なく修正しない)

## 未対応事項・次にやること

- `ComposeControl` の stop/start/`wait_healthy` の実 docker 実行は P4。`registered_source`/`register_source` の実機確認は P3
- OpenSearch 直接書き込み(AIT-51 孤児ロック・AIT-41 スキップ記録)は P3 で実装(crawler-architecture 3.3・5.1、`infra/opensearch/schema/jobs.json` の形式を確認)
- AIT-30・32 用の直読み(`terms`・`_cat`)は必要なテストで追加
- 次: P3(AIT-10〜60)。分量が多いため P3a(AIT-10・11・12・20・21)と P3b(AIT-30・31・32・40・41・50・51・60)に分けて実施する
