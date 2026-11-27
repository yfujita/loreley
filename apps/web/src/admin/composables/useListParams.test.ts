import { flushPromises } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import type { LocationQuery, RouteRecordRaw, Router } from 'vue-router'

import { runComposable } from '../../../tests/support/composableTesting'
import { useListParams, type ListParamsDefinition } from './useListParams'

type Params = {
  page: number
  size: 25 | 50 | 100
  sort: 'queued_at' | '-queued_at' | null
  status: string | null
}

const PAGE = { render: () => null }
const ROUTES: RouteRecordRaw[] = [
  { path: '/', name: 'home', component: PAGE },
  { path: '/jobs', name: 'jobs', component: PAGE },
  { path: '/other', name: 'other', component: PAGE },
]

/** 履歴を 1 つ戻り、遷移が終わるまで待つ。`push` なら 1 つ前の条件に、`replace` なら 1 つ前の画面に戻る。 */
async function goBack(router: Router): Promise<string> {
  router.go(-1)
  await flushPromises()
  return router.currentRoute.value.fullPath
}

function first(query: LocationQuery, key: string): string | null {
  const value = query[key]
  return typeof value === 'string' ? value : null
}

function positiveInteger(text: string | null): number | null {
  return text !== null && /^[1-9][0-9]*$/.test(text) ? Number(text) : null
}

function definition(
  overrides: Partial<ListParamsDefinition<Params>> = {},
): ListParamsDefinition<Params> {
  return {
    parse(query) {
      const size = Number(first(query, 'size'))
      const sort = first(query, 'sort')
      return {
        page: positiveInteger(first(query, 'page')) ?? 1,
        size: size === 50 || size === 100 ? size : 25,
        sort: sort === 'queued_at' || sort === '-queued_at' ? sort : null,
        status: first(query, 'status'),
      }
    },
    serialize(params) {
      return {
        ...(params.page !== 1 && { page: String(params.page) }),
        ...(params.size !== 25 && { size: String(params.size) }),
        ...(params.sort !== null && { sort: params.sort }),
        ...(params.status !== null && { status: params.status }),
      }
    },
    navigation: 'push',
    pageKey: 'page',
    resetPageOn: ['size', 'status'],
    ...overrides,
  }
}

async function mountAt(path: string, overrides: Partial<ListParamsDefinition<Params>> = {}) {
  const mounted = await runComposable(() => useListParams(definition(overrides)), {
    routes: ROUTES,
    previousPath: '/',
    initialPath: path,
  })
  await flushPromises()
  return mounted
}

describe('URL → 条件', () => {
  it('クエリがなければ既定値', async () => {
    const { result } = await mountAt('/jobs')

    expect(result.params.value).toEqual({ page: 1, size: 25, sort: null, status: null })
  })

  it('クエリから条件を作る', async () => {
    const { result } = await mountAt('/jobs?page=3&size=50&sort=-queued_at&status=failed')

    expect(result.params.value).toEqual({ page: 3, size: 50, sort: '-queued_at', status: 'failed' })
  })

  it('URL が変わると(戻る・進む・直接の変更)、条件も変わる(ローカルに複製しない)', async () => {
    const { result, router } = await mountAt('/jobs?page=2')

    await router.push('/jobs?page=5')

    expect(result.params.value.page).toBe(5)
  })
})

describe('不正値の正規化(既定値にして replace)', () => {
  it('不正なクエリは、既定値の URL に replace される(履歴に積まない)', async () => {
    const { router } = await mountAt('/jobs?page=abc&size=7&sort=name&status=failed')

    expect(router.currentRoute.value.fullPath).toBe('/jobs?status=failed')
    // replace なので、戻ると不正な URL ではなく 1 つ前('/')に戻る
    expect(await goBack(router)).toBe('/')
  })

  it('既定値が明示されている(page=1・size=25)URL も、省略した形に正規化する', async () => {
    const { router } = await mountAt('/jobs?page=1&size=25')

    expect(router.currentRoute.value.fullPath).toBe('/jobs')
  })

  it('範囲外の page(0・負・小数)は 1 に戻る', async () => {
    for (const bad of ['0', '-1', '1.5', '']) {
      const { router, wrapper } = await mountAt(`/jobs?page=${bad}`)

      expect(router.currentRoute.value.fullPath, `page=${bad}`).toBe('/jobs')
      wrapper.unmount()
    }
  })

  it('すでに正規化されている URL は触らない(履歴に余分な項目を足さない)', async () => {
    const { router } = await mountAt('/jobs?page=2')

    expect(router.currentRoute.value.fullPath).toBe('/jobs?page=2')
    expect(await goBack(router)).toBe('/')
  })

  it('未知のキー・同じキーの繰り返しは落とす', async () => {
    const { router } = await mountAt('/jobs?page=2&foo=bar&page=3')

    expect(router.currentRoute.value.fullPath).toBe('/jobs')
  })

  it('別の画面へ遷移したとき、遷移先の URL をこの画面の条件で書き換えない', async () => {
    const { router } = await mountAt('/jobs?page=2')

    await router.push('/other?x=1&page=abc')
    await flushPromises()

    expect(router.currentRoute.value.fullPath).toBe('/other?x=1&page=abc')
  })
})

