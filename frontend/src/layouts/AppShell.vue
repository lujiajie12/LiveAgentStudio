<template>
  <div class="shell shell--backoffice">
    <div class="shell__backdrop" aria-hidden="true">
      <div class="shell__glow shell__glow--indigo"></div>
      <div class="shell__glow shell__glow--purple"></div>
      <div class="shell__glow shell__glow--blue"></div>
      <div class="shell__noise"></div>
    </div>

    <div class="shell__frame shell__frame--backoffice">
      <aside class="backoffice-sidebar">
        <div class="backoffice-sidebar__top">
          <RouterLink class="backoffice-brand" to="/workbench">
            <span class="backoffice-brand__logo">
              <AppIcon name="monitor-play" :size="20" />
            </span>
            <span class="backoffice-brand__text">
              <span class="backoffice-brand__eyebrow">LiveAgent Studio</span>
              <span class="backoffice-brand__title">直播智能体后台</span>
            </span>
          </RouterLink>

          <nav class="backoffice-nav backoffice-scrollbar">
            <RouterLink
              v-for="item in navItems"
              :key="item.to"
              :to="item.to"
              class="backoffice-nav__item"
              :class="{ 'backoffice-nav__item--active': isNavActive(item) }"
            >
              <span class="backoffice-nav__icon">
                <AppIcon :name="item.icon" :size="18" />
              </span>
              <span class="backoffice-nav__label">{{ item.label }}</span>
              <span v-if="isNavActive(item)" class="backoffice-nav__dot"></span>
            </RouterLink>
          </nav>
        </div>

        <div class="backoffice-sidebar__bottom">
          <RouterLink
            class="backoffice-studio-entry"
            :to="{ name: 'studio-login', query: { next: '/studio-v2' } }"
          >
            <AppIcon name="external-link" :size="16" />
            <span>进入 Studio v2.0</span>
          </RouterLink>

          <div class="backoffice-user-card">
            <span class="backoffice-user-card__avatar">
              <AppIcon name="user" :size="17" />
            </span>
            <span class="backoffice-user-card__meta">
              <strong>{{ displayUsername }}</strong>
              <small>{{ displayRole }}</small>
            </span>
            <button
              type="button"
              class="backoffice-user-card__logout"
              aria-label="退出登录"
              @click="logout"
            >
              <AppIcon name="logout" :size="16" />
            </button>
          </div>
        </div>
      </aside>

      <main class="shell__main shell__main--backoffice">
        <router-view />
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import AppIcon from '@/components/AppIcon.vue'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const navItems = [
  { to: '/workbench', label: '首页', icon: 'home' },
  { to: '/rag/offline', label: '离线索引管理', icon: 'database' },
  { to: '/rag/online', label: '在线检索调试', icon: 'search' },
  { to: '/memory/qa', label: 'QA Memory', icon: 'message-square' },
  { to: '/agent-flow', label: 'Agent Flow', icon: 'activity' },
  { to: '/reports', label: '复盘报告', icon: 'file-text' },
  { to: '/system', label: '系统设置', icon: 'settings' }
]

const displayUsername = computed(() => auth.user?.username || 'demo-admin')
const displayRole = computed(() => auth.user?.role || 'admin')

function isNavActive(item) {
  return route.path === item.to || route.path.startsWith(`${item.to}/`)
}

function logout() {
  auth.logout()
  router.push('/login')
}
</script>
