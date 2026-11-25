"""AIT-10〜AIT-12: データソースの登録・更新・参照(EP-01〜06・08・11 のうち、設定に関わるもの)。

目的:
    Admin API が、実 Crawler(`POST /sources`・`PUT /sources/{source_id}`)を経由して実 OpenSearch の
    `loreley-sources` に設定を保存し、それを実 OpenSearch から読み直して返すことを確かめる。
      - AIT-10: 登録・更新が、単位の変換(日→秒、%→割合)を経て `loreley-sources` に保存され、
        EP-02・EP-01 から読めること。同内容の再送は 200、内容違いは 409 になること
      - AIT-11: 実 Connector が返す設定の違反が、Admin API で項目別の 400 `config_invalid` になること
      - AIT-12: 未登録のソースへの操作が、Crawler の応答を写して 404(EP-08 だけは 200)になること
    単体テストでは、Crawler・Connector の応答は fake で、実際の固定文・strict マッピングへの書き込み・
    実 OpenSearch の読み取り応答を確認できない。入力検証の全パターンは単体テストで済んでおり、
    ここでは再検証しない。

参照する設計書の章:
    - admin-api-v0.1.md 2.5(`config_invalid` の分解)、2.8(単位の変換)、2.9(`lock_state`)、
      3.1〜3.5(EP-01〜05)、4.1・4.3(EP-06・08)、6.1(EP-11)
    - crawler-api-v0.4.md 4.1(404)、4.3(ロック解放)、4.4(設定の登録・更新)
    - connector-file-system-v0.3.md 2 章(`connector_config` の違反の固定文)

扱うシナリオ: AIT-10(登録・更新・一覧・詳細)、AIT-11(`config_invalid`)、AIT-12(未登録のソース)
"""

from typing import Any

import pytest

from support import (
    AdminApi,
    OpenSearchProbe,
    SourceDirectory,
    expect_error,
    expect_json,
    find_source_row,
    parse_instant,
    register_source,
    source_settings,
    wait_for_source_listing,
)

# Crawler は、この設定の cron 式を、2 月 29 日の 3 時にしか起動しない式として受け付ける。IT のソースが
# 実際に定期起動されて、実行中のジョブが他のテストの窓を乱さないようにするため。
RARELY_FIRING_CRON = "0 3 29 2 *"

# Connector が `connector_config` の違反に返す固定文(connector-file-system v0.3 2 章)。
RELATIVE_ROOT_DETAIL = "`/` で始まる絶対パスでない"
UNKNOWN_ITEM_DETAIL = "未知の項目がある"


def _file_system_config(directory: SourceDirectory) -> dict[str, Any]:
    """画面が常に送る `file_system` の 5 項目(admin-api 3.3)。"""
    return {
        "root": directory.container_root,
        "include_patterns": [],
        "exclude_patterns": [],
        "follow_symlinks": False,
        "include_hidden": False,
    }


def _source_ids_of(listing: dict[str, Any]) -> set[str]:
    return {item["source_id"] for item in listing["items"]}


