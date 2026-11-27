<script setup lang="ts">
// 日時(DS 4.9): `YYYY-MM-DD HH:mm`(`withSeconds` で `:ss`)。ブラウザのローカル時刻。`<time>` で意味づける。
// 値がない・日時として読めないときは「—」を出し、読み上げ用に `emptyLabel` を添える。
import { computed } from 'vue'

import { formatDate, parseIsoDateTime } from '@/shared/lib/datetime'

const props = withDefaults(
  defineProps<{
    /** ISO 8601 の文字列、`Date`、またはミリ秒(Query の `dataUpdatedAt`) */
    value?: string | number | Date | null
    withSeconds?: boolean
    emptyLabel?: string
  }>(),
  { value: null, withSeconds: false, emptyLabel: 'なし' },
)

const date = computed(() => {
  if (props.value === null || props.value === undefined) return null
  if (typeof props.value === 'string') return parseIsoDateTime(props.value)
  const converted = new Date(props.value)
  return Number.isNaN(converted.getTime()) ? null : converted
})
</script>

<template>
  <time v-if="date" class="num" :datetime="date.toISOString()">{{
    formatDate(date, { withSeconds })
  }}</time>
  <span v-else
    >—<span class="sr-only">{{ emptyLabel }}</span></span
  >
</template>
