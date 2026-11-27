// 契約テスト(E 10.1・F 7.2): コミット済みの生成 SDK を通して、**実際に送られる URL** を正とする。
// モックで固定した応答では、パスの化けを検出できないため。
import { describe, expect, it } from 'vitest'

import {
  cancelJobMutation,
  getJobOptions,
  getSourceOptions,
  listDocumentsOptions,
  releaseLockMutation,
  startCrawlMutation,
  startSourceDeleteMutation,
  updateSourceMutation,
} from '@/admin/api'

import { jsonResponse } from '../../../tests/support/apiErrors'
import { useFetchStub } from '../../../tests/support/fetchStub'
import { createTestQueryClient, runMutation } from '../../../tests/support/queryTesting'

const API = '/api/admin/v1'

const stub = useFetchStub()

async function getJob(jobId: unknown): Promise<unknown> {
  // 型の上では string だが、実行時に不正な値が来ても送られないことを確かめる。
  const options = getJobOptions({ path: { job_id: jobId as string } })
  return createTestQueryClient()
    .fetchQuery(options)
    .catch((error: unknown) => error)
}

describe('実際に送られる URL(エンコード)', () => {
  it.each([
    ['a%b?c#d', `${API}/jobs/a%25b%3Fc%23d`],
    ['a/b', `${API}/jobs/a%2Fb`],
    ['日本語', `${API}/jobs/%E6%97%A5%E6%9C%AC%E8%AA%9E`],
    ['a b', `${API}/jobs/a%20b`],
    ['a😀b', `${API}/jobs/a%F0%9F%98%80b`],
    ['%2e%2e', `${API}/jobs/%252e%252e`],
  ])('job_id=%j → %s', async (jobId, expectedPath) => {
    stub.respondWith(jsonResponse({ ok: true }))

    await getJob(jobId)

    expect(stub.requests.map((request) => request.pathname)).toEqual([expectedPath])
  })

  it.each(['a.b', '..a', 'a..', 'my.source', '...'])(
    '`.` を含むだけの値 %j は拒否されず、そのままのパスで送られる',
    async (jobId) => {
      stub.respondWith(jsonResponse({ ok: true }))

      await getJob(jobId)

      expect(stub.requests.map((request) => request.pathname)).toEqual([`${API}/jobs/${jobId}`])
    },
  )

  it('source_id も同じ(S2 の取得)', async () => {
    stub.respondWith(jsonResponse({ ok: true }))

    await createTestQueryClient().fetchQuery(
      getSourceOptions({ path: { source_id: 'my.source/x' } }),
    )

    expect(stub.requests[0]?.pathname).toBe(`${API}/sources/my.source%2Fx`)
  })

  it('X1 の取得(パスの source_id とクエリ)', async () => {
    stub.respondWith(jsonResponse({ ok: true }))

    await createTestQueryClient().fetchQuery(
      listDocumentsOptions({ path: { source_id: 'a b' }, query: { tab: 'skipped' } }),
    )

    expect(stub.requests[0]?.pathname).toBe(`${API}/sources/a%20b/documents`)
    expect(stub.requests[0]?.search).toBe('?tab=skipped')
  })
})

describe('不正なパス値は送信せずに拒否する(合成の 400 invalid_request)', () => {
  const SYNTHESIZED_ERROR = {
    kind: 'api',
    status: 400,
    code: 'invalid_request',
    retryable: false,
    outcomeUnknown: false,
  }

  it.each([
    ['`.`(送ると一覧の EP `/jobs/` に化ける)', '.'],
    ['`..`(送ると 1 階層上に化ける)', '..'],
    ['空文字(送ると `/jobs/` に化ける)', ''],
    ['制御文字を含む値', 'a\u0001b'],
    ['改行を含む値', 'a\nb'],
    ['孤児サロゲート(SDK のエンコードが URIError になる)', 'a\ud800b'],
    ['undefined(プレースホルダが残る)', undefined],
    ['null', null],
    ['数値', 1],
  ])('job_id が %s', async (_name, jobId) => {
    stub.respondWith(jsonResponse({ ok: true }))

    const error = await getJob(jobId)

    expect(error).toEqual(SYNTHESIZED_ERROR)
    expect(stub.requests).toEqual([])
  })

  it('読み取りの source_id も同じ', async () => {
    const error = await createTestQueryClient()
      .fetchQuery(getSourceOptions({ path: { source_id: '..' } }))
      .catch((caught: unknown) => caught)

    expect(error).toEqual(SYNTHESIZED_ERROR)
    expect(stub.requests).toEqual([])
  })

  it.each([
    ['取消(EP-07)', () => cancelJobMutation(), { path: { job_id: '.' } }],
    ['ロック解放(EP-08)', () => releaseLockMutation(), { path: { source_id: '..' } }],
    ['クロール起動(EP-06)', () => startCrawlMutation(), { path: { source_id: '' } }],
    ['削除(EP-05)', () => startSourceDeleteMutation(), { path: { source_id: '.' } }],
    [
      '更新(EP-04)',
      () => updateSourceMutation(),
      {
        path: { source_id: '..' },
        body: {
          connector_config: {},
          min_delete_count: 0,
          ratio_threshold_percent: 0,
          ttl_days: 1,
        },
      },
    ],
  ])('書き込みの対象 ID も同じ: %s', async (_name, createOptions, variables) => {
    const error = await runMutation(createTestQueryClient(), createOptions(), variables).catch(
      (caught: unknown) => caught,
    )

    expect(error).toEqual(SYNTHESIZED_ERROR)
    expect(stub.requests).toEqual([])
  })
})