def test_register_update_and_read_a_source(
    api: AdminApi,
    opensearch: OpenSearchProbe,
    source_id: str,
    source_directory: SourceDirectory,
) -> None:
    """【何を確認するか】(AIT-10)
    データソースの登録(EP-03)が、日・%の入力を秒・割合に変換して `loreley-sources` に保存し、201 で
    保存内容を返すこと。同じ内容の再送は 200、内容違いは 409 `source_already_exists` になること。登録直後の
    詳細(EP-02)が「ロックなし・未実行・文書 0 件」を返し、更新(EP-04)が保存値と `updated_at` を変え、
    一覧(EP-01)が `source_id` の昇順で現れること。

    【前提と手順】
    前提: 一意な `source_id`、`file_system`、空のディレクトリ。
    手順:
      1. EP-03 で登録する(`ttl_days=2`・`ratio_threshold_percent=12.5`・`min_delete_count=3`、
         `schedule_cron` なし)。`loreley-sources` を直接読む。
      2. 同じ本文で再送する。`ttl_days` を変えた本文でも送る。
      3. EP-02 で詳細を読む。
      4. EP-04 で更新する(`ttl_seconds=3600`・`ratio_threshold_percent=20`・`min_delete_count=5`・
         `schedule_cron` あり)。`loreley-sources` と EP-02 を読む。
      5. 名前が後ろに並ぶソースをもう 1 つ登録し、EP-01 を読む。

    【期待する結果とその根拠】
    - 手順 1: 201。応答は `ttl_seconds=172800`・`ttl_days=2`・`ratio_threshold_percent=12.5`・
      `status=active`・`schedule_cron=null`(admin-api 2.8・3.3)。`loreley-sources` の文書は
      `ttl=172800`・`ratio_threshold=0.125`(Crawler の単位。秒と 0〜1 の割合。2.8)で、`status=active`。
    - 手順 2: 同じ内容は 200 で、`updated_at` を含めて同じ応答(冪等。3.3)。内容違いは 409
      `source_already_exists`・`details.status=active`(3.3)。
    - 手順 3: `lock.state=none`・`lock.job=null`・`lock.acquired_at=null`、`last_crawl=null`・
      `last_completed_at=null`・`delete_job=null`、`index.document_count=0`、`unavailable={}`(3.2・2.9)。
      設定の項目は手順 1 の応答と同じ。
    - 手順 4: 200。`ttl_seconds=3600`・`ttl_days=null`(日で割り切れない。2.8)・
      `ratio_threshold_percent=20`・`schedule_cron` は送った値。`updated_at` は手順 1 より後(3.4)。
      `loreley-sources` も同じ値(`ttl=3600`・`ratio_threshold=0.2`)で、EP-02 の設定の項目は更新の応答と
      同じ。
    - 手順 5: EP-01 の `items[].source_id` は昇順。この `source_id` の行は、未実行(`last_crawl=null`)・
      `document_count=0`・`delete_job=null`・`unavailable={}`で、最上位の `unavailable` は `{}`(3.1)。
      手順 5 で登録した、名前が後ろに並ぶソースは、この `source_id` の後ろに現れる。EP-01 は検索で読む
      ので、登録・更新の反映(最大約 1 秒。admin-api-architecture AAA-P-6)を、上限つきで待ってから確認する。

    【単体テストでは確認できず実機で確認する点】
    実 Crawler・実 OpenSearch(strict マッピングの `loreley-sources`)への保存と、保存値が Admin API の
    応答の単位に戻ること。EP-02・EP-01 が、実 OpenSearch の `loreley-jobs`(文書なし)・検索インデックス
    (0 件)を読んで、`null` と 0 を区別して返すこと。
    """
    connector_config = _file_system_config(source_directory)
    request_body = {
        "source_id": source_id,
        "connector_type": "file_system",
        "connector_config": connector_config,
        "ttl_days": 2,
        "ratio_threshold_percent": 12.5,
        "min_delete_count": 3,
    }

    # 1. 登録する
    created = expect_json(api.register_source(request_body), 201)

    expected_created = {
        "source_id": source_id,
        "connector_type": "file_system",
        "connector_config": connector_config,
        "ttl_seconds": 172800,
        "ttl_days": 2,
        "ratio_threshold_percent": 12.5,
        "min_delete_count": 3,
        "schedule_cron": None,
        "status": "active",
    }
    for name, expected_value in expected_created.items():
        assert created[name] == expected_value, f"{name} must be {expected_value!r}: {created}"
    assert "updated_at" in created, f"the response must have updated_at: {created}"
    stored = opensearch.fetch_source_config(source_id)
    assert stored is not None, "the settings must be stored in loreley-sources"
    assert (stored["ttl"], stored["ratio_threshold"], stored["min_delete_count"]) == (
        172800,
        0.125,
        3,
    ), f"the stored values must be in the Crawler's units (seconds, ratio): {stored}"
    assert stored["status"] == "active", f"the stored status must be active: {stored}"

    # 2. 同じ内容の再送と、内容違い
    resent = expect_json(api.register_source(request_body), 200)
    assert resent == created, f"a resend of the same content must return the same body: {resent}"
    conflict = expect_error(
        api.register_source({**request_body, "ttl_days": 3}), 409, "source_already_exists"
    )
    assert conflict["details"] == {"status": "active"}, (
        f"details must carry the existing status: {conflict}"
    )

    # 3. 登録直後の詳細
    detail = expect_json(api.get_source(source_id), 200)
    assert {name: detail[name] for name in expected_created} == expected_created, (
        f"EP-02 must return the saved settings: {detail}"
    )
    assert detail["updated_at"] == created["updated_at"], f"updated_at must not change: {detail}"
    assert detail["lock"] == {"state": "none", "job": None, "acquired_at": None}, (
        f"a new source has no lock: {detail['lock']}"
    )
    assert (detail["last_crawl"], detail["last_completed_at"], detail["delete_job"]) == (
        None,
        None,
        None,
    ), f"a new source has never crawled: {detail}"
    assert detail["index"] == {"document_count": 0}, f"no documents yet: {detail['index']}"
    assert detail["unavailable"] == {}, f"nothing must be unavailable: {detail['unavailable']}"

    # 4. 更新する
    update_body = {
        "connector_config": connector_config,
        "ttl_seconds": 3600,
        "ratio_threshold_percent": 20,
        "min_delete_count": 5,
        "schedule_cron": RARELY_FIRING_CRON,
    }
    updated = expect_json(api.update_source(source_id, update_body), 200)

    assert (
        updated["ttl_seconds"],
        updated["ttl_days"],
        updated["ratio_threshold_percent"],
        updated["min_delete_count"],
        updated["schedule_cron"],
    ) == (3600, None, 20, 5, RARELY_FIRING_CRON), f"the update must be reflected: {updated}"
    assert parse_instant(updated["updated_at"]) > parse_instant(created["updated_at"]), (
        f"updated_at must advance on a change: {created['updated_at']} -> {updated['updated_at']}"
    )
    stored_after_update = opensearch.fetch_source_config(source_id)
    assert stored_after_update is not None, "the settings must still be stored"
    assert (stored_after_update["ttl"], stored_after_update["ratio_threshold"]) == (3600, 0.2), (
        f"the stored values must follow the update: {stored_after_update}"
    )
    detail_after_update = expect_json(api.get_source(source_id), 200)
    assert {name: detail_after_update[name] for name in updated} == updated, (
        f"EP-02 must return the updated settings: {detail_after_update}"
    )

    # 5. 一覧: source_id の昇順で、この行は未実行・0 件
    later_source_id = f"{source_id}-later"
    register_source(api, SourceDirectory(later_source_id))
    # EP-01 は検索で読むので、登録・更新の反映(最大約 1 秒)を待つ
    listing = wait_for_source_listing(
        api,
        lambda body: (
            {source_id, later_source_id} <= _source_ids_of(body)
            and (row := find_source_row(body, source_id)) is not None
            and row["schedule_cron"] == RARELY_FIRING_CRON
        ),
        what="EP-01 listing both sources with the updated schedule",
    )
    listed_source_ids = [item["source_id"] for item in listing["items"]]
    assert listed_source_ids == sorted(listed_source_ids), (
        f"EP-01 must be in ascending source_id order: {listed_source_ids}"
    )
    assert listed_source_ids.index(source_id) < listed_source_ids.index(later_source_id), (
        f"{source_id} must come before {later_source_id}: {listed_source_ids}"
    )
    row = find_source_row(listing, source_id)
    assert row is not None, f"{source_id} must be listed: {listing}"
    assert (row["connector_type"], row["status"], row["schedule_cron"]) == (
        "file_system",
        "active",
        RARELY_FIRING_CRON,
    ), f"the row must show the updated settings: {row}"
    assert (row["last_crawl"], row["last_completed_at"], row["delete_job"]) == (None, None, None), (
        f"the row must show no job: {row}"
    )
    assert row["document_count"] == 0, f"document_count must be 0 (not null): {row}"
    assert row["unavailable"] == {}, f"the row must have no failure: {row}"
    assert listing["unavailable"] == {}, f"the top-level unavailable must be empty: {listing}"


