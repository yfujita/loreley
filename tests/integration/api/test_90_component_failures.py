"""AIT-90・AIT-91・AIT-92: コンポーネントの停止と復旧(Crawler・Indexer・OpenSearch)。

目的:
    実 Crawler・実 Indexer・実 OpenSearch のコンテナを止めたとき、Admin API の応答が設計どおりに
    変わり(読み取りは継続し、書き込みだけが失敗する。admin-api 10.1・10.2)、サービスを戻した後に
    元の動作へ復旧することを確かめる。
      - AIT-90: Crawler 停止。EP-03〜08 が 503 `crawler_unreachable`、EP-13 の `crawler` が `abnormal`、
        それ以外の EP は通常どおり。復旧後にクロールが成功する
      - AIT-91: Indexer 停止。api の読み取り・操作には影響がなく、停止中に始めたクロール・ソース削除が
        Crawler の側で失敗する(部分失敗)。復旧後の再実行で完了する
      - AIT-92: OpenSearch 停止。読み取りの EP が 503 `unavailable`、EP-13 の `opensearch` が
        `abnormal`、EP-06 が 503。復旧後に読み取りとクロールが戻る
    単体テストでは、実コンテナの停止(接続拒否・名前解決失敗)で Admin API・Crawler が返す実際の応答と、
    停止中に始めた Job の Crawler 側の終わり方、再起動後の復旧を確認できない。

参照する設計書の章:
    - admin-api-v0.1.md 2.3(エラー code)、2.6(Crawler 写像)、8.1(EP-13)、10.1・10.2(失敗時の振る舞い)
    - crawler-architecture-v0.4.md 7.8(Indexer のエラー別の扱い)、8.1・8.3(ソース削除の順と再実行)
    - crawler-architecture-v0.4.md 5.8(起動時の回復)

扱うシナリオ: AIT-90(Crawler)、AIT-91(Indexer)、AIT-92(OpenSearch)

安全策(障害系):
    - 止めてよいのは `loreley-it` の crawler・indexer・opensearch の `stop`・`start` だけ(`ComposeControl`。
      許可リスト・プロジェクト名は support.py で固定)。スクリプトが `LORELEY_IT_ALLOW_COMPOSE_CONTROL=1` を
      渡したときだけ動き、pytest を直接実行したときは skip する。
    - 止める区間は `compose_control.stopped(...)` で囲む。テストが途中で失敗しても、区間を抜けるときに
      必ず `start` し、healthy になるまで上限(300 秒)つきで待つ。停止中に始めたジョブも、上限つきで
      終わりまで待つ(止まったままのジョブが後続のテストを塞がないため)。
    - 障害系はこのファイルだけ(最後に実行される)。conftest の各テスト前後のアイドル待ち(EP-09 を読む)は、
      止める区間の外(テストの開始前と、復旧後の終了後)で実行されるので、OpenSearch 停止中に EP-09 が
      読めなくても影響しない。

実機の観測値の記録:
    設計が複数の値を許す箇所(EP-13 の `reason`、EP-06 の 503 の code など)は、どちらでも受け入れ、
    実際の値を `[observed]` つきで標準出力に出す(`-rP` で結果ログに残る)。
"""

from collections.abc import Callable
from typing import Any

from support import (
    COMPONENT_RECOVERY_POLL_INTERVAL_SECONDS,
    COMPONENT_RECOVERY_TIMEOUT_SECONDS,
    READ_LAG_POLL_INTERVAL_SECONDS,
    READ_LAG_TIMEOUT_SECONDS,
    AdminApi,
    ComposeControl,
    OpenSearchProbe,
    SourceDirectory,
    expect_error,
    expect_json,
    fetch_component_states,
    poll_until,
    run_crawl,
    source_settings,
    unique_id,
    wait_for_components_normal,
    wait_for_job_terminal,
    wait_for_lock_released,
    wait_for_source_detail,
    wait_for_source_listing,
    wait_for_source_row,
)

# 停止したコンテナへの接続の失敗として設計が許す理由(admin-api 8.1)。Docker は、停止したコンテナの
# 名前を解決できなくなる(名前解決失敗)ことが多いが、環境によっては接続拒否になるので、どちらも許す。
DOWN_REASONS = frozenset({"connection_refused", "name_not_resolved"})
OPTIONAL_COMPONENTS = ("opensearch-dashboards", "embedding", "llm")
ALL_RUNNING_COMPONENTS = ("crawler", "indexer", "opensearch", "api", "web")


