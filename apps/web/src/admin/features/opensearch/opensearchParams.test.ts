import { describe, expect, it } from 'vitest'

import { opensearchParams } from './opensearchParams'

describe('opensearchParams(q・state。opensearch 3.5)', () => {
  it('URL なしは、名前なし・状態なし', () => {
    expect(opensearchParams.parse({})).toEqual({ q: '', states: [] })
  })

  it('q と state(カンマ区切り)を読む。状態は red → yellow → green の順にそろえる', () => {
    expect(opensearchParams.parse({ q: 'logs', state: 'green,yellow' })).toEqual({
      q: 'logs',
      states: ['yellow', 'green'],
    })
  })

  it('q の前後の空白は除く。空白だけは条件なし', () => {
    expect(opensearchParams.parse({ q: '  logs ' }).q).toBe('logs')
    expect(opensearchParams.parse({ q: '   ' }).q).toBe('')
  })

  it('未知の state の値・重複は無視する(3 つとも選んだ状態は、そのまま保つ)', () => {
    expect(opensearchParams.parse({ state: 'purple,yellow,yellow,,GREEN' }).states).toEqual([
      'yellow',
    ])
    expect(opensearchParams.parse({ state: 'red,yellow,green' }).states).toEqual([
      'red',
      'yellow',
      'green',
    ])
  })

  it('同じキーが繰り返されたときは最初の値、値が配列・null のときは条件なし', () => {
    expect(opensearchParams.parse({ q: ['a', 'b'] }).q).toBe('a')
    expect(opensearchParams.parse({ q: null }).q).toBe('')
    expect(opensearchParams.parse({ state: [null, 'red'] }).states).toEqual([])
  })

  it('serialize: 既定値(空)のキーは省略し、state は正規の順のカンマ区切り', () => {
    expect(opensearchParams.serialize({ q: '', states: [] })).toEqual({})
    expect(opensearchParams.serialize({ q: 'logs', states: ['green', 'yellow'] })).toEqual({
      q: 'logs',
      state: 'yellow,green',
    })
    expect(opensearchParams.serialize({ q: '', states: ['red'] })).toEqual({ state: 'red' })
  })

  it('page は URL に入れない(1 ページの列数が幅で決まるため)。条件の変更は replace', () => {
    expect(Object.keys(opensearchParams.serialize({ q: 'a', states: ['red'] }))).toEqual([
      'q',
      'state',
    ])
    expect(opensearchParams.navigation).toBe('replace')
    expect(opensearchParams.pageKey).toBeUndefined()
  })
})