@pytest.mark.parametrize(
    ("connector_config_of", "expected_field", "expected_detail"),
    [
        pytest.param(
            lambda directory: {"root": "relative/path"},
            "connector_config.root",
            RELATIVE_ROOT_DETAIL,
            id="relative_root",
        ),
        pytest.param(
            lambda directory: {"root": directory.container_root, "rooot": "typo"},
            "connector_config",
            UNKNOWN_ITEM_DETAIL,
            id="unknown_item",
        ),
    ],
)
def test_register_with_an_invalid_connector_config_is_rejected_and_not_stored(
    api: AdminApi,
    opensearch: OpenSearchProbe,
    source_id: str,
    source_directory: SourceDirectory,
    connector_config_of: Any,
    expected_field: str,
    expected_detail: str,
) -> None:
    """【何を確認するか】(AIT-11 の EP-03)
    実 Connector が返す設定の違反(相対パスの `root`、未知の項目)が、400 `config_invalid` になり、
    項目・理由・違反の固定文に分解されて返ること。設定は保存されないこと。

    【前提と手順】
    前提: 一意な `source_id`。手順: 違反のある `connector_config` で EP-03 を呼ぶ。
    違反は 2 つ(`root` が `/` で始まらない、未知の項目 `rooot` がある)。

    【期待する結果とその根拠】
    - 400 `config_invalid`、`retryable=false`。`details.errors` は 1 件で、`field`・`reason=config_invalid`・
      `detail`(Connector の固定文)(admin-api 2.5)。`field` は、`root` のとき `connector_config.root`、
      未知の項目のとき(Connector が項目名を `connector_config` 自身として返す例外)`connector_config`。
    - `details.crawler_message` は空でない文字列(Crawler の `message`。2.5)。
    - `loreley-sources` にこの `source_id` の文書は作られない(Connector の検証が保存より前に働く)。

    【単体テストでは確認できず実機で確認する点】
    実 Connector の固定文が、Admin API の分解の規則(最初の `: ` で分け、前半が項目名の形)に実際に
    合うこと(2.5 の「実装の固定文に依存する」前提の確認)。
    """
    request_body = source_settings(
        source_directory, connector_config=connector_config_of(source_directory)
    )

    response = api.register_source(request_body)

    error = expect_error(response, 400, "config_invalid", expected_retryable=False)
    assert error["details"]["errors"] == [
        {"field": expected_field, "reason": "config_invalid", "detail": expected_detail}
    ], f"the violation must be split into field, reason and detail: {error}"
    crawler_message = error["details"]["crawler_message"]
    assert isinstance(crawler_message, str)
    assert crawler_message, f"crawler_message must not be empty: {error}"
    assert opensearch.fetch_source_config(source_id) is None, (
        "a rejected configuration must not be stored"
    )


