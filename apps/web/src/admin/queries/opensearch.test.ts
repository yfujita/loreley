import { flushPromises } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import { jsonResponse } from '../../../tests/support/apiErrors'
import { runComposable } from '../../../tests/support/composableTesting'
import { useFetchStub } from '../../../tests/support/fetchStub'
import { opensearch } from '../../../tests/support/fixtures/opensearch'
import { createTestQueryClient } from '../../../tests/support/queryTesting'
import { keys } from './keys'
import { useOpenSearchClusterQuery } from './opensearch'

const stub = useFetchStub()

describe('useOpenSearchClusterQuery(EP-12。O1)', () => {
  it('クエリを付けずに取得し(絞り込みの q・state は API に渡さない)、key は ["opensearch","cluster"]', async () => {
    stub.respondWith(jsonResponse(opensearch.green()))
    const queryClient = createTestQueryClient()

    const { result } = await runComposable(() => useOpenSearchClusterQuery(), { queryClient })
    await flushPromises()

    expect(result.data.value).toEqual(opensearch.green())
    expect(stub.requests).toHaveLength(1)
    expect(stub.requests[0]).toMatchObject({
      method: 'GET',
      pathname: '/api/admin/v1/opensearch/cluster',
      search: '',
    })
    expect(queryClient.getQueryState(keys.opensearch.cluster())?.status).toBe('success')
  })
})
