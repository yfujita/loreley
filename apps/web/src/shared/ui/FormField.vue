<script setup lang="ts">
// フォーム項目(DS 4.6): ラベルは項目の上(14px / 600)。必須は「必須」の枠付き表示(アスタリスクだけにしない)。
// ヘルプ文は入力欄の下、検証エラーは「アイコン+文言」で、入力欄に `aria-invalid` と `aria-describedby` を結ぶ。
// 入力欄そのもの(VTextField など)は default スロットで受け、スロットの値(`inputId`・`describedBy`・`invalid`)を渡してもらう。
import { computed, useId } from 'vue'

import { mdiAlertCircleOutline } from '@/shared/theme/icons'

const props = defineProps<{
  label: string
  required?: boolean
  help?: string
  /** 検証エラーの文言。null・省略ならエラーなし */
  error?: string | null
  /** 入力欄の id(エラー要約のリンク先)。省略すると自動で作る */
  inputId?: string
}>()

const generatedId = useId()
const resolvedInputId = computed(() => props.inputId ?? `field-${generatedId}`)
const helpId = computed(() => `${resolvedInputId.value}-help`)
const errorId = computed(() => `${resolvedInputId.value}-error`)
const invalid = computed(() => props.error !== undefined && props.error !== null)

// 表示している説明だけを結ぶ(存在しない id を指さない)。エラーが先、ヘルプが後。
const describedBy = computed(() => {
  const ids = [
    ...(invalid.value ? [errorId.value] : []),
    ...(props.help !== undefined ? [helpId.value] : []),
  ]
  return ids.length > 0 ? ids.join(' ') : undefined
})
</script>

<template>
  <div class="form-field" :class="{ 'form-field--error': invalid }">
    <label class="text-body-strong form-field__label" :for="resolvedInputId">
      <slot name="label">{{ label }}</slot>
      <span v-if="required" class="form-field__required">必須</span>
    </label>
    <slot :input-id="resolvedInputId" :described-by="describedBy" :invalid="invalid" />
    <p v-if="invalid" :id="errorId" class="form-field__error text-caption-sm">
      <v-icon :icon="mdiAlertCircleOutline" size="16" />
      <span>{{ error }}</span>
    </p>
    <p v-if="help !== undefined" :id="helpId" class="text-caption-sm text-on-surface-variant">
      {{ help }}
    </p>
  </div>
</template>

<style scoped>
.form-field {
  display: grid;
  gap: 4px;
}
.form-field p {
  margin: 0;
}
.form-field__label {
  display: block;
}
.form-field__required {
  display: inline-block;
  margin-left: 8px;
  vertical-align: 1px;
  font-size: 0.75rem;
  font-weight: 600;
  line-height: 1.5;
  padding: 0 6px;
  color: rgb(var(--v-theme-on-surface-variant));
  border: 1px solid rgba(var(--v-border-color), 0.4);
  border-radius: 2px;
}
.form-field__error {
  display: flex;
  gap: 6px;
  align-items: flex-start;
  font-weight: 600;
  color: rgb(var(--v-theme-error));
}
.form-field__error :deep(.v-icon) {
  margin-top: 1px;
}
</style>
