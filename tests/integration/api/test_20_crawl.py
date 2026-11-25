"""AIT-20・AIT-21: クロールの起動から完了まで(EP-06 と、実行中・完了後の EP-01・02・05・08・09・10)。

目的:
    Admin API の EP-06 で起動したクロールが、実 Crawler・実 Indexer・実 OpenSearch の上で最後まで
    進み、その間と終了後の状態を、各 EP が正しく返すことを確かめる。
      - AIT-20: 実行中の窓(ジョブがロックを持つ間)で、ロックの状態・実行中ジョブの一覧・起動の競合
        (409 `lock_held`・`lock_in_use`)を確かめ、終了後にジョブ詳細・ロック・一覧が更新されること
      - AIT-21: `force_delete=true`・`rewrite_mode=true` が Crawler・Indexer まで中継され、割合ルールで
        止まった削除が、強制削除で実行されること
    単体テストでは、実行中のロックの状態(実際にリースを持つジョブ)、実 Indexer が返す削除結果、
    実時間での TTL の経過を確認できない。

参照する設計書の章:
    - admin-api-v0.1.md 2.7(`lock_held`)、2.9(`lock_state`・導出フラグ)、3.1・3.2(EP-01・02)、
      3.5(EP-05)、4.1・4.3(EP-06・08)、5.1・5.2(EP-09・10)
    - crawler-architecture-v0.4.md 4.5(ジョブの実行)、5.1(ロック)、7.5〜7.7(終了通知・削除結果の確認)
    - indexer-architecture-v0.10.md 9.2(強制削除モード)、9.3(割合ルール)、9.7(削除判定の順序)

扱うシナリオ: AIT-20(実行中と完了後の状態)、AIT-21(`force_delete`・`rewrite_mode` の中継)

検索で読む EP(EP-01・09 と、EP-02 の最終クロール・文書数)は、書き込みの反映が最大約 1 秒遅れる
(admin-api-architecture AAA-P-6)。ID 指定で読む EP-10・ロック(EP-02 の `lock`)は即時なので、
検索で読む値は、期待する状態になるまで上限つきで待ってから確認する。

窓について:
    Crawler は終了通知の直後に Indexer の削除結果を 1 回読み、その後ポーリング間隔(compose.test.yaml で
    10 秒)ごとに読む。ジョブはその間ロックを持つので、HTTP 数回の操作は窓に収まる。操作の前に
    `running` を観測し、窓を見逃したときは、見逃したことが分かるメッセージで失敗する(support.py)。
"""

from datetime import datetime
from typing import Any

from support import (
    READ_LAG_POLL_INTERVAL_SECONDS,
    READ_LAG_TIMEOUT_SECONDS,
    AdminApi,
    OpenSearchProbe,
    SourceDirectory,
    expect_error,
    expect_json,
    parse_instant,
    poll_until,
    register_source,
    run_crawl,
    wait_for_job_running,
    wait_for_job_terminal,
    wait_for_lock_released,
    wait_for_source_detail,
    wait_for_source_row,
    wait_until_expired,
)

# AIT-21: TTL。期限切れの文書を作るために、実時間でこの時間を待つ(直接書き込みはしない)。更新した文書の
# `last_seen_at` はクロールの開始時刻で、削除の判定はその直後(終了通知の受理で起床する。実測 1 秒前後。
# 走査は最大 5 秒)に行われる。更新した文書が判定までに期限切れにならない長さにする。
FORCE_DELETE_TTL_SECONDS = 15
# AIT-21: 割合ルールのしきい値(%)。削除対象 2 件 ÷ 文書 4 件 = 50% が、これを超える。
FORCE_DELETE_RATIO_THRESHOLD_PERCENT = 10


