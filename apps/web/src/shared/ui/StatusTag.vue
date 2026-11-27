<script setup lang="ts">
// ステータスタグ(DS 4.1)。`kind` と `value` から、色・アイコン・文言を `statusMaps` の表で引く。
// 未登録の値は、中立(`secondary-container`・アイコンなし)で値をそのまま出し、開発時にだけ警告する
// (OpenSearch の状態値は API が string で返すため、未知の値がここに来うる)。
import { computed } from 'vue'

import { findStatusEntry, warnUnregisteredStatus, type StatusKind } from './statusMaps'

const props = defineProps<{
  kind: StatusKind
  value: string
}>()

const entry = computed(() => {
  const found = findStatusEntry(props.kind, props.value)
  if (found === null) warnUnregisteredStatus(props.kind, props.value)
  return found
})

const chipColor = computed(() => {
  const tone = entry.value?.tone ?? 'secondary'
  // 塗りなし(outlined)は、文字と枠を `on-*-container` の色にする。
  return entry.value?.outlined === true ? `on-${tone}-container` : `${tone}-container`
})
</script>

<template>
  <v-chip
    class="status-tag"
    :color="chipColor"
    :variant="entry?.outlined === true ? 'outlined' : 'flat'"
    :prepend-icon="entry?.icon"
  >
    {{ entry?.label ?? value }}
  </v-chip>
</template>

<style scoped>
.status-tag {
  /* 高さ 24px(DS 4.1)。`size="small"` の既定は 26px(実測。Vuetify 4.3.4) */
  height: 24px;
  font-size: 0.75rem;
  font-weight: 600;
  line-height: 1;
}
</style>
