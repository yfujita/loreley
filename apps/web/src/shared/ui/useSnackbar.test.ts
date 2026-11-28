import { describe, expect, it } from 'vitest'

import { useSnackbar } from './useSnackbar'

describe('useSnackbar(DS 4.7)', () => {
  it('通知を出し、閉じると消える(同時に 1 つ)', () => {
    const { message, show, close } = useSnackbar()

    show('クロールを受け付けました')
    expect(message.value?.text).toBe('クロールを受け付けました')
    expect(message.value?.action).toBeNull()

    close()
    expect(message.value).toBeNull()
  })

  it('新しい通知で置き換える。置き換えのたびに id が変わる(表示とタイマーをやり直すため)', () => {
    const { message, show } = useSnackbar()

    show('1 件目')
    const firstId = message.value?.id
    show('2 件目')

    expect(message.value?.text).toBe('2 件目')
    expect(message.value?.id).not.toBe(firstId)
  })

  it('操作(「ジョブを表示」)を持てる', () => {
    const { message, show } = useSnackbar()
    const onClick = () => {}

    show('受付', { action: { label: 'ジョブを表示', onClick } })

    expect(message.value?.action).toEqual({ label: 'ジョブを表示', onClick })
  })

  it('どこから呼んでも同じ状態を見る(アプリで 1 つ)', () => {
    useSnackbar().show('共有')

    expect(useSnackbar().message.value?.text).toBe('共有')
  })
})