def test_crawl_holds_the_lock_while_running_and_updates_the_states_when_finished(
    api: AdminApi, opensearch: OpenSearchProbe, registered_source: SourceDirectory
) -> None:
    """【何を確認するか】(AIT-20)
    EP-06 で起動したクロールが、実行中はロックを持ち(EP-02 `held_crawl`、EP-09 の実行中ジョブ、
    起動・削除・解放の 409)、`succeeded` で終わると、ジョブ詳細(EP-10)・ロック(EP-02)・一覧(EP-01)が
    終了後の状態になること。

    【前提と手順】
    前提: 登録済みのソースに md ファイル 3 つ。
    手順:
      1. EP-06 を呼ぶ(202)。EP-10 で `running` を観測する。
      2. 実行中に、EP-02・EP-09(`status=active`)・EP-06(`force_delete=true` つきで再送)・EP-05・EP-08 を呼ぶ。
      3. ジョブの終了とロックの解放を待つ。
      4. EP-10・EP-02・EP-01 を読み、`loreley-jobs`・検索インデックスと突き合わせる。

    【期待する結果とその根拠】
    - 手順 1: 202。`job_type=crawl`・`status=queued`・`trigger=manual`・`force_delete=false`・
      `rewrite_mode=false`(admin-api 4.1)。
    - 手順 2(実行中): EP-02 は `lock.state=held_crawl`・`lock.job` がこのジョブ(`status=running`)・
      `last_crawl` がこのジョブ。EP-09 の `active` は、このジョブだけ(`stalled=false`・
      `cancellable=true`。2.9)。EP-06 は 409 `lock_held`(`options_applied=false`、`requested` は送った
      指定、`existing_job` はこのジョブ、`lock_state=held_crawl`。2.7)。EP-05 も 409 `lock_held` で、
      `options_applied`・`requested` は含まない(3.5)。EP-08 は 409 `lock_in_use`(`existing_job`・
      `lock_state=held_crawl`。4.3)。
    - 手順 4(終了後): EP-10 は `succeeded`・`registration` が 3 件作成(`phase=final`)・
      `deletion.confirmation=confirmed`・削除結果は `deleted`(削除 0 件)・`latest_for_source=true`・
      `rerunnable=false`(`not_failed`)・`stalled=false`・`cancellable=false`。`loreley-jobs` の
      ジョブ記録と同じ値(状態・登録件数)。EP-02 は `lock.state=none`・`last_crawl`・
      `last_completed_at`(ジョブの `finished_at`)・`index.document_count=3`。EP-01 のこの行は、
      同じ `last_crawl`・`document_count=3`。件数は検索インデックスを直接読んだ値と一致する。

    【単体テストでは確認できず実機で確認する点】
    実 Crawler が実際にロックとリースを持つ間の `lock_state` の導出(`loreley-jobs` のロック文書と
    ジョブ記録の実物)、実 Crawler が返す 409 の `existing_job`、実 Indexer の削除結果の形、
    終了後に Job Runner がロックを解放すること。
    """
    source_id = registered_source.source_id
    for name in ("alpha.md", "beta.md", "gamma.md"):
        registered_source.write(name, f"# {name}\n\ntext of {name}\n".encode())

    # 1. 起動して、running を観測する(窓が開いたことの確認)
    accepted = expect_json(api.start_crawl(source_id), 202)
    job_id = accepted["job_id"]
    assert (accepted["job_type"], accepted["status"], accepted["trigger"]) == (
        "crawl",
        "queued",
        "manual",
    ), f"EP-06 must accept a manual crawl as queued: {accepted}"
    assert (accepted["source_id"], accepted["force_delete"], accepted["rewrite_mode"]) == (
        source_id,
        False,
        False,
    ), f"the options must default to false: {accepted}"
    wait_for_job_running(api, job_id)

    # 2. 実行中の状態と、起動・削除・解放の競合
    _assert_held_by_the_running_crawl(api, source_id, job_id)

    # 3. 終了とロックの解放を待つ
    job = wait_for_job_terminal(api, job_id)
    wait_for_lock_released(opensearch, source_id)

    # 4. 終了後の EP-10
    assert job["status"] == "succeeded", (
        f"the crawl must succeed: {job['status']} {job['failure_reason']} {job['failure_detail']}"
    )
    assert (job["job_type"], job["trigger"], job["failure_reason"]) == ("crawl", "manual", None)
    assert (job["stalled"], job["cancellable"], job["lease_expires_at"]) == (False, False, None), (
        f"a finished job is neither stalled nor cancellable: {job}"
    )
    assert (job["latest_for_source"], job["rerunnable"], job["rerun_blocked_reason"]) == (
        True,
        False,
        "not_failed",
    ), f"the latest succeeded job is not rerunnable: {job}"
    assert job["cancel_after_finish_notice"] is False, f"nothing was cancelled: {job}"
    assert job["warnings"] == [], f"no warning is expected: {job['warnings']}"
    registration = job["registration"]
    assert registration == {
        "enumerated_count": 3,
        "created_count": 3,
        "updated_count": 0,
        "unchanged_count": 0,
        "skipped_count": 0,
        "oversize_count": 0,
        "error_count": 0,
        "invalid_id_count": 0,
        "partial": False,
        "phase": "final",
    }, f"the 3 files must all be created and the registration final: {registration}"
    deletion = job["deletion"]
    assert deletion["confirmation"] == "confirmed", f"the deletion must be confirmed: {deletion}"
    assert deletion["current_state"] == "available", f"the result must be readable: {deletion}"
    assert deletion["current"]["status"] == "deleted", f"nothing is expired: {deletion['current']}"
    assert (deletion["current"]["target_count"], deletion["current"]["deleted_count"]) == (0, 0), (
        f"no document is expired: {deletion['current']}"
    )
    assert job["unavailable"] == {}, f"nothing may be unavailable: {job['unavailable']}"

    # loreley-jobs のジョブ記録(Crawler が書いた実物)と、同じ値か
    record = opensearch.fetch_job(job_id)
    assert record is not None, "the job record must exist in loreley-jobs"
    assert record["status"] == job["status"], f"the stored status must match: {record['status']}"
    counts_of_ep10 = {name: value for name, value in registration.items() if name != "phase"}
    assert {name: record["registration"][name] for name in counts_of_ep10} == counts_of_ep10, (
        f"the stored registration must match EP-10: {record['registration']}"
    )

    # 終了後の EP-02・EP-01(件数は検索インデックスの直接読みと一致する)
    indexed_count = opensearch.count_source_documents(source_id)
    assert indexed_count == 3, f"3 documents must be indexed: {indexed_count}"
    # 最終クロール・文書数は検索で読むので、書き込みの反映(最大約 1 秒)を待つ
    detail = wait_for_source_detail(
        api,
        source_id,
        lambda body: (
            body["last_crawl"]["status"] == "succeeded"
            and body["index"]["document_count"] == indexed_count
        ),
        what="EP-02 showing the finished crawl and the indexed count",
    )
    assert detail["lock"] == {"state": "none", "job": None, "acquired_at": None}, (
        f"the lock must be released: {detail['lock']}"
    )
    assert detail["last_crawl"]["job_id"] == job_id, f"last_crawl must be this job: {detail}"
    assert detail["last_crawl"]["status"] == "succeeded", f"last_crawl must be done: {detail}"
    assert detail["last_completed_at"] == job["finished_at"], (
        f"last_completed_at must be the finish time of this job: {detail['last_completed_at']}"
    )
    assert detail["index"]["document_count"] == indexed_count
    row = wait_for_source_row(
        api,
        source_id,
        lambda row: row["last_crawl"] == detail["last_crawl"],
        what=f"EP-01 showing the finished crawl of {source_id}",
    )
    assert row["last_crawl"] == detail["last_crawl"], f"EP-01 must match EP-02: {row}"
    assert (row["last_completed_at"], row["document_count"]) == (
        job["finished_at"],
        indexed_count,
    ), f"EP-01 must show the finished crawl: {row}"
    assert row["unavailable"] == {}, f"the row must have no failure: {row}"


