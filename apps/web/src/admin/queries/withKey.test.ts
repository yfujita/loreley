// FARC-U-22 の (4)(6): key の差し替え(withKey)が、実際の取得・invalidate で期待どおり動くこと。
import { describe, expect, it } from 'vitest'

import { getJobOptions, getSourceOptions } from '@/admin/api'

import { jsonResponse } from '../../../tests/support/apiErrors'
import { useFetchStub } from '../../../tests/support/fetchStub'
import { jobDetails } from '../../../tests/support/fixtures/jobs'
import { sourceDetails } from '../../../tests/support/fixtures/sources'
import { createTestQueryClient } from '../../../tests/support/queryTesting'
import { keys } from './keys'
import { withKey } from './withKey'

const stub = useFetchStub()

// EP-02(データソース詳細)と EP-10(ジョブ詳細)の、形の合った応答(E 5.3 の最小限の形の検査を通る)。
function respondWithFixtures() {
  stub.respondWith((request) =>
    jsonResponse(
      request.pathname.includes('/jobs/') ? jobDetails.succeeded() : sourceDetails.normal(),
    ),
  )
}

describe('withKey', () => {
  it('key だけを差し替える(他の項目はそのまま)', () => {
    const generated = getSourceOptions({ path: { source_id: 'demo' } })

    const keyed = withKey(generated, keys.sources.detail('demo'))

    expect(keyed.queryKey).toEqual(['sources', 'detail', 'demo'])
    expect((keyed as { queryFn?: unknown }).queryFn).toBe(generated.queryFn)
  })

  it('key を差し替えても、生成された queryFn は options の引数から URL を作り、正しい URL へ送る', async () => {
    respondWithFixtures()
    const options = withKey(
      getSourceOptions({ path: { source_id: 'a/b' } }),
      keys.sources.detail('a/b'),
    )

    await createTestQueryClient().fetchQuery(options)

    expect(stub.requests.map((request) => request.pathname)).toEqual([
      '/api/admin/v1/sources/a%2Fb',
    ])
  })

  it('queryKey[0] が文字列でも(生成 queryFn は ...queryKey[0] を展開する)、リクエストに影響しない', async () => {
    respondWithFixtures()
    const options = withKey(getJobOptions({ path: { job_id: 'j1' } }), keys.jobs.detail('j1'))

    await createTestQueryClient().fetchQuery(options)

    expect(stub.requests).toHaveLength(1)
    expect(stub.requests[0]).toMatchObject({
      method: 'GET',
      pathname: '/api/admin/v1/jobs/j1',
      search: '',
    })
  })

  it('key は QueryCache にドメインの key のまま入り、prefix の invalidate が意図どおり働く', async () => {
    respondWithFixtures()
    const queryClient = createTestQueryClient()
    await queryClient.fetchQuery(
      withKey(getSourceOptions({ path: { source_id: 'a' } }), keys.sources.detail('a')),
    )
    await queryClient.fetchQuery(
      withKey(getSourceOptions({ path: { source_id: 'b' } }), keys.sources.edit('b')),
    )
    await queryClient.fetchQuery(
      withKey(getJobOptions({ path: { job_id: 'j' } }), keys.jobs.detail('j')),
    )
    stub.requests.length = 0

    await queryClient.invalidateQueries({ queryKey: keys.sources.all, refetchType: 'none' })

    const stateOf = (key: readonly unknown[]) => queryClient.getQueryState(key)?.isInvalidated
    expect(stateOf(keys.sources.detail('a'))).toBe(true)
    expect(stateOf(keys.sources.edit('b'))).toBe(true)
    expect(stateOf(keys.jobs.detail('j'))).toBe(false)
  })

  it('1 つの詳細の key だけを invalidate できる(同じ EP でも詳細と編集は別)', async () => {
    respondWithFixtures()
    const queryClient = createTestQueryClient()
    await queryClient.fetchQuery(
      withKey(getSourceOptions({ path: { source_id: 'a' } }), keys.sources.detail('a')),
    )
    await queryClient.fetchQuery(
      withKey(getSourceOptions({ path: { source_id: 'a' } }), keys.sources.edit('a')),
    )

    await queryClient.invalidateQueries({ queryKey: keys.sources.detail('a'), refetchType: 'none' })

    expect(queryClient.getQueryState(keys.sources.detail('a'))?.isInvalidated).toBe(true)
    expect(queryClient.getQueryState(keys.sources.edit('a'))?.isInvalidated).toBe(false)
  })
})
