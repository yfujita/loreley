"""AIT-60: データソースの削除(EP-05 と、実行待ち・完了後の EP-01・02・06・07・08・10・11)。

目的:
    別のソースのクロールが実行中のときに起動したソース削除ジョブ(EP-05)について、実行待ちの間の
    ロック(`held_delete`)と、起動・取消・解放の拒否(409)を確かめ、完了後に、そのソースの文書・
    記録・設定が実際に消え、他のソースは残ることを確かめる。
    単体テストでは、実 Crawler が行うソース削除(Indexer の文書削除 → スキップ・原本サイズ超過記録の
    削除 → 削除記録の削除 → 設定の削除 → ロックの削除)の結果を確認できない。

参照する設計書の章:
    - admin-api-v0.1.md 2.3・2.7(`lock_held`・`job_not_cancellable`)、2.9(`held_delete`)、
      3.1・3.2(EP-01・02)、3.5(EP-05)、4.2・4.3(EP-07・08)、5.2(EP-10)、6.1(EP-11)
    - crawler-architecture-v0.4.md 8.1(ソース削除の手順)

扱うシナリオ: AIT-60

窓について:
    Job Runner は直列なので、別のソース Z のクロールが実行中(ロックを持つ約 10 秒)の間に起動した削除
    ジョブは、Z が終わるまで `queued` のままロックを持つ。Z が `running` になったことを観測してから
    EP-05 を呼び、窓を見逃したときは見逃したことが分かるメッセージで失敗する(support.py)。
    削除が終わった後の検索の反映(EP-01)は最大約 1 秒遅れる(AAA-P-6)ので、上限つきで待つ。
"""

from collections.abc import Callable

from support import (
    AdminApi,
    OpenSearchProbe,
    SourceDirectory,
    expect_error,
    expect_json,
    run_crawl,
    wait_for_job_running,
    wait_for_job_terminal,
    wait_for_lock_released,
    wait_for_source_detail,
    wait_for_source_listing,
)

# compose.test.yaml の `MAX_RAW_BYTES`(65,536 バイト)を超える大きさ(原本サイズ超過の記録を作る)。
OVERSIZE_FILE_BYTES = 70_000


