<script setup lang="ts">
// 初回読み込み中の、表と同じ列構成のスケルトン(DS 4.5)。`VDataTable` の `body` スロットに置く。
// 読み上げ用の「読み込み中」(`role="status"`)は表の外側(カード)が持つので、ここは見た目だけ。
defineProps<{
  /** 列の数 */
  columnCount: number
  rows?: number
}>()
</script>

<template>
  <tr v-for="row in rows ?? 5" :key="row" class="skeleton-rows__row" aria-hidden="true">
    <td v-for="column in columnCount" :key="column">
      <span class="skeleton-line" :style="{ width: column === 1 ? '60%' : '80%' }" />
    </td>
  </tr>
</template>
