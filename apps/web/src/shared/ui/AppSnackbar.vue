<script setup lang="ts">
// アプリで 1 つだけのスナックバー(DS 4.7)。`AppShell` が置く。表示時間・位置・色は `defaults`(VSnackbar)。
// `VSnackbar` は `role="status"` `aria-live="polite"` を持つ。
import { computed } from 'vue'

import { mdiClose } from '@/shared/theme/icons'
import { useSnackbar } from './useSnackbar'

const { message, close } = useSnackbar()

// 閉じる操作(タイムアウト・閉じるボタン)で false になったら、通知を消す。
const isOpen = computed({
  get: () => message.value !== null,
  set: (open: boolean) => {
    if (!open) close()
  },
})

function runAction(onClick: () => void): void {
  onClick()
  close()
}
</script>

<template>
  <!-- key: 新しい通知で置き換えたとき、6 秒のタイマーもやり直す -->
  <v-snackbar :key="message?.id ?? 0" v-model="isOpen" class="app-snackbar">
    <span class="app-snackbar__text">{{ message?.text }}</span>
    <button
      v-if="message?.action"
      type="button"
      class="app-snackbar__action"
      @click="runAction(message.action.onClick)"
    >
      {{ message.action.label }}
    </button>
    <template #actions>
      <v-btn
        class="app-snackbar__close"
        variant="text"
        color="on-surface"
        icon
        size="small"
        aria-label="通知を閉じる"
        @click="close"
      >
        <v-icon :icon="mdiClose" size="20" />
      </v-btn>
    </template>
  </v-snackbar>
</template>

<style scoped>
.app-snackbar__action {
  margin-left: 8px;
  color: var(--color-ink-link);
  font-weight: 600;
  text-decoration: underline;
  background: none;
  border: 0;
  padding: 3px 0;
  cursor: pointer;
}
</style>
