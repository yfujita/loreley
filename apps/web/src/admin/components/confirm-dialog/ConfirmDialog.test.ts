import type { VueWrapper } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick, ref } from 'vue'

import { mountInLayout } from '../../../../tests/support/mount'
import ConfirmDialog from './ConfirmDialog.vue'
import type { DialogLevel, Severity } from './dialogLevel'

type HostProps = {
  level: DialogLevel
  severities?: Severity[]
  disabledReason?: string | null
  pending?: boolean
  hideExecute?: boolean
  body?: () => unknown
}

/** 開く操作のボタンと、ダイアログを v-model で持つ土台。イベントを記録する。 */
async function mountDialog(props: HostProps, options: { open?: boolean } = {}) {
  const events: string[] = []
  const isOpen = ref(options.open ?? true)
  // テストが後から props を変えられるように、土台の外の ref に持つ。
  const state = ref<HostProps>(props)
  const Host = defineComponent({
    setup() {
      return () => [
        h('button', { id: 'opener', onClick: () => (isOpen.value = true) }, '開く'),
        h(
          ConfirmDialog,
          {
            modelValue: isOpen.value,
            'onUpdate:modelValue': (open: boolean) => {
              events.push(`update:modelValue(${open})`)
              isOpen.value = open
            },
            onExecute: () => events.push('execute'),
            onCancel: () => events.push('cancel'),
            title: 'ロックを解放しますか',
            executeLabel: 'ロックを解放',
            testid: 'dlg-lock-release',
            level: state.value.level,
            severities: state.value.severities,
            disabledReason: state.value.disabledReason ?? null,
            pending: state.value.pending ?? false,
            hideExecute: state.value.hideExecute ?? false,
          },
          { default: state.value.body ?? (() => h('input', { id: 'body-input' })) },
        ),
      ]
    },
  })
  const mounted = await mountInLayout(Host)
  await nextTick()
  return { ...mounted, events, isOpen, state }
}

function dialog(): HTMLElement {
  const element = document.querySelector<HTMLElement>('[data-testid="dlg-lock-release"]')
  if (element === null) throw new Error('ダイアログが開いていません')
  return element
}
function button(name: string): HTMLButtonElement {
  const found = [...dialog().querySelectorAll('button')].find((b) => b.textContent?.trim() === name)
  if (found === undefined) throw new Error(`ボタンがありません: ${name}`)
  return found
}

