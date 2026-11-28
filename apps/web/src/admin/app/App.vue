<script setup lang="ts">
// アプリのルート。シェル(サイドバー・上部バー・本文・スナックバー)を組み立てる。
// ナビのグループ定義(`navGroups`)は `router` にあり、`shell` は `router` を import できないので、ここで渡す。
import { navGroups } from '@/admin/router'
import AppShell from '@/admin/shell/AppShell.vue'
</script>

<template>
  <AppShell :nav-groups="navGroups" />
</template>