describe('条件の変更(update)', () => {
  it('push: 履歴に積む(戻る・再読み込み・共有で再現)', async () => {
    const { result, router } = await mountAt('/jobs')

    await result.update({ sort: 'queued_at' })

    expect(router.currentRoute.value.fullPath).toBe('/jobs?sort=queued_at')
    // push なので、戻ると 1 つ前の条件('/jobs')に戻る
    expect(await goBack(router)).toBe('/jobs')
  })

  it('replace を指定した画面(O1 の q・state)は、履歴に積まない', async () => {
    const { result, router } = await mountAt('/jobs', { navigation: 'replace' })

    await result.update({ status: 'failed' })

    expect(router.currentRoute.value.fullPath).toBe('/jobs?status=failed')
    // replace なので、戻ると 1 つ前の画面('/')に戻る
    expect(await goBack(router)).toBe('/')
  })

  it('既定値に戻した条件は、URL から省略される', async () => {
    const { result, router } = await mountAt('/jobs?sort=queued_at&size=50')

    await result.update({ sort: null, size: 25 })

    expect(router.currentRoute.value.fullPath).toBe('/jobs')
  })

  it('同じ条件への変更は、何もしない(履歴に積まない)', async () => {
    const { result, router } = await mountAt('/jobs?page=2')

    await result.update({ page: 2 })

    expect(await goBack(router)).toBe('/')
  })

  describe('条件を変えたら 1 ページ目に戻る(絞り込み・件数・タブ・データソース)', () => {
    it('絞り込み(status)を変えると page が 1 に戻る', async () => {
      const { result, router } = await mountAt('/jobs?page=4')

      await result.update({ status: 'failed' })

      expect(router.currentRoute.value.fullPath).toBe('/jobs?status=failed')
    })

    it('件数(size)を変えると page が 1 に戻る', async () => {
      const { result, router } = await mountAt('/jobs?page=4')

      await result.update({ size: 100 })

      expect(router.currentRoute.value.fullPath).toBe('/jobs?size=100')
    })

    it('ページだけの変更では戻らない', async () => {
      const { result, router } = await mountAt('/jobs?page=4&status=failed')

      await result.update({ page: 5 })

      expect(router.currentRoute.value.fullPath).toBe('/jobs?page=5&status=failed')
    })

    it('並べ替えだけの変更では戻らない', async () => {
      const { result, router } = await mountAt('/jobs?page=4')

      await result.update({ sort: '-queued_at' })

      expect(router.currentRoute.value.fullPath).toBe('/jobs?page=4&sort=-queued_at')
    })

    it('絞り込みと page を一緒に指定したときは、指定した page を使う', async () => {
      const { result, router } = await mountAt('/jobs?page=4')

      await result.update({ status: 'failed', page: 2 })

      expect(router.currentRoute.value.fullPath).toBe('/jobs?page=2&status=failed')
    })

    it('絞り込みを同じ値に「変更」したときは、page を戻さない(変わっていない)', async () => {
      const { result, router } = await mountAt('/jobs?page=4&status=failed')

      await result.update({ status: 'failed', sort: 'queued_at' })

      expect(router.currentRoute.value.fullPath).toBe('/jobs?page=4&sort=queued_at&status=failed')
    })
  })

  it('pageKey を持たない画面(O1)は、ページを戻す処理をしない', async () => {
    const { result, router } = await mountAt('/jobs', {
      pageKey: undefined,
      resetPageOn: undefined,
      navigation: 'replace',
    })

    await result.update({ status: 'failed' })

    expect(router.currentRoute.value.fullPath).toBe('/jobs?status=failed')
  })

  describe('続けて(同期的に)update を呼ぶ(Vuetify は並べ替え・件数の変更の直後に page=1 も通知する)', () => {
    it('反映前の条件に積み上げる: sort → page=1 の 2 回で、sort の変更が消えない', async () => {
      const { result, router } = await mountAt('/jobs?page=3&status=failed')

      const first = result.update({ sort: 'queued_at' })
      const second = result.update({ page: 1 })
      await Promise.all([first, second])
      await flushPromises()

      expect(router.currentRoute.value.fullPath).toBe('/jobs?sort=queued_at&status=failed')
    })

    it('履歴に積むのは 1 件だけ(前の遷移は後の遷移に置き換えられる)', async () => {
      const { result, router } = await mountAt('/jobs?page=3')

      await Promise.all([result.update({ sort: 'queued_at' }), result.update({ page: 1 })])
      await flushPromises()

      expect(await goBack(router)).toBe('/jobs?page=3')
    })

    it('2 回目が今の URL と同じ条件に戻すときも、1 回目を打ち消す', async () => {
      const { result, router } = await mountAt('/jobs?page=3')

      await Promise.all([result.update({ page: 4 }), result.update({ page: 3 })])
      await flushPromises()

      expect(router.currentRoute.value.fullPath).toBe('/jobs?page=3')
    })

    it('遷移が終われば、次の update は新しい URL を土台にする(積み上げが残らない)', async () => {
      const { result, router } = await mountAt('/jobs?page=3')
      await result.update({ sort: 'queued_at' })

      await result.update({ sort: '-queued_at' })

      expect(router.currentRoute.value.fullPath).toBe('/jobs?page=3&sort=-queued_at')
    })
  })
})
