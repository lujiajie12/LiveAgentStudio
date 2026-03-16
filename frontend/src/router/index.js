import { createRouter, createWebHistory } from 'vue-router'

import { hasAuthToken } from '@/utils/auth'
import AppShell from '@/layouts/AppShell.vue'
import KnowledgePage from '@/pages/KnowledgePage.vue'
import LoginPage from '@/pages/LoginPage.vue'
import ReportsPage from '@/pages/ReportsPage.vue'
import SystemPage from '@/pages/SystemPage.vue'
import WorkbenchPage from '@/pages/WorkbenchPage.vue'

const routes = [
  {
    path: '/login',
    name: 'login',
    component: LoginPage,
    meta: { public: true }
  },
  {
    path: '/',
    component: AppShell,
    meta: { requiresAuth: true },
    children: [
      { path: '', redirect: '/workbench' },
      { path: '/workbench', name: 'workbench', component: WorkbenchPage },
      { path: '/knowledge', name: 'knowledge', component: KnowledgePage },
      { path: '/reports', name: 'reports', component: ReportsPage },
      { path: '/system', name: 'system', component: SystemPage }
    ]
  }
]

export function buildRouter(history = createWebHistory()) {
  const router = createRouter({
    history,
    routes
  })

  router.beforeEach((to) => {
    if (to.meta.public) {
      return true
    }
    if (!hasAuthToken()) {
      return { name: 'login' }
    }
    return true
  })

  return router
}

export const router = buildRouter()