def observed(label: str, value: object) -> None:
    """設計が複数の値を許す箇所の実機の値を、結果ログに残す。"""
    print(f"[observed] {label}: {value}")


def assert_component_down(states: dict[str, dict[str, Any]], component_id: str) -> str:
    """`component_id` が `abnormal` で、`reason` が停止を表す値であることを確かめ、`reason` を返す。"""
    component = states[component_id]
    assert component["state"] == "abnormal", f"{component_id} must be abnormal: {component}"
    assert component["reason"] in DOWN_REASONS, (
        f"{component_id} reason must be one of {sorted(DOWN_REASONS)}: {component}"
    )
    return str(component["reason"])


def assert_components_normal(
    states: dict[str, dict[str, Any]], component_ids: tuple[str, ...]
) -> None:
    for component_id in component_ids:
        component = states[component_id]
        assert (component["state"], component["reason"]) == ("normal", None), (
            f"{component_id} must be normal: {component}"
        )


def assert_optional_components_not_configured(states: dict[str, dict[str, Any]]) -> None:
    for component_id in OPTIONAL_COMPONENTS:
        component = states[component_id]
        assert (component["state"], component["reason"]) == ("not_configured", None), (
            f"{component_id} must stay not_configured: {component}"
        )


def settings_for_update(directory: SourceDirectory) -> dict[str, Any]:
    """EP-04 の本文(EP-03 の本文から `source_id`・`connector_type` を除いたもの)。"""
    body = source_settings(directory)
    del body["source_id"], body["connector_type"]
    return body


