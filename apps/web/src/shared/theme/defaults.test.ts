import { describe, expect, it } from 'vitest'

import { vuetifyDefaults } from './defaults'
import { displayOptions } from './display'

describe('vuetifyDefaults(DS 3.2)', () => {
  it('ボタン: flat・角丸 md・色は primary(種類ごとの色・枠は global.css が補う)', () => {
    expect(vuetifyDefaults.VBtn).toMatchObject({ variant: 'flat', rounded: 'md', color: 'primary' })
  })

  it.each(['VTextField', 'VSelect', 'VTextarea', 'VCombobox'] as const)(
    '%s: outlined・密度 compact(入力欄の高さ 40px)・primary・hide-details=auto',
    (name) => {
      expect(vuetifyDefaults[name]).toMatchObject({
        variant: 'outlined',
        density: 'compact',
        color: 'primary',
        hideDetails: 'auto',
      })
    },
  )

  it('カード: flat・thin の境界線・角丸 lg・影なし', () => {
    expect(vuetifyDefaults.VCard).toMatchObject({
      variant: 'flat',
      border: 'thin',
      rounded: 'lg',
      elevation: 0,
    })
  })

  it('タグ(VChip): flat・四角(label)・small・角丸 md', () => {
    expect(vuetifyDefaults.VChip).toMatchObject({
      variant: 'flat',
      label: true,
      size: 'small',
      rounded: 'md',
    })
  })

  it('表: 密度 comfortable・ホバーあり(クライアント・サーバーの両方)', () => {
    expect(vuetifyDefaults.VDataTable).toMatchObject({ density: 'comfortable', hover: true })
    expect(vuetifyDefaults.VDataTableServer).toMatchObject({ density: 'comfortable', hover: true })
  })

  it('ダイアログ幅 560px・スナックバーは 6 秒・下・ink の面', () => {
    expect(vuetifyDefaults.VDialog).toMatchObject({ maxWidth: 560 })
    expect(vuetifyDefaults.VSnackbar).toMatchObject({
      timeout: 6000,
      location: 'bottom',
      color: 'ink',
    })
  })

  it('サイドバーの幅 232px。静的な permanent・temporary を既定にしない(840px の境で切り替えるため)', () => {
    expect(vuetifyDefaults.VNavigationDrawer).toEqual({ width: 232 })
  })

  it('ナビ(VList): nav・comfortable・primary', () => {
    expect(vuetifyDefaults.VList).toMatchObject({
      nav: true,
      density: 'comfortable',
      color: 'primary',
    })
  })
})

describe('displayOptions(DS 3.1・7)', () => {
  it('mobileBreakpoint は md(840px)。既定の lg(1145px)のままだと 840〜1144px でも mobile と判定される', () => {
    expect(displayOptions).toEqual({ mobileBreakpoint: 'md' })
  })
})
