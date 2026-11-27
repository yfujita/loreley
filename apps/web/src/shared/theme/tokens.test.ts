import { describe, expect, it } from 'vitest'

import { DEFAULT_THEME_NAME, lightColors, lightTheme, lightVariables } from './tokens'

/** WCAG 2.x の相対輝度とコントラスト比(DS 2.1 の実測値の検算)。 */
function luminance(hex: string): number {
  const channel = (offset: number) => {
    const value = parseInt(hex.slice(1 + offset, 3 + offset), 16) / 255
    return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * channel(0) + 0.7152 * channel(2) + 0.0722 * channel(4)
}
function contrast(a: string, b: string): number {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return ((light ?? 0) + 0.05) / ((dark ?? 0) + 0.05)
}
const c = lightColors

describe('tokens(DS 2.1)', () => {
  it('色名と値は DS 2.1 の表のとおり', () => {
    expect(lightColors).toMatchObject({
      background: '#F4F6F8',
      'on-background': '#1A2530',
      surface: '#FFFFFF',
      'surface-variant': '#E9EDF1',
      'on-surface-variant': '#46535F',
      primary: '#1D5B87',
      'primary-container': '#E3EEF6',
      'on-primary-container': '#123F5F',
      secondary: '#4A5A69',
      success: '#1D6F42',
      warning: '#8F5A00',
      error: '#B3261E',
      info: '#2F6B9A',
      focus: '#0B57D0',
      ink: '#26323E',
      'line-strong': '#6F7C88',
    })
  })

  it('意味色(primary・secondary・success・warning・error・info)に、主色・container・on-container の組がある', () => {
    for (const tone of ['primary', 'secondary', 'success', 'warning', 'error', 'info'] as const) {
      expect(lightColors[tone]).toMatch(/^#[0-9A-F]{6}$/)
      expect(lightColors[`on-${tone}`]).toBe('#FFFFFF')
      expect(lightColors[`${tone}-container`]).toMatch(/^#[0-9A-F]{6}$/)
      expect(lightColors[`on-${tone}-container`]).toMatch(/^#[0-9A-F]{6}$/)
    }
  })

  it('本文・補助文字のコントラスト比は 4.5:1 以上(DS の実測値: 本文 15.54・補助 7.89)', () => {
    expect(contrast(c['on-surface'], c.surface)).toBeGreaterThan(15.5)
    expect(contrast(c['on-surface'], c.background)).toBeGreaterThan(14.3)
    expect(contrast(c['on-surface-variant'], c.surface)).toBeGreaterThan(7.8)
    expect(contrast(c['on-surface-variant'], c['surface-variant'])).toBeGreaterThan(6.6)
  })

  it.each(['primary', 'secondary', 'success', 'warning', 'error', 'info'] as const)(
    '%s: 主色の白文字・container の上の文字(on-container)・container の上の主色が、いずれも 4.5:1 以上',
    (tone) => {
      expect(contrast(c[tone], '#FFFFFF')).toBeGreaterThanOrEqual(4.5)
      expect(contrast(c[`on-${tone}-container`], c[`${tone}-container`])).toBeGreaterThanOrEqual(
        4.5,
      )
      // secondary の主色は container の上に置かない(タグは on-container を使う)
      if (tone !== 'secondary') {
        expect(contrast(c[tone], c[`${tone}-container`])).toBeGreaterThanOrEqual(4.5)
      }
    },
  )

  it('UI 部品の境界(入力枠 line-strong)とフォーカスリングは 3:1 以上', () => {
    expect(contrast(c['line-strong'], c.surface)).toBeGreaterThanOrEqual(3)
    expect(contrast(c.focus, c.surface)).toBeGreaterThanOrEqual(3)
    expect(contrast(c.focus, c.background)).toBeGreaterThanOrEqual(3)
  })

  it('スナックバー(ink)の白文字は 4.5:1 以上。リンク色 #9CC9EE も', () => {
    expect(contrast(c.ink, '#FFFFFF')).toBeGreaterThanOrEqual(4.5)
    expect(contrast(c.ink, '#9CC9EE')).toBeGreaterThanOrEqual(4.5)
  })

  it('variables: 境界線は装飾(不透明度 .16)。本文は不透明度 1、補助は 0.78', () => {
    expect(lightVariables).toEqual({
      'border-color': '#1A2530',
      'border-opacity': 0.16,
      'high-emphasis-opacity': 1,
      'medium-emphasis-opacity': 0.78,
    })
  })

  it('テーマはライトの 1 つだけ(ダークは作らない)', () => {
    expect(DEFAULT_THEME_NAME).toBe('light')
    expect(lightTheme.dark).toBe(false)
    expect(lightTheme.colors).toEqual(lightColors)
  })
})
