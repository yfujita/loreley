<script setup lang="ts">
// スキップリンク(DS 8): 先頭に置き、フォーカスされたときだけ表示する。ナビを飛ばして本文へ移る。
// URL のハッシュを変えず(Router に遷移として扱わせない)、本文にフォーカスを移す。
const props = withDefaults(defineProps<{ targetId?: string }>(), { targetId: 'main' })

function moveToMain(event: Event): void {
  event.preventDefault()
  document.getElementById(props.targetId)?.focus()
}
</script>

<template>
  <a class="skip-link" :href="`#${targetId}`" @click="moveToMain">メインコンテンツへ移動</a>
</template>

<style scoped>
.skip-link {
  position: fixed;
  left: 8px;
  top: -64px;
  z-index: 2600;
  padding: 8px 12px;
  border-radius: 4px;
  background: rgb(var(--v-theme-surface));
  box-shadow: 0 4px 12px rgba(26, 37, 48, 0.16);
}
.skip-link:focus {
  top: 8px;
}
</style>
