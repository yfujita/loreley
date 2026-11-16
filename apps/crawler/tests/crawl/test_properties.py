"""ランダムなクロールの性質テスト(件数照合・ID 集合・整理後の記録。architecture 6.4・7.5)。

文書ごとに、取得・登録の結果(成功・取得できない・一時的な失敗が続く・原本サイズ超過・Indexer の
サイズ超過・拒否・1 度だけ拒否・抽出失敗・重複)をランダムに割り当て、チャンク・バッチの大きさも
ランダムにして、次の性質が成り立つことを確かめる。乱数は seed で固定し、決定的に再現できる。
- 終了通知の `enumerated_count` は、重複と識別子エラーを除いた文書数
- 列挙した文書は、登録されたか、`skipped_document_ids` か `oversize_document_ids` のどれか
  1 つに載る(件数照合の恒等式)
- `skipped_document_ids` と `oversize_document_ids` は、期待する文書の集合と一致する
- 整理の後は、今回の結果と同じ種類の記録だけが残り、消えた文書の記録は残らない
"""

import random

import pytest

from loreley_crawler.connectors.interface import (
    Completed,
    ConnectorError,
    DocumentRef,
    ErrorCategory,
)
from loreley_crawler.crawl import CrawlSettings
from loreley_crawler.documents import DocumentsSettings
from loreley_crawler.infrastructure.indexer_client import FailureType
from tests.crawl.support import CrawlEnv, crawl_env, document_id_of, finish_calls, run_full
from tests.fakes.fake_connector import FETCH, fetched_document
from tests.jobs.support import SOURCE_ID

KINDS = (
    "ok",
    "ok",
    "ok",
    "fetch_not_found",
    "fetch_transient",
    "oversize_at_fetch",
    "oversize_at_indexer",
    "rejected",
    "rejected_once",
    "extract_failed",
    "duplicate",
)
SKIPPED_KINDS = {"fetch_not_found", "fetch_transient", "rejected"}
OVERSIZE_KINDS = {"oversize_at_fetch", "oversize_at_indexer"}
MAX_RAW_BYTES = 10


def arrange_the_documents(env: CrawlEnv, kinds: dict[str, str]) -> None:
    for name, kind in kinds.items():
        if kind == "fetch_not_found":
            error = ConnectorError.of(ErrorCategory.FETCH_NOT_FOUND, "gone")
        elif kind == "fetch_transient":
            error = ConnectorError.of(ErrorCategory.FETCH_TRANSIENT, "flaky")
        else:
            error = None
        if error is not None:
            env.connector.behavior.inject(FETCH, error, key=name, times=None)
        if kind == "oversize_at_indexer":
            env.indexer.registration_failures[name] = FailureType.OVERSIZE
        if kind == "rejected":
            env.indexer.registration_failures[name] = FailureType.DOCUMENT_REJECTED
        if kind == "rejected_once":
            env.indexer.rejected_once.add(name)
        if kind == "extract_failed":
            env.indexer.extract_failed.add(name)


@pytest.mark.parametrize("seed", range(25))
def test_a_random_crawl_keeps_the_counts_the_id_sets_and_the_purged_records_consistent(
    seed: int,
) -> None:
    rnd = random.Random(seed)
    kinds: dict[str, str] = {}
    refs: list[DocumentRef] = []
    documents = {}
    for index in range(rnd.randint(0, 12)):
        name = f"d{index:02d}"
        kinds[name] = rnd.choice(KINDS)
        refs.append(DocumentRef(name, name))
        if kinds[name] == "duplicate":
            refs.append(DocumentRef(name, name))
        if rnd.random() < 0.15:
            refs.append(DocumentRef(f"/invalid{index}", index))  # 識別子エラー
        too_big = kinds[name] == "oversize_at_fetch"
        documents[name] = fetched_document(b"x" * 100 if too_big else b"hello")
    rnd.shuffle(refs)
    settings = CrawlSettings(
        chunk_size=rnd.randint(1, 6),
        batch_max_documents=rnd.randint(1, 4),
        last_seen_max_ids=rnd.randint(1, 5),
        consecutive_skip_limit=1_000,
    )
    with crawl_env(
        items=[*refs, Completed()],
        documents=documents,
        settings=settings,
        documents_settings=DocumentsSettings(max_raw_bytes=MAX_RAW_BYTES),
    ) as env:
        arrange_the_documents(env, kinds)
        # 前回までの記録: すべての文書の `skip`・`oversize` と、今回は列挙されない文書の記録。
        for name in [*kinds, "vanished"]:
            env.seed_document_record("skip", name)
            env.seed_document_record("oversize", name)

        body = run_full(env)

        assert body["status"] in ("succeeded", "partially_succeeded"), (seed, body)
        (sent,) = finish_calls(env)
        registration = body["registration"]
        assert sent["enumerated_count"] == registration["enumerated_count"] == len(kinds)
        accounted_for = (
            registration["created_count"]
            + registration["updated_count"]
            + registration["unchanged_count"]
            + len(sent["skipped_document_ids"])
            + len(sent["oversize_document_ids"])
        )
        assert accounted_for == len(kinds), seed  # 件数照合の恒等式
        skipped = {document_id_of(n) for n, k in kinds.items() if k in SKIPPED_KINDS}
        oversize = {document_id_of(n) for n, k in kinds.items() if k in OVERSIZE_KINDS}
        assert set(sent["skipped_document_ids"]) == skipped, seed
        assert set(sent["oversize_document_ids"]) == oversize, seed
        assert len(sent["skipped_document_ids"]) == len(skipped)  # 重複なし
        present = set(env.jobs.jobs_repository.record_ids())
        for name in kinds:
            document_id = document_id_of(name)
            assert (f"skip-{SOURCE_ID}-{document_id}" in present) == (document_id in skipped), seed
            assert (f"oversize-{SOURCE_ID}-{document_id}" in present) == (
                document_id in oversize
            ), seed
        assert f"skip-{SOURCE_ID}-{document_id_of('vanished')}" not in present
        assert f"oversize-{SOURCE_ID}-{document_id_of('vanished')}" not in present
