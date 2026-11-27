<script setup lang="ts">
// 自動更新スイッチ(DS 4.17。D1): 定期更新の一時停止・再開(WCAG 2.2.2)。
// `role="switch"` の `<input type="checkbox">`(`VSwitch`)に、`<label>`「自動更新(30 秒ごと)」を添える。
// 停止中は、近くに「自動更新は停止中です。…」を出す。状態は保存しない(再読み込みで既定のオンに戻る)。
// `VSwitch` の `<input>` は `role="switch"` を持たない(Vuetify 4.3.4 で確認)ので、明示する。寸法・色は DS 4.17 の値に CSS で合わせる
// (Vuetify の既定は、トラック 36×14px のつまみがはみ出す形で、DS のトラック 36×20px・つまみ 16px と違う。`inset` は使わない)。
defineProps<{
  modelValue: boolean
  /** ラベルに出す間隔(秒)。実際の間隔は `queries/polling.ts` が決める(表示だけを受け取る) */
  intervalSeconds: number
}>()

const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
</script>

<template>
  <div class="auto-refresh-switch">
    <v-switch
      class="auto-refresh-switch__control"
      role="switch"
      color="primary"
      hide-details
      :model-value="modelValue"
      :label="`自動更新(${intervalSeconds} 秒ごと)`"
      @update:model-value="emit('update:modelValue', $event === true)"
    />
    <span v-if="!modelValue" class="text-caption-sm text-on-surface-variant">
      自動更新は停止中です。「更新」で最新の状態を取得します。
    </span>
  </div>
</template>

<style scoped>
.auto-refresh-switch {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 12px;
}
/* 操作領域は高さ 32px 以上。幅 600px 未満は 44px(DS 4.17) */
.auto-refresh-switch__control {
  --v-input-control-height: 32px;
  --v-switch-track-height: 20px;
  --v-switch-thumb-height: 16px;
  --v-switch-thumb-width: 16px;
}
@media (max-width: 599px) {
  .auto-refresh-switch__control {
    --v-input-control-height: 44px;
  }
}
.auto-refresh-switch__control :deep(.v-label) {
  font-size: 0.875rem;
  opacity: 1;
}
/* オフのトラックは line-strong(白との比 4.27:1。UI 部品の境界 3:1 以上)、オンは primary。つまみは白 */
.auto-refresh-switch__control :deep(.v-switch__track) {
  min-width: 36px;
  opacity: 1;
  background-color: rgb(var(--v-theme-line-strong));
}
.auto-refresh-switch__control :deep(.v-selection-control--dirty .v-switch__track) {
  background-color: rgb(var(--v-theme-primary));
}
.auto-refresh-switch__control :deep(.v-switch__thumb) {
  background-color: #fff;
  box-shadow: none;
}
/* つまみ(16px)をトラック(36px)の内側 2px に置く */
.auto-refresh-switch__control :deep(.v-selection-control__input) {
  transform: translateX(-8px);
}
.auto-refresh-switch__control :deep(.v-selection-control--dirty .v-selection-control__input) {
  transform: translateX(8px);
}
</style>
