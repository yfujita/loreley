<script setup lang="ts">
// 識別子(`source_id`・ジョブ ID・`external_id` など)。等幅 13px・折り返し可(DS 2.2・4.9)。
defineProps<{ value: string }>()
</script>

<template>
  <span class="text-id">{{ value }}</span>
</template>
