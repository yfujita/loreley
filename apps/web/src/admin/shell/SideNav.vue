<script setup lang="ts">
// サイドバーの中身(DS 5.1・5.3): ブランド・ナビ項目・外部リンク領域。
// ナビ項目は `router.getRoutes()` の `meta.nav` から作る(定義は route `meta` にだけ持つ)。グループの順序と表示名
// (`navGroups`)は `admin/app` が渡す(`shell`(層 4)は `router`(層 6)を import しない)。
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import ExternalLinks from './ExternalLinks.vue'
import { buildNavGroups, navItemCurrent, type NavGroupDefinition } from './navItems'

const props = defineProps<{ navGroups: readonly NavGroupDefinition[] }>()

const router = useRouter()
const route = useRoute()

const groups = computed(() =>
  buildNavGroups(router.getRoutes(), props.navGroups, {
    // `featureFlag` を持つ route は、フラグが有効なときだけ出す。MVP の `/meta` にフラグはなく、
    // `featureFlag` を持つ route もないので、持つ route は出さない(安全側)。
    isFeatureEnabled: () => false,
    onUnknownGroup: (groupId) => {
      if (import.meta.env.DEV) {
        console.warn(
          `SideNav: 未定義のナビグループです(group=${groupId})。router/navGroups.ts に行を足してください。末尾のグループとして出します。`,
        )
      }
    },
  }),
)

function current(routeName: string): 'page' | 'true' | undefined {
  const result = navItemCurrent(routeName, route.name, router.getRoutes())
  if (result === null) return undefined
  return result === 'page' ? 'page' : 'true'
}
</script>

<template>
  <div class="side-nav">
    <div class="side-nav__brand">
      <svg viewBox="0 0 24 24" aria-hidden="true" width="24" height="24">
        <rect width="24" height="24" rx="6" fill="rgb(var(--v-theme-primary))" />
        <path
          d="M4 14c2.2-4 3.8-4 6 0s3.8 4 6 0 2.8-3 4-3"
          fill="none"
          stroke="#fff"
          stroke-width="2"
          stroke-linecap="round"
        />
      </svg>
      <span class="side-nav__brand-text">Loreley<small>管理</small></span>
    </div>

    <template v-for="(group, groupIndex) in groups" :key="group.id">
      <hr v-if="groupIndex > 0" class="side-nav__divider" />
      <ul class="side-nav__group" :aria-label="group.label">
        <li v-for="item in group.items" :key="item.routeName">
          <router-link
            class="side-nav__item"
            :class="{ 'side-nav__item--current': current(item.routeName) !== undefined }"
            :to="{ name: item.routeName }"
            :aria-current="current(item.routeName)"
            :data-testid="`nav-${item.routeName}`"
          >
            <v-icon :icon="item.icon" size="20" />
            <span>{{ item.label }}</span>
          </router-link>
        </li>
      </ul>
    </template>

    <div class="side-nav__grow" />
    <ExternalLinks />
  </div>
</template>

<style scoped>
.side-nav {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-height: 100%;
  padding: 16px 12px;
  color: rgb(var(--v-theme-on-surface));
}
.side-nav__brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 12px 16px;
  font-size: 1rem;
  font-weight: 600;
  line-height: 1.2;
}
.side-nav__brand-text small {
  display: block;
  font-size: 0.75rem;
  font-weight: 400;
  color: rgb(var(--v-theme-on-surface-variant));
}
.side-nav__divider {
  border: 0;
  border-top: 1px solid rgba(var(--v-border-color), 0.2);
  margin: 8px 12px;
}
.side-nav__group {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.side-nav__item {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 40px;
  padding: 0 12px;
  border-radius: 4px;
  color: rgb(var(--v-theme-on-surface));
  text-decoration: none;
}
.side-nav__item:hover {
  background: rgba(var(--v-theme-primary), 0.08);
}
.side-nav__item :deep(.v-icon) {
  color: rgb(var(--v-theme-on-surface-variant));
}
/* 現在地: 面が白に変わり、左に 3px の primary の帯、文字は 600(DS 5.1) */
.side-nav__item--current {
  background: rgb(var(--v-theme-surface));
  font-weight: 600;
  box-shadow: inset 3px 0 0 rgb(var(--v-theme-primary));
}
.side-nav__item--current :deep(.v-icon) {
  color: rgb(var(--v-theme-primary));
}
.side-nav__grow {
  flex: 1;
}
</style>
