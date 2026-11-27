<script setup lang="ts">
// 概況バー(DS 4.16。D1): 左に 28px のアイコン、1 行の文(16px / 600)と件数行(12px)。
// 左の 4px の帯・枠線・面は、状態の意味色(success・error・warning の container)。
// 色だけにせず、アイコンの形(円・八角形・疑問符)と文言でも示す。自動更新の結果を読み上げないよう、`role` は付けない(DS 8)。
import { computed } from 'vue'

import {
  mdiCheckCircleOutline,
  mdiCloseOctagonOutline,
  mdiHelpCircleOutline,
} from '@/shared/theme/icons'

import type { SummaryItem, SummaryModel, SummaryTone } from './types'

const props = defineProps<{ model: SummaryModel }>()

const ICONS: Record<SummaryTone, string> = {
  success: mdiCheckCircleOutline,
  error: mdiCloseOctagonOutline,
  warning: mdiHelpCircleOutline,
}
const icon = computed(() => ICONS[props.model.tone])

function itemText(item: SummaryItem): string {
  return item.value === undefined ? item.label : `${item.label} ${item.value}`
}
</script>

<template>
  <section
    class="summary-band"
    :class="`summary-band--${model.tone}`"
    aria-label="全体の状態"
    data-testid="d1-summary"
  >
    <v-icon class="summary-band__icon" :icon="icon" size="28" />
    <div class="summary-band__body">
      <p class="summary-band__title">{{ model.title }}</p>
      <p class="summary-band__items text-caption-sm">
        <!-- 項目の間に空白の文字を置く(flex の項目としては描かれないが、読み上げ・テキストでは区切りになる) -->
        <template v-for="item in model.items" :key="item.key">
          <span>
            <template v-if="item.names !== undefined">
              {{ item.label }}: <span class="summary-band__name">{{ item.names.join('、') }}</span>
            </template>
            <template v-else>{{ itemText(item) }}</template>
          </span>
          {{ ' ' }}
        </template>
      </p>
    </div>
  </section>
</template>

<style scoped>
.summary-band {
  --tone: var(--v-theme-success);
  --container: var(--v-theme-success-container);
  --on-container: var(--v-theme-on-success-container);
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 14px 16px;
  border-radius: 8px;
  border: 1px solid rgba(var(--tone), 0.35);
  border-left: 4px solid rgb(var(--tone));
  background: rgb(var(--container));
  color: rgb(var(--on-container));
}
.summary-band--error {
  --tone: var(--v-theme-error);
  --container: var(--v-theme-error-container);
  --on-container: var(--v-theme-on-error-container);
}
.summary-band--warning {
  --tone: var(--v-theme-warning);
  --container: var(--v-theme-warning-container);
  --on-container: var(--v-theme-on-warning-container);
}
.summary-band__icon {
  color: rgb(var(--tone));
  flex: none;
}
.summary-band__body {
  flex: 1;
  min-width: 0;
}
.summary-band__body p {
  margin: 0;
}
.summary-band__title {
  font-size: 1rem;
  line-height: 1.5;
  font-weight: 600;
}
.summary-band__items {
  display: flex;
  flex-wrap: wrap;
  gap: 2px 16px;
  margin-top: 2px;
}
.summary-band__name {
  font-family: var(--font-mono);
  font-size: 0.8125rem;
}
@media (max-width: 599px) {
  .summary-band {
    align-items: flex-start;
  }
}
</style>