def test_update_with_an_invalid_connector_config_is_rejected_and_keeps_the_saved_settings(
    api: AdminApi, opensearch: OpenSearchProbe, registered_source: SourceDirectory
) -> None:
    """【何を確認するか】(AIT-11 の EP-04)
    更新(EP-04)でも、設定の違反が 400 `config_invalid` になり、保存済みの設定が変わらないこと。

    【前提と手順】
    前提: 登録済みのソース。手順: 相対パスの `root` で EP-04 を呼ぶ → `loreley-sources` を読む。

    【期待する結果とその根拠】
    400 `config_invalid`、`field=connector_config.root`・`detail` は固定文。保存済みの文書は、更新前と
    完全に同じ(`updated_at` を含む)。Crawler は、設定があり保存済みの種別が読めるとき、その種別で先に
    検証する(admin-api 3.4)。

    【単体テストでは確認できず実機で確認する点】
    実 Crawler が、保存済みの種別で `connector_config` を検証してから保存し、違反のときは書かないこと。
    """
    source_id = registered_source.source_id
    saved = opensearch.fetch_source_config(source_id)
    assert saved is not None, "the registered source must be stored"
    update_body = {
        "connector_config": {"root": "relative/path"},
        "ttl_seconds": 3600,
        "ratio_threshold_percent": 20,
        "min_delete_count": 5,
    }

    response = api.update_source(source_id, update_body)

    error = expect_error(response, 400, "config_invalid")
    assert error["details"]["errors"] == [
        {
            "field": "connector_config.root",
            "reason": "config_invalid",
            "detail": RELATIVE_ROOT_DETAIL,
        }
    ], f"the violation must be split into field, reason and detail: {error}"
    assert opensearch.fetch_source_config(source_id) == saved, (
        "a rejected update must not change the saved settings"
    )


