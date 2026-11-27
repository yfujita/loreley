// テーマのトークン(DS 2.1・3.1・3.4)。値の正本は DS 2.1。Vuetify の theme.themes.light に 1 対 1 で置く。
// ライトテーマだけを定義する(ダークは前提 2 により作らない)。
import type { ThemeDefinition } from 'vuetify'

/**
 * 色名と値。`*-container` / `on-*-container` と `focus`・`ink`・`line-strong` は Vuetify 標準の名前ではなく、
 * 独自の色名として足す(`VChip color="success-container"` のように使う。DS 2.1)。
 */
export const lightColors = {
  background: '#F4F6F8',
  'on-background': '#1A2530',
  surface: '#FFFFFF',
  'on-surface': '#1A2530',
  'surface-variant': '#E9EDF1',
  'on-surface-variant': '#46535F',

  primary: '#1D5B87',
  'on-primary': '#FFFFFF',
  'primary-container': '#E3EEF6',
  'on-primary-container': '#123F5F',

  secondary: '#4A5A69',
  'on-secondary': '#FFFFFF',
  'secondary-container': '#E6EAEE',
  'on-secondary-container': '#3B4854',

  success: '#1D6F42',
  'on-success': '#FFFFFF',
  'success-container': '#E2F3E8',
  'on-success-container': '#114D2E',

  warning: '#8F5A00',
  'on-warning': '#FFFFFF',
  'warning-container': '#FFF1D6',
  'on-warning-container': '#6B4200',

  error: '#B3261E',
  'on-error': '#FFFFFF',
  'error-container': '#FCE8E6',
  'on-error-container': '#7A1712',

  info: '#2F6B9A',
  'on-info': '#FFFFFF',
  'info-container': '#E1EDF7',
  'on-info-container': '#173F61',

  /** フォーカスリング */
  focus: '#0B57D0',
  /** スナックバーの面 */
  ink: '#26323E',
  /** 入力欄・チェックボックスなど、情報を持つ線(白との比 4.27:1。3:1 以上) */
  'line-strong': '#6F7C88',
} as const

export const lightVariables = {
  // 境界線は装飾(情報を担わない)。`rgba(var(--v-border-color), var(--v-border-opacity))` で使う。
  'border-color': '#1A2530',
  'border-opacity': 0.16,
  // 文字の強弱は不透明度ではなく固定色(`on-surface` / `on-surface-variant`)で表す。本文は不透明度 1(既定は 0.87 で、
  // 本文色 #1A2530 が薄くなる)。`text-medium-emphasis` と揃えるため、medium は 0.78(白地で約 #4C555E、比 約 7.5)にする。
  'high-emphasis-opacity': 1,
  'medium-emphasis-opacity': 0.78,
} as const

export const lightTheme: ThemeDefinition = {
  dark: false,
  colors: { ...lightColors },
  variables: { ...lightVariables },
}

export const DEFAULT_THEME_NAME = 'light'
