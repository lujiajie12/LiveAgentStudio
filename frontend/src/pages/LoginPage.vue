<template>
  <div class="login-page">
    <section class="login-card">
      <p class="panel__eyebrow">LiveAgent Studio</p>
      <h1>进入运营工作台</h1>
      <p class="muted">
        当前是 MVP 骨架登录入口。首次登录会自动创建本地用户并签发 token。
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
            <option value="operator">operator</option>
            <option value="broadcaster">broadcaster</option>
            <option value="admin">admin</option>
          </select>
        </label>
        <p v-if="auth.error" class="error-text">{{ auth.error }}</p>
        <button class="primary-button" :disabled="auth.loading" type="submit">
          {{ auth.loading ? '登录中...' : '登录' }}
        </button>
      </form>
    </section>
  </div>
</template>

<script setup>
import { reactive } from 'vue'
import { useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()
const form = reactive({
  username: 'demo-operator',
  password: 'demo',
  role: 'operator'
})

async function submit() {
  await auth.loginWithCredentials(form)
  router.push('/workbench')
}
</script>