def test_operations_on_an_unregistered_source_are_rejected_with_404(
    api: AdminApi, opensearch: OpenSearchProbe, source_id: str
) -> None:
    """【何を確認するか】(AIT-12)
    設定のない `source_id` に対して、EP-02・04・05・06・11 が 404 `source_config_not_found` を返し、
    EP-08(ロック解放)だけが 200 `released=false` を返すこと。ジョブ記録・ロックは作られないこと。

    【前提と手順】
    前提: 一意な `source_id`(登録しない)。
    手順: EP-02・EP-11(`tab=skipped`)・EP-04(正しい本文)・EP-05・EP-06・EP-08 を呼ぶ。

    【期待する結果とその根拠】
    - EP-02・EP-11: Admin API が `loreley-sources` を読んで 404 `source_config_not_found`(3.2・6.1)。
    - EP-04・05・06: Crawler が設定なしを 404 `source_config_not_found` で返し、そのまま通る(2.6。
      Crawler は設定を読んで、なければロックを取る前に拒否する)。
    - EP-08: 200 `released=false`・`failed_job_id=null`(設定がなくても解放でき、ロック文書がなければ
      何もしない冪等な応答。4.3)。
    - `loreley-jobs` に、この `source_id` のジョブ記録とロック文書は作られない。

    【単体テストでは確認できず実機で確認する点】
    実 Crawler が、文書なし(OpenSearch の `found: false`)を「設定なし」として扱い、500 や 503 にしない
    こと。EP-08 が、実 Crawler のロック解放で「ロックなし」を 200 で返すこと。
    """
    update_body = {
        "connector_config": {"root": f"/data/documents/{source_id}"},
        "ttl_seconds": 3600,
        "ratio_threshold_percent": 20,
        "min_delete_count": 5,
    }

    responses = {
        "EP-02": api.get_source(source_id),
        "EP-11": api.list_documents(source_id, tab="skipped"),
        "EP-04": api.update_source(source_id, update_body),
        "EP-05": api.start_source_delete(source_id),
        "EP-06": api.start_crawl(source_id),
    }

    for endpoint, response in responses.items():
        error = expect_error(response, 404, "source_config_not_found", expected_retryable=False)
        assert "details" not in error or not error["details"], (
            f"{endpoint}: 404 must carry no details: {error}"
        )
    released = expect_json(api.release_lock(source_id), 200)
    assert released == {"source_id": source_id, "released": False, "failed_job_id": None}, (
        f"EP-08 must report nothing to release: {released}"
    )
    assert opensearch.job_records_of(source_id) == [], "no job record may be created"
    assert opensearch.fetch_lock(source_id) is None, "no lock may be taken"
