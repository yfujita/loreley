"""AIT-50・AIT-51: クロールの取消とロックの解放(EP-07・08 と、EP-02・06・09・10)。

目的:
    実行待ち・実行中のクロールの取消(EP-07)と、孤児ロックの検知・解放(EP-02・06・08)を、
    実 Crawler・実 OpenSearch の上で確かめる。
      - AIT-50: 実行待ちのジョブは 200 で取り消せ、実行中のジョブ(終了通知の送信を始めた後)は
        202 で受け付けられて `cancelled` になること。削除は止めず、画面に「取消は削除を止めていません」を
        出すための `cancel_after_finish_notice` と警告が付くこと
      - AIT-51: ジョブが終端なのに残ったロック(孤児ロック)が `orphan` と表示され、起動は 409
        `lock_held`、EP-08 で実際に解放でき、その後のクロールが成功すること
    単体テストでは、Crawler の取消の受付・記録・ロック解放と、実 Crawler が返す 409 の `existing_job`、
    実際のロック文書の削除を確認できない。

参照する設計書の章:
    - admin-api-v0.1.md 2.7(`lock_held`)、2.9(`lock_state`・`cancel_after_finish_notice`)、
      4.2・4.3(EP-07・08)、5.1・5.2(EP-09・10)
    - crawler-architecture-v0.4.md 4.7(取り消し)、5.1(ロック文書の形式)、5.5(解放)、
      7.5・7.6(終了通知・確認結果の区分)
    - crawler-api-v0.4.md 4.1〜4.3

扱うシナリオ: AIT-50(取消)、AIT-51(孤児ロックの解放)

窓について(AIT-50):
    Crawler は終了通知(`enumeration_completed`)の送信を始めると `finish_notice.send_started_at` を
    記録し、削除結果のポーリング(間隔 10 秒。compose.test.yaml)の間ロックを持つ。取消がこれ以降に
    受け付けられると、Indexer の削除は止まらない境界になる。ジョブ記録を直接読んで、これが記録された
    ことを観測してから操作し、見逃したときは見逃したことが分かるメッセージで失敗する(support.py)。

AIT-51 は、孤児ロックを OpenSearch に直接書く(前提作りだけ。Crawler は起動時の回復で自分のロックを
消すため、実 Crawler には孤児ロックを作らせられない)。判定は Admin API と実 Crawler の応答で行う。
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from support import (
    AdminApi,
    OpenSearchProbe,
    SourceDirectory,
    expect_error,
    expect_json,
    format_instant,
    run_crawl,
    wait_for_finish_notice_started,
    wait_for_job_list,
    wait_for_job_terminal,
    wait_for_lock_released,
    wait_for_source_detail,
)

ORPHAN_LOCK_OWNER = "it-orphan-owner"
ORPHAN_LOCK_AGE = timedelta(hours=2)


def test_queued_crawl_is_cancelled_at_once_and_running_crawl_is_cancelled_after_the_finish_notice(
    api: AdminApi,
    opensearch: OpenSearchProbe,
    registered_source: SourceDirectory,
    make_registered_source: Callable[..., SourceDirectory],
) -> None:
    """【何を確認するか】(AIT-50)
    実行待ちのクロールの取消(EP-07 が 200 `cancelled`、ロックの解放)と、終了通知の送信を始めた後の
    実行中のクロールの取消(202 `running` → `cancelled`、`cancel_after_finish_notice=true`、警告
    `polling_aborted`、確認結果 `unconfirmed`、ロックの解放)、取消済みの再取消(409
    `job_already_finished`)。

    【前提と手順】
    前提: 登録済みのソース X(md 2 件)と Y。Job Runner は直列。
    手順:
      1. X のクロールを起動し、ジョブ記録の `finish_notice.send_started_at` が記録されるのを待つ。
      2. Y のクロールを起動する(X が実行中なので `queued`)。EP-09(`status=active`)と EP-02(Y)を読む。
      3. EP-07 で Y を取り消す。
      4. EP-07 で X を取り消し、`cancelled` になるのを待つ。EP-10・EP-02(X)を読む。
      5. EP-07 で X を再び取り消す。

    【期待する結果とその根拠】
    - 手順 2: EP-09 の `active` は X(`running`)と Y(`queued`)の 2 件で、どちらも `stalled=false`・
      `cancellable=true`(B 2.9)。EP-02 の Y は `lock.state=held_crawl`・`lock.job.status=queued`・
      `lease_expires_at=null`(実行待ちのロックにリースはない。crawler-architecture 5.1)・最終クロール
      `queued`。
    - 手順 3: 200 `{job_id, status: cancelled}`。Y のロック文書は消え、EP-02 の `lock.state=none`。
      EP-10 は `cancelled`・`started_at=null`・`cancel_after_finish_notice=false`(送信を始める前の取消)。
    - 手順 4: 202 `{job_id, status: running}`(受付だけ。B 4.2)。ジョブは `cancelled` になり、
      `cancel_after_finish_notice=true`・`warnings` に `polling_aborted`・`deletion.confirmation=unconfirmed`
      (削除結果の確認を打ち切った。crawler-architecture 4.7・7.6)・`registration.partial=false`(集計の確定後の
      取消は戻さない)。ロックは解放され、EP-02 の `lock.state=none`。
    - 手順 5: 409 `job_already_finished`(`details.status=cancelled`。成功に変換しない。B 2.3)。

    【単体テストでは確認できず実機で確認する点】
    実 Crawler の取消(実行待ち → 即時、実行中 → 取消要求の記録と Job Runner の確認点での反映)、
    終了通知の送信後の取消の境界(`send_started_at`)、ポーリング中断の警告・確認結果の区分。
    """
    cancelled_source = registered_source
    queued_source = make_registered_source("queued")
    cancelled_source.write("a.md", b"# a\n\ntext of a\n")
    cancelled_source.write("b.md", b"# b\n\ntext of b\n")

    # 1. X を起動し、終了通知の送信を始めるのを待つ(取消が削除を止めない境界の内側の窓)
    running_job_id = expect_json(api.start_crawl(cancelled_source.source_id), 202)["job_id"]
    wait_for_finish_notice_started(opensearch, running_job_id)

    # 2. Y は X が実行中なので実行待ちになる。EP-09・EP-02 は検索で読むので、反映を待つ
    queued_job_id = expect_json(api.start_crawl(queued_source.source_id), 202)["job_id"]
    active = wait_for_job_list(
        api,
        lambda body: {item["job_id"] for item in body["items"]} == {running_job_id, queued_job_id},
        what="EP-09 listing the running and the queued job",
        status="active",
    )
    states = {item["job_id"]: item for item in active["items"]}
    assert states[running_job_id]["status"] == "running", f"X is running: {states}"
    assert states[queued_job_id]["status"] == "queued", f"Y waits for X: {states}"
    for job_id, item in states.items():
        assert (item["stalled"], item["cancellable"]) == (False, True), (
            f"a running (within its lease) or queued job is cancellable: {job_id} {item}"
        )
    queued_detail = wait_for_source_detail(
        api,
        queued_source.source_id,
        lambda body: body["last_crawl"] is not None and body["last_crawl"]["status"] == "queued",
        what="EP-02 showing the queued crawl of Y",
    )
    assert queued_detail["lock"]["state"] == "held_crawl", f"Y holds a lock: {queued_detail}"
    assert queued_detail["lock"]["job"]["job_id"] == queued_job_id
    assert queued_detail["lock"]["job"]["status"] == "queued"
    assert queued_detail["lock"]["job"]["lease_expires_at"] is None, (
        f"a queued job's lock has no lease: {queued_detail['lock']}"
    )

    # 3. 実行待ちの Y を取り消す(その場で cancelled)
    cancel_queued = expect_json(api.cancel_job(queued_job_id), 200)
    assert cancel_queued == {"job_id": queued_job_id, "status": "cancelled"}, (
        f"a queued job is cancelled at once: {cancel_queued}"
    )
    assert opensearch.fetch_lock(queued_source.source_id) is None, "Y's lock must be released"
    queued_job = expect_json(api.get_job(queued_job_id), 200)
    assert queued_job["status"] == "cancelled", f"Y must be cancelled: {queued_job}"
    assert queued_job["started_at"] is None, f"Y never started: {queued_job}"
    assert queued_job["cancel_after_finish_notice"] is False, (
        f"Y was cancelled before any finish notice: {queued_job}"
    )
    queued_detail_after = expect_json(api.get_source(queued_source.source_id), 200)
    assert queued_detail_after["lock"]["state"] == "none", f"Y: {queued_detail_after['lock']}"

    # 4. 終了通知の送信を始めた後の X を取り消す(202 は受付だけ)
    cancel_running = expect_json(api.cancel_job(running_job_id), 202)
    assert cancel_running == {"job_id": running_job_id, "status": "running"}, (
        f"a running job only accepts the request: {cancel_running}"
    )
    running_job = wait_for_job_terminal(api, running_job_id)
    wait_for_lock_released(opensearch, cancelled_source.source_id)
    assert running_job["status"] == "cancelled", (
        f"X must end cancelled: {running_job['status']} {running_job['failure_reason']}"
    )
    assert running_job["cancel_after_finish_notice"] is True, (
        f"the cancel came after the finish notice was sent: {running_job}"
    )
    polling_aborted = [w for w in running_job["warnings"] if w["code"] == "polling_aborted"]
    assert len(polling_aborted) == 1, f"polling_aborted must be warned: {running_job['warnings']}"
    deletion = running_job["deletion"]
    assert deletion["confirmation"] == "unconfirmed", (
        f"the confirmation was abandoned: {deletion['confirmation']}"
    )
    registration = running_job["registration"]
    assert (registration["partial"], registration["phase"]) == (False, "final"), (
        f"the registration was already finalized: {registration}"
    )
    assert (running_job["cancellable"], running_job["stalled"]) == (False, False)
    running_detail = expect_json(api.get_source(cancelled_source.source_id), 200)
    assert running_detail["lock"]["state"] == "none", f"X: {running_detail['lock']}"

    # 5. 取消済みのジョブの再取消は、成功に変換せず 409
    already_finished = expect_error(
        api.cancel_job(running_job_id), 409, "job_already_finished", expected_retryable=False
    )
    assert already_finished["details"] == {"status": "cancelled"}, (
        f"the current state must be told: {already_finished}"
    )


def test_orphan_lock_is_shown_refuses_a_crawl_is_released_by_ep08_and_the_next_crawl_succeeds(
    api: AdminApi, opensearch: OpenSearchProbe, registered_source: SourceDirectory
) -> None:
    """【何を確認するか】(AIT-51)
    ジョブが終端なのに残ったロック(孤児ロック)が、EP-02 で `orphan`・EP-06 で 409 `lock_held`
    (`lock_state=orphan`)になり、EP-08 で実際に解放(`released=true`・ロック文書の削除)でき、再送は
    `released=false`、解放後のクロールが成功すること。

    【前提と手順】
    前提: 登録済みのソースで、md 1 件のクロールを 1 回成功させる(ジョブ J は `succeeded`、ロックは解放済み)。
    手順:
      1. J を指す孤児ロックを、`loreley-jobs` に直接書く(`acquired_at` は 2 時間前。リース期限・
         ハートビートも過去。形式は crawler-architecture 5.1)。
      2. EP-02 を読む。
      3. EP-06 を呼ぶ。
      4. EP-08 を呼ぶ。ロック文書を直接読む。EP-02 を読む。
      5. EP-08 を再び呼ぶ。
      6. EP-06 を呼び、完了を待つ。

    【期待する結果とその根拠】
    - 手順 2: `lock.state=orphan`(ジョブが終端のロックは孤児。B 2.9)、`lock.job` は J(`crawl`・
      `succeeded`)、`lock.acquired_at` は書き込んだ値。
    - 手順 3: 409 `lock_held`・`options_applied=false`・`requested`・`existing_job.job_id=J`・
      `lock_state=orphan`(B 2.7。画面はこれを成功扱いにせず、解放へ導く)。
    - 手順 4: 200 `{released: true, failed_job_id: null}`(終端のジョブは `failed` にしない。B 4.3)。
      ロック文書は消え、EP-02 の `lock.state=none`。
    - 手順 5: 200 `{released: false, failed_job_id: null}`(冪等)。
    - 手順 6: 202 → `succeeded`。新しいジョブ ID は J と異なる。

    【単体テストでは確認できず実機で確認する点】
    実 Crawler の EP-08(ロック文書の実際の削除、実行中でないことの判断)と、実ロック文書・ジョブ記録
    からの `lock_state` の導出、ロックのある起動の 409 の `existing_job`。
    """
    source_id = registered_source.source_id
    registered_source.write("doc.md", b"# doc\n\ntext of doc\n")
    finished_job = run_crawl(api, opensearch, source_id)
    finished_job_id = finished_job["job_id"]

    # 1. 孤児ロックを書く(Crawler の異常終了で残った状態)
    now = datetime.now(UTC).replace(microsecond=0)
    acquired_at = now - ORPHAN_LOCK_AGE
    opensearch.write_lock_record(
        source_id=source_id,
        owner=ORPHAN_LOCK_OWNER,
        job_id=finished_job_id,
        acquired_at=acquired_at,
        lease_expires_at=acquired_at + timedelta(minutes=5),
        heartbeat_at=acquired_at,
    )

    # 2. EP-02: orphan
    detail = expect_json(api.get_source(source_id), 200)
    lock = detail["lock"]
    assert lock["state"] == "orphan", f"a lock of a finished job is an orphan: {lock}"
    assert lock["job"]["job_id"] == finished_job_id, f"lock.job must be the finished job: {lock}"
    assert (lock["job"]["job_type"], lock["job"]["status"]) == ("crawl", "succeeded"), (
        f"lock.job must show the stored job: {lock}"
    )
    assert lock["acquired_at"] == format_instant(acquired_at), f"acquired_at: {lock}"

    # 3. EP-06: 起動は拒否される
    refused = expect_error(
        api.start_crawl(source_id, {"force_delete": False, "rewrite_mode": True}),
        409,
        "lock_held",
        expected_retryable=False,
    )
    details = refused["details"]
    assert details["lock_state"] == "orphan", f"lock_state must tell the orphan: {details}"
    assert details["options_applied"] is False, f"the options must not be applied: {details}"
    assert details["requested"] == {"force_delete": False, "rewrite_mode": True}, (
        f"requested must echo the options: {details}"
    )
    assert details["existing_job"]["job_id"] == finished_job_id, (
        f"existing_job must be the job of the lock: {details}"
    )

    # 4. EP-08: 実際に解放する
    released = expect_json(api.release_lock(source_id), 200)
    assert released == {"source_id": source_id, "released": True, "failed_job_id": None}, (
        f"the orphan lock must be released without failing any job: {released}"
    )
    assert opensearch.fetch_lock(source_id) is None, "the lock document must be deleted"
    after_release = expect_json(api.get_source(source_id), 200)
    assert after_release["lock"] == {"state": "none", "job": None, "acquired_at": None}, (
        f"the lock must be gone: {after_release['lock']}"
    )

    # 5. 再送は何もしない(冪等)
    again = expect_json(api.release_lock(source_id), 200)
    assert again == {"source_id": source_id, "released": False, "failed_job_id": None}, (
        f"releasing again must do nothing: {again}"
    )

    # 6. 解放後は、クロールが起動でき成功する
    next_job = run_crawl(api, opensearch, source_id)
    assert next_job["job_id"] != finished_job_id, f"a new job must run: {next_job['job_id']}"
    # EP-08 は終端のジョブを書き換えない(`failed` にしない)
    finished_job_after = expect_json(api.get_job(finished_job_id), 200)
    assert finished_job_after["status"] == "succeeded", (
        f"the finished job must stay succeeded: {finished_job_after['status']}"
    )
