<script setup lang="ts">
// 確認チェック(DS 4.8): 要確認・警告つきで、チェックするまで実行ボタンを無効にする。`<label>` 付き。
// 指定ごとに置く(複数の指定を含むダイアログでは、それぞれの確認チェックを出す)。
const model = defineModel<boolean>({ default: false })

defineProps<{
  label: string
  /** 実行中(二重送信を防ぐため、入力を無効にする) */
  disabled?: boolean
}>()
</script>

<template>
  <v-checkbox
    v-model="model"
    class="confirm-check"
    color="primary"
    density="compact"
    hide-details
    :disabled="disabled"
  >
    <template #label>
      <span class="confirm-check__label">{{ label }}</span>
    </template>
  </v-checkbox>
</template>

<style scoped>
.confirm-check__label {
  font-size: 0.875rem;
  color: rgb(var(--v-theme-on-surface));
  opacity: 1;
}
</style>