def test_force_delete_and_rewrite_mode_reach_the_indexer_and_delete_what_the_ratio_rule_stopped(
    api: AdminApi, opensearch: OpenSearchProbe, source_directory: SourceDirectory
) -> None:
    """【何を確認するか】(AIT-21)
    通常のクロールでは割合ルールで止まる削除が、`force_delete=true` のクロールでは実行されること。
    `force_delete`・`rewrite_mode` が、EP-06 から Crawler・Indexer まで中継され、ジョブと削除結果に
    現れること。

    【前提と手順】
    前提: TTL 15 秒、割合しきい値 10%、最小件数 0 のソースに md ファイル 4 つ(keep1・keep2・gone1・
    gone2)。実時間で TTL を待つ(OpenSearch への直接書き込みで期限切れを作らない)。
    手順:
      1. クロール A。4 件が登録され、何も削除されない。
      2. gone1・gone2 を消し、gone の `last_seen_at`(= A の開始時刻)から TTL が過ぎるまで待つ。
      3. 通常のクロール B。
      4. `force_delete=true`・`rewrite_mode=true` のクロール C。

    【期待する結果とその根拠】
    - A: `succeeded`。削除は 0 件(更新した文書は TTL の内側。indexer-architecture 9.2)。
    - B: ジョブは `succeeded`(割合ルールで削除しなかったことは、ジョブの status に影響しない。9.3)。
      削除結果は `skipped_by_ratio`・`forced=false`・削除対象 T=2(gone1・gone2)・分母 D=4・
      `deleted_count` は記録なし(null)。T÷D=50% がしきい値 10% を超え、最小件数(0)以下ではないので止まる(9.3 の
      判定 1・2)。EP-01 の `document_count` は 4 のまま。
    - C: 202 の応答に `force_delete=true`・`rewrite_mode=true`。EP-10 の `force_delete`・`rewrite_mode` も
      true。削除結果は `deleted`・`forced=true`・T=2・D=4・`deleted_count=2`(割合ルールを無視する。
      9.2。TTL を過ぎた gone だけが対象で、更新した keep は消えない)。`loreley-deletions` の削除結果に
      `rewrite_mode=true`・`forced=true` が複写されている(9.4)。EP-01 の `document_count` は 2 で、
      検索インデックスには keep1・keep2 だけが残る。

    【単体テストでは確認できず実機で確認する点】
    実 Indexer の割合ルール・強制削除の判断と、`force_delete`・`rewrite_mode` の中継(Admin API →
    Crawler → Indexer の開始通知 → 削除結果)。実時間の TTL の経過による期限切れ。
    """
    source_id = source_directory.source_id
    for name in ("keep1.md", "keep2.md", "gone1.md", "gone2.md"):
        source_directory.write(name, f"# {name}\n\ntext of {name}\n".encode())
    register_source(
        api,
        source_directory,
        ttl_seconds=FORCE_DELETE_TTL_SECONDS,
        ratio_threshold_percent=FORCE_DELETE_RATIO_THRESHOLD_PERCENT,
        min_delete_count=0,
    )
    gone_document_ids = {source_directory.document_id_of(f"gone{n}.md") for n in (1, 2)}
    kept_document_ids = {source_directory.document_id_of(f"keep{n}.md") for n in (1, 2)}

    # 1. クロール A: 4 件を登録する(期限内なので、何も削除されない)
    job_a = run_crawl(api, opensearch, source_id)
    assert job_a["registration"]["created_count"] == 4, f"A: 4 created: {job_a['registration']}"
    assert job_a["deletion"]["current"]["deleted_count"] == 0, (
        f"A must not delete: {job_a['deletion']}"
    )
    gone_last_seen_at = _last_seen_at_of(opensearch, source_id, gone_document_ids)

    # 2. gone を消して、TTL が過ぎるまで待つ
    source_directory.remove("gone1.md")
    source_directory.remove("gone2.md")
    wait_until_expired(api, gone_last_seen_at, FORCE_DELETE_TTL_SECONDS)

    # 3. 通常のクロール B: 割合ルールで止まる
    job_b = run_crawl(api, opensearch, source_id)
    assert job_b["force_delete"] is False, f"B is a normal crawl: {job_b}"
    summary_b = job_b["deletion"]["summary"]
    assert summary_b["status"] == "skipped_by_ratio", (
        f"B must be stopped by the ratio rule: {summary_b}"
    )
    assert summary_b["forced"] is False, f"B is not forced: {summary_b}"
    assert (summary_b["target_count"], summary_b["denominator"]) == (2, 4), (
        f"B: T=2 (gone) of D=4: {summary_b}"
    )
    # 削除しなかった結果は `deleted_count` を記録しない(null。設計は値を定めていない)。削除がなかった
    # ことは、検索インデックスの件数で確認する。
    assert not summary_b["deleted_count"], f"B must record no deletion: {summary_b}"
    assert job_b["deletion"]["confirmation"] == "confirmed", f"B: {job_b['deletion']}"
    assert opensearch.count_source_documents(source_id) == 4, "B must delete nothing"
    row_after_b = wait_for_source_row(
        api, source_id, lambda row: row["document_count"] == 4, what="EP-01 counting 4 after B"
    )
    assert row_after_b["document_count"] == 4, "EP-01 must still count 4"

    # 4. force_delete・rewrite_mode つきのクロール C: 割合ルールを無視して削除する
    accepted_c = expect_json(
        api.start_crawl(source_id, {"force_delete": True, "rewrite_mode": True}), 202
    )
    assert (accepted_c["force_delete"], accepted_c["rewrite_mode"]) == (True, True), (
        f"EP-06 must record both options: {accepted_c}"
    )
    job_c = wait_for_job_terminal(api, accepted_c["job_id"])
    wait_for_lock_released(opensearch, source_id)
    assert job_c["status"] == "succeeded", (
        f"C must succeed: {job_c['status']} {job_c['failure_reason']} {job_c['failure_detail']}"
    )
    assert (job_c["force_delete"], job_c["rewrite_mode"]) == (True, True), (
        f"EP-10 must show both options: {job_c}"
    )
    summary_c = job_c["deletion"]["summary"]
    assert summary_c["status"] == "deleted", f"C must delete: {summary_c}"
    assert summary_c["forced"] is True, f"C must be forced: {summary_c}"
    assert (summary_c["target_count"], summary_c["denominator"], summary_c["deleted_count"]) == (
        2,
        4,
        2,
    ), f"C: T=2 of D=4, both deleted: {summary_c}"
    deletion_result = opensearch.fetch_deletion_result(job_c["job_id"])
    assert deletion_result is not None, "the deletion result of C must exist in loreley-deletions"
    assert (deletion_result["forced"], deletion_result["rewrite_mode"]) == (True, True), (
        f"the options must reach the Indexer: {deletion_result}"
    )
    remaining = {hit["_id"] for hit in opensearch.source_documents(source_id)}
    assert remaining == kept_document_ids, (
        f"only the files that remain must stay indexed: {sorted(remaining)}"
    )
    row_after_c = wait_for_source_row(
        api, source_id, lambda row: row["document_count"] == 2, what="EP-01 counting 2 after C"
    )
    assert row_after_c["document_count"] == 2, "EP-01 must count the 2 remaining"


