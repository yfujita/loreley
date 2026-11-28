import { describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import { isSamePage } from './samePage'

const EMPTY = { render: () => null }

async function locations(fromPath: string, toPath: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/jobs', name: 'jobs', component: EMPTY },
      { path: '/jobs/:jobId', name: 'job-detail', component: EMPTY },
      { path: '/sources/:sourceId', name: 'source-detail', component: EMPTY },
    ],
  })
  await router.push(fromPath)
  const from = router.currentRoute.value
  await router.push(toPath)
  const to = router.currentRoute.value
  return { from, to }
}

describe('isSamePage(E 4.5: パスが変わったときだけフォーカス・スクロールを動かす)', () => {
  it.each([
    ['/jobs', '/jobs?page=2', true],
    ['/jobs?page=2', '/jobs?page=3&size=50', true],
    ['/jobs', '/jobs#top', true],
    ['/jobs/a', '/jobs/a?x=1', true],
    ['/jobs', '/jobs/a', false],
    ['/jobs/a', '/jobs/b', false],
    ['/jobs/a', '/sources/a', false],
    ['/jobs', '/sources/a', false],
  ])('%s → %s は同じ画面か: %s', async (fromPath, toPath, expected) => {
    const { from, to } = await locations(fromPath, toPath)

    expect(isSamePage(to, from)).toBe(expected)
  })
})
