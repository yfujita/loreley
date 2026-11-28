import { describe, expect, it } from 'vitest'

import { DEFAULT_ITEMS_PER_PAGE, isItemsPerPage, ITEMS_PER_PAGE_OPTIONS } from './pagination'

describe('ページング', () => {
  it('25・50・100(既定 25)', () => {
    expect(ITEMS_PER_PAGE_OPTIONS).toEqual([25, 50, 100])
    expect(DEFAULT_ITEMS_PER_PAGE).toBe(25)
  })

  it('isItemsPerPage は 3 つの値だけ true', () => {
    expect([25, 50, 100].every(isItemsPerPage)).toBe(true)
    for (const value of [0, 10, 24, 26, '25', null, undefined, NaN]) {
      expect(isItemsPerPage(value)).toBe(false)
    }
  })
})