def test_source_delete_queued_behind_a_running_crawl_removes_only_that_source(
    api: AdminApi,
    opensearch: OpenSearchProbe,
    registered_source: SourceDirectory,
    make_registered_source: Callable[..., SourceDirectory],
) -> None:
    """【何を確認するか】(AIT-60)
    別のソース Z のクロール実行中に起動したソース S の削除ジョブが、実行待ちの間は S のロックを
    `held_delete` で持ち(起動・取消・解放は 409)、Z の終了後に実行されて、S の文書・原本サイズ超過記録・
    削除記録・設定が消え、Z の文書は残ること。

    【前提と手順】
    前提: 登録済みの S(md 2 件・上限超過のファイル 1 件をクロール済み)と Z(md 2 件をクロール済み)。
    手順:
      1. Z のクロールを再び起動し、`running` を観測する。
      2. EP-05 で S の削除を起動する(202)。EP-02(S)・EP-06(S)・EP-07(削除ジョブ)・EP-08(S)を呼ぶ。
      3. Z と削除ジョブの終了とロックの解放を待つ。
      4. EP-10(削除ジョブ)・EP-02・EP-11・EP-01・EP-08 の S と、OpenSearch の S・Z の実データを読む。

    【期待する結果とその根拠】
    - 手順 2: 202 `{job_type: source_delete, status: queued, trigger: manual, force_delete: null,
      rewrite_mode: null}`(B 3.5)。EP-02 の S は `lock.state=held_delete`・`lock.job` が削除ジョブ
      (`queued`)で、設定の `status` は `active` のまま(`deleting` になるのは実行開始から。
      crawler-architecture 8.1 の順 0)。EP-06 は 409 `lock_held`(`existing_job` が削除ジョブ・
      `job_type=source_delete`、`lock_state=held_delete`)、EP-07 は 409 `job_not_cancellable`(B 4.2)、
      EP-08 は 409 `lock_in_use`(`lock_state=held_delete`。B 4.3)。
    - 手順 4: 削除ジョブは `succeeded`(EP-10 の `job_type=source_delete`・`registration=null`・
      `deletion=null`・`rerun_blocked_reason=not_crawl`)。S の EP-02・EP-11 は 404
      `source_config_not_found`、EP-01 に S の行はなく、EP-08 は `released=false`(ロックは削除ジョブが
      自分で消した)。OpenSearch から、S の文書・原本サイズ超過記録・削除記録・設定が消え、Z の文書は
      Z のクロール前と同じ件数で残り、EP-02 の Z の `document_count` も同じ(B 3.5・crawler-architecture 8.1)。
      ※ S のジョブ記録は、ソース削除では消えない(crawler-architecture 8.1 の順 3)ので、削除ジョブも、
      S の過去のクロールのジョブも、EP-10 で 200 で読め、`loreley-jobs` にも残る。
      ※ スキップ記録の削除(8.1 の順 2)は、このテストではスキップ記録を作らないので未検証のまま
      (実 Crawler にスキップを起こさせられない。AIT-41 と同じ理由)。

    【単体テストでは確認できず実機で確認する点】
    実 Crawler・実 Indexer によるソース削除の全手順(文書・記録・設定の実際の削除)、実行待ちの削除ジョブが
    持つロックの `lock_state` の導出と、それに対する実 Crawler の 409。
    """
    doomed = registered_source
    bystander = make_registered_source("bystander")
    doomed.write("keep1.md", b"# keep1\n\ntext of keep1\n")
    doomed.write("keep2.md", b"# keep2\n\ntext of keep2\n")
    doomed.write("big.txt", b"x" * OVERSIZE_FILE_BYTES)
    bystander.write("z1.md", b"# z1\n\ntext of z1\n")
    bystander.write("z2.md", b"# z2\n\ntext of z2\n")

    doomed_crawl = run_crawl(api, opensearch, doomed.source_id)
    run_crawl(api, opensearch, bystander.source_id)
    assert opensearch.count_source_documents(doomed.source_id) == 2, "S must have 2 documents"
    assert len(opensearch.oversize_records(doomed.source_id)) == 1, "S must have an oversize record"
    assert opensearch.fetch_deletion_result(doomed_crawl["job_id"]) is not None, (
        "S's crawl must have left a deletion result"
    )
    bystander_document_count = opensearch.count_source_documents(bystander.source_id)
    assert bystander_document_count == 2, "Z must have 2 documents"

    # 1. Z のクロールを再び起動し、実行中(ロックを持つ窓)を観測する
    running_crawl_id = expect_json(api.start_crawl(bystander.source_id), 202)["job_id"]
    wait_for_job_running(api, running_crawl_id)

    # 2. 窓の中で S の削除を起動する。Job Runner が Z で塞がっているので、実行待ちになる
    accepted = expect_json(api.start_source_delete(doomed.source_id), 202)
    delete_job_id = accepted["job_id"]
    assert (
        accepted["job_type"],
        accepted["status"],
        accepted["trigger"],
        accepted["force_delete"],
        accepted["rewrite_mode"],
        accepted["source_id"],
    ) == ("source_delete", "queued", "manual", None, None, doomed.source_id), (
        f"EP-05 must accept the deletion as queued: {accepted}"
    )

    held = expect_json(api.get_source(doomed.source_id), 200)
    assert held["lock"]["state"] == "held_delete", (
        f"the deletion must hold the lock: {held['lock']}"
    )
    assert (held["lock"]["job"]["job_id"], held["lock"]["job"]["status"]) == (
        delete_job_id,
        "queued",
    ), f"lock.job must be the queued deletion: {held['lock']}"
    assert held["status"] == "active", f"the source is not deleting until the job runs: {held}"

    crawl_refused = expect_error(
        api.start_crawl(doomed.source_id), 409, "lock_held", expected_retryable=False
    )
    existing_job = crawl_refused["details"]["existing_job"]
    assert (existing_job["job_id"], existing_job["job_type"]) == (delete_job_id, "source_delete"), (
        f"existing_job must be the deletion: {crawl_refused['details']}"
    )
    assert crawl_refused["details"]["lock_state"] == "held_delete", (
        f"lock_state must be held_delete: {crawl_refused['details']}"
    )
    expect_error(
        api.cancel_job(delete_job_id), 409, "job_not_cancellable", expected_retryable=False
    )
    release_refused = expect_error(
        api.release_lock(doomed.source_id), 409, "lock_in_use", expected_retryable=False
    )
    assert release_refused["details"]["lock_state"] == "held_delete", (
        f"lock_state must be held_delete: {release_refused['details']}"
    )

    # 3. Z のクロール、続いて削除ジョブが終わるのを待つ
    bystander_crawl = wait_for_job_terminal(api, running_crawl_id)
    assert bystander_crawl["status"] == "succeeded", (
        f"Z's crawl must succeed: {bystander_crawl['status']} {bystander_crawl['failure_reason']}"
    )
    delete_job = wait_for_job_terminal(api, delete_job_id)
    wait_for_lock_released(opensearch, doomed.source_id)
    wait_for_lock_released(opensearch, bystander.source_id)

    # 4. 完了後: EP-10・EP-02・EP-11・EP-08 の S
    assert delete_job["status"] == "succeeded", (
        f"the deletion must succeed: {delete_job['status']} {delete_job['failure_reason']} "
        f"{delete_job['failure_detail']}"
    )
    assert (delete_job["job_type"], delete_job["source_id"]) == ("source_delete", doomed.source_id)
    assert (delete_job["registration"], delete_job["deletion"]) == (None, None), (
        f"a deletion job has neither registration nor deletion result: {delete_job}"
    )
    assert (delete_job["rerunnable"], delete_job["rerun_blocked_reason"]) == (False, "not_crawl"), (
        f"only crawl jobs are rerun by EP-06: {delete_job}"
    )
    expect_error(api.get_source(doomed.source_id), 404, "source_config_not_found")
    expect_error(
        api.list_documents(doomed.source_id, tab="skipped"), 404, "source_config_not_found"
    )
    gone = expect_json(api.release_lock(doomed.source_id), 200)
    assert gone == {"source_id": doomed.source_id, "released": False, "failed_job_id": None}, (
        f"the deletion job must have released the lock itself: {gone}"
    )
    # EP-01 は検索で読むので、削除の反映を待つ
    listing = wait_for_source_listing(
        api,
        lambda body: doomed.source_id not in {item["source_id"] for item in body["items"]},
        what=f"EP-01 no longer listing {doomed.source_id}",
    )
    listed_ids = {item["source_id"] for item in listing["items"]}
    assert bystander.source_id in listed_ids, "Z must stay listed"

    # ジョブ記録はソース削除で消えない: S の過去のクロールも、削除ジョブも、EP-10 と直接読みで残る
    past_crawl = expect_json(api.get_job(doomed_crawl["job_id"]), 200)
    assert (past_crawl["job_type"], past_crawl["source_id"], past_crawl["status"]) == (
        "crawl",
        doomed.source_id,
        "succeeded",
    ), f"S's past crawl must stay readable after the source is deleted: {past_crawl}"
    for job_id in (doomed_crawl["job_id"], delete_job_id):
        assert opensearch.fetch_job(job_id) is not None, f"job record {job_id} must stay"

    # OpenSearch の実データ: S の文書・記録・設定は消え、Z は残る
    assert opensearch.count_source_documents(doomed.source_id) == 0, "S's documents must be gone"
    assert opensearch.oversize_records(doomed.source_id) == [], "S's oversize records must be gone"
    assert opensearch.fetch_deletion_result(doomed_crawl["job_id"]) is None, (
        "S's deletion records must be gone"
    )
    assert opensearch.fetch_source_config(doomed.source_id) is None, "S's settings must be gone"
    assert opensearch.fetch_lock(doomed.source_id) is None, "S's lock must be gone"
    assert opensearch.count_source_documents(bystander.source_id) == bystander_document_count, (
        "Z's documents must stay"
    )
    bystander_detail = wait_for_source_detail(
        api,
        bystander.source_id,
        lambda body: body["index"]["document_count"] == bystander_document_count,
        what="EP-02 counting Z's documents",
    )
    assert bystander_detail["status"] == "active", f"Z must stay active: {bystander_detail}"
