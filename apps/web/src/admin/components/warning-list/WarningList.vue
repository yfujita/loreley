<script setup lang="ts">
// 警告リスト(DS 4.11): ジョブの警告のように、日本語の説明が要る項目を並べる。
// 1 項目 = 警告アイコン+見出し(14px / 600。日本語の要約)+詳細(14px。直し方・確認すること)+警告コード(12px・等幅。補足)。
// コードを見出しにしない(利用者に意味が伝わらないため)。コードから文言への対応は画面側の表(features/jobs/catalogs)が持ち、
// ここは並べるだけ。未知のコードの文言(見出しを「警告(コード)」にして詳細は空)も、画面側が組み立てて渡す。
import { mdiAlertOutline } from '@/shared/theme/icons'

export type WarningItem = {
  key: string
  /** 日本語の要約 */
  title: string
  /** 直し方・確認すること(空なら出さない) */
  detail?: string
  /** 警告コード(補足) */
  code?: string
}

defineProps<{ items: readonly WarningItem[] }>()
</script>

<template>
  <ul v-if="items.length > 0" class="warning-list">
    <li v-for="item in items" :key="item.key" class="warning-list__item">
      <v-icon :icon="mdiAlertOutline" color="warning" size="20" />
      <div>
        <p class="text-body-strong">{{ item.title }}</p>
        <p v-if="item.detail" class="text-body">{{ item.detail }}</p>
        <p v-if="item.code" class="text-id text-on-surface-variant warning-list__code">
          {{ item.code }}
        </p>
      </div>
    </li>
  </ul>
</template>

<style scoped>
.warning-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.warning-list__item {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 12px 16px;
  border-bottom: 1px solid rgba(var(--v-border-color), 0.08);
}
.warning-list__item:last-child {
  border-bottom: 0;
}
.warning-list__item .v-icon {
  margin-top: 1px;
}
.warning-list__item p {
  margin: 0;
}
.warning-list__code {
  font-size: 0.75rem;
}
</style>
