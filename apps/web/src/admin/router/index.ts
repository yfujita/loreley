import { createRouter, createWebHistory } from 'vue-router'

import PlaceholderPage from './PlaceholderPage.vue'

// base は vite.config.ts の base('/admin/')と一致する。
export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [{ path: '/', name: 'placeholder', component: PlaceholderPage }],
})