def test_crawler_down_fails_only_the_crawler_calls_and_the_crawl_works_after_recovery(
    api: AdminApi,
    opensearch: OpenSearchProbe,
    compose_control: ComposeControl,
    registered_source: SourceDirectory,
) -> None:
    """【何を確認するか】(AIT-90)
    Crawler が止まっている間、Crawler に中継する EP-03〜08 が 503 `crawler_unreachable`
    (`retryable=true`)になり、副作用がなく、OpenSearch だけで答える EP-01・02・09・10・11・12 と、
    設定だけで答える EP-14 は 200 のままであること。EP-13 は `crawler` だけが `abnormal` になること。
    Crawler を戻した後、EP-13 が `normal` に戻り、クロールが成功すること。

    【前提と手順】
    前提: 登録済みのソース S(md 1 件をクロール済み)。未登録の `source_id` N。
    手順:
      1. Crawler を止める(`stopped`)。
      2. EP-13 を読む。EP-03(N の登録)・04(S の更新)・05(S の削除)・06(S のクロール)・07(S の
         クロール済みジョブの取消)・08(S のロック解放)を呼ぶ。EP-01・02・09・10・11・12・14 を呼ぶ。
      3. Crawler を起動し直し(区間を抜ける)、healthy を待つ。
      4. EP-13 を読み、md を足して EP-06 でクロールする。

    【期待する結果とその根拠】
    - 手順 2: EP-13 は `crawler` が `abnormal`(`reason` は `connection_refused` か `name_not_resolved`)、
      `indexer`・`opensearch`・`api`・`web` が `normal`、任意の 3 つが `not_configured`(B 8.1)。
      EP-03〜08 は 503 `crawler_unreachable`・`retryable=true`(B 2.3・10.2)。書き込みは行われず、
      N は登録されず(EP-02 が 404)、S の設定は `active` のまま文書 1 件が残る。EP-01・02・09・10・11・12・
      14 は 200(B 10.1)。
    - 手順 4: EP-13 の 4 つ(`crawler`・`indexer`・`opensearch`・`api`)が `normal`。クロールは `succeeded`
      で、文書が 2 件になる(復旧後に Crawler・Indexer・OpenSearch の連携が元に戻った)。

    【単体テストでは確認できず実機で確認する点】
    実コンテナの停止で api が受ける接続の失敗の分類(EP-13 の `reason`、`crawler_unreachable`)、
    停止中に api の読み取りが影響を受けないこと、Crawler の再起動後の復旧(起動時の回復、api の再接続)。
    """
    stored = registered_source
    stored.write("first.md", b"# first\n\ntext of first\n")
    first_crawl = run_crawl(api, opensearch, stored.source_id)
    wait_for_source_row(
        api,
        stored.source_id,
        lambda row: row["document_count"] == 1,
        what="EP-01 counting the first document",
    )
    unregistered = SourceDirectory(unique_id("ait90-unregistered"))

    with compose_control.stopped("crawler"):
        # 2. EP-13
        states = fetch_component_states(api)
        reason = assert_component_down(states, "crawler")
        observed("AIT-90 EP-13 crawler reason", reason)
        assert_components_normal(states, ("indexer", "opensearch", "api", "web"))
        assert_optional_components_not_configured(states)

        # 2. Crawler に中継する EP は、接続前の失敗(503。再試行できる)
        crawler_calls = {
            "EP-03": api.register_source(source_settings(unregistered)),
            "EP-04": api.update_source(stored.source_id, settings_for_update(stored)),
            "EP-05": api.start_source_delete(stored.source_id),
            "EP-06": api.start_crawl(stored.source_id),
            "EP-07": api.cancel_job(first_crawl["job_id"]),
            "EP-08": api.release_lock(stored.source_id),
        }
        for response in crawler_calls.values():
            expect_error(response, 503, "crawler_unreachable", expected_retryable=True)

        # 2. OpenSearch・設定だけで答える EP は影響を受けない
        reads = {
            "EP-01": api.list_sources(),
            "EP-02": api.get_source(stored.source_id),
            "EP-09": api.list_jobs(source_id=stored.source_id),
            "EP-10": api.get_job(first_crawl["job_id"]),
            "EP-11": api.list_documents(stored.source_id, tab="extract_failed"),
            "EP-12": api.opensearch_cluster(),
            "EP-14": api.meta(),
        }
        bodies = {endpoint: expect_json(response, 200) for endpoint, response in reads.items()}
        assert bodies["EP-10"]["status"] == "succeeded", (
            f"EP-10 reads the record: {bodies['EP-10']}"
        )
        assert bodies["EP-02"]["lock"]["state"] == "none", f"no lock is held: {bodies['EP-02']}"

        # 書き込みは行われていない: N は登録されず、S は削除も更新もされていない
        expect_error(api.get_source(unregistered.source_id), 404, "source_config_not_found")
        assert bodies["EP-02"]["status"] == "active", f"S must stay active: {bodies['EP-02']}"
        assert opensearch.count_source_documents(stored.source_id) == 1, "S's document must stay"
        assert opensearch.fetch_lock(stored.source_id) is None, "no job may have been queued"

    # 3. 復旧: EP-13 が normal に戻る
    states = wait_for_components_normal(api, ("crawler", "indexer", "opensearch", "api"))
    assert_optional_components_not_configured(states)

    # 4. 復旧後のクロール
    stored.write("second.md", b"# second\n\ntext of second\n")
    run_crawl(api, opensearch, stored.source_id)
    detail = wait_for_source_detail(
        api,
        stored.source_id,
        lambda body: body["index"]["document_count"] == 2,
        what="EP-02 counting both documents after the recovery",
    )
    assert detail["lock"]["state"] == "none", f"the lock must be released: {detail['lock']}"


