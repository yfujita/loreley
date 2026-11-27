import { describe, expect, it } from 'vitest'
import { createApp, h } from 'vue'

import { vuetifyDefaults } from '@/shared/theme/defaults'
import { lightColors, lightVariables } from '@/shared/theme/tokens'

import { setupVuetify, vuetifyOptions } from './setupVuetify'

describe('setupVuetify(E 4.1 の 1。DS 3)', () => {
  it('テーマは light だけ。既定のテーマを light と明示する(v4 の既定は system で、OS がダークだと別配色になる)', () => {
    expect(vuetifyOptions.theme).toMatchObject({ defaultTheme: 'light' })
    expect(
      Object.keys(
        vuetifyOptions.theme && typeof vuetifyOptions.theme === 'object'
          ? (vuetifyOptions.theme.themes ?? {})
          : {},
      ),
    ).toEqual(['light'])
  })

  it('色・variables・defaults・display・アイコン・ロケールを、shared/theme から組み立てる', () => {
    const vuetify = setupVuetify()

    const theme = vuetify.theme.themes.value.light
    expect(theme?.colors.primary).toBe(lightColors.primary)
    expect(theme?.colors['success-container']).toBe(lightColors['success-container'])
    expect(theme?.colors['line-strong']).toBe(lightColors['line-strong'])
    expect(theme?.variables['medium-emphasis-opacity']).toBe(
      lightVariables['medium-emphasis-opacity'],
    )
    expect(vuetify.theme.name.value).toBe('light')
    expect(vuetify.defaults.value).toMatchObject(vuetifyDefaults)
    // md = 840px(R-1)
    expect(vuetify.display.thresholds.value.md).toBe(840)
    expect(vuetify.display.mobileBreakpoint.value).toBe('md')
    expect(vuetify.locale.current.value).toBe('ja')
    expect(vuetify.icons.defaultSet).toBe('mdi')
  })

  it('アプリに install できる(createVuetify の戻り値)', () => {
    const app = createApp({ render: () => h('div') })

    expect(() => app.use(setupVuetify())).not.toThrow()
  })
})
