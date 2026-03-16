<template>
  <section class="feature-page">
    <header class="feature-page__header">
      <div>
        <p class="panel__eyebrow">System</p>
        <h1>系统状态</h1>
      </div>
      <button class="ghost-button" type="button" @click="load">刷新</button>
    </header>

    <div class="report-grid">
      <article v-for="(status, name) in health.services" :key="name" class="stat-card">
        <span>{{ name }}</span>
        <strong>{{ status }}</strong>
      </article>
    </div>
  </section>
</template>

<script setup>
import { onMounted, reactive } from 'vue'

import { fetchSystemHealth } from '@/api/system'

const health = reactive({
  status: 'unknown',
  services: {}
})

async function load() {
  const data = await fetchSystemHealth()
  health.status = data.status
  health.services = data.services
}

onMounted(load)
</script>
