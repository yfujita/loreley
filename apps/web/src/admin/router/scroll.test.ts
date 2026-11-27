import { describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import { scrollBehavior } from './scroll'

const EMPTY = { render: () => null }
const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/jobs', name: 'jobs', component: EMPTY },
    { path: '/jobs/:jobId', name: 'job-detail', component: EMPTY },
  ],
})

async function behave(
  fromPath: string,
  toPath: string,
  saved: { left: number; top: number } | null,
) {
  await router.push(fromPath)
  const from = router.currentRoute.value
  await router.push(toPath)
  const to = router.currentRoute.value
  return scrollBehavior(to, from, saved)
}

describe('scrollBehavior(E 4.5)', () => {
  it('画面が変わるときは先頭へ', async () => {
    expect(await behave('/jobs', '/jobs/a', null)).toEqual({ top: 0 })
    expect(await behave('/jobs/a', '/jobs/b', null)).toEqual({ top: 0 })
  })

  it('クエリだけの変化(ページ・タブ・並べ替え)では動かさない', async () => {
    expect(await behave('/jobs', '/jobs?page=2', null)).toBe(false)
  })

  it('戻る・進む(保存された位置がある)ときは、その位置へ戻す', async () => {
    expect(await behave('/jobs/a', '/jobs', { left: 0, top: 480 })).toEqual({ left: 0, top: 480 })
    // クエリだけの変化でも、保存された位置があれば戻す(履歴の移動)
    expect(await behave('/jobs?page=2', '/jobs', { left: 0, top: 120 })).toEqual({
      left: 0,
      top: 120,
    })
  })
})
