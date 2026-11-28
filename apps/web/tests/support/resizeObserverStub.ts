// Vitest 用: `ResizeObserver` を、観測した要素と callback を記録する偽物に差し替える(FMOD-U-6)。
//
// jsdom にはレイアウトがなく、要素の幅は常に 0。`ShardMatrix` の 1 ページの列数は、観測している要素の幅から決まるので、
// テストはこの偽物の `resize()` で「その要素の幅が変わった」通知を送って、列数を駆動する。
// 実ブラウザでの列数(式の検算表・幅を変えたときの列数)は E2E(opensearch.spec.ts)で確かめる。
import { afterEach, beforeEach } from 'vitest'

type Record = { callback: ResizeObserverCallback; targets: Set<Element> }

export type ResizeObserverStub = {
  /** `selector` に一致する要素を観測している ResizeObserver に、幅 `width` の通知を送る。観測がなければ例外 */
  resize(selector: string, width: number): void
}

/** `describe` の直下で呼ぶ。各テストの前に差し替え、後に元へ戻す。 */
export function useResizeObserverStub(): ResizeObserverStub {
  const records: Record[] = []
  const original = globalThis.ResizeObserver

  beforeEach(() => {
    records.length = 0
    globalThis.ResizeObserver = class RecordingResizeObserver implements ResizeObserver {
      private readonly record: Record
      constructor(callback: ResizeObserverCallback) {
        this.record = { callback, targets: new Set() }
        records.push(this.record)
      }
      observe(target: Element): void {
        this.record.targets.add(target)
      }
      unobserve(target: Element): void {
        this.record.targets.delete(target)
      }
      disconnect(): void {
        this.record.targets.clear()
      }
    }
  })
  afterEach(() => {
    globalThis.ResizeObserver = original
  })

  return {
    resize(selector, width) {
      const matched = records.filter((record) =>
        [...record.targets].some((target) => target.matches(selector)),
      )
      if (matched.length === 0)
        throw new Error(`${selector} を観測している ResizeObserver がありません`)
      for (const record of matched) {
        record.callback([{ contentRect: { width } } as ResizeObserverEntry], {} as ResizeObserver)
      }
    },
  }
}
