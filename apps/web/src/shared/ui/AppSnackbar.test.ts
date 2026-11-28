import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import { mountInLayout } from '../../../tests/support/mount'
import AppSnackbar from './AppSnackbar.vue'
import { useSnackbar } from './useSnackbar'

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

function snackbarText(): string {
  return document.querySelector('.v-snackbar')?.textContent ?? ''
}

describe('AppSnackbar(DS 4.7)', () => {
  it('通知がなければ何も出さない', async () => {
    await mountInLayout(AppSnackbar)

    expect(document.querySelector('.v-snackbar')).toBeNull()
  })

  it('通知を role=status(aria-live=polite)で出し、閉じるボタンを持つ', async () => {
    await mountInLayout(AppSnackbar)

    useSnackbar().show('クロールを受け付けました')
    await nextTick()
    await vi.advanceTimersByTimeAsync(50)

    const status = document.querySelector('.v-snackbar [role="status"]')
    expect(snackbarText()).toContain('クロールを受け付けました')
    expect(status?.getAttribute('aria-live')).toBe('polite')
    expect(status?.textContent).toContain('クロールを受け付けました')
    expect(document.querySelector('[aria-label="通知を閉じる"]')).not.toBeNull()
  })

  it('6 秒で消える', async () => {
    await mountInLayout(AppSnackbar)
    const { message, show } = useSnackbar()

    show('受付')
    await vi.advanceTimersByTimeAsync(5_900)
    expect(message.value).not.toBeNull()

    await vi.advanceTimersByTimeAsync(200)
    expect(message.value).toBeNull()
  })

  it('新しい通知で置き換えると、6 秒のタイマーもやり直す', async () => {
    await mountInLayout(AppSnackbar)
    const { message, show } = useSnackbar()

    show('1 件目')
    await vi.advanceTimersByTimeAsync(4_000)
    show('2 件目')
    await vi.advanceTimersByTimeAsync(4_000)

    // 1 件目から数えれば 8 秒だが、2 件目のタイマーはまだ残っている。
    expect(message.value?.text).toBe('2 件目')
    expect(snackbarText()).toContain('2 件目')
    expect(snackbarText()).not.toContain('1 件目')
  })

  it('閉じるボタンで閉じる', async () => {
    await mountInLayout(AppSnackbar)
    const { message, show } = useSnackbar()
    show('受付')
    await vi.advanceTimersByTimeAsync(50)

    document.querySelector<HTMLElement>('[aria-label="通知を閉じる"]')?.click()
    await nextTick()

    expect(message.value).toBeNull()
  })

  it('操作(「ジョブを表示」)を押すと、実行して閉じる', async () => {
    await mountInLayout(AppSnackbar)
    const { message, show } = useSnackbar()
    const onClick = vi.fn()
    show('受付', { action: { label: 'ジョブを表示', onClick } })
    await vi.advanceTimersByTimeAsync(50)

    const action = [...document.querySelectorAll<HTMLElement>('.app-snackbar__action')].find(
      (element) => element.textContent?.includes('ジョブを表示'),
    )
    action?.click()
    await nextTick()

    expect(onClick).toHaveBeenCalledTimes(1)
    expect(message.value).toBeNull()
  })
})