def _assert_held_by_the_running_crawl(api: AdminApi, source_id: str, job_id: str) -> None:
    """実行中のジョブがロックを持つ間の、EP-02・09 の状態と、EP-06・05・08 の 409(窓の中で呼ぶ)。"""
    # ロックは ID 指定の読み取り(即時に見える)で、最終クロールと一覧は検索(反映が最大約 1 秒遅れる)
    detail = wait_for_source_detail(
        api,
        source_id,
        lambda body: body["last_crawl"] is not None and body["last_crawl"]["status"] == "running",
        what="EP-02 showing the running crawl",
    )
    assert detail["lock"]["state"] == "held_crawl", f"the lock must be held by the crawl: {detail}"
    assert (detail["lock"]["job"]["job_id"], detail["lock"]["job"]["status"]) == (
        job_id,
        "running",
    ), f"the lock must point to the running job: {detail['lock']}"
    assert detail["lock"]["acquired_at"] is not None, f"acquired_at must be set: {detail['lock']}"
    assert detail["last_crawl"]["job_id"] == job_id, f"last_crawl must be this job: {detail}"

    active = poll_until(
        lambda: expect_json(api.list_jobs(status="active", source_id=source_id), 200),
        lambda body: [item["status"] for item in body["items"]] == ["running"],
        timeout_secs=READ_LAG_TIMEOUT_SECONDS,
        poll_interval_secs=READ_LAG_POLL_INTERVAL_SECONDS,
        what="EP-09 listing the running job",
    )
    assert [item["job_id"] for item in active["items"]] == [job_id], (
        f"EP-09 must list only the running job: {active['items']}"
    )
    item = active["items"][0]
    assert (item["status"], item["stalled"], item["cancellable"]) == ("running", False, True), (
        f"a running job within its lease is cancellable and not stalled: {item}"
    )

    crawl_conflict = expect_error(
        api.start_crawl(source_id, {"force_delete": True}),
        409,
        "lock_held",
        expected_retryable=False,
    )
    details = crawl_conflict["details"]
    assert details["options_applied"] is False, f"the options must not be applied: {details}"
    assert details["requested"] == {"force_delete": True, "rewrite_mode": False}, (
        f"requested must echo the options: {details}"
    )
    _assert_existing_job(details, job_id)

    delete_conflict = expect_error(
        api.start_source_delete(source_id), 409, "lock_held", expected_retryable=False
    )
    assert "options_applied" not in delete_conflict["details"], (
        f"EP-05 has no options: {delete_conflict['details']}"
    )
    assert "requested" not in delete_conflict["details"], (
        f"EP-05 has no options: {delete_conflict['details']}"
    )
    _assert_existing_job(delete_conflict["details"], job_id)

    release_conflict = expect_error(
        api.release_lock(source_id), 409, "lock_in_use", expected_retryable=False
    )
    _assert_existing_job(release_conflict["details"], job_id)


