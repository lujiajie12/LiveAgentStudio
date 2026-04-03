<template>
  <section class="feature-page">
    <header class="feature-page__header">
      <div>
        <p class="panel__eyebrow">RAG Offline</p>
        <h1>离线索引管理</h1>
        <p class="muted">统一查看源文档、ES/Milvus 数量、最近任务和索引日志。</p>
      </div>
      <div class="toolbar">
        <button class="ghost-button" type="button" @click="refresh">刷新概览</button>
        <button class="primary-button" type="button" @click="startIncremental">
          启动增量索引
        </button>
      </div>
    </header>

    <article class="panel">
      <p class="muted">
        当前版本的离线索引默认扫描
        <strong class="stat-card__mono">docs/data</strong>
        目录。把 FAQ、商品资料和规则文档替换进去后，可以直接在这里触发重建。
      </p>
      <p class="muted">
        增量索引：不重建现有索引，主要用于续跑或补跑。
        全量索引：会自动带上重建参数，先清空旧索引再重新构建。
      </p>
    </article>

    <div class="dashboard-grid">
      <article class="stat-card">
        <span>源文档数量</span>
        <strong>{{ overview?.source_file_count ?? '-' }}</strong>
      </article>
      <article class="stat-card">
        <span>BM25 文档数</span>
        <strong>{{ overview?.bm25_count ?? '-' }}</strong>
      </article>
      <article class="stat-card">
        <span>Milvus 向量数</span>
        <strong>{{ overview?.vector_count ?? '-' }}</strong>
      </article>
      <article class="stat-card">
        <span>源目录</span>
        <strong class="stat-card__mono">{{ overview?.docs_dir || '-' }}</strong>
      </article>
    </div>

    <section class="split-grid">
      <article class="panel">
        <header class="panel__header">
          <div>
            <p class="panel__eyebrow">Jobs</p>
            <h2>任务操作</h2>
          </div>
        </header>
        <div class="field-grid">
          <label class="field">
            <span>文档目录</span>
            <input v-model="jobForm.docs_dir" type="text" placeholder="留空使用默认 docs/data" />
          </label>
          <label class="checkbox-field">
            <input v-model="jobForm.reset" type="checkbox" />
            <span>强制重建</span>
          </label>
          <label class="checkbox-field">
            <input v-model="jobForm.es_only" type="checkbox" />
            <span>仅 ES</span>
          </label>
          <label class="checkbox-field">
            <input v-model="jobForm.milvus_only" type="checkbox" />
            <span>仅 Milvus</span>
          </label>
        </div>
        <div class="toolbar">
          <button class="ghost-button" type="button" @click="startJob('incremental')">增量索引</button>
          <button class="ghost-button" type="button" @click="startJob('full')">全量索引</button>
          <button
            class="ghost-button"
            type="button"
            :disabled="!ragOps.activeJob?.id"
            @click="refreshJob"
          >
            刷新任务状态
          </button>
        </div>
        <p v-if="jobStatusText" class="muted">{{ jobStatusText }}</p>
        <p v-if="ragOps.error" class="error-text">{{ ragOps.error }}</p>
      </article>

      <article class="panel">
        <header class="panel__header">
          <div>
            <p class="panel__eyebrow">Active Job</p>
            <h2>当前任务</h2>
          </div>
        </header>
        <div v-if="ragOps.activeJob" class="stack">
          <div class="detail-grid">
            <div><span class="muted">任务 ID</span><strong>{{ ragOps.activeJob.id }}</strong></div>
            <div><span class="muted">状态</span><strong>{{ ragOps.activeJob.status }}</strong></div>
            <div><span class="muted">PID</span><strong>{{ ragOps.activeJob.pid || '-' }}</strong></div>
            <div><span class="muted">类型</span><strong>{{ ragOps.activeJob.job_type }}</strong></div>
          </div>
          <pre class="code-block">{{ activeJobLog }}</pre>
        </div>
        <p v-else class="muted">尚未启动索引任务。</p>
      </article>
    </section>

    <article class="panel">
      <header class="panel__header">
        <div>
          <p class="panel__eyebrow">History</p>
          <h2>最近任务</h2>
        </div>
      </header>
      <div class="list-grid">
        <article
          v-for="job in overview?.recent_jobs || []"
          :key="job.id"
          class="list-card"
        >
          <div class="list-card__row">
            <strong>{{ job.job_type }}</strong>
            <span class="pill">{{ job.status }}</span>
          </div>
          <p class="muted stat-card__mono">{{ job.id }}</p>
          <p class="muted">{{ job.docs_dir || '默认目录' }}</p>
        </article>
      </div>
    </article>
  </section>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive } from 'vue'

import { useRagOpsStore } from '@/stores/ragOps'

const ragOps = useRagOpsStore()
const overview = computed(() => ragOps.offlineOverview)
const activeJob = computed(() => ragOps.activeJob)
const activeJobLog = computed(() => (activeJob.value?.log_tail || []).join('\n') || '暂无日志')
const jobStatusText = computed(() => {
  if (!activeJob.value) {
    return ''
  }
  if (activeJob.value.status === 'running') {
    return '索引任务运行中，页面会自动刷新状态和日志。'
  }
  if (activeJob.value.status === 'completed') {
    return '索引任务已完成。'
  }
  if (activeJob.value.status === 'failed') {
    return `索引任务失败：${activeJob.value.error_message || '请查看日志'}`
  }
  return ''
})

const jobForm = reactive({
  docs_dir: '',
  reset: false,
  es_only: false,
  milvus_only: false
})

let pollTimer = null

async function refresh() {
  await ragOps.loadOfflineOverview()
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function ensurePolling() {
  if (!activeJob.value?.id || activeJob.value.status !== 'running' || pollTimer) {
    return
  }
  pollTimer = setInterval(async () => {
    if (!activeJob.value?.id) {
      stopPolling()
      return
    }
    await ragOps.refreshOfflineJob(activeJob.value.id)
    await ragOps.loadOfflineOverview()
    if (ragOps.activeJob?.status !== 'running') {
      stopPolling()
    }
  }, 2000)
}

async function startJob(jobType) {
  await ragOps.startOfflineJob({
    job_type: jobType,
    docs_dir: jobForm.docs_dir || null,
    reset: jobType === 'full' ? true : jobForm.reset,
    es_only: jobForm.es_only,
    milvus_only: jobForm.milvus_only
  })
  ensurePolling()
}

async function startIncremental() {
  await startJob('incremental')
}

async function refreshJob() {
  if (ragOps.activeJob?.id) {
    await ragOps.refreshOfflineJob(ragOps.activeJob.id)
    await ragOps.loadOfflineOverview()
    ensurePolling()
  }
}

onMounted(async () => {
  await refresh()
  ensurePolling()
})

onUnmounted(stopPolling)
</script>
