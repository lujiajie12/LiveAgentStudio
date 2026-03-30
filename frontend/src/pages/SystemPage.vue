<template>
  <section class="feature-page">
    <header class="feature-page__header">
      <div>
        <p class="panel__eyebrow">System</p>
        <h1>系统健康与偏好设置</h1>
        <p class="muted">统一查看依赖服务状态、节点指标，并维护主播默认风格和敏感词。</p>
      </div>
      <button class="ghost-button" type="button" @click="load">刷新</button>
    </header>

    <div class="dashboard-grid">
      <article
        v-for="(service, name) in settings.health?.services || {}"
        :key="name"
        class="stat-card"
      >
        <span>{{ name }}</span>
        <strong>{{ service.status }}</strong>
        <small class="muted">{{ service.reason || service.model || '' }}</small>
      </article>
    </div>

    <section class="split-grid split-grid--wide">
      <article class="panel">
        <header class="panel__header">
          <div>
            <p class="panel__eyebrow">Metrics</p>
            <h2>节点指标</h2>
          </div>
        </header>
        <div class="dashboard-grid dashboard-grid--compact">
          <article class="stat-card">
            <span>错误次数</span>
            <strong>{{ settings.metrics?.metrics?.error_count ?? 0 }}</strong>
          </article>
          <article class="stat-card">
            <span>降级次数</span>
            <strong>{{ settings.metrics?.metrics?.degraded_count ?? 0 }}</strong>
          </article>
          <article class="stat-card">
            <span>拦截次数</span>
            <strong>{{ settings.metrics?.metrics?.intercept_count ?? 0 }}</strong>
          </article>
        </div>
        <pre class="code-block">{{ JSON.stringify(settings.metrics?.metrics?.node_p95_ms || {}, null, 2) }}</pre>
      </article>

      <article class="panel">
        <header class="panel__header">
          <div>
            <p class="panel__eyebrow">Preferences</p>
            <h2>主播偏好与自定义敏感词</h2>
          </div>
        </header>
        <div class="field-grid field-grid--wide">
          <label class="field">
            <span>默认话术风格</span>
            <select v-model="settings.preferences.script_style">
              <option value="">自动</option>
              <option value="professional">professional</option>
              <option value="friendly">friendly</option>
              <option value="promotional">promotional</option>
            </select>
          </label>
          <label class="field field--full">
            <span>自定义敏感词（逗号分隔）</span>
            <textarea v-model="customSensitiveTermsText" rows="4" />
          </label>
        </div>
        <div class="toolbar">
          <button class="primary-button" type="button" @click="save">保存配置</button>
        </div>
        <p v-if="settings.error" class="error-text">{{ settings.error }}</p>
      </article>
    </section>
  </section>
</template>

<script setup>
import { computed, onMounted } from 'vue'

import { useSettingsStore } from '@/stores/settings'

const settings = useSettingsStore()

const customSensitiveTermsText = computed({
  get: () => (settings.preferences.custom_sensitive_terms || []).join(', '),
  set: (value) => {
    settings.preferences.custom_sensitive_terms = value
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean)
  }
})

async function load() {
  await settings.loadDashboard()
}

async function save() {
  await settings.savePreferences()
}

onMounted(load)
</script>
