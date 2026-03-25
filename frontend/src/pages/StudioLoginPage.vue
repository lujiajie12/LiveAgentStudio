<template>
  <div class="studio-login">
    <section class="studio-login__hero">
      <div class="studio-login__glow studio-login__glow--indigo"></div>
      <div class="studio-login__glow studio-login__glow--purple"></div>
      <div class="studio-login__grid"></div>

      <div class="studio-login__hero-content">
        <div class="studio-login__brand">
          <div class="studio-login__brand-icon">
            <AppIcon name="bot" :size="30" />
          </div>
          <div>
            <h1>LiveAgent Studio</h1>
            <p>Enterprise Edition</p>
          </div>
        </div>

        <h2>下一代多智能体<br />直播运营中台</h2>
        <p class="studio-login__hero-copy">
          融合 RAG 知识引擎与 Multi-Agent 架构，提供毫秒级弹幕意图解析、实时话术生成与全链路风控，赋能企业级直播电商。
        </p>

        <div class="studio-login__badges">
          <div class="studio-login__badge">
            <AppIcon name="database" :size="16" />
            <span>毫秒级 RAG 检索</span>
          </div>
          <div class="studio-login__badge">
            <AppIcon name="activity" :size="16" />
            <span>实时流意图捕获</span>
          </div>
          <div class="studio-login__badge">
            <AppIcon name="sparkles" :size="16" />
            <span>Agent 编排流</span>
          </div>
        </div>
      </div>
    </section>

    <section class="studio-login__panel">
      <div class="studio-login__security">
        <AppIcon name="shield-check" :size="14" />
        <span>系统安全防护中</span>
      </div>

      <div class="studio-login__form-wrap">
        <div class="studio-login__mobile-brand">
          <div class="studio-login__brand-icon">
            <AppIcon name="bot" :size="22" />
          </div>
          <h1>LiveAgent</h1>
        </div>

        <div class="studio-login__heading">
          <h2>欢迎回来</h2>
          <p>登录到您的 LiveAgent 企业工作台</p>
        </div>

        <form class="studio-login__form" @submit.prevent="submit">
          <label class="studio-login__field">
            <span>工作邮箱 / 账号</span>
            <div class="studio-login__input-shell">
              <AppIcon name="mail" :size="18" />
              <input
                v-model="form.username"
                type="text"
                required
                placeholder="operator@company.com"
              />
            </div>
          </label>

          <label class="studio-login__field">
            <div class="studio-login__field-row">
              <span>登录密码</span>
              <RouterLink class="studio-login__link" to="/login">切换到后台管理</RouterLink>
            </div>
            <div class="studio-login__input-shell">
              <AppIcon name="lock" :size="18" />
              <input
                v-model="form.password"
                type="password"
                required
                placeholder="••••••••"
              />
            </div>
          </label>

          <label class="studio-login__field">
            <span>角色</span>
            <div class="studio-login__input-shell">
              <AppIcon name="user" :size="18" />
              <select v-model="form.role">
                <option value="operator">operator</option>
                <option value="broadcaster">broadcaster</option>
              </select>
            </div>
          </label>

          <label class="studio-login__remember">
            <input type="checkbox" />
            <span>保持登录状态</span>
          </label>

          <p v-if="studioAuth.error" class="error-text">{{ studioAuth.error }}</p>

          <button class="studio-login__submit" :disabled="studioAuth.loading" type="submit">
            <template v-if="studioAuth.loading">
              <span>系统验证中...</span>
            </template>
            <template v-else>
              <span>进入控制台</span>
              <AppIcon name="arrow-right" :size="18" />
            </template>
          </button>
        </form>

        <div class="studio-login__actions">
          <RouterLink class="studio-login__back" to="/login">返回后台管理登录</RouterLink>
        </div>

        <p class="studio-login__copyright">
          © {{ year }} LiveAgent Studio. All rights reserved.
        </p>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, reactive } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import AppIcon from '@/components/AppIcon.vue'
import { useStudioAuthStore } from '@/stores/studioAuth'

const route = useRoute()
const router = useRouter()
const studioAuth = useStudioAuthStore()

const year = computed(() => new Date().getFullYear())

const form = reactive({
  username: 'demo-operator',
  password: 'demo',
  role: 'operator'
})

async function submit() {
  await studioAuth.loginWithCredentials(form)
  router.push(String(route.query.next || '/studio-v2'))
}
</script>
