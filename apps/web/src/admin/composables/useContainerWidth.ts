// 要素の幅(`ResizeObserver`)。表を載せるカードの幅で列を省く(J1。DS 4.3。viewport ではなくカード幅で決める)ため。
// VueUse は足さない(E 2.4)。要素がまだない(null)間は 0。
import { onBeforeUnmount, readonly, ref, watch, type Ref } from 'vue'

export function useContainerWidth(
  target: Readonly<Ref<HTMLElement | null>>,
): Readonly<Ref<number>> {
  const width = ref(0)
  let observer: ResizeObserver | null = null

  function stop(): void {
    observer?.disconnect()
    observer = null
  }

  watch(
    target,
    (element) => {
      stop()
      if (element === null) {
        width.value = 0
        return
      }
      width.value = element.getBoundingClientRect().width
      observer = new ResizeObserver((entries) => {
        const entry = entries[entries.length - 1]
        if (entry !== undefined) width.value = entry.contentRect.width
      })
      observer.observe(element)
    },
    { immediate: true, flush: 'post' },
  )

  onBeforeUnmount(stop)

  return readonly(width)
}
