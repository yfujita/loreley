import { describe, expect, it } from 'vitest'

import { heaviestSeverity, resolveDialogAppearance, type Severity } from './dialogLevel'

describe('heaviestSeverity(最も重い指定)', () => {
  it.each<[string, Severity[], Severity | null]>([
    ['指定なし', [], null],
    ['再書き込み・ロック解放(warning)だけ', ['warning'], 'warning'],
    ['強制削除(danger)だけ', ['danger'], 'danger'],
    ['強制削除と再書き込みの両方は、重い方(danger)', ['warning', 'danger'], 'danger'],
    ['順序によらない', ['danger', 'warning'], 'danger'],
  ])('%s', (_name, severities, expected) => {
    expect(heaviestSeverity(severities)).toBe(expected)
  })
})

describe('resolveDialogAppearance(DS 4.8)', () => {
  it('要確認・標準: 帯なし・primary・Esc で閉じられる', () => {
    expect(resolveDialogAppearance('confirm')).toEqual({
      band: null,
      executeColor: 'primary',
      persistent: false,
    })
  })

  it('要確認・標準は、指定があっても色を変えない', () => {
    expect(resolveDialogAppearance('confirm', ['danger']).executeColor).toBe('primary')
  })

  it('要入力確認: 赤の帯・danger・persistent(指定によらない)', () => {
    expect(resolveDialogAppearance('confirm-typed', ['warning'])).toEqual({
      band: 'error',
      executeColor: 'error',
      persistent: true,
    })
  })

  it.each<[string, Severity[], 'error' | 'warning']>([
    ['再書き込みのみ=琥珀', ['warning'], 'warning'],
    ['強制削除=赤', ['danger'], 'error'],
    ['強制削除と再書き込みの両方=赤(最も重い指定に合わせる)', ['warning', 'danger'], 'error'],
    ['指定を持たない警告つき(ロック解放)=琥珀', [], 'warning'],
  ])('要確認・警告つき: %s。帯と実行ボタンは同じ色・persistent', (_name, severities, color) => {
    expect(resolveDialogAppearance('confirm-warning', severities)).toEqual({
      band: color,
      executeColor: color,
      persistent: true,
    })
  })
})
