<script setup lang="ts">
// 再取得中(更新ボタン・定期更新)の、カード上端の細い進行バー(DS 4.5)。親(カード)の上端に置く。
// 動きは `prefers-reduced-motion: reduce` で止まり、静止した帯で示す(global.css)。
defineProps<{ active: boolean }>()
</script>

<template>
  <div v-if="active" class="top-progress" role="progressbar" aria-label="更新中">
    <div class="top-progress__bar" />
  </div>
</template>

<style scoped>
.top-progress {
  position: absolute;
  inset: 0 0 auto 0;
  height: 2px;
  overflow: hidden;
  background: rgba(var(--v-theme-primary), 0.18);
  z-index: 1;
}
.top-progress__bar {
  position: absolute;
  inset: 0 auto 0 0;
  width: 35%;
  background: rgb(var(--v-theme-primary));
  animation: progress-slide 1.2s ease-in-out infinite;
}
/* 停止したときも、静止した帯で「更新中」を示す(DS 2.6)。global.css に置くと、この scoped の規則に詳細度で負ける */
@media (prefers-reduced-motion: reduce) {
  .top-progress__bar {
    animation: none;
    width: 100%;
    opacity: 0.5;
  }
}
</style>
