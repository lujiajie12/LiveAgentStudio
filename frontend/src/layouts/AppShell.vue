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
              <AppIcon name="cpu" :size="20" />
            </div>
            <div class="brand-card__copy">
              <h1>LiveAgent</h1>
              <p>STUDIO HUB</p>
            </div>
          </div>

          <nav class="shell__menu shell__menu--studio" aria-label="后台管理导航">
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
          <div class="shell__user-row">
            <div class="user-card">
              <div class="user-card__avatar">
                <AppIcon name="user" :size="18" />
              </div>
              <div class="user-card__meta">
                <p>{{ auth.user?.username || 'demo-admin' }}</p>
                <small>{{ auth.user?.role || '管理员' }}</small>
              </div>
            </div>
            <ThemeWaveSwitch variant="shell" />
          </div>

          <button type="button" class="logout-link" @click="logout">
            <AppIcon name="logout" :size="16" />
            <span>退出登录</span>
          </button>
        </div>
      </aside>

      <main class="shell__main shell__main--studio">
        <header class="shell__topbar">
          <div>
            <h2>后台管理中心</h2>
            <div class="shell__topbar-status">
              <span aria-hidden="true"></span>
              <strong>System Active</strong>
            </div>
          </div>

          <div class="shell__topbar-actions">
            <button type="button" class="shell__icon-button" aria-label="通知">
              <AppIcon name="bell" :size="20" />
              <span aria-hidden="true"></span>
            </button>
            <div class="shell__topbar-separator" aria-hidden="true"></div>
            <div class="shell__version">
              <strong>Studio V2.4.0</strong>
              <span>Stable Release</span>
            </div>
          </div>
        </header>

        <section class="shell__content">
          <router-view />
        </section>
      </main>
    </div>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'

import AppIcon from '@/components/AppIcon.vue'
import ThemeWaveSwitch from '@/components/ThemeWaveSwitch.vue'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()

const navItems = [
  { to: '/workbench', label: '首页', icon: 'home' },
  { to: '/rag/offline', label: '离线索引管理', icon: 'database' },
  { to: '/rag/online', label: '在线检索调试', icon: 'search' },
  { to: '/memory/qa', label: 'QA Memory', icon: 'brain' },
  { to: '/agent-flow', label: 'Agent Flow', icon: 'workflow' },
  { to: '/reports', label: '复盘报告', icon: 'bar-chart-3' },
  { to: '/system', label: '系统设置', icon: 'settings' }
]

function logout() {
  auth.logout()
  router.push('/login')
}
</script>
