<template>
  <div class="login-page">
    <section class="login-card login-card--admin">
      <p class="panel__eyebrow">Admin Access</p>
      <h1>进入后台管理</h1>
      <p class="muted">
        这里是管理员和系统运维使用的后台管理系统。直播工作人员请从独立的 Studio
        登录入口进入操作中台。
      </p>

      <form class="login-form" @submit.prevent="submit">
        <label>
          用户名
          <input v-model="form.username" type="text" required />
        </label>
        <label>
          密码
          <input v-model="form.password" type="password" required />
        </label>
        <label>
          角色
          <select v-model="form.role">
            <option value="admin">admin</option>
          </select>
        </label>

        <p v-if="auth.error" class="error-text">{{ auth.error }}</p>

        <button class="primary-button" :disabled="auth.loading" type="submit">
          {{ auth.loading ? '登录中...' : '登录后台管理' }}
        </button>
      </form>

      <div class="login-card__links">
        <RouterLink class="ghost-button login-card__studio-link" :to="{ name: 'studio-login' }">
          直播工作人员登录入口
        </RouterLink>
      </div>
    </section>
  </div>
</template>

<script setup>
import { reactive } from 'vue'
import { RouterLink, useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()

const form = reactive({
  username: 'demo-admin',
  password: 'demo',
  role: 'admin'
})

async function submit() {
  await auth.loginWithCredentials(form)
  router.push('/workbench')
}
</script>
