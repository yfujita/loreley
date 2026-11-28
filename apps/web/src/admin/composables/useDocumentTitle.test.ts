import { nextTick, ref } from 'vue'
import { describe, expect, it } from 'vitest'

import { runComposable } from '../../../tests/support/composableTesting'
import { APP_TITLE, formatDocumentTitle, useDocumentTitle } from './useDocumentTitle'

describe('formatDocumentTitle(DS 5.3: 「title - Loreley 管理」)', () => {
  it('title の後ろに「 - Loreley 管理」を付ける', () => {
    expect(formatDocumentTitle('ダッシュボード')).toBe('ダッシュボード - Loreley 管理')
    expect(APP_TITLE).toBe('Loreley 管理')
  })
})

describe('useDocumentTitle', () => {
  it('document.title を設定し、title が変わるたびに更新する', async () => {
    const title = ref('demo-handbook')
    await runComposable(() => useDocumentTitle(title))
    expect(document.title).toBe('demo-handbook - Loreley 管理')

    title.value = 'other'
    await nextTick()

    expect(document.title).toBe('other - Loreley 管理')
  })

  it('getter でも受けられる', async () => {
    const id = ref('job-1')
    await runComposable(() => useDocumentTitle(() => `ジョブ ${id.value}`))

    expect(document.title).toBe('ジョブ job-1 - Loreley 管理')
  })
})
