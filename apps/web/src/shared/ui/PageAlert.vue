<script setup lang="ts">
// 左帯つきのアラート(ページ内・ダイアログ内。DS 4.7)。種類は info・warning・error・success。
// `role` を props で切り替える: 取得失敗・操作の失敗は `alert`、読み込み後の情報は `status`、静的な注記は付けない。
// `VAlert` は使わない: `role="alert"` を固定で付け、role を持たない注記(info)を作れないため(Vuetify 4.3.4 で確認)。
import { computed } from 'vue'

import {
  mdiAlertOutline,
  mdiCheckCircleOutline,
  mdiCloseOctagonOutline,
  mdiInformationOutline,
} from '@/shared/theme/icons'

const props = withDefaults(
  defineProps<{
    type: 'info' | 'warning' | 'error' | 'success'
    /** 太字の 1 行目(任意) */
    title?: string
    /** 既定は付けない。取得失敗・操作の失敗は 'alert'、読み込み後の情報は 'status' */
    role?: 'alert' | 'status'
  }>(),
  { title: undefined, role: undefined },
)

const ICONS = {
  info: mdiInformationOutline,
  warning: mdiAlertOutline,
  error: mdiCloseOctagonOutline,
  success: mdiCheckCircleOutline,
} as const
const icon = computed(() => ICONS[props.type])
</script>

<template>
  <div class="page-alert" :class="`page-alert--${type}`" :role="role">
    <v-icon class="page-alert__icon" :icon="icon" size="24" />
    <div class="page-alert__body">
      <p v-if="title !== undefined" class="page-alert__title">{{ title }}</p>
      <slot />
      <div v-if="$slots.actions" class="page-alert__actions">
        <slot name="actions" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-alert {
  --tone: var(--v-theme-info);
  --container: var(--v-theme-info-container);
  --on-container: var(--v-theme-on-info-container);
  display: flex;
  gap: 12px;
  align-items: flex-start;
  min-width: 0;
  padding: 12px 16px;
  border-radius: 4px;
  background: rgb(var(--container));
  color: rgb(var(--on-container));
  border: 1px solid rgba(var(--tone), 0.35);
  border-left: 4px solid rgb(var(--tone));
}
.page-alert--warning {
  --tone: var(--v-theme-warning);
  --container: var(--v-theme-warning-container);
  --on-container: var(--v-theme-on-warning-container);
}
.page-alert--error {
  --tone: var(--v-theme-error);
  --container: var(--v-theme-error-container);
  --on-container: var(--v-theme-on-error-container);
}
.page-alert--success {
  --tone: var(--v-theme-success);
  --container: var(--v-theme-success-container);
  --on-container: var(--v-theme-on-success-container);
}
.page-alert__icon {
  margin-top: 1px;
  color: rgb(var(--tone));
}
.page-alert__body {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
}
.page-alert__body :deep(p) {
  margin: 0;
}
.page-alert__title {
  font-weight: 600;
  margin: 0;
}
.page-alert__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}
.page-alert__body :deep(a) {
  color: inherit;
  font-weight: 600;
}
</style>
