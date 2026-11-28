import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { h, nextTick, reactive } from 'vue'

import type { ClusterStatus } from '@/admin/lib/clusterValues'

import { mountInLayout } from '../../../../tests/support/mount'
import IndexFilter from './IndexFilter.vue'

type Props = {
  name: string
  states: readonly ClusterStatus[]
  hasCondition: boolean
  disabled?: boolean
}

async function mountFilter(props: Partial<Props> = {}) {
  const state = reactive<Props>({ name: '', states: [], hasCondition: false, ...props })
  const events: [string, unknown][] = []
  // 関数コンポーネント(`state` の変更で再描画される)
  const Host = () =>
    h(IndexFilter, {
      ...state,
      'onUpdate:name': (value: string) => events.push(['name', value]),
      'onUpdate:states': (value: ClusterStatus[]) => events.push(['states', value]),
      onClear: () => events.push(['clear', null]),
    })
  const { wrapper } = await mountInLayout(Host)
  return {
    wrapper,
    state,
    events,
    input: () => wrapper.find('input[type="text"]'),
    checkbox: (name: string) =>
      wrapper.findAll('input[type="checkbox"]').find((el) => {
        const label = wrapper.find(`label[for="${el.attributes('id')}"]`)
        return label.text() === name
      }),
    clear: () => wrapper.findAll('button').find((b) => b.text() === '条件を解除')!,
  }
}

