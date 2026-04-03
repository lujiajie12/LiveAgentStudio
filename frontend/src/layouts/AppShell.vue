<template>
  <div class="shell shell--studio">
    <div class="shell__backdrop" aria-hidden="true">
      <div class="shell__glow shell__glow--indigo"></div>
      <div class="shell__glow shell__glow--purple"></div>
      <div class="shell__glow shell__glow--blue"></div>
      <div class="shell__noise"></div>
    </div>

    <div class="shell__frame">
      <aside class="shell__nav shell__nav--studio">
        <div>
          <div class="brand-card">
            <div class="brand-card__logo">
              <AppIcon name="settings" :size="18" />
            </div>
            <div>
              <p class="shell__eyebrow">LiveAgent Studio</p>
              <h1>直播智能体后台管理</h1>
            </div>
          </div>

          <nav class="shell__menu shell__menu--studio">
            <RouterLink
              v-for="item in navItems"
              :key="item.to"
              :to="item.to"
              class="nav-link"
            >
              <span class="nav-link__icon">
                <AppIcon :name="item.icon" :size="18" />
              </span>
              <span>{{ item.label }}</span>
            </RouterLink>
          </nav>
        </div>

        <div class="shell__user shell__user--studio">
          <RouterLink
            class="primary-button shell__studio-link"
            :to="{ name: 'studio-login', query: { next: '/studio-v2' } }"
          >
            进入 LiveAgent STUDIO v2.0
          </RouterLink>

          <div class="user-card">
            <div class="user-card__avatar">
              <AppIcon name="user" :size="18" />
            </div>
            <div class="user-card__meta">
              <p>{{ auth.user?.username || 'demo-admin' }}</p>
              <small>{{ auth.user?.role || 'admin' }}</small>
            </div>
          </div>

          <button type="button" class="logout-link" @click="logout">
            <AppIcon name="logout" :size="16" />
            <span>退出登录</span>
          </button>
        </div>
      </aside>

      <main class="shell__main shell__main--studio">
        <router-view />
      </main>
    </div>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'

import AppIcon from '@/components/AppIcon.vue'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()

const navItems = [
  { to: '/workbench', label: '首页', icon: 'home' },
  { to: '/rag/offline', label: '离线索引管理', icon: 'book-open' },
  { to: '/rag/online', label: '在线检索调试', icon: 'list-todo' },
  { to: '/memory/qa', label: 'QA Memory', icon: 'history' },
  { to: '/agent-flow', label: 'Agent Flow', icon: 'workflow' },
  { to: '/reports', label: '复盘报告', icon: 'monitor-play' },
  { to: '/system', label: '系统设置', icon: 'settings' }
]

function logout() {
  auth.logout()
  router.push('/login')
}
</script>
