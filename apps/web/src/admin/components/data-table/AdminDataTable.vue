<script setup lang="ts" generic="T extends Record<string, unknown>">
// データテーブル(クライアント側のページング・並べ替え。DS 4.3): 件数が少ない一覧(S1 のデータソース。数十件まで)用。
// `VDataTable` を、`AdminDataTableServer` と同じ props・イベントの形で使えるように包む(FMOD-U-4)。
// 矢印キーでの行移動には頼らない(DS 4.3)。並べ替えは見出しのボタン(Enter)で、`aria-sort` は Vuetify が付ける。
// 幅 840px 未満は行をカード状に積む(Vuetify の `mobile`。`display.mobileBreakpoint: 'md'` に従う)。
import { computed } from 'vue'

import SkeletonRows from './SkeletonRows.vue'
import {
  fromVuetifySortBy,
  toVuetifyHeaders,
  toVuetifySortBy,
  type AdminColumn,
  type AdminSort,
  type VuetifySortItem,
} from './tableModel'
import './dataTable.css'

const props = withDefaults(
  defineProps<{
    columns: readonly AdminColumn[]
    items: readonly T[]
    /** 行を識別するキー(`source_id` など) */
    itemKey: keyof T & string
    /** 視覚的に隠す `<caption>`(DS 8) */
    caption: string
    sort?: AdminSort
    /** 並べ替えを解除できないようにする(昇順と降順だけを切り替える) */
    mustSort?: boolean
    itemsPerPage?: 25 | 50 | 100
    /** 初回読み込み中: 表と同じ列構成のスケルトンを出す */
    loading?: boolean
    /** 行に付ける `data-testid`(DS 9。`{画面 ID}-row-{識別子}`) */
    rowTestid?: (item: T) => string | undefined
  }>(),
  {
    sort: null,
    mustSort: false,
    itemsPerPage: 25,
    loading: false,
    rowTestid: undefined,
  },
)

const emit = defineEmits<{ 'update:sort': [sort: AdminSort] }>()

const headers = computed(() => toVuetifyHeaders(props.columns, props.sort))
const sortBy = computed(() => toVuetifySortBy(props.sort))

function onSortBy(value: VuetifySortItem[]): void {
  emit('update:sort', fromVuetifySortBy(value))
}

function rowProps(data: { item: T }): Record<string, string | undefined> {
  return { 'data-testid': props.rowTestid?.(data.item) }
}
</script>

<template>
  <v-data-table
    class="admin-data-table"
    :headers="headers"
    :items="items as T[]"
    :item-value="itemKey"
    :sort-by="sortBy"
    :mobile="null"
    :must-sort="mustSort"
    :items-per-page="itemsPerPage"
    :items-per-page-options="[25, 50, 100]"
    items-per-page-text="1 ページの件数"
    :show-first-last-page="false"
    :hide-default-footer="loading"
    page-text="{0}–{1} / {2} 件"
    :row-props="rowProps"
    :aria-busy="loading ? 'true' : undefined"
    @update:sort-by="onSortBy"
  >
    <template #caption>
      <caption class="sr-only">
        {{
          caption
        }}
      </caption>
    </template>
    <template v-if="loading" #body>
      <SkeletonRows :column-count="columns.length" />
    </template>
    <template v-for="(_, slotName) in $slots" :key="slotName" #[slotName]="slotProps">
      <slot :name="slotName" v-bind="slotProps ?? {}" />
    </template>
  </v-data-table>
</template>
