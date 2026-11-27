import { describe, expect, it, vi } from 'vitest'

import { useSnackbar } from '@/shared/ui/useSnackbar'
import type { ApiError } from '@/shared/api/apiError'

import { runComposable } from '../../../tests/support/composableTesting'
import { useOperationDialog } from './useOperationDialog'

const api = (status: number, code: string, extra: Partial<ApiError> = {}): ApiError =>
  ({
    kind: 'api',
    status,
    code,
    retryable: false,
    outcomeUnknown: false,
    ...extra,
  }) as ApiError

/** 解決・失敗を、テストから制御できる実行関数。 */
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

async function mountDialog<TInput, TResult>(
  options: Parameters<typeof useOperationDialog<TInput, TResult>>[0],
) {
  const { result } = await runComposable(() => useOperationDialog(options))
  return result
}

describe('useOperationDialog(E 7.4・6.3。F 3.8)', () => {
  it('open で開き、前回の失敗を残さない。close で閉じる', async () => {
    const dialog = await mountDialog({
      operation: 'startCrawl',
      execute: () => Promise.reject(api(409, 'lock_held')),
    })

    dialog.open()
    expect(dialog.isOpen.value).toBe(true)
    await dialog.run({})
    expect(dialog.error.value).not.toBeNull()

    dialog.close()
    expect(dialog.isOpen.value).toBe(false)
    dialog.open()
    expect(dialog.error.value).toBeNull()
  })

  it('成功: 閉じて、スナックバーを出し、呼び出し側の onSuccess を(閉じた後に)呼ぶ', async () => {
    const order: string[] = []
    const dialog = await mountDialog({
      operation: 'startCrawl',
      execute: async (input: { sourceId: string }) => ({ job_id: `job-for-${input.sourceId}` }),
      successNotice: (result) => ({
        text: `クロールを受け付けました(ジョブ ID: ${result.job_id})`,
        action: { label: 'ジョブを表示', onClick: () => {} },
      }),
      onSuccess: (result) => order.push(`success:${result.job_id}:open=${dialog.isOpen.value}`),
    })
    dialog.open()

    await dialog.run({ sourceId: 'demo' })

    expect(dialog.isOpen.value).toBe(false)
    expect(useSnackbar().message.value?.text).toBe(
      'クロールを受け付けました(ジョブ ID: job-for-demo)',
    )
    expect(useSnackbar().message.value?.action?.label).toBe('ジョブを表示')
    expect(order).toEqual(['success:job-for-demo:open=false'])
    expect(dialog.error.value).toBeNull()
  })

  it('成功でも、通知が null(released=false など)ならスナックバーを出さない', async () => {
    const dialog = await mountDialog({
      operation: 'releaseLock',
      execute: async () => ({ released: false }),
      successNotice: () => null,
    })
    dialog.open()

    await dialog.run(undefined)

    expect(useSnackbar().message.value).toBeNull()
  })

  it('失敗: 開いたまま、describeError の結果をダイアログ内アラートに出す(消えない)。スナックバーは使わない', async () => {
    const dialog = await mountDialog({
      operation: 'startCrawl',
      execute: () => Promise.reject(api(409, 'lock_held')),
    })
    dialog.open()

    await dialog.run({})

    expect(dialog.isOpen.value).toBe(true)
    expect(dialog.error.value).toMatchObject({ target: 'dialog-alert', outcomeUnknown: false })
    expect(useSnackbar().message.value).toBeNull()
  })

  it('結果不明(timeout・通信断・Nginx の HTML)は、outcomeUnknown で再試行を出さない判断ができる', async () => {
    const dialog = await mountDialog({
      operation: 'startCrawl',
      execute: () => Promise.reject({ kind: 'timeout' }),
    })
    dialog.open()

    await dialog.run({})

    expect(dialog.error.value?.outcomeUnknown).toBe(true)
    expect(dialog.error.value?.retryable).toBe(false)
  })

  it('isApiError でない例外も、結果不明(invalid_response)として扱う(落ちない)', async () => {
    const dialog = await mountDialog({
      operation: 'cancelJob',
      execute: () => Promise.reject(new Error('boom')),
    })
    dialog.open()

    await dialog.run({})

    expect(dialog.isOpen.value).toBe(true)
    expect(dialog.error.value?.outcomeUnknown).toBe(true)
  })

  it('実行中は isPending。二重送信を防ぐ(実行中の run は無視し、execute は 1 回だけ)', async () => {
    const pending = deferred<{ ok: true }>()
    const execute = vi.fn(() => pending.promise)
    const dialog = await mountDialog({ operation: 'startCrawl', execute })
    dialog.open()

    const first = dialog.run({})
    await dialog.run({})
    await dialog.run({})

    expect(dialog.isPending.value).toBe(true)
    expect(execute).toHaveBeenCalledTimes(1)
    pending.resolve({ ok: true })
    await first
    expect(dialog.isPending.value).toBe(false)
  })

  it('実行中は閉じられない(失敗のアラートを見逃さない)。終われば閉じられる', async () => {
    const pending = deferred<{ ok: true }>()
    const dialog = await mountDialog({ operation: 'startCrawl', execute: () => pending.promise })
    dialog.open()
    const running = dialog.run({})

    dialog.close()
    expect(dialog.isOpen.value).toBe(true)

    pending.reject(api(409, 'lock_held'))
    await running
    dialog.close()
    expect(dialog.isOpen.value).toBe(false)
  })

  it('失敗の後に、もう一度実行できる(isPending が戻り、error は実行のたびに消える)', async () => {
    let attempts = 0
    const dialog = await mountDialog({
      operation: 'startCrawl',
      execute: async () => {
        attempts += 1
        if (attempts === 1) throw api(503, 'crawler_unreachable', { retryable: true })
        return { job_id: 'j' }
      },
    })
    dialog.open()

    await dialog.run({})
    expect(dialog.error.value?.retryable).toBe(true)
    expect(dialog.isPending.value).toBe(false)

    await dialog.run({})
    expect(dialog.error.value).toBeNull()
    expect(dialog.isOpen.value).toBe(false)
  })

  it('成功扱いの失敗(取消の 409 job_already_finished): 閉じて onAlreadyDone を呼ぶ。アラートは出さない', async () => {
    const onAlreadyDone = vi.fn()
    const dialog = await mountDialog({
      operation: 'cancelJob',
      execute: () =>
        Promise.reject(api(409, 'job_already_finished', { details: { status: 'succeeded' } })),
      onAlreadyDone,
    })
    dialog.open()

    await dialog.run({})

    expect(dialog.isOpen.value).toBe(false)
    expect(dialog.error.value).toBeNull()
    expect(onAlreadyDone).toHaveBeenCalledTimes(1)
    expect(onAlreadyDone.mock.calls[0]?.[0]).toMatchObject({ target: 'success' })
  })

  it('成功扱いの失敗で onAlreadyDone がなくても、閉じるだけで落ちない', async () => {
    const dialog = await mountDialog({
      operation: 'cancelJob',
      execute: () => Promise.reject(api(409, 'job_already_finished')),
    })
    dialog.open()

    await dialog.run({})

    expect(dialog.isOpen.value).toBe(false)
  })

  it('成功の後始末(onSuccess)が例外を投げても、操作の失敗にはしない(アラートを出さない)。isPending は戻る', async () => {
    const dialog = await mountDialog({
      operation: 'startCrawl',
      execute: async () => ({ ok: true }),
      onSuccess: () => {
        throw new Error('遷移に失敗')
      },
    })
    dialog.open()

    await expect(dialog.run({})).rejects.toThrow('遷移に失敗')

    expect(dialog.isPending.value).toBe(false)
    expect(dialog.error.value).toBeNull()
    expect(dialog.isOpen.value).toBe(false)
  })
})
