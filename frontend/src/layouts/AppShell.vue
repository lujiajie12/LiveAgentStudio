<template>
  <div class="shell">
    <aside class="shell__nav">
      <div>
        <p class="shell__eyebrow">LiveAgent Studio</p>
        <h1>运营中台</h1>
      </div>
      <nav class="shell__menu">
        <RouterLink to="/workbench">工作台</RouterLink>
        <RouterLink to="/knowledge">知识管理</RouterLink>
        <RouterLink to="/reports">复盘分析</RouterLink>
        <RouterLink to="/system">系统管理</RouterLink>
      </nav>
      <div class="shell__user">
        <p>{{ auth.user?.username || '未登录' }}</p>
        <small>{{ auth.user?.role || 'guest' }}</small>
        <button type="button" class="ghost-button" @click="logout">退出</button>
      </div>
    </aside>
    <main class="shell__main">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()

function logout() {
  auth.logout()
  router.push('/login')
}
</script>
