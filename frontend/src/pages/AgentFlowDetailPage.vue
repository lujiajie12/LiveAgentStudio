<template>
  <section class="feature-page">
    <header class="feature-page__header">
      <div>
        <p class="panel__eyebrow">Trace Detail</p>
        <h1>链路详情</h1>
        <p class="muted">完整 trace、记忆快照和工具日志在独立页面查看，不再挤占主页面。</p>
      </div>
      <div class="toolbar">
        <button class="ghost-button" type="button" @click="router.push({ name: 'agent-flow' })">返回列表</button>
        <button class="ghost-button" type="button" :disabled="!traceDetail" @click="downloadTrace">
          下载 JSON
        </button>
        <button class="primary-button" type="button" @click="loadTrace">刷新详情</button>
      </div>
    </header>

    <div v-if="traceDetail" class="stack">
      <div class="dashboard-grid">
        <article class="stat-card">
          <span>Trace</span>
          <strong class="stat-card__mono">{{ traceDetail.trace_id }}</strong>
        </article>
        <article class="stat-card">
          <span>Session</span>
          <strong class="stat-card__mono">{{ traceDetail.session_id || '-' }}</strong>
        </article>
        <article class="stat-card">
          <span>日志条数</span>
          <strong>{{ traceDetail.logs?.length || 0 }}</strong>
        </article>
        <article class="stat-card">
          <span>状态统计</span>
          <strong>{{ summarizeStatuses(traceDetail.logs) }}</strong>
        </article>
      </div>

      <div class="split-grid split-grid--wide">
        <article class="panel">
          <header class="panel__header">
            <div>
              <p class="panel__eyebrow">Memory Snapshot</p>
              <h2>记忆快照</h2>
            </div>
          </header>
          <pre class="code-block code-block--detail">{{ JSON.stringify(traceDetail.memory, null, 2) }}</pre>
        </article>

        <article class="panel">
          <header class="panel__header">
            <div>
              <p class="panel__eyebrow">Timeline Summary</p>
              <h2>链路摘要</h2>
            </div>
          </header>
          <div class="list-grid">
            <article
              v-for="log in compactLogs"
              :key="log.id"
              class="list-card"
            >
              <div class="list-card__row">
                <strong>{{ log.tool_name }}</strong>
                <span class="pill">{{ log.status }}</span>
              </div>
              <p class="muted">node={{ log.node_name || '-' }} / {{ log.category }} / {{ log.latency_ms }}ms</p>
              <p class="muted">{{ truncate(log.output_summary) }}</p>
            </article>
          </div>
        </article>
      </div>

      <article class="panel">
        <header class="panel__header">
          <div>
            <p class="panel__eyebrow">Full Logs</p>
            <h2>完整工具日志</h2>
          </div>
        </header>
        <pre class="code-block code-block--detail">{{ JSON.stringify(traceDetail.logs, null, 2) }}</pre>
      </article>
    </div>

    <article v-else class="panel">
      <p class="muted">正在加载 trace 详情...</p>
    </article>

    <p v-if="agentFlow.error" class="error-text">{{ agentFlow.error }}</p>
  </section>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAgentFlowStore } from '@/stores/agentFlow'

const route = useRoute()
const router = useRouter()
const agentFlow = useAgentFlowStore()

const traceDetail = computed(() => agentFlow.activeTrace)
const compactLogs = computed(() => (traceDetail.value?.logs || []).slice(0, 12))

async function loadTrace() {
  await agentFlow.loadTraceDetail(route.params.traceId)
}

function summarizeStatuses(logs) {
  if (!logs?.length) {
    return '-'
  }
  const counts = logs.reduce((acc, item) => {
    acc[item.status] = (acc[item.status] || 0) + 1
    return acc
  }, {})
  return Object.entries(counts)
    .map(([key, value]) => `${key}:${value}`)
    .join(' / ')
}

function truncate(value) {
  if (!value) {
    return '无输出摘要'
  }
  return value.length > 96 ? `${value.slice(0, 96)}...` : value
}

function downloadTrace() {
  if (!traceDetail.value) {
    return
  }
  const blob = new Blob([JSON.stringify(traceDetail.value, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${traceDetail.value.trace_id}.json`
  link.click()
  URL.revokeObjectURL(url)
}

onMounted(loadTrace)
</script>