def test_indexer_down_keeps_the_api_alive_and_fails_the_crawl_and_the_deletion_until_recovery(
    api: AdminApi,
    opensearch: OpenSearchProbe,
    compose_control: ComposeControl,
    registered_source: SourceDirectory,
    make_registered_source: Callable[..., SourceDirectory],
) -> None:
    """【何を確認するか】(AIT-91)
    Indexer が止まっている間も、api の読み取りと操作は影響を受けず(EP-13 の `indexer` だけが
    `abnormal`)、止まっている間に始めたクロール・ソース削除は Crawler の側で終端(失敗)になること。
    失敗したソース削除は `status=deleting` を残し、起動・更新が 409 `source_deleting` になること。
    Indexer を戻した後、ソース削除の再実行(EP-05)・クロールの再実行(EP-06)が成功し、失敗していた古い
    クロールのジョブが再実行できない(`superseded`)に変わること。

    【前提と手順】
    前提: 登録済みの 2 つのソース。C(クロール用。md 1 件。未クロール)と D(削除用。md 2 件をクロール済み)。
    手順:
      1. Indexer を止める(`stopped`)。
      2. EP-13 と、EP-01・02・09・10・11・12・14 を読む。
      3. (a) C のクロール(EP-06)を起動し、終端まで待つ。EP-10・02 を読む。
      4. (b) D の削除(EP-05)を起動し、終端まで待つ。EP-01・02・04・06・03(同じ内容)・11 を呼ぶ。
      5. Indexer を起動し直し(区間を抜ける)、healthy を待つ。
      6. (c) D の削除(EP-05)と C のクロール(EP-06)を再び起動し、終端まで待つ。EP-02・11・01・10 を読む。

    【期待する結果とその根拠】
    - 手順 2: EP-13 は `indexer` が `abnormal`(`reason` は `connection_refused` か `name_not_resolved`)、
      `crawler`・`opensearch`・`api`・`web` が `normal`(B 10.2)。読み取りの EP は 200。
    - 手順 3(a): 起動(EP-06)は受け付けられる(202。受付は Indexer を呼ばないため。B 10.2)。ジョブは
      Indexer に届かず `failed`(`failure_reason=indexer_unavailable`、`failure_detail` は「Indexer が
      応答しない」を含む。crawler-architecture 7.8)になり、ロックは解放され(EP-02 の `lock.state=none`、
      `last_crawl` はこのジョブ)、`rerunnable=true`・`latest_for_source=true`(B 2.9)。
    - 手順 4(b): 202 で受け付けられ、ジョブは `failed`(`failure_reason=indexer_unavailable`、
      `failure_detail` は「Indexer が応答しない」を含む。順 1 の Indexer の呼び出しが尽きる。
      crawler-architecture 8.1)。D の文書は消えず(2 件)、設定は `deleting` で残る(8.1)。EP-01・02 は
      `status=deleting`・`delete_job` が失敗したジョブ、EP-02 の `lock.state=none`(ロックは解放済み)。EP-04・06 は
      409 `source_deleting`、同じ内容の EP-03 は 409 `source_already_exists`(`details.status=deleting`。
      B 3.3)、EP-11 は 200。
    - 手順 6(c): どちらも `succeeded`。D は EP-02・11 が 404、EP-01 の行・文書・設定がなくなる(8.3 の
      再実行)。C は文書 1 件。手順 3 の失敗ジョブは `rerunnable=false`・`rerun_blocked_reason=superseded`
      (最新の `crawl` ではなくなった。B 2.9)。

    【単体テストでは確認できず実機で確認する点】
    実コンテナの停止での Crawler の失敗の終わり方(`failure_reason`、リトライの尽きる時間、ロックの
    解放)、失敗したソース削除の中間状態(`deleting` と文書の残り)、Indexer 再起動後の再実行での完了。
    """
    crawl_source = registered_source
    delete_source = make_registered_source("deletion")
    crawl_source.write("c1.md", b"# c1\n\ntext of c1\n")
    delete_source.write("d1.md", b"# d1\n\ntext of d1\n")
    delete_source.write("d2.md", b"# d2\n\ntext of d2\n")
    first_delete_crawl = run_crawl(api, opensearch, delete_source.source_id)
    assert opensearch.count_source_documents(delete_source.source_id) == 2, (
        "D must have 2 documents"
    )

    with compose_control.stopped("indexer"):
        # 2. api への影響は EP-13 の indexer だけ
        states = fetch_component_states(api)
        reason = assert_component_down(states, "indexer")
        observed("AIT-91 EP-13 indexer reason", reason)
        assert_components_normal(states, ("crawler", "opensearch", "api", "web"))
        assert_optional_components_not_configured(states)
        reads = {
            "EP-01": api.list_sources(),
            "EP-02": api.get_source(crawl_source.source_id),
            "EP-09": api.list_jobs(source_id=crawl_source.source_id),
            "EP-10": api.get_job(first_delete_crawl["job_id"]),
            "EP-11": api.list_documents(crawl_source.source_id, tab="extract_failed"),
            "EP-12": api.opensearch_cluster(),
            "EP-14": api.meta(),
        }
        for response in reads.values():
            expect_json(response, 200)

        # 3. (a) 停止中に始めたクロール
        crawl_job_id = expect_json(api.start_crawl(crawl_source.source_id), 202)["job_id"]
        crawl_job = wait_for_job_terminal(api, crawl_job_id)
        wait_for_lock_released(opensearch, crawl_source.source_id)
        observed(
            "AIT-91 (a) crawl job",
            {
                "status": crawl_job["status"],
                "failure_reason": crawl_job["failure_reason"],
                "failure_detail": crawl_job["failure_detail"],
                "rerunnable": crawl_job["rerunnable"],
            },
        )
        assert crawl_job["status"] == "failed", f"the crawl cannot reach the Indexer: {crawl_job}"
        assert crawl_job["failure_reason"] == "indexer_unavailable", (
            f"the failure must be told as indexer_unavailable: {crawl_job}"
        )
        assert "Indexer が応答しない" in crawl_job["failure_detail"], (
            f"failure_detail must say the Indexer did not respond: {crawl_job}"
        )
        assert crawl_job["rerunnable"] is True, f"a failed latest crawl is rerunnable: {crawl_job}"
        assert crawl_job["rerun_blocked_reason"] is None, f"must not be blocked: {crawl_job}"
        assert crawl_job["latest_for_source"] is True, f"must be the latest: {crawl_job}"
        crawl_detail = wait_for_source_detail(
            api,
            crawl_source.source_id,
            lambda body: (
                body["last_crawl"] is not None and body["last_crawl"]["status"] == "failed"
            ),
            what="EP-02 showing the failed crawl",
        )
        assert crawl_detail["last_crawl"]["job_id"] == crawl_job_id, (
            f"last_crawl must be the failed job: {crawl_detail}"
        )
        assert crawl_detail["lock"]["state"] == "none", (
            f"the failed job released the lock: {crawl_detail['lock']}"
        )

        # 4. (b) 停止中に始めたソース削除
        delete_job_id = expect_json(api.start_source_delete(delete_source.source_id), 202)["job_id"]
        delete_job = wait_for_job_terminal(api, delete_job_id)
        wait_for_lock_released(opensearch, delete_source.source_id)
        observed(
            "AIT-91 (b) delete job",
            {
                "status": delete_job["status"],
                "failure_reason": delete_job["failure_reason"],
                "failure_detail": delete_job["failure_detail"],
                "rerun_blocked_reason": delete_job["rerun_blocked_reason"],
            },
        )
        assert delete_job["status"] == "failed", (
            f"the deletion cannot reach the Indexer: {delete_job}"
        )
        assert delete_job["failure_reason"] == "indexer_unavailable", (
            f"the failure must be told as indexer_unavailable: {delete_job}"
        )
        assert "Indexer が応答しない" in delete_job["failure_detail"], (
            f"failure_detail must say the Indexer did not respond: {delete_job}"
        )

        assert opensearch.count_source_documents(delete_source.source_id) == 2, (
            "D's documents must stay (the Indexer could not delete them)"
        )
        row = wait_for_source_row(
            api,
            delete_source.source_id,
            lambda listed: (
                listed["status"] == "deleting"
                and listed["delete_job"] is not None
                and listed["delete_job"]["status"] == "failed"
            ),
            what="EP-01 showing D as deleting with its failed delete_job",
        )
        assert row["delete_job"]["job_id"] == delete_job_id, (
            f"delete_job must be the failed job: {row}"
        )
        assert row["delete_job"]["status"] == "failed", f"delete_job must be failed: {row}"
        # EP-02 の `delete_job` は検索で読むので、反映を待つ(`status` は ID 指定で即時)
        detail = wait_for_source_detail(
            api,
            delete_source.source_id,
            lambda body: (
                body["delete_job"] is not None and body["delete_job"]["status"] == "failed"
            ),
            what="EP-02 showing D's failed delete_job",
        )
        assert detail["status"] == "deleting", f"EP-02 must show deleting: {detail}"
        assert detail["delete_job"]["job_id"] == delete_job_id, f"delete_job must match: {detail}"
        assert detail["lock"]["state"] == "none", (
            f"the failed job released the lock: {detail['lock']}"
        )
        expect_error(
            api.update_source(delete_source.source_id, settings_for_update(delete_source)),
            409,
            "source_deleting",
            expected_retryable=False,
        )
        expect_error(
            api.start_crawl(delete_source.source_id),
            409,
            "source_deleting",
            expected_retryable=False,
        )
        already_exists = expect_error(
            api.register_source(source_settings(delete_source)),
            409,
            "source_already_exists",
            expected_retryable=False,
        )
        assert already_exists["details"] == {"status": "deleting"}, (
            f"details.status must be deleting: {already_exists}"
        )
        expect_json(api.list_documents(delete_source.source_id, tab="extract_failed"), 200)

    # 5. 復旧
    wait_for_components_normal(api, ("crawler", "indexer", "opensearch", "api"))

    # 6. (c) 再実行
    retried_delete_id = expect_json(api.start_source_delete(delete_source.source_id), 202)["job_id"]
    rerun_crawl_id = expect_json(api.start_crawl(crawl_source.source_id), 202)["job_id"]
    retried_delete = wait_for_job_terminal(api, retried_delete_id)
    rerun_crawl = wait_for_job_terminal(api, rerun_crawl_id)
    wait_for_lock_released(opensearch, delete_source.source_id)
    wait_for_lock_released(opensearch, crawl_source.source_id)
    assert retried_delete["status"] == "succeeded", (
        f"the deletion rerun must succeed: {retried_delete['status']} "
        f"{retried_delete['failure_reason']} {retried_delete['failure_detail']}"
    )
    assert rerun_crawl["status"] == "succeeded", (
        f"the crawl rerun must succeed: {rerun_crawl['status']} "
        f"{rerun_crawl['failure_reason']} {rerun_crawl['failure_detail']}"
    )

    expect_error(api.get_source(delete_source.source_id), 404, "source_config_not_found")
    expect_error(
        api.list_documents(delete_source.source_id, tab="extract_failed"),
        404,
        "source_config_not_found",
    )
    wait_for_source_listing(
        api,
        lambda body: delete_source.source_id not in {item["source_id"] for item in body["items"]},
        what=f"EP-01 no longer listing {delete_source.source_id}",
    )
    assert opensearch.count_source_documents(delete_source.source_id) == 0, "D's documents are gone"
    assert opensearch.fetch_source_config(delete_source.source_id) is None, "D's settings are gone"
    crawled = wait_for_source_detail(
        api,
        crawl_source.source_id,
        lambda body: body["index"]["document_count"] == 1,
        what="EP-02 counting C's document",
    )
    assert crawled["status"] == "active", f"C must stay active: {crawled}"

    # `latest_for_source` は検索で読むので、再実行のクロールが反映されるまで待つ
    superseded = poll_until(
        lambda: expect_json(api.get_job(crawl_job_id), 200),
        lambda job: job["latest_for_source"] is False,
        timeout_secs=READ_LAG_TIMEOUT_SECONDS,
        poll_interval_secs=READ_LAG_POLL_INTERVAL_SECONDS,
        what="EP-10 no longer marking the failed crawl as the latest",
    )
    assert (
        superseded["status"],
        superseded["latest_for_source"],
        superseded["rerunnable"],
        superseded["rerun_blocked_reason"],
    ) == ("failed", False, False, "superseded"), (
        f"the failed crawl must be superseded by the rerun: {superseded}"
    )


