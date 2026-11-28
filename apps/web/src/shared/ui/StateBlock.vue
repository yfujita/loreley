<script setup lang="ts">
// 空・エラー(データなし)・見つかりません・読み込み中の共通ブロック(DS 4.5。E 6.2)。
// 状態の決定(Query の結果 → viewState)は features の composable が行い、ここは見せ方だけを持つ。
import { computed } from 'vue'

import { mdiAlertCircleOutline, mdiInformationOutline } from '@/shared/theme/icons'

const props = withDefaults(
  defineProps<{
    kind: 'empty' | 'error' | 'notfound' | 'loading'
    /** 見出し(loading 以外は必須)。「…を取得できません」のように、何が起きたかを書く */
    title?: string
    /** 原因と次の行動(2 文以内。謝らない) */
    message?: string
    /** 試行時刻・診断(`code` と HTTP ステータス)などの補助文字 */
    note?: string
    /** イラスト枠のアイコン(SVG パス)。省略時は kind に応じた既定 */
    icon?: string
    /** 見出しのレベル。カード内に `h2` があるときは 3 にする(階層を飛ばさない) */
    headingLevel?: 2 | 3
    /** loading のスケルトンの行数 */
    rows?: number
    /** loading の、視覚的に隠した文言 */
    loadingLabel?: string
  }>(),
  {
    title: undefined,
    message: undefined,
    note: undefined,
    icon: undefined,
    headingLevel: 2,
    rows: 6,
    loadingLabel: '読み込み中',
  },
)

const isError = computed(() => props.kind === 'error' || props.kind === 'notfound')
const illustration = computed(
  () => props.icon ?? (isError.value ? mdiAlertCircleOutline : mdiInformationOutline),
)
// 行ごとに幅を変えて、文章の塊らしく見せる(装飾)。
const SKELETON_WIDTHS = ['40%', '100%', '88%', '70%', '100%', '55%']
const skeletonWidths = computed(() =>
  Array.from({ length: props.rows }, (_, i) => SKELETON_WIDTHS[i % SKELETON_WIDTHS.length]),
)
const headingTag = computed(() => `h${props.headingLevel}`)
</script>

<template>
  <div v-if="kind === 'loading'" class="state-block-loading" aria-busy="true">
    <div class="state-block-loading__lines" role="status">
      <span class="sr-only">{{ loadingLabel }}</span>
      <span
        v-for="(width, i) in skeletonWidths"
        :key="i"
        class="skeleton-line"
        :style="{ width }"
      />
    </div>
  </div>
  <div
    v-else
    class="state-block"
    :class="{ 'state-block--error': isError }"
    :role="kind === 'error' ? 'alert' : undefined"
  >
    <div class="state-block__illustration">
      <v-icon :icon="illustration" size="28" />
    </div>
    <component :is="headingTag" class="text-section-title">{{ title }}</component>
    <p v-if="message !== undefined" class="state-block__message text-on-surface-variant">
      {{ message }}
    </p>
    <p v-if="note !== undefined" class="text-caption-sm text-on-surface-variant">{{ note }}</p>
    <div v-if="$slots.default" class="state-block__actions">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.state-block {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 8px;
  padding: 40px 24px;
}
.state-block__illustration {
  width: 48px;
  height: 48px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgb(var(--v-theme-surface-variant));
  color: rgb(var(--v-theme-on-surface-variant));
}
.state-block--error .state-block__illustration {
  background: rgb(var(--v-theme-error-container));
  color: rgb(var(--v-theme-error));
}
.state-block h2,
.state-block h3 {
  margin: 0;
}
.state-block__message {
  max-width: 46ch;
  margin: 0;
}
.state-block p {
  margin: 0;
}
.state-block__actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
}
.state-block-loading__lines {
  display: grid;
  gap: 14px;
  padding: 16px;
}
</style>
