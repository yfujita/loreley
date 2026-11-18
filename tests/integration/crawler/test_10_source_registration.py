"""CIT-10: データソース設定の登録(`POST /sources`)。

目的:
    データソース設定の登録が、実 OpenSearch の `loreley-sources`(`dynamic: strict`)に受け入れられ、
    保存した内容を応答として返すこと。同じ内容の再送は 200 で、不正な設定は 400、設定のないソースへの
    クロール起動は 404 になること。単体テストの fake はマッピングを持たず、strict に拒否される書き込みを
    検出できない。

参照する設計書の章:
    - crawler-api-v0.4.md 3.3(エラー形式)、4.1(クロール起動。404)、4.4.2(設定の登録。201・200)
    - crawler-architecture-v0.4.md 3.1・3.2(`loreley-sources` の項目)
    - connector-file-system-v0.3.md 2 章(`connector_config`。未知の項目は `config_invalid`)
    - apps/crawler/README.md 5 章(API)、9 章(`loreley-sources` の索引定義)

扱うシナリオ: CIT-10
"""

from support import (
    CrawlerApi,
    OpenSearchProbe,
    SourceDirectory,
    expect_error,
    expect_json,
    source_settings,
)


def test_register_source_is_stored_and_a_resend_is_accepted_as_is(
    crawler_api: CrawlerApi,
    opensearch: OpenSearchProbe,
    source_id: str,
    source_directory: SourceDirectory,
) -> None:
    """【何を確認するか】
    `POST /sources` が 201 で設定を返し、`loreley-sources` に strict マッピングのまま保存されること。
    同じ内容の再送は 200 で、同じ設定を返すこと。

    【前提と手順】
    前提: 一意な `source_id`(`connector_type` は `file_system`。`filesystem` は 400)。
    手順: 登録する → `loreley-sources` を直接読む → 同じ本文で再送する。

    【期待する結果とその根拠】
    - 201。本文は、送った項目に `status: active` と `updated_at` を加えたもの(api 4.4.2)。
    - `loreley-sources` の ID `{source_id}` の文書が、同じ値を持つ(`schedule_cron` は省略なので null)。
      strict マッピングが Crawler の書き込み項目(9 項目)をすべて受け入れた証拠になる。受け入れなければ、
      Crawler は 500 を返し、この手順は 201 にならない。
    - 再送は 200 で、`updated_at` を含めて同じ設定(同じ内容の登録は冪等。api 4.4.2)。

    【fake では確認できず実機で確認する点】
    実際の strict マッピングへの書き込み、`create`(存在しない場合だけ成功)の実際の動作。
    """
    request_body = source_settings(source_id, source_directory)

    # 登録する
    created = expect_json(crawler_api.register_source(request_body), 201)

    expected_fields = {**request_body, "schedule_cron": None, "status": "active"}
    for name, expected_value in expected_fields.items():
        assert created[name] == expected_value, (
            f"the response must echo {name}={expected_value!r}: {created}"
        )
    assert "updated_at" in created, f"the response must have updated_at: {created}"

    # loreley-sources を直接読む(Crawler の応答だけに頼らない)
    stored = opensearch.fetch_source_config(source_id)
    assert stored is not None, "the source configuration must be stored in loreley-sources"
    assert stored == created, f"the stored document must equal the response: {stored} / {created}"

    # 同じ内容で再送する
    resent = expect_json(crawler_api.register_source(request_body), 200)

    assert resent == created, (
        f"a resend of the same content must return the same settings: {resent}"
    )


def test_register_source_rejects_an_unknown_connector_config_item(
    crawler_api: CrawlerApi,
    opensearch: OpenSearchProbe,
    source_id: str,
    source_directory: SourceDirectory,
) -> None:
    """【何を確認するか】
    `connector_config` に未知の項目があると 400 `config_invalid` になり、設定が保存されないこと。

    【前提と手順】
    前提: 一意な `source_id`。
    手順: 未知の項目(`rooot`)を足した `connector_config` で登録する。

    【期待する結果とその根拠】
    400 `config_invalid`(Connector の `validate_config` が返す違反。api 3.3・表の `config_invalid`)。
    綴りの誤りを見逃さないための拒否(FS 設計書 2 章)。`loreley-sources` に文書は作られない。
    `invalid_request` ではない(`invalid_request` は本文の形式の不正。例: 未知の `connector_type`)。

    【fake では確認できず実機で確認する点】
    実際の HTTP 経路で、Connector の検証が登録より前に働くこと(拒否された設定が OpenSearch に残らない)。
    """
    request_body = source_settings(source_id, source_directory)
    request_body["connector_config"] = {"root": source_directory.container_root, "rooot": "typo"}

    # 未知の項目つきで登録する
    response = crawler_api.register_source(request_body)

    expect_error(response, 400, "config_invalid")
    assert opensearch.fetch_source_config(source_id) is None, (
        "a rejected configuration must not be stored"
    )


def test_start_crawl_of_an_unregistered_source_is_rejected_with_404(
    crawler_api: CrawlerApi, opensearch: OpenSearchProbe, source_id: str
) -> None:
    """【何を確認するか】
    設定のない `source_id` へのクロール起動が 404 `source_config_not_found` になり、ジョブ記録・ロックが
    作られないこと。

    【前提と手順】
    前提: 一意な `source_id`(登録しない)。
    手順: `POST /sources/{source_id}/crawl-jobs` を呼ぶ。

    【期待する結果とその根拠】
    404 `source_config_not_found`(api 4.1。受付は、設定を読んで、なければロックを取る前に拒否する)。
    したがって `loreley-jobs` にこの `source_id` のジョブ記録とロック文書は作られない。

    【fake では確認できず実機で確認する点】
    実 OpenSearch の ID 指定の取得が「文書なし」(404 の `found: false`)を返したとき、Crawler がそれを
    「設定なし」として扱い、500 や 503 にしないこと。
    """
    # 登録していないソースのクロールを起動する
    response = crawler_api.start_crawl(source_id)

    expect_error(response, 404, "source_config_not_found")
    assert opensearch.job_records_of(source_id) == [], "no job record may be created"
    assert opensearch.fetch_lock(source_id) is None, "no lock may be taken"
