import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick, ref } from 'vue'

import { runComposable } from '../../../tests/support/composableTesting'
import { useDebouncedRef } from './useDebouncedRef'

describe('useDebouncedRef', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] })
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('最初の値はそのまま入る', async () => {
    const source = ref('a')
    const { result } = await runComposable(() => useDebouncedRef(source, 300))

    expect(result.value).toBe('a')
  })

  it('変更から待ち時間が過ぎるまで反映しない(299 ミリ秒では反映せず、300 ミリ秒で反映する)', async () => {
    const source = ref('a')
    const { result } = await runComposable(() => useDebouncedRef(source, 300))

    source.value = 'b'
    await nextTick()
    await vi.advanceTimersByTimeAsync(299)
    expect(result.value).toBe('a')
    await vi.advanceTimersByTimeAsync(1)
    expect(result.value).toBe('b')
  })

  it('続けて変更すると、待ち時間をやり直し、最後の値だけ反映する', async () => {
    const source = ref('a')
    const { result } = await runComposable(() => useDebouncedRef(source, 300))

    source.value = 'b'
    await nextTick()
    await vi.advanceTimersByTimeAsync(200)
    source.value = 'c'
    await nextTick()
    await vi.advanceTimersByTimeAsync(200)
    expect(result.value).toBe('a')
    await vi.advanceTimersByTimeAsync(100)
    expect(result.value).toBe('c')
  })

  it('スコープ(コンポーネント)の破棄でタイマーを止める', async () => {
    const source = ref('a')
    const { result, wrapper } = await runComposable(() => useDebouncedRef(source, 300))

    source.value = 'b'
    await nextTick()
    wrapper.unmount()
    await vi.advanceTimersByTimeAsync(1000)

    expect(result.value).toBe('a')
    expect(vi.getTimerCount()).toBe(0)
  })

  it('読み取り専用(代入できない)', async () => {
    const source = ref('a')
    const { result } = await runComposable(() => useDebouncedRef(source, 300))

    // @ts-expect-error 読み取り専用の ref に代入しようとしている
    result.value = 'z'

    expect(result.value).toBe('a')
  })
})
