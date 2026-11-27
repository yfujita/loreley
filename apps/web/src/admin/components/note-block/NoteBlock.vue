<script setup lang="ts">
// 注記ブロック(X1 の各タブの意味と次の行動。documents 4 章): アイコン+文。`role` を持たない常設の説明で、アラートにしない。
import { mdiInformationOutline } from '@/shared/theme/icons'
</script>

<template>
  <div class="note-block">
    <v-icon :icon="mdiInformationOutline" color="info" size="18" />
    <div class="note-block__body"><slot /></div>
  </div>
</template>

<style scoped>
.note-block {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 12px 16px;
  color: rgb(var(--v-theme-on-surface-variant));
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.note-block .v-icon {
  margin-top: 2px;
}
.note-block__body :deep(p) {
  margin: 0;
}
.note-block__body :deep(p + p) {
  margin-top: 2px;
}
</style>
