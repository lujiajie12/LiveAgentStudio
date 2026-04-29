import { createRouter, createWebHistory } from 'vue-router'

import { hasAuthToken } from '@/utils/auth'
import AppShell from '@/layouts/AppShell.vue'
import AdminOverviewPage from '@/pages/AdminOverviewPage.vue'
import AgentFlowDetailPage from '@/pages/AgentFlowDetailPage.vue'
import AgentFlowPage from '@/pages/AgentFlowPage.vue'
import KnowledgePage from '@/pages/KnowledgePage.vue'
import LoginPage from '@/pages/LoginPage.vue'
import MemoryInsightsPage from '@/pages/MemoryInsightsPage.vue'
import RagOnlinePage from '@/pages/RagOnlinePage.vue'
import ReportsPage from '@/pages/ReportsPage.vue'
import LiveSimulatorPage from '@/pages/LiveSimulatorPage.vue'
import StudioLoginPage from '@/pages/StudioLoginPage.vue'
import SystemPage from '@/pages/SystemPage.vue'
import TeleprompterPage from '@/pages/TeleprompterPage.vue'
import WorkbenchPage from '@/pages/WorkbenchPage.vue'
import { hasStudioAuthToken } from '@/utils/studioAuth'

const routes = [
  {
    path: '/login',
    name: 'login',
    component: LoginPage,
    meta: { public: true }
  },
  {
    path: '/studio-login',
    name: 'studio-login',
    component: StudioLoginPage,
    meta: { public: true }
  },
  {
    path: '/studio-v2',
    name: 'studio-v2',
    component: WorkbenchPage,
    meta: { requiresStudioAuth: true }
  },
  {
    path: '/live-simulator',
    name: 'live-simulator',
    component: LiveSimulatorPage,
    meta: { requiresStudioAuth: true }
  },
  {
    path: '/teleprompter/:sessionId',
    name: 'teleprompter',
    component: TeleprompterPage,
    meta: { requiresStudioAuth: true }
  },
  {
    path: '/',
    component: AppShell,
    meta: { requiresAuth: true },
    children: [
      { path: '', redirect: '/workbench' },
      { path: '/workbench', name: 'workbench', component: AdminOverviewPage },
      { path: '/knowledge', redirect: '/rag/offline' },
      { path: '/rag/offline', name: 'rag-offline', component: KnowledgePage },
      { path: '/rag/online', name: 'rag-online', component: RagOnlinePage },
      { path: '/memory/qa', name: 'memory-qa', component: MemoryInsightsPage },
      { path: '/agent-flow', name: 'agent-flow', component: AgentFlowPage },
      { path: '/agent-flow/:traceId', name: 'agent-flow-detail', component: AgentFlowDetailPage },
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
    if (to.meta.requiresStudioAuth) {
      if (!hasStudioAuthToken()) {
        return { name: 'studio-login', query: { next: to.fullPath } }
      }
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