def test_opensearch_down_fails_the_reads_and_the_crawl_and_everything_recovers(
    api: AdminApi,
    opensearch: OpenSearchProbe,
    compose_control: ComposeControl,
    registered_source: SourceDirectory,
) -> None:
    """【何を確認するか】(AIT-92)
    OpenSearch が止まっている間、OpenSearch を読む EP-01・02・09・10・11・12 が 503 `unavailable`
    (`retryable=true`)になり、設定だけの EP-14 と `/healthz` は 200 のままであること。EP-13 は
    `opensearch` が `abnormal`、`api` が `normal` であること。EP-06 は OpenSearch に依存する Crawler が
    失敗するため 503 になること。OpenSearch を戻した後、4 つのサービスが healthy になり、読み取りと
    クロールが成功すること。

    【前提と手順】
    前提: 登録済みのソース S(md 1 件をクロール済み)。
    手順:
      1. OpenSearch を止める(`stopped`)。
      2. EP-01・02・09・10・11・12 と EP-13・14・`/healthz` を呼ぶ。EP-06 を呼ぶ。
      3. OpenSearch を起動し直し(区間を抜ける)、opensearch・indexer・crawler・api の healthy を待つ。
      4. EP-01 が 200 に戻り、EP-13 が `normal` に戻るのを待つ。md を足して EP-06 でクロールする。

    【期待する結果とその根拠】
    - 手順 2: EP-01・02・09・10・11・12 は 503 `unavailable`・`retryable=true`(B 2.2・10.2)。EP-13 は
      `opensearch` が `abnormal`(`reason` は `connection_refused` か `name_not_resolved`)、`api`・`web` が
      `normal`(`crawler`・`indexer` の見え方は記録する。B 10.2 は「他は通常」)。EP-14・`/healthz` は 200。
      EP-06 は 503 `crawler_unavailable`(Crawler が Store 層の障害を返した)か `crawler_unreachable`
      (B 10.2。どちらかを記録する)で `retryable=true`。
    - 手順 4: EP-13 の 4 つが `normal`。クロールは `succeeded` で、文書が 2 件になる(停止前の
      データが残り、再起動後の OpenSearch へ Indexer が書けた)。

    【単体テストでは確認できず実機で確認する点】
    実 OpenSearch の停止で api が受ける接続の失敗の分類(EP-13 の `reason`、503 `unavailable`)、
    OpenSearch に依存する Crawler・Indexer の失敗と、再起動後の復旧(api・Crawler・Indexer の再接続)。
    """
    stored = registered_source
    stored.write("first.md", b"# first\n\ntext of first\n")
    first_crawl = run_crawl(api, opensearch, stored.source_id)
    wait_for_source_row(
        api,
        stored.source_id,
        lambda row: row["document_count"] == 1,
        what="EP-01 counting the first document",
    )

    with compose_control.stopped("opensearch"):
        # 2. OpenSearch を読む EP は 503
        reads = {
            "EP-01": api.list_sources(),
            "EP-02": api.get_source(stored.source_id),
            "EP-09": api.list_jobs(source_id=stored.source_id),
            "EP-10": api.get_job(first_crawl["job_id"]),
            "EP-11": api.list_documents(stored.source_id, tab="extract_failed"),
            "EP-12": api.opensearch_cluster(),
        }
        for response in reads.values():
            expect_error(response, 503, "unavailable", expected_retryable=True)

        states = fetch_component_states(api)
        reason = assert_component_down(states, "opensearch")
        observed("AIT-92 EP-13 opensearch reason", reason)
        observed(
            "AIT-92 EP-13 crawler / indexer",
            {
                name: (states[name]["state"], states[name]["reason"])
                for name in ("crawler", "indexer")
            },
        )
        assert_components_normal(states, ("api", "web"))
        assert_optional_components_not_configured(states)
        meta = expect_json(api.meta(), 200)
        assert meta["cron_timezone"] == "Asia/Tokyo", f"EP-14 needs no other component: {meta}"
        assert expect_json(api.healthz(), 200) == {"status": "ok"}

        crawl_error = expect_json(api.start_crawl(stored.source_id), 503)["error"]
        observed("AIT-92 EP-06 error code", crawl_error["code"])
        assert crawl_error["code"] in {"crawler_unavailable", "crawler_unreachable"}, (
            f"EP-06 must fail as a Crawler failure: {crawl_error}"
        )
        assert crawl_error["retryable"] is True, f"EP-06 must be retryable: {crawl_error}"

    # 3. 復旧(`stopped` が 4 つのサービスの healthy を待つ)。4. 読み取りが 200 に戻る
    poll_until(
        api.list_sources,
        lambda response: response.status_code == 200,
        timeout_secs=COMPONENT_RECOVERY_TIMEOUT_SECONDS,
        poll_interval_secs=COMPONENT_RECOVERY_POLL_INTERVAL_SECONDS,
        what="EP-01 answering 200 again",
    )
    wait_for_components_normal(api, ("crawler", "indexer", "opensearch", "api"))
    expect_json(api.list_sources(), 200)

    stored.write("second.md", b"# second\n\ntext of second\n")
    run_crawl(api, opensearch, stored.source_id)
    wait_for_source_detail(
        api,
        stored.source_id,
        lambda body: body["index"]["document_count"] == 2,
        what="EP-02 counting both documents after the recovery",
    )
