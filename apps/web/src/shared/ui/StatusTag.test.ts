import { afterEach, describe, expect, it, vi } from 'vitest'

import { mountInLayout } from '../../../tests/support/mount'
import StatusTag from './StatusTag.vue'

afterEach(() => vi.restoreAllMocks())

describe('StatusTag', () => {
  it('登録済みの値は、表の文言とアイコンで描き、警告しない', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})

    const { wrapper } = await mountInLayout(StatusTag, { props: { kind: 'job', value: 'failed' } })

    expect(wrapper.text()).toBe('失敗')
    // アイコンは SVG(文言のないアイコンだけのタグにしない)
    expect(wrapper.find('svg').exists()).toBe(true)
    expect(warn).not.toHaveBeenCalled()
  })

  it('色は `*-container`(淡い面)。枠線のみの値は outlined になる', async () => {
    const { wrapper: filled } = await mountInLayout(StatusTag, {
      props: { kind: 'job', value: 'succeeded' },
    })
    const { wrapper: outlined } = await mountInLayout(StatusTag, {
      props: { kind: 'health', value: 'not_configured' },
    })

    expect(filled.find('.v-chip').classes()).toContain('bg-success-container')
    expect(outlined.find('.v-chip').classes()).toContain('v-chip--variant-outlined')
    expect(outlined.find('.v-chip').classes()).toContain('text-on-secondary-container')
  })

  it('未登録の値は、中立(secondary-container)・アイコンなしで値をそのまま出し、開発時に警告する', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})

    const { wrapper } = await mountInLayout(StatusTag, {
      props: { kind: 'cluster', value: 'purple-unregistered' },
    })

    expect(wrapper.text()).toBe('purple-unregistered')
    expect(wrapper.find('.v-chip').classes()).toContain('bg-secondary-container')
    expect(wrapper.find('svg').exists()).toBe(false)
    expect(warn).toHaveBeenCalledTimes(1)
    expect(warn.mock.calls[0]?.[0]).toContain('kind=cluster, value=purple-unregistered')
  })

  it('同じ未登録の組では、何度描いても警告は 1 回(一覧の行ごとに出さない)', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})

    await mountInLayout(StatusTag, { props: { kind: 'job', value: 'warn-once-value' } })
    await mountInLayout(StatusTag, { props: { kind: 'job', value: 'warn-once-value' } })
    await mountInLayout(StatusTag, { props: { kind: 'index', value: 'warn-once-value' } })

    // job の 1 回 + index の 1 回(kind が違えば別の組)
    expect(warn).toHaveBeenCalledTimes(2)
  })
})