describe('IndexFilter(DS 4.15・opensearch 3.5)', () => {
  describe('構成・アクセシビリティ', () => {
    it('role=search のフォーム(aria-label=インデックスの絞り込み)・data-testid=o1-filter', async () => {
      const { wrapper } = await mountFilter()

      const form = wrapper.find('form')
      expect(form.attributes('role')).toBe('search')
      expect(form.attributes('aria-label')).toBe('インデックスの絞り込み')
      expect(form.attributes('data-testid')).toBe('o1-filter')
    })

    it('名前の入力は <label>「インデックス名」付きの type=text。説明(隠し文)を aria-describedby で結ぶ', async () => {
      const { wrapper, input } = await mountFilter()

      const id = input().attributes('id')!
      expect(wrapper.find(`label[for="${id}"]`).text()).toBe('インデックス名')
      expect(input().attributes('placeholder')).toBe('名前の一部(例: logs)')
      expect(input().attributes('autocomplete')).toBe('off')
      expect(input().attributes('spellcheck')).toBe('false')
      const helpId = input().attributes('aria-describedby')!
      expect(wrapper.find(`#${helpId}`).text()).toBe(
        '大文字小文字は区別しません。入力するとすぐに絞り込みます。',
      )
      expect(wrapper.find(`#${helpId}`).classes()).toContain('sr-only')
    })

    it('状態は fieldset + legend の複数選択。チェックボックス 3 つは red → yellow → green の順で、名前は状態の語だけ', async () => {
      const { wrapper } = await mountFilter()

      expect(wrapper.find('fieldset legend').text()).toBe(
        '状態(複数選択できます。選ばなければすべて)',
      )
      const names = wrapper
        .findAll('input[type="checkbox"]')
        .map((el) => wrapper.find(`label[for="${el.attributes('id')}"]`).text())
      expect(names).toEqual(['red', 'yellow', 'green'])
    })

    it('同じ画面に 2 つ置いても、label の for・aria-describedby の id が衝突しない', async () => {
      const Host = () =>
        h('div', [
          h(IndexFilter, { name: '', states: [], hasCondition: false }),
          h(IndexFilter, { name: '', states: [], hasCondition: false }),
        ])
      const { wrapper } = await mountInLayout(Host)

      const ids = wrapper.findAll('[id]').map((el) => el.attributes('id'))
      expect(new Set(ids).size).toBe(ids.length)
    })
  })

  describe('名前の入力(250ms の debounce・Enter・IME)', () => {
    beforeEach(() => {
      vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    })
    afterEach(() => {
      vi.useRealTimers()
    })

    it('入力から 250ms 待って通知する(249ms では通知しない)', async () => {
      const { input, events } = await mountFilter()

      await input().setValue('logs')
      await vi.advanceTimersByTimeAsync(249)
      expect(events).toEqual([])
      await vi.advanceTimersByTimeAsync(1)
      expect(events).toEqual([['name', 'logs']])
    })

    it('続けて入力すると、待ち時間をやり直し、最後の値だけを通知する', async () => {
      const { input, events } = await mountFilter()

      await input().setValue('l')
      await vi.advanceTimersByTimeAsync(200)
      await input().setValue('lo')
      await vi.advanceTimersByTimeAsync(200)
      expect(events).toEqual([])
      await vi.advanceTimersByTimeAsync(50)
      expect(events).toEqual([['name', 'lo']])
    })

    it('Enter(フォームの送信)は、待たずにすぐ通知する。ページは移動しない(送信を止める)', async () => {
      const { wrapper, input, events } = await mountFilter()
      await input().setValue('logs')

      const submit = new Event('submit', { cancelable: true })
      wrapper.find('form').element.dispatchEvent(submit)
      await nextTick()

      expect(events).toEqual([['name', 'logs']])
      expect(submit.defaultPrevented).toBe(true)
    })

    it('IME の変換中は通知しない(待ち時間を過ぎても)。確定(compositionend)後に通知する', async () => {
      const { input, events } = await mountFilter()

      await input().trigger('compositionstart')
      await input().setValue('ろぐ')
      await vi.advanceTimersByTimeAsync(1000)
      expect(events).toEqual([])

      await input().trigger('compositionend')
      expect(events).toEqual([['name', 'ろぐ']])
    })

    it('外から名前が変わったとき(戻る・解除)は、入力欄に反映する', async () => {
      const { state, input } = await mountFilter({ name: 'logs' })
      expect((input().element as HTMLInputElement).value).toBe('logs')

      state.name = 'docs'
      await nextTick()

      expect((input().element as HTMLInputElement).value).toBe('docs')
    })

    it('自分が通知した値が URL に反映されるまでの間に続けて入力しても、入力欄を書き換えない', async () => {
      const { state, input, events } = await mountFilter()
      await input().setValue('a')
      await vi.advanceTimersByTimeAsync(250)
      expect(events).toEqual([['name', 'a']])

      // 続けて入力('ab')した直後に、先の通知('a')が URL から戻ってくる
      await input().setValue('ab')
      state.name = 'a'
      await nextTick()

      expect((input().element as HTMLInputElement).value).toBe('ab')
    })

    it('入力の末尾の空白は URL の値では除かれる。その反映で入力欄を書き換えない', async () => {
      const { state, input } = await mountFilter()
      await input().setValue('logs ')
      await vi.advanceTimersByTimeAsync(250)

      state.name = 'logs'
      await nextTick()

      expect((input().element as HTMLInputElement).value).toBe('logs ')
    })
  })

  describe('状態のチェック', () => {
    it('URL の条件のとおりにチェックを表示する(3 つとも選んだ表示も保つ)', async () => {
      const { checkbox } = await mountFilter({ states: ['red', 'yellow', 'green'] })

      for (const name of ['red', 'yellow', 'green']) {
        expect((checkbox(name)!.element as HTMLInputElement).checked).toBe(true)
      }
    })

    it('チェックの切替で、すぐに新しい選択を通知する', async () => {
      const { checkbox, events } = await mountFilter({ states: ['yellow'] })

      await checkbox('green')!.setValue(true)
      expect(events.at(-1)).toEqual(['states', ['yellow', 'green']])
      await checkbox('yellow')!.setValue(false)
      expect(events.at(-1)).toEqual(['states', []])
    })
  })

  describe('条件を解除', () => {
    it('条件がないときは aria-disabled=true(disabled にしない)。押しても何も起きず、フォーカスも動かさない', async () => {
      const { clear, input, events } = await mountFilter({ hasCondition: false })

      expect(clear().attributes('aria-disabled')).toBe('true')
      expect(clear().attributes('disabled')).toBeUndefined()
      await clear().trigger('click')

      expect(events).toEqual([])
      expect(document.activeElement).not.toBe(input().element)
    })

    it('条件があるときは aria-disabled=false。押すと、入力を空にして通知し、名前の入力欄へフォーカスを移す', async () => {
      const { clear, input, events } = await mountFilter({ name: 'logs', hasCondition: true })
      expect(clear().attributes('aria-disabled')).toBe('false')

      await clear().trigger('click')

      expect(events).toEqual([['clear', null]])
      expect((input().element as HTMLInputElement).value).toBe('')
      expect(document.activeElement).toBe(input().element)
    })
  })

  describe('読み込み中(disabled)', () => {
    it('入力・チェック・解除をすべて無効にして出す。URL から復元した条件の値は表示する', async () => {
      const { wrapper, input, checkbox, clear } = await mountFilter({
        name: 'logs',
        states: ['yellow'],
        disabled: true,
      })

      expect((input().element as HTMLInputElement).value).toBe('logs')
      expect((input().element as HTMLInputElement).disabled).toBe(true)
      expect((checkbox('yellow')!.element as HTMLInputElement).checked).toBe(true)
      for (const el of wrapper.findAll('input[type="checkbox"]')) {
        expect((el.element as HTMLInputElement).disabled).toBe(true)
      }
      expect(clear().attributes('disabled')).toBeDefined()
    })
  })
})
