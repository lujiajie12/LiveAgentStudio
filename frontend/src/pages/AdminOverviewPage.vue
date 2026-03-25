<template>
  <section class="feature-page admin-overview">
    <header class="feature-page__header">
      <div>
        <p class="panel__eyebrow">Backoffice</p>
        <h1>直播智能体后台管理</h1>
        <p class="muted">
          这里负责索引、检索调试、链路观测、复盘和系统配置。直播工作人员请从独立的
          Studio 登录入口进入直播操作中台。
        </p>
      </div>
      <RouterLink class="primary-button" :to="{ name: 'studio-login', query: { next: '/studio-v2' } }">
        进入 LiveAgent STUDIO v2.0
      </RouterLink>
    </header>

    <div class="dashboard-grid">
      <article class="stat-card">
        <span>系统定位</span>
        <strong>后台管理系统</strong>
      </article>
      <article class="stat-card">
        <span>适用角色</span>
        <strong>admin</strong>
      </article>
      <article class="stat-card">
        <span>Studio 入口</span>
        <strong>/studio-login</strong>
      </article>
    </div>

    <div class="split-grid split-grid--wide">
      <article class="panel">
        <header class="panel__header">
          <div>
            <p class="panel__eyebrow">Quick Links</p>
            <h2>后台管理模块</h2>
          </div>
        </header>

        <div class="list-grid">
          <RouterLink class="list-card list-card--button" to="/rag/offline">
            <div class="list-card__row">
              <strong>离线索引管理</strong>
              <span class="pill">RAG</span>
            </div>
            <p class="muted">触发全量或增量索引，查看文档数量、任务状态和索引日志。</p>
          </RouterLink>

          <RouterLink class="list-card list-card--button" to="/rag/online">
            <div class="list-card__row">
              <strong>在线检索调试</strong>
              <span class="pill">Debug</span>
            </div>
            <p class="muted">查看 query rewrite、BM25、向量检索、RRF、Rerank 和最终上下文。</p>
          </RouterLink>

          <RouterLink class="list-card list-card--button" to="/agent-flow">
            <div class="list-card__row">
              <strong>Agent Flow</strong>
              <span class="pill">Trace</span>
            </div>
            <p class="muted">排查 Router、QA、Script、Analyst、Guardrail 的全链路执行细节。</p>
          </RouterLink>

          <RouterLink class="list-card list-card--button" to="/reports">
            <div class="list-card__row">
              <strong>复盘报告</strong>
              <span class="pill">Analyst</span>
            </div>
            <p class="muted">查看直播复盘、未解决问题、高频问题和优化建议。</p>
          </RouterLink>

          <RouterLink class="list-card list-card--button" to="/system">
            <div class="list-card__row">
              <strong>系统设置</strong>
              <span class="pill">Ops</span>
            </div>
            <p class="muted">查看健康状态、延迟指标、降级事件和 Agent 偏好配置。</p>
          </RouterLink>
        </div>
      </article>

      <article class="panel admin-overview__studio-card">
        <header class="panel__header">
          <div>
            <p class="panel__eyebrow">Studio v2.0</p>
            <h2>直播操作中台</h2>
          </div>
        </header>

        <div class="stack">
          <div class="note-card">
            <strong>这套界面面向谁</strong>
            <p class="muted">主播、场控、运营、客服在直播过程中使用，用来处理观众问题、生成话术、控场和提词器推送。</p>
          </div>

          <div class="note-card">
            <strong>为什么独立拆出去</strong>
            <p class="muted">把直播操作界面和后台管理系统分离，避免管理员页面和直播场控页面混在一起，角色边界更清楚。</p>
          </div>

          <RouterLink class="primary-button admin-overview__cta" :to="{ name: 'studio-login', query: { next: '/studio-v2' } }">
            打开独立 Studio 页面
          </RouterLink>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup>
import { RouterLink } from 'vue-router'
</script>