describe('ConfirmDialog(DS 4.8)', () => {
  it('role=dialog・aria-modal・見出しに結んだ aria-labelledby・testid が、同じ要素に付く', async () => {
    await mountDialog({ level: 'confirm' })

    const element = dialog()
    expect(element.getAttribute('role')).toBe('dialog')
    expect(element.getAttribute('aria-modal')).toBe('true')
    const heading = element.querySelector('h2')
    expect(heading?.textContent).toBe('ロックを解放しますか')
    expect(element.getAttribute('aria-labelledby')).toBe(heading?.id)
  })

  it('要確認・標準: 帯なし・実行ボタンは primary・実行ボタンは有効で理由を出さない', async () => {
    await mountDialog({ level: 'confirm' })

    expect(dialog().querySelector('.confirm-dialog__band')).toBeNull()
    expect(button('ロックを解放').classList).toContain('bg-primary')
    expect(button('ロックを解放').disabled).toBe(false)
    expect(dialog().querySelector('.confirm-dialog__reason')).toBeNull()
  })

  it.each<[string, DialogLevel, Severity[], string]>([
    ['警告つき・再書き込み=琥珀', 'confirm-warning', ['warning'], 'warning'],
    ['警告つき・強制削除=赤', 'confirm-warning', ['danger'], 'error'],
    ['警告つき・両方=赤(最も重い指定)', 'confirm-warning', ['warning', 'danger'], 'error'],
    ['要入力確認=赤', 'confirm-typed', [], 'error'],
  ])('%s: 上端の帯と実行ボタンが同じ色', async (_name, level, severities, color) => {
    await mountDialog({ level, severities })

    expect(dialog().querySelector('.confirm-dialog')?.classList).toContain(
      `confirm-dialog--${color}`,
    )
    expect(dialog().querySelector('.confirm-dialog__band')).not.toBeNull()
    expect(button('ロックを解放').classList).toContain(`bg-${color}`)
  })

  it('実行できない理由があれば、実行ボタンを無効にし、理由を実行ボタンの下に出して aria-describedby で結ぶ', async () => {
    await mountDialog({
      level: 'confirm-warning',
      disabledReason: '確認にチェックすると解放できます。',
    })

    const execute = button('ロックを解放')
    const reason = dialog().querySelector('.confirm-dialog__reason')
    expect(execute.disabled).toBe(true)
    expect(reason?.textContent?.trim()).toBe('確認にチェックすると解放できます。')
    expect(execute.getAttribute('aria-describedby')).toBe(reason?.id)
  })

  it('理由が消える(null)と、実行ボタンが有効になる', async () => {
    const { state } = await mountDialog({ level: 'confirm-warning', disabledReason: '理由' })
    expect(button('ロックを解放').disabled).toBe(true)

    state.value = { level: 'confirm-warning', disabledReason: null }
    await nextTick()

    expect(button('ロックを解放').disabled).toBe(false)
    expect(button('ロックを解放').getAttribute('aria-describedby')).toBeNull()
  })

  it('実行を押すと execute を通知する。無効のあいだは押せない', async () => {
    const { events } = await mountDialog({ level: 'confirm' })

    button('ロックを解放').click()

    expect(events).toEqual(['execute'])
  })

  it('実行中(pending)は、実行ボタンもキャンセルも無効にする(二重送信を防ぐ)', async () => {
    await mountDialog({ level: 'confirm', pending: true })

    expect(button('ロックを解放').disabled).toBe(true)
    expect(button('キャンセル').disabled).toBe(true)
  })

  it('キャンセルを押すと、閉じて cancel を通知する', async () => {
    const { events, isOpen } = await mountDialog({ level: 'confirm-warning' })

    button('キャンセル').click()
    await nextTick()

    expect(events).toEqual(['update:modelValue(false)', 'cancel'])
    expect(isOpen.value).toBe(false)
  })

  it('hideExecute(結果の確認後など)は実行ボタンと理由を出さず、閉じるだけにする', async () => {
    await mountDialog({ level: 'confirm', hideExecute: true, disabledReason: '理由' })

    expect(() => button('ロックを解放')).toThrow()
    expect(dialog().querySelector('.confirm-dialog__reason')).toBeNull()
    expect(button('キャンセル')).toBeDefined()
  })

  function pressEscape(): void {
    const content = dialog().querySelector<HTMLElement>('.v-overlay__content') ?? dialog()
    content.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
  }

  it('Esc: 要確認・標準は閉じ、update:modelValue(false) と cancel をこの順に通知する', async () => {
    const { isOpen, events } = await mountDialog({ level: 'confirm' })

    pressEscape()
    await nextTick()

    expect(isOpen.value).toBe(false)
    expect(events).toEqual(['update:modelValue(false)', 'cancel'])
  })

  // 背面クリックによる閉じ(外側クリック)は、Vuetify が isTrusted でないイベントを無視するため jsdom では確かめられない。
  // 実ブラウザの E2E(DLG。フェーズ 5)で確認する。

  it.each<DialogLevel>(['confirm-warning', 'confirm-typed'])(
    'Esc: %s は閉じない(persistent)。キャンセルだけで閉じる',
    async (level) => {
      const { isOpen } = await mountDialog({ level })

      pressEscape()
      await nextTick()

      expect(isOpen.value).toBe(true)
    },
  )

  it('実行中は、標準でも Esc で閉じない(失敗のアラートを見逃さない)', async () => {
    const { isOpen } = await mountDialog({ level: 'confirm', pending: true })

    pressEscape()
    await nextTick()

    expect(isOpen.value).toBe(true)
  })

  // jsdom には Web Animations がなく、トランジションの終了(`after-enter`)が来ない。実際の開閉でのフォーカスは
  // Chromium で確認する(tests/e2e。DLG の E2E はフェーズ 5)。ここでは、`after-enter` を受けた後の振る舞いを確かめる。
  /** VDialog が出す `after-enter` を、ConfirmDialog の `onAfterEnter` へ渡す。 */
  async function finishEnter(wrapper: VueWrapper): Promise<void> {
    wrapper.findComponent({ name: 'VDialog' }).vm.$emit('afterEnter')
    await nextTick()
  }

  async function mountAndEnter(props: HostProps) {
    const mounted = await mountDialog(props)
    await finishEnter(mounted.wrapper)
    return mounted
  }

  it('初期フォーカス: 要確認・標準は見出し(tabindex=-1)', async () => {
    await mountAndEnter({ level: 'confirm' })

    expect(document.activeElement?.tagName).toBe('H2')
    expect(document.activeElement?.getAttribute('tabindex')).toBe('-1')
  })

  it.each<DialogLevel>(['confirm-warning', 'confirm-typed'])(
    '初期フォーカス: %s は最初の入力要素(オプション・確認チェック・入力欄)',
    async (level) => {
      await mountAndEnter({ level })

      expect(document.activeElement?.id).toBe('body-input')
    },
  )

  it('初期フォーカス: 警告つきで入力要素がなければ、見出し', async () => {
    await mountAndEnter({ level: 'confirm-warning', body: () => h('p', '説明だけ') })

    expect(document.activeElement?.tagName).toBe('H2')
  })

  it('閉じたら、開く直前にフォーカスがあった操作ボタンへ戻す', async () => {
    const { wrapper, isOpen } = await mountDialog({ level: 'confirm' }, { open: false })
    const opener = wrapper.find<HTMLButtonElement>('#opener').element
    opener.focus()

    opener.click()
    await nextTick()
    // ダイアログの中へフォーカスが移った後(初期フォーカス)に閉じる。
    await finishEnter(wrapper)
    expect(document.activeElement?.tagName).toBe('H2')
    button('キャンセル').click()
    await nextTick()
    await nextTick()

    expect(isOpen.value).toBe(false)
    expect(document.activeElement).toBe(opener)
  })

  it('戻り先が DOM から外れていれば(メニューの項目から開いた場合など)、戻さない', async () => {
    const { wrapper } = await mountDialog({ level: 'confirm' }, { open: false })
    const opener = wrapper.find<HTMLButtonElement>('#opener').element
    opener.focus()
    opener.click()
    await nextTick()
    opener.remove()

    const focus = vi.spyOn(opener, 'focus')
    button('キャンセル').click()
    await nextTick()
    await nextTick()

    expect(focus).not.toHaveBeenCalled()
    expect(document.activeElement).not.toBe(opener)
  })
})
