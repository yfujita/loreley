<script setup lang="ts">
// 識別子の入力確認(DS 4.8。データソースの削除): 「確認のため識別子 `…` を入力してください」+入力欄。
// 貼り付けを許可し(`autocomplete="off"`・`spellcheck="false"`)、前後の空白は無視して完全一致(大文字小文字を区別)で判定する。
// 一致したら「識別子が一致しました」、一致しない間は入力があれば「識別子が一致しません」を `aria-live="polite"` で出す。
// 判定結果は `update:matched` で親(ConfirmDialog の実行ボタンの有効・無効)に伝える。
import { computed, watch } from 'vue'

import { matchesIdentifier } from './matchesIdentifier'
import { mdiAlertCircleOutline, mdiCheckCircleOutline } from '@/shared/theme/icons'
import FormField from '@/shared/ui/FormField.vue'

const props = defineProps<{
  /** 入力させる識別子(`source_id`) */
  expected: string
  /** 実行中(二重送信を防ぐため、入力を無効にする) */
  disabled?: boolean
}>()

const model = defineModel<string>({ default: '' })
const emit = defineEmits<{ 'update:matched': [matched: boolean] }>()

const matched = computed(() => matchesIdentifier(model.value, props.expected))
watch(matched, (value) => emit('update:matched', value), { immediate: true })

const showMismatch = computed(() => model.value.trim() !== '' && !matched.value)
</script>

<template>
  <FormField :label="`確認のため識別子 ${expected} を入力してください`" required>
    <template #label
      >確認のため識別子 <code class="text-id">{{ expected }}</code> を入力してください</template
    >
    <template #default="{ inputId }">
      <v-text-field
        :id="inputId"
        v-model="model"
        autocomplete="off"
        spellcheck="false"
        :disabled="disabled"
      />
    </template>
  </FormField>
  <p class="type-to-confirm__result text-caption-sm" aria-live="polite">
    <template v-if="matched">
      <v-icon :icon="mdiCheckCircleOutline" color="success" size="16" />
      <span class="type-to-confirm__ok">識別子が一致しました</span>
    </template>
    <template v-else-if="showMismatch">
      <v-icon :icon="mdiAlertCircleOutline" color="error" size="16" />
      <span class="type-to-confirm__ng">識別子が一致しません</span>
    </template>
  </p>
</template>

<style scoped>
.type-to-confirm__result {
  display: flex;
  gap: 6px;
  align-items: center;
  margin: 4px 0 0;
  min-height: 18px;
  font-weight: 600;
}
.type-to-confirm__ok {
  color: rgb(var(--v-theme-success));
}
.type-to-confirm__ng {
  color: rgb(var(--v-theme-error));
}
</style>
