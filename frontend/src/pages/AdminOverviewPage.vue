<template>
  <section class="backoffice-overview">
    <header class="backoffice-overview__header">
      <div class="backoffice-overview__headline">
        <div class="backoffice-overview__eyebrow">
          <AppIcon name="layout-dashboard" :size="16" />
          <span>BACKOFFICE</span>
        </div>
        <h1>直播智能体后台管理</h1>
        <p>
          这里负责索引、检索调试、链路观测、复盘和系统配置。直播工作人员请从独立的
          Studio 登录入口进入直播操作中台。
        </p>
      </div>

      <RouterLink
        class="backoffice-overview__hero-link"
        :to="{ name: 'studio-login', query: { next: '/studio-v2' } }"
      >
        <span>进入 LiveAgent STUDIO v2.0</span>
        <AppIcon name="chevron-right" :size="16" />
      </RouterLink>
    </header>

    <section class="backoffice-overview__stats">
      <article
        v-for="item in statusCards"
        :key="item.label"
        class="backoffice-overview__stat"
      >
        <div class="backoffice-overview__stat-icon">
          <AppIcon :name="item.icon" :size="20" />
        </div>
        <div class="backoffice-overview__stat-body">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
        </div>
      </article>
    </section>

    <section class="backoffice-overview__grid">
      <div class="backoffice-overview__modules">
        <p class="backoffice-overview__section-label">Quick Links / 后台管理模块</p>

        <RouterLink
          v-for="item in moduleCards"
          :key="item.title"
          :to="item.to"
          class="backoffice-module-card"
        >
          <span class="backoffice-module-card__icon">
            <AppIcon :name="item.icon" :size="20" />
          </span>

          <span class="backoffice-module-card__content">
            <span class="backoffice-module-card__header">
              <strong>{{ item.title }}</strong>
              <span
                class="backoffice-module-card__tag"
                :class="`backoffice-module-card__tag--${item.tone}`"
              >
                {{ item.tag }}
              </span>
            </span>
            <span class="backoffice-module-card__desc">{{ item.desc }}</span>
          </span>

          <span class="backoffice-module-card__action">
            <AppIcon name="chevron-right" :size="18" />
          </span>
        </RouterLink>
      </div>

      <aside class="backoffice-overview__studio">
        <p class="backoffice-overview__section-label">Studio v2.0</p>

        <article class="backoffice-studio-panel">
          <div class="backoffice-studio-panel__ghost" aria-hidden="true">
            <AppIcon name="monitor-play" :size="108" />
          </div>

          <h2>直播操作中台</h2>

          <div class="backoffice-studio-panel__section">
            <h3>这套界面面向谁</h3>
            <p>
              主播、场控、运营、客服在直播过程中使用，用来处理观众问题、生成话术、控场和提词器推送。
            </p>
          </div>

          <div class="backoffice-studio-panel__divider"></div>

          <div class="backoffice-studio-panel__section">
            <h3>为什么独立拆出去</h3>
            <p>
              把直播操作界面和后台管理系统分离，避免管理员页面和直播场控页面混在一起，角色边界更清楚。
            </p>
          </div>

          <RouterLink
            class="backoffice-studio-panel__button"
            :to="{ name: 'studio-login', query: { next: '/studio-v2' } }"
          >
            <span>打开独立 Studio 页面</span>
            <AppIcon name="external-link" :size="16" />
          </RouterLink>
        </article>
      </aside>
    </section>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { RouterLink } from 'vue-router'

import AppIcon from '@/components/AppIcon.vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

const statusCards = computed(() => [
  { label: '系统定位', value: '后台管理系统', icon: 'server' },
  { label: '适用角色', value: auth.user?.role || 'admin', icon: 'shield-check' },
  { label: 'Studio 入口', value: '/studio-login', icon: 'zap' }
])

const moduleCards = [
  {
    title: '离线索引管理',
    tag: 'RAG',
    tone: 'rag',
    icon: 'database',
    to: '/rag/offline',
    desc: '触发全量或增量索引，查看文档数量、任务状态和索引日志。'
  },
  {
    title: '在线检索调试',
    tag: 'DEBUG',
    tone: 'debug',
    icon: 'search',
    to: '/rag/online',
    desc: '查看 query rewrite、BM25、向量检索、RRF、Rerank 和最终上下文。'
  },
  {
    title: 'Agent Flow',
    tag: 'TRACE',
    tone: 'trace',
    icon: 'activity',
    to: '/agent-flow',
    desc: '排查 Router、QA、Script、Analyst、Guardrail 的全链路执行细节。'
  },
  {
    title: '复盘报告',
    tag: 'ANALYST',
    tone: 'analyst',
    icon: 'file-text',
    to: '/reports',
    desc: '查看直播复盘、未解决问题、高频问题和优化建议。'
  },
  {
    title: '系统设置',
    tag: 'OPS',
    tone: 'ops',
    icon: 'settings',
    to: '/system',
    desc: '查看健康状态、延迟指标、降级事件和 Agent 偏好配置。'
  }
]
</script>
