import { describe, expect, it } from 'vitest'
import { h } from 'vue'

import { mountInLayout } from '../../../../tests/support/mount'
import NoteBlock from './NoteBlock.vue'

describe('NoteBlock(documents 4 章)', () => {
  it('アイコン+文。常設の説明なので、role を持たない(アラートにしない)', async () => {
    const { wrapper } = await mountInLayout(NoteBlock, {
      slots: { default: () => [h('p', '1 文目'), h('p', '2 文目')] },
    })

    const block = wrapper.find('.note-block')
    expect(block.attributes('role')).toBeUndefined()
    expect(block.find('svg').exists()).toBe(true)
    expect(block.findAll('p').map((p) => p.text())).toEqual(['1 文目', '2 文目'])
  })
})
