import { describe, expect, it } from 'vitest'

import { mountInLayout } from '../../../tests/support/mount'
import TopProgress from './TopProgress.vue'

describe('TopProgress(DS 4.5)', () => {
  it('再取得中だけ、progressbar(aria-label「更新中」)を出す', async () => {
    const { wrapper } = await mountInLayout(TopProgress, { props: { active: true } })

    expect(wrapper.find('[role="progressbar"]').attributes('aria-label')).toBe('更新中')
  })

  it('再取得中でなければ何も描かない', async () => {
    const { wrapper } = await mountInLayout(TopProgress, { props: { active: false } })

    expect(wrapper.find('[role="progressbar"]').exists()).toBe(false)
  })

  it('進行バー(.top-progress__bar)は .top-progress の中にある(reduced-motion の上書きが効く構造)', async () => {
    const { wrapper } = await mountInLayout(TopProgress, { props: { active: true } })

    expect(wrapper.find('.top-progress > .top-progress__bar').exists()).toBe(true)
  })
})
