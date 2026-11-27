<script setup lang="ts">
// キー・バリュー表示(DS 4.4): `<dl>`。2 列(項目名 200px・値は残り)、行ごとに薄い区切り線。
// 値がない項目は「—」を出し、読み上げ用に「未設定」「なし」を添える(視覚的に隠す)。補足は値の下に 12px。
// 値の見た目(識別子・状態タグ・日時など)は `value-<key>` スロットで差し替える。幅 600px 未満は項目名の下に値を積む(1 列)。
// カード(見出し付き)の中に置く。1 つのカードに入れる項目は 10 件程度まで(超えるときはカードを分ける)。
export type KeyValueItem = {
  key: string
  label: string
  /** 値。null・空文字は「—」 */
  value?: string | null
  /** 値の下の補足(タイムゾーンなど) */
  note?: string
  /** 値がないときの読み上げ(視覚的に隠す)。既定は「未設定」 */
  emptyLabel?: string
}

defineProps<{ items: readonly KeyValueItem[] }>()

function hasValue(item: KeyValueItem): boolean {
  return item.value !== undefined && item.value !== null && item.value !== ''
}
</script>

<template>
  <dl class="key-value-list">
    <template v-for="item in items" :key="item.key">
      <dt>{{ item.label }}</dt>
      <dd>
        <slot :name="`value-${item.key}`" :item="item">
          <template v-if="hasValue(item)">{{ item.value }}</template>
          <span v-else class="text-on-surface-variant"
            >—<span class="sr-only">({{ item.emptyLabel ?? '未設定' }})</span></span
          >
        </slot>
        <span
          v-if="item.note !== undefined"
          class="key-value-list__note text-caption-sm text-on-surface-variant"
          >{{ item.note }}</span
        >
      </dd>
    </template>
  </dl>
</template>

<style scoped>
.key-value-list {
  display: grid;
  grid-template-columns: 200px minmax(0, 1fr);
  margin: 0;
}
.key-value-list dt,
.key-value-list dd {
  margin: 0;
  padding: 10px 16px;
  border-bottom: 1px solid rgba(var(--v-border-color), 0.08);
}
.key-value-list dt {
  color: rgb(var(--v-theme-on-surface-variant));
}
.key-value-list dd {
  overflow-wrap: anywhere;
}
.key-value-list dt:last-of-type,
.key-value-list dd:last-of-type {
  border-bottom: 0;
}
.key-value-list__note {
  display: block;
}
@media (max-width: 599px) {
  .key-value-list {
    grid-template-columns: minmax(0, 1fr);
  }
  .key-value-list dt {
    padding-bottom: 0;
    border-bottom: 0;
    font-size: 0.75rem;
  }
}
</style>
