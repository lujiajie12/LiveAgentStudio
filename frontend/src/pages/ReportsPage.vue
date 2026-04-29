<template>
  <section class="feature-page">
    <header class="feature-page__header">
      <div>
        <p class="panel__eyebrow">Reports</p>
        <h1>复盘报告中心</h1>
        <p class="muted">读取 AnalystAgent 产出的结构化报告，查看高频问题与优化建议。</p>
      </div>
      <button class="ghost-button" type="button" @click="loadReports">刷新报告</button>
    </header>

    <div class="split-grid split-grid--wide">
      <article class="panel">
        <header class="panel__header">
          <div>
            <p class="panel__eyebrow">Report List</p>
            <h2>最近报告</h2>
          </div>
        </header>
        <div class="list-grid">
          <button
            v-for="report in reports"
            :key="report.id"
            class="list-card list-card--button"
            type="button"
            @click="selectReport(report.id)"
          >
            <div class="list-card__row">
              <strong>{{ report.session_id }}</strong>
              <span class="pill">{{ report.total_messages }} 条消息</span>
            </div>
            <p class="muted">{{ report.summary }}</p>
          </button>
        </div>
      </article>

      <article class="panel">
        <header class="panel__header">
          <div>
            <p class="panel__eyebrow">Report Detail</p>
            <h2>详情</h2>
          </div>
        </header>
        <div v-if="activeReport" class="stack">
          <div class="dashboard-grid dashboard-grid--compact">
            <article class="stat-card">
              <span>消息总量</span>
              <strong>{{ activeReport.total_messages }}</strong>
            </article>
            <article class="stat-card">
              <span>热门商品</span>
              <strong>{{ activeReport.hot_products.join(' / ') || '暂无' }}</strong>
            </article>
          </div>
          <pre class="code-block">{{ JSON.stringify(activeReport, null, 2) }}</pre>
        </div>
        <p v-else class="muted">先从左侧选择一份报告。</p>
      </article>
    </div>
  </section>
</template>

<script setup>
import { onMounted, ref } from 'vue'

import { fetchReport, listReports } from '@/api/reports'

const reports = ref([])
const activeReport = ref(null)

async function loadReports() {
  reports.value = await listReports()
  if (!activeReport.value && reports.value.length) {
    await selectReport(reports.value[0].id)
  }
}

async function selectReport(reportId) {
  activeReport.value = await fetchReport(reportId)
}

onMounted(loadReports)
</script>