def _assert_existing_job(details: dict[str, Any], job_id: str) -> None:
    """409 の `details` が、実行中のジョブと `held_crawl` を指していること(2.7)。"""
    existing_job = details["existing_job"]
    assert (
        existing_job["job_id"],
        existing_job["job_type"],
        existing_job["status"],
        existing_job["trigger"],
    ) == (job_id, "crawl", "running", "manual"), (
        f"existing_job must be the running crawl: {details}"
    )
    assert existing_job["lease_expires_at"] is not None, f"the lease must be set: {details}"
    assert details["lock_state"] == "held_crawl", f"lock_state must be held_crawl: {details}"


def _last_seen_at_of(
    opensearch: OpenSearchProbe, source_id: str, document_ids: set[str]
) -> datetime:
    """指定した文書の `last_seen_at`(クロールの開始時刻。同じクロールで登録した文書は同じ値)。"""
    hits = [hit for hit in opensearch.source_documents(source_id) if hit["_id"] in document_ids]
    assert {hit["_id"] for hit in hits} == document_ids, "the documents must be indexed"
    last_seen_values = {hit["_source"]["last_seen_at"] for hit in hits}
    assert len(last_seen_values) == 1, f"the documents must share last_seen_at: {last_seen_values}"
    return parse_instant(last_seen_values.pop())
