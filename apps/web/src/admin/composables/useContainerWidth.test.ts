import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick, ref } from 'vue'

import { mountInLayout } from '../../../tests/support/mount'
import { useContainerWidth } from './useContainerWidth'

type ObserverRecord = {
  callback: ResizeObserverCallback
  observed: Element[]
  disconnected: boolean
}

const observers: ObserverRecord[] = []
const originalResizeObserver = globalThis.ResizeObserver

beforeEach(() => {
  observers.length = 0
  class RecordingResizeObserver implements ResizeObserver {
    private readonly record: ObserverRecord
    constructor(callback: ResizeObserverCallback) {
      this.record = { callback, observed: [], disconnected: false }
      observers.push(this.record)
    }
    observe(target: Element): void {
      this.record.observed.push(target)
    }
    unobserve(): void {}
    disconnect(): void {
      this.record.disconnected = true
    }
  }
  globalThis.ResizeObserver = RecordingResizeObserver
})
afterEach(() => {
  globalThis.ResizeObserver = originalResizeObserver
})

/** カード(`#card`)を観測している ResizeObserver(Vuetify の部品も別の ResizeObserver を作るので、対象で絞る)。 */
function cardObserver(): ObserverRecord | undefined {
  return observers.find((observer) =>
    observer.observed.some((element) => element instanceof HTMLElement && element.id === 'card'),
  )
}

function resizeTo(width: number): void {
  const entry = { contentRect: { width } } as ResizeObserverEntry
  cardObserver()?.callback([entry], {} as ResizeObserver)
}

async function mountWatcher() {
  const widths: number[] = []
  const show = ref(true)
  const Host = defineComponent({
    setup() {
      const element = ref<HTMLElement | null>(null)
      const width = useContainerWidth(element)
      return () => {
        widths.push(width.value)
        return show.value ? h('div', { ref: element, id: 'card' }) : null
      }
    },
  })
  const mounted = await mountInLayout(Host)
  await nextTick()
  return { ...mounted, widths, show }
}

describe('useContainerWidth(DS 4.3: 列の省略は、viewport でなく表を載せるカードの幅で決める)', () => {
  it('要素がまだない間は 0。要素ができたら観測を始める', async () => {
    const { wrapper } = await mountWatcher()

    expect(cardObserver()?.observed).toEqual([wrapper.find('#card').element])
  })

  it('ResizeObserver の通知で、幅を更新する(contentRect の幅)', async () => {
    const { widths } = await mountWatcher()

    resizeTo(920)
    await nextTick()
    resizeTo(719)
    await nextTick()

    expect(widths[widths.length - 1]).toBe(719)
    expect(widths).toContain(920)
  })

  it('要素が外れると、観測をやめて幅を 0 に戻す', async () => {
    const { widths, show } = await mountWatcher()
    resizeTo(800)
    await nextTick()

    show.value = false
    await nextTick()
    await nextTick()

    expect(cardObserver()?.disconnected).toBe(true)
    expect(widths[widths.length - 1]).toBe(0)
  })

  it('コンポーネントが外れると、観測をやめる(後始末)', async () => {
    const { wrapper } = await mountWatcher()

    wrapper.unmount()

    expect(cardObserver()?.disconnected).toBe(true)
  })

  it('観測を始める前に、要素の今の幅(getBoundingClientRect)を反映する(最初の通知を待たない)', async () => {
    const rect = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
      width: 640,
      height: 0,
      x: 0,
      y: 0,
      top: 0,
      left: 0,
      right: 640,
      bottom: 0,
      toJSON: () => ({}),
    })

    const { widths } = await mountWatcher()

    // ResizeObserver から通知が来る前(通知なし)に、初期の幅が入っている
    expect(widths[widths.length - 1]).toBe(640)
    rect.mockRestore()
  })
})
